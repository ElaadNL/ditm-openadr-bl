"""Reading what the vendor hosting the VEN reports back as received.

This is the single place where the vendor specific formats are dealt with. Two
shapes are supported:

- a table of received signals, one row per interval, read by
  `read_vendor_profile` and described by `VendorColumnMapping`;
- the OCPP message log of the charge point operator, read by
  `read_ocpp_limit_steps`, which holds the SetChargingProfile calls the CSMS
  sent to the charger rather than the intervals themselves.

Everything downstream works on `CapacitySignal` and `AppliedLimit` objects, so a
third format only needs a reader here.
"""

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

from src.application.capacity_profile import INTERVAL_DURATION, CapacitySignal
from src.infrastructure.csv_profile import parse_iso_duration
from src.logger import logger

_FALLBACK_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    # The charge point operator logs day first, with a 12 hour clock.
    "%d/%m/%Y %I:%M:%S %p %z",
    "%d/%m/%Y %H:%M:%S %z",
)

_DELIMITERS = ",;\t"

_OCPP_COLUMNS = (
    "Transferred On",
    "Sender",
    "Message Type",
    "Action",
    "chargingSchedulePeriod",
    "power_W",
    "power_W_without_buffer",
)

_WATT_PER_KW = 1000.0


@dataclass(frozen=True)
class VendorColumnMapping:
    """How the columns of a vendor export map onto a capacity signal.

    Attributes:
        start_column (str): Column holding the start of the interval.
        value_column (str): Column holding the capacity limit in kW.
        duration_column (str | None): Column holding the duration of the
            interval. None when the export has no such column.
        default_duration (timedelta): Duration to assume when the export has no
            duration column.
        assume_timezone (tzinfo): Timezone to assume for timestamps that carry no
            UTC offset.
    """

    start_column: str = "start_utc"
    value_column: str = "value_kw"
    duration_column: str | None = "duration"
    default_duration: timedelta = INTERVAL_DURATION
    assume_timezone: tzinfo = UTC


def read_vendor_profile(
    path: Path, mapping: VendorColumnMapping | None = None
) -> list[CapacitySignal]:
    """Read the signals a vendor reports as received by the VEN.

    Args:
        path (Path): The export to read.
        mapping (VendorColumnMapping | None): How to interpret the columns.
            Defaults to the schema this repository writes.

    Returns:
        list[CapacitySignal]: The reported signals, ordered by start.

    Raises:
        ValueError: If the export lacks the mapped columns or holds no rows.
    """
    column_mapping = mapping or VendorColumnMapping()

    with path.open(newline="", encoding="utf-8-sig") as export:
        sample = export.read(4096)
        export.seek(0)
        reader = csv.DictReader(export, delimiter=_sniff_delimiter(sample))
        columns = set(reader.fieldnames or ())

        required = {column_mapping.start_column, column_mapping.value_column}
        missing = required - columns
        if missing:
            err_msg = (
                f"{path} is missing the columns {sorted(missing)}. "
                f"It holds {sorted(columns)}."
            )
            raise ValueError(err_msg)

        duration_column = column_mapping.duration_column
        if duration_column and duration_column not in columns:
            logger.warning(
                "%s has no %s column, assuming intervals of %s.",
                path,
                duration_column,
                column_mapping.default_duration,
            )
            duration_column = None

        signals = [
            CapacitySignal(
                start=_parse_moment(
                    row[column_mapping.start_column], column_mapping.assume_timezone
                ),
                duration=(
                    parse_iso_duration(row[duration_column])
                    if duration_column
                    else column_mapping.default_duration
                ),
                value_kw=float(row[column_mapping.value_column]),
            )
            for row in reader
            if row.get(column_mapping.start_column)
        ]

    if not signals:
        err_msg = f"{path} does not contain any intervals."
        raise ValueError(err_msg)

    signals.sort(key=lambda signal: signal.start)
    return signals


@dataclass(frozen=True)
class AppliedLimit:
    """The charging limit in force from a moment onwards.

    Attributes:
        at (datetime): The moment the limit takes effect.
        signalled_kw (float): The limit as it was signalled to the operator, in
            kW. This is the value to compare a published profile against.
        applied_kw (float): The limit the operator actually sent to the charger,
            in kW. Operators tend to keep a safety margin below the signal.
    """

    at: datetime
    signalled_kw: float
    applied_kw: float

    @property
    def buffer_fraction(self) -> float:
        """The fraction of the signalled limit the operator holds back."""
        if self.signalled_kw == 0:
            return 0.0
        return 1 - self.applied_kw / self.signalled_kw


@dataclass(frozen=True)
class OcppLimitLog:
    """The limits an OCPP message log reports, and what the log itself covers.

    Attributes:
        charge_point_ids (tuple[str, ...]): The chargers the log holds messages for.
        message_count (int): Number of SetChargingProfile calls in the log.
        first_message_at (datetime): The first call in the log.
        last_message_at (datetime): The last call in the log. Nothing is known
            about the limits after this moment.
        buffer_fraction (float): The fraction of the signalled limit the
            operator holds back, as reported by the log itself.
        steps (list[AppliedLimit]): The limits in force, ordered in time.
    """

    charge_point_ids: tuple[str, ...]
    message_count: int
    first_message_at: datetime
    last_message_at: datetime
    buffer_fraction: float
    steps: list[AppliedLimit]


def read_ocpp_limit_steps(path: Path) -> OcppLimitLog:
    """Read the limits the operator applied from its OCPP message log.

    The log holds one row per OCPP message. Only the SetChargingProfile calls
    the CSMS sent to the charger carry a limit; the CallResults acknowledging
    them are ignored. A single call can announce more than one period, where the
    later periods take effect a number of seconds after the message. A period is
    dropped when the next message supersedes it before it takes effect.

    Args:
        path (Path): The message log to read.

    Returns:
        OcppLimitLog: The limits in force, ordered by the moment they take
            effect with consecutive repetitions of the same limit collapsed,
            together with what the log covers.

    Raises:
        ValueError: If the log lacks the expected columns or holds no
            SetChargingProfile calls.
    """
    with path.open(newline="", encoding="utf-8-sig") as log:
        sample = log.read(4096)
        log.seek(0)
        reader = csv.DictReader(log, delimiter=_sniff_delimiter(sample))
        columns = set(reader.fieldnames or ())

        missing = set(_OCPP_COLUMNS) - columns
        if missing:
            err_msg = (
                f"{path} is missing the columns {sorted(missing)}. "
                f"It holds {sorted(columns)}."
            )
            raise ValueError(err_msg)

        calls = [
            row
            for row in reader
            if row["Sender"] == "CSMS"
            and row["Message Type"] == "Call"
            and row["Action"] == "SetChargingProfile"
            and row["chargingSchedulePeriod"]
        ]

    if not calls:
        err_msg = f"{path} does not contain any SetChargingProfile calls."
        raise ValueError(err_msg)

    calls.sort(key=lambda row: _parse_moment(row["Transferred On"], UTC))

    steps: list[AppliedLimit] = []
    for index, row in enumerate(calls):
        sent_at = _parse_moment(row["Transferred On"], UTC)
        superseded_at = (
            _parse_moment(calls[index + 1]["Transferred On"], UTC)
            if index + 1 < len(calls)
            else None
        )
        buffer_ratio = _buffer_ratio(row)

        for period in json.loads(row["chargingSchedulePeriod"]):
            takes_effect_at = sent_at + timedelta(seconds=float(period["startPeriod"]))
            if superseded_at is not None and takes_effect_at >= superseded_at:
                continue
            applied_kw = float(period["limit"]) / _WATT_PER_KW
            steps.append(
                AppliedLimit(
                    at=takes_effect_at,
                    signalled_kw=round(applied_kw / buffer_ratio, 3),
                    applied_kw=applied_kw,
                )
            )

    steps.sort(key=lambda step: step.at)
    collapsed = [
        step
        for index, step in enumerate(steps)
        if index == 0 or step.signalled_kw != steps[index - 1].signalled_kw
    ]

    return OcppLimitLog(
        charge_point_ids=tuple(
            sorted({row["OCPP Identity"] for row in calls if row.get("OCPP Identity")})
        ),
        message_count=len(calls),
        first_message_at=_parse_moment(calls[0]["Transferred On"], UTC),
        last_message_at=_parse_moment(calls[-1]["Transferred On"], UTC),
        buffer_fraction=round(1 - _buffer_ratio(calls[0]), 6),
        steps=collapsed,
    )


def limit_in_force_at(
    steps: list[AppliedLimit], moment: datetime
) -> AppliedLimit | None:
    """Return the limit that was in force at a given moment.

    Args:
        steps (list[AppliedLimit]): The limits, ordered by effective moment.
        moment (datetime): The moment to look up.

    Returns:
        AppliedLimit | None: The limit in force, or None when the log starts
            after the given moment.
    """
    in_force: AppliedLimit | None = None
    for step in steps:
        if step.at > moment:
            break
        in_force = step
    return in_force


def dominant_limit_between(
    steps: list[AppliedLimit], start: datetime, end: datetime
) -> AppliedLimit | None:
    """Return the limit that was in force for the longest part of a period.

    Sampling exactly on the interval boundary would report the previous limit
    whenever the operator needs a moment to push a change, which reads as a
    deviation while it is only latency. The limit that holds for most of the
    interval is what the interval actually ran on; how quickly a change landed
    is reported separately.

    Args:
        steps (list[AppliedLimit]): The limits, ordered by effective moment.
        start (datetime): Start of the period.
        end (datetime): End of the period.

    Returns:
        AppliedLimit | None: The limit in force longest, or None when the log
            starts after the period.
    """
    held: list[tuple[AppliedLimit, timedelta]] = []

    in_force = limit_in_force_at(steps, start)
    changes = [step for step in steps if start < step.at < end]

    if in_force is not None:
        until = changes[0].at if changes else end
        held.append((in_force, until - start))

    for index, step in enumerate(changes):
        until = changes[index + 1].at if index + 1 < len(changes) else end
        held.append((step, until - step.at))

    if not held:
        return None
    return max(held, key=lambda entry: entry[1])[0]


def _buffer_ratio(row: dict[str, str]) -> float:
    """Work out which fraction of the signalled limit the operator passes on.

    Args:
        row (dict[str, str]): A SetChargingProfile row of the message log.

    Returns:
        float: The ratio between the applied and the signalled limit, 1.0 when
            the log does not report a limit without buffer.
    """
    without_buffer = row.get("power_W_without_buffer")
    applied = row.get("power_W")
    if not without_buffer or not applied or float(without_buffer) == 0:
        return 1.0
    return float(applied) / float(without_buffer)


def _sniff_delimiter(sample: str) -> str:
    """Detect the delimiter of a CSV export.

    Exports produced by a spreadsheet on a Dutch locale tend to be semicolon
    separated, so guessing beats assuming.

    Args:
        sample (str): The first bytes of the file.

    Returns:
        str: The detected delimiter, falling back to a comma.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        return ","


def _parse_moment(value: str, assumed_timezone: tzinfo) -> datetime:
    """Parse a timestamp from a vendor export.

    Args:
        value (str): The timestamp to parse.
        assumed_timezone (tzinfo): Timezone to attach when the timestamp carries
            no UTC offset of its own.

    Returns:
        datetime: The parsed moment, timezone aware.

    Raises:
        ValueError: If the timestamp is in none of the supported formats.
    """
    stripped = value.strip()

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(stripped)
    except ValueError:
        for timestamp_format in _FALLBACK_TIMESTAMP_FORMATS:
            try:
                parsed = datetime.strptime(stripped, timestamp_format)  # noqa: DTZ007
            except ValueError:
                continue
            break

    if parsed is None:
        err_msg = f"{value!r} is not a timestamp in any of the supported formats."
        raise ValueError(err_msg)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=assumed_timezone)

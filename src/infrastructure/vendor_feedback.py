"""Reading the signals the vendor hosting the VEN reports back as received.

This is the single place where the vendor specific format is dealt with. The
defaults assume an export shaped like the CSV this repository writes itself.
When the real export turns out to look different, only the column mapping and
`_parse_moment` below should need to change: everything downstream works on
`CapacitySignal` objects.
"""

import csv
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
)

_DELIMITERS = ",;\t"


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

"""Persistence of capacity profiles as CSV.

A profile is stored as two files: a CSV holding one row per interval, and a
sidecar `<name>.meta.json` holding the metadata that does not belong in a table
(the bounds, the capacity band, the targeting). Keeping the metadata out of the
CSV means the CSV stays a clean rectangle that pandas and Excel can open without
any preprocessing.

The `start_utc` column is authoritative. `start_local` is written for the benefit
of whoever opens the file, since the congestion windows only make sense in local
time.
"""

import csv
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from openadr3_client.models.common.unit import Unit
from openadr3_client.models.event.event_payload import EventPayloadType

from src.application.capacity_profile import AMSTERDAM, CapacitySignal

CSV_COLUMNS = (
    "start_utc",
    "start_local",
    "duration",
    "value_kw",
    "payload_type",
    "unit",
)

PAYLOAD_TYPE = EventPayloadType.IMPORT_CAPACITY_LIMIT.value
UNIT = Unit.KW.value

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def write_profile(
    path: Path, signals: list[CapacitySignal], meta: dict[str, Any]
) -> Path:
    """Write a profile and its metadata sidecar to disk.

    Args:
        path (Path): The path of the CSV file to write.
        signals (list[CapacitySignal]): The profile to write.
        meta (dict[str, Any]): Metadata describing how the profile was produced.

    Returns:
        Path: The path of the metadata sidecar that was written alongside the CSV.

    Raises:
        ValueError: If the profile is empty.
    """
    if not signals:
        err_msg = "refusing to write an empty profile."
        raise ValueError(err_msg)

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_COLUMNS)
        for signal in signals:
            writer.writerow(
                (
                    format_utc(signal.start),
                    signal.start.astimezone(AMSTERDAM).isoformat(),
                    format_iso_duration(signal.duration),
                    f"{signal.value_kw:g}",
                    PAYLOAD_TYPE,
                    UNIT,
                )
            )

    meta_path = meta_path_for(path)
    enriched = {
        **meta,
        "interval_count": len(signals),
        "first_interval_utc": format_utc(signals[0].start),
        "last_interval_end_utc": format_utc(signals[-1].end),
        "timezone": str(AMSTERDAM),
    }
    meta_path.write_text(
        json.dumps(enriched, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return meta_path


def read_profile(path: Path) -> tuple[list[CapacitySignal], dict[str, Any]]:
    """Read a profile and, when present, its metadata sidecar.

    Args:
        path (Path): The path of the CSV file to read.

    Returns:
        tuple[list[CapacitySignal], dict[str, Any]]: The signals, ordered by
            start, and the metadata. The metadata is empty when no sidecar exists.

    Raises:
        ValueError: If the CSV is missing required columns or holds no rows.
    """
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = {"start_utc", "duration", "value_kw"} - set(reader.fieldnames or ())
        if missing:
            err_msg = f"{path} is missing the columns {sorted(missing)}."
            raise ValueError(err_msg)

        signals = [
            CapacitySignal(
                start=parse_timestamp(row["start_utc"]),
                duration=parse_iso_duration(row["duration"]),
                value_kw=float(row["value_kw"]),
            )
            for row in reader
        ]

    if not signals:
        err_msg = f"{path} does not contain any intervals."
        raise ValueError(err_msg)

    signals.sort(key=lambda signal: signal.start)

    meta_path = meta_path_for(path)
    meta: dict[str, Any] = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    )

    return signals, meta


def meta_path_for(path: Path) -> Path:
    """Return the path of the metadata sidecar belonging to a profile CSV.

    Args:
        path (Path): The path of the CSV file.

    Returns:
        Path: The path of the sidecar, `<name>.meta.json`.
    """
    return path.with_suffix(".meta.json")


def format_utc(moment: datetime) -> str:
    """Format a moment as an ISO 8601 timestamp in UTC.

    Args:
        moment (datetime): The moment to format, timezone aware.

    Returns:
        str: The timestamp, for example 2026-08-05T04:00:00Z.
    """
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp.

    Args:
        value (str): The timestamp to parse.

    Returns:
        datetime: The parsed moment.

    Raises:
        ValueError: If the timestamp cannot be parsed or carries no offset.
    """
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        err_msg = f"timestamp {value!r} does not carry a UTC offset."
        raise ValueError(err_msg)
    return parsed


def format_iso_duration(duration: timedelta) -> str:
    """Format a duration as an ISO 8601 duration.

    Args:
        duration (timedelta): The duration to format.

    Returns:
        str: The duration, for example PT15M.
    """
    total_seconds = int(duration.total_seconds())
    if total_seconds == 0:
        return "PT0S"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    formatted = "PT"
    if hours:
        formatted += f"{hours}H"
    if minutes:
        formatted += f"{minutes}M"
    if seconds:
        formatted += f"{seconds}S"
    return formatted


def parse_iso_duration(value: str) -> timedelta:
    """Parse an ISO 8601 duration.

    Args:
        value (str): The duration to parse, for example PT15M.

    Returns:
        timedelta: The parsed duration.

    Raises:
        ValueError: If the duration is not a supported ISO 8601 duration.
    """
    match = _ISO_DURATION.match(value.strip().upper())
    if not match:
        err_msg = f"{value!r} is not a supported ISO 8601 duration."
        raise ValueError(err_msg)

    parts = {name: float(part) for name, part in match.groupdict(default="0").items()}
    return timedelta(
        days=parts["days"],
        hours=parts["hours"],
        minutes=parts["minutes"],
        seconds=parts["seconds"],
    )

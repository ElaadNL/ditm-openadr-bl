"""Writing a merged profile to CSV.

The merge is the file that gets sent back to the party hosting the VEN, so it
holds both sides next to each other: what was published, what their system was
signalled, what it forwarded to the charger, and the difference.
"""

import csv
from pathlib import Path

from src.application.capacity_profile import AMSTERDAM
from src.application.profile_merge import MergedInterval
from src.infrastructure.csv_profile import format_iso_duration, format_utc

MERGED_COLUMNS = (
    "start_utc",
    "start_local",
    "duration",
    "published_kw",
    "received_kw",
    "applied_kw",
    "delta_kw",
    "status",
)


def write_merged_profile(path: Path, merged: list[MergedInterval]) -> Path:
    """Write the merged intervals to disk.

    Args:
        path (Path): The CSV file to write.
        merged (list[MergedInterval]): The merged intervals, ordered by start.

    Returns:
        Path: The path that was written.

    Raises:
        ValueError: If there is nothing to write.
    """
    if not merged:
        err_msg = "refusing to write an empty merge."
        raise ValueError(err_msg)

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as merged_file:
        writer = csv.writer(merged_file)
        writer.writerow(MERGED_COLUMNS)
        for interval in merged:
            writer.writerow(
                (
                    format_utc(interval.start),
                    interval.start.astimezone(AMSTERDAM).isoformat(),
                    format_iso_duration(interval.duration),
                    f"{interval.published_kw:g}",
                    _optional(interval.received_kw),
                    _optional(interval.applied_kw),
                    _optional(interval.delta_kw),
                    interval.status,
                )
            )

    return path


def _optional(value: float | None) -> str:
    """Format a value that is absent when the message log does not cover it.

    Args:
        value (float | None): The value to format.

    Returns:
        str: The formatted value, empty when absent.
    """
    return "" if value is None else f"{value:g}"

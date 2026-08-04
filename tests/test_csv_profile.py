"""Tests for reading and writing capacity profiles as CSV."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.application.capacity_profile import AMSTERDAM, CapacitySignal
from src.infrastructure.csv_profile import (
    format_iso_duration,
    format_utc,
    meta_path_for,
    parse_iso_duration,
    read_profile,
    write_profile,
)

SIGNALS = [
    CapacitySignal(
        start=datetime(2026, 8, 5, 4, 0, tzinfo=UTC),
        duration=timedelta(minutes=15),
        value_kw=100.0,
    ),
    CapacitySignal(
        start=datetime(2026, 8, 5, 4, 15, tzinfo=UTC),
        duration=timedelta(minutes=15),
        value_kw=68.0,
    ),
]


def test_a_profile_survives_a_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"
    write_profile(path, SIGNALS, {"min_kw": 20, "max_kw": 100})

    read_back, meta = read_profile(path)

    assert read_back == SIGNALS
    assert meta["min_kw"] == 20
    assert meta["interval_count"] == 2


def test_the_metadata_lands_in_a_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"

    meta_path = write_profile(path, SIGNALS, {"generator_version": "1.0"})

    assert meta_path == tmp_path / "profile.meta.json"
    assert meta_path == meta_path_for(path)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["generator_version"] == "1.0"
    assert meta["first_interval_utc"] == "2026-08-05T04:00:00Z"
    assert meta["last_interval_end_utc"] == "2026-08-05T04:30:00Z"


def test_the_csv_carries_both_a_utc_and_a_local_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"
    write_profile(path, SIGNALS, {})

    rows = path.read_text(encoding="utf-8").splitlines()

    assert rows[0] == "start_utc,start_local,duration,value_kw,payload_type,unit"
    assert rows[1] == (
        "2026-08-05T04:00:00Z,2026-08-05T06:00:00+02:00,PT15M,100,"
        "IMPORT_CAPACITY_LIMIT,KW"
    )


def test_regenerating_a_profile_produces_an_identical_csv(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    write_profile(first, SIGNALS, {"generated_at": "2026-08-04T10:00:00Z"})
    write_profile(second, SIGNALS, {"generated_at": "2026-08-05T11:00:00Z"})

    assert first.read_bytes() == second.read_bytes()


def test_reading_a_profile_without_a_sidecar_yields_empty_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "profile.csv"
    write_profile(path, SIGNALS, {})
    meta_path_for(path).unlink()

    _, meta = read_profile(path)

    assert meta == {}


def test_rows_are_returned_in_chronological_order(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"
    write_profile(path, list(reversed(SIGNALS)), {})

    read_back, _ = read_profile(path)

    assert read_back == SIGNALS


def test_a_csv_without_the_required_columns_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"
    path.write_text("moment,value\n2026-08-05T04:00:00Z,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing the columns"):
        read_profile(path)


def test_an_empty_profile_is_not_written(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty profile"):
        write_profile(tmp_path / "profile.csv", [], {})


def test_a_local_timestamp_is_written_in_local_time(tmp_path: Path) -> None:
    path = tmp_path / "profile.csv"
    write_profile(path, SIGNALS, {})

    read_back, _ = read_profile(path)

    assert read_back[0].start.astimezone(AMSTERDAM).hour == 6


@pytest.mark.parametrize(
    ("duration", "formatted"),
    [
        (timedelta(minutes=15), "PT15M"),
        (timedelta(hours=1), "PT1H"),
        (timedelta(hours=1, minutes=30), "PT1H30M"),
        (timedelta(seconds=30), "PT30S"),
        (timedelta(0), "PT0S"),
    ],
)
def test_durations_round_trip(duration: timedelta, formatted: str) -> None:
    assert format_iso_duration(duration) == formatted
    assert parse_iso_duration(formatted) == duration


def test_a_duration_with_days_is_understood() -> None:
    assert parse_iso_duration("P1DT2H") == timedelta(days=1, hours=2)


def test_an_unsupported_duration_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a supported"):
        parse_iso_duration("15 minutes")


def test_utc_timestamps_are_formatted_with_a_z() -> None:
    assert format_utc(datetime(2026, 8, 5, 6, 0, tzinfo=AMSTERDAM)) == (
        "2026-08-05T04:00:00Z"
    )

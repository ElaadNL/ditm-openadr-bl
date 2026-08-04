"""Tests for reading the signals the VEN vendor reports as received."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.infrastructure.vendor_feedback import VendorColumnMapping, read_vendor_profile

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_an_export_in_our_own_format_is_read_without_configuration(
    tmp_path: Path,
) -> None:
    export = _write(
        tmp_path / "received.csv",
        "start_utc,start_local,duration,value_kw,payload_type,unit\n"
        "2026-08-05T04:00:00Z,2026-08-05T06:00:00+02:00,PT15M,100,"
        "IMPORT_CAPACITY_LIMIT,KW\n",
    )

    signals = read_vendor_profile(export)

    assert len(signals) == 1
    assert signals[0].start == datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
    assert signals[0].value_kw == 100.0
    assert signals[0].duration == timedelta(minutes=15)


def test_a_semicolon_separated_export_with_other_columns_is_read(
    tmp_path: Path,
) -> None:
    export = _write(
        tmp_path / "received.csv",
        "moment;limit_kw\n2026-08-05 06:00;100\n2026-08-05 06:15;20\n",
    )

    signals = read_vendor_profile(
        export,
        VendorColumnMapping(
            start_column="moment",
            value_column="limit_kw",
            duration_column=None,
            assume_timezone=AMSTERDAM,
        ),
    )

    assert [signal.value_kw for signal in signals] == [100.0, 20.0]
    assert signals[0].start == datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
    assert signals[0].duration == timedelta(minutes=15)


def test_a_dutch_day_first_timestamp_is_understood(tmp_path: Path) -> None:
    export = _write(
        tmp_path / "received.csv", "start_utc,value_kw\n05-08-2026 04:00,100\n"
    )

    signals = read_vendor_profile(export, VendorColumnMapping(duration_column=None))

    assert signals[0].start == datetime(2026, 8, 5, 4, 0, tzinfo=UTC)


def test_a_missing_duration_column_falls_back_to_the_default(tmp_path: Path) -> None:
    export = _write(
        tmp_path / "received.csv", "start_utc,value_kw\n2026-08-05T04:00:00Z,100\n"
    )

    signals = read_vendor_profile(export)

    assert signals[0].duration == timedelta(minutes=15)


def test_rows_are_returned_in_chronological_order(tmp_path: Path) -> None:
    export = _write(
        tmp_path / "received.csv",
        "start_utc,value_kw\n2026-08-05T04:15:00Z,20\n2026-08-05T04:00:00Z,100\n",
    )

    signals = read_vendor_profile(export)

    assert [signal.value_kw for signal in signals] == [100.0, 20.0]


def test_an_export_without_the_mapped_columns_is_rejected(tmp_path: Path) -> None:
    export = _write(tmp_path / "received.csv", "when,how_much\n2026-08-05,100\n")

    with pytest.raises(ValueError, match="missing the columns"):
        read_vendor_profile(export)


def test_an_export_without_rows_is_rejected(tmp_path: Path) -> None:
    export = _write(tmp_path / "received.csv", "start_utc,value_kw\n")

    with pytest.raises(ValueError, match="does not contain any intervals"):
        read_vendor_profile(export)


def test_an_unparseable_timestamp_is_rejected(tmp_path: Path) -> None:
    export = _write(tmp_path / "received.csv", "start_utc,value_kw\nyesterday,100\n")

    with pytest.raises(ValueError, match="not a timestamp"):
        read_vendor_profile(export)

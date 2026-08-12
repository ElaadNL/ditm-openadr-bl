"""Tests for reading the OCPP message log of the charge point operator."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.infrastructure.vendor_feedback import (
    dominant_limit_between,
    limit_in_force_at,
    read_ocpp_limit_steps,
)

_HEADER = (
    "OCPP Identity,Transferred On,Parsable,Sender,Message Type,Action,"
    "Error Code,Error Description,chargingSchedulePeriod,power_W,"
    "power_W_without_buffer\n"
)

# A charger that is held at 100 kW, is told at 12:14 that 20 kW follows two
# minutes later, and then gets a plain 20 kW message at 12:15:30 that supersedes
# the announcement before it takes effect.
_LOG = (
    _HEADER
    + "NLTEST0001,4/8/2026 12:00:00 PM +02:00,True,CSMS,Call,SetChargingProfile,,,"
    '"[{""limit"": 90000.0, ""startPeriod"": 0}]",90000.0,100000.0\n'
    "NLTEST0001,4/8/2026 12:00:01 PM +02:00,True,CS,CallResult,SetChargingProfile,,,,,\n"
    "NLTEST0001,4/8/2026 12:14:00 PM +02:00,True,CSMS,Call,SetChargingProfile,,,"
    '"[{""limit"": 90000.0, ""startPeriod"": 0}, {""limit"": 18000.0, ""startPeriod"": 120}]"'
    ",90000.0,100000.0\n"
    "NLTEST0001,4/8/2026 12:15:30 PM +02:00,True,CSMS,Call,SetChargingProfile,,,"
    '"[{""limit"": 18000.0, ""startPeriod"": 0}]",18000.0,20000.0\n'
)

NOON_UTC = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
QUARTER_PAST = datetime(2026, 8, 4, 10, 15, tzinfo=UTC)


def _write_log(tmp_path: Path, content: str = _LOG) -> Path:
    path = tmp_path / "charger-message-log.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_only_the_calls_that_carry_a_limit_are_read(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    assert log.message_count == 3
    assert log.charge_point_ids == ("NLTEST0001",)
    assert log.first_message_at == NOON_UTC
    assert log.last_message_at == datetime(2026, 8, 4, 10, 15, 30, tzinfo=UTC)


def test_the_operator_buffer_is_read_from_the_log(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    assert log.buffer_fraction == pytest.approx(0.1)
    assert log.steps[0].signalled_kw == 100.0
    assert log.steps[0].applied_kw == 90.0
    assert log.steps[0].buffer_fraction == pytest.approx(0.1)


def test_repeated_messages_collapse_into_one_step(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    assert [step.signalled_kw for step in log.steps] == [100.0, 20.0]


def test_an_announcement_the_next_message_supersedes_is_dropped(
    tmp_path: Path,
) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    # The 12:14 message announced 20 kW for 12:16, but 12:15:30 overtook it.
    assert log.steps[1].at == datetime(2026, 8, 4, 10, 15, 30, tzinfo=UTC)


def test_an_announcement_that_survives_takes_effect_on_its_own_offset(
    tmp_path: Path,
) -> None:
    log = read_ocpp_limit_steps(
        _write_log(
            tmp_path,
            _HEADER + "NLTEST0001,4/8/2026 12:14:00 PM +02:00,True,CSMS,Call,"
            'SetChargingProfile,,,"[{""limit"": 90000.0, ""startPeriod"": 0}, '
            '{""limit"": 18000.0, ""startPeriod"": 120}]",90000.0,100000.0\n',
        )
    )

    assert [step.at for step in log.steps] == [
        datetime(2026, 8, 4, 10, 14, tzinfo=UTC),
        datetime(2026, 8, 4, 10, 16, tzinfo=UTC),
    ]


def test_the_limit_on_a_boundary_is_still_the_previous_one(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    in_force = limit_in_force_at(log.steps, QUARTER_PAST)

    assert in_force is not None
    assert in_force.signalled_kw == 100.0


def test_the_dominant_limit_is_the_one_the_interval_ran_on(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    dominant = dominant_limit_between(
        log.steps, QUARTER_PAST, QUARTER_PAST + timedelta(minutes=15)
    )

    assert dominant is not None
    assert dominant.signalled_kw == 20.0


def test_nothing_is_known_before_the_first_message(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(_write_log(tmp_path))

    assert limit_in_force_at(log.steps, NOON_UTC - timedelta(minutes=1)) is None
    assert (
        dominant_limit_between(log.steps, NOON_UTC - timedelta(minutes=15), NOON_UTC)
        is None
    )


def test_a_semicolon_separated_log_is_read(tmp_path: Path) -> None:
    log = read_ocpp_limit_steps(
        _write_log(
            tmp_path,
            "OCPP Identity;Transferred On;Parsable;Sender;Message Type;Action;"
            "Error Code;Error Description;chargingSchedulePeriod;power_W;"
            "power_W_without_buffer\n"
            "NLTEST0001;4/8/2026 12:00:00 PM +02:00;True;CSMS;Call;"
            'SetChargingProfile;;;"[{""limit"": 90000.0, ""startPeriod"": 0}]"'
            ";90000.0;100000.0\n",
        )
    )

    assert log.message_count == 1
    assert log.steps[0].signalled_kw == 100.0


def test_a_log_without_the_expected_columns_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing the columns"):
        read_ocpp_limit_steps(_write_log(tmp_path, "when,what\n2026-08-04,90000\n"))


def test_a_log_without_calls_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SetChargingProfile calls"):
        read_ocpp_limit_steps(
            _write_log(
                tmp_path,
                _HEADER + "NLTEST0001,4/8/2026 12:00:01 PM +02:00,True,CS,CallResult,"
                "SetChargingProfile,,,,,\n",
            )
        )

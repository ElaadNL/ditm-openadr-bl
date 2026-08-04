"""Tests for the comparison of a reference profile against an observed one."""

from datetime import UTC, datetime, timedelta

from src.application.capacity_profile import CapacitySignal
from src.application.profile_diff import compare_profiles

FIRST = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
SECOND = datetime(2026, 8, 5, 4, 15, tzinfo=UTC)


def _signal(start: datetime, value_kw: float, minutes: int = 15) -> CapacitySignal:
    return CapacitySignal(
        start=start, duration=timedelta(minutes=minutes), value_kw=value_kw
    )


def test_identical_profiles_match() -> None:
    reference = [_signal(FIRST, 100.0), _signal(SECOND, 20.0)]

    diff = compare_profiles(reference, list(reference))

    assert diff.matches
    assert diff.problem_count == 0


def test_a_missing_interval_is_reported() -> None:
    diff = compare_profiles(
        [_signal(FIRST, 100.0), _signal(SECOND, 20.0)], [_signal(FIRST, 100.0)]
    )

    assert not diff.matches
    assert diff.missing == [SECOND]
    assert not diff.unexpected


def test_an_unexpected_interval_is_reported() -> None:
    diff = compare_profiles(
        [_signal(FIRST, 100.0)], [_signal(FIRST, 100.0), _signal(SECOND, 20.0)]
    )

    assert diff.unexpected == [SECOND]


def test_a_differing_value_is_reported() -> None:
    diff = compare_profiles([_signal(FIRST, 100.0)], [_signal(FIRST, 90.0)])

    assert [mismatch.reason for mismatch in diff.mismatches] == ["value"]
    assert "expected 100 kW, got 90 kW" in str(diff.mismatches[0])


def test_a_value_within_the_tolerance_matches() -> None:
    diff = compare_profiles([_signal(FIRST, 100.0)], [_signal(FIRST, 99.5)], 0.5)

    assert diff.matches


def test_a_differing_duration_is_reported() -> None:
    diff = compare_profiles(
        [_signal(FIRST, 100.0)], [_signal(FIRST, 100.0, minutes=30)]
    )

    assert [mismatch.reason for mismatch in diff.mismatches] == ["duration"]


def test_a_duplicated_interval_is_reported() -> None:
    diff = compare_profiles(
        [_signal(FIRST, 100.0)], [_signal(FIRST, 100.0), _signal(FIRST, 20.0)]
    )

    assert [mismatch.reason for mismatch in diff.mismatches] == ["duplicate interval"]


def test_timestamps_are_compared_as_moments_not_as_text() -> None:
    from zoneinfo import ZoneInfo

    amsterdam = datetime(2026, 8, 5, 6, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))

    diff = compare_profiles([_signal(FIRST, 100.0)], [_signal(amsterdam, 100.0)])

    assert diff.matches

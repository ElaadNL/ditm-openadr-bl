"""Tests for the synthetic congestion profile generator."""

from datetime import date, datetime, time, timedelta

import pytest

from src.application.capacity_profile import (
    AMSTERDAM,
    INTERVAL_DURATION,
    CapacitySignal,
    generate_capacity_profile,
    is_quiet_day,
    profile_bounds,
    rebase_profile,
)

MIN_KW = 20.0
MAX_KW = 100.0

# A regular working day, a Wednesday.
WORKING_DAY = date(2026, 8, 5)
# A Saturday.
WEEKEND_DAY = date(2026, 8, 8)
# Koningsdag, a Monday in 2026.
HOLIDAY = date(2026, 4, 27)
# The days the Dutch clock goes forward and back in 2026.
SPRING_FORWARD_DAY = date(2026, 3, 29)
FALL_BACK_DAY = date(2026, 10, 25)


def _local(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=AMSTERDAM)


def _generate_day(
    day: date, min_kw: float = MIN_KW, max_kw: float = MAX_KW
) -> list[CapacitySignal]:
    return generate_capacity_profile(
        _local(day), _local(day + timedelta(days=1)), min_kw, max_kw
    )


def _values_between(
    signals: list[CapacitySignal], from_hour: int, to_hour: int
) -> list[float]:
    return [
        signal.value_kw
        for signal in signals
        if from_hour <= signal.local_start.hour < to_hour
    ]


def test_a_regular_day_holds_96_intervals() -> None:
    assert len(_generate_day(WORKING_DAY)) == 96


def test_the_day_the_clock_goes_back_holds_100_intervals() -> None:
    assert len(_generate_day(FALL_BACK_DAY)) == 100


def test_the_day_the_clock_goes_forward_holds_92_intervals() -> None:
    assert len(_generate_day(SPRING_FORWARD_DAY)) == 92


@pytest.mark.parametrize(
    "day", [WORKING_DAY, WEEKEND_DAY, SPRING_FORWARD_DAY, FALL_BACK_DAY]
)
def test_intervals_are_contiguous_and_quarter_hourly(day: date) -> None:
    signals = _generate_day(day)

    assert all(signal.duration == INTERVAL_DURATION for signal in signals)
    assert all(
        earlier.end == later.start
        for earlier, later in zip(signals[:-1], signals[1:], strict=True)
    )


def test_the_profile_covers_exactly_the_requested_period() -> None:
    signals = _generate_day(WORKING_DAY)

    start, end = profile_bounds(signals)

    assert start == _local(WORKING_DAY)
    assert end == _local(WORKING_DAY + timedelta(days=1))


def test_values_stay_within_the_band() -> None:
    signals = _generate_day(WORKING_DAY)

    assert all(MIN_KW <= signal.value_kw <= MAX_KW for signal in signals)


def test_the_working_day_evening_peak_sits_at_the_floor() -> None:
    signals = _generate_day(WORKING_DAY)

    assert _values_between(signals, 16, 20) == [MIN_KW] * 16


def test_the_working_day_morning_peak_is_restricted_but_not_at_the_floor() -> None:
    signals = _generate_day(WORKING_DAY)

    morning = _values_between(signals, 7, 9)

    assert len(morning) == 8
    assert all(MIN_KW < value < MAX_KW for value in morning)


def test_the_night_is_unrestricted() -> None:
    signals = _generate_day(WORKING_DAY)

    assert _values_between(signals, 0, 6) == [MAX_KW] * 24


def test_a_weekend_day_has_no_morning_restriction() -> None:
    signals = _generate_day(WEEKEND_DAY)

    assert _values_between(signals, 7, 9) == [MAX_KW] * 8


def test_a_weekend_evening_is_restricted_but_not_at_the_floor() -> None:
    signals = _generate_day(WEEKEND_DAY)

    evening = _values_between(signals, 17, 20)

    assert all(MIN_KW < value < MAX_KW for value in evening)


def test_a_national_holiday_is_treated_as_a_quiet_day() -> None:
    assert is_quiet_day(HOLIDAY)
    assert _values_between(_generate_day(HOLIDAY), 7, 9) == [MAX_KW] * 8


def test_the_evening_peak_is_preceded_by_a_ramp() -> None:
    signals = _generate_day(WORKING_DAY)

    ramp = [
        signal.value_kw
        for signal in signals
        if _local(WORKING_DAY, 15, 30) <= signal.start < _local(WORKING_DAY, 16)
    ]

    assert len(ramp) == 2
    assert MIN_KW < ramp[1] < ramp[0] < MAX_KW


def test_generating_a_subrange_reproduces_the_same_values() -> None:
    whole_day = _generate_day(WORKING_DAY)
    subrange = generate_capacity_profile(
        _local(WORKING_DAY, 9), _local(WORKING_DAY, 12), MIN_KW, MAX_KW
    )

    overlapping = [
        signal
        for signal in whole_day
        if _local(WORKING_DAY, 9) <= signal.start < _local(WORKING_DAY, 12)
    ]

    assert subrange == overlapping


def test_the_shape_scales_with_the_band() -> None:
    narrow = _generate_day(WORKING_DAY, min_kw=50.0, max_kw=60.0)

    assert all(50.0 <= signal.value_kw <= 60.0 for signal in narrow)
    assert min(signal.value_kw for signal in narrow) == 50.0
    assert max(signal.value_kw for signal in narrow) == 60.0


@pytest.mark.parametrize(
    ("start", "end", "min_kw", "max_kw"),
    [
        (_local(WORKING_DAY), _local(WORKING_DAY), MIN_KW, MAX_KW),
        (_local(WORKING_DAY, 12), _local(WORKING_DAY, 6), MIN_KW, MAX_KW),
        (_local(WORKING_DAY), _local(WORKING_DAY, 6), 100.0, 100.0),
        (_local(WORKING_DAY), _local(WORKING_DAY, 6), -1.0, 100.0),
    ],
)
def test_invalid_input_is_rejected(
    start: datetime, end: datetime, min_kw: float, max_kw: float
) -> None:
    with pytest.raises(ValueError):
        generate_capacity_profile(start, end, min_kw, max_kw)


def test_a_naive_period_is_rejected() -> None:
    with pytest.raises(ValueError):
        generate_capacity_profile(
            datetime(2026, 8, 5),  # noqa: DTZ001
            datetime(2026, 8, 6),  # noqa: DTZ001
            MIN_KW,
            MAX_KW,
        )


def test_rebasing_preserves_the_values_and_the_structure() -> None:
    signals = _generate_day(WORKING_DAY)

    rebased = rebase_profile(signals, date(2026, 8, 19))

    assert [signal.value_kw for signal in rebased] == [
        signal.value_kw for signal in signals
    ]
    assert rebased[0].local_start.date() == date(2026, 8, 19)
    assert rebased[0].local_start.time() == time(0, 0)
    assert all(
        earlier.end == later.start
        for earlier, later in zip(rebased[:-1], rebased[1:], strict=True)
    )


def test_rebasing_can_align_on_the_weekday() -> None:
    signals = _generate_day(WORKING_DAY)

    rebased = rebase_profile(signals, date(2026, 8, 20), align_weekday=True)

    assert rebased[0].local_start.date() == date(2026, 8, 19)
    assert rebased[0].local_start.weekday() == WORKING_DAY.weekday()


def test_rebasing_onto_a_shorter_day_keeps_the_profile_contiguous() -> None:
    signals = _generate_day(FALL_BACK_DAY)

    rebased = rebase_profile(signals, SPRING_FORWARD_DAY)

    assert len(rebased) == len(signals)
    assert all(
        earlier.end == later.start
        for earlier, later in zip(rebased[:-1], rebased[1:], strict=True)
    )


def test_rebasing_an_empty_profile_is_rejected() -> None:
    with pytest.raises(ValueError):
        rebase_profile([], date(2026, 8, 19))


def test_a_signal_needs_an_unambiguous_start() -> None:
    with pytest.raises(ValueError):
        CapacitySignal(
            start=datetime(2026, 8, 5),  # noqa: DTZ001
            duration=INTERVAL_DURATION,
            value_kw=50.0,
        )

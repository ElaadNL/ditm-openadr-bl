"""Deterministic synthetic capacity limitation profiles.

Generates 15 minute capacity availability signals that mimic the grid congestion
pattern currently seen in the Netherlands: ample capacity at night and around
solar noon, a moderate restriction during the morning peak and a deep
restriction during the evening peak of a working day. Weekends and Dutch
national holidays only get the evening restriction, and a milder one.

The profile is fully deterministic. The value of an interval depends on nothing
but its timestamp and the min/max bounds, never on the order in which intervals
are generated or on the length of the period being generated. Regenerating a
subrange of a profile therefore reproduces exactly the same values, which is
what makes a stored profile usable as a reference for validation.

All congestion windows are anchored to Europe/Amsterdam wall clock time, because
that is what the peaks follow, while the interval timestamps themselves are
absolute. On the day the clock goes back, a local day therefore contains 100
intervals instead of 96, and 92 on the day it goes forward.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import blake2b
from zoneinfo import ZoneInfo

import holidays

from src.logger import logger

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
"""The timezone the congestion windows are anchored to."""

INTERVAL_DURATION = timedelta(minutes=15)
"""The resolution of the generated profile."""

# The three capacity levels, expressed as a fraction of the band between the
# minimum and the maximum available capacity. Keeping them relative means the
# same shape is produced regardless of the bounds that are passed in.
_FULL = 1.0
_MILD = 0.6
_DEEP = 0.0

# Number of intervals used to ramp from one level to the next. The ramp is
# placed at the end of the preceding level, so a window still starts exactly at
# the time listed below.
_RAMP_STEPS = 2

# Level changes of a working day, in local time. Each entry holds until the next.
_WORKING_DAY_PLATEAUS: tuple[tuple[time, float], ...] = (
    (time(0, 0), _FULL),  # night, no congestion
    (time(7, 0), _MILD),  # morning peak
    (time(9, 30), _FULL),  # daytime, solar production
    (time(16, 0), _DEEP),  # evening peak, the binding constraint
    (time(20, 30), _MILD),  # evening shoulder
    (time(21, 30), _FULL),  # night, no congestion
)

# Level changes of a weekend day or a national holiday. No morning peak, and the
# evening restriction stays mild.
_QUIET_DAY_PLATEAUS: tuple[tuple[time, float], ...] = (
    (time(0, 0), _FULL),
    (time(17, 0), _MILD),
    (time(20, 30), _FULL),
)

# Amplitude of the jitter, as a fraction of the band. Applied to intermediate
# levels only, so that the ceiling and the floor of a profile stay exact.
_NOISE_AMPLITUDE = 0.02

_NL_HOLIDAYS = holidays.country_holidays(country="NL")


@dataclass(frozen=True)
class CapacitySignal:
    """The available import capacity during a single interval.

    Attributes:
        start (datetime): Start of the interval, timezone aware.
        duration (timedelta): Duration of the interval.
        value_kw (float): The available import capacity during the interval, in kW.
    """

    start: datetime
    duration: timedelta
    value_kw: float

    def __post_init__(self) -> None:
        """Validate that the signal is unambiguous in time.

        Raises:
            ValueError: If the start is naive or the duration is not positive.
        """
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            err_msg = "capacity signal start must be timezone aware."
            raise ValueError(err_msg)
        if self.duration <= timedelta():
            err_msg = "capacity signal duration must be positive."
            raise ValueError(err_msg)

    @property
    def end(self) -> datetime:
        """The (exclusive) end of the interval."""
        return self.start + self.duration

    @property
    def local_start(self) -> datetime:
        """The start of the interval in Europe/Amsterdam local time."""
        return self.start.astimezone(AMSTERDAM)


def is_quiet_day(day: date) -> bool:
    """Whether a day is a weekend day or a Dutch national holiday.

    Args:
        day (date): The local date to classify.

    Returns:
        bool: True if the day carries the quiet day profile.
    """
    weekend_cutoff = 5
    return day.weekday() >= weekend_cutoff or day in _NL_HOLIDAYS


def generate_capacity_profile(
    start: datetime, end: datetime, min_kw: float, max_kw: float
) -> list[CapacitySignal]:
    """Generate a synthetic congestion profile between two moments in time.

    Args:
        start (datetime): Start of the profile (inclusive), timezone aware.
        end (datetime): End of the profile (exclusive), timezone aware.
        min_kw (float): Capacity available during the deepest restriction, in kW.
        max_kw (float): Capacity available when the grid is unconstrained, in kW.

    Returns:
        list[CapacitySignal]: The contiguous 15 minute signals covering the period.

    Raises:
        ValueError: If the period or the bounds are invalid.
    """
    if start.tzinfo is None or end.tzinfo is None:
        err_msg = "start and end must be timezone aware."
        raise ValueError(err_msg)
    if end <= start:
        err_msg = f"end ({end}) must be after start ({start})."
        raise ValueError(err_msg)
    if min_kw < 0:
        err_msg = f"min_kw ({min_kw}) must not be negative."
        raise ValueError(err_msg)
    if max_kw <= min_kw:
        err_msg = f"max_kw ({max_kw}) must be greater than min_kw ({min_kw})."
        raise ValueError(err_msg)

    # Stepping through the period in UTC keeps the arithmetic absolute, so a
    # daylight saving transition yields more or fewer intervals rather than a
    # gap or an overlap in the timeline.
    starts: list[datetime] = []
    current = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    while current < end_utc:
        starts.append(current)
        current += INTERVAL_DURATION

    fractions = _apply_ramps([_plateau_fraction(moment) for moment in starts])

    return [
        CapacitySignal(
            start=moment,
            duration=INTERVAL_DURATION,
            value_kw=_value_of(moment, fraction, min_kw, max_kw),
        )
        for moment, fraction in zip(starts, fractions, strict=True)
    ]


def rebase_profile(
    signals: list[CapacitySignal], new_start_date: date, *, align_weekday: bool = False
) -> list[CapacitySignal]:
    """Move a profile to a new start date, preserving its values and structure.

    The local time of day of the first interval is preserved and every following
    interval keeps its exact offset relative to the first one, so the rebased
    profile is contiguous and free of overlaps by construction.

    Args:
        signals (list[CapacitySignal]): The profile to move. Must not be empty.
        new_start_date (date): The local date the profile should start on.
        align_weekday (bool): Round the shift to whole weeks, so a working day
            profile keeps landing on a working day. Defaults to False.

    Returns:
        list[CapacitySignal]: The rebased profile.

    Raises:
        ValueError: If the profile is empty.
    """
    if not signals:
        err_msg = "cannot rebase an empty profile."
        raise ValueError(err_msg)

    origin = signals[0].start
    origin_local = origin.astimezone(AMSTERDAM)
    shift_days = (new_start_date - origin_local.date()).days

    if align_weekday:
        days_per_week = 7
        aligned = round(shift_days / days_per_week) * days_per_week
        if aligned != shift_days:
            logger.info(
                "Aligning the shift of %d days to %d days to keep the weekday.",
                shift_days,
                aligned,
            )
        shift_days = aligned

    target_date = origin_local.date() + timedelta(days=shift_days)
    if target_date != new_start_date:
        logger.info(
            "Profile is rebased onto %s instead of %s.", target_date, new_start_date
        )
    if target_date.weekday() != origin_local.date().weekday():
        logger.warning(
            "Rebasing from a %s onto a %s, the working day and weekend windows "
            "of the profile no longer line up with the calendar.",
            origin_local.strftime("%A"),
            target_date.strftime("%A"),
        )

    new_origin_local = datetime.combine(
        target_date, origin_local.time(), tzinfo=AMSTERDAM
    )
    new_origin = new_origin_local.astimezone(UTC)

    rebased = [
        CapacitySignal(
            start=new_origin + (signal.start - origin),
            duration=signal.duration,
            value_kw=signal.value_kw,
        )
        for signal in signals
    ]

    _warn_on_dst_drift(signals, rebased)

    return rebased


def profile_bounds(signals: list[CapacitySignal]) -> tuple[datetime, datetime]:
    """Return the start of the first interval and the end of the last one.

    Args:
        signals (list[CapacitySignal]): The profile.

    Returns:
        tuple[datetime, datetime]: The start (inclusive) and end (exclusive).

    Raises:
        ValueError: If the profile is empty.
    """
    if not signals:
        err_msg = "an empty profile has no bounds."
        raise ValueError(err_msg)
    return signals[0].start, signals[-1].end


def _plateau_fraction(moment: datetime) -> float:
    """Return the level of the plateau the given moment falls in.

    Args:
        moment (datetime): The start of the interval, timezone aware.

    Returns:
        float: The fraction of the capacity band for this interval.
    """
    local = moment.astimezone(AMSTERDAM)
    plateaus = (
        _QUIET_DAY_PLATEAUS if is_quiet_day(local.date()) else _WORKING_DAY_PLATEAUS
    )

    fraction = plateaus[0][1]
    for plateau_start, plateau_fraction in plateaus:
        if local.time() < plateau_start:
            break
        fraction = plateau_fraction
    return fraction


def _apply_ramps(fractions: list[float]) -> list[float]:
    """Soften every level change by ramping towards it over the preceding intervals.

    The ramp consumes the tail of the preceding level, so the new level still
    starts exactly at the time it is scheduled for.

    Args:
        fractions (list[float]): The plateau level of each interval.

    Returns:
        list[float]: The levels with ramps applied.
    """
    ramped = list(fractions)
    for index in range(1, len(fractions)):
        previous = fractions[index - 1]
        current = fractions[index]
        if previous == current:
            continue
        for step in range(1, _RAMP_STEPS + 1):
            ramp_index = index - (_RAMP_STEPS + 1 - step)
            if ramp_index < 0:
                continue
            ramped[ramp_index] = previous + (current - previous) * (
                step / (_RAMP_STEPS + 1)
            )
    return ramped


def _value_of(moment: datetime, fraction: float, min_kw: float, max_kw: float) -> float:
    """Turn a level into a capacity value in kW.

    Jitter is applied to intermediate levels only. The unconstrained level is
    therefore always exactly max_kw and the deepest restriction exactly min_kw,
    which keeps a generated profile easy to assert against.

    Args:
        moment (datetime): The start of the interval, used to derive the jitter.
        fraction (float): The level of the interval.
        min_kw (float): The lower bound of the capacity band.
        max_kw (float): The upper bound of the capacity band.

    Returns:
        float: The available capacity in kW, rounded to whole kW.
    """
    band = max_kw - min_kw
    value = min_kw + fraction * band
    if _DEEP < fraction < _FULL:
        value += _jitter(moment) * band
    return float(round(min(max(value, min_kw), max_kw)))


def _jitter(moment: datetime) -> float:
    """Derive a reproducible jitter in [-amplitude, amplitude] from a timestamp.

    A hash of the timestamp is used rather than a random number generator, so
    that the value of an interval never depends on which other intervals were
    generated alongside it.

    Args:
        moment (datetime): The start of the interval.

    Returns:
        float: The jitter as a fraction of the capacity band.
    """
    digest = blake2b(
        moment.astimezone(UTC).isoformat().encode(), digest_size=8
    ).digest()
    unit_interval = int.from_bytes(digest, "big") / float(2**64 - 1)
    return (unit_interval * 2 - 1) * _NOISE_AMPLITUDE


def _warn_on_dst_drift(
    original: list[CapacitySignal], rebased: list[CapacitySignal]
) -> None:
    """Warn when rebasing moved the profile across a different set of DST transitions.

    Args:
        original (list[CapacitySignal]): The profile before rebasing.
        rebased (list[CapacitySignal]): The profile after rebasing.
    """
    original_drift = (
        original[-1].local_start.utcoffset() != original[0].local_start.utcoffset()
    )
    rebased_drift = (
        rebased[-1].local_start.utcoffset() != rebased[0].local_start.utcoffset()
    )

    if original_drift != rebased_drift:
        logger.warning(
            "The rebased period does not contain the same daylight saving "
            "transitions as the original, the congestion windows after the "
            "transition shift by an hour in local time."
        )

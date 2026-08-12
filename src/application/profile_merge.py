"""Merging a published profile with the limits the charger actually received.

Where `profile_diff` answers whether two profiles are equal, this module lays
them side by side interval by interval, so the result can be reported back to
the party hosting the VEN: what was published, what their system applied, and
how quickly it followed a change.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.capacity_profile import AMSTERDAM, CapacitySignal
from src.infrastructure.vendor_feedback import (
    AppliedLimit,
    OcppLimitLog,
    dominant_limit_between,
)

MATCH = "match"
DEVIATES = "deviates"
NOT_COVERED = "not covered"


@dataclass(frozen=True)
class MergedInterval:
    """One interval of the published profile next to what the charger received.

    Attributes:
        start (datetime): Start of the interval.
        duration (timedelta): Duration of the interval.
        published_kw (float): The capacity limit this repository published.
        received (AppliedLimit | None): The limit in force at the start of the
            interval, or None when the message log does not cover it.
        tolerance_kw (float): Absolute tolerance the comparison allows.
    """

    start: datetime
    duration: timedelta
    published_kw: float
    received: AppliedLimit | None
    tolerance_kw: float = 0.0

    @property
    def local_start(self) -> datetime:
        """The start of the interval in Europe/Amsterdam local time."""
        return self.start.astimezone(AMSTERDAM)

    @property
    def received_kw(self) -> float | None:
        """The limit the operator was signalled, before its own buffer."""
        return self.received.signalled_kw if self.received else None

    @property
    def applied_kw(self) -> float | None:
        """The limit the operator forwarded to the charger."""
        return self.received.applied_kw if self.received else None

    @property
    def delta_kw(self) -> float | None:
        """The difference between the received and the published limit."""
        if self.received is None:
            return None
        return round(self.received.signalled_kw - self.published_kw, 3)

    @property
    def status(self) -> str:
        """Whether this interval matches, deviates, or is not covered."""
        delta = self.delta_kw
        if delta is None:
            return NOT_COVERED
        return MATCH if abs(delta) <= self.tolerance_kw else DEVIATES


@dataclass(frozen=True)
class Transition:
    """A change in the published profile, and how the operator followed it.

    Attributes:
        at (datetime): The interval boundary the published limit changes on.
        from_kw (float): The limit before the change.
        to_kw (float): The limit after the change.
        applied_at (datetime | None): When the operator put the new limit in
            force, or None when it never did.
    """

    at: datetime
    from_kw: float
    to_kw: float
    applied_at: datetime | None

    @property
    def latency(self) -> timedelta | None:
        """How long after the boundary the new limit took effect."""
        if self.applied_at is None:
            return None
        return self.applied_at - self.at


@dataclass(frozen=True)
class MergeSummary:
    """The headline numbers of a merge.

    Attributes:
        compared (int): Intervals the message log covers.
        matching (int): Covered intervals whose limits agree.
        deviating (int): Covered intervals whose limits differ.
        not_covered (int): Intervals of the profile outside the log.
        max_abs_delta_kw (float): Largest absolute difference found.
        transitions (int): Changes in the published profile within the window.
        followed_transitions (int): Changes the operator put in force.
        worst_latency (timedelta | None): Slowest change the operator followed.
    """

    compared: int
    matching: int
    deviating: int
    not_covered: int
    max_abs_delta_kw: float
    transitions: int
    followed_transitions: int
    worst_latency: timedelta | None

    @property
    def matches(self) -> bool:
        """Whether every covered interval agrees."""
        return self.compared > 0 and self.deviating == 0


def merge_profile_with_log(
    signals: list[CapacitySignal], log: OcppLimitLog, tolerance_kw: float = 0.0
) -> list[MergedInterval]:
    """Lay a published profile next to the limits an OCPP message log reports.

    Only the part of the profile the log actually covers is compared. Nothing is
    known about the limits before the first and after the last message, so those
    intervals are marked as not covered rather than as a deviation. An interval
    is compared against the limit that was in force for most of it, so the
    seconds an operator needs to push a change do not read as a deviation.

    Args:
        signals (list[CapacitySignal]): The published profile.
        log (OcppLimitLog): The limits read from the operator's message log.
        tolerance_kw (float): Absolute tolerance on the capacity values.

    Returns:
        list[MergedInterval]: One entry per interval of the profile, ordered by
            start.
    """
    merged: list[MergedInterval] = []
    for signal in signals:
        covered = log.first_message_at <= signal.start <= log.last_message_at
        merged.append(
            MergedInterval(
                start=signal.start,
                duration=signal.duration,
                published_kw=signal.value_kw,
                received=dominant_limit_between(
                    log.steps, signal.start, signal.start + signal.duration
                )
                if covered
                else None,
                tolerance_kw=tolerance_kw,
            )
        )
    return merged


def find_transitions(
    merged: list[MergedInterval], log: OcppLimitLog
) -> list[Transition]:
    """Find the changes in the covered part of the profile and when they landed.

    Args:
        merged (list[MergedInterval]): The merged intervals, ordered by start.
        log (OcppLimitLog): The limits read from the operator's message log.

    Returns:
        list[Transition]: One entry per change of the published limit within the
            covered window.
    """
    transitions: list[Transition] = []
    for previous, current in zip(merged[:-1], merged[1:], strict=True):
        if current.published_kw == previous.published_kw:
            continue
        if current.status == NOT_COVERED:
            continue
        transitions.append(
            Transition(
                at=current.start,
                from_kw=previous.published_kw,
                to_kw=current.published_kw,
                applied_at=_first_step_at(
                    log.steps, current.published_kw, previous.start
                ),
            )
        )
    return transitions


def summarize_merge(
    merged: list[MergedInterval], transitions: list[Transition]
) -> MergeSummary:
    """Reduce a merge to the numbers worth reporting.

    Args:
        merged (list[MergedInterval]): The merged intervals.
        transitions (list[Transition]): The transitions found in the window.

    Returns:
        MergeSummary: The headline numbers.
    """
    covered = [interval for interval in merged if interval.status != NOT_COVERED]
    deltas = [abs(interval.delta_kw or 0.0) for interval in covered]
    latencies = [
        transition.latency
        for transition in transitions
        if transition.latency is not None
    ]

    return MergeSummary(
        compared=len(covered),
        matching=sum(1 for interval in covered if interval.status == MATCH),
        deviating=sum(1 for interval in covered if interval.status == DEVIATES),
        not_covered=len(merged) - len(covered),
        max_abs_delta_kw=max(deltas, default=0.0),
        transitions=len(transitions),
        followed_transitions=len(latencies),
        worst_latency=max(latencies, default=None),
    )


def covered_window(
    merged: list[MergedInterval],
) -> tuple[datetime, datetime] | None:
    """Return the period the message log covers.

    Args:
        merged (list[MergedInterval]): The merged intervals.

    Returns:
        tuple[datetime, datetime] | None: The start of the first and the end of
            the last covered interval, or None when nothing is covered.
    """
    covered = [interval for interval in merged if interval.status != NOT_COVERED]
    if not covered:
        return None
    return covered[0].start, covered[-1].start + covered[-1].duration


def _first_step_at(
    steps: list[AppliedLimit], limit_kw: float, not_before: datetime
) -> datetime | None:
    """Find when a limit was first put in force at or after a moment.

    Args:
        steps (list[AppliedLimit]): The limits, ordered by effective moment.
        limit_kw (float): The limit to look for.
        not_before (datetime): Ignore anything that took effect earlier.

    Returns:
        datetime | None: The moment the limit took effect, or None when the log
            never reports it.
    """
    for step in steps:
        if step.at >= not_before and step.signalled_kw == limit_kw:
            return step.at
    return None

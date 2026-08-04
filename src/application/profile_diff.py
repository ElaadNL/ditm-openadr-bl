"""Comparison of a generated capacity profile against a profile observed elsewhere.

Used to check that what was generated is what the VTN stored, and that it is
also what the vendor hosting the VEN says it received.
"""

from dataclasses import dataclass, field
from datetime import datetime

from src.application.capacity_profile import CapacitySignal
from src.infrastructure.csv_profile import format_utc


@dataclass(frozen=True)
class SignalMismatch:
    """A single interval that does not match.

    Attributes:
        start (datetime): The start of the interval.
        reason (str): What differs, for example value or duration.
        expected (str): The expected value, rendered for reporting.
        actual (str): The observed value, rendered for reporting.
    """

    start: datetime
    reason: str
    expected: str
    actual: str

    def __str__(self) -> str:
        """Render the mismatch as a single reportable line."""
        return (
            f"{format_utc(self.start)}  {self.reason}: "
            f"expected {self.expected}, got {self.actual}"
        )


@dataclass(frozen=True)
class ProfileDiff:
    """The outcome of comparing two profiles.

    Attributes:
        expected_count (int): Number of intervals in the reference profile.
        actual_count (int): Number of intervals observed.
        missing (list[datetime]): Intervals present in the reference but not observed.
        unexpected (list[datetime]): Intervals observed but not in the reference.
        mismatches (list[SignalMismatch]): Intervals present on both sides that differ.
    """

    expected_count: int
    actual_count: int
    missing: list[datetime] = field(default_factory=list)
    unexpected: list[datetime] = field(default_factory=list)
    mismatches: list[SignalMismatch] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        """Whether the two profiles are equivalent."""
        return not self.missing and not self.unexpected and not self.mismatches

    @property
    def problem_count(self) -> int:
        """The total number of differences found."""
        return len(self.missing) + len(self.unexpected) + len(self.mismatches)


def compare_profiles(
    expected: list[CapacitySignal],
    actual: list[CapacitySignal],
    tolerance_kw: float = 0.0,
) -> ProfileDiff:
    """Compare an observed profile against a reference profile.

    Intervals are matched on their start, which is compared as an absolute
    moment, so a difference in how the timestamps were formatted or in which
    timezone they were expressed does not register as a difference.

    Args:
        expected (list[CapacitySignal]): The reference profile.
        actual (list[CapacitySignal]): The observed profile.
        tolerance_kw (float): Absolute tolerance on the capacity value, in kW.
            Defaults to 0.0, an exact comparison.

    Returns:
        ProfileDiff: The differences between the two profiles.
    """
    expected_by_start = {signal.start: signal for signal in expected}
    actual_by_start: dict[datetime, CapacitySignal] = {}
    mismatches: list[SignalMismatch] = []

    for signal in actual:
        duplicate = actual_by_start.get(signal.start)
        if duplicate is not None:
            mismatches.append(
                SignalMismatch(
                    start=signal.start,
                    reason="duplicate interval",
                    expected=f"{duplicate.value_kw:g} kW",
                    actual=f"{signal.value_kw:g} kW",
                )
            )
            continue
        actual_by_start[signal.start] = signal

    for start, expected_signal in sorted(expected_by_start.items()):
        actual_signal = actual_by_start.get(start)
        if actual_signal is None:
            continue
        if abs(actual_signal.value_kw - expected_signal.value_kw) > tolerance_kw:
            mismatches.append(
                SignalMismatch(
                    start=start,
                    reason="value",
                    expected=f"{expected_signal.value_kw:g} kW",
                    actual=f"{actual_signal.value_kw:g} kW",
                )
            )
        if actual_signal.duration != expected_signal.duration:
            mismatches.append(
                SignalMismatch(
                    start=start,
                    reason="duration",
                    expected=str(expected_signal.duration),
                    actual=str(actual_signal.duration),
                )
            )

    return ProfileDiff(
        expected_count=len(expected),
        actual_count=len(actual),
        missing=sorted(set(expected_by_start) - set(actual_by_start)),
        unexpected=sorted(set(actual_by_start) - set(expected_by_start)),
        mismatches=sorted(mismatches, key=lambda mismatch: mismatch.start),
    )

"""Tests for merging a published profile with an operator message log."""

from datetime import UTC, datetime, timedelta

from src.application.capacity_profile import CapacitySignal
from src.application.profile_merge import (
    DEVIATES,
    MATCH,
    NOT_COVERED,
    covered_window,
    find_transitions,
    merge_profile_with_log,
    summarize_merge,
)
from src.infrastructure.vendor_feedback import AppliedLimit, OcppLimitLog

QUARTER = timedelta(minutes=15)
NOON = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)


def _profile(*values: float, start: datetime = NOON) -> list[CapacitySignal]:
    return [
        CapacitySignal(start=start + index * QUARTER, duration=QUARTER, value_kw=value)
        for index, value in enumerate(values)
    ]


def _log(*steps: tuple[datetime, float], last_message_at: datetime | None = None):
    applied = [
        AppliedLimit(at=at, signalled_kw=kilowatt, applied_kw=kilowatt * 0.9)
        for at, kilowatt in steps
    ]
    return OcppLimitLog(
        charge_point_ids=("NLTEST0001",),
        message_count=len(applied),
        first_message_at=applied[0].at,
        last_message_at=last_message_at or applied[-1].at,
        buffer_fraction=0.1,
        steps=applied,
    )


def test_an_interval_that_ran_on_the_published_limit_matches() -> None:
    merged = merge_profile_with_log(_profile(100.0), _log((NOON, 100.0)))

    assert merged[0].status == MATCH
    assert merged[0].received_kw == 100.0
    assert merged[0].applied_kw == 90.0
    assert merged[0].delta_kw == 0.0


def test_a_late_change_is_not_reported_as_a_deviation() -> None:
    # The operator pushes 20 kW 90 seconds into the interval, so the interval
    # ran on 20 kW even though the boundary itself still held 100 kW.
    merged = merge_profile_with_log(
        _profile(100.0, 20.0),
        _log(
            (NOON, 100.0),
            (NOON + QUARTER + timedelta(seconds=90), 20.0),
            last_message_at=NOON + 2 * QUARTER,
        ),
    )

    assert [interval.status for interval in merged] == [MATCH, MATCH]


def test_a_limit_the_operator_never_applied_deviates() -> None:
    merged = merge_profile_with_log(
        _profile(100.0, 20.0),
        _log((NOON, 100.0), last_message_at=NOON + 2 * QUARTER),
    )

    assert [interval.status for interval in merged] == [MATCH, DEVIATES]
    assert merged[1].delta_kw == 80.0


def test_intervals_outside_the_log_are_not_counted_as_deviations() -> None:
    merged = merge_profile_with_log(
        _profile(100.0, 100.0, 100.0, start=NOON - QUARTER),
        _log((NOON, 100.0), last_message_at=NOON + QUARTER),
    )

    assert [interval.status for interval in merged] == [NOT_COVERED, MATCH, MATCH]
    assert merged[0].received_kw is None
    assert merged[0].delta_kw is None


def test_a_tolerance_absorbs_a_small_difference() -> None:
    merged = merge_profile_with_log(
        _profile(100.0), _log((NOON, 99.5)), tolerance_kw=0.5
    )

    assert merged[0].status == MATCH


def test_the_covered_window_spans_the_compared_intervals() -> None:
    merged = merge_profile_with_log(
        _profile(100.0, 100.0, 100.0, start=NOON - QUARTER),
        _log((NOON, 100.0), last_message_at=NOON + QUARTER),
    )

    assert covered_window(merged) == (NOON, NOON + 2 * QUARTER)


def test_a_change_is_matched_to_the_moment_it_took_effect() -> None:
    applied_at = NOON + QUARTER + timedelta(seconds=18)
    log = _log((NOON, 100.0), (applied_at, 20.0), last_message_at=NOON + 2 * QUARTER)
    merged = merge_profile_with_log(_profile(100.0, 20.0), log)

    transitions = find_transitions(merged, log)

    assert len(transitions) == 1
    assert transitions[0].from_kw == 100.0
    assert transitions[0].to_kw == 20.0
    assert transitions[0].applied_at == applied_at
    assert transitions[0].latency == timedelta(seconds=18)


def test_a_change_the_operator_ignored_has_no_latency() -> None:
    log = _log((NOON, 100.0), last_message_at=NOON + 2 * QUARTER)
    merged = merge_profile_with_log(_profile(100.0, 20.0), log)

    transitions = find_transitions(merged, log)

    assert transitions[0].applied_at is None
    assert transitions[0].latency is None


def test_the_summary_counts_what_was_compared() -> None:
    log = _log(
        (NOON, 100.0),
        (NOON + QUARTER + timedelta(seconds=30), 20.0),
        last_message_at=NOON + 3 * QUARTER,
    )
    merged = merge_profile_with_log(
        _profile(100.0, 100.0, 20.0, 20.0, start=NOON - QUARTER), log
    )
    summary = summarize_merge(merged, find_transitions(merged, log))

    assert summary.compared == 3
    assert summary.matching == 3
    assert summary.deviating == 0
    assert summary.not_covered == 1
    assert summary.max_abs_delta_kw == 0.0
    assert summary.transitions == 1
    assert summary.followed_transitions == 1
    assert summary.worst_latency == timedelta(seconds=30)
    assert summary.matches


def test_a_merge_without_coverage_does_not_claim_a_match() -> None:
    merged = merge_profile_with_log(
        _profile(100.0, start=NOON - 4 * QUARTER),
        _log((NOON, 100.0), last_message_at=NOON + QUARTER),
    )
    summary = summarize_merge(merged, [])

    assert summary.compared == 0
    assert not summary.matches
    assert covered_window(merged) is None

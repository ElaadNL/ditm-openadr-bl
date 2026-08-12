"""Tests for the SVG overlay of a published and a received profile."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from src.application.capacity_profile import CapacitySignal
from src.application.profile_merge import (
    find_transitions,
    merge_profile_with_log,
    summarize_merge,
)
from src.infrastructure.step_plot import render_overlay_svg
from src.infrastructure.vendor_feedback import AppliedLimit, OcppLimitLog

QUARTER = timedelta(minutes=15)
NOON = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)

_PLOT_LEFT = 62
_PLOT_RIGHT = 1010
_PLOT_TOP = 84
_PLOT_BOTTOM = 416


def _rendered(*, deviating: bool = False) -> str:
    published = [100.0, 100.0, 20.0, 20.0]
    received = [100.0, 100.0, 20.0, 55.0 if deviating else 20.0]

    signals = [
        CapacitySignal(start=NOON + index * QUARTER, duration=QUARTER, value_kw=value)
        for index, value in enumerate(published)
    ]
    log = OcppLimitLog(
        charge_point_ids=("NLTEST0001",),
        message_count=len(received),
        first_message_at=NOON,
        last_message_at=NOON + 4 * QUARTER,
        buffer_fraction=0.1,
        steps=[
            AppliedLimit(
                at=NOON + index * QUARTER,
                signalled_kw=value,
                applied_kw=round(value * 0.9, 3),
            )
            for index, value in enumerate(received)
        ],
    )

    merged = merge_profile_with_log(signals, log)
    summary = summarize_merge(merged, find_transitions(merged, log))
    return render_overlay_svg(merged, summary, "Overlay", "a subtitle")


def _path_points(svg: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for path in re.findall(r'\sd="([^"]+)"', svg):
        points.extend(
            (float(x), float(y)) for x, y in re.findall(r"[ML] ([\d.]+) ([\d.]+)", path)
        )
    return points


def test_the_chart_carries_all_three_series() -> None:
    svg = _rendered()

    assert svg.count('class="series published"') == 1
    assert svg.count('class="series received"') == 1
    assert svg.count('class="series applied"') == 1


def test_every_mark_stays_inside_the_plot_area() -> None:
    points = _path_points(_rendered())

    assert points
    assert all(_PLOT_LEFT <= x <= _PLOT_RIGHT for x, _ in points)
    assert all(_PLOT_TOP <= y <= _PLOT_BOTTOM for _, y in points)


def test_the_series_are_direct_labelled_as_well_as_legended() -> None:
    svg = _rendered()

    # Slot three is below 3:1 on the light surface, so identity may never rest
    # on the legend alone.
    for series in ("published", "received", "applied"):
        assert f">{series} " in svg
    assert "published to the VTN" in svg


def test_the_document_declares_both_themes() -> None:
    svg = _rendered()

    assert "prefers-color-scheme: dark" in svg
    assert 'data-theme="light"' in svg
    assert "#2a78d6" in svg
    assert "#3987e5" in svg


def test_a_matching_merge_says_so_in_the_caption() -> None:
    assert "4 of 4 intervals identical" in _rendered()


def test_a_deviating_interval_is_marked_and_reported() -> None:
    svg = _rendered(deviating=True)

    assert "#d03b3b" in svg
    assert "1 of 4 intervals differ" in svg


def test_the_title_is_escaped() -> None:
    signals = [CapacitySignal(start=NOON, duration=QUARTER, value_kw=100.0)]
    log = OcppLimitLog(
        charge_point_ids=("NLTEST0001",),
        message_count=1,
        first_message_at=NOON,
        last_message_at=NOON + QUARTER,
        buffer_fraction=0.1,
        steps=[AppliedLimit(at=NOON, signalled_kw=100.0, applied_kw=90.0)],
    )
    merged = merge_profile_with_log(signals, log)

    svg = render_overlay_svg(merged, summarize_merge(merged, []), "A & B", "<sub>")

    assert "A &amp; B" in svg
    assert "&lt;sub&gt;" in svg


def test_a_merge_without_coverage_cannot_be_plotted() -> None:
    signals = [CapacitySignal(start=NOON, duration=QUARTER, value_kw=100.0)]
    log = OcppLimitLog(
        charge_point_ids=("NLTEST0001",),
        message_count=1,
        first_message_at=NOON + 10 * QUARTER,
        last_message_at=NOON + 11 * QUARTER,
        buffer_fraction=0.1,
        steps=[
            AppliedLimit(at=NOON + 10 * QUARTER, signalled_kw=100.0, applied_kw=90.0)
        ],
    )
    merged = merge_profile_with_log(signals, log)

    with pytest.raises(ValueError, match="does not cover"):
        render_overlay_svg(merged, summarize_merge(merged, []), "Overlay", "")

"""Rendering a merged profile as a standalone SVG step chart.

The chart overlays what was published on what the charger received, so the two
can be read as one picture. It is written as plain SVG without any dependency,
which keeps it embeddable in a mail, a report, or an HTML page.
"""

import math
from datetime import datetime, timedelta

from src.application.capacity_profile import AMSTERDAM
from src.application.profile_merge import DEVIATES, MergedInterval, MergeSummary

# Categorical slots 1, 2 and 3 of the reference palette, validated against both
# surfaces. Slot 3 sits below 3:1 on the light surface, which is why every
# series carries a direct label rather than relying on the legend alone.
_SERIES = (
    ("published", "#2a78d6", "#3987e5"),
    ("received", "#eb6834", "#d95926"),
    ("applied", "#1baf7a", "#199e70"),
)
_CRITICAL = "#d03b3b"

_WIDTH = 1160
_HEIGHT = 470
_PAD_LEFT = 62
_PAD_RIGHT = 150
_PAD_TOP = 84
_PAD_BOTTOM = 54

_KW_TICK = 20


def render_overlay_svg(
    merged: list[MergedInterval],
    summary: MergeSummary,
    title: str,
    subtitle: str,
) -> str:
    """Render the overlay of a published and a received profile.

    Args:
        merged (list[MergedInterval]): The merged intervals. Intervals the
            message log does not cover are left out of the plot.
        summary (MergeSummary): The headline numbers, used for the caption.
        title (str): The title of the chart.
        subtitle (str): One line of context below the title.

    Returns:
        str: A standalone SVG document.

    Raises:
        ValueError: If no interval is covered by the message log.
    """
    covered = [interval for interval in merged if interval.received is not None]
    if not covered:
        err_msg = "the message log does not cover any interval of the profile."
        raise ValueError(err_msg)

    first = covered[0].start
    last = covered[-1].start + covered[-1].duration
    ceiling = max(
        max(interval.published_kw for interval in covered),
        max(interval.received_kw or 0.0 for interval in covered),
    )
    top_kw = _KW_TICK * math.ceil(ceiling / _KW_TICK)

    def x_of(moment: datetime) -> float:
        span = (last - first).total_seconds()
        offset = (moment - first).total_seconds()
        return _PAD_LEFT + (_WIDTH - _PAD_LEFT - _PAD_RIGHT) * offset / span

    def y_of(kilowatt: float) -> float:
        plot_height = _HEIGHT - _PAD_TOP - _PAD_BOTTOM
        return _PAD_TOP + plot_height * (1 - kilowatt / top_kw)

    parts = [
        _header(title, subtitle),
        _grid(top_kw, y_of),
        _time_axis(first, last, x_of),
        _deviation_marks(covered, x_of),
    ]

    values = (
        [interval.published_kw for interval in covered],
        [interval.received_kw or 0.0 for interval in covered],
        [interval.applied_kw or 0.0 for interval in covered],
    )
    widths = (6.0, 2.0, 2.0)
    opacities = (0.45, 1.0, 0.9)

    for (name, _, _), series, width, opacity in zip(
        _SERIES, values, widths, opacities, strict=True
    ):
        parts.append(
            f'<path class="series {name}" d="{_step_path(covered, series, last, x_of, y_of)}" '
            f'fill="none" stroke-width="{width}" stroke-opacity="{opacity}" '
            'stroke-linejoin="round" stroke-linecap="butt" />'
        )

    parts.append(_direct_labels(values, y_of))
    parts.append(_caption(summary))

    return _document("\n  ".join(parts), title)


def _document(body: str, title: str) -> str:
    """Wrap the chart body in an SVG document with its own theming.

    Args:
        body (str): The rendered chart elements.
        title (str): Accessible title of the chart.

    Returns:
        str: The SVG document.
    """
    light = "\n".join(f"    --{name}: {light_hex};" for name, light_hex, _ in _SERIES)
    dark = "\n".join(f"      --{name}: {dark_hex};" for name, _, dark_hex in _SERIES)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_WIDTH} {_HEIGHT}"
  width="{_WIDTH}" height="{_HEIGHT}" role="img" aria-label="{_escape(title)}"
  font-family="Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif">
  <style>
    svg {{
    --surface: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #77766f;
    --grid: #e6e5e1;
{light}
    }}
    @media (prefers-color-scheme: dark) {{
      svg:where(:not([data-theme="light"])) {{
      --surface: #1a1a19;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #96958c;
      --grid: #2e2e2b;
{dark}
      }}
    }}
    .series.published {{ stroke: var(--published); }}
    .series.received {{ stroke: var(--received); }}
    .series.applied {{ stroke: var(--applied); }}
    .swatch.published {{ fill: var(--published); }}
    .swatch.received {{ fill: var(--received); }}
    .swatch.applied {{ fill: var(--applied); }}
    .title {{ fill: var(--text-primary); font-size: 19px; font-weight: 600; }}
    .subtitle, .caption {{ fill: var(--text-secondary); font-size: 13px; }}
    .tick {{ fill: var(--text-muted); font-size: 11.5px; }}
    .label {{ fill: var(--text-secondary); font-size: 12px; }}
    .grid {{ stroke: var(--grid); stroke-width: 1; }}
  </style>
  <title>{_escape(title)}</title>
  <rect width="{_WIDTH}" height="{_HEIGHT}" fill="var(--surface)" />
  {body}
</svg>
"""


def _header(title: str, subtitle: str) -> str:
    """Render the title, the subtitle and the legend.

    Args:
        title (str): The title of the chart.
        subtitle (str): One line of context.

    Returns:
        str: The SVG fragment.
    """
    legend_labels = (
        "published to the VTN",
        "received (before operator buffer)",
        "applied to the charger",
    )
    legend = []
    offset = float(_PAD_LEFT)
    for (name, _, _), text in zip(_SERIES, legend_labels, strict=True):
        legend.append(
            f'<rect class="swatch {name}" x="{offset}" y="60" width="10" height="10" rx="2" />'
            f'<text class="label" x="{offset + 16}" y="69">{_escape(text)}</text>'
        )
        offset += 24 + 7.1 * len(text)

    return (
        f'<text class="title" x="{_PAD_LEFT}" y="30">{_escape(title)}</text>\n  '
        f'<text class="subtitle" x="{_PAD_LEFT}" y="49">{_escape(subtitle)}</text>\n  '
        + "\n  ".join(legend)
    )


def _grid(top_kw: float, y_of: object) -> str:
    """Render the horizontal gridlines and the kW axis.

    Args:
        top_kw (float): The top of the value axis.
        y_of (object): Callable mapping a value to a y coordinate.

    Returns:
        str: The SVG fragment.
    """
    lines = []
    for kilowatt in range(0, int(top_kw) + 1, _KW_TICK):
        y_position = y_of(kilowatt)  # type: ignore[operator]
        lines.append(
            f'<line class="grid" x1="{_PAD_LEFT}" y1="{y_position:.1f}" '
            f'x2="{_WIDTH - _PAD_RIGHT}" y2="{y_position:.1f}" />'
            f'<text class="tick" x="{_PAD_LEFT - 10}" y="{y_position + 4:.1f}" '
            f'text-anchor="end">{kilowatt}</text>'
        )
    lines.append(
        f'<text class="tick" x="{_PAD_LEFT - 10}" y="{_PAD_TOP - 14}" '
        'text-anchor="end">kW</text>'
    )
    return "\n  ".join(lines)


def _time_axis(first: datetime, last: datetime, x_of: object) -> str:
    """Render the time axis, ticking at every local midnight and noon.

    Args:
        first (datetime): Start of the plotted window.
        last (datetime): End of the plotted window.
        x_of (object): Callable mapping a moment to an x coordinate.

    Returns:
        str: The SVG fragment.
    """
    baseline = _HEIGHT - _PAD_BOTTOM
    parts = [
        f'<line class="grid" x1="{_PAD_LEFT}" y1="{baseline}" '
        f'x2="{_WIDTH - _PAD_RIGHT}" y2="{baseline}" />'
    ]

    local = first.astimezone(AMSTERDAM)
    tick = local.replace(minute=0, second=0, microsecond=0)
    while tick <= last.astimezone(AMSTERDAM):
        if tick >= local and tick.hour in (0, 12):
            x_position = x_of(tick)  # type: ignore[operator]
            label = (
                tick.strftime("%a %-d %b") if tick.hour == 0 else tick.strftime("%H:%M")
            )
            parts.append(
                f'<line class="grid" x1="{x_position:.1f}" y1="{_PAD_TOP}" '
                f'x2="{x_position:.1f}" y2="{baseline}" />'
                f'<text class="tick" x="{x_position:.1f}" y="{baseline + 18}" '
                f'text-anchor="middle">{label}</text>'
            )
        tick += timedelta(hours=1)

    parts.append(
        f'<text class="tick" x="{_WIDTH - _PAD_RIGHT}" y="{baseline + 36}" '
        'text-anchor="end">local time (Europe/Amsterdam)</text>'
    )
    return "\n  ".join(parts)


def _deviation_marks(covered: list[MergedInterval], x_of: object) -> str:
    """Mark the intervals whose received limit differs from the published one.

    Args:
        covered (list[MergedInterval]): The covered intervals.
        x_of (object): Callable mapping a moment to an x coordinate.

    Returns:
        str: The SVG fragment, empty when everything matches.
    """
    marks = []
    for interval in covered:
        if interval.status != DEVIATES:
            continue
        start = x_of(interval.start)  # type: ignore[operator]
        end = x_of(interval.start + interval.duration)  # type: ignore[operator]
        marks.append(
            f'<rect x="{start:.1f}" y="{_PAD_TOP}" width="{max(end - start, 2):.1f}" '
            f'height="{_HEIGHT - _PAD_TOP - _PAD_BOTTOM}" fill="{_CRITICAL}" '
            'fill-opacity="0.18" />'
        )
    return "\n  ".join(marks)


def _step_path(
    covered: list[MergedInterval],
    values: list[float],
    last: datetime,
    x_of: object,
    y_of: object,
) -> str:
    """Build the path of a step series.

    Args:
        covered (list[MergedInterval]): The covered intervals.
        values (list[float]): One value per interval.
        last (datetime): End of the plotted window.
        x_of (object): Callable mapping a moment to an x coordinate.
        y_of (object): Callable mapping a value to a y coordinate.

    Returns:
        str: The `d` attribute of the path.
    """
    commands: list[str] = []
    for interval, value in zip(covered, values, strict=True):
        start = x_of(interval.start)  # type: ignore[operator]
        height = y_of(value)  # type: ignore[operator]
        commands.append(f"{'M' if not commands else 'L'} {start:.1f} {height:.1f}")
        end = x_of(min(interval.start + interval.duration, last))  # type: ignore[operator]
        commands.append(f"L {end:.1f} {height:.1f}")
    return " ".join(commands)


def _direct_labels(values: tuple[list[float], ...], y_of: object) -> str:
    """Label every series at its last value, so the legend is never load bearing.

    Args:
        values (tuple[list[float], ...]): The values of each series.
        y_of (object): Callable mapping a value to a y coordinate.

    Returns:
        str: The SVG fragment.
    """
    labels = []
    texts = ("published", "received", "applied")
    placed: list[float] = []
    for (name, _, _), series, text in zip(_SERIES, values, texts, strict=True):
        y_position = y_of(series[-1])  # type: ignore[operator]
        while any(abs(y_position - taken) < 15 for taken in placed):
            y_position += 15
        placed.append(y_position)
        labels.append(
            f'<rect class="swatch {name}" x="{_WIDTH - _PAD_RIGHT + 10}" '
            f'y="{y_position - 8:.1f}" width="8" height="8" rx="2" />'
            f'<text class="label" x="{_WIDTH - _PAD_RIGHT + 24}" '
            f'y="{y_position:.1f}">{text} {series[-1]:g} kW</text>'
        )
    return "\n  ".join(labels)


def _caption(summary: MergeSummary) -> str:
    """Render the one line conclusion under the chart.

    Args:
        summary (MergeSummary): The headline numbers.

    Returns:
        str: The SVG fragment.
    """
    if summary.matches:
        text = (
            f"{summary.matching} of {summary.compared} intervals identical, "
            f"{summary.followed_transitions} of {summary.transitions} changes followed"
        )
    else:
        text = (
            f"{summary.deviating} of {summary.compared} intervals differ, "
            f"largest difference {summary.max_abs_delta_kw:g} kW"
        )
    return f'<text class="caption" x="{_PAD_LEFT}" y="{_HEIGHT - 10}">{_escape(text)}</text>'


def _escape(text: str) -> str:
    """Escape the characters that cannot appear in SVG text.

    Args:
        text (str): The text to escape.

    Returns:
        str: The escaped text.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

#!/usr/bin/env sh
# Render an SVG to a high resolution PNG.
#
# The chart the profile tool writes carries its own theming in CSS custom
# properties, which the usual command line converters drop. Chrome renders it
# the way a browser does, so it is used here as the renderer.
#
# Usage:
#   scripts/svg-to-png.sh reports/august-2026-vs-heliox.svg          # 3x
#   scripts/svg-to-png.sh reports/august-2026-vs-heliox.svg 4        # 4x
#   scripts/svg-to-png.sh chart.svg 2 /tmp/chart.png                 # own path
#
# The PNG is tagged with the matching resolution (96 dpi per scale step), so it
# drops into a document at the size the chart was designed for.

set -eu

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

svg="${1:?usage: scripts/svg-to-png.sh <file.svg> [scale] [out.png]}"
scale="${2:-3}"
png="${3:-${svg%.svg}@${scale}x.png}"

if [ ! -x "$CHROME" ]; then
    echo "svg-to-png: $CHROME not found, install Chrome or render elsewhere" >&2
    exit 1
fi

width=$(sed -n 's/.*[^-]width="\([0-9]*\)".*/\1/p' "$svg" | head -1)
height=$(sed -n 's/.*[^-]height="\([0-9]*\)".*/\1/p' "$svg" | head -1)

if [ -z "$width" ] || [ -z "$height" ]; then
    echo "svg-to-png: $svg has no width and height to render at" >&2
    exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

{
    echo '<!doctype html><meta charset="utf-8"><style>'
    echo "html,body{margin:0;padding:0;background:#fcfcfb}"
    echo "svg{display:block;width:${width}px;height:${height}px}"
    echo '</style>'
    cat "$svg"
} > "$work/page.html"

"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor="$scale" \
    --window-size="$width,$height" \
    --screenshot="$work/out.png" "file://$work/page.html" >/dev/null 2>&1

mkdir -p "$(dirname "$png")"
cp "$work/out.png" "$png"
sips -s dpiWidth "$((96 * scale))" -s dpiHeight "$((96 * scale))" "$png" >/dev/null 2>&1 || true

echo "$png ($((width * scale))x$((height * scale)) px, $((96 * scale)) dpi)"

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

# Reference OpenADR GAC BL Implementation

This repository contains a reference implementation for a GAC compliant BL implementation.

## Configuration

For the openadr3-client dependency, you need to configure the following environment variables:

```python
OAUTH_TOKEN_ENDPOINT # The oauth token endpoint to provision access tokens from
OAUTH_CLIENT_ID      # The client ID for OAuth client credential authentication
OAUTH_CLIENT_SECRET  # The client secret for OAuth client credential authentication
OAUTH_SCOPES         # Comma-delimited list of OAuth scope to request (optional)
```

The full set of variables the BL reads is declared in `src/config.py`. Locally
they live in a `.env` file in the root of the repository, which is not checked
in.

## Running the BL manually

`src/config.py` uses python-decouple, which only auto-discovers the `.env` file
in a few situations, so running the module directly fails with
`UndefinedValueError: VTN_BASE_URL not found`. Because decouple reads
`os.environ` first, exporting the `.env` into the shell is enough to make the
run work. `scripts/dotenv.sh` does that:

```shell
source scripts/dotenv.sh && poetry run python -m src.main
```

Note that a manual run is not a dry run: it deletes the existing events for the
configured VENs from the VTN and publishes a new capacity limitation event in
their place.

A plain `source .env` does not work, because the entries are written as
`KEY = 'value'` and the shell reads `KEY` as a command when there are spaces
around the `=`. `scripts/dotenv.sh` strips those spaces before exporting.
Alternatively pass a different file with `source scripts/dotenv.sh path/to/other.env`.

## Synthetic congestion profiles

Besides the prediction driven flow above, the repository can generate synthetic
capacity limitation profiles that mimic the grid congestion currently seen in
the Netherlands. They are meant for testing and validation: a profile is written
to CSV, published to the VTN from that CSV, and afterwards compared against what
the VTN stored and against what the vendor hosting the VEN reports as received.

### The shape of a profile

The generator works with three levels, expressed relative to the `--min-kw` and
`--max-kw` band that is passed in, and ramps between them over 30 minutes. On a
working day:

| Local time    | Available capacity | Why                              |
| ------------- | ------------------ | -------------------------------- |
| 00:00 - 06:30 | maximum            | night, no congestion             |
| 07:00 - 09:00 | 60% of the band    | morning peak                     |
| 09:30 - 15:30 | maximum            | daytime, solar production        |
| 16:00 - 20:00 | minimum            | evening peak, the real constraint|
| 20:30 - 21:00 | 60% of the band    | evening shoulder                 |
| 21:30 - 00:00 | maximum            | night, no congestion             |

Weekend days and Dutch national holidays skip the morning peak and only get the
milder evening restriction, between 17:00 and 20:00.

The profile is deterministic: the value of an interval follows from its
timestamp and the band alone. Jitter of up to 2% of the band is applied to the
intermediate levels, derived from a hash of the timestamp rather than from a
random number generator, so no seed has to be stored and regenerating any part
of a period reproduces exactly the same values. The unconstrained level is
always exactly `--max-kw` and the deepest restriction exactly `--min-kw`.

Windows are anchored to Europe/Amsterdam wall clock time while the timestamps
themselves are absolute, so a local day holds 96 intervals normally, 100 on the
day the clock goes back and 92 on the day it goes forward.

### Generating

```shell
poetry run python -m src.tools.profile generate \
    --start 2026-08-03 --weeks 1 --min-kw 20 --max-kw 100 \
    --out profiles/example-week-2026-08-03.csv
```

The period is given as `--days`, `--weeks`, `--months` or an explicit `--end`.
`--end` is exclusive, so covering a month up to and including 31 August means
ending on 1 September:

```shell
poetry run python -m src.tools.profile generate \
    --start 2026-08-04 --end 2026-09-01 --min-kw 20 --max-kw 100 \
    --out profiles/august-2026.csv
```

Generating needs no configuration, so it works without a `.env`.

Profiles live in `profiles/` and are committed, so they can be reviewed and
reused as a reference:

| Profile                              | Period                    | Intervals |
| ------------------------------------ | ------------------------- | --------- |
| `profiles/august-2026.csv`           | 4 August - 31 August 2026 | 2688      |
| `profiles/example-week-2026-08-03.csv` | one example week        | 672       |

Two files are written: the CSV, holding one row per interval, and a
`<name>.meta.json` sidecar holding the bounds, the band and the generator
version. Regenerating a profile produces a byte identical CSV; only the sidecar
carries a timestamp.

```csv
start_utc,start_local,duration,value_kw,payload_type,unit
2026-08-02T22:00:00Z,2026-08-03T00:00:00+02:00,PT15M,100,IMPORT_CAPACITY_LIMIT,KW
```

`start_utc` is the authoritative column. `start_local` is written for the reader,
since the congestion windows only make sense in local time.

### Publishing

```shell
source scripts/dotenv.sh
poetry run python -m src.tools.profile send profiles/august-2026.csv --dry-run
```

The whole period is published as a single event. That event is large: 28 days
comes to 2688 intervals and 376 KiB of JSON, a full 31 day month to 2980
intervals and 417 KiB. `--dry-run` builds and sizes it without sending, which is
worth doing whenever the period grows.

`--start` rebases the profile onto another date, keeping the local time of day
and the exact spacing of the intervals. Add `--align-weekday` to round the shift
to whole weeks, so a working day keeps landing on a working day. Without
`--start` the timestamps in the CSV are used as they are, and a profile that
starts in the past is refused unless `--allow-past` is passed. A profile that
starts at midnight today needs that flag, and the intervals that have already
elapsed are published along with the rest.

Sending deletes the events already in the VTN for the targeted VENs first, the
same way the scheduled function does. Pass `--no-cleanup` to keep them.

The reverse holds as well: the scheduled function in `src/main.py` runs at 07:55
and deletes the events for those VENs before publishing its own prediction based
event. A profile published by hand survives only until the next run of that
timer, so disable it while a long profile is meant to stand.

### Validating

Compare the profile against what the VTN stored:

```shell
poetry run python -m src.tools.profile verify-vtn profiles/august-2026.csv
```

```
Comparing against 1 event(s): c56eaa13-716a-4fd4-bfd9-17c182bf0a8b
Reference intervals: 2688
Observed intervals : 2688
Missing            : 0
Unexpected         : 0
Differing          : 0
MATCH: the observed profile is identical to the reference.
```

Compare it against what the vendor hosting the VEN reports as received:

```shell
poetry run python -m src.tools.profile verify-vendor profiles/august-2026.csv \
    --received vendor-export.csv
```

Both report missing, unexpected and differing intervals, and exit with 1 when
they find any. Pass the same `--start` that was used to send, so the reference
lines up with what was published; leave it out when the profile was sent as it
is. `--tolerance-kw` allows a margin on the values, and `--limit` caps how many
differences are listed per category.

### Comparing against the charge point operator's message log

When the operator sends back its OCPP message log rather than a table of
intervals, `merge` reads the SetChargingProfile calls from it, lays them next to
the published profile and writes both sides into one file:

```shell
poetry run python -m src.tools.profile merge profiles/august-2026.csv \
    --ocpp-log charger-message-logs.csv \
    --out reports/august-2026-vs-operator.csv \
    --plot reports/august-2026-vs-operator.svg
```

The merged CSV holds `published_kw`, `received_kw`, `applied_kw` and the
difference per interval, and `--plot` writes a standalone SVG that overlays the
three. Operators tend to hold a safety margin below the signal, so
`received_kw` is the limit read back through the buffer the log itself reports,
while `applied_kw` is what the charger was actually given.

An interval is compared against the limit that was in force for most of it, not
against the limit exactly on its boundary: a change takes an operator seconds to
push, and that is latency rather than a deviation. How fast each change landed
is reported separately, per change.

Only the part of the profile the log covers is compared. Intervals before the
first and after the last message come out as `not covered` instead of as a
difference.

The vendor export is read by `src/infrastructure/vendor_feedback.py`, which
defaults to the schema written by this tool and detects comma, semicolon and tab
separated files. When the real export looks different, point the tool at the
right columns with `--timestamp-column`, `--value-column`, `--duration-column`
and `--assume-timezone`; anything beyond that belongs in that one module.

### Tests

```shell
poetry run pytest
```

The tests cover the profile generator, including both daylight saving
transitions, the CSV round trip, the translation to and from OpenADR3 events and
the comparison logic. They need no configuration and no network.

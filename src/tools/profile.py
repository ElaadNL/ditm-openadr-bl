"""Generate, publish and verify synthetic congestion profiles.

    poetry run python -m src.tools.profile generate --start 2026-08-03 --weeks 1 \
        --min-kw 20 --max-kw 100 --out profiles/week-2026-08-03.csv
    poetry run python -m src.tools.profile send profiles/week-2026-08-03.csv \
        --start 2026-08-17 --dry-run
    poetry run python -m src.tools.profile verify-vtn profiles/week-2026-08-03.csv \
        --start 2026-08-17
    poetry run python -m src.tools.profile verify-vendor profiles/week-2026-08-03.csv \
        --received vendor-export.csv --start 2026-08-17

Only the commands that talk to the VTN need the environment variables from .env,
so a profile can be generated and inspected without any configuration.
"""

import argparse
import calendar
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.application.capacity_profile import (
    AMSTERDAM,
    CapacitySignal,
    generate_capacity_profile,
    profile_bounds,
    rebase_profile,
)
from src.application.profile_diff import ProfileDiff, compare_profiles
from src.infrastructure.csv_profile import format_utc, read_profile, write_profile

GENERATOR_VERSION = "1.0"

_EXIT_OK = 0
_EXIT_DIFFERENCES = 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the profile tool.

    Args:
        argv (Sequence[str] | None): Arguments to parse. Defaults to sys.argv.

    Returns:
        int: The process exit code. 1 when a verification found differences or
            when the command was refused.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the tool.

    Returns:
        argparse.ArgumentParser: The parser, with one subparser per command.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.tools.profile",
        description="Generate, publish and verify synthetic congestion profiles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    rebase_options = argparse.ArgumentParser(add_help=False)
    rebase_options.add_argument(
        "--start",
        type=date.fromisoformat,
        help=(
            "Local date to rebase the profile onto before using it. Without it "
            "the timestamps in the CSV are used as they are."
        ),
    )
    rebase_options.add_argument(
        "--align-weekday",
        action="store_true",
        help="Round the rebase to whole weeks, so the profile keeps its weekdays.",
    )

    compare_options = argparse.ArgumentParser(add_help=False)
    compare_options.add_argument(
        "--tolerance-kw",
        type=float,
        default=0.0,
        help="Absolute tolerance on the capacity values. Defaults to an exact match.",
    )
    compare_options.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of differences to report per category. Defaults to 10.",
    )

    generate = commands.add_parser(
        "generate", help="Generate a profile and write it to CSV."
    )
    generate.add_argument(
        "--start", type=date.fromisoformat, required=True, help="Local start date."
    )
    generate.add_argument(
        "--start-time",
        type=time.fromisoformat,
        default=time(0, 0),
        help="Local start time. Defaults to midnight.",
    )
    period = generate.add_mutually_exclusive_group(required=True)
    period.add_argument("--days", type=int, help="Number of days to cover.")
    period.add_argument("--weeks", type=int, help="Number of weeks to cover.")
    period.add_argument(
        "--months", type=int, help="Number of calendar months to cover."
    )
    period.add_argument(
        "--end", type=date.fromisoformat, help="Local end date, exclusive."
    )
    generate.add_argument(
        "--min-kw",
        type=float,
        required=True,
        help="Capacity available during the deepest restriction.",
    )
    generate.add_argument(
        "--max-kw",
        type=float,
        required=True,
        help="Capacity available when the grid is unconstrained.",
    )
    generate.add_argument("--out", type=Path, required=True, help="CSV file to write.")
    generate.add_argument(
        "--force", action="store_true", help="Overwrite an existing profile."
    )
    generate.set_defaults(handler=_handle_generate)

    send = commands.add_parser(
        "send", parents=[rebase_options], help="Publish a profile to the VTN."
    )
    send.add_argument("csv", type=Path, help="The profile to publish.")
    send.add_argument(
        "--event-name",
        help="Name of the event. Defaults to a name derived from the date.",
    )
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and size the event without sending it.",
    )
    send.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep the events already in the VTN instead of deleting them first.",
    )
    send.add_argument(
        "--allow-past",
        action="store_true",
        help="Publish even though the profile starts in the past.",
    )
    send.set_defaults(handler=_handle_send)

    verify_vtn = commands.add_parser(
        "verify-vtn",
        parents=[rebase_options, compare_options],
        help="Compare a profile against the events stored in the VTN.",
    )
    verify_vtn.add_argument("csv", type=Path, help="The reference profile.")
    verify_vtn.add_argument(
        "--event-id", help="Only compare against this event instead of all of them."
    )
    verify_vtn.set_defaults(handler=_handle_verify_vtn)

    verify_vendor = commands.add_parser(
        "verify-vendor",
        parents=[rebase_options, compare_options],
        help="Compare a profile against what the VEN vendor reports as received.",
    )
    verify_vendor.add_argument("csv", type=Path, help="The reference profile.")
    verify_vendor.add_argument(
        "--received", type=Path, required=True, help="The export from the vendor."
    )
    verify_vendor.add_argument(
        "--timestamp-column",
        default="start_utc",
        help="Column holding the interval start. Defaults to start_utc.",
    )
    verify_vendor.add_argument(
        "--value-column",
        default="value_kw",
        help="Column holding the capacity limit. Defaults to value_kw.",
    )
    verify_vendor.add_argument(
        "--duration-column",
        default="duration",
        help="Column holding the interval duration. Defaults to duration.",
    )
    verify_vendor.add_argument(
        "--assume-timezone",
        default="UTC",
        help="Timezone of timestamps without an offset. Defaults to UTC.",
    )
    verify_vendor.set_defaults(handler=_handle_verify_vendor)

    return parser


def _handle_generate(args: argparse.Namespace) -> int:
    """Generate a profile and write it to disk.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        int: The exit code.
    """
    out: Path = args.out
    if out.exists() and not args.force:
        print(f"{out} already exists, pass --force to overwrite it.")
        return _EXIT_DIFFERENCES

    start_local = datetime.combine(args.start, args.start_time, tzinfo=AMSTERDAM)
    end_local = _resolve_end(start_local, args)

    signals = generate_capacity_profile(
        start=start_local, end=end_local, min_kw=args.min_kw, max_kw=args.max_kw
    )

    meta = {
        "generator": "capacity_profile",
        "generator_version": GENERATOR_VERSION,
        "generated_at": format_utc(datetime.now(tz=UTC)),
        "period_start_local": start_local.isoformat(),
        "period_end_local": end_local.isoformat(),
        "min_kw": args.min_kw,
        "max_kw": args.max_kw,
    }
    meta_path = write_profile(out, signals, meta)

    print(f"Wrote {out} and {meta_path}")
    _print_profile_summary(signals, args.min_kw, args.max_kw)
    return _EXIT_OK


def _handle_send(args: argparse.Namespace) -> int:
    """Publish a profile to the VTN.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        int: The exit code.
    """
    from src.application.profile_events import build_capacity_limitation_event
    from src.config import MOCK_EAN_NUMBER, PROGRAM_ID, VEN_NAMES
    from src.infrastructure.openadr.bl_client import (
        create_bl_client,
        fetch_events_for_vens,
    )

    signals = _load_reference(args)
    start, end = profile_bounds(signals)

    if start < datetime.now(tz=UTC) and not args.allow_past:
        print(
            f"The profile starts at {format_utc(start)}, which is in the past. "
            "Rebase it with --start YYYY-MM-DD, or pass --allow-past to send it anyway."
        )
        return _EXIT_DIFFERENCES

    ven_names = VEN_NAMES.split(",")
    event_name = (
        args.event_name
        or f"bl-congestion-profile-{start.astimezone(AMSTERDAM):%d-%m-%Y}"
    )
    event = build_capacity_limitation_event(
        signals=signals,
        program_id=PROGRAM_ID,
        ven_names=ven_names,
        power_service_location=MOCK_EAN_NUMBER,
        event_name=event_name,
    )

    payload_bytes = len(
        event.model_dump_json(by_alias=True, exclude_none=True).encode()
    )
    print(f"Event      : {event_name}")
    print(f"Program    : {PROGRAM_ID}")
    print(f"Targets    : {', '.join(ven_names)} / {MOCK_EAN_NUMBER}")
    print(f"Period     : {start.astimezone(AMSTERDAM)} .. {end.astimezone(AMSTERDAM)}")
    print(f"Intervals  : {len(signals)}")
    print(f"Payload    : {payload_bytes / 1024:.1f} KiB of JSON")

    if args.dry_run:
        print("Dry run, nothing was sent.")
        return _EXIT_OK

    bl_client = create_bl_client()

    if not args.no_cleanup:
        for existing in fetch_events_for_vens(bl_client, PROGRAM_ID, ven_names):
            bl_client.events.delete_event_by_id(event_id=existing.id)
            print(f"Deleted existing event {existing.id}")

    created = bl_client.events.create_event(new_event=event)
    print(f"Created event {created.id} in the VTN.")
    return _EXIT_OK


def _handle_verify_vtn(args: argparse.Namespace) -> int:
    """Compare a profile against the events stored in the VTN.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        int: The exit code.
    """
    from src.application.profile_events import extract_capacity_signals
    from src.config import PROGRAM_ID, VEN_NAMES
    from src.infrastructure.openadr.bl_client import (
        create_bl_client,
        fetch_events_for_vens,
    )

    expected = _load_reference(args)
    start, end = profile_bounds(expected)

    bl_client = create_bl_client()
    events = fetch_events_for_vens(bl_client, PROGRAM_ID, VEN_NAMES.split(","))
    if args.event_id:
        events = tuple(event for event in events if event.id == args.event_id)

    if not events:
        print("The VTN holds no events for these VEN targets.")
        return _EXIT_DIFFERENCES

    print(
        f"Comparing against {len(events)} event(s): " + ", ".join(e.id for e in events)
    )

    observed = [
        signal for event in events for signal in extract_capacity_signals(event)
    ]
    in_window = [signal for signal in observed if start <= signal.start < end]
    outside = len(observed) - len(in_window)
    if outside:
        print(f"Ignored {outside} interval(s) outside the period of the profile.")

    return _report(compare_profiles(expected, in_window, args.tolerance_kw), args.limit)


def _handle_verify_vendor(args: argparse.Namespace) -> int:
    """Compare a profile against the signals the vendor reports as received.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        int: The exit code.
    """
    from src.infrastructure.vendor_feedback import (
        VendorColumnMapping,
        read_vendor_profile,
    )

    expected = _load_reference(args)
    mapping = VendorColumnMapping(
        start_column=args.timestamp_column,
        value_column=args.value_column,
        duration_column=args.duration_column,
        assume_timezone=ZoneInfo(args.assume_timezone),
    )
    observed = read_vendor_profile(args.received, mapping)
    print(f"Read {len(observed)} interval(s) from {args.received}")

    return _report(compare_profiles(expected, observed, args.tolerance_kw), args.limit)


def _load_reference(args: argparse.Namespace) -> list[CapacitySignal]:
    """Read the reference profile, rebasing it when a start date was given.

    Args:
        args (argparse.Namespace): The parsed arguments.

    Returns:
        list[CapacitySignal]: The reference profile.
    """
    signals, _ = read_profile(args.csv)
    if args.start:
        signals = rebase_profile(signals, args.start, align_weekday=args.align_weekday)
    return signals


def _resolve_end(start_local: datetime, args: argparse.Namespace) -> datetime:
    """Work out the end of the period from the period arguments.

    The arithmetic is done on the local wall clock, so a day stays a day across a
    daylight saving transition even though it holds 92 or 100 intervals.

    Args:
        start_local (datetime): The local start of the period.
        args (argparse.Namespace): The parsed arguments.

    Returns:
        datetime: The local end of the period, exclusive.
    """
    if args.end:
        return datetime.combine(args.end, start_local.timetz())
    if args.days:
        return _add_local_days(start_local, args.days)
    if args.weeks:
        return _add_local_days(start_local, args.weeks * 7)
    return _add_local_months(start_local, args.months)


def _add_local_days(moment: datetime, days: int) -> datetime:
    """Add whole days to a local moment, keeping its time of day.

    Args:
        moment (datetime): The local moment.
        days (int): The number of days to add.

    Returns:
        datetime: The shifted local moment.
    """
    return datetime.combine(
        moment.date() + timedelta(days=days), moment.time(), tzinfo=moment.tzinfo
    )


def _add_local_months(moment: datetime, months: int) -> datetime:
    """Add whole calendar months to a local moment, keeping its time of day.

    Args:
        moment (datetime): The local moment.
        months (int): The number of months to add.

    Returns:
        datetime: The shifted local moment, with the day clamped to the length of
            the target month.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return datetime.combine(date(year, month, day), moment.time(), tzinfo=moment.tzinfo)


def _print_profile_summary(
    signals: list[CapacitySignal], min_kw: float, max_kw: float
) -> None:
    """Print a short description of a generated profile.

    Args:
        signals (list[CapacitySignal]): The profile.
        min_kw (float): The lower bound of the capacity band.
        max_kw (float): The upper bound of the capacity band.
    """
    start, end = profile_bounds(signals)
    restricted = [signal for signal in signals if signal.value_kw < max_kw]
    deepest = [signal for signal in signals if signal.value_kw <= min_kw]
    interval_hours = signals[0].duration / timedelta(hours=1)

    print(f"Period     : {start.astimezone(AMSTERDAM)} .. {end.astimezone(AMSTERDAM)}")
    print(f"Intervals  : {len(signals)}")
    print(f"Band       : {min_kw:g} - {max_kw:g} kW")
    print(f"Restricted : {len(restricted) * interval_hours:g} h below {max_kw:g} kW")
    print(f"At the floor: {len(deepest) * interval_hours:g} h at {min_kw:g} kW")


def _report(diff: ProfileDiff, limit: int) -> int:
    """Print a diff and turn it into an exit code.

    Args:
        diff (ProfileDiff): The differences found.
        limit (int): Maximum number of differences to print per category.

    Returns:
        int: The exit code.
    """
    print(f"Reference intervals: {diff.expected_count}")
    print(f"Observed intervals : {diff.actual_count}")
    print(f"Missing            : {len(diff.missing)}")
    print(f"Unexpected         : {len(diff.unexpected)}")
    print(f"Differing          : {len(diff.mismatches)}")

    for start in diff.missing[:limit]:
        print(f"  missing    {format_utc(start)}")
    for start in diff.unexpected[:limit]:
        print(f"  unexpected {format_utc(start)}")
    for mismatch in diff.mismatches[:limit]:
        print(f"  {mismatch}")

    if diff.problem_count > limit:
        print(f"  ... reporting the first {limit} of each category.")

    if diff.matches:
        print("MATCH: the observed profile is identical to the reference.")
        return _EXIT_OK

    print(f"DIFFERENCES: {diff.problem_count} problem(s) found.")
    return _EXIT_DIFFERENCES


if __name__ == "__main__":
    raise SystemExit(main())

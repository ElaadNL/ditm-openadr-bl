"""Translation between capacity profiles and OpenADR3 events."""

from collections.abc import Sequence
from datetime import timedelta

from openadr3_client.models.common.interval import Interval
from openadr3_client.models.common.interval_period import IntervalPeriod
from openadr3_client.models.common.target import Target
from openadr3_client.models.common.unit import Unit
from openadr3_client.models.event.event import Event, NewEvent
from openadr3_client.models.event.event_payload import (
    EventPayload,
    EventPayloadDescriptor,
    EventPayloadType,
)

from src.application.capacity_profile import CapacitySignal


def build_capacity_limitation_event(
    signals: list[CapacitySignal],
    program_id: str,
    ven_names: Sequence[str],
    power_service_location: str,
    event_name: str,
) -> NewEvent:
    """Build a capacity limitation event covering the whole profile.

    Args:
        signals (list[CapacitySignal]): The profile to publish. Must not be empty.
        program_id (str): The program the event belongs to.
        ven_names (Sequence[str]): The VEN names to target.
        power_service_location (str): The EAN to target.
        event_name (str): The name of the event.

    Returns:
        NewEvent: The event, with one interval per signal.

    Raises:
        ValueError: If the profile is empty.
    """
    if not signals:
        err_msg = "cannot build an event from an empty profile."
        raise ValueError(err_msg)

    intervals = tuple(
        Interval(
            id=interval_id,
            interval_period=IntervalPeriod(
                start=signal.start, duration=signal.duration
            ),
            payloads=(
                EventPayload(
                    type=EventPayloadType.IMPORT_CAPACITY_LIMIT,
                    values=(signal.value_kw,),
                ),
            ),
        )
        for interval_id, signal in enumerate(signals)
    )

    return NewEvent(
        programID=program_id,
        event_name=event_name,
        payload_descriptors=(
            EventPayloadDescriptor(
                payload_type=EventPayloadType.IMPORT_CAPACITY_LIMIT, units=Unit.KW
            ),
        ),
        intervals=intervals,
        targets=(
            Target(type="VEN_NAME", values=tuple(ven_names)),
            Target(type="POWER_SERVICE_LOCATION", values=(power_service_location,)),
        ),
    )


def extract_capacity_signals(event: Event) -> list[CapacitySignal]:
    """Extract the capacity limitation signals from an event.

    Intervals carry their own interval period in the events this repository
    publishes. An event level interval period is honoured as a fallback, in which
    case the intervals are laid out back to back from the event start.

    Args:
        event (Event): The event to read, typically one retrieved from the VTN.

    Returns:
        list[CapacitySignal]: The signals of the event, ordered by start.

    Raises:
        ValueError: If an interval has no interval period to fall back on, or its
            capacity limit payload does not hold a numeric value.
    """
    signals: list[CapacitySignal] = []
    offset = timedelta()

    for interval in event.intervals:
        period = interval.interval_period or event.interval_period
        if period is None:
            err_msg = f"interval {interval.id} has no interval period."
            raise ValueError(err_msg)

        start = period.start if interval.interval_period else period.start + offset
        offset += period.duration

        value = _capacity_limit_value(interval)
        if value is None:
            continue

        signals.append(
            CapacitySignal(start=start, duration=period.duration, value_kw=value)
        )

    signals.sort(key=lambda signal: signal.start)
    return signals


def _capacity_limit_value(interval: Interval[EventPayload]) -> float | None:
    """Return the import capacity limit of an interval, if it carries one.

    Args:
        interval (Interval[EventPayload]): The interval to read.

    Returns:
        float | None: The limit in kW, or None if the interval carries no import
            capacity limit payload.

    Raises:
        ValueError: If the payload does not hold a single numeric value.
    """
    for payload in interval.payloads:
        if payload.type != EventPayloadType.IMPORT_CAPACITY_LIMIT:
            continue
        if len(payload.values) != 1:
            err_msg = (
                f"interval {interval.id} has {len(payload.values)} capacity limit "
                "values, expected exactly one."
            )
            raise ValueError(err_msg)
        try:
            return float(payload.values[0])  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            err_msg = (
                f"interval {interval.id} has a non numeric capacity limit "
                f"{payload.values[0]!r}."
            )
            raise ValueError(err_msg) from exc
    return None

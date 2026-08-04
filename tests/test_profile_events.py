"""Tests for the translation between profiles and OpenADR3 events."""

from datetime import UTC, datetime, timedelta

import pytest
from openadr3_client.models.common.interval import Interval
from openadr3_client.models.common.interval_period import IntervalPeriod
from openadr3_client.models.event.event import ExistingEvent, NewEvent
from openadr3_client.models.event.event_payload import EventPayload, EventPayloadType

from src.application.capacity_profile import CapacitySignal
from src.application.profile_events import (
    build_capacity_limitation_event,
    extract_capacity_signals,
)

SIGNALS = [
    CapacitySignal(
        start=datetime(2026, 8, 5, 4, 0, tzinfo=UTC),
        duration=timedelta(minutes=15),
        value_kw=100.0,
    ),
    CapacitySignal(
        start=datetime(2026, 8, 5, 4, 15, tzinfo=UTC),
        duration=timedelta(minutes=15),
        value_kw=20.0,
    ),
]


def _event() -> NewEvent:
    return build_capacity_limitation_event(
        signals=SIGNALS,
        program_id="program-1",
        ven_names=["ven-a", "ven-b"],
        power_service_location="871234567890123456",
        event_name="bl-congestion-profile-05-08-2026",
    )


def test_every_signal_becomes_an_interval() -> None:
    event = _event()

    assert len(event.intervals) == len(SIGNALS)
    assert [interval.id for interval in event.intervals] == [0, 1]
    assert event.intervals[0].payloads[0].values == (100.0,)
    assert event.intervals[0].payloads[0].type == EventPayloadType.IMPORT_CAPACITY_LIMIT


def test_the_event_targets_the_vens_and_the_connection() -> None:
    event = _event()

    targets = {target.type: target.values for target in event.targets or ()}

    assert targets["VEN_NAME"] == ("ven-a", "ven-b")
    assert targets["POWER_SERVICE_LOCATION"] == ("871234567890123456",)


def test_the_payload_descriptor_declares_kilowatts() -> None:
    descriptors = _event().payload_descriptors or ()

    assert len(descriptors) == 1
    assert descriptors[0].units == "KW"


def test_signals_survive_a_round_trip_through_an_event() -> None:
    assert extract_capacity_signals(_event()) == SIGNALS


def _event_from_vtn(**overrides: object) -> ExistingEvent:
    """Build an event the way it could come back from a VTN.

    The GAC validators reject most of these shapes on creation, which is exactly
    why the extractor has to cope with them: it reads what a VTN returns, not
    what this repository is allowed to publish. Validation is therefore bypassed
    here rather than worked around.
    """
    defaults: dict[str, object] = {
        "id": "event-1",
        "created_date_time": datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        "modification_date_time": datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
        "program_id": "program-1",
        "interval_period": None,
    }
    return ExistingEvent.model_construct(None, **{**defaults, **overrides})


def test_an_event_level_interval_period_is_used_as_a_fallback() -> None:
    event = _event_from_vtn(
        interval_period=IntervalPeriod(
            start=datetime(2026, 8, 5, 4, 0, tzinfo=UTC), duration=timedelta(minutes=15)
        ),
        intervals=(
            Interval(
                id=0,
                payloads=(
                    EventPayload(
                        type=EventPayloadType.IMPORT_CAPACITY_LIMIT, values=(100.0,)
                    ),
                ),
            ),
            Interval(
                id=1,
                payloads=(
                    EventPayload(
                        type=EventPayloadType.IMPORT_CAPACITY_LIMIT, values=(20.0,)
                    ),
                ),
            ),
        ),
    )

    assert extract_capacity_signals(event) == SIGNALS


def test_intervals_without_a_capacity_limit_are_ignored() -> None:
    event = _event_from_vtn(
        intervals=(
            Interval(
                id=0,
                interval_period=IntervalPeriod(
                    start=datetime(2026, 8, 5, 4, 0, tzinfo=UTC),
                    duration=timedelta(minutes=15),
                ),
                payloads=(EventPayload(type=EventPayloadType.PRICE, values=(0.25,)),),
            ),
        ),
    )

    assert extract_capacity_signals(event) == []


def test_an_interval_without_a_period_is_rejected() -> None:
    event = _event_from_vtn(
        intervals=(
            Interval(
                id=0,
                payloads=(
                    EventPayload(
                        type=EventPayloadType.IMPORT_CAPACITY_LIMIT, values=(100.0,)
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="no interval period"):
        extract_capacity_signals(event)


def test_an_empty_profile_produces_no_event() -> None:
    with pytest.raises(ValueError, match="empty profile"):
        build_capacity_limitation_event(
            signals=[],
            program_id="program-1",
            ven_names=["ven-a"],
            power_service_location="871234567890123456",
            event_name="empty",
        )

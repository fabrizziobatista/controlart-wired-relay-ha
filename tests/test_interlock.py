"""Tests for Controlart logical interlock atomicity."""

import asyncio
from datetime import timedelta

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.controlart_wired_relay.const import parse_interlock_pairs
from custom_components.controlart_wired_relay.coordinator import (
    ControlartRelayCoordinator,
    ControlartRelayError,
)


class FakeRelayClient:
    """Deterministic stateful relay client for coordinator tests."""

    mac_suffix = "6D-08-CA"
    host = "192.0.2.10"
    port = 4998

    def __init__(
        self,
        outputs: list[bool],
        *,
        fail_command: tuple[int, bool] | None = None,
        response_override: dict[tuple[int, bool], list[bool]] | None = None,
    ) -> None:
        self.outputs = list(outputs)
        self.commands: list[tuple[int, bool]] = []
        self.fail_command = fail_command
        self.response_override = response_override or {}
        self.peer_off = asyncio.Event()
        self.ever_both_on = False

    async def async_set_output(self, channel: int, value: bool) -> dict:
        self.commands.append((channel, value))
        if self.fail_command == (channel, value):
            raise ControlartRelayError("simulated command failure")

        response_outputs = self.response_override.get((channel, value))
        if response_outputs is None:
            self.outputs[channel] = value
            response_outputs = self.outputs
        if not value:
            self.peer_off.set()
        self.ever_both_on |= bool(len(self.outputs) > 1 and self.outputs[0] and self.outputs[1])
        return {"inputs": [], "outputs": list(response_outputs)}

    async def async_get_state(self) -> dict:
        return {"inputs": [], "outputs": list(self.outputs)}

    async def async_close(self) -> None:
        """Match the client shutdown API."""


def _coordinator(hass, client: FakeRelayClient, pairs, delay_ms: int = 1):
    coordinator = ControlartRelayCoordinator(
        hass,
        client,
        "test",
        timedelta(seconds=60),
        interlock_pairs=pairs,
        interlock_delay_ms=delay_ms,
    )
    coordinator.data = {"inputs": [], "outputs": list(client.outputs)}
    return coordinator


def test_parse_interlock_pairs_accepts_pair_and_deduplicates_reverse() -> None:
    """One pair is valid and a reversed duplicate remains one pair."""
    assert parse_interlock_pairs("0-1\n1-0") == [(0, 1)]


@pytest.mark.parametrize("value", ["0-0", "0-1\n0-2"])
def test_parse_interlock_pairs_rejects_self_and_overlap(value: str) -> None:
    """A channel can belong to only one configured pair."""
    with pytest.raises(ValueError):
        parse_interlock_pairs(value)


async def test_interlock_turn_on_turns_off_peer_then_waits_then_turns_on(hass) -> None:
    """The normal transaction has the intended command order."""
    client = FakeRelayClient([False, True])
    coordinator = _coordinator(hass, client, [(0, 1)], delay_ms=1)

    await coordinator.async_set_output(0, True)

    assert client.commands == [(1, False), (0, True)]
    assert client.outputs == [True, False]


async def test_concurrent_turn_on_same_pair_is_serialized_last_operation_wins(hass) -> None:
    """The second request waits for the first pair transaction to finish."""
    client = FakeRelayClient([False, True])
    coordinator = _coordinator(hass, client, [(0, 1)], delay_ms=20)

    first = asyncio.create_task(coordinator.async_set_output(0, True))
    await client.peer_off.wait()
    second = asyncio.create_task(coordinator.async_set_output(1, True))
    await asyncio.gather(first, second)

    assert client.commands == [(1, False), (0, True), (0, False), (1, True)]
    assert client.outputs == [False, True]
    assert not client.ever_both_on


async def test_turn_off_waits_for_turn_on_transaction_in_the_same_pair(hass) -> None:
    """An OFF request cannot interleave between peer OFF and target ON."""
    client = FakeRelayClient([False, True])
    coordinator = _coordinator(hass, client, [(0, 1)], delay_ms=20)

    turn_on = asyncio.create_task(coordinator.async_set_output(0, True))
    await client.peer_off.wait()
    turn_off = asyncio.create_task(coordinator.async_set_output(0, False))
    await asyncio.gather(turn_on, turn_off)

    assert client.commands == [(1, False), (0, True), (0, False)]
    assert client.outputs == [False, False]


async def test_off_response_that_keeps_peer_on_aborts_target_turn_on(hass) -> None:
    """A successful socket command is insufficient if its state response is unsafe."""
    client = FakeRelayClient(
        [False, True], response_override={(1, False): [False, True]}
    )
    coordinator = _coordinator(hass, client, [(0, 1)])

    with pytest.raises(HomeAssistantError, match="remained on"):
        await coordinator.async_set_output(0, True)

    assert client.commands == [(1, False)]
    assert coordinator.data["outputs"] == [False, True]


async def test_peer_becoming_on_during_delay_aborts_target_turn_on(hass) -> None:
    """A newer coordinator update is rechecked before the target command."""
    client = FakeRelayClient([False, True])
    coordinator = _coordinator(hass, client, [(0, 1)], delay_ms=20)

    turn_on = asyncio.create_task(coordinator.async_set_output(0, True))
    await client.peer_off.wait()
    coordinator.async_set_updated_data({"inputs": [], "outputs": [False, True]})

    with pytest.raises(HomeAssistantError, match="is on"):
        await turn_on

    assert client.commands == [(1, False)]


async def test_off_failure_does_not_turn_on_target(hass) -> None:
    """A failed peer OFF ends the transaction before target ON."""
    client = FakeRelayClient([False, True], fail_command=(1, False))
    coordinator = _coordinator(hass, client, [(0, 1)])

    with pytest.raises(HomeAssistantError, match="simulated command failure"):
        await coordinator.async_set_output(0, True)

    assert client.commands == [(1, False)]
    assert client.outputs == [False, True]


async def test_on_failure_leaves_peer_off_without_rollback(hass) -> None:
    """A failed target ON does not automatically re-enable its peer."""
    client = FakeRelayClient([False, True], fail_command=(0, True))
    coordinator = _coordinator(hass, client, [(0, 1)])

    with pytest.raises(HomeAssistantError, match="simulated command failure"):
        await coordinator.async_set_output(0, True)

    assert client.commands == [(1, False), (0, True)]
    assert client.outputs == [False, False]


async def test_fallback_waits_for_pair_lock_and_rechecks_conflict(hass) -> None:
    """Fallback cannot interleave with a pair transaction."""
    client = FakeRelayClient([True, True])
    coordinator = _coordinator(hass, client, [(0, 1)])
    lock = coordinator._interlock_lock_for_channel(0)
    assert lock is not None
    await lock.acquire()
    try:
        coordinator._check_interlock_conflicts(coordinator.data)
        await asyncio.sleep(0)
        assert client.commands == []
    finally:
        lock.release()
    await hass.async_block_till_done()
    assert client.commands == [(0, False), (1, False)]
    assert client.outputs == [False, False]


async def test_fallback_and_turn_on_share_the_same_pair_lock(hass) -> None:
    """A requested turn-on waits until an already scheduled fallback finishes."""
    client = FakeRelayClient([True, True])
    coordinator = _coordinator(hass, client, [(0, 1)])
    lock = coordinator._interlock_lock_for_channel(0)
    assert lock is not None
    await lock.acquire()
    try:
        coordinator._check_interlock_conflicts(coordinator.data)
        request_turn_on = asyncio.create_task(coordinator.async_set_output(0, True))
        await asyncio.sleep(0)
    finally:
        lock.release()

    await request_turn_on
    await hass.async_block_till_done()
    assert client.commands == [(0, False), (1, False), (0, True)]
    assert client.outputs == [True, False]


async def test_different_pairs_and_unpaired_channel_are_not_pair_locked(hass) -> None:
    """A held pair lock does not block unrelated channels."""
    client = FakeRelayClient([False, False, False, False, False])
    coordinator = _coordinator(hass, client, [(0, 1), (2, 3)])
    lock = coordinator._interlock_lock_for_channel(0)
    assert lock is not None
    await lock.acquire()
    try:
        await asyncio.wait_for(coordinator.async_set_output(2, True), timeout=0.1)
    finally:
        lock.release()

    await asyncio.wait_for(coordinator.async_set_output(4, True), timeout=0.1)
    assert client.commands == [(2, True), (4, True)]


async def test_interlock_stress_never_sets_both_outputs_on(hass) -> None:
    """Repeated competing HA requests cannot create an internal ON/ON state."""
    client = FakeRelayClient([False, True])
    coordinator = _coordinator(hass, client, [(0, 1)], delay_ms=1)

    for _ in range(100):
        client.outputs[:] = [False, True]
        coordinator.data = {"inputs": [], "outputs": list(client.outputs)}
        await asyncio.gather(
            coordinator.async_set_output(0, True),
            coordinator.async_set_output(1, True),
        )

    assert not client.ever_both_on


async def test_stopping_coordinator_rejects_new_operations(hass) -> None:
    """Unload state prevents a new relay command from starting."""
    client = FakeRelayClient([False, False])
    coordinator = _coordinator(hass, client, [(0, 1)])
    await coordinator.async_stop_listener()

    with pytest.raises(HomeAssistantError, match="stopping"):
        await coordinator.async_set_output(0, True)

    assert client.commands == []


async def test_unload_cancels_pending_fallback_task(hass) -> None:
    """A fallback waiting on a pair lock does not survive coordinator shutdown."""
    client = FakeRelayClient([True, True])
    coordinator = _coordinator(hass, client, [(0, 1)])
    lock = coordinator._interlock_lock_for_channel(0)
    assert lock is not None
    await lock.acquire()
    try:
        coordinator._check_interlock_conflicts(coordinator.data)
        await asyncio.sleep(0)
        assert coordinator._background_tasks
        await coordinator.async_stop_listener()
        assert not coordinator._background_tasks
    finally:
        lock.release()

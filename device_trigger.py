"""Device triggers for Controlart Wired Relay inputs."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import (
    event as event_trigger,
    state as state_trigger,
)
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import DOMAIN, EVENT_KEYPAD, INPUT_COUNT

CONF_SUBTYPE = "subtype"
CONF_EVENT_DATA = "event_data"
CONF_EVENT_TYPE = "event_type"
TRIGGER_TYPE_INPUT_PRESSED = "input_pressed"
TRIGGER_TYPE_KEYPAD_EVENT = "keypad_event"
INPUT_SUBTYPES = [f"in{channel}" for channel in range(INPUT_COUNT)]
KEYPAD_TYP_ID = "02"
KEYPAD_DEV_ID = "01-0E-11"
KEYPAD_KEYS = ("0", "1", "2", "3")
KEYPAD_EVENTS = ("click", "double_click", "long_click", "press", "release")
KEYPAD_SUBTYPES = [
    f"keypad_{KEYPAD_DEV_ID}_key_{key}_{event}"
    for key in KEYPAD_KEYS
    for event in KEYPAD_EVENTS
]
ALL_SUBTYPES = INPUT_SUBTYPES + KEYPAD_SUBTYPES

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(
            [TRIGGER_TYPE_INPUT_PRESSED, TRIGGER_TYPE_KEYPAD_EVENT]
        ),
        vol.Required(CONF_SUBTYPE): vol.In(ALL_SUBTYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """Return device triggers for Controlart relay inputs."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_device(
        registry, device_id, include_disabled_entities=False
    )

    if not any(entry.platform == DOMAIN for entry in entries):
        return []

    input_triggers = [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_INPUT_PRESSED,
            CONF_SUBTYPE: subtype,
        }
        for subtype in INPUT_SUBTYPES
    ]
    keypad_triggers = [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_KEYPAD_EVENT,
            CONF_SUBTYPE: subtype,
        }
        for subtype in KEYPAD_SUBTYPES
    ]
    return input_triggers + keypad_triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger for an input or keypad event."""
    config = TRIGGER_SCHEMA(config)
    if config[CONF_TYPE] == TRIGGER_TYPE_KEYPAD_EVENT:
        key, keypad_event = _parse_keypad_subtype(config[CONF_SUBTYPE])
        event_data = {
            "typ_id": KEYPAD_TYP_ID,
            "dev_id": KEYPAD_DEV_ID,
            "key": key,
            "event": keypad_event,
        }
        config_entry_id = _get_config_entry_id(hass, config[CONF_DEVICE_ID])
        if config_entry_id is not None:
            event_data["config_entry_id"] = config_entry_id

        event_config = {
            CONF_PLATFORM: "event",
            CONF_EVENT_TYPE: EVENT_KEYPAD,
            CONF_EVENT_DATA: event_data,
        }
        return await event_trigger.async_attach_trigger(
            hass,
            event_config,
            action,
            trigger_info,
            platform_type="device",
        )

    entity_id = _get_input_entity_id(
        hass, config[CONF_DEVICE_ID], config[CONF_SUBTYPE]
    )

    state_config = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: entity_id,
        "from": STATE_OFF,
        "to": STATE_ON,
    }
    return await state_trigger.async_attach_trigger(
        hass,
        state_config,
        action,
        trigger_info,
        platform_type="device",
    )


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: dict
) -> dict[str, vol.Schema]:
    """List trigger capabilities."""
    return {"extra_fields": vol.Schema({})}


def _parse_keypad_subtype(subtype: str) -> tuple[str, str]:
    """Return key and event from a fixed keypad subtype."""
    prefix = f"keypad_{KEYPAD_DEV_ID}_key_"
    if not subtype.startswith(prefix):
        raise ValueError(f"Invalid Controlart keypad subtype: {subtype}")

    key, event_name = subtype[len(prefix) :].split("_", 1)
    if key not in KEYPAD_KEYS or event_name not in KEYPAD_EVENTS:
        raise ValueError(f"Invalid Controlart keypad subtype: {subtype}")
    return key, event_name


def _get_config_entry_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Return config entry id for this Controlart device if available."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_device(
        registry, device_id, include_disabled_entities=False
    )
    for entry in entries:
        if entry.platform == DOMAIN and entry.config_entry_id is not None:
            return entry.config_entry_id
    return None


def _get_input_entity_id(
    hass: HomeAssistant, device_id: str, subtype: str
) -> str:
    """Return the binary sensor entity_id for an input subtype."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_device(
        registry, device_id, include_disabled_entities=False
    )
    suffix = f"_{subtype}"

    for entry in entries:
        if (
            entry.domain == "binary_sensor"
            and entry.platform == DOMAIN
            and entry.unique_id.endswith(suffix)
        ):
            return entry.entity_id

    raise ValueError(f"No Controlart input entity found for {subtype}")

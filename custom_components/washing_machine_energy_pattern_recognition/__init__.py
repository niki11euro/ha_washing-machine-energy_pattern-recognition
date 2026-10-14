"""Washing machine energy pattern recognition integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .manager import WashingMachineManager

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = WashingMachineManager(hass, entry)
    try:
        await manager.async_start()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await manager.async_stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _register_services(hass)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        manager = hass.data[DOMAIN].pop(entry.entry_id)
        await manager.async_stop()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "import_history")
            hass.services.async_remove(DOMAIN, "label_cycle")
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "import_history"):
        return

    def _managers(call: ServiceCall):
        entry_id = call.data.get("entry_id")
        entries = hass.data.get(DOMAIN, {})
        if entry_id:
            if entry_id not in entries:
                raise ValueError(f"Unknown entry_id: {entry_id}")
            return [entries[entry_id]]
        if len(entries) != 1:
            raise ValueError("Specify entry_id when multiple washing machines are configured")
        return list(entries.values())

    async def _import(call: ServiceCall) -> None:
        for manager in _managers(call):
            imported = await manager.async_import_history(call.data.get("days"))
            _LOGGER.info("Imported %s washing cycles for %s", imported, manager.name)

    async def _label(call: ServiceCall) -> None:
        for manager in _managers(call):
            found = await manager.async_label_cycle(call.data["cycle_id"], call.data["label"])
            if not found:
                _LOGGER.warning("Cycle %s not found for %s", call.data["cycle_id"], manager.name)

    hass.services.async_register(
        DOMAIN, "import_history", _import,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Optional("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
        }),
    )
    hass.services.async_register(
        DOMAIN, "label_cycle", _label,
        schema=vol.Schema({
            vol.Optional("entry_id"): cv.string,
            vol.Required("cycle_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required("label"): vol.All(cv.string, vol.Length(min=1, max=80)),
        }),
    )

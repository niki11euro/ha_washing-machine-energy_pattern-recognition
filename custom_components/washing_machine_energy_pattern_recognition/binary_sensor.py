"""Running indicator for dashboards and automations."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WashingPatternRunning(manager, entry.entry_id)])


class WashingPatternRunning(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, manager, entry_id: str):
        self.manager = manager
        self._attr_unique_id = f"{entry_id}_running"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=manager.name,
            manufacturer="Washing Machine Energy Pattern Recognition",
            model="Power profile analyzer",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self.manager.active_since is not None

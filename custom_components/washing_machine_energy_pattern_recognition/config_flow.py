"""Setup through the native Home Assistant UI."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_NAME, CONF_POWER_ENTITY, DEFAULT_NAME, DEFAULT_OPTIONS, DOMAIN


class WashingMachineFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Associate this integration with a power sensor."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_POWER_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_POWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power")
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return WashingMachineOptions()


class WashingMachineOptions(config_entries.OptionsFlow):
    """Thresholds and prediction cadence."""

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            if user_input["end_w"] >= user_input["start_w"]:
                return self.async_show_form(
                    step_id="init", data_schema=self._schema(),
                    errors={"base": "threshold_order"},
                )
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=self._schema())

    def _schema(self) -> vol.Schema:
        options = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return vol.Schema({
            vol.Required("start_w", default=options["start_w"]): vol.All(vol.Coerce(float), vol.Range(min=1, max=1000)),
            vol.Required("end_w", default=options["end_w"]): vol.All(vol.Coerce(float), vol.Range(min=0, max=500)),
            vol.Required("start_hold", default=options["start_hold"]): vol.All(vol.Coerce(int), vol.Range(min=5, max=600)),
            vol.Required("end_hold", default=options["end_hold"]): vol.All(vol.Coerce(int), vol.Range(min=60, max=1800)),
            vol.Required("min_cycle_minutes", default=options["min_cycle_minutes"]): vol.All(vol.Coerce(int), vol.Range(min=3, max=120)),
            vol.Required("prediction_after_minutes", default=options["prediction_after_minutes"]): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
            vol.Required("prediction_every_minutes", default=options["prediction_every_minutes"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
            vol.Required("import_days", default=options["import_days"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
        })

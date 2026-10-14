"""Integration constants."""

DOMAIN = "washing_machine_energy_pattern_recognition"
PLATFORMS = ["sensor", "binary_sensor"]
CONF_POWER_ENTITY = "power_entity"
CONF_NAME = "name"
DEFAULT_NAME = "Washing machine"
DEFAULT_OPTIONS = {
    "start_w": 5.0,
    "end_w": 2.5,
    "start_hold": 20,
    "end_hold": 480,
    "min_cycle_minutes": 10,
    "prediction_after_minutes": 10,
    "prediction_every_minutes": 5,
    "import_days": 7,
}

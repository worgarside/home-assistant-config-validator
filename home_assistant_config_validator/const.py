"""Constants for the configuration validator."""

# pylint: disable=wrong-import-position
# mypy: disable-error-code="import"

from __future__ import annotations

import re
import sys
from argparse import ArgumentParser
from json import loads
from logging import getLogger
from pathlib import Path
from typing import TypedDict
from unittest.mock import MagicMock

from wg_utilities.loggers import add_stream_handler

from .custom_components_loader import import_custom_components

# Home Assistant Imports

# Mock out packages that are not installable in a CI environment and would otherwise
# cause the custom components to fail to load
for package_to_mock in (
    "bluetooth",
    "bluetooth._bluetooth",
):
    sys.modules[package_to_mock] = MagicMock()

from homeassistant.components.binary_sensor import (  # noqa: E402
    PLATFORM_SCHEMA as BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.bluetooth_le_tracker.device_tracker import (  # noqa: E402
    PLATFORM_SCHEMA as BLUETOOTH_LE_TRACKER_SCHEMA,
)
from homeassistant.components.bluetooth_tracker.device_tracker import (  # noqa: E402
    PLATFORM_SCHEMA as BLUETOOTH_TRACKER_SCHEMA,
)
from homeassistant.components.device_tracker import (  # noqa: E402
    PLATFORM_SCHEMA as DEVICE_TRACKER_SCHEMA,
)
from homeassistant.components.google_maps.device_tracker import (  # noqa: E402
    PLATFORM_SCHEMA as GOOGLE_MAPS_SCHEMA,
)
from homeassistant.components.history_stats.sensor import (  # noqa: E402
    PLATFORM_SCHEMA as SENSOR_HISTORY_STATS_SCHEMA,
)
from homeassistant.components.input_boolean import (  # noqa: E402
    InputBooleanStorageCollection,
)
from homeassistant.components.input_button import (  # noqa: E402
    InputButtonStorageCollection,
)
from homeassistant.components.input_datetime import (  # noqa: E402
    DateTimeStorageCollection,
)
from homeassistant.components.input_number import NumberStorageCollection  # noqa: E402
from homeassistant.components.input_select import (  # noqa: E402
    InputSelectStorageCollection,
)
from homeassistant.components.input_text import InputTextStorageCollection  # noqa: E402
from homeassistant.components.london_air.sensor import (  # noqa: E402
    PLATFORM_SCHEMA as SENSOR_LONDON_AIR_SCHEMA,
)
from homeassistant.components.mqtt.binary_sensor import (  # noqa: E402
    PLATFORM_SCHEMA_MODERN as MQTT_BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.mqtt.sensor import (  # noqa: E402
    PLATFORM_SCHEMA_MODERN as MQTT_SENSOR_SCHEMA,
)
from homeassistant.components.ping.binary_sensor import (  # noqa: E402
    PLATFORM_SCHEMA as PING_SCHEMA,
)
from homeassistant.components.rest.sensor import (  # noqa: E402
    PLATFORM_SCHEMA as SENSOR_REST_SCHEMA,
)
from homeassistant.components.rest_command import (  # noqa: E402
    CONFIG_SCHEMA as REST_COMMAND_SCHEMA,
)
from homeassistant.components.script.config import (  # noqa: E402
    SCRIPT_ENTITY_SCHEMA as SCRIPT_SCHEMA,
)
from homeassistant.components.systemmonitor.sensor import (  # noqa: E402
    PLATFORM_SCHEMA as SENSOR_SYSTEMMONITOR_SCHEMA,
)
from homeassistant.components.template.binary_sensor import (  # noqa: E402
    BINARY_SENSOR_SCHEMA as TEMPLATE_BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.template.cover import COVER_SCHEMA  # noqa: E402
from homeassistant.components.template.sensor import (  # noqa: E402
    SENSOR_SCHEMA as TEMPLATE_SENSOR_SCHEMA,
)
from homeassistant.components.universal.media_player import (  # noqa: E402
    PLATFORM_SCHEMA as UNIVERSAL_MEDIA_PLAYER_SCHEMA,
)

# This import order fixes an issue with `websocket_api.websocket_command` not being
# loaded correctly; not sure why
from homeassistant.components.automation.config import (  # isort:skip # noqa: E402
    PLATFORM_SCHEMA as AUTOMATION_SCHEMA,
)

# Args
REPO_PATH = Path().cwd()


parser = ArgumentParser(description="Custom Component Parser")

parser.add_argument(
    "-c",
    "--config-path",
    type=Path,
    required=False,
    help="Comma or space-delimited list of `<repo URL>|<schema import path>` pairs",
    default=REPO_PATH / "config_validator.json",
)

args, _ = parser.parse_known_args()

_BASE_CONFIG = loads(args.config_path.read_text())

CUSTOM_VALIDATIONS = _BASE_CONFIG["customValidators"]
CUSTOM_COMPONENTS_CONFIG = _BASE_CONFIG["customComponents"]


# Custom Components Imports

component_modules = import_custom_components(CUSTOM_COMPONENTS_CONFIG)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


ENTITIES_DIR = REPO_PATH / "entities"
INTEGRATIONS_DIR = REPO_PATH / "integrations"

DOMAIN_SCHEMA_MAP = {
    "automation": AUTOMATION_SCHEMA,
    "binary_sensor": BINARY_SENSOR_SCHEMA,
    "binary_sensor.ping": PING_SCHEMA,
    "cover": COVER_SCHEMA,
    "device_tracker": DEVICE_TRACKER_SCHEMA,
    "device_tracker.bluetooth_le_tracker": BLUETOOTH_LE_TRACKER_SCHEMA,
    "device_tracker.bluetooth_tracker": BLUETOOTH_TRACKER_SCHEMA,
    "device_tracker.google_maps": GOOGLE_MAPS_SCHEMA,
    "input_boolean": InputBooleanStorageCollection.CREATE_UPDATE_SCHEMA,
    "input_button": InputButtonStorageCollection.CREATE_UPDATE_SCHEMA,
    "input_datetime": DateTimeStorageCollection.CREATE_UPDATE_SCHEMA,
    "input_number": NumberStorageCollection.SCHEMA,
    "input_select": InputSelectStorageCollection.CREATE_UPDATE_SCHEMA,
    "input_text": InputTextStorageCollection.CREATE_UPDATE_SCHEMA,
    "media_player.universal": UNIVERSAL_MEDIA_PLAYER_SCHEMA,
    "mqtt.binary_sensor": MQTT_BINARY_SENSOR_SCHEMA,
    "mqtt.sensor": MQTT_SENSOR_SCHEMA,
    "rest_command": REST_COMMAND_SCHEMA,
    "script": SCRIPT_SCHEMA,
    "sensor.history_stats": SENSOR_HISTORY_STATS_SCHEMA,
    "sensor.london_air": SENSOR_LONDON_AIR_SCHEMA,
    "sensor.rest": SENSOR_REST_SCHEMA,
    "sensor.systemmonitor": SENSOR_SYSTEMMONITOR_SCHEMA,
    "template.binary_sensor": TEMPLATE_BINARY_SENSOR_SCHEMA,
    "template.sensor": TEMPLATE_SENSOR_SCHEMA,
}

for component_name, cc_package in component_modules.items():
    domain = CUSTOM_COMPONENTS_CONFIG[component_name].get("domain", component_name)

    DOMAIN_SCHEMA_MAP[domain] = cc_package["schema_var"]
    LOGGER.debug(
        "Loaded schema for custom component %r",
        domain,
    )


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]
    services: list[str]


KNOWN_ENTITIES: dict[str, KnownEntityType] = {
    "automation": {
        "names": [
            f"automation.{automation_file.stem}"
            for automation_file in (ENTITIES_DIR / "automation").rglob("*.yaml")
        ],
        "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
        "services": [
            "automation.reload",
            "automation.toggle",
            "automation.turn_off",
            "automation.turn_on",
        ],
    },
    "script": {
        "names": [
            f"script.{script_file.stem}"
            for script_file in (ENTITIES_DIR / "script").rglob("*.yaml")
        ],
        "name_pattern": re.compile(r"^script\.[a-z0-9_-]+$", flags=re.IGNORECASE),
        "services": [
            "script.reload",
            "script.toggle",
            "script.turn_off",
            "script.turn_on",
        ],
    },
}


__all__ = [
    "CUSTOM_VALIDATIONS",
    "DOMAIN_SCHEMA_MAP",
    "ENTITIES_DIR",
    "INTEGRATIONS_DIR",
    "REPO_PATH",
    "KNOWN_ENTITIES",
]

"""Constants for the configuration validator."""

# pylint: disable=wrong-import-position
# mypy: disable-error-code="import"
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import (
    PLATFORM_SCHEMA as BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.bluetooth_le_tracker.device_tracker import (
    PLATFORM_SCHEMA as BLUETOOTH_LE_TRACKER_SCHEMA,
)
from homeassistant.components.device_tracker import (
    PLATFORM_SCHEMA as DEVICE_TRACKER_SCHEMA,
)
from homeassistant.components.google_maps.device_tracker import (
    PLATFORM_SCHEMA as GOOGLE_MAPS_SCHEMA,
)
from homeassistant.components.history_stats.sensor import (
    PLATFORM_SCHEMA as SENSOR_HISTORY_STATS_SCHEMA,
)
from homeassistant.components.input_boolean import InputBooleanStorageCollection
from homeassistant.components.input_button import InputButtonStorageCollection
from homeassistant.components.input_datetime import DateTimeStorageCollection
from homeassistant.components.input_number import NumberStorageCollection
from homeassistant.components.input_select import InputSelectStorageCollection
from homeassistant.components.input_text import InputTextStorageCollection
from homeassistant.components.london_air.sensor import (
    PLATFORM_SCHEMA as SENSOR_LONDON_AIR_SCHEMA,
)
from homeassistant.components.mqtt.binary_sensor import (
    PLATFORM_SCHEMA_MODERN as MQTT_BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.mqtt.sensor import (
    PLATFORM_SCHEMA_MODERN as MQTT_SENSOR_SCHEMA,
)
from homeassistant.components.ping.binary_sensor import PLATFORM_SCHEMA as PING_SCHEMA
from homeassistant.components.rest.sensor import PLATFORM_SCHEMA as SENSOR_REST_SCHEMA
from homeassistant.components.rest_command import CONFIG_SCHEMA as REST_COMMAND_SCHEMA
from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA as SCRIPT_SCHEMA
from homeassistant.components.systemmonitor.sensor import (
    PLATFORM_SCHEMA as SENSOR_SYSTEMMONITOR_SCHEMA,
)
from homeassistant.components.template.binary_sensor import (
    BINARY_SENSOR_SCHEMA as TEMPLATE_BINARY_SENSOR_SCHEMA,
)
from homeassistant.components.template.cover import COVER_SCHEMA
from homeassistant.components.template.sensor import (
    SENSOR_SCHEMA as TEMPLATE_SENSOR_SCHEMA,
)
from homeassistant.components.universal.media_player import (
    PLATFORM_SCHEMA as UNIVERSAL_MEDIA_PLAYER_SCHEMA,
)

# This import order fixes an issue with `websocket_api.websocket_command` not being
# loaded correctly; not sure why
from homeassistant.components.automation.config import (  # isort:skip
    PLATFORM_SCHEMA as AUTOMATION_SCHEMA,
)

# Mock out packages that are not installable in a CI environment and would otherwise
# cause the custom component to fail to load
for package in (
    "bluetooth",
    "bluetooth._bluetooth",
):
    sys.modules[package] = MagicMock()


from homeassistant.components.bluetooth_tracker.device_tracker import (  # noqa: E402
    PLATFORM_SCHEMA as BLUETOOTH_TRACKER_SCHEMA,
)

REPO_PATH = Path(__file__).parents[2]

# Allow custom components to be loaded
sys.path.append(
    custom_components_path_str := (REPO_PATH / "custom_components").as_posix()
)

NO_SCHEMA_AVAILABLE = object()
try:
    from feedparser.sensor import PLATFORM_SCHEMA as SENSOR_FEEDPARSER_SCHEMA
    from var import CONFIG_SCHEMA as VAR_SCHEMA
except ImportError as exc:
    if not re.fullmatch(
        r"^No module named (?:'|\")([a-z_]+[a-z0-9_-]*)(?:'|\")$",
        str(exc),
        flags=re.IGNORECASE,
    ):
        raise

    SENSOR_FEEDPARSER_SCHEMA = NO_SCHEMA_AVAILABLE
    VAR_SCHEMA = NO_SCHEMA_AVAILABLE

    # raise FileNotFoundError(
    #     f"Directory `{custom_components_path_str}` not found; please create it"  # noqa: ERA001,E501  # pylint: disable=line-too-long
    #     " and try again"
    # ) from exc


VALIDATOR_CONFIGS = Path(__file__).parent / "validator_configs.json"
ENTITIES_DIR = REPO_PATH / "entities"
INTEGS_DIR = REPO_PATH / "integrations"

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
    "sensor.feedparser": SENSOR_FEEDPARSER_SCHEMA,
    "sensor.london_air": SENSOR_LONDON_AIR_SCHEMA,
    "sensor.rest": SENSOR_REST_SCHEMA,
    "sensor.systemmonitor": SENSOR_SYSTEMMONITOR_SCHEMA,
    "template.binary_sensor": TEMPLATE_BINARY_SENSOR_SCHEMA,
    "template.sensor": TEMPLATE_SENSOR_SCHEMA,
    "var": VAR_SCHEMA,
}

SCRIPT_NAMES = [
    f"script.{script_file.stem}"
    for script_file in (ENTITIES_DIR / "script").rglob("*.yaml")
]

SCRIPT_NAME_PATTERN = re.compile(r"script\.(?P<script_name>.*)")

SCRIPT_SERVICES = [
    "script.reload",
    "script.toggle",
    "script.turn_off",
    "script.turn_on",
]

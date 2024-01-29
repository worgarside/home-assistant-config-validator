# pylint: disable=cyclic-import
"""Constants for the configuration validator."""


from __future__ import annotations

import re
from argparse import ArgumentParser
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache
from json import loads
from os import getenv
from pathlib import Path
from typing import TypedDict

from wg_utilities.functions.json import JSONObj, JSONVal, process_list, traverse_dict

# Args
REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd().absolute().as_posix()))

parser = ArgumentParser(description="Custom Component Parser")

parser.add_argument(
    "-c",
    "--config-path",
    type=Path,
    required=False,
    help="Path to custom validations configuration file.",
    default=REPO_PATH / "config_validator.json",
)

args, _ = parser.parse_known_args()

CUSTOM_VALIDATIONS = loads(args.config_path.read_text())["customValidators"]

ENTITIES_DIR = REPO_PATH / "entities"
INTEGRATIONS_DIR = REPO_PATH / "integrations"
LOVELACE_DIR = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE = REPO_PATH / "ui-lovelace.yaml"


class Domain(StrEnum):
    AUTOMATION = "automation"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    CALENDAR = "calendar"
    CAMERA = "camera"
    COVER = "cover"
    DEVICE_TRACKER = "device_tracker"
    EVENT = "event"
    FAN = "fan"
    INPUT_BOOLEAN = "input_boolean"
    INPUT_BUTTON = "input_button"
    INPUT_DATETIME = "input_datetime"
    INPUT_NUMBER = "input_number"
    INPUT_SELECT = "input_select"
    INPUT_TEXT = "input_text"
    LIGHT = "light"
    MEDIA_PLAYER = "media_player"
    NUMBER = "number"
    PERSON = "person"
    REMOTE = "remote"
    SCRIPT = "script"
    SELECT = "select"
    SENSOR = "sensor"
    SHELL_COMMAND = "shell_command"
    SUN = "sun"
    SWITCH = "switch"
    UPDATE = "update"
    VACUUM = "vacuum"
    VAR = "var"
    WEATHER = "weather"
    ZONE = "zone"


KNOWN_SERVICES = {
    Domain.SCRIPT: (
        "reload",
        "turn_off",
        "turn_on",
    ),
}


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]


@lru_cache(maxsize=1)
def _get_known_entities() -> dict[Domain, KnownEntityType]:
    # pylint: disable=import-outside-toplevel
    from home_assistant_config_validator.ha_yaml_loader import load_yaml

    known_entities: dict[Domain, KnownEntityType] = {
        domain: {
            "names": [
                f"{domain}.{entity_file.stem}"
                for entity_file in (ENTITIES_DIR / domain).rglob("*.yaml")
            ],
            "name_pattern": re.compile(
                rf"^{domain}\.[a-z0-9_-]+$",
                flags=re.IGNORECASE,
            ),
        }
        for domain in (
            Domain.INPUT_BOOLEAN,
            Domain.INPUT_BUTTON,
            Domain.INPUT_DATETIME,
            Domain.INPUT_NUMBER,
            Domain.INPUT_SELECT,
            Domain.INPUT_TEXT,
            Domain.SCRIPT,
            Domain.SHELL_COMMAND,
            Domain.VAR,
        )
    }

    # Special case
    known_entities[Domain.AUTOMATION] = {
        "names": [
            ".".join((Domain.AUTOMATION, load_yaml(automation_file).get("id", "")))  # type: ignore[attr-defined]
            for automation_file in (ENTITIES_DIR / "automation").rglob("*.yaml")
        ],
        "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
    }

    return known_entities


def check_known_entity_usages(
    entity_yaml: JSONObj | Iterable[JSONVal],
    entity_keys: Iterable[str] = ("entity_id",),
) -> list[Exception]:
    """Check that all entities used in the config YAML are defined elsewhere.

    This only applies to the daomins which are solely defined in YAML files; any
    domains which have entities that can be defined through the
    Args:
        entity_yaml (JSONObj | Iterable[JSONVal]): The entity's YAML
        entity_keys (Iterable[str], optional): The keys to check for entities. Defaults
            to ("entity_id",).

    Returns:
        list[Exception]: A list of exceptions raised during validation
    """
    if "service" not in entity_keys:
        entity_keys = (*entity_keys, "service")

    known_entity_issues: list[Exception] = []

    def _callback(
        string: str,
        *,
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> str:
        nonlocal known_entity_issues

        _ = list_index

        if not dict_key or dict_key not in entity_keys:
            return string

        for domain, entity_comparands in _get_known_entities().items():
            if (not entity_comparands["name_pattern"].fullmatch(string)) or (
                dict_key == "service"
                and (
                    domain not in (Domain.SCRIPT, Domain.SHELL_COMMAND)
                    or string.split(".")[1] in KNOWN_SERVICES.get(domain, ())
                )
            ):
                continue

            if string not in entity_comparands["names"]:
                known_entity_issues.append(
                    ValueError(
                        " ".join(
                            (
                                domain.replace("_", " ").title(),
                                dict_key.replace("_", " ").title(),
                                string,
                                "is not defined",
                            ),
                        ),
                    ),
                )

        return string

    if isinstance(entity_yaml, dict):
        traverse_dict(
            entity_yaml,
            target_type=str,
            target_processor_func=_callback,  # type: ignore[arg-type]
            pass_on_fail=False,
        )
    elif isinstance(entity_yaml, list):
        process_list(
            entity_yaml,
            target_type=str,
            target_processor_func=_callback,  # type: ignore[arg-type]
            pass_on_fail=False,
        )
    else:
        known_entity_issues.append(
            TypeError(
                "Expected `entity_yaml` to be a dict or iterable, not"
                f" {type(entity_yaml)!r}",
            ),
        )

    return known_entity_issues


def format_output(
    data: (
        dict[str, dict[str, list[Exception]]]
        | dict[str, list[Exception]]
        | list[Exception]
    ),
    _indent: int = 0,
) -> str:
    """Format output for better readability.

    Args:
        data (dict | list): Data to format
        _indent (int, optional): Current indentation level. Defaults to 0.

    Returns:
        str: Formatted output; sort of YAML, sort of not

    Raises:
        TypeError: If `data` is not a dict or list
    """
    output = ""

    if isinstance(data, dict):
        for key, value in data.items():
            if _indent == 0:
                output += "\n"
            output += ("  " * _indent + str(key)) + "\n"
            output += format_output(value, _indent + 2)
    elif isinstance(data, list):
        for exc in data:
            output += ("  " * _indent) + f"{type(exc).__name__}: {exc!s}" + "\n"
    else:
        raise TypeError(f"Unexpected type {type(data).__name__}")  # noqa: TRY003

    return output


__all__ = [
    "CUSTOM_VALIDATIONS",
    "ENTITIES_DIR",
    "INTEGRATIONS_DIR",
    "REPO_PATH",
    "format_output",
]

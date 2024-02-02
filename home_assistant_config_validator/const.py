# pylint: disable=cyclic-import
"""Constants for the configuration validator."""


from __future__ import annotations

import re
from argparse import ArgumentParser
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache
from os import getenv
from pathlib import Path
from typing import Final, TypedDict

from wg_utilities.functions.json import (
    InvalidJsonObjectError,
    JSONArr,
    JSONObj,
    process_json_object,
)

REPO_PATH = Path(getenv("HA_REPO_PATH", Path.cwd().absolute().as_posix()))

# Args

parser = ArgumentParser(description="Custom Component Parser")

parser.add_argument(
    "-p",
    "--pch-config-path",
    type=Path,
    required=False,
    help="Path to custom validations configuration file.",
    default=REPO_PATH / "config_validator.json",
)

parser.add_argument(
    "-a",
    "--validate-all",
    action="store_true",
    help="Validate all packages (requires exactly one configuration per package).",
    default=False,
)

parser.add_argument(
    "-c",
    "--ha-config-path",
    type=Path,
    required=False,
    help="Path to Home Assistant configuration.yaml",
    default=REPO_PATH / "configuration.yaml",
)

args, _ = parser.parse_known_args()


PCH_CONFIG: Path = args.pch_config_path
VALIDATE_ALL_PACKAGES: bool = args.validate_all
HA_CONFIG: Path = args.ha_config_path

ENTITIES_DIR = REPO_PATH / "entities"
PACKAGES_DIR = REPO_PATH / "integrations"
LOVELACE_DIR = REPO_PATH / "lovelace"
LOVELACE_ROOT_FILE = REPO_PATH / "ui-lovelace.yaml"

NULL_PATH: Final[Path] = Path("/dev/null")


KNOWN_SERVICES = {
    "script": (
        "reload",
        "turn_off",
        "turn_on",
    ),
}


class ConfigurationType(StrEnum):
    """Enum for the different types of configurations."""

    DOCUMENTATION = "documentation"
    PARSER = "parser"
    VALIDATION = "validation"


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]


@lru_cache(maxsize=1)
def _get_known_entities() -> dict[str, KnownEntityType]:
    # pylint: disable=import-outside-toplevel
    from home_assistant_config_validator.ha_yaml_loader import load_yaml

    known_entities: dict[str, KnownEntityType] = {
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
            "input_boolean",
            "input_button",
            "input_datetime",
            "input_number",
            "input_select",
            "input_text",
            "script",
            "shell_command",
            "var",
        )
    }

    # Special case
    known_entities["automation"] = {
        "names": [
            ".".join(
                (
                    "automation",
                    str(load_yaml(automation_file, resolve_tags=False).get("id", "")),
                ),
            )
            for automation_file in (ENTITIES_DIR / "automation").rglob("*.yaml")
        ],
        "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
    }

    return known_entities


def check_known_entity_usages(
    entity_yaml: JSONObj | JSONArr,
    entity_keys: Iterable[str] = ("entity_id",),
) -> list[Exception]:
    """Check that all entities used in the config YAML are defined elsewhere.

    This only applies to the domains which are solely defined in YAML files; any
    domains which have entities that can be defined through the

    Args:
        entity_yaml (JSONObj | JSONArr): The entity's YAML
        entity_keys (Iterable[str], optional): The keys to check for entities. Defaults
            to ("entity_id",).

    Returns:
        list[Exception]: A list of exceptions raised during validation
    """
    if "service" not in entity_keys:
        entity_keys = (*entity_keys, "service")

    known_entity_issues: list[Exception] = []

    def _callback(
        value: str,
        *,
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> str:
        nonlocal known_entity_issues

        _ = list_index

        if not dict_key or dict_key not in entity_keys:
            return value

        for domain, entity_comparands in _get_known_entities().items():
            if (not entity_comparands["name_pattern"].fullmatch(value)) or (
                dict_key == "service"
                and (
                    domain not in ("script", "shell_command")
                    or value.split(".")[1] in KNOWN_SERVICES.get(domain, ())
                )
            ):
                continue

            if value not in entity_comparands["names"]:
                known_entity_issues.append(
                    ValueError(
                        " ".join(
                            (
                                domain.replace("_", " ").title(),
                                dict_key.replace("_", " ").title(),
                                value,
                                "is not defined",
                            ),
                        ),
                    ),
                )

        return value

    try:
        process_json_object(
            entity_yaml,
            target_type=str,
            target_processor_func=_callback,
            pass_on_fail=False,
        )
    except InvalidJsonObjectError as exc:
        known_entity_issues.append(exc)

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
            if not _indent:
                output += "\n"
            output += f"{' ' * _indent}{key}\n{format_output(value, _indent + 2)}"
    elif isinstance(data, list):
        for exc in data:
            output += f"{'  ' * _indent}{type(exc).__name__}: {exc!s}\n"
    else:
        raise TypeError(f"Unexpected type {type(data).__name__}")  # noqa: TRY003

    return output


__all__ = [
    "ENTITIES_DIR",
    "PACKAGES_DIR",
    "REPO_PATH",
    "format_output",
]

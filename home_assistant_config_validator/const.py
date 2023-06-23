"""Constants for the configuration validator."""


from __future__ import annotations

import re
from argparse import ArgumentParser
from collections.abc import Iterable
from json import loads
from pathlib import Path
from typing import TypedDict

from wg_utilities.functions.json import JSONObj, JSONVal, process_list, traverse_dict
from yaml import safe_load

# Args
REPO_PATH = Path().cwd()

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


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]


KNOWN_ENTITIES: dict[str, KnownEntityType] = {
    domain: {
        "names": [
            f"{domain}.{entity_file.stem}"
            for entity_file in (ENTITIES_DIR / domain).rglob("*.yaml")
        ],
        "name_pattern": re.compile(rf"^{domain}\.[a-z0-9_-]+$", flags=re.IGNORECASE),
    }
    for domain in (
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "script",
        "var",
    )
}

# Special case
KNOWN_ENTITIES["automation"] = {
    "names": [
        "automation." + safe_load(automation_file.read_text()).get("id", "")
        for automation_file in (ENTITIES_DIR / "automation").rglob("*.yaml")
    ],
    "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
}


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

        for domain, entity_comparands in KNOWN_ENTITIES.items():
            if (
                entity_comparands["name_pattern"].fullmatch(string)
                and string not in entity_comparands["names"]
            ):
                known_entity_issues.append(
                    ValueError(f"{domain.title()} {string!r} is not defined")
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
                f" {type(entity_yaml)!r}"
            )
        )

    return known_entity_issues


def format_output(
    data: dict[str, dict[str, list[Exception]]]
    | dict[str, list[Exception]]
    | list[Exception],
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
        raise TypeError(f"Unexpected type {type(data).__name__}")

    return output


__all__ = [
    "CUSTOM_VALIDATIONS",
    "ENTITIES_DIR",
    "INTEGRATIONS_DIR",
    "REPO_PATH",
    "KNOWN_ENTITIES",
    "format_output",
]

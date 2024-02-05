"""Helper functions for the Home Assistant Config Validator."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from jsonpath_ng import JSONPath, parse  # type: ignore[import-untyped]
from wg_utilities.functions.json import (
    InvalidJsonObjectError,
    JSONArr,
    JSONObj,
    process_json_object,
)

from . import Entity, const
from .exception import (
    InvalidConfigurationError,
    InvalidFieldTypeError,
    JsonPathNotFoundError,
)


class KnownEntityType(TypedDict):
    """Known entity type."""

    names: list[str]
    name_pattern: re.Pattern[str]


KNOWN_SERVICES = {
    "script": (
        "reload",
        "turn_off",
        "turn_on",
    ),
}


@lru_cache(maxsize=1)
def _get_known_entities() -> dict[str, KnownEntityType]:
    from home_assistant_config_validator.utils.ha_yaml_loader import load_yaml

    known_entities: dict[str, KnownEntityType] = {
        package: {
            "names": [
                f"{package}.{entity_file.stem}"
                for entity_file in (const.ENTITIES_DIR / package).rglob("*.yaml")
            ],
            "name_pattern": re.compile(
                rf"^{package}\.[a-z0-9_-]+$",
                flags=re.IGNORECASE,
            ),
        }
        for package in (
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
            for automation_file in (const.ENTITIES_DIR / "automation").rglob("*.yaml")
        ],
        "name_pattern": re.compile(r"^automation\.[a-z0-9_-]+$", flags=re.IGNORECASE),
    }

    return known_entities


def check_known_entity_usages(
    entity_yaml: JSONObj | JSONArr,
    entity_keys: Iterable[str] = ("entity_id",),
) -> list[InvalidConfigurationError]:
    """Check that all entities used in the config YAML are defined elsewhere.

    This only applies to the packages which are solely defined in YAML files; any
    packages which have entities that can be defined through the

    Args:
        entity_yaml (JSONObj | JSONArr): The entity's YAML
        entity_keys (Iterable[str], optional): The keys to check for entities. Defaults
            to ("entity_id",).

    Returns:
        list[Exception]: A list of exceptions raised during validation
    """
    if "service" not in entity_keys:
        entity_keys = (*entity_keys, "service")

    known_entity_issues: list[InvalidConfigurationError] = []

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

        for package, entity_comparands in _get_known_entities().items():
            if (not entity_comparands["name_pattern"].fullmatch(value)) or (
                dict_key == "service"
                and (
                    package not in ("script", "shell_command")
                    or value.split(".")[1] in KNOWN_SERVICES.get(package, ())
                )
            ):
                continue

            if value not in entity_comparands["names"]:
                known_entity_issues.append(
                    InvalidConfigurationError(
                        " ".join(
                            (
                                package.replace("_", " ").title(),
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
        known_entity_issues.append(
            InvalidFieldTypeError("<root>", exc.args[0], (dict, list)),
        )

    return known_entity_issues


def format_output(
    data: dict[str, dict[Path, list[InvalidConfigurationError]]],
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
    output_lines = []

    for pkg_name, issues in data.items():
        if not issues:
            continue

        package_lines = []

        for path, issue_list in issues.items():
            if not issue_list:
                continue

            if issue_lines := [
                f"{'  ' * (_indent + 4)}{type(exc).__name__}: {exc.fmt_msg}"
                for exc in issue_list
            ]:
                package_lines.append(
                    f"{' ' * (_indent + 2)}{path.relative_to(const.REPO_PATH)}",
                )
                package_lines.extend(issue_lines)

        if package_lines:
            output_lines.append(f"{' ' * _indent}{pkg_name}")
            output_lines.extend(package_lines)

    return "\n".join(output_lines)


NO_DEFAULT = object()


def get_json_value(
    json_obj: Entity | JSONObj | JSONArr,
    json_path: str,
    /,
    default: Any = NO_DEFAULT,
    valid_type: type[Any] = object,
) -> Any:
    """Get a value from a JSON object using a JSONPath expression.

    Args:
        json_obj (JSONObj | JSONArr): The JSON object to search
        json_path (str): The JSONPath expression
        default (Any, optional): The default value to return if the path is not found.
            Defaults to None.
        valid_type (type[Any], optional): The type of the value to return. Defaults to
            object.

    Returns:
        Any: The value at the JSONPath expression
    """
    if isinstance(json_obj, Entity):
        json_obj = json_obj.model_dump()

    values = [match.value for match in parse_jsonpath(json_path).find(json_obj)]

    if not values and default is not NO_DEFAULT:
        return default

    if not values:
        raise JsonPathNotFoundError(json_path)

    if not all(isinstance(value, valid_type) for value in values):
        raise InvalidFieldTypeError(json_path, values, valid_type)

    if len(values) == 1:
        return values[0]

    return values


@lru_cache
def parse_jsonpath(__jsonpath: str, /) -> JSONPath:
    """Parse a JSONPath expression."""
    return parse(__jsonpath)


__all__ = [
    "check_known_entity_usages",
    "format_output",
    "parse_jsonpath",
    "KnownEntityType",
]
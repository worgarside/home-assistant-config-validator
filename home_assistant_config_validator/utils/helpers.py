"""Helper functions for the Home Assistant Config Validator."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import Any, Literal, TypedDict

from wg_utilities.functions.json import (
    InvalidJsonObjectError,
    JSONArr,
    JSONObj,
    process_json_object,
)
from wg_utilities.loggers import add_stream_handler

from . import const, load_yaml
from .exception import (
    FixableConfigurationError,
    InvalidConfigurationError,
    InvalidFieldTypeError,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


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
                                f"`{value}`",
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

    def fmt_str(
        v: Any,
        /,
        *fmt_opts: Literal["bold", "italic", "red", "green", "amber", "blue", "cyan"],
    ) -> str:
        s = str(v)
        codes = {
            "bold": "\033[1m",
            "italic": "\033[3m",
            "red": "\033[31m",
            "green": "\033[32m",
            "amber": "\033[33m",
            "blue": "\033[34m",
            "cyan": "\033[36m",
            "reset": "\033[0m",
        }

        for fmt_opt in fmt_opts:
            s = f"{codes[fmt_opt]}{s!s}"

        if s.endswith(codes["reset"]):
            return s

        return f"{s}{codes['reset']}"

    fixable_indicator = f"[{fmt_str('*', 'cyan')}]"

    output_lines = []
    issue_count = {
        "fixed": 0,
        "fixable": 0,
        "total": 0,
    }
    name_pad = 0

    for pkg_name, issues in data.items():
        if not issues:
            continue

        package_lines = []

        for path, issue_list in issues.items():
            for exc in issue_list:
                if exc.fixed:
                    issue_count["fixed"] += 1
                    issue_count["total"] += 1
                    continue

                exc_typ = type(exc).__name__.removesuffix("Error")

                if isinstance(exc, FixableConfigurationError):
                    issue_count["fixable"] += 1
                    exc_typ = f"{fmt_str(exc_typ, 'amber', 'bold')} {fixable_indicator}"
                else:
                    exc_typ = fmt_str(exc_typ, "red", "bold")

                issue_line = " ".join(
                    (
                        fmt_str(path.relative_to(const.REPO_PATH), "bold")
                        + fmt_str(":", "cyan"),
                        exc_typ,
                        exc.fmt_msg,
                    ),
                )

                package_lines.append((pkg_name, issue_line))
                issue_count["total"] += 1

        if package_lines:
            name_pad = max(
                name_pad,
                len(pkg_name) + 1,
            )
            output_lines.extend(package_lines)

    summary_line = fmt_str(
        " ".join(
            (
                "Found",
                fmt_str(
                    str(issue_count["total"]),
                    (
                        "amber"
                        if (issue_count["total"] - issue_count["fixed"])
                        < 10  # noqa: PLR2004
                        else "red"
                    ),
                ),
                "issues",
            ),
        ),
        "bold",
    )

    if issue_count["fixed"]:
        summary_line += f", fixed {fmt_str(issue_count['fixed'], 'bold', 'green')} 🎉"

    if issue_count["fixable"]:
        summary_line += f"\n{fixable_indicator} {fmt_str(issue_count['fixable'], 'bold', 'green')} fixable with the `--fix` option"  # noqa: E501

    return "\n" + (
        "\n".join(
            f"{fmt_str(f'{pkg_name:<{name_pad}}', 'bold', 'italic', 'blue')} {issue_line}"
            for pkg_name, issue_line in output_lines
        )
        + f"\n\n{summary_line}\n"
    )


__all__ = [
    "check_known_entity_usages",
    "format_output",
    "KnownEntityType",
]

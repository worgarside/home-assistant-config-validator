"""Validate Home Assistant Lovelace configuration."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from wg_utilities.functions.json import (
    InvalidJsonObjectError,
    JSONArr,
    JSONObj,
    JSONVal,
    process_json_object,
    traverse_dict,
)

from home_assistant_config_validator.utils import (
    DeclutteringTemplateNotFoundError,
    InvalidConfigurationError,
    InvalidFieldTypeError,
    Secret,
    Tag,
    UnusedFileError,
    args,
    const,
    format_output,
    load_yaml,
    subclasses_recursive,
)


class LovelaceConfig(TypedDict):
    """Type definition for the entire Lovelace Config."""

    title: str
    decluttering_templates: dict[str, JSONVal]
    views: list[JSONObj]


class DashboardConfig(LovelaceConfig):
    """Type definition for a single dashboard."""

    icon: str
    path: str


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
                for entity_file in (const.ENTITIES_DIR / package).rglob(const.GLOB_PATTERN)
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
                    str(load_yaml(automation_file, resolve_tags=False)[0].get("id", "")),
                ),
            )
            for automation_file in (const.ENTITIES_DIR / "automation").rglob(const.GLOB_PATTERN)
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


def create_callback(
    root_file: Path,
    imported_files: list[Path],
) -> Callable[
    [Tag[Any], str | None, int | None],
    JSONObj | Iterable[JSONVal] | JSONVal,
]:
    """Create a callback for custom YAML tags.

    Args:
        root_file (Path): the file from which the import is being made
        imported_files (list[Path]): list of imported files, modified in place

    Returns:
        Callable: Callback to get the values of custom YAML tags.
    """
    load_data_relative_to = root_file.parent if root_file.is_file() else root_file

    def _callback(
        yaml_tag: Tag[Any],
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> JSONObj | Iterable[JSONVal] | JSONVal:
        """Callback for custom YAML tags.

        Args:
            yaml_tag (_CustomTag): Custom YAML tag.
            dict_key (str | None, optional): Dictionary key. Defaults to None.
            list_index (int | None, optional): List index. Defaults to None.

        Returns:
            JSONObj | Iterable[JSONVal]: If it's a secret, return the fake value.
                Otherwise, return the loaded YAML.
        """
        _ = dict_key, list_index

        if isinstance(yaml_tag, Secret):
            return yaml_tag.get_fake_value()

        import_path = (
            load_data_relative_to / yaml_tag.path  # type: ignore[attr-defined]
        ).resolve()

        imported_files.append(import_path.relative_to(const.REPO_PATH))

        return load_yaml(import_path, resolve_tags=False)

    return _callback


def load_lovelace_config() -> tuple[LovelaceConfig, list[Path]]:
    """Load the entire* Lovelace config.

    * Still working on it being the full, perfect config -.-

    Returns:
        tuple[LovelaceConfig, list[Path]]: The Lovelace config and a list of imported
            files for later reference.
    """
    lovelace_config: LovelaceConfig
    lovelace_config, _ = load_yaml(  # type: ignore[assignment]
        const.LOVELACE_ROOT_FILE,
        resolve_tags=False,
    )

    imported_files: list[Path] = []

    target_types = tuple(subclasses_recursive(Tag))

    traverse_dict(
        lovelace_config,  # type: ignore[arg-type]
        target_type=target_types,
        target_processor_func=create_callback(
            const.LOVELACE_ROOT_FILE,
            imported_files,
        ),
        pass_on_fail=False,
    )

    for dashboard_file in (const.LOVELACE_DIR / "dashboards").glob(const.GLOB_PATTERN):
        dashboard_yaml: DashboardConfig
        dashboard_yaml, _ = load_yaml(  # type: ignore[assignment]
            dashboard_file,
            resolve_tags=False,
        )

        traverse_dict(
            dashboard_yaml,  # type: ignore[arg-type]
            target_type=target_types,
            target_processor_func=create_callback(
                dashboard_file,
                imported_files,
            ),
            pass_on_fail=False,
        )

        lovelace_config["views"].extend(dashboard_yaml.get("views", []))

    return lovelace_config, imported_files


def validate_decluttering_templates(
    lovelace_file_yaml: JSONObj,
    lovelace_config: LovelaceConfig,
) -> list[InvalidConfigurationError]:
    """Validate that all referenced decluttering templates are defined.

    Args:
        lovelace_file_yaml (JSONObj): The YAML of a Lovelace file
        lovelace_config (LovelaceConfig): The entire Lovelace config

    Returns:
        list[Exception]: A list of exceptions raised during validation
    """
    dc_template_issues: list[InvalidConfigurationError] = []

    def _callback(
        string: str,
        *,
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> str:
        """Callback to validate decluttering template references.

        Every string will be sent to this callback, so the `dict_key` is used to
        filter out everything other than the `template` key (plus any Jinja templates).

        Args:
            string (str): Any string found within the YAML
            dict_key (str | None, optional): The key of the given value
            list_index (int | None, optional): The index of the given value (unused)

        Returns:
            str: The original string
        """
        nonlocal dc_template_issues

        _ = list_index

        if dict_key != "template" or (
            # False positives from actual templates
            string.lstrip().startswith(("{{", "[[")) and string.rstrip().endswith(("}}", "]]"))
        ):
            return string

        if string not in lovelace_config["decluttering_templates"]:
            dc_template_issues.append(
                DeclutteringTemplateNotFoundError(string),
            )

        return string

    traverse_dict(
        lovelace_file_yaml,
        target_type=str,
        target_processor_func=_callback,  # type: ignore[arg-type]
        pass_on_fail=False,
    )

    return dc_template_issues


def main() -> None:
    """Validate all entities."""
    args.parse_arguments()

    lovelace_config, imported_files = load_lovelace_config()

    all_lovelace_files = [
        *list(const.LOVELACE_DIR.rglob(const.GLOB_PATTERN)),
        const.LOVELACE_ROOT_FILE,
    ]

    # Unused files
    all_issues: defaultdict[Path, list[InvalidConfigurationError]] = defaultdict(list)

    # Use of unknown entities (that should be known)
    for ll_file in all_lovelace_files:
        if ll_file.relative_to(const.REPO_PATH) not in [
            *imported_files,
            const.LOVELACE_ROOT_FILE.relative_to(const.REPO_PATH),
        ] and ll_file.parent.name not in ("dashboards", "archive"):
            all_issues[ll_file].append(UnusedFileError(ll_file))

        lovelace_file_yaml: JSONObj
        lovelace_file_yaml, _ = load_yaml(ll_file, resolve_tags=False)

        if bad_entity_usages := check_known_entity_usages(
            lovelace_file_yaml,
            entity_keys=("entity", "entity_id", "service"),
        ):
            all_issues[ll_file].extend(bad_entity_usages)

        # Use of unknown decluttering templates
        if dc_template_issues := validate_decluttering_templates(
            lovelace_file_yaml,
            lovelace_config,
        ):
            all_issues[ll_file].extend(dc_template_issues)

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output({"lovelace": all_issues}))


if __name__ == "__main__":
    main()

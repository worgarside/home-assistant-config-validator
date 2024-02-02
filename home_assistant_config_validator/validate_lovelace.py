"""Validate Home Assistant Lovelace configuration."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypedDict

from wg_utilities.functions.json import JSONObj, JSONVal, traverse_dict

from home_assistant_config_validator.const import (
    LOVELACE_DIR,
    LOVELACE_ROOT_FILE,
    REPO_PATH,
    check_known_entity_usages,
    format_output,
)
from home_assistant_config_validator.ha_yaml_loader import (
    Secret,
    Tag,
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

        imported_files.append(import_path.relative_to(REPO_PATH))

        return load_yaml(import_path, resolve_tags=False)

    return _callback


def load_lovelace_config() -> tuple[LovelaceConfig, list[Path]]:
    """Load the entire* Lovelace config.

    * Still working on it being the full, perfect config -.-

    Returns:
        tuple[LovelaceConfig, list[Path]]: The Lovelace config and a list of imported
            files for later reference.
    """
    lovelace_config: LovelaceConfig = load_yaml(  # type: ignore[assignment]
        LOVELACE_ROOT_FILE,
        resolve_tags=False,
    )

    imported_files: list[Path] = []

    target_types = tuple(subclasses_recursive(Tag))

    traverse_dict(
        lovelace_config,  # type: ignore[arg-type]
        target_type=target_types,
        target_processor_func=create_callback(  # type: ignore[arg-type]
            LOVELACE_ROOT_FILE,
            imported_files,
        ),
        pass_on_fail=False,
    )

    for dashboard_file in (LOVELACE_DIR / "dashboards").glob("*.yaml"):
        dashboard_yaml: DashboardConfig = load_yaml(  # type: ignore[assignment]
            dashboard_file,
            resolve_tags=False,
        )

        traverse_dict(
            dashboard_yaml,  # type: ignore[arg-type]
            target_type=target_types,
            target_processor_func=create_callback(  # type: ignore[arg-type]
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
) -> list[Exception]:
    """Validate that all referenced decluttering templates are defined.

    Args:
        lovelace_file_yaml (JSONObj): The YAML of a Lovelace file
        lovelace_config (LovelaceConfig): The entire Lovelace config

    Returns:
        list[Exception]: A list of exceptions raised during validation
    """
    dc_template_issues: list[Exception] = []

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
            string.lstrip().startswith(("{{", "[["))
            and string.rstrip().endswith(("}}", "]]"))
        ):
            return string

        if string not in lovelace_config["decluttering_templates"]:
            dc_template_issues.append(
                KeyError(f"Unknown decluttering template: {string}"),
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
    lovelace_config, imported_files = load_lovelace_config()

    all_lovelace_files = [
        *list(LOVELACE_DIR.rglob("*.yaml")),
        REPO_PATH / "ui-lovelace.yaml",
    ]

    # Unused files
    all_issues: dict[str, list[Exception]] = {
        f.relative_to(REPO_PATH).as_posix(): [
            FileExistsError("File is not used in lovelace config."),
        ]
        for f in all_lovelace_files
        if f.relative_to(REPO_PATH)
        not in [*imported_files, LOVELACE_ROOT_FILE.relative_to(REPO_PATH)]
        and f.parent.name not in ("dashboards", "archive")
    }

    # Use of unknown entities (that should be known)
    for ll_file in all_lovelace_files:
        lovelace_file_yaml: JSONObj = load_yaml(ll_file, resolve_tags=False)
        issues_key = ll_file.relative_to(REPO_PATH).as_posix()

        if bad_entity_usages := check_known_entity_usages(
            lovelace_file_yaml,
            entity_keys=("entity", "entity_id", "service"),
        ):
            all_issues.setdefault(issues_key, []).extend(bad_entity_usages)

        # Use of unknown decluttering templates
        if dc_template_issues := validate_decluttering_templates(
            lovelace_file_yaml,
            lovelace_config,
        ):
            all_issues.setdefault(issues_key, []).extend(dc_template_issues)

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output(all_issues))


if __name__ == "__main__":
    main()

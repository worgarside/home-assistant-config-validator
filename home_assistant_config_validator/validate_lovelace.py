"""Validate Home Assistant Lovelace configuration."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict

from wg_utilities.functions.json import (
    JSONObj,
    traverse_dict,
)

from home_assistant_config_validator.models import Package
from home_assistant_config_validator.models.config import ValidationConfig
from home_assistant_config_validator.utils import (
    DeclutteringTemplateNotFoundError,
    Include,
    InvalidConfigurationError,
    Secret,
    UnusedFileError,
    args,
    const,
    format_output,
    load_yaml,
)
from home_assistant_config_validator.utils.exception import InvalidDependencyError


class Card(TypedDict):
    """Basic type definition for a single Lovelace card."""

    type: str


class DeclutteringTemplate(TypedDict):
    """Type definition for a single decluttering template."""

    card: Card
    default: list[dict[str, object]]


class View(TypedDict):
    """Type definition for a single Lovelace view."""

    cards: list[Card]
    icon: str
    path: str
    title: str


class LovelaceConfig(TypedDict, total=False):
    """Type definition for the entire Lovelace Config."""

    title: str | Secret
    decluttering_templates: Include | dict[str, DeclutteringTemplate]
    views: list[Include] | list[View]


class DashboardConfig(LovelaceConfig):
    """Type definition for a single dashboard."""

    icon: str
    path: Path


def check_known_entity_usages(
    *,
    all_issues: dict[Path, list[InvalidConfigurationError]],
    config: JSONObj,
    file: Path,
) -> None:
    """Check that all entities used in the config YAML are defined elsewhere.

    This only applies to the packages which are solely defined in YAML files; any
    packages which have entities that can be defined through the GUI are not checked.
    """
    entity_ids: set[tuple[str, str]] = set()
    cb = const.create_entity_id_check_callback(entity_ids)
    traverse_dict(
        config,
        target_type=str,
        target_processor_func=cb,
    )

    while entity_ids:
        dict_key, entity_id = entity_ids.pop()

        if dict_key not in ("entity", "entity_id", "service"):
            continue

        if entity_id not in ValidationConfig.KNOWN_ENTITY_IDS:
            all_issues[file].append(InvalidDependencyError(dict_key, entity_id))


def validate_decluttering_templates(
    *,
    all_issues: dict[Path, list[InvalidConfigurationError]],
    config: JSONObj,
    decluttering_templates: Include | dict[str, DeclutteringTemplate],
    file: Path,
) -> None:
    """Validate that all referenced decluttering templates are defined."""

    def _cb(
        value: str,
        *,
        dict_key: str | None = None,
        **_: Any,
    ) -> str:
        if dict_key != "template" or (
            # False positives from actual templates
            value.lstrip().startswith(("{{", "[[")) and value.rstrip().endswith(("}}", "]]"))
        ):
            return value

        if value not in decluttering_templates:
            all_issues[file].append(
                DeclutteringTemplateNotFoundError(value),
            )

        return value

    traverse_dict(
        config,
        target_type=str,
        target_processor_func=_cb,
        pass_on_fail=False,
    )


def get_unused_files(
    *,
    all_issues: dict[Path, list[InvalidConfigurationError]],
    lovelace_config: LovelaceConfig,
    package_config: JSONObj,
) -> list[tuple[Path, DashboardConfig]]:
    """Get a list of files which areen't used anywhere in the Lovelace configuration."""
    all_lovelace_files = [
        *list(const.LOVELACE_DIR.rglob(const.GLOB_PATTERN)),
        const.LOVELACE_ROOT_FILE,
    ]

    included_files: list[Path] = []

    def _cb(
        value: Include,
        *,
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> JSONObj:
        _ = dict_key, list_index
        included_files.append(value.absolute_path)
        return value.resolve()

    traverse_dict(
        lovelace_config,  # type: ignore[arg-type]
        target_type=Include,
        target_processor_func=_cb,
        pass_on_fail=False,
    )
    traverse_dict(
        package_config,
        target_type=Include,
        target_processor_func=_cb,
        pass_on_fail=False,
    )

    dashboards = []
    db_config: dict[str, str]
    for db_config in package_config["lovelace"]["dashboards"].values():  # type: ignore[call-overload,index,union-attr]
        dashboard_file = const.REPO_PATH.joinpath(db_config["filename"])
        included_files.append(dashboard_file.resolve())
        db_yaml, _ = load_yaml(dashboard_file, validate_content_type=JSONObj)
        traverse_dict(
            db_yaml,
            target_type=Include,
            target_processor_func=_cb,
            pass_on_fail=False,
        )

        dashboards.append(
            (
                dashboard_file,
                DashboardConfig(**db_yaml),  # type: ignore[typeddict-item]
            ),
        )

    for file in all_lovelace_files:
        if (
            file not in included_files
            and not file.is_relative_to(const.LOVELACE_ARCHIVE_DIR)
            and file != const.LOVELACE_ROOT_FILE
        ):
            all_issues[file].append(UnusedFileError(file))

    return dashboards


def main() -> None:
    """Validate all entities."""
    args.parse_arguments(validate_all_packages_override=False)

    llc, _ = load_yaml(const.LOVELACE_ROOT_FILE)

    pkg = Package.by_name("lovelace")
    ValidationConfig.get_for_package(pkg)

    lovelace_config = LovelaceConfig(**llc)  # type: ignore[typeddict-item]
    package_config, _ = load_yaml(pkg.root_file, validate_content_type=JSONObj)

    all_issues: defaultdict[Path, list[InvalidConfigurationError]] = defaultdict(list)

    dashboards = get_unused_files(
        all_issues=all_issues,
        lovelace_config=lovelace_config,
        package_config=package_config,
    )

    for file, config in (
        (const.LOVELACE_ROOT_FILE, lovelace_config),
        (pkg.root_file, package_config),
        *dashboards,
    ):
        validate_decluttering_templates(
            all_issues=all_issues,
            config=config,
            decluttering_templates=lovelace_config["decluttering_templates"],
            file=file,
        )
        check_known_entity_usages(
            all_issues=all_issues,
            config=config,
            file=file,
        )

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output({"lovelace": all_issues}))


if __name__ == "__main__":
    main()

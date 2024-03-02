"""Validate Home Assistant Lovelace configuration."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Final, Literal, TypedDict

from jinja2.defaults import (
    BLOCK_END_STRING,
    BLOCK_START_STRING,
    COMMENT_END_STRING,
    COMMENT_START_STRING,
    VARIABLE_END_STRING,
    VARIABLE_START_STRING,
)
from wg_utilities.helpers.mixin.instance_cache import CacheIdNotFoundError
from wg_utilities.helpers.processor import JProc

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
    entity_id_check_callback,
    format_output,
    load_yaml,
)
from home_assistant_config_validator.utils.exception import InvalidDependencyError

VAR_TEMPLATE_BLOCK_START_STRING: Final[Literal["[["]] = "[["
VAR_TEMPLATE_BLOCK_END_STRING: Final[Literal["]]"]] = "]]"


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
    config: dict[str, object],
    file: Path,
) -> None:
    """Check that all entities used in the config YAML are defined elsewhere.

    This only applies to the packages which are solely defined in YAML files; any
    packages which have entities that can be defined through the GUI are not checked.
    """
    entity_ids: set[tuple[str, str]] = set()

    try:
        jproc = JProc.from_cache("entity_id_check")
    except CacheIdNotFoundError:
        jproc = JProc(
            {str: entity_id_check_callback},
            identifier="entity_id_check",
            process_pydantic_extra_fields=True,
        )

    jproc.process(config, entity_ids=entity_ids)

    while entity_ids:
        dict_key, entity_id = entity_ids.pop()

        if dict_key not in ("entity", "entity_id", "service"):
            continue

        if entity_id not in ValidationConfig.KNOWN_ENTITY_IDS:
            all_issues[file].append(InvalidDependencyError(dict_key, entity_id))


def validate_decluttering_templates(
    *,
    all_issues: dict[Path, list[InvalidConfigurationError]],
    config: dict[str, object],
    lovelace_config: LovelaceConfig,
    file: Path,
) -> None:
    """Validate that all referenced decluttering templates are defined."""
    decluttering_templates: Include | dict[str, DeclutteringTemplate] = lovelace_config[
        "decluttering_templates"
    ]

    @JProc.callback(allow_mutation=False)
    def _val_decluttering_templates(
        _value_: str,
    ) -> None:
        all_issues[file].append(DeclutteringTemplateNotFoundError(_value_))

    try:
        jproc = JProc.from_cache("validate_decluttering_templates")
    except CacheIdNotFoundError:
        jproc = JProc(
            {
                str: JProc.cb(
                    _val_decluttering_templates,
                    lambda item, loc: (
                        loc == "template"
                        # False positives from actual templates
                        and not item.lstrip().startswith(
                            (
                                BLOCK_START_STRING,
                                COMMENT_START_STRING,
                                VARIABLE_START_STRING,
                                VAR_TEMPLATE_BLOCK_START_STRING,
                            ),
                        )
                        and not item.rstrip().endswith(
                            (
                                BLOCK_END_STRING,
                                COMMENT_END_STRING,
                                VARIABLE_END_STRING,
                                VAR_TEMPLATE_BLOCK_END_STRING,
                            ),
                        )
                        and item not in decluttering_templates
                    ),
                ),
            },
            identifier="validate_decluttering_templates",
            process_pydantic_extra_fields=True,
        )

    jproc.process(config)


@JProc.callback()
def _get_unused_files_cb(
    _value_: Include,
    included_files: list[Path],
) -> dict[str, object]:
    included_files.append(_value_.absolute_path)
    return _value_.resolve()


def get_unused_files(
    *,
    all_issues: dict[Path, list[InvalidConfigurationError]],
    lovelace_config: LovelaceConfig,
    package_config: dict[str, object],
) -> list[tuple[Path, DashboardConfig]]:
    """Get a list of files which areen't used anywhere in the Lovelace configuration."""
    all_lovelace_files = [
        *list(const.LOVELACE_DIR.rglob(const.GLOB_PATTERN)),
        const.LOVELACE_ROOT_FILE,
    ]

    included_files: list[Path] = []

    try:
        jproc = JProc.from_cache("get_unused_files")
    except CacheIdNotFoundError:
        jproc = JProc(
            {Include: _get_unused_files_cb},
            identifier="get_unused_files",
            process_pydantic_extra_fields=True,
        )

    jproc.process(lovelace_config, included_files=included_files)
    jproc.process(package_config, included_files=included_files)

    dashboards = []
    db_config: dict[str, str]
    for db_config in package_config["lovelace"]["dashboards"].values():  # type: ignore[index]
        dashboard_file = const.REPO_PATH.joinpath(db_config["filename"]).resolve()
        included_files.append(dashboard_file)
        db_yaml, _ = load_yaml(dashboard_file, validate_content_type=dict[str, object])

        jproc.process(db_yaml, included_files=included_files)

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


def main() -> int:
    """Validate all entities."""
    args.parse_arguments(validate_all_packages_override=False)
    llc, _ = load_yaml(const.LOVELACE_ROOT_FILE)

    pkg = Package.by_name("lovelace")
    ValidationConfig.get_for_package(pkg)

    lovelace_config = LovelaceConfig(**llc)  # type: ignore[typeddict-item]
    package_config, _ = load_yaml(pkg.root_file, validate_content_type=dict[str, object])

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
            lovelace_config=lovelace_config,
            file=file,
        )
        check_known_entity_usages(
            all_issues=all_issues,
            config=config,
            file=file,
        )

    if all_issues:
        print(format_output({"lovelace": all_issues}), file=sys.stderr)

        return const.EXIT_1 and 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

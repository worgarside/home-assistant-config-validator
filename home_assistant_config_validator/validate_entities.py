"""Validate Home Assistant configurations."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from re import sub
from typing import TypedDict

from wg_utilities.functions.json import JSONObj, JSONVal

from .const import (
    CUSTOM_VALIDATIONS,
    ENTITIES_DIR,
    REPO_PATH,
    check_known_entity_usages,
    format_output,
)
from .ha_yaml_loader import load_yaml


def replace_non_alphanumeric(string: str, ignore_chars: str = "") -> str:
    """Convert a string to be alphanumeric and snake_case.

    Leading underscores are removed, and double underscores are replaced with a single
    underscore. Ignores values within `string` that are also in `ignore_strings`.

    Args:
        string (str): The string to convert
        ignore_chars (str, optional): Other characters to ignore. Defaults to None.

    Returns:
        str: The converted string
    """
    return (
        sub(rf"[^a-zA-Z0-9{ignore_chars}]", "_", string)
        .lower()
        .removeprefix("_")
        .replace("__", "_")
    )


class ShouldMatchFilepathItem(TypedDict):
    """Type definition for a single item in the `should_match_filepath` list."""

    field: str
    separator: str
    prefix: str
    ignore_chars: str
    include_domain_dir: bool


@dataclass
class ValidatorConfig:
    """Dataclass for a domain's validator configuration."""

    domain: str

    should_match_filename: list[str] = dataclass_field(default_factory=list)
    should_match_filepath: list[ShouldMatchFilepathItem] = dataclass_field(
        default_factory=list
    )
    should_be_equal: list[tuple[str, ...]] = dataclass_field(default_factory=list)
    should_exist: list[str] = dataclass_field(default_factory=list)
    should_be_hardcoded: dict[str, JSONVal] = dataclass_field(default_factory=dict)

    _domain_issues: dict[str, list[Exception]] = dataclass_field(default_factory=dict)

    def run_custom_validations(
        self,
        *,
        domain_dir_path: Path,
        file_path: Path,
        entity_yaml: JSONObj,
    ) -> list[Exception]:
        # pylint: disable=too-many-locals
        """Run all validations on the given entity.

        Args:
            domain_dir_path (Path): The domain's directory path
            file_path (Path): The entity's file path
            entity_yaml (JSONObj): The entity's YAML

        Returns:
            list[Exception]: A list of exceptions raised during validation
        """
        custom_issues: list[Exception] = []

        for smfn_field in self.should_match_filename:
            # Some entity types (e.g. sensor.systemmonitor) don't have certain fields
            # (e.g. name). If it's required, it'll get picked up in the other checks.
            if smfn_field not in entity_yaml:
                continue

            if (
                fmt_value := replace_non_alphanumeric(
                    field_value := entity_yaml.get(  # type: ignore[arg-type]
                        smfn_field, ""
                    )
                )
            ) != file_path.with_suffix("").name.lower():
                custom_issues.append(
                    ValueError(
                        f"`{smfn_field}: {field_value!s}` ({fmt_value=}) should match"
                        " file name"
                    )
                )

        for field_name_1, field_name_2 in self.should_be_equal:
            if (field_value_1 := entity_yaml.get(field_name_1)) != (
                field_value_2 := entity_yaml.get(field_name_2)
            ):
                custom_issues.append(
                    ValueError(
                        f"`{field_name_1}: {field_value_1!s}` should match"
                        f" `{field_name_2}: {field_value_2!s}`"
                    )
                )

        for smfp_config in self.should_match_filepath:
            if smfp_config.get("include_domain_dir", False):
                filepath_parts = (
                    file_path.with_suffix("").relative_to(domain_dir_path.parent).parts
                )
            else:
                filepath_parts = (
                    file_path.with_suffix("").relative_to(domain_dir_path).parts
                )

            expected_value = smfp_config.get("prefix", "") + smfp_config[
                "separator"
            ].join(filepath_parts)

            actual_value = replace_non_alphanumeric(
                entity_yaml.get(smfp_config["field"], ""),  # type: ignore[arg-type]
                ignore_chars=smfp_config.get("separator", ""),
            )
            if expected_value != actual_value:
                custom_issues.append(
                    ValueError(
                        f"`{smfp_config['field']}: {(actual_value or 'null')!s}`"
                        f"should match file path: `{expected_value!s}`"
                    )
                )

        for se_field in self.should_exist:
            if se_field not in entity_yaml:
                custom_issues.append(ValueError(f"`{se_field}` should be defined"))

        for sbh_field, hardcoded_value in self.should_be_hardcoded.items():
            if (field_value := entity_yaml.get(sbh_field)) != hardcoded_value:
                custom_issues.append(
                    ValueError(
                        f"`{sbh_field}: {field_value!s}` should be hardcoded as"
                        f" {hardcoded_value!r}"
                    )
                )

        return custom_issues

    def validate_domain(self: ValidatorConfig) -> None:
        """Validate a domain's YAML files.

        Each file is validated against Home Assistant's schema for that domain, and
        against the domain's validator configuration. Custom validation is done by
        evaluating the JSON configuration adjacent to this module and applying each
        validation rule to the entity.

        Invalid files are added to the `self._domain_issues` dict, with the file path
        as the key and a list of exceptions as the value.
        """

        domain_dir_path = ENTITIES_DIR / self.domain

        if not domain_dir_path.is_dir():
            self._domain_issues["root"] = [
                ValueError(
                    f"Directory {domain_dir_path.relative_to(REPO_PATH)} does not exist"
                )
            ]

        for file in domain_dir_path.rglob("*.yaml"):
            entity_yaml: JSONObj | Iterable[JSONVal] = load_yaml(file)

            file_issues: list[Exception] = self.run_custom_validations(
                domain_dir_path=domain_dir_path,
                file_path=file,
                entity_yaml=entity_yaml,  # type: ignore[arg-type]
            )

            file_issues.extend(check_known_entity_usages(entity_yaml))

            if file_issues:
                self._domain_issues[
                    file.relative_to(REPO_PATH).as_posix()
                ] = file_issues

    @property
    def domain_issues(self: ValidatorConfig) -> dict[str, list[Exception]]:
        """Return a list of all issues found in the domain.

        Returns:
            dict[str, list[Exception]]: A list of all issues found in the domain
        """
        return self._domain_issues


def main() -> None:
    """Validate all entities."""

    custom_validation_configs = {
        domain: ValidatorConfig(domain=domain, **json_config)
        for domain, json_config in CUSTOM_VALIDATIONS.items()
    }

    all_issues: dict[str, dict[str, list[Exception]]] = {}

    for domain_dir in sorted(ENTITIES_DIR.iterdir()):
        v_config = custom_validation_configs.get(
            domain_dir.name, ValidatorConfig(domain=domain_dir.name)
        )

        v_config.validate_domain()

        if v_config.domain_issues:
            all_issues[domain_dir.name] = v_config.domain_issues

    if not all_issues:
        sys.exit(0)

    sys.exit(format_output(all_issues))


if __name__ == "__main__":
    main()

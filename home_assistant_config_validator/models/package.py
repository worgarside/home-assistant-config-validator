"""Models for packages."""

from __future__ import annotations

from collections.abc import Generator, Iterable
from dataclasses import dataclass
from functools import cached_property
from logging import getLogger
from pathlib import Path, PurePath
from typing import Any, ClassVar, Self

from wg_utilities.functions.json import JSONObj, process_json_object
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.utils import (
    EntityGenerator,
    PackageDefinitionError,
    PackageNotFoundError,
    TagWithPath,
    const,
    load_yaml,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)


@dataclass
class Package:
    """A package of entities.

    https://www.home-assistant.io/docs/configuration/packages
    """

    INSTANCES: ClassVar[dict[str, Self]] = {}

    pkg_name: str
    name: str
    root_file: Path
    tag_paths: Iterable[PurePath]
    entity_generators: list[EntityGenerator]

    def __post_init__(self: Self) -> None:
        """Add the instance to the instances dict."""
        if (instance := self.INSTANCES.get(self.pkg_name)) is None:
            self.INSTANCES[self.pkg_name] = self
        elif instance != self:
            raise PackageDefinitionError(
                const.PACKAGES_DIR.joinpath(self.pkg_name),
                f"Can't have multiple packages with same name ({self.pkg_name})",
            )

    def get_tag_path(self, entity_path: Path) -> Path:
        """Get the path from the tag which includes this entity."""
        ancestors = [
            self.root_file.parent.joinpath(path).resolve()
            for path in self.tag_paths
            if entity_path.is_relative_to(path)
        ]

        return sorted(ancestors, key=lambda x: len(x.parts), reverse=True)[0]

    @cached_property
    def tag_paths_highest_common_ancestor(self) -> Path:
        """Get the highest common ancestor of all tag paths."""
        parts = [self.root_file.parent.joinpath(p).resolve().parts for p in self.tag_paths]

        common_parts = []
        zipped_parts: tuple[str, ...]
        for zipped_parts in zip(*parts):
            if len(set(zipped_parts)) != 1:
                break

            common_parts.append(zipped_parts[0])

        return Path(*common_parts)

    @classmethod
    def by_name(cls, name: str, /, *, allow_creation: bool = True) -> Package:
        """Get or create a package by its name."""
        if (self := cls.INSTANCES.get(name)) is not None:
            return self

        if allow_creation and const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml").is_file():
            return cls.parse_file(
                const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml"),
            )

        raise PackageNotFoundError(const.PACKAGES_DIR.joinpath(name))

    @classmethod
    def get_packages(cls) -> Generator[Package, None, None]:
        """Generate all packages."""
        for pkg_file in sorted(const.PACKAGES_DIR.glob("*.yaml")):
            yield cls.by_name(pkg_file.stem)

    @classmethod
    def parse_file(cls, file: Path) -> Package:
        """Parse a file from the packages directory."""
        package_config: JSONObj
        package_config, _ = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=JSONObj,
        )

        if len(package_config) == 1:
            name = str(next(iter(package_config)))
        elif len(key_set := {str(k).split()[0] for k in package_config}) == 1:
            name = key_set.pop()

            LOGGER.info(
                "Found package in file %s with split keys, combined into: %r",
                file.relative_to(const.REPO_PATH),
                name,
            )
        else:
            raise PackageDefinitionError(
                file,
                f"invalid split keys { {str(k).split()[0] for k in package_config} }",
            )

        entity_generators: list[EntityGenerator] = []
        tag_paths: list[PurePath] = []

        def _get_entity_generators(
            tag: TagWithPath[Any, Any],
            **_: str | int | None,
        ) -> Any:
            entity_generators.append(tag.entity_generator)

            # Only save tags from the package file
            if tag.file == file:
                tag_paths.append(tag.absolute_path)

            return tag

        process_json_object(
            package_config,
            target_type=TagWithPath,
            target_processor_func=_get_entity_generators,  # type: ignore[arg-type]
            pass_on_fail=False,
            log_op_func_failures=False,
        )

        if (pkg := cls.INSTANCES.get(file.stem)) is None:
            return cls(
                pkg_name=file.stem,
                name=name,
                entity_generators=entity_generators,
                root_file=file,
                tag_paths=tag_paths,
            )

        pkg.entity_generators.extend(entity_generators)

        return pkg

    def __hash__(self) -> int:
        """Return a hash of the package."""
        return hash(self.pkg_name)


__all__ = ["Package"]

"""Models for packages."""

from __future__ import annotations

from collections.abc import Generator, Iterable
from dataclasses import dataclass
from functools import cached_property
from logging import getLogger
from pathlib import Path, PurePath
from typing import Any, ClassVar, Self

from wg_utilities.helpers.mixin.instance_cache import CacheIdNotFoundError
from wg_utilities.helpers.processor import JProc

from home_assistant_config_validator.utils import (
    Entity,
    EntityGenerator,
    PackageDefinitionError,
    PackageNotFoundError,
    TagWithPath,
    const,
    load_yaml,
)

LOGGER = getLogger(__name__)  # Level set by args


@JProc.callback(allow_mutation=False)
def _get_entity_generators(
    _value_: TagWithPath[Any, Any],
    entity_generators: list[EntityGenerator],
    file: Path,
    tag_paths: list[Path],
) -> None:
    entity_generators.append(_value_.entity_generator)

    # Only save tags from the package file
    if _value_.file == file:
        tag_paths.append(_value_.absolute_path)


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
    entity_generators__: list[EntityGenerator]

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

        if (
            allow_creation
            and (
                pkg_file := const.PACKAGES_DIR.joinpath(name).with_suffix(const.EXT)
            ).is_file()
        ):
            return cls.parse_file(pkg_file)

        raise PackageNotFoundError(const.PACKAGES_DIR.joinpath(name))

    @classmethod
    def get_packages(cls) -> Generator[Package, None, None]:
        """Generate all packages."""
        for pkg_file in sorted(const.PACKAGES_DIR.glob(const.GLOB_PATTERN)):
            yield cls.by_name(pkg_file.stem)

    @classmethod
    def parse_file(cls, file: Path) -> Package:
        """Parse a file from the packages directory."""
        package_config: dict[str, object]
        package_config, _ = load_yaml(
            file,
            validate_content_type=dict[str, object],
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

        try:
            jproc = JProc.from_cache("get_entity_generators")
        except CacheIdNotFoundError:
            jproc = JProc(
                {TagWithPath: _get_entity_generators},
                identifier="get_entity_generators",
                process_type_changes=True,
                process_pydantic_extra_fields=True,
            )

        jproc.process(
            package_config,
            entity_generators=entity_generators,
            file=file,
            tag_paths=tag_paths,
        )

        if (pkg := cls.INSTANCES.get(file.stem)) is None:
            return cls(
                pkg_name=file.stem,
                name=name,
                entity_generators__=entity_generators,
                root_file=file,
                tag_paths=tag_paths,
            )

        pkg.entity_generators__.extend(entity_generators)

        return pkg

    @cached_property
    def entities(self) -> tuple[Entity, ...]:
        """Generate all entities."""
        entities: list[Entity] = []
        for entity_generator in self.entity_generators__:
            entities.extend(entity_generator)

        return tuple(entities)

    def __hash__(self) -> int:
        """Return a hash of the package."""
        return hash(self.pkg_name)


__all__ = ["Package"]

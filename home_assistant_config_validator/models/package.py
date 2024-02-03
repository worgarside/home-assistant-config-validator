"""Models for packages."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Any, ClassVar, Self

from wg_utilities.functions.json import JSONObj, process_json_object
from wg_utilities.loggers import add_stream_handler

from home_assistant_config_validator.utils import (
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
    root_path: Path
    entities: list[JSONObj] = field(default_factory=list)

    def __post_init__(self: Self) -> None:
        """Add the instance to the instances dict."""
        if (instance := self.INSTANCES.get(self.pkg_name)) is None:
            self.INSTANCES[self.pkg_name] = self
        elif instance != self:
            raise PackageDefinitionError(
                const.PACKAGES_DIR.joinpath(self.pkg_name),
                f"Can't have multiple packages with same name ({self.pkg_name})",
            )

    @classmethod
    def get_packages(cls) -> Generator[Package, None, None]:
        """Generate all packages."""
        for pkg_file in sorted(const.PACKAGES_DIR.glob("*.yaml")):
            yield cls.by_name(pkg_file.stem)

    @classmethod
    def by_name(cls, name: str, /, *, allow_creation: bool = True) -> Package:
        """Get or create a package by its name."""
        if (self := cls.INSTANCES.get(name)) is not None:
            return self

        if (
            allow_creation
            and const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml").is_file()
        ):
            return cls.parse_file(
                const.PACKAGES_DIR.joinpath(name).with_suffix(".yaml"),
            )

        raise PackageNotFoundError(const.PACKAGES_DIR.joinpath(name))

    @classmethod
    def parse_file(cls, file: Path) -> Package:
        """Parse a file from the packages directory."""
        # TODO add check that the file is in the integs dir

        package_config: JSONObj = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=JSONObj,
        )

        if len(package_config) == 1:
            name = str(next(iter(package_config)))
        elif len(key_set := {str(k).split()[0] for k in package_config}) == 1:
            name = key_set.pop()

            LOGGER.warning(
                "Found package in file %s with split keys, combined into: %r",
                file.relative_to(const.REPO_PATH),
                name,
            )
        else:
            raise PackageDefinitionError(file, f"invalid split keys {key_set!r}")

        entities: list[JSONObj] = []

        def _add_to_entities_and_resolve(
            tag: TagWithPath[Any, Any],
            **_: Any,
        ) -> Any:
            entities.extend(tag.entities)
            return tag.resolve(resolve_tags=False)

        process_json_object(
            package_config,
            target_type=TagWithPath,
            target_processor_func=_add_to_entities_and_resolve,  # type: ignore[arg-type]
            pass_on_fail=False,
            log_op_func_failures=False,
        )

        if (pkg := cls.INSTANCES.get(file.stem)) is None:
            return cls(pkg_name=file.stem, name=name, entities=entities, root_path=file)

        pkg.entities.extend(entities)

        return pkg

    def __hash__(self) -> int:
        """Return a hash of the package."""
        return hash(self.pkg_name)


__all__ = ["Package"]

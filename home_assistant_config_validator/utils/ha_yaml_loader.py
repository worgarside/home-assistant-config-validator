"""Functionality for loading Home Assistant YAML files."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path, PurePath
from typing import Any, ClassVar, Generic, Literal, Self, TypeVar, cast, get_origin

from pydantic import BaseModel, ConfigDict, Field
from wg_utilities.functions.json import (
    JSONObj,
    JSONVal,
    TargetProcessorFunc,
    process_json_object,
)
from wg_utilities.loggers import add_stream_handler
from yaml import SafeLoader, ScalarNode, load

from . import const
from .exception import FileContentTypeError

LOGGER = getLogger(__name__)
LOGGER.setLevel("INFO")
add_stream_handler(LOGGER)

F = TypeVar("F", JSONObj, list[JSONObj])

ResTo = TypeVar("ResTo", bound=JSONVal)
ResToPath = TypeVar("ResToPath", JSONObj, list[JSONObj], JSONObj | list[JSONObj])


class Entity(BaseModel):

    file__: Path = Field(exclude=True)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    def get(self, key: str, default: Any = None, /) -> Any:
        """Get a value from the entity."""
        return getattr(self, key, default)


class HAYamlLoader(SafeLoader):
    """A YAML loader that supports custom Home Assistant tags."""


@dataclass
class Tag(ABC, Generic[ResTo]):
    RESOLVES_TO: ClassVar[type]
    TAG: ClassVar[str]

    file: Path = field(default=const.NULL_PATH)

    @classmethod
    def construct(
        cls,
        loader: SafeLoader,
        node: ScalarNode,
        **kwargs: dict[str, Any],
    ) -> Self:
        """Construct a custom tag from a YAML node.

        Args:
            loader (SafeLoader): The YAML loader
            node (ScalarNode): The YAML node to construct from
            **kwargs (dict[str, Any]): Additional keyword arguments to pass to the
                constructor

        Returns:
            _CustomTag: The constructed custom tag
        """
        return cls(loader.construct_scalar(node), **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def subclasses_recursive(
        __cls: type[Tag[Any]] | None = None,
        /,
    ) -> tuple[type[Any], ...]:
        """Get all subclasses of a class recursively.

        Args:
            cls (type[_CustomTag]): The class to get the subclasses of.

        Returns:
            list[type[_CustomTag]]: A list of all subclasses of the class.
        """
        __cls = __cls or Tag

        indirect: list[type[Any]] = []
        for subclass in (direct := __cls.__subclasses__()):
            indirect.extend(__cls.subclasses_recursive(subclass))

        return tuple(direct + indirect)

    @abstractmethod
    def resolve(
        self,
        source_file: Path,
        *,
        resolve_tags: bool,
    ) -> ResTo:
        """Load the data for the tag."""
        raise NotImplementedError

    def resolves_to(self, __type: type, /) -> bool:
        """Return whether the tag resolves to a given type."""
        return __type == self.RESOLVES_TO


@dataclass
class Include(Tag[JSONObj | list[JSONObj]]):
    """Return the content of a file."""

    path: PurePath

    TAG: ClassVar[Literal["!include"]] = "!include"
    file: Path = field(init=False)

    def resolve(
        self,
        source_file: Path = const.NULL_PATH,
        *,
        resolve_tags: bool,
    ) -> JSONObj | list[JSONObj]:
        """Load the data from the path.

        Args:
            source_file (Path): The path to load the data relative to.
            resolve_tags (bool): Whether to resolve tags in the loaded data.

        Returns:
            JSONObj | JSONArr: The data from the path.
        """
        if source_file == const.NULL_PATH:
            source_file = self.file
        elif not source_file.is_file():
            raise FileNotFoundError(source_file)

        return load_yaml(
            source_file.parent / self.path,
            resolve_tags=resolve_tags,
        )


@dataclass
class Secret(Tag[str]):
    """Return the value of a secret.

    https://www.home-assistant.io/docs/configuration/secrets#using-secretsyaml
    """

    secret_id: str
    file: Path = field(init=False)

    FAKE_SECRETS_PATH: ClassVar[Path] = const.REPO_PATH / "secrets.fake.yaml"
    TAG: ClassVar[Literal["!secret"]] = "!secret"

    def resolve(self, *_: Any, **__: Any) -> str:
        """Get a substitute value for a secret from the ID."""
        return self.get_fake_value()

    def get_fake_value(self, fallback_value: str | None = None) -> str:
        """Get a substitute value for a secret.

        Args:
            fallback_value (str | None, optional): The value to return if the secret
                is not found. Defaults to None.

        Returns:
            str: The substitute value for the secret.

        Raises:
            TypeError: If the file does not contain a dictionary.
            ValueError: If the secret is not found in the file and no fallback value
                is provided.
        """
        fake_secrets = load_yaml(self.FAKE_SECRETS_PATH, resolve_tags=False)

        if isinstance(fake_secrets, dict):
            if (
                fake_secret := fake_secrets.get(self.secret_id, fallback_value)
            ) is not None:
                return str(fake_secret)
        else:
            raise TypeError(  # noqa: TRY003
                f"File {self.FAKE_SECRETS_PATH.as_posix()} contains a"
                f" {type(fake_secrets)}, but `!secret` expects it to contain a"
                " dictionary",
            )

        raise ValueError(  # noqa: TRY003
            f"Secret {self.secret_id!r} not found in"
            f" {self.FAKE_SECRETS_PATH.as_posix()!r}",
        )


class TagWithPath(Tag[ResToPath], Generic[F, ResToPath]):
    FILE_CONTENT_TYPE: ClassVar[type]
    RESOLVES_TO: ClassVar[type]
    path: PurePath

    def __post_init__(self) -> None:
        """Post-initialisation."""
        self.path = PurePath(self.path)

    @classmethod
    def attach_file_to_tag(
        cls,
        file: Path,
    ) -> TargetProcessorFunc[Tag[ResToPath]]:
        def _cb(
            value: Tag[ResToPath],
            *,
            dict_key: str | None = None,
            list_index: int | None = None,
        ) -> Tag[ResToPath]:
            _ = dict_key, list_index
            if (
                not hasattr(value, "file")
                or not value.file
                or value.file == const.NULL_PATH
            ):
                value.file = file

            return value

        return _cb

    @abstractmethod
    def _add_file_content_to_data(
        self,
        data: ResToPath,
        file: Path,
        file_content: F,
    ) -> ResToPath:
        """Add the file content to the data."""
        raise NotImplementedError

    @abstractmethod
    def _get_entities_from_file_content(
        self,
        file: Path,
        file_content: F,
    ) -> Generator[Entity, None, None]:
        """Get the entities from the file content."""
        raise NotImplementedError

    def resolve(
        self,
        source_file: Path = const.NULL_PATH,
        *,
        resolve_tags: bool,
    ) -> ResToPath:
        if source_file == const.NULL_PATH:
            source_file = self.file
        elif not source_file.is_file():
            raise FileNotFoundError(source_file)

        data: ResToPath = self.RESOLVES_TO()

        for file in sorted((source_file.parent / self.path).rglob("*.yaml")):
            file_content: F = load_yaml(
                file,
                resolve_tags=resolve_tags,
                validate_content_type=self.FILE_CONTENT_TYPE,
            )

            if not isinstance(file_content, self.FILE_CONTENT_TYPE):
                raise TypeError(  # noqa: TRY003
                    f"File {file} contains a {type(file_content)}, but"
                    f"`{self.TAG}` expects each file to contain a {self.FILE_CONTENT_TYPE}",
                )

            if resolve_tags is False:
                # If tags aren't being resolved, attach a file path to them for
                # resolution later
                process_json_object(  # type: ignore[misc]
                    file_content,
                    target_type=TagWithPath,
                    target_processor_func=TagWithPath.attach_file_to_tag(file),
                    pass_on_fail=False,
                    log_op_func_failures=False,
                    single_keys_to_remove=["sensor"],
                )

            data = self._add_file_content_to_data(data, file, file_content)

        return data

    @property
    def entities(self) -> Generator[Entity, None, None]:
        for file in sorted(self.absolute_path.rglob("*.yaml")):
            file_content: F = load_yaml(
                file,
                resolve_tags=False,
                validate_content_type=self.FILE_CONTENT_TYPE,
            )

            if not isinstance(file_content, self.FILE_CONTENT_TYPE):
                raise TypeError(  # noqa: TRY003
                    f"File {file} contains a {type(file_content)}, but"
                    f"`{self.TAG}` expects each file to contain a {self.FILE_CONTENT_TYPE}",
                )

            yield from self._get_entities_from_file_content(file, file_content)

    @property
    def absolute_path(self) -> Path:
        return (self.file.parent / self.path).resolve()

    def __str__(self) -> str:
        return f"{self.TAG} {self.path.as_posix()}"

    def __hash__(self) -> int:
        return hash(self.path)


@dataclass
class IncludeDirList(TagWithPath[JSONObj, list[JSONObj]]):
    """Return the content of a directory as a list.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_list will return the content of a directory as a list with each file
    content being an entry in the list. The list entries are ordered based on the
    alphanumeric ordering of the names of the files.
    """

    path: PurePath
    file: Path = field(init=False)

    TAG: ClassVar[Literal["!include_dir_list"]] = "!include_dir_list"

    FILE_CONTENT_TYPE: ClassVar[type] = dict
    RESOLVES_TO: ClassVar[type] = list

    def _add_file_content_to_data(
        self,
        data: list[JSONObj],
        file: Path,
        file_content: JSONObj,
    ) -> list[JSONObj]:
        file_content["file__"] = file.resolve()
        data.append(file_content)
        return data

    def _get_entities_from_file_content(
        self,
        file: Path,
        file_content: JSONObj,
    ) -> Generator[Entity, None, None]:
        file_content["file__"] = file.resolve()

        yield Entity.model_validate(file_content)


@dataclass
class IncludeDirMergeList(TagWithPath[list[JSONObj], list[JSONObj]]):
    """Return the content of a directory as a list by combining all items.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_merge_list will return the content of a directory as a list by merging
    all files (which should contain a list) into 1 big list.
    """

    path: PurePath
    file: Path = field(init=False)

    FILE_CONTENT_TYPE: ClassVar[type] = list
    RESOLVES_TO: ClassVar[type] = list
    TAG: ClassVar[Literal["!include_dir_merge_list"]] = "!include_dir_merge_list"

    def _add_file_content_to_data(
        self,
        data: list[JSONObj],
        file: Path,
        file_content: list[JSONObj],
    ) -> list[JSONObj]:
        for elem in file_content:
            elem["file__"] = file.resolve()

        data.extend(file_content)
        return data

    def _get_entities_from_file_content(
        self,
        file: Path,
        file_content: list[JSONObj],
    ) -> Generator[Entity, None, None]:
        for elem in file_content:
            elem["file__"] = file.resolve()

            yield Entity.model_validate(elem)


@dataclass
class IncludeDirMergeNamed(TagWithPath[JSONObj, JSONObj]):
    """Return the content of a directory as a dictionary.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_merge_named will return the content of a directory as a dictionary by
    loading each file and merging it into 1 big dictionary.
    """

    path: PurePath
    file: Path = field(init=False)

    FILE_CONTENT_TYPE: ClassVar[type] = dict
    RESOLVES_TO: ClassVar[type] = dict
    TAG: ClassVar[Literal["!include_dir_merge_named"]] = "!include_dir_merge_named"

    def _add_file_content_to_data(
        self,
        data: JSONObj,
        file: Path,
        file_content: JSONObj,
    ) -> JSONObj:
        file_content["file__"] = file.resolve()
        data.update(file_content)
        return data

    def _get_entities_from_file_content(
        self,
        file: Path,
        file_content: JSONObj,
    ) -> Generator[Entity, None, None]:
        file_content["file__"] = file.resolve()
        yield Entity.model_validate(file_content)


@dataclass
class IncludeDirNamed(TagWithPath[JSONObj, JSONObj]):
    """Return the content of a directory as a dictionary.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_named will return the content of a directory as a dictionary which
    maps filename => content of file.
    """

    path: PurePath
    file: Path = field(init=False)

    FILE_CONTENT_TYPE: ClassVar[type] = dict
    RESOLVES_TO: ClassVar[type] = dict
    TAG: ClassVar[Literal["!include_dir_named"]] = "!include_dir_named"

    def _add_file_content_to_data(
        self,
        data: JSONObj,
        file: Path,
        file_content: JSONObj,
    ) -> JSONObj:
        file_content["file__"] = file.resolve()
        data[file.stem] = file_content
        return data

    def _get_entities_from_file_content(
        self,
        file: Path,
        file_content: JSONObj,
    ) -> Generator[Entity, None, None]:
        file_content["file__"] = file.resolve()

        yield Entity.model_validate(file_content)


def load_yaml(
    path: Path,
    *,
    resolve_tags: bool,
    validate_content_type: type[F] | None = None,
) -> F:
    """Load a YAML file.

    Args:
        path (Path): The path to the YAML file.
        resolve_tags (bool, optional): Whether to resolve tags in the YAML file.
            Defaults to False.
        validate_content_type (type[F] | None, optional): The type to validate the
            content of the YAML file against. Defaults to None.

    Returns:
        JSONObj: The content of the YAML file as a JSON object
    """
    content = cast(
        F,
        load(path.read_text(), Loader=HAYamlLoader),  # noqa: S506
    )

    if validate_content_type is not None and not issubclass(
        type(content),
        get_origin(validate_content_type) or validate_content_type,
    ):
        raise FileContentTypeError(path, content, validate_content_type)

    if resolve_tags:
        process_json_object(
            content,
            target_type=Tag,
            target_processor_func=lambda tag, **_: tag.resolve(  # type: ignore[arg-type]
                path,
                resolve_tags=resolve_tags,
            ),
            pass_on_fail=False,
            log_op_func_failures=False,
        )
    else:
        process_json_object(  # type: ignore[misc]
            content,
            target_type=TagWithPath,
            target_processor_func=TagWithPath.attach_file_to_tag(path),
            pass_on_fail=False,
            log_op_func_failures=False,
        )

    return content


def add_custom_tags_to_loader(loader: type[SafeLoader]) -> None:
    """Add all custom tags to a YAML loader.

    Args:
        loader (type[SafeLoader]): The YAML loader to add the custom tags to.
    """
    for tag_class in Tag.subclasses_recursive():
        try:
            loader.add_constructor(tag_class.TAG, tag_class.construct)
            LOGGER.debug("Added constructor for %s", tag_class.TAG)
        except AttributeError:
            continue


add_custom_tags_to_loader(HAYamlLoader)

__all__ = [
    "load_yaml",
]

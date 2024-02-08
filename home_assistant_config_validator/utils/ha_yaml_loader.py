"""Functionality for loading Home Assistant YAML files."""

from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass, field
from functools import lru_cache
from logging import getLogger
from pathlib import Path, PurePath
from tempfile import NamedTemporaryFile
from typing import (
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    Literal,
    Self,
    TypeVar,
    cast,
    get_origin,
    overload,
)

from jsonpath_ng import JSONPath, parse  # type: ignore[import-untyped]
from jsonpath_ng.exceptions import JsonPathParserError  # type: ignore[import-untyped]
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from ruamel.yaml import YAML, ScalarNode
from ruamel.yaml.representer import Representer
from wg_utilities.functions.json import (
    JSONArr,
    JSONObj,
    JSONVal,
    TargetProcessorFunc,
    process_json_object,
)
from wg_utilities.loggers import add_stream_handler

from . import const
from .exception import (
    FileContentTypeError,
    FileIOError,
    FixableConfigurationError,
    InvalidConfigurationError,
    InvalidFieldTypeError,
    JsonPathNotFoundError,
    UserPCHConfigurationError,
)

LOGGER = getLogger(__name__)
LOGGER.setLevel("DEBUG")
add_stream_handler(LOGGER)

F = TypeVar("F", JSONObj, list[JSONObj])

ResTo = TypeVar("ResTo", bound=JSONVal)
ResToPath = TypeVar("ResToPath", JSONObj, list[JSONObj], JSONObj | list[JSONObj])


HAYamlLoader = YAML(typ="rt")
HAYamlLoader.explicit_start = True
HAYamlLoader.preserve_quotes = True
HAYamlLoader.indent(mapping=2, sequence=4, offset=2)


class Entity(BaseModel):

    file__: Path = Field(exclude=True)
    modified__: bool = Field(default=False, exclude=True)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    def get(self, key: str, default: Any = None, /) -> Any:
        """Get a value from the entity."""
        return getattr(self, key, default)

    def model_copy(
        self,
        *,
        update: dict[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        self.modified__ = not deep and bool(update)
        return super().model_copy(update=update, deep=deep)

    def autofix_file_issues(
        self,
        issues: list[InvalidConfigurationError],
        /,
        *,
        new_file: Path | None = None,
    ) -> None:
        """Dump the entity to a file.

        Args:
            issues (list[InvalidConfigurationError]): The issues to fix in the file.
            new_file (Path, optional): The new file to dump the entity to. Defaults
                to None (i.e. the original file).
        """
        try:
            entity_yaml = HAYamlLoader.load(new_file or self.file__)
        except Exception as exc:
            raise FileIOError(
                new_file or self.file__,
                "load",
            ) from exc

        for issue in issues:
            if isinstance(issue, FixableConfigurationError):
                set_json_value(
                    entity_yaml,
                    issue.json_path_str,
                    issue.expected_value,
                    allow_create=True,
                )
                issue.fixed = True

        try:
            with NamedTemporaryFile("w", delete=False) as temp_file:
                HAYamlLoader.dump(entity_yaml, Path(temp_file.name))
            shutil.move(temp_file.name, new_file or self.file__)
        except Exception as exc:
            raise FileIOError(
                new_file or self.file__,
                "dump",
            ) from exc


EntityGenerator = Generator[Entity, None, None]


@dataclass
class Tag(ABC, Generic[ResTo]):
    RESOLVES_TO: ClassVar[type]
    TAG: ClassVar[str]

    file: Path = field(default=const.NULL_PATH)

    @classmethod
    def construct(
        cls,
        loader: Any,  # XLoader type isn't importable
        node: ScalarNode,
        **kwargs: dict[str, Any],
    ) -> Self:
        """Construct a custom tag from a YAML node.

        Args:
            loader (Loader): The YAML loader
            node (ScalarNode): The YAML node to construct from
            **kwargs (dict[str, Any]): Additional keyword arguments to pass to the
                constructor

        Returns:
            _CustomTag: The constructed custom tag
        """
        return cls(loader.construct_scalar(node), **kwargs)

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
                value.file = file.resolve(strict=True)

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
    def _get_entities_from_file(
        self,
        file: Path,
    ) -> EntityGenerator:
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
    def absolute_path(self) -> Path:
        """Get the resolved path for this tag."""
        return (self.file.parent / self.path).resolve()

    @property
    def entity_generator(self) -> EntityGenerator:
        """Get the entities from the tag."""
        for file in sorted(self.absolute_path.rglob("*.yaml")):
            yield from self._get_entities_from_file(file)

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

    def _get_entities_from_file(
        self,
        file: Path,
    ) -> EntityGenerator:
        file_content = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=self.FILE_CONTENT_TYPE,
            isolate_tags_from_files=True,
        )

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

    def _get_entities_from_file(
        self,
        file: Path,
    ) -> EntityGenerator:
        file_content: list[JSONObj] = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=self.FILE_CONTENT_TYPE,
            isolate_tags_from_files=True,
        )

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

    def _get_entities_from_file(
        self,
        file: Path,
    ) -> EntityGenerator:
        file_content = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=self.FILE_CONTENT_TYPE,
            isolate_tags_from_files=True,
        )
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

    def _get_entities_from_file(
        self,
        file: Path,
    ) -> EntityGenerator:
        file_content = load_yaml(
            file,
            resolve_tags=False,
            validate_content_type=self.FILE_CONTENT_TYPE,
            isolate_tags_from_files=True,
        )
        file_content["file__"] = file.resolve()

        yield Entity.model_validate(file_content)


def load_yaml(
    path: Path,
    *,
    resolve_tags: bool,
    validate_content_type: type[F] | None = None,
    isolate_tags_from_files: bool = False,
) -> F:
    """Load a YAML file.

    Args:
        path (Path): The path to the YAML file.
        resolve_tags (bool, optional): Whether to resolve tags in the YAML file.
            Defaults to False.
        validate_content_type (type[F] | None, optional): The type to validate the
            content of the YAML file against. Defaults to None.
        isolate_tags_from_files (bool, optional): Whether to isolate tags from files.
            Defaults to False, which will attach a file path to each tag. Setting this
            to True is not recommended unless you are sure that the tags in the file
            are not being used elsewhere (or therer aren't any tags).

    Returns:
        JSONObj: The content of the YAML file as a JSON object
    """
    content = cast(F, HAYamlLoader.load(path))

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
    elif not isolate_tags_from_files:
        process_json_object(  # type: ignore[misc]
            content,
            target_type=TagWithPath,
            target_processor_func=TagWithPath.attach_file_to_tag(path),
            pass_on_fail=False,
            log_op_func_failures=False,
        )

    return content


def add_custom_tags_to_loader(loader: YAML) -> None:
    """Add all custom tags to a YAML loader.

    Args:
        loader (YAML): The YAML loader to add the custom tags to.
    """
    for tag_class in Tag.subclasses_recursive():
        try:
            loader.constructor.add_constructor(tag_class.TAG, tag_class.construct)
            LOGGER.debug("Added constructor for %s", tag_class.TAG)
        except AttributeError:
            continue

    def repr_secret(
        representer: Representer,
        secret: Secret,
    ) -> ScalarNode:
        return representer.represent_scalar(secret.TAG, secret.secret_id)

    loader.representer.add_representer(Secret, repr_secret)


@lru_cache
def _validate_json_path(path: str, /) -> JSONPathStr:
    """Validate a JSONPath string."""
    try:
        parse(path)
    except JsonPathParserError:
        raise UserPCHConfigurationError(
            const.ConfigurationType.VALIDATION,
            "unknown",
            f"Invalid JSONPath: {path}",
        ) from None

    return path


JSONPathStr = Annotated[str, AfterValidator(_validate_json_path)]

NO_DEFAULT: Final[object] = object()

G = TypeVar("G")


@overload
def get_json_value(
    json_obj: Entity,
    json_path: JSONPathStr,
    /,
    valid_type: Literal[None] = None,
    default: JSONVal = ...,
) -> JSONVal: ...


@overload
def get_json_value(
    json_obj: Entity | JSONObj | JSONArr,
    json_path: JSONPathStr,
    /,
    valid_type: type[G],
    default: JSONVal = NO_DEFAULT,
) -> G: ...


def get_json_value(
    json_obj: Entity | JSONObj | JSONArr,
    json_path_str: JSONPathStr,
    /,
    valid_type: type[G] | None = None,
    default: JSONVal = NO_DEFAULT,
) -> G | JSONVal:
    """Get a value from a JSON object using a JSONPath expression.

    Args:
        json_obj (JSONObj | JSONArr): The JSON object to search
        json_path_str (JSONPathStr): The JSONPath expression
        default (Any, optional): The default value to return if the path is not found.
            Defaults to None.
        valid_type (type[Any], optional): The type of the value to return. Defaults to
            object.

    Returns:
        Any: The value at the JSONPath expression
    """
    json_path = parse_jsonpath(json_path_str)

    values: JSONArr = [match.value for match in json_path.find(json_obj)]

    if isinstance(json_obj, Entity):
        json_obj = json_obj.model_dump()

    if not values:
        if default is not NO_DEFAULT:
            return default

        raise JsonPathNotFoundError(json_path_str)

    if valid_type is not None and not all(
        isinstance(value, valid_type) for value in values
    ):
        raise InvalidFieldTypeError(json_path_str, values, valid_type)

    if len(values) == 1:
        return values[0]

    return values


S = TypeVar("S", Entity, JSONObj)


def set_json_value(
    obj: S,
    json_path_str: JSONPathStr,
    value: JSONVal,
    /,
    *,
    allow_create: bool = False,
) -> S:
    """Set a value in a JSON object using a JSONPath expression.

    Args:
        obj (JSONObj | Entity): The JSON object to search
        json_path_str (str): The JSONPath expression
        value (Any): The value to set
        allow_create (bool, optional): Whether to allow creating the path if it doesn't
            exist. Defaults to False.

    Returns:
        JSONObj | JSONArr: The updated JSON object
    """
    json_path = parse_jsonpath(json_path_str)

    if isinstance(obj, Entity):
        LOGGER.debug(
            "Setting value in %s at %s: %s",
            obj.file__.relative_to(const.REPO_PATH),
            json_path_str,
            value,
        )
        json_obj = obj.model_dump()
    else:
        LOGGER.debug("Setting value at %s: %s", json_path_str, value)
        json_obj = obj

    if allow_create:
        json_path.update_or_create(json_obj, value)
    else:
        json_path.update(json_obj, value)

    if isinstance(obj, Entity):
        return obj.model_copy(update=json_obj, deep=False)

    return obj


ROOT_PREFIX_PATTERN = re.compile(r"^root(?=\W)")


@lru_cache
def parse_jsonpath(__jsonpath: str, /) -> JSONPath:
    """Parse a JSONPath expression.

    This is just to cache parsed paths.
    """
    if ROOT_PREFIX_PATTERN.match(__jsonpath):
        __jsonpath = ROOT_PREFIX_PATTERN.sub("$.", __jsonpath)

    _validate_json_path(__jsonpath)
    return parse(__jsonpath)


add_custom_tags_to_loader(HAYamlLoader)

__all__ = [
    "load_yaml",
]

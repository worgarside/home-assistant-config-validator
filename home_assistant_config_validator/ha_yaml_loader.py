"""Functionality for loading Home Assistant YAML files."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast

from wg_utilities.functions.json import JSONObj, JSONVal
from yaml import SafeLoader, ScalarNode, load

from .const import INTEGRATIONS_DIR, REPO_PATH


@dataclass
class _CustomTag:
    TAG: ClassVar[str]

    @classmethod
    def construct(
        cls, loader: SafeLoader, node: ScalarNode, **kwargs: dict[str, Any]
    ) -> _CustomTag:
        """Construct a custom tag from a YAML node.

        Args:
            loader (SafeLoader): The YAML loader
            node (ScalarNode): The YAML node to construct from
            **kwargs (dict[str, Any]): Additional keyword arguments to pass to the
                constructor

        Returns:
            _CustomTag: The constructed custom tag
        """

        # pylint: disable=too-many-function-args
        return cls(loader.construct_scalar(node), **kwargs)  # type: ignore[call-arg]


class _CustomTagWithPath(_CustomTag):
    path: str


@dataclass
class IncludeDirList(_CustomTagWithPath):
    """Return the content of a directory as a list.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_list will return the content of a directory as a list with each file
    content being an entry in the list. The list entries are ordered based on the
    alphanumeric ordering of the names of the files.
    """

    TAG: ClassVar[str] = "!include_dir_list"
    path: str

    def load_data(self, relative_to: Path = INTEGRATIONS_DIR) -> list[JSONObj]:
        """Load the data from the directory.

        Args:
            relative_to (Path, optional): The path to load the data relative to.
                Defaults to INTEGRATIONS_DIR.

        Returns:
            list[JSONObj]:the content of a directory as a list with each file content
                being an entry in the list

        Raises:
            TypeError: If any of the files in the directory do not contain a dictionary
        """
        data: list[JSONObj] = []

        for file in sorted((relative_to / self.path).rglob("*.yaml")):
            file_content = load_yaml(file)

            if isinstance(file_content, dict):
                data.append(file_content)
            else:
                raise TypeError(
                    f"File {file} contains a {type(file_content)}, but"
                    "`!include_dir_list` expects each file to contain a dictionary"
                )

        return data


@dataclass
class IncludeDirMergeList(_CustomTagWithPath):
    """Return the content of a directory as a list.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_merge_list will return the content of a directory as a list by merging
    all files (which should contain a list) into 1 big list.
    """

    TAG: ClassVar[str] = "!include_dir_merge_list"
    path: str

    def load_data(self, relative_to: Path = INTEGRATIONS_DIR) -> list[JSONObj]:
        """Load the data from the directory.

        Args:
            relative_to (Path, optional): The path to load the data relative to.
                Defaults to INTEGRATIONS_DIR.

        Returns:
            list[JSONObj]: The content of a directory as a list by merging all files
                (which should contain a list) into 1 big list.

        Raises:
            TypeError: If any of the files in the directory do not contain a list
        """
        data: list[JSONObj] = []

        for file in sorted((relative_to / self.path).rglob("*.yaml")):
            file_content = load_yaml(file)

            if isinstance(file_content, list):
                data.extend(file_content)
            else:
                raise TypeError(
                    f"File {file} contains a {type(file_content)}, but"
                    "`!include_dir_merge_list` expects each file to contain a list"
                )

        return data


@dataclass
class IncludeDirMergeNamed(_CustomTagWithPath):
    """Return the content of a directory as a dictionary.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_merge_named will return the content of a directory as a dictionary by
    loading each file and merging it into 1 big dictionary.
    """

    TAG: ClassVar[str] = "!include_dir_merge_named"
    path: str

    def load_data(self, relative_to: Path = INTEGRATIONS_DIR) -> JSONObj:
        """Load the data from the directory.

        Args:
            relative_to (Path, optional): The path to load the data relative to.
                Defaults to INTEGRATIONS_DIR.

        Returns:
            JSONObj: The content of a directory as a dictionary by merging all files
                (which should contain a dictionary) into 1 big dictionary.

        Raises:
            TypeError: If any of the files in the directory do not contain a dictionary
        """
        data = {}

        for file in sorted((relative_to / self.path).rglob("*.yaml")):
            print("    Loading", file)
            file_content = load_yaml(file)

            if isinstance(file_content, dict):
                data.update(file_content)
            else:
                raise TypeError(
                    f"File {file.as_posix()} contains a {type(file_content)}, but"
                    "`!include_dir_merge_named` expects each file to contain a"
                    " dictionary"
                )

        return data


@dataclass
class IncludeDirNamed(_CustomTagWithPath):
    """Return the content of a directory as a dictionary.

    https://www.home-assistant.io/docs/configuration/splitting_configuration/#advanced-usage

    !include_dir_named will return the content of a directory as a dictionary which
    maps filename => content of file.
    """

    TAG: ClassVar[str] = "!include_dir_named"
    path: str

    def load_data(self, relative_to: Path = INTEGRATIONS_DIR) -> JSONObj:
        """Load the data from the directory.

        Args:
            relative_to (Path, optional): The path to load the data relative to.
                Defaults to INTEGRATIONS_DIR.

        Returns:
            JSONObj: The content of a directory as a dictionary with each file content
                being a key in the dictionary. The key is the filename without the
                extension.

        Raises:
            TypeError: If any of the files in the directory do not contain a single
                object
        """
        data: JSONObj = {}

        for file in sorted((relative_to / self.path).rglob("*.yaml")):
            file_content = load_yaml(file)

            if isinstance(file_content, dict):
                data.update(file_content)
            else:
                raise TypeError(
                    f"File {file.as_posix()} contains a list, but `!include_dir_list`"
                    " expects each file to contain a single object"
                )

        return data


@dataclass
class Secret(_CustomTag):
    """Return the value of a secret.

    https://www.home-assistant.io/docs/configuration/secrets#using-secretsyaml
    """

    FAKE_SECRETS_PATH: ClassVar[Path] = REPO_PATH / "secrets.fake.yaml"
    TAG: ClassVar[str] = "!secret"

    secret_id: str

    @classmethod
    def get_value_callback(
        cls,
        secret: Secret,
        *,
        dict_key: str | None = None,
        list_index: int | None = None,
    ) -> JSONVal:
        """Get a substitute value for a secret from the ID."""

        _ = dict_key, list_index

        return secret.get_fake_value()

    def get_fake_value(self, fallback_value: str | None = None) -> JSONVal:
        """Get a substitute value for a secret.

        Args:
            fallback_value (str | None, optional): The value to return if the secret
                is not found. Defaults to None.

        Returns:
            Any: The substitute value for the secret.

        Raises:
            TypeError: If the file does not contain a dictionary.
            ValueError: If the secret is not found in the file and no fallback value
                is provided.
        """
        fake_secrets = load_yaml(self.FAKE_SECRETS_PATH)

        if isinstance(fake_secrets, dict):
            if (
                fake_secret := fake_secrets.get(self.secret_id, fallback_value)
            ) is not None:
                return fake_secret  # type: ignore[no-any-return]
        else:
            raise TypeError(
                f"File {self.FAKE_SECRETS_PATH.as_posix()} contains a"
                f" {type(fake_secrets)}, but `!secret` expects it to contain a"
                " dictionary"
            )

        raise ValueError(
            f"Secret {self.secret_id!r} not found in"
            f" {self.FAKE_SECRETS_PATH.as_posix()!r}"
        )


# pylint: disable=too-few-public-methods
class HAYamlLoader(SafeLoader):
    """A YAML loader that supports custom Home Assistant tags."""


def load_yaml(path: Path) -> JSONObj | Iterable[JSONVal]:
    """Load a YAML file.

    Args:
        path (Path): The path to the YAML file.

    Returns:
        JSONObj | Iterable[JSONVal]: The content of the YAML file as a JSON object or
            iterable of JSON values.
    """
    return cast(
        JSONObj | Iterable[JSONVal],
        load(path.read_text(), Loader=HAYamlLoader),
    )


def subclasses_recursive(cls: type[_CustomTag]) -> list[type[_CustomTag]]:
    """Get all subclasses of a class recursively.

    Args:
        cls (type[_CustomTag]): The class to get the subclasses of.

    Returns:
        list[type[_CustomTag]]: A list of all subclasses of the class.
    """
    indirect = []
    for subclass in (direct := cls.__subclasses__()):
        indirect.extend(subclasses_recursive(subclass))
    return direct + indirect


def add_custom_tags_to_loader(loader: type[SafeLoader]) -> None:
    """Add all custom tags to a YAML loader.

    Args:
        loader (type[SafeLoader]): The YAML loader to add the custom tags to.
    """
    for tag_class in subclasses_recursive(_CustomTag):
        if not tag_class.__name__.startswith("_"):
            loader.add_constructor(tag_class.TAG, tag_class.construct)


add_custom_tags_to_loader(HAYamlLoader)

__all__ = [
    "IncludeDirList",
    "IncludeDirMergeList",
    "IncludeDirMergeNamed",
    "IncludeDirNamed",
    "Secret",
    "load_yaml",
]

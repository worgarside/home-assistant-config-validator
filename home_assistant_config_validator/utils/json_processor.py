"""Useful functions for working with JSON/dictionaries."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import MutableMapping, Sequence
from functools import wraps
from logging import DEBUG, getLogger
from typing import Any, Callable, ClassVar, NamedTuple, Protocol, Self, TypeVar, Union, final, overload

LOGGER = getLogger(__name__)
LOGGER.setLevel(DEBUG)

JSONVal = Union[
    None,
    object,
    bool,
    str,
    float,
    int,
    list["JSONVal"],
    "JSONObj",
    dict[str, object],
]
JSONObj = dict[str, JSONVal]
JSONArr = list[JSONVal]


class Callback(Protocol):
    """Typing protocol for the user-defined functions passed into the JSONProcessor.

    Example:
        ```python
        def convert_floats_to_ints(
            value: float,
            loc: str | int,
            obj_type: type[dict[Any, Any] | list[Any]],
        ) -> int:
            return int(value)


        jproc = JSONProcessor({float: [(convert_floats_to_ints,)]})
        ```
    """

    def __call__(
        self,
        value: Any,
        *,
        loc: str | int,
        obj_type: type[dict[Any, Any] | list[Any]],
        **kwargs: Any,
    ) -> Any:
        """The function to be called on each value in the JSON object."""


class ItemFilter(Protocol):
    """Function to filter items before processing them."""

    def __call__(self, item: Any, /, *, loc: str | int) -> bool:
        """The function to be called on each value in the JSON object."""


_Obj = dict[Any, Any] | list[Any]


T = TypeVar("T")


class InstanceCacheKeyError(KeyError):
    """Raised when a key is not found in the cache."""

    def __init__(self, cls: type, key: object, /) -> None:
        self.cls = cls
        self.key = key

        super().__init__(f"{cls.__name__!r} instance with cache ID {key!r} not found.")


class InstanceCacheDuplicateError(Exception):
    """Raised when a key is already in the cache."""

    def __init__(self, cls: type, key: str, /) -> None:
        self.cls = cls
        self.key = key

        super().__init__(f"{cls.__name__!r} instance with cache ID {key!r} already exists.")


class InstanceCacheMixin:
    _INSTANCES: dict[object, Self]

    _CACHE_ID_FIELD: ClassVar[str]  # The field to use as the cache ID per subclass

    def __init_subclass__(cls, cache_id_field: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._INSTANCES = {}

        if cache_id_field:
            cls._CACHE_ID_FIELD = cache_id_field

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        obj = super().__new__(cls)
        obj.__init__(*args, **kwargs)  # type: ignore[misc]

        try:
            id_field = cls._CACHE_ID_FIELD
        except AttributeError:
            _id = str(id(obj))
        else:
            _id = getattr(obj, id_field)

        if _id in cls._INSTANCES:
            raise InstanceCacheDuplicateError(cls, _id)

        cls._INSTANCES[_id] = obj

        return obj

    @final
    @classmethod
    def from_cache(cls, __cache_id: str, /) -> Self:
        try:
            return cls._INSTANCES[__cache_id]  # type: ignore[return-value]
        except KeyError:
            raise InstanceCacheKeyError(cls, __cache_id) from None

    @final
    @classmethod
    def has_cache_entry(cls, __cache_id: str, /) -> bool:
        return __cache_id in cls._INSTANCES


class JSONProcessor(InstanceCacheMixin, cache_id_field="identifier"):
    """Recursively process JSON objects with user-defined callbacks.

    Attributes:
        callback_mapping (dict): A mapping of types to a list of callback functions
            to be executed on the values of the given type.
        process_subclasses (bool): Whether to (also) process subclasses of the target types.
            Defaults to True.
    """

    callback_mapping: MutableMapping[type[Any], list[CallbackDefinition]]

    class CallbackDefinition(NamedTuple):
        """A named tuple to hold the callback function and its associated data."""

        callback: Callback
        item_filter: ItemFilter | None = None
        allow_failures_in_callback: bool = False

    cb = CallbackDefinition

    def __init__(
        self,
        callback_mapping: dict[type[Any], list[CallbackDefinition]] | None = None,
        *,
        identifier: str = "",
        process_subclasses: bool = True,
    ) -> None:
        """Initialize the JSONProcessor."""
        self.callback_mapping = defaultdict(list)
        self.process_subclasses = process_subclasses

        self.identifier = identifier or str(id(self))

        if callback_mapping:
            for target_type, callbacks in callback_mapping.items():
                self.register_callbacks(target_type, callbacks)

    @overload
    def _iterate(self, obj: dict[Any, Any]) -> dict[Any, Any]:
        ...

    @overload
    def _iterate(self, obj: list[Any]) -> list[int]:
        ...

    def _iterate(self, obj: _Obj) -> dict[Any, Any] | list[int]:
        if isinstance(obj, list):
            return list(range(len(obj)))

        return obj

    def _get_callbacks(self, typ: type[Any]) -> Sequence[CallbackDefinition]:
        if cb := self.callback_mapping.get(typ):
            return cb

        if self.process_subclasses:
            for cb_typ in self.callback_mapping:
                if issubclass(typ, cb_typ):
                    return self.callback_mapping[cb_typ]

        return ()

    def process(self, obj: _Obj, **kwargs: Any) -> None:
        """Recursively process a JSON object with the registered callbacks.

        Args:
            obj (dict[Any, Any] | list[Any]): The JSON object to process.
            kwargs (Any): Any additional keyword arguments to pass to the callbacks.
        """
        for loc in self._iterate(obj):
            obj_type = type(obj)
            orig_item_type = type(obj[loc])

            for cb, item_filter, allow_failures in self._get_callbacks(orig_item_type):
                if item_filter is None or item_filter(obj[loc], loc=loc):
                    try:
                        obj[loc] = cb(obj[loc], loc=loc, obj_type=obj_type, **kwargs)
                    except KeyError:
                        raise
                    except Exception:
                        if not allow_failures:
                            raise
                    # else: a
                    #     if type(obj[loc]) != orig_item_type:
                    #         break  # noqa: ERA001

            if issubclass(type(obj[loc]), dict | list):
                self.process(obj[loc], **kwargs)

    def register_callback(
        self,
        target_type: type[Any],
        callback: Callback,
        *,
        item_filter: ItemFilter | None = None,
        allow_failures_in_callback: bool = True,
    ) -> None:
        """Register a new callback for use when processing any JSON objects.

        Args:
            target_type (type): The type of the values to be processed.
            callback (Callback[JSONVal]): The callback function to execute on the target values
            item_filter (ItemFilter, optional): An optional funcntion to use to filter target
                values before processing them. Defaults to None.
            allow_failures_in_callback (bool, optional): Whether to suppress exceptions.
                Defaults to True.

        Raises:
            TypeError: If the callback arguments are invalid.
        """
        if not callable(callback):
            raise TypeError(callback, type(callback))

        if item_filter and not callable(item_filter):
            raise TypeError(item_filter, type(item_filter))

        if not isinstance(allow_failures_in_callback, bool):
            raise TypeError(
                allow_failures_in_callback,
                type(allow_failures_in_callback),
            )

        self.callback_mapping[target_type].append(
            self.CallbackDefinition(
                callback,
                item_filter,
                allow_failures_in_callback,
            ),
        )

    def register_callbacks(
        self,
        target_type: type[Any],
        callbacks: list[CallbackDefinition],
    ) -> None:
        """Register multiple callbacks at once for a given target type.

        Args:
            target_type (type): The type of the values to be processed.
            callbacks (list[CallbackFunction]): The callback functions to execute on the target
                values.
        """
        for cb in callbacks:
            self.register_callback(
                target_type,
                cb.callback,
                item_filter=cb.item_filter,
                allow_failures_in_callback=cb.allow_failures_in_callback,
            )

    def callback():

        def _decorator(func: Callable[[Any], Any]) -> Callable[[Any, Any], Any]:

            @wraps(func)
            def worker(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return worker

        return _decorator


JProc = JSONProcessor

__all__ = ["JSONProcessor", "Callback", "ItemFilter", "JProc"]

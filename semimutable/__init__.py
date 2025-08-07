"""Utilities for partially-frozen dataclasses.

Portions of the `freeze_fields` function are adapted from Python's standard library `dataclasses` module, which is
licensed under the Python Software Foundation License.
"""

import itertools
from dataclasses import (
    KW_ONLY,
    MISSING,
    Field,
    FrozenInstanceError,
    InitVar,
    asdict,
    astuple,
    fields,
    is_dataclass,
    make_dataclass,
    replace,
)
from dataclasses import dataclass as std_dataclass
from dataclasses import field as std_field
from typing import TYPE_CHECKING, Any, Callable, Final, Literal, Never, Self, dataclass_transform, overload, override

# Type checkers hate private imports, even though this is technically legal. So we lie to them.
if TYPE_CHECKING:
    from collections.abc import Generator

    _MISSING_TYPE = Never

    # The type hints should match the actual implementation.
    def _get_slots(cls: type) -> Generator[str, None, None]:
        raise RuntimeError
else:
    from dataclasses import _MISSING_TYPE, _get_slots

__version__ = "0.2.0"

# Exact match of dataclasses module's __all__.
__all__ = [
    "dataclass",
    "field",
    "Field",
    "FrozenInstanceError",
    "InitVar",
    "KW_ONLY",
    "MISSING",
    # Helper functions.
    "fields",
    "asdict",
    "astuple",
    "make_dataclass",
    "replace",
    "is_dataclass",
]

# Extra items for our module.
__all__ += ["FrozenField", "FrozenFieldPlaceholder", "FrozenFieldError"]

# Note: This prefix CANNOT be dunder, because we used dynamic class creation it would cause name mangling issues.
FROZEN_PREFIX: Final = "_frozen_"


class FrozenFieldError(TypeError):
    """Raised when trying to mutate a frozen field."""

    def __init__(self, field_name: str) -> None:
        super().__init__(f"Cannot modify frozen field '{field_name}'.")


class FrozenField[T]:
    """A descriptor that makes an attribute immutable after it has been set."""

    __slots__ = ("_private_name",)

    def __init__(self, name: str) -> None:
        self._private_name = FROZEN_PREFIX + name

    @overload
    def __get__(self, instance: None, owner: type[object]) -> Self: ...

    @overload
    def __get__(self, instance: object, owner: type[object]) -> T: ...

    def __get__(self, instance: object | None, owner: type[object] | None = None) -> T | Self:
        if instance is None:
            return self
        value = getattr(instance, self._private_name)
        return value

    def __set__(self, instance: object, value: T) -> None:
        if hasattr(instance, self._private_name):
            raise FrozenFieldError(self._private_name[len(FROZEN_PREFIX) :]) from None

        setattr(instance, self._private_name, value)


error = RuntimeError(
    "This field is created via field(frozen=True) but the @semimutable.dataclass decorator is not used on the dataclass. "
    "Replace your use of @dataclass with @semimutable.dataclass."
)


class FrozenFieldPlaceholder:
    """A placeholder for a frozen field before @dataclass transformation.

    If @semimutable.dataclass is not used, this will raise an error when accessed. Otherwise, it will be replaced with a FrozenField descriptor.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the placeholder with the given arguments."""
        super().__setattr__("kwargs", kwargs)

    # dataclass uses getattr() to access fields, overriding __getattribute__ allows us to raise an error at declaration time
    @override
    def __getattribute__(self, name: str, /) -> Never:
        raise error


@overload
def field[_T](
    *,
    default: _T,
    default_factory: _MISSING_TYPE = MISSING,  # type: ignore
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    frozen: bool = False,
    metadata: dict[str, Any] | None = None,
    kw_only: _MISSING_TYPE = MISSING,  # type: ignore
) -> _T: ...


@overload
def field[_T](
    *,
    default: _MISSING_TYPE = MISSING,  # type: ignore
    default_factory: Callable[[], _T],
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    frozen: bool = False,
    metadata: dict[str, Any] | None = None,
    kw_only: _MISSING_TYPE = MISSING,  # type: ignore
) -> _T: ...


@overload
def field(
    *,
    default: _MISSING_TYPE = MISSING,  # type: ignore
    default_factory: _MISSING_TYPE = MISSING,  # type: ignore
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    frozen: bool = False,
    metadata: dict[str, Any] | None = None,
    kw_only: _MISSING_TYPE = MISSING,  # type: ignore
) -> Any: ...


def field(
    *,
    default: Any = MISSING,
    default_factory: Callable[[], Any] | _MISSING_TYPE = MISSING,  # type: ignore
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    frozen: bool = False,
    metadata: dict[str, Any] | None = None,
    kw_only: bool | _MISSING_TYPE = MISSING,  # type: ignore
) -> Any:
    """Like :func:`dataclasses.field` but marks the field as frozen when requested."""

    if frozen:
        metadata = (metadata or {}) | {"frozen": True}
        return FrozenFieldPlaceholder(
            default=default,
            default_factory=default_factory,
            init=init,
            repr=repr,
            hash=hash,
            compare=compare,
            metadata=metadata,
            kw_only=kw_only,
        )

    return std_field(
        default=default,
        default_factory=default_factory,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata=metadata,
        kw_only=kw_only,
    )


def _freeze_fields[T](
    cls: type[T], *, classvar_frozen_assignment: Literal["patch", "replace", "error"] = "patch"
) -> type[T]:
    """
    A decorator that makes fields of a dataclass immutable, if they have the `frozen` metadata set to True.

    This is done by replacing the fields with FrozenField descriptors.

    Args:
        cls: The class to make immutable, must be a dataclass.
        classvar_frozen_assignment: The behaviour of frozen fields when you try to assign to the same name in the class body.

    Raises:
        TypeError: If cls is not a dataclass

    See Also:
        - `semimutable.dataclass`: Elaborates on what classvar_frozen_assignment does.
    """

    cls_fields = getattr(cls, "__dataclass_fields__", None)
    if cls_fields is None:  # pragma: no cover
        raise TypeError(f"{cls} is not a dataclass")

    params = getattr(cls, "__dataclass_params__")
    # _DataclassParams(init=True,repr=True,eq=True,order=True,unsafe_hash=False,
    #                   frozen=True,match_args=True,kw_only=False,slots=False,
    #                   weakref_slot=False)
    if params.frozen:
        return cls

    if classvar_frozen_assignment == "replace":  # We don't need to do anything special, just return the class.
        new_cls = cls
    else:
        # For "patch" and "error", we need to replace the metaclass's __getattribute__ and __setattr__ methods to hook
        # into the class variable assignment and retrieval for frozen fields. Either to patch the class variable assignment
        # to a hidden variable, or to raise an error if the field is frozen and the class variable is assigned to.
        metacls: type[type[T]] = cls.__class__  # type: ignore  # typeshed bug, should be type[object] but it is annotated as property
        # The following two methods are unbound methods despite what pyright says.
        orig_meta_getattribute = metacls.__getattribute__
        orig_meta_setattr = metacls.__setattr__

        if classvar_frozen_assignment == "patch":

            def meta_getattribute(cls: type[T], name: str) -> Any:
                try:
                    descriptor_vars = orig_meta_getattribute(cls, "__frozen_dataclass_descriptors__")
                    if name in descriptor_vars:
                        return orig_meta_getattribute(cls, "__cls_var_" + name)
                except AttributeError:
                    # If the class does not have __frozen_dataclass_descriptors__, we can just return the original attribute
                    pass
                return orig_meta_getattribute(cls, name)

            def meta_setattr(cls: type[T], name: str, value: Any) -> None:
                # If the name is a frozen field, we need to set it on another attribute
                try:
                    descriptor_vars = orig_meta_getattribute(cls, "__frozen_dataclass_descriptors__")
                    if name in descriptor_vars:
                        return orig_meta_setattr(cls, "__cls_var_" + name, value)
                except AttributeError:
                    # If the class does not have __frozen_dataclass_descriptors__, we can just set on the original attribute
                    pass
                return orig_meta_setattr(cls, name, value)

        elif classvar_frozen_assignment == "error":

            def meta_getattribute(cls: type[T], name: str) -> Any:
                try:
                    descriptor_vars = orig_meta_getattribute(cls, "__frozen_dataclass_descriptors__")
                    if name in descriptor_vars:
                        raise FrozenFieldError(name)
                except AttributeError:
                    # If the class does not have __frozen_dataclass_descriptors__, we can just return the original attribute
                    pass
                return orig_meta_getattribute(cls, name)

            def meta_setattr(cls: type[T], name: str, value: Any) -> None:
                # If the name is a frozen field, we need to set it on another attribute
                try:
                    descriptor_vars = orig_meta_getattribute(cls, "__frozen_dataclass_descriptors__")
                    if name in descriptor_vars:
                        raise FrozenFieldError(name)
                except AttributeError:
                    # If the class does not have __frozen_dataclass_descriptors__, we can just set on the original attribute
                    pass
                return orig_meta_setattr(cls, name, value)

        else:
            raise ValueError(f"Invalid classvar_frozen_assignment value: {classvar_frozen_assignment!r}")

        # Create a new metaclass that overrides __getattribute__ to allow setting class variables on frozen fields descriptors
        # We cannot just set metacls.__getattribute__ because it would override the original __getattribute__ of the class,
        # changing the behavior of all classes that use this metaclass.
        # It would be very bad if we patched type.__getattribute__ by accident.
        #
        # Even if we patched it in a way where it only modifies the behaviour if and only if the object is one of the registered
        # frozen dataclasses, it would likely cause slowdowns in the interpreter, as it would have to check every time any
        # object attribute is accessed whether it is a frozen dataclass or not, and the function is changed from a fast C function
        # to a Python function.
        #
        # Caveat: This would trigger the metaclass's __init_subclass__ method, which is not ideal, but it should not be common
        # to have a metaclass with __init_subclass__. Even if it has one, it is probably less surprising to have it triggered without
        # the user knowing here, than to patch it temporarily and then patch it back.
        new_meta: type[type[T]] = type(
            "FreezableDataclassMeta", (metacls,), {"__getattribute__": meta_getattribute, "__setattr__": meta_setattr}
        )  # pyright: ignore[reportAssignmentType] # pyright does not understand subclass relationships well in this usage of type()

        # If either of the following is true, we need to create a new class:
        #
        # 1. If slots are used, we need create a new class with more entries in __slots__ to allow the FrozenField
        # descriptors to work properly. This is because we need private instance variables for the FrozenField descriptors
        # to work.
        #
        # 2. If the class does not have a custom metaclass, we need to create a new class with a custom metaclass that
        # overrides __getattribute__ to allow setting class variables on frozen fields descriptors.
        # This seems to be because `type` is an immutable class.
        needs_new_class = False
        # See if we can just directly swap the class's metaclass, if so we can avoid creating a new class.
        try:
            cls.__class__ = new_meta  # pyright: ignore[reportAttributeAccessIssue]
        except TypeError:
            # TypeError: __class__ assignment only supported for mutable types or ModuleType subclasses
            # Not sure what this means, but creating a new class is the only way to go.
            needs_new_class = True

        cls_dict = dict(cls.__dict__)
        # This if block is mostly copied from dataclasses._process_class, but with extra handling for frozen fields.
        # Copyright (c) 2001-2025 Python Software Foundation; All Rights Reserved
        if "__slots__" in cls.__dict__:
            needs_new_class = True
            field_names = tuple(f.name for f in fields(cls))  # pyright: ignore[reportArgumentType]  # cls must be a dataclass
            # Make sure slots don't overlap with those in base classes.
            inherited_slots = set(itertools.chain.from_iterable(map(_get_slots, cls.__mro__[1:-1])))
            # The slots for our class.  Remove slots from our base classes.  Add
            # '__weakref__' if weakref_slot was given, unless it is already present.
            cls_dict["__slots__"] = tuple(
                itertools.filterfalse(
                    inherited_slots.__contains__,
                    itertools.chain(
                        # gh-93521: '__weakref__' also needs to be filtered out if
                        # already present in inherited_slots
                        field_names,
                        ("__weakref__",) if params.weakref_slot else (),
                    ),
                ),
            )

            # Add our frozen fields to the slots, so they can be used by descriptors.
            cls_dict["__slots__"] += tuple(FROZEN_PREFIX + field_name for field_name in field_names)

            for field_name in field_names:
                # Remove our attributes, if present. They'll still be available in _MARKER.
                cls_dict.pop(field_name, None)

            # Remove __dict__ itself.
            cls_dict.pop("__dict__", None)

            # Clear existing `__weakref__` descriptor, it belongs to a previous type:
            cls_dict.pop("__weakref__", None)  # gh-102069
        # End of copied block from dataclasses._process_class

        if needs_new_class:
            qualname = getattr(cls, "__qualname__", None)
            new_cls = new_meta(cls.__name__, cls.__bases__, cls_dict)  # pyright: ignore[reportCallIssue]
            if qualname is not None:
                new_cls.__qualname__ = qualname
        else:
            # If we don't need a new class, we can just use the original class
            new_cls = cls

    descriptor_vars = set()
    # Now we can iterate over the fields and replace the frozen fields (those with "frozen" in their metadata, as set by field(frozen=True))
    # with FrozenField descriptors.
    for f in fields(cls):  # pyright: ignore[reportArgumentType]  # cls must be a dataclass
        if "frozen" in f.metadata:
            setattr(new_cls, f.name, FrozenField(f.name))
            descriptor_vars.add(f.name)

    # This has 2 purposes:
    # 1. It caches the name of the frozen fields, so we can access them later in the metaclass's __getattribute__ and
    # __setattr__ methods. Avoiding an isinstance check on every attribute access.
    # 2. It allows external code to check if a class is a freezable dataclass, by checking if it has the
    # __frozen_dataclass_descriptors__ attribute.
    new_cls.__frozen_dataclass_descriptors__ = descriptor_vars  # pyright: ignore[reportAttributeAccessIssue]
    return new_cls


def replace_frozen_field_placeholders_with_dataclass_fields_inplace(cls: type) -> None:
    """Replaces the object created by ``field(frozen=True)`` with a dataclass field to make dataclass transformation work properly.

    This is needed because ``field(frozen=True)`` creates a magic object that errors on runtime if accessed directly, to avoid
    itself being used on a normal dataclasses rather than one with the @semimutable.dataclass decorator, as it would
    not prevent runtime mutations of the dataclass fields without the @semimutable.dataclass decorator.
    """
    for name in cls.__annotations__:
        default = getattr(cls, name, None)
        if isinstance(default, FrozenFieldPlaceholder):
            kwargs = object.__getattribute__(default, "kwargs")
            # Replace the FrozenFieldPlaceholder with a dataclass field
            setattr(cls, name, std_field(**kwargs))


@overload
def dataclass[_T](
    cls: type[_T],
    /,
    *,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
    classvar_frozen_assignment: Literal["patch", "replace", "error"] = "patch",
) -> type[_T]: ...


@overload
def dataclass[_T](
    cls: None = None,
    /,
    *,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
    classvar_frozen_assignment: Literal["patch", "replace", "error"] = "patch",
) -> Callable[[type[_T]], type[_T]]: ...


@dataclass_transform()
def dataclass[_T](
    cls: type[_T] | None = None,
    /,
    *,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
    classvar_frozen_assignment: Literal["patch", "replace", "error"] = "patch",
) -> Any:
    """Just like @dataclass, but if you use ``field(frozen=True)`` in the class, it will make that field immutable.

    Additional kwargs not supported @dataclass:
        classvar_frozen_assignment (Literal["patch", "replace"] | None):
            The behaviour of frozen fields when you try to assign to the same name in the class body.
            - "patch" will transparently assign/fetch the class variable to/from a hidden variable, making it behave
                exactly like a normal class variable at the cost of a small(?) performance penalty every time you access
                any class variable. Default is "patch".
            - "replace" will replace the FrozenField descriptor with a normal class variable, allowing you to assign to it.
                Warning: this will break the immutability of the field.
            - "error" will raise an error if you try to assign to a frozen field in the class body. This has the same
                performance penalty as "patch", but it will not allow you to assign to the field in the class body. This
                is useful for ensuring that you do not accidentally mutate the class variable, before switching to "replace".
                Otherwise, it is recommended to use "patch" or "replace" instead.
    """

    def wrap(cls: type[_T]):
        replace_frozen_field_placeholders_with_dataclass_fields_inplace(cls)
        if classvar_frozen_assignment not in ("patch", "replace", "error"):  # pragma: no cover
            raise ValueError(
                f"Invalid value for classvar_frozen_assignment: {classvar_frozen_assignment}. "
                "Expected 'patch', 'replace', or 'error'."
            )
        klass = std_dataclass(
            init=init,
            repr=repr,
            eq=eq,
            order=order,
            unsafe_hash=unsafe_hash,
            frozen=frozen,
            match_args=match_args,
            kw_only=kw_only,
            slots=slots,
            weakref_slot=weakref_slot,
        )(cls)
        return _freeze_fields(klass, classvar_frozen_assignment=classvar_frozen_assignment)

    # See if we're being called as @dataclass or @dataclass().
    if cls is None:
        # We're called with parens.
        return wrap

    # We're called as @dataclass without parens.
    return wrap(cls)

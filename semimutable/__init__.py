import itertools
from dataclasses import (
    KW_ONLY,
    MISSING,
    Field,
    FrozenInstanceError,
    InitVar,
    asdict,
    astuple,
    field,
    fields,
    is_dataclass,
    make_dataclass,
    replace,
)
from dataclasses import dataclass as std_dataclass
from typing import Any, Callable, Final, Literal, Never, Self, dataclass_transform, overload, override

__version__ = "0.1.0a0"

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
__all__ += ["frozen_field", "FrozenField", "freeze_fields", "FrozenFieldPlaceholder"]

# Note: This prefix CANNOT be dunder, because we used dynamic class creation it would cause name mangling issues.
FROZEN_PREFIX: Final = "_frozen_"


# https://stackoverflow.com/questions/74714300/paramspec-for-a-pre-defined-function-without-using-generic-callablep
# Note: This is actually less accurate of a typing than Callable[P, T], but see
# https://github.com/microsoft/pyright/discussions/10727, pyright could not resolve overloads properly
def signature_from[Fn: Callable](_original: Fn) -> Callable[[Fn], Fn]:
    """Copies the signature of a function to another function."""

    def _decorator(func: Fn) -> Fn:
        return func

    return _decorator


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
            msg = f"Attribute `{self._private_name[len(FROZEN_PREFIX) :]}` is immutable!"
            raise TypeError(msg) from None

        setattr(instance, self._private_name, value)


error = RuntimeError(
    "This field is created via frozen_field() but the @freezable_dataclass decorator is not used on the dataclass. "
    "Replace your use of @dataclass with @freezable_dataclass."
)


class FrozenFieldPlaceholder:
    """A placeholder for a frozen field before @dataclass transformation.

    If @freezable_dataclass is not used, this will raise an error when accessed. Otherwise, it will be replaced with a FrozenField descriptor.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the placeholder with the given arguments."""
        super().__setattr__("kwargs", kwargs)

    # dataclass uses getattr() to access fields, overriding __getattribute__ allows us to raise an error at declaration time
    @override
    def __getattribute__(self, name: str, /) -> Never:
        raise error


@signature_from(field)
def frozen_field(**kwargs: Any) -> Any:
    """A field that is immutable after it has been set. See `dataclasses.field` for more information."""
    metadata = kwargs.pop("metadata", {}) | {"frozen": True}
    return FrozenFieldPlaceholder(**kwargs, metadata=metadata)


def freeze_fields[T](
    cls: type[T], *, classvar_frozen_assignment: Literal["patch", "replace", "error"] = "patch"
) -> type[T]:
    """
    A decorator that makes fields of a dataclass immutable, if they have the `frozen` metadata set to True.

    This is done by replacing the fields with FrozenField descriptors.

    Args:
        cls: The class to make immutable, must be a dataclass.
        classvar_frozen_assignment: The behaviour of frozen fields when you try to assign to the same name in the class body.
            - "patch" will transparently assign/fetch the class variable to/from a hidden variable, making it behave
                exactly like a normal class variable at the cost of a small(?) performance penalty every time you access
                any class variable (This includes accessing any methods, as they are class variables too).
            - "replace" will replace the FrozenField descriptor with a normal class variable, allowing you to assign to it.
            - "error" will raise an error if you try to assign to a frozen field in the class body. This has the same
                performance penalty as "patch", but it will not allow you to assign to the field in the class body. This
                is useful for ensuring that you do not accidentally mutate the class variable, before switching to "replace".
                Otherwise, it is recommended to use "patch" or "replace" instead.
    Raises:
        TypeError: If cls is not a dataclass
    """

    cls_fields = getattr(cls, "__dataclass_fields__", None)
    if cls_fields is None:
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
        metacls = cls.__class__
        orig_meta_getattribute = metacls.__getattribute__  # This is an unbound method
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
            pass

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
        new_meta = type(
            "FreezableDataclassMeta", (metacls,), {"__getattribute__": meta_getattribute, "__setattr__": meta_setattr}
        )

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
            cls.__class__ = new_meta
        except TypeError:
            # TypeError: __class__ assignment only supported for mutable types or ModuleType subclasses
            # Not sure what this means, but creating a new class is the only way to go.
            needs_new_class = True

        cls_dict = dict(cls.__dict__)
        # This if block is mostly copied from dataclasses._process_class, but with extra handling for frozen fields.
        if "__slots__" in cls.__dict__:
            needs_new_class = True
            field_names = tuple(f.name for f in fields(cls))
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

        if needs_new_class:
            qualname = getattr(cls, "__qualname__", None)
            new_cls = new_meta(cls.__name__, cls.__bases__, cls_dict)
            if qualname is not None:
                new_cls.__qualname__ = qualname
        else:
            # If we don't need a new class, we can just use the original class
            new_cls = cls

    descriptor_vars = set()
    # Now we can iterate over the fields and replace the frozen fields (those with "frozen" in their metadata, as set by frozen_field())
    # with FrozenField descriptors.
    for f in fields(cls):
        if "frozen" in f.metadata:
            setattr(new_cls, f.name, FrozenField(f.name))
            descriptor_vars.add(f.name)

    # This has 2 purposes:
    # 1. It caches the name of the frozen fields, so we can access them later in the metaclass's __getattribute__ and
    # __setattr__ methods. Avoiding an isinstance check on every attribute access.
    # 2. It allows external code to check if a class is a freezable dataclass, by checking if it has the
    # __frozen_dataclass_descriptors__ attribute.
    new_cls.__frozen_dataclass_descriptors__ = descriptor_vars
    return new_cls


def _get_slots(cls: type):
    match cls.__dict__.get("__slots__"):
        # `__dictoffset__` and `__weakrefoffset__` can tell us whether
        # the base type has dict/weakref slots, in a way that works correctly
        # for both Python classes and C extension types. Extension types
        # don't use `__slots__` for slot creation
        case None:
            slots = []
            if getattr(cls, "__weakrefoffset__", -1) != 0:
                slots.append("__weakref__")
            if getattr(cls, "__dictoffset__", -1) != 0:
                slots.append("__dict__")
            yield from slots
        case str(slot):
            yield slot
        # Slots may be any iterable, but we cannot handle an iterator
        # because it will already be (partially) consumed.
        case iterable if not hasattr(iterable, "__next__"):
            yield from iterable
        case _:
            raise TypeError(f"Slots of '{cls.__name__}' cannot be determined")


def replace_frozen_field_placeholders_with_dataclass_fields_inplace(cls: type) -> None:
    """Replaces the object created by frozen_field() with a dataclass field to make dataclass transformation work properly.

    This is needed because frozen_field() creates a magic object that errors on runtime if accessed directly, to avoid
    itself being used on a normal dataclasses rather than one with the @freezable_dataclass decorator, as it would
    not prevent runtime mutations of the dataclass fields without the @freezable_dataclass decorator.
    """
    for name in cls.__annotations__:
        default = getattr(cls, name, None)
        if isinstance(default, FrozenFieldPlaceholder):
            kwargs = object.__getattribute__(default, "kwargs")
            # Replace the FrozenFieldPlaceholder with a dataclass field
            setattr(cls, name, field(**kwargs))


@dataclass_transform()
@signature_from(std_dataclass)
def dataclass[_T](cls: type[_T] | None = None, /, **kwargs: Any) -> Any:
    """Just like @dataclass, but if you use frozen_field() in the class, it will make that field immutable.

    Additional kwargs not supported @dataclass:
        classvar_frozen_assignment (Literal["patch", "replace"] | None):
            The behaviour of frozen fields when you try to assign to the same name in the class body.
            - "patch" will transparently assign/fetch the class variable to/from a hidden variable, making it behave
                exactly like a normal class variable at the cost of a small(?) performance penalty every time you access
                any class variable. Default is "patch".
            - "replace" will replace the FrozenField descriptor with a normal class variable, allowing you to assign to it.
                Warning: this will break the immutability of the field.
    """

    def wrap(cls: type[_T]):
        replace_frozen_field_placeholders_with_dataclass_fields_inplace(cls)
        classvar_frozen_assignment = kwargs.pop(
            "classvar_frozen_assignment", "patch"
        )  # Not supported by dataclass, so we remove it.
        if classvar_frozen_assignment not in ("patch", "replace", "error"):
            raise ValueError(
                f"Invalid value for classvar_frozen_assignment: {classvar_frozen_assignment}. "
                "Expected 'patch' or 'replace'."
            )
        klass = std_dataclass(**kwargs)(cls)
        return freeze_fields(klass, classvar_frozen_assignment=classvar_frozen_assignment)

    # See if we're being called as @dataclass or @dataclass().
    if cls is None:
        # We're called with parens.
        return wrap

    # We're called as @dataclass without parens.
    return wrap(cls)

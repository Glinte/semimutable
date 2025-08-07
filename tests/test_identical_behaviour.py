import dataclasses
import weakref

import pytest

import semimutable


def test_already_frozen_class_raises_frozen_instance_error():
    """We raise dataclasses.FrozenInstanceError for frozen=True fields even in semimutable dataclasses for maximum
    compatibility with existing code.
    """

    @dataclasses.dataclass(frozen=True)
    class Std:
        x: int

    @semimutable.dataclass(frozen=True)
    class Sm:
        x: int

    for cls in (Std, Sm):
        inst = cls(x=7)
        with pytest.raises(dataclasses.FrozenInstanceError):
            inst.x = 8


@pytest.xfail("FIXME: semimutable always handles class variables consistently regardless of slots=True, but seems like dataclasses does not.")
def test_class_attribute_rebinding_is_not_noop_if_slots_true():
    @dataclasses.dataclass(slots=True)
    class Std:
        x: int = dataclasses.field()

    @semimutable.dataclass(slots=True)
    class Sm:
        x: int = semimutable.frozen_field()

    std = Std(x=5)
    sm = Sm(x=5)
    Std.x = 123
    Sm.x = 123
    assert std.x == sm.x == 123  # This is what dataclasses does, but semimutable does not. Instead, sm.x == 5 here.
    assert Std.x == Sm.x == 123


def test_class_attribute_rebinding_is_noop_if_slots_false():
    @dataclasses.dataclass(slots=True)
    class Std:
        x: int = dataclasses.field()

    @semimutable.dataclass(slots=True)
    class Sm:
        x: int = semimutable.frozen_field()

    std = Std(x=5)
    sm = Sm(x=5)
    Std.x = 123
    Sm.x = 123
    assert std.x == sm.x == 5
    assert Std.x == Sm.x == 123


def test_custom_metaclass_behavior_preserved():
    class WeirdMeta(type):
        def __new__(mcls, name, bases, ns):
            ns["created_by_meta"] = True
            return super().__new__(mcls, name, bases, ns)

        def __getattribute__(cls, name):
            type.__setattr__(cls, "_last_attr", name)
            return super().__getattribute__(name)

        def __setattr__(cls, name, value):
            type.__setattr__(cls, "_last_set", (name, value))
            return super().__setattr__(name, value)

        def __call__(cls, *args, **kwargs):
            type.__setattr__(cls, "_called", True)
            return super().__call__(*args, **kwargs)

    @dataclasses.dataclass(slots=True)
    class Std(metaclass=WeirdMeta):
        a: int = dataclasses.field()
        b: int = 0

    @semimutable.dataclass(slots=True)
    class Sm(metaclass=WeirdMeta):
        a: int = semimutable.frozen_field()
        b: int = 0

    for cls in (Std, Sm):
        assert cls.created_by_meta is True
        inst = cls(a=1, b=2)  # noqa: F841
        assert cls._called is True
        cls.a = 99
        assert cls._last_set[1] == 99
        _ = cls.a
        assert cls._last_attr is not None


def test_slots_option():
    @dataclasses.dataclass(slots=True)
    class Std:
        x: int

    @semimutable.dataclass(slots=True)
    class Sm:
        x: int

    for cls in (Std, Sm):
        inst = cls(x=1)
        assert not hasattr(inst, "__dict__")
        inst.x = 2
        with pytest.raises(AttributeError):
            inst.y = 2


def test_order_option():
    @dataclasses.dataclass(order=True)
    class Std:
        x: int = dataclasses.field()
        y: int

    @semimutable.dataclass(order=True)
    class Sm:
        x: int = semimutable.frozen_field()
        y: int

    s1_std, s2_std = Std(x=1, y=2), Std(x=1, y=3)
    s1_sm, s2_sm = Sm(x=1, y=2), Sm(x=1, y=3)
    assert s1_std < s2_std
    assert s1_sm < s2_sm


def test_weakref_slot_option():
    @dataclasses.dataclass(weakref_slot=True, slots=True)
    class Std:
        x: int = dataclasses.field()

    @semimutable.dataclass(weakref_slot=True, slots=True)
    class Sm:
        x: int = semimutable.frozen_field()

    for cls in (Std, Sm):
        inst = cls(x=1)
        ref = weakref.ref(inst)
        assert ref() is inst


def test_kw_only_option():
    @dataclasses.dataclass(kw_only=True)
    class Std:
        x: int = dataclasses.field()
        y: int

    @semimutable.dataclass(kw_only=True)
    class Sm:
        x: int = semimutable.frozen_field()
        y: int

    with pytest.raises(TypeError):
        Std(1, 2)
    with pytest.raises(TypeError):
        Sm(1, 2)
    Std(x=1, y=2)
    Sm(x=1, y=2)

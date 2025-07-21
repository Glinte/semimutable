import dataclasses

import pytest

from semimutable import dataclass, frozen_field


# ---------------------------------------------------------------------
# 1. Happy‑path basics
# ---------------------------------------------------------------------
@dataclass(slots=True)
class Simple:
    x: int = frozen_field()
    y: int = 0  # normal, mutable field


def test_frozen_field_is_immutable():
    obj = Simple(x=1, y=2)
    with pytest.raises(TypeError):
        obj.x = 99


def test_non_frozen_field_is_mutable():
    obj = Simple(x=1, y=2)
    obj.y = 42
    assert obj.y == 42


# ---------------------------------------------------------------------
# 2. Multiple frozen fields
# ---------------------------------------------------------------------


@dataclass
class Multi:
    a: int = frozen_field()
    b: str = frozen_field()
    c: float = 0.0


def test_multiple_frozen_fields():
    m = Multi(a=1, b="hi", c=3.14)
    with pytest.raises(TypeError):
        m.a = 10
    with pytest.raises(TypeError):
        m.b = "bye"
    m.c = 2.71
    assert m.c == 2.71


# ---------------------------------------------------------------------
# 3. Using plain @dataclass should explode early
# ---------------------------------------------------------------------


def test_plain_dataclass_is_refused():
    # Defining the class itself should raise, because dataclasses tries
    # to inspect the placeholder and hits its trap.
    with pytest.raises(RuntimeError):

        @dataclasses.dataclass
        class Bad:
            x: int = frozen_field()  # noqa: F841


# ---------------------------------------------------------------------
# 4. Opt‑in full dataclass freezing still works
# ---------------------------------------------------------------------


@dataclass(frozen=True)  # passes through to dataclass(frozen=True)
class AlreadyFrozen:
    z: int


def test_already_frozen_class_behaves():
    inst = AlreadyFrozen(z=7)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inst.z = 8


# ---------------------------------------------------------------------
# 5. Re‑assignment at class level is ignored
# ---------------------------------------------------------------------


def test_class_attribute_rebinding_is_noop():
    s = Simple(x=5, y=6)
    # This sets a *class* attribute, not the instance field.
    Simple.x = 123
    assert s.x == 5  # instance still sees old value
    assert Simple.x == 123  # class sees new value

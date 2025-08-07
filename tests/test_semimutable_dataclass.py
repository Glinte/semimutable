import dataclasses

import pytest

from semimutable import FrozenFieldError, dataclass, frozen_field


def test_frozen_field_is_immutable():
    @dataclass(slots=True)
    class Sm:
        x: int = frozen_field()
        y: int = 0

    sm = Sm(x=1, y=2)

    with pytest.raises(TypeError):
        sm.x = 99


def test_non_frozen_field_is_mutable():
    @dataclass(slots=True)
    class Sm:
        x: int = frozen_field()
        y: int = 0

    sm = Sm(x=1, y=2)
    sm.y = 42


def test_plain_dataclass_is_refused():
    with pytest.raises(RuntimeError):

        @dataclasses.dataclass
        class Bad:
            x: int = frozen_field()

    @dataclass
    class Good:
        x: int = frozen_field()

    Good(x=1)


def test_classvar_assignment_replace_allows_mutation():
    @dataclass(classvar_frozen_assignment="replace")
    class Sm:
        x: int = frozen_field()

    Sm.x = 10
    sm = Sm(x=1)
    # This should not raise an error because the descriptor is already replaced with the literal 10, suppressing all
    # further attempts to mutate instance variables.
    sm.x = 5
    assert sm.x == 5


def test_classvar_assignment_error_raises():
    @dataclass(classvar_frozen_assignment="error")
    class Sm:
        x: int = frozen_field()

    with pytest.raises(FrozenFieldError):
        Sm.x = 10

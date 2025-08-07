# Semimutable

[![Tests](https://github.com/Glinte/semimutable/actions/workflows/ci.yml/badge.svg)](https://github.com/Glinte/semimutable/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/Glinte/semimutable/branch/main/graph/badge.svg)](https://codecov.io/gh/Glinte/semimutable)

A dataclass drop-in that allows you to define individual fields as immutable.

## Usage

Simply replace all your `dataclasses` imports with `semimutable`, and use `frozen_field` to replace `field` for the fields you want to be immutable.

`frozen_field` takes in the same parameters as `dataclasses.field`, so you can specify default values, default factories, and other options just like you would with a regular dataclass field.

Here is one example from our tests.

```python
from semimutable import dataclass, frozen_field

@dataclass
class Simple:
    x: int = frozen_field()
    y: int = 0 # normal, mutable field

def test_frozen_field_is_immutable():
    obj = Simple(x=1, y=2)
    with pytest.raises(TypeError):
        obj.x = 99

def test_non_frozen_field_is_mutable():
    obj = Simple(x=1, y=2)
    obj.y = 42
    assert obj.y == 42
```

## Credits

Parts of this library are derived from Python's standard library `dataclasses` module. The original implementation is distributed under the Python Software Foundation License. See `LICENSE.PSF` for the full license text.
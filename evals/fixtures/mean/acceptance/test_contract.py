import pytest
from solution import mean


def test_mean():
    assert mean([1, 2, 3]) == 2
    with pytest.raises(ValueError):
        mean([])

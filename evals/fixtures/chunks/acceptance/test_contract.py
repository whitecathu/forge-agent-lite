import pytest
from solution import chunks


def test_chunks():
    assert chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert chunks([], 3) == []
    with pytest.raises(ValueError):
        chunks([1], 0)

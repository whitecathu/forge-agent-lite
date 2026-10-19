from solution import merge


def test_merge():
    a = {"x": 1}
    b = {"x": 2, "y": 3}
    assert merge(a, b) == b
    assert a == {"x": 1}

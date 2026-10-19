from solution import overlaps


def test_overlap():
    assert not overlaps((1, 2), (2, 3))
    assert overlaps((1, 4), (2, 3))
    assert not overlaps((1, 1), (0, 2))

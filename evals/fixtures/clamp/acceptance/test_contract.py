from solution import clamp


def test_clamp():
    assert clamp(-2, 0, 10) == 0
    assert clamp(15, 0, 10) == 10
    assert clamp(5, 0, 10) == 5

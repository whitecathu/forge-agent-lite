from solution import divide


def test_divide():
    assert divide(3, 2) == 1.5
    assert divide(1, 0) is None

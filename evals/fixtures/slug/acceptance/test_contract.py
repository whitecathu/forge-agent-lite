from solution import slug


def test_slug():
    assert slug("  Hello   World  ") == "hello-world"
    assert slug("A\tB") == "a-b"

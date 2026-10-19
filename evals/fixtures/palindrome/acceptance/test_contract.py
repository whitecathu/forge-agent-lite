from solution import is_palindrome


def test_palindrome():
    assert is_palindrome("A man, a plan, a canal: Panama")
    assert not is_palindrome("abc")

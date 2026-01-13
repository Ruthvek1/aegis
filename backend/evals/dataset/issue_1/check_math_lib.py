from math_lib import add, subtract, multiply, divide


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(2, 3) == 6


def test_divide():
    assert divide(6, 2) == 3.0


# The issue is that divide(6, 0) throws ZeroDivisionError instead of raising ValueError("Cannot divide by zero")

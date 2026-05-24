from test_env.hello import greet


def test_greet_default():
    result = greet("World")
    assert result == "Hello, World! Welcome to test_env."


def test_greet_custom_name():
    result = greet("Claude")
    assert result == "Hello, Claude! Welcome to test_env."


def test_greet_empty_string():
    result = greet("")
    assert result == "Hello, ! Welcome to test_env."

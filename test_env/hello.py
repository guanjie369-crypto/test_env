def greet(name: str) -> str:
    return f"Hello, {name}! Welcome to test_env."

def main():
    message = greet("World")
    print(message)
    print(f"Python is running from: {__file__}")

if __name__ == "__main__":
    main()

import sys
from string_utils import get_first_char


def main():
    try:
        val = get_first_char("")
        if val is None:
            print("Pass")
            sys.exit(0)
        else:
            print("Failed: expected None, got", val)
            sys.exit(1)
    except IndexError:
        print("Failed: IndexError raised")
        sys.exit(1)
    except Exception as e:
        print("Failed: Unexpected error", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

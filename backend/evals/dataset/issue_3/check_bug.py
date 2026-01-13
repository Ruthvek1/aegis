import sys
from dict_utils import get_value


def main():
    try:
        val = get_value({"a": 1}, "b")
        if val is None:
            print("Pass")
            sys.exit(0)
        else:
            print("Failed: expected None, got", val)
            sys.exit(1)
    except KeyError:
        print("Failed: KeyError raised")
        sys.exit(1)
    except Exception as e:
        print("Failed: Unexpected error", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

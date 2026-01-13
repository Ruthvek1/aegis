import sys
from concat_utils import concat_strings


def main():
    try:
        val = concat_strings("a", 1)
        if val == "a1":
            print("Pass")
            sys.exit(0)
        else:
            print("Failed: expected 'a1', got", val)
            sys.exit(1)
    except TypeError:
        print("Failed: TypeError raised")
        sys.exit(1)
    except Exception as e:
        print("Failed: Unexpected error", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

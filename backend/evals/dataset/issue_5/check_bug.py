import sys
from math_utils import multiply_list


def main():
    try:
        val = multiply_list([2, 3, 4])
        if val == 24:
            print("Pass")
            sys.exit(0)
        else:
            print("Failed: expected 24, got", val)
            sys.exit(1)
    except Exception as e:
        print("Failed: Unexpected error", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

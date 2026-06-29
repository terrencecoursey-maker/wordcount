import sys


def count_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    words = text.split()
    return len(lines), len(words), len(text)


def main():
    if len(sys.argv) != 2:
        print("Usage: python wordcount.py <file>")
        sys.exit(1)

    path = sys.argv[1]
    lines, words, chars = count_file(path)
    print(f"Lines:  {lines}")
    print(f"Words:  {words}")
    print(f"Chars:  {chars}")


if __name__ == "__main__":
    main()

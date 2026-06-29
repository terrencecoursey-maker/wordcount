import tempfile
import os
from wordcount import count_file


def test_basic():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("hello world\nfoo bar baz\n")
        name = f.name
    try:
        lines, words, chars = count_file(name)
        assert lines == 2
        assert words == 5
        assert chars == 23
    finally:
        os.unlink(name)


def test_empty():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        name = f.name
    try:
        lines, words, chars = count_file(name)
        assert lines == 0
        assert words == 0
        assert chars == 0
    finally:
        os.unlink(name)

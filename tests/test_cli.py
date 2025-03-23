import random

import pytest

from sprat.__main__ import color_textwrap

RESET = "\x1b[0m"
GREY = "\x1b[37m"
RED = "\x1b[31m"


@pytest.mark.parametrize("seed", range(1000))
def test_color_textwrap(seed):
    r = random.Random(seed)
    input = "".join(r.choice([RESET, GREY, RED, "a" * r.randint(0, 200), " "])
                    for _ in range(r.randint(0, 10)))
    output = color_textwrap(input, "    ", 80)

    decolored = output.replace(RESET, "").replace(GREY, "").replace(RED, "")
    assert "\x1b" not in decolored
    lines = decolored.rstrip("\n").split("\n")
    for line in lines:
        if " " in line[4:]:
            assert len(line) <= 80

    for (line, next_line) in zip(lines[:-1], lines[1:]):
        next_word = next_line[4:].split(" ")[0]
        if " " in line[4:] and next_word and not line.isspace():
            assert len(line) + 1 + len(next_word) > 80


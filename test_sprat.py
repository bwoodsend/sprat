import textwrap
import random
import copy

import sprat



def _index(text):
    return (textwrap.dedent(text).strip() + "\n").encode()


def _join(delta):
    return "".join(map("%s:%s\n".__mod__, delta)).encode()


def test_requires_python():
    old = sprat.Package._parse("foo", _index("""
        n:foo
        v:0.19.0
        p:>=3.8
        v:0.19.1
        p:
    """))
    self = sprat.Package._new("foo", versions={
        "0.19.0": {"requires_python": ">=3.8"},
        "0.19.1": {},
        "0.19.2": {},
    })
    assert self.delta(old) == [("n", "foo"), ("v", "0.19.2")]

    self = sprat.Package._new("foo", versions={
        "0.19.0": {"requires_python": ">=3.9"},
        "0.19.1": {},
    })
    assert self.delta(old) == [("n", "foo"), ("v", "0.19.0"), ("p", ">=3.9")]

    old._update(_join(self.delta(old)))
    assert self == old

    old = sprat.Package._new("foo", versions={
        'v1': {'requires_python': '>=3.8', 'yanked': 'broken version handling'},
        'v2': {'requires_python': '>=3.8', 'yanked': 'crashes on windows'},
    })
    new = sprat.Package._new("foo", versions={
        'v0': {},
        'v2': {'yanked': 'broken version handling'},
    })
    assert new.delta(old) == [("n", "foo"), ("V", "v1"), ("v", "v0"), ("p", ""), ("v", "v2"), ("p", ""), ("y", "broken version handling")]


def _random_package(seed):
    _random = random.Random(seed)
    return sprat.Package(
        _random.choice(["foo", "FOO", "Foo"]),
        {f"classifier {i}" for i in range(3) if _random.random() > 0.6},
        {f"keyword {i}" for i in range(3) if _random.random() > 0.6},
        _random.choice(["", "MIT", "BSD"]),
        _random.choice(["", "summary 0", "summary 1"]),
        {f"url {i}": _random.choice(["foo.com", "foo.org"]) for i in range(3) if _random.random() > 0.6},
        {f"v{i}": _random_release(_random) for i in range(3) if _random.random() > 0.5},
    )


def _random_release(_random):
    out = {}
    if _random.random() > 0.5:
        out["requires_python"] = _random.choice([">=3.8", ">=3.10"])
    if _random.random() > 0.5:
        out["yanked"] = _random.choice(["", "broken version handling", "crashes on windows"])
    return out


def test_fuzz():
    old = _random_package(-1)
    history = old.delta(old.null)
    for i in range(1000):
        self = _random_package(i)
        assert sprat.Package._parse("foo", _join(self.delta(self.null)))

        delta = self.delta(old)
        new = self
        self = copy.deepcopy(old)
        self._update(_join(delta))
        if self.versions != new.versions:
            print()
            print("old:   _latest_requires_python", old._latest_requires_python)
            print("old:  ", old.versions)
            print("new:  ", new.versions)
            print("self: ", self.versions)
            print("delta:", [i for i in delta if i[0] in "vVpyY"])
        assert self == new

        history += delta
        assert sprat.Package._parse("foo", _join(history)) == self
        old = self

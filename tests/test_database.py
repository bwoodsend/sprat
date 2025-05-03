import textwrap
import random
import copy
import io
from pathlib import Path
import tempfile

import pytest
import trove_classifiers

import sprat


def _index(text):
    return (textwrap.dedent(text).strip() + "\n").encode()


def _join(delta):
    return "".join(map("%s:%s\n".__mod__, delta)).encode()


def test_requires_python():
    old = sprat.Package.parse(b"foo", _index("""
        n:foo
        v:0.19.0
        p:>=3.8
        v:0.19.1
        p:
    """))
    self = sprat.Package("foo", versions={
        "0.19.0": {"requires_python": ">=3.8"},
        "0.19.1": {},
        "0.19.2": {},
    })
    assert self.delta(old) == [("n", "foo"), ("v", "0.19.2")]

    self = sprat.Package("foo", versions={
        "0.19.0": {"requires_python": ">=3.9"},
        "0.19.1": {},
    })
    assert self.delta(old) == [("n", "foo"), ("v", "0.19.0"), ("p", ">=3.9")]

    old._update(_join(self.delta(old)))
    assert self == old

    old = sprat.Package("foo", versions={
        'v1': {'requires_python': '>=3.8', 'yanked': 'broken version handling'},
        'v2': {'requires_python': '>=3.8', 'yanked': 'crashes on windows'},
    })
    new = sprat.Package("foo", versions={
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
        assert sprat.Package.parse(b"foo", _join(self.delta(self.null)))

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
        assert sprat.Package.parse(b"foo", _join(history)) == self
        old = self


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("size", [1, 2, 10, 1000])
def test_read_database(seed, size):
    _random = random.Random(seed)
    file = io.BytesIO()
    for i in range(size):
        file.write(b"n:%s\nx:%s\n\n" % (b"a" * _random.randint(0, 10),
                                        b"b" * _random.randint(0, 10)))
    _random = random.Random(seed)
    file.seek(0)
    for (name, chunk) in sprat._database._read_database_raw(file, 50):
        assert name == b"a" * _random.randint(0, 10)
        assert chunk == b"x:%s\n" % (b"b" * _random.randint(0, 10))


@pytest.fixture(scope="module")
def fake_workspace():
    from test_update import fake_upstream, packed
    with tempfile.TemporaryDirectory() as workspace:
        old_cache_root = sprat._database.cache_root
        try:
            sprat._database.cache_root = Path(workspace)
            with fake_upstream(packed()[1]):
                sprat.update()
            yield workspace
        finally:
            sprat._database.cache_root = old_cache_root


def test_raw_iter_unique_and_ordered(fake_workspace):
    names = [i[0] for i in sprat.raw_iter()]
    assert len(names) > 140
    assert len(names) == len(set(names))
    assert names == sorted(names, key=sprat.sluggify_b)


def test_bulk_lookup(fake_workspace):
    names = [i[0].decode() for i in sprat.raw_iter()]
    for (name, package) in zip(names, sprat.bulk_lookup(names)):
        assert name == package.name

    random.Random(0).shuffle(names)
    for (name, package) in zip(names, sprat.bulk_lookup(names)):
        assert name == package.name

    packages = list(sprat.bulk_lookup(["rp", "RP", "jk.-Flexdata", "RP", "rp"]))
    assert [i.name for i in packages] == ["rp", "rp", "jk_flexdata", "rp", "rp"]

    packages_iter = sprat.bulk_lookup(["rp", "a..B_C", "rp", "noodles"])
    assert next(packages_iter) == sprat.lookup("rp")
    with pytest.raises(sprat.NoSuchPackageError, match="a..B_C"):
        next(packages_iter)


def test_with_prefix(fake_workspace):
    assert list(sprat.with_prefix("m")) == list(sprat.bulk_lookup([
        "MagmaPandas", "marimo", "marimo-base", "mcp-server-elastic",
        "methodwebscan", "miracle-helper", "monkdb", "moyopy"
    ]))
    assert list(sprat.with_prefix("MaRiMo")) == list(sprat.bulk_lookup([
        "marimo", "marimo-base"
    ]))
    assert list(sprat.with_prefix("pytest")) == list(sprat.bulk_lookup([
        "pytest-broadcaster", "pytest-mongo"
    ]))
    assert list(sprat.with_prefix("sight")) == []
    assert list(sprat.with_prefix("shipyard-")) == [sprat.lookup("shipyard-trello")]
    assert list(sprat.with_prefix("shipyard_")) == [sprat.lookup("shipyard-trello")]
    assert list(sprat.with_prefix("shipyard-trello")) == [sprat.lookup("shipyard-trello")]

    assert list(sprat.raw_iter()) == list(sprat.raw_with_prefix(""))


def test_crude_search(fake_workspace):
    names = {i.name for i in sprat.crude_search("configuration")}
    assert "pan-analyzer" in names
    assert "clipped" in names
    assert "sage-conf" not in names

    names = {i.name for i in sprat.crude_search("configuration", False)}
    assert "sage-conf" in names

    assert [i.name for i in sprat.crude_search("aa-metenox")] == ["aa-metenox"]
    assert [i.name for i in sprat.crude_search("n:aa-metenox")] == ["aa-metenox"]
    assert [i.name for i in sprat.crude_search("aa-metenox")] == ["aa-metenox"]
    assert next(sprat.crude_search("v:0.0.1.13610532696")).name == "zuspec-be-py"

    assert [i.name for i in sprat.crude_search(r"\\G")] == []
    assert [i.name for i in sprat.crude_search(r"\\G", False)] == ["gprim"]
    assert [i.name for i in sprat.crude_search(r"\\\w", False)] == ["gprim"]
    assert [i.name for i in sprat.crude_search(r"\\\W", False)] == []
    assert [i.name for i in sprat.crude_search(r"\\\d", False)] == []
    assert [i.name for i in sprat.crude_search(r"\\\D", False)] == ["gprim"]

    assert [i.name for i in sprat.crude_search(r"^^^genetic$$$", False)] == ["gprim"]

    assert not any(sprat.crude_search("(azazaz)*"))

    names = [i.name for i in sprat.crude_search(".*")]
    assert len(names) == len(set(names))


def test_iter_no_versions(fake_workspace):
    for package in sprat.iter(ignore_versions=True):
        assert package.versions == {}


def test_classifier_sort():
    reference = trove_classifiers.sorted_classifiers
    for (lesser, greater) in zip(reference[:-1], reference[1:]):
        assert sprat.classifier_sort_key(lesser) < sprat.classifier_sort_key(greater)

    unordered = reference.copy()
    random.Random(0).shuffle(unordered)
    assert sorted(unordered, key=sprat.classifier_sort_key) == reference


@pytest.mark.parametrize("function", [
    sprat.raw_iter,
    lambda: sprat.with_prefix("a"),
    lambda: sprat.raw_crude_search("3.12"),
])
def test_interrupted_iterable(fake_workspace, function):
    count = 0
    iterable = function()
    while True:
        for (i, _) in enumerate(iterable):
            count += 1
            if i == 3:
                break
        else:
            break
    assert count == sum(1 for _ in function())
    assert count > 3

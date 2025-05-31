import random
import io
import sys
from pathlib import Path

import sprat
sys.path.append(str(Path(__file__).parents[1]))
import pack


def fuzz_string(r):
    if r.random() < 0.5:
        return "".join(chr(r.randrange(300)) for _ in range(r.randrange(5)))
    else:
        return "".join(chr(r.randrange(sys.maxunicode)) for _ in range(r.randrange(1, 3)))


def fuzz_list(r):
    return [fuzz_string(r) for _ in range(r.randrange(4))]


def fuzz(make_package):

    def test():
        for i in range(100000):
            try:
                package = make_package(random.Random(i))
            except pack.SanitationError:
                continue
            delta = package.delta(package.null)
            serialised = "".join(map("%s:%s\n".__mod__, delta)).encode() + b"\n"
            x, = sprat._database._read_database_raw(io.BytesIO(serialised), 10000)
            unpacked = sprat.Package.parse(*x)
            for field in sprat.Package.__dataclass_fields__:
                assert getattr(unpacked, field) == getattr(package, field)

    test.__name__ = make_package.__name__
    return test


@fuzz
def test_name(r):
    return pack.UpstreamPackage(fuzz_string(r), [], [], "s", "", {}, {})


@fuzz
def test_classifiers(r):
    return pack.UpstreamPackage("x", set(fuzz_list(r)), [], "s", "", {}, {})


@fuzz
def test_keywords(r):
    return pack.UpstreamPackage("x", [], set(fuzz_list(r)), "s", "", {}, {})


@fuzz
def test_license(r):
    return pack.UpstreamPackage("x", [], [], fuzz_string(r), "s", {}, {})


@fuzz
def test_summary(r):
    return pack.UpstreamPackage("x", [], [], "s", fuzz_string(r), {}, {})


@fuzz
def test_url_keys(r):
    urls = {fuzz_string(r): "https://example.com" for _ in range(r.randrange(3))}
    return pack.UpstreamPackage("x", [], [], "s", "", urls, {})


@fuzz
def test_url_values(r):
    urls = {"Homepage": fuzz_string(r) for _ in range(r.randrange(3))}
    return pack.UpstreamPackage("x", [], [], "s", "", urls, {})


@fuzz
def test_urls(r):
    urls = {fuzz_string(r): fuzz_string(r) for _ in range(r.randrange(3))}
    return pack.UpstreamPackage("x", [], [], "s", "", urls, {})


@fuzz
def test_versions(r):
    versions = {fuzz_string(r): {}}
    return pack.UpstreamPackage("x", [], [], "s", "", {}, versions)


@fuzz
def test_requires_python(r):
    versions = {fuzz_string(r): {"requires_python": fuzz_string(r)}}
    return pack.UpstreamPackage("x", [], [], "s", "", {}, versions)


@fuzz
def test_yank_reason(r):
    versions = {"v1.2.3": {"yanked": fuzz_string(r)}}
    return pack.UpstreamPackage("x", [], [], "s", "", {}, versions)

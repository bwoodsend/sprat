import random
import tempfile
import subprocess
import sys
import os
from pathlib import Path
import signal
import re
import json
import threading

import pytest

import sprat
from sprat.__main__ import color_textwrap, cli
from test_sync import fake_upstream, packed

RESET = "\x1b[0m"
GREY = "\x1b[37m"
RED = "\x1b[31m"


@pytest.fixture(scope="module")
def fake_root():
    with tempfile.TemporaryDirectory() as workspace:
        old_cache_root = sprat._database.cache_root
        try:
            sprat._database.cache_root = Path(workspace)
            with fake_upstream(packed()[1]):
                cli(["sync", "-q"])
            yield workspace
        finally:
            sprat._database.cache_root = old_cache_root


@pytest.fixture()
def run(fake_root, monkeypatch, capsys):
    monkeypatch.setattr(sprat.__main__, "RESET", RESET)
    monkeypatch.setattr(sprat.__main__, "RED", RED)
    monkeypatch.setattr(sprat.__main__, "GREY", GREY)
    monkeypatch.setenv("FORCE_COLOR", "")
    monkeypatch.setenv("SPRAT_CACHE_ROOT", fake_root)

    def run(*args):
        cli(args)
        return capsys.readouterr().out

    yield run


def snapshot_test(actual, key):
    path = Path(__file__).with_name("snapshots") / key
    if os.environ.get("WRITE_SNAPSHOTS"):
        path.write_bytes(actual.encode())
    else:
        snapshot = path.read_text("utf-8")
        assert actual == snapshot


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


def test_info_urls(run):
    output = run("info", "localstack-twisted")
    assert "Twitter" not in output
    assert "Homepage" in output
    assert "Twitter" in run("info", "localstack-twisted", "-u")


def test_info_glob(run, capsys):
    output = run("info", "pytest.*", "*O", "s*i*lo", "--json")
    names = [json.loads(line)["name"] for line in output.splitlines()]
    assert names[:3] == ["pytest-broadcaster", "pytest-mongo", "curvanato"]
    assert names[-3:] == ["pytest-mongo", "shipyard-trello", "shipyard-trello"]

    output = run("info", "pytest-*", "*o", "s*i*lo")
    snapshot_test(output, "info-glob")

    assert "StreamingCommunity" in run("info", "s*Tr*cO*")
    assert "smol_k8s_lab" in run("info", "*_k8s-*")

    with pytest.raises(SystemExit) as ex:
        run("info", "duckboat", "duckboat*", "bagpuss*")
    assert ex.value.code == 1
    output = capsys.readouterr()
    assert output.err == "sprat error: No package matching pattern 'bagpuss*'\n"
    assert output.out.count("duckboat") - output.out.count("/duckboat") == 2


def test_info_long_url(run):
    output = run("info", "-u", "SQLDbWrpr", "ChromePasswordsStealer", "posthog")
    snapshot_test(output, "long-url")


def test_info_latest_version(run):
    assert "0.0.6" in run("info", "radixhopper")
    assert re.search(r"Version +:[^.\n]+", run("info", "ZombieAdventure"))
    assert re.search(r"Version +:[^.\n]+", run("info", "letschatty"))
    assert "0.26.0.dev20250302" in run("info", "tfp-nightly")


def test_classifiers(run):
    snapshot_test(run("info", "-c", "posthog", "aim-ui"), "classifiers")


def test_info_not_found(run, capsys):
    with pytest.raises(SystemExit) as ex:
        run("info", "duckboat", "bagpuss")
    assert ex.value.code == 1
    output = capsys.readouterr()
    assert "duckdb" in output.out
    assert "sprat error: No such package 'bagpuss'" in output.err


def test_info_versions(run):
    snapshot_test(run("info", "-v", "xlviews"), "info-versions-initial-python")
    snapshot_test(run("info", "-a", "x2polygons"), "info-versions-no-python")
    snapshot_test(run("info", "-v", "radixhopper"), "info-versions-short-yank")
    snapshot_test(run("info", "-v", "vtexpy"), "info-versions-long-yank")
    snapshot_test(run("info", "-v", "pytest-broadcaster"), "info-versions-empty-yank")
    snapshot_test(run("info", "-v", "SQLDbWrpr"), "info-versions-python-any")
    snapshot_test(run("info", "-v", "pozalabs-compose"), "info-versions-chaos")


@pytest.mark.skipif(os.name == "nt", reason="Windows?")
def test_sigint(run):
    with subprocess.Popen([sys.executable, "-um", "sprat", "search", "-l", ".*.*.*.*.*.*.*a"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        assert b"metenox" in p.stdout.readline()
        p.send_signal(signal.CTRL_C_EVENT if os.name == "nt" else signal.SIGINT)
        assert p.wait(2)
        assert not p.stderr.read()


def test_piping(run):
    # Mimic running ``sprat search | head``
    with subprocess.Popen([sys.executable, "-um", "sprat", "search"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        for i in range(10):
            assert p.stdout.readline()
        p.stdout.close()
        exit_code = p.wait(2)
        stderr = p.stderr.read()
        assert exit_code == 0, stderr.decode()


@pytest.mark.parametrize("quiet", [False, True])
def test_search_no_patterns(run, quiet):
    output = run("search", *(("-q",) if quiet else ()))
    assert "cdklabs.appsync-utils" in output
    assert "smol_k8s_lab" in output
    assert "StreamingCommunity" in output
    assert RED not in output
    assert (GREY in output) != quiet
    assert ("Text-based survival adventure" in output) != quiet


def test_search_summary_wrapping(run):
    output = run("search", "Community|smallneuron|jk-flex")
    snapshot_test(output, "search-summary-wrapping")

    output = run("search", "Streaming|smallneuron|jk-flexdata", "-s", "[aeiou]")
    snapshot_test(output, "search-summary-wrapping-highlighted")

    snapshot_test(run("search", "[^ ]{30}"), "search-long-word")
    snapshot_test(run("search", "[^ ]{30}", "-so"), "search-long-word-highlighted")


def test_search_no_match(run):
    with pytest.raises(SystemExit):
        run("search", "flobbing")


def test_uninitialized(monkeypatch, tmp_path):
    p = subprocess.run([sys.executable, "-m", "sprat", "search"],
                       env={**os.environ, "SPRAT_CACHE_ROOT": str(tmp_path)},
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.returncode == 3
    assert b"sprat sync" in p.stderr


def test_search_prefix(run):
    assert run("search", "-qn", "^ra") == "radixhopper\nraspi-tools\n"
    assert run("search", "-qn", "^ra.") == "radixhopper\nraspi-tools\n"
    with pytest.raises(SystemExit):
        run("search", "-qn", "^radixhopper.")
    assert run("search", "-qn", "^radixhopper.*") == "radixhopper\n"
    assert run("search", "-qn", "^raz?") == "radixhopper\nraspi-tools\n"
    assert run("search", "-qn", "^r?at") == "atimer\n"
    assert run("search", "-qn", "^[a-f]b") == "fbgemm-gpu-nightly-genai\n"
    assert run("search", "-qn", "^xmz{,6}") == "xmlable\n"


def test_search_optimization(run, monkeypatch):
    original_raw_with_prefix = sprat.raw_with_prefix
    original_Package_parse = sprat.Package.parse
    state = threading.local()

    def raw_with_prefix(prefix):
        state.last_prefix = prefix
        return original_raw_with_prefix(prefix)

    def Package_parse(name, block, ignore_versions=False):
        state.parsed.append(name)
        return original_Package_parse(name, block, ignore_versions)

    monkeypatch.setattr(sprat, "raw_with_prefix", raw_with_prefix)
    monkeypatch.setattr(sprat.Package, "parse", Package_parse)

    state.parsed = []
    output = run("search", "--summary=sdk")
    assert not hasattr(state, "last_prefix")
    assert len(state.parsed) > 1
    assert "sdkfabric-discord" in output

    state.parsed = []
    output = run("search", "--name=sdk", "--name=fabric")
    assert not hasattr(state, "last_prefix")
    assert state.parsed == [b"sdkfabric-discord"]
    assert f"{RED}sdkfabric{RESET}-discord" in output

    state.parsed = []
    output = run("search", "--summary=sdk", "--name=^sd")
    assert state.last_prefix == "sd"
    assert state.parsed == [b"sdkfabric-discord"]
    assert f"{RED}sd{RESET}kfabric-discord" in output

    state.parsed = []
    with pytest.raises(SystemExit):
        run("search", "--summary=sdk", "--name=^s.*N.*e")
    assert state.last_prefix == "s"
    assert state.parsed == [b'simple-conf-manager', b'smallneuron',
                            b'social-interaction-cloud', b'starknet-devnet']

    state.parsed = []
    with pytest.raises(SystemExit):
        run("search", "--name=bagpuss", "-q")
    assert state.parsed == []
    assert run("search", "--name=radixhopper", "-q") == "radixhopper\n"
    assert state.parsed == []


def test_search_ignore_unsearchable(run):
    matched = re.findall("Name +: (.+)", run("search", "-l", "http"))
    assert matched == ["aa-metenox", "jinja2-fragments", "monkdb"]


def test_filter(run):
    assert run("search", "-qk", "analysis") == "x2polygons\n"
    assert run("search", "analysis", "-qk", "analysis") == "x2polygons\n"
    with pytest.raises(SystemExit):
        assert run("search", "-qk", "^analysis")
    assert run("search", "-qk", "^Spatial analysis") == "x2polygons\n"

    assert run("search", "-q", "-n", "[-.]", "-n", "z").splitlines() == [
        "lazydock-md-task", "pan-analyzer", "pozalabs-compose", "zuspec-be-py"]

    assert run("search", "-q", "-c", r"AGPLv3\+", r"k\ds") == "smol_k8s_lab\n"
    assert run("search", "-n^a", "-qc3.12").split() == \
        ["arcplot", "armcortnet", "autogluon.timeseries"]


@pytest.mark.parametrize("args", [("",), ("-q", ""), ("-n", ""), ("foo", "")])
def test_empty_search(run, capsys, args):
    with pytest.raises(SystemExit):
        run("search", *args)
    assert "Empty search terms are not allowed" in capsys.readouterr().err


@pytest.mark.parametrize("args", [("(",), ("-q", "("), ("-n", "^aa("), ("foo", "(")])
def test_invalid_regex(run, capsys, args):
    with pytest.raises(SystemExit):
        run("search", *args)
    error = capsys.readouterr().err
    if args[0] == "-n":
        assert 'Invalid search pattern "^aa(", missing ), unterminated' in error
    else:
        assert 'Invalid search pattern "(", missing ), unterminated' in error


def test_search_json(run):
    output = run("search", "-j", "zombie|aa-metenox")
    packages = [json.loads(i) for i in output.splitlines()]
    assert [i["name"] for i in packages] == ["aa-metenox", "ZombieAdventure"]
    assert "1.1.0b2" in packages[0]["versions"]
    assert packages[1]["versions"] == {}


def test_sync(run, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sprat._database, "cache_root", tmp_path)
    _strip_size = lambda x: re.sub(r"\([\d.]+ kB\)", "(xx.x kB)", x)
    with fake_upstream(packed()[0]):
        snapshot_test(_strip_size(run("sync")), "sync-initial")
        assert "Already in sync" in run("sync")
    with fake_upstream(packed()[2]):
        snapshot_test(_strip_size(run("sync")), "sync-update")

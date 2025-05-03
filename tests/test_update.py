import contextlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path
import re
import os
import tempfile
from functools import lru_cache
import time

import pytest

sys.path.insert(0, str(Path(__file__, "../..").resolve()))
import sprat
import pack


@contextlib.contextmanager
def fake_upstream(content):
    settings = {}

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if "Range" in self.headers:
                match = re.match(r"bytes=(\d*)-(\d*)", self.headers["Range"])
                range = (int(match[1] or 0), int(match[2] or len(content)))
                self.send_response(206)
                if not settings.get("disable_content_length"):
                    self.send_header("Content-Length", range[1] - range[0])
                self.end_headers()
                self.wfile.write(content[range[0]: range[1]])
            else:
                self.send_response(200)
                if not settings.get("disable_content_length"):
                    self.send_header("Content-Length", len(content))
                self.end_headers()
                while settings.get("wait"):
                    time.sleep(0.5)
                self.wfile.write(content)

        def log_message(self, format, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler) as httpd:
        try:
            thread = threading.Thread(target=httpd.serve_forever)
            thread.start()
            os.environ["SPRAT_INDEX_URL"] = "http://{}:{}".format(*httpd.server_address)
            yield settings
        finally:
            httpd.shutdown()
            del os.environ["SPRAT_INDEX_URL"]


@lru_cache()
def packed():
    here = Path(__file__).parent
    files = [list((here / i).glob("*.json")) for i in ("before", "after")]
    with tempfile.TemporaryDirectory() as temp:
        index = Path(temp) / "index.gz"
        pack.cli(["-o", str(index), *map(str, files[0])])
        before = index.read_bytes()
        pack.cli(["--update", str(index), "-o", str(index), *map(str, files[1])])
        after = index.read_bytes()
    return before, after


def test_uninitialised(tmp_path, monkeypatch):
    monkeypatch.setattr(sprat._database, "cache_root", tmp_path)
    with pytest.raises(sprat.DatabaseUninitializedError, match="sprat.update"):
        next(sprat.raw_iter())


def test_update(tmp_path, monkeypatch):
    monkeypatch.setattr(sprat._database, "cache_root", tmp_path)
    before, after = packed()

    with fake_upstream(before):
        sprat.update()
        mtimes = ((tmp_path / "database.gz").stat().st_mtime,
                  (tmp_path / "unpacked" / "12").stat().st_mtime)
        assert "1.1.0" not in sprat.lookup("r2x").versions
        assert sprat.lookup("jk-flexdata").name == "jk-flexdata"
        assert sprat.lookup("SM16inpind").name == "SM16inpind"
        sprat.lookup("awscli-plugin-proxy")
        with pytest.raises(sprat.NoSuchPackageError):
            sprat.lookup("corex")
        with pytest.raises(sprat.NoSuchPackageError):
            sprat.lookup("nexus-cat")
        assert "0.18" in sprat.lookup("x2polygons").versions
        assert "yanked" in sprat.lookup("StreamingCommunity").versions["2.5.0"]
        assert sprat.lookup("pylywsdxx").license_expression == ""
        assert sprat.lookup("node-hermes-core").summary == ""
        assert "Programming Language :: Python :: 3" \
            in sprat.lookup("qt-interface-utils").classifiers
        assert len(sprat.lookup("h3pandas").keywords) == 7
        with pytest.raises(sprat.NoSuchPackageError):
            sprat.lookup("simple-conf-manager")
        old_shipyard_trello = sprat.lookup("shipyard-trello")
        old_zombie_adventure = sprat.lookup("ZombieAdventure")
        assert "Homepage" in old_zombie_adventure.urls
        assert "Download" not in old_zombie_adventure.urls

    with fake_upstream(before):
        sprat.update()
        assert ((tmp_path / "database.gz").stat().st_mtime,
                (tmp_path / "unpacked" / "12").stat().st_mtime) == mtimes

    with fake_upstream(after):
        sprat.update()
        assert "1.1.0" in sprat.lookup("r2x").versions
        assert sprat.lookup("jk-flexdata").name == "jk_flexdata"
        assert sprat.lookup("SM16inpind").name == "sm16inpind"
        with pytest.raises(sprat.NoSuchPackageError):
            sprat.lookup("awscli-plugin-proxy")
        with pytest.raises(sprat.NoSuchPackageError):
            sprat.lookup("corex")
        sprat.lookup("nexus-cat")
        assert "0.18" not in sprat.lookup("x2polygons").versions
        assert "yanked" not in sprat.lookup("StreamingCommunity").versions["2.5.0"]
        assert sprat.lookup("pylywsdxx").license_expression == "MIT"
        assert "Node Hermes" in sprat.lookup("node-hermes-core").summary
        assert "Programming Language :: Python :: 3" \
            not in sprat.lookup("qt-interface-utils").classifiers
        assert len(sprat.lookup("h3pandas").keywords) == 0
        assert len(sprat.lookup("simple-conf-manager").versions) == 0
        assert sprat.lookup("shipyard-trello") == old_shipyard_trello
        assert sprat.lookup("ZombieAdventure") == old_zombie_adventure


def test_error_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(sprat._database, "cache_root", tmp_path)
    before, after = packed()
    original_repack_database = sprat._database.repack_database

    def bad_repack_database(path, dest):
        if "3" in path.name:
            raise RuntimeError
        original_repack_database(path, dest)

    with fake_upstream(before):
        monkeypatch.setattr(sprat._database, "repack_database", bad_repack_database)
        with pytest.raises(RuntimeError):
            sprat.update()
        assert (tmp_path / "work" / "02").exists()
        assert not (tmp_path / "work" / "03").exists()
        assert (tmp_path / "work" / "_03").exists()
        with pytest.raises(sprat.DatabaseUninitializedError):
            sprat.lookup("aa-metenox")

    with fake_upstream(before):
        sprat._database.repack_database = original_repack_database
        sprat.update()
        assert not (tmp_path / "work").exists()
        sprat.lookup("aa-metenox")
        sprat.lookup("xss-utils")

    with fake_upstream(after):
        monkeypatch.setattr(sprat._database, "repack_database", bad_repack_database)
        with pytest.raises(RuntimeError):
            sprat.update()
        assert "1.2.0" not in sprat.lookup("aa-metenox").versions
        with pytest.raises(RuntimeError):
            sprat.update()
        assert "0.7.1" not in sprat.lookup("xss-utils").versions

    with fake_upstream(after):
        sprat._database.repack_database = original_repack_database
        (tmp_path / "graveyard").mkdir()
        (tmp_path / "graveyard" / "1").touch()
        sprat.update()
        assert not (tmp_path / "work").exists()
        assert not (tmp_path / "graveyard").exists()
        assert "1.2.0" in sprat.lookup("aa-metenox").versions
        assert "0.7.1" in sprat.lookup("xss-utils").versions


def test_concurrent_update(tmp_path, monkeypatch):
    monkeypatch.setattr(sprat._database, "cache_root", tmp_path)

    with fake_upstream(packed()[0]) as server_settings:
        try:
            server_settings["wait"] = True
            thread = threading.Thread(target=sprat.update)
            thread.start()
            for _ in range(10):
                if (tmp_path / "database.gz").exists():
                    break
                time.sleep(0.5)
            else:
                raise

            with pytest.raises(sprat.UpdateAlreadyInProgressError):
                sprat.update()
        finally:
            server_settings["wait"] = False
            thread.join()

    assert any(sprat.raw_with_prefix("pytest-"))

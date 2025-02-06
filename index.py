import json
import sys
import re
from pathlib import Path
from functools import lru_cache
import gzip
import argparse
import shutil
import io
import string

from packaging.version import Version, InvalidVersion
from packaging.specifiers import SpecifierSet, InvalidSpecifier

import sprat
from sprat._index import _read_index

Version = lru_cache()(Version)
SpecifierSet = lru_cache()(SpecifierSet)


class UpstreamPackage(sprat.Package):
    def __init__(self, name, classifiers, keywords, license_expression, summary, urls, versions):
        super().__init__(name, classifiers, keywords, license_expression, summary, urls, versions)

        sanitize(name, "\r\n")
        [sanitize(i, "\r\n") for i in classifiers]
        [sanitize(i, "\r\n,") for i in keywords if i.strip()]
        sanitize(license_expression, "\r\n")
        self.summary = " ".join(summary.split())

        self.urls = {}
        for (key, url) in urls.items():
            key = normalize_url_label(key)
            url = url.strip()
            if not url or url.lower() == "unknown":
                continue
            sanitize(key, "\r\n=")
            sanitize(url, "\r\n")
            if not url:
                raise SanitationError(f"Url {repr(key)} is empty")
            self.urls[key] = url

        sanitized_versions = {}
        for (version, info) in versions.items():
            try:
                Version(version)
            except InvalidVersion:
                continue
            sanitize(version, "\r\n")
            if yanked_reason := info.get("yanked"):
                info["yanked"] = re.sub("[\r\n]+", " ", yanked_reason)
            if requires_python := info.get("requires_python"):
                try:
                    SpecifierSet(requires_python)
                except InvalidSpecifier:
                    continue
            sanitized_versions[version] = info
        self.versions = sanitized_versions

    @classmethod
    def _from_json(cls, name, data):
        if data.get("empty"):
            return cls(name, set(), set(), "", "", {}, {})

        info = data["info"]
        releases = data["releases"]

        versions = []
        for version in releases:
            files = releases[version]
            if not files:
                continue
            release = files[0]
            _info = {}
            if release.get("requires_python"):
                _info["requires_python"] = release["requires_python"]
            if release["yanked"]:
                _info["yanked"] = release["yanked_reason"] or ""
            versions.append((version, _info))
        versions.sort(key=lambda x: min(file["upload_time"] for file in releases[x[0]]))

        return cls(
            info["name"],
            set(info["classifiers"]),
            {i.strip() for i in re.findall("[^,\n]+", info["keywords"] or "")},
            info["license_expression"] or "",
            info["summary"] or "",
            info["project_urls"] or {},
            dict(versions),
        )


def normalize_url_label(label: str) -> str:
    chars_to_remove = string.punctuation + string.whitespace
    removal_map = str.maketrans("", "", chars_to_remove)
    # https://packaging.python.org/en/latest/specifications/well-known-project-urls/#well-known-labels
    return {
        "homepage": "Homepage",
        "source": "Source Code",
        "repository": "Source Code",
        "sourcecode": "Source Code",
        "github": "Source Code",
        "download": "Download",
        "changelog": "Changelog",
        "changes": "Changelog",
        "whatsnew": "Changelog",
        "history": "Changelog",
        "releasenotes": "Release Notes",
        "documentation": "Documentation",
        "docs": "Documentation",
        "issues": "Issue Tracker",
        "bugs": "Issue Tracker",
        "issue": "Issue Tracker",
        "tracker": "Issue Tracker",
        "issuetracker": "Issue Tracker",
        "bugtracker": "Issue Tracker",
        "funding": "Funding",
        "sponsor": "Funding",
        "donate": "Funding",
        "donation": "Funding",
    }.get(label.translate(removal_map).lower(), label)


class SanitationError(Exception):
    pass


def sanitize(string, bad_characters):
    pattern = re.compile("[" + bad_characters + "]+")
    if pattern.search(string):
        raise SanitationError(f"{repr(string)} contains illegal characters {pattern.findall(string)}")


def main(output, files):
    for file in map(Path, files):
        source = json.loads(gzip.decompress(file.read_bytes()))
        try:
            package = UpstreamPackage._from_json(split_path(file)[0], source)
        except SanitationError as ex:
            ex.add_note(str(file))
            sys.excepthook(type(ex), ex, ex.__traceback__)
            print()
            continue
        delta = package.delta(sprat.Package.null)
        if delta:
            output.writelines(map("%s:%s\n".__mod__, delta))
            output.write("\n")
    return int(file.stem.rsplit("-", maxsplit=1)[1])


def update(old_index, new_index, files):
    with open(str(old_index) + ".lastserial") as f:
        last_serial = int(f.read().strip())
    if new_index and new_index != old_index:
        shutil.copy(old_index, new_index)
        shutil.copy(str(old_index) + ".lastserial", str(new_index) + ".lastserial")

    files = [i for i in files if split_path(i)[1] > last_serial]
    ids = {sprat.sluggify(split_path(i)[0]).encode() for i in files}
    packages = {}
    for (id, block) in _read_index(old_index):
        if id in ids:
            id = id.decode()
            try:
                if id in packages:
                    packages[id]._update(block)
                else:
                    packages[id] = sprat.Package.parse(id, block)
            except sprat.PackageDeleted:
                packages.pop(id, None)
    try:
        if new_index:
            f = io.TextIOWrapper(gzip.GzipFile(new_index, "a"))
        else:
            f = sys.stdout
        for file in files:
            name, _ = split_path(file)
            id = sprat.sluggify(name)
            old = packages.get(id, UpstreamPackage.null)
            new_data = json.loads(gzip.decompress(file.read_bytes()))
            if new_data.get("empty"):
                if old is not UpstreamPackage.null:
                    delta = [("i", id), ("I", "")]
                else:
                    delta = []
            else:
                new = UpstreamPackage._from_json(name, new_data)
                delta = new.delta(old)
            if delta:
                f.writelines(map("%s:%s\n".__mod__, delta))
                f.write("\n")
    finally:
        if new_index:
            f.close()
    if new_index:
        with open(new_index + ".lastserial", "w") as f:
            f.write(str(last_serial))


def sort_key(path):
    name, serial = split_path(path)
    return (serial, name)


def split_path(path):
    match = re.fullmatch(r"(.+)-(\d+).jsongz", path.name)
    return match[1], int(match[2])


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--output", "-o")
    parser.add_argument("--update")
    options = parser.parse_args()
    options.files = [Path(i) for i in options.files] or list(Path("pypi").glob("*.jsongz"))
    options.files = sorted(options.files, key=sort_key)
    if options.update:
        update(options.update, options.output, options.files)
    elif options.output:
        with gzip.open(options.output, "wt") as f:
            last_serial = main(f, options.files)
        with open(options.output + ".lastserial", "w") as f:
            f.write(str(last_serial))
    else:
        main(sys.stdout, options.files)


if __name__ == "__main__":
    cli()

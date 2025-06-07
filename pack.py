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
from sprat._database import _read_database

Version = lru_cache()(Version)
SpecifierSet = lru_cache()(SpecifierSet)


class UpstreamPackage(sprat.Package):
    def __init__(self, name, classifiers, keywords, license, summary, urls, versions):
        super().__init__(name, classifiers, keywords, license, summary, urls, versions)

        sanitize(name)
        [sanitize(i) for i in classifiers]
        [sanitize(i, ",") for i in keywords]
        sanitize(license)
        self.summary = " ".join(summary.split())
        sanitize(self.summary)

        self.urls = {}
        for (key, url) in urls.items():
            key = normalize_url_label(key)
            url = url.strip()
            if url.lower() == "unknown":
                continue
            sanitize(key, "=")
            sanitize(url)
            if not url:
                continue
            self.urls[key] = url

        sanitized_versions = {}
        for (version, info) in versions.items():
            try:
                Version(version)
            except InvalidVersion:
                continue
            sanitize(version)
            yanked_reason = info.get("yanked")
            if yanked_reason:
                yanked_reason = re.sub("[\r\n]+", " ", yanked_reason)
                sanitize(yanked_reason)
                info["yanked"] = yanked_reason
            requires_python = info.get("requires_python")
            if requires_python is not None:
                requires_python = requires_python.strip()
                if not requires_python:
                    continue
                try:
                    SpecifierSet(requires_python)
                except InvalidSpecifier:
                    continue
            sanitized_versions[version] = info
        self.versions = sanitized_versions

    @classmethod
    def _from_json(cls, name, data):
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

        # There's no standard delimiter for keywords. Assume the package uses
        # either commas or line breaks then fall back to whitespace if no splits
        # are already made.
        keywords = re.findall("[^,\n]+", info["keywords"] or "")
        keywords = set(filter(None, map(str.strip, keywords)))
        if len(keywords) == 1:
            keywords = set(next(iter(keywords)).split())

        return cls(
            info["name"],
            set(info["classifiers"]),
            keywords,
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


def sanitize(string, bad_characters=None):
    bad_characters = "\r\n" + (bad_characters or "")
    pattern = re.compile("[" + bad_characters + "]+")
    bad = pattern.findall(string)
    if bad:
        raise SanitationError(f"{repr(string)} contains characters {bad}")
    try:
        string.encode()
    except UnicodeEncodeError as ex:
        raise SanitationError(repr(ex))
    if [i.encode() for i in string.splitlines()] != string.encode().splitlines():
        raise SanitationError(f"{repr(string)} contains inconsistent line breaks")


def load_json(path):
    path = Path(path)
    if path.name.endswith("gz"):  # pragma: no cover
        return json.loads(gzip.decompress(path.read_bytes()))
    else:
        return json.loads(path.read_bytes())


def main(output, files):
    for file in map(Path, files):
        source = load_json(file)
        if source.get("empty"):
            continue
        try:
            package = UpstreamPackage._from_json(split_path(file)[0], source)
        except SanitationError as ex:  # pragma: no cover
            ex.add_note(str(file))
            sys.excepthook(type(ex), ex, ex.__traceback__)
            print()
            continue
        delta = package.delta(sprat.Package.null)
        if delta:  # pragma: no branch
            output.writelines(map("%s:%s\n".__mod__, delta))
            output.write("\n")
    return int(file.stem.rsplit("-", maxsplit=1)[1])


def update(old_database, new_database, files):
    with open(str(old_database) + ".lastserial") as f:
        last_serial = int(f.read().strip())
    if new_database and new_database != old_database:  # pragma: no cover
        shutil.copy(old_database, new_database)
        shutil.copy(str(old_database) + ".lastserial", str(new_database) + ".lastserial")

    files = [i for i in files if split_path(i)[1] > last_serial]
    ids = {sprat.sluggify(split_path(i)[0]).encode() for i in files}
    packages = {}
    for (name, block) in _read_database(old_database):
        if name not in ids:
            id = sprat.sluggify_b(name)
        else:
            id = name
        if id in ids:
            try:
                if id in packages:
                    packages[id]._update(block)
                else:
                    packages[id] = sprat.Package.parse(name, block)
            except sprat._database.PackageDeleted:
                packages.pop(id, None)
    try:
        if new_database:  # pragma: no branch
            f = io.TextIOWrapper(gzip.GzipFile(new_database, "a"),
                                 newline="\n", encoding="utf-8")
        else:  # pragma: no cover
            f = sys.stdout
        for file in files:
            name, last_serial = split_path(file)
            id = sprat.sluggify(name).encode()
            old = packages.get(id, UpstreamPackage.null)
            new_data = load_json(file)
            if new_data.get("empty"):
                if old is not UpstreamPackage.null:
                    delta = [("n", name), ("N", "")]
                else:
                    delta = []
            else:
                new = UpstreamPackage._from_json(name, new_data)
                delta = new.delta(old)
            if delta:
                f.writelines(map("%s:%s\n".__mod__, delta))
                f.write("\n")
    finally:
        if new_database:  # pragma: no branch
            f.close()
    if new_database:  # pragma: no branch
        with open(new_database + ".lastserial", "w") as f:
            f.write(str(last_serial))


def sort_key(path):
    name, serial = split_path(path)
    return (serial, name)


def split_path(path):
    match = re.fullmatch(r"(.+)-(\d+).json(gz)?", path.name)
    return match[1], int(match[2])


def cli(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--output", "-o")
    parser.add_argument("--update")
    options = parser.parse_args(args)
    options.files = [Path(i) for i in options.files] or list(Path("pypi").glob("*.jsongz"))
    options.files = sorted(options.files, key=sort_key)
    if options.update:
        update(options.update, options.output, options.files)
    elif options.output:  # pragma: no branch
        with gzip.open(options.output, "wt", encoding="utf-8", newline="\n") as f:
            last_serial = main(f, options.files)
        with open(options.output + ".lastserial", "w") as f:
            f.write(str(last_serial))
    else:  # pragma: no cover
        main(sys.stdout, options.files)


if __name__ == "__main__":  # pragma: no cover
    cli()

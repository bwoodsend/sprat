import gzip
import re
from pathlib import Path
from dataclasses import dataclass
import bisect
import collections
import os
import time
import warnings

import platformdirs

cache_root = Path(os.environ.get("SPRAT_CACHE_ROOT") or
                  platformdirs.user_cache_dir("sprat", False, "v1", False))


def sluggify(name):
    return re.sub(r"[-_.]+", "-", name).lower()


_sluggify_b_re = re.compile(rb"[-_.]+")


def sluggify_b(name):
    return _sluggify_b_re.sub(b"-", name).lower()


@dataclass
class Package:
    name: str
    classifiers: set
    keywords: set
    license: str
    summary: str
    urls: dict
    versions: dict

    def __init__(self, name="", classifiers=None, keywords=None, license="",
                 summary="", urls=None, versions=None):
        assert isinstance(name, str)
        self.name = name
        self.classifiers = classifiers or set()
        self.keywords = keywords or set()
        self.license = license
        self.summary = summary
        self.urls = urls or {}
        self.versions = versions or {}

    def delta(self, old):
        out = [("n", self.name)]
        for classifier in sorted(self.classifiers - old.classifiers):
            out.append(("c", classifier))
        for classifier in sorted(old.classifiers - self.classifiers):
            out.append(("C", classifier))
        for keyword in sorted(self.keywords - old.keywords):
            out.append(("k", keyword))
        for keyword in sorted(old.keywords - self.keywords):
            out.append(("K", keyword))
        if self.license != old.license:
            out.append(("l", self.license))
        if self.summary != old.summary:
            out.append(("s", self.summary))
        for (key, url) in sorted(self.urls.items()):
            if old.urls.get(key, "") != url:
                out.append(("u", key + "=" + url))
        for key in sorted(old.urls):
            if key not in self.urls:
                out.append(("U", key))

        requires_python = old._latest_requires_python
        for (version, info) in old.versions.items():
            if version not in self.versions:
                out.append(("V", version))
        for (version, new_info) in self.versions.items():
            old_info = old.versions.get(version)
            if new_info == old_info:
                # Unchanged release
                continue
            out.append(("v", version))
            if old_info is None:
                # New release
                new_requires_python = new_info.get("requires_python", "")
                if new_requires_python != requires_python:
                    requires_python = new_requires_python
                    out.append(("p", requires_python))
                if "yanked" in new_info:
                    out.append(("y", new_info["yanked"]))
            else:
                # Modified release
                if new_info.get("requires_python", "") != old_info.get("requires_python", ""):
                    requires_python = new_info.get("requires_python", "")
                    out.append(("p", requires_python))
                if "yanked" not in new_info:
                    if "yanked" in old_info:
                        out.append(("Y", ""))
                elif new_info["yanked"] != old_info.get("yanked"):
                    out.append(("y", new_info["yanked"]))

        return out if len(out) > 1 else []

    @property
    def _latest_requires_python(self):
        try:
            return self.__latest_requires_python
        except AttributeError:
            if not self.versions:
                return ""
            for version_info in self.versions.values():
                pass
            return version_info.get("requires_python", "")

    @_latest_requires_python.setter
    def _latest_requires_python(self, value):
        self.__latest_requires_python = value

    _last_modified_version = None

    @classmethod
    def parse(cls, name, source, ignore_versions=False):
        self = cls(name.decode())
        self._update(source, ignore_versions=ignore_versions)
        return self

    def _update(self, source, ignore_versions=False):
        for line in source.decode().splitlines():
            key = line[0]
            if ignore_versions and key in "vVyYp":
                continue
            value = line[2:]
            if key == "v":
                if value in self.versions:
                    self._last_modified_version = self.versions[value]
                else:
                    self._last_modified_version = self.versions[value] = {}
                    if self._latest_requires_python:
                        self._last_modified_version["requires_python"] = self._latest_requires_python
            elif key == "n":
                self.name = value
            elif key == "c":
                self.classifiers.add(value)
            elif key == "u":
                _key, _value = value.split("=", maxsplit=1)
                self.urls[_key] = _value
            elif key == "p":
                if value:
                    self._last_modified_version["requires_python"] = value
                else:
                    del self._last_modified_version["requires_python"]
                self._latest_requires_python = value
            elif key == "k":
                self.keywords.add(value)
            elif key == "s":
                self.summary = value
            elif key == "V":
                del self.versions[value]
            elif key == "C":
                self.classifiers.remove(value)
            elif key == "U":
                del self.urls[value]
            elif key == "y":
                self._last_modified_version["yanked"] = value
            elif key == "K":
                self.keywords.remove(value)
            elif key == "l":
                self.license = value
            elif key == "Y":
                del self._last_modified_version["yanked"]
            elif key == "N":  # pragma: no branch
                raise PackageDeleted
            else:  # pragma: no cover
                assert 0, (key, value)


Package.null = Package("", set(), set(), "", "", {}, {})

anchors = [
    b'aiohttp-csrf2', b'animalai-train', b'aspose-barcode-for-python-via-java',
    b'azfuncfastapi', b'billocosmos', b'browserjquery',
    b'cdk8s-argoworkflow-resources', b'claude-api-temp', b'colrev-scidb',
    b'crispy-forms-propeller', b'data-ecosystem-flask', b'deps-rocker',
    b'django-blob-storage', b'django-redisearch', b'dominus-python-sdk',
    b'eazy-percent-finder', b'esbanner', b'fast-io', b'flashrag-dev',
    b'fsspec-dnanexus', b'getallcolumnname', b'grandiorite', b'hello-geo',
    b'hypertunity', b'interstate-love-song-simplewebservicemapper', b'jobject',
    b'kiauhoku', b'ldap-attributes-selector', b'lm-eval', b'maoc-rep-17168545',
    b'metaseg', b'model-explanation', b'mvvmqt', b'nester-astutulus',
    b'notebin', b'odoo-addon-stock-picking-back2draft',
    b'odoo14-addon-base-name-search-multi-lang', b'ooi', b'package110-5585580',
    b'persai', b'plyvel-wheels', b'progresspanel', b'pyaez', b'pyfisher',
    b'pynurex', b'pystubs', b'pytorch-text-utils', b'radix', b'requests-guard',
    b'rts2', b'scrapy-jsonrpc', b'shipyard-trello', b'smartanthill',
    b'splitfvm', b'streamlit-flexselect', b'tap-geekbot', b'tf-lambda',
    b'topsis-kartik-101803702', b'tutor-cairn', b'useis', b'vspacker',
    b'wix-protos-answers-streams-prod-repartition-csat-repart-csat',
    b'yacern-tokenmanager'
]


def hash_id(id):
    return bisect.bisect(anchors, id)


def _read_database(path):
    path = Path(path)
    with (gzip.open if path.suffix == ".gz" else open)(path, "rb") as f:
        yield from _read_database_raw(f, 500_000)


def _read_database_raw(f, chunk_size):
    buffer = f.read(chunk_size)
    while True:
        chunks = buffer.split(b"\n\n")
        for chunk in chunks[:-1]:
            idx = chunk.find(b"\n")
            yield chunk[2: idx], chunk[idx + 1:] + b"\n"
        remainder = chunks[-1]
        buffer = remainder + f.read(chunk_size)
        if len(buffer) == len(remainder):
            break
    assert not remainder, remainder


def disassemble(source, dest_dir, progress):
    try:
        dest_files = [open(dest_dir / f"_{i:02}", "wb") for i in range(len(anchors) + 1)]
        for (name, chunk) in _read_database(source):
            dest_files[hash_id(sluggify_b(name))].write(b"n:%s\n%s\n" % (name, chunk))
    finally:
        [i.close() for i in dest_files]
    total = 0
    progress.start_unpack(total_parts=len(anchors) + 1)
    for i in range(len(anchors) + 1):
        total += repack_database(dest_dir / f"_{i:02}", dest_dir / f"{i:02}")
        windows_proof(Path.unlink, dest_dir / f"_{i:02}")
        progress.update_unpack(part=i + 1)
    progress.finish_unpack()
    return total


def repack_database(path, dest):
    package_blocks = {}
    for (name, source) in _read_database(path):
        id = sluggify_b(name)
        if id in package_blocks:
            if source == b"N:\n":
                del package_blocks[id]
            else:
                package_blocks[id] = (name, package_blocks[id][1] + source)
        else:
            package_blocks[id] = (name, source)
    with open(dest, "wb") as f:
        template = b"n:%s\n%s\n" * len(package_blocks)
        values = []
        for i in sorted(package_blocks.items()):
            values.extend(i[1])
        f.write(template % tuple(values))
    return len(package_blocks)


class PackageDeleted(Exception):
    pass


def database_path(database_id):
    unpacked = cache_root / "unpacked"
    if not unpacked.is_dir():
        raise DatabaseUninitializedError
    return unpacked / format(database_id, "02")


def with_prefix(prefix):
    return (Package.parse(*i) for i in raw_with_prefix(prefix))


def raw_with_prefix(prefix):
    if not prefix:
        yield from raw_iter()
        return
    prefix = sluggify(prefix).encode()
    start = prefix
    end = prefix[:-1] + bytes([prefix[-1] + 1])
    for database_id in range(hash_id(start), hash_id(end) + 1):
        _iter = _read_database(database_path(database_id))
        for (name, block) in _iter:
            if sluggify_b(name).startswith(prefix):
                yield name, block
                break
        for (name, block) in _iter:
            if not sluggify_b(name).startswith(prefix):
                break
            yield name, block


def iter(ignore_versions=False):
    return (Package.parse(*i, ignore_versions) for i in raw_iter())


def raw_iter():
    for database_id in range(len(anchors) + 1):
        yield from _read_database(database_path(database_id))


def crude_search(pattern, case_sensitive=True):
    return (Package.parse(*i) for i in raw_crude_search(pattern, case_sensitive))


def raw_crude_search(pattern, case_sensitive=True):
    if not case_sensitive:
        pattern = re.sub(r"(\\\\)|(\\.)|(.)", lambda m: m[1] or m[2] or m[3].lower(), pattern)
    pattern = re.compile(pattern.encode().lstrip(b"^").rstrip(b"$"))
    name = None
    for database_id in range(len(anchors) + 1):
        source = database_path(database_id).read_bytes()
        end = -1
        for match in pattern.finditer(source if case_sensitive else source.lower()):
            if match.start() < end:
                continue
            if not match[0]:
                continue
            if b"\n" in match[0]:
                yield from _slow_raw_crude_search(pattern, name)
                return
            start = source.rfind(b"\n\n", 0, match.start())
            start = 0 if start == -1 else start + 2
            end = source.find(b"\n\n", match.end())
            _source = source[start:end]
            name, block = _source.split(b"\n", maxsplit=1)
            name = name[2:]
            yield name, block


def _slow_raw_crude_search(pattern, initial):
    """A variant of raw_crude_search() which won't allow multiline matches to
    span across multiple package blocks"""
    _iter = raw_iter()
    if initial is not None:
        next(name for (name, _) in _iter if name == initial)  # pragma: no branch
    for (name, block) in _iter:
        if pattern.search(name) or pattern.search(block):
            yield name, block


def bulk_lookup(names):
    ids = [(sluggify(i).encode(), i) for i in names]
    grouped = collections.defaultdict(list)
    [grouped[hash_id(i[0])].append(i) for i in ids]
    [i.sort() for i in grouped.values()]
    packages = {}
    _id_i = 0
    last_id = None
    for (database_id, targets) in grouped.items():
        database_iter = _read_database(database_path(database_id))
        for (target_id, target_name) in targets:
            if target_id == last_id:
                continue
            last_id = target_id
            for (name, block) in database_iter:
                id = sluggify_b(name)
                if id == target_id:
                    packages[id] = Package.parse(name, block)
                    break
            else:
                raise NoSuchPackageError(target_name)
        while _id_i < len(ids):
            id = ids[_id_i][0]
            if id in packages:
                yield packages[id]
                _id_i += 1
            else:
                break


def lookup(name):
    id = sluggify(name).encode()
    for (_name, block) in _read_database(database_path(hash_id(id))):
        if sluggify_b(_name) == id:
            return Package.parse(_name, block)
    raise NoSuchPackageError(name)


class NoSuchPackageError(Exception):
    pass


class DatabaseUninitializedError(Exception):
    def __str__(self):
        return "Packages database has not been downloaded. Please call: sprat.sync()"


class UpdateAlreadyInProgressError(Exception):
    pass


def classifier_sort_key(classifier):
    start, numbers, end = re.fullmatch(r"(\D*)(.*?)(\D*)", classifier).groups()
    return (start, [int(i) for i in re.findall(r"\d+", numbers)], end)


def windows_proof(function, file, *args, **kwargs):
    """Add retries to a function which modifies or deletes an existing file"""
    for i in range(1000):  # pragma: no branch
        try:
            return function(file, *args, **kwargs)
        except OSError as ex:
            if not _retryable_exception(ex):
                raise
            if i == 7:  # pragma: no cover
                raise
            warnings.warn(
                f'Another process is blocking access to "{file}". '
                "This is most likely to be an antivirus. "
                f"Retrying in {i / 2:.1f} seconds"
            )
            time.sleep(i / 2)


def _retryable_exception(ex):
    """Test if ``ex`` is an error that can be raised by antivirus interference"""
    if isinstance(ex, PermissionError):  # pragma: no cover
        return True

    # Windows-specific errno and winerror codes.
    # https://learn.microsoft.com/en-us/cpp/c-runtime-library/errno-constants
    ERRNOs = {
        13,  # EACCES (would typically be a PermissionError instead)
        22,  # EINVAL (reported to be caused by Crowdstrike; see pyinstaller/pyinstaller#7840)
    }
    # https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-
    WINERRORs = {
        5,  # ERROR_ACCESS_DENIED (reported in pyinstaller/pyinstaller#7825)
        32,  # ERROR_SHARING_VIOLATION (exclusive lock via `CreateFileW` flags, or via `_locked`).
        110,  # ERROR_OPEN_FAILED (reported in pyinstaller/pyinstaller#8138)
    }
    if ex.errno in ERRNOs or getattr(ex, "winerror", -1) in WINERRORs:
        return True

    return False



def sync(progress=None, database_file=None):
    import shutil, filelock

    progress = progress or SyncProgress()
    cache_root.mkdir(parents=True, exist_ok=True)
    lock = None
    try:
        lock = filelock.FileLock(cache_root / "lock", timeout=0)
        lock.acquire()
    except (filelock.Timeout, OSError):
        raise UpdateAlreadyInProgressError from None
    else:
        work_dir = cache_root / "work"
        work_dir.mkdir(exist_ok=True)

        download_no_op = False
        if database_file is None:  # pragma: no branch
            from urllib.request import urlopen, Request
            from urllib.error import HTTPError
            database_file = cache_root / "database.gz"
            headers = {}
            try:
                current_size = database_file.stat().st_size
                headers["Range"] = f"bytes={current_size}-"
            except FileNotFoundError:
                current_size = 0
            url = os.environ.get("SPRAT_INDEX_URL") \
                or "https://github.com/bwoodsend/sprat/releases/download/database-v1/database.gz"
            try:
                with urlopen(Request(url, headers=headers)) as response:
                    expected_length = int(response.headers["Content-Length"])
                    if expected_length != 0:
                        progress.start_download(total_size=expected_length)
                        with windows_proof(open, database_file, "ab") as f:
                            total_read = 0
                            while True:
                                read = f.write(response.read1())
                                if read == 0:
                                    break
                                total_read += read
                                progress.update_download(size=total_read)
                        progress.finish_download()
                    else:
                        download_no_op = True
            except HTTPError as response:
                with response:
                    if response.code == 416:  # pragma: no branch
                        assert response.headers["Content-Range"].endswith(str(current_size)), \
                            (dict(response.headers), current_size)
                        download_no_op = True
                    else:  # pragma: no cover
                        raise

        dest_dir = cache_root / "unpacked"
        graveyard_dir = cache_root / "graveyard"
        if download_no_op and dest_dir.exists():
            if dest_dir.stat().st_mtime > database_file.stat().st_mtime:
                progress.announce_no_op()
                return
        total = disassemble(database_file, work_dir, progress)
        try:
            windows_proof(shutil.rmtree, graveyard_dir)
        except FileNotFoundError:
            pass
        try:
            windows_proof(dest_dir.rename, graveyard_dir)
        except FileNotFoundError:
            windows_proof(work_dir.rename, dest_dir)
        else:
            windows_proof(work_dir.rename, dest_dir)
            windows_proof(shutil.rmtree, graveyard_dir)
        progress.announce_done(total_packages=total)
    finally:
        if lock is not None:  # pragma: no branch
            lock.release()


class SyncProgress:
    """A base class for progress-indicating sprat.sync()

    sprat.sync() will call this class's methods sketched out below::

        if not_up_to_date:
            start_download(total_size=number_of_bytes_to_download)
            while still_downloading:
                 update_download(size=number_of_bytes_downloaded_so_far)
            finish_download()

            start_unpack(total_parts=number_of_database_parts_to_unpack)
            for each database part:
                update_unpack(part=number_of_database_parts_unpacked_so_far)
            finish_unpack()

            announce_done(total_packages=number_of_packages_now_in_database)
        else:
            announce_no_op()

    Overrides of methods should add a ``**ignored`` parameter so that new
    keyword parameters can be passed in without breaking the override.

    """
    def start_download(self, *, total_size):
        pass

    def update_download(self, *, size):
        pass

    def finish_download(self):
        pass

    def start_unpack(self, *, total_parts):
        pass

    def update_unpack(self, *, part):
        pass

    def finish_unpack(self):
        pass

    def announce_done(self, *, total_packages):
        pass

    def announce_no_op(self):
        pass

import gzip
import re
from pathlib import Path
from dataclasses import dataclass
import bisect
import collections

import appdirs

cache_root = Path(appdirs.user_cache_dir("sprat"), "v1")


def sluggify(name):
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class BasePackage:
    id: str
    name: str
    classifiers: set
    keywords: set
    license_expression: str
    summary: str
    urls: dict
    versions: dict

    @classmethod
    def _new(cls, id="", name="", classifiers=None, keywords=None, license_expression="", summary="", urls=None, versions=None):
        return cls(id, name or id, classifiers or set(), keywords or set(), license_expression, summary, urls or {}, versions or {})

    def delta(self, old):
        out = [("i", self.id)]
        if self.name != old.name:
            if not (old is self.null and self.name == self.id):
                out.append(("n", self.name))
        for classifier in sorted(self.classifiers - old.classifiers):
            out.append(("c", classifier))
        for classifier in sorted(old.classifiers - self.classifiers):
            out.append(("C", classifier))
        for keyword in sorted(self.keywords - old.keywords):
            out.append(("k", keyword))
        for keyword in sorted(old.keywords - self.keywords):
            out.append(("K", keyword))
        if self.license_expression != old.license_expression:
            out.append(("l", self.license_expression))
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


BasePackage.null = BasePackage("", "", set(), set(), "", "", {}, {})

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


def _read_index(path):
    path = Path(path)
    with (gzip.open if path.suffix == ".gz" else open)(path, "rb") as f:
        buffer = f.read(500_000)
        while True:
            chunks = buffer.split(b"\n\n")
            for chunk in chunks[:-1]:
                id, payload = chunk.split(b"\n", maxsplit=1)
                yield (id[2:], payload + b"\n")
            remainder = chunks[-1]
            buffer = remainder + f.read(500_000)
            if len(buffer) == len(remainder):
                break
        assert not remainder, remainder


def disassemble(source, dest_dir):
    try:
        dest_files = [open(dest_dir / f"_{i:02}", "wb") for i in range(len(anchors) + 1)]
        for (id, chunk) in _read_index(source):
            dest_files[hash_id(id)].write(b"i:%s\n%s\n" % (id, chunk))
    finally:
        [i.close() for i in dest_files]
    [repack_index(dest_dir / f"_{i:02}", dest_dir / f"{i:02}") for i in range(len(anchors) + 1)]
    [(dest_dir / f"_{i:02}").unlink() for i in range(len(anchors) + 1)]


def repack_index(path, dest):
    package_blocks = {}
    for (id, source) in _read_index(path):
        if id in package_blocks:
            if source == b"I:\n":
                del package_blocks[id]
            else:
                package_blocks[id] += source
        else:
            package_blocks[id] = source
    with open(dest, "wb") as f:
        f.writelines(map(b"i:%s\n%s\n".__mod__, sorted(package_blocks.items())))




class Package(BasePackage):
    _last_modified_version = None

    @classmethod
    def _parse(cls, id, source, ignore_versions=False):
        self = cls._new(id, id)
        self._update(source, ignore_versions=ignore_versions)
        return self

    def _update(self, source, ignore_versions=False):
        for line in bytes(source).decode().splitlines():
            key = line[0]
            value = line[2:]
            if ignore_versions and key in "vVyYp":
                continue
            if key == "v":
                if value in self.versions:
                    self._last_modified_version = self.versions[value]
                else:
                    self._last_modified_version = self.versions[value] = {}
                    if self._latest_requires_python:
                        self._last_modified_version["requires_python"] = self._latest_requires_python
            elif key == "i":
                continue
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
            elif key == "n":
                self.name = value
            elif key == "y":
                self._last_modified_version["yanked"] = value
            elif key == "K":
                self.keywords.remove(value)
            elif key == "l":
                self.license_expression = value
            elif key == "Y":
                del self._last_modified_version["yanked"]
            elif key == "I":
                raise PackageDeleted
            else:
                assert 0, (key, value)


class PackageDeleted(Exception):
    pass


def filter_by_name(index, names):
    ids = {"i:" + sluggify(i) + "\n" for i in names}
    with gzip.open(index, "rt") as f:
        grouped = {}
        id = False
        for line in f:
            if line[0] == "i":
                if line in ids:
                    id = line[2:-1]
                    grouped.setdefault(id, [])
                else:
                    id = False
            elif id:
                grouped[id].append((line[0], line[2:-1]))
    return grouped


def info(name):
    id = sluggify(name).encode()
    for (_id, source) in _read_index(Path("disassembled") / f"{hash_id(id):02}"):
        if _id == id:
            print(Package._parse(id.decode(), source))
            break


def index_path(index_id):
    return cache_root / "unpacked" / format(index_id, "02")


def with_prefix(prefix):
    prefix = sluggify(prefix).encode()
    start = prefix
    end = prefix[:-1] + bytes([prefix[-1] + 1])
    for index_id in range(hash_id(start), hash_id(end) + 1):
        _iter = _read_index(index_path(index_id))
        for (id, block) in _iter:
            if id.startswith(prefix):
                yield id, block
                break
        for (id, block) in _iter:
            if not id.startswith(prefix):
                break
            yield id, block


def iter():
    for index_id in range(len(anchors) + 1):
        yield from _read_index(index_path(index_id))


def name(id, block):
    start = block.rfind(b"\nn:")
    if start == -1:
        if block[0] == b"n"[0]:
           return block[:block.find(b"\n")]
        else:
            return id
    else:
        return block[start + 3 :block.find(b"\n", start + 3)]


def iter_names():
    for (id, block) in iter():
        start = block.rfind(b"\nn:")
        if start == -1:
            if block[0] == b"n"[0]:
                yield block[:block.find(b"\n")], block
            else:
                yield id, block
        else:
            yield block[start + 3 :block.find(b"\n", start + 3)], block


def crude_search(pattern, case_sensitive=True):
    if not case_sensitive:
        pattern = re.sub(r"(\\\\)|(\\.)|(.)", lambda m: m[1] or m[2] or m[3].lower(), pattern)
    pattern = re.compile(pattern.encode().lstrip(b"^").rstrip(b"$"))
    for index_id in range(len(anchors) + 1):
        source = index_path(index_id).read_bytes()
        end = -1
        for match in pattern.finditer(source if case_sensitive else source.lower()):
            if match.start() < end:
                continue
            start = source.rfind(b"\n\n", 0, match.start())
            start = 0 if start == -1 else start + 2
            end = source.find(b"\n\n", match.end())
            _source = source[start:end]
            id, block = _source.split(b"\n", maxsplit=1)
            yield id[2:], block


def bulk_lookup(names):
    ids = [(sluggify(i).encode(), i) for i in names]
    grouped = collections.defaultdict(list)
    [grouped[hash_id(i[0])].append(i) for i in ids]
    [i.sort() for i in grouped.values()]
    packages = {}
    for (index_id, targets) in grouped.items():
        index_iter = _read_index(index_path(index_id))
        for (target_id, target_name) in targets:
            for (id, block) in index_iter:
                if id == target_id:
                    packages[id] = Package._parse(id.decode(), block)
                    break
            else:
                raise NoSuchPackageError(target_name)
    return [packages[id] for (id, _) in ids]


class NoSuchPackageError(Exception):
    pass


def classifier_sort_key(classifier):
    start, numbers, end = re.fullmatch(r"(\D*)(.*?)(\D*)", classifier).groups()
    return (start, [int(i) for i in re.findall(r"\d+", numbers)], end)


def update(index_file=None):
    dest_dir = cache_root / "unpacked"
    dest_dir.mkdir(parents=True, exist_ok=True)
    disassemble(index_file, dest_dir)

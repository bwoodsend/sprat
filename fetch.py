import asyncio
from xml.etree import ElementTree
import json
import gzip
import collections
from pathlib import Path
import argparse
import re

import aiohttp

import sprat


async def fetch(session, name, serial):
    print(name, serial)
    if Path(f"pypi/{name}-{serial}.jsongz").exists():
        return
    async with session.get(f"/pypi/{name}/json") as response:
        content = await response.read()
        if response.status == 404:
            content = ('{"empty": true, "last_serial": %s}' % serial).encode()
        else:
            assert response.status == 200, name + "\n" + content.decode()
            data = json.loads(content)
            for key in ["vulnerabilities", "urls"]:
                data.pop(key, None)
            for key in ["downloads", "license", "description", "description_content_type"]:
                data["info"].pop(key, None)
            for release in data["releases"].values():
                for artifact in release:
                    for key in ["digests", "downloads", "md5_digest", "url", "comment_text"]:
                        artifact.pop(key, None)
            content = json.dumps(data, separators=(",", ":")).encode()
        with open(f"pypi/{name}-{serial}.jsongz", "wb") as f:
            f.write(gzip.compress(content))


def parse_delta(tree, project_serials, true_names):
    for entry in tree.findall("params/param/value/array/data/value/array/data"):
        name = entry[0][0].text
        id = sprat.sluggify(name)
        project_serials[id] = int(entry[4][0].text)
        true_names[id] = name


async def main(packages_xml=None, delta_xml=None, since_serial=None):
    user_agent = "sprat/v0.1.0 (PyPI search and indexing tool)"
    async with aiohttp.ClientSession(
            "https://pypi.org/", headers={"User-Agent": user_agent}) as session:
        if packages_xml:
            with open(packages_xml) as f:
                tree = ElementTree.fromstring(f.read())
            project_serials = []
            for item in tree.find("params/param/value/struct"):
                project_serials.append((item.find("name").text,
                                        int(item.find("value/int").text)))
            project_serials.sort(key=lambda x: x[1])
        else:
            project_serials = {}
            true_names = {}
            if since_serial is not None:
                _since_serial = since_serial
                while True:
                    print("Fetch delta since_serial", _since_serial)
                    async with session.post(data=b"<?xml version='1.0' encoding='ASCII'?><methodCall><methodName>changelog_since_serial</methodName><params><param><int>%i</int></param></params></methodCall>" % _since_serial, url="/pypi", headers={"Content-Type": "text/xml"}) as response:
                        content = await response.text()
                    assert response.status == 200, content
                    parse_delta(ElementTree.fromstring(content), project_serials, true_names)
                    __since_serial = max(project_serials.values())
                    print("Fetched up to serial", __since_serial)
                    if _since_serial == __since_serial:
                        break
                    _since_serial = __since_serial
            else:
                with open(delta_xml) as f:
                    content = f.read()
                parse_delta(ElementTree.fromstring(content), project_serials, true_names)
            project_serials = sorted(((true_names[i], j) for (i, j) in project_serials.items()), key=lambda x: x[1])

        existing = {}
        for path in Path("pypi").glob("*.jsongz"):
            name, serial = split_path(path)
            id = sprat.sluggify(name)
            if id in existing:
                if split_path(existing[id])[1] > serial:
                    print("Delete", path)
                    path.unlink()
                    continue
                else:
                    existing[id].unlink()
            existing[id] = path

        tasks = collections.deque(maxlen=5)
        for (name, serial) in project_serials:
            if _path := existing.get(sprat.sluggify(name)):
                if split_path(_path)[1] != serial:
                    assert serial > split_path(_path)[1]
                    _path.unlink()
            if len(tasks) == tasks.maxlen:
                await tasks[0]
            tasks.append(asyncio.create_task(fetch(session, name, serial)))
        for task in tasks:
            await task


def split_path(path):
    match = re.fullmatch(r"(.+)-(\d+).jsongz", path.name)
    return match[1], int(match[2])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-xml")
    parser.add_argument("--delta-xml")
    parser.add_argument("--since-serial", type=int)
    options = parser.parse_args()
    assert options.packages_xml or options.delta_xml or options.since_serial

    asyncio.run(main(options.packages_xml, options.delta_xml, options.since_serial))

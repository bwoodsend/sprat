import re
import sys
import textwrap

import sprat


def red(string):
    return RED + string + RESET


def info(options):
    try:
        packages = sprat.bulk_lookup(options.packages)
    except sprat.NoSuchPackageError as ex:
        raise SystemExit(f"No such package '{ex.args[0]}'")
    lines = []
    if options.json:
        import json
        for package in packages:
            print(json.dumps({
                "name": package.name,
                "summary": package.summary,
                "keywords": sorted(package.keywords),
                "urls": package.urls,
                "classifiers": sorted(package.classifiers, key=sprat.classifier_sort_key),
                "license": package.license_expression,
                "versions": package.versions,
            }, separators=(",", ":")))
        return

    for package in packages:
        try:
            latest = [i for i in package.versions if "yanked" not in package.versions[i]][-1]
        except IndexError:
            latest = ""
        if options.urls or options.all:
            urls = sorted(package.urls.items())
        else:
            urls = [(i, j) for (i, j) in package.urls.items() if i == "Homepage"]
        if options.classifiers or options.all:
            _classifiers = sorted(package.classifiers, key=sprat.classifier_sort_key)
            classifiers = [("Classifiers", i) for i in _classifiers[:1]]
            classifiers += [("", i) for i in _classifiers[1:]]
        else:
            classifiers = []
        if (options.versions or options.all) and package.versions:
            version_width = 0
            for (version, info) in package.versions.items():
                version_width = max(version_width, len(version) + 8 * ("yanked" in info))
            versions = []
            last_requires_python = ""
            for (version, info) in package.versions.items():
                entry = version
                if "yanked" in info:
                    entry += " (yanked)"
                entry = entry.ljust(version_width + 2) + ":"
                if info.get("requires_python", "") != last_requires_python:
                    last_requires_python = info.get("requires_python", "")
                    entry += " Python" + info.get("requires_python", "=any")
                if "yanked" in info:
                    entry = red(entry)
                versions.append(("", entry))
                if "yanked" in info:
                    if info["yanked"]:
                        reason = textwrap.wrap(info["yanked"])
                        versions.append(("", red(reason[0])))
                        versions += (("", red(i)) for i in reason[1:])
            versions[0] = ("Versions", versions[0][1])
        else:
            versions = []
        lines += [
            ("Name", package.name),
            ("Version", latest),
            ("Summary", package.summary),
            ("Keywords", ", ".join(sorted(package.keywords))),
            *urls,
            *classifiers,
            ("License", package.license_expression),
            *versions,
            ("", ""),
        ]
    print_table(lines)


def print_table(lines):
    width = max(len(i[0]) for i in lines) + 2
    [print(i.ljust(width), ": ", j, sep="") if i or j else print() for (i, j) in lines[:-1]]


def _literal_length(regex):
    length = next((i for (i, c) in enumerate(regex) if c != "-" and re.escape(c) != c), len(regex))
    if 1 <= length < len(regex) and regex[length] in "*?{":
        length -= 1
    return length


def search(options):
    all_terms = []
    for _terms in (options.terms, options.name, options.summary, options.keyword, options.classifier):
        if _terms:
            all_terms += _terms
    if len(all_terms) == 0:
        if options.quiet:
            for (id, block) in sprat.iter():
                print(id.decode())
            return True
    try:
        prefix = max((pattern[1:] for pattern in options.name or () if pattern.startswith("^")), key=_literal_length)
    except ValueError:
        prefix = ""
    if prefix:
        filtered = sprat.with_prefix(prefix[:_literal_length(prefix)])
    else:
        if all_terms:
            term = max(all_terms, key=lambda t: 2 * len(t) - len(re.escape(t)))
            filtered = sprat.crude_search(term, case_sensitive=False)
        else:
            filtered = sprat.iter()
    filter = Filter(options.terms, options.name, options.summary, options.keyword, options.classifier)

    if filter.name and not (prefix and len(filter.name) == 1 == len(filter.all)):
        filtered = (i for i in filtered if filter.filter_name(i[0].decode()))

    found = 0
    if options.quiet and len(filter.name) == len(filter.all):
        for (name, _) in filtered:
            print(name.decode())
            found += 1
        return found

    for (name, block) in filtered:
        package = sprat.Package.parse(name.decode(), block, ignore_versions=True)
        if filter.filter(package):
            found += 1
            if options.quiet:
                print(name.decode())
                continue
            print(_highlight(package.name, *filter.name, *filter.any))
            [print("   ", i) for i in textwrap.wrap(_highlight_grey(package.summary, *filter.summary, *filter.any), 120)]
            continue
            if found > 1:
                print()
            lines = [
                ("Name", _highlight(package.name, *filter.name, *filter.any)),
                ("Summary", _highlight(package.summary, *filter.summary, *filter.any)),
            ]
            if package.keywords:
                lines.append(("Keywords", ", ".join(_highlight(word, *filter.keyword, *filter.any) for word in package.keywords)))

            classifier_match = False
            classifier_lines = []
            for classifier in sorted(package.classifiers, key=sprat.classifier_sort_key):
                highlighted, n = _highlight_n(classifier, *filter.classifier, *filter.any)
                classifier_match |= bool(n)
                classifier_lines.append(("Classifiers" if not classifier_lines else "", highlighted))
            if classifier_match:
                lines += classifier_lines
            [print(i.ljust(13), ": ", j, sep="") for (i, j) in lines]
    return found > 0


RESET = "\x1b[0m"
GREY = "\x1b[30m"
RED = "\x1b[31m"


def _highlight_n(word, *patterns):
    n = 0
    for pattern in patterns:
        word, _n = pattern.subn(lambda m: red(m[0]), word)
        n += _n
    return word, n


def _highlight(word, *patterns):
    return _highlight_n(word, *patterns)[0]


def _highlight_grey(word, *patterns):
    for pattern in patterns:
        word = pattern.sub(lambda m: RED + m[0] + GREY, word)
    return GREY + word + RESET


class Filter:
    def __init__(self, any, name, summary, keyword, classifier):
        self.any = self._precompile(any)
        self.name = self._precompile(name)
        self.summary = self._precompile(summary)
        self.keyword = self._precompile(keyword)
        self.classifier = self._precompile(classifier)
        self.all = sum((self.any, self.name, self.summary, self.keyword, self.classifier), [])

    @staticmethod
    def _precompile(terms):
        return [re.compile(i, flags=re.I) for i in terms or []]

    def strongest(self):
        return max(self.all, key=lambda p: 2 * len(p.pattern) - len(re.escape(p.pattern)))

    def filter_name(self, name):
        return all(pattern.search(name) for pattern in self.name)

    def filter(self, package):
        import itertools
        for pattern in self.any:
            if not any(map(pattern.search, itertools.chain((package.summary, package.name), package.keywords, package.classifiers))):
                return False
        if not self.filter_name(package.name):
            return False
        if not all(pattern.search(package.summary) for pattern in self.summary):
            return False
        for pattern in self.keyword:
            if not any(map(pattern.search, package.keywords)):
                return False
        for pattern in self.classifier:
            if not any(map(pattern.search, package.classifiers)):
                return False
        return True


def cli(args=None):
    options = _parse_args(args)
    if options.command == "update":
        sprat.update(options.index_file)
    if options.command == "info":
        info(options)
    if options.command == "search":
        if not search(options):
            sys.exit(2)


def _parse_args(args=None):
    import argparse
    parser = argparse.ArgumentParser("sprat")
    subparsers = parser.add_subparsers(required=True, metavar="COMMAND", dest="command")

    update = subparsers.add_parser("update", help="Download latest index")
    update.add_argument("--index-file", metavar="FILE")

    search = subparsers.add_parser("search", help="List packages matching a pattern or other criteria")
    search.add_argument("terms", nargs="*")
    search.add_argument("--name", nargs="+", dest="name")
    search.add_argument("--summary", nargs="+", dest="summary")
    search.add_argument("--keywords", nargs="+", dest="keyword")
    search.add_argument("--classifiers", nargs="+", dest="classifier")
    search.add_argument("--quiet", "-q", action="store_true")

    info = subparsers.add_parser("info", help="Show details of a given package")
    info.add_argument("packages", nargs="+")
    info.add_argument("--urls", "-u", action="store_true", help="Show all URLs, defaults to just the Homepage")
    info.add_argument("--classifiers", "-c", action="store_true", help="Show classifiers")
    info.add_argument("--versions", "-v", action="store_true", help="List releases")
    info.add_argument("--all", "-a", action="store_true", help='Show everything, equivalent to --urls --classifiers --versions plus any future "show more" options')
    info.add_argument("--json",  "-j", action="store_true", help="Export to JSON, implies --all")

#    print(parser.parse_args(args))
    return parser.parse_args(args)


if __name__ == "__main__":
    cli()

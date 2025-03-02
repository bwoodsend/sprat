import io
import os
import re
import sys
import textwrap

import sprat


def info(options):
    try:
        if any("*" in i for i in options.packages):
            packages = []
            for glob in options.packages:
                regex = re.compile(glob.encode().replace(b"*", b".*"))
                new = [sprat.Package.parse(i[0].decode(), i[1]) for i in sprat.with_prefix(glob.split("*")[0]) if regex.fullmatch(i[0])]
                if not new:
                    die(1, f"No package matching pattern '{glob}'")
                packages += new
        else:
            packages = sprat.bulk_lookup(options.packages)
        lines = []
        if options.json:
            for package in packages:
                print(jsonify(package))
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
                        entry = RED + entry + GREY
                    versions.append(("", entry))
                    if "yanked" in info:
                        if info["yanked"]:
                            reason = textwrap.wrap(info["yanked"])
                            versions.append(("", RED + reason[0] + GREY))
                            versions += (("", RED + i + GREY) for i in reason[1:])
                versions[0] = ("Versions", versions[0][1])
            else:
                versions = []
            lines += [
                ("Name", package.name),
                ("Version", latest),
                ("Summary", package.summary),
                ("Keywords", ", ".join(sorted(package.keywords))),
                *urls,
                ("License", package.license_expression),
                *classifiers,
                *versions,
                ("", ""),
            ]
        print_info_table(lines)
    except sprat.NoSuchPackageError as ex:
        die(1, f"No such package '{ex.args[0]}'")


def jsonify(package):
    import json
    return json.dumps({
        "name": package.name,
        "summary": package.summary,
        "keywords": sorted(package.keywords),
        "urls": package.urls,
        "classifiers": sorted(package.classifiers, key=sprat.classifier_sort_key),
        "license": package.license_expression,
        "versions": package.versions,
    }, separators=(",", ":"))


def print_info_table(lines):
    width = max(len(i[0]) for i in lines) + 2
    for (caption, content) in lines[:-1]:
        if caption == "Name":
            print(RESET, caption.ljust(width), ": ", content, sep="")
        else:
            print(caption.ljust(width), ": ", GREY, content, RESET, sep="")


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
    for term in all_terms:
        if not term:
            die(2, "Empty search terms are not allowed")
    if len(all_terms) == 0:
        if options.quiet:
            for (id, block) in sprat.iter():
                print(id.decode())
            return True
    try:
        prefixes = (pattern[1:] for pattern in options.name or () if pattern.startswith("^"))
        prefix = max(prefixes, key=_literal_length)
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

    highlighter = Highlighter(options.terms, options.name, options.summary, options.keyword, options.classifier)
    for (name, block) in filtered:
        package = sprat.Package.parse(name.decode(), block, ignore_versions=True)
        if filter.filter(package):
            found += 1
            if options.quiet:
                print(name.decode())
                continue
            if options.json:
                print(jsonify(package))
                continue
            if not options.long:
                print(highlighter.name.on_default(package.name))
                _summary = highlighter.summary.on_grey(package.summary)
                for line in textwrap.wrap(_summary, 120):
                    print("   ", line)
                continue

            if found > 1:
                print()
            lines = [
                ("Name", highlighter.name.on_default(package.name)),
                ("Summary", highlighter.summary.on_grey(package.summary)),
            ]
            if package.keywords:
                _joined = ", ".join(highlighter.keyword.raw(GREY, w)[0] for w in package.keywords)
                lines.append(("Keywords", GREY + _joined + RESET))
            homepage = package.urls.get("Homepage", f"https://pypi.org/p/{package.name}")
            lines.append(("Homepage", GREY + homepage + RESET))

            classifier_match = False
            classifier_lines = []
            for classifier in sorted(package.classifiers, key=sprat.classifier_sort_key):
                highlighted, n = highlighter.classifier.raw(GREY, classifier)
                highlighted = GREY + highlighted + RESET
                classifier_match |= bool(n)
                classifier_lines.append(("Classifiers" if not classifier_lines else "", highlighted))
            if classifier_match:
                lines += classifier_lines
            [print(i.ljust(13), ": ", j, sep="") for (i, j) in lines]

    return found > 0


if "FORCE_COLOR" in os.environ:
    color_output = True
elif "ANSI_COLORS_DISABLED" in os.environ or "NO_COLOR" in os.environ:
    color_output = False
elif os.environ.get("TERM") == "dumb":
    color_output = False
else:
    try:
        color_output = os.isatty(sys.stdout.fileno())
    except (io.UnsupportedOperation, AttributeError):
        color_output = False

if color_output:
    RESET = "\x1b[0m"
    GREY = "\x1b[37m"
    RED = "\x1b[31m"
else:
    RESET = GREY = RED = ""


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


class Highlighter:
    def __init__(self, any, name, summary, keyword, classifier):
        self.any = self.Group(any, name, summary, keyword, classifier)
        self.name = self.Group(name, any)
        self.summary = self.Group(summary, any)
        self.keyword = self.Group(keyword, any)
        self.classifier = self.Group(classifier, any)

    class Group:
        def __init__(self, *terms):
            pattern = "|".join("(?:" + i + ")" for j in terms for i in j or ())
            self.pattern = re.compile(pattern or "$^", flags=re.I)

        def raw(self, background, word):
            return self.pattern.subn(lambda m: RED + m[0] + background, word)

        def on_grey(self, word):
            return GREY + self.raw(GREY, word)[0] + RESET

        def on_default(self, word):
            return self.raw(RESET, word)[0]


def cli(args=None):
    try:
        options = _parse_args(args)
        if options.command == "update":
            sprat.update(options.index_file)
        if options.command == "info":
            info(options)
        if options.command == "search":
            if not search(options):
                sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        pass
    except sprat.DatabaseUninitializedError:
        die(3, "Repository database has not been downloaded. Please run: sprat update")


def die(code, message):
    print("sprat error: " + message, file=sys.stderr)
    sys.exit(code)


def _parse_args(args=None):
    import argparse
    parser = argparse.ArgumentParser("sprat")
    subparsers = parser.add_subparsers(required=True, metavar="COMMAND", dest="command")

    update = subparsers.add_parser("update", help="Download latest index")
    update.add_argument("--index-file", metavar="FILE")

    search = subparsers.add_parser("search", help="List packages matching a pattern or other criteria")
    search.add_argument("terms", nargs="*")
    search.add_argument("--name", "-n", nargs="+", dest="name")
    search.add_argument("--summary", "-s", nargs="+", dest="summary")
    search.add_argument("--keywords", "-k", nargs="+", dest="keyword")
    search.add_argument("--classifiers", "-c", nargs="+", dest="classifier")
    search.add_argument("--long", "-l", action="store_true")
    search.add_argument("--quiet", "-q", action="store_true")
    search.add_argument("--json",  "-j", action="store_true", help="Export to JSON")

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

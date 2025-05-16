import io
import os
import re
import sys
import textwrap

import sprat


def expand_package_globs(packages):
    if any("*" in i for i in packages):
        for glob in packages:
            regex = re.compile(sprat.sluggify(glob).encode().replace(b"*", b".*"))
            found = False
            for (name, chunk) in sprat.raw_with_prefix(glob.split("*")[0]):
                if regex.fullmatch(sprat.sluggify_b(name)):
                    found = True
                    yield sprat.Package.parse(name, chunk)
            if not found:
                die(1, f"No package matching pattern '{glob}'")
    else:
        yield from sprat.bulk_lookup(packages)


def info(options):
    try:
        packages = expand_package_globs(options.packages)
        lines = []
        if options.json:
            for package in packages:
                print(jsonify(package))
            return

        for (i, package) in enumerate(packages):
            latest = ""
            for version in package.versions:
                if "yanked" not in package.versions[version]:
                    latest = version
            if options.urls or options.all:
                urls = sorted(package.urls.items())
            else:
                urls = [i for i in package.urls.items() if i[0] == "Homepage"]
            if options.classifiers or options.all:
                _classifiers = sorted(package.classifiers,
                                      key=sprat.classifier_sort_key)
                classifiers = [("Classifiers", i) for i in _classifiers[:1]]
                classifiers += [("", i) for i in _classifiers[1:]]
            else:
                classifiers = []
            if (options.versions or options.all) and package.versions:
                version_width = 0
                for (version, info) in package.versions.items():
                    version_width = max(version_width,
                                        len(version) + 8 * ("yanked" in info))
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
                            for line in textwrap.wrap(info["yanked"]):
                                versions.append(("", " " + RED + line + GREY))
                versions[0] = ("Versions", versions[0][1])
            else:
                versions = []
            lines = [
                ("Name", package.name),
                ("Version", latest),
                ("Summary", package.summary),
                ("Keywords", ", ".join(sorted(package.keywords))),
                *urls,
                ("License", package.license),
                *classifiers,
                *versions,
            ]
            if i != 0:
                print()
            # URLs are the only keys of variable length. Several of the common
            # ones are 13 characters long (Issue Tracker, Documentation, Release
            # Notes) and anything longer is much rarer.
            if options.urls or options.all:
                print_info_table(lines, min_width=13)
            # The key `Classifiers` is 11 characters long.
            elif options.classifiers:
                print_info_table(lines, width=11)
            # `Keywords` is 8 characters long.
            else:
                print_info_table(lines, width=8)
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
        "license": package.license,
        "versions": package.versions,
    }, separators=(",", ":"))


def print_info_table(lines, width=None, min_width=None):
    if min_width:
        width = max(min_width, max(len(i[0]) for i in lines)) + 2
    else:
        width = width + 2
    for (caption, content) in lines:
        if caption == "Name":
            print(RESET, caption.ljust(width), ": ", content, sep="")
        else:
            print(caption.ljust(width), ": ", GREY, content, RESET, sep="")


def _literal_length(regex):
    length = next((i for (i, c) in enumerate(regex) if c != "-" and re.escape(c) != c),
                  len(regex))
    if 1 <= length < len(regex) and regex[length] in "*?{":
        length -= 1
    return length


def search(options):
    all_terms = []
    for _terms in (options.terms, options.name, options.summary,
                   options.keyword, options.classifier):
        if _terms:
            all_terms += _terms
    for term in all_terms:
        if not term:
            die(2, "Empty search terms are not allowed")
    if len(all_terms) == 0:
        if options.quiet:
            for (id, block) in sprat.raw_iter():
                print(id.decode())
            return True
    try:
        prefixes = (p[1:] for p in options.name or () if p.startswith("^"))
        prefix = max(prefixes, key=_literal_length)
    except ValueError:
        prefix = ""
    if prefix:
        filtered = sprat.raw_with_prefix(prefix[:_literal_length(prefix)])
    else:
        if all_terms:
            term = max(all_terms, key=lambda t: 2 * len(t) - len(re.escape(t)))
            filtered = sprat.raw_crude_search(term, case_sensitive=False)
        else:
            filtered = sprat.raw_iter()
    filter = Filter(options.terms, options.name, options.summary,
                    options.keyword, options.classifier)

    if filter.name and not (prefix and len(filter.name) == 1 == len(filter.all)):
        filtered = (i for i in filtered if filter.filter_name(i[0].decode()))

    found = 0
    if options.quiet and len(filter.name) == len(filter.all):
        for (name, _) in filtered:
            print(name.decode())
            found += 1
        return found

    highlighter = Highlighter(options.terms, options.name, options.summary,
                              options.keyword, options.classifier)
    for (name, block) in filtered:
        package = sprat.Package.parse(name, block, ignore_versions=True)
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
                print(color_textwrap(_summary, "    ", 80), end="")
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
            homepage = package.urls.get("Homepage",
                                        f"https://pypi.org/project/{package.name}")
            lines.append(("Homepage", GREY + homepage + RESET))

            classifier_match = False
            classifier_lines = []
            for classifier in sorted(package.classifiers, key=sprat.classifier_sort_key):
                highlighted, n = highlighter.classifier.raw(GREY, classifier)
                highlighted = GREY + highlighted + RESET
                classifier_match |= bool(n)
                if classifier_lines:
                    classifier_lines.append(("", highlighted))
                else:
                    classifier_lines.append(("Classifiers", highlighted))
            if classifier_match:
                lines += classifier_lines
            print_info_table(lines, width=11)

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


def color_textwrap(text, indentation, width):
    """textwrap.wrap() replacement that knows to ignore ANSI color sequences"""
    width -= len(indentation)
    line_length = 0
    word_length = 0
    last_space = None
    breaking_space = []
    for match in re.finditer("\x1b\\[(?:37|0|31)m|(\\s+)|([^\\s\x1b]+)", text):
        if match[1]:  # whitespace
            last_space = match
            line_length += word_length
            word_length = 0
            if len(match[0]) + line_length > width:
                breaking_space.append(match)
                last_space = None
                line_length = 0
            else:
                line_length += len(match[0])
        elif match[2]:  # significant (not space or ANSI) text
            word_length += len(match[2])
            if last_space and line_length + word_length > width:
                breaking_space.append(last_space)
                line_length = 0
                last_space = None
    start = 0
    chunks = []
    for match in breaking_space:
        if match is None:  # word too long to wrap
            continue
        chunks.append(indentation)
        chunks.append(text[start:match.start()])
        chunks.append("\n")
        start = match.end()
    chunks.append(indentation)
    chunks.append(text[start:])
    chunks.append("\n")
    return "".join(chunks)


class Filter:
    def __init__(self, any, name, summary, keyword, classifier):
        self.any = self._precompile(any)
        self.name = self._precompile(name)
        self.summary = self._precompile(summary)
        self.keyword = self._precompile(keyword)
        self.classifier = self._precompile(classifier)
        self.all = self.any + self.name + self.summary + self.keyword + self.classifier

    @staticmethod
    def _precompile(terms):
        return [re.compile(i, flags=re.I) for i in terms or []]

    def strongest(self):
        return max(self.all, key=lambda p: 2 * len(p.pattern) - len(re.escape(p.pattern)))

    def filter_name(self, name):
        return all(pattern.search(name) for pattern in self.name)

    def filter(self, package):
        flat = [package.summary, package.name, *package.keywords, *package.classifiers]
        for pattern in self.any:
            if not any(map(pattern.search, flat)):
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
            if pattern:
                self.pattern = re.compile("(?:" + pattern + ")+", flags=re.I)
            else:
                self.pattern = self._no_op_pattern

        def raw(self, background, word):
            return self.pattern.subn(lambda m: RED + m[0] + background, word)

        def on_grey(self, word):
            return GREY + self.raw(GREY, word)[0] + RESET

        def on_default(self, word):
            return self.raw(RESET, word)[0]

        class _no_op_pattern:
            def subn(x, y):
                return y, 0


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
    except sprat.UpdateAlreadyInProgressError:
        die(128, "Database is locked. A sprat update is already in progress")
    except BrokenPipeError:
        pass
    except sprat.DatabaseUninitializedError:
        die(3, "Packages database has not been downloaded. Please run: sprat update")


def die(code, message):
    print("sprat error: " + message, file=sys.stderr)
    sys.exit(code)


def _parse_args(args=None):
    import argparse
    _ = lambda x: re.sub(r"\s+", " ", x)
    parser = argparse.ArgumentParser("sprat")
    subparsers = parser.add_subparsers(required=True, metavar="COMMAND", dest="command")

    update = subparsers.add_parser("update", help="Download latest index")
    update.add_argument("--index-file", metavar="FILE")


    search = subparsers.add_parser("search", help= \
        "List packages matching a pattern or other criteria")
    search.add_argument("terms", nargs="*")
    search.add_argument("--name", "-n", action="append", dest="name")
    search.add_argument("--summary", "-s", action="append", dest="summary")
    search.add_argument("--keywords", "-k", action="append", dest="keyword")
    search.add_argument("--classifiers", "-c", action="append", dest="classifier")
    search.add_argument("--long", "-l", action="store_true")
    search.add_argument("--quiet", "-q", action="store_true")
    search.add_argument("--json",  "-j", action="store_true", help= \
        "Export to JSON")

    info = subparsers.add_parser("info", help= \
        "Show details of a given package")
    info.add_argument("packages", nargs="+")
    info.add_argument("--urls", "-u", action="store_true", help= \
        "Show all URLs, defaults to just the Homepage")
    info.add_argument("--classifiers", "-c", action="store_true", help= \
        "Show classifiers")
    info.add_argument("--versions", "-v", action="store_true", help= \
        "List releases")
    info.add_argument("--all", "-a", action="store_true", help= \
        'Show everything, equivalent to --urls --classifiers --versions '
        'plus any future "show more" options')
    info.add_argument("--json",  "-j", action="store_true", help= \
        "Export to JSON, implies --all")

    return parser.parse_args(args)


if __name__ == "__main__":
    cli()

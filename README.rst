=================
Welcome to sprat!
=================

``sprat`` is a command line tool and Python library for searching PyPI,
replacing what was once ``pip search``.

.. code-block:: bash

    $ sprat search opengl 3d --classifiers 'Python :: 3.13'
    flitter-lang
        Flitter is a functional programming language and declarative system for
        describing 2D and 3D visuals
    ps2mc-browser
        A PS2 save file viewer with OpenGL 3D icon rendering support.
    pyglm
        OpenGL Mathematics library for Python
    ...

.. code-block:: bash

    $ sprat info norwegianblue
    Name      : norwegianblue
    Version   : 0.22.0
    Summary   : CLI to show end-of-life dates for a number of products
    Keywords  : cli, end-of-life, endoflife, eol
    Homepage  : https://github.com/hugovk/norwegianblue
    License   : MIT


Background
----------

Some time ago, packages on PyPI could be discovered using the ``pip search``
command – a CLI wrapper around a PyPI search API which was unfortunately so
overloaded with excessive machine usage that it had to be switched off
indefinitely.

Overtime, people have moved to web scraping `pypi.org/search
<https://pypi.org/search/>`_, which again disrupted PyPI to the point where
browser verification had to be installed to block such usage.

``sprat`` also seeks to provide CLI and programmatic searching of PyPI but, in
order to avoid the same fate as ``pip search``, ``sprat`` does not talk to PyPI
directly. A `single database
<https://github.com/bwoodsend/sprat/releases/tag/database-v1>`_ of project
metadata is `built externally
<https://github.com/bwoodsend/sprat/actions/workflows/sync.yml>`_, all ``sprat``
users download that database then ``sprat`` does all its searching offline.
(This should sound familiar to anyone whose used package mangers like ``apt`` or
``dnf``.) Updates are incrementally synced from PyPI to the database and from
the database to ``sprat`` making both parts of the transaction as economic as
possible.


Installation
------------

``sprat`` is remaining off PyPI until it shows signs of being used (and I'm more
confident that PyPI's accelerating growth won't kill it). To install ``sprat``
from source run::

    git clone https://github.com/bwoodsend/sprat.git
    cd sprat
    pip install -e .

Later, to update, run:

.. code-block:: bash

    git pull
    pip install -e .  # Only needed if dependencies have changed

The ``sprat`` command comes with bash and fish completions. If using either of
those shells then you can install the appropriate completion file using:

.. code-block:: bash

    sudo ln -s "$PWD/sprat/_sprat.bash" /usr/share/bash-completion/completions/sprat
    # Or
    ln -s $PWD/sprat/_sprat.fish ~/.config/fish/completions/sprat.fish


CLI Usage
---------

Before ``sprat`` can do anything, it needs to download its database::

    sprat sync

As packages and releases are subsequently uploaded to PyPI, run ``sync`` again
for those uploads to propagate. ``sprat`` will never automatically resynchronise
– no matter how stale its local database is.

All other ``sprat`` operations run offline.


Searching for packages
~~~~~~~~~~~~~~~~~~~~~~

Basic search (hopefully self explanatory):

.. code-block::

    # Find a package containing "pytest plugin" and "json"
    $ sprat search 'pytest plugin' json
    pytest-data-extractor
        A pytest plugin to extract relevant metadata about tests into an external
        file (currently only json support)
    pytest-dump2json
        A pytest plugin for dumping test results to json.
    pytest-json-ctrf
        Pytest plugin to generate json report in CTRF (Common Test Report Format)
    pytest-json-report
        A pytest plugin to report test results as JSON files
    pytest-json-report-wip
        A pytest plugin to report test results as JSON files
    pytest-jsonschema
        A pytest plugin to perform JSONSchema validations
    pytest-jtr
        pytest plugin supporting json test report output
    pytest-pydantic-schema-sync
        Pytest plugin to synchronise Pydantic model schemas with JSONSchema files
    pytest-variables
        pytest plugin for providing variables to tests/fixtures
    pytest-xray-reporter
        A pytest plugin that generates test results in Xray JSON format
    test-guide-pytest-json
        A pytest plugin to generate JSON reports, with ATX support.

``sprat``\ 's search output favours compactness over completeness of
information. Once you've applied sufficient filtering that the output isn't
unusably long, you can switch to ``-l/--long`` format.

.. code-block:: bash

    $ sprat search --long pytest
    Name         : adcm-pytest-plugin
    Summary      : The pytest plugin including a set of common tools for ADCM testing
    Homepage     : https://pypi.org/project/adcm-pytest-plugin
    Classifiers  : Framework :: Pytest

    Name         : adilmar-libpythonpro-package
    Summary      : Módulo para exemplificar construção de projetos Python no curso PyTools
    Homepage     : https://github.com/pythonprobr/libpythonpro
    Classifiers  : Development Status :: 2 - Pre-Alpha
                 : Environment :: Console
                 : Framework :: Pytest
                 : Intended Audience :: Developers
                 : License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)
                 : Operating System :: OS Independent
                 : Programming Language :: Python
                 : Programming Language :: Python :: 3.6

    ...

Without flags, a package is considered a match if each term is found in any of
the its searchable fields (name, summary, keywords and classifiers). Search
terms can target specific fields using:

.. code-block:: bash

    sprat search --name boto
    sprat search --summary 'linear programming'
    sprat search --keyword ASGI
    sprat search --classifier 'Programming Language :: Python :: 3.14'

Search terms are regexs. Regex patterns give you wildcards (``.*``), whole word
(``\bword\b``) or whole term (``^whole term$``) matches, character ranges
(``[a-z]``), unions (``foo|bar``), etc.

.. code-block:: bash

    # Search for "REST" but ignore "restaurant" or "interest"
    sprat search '\bREST\b'
    # Search for "CI/CD" or "continuous integration"
    sprat search 'CI/CD|continuous integration'
    # Search by name prefix
    sprat search --name '^pytest-'
    # Search with wildcard
    sprat search --name '^poetry-.*-plugin'
    # Handle localised spellings
    sprat search 'visuali[sz]ation'

There are half-hearted *machine readable* formats: ``-q/--quiet`` lists only
package names and ``-j/--json`` outputs in JSONL.

.. code-block:: bash

    # Count how many packages declare themselves as typed
    sprat search --classifier 'Typing :: Typed' --quiet | wc -l
    # Do weird custom data slicing with jq
    sprat search -j | jq '{(.name): (.versions | length)}'

There's a `Python API`_ for anything the CLI doesn't cover.


Querying packages
~~~~~~~~~~~~~~~~~

The ``info`` command displays information about a given package:

.. code-block::

    $ sprat info meson-python
    Name      : meson-python
    Version   : 0.18.0
    Summary   : Meson Python build backend (PEP 517)
    Keywords  : backend, build, meson, package, pep517
    Homepage  : https://github.com/mesonbuild/meson-python
    License   : MIT

Again, ``sprat`` errs on the side of trying not to swamp the terminal with text
(particularly given the overenthusiasm with which some packages add URLs and
classifiers). By default, only the homepage URL and no classifiers or versions
are displayed. Extra information can be shown using the ``-c/--classifiers``,
``-u/--urls``, ``-v/--versions`` or ``-a/--all`` flags.

.. code-block::

    $ sprat info meson-python -a
    Name           : meson-python
    Version        : 0.18.0
    Summary        : Meson Python build backend (PEP 517)
    Keywords       : backend, build, meson, package, pep517
    Changelog      : https://mesonbuild.com/meson-python/changelog.html
    Documentation  : https://mesonbuild.com/meson-python/
    Homepage       : https://github.com/mesonbuild/meson-python
    Source Code    : https://github.com/mesonbuild/meson-python
    License        : MIT
    Classifiers    : Development Status :: 5 - Production/Stable
                   : Programming Language :: Python
                   : Topic :: Software Development :: Build Tools
    Versions       : 0.1.0          : Python>=3.7
                   : 0.1.1          :
                   : 0.1.2          :
                   : 0.2.0          :
                   : 0.2.1          :
                   : 0.3.0          :
                   : 0.4.0          :
                   : 0.5.0          :
                   : 0.6.0          :
                   : 0.7.0          :
                   : 0.8.0 (yanked) :
                   :  https://github.com/FFY00/meson-python/issues/118
                   : 0.8.1          :
                   : 0.9.0          :
                   : 0.10.0         :
                   : 0.11.0         :
                   : 0.12.0         :
                   : 0.13.0rc0      :
                   : 0.12.1         :
                   : 0.13.0         :
                   : 0.13.1         :
                   : 0.13.2         :
                   : 0.14.0         :
                   : 0.15.0         :
                   : 0.16.0         :
                   : 0.17.0         :
                   : 0.17.1         :
                   : 0.18.0         : Python>=3.8

Multiple package names and globs are supported:

.. code-block:: bash

    $ sprat info "zope*"
    Name      : Zope
    Version   : 5.13
    Summary   : Zope application server / web framework
    Keywords  : 
    Homepage  : https://zope.readthedocs.io/en/latest/
    License   : 

    Name      : zope.annotation
    Version   : 5.1
    Summary   : Object annotation mechanism
    Keywords  : zope annotation ZODB zope3 ztk
    Homepage  : https://github.com/zopefoundation/zope.annotation
    License   : 
    ...
    [lots of zope packages]

Again, there's a JSONL mode which plays well with `jq <https://jqlang.org/>`_ in
scripts.

.. code-block:: bash

    $ sprat info numpy scipy matplotlib --json | jq -r .urls.Homepage
    https://numpy.org
    https://scipy.org/
    https://matplotlib.org


Python API
----------

Most simple usage of ``sprat``\ 's Python API distils down to calling either
``sprat.lookup()`` for information on a specific package or ``sprat.iter()`` for
searching.

.. code-block:: python

    import sprat

    # Lookup a package by name
    package = sprat.lookup("numpy")
    # Or Lookup packages in bulk. This is more optimized than individual lookups.
    names = ["pytest", "pytest-cov", "pytest-echo"]
    packages = dict(zip(names, sprat.bulk_lookup(names)))

    # Iterate through all available packages:
    for package in sprat.iter():
        if "eggs" in package.summary:
            print(package.name)

If performance isn't an issue then that is all you need. The rest of the API is
just variations of ``sprat.iter()`` with opportunistic optimisations and
shortcuts.

.. code-block:: python

    # Unpacking each package's version information is expensive. When version
    # information isn't needed you can skip parsing it.
    for package in sprat.iter(ignore_versions=True):
        if "eggs" in package.summary:
            print(package.name)

    # Literal or regex searches can be optimised by finding search terms in the
    # raw, unparsed (clear text) database then only unpacking the packages with
    # matches. This process does not discriminate between the package's fields
    # so more precise filtering is still required on the subset that get
    # through.
    for package in sprat.crude_search("eggs"):  # <-- "eggs" is a regex
        if "eggs" in package.summary:
            print(package.name)
    
    # Some packages belong to groups with a common naming prefix. sprat's
    # database is organised alphabetically making searching by prefix much more
    # efficient that brute force.
    for package in sprat.with_prefix("ansible-"):
        assert sprat.sluggify(package.name).startswith("ansible-")

    # For when only package names are required, or when filtering by name, each
    # of sprat's search functions has a raw_ variant which can also be used to
    # skip unnecessarily parsing packages.
    for (name, data) in sprat.raw_iter():
        # When working with raw names, be careful to sluggify them to avoid case
        # sensitivity and - vs _ vs . bugs.
        if b"eggs" not in sprat.sluggify_b(name):
            continue
        # PyPI names are guaranteed to be ASCII.
        print(name.decode("ascii"))
        # Parse a package of interest:
        package = sprat.Package.parse(name, data, ignore_versions=True)


Supported Fields
----------------

``sprat`` collects the following information about each package. All fields par
the per-version fields reflect their values as of the latest version of a given
package.

* `name
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#name>`_
  (``str``): Stored without `normalisation
  <https://packaging.python.org/en/latest/specifications/name-normalization/#name-normalization>`_
  (although ``sprat info NUMPY``) will still work.

* `summary
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#description>`_
  (``str``): With line-breaks and indentation removed.

* `keywords
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#keywords>`_
  (``set[str]``): Given the lack of standardisation on what delimits a list of
  keywords, ``sprat`` reluctantly uses the heuristic of splitting a keywords
  string into a list on commas and newlines if either exist or whitespace
  otherwise.

* `urls
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#urls>`_
  (``dict[str, str]``): Empty URLs are removed, `well known URL labels
  <https://packaging.python.org/en/latest/specifications/well-known-project-urls/#well-known-labels>`_
  are normalised into their canonical *human readable* form.

* `classifiers
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#classifiers>`_
  (``set[str]``): Consumed as-is. 🚀

* `license
  <https://packaging.python.org/en/latest/specifications/declaring-project-metadata/#license>`_
  (``str``): Strictly the new *license expression* field. ``sprat`` makes no
  effort to amalgamate it with the legacy license field or license classifiers.

* ``versions`` (``dict[str, dict]``): Listed in order of release date rather
  than lowest highest version, filtered for validity via
  `packaging.version.Version()
  <https://packaging.pypa.io/en/stable/version.html#packaging.version.Version>`_.
  Note that it is possible for a package to not have any versions. Each version
  may optionally contain:

  - `requires_python
    <https://packaging.python.org/en/latest/specifications/pyproject-toml/#requires-python>`_
    (``str``): Filtered for validity via `packaging.specifiers.SpecifierSet()
    <https://packaging.pypa.io/en/stable/specifiers.html#packaging.specifiers.SpecifierSet>`_.

  - ``yanked`` (``str``): The reason for the release being yanked or possibly
    an empty string to indicate being yanked without explanation. Line-breaks
    and indentation are removed.

Packages or versions that are deleted from PyPI are not exposed in any way.
``sprat`` will simply act like they never existed. Quarantined packages are
treated as if they were deleted.


Unsupported Fields
~~~~~~~~~~~~~~~~~~

Fields that at least sound to me like they may be meaningfully and possible to
support in the future:

* Release timestamps
* Wheel tags (for non pure Python packages)

Fields that are unlikely to be supported:

* Long descriptions: The sum of all long descriptions on PyPI is (as of time of
  writing) 1.1 GB and whose contents vary from a handful of URLs to the whole
  documentation to some likely irrelevant developer guide – none of which
  provide good quality search data.

* Download counts: Are always in motion so they'd ruin incremental syncing.

* Legacy licence specifiers: Lack any definition as to what they really mean.
  They may be a well defined SPDX identifier, an ambiguous identifier (Apache,
  BSD), a random summary sentence or the entire contents of the license file.

* Authors/Maintainers: There's too much uncertainty around Author versus Author
  + Author-Email versus an Author-Email containing both the author and email
  address. Additionally, PyPI's JSON API only exposes one of each.

* Dependencies: Can be dynamic or or inconsistent between wheels, even within a
  single version, and aren't available using PyPI's JSON API.


Deploying sprat
---------------

``sprat`` was written for console/terminal bashing and light informal scripting.
There are non-obvious reasons why doing more with it is likely a bad idea:

As ``sprat`` and the world of Python packaging evolve, ``sprat``\ 's database
format will need changes. When the format changes, old versions of ``sprat``
will no longer be able to sync database updates. To that end, ``sprat`` must
never be put somewhere where it can not be easily updated such as a statically
bundled end user application.

Searches in ``sprat`` are regex driven which, if the regex is untrusted, means
ReDoS attacks via `explosive quantifiers
<https://www.rexegg.com/regex-explosive-quantifiers.php>`_.

.. code-block:: bash

    # How long do you think this will take to finish?
    sprat search '.*.*.*.*.*.*.*0$'

Anyone considering putting ``sprat`` in a web server should disallow or escape
user-defined regex patterns as inputs and/or limit response execution time.

"""Sphinx configuration for Luna GUI Wrapper documentation."""

import os
import sys

sys.path.insert(0, os.path.abspath("../src"))

from luna_gui_wrapper import __version__  # noqa: E402

project = "Luna GUI Wrapper"
copyright = "2026, Sergei Kulkov"
author = "Sergei Kulkov"
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "sphinx_rtd_theme"

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Links to headings (installation.md#linux ...) resolve to heading anchors.
myst_heading_anchors = 3

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

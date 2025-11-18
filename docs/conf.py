# Configuration file for the Sphinx documentation builder.

import os
import sys
sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../users_service"))
sys.path.insert(0, os.path.abspath("../room_service"))
project = 'Smart Meeting Room Backend'
copyright = '2025, Nour Shammaa and Riwa ElKari'
author = 'Nour Shammaa and Riwa ElKari'
release = 'v1'

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'alabaster'
html_static_path = ['_static']

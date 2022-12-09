"""Sphinx configuration file for an LSST stack package.

This configuration only affects single-package Sphinx documentation builds.
"""

import lsst.ts.atmonochromator  # noqa
from documenteer.conf.pipelinespkg import *  # noqa

project = "ts_atmonochromator"
html_theme_options["logotext"] = project  # type: ignore # noqa
html_title = project
html_short_title = project
doxylink = {}  # type: ignore

intersphinx_mapping["ts_xml"] = ("https://ts-xml.lsst.io", None)  # type: ignore # noqa
intersphinx_mapping["ts_salobj"] = ("https://ts-salobj.lsst.io", None)  # type: ignore # noqa
intersphinx_mapping["ts_utils"] = ("https://ts-utils.lsst.io", None)  # type: ignore # noqa

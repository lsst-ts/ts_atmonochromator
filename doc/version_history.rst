0.5.0 (2024-08-23)
==================

New Features
------------

- Add ack_in_progress calls to long running commands. (`DM-45282 <https://rubinobs.atlassian.net//browse/DM-45282>`_)


Bug Fixes
---------

- Made conda recipe run unit tests. (`DM-45282 <https://rubinobs.atlassian.net//browse/DM-45282>`_)
- Moved enum imports from idl to xml. (`DM-45282 <https://rubinobs.atlassian.net//browse/DM-45282>`_)
- CSC will transition to fault state if the connection is lost. (`DM-45790 <https://rubinobs.atlassian.net//browse/DM-45790>`_)


Documentation
-------------

- Added towncrier support. (`DM-45282 <https://rubinobs.atlassian.net//browse/DM-45282>`_)


.. py:currentmodule:: lsst.ts.atmonochromator

.. _lsst.ts.atmonochromator.version_history:

###############
Version History
###############

v0.3.4
------

* Use !SET tcp command for changing wavelength.
* Implement ts_tcpip Client for handling tcpip connection.

v0.3.2
------

* Add except to try-finally clause when disconnecting.
* Fix sconscript name.

v0.3.1
------

* Include conda build scripts.
* Update pre-commit configuration.
* Update to pyproject.toml.
* Rename executable.

v0.3.0
------

* Upgrade to salobj 7
* Add support for python type annotations and enable mypy.

v0.2.0
------

* Modernize the code.
* This version requires ts_idl 3.6

v0.1.1
------

* Fix some flake8 warnings.


v0.1.0
------

* First release.

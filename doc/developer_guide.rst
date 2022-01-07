.. py:currentmodule:: lsst.ts.atmonochromator

.. _lsst.ts.atmonochromator.developer_guide:

###############
Developer Guide
###############

The ATMonochromator CSC is implemented using `ts_salobj <https://github.com/lsst-ts/ts_salobj>`_.

The CSC controls the monochromator using a TCP/IP connection to a low-level hardware controller.
The Monochromator TCP Protocol is specified here:
https://confluence.lsstcorp.org/display/LTS/Monochromator+TCP+Protocol

.. _lsst.ts.atmonochromator.api:

API
===

The primary classes are:

* `MonochromatorCsc`: controller for the auxiliary telescope dome.
* `MockController`: simulator for the low-level controller.

.. automodapi:: lsst.ts.atmonochromator
    :no-main-docstr:

.. _lsst.ts.atmonochromator.build:

Build and Test
==============

This is a pure python package. There is nothing to build except the documentation.

.. code-block:: bash

    make_idl_files.py ATMonochromator
    setup -r .
    pytest -v  # to run tests
    package-docs clean; package-docs build  # to build the documentation

.. _lsst.ts.atmonochromator.contributing:

Contributing
============

``lsst.ts.atmonochromator`` is developed at https://github.com/lsst-ts/ts_atmonochromator.
Bug reports and feature requests use `Jira with labels=ts_atmonochromator <https://jira.lsstcorp.org/issues/?jql=project%20%3D%20DM%20AND%20labels%20%20%3D%20ts_atmonochromator>`_.

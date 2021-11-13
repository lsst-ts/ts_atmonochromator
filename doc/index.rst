.. py:currentmodule:: lsst.ts.atmonochromator

.. _lsst.ts.atmonochromator:

#######################
lsst.ts.atmonochromator
#######################

.. image:: https://img.shields.io/badge/SAL\ Interface-gray.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/atmonochromator.html
.. image:: https://img.shields.io/badge/GitHub-gray.svg
    :target: https://github.com/lsst-ts/ts_atmonochromator
.. image:: https://img.shields.io/badge/Jira-gray.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_atmonochromator

.. _lsst.ts.atmonochromator.overview:

Overview
========

The ATMonochromator CSC controls the Monochromator for the Vera C. Rubin Observatory Auxiliary Telescope.

The CSC talks via TCP/IP to a low-level hardware controller.

.. _lsst.ts.atmonochromator.user_guide:

User Guide
==========

Start the atmonochromator CSC as follows:

.. prompt:: bash

    atmonochromator_csc.py

Stop the CSC by sending it to the OFFLINE state.

See atmonochromator `SAL communication interface <https://ts-xml.lsst.io/sal_interfaces/atmonochromator.html>`_ for commands, events and telemetry.

.. _lsst.ts.atmonochromator.configuration:

Configuration
-------------

The default configuration is mostly usable, but the default host is LOCALHOST.

Configuration is defined by `this schema <https://github.com/lsst-ts/ts_atmonochromator/blob/develop/schema/atmonochromator.yaml>`_.

Configuration files live in `ts_config_atcalsys/ATMonochromator <https://github.com/lsst-ts/ts_config_atcalsys/tree/develop/ATMonochromator>`_.

.. _lsst.ts.atmonochromator.simulation:

Simulator
---------

The CSC includes a simulation mode. To run using simulation:

.. prompt:: bash

    atmonochromator_csc.py --simulate

Developer Guide
===============

.. toctree::
    developer_guide
    :maxdepth: 1

Version History
===============

.. toctree::
    version_history
    :maxdepth: 1

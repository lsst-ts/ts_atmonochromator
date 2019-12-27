# This file is part of ts_atmonochromator.
#
# Developed for the LSST Telescope and Site System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

import os
import glob
import asyncio
import logging
import pathlib
import unittest
import asynctest

from lsst.ts import salobj

from lsst.ts.monochromator import monochromator_csc as csc
from lsst.ts.monochromator import SimulationConfiguration

from lsst.ts.idl.enums import ATMonochromator

TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

STD_TIMEOUT = 5.
LONG_TIMEOUT = 30.
LONG_LONG_TIMEOUT = 120.


class Harness:
    def __init__(self, initial_simulation_mode=0, config_dir=None):

        self.log = logging.getLogger("harness")

        self.csc = csc.CSC(initial_simulation_mode=initial_simulation_mode,
                           config_dir=config_dir)
        self.remote = salobj.Remote(self.csc.domain, "ATMonochromator")

    def error_code_callback(self, data):
        """Auxiliary callback method to output error code in case any is
        published during the test.
        """
        self.log.error(f"[CODE:{data.errorCode}][REPORT:{data.errorReport}]")
        self.log.error(data.trackeback)

    async def __aenter__(self):
        await self.csc.start_task
        await self.remote.start_task
        self.remote.evt_errorCode.callback = self.error_code_callback
        return self

    async def __aexit__(self, *args):
        await asyncio.sleep(STD_TIMEOUT)
        self.remote.evt_errorCode.callback = None
        await self.remote.close()
        await self.csc.close()


class TestATMonochromatorCSC(asynctest.TestCase):

    async def setUp(self):
        salobj.set_random_lsst_dds_domain()

    async def test_standard_state_transitions(self):
        """Test standard CSC state transitions.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * enterControl: OFFLINE to STANDBY
        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED to STANDBY
        * exitControl: STANDBY, FAULT to OFFLINE (quit)
        """

        async with Harness(initial_simulation_mode=1) as harness:

            commands = ("start", "enable", "disable", "exitControl", "standby",
                        "changeWavelength", "calibrateWavelength", "power", "selectGrating",
                        "changeSlitWidth", "updateMonochromatorSetup")

            # Check initial state
            with self.subTest(initial_state=salobj.State.STANDBY):
                current_state = await harness.remote.evt_summaryState.next(flush=False,
                                                                           timeout=STD_TIMEOUT)

                self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)
                self.assertEqual(current_state.summaryState, salobj.State.STANDBY)

            # Check that settingVersions was published
            with self.subTest(settingsVersions=True):
                try:
                    await harness.remote.evt_settingVersions.next(flush=False,
                                                                  timeout=STD_TIMEOUT)
                except asyncio.TimeoutError:
                    self.assertTrue(False, f"No settingVersions event.")

            for bad_command in commands:
                if bad_command in ("start", "exitControl"):
                    continue  # valid command in STANDBY state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(timeout=STD_TIMEOUT)

            # send start; new state is DISABLED
            with self.subTest(next_state=salobj.State.DISABLED):
                await harness.remote.cmd_start.start(timeout=LONG_LONG_TIMEOUT)
                state = await harness.remote.evt_summaryState.next(flush=False,
                                                                   timeout=STD_TIMEOUT)
                self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)
                self.assertEqual(state.summaryState, salobj.State.DISABLED)

            # check settings applied events
            simulation_mode_config = SimulationConfiguration()
            with self.subTest(settings_applied="settingsAppliedMonoCommunication"):
                sa = await harness.remote.evt_settingsAppliedMonoCommunication.next(
                    flush=False,
                    timeout=STD_TIMEOUT
                )
                self.assertEqual(sa.ip, simulation_mode_config.host)
                self.assertEqual(sa.portRange, simulation_mode_config.port)
                self.assertEqual(sa.connectionTimeout, simulation_mode_config.connection_timeout)
                self.assertEqual(sa.readTimeout, simulation_mode_config.read_timeout)
                self.assertEqual(sa.writeTimeout, simulation_mode_config.write_timeout)

            with self.subTest(settings_applied="settingsAppliedMonochromatorRanges"):
                sa = await harness.remote.evt_settingsAppliedMonochromatorRanges.next(
                    flush=False,
                    timeout=STD_TIMEOUT
                )
                self.assertEqual(sa.wavelengthGR1, simulation_mode_config.wavelength_gr1)
                self.assertEqual(sa.wavelengthGR1_GR2, simulation_mode_config.wavelength_gr1_gr2)
                self.assertEqual(sa.wavelengthGR2, simulation_mode_config.wavelength_gr2)
                self.assertEqual(sa.minSlitWidth, simulation_mode_config.min_slit_width)
                self.assertEqual(sa.maxSlitWidth, simulation_mode_config.max_slit_width)
                self.assertEqual(sa.minWavelength, simulation_mode_config.min_wavelength)
                self.assertEqual(sa.maxWavelength, simulation_mode_config.max_wavelength)

            with self.subTest(settings_applied="settingsAppliedMonoHeartbeat"):
                sa = await harness.remote.evt_settingsAppliedMonoHeartbeat.next(flush=False,
                                                                                timeout=STD_TIMEOUT)
                self.assertEqual(sa.period, simulation_mode_config.period)
                self.assertEqual(sa.timeout, simulation_mode_config.timeout)

            for bad_command in commands:
                if bad_command in ("enable", "standby"):
                    continue  # valid command in DISABLED state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(timeout=STD_TIMEOUT)

            # send enable; new state is ENABLED
            cmd_attr = getattr(harness.remote, f"cmd_enable")
            try:
                # enable may take some time to complete
                await cmd_attr.start(timeout=LONG_LONG_TIMEOUT)
            finally:
                state = await harness.remote.evt_summaryState.aget(timeout=STD_TIMEOUT)
            self.assertEqual(harness.csc.summary_state, salobj.State.ENABLED)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)

            # Check that expected events where published
            with self.subTest(expected_evt="status"):
                status = await harness.remote.evt_status.aget(timeout=STD_TIMEOUT)
                self.assertEqual(status.status, ATMonochromator.Status.READY)

            with self.subTest(expected_evt="wavelength"):
                wavelength = await harness.remote.evt_wavelength.aget(timeout=STD_TIMEOUT)
                self.assertEqual(wavelength.wavelength,
                                 harness.csc.mock_ctrl.wavelength)

            with self.subTest(expected_evt="grating"):
                grating = await harness.remote.evt_selectedGrating.aget(timeout=STD_TIMEOUT)

                self.assertEqual(grating.gratingType,
                                 harness.csc.mock_ctrl.grating)

            with self.subTest(expected_evt="entry slit width"):
                entrance_slit = await harness.remote.evt_entrySlitWidth.aget(timeout=STD_TIMEOUT)

                self.assertEqual(entrance_slit.width,
                                 harness.csc.mock_ctrl.entrance_slit_position)

                slit_width_1 = await harness.remote.evt_slitWidth.next(flush=False,
                                                                       timeout=STD_TIMEOUT)

                self.assertEqual(slit_width_1.slit,
                                 ATMonochromator.Slit.ENTRY)
                self.assertEqual(slit_width_1.slitPosition,
                                 entrance_slit.width)

            with self.subTest(expected_evt="exit slid width"):
                exit_slit = await harness.remote.evt_exitSlitWidth.aget(timeout=STD_TIMEOUT)

                self.assertEqual(exit_slit.width,
                                 harness.csc.mock_ctrl.exit_slit_position)

                slit_width_2 = await harness.remote.evt_slitWidth.next(flush=False,
                                                                       timeout=STD_TIMEOUT)

                self.assertEqual(slit_width_2.slit,
                                 ATMonochromator.Slit.EXIT)
                self.assertEqual(slit_width_2.slitPosition,
                                 exit_slit.width)

            for bad_command in commands:
                if bad_command in ("disable", "changeWavelength", "calibrateWavelength", "power",
                                   "selectGrating", "changeSlitWidth", "updateMonochromatorSetup"):
                    continue  # valid command in ENABLE state
                with self.subTest(bad_command=bad_command):
                    cmd_attr = getattr(harness.remote, f"cmd_{bad_command}")
                    with self.assertRaises(salobj.AckError):
                        await cmd_attr.start(timeout=STD_TIMEOUT)

            # send disable; new state is DISABLED
            cmd_attr = getattr(harness.remote, f"cmd_disable")
            # this CMD may take some time to complete
            await cmd_attr.start(timeout=LONG_LONG_TIMEOUT)
            state = await harness.remote.evt_summaryState.aget(timeout=STD_TIMEOUT)
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)
            self.assertEqual(salobj.State(state.summaryState),
                             salobj.State.DISABLED)

            # send standby; new state is STANDBY
            cmd_attr = getattr(harness.remote, f"cmd_standby")
            # this CMD may take some time to complete
            await cmd_attr.start(timeout=LONG_TIMEOUT)
            await asyncio.sleep(STD_TIMEOUT)
            state = await harness.remote.evt_summaryState.aget(timeout=STD_TIMEOUT)
            self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)
            self.assertEqual(salobj.State(state.summaryState),
                             salobj.State.STANDBY)

    async def test_config(self):
        """Test CSC configuration validator.
        """
        async with Harness(config_dir=TEST_CONFIG_DIR) as harness:
            self.assertEqual(harness.csc.summary_state, salobj.State.STANDBY)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=LONG_TIMEOUT)
            self.assertEqual(state.summaryState, salobj.State.STANDBY)

            invalid_files = glob.glob(os.path.join(TEST_CONFIG_DIR, "invalid_*.yaml"))
            bad_config_names = [os.path.basename(name) for name in invalid_files]
            bad_config_names.append("no_such_file.yaml")
            for bad_config_name in bad_config_names:
                with self.subTest(bad_config_name=bad_config_name):
                    harness.remote.cmd_start.set(settingsToApply=bad_config_name)
                    with salobj.test_utils.assertRaisesAckError():
                        await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)

            harness.remote.cmd_start.set(settingsToApply="all_fields")
            await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)
            self.assertEqual(harness.csc.summary_state, salobj.State.DISABLED)
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=STD_TIMEOUT)
            self.assertEqual(state.summaryState, salobj.State.DISABLED)


if __name__ == '__main__':
    unittest.main()

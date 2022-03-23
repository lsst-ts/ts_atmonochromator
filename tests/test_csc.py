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
import pathlib
import unittest
import typing

from lsst.ts import salobj

from lsst.ts import atmonochromator

from lsst.ts.idl.enums import ATMonochromator

TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

STD_TIMEOUT = 60
LONG_TIMEOUT = 120.0


class TestATMonochromatorCSC(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        salobj.set_random_lsst_dds_partition_prefix()

    def basic_make_csc(
        self,
        initial_state: typing.Union[salobj.sal_enums.State, int],
        config_dir: typing.Union[str, pathlib.Path, None],
        simulation_mode: int,
        override: str = "",
    ) -> salobj.base_csc.BaseCsc:
        return atmonochromator.MonochromatorCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            override=override,
            simulation_mode=simulation_mode,
        )

    async def test_basics(self) -> None:

        async with self.make_csc(initial_state=salobj.State.ENABLED, simulation_mode=1):

            # check settings applied events
            sim_config = atmonochromator.SimulationConfiguration()
            await self.assert_next_sample(
                topic=self.remote.evt_settingsAppliedMonoCommunication,
                ip=sim_config.host,
                portRange=sim_config.port,
                connectionTimeout=sim_config.connection_timeout,
                readTimeout=sim_config.read_timeout,
                writeTimeout=sim_config.write_timeout,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_settingsAppliedMonochromatorRanges,
                wavelengthGR1=sim_config.wavelength_gr1,
                wavelengthGR1_GR2=sim_config.wavelength_gr1_gr2,
                wavelengthGR2=sim_config.wavelength_gr2,
                minSlitWidth=sim_config.min_slit_width,
                maxSlitWidth=sim_config.max_slit_width,
                minWavelength=sim_config.min_wavelength,
                maxWavelength=sim_config.max_wavelength,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_settingsAppliedMonoHeartbeat,
                period=sim_config.period,
                timeout=sim_config.timeout,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_status, status=ATMonochromator.Status.READY
            )
            await self.assert_next_sample(
                topic=self.remote.evt_wavelength,
                wavelength=self.csc.mock_ctrl.wavelength,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_selectedGrating,
                gratingType=self.csc.mock_ctrl.grating,
            )
            entrance_slit = await self.assert_next_sample(
                topic=self.remote.evt_entrySlitWidth,
                width=self.csc.mock_ctrl.entrance_slit_position,
            )
            await self.assert_next_sample(
                topic=self.remote.evt_slitWidth,
                slit=ATMonochromator.Slit.ENTRY,
                slitPosition=entrance_slit.width,
            )

            exit_slit = await self.assert_next_sample(
                topic=self.remote.evt_exitSlitWidth,
                width=self.csc.mock_ctrl.exit_slit_position,
            )

            await self.assert_next_sample(
                topic=self.remote.evt_slitWidth,
                slit=ATMonochromator.Slit.EXIT,
                slitPosition=exit_slit.width,
            )

    async def test_bin_script(self) -> None:
        await self.check_bin_script(
            name="ATMonochromator", index=None, exe_name="atmonochromator_csc.py"
        )

    async def test_config(self) -> None:
        """Test MonochromatorCsc configuration validator."""
        async with self.make_csc(simulation_mode=1, config_dir=TEST_CONFIG_DIR):
            await self.assert_next_summary_state(salobj.State.STANDBY)

            invalid_files = glob.glob(os.path.join(TEST_CONFIG_DIR, "invalid_*.yaml"))
            bad_config_names = [os.path.basename(name) for name in invalid_files]
            bad_config_names.append("no_such_file.yaml")
            for bad_config_name in bad_config_names:
                with self.subTest(bad_config_name=bad_config_name):
                    with salobj.assertRaisesAckError():
                        await self.remote.cmd_start.set_start(
                            configurationOverride=bad_config_name, timeout=STD_TIMEOUT
                        )

    async def test_standard_state_transitions(self) -> None:
        """Test standard MonochromatorCsc state transitions.

        The initial state is STANDBY.
        The standard commands and associated state transitions are:

        * enterControl: OFFLINE to STANDBY
        * start: STANDBY to DISABLED
        * enable: DISABLED to ENABLED

        * disable: ENABLED to DISABLED
        * standby: DISABLED to STANDBY
        * exitControl: STANDBY, FAULT to OFFLINE (quit)
        """

        async with self.make_csc(simulation_mode=1):
            await self.check_standard_state_transitions(
                enabled_commands=(
                    "changeWavelength",
                    "calibrateWavelength",
                    "power",
                    "selectGrating",
                    "changeSlitWidth",
                    "updateMonochromatorSetup",
                )
            )

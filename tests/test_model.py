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

import asyncio
import itertools
import logging
import unittest

import numpy as np
from lsst.ts import atmonochromator
from lsst.ts.xml.enums.ATMonochromator import Status

# Standard timeout (seconds)
STD_TIMEOUT = 10


class ModelTestCase(unittest.IsolatedAsyncioTestCase):
    """Test Model"""

    async def asyncSetUp(self) -> None:
        self.model = atmonochromator.Model(logging.getLogger())
        self.server = atmonochromator.mock_controller.MockServer()

        self.host = self.server.host

        async with asyncio.timeout(STD_TIMEOUT):
            await self.server.start_task
            await self.model.connect(host=self.host, port=self.server.port)

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            async with asyncio.timeout(STD_TIMEOUT):
                await self.server.close()
                await self.model.disconnect()

    async def test_wavelength(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_wavelength()
        assert reply == self.server.device.wavelength

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.server.device.wavelength_range):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.server.device.wavelength

        # Test out of range
        current_wave = float(self.server.device.wavelength)

        for value in (
            self.server.device.wavelength_range[0] - 10.0,
            self.server.device.wavelength_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_wave == self.server.device.wavelength

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_wave == self.server.device.wavelength

    async def test_grating(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_grating()
        assert reply == self.server.device.grating

        # Test setting range of values from minimum to maximum...
        for value in self.server.device.grating_options:
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.server.device.grating

        # Test out of range
        current_grating = float(self.server.device.grating)

        min_grating = np.min(self.server.device.grating_options)
        max_grating = np.min(self.server.device.grating_options)
        for value in np.random.randint(min_grating - 10, max_grating + 10, 10):
            if value not in self.server.device.grating_options:
                with self.subTest(cmd=f"set_grating({value})"):
                    reply = await self.model.set_grating(value)
                    assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                    assert current_grating == self.server.device.grating

        # Test invalid
        for value in ("FoO", "bAr"):
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_grating == self.server.device.grating

    async def test_ens(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_entrance_slit()
        assert reply == self.server.device.entrance_slit_position

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.server.device.entrance_slit_range):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.server.device.entrance_slit_position

        # Test out of range
        current_ens = float(self.server.device.entrance_slit_position)

        for value in (
            self.server.device.entrance_slit_range[0] - 10.0,
            self.server.device.entrance_slit_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_ens == self.server.device.entrance_slit_position

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_ens == self.server.device.entrance_slit_position

    async def test_exs(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_exit_slit()
        assert reply == self.server.device.exit_slit_position

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.server.device.exit_slit_range):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.server.device.exit_slit_position

        # Test out of range
        current_ens = float(self.server.device.exit_slit_position)

        for value in (
            self.server.device.exit_slit_range[0] - 10.0,
            self.server.device.exit_slit_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_ens == self.server.device.exit_slit_position

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_ens == self.server.device.exit_slit_position

    async def test_set(self) -> None:

        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        wave_range = np.linspace(
            float(self.server.device.wavelength_range[0]),
            float(self.server.device.wavelength_range[1]),
            3,
        )
        grt_range = self.server.device.grating_options
        es_range = np.linspace(
            float(self.server.device.entrance_slit_range[0]),
            float(self.server.device.entrance_slit_range[1]),
            3,
        )
        ex_range = np.linspace(
            float(self.server.device.exit_slit_range[0]),
            float(self.server.device.exit_slit_range[1]),
            3,
        )

        for wave, gtr, es, ex in itertools.product(
            wave_range, grt_range, es_range, ex_range
        ):
            with self.subTest(cmd=f"set({wave},{gtr},{es},{ex})"):
                reply = await self.model.set_all(wave, gtr, es, ex)
                assert reply == atmonochromator.ModelReply.OK
                assert wave == self.server.device.wavelength
                assert gtr == self.server.device.grating
                assert es == self.server.device.entrance_slit_position
                assert ex == self.server.device.exit_slit_position

    async def test_status(self) -> None:

        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_status()
        assert reply == Status.READY

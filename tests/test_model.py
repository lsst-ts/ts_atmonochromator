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
from lsst.ts.idl.enums.ATMonochromator import Status

# Standard timeout (seconds)
STD_TIMEOUT = 10


class ModelTestCase(unittest.IsolatedAsyncioTestCase):
    """Test Model"""

    async def asyncSetUp(self) -> None:
        self.model = atmonochromator.Model(logging.getLogger())

        self.ctrl = atmonochromator.MockController()

        self.host = self.ctrl.config.host

        await asyncio.wait_for(self.ctrl.start(), timeout=STD_TIMEOUT)
        await self.model.connect(host=self.host, port=self.ctrl.port)

    async def asyncTearDown(self) -> None:
        if self.ctrl is not None:
            await asyncio.wait_for(self.ctrl.stop(), timeout=STD_TIMEOUT)
            await self.model.disconnect()

    async def test_wavelength(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_wavelength()
        assert reply == self.ctrl.wavelength

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.wavelength_range):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.ctrl.wavelength

        # Test out of range
        current_wave = float(self.ctrl.wavelength)

        for value in (
            self.ctrl.wavelength_range[0] - 10.0,
            self.ctrl.wavelength_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_wave == self.ctrl.wavelength

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_wave == self.ctrl.wavelength

    async def test_grating(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_grating()
        assert reply == self.ctrl.grating

        # Test setting range of values from minimum to maximum...
        for value in self.ctrl.grating_options:
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.ctrl.grating

        # Test out of range
        current_grating = float(self.ctrl.grating)

        min_grating = np.min(self.ctrl.grating_options)
        max_grating = np.min(self.ctrl.grating_options)
        for value in np.random.randint(min_grating - 10, max_grating + 10, 10):
            if value not in self.ctrl.grating_options:
                with self.subTest(cmd=f"set_grating({value})"):
                    reply = await self.model.set_grating(value)
                    assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                    assert current_grating == self.ctrl.grating

        # Test invalid
        for value in ("FoO", "bAr"):
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_grating == self.ctrl.grating

    async def test_ens(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_entrance_slit()
        assert reply == self.ctrl.entrance_slit_position

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.entrance_slit_range):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.ctrl.entrance_slit_position

        # Test out of range
        current_ens = float(self.ctrl.entrance_slit_position)

        for value in (
            self.ctrl.entrance_slit_range[0] - 10.0,
            self.ctrl.entrance_slit_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_ens == self.ctrl.entrance_slit_position

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_ens == self.ctrl.entrance_slit_position

    async def test_exs(self) -> None:
        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_exit_slit()
        assert reply == self.ctrl.exit_slit_position

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.exit_slit_range):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.OK
                assert value == self.ctrl.exit_slit_position

        # Test out of range
        current_ens = float(self.ctrl.exit_slit_position)

        for value in (
            self.ctrl.exit_slit_range[0] - 10.0,
            self.ctrl.exit_slit_range[1] + 10.0,
        ):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.OUT_OF_RANGE
                assert current_ens == self.ctrl.exit_slit_position

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                assert reply == atmonochromator.ModelReply.REJECTED
                assert current_ens == self.ctrl.exit_slit_position

    async def test_set(self) -> None:

        # setup controller
        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        wave_range = np.linspace(
            float(self.ctrl.wavelength_range[0]),
            float(self.ctrl.wavelength_range[1]),
            3,
        )
        grt_range = self.ctrl.grating_options
        es_range = np.linspace(
            float(self.ctrl.entrance_slit_range[0]),
            float(self.ctrl.entrance_slit_range[1]),
            3,
        )
        ex_range = np.linspace(
            float(self.ctrl.exit_slit_range[0]),
            float(self.ctrl.exit_slit_range[1]),
            3,
        )

        for wave, gtr, es, ex in itertools.product(
            wave_range, grt_range, es_range, ex_range
        ):
            with self.subTest(cmd=f"set({wave},{gtr},{es},{ex})"):
                reply = await self.model.set_all(wave, gtr, es, ex)
                assert reply == atmonochromator.ModelReply.OK
                assert wave == self.ctrl.wavelength
                assert gtr == self.ctrl.grating
                assert es == self.ctrl.entrance_slit_position
                assert ex == self.ctrl.exit_slit_position

    async def test_status(self) -> None:

        reply = await self.model.reset_controller()
        assert reply == atmonochromator.ModelReply.OK

        reply = await self.model.get_status()
        assert reply == Status.READY

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

import sys
import asyncio
import logging
import unittest
import asynctest

import numpy as np

from lsst.ts import salobj

from lsst.ts.monochromator import Model, ModelReply
from lsst.ts.monochromator import MockMonochromatorController

from lsst.ts.idl.enums.ATMonochromator import Status as MonochromatorStatus

logger = logging.getLogger()
logger.level = logging.DEBUG

port_generator = salobj.index_generator(imin=3200)


class ModelTestCase(asynctest.TestCase):
    """Test Model
    """
    async def setUp(self):
        self.model = Model(logger)

        self.ctrl = MockMonochromatorController()
        self.ctrl.config.port = next(port_generator)

        self.host = self.ctrl.config.host
        self.port = self.ctrl.config.port

        self.model.host = self.host
        self.model.port = self.port
        self.reader = None
        self.writer = None

        await asyncio.wait_for(self.ctrl.start(), 5)
        await self.model.connect()

    async def tearDown(self):
        if self.ctrl is not None:
            await asyncio.wait_for(self.ctrl.stop(), 5)
            await self.model.disconnect()
        if self.writer is not None:
            self.writer.close()

    async def test_wavelength(self):
        # setup controller
        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        with self.subTest(cmd="get_wavelength"):
            reply = await self.model.get_wavelength()
            self.assertEqual(reply, self.ctrl.wavelength)

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.wavelength_range):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                self.assertEqual(reply, ModelReply.OK)
                self.assertEqual(value, self.ctrl.wavelength)

        # Test out of range
        current_wave = float(self.ctrl.wavelength)

        for value in (self.ctrl.wavelength_range[0] - 10., self.ctrl.wavelength_range[1] + 10.):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                self.assertEqual(reply, ModelReply.OUT_OF_RANGE)
                self.assertEqual(current_wave, self.ctrl.wavelength)

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_wavelength({value})"):
                reply = await self.model.set_wavelength(value)
                self.assertEqual(reply, ModelReply.REJECTED)
                self.assertEqual(current_wave, self.ctrl.wavelength)

    async def test_grating(self):
        # setup controller
        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        with self.subTest(cmd="get_grating"):
            reply = await self.model.get_grating()
            self.assertEqual(reply, self.ctrl.grating)

        # Test setting range of values from minimum to maximum...
        for value in self.ctrl.grating_options:
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                self.assertEqual(reply, ModelReply.OK)
                self.assertEqual(value, self.ctrl.grating)

        # Test out of range
        current_grating = float(self.ctrl.grating)

        min_grating = np.min(self.ctrl.grating_options)
        max_grating = np.min(self.ctrl.grating_options)
        for value in np.random.randint(min_grating - 10, max_grating + 10, 10):
            if value not in self.ctrl.grating_options:
                with self.subTest(cmd=f"set_grating({value})"):
                    reply = await self.model.set_grating(value)
                    self.assertEqual(reply, ModelReply.OUT_OF_RANGE)
                    self.assertEqual(current_grating, self.ctrl.grating)

        # Test invalid
        for value in ("FoO", "bAr"):
            with self.subTest(cmd=f"set_grating({value})"):
                reply = await self.model.set_grating(value)
                self.assertEqual(reply, ModelReply.REJECTED)
                self.assertEqual(current_grating, self.ctrl.grating)

    async def test_ens(self):
        # setup controller
        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        with self.subTest(cmd="get_entrance_slit"):
            reply = await self.model.get_entrance_slit()
            self.assertEqual(reply, self.ctrl.entrance_slit_position)

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.entrance_slit_range):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                self.assertEqual(reply, ModelReply.OK)
                self.assertEqual(value, self.ctrl.entrance_slit_position)

        # Test out of range
        current_ens = float(self.ctrl.entrance_slit_position)

        for value in (self.ctrl.entrance_slit_range[0] - 10.,
                      self.ctrl.entrance_slit_range[1] + 10.):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                self.assertEqual(reply, ModelReply.OUT_OF_RANGE)
                self.assertEqual(current_ens, self.ctrl.entrance_slit_position)

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_entrance_slit({value})"):
                reply = await self.model.set_entrance_slit(value)
                self.assertEqual(reply, ModelReply.REJECTED)
                self.assertEqual(current_ens, self.ctrl.entrance_slit_position)

    async def test_exs(self):
        # setup controller
        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        with self.subTest(cmd="get_exit_slit"):
            reply = await self.model.get_exit_slit()
            self.assertEqual(reply, self.ctrl.exit_slit_position)

        # Test setting range of values from minimum to maximum...
        for value in np.linspace(*self.ctrl.exit_slit_range):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                self.assertEqual(reply, ModelReply.OK)
                self.assertEqual(value, self.ctrl.exit_slit_position)

        # Test out of range
        current_ens = float(self.ctrl.exit_slit_position)

        for value in (self.ctrl.exit_slit_range[0] - 10., self.ctrl.exit_slit_range[1] + 10.):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                self.assertEqual(reply, ModelReply.OUT_OF_RANGE)
                self.assertEqual(current_ens, self.ctrl.exit_slit_position)

        # Test invalid
        for value in ("FOO", "bAr"):
            with self.subTest(cmd=f"set_exit_slit({value})"):
                reply = await self.model.set_exit_slit(value)
                self.assertEqual(reply, ModelReply.REJECTED)
                self.assertEqual(current_ens, self.ctrl.exit_slit_position)

    async def test_set(self):

        # setup controller
        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        wave_range = np.linspace(*self.ctrl.wavelength_range, 3)
        grt_range = self.ctrl.grating_options
        es_range = np.linspace(*self.ctrl.entrance_slit_range, 3)
        ex_range = np.linspace(*self.ctrl.exit_slit_range, 3)

        for wave in wave_range:
            for gtr in grt_range:
                for es in es_range:
                    for ex in ex_range:
                        with self.subTest(cmd=f"set({wave},{gtr},{es},{ex})"):
                            reply = await self.model.set_all(wave, gtr, es, ex)
                            self.assertEqual(reply, ModelReply.OK)
                            self.assertEqual(wave, self.ctrl.wavelength)
                            self.assertEqual(gtr, self.ctrl.grating)
                            self.assertEqual(es, self.ctrl.entrance_slit_position)
                            self.assertEqual(ex, self.ctrl.exit_slit_position)

    async def test_status(self):

        with self.subTest(cmd="setup"):
            reply = await self.model.reset_controller()
            self.assertEqual(reply, ModelReply.OK)

        with self.subTest(cmd="get_status"):
            reply = await self.model.get_status()
            self.assertEqual(reply, MonochromatorStatus.READY)


if __name__ == "__main__":

    stream_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(stream_handler)

    unittest.main()

# This file is part of ts_pymonochromator.
#
# Developed for the LSST Data Management System.
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
import unittest
import logging
import numpy as np

from lsst.ts import salobj
from lsst.ts.monochromator import MockMonochromatorController

logger = logging.getLogger()
logger.level = logging.DEBUG

port_generator = salobj.index_generator(imin=3100)


class MockTestCase(unittest.TestCase):
    """Test MockMonochromatorController
    """
    def setUp(self):
        self.port = next(port_generator)
        self.writer = None

        async def doit():
            self.ctrl = MockMonochromatorController(port=self.port)
            await asyncio.wait_for(self.ctrl.start(), 5)
            rw_coro = asyncio.open_connection(host="127.0.0.1", port=self.port)
            self.reader, self.writer = await asyncio.wait_for(rw_coro, timeout=10)

        asyncio.get_event_loop().run_until_complete(doit())

    def tearDown(self):
        async def doit():
            if self.ctrl:
                await asyncio.wait_for(self.ctrl.stop(), 5)
            if self.writer:
                self.writer.close()

        asyncio.get_event_loop().run_until_complete(doit())

    async def send_cmd(self, cmd, timeout=2):
        """Send a command to the mock controller and wait for the reply.

        Return the decoded reply as 0 or more lines of text
        with the final ">" stripped.
        """
        self.writer.write(f"{cmd}\n".encode())
        await self.writer.drain()
        read_bytes = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
        return read_bytes.decode().strip()

    def test_wl(self):
        async def doit():

            # setup controller
            with self.subTest(cmd="!RST"):
                reply_lines = await self.send_cmd("!RST 1\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

            with self.subTest(cmd="?WL"):
                reply_lines = await self.send_cmd("?WL\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#WL")
                self.assertEqual(status[1], f"{self.ctrl.wavelength}")

            # Test minimum value
            with self.subTest(cmd=f"!WL {self.ctrl.wavelength_range[0]}"):
                reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[0]}\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

                reply_lines = await self.send_cmd("?WL\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#WL")
                self.assertEqual(status[1], f"{self.ctrl.wavelength_range[0]}")

            # Test maximum value
            with self.subTest(cmd=f"!WL {self.ctrl.wavelength_range[1]}"):
                reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[1]}\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

                reply_lines = await self.send_cmd("?WL\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#WL")
                self.assertEqual(status[1], f"{self.ctrl.wavelength_range[1]}")

            # Test out of range

            current_wave = float(self.ctrl.wavelength)

            with self.subTest(cmd=f"!WL {self.ctrl.wavelength_range[0]-10.}"):

                # Test below minimum value
                reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[0]-10.}\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.our)
                self.assertEqual(current_wave, self.ctrl.wavelength)

            with self.subTest(cmd=f"!WL {self.ctrl.wavelength_range[1]+10.}"):

                # Test above maximum value
                reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[1]+10.}\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.our)
                self.assertEqual(current_wave, self.ctrl.wavelength)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_gr(self):
        async def doit():

            with self.subTest(cmd="!RST"):
                # setup controller
                reply_lines = await self.send_cmd("!RST 1\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

            with self.subTest(cmd="?GR"):
                reply_lines = await self.send_cmd("?GR\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#GR")
                self.assertEqual(status[1], f"{self.ctrl.grating}")

            # Test each valid value
            for value in self.ctrl.grating_options:
                with self.subTest(cmd=f"!GR {value}"):
                    reply_lines = await self.send_cmd(f"!GR {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.ok)
                    self.assertEqual(value, self.ctrl.grating)

            # Test out of range
            current_value = int(self.ctrl.grating)

            for value in (-1, 10, "FOO"):
                with self.subTest(cmd=f"!GR {value}"):
                    reply_lines = await self.send_cmd(f"!GR {value}\r\n")
                    status = reply_lines.split()
                    self.assertNotEqual(status[0], self.ctrl.ok)
                    self.assertEqual(current_value, self.ctrl.grating)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_ens(self):
        async def doit():

            with self.subTest(cmd="!RST"):
                # setup controller
                reply_lines = await self.send_cmd("!RST 1\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

            with self.subTest(cmd="?ENS"):
                reply_lines = await self.send_cmd("?ENS\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#ENS")
                self.assertEqual(status[1], f"{self.ctrl.entrance_slit_position}")

            # Test range of valid values
            for value in np.linspace(*self.ctrl.entrance_slit_range):
                with self.subTest(cmd=f"!ENS {value}"):
                    reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.ok)
                    self.assertEqual(value, self.ctrl.entrance_slit_position)

            current_value = self.ctrl.entrance_slit_position

            # Test out of range values
            for value in (self.ctrl.entrance_slit_range[0]-10, self.ctrl.entrance_slit_range[1]+10):
                with self.subTest(cmd=f"!ENS {value}"):
                    reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.our)
                    self.assertEqual(current_value, self.ctrl.entrance_slit_position)

            # Test invalid values
            for value in ("FOO", "bar"):
                with self.subTest(cmd=f"!ENS {value}"):
                    reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.rejected)
                    self.assertEqual(current_value, self.ctrl.entrance_slit_position)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_exs(self):
        async def doit():

            with self.subTest(cmd="!RST"):
                # setup controller
                reply_lines = await self.send_cmd("!RST 1\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

            with self.subTest(cmd="?EXS"):
                reply_lines = await self.send_cmd("?EXS\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], "#EXS")
                self.assertEqual(status[1], f"{self.ctrl.exit_slit_position}")

            # Test range of valid values
            for value in np.linspace(*self.ctrl.exit_slit_range):
                with self.subTest(cmd=f"!EXS {value}"):
                    reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.ok)
                    self.assertEqual(value, self.ctrl.exit_slit_position)

            current_value = self.ctrl.exit_slit_position

            # Test out of range values
            for value in (self.ctrl.exit_slit_range[0]-10, self.ctrl.exit_slit_range[1]+10):
                with self.subTest(cmd=f"!EXS {value}"):
                    reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.our)
                    self.assertEqual(current_value, self.ctrl.exit_slit_position)

            # Test invalid values
            for value in ("FOO", "bar"):
                with self.subTest(cmd=f"!EXS {value}"):
                    reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                    status = reply_lines.split()
                    self.assertEqual(status[0], self.ctrl.rejected)
                    self.assertEqual(current_value, self.ctrl.exit_slit_position)

        asyncio.get_event_loop().run_until_complete(doit())

    def test_set(self):
        async def doit():

            with self.subTest(cmd="!RST"):
                # setup controller
                reply_lines = await self.send_cmd("!RST 1\r\n")
                status = reply_lines.split()
                self.assertEqual(status[0], self.ctrl.ok)

            max_w = self.ctrl.wavelength_range[1]
            min_w = self.ctrl.wavelength_range[0]
            wavelength = np.random.random()*(max_w-min_w)+min_w
            grating = np.random.randint(self.ctrl.grating_options[0],
                                        self.ctrl.grating_options[-1])

            max_f = self.ctrl.entrance_slit_range[1]
            min_f = self.ctrl.entrance_slit_range[0]

            front_slit = np.random.random()*(max_f-min_f)+min_f

            max_e = self.ctrl.exit_slit_range[1]
            min_e = self.ctrl.exit_slit_range[0]
            exit_slit = np.random.random()*(max_e-min_e)+min_e

            reply_lines = await self.send_cmd(f"!SET {wavelength} {grating} {front_slit} {exit_slit}\r\n")
            status = reply_lines.split()
            self.assertEqual(status[0], self.ctrl.ok)
            self.assertEqual(wavelength, self.ctrl.wavelength)
            self.assertEqual(grating, self.ctrl.grating)
            self.assertEqual(front_slit, self.ctrl.entrance_slit_position)
            self.assertEqual(exit_slit, self.ctrl.exit_slit_position)

        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":

    stream_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(stream_handler)

    unittest.main()

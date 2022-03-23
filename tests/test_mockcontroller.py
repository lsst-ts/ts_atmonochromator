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
import typing
import unittest

import numpy as np

from lsst.ts import atmonochromator

# Standard timeout (seconds)
STD_TIMEOUT = 10


class MockTestCase(unittest.IsolatedAsyncioTestCase):
    """Test MockController"""

    async def asyncSetUp(self) -> None:
        self.ctrl = atmonochromator.MockController()

        await asyncio.wait_for(self.ctrl.start(), timeout=STD_TIMEOUT)
        rw_coro = asyncio.open_connection(
            host=self.ctrl.config.host, port=self.ctrl.port
        )
        self.reader, self.writer = await asyncio.wait_for(rw_coro, timeout=STD_TIMEOUT)

    async def asyncTearDown(self) -> None:
        if self.ctrl is not None:
            await asyncio.wait_for(self.ctrl.stop(), timeout=STD_TIMEOUT)
        if self.writer is not None:
            self.writer.write_eof()
            await self.writer.drain()
            self.writer.close()

    async def send_cmd(
        self, cmd: str, timeout: typing.Union[int, float] = STD_TIMEOUT
    ) -> str:
        """Send a command to the mock controller and wait for the reply.

        Return the decoded reply as 0 or more lines of text
        with the final ">" stripped.
        """
        self.writer.write(f"{cmd}\n".encode())
        await self.writer.drain()
        read_bytes = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
        return read_bytes.decode().strip()

    async def test_wl(self) -> None:
        # setup controller
        reply_lines = await self.send_cmd("!RST 1\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?WL\r\n")
        status = reply_lines.split()
        assert status[0] == "#WL"
        assert status[1] == f"{self.ctrl.wavelength}"

        # Test minimum value
        reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[0]}\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?WL\r\n")
        status = reply_lines.split()
        assert status[0] == "#WL"
        assert status[1] == f"{self.ctrl.wavelength_range[0]}"

        # Test maximum value
        reply_lines = await self.send_cmd(f"!WL {self.ctrl.wavelength_range[1]}\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?WL\r\n")
        status = reply_lines.split()
        assert status[0] == "#WL"
        assert status[1] == f"{self.ctrl.wavelength_range[1]}"

        # Test out of range

        current_wave = float(self.ctrl.wavelength)

        # Test below minimum value
        reply_lines = await self.send_cmd(
            f"!WL {self.ctrl.wavelength_range[0]-10.}\r\n"
        )
        status = reply_lines.split()
        assert status[0] == self.ctrl.our
        assert current_wave == self.ctrl.wavelength

        # Test above maximum value
        reply_lines = await self.send_cmd(
            f"!WL {self.ctrl.wavelength_range[1]+10.}\r\n"
        )
        status = reply_lines.split()
        assert status[0] == self.ctrl.our
        assert current_wave == self.ctrl.wavelength

    async def test_gr(self) -> None:
        # setup controller
        reply_lines = await self.send_cmd("!RST 1\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?GR\r\n")
        status = reply_lines.split()
        assert status[0] == "#GR"
        assert status[1] == f"{self.ctrl.grating}"

        # Test each valid value
        for value in self.ctrl.grating_options:
            with self.subTest(cmd=f"!GR {value}"):
                reply_lines = await self.send_cmd(f"!GR {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.ok
                assert value == self.ctrl.grating

        # Test out of range
        current_value = int(self.ctrl.grating)

        for value in (-1, 10, "FOO"):
            with self.subTest(cmd=f"!GR {value}"):
                reply_lines = await self.send_cmd(f"!GR {value}\r\n")
                status = reply_lines.split()
                assert status[0] != self.ctrl.ok
                assert current_value == self.ctrl.grating

    async def test_ens(self) -> None:
        # setup controller
        reply_lines = await self.send_cmd("!RST 1\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?ENS\r\n")
        status = reply_lines.split()
        assert status[0] == "#ENS"
        assert status[1] == f"{self.ctrl.entrance_slit_position}"

        # Test range of valid values
        for value in np.linspace(*self.ctrl.entrance_slit_range):
            with self.subTest(cmd=f"!ENS {value}"):
                reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.ok
                assert value == self.ctrl.entrance_slit_position

        current_value = self.ctrl.entrance_slit_position

        # Test out of range values
        for value in (
            self.ctrl.entrance_slit_range[0] - 10,
            self.ctrl.entrance_slit_range[1] + 10,
        ):
            with self.subTest(cmd=f"!ENS {value}"):
                reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.our
                assert current_value == self.ctrl.entrance_slit_position

        # Test invalid values
        for value in ("FOO", "bar"):
            with self.subTest(cmd=f"!ENS {value}"):
                reply_lines = await self.send_cmd(f"!ENS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.rejected
                assert current_value == self.ctrl.entrance_slit_position

    async def test_exs(self) -> None:
        # setup controller
        reply_lines = await self.send_cmd("!RST 1\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        reply_lines = await self.send_cmd("?EXS\r\n")
        status = reply_lines.split()
        assert status[0] == "#EXS"
        assert status[1] == f"{self.ctrl.exit_slit_position}"

        # Test range of valid values
        for value in np.linspace(*self.ctrl.exit_slit_range):
            with self.subTest(cmd=f"!EXS {value}"):
                reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.ok
                assert value == self.ctrl.exit_slit_position

        current_value = self.ctrl.exit_slit_position

        # Test out of range values
        for value in (
            self.ctrl.exit_slit_range[0] - 10,
            self.ctrl.exit_slit_range[1] + 10,
        ):
            with self.subTest(cmd=f"!EXS {value}"):
                reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.our
                assert current_value == self.ctrl.exit_slit_position

        # Test invalid values
        for value in ("FOO", "bar"):
            with self.subTest(cmd=f"!EXS {value}"):
                reply_lines = await self.send_cmd(f"!EXS {value}\r\n")
                status = reply_lines.split()
                assert status[0] == self.ctrl.rejected
                assert current_value == self.ctrl.exit_slit_position

    async def test_set(self) -> None:
        # setup controller
        reply_lines = await self.send_cmd("!RST 1\r\n")
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok

        max_w = self.ctrl.wavelength_range[1]
        min_w = self.ctrl.wavelength_range[0]
        wavelength = np.random.random() * (max_w - min_w) + min_w
        grating = np.random.randint(
            self.ctrl.grating_options[0], self.ctrl.grating_options[-1]
        )

        max_f = self.ctrl.entrance_slit_range[1]
        min_f = self.ctrl.entrance_slit_range[0]

        front_slit = np.random.random() * (max_f - min_f) + min_f

        max_e = self.ctrl.exit_slit_range[1]
        min_e = self.ctrl.exit_slit_range[0]
        exit_slit = np.random.random() * (max_e - min_e) + min_e

        reply_lines = await self.send_cmd(
            f"!SET {wavelength} " f"{grating} " f"{front_slit} " f"{exit_slit}\r\n"
        )
        status = reply_lines.split()
        assert status[0] == self.ctrl.ok
        assert wavelength == self.ctrl.wavelength
        assert grating == self.ctrl.grating
        assert front_slit == self.ctrl.entrance_slit_position
        assert exit_slit == self.ctrl.exit_slit_position

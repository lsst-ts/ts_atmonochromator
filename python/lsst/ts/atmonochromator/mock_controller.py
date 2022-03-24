__all__ = ["MockController", "SimulationConfiguration"]

import asyncio
import logging
import typing

from lsst.ts.idl.enums.ATMonochromator import Status as MonochromatorStatus


class SimulationConfiguration:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 0
        self.connection_timeout = 10.0
        self.read_timeout = 10.0
        self.write_timeout = 10.0
        self.wavelength_gr1 = 320.0
        self.wavelength_gr1_gr2 = 800.0
        self.wavelength_gr2 = 1130.0
        self.min_slit_width = 0.0
        self.max_slit_width = 7.0
        self.min_wavelength = 320.0
        self.max_wavelength = 1130.0
        self.period = 1.0
        self.timeout = 5.0


class MockController:
    """Mock Monochromator low-level controller that talks over TCP/IP.

    The Monochromator TCP Protocol is specified here:
    https://confluence.lsstcorp.org/display/LTS/Monochromator+TCP+Protocol
    """

    def __init__(self) -> None:
        self.config = SimulationConfiguration()

        self.log = logging.getLogger("MockController")

        self.server: typing.Optional[asyncio.base_events.Server] = None

        self.wait_time = 0.1

        # Status of the monochromator controller.
        self.status = MonochromatorStatus.OFFLINE

        self.controller_busy = False

        self.wavelength = 320.0
        self.wavelength_offset = 0.0

        self.grating_options = (0, 1, 2)
        self.grating = 0

        self.entrance_slit_position = 0.0

        self.exit_slit_position = 0.0

        self._cmds = {
            "!WL": self.set_wl,
            "!GR": self.set_gr,
            "!ENS": self.set_ens,
            "!EXS": self.set_exs,
            "!CLW": self.set_clw,
            "!RST": self.set_rst,
            "!SET": self.set_set,
            "?WL": self.get_wl,
            "?GR": self.get_gr,
            "?ENS": self.get_ens,
            "?EXS": self.get_exs,
            "?SWST": self.get_swst,
        }

    @property
    def exit_slit_range(self) -> typing.Tuple[float, float]:
        return self.config.min_slit_width, self.config.max_slit_width

    @property
    def entrance_slit_range(self) -> typing.Tuple[float, float]:
        return self.config.min_slit_width, self.config.max_slit_width

    @property
    def wavelength_range(self) -> typing.Tuple[float, float]:
        return self.config.min_wavelength, self.config.min_wavelength

    @property
    def ok(self) -> str:
        return "#OK"  # Accepted command

    @property
    def our(self) -> str:
        return "#OUR"  # Out of range

    @property
    def invalid(self) -> str:
        return "??"  # Invalid command

    @property
    def busy(self) -> str:
        return "#BUSY"  # Device busy executing another command

    @property
    def rejected(self) -> str:
        return "#RJCT"  # Rejected

    async def start(self) -> None:
        """Start the TCP/IP server, set start_task Done
        and start the command loop.
        """
        self.status = MonochromatorStatus.SETTING_UP
        self.server = await asyncio.start_server(
            self.cmd_loop, host=self.config.host, port=0
        )
        num_sockets = len(self.server.sockets)
        if num_sockets != 1:
            raise RuntimeError(
                "Listening on more than one socket; cannot determine port"
            )
        self.port = self.server.sockets[0].getsockname()[1]
        self.log.info(
            f"MockController server running: host={self.config.host}; port={self.port}"
        )
        self.status = MonochromatorStatus.READY

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the TCP/IP server."""
        if self.server is None:
            return

        server = self.server
        self.server = None
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=timeout)
        MonochromatorStatus.OFFLINE

    async def cmd_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Execute the server control loop.

        Parameters
        ----------
        reader : asyncio.StreamReader
            Server stream reader.
        writer : asyncio.StreamWrite
            Server stream writer.
        """
        self.log.info("cmd_loop begins")

        while True:
            _line = (await reader.readline()).decode()
            if not _line:
                # connection lost; close the writer and exit the loop
                writer.close()
                return
            self.log.debug(f"read command: {_line!r}")

            line = _line.strip().split()
            if line:
                try:
                    if len(line) > 0 and line[0] in self._cmds:
                        reply = await self._cmds[line[0]](line[1:])
                        self.log.debug(f"reply: {reply!r}")
                        writer.write(f"{reply}\r\n".encode())
                        await writer.drain()
                    else:
                        writer.write("??\r\n".encode())
                        await writer.drain()
                except Exception:
                    writer.write("??\r\n".encode())
                    await writer.drain()
                    self.log.exception(f"command {line} failed")
                await writer.drain()

    async def set_wl(self, args: typing.List[str]) -> str:
        """Set wavelength, range.

        Parameters
        ----------
        args : str
            A string of number that can be converted to a float.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected

        """
        if self.status != MonochromatorStatus.READY:
            return self.rejected
        elif self.controller_busy:
            return self.busy

        try:
            new_wl = float(args[0])
        except Exception:
            return self.rejected

        if not (self.wavelength_range[0] <= new_wl <= self.wavelength_range[1]):
            return self.our

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.wavelength = new_wl + self.wavelength_offset

        # Make sure offset does not take values out of range
        if self.wavelength > self.wavelength_range[1]:
            self.wavelength = self.wavelength_range[1]

        elif self.wavelength < self.wavelength_range[0]:
            self.wavelength = self.wavelength_range[0]

        return self.ok

    async def set_gr(self, args: typing.List[str]) -> str:
        """Select grating.

        Parameters
        ----------
        args : str
            A string of number that can be converted to an int.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected


        """
        if self.status != MonochromatorStatus.READY:
            return self.rejected
        elif self.controller_busy:
            return self.busy

        try:
            new_gr = int(args[0])
        except Exception:
            return self.rejected

        if new_gr not in self.grating_options:
            return self.our

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.grating = new_gr

        return self.ok

    async def set_ens(self, args: typing.List[str]) -> str:
        """Select entrance slit width.

        Parameters
        ----------
        args : str
            A string of number that can be converted to a float.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected

        """
        if self.status != MonochromatorStatus.READY:
            return self.rejected
        elif self.controller_busy:
            return self.busy

        try:
            new_ens = float(args[0])
        except Exception:
            return self.rejected

        if not (self.entrance_slit_range[0] <= new_ens <= self.entrance_slit_range[1]):
            return self.our

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.entrance_slit_position = new_ens

        return self.ok

    async def set_exs(self, args: typing.List[str]) -> str:
        """Select exit slit width.

        Parameters
        ----------
        args : str
            A string of number that can be converted to a float.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected

        """
        if self.status != MonochromatorStatus.READY:
            return self.rejected
        elif self.controller_busy:
            return self.busy

        try:
            new_exs = float(args[0])
        except Exception:
            return self.rejected

        if not (self.exit_slit_range[0] <= new_exs <= self.exit_slit_range[1]):
            return self.our

        # Give control back to event loop for responsiveness and to
        # simulate action
        await asyncio.sleep(self.wait_time)

        self.exit_slit_position = new_exs

        return self.ok

    async def set_clw(self, args: typing.List[str]) -> str:
        """Calibrate the wavelength with the current value.

        Set the value for wavelength offset.

        Parameters
        ----------
        args : str
            A string of number that can be converted to a float.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected
        """

        if self.status != MonochromatorStatus.READY:
            return self.rejected
        elif self.controller_busy:
            return self.busy

        try:
            new_offset = float(args[0])
        except Exception:
            return self.rejected

        exit_0 = self.exit_slit_range[0]
        exit_1 = self.exit_slit_range[1]
        new_w = self.wavelength + new_offset

        if not (exit_0 <= new_w <= exit_1):
            return self.our

        self.wavelength_offset = new_offset

        return self.ok

    async def set_rst(self, args: typing.List[str]) -> str:
        """Reset device and go to initial state.


        Parameters
        ----------
        args : str
            A string of number that can be converted to an int. Must be equal
            to 1 or it will be rejected.

        Returns
        -------
        result : str
            Response to the set command:
                #OK - Accepted command
                #OUR - Out of range
                ?? - Invalid command
                #BUSY - Device busy executing another command
                #RJCT - Rejected

        """

        if self.controller_busy:
            return self.busy

        try:
            value = int(args[0])
        except Exception as e:
            self.log.exception(e)
            return self.rejected

        if value != 1:
            return self.rejected

        self.log.debug("Starting rst")
        self.status = MonochromatorStatus.SETTING_UP

        await asyncio.sleep(self.wait_time)

        # reset values
        self.log.debug("Resetting wavelength")
        self.wavelength_offset = 0.0
        self.wavelength = self.wavelength_range[0]
        await asyncio.sleep(self.wait_time)
        self.log.debug("Resetting entrance slit")
        self.entrance_slit_position = self.entrance_slit_range[0]
        await asyncio.sleep(self.wait_time)
        self.log.debug("Resetting exit slit")
        self.exit_slit_position = self.exit_slit_range[0]
        await asyncio.sleep(self.wait_time)
        self.log.debug("Resetting grating")
        self.grating = self.grating_options[0]
        await asyncio.sleep(self.wait_time)

        self.status = MonochromatorStatus.READY

        self.log.debug("Done rst")
        return self.ok

    async def set_set(self, args: typing.List[str]) -> str:
        """Set all parameters.

        Parameters
        ----------
        args : list(str)
            A list with the following values:

            * wavelength, in nm
            * grating name
            * front entrance slit width, in mm
            * front exit slit width, im mm

        Returns
        -------
        result : str
            Response to the set command; one of:

            * #OK - Accepted command
            * #OUR - Out of range
            * ?? - Invalid command
            * #BUSY - Device busy executing another command
            * #RJCT - Rejected
        """
        if len(args) != 4:
            return self.rejected

        try:
            retval = await self.set_wl(args)
            if retval != self.ok:
                return retval

            retval = await self.set_gr(args[1:])
            if retval != self.ok:
                return retval

            retval = await self.set_ens(args[2:])
            if retval != self.ok:
                return retval

            retval = await self.set_exs(args[3:])
            if retval != self.ok:
                return retval

        except Exception:

            return self.rejected
        else:
            return self.ok

    async def get_wl(self, args: typing.List[str]) -> str:
        """Return parsed string with current wavelength.

        Parameters
        ----------
        args :
            Not used.

        Returns
        -------
        retval : str
            A string consisting of "#WL {wavelength}"

        """
        return f"#WL {self.wavelength+self.wavelength_offset}"

    async def get_gr(self, args: typing.List[str]) -> str:
        """Return parsed string with current grating.

        Parameters
        ----------
        args :
            Not used.

        Returns
        -------
        retval : str
            A string consisting of "#WL {grating}
        """
        return f"#GR {self.grating}"

    async def get_ens(self, args: typing.List[str]) -> str:
        """Return parsed string with current entrance slit position.

        Parameters
        ----------
        args :
            Not used.

        Returns
        -------
        retval : str
            A string consisting of "#WL {ens}
        """
        return f"#ENS {self.entrance_slit_position}"

    async def get_exs(self, args: typing.List[str]) -> str:
        """Return parsed string with current exit slit position.

        Parameters
        ----------
        args :
            Not used.

        Returns
        -------
        retval : str
            A string consisting of "#EXS {exs}
        """
        return f"#EXS {self.exit_slit_position}"

    async def get_swst(self, args: typing.List[str]) -> str:
        """Query Software status

        Parameters
        ----------
        args :
            Not used.

        Returns
        -------
        retval : str
            A string consisting of "#SWST {status}
        """
        return f"#SWST {int(self.status)}"

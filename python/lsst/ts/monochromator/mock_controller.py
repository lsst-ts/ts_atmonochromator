__all__ = ["MockMonochromatorController"]

import asyncio
import logging

from .model import MonochromatorStatus


class MockMonochromatorController:
    """Mock Monochromator Controller that talks over TCP/IP.

    The Monochromator TCP Protocol is specified here:
    https://confluence.lsstcorp.org/display/LTS/Monochromator+TCP+Protocol

    Parameters
    ----------
    port : int
        TCP/IP port

    """

    def __init__(self, port):
        self.port = port

        self.log = logging.getLogger("MockMonochromatorController")

        self._server = None

        self.wait_time = .1

        self.status = MonochromatorStatus.OFFLINE
        """Status of the monochromator controller.
        Must be one of:
            0 for SettingUp, 1 for Ready, 2 for Offline, 3 for Fault.
        """

        self.controller_busy = False

        self.wavelength_range = (320., 1130.)  # wavelength range in nm
        self.wavelength = 320.
        self.wavelength_offset = 0.

        self.grating_options = (0, 1, 2)
        self.grating = 0

        self.entrance_slit_range = (0., 7.)  # entrance slit range in mm
        self.entrance_slit_position = 0.

        self.exit_slit_range = (0., 7.)  # entrance slit range in mm
        self.exit_slit_position = 0.

        # responses to commands:
        self.ok = "#OK"  # Accepted command
        self.our = "#OUR"  # Out of range
        self.invalid = "??"  # Invalid command
        self.busy = "#BUSY"  # Device busy executing another command
        self.rejected = "#RJCT"  # Rejected

        self._cmds = {"!WL": self.set_wl,
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

    async def start(self):
        """Start the TCP/IP server, set start_task Done
        and start the command loop.
        """
        self._server = await asyncio.start_server(self.cmd_loop,
                                                  host="127.0.0.1",
                                                  port=self.port)

    async def stop(self, timeout=5):
        """Stop the TCP/IP server.
        """
        if self._server is None:
            return

        server = self._server
        self._server = None
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=timeout)

    async def cmd_loop(self, reader, writer):
        self.log.info("cmd_loop begins")

        while True:
            # Write string specifing that server is ready
            line = await reader.readline()
            line = line.decode()
            if not line:
                # connection lost; close the writer and exit the loop
                writer.close()
                return
            line = line.strip().split()
            self.log.debug(f"read command: {line!r}")
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

    async def set_wl(self, args):
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

        self.busy = True

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.wavelength = new_wl + self.wavelength_offset

        # Make sure offset does not take values out of range
        if self.wavelength > self.wavelength_range[1]:
            self.wavelength = self.wavelength_range[1]

        elif self.wavelength < self.wavelength_range[0]:
            self.wavelength = self.wavelength_range[0]

        self.busy = False

        return self.ok

    async def set_gr(self, args):
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

        self.busy = True

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.grating = new_gr

        self.busy = False

        return self.ok

    async def set_ens(self, args):
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

        self.busy = True

        # Give control back to event loop for responsiveness and to simulate
        # action
        await asyncio.sleep(self.wait_time)

        self.entrance_slit_position = new_ens

        self.busy = False

        return self.ok

    async def set_exs(self, args):
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

        self.busy = True

        # Give control back to event loop for responsiveness and to
        # simulate action
        await asyncio.sleep(self.wait_time)

        self.exit_slit_position = new_exs

        self.busy = False

        return self.ok

    async def set_clw(self, args):
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

        exit_0 = self.exit_slit_position[0]
        exit_1 = self.exit_slit_position[1]
        new_w = self.wavelength + new_offset

        if not (exit_0 <= new_w <= exit_1):
            return self.our

        self.busy = True

        self.wavelength_offset = new_offset

        self.busy = False

        return self.ok

    async def set_rst(self, args):
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
        self.status = MonochromatorStatus.SETTINGUP
        self.busy = True

        await asyncio.sleep(self.wait_time)

        # reset values
        self.log.debug("Resetting wavelength")
        self.wavelength_offset = 0.
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
        self.busy = False

        self.log.debug("Done rst")
        return self.ok

    async def set_set(self, args):
        """Setup all parameters in the following order:
        "Wavelength Grating FrontEntranceSlitWidth FrontExitSlitWidth"

        Parameters
        ----------
        args : list(str)
            A list with the values for each parameter to set. A total of four
            items is expected;
                Wavelength, in nm
                Grating
                FrontEntranceSlitWidth, in mm
                FrontExitSlitWidth, im mm


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

    async def get_wl(self, args):
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

    async def get_gr(self, args):
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

    async def get_ens(self, args):
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

    async def get_exs(self, args):
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

    async def get_swst(self, args):
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

import asyncio
import enum
import logging
import time

from lsst.ts import tcpip, utils
from lsst.ts.idl.enums.ATMonochromator import Status as MonochromatorStatus

__all__ = ["Model", "ModelReply"]


class ModelReply(enum.Enum):
    OK = "#OK"
    OUT_OF_RANGE = "#OUR"  # Out of range
    INVALID = "??"  # Invalid command
    BUSY = "#BUSY"  # Device busy executing another command
    REJECTED = "#RJCT"  # Rejected


class Model:
    """A model class to represent the connection to the Monochromator. It
    implements all the available commands from the hardware and ways to select
    a configuration, connect to the Monochromator and so on.
    """

    def __init__(self, log: logging.Logger) -> None:

        self.log = (
            logging.getLogger(type(self).__name__)
            if log is None
            else log.getChild(type(self).__name__)
        )

        self.connection_timeout = 10.0
        self.read_timeout = 10.0
        self.move_timeout = 60.0
        self.move_grating_timeout = 300

        self.wait_ready_sleeptime = 0.5

        self.connect_task = utils.make_done_future()
        self.client = tcpip.Client(host="", port=None, log=self.log)

        self.cmd_lock = asyncio.Lock()
        self.controller_ready = False

    @property
    def connected(self):
        return self.client.connected

    async def connect(self, host: str, port: str) -> None:
        """Connect to the monochromator controller's TCP/IP port."""
        self.log.debug(f"connecting to: {host}:{port}")
        if self.connected:
            raise RuntimeError("Already connected")
        self.client = tcpip.Client(host=host, port=port, log=self.log)
        await self.client.start_task

        self.log.debug("connected")

    async def disconnect(self) -> None:
        """Disconnect from the monochromator controller's TCP/IP port."""
        self.log.debug("disconnect")

        try:
            await self.client.close()
        except Exception:
            self.log.exception("Disconnect failed")
        finally:
            self.log.debug("Closing anyway.")
            self.client = tcpip.Client(host="", port=None, log=self.log)

    async def reset_controller(self) -> ModelReply:
        """Reset controller.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd("!RST 1")
        return ModelReply(cmd_reply)

    async def get_wavelength(self) -> float:
        """Get current wavelength.

        Returns
        -------
        wavelength : float
            In nm.

        """
        cmd_reply = await self.send_cmd("?WL")
        reply = cmd_reply.split()

        if reply[0] == "#WL":
            return float(reply[1])
        else:
            raise RuntimeError(f"Got {cmd_reply} from controller.")

    async def get_grating(self) -> int:
        """Get current grating.

        Returns
        -------
        grating : int

        """
        cmd_reply = await self.send_cmd("?GR")
        reply = cmd_reply.split()
        if reply[0] == "#GR":
            return int(reply[1])
        else:
            raise RuntimeError(f"Got {cmd_reply} from controller.")

    async def get_entrance_slit(self) -> float:
        """Get current entrance slit position.

        Returns
        -------
        ens : float
            In mm

        """
        cmd_reply = await self.send_cmd("?ENS")
        reply = cmd_reply.split()

        if reply[0] == "#ENS":
            return float(reply[1])
        else:
            raise RuntimeError(f"Got {cmd_reply} from controller.")

    async def get_exit_slit(self) -> float:
        """Get current exit slit position.

        Returns
        -------
        exs : float
            In mm

        """
        cmd_reply = await self.send_cmd("?EXS")
        reply = cmd_reply.split()
        if reply[0] == "#EXS":
            return float(reply[1])
        else:
            raise RuntimeError(f"Got {cmd_reply} from controller.")

    async def get_status(self) -> MonochromatorStatus:
        """Get controller status.

        Returns
        -------
        status : MonochromatorStatus

        """
        cmd_reply = await self.send_cmd("?SWST")
        reply = cmd_reply.split()
        if reply[0] == "#SWST":
            return MonochromatorStatus(int(reply[1]))
        else:
            raise RuntimeError(f"Got {cmd_reply} from controller.")

    async def set_wavelength(self, value: float) -> ModelReply:
        """Set current wavelength.

        Parameters
        ----------
        value : float
            Wavelength in nm.

        Returns
        -------
        reply : ModelReply

        """
        grating = await self.get_grating()
        entry = await self.get_entrance_slit()
        ex = await self.get_exit_slit()
        cmd_reply = await self.send_cmd(f"!SET {value} {grating} {entry} {ex}")
        return ModelReply(cmd_reply)

    async def set_grating(self, value: int) -> ModelReply:
        """Set current grating.

        Parameters
        ----------
        value : int
            Grating index.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd(f"!GR {value}")
        return ModelReply(cmd_reply)

    async def set_entrance_slit(self, value: float) -> ModelReply:
        """Set current entrance slit size.

        Parameters
        ----------
        value : float
            Size in mm.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd(f"!ENS {value}")
        return ModelReply(cmd_reply)

    async def set_exit_slit(self, value: float) -> ModelReply:
        """Set current exit slit size.

        Parameters
        ----------
        value : float
            Size in mm.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd(f"!EXS {value}")
        return ModelReply(cmd_reply)

    async def set_calibrate_wavelength(self, wavelength: float) -> ModelReply:
        """Calibrate wavelength.

        Will make the current wavelength match the passed value.

        Parameters
        ----------
        wavelength : float

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd(f"!CLW {wavelength}")
        return ModelReply(cmd_reply)

    async def set_all(
        self, wavelength: float, grating: int, entrance_slit: float, exit_slit: float
    ) -> ModelReply:
        """Set all values at the same time.

        Parameters
        ----------
        wavelength : float
            In nm.
        grating : int
            Grating index
        entrance_slit : float
            In mm.
        exit_slit : float
            In mm.

        Returns
        -------
        reply : ModelReply

        """
        self.log.debug(
            f"Setting all: {wavelength} {grating} {entrance_slit} {exit_slit}"
        )
        cmd_reply = await self.send_cmd(
            f"!SET {wavelength} {grating} {entrance_slit} {exit_slit}"
        )
        return ModelReply(cmd_reply)

    async def wait_ready(self, cmd: str) -> bool:
        """Wait until controller is ready.

        Parameters
        ----------
        cmd : str
            Name of the command being waited on. This is used mostly for
            logging/reporting purposes.

        Returns
        -------
        bool
            Returns True when the status is ready.

        Raises
        ------
        TimeoutError
            If monochromator status does not transition to READY in the
            specified timeout.
        RuntimeError
            If monochromator controller status is FAULT or OFFLINE.
        """
        # Wait until controller is ready again
        start_time = time.time()

        timeout = self.move_grating_timeout if "grating" in cmd else self.move_timeout
        while True:

            status = await self.get_status()
            if status == MonochromatorStatus.READY:
                return True
            elif time.time() > start_time + timeout:
                raise TimeoutError(f"Setting up {cmd} timed out.")
            elif status == MonochromatorStatus.FAULT:
                raise RuntimeError(
                    f"Controller in FAULT state while checking for {cmd}."
                )
            elif status == MonochromatorStatus.OFFLINE:
                raise RuntimeError(f"Controller OFFLINE while checking for {cmd}.")

            await asyncio.sleep(self.wait_ready_sleeptime)

    async def send_cmd(self, cmd: str, timeout: float = 2.0) -> str:
        """Send a command to the controller and wait for the reply.

        Return the decoded reply as 0 or more lines of text
        with the final ">" stripped.

        Parameters
        ----------
        cmd : str
            Command to send to the controller.
        timeout : float
            Timeout for the command being executed (in seconds).

        Returns
        -------
        reply : str
            Response from controller.
        """
        async with self.cmd_lock:
            self.log.debug(f"Sending command of: {cmd}")
            # await asyncio.sleep(1)
            await self.client.write_str(cmd)
            # await asyncio.sleep(1)
            reply = await self.client.read_str()
            self.log.debug(f"Got reply of: {reply}")
            return reply

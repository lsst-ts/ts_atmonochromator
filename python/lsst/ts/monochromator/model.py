
import enum
import time
import asyncio

from lsst.ts.idl.enums.ATMonochromator import Status as MonochromatorStatus


__all__ = ['Model', 'ModelReply']

_LOCAL_HOST = "127.0.0.1"
_DEFAULT_PORT = 50000


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
    def __init__(self, log):

        self.log = log

        self.host = _LOCAL_HOST
        self.port = _DEFAULT_PORT
        self.connection_timeout = 10.
        self.read_timeout = 10.
        self.move_timeout = 60.

        self.wait_ready_sleeptime = 0.5

        self.connect_task = None
        self.reader = None
        self.writer = None

        self.cmd_lock = asyncio.Lock()
        self.controller_ready = False

    async def connect(self):
        """Connect to the spectrograph controller's TCP/IP port.
        """
        self.log.debug(f"connecting to: {self.host}:{self.port}")
        if self.connected:
            raise RuntimeError("Already connected")
        self.connect_task = asyncio.open_connection(host=self.host, port=self.port)
        self.reader, self.writer = await asyncio.wait_for(self.connect_task,
                                                          timeout=self.connection_timeout)

        self.log.debug(f"connected")

    async def disconnect(self):
        """Disconnect from the spectrograph controller's TCP/IP port.
        """
        self.log.debug("disconnect")
        writer = self.writer
        self.reader = None
        self.writer = None
        if writer:
            try:
                writer.write_eof()
                await asyncio.wait_for(writer.drain(), timeout=2)
            finally:
                writer.close()

    async def reset_controller(self):
        """Reset controller.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd("!RST 1")
        return ModelReply(cmd_reply)

    async def get_wavelength(self):
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

    async def get_grating(self):
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

    async def get_entrance_slit(self):
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

    async def get_exit_slit(self):
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

    async def get_status(self):
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

    async def set_wavelength(self, value):
        """Set current wavelength.

        Parameters
        ----------
        value : float
            Wavelength in nm.

        Returns
        -------
        reply : ModelReply

        """
        cmd_reply = await self.send_cmd(f"!WL {value}")
        return ModelReply(cmd_reply)

    async def set_grating(self, value):
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

    async def set_entrance_slit(self, value):
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

    async def set_exit_slit(self, value):
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

    async def set_calibrate_wavelength(self, wavelength):
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

    async def set_all(self, wavelength, grating, entrance_slit, exit_slit):
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
        self.log.debug(f"Setting all: {wavelength} {grating} {entrance_slit} {exit_slit}")
        cmd_reply = await self.send_cmd(f"!SET {wavelength} {grating} {entrance_slit} {exit_slit}")
        return ModelReply(cmd_reply)

    async def wait_ready(self, cmd):
        """Wait until controller is ready.

        Raises
        ------
        TimeoutError
        RuntimeError

        """
        # Wait until controller is ready again
        start_time = time.time()
        while True:

            status = await self.get_status()
            if status == MonochromatorStatus.READY:
                return True
            elif time.time() > start_time + self.move_timeout:
                raise TimeoutError(f"Setting up {cmd} timed out.")
            elif status == MonochromatorStatus.FAULT:
                raise RuntimeError(f"Controller in FAULT state while checking for {cmd}.")
            elif status == MonochromatorStatus.OFFLINE:
                raise RuntimeError(f"Controller OFFLINE while checking for {cmd}.")

            await asyncio.sleep(self.wait_ready_sleeptime)

    @property
    def connected(self):
        if None in (self.reader, self.writer):
            return False
        return True

    async def send_cmd(self, cmd, timeout=2):
        """Send a command to the controller and wait for the reply.

        Return the decoded reply as 0 or more lines of text
        with the final ">" stripped.
        """
        async with self.cmd_lock:
            self.writer.write(f"{cmd}\r\n".encode())
            await self.writer.drain()
            read_bytes = await asyncio.wait_for(self.reader.readline(), timeout=timeout)
            return read_bytes.decode().strip()

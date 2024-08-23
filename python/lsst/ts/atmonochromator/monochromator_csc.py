import asyncio
import contextlib
import pathlib
import traceback
import typing

from lsst.ts import salobj, utils
from lsst.ts.xml.enums.ATMonochromator import DetailedState, ErrorCode, Slit, Status

from . import __version__
from .config_schema import CONFIG_SCHEMA
from .mock_controller import MockServer, SimulationConfiguration
from .model import Model, ModelReply

__all__ = [
    "MonochromatorCsc",
    "run_atmonochromator",
]

# Timeout to disconnect the TCP/IP and close the mock controller (seconds)
DISCONNECT_TIMEOUT = 10


class MonochromatorCsc(salobj.ConfigurableCsc):
    """
    Commandable SAL Component (MonochromatorCsc) for the Monochromator.

    Parameters
    ----------
    initial_state : `lsst.ts.salobj.State` or `int` (optional)
        The initial state of the CSC.
    settings_to_apply : `str`, optional
        Settings to apply if ``initial_state`` is `State.DISABLED`
        or `State.ENABLED`.
    simulation_mode : `int` (optional)
        Initial simulation mode.

    Notes
    -----
    **Simulation Modes**

    Supported simulation modes

    * 0: regular operation
    * 1: simulation mode: start a mock TCP/IP ATMonochromator controller
        and talk to it

    **Error Codes**

    See `ErrorCodes`.
    """

    valid_simulation_modes = (0, 1)
    version = __version__

    def __init__(
        self,
        config_dir: typing.Union[str, pathlib.Path, None] = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        override: str = "",
        simulation_mode: int = 0,
    ) -> None:
        super().__init__(
            name="ATMonochromator",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )

        self.model = Model(self.log)

        self.want_connection = False
        self.health_monitor_task = utils.make_done_future()

        self.connect_task = utils.make_done_future()
        self.mock_server = None

    @property
    def wavelength(self):
        return self.evt_wavelength.data.wavelength

    @property
    def grating(self):
        return self.evt_selectedGrating.data.gratingType

    @property
    def front_slit(self):
        return self.evt_entrySlitWidth.data.width

    @property
    def exit_slit(self):
        return self.evt_exitSlitWidth.data.width

    @property
    def detailed_state(self) -> int:
        """Set or get the detailed state as a `DetailedState` enum.

        If you set the state then it is reported as a detailedState event.
        You can set detailed_state to a `State` constant or to
        the integer equivalent.

        Raises
        ------
        ValueError
            If the new summary state is an invalid integer.
        """
        return self.evt_detailedState.data.detailedState

    async def set_detailed_state(self, detailed_state: DetailedState) -> None:
        """Set and publish detailed state.

        Parameters
        ----------
        detailed_state : DetailedState
            New value for detailed state.
        """
        await self.evt_detailedState.set_write(detailedState=detailed_state)

    def assert_ready(self) -> None:
        """Assert summary state is enabled and detailed state is READY.

        Raises
        ------
        ExpectedError
            If summary_state is not ENABLED or detailed state is not READY.
        """
        self.assert_enabled()
        if self.detailed_state != DetailedState.READY:
            raise salobj.ExpectedError(
                f"Detailed state={self.detailed_state!r} not READY"
            )

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_atcalsys"

    async def configure(self, config: typing.Any) -> None:
        """Configure the CSC.

        Parameters
        ----------
        config : object
            CSC configuration.
        """
        if self.simulation_mode == 0:
            self.log.debug("Standard operation mode.")
        elif self.simulation_mode == 1:
            self.log.warning(
                f"Simulation mode {self.simulation_mode}. "
                f"Using SimulationConfiguration instead."
            )
            config = SimulationConfiguration()
        else:
            raise RuntimeError(
                f"Unspecified simulation mode: {self.simulation_mode}. "
                f"Expecting either 0 or 1."
            )

        await self.evt_settingsAppliedMonoCommunication.set_write(
            ip=config.host,
            portRange=config.port,
            connectionTimeout=config.connection_timeout,
            readTimeout=config.read_timeout,
            writeTimeout=config.write_timeout,
            force_output=True,
        )
        await self.evt_settingsAppliedMonochromatorRanges.set_write(
            wavelengthGR1=config.wavelength_gr1,
            wavelengthGR1_GR2=config.wavelength_gr1_gr2,
            wavelengthGR2=config.wavelength_gr2,
            minSlitWidth=config.min_slit_width,
            maxSlitWidth=config.max_slit_width,
            minWavelength=config.min_wavelength,
            maxWavelength=config.max_wavelength,
            force_output=True,
        )
        await self.evt_settingsAppliedMonoHeartbeat.set_write(
            period=config.period,
            timeout=config.timeout,
            force_output=True,
        )

        self.model.connection_timeout = config.connection_timeout
        self.model.read_timeout = config.read_timeout
        self.model.move_timeout = config.write_timeout

    async def connect(self) -> None:
        """Connect to the hardware controller. Disconnect first, if connected.

        If simulating, start the mock controller just before connecting.
        After connecting, check status and start the health monitor loop.
        """
        await self.disconnect()

        if self.simulation_mode == 0:
            host = self.evt_settingsAppliedMonoCommunication.data.ip
            port = self.evt_settingsAppliedMonoCommunication.data.portRange
        elif self.simulation_mode == 1:
            self.mock_server = MockServer()
            await asyncio.wait_for(
                self.mock_server.start_task,
                timeout=SimulationConfiguration().connection_timeout,
            )
            host = self.mock_server.host
            port = self.mock_server.port
        else:
            raise RuntimeError(f"Unsupported simulation_mode={self.simulation_mode}")

        # start connection with the controller
        if not self.model.connected:
            await self.model.connect(host=host, port=port)

        # For some reason I have to add this sleep here. If I try to read
        # before that the connection unexpectedly drops.
        await asyncio.sleep(self.model.read_timeout)

        # Check that the hardware status is ready, otherwise go to FAULT
        # Note that when the controller first comes up, it will be in the
        # SETTING_UP state until a status is requested, then it will
        # become READY
        controller_status = await self.model.get_status()
        if controller_status != Status.READY:
            await self.fault(
                code=ErrorCode.HARDWARE_NOT_READY,
                report=f"Controller is not ready. Current status is "
                f"{controller_status!r}",
            )
        else:
            await self.evt_status.set_write(status=controller_status)

        wavelength = await self.model.get_wavelength()
        await self.evt_wavelength.set_write(wavelength=wavelength, force_output=True)

        grating = await self.model.get_grating()
        await self.evt_selectedGrating.set_write(gratingType=grating, force_output=True)

        entrance_slit = await self.model.get_entrance_slit()
        await self.evt_entrySlitWidth.set_write(width=entrance_slit, force_output=True)
        await self.evt_slitWidth.set_write(
            slit=Slit.ENTRY,
            slitPosition=entrance_slit,
            force_output=True,
        )

        exit_slit = await self.model.get_exit_slit()
        await self.evt_exitSlitWidth.set_write(width=exit_slit, force_output=True)
        await self.evt_slitWidth.set_write(
            slit=Slit.EXIT,
            slitPosition=exit_slit,
            force_output=True,
        )
        self.health_monitor_task = asyncio.create_task(self.health_monitor_loop())
        await self.set_detailed_state(DetailedState.READY)

    async def begin_start(self, data):
        if not self.connect_task.done():
            self.cmd_start.ack_in_progress(
                data=data, timeout=self.model.connection_timeout
            )
        return await super().begin_start(data)

    async def end_disable(self, data) -> None:
        if not self.connect_task.done():
            self.cmd_disable.ack_in_progress(
                data=data, timeout=self.model.connection_timeout, result=""
            )
        return await super().end_disable(data)

    async def end_enable(self, data) -> None:
        if not self.connect_task.done():
            self.cmd_enable.ack_in_progress(
                data=data, timeout=self.model.connection_timeout, result=""
            )
        return await super().end_enable(data)

    async def disconnect(self) -> None:
        """Disconnect from the hardware controller. A no-op if not connected.

        Stop the mock controller, if running.
        """
        self.health_monitor_task.cancel()
        if self.model.connected:
            try:
                await asyncio.wait_for(self.model.disconnect(), DISCONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                self.log.warning("Timed out disconnecting from controller.")
        if self.mock_server:
            try:
                await self.mock_server.close()
            except asyncio.TimeoutError:
                self.log.warning("Timed out stopping the mock controller.")
            finally:
                self.mock_server = None

    async def handle_summary_state(self) -> None:
        """Called when the summary state has changed."""

        if self.disabled_or_enabled:
            if not self.model.connected and self.connect_task.done():
                try:
                    await self.connect()
                    await self.set_detailed_state(DetailedState.READY)
                except Exception as e:
                    await self.fault(
                        code=ErrorCode.CONNECTION_FAILED,
                        report="Error trying to connect.",
                        traceback=traceback.format_exc(),
                    )
                    raise e
        else:

            await self.set_detailed_state(DetailedState.NOT_ENABLED)

            await self.disconnect()

    async def do_calibrateWavelength(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Calibrate wavelength.

        Parameters
        ----------
        data : ``cmd_calibrateWavelength.DataType``
            Command data
        """
        self.assert_ready()

        async with self.handle_detailed_state(DetailedState.CALIBRATING_WAVELENGTH):

            reply = await self.model.set_calibrate_wavelength(data.wavelength)
            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply!r} from controller.")
            await self.cmd_calibrateWavelength.ack_in_progress(
                data=data, timeout=self.model.move_timeout, result=""
            )
            await self.model.wait_ready("calibrate wavelength")

    async def do_changeSlitWidth(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Change slit width.

        Parameters
        ----------
        data : ``cmd_changeSlitWidth.DataType``
            Command data
        """
        self.assert_ready()

        async with self.handle_detailed_state(DetailedState.CHANGING_SLIT_WIDTH):

            if data.slit == Slit.ENTRY:
                reply = await self.model.set_entrance_slit(data.slitWidth)
            elif data.slit == Slit.EXIT:
                reply = await self.model.set_exit_slit(data.slitWidth)
            else:
                raise RuntimeError(f"Unrecognized slit {data.slit}.")

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply!r} from controller.")
            else:
                await self.cmd_changeSlitWidth.ack_in_progress(
                    data=data, timeout=self.model.move_timeout, result=""
                )
                await self.model.wait_ready("change slit width")

                if data.slit == Slit.ENTRY:
                    new_pos = await self.model.get_entrance_slit()
                    await self.evt_entrySlitWidth.set_write(
                        width=new_pos, force_output=True
                    )
                elif data.slit == Slit.EXIT:
                    new_pos = await self.model.get_exit_slit()
                    await self.evt_exitSlitWidth.set_write(
                        width=new_pos, force_output=True
                    )
                await self.evt_slitWidth.set_write(slit=data.slit, slitPosition=new_pos)

    async def do_changeWavelength(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Change wavelength.

        Parameters
        ----------
        data : ``cmd_changeWavelength.DataType``
            Command data
        """
        self.assert_ready()

        async with self.handle_detailed_state(DetailedState.CHANGING_WAVELENGTH):

            reply = await self.model.set_wavelength(data.wavelength)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.cmd_changeWavelength(
                    data=data,
                    timeout=self.model.move_timeout,
                    result="Waiting for wavelength change.",
                )
                await self.model.wait_ready("change wavelength")

                wavelength = await self.model.get_wavelength()
                await self.evt_wavelength.set_write(wavelength=wavelength)

    async def do_power(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Power up controller.

        NOT IMPLEMENTED.

        Parameters
        ----------
        data : ``cmd_power.DataType``
            Command data

        Raises
        ------
        NotImplementedError
            Command not implemented yet.
        """
        self.assert_enabled()
        raise NotImplementedError("Power command not implemented.")

    async def do_selectGrating(self, data: salobj.type_hints.BaseMsgType) -> None:
        """Select grating.

        Parameters
        ----------
        data : ``cmd_selectGrating.DataType``
            Command data
        """
        self.assert_ready()

        async with self.handle_detailed_state(DetailedState.SELECTING_GRATING):

            reply = await self.model.set_grating(data.gratingType)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.cmd_selectGrating.ack_in_progress(
                    data=data, timeout=self.model.move_grating_timeout, result=""
                )
                await self.model.wait_ready("select grating")

                grating = await self.model.get_grating()
                await self.evt_selectedGrating.set_write(
                    gratingType=grating, force_output=True
                )

    async def do_updateMonochromatorSetup(
        self, data: salobj.type_hints.BaseMsgType
    ) -> None:
        """Change wavelength, grating, entry and exit slit values at the same
        time.

        Parameters
        ----------
        data : ``cmd_updateMonochromatorSetup``
            Command data
        """
        self.assert_ready()

        async with self.handle_detailed_state(DetailedState.UPDATING_SETUP):

            reply = await self.model.set_all(
                wavelength=data.wavelength,
                grating=data.gratingType,
                entrance_slit=data.fontEntranceSlitWidth,
                exit_slit=data.fontExitSlitWidth,
            )

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.cmd_updateMonochromatorSetup.ack_in_progress(
                    data=data,
                    timeout=self.model.move_grating_timeout,
                    result="Waiting for movement",
                )
                await self.model.wait_ready("update monochromator setup.")

                wavelength = await self.model.get_wavelength()
                await self.evt_wavelength.set_write(
                    wavelength=wavelength, force_output=True
                )

                grating = await self.model.get_grating()
                await self.evt_selectedGrating.set_write(
                    gratingType=grating, force_output=True
                )

                entrance_slit = await self.model.get_entrance_slit()
                await self.evt_entrySlitWidth.set_write(
                    width=entrance_slit, force_output=True
                )
                await self.evt_slitWidth.set_write(
                    slit=Slit.ENTRY,
                    slitPosition=entrance_slit,
                    force_output=True,
                )

                exit_slit = await self.model.get_exit_slit()
                await self.evt_exitSlitWidth.set_write(
                    width=exit_slit, force_output=True
                )
                await self.evt_slitWidth.set_write(
                    slit=Slit.EXIT,
                    slitPosition=exit_slit,
                    force_output=True,
                )

    async def health_monitor_loop(self) -> None:
        """Monitor the state of the hardware."""

        start_tai = utils.current_tai()
        self.log.debug("starting health monitor loop.")

        while True:
            try:
                self.log.debug(
                    f"{self.model.connected=}, {self.model.should_be_connected=}"
                )
                controller_status = await self.model.get_status()
                await self.evt_status.set_write(status=controller_status)
                if controller_status == Status.FAULT:
                    await self.fault(
                        code=ErrorCode.HARDWARE_ERROR,
                        report="Hardware controller reported FAULT.",
                        traceback="",
                    )
                    return
                curr_tai = utils.current_tai()
                await self.tel_timestamp.set_write(timestamp=curr_tai)
                await self.tel_loopTime.set_write(loopTime=curr_tai - start_tai)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception:
                self.log.debug(
                    f"{self.model.connected=}, {self.model.should_be_connected=}"
                )
                if not self.model.connected and self.model.should_be_connected:
                    await self.fault(
                        code=ErrorCode.MISC,
                        report="Health monitor loop unexpectedly lost connection.",
                        traceback=traceback.format_exc(),
                    )
                    self.log.debug("closing health monitor loop.")
                    return
                else:
                    await self.fault(
                        code=ErrorCode.MISC,
                        report="Monitor health loop unexpectedly failed.",
                        traceback=traceback.format_exc(),
                    )
                    return

    @contextlib.asynccontextmanager
    async def handle_detailed_state(
        self,
        detailed_state_initial: DetailedState,
        detailed_state_final: DetailedState = DetailedState.READY,
    ) -> typing.AsyncGenerator[None, None]:
        """A context manager to handle changing the detailed state to an
        initial value and transitioning back to a final state.

        Parameters
        ----------
        detailed_state_initial : DetailedState
            Initial detailed state.
        detailed_state_final : DetailedState, optional
            Final detailed state. By default, DetailedState.READY.
        """

        try:
            await self.set_detailed_state(detailed_state=detailed_state_initial)
            yield
        finally:
            await self.set_detailed_state(detailed_state=detailed_state_final)


def run_atmonochromator():
    """Run ATMonochromator CSC."""
    asyncio.run(MonochromatorCsc.amain(index=False))

import asyncio
import traceback

from lsst.ts import salobj
from lsst.ts import utils
from lsst.ts.idl.enums.ATMonochromator import DetailedState, Status, Slit, ErrorCode

from .config_schema import CONFIG_SCHEMA
from .model import Model, ModelReply
from .mock_controller import MockController, SimulationConfiguration
from . import __version__

__all__ = ["MonochromatorCsc"]

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
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        settings_to_apply="",
        simulation_mode=0,
    ):
        super().__init__(
            name="ATMonochromator",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            settings_to_apply=settings_to_apply,
            simulation_mode=simulation_mode,
        )

        self.detailed_state = DetailedState.NOT_ENABLED

        self.model = Model(self.log)

        self.want_connection = False
        self.health_monitor_task = utils.make_done_future()

        self.mock_ctrl = None

        self.connect_task = utils.make_done_future()

    @property
    def detailed_state(self):
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

    @detailed_state.setter
    def detailed_state(self, detailed_state):
        # cast state from an int or DetailedState to a DetailedState,
        # and reject invalid int values with ValueError
        new_state = DetailedState(detailed_state)
        self.evt_detailedState.set_put(detailedState=new_state)

    def assert_ready(self):
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
    def get_config_pkg():
        return "ts_config_atcalsys"

    async def configure(self, config):
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

        self.evt_settingsAppliedMonoCommunication.set_put(
            ip=config.host,
            portRange=config.port,
            connectionTimeout=config.connection_timeout,
            readTimeout=config.read_timeout,
            writeTimeout=config.write_timeout,
            force_output=True,
        )
        self.evt_settingsAppliedMonochromatorRanges.set_put(
            wavelengthGR1=config.wavelength_gr1,
            wavelengthGR1_GR2=config.wavelength_gr1_gr2,
            wavelengthGR2=config.wavelength_gr2,
            minSlitWidth=config.min_slit_width,
            maxSlitWidth=config.max_slit_width,
            minWavelength=config.min_wavelength,
            maxWavelength=config.max_wavelength,
            force_output=True,
        )
        self.evt_settingsAppliedMonoHeartbeat.set_put(
            period=config.period,
            timeout=config.timeout,
            force_output=True,
        )

        self.model.connection_timeout = config.connection_timeout
        self.model.read_timeout = config.read_timeout
        self.model.move_timeout = config.write_timeout

    async def connect(self):
        """Connect to the hardware controller. Disconnect first, if connected.

        If simulating, start the mock controller just before connecting.
        After connecting, check status and start the health monitor loop.
        """
        await self.disconnect()

        if self.simulation_mode == 0:
            host = self.evt_settingsAppliedMonoCommunication.data.ip
            port = self.evt_settingsAppliedMonoCommunication.data.portRange
        elif self.simulation_mode == 1:
            self.mock_ctrl = MockController()
            await asyncio.wait_for(
                self.mock_ctrl.start(),
                timeout=SimulationConfiguration().connection_timeout,
            )
            host = self.mock_ctrl.config.host
            port = self.mock_ctrl.port
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
            self.fault(
                code=ErrorCode.HARDWARE_NOT_READY,
                report=f"Controller is not ready. Current status is "
                f"{controller_status!r}",
            )
        else:
            self.evt_status.set_put(status=controller_status)

        wavelength = await self.model.get_wavelength()
        self.evt_wavelength.set_put(wavelength=wavelength, force_output=True)

        grating = await self.model.get_grating()
        self.evt_selectedGrating.set_put(gratingType=grating, force_output=True)

        entrance_slit = await self.model.get_entrance_slit()
        self.evt_entrySlitWidth.set_put(width=entrance_slit, force_output=True)
        self.evt_slitWidth.set_put(
            slit=Slit.ENTRY,
            slitPosition=entrance_slit,
            force_output=True,
        )

        exit_slit = await self.model.get_exit_slit()
        self.evt_exitSlitWidth.set_put(width=exit_slit, force_output=True)
        self.evt_slitWidth.set_put(
            slit=Slit.EXIT,
            slitPosition=exit_slit,
            force_output=True,
        )
        self.health_monitor_task = asyncio.create_task(self.health_monitor_loop())
        self.detailed_state = DetailedState.READY

    async def disconnect(self):
        """Disconnect from the hardware controller. A no-op if not connected.

        Stop the mock controller, if running.
        """
        self.detailed_state = DetailedState.NOT_ENABLED
        self.health_monitor_task.cancel()
        if self.model.connected:
            try:
                await asyncio.wait_for(self.model.disconnect(), DISCONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                self.log.warning("Timed out disconnecting from controller.")
        if self.mock_ctrl is not None:
            try:
                await self.mock_ctrl.stop(DISCONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                self.log.warning("Timed out stopping the mock controller.")
            self.mock_ctrl = None

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if not self.model.connected and self.connect_task.done():
                try:
                    await self.connect()
                except Exception as e:
                    self.fault(
                        code=ErrorCode.CONNECTION_FAILED,
                        report="Error trying to connect.",
                        traceback=traceback.format_exc(),
                    )
                    raise e

        else:
            await self.disconnect()

    async def do_calibrateWavelength(self, data):
        """Calibrate wavelength.

        Parameters
        ----------
        data : ATMonochromator_command_calibrateWavelengthC

        """
        self.assert_ready()
        self.detailed_state = DetailedState.CALIBRATING_WAVELENGTH

        try:
            reply = await self.model.set_calibrate_wavelength(data.wavelength)
            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply!r} from controller.")

            await self.model.wait_ready("calibrate wavelength")
        except Exception as e:
            self.log.error("Error executing command 'calibrateWavelength'.")
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.READY

    async def do_changeSlitWidth(self, data):
        """Change slit width.

        Parameters
        ----------
        data : ATMonochromator_command_changeSlitWidthC

        """
        self.assert_ready()
        self.detailed_state = DetailedState.CHANGING_SLIT_WIDTH

        try:
            if data.slit == Slit.ENTRY:
                reply = await self.model.set_entrance_slit(data.slitWidth)
            elif data.slit == Slit.EXIT:
                reply = await self.model.set_exit_slit(data.slitWidth)
            else:
                raise RuntimeError(f"Unrecognized slit {data.slit}.")

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply!r} from controller.")
            else:

                await self.model.wait_ready("change slit width")

                if data.slit == Slit.ENTRY:
                    new_pos = await self.model.get_entrance_slit()
                    self.evt_entrySlitWidth.set_put(width=new_pos, force_output=True)
                elif data.slit == Slit.EXIT:
                    new_pos = await self.model.get_exit_slit()
                    self.evt_exitSlitWidth.set_put(width=new_pos, force_output=True)
                self.evt_slitWidth.set_put(slit=data.slit, slitPosition=new_pos)
        except Exception as e:
            self.log.error("Error executing command 'changeSlitWidth'.")
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.READY

    async def do_changeWavelength(self, data):
        """Change wavelength.

        Parameters
        ----------
        data : ATMonochromator_command_changeWavelengthC

        """
        self.assert_ready()
        self.detailed_state = DetailedState.CHANGING_WAVELENGTH
        try:
            reply = await self.model.set_wavelength(data.wavelength)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:

                await self.model.wait_ready("change wavelength")

                wavelength = await self.model.get_wavelength()
                self.evt_wavelength.set_put(wavelength=wavelength)

        except Exception as e:
            self.log.error("Error executing command 'changeWavelength'")
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.READY

    async def do_power(self, data):
        """

        Parameters
        ----------
        data : ATMonochromator_command_powerC

        """
        self.assert_enabled()
        raise NotImplementedError("Power command not implemented.")

    async def do_selectGrating(self, data):
        """Select grating.

        Parameters
        ----------
        data : ATMonochromator_command_selectGratingC

        """
        self.assert_ready()
        self.detailed_state = DetailedState.SELECTING_GRATING
        try:
            reply = await self.model.set_grating(data.gratingType)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("select grating")

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating, force_output=True)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.READY

    async def do_updateMonochromatorSetup(self, data):
        """Change wavelength, grating, entry and exit slit values at the same
        time.

        Parameters
        ----------
        data : ATMonochromator_command_updateMonochromatorSetupC

        """
        self.assert_ready()
        self.detailed_state = DetailedState.UPDATING_SETUP
        try:
            reply = await self.model.set_all(
                wavelength=data.wavelength,
                grating=data.gratingType,
                entrance_slit=data.fontEntranceSlitWidth,
                exit_slit=data.fontExitSlitWidth,
            )

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("update monochromator setup.")

                wavelength = await self.model.get_wavelength()
                self.evt_wavelength.set_put(wavelength=wavelength, force_output=True)

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating, force_output=True)

                entrance_slit = await self.model.get_entrance_slit()
                self.evt_entrySlitWidth.set_put(width=entrance_slit, force_output=True)
                self.evt_slitWidth.set_put(
                    slit=Slit.ENTRY,
                    slitPosition=entrance_slit,
                    force_output=True,
                )

                exit_slit = await self.model.get_exit_slit()
                self.evt_exitSlitWidth.set_put(width=exit_slit, force_output=True)
                self.evt_slitWidth.set_put(
                    slit=Slit.EXIT,
                    slitPosition=exit_slit,
                    force_output=True,
                )

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.READY

    async def health_monitor_loop(self):
        """Monitor the state of the hardware."""

        start_tai = utils.current_tai()

        while self.summary_state == salobj.State.ENABLED:
            try:
                controller_status = await self.model.get_status()
                self.evt_status.set_put(status=controller_status)
                if controller_status == Status.FAULT:
                    self.fault(
                        code=ErrorCode.HARDWARE_ERROR,
                        report="Hardware controller reported FAULT.",
                        traceback="",
                    )
                    return
                curr_tai = utils.current_tai()
                self.tel_timestamp.set_put(timestamp=curr_tai)
                self.tel_loopTime.set_put(loopTime=curr_tai - start_tai)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception:
                self.fault(
                    code=ErrorCode.MISC,
                    report="Health monitor loop unexpectedly died.",
                    traceback=traceback.format_exc(),
                )
                return

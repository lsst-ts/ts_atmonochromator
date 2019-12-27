import time
import asyncio
import pathlib
import traceback

from lsst.ts import salobj
from lsst.ts.idl.enums import ATMonochromator

from .model import Model, ModelReply
from .mock_controller import MockMonochromatorController, SimulationConfiguration

__all__ = ['CSC']

GENERIC_ERROR = 8200
"""Generic error code
"""

CMD_TIMEOUT = 8201
"""Time out executing command
"""

DEV_TIMEOUT = 8202
"""Device execution timeout
"""

WRONG_STAT = 8203
"""Wrong answer at querying status
"""

NO_CONTROLLER = 8204
"""Monochromator Controller not responding
"""

NO_SERVER = 8205
"""Monochromator server not connected
"""

CONTROLLER_TIMEOUT = 8206
"""Monochromator Controller timeout
"""

HARDWARE_ERROR = 8207
"""Monochromator Hardware Error
"""

HEALTH_LOOP_DIED = 8208
"""Health monitor loop died
"""


class CSC(salobj.ConfigurableCsc):
    """
    Commandable SAL Component (CSC) for the Monochromator.

    Parameters
    ----------
    initial_state : `salobj.State` or `int` (optional)
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `lsst.ts.salobj.StateSTANDBY`,
        the default.
    initial_simulation_mode : `int` (optional)
        Initial simulation mode.

    Notes
    -----
    **Simulation Modes**

    Supported simulation modes

    * 0: regular operation
    * 1: simulation mode: start a mock TCP/IP ATMonochromator controller
        and talk to it

    **Error Codes**

    * 8200: Generic error

    * 8201: Time out executing command

    * 8202: Device execution timeout

    * 8203: Wrong answer at querying status

    * 8204: Monochromator Controller not responding

    * 8205: Monochromator server not connected

    * 8206: Monochromator Controller timeout

    * 8207: Monochromator Hardware Error

    * 8208: Health monitoring loop died.

    """

    def __init__(self, config_dir=None, initial_state=salobj.State.STANDBY,
                 initial_simulation_mode=0):
        self._detailed_state = None

        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath("schema",
                                                                           "ATMonochromator.yaml")

        super().__init__("ATMonochromator", index=0,
                         schema_path=schema_path,
                         config_dir=config_dir, initial_state=initial_state,
                         initial_simulation_mode=initial_simulation_mode)

        self.detailed_state = ATMonochromator.DetailedState.NOT_ENABLED

        self.model = Model(self.log)

        self.config = None

        self.want_connection = False
        self._health_loop = None

        self.mock_ctrl = None
        self.mock_ctrl_port = 50000

    def report_detailed_state(self):
        """Report a new value for detailed_state, including current state.
        """
        self.evt_detailedState.set_put(detailedState=self.detailed_state)

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
        return self._detailed_state

    async def end_start(self, data):
        """ Mark a connection to the controller and wanted.
        """
        self.want_connection = True
        await super().end_start(data)

    @detailed_state.setter
    def detailed_state(self, detailed_state):
        # cast summary_state from an int or State to a State,
        # and reject invalid int values with ValueError
        self._detailed_state = ATMonochromator.DetailedState(detailed_state)
        self.report_detailed_state()

    def assert_ready(self, action):
        """ Check that detailed state is READY.

        Parameters
        ----------
        action : str
            Name of command or action being performed.

        Raises
        ------
        ExpectedError
            If detailed state is not READY.
        """
        if self.detailed_state != ATMonochromator.DetailedState.READY:
            raise salobj.ExpectedError(f"{action} not allowed in detailed state "
                                       f"{self.detailed_state!r}, expected "
                                       f"{ATMonochromator.DetailedState.READY!r}.")

    @staticmethod
    def get_config_pkg():
        return "ts_config_atcalsys"

    async def configure(self, config):

        if self.simulation_mode == 0:
            self.log.debug("Standard operation mode.")
            self.config = config
        elif self.simulation_mode == 1:
            self.log.warning(f"Simulation mode {self.simulation_mode}. "
                             f"Using SimulationConfiguration instead.")
            self.config = SimulationConfiguration()
        else:
            raise RuntimeError(f"Unspecified simulation mode: {self.simulation_mode}. "
                               f"Expecting either 0 or 1.")

        self.evt_settingsAppliedMonoCommunication.set_put(
            ip=self.config.host,
            portRange=self.config.port,
            connectionTimeout=self.config.connection_timeout,
            readTimeout=self.config.read_timeout,
            writeTimeout=self.config.write_timeout,
            force_output=True,
        )
        self.evt_settingsAppliedMonochromatorRanges.set_put(
            wavelengthGR1=self.config.wavelength_gr1,
            wavelengthGR1_GR2=self.config.wavelength_gr1_gr2,
            wavelengthGR2=self.config.wavelength_gr2,
            minSlitWidth=self.config.min_slit_width,
            maxSlitWidth=self.config.max_slit_width,
            minWavelength=self.config.min_wavelength,
            maxWavelength=self.config.max_wavelength,
            force_output=True,
        )
        self.evt_settingsAppliedMonoHeartbeat.set_put(
            period=self.config.period,
            timeout=self.config.timeout,
            force_output=True,
        )

        self.model.host = self.config.host
        self.model.port = self.config.port
        self.model.connection_timeout = self.config.connection_timeout
        self.model.read_timeout = self.config.read_timeout
        self.model.move_timeout = self.config.write_timeout

    async def end_enable(self, data):
        """Connect to the hardware controller.
        """
        try:
            # start connection with the controller
            if not self.model.connected:
                await self.model.connect()
                self.want_connection = False

            # For some reason I have to add this sleep here. If I try to read
            # before that the connection unexpectedly drops.
            await asyncio.sleep(self.model.read_timeout)

            # Check that the hardware status is ready, otherwise go to FAULT
            controller_status = await self.model.get_status()
            if controller_status != ATMonochromator.Status.READY:
                self.fault(code=WRONG_STAT,
                           report=f"Controller is not ready. Current status is "
                                  f"{controller_status!r}")
            else:
                self.evt_status.set_put(status=controller_status)

            wavelength = await self.model.get_wavelength()
            self.evt_wavelength.set_put(wavelength=wavelength,
                                        force_output=True)

            grating = await self.model.get_grating()
            self.evt_selectedGrating.set_put(gratingType=grating,
                                             force_output=True)

            entrance_slit = await self.model.get_entrance_slit()
            self.evt_entrySlitWidth.set_put(width=entrance_slit,
                                            force_output=True)
            self.evt_slitWidth.set_put(
                slit=ATMonochromator.Slit.ENTRY,
                slitPosition=entrance_slit,
                force_output=True)

            exit_slit = await self.model.get_exit_slit()
            self.evt_exitSlitWidth.set_put(width=exit_slit,
                                           force_output=True)
            self.evt_slitWidth.set_put(
                slit=ATMonochromator.Slit.EXIT,
                slitPosition=exit_slit,
                force_output=True)
        except Exception as e:
            self.fault(code=GENERIC_ERROR,
                       report="Error trying to finish enable command.",
                       traceback=traceback.format_exc())
            raise e
        else:
            self.detailed_state = ATMonochromator.DetailedState.READY

        self._health_loop = asyncio.create_task(self.health_monitor_loop())

    async def end_disable(self, data):
        """End do_disable; called after state changes
        but before command acknowledged.

        Schedule disconnect from model controller to the event loop, specify
        that a new connection will be required when enabling and set detailed
        state.
        """
        self.detailed_state = ATMonochromator.DetailedState.NOT_ENABLED
        try:
            await asyncio.wait_for(self._health_loop,
                                   timeout=self.config.connection_timeout)
        except asyncio.TimeoutError:
            self.log.warning('Health monitor loop timed out. Cancelling')
            self._health_loop.cancel()
            try:
                await self._health_loop
            except asyncio.CancelledError:
                self.log.debug("Health monitor loop cancelled.")
            except Exception as e:
                self.log.error("Unexpected exception cancelling health monitor loop.")
                self.log.exception(e)
        except Exception as e:
            self.log.error("Unexpected exception waiting for health monitor loop to finish.")
            self.log.exception(e)

        try:
            await asyncio.wait_for(self.model.disconnect(),
                                   self.config.connection_timeout)
        except asyncio.TimeoutError:
            self.log.error("Timed out waiting for model to disconnect from controller.")
        except Exception as e:
            self.log.error("Unexpected exception disconnecting from controller.")
            self.log.exception(e)

        self.want_connection = True

    async def do_calibrateWavelength(self, data):
        """Calibrate wavelength.

        Parameters
        ----------
        data : ATMonochromator_command_calibrateWavelengthC

        """
        self.assert_enabled("calibrateWavelength")
        self.assert_ready("calibrateWavelength")
        self.detailed_state = ATMonochromator.DetailedState.CALIBRATING_WAVELENGTH

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
            self.detailed_state = ATMonochromator.DetailedState.READY

    async def do_changeSlitWidth(self, data):
        """Change slit width.

        Parameters
        ----------
        data : ATMonochromator_command_changeSlitWidthC

        """
        self.assert_enabled("changeSlitWidth")
        self.assert_ready("changeSlitWidth")
        self.detailed_state = ATMonochromator.DetailedState.CHANGING_SLIT_WIDTH

        try:
            if data.slit == ATMonochromator.Slit.ENTRY:
                reply = await self.model.set_entrance_slit(data.slitWidth)
            elif data.slit == ATMonochromator.Slit.EXIT:
                reply = await self.model.set_exit_slit(data.slitWidth)
            else:
                raise RuntimeError(f"Unrecognized slit {data.slit}.")

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply!r} from controller.")
            else:

                await self.model.wait_ready("change slit width")

                if data.slit == ATMonochromator.Slit.ENTRY:
                    new_pos = await self.model.get_entrance_slit()
                    self.evt_entrySlitWidth.set_put(width=new_pos,
                                                    force_output=True)
                elif data.slit == ATMonochromator.Slit.EXIT:
                    new_pos = await self.model.get_exit_slit()
                    self.evt_exitSlitWidth.set_put(width=new_pos,
                                                   force_output=True)
                self.evt_slitWidth.set_put(slit=data.slit,
                                           slitPosition=new_pos)
        except Exception as e:
            self.log.error("Error executing command 'changeSlitWidth'.")
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = ATMonochromator.DetailedState.READY

    async def do_changeWavelength(self, data):
        """Change wavelength.

        Parameters
        ----------
        data : ATMonochromator_command_changeWavelengthC

        """
        self.assert_enabled("changeWavelength")
        self.assert_ready("changeWavelength")
        self.detailed_state = ATMonochromator.DetailedState.CHANGING_WAVELENGTH
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
            self.detailed_state = ATMonochromator.DetailedState.READY

    async def do_power(self, data):
        """

        Parameters
        ----------
        data : ATMonochromator_command_powerC

        """
        self.assert_enabled("power")
        raise NotImplementedError("Power command not implemented.")

    async def do_selectGrating(self, data):
        """Select grating.

        Parameters
        ----------
        data : ATMonochromator_command_selectGratingC

        """
        self.assert_enabled("selectGrating")
        self.assert_ready("selectGrating")
        self.detailed_state = ATMonochromator.DetailedState.SELECTING_GRATING
        try:
            reply = await self.model.set_grating(data.gratingType)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("select grating")

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating,
                                                 force_output=True)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = ATMonochromator.DetailedState.READY

    async def do_updateMonochromatorSetup(self, data):
        """Change wavelength, grating, entry and exit slit values at the same
        time.

        Parameters
        ----------
        data : ATMonochromator_command_updateMonochromatorSetupC

        """
        self.assert_enabled("updateMonochromatorSetup")
        self.assert_ready("updateMonochromatorSetup")
        self.detailed_state = ATMonochromator.DetailedState.UPDATING_SETUP
        try:
            reply = await self.model.set_all(wavelength=data.wavelength,
                                             grating=data.gratingType,
                                             entrance_slit=data.fontEntranceSlitWidth,
                                             exit_slit=data.fontExitSlitWidth)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("update monochromator setup.")

                wavelength = await self.model.get_wavelength()
                self.evt_wavelength.set_put(wavelength=wavelength,
                                            force_output=True)

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating,
                                                 force_output=True)

                entrance_slit = await self.model.get_entrance_slit()
                self.evt_entrySlitWidth.set_put(width=entrance_slit,
                                                force_output=True)
                self.evt_slitWidth.set_put(
                    slit=ATMonochromator.Slit.ENTRY,
                    slitPosition=entrance_slit,
                    force_output=True)

                exit_slit = await self.model.get_exit_slit()
                self.evt_exitSlitWidth.set_put(width=exit_slit,
                                               force_output=True)
                self.evt_slitWidth.set_put(
                    slit=ATMonochromator.Slit.EXIT,
                    slitPosition=exit_slit,
                    force_output=True)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = ATMonochromator.DetailedState.READY

    async def health_monitor_loop(self):
        """A coroutine to monitor the state of the hardware."""

        start_time = time.time()

        while self.summary_state == salobj.State.ENABLED:
            try:
                controller_status = await self.model.get_status()
                self.evt_status.set_put(status=controller_status)
                if controller_status == ATMonochromator.Status.FAULT:
                    self.fault(code=HARDWARE_ERROR,
                               report="Hardware controller reported FAULT.",
                               traceback="")
                    return
                self.tel_timestamp.set_put(timestamp=time.time())
                self.tel_loopTime.set_put(loopTime=time.time() - start_time)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception:
                self.fault(code=HEALTH_LOOP_DIED,
                           report="Health loop died for an unspecified reason.",
                           traceback=traceback.format_exc())
                return

    async def implement_simulation_mode(self, simulation_mode):
        """Implement going into or out of simulation mode.

        Parameters
        ----------
        simulation_mode : `int`
            Requested simulation mode; 0 for normal operation.

        Raises
        ------
        ExpectedError
            If ``simulation_mode`` is not a supported value.

        Notes
        -----
        Subclasses should override this method to implement simulation
        mode. The implementation should:

        * Check the value of ``simulation_mode`` and raise
          `ExpectedError` if not supported.
        * If ``simulation_mode`` is 0 then go out of simulation mode.
        * If ``simulation_mode`` is nonzero then enter the requested
          simulation mode.

        Do not check the current summary state, nor set the
        ``simulation_mode`` property nor report the new mode.
        All of that is handled `do_setSimulationMode`.
        """
        if simulation_mode not in (0, 1):
            raise salobj.ExpectedError(
                f"Simulation_mode={simulation_mode} must be 0 or 1")

        if self.simulation_mode == simulation_mode:
            return

        await self.model.disconnect()
        if self.mock_ctrl is not None:
            await self.mock_ctrl.stop(self.config.write_timeout)
            self.mock_ctrl = None

        if simulation_mode == 1:
            self.mock_ctrl = MockMonochromatorController()
            await asyncio.wait_for(self.mock_ctrl.start(),
                                   timeout=SimulationConfiguration().connection_timeout)
        if self.want_connection:
            await self.model.connect()

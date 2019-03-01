import asyncio
import traceback
import time
import enum

import SALPY_ATMonochromator

from lsst.ts import salobj

from .model import Model, MonochromatorStatus, ModelReply
from .mock_controller import MockMonochromatorController

__all__ = ['CSC', "DetailedState"]

HEALTH_LOOP_DIED = 8208

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


class DetailedState(enum.IntEnum):
    """State constants.

    The numeric values come from
    https://confluence.lsstcorp.org/display/SYSENG/SAL+constraints+and+recommendations
    """

    OFFLINE = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_OfflineState
    STANDBY = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_StandbyState
    DISABLED = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_DisabledState
    ENABLED = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_EnabledState
    FAULT = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_FaultState
    MONO_SETTING_UP = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_MonoSettingUpState
    STOPPED = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_StoppedState
    STOPPED_COOLER_OFF = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_StoppedCoolerOffState
    STOPPED_LIGHTS_OFF = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_StoppedLightOffState
    STOPPED_LIGHTS_ON = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_StoppedLightOnState
    MONO_MANUAL_SETUP = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_MonoManualSetup
    MONO_AUTO_SETUP = SALPY_ATMonochromator.ATMonochromator_shared_DetailedState_MonoAutomaticSetup


class CSC(salobj.BaseCsc):
    """
    Commandable SAL Component (CSC) for the Monochromator.
    """

    def __init__(self):
        """
        Initialize CSC.
        """

        self._detailed_state = None

        super().__init__(SALPY_ATMonochromator)

        self.detailed_state = self.summary_state

        self.model = Model(self.log)

        # Publish setting versions
        self.evt_settingVersions.set_put(recommendedSettingsVersion=self.model.recommended_settings,
                                         recommendedSettingsLabels=self.model.settings_labels)

        self.want_connection = False
        self._health_loop = None

        self.mock_ctrl = None
        self.controller_status = None

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

    @detailed_state.setter
    def detailed_state(self, detailed_state):
        # cast summary_state from an int or State to a State,
        # and reject invalid int values with ValueError
        self._detailed_state = DetailedState(detailed_state)
        self.report_detailed_state()

    def begin_start(self, id_data):
        """Begin do_start; called before state changes.

        This method call setup on the model, passing the selected setting.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self.model.setup(id_data.data.settingsToApply)
        self.want_connection = True

    async def do_enable(self, id_data):
        """Transition from `State.DISABLED` to `State.ENABLED`.

        Override superclass method. The CSC needs to connect to the hardware
        controller which, is done via a coroutine. This method takes some time
        to run and the CSC cannot finalize the transition until the connection is
        complete. If the regular method begin_enable is used, the CSC will block
        and won't publish the heartbeat, which will seem like the it disappeared
        from the system.


        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self._do_change_state(id_data, "enable", [salobj.State.DISABLED], salobj.State.ENABLED)

        try:
            # start connection with the controller
            if not self.model.connected:
                await self.model.connect()
                self.want_connection = False

            # For some reason I have to add this sleep here. If I try to read before
            # that the connection unexpectedly drops.
            await asyncio.sleep(self.model.read_timeout)

            wavelength = await self.model.get_wavelength()
            self.evt_wavelength.set_put(wavelength=wavelength)

            grating = await self.model.get_grating()
            self.evt_selectedGrating.set_put(gratingType=grating)

            entrance_slit = await self.model.get_entrance_slit()
            self.evt_slitWidth.set_put(
                slit=SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontEntrance,
                slitPosition=entrance_slit)

            exit_slit = await self.model.get_exit_slit()
            self.evt_slitWidth.set_put(
                slit=SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontExit,
                slitPosition=exit_slit)
        except Exception as e:
            self.log.exception(e)
            self.fault()
            raise e

        self._health_loop = asyncio.ensure_future(self.health_monitor_loop())

    def end_disable(self, id_data):
        """End do_disable; called after state changes
        but before command acknowledged.

        Schedule disconnect from model controller to the event loop, specify that a new
        connection will be required when enabling and set detailed state.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        asyncio.ensure_future(self.model.disconnect())
        self.want_connection = True
        self.detailed_state = DetailedState.DISABLED

    def end_enable(self, id_data):
        """End do_enable; called after state changes
        but before command acknowledged.

        Set detailed state.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self.detailed_state = DetailedState.ENABLED

    def end_exitControl(self, id_data):
        """End do_exitControl; called after state changes
        but before command acknowledged.

        Set detailed state.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self.detailed_state = DetailedState.OFFLINE

    def end_standby(self, id_data):
        """End do_standby; called after state changes
        but before command acknowledged.

        Set detailed state.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self.detailed_state = DetailedState.STANDBY

    def end_start(self, id_data):
        """End do_start; called after state changes
        but before command acknowledged.

        Set detailed state.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        self.detailed_state = DetailedState.DISABLED

    async def do_calibrateWavelength(self, id_data):
        """Calibrate wavelength.

        Parameters
        ----------
        id_data : ATMonochromator_command_calibrateWavelengthC

        """
        self.assert_enabled("calibrateWavelength")
        self.detailed_state = DetailedState.MONO_MANUAL_SETUP
        try:
            reply = await self.model.set_calibrate_wavelength(id_data.data.wavelength)
            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")

            await self.model.wait_ready("calibrate wavelength")

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.ENABLED

    async def do_changeSlitWidth(self, id_data):
        """Change slit width.

        Parameters
        ----------
        id_data : ATMonochromator_command_changeSlitWidthC

        """
        self.assert_enabled("changeSlitWidth")
        self.detailed_state = DetailedState.MONO_MANUAL_SETUP
        try:
            if id_data.data.slit == SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontEntrance:
                reply = await self.model.set_entrance_slit(id_data.data.slitWidth)
            elif id_data.data.slit == SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontExit:
                reply = await self.model.set_exit_slit(id_data.data.slitWidth)
            else:
                raise RuntimeError(f"Unrecognized slit {id_data.data.slit}.")

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:

                await self.model.wait_ready("change slit width")

                if id_data.data.slit == SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontEntrance:
                    new_pos = await self.model.get_entrance_slit()
                elif id_data.data.slit == SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontExit:
                    new_pos = await self.model.get_exit_slit()

                self.evt_slitWidth.set_put(slit=id_data.data.slit,
                                           slitPosition=new_pos)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.ENABLED

    async def do_changeWavelength(self, id_data):
        """Change wavelength.

        Parameters
        ----------
        id_data : ATMonochromator_command_changeWavelengthC

        """
        self.assert_enabled("changeWavelength")
        self.detailed_state = DetailedState.MONO_MANUAL_SETUP
        try:
            reply = await self.model.set_wavelength(id_data.data.wavelength)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:

                await self.model.wait_ready("change wavelength")

                wavelength = await self.model.get_wavelength()
                self.evt_wavelength.set_put(wavelength=wavelength)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.ENABLED

    async def do_power(self, id_data):
        """

        Parameters
        ----------
        id_data : ATMonochromator_command_powerC

        """
        self.assert_enabled("power")
        raise NotImplementedError("Power command not implemented.")

    async def do_selectGrating(self, id_data):
        """Select grating.

        Parameters
        ----------
        id_data : ATMonochromator_command_selectGratingC

        """
        self.assert_enabled("selectGrating")
        self.detailed_state = DetailedState.MONO_MANUAL_SETUP
        try:
            reply = await self.model.set_grating(id_data.data.gratingType)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("select grating")

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.ENABLED

    async def do_updateMonochromatorSetup(self, id_data):
        """

        Parameters
        ----------
        id_data : ATMonochromator_command_updateMonochromatorSetupC

        """
        self.assert_enabled("updateMonochromatorSetup")
        self.detailed_state = DetailedState.MONO_MANUAL_SETUP
        try:
            reply = await self.model.set_all(wavelength=id_data.data.wavelength,
                                             grating=id_data.data.gratingType,
                                             entrance_slit=id_data.data.fontEntranceSlitWidth,
                                             exit_slit=id_data.data.fontExitSlitWidth)

            if reply != ModelReply.OK:
                raise RuntimeError(f"Got {reply} from controller.")
            else:
                await self.model.wait_ready("update monochromator setup.")

                wavelength = await self.model.get_wavelength()
                self.evt_wavelength.set_put(wavelength=wavelength)

                grating = await self.model.get_grating()
                self.evt_selectedGrating.set_put(gratingType=grating)

                entrance_slit = await self.model.get_entrance_slit()
                self.evt_slitWidth.set_put(
                    slit=SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontEntrance,
                    slitPosition=entrance_slit)

                exit_slit = await self.model.get_exit_slit()
                self.evt_slitWidth.set_put(
                    slit=SALPY_ATMonochromator.ATMonochromator_shared_Slit_FrontExit,
                    slitPosition=exit_slit)

        except Exception as e:
            self.log.exception(e)
            raise e
        finally:
            self.detailed_state = DetailedState.ENABLED

    async def health_monitor_loop(self):
        """A coroutine to monitor the state of the hardware."""

        start_time = time.time()

        while self.summary_state == salobj.State.ENABLED:
            try:
                self.controller_status = await self.model.get_status()
                if self.controller_status == MonochromatorStatus.FAULT:
                    raise RuntimeError("Controller in fault state.")
                self.tel_timestamp.set_put(timestamp=time.time())
                self.tel_loopTime.set_put(loopTime=time.time()-start_time)
                await asyncio.sleep(salobj.base_csc.HEARTBEAT_INTERVAL)
            except Exception as e:
                self.fault()
                self.log.exception(e)
                self.evt_errorCode.set_put(errorCode=HEALTH_LOOP_DIED,
                                           errorReport="Health loop died for an unspecified reason.",
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
        await self.stop_mock_ctrl()
        if simulation_mode == 1:
            self.mock_ctrl = MockMonochromatorController(port=self.port)
            await asyncio.wait_for(self.mock_ctrl.start(), timeout=2)
        if self.want_connection:
            await self.model.connect()

    def assert_enabled(self, action):
        """Assert that an action that requires ENABLED state can be run.
        """
        if self.summary_state != salobj.State.ENABLED or self.detailed_state != DetailedState.ENABLED:
            raise salobj.base.ExpectedError(f"{action} not allowed in state "
                                            f"{self.summary_state!r}:{self.detailed_state!r}")

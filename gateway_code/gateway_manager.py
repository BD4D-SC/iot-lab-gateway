#! /usr/bin/env python
# -*- coding:utf-8 -*-


""" Gateway manager """

from threading import Thread, RLock, Timer
import os
import time

from gateway_code import config
from gateway_code import common
from gateway_code import openocd_cmd
from gateway_code.profile import Profile
from gateway_code.serial_redirection import SerialRedirection
from gateway_code.autotest import autotest, expect


from gateway_code import control_node_interface, protocol_cn


import gateway_code.gateway_logging
import logging


LOGGER = logging.getLogger('gateway_code')


# Disable: I0011 - 'locally disabling warning'
# too many instance attributes
# pylint:disable=I0011,R0902
class GatewayManager(object):
    """
    Gateway Manager class,

    Manages experiments, open node and control node
    """

    def __init__(self, log_folder='.'):

        # current experiment infos
        self.exp_id = None
        self.user = None
        self.experiment_is_running = False
        self.profile = None
        self.open_node_state = "stop"

        self.rlock = RLock()
        self.timeout_timer = None

        gateway_code.gateway_logging.init_logger(log_folder)  # logger config

        self.cn_serial = control_node_interface.ControlNodeSerial()
        self.protocol = protocol_cn.Protocol(self.cn_serial.send_command)

        # open node interraction
        self.serial_redirection = SerialRedirection('m3')

        self._a8_expect = None

    def setup(self):
        """ Run commands that might crash
        Must be run before running other commands """
        # Setup control node
        ret = self.node_flash('gwt', config.FIRMWARES['control_node'])
        if ret != 0:
            raise StandardError("Control node flash failed: {ret:%d, '%s')",
                                ret, config.FIRMWARES['control_node'])

    # R0913 too many arguments 6/5
    @common.syncronous('rlock')
    def exp_start(self, exp_id, user,  # pylint: disable=R0913
                  firmware_path=None, profile=None, timeout=0):
        """
        Start an experiment

        :param exp_id: experiment id
        :param user: user owning the experiment
        :param firmware_path: path of the firmware file to flash
        :param profile: profile to configure the experiment
        :type profile: class Profile

        Experiment start steps

        1) Prepare Gateway
            a) Reset control node
            b) Start control node serial communication
            c) Start measures handler (OML thread)
        2) Prepare Control node
            a) Start Open Node DC (stopped before)
            b) Reset time control node, and update time reference
            c) Configure profile
        3) Prepare Open node
            a) Flash open node
            b) Start open node serial redirection
            c) Start GDB server
        4) Experiment Started

        """
        if config.board_type() not in ('M3', 'A8'):
            raise NotImplementedError('Board type not managed')

        if self.experiment_is_running:
            LOGGER.warning('Experiment running. Stop previous experiment')
            self.exp_stop()

        self.exp_id = exp_id
        self.user = user
        firmware_path = firmware_path or config.FIRMWARES['idle']
        try:
            _prof = profile or config.default_profile()
            self.profile = Profile(_prof, config.board_type())
        except ValueError:
            LOGGER.error('Invalid profile')
            return 1

        self.experiment_is_running = True

        ret_val = 0
        # start steps described in docstring

        # # # # # # # # # #
        # Prepare Gateway #
        # # # # # # # # # #
        ret = self.node_soft_reset('gwt')
        ret_val += ret
        time.sleep(1)  # wait CN started
        ret = self.cn_serial.start(user=self.user, exp_id=self.exp_id)
        ret_val += ret

        # # # # # # # # # # # # #
        # Prepare Control Node  #
        # # # # # # # # # # # # #
        ret = self.protocol.green_led_blink()
        ret_val += ret
        ret = self.open_power_start(power='dc')
        ret_val += ret
        ret = self.reset_time()
        ret_val += ret
        ret = self.exp_update_profile()
        ret_val += ret

        # # # # # # # # # # #
        # Prepare Open Node #
        # # # # # # # # # # #
        if config.board_type() == 'M3':
            ret = self.node_flash('m3', firmware_path)
            ret_val += ret
            ret = self.serial_redirection.start()
            ret_val += ret
            # ret = self.gdb_server.start()
            # ret_val += ret
        else:  # pragma: no cover
            pass
        if config.board_type() == 'A8':
            ret = self._debug_start_a8_tty(config.OPEN_A8_CFG['tty'],
                                           timeout=5)
            ret_val += ret
            if ret == 0:
                # Timeout 5 minutes for boot
                self._debug_a8_boot_start(5*60, config.OPEN_A8_CFG)
        else:  # pragma: no cover
            pass

        if config.robot_type() == 'roomba':  # pragma: no cover
            LOGGER.info("I'm a roomba")
            LOGGER.info("Running Start Roomba")

        if timeout != 0:
            LOGGER.debug("Setting timeout to: %d", timeout)
            self.timeout_timer = Timer(timeout, self._timeout_exp_stop,
                                       args=(exp_id, user))
            self.timeout_timer.start()
        return ret_val

    @common.syncronous('rlock')
    def _timeout_exp_stop(self, exp_id, user):
        """ Run exp_stop after timeout.

        Should stop only if experiment is the same as the experiment
        that started the timer """
        LOGGER.debug("Timeout experiment: %r %r", user, exp_id)
        if self.exp_id == exp_id and self.user == user:
            LOGGER.debug("Still running. Stop exp")
            self.exp_stop()

    @common.syncronous('rlock')
    def exp_stop(self):
        """
        Stop the current running experiment

        Experiment stop steps

        1) Cleanup Control node config
            a) Stop measures Control Node, Configure profile == None
            b) Start Open Node DC (may be running on battery)
        2) Cleanup open node
            a) Stop GDB server
            b) Stop open node serial redirection
            c) Flash Idle open node (when DC)
            d) Shutdown open node (DC)
        3) Cleanup control node interraction
            a) Stop control node serial communication
        4) Cleanup Manager state
        5) Experiment Stopped

        """
        if not self.experiment_is_running:
            LOGGER.warning("No experiment running. Don't stop")
            return 0
        ret_val = 0
        if self.timeout_timer is not None:
            self.timeout_timer.cancel()

        # # # # # # # # # # # # # # # #
        # Cleanup Control node config #
        # # # # # # # # # # # # # # # #

        self.profile = Profile(config.default_profile(), config.board_type())
        ret = self.exp_update_profile()
        ret_val += ret
        ret = self.open_power_start(power='dc')
        ret_val += ret
        ret = self.protocol.green_led_on()
        ret_val += ret

        if config.robot_type() == 'roomba':  # pragma: no cover
            LOGGER.info("I'm a roomba")
            LOGGER.info("Running stop Roomba")

        # # # # # # # # # # #
        # Cleanup open node #
        # # # # # # # # # # #
        if config.board_type() == 'M3':
            # ret = self.gdb_server.stop()
            # ret_val += ret
            ret = self.serial_redirection.stop()
            ret_val += ret
            ret = self.node_flash('m3', config.FIRMWARES['idle'])
            ret_val += ret
        elif config.board_type() == 'A8':
            self._debug_a8_boot_stop_thread()
        else:  # pragma: no cover
            raise NotImplementedError('Board type not managed')
        ret = self.open_power_stop(power='dc')
        ret_val += ret

        if config.board_type() == 'A8':
            ret = self._debug_stop_a8_tty(config.OPEN_A8_CFG['tty'], timeout=5)
            ret_val += ret

        # # # # # # # # # # # # # # # # # # #
        # Cleanup control node interraction #
        # # # # # # # # # # # # # # # # # # #
        self.cn_serial.stop()

        # Reset configuration
        self.user = None
        self.exp_id = None
        self.experiment_is_running = False

        return ret_val

    @staticmethod
    def _debug_start_a8_tty(a8_tty, timeout=0):
        """ Procedure to call at a8 startup
        It runs sanity checks and start debug features """
        # Test if open a8 tty correctly appeared
        if not common.wait_cond(timeout, True, os.path.exists, a8_tty):
            LOGGER.error('Error Open A8 tty not visible: %s', a8_tty)
            return 1
        return 0

    @staticmethod
    def _debug_stop_a8_tty(a8_tty, timeout=0):
        """ Procedure to call at a8 stop
        It runs sanity checks and stop debug features """
        # Test if open a8 tty correctly disappeared
        if not common.wait_cond(timeout, False, os.path.exists, a8_tty):
            LOGGER.error('Error Open A8 tty still exist: %s', a8_tty)
            return 1
        return 0

    def _debug_a8_boot_start(self, timeout, open_a8_cfg):
        """ A8 boot debug thread start """
        a8_debug_thread = Thread(target=self._debug_a8_boot_start_thread,
                                 args=(timeout, open_a8_cfg))
        a8_debug_thread.daemon = True
        a8_debug_thread.start()

    def _debug_a8_boot_start_thread(self, timeout, open_a8_cfg):
        """ Monitor A8 tty to check if node booted """
        self._a8_expect = expect.SerialExpect(logger=LOGGER, **open_a8_cfg)
        ret = self._a8_expect.expect(' login: ', timeout=timeout)

        if not ret:
            LOGGER.error("Boot A8 failed in time: %ds", timeout)
        else:
            LOGGER.info("Boot A8 Succeeded in time: %ds", timeout)

    def _debug_a8_boot_stop_thread(self):
        """ Stop the debug thread """
        try:
            self._a8_expect.serial_fd.close()
        except AttributeError:
            pass

    @common.syncronous('rlock')
    def exp_update_profile(self, profile=None):
        """ Update the control node profile """
        if profile is not None:
            self.profile = profile
        LOGGER.debug('Update profile')

        ret = 0
        # power_mode (keep open node started/stoped state)
        ret += self.protocol.start_stop(
            self.open_node_state, self.profile.power)
        # Consumption
        ret += self.protocol.config_consumption(self.profile.consumption)
        # Radio
        ret += self.protocol.config_radio(self.profile.radio)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Profile update failed')
        return ret

    @common.syncronous('rlock')
    def reset_time(self):
        """
        Reset control node time and update absolute time reference

        Updating time reference is propagated to measures handler
        """
        LOGGER.debug('Reset control node time')
        ret = self.protocol.reset_time()
        if ret != 0:  # pragma: no cover
            LOGGER.error('Reset time failed')
        return ret

    @common.syncronous('rlock')
    def open_power_start(self, power=None):
        """ Power on the open node """
        LOGGER.debug('Open power start')
        if power is None:
            assert self.profile is not None
            power = self.profile.power

        ret = self.protocol.start_stop('start', power)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Open power start failed')
        else:
            self.open_node_state = "start"
        return ret

    @common.syncronous('rlock')
    def open_power_stop(self, power=None):
        """ Power off the open node """
        LOGGER.debug('Open power stop')
        if power is None:
            assert self.profile is not None
            power = self.profile.power

        ret = self.protocol.start_stop('stop', power)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Open power stop failed')
        else:
            self.open_node_state = "stop"
        return ret

    @common.syncronous('rlock')       # uses `self`
    def node_soft_reset(self, node):  # pylint: disable=R0201

        """
        Reset the given node using reset pin

        :param node: Node name in {'gwt', 'm3'}
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.debug('Node %s reset', node)

        ret, _ = openocd_cmd.reset(node)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Node %s reset failed: %d', node, ret)

        return ret

    @common.syncronous('rlock')                 # uses `self`
    def node_flash(self, node, firmware_path):  # pylint: disable=R0201
        """
        Flash the given firmware on the given node

        :param node: Node name in {'gwt', 'm3'}
        :param firmware_path: Path to the firmware to be flashed on `node`.
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.debug('Flash firmware on %s: %s', node, firmware_path)

        ret, _ = openocd_cmd.flash(node, firmware_path)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Flash firmware failed on %s: %d', node, ret)
        return ret

    @common.syncronous('rlock')
    def auto_tests(self, channel, blink, flash, gps):
        """
        Run Auto-tests on nodes and gateway
        """
        autotest_manager = autotest.AutoTestManager(self)
        return autotest_manager.auto_tests(channel, blink, flash, gps)

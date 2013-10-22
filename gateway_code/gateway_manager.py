#! /usr/bin/env python
# -*- coding:utf-8 -*-


"""
manager script
"""

import gateway_code.profile
from gateway_code import config
from gateway_code import flash_firmware, reset
from gateway_code.serial_redirection import SerialRedirection

from gateway_code import control_node_interface, protocol_cn

import time

import gateway_code.gateway_logging
import logging

import atexit

LOGGER = logging.getLogger('gateway_code')

CONTROL_NODE_FIRMWARE = config.STATIC_FILES_PATH + 'control_node.elf'
IDLE_FIRMWARE = config.STATIC_FILES_PATH + 'idle.elf'


# Disable: I0011 - 'locally disabling warning'
# too many instance attributes
# pylint:disable =I0011,R0902
class GatewayManager(object):
    """
    Gateway Manager class,

    Manages experiments, open node and control node
    """
    board_type = None

    def __init__(self, log_folder='.'):

        # current experiment infos
        self.exp_id = None
        self.user = None
        self.experiment_is_running = False
        self.profile = None

        # Init cleanup, logger and board type
        atexit.register(self.exp_stop)
        gateway_code.gateway_logging.init_logger(log_folder)
        self.board_type = GatewayManager.get_board_type()

        # Setup control node
        ret = self.node_flash('gwt', CONTROL_NODE_FIRMWARE)
        if ret != 0:  # pragma: no cover
            raise StandardError("Control node flash failed: {ret:%d, '%s')",
                                ret, CONTROL_NODE_FIRMWARE)
        self.cn_serial = control_node_interface.ControlNodeSerial()
        self.protocol = protocol_cn.Protocol(self.cn_serial.send_command)

        # open node interraction
        self.serial_redirection = SerialRedirection('m3')

    def exp_start(self, exp_id, user,
                  firmware_path=None, profile=None):
        """
        Start an experiment

        :param exp_id: experiment id
        :param user: user owning the experiment
        :param firmware_path: path of the firmware file to flash
        :param profile: profile to configure the experiment
        :type profile: class Profile


        Experiment start steps
        ======================

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

        if self.experiment_is_running:
            LOGGER.warning('Experiment already running')
            return 1
        self.experiment_is_running = True

        self.exp_id = exp_id
        self.user = user
        self.profile = profile or self.default_profile()
        firmware_path = firmware_path or IDLE_FIRMWARE

        ret_val = 0
        # start steps described in docstring

        # # # # # # # # # #
        # Prepare Gateway #
        # # # # # # # # # #

        ret = self.node_soft_reset('gwt')
        ret_val += ret
        self.cn_serial.start()  # ret ?
        time.sleep(1)  # wait control node Ready, reajust time later

        # # # # # # # # # # # # #
        # Prepare Control Node  #
        # # # # # # # # # # # # #

        ret = self.open_power_start(power='dc')
        ret_val += ret
        ret = self.reset_time()
        ret_val += ret
        ret = self.exp_update_profile()
        ret_val += ret

        # # # # # # # # # # #
        # Prepare Open Node #
        # # # # # # # # # # #

        if self.board_type == 'M3':
            ret = self.node_flash('m3', firmware_path)
            ret_val += ret
            ret = self.serial_redirection.start()
            ret_val += ret
            # ret = self.gdb_server.start()
            # ret_val += ret
        else:  # pragma: no cover
            raise NotImplementedError('Board type not managed')

        return ret_val

    def exp_stop(self):
        """
        Stop the current running experiment

        Experiment stop steps
        =====================

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
            b) Reset control node (just in case)
        4) Cleanup Manager state
        5) Experiment Stopped

        """
        if not self.experiment_is_running:
            ret = 1
            LOGGER.warning('No experiment running')
            return ret
        ret_val = 0

        # # # # # # # # # # # # # # # #
        # Cleanup Control node config #
        # # # # # # # # # # # # # # # #

        ret = self.exp_update_profile(self.default_profile())
        ret_val += ret
        ret = self.open_power_start(power='dc')
        ret_val += ret

        # # # # # # # # # # #
        # Cleanup open node #
        # # # # # # # # # # #
        if self.board_type == 'M3':
            # ret = self.gdb_server.stop()
            # ret_val += ret
            ret = self.serial_redirection.stop()
            ret_val += ret
            ret = self.node_flash('m3', IDLE_FIRMWARE)
            ret_val += ret
            ret = self.open_power_stop(power='dc')
            ret_val += ret
        else:  # pragma: no cover
            raise NotImplementedError('Board type not managed')

        # # # # # # # # # # # # # # # # # # #
        # Cleanup control node interraction #
        # # # # # # # # # # # # # # # # # # #

        self.cn_serial.stop()
        ret = self.node_soft_reset('gwt')
        ret_val += ret

        # Reset configuration
        self.user = None
        self.exp_id = None
        self.profile = None
        self.experiment_is_running = False

        return ret_val

    def exp_update_profile(self, profile=None):
        """
        Update the control node profile
        """
        if profile is not None:
            self.profile = profile
        LOGGER.debug('Update profile')

        ret = 0
        ret += self.open_power_start(power=self.profile.power)
        ret += self.protocol.config_consumption(self.profile.consumption)
        # Radio

        if ret != 0:  # pragma: no cover
            LOGGER.error('Profile update failed')
        return ret

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

    def open_power_start(self, power=None):
        """ Power on the open node """
        LOGGER.debug('Open power start')
        if power is None:
            assert self.profile is not None
            power = self.profile.power

        ret = self.protocol.start_stop('start', power)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Open power start failed')
        return ret

    def open_power_stop(self, power=None):
        """ Power off the open node """
        LOGGER.debug('Open power stop')
        if power is None:
            assert self.profile is not None
            power = self.profile.power

        ret = self.protocol.start_stop('stop', power)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Open power stop failed')
        return ret

    @staticmethod
    def node_soft_reset(node):
        """
        Reset the given node using reset pin
        :param node: Node name in {'gwt', 'm3'}
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.debug('Node %s reset', node)

        ret, _out, _err = reset.reset(node)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Node %s reset failed: %d', node, ret)

        return ret

    @staticmethod
    def node_flash(node, firmware_path):
        """
        Flash the given firmware on the given node
        :param node: Node name in {'gwt', 'm3'}
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.debug('Flash firmware on %s: %s', node, firmware_path)

        ret, _out, _err = flash_firmware.flash(node, firmware_path)

        if ret != 0:  # pragma: no cover
            LOGGER.error('Flash firmware failed on %s: %d', node, ret)
        return ret

    @staticmethod
    def default_profile():
        """
        Get the default profile
        """
        import json
        with open(config.STATIC_FILES_PATH + 'default_profile.json') as _prof:
            profile_dict = json.load(_prof)
            def_profile = gateway_code.profile.profile_from_dict(
                profile_dict, GatewayManager.get_board_type())
        return def_profile

    @classmethod
    def get_board_type(cls):
        """
        Return the board type 'M3' or 'A8'
        """
        if cls.board_type is None:
            try:
                board = open(config.GATEWAY_CONFIG_PATH + 'board_type')
                cls.board_type = board.read().strip()
                board.close()
            except IOError as err:  # pragma: no cover
                raise StandardError("Could not find board type:\n  '%s'" % err)
        return cls.board_type

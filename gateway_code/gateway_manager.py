#! /usr/bin/env python
# -*- coding:utf-8 -*-


"""
manager script
"""

import gateway_code.profile
from gateway_code import config
from gateway_code import flash_firmware, reset
from gateway_code import dispatch, cn_serial_io, protocol, measures_handler
from gateway_code.serial_redirection import SerialRedirection

import Queue
import time

import gateway_code.gateway_logging
import logging

LOGGER = logging.getLogger()

CONTROL_NODE_FIRMWARE = config.STATIC_FILES_PATH + 'control_node.elf'
IDLE_FIRMWARE         = config.STATIC_FILES_PATH + 'idle.elf'

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
        self.exp_id                = None
        self.user                  = None
        self.experiment_is_running = False

        self.current_profile       = None
        self.time_reference        = None

        self.open_node_started     = False

        ret = self.node_flash('gwt', CONTROL_NODE_FIRMWARE)
        if ret != 0:
            raise StandardError("Control node flash failed: {ret:%d, '%s')" % \
                    (ret, CONTROL_NODE_FIRMWARE))

        # open node interraction
        self.serial_redirection = SerialRedirection('m3', \
                error_handler = self.cb_serial_redirection_error,
                handler_arg = self)

        # setup control node communication
        measures_queue  = Queue.Queue(1024)
        self.dispatcher = dispatch.Dispatch(measures_queue, \
                protocol.TYPE_MEASURES_MASK)

        self.rxtx       = cn_serial_io.RxTxSerial(self.dispatcher.cb_dispatcher)
        self.dispatcher.io_write = self.rxtx.write
        self.sender = self.dispatcher.send_command

        self.measure_handler = measures_handler.MeasuresReader(measures_queue)

        # configure logger
        gateway_code.gateway_logging.init_logger(log_folder)



    def exp_start(self, exp_id, user, \
            firmware_path=IDLE_FIRMWARE, profile=None):
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
        2) Prepare Open node
            a) Start Open Node DC (stopped before)
            b) Flash open node (flash when started DC)
        3) Prepare Control node
            a) Reset time control node, and update time reference
            b) Configure profile
        4) Finish Open node
            a) Start open node serial redirection
            d) Start GDB server
            c) Final reset of open node
        5) Experiment Started

        """

        if self.experiment_is_running:
            LOGGER.error('Experiment already running')
            return 1

        self.experiment_is_running = True

        self.exp_id                = exp_id
        self.user                  = user
        self.current_profile       = profile \
                if profile is not None else self.default_profile()

        ret_val = 0

        # start steps described in docstring

        # # # # # # # # # #
        # Prepare Gateway #
        # # # # # # # # # #

        ret      = self.node_soft_reset('gwt')
        ret_val += ret
        self.rxtx.start()   # ret ?
        self.measure_handler.start(self.user, self.exp_id)

        time.sleep(1) # wait control node Ready, reajust time later

        # # # # # # # # # # #
        # Prepare Open Node #
        # # # # # # # # # # #

        ret      = self.open_power_start(power='dc')
        ret_val += ret
        ret      = self.node_flash('m3', firmware_path)
        ret_val += ret

        # # # # # # # # # # # # #
        # Prepare Control Node  #
        # # # # # # # # # # # # #

        ret      = self.reset_time()
        ret_val += ret
        ret      = self.exp_update_profile()
        ret_val += ret

        # # # # # # # # # # #
        # Finish Open Node  #
        # # # # # # # # # # #

        ret      = self.serial_redirection.start()
        ret_val += ret
        # start the gdb server
        ret      = self.node_soft_reset('m3')
        ret_val += ret


        if ret_val == 0:
            LOGGER.info('Start experiment Succeeded')
        else:
            LOGGER.error('Start experiment with errors: ret_val: %d', ret_val)

        return ret_val


    def exp_stop(self):
        """
        Stop the current running experiment



        Experiment stop steps
        ======================

        1) Remove open node access
            a) Stop GDB server
            b) Stop open node serial redirection

        2) Cleanup Control node config and open node
            a) Stop measures Control Node, Configure profile == None
            b) Start Open Node DC (may be running on battery)
            b) Flash Idle open node (when DC)
            c) Shutdown open node (DC)

        3) Cleanup control node interraction
            a) Stop control node serial communication
            b) Stop measures handler (OML thread)
            c) Reset control node (just in case)

        4) Cleanup experiment informations
            a) remove current user
            b) remove expid
            c) Remove current profile
            d) Remove time reference
            e) 'Experiment running' = False

        """

        if not self.experiment_is_running:
            ret = 1
            LOGGER.error('No experiment running')
            return ret

        ret_val = 0

        # # # # # # # # # # # # # #
        # Remove open node access #
        # # # # # # # # # # # # # #

        # stop gdb server
        ret      = self.serial_redirection.stop()
        ret_val += ret

        # # # # # # # # # # # # # # # # # # # # # # #
        # Cleanup Control node config and open node #
        # # # # # # # # # # # # # # # # # # # # # # #

        ret      = self.exp_update_profile(self.default_profile())
        ret_val += ret
        ret      = self.open_power_start(power='dc')
        ret_val += ret
        ret      = self.node_flash('m3', IDLE_FIRMWARE)
        ret_val += ret
        ret      = self.open_power_stop(power='dc')
        ret_val += ret


        # # # # # # # # # # # # # # # # # # #
        # Cleanup control node interraction #
        # # # # # # # # # # # # # # # # # # #

        self.rxtx.stop()
        # stop measures handler (oml thread)
        self.measure_handler.stop()

        ret      = self.node_soft_reset('gwt')
        ret_val += ret

        self.user                  = None
        self.exp_id                = None
        self.current_profile       = None
        self.time_reference        = None

        self.experiment_is_running = False

        return ret_val


    @staticmethod
    def cb_serial_redirection_error(handler_arg, error_code):
        """ Callback for SerialRedirection error handler """
        LOGGER.error('Serial Redirection process failed "socat: ret == %d"', \
                error_code)
        time.sleep(0.5) # prevent quick loop

    def exp_update_profile(self, profile=None):
        """
        Update the control node profile
        """

        LOGGER.info('Update profile')
        ret = 0

        if profile is not None:
            self.current_profile = profile

        ret += self.open_power_start(power=self.current_profile.power)

        ret += protocol.config_consumption(self.sender, \
                self.current_profile.consumption)
        # Radio

        if ret != 0:
            LOGGER.error('Profile update failed')
        return ret


    def reset_time(self):
        """
        Reset control node time and update absolute time reference

        Updating time reference is propagated to measures handler
        """
        from datetime import datetime
        LOGGER.info('Reset control node time')
        # save the start experiment time
        new_time_ref = datetime.now()
        old_time_ref = self.time_reference

        # measure handler will update its time when it gets
        # measure_time_ack from control node
        self.measure_handler.set_time_ref(new_time_ref)

        ret = protocol.reset_time(self.sender, 'reset_time')

        if ret == 0:
            self.time_reference = new_time_ref
            if old_time_ref is None:
                LOGGER.info('Start experiment time = %r', self.time_reference)
            else:
                LOGGER.info('New time reference = %r', self.time_reference)
        else:
            LOGGER.error('Reset time failed')

        return ret


    def open_power_start(self, power=None):
        """
        Power on the open node
        """
        LOGGER.info('Open power start')

        if power is None:
            assert self.current_profile is not None
            power = self.current_profile.power


        ret = protocol.start_stop(self.sender, 'start', power)

        if ret == 0:
            self.open_node_started = True
        else:
            LOGGER.error('Open power start failed')
        return ret



    def open_power_stop(self, power=None):
        """
        Power off the open node
        """
        LOGGER.info('Open power stop')
        ret = 0

        if power is None:
            assert self.current_profile is not None
            power = self.current_profile.power

        ret = protocol.start_stop(self.sender, 'stop', power)

        if ret == 0:
            self.open_node_started = False
        else:
            LOGGER.error('Open power stop failed')
        return ret



    @staticmethod
    def node_soft_reset(node):
        """
        Reset the given node using reset pin
        :param node: Node name in {'gwt', 'm3'}
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.info('Node %s reset', node)

        ret, _out, _err = reset.reset(node)

        if ret != 0:
            LOGGER.error('Node %s reset failed: %d', node, ret)

        return ret


    @staticmethod
    def node_flash(node, firmware_path):
        """
        Flash the given firmware on the given node
        :param node: Node name in {'gwt', 'm3'}
        """
        assert node in ['gwt', 'm3'], "Invalid node name"
        LOGGER.info('Flash firmware on %s: %s', node, firmware_path)

        ret, _out, _err = flash_firmware.flash(node, firmware_path)

        if ret != 0:
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
            def_profile = gateway_code.profile.profile_from_dict(profile_dict)
        return def_profile


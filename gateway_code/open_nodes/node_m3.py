# -*- coding:utf-8 -*-
""" Open Node M3 experiment implementation """

from gateway_code.config import static_path
from gateway_code import common
from gateway_code.common import logger_call

from gateway_code.utils.ftdi_check import ftdi_check
from gateway_code.utils.openocd import OpenOCD
from gateway_code.utils.serial_redirection import SerialRedirection

import logging
LOGGER = logging.getLogger('gateway_code')


class NodeM3(object):
    """ Open node M3 implemenation """

    TYPE = 'm3'
    TTY = '/dev/ttyON_M3'
    BAUDRATE = 500000
    OPENOCD_CFG_FILE = static_path('iot-lab-m3.cfg')
    FW_IDLE = static_path('idle_m3.elf')
    FW_AUTOTEST = static_path('m3_autotest.elf')
    ALIM = '3.3V'
    AUTOTEST_AVAILABLE = [
        'echo', 'get_time',  # mandatory
        'get_uid',
        'get_pressure', 'get_light', 'test_flash',
        'get_accelero', 'get_gyro', 'get_magneto',
        'test_gpio', 'test_i2c',
        'radio_pkt', 'radio_ping_pong',
        'leds_consumption',
        'leds_on', 'leds_off', 'leds_blink',
    ]

    def __init__(self):
        self.serial_redirection = SerialRedirection(self.TTY, self.BAUDRATE)
        self.openocd = OpenOCD(self.OPENOCD_CFG_FILE)

    @logger_call("Node M3 : Setup of m3 node")
    def setup(self, firmware_path):
        """ Flash open node, create serial redirection """
        ret_val = 0

        common.wait_no_tty(self.TTY, timeout=0)
        ret_val += common.wait_tty(self.TTY, LOGGER, timeout=0)
        ret_val += self.flash(firmware_path)
        ret_val += self.serial_redirection.start()
        return ret_val

    @logger_call("Node M3 : teardown of m3 node")
    def teardown(self):
        """ Stop serial redirection and flash idle firmware """
        ret_val = 0
        common.wait_no_tty(self.TTY, timeout=0)
        ret_val += common.wait_tty(self.TTY, LOGGER, timeout=0)
        # cleanup debugger before flashing
        ret_val += self.debug_stop()
        ret_val += self.serial_redirection.stop()
        ret_val += self.flash(None)
        return ret_val

    @logger_call("Node M3 : flash of m3 node")
    def flash(self, firmware_path=None):
        """ Flash the given firmware on M3 node

        :param firmware_path: Path to the firmware to be flashed on `node`.
                              If None, flash 'idle' firmware.
        """
        firmware_path = firmware_path or self.FW_IDLE
        LOGGER.info('Flash firmware on M3: %s', firmware_path)
        return self.openocd.flash(firmware_path)

    @logger_call("Node M3 : reset of m3 node")
    def reset(self):
        """ Reset the M3 node using jtag """
        LOGGER.info('Reset M3 node')
        return self.openocd.reset()

    def debug_start(self):
        """ Start M3 node debugger """
        LOGGER.info('M3 Node debugger start')
        return self.openocd.debug_start()

    def debug_stop(self):
        """ Stop M3 node debugger """
        LOGGER.info('M3 Node debugger stop')
        return self.openocd.debug_stop()

    @staticmethod
    def status():
        """ Check M3 node status """
        return ftdi_check('m3', '2232')

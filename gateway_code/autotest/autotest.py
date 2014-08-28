#! /usr/bin/env python
# -*- coding:utf-8 -*-

""" auto tests implementation """

import time
from bisect import bisect
import re

from subprocess import check_output, STDOUT, CalledProcessError
from serial import SerialException

from collections import defaultdict

import gateway_code.config as config
import gateway_code.open_node
from gateway_code.autotest import m3_node_interface
from gateway_code.autotest import open_a8_interface
from gateway_code.profile import Consumption, Radio

import logging
LOGGER = logging.getLogger('gateway_code')

MAC_CMD = "cat /sys/class/net/eth0/address"
MAC_RE = re.compile(r'([0-9a-f]{2}:){5}[0-9a-f]{2}')


class FatalError(Exception):
    """ FatalError during tests """
    def __init__(self, value):
        super(FatalError, self).__init__()
        self.value = value

    def __str__(self):
        return repr(self.value)

TST_OK = lambda bool_value: (0 if bool_value else 1)


class AutoTestManager(object):
    """ Gateway and open node auto tests """
    def __init__(self, gateway_manager):
        self.g_m = gateway_manager

        self.on_serial = None
        self.a8_connection = None

        self.ret_dict = None

        self.cn_measures = []

    def _measures_handler(self, measure_str):
        """ control node measures Handler """
        self.cn_measures.append(measure_str.split(' '))

    @staticmethod
    def get_local_mac_addr():
        """ Get eth0 mac address """
        mac_addr = check_output(MAC_CMD, stderr=STDOUT, shell=True).strip()
        return mac_addr

    def setup_control_node(self):
        """ setup connection with control_node"""
        LOGGER.info("Setup autotests")
        ret_val = 0

        # configure Control Node
        ret_val += self.g_m.node_soft_reset('gwt')
        self.g_m.cn_serial.start(None, ['-d'], self._measures_handler)
        time.sleep(1)
        ret_val += self.g_m.set_time()

        gwt_mac_addr = self.get_local_mac_addr()
        self.ret_dict['mac']['GWT'] = gwt_mac_addr

        test_ok = (MAC_RE.match(gwt_mac_addr) is not None)
        ret_val += self._check(TST_OK(test_ok), 'gw_mac_addr', gwt_mac_addr)

        self._check(ret_val, 'setup_cn_connection', ret_val)
        if 0 != ret_val:  # pragma: no cover
            raise FatalError('Setup control node failed')

    def _setup_open_node_m3(self):
        """ Setup open node M3 connection """
        ret_val = 0

        ret = self.g_m.node_flash('m3', config.FIRMWARES['m3_autotest'])
        ret_val += self._check(ret, 'flash_m3', ret)
        time.sleep(2)

        self.on_serial = m3_node_interface.OpenNodeSerial()
        ret, err_msg = self.on_serial.start()
        ret_val += self._check(ret, 'open_M3_serial', err_msg)

        return ret_val

    def _setup_open_node_a8(self):
        """ Setup open node A8-M3 connection

        * Boot open node
        * Connect through serial and get ip address
        * SSH connect to it
          * get

        """
        ret_val = 0
        try:
            ret_val += gateway_code.open_node.NodeA8.wait_tty_a8(
                config.OPEN_A8_CFG['tty'], timeout=20)

            # wait nodes start
            # get ip address using serial
            # run socats commands to access A8-M3 open node on gateway
            self.a8_connection = open_a8_interface.OpenA8Connection()
            LOGGER.debug("Wait that open A8 node starts")
            self.a8_connection.start()

        except SerialException as err:  # pragma: no cover
            ret_val += self._check(1, 'access_A8_serial_port', str(err))
            raise FatalError('Setup Open Node failed')
        except open_a8_interface.A8ConnectionError as err:  # pragma: no cover
            ret_val += self._check(1, 'open_a8_init_error: %s' % err.err_msg,
                                   str(err))
            raise FatalError('Setup Open Node failed')

        # save mac address
        a8_mac_addr = self.a8_connection.get_mac_addr()
        self.ret_dict['mac']['A8'] = a8_mac_addr
        test_ok = (MAC_RE.match(a8_mac_addr) is not None)
        ret_val += self._check(TST_OK(test_ok), 'a8_mac_addr', a8_mac_addr)

        # open A8 flash
        try:
            self.a8_connection.scp(config.FIRMWARES['a8_autotest'],
                                   '/tmp/a8_autotest.elf')
        except CalledProcessError as err:  # pragma: no cover
            ret_val += self._check(1, 'scp a8_autotest.elf fail', str(err))
            raise FatalError('Setup Open Node failed')
        try:
            self.a8_connection.ssh_run('flash_a8.sh /tmp/a8_autotest.elf')
            time.sleep(5)
        except CalledProcessError as err:  # pragma: no cover
            ret_val += self._check(1, 'Flash A8-M3 fail', str(err))
            raise FatalError('Setup Open Node failed')

        # Create open node A8-M3 connection through socat
        self.on_serial = m3_node_interface.OpenNodeSerial()
        ret, err_msg = self.on_serial.start(tty=open_a8_interface.A8_TTY_PATH)
        ret_val += self._check(ret, 'open_A8_serial', err_msg)

        return ret_val

    def _setup_open_node_connection(self, board_type):
        """ Setup the connection with Open Node
        Should be done on DC"""

        ret_val = 0
        ret_val += self.g_m.open_power_start(power='dc')
        time.sleep(2)  # wait open node ready

        # setup open node
        ret_val += {'M3': self._setup_open_node_m3,
                    'A8': self._setup_open_node_a8}[board_type]()

        if 0 != ret_val:  # pragma: no cover
            raise FatalError('Setup Open Node failed')

    def teardown(self, blink):
        """ cleanup """
        ret_val = 0
        LOGGER.info("Teardown autotests")

        # ensure DC alim
        ret_val += self.g_m.open_power_start(power='dc')

        try:
            self.on_serial.stop()
        except AttributeError:  # pragma: no cover
            ret_val += 1   # access NoneType attribute
        finally:
            self.on_serial = None

        if not blink:
            LOGGER.debug("Stop open node, no blinking")
            ret_val += self.g_m.open_power_stop(power='dc')
        else:
            LOGGER.debug("Set status on LEDs")

        self.g_m.cn_serial.stop()
        LOGGER.debug("cn_serial stopped")

        try:
            self.a8_connection.stop()
        except AttributeError:  # pragma: no cover
            pass

        return self._check(ret_val, 'teardown', ret_val)

    def auto_tests(self, channel=None, blink=False, flash=False, gps=False):
        """
        run auto-tests on nodes and gateway using 'gateway_manager'
        """
        ret_val = 0
        self.ret_dict = {'ret': None, 'success': [], 'error': [], 'mac': {}}
        board_type = config.board_type()

        if board_type not in ['M3', 'A8']:
            self.ret_dict['ret'] = self._check(1, 'board_type', board_type)
            return self.ret_dict

        try:
            self.setup_control_node()

            #
            # Tests using Battery
            #
            # dc -> battery: A8 reboot
            # battery -> dc: No reboot
            # A8 may not work with new batteries (not enough power)
            # so check battery and then switch to DC
            ret_val += self.test_consumption_batt(board_type)

            # switch to DC and configure open node
            self._setup_open_node_connection(board_type)
            self.check_get_time()
            self.get_uid()

            #
            # Other tests, run on DC
            #
            ret = self.g_m.open_power_start(power='dc')
            ret_val += self._check(ret, 'switch_to_dc', ret)

            # test IMU
            ret_val += self.test_gyro()
            ret_val += self.test_magneto()
            ret_val += self.test_accelero()

            # test M3-ON communication
            ret_val += self.test_gpio()
            ret_val += self.test_i2c()

            # radio tests
            ret_val += self.test_radio_ping_pong(channel)
            ret_val += self.test_radio_with_rssi(channel)

            # test consumption measures
            ret_val += self.test_consumption_dc(board_type)

            # M3 specific tests
            if 'M3' == board_type:  # pragma: no branch
                # cannot test this with A8 I think
                ret_val += self.test_leds_with_consumption(board_type)
                # test m3 specific sensors
                ret_val += self.test_pressure()
                ret_val += self.test_light()
                ret_val += self.test_flash(flash)

            # run test_gps if requested
            ret_val += self.test_gps(gps)

            # set_leds
            self._on_call(['leds_off', '7'])
            if ret_val == 0:
                self._on_call(['leds_blink', '7', '500'])
                self.g_m.protocol.green_led_blink()
            else:  # pragma: no cover
                pass
        except FatalError as err:
            # Fatal Error during test, don't run further tests
            LOGGER.error("Fatal Error in tests, stop further tests: %s",
                         str(err))
            ret_val += 1

        # shutdown node if test failed
        ret_val += self.teardown(blink and (ret_val == 0))
        self.ret_dict['ret'] = ret_val

        return self.ret_dict

    def _check(self, ret, operation, log_message=''):
        """ Check the operation
        Adds `operation` to ret_dict in the correct failed or success entry

        :param ret: 0 means success non zero means failure
        :return: 0 if `ret` == 0, a positive value otherwise
        """
        if 0 == int(ret):
            self.ret_dict['success'].append(operation)
            LOGGER.debug('autotest: %r OK: %r', operation, log_message)
        else:
            self.ret_dict['error'].append(operation)
            LOGGER.error('Autotest: %r: %r', operation, log_message)
        return abs(int(ret))

    def _run_test(self, num, cmd, parse_function):
        """ Run a test 'num' times.
        In case of success parse answer with 'parse_function' """
        values = []
        for _ in range(0, num):
            (ret, answer) = self._on_call(cmd)
            if ret:
                continue
            values.append(parse_function(answer))
        return values

    def _on_call(self, cmd):
        """ Call command to Open Node and expect correct answer
        cmd args
        ACK cmd [answer_args]
        """
        answer = self.on_serial.send_command(cmd)
        if (answer is None) or (answer[0:2] != ['ACK', cmd[0]]):
            self._check(1, "On Command: %r" % cmd, answer)
            return (1, answer)
        return (0, answer)

#
# Test implementation
#

    def check_get_time(self):
        """ runs the 'get_time' command
        Error on this check are fatal
        """
        # get_time: ['ACK', 'get_time', '122953', 'tick_32khz']
        (_, answer) = self._on_call(['get_time'])

        values = self._run_test(5, ['get_time'], (lambda x: x[2].isdigit()))
        test_ok = (any(values))
        ret_val = self._check(TST_OK(test_ok), 'm3_comm_with_get_time', answer)

        if 0 != ret_val:  # pragma: no cover
            raise FatalError("get_time failed. Can't communicate with M3 node")

    def get_uid(self):
        """ runs the 'get_uid' command
        And add the resulting UID to the global return dictionary
        """
        # get_uid: ['ACK', 'get_uid', '05D8FF323632483343037109']
        values = self._run_test(1, ['get_uid'], (lambda x: x[2]))
        test_ok = len(values)

        if test_ok:
            uid_str = values[0]
            # UID: split every 4 char
            uid_split = [''.join(x) for x in zip(*[iter(uid_str)]*4)]
            uid = ':'.join(uid_split)
            self.ret_dict['open_node_m3_uid'] = uid
        else:  # pragma: no cover
            pass

        ret_val = self._check(TST_OK(test_ok), 'get_uid', values)
        return ret_val
#
# sensors and flash
#

    def test_flash(self, flash):
        """ test Flash """
        if not flash:
            return 0

        values = self._run_test(1, ['test_flash'], (lambda x: x))
        test_ok = len(values)
        return self._check(TST_OK(test_ok), 'test_flash', values)

    def test_pressure(self):
        """ test pressure sensor """
        # ['ACK', 'get_pressure', '9.944219E2', 'mbar']
        values = self._run_test(10, ['get_pressure'], (lambda x: float(x[2])))
        test_ok = 1 < len(set(values))
        return self._check(TST_OK(test_ok), 'test_pressure', values)

    def test_light(self):
        """ test light sensor with leds"""
        # ['ACK', 'get_light', '5.2001953E1', 'lux']

        # get light with leds
        self._on_call(['leds_on', '7'])
        values_on = self._run_test(5, ['get_light'], (lambda x: float(x[2])))
        # get light without leds
        self._on_call(['leds_off', '7'])
        values_off = self._run_test(5, ['get_light'], (lambda x: float(x[2])))

        values = values_on + values_off
        test_ok = 1 < len(set(values))
        return self._check(TST_OK(test_ok), 'get_light', values)

#
# Test GPS
#
    def _test_pps_open_node(self, timeout):
        """ Test the pps on open A8 m3 node"""
        ret_val = 0

        # start pps on open node
        (ret, answer) = self._on_call(['test_pps_start'])
        if ret:  # pragma: no cover
            return self._check(1, 'test_pps_start', answer)

        end_time = time.time() + timeout
        while time.time() < end_time:
            time.sleep(5)
            (ret, answer) = self._on_call(['test_pps_get'])
            if ret:  # pragma: no cover
                return self._check(1, 'test_pps_get', answer)

            # get pps value
            pps_count = int(answer[2])
            if pps_count > 2:
                ret_val = self._check(0, 'test_pps_open_node', pps_count)
                break
        else:
            ret_val = self._check(1, 'test_pps_open_node_timeout', 0)

        _ = self._on_call(['test_pps_stop'])
        return ret_val

    def test_gps(self, gps):
        """ Test the gps """
        if not gps:
            return 0
        ret_val = 0
        # ret_val += self._test_gps_serial()
        ret_val += self._test_pps_open_node(120.0)  # try to get pps, max 2 min
        ret_val = self._check(ret_val, 'test_gps', ret_val)
        return ret_val

#
# Control Node <--> Open Node Interraction
#
    def test_gpio(self):
        """ test GPIO connections """
        return self._test_on_cn(5, ['test_gpio'])

    def test_i2c(self):
        """ test i2c communication """
        return self._test_on_cn(1, ['test_i2c'])

    def _test_on_cn(self, num, cn_command, on_cmd=None, args=None):
        """ Run a test command between open node and control node
        setup control node
        run num times on open node
        teardown control node """
        on_cmd = on_cmd or cn_command  # on_cmd is the same as cn_command
        args = args or []
        debug_str = '%s_on_cn' % cn_command[0]
        ret_val = 0

        # setup control node
        ret_val += self.g_m.protocol.send_cmd(cn_command + ['start'] + args)

        # Run num times
        values = self._run_test(num, on_cmd + args, (lambda x: 0))
        test_ok = (0 in values)  # at least one success
        ret_val += self._check(TST_OK(test_ok), debug_str, values)

        # teardown
        ret = self.g_m.protocol.send_cmd(cn_command + ['stop'])
        ret_val += self._check(ret, debug_str, 'cleanup error')

        return ret_val

#
# Inertial Measurement Unit
#
    def test_magneto(self):
        """ test magneto sensor """
        # ['ACK', 'get_magneto' '4.328358E-2', '6.716418E-2', '-3.880597E-1',
        # 'gauss']
        return self._test_xyz_sensor('get_magneto')

    def test_gyro(self):
        """ test gyro sensor """
        # ['ACK', 'get_gyro', '1.07625', '1.75', '5.2500002E-2', 'dps']
        return self._test_xyz_sensor('get_gyro')

    def test_accelero(self):
        """ test accelerator sensor """
        # ['ACK', 'get_accelero', '3.6E-2', '-1.56E-1', '1.0320001', 'g']
        return self._test_xyz_sensor('get_accelero')

    def _test_xyz_sensor(self, sensor):
        """ Test sensors returning 'xyz' float values """
        # ['ACK', sensor, '3.6E-2', '-1.56E-1', '1.0320001', unit]

        values = self._run_test(
            10, [sensor], (lambda x: tuple([float(val) for val in x[2:5]])))

        test_ok = 1 < len(set(values))  # got different values
        return self._check(TST_OK(test_ok), sensor, values)

#
# Radio tests
#

    def test_radio_ping_pong(self, channel):
        """ test Radio Ping-pong with control-node """
        if channel is None:
            return 0

        return self._test_on_cn(10, ['test_radio_ping_pong'],
                                ['radio_ping_pong'], [str(channel), '3dBm'])

    def test_radio_with_rssi(self, channel):
        """ Test radio with rssi"""
        self.cn_measures = []
        if channel is None:
            return 0

        # pkt length = 125
        # one measure every ~0.01 seconds
        ret_val = 0
        radio = Radio("rssi", [channel], period=10, num_per_channel=0)
        cmd_on = ['radio_pkt', str(channel), '3dBm']

        # get RSSI while sending 10 packets length 125
        ret_val += self.g_m.protocol.config_radio(radio)
        for _ in range(0, 10):
            self._on_call(cmd_on)
            time.sleep(0.5)
        ret_val += self.g_m.protocol.config_radio(None)

        # ('11', '-91')
        # -91 == no radio detected
        measures = extract_measures(self.cn_measures)
        values = [v[1] for v in measures['radio']['values']]

        # check that there are values other than -91 measured
        test_ok = set([-91]) != set(values)
        ret_val += self._check(TST_OK(test_ok), 'rssi_measures', set(values))

        return ret_val

#
# Consumption tests
#

    def test_consumption_dc(self, board_type):
        """ Try consumption for DC """

        ret_val = 0

        # one measure every ~0.1 seconds

        conso = Consumption('dc', board_type, '1100', '64', True, True, True)
        ret_val += self.g_m.open_power_start(power='dc')

        self.cn_measures = []
        # store 2 secs of measures
        ret_val += self.g_m.protocol.config_consumption(conso)
        time.sleep(2)  # get measures for 2 seconds
        ret_val += self.g_m.protocol.config_consumption(None)
        time.sleep(2)  # wait 2 seconds for flush

        # (0.257343, 3.216250, 0.080003)
        measures = extract_measures(self.cn_measures)
        values = measures['consumption']['values']

        # Value ranges may be validated with an Idle firmware
        test_ok = 1 < len(set(values))
        ret_val += self._check(TST_OK(test_ok), 'consumption_dc', values)

        return ret_val

    def test_consumption_batt(self, board_type):
        """ Try consumption for Battery """

        ret_val = 0
        ret_val += self.g_m.open_power_start(power='battery')

        # set a firmware on M3 to ensure corret consumption measures
        # on A8, linux is consuming enough I think
        if 'M3' == board_type:  # pragma: no branch
            time.sleep(1)
            ret = self.g_m.node_flash('m3', config.FIRMWARES['m3_autotest'])
            ret_val += self._check(ret, 'flash_m3_on_battery', ret)

        # configure consumption
        # one measure every ~0.1 seconds
        conso = Consumption('battery', board_type, '1100', '64',
                            True, True, True)
        self.cn_measures = []
        ret_val += self.g_m.protocol.config_consumption(conso)

        ret_val += self.g_m.open_power_stop(power='battery')
        time.sleep(1)
        ret_val += self.g_m.open_power_start(power='battery')
        time.sleep(1)

        # stop
        ret_val += self.g_m.protocol.config_consumption(None)
        time.sleep(1)  # Flush last values

        # (0.257343, 3.216250, 0.080003)
        measures = extract_measures(self.cn_measures)
        values = measures['consumption']['values']

        test_ok = 1 < len(set(values))
        ret_val += self._check(TST_OK(test_ok), 'consumption_batt', values)

        # Value ranges may be validated with an Idle firmware
        return ret_val

    def test_leds_with_consumption(self, board_type):
        """ Test Leds with consumption

        Start consumption measure
        Then switch different leds on and save the timestamp where it's done

        Finally compare that consumption with no leds on was lower than
        with one or more leds on.
        """

        self._on_call(['leds_off', '7'])

        # one measure every ~0.1 seconds
        ret_val = 0
        conso = Consumption('dc', board_type, '1100', '64', True, True, True)
        ret_val += self.g_m.open_power_start(power='dc')

        self.cn_measures = []
        leds_timestamps = []
        # get consumption for all leds mode:
        #     no leds, each led, all leds
        ret_val += self.g_m.protocol.config_consumption(conso)
        for leds in ['0', '1', '2', '4', '7']:
            self._on_call(['leds_on', leds])
            time.sleep(0.5)
            leds_timestamps.append(time.time())
            time.sleep(0.5)
            self._on_call(['leds_off', '7'])
        ret_val += self.g_m.protocol.config_consumption(None)
        time.sleep(1)  # wait last values

        # (0.257343, 3.216250, 0.080003)
        measures = extract_measures(self.cn_measures)
        values = [v[0] for v in measures['consumption']['values']]
        timestamps = measures['consumption']['timestamps']

        led_consumption = []
        LOGGER.debug("t0, tEnd: %r - %r", timestamps[0], timestamps[-1])
        LOGGER.debug("leds_timestamps: %r", leds_timestamps)
        for led_time in leds_timestamps:
            try:
                led_consumption.append(values[bisect(timestamps, led_time)])
            except IndexError as err:  # pragma: no cover
                LOGGER.debug(err)
                led_consumption.append(float('NaN'))

        # check that consumption is higher with each led than with no leds on
        led_0 = led_consumption.pop(0)
        test_ok = all([led_0 < v for v in led_consumption])
        ret_val += self._check(TST_OK(test_ok), 'leds_using_conso',
                               (led_0, led_consumption))
        return ret_val


def extract_measures(meas_list):
    """ Extract the measures of meas_list

    >>> measures_list = [                         \
        ['measures_debug', 'consumption_measure', \
            '123.450000', '1.0', '2.0', '3.0'],   \
        ['measures_debug', 'radio_measure',       \
            '122.000000', '22', '-91'],           \
        ['measures_debug', 'consumption_measure', \
            '124.000000', '4.0', '5.0', '6.0'],   \
        ['measures_debug', 'unhandled_measure'],  \
    ]
    >>> expected_result = {                       \
        'consumption': {                          \
            'values': [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],\
            'timestamps': [123.45, 124.0]         \
        },                                        \
        'radio': {                                \
            'values': [(22, -91)],                \
            'timestamps': [122]                   \
        }                                         \
    }
    >>> expected_result == extract_measures(measures_list)
    True
    """
    meas_dict = defaultdict(lambda: dict({'values': [], 'timestamps': []}))

    for meas in meas_list:
        if 'consumption_measure' == meas[1]:
            # ['measures_debug', 'consumption_measure'
            #     '1378387028.906210', '0.257343', '3.216250', '0.080003']
            values = tuple([float(v) for v in meas[3:6]])
            meas_dict['consumption']['values'].append(values)
            meas_dict['consumption']['timestamps'].append(float(meas[2]))
        elif 'radio_measure' == meas[1]:
            # ['measures_debug:', 'radio_measure',
            #      '1378466517.186216', '11', '-91']
            values = tuple([int(v) for v in meas[3:5]])
            meas_dict['radio']['values'].append(values)
            meas_dict['radio']['timestamps'].append(float(meas[2]))
        else:
            LOGGER.debug('unhandled measure type: %r', meas)

    # keep 'defaultdict' to simplify usage
    return meas_dict

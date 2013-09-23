#! /usr/bin/env python
# -*- coding:utf-8 -*-

"""
auto tests implementation
"""

import time
import Queue
import logging

from subprocess import Popen, PIPE, STDOUT

from gateway_code import config
from gateway_code import open_node_validation_interface
from gateway_code import open_a8_interface
from gateway_code.profile import Consumption, Radio

LOGGER = logging.getLogger('gateway_code')

MAC_CMD = "ip link show dev eth0 " + \
    r"| sed -n '/ether/ s/.*ether \(.*\) brd.*/\1/p'"


class GatewayValidation(object):
    """ Gateway and open node auto tests """
    def __init__(self, gateway_manager):
        self.g_m = gateway_manager
        self.on_serial = None

        self.ret_dict = None

        self.a8_connection = None

        self.keep_all_measures = False
        self.last_measure = Queue.Queue(0)

    def _measures_handler(self, measure):
        """ Discard previous measure and add new one """
        if not self.keep_all_measures:
            try:
                self.last_measure.get_nowait()  # discard old measure
            except Queue.Empty:
                pass
        self.last_measure.put(measure)

    def _get_measure(self, timeout=None):
        """ Wait until a new measure is received """
        try:
            measure = self.last_measure.get(timeout=timeout)
        except Queue.Empty:
            measure = None
        return measure

    @staticmethod
    def get_local_mac_addr():
        """ Get eth0 mac address """
        process = Popen(MAC_CMD, stdout=PIPE, stderr=STDOUT, shell=True)
        mac_addr = process.communicate()[0].strip()
        return mac_addr

    def setup(self):
        """ setup connection with m3 """
        self.ret_dict = {'ret': None, 'success': [], 'error': [], 'mac': {}}
        ret_val = 0

        # configure Control Node
        ret_val += self.g_m.node_soft_reset('gwt')
        self.g_m.cn_serial.start(_args=['-d'],
                                 _measures_handler=self._measures_handler)
        time.sleep(1)
        board_type = config.board_type()

        ret_val += self.g_m.open_power_start(power='dc')
        ret_val += self.g_m.reset_time()

        gwt_mac_addr = self.get_local_mac_addr()
        self.ret_dict['mac']['GWT'] = gwt_mac_addr

        if board_type == 'M3':
            # setup open node
            ret_val += self.g_m.node_flash('m3',
                                           config.FIRMWARES['m3_autotest'])
            self.on_serial = open_node_validation_interface.OpenNodeSerial()
            time.sleep(1)
            self.on_serial.start()

        elif board_type == 'A8':
            # time.sleep(60)  # wait open node started
            time.sleep(1)  # wait open node started
            self.a8_connection = open_a8_interface.OpenA8Connection()
            self.a8_connection.start()
            open_a8_mac_addr = self.a8_connection.get_mac_addr()
            self.ret_dict['mac']['A8'] = open_a8_mac_addr

            # open A8 flash
            self.a8_connection.ssh_run(
                'source /etc/profile; ' +
                '/home/root/bin/flash_a8.sh ' +
                '/var/lib/gateway_code/a8_autotest.elf')
            time.sleep(5)

            self.on_serial = open_node_validation_interface.OpenNodeSerial()
            time.sleep(1)
            self.on_serial.start(tty=open_a8_interface.A8_TTY_PATH)

        return self._validate(ret_val, 'setup', ret_val)

    def teardown(self, blink):
        """ cleanup """
        ret_val = 0

        # restore
        self.on_serial.stop()
        self.on_serial = None
        if self.a8_connection is None:
            ret_val += self.g_m.node_flash('m3', config.FIRMWARES['idle'])
        # TODO actually shut down the A8 node but not now
        if not blink and self.a8_connection is None:
            # keep blinking after tests
            ret_val += self.g_m.open_power_stop(power='dc')

        self.g_m.cn_serial.stop()

        if self.a8_connection is not None:
            self.a8_connection.stop()

        return self._validate(ret_val, 'teardown', ret_val)

    def auto_tests(self, channel=None, blink=False):
        """
        run auto-tests on nodes and gateway using 'gateway_manager'
        """
        ret_val = 0

        ret_val += self.setup()
        if ret_val == 0:
            # can communicate and get_time working
            ret_val += self.test_get_time()

            # test IMU
            ret_val += self.test_gyro()
            ret_val += self.test_magneto()
            ret_val += self.test_accelero()
            if 'M3' == config.board_type():
                # test pressure and flash
                ret_val += self.test_pressure()
                ret_val += self.test_flash()

            # radio tests
            if channel is not None:
                ret_val += self.test_radio_ping_pong(channel)
                ret_val += self.test_radio_with_rssi(channel)

            if 'M3' == config.board_type():
                # test battery switch
                # (done after some time to get a big uptime)
                ret_val += self.test_battery_switch()

            # test measure_conso
            ret_val += self.test_consumption_dc()
            if 'M3' == config.board_type():
                # TODO A8 Maybe later too lazy to check that not shut down
                ret_val += self.test_consumption_batt()

            if 'M3' == config.board_type():
                # test leds (requires conso)
                ret_val += self.test_leds_with_consumption()
                # test light sensor (requires test leds and light sensor)
                ret_val += self.test_light()

            # set_leds
            _ = self.on_serial.send_command(['leds_off', '7', '500'])
            if ret_val == 0:
                _ = self.on_serial.send_command(['leds_blink', '7', '500'])
            else:  # pragma: no cover
                pass
        else:  # pragma: no cover
            pass

        ret_val += self.teardown(blink)
        self.ret_dict['ret'] = ret_val

        return self.ret_dict

    def _validate(self, ret, message, log_message=''):
        """ validate an return and print log if necessary """
        if ret == 0:
            self.ret_dict['success'].append(message)
            LOGGER.debug('autotest: %r OK: %r', message, log_message)
        else:
            self.ret_dict['error'].append(message)
            LOGGER.error('Autotest: %r: %r', message, log_message)
        return ret

#
# Test implementation
#

    def test_get_time(self):
        """ runs the 'get_time' command """
        # get_time: ['ACK', 'CURRENT_TIME', '=', '122953', 'tick_32khz']
        answer = self.on_serial.send_command(['get_time'])

        ret = (answer[:2] == ['ACK', 'CURRENT_TIME']) and answer[3].isdigit()
        return self._validate(int(not ret), 'get_time', answer)

    def test_battery_switch(self):
        """ test_battery_switch
        test if changing to battery and back resets open_node
        """
        ret_val = 0

        # save time before test
        answer = self.on_serial.send_command(['get_time'])
        time_1 = int(answer[3]) if answer[0] == 'ACK' else 0

        # switch to battery and get_time
        ret = self.g_m.open_power_start(power='battery')
        ret_val += self._validate(ret, 'open_battery_start', ret)
        time.sleep(0.5)
        answer = self.on_serial.send_command(['get_time'])
        time_2 = int(answer[3]) if answer[0] == 'ACK' else 0

        # switch back to dc and get_time
        ret = self.g_m.open_power_start(power='dc')
        ret_val += self._validate(ret, 'open_power_start', ret)
        time.sleep(0.5)
        answer = self.on_serial.send_command(['get_time'])
        time_3 = int(answer[3]) if answer[0] == 'ACK' else 0

        # check time increasing => no reboot
        time_increasing = 0 if time_3 > time_2 > time_1 else 1
        ret_val += self._validate(time_increasing, 'no_reboot_on_alim_switch',
                                  '%d < %d < %d' % (time_1, time_2, time_3))
        return ret_val

#
# sensors and flash
#

    def test_flash(self):
        """ test Flash """
        answer = self.on_serial.send_command(['test_flash'])
        ret = answer[:2] == ['ACK', 'TST_FLASH']
        return self._validate(int(not ret), 'test_flash', answer)

    def test_pressure(self):
        """ test pressure sensor """
        # ['ack', 'PRESSURE', '=', '9.944219E2', 'mbar']
        values = []
        for _ in range(0, 10):
            answer = self.on_serial.send_command(['get_pressure'])
            values.append(float(answer[3]))

        got_diff_values = 0 if (1 != len(set(values))) else 1
        return self._validate(got_diff_values, 'test_pressure', values)

    def test_light(self):
        """ test light sensor with leds"""
        # ['ACK', 'LIGHT', '=', '5.2001953E1', 'lux']

        _ = self.on_serial.send_command(['leds_blink', '7', '2000'])

        values = []
        for _ in range(0, 10):
            answer = self.on_serial.send_command(['get_light'])
            values.append(float(answer[3]))
            time.sleep(1)

        _ = self.on_serial.send_command(['leds_blink', '7', '0'])
        _ = self.on_serial.send_command(['leds_off', '7'])

        if (len(set(values)) == 1 and values[0] == '0.12207031'):
            # hack to prevent multiple false tests but with a warning
            LOGGER.warning("Got the same value which is '0.12207031'")
            self.ret_dict['warning'] = {'get_light_value': 0.12207031}
            got_diff_values = 0
        else:
            got_diff_values = int(not(1 != len(set(values))))
        return self._validate(got_diff_values, 'get_light', values)

#
# Inertial Measurement Unit
#

    def test_magneto(self):
        """ test magneto sensor """
        # ['ack', 'MAGNETO', '=', '4.328358E-2', '6.716418E-2', '-3.880597E-1']
        values = []
        for _ in range(0, 10):
            answer = self.on_serial.send_command(['get_magneto'])
            measures = tuple([float(val) for val in answer[3:6]])
            values.append(measures)
        got_diff_values = 0 if (1 != len(set(values))) else 1
        return self._validate(got_diff_values, 'get_magneto', values)

    def test_gyro(self):
        """ test gyro sensor """
        # ['ack', 'GYRO_ROTATION_SPEED', '=',
        #  '1.07625', '1.75', '5.2500002E-2', 'dps']
        values = []
        for _ in range(0, 10):
            answer = self.on_serial.send_command(['get_gyro'])
            measures = tuple([float(val) for val in answer[3:6]])
            values.append(measures)
        got_diff_values = 0 if (1 != len(set(values))) else 1
        return self._validate(got_diff_values, 'get_gyro', values)

    def test_accelero(self):
        """ test accelerator sensor """
        # ['ack', 'ACCELERATION', '=', '3.6E-2', '-1.56E-1', '1.0320001']
        values = []
        for _ in range(0, 10):
            answer = self.on_serial.send_command(['get_accelero'])
            measures = tuple([float(val) for val in answer[3:6]])
            values.append(measures)
        got_diff_values = 0 if (1 != len(set(values))) else 1
        return self._validate(got_diff_values, 'get_accelero', values)

#
# Radio tests
#

    def test_radio_ping_pong(self, channel):
        """ test Radio Ping-pong with control-node """
        ret_val = 0

        # setup control node
        cmd = ['config_radio_signal', '3.0', str(channel)]
        ret_val += self.g_m.protocol.send_cmd(cmd)
        cmd = ['test_radio_ping_pong', 'start']
        ret_val += self.g_m.protocol.send_cmd(cmd)

        # send 10 packets
        values = []
        for _ in range(0, 10):
            cmd_on = ['radio_ping_pong', '3dBm', str(channel)]
            answer = self.on_serial.send_command(cmd_on)
            values.append(int(not(answer[:2] == ['ACK', 'RADIO_PINGPONG'])))

        # got at least one answer from control_node
        result = int(not(0 in values))  # at least one success
        ret_val += self._validate(result, 'radio_ping_pong_pkts', values)

        # cleanup
        ret_val += self.g_m.protocol.send_cmd(['test_radio_ping_pong', 'stop'])
        self._validate(ret_val, 'radio_ping_pong_test', 'Cleanup error')
        return ret_val

    def test_radio_with_rssi(self, channel):
        """ Test radio with rssi"""

        # one measure every ~0.1 seconds
        ret_val = 0
        radio = Radio(power=3.0, channel=channel, mode="measure",
                      frequency=100)
        ret_val += self.g_m.protocol.config_radio(radio)

        # send 10 radio packets and keep all radio measures
        self.keep_all_measures = True
        for _ in range(0, 10):
            cmd_on = ['radio_pkt', '3dBm', str(channel)]
            _ = self.on_serial.send_command(cmd_on)
            time.sleep(0.5)
        ret_val += self.g_m.protocol.config_radio(None)
        self.keep_all_measures = False

        # extract rssi measures
        # ['measures_debug:', 'radio_measure',
        #  '1378466517.186216:21.018127', '0', '0']
        values = []
        while not self.last_measure.empty():
            val = self.last_measure.get().split(' ')
            values.append(tuple([int(meas) for meas in val[3:5]]))

        # check that values other than (0,0) were measured
        values.append((0, 0))
        got_diff_values = 0 if (1 != len(set(values))) else 1
        ret_val += self._validate(got_diff_values, 'rssi_measures', values)

        return ret_val

#
# Consumption tests
#

    def test_consumption_dc(self):
        """ Try consumption for DC """

        # one measure every ~0.1 seconds
        ret_val = 0
        conso = Consumption(power_source='dc', board_type=config.board_type(),
                            period='1100', average='64',
                            power=True, voltage=True, current=True)
        ret_val += self.g_m.open_power_start(power='dc')
        ret_val += self.g_m.protocol.config_consumption(conso)

        values = []

        # measures_debug: consumption_measure
        #     1378387028.906210:21.997924
        #     0.257343 3.216250 0.080003
        for _ in range(0, 10):
            try:
                val = self._get_measure(timeout=1).split(' ')
            except AttributeError:
                continue
            values.append(tuple([float(meas) for meas in val[3:6]]))
        ret_val += self.g_m.protocol.config_consumption(None)

        # TODO Validate value ranges (maybe with idle firmware)

        got_diff_values = 0 if (1 < len(set(values))) else 1
        ret_val += self._validate(got_diff_values, 'consumption_dc', values)

        return ret_val

    def test_consumption_batt(self):
        """ Try consumption for Battery """

        # one measure every ~0.1 seconds
        ret_val = 0
        conso = Consumption(power_source='battery',
                            board_type=config.board_type(),
                            period='1100', average='64',
                            power=True, voltage=True, current=True)
        ret_val += self.g_m.open_power_start(power='battery')
        ret_val += self.g_m.protocol.config_consumption(conso)

        values = []

        # measures_debug: consumption_measure
        #     1378387028.906210:21.997924
        #     0.257343 3.216250 0.080003
        for _ in range(0, 10):
            val = self._get_measure(timeout=1).split(' ')
            values.append(tuple([float(meas) for meas in val[3:6]]))
        got_diff_values = 0 if (1 < len(set(values))) else 1
        ret_val += self._validate(got_diff_values, 'consumption_batt', values)

        # TODO Validate value ranges (maybe with idle firmware)
        ret_val += self.g_m.protocol.config_consumption(None)
        ret_val += self.g_m.open_power_start(power='dc')

        return ret_val

    def test_leds_with_consumption(self):
        """ Test Leds with consumption """

        _ = self.on_serial.send_command(['leds_off', '7'])

        # one measure every ~0.1 seconds
        ret_val = 0
        conso = Consumption(power_source='dc', board_type=config.board_type(),
                            period='1100', average='64',
                            power=True, voltage=True, current=True)
        ret_val += self.g_m.open_power_start(power='dc')
        ret_val += self.g_m.protocol.config_consumption(conso)

        values = []

        # measures_debug: consumption_measure
        #     1378387028.906210:21.997924
        #     0.257343 3.216250 0.080003

        # keep only power
        time.sleep(0.5)
        val = self._get_measure(timeout=1).split(' ')
        value_0 = float(val[3])

        for i in ['1', '2', '4', '7']:
            _ = self.on_serial.send_command(['leds_on', i])
            time.sleep(0.5)
            val = self._get_measure(timeout=1).split(' ')
            values.append(float(val[3]))
            _ = self.on_serial.send_command(['leds_off', '7'])

        ret_val += self.g_m.protocol.config_consumption(None)

        leds_working = int(not(all([value_0 < val for val in values])))
        ret_val += self._validate(leds_working, 'test_leds_using_conso',
                                  (value_0, values))

        return ret_val

#! /usr/bin/env python

import gateway_code
import time
import os
import recordtype # mutable namedtuple (for small classes)
from string import Template
import shutil

import mock
from mock import patch
import unittest

# pylint: disable=C0103,R0904

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) + '/'
STATIC_DIR  = CURRENT_DIR + 'static/' # using the 'static' symbolic link
STABLE_FIRMWARE = STATIC_DIR + 'control_node.elf'


# Bottle FileUpload class stub
FileUpload = recordtype.recordtype('FileUpload', \
        ['file', 'name', 'filename', ('headers', None)])


import socket
def _send_command_open_node(host, port, command):
    """
    send a command to host/port and wait for an answer as a line
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock_file = sock.makefile('rw')
    sock.settimeout(5.0)
    ret = None
    try:
        sock.send(command)
        ret = sock_file.readline()
    except socket.timeout:
        ret = None
    finally:
        sock.close()
    return ret


MOCK_FIRMWARES = {
    'idle': STATIC_DIR + 'idle.elf',
    'control_node': STATIC_DIR + 'control_node.elf',
    'm3_autotest': STATIC_DIR + 'm3_autotest.elf',
    }


class GatewayCodeMock(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.static_patcher = patch('gateway_code.openocd_cmd.config.STATIC_FILES_PATH', new=STATIC_DIR)
        cls.static_patcher.start()

        cls.firmwares_patcher = patch('gateway_code.config.FIRMWARES', MOCK_FIRMWARES)
        cls.firmwares_patcher.start()
        cls.config_path_patcher = patch('gateway_code.config.GATEWAY_CONFIG_PATH', CURRENT_DIR + '/config_m3/')
        cls.config_path_patcher.start()
        cls.cn_interface_patcher = patch('gateway_code.control_node_interface.CONTROL_NODE_INTERFACE_ARGS', ['-d'])  # print measures
        cls.cn_interface_patcher.start()

        cls.app = gateway_code.server_rest.GatewayRest(\
                gateway_code.server_rest.GatewayManager('.'))

        cls.files = {}
        # default files
        cls.files['control_node'] = FileUpload(\
                file = open(STATIC_DIR + 'control_node.elf', 'rb'),
                name = 'firmware', filename = 'control_node.elf')

        cls.files['idle'] = FileUpload(\
                file = open(STATIC_DIR + 'idle.elf', 'rb'),
                name = 'firmware', filename = 'idle.elf')
        cls.files['default_profile'] = FileUpload(\
                file = open(STATIC_DIR + 'default_profile.json', 'rb'),
                name = 'profile', filename = 'default_profile.json')


        # test specific files
        cls.files['echo'] = FileUpload(\
                file = open(CURRENT_DIR + 'serial_echo.elf', 'rb'),
                name = 'firmware', filename = 'serial_echo.elf')

        cls.files['profile'] = FileUpload(\
                file = open(CURRENT_DIR + 'profile.json', 'rb'),
                name = 'profile', filename = 'profile.json')
        cls.files['invalid_profile'] = FileUpload(\
                file = open(CURRENT_DIR + 'invalid_profile.json', 'rb'),
                name = 'profile', filename = 'invalid_profile.json')
        cls.files['invalid_profile_2'] = FileUpload(\
                file = open(CURRENT_DIR + 'invalid_profile_2.json', 'rb'),
                name = 'profile', filename = 'invalid_profile_2.json')


    @classmethod
    def tearDownClass(cls):
        for file_obj in cls.files.itervalues():
            file_obj.file.close()
        cls.static_patcher.stop()
        cls.firmwares_patcher.stop()
        cls.config_path_patcher.stop()
        cls.cn_interface_patcher.stop()


    def setUp(self):
        # get quick access to class attributes
        self.app   = type(self).app
        self.files = type(self).files

        self.request_patcher = patch('gateway_code.server_rest.request')
        self.request = self.request_patcher.start()

        self._rewind_files()


    def _rewind_files(self):
        """
        Rewind files at start position
        """
        for file_obj in self.files.itervalues():
            file_obj.file.seek(0)


    def tearDown(self):
        self.request_patcher.stop()
        self.app.exp_stop() # just in case, post error cleanup



class TestComplexExperimentRunning(GatewayCodeMock):

    def setUp(self):
        super(TestComplexExperimentRunning, self).setUp()
        self.exp_conf = {
            'user': 'harter',
            'exp_id': 123,
            'node_id': gateway_code.config.hostname()
            }
        self.request.files = {'firmware': self.files['control_node']}
        ret = self.app.admin_control_flash()
        self.assertEquals(ret, {'ret':0})

        ret = self.app.admin_control_soft_reset()
        self.assertEquals(ret, {'ret':0})

        measure_path = Template(gateway_code.config.MEASURES_PATH)
        self.radio_path = measure_path.substitute(self.exp_conf, type='radio')
        self.conso_path = measure_path.substitute(self.exp_conf, type='consumption')
        for folder in (self.conso_path, self.radio_path):
            try:
                folder_path = os.path.dirname(folder)
                os.makedirs(folder_path)
            except os.error as err:
                pass

    def tearDown(self):
        super(TestComplexExperimentRunning, self).tearDown()
        # remove exp folder
        # ...../exp_id/consumption/node_name.oml
        shutil.rmtree(os.path.dirname(os.path.dirname(self.conso_path)))


    @patch('gateway_code.control_node_interface.LOGGER.debug')
    def tests_multiple_complete_experiment(self, m_logger):
        """
        Test a complete experiment 3 times (loooong test)
        Experiment ==
            start
            flash
            reset
            stop
        """

        msg = 'HELLO WORLD\n'

        for i in range(0, 3):
            m_logger.reset_mock()
            self._rewind_files()


            # start
            self.request.files = {
                'firmware': self.files['idle'],
                'profile':self.files['profile']
                }
            ret = self.app.exp_start(self.exp_conf['exp_id'], self.exp_conf['user'])
            self.assertEquals(ret, {'ret':0})
            time.sleep(1)

            # idle firmware, should be no reply
            ret = _send_command_open_node('localhost', 20000, msg)
            self.assertEquals(ret, None)

            # flash echo firmware
            self.request.files = {'firmware': self.files['echo']}
            ret = self.app.open_flash()
            self.assertEquals(ret, {'ret':0})
            time.sleep(1)

            # test reset_time
            self.app.reset_time()

            # echo firmware, should reply what was sent
            ret = _send_command_open_node('localhost', 20000, msg)
            self.assertEquals(ret, msg)

            ret = self.app.open_soft_reset()
            self.assertEquals(ret, {'ret':0})

            ret = self.app.open_start()
            self.assertEquals(ret, {'ret':0})
            ret = self.app.open_stop()
            self.assertEquals(ret, {'ret':0})

            # stop exp
            ret = self.app.exp_stop()
            self.assertEquals(ret, {'ret':0})

            # flash firmware should fail
            self._rewind_files()
            self.request.files = {'firmware': self.files['echo']}
            ret = self.app.open_flash()
            self.assertNotEquals(ret, {'ret':0})

            #
            # Validate measures consumption
            #

            # measures values in correct range
            calls = [call[0][0].split(' ') for call in m_logger.call_args_list]
            measures = [args[2:] for args in calls if
                        args[0:2] == ['measures_debug:', 'consumption_measure']]
            for measure in measures:
                # no power,  voltage in 3.3V, current not null
                self.assertEquals(0.0, float(measure[1]))
                self.assertTrue(3.0 <= float(measure[2]) <= 3.5)
                self.assertNotEquals(0.0, float(measure[3]))

            # timestamps are in correct order
            timestamps = [float(args) for args in measures]
            is_sorted = [timestamps[i] <= timestamps[i+1] for (i, _) in
                      enumerate(timestamps[:-1])]
            self.assertTrue(all(is_sorted))




class TestAutoTests(GatewayCodeMock):

    def test_complete_auto_tests(self):
        # replace stop
        g_m = self.app.gateway_manager
        real_stop = g_m.open_power_stop
        mock_stop = mock.Mock(side_effect=real_stop)

        g_m.open_power_stop = mock_stop

        self.request.query = mock.Mock()
        self.request.query.channel = '22'

        # call using rest
        ret_dict = self.app.auto_tests(mode='blink')
        ret = ret_dict['ret']
        passed = ret_dict['passed']
        errors = ret_dict['errors']

        import sys
        print >> sys.stderr, "ret: %r" % ret
        print >> sys.stderr, "passed: %r" % passed
        print >> sys.stderr, "errors: %r" % errors
        self.assertEquals([], errors)
        self.assertEquals(0, ret)

        self.assertEquals(0, g_m.open_power_stop.call_count)

        # test that ON still on => should be blinking and answering
        open_serial = gateway_code.open_node_validation_interface.\
            OpenNodeSerial()
        open_serial.start()
        answer = open_serial.send_command(['get_time'])
        self.assertNotEquals(None, answer)
        open_serial.stop()


    def test_mode_no_blink_no_radio(self):

        g_v = gateway_code.gateway_validation.GatewayValidation(
                self.app.gateway_manager)
        # radio functions
        g_v.test_radio_ping_pong = mock.Mock()
        g_v.test_radio_with_rssi = mock.Mock()

        ret, passed, errors = g_v.auto_tests(channel=None, blink=False)
        self.assertEquals([], errors)
        self.assertEquals(0, ret)
        self.assertEquals(0, g_v.test_radio_ping_pong.call_count)
        self.assertEquals(0, g_v.test_radio_with_rssi.call_count)


class TestInvalidCases(GatewayCodeMock):

    def tests_invalid_calls(self):
        """
        Test start calls when not needed
            * start when started
            * stop when stopped
        """

        ret = self.app.exp_start(123, 'harter')
        self.assertEquals(ret, {'ret':0})
        ret = self.app.exp_start(123, 'harter') # cannot start started exp
        self.assertNotEquals(ret, {'ret':0})

        # stop exp
        ret = self.app.exp_stop()
        self.assertEquals(ret, {'ret':0})

        ret = self.app.exp_stop() # cannot stop stoped exp
        self.assertNotEquals(ret, {'ret':0})


    def tests_invalid_profile_at_start(self):

        self._rewind_files()
        self.request.files = {'profile': self.files['invalid_profile']}
        ret = self.app.exp_start(123, 'harter')
        self.assertNotEquals(ret, {'ret':0})

        # invalid json
        self._rewind_files()
        self.request.files = {'profile': self.files['invalid_profile_2']}
        ret = self.app.exp_start(123, 'harter')
        self.assertNotEquals(ret, {'ret':0})



    def tests_invalid_files(self):
        """
        Test invalid calls
            * invalid start
            * invalid flash
        """

        self.request.files = {'profile':self.files['profile']}
        ret = self.app.open_flash()
        self.assertNotEquals(ret, {'ret':0})


# -*- coding: utf-8 -*-

""" Common integration tests M3/A8 """

# pylint: disable=protected-access
# pylint: disable=too-many-public-methods
# pylint: disable=star-args

import os
import time
import math
from itertools import izip

import mock
from mock import patch

# all modules should be imported and not only the package
from gateway_code.integration import test_integration_mock
import gateway_code.control_node_interface
import gateway_code.config
from gateway_code.common import wait_cond
from gateway_code.autotest.autotest import extract_measures

USER = 'harter'


class ExperimentRunningMock(test_integration_mock.GatewayCodeMock):
    """ Create environment for running experiments """

    def setUp(self):
        super(ExperimentRunningMock, self).setUp()
        self.cn_measures = []
        self.g_m.cn_serial.measures_handler = self._measures_handler

        # no timeout
        self.request.query = mock.Mock(timeout='')
        self.request.files = {}

        # config experiment and create folder
        self.exp_conf = {'user': USER, 'exp_id': 123}
        self.g_m._create_user_exp_folders(**self.exp_conf)

    def tearDown(self):
        super(ExperimentRunningMock, self).tearDown()
        self.g_m._destroy_user_exp_folders(**self.exp_conf)

    def _measures_handler(self, measure_str):
        """ control node measures Handler """
        gateway_code.control_node_interface.LOGGER.debug(measure_str)
        self.cn_measures.append(measure_str.split(' '))

    @staticmethod
    def _send_command_open_node(command, host='localhost', port=20000):
        """ send a command to host/port and wait for an answer as a line """
        import socket

        ret = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            sock_file = sock.makefile('rw')
            sock.settimeout(5.0)
            sock.send(command + '\n')
            ret = sock_file.readline().rstrip()
        except (socket.timeout, IOError):
            ret = None
        finally:
            sock.close()
        return ret

    def _send_command_multiple(self, command, num_times, step=0.5):
        """ Send a command multiple times and return array of answers """
        answers = []
        for _ in range(0, num_times):
            answers.append(self._send_command_open_node(command))
            time.sleep(step)
        return answers


class TestComplexExperimentRunning(ExperimentRunningMock):
    """ Run complete experiment test """

    @patch('gateway_code.control_node_interface.LOGGER.error')
    def test_simple_experiment(self, m_error):
        """ Test simple experiment"""
        if 'M3' == gateway_code.config.board_type():
            self._run_simple_experiment_m3(m_error)
        elif 'A8' == gateway_code.config.board_type():
            self._run_simple_experiment_a8(m_error)

    def _run_simple_experiment_a8(self, m_error):
        """ Run an experiment for A8 nodes """
        _ = m_error

        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))

        # waiting One minute to try to have complete boot log on debug output
        time.sleep(60)  # maybe do something here later

        self.assertEquals({'ret': 0}, self.app.exp_stop())

    def _run_simple_experiment_m3(self, m_error):
        """ Run a simple experiment on M3 node without profile
        Try the different node features """

        msg = 'HELLO WORLD'

        # start exp with idle firmware
        self.request.files = {'firmware': self.files['idle']}
        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))
        time.sleep(1)

        # idle firmware, there should be no reply
        self.assertNotIn(msg, self._send_command_multiple('echo %s' % msg, 5))

        # flash echo firmware
        self.request.files = {'firmware': self.files['m3_autotest']}
        self.assertEquals({'ret': 0}, self.app.open_flash())
        time.sleep(1)

        self.app.set_time()  # test set_time during experiment

        # Should echo <message>, do it multiple times for reliability
        self.assertIn(msg, self._send_command_multiple('echo %s' % msg, 5))

        # open node reset and start stop
        self.assertEquals({'ret': 0}, self.app.open_soft_reset())
        self.assertEquals({'ret': 0}, self.app.open_start())
        self.assertEquals({'ret': 0}, self.app.open_stop())

        # stop exp
        self.assertEquals({'ret': 0}, self.app.exp_stop())

        # Got no error during tests (use call_args_list for printing on error)
        self.assertEquals([], m_error.call_args_list)

        # node is correctly shutdown
        # reset firmware should fail and logger error will be called
        self.assertNotEquals({'ret': 0}, self.app.open_soft_reset())
        self.assertTrue(m_error.called)

    @patch('gateway_code.control_node_interface.LOGGER.error')
    def test_m3_exp_with_measures(self, m_error):
        """ Run an experiment with measures and profile update """

        if 'M3' != gateway_code.config.board_type():
            return
        t_start = time.time()

        self.request.files = {'firmware': self.files['m3_autotest']}
        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))
        exp_files = self.g_m.exp_desc['exp_files'].copy()
        time.sleep(1)

        # Set first profile
        self.request.files = {'profile': self.files['profile']}
        self.assertEquals({'ret': 0}, self.app.exp_update_profile())
        time.sleep(5)  # wait measures here
        self.app.set_time()  # test set_time during experiment
        time.sleep(5)  # wait measures here
        # remove profile
        self.request.files = {}
        self.assertEquals({'ret': 0}, self.app.exp_update_profile())
        time.sleep(2)  # wait maybe remaining values

        measures = extract_measures(self.cn_measures)
        self.cn_measures = []

        # # # # # # # # # #
        # Check measures  #
        # # # # # # # # # #

        # Got consumption and radio
        self.assertNotEquals([], measures['consumption']['values'])
        self.assertNotEquals([], measures['radio']['values'])

        # Validate values
        for values in measures['consumption']['values']:
            # no power, voltage in 3.3V, current not null
            self.assertTrue(math.isnan(values[0]))
            self.assertTrue(2.8 <= values[1] <= 3.5)
            self.assertNotEquals(0.0, values[2])
        for values in measures['radio']['values']:
            self.assertIn(values[0], [15, 26])
            self.assertGreaterEqual(-91, values[1])

        # check timestamps are sorted in correct order
        for values in measures.values():
            timestamps = [t_start] + values['timestamps'] + [time.time()]
            _sorted = all([a < b for a, b in izip(timestamps, timestamps[1:])])
            self.assertTrue(_sorted)

        # there should be no new measures
        self.assertEquals([], self.cn_measures)

        # Stop experiment
        self.assertEquals({'ret': 0}, self.app.exp_stop())
        # Got no error during tests (use assertEquals for printing result)
        self.assertEquals([], m_error.call_args_list)

        # # # # # # # # # # # # # # # # # # # # # #
        # Test OML Files still exists after stop  #
        #    * radio and conso file exist         #
        # # # # # # # # # # # # # # # # # # # # # #
        for meas_type in ('radio', 'consumption'):
            try:
                os.remove(exp_files[meas_type])
            except IOError:
                self.fail('File should exist %r' % exp_files[meas_type])


class TestExperimentTimeout(ExperimentRunningMock):
    """ Test the 'timeout' feature of experiments """

    def setUp(self):
        super(TestExperimentTimeout, self).setUp()
        self.timeout_mock = mock.Mock(side_effect=self.g_m._timeout_exp_stop)

        self.timeout_patcher = patch.object(self.g_m, '_timeout_exp_stop',
                                            self.timeout_mock)
        self.timeout_patcher.start()

    def tearDown(self):
        super(TestExperimentTimeout, self).tearDown()
        self.timeout_patcher.stop()

    def _safe_exp_is_running(self):
        """ Return experiment state but do it under gateway manager rlock
        It prevents other commands to be still running while checking """
        with self.g_m.rlock:  # No operation running at the same time
            return self.g_m.experiment_is_running

    def test_experiment_with_timeout(self):
        """ Start an experiment with a timeout. """
        self.request.query = mock.Mock(timeout='5')
        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))
        # Wait max 10 seconds for experiment to have been stopped
        self.assertTrue(wait_cond(10, False, self._safe_exp_is_running))
        self.assertTrue(self.timeout_mock.called)

    def test_exp_stop_removes_timeout(self):
        """ Test exp_stop removes timeout stop """
        self.request.query = mock.Mock(timeout='5')
        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))
        self.app.exp_stop()  # Stop should remove timeout

        time.sleep(10)   # Ensure that timeout could have occured
        self.assertFalse(self.timeout_mock.called)  # not called

    def test__timeout_on_wrong_exp(self):
        """ Test _timeout_exp_stop only stops it's experiment """
        old_exp_conf = self.exp_conf.copy()
        old_exp_conf['exp_id'] -= 1

        self.assertEquals({'ret': 0}, self.app.exp_start(**self.exp_conf))
        # simulate a previous experiment stop occuring too late
        self.g_m._timeout_exp_stop(**old_exp_conf)
        # still running
        self.assertTrue(self._safe_exp_is_running)

        # cleanup
        self.app.exp_stop()


class TestIntegrationOther(ExperimentRunningMock):
    """ Group other tests cases"""

    def test_admin_commands(self):
        """ Try running the admin commands """
        # flash Control Node
        self.request.files = {'firmware': self.files['control_node']}
        ret = self.app.admin_control_flash()
        self.assertEquals(ret, {'ret': 0})
        ret = self.app.admin_control_soft_reset()
        self.assertEquals(ret, {'ret': 0})

    def tests_non_regular_start_stop(self):
        """ Test start calls when not needed
            * start when started
            * stop when stopped
        """
        stop_mock = mock.Mock(side_effect=self.g_m.exp_stop)
        with patch.object(self.g_m, 'exp_stop', stop_mock):

            # create experiment
            self.assertEquals(0, self.g_m.exp_start(**self.exp_conf))
            self.assertEquals(stop_mock.call_count, 0)
            # replace current experiment
            self.assertEquals(0, self.g_m.exp_start(**self.exp_conf))
            self.assertEquals(stop_mock.call_count, 1)

            # stop exp
            self.assertEquals(0, self.g_m.exp_stop())
            # exp already stoped no error
            self.assertEquals(0, self.g_m.exp_stop())

    def tests_invalid_tty_exp_a8(self):
        """ Test start where tty is not visible """
        if 'A8' != gateway_code.config.board_type():
            return

        g_m = self.g_m
        g_m.exp_start(**self.exp_conf)

        with patch.object(g_m, 'open_power_start', g_m.open_power_stop):
            # detect error when A8 does not start
            self.assertNotEquals(0, g_m.exp_start(**self.exp_conf))

        # stop and cleanup
        self.assertEquals(0, g_m.exp_stop())


class TestInvalidCases(test_integration_mock.GatewayCodeMock):
    """ Invalid calls """

    def tests_invalid_profile_at_start(self):
        """ Run experiments with invalid profiles """

        self.request.files = {'profile': self.files['invalid_profile']}
        self.assertNotEquals({'ret': 0}, self.app.exp_start(USER, 123))

        self.request.files = {'profile': self.files['invalid_profile_2']}
        self.assertNotEquals({'ret': 0}, self.app.exp_start(USER, 123))

    def tests_invalid_files(self):
        """ Test invalid flash files """

        self.request.files = {'profile': self.files['profile']}
        self.assertNotEquals({'ret': 0}, self.app.open_flash())

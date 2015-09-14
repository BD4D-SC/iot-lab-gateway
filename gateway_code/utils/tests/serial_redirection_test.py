# -*- coding:utf-8 -*-

""" test serial_redirection module """

import mock
import unittest
import time

import logging
import socket
from subprocess import Popen, PIPE

from gateway_code.common import wait_tty
from ..serial_redirection import SerialRedirection
from gateway_code.autotest.node_connection import OpenNodeConnection

# pylint: disable=invalid-name
# pylint: disable=protected-access
# pylint <= 1.3
# pylint: disable=too-many-public-methods
# pylint >= 1.4
# pylint: disable=too-few-public-methods
# pylint: disable=no-member


class TestSerialRedirection(unittest.TestCase):
    """ SerialRedirection class test """

    def setUp(self):
        self.tty = '/tmp/ttySRT'
        self.baud = 500000
        self.redirect = None

        cmd = ['socat', '-', 'pty,link=%s,raw,b%d,echo=0' % (self.tty,
                                                             self.baud)]
        self.serial = Popen(cmd, stdout=PIPE, stdin=PIPE)
        wait_tty(self.tty, mock.Mock(side_effect=RuntimeError()), 5)

    def tearDown(self):
        self.serial.terminate()
        self.redirect.stop()

    def test_serialredirection_execution(self):
        """ Test a standard SerialRedirection execution """
        self.redirect = SerialRedirection(self.tty, self.baud)
        self.redirect.start()

        for i in range(0, 3):
            # connect to port 20000
            conn = OpenNodeConnection.try_connect(('0.0.0.0', 20000))

            # TCP send
            sock_txt = 'HelloFromSock: %u\n' % i
            conn.send(sock_txt)
            ret = self.serial.stdout.read(len(sock_txt))
            self.assertEquals(ret, sock_txt)
            logging.debug(ret)

            # Serial send
            serial_txt = 'HelloFromSerial %u\n' % i
            self.serial.stdin.write(serial_txt)
            ret = conn.recv(len(serial_txt))
            self.assertEquals(ret, serial_txt)
            logging.debug(ret)

            conn.close()

        self.redirect.stop()

    def test_serialredirection_multiple_uses(self):
        """ Test calling multiple times start-stop """
        self.redirect = SerialRedirection(self.tty, self.baud)
        self.assertEquals(0, self.redirect.start())
        self.assertEquals(0, self.redirect.stop())
        self.assertEquals(0, self.redirect.start())
        self.assertEquals(0, self.redirect.stop())
        self.assertEquals(0, self.redirect.start())
        self.assertEquals(0, self.redirect.stop())

    def test_serialredirection_exclusion(self):
        """ Check the exclusion of multiple connection on SerialRedirection """
        self.redirect = SerialRedirection(self.tty, self.baud)
        self.redirect.start()

        conn = OpenNodeConnection.try_connect(('0.0.0.0', 20000))
        time.sleep(1)
        # Second connection should fail
        self.assertRaises(IOError,
                          socket.create_connection, ('0.0.0.0', 20000))
        conn.close()
        self.redirect.stop()

    @mock.patch('subprocess.Popen')
    def test_terminate_non_running_process(self, m_popen):
        """ Test the case where 'stop' is called on a process that is currently
        being restarted.
        It can happen if stop is called after an error """

        m_socat = m_popen.return_value
        m_socat.terminate.side_effect = OSError(3, "No such process")

        self.redirect = SerialRedirection(self.tty, self.baud)
        self.redirect.start()
        self.redirect.stop()

        self.assertTrue(m_socat.terminate.called)

    @mock.patch('subprocess.Popen')
    def test__call_socat_error(self, m_popen):
        """ Test the _call_socat error case """
        m_popen.return_value.wait.return_value = -1
        self.redirect = SerialRedirection(self.tty, self.baud)
        self.redirect._run = True

        ret = self.redirect._call_socat(self.redirect.DEVNULL)
        self.assertEquals(-1, ret)

    @mock.patch('subprocess.Popen')
    def test__call_socat_error_tty_not_found(self, m_popen):
        """ Test the _call_socat error case when path can't be found"""
        m_popen.return_value.wait.return_value = -1
        self.redirect = SerialRedirection('/dev/NotATty', self.baud)
        self.redirect._run = True

        ret = self.redirect._call_socat(self.redirect.DEVNULL)
        self.assertEquals(-1, ret)

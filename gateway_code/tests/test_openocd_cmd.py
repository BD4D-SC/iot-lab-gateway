#! /usr/bin/env python
# -*- coding:utf-8 -*-

# pylint: disable=missing-docstring
# pylint: disable=too-many-public-methods
# pylint: disable=invalid-name
# pylint: disable=protected-access
# serial mock note correctly detected
# pylint: disable=maybe-no-member

from mock import patch
import unittest
from cStringIO import StringIO

from os.path import dirname, abspath

from gateway_code import openocd_cmd

CURRENT_DIR = dirname(abspath(__file__)) + '/'
STATIC_DIR = CURRENT_DIR + 'static/'  # using the 'static' symbolic link


@patch('gateway_code.config.STATIC_FILES_PATH', new=STATIC_DIR)
@patch('subprocess.call')
class TestsMethods(unittest.TestCase):
    """ Tests openocd_cmd methods """

    def test_node_detection(self, call_mock):
        """ Test node detection """
        # valid nodes
        call_mock.return_value = 0
        for node in ('m3', 'gwt', 'a8'):
            openocd_cmd.flash(node, STATIC_DIR + 'idle.elf')

        # invalid nodes
        self.assertRaises(ValueError, openocd_cmd.flash, 'INEXISTANT',
                          '/dev/null')

    def test_flash(self, call_mock):
        """ Test flash """

        filename = STATIC_DIR + 'idle.elf'
        call_mock.return_value = 0
        self.assertEquals(0, openocd_cmd.flash('m3', filename))

        call_mock.return_value = 42
        self.assertEquals(42, openocd_cmd.flash('m3', filename))

    def test_reset(self, call_mock):
        """ Test reset"""
        call_mock.return_value = 0
        self.assertEquals(0, openocd_cmd.reset('m3'))

        call_mock.return_value = 42
        self.assertEquals(42, openocd_cmd.reset('m3'))


class TestsFlashInvalidPaths(unittest.TestCase):
    @patch('gateway_code.config.STATIC_FILES_PATH', new='/invalid/path/')
    def test_invalid_config_file_path(self):
        self.assertRaises(IOError, openocd_cmd.flash, 'm3', '/dev/null')

    @patch('gateway_code.config.STATIC_FILES_PATH', new=STATIC_DIR)
    def test_invalid_firmware_path(self):
        self.assertNotEqual(0, openocd_cmd.flash('m3', '/invalid/path'))


# Command line tests
@patch('sys.stderr', StringIO())
class TestsCommandLineCalls(unittest.TestCase):

    @patch('gateway_code.openocd_cmd.flash')
    def test_flash(self, mock_fct):
        """ Running command line flash """
        mock_fct.return_value = 0
        ret = openocd_cmd._main(['openocd_cmd.py', 'flash', 'm3', '/dev/null'])
        self.assertEquals(ret, 0)

        mock_fct.return_value = 42
        ret = openocd_cmd._main(['openocd_cmd.py', 'flash', 'm3', '/dev/null'])
        self.assertEquals(ret, 42)

    @patch('gateway_code.openocd_cmd.reset')
    def test_reset(self, mock_fct):
        """ Running command line reset """
        mock_fct.return_value = 0
        ret = openocd_cmd._main(['openocd_cmd.py', 'reset', 'm3'])
        self.assertEquals(ret, 0)

        mock_fct.return_value = 42
        ret = openocd_cmd._main(['openocd_cmd.py', 'reset', 'm3'])
        self.assertEquals(ret, 42)

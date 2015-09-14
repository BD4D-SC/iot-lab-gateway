# -*- coding: utf-8 -*-
""" Implementation of common mocks for integration tests """

import os
import unittest
import mock
import json
from nose.plugins.attrib import attr

from mock import patch

import gateway_code.rest_server
import gateway_code.board_config


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) + '/'


# pylint: disable=too-many-public-methods
@attr('integration')
class GatewayCodeMock(unittest.TestCase):
    """ gateway_code mock for integration tests  """

    @classmethod
    def setUpClass(cls):

        if os.uname()[4] != 'armv7l':
            raise unittest.SkipTest("Skip board embedded tests")

        g_m = gateway_code.rest_server.GatewayManager('.')
        g_m.setup()
        cls.app = gateway_code.rest_server.GatewayRest(g_m)

    @classmethod
    def tearDownClass(cls):
        patch.stopall()

    def setUp(self):
        # get quick access to class attributes
        self.app = type(self).app
        self.g_m = self.app.gateway_manager

        self.board_cfg = gateway_code.board_config.BoardConfig()

        self.cn_measures = []
        self.g_m.control_node.cn_serial.measures_debug = self.cn_measure

        self.request_patcher = patch('gateway_code.rest_server.request')
        self.request = self.request_patcher.start()
        self.request.query = mock.Mock(timeout='0')  # no timeout by default

        with open(CURRENT_DIR + 'profile.json') as prof:
            self.profile_dict = json.load(prof)

    def cn_measure(self, measure):
        """ Store control node measures """
        self.cn_measures.append(measure.split(' '))

    def tearDown(self):
        self.request_patcher.stop()
        self.app.exp_stop()  # just in case, post error cleanup

#! /usr/bin/env python
# -*- coding:utf-8 -*-

# pylint: disable=no-self-use

""" Board Config """

import os

_BOARD_CONFIG = {}
GATEWAY_CONFIG_PATH = '/var/local/config/'


class BoardConfig(object):

    """ 
            Class BoardConfig, used to get all the informations on the actual node 
            this class is implemented as a Singleton
    """
    # The unique instance of the class Board Config
    _instance = None

    # We define a new contructor to respect the Singleton patern
    def __new__(cls):
        # if the instance of the class doesn't exist
        if BoardConfig._instance == None:
                # we create a new instance of the class
            BoardConfig._instance = object.__new__(cls)
        # we return the new instance of the existing instance
        return BoardConfig._instance

    # the initialisation of the class
    def __init__(self):
        self.board_type = self.find_board_type()

    def _get_conf(self, key, path, raise_error=False):
        """
        Load config from file given as key

        :param key: config file name
        :param raise_error: select if exceptions are silenced or raised
        """
        # Singleton pattern
        if key not in _BOARD_CONFIG:
                # load from file
            try:
                _file = open(os.path.join(path, key))
                _BOARD_CONFIG[key] = _file.read().strip().lower()
                _file.close()
            except IOError as err:
                _BOARD_CONFIG[key] = None
                if raise_error:
                    raise err
        return _BOARD_CONFIG[key]

    def find_board_type(self):
        """ Return the board type
        Currently in ('m3', 'a8', 'fox', 'leonardo')
        """
        return self._get_conf('board_type', GATEWAY_CONFIG_PATH, raise_error=True)

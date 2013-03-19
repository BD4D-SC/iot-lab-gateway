#! /usr/bin/env python
# -*- coding:utf-8 -*-


"""
manager script
"""

from gateway_code import flash_firmware

class GatewayManager(object):
    """
    Gateway Manager class,

    Manages experiments, open node and control node
    """
    def __init__(self):
        self.exp_id = None
        self.user = None


    def exp_start(self, exp_id, user, firmware_path, profile):

        param_str = str((self, exp_id, user, firmware_path, profile))
        ret_str = "%s: %s" % (_unimplemented_fct_str_(), param_str)
        return 0, ret_str


    def exp_stop(self, exp_id, user):
        param_str = str((self, exp_id, user))
        ret_str = "%s: %s" % (_unimplemented_fct_str_(), param_str)
        return 0, ret_str


    def exp_update_profile(self, exp_id, user, profile):
        param_str = str((self, exp_id, user, profile))
        ret_str = "%s: %s" % (_unimplemented_fct_str_(), param_str)
        return 0, ret_str



    @staticmethod
    def open_start():
        ret_str = _unimplemented_fct_str_()
        return 0, ret_str

    @staticmethod
    def open_stop():
        ret_str = _unimplemented_fct_str_()
        return 0, ret_str

    @staticmethod
    def open_reset():
        ret_str = _unimplemented_fct_str_()
        return 0, ret_str

    @staticmethod
    def open_flash(firmware_path):
        ret, out, err = flash_firmware.flash('m3', firmware_path)
        return ret, out, err



    @staticmethod
    def control_flash(firmware_path):
        param_str = str((firmware_path))
        ret_str = "%s: %s" % (_unimplemented_fct_str_(), param_str)
        return 0, ret_str


def _unimplemented_fct_str_():
    """
    Current function name
    """
    import sys
    fct = sys._getframe(1).f_code.co_name
    ret_str = "Not implemented %s" % fct
    return ret_str


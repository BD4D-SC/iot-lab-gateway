#-*- coding: utf-8 -*-

"""
Rest server listening to the experiment handler

"""

from bottle import run, request, route
from tempfile import NamedTemporaryFile
import json

from gateway_code.gateway_manager import GatewayManager
import gateway_code

class GatewayRest(object):
    """
    Gateway Rest class

    It calls the gateway manager to treat commands
    """
    def __init__(self, gateway_manager):
        self.gateway_manager = gateway_manager

    @staticmethod
    def __valid_request(required_files_seq):
        """
        Check the file arguments in the request.

        :param required_files_seq: file arguments required in 'request.files'
        :type required_files_seq:  sequence
        :return: If files match required files
        """
        # compare that the two lists have the same elements
        return set(request.files.keys()) == set(required_files_seq)


    def exp_start(self, expid, username):
        """
        Start an experiment

        :param expid: experiment id
        :param username: username of the experiment owner
        """
        # verify passed files as request
        if not self.__valid_request(('firmware', 'profile')):
            return {'ret': 1, 'error': \
                    "Wrong file args: required 'firmware' + 'profile'"}

        firmware = request.files['firmware']
        profile  = request.files['profile']
        profile_dict = json.load(profile.file)
        profile_obj = gateway_code.profile.profile_from_dict(profile_dict)

        with NamedTemporaryFile(suffix = '--' + firmware.filename) as _file:
            _file.write(firmware.file.read())
            ret = self.gateway_manager.exp_start(expid, username, \
                    _file.name, profile_obj)
        return {'ret':ret}


    def exp_stop(self):
        """
        Stop the current experiment
        """

        # no files required, don't check

        ret = self.gateway_manager.exp_stop()
        return {'ret':ret}

    def reset_time(self):
        """
        Reset Control node time and update time reference
        """
        ret = self.gateway_manager.reset_time()
        return {'ret':ret}


    def _flash(self, node):
        """
        Flash node

        Requires:
        request.files contains 'firmware' file argument
        """

        # verify passed files as request
        if not self.__valid_request(('firmware',)):
            return {'ret': 1, 'error':"Wrong file args: required 'firmware'"}
        firmware = request.files['firmware']

        with NamedTemporaryFile(suffix = '--' + firmware.filename) as _file:
            _file.write(firmware.file.read())
            ret = self.gateway_manager.node_flash(node, _file.name)

        return {'ret':ret}


    def open_flash(self):
        """
        Flash open node
        """
        return self._flash('m3')

    def open_soft_reset(self):
        """
        Reset the open node with 'reset' pin
        """
        ret = self.gateway_manager.node_soft_reset('m3')
        return {'ret':ret}




    def admin_control_soft_reset(self):
        """
        Reset the control node with 'reset' pin
        """
        ret = self.gateway_manager.node_soft_reset('gwt')
        return {'ret':ret}


    def admin_control_flash(self):
        """
        Flash control node
        """
        return self._flash('gwt')


def parse_arguments(args):
    """
    Parse arguments:
        [host, port]

    :param args: arguments, without the script name == sys.argv[1:]
    :type args: list
    """
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('host', type=str,
            help="Server address to bind to")
    parser.add_argument('port', type=int, help="Server port to bind to")
    parser.add_argument('--log-folder', default='.', \
            help="Folder where to write logs, default current folder")
    arguments = parser.parse_args(args)

    return arguments.host, arguments.port, arguments.log_folder

def app_routing(app):
    """
    routing configuration
    :param app: default application
    """
    route('/exp/start/:expid/:username', 'POST')(app.exp_start)
    route('/exp/stop', 'DELETE')(app.exp_stop)
    route('/open/flash', 'POST')(app.open_flash)
    route('/open/reset', 'PUT')(app.open_soft_reset)


def main(args):
    """
    Command line main function
    """

    host, port, log_folder = parse_arguments(args[1:])

    app = GatewayRest(GatewayManager(log_folder))
    app_routing(app)
    run(host=host, port=port, server='paste')

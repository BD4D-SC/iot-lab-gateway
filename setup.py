#! /usr/share/env python
# -*- coding:utf-8 -*-

"""
setup.py deployement script

Install all the `gateway code` on a gateway

    python setup.py release

It runs the `install` command and the `post_install` procedure.

Tests commands:

    python setup.py nosetests
    python setup.py integration

Pylint and pep8 checker:

    python setup.py lint
    python setup.py pep8


"""

from setuptools import setup, Command, Extension
from setuptools.command.build_ext import build_ext

import sys
import os
import subprocess

# pylint: disable=attribute-defined-outside-init
# pylint <= 1.3
# pylint: disable=too-many-public-methods
# pylint >= 1.4
# pylint: disable=too-few-public-methods

PACKAGE = 'gateway_code'


def get_version(package):
    """ Extract package version without importing file
    Importing cause issues with coverage,
        (modules can be removed from sys.modules to prevent this)
    Importing __init__.py triggers importing rest and then requests too

    Inspired from pep8 setup.py
    """
    with open(os.path.join(package, '__init__.py')) as init_fd:
        for line in init_fd:
            if line.startswith('__version__'):
                return eval(line.split('=')[-1])  # pylint:disable=eval-used


SCRIPTS = ['bin/scripts/' + el for el in os.listdir('bin/scripts')]
SCRIPTS += ['control_node_serial/control_node_serial_interface']

INSTALL_REQUIRES = ['argparse', 'bottle', 'paste', 'pyserial']


class BuildExt(build_ext):
    """ Overwrite build_ext to build control node serial """

    def run(self):
        """ Build control node serial interface """
        args = ['make', '-C', 'control_node_serial', 'realclean', 'all']
        try:
            subprocess.check_call(args)
        except subprocess.CalledProcessError as err:
            exit(err.returncode)


class Release(Command):
    """ Install and do the 'post installation' procedure too.
    Meant to be used directly on the gateways """
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            subprocess.check_call(['python', 'setup.py', 'install'])
        except subprocess.CalledProcessError as err:
            exit(err.returncode)
        self.post_install()

    @staticmethod
    def post_install():
        """ Install init.d script
        Add www-data user to dialout group """
        import shutil

        # setup init script
        init_script = 'gateway-server-daemon'
        update_rc_d_args = ['update-rc.d', init_script,
                            'start', '80', '2', '3', '4', '5', '.',
                            'stop', '20', '0', '1', '6', '.']
        shutil.copy('bin/init_script/' + init_script, '/etc/init.d/')
        os.chmod('/etc/init.d/' + init_script, 0755)
        subprocess.check_call(update_rc_d_args)

        #  add `www-data` user to `dialout` group
        subprocess.check_call(['usermod', '-a', '-G', 'dialout', 'www-data'])


class Integration(Command):
    """ Run unit tests and integration tests.  Should be run on a gateway """
    user_options = [('stop', None, "Stop tests after a failed test"),
                    ('tests=', None, "Run these tests (comma-separated-list)")]

    def initialize_options(self):
        self.tests = ''
        self.stop = False

    def finalize_options(self):
        self.nose_args = ['nosetests',
                          '--xcoverage-file=%s_coverage.xml' % os.uname()[1],
                          '--xunit-file=%s_nosetests.xml' % os.uname()[1]]
        self.nose_args += ['--tests=%s' % self.tests] if self.tests else []
        if self.stop:
            self.nose_args.append('--stop')

    def run(self):
        args = ['python', 'setup.py']
        print >> sys.stderr, ' '.join(self.nose_args)

        env = os.environ.copy()
        env['PATH'] = './control_node_serial/:' + env['PATH']
        if 'www-data' != env['USER']:
            print >> sys.stderr, (
                "ERR: Run Integration tests as 'www-data':\n\n",
                "\tsu www-data -c 'python setup.py integration'\n"
            )
            exit(1)

        ret = subprocess.call(args + self.nose_args, env=env)
        return ret


setup(name=PACKAGE,
      version=get_version(PACKAGE),
      description='Linux Gateway code',
      author='IoT-Lab Team',
      author_email='admin@iot-lab.info',
      url='http://www.iot-lab.info',
      packages=[PACKAGE, '%s.autotest' % PACKAGE, 'roomba'],

      scripts=SCRIPTS,
      include_package_data=True,
      package_data={'static': ['static/*']},
      ext_modules=[Extension('control_node_serial_interface', [])],

      cmdclass={
          'build_ext': BuildExt,
          'release': Release,
          'integration': Integration,
      },
      install_requires=INSTALL_REQUIRES)

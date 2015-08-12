#! /usr/bin/python
# -*- coding:utf-8 -*-

"""
Open node validation interface

Interface for running autotests with open node auto-test firmware
"""


import threading
import serial
import Queue
import time

from gateway_code import common


class OpenNodeSerial(object):
    """
    OpenNodeSerial class implementing the interface with open node auto-test
    """

    def __init__(self, tty, baudrate):
        self.tty = tty
        self.baudrate = baudrate
        self.serial_fd = None
        self.stop_reader = threading.Event()
        self.msg_queue = Queue.Queue(0)

        self.reader_thread = None

    def start(self):
        """ Start serial interface """
        # open serial
        try:
            self.serial_fd = serial.Serial(
                self.tty, self.baudrate, timeout=0.5)
            self.serial_fd.flushInput()

            # start reader thread
            self.reader_thread = threading.Thread(target=self._serial_reader)
            self.reader_thread.start()
        except serial.SerialException as err:
            return 1, str(err)
        return 0, 'OK'

    def stop(self):
        """ Stop serial interface """
        self.stop_reader.set()
        self.reader_thread.join()
        self.serial_fd.close()

    def send_command(self, command_list):
        """ Send command and wait for answer """
        assert (isinstance(command_list, list) or
                isinstance(command_list, tuple))
        packet = ' '.join(command_list)
        self.serial_fd.write(packet + '\n')

        # wait answer
        common.empty_queue(self.msg_queue)
        try:
            answer = self.msg_queue.get(timeout=5).split(' ')
        except Queue.Empty:
            answer = None
        return answer

    def _serial_reader(self):
        """ Serial port reader thread """
        read_str = ''
        while not self.stop_reader.is_set():
            read_str += self.serial_fd.readline()  # append waiting data
            # issues without this or a print for test_gpio
            # This is pure magic, really
            time.sleep(0.1)
            if not read_str or read_str[-1] != '\n':  # timeout reached
                continue
            # answer complete
            self.msg_queue.put(read_str.strip())
            read_str = ''

# -*- coding: utf-8 -*-

"""
Serial IO layer for control node
"""
import serial
import Queue
#import threading
from threading import Lock, Thread


# Remove for the moment
#  from gateway_code.gateway_logging import logger

SYNC_BYTE = chr(0x80)





# States of the packet reception progression state machine.
RX_IDLE, RX_LEN, RX_PAYLOAD, RX_PACKET_FULL = range(4)

#Definitions used to trigger the creation of a new Buffer to receive the packet.
IN_USE = 5
UNUSED = 6



class Buffer(object):
    """
    Buffer to hold a packet while being created
    """

    def __init__(self):
        self.length = None
        self.payload = ""

    def __repr__(self):
        result = " length=%d, payload=%s" % \
                ( self.length,  self.payload)
        return result

    def is_complete(self):
        """
        Returns if the packet is complete
        """
        return (self.length is not None) and (self.length == len(self.payload))





def rx_idle(packet, rx_char):
    """
    Adds the sync byte to the packet and changes the rx_State
    to RX_LEN in order to get the next length byte.
    """
    if rx_char == SYNC_BYTE:
        return RX_LEN
    else:
        #logger.debug("rx_idle : packet lost?")
        return RX_IDLE


def rx_length(packet, rx_char):
    """
    'length' byte received, store it into packet
    :return: new state for the state machine
    """

    packet.length = ord(rx_char)
    return RX_PAYLOAD


def rx_payload(packet, rx_char):
    """
    Adds the received byte to payload.

    If packet complete, change state to PACKET_FULL
    else, keep waiting for bytes
    """
    packet.payload += rx_char

    if packet.is_complete():
        #logger.debug("\t rx_payload packet : %s" %(packet))
        return RX_PACKET_FULL

    return RX_PAYLOAD


STATE_MACHINE_DICT = {
        RX_IDLE: rx_idle,
        RX_LEN : rx_length,
        RX_PAYLOAD: rx_payload,
        RX_PACKET_FULL: None,
        }


# RX_THREAD = Thread(group=None, target=receive_packets, \
#     name='rx_thread', args= (), kwargs={})
# RX_THREAD.start()


class ThreadRead(Thread):
    """Threaded read"""
    def __init__(self, queue):
        Thread.__init__(self)
        self.rx_queue = queue

        # TODO maybe adapt this
        self.serial_port = serial.Serial(port='/dev/ttyFITECO_GWT', \
                baudrate=500000)

    def run(self):
        """
        Read packets from the serial link

        Packet have the format:
            | SYNC  |  LENGTH | DATA |
        """

        rx_state = RX_IDLE
        packet = Buffer()

        while True:
            #call to read will block when no bytes are received
            try:
                rx_char = self.serial_port.read()
            except ValueError:
                break

            # Putting the bytes received into the packet depending on the
            # reception state (rx_state)
            rx_state = STATE_MACHINE_DICT[rx_state](packet, rx_char)


            if rx_state == RX_PACKET_FULL:
                try:
                    self.rx_queue.put(packet.payload)
                #TODO : remplir condition queue full, bloquer sur le put?
                except Queue.Full:
                    pass
                rx_state = RX_IDLE
                packet = Buffer()

        # TODO maybe cleanup the code...


def make_header(data):
    """
    Create a packet from the data

    :param data: contains 'type', maybe 'ack byte', and 'data payload'
    :type data: string

    :return: a packet with header + data
    """
    length = len(data)
    packet = SYNC_BYTE + chr(length) + data
    return packet




PROTECT_SEND = Lock()
#Queue can store 1 item
RX_QUEUE = Queue.Queue(1)
def send_packet(data):
    """
    Send a packet and wait for the answer
    """

    PROTECT_SEND.acquire()

    tx_packet = make_header(data)
    SERIAL_PORT.write(tx_packet)

    rx_packet = RX_QUEUE.get(block=True)
    PROTECT_SEND.release()

    return rx_packet


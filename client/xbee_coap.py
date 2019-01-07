import logging.config
import threading
import random
import time

from digi.xbee.exception import TimeoutException

from coapthon import defines
from coapthon.layers.blocklayer import BlockLayer
from coapthon.layers.messagelayer import MessageLayer
from coapthon.layers.observelayer import ObserveLayer
from coapthon.layers.requestlayer import RequestLayer
from coapthon.messages.message import Message
from coapthon.messages.request import Request
from coapthon.messages.response import Response
from coapthon.serializer import Serializer

import collections

__author__ = 'Magnus Hagdorn'


logger = logging.getLogger(__name__)


class CoAP(object):
    """
    Client class to perform requests to remote servers.
    """
    def __init__(self, xbee, remote_id, starting_mid, callback, cb_ignore_read_exception=None, cb_ignore_write_exception=None):
        """
        Initialize the client.
        :param xbee: the xbee device
        :param remote_id: the remote xbee device
        :param callback:the callback function to be invoked when a response is received
        :param starting_mid: used for testing purposes
        :param sock: if a socket has been created externally, it can be used directly
        :param cb_ignore_read_exception: Callback function to handle exception raised during the socket read operation
        :param cb_ignore_write_exception: Callback function to handle exception raised during the socket write operation        
        """

        self.xbee = xbee
        self.xbee.open()
        logger.info('xbee address %s'%xbee.get_64bit_addr())
        logger.info('xbee node id %s'%xbee.get_node_id())

        xnet = xbee.get_network()
        self.remote = xnet.discover_device(remote_id)
        logger.info(self.remote)

        self._currentMID = starting_mid
        self._callback = callback
        self._cb_ignore_read_exception = cb_ignore_read_exception
        self._cb_ignore_write_exception = cb_ignore_write_exception
        self.stopped = threading.Event()
        self.to_be_stopped = []

        self._messageLayer = MessageLayer(self._currentMID)
        self._blockLayer = BlockLayer()
        self._observeLayer = ObserveLayer()
        self._requestLayer = RequestLayer(self)

        self._receiver_thread = None
        
    def close(self):
        """
        Stop the client.
        """
        self.stopped.set()
        for event in self.to_be_stopped:
            event.set()
        if self._receiver_thread is not None:
            self._receiver_thread.join()
        self.xbee.close()

    @property
    def current_mid(self):
        """
        Return the current MID.
        :return: the current mid
        """
        return self._currentMID

    @current_mid.setter
    def current_mid(self, c):
        """
        Set the current MID.
        :param c: the mid to set
        """
        assert isinstance(c, int)
        self._currentMID = c

    def send_message(self, message):
        """
        Prepare a message to send on the UDP socket. Eventually set retransmissions.
        :param message: the message to send
        """

        if isinstance(message, Request):
            request = self._requestLayer.send_request(message)
            request = self._observeLayer.send_request(request)
            request = self._blockLayer.send_request(request)
            transaction = self._messageLayer.send_request(request)
            self.send_datagram(transaction.request)
            if transaction.request.type == defines.Types["CON"]:
                self._start_retransmission(transaction, transaction.request)
        elif isinstance(message, Message):
            message = self._observeLayer.send_empty(message)
            message = self._messageLayer.send_empty(None, None, message)
            self.send_datagram(message)

    def send_datagram(self, message):
        """
        Send a message over the UDP socket.
        :param message: the message to send
        """

        logger.debug("send_datagram - " + str(message))
        serializer = Serializer()
        raw_message = serializer.serialize(message)


        try:
            self.xbee.send_data(self.remote,raw_message)
        except Exception as e:
            if self._cb_ignore_write_exception is not None and isinstance(self._cb_ignore_write_exception, collections.Callable):
                if not self._cb_ignore_write_exception(e, self):
                    raise

        # if you're explicitly setting that you don't want a response, don't wait for it
        # https://tools.ietf.org/html/rfc7967#section-2.1
        for opt in message.options:
            if opt.number == defines.OptionRegistry.NO_RESPONSE.number:
                if opt.value == 26:
                    return

        if self._receiver_thread is None or not self._receiver_thread.isAlive():
            self._receiver_thread = threading.Thread(target=self.receive_datagram)
            self._receiver_thread.daemon = True
            self._receiver_thread.start()

    def _start_retransmission(self, transaction, message):
        """
        Start the retransmission task.
        :type transaction: Transaction
        :param transaction: the transaction that owns the message that needs retransmission
        :type message: Message
        :param message: the message that needs the retransmission task
        """
        with transaction:
            if message.type == defines.Types['CON']:
                future_time = random.uniform(defines.ACK_TIMEOUT, (defines.ACK_TIMEOUT * defines.ACK_RANDOM_FACTOR))
                transaction.retransmit_stop = threading.Event()
                self.to_be_stopped.append(transaction.retransmit_stop)
                transaction.retransmit_thread = threading.Thread(target=self._retransmit,
                                                                 name=str('%s-Retry-%d' % (threading.current_thread().name, message.mid)),
                                                                 args=(transaction, message, future_time, 0))
                transaction.retransmit_thread.start()

    def _retransmit(self, transaction, message, future_time, retransmit_count):
        """
        Thread function to retransmit the message in the future
        :param transaction: the transaction that owns the message that needs retransmission
        :param message: the message that needs the retransmission task
        :param future_time: the amount of time to wait before a new attempt
        :param retransmit_count: the number of retransmissions
        """
        with transaction:
            logger.debug("retransmit loop ... enter")
            while retransmit_count <= defines.MAX_RETRANSMIT \
                    and (not message.acknowledged and not message.rejected) \
                    and not transaction.retransmit_stop.isSet():
                transaction.retransmit_stop.wait(timeout=future_time)
                if not message.acknowledged and not message.rejected and not transaction.retransmit_stop.isSet():
                    retransmit_count += 1
                    future_time *= 2
                    if retransmit_count < defines.MAX_RETRANSMIT:
                        logger.debug("retransmit loop ... retransmit Request")
                        self.send_datagram(message)

            if message.acknowledged or message.rejected:
                message.timeouted = False
            else:
                logger.warning("Give up on message {message}".format(message=message.line_print))
                message.timeouted = True

                # Inform the user, that nothing was received
                self._callback(None)

            try:
                self.to_be_stopped.remove(transaction.retransmit_stop)
            except ValueError:
                pass
            transaction.retransmit_stop = None
            transaction.retransmit_thread = None

            logger.debug("retransmit loop ... exit")

    def receive_datagram(self):
        """
        Receive datagram from the UDP socket and invoke the callback function.
        """
        
        logger.debug("Start receiver Thread")
        while not self.stopped.isSet():
            try:
                xbee_message = self.xbee.read_data(timeout=0.1)
            except TimeoutException:
                continue
            except Exception as e:  
                if self._cb_ignore_read_exception is not None and isinstance(self._cb_ignore_read_exception, collections.Callable):
                    if self._cb_ignore_read_exception(e, self):
                        continue
                return

            print ( xbee_message)
            
        
        raise NotImplementedError


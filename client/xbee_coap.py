import logging.config
import threading
import random
import time

from digi.xbee.exception import TimeoutException

from coapthon.client.coap import CoAP as UDP_CoAP

from coapthon import defines
from coapthon.messages.message import Message
from coapthon.messages.request import Request
from coapthon.messages.response import Response
from coapthon.serializer import Serializer

import collections

__author__ = 'Magnus Hagdorn'


logger = logging.getLogger(__name__)


class CoAP(UDP_CoAP):
    """
    Client class to perform requests to remote servers.
    """
    def __init__(self, server, xbee, remote_id, starting_mid, callback, cb_ignore_read_exception=None, cb_ignore_write_exception=None):
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

        UDP_CoAP.__init__(self,server, starting_mid, callback, sock=None, cb_ignore_read_exception=cb_ignore_read_exception, cb_ignore_write_exception=cb_ignore_write_exception)
        
    def close(self):
        """
        Stop the client.
        """
        UDP_CoAP.close(self)
        self.xbee.close()

            
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


            serializer = Serializer()
            message = serializer.deserialize(bytes(xbee_message.data) , self._server)


            if isinstance(message, Response):
                logger.debug("receive_datagram - " + str(message))
                transaction, send_ack = self._messageLayer.receive_response(message)
                if transaction is None:  # pragma: no cover
                    continue
                self._wait_for_retransmit_thread(transaction)
                if send_ack:
                    self._send_ack(transaction)
                self._blockLayer.receive_response(transaction)
                if transaction.block_transfer:
                    self._send_block_request(transaction)
                    continue
                elif transaction is None:  # pragma: no cover
                    self._send_rst(transaction)
                    return
                self._observeLayer.receive_response(transaction)
                if transaction.notification:  # pragma: no cover
                    ack = Message()
                    ack.type = defines.Types['ACK']
                    ack = self._messageLayer.send_empty(transaction, transaction.response, ack)
                    self.send_datagram(ack)
                    self._callback(transaction.response)
                else:
                    self._callback(transaction.response)
            elif isinstance(message, Message):
                self._messageLayer.receive_empty(message)

        logger.debug("Exiting receiver Thread due to request")



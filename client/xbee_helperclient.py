import random
from multiprocessing import Queue

from coapthon.client.helperclient import HelperClient
from .xbee_coap import CoAP

__author__ = 'Magnus Hagdorn'


class XBeeHelperClient(HelperClient):
    """
    Helper Client class to perform requests to remote servers in a simplified way.
    """
    def __init__(self, server, xbee, remote, cb_ignore_read_exception=None, cb_ignore_write_exception=None):
        """
        Initialize a client to perform request to a server.
        :param xbee: the xbee device
        :param remote: the remote xbee device
        :param cb_ignore_read_exception: Callback function to handle exception raised during the socket read operation
        :param cb_ignore_write_exception: Callback function to handle exception raised during the socket write operation 
        """

        self.xbee = xbee
        self.remote = remote
        self.server = server
        self.protocol = CoAP(server,self.xbee, self.remote, random.randint(1, 65535), self._wait_response, 
                             cb_ignore_read_exception=cb_ignore_read_exception, cb_ignore_write_exception=cb_ignore_write_exception)
        self.queue = Queue()


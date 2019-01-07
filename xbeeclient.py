import argparse
import sys
import logging
import time
from digi.xbee.devices import XBeeDevice

from client.xbee_helperclient import XBeeHelperClient

OPERATIONS = ["GET","PUT","POST","DELETE","DISCOVER","OBSERVE"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('device',help='xbee device to open')
    parser.add_argument('-b','--baud-rate',type=int,default=9600,help='the baud rate')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a","--xbee-address",help="the 64 bit address of the remote xbee device")
    group.add_argument("-n","--node-id",help="the node ID of the remote xbee device")

    parser.add_argument("-o","--operation",choices=OPERATIONS,default="DISCOVER",help="CoAP operation. default: GET")
    parser.add_argument("-r","--resource",help="the resource to request")
    parser.add_argument("-p","--payload",help="payload of the request")
    parser.add_argument("-d","--debug",default=False,action="store_true",help="enable debugging")

    args = parser.parse_args()

    logger = logging.getLogger("")
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    
    if args.resource is not None:
        if not args.resource.startswith('/'):
            parser.error('resource must start with /')
            sys.exit(1)

    if args.operation != 'DISCOVER':
        if args.resource is None:
            parser.error('resource must not be empty for a %s request'%args.operation)
    if args.operation in ['PUT','POST']:
        if args.payload is None:
            parser.error('payload must not be empty for a %s request'%args.operation)
            
    xbee = XBeeDevice(args.device,args.baud_rate)
    client = XBeeHelperClient(xbee, args.node_id)

    if args.operation == 'GET':
        pass
    elif args.operation == 'OBSERVE':
        pass
    elif args.operation == 'DELETE':
        pass
    elif args.operation == 'POST':
        pass
    elif args.operation == 'PUT':
        pass
    elif args.operation == 'DISCOVER':
        response = client.discover()
        print((response.pretty_print()))
        pass
    
    time.sleep(1)
    client.close()

if __name__ == '__main__':
    main()

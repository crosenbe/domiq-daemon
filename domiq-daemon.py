#!/usr/bin/python

#  Domiq Base Caching Daemon        by Claus Rosenberger
#
#  This daemon connects to Domiq Base and store all visible variables in a
#  cache dict. The daemon does listen itself for client requests and delivers
#  the variables from the cache dict, if the variable does not exist it try 
#  to fetch it from the Base.
#
#  1.0  - First release
#  1.1  - Complete rewrite with the twisted framework
#

from twisted.internet.protocol import Protocol, ReconnectingClientFactory, Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import Deferred
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from sys import stdout, argv, exit
from getopt import getopt, GetoptError
from time import time, sleep

class Controller:
    def __init__(self):
        self.__controller = {}
        self.client_protocol = None

    def add_entry(self, key, value):
        if self.__controller.has_key(key):
            print 'Refreshed ',key,':',value
        else:
            print 'Added ',key,':',value
        self.__controller[key] = [value, time()]

    def remove_entry(self, key):
        if self.__controller.has_key(key):
            del self.__controller[key]

    def get_entry(self, key):
        if self.__controller.has_key(key):
            return self.__controller[key][0]
        else:
            return None

    def garbage(self):
        """ remove all entries which are older as cachetime """
        print 'Starting garbage collector.'
        for key in self.__controller.keys():
            if time() - self.__controller[key][1] > cachetime:
                del self.__controller[key]
                print 'Removed ', key, ', caching period time expired'

    def show_all(self):
        return self.__controller

class CachingServer(LineReceiver):
    def __init__(self, controller):
        self.delimiter = '\n'
        self.__controller = controller

    def connectionMade(self):
        pass

    def connectionLost(self, reason):
        pass

    def lineReceived(self, line):
        self.handle_chat(line)

    def handle_chat(self, message):
        """ handle requests from clients """
        # syntax check
        if message == "?":
            for key in self.__controller.show_all().keys():
                self.sendLine('%s=%s' % (key, self.__controller.get_entry(key)))
            return

        if len(message.rsplit('=')) > 1:
            key = message.rsplit('=')[0]
            value = self.__controller.get_entry(key)
            if value is not None:
                self.buildResponse(key, value)
                return

            if self.__controller.client_protocol is not None:
                response = self.__controller.client_protocol.requestKey(key)
                response.addCallback(self.gotResponse)

    def buildResponse(self, key, value=None):
        if value is None:
            retval = '%s=not available' % (key)
        else:
            retval = '%s=%s' % (key, value)
        self.sendLine(retval)
        print 'send to client: ', retval

    def gotResponse(self, result):
        self.buildResponse(result[0], result[1])

class CachingServerFactory(Factory):
    def __init__(self, controller):
        self.__controller = controller

    def buildProtocol(self, addr):
        return CachingServer(controller)

class DomiqUplink(LineReceiver):
    def __init__(self, controller):
        self.__controller = controller
        self.__lc = LoopingCall(self.garbage)
        self.__lc.start(cachetime, False)
        self.__requestResult = {}

    def connectionMade(self):
        self.__controller.client_protocol = self
        #self.requestAll()

    def requestKey(self, key):
        d = Deferred()
        self.__requestResult[key] = d
        self.sendLine('%s=?' % (key))
        return d

    def requestAll(self):
        self.sendLine("?")

    def lineReceived(self, data):
        """ fill central database with values """
        key, value = data.split('=')
        self.__controller.add_entry(key,value)
        if key in self.__requestResult.keys():
            self.__requestResult[key].callback([key, value])
            del self.__requestResult[key]

    def garbage(self):
        #self.requestAll()
        #for key in self.__controller.show_all().keys():
        #    self.requestKey(key)
        self.__controller.garbage()

class DomiqClientFactory(ReconnectingClientFactory):
    def __init__(self, controller, caching_server):
        self.__controller = controller
        self.caching_server = caching_server

    def startedConnecting(self, connector):
        print 'Started to connect.'

    def buildProtocol(self, addr):
        print 'Connected.'
        print 'Resetting reconnection delay.'
        self.resetDelay()
        return DomiqUplink(self.__controller)

    def clientConnectionLost(self, connector, reason):
        print 'Lost connection. Reason: ', reason
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print 'Connection failed. Reason: ', reason
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

def usage():
    print 'Usage: domiq-proxy -d DOMIQHOST [OPTION]'
    print 'Start a proxy in background which is sniffing and caching the Domiq Base'
    print ''
    print '-d, --domiq-host         Domiq Base to connect to'
    print '-p, --domiq-port         port where Domiq Base is listening, default=4224'
    print '-l, --listen-port        port where local daemon should listen on, default=4224'
    print '-c, --cachetime          how long the retrieved values should hold in cache before'
    print '                         forcing a refresh, default=900, specifiy in seconds'
    print '-h, --help               display this help and exit'
    print ''
    exit(1)

def param(argv):

    global domiq_host
    global domiq_port
    global listen_port
    global cachetime

    try:
        opts, args = getopt(argv,"d:p:l:c:h",["domiq-host=","domiq-port=","listen-port=","cachetime=","help"])
    except GetoptError:
        usage()
    for opt,arg in opts:
        if opt in ("-h", "--help"):
            usage()
        elif opt in ("-d", "--domiq-host"):
            domiq_host = arg
        elif opt in ("-p", "--domiq-port"):
            domiq_port = int(arg)
        elif opt in ("-l", "--listen-port"):
            listen_port = int(arg)
        elif opt in ("-c", "--cachetime"):
            cachetime = int(arg)

    if domiq_host == '': usage()


if __name__ == '__main__':

    listen_port = 4224
    domiq_host = ''
    domiq_port = 4224
    cachetime = 900
    # parse parameters
    param(argv[1:])

    # define global caching database
    controller = Controller()

    caching_server = CachingServerFactory(controller)
    reactor.listenTCP(listen_port, caching_server)
    reactor.connectTCP(domiq_host,domiq_port, DomiqClientFactory(controller, caching_server))
    reactor.run()


#!/usr/bin/python

import sys, socket, time, threading, select, getopt

buffer_size = 1024
delay = 0.0001

class MySocket():

    def __init__(self):
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def connect(self):
        while True:
            try:
                self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.__sock.connect((domiq_host, domiq_port))
                break
            except Exception, e:
                print 'Error on connect:', e
		time.sleep(5)
                continue

    def disconnect(self):
        try:
            self.__sock.close()
        except Exception, e:
            print 'Error on disconnect:', e

    def sendall(self,content):
        while True:
            try:
                self.__sock.sendall(content)
                break
            except socket.error:
                self.disconnect()
                self.connect()

    def recv(self,buffersize):
        while True:
            try:
                return self.__sock.recv(buffersize)
            except socket.error:
                self.disconnect()
                self.connect()


class Uplink(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.uplink = MySocket()
        self.__stop = False
        self.__data = ''
        self.__cache = {}

    def stop(self):
        self.__stop = True

    def run(self):
        try:
            self.uplink.sendall('?\n')
        except Exception, e:
            print e

        while self.__stop == False:
            time.sleep(delay)
            self.__data += self.uplink.recv(buffer_size)
            if len(self.__data) == 0:
                break
            else:
                self.on_recv()

    def send_request(self,key):
        if not self.__cache.has_key(key):
            print 'no key send request to socket', key
            try:
                self.uplink.sendall('%s=?\n' % (key))
            except Exception, e:
                print e
                print self.uplink
        elif time.time() - self.__cache[key][1] > cachetime:
            print 'old cache send request to socket', key
            try:
                self.uplink.sendall('%s=?\n' % (key))
            except Exception, e:
                print e
                print self.uplink

    def cache_entry(self,key,value):
        self.__cache[key] = [value,time.time()]

    def get_entry(self,key):
        # get one entry from cache an delivers the value back
        self.send_request(key)
        time.sleep(0.1)
        return self.__cache.get(key,['NONE',0])[0]

    def on_recv(self):
        # split the input to key and value
        for element in self.__data.splitlines(True):
            if element.find('\r\n') > 0:     # if the line is complete
                data = element.rstrip('\r\n')
                key, value = data.split('=')
                self.cache_entry(key,value)
            else:  # store incomplete commands
                self.__data = element

class Server:

    input_list = []

    def __init__(self, host, port):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

    def main_loop(self, uplink):
        self.uplink = uplink
        self.input_list.append(self.server)
        while 1:
            time.sleep(delay)
            ss = select.select
            inputready, outputready, exceptready = ss(self.input_list, [], [])
            for self.s in inputready:
                if self.s == self.server:
                    self.on_accept()
                    break

                self.data = self.s.recv(buffer_size)
                if len(self.data) == 0:
                    pass
                    self.on_close()
                else:
                    self.on_recv()

    def on_close(self):
        self.input_list.remove(self.s)
        self.s.close()

    def on_accept(self):
        clientsock, clientaddr = self.server.accept()
        self.input_list.append(clientsock)

    def on_recv(self):
        if self.data.find('\n') > 0:    # command is complete
            line = self.data.splitlines()[0]
            if len(line.rsplit('=')) > 1:
                key = line.rsplit('=')[0]
                value = self.uplink.get_entry(key)
                self.s.sendall('%s=%s\n' % ( key, value ))
            else:
                self.s.sendall('not available\n')
            self.on_close()

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
    sys.exit(1)

def param(argv):

    global domiq_host
    global domiq_port
    global listen_port
    global cachetime

    try:
        opts, args = getopt.getopt(argv,"d:p:l:c:h",["domiq-host=","domiq-port=","listen-port=","cachetime=","help"])
    except getopt.GetoptError:
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
    param(sys.argv[1:])

    # start uplink to Domiq Base
    uplink = Uplink()
    uplink.daemon = True
    uplink.setDaemon(True)
    uplink.start()

    # start listening server
    server = Server('', listen_port)
    try:
        server.main_loop(uplink)
    except KeyboardInterrupt:
        print "Ctrl C - Stopping server"
        uplink.stop()
        uplink.join()
        sys.exit(1)



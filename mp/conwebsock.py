##
# The MIT License (MIT)
#
# Copyright (c) 2016 Stefan Wendler
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
##


import websocket
import threading
import time
import logging

from collections import deque
from mp.conbase import ConBase, ConError


class ConWebsock(ConBase, threading.Thread):

    def __init__(self, ip, password):

        ConBase.__init__(self)
        threading.Thread.__init__(self)

        self.daemon = True
        self.fifo_lock = threading.Lock()
        self.fifo = deque()
        self.ws = None
        self.active = True
        self.start()

        # websocket.enableTrace(logging.root.getEffectiveLevel() < logging.INFO)
        #websocket.enableTrace(True)

        success = False
        for t in range(5): # try 5 times
            print("Allocating new websocket.")
            self.ws = websocket.WebSocketApp("ws://%s:8266" % ip,
                                             on_message=self.on_message,
                                             on_error=self.on_error,
                                             on_close=self.on_close)
            self.ws.keep_running = True

            self.timeout = 5.0

            inp1 = self.read(256, blocking=False)
            if b'Password:' in inp1:
                self.ws.send(password + "\r")
                inp2 = self.read(256, blocking=False)
                if not b'WebREPL connected' in inp2:
                    pass
                else:
                    success = True
                    break;
            # reset socket and prepare to reconnect
            print("Retrying.")
            oldws = self.ws
            self.ws = None
            oldws.keep_running = False
            try:
                oldws.close()
            except:
                pass
            self.cleanup()

        if not success:
            self.close()
            raise ConError()

        # we were successful to connect
        self.timeout = 1.0

        logging.info("websocket connected to ws://{}:8266 after {} tries."
                     .format(ip,t))

    def run(self):
        while self.active:
            if self.ws is not None:
                print("Entering run loop.")
                self.ws.run_forever()
                print("Exiting run loop.")
            else:
                print("Waiting.")
                time.sleep(0.1)  # no busy waiting
                print("Waited.")

    def __del__(self):
        self.close()

    def on_message(self, ws, message):
        self.fifo.extend(message)

        try:
            self.fifo_lock.release()
        except:
            pass

    def on_error(self, ws, error):
        logging.error("websocket error: %s" % error)
        print("websocket error: %s" % error)

        try:
            self.fifo_lock.release()
        except:
            pass

    def cleanup(self):
        try:
            self.ws.close()
            self.fifo_lock.release()
        except:
            pass

    def on_close(self, ws):
        logging.info("websocket closed")
        print("on_close called.")
        self.cleanup()

    def close(self):
        print("Close called: active=False.")
        try:
            self.ws.send("\2")  # ctrl b to exit raw-repl
            time.sleep(0.1)
            # reset a potentially messed up repl
            self.ws.send("import webrepl; webrepl.stop(); webrepl.start()\r")
        except:
            pass
        self.active = False
        try:
            self.cleanup()
            self.join()
        except Exception:
            try:
                self.fifo_lock.release()
            except:
                pass

    def read(self, size=1, blocking=True):

        data = ''

        tstart = time.time()

        while (len(data) < size) and (time.time() - tstart < self.timeout):

            if len(self.fifo) > 0:
                data += self.fifo.popleft()
            elif blocking:
                self.fifo_lock.acquire()

        return data.encode("utf-8")

    def write(self, data):

        self.ws.send(data)
        return len(data)

    def inWaiting(self):
        return len(self.fifo)

    def survives_soft_reset(self):
        return False

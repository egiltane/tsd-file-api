# https://gist.github.com/bdarnell/5bb1bd04a443c4e06ccd

import os
import logging
import tornado.queues

from tornado.concurrent import Future
from tornado.escape import utf8
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import parse_command_line, define, options
from tornado.web import Application, RequestHandler, stream_request_body

from auth import verify_json_web_token

define('port', default=8888)
define('debug', default=True)
define('server_delay', default=0)
define('num_chunks', default=50)
define('max_body_size', 1024*1024*1024*5)

UPLOADS_FOLDER = '/Users/leondutoit/uploaded-files' # read from config
JWT_SECRET = 'testsecret' # read from config


class JWTIssuerHandler(RequestHandler):

    def get(self):
        self.write([{'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjogImFwcF91c2VyIiwgImVtYWlsIjogImhlYWx0aEBjaGVjay5sb2NhbCIsICJleHAiOiAxNDg4NDY0Nzc5fQ.mfzInWsSGPuiH4XVXOmzyZPLrwe-X6n5TaqLV-tDPak'}])


class FormDataHandler(RequestHandler):

    def prepare(self):
        auth_header = self.request.headers['Authorization']
        resp = verify_json_web_token(auth_header, JWT_SECRET, 'app_user', timeout=(60*60*24))
        if resp is not True:
            return resp


    def post(self):
        if len(self.request.files['file']) > 1:
            # only allow one file per request for now
            self.send_error()
        # TODO: check filename
        filename = self.request.files['file'][0]['filename']
        target = os.path.normpath(UPLOADS_FOLDER + '/' + filename)
        filebody = self.request.files['file'][0]['body']
        with open(target, 'ab+') as f:
            f.write(filebody)
        self.write({'message': 'file uploaded'})

    def on_finish(self):
        # called after response is returned to client
        # could notify an external worker here
        pass

@stream_request_body
class UploadHandler(RequestHandler):

    def prepare(self):
        logging.info('UploadHandler.prepare')

    @gen.coroutine
    def data_received(self, chunk):
        #logging.info('UploadHandler.data_received(%d bytes: %r)', len(chunk), chunk[:9])
        with open('out', 'ab+') as f:
            f.write(chunk)
        # could use this to slow the client down if needed
        # yield gen.Task(IOLoop.current().call_later, options.server_delay)

    def post(self):
        logging.info('UploadHandler.post')
        self.write('ok')

@stream_request_body
class ProxyHandler(RequestHandler):

    def prepare(self):
        logging.info('ProxyHandler.prepare')
        self.chunks = tornado.queues.Queue(1)
        self.fetch_future = AsyncHTTPClient().fetch(
            'http://localhost:%d/upload_stream' % options.port,
            method='POST',
            body_producer=self.body_producer,
            request_timeout=12000.0)

    @gen.coroutine
    def body_producer(self, write):
        while True:
            chunk = yield self.chunks.get()
            if chunk is None:
                return
            yield write(chunk)

    @gen.coroutine
    def data_received(self, chunk):
        #logging.info('ProxyHandler.data_received(%d bytes: %r)', len(chunk), chunk[:9])
        yield self.chunks.put(chunk)

    @gen.coroutine
    def post(self):
        logging.info('ProxyHandler.post')
        # Write None to the chunk queue to signal body_producer to exit,
        # then wait for the request to finish.
        yield self.chunks.put(None)
        response = yield self.fetch_future
        self.set_status(response.code)
        self.write(response.body)

def main():
    parse_command_line()
    app = Application([
        ('/upload_token', JWTIssuerHandler),
        ('/upload_stream', UploadHandler),
        ('/stream', ProxyHandler),
        ('/upload', FormDataHandler),
    ], debug=options.debug)
    app.listen(options.port, max_body_size=options.max_body_size)
    IOLoop.instance().start()

if __name__ == '__main__':
    main()

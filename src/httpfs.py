#############################################################################################
# Written by:
#   - Pierre-Olivier Trottier (40059235)
#   - Nimit Jaggi (40032159)
#############################################################################################

import argparse
import datetime
import os
import pathlib
import selectors
import socket
import sys
import types
from enum import Enum
from wsgiref.handlers import format_date_time


#############################################################################################
# Library Implementation
#############################################################################################


class HttpStatus(Enum):
    OK = (200, "OK")
    CREATED = (201, "Created")
    FORBIDDEN = (403, "Forbidden")
    NOT_FOUND = (404, "Not Found")
    INTERNAL_SERVER_ERROR = (500, "Internal Server Error")


# Default server host
__SERVER_HOST = 'localhost'
# Socket buffer size
__BUFFER_SIZE = 1024


# Allow multi-connections
selector = selectors.DefaultSelector()


# Initialize the server on the sockets
def start_server(host, port, verbose = False):
    # Open the socket
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Start the server
        listener.bind((host, port))
        listener.listen(5)

        if verbose:
            print(f'[INIT] HTTP File System server is listening at http://{host}:{port}')

        # Setup multi-connection
        listener.setblocking(False)
        selector.register(listener, selectors.EVENT_READ, data=None)

        # Listen to connections
        while True:
            events = selector.select(timeout=None)
            for key, mask in events:
                if key.data is None:
                    __accept_connection(key.fileobj, verbose)
                else:
                    __service_connection(key, mask, verbose)

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")

    finally:
        # Always close the socket
        listener.close()
        selector.close()


# Accept a client connection through the selector
def __accept_connection(listener, verbose):
    (conn, address) = listener.accept()

    if verbose:
        print("[CONNECTION] Accepted connection from", address)

    conn.setblocking(False)
    data = types.SimpleNamespace(addr=address, inb=b"", outb=b"")
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    selector.register(conn, events, data=data)


# Accept a service connection (Read or Write data)
def __service_connection(key, mask, verbose):
    sock = key.fileobj
    data = key.data

    # Read the request from the client
    if mask & selectors.EVENT_READ:
        # Get the response data from the request
        recv_data = __receive_connection(sock)
        if recv_data:
            data.outb += recv_data

    # Send the response to the client
    if mask & selectors.EVENT_WRITE:
        if data.outb:
            sent = sock.send(data.outb)
            data.outb = data.outb[sent:]
            if verbose and not data.outb:
                print('[RESPONSE] Response sent to client')

    # Close the connection if there is no more data to read or send back
    if not data.outb:
        selector.unregister(sock)
        sock.close()
        if verbose:
            print("[CONNECTION] Closed connection to", data.addr)



# Handler for client connections
def __receive_connection(sock):
    # Receive the byte array
    data = sock.recv(__BUFFER_SIZE)

    # Build a proper HTTP response from the request
    response = __build_response(data.decode())

    # Return the response back to the client
    return response.encode(encoding='UTF-8')


# Build a proper HTTP response
def __build_response(data, status = HttpStatus.OK):
    if not isinstance(status, HttpStatus):
        print("Invalid status given", status)
        sys.exit(1)

    # TODO Use the request data to do an action and build a response
    response = data
    # TODO Determine the content-type from the file name
    content_type = 'application/json;charset=utf-8'
    # TODO Determine the content-disposition from the file (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition)
    content_disposition = 'inline'
    # TODO Determine the proper response status
    response_status = status

    dt = datetime.datetime.utcnow()

    content = f'HTTP/1.1 {response_status.value[0]} {response_status.value[1]}\r\n' \
              f'Content-Type: {content_type}\r\n' \
              f'Content-Disposition: {content_disposition}\r\n' \
              f'Content-Length: {len(data)}\r\n' \
              f'Date: {format_date_time(dt.timestamp())}\r\n\r\n'
    content += response

    return content


#############################################################################################
# CLI Tool Implementation
#############################################################################################


# Access a values by doing "args.dir" or "args.port", etc.
def __parse_flags(path):
    parser = argparse.ArgumentParser(prog="httpfs")

    parser.add_argument("-v", "--verbose", help="Activate verbose mode", action="store_true")
    parser.add_argument("-p", "--port", help="Port to open the server on", type=int, default=1773)
    parser.add_argument("-d", "--dir", help="Path to shared directory", type=pathlib.Path, default=path)

    return parser.parse_args()


# CLI Entry Point
if __name__ == "__main__":
    # Normalize the script parent directory + "\.." + "shared"
    default_path = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir, 'shared'))

    flags = __parse_flags(default_path)

    if flags.verbose:
        print(f"[ARGS] Arguments: {flags}")

    start_server(__SERVER_HOST, flags.port, flags.verbose)

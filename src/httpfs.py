#############################################################################################
# Written by:
#   - Pierre-Olivier Trottier (40059235)
#   - Nimit Jaggi (40032159)
#############################################################################################

import argparse
import datetime
import os
import pathlib
import socket
import sys
import threading
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
__BUFFER_SIZE = 1


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

        # Keep listening for connections
        while True:
            (conn, address) = listener.accept()
            threading.Thread(target=__receive_connection, args=(conn, address, verbose)).start()

    finally:
        # Always close the socket
        listener.close()


# Handler for client connections
def __receive_connection(conn, address, verbose):
    if verbose:
        print('[CLIENT] New client connection from', address)

    try:
        # Receive the byte array
        data = __receive_data(conn)
        # Build a proper HTTP response from the request
        response = __build_response(data.decode(), HttpStatus.OK)
        # Send the response back to the client
        conn.sendall(response.encode(encoding='UTF-8'))

    finally:
        # If an error occurred, attempt to send an error response
        try:
            conn.sendall(__build_response('', HttpStatus.INTERNAL_SERVER_ERROR).encode(encoding='UTF-8'))
        # Always close the connection
        finally:
            print('[ERROR] An unknown error occurred while handling the client request')
            conn.close()

    if verbose:
        print('[RESPONSE] Response sent to client', response)


# Receive the byte array from the client connection
def __receive_data(conn):
    # Read the socket data byte by byte until we reach the end of the headers
    data = b''
    while b'\r\n\r\n' not in data:
        data += conn.recv(__BUFFER_SIZE)

    # Get a string from the header bytes without the empty lines
    header_data = data[:-4].decode()

    # Ignore the HTTP Version and Request Status
    header_strings = header_data.splitlines()[1:]

    # Build a dictionary from the string
    header_dictionary = {}
    for string in header_strings:
        header = string.split(': ')
        header_dictionary[header[0]] = header[1]

    # Create a dictionary from the headers
    content_length = None
    if 'Content-Length' in header_dictionary:
        content_length = int(header_dictionary.get('Content-Length'))

    # Receive the rest of the request
    if content_length:
        data += conn.recv(content_length)

    return data


# Build a proper HTTP response
def __build_response(data, status):
    if not isinstance(status, HttpStatus):
        print("Invalid status given", status)
        sys.exit(1)

    # TODO Use the request data to do an action and build a response
    response = data
    # TODO Determine the content-type from the file name
    content_type = 'application/json;charset=utf-8'
    # TODO Determine the content-disposition from the file (https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition)
    content_disposition = 'inline'

    dt = datetime.datetime.utcnow()

    content = f'HTTP/1.1 {status.value[0]} {status.value[1]}\r\n' \
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

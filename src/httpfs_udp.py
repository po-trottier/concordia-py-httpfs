#############################################################################################
# Written by:
#   - Pierre-Olivier Trottier (40059235)
#   - Nimit Jaggi (40032159)
#############################################################################################


import argparse
import datetime
import json
import mimetypes
import os
import pathlib
import re
import selectors
import socket
import sys
import types
from enum import Enum
from wsgiref.handlers import format_date_time


#############################################################################################
# Library Implementation
#############################################################################################


# Subset of the valid HTTP Status Codes
class HttpStatus(Enum):
    OK = (200, "OK")
    CREATED = (201, "Created")
    FORBIDDEN = (403, "Forbidden")
    BAD_REQUEST = (400, "Bad Request")
    NOT_FOUND = (404, "Not Found")
    INTERNAL_SERVER_ERROR = (500, "Internal Server Error")


# Subset of the valid HTTP Verbs
class HttpVerb(Enum):
    GET = "GET"
    POST = "POST"


# Default server host
__SERVER_HOST = 'localhost'
# Socket buffer size
__BUFFER_SIZE = 1024
# Mime types to return inline
__INLINE_MIME_TYPES = [
    'text/css',
    'text/html',
    'application/json',
    'text/javascript',
    'text/plain',
    'application/xhtml+xml',
    'application/xml',
    'text/xml'
]


# Allow multi-connections
selector = selectors.DefaultSelector()


# Initialize the server on the sockets
def start_server(host, port, path, verbose = False):
    # Open the socket
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # Start the server
        listener.bind((host, port))

        if verbose:
            # noinspection HttpUrlsUsage
            print(f'[INIT] HTTP File System server is listening at http://{host}:{port}')

        # Listen to connections
        while True:
            response, connection = __receive_connection(listener, path, verbose)

            listener.sendto(response, connection)

            if verbose:
                # noinspection HttpUrlsUsage
                print(f'[CLIENT] Response sent to {connection}')

    finally:
        # Always close the socket
        listener.close()

# Handler for client connections
def __receive_connection(sock, path, verbose):
    # Receive the byte array
    headers, body, connection = __receive_data(sock, verbose)
    # Build a proper HTTP response from the request
    response = __build_response(headers, body, path, verbose)
    # Return the response back to the client
    if verbose:
        print("[CONNECTION] Connection received")
    return response, connection


# Receive the byte array from the client connection
def __receive_data(sock, verbose):
    # Read the socket data byte by byte until we reach the end of the headers
    data, address = sock.recvfrom(__BUFFER_SIZE)

    headers_buffer = b''
    for byte in data:
        if b'\r\n\r\n' in headers_buffer:
            break
        headers_buffer += byte.to_bytes(1, sys.byteorder)

    # Get a string from the header bytes without the empty lines
    header_data = headers_buffer[:-4].decode()

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
    body_buffer = b''
    if content_length:
        body_buffer += sock.recvfrom(content_length)

    if verbose:
        # noinspection HttpUrlsUsage
        print(f'[DATA] Data received from {address}')

    return headers_buffer, body_buffer, address


# Build a proper HTTP response
def __build_response(headers, body, path, verbose):
    # Get a request dictionary from the raw request
    request = __parse_request(headers.decode(), verbose)
    # Handle the request appropriately
    response = __handle_request(request, body, path)

    dt = datetime.datetime.utcnow()

    # Build the text-based part of the request
    content_string = f'HTTP/1.1 {response["response_status"][0]} {response["response_status"][1]}\r\n' \
              f'Content-Type: {response["content_type"]}\r\n' \
              f'Content-Disposition: {response["content_disposition"]}\r\n' \
              f'Content-Length: {len(response["response_body"])}\r\n' \
              f'Date: {format_date_time(dt.timestamp())}\r\n\r\n'

    # Convert to a byte array
    content = bytearray(content_string.encode())
    # Add the binary part of the request
    content += response["response_body"]

    if verbose:
        print("[RESPONSE] Response created")

    return content


def __parse_request(request, verbose):
    lines = request.splitlines()

    # Use REGEX to parse the request pattern
    match = re.search('^([A-Z]+) (.+) HTTP/\d\.?\d?$', lines[0])
    if verbose:
        print("[REQUEST] Request parsed ")

    return {
        'verb': match.group(1),
        'path': match.group(2)
    }


def __handle_request(request, body, path):
    # Default Values
    response = {
        'content_type': 'application/json;charset=utf-8',
        'content_disposition': 'inline',
        'response_status': HttpStatus.BAD_REQUEST.value,
        'response_body': json.dumps({
            'error': 'Unknown HTTP verb received. The supported verbs are GET, POST.'
        }).encode()
    }

    # Get the full request path by merging the base path and the request
    full_path = pathlib.Path(os.path.normpath(pathlib.Path(str(path) + request['path'])))

    # Make sure the use doesn't go out of the base path
    if str(path) not in str(full_path):
        response['response_status'] = HttpStatus.FORBIDDEN.value
        response['response_body'] = json.dumps({
            'error': 'The requested path is not accessible.'
        }).encode()
        return response

    # Read a given file or list the directory
    if request['verb'] == HttpVerb.GET.value:
        if full_path.is_dir():
            return __list_directory(full_path)
        else:
            return __read_file(full_path)

    # Write/Create a given file
    if request['verb'] == HttpVerb.POST.value:
        if not full_path.is_dir():
            return __write_file(full_path, body)
        else:
            response['response_body'] = json.dumps({
                'error': 'The requested path represents a directory. The path must represent a file to work correctly.'
            }).encode()
            return response

    return response


def __list_directory(path):
    # Common response values
    response = {
        'content_type': 'application/json;charset=utf-8',
        'content_disposition': 'inline'
    }

    try:
        children = []
        # For every child int the directory
        for child in path.iterdir():
            # Add an object with the name and type of the child
            children.append({'name': child.name, 'is_directory': child.is_dir()})
        # Add these values to the response
        response['response_body'] = json.dumps(children).encode()
        response['response_status'] = HttpStatus.OK.value

    # If an exception occurs set the response status as Internal Server Error
    except IOError as e:
        response['response_status'] = HttpStatus.INTERNAL_SERVER_ERROR.value
        response['response_body'] = json.dumps({
            'error': 'An unknown error occurred while listing the directory contents.',
            'details': str(e)
        }).encode()

    return response


def __read_file(path, verbose):
    # Common response values
    response = {
        'content_type': 'application/json;charset=utf-8',
        'content_disposition': 'inline'
    }

    # If the path doesn't exist we're trying to read a file that doesn't exist
    if not path.exists():
        response['response_status'] = HttpStatus.NOT_FOUND.value
        response['response_body'] = json.dumps({
            'error': 'The requested file was not found.'
        }).encode()
        return response

    try:
        # Guess the Mime Type from the file extension
        mime_type = mimetypes.guess_type(path)[0]

        # Read the file
        with open(path, 'rb') as file:
            file_content = file.read()
            # Get the content disposition based on the Mime Type
            response['content_disposition'] = __get_content_disposition(mime_type, path)
            response['response_body'] = file_content
            response['content_type'] = mime_type
            response['response_status'] = HttpStatus.OK.value

    # If an error occurs return an Internal Server Error
    except IOError as e:
        response['content_disposition'] = 'inline'
        response['response_status'] = HttpStatus.INTERNAL_SERVER_ERROR.value
        response['response_body'] = json.dumps({
            'error': 'An unknown error occurred while reading the file contents.',
            'details': str(e)
        }).encode()
        return response

    if verbose:
        print("[RESPONSE] Response has been created")

    return response


def __write_file(path, content, verbose):
    # Common response values
    response = {
        'content_type': 'application/json;charset=utf-8',
        'content_disposition': 'inline'
    }

    try:
        # Determine if the file will be overwritten or created
        created = not path.exists()
        # Create all the parent directories required
        path.parent.mkdir(parents=True, exist_ok=True)

        # Start writing the file
        with open(path, 'wb') as file:
            file.write(content)
            response['response_status'] = HttpStatus.CREATED.value if created else HttpStatus.OK.value
            response['response_body'] = json.dumps({
                'success': f'The file was {"created" if created else "overwritten"}.'
            }).encode()


    # If an error occurs return an Internal Server Error
    except IOError as e:
        response['content_disposition'] = 'inline'
        response['response_status'] = HttpStatus.INTERNAL_SERVER_ERROR.value
        response['response_body'] = json.dumps({
            'error': 'An unknown error occurred while writing the file contents.',
            'details': str(e)
        }).encode()
        return response
    if verbose:
        print("[")

    return response


def __get_content_disposition(mime, path):
    # Only return a given subset of Mime Types inline
    if mime in __INLINE_MIME_TYPES:
        return 'inline'
    # Return the rest as attachments
    else:
        return f'attachment; filename="{path.name}"'


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
    # Get the root of the repository + "\shared"
    default_path = pathlib.Path(__file__).parent.parent.joinpath('shared')

    flags = __parse_flags(default_path)

    if flags.verbose:
        print(f"[ARGS] Arguments: {flags}")

    start_server(__SERVER_HOST, flags.port, flags.dir, flags.verbose)

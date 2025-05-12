import argparse
import os
import selectors
import signal
import socket
import sys
import logging

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument("--socket_fileno", required=True)
parser.add_argument("--public_dir", required=True)
args = parser.parse_args()

listen_fd = int(args.socket_fileno)
public_dir = args.public_dir

listen_sock = socket.socket(fileno=listen_fd)
listen_sock.setblocking(False)

sel = selectors.DefaultSelector()

def accept(sock: socket.socket):
    while True:
        try:
            conn, addr = sock.accept()
        except BlockingIOError: # another worker has accepted socket
            break
        conn.setblocking(False)
        sel.register(conn, selectors.EVENT_READ, read)
        logging.debug(f"[{os.getpid()}] accepted from {addr}")

def read(conn: socket.socket):
    try:
        data = conn.recv(4096)
    except BlockingIOError: # not ready yet
        return

    if not data:
        sel.unregister(conn)
        conn.close()
        return

    # I don't want to bother with doing actual http parsing
    data_split = data.decode("utf-8").split(' ')[:2]
    file_name = os.path.join(public_dir, data_split[1][1:])
    file_size = 0
    if os.path.isfile(file_name):
        file_size = os.stat(file_name).st_size
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Length: {file_size}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
    else:
        header = (
            f"HTTP/1.1 400 Bad Request\r\n"
            f"Content-Length: 0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        sel.unregister(conn)
        conn.close()
        return

    # chatgpt hack: temporarily switch to blocking mode so sendall/sendfile works on mac
    conn.setblocking(True)
    conn.sendall(header)

    # sendfile is zero-copy, it keeps filedata in kernel space during tranfer
    # usually id use conn.sendfile but there is a mac impl bug in the library
    infd = os.open(file_name, os.O_RDONLY)
    offset = 0
    try:
        while offset < file_size:
            sent = os.sendfile(conn.fileno(), infd, offset, file_size - offset)
            offset += sent
    finally:
        os.close(infd)

    conn.setblocking(False)
    sel.unregister(conn)
    conn.close()

# graceful exit
def sigterm_handler(signum, _frame):
    logging.info(f"[{os.getpid()}] received SIGTERM – shutting down")
    sel.close()
    listen_sock.close()
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)

sel.register(listen_sock, selectors.EVENT_READ, accept)
logging.debug(f"[{os.getpid()}] Worker running, serving on port {listen_sock.getsockname()[1]}")

while True:
    events = sel.select(timeout=1)
    for key, _ in events:
        callback = key.data # accept / read
        callback(key.fileobj) 

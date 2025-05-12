import os
import sys
import socket
import signal
import time
import argparse
import logging

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument("--port", required=True, default=3000, type=int)
parser.add_argument("--num_workers", required=True, default=4, type=int)
parser.add_argument("--public_dir", required=True)
args = parser.parse_args()

def create_http_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # reuses address, similar to nginx
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1) # reuses port
    sock.bind(("0.0.0.0", port))
    sock.listen(socket.SOMAXCONN)
    sock.setblocking(False)
    sock.set_inheritable(True) 
    return sock
 
listen_sock = create_http_socket(args.port)
worker_pids = []
running = True

# graceful shitdown
def shutdown_handler(signum, _frame):
    global running
    logging.info(f"\n[MASTER] Initiating shutdown …")
    running = False

def reap_children(signum, _frame):
    # go last of us on these zombie processes
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            if pid in worker_pids:
                worker_pids.remove(pid)
                logging.info(f"[MASTER] Worker {pid} exited")
        except ChildProcessError:
            break

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGCHLD, reap_children)

# spawn children
worker_py = os.path.join(os.path.dirname(__file__), "worker.py")
fd = str(listen_sock.fileno())

for i in range(args.num_workers):
    pid = os.fork()
    if pid == 0:
        os.execv(
            sys.executable,
            [
                sys.executable,
                worker_py,
                "--socket_fileno",
                fd,
                "--public_dir",
                args.public_dir,
            ],
        )
        # the following will only get interpreted if execv failed, so error
        logging.info("[MASTER] execv failed", file=sys.stderr)
        os._exit(1)
    else:
        logging.info(f"[MASTER] Spawned worker PID {pid}")
        worker_pids.append(pid)

# master's job is done, it stays alive till Ctrl-C
try:
    while running:
        time.sleep(1)
except KeyboardInterrupt:
    running = False

# if python interpreter is here, I sigtermed
logging.info("[MASTER] SIGTERM -> workers")
for pid in worker_pids:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

# wait for remaining workers to exit
while worker_pids:
    reap_children(None, None)  # harvest anything that’s ready
    time.sleep(0.1)

logging.info("[MASTER] All workers exited.... closing socket.")
listen_sock.close()

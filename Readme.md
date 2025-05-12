# minginx-py

`minginx-py` is a minimal Python implementation inspired by Nginx, I wrote this to help me understand modern web server architecture.

### Why minginx-py?

Understand how event-driven servers differ from traditional (e.g., Apache) architectures.

Learn fundamental concepts: event loops, selectors, process handling, and socket programming.

### How It Works

A master process manages worker processes.

Workers handle incoming HTTP requests concurrently without creating new processes per request, enabling efficient scalability.

### Quickstart

Place your static files in the configured public directory, configure and then run:

`python master.py --port 3000 --num_workers 4 --public_dir <PATH_TO_FOLDER_WITH_FILES>`

Then, simply go to `http://localhost:3000/<file.xyz>`.

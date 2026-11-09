"""Serve the built Pyodide app locally; the editor runs only in the browser."""
import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8868)
    parser.add_argument('--directory', type=Path, default=Path('dist/pyodide'))
    args = parser.parse_args()
    if not (args.directory / 'index.html').is_file():
        parser.error('Build the static site first: see README.md')
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(args.directory.resolve()))
    print(f'Open http://localhost:{args.port}', flush=True)
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()

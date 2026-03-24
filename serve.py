#!/usr/bin/env python3
"""
Simple HTTP server for HLS streaming.

Serves HLS manifests and segments with appropriate MIME types.
Runs on localhost:8080 by default.

Author: Goutham Soratoor
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path


class HLSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with HLS-aware MIME types."""

    MIME_TYPES = {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
    }

    def end_headers(self) -> None:
        """Add CORS headers to response."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.end_headers()

    def guess_type(self, path: str) -> str:
        """Override MIME type guessing for HLS files."""
        for ext, mime_type in self.MIME_TYPES.items():
            if path.endswith(ext):
                return mime_type

        return super().guess_type(path)

    def log_message(self, format: str, *args: object) -> None:
        """Log HTTP requests."""
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self) -> None:
        """Serve player.html at root instead of directory listing."""
        if self.path in ("/", ""):
            self.path = "/player.html"
        super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
    """TCP server that can re-bind to a recently used port."""

    allow_reuse_address = True


def run_server(port: int = 8080) -> None:
    """Start HTTP server for HLS streaming.
    
    Args:
        port: Port number to listen on (default: 8080)
    """
    os.chdir(Path(__file__).parent)

    Handler = HLSRequestHandler

    with ReusableTCPServer(("", port), Handler) as httpd:
        print(f"HLS Server running at http://localhost:{port}")
        print(f"Serving from: {Path.cwd()}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")
            sys.exit(0)


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)

    run_server(port)

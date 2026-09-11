#!/usr/bin/env python3
"""Small byte-blind TCP relay for CDP HTTP and WebSocket traffic."""

from __future__ import annotations

import argparse
import select
import socket
import socketserver


class RelayHandler(socketserver.BaseRequestHandler):
    target: tuple[str, int]
    chunk_size = 1024 * 1024
    high_water_mark = 4 * chunk_size

    def handle(self) -> None:
        try:
            upstream = socket.create_connection(self.target, timeout=10)
        except OSError:
            return

        with upstream:
            self.request.setblocking(False)
            upstream.setblocking(False)
            peers = {self.request: upstream, upstream: self.request}
            outgoing = {self.request: bytearray(), upstream: bytearray()}
            readable = set(peers)
            shutdown_after_write: set[socket.socket] = set()

            while readable or any(outgoing.values()):
                # Pause a reader when its peer has queued enough data. This
                # keeps memory bounded while still accepting very large frames.
                readers = [
                    stream for stream in readable
                    if len(outgoing[peers[stream]]) < self.high_water_mark
                ]
                writers = [stream for stream, data in outgoing.items() if data]
                try:
                    can_read, can_write, _ = select.select(readers, writers, [], 30)
                except (OSError, ValueError):
                    return

                for source in can_read:
                    try:
                        data = source.recv(self.chunk_size)
                    except BlockingIOError:
                        continue
                    except (ConnectionError, OSError):
                        return
                    if data:
                        outgoing[peers[source]].extend(data)
                    else:
                        readable.discard(source)
                        destination = peers[source]
                        if outgoing[destination]:
                            shutdown_after_write.add(destination)
                        else:
                            try:
                                destination.shutdown(socket.SHUT_WR)
                            except OSError:
                                pass

                for destination in can_write:
                    try:
                        sent = destination.send(outgoing[destination])
                    except BlockingIOError:
                        continue
                    except (ConnectionError, OSError):
                        return
                    if sent == 0:
                        return
                    del outgoing[destination][:sent]
                    if not outgoing[destination] and destination in shutdown_after_write:
                        shutdown_after_write.remove(destination)
                        try:
                            destination.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass


class ThreadingRelay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = type("ConfiguredRelayHandler", (RelayHandler,), {
        "target": (args.target_host, args.target_port)
    })
    with ThreadingRelay((args.listen_host, args.listen_port), handler) as server:
        server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()

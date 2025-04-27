from __future__ import annotations
import argparse
import asyncio
from asyncio.streams import StreamReader, StreamWriter
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable, Coroutine
from typing import Any

CRLF = "\r\n"
REQ_LINE_200 = b"HTTP/1.1 200 OK"

def extract_params(requested_target: str) -> str | None:
    if requested_target.count("/") == 1:
        return None
    return requested_target.split("/")[-1]


class HTTPHeader(Enum):
    HOST = "Host"
    USER_AGENT = "User-Agent"
    ACCEPT = "Accept"
    CONTENT_TYPE = "Content-Type"
    CONTENT_LENGTH = "Content-Length"


class HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


@dataclass
class Request:
    method: HTTPMethod
    target: str
    headers: dict[str, str]
    body: list[str]
    params: str | None
    version: str = "HTTP/1.1"


class TargetNotFoundException(Exception):
    pass


type Route = Callable[..., Coroutine[Any, Any, bytes]]


class HTTPServer:
    def __init__(self, port: int, directory: str, bufsize: int = 1024) -> None:
        self.port = port
        self.directory = directory
        self.bufsize = bufsize
        self.routes: dict[str, Route] = {
            "/": self.home,
            "/echo": self.echo,
            "/user-agent": self.user_agent,
            "/files": self.files,
        }

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, "localhost", self.port)
        print("Started server")
        async with server:
            await server.serve_forever()

    async def make_bad_request(
        self, status_code: int = 404, reason: str = "Not Found"
    ) -> bytes:
        return f"HTTP/1.1 {status_code} {reason}{CRLF}{CRLF}".encode()

    async def home(self, request: Request) -> bytes:
        return f"HTTP/1.1 200 OK{CRLF}{CRLF}".encode()

    async def echo(self, request: Request) -> bytes:
        params = request.params
        if params is None:
            return await self.make_bad_request(status_code=400, reason="Bad Request")
        resp = REQ_LINE_200
        resp += CRLF.encode()
        resp += f"Content-Type: text/plain{CRLF}".encode()
        resp += f"Content-Length: {len(params)}{CRLF}".encode()
        resp += CRLF.encode()
        resp += params.encode()
        return resp

    async def files(self, request: Request) -> bytes:
        if not request.params:
            return await self.make_bad_request(400, "Bad Request")
        path = f"{self.directory}/{request.params}"
        try:
            with open(path, "r") as f:
                content = f.read().encode()
        except FileNotFoundError:
            return await self.make_bad_request()
        resp = REQ_LINE_200
        resp += CRLF.encode()
        resp += f"{HTTPHeader.CONTENT_TYPE.value}: application/octet-stream{CRLF}".encode()
        resp += f"{HTTPHeader.CONTENT_LENGTH.value}: {len(content)}{CRLF}".encode()
        resp += CRLF.encode()

        # body
        resp += content
        return resp
        

    async def user_agent(self, request: Request) -> bytes:
        try:
            user_agent = request.headers[HTTPHeader.USER_AGENT.value]
        except KeyError:
            return await self.make_bad_request()

        resp = REQ_LINE_200
        resp += CRLF.encode()
        resp += f"{HTTPHeader.CONTENT_TYPE.value}: text/plain {CRLF}".encode()
        resp += f"{HTTPHeader.CONTENT_LENGTH.value}: {len(user_agent)} {CRLF}".encode()
        resp += CRLF.encode()

        # body
        resp += user_agent.encode()
        return resp

    async def parse_request(self, req: bytes) -> Request:
        data = req.decode().split(CRLF)
        req_line = data.pop(0)
        method, raw_target, version = req_line.split(" ")

        maybe_params = extract_params(raw_target)
        if maybe_params is not None:
            target = raw_target.removesuffix(f"/{maybe_params}")
        else:
            target = raw_target

        if not target in self.routes:
            raise TargetNotFoundException

        headers: dict[str, str] = {}
        body: list[str] = []
        for line in data:
            if ": " in line:
                k, v = line.split(": ")
                headers[k] = v
            else:
                body.append(line)
        return Request(HTTPMethod(method), target, headers, body, maybe_params, version)

    async def handle_client(self, reader: StreamReader, writer: StreamWriter) -> None:
        while True:
            raw_data = await reader.read(self.bufsize)
            if not raw_data:
                print(f"Client disconnected")
                break
            try:
                request = await self.parse_request(raw_data)
            except TargetNotFoundException:
                writer.write(await self.make_bad_request())
                await writer.drain()
            else:
                func = self.routes[request.target]
                resp = await func(request)
                writer.write(resp)
                await writer.drain()


if __name__ == "__main__":
    parser = argparse.ArgumentParser("HTTP server")
    parser.add_argument("--directory")
    args = parser.parse_args()
    server = HTTPServer(port=4221, directory=args.directory)
    asyncio.run(server.start())

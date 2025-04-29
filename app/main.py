from __future__ import annotations
import argparse
import asyncio
from asyncio.streams import StreamReader, StreamWriter
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec

CRLF = "\r\n"
RESP_LINE_200 = b"HTTP/1.1 200 OK"
RESP_LINE_201 = b"HTTP/1.1 201 Created"
SUPPORTED_ENCODINGS = ["gzip"]

def extract_params(requested_target: str) -> str | None:
    if requested_target.count("/") == 1:
        return None
    return requested_target.split("/")[-1]


class HTTPHeader(Enum):
    HOST = "Host"
    USER_AGENT = "User-Agent"
    ACCEPT = "Accept"
    ACCEPT_ENCODING = "Accept-Encoding"
    CONTENT_ENCODING = "Content-Encoding"
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
    body: str
    params: str | None
    version: str = "HTTP/1.1"


class TargetNotFoundException(Exception):
    pass

class MissingParamsException(Exception):
    pass

class MissingHeaderException(Exception):
    pass

class ResourceNotFoundException(Exception):
    pass

type Route = Callable[..., Coroutine[Any, Any, bytes]]
type RouteDirectory = dict[HTTPMethod, dict[str, Route]]
TArgs = ParamSpec("TArgs")

class HTTPServer:
    def __init__(self, port: int, directory: str, bufsize: int = 1024) -> None:
        self.port = port
        self.directory = directory
        self.bufsize = bufsize
        self.routes: RouteDirectory = {
            HTTPMethod.GET: {
                "/": self.home,
                "/echo": self.echo,
                "/user-agent": self.user_agent,
                "/files": self.get_file,
            },
            HTTPMethod.POST: {
                "/files": self.post_file, 
            }
        }

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, "localhost", self.port)
        print("Started server")
        async with server:
            await server.serve_forever()

    @staticmethod
    async def make_bad_request(status_code: int, reason: str) -> bytes:
        return f"HTTP/1.1 {status_code} {reason}{CRLF}{CRLF}".encode()

    @staticmethod
    def route(retcode: int = 200, declared_content_type: str = "text/plain") -> Callable[[Route], Route]:
        def decorator(func: Route) -> Route:
            async def wrapper(self: Any, request: Request) -> bytes:
                try:
                    ret = await func(self, request)
                except (MissingParamsException, MissingHeaderException):
                    return await HTTPServer.make_bad_request(status_code=400, reason="Bad Request")
                except ResourceNotFoundException:
                    return await HTTPServer.make_bad_request(status_code=404, reason="Not Found")

                if retcode == 200:
                    resp = RESP_LINE_200
                elif retcode == 201:
                    resp = RESP_LINE_201
                else:
                    raise ValueError(f"Return code {retcode} not supported")

                resp += CRLF.encode()

                if (requested_content_type := request.headers.get(HTTPHeader.CONTENT_TYPE.value)) is not None:
                    resp += f"{HTTPHeader.CONTENT_TYPE.value}: {requested_content_type}{CRLF}".encode()
                elif requested_content_type is None and len(ret) > 0:
                    # If not set by the client, we set it ourselves 
                    resp += f"{HTTPHeader.CONTENT_TYPE.value}: {declared_content_type}{CRLF}".encode()
                else:
                    pass

                if (requested_content_encoding_raw := request.headers.get(HTTPHeader.ACCEPT_ENCODING.value)) is not None:
                    requested_content_encodings = requested_content_encoding_raw.split(", ")
                    try:
                        content_encoding_match = next(filter(lambda enc: enc in SUPPORTED_ENCODINGS, requested_content_encodings))
                        resp += f"{HTTPHeader.CONTENT_ENCODING.value}: {content_encoding_match}{CRLF}".encode()
                    except StopIteration:
                        print("None of the requested encodings are supported")

                resp += f"{HTTPHeader.CONTENT_LENGTH.value}: {len(ret)}{CRLF}".encode()
                resp += CRLF.encode()

                resp += ret

                return resp
            return wrapper
        return decorator

    @route()
    async def home(self, request: Request) -> bytes:
        return b""

    @route()
    async def echo(self, request: Request) -> bytes:
        params = request.params
        if params is None:
            raise MissingParamsException
        return params.encode()

    @route(declared_content_type="application/octet-stream")
    async def get_file(self, request: Request) -> bytes:
        if not request.params:
            raise MissingParamsException
        
        path = f"{self.directory}/{request.params}"
        try:
            with open(path, "r") as f:
                content = f.read().encode()
        except:
            raise ResourceNotFoundException
        
        return content
    
    @route(retcode=201, declared_content_type="application/octet-stream")
    async def post_file(self, request: Request) -> bytes:
        if not request.params:
            raise MissingParamsException
        
        path = f"{self.directory}/{request.params}"
        with open(path, "w") as f:
            f.write(request.body)
        return b"" # TODO should be able to return None
        

    @route()
    async def user_agent(self, request: Request) -> bytes:
        try:
            user_agent = request.headers[HTTPHeader.USER_AGENT.value]
        except KeyError:
            raise MissingHeaderException
        return user_agent.encode()

    async def parse_request(self, req: bytes) -> Request:
        data = req.decode().split(CRLF)
        req_line = data.pop(0)
        raw_method, raw_target, version = req_line.split(" ")

        maybe_params = extract_params(raw_target)
        if maybe_params is not None:
            target = raw_target.removesuffix(f"/{maybe_params}")
        else:
            target = raw_target

        method = HTTPMethod(raw_method)
        if not target in self.routes[method]:
            raise TargetNotFoundException

        headers: dict[str, str] = {}
        body: str = ""
        for line in data:
            if ": " in line:
                k, v = line.split(": ")
                headers[k] = v
            elif line == "":
                continue
            else:
                body = line

        return Request(method, target, headers, body, maybe_params, version)

    async def handle_client(self, reader: StreamReader, writer: StreamWriter) -> None:
        while True:
            raw_data = await reader.read(self.bufsize)
            if not raw_data:
                print(f"Client disconnected")
                break
            try:
                request = await self.parse_request(raw_data)
            except TargetNotFoundException:
                writer.write(await HTTPServer.make_bad_request(404, "Not Found"))
                await writer.drain()
            else:
                func = self.routes[request.method][request.target]
                resp = await func(request)
                writer.write(resp)
                await writer.drain()


if __name__ == "__main__":
    parser = argparse.ArgumentParser("HTTP server")
    parser.add_argument("--directory")
    args = parser.parse_args()
    server = HTTPServer(port=4221, directory=args.directory)
    asyncio.run(server.start())

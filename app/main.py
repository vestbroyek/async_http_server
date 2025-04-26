from dataclasses import dataclass
import socket  # noqa: F401

CRLF = "\r\n"

# Route has any number of words and optionally query params; the last value is the param
@dataclass
class Endpoint:
    path: str
    accepts_params: bool

ENDPOINTS = [Endpoint("/", False), Endpoint("echo", True)]

def is_valid_target(requested_target: str) -> bool:
    if requested_target == "/":
        return True
    elif requested_target.startswith("/echo/"):
        return True
    else:
        return False
    
def has_params(requested_target: str) -> bool:
    return requested_target.count("/") > 1

def extract_params(requested_target: str) -> str:
    return requested_target.split("/")[-1]

def main():
    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    print("Started server")
    conn, addr = server_socket.accept() # wait for client
    with conn:
        print(f"Connected by {addr}")
        while True:
            raw_data = conn.recv(1024)
            data = raw_data.decode().split(CRLF)
            req_line = data.pop(0)
            method, target, version = req_line.split(" ")
            if not is_valid_target(target):
                resp = b"HTTP/1.1 404 Not Found\r\n\r\n"
            else:
                if not has_params(target):
                    resp = b"HTTP/1.1 200 OK\r\n\r\n"
                else:
                    params = extract_params(target)
                    resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    resp += f"Content-Length: {len(params)}\r\n\r\n".encode()
                    resp += params.encode()
            conn.sendall(resp)
        

if __name__ == "__main__":
    main()
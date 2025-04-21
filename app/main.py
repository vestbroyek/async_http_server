import socket  # noqa: F401

CRLF = "\r\n"
VALID_TARGETS = ["/"]

def parse_request_line(req_line: str) -> list[str]:
    return req_line.split(" ")

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
            if target in VALID_TARGETS:
                resp = b"HTTP/1.1 200 OK\r\n\r\n"
            else:
                resp = b"HTTP/1.1 404 Not Found\r\n\r\n"
            conn.sendall(resp)
            


if __name__ == "__main__":
    main()
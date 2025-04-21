import socket  # noqa: F401

CRLF = b"\r\n"


def main():
    print("Logs from your program will appear here!")

    server_socket = socket.create_server(("localhost", 4221), reuse_port=True)
    conn, addr = server_socket.accept() # wait for client
    with conn:
        print(f"Connected by {addr}")
        resp = b"HTTP/1.1 200 OK \r\n"
        conn.sendall(resp)


if __name__ == "__main__":
    main()
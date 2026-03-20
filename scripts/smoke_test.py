import hashlib
import json
import os
import socket
import time


def recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break

    if not data:
        raise RuntimeError("No response from server")

    return bytes(data).split(b"\n", 1)[0].decode("utf-8")


def build_command(base_command: str, token: str) -> str:
    if not token:
        return base_command
    parts = base_command.split(" ", 1)
    return f"{parts[0]} {token}" + (f" {parts[1]}" if len(parts) > 1 else "")


def send_command(command_line: str, payload: bytes = b"") -> dict:
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "4000"))
    token = os.getenv("AUTH_TOKEN", "")

    command_line = build_command(command_line, token)

    with socket.create_connection((host, port), timeout=20) as sock:
        sock.sendall((command_line + "\n").encode("utf-8"))
        if payload:
            sock.sendall(payload)

        line = recv_line(sock)
        return json.loads(line)


def require_ok(response: dict) -> None:
    if not response.get("ok"):
        raise RuntimeError(response.get("error", "Unknown server error"))


def main() -> None:
    payload = b"ci-smoke-test-payload\n"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = f"smoke-{int(time.time())}.txt"

    upload_response = send_command(f"SEND {filename} {len(payload)} {checksum}", payload=payload)
    require_ok(upload_response)

    list_response = send_command("LIST")
    require_ok(list_response)
    names = {item.get("name") for item in list_response.get("files", [])}
    if filename not in names:
        raise RuntimeError(f"Uploaded file {filename} not found in list")

    delete_response = send_command(f"DELETE {filename}")
    require_ok(delete_response)

    list_after_delete = send_command("LIST")
    require_ok(list_after_delete)
    names_after_delete = {item.get("name") for item in list_after_delete.get("files", [])}
    if filename in names_after_delete:
        raise RuntimeError(f"Deleted file {filename} still present in list")

    print("Smoke test passed")


if __name__ == "__main__":
    main()

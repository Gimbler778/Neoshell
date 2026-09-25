import hashlib
import os
import time

import requests


def main() -> None:
    base_url = os.getenv("SERVER_URL") or f"http://{os.getenv('SERVER_HOST', '127.0.0.1')}:{os.getenv('SERVER_PORT', '8080')}"
    token = os.getenv("AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = b"ci-smoke-test-payload\n"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = f"smoke-{int(time.time())}.txt"

    upload_headers = {
        **headers,
        "X-File-Name": filename,
        "X-SHA256": checksum,
        "Content-Length": str(len(payload)),
    }
    upload_response = requests.post(f"{base_url}/api/files", headers=upload_headers, data=payload, timeout=20)
    upload_response.raise_for_status()

    list_response = requests.get(f"{base_url}/api/files", headers=headers, timeout=20)
    list_response.raise_for_status()
    names = {item.get("name") for item in list_response.json().get("files", [])}
    if filename not in names:
        raise RuntimeError(f"Uploaded file {filename} not found in list")

    delete_response = requests.delete(f"{base_url}/api/files/{filename}", headers=headers, timeout=20)
    delete_response.raise_for_status()

    list_after_delete = requests.get(f"{base_url}/api/files", headers=headers, timeout=20)
    list_after_delete.raise_for_status()
    names_after_delete = {item.get("name") for item in list_after_delete.json().get("files", [])}
    if filename in names_after_delete:
        raise RuntimeError(f"Deleted file {filename} still present in list")

    print("Smoke test passed")


if __name__ == "__main__":
    main()

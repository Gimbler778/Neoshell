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

    # 1. Upload
    upload_headers = {
        **headers,
        "X-File-Name": filename,
        "X-SHA256": checksum,
        "Content-Length": str(len(payload)),
    }
    upload_response = requests.post(f"{base_url}/api/files", headers=upload_headers, data=payload, timeout=20)
    upload_response.raise_for_status()

    # 2. List
    list_response = requests.get(f"{base_url}/api/files", headers=headers, timeout=20)
    list_response.raise_for_status()
    names = {item.get("name") for item in list_response.json().get("files", [])}
    if filename not in names:
        raise RuntimeError(f"Uploaded file {filename} not found in list")

    # 3. Direct Download
    download_response = requests.get(f"{base_url}/api/files/{filename}", headers=headers, timeout=20)
    download_response.raise_for_status()
    if download_response.content != payload:
        raise RuntimeError("Downloaded content does not match uploaded payload")
    if download_response.headers.get("X-SHA256") != checksum:
        raise RuntimeError(f"Download X-SHA256 header mismatch: {download_response.headers.get('X-SHA256')}")

    # 4. Generate Share URL
    share_response = requests.post(
        f"{base_url}/api/files/{filename}/share",
        headers=headers,
        json={"expires_in": 3600},
        timeout=20,
    )
    share_response.raise_for_status()
    share_data = share_response.json()
    share_url = share_data.get("url")
    if not share_url or not share_data.get("expires_at"):
        raise RuntimeError(f"Invalid share response: {share_data}")

    # 5. Fetch via Presigned Share URL
    presigned_download = requests.get(share_url, timeout=20)
    presigned_download.raise_for_status()
    if presigned_download.content != payload:
        raise RuntimeError("Content downloaded via presigned URL does not match")

    # 6. Delete
    delete_response = requests.delete(f"{base_url}/api/files/{filename}", headers=headers, timeout=20)
    delete_response.raise_for_status()

    # 7. Verify deletion
    list_after_delete = requests.get(f"{base_url}/api/files", headers=headers, timeout=20)
    list_after_delete.raise_for_status()
    names_after_delete = {item.get("name") for item in list_after_delete.json().get("files", [])}
    if filename in names_after_delete:
        raise RuntimeError(f"Deleted file {filename} still present in list")

    print("Smoke test passed (upload, list, download, share, delete)")


if __name__ == "__main__":
    main()

from pathlib import Path

import pytest

from lanlink.app import create_app, safe_path


def test_safe_path_blocks_parent_escape(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    assert safe_path(share, "folder", must_exist=False) == share / "folder"
    with pytest.raises(ValueError):
        safe_path(share, "../private", must_exist=False)


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "settings.json", start_discovery=False)
    app.config.update(TESTING=True)
    return app.test_client(), app, tmp_path


def pair(client, app):
    settings = app.extensions["lan_settings"]
    token = settings.issue_token("peer-1", "Test PC")
    return {"X-Device-ID": "peer-1", "Authorization": f"Bearer {token}"}


def test_read_only_share_lists_and_downloads_but_rejects_write(client):
    http, app, tmp = client
    folder = tmp / "shared"
    folder.mkdir()
    (folder / "hello.txt").write_text("hello", encoding="utf-8")
    added = http.post("/api/shares", json={"path": str(folder), "name": "Docs", "mode": "read"})
    assert added.status_code == 201
    share_id = added.get_json()["id"]
    headers = pair(http, app)
    listing = http.get(f"/api/public/files/{share_id}", headers=headers)
    assert listing.status_code == 200
    assert listing.get_json()[0]["name"] == "hello.txt"
    denied = http.post(f"/api/public/operation/{share_id}", json={"operation": "delete", "path": "hello.txt"}, headers=headers)
    assert denied.status_code == 403
    assert (folder / "hello.txt").exists()


def test_full_access_operations_stay_inside_share(client):
    http, app, tmp = client
    folder = tmp / "shared"
    folder.mkdir()
    share_id = http.post("/api/shares", json={"path": str(folder), "mode": "full"}).get_json()["id"]
    headers = pair(http, app)
    created = http.post(f"/api/public/operation/{share_id}", json={"operation": "mkdir", "path": "New"}, headers=headers)
    assert created.status_code == 200
    escaped = http.post(f"/api/public/operation/{share_id}", json={"operation": "mkdir", "path": "../Outside"}, headers=headers)
    assert escaped.status_code == 400
    assert not (tmp / "Outside").exists()


def test_management_api_is_local_only(client):
    http, _, _ = client
    response = http.get("/api/state", environ_base={"REMOTE_ADDR": "192.168.1.10"})
    assert response.status_code == 403


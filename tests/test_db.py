from app import db


def test_creates_missing_data_folder(tmp_path):
    path = tmp_path / "data" / "dss.sqlite3"  # folder does not exist yet, as on a fresh clone
    assert db.list_sites(path) == []
    assert path.exists()

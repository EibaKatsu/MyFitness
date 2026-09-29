from pathlib import Path

from fastapi.testclient import TestClient

from myfitness.config import Settings
from myfitness.web import create_app


class EmptyRepository:
    def list_activities(self, limit=500): return []
    def list_rows(self, table): return []
    def list_syncs(self): return []


def test_health_and_local_dashboard():
    settings = Settings("https://example.supabase.co", "secret", Path("/tmp/tokens"))
    client = TestClient(create_app(settings, repository_factory=EmptyRepository))
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/dashboard").json() == {
        "activities": [], "weights": [], "meals": [], "syncs": []
    }


def test_untrusted_host_is_rejected():
    settings = Settings("https://example.supabase.co", "secret", Path("/tmp/tokens"))
    client = TestClient(create_app(settings, repository_factory=EmptyRepository))
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400

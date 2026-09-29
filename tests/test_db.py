from myfitness.db import SupabaseRepository


def test_new_secret_key_is_only_sent_as_api_key():
    repository = SupabaseRepository("https://example.supabase.co", "sb_secret_example")
    assert repository.headers["apikey"] == "sb_secret_example"
    assert "Authorization" not in repository.headers


def test_legacy_service_role_jwt_is_also_sent_as_bearer():
    repository = SupabaseRepository("https://example.supabase.co", "legacy.jwt.value")
    assert repository.headers["apikey"] == "legacy.jwt.value"
    assert repository.headers["Authorization"] == "Bearer legacy.jwt.value"

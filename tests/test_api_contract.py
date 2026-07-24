from __future__ import annotations

from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from fastapi_app import app


EXPECTED_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/health"),
    ("GET", "/api/classifier/diagnose"),
    ("POST", "/api/classify"),
    ("GET", "/api/news"),
    ("GET", "/api/news/important"),
    ("GET", "/api/news/popular"),
    ("GET", "/api/news/trending"),
    ("POST", "/api/news/{article_id:int}/view"),
    ("GET", "/api/news/{article_id:int}"),
    ("POST", "/api/sync"),
    ("POST", "/api/reclassify"),
    ("GET", "/api/admin/paraphrase-status"),
    ("POST", "/api/admin/paraphrase-news"),
    ("POST", "/api/admin/paraphrase-titles"),
    ("POST", "/api/admin/normalize-images"),
    ("GET", "/api/admin/news"),
    ("GET", "/api/admin/news/{article_id:int}"),
    ("PUT", "/api/admin/news/{article_id:int}"),
    ("POST", "/api/admin/news/{article_id:int}/approve"),
    ("POST", "/api/admin/news/{article_id:int}/reject"),
}


def test_existing_endpoint_contract_is_preserved() -> None:
    actual: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method not in {"HEAD", "OPTIONS"}:
                actual.add((method, route.path))
    assert EXPECTED_ROUTES <= actual


def test_sensitive_routes_require_authentication() -> None:
    protected_paths = {
        "/api/classifier/diagnose",
        "/api/sync",
        "/api/reclassify",
    }
    routes = {
        route.path: route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path in protected_paths
    }
    assert routes.keys() == protected_paths
    assert all(route.dependant.dependencies for route in routes.values())


def test_http_smoke_contract() -> None:
    client = TestClient(app)

    assert client.get("/").json() == {
        "ok": True,
        "service": "Tamil News API",
        "docs": "/docs",
        "health": "/health",
    }
    assert client.get("/health").json() == {"ok": True}
    api_health = client.get("/api/health").json()
    assert api_health["ok"] is True
    assert api_health["features"]["admin_image_upload"] is True
    assert client.post("/api/classify", json={"text": ""}).json() == {
        "category_ta": ""
    }
    assert client.post("/api/sync").status_code == 401
    assert client.get("/api/classifier/diagnose").status_code == 401

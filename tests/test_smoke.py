"""Smoke tests: does the app boot and answer requests without blowing up.

These deliberately check shape/status, not business-rule outcomes -
validar_combinacion is a stub pending real rules (see CLAUDE.md), so
asserting a specific "valido" value here would just re-lock today's
placeholder behavior instead of catching real breakage.
"""
import document_logic
import pytest


@pytest.fixture
def client():
    document_logic.app.config.update(TESTING=True)
    return document_logic.app.test_client()


def test_home_page_responds(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<html" in resp.data.lower()


def test_app_js_route_responds(client):
    # Custom route because app.js lives outside static_folder (see CLAUDE.md
    # "Path wiring") - if this ever 404s, that wiring broke.
    resp = client.get("/static/app.js")
    assert resp.status_code == 200


def test_orden_endpoint_responds(client):
    resp = client.get("/api/orden")
    assert resp.status_code == 200

    mapa = resp.get_json()
    assert isinstance(mapa, dict)
    for opciones in mapa.values():
        assert isinstance(opciones, list)


def test_procesar_endpoint_responds(client):
    resp = client.post("/api/procesar", json={"opciones": []})
    assert resp.status_code == 200

    data = resp.get_json()
    assert isinstance(data, dict)
    assert isinstance(data.get("valido"), bool)
    assert isinstance(data.get("mensaje"), str)
    assert isinstance(data.get("archivos"), list)

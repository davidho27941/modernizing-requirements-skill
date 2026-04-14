import pytest
from src.app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_create_product(client):
    resp = client.post("/products", json={
        "id": "p1", "name": "Widget", "price": 9.99
    })
    assert resp.status_code == 201

import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_create_item():
    response = client.post("/items", json={"name": "test", "price": 9.99})
    assert response.status_code == 200

def test_get_item():
    response = client.get("/items/test")
    assert response.status_code == 200

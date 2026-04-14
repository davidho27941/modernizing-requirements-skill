from flask import Flask, request, jsonify
from marshmallow import Schema, fields
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.orm import DeclarativeBase, Session
import requests
from PIL import Image
from dateutil.parser import parse as parse_date
import io
import os

app = Flask(__name__)

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./app.db"))

class Base(DeclarativeBase):
    pass

class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Float)

class ProductSchema(Schema):
    id = fields.String(required=True)
    name = fields.String(required=True)
    price = fields.Float()

product_schema = ProductSchema()

@app.route("/products", methods=["POST"])
def create_product():
    data = product_schema.load(request.json)
    with Session(engine) as session:
        product = Product(**data)
        session.add(product)
        session.commit()
    return jsonify(data), 201

@app.route("/products/<product_id>/thumbnail", methods=["POST"])
def upload_thumbnail(product_id):
    img_data = requests.get(request.json["image_url"]).content
    img = Image.open(io.BytesIO(img_data))
    img.thumbnail((128, 128))
    img.save(f"thumbnails/{product_id}.png")
    return jsonify({"status": "ok"})

@app.route("/products/since/<date_str>")
def products_since(date_str):
    dt = parse_date(date_str)
    return jsonify({"since": dt.isoformat()})

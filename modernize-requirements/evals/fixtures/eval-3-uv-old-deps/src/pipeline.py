import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import cv2
from PIL import Image
from dateutil.parser import parse as parse_date
import yaml
import requests
from tqdm import tqdm
import os


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def fetch_dataset(url: str, output_path: str) -> None:
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get("content-length", 0))
    with open(output_path, "wb") as f:
        for chunk in tqdm(resp.iter_content(1024), total=total // 1024):
            f.write(chunk)


def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.resize(img, (224, 224))
    return img.astype(np.float32) / 255.0


def train_model(csv_path: str) -> float:
    df = pd.read_csv(csv_path)
    df["date"] = df["date"].apply(lambda x: parse_date(x).timestamp())
    X = df.drop(columns=["target"])
    y = df["target"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    return accuracy_score(y_test, preds)

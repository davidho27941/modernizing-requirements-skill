import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


def plot_distribution(data: np.ndarray, output_path: str) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    ax.hist(data, bins=50, density=True, alpha=0.7)

    mu, sigma = stats.norm.fit(data)
    x = np.linspace(data.min(), data.max(), 100)
    ax.plot(x, stats.norm.pdf(x, mu, sigma), "r-", linewidth=2)

    ax.set_title(f"Distribution (mu={mu:.2f}, sigma={sigma:.2f})")
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_timeseries(df: pd.DataFrame, col: str, output_path: str) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df.index, df[col])
    ax.set_ylabel(col)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

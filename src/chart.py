import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


def generate_price_chart(prices: list[dict]) -> io.BytesIO | None:
    if len(prices) < 2:
        return None

    times = []
    values = []
    for p in reversed(prices):
        raw = p["checked_at"]
        if isinstance(raw, datetime):
            t = raw
        else:
            try:
                t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except Exception:
                try:
                    t = datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
        times.append(t)
        values.append(p["price"])

    if len(values) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 4), dpi=100)
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    color = "#00d4aa" if values[-1] <= values[0] else "#ff6b6b"
    ax.plot(times, values, color=color, linewidth=2, marker="o", markersize=4)
    ax.fill_between(times, values, alpha=0.15, color=color)

    ax.set_title("История цены", color="white", fontsize=14, pad=15)
    ax.set_ylabel("Цена", color="white", fontsize=11)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.tick_params(colors="white", labelsize=9)
    ax.spines["bottom"].set_color("#333")
    ax.spines["left"].set_color("#333")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.15, color="white")

    min_p = min(values)
    max_p = max(values)
    ax.annotate(
        f"Мин: {min_p:.0f}",
        xy=(times[values.index(min_p)], min_p),
        xytext=(10, 15), textcoords="offset points",
        color="#00d4aa", fontsize=9,
        arrowprops=dict(arrowstyle="->", color="#00d4aa", lw=1.5),
    )
    ax.annotate(
        f"Макс: {max_p:.0f}",
        xy=(times[values.index(max_p)], max_p),
        xytext=(10, -20), textcoords="offset points",
        color="#ff6b6b", fontsize=9,
        arrowprops=dict(arrowstyle="->", color="#ff6b6b", lw=1.5),
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf

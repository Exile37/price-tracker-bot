import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from src.database.db import get_user_products, get_price_history

logger = logging.getLogger(__name__)

app = FastAPI(title="Price Tracker Mini App")


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


@app.get("/api/products/{user_id}")
async def api_products(user_id: int):
    products = await get_user_products(user_id)
    result = []
    for p in products:
        result.append({
            "id": p["id"],
            "title": p["title"],
            "url": p["url"],
            "price": p["current_price"],
            "target_price": p["target_price"],
            "currency": p["currency"],
            "image_url": p["image_url"],
        })
    return {"products": result}


@app.get("/api/history/{product_id}")
async def api_history(product_id: int):
    history = await get_price_history(product_id, limit=60)
    result = [{"price": h["price"], "date": str(h["checked_at"])} for h in history]
    return {"history": result}


HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Price Tracker</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            min-height: 100vh;
            padding: 16px;
        }
        .header {
            text-align: center;
            padding: 20px 0;
        }
        .header h1 {
            font-size: 24px;
            background: linear-gradient(135deg, #00d4aa, #00b4d8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stats {
            display: flex;
            gap: 12px;
            margin: 16px 0;
        }
        .stat-card {
            flex: 1;
            background: #1a1a3e;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #00d4aa;
        }
        .stat-label {
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }
        .product-list { margin-top: 16px; }
        .product-card {
            background: #1a1a3e;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            display: flex;
            gap: 12px;
            align-items: center;
        }
        .product-img {
            width: 60px;
            height: 60px;
            border-radius: 8px;
            object-fit: cover;
            background: #2a2a4e;
        }
        .product-info { flex: 1; }
        .product-title {
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 4px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .product-price {
            font-size: 18px;
            font-weight: bold;
            color: #00d4aa;
        }
        .product-target {
            font-size: 12px;
            color: #ff6b6b;
            margin-top: 2px;
        }
        .btn-chart {
            background: #2a2a5e;
            border: none;
            color: #00d4aa;
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
        }
        .chart-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            z-index: 100;
            padding: 20px;
        }
        .chart-modal.active { display: flex; flex-direction: column; align-items: center; }
        .chart-close {
            position: absolute;
            top: 20px;
            right: 20px;
            background: none;
            border: none;
            color: white;
            font-size: 24px;
            cursor: pointer;
        }
        .chart-canvas {
            width: 100%;
            max-width: 400px;
            margin-top: 60px;
        }
        .empty {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-icon { font-size: 48px; margin-bottom: 16px; }
        .loading { text-align: center; padding: 40px; color: #888; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛒 Price Tracker</h1>
    </div>

    <div class="stats" id="stats">
        <div class="stat-card">
            <div class="stat-value" id="total">-</div>
            <div class="stat-label">Товаров</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="dropped">-</div>
            <div class="stat-label">Снижений</div>
        </div>
    </div>

    <div class="product-list" id="products">
        <div class="loading">Загрузка...</div>
    </div>

    <div class="chart-modal" id="chartModal">
        <button class="chart-close" onclick="closeChart()">✕</button>
        <canvas class="chart-canvas" id="chartCanvas" width="400" height="250"></canvas>
    </div>

    <script>
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
            tg.setHeaderColor('#0f0f23');
            tg.setBackgroundColor('#0f0f23');
        }

        const urlParams = new URLSearchParams(window.location.search);
        const userId = parseInt(urlParams.get('user_id')) || tg?.initDataUnsafe?.user?.id || 0;

        async function loadProducts() {
            try {
                const resp = await fetch(`/api/products/${userId}`);
                const data = await resp.json();
                renderProducts(data.products);
            } catch (e) {
                document.getElementById('products').innerHTML = '<div class="empty"><div class="empty-icon">📦</div>Нет товаров</div>';
            }
        }

        function renderProducts(products) {
            const container = document.getElementById('products');
            document.getElementById('total').textContent = products.length;

            if (products.length === 0) {
                container.innerHTML = '<div class="empty"><div class="empty-icon">📦</div>Отправь ссылку в бота<br>чтобы начать</div>';
                return;
            }

            container.innerHTML = products.map(p => `
                <div class="product-card">
                    ${p.image_url ? `<img class="product-img" src="${p.image_url}" onerror="this.style.display='none'">` : '<div class="product-img"></div>'}
                    <div class="product-info">
                        <div class="product-title">${escapeHtml(p.title)}</div>
                        <div class="product-price">${p.price}${p.currency}</div>
                        ${p.target_price ? `<div class="product-target">🎯 Цель: ${p.target_price}${p.currency}</div>` : ''}
                    </div>
                    <button class="btn-chart" onclick="showChart(${p.id})">📊</button>
                </div>
            `).join('');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function showChart(productId) {
            try {
                const resp = await fetch(`/api/history/${productId}`);
                const data = await resp.json();
                drawChart(data.history);
                document.getElementById('chartModal').classList.add('active');
            } catch (e) {}
        }

        function closeChart() {
            document.getElementById('chartModal').classList.remove('active');
        }

        function drawChart(history) {
            const canvas = document.getElementById('chartCanvas');
            const ctx = canvas.getContext('2d');
            const W = canvas.width;
            const H = canvas.height;

            ctx.fillStyle = '#1a1a3e';
            ctx.fillRect(0, 0, W, H);

            if (history.length < 2) {
                ctx.fillStyle = '#888';
                ctx.font = '14px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText('Недостаточно данных', W/2, H/2);
                return;
            }

            const prices = history.map(h => h.price).reverse();
            const min = Math.min(...prices);
            const max = Math.max(...prices);
            const range = max - min || 1;
            const pad = 40;

            ctx.strokeStyle = '#00d4aa';
            ctx.lineWidth = 2;
            ctx.beginPath();

            prices.forEach((p, i) => {
                const x = pad + (i / (prices.length - 1)) * (W - pad * 2);
                const y = pad + (1 - (p - min) / range) * (H - pad * 2);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();

            ctx.fillStyle = 'rgba(0, 212, 170, 0.1)';
            ctx.lineTo(W - pad, H - pad);
            ctx.lineTo(pad, H - pad);
            ctx.fill();

            ctx.fillStyle = '#888';
            ctx.font = '11px sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(`${max.toFixed(0)}₽`, 4, pad + 4);
            ctx.fillText(`${min.toFixed(0)}₽`, 4, H - pad + 4);

            const last = prices[prices.length - 1];
            ctx.fillStyle = '#00d4aa';
            ctx.font = 'bold 14px sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(`${last.toFixed(0)}₽`, W - 4, pad + 4);
        }

        loadProducts();
    </script>
</body>
</html>"""

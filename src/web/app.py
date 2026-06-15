import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from src.database.db import get_user_products, get_price_history, deactivate_product, get_analytics, get_user_settings, get_all_users, get_user_count, get_premium_user_count, get_total_products, set_custom_limit, create_promocode

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


@app.delete("/api/products/{product_id}")
async def api_delete_product(product_id: int):
    await deactivate_product(product_id)
    return {"ok": True}


@app.get("/api/analytics/{user_id}")
async def api_analytics(user_id: int):
    a = await get_analytics(user_id)
    settings = await get_user_settings(user_id)
    return {
        "analytics": a,
        "min_drop_pct": settings[0] if settings else 5,
        "check_interval": settings[1] if settings else 30,
        "total_saved": settings[2] if settings else 0,
    }


@app.get("/api/admin/stats")
async def api_admin_stats():
    return {
        "total_users": await get_user_count(),
        "premium_users": await get_premium_user_count(),
        "total_products": await get_total_products(),
    }


@app.get("/api/admin/users")
async def api_admin_users():
    users = await get_all_users()
    result = []
    for u in users:
        result.append({
            "user_id": u["user_id"],
            "username": u["username"],
            "is_premium": u["is_premium"],
            "custom_limit": u["custom_limit"],
            "created_at": str(u["created_at"]),
        })
    return {"users": result}


@app.post("/api/admin/setlimit")
async def api_admin_setlimit(data: dict):
    user_id = data.get("user_id")
    limit = data.get("limit")
    if user_id and limit is not None:
        await set_custom_limit(int(user_id), int(limit))
        return {"ok": True}
    return {"ok": False}


@app.post("/api/admin/promo")
async def api_admin_promo(data: dict):
    code = data.get("code", "").upper()
    bonus = data.get("bonus", 0)
    if code and bonus:
        success = await create_promocode(code, bonus_products=int(bonus))
        return {"ok": success}
    return {"ok": False}


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
        .btn-delete {
            background: #3a1a1a;
            border: none;
            color: #ff6b6b;
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
        }
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }
        .tab {
            flex: 1;
            padding: 10px;
            background: #1a1a3e;
            border: none;
            border-radius: 8px;
            color: #888;
            cursor: pointer;
            font-size: 13px;
        }
        .tab.active {
            background: #2a2a5e;
            color: #00d4aa;
        }
        .admin-section { display: none; }
        .admin-section.active { display: block; }
        .admin-card {
            background: #1a1a3e;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .admin-stat {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #2a2a4e;
        }
        .admin-input {
            width: 100%;
            padding: 10px;
            background: #0f0f23;
            border: 1px solid #2a2a4e;
            border-radius: 8px;
            color: #e0e0e0;
            margin: 4px 0;
        }
        .admin-btn {
            width: 100%;
            padding: 12px;
            background: #00d4aa;
            border: none;
            border-radius: 8px;
            color: #0f0f23;
            font-weight: bold;
            cursor: pointer;
            margin-top: 8px;
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

    <div class="tabs">
        <button class="tab active" onclick="switchTab('products')">📦 Товары</button>
        <button class="tab" id="adminTab" onclick="switchTab('admin')" style="display:none">🔧 Админ</button>
    </div>

    <div id="productsSection" class="admin-section active">

    <div class="stats" id="stats">
        <div class="stat-card">
            <div class="stat-value" id="total">-</div>
            <div class="stat-label">Товаров</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="dropped">-</div>
            <div class="stat-label">Снижений</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="saved">-</div>
            <div class="stat-label">Сэкономлено</div>
        </div>
    </div>

    <div class="product-list" id="products">
        <div class="loading">Загрузка...</div>
    </div>
    </div>

    <div id="adminSection" class="admin-section">
        <div class="admin-card">
            <h3 style="color:#00d4aa;margin-bottom:12px">📊 Статистика</h3>
            <div class="admin-stat"><span>Пользователей</span><span id="aUsers">-</span></div>
            <div class="admin-stat"><span>Премиум</span><span id="aPremium">-</span></div>
            <div class="admin-stat"><span>Товаров</span><span id="aProducts">-</span></div>
        </div>
        <div class="admin-card">
            <h3 style="color:#00d4aa;margin-bottom:12px">🎁 Создать промокод</h3>
            <input class="admin-input" id="promoCode" placeholder="Код (PROMO-XXXX)">
            <input class="admin-input" id="promoBonus" type="number" placeholder="Бонус (кол-во товаров)">
            <button class="admin-btn" onclick="createPromo()">Создать</button>
        </div>
        <div class="admin-card">
            <h3 style="color:#00d4aa;margin-bottom:12px">👥 Пользователи</h3>
            <div id="userList">Загрузка...</div>
        </div>
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
                loadAnalytics();
            } catch (e) {
                document.getElementById('products').innerHTML = '<div class="empty"><div class="empty-icon">📦</div>Нет товаров</div>';
            }
        }

        async function loadAnalytics() {
            try {
                const resp = await fetch(`/api/analytics/${userId}`);
                const data = await resp.json();
                const a = data.analytics;
                document.getElementById('dropped').textContent = a.drops;
                document.getElementById('saved').textContent = data.total_saved + '₽';
            } catch (e) {}
        }

        async function deleteProduct(productId) {
            if (!confirm('Удалить товар?')) return;
            await fetch(`/api/products/${productId}`, { method: 'DELETE' });
        const ADMIN_ID = 951494385;

        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
            if (tab === 'products') {
                document.querySelector('.tab:first-child').classList.add('active');
                document.getElementById('productsSection').classList.add('active');
            } else {
                document.getElementById('adminTab').classList.add('active');
                document.getElementById('adminSection').classList.add('active');
                loadAdmin();
            }
        }

        async function loadAdmin() {
            try {
                const [statsResp, usersResp] = await Promise.all([
                    fetch('/api/admin/stats'),
                    fetch('/api/admin/users')
                ]);
                const stats = await statsResp.json();
                const users = await usersResp.json();

                document.getElementById('aUsers').textContent = stats.total_users;
                document.getElementById('aPremium').textContent = stats.premium_users;
                document.getElementById('aProducts').textContent = stats.total_products;

                const list = document.getElementById('userList');
                list.innerHTML = users.users.slice(0, 20).map(u => `
                    <div class="admin-stat">
                        <span>${u.username ? '@' + u.username : u.user_id}</span>
                        <span>${u.is_premium ? '⭐' : '👤'} ${u.custom_limit > 0 ? 'лимит:' + u.custom_limit : ''}</span>
                    </div>
                `).join('');
            } catch (e) {}
        }

        async function createPromo() {
            const code = document.getElementById('promoCode').value.trim();
            const bonus = parseInt(document.getElementById('promoBonus').value);
            if (!code || !bonus) return alert('Заполни все поля');
            const resp = await fetch('/api/admin/promo', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({code, bonus})
            });
            const data = await resp.json();
            if (data.ok) alert('Промокод создан: ' + code);
            else alert('Ошибка');
        }

        if (userId === ADMIN_ID) {
            document.getElementById('adminTab').style.display = 'block';
        }

        loadProducts();
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
                    <button class="btn-delete" onclick="deleteProduct(${p.id})">🗑</button>
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

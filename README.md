# 📈 美股監控 Web UI

瀏覽器版的美股監控介面，提供即時報價、互動走勢圖與價格警報功能。

## 🚀 快速啟動

### 1. 建立虛擬環境

```bash
python -m venv venv

# Windows CMD
venv\Scripts\activate

# Windows PowerShell
venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

### 2. 安裝套件

```bash
pip install -r requirements.txt
```

### 3. 啟動伺服器

```bash
python app.py
```

### 4. 開啟瀏覽器

前往 **http://localhost:5000**

---

## 🖥️ 功能說明

| 功能 | 說明 |
|------|------|
| 即時報價表 | 顯示現價、漲跌幅、成交量、市值，顏色標示漲跌 |
| 自訂股票 | 輸入框填入股票代碼，以逗號分隔 |
| 自動更新 | 支援 30s / 1m / 5m 定時刷新，或關閉 |
| 走勢圖 | 點選股票查看 K 線走勢，支援 5D / 1M / 3M / 6M / 1Y |
| 價格警報 | 設定目標價與停損價，達標時前端彈出通知 |

---

## 📁 檔案結構

```
stock_ui/
├── app.py               # Flask 後端 (API 路由)
├── requirements.txt     # 套件依賴
├── alerts.json          # 警報資料 (自動產生)
└── templates/
    └── index.html       # 前端頁面
```

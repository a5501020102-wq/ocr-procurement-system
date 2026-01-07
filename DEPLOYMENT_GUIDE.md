# 🚀 AI 採購稽核戰情室 - 部署指南

## 📋 部署方式比較

| 方式 | 難度 | 費用 | 時間 | 適合場景 |
|------|------|------|------|----------|
| Streamlit Cloud | ⭐ | 免費 | 20分鐘 | 快速部署、團隊分享 |
| Hugging Face | ⭐⭐ | 免費 | 30分鐘 | AI 應用、公開展示 |
| Docker + Cloud | ⭐⭐⭐⭐ | 付費 | 2小時 | 企業級部署 |
| 桌面應用 | ⭐⭐⭐ | 免費 | 2小時 | 本地使用 |

---

## 🥇 方案 A：Streamlit Cloud 部署（推薦）

### Step 1: 準備 GitHub Repository

#### 1.1 創建 GitHub 帳號
如果還沒有：https://github.com/signup

#### 1.2 創建新 Repository
```
名稱: ocr-procurement-system
描述: AI 採購稽核戰情室 - 智能採購單據分析系統
可見性: Public（免費）或 Private（需 Streamlit 付費版）
```

#### 1.3 上傳檔案

**必要檔案**：
```
您的專案/
├── web_app.py              ✅ 主程式
├── config.py               ✅ 設定檔
├── utils.py                ✅ 工具函式
├── agent_tools.py          ✅ AI 工具
├── ocr_engine.py           ✅ OCR 引擎
├── requirements.txt        ✅ 套件清單
├── .gitignore              ✅ Git 忽略清單
├── .streamlit/
│   ├── config.toml         ✅ Streamlit 設定
│   └── secrets.toml.example ✅ Secrets 範例
└── README.md               ✅ 說明文件
```

**❌ 不要上傳**：
- `.env` 檔案
- `temp_uploads/` 目錄
- `debug_logs/` 目錄
- 任何包含 API Key 的檔案

---

### Step 2: 上傳到 GitHub

#### 方式 A：使用 Git（推薦）

```bash
# 1. 在專案目錄初始化 Git
cd C:\Users\pengchi.tseng\ocr_agent_skill
git init

# 2. 添加遠端 Repository
git remote add origin https://github.com/您的用戶名/ocr-procurement-system.git

# 3. 添加檔案
git add web_app.py config.py utils.py agent_tools.py ocr_engine.py
git add requirements.txt .gitignore .streamlit/

# 4. 提交
git commit -m "Initial commit: AI 採購稽核戰情室 V25.6"

# 5. 推送到 GitHub
git push -u origin main
```

#### 方式 B：使用 GitHub Desktop（簡單）

1. 下載 GitHub Desktop: https://desktop.github.com/
2. File → New Repository
3. 將檔案拖入
4. Commit → Publish

#### 方式 C：網頁上傳（最簡單）

1. 在 GitHub 創建 Repository
2. 點擊 "uploading an existing file"
3. 拖入所有檔案
4. Commit changes

---

### Step 3: 部署到 Streamlit Cloud

#### 3.1 註冊 Streamlit Cloud
1. 前往: https://streamlit.io/cloud
2. 點擊 "Sign up"
3. 使用 GitHub 帳號登入

#### 3.2 創建新應用
```
1. 點擊 "New app"
2. Repository: 選擇您的 ocr-procurement-system
3. Branch: main
4. Main file path: web_app.py
5. App URL (optional): 自訂網址
```

#### 3.3 設定 Secrets（重要！）
```
1. 在部署界面，點擊 "Advanced settings"
2. 或部署後在 Settings → Secrets
3. 貼上以下內容：

GOOGLE_API_KEY = "您的真實 API Key"
GEMINI_MODEL = "gemini-3-flash-preview"
```

#### 3.4 部署
點擊 "Deploy!" 按鈕

等待 5-10 分鐘，完成！

---

### Step 4: 驗證部署

部署成功後，您會看到：
```
✅ 應用 URL: https://您的應用名稱.streamlit.app
✅ 狀態: Running
✅ 日誌: 顯示啟動訊息
```

測試功能：
- ✅ 上傳測試檔案
- ✅ 執行批次處理
- ✅ 使用 AI 對話功能

---

## 🥈 方案 B：Hugging Face Spaces

### 優點
- ✅ 免費且資源更多
- ✅ 可設為私有
- ✅ AI 社群友善

### 步驟

1. **註冊 Hugging Face**: https://huggingface.co/join
2. **創建 Space**:
   ```
   Space name: ocr-procurement-system
   SDK: Streamlit
   Hardware: CPU basic (免費)
   ```
3. **上傳檔案**:
   - 所有 Python 檔案
   - requirements.txt
   - README.md
4. **設定 Secrets**:
   ```
   Settings → Repository secrets
   GOOGLE_API_KEY = "您的 API Key"
   ```

---

## 🥉 方案 C：桌面應用程式

### 使用 PyInstaller

```bash
# 1. 安裝 PyInstaller
pip install pyinstaller

# 2. 打包應用
pyinstaller --onefile --windowed --add-data "config.py;." web_app.py

# 3. 產出位置
dist/web_app.exe
```

### 注意事項
- ⚠️ Streamlit 不太適合打包成 exe
- ⚠️ 檔案會很大（>200MB）
- ⚠️ 建議使用 Docker 容器化

---

## 📋 常見問題

### Q1: 部署後顯示 "Module not found"
**A**: 檢查 requirements.txt 是否包含所有套件

### Q2: API Key 錯誤
**A**: 確認 Secrets 設定正確，無多餘空格

### Q3: 上傳檔案後無反應
**A**: 檢查日誌，可能是記憶體不足

### Q4: 如何更新部署?
**A**: 推送新的 commit 到 GitHub，Streamlit Cloud 會自動重新部署

### Q5: 可以設為私有嗎?
**A**: Streamlit Cloud 免費版不支援，需要付費版（$20/月）

---

## 🔒 安全性建議

### 1. API Key 管理
- ❌ 不要寫在程式碼中
- ❌ 不要上傳 .env 到 GitHub
- ✅ 使用 Streamlit Secrets
- ✅ 定期更換 API Key

### 2. 存取控制
如果處理敏感資料：
- 使用 Streamlit 付費版設為私有
- 或使用登入機制
- 或部署到內部伺服器

### 3. 資料安全
- 上傳的檔案是臨時的
- 關閉瀏覽器後會清除
- 不會永久儲存在雲端

---

## 💰 費用比較

| 方案 | 免費版 | 付費版 |
|------|--------|--------|
| Streamlit Cloud | ✅ 公開應用 | $20/月（私有） |
| Hugging Face | ✅ 私有應用 | $9/月（更多資源） |
| Google Cloud Run | 免費額度 | 按使用量 |
| AWS | 免費額度 | 按使用量 |

---

## 🎯 我的推薦

### 適合使用 Streamlit Cloud 如果：
- ✅ 快速部署需求
- ✅ 團隊內部分享（公開無妨）
- ✅ 不需要高可用性
- ✅ 檔案不敏感

### 考慮其他方案如果：
- ⚠️ 處理敏感資料（需要私有）
- ⚠️ 需要24/7運作
- ⚠️ 大量使用者同時存取
- ⚠️ 需要自訂網域

---

## 📞 需要協助？

如果在部署過程中遇到問題：
1. 檢查此文件的常見問題
2. 查看 Streamlit Cloud 日誌
3. 提供錯誤訊息尋求協助

---

**祝部署順利！** 🚀
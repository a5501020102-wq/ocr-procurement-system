"""
AI 採購稽核戰情室 - 配置文件
Version: V25 (完整修復版)
"""


class Config:
    """系統配置參數集中管理"""

    # === API 設定 ===
    API_RETRY_TIMES = 3
    API_RETRY_DELAY = 2  # 秒
    DEFAULT_MODEL = "gemini-3-flash-preview"

    # === 執行緒設定 ===
    MAX_WORKERS = 4
    API_RATE_LIMIT_MIN = 0.5  # 秒
    API_RATE_LIMIT_MAX = 1.5  # 秒

    # === 檔案管理 ===
    TEMP_DIR = "temp_web_upload"
    MAX_TEMP_AGE_HOURS = 24  # 超過此時間的檔案將被清理
    ALLOWED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg']
    MAX_FILE_SIZE_MB = 10  # 單檔上限

    # === Excel 設定 ===
    MIN_COLUMN_WIDTH = 8
    MAX_COLUMN_WIDTH = 50
    EXCEL_OUTPUT_NAME = "verified_po_v25.xlsx"
    EXCEL_SHEET_NAME = "採購資料"

    # === 快取設定 ===
    CACHE_TTL = 3600  # 秒
    ENABLE_FILE_HASH_CACHE = True


class ColumnSchema:
    """欄位定義集中管理"""

    # === 核心欄位 ===
    CORE = ["項次", "品名", "規格", "採購數", "單價", "金額"]

    # === 訂單資訊欄位 ===
    ORDER_INFO = [
        "訂單號碼", "採購單號", "供應商", "採購日期",
        "廠牌", "單位", "聯絡電話"
    ]

    # === 稽核欄位 ===
    AUDIT = [
        "_稽核狀態", "_稽核訊息",
        "_confidence", "_來源檔案"
    ]

    # === 顯示順序（前台展示）===
    @classmethod
    def get_display_order(cls):
        """取得前台顯示欄位順序"""
        return (
                cls.AUDIT[:2] + ["_來源檔案"] +
                cls.CORE +
                [c for c in cls.ORDER_INFO if c not in ["廠牌", "單位", "聯絡電話"]] +
                ["備註"] +
                cls.AUDIT[2:]
        )

    # === 下載順序（Excel 輸出）===
    @classmethod
    def get_download_order(cls):
        """取得 Excel 下載欄位順序"""
        return (
                ["項次", "訂單號碼", "採購單號", "供應商", "採購日期"] +
                ["品名", "規格", "廠牌", "單位", "採購數"] +
                ["單價", "金額"] +
                ["備註", "聯絡電話"] +
                cls.AUDIT
        )

    # === 資料型態定義 ===
    STRING_COLS = ["訂單號碼", "採購單號", "供應商", "聯絡電話"]
    NUMERIC_COLS = ["採購數", "單價", "金額"]
    REQUIRED_FIELDS = ["品名", "採購數", "單價", "金額"]


class UIConfig:
    """使用者介面設定"""

    PAGE_TITLE = "AI 採購稽核戰情室 V25"
    PAGE_ICON = "⚡"
    LAYOUT = "wide"

    # 快捷指令
    QUICK_PROMPTS = {
        "💰 計算總金額": "幫我計算這張單子的總金額，並檢查數學是否有誤？",
        "🔍 找最貴項目": "列出單價最高的前 3 個項目，並畫出長條圖。",
        "📊 供應商分析": "這張單子的供應商是誰？有沒有異常項目？",
        "📈 趨勢分析": "分析最近的採購趨勢，有什麼值得注意的地方？"
    }


# 建立配置實例
CONFIG = Config()
SCHEMA = ColumnSchema()
UI = UIConfig()
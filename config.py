"""
AI 採購稽核戰情室 - 配置文件
Version: V25.7 (環境變數修復 + 優化版)

主要改進：
- ✅ 支援從環境變數讀取 GEMINI_MODEL
- ✅ 增加類型提示
- ✅ 改進預設值邏輯
- ✅ 優化程式碼結構
- ✅ 增加配置驗證
"""

import os
from typing import List, Dict, ClassVar


class Config:
    """
    系統配置參數集中管理
    
    所有配置項目都可透過環境變數覆寫，優先順序：
    1. 環境變數（.env 或 Streamlit Secrets）
    2. 類別預設值
    """
    
    # === API 設定 ===
    API_RETRY_TIMES: int = 3
    API_RETRY_DELAY: int = 2  # 秒
    
    # 🟢 [修復] 優先讀取環境變數，支援 Streamlit Cloud Secrets
    DEFAULT_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # === 執行緒設定 ===
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
    API_RATE_LIMIT_MIN: float = 0.5  # 秒（最小延遲）
    API_RATE_LIMIT_MAX: float = 1.5  # 秒（最大延遲）
    
    # === 檔案管理 ===
    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp_web_upload")
    MAX_TEMP_AGE_HOURS: int = 24  # 超過此時間的檔案將被清理
    ALLOWED_EXTENSIONS: List[str] = ['pdf', 'png', 'jpg', 'jpeg']
    MAX_FILE_SIZE_MB: int = 10  # 單檔上限
    
    # === Excel 設定 ===
    MIN_COLUMN_WIDTH: int = 8
    MAX_COLUMN_WIDTH: int = 50
    EXCEL_OUTPUT_NAME: str = "verified_po_v25.xlsx"
    EXCEL_SHEET_NAME: str = "採購資料"
    
    # === 快取設定 ===
    CACHE_TTL: int = 3600  # 秒
    ENABLE_FILE_HASH_CACHE: bool = True
    
    # === 日誌設定 ===
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENABLE_DEBUG: bool = os.getenv("ENABLE_DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> bool:
        """
        驗證配置的有效性
        
        Returns:
            bool: 配置是否有效
        """
        try:
            # 檢查必要參數
            assert cls.MAX_WORKERS > 0, "MAX_WORKERS 必須大於 0"
            assert cls.MAX_FILE_SIZE_MB > 0, "MAX_FILE_SIZE_MB 必須大於 0"
            assert cls.API_RETRY_TIMES > 0, "API_RETRY_TIMES 必須大於 0"
            
            # 檢查模型名稱格式
            valid_models = [
                "gemini-2.5-flash", "gemini-2.5-pro",
                "gemini-3-flash-preview", "gemini-3-pro-preview",
                "gemini-2.0-flash-exp"
            ]
            if cls.DEFAULT_MODEL not in valid_models:
                print(f"⚠️ 警告：使用的模型 '{cls.DEFAULT_MODEL}' 不在推薦列表中")
            
            return True
            
        except AssertionError as e:
            print(f"❌ 配置驗證失敗：{e}")
            return False
    
    @classmethod
    def get_info(cls) -> Dict[str, any]:
        """
        取得當前配置資訊（用於 debug）
        
        Returns:
            Dict: 配置字典
        """
        return {
            "model": cls.DEFAULT_MODEL,
            "max_workers": cls.MAX_WORKERS,
            "temp_dir": cls.TEMP_DIR,
            "max_file_size_mb": cls.MAX_FILE_SIZE_MB,
            "allowed_extensions": cls.ALLOWED_EXTENSIONS,
            "enable_debug": cls.ENABLE_DEBUG
        }


class ColumnSchema:
    """
    欄位定義集中管理
    
    定義資料表欄位結構、顯示順序、資料型態等
    """
    
    # === 核心欄位 ===
    CORE: ClassVar[List[str]] = [
        "項次", "品名", "規格", "採購數", "單價", "金額"
    ]
    
    # === 訂單資訊欄位 ===
    ORDER_INFO: ClassVar[List[str]] = [
        "訂單號碼", "採購單號", "供應商", "採購日期",
        "廠牌", "單位", "聯絡電話"
    ]
    
    # === 稽核欄位 ===
    AUDIT: ClassVar[List[str]] = [
        "_稽核狀態", "_稽核訊息",
        "_confidence", "_來源檔案"
    ]
    
    # === 資料型態定義 ===
    STRING_COLS: ClassVar[List[str]] = [
        "訂單號碼", "採購單號", "供應商", "聯絡電話", "品名", "規格", "備註"
    ]
    
    NUMERIC_COLS: ClassVar[List[str]] = [
        "採購數", "單價", "金額"
    ]
    
    DATE_COLS: ClassVar[List[str]] = [
        "採購日期"
    ]
    
    REQUIRED_FIELDS: ClassVar[List[str]] = [
        "品名", "採購數", "單價", "金額"
    ]
    
    @classmethod
    def get_display_order(cls) -> List[str]:
        """
        取得前台顯示欄位順序
        
        順序：稽核資訊 → 核心資料 → 訂單資訊 → 備註 → 元資料
        
        Returns:
            List[str]: 欄位名稱列表
        """
        return (
            # 優先顯示稽核狀態
            cls.AUDIT[:2] + ["_來源檔案"] +
            # 核心業務資料
            cls.CORE +
            # 重要訂單資訊（排除次要欄位）
            [c for c in cls.ORDER_INFO if c not in ["廠牌", "單位", "聯絡電話"]] +
            # 備註與元資料
            ["備註"] + cls.AUDIT[2:]
        )
    
    @classmethod
    def get_download_order(cls) -> List[str]:
        """
        取得 Excel 下載欄位順序
        
        順序：識別資訊 → 產品資訊 → 數量金額 → 備註 → 稽核資訊
        
        Returns:
            List[str]: 欄位名稱列表
        """
        return (
            # 訂單識別資訊
            ["項次", "訂單號碼", "採購單號", "供應商", "採購日期"] +
            # 產品資訊
            ["品名", "規格", "廠牌", "單位", "採購數"] +
            # 金額資訊
            ["單價", "金額"] +
            # 其他資訊
            ["備註", "聯絡電話"] +
            # 稽核元資料
            cls.AUDIT
        )
    
    @classmethod
    def get_column_type(cls, column_name: str) -> str:
        """
        取得欄位的資料型態
        
        Args:
            column_name: 欄位名稱
            
        Returns:
            str: 資料型態 ('string', 'numeric', 'date', 'unknown')
        """
        if column_name in cls.STRING_COLS:
            return "string"
        elif column_name in cls.NUMERIC_COLS:
            return "numeric"
        elif column_name in cls.DATE_COLS:
            return "date"
        else:
            return "unknown"
    
    @classmethod
    def validate_required_fields(cls, data: Dict[str, any]) -> tuple:
        """
        驗證必要欄位是否存在
        
        Args:
            data: 資料字典
            
        Returns:
            tuple: (是否有效, 缺少的欄位列表)
        """
        missing_fields = [field for field in cls.REQUIRED_FIELDS if field not in data]
        is_valid = len(missing_fields) == 0
        return is_valid, missing_fields


class UIConfig:
    """
    使用者介面設定
    
    定義前端顯示相關的配置
    """
    
    PAGE_TITLE: ClassVar[str] = "AI 採購稽核戰情室 V25"
    PAGE_ICON: ClassVar[str] = "⚡"
    LAYOUT: ClassVar[str] = "wide"
    
    # === 快捷指令 ===
    QUICK_PROMPTS: ClassVar[Dict[str, str]] = {
        "💰 計算總金額": "幫我計算這張單子的總金額，並檢查數學是否有誤？",
        "🔍 找最貴項目": "列出單價最高的前 3 個項目。",
        "📊 供應商分析": "這張單子的供應商是誰？有沒有異常項目？",
        "📈 趨勢分析": "分析採購數據，有什麼值得注意的地方？",
    }
    
    # === 主題配色（可選）===
    THEME_PRIMARY_COLOR: ClassVar[str] = "#FF4B4B"
    THEME_BACKGROUND_COLOR: ClassVar[str] = "#FFFFFF"
    
    # === 訊息文字 ===
    MSG_SUCCESS_UPLOAD: ClassVar[str] = "✅ 檔案上傳成功"
    MSG_ERROR_UPLOAD: ClassVar[str] = "❌ 檔案上傳失敗"
    MSG_PROCESSING: ClassVar[str] = "🔄 處理中，請稍候..."
    MSG_COMPLETE: ClassVar[str] = "🎉 處理完成！"


# ============================================================================
# 建立配置實例（全域可用）
# ============================================================================

CONFIG = Config()
SCHEMA = ColumnSchema()
UI = UIConfig()


# ============================================================================
# 配置驗證（啟動時執行）
# ============================================================================

def validate_config_on_startup() -> None:
    """
    應用啟動時驗證配置
    
    如果配置無效會印出警告訊息
    """
    if not CONFIG.validate():
        print("⚠️ 警告：配置驗證未通過，某些功能可能無法正常運作")
    
    if CONFIG.ENABLE_DEBUG:
        print("🔍 [DEBUG] 當前配置資訊：")
        for key, value in CONFIG.get_info().items():
            print(f"  - {key}: {value}")


# 自動執行驗證
validate_config_on_startup()


# ============================================================================
# 使用範例（註解）
# ============================================================================

"""
使用範例：

1. 在程式中引入配置：
   from config import CONFIG, SCHEMA, UI

2. 使用配置值：
   model_name = CONFIG.DEFAULT_MODEL
   max_workers = CONFIG.MAX_WORKERS

3. 透過環境變數覆寫（.env 或 Streamlit Secrets）：
   GEMINI_MODEL=gemini-2.5-flash
   MAX_WORKERS=8

4. 驗證配置：
   if CONFIG.validate():
       print("配置有效")

5. 取得配置資訊：
   info = CONFIG.get_info()
   print(info)
"""

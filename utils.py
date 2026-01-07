"""
AI 採購稽核戰情室 - 工具函式模組
Version: V25 (完整修復版)
"""

import os
import re
import hashlib
import threading
import time
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import pandas as pd
import streamlit as st

from config import CONFIG, SCHEMA

# === 全域變數 ===
_file_locks = {}
_locks_lock = threading.Lock()


# =============================================================================
# 檔案管理
# =============================================================================

def sanitize_filename(filename: str) -> str:
    """
    清理檔案名稱，防止路徑遍歷攻擊

    Args:
        filename: 原始檔案名稱

    Returns:
        清理後的安全檔案名稱
    """
    # 移除路徑分隔符號和特殊字元
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 確保只取檔名部分，移除任何路徑
    safe_name = os.path.basename(safe_name)
    # 移除開頭的點（隱藏檔案）
    safe_name = safe_name.lstrip('.')

    return safe_name if safe_name else "unnamed_file"


def get_file_hash(file_path: str) -> Optional[str]:
    """
    計算檔案的 MD5 雜湊值（用於快取）

    Args:
        file_path: 檔案路徑

    Returns:
        MD5 雜湊值字串，失敗則返回 None
    """
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        st.warning(f"⚠️ 無法計算檔案雜湊值: {e}")
        return None


def validate_file_size(file_path: str, max_size_mb: float = None) -> bool:
    """
    驗證檔案大小是否在限制內

    Args:
        file_path: 檔案路徑
        max_size_mb: 最大檔案大小（MB），預設使用 CONFIG 設定

    Returns:
        是否通過驗證
    """
    if max_size_mb is None:
        max_size_mb = CONFIG.MAX_FILE_SIZE_MB

    try:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > max_size_mb:
            st.warning(f"⚠️ 檔案 {os.path.basename(file_path)} 過大 ({size_mb:.2f} MB > {max_size_mb} MB)")
            return False
        return True
    except Exception as e:
        st.error(f"❌ 無法檢查檔案大小: {e}")
        return False


def cleanup_old_files(directory: str, max_age_hours: int = None) -> int:
    """
    清理超過指定時間的臨時檔案

    Args:
        directory: 要清理的目錄
        max_age_hours: 檔案最大保留時間（小時），預設使用 CONFIG 設定

    Returns:
        清理的檔案數量
    """
    if max_age_hours is None:
        max_age_hours = CONFIG.MAX_TEMP_AGE_HOURS

    if not os.path.exists(directory):
        return 0

    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    cleaned = 0

    try:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)

            if os.path.isfile(filepath):
                file_modified = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_modified < cutoff_time:
                    try:
                        os.remove(filepath)
                        cleaned += 1
                    except OSError as e:
                        st.warning(f"⚠️ 無法刪除 {filename}: {e}")
    except Exception as e:
        st.warning(f"⚠️ 清理臨時檔案時發生錯誤：{str(e)}")

    return cleaned


def ensure_temp_directory() -> str:
    """
    確保臨時目錄存在並已清理舊檔案

    Returns:
        臨時目錄路徑
    """
    temp_dir = CONFIG.TEMP_DIR

    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        st.sidebar.info(f"📁 已建立臨時目錄: {temp_dir}")
    else:
        # 清理舊檔案
        cleaned = cleanup_old_files(temp_dir)
        if cleaned > 0:
            st.sidebar.success(f"🧹 已清理 {cleaned} 個過期檔案")

    return temp_dir


# =============================================================================
# 執行緒安全
# =============================================================================

def get_file_lock(file_path: str) -> threading.Lock:
    """
    取得檔案專屬的執行緒鎖

    Args:
        file_path: 檔案路徑

    Returns:
        該檔案的執行緒鎖物件
    """
    with _locks_lock:
        if file_path not in _file_locks:
            _file_locks[file_path] = threading.Lock()
        return _file_locks[file_path]


def api_rate_limit_sleep():
    """API 速率限制等待（防止觸發 rate limit）"""
    time.sleep(random.uniform(
        CONFIG.API_RATE_LIMIT_MIN,
        CONFIG.API_RATE_LIMIT_MAX
    ))


# =============================================================================
# 資料處理
# =============================================================================

def clean_excel_number(value: Any) -> Any:
    """
    清理並轉換數字格式（移除千分位、貨幣符號）

    Args:
        value: 原始值

    Returns:
        清理後的數值或原始值
    """
    if not value:
        return ""

    if isinstance(value, (int, float)):
        return value

    # 字串處理
    s = str(value).replace(",", "").replace("$", "").replace("NT$", "").strip()

    try:
        f = float(s)
        # 整數不要小數點
        if f.is_integer():
            return int(f)
        return f
    except (ValueError, TypeError):
        return value


def validate_item_data(item: Dict[str, Any], file_name: str, item_index: int) -> bool:
    """
    驗證單筆資料的完整性

    Args:
        item: 資料項目
        file_name: 來源檔案名稱
        item_index: 項目索引

    Returns:
        是否通過驗證
    """
    missing_fields = [
        field for field in SCHEMA.REQUIRED_FIELDS
        if field not in item or not item[field]
    ]

    if missing_fields:
        st.warning(
            f"⚠️ {file_name} 第 {item_index + 1} 筆資料缺少必要欄位：{', '.join(missing_fields)}"
        )
        return False

    return True


def prepare_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    準備 DataFrame 供前台顯示（欄位排序、數字清理）

    Args:
        df: 原始 DataFrame

    Returns:
        處理後的 DataFrame
    """
    # 數字清洗
    for col in SCHEMA.NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].apply(clean_excel_number)

    # 字串型態轉換
    for col in SCHEMA.STRING_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str)

    return df


def prepare_dataframe_for_download(df: pd.DataFrame) -> pd.DataFrame:
    """
    準備 DataFrame 供下載（欄位排序、格式化）

    Args:
        df: 原始 DataFrame

    Returns:
        處理後的 DataFrame
    """
    download_df = df.copy()

    # 依照預定順序排列欄位
    download_order = SCHEMA.get_download_order()
    final_cols = download_order + [
        c for c in download_df.columns if c not in download_order
    ]
    final_cols = [c for c in final_cols if c in download_df.columns]

    download_df = download_df[final_cols]

    # 字串型態轉換（避免 Excel 自動轉換）
    for col in SCHEMA.STRING_COLS:
        if col in download_df.columns:
            download_df[col] = download_df[col].astype(str)

    return download_df


# =============================================================================
# Excel 處理
# =============================================================================

def calculate_column_width(df: pd.DataFrame, col: str) -> int:
    """
    計算 Excel 欄位最佳寬度

    Args:
        df: DataFrame
        col: 欄位名稱

    Returns:
        欄位寬度
    """
    try:
        # 計算內容最大長度
        col_max = df[col].astype(str).map(len).max()
        # 計算標題長度
        header_len = len(str(col))
        # 取較大值
        max_len = max(
            col_max if pd.notna(col_max) else 0,
            header_len
        )
    except Exception:
        # 出錯時使用標題長度
        max_len = len(str(col))

    # 限制在最小/最大寬度之間
    return min(
        max(max_len + 2, CONFIG.MIN_COLUMN_WIDTH),
        CONFIG.MAX_COLUMN_WIDTH
    )


# =============================================================================
# 統計與監控
# =============================================================================

class ProcessingStats:
    """處理統計資訊"""

    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.total_items = 0
        self.start_time = None
        self.end_time = None

    def start(self, total_files: int):
        """開始處理"""
        self.total = total_files
        self.start_time = time.time()

    def add_success(self, item_count: int):
        """記錄成功"""
        self.success += 1
        self.total_items += item_count

    def add_failure(self):
        """記錄失敗"""
        self.failed += 1

    def finish(self):
        """完成處理"""
        self.end_time = time.time()

    def get_duration(self) -> float:
        """取得處理時長（秒）"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0

    def get_summary(self) -> str:
        """取得摘要報告"""
        duration = self.get_duration()
        return (
            f"📊 處理完成統計\n"
            f"- 總檔案數：{self.total}\n"
            f"- 成功：{self.success} | 失敗：{self.failed}\n"
            f"- 擷取資料筆數：{self.total_items}\n"
            f"- 處理時間：{duration:.1f} 秒\n"
            f"- 平均速度：{self.success / duration if duration > 0 else 0:.1f} 檔/秒"
        )
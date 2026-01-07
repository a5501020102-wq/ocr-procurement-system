"""
AI 採購稽核戰情室 - 主程式
Version: V25.6 (修復 function_call 錯誤)

修復內容：
- ✅ 修復 "Could not convert function_call to text" 錯誤
- ✅ 正確處理工具調用回應
- ✅ 支援 SDK 0.8.x 的新行為
"""

import streamlit as st
import os
import pandas as pd
import io
import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Dict, Any

# 引入 openpyxl 處理 Excel
try:
    from openpyxl.utils import get_column_letter
except ImportError:
    st.error("❌ 嚴重錯誤：找不到 openpyxl 套件")
    st.info("💡 請在終端機執行：`pip install openpyxl`")
    st.stop()

# 引入本地模組
try:
    from agent_tools import read_purchase_order
    from config import CONFIG, SCHEMA, UI
    from utils import (
        sanitize_filename, ensure_temp_directory, get_file_lock,
        api_rate_limit_sleep, validate_item_data,
        prepare_dataframe_for_display, prepare_dataframe_for_download,
        calculate_column_width, ProcessingStats, validate_file_size,
        cleanup_old_files
    )
except ImportError as e:
    st.error(f"❌ 模組載入失敗：{e}")
    st.info("💡 請確認所有必要檔案都在同一目錄")
    st.stop()


# =============================================================================
# API 初始化
# =============================================================================

def initialize_api() -> bool:
    """初始化 Google Generative AI API"""
    load_dotenv(override=True)

    # 優先使用 Streamlit secrets（雲端部署）
    try:
        api_key = st.secrets.get("GOOGLE_API_KEY")
    except:
        # 本地開發使用 .env
        api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key or api_key.strip() == "":
        st.error("❌ 致命錯誤：找不到 GOOGLE_API_KEY")
        st.stop()
        return False

    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"❌ API 配置失敗：{str(e)}")
        st.stop()
        return False


# =============================================================================
# 檔案處理核心
# =============================================================================

def process_single_file(file_path: str, split_spec_mode: bool) -> Dict[str, Any]:
    """處理單一檔案（執行緒安全版本）"""
    file_name = os.path.basename(file_path)
    file_lock = get_file_lock(file_path)
    api_rate_limit_sleep()

    with file_lock:
        try:
            if not validate_file_size(file_path):
                return {"file": file_name, "status": "error", "items": [], "error": "檔案大小超過限制"}

            result = read_purchase_order(file_path, split_spec=split_spec_mode)

            if result["status"] == "success":
                items = result.get("data", [])
                valid_items = []
                for idx, item in enumerate(items):
                    validate_item_data(item, file_name, idx)
                    item["_來源檔案"] = file_name
                    valid_items.append(item)
                return {"file": file_name, "status": "success", "items": valid_items, "error": None}
            else:
                return {"file": file_name, "status": "error", "items": [], "error": result.get("error", "未知錯誤")}
        except Exception as e:
            return {"file": file_name, "status": "error", "items": [], "error": str(e)}


# =============================================================================
# 🟢 修復：安全取得 Response Text
# =============================================================================

def safe_get_response_text(response) -> str:
    """
    安全地從 response 取得文字，處理 function_call 的情況

    在 SDK 0.8.x 中，當 AI 使用工具時，response 可能包含：
    - function_call: AI 決定調用哪個函式
    - function_response: 函式執行的結果
    - text: 最終的文字回應
    """
    try:
        # 嘗試直接取得文字
        return response.text
    except ValueError as e:
        # 如果包含 function_call，需要特殊處理
        if "function_call" in str(e).lower() or "convert" in str(e).lower():
            # 嘗試從 parts 中提取文字
            text_parts = []
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)

            if text_parts:
                return "\n".join(text_parts)
            else:
                # 如果完全沒有文字，返回說明
                return "（AI 正在處理工具調用，等待回應...）"
        else:
            # 其他錯誤，重新拋出
            raise e


# =============================================================================
# Gemini Chat 初始化
# =============================================================================

def get_or_create_chat(system_prompt: str):
    """
    確保 chat 總是有效，如果不存在或無效，立即創建
    """
    # 檢查是否已存在且有效
    if "gemini_chat" in st.session_state and st.session_state.gemini_chat is not None:
        try:
            if hasattr(st.session_state.gemini_chat, 'send_message'):
                return st.session_state.gemini_chat
        except:
            pass

    # 不存在或無效，創建新的
    try:
        model = genai.GenerativeModel(
            model_name=CONFIG.DEFAULT_MODEL,
            tools=[read_purchase_order],
            system_instruction=system_prompt
        )

        # 🟢 SDK 0.8.x: 啟用自動函式調用
        chat = model.start_chat(enable_automatic_function_calling=True)

        # 驗證
        if chat is None or not hasattr(chat, 'send_message'):
            raise ValueError("Chat 初始化失敗")

        # 儲存到 session_state
        st.session_state.gemini_chat = chat
        st.session_state.chat_initialized = True

        return chat

    except Exception as e:
        st.error(f"❌ AI 初始化失敗: {str(e)}")
        st.session_state.gemini_chat = None
        st.session_state.chat_initialized = False
        return None


# =============================================================================
# Session State 初始化
# =============================================================================

def init_session_state():
    """初始化 session state"""
    defaults = {
        "messages": [],
        "edit_df": None,
        "gemini_chat": None,
        "chat_initialized": False,
        "processing_stats": ProcessingStats(),
        "file_signature": "",
        "prompt_queue": [],
        "saved_paths": []
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# =============================================================================
# 主程式設定
# =============================================================================

st.set_page_config(page_title=UI.PAGE_TITLE, page_icon=UI.PAGE_ICON, layout=UI.LAYOUT)
st.title(f"{UI.PAGE_ICON} {UI.PAGE_TITLE}")
st.caption(f"核心引擎：{CONFIG.MAX_WORKERS} 執行緒平行運算 | 輸出格式：Excel (.xlsx) | Version 25.6")

init_session_state()
initialize_api()
atexit.register(lambda: cleanup_old_files(CONFIG.TEMP_DIR, 0))

# =============================================================================
# 側邊欄與檔案上傳
# =============================================================================

with st.sidebar:
    st.header("⚙️ 系統設定")
    split_spec_mode = st.toggle("開啟「品名/規格」拆分", value=False)

    st.divider()
    st.header("📁 檔案上傳")
    uploaded_files = st.file_uploader(
        "上傳採購單",
        type=CONFIG.ALLOWED_EXTENSIONS,
        accept_multiple_files=True,
        help=f"支援格式：{', '.join(CONFIG.ALLOWED_EXTENSIONS)}"
    )

    temp_dir = ensure_temp_directory()

    if uploaded_files:
        new_saved_paths = []
        st.success(f"✅ 已載入 {len(uploaded_files)} 個檔案")

        for f in uploaded_files:
            safe_name = sanitize_filename(f.name)
            path = os.path.join(temp_dir, safe_name)
            try:
                with open(path, "wb") as fh:
                    fh.write(f.getbuffer())
                new_saved_paths.append(path)
            except Exception as e:
                st.error(f"❌ 儲存失敗: {e}")

        current_signature = ",".join([f.name for f in uploaded_files])

        if st.session_state.file_signature != current_signature:
            st.session_state.file_signature = current_signature
            st.session_state.saved_paths = new_saved_paths

            if "gemini_chat" in st.session_state:
                del st.session_state.gemini_chat
            st.session_state.chat_initialized = False

            st.toast("🔄 偵測到檔案變更，AI 記憶已刷新！", icon="🧠")
            st.rerun()
        else:
            st.session_state.saved_paths = new_saved_paths

        with st.expander("📋 已上傳檔案"):
            for p in st.session_state.saved_paths:
                st.text(f"• {os.path.basename(p)}")

    else:
        if st.session_state.file_signature != "":
            st.session_state.file_signature = ""
            st.session_state.saved_paths = []

            if "gemini_chat" in st.session_state:
                del st.session_state.gemini_chat
            st.session_state.chat_initialized = False

            st.toast("🗑️ 所有檔案已移除，AI 記憶已重置", icon="🧹")
            st.rerun()
        else:
            st.session_state.saved_paths = []

    st.divider()

    # 顯示系統狀態
    if st.session_state.chat_initialized:
        st.success("🤖 AI 助理：已就緒")
    else:
        st.info("🤖 AI 助理：等待初始化")

    st.caption(f"🗂️ 臨時目錄：`{temp_dir}`")
    st.caption(f"🔧 模型：{CONFIG.DEFAULT_MODEL}")
    st.caption(f"📦 SDK：{genai.__version__}")

# =============================================================================
# 分頁功能
# =============================================================================

tab1, tab2, tab3 = st.tabs(["💬 AI 稽核助理", "🚀 極速批次處理", "📊 處理統計"])

# === Tab 1: AI 稽核助理 ===
with tab1:
    st.write("⚡ **快捷指令**：")

    quick_cols = st.columns(len(UI.QUICK_PROMPTS) + 1)

    for idx, (btn_text, p_text) in enumerate(UI.QUICK_PROMPTS.items()):
        if quick_cols[idx].button(btn_text, key=f"quick_{idx}"):
            st.session_state.prompt_queue.append(p_text)
            st.rerun()

    if quick_cols[-1].button("🧹 清除記憶", key="clear_memory"):
        st.session_state.messages = []
        st.session_state.prompt_queue = []
        if "gemini_chat" in st.session_state:
            del st.session_state.gemini_chat
        st.session_state.chat_initialized = False
        st.toast("✅ 對話記憶已清除", icon="🧹")
        st.rerun()

    st.divider()

    # 動態生成系統提示
    file_names = [os.path.basename(p) for p in st.session_state.saved_paths]
    file_list_str = ", ".join(file_names) if file_names else "（目前無檔案，請先上傳）"

    system_prompt = f"""
你是一個專業的採購稽核師 AI 助理。

【工作環境】
- 使用者檔案位於：'{temp_dir}/'
- 目前可用檔案：{file_list_str}

【重要規則】
1. 所有金額數字必須加上千分位逗號（例如：1,234,567）
2. 優先檢查 '_稽核狀態' 為 '🔴 異常' 的項目
3. 若使用者提到檔名但未指定路徑，請自動補上 '{temp_dir}/' 前綴
4. 發現異常時請明確指出問題所在並提供建議

【能力範圍】
- 讀取並分析採購單資料（使用 read_purchase_order 工具）
- 計算金額、統計資訊
- 檢查數學錯誤、異常項目
- 提供採購建議與風險評估
"""

    # 顯示歷史訊息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 處理輸入
    prompt = st.chat_input("請輸入指令或問題...")

    if st.session_state.prompt_queue:
        prompt = st.session_state.prompt_queue.pop(0)

    if prompt:
        # 確保 chat 存在且有效
        chat = get_or_create_chat(system_prompt)

        if chat is None:
            st.error("❌ AI 助理初始化失敗，請重新整理頁面或聯繫管理員")
            with st.expander("🔍 技術資訊"):
                st.info(f"模型: {CONFIG.DEFAULT_MODEL}")
                st.info(f"SDK: {genai.__version__}")
                st.info("請確認網路連線和 API 配額")
            st.stop()

        # 無檔案警告
        if not st.session_state.saved_paths and any(kw in prompt for kw in ["計算", "分析", "總金額", "項目", "稽核"]):
            st.warning("⚠️ 系統偵測到您尚未上傳檔案，AI 可能無法進行計算分析。")

        # 加入使用者訊息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 回應
        with st.chat_message("assistant"):
            with st.spinner("🕵️‍♂️ AI 稽核師正在分析中..."):
                try:
                    response = chat.send_message(prompt)

                    # 🟢 修復：安全取得回應文字
                    response_text = safe_get_response_text(response)

                    if response_text:
                        st.markdown(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})

                except Exception as e:
                    error_msg = str(e)
                    if "safety" in error_msg.lower():
                        st.error("🚫 內容被 API 安全過濾器攔截")
                        st.info("💡 請調整問題措辭，避免敏感內容")
                    elif "quota" in error_msg.lower():
                        st.error("❌ API 配額已用盡")
                        st.info("💡 請稍後再試，或檢查 API 配額")
                    else:
                        st.error(f"❌ 發生錯誤: {type(e).__name__}")
                        st.info("💡 建議：嘗試「清除記憶」重試")

                    with st.expander("🔍 查看詳細錯誤"):
                        st.code(str(e))

# === Tab 2: 極速批次處理 ===
with tab2:
    st.info(
        f"⚡ **極速模式說明**\n\n"
        f"系統將啟動 {CONFIG.MAX_WORKERS} 個執行緒進行平行運算，"
        f"大幅提升處理速度。"
    )

    if st.button("🚀 啟動極速辨識", type="primary", disabled=not st.session_state.saved_paths):
        if not st.session_state.saved_paths:
            st.warning("⚠️ 請先上傳檔案")
        else:
            stats = ProcessingStats()
            stats.start(len(st.session_state.saved_paths))
            all_data = []
            progress = st.progress(0)
            status = st.empty()

            import multiprocessing

            workers = min(CONFIG.MAX_WORKERS, multiprocessing.cpu_count(), len(st.session_state.saved_paths))
            status.text(f"🚀 已啟動 {workers} 個執行緒...")

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(process_single_file, p, split_spec_mode): p
                    for p in st.session_state.saved_paths
                }

                for i, future in enumerate(as_completed(futures)):
                    res = future.result()
                    progress.progress((i + 1) / len(st.session_state.saved_paths))

                    if res["status"] == "success":
                        stats.add_success(len(res["items"]))
                        all_data.extend(res["items"])
                        status.text(
                            f"✅ [{i + 1}/{len(st.session_state.saved_paths)}] 完成: {res['file']} ({len(res['items'])} 筆)")
                    else:
                        stats.add_failure()
                        status.error(
                            f"❌ [{i + 1}/{len(st.session_state.saved_paths)}] 失敗: {res['file']} - {res['error']}")

            stats.finish()
            progress.empty()

            if all_data:
                st.balloons()
                st.success("🎉 批次處理完成！")
                st.session_state.edit_df = prepare_dataframe_for_display(pd.DataFrame(all_data))
                st.session_state.processing_stats = stats
                st.info(stats.get_summary())
            else:
                st.error("❌ 未能擷取任何資料，請檢查檔案格式")

    # 資料編輯器與下載
    if st.session_state.edit_df is not None:
        st.divider()
        st.subheader("📝 資料稽核與編輯")

        display_order = SCHEMA.get_display_order()
        available_cols = [c for c in display_order if c in st.session_state.edit_df.columns]

        edited_df = st.data_editor(
            st.session_state.edit_df,
            width="stretch",
            num_rows="dynamic",
            column_order=available_cols,
            column_config={
                "_稽核狀態": st.column_config.TextColumn("狀態", width="small", disabled=True),
                "_稽核訊息": st.column_config.TextColumn("稽核說明", width="medium", disabled=True),
                "單價": st.column_config.NumberColumn("單價", format="$%.2f"),
                "金額": st.column_config.NumberColumn("金額", format="$%d"),
                "採購數": st.column_config.NumberColumn("數量", format="%.2f"),
                "_confidence": st.column_config.ProgressColumn("信心度", min_value=0, max_value=1, format="%.2f"),
                "_來源檔案": st.column_config.TextColumn("來源檔案", disabled=True),
            }
        )

        st.divider()
        st.subheader("💾 匯出資料")

        dl_df = prepare_dataframe_for_download(edited_df)
        output = io.BytesIO()

        try:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                dl_df.to_excel(writer, index=False, sheet_name=CONFIG.EXCEL_SHEET_NAME)

                ws = writer.sheets[CONFIG.EXCEL_SHEET_NAME]
                for i, col in enumerate(dl_df.columns):
                    col_width = calculate_column_width(dl_df, col)
                    ws.column_dimensions[get_column_letter(i + 1)].width = col_width

            output.seek(0)

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.download_button(
                    "📥 下載 Excel 檔案",
                    output.getvalue(),
                    CONFIG.EXCEL_OUTPUT_NAME,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            with col2:
                st.metric("總筆數", len(dl_df))
            with col3:
                anomaly = len(dl_df[dl_df["_稽核狀態"] == "🔴 異常"]) if "_稽核狀態" in dl_df.columns else 0
                st.metric("異常筆數", anomaly)

        except Exception as e:
            st.error(f"❌ Excel 生成失敗: {type(e).__name__}")
            with st.expander("🔍 查看詳細錯誤"):
                st.code(str(e))

# === Tab 3: 處理統計 ===
with tab3:
    st.subheader("📊 處理統計資訊")

    if st.session_state.processing_stats.total > 0:
        stats = st.session_state.processing_stats

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("總檔案數", stats.total)
        with col2:
            st.metric("成功處理", stats.success)
        with col3:
            st.metric("處理失敗", stats.failed)
        with col4:
            rate = (stats.success / stats.total * 100) if stats.total > 0 else 0
            st.metric("成功率", f"{rate:.1f}%")

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("擷取資料筆數", stats.total_items)
            st.metric("處理時間", f"{stats.get_duration():.1f} 秒")
        with col2:
            speed = stats.success / stats.get_duration() if stats.get_duration() > 0 else 0
            st.metric("處理速度", f"{speed:.2f} 檔/秒")
            avg = stats.total_items / stats.success if stats.success > 0 else 0
            st.metric("平均每檔筆數", f"{avg:.1f} 筆")

        st.divider()
        with st.expander("📋 查看完整報告"):
            st.code(stats.get_summary())
    else:
        st.info("尚無統計資料，請先在「極速批次處理」執行任務。")

# 頁尾
st.divider()
st.caption(
    f"⚡ {UI.PAGE_TITLE} | "
    f"模型：{CONFIG.DEFAULT_MODEL} | "
    f"執行緒：{CONFIG.MAX_WORKERS} | "
    f"SDK：{genai.__version__} | "
    f"Version 25.6 (Function Call 修復版)"
)
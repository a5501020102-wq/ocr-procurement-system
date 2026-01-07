from ocr_engine import extract_items_with_template

# 欄位定義 (維持 V19 設定，確保資料完整)
DEFAULT_TEMPLATE = {
    "excel_columns": [
        # --- 識別資訊 ---
        "供應商", "採購日期", "訂單號碼", "採購單號",

        # --- 明細內容 ---
        "項次", "廠牌", "品名", "規格",
        "採購數", "單位",
        "牌價", "折數%", "單價", "金額",

        # --- 備註與其他 ---
        "重量", "備註", "交貨日期", "訂購員",
        "聯絡人", "聯絡地址", "交貨地址",

        # --- 系統資訊 ---
        "_confidence"
    ]
}


def clean_num(val):
    """
    [輔助] 將字串轉為浮點數，若失敗回傳 0.0
    處理例如 "1,200" 或 " $500 " 這種格式
    """
    if not val: return 0.0
    if isinstance(val, (int, float)): return float(val)  # 如果已經是數字就直接回傳
    try:
        # 移除逗號、錢字號與空白
        s = str(val).replace(",", "").replace("$", "").replace(" ", "").strip()
        return float(s)
    except:
        return 0.0


def perform_math_check(items, tolerance=5.0):
    """
    [V20 新功能] 執行數學稽核 (紅綠燈邏輯) 并 **強制轉型為數字**
    Args:
        items: OCR 抓出來的明細列表
        tolerance: 容許誤差值 (預設 5 元)
    """
    for item in items:
        # 1. 取得並清洗數值
        qty = clean_num(item.get("採購數"))
        price = clean_num(item.get("單價"))
        amount = clean_num(item.get("金額"))

        # 🟢 [優化] 直接更新 item 內容為數字類型
        # 這樣 Web App 接收到時，就知道這是數字，可以進行排序和格式化顯示 ($1,200)
        item["採購數"] = qty
        item["單價"] = price
        item["金額"] = amount

        # 2. 執行 Python 精準計算
        calculated_amount = qty * price
        diff = abs(amount - calculated_amount)

        # 3. 判斷紅綠燈狀態
        status = ""
        msg = ""

        # 判斷邏輯優化：使用 < 0.01 避免浮點數微小誤差
        if amount == 0 and calculated_amount == 0:
            status = "⚪ 待確認"  # 數值為 0
            msg = "數值為 0 或空白"
        elif diff < 0.01:
            status = "🟢 通過"
            msg = "完美吻合"
        elif diff <= tolerance:
            status = "🟡 誤差"
            msg = f"誤差 {diff:.2f} 元 (可接受)"
        else:
            status = "🔴 異常"
            # 讓 AI 讀到這個訊息，它就會警告使用者
            msg = f"帳面金額 {amount:,.0f} ≠ 計算值 {calculated_amount:,.0f} (差額 {diff:,.0f})"

        # 4. 寫入新欄位
        item["_稽核狀態"] = status
        item["_稽核訊息"] = msg

    return items


def read_purchase_order(file_path: str, split_spec: bool = False):
    """
    [技能描述] 讀取採購單 PDF 或圖片，並自動執行數學稽核。

    使用時機：
    1. 當使用者要求「讀取」、「分析」、「檢查」檔案時。
    2. 系統會自動計算 (單價 x 數量) 並比對金額，標示異常。

    Args:
        file_path (str): 檔案路徑
        split_spec (bool): 是否拆分規格 (True=拆分, False=合併)

    Returns:
        dict: 包含執行狀態、統計摘要與詳細資料
    """
    print(f"\n🤖 [系統訊息] Agent 正在讀取並稽核: {file_path} (拆分: {split_spec})")

    try:
        # 1. 呼叫 OCR 引擎提取資料
        items, errors = extract_items_with_template(file_path, DEFAULT_TEMPLATE, split_spec)

        if not items:
            return {
                "status": "error",
                "message": f"讀取失敗，OCR 未回傳資料。錯誤訊息: {errors}"
            }

        # 2. 執行數學檢查 (並轉型為數字)
        checked_items = perform_math_check(items)

        # 3. 計算統計摘要 (讓 AI 能快速報告)
        error_count = sum(1 for x in checked_items if "🔴" in x["_稽核狀態"])
        warning_count = sum(1 for x in checked_items if "🟡" in x["_稽核狀態"])
        total_amount = sum(x["金額"] for x in checked_items)  # 幫 AI 先算好總額

        return {
            "status": "success",
            "file_processed": file_path,
            "summary": {
                "total_items": len(checked_items),
                "error_items": error_count,  # 紅燈數
                "warning_items": warning_count,  # 黃燈數
                "calculated_total_amount": total_amount,  # 提供總金額給 AI 參考
                "math_check_note": "系統已自動驗算。若有 '🔴 異常'，請優先檢查。"
            },
            "data": checked_items
        }

    except Exception as e:
        return {"status": "error", "message": f"工具執行發生例外錯誤: {str(e)}"}
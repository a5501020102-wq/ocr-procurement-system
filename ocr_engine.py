import os
import json
import time
import re
import glob
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# ============================================================================
# 1. 配置與常數
# ============================================================================

load_dotenv(override=True)
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("❌ [錯誤] 找不到 GOOGLE_API_KEY，請檢查 .env 檔案")
else:
    genai.configure(api_key=api_key)

# 配置常數
MAX_RETRIES = 3
DEBUG_MODE = True
DEBUG_DIR = "debug_logs"

# 🟢 使用最強模型
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# 驗證閾值
class ValidationThresholds:
    PRICE_ERROR_TOLERANCE = 0.05
    DISCOUNT_MIN = 1
    DISCOUNT_MAX = 150
    LIST_PRICE_MIN_RATIO = 0.5
    FALLBACK_CONFIDENCE_PENALTY = 0.2
    LOW_CONFIDENCE_THRESHOLD = 0.7
    FLOAT_EPSILON = 0.001


if DEBUG_MODE and not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)


# ============================================================================
# 2. 輔助函數
# ============================================================================

def normalize_roc_date(date_str: str) -> str:
    """轉換民國年為西元年"""
    if not date_str: return ""
    s = re.sub(r'[^\d]', '', str(date_str).strip())
    match_digits = re.match(r'^(\d{2,3})(\d{2})(\d{2})$', s)
    if match_digits:
        y, m, d = match_digits.groups()
        year = int(y)
        if year < 1900: year += 1911
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{year}/{m}/{d}"
    return date_str


def clean_money(value) -> str:
    """清理金額字串"""
    if not value: return "0"
    s = str(value).upper().replace('O', '0').replace('L', '1').replace('I', '1')
    clean_val = re.sub(r'[^\d.]', '', s)
    try:
        float(clean_val)
        return clean_val
    except ValueError:
        return "0"


def validate_prices(prices_dict: Dict[str, str], quantity: str) -> Dict:
    """驗證價格合理性"""
    warnings = []
    confidence = 1.0
    try:
        list_price = float(prices_dict.get("牌價") or 0)
        discount_val = float(prices_dict.get("折數%") or 0)
        unit_price = float(prices_dict.get("單價") or 0)
        amount = float(prices_dict.get("金額") or 0)
        qty = float(clean_money(quantity)) if quantity else 0
    except (ValueError, TypeError) as e:
        return {"is_valid": False, "warnings": [f"價格格式錯誤: {str(e)}"], "confidence": 0.0}

    if unit_price > 0 and qty > 0 and amount > 0:
        expected = unit_price * qty
        error = abs(amount - expected) / expected
        if error > ValidationThresholds.PRICE_ERROR_TOLERANCE:
            warnings.append(f"金額異常: {amount} ≠ {unit_price}*{qty}")
            confidence -= 0.3

    if list_price > 0 and discount_val > 0 and unit_price > 0:
        rate = discount_val / 100.0 if discount_val > 1 else discount_val
        expected = list_price * rate
        if expected > 0:
            error = abs(unit_price - expected) / expected
            if error > ValidationThresholds.PRICE_ERROR_TOLERANCE:
                warnings.append(f"單價異常: {unit_price} ≠ {list_price}*{discount_val}%")
                confidence -= 0.2

    confidence = max(0.0, min(1.0, confidence))
    return {"is_valid": len(warnings) == 0, "warnings": warnings, "confidence": confidence}


def allocate_prices_smart(raw_prices_str: str, quantity: str) -> Dict[str, str]:
    """Fallback: 智慧分配價格"""
    price_list = [clean_money(x) for x in raw_prices_str.split() if clean_money(x) != "0"]
    result = {"牌價": "", "折數%": "", "單價": "", "金額": ""}
    if not price_list: return result

    try:
        prices = [float(p) for p in price_list]
    except ValueError:
        return result

    qty = float(clean_money(quantity)) if quantity else 0
    used_indices = set()

    if len(prices) >= 4:
        amount_idx = prices.index(max(prices))
        amount = prices[amount_idx]
        used_indices.add(amount_idx)

        remaining = [(i, p) for i, p in enumerate(prices) if i not in used_indices]
        if qty > 0:
            unit_idx, unit_price = min(remaining, key=lambda x: abs(x[1] - (amount / qty)))
        else:
            unit_idx, unit_price = max(remaining, key=lambda x: x[1])
        used_indices.add(unit_idx)

        remaining = [(i, p) for i, p in enumerate(prices) if i not in used_indices]
        if remaining:
            disc_idx, discount = min(remaining, key=lambda x: x[1])
            used_indices.add(disc_idx)
        else:
            discount = ""

        remaining = [(i, p) for i, p in enumerate(prices) if i not in used_indices]
        list_price = remaining[0][1] if remaining else ""

        result = {"牌價": str(list_price), "折數%": str(discount), "單價": str(unit_price), "金額": str(amount)}

    elif len(prices) == 3:
        amount_idx = prices.index(max(prices))
        amount = prices[amount_idx]
        used_indices.add(amount_idx)

        remaining = [(i, p) for i, p in enumerate(prices) if i not in used_indices]
        if qty > 0:
            unit_idx, unit_price = min(remaining, key=lambda x: abs(x[1] - (amount / qty)))
        else:
            unit_idx, unit_price = max(remaining, key=lambda x: x[1])
        used_indices.add(unit_idx)

        remaining = [(i, p) for i, p in enumerate(prices) if i not in used_indices]
        last = remaining[0][1]
        if last < unit_price and last < 150:
            result = {"牌價": "", "折數%": str(last), "單價": str(unit_price), "金額": str(amount)}
        else:
            result = {"牌價": str(last), "折數%": "", "單價": str(unit_price), "金額": str(amount)}

    elif len(prices) == 2:
        result = {"牌價": "", "折數%": "", "單價": str(min(prices)), "金額": str(max(prices))}

    return result


def sanitize_filename(filename: str) -> str:
    basename = os.path.basename(filename)
    name_without_ext = os.path.splitext(basename)[0]
    safe_name = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fa5]', '_', name_without_ext)
    return safe_name[:100]


def save_debug_log(filename: str, debug_data: Dict):
    if not DEBUG_MODE: return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = sanitize_filename(filename)
    log_file = os.path.join(DEBUG_DIR, f"{safe_filename}_{timestamp}.json")
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
    except:
        pass


# ============================================================================
# 3. 主要提取函數 (V19 核心)
# ============================================================================

# 🟢 [關鍵更新] 加入 split_spec 參數，預設為 False，防止 main.py 沒傳參數時報錯
def extract_items_with_template(image_path: str, template: Dict, split_spec: bool = False) -> Tuple[
    List[Dict], List[str]]:
    """
    從採購單圖片/PDF 提取明細資料
    Args:
        split_spec: 是否拆分品名與規格 (True=拆分, False=合併)
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"檔案不存在: {image_path}")

    filename = os.path.basename(image_path)
    start_time = time.time()

    # 🟢 動態產生指令 (這裡就是 AI 聽話的關鍵)
    if split_spec:
        spec_instruction = "1. **品名規格拆分**：請將「主要名稱」填入 ProductName，「尺寸/型號/規格」填入 Spec。例如：'軟管 1\"' -> ProductName='軟管', Spec='1\"'。"
    else:
        spec_instruction = "1. **品名規格合併 (勿拆)**：請將「品名+尺寸+型號」全部完整填入 ProductName，並務必將 Spec 欄位留空 (\"\")。例如：'軟管 1\"' -> ProductName='軟管 1\"', Spec=''。"

    print(f"\n{'=' * 60}")
    print(f"[Gemini API] 啟動: {GEMINI_MODEL} | 檔案: {filename}")
    print(f"⚙️ 模式: {'✅ 拆分規格' if split_spec else '⛔ 合併規格'}")
    print(f"{'=' * 60}")

    debug_log = {
        "file": filename,
        "model": GEMINI_MODEL,
        "mode": "split" if split_spec else "merge",
        "timestamp": datetime.now().isoformat(),
        "parsed_items": [],
        "errors": []
    }

    model = genai.GenerativeModel(GEMINI_MODEL)

    # V19 Prompt: 植入動態指令
    prompt = f"""
    你是一個高階採購單據分析師。請提取圖片中的表格資料並輸出為 JSON。

    【重要規則】
    {spec_instruction}
    2. **價格欄位**：請優先提取結構化欄位 (牌價, 折數, 單價, 金額)。
    3. **RawPrices (保險機制)**：請務必將該行「所有看到的價格數字」填入 RawPrices，以空白分隔。
    4. **日期**：請提取原始字串 (如 1141028)，不要自行轉換。
    5. **空值**：若欄位空白請填 ""。

    【JSON 結構】
    {{
        "header": {{
            "Supplier": "供應商", "Purchaser": "買方",
            "VendorOrderNo": "訂單號碼", "PurchaseDate": "日期",
            "PONumber": "採購單號"
        }},
        "items": [
            {{
                "Index": "1",
                "ItemDate": "1141028",
                "ItemOrderNo": "11411B0324",
                "Brand": "南亞", 
                "ProductName": "膠合劑", 
                "Spec": "1KG", 
                "Quantity": "40", "Unit": "罐",
                "PriceFields": {{
                    "ListPrice": "250", "Discount": "80",
                    "UnitPrice": "200", "Amount": "8000"
                }},
                "RawPrices": "250 80 200 8000",
                "Remarks": ""
            }}
        ]
    }}
    """

    sample_file = None

    try:
        sample_file = genai.upload_file(path=image_path, display_name="PurchaseOrder")
        print(f"   📤 檔案上傳成功")

        for attempt in range(MAX_RETRIES):
            try:
                print(f"   🔄 分析中 (嘗試 {attempt + 1}/{MAX_RETRIES})...")
                response = model.generate_content(
                    [prompt, sample_file],
                    generation_config={"response_mime_type": "application/json"}
                )

                response_text = response.text.replace("```json", "").replace("```", "").strip()
                debug_log["raw_response"] = response_text

                try:
                    data = json.loads(response_text)
                except:
                    # 容錯處理：有時 AI 會多講話，嘗試抓取第一個 { ... }
                    match = re.search(r'(\{.*\}|\[.*\])', response_text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                    else:
                        raise ValueError("JSON 解析失敗")

                header = data.get("header", {})
                items_list = data.get("items", [])
                if not items_list and isinstance(data, list):
                    items_list = data
                    header = {}

                print(f"   ✅ 成功解析 {len(items_list)} 筆明細")

                final_items = []
                columns_def = template.get("excel_columns", [])

                for entry in items_list:
                    item_dict = {}

                    item_dict['訂單號碼'] = entry.get('ItemOrderNo') or header.get('VendorOrderNo', '')
                    item_dict['採購單號'] = header.get('PONumber', '')
                    raw_date = entry.get('ItemDate') or header.get('PurchaseDate', '')
                    item_dict['採購日期'] = normalize_roc_date(raw_date)
                    item_dict['供應商'] = header.get('Supplier', '')
                    item_dict['訂購員'] = header.get('Purchaser', '')
                    item_dict['聯絡地址'] = header.get('Address', '')

                    item_dict['項次'] = str(entry.get('Index', ''))
                    item_dict['廠牌'] = entry.get('Brand', '')
                    item_dict['品名'] = entry.get('ProductName', '')
                    item_dict['規格'] = entry.get('Spec', '')
                    item_dict['單位'] = entry.get('Unit', '')
                    item_dict['採購數'] = clean_money(entry.get('Quantity'))
                    item_dict['重量'] = str(entry.get('Weight', ''))
                    item_dict['備註'] = entry.get('Remarks', '')

                    # 價格處理
                    price_fields = entry.get('PriceFields', {})
                    has_structured = bool(price_fields.get('UnitPrice') or price_fields.get('Amount'))
                    used_fallback = False

                    if has_structured:
                        item_dict['牌價'] = price_fields.get('ListPrice', '')
                        item_dict['折數%'] = price_fields.get('Discount', '')
                        item_dict['單價'] = price_fields.get('UnitPrice', '')
                        item_dict['金額'] = price_fields.get('Amount', '')
                    else:
                        raw_str = entry.get('RawPrices', '')
                        if raw_str:
                            print(f"      ⚠️ 項次 {item_dict['項次']} 啟用 Fallback 機制")
                            allocated = allocate_prices_smart(raw_str, item_dict['採購數'])
                            item_dict['牌價'] = allocated['牌價']
                            item_dict['折數%'] = allocated['折數%']
                            item_dict['單價'] = allocated['單價']
                            item_dict['金額'] = allocated['金額']
                            used_fallback = True
                        else:
                            item_dict['牌價'] = item_dict['折數%'] = item_dict['單價'] = item_dict['金額'] = ""

                    # 驗證
                    validation = validate_prices(
                        {"牌價": item_dict['牌價'], "折數%": item_dict['折數%'], "單價": item_dict['單價'],
                         "金額": item_dict['金額']},
                        item_dict['採購數']
                    )
                    confidence = validation["confidence"]
                    if used_fallback: confidence -= ValidationThresholds.FALLBACK_CONFIDENCE_PENALTY
                    item_dict['_confidence'] = round(max(0, confidence), 2)

                    if not validation["is_valid"] or confidence < ValidationThresholds.LOW_CONFIDENCE_THRESHOLD:
                        warnings = validation["warnings"]
                        if confidence < ValidationThresholds.LOW_CONFIDENCE_THRESHOLD:
                            warnings.insert(0, f"信心度低 ({confidence:.0%})")
                        warning_text = " | ".join(warnings[:2])
                        item_dict['備註'] = f"⚠️ {warning_text} " + str(item_dict['備註'])
                        print(f"      🚩 警告: {warning_text}")

                    # 補欄位
                    for col in columns_def:
                        if col not in item_dict: item_dict[col] = ""

                    final_items.append(item_dict)
                    debug_log["parsed_items"].append(item_dict)

                elapsed = time.time() - start_time
                print(f"   ⏱️ 耗時: {elapsed:.2f} 秒")
                save_debug_log(filename, debug_log)
                return final_items, []

            except Exception as e:
                print(f"   ❌ API 錯誤: {e}")
                debug_log["errors"].append(str(e))
                if attempt < MAX_RETRIES - 1:
                    print("   ⏳ 等待 2 秒重試...")
                    time.sleep(2)

        save_debug_log(filename, debug_log)
        return [], ["超過最大重試次數"]

    finally:
        if sample_file:
            try:
                genai.delete_file(sample_file.name)
            except:
                pass


# 4. 批次處理函式 (給獨立測試用)
def batch_extract(image_folder: str, template: Dict, output_json: Optional[str] = None) -> Tuple[
    List[Dict], List[Dict]]:
    print(f"\n🚀 啟動批次處理: {image_folder}")
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.pdf']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(image_folder, ext)))
        files.extend(glob.glob(os.path.join(image_folder, ext.upper())))

    files = sorted(list(set(files)))
    print(f"📂 找到 {len(files)} 個檔案\n")

    all_items = []
    all_errors = []

    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] 處理: {os.path.basename(f)}")
        # 這裡也要修正呼叫方式，預設不拆分
        items, errors = extract_items_with_template(f, template, split_spec=False)

        if items:
            for it in items: it['_source_file'] = os.path.basename(f)
            all_items.extend(items)
        if errors: all_errors.append({"file": f, "errors": errors})
        if i < len(files): time.sleep(1)

    if output_json and all_items:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n🏁 批次完成! 成功: {len(all_items)} 筆, 失敗: {len(all_errors)}")
    return all_items, all_errors
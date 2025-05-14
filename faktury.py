import requests
import json
import os
import sys
from datetime import date, timedelta, datetime

# ========== 🧭 Nastavení cest (funguje pro .py i .exe) ==========

# Určení základní složky podle prostředí
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)  # při běhu z .exe
else:
    BASE_DIR = os.getcwd()  # při běhu v Colabu nebo běžném skriptu

# Příklady složek:
INVOICE_FOLDER = os.path.join(BASE_DIR, "json_faktury")
FLEXIBEE_FOLDER = os.path.join(BASE_DIR, "flexibee_json")
ERROR_LOG = os.path.join(BASE_DIR, "chyby_log.txt")

log_file_name = os.path.join(BASE_DIR, f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")

# ========== 📄 Duální výstup do konzole a logu ==========
log_file = open(log_file_name, "a", encoding="utf-8")

class DualOutput:
    def __init__(self, log_file):
        self.terminal = sys.__stdout__
        self.log_file = log_file

    def write(self, message):
        try:
            self.terminal.write(message)
        except Exception:
            pass
        self.log_file.write(message)

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        self.log_file.flush()

sys.stdout = DualOutput(log_file)
sys.stderr = DualOutput(log_file)

print(f"\n===== Spuštěno: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")

# ========== ⚙️ Konfigurace ==========
API_KEY = "3bfmV*18472@6482*KBXJtKwc-!*pbb4"
EMAIL = "smid13@seznam.cz"

# ========== 🛠️ Pomocné funkce ==========
def log_error(message):
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{time_str}] {message}"
    with open(ERROR_LOG, "a", encoding="utf-8") as logf:
        logf.write(full_message + "\n")
    print(full_message)

def map_vat_rate(rate):
    return {
        21: "typSzbDph.dphZakl",
        15: "typSzbDph.dphSniz",
        10: "typSzbDph.dphSniz2",
        0: "typSzbDph.dphOsv"
    }.get(rate, "typSzbDph.dphOsv")

def convert_to_flexibee_format(original_data):
    mj_id = 1
    polozky = []
    for idx, item in enumerate(original_data.get("items", []), start=1):
        polozky.append({
            "id": f"ext:POLOZKA-{idx}",
            "nazev": item["item_name"],
            "mnozMj": item["item_quantity"],
            "cenaMj": item["item_unit_price"],
            "typSzbDphK": map_vat_rate(item["item_vat_rate"]),
            "typCenyDphK": "typCeny.sDph",
            "mj": {"id": mj_id}
        })

    return {
        "winstrom": {
            "faktura-vydana": [{
                "id": f"ext:FAKTURA-{original_data['invoice_number']}",
                "typDokl": "code:FAKTURA",
                "kod": original_data["invoice_number"],
                "varSym": original_data.get("invoice_vs", ""),
                "datVyst": original_data["invoice_date_issue"],
                "datSplat": original_data["invoice_date_due"],
                "mena": "code:CZK",
                "firma": {
                    "nazev": original_data["customer"],
                    "ulice": original_data["customer_street"],
                    "mesto": original_data["customer_city"],
                    "psc": original_data["customer_zip"],
                    "stat": "code:CZ",
                    "ic": original_data["customer_ico"].replace(" ", ""),
                    "dic": original_data["customer_dic"]
                },
                "poznam": original_data.get("invoice_note", ""),
                "bezPolozek": False,
                "polozkyDokladu@removeAll": True,
                "polozkyDokladu": polozky
            }]
        }
    }

# ========== 📆 Datumové rozsahy ==========
today = date.today()
yesterday = today - timedelta(days=1)

# ========== 🌐 Připojení k API ==========
session = requests.Session()
init_data = {"key": API_KEY, "email": EMAIL}
init_url = "https://www.fakturyweb.cz/api/init?data=" + requests.utils.quote(json.dumps(init_data))
session.get(init_url)

list_data = {
    "key": API_KEY,
    "email": EMAIL,
    "from": str(yesterday),
    "to": str(today)
}
list_url = "https://www.fakturyweb.cz/api/list/issued?data=" + requests.utils.quote(json.dumps(list_data))
list_response = session.get(list_url)
list_result = list_response.json()

if list_result.get("status") != 1:
    log_error(f"Chyba nebo žádné faktury v rozsahu: {list_result}")
    faktury = []
else:
    faktury = list_result.get("invoices", [])

print(f"📄 Faktur ke zpracování: {len(faktury)}")

# ========== 💾 Ukládání ==========
os.makedirs(INVOICE_FOLDER, exist_ok=True)
os.makedirs(FLEXIBEE_FOLDER, exist_ok=True)
ulozeno = 0
preskoceno = 0

for faktura in faktury:
    invoice_number = faktura.get("invoice_number", "nezname")
    invoice_code = faktura.get("code")

    if not invoice_code or invoice_number == "nezname":
        log_error("Faktura bez kódu nebo čísla – přeskočeno.")
        continue

    json_path = os.path.join(INVOICE_FOLDER, f"{invoice_number}.json")
    flexibee_path = os.path.join(FLEXIBEE_FOLDER, f"{invoice_number}_flexibee.json")

    if os.path.exists(json_path):
        log_error(f"Faktura {invoice_number} už existuje – přeskočeno.")
        preskoceno += 1
        continue

    detail_data = {"key": API_KEY, "email": EMAIL, "code": invoice_code}
    detail_url = "https://www.fakturyweb.cz/api/status?data=" + requests.utils.quote(json.dumps(detail_data))
    detail_response = session.get(detail_url)
    detail_result = detail_response.json()

    if detail_result.get("status") != 1:
        log_error(f"Chyba při stahování detailu faktury {invoice_number}")
        continue

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(detail_result, f, ensure_ascii=False, indent=2)

        flexibee_json = convert_to_flexibee_format(detail_result)
        with open(flexibee_path, "w", encoding="utf-8") as f:
            json.dump(flexibee_json, f, ensure_ascii=False, indent=2)

        ulozeno += 1
        print(f"💾 Uložena faktura: {invoice_number}")

    except Exception as e:
        log_error(f"Výjimka při ukládání {invoice_number}: {str(e)}")
        continue

print(f"\n✅ Hotovo! Uloženo: {ulozeno}, Přeskočeno: {preskoceno}")
print(f"===== Dokončeno: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")

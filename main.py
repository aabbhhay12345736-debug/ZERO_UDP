# ============================================================
# STAR GUEST GENERATOR
# Generation : app.py (step1..step8) — untouched
# Save/UI    : app.py style (atomic + dedup)
# Password   : app.py style (os.urandom hex)
# + NEW-GENN style speed  (worker-loop threading)
# + EXACT count  (never over-generates, hard stop)
# ============================================================

import os, sys, json, time, hmac, uuid, codecs, hashlib, random, re
import requests, urllib3, threading
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# GLOBAL CONFIG
# ============================================================
REGION = "IND"
ACCOUNT_COUNT = 1
GLOBAL_THREAD_COUNT = 1
SUPERSCRIPT_DIGITS = 5
NICKNAME_PREFIX = "Star"

REGION_HOST = "loginbp.ppmainecoonghj.com"
CLIENT_HOST = "clientbp.ppmainecoonghj.com"
CONNECT_BASE = "ffmconnect.live.gop.garenanow.com"
MSDK_BASE    = "ffmmsdk.live.gop.garenanow.com"

CLIENT_VERSION = "1.132.6"
RELEASE_VERSION = "OB55"
UNITY_VERSION = "2018.4.12f1"

cLiEnT_iD = 100067
cLiEnT_sEcReT = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# ============================================================
# COLORS
# ============================================================
class Colors:
    RED='\033[91m'; GREEN='\033[92m'; YELLOW='\033[93m'; BLUE='\033[94m'
    PURPLE='\033[95m'; CYAN='\033[96m'; WHITE='\033[97m'
    BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

# ============================================================
# CRYPTO
# ============================================================
AES_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
AES_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

# ============================================================
# NAME GENERATOR
# ============================================================
def generate_custom_name(prefix=None):
    if prefix is None: prefix = NICKNAME_PREFIX
    sm = {"0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹"}
    digits = ''.join(random.choice("0123456789") for _ in range(SUPERSCRIPT_DIGITS))
    return f"{prefix}ㅤ{''.join(sm[d] for d in digits)}"

def generate_ascii_name(prefix=None):
    if prefix is None: prefix = NICKNAME_PREFIX
    return f"{prefix}{random.randint(10000, 99999)}"

# ============================================================
# FOLDERS
# ============================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_FOLDER = os.path.join(CURRENT_DIR, "Accounts")
ACCOUNTS_FOLDER = os.path.join(BASE_FOLDER, "ACCOUNTS")
TOKENS_FOLDER = os.path.join(BASE_FOLDER, "TOKENS-JWT")
for f in [BASE_FOLDER, ACCOUNTS_FOLDER, TOKENS_FOLDER]:
    os.makedirs(f, exist_ok=True)

# ============================================================
# UI
# ============================================================
def clear_screen(): os.system('cls' if os.name == 'nt' else 'clear')

def get_random_color():
    return random.choice([Colors.CYAN, Colors.GREEN, Colors.YELLOW,
                          Colors.PURPLE, Colors.BLUE, Colors.WHITE])

def display_banner():
    color = get_random_color()
    print(f"""
{color}{Colors.BOLD}
      ███████╗████████╗ █████╗ ██████╗
      ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
      ███████╗   ██║   ███████║██████╔╝
      ╚════██║   ██║   ██╔══██║██╔══██╗
      ███████║   ██║   ██║  ██║██║  ██║
      ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
{Colors.RESET}
{get_random_color()}{Colors.BOLD}      STAR GAMER GUEST GENERATOR PRO{Colors.RESET}
{get_random_color()}{Colors.BOLD}           OFFICIAL TELEGRAM : @STAR_METHODE{Colors.RESET}
""")

def print_success(msg): print(f"{Colors.GREEN}{Colors.BOLD}✅ {msg}{Colors.RESET}")
def print_error(msg):   print(f"{Colors.RED}{Colors.BOLD}❌ {msg}{Colors.RESET}")

def print_warning(msg):
    for ig in ["429", "503", "Too Many Requests", "Service Temporarily"]:
        if ig in msg: return
    print(f"{Colors.YELLOW}{Colors.BOLD}⚠️ {msg}{Colors.RESET}")

def print_success_box(acc, cnt, total):
    color = get_random_color()
    print(f"\n{color}{Colors.BOLD}╔════════════════════════════════════════╗{Colors.RESET}")
    print(f"{color}{Colors.BOLD}║ ✅ #{cnt}/{total}{Colors.RESET}")
    print(f"{color}{Colors.BOLD}╠════════════════════════════════════════╣{Colors.RESET}")
    print(f"{color}║ 📌 UID  : {Colors.CYAN}{acc.get('uid','N/A')}{Colors.RESET}")
    print(f"{color}║ 🔑 PASS : {Colors.CYAN}{acc.get('password','N/A')}{Colors.RESET}")
    print(f"{color}║ 👤 NAME : {Colors.CYAN}{acc.get('name','N/A')}{Colors.RESET}")
    print(f"{color}║ 🎮 ID   : {Colors.CYAN}{acc.get('account_id','N/A')}{Colors.RESET}")
    print(f"{color}║ 🌍 REG  : {Colors.CYAN}{acc.get('region','N/A')}{Colors.RESET}")
    print(f"{color}{Colors.BOLD}╚════════════════════════════════════════╝{Colors.RESET}")

# ============================================================
# PROTO HELPERS
# ============================================================
def varint(n):
    if n < 0: n += 1 << 64
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        if n: out.append(b | 0x80)
        else: out.append(b); return bytes(out)

def build_field(fn, val):
    if isinstance(val, bool):
        return varint((fn << 3) | 0) + varint(1 if val else 0)
    if isinstance(val, int):
        return varint((fn << 3) | 0) + varint(val)
    if isinstance(val, (str, bytes)):
        d = val.encode("utf-8") if isinstance(val, str) else val
        return varint((fn << 3) | 2) + varint(len(d)) + d
    if isinstance(val, dict):
        sub = assemble(val)
        return varint((fn << 3) | 2) + varint(len(sub)) + sub
    raise TypeError(f"Unsupported: {type(val)}")

def assemble(fields):
    packet = b""
    norm = {}
    for k, v in fields.items():
        try: norm[int(k)] = v
        except: pass
    for k in sorted(norm):
        v = norm[k]
        if isinstance(v, list):
            for item in v: packet += build_field(k, item)
        else: packet += build_field(k, v)
    return packet

def aes_enc(plain):
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(plain, AES.block_size))

def aes_dec(data):
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(data)

def parse_proto(data):
    result = {}; i = 0
    try:
        while i < len(data):
            tag = data[i]; f = tag >> 3; w = tag & 7; i += 1
            if w == 0:
                val = 0; sh = 0
                while i < len(data):
                    b = data[i]; i += 1
                    val |= (b & 0x7F) << sh
                    if not (b & 0x80): break
                    sh += 7
                result[f] = val
            elif w == 2:
                ln = 0; sh = 0
                while i < len(data):
                    b = data[i]; i += 1
                    ln |= (b & 0x7F) << sh
                    if not (b & 0x80): break
                    sh += 7
                result[f] = data[i:i+ln]; i += ln
            elif w == 5: result[f] = data[i:i+4]; i += 4
            elif w == 1: result[f] = data[i:i+8]; i += 8
            else: break
    except: pass
    return result

def _decode_varint(data, offset):
    result = 0; shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1; shift += 7
        if not (byte & 0x80): return result, offset
    return None, offset

def _extract_field8_jwt(raw):
    o = 0
    while o < len(raw) - 1:
        idx = raw.find(b"\x42", o)
        if idx < 0: break
        length, after = _decode_varint(raw, idx + 1)
        if length is None: o = idx + 1; continue
        end = after + length
        if end <= len(raw) and raw[after:after + 3] == b"eyJ":
            return raw[after:end]
        o = idx + 1
    return None

def encode_open_id(original):
    ks = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,
          0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30]
    return ''.join(chr(ord(c) ^ ks[i % len(ks)]) for i, c in enumerate(original))

# ============================================================
# IP ROTATOR
# ============================================================
import ipaddress
class IPRotator:
    REGION_IP_CIDRS = {
        "TW": ["1.160.0.0/12", "36.224.0.0/12", "114.24.0.0/12", "118.160.0.0/12"],
        "VN": ["1.52.0.0/14", "14.160.0.0/11", "27.64.0.0/12"],
        "TH": ["1.46.0.0/15", "27.55.0.0/16", "49.228.0.0/15"],
        "BD": ["27.147.128.0/17", "37.111.192.0/19", "103.220.220.0/22"],
        "ID": ["36.64.0.0/11", "101.255.0.0/16", "103.10.60.0/22"],
        "IND": ["1.6.0.0/15", "1.38.0.0/15", "14.96.0.0/15"],
        "ME": ["5.32.0.0/11", "37.128.0.0/11", "94.200.0.0/13"],
        "PK": ["39.32.0.0/11", "103.22.0.0/16", "111.68.0.0/14"],
        "BR": ["177.0.0.0/10", "189.0.0.0/11", "200.128.0.0/9"],
        "US": ["3.0.0.0/8", "8.0.0.0/7", "64.0.0.0/11"],
        "SAC": ["181.0.0.0/11", "190.0.0.0/11", "200.0.0.0/11"],
        "CIS": ["5.16.0.0/12", "31.128.0.0/11", "77.88.0.0/18"],
    }
    @classmethod
    def get_random_ip(cls, region):
        cidrs = cls.REGION_IP_CIDRS.get(region.upper(), ["203.113.0.0/16"])
        cidr = random.choice(cidrs)
        try:
            net = ipaddress.IPv4Network(cidr, strict=False)
            offset = random.randint(1, net.num_addresses - 2)
            return str(ipaddress.IPv4Address(int(net.network_address) + offset))
        except: return "203.113.1.1"
    @classmethod
    def get_ip_headers(cls, region):
        ip = cls.get_random_ip(region)
        return {"X-Forwarded-For": ip, "X-Real-IP": ip, "Client-IP": ip}

# ============================================================
# ✅ EXACT COUNT + THREADING GLOBALS
# ============================================================
EXIT_FLAG = False
SUCCESS_COUNTER = 0
TARGET_ACCOUNTS = 0
STAT_LOCK = threading.Lock()

# ============================================================
# SAVE SYSTEM
# ============================================================
file_lock = threading.Lock()
success_lock = threading.Lock()
successful_count = 0
tOtAl_AcCoUnTs = ACCOUNT_COUNT

def save_account_data(region, account_entry, jwt_entry):
    reg = region.upper()
    with file_lock:
        # --- accounts ---
        af = os.path.join(ACCOUNTS_FOLDER, f"accounts-{reg}.json")
        data = []
        if os.path.exists(af):
            try:
                with open(af, "r", encoding="utf-8") as f: data = json.load(f)
            except: data = []
        existing_ids = {x.get('account_id') for x in data if x.get('account_id')}
        if account_entry.get('account_id') and account_entry['account_id'] not in existing_ids:
            data.append(account_entry)
            tmp = af + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush(); os.fsync(f.fileno())
                os.replace(tmp, af)
            except: pass

        # --- tokens ---
        if jwt_entry.get("token"):
            jf = os.path.join(TOKENS_FOLDER, f"jwt-{reg}.json")
            jd = []
            if os.path.exists(jf):
                try:
                    with open(jf, "r", encoding="utf-8") as f: jd = json.load(f)
                except: jd = []
            existing_uids = {x.get('uid') for x in jd if x.get('uid')}
            if jwt_entry.get('uid') and jwt_entry['uid'] not in existing_uids:
                jd.append(jwt_entry)
                tmp = jf + ".tmp"
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(jd, f, indent=2, ensure_ascii=False)
                        f.flush(); os.fsync(f.fileno())
                    os.replace(tmp, jf)
                except: pass

# ============================================================
# RANDOM MSDK UA
# ============================================================
def random_msdk_ua():
    devices = ["ASUS_AI2401_A", "SM-G998B", "CPH2095", "Pixel 6", "OnePlus 9 Pro",
               "Samsung Galaxy S23 Ultra", "Xiaomi 13 Pro", "Redmi Note 10 Pro",
               "Moto G100", "OPPO Find X3", "Vivo X60 Pro", "Realme GT 5G"]
    device = random.choice(devices)
    version = random.choice(["9", "10", "11", "12", "13"])
    lang = random.choice(["en", "hi", "id", "th"])
    region = random.choice(["US", "IND", "ID", "TH"])
    return f"GarenaMSDK/4.0.44({device} ;Android {version};{lang};{region};app {CLIENT_VERSION} 2019121229;)"

# ============================================================
# STEP 1: GUEST REGISTER
# ============================================================
def step1_register(session, password):
    url = f"https://{CONNECT_BASE}/api/v2/oauth/guest:register"
    payload = {"app_id": cLiEnT_iD, "client_type": 2, "password": password, "source": 2}
    raw = json.dumps(payload, separators=(',', ':'))
    sig = hmac.new(cLiEnT_sEcReT.encode(), raw.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": random_msdk_ua(),
        "Authorization": f"Signature {sig}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
    }
    try:
        r = session.post(url, headers=headers, data=raw, timeout=20, verify=False)
        if r.status_code != 200:
            print_warning(f"Register: HTTP {r.status_code}")
            return None
        uid = r.json().get("data", {}).get("uid")
        if not uid:
            print_warning(f"Register: no uid")
            return None
        return uid
    except Exception as e:
        print_warning(f"Register: {e}")
        return None

# ============================================================
# STEP 2: TOKEN GRANT
# ============================================================
def step2_token(session, uid, password):
    url = f"https://{CONNECT_BASE}/api/v2/oauth/guest/token:grant"
    payload = {
        "client_id": cLiEnT_iD, "client_secret": cLiEnT_sEcReT,
        "client_type": 2, "password": password,
        "response_type": "token", "uid": int(uid)
    }
    raw = json.dumps(payload, separators=(',', ':'))
    headers = {
        "User-Agent": random_msdk_ua(),
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
    }
    try:
        r = session.post(url, headers=headers, data=raw, timeout=20, verify=False)
        if r.status_code != 200:
            print_warning(f"Token: HTTP {r.status_code}")
            return None
        d = r.json().get("data", {})
        oid = d.get("open_id"); at = d.get("access_token")
        if not oid or not at:
            print_warning(f"Token: missing")
            return None
        return oid, at
    except Exception as e:
        print_warning(f"Token: {e}")
        return None

# ============================================================
# STEP 3: DEVICE-ID
# ============================================================
def step3_device_id(session):
    url = f"https://{MSDK_BASE}/device/api/v1/android/device-id:generate"
    payload_json = {
        "app_id": 100067,
        "data": {
            "ad_aaid": "", "android_id": "01b05346c944b5e6",
            "android_version_release": "10", "android_version_sdk": "29",
            "brand": "Google", "build_date": "1697185398000",
            "build_display": "NHG47O release-keys", "build_id": "NHG47O",
            "cpu_abis": "arm64-v8a,armeabi-v7a,armeabi",
            "drm_id": "", "drm_vendor": "",
            "fingerprint": "Google/sailfish/sailfish:10/NHG47O/eng.build.20231013.013027:user/release-keys",
            "gcbooster_uuid": "", "hardware": "msm8996", "imei": "",
            "model": "Pixel", "key_mqs_uuid": "", "product_name": "sailfish",
            "random_uuid": str(uuid.uuid4()),
            "soc_manufacturer": "", "soc_model": ""
        }
    }
    raw = json.dumps(payload_json, separators=(',', ':'))
    sig = hmac.new(cLiEnT_sEcReT.encode(), raw.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": f"GarenaMSDK/4.0.44(Pixel ;Android 10;en;US;app {CLIENT_VERSION} 2019121229;)",
        "Authorization": f"Signature {sig}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        **IPRotator.get_ip_headers(REGION),
    }
    try:
        r = session.post(url, headers=headers, data=raw, timeout=20, verify=False)
        if r.status_code == 200:
            j = r.json()
            if j.get("code") == 0:
                return j["data"].get("device_id", "")
    except: pass
    return ""

# ============================================================
# STEP 4: MAJOR REGISTER
# ============================================================
FIELD22_HEX = '474752450101010067020000a6a42db7bc5516876af3d1ba4adc337bac558af092eb3757d59d65c9323bba42c6593a48b74f33b2b5b3dc45cbd7ac02040db58f394045be4835213e12c35e5566445a5224f39d205fcf91c0e6bec797e7b3968ac00e90d7500b5865828a9d6f2091c3070f5319a130748e407ed57e6638974670ac045631b3d08c310cf1256cebcf1aed2d97d177534603d1c95d9c5d698340e797e72aa7ecc67a33122e48b0dfda050a1649586aca5e979be1fd9d99f48cd8cf59630e0ff60f67d4ed2ec4e5e7475970449a6c06329009ee0ce2567892587675781a31e4bb2774403b2f78e9811df2cb397fa602572266747704c6258077910902eb7420bcb4ab743d1610cddba9019e7867aaad3aa7ba9b04968064a409b66733f9f78c566a25ff478cba37a2ffe23203d4b05bceef826f174b0be7912d19432cc759325251fa094d70693fb672d6f9e799284081b3adb541dd8f27ef80dcf1e7f0ff30f2fd976659457ce41e175a2d6301b777981ccc16b9a8247abaab8de0867836c27de0146fe4d0e1fd39b86ba51f0b58601cfcbd7f6f3451fe4184b26ed44ac2f6f7bb4ce5d9a80f88c2cbfe7553e5ab97c8b028ae16b4f70f037753b8c229a6e5e9038fcbb9b4c2abb954894f8f2faf177bfdaab3b0ed537156633621d16b62d58ba4ebe518997c33e2304976ba6af9df7e7e34302c7910ae559c7e3d20a30d71c14f85c0e86f26291bbf18c2d9dfe9a908592eea4523e6c1e5d9bb5abfbebfccd5c4e136f9be777723e932b06c029df5125191000c90fde62a8e5f8fceb28648f0c69ec3037d09302b2ade908a20dbd42761ca449b2743fc362649e16235769d9fbd7f87cd64972b58d69c0441abb5d22ddc6ed059f7ac1bdbfaef8c60e64631809c5e08c7cb4074c8ce6170d94b411604986be4ae163a'

def step4_major_register(session, access_token, open_id, nickname):
    url = f"https://{REGION_HOST}/MajorRegister"
    lang = {"IND":"hi","BR":"pt","US":"en","ID":"id","TH":"th","VN":"vi",
            "ME":"ar","PK":"ur","BD":"bn","TW":"zh","CIS":"ru","SAC":"es"}.get(REGION.upper(), "en")

    encoded_open_id = encode_open_id(open_id)
    field14 = encoded_open_id.encode('latin1', errors='ignore')

    payload_fields = {
        1: nickname, 2: access_token, 3: open_id,
        5: 102000007, 6: 4, 7: 1, 13: 1,
        14: field14,
        15: lang, 16: 1, 17: 1,
        20: CLIENT_VERSION, 21: 1,
        22: bytes.fromhex(FIELD22_HEX),
    }
    payload = aes_enc(assemble(payload_fields))

    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer",
        "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue", "Host": REGION_HOST,
        "ReleaseVersion": RELEASE_VERSION,
        "User-Agent": f"UnityPlayer/{UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1", "X-GA-SV": str(int(time.time())),
        "X-Unity-Version": UNITY_VERSION,
        **IPRotator.get_ip_headers(REGION),
    }
    try:
        r = session.post(url, headers=headers, data=payload, timeout=20, verify=False)
        if r.status_code == 200:
            parsed = parse_proto(r.content)
            account_id = None
            if parsed and 3 in parsed:
                account_id = parsed[3]
                if isinstance(account_id, bytes):
                    try: account_id = account_id.decode()
                    except: account_id = account_id.hex()
            return {"name": nickname, "account_id": str(account_id) if account_id else None}
        else:
            print_warning(f"MajorRegister: HTTP {r.status_code}")
            return None
    except Exception as e:
        print_warning(f"MajorRegister: {e}")
    return None

# ============================================================
# STEP 5: CHOOSE NEWBIE
# ============================================================
def step5_choose_newbie(session, account_id):
    if not account_id: return False
    url = f"https://{REGION_HOST}/ChooseNewbieChoice"
    payload = aes_enc(assemble({1: int(account_id), 2: 1, 3: 3}))
    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer",
        "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue", "Host": REGION_HOST,
        "ReleaseVersion": RELEASE_VERSION,
        "User-Agent": f"UnityPlayer/{UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1", "X-GA-SV": str(int(time.time())),
        "X-Unity-Version": UNITY_VERSION,
        **IPRotator.get_ip_headers(REGION),
    }
    try:
        r = session.post(url, headers=headers, data=payload, timeout=20, verify=False)
        return r.status_code == 200
    except: return False

# ============================================================
# STEP 6: MAJOR LOGIN
# ============================================================
def build_major_login_payload(access_token, open_id, platform_type=4):
    fields = {
        3: str(datetime.now())[:-7], 4: "free fire", 5: 1, 7: CLIENT_VERSION,
        8: "Android OS 10 / API-29 (NHG47O/eng.build.20231013.013027)",
        9: "Handheld", 10: "TelKila", 11: "WIFI",
        12: 1708, 13: 750, 14: "440", 15: "ARM64 FP ASIMD AES | 2850 | 8",
        16: 3968, 17: "Mali-G610 MC6",
        18: "OpenGL ES 3.2 v1.r32p1-01eac0.54329dee8f160f288c574caaf67bbe3f",
        19: "Google|0ecc7b3b-6c41-462e-9050-26d835e84c53",
        20: IPRotator.get_random_ip(REGION),
        21: {"IND":"hi","BR":"pt","US":"en","ID":"id","TH":"th","VN":"vi",
             "ME":"ar","PK":"ur","BD":"bn","TW":"zh","CIS":"ru","SAC":"es"}.get(REGION.upper(), "en"),
        22: open_id, 23: str(platform_type), 24: "Handheld",
        25: "Google Pixel", 26: REGION.upper(), 29: access_token, 30: 1,
        41: "TelKila", 42: "WIFI",
        57: "7428b253defc164018c604a1ebbfebdf",
        60: 109029, 61: 37616, 62: 2048, 63: 804,
        64: 37616, 65: 109029, 66: 37616, 67: 109029,
        73: 3,
        74: "/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/lib/arm64",
        76: 1,
        77: "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/base.apk",
        78: 3, 79: 2, 81: "64", 83: "2019121229",
        85: 3, 86: "OpenGLES2", 87: 511, 88: platform_type,
        92: 36711, 93: "android",
        94: "KqsHT8at0g7Na/G7iOeF1IpesHMf+HoePFMFFE8Tq/dSk4fIbJ1j8TdV8OAyWIVnSmD2rM6vfFMtCD8Ig7iROgDJmIMrdtcB6orwuNRpMr4MVu3D7FoTcuQdq/8EyOkRQiUrbg==",
        96: '{"cur_rate":null,"support_etc2":false}',
        97: 1, 99: str(platform_type), 100: str(platform_type),
        102: bytes.fromhex('4000434f07555f0637'),
        104: 1797, 105: 1,
        106: "https://dl.cdn.freefiremobile.com/live/ABHotUpdates/|https://dl-core.cdn.freefiremobile.com/live/ABHotUpdates/|4a0070ac356973792f002e0b25b96c3b",
        107: "c8e41b7a93f02d56e1a94c7b8203f5d1"
    }
    return aes_enc(assemble(fields))

def step6_major_login(session, access_token, open_id, platform_type=4, tag="L1"):
    url = f"https://{REGION_HOST}/MajorLogin"
    payload = build_major_login_payload(access_token, open_id, platform_type)
    headers = {
        'X-Unity-Version': UNITY_VERSION, 'ReleaseVersion': RELEASE_VERSION,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': 'Bearer', 'Accept': '*/*', 'Expect': '100-continue',
        'X-GA': 'v1 1', 'X-GA-SV': str(int(time.time())),
        'User-Agent': f"UnityPlayer/{UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        'Host': REGION_HOST,
        'Connection': 'Keep-Alive', 'Accept-Encoding': 'deflate, gzip',
        **IPRotator.get_ip_headers(REGION),
    }
    try:
        r = session.post(url, headers=headers, data=payload, timeout=20, verify=False)
        if r.status_code == 200:
            jwt_bytes = _extract_field8_jwt(r.content)
            if jwt_bytes is None:
                text = r.text
                js = text.find("eyJ")
                if js != -1:
                    jwt = text[js:]
                    dot2 = jwt.find(".", jwt.find(".") + 1)
                    if dot2 != -1:
                        jwt_bytes = jwt[:dot2 + 44].encode('utf-8', 'replace')
            if jwt_bytes:
                return jwt_bytes.decode('utf-8', 'replace')
    except: pass
    return None

# ============================================================
# STEP 7: CHOOSE REGION
# ============================================================
def step7_choose_region(session, jwt_token):
    url = f"https://{REGION_HOST}/ChooseRegion"
    body = aes_enc(assemble({1: REGION.upper()}))
    headers = {
        "X-Unity-Version": UNITY_VERSION, "ReleaseVersion": RELEASE_VERSION,
        "Content-Type": "application/x-www-form-urlencoded",
        "Expect": "100-continue",
        "Authorization": f"Bearer {jwt_token}",
        "User-Agent": f"UnityPlayer/{UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Host": REGION_HOST, "Connection": "Keep-Alive",
        "X-GA": "v1 1", "Accept-Encoding": "gzip",
    }
    try:
        r = session.post(url, headers=headers, data=body, timeout=20, verify=False)
        return r.status_code == 200
    except: return False

# ============================================================
# STEP 8: GET LOGIN DATA
# ============================================================
def step8_get_login_data(session, jwt_token, access_token, open_id, platform_type=4):
    url = f"https://{CLIENT_HOST}/GetLoginData"
    fields = {
        3: str(datetime.now())[:-7], 4: "free fire", 5: 1, 7: CLIENT_VERSION,
        8: "Android OS 10 / API-29 (NHG47O/eng.build.20231013.013027)",
        9: "Handheld", 10: "TelKila", 11: "WIFI",
        12: 1708, 13: 750, 14: "440", 15: "ARM64 FP ASIMD AES | 2850 | 8",
        16: 3968, 17: "Mali-G610 MC6",
        18: "OpenGL ES 3.2 v1.r32p1-01eac0.54329dee8f160f288c574caaf67bbe3f",
        19: "Google|0ecc7b3b-6c41-462e-9050-26d835e84c53",
        20: IPRotator.get_random_ip(REGION),
        21: {"IND":"hi","BR":"pt","US":"en","ID":"id","TH":"th","VN":"vi",
             "ME":"ar","PK":"ur","BD":"bn","TW":"zh","CIS":"ru","SAC":"es"}.get(REGION.upper(), "en"),
        22: open_id, 23: str(platform_type), 24: "Handheld",
        25: "Google Pixel", 26: REGION.upper(), 29: access_token, 30: 1,
        41: "TelKila", 42: "WIFI",
        57: "7428b253defc164018c604a1ebbfebdf",
        73: 3,
        74: "/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/lib/arm64",
        76: 1,
        77: "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/base.apk",
        78: 3, 79: 2, 81: "64", 83: "2019121229",
        85: 3, 86: "OpenGLES2", 87: 511, 88: platform_type,
        90: bytes.fromhex('48e1baa3692044c6b0c6a16e67'), 91: "61",
        92: 36711, 93: "android",
        94: "KqsHT8at0g7Na/G7iOeF1IpesHMf+HoePFMFFE8Tq/dSk4fIbJ1j8TdV8OAyWIVnSmD2rM6vfFMtCD8Ig7iROgDJmIMrdtcB6orwuNRpMr4MVu3D7FoTcuQdq/8EyOkRQiUrbg==",
        96: '{"cur_rate":null,"support_etc2":false}', 97: 1,
        99: "0", 100: str(platform_type),
        102: bytes.fromhex('4000434f07555f0637'),
        103: 1, 104: 1797, 105: 1,
        106: "https://dl.cdn.freefiremobile.com/live/ABHotUpdates/|https://dl-core.cdn.freefiremobile.com/live/ABHotUpdates/|4a0070ac356973792f002e0b25b96c3b",
        107: "c8e41b7a93f02d56e1a94c7b8203f5d1"
    }
    payload = aes_enc(assemble(fields))
    headers = {
        'X-Unity-Version': UNITY_VERSION, 'ReleaseVersion': RELEASE_VERSION,
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-GA': 'v1 1', 'X-GA-SV': str(int(time.time())),
        'User-Agent': f"UnityPlayer/{UNITY_VERSION} (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        'Host': CLIENT_HOST,
        'Connection': 'Keep-Alive', 'Accept-Encoding': 'gzip',
        'Authorization': f'Bearer {jwt_token}',
        **IPRotator.get_ip_headers(REGION),
    }
    try:
        r = session.post(url, headers=headers, data=payload, timeout=20, verify=False)
        if r.status_code == 200:
            return parse_proto(r.content)
    except: pass
    return None

# ============================================================
# ✅ CREATE ACCOUNT (FIXED: all globals declared)
# ============================================================
def create_account(index, existing_uids, region):
    global successful_count, SUCCESS_COUNTER, TARGET_ACCOUNTS, EXIT_FLAG

    # ⛔ exact-count: stop before starting if quota full
    with STAT_LOCK:
        if EXIT_FLAG: return
        if SUCCESS_COUNTER >= TARGET_ACCOUNTS: return

    # app.py password
    password = os.urandom(32).hex().upper()
    session = requests.Session()
    session.verify = False

    custom_name = generate_custom_name(NICKNAME_PREFIX)

    # Step 1
    uid = step1_register(session, password)
    if not uid: return

    # Step 2
    r2 = step2_token(session, uid, password)
    if not r2: return
    open_id, access_token = r2

    if uid in existing_uids: return

    # Step 3
    device_id = step3_device_id(session)

    # Step 4
    r4 = step4_major_register(session, access_token, open_id, custom_name)
    if not r4:
        ascii_name = generate_ascii_name(NICKNAME_PREFIX)
        print_warning(f"Fancy name fail → trying ASCII: {ascii_name}")
        r4 = step4_major_register(session, access_token, open_id, ascii_name)
        if not r4: return
    name = r4["name"]
    account_id = r4.get("account_id")

    # Step 5
    if account_id:
        step5_choose_newbie(session, account_id)

    # Step 6
    jwt1 = step6_major_login(session, access_token, open_id)
    if not jwt1: return

    # Step 7
    step7_choose_region(session, jwt1)

    # Step 6b
    jwt2 = step6_major_login(session, access_token, open_id)
    jwt_final = jwt2 if jwt2 else jwt1

    # Step 8
    ld = step8_get_login_data(session, jwt_final, access_token, open_id)
    if ld and 1 in ld:
        f1 = ld[1]
        if isinstance(f1, int):
            account_id = str(f1)

    # ⛔ exact-count: discard if another thread already filled quota
    with STAT_LOCK:
        if SUCCESS_COUNTER >= TARGET_ACCOUNTS:
            return
        SUCCESS_COUNTER += 1
        current = SUCCESS_COUNTER
        with success_lock:
            successful_count += 1

    # Save
    account_entry = {
        "uid": str(uid), "password": password,
        "account_id": str(account_id) if account_id else None,
        "name": name, "region": region.upper(),
        "device_id": device_id,
        "created": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    jwt_entry = {
        "access_token": access_token, "token": jwt_final or "",
        "uid": str(uid), "region": region.upper()
    }
    save_account_data(region, account_entry, jwt_entry)
    existing_uids.add(uid)

    print_success_box(account_entry, current, TARGET_ACCOUNTS)

    time.sleep(random.uniform(0.3, 1.0))

# ============================================================
# ✅ WORKER THREAD
# ============================================================
def worker_thread(existing_uids, region, thread_id):
    tc = get_random_color()
    print(f"{tc}{Colors.BOLD}🧵 Thread {thread_id} started{Colors.RESET}")
    idx = 0
    while not EXIT_FLAG:
        with STAT_LOCK:
            if SUCCESS_COUNTER >= TARGET_ACCOUNTS:
                break
        idx += 1
        try:
            create_account(idx, existing_uids, region)
        except Exception as e:
            print_warning(f"T{thread_id}: {e}")
        time.sleep(random.uniform(0.1, 0.3))
    print(f"{tc}{Colors.BOLD}🧵 Thread {thread_id} finished{Colors.RESET}")

# ============================================================
# VIEW
# ============================================================
def view_accounts():
    clear_screen(); display_banner()
    print(f"{Colors.BOLD}{Colors.CYAN}📁 VIEW SAVED ACCOUNTS{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
    ta = tj = 0
    if os.path.exists(ACCOUNTS_FOLDER):
        for f in [f for f in os.listdir(ACCOUNTS_FOLDER) if f.endswith('.json')]:
            try:
                with open(os.path.join(ACCOUNTS_FOLDER, f), 'r', encoding='utf-8') as fp:
                    d = json.load(fp); ta += len(d)
                    print(f"{Colors.WHITE}   📄 {f}: {Colors.CYAN}{len(d)} accounts{Colors.RESET}")
            except: pass
    if os.path.exists(TOKENS_FOLDER):
        for f in [f for f in os.listdir(TOKENS_FOLDER) if f.endswith('.json')]:
            try:
                with open(os.path.join(TOKENS_FOLDER, f), 'r', encoding='utf-8') as fp:
                    d = json.load(fp); tj += len(d)
                    print(f"{Colors.WHITE}   📄 {f}: {Colors.CYAN}{len(d)} tokens{Colors.RESET}")
            except: pass
    print(f"\n{Colors.BOLD}{Colors.GREEN}📊 TOTAL: {ta} accounts | {tj} tokens{Colors.RESET}")
    input(f"\n{Colors.YELLOW}▶ Press Enter to continue...{Colors.RESET}")

# ============================================================
# ✅ GENERATE FLOW
# ============================================================
def generate_flow():
    global successful_count, tOtAl_AcCoUnTs, REGION, NICKNAME_PREFIX, GLOBAL_THREAD_COUNT
    global SUCCESS_COUNTER, TARGET_ACCOUNTS, EXIT_FLAG

    clear_screen(); display_banner()

    # Region
    print(f"{Colors.BOLD}{Colors.CYAN}🌍 AVAILABLE REGIONS:{Colors.RESET}")
    regions = ["IND", "ME", "ID", "VN", "TH", "BD", "PK", "TW", "CIS", "SAC", "US", "BR"]
    for i, r in enumerate(regions, 1):
        print(f"{Colors.WHITE}  {i:2}) {Colors.CYAN}{r}{Colors.RESET}")

    while True:
        try:
            choice = input(f"\n{Colors.YELLOW}{Colors.BOLD}🎯 Choose region: {Colors.RESET}").strip().upper()
            if choice in regions:
                REGION = choice; break
            elif choice.isdigit() and 1 <= int(choice) <= len(regions):
                REGION = regions[int(choice) - 1]; break
            else:
                print_error("Invalid region.")
        except KeyboardInterrupt:
            return

    # Count (EXACT)
    while True:
        try:
            count = int(input(f"\n{Colors.YELLOW}{Colors.BOLD}🔢 Total accounts (exact): {Colors.RESET}").strip())
            if count > 0:
                tOtAl_AcCoUnTs = count; break
            else:
                print_error("Enter positive number.")
        except ValueError:
            print_error("Invalid number.")
        except KeyboardInterrupt:
            return

    # Prefix
    while True:
        prefix = input(f"\n{Colors.YELLOW}{Colors.BOLD}👤 Nickname prefix (e.g. Star / Shadow / King): {Colors.RESET}").strip()
        if prefix:
            NICKNAME_PREFIX = prefix; break
        else:
            print_error("Cannot be empty.")

    # Threads
    while True:
        try:
            threads = int(input(f"\n{Colors.YELLOW}{Colors.BOLD}🧵 Thread count (default 3): {Colors.RESET}").strip() or "3")
            if threads > 0:
                GLOBAL_THREAD_COUNT = threads; break
            else:
                print_error("Must be positive.")
        except ValueError:
            print_error("Invalid number.")
        except KeyboardInterrupt:
            return

    # Confirm
    clear_screen(); display_banner()
    print(f"{Colors.GREEN}{Colors.BOLD}🚀 STARTING GENERATION{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}")
    print(f"{Colors.WHITE}🌍 Region:      {Colors.CYAN}{REGION}{Colors.RESET}")
    print(f"{Colors.WHITE}🔢 Total:       {Colors.CYAN}{count} (exact){Colors.RESET}")
    print(f"{Colors.WHITE}👤 Prefix:      {Colors.CYAN}{NICKNAME_PREFIX}{Colors.RESET}")
    print(f"{Colors.WHITE}✨ Name Style:  {Colors.CYAN}{NICKNAME_PREFIX}ㅤ³³³⁷³{Colors.RESET}")
    print(f"{Colors.WHITE}🔑 Password:    {Colors.CYAN}os.urandom(32).hex().upper(){Colors.RESET}")
    print(f"{Colors.WHITE}🧵 Threads:     {Colors.CYAN}{threads}{Colors.RESET}")
    print(f"{Colors.WHITE}📁 Saving to:   {Colors.CYAN}{ACCOUNTS_FOLDER}{Colors.RESET}")
    print(f"{Colors.WHITE}🌐 Login Host:  {Colors.CYAN}{REGION_HOST}{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}")
    print(f"{Colors.YELLOW}⏳ Starting in 3 seconds...{Colors.RESET}")
    time.sleep(3)

    # Load existing UIDs
    existing_uids = set()
    rf = os.path.join(ACCOUNTS_FOLDER, f"accounts-{REGION.upper()}.json")
    if os.path.exists(rf):
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_uids = {acc.get("uid") for acc in data if acc.get("uid")}
        except: pass
    initial = len(existing_uids)
    successful_count = initial

    # reset globals for exact count
    SUCCESS_COUNTER = 0
    TARGET_ACCOUNTS = count
    EXIT_FLAG = False
    start = time.time()

    print(f"\n{get_random_color()}{Colors.BOLD}🚀 Launching {threads} threads...{Colors.RESET}\n")

    ts = []
    for i in range(threads):
        t = threading.Thread(target=worker_thread, args=(existing_uids, REGION, i+1))
        t.daemon = True
        t.start()
        ts.append(t)

    # live progress
    try:
        while any(t.is_alive() for t in ts):
            time.sleep(1)
            with STAT_LOCK:
                cur = SUCCESS_COUNTER
            pct = (cur / count) * 100 if count else 0
            el = time.time() - start
            sp = cur / el if el > 0 else 0
            print(f"\r{get_random_color()}{Colors.BOLD}📊 {cur}/{count} "
                  f"({pct:.1f}%) | ⚡ {sp:.2f}/s | STAR PRO{Colors.RESET}",
                  end="", flush=True)
            if cur >= count: break
    except KeyboardInterrupt:
        print_warning("Interrupted by user!")
        EXIT_FLAG = True

    for t in ts: t.join(timeout=5)

    elapsed = round(time.time() - start, 2)
    new_count = SUCCESS_COUNTER
    print(f"\n\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}📊 SUMMARY{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.WHITE}🌍 Region:    {Colors.CYAN}{REGION}{Colors.RESET}")
    print(f"{Colors.WHITE}🔢 Target:    {Colors.CYAN}{count}{Colors.RESET}")
    print(f"{Colors.WHITE}✅ Generated: {Colors.GREEN}{new_count}{Colors.RESET}")
    print(f"{Colors.WHITE}⏱  Time:      {Colors.CYAN}{elapsed}s{Colors.RESET}")
    print(f"{Colors.WHITE}⚡ Speed:     {Colors.CYAN}{new_count/elapsed if elapsed>0 else 0:.2f}/s{Colors.RESET}")
    print(f"{Colors.WHITE}📁 Saved to:  {Colors.CYAN}{ACCOUNTS_FOLDER}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    input(f"\n{Colors.YELLOW}▶ Press Enter...{Colors.RESET}")

# ============================================================
# ABOUT
# ============================================================
def about():
    clear_screen(); display_banner()
    print(f"{Colors.BOLD}{Colors.CYAN}ℹ️  ABOUT{Colors.RESET}")
    print(f"{Colors.CYAN}{'─'*60}{Colors.RESET}\n")
    print(f"{Colors.WHITE}Version: 7.2 (app.py + EXACT + SPEED){Colors.RESET}")
    print(f"{Colors.WHITE}Creator: STAR GAMER{Colors.RESET}")
    print(f"\n{Colors.GREEN}{Colors.BOLD}✨ FEATURES:{Colors.RESET}")
    print(f"{Colors.WHITE}   • app.py full flow (step1..step8)")
    print(f"{Colors.WHITE}   • EXACT count (never over-generates)")
    print(f"{Colors.WHITE}   • NEW-GENN style worker-thread loop (fast)")
    print(f"{Colors.WHITE}   • Atomic save + dedup")
    print(f"{Colors.WHITE}   • app.py password (os.urandom hex)")
    print(f"{Colors.WHITE}   • Custom name + ASCII fallback")
    print(f"{Colors.WHITE}   • Multi-region + IP rotation")
    print(f"{Colors.WHITE}   • Live speed / progress")
    input(f"\n{Colors.YELLOW}▶ Press Enter...{Colors.RESET}")

# ============================================================
# MAIN MENU
# ============================================================
def main():
    while True:
        clear_screen(); display_banner()
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.WHITE}📋 MAIN MENU{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.CYAN} 1{Colors.RESET} → {Colors.GREEN}{Colors.BOLD}GENERATE ACCOUNTS{Colors.RESET}")
        print(f"{Colors.CYAN} 2{Colors.RESET} → {Colors.GREEN}{Colors.BOLD}VIEW SAVED{Colors.RESET}")
        print(f"{Colors.CYAN} 3{Colors.RESET} → {Colors.GREEN}{Colors.BOLD}ABOUT{Colors.RESET}")
        print(f"{Colors.CYAN} 0{Colors.RESET} → {Colors.RED}{Colors.BOLD}EXIT{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
        try:
            ch = input(f"\n{Colors.YELLOW}{Colors.BOLD}🎯 CHOOSE: {Colors.RESET}").strip()
            if ch == "1": generate_flow()
            elif ch == "2": view_accounts()
            elif ch == "3": about()
            elif ch == "0":
                print(f"\n{Colors.GREEN}{Colors.BOLD}👋 Bye!{Colors.RESET}"); sys.exit(0)
            else:
                print_error("Invalid"); time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n{Colors.GREEN}{Colors.BOLD}👋 Bye!{Colors.RESET}"); sys.exit(0)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print(f"\n{Colors.GREEN}{Colors.BOLD}👋 Bye!{Colors.RESET}"); sys.exit(0)
    except Exception as e:
        print_error(f"Fatal: {e}"); sys.exit(1)
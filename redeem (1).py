import json, os, random, string, time, threading
from datetime import datetime, timedelta
CODES_FILE = 'redeem_codes.json'
PREMIUM_FILE = 'premium.txt'
_LOCK = threading.Lock()
PLANS = {
    'basic': {'label': 'BASIC', 'days': 1, 'workers': 20, 'mass_limit': 1000, 'credits': 0},
    'pro':   {'label': 'PRO',   'days': 7,  'workers': 30, 'mass_limit': 5000,  'credits': 0},
    'max':   {'label': 'MAX',   'days': 30, 'workers': 50, 'mass_limit': 10000, 'credits': 0},
    'ultra': {'label': 'ULTRA', 'days': 90, 'workers': 200, 'mass_limit': 50000,'credits': 0},
}
def _load():
    if not os.path.exists(CODES_FILE):
        return {}
    with _LOCK:
        try:
            with open(CODES_FILE) as f:
                return json.load(f)
        except:
            return {}
def _save(data):
    with _LOCK:
        with open(CODES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
def _generate_code_str():
    chars = string.ascii_uppercase + string.digits
    return 'DEVEN-' + '-'.join(''.join(random.choices(chars, k=4)) for _ in range(3))
def generate_code(plan, days=0, max_uses=1, created_by=0, workers=0, mass_limit=0):
    data = _load()
    code = _generate_code_str()
    while code in data:
        code = _generate_code_str()
    preset = PLANS.get(plan, PLANS['basic'])
    data[code] = {
        'plan': plan,
        'days': days or preset['days'],
        'workers': workers or preset['workers'],
        'mass_limit': mass_limit or preset['mass_limit'],
        'max_uses': max_uses,
        'used': 0,
        'created_by': created_by,
        'created_at': time.time(),
        'redeemed_by': [],
        'revoked': False,
    }
    _save(data)
    return code
def redeem_code(code, user_id):
    """Redeem a code. Returns dict with success and details."""
    code = code.strip().upper()
    data = _load()
    if code not in data:
        return {'success': False, 'error': 'Code not found.'}
    entry = data[code]
    if entry.get('revoked'):
        return {'success': False, 'error': 'Code has been revoked.'}
    if entry['used'] >= entry['max_uses']:
        return {'success': False, 'error': 'Code has already been used.'}
    if str(user_id) in entry.get('redeemed_by', []):
        return {'success': False, 'error': 'You have already redeemed this code.'}
    entry['used'] += 1
    entry.setdefault('redeemed_by', []).append(str(user_id))
    _save(data)
    now = datetime.now()
    expiry = now + timedelta(days=entry['days'])
    _add_premium_user(user_id, expiry.isoformat())
    return {
        'success': True,
        'plan': entry['plan'],
        'days': entry['days'],
        'workers': entry['workers'],
        'mass_limit': entry['mass_limit'],
        'expiry': expiry.isoformat(),
    }
def _add_premium_user(user_id, expiry_str):
    with _LOCK:
        lines = []
        if os.path.exists(PREMIUM_FILE):
            with open(PREMIUM_FILE) as f:
                lines = [l.strip() for l in f if l.strip()]
        lines = [l for l in lines if not l.startswith(str(user_id) + '|')]
        lines.append(f"{user_id}|{expiry_str}")
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                f.write(l + '\n')
def is_premium_user(user_id):
    with _LOCK:
        if not os.path.exists(PREMIUM_FILE):
            return False
        with open(PREMIUM_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(str(user_id) + '|') or line == str(user_id):
                    return True
        return False
def get_active_codes():
    data = _load()
    result = []
    for code, entry in data.items():
        if not entry.get('revoked') and entry['used'] < entry['max_uses']:
            result.append({
                'code': code,
                'plan': entry['plan'],
                'used': entry['used'],
                'max_uses': entry['max_uses'],
                'days': entry['days'],
                'created_by': entry['created_by'],
            })
    return result
def get_code_info(code):
    data = _load()
    code = code.strip().upper()
    if code not in data:
        return None
    entry = data[code]
    return {
        'code': code,
        'plan': entry['plan'],
        'days': entry['days'],
        'workers': entry['workers'],
        'mass_limit': entry['mass_limit'],
        'used': entry['used'],
        'max_uses': entry['max_uses'],
        'created_by': entry['created_by'],
        'created_at': entry['created_at'],
        'revoked': entry.get('revoked', False),
        'redeemed_by': entry.get('redeemed_by', []),
    }
def revoke_code(code):
    data = _load()
    code = code.strip().upper()
    if code not in data:
        return False
    data[code]['revoked'] = True
    _save(data)
    return True
def revoke_all_codes():
    data = _load()
    count = 0
    for code in data:
        if not data[code].get('revoked'):
            data[code]['revoked'] = True
            count += 1
    _save(data)
    return count
def is_redeem_code_text(text):
    import re
    return bool(re.match(r'^(?:DEVEN|SHOPI)-[A-Z0-9][A-Z0-9-]{5,}$', str(text or '').strip(), re.IGNORECASE))
def get_expired_premium_users():
    expired = []
    with _LOCK:
        if not os.path.exists(PREMIUM_FILE):
            return expired
        with open(PREMIUM_FILE) as f:
            for line in f:
                line = line.strip()
                if '|' in line:
                    parts = line.split('|', 1)
                    if len(parts) == 2:
                        try:
                            expiry = datetime.fromisoformat(parts[1])
                            if expiry < datetime.now():
                                expired.append({'user_id': int(parts[0]), 'expiry': parts[1]})
                        except:
                            pass
        return expired
def remove_expired_user(user_id):
    with _LOCK:
        if not os.path.exists(PREMIUM_FILE):
            return
        lines = []
        with open(PREMIUM_FILE) as f:
            lines = [l.strip() for l in f if l.strip()]
        lines = [l for l in lines if not l.startswith(str(user_id) + '|')]
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                f.write(l + '\n')
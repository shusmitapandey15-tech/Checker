from telethon import Button
def green_btn(text, data, icon=None):
    return Button.inline(text, data, icon=icon)
def red_btn(text, data, icon=None):
    return Button.inline(text, data, icon=icon, style="danger")
def primary_btn(text, data, icon=None):
    return Button.inline(text, data, icon=icon, style="primary")
def url_btn(text, url):
    return Button.url(text, url)
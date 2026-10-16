"""Discord とのやりとり係（発言を読む・返事する・DMを送る）。

ボットを24時間動かす代わりに、5分おきに Discord の公式API（REST）でチャンネルを見に行く「見回り方式」。
トークンは環境変数から受け取り、画面やログには出さない。
"""
import time

import requests

API = "https://discord.com/api/v10"
MAX_LEN = 1900


class DiscordError(Exception):
    pass


class Discord:
    def __init__(self, token, dry_run=False):
        if not token:
            raise DiscordError("DISCORD_BOT_TOKEN（ボットのトークン）が設定されていません")
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://github.com/duema-yoyaku-watch, 1.0)",
        })
        self.dm_channels = {}
        self.me = None

    def _req(self, method, path, **kw):
        for _ in range(5):
            try:
                res = self.session.request(method, API + path, timeout=20, **kw)
            except requests.RequestException as e:
                raise DiscordError(f"Discord に接続できませんでした（{type(e).__name__}）") from e
            if res.status_code == 429:  # 送りすぎ → 指定された秒数だけ待つ
                time.sleep(float(res.json().get("retry_after", 1)) + 0.5)
                continue
            if res.status_code == 401:
                raise DiscordError("ボットのトークンが正しくありません（DISCORD_BOT_TOKEN を確認）")
            if res.status_code >= 400:
                raise DiscordError(f"Discord への{_what(method, path)}に失敗しました"
                                   f"（HTTP {res.status_code}・{_code(res)}）{_hint(res)}")
            return res.json() if res.content else None
        raise DiscordError("Discord が混み合っていて送れませんでした")

    def bot_user_id(self):
        if self.me is None:
            self.me = self._req("GET", "/users/@me")["id"]
        return self.me

    def messages_after(self, channel_id, after):
        """after より後の発言を、古い順にすべて返す（after が無い時は直近50件）。"""
        params = {"limit": 100}
        if after:
            params["after"] = after
            found = []
            while True:
                batch = self._req("GET", f"/channels/{channel_id}/messages", params=params)
                if not batch:
                    break
                batch.sort(key=lambda m: int(m["id"]))
                found += batch
                if len(batch) < 100:
                    break
                params["after"] = batch[-1]["id"]
            return found
        params["limit"] = 50
        batch = self._req("GET", f"/channels/{channel_id}/messages", params=params)
        return sorted(batch, key=lambda m: int(m["id"]))

    def send(self, channel_id, content, reply_to=None):
        """チャンネルに書き込み、最後に書き込んだ発言のIDを返す。"""
        last = None
        for part in _split(content):
            if self.dry_run:
                print(f"[Discord・送信しません] #{channel_id}: {part}")
                continue
            body = {"content": part, "allowed_mentions": {"parse": ["users"]}}
            if reply_to:
                body["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
                reply_to = None
            last = self._req("POST", f"/channels/{channel_id}/messages", json=body)["id"]
        return last

    def dm(self, user_id, content):
        """個人メッセージを送る。相手がDMを受け付けていない時は False を返す。"""
        if self.dry_run:
            print(f"[DM・送信しません] {user_id}: {content}")
            return True
        try:
            if user_id not in self.dm_channels:
                ch = self._req("POST", "/users/@me/channels", json={"recipient_id": user_id})
                self.dm_channels[user_id] = ch["id"]
            for part in _split(content):
                self._req("POST", f"/channels/{self.dm_channels[user_id]}/messages",
                          json={"content": part, "allowed_mentions": {"parse": []}})
            return True
        except DiscordError as e:
            if "50007" in str(e) or "403" in str(e):
                return False
            raise


def _what(method, path):
    if path.startswith("/users/@me/channels"):
        return "DMの準備（OWNER_DISCORD_ID 宛て）"
    if path.startswith("/channels/") and method == "POST":
        return "書き込み（SINGLE_CHANNEL_ID または DM）"
    if path.startswith("/channels/"):
        return "チャンネルの読み取り（SINGLE_CHANNEL_ID）"
    return f"{method} {path}"


def _hint(res):
    code = None
    try:
        code = res.json().get("code")
    except ValueError:
        pass
    hints = {
        0: " → IDの形がおかしい可能性。Secrets に数字だけが入っているか確認してください",
        10003: " → チャンネルが見つかりません。SINGLE_CHANNEL_ID を確認してください",
        10013: " → ユーザーが見つかりません。OWNER_DISCORD_ID を確認してください",
        50001: " → ボットにそのチャンネルを見る権限がありません",
        50013: " → ボットに書き込む権限がありません",
        50035: " → IDの形が正しくありません（数字だけか確認）",
    }
    return hints.get(code, "")


def _code(res):
    try:
        return f"code {res.json().get('code')}"
    except ValueError:
        return "詳細不明"


def _split(content):
    parts, buf = [], ""
    for line in content.split("\n"):
        if len(buf) + len(line) + 1 > MAX_LEN:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        parts.append(buf)
    return parts

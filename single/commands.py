"""Discord のコマンド（!登録 など）を処理する係。"""
import re
import unicodedata
from datetime import date, timedelta

import state
import watchlist as wl

HELP = """\
📖 **シングル通知の使い方**
`!登録 カード名` … カードを登録（{days}日後に自動で削除。1人{limit}枚まで）
`!解除 カード名` … 登録を消す（`!解除 全部` で全部消す）
`!一覧` … 自分の登録カードをDMで確認
`!延長 カード名` … 期限を{days}日延ばす（`!延長 全部` も可）
`!検索 カード名` … 2店の値段と在庫を調べる
`!停止` / `!再開` … 自分への通知を止める・再開する
※返事まで5〜15分かかります。カード名は一部だけでもOK（例: `ボルメテウス`）
"""
OWNER_HELP = """\
👑 **オーナー用**
`!全体停止` / `!全体再開` … 全員の通知を止める・再開する
`!タイマー 2026-11-15 2` … 指定日から2日間だけ通知する（`!タイマー 解除` で取り消し）
"""


def parse(content):
    """「!登録 ボルメテウス」→ ("登録", "ボルメテウス")。コマンドでなければ None。"""
    text = unicodedata.normalize("NFKC", content or "").strip()
    if not text.startswith("!"):
        return None
    cmd, _, arg = text[1:].partition(" ")
    return cmd.strip(), arg.strip()


class Handler:
    def __init__(self, data, settings, owner_id, searcher):
        self.data = data
        self.settings = settings
        self.limits = settings["limits"]
        self.owner_id = owner_id
        self.searcher = searcher

    def handle(self, msg):
        """1つの発言を処理し、(チャンネルへの返事, DMで送る内容) を返す。"""
        parsed = parse(msg.get("content"))
        if not parsed:
            return None, None
        cmd, arg = parsed
        uid = msg["author"]["id"]
        name = msg["author"].get("global_name") or msg["author"].get("username", "")
        func = {
            "ヘルプ": self.help, "help": self.help,
            "登録": self.register, "解除": self.unregister, "一覧": self.listing,
            "延長": self.extend, "検索": self.search,
            "停止": self.pause, "再開": self.resume,
            "全体停止": self.global_pause, "全体再開": self.global_resume, "タイマー": self.timer,
        }.get(cmd)
        if func is None:
            return f"「!{cmd}」というコマンドはありません。`!ヘルプ` で使い方を確認できます。", None
        return func(uid, name, arg)

    # ---------- 全員が使えるコマンド ----------

    def help(self, uid, name, arg):
        text = HELP.format(days=self.limits["expire_days"], limit=self.limits["cards_per_user"])
        if uid == self.owner_id:
            text += "\n" + OWNER_HELP
        return text, None

    def register(self, uid, name, arg):
        if not arg:
            return "カード名を書いてください（例: `!登録 ボルメテウス`）", None
        if len(arg) > 40:
            return "カード名が長すぎます（40文字まで）", None
        users = self.data["users"]
        if uid not in users and len(users) >= self.limits["max_users"]:
            return f"登録できるのは{self.limits['max_users']}人までです。ほかの人の登録が消えるまでお待ちください。", None
        rec = wl.user(self.data, uid, name)
        if wl.find_card(rec, arg):
            return f"「{arg}」はもう登録されています（`!延長 {arg}` で期限を延ばせます）", None
        if len(rec["cards"]) >= self.limits["cards_per_user"]:
            return f"登録は1人{self.limits['cards_per_user']}枚までです。`!解除 カード名` で空きを作ってください。", None
        rec["cards"].append({"name": arg, "added": state.iso(state.now()),
                             "expires": wl.expires_at(self.settings), "reminded": False})
        left = self.limits["cards_per_user"] - len(rec["cards"])
        return (f"✅ 「{arg}」を登録しました（{_md(rec['cards'][-1]['expires'])}まで・残り{left}枠）\n"
                f"入荷したらDMでお知らせします。"), None

    def unregister(self, uid, name, arg):
        rec = self.data["users"].get(uid)
        if not rec or not rec["cards"]:
            return "登録されているカードはありません。", None
        if arg == "全部":
            count = len(rec["cards"])
            del self.data["users"][uid]
            return f"🗑️ 登録していた{count}枚をすべて消しました。", None
        card = wl.find_card(rec, arg)
        if not card:
            return f"「{arg}」は登録されていません（`!一覧` で確認できます）", None
        rec["cards"].remove(card)
        if not rec["cards"]:
            del self.data["users"][uid]
        return f"🗑️ 「{card['name']}」の登録を消しました。", None

    def listing(self, uid, name, arg):
        rec = self.data["users"].get(uid)
        if not rec or not rec["cards"]:
            return "登録されているカードはありません。`!登録 カード名` で登録できます。", None
        lines = [f"📋 **あなたの登録カード（{len(rec['cards'])}/{self.limits['cards_per_user']}枚）**"]
        lines += [f"・{c['name']}（{_md(c['expires'])}まで）" for c in rec["cards"]]
        if rec.get("paused"):
            lines.append("※いまは通知を止めています（`!再開` で再開）")
        return "📩 登録カードをDMで送りました。", "\n".join(lines)

    def extend(self, uid, name, arg):
        rec = self.data["users"].get(uid)
        if not rec or not rec["cards"]:
            return "登録されているカードはありません。", None
        targets = rec["cards"] if arg == "全部" else [c for c in [wl.find_card(rec, arg)] if c]
        if not targets:
            return f"「{arg}」は登録されていません（`!一覧` で確認できます）", None
        for c in targets:
            c["expires"] = wl.expires_at(self.settings)
            c["reminded"] = False
        return f"⏰ {len(targets)}枚の期限を{_md(targets[0]['expires'])}まで延ばしました。", None

    def search(self, uid, name, arg):
        if not arg:
            return "カード名を書いてください（例: `!検索 ボルメテウス`）", None
        return self.searcher(arg), None

    def pause(self, uid, name, arg):
        rec = self.data["users"].get(uid)
        if not rec:
            return "登録されているカードがないので、通知は届きません。", None
        rec["paused"] = True
        return "🔕 あなたへの通知を止めました（`!再開` で再開）。登録はそのまま残ります。", None

    def resume(self, uid, name, arg):
        rec = self.data["users"].get(uid)
        if not rec:
            return "登録されているカードはありません。", None
        rec["paused"] = False
        return "🔔 あなたへの通知を再開しました。", None

    # ---------- オーナーだけが使えるコマンド ----------

    def _owner_only(self, uid):
        return None if uid == self.owner_id else "このコマンドはオーナーだけが使えます。"

    def global_pause(self, uid, name, arg):
        if (deny := self._owner_only(uid)):
            return deny, None
        self.data["global"]["paused"] = True
        return "🔕 全員へのシングル通知を止めました（`!全体再開` で再開）。", None

    def global_resume(self, uid, name, arg):
        if (deny := self._owner_only(uid)):
            return deny, None
        self.data["global"]["paused"] = False
        return "🔔 全員へのシングル通知を再開しました。", None

    def timer(self, uid, name, arg):
        if (deny := self._owner_only(uid)):
            return deny, None
        if arg in ("解除", "取消", "取り消し"):
            self.data["global"]["timer"] = None
            return "⏱️ タイマーを取り消しました（いつでも通知します）。", None
        if not arg:
            t = self.data["global"].get("timer")
            if not t:
                return "タイマーは設定されていません（いつでも通知します）。", None
            return f"⏱️ {t['start']} から {t['days']}日間だけ通知する設定です。", None
        m = re.fullmatch(r"(\d{4}-\d{1,2}-\d{1,2})\s+(\d{1,2})", arg)
        if not m:
            return "書き方: `!タイマー 2026-11-15 2`（11/15から2日間）", None
        try:
            start = date.fromisoformat("-".join(f"{int(x):02d}" if i else x
                                                for i, x in enumerate(m.group(1).split("-"))))
        except ValueError:
            return "日付が正しくありません（例: 2026-11-15）", None
        days = int(m.group(2))
        if not 1 <= days <= 30:
            return "日数は1〜30で指定してください。", None
        self.data["global"]["timer"] = {"start": start.isoformat(), "days": days}
        end = start + timedelta(days=days - 1)
        return f"⏱️ {start:%m/%d}〜{end:%m/%d} の{days}日間だけ通知します。", None


def _md(iso_text):
    return state.parse_iso(iso_text).strftime("%m/%d")

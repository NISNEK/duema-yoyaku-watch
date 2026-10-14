"""接続テスト：候補のショップに GitHub から見に行けるかを1回ずつ確かめる。

- 本番と同じく正直に名乗り、robots.txt を確認してからページを1回だけ取る
- サイトごとに数秒空ける
- 結果を表にして、Actions の実行画面（Summary）に表示する
"""
import os
import sys
import time
import urllib.robotparser
from urllib.parse import quote, urlsplit

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "monitor"))
from fetcher import user_agent  # noqa: E402

WAIT_SECONDS = 4
CHALLENGE_SIGNS = ["Just a moment", "アクセス確認", "cf-chl", "captcha", "/cheq/", "Access Denied"]
DM = quote("デュエル・マスターズ")

CANDIDATES = [
    # (区分, 名前, URL)
    ("予約", "ホビーサーチ", f"https://www.1999.co.jp/search?typ1_c=121&searchkey={DM}&spage=1&sortid=0"),
    ("予約", "フルアヘッド", "https://fullahead-dm.com/shopbrand/yoyaku/page1/new/"),
    ("予約", "イオンスタイルオンライン", f"https://aeonretail.com/Form/Product/ProductList.aspx?shop=0&swrd={DM}"),
    ("予約", "トイザらス", "https://www.toysrus.co.jp/ja-jp/duelmasters/"),
    ("予約", "エディオン", f"https://www.edion.com/item_list.html?keyword={DM}&d_num=90&d_sort=1&d_type=panel"),
    ("予約", "ジョーシン", "https://joshinweb.jp/"),
    ("予約", "ヨドバシ", "https://www.yodobashi.com/"),
    ("予約", "ビックカメラ", "https://www.biccamera.com/"),
    ("予約", "タカラトミーモール", "https://takaratomymall.jp/"),
    ("予約", "ハピネット・オンライン",
     f"https://www.happinetonline.com/ec/Facet?inputKeywordFacet={DM}&kclsf=AND&dnumber=60"),
    ("予約", "ドラゴンスター", "https://dorasuta.jp/"),
    ("予約", "マスターズスクウェア", "https://www.tcgacademy.com/product-list/2270"),
    ("予約", "カードラボ", "https://www.c-labo-online.jp/product-list/3378"),
    ("シングル", "トレキャット（本日の入荷品）",
     "https://torecat.shop/collections/" + quote("本日の入荷品") + "/products.json?limit=250"),
    ("シングル", "アメニティードリーム（新着）", "https://www.amenitydream.com/new"),
    ("シングル", "アメニティードリーム（検索）",
     "https://www.amenitydream.com/product-list?keyword=" + quote("ボルメテウス") + "&num=100"),
]


def get(url):
    return requests.get(url, headers={"User-Agent": user_agent(), "Accept-Language": "ja"}, timeout=20)


def check(url):
    parts = urlsplit(url)
    try:
        robots = get(f"{parts.scheme}://{parts.netloc}/robots.txt")
    except requests.RequestException as e:
        return "❌", f"接続できない（{type(e).__name__}）", "-"
    robots_note = f"robots {robots.status_code}"
    if robots.status_code == 200:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots.text.splitlines())
        if not rp.can_fetch(user_agent(), url):
            return "⛔", "robots.txt で禁止", robots_note
    elif robots.status_code >= 500:
        return "❌", f"robots.txt がサーバーエラー（{robots.status_code}）", robots_note
    time.sleep(WAIT_SECONDS)
    try:
        res = get(url)
    except requests.RequestException as e:
        return "❌", f"接続できない（{type(e).__name__}）", robots_note
    text = res.text[:200000]
    if res.status_code != 200:
        return "❌", f"拒否・エラー（HTTP {res.status_code}）", robots_note
    # 確認画面は小さいページなので、タイトルと「小さいページの本文」だけを調べる
    # （普通のページにも問い合わせフォーム用の captcha 部品が入っていることがあるため）
    title = text.split("<title", 1)[-1].split("</title>", 1)[0] if "<title" in text else ""
    body = text if len(res.content) < 60000 else ""
    sign = next((s for s in CHALLENGE_SIGNS if s in title or s in body or s in res.url), None)
    if sign:
        return "❌", f"ロボット確認画面（{sign}）", robots_note
    return "✅", f"OK（{len(res.content) // 1024}KB）", robots_note


def main():
    rows = []
    for kind, name, url in CANDIDATES:
        mark, result, robots_note = check(url)
        print(f"{mark} [{kind}] {name}: {result} / {robots_note}")
        rows.append(f"| {mark} | {kind} | {name} | {result} | {robots_note} |")
        time.sleep(WAIT_SECONDS)
    table = "\n".join(["| 結果 | 区分 | ショップ | 内容 | robots.txt |", "|---|---|---|---|---|", *rows])
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## GitHub からの接続テスト結果\n\n" + table + "\n")


if __name__ == "__main__":
    main()

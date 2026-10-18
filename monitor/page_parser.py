"""ページから商品を取り出し、受付状況を判定する係。

状態は次の3つ:
  before  … 受付前（ページはあるが、まだ買えない）
  open    … 受付中（予約・購入できる）
  soldout … 売り切れ・受付終了
"""
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class Item:
    id: str
    title: str
    url: str
    state: str
    image: str = ""    # 商品画像のURL（お店のサイトの画像をそのまま表示する。保存はしない）


class ParseError(Exception):
    """ページの作りが想定と違い、判定できない時のエラー。"""


def normalize(text):
    """全角・半角の違いや余分な空白をそろえて、比べやすくする。"""
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text, words):
    folded = normalize(text).casefold()
    return any(normalize(w).casefold() in folded for w in words)


def _matches(text, words, pattern):
    if _contains_any(text, words):
        return True
    return bool(pattern) and re.search(pattern, normalize(text)) is not None


def classify(text, rules):
    is_open = _matches(text, rules.get("open_keywords", []), rules.get("open_pattern"))
    is_soldout = _matches(text, rules.get("soldout_keywords", []), rules.get("soldout_pattern"))
    if is_open and is_soldout:
        # 両方の言葉がある時（例:「予約品 在庫なし」）は、soldout_first の設定で決める
        return "soldout" if rules.get("soldout_first") else "open"
    if is_open:
        return "open"
    if is_soldout:
        return "soldout"
    return "before"


def is_excluded(title, target):
    return _contains_any(title, target.get("exclude_keywords", []))


def is_target(title, target, check_keywords=True):
    if check_keywords and not _contains_any(title, target.get("keywords", [])):
        return False
    return not is_excluded(title, target)


def _text(element, selector):
    if not selector:
        return element.get_text(" ", strip=True)
    found = element.select(selector)
    return " ".join(e.get_text(" ", strip=True) for e in found)


def image_url(block, selector, page_url):
    """商品の枠から画像のURLを取り出す（遅れて読み込む作りの店は、大きい画像の方を使う）。"""
    if not selector:
        return ""
    img = block.select_one(selector)
    if img is None:
        return ""
    for attr in ("data-x2", "data-src", "data-original", "src"):
        src = img.get(attr)
        if src and "spacer" not in src:
            return urljoin(page_url, src)
    return ""


def parse_list(html, page_url, rules, target):
    """一覧ページから対象の商品をすべて取り出す。"""
    soup = BeautifulSoup(html, "lxml")
    blocks = soup.select(rules["item"])
    if not blocks:
        raise ParseError("商品が1つも見つかりません（ページの作りが変わった可能性）")

    items = {}
    for block in blocks:
        title = normalize(_text(block, rules.get("title")))
        link = block.select_one(rules.get("link") or "a")
        if not title or link is None or not link.get("href"):
            continue
        # all_items: true のページでも、対象外の言葉（exclude_keywords）は除く
        if not is_target(title, target, check_keywords=not rules.get("all_items")):
            continue
        url = urljoin(page_url, link["href"])
        match = re.search(rules["id_regex"], url) if rules.get("id_regex") else None
        item_id = match.group(1) if match else url
        if match and rules.get("link_template"):
            # 一覧ページのリンクにおまけの文字が付いていて直接開けない店は、商品番号から正しいURLを作る
            url = rules["link_template"].format(id=item_id)
        state = classify(_text(block, rules.get("status")), rules)
        items[item_id] = Item(item_id, title, url, state, image_url(block, rules.get("image"), page_url))
    return list(items.values())


def parse_product(html, page_url, rules, product_name):
    """商品ページ1つを判定する（mode: product 用）。"""
    soup = BeautifulSoup(html, "lxml")
    selector = rules.get("selector")
    area = soup.select_one(selector) if selector else soup.body
    if area is None:
        raise ParseError("判定する範囲が見つかりません（ページの作りが変わった可能性）")
    state = classify(area.get_text(" ", strip=True), rules)
    return [Item("page", product_name, page_url, state)]

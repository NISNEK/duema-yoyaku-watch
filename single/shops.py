"""トレキャット・アメニティードリームから商品を読み取る係。"""
from dataclasses import dataclass
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

import common


@dataclass
class Product:
    shop: str          # torecat / amenity
    id: str
    title: str
    url: str
    price: str         # 表示用（例: "1,980円"）
    available: bool    # 買えるか
    stock: str = ""    # 表示用（例: "在庫数 3枚"）
    image: str = ""    # 商品画像のURL（お店の画像をそのまま表示する。保存はしない）


def _https(src):
    return ("https:" + src) if src and src.startswith("//") else (src or "")


def _shopify_image(p):
    images = p.get("images") or []
    return _https(images[0].get("src", "")) if images and isinstance(images[0], dict) else ""


def _yen(value):
    try:
        return f"{int(float(value)):,}円"
    except (TypeError, ValueError):
        return ""


# ---------------- トレキャット（お店が公式に出している商品データ JSON を使う） ----------------

def torecat_arrivals(http, cfg):
    """「本日の入荷品」のうち、デュエマのシングルだけを返す（1回のアクセスで全部取れる）。

    オリパ・福袋・スリーブなども混ざるので、お店が付けている「DMシングル全て」の目印で絞る。
    """
    data = http.get(cfg["arrivals"]).json()
    tag = cfg.get("single_tag", "DMシングル全て")
    return [_torecat_product(p, cfg) for p in data.get("products", []) if tag in (p.get("tags") or [])]


def _torecat_product(p, cfg):
    variants = p.get("variants") or [{}]
    available = any(v.get("available") for v in variants)
    return Product("torecat", str(p["id"]), p.get("title", ""), cfg["product"].format(handle=p["handle"]),
                   _yen(variants[0].get("price")), available, "在庫あり" if available else "売り切れ",
                   _shopify_image(p))


def torecat_catalog_page(http, cfg, page):
    """値段検索用に「デュエマシングル全て」の1ページ分（最大250件）を返す。"""
    data = http.get(cfg["catalog"].format(page=page)).json()
    items = []
    for p in data.get("products", []):
        variants = p.get("variants") or [{}]
        items.append({"id": str(p["id"]), "title": p.get("title", ""), "handle": p["handle"],
                      "price": _yen(variants[0].get("price")),
                      "available": any(v.get("available") for v in variants),
                      "image": _shopify_image(p)})
    return items


def torecat_live(http, cfg, item):
    """1つの商品の今の値段と在庫を確かめる。"""
    p = http.get(cfg["product"].format(handle=item["handle"]) + ".js").json()
    available = bool(p.get("available"))
    return Product("torecat", item["id"], p.get("title", item["title"]),
                   cfg["product"].format(handle=item["handle"]),
                   _yen((p.get("price") or 0) / 100), available, "在庫あり" if available else "売り切れ",
                   _https(p.get("featured_image")) or item.get("image", ""))


# ---------------- アメニティードリーム（ページを読む） ----------------

def amenity_new(http, cfg):
    """「新着」ページの1ページ目にあるデュエマのシングルを返す。"""
    res = http.get(cfg["new"])
    return _amenity_list(res.text, res.url, cfg)


def amenity_search(http, cfg, keyword):
    res = http.get(cfg["search"].format(keyword=quote(keyword)))
    return _amenity_list(res.text, res.url, cfg)


def _amenity_list(html, page_url, cfg):
    soup = BeautifulSoup(html, "lxml")
    products = []
    for cell in soup.select("li.list_item_cell"):
        model = cell.select_one(".model_number_value")
        if model is None or not model.get_text(strip=True).startswith(cfg.get("model_prefix", "")):
            continue
        link = cell.select_one("a.item_data_link")
        name = cell.select_one(".goods_name")
        if link is None or name is None:
            continue
        stock_el = cell.select_one("p.stock")
        stock = stock_el.get_text(" ", strip=True) if stock_el else ""
        soldout = (stock_el is not None and "soldout" in stock_el.get("class", [])) or "在庫なし" in stock
        price_el = cell.select_one(".selling_price .figure")
        img = cell.select_one(".global_photo img")
        image = ""
        if img is not None:
            image = urljoin(page_url, img.get("data-x2") or img.get("src") or "")
        url = urljoin(page_url, link["href"])
        item_id = cell.select_one(".item_data").get("data-product-id") if cell.select_one(".item_data") else url
        products.append(Product("amenity", str(item_id), name.get_text(" ", strip=True), url,
                                price_el.get_text(strip=True) if price_el else "",
                                bool(stock) and not soldout, stock or "表示なし", image))
    return products

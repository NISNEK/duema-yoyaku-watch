// お知らせ欄に、予約ページの【予約】商品を自動で並べる（予約・シングル・相場の3ページ共通）
// - 再販ではない予約が受付中なら「予約開始」を太字で一番上に（再販は「再販開始」）
// - どのお店でも売り切れなら、先頭に「予約一杯」
// - カートンは入れない。同じ商品（弾の番号が同じ）はお店をまとめて1行に
// - 押すと予約のページの、その商品の場所へ移動する
// 古い弾（去年以前の番号）は、受付中のものだけ残す
(function () {
  const list = document.querySelector(".news ul");
  if (!list) return;

  const style = document.createElement("style");
  style.textContent = `
    .news li.auto a { color: inherit; text-decoration: none; }
    .news li.auto a:hover { text-decoration: underline; }
    .news .start { color: var(--good, var(--open, #0f8a4a)); font-weight: 800; }
    .news .full { color: var(--down, var(--error, #d23c3c)); font-weight: 800; }
    .news .soon { color: var(--accent, #1f6feb); font-weight: 700; }
    .news .nshops { color: var(--sub); font-size: .78rem; }
    .news .nshops a { text-decoration: underline; }`;
  document.head.append(style);

  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const day = (iso) => { const d = new Date(iso); return (d.getMonth() + 1) + "/" + d.getDate(); };
  const CODE = /DM(\d{2})-[A-Z]+\d+[A-Z]?/i;

  // 「【予約】[新品]デュエル・マスターズTCG ○○【DM26-BD1】 [2611/21]」→「DM26-BD1 ○○」
  function shortName(title, code) {
    let t = title
      .replace(/[【\[〔][^】\]〕]*[】\]〕]/g, " ")
      .replace(/[(（][^)）]*[)）]/g, " ")
      .replace(/デュエル・?マスターズ\s*(TCG)?/g, " ")
      .replace(new RegExp(code, "gi"), " ")
      .replace(/\d{1,2}\/\d{1,2}\s*(発売予定|発売|出荷予定)?|\d{1,2}月\d{1,2}日\S*/g, " ")
      .replace(/\d*BOX\S*|おひとりさま\S*/gi, " ")
      .replace(/\s+/g, " ").trim();
    return (code.toUpperCase() + " " + t).trim();
  }

  fetch("status.json?t=" + Date.now())
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || !data.shops) return;
      const yy = new Date().getFullYear() % 100;
      const groups = new Map();
      for (const [shopKey, shop] of Object.entries(data.shops)) {
        if (shop.enabled === false) continue;
        for (const [id, item] of Object.entries(shop.items || {})) {
          const title = item.title || "";
          if (!title.includes("【予約】") || title.includes("カートン")) continue;
          const m = title.match(CODE);
          if (!m) continue;
          if (Number(m[1]) < yy && item.state !== "open") continue;   // 古い弾は受付中のものだけ
          const resale = /再販/.test(title);
          const key = m[0].toUpperCase() + (resale ? "|再販" : "");
          if (!groups.has(key)) groups.set(key, { code: m[0], resale, items: [] });
          groups.get(key).items.push({ shopKey, id, shopName: shop.name || shopKey, ...item });
        }
      }
      const rows = [...groups.values()].map(g => {
        const states = g.items.map(i => i.state);
        const state = states.includes("open") ? "open" : states.includes("before") ? "before" : "soldout";
        const changed = g.items.map(i => i.changed_at || i.first_seen || "").sort().pop();
        const name = g.items.map(i => shortName(i.title, g.code)).sort((a, b) => a.length - b.length)[0];
        const rank = state === "open" ? (g.resale ? 1 : 0) : state === "before" ? 2 : 3;
        return { ...g, state, changed, name, rank };
      }).sort((a, b) => a.rank - b.rank || b.changed.localeCompare(a.changed));

      const target = (i) => "index.html#i-" + encodeURIComponent(i.shopKey + "-" + i.id);
      const frag = document.createDocumentFragment();
      for (const g of rows) {
        const li = el("li", { class: "auto" });
        const first = g.items.find(i => i.state === g.state) || g.items[0];
        const a = el("a", { href: target(first) });
        if (g.state === "open" && !g.resale) a.append(el("span", { class: "start" }, "予約開始"), " ");
        if (g.state === "open" && g.resale) a.append(el("span", { class: "soon" }, "再販開始"), " ");
        if (g.state === "before") a.append(el("span", { class: "soon" }, "予約開始前"), " ");
        if (g.state === "soldout") a.append(el("span", { class: "full" }, "予約一杯"), " ");
        a.append(day(g.changed) + " " + g.name + (g.resale && g.state !== "open" ? "（再販）" : ""));
        li.append(a, " ");
        const shops = el("span", { class: "nshops" }, "（");
        g.items.forEach((i, n) => {
          if (n) shops.append("・");
          shops.append(el("a", { href: target(i) }, i.shopName + (i.state === "soldout" && g.state !== "soldout" ? "：売り切れ" : "")));
        });
        shops.append("）");
        li.append(shops);
        frag.append(li);
      }
      list.prepend(frag);
    })
    .catch(() => {});
})();

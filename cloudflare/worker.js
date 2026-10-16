/**
 * Discord スラッシュコマンドの受付係（Cloudflare Workers に置くプログラム）
 *
 * やること（3つだけ）
 *   1. 本物の Discord からの呼び出しか、電子署名で確かめる（偽物は 401 で断る）
 *   2. 3秒以内に「⏳ 受け付けました」と返す（本人にだけ見える表示）
 *   3. GitHub の「シングル即答」を起動して、実際の処理（登録・検索・保存）を任せる
 *
 * 登録リストなどのデータはここには置かない（GitHub に暗号化して保存したまま）。
 *
 * Cloudflare の「設定 → 変数とシークレット」に入れるもの
 *   DISCORD_PUBLIC_KEY … Discord 開発者ページの「PUBLIC KEY」（テキスト）
 *   GITHUB_REPO        … 例: yourname/duema-yoyaku-watch（テキスト）
 *   GITHUB_TOKEN       … GitHub の専用トークン（シークレット）
 *   ALLOWED_GUILD_ID   … 自分の Discord サーバーのID（テキスト。ほかのサーバーからの呼び出しを断る）
 *   PAYLOAD_KEY        … 依頼の中身を暗号化する鍵（シークレット。GitHub の Secrets にも同じものを入れる）
 *
 * GitHub は公開リポジトリなので、実行の記録（ログ）は誰でも見られる。
 * 「誰が何を登録したか」がログに残らないよう、GitHub に渡す依頼の中身は暗号化する。
 */

const WORKFLOW_FILE = "single-command.yml";
const EPHEMERAL = 64; // 本人にだけ見える表示

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("duema-bot は動いています。", { status: 200 });
    }
    const body = await request.text();
    if (!(await verify(request, body, env.DISCORD_PUBLIC_KEY))) {
      return new Response("署名が正しくありません", { status: 401 });
    }
    const interaction = JSON.parse(body);

    // Discord からの接続確認（PING）
    if (interaction.type === 1) {
      return json({ type: 1 });
    }

    // スラッシュコマンド
    if (interaction.type === 2) {
      if (env.ALLOWED_GUILD_ID && interaction.guild_id !== env.ALLOWED_GUILD_ID) {
        return reply("このサーバーでは使えません。");
      }
      const user = interaction.member?.user || interaction.user || {};
      const options = {};
      for (const o of interaction.data.options || []) options[o.name] = o.value;
      const payload = {
        command: interaction.data.name,
        options,
        user: { id: user.id, name: user.global_name || user.username || "" },
        application_id: interaction.application_id,
        token: interaction.token,
      };
      const ok = await dispatch(env, payload);
      if (!ok) {
        return reply("⚠️ 受付に失敗しました。少し待ってから試すか、`!` で始まるコマンドを使ってください。");
      }
      // 「考え中…」の表示を出しておき、GitHub の処理が終わったら結果に書き換える
      return json({ type: 5, data: { flags: EPHEMERAL } });
    }

    return reply("このボタン・操作には対応していません。");
  },
};

async function dispatch(env, payload) {
  const res = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "duema-bot-worker",
      },
      body: JSON.stringify({ ref: "main", inputs: { payload: await encrypt(env.PAYLOAD_KEY, JSON.stringify(payload)) } }),
    },
  );
  return res.status === 204;
}

// AES-GCM で暗号化し「12バイトの乱数 + 暗号文」を URL で使える Base64 にする
async function encrypt(keyText, plain) {
  const raw = Uint8Array.from(atob(keyText.trim().replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plain)));
  const all = new Uint8Array(iv.length + sealed.length);
  all.set(iv);
  all.set(sealed, iv.length);
  return btoa(String.fromCharCode(...all)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function verify(request, body, publicKeyHex) {
  const signature = request.headers.get("X-Signature-Ed25519");
  const timestamp = request.headers.get("X-Signature-Timestamp");
  if (!signature || !timestamp || !publicKeyHex) return false;
  try {
    const key = await crypto.subtle.importKey("raw", hex(publicKeyHex), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify("Ed25519", key, hex(signature), new TextEncoder().encode(timestamp + body));
  } catch {
    return false;
  }
}

function hex(text) {
  const bytes = new Uint8Array(text.length / 2);
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(text.substr(i * 2, 2), 16);
  return bytes;
}

function json(obj) {
  return new Response(JSON.stringify(obj), { headers: { "Content-Type": "application/json" } });
}

function reply(content) {
  return json({ type: 4, data: { content, flags: EPHEMERAL } });
}

# 設定手順書

GitHub アカウントをお持ちの状態から、**スマホにテスト通知が届くまで**の手順です。
上から順番に進めてください。所要時間は30〜45分ほどです。

**用意するもの**
- iPhone
- パソコン（Windows）と、ブラウザ（Chrome または Edge）
- GitHub アカウント
- このフォルダ一式（`購入自動通知github`）

**目次**
1. [合言葉（トピック名）を作る](#1-合言葉トピック名を作る)
2. [iPhone に ntfy を入れる](#2-iphone-に-ntfy-を入れる)
3. [Discord の通知先を作る（任意）](#3-discord-の通知先を作る任意)
4. [GitHub にリポジトリを作る](#4-github-にリポジトリを作る)
5. [ファイルをアップロードする](#5-ファイルをアップロードする)
6. [秘密情報を GitHub Secrets に入れる](#6-秘密情報を-github-secrets-に入れる)
7. [テスト通知を送る](#7-テスト通知を送る)
8. [見張りを始める](#8-見張りを始める)
9. [一覧ページを公開する](#9-一覧ページを公開する)
- [運用編（設定の変え方）](#運用編設定の変え方)
- [困ったとき](#困ったとき)
- [秘密情報が漏れたとき](#秘密情報が漏れたとき)

---

## 1. 合言葉（トピック名）を作る

ntfy は「**トピック名**」という合言葉を知っている人に通知を届けます。他人に推測されないよう、**長いランダムな文字列**を作ります。

1. キーボードの **Windowsキー** を押し、`powershell` と入力して **Windows PowerShell** を開きます。
2. 次の1行をコピーして貼り付け、**Enter** を押します。
   ```powershell
   [guid]::NewGuid().ToString("N")
   ```
3. `3f9a0c7e5b2d4e1fa8c6...` のような**32文字の英数字**が表示されます。これがあなたのトピック名です。
4. メモ帳などに一時的に控えてください。

> ⚠️ このトピック名は**誰にも教えないでください**。チャット（AIとの会話を含む）、SNS、スクリーンショットにも載せないでください。知られると、他人があなたのスマホに通知を送れてしまいます。

## 2. iPhone に ntfy を入れる

1. iPhone で **App Store** を開き、`ntfy` で検索して **ntfy**（アイコンは緑の吹き出し）を入れます。
2. ntfy を開き、通知の許可を聞かれたら **「許可」** を押します。
3. 右上（または下）の **「＋」** を押します。
4. **Topic name** の欄に、手順1で作ったトピック名を入力します（メモから貼り付けると確実です）。
5. **Use another server** はオフのままにし、**Subscribe**（購読）を押します。
6. 一覧にトピック名が表示されたら完了です。

> 💡 通知を見逃さないために：iPhone の **設定 → 通知 → ntfy** で「通知を許可」がオン、「即時通知」があればオンにしておきましょう。

## 3. Discord の通知先を作る（任意）

Discord にも通知が欲しい場合だけ行ってください。不要なら手順4へ進みます。

1. Discord（パソコン版かブラウザ版）を開きます。
2. 左端の **「＋」（サーバーを追加）** → **オリジナルの作成** → **自分と友達のため** を押し、サーバー名（例：`デュエマ通知`）を入れて **新規作成** を押します。
3. 通知を流したいチャンネル（例：`#一般`）の横の **歯車マーク（チャンネルの編集）** を押します。
4. 左メニューの **連携サービス** → **ウェブフックを作成**（または **新しいウェブフック**）を押します。
5. 作られたウェブフックを開き、**ウェブフックURLをコピー** を押します。
6. コピーした URL（`https://discord.com/api/webhooks/...`）をメモ帳に控えます。

> ⚠️ この URL も**秘密情報**です。知られると誰でもそのチャンネルに投稿できてしまいます。誰にも教えないでください。

## 4. GitHub にリポジトリを作る

**リポジトリ**＝GitHub 上のプロジェクト置き場です。

1. ブラウザで <https://github.com> を開き、ログインします。
2. 右上の **「＋」** → **New repository** を押します。
3. 次のように入力します。
   | 項目 | 入力・選択 |
   |---|---|
   | Repository name | `duema-yoyaku-watch`（好きな名前でOK。英数字とハイフン） |
   | Description | 空欄でOK |
   | 公開設定 | **Public** を選ぶ（無料で動かすために必要） |
   | Add a README file | **チェックしない** |
4. 下の **Create repository** を押します。

## 5. ファイルをアップロードする

1. 作ったリポジトリの画面で、**uploading an existing file** という青い文字を押します。
2. パソコンでエクスプローラーを開き、`購入自動通知github` フォルダを開きます。
3. フォルダの中身を**すべて選択**（`Ctrl` + `A`）し、ブラウザの **「Drag files here」** の枠にドラッグします。
   次のものが入っていればOKです。
   ```
   .github（フォルダ）   docs（フォルダ）   monitor（フォルダ）
   .gitignore   README.md   SETUP.md   requirements.txt   shops.yml
   ```
4. 一番下の **Commit changes** を押します。
5. リポジトリの画面に戻り、上の一覧に `.github` フォルダがあることを確認します。

> ❓ `.github` フォルダが一覧に無い場合：リポジトリ画面の **Add file → Create new file** を押し、ファイル名の欄に `.github/workflows/monitor.yml` と入力します。パソコンの `.github\workflows\monitor.yml` をメモ帳で開いて中身を全部コピーし、貼り付けて **Commit changes** を押してください。

## 6. 秘密情報を GitHub Secrets に入れる

**GitHub Secrets**＝鍵付きの金庫です。ここに入れたものは、あなたにも後から見えません（上書きはできます）。

1. リポジトリ画面の上にある **Settings**（歯車マーク）を押します。
2. 左メニューの **Secrets and variables** → **Actions** を押します。
3. **New repository secret** を押し、次のとおり入力して **Add secret** を押します。
   | Name（名前） | Secret（中身） |
   |---|---|
   | `NTFY_TOPIC` | 手順1で作ったトピック名 |
4. Discord も使う場合は、もう一度 **New repository secret** を押して追加します。
   | Name（名前） | Secret（中身） |
   |---|---|
   | `DISCORD_WEBHOOK_URL` | 手順3でコピーしたURL |
5. 入れ終わったら、メモ帳に控えたトピック名と URL は**削除**してかまいません（ntfy アプリにはトピック名が残っています）。

> ⚠️ Name は**大文字・アンダーバーまで正確に**入力してください。1文字でも違うと通知が届きません。

## 7. テスト通知を送る

1. リポジトリ画面の上にある **Actions** を押します。
2. 左の一覧から **予約ページ監視** を押します。
3. 右側の **Run workflow** ボタンを押します。
4. 「実行モード」で **test-notify** を選び、緑の **Run workflow** を押します。
5. 1分ほど待つと、一覧に実行が表示されます。**緑のチェック ✅** になれば成功です。
6. **iPhone に「✅ テスト通知」が届けば完了です！** 🎉
   （Discord を設定した場合は、Discord にも届きます）

> ❌ 赤いバツになった・通知が来ない場合は、[困ったとき](#困ったとき) を見てください。

## 8. 見張りを始める

1. もう一度 **Actions → 予約ページ監視 → Run workflow** を押します。
2. 今度は「実行モード」を **normal** のまま、緑の **Run workflow** を押します。
3. 緑のチェックになったら、実行名を押して中身を開き、**見張る** の行を押します。次のように各ショップの件数が表示されていれば成功です。
   ```
   - 駿河屋: 商品 24 件（受付中 24 / 受付前 0 / 売り切れ 0）、通知 0 件
   ```
   初回は「すでにある商品を覚えるだけ」なので、通知は届きません（これで正常です）。
4. 以後は**自動で約5分おき**に動きます。何もしなくてOKです。

## 9. 一覧ページを公開する

1. リポジトリの **Settings** → 左メニューの **Pages** を押します。
2. **Build and deployment** の **Source** で **Deploy from a branch** を選びます。
3. **Branch** で `main` と `/docs` を選び、**Save** を押します。
4. 1〜2分待ってページを再読み込みすると、上に `https://（あなたのユーザー名）.github.io/duema-yoyaku-watch/` のようなアドレスが表示されます。
5. そのアドレスをスマホで開き、**共有ボタン → ホーム画面に追加** しておくと便利です。

**これで設定はすべて完了です。お疲れさまでした！**

---

## 運用編（設定の変え方）

設定の変更は、すべて GitHub のサイト上でできます。

### shops.yml の書き換え方（共通）
1. リポジトリ画面で `shops.yml` を押します。
2. 右上の **鉛筆マーク（Edit this file）** を押します。
3. 書き換えます（下の例を参照）。
4. 右上の **Commit changes...** → もう一度 **Commit changes** を押します。
5. 念のため **Actions → 予約ページ監視 → Run workflow → dry-run** で確認すると安心です。

> ⚠️ 行の先頭のスペース（字下げ）は意味を持ちます。**スペースの数を変えない**ように注意してください。タブは使えません。

### 再販通知をオン・オフする
```yaml
  include_restock: true    # 再販も通知する
  include_restock: false   # 再販は通知しない
```

### ショップを一時的に休ませる
休ませたいショップの `enabled` を書き換えます。
```yaml
    enabled: false   # 休む（true に戻すと再開）
```

### 対象外にしたい言葉を決める
例：中古品の通知が要らない場合
```yaml
  exclude_keywords: ["中古"]
```

### ショップを追加したい
ショップごとにページの作りが違うため、追加には調べる作業が必要です。運用部にご相談ください。
（規約で禁止されているショップや、ロボット確認画面が出るショップは追加できません）

---

## 困ったとき

| 症状 | 確認すること |
|---|---|
| テスト通知が届かない | ① Secrets の Name が `NTFY_TOPIC` と正確か ② ntfy アプリのトピック名と Secrets の中身が同じか ③ iPhone の設定で ntfy の通知が許可されているか |
| Actions に「予約ページ監視」が無い | `.github/workflows/monitor.yml` がアップロードされているか（手順5の❓を参照） |
| 「⚠️ 監視に失敗しています」が届いた | 一覧ページで赤字のエラー内容を確認。ショップの一時的な不調なら自然に直ります。数日続く場合は運用部へ |
| 「⚠️ 見張りプログラムが止まっています」が届いた | 直前に `shops.yml` を書き換えていないか確認。字下げのずれが多い原因です。**History** から前の状態に戻せます |
| 一覧ページが「まだデータがありません」のまま | 手順8を実行したか確認。実行後、1〜2分待って再読み込み |
| 5分おきに動いていない | GitHub の混雑で遅れることがあります。1時間以上動かない場合は Actions 画面に止まった旨の表示が無いか確認 |

## 秘密情報が漏れたとき

トピック名や Webhook URL を誤って人に見せてしまった場合は、**新しいものに取り替えれば**大丈夫です。

**ntfy のトピック名**
1. 手順1と同じ方法で、新しいトピック名を作ります。
2. GitHub の **Settings → Secrets and variables → Actions** で `NTFY_TOPIC` の右の **鉛筆マーク** を押し、新しいトピック名で上書きして **Update secret** を押します。
3. ntfy アプリで古いトピックを**左にスワイプして削除**し、手順2と同じ方法で新しいトピックを購読します。
4. 手順7でテスト通知が届くことを確認します。

**Discord の Webhook URL**
1. Discord のチャンネル設定 → **連携サービス** → **ウェブフック** で、古いウェブフックを開いて **ウェブフックを削除** します。
2. 手順3と同じ方法で新しいウェブフックを作り、URL をコピーします。
3. GitHub の Secrets で `DISCORD_WEBHOOK_URL` を新しい URL で上書きします。
4. 手順7でテスト通知が届くことを確認します。

---

# シングル通知編

予約確認と同じリポジトリに、シングル通知（トレキャット・アメニティードリーム）を追加する手順です。
Discord の準備（`# シングル通知` チャンネル・ボットの作成と招待・チャンネルIDと自分のIDのコピー）が終わっている前提です。

## S1. 暗号化の鍵を作る
登録リスト（誰がどのカードを登録したか）を、鍵がないと読めない形で保存するための鍵です。

1. **Windows PowerShell** を開きます（Windowsキー → `powershell` と入力）。
2. 次の1行を貼り付けて **Enter** を押します。
   ```powershell
   $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_')
   ```
3. 表示された**44文字**の文字列（最後が `=`）をメモ帳に控えます。

> ⚠️ この鍵は誰にも教えないでください。**なくすと登録リストが読めなくなります**（その場合は「困ったとき」を参照）。

## S2. Secrets に4つ追加する
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で、次の4つを1つずつ追加します。

| Name | Secret |
|---|---|
| `DISCORD_BOT_TOKEN` | ボットのトークン（Discord 開発者ページでコピーしたもの） |
| `SINGLE_CHANNEL_ID` | `# シングル通知` のチャンネルID（数字） |
| `OWNER_DISCORD_ID` | 自分のユーザーID（数字） |
| `WATCHLIST_KEY` | S1 で作った鍵（44文字） |

## S3. ファイルをアップロードする
1. リポジトリのトップ画面で **Add file → Upload files**。
2. パソコンの `購入自動通知github` フォルダから、次をまとめてドラッグします。
   - `single`・`docs` フォルダ
   - `single_settings.yml`・`requirements.txt`・`SETUP.md`・`README.md`
3. **Commit changes** を押します。

## S4. 自動実行の設定を作る
1. **Add file → Create new file** を押し、名前に `.github/workflows/single.yml` と入力します。
2. パソコンの `.github\workflows\single.yml` をメモ帳で開き、中身をすべてコピーして貼り付けます。
3. **Commit changes** を押します。

## S5. テストする
1. **Actions → シングル通知 → Run workflow** で、実行モード **`test-dm`** を選んで実行します。
2. 自分に「✅ シングル通知のテストDMです」が届き、`# シングル通知` に「✅ シングル通知ボットは動いています」と書き込まれれば成功です。
3. 次に **`normal`** で1回実行します（以後は5分おきに自動で動きます）。
4. `# シングル通知` に `!ヘルプ` と書き、5〜15分後に返事が来れば完了です。

> 💡 トレキャットの値段検索は、カード一覧を作り終えるまで（初回は約1時間）「準備中」と表示されます。

## シングル通知の運用

| やりたいこと | 方法 |
|---|---|
| カードを登録・解除する | Discord で `!登録 カード名` / `!解除 カード名` |
| 全員の通知を止める | オーナーが `!全体停止`（再開は `!全体再開`） |
| 発売日だけ通知する | オーナーが `!タイマー 2026-11-15 2`（11/15から2日間） |
| 上限や期限を変える | `single_settings.yml` の `limits` を書き換える |
| 友人に使ってもらう | Discord サーバーに招待するだけ。各自が `!登録` できます（10人まで） |

## シングル通知で困ったとき

| 症状 | 確認すること |
|---|---|
| テストDMが届かない | ① Secrets の名前4つが正確か ② ボットがサーバーに入っているか ③ Discord の「サーバー名 → プライバシー設定 → ダイレクトメッセージ」がオンか |
| `!ヘルプ` に返事がない | ① 5〜15分待ったか ② ボットの「MESSAGE CONTENT INTENT」がオンか ③ ボットが `# シングル通知` を見られる権限があるか |
| 「⚠️ シングル通知が止まっています」が ntfy に届いた | 本文の理由を確認。トークンや鍵の Secrets の入れ間違いが多い原因です |
| 鍵（WATCHLIST_KEY）をなくした | 新しい鍵を作って Secrets を上書きし、リポジトリの `data/watchlist.enc` を削除します（**全員の登録が消えるので、登録し直してもらいます**） |
| ボットのトークンが漏れた | 開発者ページの Bot → **Reset Token** で作り直し、Secrets の `DISCORD_BOT_TOKEN` を上書きします |

---

# 即答（スラッシュコマンド）編

Discord で `/登録` などを使うと、**約1分**で返事が来るようにする手順です（`!登録` などは今まで通り5〜15分で使えます）。
Cloudflare で `duema-bot` を作り、`Hello World!` が表示できている前提です。

## Q1. 受付係のプログラムを Cloudflare に貼り付ける
1. Cloudflare の **Workers & Pages** → **duema-bot** を開きます。
2. 右上の **「Edit code」**（コードを編集）を押します。ブラウザの中にプログラムの編集画面が開きます。
3. 左のファイル一覧で **`worker.js`**（または `index.js`）が選ばれていることを確認します。
4. 右側の編集欄をクリックし、**Ctrl + A → Delete** で中身を全部消します。
5. パソコンの `cloudflare\worker.js` をメモ帳で開き、**Ctrl + A → Ctrl + C** でコピーして、編集欄に **Ctrl + V** で貼り付けます。
6. 右上の **「Deploy」**（デプロイ）を押します。

## Q2. 依頼を暗号化する鍵（PAYLOAD_KEY）を作る
1. **Windows PowerShell** を開き、シングル通知編 S1 と同じ1行を貼り付けて **Enter**。
   ```powershell
   $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_')
   ```
2. 表示された44文字をメモ帳に「PAYLOAD_KEY：」として控えます（WATCHLIST_KEY とは**別の鍵**です）。
3. GitHub の **Settings → Secrets and variables → Actions → New repository secret** で、Name `PAYLOAD_KEY`、Secret に今の44文字を入れて保存します。

## Q3. GitHub の専用トークンを作る（Cloudflare から GitHub を起動するための鍵）
1. ブラウザで https://github.com/settings/personal-access-tokens/new を開きます。
2. 次のとおり入力します。
   | 項目 | 入力・選択 |
   |---|---|
   | Token name | `duema-bot` |
   | Expiration（有効期限） | 選べる中で一番長いもの（期限が来たら作り直します） |
   | Repository access | **Only select repositories** → `duema-yoyaku-watch` だけを選ぶ |
   | Permissions → Repository permissions → **Actions** | **Read and write** |
   | ほかの Permissions | **触らない**（Metadata の Read-only は自動で付きます） |
3. 一番下の **「Generate token」** を押し、表示された `github_pat_…` で始まる文字列をメモ帳に控えます（**この画面を閉じると二度と表示されません**）。

## Q4. Cloudflare に設定を5つ入れる
1. **duema-bot** の画面で **「Settings」**（設定）→ **「Variables and Secrets」**（変数とシークレット）を開き、**「Add」**（追加）を押します。
2. 次の5つを1つずつ追加します。**Type**（種類）の選び方に注意してください。
   | Type | Variable name | Value |
   |---|---|---|
   | **Text** | `DISCORD_PUBLIC_KEY` | Discord 開発者ページの **General Information → PUBLIC KEY** |
   | **Text** | `GITHUB_REPO` | `GitHubのユーザー名/duema-yoyaku-watch` |
   | **Text** | `ALLOWED_GUILD_ID` | 自分の Discord サーバーのID（Discord でサーバーのアイコンを右クリック →「サーバーIDをコピー」） |
   | **Secret** | `GITHUB_TOKEN` | Q3 のトークン |
   | **Secret** | `PAYLOAD_KEY` | Q2 の鍵（GitHub に入れたものと**同じ**もの） |
3. **「Deploy」**（デプロイ）を押して保存します。

## Q5. GitHub にファイルを追加する
1. **Add file → Upload files** で、`single`・`cloudflare` フォルダをドラッグして **Commit changes**。
2. **Add file → Create new file** で、次の2つを作ります（パソコンの同じ名前のファイルをメモ帳で開き、中身をコピーして貼り付け）。
   - `.github/workflows/single-command.yml`
   - `.github/workflows/register-commands.yml`

## Q6. スラッシュコマンドを Discord に登録する
**Actions → スラッシュコマンド登録 → Run workflow** を押します。✅ になり、ログに「スラッシュコマンドを 11 個登録しました」と出れば完了です。

## Q7. Discord に受付のアドレスを教える
1. Discord 開発者ページで **duema-bot（デュエマ通知ボット）** を開き、**General Information** を開きます。
2. **INTERACTIONS ENDPOINT URL** の欄に `https://duema-bot.（サブドメイン）.workers.dev` を貼り付けます。
3. **「Save Changes」** を押します。Discord が受付係に確認の呼び出しをし、成功すれば保存されます。
   - 「interactions_endpoint_url: The specified interactions endpoint url could not be verified.」と出たら、Q1 の貼り付けと Q4 の `DISCORD_PUBLIC_KEY` を確認してください。

## Q8. 試す
`# シングル通知` で `/` を入力すると、コマンドの候補が出ます。**`/ヘルプ`** を選んで送り、「考え中…」のあと約1分で使い方が表示されれば完成です。

## 即答で困ったとき
| 症状 | 確認すること |
|---|---|
| 「⚠️ 受付に失敗しました」と出る | Cloudflare の `GITHUB_TOKEN`（期限切れ・権限）と `GITHUB_REPO` の書き方 |
| 「考え中…」のまま変わらない | GitHub の **Actions → シングル即答** の実行が失敗していないか。`PAYLOAD_KEY` が GitHub と Cloudflare で同じか |
| 「このサーバーでは使えません」と出る | Cloudflare の `ALLOWED_GUILD_ID` |
| `/` を打ってもコマンドが出ない | Q6 を実行したか。Discord アプリを再起動 |
| トークンの期限が切れた | Q3 で作り直し、Cloudflare の `GITHUB_TOKEN` を上書きして Deploy |

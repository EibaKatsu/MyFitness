# MyFitness

Mac上の簡易Web画面からGarmin Connectの活動を取得し、体重・食事と一緒に**自分のSupabaseプロジェクト**へ保存する個人用アプリです。ブラウザへGarminトークンやSupabaseの秘密鍵を渡さず、Pythonサーバーは`127.0.0.1`だけで待ち受けます。

> [!IMPORTANT]
> MyFitnessは複数人で1つのDBを共有するSaaSではありません。利用者ごとに、自分専用のSupabaseプロジェクトを作成してください。

> [!WARNING]
> Garmin接続には非公式の`garminconnect`ライブラリを使用します。Garmin側の仕様変更、レート制限、認証方式の変更によって、予告なく停止する可能性があります。

## できること

- Garminの活動概要を日付範囲で同期（初期値は直近90日）
- Garmin活動IDを一意キーにしたupsert（再同期しても重複しない）
- 日時、種目、距離、時間、平均ペース、平均・最大心拍などの概要を保存
- ラップ、心拍ゾーン、心拍・速度・ケイデンス・パワー等の時系列、天候、ギアを詳細データとして保存
- 有酸素効率指数、週間走行距離、週間獲得標高、心拍ドリフトを期間グラフで確認
- 各活動に練習区分、RPE、疲労感、痛み、路面、実施状況、目的、メモを記録
- ランニング／トレイルランニングを画面で絞り込み
- 体重とメモの追加・編集・削除
- 食事区分、自由記述、任意のカロリー・PFCの追加・編集・削除
- 同期中表示、追加・更新・スキップ件数、失敗理由、同期履歴の記録

GPS座標・軌跡、FITファイル、写真解析、栄養量の自動推定は対象外です。Garminの時系列応答に位置情報が含まれていても、MyFitnessは緯度・経度をDBへ保存しません。

## 安全設計

- Garminのメールアドレスとパスワードは対話ログイン時だけ使用し、保存・ログ出力しません。
- Garminトークンはホームディレクトリ配下に保存し、リポジトリやSupabaseには保存しません。
- Supabase secret/service_role keyは`.env`からPythonだけが読みます。
- 全テーブルでRLSを有効にし、anon/authenticatedロールの権限を取り消します。
- 429、認証失敗、通信失敗をアプリ側で無制限に再試行しません。同期失敗時に既存データは削除しません。

## 必要環境

- macOS
- Python 3.12以上
- [uv](https://docs.astral.sh/uv/)
- 自分のGarmin Connectアカウント
- 自分専用のSupabaseプロジェクト

`pip`や`ensurepip`は使いません。

## セットアップ

### 1. uvをインストール

Homebrewを使う場合:

```bash
brew install uv
```

またはuv公式インストーラー:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. コードを取得

```bash
git clone https://github.com/EibaKatsu/MyFitness.git
cd MyFitness
uv sync --extra dev
```

`uv sync`はプロジェクト専用の`.venv`とロック済み依存関係を使います。

### 3. Supabaseプロジェクトを作成

1. [Supabase Dashboard](https://supabase.com/dashboard)で`New project`を選び、自分専用プロジェクトを作成します。
2. Dashboardの`SQL Editor`で[`supabase/schema.sql`](supabase/schema.sql)を開き、全SQLを実行します。
3. Dashboardの`Settings` → `API Keys`でsecret key（またはlegacy service_role key）を確認します。
4. Project URLはDashboard上部の`Connect`、または`Settings` → `Data API`で確認します。

secret/service_role keyは強い権限を持ちます。ブラウザ、GitHub、チャット、スクリーンショットへ貼らないでください。新しい`sb_secret_...`形式を推奨し、旧service_role JWTにも互換対応しています。

### 4. `.env`を設定

```bash
cp .env.example .env
chmod 600 .env
```

`.env`をエディタで開き、次を設定します。

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SECRET_KEY=sb_secret_REPLACE_ME
GARMIN_TOKEN_STORE=~/.garminconnect_personal
MYFITNESS_DETAIL_SYNC_LIMIT=10
```

検証済みの`~/.garminconnect_personal`を使う場合、そのパスを指定するだけです。既存ファイルを移動・コピー・削除しません。新しく分ける場合は、例えば`~/.garminconnect_myfitness`を指定します。

### 5. Garminへ初回ログイン

```bash
uv run myfitness garmin-login
```

ターミナルでメールアドレス、表示されないパスワード、要求された場合だけMFAコードを入力します。成功するとGarmin発行トークンだけが`GARMIN_TOKEN_STORE`へ保存されます。パスワードは永続保存されません。

既存の有効なトークンを指定した場合、この手順は省略できます。

### 6. アプリを起動

```bash
uv run myfitness serve
```

ブラウザで <http://127.0.0.1:8000> を開き、「活動データ取得」を押します。サーバーは`127.0.0.1`にのみバインドし、LANには公開しません。終了はターミナルで`Control-C`です。

## 使い方

### Garmin同期

初期表示は直近90日です。過去データは開始日・終了日を指定して分割同期できます。同じ期間を再同期しても`garmin_activity_id`の一意制約とupsertにより重複しません。Garminから返らない項目はDBで`NULL`のまま保持します。

1回の同期で詳細取得する活動数は、Garminへの連続アクセスを抑えるため初期値10件です。画面に「未取得の詳細あり」と表示された場合は、少し間隔を空けて同じ期間を再同期してください。`MYFITNESS_DETAIL_SYNC_LIMIT`は1〜50の範囲で変更できます。429が発生した場合は連打せず、時間を置いてください。

DBの日時は`timestamptz`、API送信値はISO 8601で扱い、画面ではMac／ブラウザのローカルタイムゾーンで表示します。距離はDBでメートル、時間は秒、速度はm/sとして保存し、画面でkmや分/kmへ変換します。

### 走力の推移

グラフは横軸が期間、縦軸は選択した指標です。

- **有酸素効率指数**: 3km以上かつ20分以上の通常ランニングについて、勾配補正速度（取得できない場合は平均速度）÷平均心拍を計算します。最初の最大6活動の中央値を100とした固定基準で、各週の中央値を表示します。トレイルは地形差が大きいためこの指数から除外します。
- **週間走行距離**: ランニングとトレイルランニングの週合計です。
- **週間獲得標高**: ランニングとトレイルランニングの週合計です。
- **心拍ドリフト**: 時系列データの前半と後半で心拍÷速度の変化を比較します。低い値ほど、同じ運動強度を保ちやすかった目安になります。

気温、疲労、コース、練習内容でも数値は変動します。単独の活動で判断せず、複数週の傾向として利用してください。

### 体重・食事

各カードから登録できます。既存行の「編集」「削除」も利用できます。カロリーとPFCの空欄は`NULL`であり、ゼロには変換しません。

## よくあるエラー

### MFAコードを求められる／通らない

Garminから届いた最新コードを同じCLIセッションで入力してください。コードを繰り返し間違えた場合は試行を止め、少し時間を置いて`uv run myfitness garmin-login`をやり直します。

### 429 / Too Many Requests

短時間のログイン・同期試行をGarminが制限しています。アプリは無制限再試行しません。連打せず時間を置いてください。毎回ログインせず、保存トークンを再利用することも重要です。

### トークン失効

画面に再認証が必要と表示されたら、ターミナルで次を実行します。

```bash
uv run myfitness garmin-login
```

既存トークンを自動削除しません。トークン保存先自体の破棄が必要な場合は、内容とパスを確認した上で利用者が判断してください。

### Supabase接続失敗

- `.env`のURLとkeyに余分な引用符や空白がないか確認する
- anon/publishable keyではなくsecret/service_role keyか確認する
- `supabase/schema.sql`を実行済みか確認する
- Supabase Dashboardでプロジェクトが一時停止していないか確認する

### 詳細ボタンでDBエラーになる（既存利用者）

v0.1から更新した場合は、Supabase Dashboardの`SQL Editor`で次のマイグレーションを1回実行してください。

```text
supabase/migrations/002_activity_details.sql
```

その後アプリを再起動して同期します。新規セットアップで最新の`supabase/schema.sql`を実行した場合、この追加操作は不要です。

### 画面が開かない

起動中のターミナルにエラーがないか確認し、<http://127.0.0.1:8000> を直接開きます。8000番が使用中なら次を使えます。

```bash
uv run myfitness serve --port 8001
```

## 開発・検証

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

テストでは実アカウントへ接続せず、模擬応答で次を検証します。

- 活動IDによる追加／更新判定とupsert境界
- Garmin日時のUTC化、メートル・秒の維持、欠損値の`NULL`
- 詳細時系列の変換とGPS座標を保存しないこと
- 固定基準の有酸素効率指数、週間集計、心拍ドリフト
- 429発生時に書き込み・再試行せず、失敗履歴を残すこと
- 食事の未入力栄養値が`NULL`のままであること
- localhost以外のHostヘッダーを拒否すること

## データと機密情報をGitへ入れない

`.gitignore`で`.env`、Garminトークン、ログ、`data/`、DBダンプ、仮想環境を除外しています。公開前には次を確認してください。

```bash
git status --short
git ls-files
git log --all -p -- .env '*.log' '*.dump' '*.backup' 'garmin_tokens.json'
```

このチェックは履歴に一度入った秘密を自動削除しません。誤ってcommitした場合はpushを止め、該当キー／トークンを失効させてから履歴を清掃してください。

## 構成

```text
src/myfitness/
  cli.py       # garmin-login / serve
  garmin.py    # 非公式Garmin接続を隔離
  db.py        # Pythonサーバー専用Supabase RESTアクセス
  sync.py      # 概要・詳細のupsertと同期履歴
  analytics.py # 走力指標と週間集計
  web.py       # ローカルWeb API
  templates/   # HTML
  static/      # CSS / JavaScript（ビルド不要）
supabase/schema.sql
supabase/migrations/002_activity_details.sql
tests/
```

## ライセンス

[MIT License](LICENSE)

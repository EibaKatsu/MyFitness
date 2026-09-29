from __future__ import annotations

import getpass
import logging

import typer

from .config import ConfigurationError, Settings
from .garmin import GarminError, login_interactively

app = typer.Typer(
    no_args_is_help=True,
    help="MyFitness: Garminデータと食事・体重を自分のSupabaseへ保存します。",
)


@app.command("garmin-login")
def garmin_login() -> None:
    """Garminへ対話ログインし、ホームディレクトリ配下へトークンを保存します。"""
    try:
        settings = Settings.from_env(require_supabase=False)
        typer.echo(f"トークン保存先: {settings.garmin_token_store}")
        email = typer.prompt("Garminメールアドレス").strip()
        password = getpass.getpass("Garminパスワード（表示されません）: ")
        login_interactively(
            settings.garmin_token_store,
            email,
            password,
            lambda: typer.prompt("MFAコード").strip(),
        )
        password = ""
        typer.secho("Garmin認証に成功しました。", fg=typer.colors.GREEN)
    except (ConfigurationError, GarminError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def serve(port: int = typer.Option(8000, min=1024, max=65535, help="待受ポート")) -> None:
    """ローカルWeb画面を127.0.0.1限定で起動します。"""
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import uvicorn

    from .web import create_app

    typer.echo(f"MyFitness: http://127.0.0.1:{port}")
    uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    app()

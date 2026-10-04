import os
import time
from pathlib import Path
from dotenv import load_dotenv

from db_handler import MediationDB
from discord_notifier import DiscordNotifier
from scraper import MediationScraper

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


def run_check():
    start_time = time.time()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    notifier = DiscordNotifier(webhook_url) if webhook_url else None
    db = MediationDB()

    try:
        scraper = MediationScraper()
        result = scraper.check_citations()

        has_date = result["has_scheduled_date"]
        raw_text = result["raw_text"]
        target_url = result["url"]

        # Actualiza en Firestore y evalúa si es un cambio que requiere notificación
        should_notify = db.update_state_if_changed(new_has_date=has_date, raw_text=raw_text)

        if should_notify and notifier:
            notifier.send_change_alert(detected_text=raw_text, target_url=target_url)
            db.mark_as_notified()

        exec_ms = round((time.time() - start_time) * 1000, 2)
        status_label = "DATE_DETECTED" if has_date else "NO_SESSIONS"
        db.log_execution(result_type=status_label, http_code=200, exec_time_ms=exec_ms)
        print(f"[{status_label}] Chequeo finalizado en {exec_ms}ms: {raw_text[:90]}")

    except Exception as e:
        exec_ms = round((time.time() - start_time) * 1000, 2)
        error_msg = str(e)
        print(f"[ERROR] Falla en chequeo ({exec_ms}ms): {error_msg}")

        try:
            db.log_execution(result_type="ERROR", http_code=500, exec_time_ms=exec_ms, error_msg=error_msg)
        except Exception as db_err:
            print(f"Error al guardar log en Firestore: {db_err}")

        if notifier:
            try:
                notifier.send_error_alert(error_msg)
            except Exception as notif_err:
                print(f"Error al enviar alerta a Discord: {notif_err}")

        raise e


if __name__ == "__main__":
    run_check()
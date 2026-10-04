import requests


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_change_alert(self, detected_text: str, target_url: str = "https://pmf.mediacionchile.gob.cl/MisCitaciones/MisCitaciones") -> bool:
        """Notifica cuando se detecta un cambio en el estado de las citaciones."""
        embed = {
            "title": "🚨 ¡Cambio detectado en Mediación Chile!",
            "description": (
                "**Se ha detectado una citación agendada o un cambio en el estado.**\n\n"
                f"**Detalle encontrado:**\n```text\n{detected_text[:500]}\n```\n"
                f"[👉 Ir a Mis Citaciones]({target_url})"
            ),
            "color": 3066993,  # Verde éxito
            "footer": {"text": "Bot Mediación Usted"}
        }
        res = requests.post(self.webhook_url, json={"username": "Bot Mediación", "embeds": [embed]}, timeout=10)
        return res.status_code in (200, 204)

    def send_error_alert(self, error_message: str):
        """Notifica errores técnicos de ejecución."""
        embed = {
            "title": "⚠️ Error en Bot Mediación",
            "description": f"```{error_message[:800]}```",
            "color": 15158332,  # Rojo
            "footer": {"text": "Bot Mediación Usted"}
        }
        requests.post(self.webhook_url, json={"username": "Bot Mediación (Error)", "embeds": [embed]}, timeout=10)
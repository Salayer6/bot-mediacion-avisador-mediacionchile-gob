import os
import datetime
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import firestore
from google.oauth2 import service_account

# Cargar las variables de entorno buscando el archivo .env en la misma carpeta
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

class MediationDB:
    def __init__(self, collection_name="mediation_state", log_collection="execution_logs"):
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if key_path:
            absolute_key_path = Path(__file__).resolve().parent / key_path
            
            if not absolute_key_path.exists():
                raise FileNotFoundError(
                    f"No se encontró el archivo de clave JSON en: {absolute_key_path}. "
                    "Asegúrate de que 'gcp-key.json' esté en la misma carpeta que este script."
                )
            
            # NOMBRE CORRECTO DEL MÉTODO: from_service_account_file
            credentials = service_account.Credentials.from_service_account_file(str(absolute_key_path))
            project_id = credentials.project_id
            
            # Inicializamos el cliente pasando credenciales y project ID
            self.db = firestore.Client(credentials=credentials, project=project_id, database="wawitadb")
        else:
            # Si no hay variable configurada, intenta las credenciales del sistema
            self.db = firestore.Client()

        self.status_doc_ref = self.db.collection(collection_name).document("current_status")
        self.log_collection_ref = self.db.collection(log_collection)

    def get_current_state(self) -> dict:
        """Obtiene el último estado registrado en la base de datos."""
        doc = self.status_doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        
        return {
            "status": "NO_MEDIATION_SCHEDULED",
            "has_scheduled_date": False,
            "scheduled_date": None,
            "raw_text": "Sin agendamiento detectado",
            "last_checked_at": None,
            "notified": False,
            "notification_sent_at": None
        }

    def update_state_if_changed(self, new_has_date: bool, raw_text: str, scheduled_date_str: str = None) -> bool:
        """Compara y actualiza el estado en Firestore."""
        current_state = self.get_current_state()
        now = datetime.datetime.now(datetime.timezone.utc)

        should_notify = False

        if new_has_date and not current_state.get("notified", False):
            should_notify = True
            new_status_str = "SCHEDULED"
        elif new_has_date:
            new_status_str = "SCHEDULED"
        else:
            new_status_str = "NO_MEDIATION_SCHEDULED"

        update_data = {
            "status": new_status_str,
            "has_scheduled_date": new_has_date,
            "raw_text": raw_text,
            "last_checked_at": now
        }

        if not new_has_date:
            update_data["notified"] = False

        if scheduled_date_str:
            update_data["scheduled_date"] = scheduled_date_str

        self.status_doc_ref.set(update_data, merge=True)
        return should_notify

    def mark_as_notified(self):
        """Marca en la base de datos que la notificación ya fue enviada."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self.status_doc_ref.set({
            "notified": True,
            "notification_sent_at": now
        }, merge=True)


    def log_execution(self, result_type: str, http_code: int = 200, exec_time_ms: float = 0.0, error_msg: str = None):
        """Guarda un log de auditoría de la ejecución."""
        now = datetime.datetime.now(datetime.timezone.utc)
        log_entry = {
            "timestamp": now,
            "result": result_type,
            "http_status_code": http_code,
            "execution_time_ms": exec_time_ms,
            "error_message": error_msg
        }
        self.log_collection_ref.add(log_entry)
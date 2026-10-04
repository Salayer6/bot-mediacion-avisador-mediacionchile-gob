from db_handler import MediationDB

db = MediationDB()

# Probamos leer el estado inicial
estado = db.get_current_state()
print("Estado actual en Firestore:", estado)

# Probamos insertar un log de prueba
db.log_execution(result_type="TEST_SUCCESS", http_code=200, exec_time_ms=120.5)
print("¡Log guardado exitosamente en la nube!")
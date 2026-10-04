import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

BASE_URL = "https://pmf.mediacionchile.gob.cl"
LOGIN_PAGE_URL = f"{BASE_URL}/Login/SegundaClave"
LOGIN_ACTION_URL = f"{BASE_URL}/Login/IngresoSC"
CITACIONES_URL = f"{BASE_URL}/MisCitaciones/MisCitaciones"

NO_SESSIONS_TEXT = "usted no posee sesiones pendientes actualmente"

# Límites de seguridad
HTTP_TIMEOUT = 15           # segundos
MAX_RESPONSE_BYTES = 512_000  # 512 KB — previene DoS por respuesta gigante
ALLOWED_HOST = "pmf.mediacionchile.gob.cl"  # único dominio permitido


def format_chilean_run(run: str) -> str:
    """Formatea el RUN al formato ##.###.###-# esperado por el portal."""
    clean = re.sub(r"[^0-9kK]", "", run or "")
    if len(clean) >= 2:
        num = clean[:-1]
        dv = clean[-1].upper()
        num_rev = num[::-1]
        groups = [num_rev[i : i + 3] for i in range(0, len(num_rev), 3)]
        formatted_num = ".".join(groups)[::-1]
        return f"{formatted_num}-{dv}"
    return clean


class MediationScraper:
    def __init__(self, run: str = None, password: str = None, session_cookie: str = None):
        self.run = run or os.getenv("MEDIACION_RUN", "")
        self.password = password or os.getenv("MEDIACION_PASSWORD", "")
        self.session_cookie = session_cookie or os.getenv("MEDIACION_COOKIE", "")

        self.session = requests.Session()
        # verify=True es el default, se declara explícitamente para dejar constancia
        # de que la verificación SSL NUNCA debe desactivarse.
        self.session.verify = True
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            # Sin wildcard */* para no aceptar tipos de contenido arbitrarios
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        })

        if self.session_cookie:
            # Si se proporciona cookie manual (por ejemplo obtenida con ClaveÚnica)
            self.session.cookies.set("ASP.NET_SessionId", self.session_cookie)

    @staticmethod
    def _safe_url(url: str) -> str:
        """Valida que una URL de redirección pertenezca al dominio permitido."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname != ALLOWED_HOST:
            raise RuntimeError(
                f"Redirección a dominio no permitido bloqueada: {parsed.hostname!r}"
            )
        return url

    def login(self) -> bool:
        """Inicia sesión en el portal mediante Segunda Clave."""
        if not self.run or not self.password:
            raise ValueError(
                "Faltan credenciales: configure MEDIACION_RUN y MEDIACION_PASSWORD en .env "
                "(o MEDIACION_COOKIE si usa sesión de ClaveÚnica)."
            )

        # 1. Obtener token CSRF de la página de SegundaClave
        resp = self.session.get(LOGIN_PAGE_URL, timeout=HTTP_TIMEOUT, stream=True)
        resp.raise_for_status()
        content = resp.raw.read(MAX_RESPONSE_BYTES, decode_content=True)
        page_html = content.decode("utf-8", errors="replace")

        match = re.search(
            r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
            page_html,
        )
        if not match:
            raise RuntimeError("No se encontró el token CSRF en la página de login.")

        token = match.group(1)
        formatted_run = format_chilean_run(self.run)

        # 2. Enviar login POST vía AJAX
        payload = {
            "screenWidth": "1920",
            "run": formatted_run,
            "clave": self.password,
            "__RequestVerificationToken": token,
        }

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": LOGIN_PAGE_URL,
            "Origin": BASE_URL,
        }

        login_res = self.session.post(
            LOGIN_ACTION_URL, data=payload, headers=headers, timeout=HTTP_TIMEOUT
        )
        login_res.raise_for_status()

        try:
            data = login_res.json()
        except Exception:
            # No se incluye el cuerpo de la respuesta para evitar filtrar tokens/sesión
            raise RuntimeError("Respuesta inesperada al iniciar sesión (ver logs del servidor).")

        message = data.get("message", "")
        if message == "ERRORSC":
            # Mensaje genérico: no revelar cuál campo falló
            raise ValueError("Error de autenticación: verifique sus credenciales en .env.")

        # Los mensajes 'HOME', 'PASO1', etc. indican éxito en la autenticación
        return True

    def _get_page(self, url: str) -> str:
        """Descarga una página con límite de tamaño y validación de dominio."""
        self._safe_url(url)
        res = self.session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True, stream=True)
        res.raise_for_status()
        # Validar que la redirección final sigue en el dominio permitido
        self._safe_url(res.url)
        content = res.raw.read(MAX_RESPONSE_BYTES, decode_content=True)
        return content.decode("utf-8", errors="replace")

    def check_citations(self) -> dict:
        """
        Navega a MisCitaciones/MisCitaciones y escanea el estado de sesiones.
        Retorna un diccionario con:
            - has_scheduled_date (bool): True si se detecta una fecha agendada o cambio.
            - raw_text (str): Texto o detalle detectado.
            - url (str): URL de consulta.
        """
        page_html = self._get_page(CITACIONES_URL)

        # Si el sitio redirigió al login o al home sin autenticar, autenticamos y reintentamos
        if "/Login" in page_html or "SegundaClave" in page_html:
            self.login()
            page_html = self._get_page(CITACIONES_URL)

        soup = BeautifulSoup(page_html, "html.parser")
        page_text = " ".join(soup.stripped_strings)
        page_lower = page_text.lower()

        # Validación principal: estado vacío
        if NO_SESSIONS_TEXT in page_lower:
            return {
                "has_scheduled_date": False,
                "raw_text": "Usted no posee sesiones pendientes actualmente.",
                "url": CITACIONES_URL,
            }

        # Si no aparece la frase de "no posee sesiones", se detectó un cambio o agendamiento
        content_container = (
            soup.find("table")
            or soup.find("div", class_=re.compile(r"card|accordion|table|citacion|container", re.I))
            or soup.find("main")
        )
        detected_snippet = (
            content_container.get_text(separator="\n", strip=True)
            if content_container
            else page_text[:500]
        )

        return {
            "has_scheduled_date": True,
            "raw_text": detected_snippet[:1000],
            "url": CITACIONES_URL,
        }

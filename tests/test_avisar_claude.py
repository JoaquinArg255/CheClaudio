import importlib.util
import unittest
from pathlib import Path

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "avisar_claude.py"
_spec = importlib.util.spec_from_file_location("avisar_claude", _RUTA)
avisar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avisar)

CWD = r"C:\Users\Alguien\Desktop\CheClaudio"


class PreguntaFinal(unittest.TestCase):
    def test_detecta_la_pregunta_del_cierre(self):
        respuesta = "Listo, lo subí.\n\n- detalle uno\n- detalle dos\n\nEso es todo. ¿Querés que también lo pruebe?"
        self.assertEqual(avisar.pregunta_final(respuesta), "¿Querés que también lo pruebe?")

    def test_una_pregunta_en_el_medio_no_cuenta(self):
        respuesta = "Me preguntaste ¿por qué falla? Era el import.\n\nYa lo arreglé y pasan los tests."
        self.assertIsNone(avisar.pregunta_final(respuesta))
        self.assertIsNone(avisar.pregunta_final(""))


class Avisos(unittest.TestCase):
    def test_pregunta_con_opciones(self):
        datos = {"cwd": CWD, "tool_input": {"questions": [{"question": "¿Cuál preferís?"},
                                                           {"question": "¿Y el color?"}]}}
        self.assertEqual(avisar.aviso_de_pregunta(datos),
                         "Claude te está preguntando algo en CheClaudio: ¿Cuál preferís? Y 1 pregunta más.")
        self.assertIsNone(avisar.aviso_de_pregunta({"cwd": CWD, "tool_input": {}}))

    def test_permiso(self):
        datos = {"cwd": CWD, "notification_type": "permission_prompt",
                 "message": "Claude needs your permission to use Bash"}
        self.assertEqual(avisar.aviso_de_permiso(datos), "Claude necesita tu permiso en CheClaudio para usar Bash.")
        # "Está esperando" sin pregunta lo cubre el aviso de cuando termina: no se repite.
        self.assertIsNone(avisar.aviso_de_permiso({"cwd": CWD, "notification_type": "idle_prompt",
                                                   "message": "Claude is waiting for your input"}))

    def test_lo_largo_se_recorta(self):
        largo = "¿" + "palabra " * 60 + "?"
        self.assertLessEqual(len(avisar._corto(largo)), avisar._LARGO + 3)


if __name__ == "__main__":
    unittest.main()

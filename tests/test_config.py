import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from che_claudio import config as configuracion
from che_claudio.tiempo import fecha_hablada


class Config(unittest.TestCase):
    def setUp(self):
        self.carpeta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.propio = self.carpeta / "config.json"
        self.enterContext(mock.patch.object(configuracion, "PREFERENCIAS", self.carpeta / "datos" / "preferencias.json"))
        self.ejemplo = json.loads(configuracion.EJEMPLO.read_text(encoding="utf-8"))

    def test_sin_config_propio_vale_todo_el_ejemplo(self):
        config = configuracion.cargar(self.propio)
        self.assertEqual(config["voz"], self.ejemplo["voz"])
        self.assertEqual(config["cerebro"], self.ejemplo["cerebro"])
        self.assertIn("youtube", config["sitios"])

    def test_el_propio_cambia_solo_lo_que_escribe(self):
        self.propio.write_text(json.dumps({"voz": "propia", "cerebro": {"modelo": "otro"}}), encoding="utf-8")
        config = configuracion.cargar(self.propio)
        self.assertEqual(config["voz"], "propia")
        self.assertEqual(config["cerebro"]["modelo"], "otro")
        self.assertEqual(config["cerebro"]["esfuerzo"], self.ejemplo["cerebro"]["esfuerzo"])  # el resto queda
        self.assertEqual(config["segundos_atento"], self.ejemplo["segundos_atento"])

    def test_las_preferencias_dichas_por_voz_crean_la_carpeta_de_datos(self):
        configuracion.guardar_preferencia("volumen_voz", 0.5)
        self.assertEqual(configuracion.cargar(self.propio)["volumen_voz"], 0.5)


class Fechas(unittest.TestCase):
    def test_fecha_hablada(self):
        self.assertEqual(fecha_hablada(datetime(2026, 10, 16)), "viernes 16 de octubre de 2026")
        self.assertEqual(fecha_hablada(datetime(2026, 1, 5)), "lunes 5 de enero de 2026")


if __name__ == "__main__":
    unittest.main()

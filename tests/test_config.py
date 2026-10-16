import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from che_claudio import config as configuracion
from che_claudio.interprete import fecha_hablada


class Config(unittest.TestCase):
    def setUp(self):
        self.carpeta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(configuracion, "PREFERENCIAS", self.carpeta / "datos" / "preferencias.json"))
        (self.carpeta / "config.example.json").write_text(json.dumps({"voz": "de_ejemplo"}), encoding="utf-8")

    def test_sin_config_propio_usa_el_de_ejemplo(self):
        config = configuracion.cargar(self.carpeta / "config.json")
        self.assertEqual(config["voz"], "de_ejemplo")
        self.assertEqual(config["segundos_atento"], 2.5)  # lo que no está en el archivo queda por defecto

    def test_el_config_propio_tiene_prioridad(self):
        (self.carpeta / "config.json").write_text(json.dumps({"voz": "propia"}), encoding="utf-8")
        self.assertEqual(configuracion.cargar(self.carpeta / "config.json")["voz"], "propia")

    def test_las_preferencias_dichas_por_voz_crean_la_carpeta_de_datos(self):
        configuracion.guardar_preferencia("volumen_voz", 0.5)
        self.assertEqual(configuracion.cargar(self.carpeta / "config.json")["volumen_voz"], 0.5)


class Fechas(unittest.TestCase):
    def test_fecha_hablada(self):
        self.assertEqual(fecha_hablada(datetime(2026, 10, 16)), "viernes 16 de octubre de 2026")
        self.assertEqual(fecha_hablada(datetime(2026, 1, 5)), "lunes 5 de enero de 2026")


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from che_claudio import proyectos
from che_claudio.servicios.whatsapp import _coincidencia
from che_claudio.sistema import archivos, ventanas


class BuscarArchivos(unittest.TestCase):
    def test_no_ofrece_ejecutables_para_abrir(self):
        carpeta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for nombre in ("factura.pdf.exe", "factura de luz.pdf", "factura.bat", "factura.lnk"):
            (carpeta / nombre).touch()
        self.assertEqual([p.name for p in archivos.buscar("factura", carpeta)], ["factura de luz.pdf"])


class ChatsDeWhatsApp(unittest.TestCase):
    def test_gana_el_que_tiene_las_palabras_pedidas(self):
        exacto, contiene = _coincidencia("tortugas", "Tortugas"), _coincidencia("tortugas", "Tortugas 2026")
        parecido = _coincidencia("tortugas", "Tortuga")
        self.assertGreater(exacto, contiene)
        self.assertGreater(contiene, parecido)
        self.assertGreaterEqual(parecido, 0.8)  # sigue sirviendo si no hay nada mejor
        self.assertLess(_coincidencia("tortugas", "Tortas de mamá"), 0.8)


class Procesos(unittest.TestCase):
    def victima(self) -> subprocess.Popen:
        """Un proceso aparte para cerrar: si un freno se rompe, se cierra este y no la corrida de tests."""
        proceso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (proceso.kill(), proceso.wait()))
        return proceso

    def test_solo_reconoce_el_proceso_que_arranco_a_esa_hora(self):
        proceso = self.victima()
        inicio = ventanas.inicio_de_pid(proceso.pid)
        self.assertTrue(ventanas.es_el_mismo(proceso.pid, inicio))
        # El mismo número con otra hora es otro programa (Windows reutiliza los números).
        self.assertFalse(ventanas.es_el_mismo(proceso.pid, inicio - 3600))
        self.assertFalse(ventanas.es_el_mismo(proceso.pid, 0))  # guardado sin hora: no se toca

    def test_cierra_solo_si_sigue_siendo_el_mismo(self):
        proceso = self.victima()
        inicio = ventanas.inicio_de_pid(proceso.pid)
        self.assertFalse(ventanas.terminar(proceso.pid, inicio - 3600))
        self.assertIsNone(proceso.poll())
        self.assertTrue(ventanas.terminar(proceso.pid, inicio))
        proceso.wait(10)

    def test_lo_anotado_en_un_archivo(self):
        nota = Path(self.enterContext(tempfile.TemporaryDirectory())) / "proceso.pid"
        proceso = self.victima()
        nota.write_text(str(proceso.pid))  # formato viejo, sin hora: no se sabe si es el mismo
        self.assertFalse(ventanas.terminar_anotado(nota))
        self.assertIsNone(proceso.poll())
        self.assertFalse(nota.exists())
        ventanas.anotar_proceso(nota, proceso.pid)
        self.assertTrue(ventanas.terminar_anotado(nota))
        proceso.wait(10)
        self.assertFalse(ventanas.terminar_anotado(nota))  # ya no hay nota

    def test_bajar_un_proyecto_no_toca_procesos_ajenos(self):
        carpeta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(proyectos, "_CARPETA", carpeta))
        self.enterContext(mock.patch.object(proyectos, "_ACTIVOS", carpeta / "activos.json"))
        ajeno, propio = self.victima(), self.victima()
        # "viejo" quedó de antes de un reinicio: su número ahora es de otro programa (otra hora de inicio).
        (carpeta / "activos.json").write_text(json.dumps({"demo": [
            {"paso": "viejo", "pid": ajeno.pid, "inicio": ventanas.inicio_de_pid(ajeno.pid) - 3600},
            {"paso": "web", "pid": propio.pid, "inicio": ventanas.inicio_de_pid(propio.pid)},
        ]}))
        respuesta = proyectos.Proyectos({"demo": {"pasos": [{"nombre": "web"}]}}, print, print).bajar("demo")
        self.assertEqual(respuesta, "Listo, bajé demo")
        self.assertIsNone(ajeno.poll())
        propio.wait(10)
        self.assertNotIn("demo", json.loads((carpeta / "activos.json").read_text()))


if __name__ == "__main__":
    unittest.main()

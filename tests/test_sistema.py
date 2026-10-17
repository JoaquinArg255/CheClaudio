import os
import tempfile
import unittest
from pathlib import Path

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
    def test_solo_reconoce_el_proceso_que_arranco_a_esa_hora(self):
        propio = os.getpid()
        inicio = ventanas.inicio_de_pid(propio)
        self.assertTrue(ventanas.es_el_mismo(propio, inicio))
        # El mismo número con otra hora es otro programa (Windows reutiliza los números).
        self.assertFalse(ventanas.es_el_mismo(propio, inicio - 3600))
        self.assertFalse(ventanas.es_el_mismo(propio, 0))  # guardado sin hora: no se toca

    def test_no_mata_un_numero_que_ya_es_de_otro(self):
        propio = os.getpid()
        self.assertFalse(ventanas.terminar(propio, ventanas.inicio_de_pid(propio) - 3600))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from che_claudio import memoria
from che_claudio.cerebro import _NO_SABE, _para_decir
from che_claudio.proyectos import Proyectos
from che_claudio.texto import normalizar


class MemoriaTest(unittest.TestCase):
    def setUp(self):
        carpeta = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for nombre, archivo in (("CARPETA", ""), ("_RECUERDOS", "recuerdos.md"), ("_CHARLAS", "charlas.md"),
                                ("_REPASADO", "repasado.txt")):
            self.enterContext(mock.patch.object(memoria, nombre, carpeta / archivo))

    def test_los_comentarios_no_llegan_al_cerebro(self):
        (memoria.CARPETA / "sobre_mi.md").write_text("# Sobre mí\n<!-- ejemplo: (tu nombre) -->\n- Uso Brave.\n",
                                                     encoding="utf-8")
        self.assertNotIn("tu nombre", memoria.cargar())
        self.assertIn("Uso Brave", memoria.cargar())

    def test_repasa_solo_lo_nuevo(self):
        memoria.anotar_charla("soy de Córdoba", "Anotado.")
        memoria.anotar_charla("¿qué clima hace?", "Va a llover.\n\nSources:\n- una página", de_afuera=True)
        nuevas = memoria.charlas_sin_repasar()
        self.assertEqual(len(nuevas), 2)  # cada intercambio queda en una sola línea
        # Lo que Claudio leyó de internet o de la pantalla no se le pasa a quien saca los recuerdos.
        self.assertNotIn("Va a llover", memoria.para_repasar(nuevas)[1])
        self.assertIn("¿qué clima hace?", memoria.para_repasar(nuevas)[1])
        memoria.marcar_repasadas(nuevas)
        self.assertEqual(memoria.charlas_sin_repasar(), [])
        memoria.anotar_charla("me gusta Rihanna", "Buen gusto.")
        self.assertEqual(len(memoria.charlas_sin_repasar()), 1)


class CerebroTest(unittest.TestCase):
    def test_lo_que_no_se_dice_en_voz_alta(self):
        respuesta = "Mañana llueve en Córdoba.\n\nSources:\n- [Meteored](https://www.meteored.com.ar/cordoba)"
        self.assertEqual(_para_decir(respuesta), "Mañana llueve en Córdoba.")
        self.assertEqual(_para_decir("Mirá [esta página](https://ejemplo.com) cuando puedas."),
                         "Mirá esta página cuando puedas.")

    def test_detecta_cuando_dice_que_no_sabe(self):
        for frase in ("Eso no lo puedo hacer, mis herramientas no me permiten hacer clic.",
                      "No tengo una herramienta para apagar la computadora.",
                      "Programar está fuera de mis herramientas.", "Eso todavía no lo sé hacer."):
            with self.subTest(frase):
                self.assertTrue(_NO_SABE.search(normalizar(frase)))
        for frase in ("No puedo decirte con seguridad quién gana.", "Quedó anotado, en segundo plano.",
                      "No te entendí bien, ¿me lo repetís?"):
            with self.subTest(frase):
                self.assertFalse(_NO_SABE.search(normalizar(frase)))


class ProyectosTest(unittest.TestCase):
    def test_reconoce_el_proyecto_por_nombre_aproximado(self):
        proyectos = Proyectos({"Cancha Libre": {"pasos": [{"nombre": "frontend"}]}}, print, print)
        for pedido in ("cancha libre", "canchalibre", "el de cancha libre", "Cancha Libre"):
            with self.subTest(pedido):
                self.assertEqual(proyectos.resolver(pedido), "cancha libre")
        self.assertIsNone(proyectos.resolver("la facturación"))
        self.assertEqual(proyectos.pasos("cancha libre"), ["frontend"])


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest import mock

from che_claudio.asistente import Asistente
from che_claudio.texto import tokenizar


class SinLlamarlo(unittest.TestCase):
    """Lo que se dice en los segundos que sigue atento, sin "Che Claudio"."""

    def setUp(self):
        self.ejecutor = mock.Mock()
        self.asistente = Asistente({"cerebro": {"modo": "hibrido"}}, mock.Mock(), mock.Mock(), self.ejecutor, None)

    def test_no_cierra_ni_se_apaga(self):
        for frase in ("chau", "bueno, chau", "cerrá todo", "cerrá Spotify", "bloqueá la compu", "apagá la compu"):
            with self.subTest(frase=frase):
                self.assertEqual(self.asistente.atender(tokenizar(frase), sin_llamado=True), "ignorado")
        self.ejecutor.ejecutar.assert_not_called()

    def test_lo_que_se_deshace_sigue_andando(self):
        self.assertEqual(self.asistente.atender(tokenizar("pausá"), sin_llamado=True), "listo")
        self.assertEqual(self.ejecutor.ejecutar.call_args[0][0].tipo, "pausar")

    def test_llamandolo_si_lo_hace(self):
        self.asistente.atender(tokenizar("cerrá todo"))
        self.assertEqual(self.ejecutor.ejecutar.call_args[0][0].tipo, "cerrar_todo")


if __name__ == "__main__":
    unittest.main()

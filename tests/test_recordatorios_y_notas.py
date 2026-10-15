import unittest
from datetime import datetime

from che_claudio.interprete import Accion, cuando, interpretar, separar_llamado
from che_claudio.texto import normalizar

# Viernes 2 de octubre de 2026, 18:19: la hora de la prueba real del registro.
AHORA = datetime(2026, 10, 2, 18, 19)


def orden(texto):
    return interpretar(separar_llamado(texto), AHORA)


def momento(frase):
    encontrado = cuando(normalizar(frase), AHORA)
    return encontrado[0] if encontrado else None


class HorasTest(unittest.TestCase):
    def test_relativas(self):
        self.assertEqual(momento("en 10 minutos"), datetime(2026, 10, 2, 18, 29))
        self.assertEqual(momento("en media hora"), datetime(2026, 10, 2, 18, 49))
        self.assertEqual(momento("en una hora y media"), datetime(2026, 10, 2, 19, 49))
        self.assertEqual(momento("en 2 horas"), datetime(2026, 10, 2, 20, 19))

    def test_absolutas(self):
        # "a las 6 y 21" dicho a las 18:19 es dentro de dos minutos, no mañana a la mañana.
        self.assertEqual(momento("a las 6 y 21"), datetime(2026, 10, 2, 18, 21))
        self.assertEqual(momento("a las 18:30"), datetime(2026, 10, 2, 18, 30))
        self.assertEqual(momento("a las siete y media"), datetime(2026, 10, 2, 19, 30))
        self.assertEqual(momento("a las 8 menos cuarto"), datetime(2026, 10, 2, 19, 45))
        self.assertEqual(momento("a las 10 de la noche"), datetime(2026, 10, 2, 22, 0))
        self.assertEqual(momento("a las 5"), datetime(2026, 10, 3, 5, 0))  # las 17 ya pasaron
        self.assertEqual(momento("mañana a las 8"), datetime(2026, 10, 3, 8, 0))
        self.assertEqual(momento("mañana a las 8 de la noche"), datetime(2026, 10, 3, 20, 0))
        self.assertEqual(momento("a la una de la tarde"), datetime(2026, 10, 3, 13, 0))
        self.assertIsNone(momento("cuando puedas"))


class RecordatoriosTest(unittest.TestCase):
    def test_recordatorio(self):
        self.assertEqual(orden("Che Claudio, avisame a las 6 y 21 que tengo que salir."),
                         [Accion("recordatorio", "Tengo que salir", valor=int(datetime(2026, 10, 2, 18, 21).timestamp()))])
        self.assertEqual(orden("che claudio, recordame en 10 minutos que saque la pizza del horno"),
                         [Accion("recordatorio", "Saque la pizza del horno",
                                 valor=int(datetime(2026, 10, 2, 18, 29).timestamp()))])
        self.assertEqual(orden("che claudio, recordame que mañana a las 9 tengo dentista"),
                         [Accion("recordatorio", "Tengo dentista", valor=int(datetime(2026, 10, 3, 9).timestamp()))])

    def test_sin_hora_lo_piensa_el_cerebro(self):
        self.assertEqual(orden("che claudio, recordame lo del dentista"),
                         [Accion("desconocido", "recordame lo del dentista")])

    def test_ver_y_cancelar(self):
        self.assertEqual(orden("che claudio, ¿qué recordatorios tengo?"), [Accion("ver_recordatorios")])
        self.assertEqual(orden("che claudio, cancelá el recordatorio de la pizza"),
                         [Accion("cancelar_recordatorio", "pizza")])

    def test_acordate_sigue_siendo_memoria(self):
        self.assertEqual(orden("che claudio, acordate de que me gusta el mate")[0].tipo, "desconocido")


class NotasTest(unittest.TestCase):
    def test_abrir_bloc_y_escribir(self):
        self.assertEqual(orden("che claudio, abrí un bloc de notas y escribí: comprar pan, leche y yerba."),
                         [Accion("nota", "Comprar pan, leche y yerba", valor=1)])

    def test_dictado(self):
        self.assertEqual(orden("che claudio, anotá que el parcial es el 15 de octubre"),
                         [Accion("nota", "El parcial es el 15 de octubre")])
        self.assertEqual(orden("che claudio, escribí en una nota nueva ideas para el proyecto"),
                         [Accion("nota", "Ideas para el proyecto", valor=1)])
        self.assertEqual(orden("che claudio, escribí también que llame a mamá"),
                         [Accion("nota", "Llame a mamá", valor=0)])
        self.assertEqual(orden("che claudio, agregá a la lista: tomates"), [Accion("nota", "Tomates", valor=0)])

    def test_dictado_que_viene_despues(self):
        # Casos reales del registro: no hay que escribir "en el blog de notas, eh, lo siguiente".
        self.assertEqual(orden("Che Claudio, también anótame en el blog de notas. Eh, lo siguiente.")[0].tipo,
                         "desconocido")
        self.assertEqual(orden("che claudio, anotá en el bloque de notas que mañana hay parcial"),
                         [Accion("nota", "Mañana hay parcial")])

    def test_escribir_a_alguien_sigue_siendo_whatsapp(self):
        self.assertEqual(orden("che claudio, escribí a Martín que llego tarde"),
                         [Accion("mensaje", "Llego tarde", destinatario="Martín")])


if __name__ == "__main__":
    unittest.main()

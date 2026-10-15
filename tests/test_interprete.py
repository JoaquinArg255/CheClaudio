import unittest
from datetime import datetime

from che_claudio.interprete import (Accion, acepta_verlo, es_afirmacion, frase_cortada, hora_hablada, interpretar,
                                    pide_mostrar, separar_llamado)
from che_claudio.texto import tokenizar, unir


def orden(texto):
    """Simula la frase completa: llamado + interpretación."""
    palabras = separar_llamado(texto)
    return None if palabras is None else interpretar(palabras)


class LlamadoTest(unittest.TestCase):
    def test_reconoce_el_llamado(self):
        for frase in ("Che Claudio, abrí YouTube.", "che claudio abri youtube", "¡Ché, Claudio! Abrí YouTube",
                      "Hey Claudio, abrí YouTube", "Claudio, abrí YouTube", "Checlaudio abrí YouTube",
                      "Che Claudia, abrí YouTube"):
            with self.subTest(frase):
                self.assertEqual(unir(separar_llamado(frase)).lower().replace("í", "i"), "abri youtube")

    def test_ignora_lo_que_no_es_llamado(self):
        for frase in ("abrí youtube", "el audio está bajo", "che, subí el audio", "ayer hablé con mi amigo Claudio",
                      "", "claro que sí"):
            with self.subTest(frase):
                self.assertIsNone(separar_llamado(frase))

    def test_llamado_solo(self):
        self.assertEqual(separar_llamado("Che Claudio."), [])


class InterpreteTest(unittest.TestCase):
    def test_abrir_sitio(self):
        self.assertEqual(orden("Che Claudio, abrí YouTube"), [Accion("abrir", "YouTube")])

    def test_ejemplo_spotify_en_segundo_plano(self):
        self.assertEqual(
            orden("Che Claudio, abrí Spotify en segundo plano y poné Don't Speak."),
            [Accion("reproducir", "Don't Speak", "spotify", True)])

    def test_abrir_y_reproducir_se_funden(self):
        self.assertEqual(orden("Che Claudio, abrí Spotify y poné Don’t Speak"),
                         [Accion("reproducir", "Don't Speak", "spotify")])

    def test_mostramelo_trae_al_frente(self):
        self.assertEqual(orden("che claudio, abrí Spotify y poné Don't Speak y mostrámelo"),
                         [Accion("reproducir", "Don't Speak", "spotify", False)])
        self.assertEqual(orden("che claudio, abrí YouTube y mostrámelo, por favor"),
                         [Accion("abrir", "YouTube", segundo_plano=False)])
        self.assertEqual(orden("che claudio, mostrame YouTube"), [Accion("abrir", "YouTube", segundo_plano=False)])
        self.assertEqual(orden("che claudio, abrí la calculadora en primer plano"),
                         [Accion("abrir", "calculadora", segundo_plano=False)])

    def test_archivos(self):
        self.assertEqual(orden("che claudio, buscá el archivo resumen parcial"),
                         [Accion("archivo", "resumen parcial")])
        self.assertEqual(
            orden("che claudio, buscá en la carpeta seminario el archivo resumen parcial pdf y abrilo en Brave"),
            [Accion("archivo", "resumen parcial", carpeta="seminario", formato="pdf", programa="brave")])
        # Todo de corrido: la carpeta y el nombre se separan al ejecutar, mirando qué carpetas existen.
        self.assertEqual(
            orden("che claudio, buscá en la carpeta seminario resumen parcial archivo pdf, y abrilo en brave"),
            [Accion("archivo", carpeta="seminario resumen parcial", formato="pdf", programa="brave")])
        self.assertEqual(
            orden("che claudio, buscá en descargas el pdf de ingeniería de software y mostrámelo"),
            [Accion("archivo", "ingeniería de software", segundo_plano=False, carpeta="descargas", formato="pdf")])
        self.assertEqual(orden("che claudio, abrí el pdf del parcial en brave"),
                         [Accion("archivo", "parcial", formato="pdf", programa="brave")])
        self.assertEqual(orden("che claudio, abrí la carpeta descargas"), [Accion("archivo", carpeta="descargas")])

    def test_programas_no_son_archivos(self):
        self.assertEqual(orden("che claudio, abrí word y excel"), [Accion("abrir", "word"), Accion("abrir", "excel")])
        self.assertEqual(orden("che claudio, abrí el word del informe final"),
                         [Accion("archivo", "informe final", formato="word")])

    def test_mensajes(self):
        self.assertEqual(orden("che claudio, mandá un hola a mi grupo llamado Tortugas"),
                         [Accion("mensaje", "Hola", destinatario="Tortugas")])
        self.assertEqual(orden("che claudio, mandale un mensaje a Martín que diga llego en diez minutos."),
                         [Accion("mensaje", "Llego en diez minutos", destinatario="Martín")])
        self.assertEqual(orden("che claudio, decile a mamá que ya salgo, gracias"),
                         [Accion("mensaje", "Ya salgo, gracias", destinatario="mamá")])
        self.assertEqual(orden("che claudio, mandá por whatsapp un nos vemos mañana al grupo de la facu"),
                         [Accion("mensaje", "Nos vemos mañana", destinatario="facu")])
        self.assertEqual(orden("che claudio, escribile a Martín Gómez hola, ¿cómo andás?"),
                         [Accion("mensaje", "Hola, ¿cómo andás?", destinatario="Martín Gómez")])
        self.assertEqual(orden("che claudio, enviá un mensaje"), [Accion("desconocido", "enviá un mensaje")])

    def test_volumen_de_su_voz_no_es_el_de_la_pc(self):
        self.assertEqual(orden("che claudio, hablá más bajo"), [Accion("volumen_voz_relativo", valor=-10)])
        self.assertEqual(orden("che claudio, bajate el volumen a 30"), [Accion("volumen_voz", valor=30)])
        self.assertEqual(orden("che claudio, subí un poco tu voz"), [Accion("volumen_voz_relativo", valor=6)])
        self.assertEqual(orden("che claudio, bajá el volumen"), [Accion("volumen_relativo", valor=-10)])

    def test_cerrar_todo(self):
        self.assertEqual(orden("che claudio, cerrá todo"), [Accion("cerrar_todo")])
        self.assertEqual(orden("che claudio, cerrá todo lo demás"), [Accion("cerrar_todo")])
        self.assertEqual(orden("che claudio, cerrá todo menos Spotify y el Brave"),
                         [Accion("cerrar_todo", "Spotify,Brave")])

    def test_pide_mostrar(self):
        for frase in ("abrí YouTube y mostrámelo", "sí, mostrame", "abrilo en pantalla", "ponelo al frente"):
            self.assertTrue(pide_mostrar(tokenizar(frase)), frase)
        for frase in ("tengo ganas de hacer unas cuentas", "sí, dale", "abrí YouTube"):
            self.assertFalse(pide_mostrar(tokenizar(frase)), frase)

    def test_confirmacion(self):
        for respuesta in ("Sí.", "sí, dale", "mandalo", "ok"):
            self.assertTrue(es_afirmacion(respuesta), respuesta)
        for respuesta in ("no", "no, cancelá", "¿qué?", ""):
            self.assertFalse(es_afirmacion(respuesta), respuesta)

    def test_reproducir_sin_plataforma(self):
        self.assertEqual(orden("Che Claudio, poné De música ligera"), [Accion("reproducir", "De música ligera")])

    def test_reproducir_con_plataforma_y_descriptor(self):
        self.assertEqual(orden("che claudio poneme la canción Persiana Americana en Spotify por favor"),
                         [Accion("reproducir", "Persiana Americana", "spotify")])
        self.assertEqual(orden("che claudio, poné algo de Queen en youtube"),
                         [Accion("reproducir", "Queen", "youtube")])
        self.assertEqual(orden("che claudio, poné el video de Despacito"),
                         [Accion("reproducir", "Despacito", "youtube")])

    def test_abrir_youtube_y_reproducir(self):
        self.assertEqual(orden("che claudio abrí youtube y poné lofi para estudiar"),
                         [Accion("reproducir", "lofi para estudiar", "youtube")])

    def test_abrir_varios(self):
        self.assertEqual(orden("che claudio, abrí youtube y spotify"),
                         [Accion("abrir", "youtube"), Accion("abrir", "spotify")])
        self.assertEqual(orden("che claudio, abrí la calculadora y después abrí el bloc de notas"),
                         [Accion("abrir", "calculadora"), Accion("abrir", "bloc de notas")])

    def test_abrir_en_segundo_plano(self):
        self.assertEqual(orden("che claudio, abrí discord en segundo plano"),
                         [Accion("abrir", "discord", segundo_plano=True)])

    def test_buscar(self):
        self.assertEqual(orden("che claudio, buscá recetas de empanadas"),
                         [Accion("buscar", "recetas de empanadas")])
        self.assertEqual(orden("che claudio, buscame en youtube tutoriales de python"),
                         [Accion("buscar", "tutoriales de python", "youtube")])
        self.assertEqual(orden("che claudio, abrí google y buscá el clima en Córdoba"),
                         [Accion("buscar", "el clima en Córdoba", "google")])

    def test_musica(self):
        casos = {
            "pausá la música": "pausar", "pará": "pausar", "poné pausa": "pausar",
            "seguí": "continuar", "poné música": "continuar", "dale play": "continuar",
            "siguiente": "siguiente", "poné la siguiente canción": "siguiente", "pasá de tema": "siguiente",
            "anterior": "anterior", "volvé a la anterior": "anterior", "tema anterior": "anterior",
        }
        for frase, tipo in casos.items():
            with self.subTest(frase):
                self.assertEqual(orden("che claudio, " + frase), [Accion(tipo)])

    def test_volumen(self):
        self.assertEqual(orden("che claudio, subí el volumen"), [Accion("volumen_relativo", valor=10)])
        self.assertEqual(orden("che claudio, bajá un poco el volumen"), [Accion("volumen_relativo", valor=-6)])
        self.assertEqual(orden("che claudio, poné el volumen al 50%"), [Accion("volumen", valor=50)])
        self.assertEqual(orden("che claudio, volumen al máximo"), [Accion("volumen", valor=100)])
        self.assertEqual(orden("che claudio, silenciá"), [Accion("silenciar")])

    def test_varias(self):
        self.assertEqual(orden("che claudio, qué hora es"), [Accion("hora")])
        self.assertEqual(orden("che claudio, qué día es hoy?"), [Accion("fecha")])
        self.assertEqual(orden("che claudio, cerrá spotify"), [Accion("cerrar", "spotify")])
        self.assertEqual(orden("che claudio, bloqueá la compu"), [Accion("bloquear")])
        self.assertEqual(orden("che claudio, chau"), [Accion("salir")])
        self.assertEqual(orden("che claudio, pausá la música y abrí youtube"),
                         [Accion("pausar"), Accion("abrir", "youtube")])
        self.assertEqual(orden("che claudio, qué hora es y qué día es hoy"), [Accion("hora"), Accion("fecha")])

    def test_preguntas_parecidas_a_la_hora_van_al_cerebro(self):
        # Caso real: contestaba la hora actual.
        self.assertEqual(orden("che claudio, ¿a qué hora termina este bloque?")[0].tipo, "desconocido")
        self.assertEqual(orden("che claudio, decime qué hora es"), [Accion("hora")])

    def test_mostrar_en_cualquier_parte(self):
        self.assertEqual(orden("che claudio, mostrame en pantalla YouTube"),
                         [Accion("abrir", "YouTube", segundo_plano=False)])
        self.assertEqual(orden("che claudio, abrí en pantalla la calculadora"),
                         [Accion("abrir", "calculadora", segundo_plano=False)])

    def test_seguir_lo_que_sonaba_en_un_lugar(self):
        self.assertEqual(orden("che claudio, cerrá spotify y poné la música en youtube"),
                         [Accion("cerrar", "spotify"), Accion("continuar", plataforma="youtube")])

    def test_desconocido(self):
        self.assertEqual(orden("che claudio, contame un chiste"), [Accion("desconocido", "contame un chiste")])

    def test_titulos_con_palabras_de_comando(self):
        self.assertEqual(orden("che claudio, poné Para no verte más"), [Accion("reproducir", "Para no verte más")])
        self.assertEqual(orden("che claudio, poné La Bamba"), [Accion("reproducir", "La Bamba")])


class CasosDelUsoRealTest(unittest.TestCase):
    """Frases tomadas del registro, tal como las escribió el reconocedor."""

    AHORA = datetime(2026, 10, 5, 19, 2)

    def orden(self, texto):
        return interpretar(separar_llamado(texto), self.AHORA)

    def test_avisame_cuando_sean(self):
        # Decía "Te aviso: Cuando sean".
        accion, = self.orden("Che Claudio, avísame cuando sean las 7 y 5.")
        self.assertEqual((accion.tipo, accion.objetivo), ("recordatorio", "Ya son las 7 y 5"))
        self.assertEqual(datetime.fromtimestamp(accion.valor), datetime(2026, 10, 5, 19, 5))
        accion, = self.orden("Claudio, avísame cuando sea a las 10 menos 5.")
        self.assertEqual((accion.objetivo, datetime.fromtimestamp(accion.valor).hour), ("Ya son las 9 y 55", 21))
        self.assertEqual(self.orden("Che Claudio, ¿me puede avisar cuando sean las 8 y media?")[0].objetivo,
                         "Ya son las 8 y media")

    def test_la_hora_antes_del_verbo(self):
        accion, = self.orden("Che Claudio, en cinco minutos recordadme que le tengo que escribir a Mirko.")
        self.assertEqual((accion.tipo, accion.objetivo), ("recordatorio", "Le tengo que escribir a Mirko"))
        self.assertEqual(datetime.fromtimestamp(accion.valor), datetime(2026, 10, 5, 19, 7))

    def test_cambiar_y_pausar_lo_que_suena(self):
        casos = {
            "cambia la música": Accion("siguiente"), "cámbiame de música por favor": Accion("siguiente"),
            "cambiame la música de Spotify": Accion("siguiente", plataforma="spotify"),
            "ponenle pausa al video de YouTube": Accion("pausar", plataforma="youtube"),
            "ponelo en pausa la música": Accion("pausar"),
            "poné la música de YouTube": Accion("continuar", plataforma="youtube"),
        }
        for frase, esperada in casos.items():
            with self.subTest(frase):
                self.assertEqual(self.orden("Che Claudio, " + frase), [esperada])

    def test_musica_sin_decir_cual_la_elige_el_cerebro(self):
        for frase in ("poneme una buena música", "poneme una música que le gustaría a Sofía", "poné lo que quieras",
                      "poné algo tranqui", "poneme una buena música de fondo con Spotify. Lo que vos quieras."):
            with self.subTest(frase):
                self.assertEqual(self.orden("Che Claudio, " + frase)[0].tipo, "musica_a_gusto")
        self.assertEqual(self.orden("Che Claudio, poné algo de Queen"), [Accion("reproducir", "Queen")])
        # Buscaba "en el Spotify" como si fuera el nombre de la canción.
        self.assertEqual(self.orden("Che Claudio, poneme una canción en el Spotify."),
                         [Accion("musica_a_gusto", "una canción", "spotify")])

    def test_pedido_de_musica_con_cola(self):
        # Buscaba "Don't Speak en Spotify por favor cámeme esto" y sonaba cualquier cosa.
        self.assertEqual(self.orden("Che Claudio, poneme Don't Speak en Spotify, por favor, cámeme esto."),
                         [Accion("reproducir", "Don't Speak", "spotify")])
        self.assertEqual(self.orden("Che Claudio, poneme Don't Speak en..."), [Accion("reproducir", "Don't Speak")])

    def test_poneme_a_secas_es_una_frase_cortada(self):
        self.assertEqual(self.orden("Che Claudio, poneme...")[0].tipo, "desconocido")  # antes reanudaba la música
        self.assertTrue(frase_cortada("Che Claudio, poneme..."))
        self.assertTrue(frase_cortada("Che Claudio, avísame cuando sean las"))
        self.assertFalse(frase_cortada("Che Claudio, abrí YouTube."))
        self.assertFalse(frase_cortada("Che Claudio, poné La Bamba"))

    def test_videos_de_youtube(self):
        self.assertEqual(
            self.orden("Che Claudio, abrime en otra pestaña el video de No sabía que esto pasa en España"),
            [Accion("reproducir", "No sabía que esto pasa en España", "youtube")])
        self.assertEqual(self.orden("Claudio, reproducidme el primer vídeo de desafío de Farfadox."),
                         [Accion("reproducir", "desafío de Farfadox", "youtube")])

    def test_abrir_sin_lo_que_sobra(self):
        self.assertEqual(self.orden("Che Claudio, abrí el navegador Brave."), [Accion("abrir", "Brave")])
        self.assertEqual(
            self.orden("Che Claudio, mostrame un bloc de notas para que me anote lo siguiente que te voy a decir."),
            [Accion("abrir", "bloc de notas", segundo_plano=False)])

    def test_la_hora_dicha_de_otra_forma(self):
        self.assertEqual(self.orden("Che Claudio, que horas son?"), [Accion("hora")])
        self.assertEqual(hora_hablada(datetime(2026, 10, 3, 16, 55), con_franja=True), "son las 4 y 55 de la tarde")
        self.assertEqual(hora_hablada(datetime(2026, 10, 3, 1, 30)), "es la 1 y media")

    def test_apagar_el_equipo(self):
        self.assertEqual(self.orden("Che Claudio, ¿podéis apagar mi computadora?"), [Accion("apagar")])
        self.assertEqual(self.orden("Che Claudio, reiniciá la compu"), [Accion("reiniciar")])
        self.assertEqual(self.orden("Che Claudio, cancelá el apagado"), [Accion("cancelar_apagado")])
        self.assertEqual(self.orden("Che Claudio, apagate"), [Accion("salir")])  # eso es apagar a Claudio

    def test_proyectos(self):
        self.assertEqual(
            self.orden("Che Claudio, ¿me podés levantar el proyecto a cancha libre para ver el front?"),
            [Accion("proyecto", "cancha libre", segundo_plano=False)])
        self.assertEqual(self.orden("Che Claudio, levantá cancha libre"), [Accion("proyecto", "cancha libre")])
        self.assertEqual(self.orden("Che Claudio, bajá el proyecto cancha libre"),
                         [Accion("proyecto_detener", "cancha libre")])
        self.assertEqual(self.orden("Che Claudio, levantá el volumen"), [Accion("volumen_relativo", valor=10)])

    def test_volumen_solo_de_spotify(self):
        self.assertEqual(self.orden("Che Claudio, subile un poquito a Spotify"),
                         [Accion("volumen_relativo", plataforma="spotify", valor=6)])
        self.assertEqual(self.orden("Che Claudio, poné el volumen de Spotify al 30"),
                         [Accion("volumen", plataforma="spotify", valor=30)])

    def test_nota_con_el_bloc_mal_escuchado(self):
        self.assertEqual(self.orden("Che Claudio, anotame en un plug de notas que mañana hay parcial")[0],
                         Accion("nota", "Mañana hay parcial"))

    def test_quiere_verlo(self):
        ofrecido = "Listo, Brave está abierto pero quedó minimizado. Decime si lo querés en pantalla."
        self.assertTrue(acepta_verlo(ofrecido, tokenizar("Ay, lo quiero en bandas ya.")))
        self.assertTrue(acepta_verlo(ofrecido, tokenizar("Sí, sí, ponelo, por favor.")))
        self.assertFalse(acepta_verlo(ofrecido, tokenizar("No, dejalo así.")))
        self.assertFalse(acepta_verlo("Son las cinco de la tarde.", tokenizar("sí, dale")))
        self.assertTrue(pide_mostrar(tokenizar("ponelo en batalla, por favor")))  # así oyó "en pantalla"


if __name__ == "__main__":
    unittest.main()

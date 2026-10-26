"""Pruebas del Módulo 3 (motor.py): corrección de la inferencia frente al oráculo y al mundo real.
Ejecutar:  python -m unittest pruebas_motor -v"""
import random
import unittest

import oraculo
from auxiliar_pruebas import asignacion_real, explorar_con_kb
from entorno import Entorno
from motor import ENCADENAMIENTO, RESOLUCION, Motor, Resultado
from wumpus_kb import M, BaseConocimiento, negar, simbolo

V, F, D = Resultado.VERDADERO, Resultado.FALSO, Resultado.DESCONOCIDO


def observaciones(kb, e):
    """Observaciones (para el oráculo) de las casillas visitadas, tal como las percibió el agente."""
    obs = []
    a = asignacion_real(e)
    for (i, j) in sorted(kb.casillas_visitadas):
        p = [n for n, s in (("Brisa", "B"), ("Hedor", "H"), ("Resplandor", "R")) if kb.valor_directo(simbolo(s, i, j))]
        obs.append(((i, j), p))
    return obs


class ConsultasBasicas(unittest.TestCase):
    def kb_con(self, *obs):
        kb = BaseConocimiento(4)
        for c, p in obs:
            kb.traducir_percepciones(c, p)
        return kb, Motor(kb)

    def test_inicio_sin_percepciones_vecinas_seguras(self):
        kb, m = self.kb_con(((1, 1), []))
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.es_seguro(2, 1, met)[0], V)
            self.assertEqual(m.es_seguro(1, 2, met)[0], V)
            self.assertEqual(m.es_seguro(3, 3, met)[0], D)          # desconocido ≠ falso
            self.assertEqual(m.hay_pozo(3, 3, met)[0], D)
            self.assertEqual(m.hay_pozo(2, 1, met)[0], F)
            self.assertEqual(m.hay_wumpus(2, 1, met)[0], F)

    def test_brisa_inicial_bloquea(self):
        kb, m = self.kb_con(((1, 1), ["Brisa"]))
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.es_seguro(2, 1, met)[0], D)
            self.assertEqual(m.es_seguro(1, 2, met)[0], D)
        self.assertEqual(m.casillas_seguras(), [(1, 1)])

    def test_pozo_demostrado(self):
        # brisa en (1,1) y (2,1) segura con ¬brisa... (2,1) visitada sin brisa → pozo en (1,2)
        kb, m = self.kb_con(((1, 1), ["Brisa"]), ((2, 1), []))
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.hay_pozo(1, 2, met)[0], V)
            self.assertEqual(m.es_seguro(1, 2, met)[0], F)
            self.assertEqual(m.es_seguro(3, 1, met)[0], V)

    def test_wumpus_demostrado_y_seguridad_falsa_hasta_el_grito(self):
        kb, m = self.kb_con(((1, 1), ["Hedor"]), ((2, 1), []))
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.hay_wumpus(1, 2, met)[0], V)
            self.assertEqual(m.es_seguro(1, 2, met)[0], F)
        kb.traducir_percepciones((2, 1), ["Grito"])                   # el Wumpus muere
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.hay_wumpus(1, 2, met)[0], V)           # «estaba» allí
            self.assertEqual(m.es_seguro(1, 2, met)[0], V)            # muerto: ya no es peligro (y no hay pozo)

    def test_el_grito_vuelve_segura_la_casilla_del_wumpus(self):
        kb, m = self.kb_con(((1, 1), ["Hedor"]))
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.es_seguro(2, 1, met)[0], D)            # el Wumpus podría estar allí
            self.assertEqual(m.hay_wumpus(2, 1, met)[0], D)
        kb.traducir_percepciones((1, 1), ["Grito"])
        for met in (RESOLUCION, ENCADENAMIENTO):
            self.assertEqual(m.es_seguro(2, 1, met)[0], V)
            self.assertEqual(m.es_seguro(1, 2, met)[0], V)

    def test_razonamiento_por_casos(self):
        # (2,1) con brisa y hedor: pozo ∈ {(3,1),(2,2)} y Wumpus ∈ {(3,1),(2,2)}; como no pueden coincidir
        # (un peligro por casilla), una es pozo y la otra Wumpus: AMBAS son peligrosas, aunque ninguna se
        # pueda señalar como «el pozo» o «el Wumpus». Sólo la resolución llega ahí (razona por casos).
        kb, m = self.kb_con(((1, 1), []), ((2, 1), ["Brisa", "Hedor"]))
        self.assertEqual(m.es_seguro(3, 1)[0], F)
        self.assertEqual(m.es_seguro(2, 2)[0], F)
        self.assertEqual(m.hay_pozo(3, 1)[0], D)
        self.assertEqual(m.hay_wumpus(3, 1)[0], D)
        r, _ = m.consultar_clausula(["P_3_1", "P_2_2"])
        self.assertEqual(r, V)
        self.assertEqual(m.es_seguro(3, 1, ENCADENAMIENTO)[0], D)      # encadenamiento: no alcanza

    def test_la_traza_de_una_demostracion_incluye_premisas_y_pasos(self):
        kb, m = self.kb_con(((1, 1), []))
        r, tr = m.es_seguro(2, 1)
        self.assertEqual(r, V)
        self.assertTrue(tr.premisas and tr.pasos)
        self.assertIn("□", tr.texto())
        self.assertTrue(any(e == "c365" or e.startswith("c") for e, _, _ in tr.premisas))
        r, tr = m.es_seguro(2, 1, ENCADENAMIENTO)
        self.assertTrue(any("→" in p for p in tr.pasos))

    def test_clausula_disyuntiva(self):
        kb, m = self.kb_con(((1, 1), ["Hedor"]))
        r, _ = m.consultar_clausula(["W_2_1", "W_1_2"], RESOLUCION)
        self.assertEqual(r, V)
        r, _ = m.consultar_clausula(["W_2_1", "W_1_2"], ENCADENAMIENTO)
        self.assertEqual(r, D)                                         # el encadenamiento no razona por casos
        self.assertEqual(m.hay_wumpus(2, 1)[0], D)

    def test_las_seis_consultas_obligatorias(self):
        kb, m = self.kb_con(((1, 1), []))
        self.assertIsInstance(m.casillas_seguras(), list)
        self.assertIsInstance(m.casillas_sospechosas(), list)
        self.assertIn("es_seguro(2,1)", m.explicacion_de_consulta(2, 1))
        self.assertEqual(m.hay_pozo(1, 1)[0], F)


class Contradicciones(unittest.TestCase):
    def test_se_detecta_y_no_se_usa_como_evidencia(self):
        kb = BaseConocimiento(4)
        m = Motor(kb)
        kb.traducir_percepciones((1, 1), [])
        self.assertTrue(m.es_consistente())
        kb.agregar_clausula("B_1_1", origen="observacion", categoria="Observación")   # brisa falsa: contradice ¬B_1_1
        for met in (RESOLUCION, ENCADENAMIENTO):
            r, tr = m.es_seguro(2, 1, met)
            self.assertEqual(r, D)
            self.assertTrue(tr.inconsistente)
        self.assertFalse(m.es_consistente())
        self.assertTrue(m.eventos_contradiccion)
        self.assertIn("□", m.eventos_contradiccion[0])

    def test_contradiccion_que_exige_propagar(self):
        kb = BaseConocimiento(4)
        m = Motor(kb)
        kb.traducir_percepciones((1, 1), [])                       # ¬B_1_1 ⇒ ¬P_2_1
        kb.agregar_clausula("P_2_1", origen="observacion", categoria="Observación")
        self.assertFalse(m.es_consistente())


class ContraElOraculo(unittest.TestCase):
    """La resolución debe coincidir EXACTAMENTE con el oráculo; el encadenamiento debe ser correcto (⊆)."""

    def comparar(self, e, kb, motor, vivo):
        n = e.n
        o = oraculo.consecuencias(n, observaciones(kb, e), wumpus_vivo=vivo, exclusion=True)
        self.assertFalse(o["inconsistente"])
        seguras = {c for c in kb.casillas() if motor.es_seguro(*c)[0] is V}
        peligrosas = {c for c in kb.casillas() if motor.es_seguro(*c)[0] is F}
        self.assertEqual(seguras, o["seguras"], f"seguras ≠ oráculo en semilla {e.semilla if hasattr(e,'semilla') else '?'}")
        self.assertEqual(peligrosas, o["peligro_cierto"])      # incluye peligro «por casos» (pozo o Wumpus)
        for c in kb.casillas():
            self.assertEqual(motor.hay_pozo(*c)[0] is V, c in o["pozo_cierto"])
            self.assertEqual(motor.hay_pozo(*c)[0] is F, c not in o["pozo_posible"])
            if vivo:
                self.assertEqual(motor.hay_wumpus(*c)[0] is V, o["wumpus_cierto"] == c)
                self.assertEqual(motor.hay_wumpus(*c)[0] is F, c not in o["wumpus_posible"])
        # encadenamiento: nunca afirma de más
        fc_seguras = {c for c in kb.casillas() if motor.es_seguro(*c, ENCADENAMIENTO)[0] is V}
        self.assertTrue(fc_seguras <= seguras)
        fc_peligro = {c for c in kb.casillas() if motor.es_seguro(*c, ENCADENAMIENTO)[0] is F}
        self.assertTrue(fc_peligro <= peligrosas)
        return len(seguras - fc_seguras), len(peligrosas - fc_peligro)

    def test_resolucion_igual_al_oraculo_en_mundos_aleatorios(self):
        rng = random.Random(99)
        perdidas_fc = [0, 0]
        comparaciones = grito = 0
        for k in range(45):
            e = Entorno(4, semilla=3000 + k, politica="aleatoria" if k % 3 == 0 else "ruta_segura")
            kb = BaseConocimiento(4)
            motor = Motor(kb)

            def revisar(paso):
                nonlocal comparaciones
                if paso % 4 == 0:
                    a, b = self.comparar(e, kb, motor, vivo=not kb.wumpus_muerto)
                    perdidas_fc[0] += a
                    perdidas_fc[1] += b
                    comparaciones += 1

            explorar_con_kb(e, kb, 24, rng, p_disparo=0.4, al_paso=revisar)
            grito += kb.wumpus_muerto
            self.assertEqual(motor.contradicciones(), [])
        self.assertGreater(comparaciones, 200)
        self.assertGreaterEqual(grito, 5, "debe cubrirse el caso del Wumpus muerto")
        print(f"\n  [{comparaciones} comparaciones; el encadenamiento dejó de demostrar "
              f"{perdidas_fc[0]} casillas seguras y {perdidas_fc[1]} peligrosas que la resolución sí]")

    def test_los_mundos_de_prueba(self):
        import glob, os
        rutas = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mundos", "m*.json")))
        rng = random.Random(5)
        for r in rutas:
            e = Entorno.cargar(r)
            if e.n != 4:
                continue
            kb = BaseConocimiento(4)
            motor = Motor(kb)
            explorar_con_kb(e, kb, 14, rng, al_paso=lambda p: self.comparar(e, kb, motor, vivo=not kb.wumpus_muerto)
                            if p % 3 == 0 else None)


class Memoria(unittest.TestCase):
    def test_resultado_demostrado_se_reutiliza_y_cuesta_cero(self):
        kb = BaseConocimiento(4)
        m = Motor(kb)
        kb.traducir_percepciones((1, 1), [])
        _, t1 = m.es_seguro(2, 1)
        _, t2 = m.es_seguro(2, 1)
        self.assertFalse(t1.desde_memoria)
        self.assertTrue(t2.desde_memoria)
        self.assertEqual(t2.esfuerzo, 0)

    def test_grito_invalida_lo_demostrado_bajo_mundo_cerrado(self):
        kb = BaseConocimiento(4)
        m = Motor(kb)
        kb.traducir_percepciones((1, 1), ["Hedor"])
        kb.traducir_percepciones((2, 1), [])
        self.assertEqual(m.es_seguro(1, 2)[0], F)
        kb.traducir_percepciones((2, 1), ["Grito"])
        self.assertNotEqual(m.es_seguro(1, 2)[0], F)


if __name__ == "__main__":
    unittest.main()

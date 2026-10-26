"""Pruebas del Módulo 2 (wumpus_kb.py). Ejecutar:  python -m unittest pruebas_kb -v"""
import ast
import os
import random
import unittest

from auxiliar_pruebas import clausulas_falsas, explorar_con_kb
from entorno import Entorno
from wumpus_kb import (CAT_SEGURA, M, BaseConocimiento, negar, simbolo)

AQUI = os.path.dirname(os.path.abspath(__file__))


class Axiomas(unittest.TestCase):
    def setUp(self):
        self.kb = BaseConocimiento(4)

    def test_tamano_y_categorias(self):
        r = self.kb.resumen()
        self.assertEqual(r["A1 inicio seguro"], 2)
        self.assertEqual(r["A2 brisa ⇔ pozo adyacente"], 64)       # 2·(#aristas dirigidas)=2·... 16 cláusulas largas + 48
        self.assertEqual(r["A4 resplandor ⇔ oro aquí"], 32)
        self.assertEqual(r["A5 un solo Wumpus"], 1 + 120)           # 1 «al menos uno» + C(16,2) «a lo sumo uno»
        self.assertEqual(r["A6 un peligro por casilla"], 16)
        self.assertEqual(r[CAT_SEGURA], 64)

    def test_sin_tautologias_ni_repetidas(self):
        self.assertEqual(len(self.kb.clausulas), len(set(self.kb.clausulas)))
        for c in self.kb.clausulas:
            self.assertFalse(any(negar(l) in c for l in c), c)

    def test_clausulas_ordenadas_y_con_origen(self):
        for c in self.kb.clausulas:
            self.assertEqual(c, tuple(sorted(c)))
            self.assertEqual(self.kb.info[c].origen, "regla")

    def test_resplandor_es_de_la_misma_casilla(self):
        self.assertIn(("O_2_3", "¬R_2_3"), self.kb)
        self.assertIn(("R_2_3", "¬O_2_3"), self.kb)
        self.assertNotIn(("R_2_3", "¬O_2_4"), self.kb)

    def test_brisa_vecinas_en_base_uno(self):
        self.assertIn(("¬B_1_1", "P_1_2", "P_2_1"), self.kb)       # esquina: 2 vecinas
        self.assertIn(("¬B_2_2", "P_1_2", "P_2_1", "P_2_3", "P_3_2"), self.kb)
        self.assertNotIn(("¬B_1_1", "P_0_1", "P_1_2", "P_2_1"), self.kb)

    def test_axioma_siete(self):
        for c in [("¬P_2_2", "¬S_2_2"), ("M", "¬S_2_2", "¬W_2_2"), ("P_2_2", "S_2_2", "W_2_2"), ("P_2_2", "S_2_2", "¬M")]:
            self.assertIn(c, self.kb)

    def test_unicidad_de_oro_opcional(self):
        self.assertEqual(BaseConocimiento(4).resumen().get("A5' un solo oro", 0), 0)
        self.assertEqual(BaseConocimiento(4, unicidad_oro=True).resumen()["A5' un solo oro"], 121)


class Traduccion(unittest.TestCase):
    def setUp(self):
        self.kb = BaseConocimiento(4)

    def literales(self):
        return {c[0] for c in self.kb.clausulas_de(origen="observacion", solo_unitarias=True)}

    def test_percepciones_presentes_y_ausentes(self):
        self.kb.traducir_percepciones((2, 1), ["Brisa", "Resplandor"])
        self.assertTrue({"V_2_1", "¬P_2_1", "¬W_2_1", "B_2_1", "¬H_2_1", "R_2_1"} <= self.literales())

    def test_golpe_no_describe_la_casilla(self):
        a = self.kb.traducir_percepciones((1, 1), ["Golpe"])
        self.assertTrue(any(p == "Golpe" for p, _ in a.ignoradas))
        self.assertNotIn("Golpe", " ".join(self.literales()))

    def test_percepcion_o_coordenada_invalida(self):
        with self.assertRaises(ValueError):
            self.kb.traducir_percepciones((1, 1), ["Aroma"])
        with self.assertRaises(ValueError):
            self.kb.traducir_percepciones((5, 1), [])
        with self.assertRaises(ValueError):
            self.kb.traducir_percepciones((1, 1), "Brisa")

    def test_repetir_la_observacion_no_duplica(self):
        self.kb.traducir_percepciones((1, 1), ["Hedor"])
        n = len(self.kb)
        a = self.kb.traducir_percepciones((1, 1), ["Hedor"])
        self.assertEqual(len(self.kb), n)
        self.assertEqual(a.nuevas, [])

    def test_grito_afirma_m_y_deja_de_registrar_hedor(self):
        self.kb.traducir_percepciones((1, 1), [])
        self.kb.traducir_percepciones((2, 1), ["Hedor"])
        self.kb.traducir_percepciones((2, 1), ["Grito"])
        self.assertTrue(self.kb.wumpus_muerto)
        self.kb.traducir_percepciones((3, 1), [])
        lits = self.literales()
        self.assertIn(M, lits)
        self.assertNotIn("¬H_3_1", lits)
        self.assertNotIn("¬W_3_1", lits)
        self.assertIn("¬P_3_1", lits)

    def test_oro_recogido_no_registra_ausencia_de_resplandor(self):
        self.kb.traducir_percepciones((2, 1), ["Resplandor"])
        self.kb.traducir_percepciones((2, 1), [])            # tras recoger
        self.assertNotIn("¬R_2_1", self.literales())

    def test_actualizacion_informa_lo_agregado(self):
        a = self.kb.traducir_percepciones((1, 1), ["Brisa"])
        self.assertEqual(a.casilla, (1, 1))
        self.assertGreater(a.total_despues, a.total_antes)
        self.assertEqual(self.kb.info[("B_1_1",)].origen, "observacion")


class ConsistenciaConElMundoReal(unittest.TestCase):
    def test_la_kb_nunca_contradice_el_mundo(self):
        """Cientos de mundos y recorridos aleatorios (con disparos): ninguna cláusula es falsa en el mundo real."""
        rng = random.Random(2024)
        grito, oro = 0, 0
        for k in range(300):
            e = Entorno(4, semilla=1000 + k, politica="aleatoria" if k % 3 == 0 else "ruta_segura")
            kb = BaseConocimiento(4)
            explorar_con_kb(e, kb, 40, rng, p_disparo=0.2,
                            al_paso=lambda _: self.assertEqual(clausulas_falsas(kb, e), []))
            grito += kb.wumpus_muerto
            oro += e.verdad()["oro"] in kb.casillas_visitadas
        self.assertGreater(grito, 20, "la prueba debe cubrir casos con Grito")
        self.assertGreater(oro, 20, "la prueba debe cubrir casos con oro visitado")

    def test_mundo_5x5(self):
        rng = random.Random(7)
        for k in range(30):
            e = Entorno(5, semilla=500 + k)
            kb = BaseConocimiento(5)
            explorar_con_kb(e, kb, 40, rng, p_disparo=0.2,
                            al_paso=lambda _: self.assertEqual(clausulas_falsas(kb, e), []))


class Aislamiento(unittest.TestCase):
    def test_la_kb_no_importa_el_simulador(self):
        with open(os.path.join(AQUI, "wumpus_kb.py"), encoding="utf-8") as f:
            arbol = ast.parse(f.read())
        mods = {n.names[0].name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import)}
        mods |= {n.module.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(mods & {"entorno", "oraculo", "referencia"}, mods)


if __name__ == "__main__":
    unittest.main()

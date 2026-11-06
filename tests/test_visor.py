"""Revisión estática de site/index.html: lee data.json, no trae datos incrustados y muestra estados claros."""
import re, unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / 'site' / 'index.html').read_text(encoding='utf-8')

class Visor(unittest.TestCase):
    def test_lee_data_json(self):
        self.assertIn("url:'./data.json'", HTML)
        self.assertIn("cache:'no-store'", HTML)

    def test_sin_registros_incrustados(self):
        self.assertNotIn('"registros":[', HTML)
        self.assertNotIn('"records":[', HTML)
        self.assertIn('<!--DATOS_LOCALES:', HTML)

    def test_mensajes_de_estado(self):
        for texto in ['Cargando los datos publicados', 'No se pudieron cargar los datos publicados', 'Aún no hay respuestas publicadas', 'Datos actualizados el']:
            self.assertIn(texto, HTML)

    def test_sin_campos_personales(self):
        for campo in ['informante', 'observaciones']:
            self.assertIsNone(re.search(r'\br\.' + campo + r'\b', HTML))

    def test_rotulos_aprobados(self):
        for texto in ['Aspectos para revisar y fortalecer', 'Respuestas por confirmar con la DMP', 'Propuesta declarada por la DMP', 'no es un compromiso acordado']:
            self.assertIn(texto, HTML)

if __name__ == '__main__':
    unittest.main()

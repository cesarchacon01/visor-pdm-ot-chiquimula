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
        for texto in ['Aspectos para revisar y fortalecer', 'Aspectos para aclarar durante el diálogo con la DMP', 'Propuesta declarada por la DMP', 'No constituye un compromiso acordado']:
            self.assertIn(texto, HTML)

    def test_fechas_y_zona_horaria(self):
        for texto in ['Fecha anotada en la boleta', 'Recibida en Kobo', 'Recepción en Kobo', 'hora de Guatemala', "timeZone:'America/Guatemala'"]:
            self.assertIn(texto, HTML)
        self.assertNotIn('Diagnóstico del ${', HTML)   # no se atribuye la fecha a un concepto no verificado

    def test_nota_de_control_con_detalle_plegado(self):
        self.assertIn('Detalle para auditoría', HTML)
        self.assertIn('<details class="aud">', HTML)

    def test_respuestas_por_confirmar_explicadas(self):
        for texto in ['Por qué conviene aclararlo', 'Pregunta sugerida', 'no es un error']:
            self.assertIn(texto, HTML)
        self.assertEqual(HTML.count("f.push({r:'"), 6)    # reglas A a F, sin agregar ni quitar

    def test_tarjetas_municipales_accesibles(self):
        for texto in ['Cómo leer las franjas', 'Ver ficha', 'Seleccionado', 'aria-pressed', 'class="sr"', 'data-tip=']:
            self.assertIn(texto, HTML)

    def test_orientaciones_para_el_dialogo(self):
        self.assertIn('Orientaciones para el diálogo técnico', HTML)
        self.assertIn('No son acuerdos, compromisos ni calificaciones de desempeño', HTML)
        self.assertIn('Respuestas en Kobo', HTML)                                      # declarado vs. interpretación
        self.assertIn('oportunidad para consolidar lo que ya funciona', HTML)
        self.assertIn("tema:['registro_seguimiento'],apoyo:['seguimiento']", HTML)   # E3: criterio 9 sin «Metas y resultados»
        self.assertNotIn("tema:['registro_seguimiento','metas']", HTML)
        self.assertNotIn('Pidió trabajar este tema', HTML)

    def test_sin_prototipo_y_aspectos_para_aclarar(self):
        self.assertNotIn('Prototipo', HTML)
        self.assertIn('Aspectos para aclarar durante el diálogo con la DMP', HTML)
        self.assertNotIn('Respuestas por confirmar con la DMP', HTML)
        self.assertIn('no son una evaluación ni una verificación institucional', HTML)

    def test_coordinacion_sin_compromisos(self):
        self.assertIn('Coincidencias para coordinar entre municipios', HTML)
        self.assertIn('no son acuerdos, compromisos ni asistencias aprobadas', HTML)
        for th in ['Tema relacionado', 'Municipios que necesitan fortalecimiento', 'Municipios que solicitaron el tema',
                   'Coincidencia entre diagnóstico y solicitud', 'En rojo, sin solicitar el tema', 'Cómo leer esta tabla']:
            self.assertIn(th, HTML)

    def test_ficha_imprimible_en_dos_paginas(self):
        self.assertIn('@page{size:letter', HTML)
        self.assertRegex(HTML, r'\.p2h{[^}]*break-before:page')
        self.assertNotIn('zoom:', HTML)                                               # sin reducir la ficha para forzar una página
        self.assertIn("'gestion_riesgo','uso_territorio'", HTML)                       # H2: cuatro tarjetas

    def test_criterios_compactos_en_telefono(self):
        self.assertIn('aria-expanded="${open}" aria-controls="cd-${c.k}"', HTML)   # botón accesible
        self.assertIn('.crit:not(.open) .cdet{display:none}', HTML)                # solo en teléfonos (media query)
        self.assertIn('grid-template-columns:1.25fr 1fr 1fr', HTML)                 # tres columnas en computadora

    def test_coincidencias_con_detalle_plegable(self):
        self.assertIn('<details class="cgd">', HTML)
        self.assertIn('oportunidades para explorar acciones conjuntas', HTML)

    def test_encabezado_en_ambas_paginas(self):
        self.assertIn('Página 1 de 2', HTML)
        self.assertIn('Página 2 de 2', HTML)


if __name__ == '__main__':
    unittest.main()

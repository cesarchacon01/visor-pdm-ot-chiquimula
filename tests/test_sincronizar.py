"""Pruebas del script de sincronización. No se conectan a Kobo: usan tests/fixtures/kobo_referencia.json,
una copia de las 11 respuestas del 6 de noviembre de 2026 en formato de la API, con datos personales ficticios.

Ejecutar desde la raíz del repositorio:  python -m unittest discover -s tests -v
"""
import copy, importlib.util, json, unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sincronizar_kobo', RAIZ / 'scripts' / 'sincronizar_kobo.py')
sk = importlib.util.module_from_spec(spec); spec.loader.exec_module(sk)
BASE = json.loads((RAIZ / 'tests' / 'fixtures' / 'kobo_referencia.json').read_text(encoding='utf-8'))


def fila(municipio, datos):
    return next(x for x in datos if x['datos_generales/municipio'] == municipio)


def registro(salida, municipio):
    return next((r for r in salida['records'] if r['municipio'] == municipio), None)


class Referencia(unittest.TestCase):
    """Con la exportación de referencia deben salir las cifras conciliadas."""
    def setUp(self):
        self.salida = sk.construir(copy.deepcopy(BASE))

    def test_once_municipios_una_vez(self):
        munis = [r['municipio'] for r in self.salida['records']]
        self.assertEqual(len(munis), 11)
        self.assertEqual(len(set(munis)), 11)

    def test_noventa_y_nueve_valoraciones(self):
        v = self.salida['meta']['valoraciones']
        self.assertEqual(v, {'verde': 29, 'amarillo': 49, 'rojo': 12, 'sin_informacion': 9})
        self.assertEqual(sum(v.values()), 99)

    def test_sin_omitidos_ni_duplicados(self):
        self.assertEqual(self.salida['omitted'], 0)
        self.assertEqual(self.salida['meta']['duplicados'], [])

    def test_multiseleccion(self):
        r = registro(self.salida, 'ipala')
        self.assertEqual(r['oficinas'], ['ugam', 'dmm'])
        self.assertEqual(registro(self.salida, 'esquipulas')['medios_metas'], ['excel', 'pei_pom_poa', 'plataforma'])

    def test_condicionada_vacia_no_es_negativa(self):
        r = registro(self.salida, 'camotan')       # sin registro de metas: no contesta el contenido
        self.assertEqual(r['contenido_metas'], [])
        self.assertIsNone(registro(self.salida, 'jocotan')['anio_aprobacion'])

    def test_textos_revisados_publicados(self):
        self.assertEqual(registro(self.salida, 'concepcion_las_minas')['accion_prioritaria'], 'Ordenamiento territorial')
        self.assertEqual(registro(self.salida, 'olopa')['coordina'], 'DMP')
        self.assertTrue(registro(self.salida, 'san_juan_ermita')['texto_corregido'])
        self.assertEqual(self.salida['meta']['textos_pendientes'], [])

    def test_nota_de_control_chiquimula(self):
        notas = self.salida['meta']['notas_control']
        self.assertTrue(any(n['municipio'] == 'chiquimula' for n in notas))


class Privacidad(unittest.TestCase):
    def test_no_publica_datos_personales(self):
        salida = sk.construir(copy.deepcopy(BASE))
        texto = json.dumps(salida, ensure_ascii=False)
        for prohibido in ['PERSONA DE PRUEBA', 'CARGO DE PRUEBA', 'OBSERVACION DE PRUEBA', 'prueba-0', 'Director DMP']:
            self.assertNotIn(prohibido, texto)
        for r in salida['records']:
            for clave in ['informante', 'cargo', 'observaciones', '_id', '_uuid', 'rootUuid', '_submitted_by']:
                self.assertNotIn(clave, r)


class CambiosEnKobo(unittest.TestCase):
    """Simula registros nuevos, modificaciones y eliminaciones en Kobo."""
    def test_eliminacion_no_conserva_datos_anteriores(self):
        datos = [x for x in copy.deepcopy(BASE) if x['datos_generales/municipio'] != 'ipala']
        salida = sk.construir(datos)
        self.assertIsNone(registro(salida, 'ipala'))
        self.assertEqual(salida['meta']['publicados'], 10)
        self.assertEqual(sum(salida['meta']['valoraciones'].values()), 90)

    def test_modificacion_de_semaforo(self):
        datos = copy.deepcopy(BASE)
        fila('olopa', datos)['semaforo/gestion_riesgo'] = 'verde'
        salida = sk.construir(datos)
        self.assertEqual(registro(salida, 'olopa')['gestion_riesgo'], 'verde')
        self.assertEqual(salida['meta']['valoraciones']['verde'], 30)

    def test_registro_nuevo_mas_reciente_reemplaza(self):
        datos = copy.deepcopy(BASE)
        nuevo = copy.deepcopy(fila('camotan', datos))
        nuevo.update({'_uuid': 'prueba-nuevo', '_submission_time': '2026-12-01T10:00:00', 'semaforo/seguimiento': 'verde'})
        datos.append(nuevo)
        salida = sk.construir(datos)
        self.assertEqual(len(salida['records']), 11)
        self.assertEqual(registro(salida, 'camotan')['seguimiento'], 'verde')
        self.assertEqual(salida['meta']['duplicados'], [{'municipio': 'camotan', 'descartados': 1}])

    def test_duplicado_anterior_no_reemplaza(self):
        datos = copy.deepcopy(BASE)
        viejo = copy.deepcopy(fila('camotan', datos))
        viejo.update({'_uuid': 'prueba-viejo', '_submission_time': '2026-09-01T10:00:00', 'semaforo/seguimiento': 'verde'})
        datos.append(viejo)
        self.assertEqual(registro(sk.construir(datos), 'camotan')['seguimiento'], 'amarillo')

    def test_texto_libre_modificado_queda_en_revision(self):
        datos = copy.deepcopy(BASE)
        fila('esquipulas', datos)['acompanamiento/accion_prioritaria'] = 'Reunión con Juan Pérez, tel. 5555-0000'
        salida = sk.construir(datos)
        r = registro(salida, 'esquipulas')
        self.assertIsNone(r['accion_prioritaria'])
        self.assertIn('accion', r['textos_pendientes'])
        publicado = {k: v for k, v in salida.items() if k != '_huellas_pendientes'}
        self.assertNotIn('Juan Pérez', json.dumps(salida, ensure_ascii=False))
        self.assertEqual(salida['_huellas_pendientes'][0]['campo'], 'accion')
        self.assertEqual(len(salida['_huellas_pendientes'][0]['huella']), 64)
        self.assertNotIn('_huellas_pendientes', json.dumps(publicado['records']))

    def test_espacios_extra_no_cambian_el_texto(self):
        datos = copy.deepcopy(BASE)
        fila('ipala', datos)['acompanamiento/accion_prioritaria'] = '  Por   definir '
        self.assertEqual(registro(sk.construir(datos), 'ipala')['accion_prioritaria'], 'Por definir')

    def test_respuesta_no_aprobada_se_excluye(self):
        datos = copy.deepcopy(BASE)
        fila('jocotan', datos)['_validation_status'] = {'uid': 'validation_status_not_approved'}
        salida = sk.construir(datos)
        self.assertIsNone(registro(salida, 'jocotan'))
        self.assertEqual(salida['meta']['omitidos'], {'no_aprobada_en_kobo': 1})

    def test_municipio_fuera_de_catalogo_se_omite(self):
        datos = copy.deepcopy(BASE) + [{'datos_generales/municipio': 'zacapa', '_submission_time': '2026-11-01T00:00:00'}]
        salida = sk.construir(datos)
        self.assertEqual(salida['omitted'], 1)
        self.assertEqual(len(salida['records']), 11)

    def test_valor_fuera_de_catalogo_no_se_publica(self):
        datos = copy.deepcopy(BASE)
        fila('olopa', datos)['semaforo/seguimiento'] = 'morado'
        self.assertEqual(registro(sk.construir(datos), 'olopa')['seguimiento'], '')


class TextosEnRepositorio(unittest.TestCase):
    def test_el_repositorio_no_guarda_textos_originales(self):
        textos = json.loads((RAIZ / 'scripts' / 'textos_publicables.json').read_text(encoding='utf-8'))
        for campos in textos['textos'].values():
            for v in campos.values():
                self.assertEqual(set(v), {'huella', 'publicado'})
        bruto = (RAIZ / 'scripts' / 'textos_publicables.json').read_text(encoding='utf-8')
        self.assertNotIn('Director DMP', bruto)
        self.assertNotIn('terriotorial', bruto)


class CargaVacia(unittest.TestCase):
    def test_sin_respuestas_falla(self):
        with self.assertRaises(ValueError):
            sk.construir([])

    def test_sin_municipios_validos_falla(self):
        with self.assertRaises(ValueError):
            sk.construir([{'datos_generales/municipio': 'zacapa'}])


if __name__ == '__main__':
    unittest.main()

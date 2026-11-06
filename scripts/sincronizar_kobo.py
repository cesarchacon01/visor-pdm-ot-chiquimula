"""Sincroniza el Diagnóstico rápido del PDM-OT desde KoboToolbox y escribe el data.json público.

Reglas de publicación:
- Solo se publica una lista cerrada de campos, con valores que existan en scripts/opciones.json.
- Nunca se publican el nombre de quien responde, su cargo, las observaciones ni identificadores
  de Kobo (_id, _uuid, rootUuid, _submitted_by).
- Los textos libres (acción prioritaria, oficina que la coordinaría y ejemplo de registro) solo se
  publican si su huella SHA-256 coincide con un texto revisado en scripts/textos_publicables.json.
  El repositorio guarda la huella y la versión revisada, nunca el texto original. Si no coinciden,
  se marcan como "en revisión", no se publica su contenido y el registro muestra solo la huella.
- Se publica una sola respuesta por municipio: la más reciente según _submission_time.
- Las respuestas marcadas en Kobo como «No aprobado» no se publican.
- El archivo se reconstruye completo en cada ejecución: lo que se elimina o cambia en Kobo
  desaparece o cambia en el visor, sin conservar datos anteriores.
- Si Kobo no devuelve respuestas válidas, el script termina con error y no escribe el archivo,
  para que la Action no publique una carga vacía.

Uso:
  python scripts/sincronizar_kobo.py                      # escribe site/data.json (uso de la Action)
  python scripts/sincronizar_kobo.py --salida prueba/data.json
"""
import json, os, re, sys, argparse, hashlib
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse, urljoin

BASE = Path(__file__).resolve().parent
SCHEMA = json.loads((BASE / 'opciones.json').read_text(encoding='utf-8'))
TEXTOS = json.loads((BASE / 'textos_publicables.json').read_text(encoding='utf-8'))

# Campo de Kobo (nombre XML) -> (nombre en data.json, lista de opciones)
UNICA = {
    'municipio': ('municipio', 'municipios'),
    'conoce_anio': ('conoce_anio', 'si_no_ns'),
    'en_actualizacion': ('en_actualizacion', 'si_no_ns'),
    'datos_actuales': ('datos_actuales', 'semaforo'),
    'prioridades': ('prioridades', 'semaforo'),
    'gestion_riesgo': ('gestion_riesgo', 'semaforo'),
    'metas_medibles': ('metas_medibles', 'semaforo'),
    'registro_metas': ('registro_metas', 'semaforo'),
    'uso_planificacion': ('uso_planificacion', 'semaforo'),
    'uso_inversion': ('uso_inversion', 'semaforo'),
    'uso_territorio': ('uso_territorio', 'semaforo'),
    'seguimiento': ('seguimiento', 'semaforo'),
    'frecuencia_revision': ('frecuencia_revision', 'frecuencia'),
    'necesidad': ('necesidad', 'necesidad_principal'),
    'modalidad': ('modalidad', 'modalidades'),
    'plazo_inicio': ('plazo', 'plazos'),
}
MULTIPLE = {
    'oficinas_existentes': ('oficinas', 'oficinas'),
    'medios_metas': ('medios_metas', 'medios_registro'),
    'contenido_metas': ('contenido_metas', 'contenido_registro'),
    'temas_prioritarios': ('temas', 'temas'),
    'apoyos_requeridos': ('apoyos', 'apoyos'),
}
# Textos libres: campo de Kobo -> (nombre en data.json, clave en textos_publicables.json)
TEXTO_LIBRE = {
    'accion_prioritaria': ('accion_prioritaria', 'accion'),
    'responsable_propuesto': ('coordina', 'coordina'),
    'ejemplo_registro': ('ejemplo_registro', 'ejemplo'),
}
CRITERIOS = ['datos_actuales', 'prioridades', 'gestion_riesgo', 'metas_medibles', 'registro_metas',
             'uso_planificacion', 'uso_inversion', 'uso_territorio', 'seguimiento']
NO_PUBLICADOS = ['Nombre de quien responde', 'Cargo', 'Observaciones adicionales']
VALIDACION_EXCLUIDA = {'validation_status_not_approved'}


def _texto(v):
    """Normaliza espacios para comparar textos libres."""
    return ' '.join(str(v).split()) if v not in (None, '') else ''


def huella(v):
    """Huella SHA-256 del texto normalizado. Permite reconocer un texto revisado sin guardarlo."""
    return hashlib.sha256(_texto(v).encode('utf-8')).hexdigest()


def _plano(fila):
    """Quita los prefijos de grupo de Kobo (grupo/campo -> campo)."""
    return {k.split('/')[-1]: v for k, v in fila.items()}


def _fecha_iso(v):
    if not isinstance(v, str) or not v.strip():
        return ''
    try:
        return datetime.fromisoformat(v.strip().replace('Z', '+00:00')).isoformat()
    except ValueError:
        return ''


def _estado_validacion(v):
    if isinstance(v, dict):
        return v.get('uid') or ''
    return v if isinstance(v, str) else ''


def limpiar(fila):
    """Convierte una respuesta de Kobo en un registro público. Devuelve (registro, motivo_omision)."""
    plano = _plano(fila)
    municipio = plano.get('municipio')
    if municipio not in SCHEMA['municipios']:
        return None, 'municipio_no_valido'
    validacion = _estado_validacion(plano.get('_validation_status'))
    if validacion in VALIDACION_EXCLUIDA:
        return None, 'no_aprobada_en_kobo'

    r = {'municipio': municipio,
         'fecha': (_fecha_iso(plano.get('fecha')) or '')[:10],
         'enviado': _fecha_iso(plano.get('_submission_time')),
         'validacion': validacion}
    for campo, (destino, lista) in UNICA.items():
        if campo == 'municipio':
            continue
        valor = plano.get(campo, '')
        r[destino] = valor if isinstance(valor, str) and valor in SCHEMA[lista] else ''
    for campo, (destino, lista) in MULTIPLE.items():
        valor = plano.get(campo, '')
        valores = valor if isinstance(valor, list) else str(valor or '').split()
        r[destino] = list(dict.fromkeys(v for v in valores if isinstance(v, str) and v in SCHEMA[lista]))

    anio = str(plano.get('anio_aprobacion', '') or '').strip()
    r['anio_aprobacion'] = int(anio) if anio.isdigit() and 1990 <= int(anio) <= datetime.now(timezone.utc).year else None

    # Textos libres: solo los revisados
    revisados = TEXTOS.get('textos', {}).get(municipio, {})
    pendientes, corregido, r['_huellas_pendientes'] = [], False, {}
    for campo, (destino, clave) in TEXTO_LIBRE.items():
        recibido = _texto(plano.get(campo))
        r[destino] = None
        if not recibido:
            continue
        aprobado = revisados.get(clave)
        if aprobado and aprobado.get('huella') == huella(recibido):
            r[destino] = aprobado.get('publicado')
            corregido = corregido or (_texto(aprobado.get('publicado')) != recibido)
        else:
            pendientes.append(clave)
            r['_huellas_pendientes'][clave] = huella(recibido)
    r['textos_pendientes'] = pendientes
    r['texto_corregido'] = corregido
    return r, None


def construir(respuestas, ahora=None):
    """Construye el contenido completo de data.json a partir de las respuestas de Kobo.
    Lanza ValueError si no hay ninguna respuesta válida (no se debe publicar una carga vacía)."""
    if not respuestas:
        raise ValueError('Kobo no devolvió respuestas; no se publica una carga vacía')
    omitidos, por_municipio, versiones = {}, {}, set()
    for fila in respuestas:
        registro, motivo = limpiar(fila)
        if motivo:
            omitidos[motivo] = omitidos.get(motivo, 0) + 1
            continue
        versiones.add(str(_plano(fila).get('__version__') or ''))
        por_municipio.setdefault(registro['municipio'], []).append(registro)
    if not por_municipio:
        raise ValueError('Ninguna respuesta tiene un municipio válido; revise el formulario y opciones.json')

    registros, duplicados = [], []
    for municipio in SCHEMA['municipios']:
        lista = por_municipio.get(municipio)
        if not lista:
            continue
        lista.sort(key=lambda x: x['enviado'])
        registros.append(lista[-1])  # la más reciente
        if len(lista) > 1:
            duplicados.append({'municipio': municipio, 'descartados': len(lista) - 1})

    huellas = [{'municipio': r['municipio'], 'campo': c, 'huella': h}
               for r in registros for c, h in r.pop('_huellas_pendientes').items()]
    for lista in por_municipio.values():          # quita el dato interno también de los descartados
        for r in lista:
            r.pop('_huellas_pendientes', None)
    valoraciones = {k: 0 for k in SCHEMA['semaforo']}
    for r in registros:
        for c in CRITERIOS:
            if r[c] in valoraciones:
                valoraciones[r[c]] += 1

    ahora = ahora or datetime.now(timezone.utc)
    return {
        'updated_at': ahora.isoformat(),
        'records': registros,
        'omitted': sum(omitidos.values()),
        'public_fields_only': True,
        'meta': {
            'fuente': 'KoboToolbox · Diagnóstico rápido del PDM-OT',
            'recibidos': len(respuestas),
            'publicados': len(registros),
            'omitidos': omitidos,
            'duplicados': duplicados,
            'valoraciones': valoraciones,
            'versiones_formulario': sorted(v for v in versiones if v),
            'campos_no_publicados': NO_PUBLICADOS,
            'textos_revisados': {'fecha': TEXTOS.get('revisado'), 'criterio': TEXTOS.get('criterio')},
            'textos_pendientes': [{'municipio': r['municipio'], 'campos': r['textos_pendientes']}
                                  for r in registros if r['textos_pendientes']],
            'notas_control': TEXTOS.get('notas_control', []),
        },
        '_huellas_pendientes': huellas,   # solo para el registro de la ejecución; no se escribe en data.json
    }


class SinRedireccion(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def descargar(servidor, uid, token):
    endpoint = f'{servidor}/api/v2/assets/{uid}/data/'
    url = endpoint + '?limit=1000'
    opener = build_opener(SinRedireccion())
    vistos, resultados = set(), []
    while url:
        if url in vistos or len(vistos) > 1000:
            raise ValueError('Paginación inválida')
        p = urlparse(url)
        if p.scheme != 'https' or p.netloc != urlparse(servidor).netloc or p.path.rstrip('/') != urlparse(endpoint).path.rstrip('/'):
            raise ValueError('URL de paginación no válida')
        vistos.add(url)
        with opener.open(Request(url, headers={'Authorization': 'Token ' + token, 'Accept': 'application/json'}), timeout=60) as resp:
            pagina = json.load(resp)
        if not isinstance(pagina, dict) or not isinstance(pagina.get('results'), list):
            raise ValueError('Respuesta de la API no válida')
        resultados.extend(pagina['results'])
        url = urljoin(servidor, pagina['next']) if pagina.get('next') else None
    return resultados


def escribir(datos, salida):
    destino = Path(salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    temporal.replace(destino)


def main(argv=None):
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument('--salida', default='site/data.json')
    opciones = args.parse_args(argv)
    servidor = os.environ.get('KOBO_SERVER', '').strip().rstrip('/')
    uid = os.environ.get('KOBO_ASSET_UID', '').strip()
    token = os.environ.get('KOBO_TOKEN', '').strip()
    if servidor not in {'https://eu.kobotoolbox.org', 'https://kf.kobotoolbox.org'} or not re.fullmatch(r'[A-Za-z0-9]+', uid) or not token:
        raise ValueError('Revise los tres secretos de Kobo')
    datos = construir(descargar(servidor, uid, token))
    huellas = datos.pop('_huellas_pendientes')
    escribir(datos, opciones.salida)
    m = datos['meta']
    print(f"Sincronización completa: {m['publicados']} respuestas publicadas; {datos['omitted']} omitidas.")
    print(f"Recibidas de Kobo: {m['recibidos']} · duplicados descartados: {sum(d['descartados'] for d in m['duplicados'])} · "
          f"valoraciones: {m['valoraciones']} · textos en revisión: {len(huellas)}")
    for h in huellas:
        print(f"Texto en revisión · {h['municipio']} · {h['campo']} · huella {h['huella']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'No se completó la sincronización ({type(e).__name__}: {e}). No se publicará una nueva versión.', file=sys.stderr)
        sys.exit(1)

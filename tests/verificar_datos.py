"""Revisa un data.json generado y lo compara con una referencia.

Uso:
  python tests/verificar_datos.py prueba/data.json
  python tests/verificar_datos.py prueba/data.json --referencia 11,29,49,12,9

La referencia es: municipios, verde, amarillo, rojo, sin información.
Sin --referencia solo revisa la estructura y la privacidad, y muestra los conteos.
Termina con código 1 si encuentra un problema.
"""
import argparse, json, sys
from pathlib import Path

CRIT = ['datos_actuales', 'prioridades', 'gestion_riesgo', 'metas_medibles', 'registro_metas',
        'uso_planificacion', 'uso_inversion', 'uso_territorio', 'seguimiento']
PROHIBIDAS = {'informante', 'cargo', 'observaciones', '_id', '_uuid', 'rootUuid', '_submitted_by'}

a = argparse.ArgumentParser()
a.add_argument('archivo')
a.add_argument('--referencia')
op = a.parse_args()
d = json.loads(Path(op.archivo).read_text(encoding='utf-8'))
problemas = []
reg = d.get('records') or []
munis = [r.get('municipio') for r in reg]
if not reg: problemas.append('El archivo no tiene registros')
if len(munis) != len(set(munis)): problemas.append('Hay municipios repetidos')
for r in reg:
    claves = PROHIBIDAS & set(r)
    if claves: problemas.append(f"{r.get('municipio')}: campos que no deben publicarse {sorted(claves)}")
c = {'verde': 0, 'amarillo': 0, 'rojo': 0, 'sin_informacion': 0, 'otro': 0}
for r in reg:
    for k in CRIT:
        c[r.get(k) if r.get(k) in c else 'otro'] += 1
print(f"Actualizado: {d.get('updated_at')}")
print(f"Municipios: {len(reg)} · valoraciones: {sum(c.values())} · verde {c['verde']} · amarillo {c['amarillo']} · rojo {c['rojo']} · sin información {c['sin_informacion']} · vacías u otras {c['otro']}")
pend = (d.get('meta') or {}).get('textos_pendientes') or []
if pend: print('Textos en revisión:', pend)
if op.referencia:
    m, v, am, ro, si = [int(x) for x in op.referencia.split(',')]
    esperado = (m, v, am, ro, si); obtenido = (len(reg), c['verde'], c['amarillo'], c['rojo'], c['sin_informacion'])
    if esperado != obtenido:
        problemas.append(f'No coincide con la referencia: esperado {esperado}, obtenido {obtenido}. '
                         'Si hubo respuestas nuevas, modificadas o eliminadas en Kobo, actualice la referencia.')
for p in problemas: print('PROBLEMA:', p)
sys.exit(1 if problemas else 0)

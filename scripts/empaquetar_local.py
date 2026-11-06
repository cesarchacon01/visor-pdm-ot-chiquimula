"""Crea una copia del visor con los datos incluidos, para revisarla sin servidor (doble clic).

Uso:
  python scripts/empaquetar_local.py site/index.html prueba/data.json prueba/vista-local.html

No se usa en la publicación: GitHub Pages sirve site/index.html, que lee data.json.
"""
import json, sys
from pathlib import Path

MARCA = '<!--DATOS_LOCALES:'

def main(visor, datos, salida):
    html = Path(visor).read_text(encoding='utf-8')
    inicio = html.find(MARCA)
    if inicio < 0:
        raise SystemExit('No se encontró la marca DATOS_LOCALES en el visor')
    fin = html.find('-->', inicio) + 3
    contenido = json.loads(Path(datos).read_text(encoding='utf-8'))
    bloque = '<script>window.PDMOT_DATOS_LOCALES=' + json.dumps(contenido, ensure_ascii=False).replace('</', '<\\/') + ';</script>'
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(html[:inicio] + bloque + html[fin:], encoding='utf-8')
    print(f'Vista local creada: {salida}')

if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])

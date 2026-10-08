"""Publica solo campos cerrados del diagnóstico. Nunca escribe respuestas crudas."""
import json, os, re, sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlparse, urljoin

FIELDS = {
 'municipio':'municipios', 'en_actualizacion':'si_no_ns',
 'datos_actuales':'semaforo','prioridades':'semaforo','gestion_riesgo':'semaforo',
 'metas_medibles':'semaforo','registro_metas':'semaforo','uso_planificacion':'semaforo',
 'uso_inversion':'semaforo','uso_territorio':'semaforo','seguimiento':'semaforo',
 'necesidad':'necesidad_principal','medios_metas':'medios_registro',
 'contenido_metas':'contenido_registro','frecuencia_revision':'frecuencia',
 'temas_prioritarios':'temas','apoyos_requeridos':'apoyos',
 'modalidad':'modalidades','plazo_inicio':'plazos'
}
MULTI={'medios_metas','contenido_metas','temas_prioritarios','apoyos_requeridos'}
SCHEMA=json.loads(Path(__file__).with_name('opciones.json').read_text(encoding='utf-8'))

def clean(row):
    flat={k.split('/')[-1]:v for k,v in row.items()}
    if flat.get('municipio') not in SCHEMA['municipios']: return None
    result={}
    for key, choices in FIELDS.items():
        value=flat.get(key,'')
        if key in MULTI:
            vals=value if isinstance(value,list) else str(value).split()
            result[key]=list(dict.fromkeys(v for v in vals if isinstance(v,str) and v in SCHEMA[choices]))
        else: result[key]=value if isinstance(value,str) and value in SCHEMA[choices] else ''
    year=str(flat.get('anio_aprobacion',''))
    if year.isdigit() and 2000<=int(year)<=datetime.now(timezone.utc).year: result['anio_aprobacion']=int(year)
    for key in ['fecha','_submission_time','fin']:
        val=flat.get(key)
        if isinstance(val,str):
            try:
                dt=datetime.fromisoformat(val.replace('Z','+00:00'))
                result[key]=dt.isoformat()
            except ValueError: pass
    return result

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def fetch_all(server, uid, token):
    endpoint=f'{server}/api/v2/assets/{uid}/data/'
    url=endpoint+'?limit=1000'
    opener=build_opener(NoRedirect())
    seen=set(); results=[]
    while url:
        if url in seen or len(seen)>1000: raise ValueError('Paginación inválida')
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.netloc!=urlparse(server).netloc or parsed.path.rstrip('/')!=urlparse(endpoint).path.rstrip('/'):
            raise ValueError('URL de paginación no válida')
        seen.add(url)
        with opener.open(Request(url,headers={'Authorization':'Token '+token,'Accept':'application/json'}),timeout=60) as response:
            page=json.load(response)
        if not isinstance(page,dict) or not isinstance(page.get('results'),list): raise ValueError('Respuesta API no válida')
        results.extend(page['results'])
        url=urljoin(server,page['next']) if page.get('next') else None
    return results

def main():
    server=os.environ.get('KOBO_SERVER','').strip().rstrip('/')
    uid=os.environ.get('KOBO_ASSET_UID','').strip()
    token=os.environ.get('KOBO_TOKEN','').strip()
    if server not in {'https://eu.kobotoolbox.org','https://kf.kobotoolbox.org'} or not re.fullmatch(r'[A-Za-z0-9]+',uid) or not token:
        raise ValueError('Revise los tres secretos de Kobo')
    raw=fetch_all(server,uid,token)
    rows=[r for item in raw if (r:=clean(item)) is not None]
    if raw and not rows: raise ValueError('No se reconoció ningún municipio; revise las variables del formulario')
    data={'updated_at':datetime.now(timezone.utc).isoformat(),'records':rows,'omitted':len(raw)-len(rows),'public_fields_only':True}
    target=Path('site/data.json');target.parent.mkdir(exist_ok=True)
    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');tmp.replace(target)
    print(f'Sincronización completa: {len(rows)} respuestas publicadas; {len(raw)-len(rows)} omitidas.')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'No se completó la sincronización ({type(e).__name__}). Revise los secretos y el acceso al proyecto. No se publicará una nueva versión.',file=sys.stderr)
        sys.exit(1)

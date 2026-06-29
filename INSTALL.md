# Instalación portable - Proyecto D

Esta versión del repositorio está preparada para clonarse fuera del VPS original sin depender de rutas fijas de `/root/.openclaw/workspace/...`.

## 1. Requisitos

- Python 3.11+
- acceso a ClickUp API
- opcional: Supabase para trazabilidad
- OpenClaw si vas a usar el watcher contra sesiones reales de WhatsApp/OpenClaw

## 2. Clonar y preparar archivos locales

```bash
git clone https://github.com/luiscampos-evinka/proyecto-d.git
cd proyecto-d
mkdir -p secrets state
cp config/config.example.json config/config.json
cp config/proyecto_d_supabase.env.example config/proyecto_d_supabase.env
```

## 3. Completar secretos y configuración

### ClickUp token
Guardar el token en:

```text
secrets/proyecto_d_clickup_token
```

### Configuración principal
Editar:

```text
config/config.json
```

Campos mínimos:
- `clickup.list_id`
- `routing.allowed_senders`
- `supabase.*` si usarás trazabilidad

### Supabase opcional
Si usarás auditoría estructurada, completar:

```text
config/proyecto_d_supabase.env
```

## 4. Paths portables disponibles

El repo soporta estas variables de entorno:

- `PROYECTO_D_HOME`: cambia la raíz operativa del proyecto
- `PROYECTO_D_CONFIG`: apunta a otro `config.json`
- `PROYECTO_D_SESSION_ROOTS`: lista de roots de sesiones OpenClaw separadas por `:`

Además, `config/config.json` soporta un bloque `runtime` para sobreescribir:

- `watcher_state_path`
- `payload_dir`
- `router_script`
- `session_registry_roots`

## 5. Ejecución manual

### Probar router directamente

```bash
python3 src/router.py \
  --config config/config.json \
  --sender +51936005850 \
  --message-id test-001 \
  --body "📢 120 UTP BREÑA pasa a metrado y cotizaciones"
```

### Ejecutar watcher una sola vez

```bash
python3 src/whatsapp_watcher.py --once
```

### Ejecutar watcher en loop

```bash
python3 src/whatsapp_watcher.py --sleep-seconds 3
```

## 6. Cron sugerido

```bash
* * * * * cd /ruta/proyecto-d && /usr/bin/python3 src/whatsapp_watcher.py --once >> state/cron.log 2>&1
```

## 7. Fuente de verdad operativa

- ClickUp = destino principal de trabajo
- Supabase = trazabilidad opcional
- logs locales/state = soporte técnico local

## 8. Compatibilidad

La lógica operativa se mantiene igual; esta portableización solo cambia la forma de resolver rutas y configuración para que el repo pueda replicarse en otros entornos.

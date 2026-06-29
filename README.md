# Proyecto D

**Autor técnico / documentación:** OpenClaw  
**Canales y sistemas involucrados:** WhatsApp, ClickUp, Supabase, OpenClaw

## 1. Resumen ejecutivo

Proyecto D es una automatización operativa diseñada para leer mensajes de WhatsApp marcados con **📢** o **📣**, interpretarlos como eventos de avance de proyectos y sincronizarlos hacia **ClickUp** como creación o actualización de tareas. En paralelo, registra auditoría y trazabilidad en **Supabase** y en logs locales.

La solución nació porque el flujo original podía responder en chats donde no debía hacerlo o mezclar esta operación con otros frentes de EVINKA. Por eso se aisló en un módulo propio, con remitentes permitidos, reglas de activación explícitas y salida visible silenciosa (`NO_REPLY`).

## 2. Objetivo del sistema

Centralizar y normalizar comunicados operativos de WhatsApp para que:

- solo se procesen mensajes autorizados,
- solo entren mensajes con intención operativa real,
- se creen o actualicen tareas en ClickUp automáticamente,
- quede auditoría técnica del procesamiento,
- el flujo pueda operar 24/7 sin intervención manual continua.

## 3. Problema que resuelve

Antes del aislamiento de Proyecto D:

- mensajes de un chat operativo podían entrar al agente principal,
- existía riesgo de respuestas no deseadas,
- no había una carpeta técnica limpia y separada para documentar el funcionamiento,
- la trazabilidad dependía demasiado del historial operativo y no de una estructura propia.

Proyecto D corrige eso mediante un pipeline separado, silencioso y auditable.

## 4. Arquitectura funcional

```text
WhatsApp
  -> OpenClaw channel session
    -> whatsapp_watcher.py
      -> router.py
        -> sync_clickup.py
          -> ClickUp API
        -> supabase_store.py
          -> Supabase audit tables
      -> audit log local / state local
```

## 5. Componentes principales

### `src/whatsapp_watcher.py`
Observa sesiones de OpenClaw, detecta mensajes nuevos de remitentes permitidos y dispara el router cuando encuentra mensajes con **📢/📣**.

### `src/router.py`
Es la puerta de entrada operativa. Valida remitente, registra auditoría, actualiza tablas de Supabase y delega el procesamiento de negocio a `sync_clickup.py`.

### `src/sync_clickup.py`
Contiene la lógica de negocio:

- limpia el cuerpo del mensaje,
- separa nombre de proyecto y texto de estado,
- clasifica el estado operativo,
- busca coincidencia en ClickUp,
- crea o actualiza tareas,
- evita duplicados por `message_id`.
- si el mensaje trae adjuntos, arma también un resumen contextual y los sube a la misma tarea de ClickUp.

### `src/supabase_store.py`
Persistencia técnica hacia Supabase para:

- mensajes entrantes,
- eventos de sincronización con ClickUp,
- errores de procesamiento.

### `schema/proyecto_d_supabase_schema.sql`
DDL base para las tablas de trazabilidad de Proyecto D.

### `config/config.example.json`
Plantilla de configuración sin secretos para desplegar el flujo en otro entorno.

## 6. Reglas operativas

- Solo se aceptan remitentes del allowlist.
- Solo se procesan mensajes que incluyan **📢** o **📣**.
- La salida visible del flujo es **`NO_REPLY`**.
- Los mensajes sin emoji trigger se ignoran.
- Los mensajes repetidos se deduplican por `message_id`.
- ClickUp actúa como destino operativo principal.
- Supabase actúa como capa de auditoría y trazabilidad.

## 7. Estados que puede inferir el sistema

El parser actual puede mapear mensajes hacia estados como:

- `revisión inicial`
- `revisión interna`
- `en espera`
- `metrado y cotizaciones`
- `entregado`
- `Closed`

## 8. Ejemplos de mensajes válidos

- `Comunicado 📢 80 MAE CHO - OOCC se reactiva el proceso y recibimos las respuestas a consultas, las cuales lo ubican en su carpeta.`
- `📢 91 UTP ATE recién nos compartieron la información inicial`
- `📣 PARDOS CHORRILLOS información preliminar para revisión`
- `📢 120 UTP BREÑA pasa a metrado y cotizaciones`
- `📢 120 UTP BREÑA proyecto cerrado, dar por cerrado`

## 9. Dependencias externas

### WhatsApp
Fuente de mensajes operativos. El canal debe estar vinculado y conectado en OpenClaw.

### OpenClaw
Orquesta la sesión del canal, el watcher, el cron silencioso y el entorno de ejecución.

### ClickUp
Sistema de destino para tareas y estados operativos.

### Supabase
Sistema de trazabilidad estructurada y registro de errores/eventos.

## 10. Operación 24/7

El diseño contempla operación continua mediante un **cron silencioso** que ejecuta un escaneo periódico del watcher. Ese cron no debe responder en chat; solo debe procesar mensajes y dejar evidencia si hay error.

## 11. Seguridad y buenas prácticas

- No se deben subir secretos al repositorio.
- `config.example.json` es solo plantilla.
- El token de ClickUp debe vivir fuera del repo.
- Las credenciales de Supabase deben vivir fuera del repo.
- Los logs y estados locales deben ignorarse en Git.

## 12. Estructura del repositorio

```text
README.md
.gitignore
config/
  config.example.json
docs/
  INFORME_TECNICO.md
legacy/
  proyecto_d_clickup_sync.py
schema/
  proyecto_d_supabase_schema.sql
src/
  router.py
  supabase_store.py
  sync_clickup.py
  whatsapp_watcher.py
```

## 13. Próximos pasos recomendados

- crear `config/config.json` real en el entorno objetivo,
- validar credenciales de ClickUp y Supabase en el entorno destino,
- probar ingreso real de mensajes desde WhatsApp con canal ya conectado,
- agregar monitoreo explícito de salud del canal WhatsApp,
- opcionalmente agregar tests unitarios para parsing y clasificación de estados.

## 14. Estado de publicación

Este módulo ya fue separado y publicado como repositorio independiente para mantener:

- aislamiento de código,
- historial propio,
- documentación técnica propia,
- y una ruta clara de mantenimiento/evolución.

# Informe técnico profesional - Proyecto D

**Preparado por:** OpenClaw  
**Fecha:** 2026-06-28  
**Ámbito:** WhatsApp + OpenClaw + ClickUp + Supabase

---

## 1. Contexto

Proyecto D es un flujo de automatización para intake operativo por WhatsApp. Su función es transformar mensajes cortos de avance operativo en acciones estructuradas dentro de ClickUp, conservando trazabilidad y reduciendo intervención manual.

El sistema fue aislado porque el flujo original convivía con otras automatizaciones de EVINKA y eso generaba riesgo de ruido, respuestas no deseadas y falta de claridad documental.

---

## 2. Necesidad de negocio

La operación necesitaba:

- un canal simple para reportar avances,
- una forma consistente de convertir mensajes en estados de trabajo,
- trazabilidad técnica por mensaje,
- un mecanismo silencioso que no respondiera a los usuarios,
- independencia respecto del agente principal,
- una base ordenada para documentación y futura publicación en GitHub.

---

## 3. Solución implementada

La solución final se compone de cuatro capas:

1. **Captura:** lectura de mensajes desde sesiones de OpenClaw/WhatsApp.
2. **Control de acceso:** validación por remitente permitido y emoji trigger.
3. **Lógica operativa:** parsing del mensaje, clasificación de estado, creación/actualización en ClickUp.
4. **Trazabilidad:** auditoría local y persistencia estructurada en Supabase.

---

## 4. Principios de diseño

- **Aislamiento:** Proyecto D no debe contaminar otros frentes de automatización.
- **Silencio operacional:** el flujo no responde al chat; solo procesa.
- **Activación explícita:** solo se procesan mensajes con 📢 o 📣.
- **Control de remitente:** solo números aprobados pueden disparar acciones.
- **Idempotencia:** se evita procesar dos veces el mismo mensaje.
- **Trazabilidad:** cada evento importante puede dejar rastro técnico.

---

## 5. Flujo detallado

### 5.1 Ingreso
Un remitente autorizado envía un mensaje por WhatsApp con el emoji operativo.

### 5.2 Detección
`whatsapp_watcher.py` revisa sesiones de OpenClaw y encuentra mensajes nuevos.

### 5.3 Enrutamiento
`router.py` valida remitente, registra base de auditoría y llama a la lógica de sincronización.

### 5.4 Interpretación
`sync_clickup.py`:

- limpia el texto,
- extrae nombre del proyecto,
- detecta intención/estado,
- busca coincidencias con tareas existentes,
- crea o actualiza la tarea correcta en ClickUp.

### 5.5 Persistencia
Si Supabase está configurado, el sistema registra:

- mensaje recibido,
- resultado del procesamiento,
- evento ClickUp,
- error técnico si corresponde.

---

## 6. Integraciones

### 6.1 WhatsApp
Origen de los mensajes. Requiere que el canal de OpenClaw esté vinculado y conectado.

### 6.2 OpenClaw
Motor de ejecución del watcher, cron silencioso y acceso a sesiones del canal.

### 6.3 ClickUp
Destino operativo final. Las tareas se crean o actualizan dentro de la lista configurada.

### 6.4 Supabase
Capa de observabilidad/auditoría. No sustituye a ClickUp; complementa la trazabilidad.

---

## 7. Estructura de datos mínima

### 7.1 Configuración
- remitentes permitidos,
- emojis permitidos,
- lista de ClickUp,
- rutas locales de estado/auditoría,
- tablas de Supabase.

### 7.2 Estado local
- `processed_ids` para deduplicación,
- log de auditoría,
- log de errores de Supabase.

---

## 8. Riesgos conocidos

- si WhatsApp se desconecta, el watcher no verá mensajes nuevos,
- si ClickUp falla, el mensaje puede quedar auditado pero no reflejado como tarea,
- si el patrón textual del mensaje cambia mucho, la clasificación puede perder precisión,
- si se publican secretos por error, se compromete la seguridad operativa.

---

## 9. Recomendaciones

1. Mantener este módulo separado dentro de GitHub.
2. Versionar solo código y plantillas, nunca secretos.
3. Agregar pruebas unitarias para parsing y clasificación.
4. Agregar monitoreo explícito de salud del canal WhatsApp.
5. Mantener ClickUp como destino operativo y Supabase como auditoría.

---

## 10. Conclusión

Proyecto D ya tiene una base técnica clara, separada y profesional para operar como módulo propio. La carpeta preparada en este repositorio permite:

- entender cómo funciona,
- revisar el código principal,
- desplegarlo en otro entorno,
- documentarlo profesionalmente,
- y publicarlo en GitHub con una narrativa técnica ordenada.

El siguiente paso natural es **subir esta carpeta a GitHub con un commit limpio** y, si quieres máxima separación, moverla luego a un repositorio independiente.

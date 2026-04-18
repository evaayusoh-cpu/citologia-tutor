# Citología Ginecológica · Tutor Socrático IA

Aplicación de tutoría socrática para citología ginecológica, desarrollada para alumnado de FP Sanitaria.

## Estructura

- `app.py` — Aplicación principal
- `requirements.txt` — Dependencias
- `secrets_template.txt` — Plantilla de configuración (no subir a GitHub)

## Despliegue en Streamlit Cloud

1. Sube este repositorio a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu cuenta de GitHub y selecciona este repositorio
4. En **Settings > Secrets**, añade:

```
ANTHROPIC_API_KEY = "sk-ant-..."
TEACHER_PASSWORD = "tu-contraseña"
```

5. Haz clic en Deploy

## Uso

- **Alumnas**: seleccionan "Soy alumna" y comienzan la sesión
- **Profesora**: selecciona "Acceso profesora", introduce la contraseña y accede al panel de registros

## Registros

Cada sesión se guarda en la carpeta `logs/` con el formato:
`{id_alumna}_{timestamp}.json`

Contiene el chat completo y el estado del checklist turno a turno.

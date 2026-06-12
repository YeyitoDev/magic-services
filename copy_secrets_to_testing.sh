#!/bin/bash
# Copia los secrets del .env local a GitHub secrets (repo-level para testing)
# Uso: ./copy_secrets_to_testing.sh

set -e

echo "📋 Leyendo .env local y configurando secrets de GitHub para testing..."

# Cargar el archivo .env
if [ ! -f .env ]; then
  echo "❌ Error: No se encontró el archivo .env"
  exit 1
fi

# Función para obtener valor de variable del .env
get_env_value() {
  grep "^$1=" .env | cut -d '=' -f2-
}

# Lista de secrets a configurar desde .env
SECRETS=(
  "TELEGRAM_BOT_TOKEN"
  "TELEGRAM_BOT_TOKEN_LINKS"
  "TELEGRAM_VALIDATOR_IDS"
  "TELEGRAM_VIP_GROUP_ID"
  "DB_USER"
  "DB_PASSWORD"
  "DB_HOST"
  "DB_NAME"
)

# Configurar secrets desde .env
for secret in "${SECRETS[@]}"; do
  value=$(get_env_value "$secret")
  if [ -n "$value" ]; then
    echo "🔧 Configurando $secret..."
    echo "$value" | gh secret set "$secret"
    echo "✅ $secret configurado"
  else
    echo "⚠️  $secret está vacío en .env, omitiendo..."
  fi
done

# Secrets que faltan en .env (requerirán input manual)
echo ""
echo "⚠️  Los siguientes secrets no están en .env y deben configurarse manualmente:"
echo "   - GOOGLE_CREDENTIALS_JSON"
echo "   - AWS_ACCESS_KEY_ID"
echo "   - AWS_SECRET_ACCESS_KEY"
echo ""
echo "   Ejecuta: gh secret set <nombre> y pega el valor cuando se solicite."
echo ""
echo "✅ Secrets de .env configurados en GitHub (repo-level para testing)"

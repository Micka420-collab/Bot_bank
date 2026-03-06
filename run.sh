#!/bin/bash
# 🎮 GameVault Bot - Launcher
# Usage: ./run.sh [bot|admin|both]

set -e

cd "$(dirname "$0")"

# Créer le dossier data
mkdir -p data

# Vérifier le .env
if [ ! -f .env ]; then
    echo "⚠️  Fichier .env manquant!"
    echo "   Copiez .env.example en .env et configurez vos clés."
    echo "   cp .env.example .env"
    exit 1
fi

# Install deps
pip install -r requirements.txt --quiet 2>/dev/null

MODE=${1:-both}

case $MODE in
    bot)
        echo "🤖 Lancement du bot Telegram..."
        python -m bot.main
        ;;
    admin)
        echo "🌐 Lancement du panel admin..."
        python -m admin.panel
        ;;
    both)
        echo "🚀 Lancement du bot + admin panel..."
        python -m admin.panel &
        ADMIN_PID=$!
        python -m bot.main &
        BOT_PID=$!
        
        trap "kill $ADMIN_PID $BOT_PID 2>/dev/null" EXIT
        wait
        ;;
    *)
        echo "Usage: $0 [bot|admin|both]"
        exit 1
        ;;
esac

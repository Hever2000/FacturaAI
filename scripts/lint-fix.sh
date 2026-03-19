#!/bin/bash
# FacturaAI Lint Fix Script
# Runs automatic code formatting and fixes

set -e

echo "🧹 Running code fixes..."

# Install tools if needed
if ! command -v ruff &> /dev/null; then
    echo "📦 Installing ruff..."
    pip install ruff
fi

if ! command -v black &> /dev/null; then
    echo "📦 Installing black..."
    pip install black
fi

if ! command -v isort &> /dev/null; then
    echo "📦 Installing isort..."
    pip install isort
fi

# Fix with ruff
echo "🔧 Running ruff (fix)..."
ruff check --fix .

# Format with ruff (alternative to black)
echo "🎨 Running ruff format..."
ruff format .

# Sort imports
echo "📝 Sorting imports..."
isort .

# Format with black
echo "🎨 Running black..."
black --line-length=100 .

echo "✅ All fixes applied!"

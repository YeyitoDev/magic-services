.PHONY: help install test lint run clean

help:
	@echo "Magic Chatbot v2 - Comandos"
	@echo "  make install   - Instalar dependencias"
	@echo "  make test      - Ejecutar tests"
	@echo "  make lint      - Lint con Ruff"
	@echo "  make run       - Iniciar bot (polling)"
	@echo "  make clean     - Limpiar caché + logs"
	@echo "  make db-seed   - Sembrar precios en BD"
	@echo "  make deploy    - Deploy a PythonAnywhere"

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v --tb=short

lint:
	ruff check .

run:
	python main.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf logs/*.log 2>/dev/null || true

db-seed:
	python -c "from core.container import container; container.initialize_defaults(); print('✅ DB seeded')"

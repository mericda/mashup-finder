APP_RESOURCES = Mashup Finder.app/Contents/Resources
MODULES = matching.py db.py importer.py server.py

.PHONY: run install test

run:
	python3 app.py

install:
	cp $(MODULES) "$(APP_RESOURCES)/"
	rm -rf "/Applications/Mashup Finder.app"
	cp -R "Mashup Finder.app" "/Applications/"
	@echo "Installed to /Applications"

test:
	python -m pytest tests/ -v -k "not (run_sync_populates_db or run_sync_idempotent)"

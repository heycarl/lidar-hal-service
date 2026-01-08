.PHONY: help lint format ci deb-layout deb clean wheels

PYTHON ?= python3

PKG_NAME ?= lidar-service
VERSION  ?= 0.0.0
DEB_ARCH ?= arm64
PYTHON   ?= python3

DESCRIPTION := $(shell grep -Po '^description\s*=\s*"\K[^"]+' pyproject.toml || echo "")
MAINTAINER  := $(shell grep -Po '^name\s*=\s*"\K[^"]+' pyproject.toml | head -1)
EMAIL       := $(shell grep -Po '^email\s*=\s*"\K[^"]+' pyproject.toml | head -1)
MAINTAINER_FULL := $(MAINTAINER) <$(EMAIL)>

help:
	@echo "Available targets:"
	@echo "  lint    - run linters (black)"
	@echo "  format  - autoformat code (ruff format)"
	@echo "  ci      - lint + format"

lint:
	$(PYTHON) -m black --check src

format:
	$(PYTHON) -m ruff check src

ci: lint format

wheels:
	$(PYTHON) -m pip install --upgrade pip setuptools wheel
	$(PYTHON) -m pip wheel . -w packaging/wheels

deb-layout:
	mkdir -p pkg/opt/$(PKG_NAME)/{app,config,wheels,bin}
	mkdir -p pkg/lib/systemd/system
	mkdir -p pkg/DEBIAN

	cp -r src pkg/opt/$(PKG_NAME)/app/
	cp config.yaml pkg/opt/$(PKG_NAME)/config/
	cp -r packaging/wheels/* pkg/opt/$(PKG_NAME)/wheels/
	cp packaging/bin/$(PKG_NAME) pkg/opt/$(PKG_NAME)/bin/
	cp packaging/systemd/$(PKG_NAME).service pkg/lib/systemd/system/

	sed \
	  -e "s/@NAME@/$(PKG_NAME)/" \
	  -e "s/@VERSION@/$(VERSION)/" \
	  -e "s/@DESCRIPTION@/$(DESCRIPTION)/" \
	  -e "s/@MAINTAINER@/$(MAINTAINER_FULL)/" \
	  packaging/DEBIAN/control.in > pkg/DEBIAN/control

	cp packaging/DEBIAN/postinst pkg/DEBIAN/
	chmod 755 pkg/DEBIAN/postinst

deb: wheels deb-layout
	dpkg-deb --build pkg \
	  $(PKG_NAME)_$(VERSION)_$(DEB_ARCH).deb

release: deb

clean:
	rm -rf pkg packaging/wheels
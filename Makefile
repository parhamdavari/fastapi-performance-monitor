# Use bash with strict flags so failures stop the pipeline early.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Load local environment overrides (e.g. API tokens) if a .env file exists.
ifneq (,$(wildcard .env))
include .env
export $(shell sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' .env)
endif

# Run everything with python3 by default, but allow overrides (e.g. PYTHON=python3.12).
PYTHON ?= python3
PYPROJECT := pyproject.toml

# Extract the package name and version from pyproject.toml without hardcoding them.
PKG_NAME := $(shell $(PYTHON) -c "import re;from pathlib import Path;text=Path('$(PYPROJECT)').read_text(encoding='utf-8');match=re.search(r'(?m)^name\\s*=\\s*\"([^\"]+)\"', text);print(match.group(1))")
PKG_VERSION := $(shell $(PYTHON) -c "import re;from pathlib import Path;text=Path('$(PYPROJECT)').read_text(encoding='utf-8');match=re.search(r'(?m)^version\\s*=\\s*\"([^\"]+)\"', text);print(match.group(1))")

# Centralised config for build artefact locations and external services.
DIST_DIR := dist
BUILD_DIR := build
TEST_INSTALL_VENV := .venv-testpypi
TEST_SIMPLE_INDEX := https://test.pypi.org/simple/
PROD_SIMPLE_INDEX := https://pypi.org/simple/
TEST_PYPI_API := https://test.pypi.org/pypi
PROD_PYPI_API := https://pypi.org/pypi
TOOLS_VENV := .venv-build
TOOLS_PYTHON := $(TOOLS_VENV)/bin/python
TOOLS_PIP := $(TOOLS_VENV)/bin/pip
TOOLS_TWINE := $(TOOLS_VENV)/bin/twine
TOOLS_BOOTSTRAP := build twine

TWINE := $(TOOLS_TWINE)
BUILD_CMD := $(TOOLS_PYTHON) -m build
TWINE_UPLOAD_FLAGS ?= --skip-existing
TWINE_REPOSITORY_TEST ?= testpypi
TWINE_REPOSITORY_PROD ?= pypi
# twine respects TWINE_USERNAME/TWINE_PASSWORD or repository aliases in ~/.pypirc.

define CHECK_VERSION_PY
import os, sys, urllib.request, urllib.error
base = os.environ["PYPI_BASE"].rstrip("/")
name = os.environ["PKG_NAME"]
version = os.environ["PKG_VERSION"]
url = f"{base}/{name}/{version}/json"
try:
    urllib.request.urlopen(url, timeout=5)
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        sys.exit(0)
    print(f"Failed to check {url}: HTTP {exc.code}", file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as exc:
    print(f"Failed to reach {url}: {exc.reason}", file=sys.stderr)
    sys.exit(2)
else:
    print(f"{name} {version} already published at {base}", file=sys.stderr)
    sys.exit(10)
endef

export CHECK_VERSION_PY

# The default goal exercises the full TestPyPI pipeline.
.DEFAULT_GOAL := test-release

.PHONY: test-release clean clean-dist clean-test-install build check upload-test install-test upload tag-release publish verify-version configure-pypirc tools-venv help

## tools-venv - bootstrap a dedicated virtualenv with build/twine tooling.
tools-venv: $(TOOLS_PYTHON)

$(TOOLS_PYTHON):
	@echo "Creating packaging virtualenv at $(TOOLS_VENV)"
	@python3 -m venv $(TOOLS_VENV)
	@$(TOOLS_PIP) install --upgrade pip
	@$(TOOLS_PIP) install $(TOOLS_BOOTSTRAP)

## test-release - build, upload to TestPyPI, and install back for confidence.
test-release: clean-dist tools-venv
	@$(MAKE) upload-test
	@$(MAKE) install-test

## clean - remove build artefacts so a fresh build starts cleanly.
clean: clean-dist clean-test-install
	@rm -rf $(BUILD_DIR) .eggs *.egg-info $(TOOLS_VENV)

## clean-dist - remove the dist directory but guard when it is missing.
clean-dist:
	@rm -rf $(DIST_DIR)

## clean-test-install - drop the temporary venv used for TestPyPI verification.
clean-test-install:
	@rm -rf $(TEST_INSTALL_VENV)

## build - create both sdist and wheel using the PEP 517 build backend.
build: clean-dist tools-venv
	@echo "Building source and wheel distributions for $(PKG_NAME) $(PKG_VERSION)"
	@$(BUILD_CMD)

## check - run the metadata sanity checks before any upload.
check: build
	@echo "Running twine checks on $(DIST_DIR)"
	@$(TWINE) check $(DIST_DIR)/*

## upload-test - push artefacts to TestPyPI unless that exact version already exists.
upload-test: check
	@set -eu; \
	status=0; \
	printf '%s\n' "$$CHECK_VERSION_PY" | PYPI_BASE="$(TEST_PYPI_API)" PKG_NAME="$(PKG_NAME)" PKG_VERSION="$(PKG_VERSION)" $(PYTHON) - || status=$$?; \
	if [ "$$status" -eq 10 ]; then \
	    echo "Skipping TestPyPI upload: $(PKG_NAME) $(PKG_VERSION) already exists."; \
	elif [ "$$status" -ne 0 ]; then \
	    exit "$$status"; \
	else \
	    $(TWINE) upload --repository "$(TWINE_REPOSITORY_TEST)" $(TWINE_UPLOAD_FLAGS) $(DIST_DIR)/*; \
	fi

## install-test - install the package from TestPyPI into a throwaway venv.
install-test:
	@set -eu; \
	if [ ! -d "$(TEST_INSTALL_VENV)" ]; then \
	    $(PYTHON) -m venv "$(TEST_INSTALL_VENV)"; \
	fi; \
	"$(TEST_INSTALL_VENV)/bin/pip" install --upgrade pip; \
	if ! "$(TEST_INSTALL_VENV)/bin/pip" install fastapi "tdigest>=0.5.2" "httpx>=0.23.0"; then \
		echo "Dependency installation failed (likely missing build headers for accumulation-tree); continuing with package-only install." >&2; \
	fi; \
	"$(TEST_INSTALL_VENV)/bin/pip" install --index-url "$(TEST_SIMPLE_INDEX)" --extra-index-url "$(PROD_SIMPLE_INDEX)" --no-deps "$(PKG_NAME)==$(PKG_VERSION)"; \
	echo "Test installation succeeded in $(TEST_INSTALL_VENV)"

## upload - push artefacts to the real PyPI after verifying they are not already present.
upload: check
	@set -eu; \
	status=0; \
	printf '%s\n' "$$CHECK_VERSION_PY" | PYPI_BASE="$(PROD_PYPI_API)" PKG_NAME="$(PKG_NAME)" PKG_VERSION="$(PKG_VERSION)" $(PYTHON) - || status=$$?; \
	if [ "$$status" -eq 10 ]; then \
	    echo "Skipping PyPI upload: $(PKG_NAME) $(PKG_VERSION) already exists."; \
	elif [ "$$status" -ne 0 ]; then \
	    exit "$$status"; \
	else \
	    $(TWINE) upload --repository "$(TWINE_REPOSITORY_PROD)" $(TWINE_UPLOAD_FLAGS) $(DIST_DIR)/*; \
	fi

## tag-release - create and push a git tag that matches the distribution version.
tag-release:
	@git diff --quiet || (echo "Working tree has uncommitted changes; commit or stash before tagging." >&2 && exit 1)
	@if git rev-parse "v$(PKG_VERSION)" >/dev/null 2>&1; then \
	    echo "Git tag v$(PKG_VERSION) already exists. Aborting."; \
	    exit 1; \
	fi
	@git tag -a "v$(PKG_VERSION)" -m "Release v$(PKG_VERSION)"
	@git push origin "v$(PKG_VERSION)"

## publish - convenience target tying together the production upload and tagging.
publish: upload tag-release

## verify-version - show the resolved package identity for quick sanity checks.
verify-version:
	@echo "Package: $(PKG_NAME)"
	@echo "Version: $(PKG_VERSION)"

## configure-pypirc - create ~/.pypirc using TESTPYPI_TOKEN and PYPI_TOKEN env vars.
configure-pypirc:
	@set -eu; \
	: "$${PYPI_TOKEN:?Set PYPI_TOKEN to your PyPI API token}"; \
	: "$${TESTPYPI_TOKEN:?Set TESTPYPI_TOKEN to your TestPyPI API token}"; \
	umask 177; \
	if [ -f "$$HOME/.pypirc" ]; then \
		cp "$$HOME/.pypirc" "$$HOME/.pypirc.bak"; \
		echo "Backed up existing $$HOME/.pypirc to $$HOME/.pypirc.bak"; \
	fi; \
	{ \
		echo "[distutils]"; \
		echo "index-servers ="; \
		echo "    pypi"; \
		echo "    testpypi"; \
		echo ""; \
		echo "[pypi]"; \
		echo "username = __token__"; \
		echo "password = $$PYPI_TOKEN"; \
		echo ""; \
		echo "[testpypi]"; \
		echo "username = __token__"; \
		echo "password = $$TESTPYPI_TOKEN"; \
	} > "$$HOME/.pypirc"
	@echo "Wrote credentials to $$HOME/.pypirc (permissions 600)."

## help - list available targets and their descriptions.
help:
	@awk 'BEGIN {FS=":.*## "}; /^## / {desc=$$0; sub(/^## /, "", desc); next} /^[a-zA-Z0-9_-]+:.*$$/ {if (desc) {split($$0, parts, ":"); printf "%-20s %s\n", parts[1], desc; desc=""}}' $(MAKEFILE_LIST)

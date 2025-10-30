# API Coverage Report Generator

This directory contains tools to generate human-readable API coverage reports by cross-referencing griffe API snapshots with pytest code coverage data.

## Overview

The API coverage report helps identify which public API functions, classes, and methods still need testing by combining:

1. **Griffe API Detection**: Identifies all public APIs in the codebase
2. **Pytest Coverage Data**: Shows which lines and branches have been tested
3. **Cross-referencing**: Matches API items with their coverage status

## Files

- `generate_api_snapshot.py` - Generates API snapshots using griffe
- `validate_api_snapshot.py` - Validates API snapshots
- `generate_api_coverage_report.py` - Generates API coverage reports for unit or integration tests

## Quick Start

### Step 1: Generate API Snapshot

Generate the API snapshot once (or when the API changes):

```bash
python scripts/generate_api_snapshot.py api_snapshot.json
```

### Step 2: Run Tests with Coverage

**For Unit Tests:**
```bash
hatch run test

# Coverage XML is automatically generated at: build/coverage/coverage.xml
```

**For Integration Tests:**
```bash
hatch run integ:test-with-coverage

# Coverage XML is automatically generated at: build/coverage/integ-coverage.xml
```

### Step 3: Generate Coverage Report

**Unit Test Coverage:**
```bash
# TSV format (default) - outputs to api_coverage_report.tsv
python scripts/generate_api_coverage_report.py --test-type unit

# Markdown format - outputs to api_coverage_report.md
python scripts/generate_api_coverage_report.py --test-type unit --format markdown
```

**Integration Test Coverage:**
```bash
# TSV format (default) - outputs to integ_coverage_report.tsv
python scripts/generate_api_coverage_report.py --test-type integ

# Markdown format - outputs to integ_coverage_report.md
python scripts/generate_api_coverage_report.py --test-type integ --format markdown
```

## Generated Files (Ignored by Git)

All generated files are automatically ignored by `.gitignore`:
- `api_snapshot.json` - API snapshot from griffe
- `api_coverage_report.tsv` - Unit test coverage (TSV)
- `api_coverage_report.md` - Unit test coverage (Markdown)
- `integ_coverage_report.tsv` - Integration test coverage (TSV)
- `integ_coverage_report.md` - Integration test coverage (Markdown)

## Advanced Usage

### Custom Coverage File Paths

```bash
# Use custom coverage XML file
python scripts/generate_api_coverage_report.py \
    --test-type unit \
    --coverage-xml path/to/custom-coverage.xml \
    --output custom_report.tsv
```

### Custom Output Paths

```bash
# Specify custom output location
python scripts/generate_api_coverage_report.py \
    --test-type integ \
    --output reports/integration_coverage.tsv
```

### Using with Different Environments

```bash
# Generate snapshot with docs environment
hatch run docs:python scripts/generate_api_snapshot.py api_snapshot.json

# Run tests in specific environment
hatch run test:pytest --cov=src --cov-report=xml:build/coverage/coverage.xml

# Generate report
python scripts/generate_api_coverage_report.py --test-type unit
```

## Related Files

- `scripts/generate_api_snapshot.py` - Generates API snapshots using griffe
- `scripts/validate_api_snapshot.py` - Validates API snapshots for changes
- `scripts/generate_api_coverage_report.py` - Generates coverage reports (this script)
- `.github/workflows/api-change-detection.yml` - CI workflow using griffe
- `hatch.toml` - Build configuration with test environments

#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Generate API coverage report by cross-referencing griffe API snapshots with pytest coverage data.

This script analyzes the public API (detected by griffe) and cross-references it with
pytest code coverage to show which public functions, classes, and parameters still need testing.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CoverageInfo:
    """Coverage information for a specific line or function."""

    line_number: int
    hits: int
    is_branch: bool = False
    branch_coverage: Optional[str] = None
    missing_branches: Optional[str] = None


@dataclass
class FunctionCoverage:
    """Coverage information for a function."""

    name: str
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    lines_covered: int = 0
    lines_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    is_tested: bool = False
    coverage_lines: List[CoverageInfo] = field(default_factory=list)


@dataclass
class ApiItem:
    """Represents a public API item (function, class, method, etc.)."""

    name: str
    kind: str  # function, class, method, property, etc.
    file_path: str
    line_number: Optional[int] = None
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    is_public: bool = True
    coverage: Optional[FunctionCoverage] = None


@dataclass
class ApiCoverageReport:
    """Complete API coverage report."""

    total_api_items: int = 0
    covered_api_items: int = 0
    uncovered_api_items: int = 0
    coverage_percentage: float = 0.0
    api_items: List[ApiItem] = field(default_factory=list)
    uncovered_functions: List[ApiItem] = field(default_factory=list)
    low_coverage_functions: List[ApiItem] = field(default_factory=list)
    partially_covered_functions: List[ApiItem] = field(default_factory=list)
    well_covered_functions: List[ApiItem] = field(default_factory=list)


class ApiCoverageAnalyzer:
    """Analyzes API coverage by cross-referencing griffe API data with pytest coverage."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.src_root = project_root / "src"
        self.coverage_data: Dict[str, Dict] = {}
        self.api_data: Dict = {}

    def load_coverage_data(self, coverage_xml_path: Path) -> None:
        """Load pytest coverage data from XML file."""
        if not coverage_xml_path.exists():
            raise FileNotFoundError(f"Coverage XML file not found: {coverage_xml_path}")

        tree = ET.parse(coverage_xml_path)
        root = tree.getroot()

        for package in root.findall(".//package"):
            for class_elem in package.findall(".//class"):
                filename = class_elem.get("filename", "")
                if not filename:
                    continue

                # Normalize the file path for matching with API data
                # Coverage XML uses relative paths from src/deadline/
                if filename.startswith("/"):
                    # Absolute path - use as is
                    file_path = filename
                else:
                    # Relative path - convert to absolute path under src/deadline/
                    file_path = str(self.src_root / "deadline" / filename)

                lines_data = {}
                for line in class_elem.findall(".//line"):
                    line_num = int(line.get("number", 0))
                    hits = int(line.get("hits", 0))
                    is_branch = line.get("branch") == "true"
                    branch_coverage = line.get("condition-coverage")
                    missing_branches = line.get("missing-branches")

                    lines_data[line_num] = CoverageInfo(
                        line_number=line_num,
                        hits=hits,
                        is_branch=is_branch,
                        branch_coverage=branch_coverage,
                        missing_branches=missing_branches,
                    )

                self.coverage_data[file_path] = lines_data

    def load_api_snapshot(self, snapshot_path: Path) -> None:
        """Load griffe API snapshot data."""
        if not snapshot_path.exists():
            raise FileNotFoundError(f"API snapshot file not found: {snapshot_path}")

        with open(snapshot_path, "r", encoding="utf-8") as f:
            self.api_data = json.load(f)

    def _is_ui_related(self, name: str, filepath: str) -> bool:
        """Check if an API item is UI-related and should be excluded."""
        # Check if the file path contains UI-related directories
        ui_path_indicators = ["/ui/", "\\ui\\", "/gui/", "\\gui\\", "/widgets/", "\\widgets\\"]
        if any(indicator in filepath.lower() for indicator in ui_path_indicators):
            return True

        # Check if the module name contains UI-related terms
        ui_name_indicators = [".ui.", ".gui.", ".widgets.", ".dialogs."]
        if any(indicator in name.lower() for indicator in ui_name_indicators):
            return True

        # Check for common UI class patterns
        ui_class_patterns = [
            "widget",
            "dialog",
            "window",
            "button",
            "label",
            "menu",
            "toolbar",
            "statusbar",
            "scrollarea",
            "combobox",
            "spinbox",
            "checkbox",
            "radiobutton",
            "slider",
            "progressbar",
            "tabwidget",
            "treewidget",
            "listwidget",
            "tablewidget",
        ]
        name_lower = name.lower()
        if any(pattern in name_lower for pattern in ui_class_patterns):
            return True

        return False

    def _extract_api_items(
        self, obj: Dict, parent_path: str = "", file_path: str = ""
    ) -> List[ApiItem]:
        """Recursively extract API items from griffe data."""
        items = []

        if not isinstance(obj, dict):
            return items

        # Get basic info
        name = obj.get("name", "")
        kind = obj.get("kind", "")
        filepath = obj.get("filepath", file_path)
        line_number = obj.get("lineno")
        docstring = obj.get("docstring", {}).get("value") if obj.get("docstring") else None

        # Build full name
        full_name = f"{parent_path}.{name}" if parent_path else name

        # Extract parameters for functions/methods
        parameters = []
        if kind in ["function", "method"] and "parameters" in obj:
            params = obj.get("parameters", {})
            if isinstance(params, dict):
                parameters = list(params.keys())

        # Check if this is a public API item
        is_public = not name.startswith("_") and obj.get("is_public", True)

        if is_public and kind in ["function", "method", "class", "property"]:
            # Normalize filepath for matching with coverage data
            if filepath:
                if isinstance(filepath, list):
                    # Handle case where filepath is a list (for modules)
                    abs_filepath = str(self.project_root / filepath[0]) if filepath else ""
                elif filepath.startswith("/"):
                    # Absolute path - use as is
                    abs_filepath = filepath
                else:
                    # Relative path - convert to absolute
                    abs_filepath = str(self.project_root / filepath)
            else:
                abs_filepath = ""

            # Skip UI-related items
            # if not self._is_ui_related(full_name, abs_filepath):
            api_item = ApiItem(
                name=full_name,
                kind=kind,
                file_path=abs_filepath,
                line_number=line_number,
                docstring=docstring,
                parameters=parameters,
                is_public=is_public,
            )
            items.append(api_item)

        # Recursively process members
        members = obj.get("members", {})
        if isinstance(members, dict):
            for member_name, member_obj in members.items():
                if isinstance(member_obj, dict):
                    child_items = self._extract_api_items(member_obj, full_name, filepath)
                    items.extend(child_items)

        return items

    def _calculate_function_coverage(self, api_item: ApiItem) -> FunctionCoverage:
        """Calculate coverage for a specific API item."""
        file_coverage = self.coverage_data.get(api_item.file_path, {})

        if not file_coverage:
            return FunctionCoverage(
                name=api_item.name, file_path=api_item.file_path, is_tested=False
            )

        # For now, we'll use a simple heuristic: if the line where the function
        # is defined has been hit, we consider it covered
        start_line = api_item.line_number
        if start_line and start_line in file_coverage:
            line_info = file_coverage[start_line]
            is_tested = line_info.hits > 0

            # Try to estimate function coverage by looking at nearby lines
            lines_covered = 0
            lines_total = 0
            branches_covered = 0
            branches_total = 0
            coverage_lines = []

            # Look at a range of lines around the function definition
            # This is a heuristic - ideally we'd parse the AST to get exact function boundaries
            search_range = 20  # Look at next 20 lines as a rough estimate
            for line_num in range(start_line, start_line + search_range):
                if line_num in file_coverage:
                    line_info = file_coverage[line_num]
                    coverage_lines.append(line_info)
                    lines_total += 1
                    if line_info.hits > 0:
                        lines_covered += 1

                    if line_info.is_branch:
                        branches_total += 1
                        if line_info.branch_coverage and "100%" in line_info.branch_coverage:
                            branches_covered += 1

            return FunctionCoverage(
                name=api_item.name,
                file_path=api_item.file_path,
                start_line=start_line,
                end_line=start_line + search_range,
                lines_covered=lines_covered,
                lines_total=lines_total,
                branches_covered=branches_covered,
                branches_total=branches_total,
                is_tested=is_tested,
                coverage_lines=coverage_lines,
            )

        return FunctionCoverage(name=api_item.name, file_path=api_item.file_path, is_tested=False)

    def analyze_coverage(self) -> ApiCoverageReport:
        """Analyze API coverage and generate report."""
        # Extract all public API items
        api_items = self._extract_api_items(self.api_data)

        # Calculate coverage for each API item
        for api_item in api_items:
            api_item.coverage = self._calculate_function_coverage(api_item)

        # Categorize items by coverage
        uncovered = []
        low_coverage = []
        partial_coverage = []
        well_covered = []

        for item in api_items:
            if not item.coverage or not item.coverage.is_tested:
                uncovered.append(item)
            elif item.coverage.lines_total > 0:
                coverage_ratio = item.coverage.lines_covered / item.coverage.lines_total
                if coverage_ratio >= 0.95:  # ≥95% line coverage
                    well_covered.append(item)
                elif coverage_ratio >= 0.50:  # 50-94% line coverage
                    partial_coverage.append(item)
                else:  # >0% and <50% line coverage
                    low_coverage.append(item)
            else:
                # Has some coverage but we can't determine extent
                low_coverage.append(item)

        # Calculate overall statistics
        total_items = len(api_items)
        covered_items = len(well_covered) + len(partial_coverage) + len(low_coverage)
        coverage_percentage = (covered_items / total_items * 100) if total_items > 0 else 0

        return ApiCoverageReport(
            total_api_items=total_items,
            covered_api_items=covered_items,
            uncovered_api_items=len(uncovered),
            coverage_percentage=coverage_percentage,
            api_items=api_items,
            uncovered_functions=uncovered,
            partially_covered_functions=partial_coverage,
            well_covered_functions=well_covered,
            low_coverage_functions=low_coverage,
        )


class ReportGenerator:
    """Generates human-readable API coverage reports."""

    def generate_tsv_report(self, report: ApiCoverageReport, output_path: Path) -> None:
        """Generate a TSV report for easy pasting into Quip."""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("Status\tModule\tFunction/Member\tKind\tCoverage %\tLine\tFile\n")
            
            # Uncovered items (0%)
            for item in sorted(report.uncovered_functions, key=lambda x: (x.file_path, x.name)):
                file_path = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                func_name = item.name.split(".")[-1]
                
                f.write(f"🔴 Uncovered\t{item.name}\t{func_name}\t{item.kind}\t0%\t{item.line_number or ''}\t{file_path}\n")
            
            # Low coverage items (1-49%)
            for item in sorted(report.low_coverage_functions, key=lambda x: (x.file_path, x.name)):
                file_path = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                func_name = item.name.split(".")[-1]
                
                coverage = item.coverage
                if coverage and coverage.lines_total > 0:
                    line_pct = (coverage.lines_covered / coverage.lines_total) * 100
                    coverage_str = f"{line_pct:.1f}%"
                else:
                    coverage_str = "Limited data"
                
                f.write(f"🟠 Low\t{item.name}\t{func_name}\t{item.kind}\t{coverage_str}\t{item.line_number or ''}\t{file_path}\n")
            
            # Partial coverage items (50-94%)
            for item in sorted(report.partially_covered_functions, key=lambda x: (x.file_path, x.name)):
                file_path = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                func_name = item.name.split(".")[-1]
                
                coverage = item.coverage
                if coverage and coverage.lines_total > 0:
                    line_pct = (coverage.lines_covered / coverage.lines_total) * 100
                    coverage_str = f"{line_pct:.1f}%"
                else:
                    coverage_str = "Limited data"
                
                f.write(f"🟡 Partial\t{item.name}\t{func_name}\t{item.kind}\t{coverage_str}\t{item.line_number or ''}\t{file_path}\n")
            
            # Well covered items (≥95%)
            for item in sorted(report.well_covered_functions, key=lambda x: (x.file_path, x.name)):
                file_path = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                func_name = item.name.split(".")[-1]
                
                coverage = item.coverage
                if coverage and coverage.lines_total > 0:
                    line_pct = (coverage.lines_covered / coverage.lines_total) * 100
                    coverage_str = f"{line_pct:.1f}%"
                else:
                    coverage_str = "≥95%"
                
                f.write(f"✅ Well Covered\t{item.name}\t{func_name}\t{item.kind}\t{coverage_str}\t{item.line_number or ''}\t{file_path}\n")

    def generate_markdown_report(self, report: ApiCoverageReport, output_path: Path) -> None:
        """Generate a markdown report."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# API Coverage Report\n\n")

            # Summary
            f.write("## Summary\n\n")
            f.write(
                f"- **Total Public API Items**: {report.total_api_items} (UI classes excluded)\n"
            )
            f.write(f"- **Covered Items**: {report.covered_api_items}\n")
            f.write(f"- **Uncovered Items**: {report.uncovered_api_items}\n")
            f.write(f"- **Coverage Percentage**: {report.coverage_percentage:.1f}%\n\n")

            # Coverage thresholds
            f.write("## Coverage Thresholds\n\n")
            f.write("- **🔴 Uncovered**: 0% line coverage - No test coverage detected\n")
            f.write("- **🟠 Low Coverage**: >0% and <50% line coverage - Minimal testing\n")
            f.write(
                "- **🟡 Partial Coverage**: ≥50% and <95% line coverage - Some testing but below well-covered threshold\n"
            )
            f.write(
                "- **✅ Well Covered**: ≥95% line coverage - Meets or exceeds coverage threshold\n\n"
            )

            # Coverage breakdown
            f.write("## Coverage Breakdown\n\n")
            f.write(f"- **Well Covered** (≥95%): {len(report.well_covered_functions)} items\n")
            f.write(
                f"- **Partial Coverage** (50-94%): {len(report.partially_covered_functions)} items\n"
            )
            f.write(f"- **Low Coverage** (1-49%): {len(report.low_coverage_functions)} items\n")
            f.write(f"- **Uncovered** (0%): {len(report.uncovered_functions)} items\n\n")

            # Uncovered functions (highest priority)
            if report.uncovered_functions:
                f.write("## 🔴 Uncovered Public API Items (0% Coverage)\n\n")

                # Group by file for better organization
                by_file = {}
                for item in report.uncovered_functions:
                    file_key = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                    if file_key not in by_file:
                        by_file[file_key] = []
                    by_file[file_key].append(item)

                for file_path, items in sorted(by_file.items()):
                    f.write(f"### {file_path}\n\n")
                    for item in sorted(items, key=lambda x: x.name):
                        f.write(f"- **{item.name}** ({item.kind}) - **0%**")
                        if item.line_number:
                            f.write(f" - Line {item.line_number}")
                        f.write("\n")
                    f.write("\n")

            # Low coverage functions
            if report.low_coverage_functions:
                f.write("## 🟠 Low Coverage Public API Items (1-49% Coverage)\n\n")

                by_file = {}
                for item in report.low_coverage_functions:
                    file_key = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                    if file_key not in by_file:
                        by_file[file_key] = []
                    by_file[file_key].append(item)

                for file_path, items in sorted(by_file.items()):
                    f.write(f"### {file_path}\n\n")
                    for item in sorted(items, key=lambda x: x.name):
                        coverage = item.coverage
                        if coverage and coverage.lines_total > 0:
                            line_pct = (coverage.lines_covered / coverage.lines_total) * 100
                            f.write(f"- **{item.name}** ({item.kind}) - **{line_pct:.1f}%**")
                        else:
                            f.write(f"- **{item.name}** ({item.kind}) - **Limited data**")

                        if item.line_number:
                            f.write(f" - Line {item.line_number}")
                        f.write("\n")
                    f.write("\n")

            # Partially covered functions
            if report.partially_covered_functions:
                f.write("## 🟡 Partial Coverage Public API Items (50-94% Coverage)\n\n")

                by_file = {}
                for item in report.partially_covered_functions:
                    file_key = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                    if file_key not in by_file:
                        by_file[file_key] = []
                    by_file[file_key].append(item)

                for file_path, items in sorted(by_file.items()):
                    f.write(f"### {file_path}\n\n")
                    for item in sorted(items, key=lambda x: x.name):
                        coverage = item.coverage
                        if coverage and coverage.lines_total > 0:
                            line_pct = (coverage.lines_covered / coverage.lines_total) * 100
                            f.write(f"- **{item.name}** ({item.kind}) - **{line_pct:.1f}%**")
                        else:
                            f.write(f"- **{item.name}** ({item.kind}) - **Limited data**")

                        if item.line_number:
                            f.write(f" - Line {item.line_number}")
                        f.write("\n")
                    f.write("\n")

            # Well covered functions (for completeness)
            if report.well_covered_functions:
                f.write("## ✅ Well Covered Public API Items (≥95% Coverage)\n\n")
                f.write(
                    "**Threshold**: ≥95% line coverage - These items meet or exceed the well-covered threshold.\n\n"
                )
                f.write(
                    f"These {len(report.well_covered_functions)} items have excellent test coverage:\n\n"
                )

                # Just show a summary by file
                by_file = {}
                for item in report.well_covered_functions:
                    file_key = item.file_path.replace(str(Path.cwd()), "").lstrip("/")
                    if file_key not in by_file:
                        by_file[file_key] = 0
                    by_file[file_key] += 1

                for file_path, count in sorted(by_file.items()):
                    f.write(f"- **{file_path}**: {count} well-covered items (≥95% coverage)\n")
                f.write("\n")

            # Recommendations
            f.write("## Recommendations\n\n")
            f.write("1. **Priority 1**: Add tests for uncovered public API items\n")
            f.write("2. **Priority 2**: Improve coverage for partially covered items\n")
            f.write("3. **Priority 3**: Add parameter-specific tests for complex functions\n")
            f.write("4. **Priority 4**: Add edge case and error condition tests\n\n")

            f.write("## How to Use This Report\n\n")
            f.write("1. Focus on the 🔴 **Uncovered** section first\n")
            f.write("2. For each uncovered item, write unit tests that:\n")
            f.write("   - Test the main functionality\n")
            f.write("   - Test each parameter combination\n")
            f.write("   - Test error conditions and edge cases\n")
            f.write(
                "3. Use the 🟡 **Partially Covered** section to identify gaps in existing tests\n"
            )
            f.write("4. Re-run this report after adding tests to track progress\n\n")

            f.write("---\n")
            f.write(
                "*This report was generated by cross-referencing griffe API detection with pytest coverage data.*\n"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Generate API coverage report for unit or integration tests"
    )
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        help="Path to pytest coverage XML file",
    )
    parser.add_argument(
        "--api-snapshot",
        type=Path,
        default=Path("api_snapshot.json"),
        help="Path to griffe API snapshot JSON file (default: api_snapshot.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for the coverage report",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["tsv", "markdown"],
        default="tsv",
        help="Output format (default: tsv)",
    )
    parser.add_argument(
        "--test-type",
        type=str,
        choices=["unit", "integ"],
        default="unit",
        help="Type of tests to analyze: 'unit' or 'integ' (default: unit)",
    )
    parser.add_argument(
        "--project-root", type=Path, default=Path.cwd(), help="Project root directory"
    )

    args = parser.parse_args()

    # Set defaults based on test type if not specified
    if args.coverage_xml is None:
        if args.test_type == "integ":
            args.coverage_xml = Path("build/coverage/integ-coverage.xml")
        else:
            args.coverage_xml = Path("build/coverage/coverage.xml")

    if args.output is None:
        ext = "tsv" if args.format == "tsv" else "md"
        if args.test_type == "integ":
            args.output = Path(f"integ_coverage_report.{ext}")
        else:
            args.output = Path(f"api_coverage_report.{ext}")

    try:
        # Initialize analyzer
        analyzer = ApiCoverageAnalyzer(args.project_root)

        # Load data
        print(f"Loading coverage data from {args.coverage_xml}")
        analyzer.load_coverage_data(args.coverage_xml)

        print(f"Loading API snapshot from {args.api_snapshot}")
        analyzer.load_api_snapshot(args.api_snapshot)

        # Analyze coverage
        test_type_label = "integration test" if args.test_type == "integ" else "unit test"
        print(f"Analyzing {test_type_label} API coverage...")
        report = analyzer.analyze_coverage()

        # Generate report
        print(f"Generating {args.format.upper()} report to {args.output}")
        generator = ReportGenerator()
        if args.format == "tsv":
            generator.generate_tsv_report(report, args.output)
        else:
            generator.generate_markdown_report(report, args.output)

        # Print summary
        print(f"\n📊 {test_type_label.title()} API Coverage Summary:")
        print(f"   Total API items: {report.total_api_items}")
        print(f"   Covered items: {report.covered_api_items}")
        print(f"   Coverage: {report.coverage_percentage:.1f}%")
        print(f"   Uncovered: {report.uncovered_api_items}")
        print(f"\n📝 Report saved to: {args.output}")

        # Exit with error code if coverage is low (only for unit tests)
        if args.test_type == "unit" and report.coverage_percentage < 80:
            print(f"\n⚠️  API coverage is below 80% ({report.coverage_percentage:.1f}%)")
            sys.exit(1)
        else:
            print(f"\n✅ {test_type_label.title()} API coverage: {report.coverage_percentage:.1f}%")

    except Exception as e:
        print(f"Error generating API coverage report: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

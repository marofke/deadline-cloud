#!/usr/bin/env python3
"""
Generate a spreadsheet from the deadline-cloud API snapshot.

This script parses the API snapshot JSON and creates a CSV file
that can be imported into spreadsheet applications.
"""

import ast
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def scan_package_for_usage(package_path: Path, api_items: List[Dict[str, str]]) -> Dict[str, Set[str]]:
    """
    Scan a package directory for usage of API items.
    
    Returns a dict mapping API item keys to sets of package names that use them.
    """
    package_name = package_path.name
    usage_map: Dict[str, Set[str]] = {}
    
    # Find all Python files
    python_files = list(package_path.rglob("*.py"))
    
    for py_file in python_files:
        try:
            content = py_file.read_text(encoding='utf-8')
            
            # Parse the file to extract imports and usage
            try:
                tree = ast.parse(content, filename=str(py_file))
            except SyntaxError:
                # Skip files with syntax errors
                continue
            
            # Track what's imported from deadline
            # Maps: local_name -> (full_module_path, imported_name_or_None)
            imported_items = {}
            # Also track which modules are imported (for submodule detection)
            imported_modules = set()
            
            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith('deadline'):
                            local_name = alias.asname if alias.asname else alias.name
                            imported_items[local_name] = (alias.name, None)
                            imported_modules.add(alias.name)
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith('deadline'):
                        imported_modules.add(node.module)
                        for alias in node.names:
                            local_name = alias.asname if alias.asname else alias.name
                            imported_items[local_name] = (node.module, alias.name)
            
            # Now check for usage of each API item
            for item in api_items:
                item_key = f"{item['module']}|{item['class']}|{item['function']}|{item['member']}"
                
                # Check if this item is imported
                module = item['module']
                class_name = item['class']
                function_name = item['function']
                member_name = item['member']
                
                # Check various import patterns
                found = False
                
                # Pattern 1: Direct import - from module import ClassName/function_name/member_name
                if class_name and not function_name and not member_name:
                    # Looking for a class
                    for local, (imp_module, imp_name) in imported_items.items():
                        if imp_module == module and imp_name == class_name:
                            found = True
                            break
                elif function_name and not member_name:
                    # Looking for a function (could be module-level or class method)
                    if class_name:
                        # Class method - check if class is imported
                        for local, (imp_module, imp_name) in imported_items.items():
                            if imp_module == module and imp_name == class_name:
                                found = True
                                break
                    else:
                        # Module-level function
                        for local, (imp_module, imp_name) in imported_items.items():
                            if imp_module == module and imp_name == function_name:
                                found = True
                                break
                elif member_name:
                    # Looking for a member/attribute
                    if class_name:
                        # Class attribute - check if class is imported
                        for local, (imp_module, imp_name) in imported_items.items():
                            if imp_module == module and imp_name == class_name:
                                found = True
                                break
                    else:
                        # Module-level attribute - check if it's directly imported
                        for local, (imp_module, imp_name) in imported_items.items():
                            if imp_module == module and imp_name == member_name:
                                found = True
                                break
                else:
                    # Just a module - check if module is imported exactly
                    if module in imported_modules:
                        found = True
                
                if found:
                    if item_key not in usage_map:
                        usage_map[item_key] = set()
                    usage_map[item_key].add(package_name)
        
        except Exception as e:
            # Skip files that can't be read
            continue
    
    return usage_map


def find_usage_across_packages(api_items: List[Dict[str, str]], oss_dir: Path) -> Dict[str, Set[str]]:
    """
    Find usage of API items across all deadline-cloud-for-* and deadline-cloud-worker-agent packages.
    """
    print("\nScanning packages for API usage...")
    
    all_usage: Dict[str, Set[str]] = {}
    
    # Find all relevant packages
    packages = []
    if oss_dir.exists():
        for item in oss_dir.iterdir():
            if item.is_dir() and (item.name.startswith('deadline-cloud-for-') or item.name == 'deadline-cloud-worker-agent'):
                packages.append(item)
    
    if not packages:
        print(f"Warning: No packages found in {oss_dir}")
        return all_usage
    
    print(f"Found {len(packages)} packages to scan:")
    for pkg in packages:
        print(f"  - {pkg.name}")
    
    # Scan each package
    for package_path in packages:
        print(f"Scanning {package_path.name}...")
        usage_map = scan_package_for_usage(package_path, api_items)
        
        # Merge results
        for item_key, package_names in usage_map.items():
            if item_key not in all_usage:
                all_usage[item_key] = set()
            all_usage[item_key].update(package_names)
    
    return all_usage


def extract_api_items(
    obj: Dict[str, Any],
    module_path: str = "",
    class_name: Optional[str] = None,
    results: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """
    Recursively extract API items from the snapshot.
    
    Returns a list of dicts with keys: module, class, function, member
    """
    if results is None:
        results = []
    
    kind = obj.get("kind")
    name = obj.get("name", "")
    
    # Build the current module path
    if kind == "module" and name:
        current_module = f"{module_path}.{name}" if module_path else name
    else:
        current_module = module_path
    
    # Process based on kind
    if kind == "module":
        # Add module entry
        if name and not name.startswith("_"):  # Skip private modules
            results.append({
                "module": current_module,
                "class": "",
                "function": "",
                "member": "",
                "used_by": ""
            })
        
        # Process members
        members = obj.get("members", {})
        for member_name, member_obj in members.items():
            if not member_name.startswith("_"):  # Skip private members
                extract_api_items(member_obj, current_module, class_name, results)
    
    elif kind == "class":
        # Add class entry
        if name and not name.startswith("_"):
            results.append({
                "module": module_path,
                "class": name,
                "function": "",
                "member": "",
                "used_by": ""
            })
            
            # Process class members
            members = obj.get("members", {})
            for member_name, member_obj in members.items():
                if not member_name.startswith("_"):  # Skip private members
                    extract_api_items(member_obj, module_path, name, results)
    
    elif kind == "function":
        # Add function entry
        if name and not name.startswith("_"):
            results.append({
                "module": module_path,
                "class": class_name or "",
                "function": name,
                "member": "",
                "used_by": ""
            })
    
    elif kind == "attribute":
        # Add attribute/member entry
        if name and not name.startswith("_"):
            results.append({
                "module": module_path,
                "class": class_name or "",
                "function": "",
                "member": name,
                "used_by": ""
            })
    
    # Note: We skip "alias" kind as those are typically imports
    
    return results


def write_csv(api_items: List[Dict[str, str]], output_path: Path) -> None:
    """
    Write API items to a CSV file.
    """
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["module", "class", "function", "member", "used_by"])
        writer.writeheader()
        writer.writerows(api_items)


def write_markdown_table(api_items: List[Dict[str, str]], output_path: Path) -> None:
    """
    Write API items to a Markdown table that can be copied into spreadsheet software.
    """
    with open(output_path, 'w') as f:
        # Header
        f.write("| Module | Class | Function | Member | Used By |\n")
        f.write("|--------|-------|----------|--------|----------|\n")
        
        # Rows
        for item in api_items:
            f.write(f"| {item['module']} | {item['class']} | {item['function']} | {item['member']} | {item['used_by']} |\n")


def write_html_table(api_items: List[Dict[str, str]], output_path: Path) -> None:
    """
    Write API items to an HTML table that can be pasted into  spreadsheet software.
    """
    with open(output_path, 'w') as f:
        f.write("<table>\n")
        
        # Header
        f.write("  <tr>\n")
        f.write("    <th>Module</th>\n")
        f.write("    <th>Class</th>\n")
        f.write("    <th>Function</th>\n")
        f.write("    <th>Member</th>\n")
        f.write("    <th>Used By</th>\n")
        f.write("  </tr>\n")
        
        # Rows
        for item in api_items:
            f.write("  <tr>\n")
            f.write(f"    <td>{item['module']}</td>\n")
            f.write(f"    <td>{item['class']}</td>\n")
            f.write(f"    <td>{item['function']}</td>\n")
            f.write(f"    <td>{item['member']}</td>\n")
            f.write(f"    <td>{item['used_by']}</td>\n")
            f.write("  </tr>\n")
        
        f.write("</table>\n")


def write_tsv(api_items: List[Dict[str, str]], output_path: Path) -> None:
    """
    Write API items to a TSV (tab-separated values) file.
    TSV often works better than CSV for pasting into spreadsheet software.
    """
    with open(output_path, 'w') as f:
        # Header
        f.write("Module\tClass\tFunction\tMember\tUsed By\n")
        
        # Rows
        for item in api_items:
            f.write(f"{item['module']}\t{item['class']}\t{item['function']}\t{item['member']}\t{item['used_by']}\n")


def main():
    # Check for snapshot file
    snapshot_path = Path("snapshot.json")
    if not snapshot_path.exists():
        print(f"Error: {snapshot_path} not found")
        print("Run: hatch run docs:generate-api-snapshot")
        sys.exit(1)
    
    # Load the snapshot
    print(f"Loading {snapshot_path}...")
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    
    # Extract API items
    print("Extracting API items...")
    api_items = extract_api_items(snapshot)
    
    # Find usage across packages
    oss_dir = Path.home() / "workplace" / "oss"
    usage_map = find_usage_across_packages(api_items, oss_dir)
    
    # Update api_items with usage information
    for item in api_items:
        item_key = f"{item['module']}|{item['class']}|{item['function']}|{item['member']}"
        if item_key in usage_map:
            # Sort package names for consistent output
            packages = sorted(usage_map[item_key])
            item['used_by'] = ', '.join(packages)
        else:
            item['used_by'] = ''
    
    # Calculate statistics
    modules = sum(1 for item in api_items if item['module'] and not item['class'] and not item['function'] and not item['member'])
    classes = sum(1 for item in api_items if item['class'] and not item['function'] and not item['member'])
    functions = sum(1 for item in api_items if item['function'])
    members = sum(1 for item in api_items if item['member'])
    used_items = sum(1 for item in api_items if item['used_by'])
    
    print(f"\nFound {len(api_items)} API items:")
    print(f"  - {modules} modules")
    print(f"  - {classes} classes")
    print(f"  - {functions} functions/methods")
    print(f"  - {members} attributes/members")
    print(f"  - {used_items} items used by downstream packages")
    
    # Write outputs
    csv_path = Path("api_spreadsheet.csv")
    tsv_path = Path("api_spreadsheet.tsv")
    md_path = Path("api_spreadsheet.md")
    html_path = Path("api_spreadsheet.html")
    
    print(f"\nWriting CSV to {csv_path}...")
    write_csv(api_items, csv_path)
    
    print(f"Writing TSV to {tsv_path}...")
    write_tsv(api_items, tsv_path)
    
    print(f"Writing Markdown table to {md_path}...")
    write_markdown_table(api_items, md_path)
    
    print(f"Writing HTML table to {html_path}...")
    write_html_table(api_items, html_path)
    
    print(f"\n✓ Files created:")
    print(f"  - {tsv_path} (RECOMMENDED: Open in text editor, copy all, paste into spreadsheet software)")
    print(f"  - {csv_path} (import into Excel, then copy/paste to spreadsheet software)")
    print(f"  - {md_path} (copy/paste into spreadsheet software)")
    print(f"  - {html_path} (for reference)")
    print(f"\n📋 Best method for spreadsheet software:")
    print(f"  1. Create a new spreadsheet software document")
    print(f"  2. Open {tsv_path} in a text editor")
    print(f"  3. Select all (Ctrl+A / Cmd+A) and copy")
    print(f"  4. Paste into spreadsheet software - it will auto-create a table!")


if __name__ == "__main__":
    main()

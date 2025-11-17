# API Spreadsheet Generator

This script generates a spreadsheet view of the deadline-cloud public API from the API snapshot.

## Usage

1. Generate the API snapshot:
   ```bash
   hatch run docs:generate-api-snapshot
   ```

2. Run the script:
   ```bash
   python3 generate_api_spreadsheet.py
   ```

3. Import into spreadsheet software:
   - **Option 1 (TSV - RECOMMENDED)**: 
     1. Create a new document in your spreadsheet software
     2. Open `api_spreadsheet.tsv` in a text editor
     3. Select all (Ctrl+A / Cmd+A) and copy
     4. Paste - it will automatically create a table!
   - **Option 2 (CSV via Excel)**: 
     1. Open `api_spreadsheet.csv` in Excel
     2. Select all and copy
     3. Paste into a document
   - **Option 3 (Markdown)**: 
     1. Create a new document
     2. Copy content from `api_spreadsheet.md` and paste

## Output Format

The spreadsheet has four columns:

- **Module**: The Python module path (e.g., `deadline.job_attachments.upload`)
- **Class**: The class name (if the item is a class or class member)
- **Function**: The function/method name (if the item is a function)
- **Member**: The attribute/member name (if the item is an attribute)

Some rows will have empty columns depending on the type of API item:
- Module-only entries: Only the Module column is filled
- Class entries: Module and Class columns are filled
- Function entries: Module, Class (if method), and Function columns are filled
- Attribute entries: Module, Class (if class attribute), and Member columns are filled

## Files Generated

- `api_spreadsheet.tsv` - Tab-separated values (RECOMMENDED - just copy/paste!)
- `api_spreadsheet.csv` - CSV format for importing into spreadsheet applications
- `api_spreadsheet.html` - HTML table format
- `api_spreadsheet.md` - Markdown table format

## Regenerating

Since the script reads from `snapshot.json`, you can easily regenerate the spreadsheet whenever the API changes:

```bash
hatch run docs:generate-api-snapshot && python3 generate_api_spreadsheet.py
```

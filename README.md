# PubMed Proximity Search with Wildcards

This Flask app addresses the limitation in PubMed where proximity searches cannot be performed together with wildcard search terms. 

## Features

- Input two PubMed title/abstract search terms, each containing one wildcard (e.g., `canc*` and `treat*`).
- Retrieve all variants of the search terms.
- Select desired variants using checkboxes.
- Specify the proximity between the two search terms.
- Generate output combining the selected variants with the specified proximity which can be fed into pubmed.

## Usage (if you want to run it locally, make sure to put a valid NCBI_API_KEY in the main.py script)

1. Clone the repository:
   ```bash
   git clone https://github.com/Rinus-Verdonschot-UB/remi.git
   ```

2. Navigate to the project directory:
   ```bash
   cd remi
   ```

3. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```

4. Activate the virtual environment:
   - On macOS and Linux:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```

5. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

6. Run the app:
   ```bash
   flask run
   ```

7. Open your web browser and go to:
   ```
   http://127.0.0.1:5000
   ```

## Example

1. Input your search terms with wildcards (e.g., `canc*` and `treat*`).
2. Select the variants you want to include in the search.
3. Specify the proximity (e.g., within 5 words).
4. Click "Generate Output" to get the combined search terms with the specified proximity.

## Working Version
A working version can be found at: https://remi-427811.ew.r.appspot.com/

## Contributing
Contributions are of course welcome! Please open an issue or submit a pull request.

# import the libraries, heavily inspired by Ankie's script ;-)
import xml.etree.ElementTree as ET
import requests
import pandas as pd
import time
from collections import Counter
import os
import re
from flask import Flask, request, render_template, jsonify, stream_with_context, Response
from metapub import PubMedFetcher
import json
from eutils._internal.queryservice import QueryService

# Set NCBI API key (uncomment and replace with your actual key)
#set NCBI_API_KEY="xxxyyyzzz"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'

# Progress dictionary to keep track of queries and variants
progress = {
    "term1_query": "",
    "term2_query": "",
    "term1_variants": Counter(),
    "term2_variants": Counter()
}

# Specify an alternate cache directory, this is necessary as gunicorn (i.e., Googles app engine) does not allow the cache to be saved anywhere else except in tmp.
alt_cache_dir = '/tmp/eutils_cache'

# Function to get the PMIDs from PubMed
def get_pmids(query, retmax=1000):
    fetch = PubMedFetcher(cachedir=alt_cache_dir)
    print(f"Fetching PMIDs for query: {query}")  # Debug print
    return fetch.pmids_for_query(query=query, retmax=retmax)

# Function to extract the titles and abstracts from the articles
def extract_title_abstract(pmid_chunk):
    pmid_str = ','.join(pmid_chunk)
    efetch = f"http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id={pmid_str}"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Fetching articles for PMIDs: {pmid_str}")  # Debug print, just so we can see what is going on. 
            response = requests.get(efetch)                    # To see the debug in gunicorn (google), you can do: gcloud app logs tail -s default
            response.raise_for_status()
            root = ET.fromstring(response.content)
            articles = []

            for article in root.findall("PubmedArticle"):
                pmid = article.find("MedlineCitation/PMID").text
                title = article.find("MedlineCitation/Article/ArticleTitle").text
                abstract = article.find("MedlineCitation/Article/Abstract/AbstractText")
                if abstract is not None:
                    abstract_text = ' '.join([elem.text if elem.text is not None else '' for elem in abstract])
                else:
                    abstract_text = "No abstract available"
                articles.append({"pmid": pmid, "title": title, "abstract": abstract_text})

            return articles

        except ET.ParseError as e:
            print(f"ParseError: {e}, attempt {attempt + 1} of {max_retries}")  # In case of error, we wanna know what is going on.
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait a bit before retrying
                continue
            else:
                return []
        except requests.RequestException as e:
            print(f"RequestException: {e}, attempt {attempt + 1} of {max_retries}")  # In case of exception, we wanna know what is going on.
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return []

# Function to chunk PMIDs into smaller groups (N=200 is max we can put in pubmed entrez per request)
def chunk_pmids(pmids, chunk_size=200):
    for i in range(0, len(pmids), chunk_size):
        yield pmids[i:i + chunk_size]

# Function to find variants of a search term
def find_variants(initial_query):
    variants = Counter()
    discovered_variants = set()
    current_query = initial_query

    def update_exclusion_query(base_query, exclusions):
        if exclusions:
            exclusion_part = ' OR '.join([f'{variant}[tiab]' for variant in exclusions])
            return f'{base_query} NOT ({exclusion_part})'
        return base_query

    while True:
        initial_pmids = get_pmids(current_query)
        if not initial_pmids:
            break

        new_variants_found = False
        for pmid_chunk in chunk_pmids(initial_pmids, chunk_size=200):
            articles = extract_title_abstract(pmid_chunk)
            for article in articles:
                text = f"{article['title']} {article['abstract']}".lower()
                words = re.findall(r'\b' + re.escape(initial_query.rstrip('[tiab]').rstrip('*').lower()) + r'\w*\b', text)
                for word in words:
                    if word not in discovered_variants:
                        discovered_variants.add(word)
                        variants[word] += 1
                        new_variants_found = True
                    else:
                        variants[word] += 1

        if not new_variants_found:
            break

        current_query = update_exclusion_query(initial_query, discovered_variants)

    return variants

# Route to render the main page, see also app.yaml, it refers to this route (rendering index.html)
@app.route('/')
def index():
    return render_template('index.html')

# Route to handle the search form submission
@app.route('/search', methods=['POST'])
def search():
    global progress
    term1_query = request.form['term1']
    term2_query = request.form['term2']

    # Ensure [tiab] is appended to the queries
    if '[tiab]' not in term1_query.lower():
        term1_query += '[tiab]'
    if '[tiab]' not in term2_query.lower():
        term2_query += '[tiab]'

    progress['term1_query'] = term1_query
    progress['term2_query'] = term2_query

    # Find variants for both terms
    progress['term1_variants'] = find_variants(term1_query)
    progress['term2_variants'] = find_variants(term2_query)

    return jsonify({"status": "started"})

# Route to stream the search progress
@app.route('/search_stream', methods=['GET'])
def search_stream():
    global progress

    def generate():
        yield f"data: Variants for Term 1 ({progress['term1_query']}): {len(progress['term1_variants'])}\n\n"
        yield f"data: Variants for Term 2 ({progress['term2_query']}): {len(progress['term2_variants'])}\n\n"

        results = {
            "term1_variants": [{"word": word, "count": count} for word, count in progress['term1_variants'].most_common()],
            "term2_variants": [{"word": word, "count": count} for word, count in progress['term2_variants'].most_common()]
        }

        yield f"data: {json.dumps(results)}\n\n"
        yield "data: DONE\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# Function to combine both term variants for search
def generate_combined_terms(term1_variants, term2_variants, proximity):
    combined_terms = []
    for term1 in term1_variants:
        for term2 in term2_variants:
            combined_term = f'"{term1} {term2}"[tiab:~{proximity}]'
            combined_terms.append(combined_term)
            print(f"Generated combined term: {combined_term}")  # Debug print
    return " OR ".join(combined_terms)

# Route to generate the final combined query
@app.route('/generate_query', methods=['GET'])
def generate_query():
    term1_variants = [variant for variant, _ in progress['term1_variants'].most_common()]
    term2_variants = [variant for variant, _ in progress['term2_variants'].most_common()]
    proximity = request.args.get('proximity', default=2, type=int)
    
    combined_query = generate_combined_terms(term1_variants, term2_variants, proximity)
    print(f"Final combined query: {combined_query}")  # Debug print
    
    return jsonify({"combined_query": combined_query})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
# so in app.yaml make sure that the entrypoint refers to main:app (or whatever name we call it here, e.g., if you call it pubmed it should be pubmed:app)
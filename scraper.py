import os

from serpapi import GoogleSearch

# Search queries - location-based ones get {location} substituted
LOCATION_QUERIES = [
    "data analyst jobs in {location}",
    "data engineer jobs in {location}",
    "data scientist jobs in {location}",
]

REMOTE_QUERIES = [
    "remote data analyst jobs",
    "remote data engineer jobs",
    "remote data scientist jobs",
]


def fetch_jobs(location_name, max_pages_per_query=3):
    """
    Fetch jobs from Google Jobs via SerpAPI.
    Searches multiple query variations for both the location and remote.
    Returns a deduplicated list of job dicts.
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("Error: SERPAPI_KEY must be set in .env")
        print("Sign up for free at https://serpapi.com (100 searches/month)")
        return []

    all_jobs = []
    seen = set()  # dedupe by title+company

    queries = [q.format(location=location_name) for q in LOCATION_QUERIES]
    queries += REMOTE_QUERIES

    for query in queries:
        print(f"Searching: {query}")
        jobs = _search_google_jobs(api_key, query, location_name, max_pages_per_query)
        new = 0
        for job in jobs:
            key = (job.get("title", ""), job.get("company_name", ""))
            if key not in seen:
                seen.add(key)
                all_jobs.append(job)
                new += 1
        print(f"  {len(jobs)} results, {new} new ({len(all_jobs)} total)")

    return all_jobs


def _search_google_jobs(api_key, query, location_name, max_pages=3):
    """Search Google Jobs and paginate through results."""
    jobs = []
    start = 0

    for page in range(max_pages):
        params = {
            "engine": "google_jobs",
            "q": query,
            "location": location_name + ", United States",
            "hl": "en",
            "api_key": api_key,
        }
        if start > 0:
            params["start"] = start

        try:
            search = GoogleSearch(params)
            results = search.get_dict()

            batch = results.get("jobs_results", [])
            if not batch:
                break

            jobs.extend(batch)

            if not results.get("serpapi_pagination", {}).get("next"):
                break

            start += 10

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break

    return jobs

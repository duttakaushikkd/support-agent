# Architecture Notes

The service processes every ticket through ingestion, classification, retrieval,
routing, generation, validation, and persistent decision logging. `POST /tickets`
is the single-ticket interface; `python -m evaluation.harness` is the unattended
batch interface. The browser UI at `/` is a testing client for the same API and
does not bypass any safety controls.

The application uses SQLite for the decision log and Chroma for the persisted
documentation vector index. If Chroma cannot initialise, the retriever uses its
deterministic local vector fallback so batch evaluation still completes safely.

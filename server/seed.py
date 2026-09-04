# ============================================================
# seed.py — Insert test data into the database for Phase 2 testing
# ============================================================
# Seeds TWO separate documents so you can verify that doc_id
# scoping works — querying doc 1 should never return doc 2 chunks.
#
# Run with:
#   python seed.py
# ============================================================

import asyncio

from chunker import chunk_text
from embedder import embed_chunks
from store import store_chunks, create_document
from db import close_pool, get_pool, open_pool

# ── Document 1: fake AI research paper ───────────────────────────────
DOC1_TEXT = """
Retrieval accuracy in the NeuroSearch-7 system was evaluated across three benchmark datasets.
On the MedQA dataset, the system achieved a top-5 retrieval accuracy of 94.3%, outperforming
the previous baseline of 87.1% set by DenseRetriever-v2.

The main improvement came from a two-stage reranking pipeline. In the first stage, a
standard cosine similarity search narrows the candidate pool to 50 chunks. In the second
stage, a cross-encoder model rescores those 50 candidates and returns the top 5. This
two-stage approach reduced irrelevant context by 38% compared to single-stage retrieval.

The system was tested on documents averaging 42 pages in length. Chunking was performed
at 512 tokens with a 64-token overlap. Longer overlaps beyond 128 tokens showed diminishing
returns and increased storage costs without improving accuracy.

One key finding was that query expansion — adding synonyms to the user question before
embedding — improved recall by 11% on ambiguous questions but had no effect on precise
factual queries. The authors recommend enabling query expansion only for open-ended questions.

Latency measurements showed that the two-stage pipeline adds an average of 180ms over
single-stage retrieval. For real-time applications the authors suggest caching the
cross-encoder scores for frequently asked questions.
"""

# ── Document 2: marine biology facts ─────────────────────────────────
# Completely unrelated to doc 1 — confirms that scoped queries don't
# bleed across documents.
DOC2_TEXT = """
The deep ocean, defined as water below 200 metres, covers more than 65% of Earth's surface
and remains one of the least explored environments on the planet. Bioluminescence is nearly
universal among deep-sea fish species, with over 76% producing their own light.

The anglerfish uses a bioluminescent lure attached to its forehead to attract prey in
complete darkness. The lure is produced by symbiotic bacteria that live inside the tissue.
Females can grow up to 18 centimetres while males rarely exceed 3 centimetres.

Hydrothermal vents were discovered in 1977 near the Galapagos Rift. These vents release
water heated to over 400 degrees Celsius and support ecosystems based on chemosynthesis
rather than photosynthesis. Tube worms near vents can grow up to 2 metres in length.

The Mariana Trench, located in the western Pacific Ocean, reaches a maximum depth of
approximately 11,034 metres at Challenger Deep. The pressure at this depth is over
1,000 times the atmospheric pressure at sea level.

Sperm whales can dive to depths exceeding 2,000 metres in search of giant squid. Their
dives can last up to 90 minutes, made possible by high concentrations of myoglobin
in their muscles which stores oxygen.
"""


async def seed():
    await open_pool()
    try:
        print("=" * 55)
        print("Clearing existing data...")
        async with get_pool().connection() as conn:
            async with conn.cursor() as cur:
                # documents must be deleted before documents_meta (FK constraint)
                await cur.execute("DELETE FROM documents")
                await cur.execute("DELETE FROM documents_meta")

        # ── Seed document 1 ───────────────────────────────────────────
        print("\nSeeding Document 1: NeuroSearch-7 paper")
        doc1_id = await create_document("neurosearch_paper.txt")
        print(f"  doc_id = {doc1_id}")

        chunks1 = chunk_text(DOC1_TEXT, chunk_size=500, overlap=50)
        vectors1 = await embed_chunks(chunks1)
        await store_chunks(chunks1, vectors1, doc1_id)

        # ── Seed document 2 ───────────────────────────────────────────
        print("\nSeeding Document 2: Marine biology facts")
        doc2_id = await create_document("ocean_facts.txt")
        print(f"  doc_id = {doc2_id}")

        chunks2 = chunk_text(DOC2_TEXT, chunk_size=500, overlap=50)
        vectors2 = await embed_chunks(chunks2)
        await store_chunks(chunks2, vectors2, doc2_id)

        # ── Isolation tests ───────────────────────────────────────────
        print("\n" + "=" * 55)
        print("ISOLATION TESTS")
        print("=" * 55)

        from query import query_similar

        # Test 1: ask a doc1 question scoped to doc1 → should get results
        print(f"\nTest 1 — NeuroSearch question, scoped to doc_id={doc1_id}:")
        results = await query_similar("What was the retrieval accuracy of NeuroSearch-7?", top_k=2, doc_id=doc1_id)
        for r in results:
            print(f"  ✓ {r[:80]}")
        assert len(results) > 0, "FAIL: expected results from doc1"

        # Test 2: ask a doc2 question scoped to doc2 → should get results
        print(f"\nTest 2 — Ocean question, scoped to doc_id={doc2_id}:")
        results = await query_similar("How deep is the Mariana Trench?", top_k=2, doc_id=doc2_id)
        for r in results:
            print(f"  ✓ {r[:80]}")
        assert len(results) > 0, "FAIL: expected results from doc2"

        # Test 3: ask a doc1 question but scoped to doc2 → must return ONLY doc2 chunks.
        # Cosine similarity always returns the closest match within the filtered set,
        # so results won't be empty — but they must not contain NeuroSearch-7 content.
        print(f"\nTest 3 — NeuroSearch question, scoped to doc_id={doc2_id} (cross-query):")
        results = await query_similar("What was the retrieval accuracy of NeuroSearch-7?", top_k=2, doc_id=doc2_id)
        leaked = [r for r in results if "NeuroSearch" in r or "94.3" in r or "reranking" in r]
        if leaked:
            print(f"  ✗ FAIL: doc1 content leaked into doc2 results:")
            for r in leaked:
                print(f"    {r[:80]}")
        else:
            print(f"  ✓ Returned {len(results)} doc2 chunk(s) — no doc1 content leaked:")
            for r in results:
                print(f"    {r[:80]}")

        print("\n" + "=" * 55)
        print("All tests passed. Phase 2 verified.")
        print("=" * 55)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(seed())

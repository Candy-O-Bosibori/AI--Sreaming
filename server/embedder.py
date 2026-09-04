# ============================================================
# embedder.py — Convert text chunks into embedding vectors
# ============================================================
# An "embedding" is a list of 1536 numbers that represents the
# *meaning* of a piece of text. Similar sentences get similar
# numbers, so we can find related chunks by comparing numbers.
#
# Example:
#   "The ocean is deep"   → [0.02, -0.14, 0.87, ...] (1536 numbers)
#   "The sea is vast"     → [0.03, -0.13, 0.85, ...] (very similar!)
#   "I like pizza"        → [0.91,  0.44, -0.21, ...] (very different)
#
# We use OpenAI's text-embedding-3-small model to generate these.
# Install the SDK with: pip install openai
# ============================================================

import os
from typing import List
from openai import AsyncOpenAI   # OpenAI's async Python SDK — handles the API call for us

# Load .env file (same pattern used across the project)
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value

# Create the OpenAI client.
# It automatically reads OPENAI_API_KEY from the environment.
client = AsyncOpenAI()

# The model we're using to generate embeddings.
# Defined once here so it's easy to swap out later.
EMBEDDING_MODEL = "text-embedding-3-small"  # Outputs 1536-dimension vectors


async def embed_chunks(chunks: List[str]) -> List[List[float]]:
    """
    Take a list of text chunks and return a list of embedding vectors.

    Args:
        chunks: A list of strings (from chunker.py).

    Returns:
        A list of vectors — one vector per chunk.
        Each vector is a list of 1536 floats.

    Example:
        await embed_chunks(["The ocean is deep", "Fish live underwater"])
        → [[0.02, -0.14, ...], [0.05, -0.11, ...]]
    """

    # Send all chunks to OpenAI in a single API call.
    # The embeddings endpoint accepts a list — more efficient than
    # calling it once per chunk (fewer API round-trips, lower latency).
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=chunks,   # Pass the whole list at once
    )

    # response.data is a list of embedding objects, one per chunk.
    # We extract just the vector (.embedding) from each object.
    # The order matches the input — response.data[0] is for chunks[0], etc.
    vectors = [item.embedding for item in response.data]

    return vectors  # List of 1536-float lists, one per chunk

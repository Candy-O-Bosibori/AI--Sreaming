# ============================================================
# auth.py — Verify Supabase-issued JWTs and enforce @williams.edu
# ============================================================
# Every protected route takes `user: dict = Depends(get_current_user)`.
# FastAPI calls get_current_user() before the route body runs; if it
# raises HTTPException, the route never executes and that error is
# returned to the client instead.
#
# Where the token comes from:
#   Frontend signs in via Supabase Auth (Google OAuth) -> Supabase
#   returns a JWT -> frontend sends it as `Authorization: Bearer <jwt>`
#   on every API call -> this file verifies it on the way in.
#
# Why ES256 + a JWKS endpoint (not a shared HS256 secret):
#   Supabase projects created with the newer "JWT Signing Keys" feature
#   sign tokens asymmetrically (ES256) rather than with a single shared
#   secret. We verify by fetching Supabase's PUBLIC key from its JWKS
#   endpoint — nobody but Supabase can forge a valid signature, since
#   only Supabase holds the private key. PyJWKClient caches the fetched
#   key set in-process (default 5 minutes) so this doesn't mean a
#   network call on every request — see SUPABASE_JWKS_CLIENT below.
# ============================================================

import os

import jwt
from fastapi import Header, HTTPException

REQUIRED_EMAIL_DOMAIN = "@williams.edu"

# Built once at import time and reused across requests — PyJWKClient
# caches the fetched key set internally, so most requests verify the
# token signature locally with no network call at all.
_jwks_client = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.environ.get("SUPABASE_URL")
        if not supabase_url:
            raise HTTPException(status_code=500, detail="Server auth is not configured.")
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, cache_keys=True)
    return _jwks_client


def get_current_user(authorization: str = Header(...)) -> dict:
    """
    FastAPI dependency — verifies the bearer token and enforces the
    @williams.edu restriction (defense-in-depth: Supabase's "before
    user created" hook should already block sign-up for other domains,
    but every request re-checks here too in case that hook is ever
    misconfigured or bypassed).

    Args:
        authorization: The raw `Authorization` header, expected to be
            "Bearer <supabase_access_token>".

    Returns:
        {"id": <supabase user uuid>, "email": <verified email>}

    Raises:
        HTTPException(401): missing/malformed header, invalid or
            expired token.
        HTTPException(403): token is valid but the email isn't
            @williams.edu.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.PyJWKClientError:
        raise HTTPException(status_code=401, detail="Could not verify token signature.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    email = payload.get("email", "")
    if not email.lower().endswith(REQUIRED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to {REQUIRED_EMAIL_DOMAIN} accounts.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject claim.")

    return {"id": user_id, "email": email}

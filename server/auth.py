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
# Why HS256 + a shared secret (not JWKS/asymmetric keys):
#   Supabase projects still support a single "legacy JWT secret" for
#   HS256 verification. It's simpler than fetching/caching a JWKS
#   endpoint and is entirely sufficient at this app's scale.
# ============================================================

import os

import jwt
from fastapi import Header, HTTPException

REQUIRED_EMAIL_DOMAIN = "@williams.edu"


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
    # Read lazily (not at module import time) — main.py loads .env into
    # os.environ *after* importing this module, so a module-level read
    # would always see an empty value.
    supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not supabase_jwt_secret:
        # Fails loudly in any environment that forgot to set the secret,
        # rather than silently accepting unverifiable tokens.
        raise HTTPException(status_code=500, detail="Server auth is not configured.")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(
            token,
            supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
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

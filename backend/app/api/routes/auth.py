"""
Auth routes:
  POST /auth/register   — email/password signup
  POST /auth/login      — email/password login → JWT
  GET  /auth/github     — redirect to GitHub OAuth
  GET  /auth/github/callback — exchange code → JWT
  GET  /auth/me         — return current user
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import User
from app.schemas.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    response.set_cookie(
        key="jwt",
        value=token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,   # 1 Week     
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id)})
    response.set_cookie(
        key="jwt",
        value=token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,   # 1 Week     
    )
    return TokenResponse(access_token=token)


@router.get("/github")
async def github_oauth_redirect():
    """Returns the GitHub OAuth URL for the frontend to redirect to."""
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=repo,read:user,user:email"
    )
    return {"url": url}


@router.get("/github/callback", response_model=TokenResponse)
async def github_callback(code: str, response: Response, db: AsyncSession = Depends(get_db)):
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth failed: {data}")

    # Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        profile_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        email_resp = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )

    profile = profile_resp.json()
    github_id = str(profile["id"])
    display_name = profile.get("name") or profile.get("login")
    avatar_url = profile.get("avatar_url")

    # Find primary email
    email = profile.get("email")
    if not email:
        emails = email_resp.json()
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        email = primary["email"] if primary else f"{github_id}@github.noreply"

    # Upsert user
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if not user:
        # Check by email too
        result2 = await db.execute(select(User).where(User.email == email))
        user = result2.scalar_one_or_none()

    if user:
        user.github_id = github_id
        user.github_access_token = access_token
        user.display_name = display_name
        user.avatar_url = avatar_url
    else:
        user = User(
            email=email,
            github_id=github_id,
            github_access_token=access_token,
            display_name=display_name,
            avatar_url=avatar_url,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    response.set_cookie(
        key="jwt",
        value=token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,   # 1 Week     
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    response.delete_cookie(
        key="jwt",
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
    )

    return {"message": "Logged out successfully"}
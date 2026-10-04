from httpx import AsyncClient

EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery"


async def register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def login(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/auth/login", data={"username": email, "password": password})


async def test_register_creates_user_without_exposing_password(client: AsyncClient) -> None:
    response = await register(client, email="Alice@Example.com")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "id" in body and "created_at" in body
    assert "password" not in body and "hashed_password" not in body


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await register(client)

    response = await register(client, email="ALICE@example.com")

    assert response.status_code == 409


async def test_register_rejects_invalid_input(client: AsyncClient) -> None:
    assert (await register(client, email="not-an-email")).status_code == 422
    assert (await register(client, password="short")).status_code == 422


async def test_login_returns_bearer_token(client: AsyncClient) -> None:
    await register(client)

    response = await login(client)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await register(client)

    assert (await login(client, password="wrong-password")).status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    assert (await login(client, email="nobody@example.com")).status_code == 401


async def test_dummy_timing_password_does_not_log_in_real_user(client: AsyncClient) -> None:
    await register(client)

    response = await login(client, password="dummy-password-for-timing")

    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient) -> None:
    await register(client)
    token = (await login(client)).json()["access_token"]

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/users/me")).status_code == 401


async def test_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/users/me", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401

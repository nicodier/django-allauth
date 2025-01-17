from unittest.mock import ANY

from allauth.headless.constants import Flow
from allauth.mfa.models import Authenticator


def test_passkey_login(
    client, passkey, webauthn_authentication_bypass, headless_reverse
):
    with webauthn_authentication_bypass(passkey) as credential:
        resp = client.post(
            headless_reverse("headless:mfa:login_webauthn"),
            data={"credential": credential},
            content_type="application/json",
        )
    data = resp.json()
    assert data["data"]["user"]["id"] == passkey.user_id


def test_passkey_login_get_options(client, headless_reverse, db):
    resp = client.get(headless_reverse("headless:mfa:login_webauthn"))
    data = resp.json()
    assert data == {"status": 200, "data": {"request_options": {"publicKey": ANY}}}


def test_reauthenticate(
    auth_client,
    passkey,
    user_with_recovery_codes,
    webauthn_authentication_bypass,
    headless_reverse,
):
    # View recovery codes, confirm webauthn reauthentication is an option
    resp = auth_client.get(headless_reverse("headless:mfa:manage_recovery_codes"))
    assert resp.status_code == 401
    assert Flow.MFA_REAUTHENTICATE_WEBAUTHN in [
        flow["id"] for flow in resp.json()["data"]["flows"]
    ]

    # Get request options
    with webauthn_authentication_bypass(passkey):
        resp = auth_client.get(headless_reverse("headless:mfa:reauthenticate_webauthn"))
        data = resp.json()
        assert data["status"] == 200
        assert data["data"]["request_options"] == ANY

    # Reauthenticate
    with webauthn_authentication_bypass(passkey) as credential:
        resp = auth_client.post(
            headless_reverse("headless:mfa:reauthenticate_webauthn"),
            data={"credential": credential},
            content_type="application/json",
        )
        assert resp.status_code == 200
    resp = auth_client.get(headless_reverse("headless:mfa:manage_recovery_codes"))
    assert resp.status_code == 200


def test_update_authenticator(
    auth_client, headless_reverse, passkey, reauthentication_bypass
):
    data = {"id": passkey.pk, "name": "Renamed!"}
    resp = auth_client.put(
        headless_reverse("headless:mfa:manage_webauthn"),
        data=data,
        content_type="application/json",
    )
    # Reauthentication required
    assert resp.status_code == 401
    with reauthentication_bypass():
        resp = auth_client.put(
            headless_reverse("headless:mfa:manage_webauthn"),
            data=data,
            content_type="application/json",
        )
    assert resp.status_code == 200
    passkey.refresh_from_db()
    assert passkey.wrap().name == "Renamed!"


def test_delete_authenticator(
    auth_client, headless_reverse, passkey, reauthentication_bypass
):
    data = {"authenticators": [passkey.pk]}
    resp = auth_client.delete(
        headless_reverse("headless:mfa:manage_webauthn"),
        data=data,
        content_type="application/json",
    )
    # Reauthentication required
    assert resp.status_code == 401
    with reauthentication_bypass():
        resp = auth_client.delete(
            headless_reverse("headless:mfa:manage_webauthn"),
            data=data,
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert not Authenticator.objects.filter(pk=passkey.pk).exists()


def test_add_authenticator(
    user,
    auth_client,
    headless_reverse,
    webauthn_registration_bypass,
    reauthentication_bypass,
):
    resp = auth_client.get(headless_reverse("headless:mfa:manage_webauthn"))
    # Reauthentication required
    assert resp.status_code == 401

    with reauthentication_bypass():
        resp = auth_client.get(headless_reverse("headless:mfa:manage_webauthn"))
        data = resp.json()
        assert data["data"]["creation_options"] == ANY

        with webauthn_registration_bypass(user, False) as credential:
            resp = auth_client.post(
                headless_reverse("headless:mfa:manage_webauthn"),
                data={"credential": credential},
                content_type="application/json",
            )
            assert resp.status_code == 200
    assert (
        Authenticator.objects.filter(
            type=Authenticator.Type.WEBAUTHN, user=user
        ).count()
        == 1
    )

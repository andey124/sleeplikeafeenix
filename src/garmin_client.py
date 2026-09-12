from getpass import getpass
from pathlib import Path
from typing import Any

from garminconnect import Garmin, GarminConnectAuthenticationError

ENDPOINTS = (
    ("sleep", "get_sleep_data"),
    ("spo2", "get_spo2_data"),
    ("respiration", "get_respiration_data"),
    ("heart_rate", "get_heart_rates"),
    ("stress", "get_all_day_stress"),
    ("hrv", "get_hrv_data"),
    ("body_battery", "get_body_battery"),
    ("body_battery_events", "get_body_battery_events"),
    ("stats", "get_stats"),
)


def authenticate(tokenstore: Path) -> Garmin:
    tokenstore_text = str(tokenstore.expanduser())
    cached = Garmin()
    try:
        cached.login(tokenstore_text)
        return cached
    except (FileNotFoundError, GarminConnectAuthenticationError):
        pass

    email = input("Garmin email: ").strip()
    password = getpass("Garmin password: ")
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
    )
    del password
    client.login(tokenstore_text)
    return client


def fetch_date(client: Garmin, cdate: str) -> tuple[dict[str, Any], dict[str, str]]:
    payloads = {}
    errors = {}
    for endpoint, method_name in ENDPOINTS:
        try:
            method = getattr(client, method_name)
            payloads[endpoint] = (
                method(cdate, cdate)
                if method_name == "get_body_battery"
                else method(cdate)
            )
        except Exception as error:
            detail = (str(error).splitlines() or ["no details"])[0]
            errors[endpoint] = f"{type(error).__name__}: {detail}"
    return payloads, errors

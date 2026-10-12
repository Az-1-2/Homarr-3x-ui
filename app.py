import json
import logging
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

import psutil
import requests
from flask import Flask, jsonify


app = Flask(__name__)

X3UI_URL = os.environ["3XUI_URL"].rstrip("/")
X3UI_TOKEN = os.environ["3XUI_TOKEN"]
PORT = int(os.environ.get("PORT", "3000"))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default

        return int(float(value))

    except (TypeError, ValueError, OverflowError):
        return default


def to_bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
            "online",
            "enabled",
        }

    return default


def round_2(value):
    try:
        number = Decimal(str(value if value is not None else 0))

        return number.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def format_number(value):
    return f"{round_2(value):.2f}"


def format_bytes(value):
    try:
        value = Decimal(str(value if value is not None else 0))

    except (InvalidOperation, TypeError, ValueError):
        value = Decimal("0")

    units = ["B", "KB", "MB", "GB", "TB", "PB"]

    for unit in units:
        if value < Decimal("1024") or unit == units[-1]:
            return f"{round_2(value):.2f} {unit}"

        value /= Decimal("1024")

    return "0.00 B"


def parse_json_object(value):
    if isinstance(value, dict):
        return value

    if not isinstance(value, str) or not value.strip():
        return {}

    try:
        parsed = json.loads(value)

    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def system_info():
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")

    cpu_percent = psutil.cpu_percent(interval=0.5)
    uptime_seconds = int(time.time() - psutil.boot_time())

    load = (
        list(os.getloadavg())
        if hasattr(os, "getloadavg")
        else []
    )

    return {
        "cpuPercent": cpu_percent,
        "cpuPercentFormatted": format_number(cpu_percent),

        "memoryPercent": memory.percent,
        "memoryPercentFormatted": format_number(memory.percent),
        "memoryUsed": memory.used,
        "memoryTotal": memory.total,
        "memoryUsedFormatted": format_bytes(memory.used),
        "memoryTotalFormatted": format_bytes(memory.total),

        "swapPercent": swap.percent,
        "swapPercentFormatted": format_number(swap.percent),
        "swapUsed": swap.used,
        "swapTotal": swap.total,
        "swapUsedFormatted": format_bytes(swap.used),
        "swapTotalFormatted": format_bytes(swap.total),

        "diskPercent": disk.percent,
        "diskPercentFormatted": format_number(disk.percent),
        "diskUsed": disk.used,
        "diskTotal": disk.total,
        "diskUsedFormatted": format_bytes(disk.used),
        "diskTotalFormatted": format_bytes(disk.total),

        "uptimeSeconds": uptime_seconds,

        "load": load,
        "loadFormatted": [
            format_number(load_value)
            for load_value in load
        ],
    }


def empty_x3ui_info():
    return {
        "reachable": False,
        "inbounds": 0,
        "clients": 0,
        "enabledClients": 0,
        "onlineClients": 0,
        "uploadBytes": 0,
        "downloadBytes": 0,
        "upload": "0.00 B",
        "download": "0.00 B",
        "items": [],
    }


def x3ui_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {X3UI_TOKEN}",
        "User-Agent": "Homarr-3xUI-Widget/1.0",
    }


def request_x3ui(path):
    url = f"{X3UI_URL}{path}"

    logger.info("Requesting 3x-ui endpoint: %s", url)

    try:
        response = requests.get(
            url,
            headers=x3ui_headers(),
            timeout=10,
        )

    except requests.RequestException:
        logger.exception("Could not connect to 3x-ui")
        raise

    logger.info(
        "3x-ui response: HTTP %s, content-type=%s",
        response.status_code,
        response.headers.get("Content-Type", ""),
    )

    response.raise_for_status()

    try:
        payload = response.json()

    except ValueError as error:
        logger.error(
            "3x-ui returned invalid JSON: %s",
            response.text[:500],
        )

        raise ValueError(
            f"3x-ui returned invalid JSON: {response.text[:500]}"
        ) from error

    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(
            payload.get("msg")
            or payload.get("message")
            or "3x-ui API returned success=false"
        )

    return payload


def get_inbounds():
    payload = request_x3ui("/panel/api/inbounds/list")

    if not isinstance(payload, dict):
        raise ValueError("Unexpected response from 3x-ui")

    inbounds = payload.get("obj") or []

    if not isinstance(inbounds, list):
        raise ValueError("3x-ui inbound obj is not a list")

    return inbounds


def extract_clients(inbound):
    client_stats = inbound.get("clientStats")

    if isinstance(client_stats, list) and client_stats:
        return client_stats

    settings = parse_json_object(inbound.get("settings"))
    clients = settings.get("clients") or []

    return clients if isinstance(clients, list) else []


def get_client_id(client):
    return (
        client.get("id")
        or client.get("uuid")
        or client.get("clientId")
        or ""
    )


def get_client_email(client):
    return client.get("email") or client.get("remark") or ""


def get_traffic_values(traffic):
    upload = to_int(
        traffic.get(
            "up",
            traffic.get(
                "upload",
                traffic.get("uploadBytes", 0),
            ),
        )
    )

    download = to_int(
        traffic.get(
            "down",
            traffic.get(
                "download",
                traffic.get("downloadBytes", 0),
            ),
        )
    )

    online = to_bool(
        traffic.get(
            "online",
            traffic.get(
                "isOnline",
                traffic.get(
                    "onlineStatus",
                    traffic.get(
                        "clientOnline",
                        traffic.get("lastOnline", False),
                    ),
                ),
            ),
        )
    )

    return {
        "up": upload,
        "down": download,
        "online": online,
    }


def get_client_traffic_from_client(client):
    return get_traffic_values(client)


def get_traffic_object(payload):
    if not isinstance(payload, dict):
        return {}

    traffic = payload.get("obj")

    if isinstance(traffic, list):
        return traffic[0] if traffic else {}

    if isinstance(traffic, dict):
        return traffic

    traffic_keys = {
        "up",
        "down",
        "upload",
        "download",
        "uploadBytes",
        "downloadBytes",
    }

    return payload if traffic_keys.intersection(payload) else {}


def get_client_traffic_from_api(client):
    client_id = get_client_id(client)
    email = get_client_email(client)
    endpoints = []

    if email:
        endpoints.append(
            "/panel/api/inbounds/getClientTraffics/"
            + quote(str(email), safe="")
        )

    if client_id:
        endpoints.append(
            "/panel/api/inbounds/getClientTrafficsById/"
            + quote(str(client_id), safe="")
        )

    for endpoint in endpoints:
        try:
            payload = request_x3ui(endpoint)
            traffic = get_traffic_object(payload)

            if not traffic:
                logger.warning(
                    "No traffic object returned from %s: %s",
                    endpoint,
                    payload,
                )
                continue

            return get_traffic_values(traffic)

        except requests.HTTPError as error:
            response = getattr(error, "response", None)

            if response is not None:
                logger.warning(
                    "Traffic endpoint failed: %s - HTTP %s: %s",
                    endpoint,
                    response.status_code,
                    response.text[:500],
                )
            else:
                logger.warning(
                    "Traffic endpoint failed: %s - %s",
                    endpoint,
                    error,
                )

        except (
            requests.RequestException,
            RuntimeError,
            ValueError,
        ) as error:
            logger.warning(
                "Traffic endpoint failed: %s - %s",
                endpoint,
                error,
            )

    return {
        "up": 0,
        "down": 0,
        "online": False,
    }


def get_expiry_time(client):
    return to_int(
        client.get(
            "expiryTime",
            client.get(
                "expiry",
                client.get("expire", 0),
            ),
        )
    )


def x3ui_info():
    inbounds = get_inbounds()
    clients = []

    total_upload = 0
    total_download = 0
    enabled_clients = 0
    online_clients = 0

    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue

        inbound_name = (
            inbound.get("remark")
            or inbound.get("tag")
            or inbound.get("protocol")
            or ""
        )

        for client in extract_clients(inbound):
            if not isinstance(client, dict):
                continue

            enabled = to_bool(
                client.get("enable", True),
                default=True,
            )

            if enabled:
                enabled_clients += 1

            traffic = get_client_traffic_from_client(client)

            if not traffic["online"]:
                api_traffic = get_client_traffic_from_api(client)

                if (
                    api_traffic["up"] != 0
                    or api_traffic["down"] != 0
                    or api_traffic["online"]
                ):
                    traffic = api_traffic

            client_upload = traffic["up"]
            client_download = traffic["down"]
            client_online = traffic["online"]

            if client_online:
                online_clients += 1

            total_upload += client_upload
            total_download += client_download

            expiry_time = get_expiry_time(client)
            client_email = get_client_email(client)

            clients.append({
                "email": client_email,
                "id": get_client_id(client) or client_email,
                "enable": enabled,
                "online": client_online,
                "inbound": inbound_name,
                "upload": client_upload,
                "download": client_download,
                "uploadFormatted": format_bytes(client_upload),
                "downloadFormatted": format_bytes(client_download),
                "expiryTime": expiry_time,
                "expiryFormatted": (
                    "Never"
                    if expiry_time == 0
                    else str(expiry_time)
                ),
            })

    return {
        "reachable": True,
        "inbounds": len(inbounds),
        "clients": len(clients),
        "enabledClients": enabled_clients,
        "onlineClients": online_clients,
        "uploadBytes": total_upload,
        "downloadBytes": total_download,
        "upload": format_bytes(total_upload),
        "download": format_bytes(total_download),
        "items": clients,
    }


@app.get("/")
def index():
    """
    Root endpoint.

    This prevents a 404 if HAProxy or Homarr forwards
    /widget-api/ as /.
    """
    return jsonify({
        "ok": True,
        "service": "homarr-3x-ui",
        "endpoints": {
            "health": "/health",
            "dashboard": "/api/dashboard",
        },
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
    })


@app.get("/api/dashboard")
def dashboard():
    logger.info("Dashboard request received")

    result = {
        "system": system_info(),
        "x3ui": empty_x3ui_info(),
        "error": None,
    }

    try:
        result["x3ui"] = x3ui_info()

    except requests.HTTPError as error:
        response = getattr(error, "response", None)

        if response is not None:
            result["error"] = (
                f"3x-ui HTTP error {response.status_code}: "
                f"{response.text[:500]}"
            )

        else:
            result["error"] = f"3x-ui HTTP error: {error}"

        logger.error(result["error"])

    except requests.RequestException as error:
        result["error"] = f"3x-ui request failed: {error}"
        logger.error(result["error"])

    except ValueError as error:
        result["error"] = f"Invalid 3x-ui response: {error}"
        logger.error(result["error"])

    except Exception as error:
        logger.exception("Unexpected dashboard error")
        result["error"] = str(error)

    return jsonify(result)


if __name__ == "__main__":
    logger.info("Starting Homarr 3x-ui widget")
    logger.info("Listening on port %s", PORT)
    logger.info("3x-ui base URL: %s", X3UI_URL)

    app.run(
        host="0.0.0.0",
        port=PORT,
    )


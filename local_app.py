import os
from flask import request, send_from_directory
from pioreactor.web.app import create_app

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "pioreactor", "web", "static")

app = create_app()
app.static_folder = STATIC_DIR
app.static_url_path = "/static"


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.after_request
def rewrite_mqtt_config_for_frontend(response):
    if request.path == "/api/config/shared":
        text = response.get_data(as_text=True)
        text = text.replace("broker_address=mosquitto", "broker_address=localhost")
        response.set_data(text)
    return response


@app.after_request
def spa_catch_all(response):
    if response.status_code == 404:
        path = request.path
        if not path.startswith(("/api/", "/unit_api/", "/mcp/")):
            return send_from_directory(STATIC_DIR, "index.html")
    return response

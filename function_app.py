import os
import json
import requests
import azure.functions as func

from botbuilder.core import (
    BotFrameworkAdapterSettings,
    BotFrameworkAdapter,
    TurnContext,
    ActivityHandler,
)
from botbuilder.schema import Activity


# ---- Call Databricks Serving ----
def call_databricks_serving(user_text: str) -> str:
    host = os.environ["DATABRICKS_HOST"].rstrip("/")     # https://adb-xxx.azuredatabricks.net
    endpoint = os.environ["DATABRICKS_ENDPOINT"]         # serving endpoint name
    token = os.environ["DATABRICKS_TOKEN"]               # PAT

    url = f"{host}/serving-endpoints/{endpoint}/invocations"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # IMPORTANT: Adjust schema to match your endpoint.
    payload = {"inputs": {"prompt": user_text}}

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        return f"Databricks error {r.status_code}: {r.text}"

    data = r.json()

    # Common response shapes (adjust if your endpoint differs)
    if isinstance(data, dict):
        if "predictions" in data:
            return str(data["predictions"])
        if "choices" in data and data["choices"]:
            return data["choices"][0].get("text") or str(data["choices"][0])
        if "output" in data:
            return str(data["output"])

    return json.dumps(data)[:3500]


# ---- Bot Logic ----
class DbxBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("Please type a message.")
            return

        await turn_context.send_activity("Calling Databricks…")
        answer = call_databricks_serving(text)
        await turn_context.send_activity(answer)


# ---- Adapter / App ----
APP_ID = os.environ.get("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "")

adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)
bot = DbxBot()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="messages", methods=["POST"])
async def messages(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    async def logic(turn_context: TurnContext):
        await bot.on_turn(turn_context)

    await adapter.process_activity(activity, auth_header, logic)
    return func.HttpResponse(status_code=200)
@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("OK", status_code=200)

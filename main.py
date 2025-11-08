from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from openai import OpenAI
import os
import json
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Setup templates
templates = Jinja2Templates(directory="templates")

# Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# PubNub configuration
pubnub_publish_key = os.environ.get("PUBNUB_PUBLISH_KEY", "demo")
pubnub_subscribe_key = os.environ.get("PUBNUB_SUBSCRIBE_KEY", "demo")

pnconfig = PNConfiguration()
pnconfig.publish_key = pubnub_publish_key
pnconfig.subscribe_key = pubnub_subscribe_key
pnconfig.user_id = "server-instance"
pubnub_client = PubNub(pnconfig)

# OpenAI client
openai_api_key = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/message")
async def get_message():
    """Returns backend message as HTML fragment"""
    return HTMLResponse("<p>Hello World from FastAPI!</p>")


@app.get("/api/data")
async def get_data():
    """Returns Supabase data as HTML fragment"""
    try:
        # Query 'items' table from Supabase
        response = supabase.table('items').select("*").execute()
        if response.data and len(response.data) > 0:
            data_html = f"<pre>{json.dumps(response.data, indent=2)}</pre>"
        else:
            data_html = "<p>No data from Supabase (make sure to create an 'items' table)</p>"
        return HTMLResponse(data_html)
    except Exception as e:
        return HTMLResponse(f"<p>Error: {str(e)}</p>")


@app.get("/pingpong", response_class=HTMLResponse)
async def pingpong(request: Request):
    """Render the PubNub ping pong page"""
    return templates.TemplateResponse("pingpong.html", {
        "request": request,
        "pubnub_publish_key": pubnub_publish_key,
        "pubnub_subscribe_key": pubnub_subscribe_key
    })


@app.get("/api/pubnub/config")
async def get_pubnub_config():
    """Returns PubNub configuration"""
    return {
        "publish_key": pubnub_publish_key,
        "subscribe_key": pubnub_subscribe_key
    }


@app.post("/api/pubnub/publish/{channel}")
async def publish_message(channel: str, message: dict):
    """Publish a message to a PubNub channel"""
    try:
        envelope = pubnub_client.publish()\
            .channel(channel)\
            .message(message)\
            .sync()

        return {
            "status": "success",
            "timetoken": envelope.result.timetoken
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Render the chat page"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/api/chat")
async def chat(request: Request):
    """Handle chat messages with OpenAI"""
    if not openai_client:
        return {
            "error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."
        }

    try:
        body = await request.json()
        print(body)
        user_message = body.get("message", "")

        if not user_message:
            return {"error": "No message provided"}

        # Call OpenAI API
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a very concise assistant but super helpful assistant."},
                {"role": "user", "content": user_message}
            ],
            temperature=1,
            max_tokens=300
        )

        response_message = completion.choices[0].message.content

        return {"response": response_message}

    except Exception as e:
        return {"error": f"Error communicating with OpenAI: {str(e)}"}


@app.get("/resume", response_class=HTMLResponse)
async def resume_page(request: Request):
    """Render the resume parser page"""
    return templates.TemplateResponse("resume.html", {"request": request})


@app.post("/api/parse-resume")
async def parse_resume(request: Request):
    """Parse HTML resume/LinkedIn profile using OpenAI"""
    if not openai_client:
        print("❌ OpenAI client not configured.")
        return {"error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."}

    try:
        print("🟦 STEP 1: Reading request body...")
        body = await request.json()
        html_content = body.get("html_content", "")
        print(f"✅ Received HTML content length: {len(html_content)} characters")

        if not html_content:
            print("❌ No HTML content provided.")
            return {"error": "No HTML content provided"}

        # Prompt construction
        print("🟦 STEP 2: Constructing system and user prompts...")
        system_prompt = "You are a structured information extraction assistant."
        user_prompt = f"Extract key fields from this resume/profile HTML:\n\n{html_content}"
        print("✅ Prompts ready.")

        # Tool schema
        print("🟦 STEP 3: Defining key_parsed_elements tool schema...")
        key_parsed_elements_tool = {
    "type": "function",
    "function": {
        "name": "key_parsed_elements",
        "description": (
            "Parses resume or LinkedIn HTML/text and extracts exactly three fields — "
            "name, header, and location — returning a clean JSON object.\n\n"
            "The output must be a single JSON object with the following keys:\n"
            "• name: The candidate's full name as it appears at the top of the resume/profile.\n"
            "• header: The person's professional headline or short title (e.g., 'Data Engineer @ Wafra | MS in Applied Data Science').\n"
            "• location: The current city or region (e.g., 'New York City Metropolitan Area').\n\n"
            "Remove HTML tags, navigation items, and noise before extraction."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "The candidate's full name (usually top of resume or LinkedIn profile). "
                        "Exclude prefixes like Mr., Ms., Dr."
                    )
                },
                "header": {
                    "type": "string",
                    "description": (
                        "Professional headline or job title describing the person’s role or expertise. "
                        "Examples: 'Software Engineer at Google', 'Data Scientist | AI Research'."
                    )
                },
                "location": {
                    "type": "string",
                    "description": (
                        "Geographic area or city listed in the profile. Examples: "
                        "'New York City Metropolitan Area', 'San Francisco Bay Area'."
                    )
                },
            },
            "required": ["name", "header", "location"]
        }
    }
}

        print("✅ Tool schema defined.")

        # Supabase insert helper
        def insert_parsed_profile(profile_data: dict):
            print("🟧 STEP 6: Inserting into Supabase...")
            required_keys = ["name", "header", "location"]
            for key in required_keys:
                if key not in profile_data:
                    print(f"❌ Missing required key: {key}")
                    return {"error": f"Missing required field: {key}"}

            row = {
                "name": profile_data["name"],
                "header": profile_data["header"],
                "location": profile_data["location"],
                "created_at": datetime.utcnow().isoformat()
            }

            try:
                print(f"📤 Inserting row into Supabase: {row}")
                response = supabase.table("parsed_profiles").insert(row).execute()
                print("✅ Supabase insert successful.")
                return {"success": True, "data": response.data}
            except Exception as e:
                print(f"❌ Supabase insert failed: {e}")
                return {"error": str(e)}

        # Call OpenAI API
        print("🟦 STEP 4: Calling OpenAI API (model=gpt-5)...")
        completion = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1,
            tools=[key_parsed_elements_tool],
            tool_choice={"type": "function", "function": {"name": "key_parsed_elements"}},
        )

        print("✅ OpenAI API call completed.")
        print(f"🧾 Raw completion response keys: {list(completion.model_dump().keys())}")

        # Extract structured output
        print("🟦 STEP 5: Parsing OpenAI structured response...")
        message = completion.choices[0].message
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_call = message.tool_calls[0]
            args_json = tool_call.function.arguments
            print(f"📜 Raw arguments string: {args_json}")
            parsed_resume = json.loads(args_json)
            print(f"✅ Parsed JSON: {parsed_resume}")
        elif message.content:
            print("⚠️ No tool call found, falling back to content parsing...")
            try:
                parsed_resume = json.loads(message.content)
            except json.JSONDecodeError:
                print(f"❌ Could not decode JSON from message.content: {message.content}")
                parsed_resume = {"raw_output": message.content}
        else:
            print("❌ No valid tool_calls or content in response.")
            return {"error": "No valid output from OpenAI response."}

        # Insert into Supabase
        insert_result = insert_parsed_profile(parsed_resume)

        print("✅ All steps complete. Returning response.")
        return {
            "parsed_resume": parsed_resume,
            "insert_result": insert_result
        }

    except Exception as e:
        print(f"❌ Unhandled exception in /api/parse-resume: {e}")
        return {"error": f"Error parsing resume: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
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
        user_message = body.get("message", "")

        if not user_message:
            return {"error": "No message provided"}

        # Call OpenAI API
        completion = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a senior data engineer who has mastered data engineering. Be very brief"},
                {"role": "user", "content": user_message}
            ],
            max_tokens=50,
            temperature=0
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
        return {
            "error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."
        }

    try:
        body = await request.json()
        html_content = body.get("html_content", "")

        if not html_content:
            return {"error": "No HTML content provided"}

        # Create a prompt to parse the resume
        system_prompt = """You are a resume parser. Extract and format the key information from HTML content (from LinkedIn profiles or resumes) into only a JSON format. 
        Remove any HTML tags, navigation elements, or extraneous information.
Focus on extracting:
{
"name": "Random Name",
"contact_information": {
"location": "Bay Area"
},
"professional_summary": "Data Engineer @ Meta",
"work_experience": [
{
"company": "Meta",
"title": "Engineer",
"startDate": "May 2025",
"endDate": "Present",
"responsibilities": "I wrote pipelines"
}
],
"education": [
{
"school": "Stanford",
"degree": "Bachelor's Degree, Computer Science",
"startDate": "Not specified",
"endDate": "Not specified"
}
],
"skills": [
"Big Data",
"Machine Learning"
],
"certifications": [
{
"name": "Databricks Certified Professional",
"issuer": "Databricks",
"date": "Nov 2015"
}
],
"projects": [
{
"name": "Some Github Repo",
"dates": "Nov 2023 - Present",
"description": "A list of repos or something",
"associated_with": "DataExpert.io"
}
]
}
Format the output as clean JSON"""

        user_prompt = f"Please parse and format this resume into JSON:\n\n{html_content}\n\n"

        # Call OpenAI API
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "parse_resume",
                        "description": "Parse resume text into a structured schema with work experience, education, skills, certifications, and projects.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Full name of the person"},
                                "contact_information": {
                                    "type": "object",
                                    "properties": {
                                        "location": {"type": "string"}
                                    },
                                    "required": ["location"]
                                },
                                "professional_summary": {"type": "string"},
                                "work_experience": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "company": {"type": "string"},
                                            "title": {"type": "string"},
                                            "startDate": {"type": "string"},
                                            "endDate": {"type": "string"},
                                            "responsibilities": {"type": "string"}
                                        },
                                        "required": ["company", "title"]
                                    }
                                },
                                "education": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "school": {"type": "string"},
                                            "degree": {"type": "string"},
                                            "startDate": {"type": "string"},
                                            "endDate": {"type": "string"}
                                        },
                                        "required": ["school", "degree"]
                                    }
                                },
                                "skills": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "certifications": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "issuer": {"type": "string"},
                                            "date": {"type": "string"}
                                        },
                                        "required": ["name", "issuer"]
                                    }
                                },
                                "projects": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "dates": {"type": "string"},
                                            "description": {"type": "string"},
                                            "associated_with": {"type": "string"}
                                        },
                                        "required": ["name"]
                                    }
                                }
                            },
                            "required": ["name", "contact_information", "professional_summary"]
                        }
                    }
                }
            ]
        )

        parsed_resume = completion.choices[0].message.content
        insert_resume(json.loads(parsed_resume))

        return {"parsed_resume": parsed_resume}

    except Exception as e:
        return {"error": f"Error parsing resume: {str(e)}"}


def insert_resume(resume_json: dict) -> dict:
    """
    Inserts a parsed resume JSON object into the Supabase 'resumes' table.

    Args:
        resume_json (dict): Resume data matching the JSON schema.

    Returns:
        dict: The inserted row data from Supabase.
    """
    # Ensure valid JSON
    if not isinstance(resume_json, dict):
        raise ValueError("resume_json must be a Python dict")

    try:
        response = (
            supabase.table("resumes")
            .insert({"resume": resume_json})
            .execute()
        )

        if response.data:
            print("✅ Resume inserted successfully!")
            return response.data[0]
        else:
            raise Exception(f"Insertion failed: {response}")

    except Exception as e:
        print(f"❌ Error inserting resume: {e}")
        raise

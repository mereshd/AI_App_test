from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from openai import OpenAI
import os
import json
import base64
from typing import Optional
import io
from PyPDF2 import PdfReader
from PIL import Image

from supabase_lib import query_rag_content
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
    """Handle chat messages with OpenAI and RAG"""
    if not openai_client:
        return {
            "error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."
        }

    try:
        body = await request.json()
        user_message = body.get("message", "")

        if not user_message:
            return {"error": "No message provided"}

        # Generate embedding for the user message
        embedding_response = openai_client.embeddings.create(
            input=user_message,
            model='text-embedding-3-small'
        )
        query_embedding = embedding_response.data[0].embedding

        # Query rag_content table with cosine distance to get top 10 results
        rag_results = supabase.rpc(
            'match_documents_by_document_type',
            {
                'query_embedding': query_embedding,
                'match_count': 10,
                'query_document_type': 'job'
            }
        ).execute()

        # Extract context from RAG results
        context_items = []
        if rag_results.data:
            for item in rag_results.data:
                if item['similarity'] > .3:
                    context_items.append(item.get('context', ''))

        print(len(context_items))
        # Build context string
        rag_context = "\n\n".join(context_items) if context_items else "No relevant context found."

        # Call OpenAI API with RAG context
        completion = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"You are a senior data engineer who has mastered data engineering. Use the following context to answer questions:\n\n{rag_context}"},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0
        )

        response_message = completion.choices[0].message.content

        return {
            "response": response_message,
            "rag_results": rag_results.data if rag_results.data else []
        }

    except Exception as e:
        return {"error": f"Error communicating with OpenAI: {str(e)}"}


@app.get("/resume", response_class=HTMLResponse)
async def resume_page(request: Request):
    """Render the resume parser page"""
    return templates.TemplateResponse("resume.html", {"request": request})


@app.get("/resume-with-matching", response_class=HTMLResponse)
async def resume_with_matching_page(request: Request):
    """Render the resume parser page"""
    return templates.TemplateResponse("resume_with_matching.html", {"request": request})


@app.post('/api/parse-resume-with-matching')
async def parse_resume_with_matching(request: Request):
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

        print('user prompt is', user_prompt)
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

        # Check if the response has tool calls
        parsed_json = None
        if (hasattr(completion.choices[0].message, 'tool_calls') and
            completion.choices[0].message.tool_calls and
            len(completion.choices[0].message.tool_calls) > 0):
            # Extract parsed resume from tool calls
            parsed_resume = completion.choices[0].message.tool_calls[0].function.arguments
            parsed_json = json.loads(parsed_resume)
        else:
            # If no tool calls, try to parse the content directly
            try:
                content = completion.choices[0].message.content
                parsed_json = json.loads(content)
                parsed_resume = content
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error parsing JSON from response: {str(e)}")
                return {"error": "Failed to parse resume. The AI response was not in the expected format."}

        # Validate that we have a valid JSON object
        if not parsed_json or not isinstance(parsed_json, dict):
            return {"error": "Failed to parse resume. The response did not contain valid resume data."}

        embedding_response = openai_client.embeddings.create(
            input=parsed_resume,
            model='text-embedding-3-small'
        )
        query_embedding = embedding_response.data[0].embedding

        jobs = query_rag_content(query_embedding, 10, 'job')
        profile = query_rag_content(query_embedding, 10, 'profile')

        job_items = []
        if jobs.data:
            for item in jobs.data:
                if item['similarity'] > .3:
                    job_items.append(item.get('context', ''))

        profile_items = []
        if profile.data:
            for item in profile.data:
                if item['similarity'] > .3:
                    profile_items.append(item.get('context', ''))

        insert_resume(parsed_json)

        return {"parsed_resume": parsed_resume, 'jobs': job_items, 'profiles': profile_items}

    except Exception as e:
        print(str(e))
        return {"error": f"Error parsing resume: {str(e)}"}



@app.post("/api/parse-resume")
async def parse_resume(
    request: Request,
    file: Optional[UploadFile] = File(None),
    html_content: Optional[str] = Form(None)
):
    """
    Parse resume from multiple formats (HTML, PDF, or image) using OpenAI
    Accepts either an uploaded file (PDF or image) or HTML content
    """
    if not openai_client:
        return {
            "error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."
        }

    try:
        # Check if we have valid input
        if not file and not html_content:
            # Fallback to JSON request body for backward compatibility
            try:
                body = await request.json()
                html_content = body.get("html_content", "")
                if not html_content:
                    return {"error": "No content provided. Please provide either a file or HTML content."}
            except:
                return {"error": "No content provided. Please provide either a file or HTML content."}

        # Create the system prompt for resume parsing
        system_prompt = """You are a resume parser. Extract and format the key information from the provided content (HTML, PDF, or image of LinkedIn profiles or resumes) into only a JSON format.
        Remove any tags, navigation elements, or extraneous information.
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

        # Process input based on type
        messages = [{"role": "system", "content": system_prompt}]

        if file:
            content_type = file.content_type
            file_content = await file.read()

            if content_type.startswith("image/"):
                # Process image file
                # Convert image to base64
                encoded_image = base64.b64encode(file_content).decode("utf-8")
                image_url = f"data:{content_type};base64,{encoded_image}"

                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please parse and format this resume image into JSON:"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                })

            elif content_type == "application/pdf":
                # Process PDF file
                try:
                    # Convert PDF to text
                    pdf_text = ""
                    pdf_reader = PdfReader(io.BytesIO(file_content))
                    for page in pdf_reader.pages:
                        pdf_text += page.extract_text()

                    # For longer PDFs, we'll use the Files API
                    if len(pdf_text) > 4000:  # Arbitrary threshold, adjust as needed
                        # Upload PDF file to OpenAI
                        file_response = openai_client.files.create(
                            file=io.BytesIO(file_content),
                            purpose="assistants"
                        )

                        # Get file URL
                        file_id = file_response.id

                        messages.append({
                            "role": "user",
                            "content": f"Please parse and format this resume PDF into JSON. The PDF is attached as file ID: {file_id}"
                        })
                    else:
                        # For shorter PDFs, we can just use the extracted text
                        messages.append({
                            "role": "user",
                            "content": f"Please parse and format this resume PDF into JSON:\n\n{pdf_text}\n\n"
                        })
                except Exception as e:
                    print(f"Error processing PDF: {str(e)}")
                    return {"error": f"Error processing PDF: {str(e)}"}
            else:
                return {"error": f"Unsupported file type: {content_type}. Please upload a PDF or image file."}
        else:
            # Process HTML content
            messages.append({"role": "user", "content": f"Please parse and format this resume into JSON:\n\n{html_content}\n\n"})

        print('Processing resume with OpenAI...')
        # Call OpenAI API with appropriate model and format
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
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

        # Check if the response has tool calls
        parsed_json = None
        if (hasattr(completion.choices[0].message, 'tool_calls') and
            completion.choices[0].message.tool_calls and
            len(completion.choices[0].message.tool_calls) > 0):
            # Extract parsed resume from tool calls
            parsed_resume = completion.choices[0].message.tool_calls[0].function.arguments
            parsed_json = json.loads(parsed_resume)
        else:
            # If no tool calls, try to parse the content directly
            try:
                content = completion.choices[0].message.content
                parsed_json = json.loads(content)
                parsed_resume = content
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error parsing JSON from response: {str(e)}")
                return {"error": "Failed to parse resume. The AI response was not in the expected format."}

        # Validate that we have a valid JSON object
        if not parsed_json or not isinstance(parsed_json, dict):
            return {"error": "Failed to parse resume. The response did not contain valid resume data."}

        # Insert into database
        insert_resume(parsed_json)

        return {"parsed_resume": parsed_resume, "source_type": "pdf" if file and file.content_type == "application/pdf" else "image" if file else "html"}

    except Exception as e:
        print(str(e))
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

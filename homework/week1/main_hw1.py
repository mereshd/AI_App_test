import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from openai import OpenAI
from typing import Optional
import base64
import os
import json
import datetime
import io

from supabase_lib import query_rag_content, query_rag_content_many_types
from dotenv import load_dotenv

load_dotenv(dotenv_path=project_root / ".env")

app = FastAPI()

# Setup templates with correct path
templates = Jinja2Templates(directory=str(project_root / "templates"))

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


def query_rag_content(query_embedding, match_content, document_type):
  rag_results = supabase.rpc(
            'match_documents_by_document_type',
            {
                'query_embedding': query_embedding,
                'match_count': match_content,
                'query_document_type': document_type
            }
        ).execute()
  return rag_results


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Render the chat page"""
    return templates.TemplateResponse("chat.html", {"request": request})


def classify_document_type(user_message: str) -> list:
    """
    Uses OpenAI to classify the user's query into the appropriate document_type(s).
    Returns: list of document types - ['job'], ['profile'], or ['job', 'profile'] if uncertain
    """
    classification_prompt = """You are a document classifier. Analyze the user's query and determine if they are asking about:
- 'job': job postings, job requirements, job descriptions, career opportunities, positions
- 'profile': candidate profiles, resumes, skills, experience, people
- 'both': if the query is ambiguous or could relate to both jobs and profiles

Respond with ONLY one word: 'job', 'profile', or 'both'."""

    try:
        classification_response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": classification_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=10,
            temperature=1
        )

        classification = classification_response.choices[0].message.content.strip().lower()

        # Map classification to document types array
        if classification == 'job':
            document_types = ['job']
        elif classification == 'profile':
            document_types = ['profile']
        elif classification == 'both':
            document_types = ['job', 'profile']
        else:
            print(f"Warning: Unexpected classification '{classification}', searching all document types")
            document_types = ['job', 'profile']

        print(f"Classified query as document_types: {document_types}")
        return document_types
    except Exception as e:
        print(f"Error classifying document type: {str(e)}, searching all document types")
        return ['job', 'profile']


def determine_optimal_top_k(user_message: str) -> int:
    """
    Uses OpenAI to determine the optimal number of documents to retrieve (top-k)
    based on the query's complexity, specificity, and scope.

    Returns: integer between 3 and 20 representing the optimal number of documents to retrieve
    """
    top_k_prompt = """You are a retrieval optimization expert. Analyze the user's query and determine the optimal number of documents to retrieve (top-k value).

Consider:
- **Specific queries** (e.g., "What is the salary for Software Engineer at Google?") → Lower k (3-5)
- **Broad/exploratory queries** (e.g., "Tell me about all engineering roles") → Higher k (15-20)
- **Moderate complexity** (e.g., "What skills do senior data engineers need?") → Medium k (8-12)
- **Comparison queries** (e.g., "Compare job requirements for ML and Data roles") → Higher k (12-15)
- **List/enumeration requests** (e.g., "List all available positions") → Highest k (40-50)
The return structure should be
{
  "top_k": 10
}
"""

    try:
        top_k_response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": top_k_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=10,
            temperature=1
        )

        top_k_str = top_k_response.choices[0].message.content.strip()
        json_top_k = json.loads(top_k_str)

        top_k = int(json_top_k['top_k'])

        # Validate and constrain the top_k value
        if top_k < 3:
            top_k = 3
        elif top_k > 20:
            top_k = 20

        print(f"Determined optimal top-k: {top_k} for query: '{user_message[:50]}...'")
        return top_k
    except Exception as e:
        print(f"Error determining top-k: {str(e)}, using default value of 10")
        return 10


def rerank_results_gpt(query: str, results: list, top_n: int = None) -> list:
    """
    Reranks search results using GPT-3.5 Turbo for improved relevance.

    Args:
        query: The user's search query
        results: List of result dictionaries with 'context' field
        top_n: Number of top results to return (default: return all, sorted)

    Returns:
        Reranked list of results sorted by relevance score
    """
    if not results or not openai_client:
        return results

    # If we have few results, just return them as-is
    if len(results) <= 3:
        for i, result in enumerate(results):
            result['rerank_score'] = len(results) - i
        return results

    # Build a prompt asking GPT to rank the results by relevance
    contexts_with_ids = []
    for idx, item in enumerate(results):
        contexts_with_ids.append({
            "id": idx,
            "context": item.get('context', '')[:500]  # Limit to first 500 chars to save tokens
        })

    rerank_prompt = f"""Given the user query and the following search results, rank them by relevance to the query.
Return ONLY a JSON array of result IDs in order from most relevant to least relevant.

User Query: {query}

Search Results:
{json.dumps(contexts_with_ids, indent=2)}

Return format: {{"ranked_ids": [2, 0, 1, ...]}}"""

    try:
        rerank_response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You are a relevance ranking expert. Analyze search results and rank them by relevance to the user's query."},
                {"role": "user", "content": rerank_prompt}
            ],
            max_tokens=200,
            temperature=1,
            response_format={"type": "json_object"}
        )

        ranking_data = json.loads(rerank_response.choices[0].message.content)
        ranked_ids = ranking_data.get('ranked_ids', [])

        # Create a mapping of original index to rank score
        rank_scores = {}
        for rank, idx in enumerate(ranked_ids):
            rank_scores[idx] = len(ranked_ids) - rank  # Higher score = more relevant

        # Attach rerank scores to results
        for i, result in enumerate(results):
            result['rerank_score'] = rank_scores.get(i, 0)

        # Sort by rerank score (descending)
        reranked_results = sorted(results, key=lambda x: x['rerank_score'], reverse=True)

        print(f"Reranked {len(results)} results using GPT-3.5 Turbo")

        # Return top_n if specified, otherwise return all
        if top_n:
            return reranked_results[:top_n]

        return reranked_results

    except Exception as e:
        print(f"Error during GPT-3.5 reranking: {str(e)}, returning original order")
        # Fallback: return original results with default scores
        for i, result in enumerate(results):
            result['rerank_score'] = len(results) - i
        return results


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

        # Classify the document type(s) based on user query
        document_types = classify_document_type(user_message)
        print(document_types)
        # Determine optimal top-k value based on query complexity
        top_k = determine_optimal_top_k(user_message)
        # print(top_k)
        # Generate embedding for the user message
        embedding_response = openai_client.embeddings.create(
            input=user_message,
            model='text-embedding-3-small'
        )
        query_embedding = embedding_response.data[0].embedding

        # Query rag_content table with cosine distance using dynamic top-k
        # Use the new array-based function
        rag_results = query_rag_content_many_types(query_embedding, top_k, document_types)

        # Rerank results using GPT-3.5 Turbo

        # print('before reranking',  rag_results.data)
        reranked_results = []
        if rag_results.data:
            reranked_results = rerank_results_gpt(user_message, rag_results.data, 5)
        print('before reranking', reranked_results)
        # Extract context from reranked RAG results
        context_items = []
        if reranked_results:
            for item in reranked_results:
                context_items.append(item.get('context', ''))

        print(f"Found {len(context_items)} relevant context items for document_types: {document_types}")
        # Build context string
        rag_context = "\n\n".join(context_items) if context_items else "No relevant context found."

        # Call OpenAI API with RAG context
        completion = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": f"You are a senior data engineer who has mastered data engineering. Use the following context to answer questions:\n\n{rag_context}"},
                {"role": "user", "content": user_message}
            ],
            temperature=1
        )

        response_message = completion.choices[0].message.content

        return {
            "response": response_message,
            "rag_results": reranked_results if reranked_results else [],
            "document_types": document_types,
            "top_k": top_k
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
        system_prompt = """You are a resume parser. Extract and format the key information from HTML content (from LinkedIn profiles or resumes) into a structured JSON format. 
Remove any HTML tags, navigation elements, or extraneous information."""

        user_prompt = f"Please parse and format this resume into JSON:\n\n{html_content}\n\n"

        print('user prompt is', user_prompt)
        
        # Call OpenAI API with function calling (remove response_format)
        completion = openai_client.chat.completions.create(
            model="gpt-4o",  # ✅ Fixed: gpt-5 doesn't exist
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # ✅ Lower temperature for consistent parsing
            # ❌ REMOVED: response_format={"type": "json_object"}, - conflicts with tools
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
            ],
            tool_choice={"type": "function", "function": {"name": "parse_resume"}}  # ✅ Force tool usage
        )

        # ✅ Check if tool_calls exists before accessing
        if not completion.choices[0].message.tool_calls:
            return {"error": "Model did not return structured data"}

        parsed_resume = completion.choices[0].message.tool_calls[0].function.arguments
        print('Parsed resume:', parsed_resume)
        
        # Create embedding from the parsed resume
        embedding_response = openai_client.embeddings.create(
            input=parsed_resume,
            model='text-embedding-3-small'
        )
        query_embedding = embedding_response.data[0].embedding

        # Query for similar jobs and profiles
        jobs = query_rag_content(query_embedding, 10, 'job')
        profile = query_rag_content(query_embedding, 10, 'profile')

        job_items = []
        if jobs.data:
            for item in jobs.data:
                if item['similarity'] > 0.3:
                    job_items.append(item.get('context', ''))

        profile_items = []
        if profile.data:
            for item in profile.data:
                if item['similarity'] > 0.3:
                    profile_items.append(item.get('context', ''))

        # Insert parsed resume into database
        insert_resume(json.loads(parsed_resume))

        return {
            "parsed_resume": json.loads(parsed_resume),  # ✅ Return as JSON object
            'jobs': job_items, 
            'profiles': profile_items
        }

    except Exception as e:
        import traceback
        traceback.print_exc()  # ✅ Print full error trace
        print(str(e))
        return {"error": f"Error parsing resume: {str(e)}"}






@app.post("/api/parse-resume")
async def parse_resume(
    request: Request,
    file: Optional[UploadFile] = File(None)
):
    """Parse resume from HTML text, image file, or PDF file"""
    if not openai_client:
        return {"error": "OpenAI API key not configured."}

    try:
        content_type = request.headers.get("content-type", "")
        
        # Handle JSON body (HTML text input)
        if "application/json" in content_type:
            body = await request.json()
            html_content = body.get("html_content", "")
            
            if not html_content:
                return {"error": "No HTML content provided"}
            
            print("📝 Processing HTML text input...")
            
            messages = [
                {"role": "system", "content": "Extract name, header, and location from resumes."},
                {"role": "user", "content": f"Extract the name, professional header, and location from this resume HTML:\n\n{html_content}"}
            ]
            
            content_type_used = "html"
            filename_used = "html_input"
        
        # Handle file upload
        elif file:
            print(f"🟦 Processing uploaded file: {file.filename}, content_type: {file.content_type}")
            
            file_bytes = await file.read()
            
            messages = [
                {"role": "system", "content": "Extract name, header, and location from resumes."}
            ]
            
            # Handle PDFs - pass base64-encoded PDF directly to chat.completions
            if file.content_type == "application/pdf" or file.filename.lower().endswith(".pdf"):
                print("📄 Processing PDF with Chat Completions API...")
            
                # Wrap BytesIO in a tuple with filename and MIME type
                uploaded_file = openai_client.files.create(
                    file=("resume.pdf", io.BytesIO(file_bytes), "application/pdf"),
                    purpose="assistants"   # ✅ correct purpose
                )
            
                print(f"✅ Uploaded PDF to OpenAI with ID: {uploaded_file.id}")
            
                # Reference uploaded file correctly in the message
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the name, professional header, and location from this resume PDF."
                        },
                        {
                            "type": "file",
                            "file": {
                                "file_id": uploaded_file.id   # ✅ correct format
                            }
                        }
                    ]
                })
            
                content_type_used = file.content_type
                filename_used = file.filename
            
            # Handle images - base64 encode on server
            elif file.content_type and file.content_type.startswith('image/'):
                print("📸 Base64 encoding image on server...")
                
                base64_image = base64.b64encode(file_bytes).decode('utf-8')
                image_format = file.content_type.split('/')[-1]
                image_data_url = f"data:image/{image_format};base64,{base64_image}"
                
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract name, header, and location."},
                        {"type": "image_url", "image_url": {"url": image_data_url}}
                    ]
                })
                content_type_used = file.content_type
                filename_used = file.filename
            else:
                return {"error": f"Unsupported file type: {file.content_type}"}
        
        else:
            return {"error": "No file or HTML content provided"}
        
        # Tool schema for structured output
        key_parsed_elements_tool = {
            "type": "function",
            "function": {
                "name": "key_parsed_elements",
                "description": "Extract name, header, and location from resume",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Full name"},
                        "header": {"type": "string", "description": "Professional headline"},
                        "location": {"type": "string", "description": "Location"}
                    },
                    "required": ["name", "header", "location"]
                }
            }
        }
        
        # SINGLE CALL to chat.completions with PDF content
        completion = openai_client.chat.completions.create(
            model="gpt-4o",  # Vision-capable model that supports PDFs
            messages=messages,
            temperature=0.3,
            tools=[key_parsed_elements_tool],
            tool_choice={"type": "function", "function": {"name": "key_parsed_elements"}}
        )
        
        # Extract structured output
        if not completion.choices[0].message.tool_calls:
            return {"error": "No structured data returned"}
        
        tool_call = completion.choices[0].message.tool_calls[0]
        parsed_resume = json.loads(tool_call.function.arguments)
        
        print(f"✅ Parsed resume: {parsed_resume}")
        
        # Insert into database
        insert_result = insert_parsed_profile(parsed_resume)
        
        return {
            "parsed_resume": parsed_resume,
            "insert_result": insert_result,
            "filename": filename_used,
            "content_type": content_type_used
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error: {e}")
        return {"error": f"Error: {str(e)}"}



def insert_parsed_profile(profile_data: dict):
    """
    Inserts a parsed profile with name, header, and location into Supabase.
    """
    print("🟧 Inserting into Supabase...")
    required_keys = ["name", "header", "location"]
    for key in required_keys:
        if key not in profile_data:
            print(f"❌ Missing required key: {key}")
            return {"error": f"Missing required field: {key}"}

    row = {
        "name": profile_data["name"],
        "header": profile_data["header"],
        "location": profile_data["location"],
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    try:
        print(f"📤 Inserting row into Supabase: {row}")
        response = supabase.table("parsed_profiles").insert(row).execute()
        print("✅ Supabase insert successful.")
        return {"success": True, "data": response.data}
    except Exception as e:
        print(f"❌ Supabase insert failed: {e}")
        return {"error": str(e)}




def insert_resume(resume_json: dict) -> dict:
    """
    @app.post('/api/parse-resume-with-matching')

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






if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_hw1:app", host="0.0.0.0", port=port)


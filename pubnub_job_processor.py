"""
PubNub Job Processor

This script listens on a PubNub queue for job requests, queries job context from Supabase,
submits the request to OpenAI for processing, stores the response in Supabase,
and publishes the response reference back to PubNub.
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory
from openai import OpenAI
from supabase import create_client, Client
from supabase_lib import query_rag_content, insert_resume
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PUBNUB_PUBLISH_KEY = os.environ.get("PUBNUB_PUBLISH_KEY")
PUBNUB_SUBSCRIBE_KEY = os.environ.get("PUBNUB_SUBSCRIBE_KEY")
PUBNUB_JOB_CHANNEL = os.environ.get("PUBNUB_JOB_CHANNEL", "job-requests")
PUBNUB_RESPONSE_CHANNEL = os.environ.get("PUBNUB_RESPONSE_CHANNEL", "job-responses")

# Initialize clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


class JobProcessor:
    """Processes job requests from PubNub queue"""

    def __init__(self):
        self.supabase = supabase
        self.openai_client = openai_client

    def query_job_context(self, job_id: str, job_description: str = None) -> dict:
        """
        Query job context from Supabase using embeddings

        Args:
            job_id: The ID of the job
            job_description: Optional job description for semantic search

        Returns:
            dict containing job context
        """
        try:
            # If we have a job_id, query directly
            if job_id:
                response = self.supabase.table('rag_content').select("*").eq('document_id', job_id).eq('document_type', 'job').execute()
                if response.data and len(response.data) > 0:
                    return {
                        'job_id': job_id,
                        'context': response.data[0].get('context', ''),
                        'metadata': response.data[0]
                    }

            # If we have a job description, use embeddings for semantic search
            if job_description:
                embedding_response = self.openai_client.embeddings.create(
                    input=job_description,
                    model='text-embedding-3-small'
                )
                query_embedding = embedding_response.data[0].embedding

                # Query using the RPC function
                rag_results = self.supabase.rpc(
                    'match_documents_by_document_type',
                    {
                        'query_embedding': query_embedding,
                        'match_count': 1,
                        'query_document_type': 'job'
                    }
                ).execute()

                if rag_results.data and len(rag_results.data) > 0:
                    return {
                        'job_id': rag_results.data[0].get('document_id', ''),
                        'context': rag_results.data[0].get('context', ''),
                        'similarity': rag_results.data[0].get('similarity', 0),
                        'metadata': rag_results.data[0]
                    }

            return {'error': 'No job context found'}

        except Exception as e:
            logger.error(f"Error querying job context: {e}")
            return {'error': str(e)}

    def process_with_openai(self, job_context: dict, user_query: str) -> str:
        """
        Process the job context and user query with OpenAI

        Args:
            job_context: Dictionary containing job information
            user_query: The user's question or request

        Returns:
            OpenAI response text
        """
        try:
            context_text = job_context.get('context', '')

            system_prompt = f"""You are an expert job matching assistant. Use the following job context to answer questions:

{context_text}

Provide helpful, accurate information about the job based on the context provided. Be concise"""

            completion = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0
            )

            return completion.choices[0].message.content

        except Exception as e:
            logger.error(f"Error processing with OpenAI: {e}")
            raise

    def store_response(self, job_id: str, user_query: str, response: str, metadata: dict = None) -> dict:
        """
        Store the AI response in Supabase

        Args:
            job_id: The job ID
            user_query: The original user query
            response: The AI response
            metadata: Additional metadata

        Returns:
            Dictionary with the inserted record
        """
        try:
            record = {
                'job_id': job_id,
                'user_query': user_query,
                'ai_response': response,
                'metadata': metadata or {},
                'created_at': datetime.utcnow().isoformat()
            }

            result = self.supabase.table('job_responses').insert(record).execute()

            if result.data:
                logger.info(f"Response stored successfully with ID: {result.data[0].get('id')}")
                return result.data[0]
            else:
                raise Exception("Failed to store response in Supabase")

        except Exception as e:
            logger.error(f"Error storing response: {e}")
            raise

    def process_job_request(self, message: dict) -> dict:
        """
        Main processing function for job requests

        Args:
            message: The message received from PubNub

        Returns:
            Dictionary containing the response reference
        """
        try:
            job_id = message.get('job_id')
            job_description = message.get('job_description')
            user_query = message.get('query', 'Tell me about this job')

            logger.info(f"Processing job request - job_id: {job_id}, query: {user_query}")

            # Step 1: Query job context
            job_context = self.query_job_context(job_id, job_description)
            if 'error' in job_context:
                return {'error': job_context['error'], 'request_id': message.get('request_id')}

            # Step 2: Process with OpenAI
            ai_response = self.process_with_openai(job_context, user_query)

            # Step 3: Store in Supabase
            stored_record = self.store_response(
                job_id=job_context.get('job_id', job_id),
                user_query=user_query,
                response=ai_response,
                metadata={
                    'similarity': job_context.get('similarity'),
                    'request_id': message.get('request_id'),
                    'original_job_id': job_id
                }
            )

            # Step 4: Return reference
            return {
                'status': 'success',
                'response_id': stored_record.get('id'),
                'job_id': job_context.get('job_id'),
                'request_id': message.get('request_id'),
                'response': ai_response,
                'timestamp': stored_record.get('created_at')
            }

        except Exception as e:
            logger.error(f"Error processing job request: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'request_id': message.get('request_id')
            }


class PubNubJobListener(SubscribeCallback):
    """PubNub callback handler for job requests"""

    def __init__(self, pubnub_client, response_channel: str):
        self.pubnub = pubnub_client
        self.response_channel = response_channel
        self.processor = JobProcessor()

    def status(self, pubnub, status):
        if status.category == PNStatusCategory.PNConnectedCategory:
            logger.info("Connected to PubNub")
        elif status.category == PNStatusCategory.PNUnexpectedDisconnectCategory:
            logger.warning("Disconnected from PubNub")
        elif status.category == PNStatusCategory.PNReconnectedCategory:
            logger.info("Reconnected to PubNub")

    def message(self, pubnub, message):
        """Handle incoming messages from PubNub"""
        try:
            logger.info(f"Received message: {message.message}")

            job = message.message

            resume_job = (
                supabase.table("resume_job")
                .select("*")
                .eq("id", job['id'])  # Filter where 'column_name' equals 'value'
                .execute()
            )

            print(resume_job)

            html_content = resume_job.data[0]['resume_text']

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

            parsed_resume = completion.choices[0].message.tool_calls[0].function.arguments
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

            print(parsed_resume, job_items)
            resume = insert_resume(json.loads(parsed_resume))

            # Publish the full response with parsed resume, jobs, and profiles
            response_data = {
                "parsed_resume": parsed_resume,
                "jobs": job_items,
                "profiles": profile_items,
                "resume_id": resume.get('id')
            }
            self.publish_response(response_data)
            return response_data

        except Exception as e:
            print(str(e))
            error_response = {"error": f"Error parsing resume: {str(e)}"}
            self.publish_response(error_response)
            return error_response
            # Process the job request
            response = self.processor.process_job_request(message.message)

            # Publish response to response channel
            self.publish_response(response)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            error_response = {
                'status': 'error',
                'error': str(e),
                'request_id': message.message.get('request_id')
            }
            self.publish_response(error_response)

    def publish_response(self, response: dict):
        """Publish response to PubNub response channel"""
        try:
            envelope = self.pubnub.publish()\
                .channel(self.response_channel)\
                .message(response)\
                .sync()

            logger.info(f"Response published to {self.response_channel}: {response.get('status')}")

        except Exception as e:
            logger.error(f"Error publishing response: {e}")


def main():
    """Main function to start the PubNub listener"""

    # Validate environment variables
    if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY,
                PUBNUB_PUBLISH_KEY, PUBNUB_SUBSCRIBE_KEY]):
        logger.error("Missing required environment variables")
        return

    # Configure PubNub
    pnconfig = PNConfiguration()
    pnconfig.publish_key = PUBNUB_PUBLISH_KEY
    pnconfig.subscribe_key = PUBNUB_SUBSCRIBE_KEY
    pnconfig.user_id = "job-processor-worker"

    pubnub_client = PubNub(pnconfig)

    # Set up listener
    listener = PubNubJobListener(pubnub_client, PUBNUB_RESPONSE_CHANNEL)
    pubnub_client.add_listener(listener)

    # Subscribe to job channel
    pubnub_client.subscribe().channels(PUBNUB_JOB_CHANNEL).execute()

    logger.info(f"Listening on channel: {PUBNUB_JOB_CHANNEL}")
    logger.info(f"Publishing responses to: {PUBNUB_RESPONSE_CHANNEL}")
    logger.info("Press Ctrl+C to stop")

    try:
        # Keep the script running
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        pubnub_client.unsubscribe_all()
        pubnub_client.stop()


if __name__ == "__main__":
    main()

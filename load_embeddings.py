#!/usr/bin/env python3
"""
Script to read JSON files from the data folder, convert them to embeddings,
and load them into the Supabase rag_content table.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize clients
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """
    Generate an embedding for the given text using OpenAI's API.

    Args:
        text: The text to embed
        model: The embedding model to use (default: text-embedding-3-small)

    Returns:
        A list of floats representing the embedding vector
    """
    response = openai_client.embeddings.create(
        input=text,
        model=model
    )
    return response.data[0].embedding


def format_job_context(job: dict) -> str:
    """
    Format a job posting into a text string for embedding.

    Args:
        job: Dictionary containing job information

    Returns:
        Formatted string representation of the job
    """
    skills_str = ", ".join(job.get("skills", []))
    return f"""Job Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Employment Type: {job.get('employment_type', 'N/A')}
Experience Level: {job.get('experience_level', 'N/A')}
Salary Range: {job.get('salary_range', 'N/A')}
Skills: {skills_str}
Description: {job.get('description', 'N/A')}"""


def format_profile_context(profile: dict) -> str:
    """
    Format a user profile into a text string for embedding.

    Args:
        profile: Dictionary containing profile information

    Returns:
        Formatted string representation of the profile
    """
    skills_str = ", ".join(profile.get("skills", []))
    education_str = "; ".join([
        f"{edu.get('degree', '')} from {edu.get('school', '')}"
        for edu in profile.get("education", [])
    ])

    return f"""Name: {profile.get('name', 'N/A')}
Title: {profile.get('title', 'N/A')}
Company: {profile.get('company', 'N/A')}
Location: {profile.get('location', 'N/A')}
Experience: {profile.get('experience_years', 0)} years
Career Level: {profile.get('career_level', 'N/A')}
Industry: {profile.get('industry', 'N/A')}
Skills: {skills_str}
Education: {education_str}
Summary: {profile.get('summary', 'N/A')}
LinkedIn: {profile.get('linkedin_url', 'N/A')}"""



def load_vectors_into_supabase(id, embedding, context, user_id, document_type, **kwargs):
    # Insert into Supabase
        data = {
            "id": id,
            "embedding": embedding,
            "context": context,
            "user_id": user_id,
            "document_type": document_type,
            **kwargs
        }

        try:
            supabase.table("rag_content").upsert(data).execute()
            print(f"  ✓ Inserted job {id}")
        except Exception as e:
            print(f"  ✗ Error inserting vectors {id}: {e}")


def load_jobs_into_rag(file_path: str, user_id: int = 1):
    """
    Load job postings from a JSON file into the rag_content table.

    Args:
        file_path: Path to the JSON file containing job postings
        user_id: User ID to associate with the content (default: 1)
    """
    print(f"Loading jobs from {file_path}...")

    with open(file_path, 'r') as f:
        jobs = json.load(f)

    for i, job in enumerate(jobs):
        job_id = f"job_{job.get('id', i)}"
        context = format_job_context(job)

        print(f"Processing job {i+1}/{len(jobs)}: {job.get('title', 'Unknown')}...")
        # Generate embedding
        embedding = get_embedding(context)
        load_vectors_into_supabase(job_id, embedding, context, user_id, "job")

    print(f"Completed loading {len(jobs)} jobs.\n")


def load_profiles_into_rag(file_path: str, user_id: int = 1):
    """
    Load user profiles from a JSON file into the rag_content table.

    Args:
        file_path: Path to the JSON file containing profiles
        user_id: User ID to associate with the content (default: 1)
    """
    print(f"Loading profiles from {file_path}...")

    with open(file_path, 'r') as f:
        profiles = json.load(f)

    for i, profile in enumerate(profiles):
        profile_id = f"{profile.get('linkedin_url', i)}"
        context = format_profile_context(profile)

        print(f"Processing profile {i+1}/{len(profiles)}: {profile.get('name', 'Unknown')}...")
        # Generate embedding
        embedding = get_embedding(context)
        load_vectors_into_supabase(profile_id, embedding, context, user_id, "profile")
    print(f"Completed loading {len(profiles)} profiles.\n")

def main():
    """
    Main function to load all JSON files from the data folder.
    """
    data_dir = Path(__file__).parent / "data"

    print("=" * 60)
    print("Starting RAG Content Loading Process")
    print("=" * 60)
    print()

    # Load jobs
    jobs_file = data_dir / "synthetic_data_jobs.json"
    if jobs_file.exists():
        load_jobs_into_rag(str(jobs_file))
    else:
        print(f"Warning: {jobs_file} not found, skipping jobs.\n")

    # Load profiles
    profiles_file = data_dir / "synthetic_profiles.json"
    if profiles_file.exists():
        load_profiles_into_rag(str(profiles_file))
    else:
        print(f"Warning: {profiles_file} not found, skipping profiles.\n")

    print("=" * 60)
    print("RAG Content Loading Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

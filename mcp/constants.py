import os
from dotenv import load_dotenv
# Load environment variables
load_dotenv()
GITHUB_MCP_PAT = os.getenv("GITHUB_TOKEN")
SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN")
SUPABASE_PROJECT_REF = os.getenv('SUPABASE_PROJECT_REF')


mcp_config = {
    "github-mcp-remote": {
        "transport": "streamable_http", # stdio, a bunch of others
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
            "Authorization": f"Bearer {GITHUB_MCP_PAT}"
        }
    },
    "supabase": {
        "transport": "streamable_http",
        "url": f"https://mcp.supabase.com/mcp?project_ref={SUPABASE_PROJECT_REF}",
        "headers": {
            "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}"
        }
    }
}
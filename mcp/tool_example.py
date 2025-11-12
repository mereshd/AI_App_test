#!/usr/bin/env python3
"""
GitHub REST API Client with LangChain Integration

Fallback client that uses GitHub's REST API instead of MCP for GitHub operations.
Includes LangChain tool integration for OpenAI function calling.
"""

import os
import requests
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse


basic_model = ChatOpenAI(model="gpt-4o")
advanced_model = ChatOpenAI(model="gpt-5")

@wrap_model_call
def dynamic_model_selection(request: ModelRequest, handler) -> ModelResponse:
    """Choose model based on conversation complexity."""
    print(request.state['messages'])
    message_count = len(request.state["messages"])

    if message_count > 10:
        # Use an advanced model for longer conversations
        model = advanced_model
    else:
        model = basic_model

    request.model = model
    return handler(request)


# Load environment variables
load_dotenv()


class GitHubRESTClient:
    """Client for GitHub REST API operations."""

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
        print(self.github_token)
        self.base_url = "https://api.github.com"

        if not self.github_token:
            raise ValueError("GitHub token not found. Set GITHUB_PAT or GITHUB_TOKEN environment variable.")

        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "github-rest-client/1.0.0"
        }

    def test_connection(self) -> bool:
        """Test connection to GitHub API."""
        try:
            response = requests.get(f"{self.base_url}/user", headers=self.headers, timeout=10)
            if response.status_code == 200:
                user_data = response.json()
                print(f"✅ GitHub API connection successful - User: {user_data.get('login', 'Unknown')}")
                return True
            else:
                print(f"❌ GitHub API connection failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ GitHub API connection error: {e}")
            return False

    def create_issue(self, repo: str, title: str, body: str, labels: List[str] = None) -> Dict[str, Any]:
        """Create a GitHub issue."""
        url = f"{self.base_url}/repos/{repo}/issues"

        data = {
            "title": title,
            "body": body
        }

        if labels:
            data["labels"] = labels

        try:
            response = requests.post(url, json=data, headers=self.headers, timeout=30)
            response.raise_for_status()

            issue_data = response.json()
            print(f"✅ Issue created successfully: {issue_data.get('html_url', 'Unknown URL')}")
            return {
                "success": True,
                "issue": issue_data,
                "url": issue_data.get('html_url')
            }

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to create issue: {e}")
            return {"success": False, "error": str(e)}

    def get_issues(self, repo: str, state: str = "open", per_page: int = 10) -> List[Dict[str, Any]]:
        """Get issues from a repository."""
        url = f"{self.base_url}/repos/{repo}/issues"
        params = {
            "state": state,
            "per_page": per_page,
            "sort": "updated",
            "direction": "desc"
        }

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()

            issues = response.json()
            print(f"✅ Retrieved {len(issues)} issues from {repo}")
            return issues

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get issues: {e}")
            return []

    def get_repositories(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get repositories for a user."""
        if username:
            url = f"{self.base_url}/users/{username}/repos"
        else:
            url = f"{self.base_url}/user/repos"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            repos = response.json()
            print(f"✅ Retrieved {len(repos)} repositories")
            return repos

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get repositories: {e}")
            return []

    def search_issues(self, query: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """Search for issues across repositories."""
        url = f"{self.base_url}/search/issues"
        params = {
            "q": query,
            "per_page": per_page,
            "sort": "updated",
            "order": "desc"
        }

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()

            search_results = response.json()
            issues = search_results.get('items', [])
            print(f"✅ Found {len(issues)} issues matching query: {query}")
            return issues

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to search issues: {e}")
            return []

    def get_repository_content(self, repo: str, path: str = "") -> Dict[str, Any]:
        """Get the contents of a repository path.

        Args:
            repo: Repository in format 'owner/repo'
            path: Path within the repository (empty string for root)

        Returns:
            Dictionary with content information or error
        """
        url = f"{self.base_url}/repos/{repo}/contents/{path}"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            content = response.json()

            # Handle both file and directory responses
            if isinstance(content, list):
                print(f"✅ Retrieved directory listing for {repo}/{path} ({len(content)} items)")
                return {
                    "success": True,
                    "type": "dir",
                    "contents": content
                }
            else:
                print(f"✅ Retrieved file content for {repo}/{path}")
                return {
                    "success": True,
                    "type": "file",
                    "content": content
                }

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get repository content: {e}")
            return {"success": False, "error": str(e)}


# Global GitHub client instance
_github_client = None


def get_github_client() -> GitHubRESTClient:
    """Get or create a GitHub client instance."""
    global _github_client
    if _github_client is None:
        _github_client = GitHubRESTClient()
    return _github_client


@tool
def create_github_issue(repo: str, title: str, body: str, labels: Optional[List[str]] = None) -> str:
    """Create a GitHub issue in a repository.

    Args:
        repo: Repository in format 'owner/repo'
        title: Issue title
        body: Issue body
        labels: Optional list of labels
    """
    try:
        client = get_github_client()
        result = client.create_issue(repo, title, body, labels or [])
        if result.get("success"):
            return f"Issue created successfully: {result.get('url')}"
        else:
            return f"Failed to create issue: {result.get('error')}"
    except Exception as e:
        return f"Error creating issue: {str(e)}"


@tool
def get_github_issues(repo: str, state: str = "open", per_page: int = 10) -> str:
    """Get issues from a GitHub repository.

    Args:
        repo: Repository in format 'owner/repo'
        state: Issue state (open, closed, all)
        per_page: Number of issues to retrieve
    """
    try:
        client = get_github_client()
        issues = client.get_issues(repo, state, per_page)
        if issues:
            issue_list = []
            for issue in issues[:5]:  # Limit to first 5 for readability
                issue_list.append(f"- {issue.get('title', 'No title')} (#{issue.get('number', 'N/A')})")
            return f"Found {len(issues)} issues in {repo}:\n" + "\n".join(issue_list)
        else:
            return f"No issues found in {repo}"
    except Exception as e:
        return f"Error getting issues: {str(e)}"


@tool
def create_github_pull_request(repo: str, title: str, body: str, head: str, base: str = "main") -> str:
    """Create a GitHub pull request.

    Args:
        repo: Repository in format 'owner/repo'
        title: PR title
        body: PR body
        head: Source branch
        base: Target branch (default: main)
    """
    try:
        client = get_github_client()
        result = client.create_pull_request(repo, title, body, head, base)
        if result.get("success"):
            return f"Pull request created successfully: {result.get('url')}"
        else:
            return f"Failed to create pull request: {result.get('error')}"
    except Exception as e:
        return f"Error creating pull request: {str(e)}"


@tool
def get_github_repositories(username: Optional[str] = None) -> str:
    """Get repositories for a user.

    Args:
        username: Optional username (uses authenticated user if not provided)
    """
    try:
        client = get_github_client()
        repos = client.get_repositories(username)
        if repos:
            repo_list = []
            for repo in repos:
                repo_list.append(f"- {repo.get('name', 'No name')} ({repo.get('html_url', 'No URL')})")
            return f"Found {len(repos)} repositories:\n" + "\n".join(repo_list)
        else:
            return "No repositories found"
    except Exception as e:
        return f"Error getting repositories: {str(e)}"


@tool
def search_github_issues(query: str, per_page: int = 10) -> str:
    """Search for issues across GitHub repositories.

    Args:
        query: Search query
        per_page: Number of results to retrieve
    """
    try:
        client = get_github_client()
        issues = client.search_issues(query, per_page)
        if issues:
            issue_list = []
            for issue in issues[:5]:  # Limit to first 5 for readability
                repo = issue.get('repository', {}).get('full_name', 'Unknown')
                issue_list.append(f"- {issue.get('title', 'No title')} in {repo} (#{issue.get('number', 'N/A')})")
            return f"Found {len(issues)} issues matching '{query}':\n" + "\n".join(issue_list)
        else:
            return f"No issues found matching '{query}'"
    except Exception as e:
        return f"Error searching issues: {str(e)}"


@tool
def get_repository_content(repo: str, path: str = "") -> str:
    """Get the contents of a repository path.

    Args:
        repo: Repository in format 'owner/repo'
        path: Path within the repository (empty string for root)
    """
    try:
        client = get_github_client()
        result = client.get_repository_content(repo, path)

        if not result.get("success"):
            return f"Failed to get repository content: {result.get('error')}"

        if result.get("type") == "dir":
            contents = result.get("contents", [])
            if contents:
                content_list = []
                for item in contents:
                    item_type = item.get('type', 'unknown')
                    name = item.get('name', 'unknown')
                    content_list.append(f"- {name} ({item_type})")
                return f"Directory listing for {repo}/{path} ({len(contents)} items):\n" + "\n".join(content_list)
            else:
                return f"Empty directory: {repo}/{path}"
        else:
            content_data = result.get("content", {})
            name = content_data.get("name", "unknown")
            size = content_data.get("size", 0)
            encoding = content_data.get("encoding", "unknown")
            return f"File: {name}\nSize: {size} bytes\nEncoding: {encoding}\nPath: {repo}/{path}"
    except Exception as e:
        return f"Error getting repository content: {str(e)}"


def create_github_agent(openai_api_key: Optional[str] = None):
    """Create a LangChain agent with GitHub tools and OpenAI integration."""
    try:
        # Initialize GitHub client
        github_client = get_github_client()

        if not github_client.test_connection():
            print("❌ GitHub API connection failed")
            return None

        # Create tools list
        tools = [
            create_github_issue,
            get_github_issues,
            create_github_pull_request,
            get_github_repositories,
            search_github_issues,
            get_repository_content
        ]

        # Initialize OpenAI
        openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            print("❌ OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
            return None

        llm = ChatOpenAI(
            model="gpt-5",
            temperature=0,
            openai_api_key=openai_key
        )

        # Create agent using langgraph's create_react_agent
        # The new API doesn't require a separate prompt template
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt="You are a helpful GitHub assistant. You can create issues, pull requests, search repositories, and more. Always provide clear, helpful responses.",
            middleware=[dynamic_model_selection]
        )

        print("✅ GitHub agent created successfully!")
        return agent

    except Exception as e:
        print(f"❌ Failed to create GitHub agent: {e}")
        return None


def chat_with_github_agent(message: str, agent=None) -> str:
    """Chat with the GitHub agent."""
    if not agent:
        agent = create_github_agent()
        if not agent:
            return "❌ Failed to create GitHub agent"

    try:
        # Langgraph agents use a different invoke format
        result = agent.invoke({"messages": [("user", message)]})
        # Extract the final message from the result
        if "messages" in result and len(result["messages"]) > 0:
            final_message = result["messages"][-1]
            return final_message.content if hasattr(final_message, 'content') else str(final_message)
        return "No response from agent"
    except Exception as e:
        return f"❌ Error chatting with agent: {e}"


def main():
    """Main function for testing."""
    print("🚀 GitHub REST API Client with LangChain Integration")
    print("=" * 60)

    try:
        # Test basic functionality
        client = GitHubRESTClient()

        if client.test_connection():
            print("\n✅ GitHub REST API client ready!")

            # Create agent
            print("\n🧪 Creating GitHub agent...")
            agent = create_github_agent()
            if agent:
                # First, get the list of repositories
                print("\n📋 Getting list of repositories...")
                # Get repositories directly to loop over them
                repos = client.get_repositories("EcZachly")

                if repos:
                    print(f"\n🔄 Processing {len(repos)} repositories...")

                    # Loop over each repository one at a time
                    for i, repo in enumerate(repos, 1):
                        repo_name = repo.get('name')
                        repo_full_name = repo.get('full_name')

                        print(f"\n[{i}/{len(repos)}] Processing repository: {repo_full_name}")

                        # Read repository contents and create an issue for this specific repo
                        response = chat_with_github_agent(
                            f"Read the contents of the repository '{repo_full_name}' and create a single issue for this repository with a title and description based on what you think could be improved. Be specific and actionable.",
                            agent
                        )
                        print(f"🤖 Agent response for {repo_full_name}: {response}")
                        print("-" * 60)
                else:
                    print("❌ No repositories found for EcZachly")

        else:
            print("❌ GitHub REST API client failed to connect")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

# Middleware tools help prevent misuse and abuse
from langchain.agents.middleware import ToolCallLimitMiddleware
from constants import mcp_config, GITHUB_MCP_PAT
import asyncio


async def main():
    client = MultiServerMCPClient(mcp_config)
    tools = await client.get_tools()
    # Create LLM
    llm = ChatOpenAI(model="gpt-4o")
    # Plz change this before running
    organization = 'DataExpert-io'

    # Create agent with the client
    agent = create_agent(model=llm, tools=tools,
                         middleware=[
                             ToolCallLimitMiddleware(
                                 thread_limit=100,  # Limit total tool calls across the thread
                                 run_limit=30,
                                 exit_behavior="continue",  # or "end" / "error"
                             )
                         ],
                         )
    # Original GitHub functionality (if token is available)
    if GITHUB_MCP_PAT:
        print("\n--- Testing GitHub MCP Server ---")
        # Run the query

        repo_json_structure = '[{"repo": "repo", "metadata": {"stars": 3333, "readme": "readme content"}}]'

        result = await agent.ainvoke(
            {"messages": f"""List the first 5 repos of {organization} organization repositories with all their stars.
                        Output in {repo_json_structure}"""}
        )
        for message in result['messages']:
            print(message)

        json_structure = '[{"repo": "repo", "read_me" : "read me content", "suggested_improvements": "Detailed list of improvements", "completeness_score": 0-10}]'
        result = await agent.ainvoke(
            {"messages": f"""For these repositories: {result['messages']}, read their README.md file. Give detailed feedback and a completeness score.
             Output the result as an json array {json_structure} and load it into a new supabase table called repos
            """}
        )
    else:
        print("⚠️  GitHub PAT not found. Skipping GitHub functionality.")


if __name__ == "__main__":
    asyncio.run(main())
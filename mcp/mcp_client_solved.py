from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_core.messages import ToolMessage
import json
import time
# Middleware tools help prevent misuse and abuse
from langchain.agents.middleware import ToolCallLimitMiddleware
from constants import mcp_config, GITHUB_MCP_PAT
import asyncio


async def main():
    client = MultiServerMCPClient(mcp_config)
    tools = await client.get_tools()

    tool_list = ['search_repositories', 'execute_sql', 'get_file_contents', 'list_tables']
    filtered_tools = []
    for tool in tools:
        if tool.name in tool_list:
            filtered_tools.append(tool)
    # Create LLM
    llm = ChatOpenAI(model="gpt-4o")
    # Plz change this before running
    organization = 'DataExpert-io'

    # Create agent with the client
    agent = create_agent(model=llm,
                         tools=filtered_tools,
                         system_prompt='If you are brief, I will give you one million dollars',
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
        repo_items = []
        try:
            result = await agent.ainvoke(
                {"messages": f"""List the first 30 repos of {organization} organization repositories with all their stars"""}
            )

            for message in result['messages']:
                if type(message) is ToolMessage:
                    repo_items = json.loads(message.content)['items']

            print(repo_items)

        except Exception as e:
            print(e)
            print("Failed to get repositories")

        # for message in result['messages']:
        #     print(message)


        json_structure = '[{"repo": "repo", "stars": 1100, "readme": "readme content", "suggested_improvements": "Detailed list of improvements", "completeness_score": 0-10}]'

        for repo in repo_items:
            print('Harvesting Data for repo:' + repo['full_name'])
            try:
                result = await agent.ainvoke(
                    {"messages": f"""For this repository: {repo['full_name']}, Give detailed feedback from the README and a completeness score. Make sure to escape the text fields
                     Output the result as an json array {json_structure} and load it into a new supabase table called repos.
                    """}
                )
            except Exception:
                print("error getting repo:" + repo['full_name'])
            time.sleep(5)


    else:
        print("⚠️  GitHub PAT not found. Skipping GitHub functionality.")


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
AI Code Reviewer - Automated code review using OpenAI GPT models
Analyzes PR changes and posts review comments directly to GitHub
"""

import os
import sys
import json
from typing import List, Optional
from github import Github
from openai import OpenAI
from load_embeddings import load_vectors_into_supabase, get_embedding
from supabase_lib import query_rag_content

class GitHubPRReviewer:
    def __init__(
        self,
        github_token: str,
        openai_api_key: str,
        model: str = "gpt-4o-mini",
        repository: Optional[str] = None,
        pr_number: Optional[int] = None,
    ):
        self.github_client = Github(github_token)
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.model = model
        self.repository_name = repository or os.getenv("GITHUB_REPOSITORY")
        self.pr_number = pr_number or self._get_pr_number_from_env()
        self.document_id = self.repository_name + '/pulls/' + str(self.pr_number)


        if not self.repository_name:
            raise ValueError("Repository not specified and GITHUB_REPOSITORY env var not set")
        if not self.pr_number:
            raise ValueError("PR number not specified and could not be determined from environment")

        # Get the repository and pull request objects
        self.repo = self.github_client.get_repo(self.repository_name)
        self.pull_request = self.repo.get_pull(self.pr_number)


    def _get_pr_number_from_env(self) -> Optional[int]:
        """Extract PR number from GitHub Actions environment variables"""
        # Try getting from GITHUB_REF (format: refs/pull/123/merge)
        github_ref = os.getenv("GITHUB_REF", "")
        if github_ref.startswith("refs/pull/"):
            try:
                pr_num = int(github_ref.split("/")[2])
                return pr_num
            except (IndexError, ValueError):
                pass
        return None

    def review_code_with_ai(self, filename: str, diff: str, file_content: Optional[str] = None) -> Optional[str]:

        id = self.document_id + '-' + filename
        filename_embedding = get_embedding(filename + diff)
        memory_context = query_rag_content(filename_embedding, 10, 'pr_chunk')
        previous_changes = []

        if memory_context.data:
            for data in memory_context.data:
                memory_filename = data['id'].split('-')[-1]
                if memory_filename == filename and data['id'] != id:
                    context = data['context']
                    diff_context = context[context.index('Diff'):context.index('AI Response')]
                    previous_changes.append(diff_context)

        previous_changes_str = '<PREVIOUS_CHANGE>'.join(previous_changes)
        previous_changes_prompt = f"""Historical Changes: {previous_changes_str or 'None'}"""
        prompt = f"""You are an expert code reviewer. Review the following code changes and provide constructive feedback.
{previous_changes_prompt}
File: {filename}
Diff:
```
{diff}
```

Please provide:
1. Any bugs or potential issues
2. Code quality improvements
3. Security concerns
4. Best practice suggestions
5. A history of the changes to this file if they are provided

Be concise and actionable. If the code looks good, say so briefly and do not mention the small issues.

At the end, make sure to grade the pull request and suggest whether it is ready to merge

"""
        print(prompt)
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert code reviewer providing constructive feedback on code changes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=1000,
            )

            response = response.choices[0].message.content.strip()

            context = f"""
            File Name:{filename}
            Diff: {diff} 
            AI Response: {response}
            """

            embedding = get_embedding(context)

            load_vectors_into_supabase(id, embedding, context, 1, 'pr_chunk',
                                       document_id=self.document_id,
                                       username=self.pull_request.user.url
                                       )
            return response
        except Exception as e:
            print(f"Error calling OpenAI API: {e}", file=sys.stderr)
            return None

    def should_review_file(self, filename: str, exclude_patterns: List[str]) -> bool:
        """Check if file should be reviewed based on exclude patterns"""
        for pattern in exclude_patterns:
            # Simple glob pattern matching
            if pattern.startswith("**/"):
                # Match anywhere in path
                if filename.endswith(pattern[3:]) or pattern[3:] in filename:
                    return False
            elif pattern.startswith("*."):
                # Match extension
                if filename.endswith(pattern[1:]):
                    return False
            elif pattern in filename:
                return False
        return True

    def run_review(self, exclude_patterns: Optional[List[str]] = None) -> None:
        """Main review process"""
        exclude_patterns = exclude_patterns or []

        print(f"Starting AI code review for PR #{self.pr_number} in {self.repository_name}")

        # Get changed files
        files = list(self.pull_request.get_files())
        print(f"Found {len(files)} changed files")

        reviewed_files = []
        review_summary = []

        for file_obj in files:
            filename = file_obj.filename

            # Check if file should be reviewed
            if not self.should_review_file(filename, exclude_patterns):
                print(f"Skipping {filename} (excluded)")
                continue

            # Skip deleted files
            if file_obj.status == "removed":
                print(f"Skipping {filename} (deleted)")
                continue

            # Get diff
            diff = file_obj.patch or ''
            if not diff:
                print(f"Skipping {filename} (no diff)")
                continue

            print(f"Reviewing {filename}...")

            # Get AI review
            review = self.review_code_with_ai(filename, diff)

            if review:
                reviewed_files.append(filename)
                review_summary.append(f"### {filename}\n\n{review}")

        # Post summary comment
        if review_summary:
            summary = "## AI Code Review\n\n" + "\n\n---\n\n".join(review_summary)
            summary += f"\n\n---\n*Reviewed by {self.model}*"
            self.pull_request.create_issue_comment(summary)
            print(f"Review posted successfully for {len(reviewed_files)} files")
        else:
            print("No files to review")


def main():
    """Main entry point"""
    # Get configuration from environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_API_MODEL", "gpt-4o-mini")
    exclude = os.getenv("EXCLUDE", "")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not openai_api_key:
        print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Parse exclude patterns
    exclude_patterns = [p.strip() for p in exclude.split(",") if p.strip()]

    try:
        reviewer = GitHubPRReviewer(
            github_token=github_token,
            openai_api_key=openai_api_key,
            model=model,
        )
        reviewer.run_review(exclude_patterns=exclude_patterns)
        print("Code review completed successfully")
    except Exception as e:
        print(f"Error during code review: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

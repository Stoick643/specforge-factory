"""Prompt templates for the Tester agent."""

ANALYSIS_PROMPT = """\
You are an expert Python test analyst. Analyze the following pytest output and provide \
concise, actionable feedback for a developer to fix the failing tests.

## Pytest Output

{pytest_output}

## Generated Files

The following files were generated:
{file_list}

---

Provide:
1. A summary of what went wrong (be specific — which tests failed and why)
2. Root cause analysis for each failure
3. Specific code changes needed to fix each issue
4. Any missing imports, incorrect assertions, or logic errors you spot

Be concise but thorough. Focus on actionable fixes, not general advice.
"""

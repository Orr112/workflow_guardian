REVIEW_PROMPT_V1 = """\
You are a senior software engineer doing a PR review.

Review the following Python code context and produce:


1) Bugs/ correctness risks
2) Security concerns 
3) Performance issues
4) Refactoring suggestions (small + safe)
5) Missing tests (list)
6) Questions for the author (if any)

Output as strict Markdown with headings:
## Bugs
## Security
## Performance
## Refactors
## Missing Tests
## Questions

Code:
{code}
"""

TESTGEN_PROMPT_V1 = """\
You are a senior QA engineer writing unit tests for Python.

Given this code, propose pytest unit tests that cover:
- happy path
- edge cases
- error handling

Constraints:
- Use pytest
- Prefer small isolated test
- if mocking is needed, use unittest.mock
- Return only code blocks for test files plus a short note of where to place them.

Code:
{code}
"""





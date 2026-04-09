"""Deep Research Stock Analyst (ADK + Vertex AI).

This repository now provides an ADK-based deep search agent in `deep_search_agent/`.

Recommended usage (interactive):
  adk run deep_search_agent

Dev UI:
  adk web --no-reload

Vertex AI prerequisites:
  gcloud auth application-default login
  set GOOGLE_GENAI_USE_VERTEXAI=TRUE
  set GOOGLE_CLOUD_PROJECT=your-project
  set GOOGLE_CLOUD_LOCATION=us-central1

See docs: docs/ADK_DEEP_SEARCH_AGENT.md
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
	parser = argparse.ArgumentParser(description="Deep Research Stock Analyst (ADK)")
	parser.add_argument(
		"prompt",
		nargs="*",
		help="Optional one-shot prompt. If omitted, use `adk run deep_search_agent`.",
	)
	args = parser.parse_args()

	if not args.prompt:
		print("This script is a thin wrapper for the ADK agent.")
		print("Run: adk run deep_search_agent")
		print("Docs: docs/ADK_DEEP_SEARCH_AGENT.md")
		return 0

	user_prompt = " ".join(args.prompt).strip()
	if not user_prompt:
		return 0

	try:
		from google.adk.runners import InMemoryRunner
		from google.genai import types

		# Import the ADK root agent
		from deep_search_agent.agent import root_agent
	except Exception as e:
		print("Failed to import ADK runtime.")
		print("Install: pip install google-adk google-genai")
		print(f"Error: {e}")
		return 2

	# Minimal one-shot run.
	# Note: for richer UX, use `adk run deep_search_agent`.
	runner = InMemoryRunner(app_name="kite_deep_search", agent=root_agent)
	session = runner.session_service.create_session_sync(app_name="kite_deep_search", user_id="local")

	message = types.Content(role="user", parts=[types.Part(text=user_prompt)])

	final_text: str | None = None
	last_error: str | None = None

	for event in runner.run(user_id=session.user_id, session_id=session.id, new_message=message):
		if getattr(event, "error_message", None):
			last_error = str(event.error_message)
		if event.is_final_response() and getattr(event, "content", None):
			parts = getattr(event.content, "parts", []) or []
			final_text = "".join([getattr(p, "text", "") or "" for p in parts])

	if last_error and not final_text:
		print(last_error)
		return 1

	if final_text:
		print(final_text)
	else:
		print("No response produced. Try the interactive CLI: adk run deep_search_agent")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

# 1. Start from a small official image that already has Python 3.12
FROM python:3.12-slim

# 2. Work inside the folder /app in the container
WORKDIR /app

# 3. Copy the list of libraries first and install them
#    (Docker caches this step, so rebuilds are fast when only code changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the agent's code
COPY sprint_copilot ./sprint_copilot

# 5. Default command: a safe run (dry-run, nothing posted to Slack)
#    Keys are passed at run time:  docker run --env-file .env sprint-copilot
CMD ["python", "-m", "sprint_copilot.run", "--no-slack"]

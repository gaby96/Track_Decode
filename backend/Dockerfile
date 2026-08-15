FROM ghcr.io/astral-sh/uv:0.12.3-python3.12-trixie-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-install-project

COPY . .

RUN uv sync --locked

RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home appuser \
    && chown -R appuser:appgroup /app /opt/venv

USER appuser

ENTRYPOINT []

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
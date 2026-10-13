# Build stage: the dependencies and the package are installed into a prefix, away from the final image.
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

# Run stage: the installed packages, the entry point, and a user that is not root.
FROM python:3.12-slim
COPY --from=build /install /usr/local
WORKDIR /app
COPY apps ./apps
USER 10001
EXPOSE 8082
CMD ["python", "-m", "apps.api"]

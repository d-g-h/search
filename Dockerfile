FROM node:22.23.5-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS frontend-build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY frontend ./frontend
COPY public/favicon.ico ./public/favicon.ico
RUN npm run build

FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=10001:10001 backend ./backend
COPY --chown=10001:10001 sample_listings.json ./
USER 10001:10001

FROM python-base AS tests
CMD ["python", "-m", "unittest", "discover", "-s", "backend/tests", "-v"]

FROM python-base AS runtime
COPY --from=frontend-build /app/dist ./dist
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).read()"]
CMD ["python", "-m", "backend", "--host", "0.0.0.0"]

FROM node:22

WORKDIR /code

# skip playwright browser download (only used for local screenshots)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# start with dependencies to enjoy caching
COPY ./site/package.json /code/package.json
COPY ./site/package-lock.json /code/package-lock.json
RUN npm ci

# copy rest and build
COPY ./site /code/.
RUN --mount=type=secret,id=.env env $(cat /run/secrets/.env | xargs) npm run build

FROM node:20-bookworm-slim AS builder

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY src ./src

FROM gcr.io/distroless/nodejs20-debian12:nonroot

WORKDIR /app

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/src ./src

EXPOSE 4000

CMD ["src/index.js"]

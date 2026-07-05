FROM nginx:1.27-alpine

RUN apk add --no-cache python3

WORKDIR /app
COPY site /app/site
COPY scripts/railway_sync.py /app/scripts/railway_sync.py
COPY railway/start.sh /app/railway/start.sh
COPY railway/default.conf.template /etc/nginx/conf.d/default.conf

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "/app/railway/start.sh"]

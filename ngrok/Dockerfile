FROM ngrok/ngrok:latest

# Install curl for health checks
RUN apk add --no-cache curl

# Create ngrok configuration
RUN mkdir -p /etc/ngrok
COPY ngrok.yml /etc/ngrok/ngrok.yml

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4040/api/tunnels || exit 1

CMD ["start", "--all", "--config", "/etc/ngrok/ngrok.yml"]
FROM ngrok/ngrok:alpine

# Install curl for health checks (Alpine Linux uses apk)
RUN apk add --no-cache curl

# Create ngrok configuration directory
RUN mkdir -p /etc/ngrok

# Copy ngrok configuration
COPY ngrok.yml /etc/ngrok/ngrok.yml

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4040/api/tunnels || exit 1

# Start ngrok with the configuration
CMD ["start", "--all", "--config", "/etc/ngrok/ngrok.yml"]
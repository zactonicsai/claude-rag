# Bake the dynamic-config setup file directly into the image so the temporal
# server can never fail to find it (volume mounts can silently no-op on
# Docker Desktop / WSL2 when the host path isn't where compose thinks it is).
FROM temporalio/auto-setup:1.25.2

# The upstream image runs as the non-root `temporal` user, so we have to
# elevate to root to write under /etc/temporal/, then drop back.
USER root

# Copy first, then normalize line endings — Windows users who extract the
# project zip can end up with CRLF in the YAML, which Temporal's Go parser
# rejects with cryptic errors. The `tr -d '\r'` rewrite makes this a no-op
# for files that are already LF.
COPY dynamicconfig/development-sql.yaml /tmp/development-sql.yaml
RUN mkdir -p /etc/temporal/config/dynamicconfig \
    && tr -d '\r' < /tmp/development-sql.yaml \
       > /etc/temporal/config/dynamicconfig/development-sql.yaml \
    && chmod 0644 /etc/temporal/config/dynamicconfig/development-sql.yaml \
    && rm /tmp/development-sql.yaml \
    && ls -l /etc/temporal/config/dynamicconfig/

# Restore the runtime user the upstream image expects.
USER temporal

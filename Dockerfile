# ── Java 21 Game Portal ─────────────────────────────────────────────────────
# Stack: Java 21 (Temurin) + Xvfb + x11vnc + noVNC + nginx + Flask
# Deploy: Render.com (Docker)
# ─────────────────────────────────────────────────────────────────────────────

FROM eclipse-temurin:21-jre-jammy

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Virtual display & VNC
    xvfb \
    x11vnc \
    fluxbox \
    # X11 libraries required by Java AWT/Swing
    libxext6 \
    libxi6 \
    libxrender1 \
    libxtst6 \
    libxinerama1 \
    libfontconfig1 \
    libfreetype6 \
    # Fonts
    fonts-dejavu-core \
    fonts-liberation \
    # Web server & process manager
    nginx \
    supervisor \
    # Python for API & websockify
    python3 \
    python3-pip \
    # Misc
    wget \
    gettext-base \
    procps \
    dos2unix \
    && pip3 install --no-cache-dir flask websockify \
    && rm -rf /var/lib/apt/lists/*

# Download noVNC v1.4.0 (stable)
RUN wget -q -O /tmp/novnc.tar.gz \
      https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz \
    && tar -xzf /tmp/novnc.tar.gz -C /usr/share/ \
    && mv /usr/share/noVNC-1.4.0 /usr/share/novnc \
    && rm /tmp/novnc.tar.gz

# Create required directories
RUN mkdir -p /games /api /www /var/log/supervisor

# ── Copy game JARs ────────────────────────────────────────────────────────────
COPY games/ /games/

# ── Copy API server ───────────────────────────────────────────────────────────
COPY api/server.py /api/server.py

# ── Copy frontend static files ────────────────────────────────────────────────
COPY index.html  /www/index.html
COPY style.css   /www/style.css
COPY script.js   /www/script.js
COPY data/       /www/data/
COPY images/     /www/images/

# ── Copy config files ─────────────────────────────────────────────────────────
COPY supervisord.conf         /etc/supervisor/conf.d/supervisord.conf
COPY nginx.conf.template      /etc/nginx/nginx.conf.template
COPY start.sh                 /start.sh

# Fix line endings (Windows CRLF → Unix LF) then make executable
RUN dos2unix /start.sh && chmod +x /start.sh

# ── Fluxbox minimal config (dark background, no taskbar) ─────────────────────
RUN mkdir -p /root/.fluxbox && \
    echo 'session.screen0.rootCommand: xsetroot -solid "#0a0a0f"' \
      > /root/.fluxbox/init && \
    echo 'session.screen0.toolbar.visible: false' \
      >> /root/.fluxbox/init

EXPOSE 8080

CMD ["/start.sh"]

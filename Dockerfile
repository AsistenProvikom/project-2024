# ── Java Game Portal — Custom Streaming ─────────────────────────────────────
# Stack: Java 23 + Xvfb + Flask (screenshot streaming + input injection)
# NO VNC, NO noVNC, NO websockify, NO nginx
# ─────────────────────────────────────────────────────────────────────────────

FROM eclipse-temurin:23-jre-noble

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Virtual display
    xvfb \
    fluxbox \
    # X11 libs for Java Swing/AWT
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
    # Screenshot & input tools
    imagemagick \
    xdotool \
    # Python
    python3 \
    python3-pip \
    # Process manager
    supervisor \
    # Misc
    dos2unix \
    procps \
    && pip3 install --no-cache-dir --break-system-packages \
       flask \
       gunicorn \
       mss \
       Pillow \
    && rm -rf /var/lib/apt/lists/*

# Directories
RUN mkdir -p /games /app /var/log/supervisor

# Copy game JARs
COPY games/ /games/

# Copy application
COPY api/server.py   /app/server.py
COPY index.html      /app/static/index.html
COPY style.css       /app/static/style.css
COPY script.js       /app/static/script.js
COPY data/           /app/static/data/
COPY images/         /app/static/images/

# Copy configs
COPY supervisord.conf  /etc/supervisor/conf.d/supervisord.conf
COPY start.sh          /start.sh
RUN dos2unix /start.sh && chmod +x /start.sh

# Fluxbox dark bg, no taskbar
RUN mkdir -p /root/.fluxbox && \
    echo 'session.screen0.rootCommand: xsetroot -solid "#0a0a0f"' > /root/.fluxbox/init && \
    echo 'session.screen0.toolbar.visible: false' >> /root/.fluxbox/init

EXPOSE 8080

CMD ["/start.sh"]

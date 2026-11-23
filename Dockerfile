FROM docker.io/library/nginx:1.27-alpine

COPY index.html style.css script.js /usr/share/nginx/html/
COPY data/ /usr/share/nginx/html/data/
COPY images/ /usr/share/nginx/html/images/
COPY games/ /usr/share/nginx/html/games/
COPY web-games/ /usr/share/nginx/html/web-games/
RUN chmod -R a+rX /usr/share/nginx/html/web-games
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

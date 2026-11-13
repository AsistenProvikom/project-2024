FROM nginx:1.27-alpine

COPY index.html style.css script.js /usr/share/nginx/html/
COPY data/ /usr/share/nginx/html/data/
COPY images/ /usr/share/nginx/html/images/
COPY games/ /usr/share/nginx/html/app/games/
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

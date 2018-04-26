FROM python:2-alpine

LABEL maintainer="milonas.ko@gmail.com, forked: github.com/sdhamilton6/rabbitmq-alert"

RUN apk update && \
    apk add git

RUN pip install git+git://github.com/sdhamilton6/rabbitmq-alert

CMD ["rabbitmq-alert"]

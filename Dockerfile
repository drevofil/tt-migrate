ARG BASE_IMAGE=registry.red-soft.ru/ubi8/python-313-minimal:3.13
FROM $BASE_IMAGE
USER 0
COPY tt /usr/local/bin/tt
RUN chmod +x /usr/local/bin/tt

COPY migrations.py /usr/local/bin/migrate.py
RUN chmod +x /usr/local/bin/migrate.py

USER 1001
WORKDIR /workspace
ENTRYPOINT ["python3", "/usr/local/bin/migrate.py"]
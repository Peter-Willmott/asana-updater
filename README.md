# Asana Integrations

This a repo of lightweight Asana integrations (lambda functions).

## Mapping Uploads

A job which is responsible for keeping the
[Data-Ops | Mapping Uploads]
Asana project
up to date with mapping uploads. This is based off the following criteria:

- Satellite
- Drone (Aerobotics)
- Self-service Drone

# Testing

Build

```
docker build -t jobs-asana-integrations:latest . --build-arg PIP_EXTRA_INDEX_URL=$PIP_EXTRA_INDEX_URL
```

Run container

```
docker run \
-p 9000:8080 \
-v ~/.aws:/root/.aws \
-v ~/.aero:/root/.aero \
jobs-asana-integrations:latest
```

Test container

```
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```

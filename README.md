# Asana Integrations
This a repo of lightweight Asana integrations (lambda functions).

## Survey issues
A job which is responsible for keeping the 
[Data-Ops | Tree Insights | Concernveys™](https://app.asana.com/0/1199123248405069/list) 
Asana project
up to date with survey issues. This is based off the following criteria:
- Survey status 6 (In Progress) or 8 (Satellite Imagery Issue).
- Latest internal job is errored or completed (if complete, another job should exist)
- Survey past SLA date (> 3 days)
- Latest internal job started > 7 hours ago and no end/error time


## Bitbucket PRs
Currently not in this repo. To be added.

## Google calendar
Currently not in this repo. To be added.


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
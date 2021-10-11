FROM public.ecr.aws/lambda/python:3.8

ARG PIP_EXTRA_INDEX_URL

# Install the rest of the requirements
COPY requirements.txt .
RUN pip install pip==20.2.4 --upgrade && \
    pip install -r requirements.txt --extra-index-url=$PIP_EXTRA_INDEX_URL

COPY main.py .
COPY src ./src

CMD ["main.sync_survey_issues_to_asana_handler"]
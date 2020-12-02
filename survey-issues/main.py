import requests
import boto3
import json
import os
import datetime

import sentry_sdk
from aeroclient.drf import get_response_assert_success
from aeroclient.sherlock import get_sherlock_drf_client
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

_ASANA_FIELD_CURRENT_STAGE_GID = '1199163649964273'
_ASANA_FIELD_ISSUE_TYPE_GID = '1199123943256118'
_ASANA_FIELD_SLA_ON_TRACK = '1199402168590880'
_ASANA_FIELD_CLIENT = '1199409912804538'
_ASANA_PROJECT_ID = '1199123248405069'


_ASANA_FIELD_MAPPING = {
    _ASANA_FIELD_ISSUE_TYPE_GID: {
        'error': '1199401714031293',
        'end': '1199401714031294',
        '>7hours': '1199401714031295',
        'slabreach': '1199409912804533'
    },
    _ASANA_FIELD_SLA_ON_TRACK: {
        True: '1199402168590881',
        False: '1199402168590882'
    }
}

JOBS_SECRET = json.loads(boto3.client('secretsmanager').get_secret_value(
    SecretId=os.environ.get('JOBS_SECRET_ARN')
)['SecretString'])

# Initialise the sentry config
sentry_sdk.init(
    dsn=JOBS_SECRET['SENTRY_DSN'],
    integrations=[AwsLambdaIntegration(timeout_warning=True)],
    traces_sample_rate=1.0
)
with sentry_sdk.configure_scope() as scope:
    scope.set_tag('application', 'survey-fulfilment')


def get_asana_project(project_gid):
    r = requests.get(f'https://app.asana.com/api/1.0/projects/{project_gid}',
                     headers={'Authorization': f'Bearer {JOBS_SECRET["ASANA_API_KEY"]}'})

    if r.status_code != 200:
        raise Exception('Unable to fetch project')

    return r.json()['data']


def get_asana_tasks(project_gid):
    today = datetime.date.today().strftime('%Y-%m-%d')

    r = requests.get(f'https://app.asana.com/api/1.0/tasks/?project={project_gid}&completed_since={today}'
                     f'&opt_fields=due_at,name,resource_type',
                     headers={'Authorization': f'Bearer {JOBS_SECRET["ASANA_API_KEY"]}'})

    if r.status_code != 200:
        raise Exception('Unable to fetch tasks')

    return r.json()['data']


def create_or_update_task_in_asana(survey_id, project_id, sla_datetime, custom_fields, description,
                                   existing_task_gid=None):
    title = f'Survey ID: {survey_id}'

    task_data = {
        'approval_status': 'pending',
        'completed': False,
        'due_at': sla_datetime,
        'html_notes': f'<body>{description}</body>',
        'name': title,
        'custom_fields': custom_fields,
        'projects': [
            project_id
        ]
    }
    if existing_task_gid:
        print('Updating: ', existing_task_gid)
        # Properties which give issues updating and actually do not need to be updated
        task_data.pop('approval_status')
        task_data.pop('completed')
        task_data.pop('projects')
        r = requests.put(f'https://app.asana.com/api/1.0/tasks/{existing_task_gid}', json={'data': task_data},
                         headers={'Authorization': f'Bearer {JOBS_SECRET["ASANA_API_KEY"]}'})
        if r.status_code != 200:
            raise Exception('Unable to update task')

        return r.json()['data']

    r = requests.post('https://app.asana.com/api/1.0/tasks', json={'data': task_data},
                      headers={'Authorization': f'Bearer {JOBS_SECRET["ASANA_API_KEY"]}'})
    if r.status_code != 201:
        raise Exception('Unable to create task')

    return r.json()['data']


def update_task_in_asana_to_completed(task_gid):
    r = requests.put(f'https://app.asana.com/api/1.0/tasks/{task_gid}', json={'data': {'completed': True}},
                     headers={'Authorization': f'Bearer {JOBS_SECRET["ASANA_API_KEY"]}'})
    if r.status_code != 200:
        raise Exception('Unable to update task')

    return r.json()['data']


def get_survey_issues_data():
    gateway_api_client = get_sherlock_drf_client('gateway')
    return get_response_assert_success(
        gateway_api_client.surveys_get_in_progress_latest_internal_job_status(override_http_method='get')
    )


def get_asana_current_stage_gid_for_job_type(project, type_id):
    custom_field_settings = project['custom_field_settings']
    current_stage_field = [
        c for c in custom_field_settings if _ASANA_FIELD_CURRENT_STAGE_GID == c['custom_field']['gid']
    ][0]
    try:
        enum_option = [
            e for e in current_stage_field['custom_field']['enum_options'] if str(type_id) in e['name']
        ][0]
    except IndexError:
        print('ERROR: Type id is: ', type_id)
        return None

    return enum_option['gid']


def complete_finished_tasks(existing_tasks, existing_task_gids_to_persist):
    tasks_to_complete = [
        e for e in existing_tasks if e['gid'] not in existing_task_gids_to_persist
    ]
    for t in tasks_to_complete:
        print('Completing: ', t['name'])
        update_task_in_asana_to_completed(t['gid'])


def sync():
    project = get_asana_project(_ASANA_PROJECT_ID)
    survey_issues = get_survey_issues_data()
    existing_tasks = get_asana_tasks(_ASANA_PROJECT_ID)
    # Variable to keep track of existing tasks which should be there
    existing_task_gids_to_persist = []
    for s in survey_issues:
        survey_id = s['survey_id']
        existing_tasks_for_survey = [
            e for e in existing_tasks if e['name'].split(': ')[1] == str(survey_id)
        ]
        existing_task_gid = None
        if len(existing_tasks_for_survey) > 0:
            existing_task_gid = existing_tasks_for_survey[0]['gid']
            existing_task_gids_to_persist.append(existing_task_gid)

        survey_has_error = False
        custom_fields = {
            _ASANA_FIELD_ISSUE_TYPE_GID: None,
            _ASANA_FIELD_CLIENT: f'{s["client_name"]} ({s["client_id"]})'
        }

        # Do the error checking
        if s['sla_on_track'] is False:
            survey_has_error = True
            # This entry can be overwritten if necessary
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[_ASANA_FIELD_ISSUE_TYPE_GID]['slabreach']

        if s['hours_since_start_time'] and s['hours_since_start_time'] > 7:
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[_ASANA_FIELD_ISSUE_TYPE_GID]['>7hours']

        if s['latest_job_error_time'] is not None:
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[_ASANA_FIELD_ISSUE_TYPE_GID]['error']

        if s['latest_job_end_time'] is not None:
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[_ASANA_FIELD_ISSUE_TYPE_GID]['end']

        if s['sla_datetime'] is not None:
            custom_fields[_ASANA_FIELD_SLA_ON_TRACK] =\
                _ASANA_FIELD_MAPPING[_ASANA_FIELD_SLA_ON_TRACK][s['sla_on_track']]

        current_stage_gid = get_asana_current_stage_gid_for_job_type(project, s['latest_job_type_id'])
        custom_fields[_ASANA_FIELD_CURRENT_STAGE_GID] = current_stage_gid

        if survey_has_error:
            # print('Survey has error: ', s)
            # print(custom_fields)
            sla_datetime_formatted = \
                s['sla_datetime'].replace(' ', 'T').split('+')[0] + '.000Z' if s['sla_datetime'] is not None else None

            description = f'<b>Link:</b> <a href="{s["aeroview_url"]}">Aeroview</a>\n\n' \
                          f'<b>Farm:</b> {s["farm_name"]} ({s["farm_id"]})\n\n' \
                          f'<b>Client:</b> {s["client_name"]} ({s["client_id"]})\n\n' \
                          f'<b>Orchard:</b> {s["orchard_id"]} ({s["hectares"]:.2f} ha)'

            create_or_update_task_in_asana(
                s['survey_id'], _ASANA_PROJECT_ID, sla_datetime_formatted, custom_fields, description,
                existing_task_gid
            )
            print('Created/updated task for: ', s['survey_id'])

    complete_finished_tasks(existing_tasks, existing_task_gids_to_persist)


def lambda_handler(event, context):
    sync()
    return {'success': True}


if __name__ == '__main__':
    lambda_handler(None, None)

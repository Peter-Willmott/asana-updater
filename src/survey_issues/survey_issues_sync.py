import os
import concurrent.futures

import sentry_sdk
from aeroclient.drf import get_response_assert_success
from aeroclient.sherlock import get_sherlock_drf_client
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

from src.interfaces.asana_interface import AsanaInterface
from src.utils.secrets import JOBS_SECRET


_ASANA_FIELD_CURRENT_STAGE_GID = "1199163649964273"
_ASANA_FIELD_ISSUE_TYPE_GID = "1199123943256118"
_ASANA_FIELD_SLA_ON_TRACK = "1199402168590880"
_ASANA_FIELD_CLIENT = "1199409912804538"
_ASANA_PROJECT_ID = "1199123248405069"


_ASANA_FIELD_MAPPING = {
    _ASANA_FIELD_ISSUE_TYPE_GID: {
        "error": "1199401714031293",
        "end": "1199401714031294",
        ">7hours": "1199401714031295",
        "slabreach": "1199409912804533",
    },
    _ASANA_FIELD_SLA_ON_TRACK: {True: "1199402168590881", False: "1199402168590882"},
}

_DEBUG = int(os.environ.get("DEBUG", "0"))

_MIN_HOURS_FOR_LATEST_JOB = 0.2
_MAX_HOURS_FOR_LATEST_JOB = 7

_NUMBER_CONCURRENT_WORKERS = 8

_SENTRY_APP_NAME = "asana-integrations-survey-issues"

if not _DEBUG:
    # Initialise the sentry config
    sentry_sdk.init(
        dsn=JOBS_SECRET["SENTRY_DSN"],
        integrations=[AwsLambdaIntegration(timeout_warning=True)],
        traces_sample_rate=1.0,
    )
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("application", _SENTRY_APP_NAME)


def create_or_update_task_in_asana(
    asana_interface,
    survey_id,
    project_id,
    sla_datetime,
    custom_fields,
    description,
    existing_task_gid=None,
):
    title = f"Survey ID: {survey_id}"

    task_data = {
        "approval_status": "pending",
        "completed": False,
        "due_at": sla_datetime,
        "html_notes": f"<body>{description}</body>",
        "followers": [],
        "name": title,
        "custom_fields": custom_fields,
        "projects": [project_id],
    }
    if existing_task_gid:
        # Properties which give issues updating and actually do not need to be updated
        task_data.pop("approval_status")
        task_data.pop("completed")
        task_data.pop("projects")
        task_data.pop("followers")
        return asana_interface.update_task_in_asana(existing_task_gid, task_data)

    return asana_interface.create_task_in_asana(task_data)


def get_asana_current_stage_gid_for_job_type(project, type_id):
    custom_field_settings = project["custom_field_settings"]
    current_stage_field = [
        c
        for c in custom_field_settings
        if _ASANA_FIELD_CURRENT_STAGE_GID == c["custom_field"]["gid"]
    ][0]
    try:
        enum_option = [
            e
            for e in current_stage_field["custom_field"]["enum_options"]
            if str(type_id) in e["name"]
        ][0]
    except IndexError:
        print("ERROR: Type id is: ", type_id)
        return None

    return enum_option["gid"]


def complete_finished_tasks(asana_interface, existing_tasks, existing_task_gids_to_persist):
    tasks_to_complete = [e for e in existing_tasks if e["gid"] not in existing_task_gids_to_persist]

    with concurrent.futures.ThreadPoolExecutor(max_workers=_NUMBER_CONCURRENT_WORKERS) as executor:
        list(
            executor.map(
                lambda t: asana_interface.update_task_in_asana_to_completed(t["gid"]),
                tasks_to_complete,
            )
        )


def get_survey_issues():
    gateway_api_client = get_sherlock_drf_client("gateway")
    return get_response_assert_success(
        gateway_api_client.surveys_get_in_progress_latest_internal_job_status(
            override_http_method="get"
        )
    )


def sync_survey_issues_to_asana():
    asana_interface = AsanaInterface(JOBS_SECRET["ASANA_API_KEY"])
    project = asana_interface.get_asana_project(_ASANA_PROJECT_ID)
    survey_issues = get_survey_issues()
    existing_tasks = asana_interface.get_asana_tasks(_ASANA_PROJECT_ID)
    # Variable to keep track of existing tasks which should be there
    existing_task_gids_to_persist = []

    create_or_update_task_in_asana_kwargs_list = []
    for s in survey_issues:
        survey_id = s["survey_id"]
        existing_tasks_for_survey = [
            e for e in existing_tasks if e["name"].split(": ")[1] == str(survey_id)
        ]

        survey_has_error = False
        custom_fields = {
            _ASANA_FIELD_ISSUE_TYPE_GID: None,
            _ASANA_FIELD_CLIENT: f'{s["client_name"]} ({s["client_id"]})',
        }

        # Might want to add this back in at some point
        # if s["sla_on_track"] is False:
        #     survey_has_error = True
        #     # This entry can be overwritten if necessary
        #     custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[
        #         _ASANA_FIELD_ISSUE_TYPE_GID
        #     ]["slabreach"]

        if s["hours_since_start_time"] and s["hours_since_start_time"] > _MAX_HOURS_FOR_LATEST_JOB:
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_ISSUE_TYPE_GID
            ][">7hours"]

        if (
            s["latest_job_error_time"] is not None
            and s["hours_since_error_time"] > _MIN_HOURS_FOR_LATEST_JOB
        ):
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_ISSUE_TYPE_GID
            ]["error"]
        if (
            s["latest_job_end_time"] is not None
            and s["hours_since_end_time"] > _MIN_HOURS_FOR_LATEST_JOB
        ):
            survey_has_error = True
            custom_fields[_ASANA_FIELD_ISSUE_TYPE_GID] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_ISSUE_TYPE_GID
            ]["end"]

        if s["sla_datetime"] is not None:
            custom_fields[_ASANA_FIELD_SLA_ON_TRACK] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_SLA_ON_TRACK
            ][s["sla_on_track"]]

        current_stage_gid = get_asana_current_stage_gid_for_job_type(
            project, s["latest_job_type_id"]
        )
        custom_fields[_ASANA_FIELD_CURRENT_STAGE_GID] = current_stage_gid

        existing_task_gid = None
        if len(existing_tasks_for_survey) > 0:
            existing_task_gid = existing_tasks_for_survey[0]["gid"]

        if survey_has_error:
            if existing_task_gid:
                existing_task_gids_to_persist.append(existing_task_gid)
            # print('Survey has error: ', s)
            # print(custom_fields)
            sla_datetime_formatted = (
                s["sla_datetime"].replace(" ", "T").split("+")[0] + ".000Z"
                if s["sla_datetime"] is not None
                else None
            )

            description = (
                f'<b>Link:</b> <a href="{s["aeroview_url"]}">Aeroview</a>\n\n'
                f'<b>Farm:</b> {s["farm_name"]} ({s["farm_id"]})\n\n'
                f'<b>Client:</b> {s["client_name"]} ({s["client_id"]})\n\n'
                f'<b>Orchard:</b> {s["orchard_id"]} ({s["hectares"]:.2f} ha)'
            )

            create_or_update_task_in_asana_kwargs_list.append(
                {
                    "asana_interface": asana_interface,
                    "survey_id": s["survey_id"],
                    "project_id": _ASANA_PROJECT_ID,
                    "sla_datetime": sla_datetime_formatted,
                    "custom_fields": custom_fields,
                    "description": description,
                    "existing_task_gid": existing_task_gid,
                }
            )

    print("---- Completing tasks ----")
    complete_finished_tasks(asana_interface, existing_tasks, existing_task_gids_to_persist)

    print("--- Updating / creating tasks ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=_NUMBER_CONCURRENT_WORKERS) as executor:
        list(
            executor.map(
                lambda x: create_or_update_task_in_asana(**x),
                create_or_update_task_in_asana_kwargs_list,
            )
        )

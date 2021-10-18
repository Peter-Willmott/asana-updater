import os
import concurrent.futures

from aeroclient.drf import get_response_assert_success
from aeroclient.sherlock import get_sherlock_drf_client

from src.interfaces.asana_interface import AsanaInterface
from src.utils.secrets import JOBS_SECRET

asana_interface = AsanaInterface(JOBS_SECRET["ASANA_API_KEY"])

_ASANA_PROJECT_ID = "1201076572112640"

_ASANA_FIELD_HECTARES = "1201166657450592"

_ASANA_SECTION_UPLOADS = "1201076572112641"
_ASANA_SECTION_SURVEYS = "1201167542694765"
# Not in use currently
_ASANA_SECTION_MAPPING_DRONE_SERVICE = "1201167542694774"
_ASANA_SECTION_MAPPING_DRONE_FLIGHT = "1201167542694773"


INTERNAL_TOOLS_URL = "https://internal-tools.aerobotics.com/internal-tools"

_NUMBER_CONCURRENT_WORKERS = 3


_TASK_CUSTOM_FIELD_MAPPING = {
    "client_id": "1201076842662650",
    "client_name": "1201076842663017",
    "uploaded_from_client_id": "1201076842662659",
    "mapping_drone_service_id": "1201076842662661",
    "sum_orchard_hectares": _ASANA_FIELD_HECTARES,
}

_UPDATE_TASK_ONLY_ON_COMPLETE_STATUS = os.getenv(
    "UPDATE_TASK_ONLY_ON_COMPLETE_STATUS", "xxx"
).lower() in ("true", "1", "t")


def get_unprocessed_uploads_with_thermal_data():
    gateway_api_client = get_sherlock_drf_client("gateway")
    unprocessed_uploads = sorted(
        get_response_assert_success(
            gateway_api_client.uploads_unprocessed(override_http_method="get")
        ),
        key=lambda u: u["sla_datetime"],
        reverse=True,
    )
    return [u for u in unprocessed_uploads if u["has_thermal_data"]]


def generate_description_for_survey(survey):
    return (
        f'<b><a href="{INTERNAL_TOOLS_URL}/survey/{survey["id"]}/">Aeroview Link</a></b>\n\n'
        f'<b><a href="{INTERNAL_TOOLS_URL}/human-intelligence/job-heatmap?survey_id={survey["id"]}">Heatmap Link</a></b>\n\n'
    )


def handle_survey_tasks(upload, task_gid, existing_survey_tasks):
    surveys_task_data = sorted(
        [
            {
                "name": f"Survey: {s['id']}",
                "html_notes": f"<body>{generate_description_for_survey(s)}</body>",
                "completed": True if s["status_id"] == 1 else False,
                "approval_status": "pending",
                "followers": [],
                "parent": task_gid,
                "projects": [_ASANA_PROJECT_ID],
                "custom_fields": {
                    **{v: upload[k] for k, v in _TASK_CUSTOM_FIELD_MAPPING.items()},
                    **{_ASANA_FIELD_HECTARES: s["hectares"]},
                },
            }
            for s in upload.get("surveys_in_progress") + upload.get("surveys_processed")
        ],
        key=lambda s: s["name"],
    )
    print("Surveys to create/update: ", len(surveys_task_data))
    for survey_task_data in surveys_task_data:
        existing_survey_tasks_by_name = [
            s for s in existing_survey_tasks if s["name"] == survey_task_data["name"]
        ]
        if existing_survey_tasks_by_name:
            task_gid = existing_survey_tasks_by_name[0]["gid"]
            # Properties which give issues updating and actually do not need to be updated
            survey_task_data.pop("approval_status")
            survey_task_data.pop("projects")
            survey_task_data.pop("followers")
            # Status has not changed, no need to update right now. Will have to look at internal job stage if we want
            # to handle other cases in the future
            if (
                survey_task_data["completed"] != existing_survey_tasks_by_name[0]["completed"]
                or _UPDATE_TASK_ONLY_ON_COMPLETE_STATUS is False
            ):
                asana_interface.update_task_in_asana(task_gid, survey_task_data)
                asana_interface.add_task_to_section(task_gid, _ASANA_SECTION_SURVEYS)

        else:
            task = asana_interface.create_task_in_asana(survey_task_data)
            task_gid = task["gid"]
            asana_interface.add_task_to_section(task_gid, _ASANA_SECTION_SURVEYS)


def create_or_update_upload_task(upload, existing_tasks, existing_survey_tasks):
    task_data = {
        "name": f"Upload: {upload['id']}",
        "completed": upload["processed"],
        "approval_status": "pending",
        "followers": [],
        "projects": [_ASANA_PROJECT_ID],
        "custom_fields": {v: upload[k] for k, v in _TASK_CUSTOM_FIELD_MAPPING.items()},
        "due_at": (
            upload["sla_datetime"].replace(" ", "T").split("+")[0] + ".000Z"
            if upload["sla_datetime"] is not None
            else None
        ),
    }
    existing_upload_tasks = [u for u in existing_tasks if u["name"] == task_data["name"]]
    if existing_upload_tasks:
        task_gid = existing_upload_tasks[0]["gid"]
        # Properties which give issues updating and actually do not need to be updated
        task_data.pop("approval_status")
        task_data.pop("projects")
        task_data.pop("followers")

        # If processing status has not changed, no need to update right now
        if (
            task_data["completed"] != existing_upload_tasks[0]["completed"]
            or _UPDATE_TASK_ONLY_ON_COMPLETE_STATUS is False
        ):
            asana_interface.update_task_in_asana(task_gid, task_data)
    else:
        task = asana_interface.create_task_in_asana(task_data)
        task_gid = task["gid"]

    handle_survey_tasks(upload, task_gid, existing_survey_tasks)


def complete_finished_uploads(uploads, existing_upload_tasks):
    """
    Do we need to include completion of surveys at this level?
    :param uploads:
    :param existing_upload_tasks:
    :return:
    """
    upload_task_names = [f"Upload: {upload['id']}" for upload in uploads]
    tasks_to_complete = [e for e in existing_upload_tasks if e["name"] not in upload_task_names]
    print(f"Need to complete: {len(tasks_to_complete)} uploads")

    with concurrent.futures.ThreadPoolExecutor(max_workers=_NUMBER_CONCURRENT_WORKERS) as executor:
        list(
            executor.map(
                lambda t: asana_interface.update_task_in_asana_to_completed(t["gid"]),
                tasks_to_complete,
            )
        )


def add_upload_task_to_section_ordered(task_gid, tasks):
    """
    This function requires an ordered list of tasks in descending order (due_at latest first)
    :param task_gid:
    :param tasks:
    :return:
    """
    task_index = [i for i, task in enumerate(tasks) if task["gid"] == task_gid][0]
    if task_index == 0:
        kwargs = {"insert_after": tasks[task_index + 1]["gid"]}
    else:
        kwargs = {"insert_before": tasks[task_index - 1]["gid"]}

    return asana_interface.add_task_to_section(task_gid, _ASANA_SECTION_UPLOADS, **kwargs)


def sync_thermal_uploads():
    thermal_uploads = get_unprocessed_uploads_with_thermal_data()
    print("Number of thermal uploads: ", len(thermal_uploads))

    existing_upload_tasks = asana_interface.get_asana_tasks(section=_ASANA_SECTION_UPLOADS)
    existing_survey_tasks = asana_interface.get_asana_tasks(section=_ASANA_SECTION_SURVEYS)

    print("Number existing uploads: ", len(existing_upload_tasks))

    with concurrent.futures.ThreadPoolExecutor(max_workers=_NUMBER_CONCURRENT_WORKERS) as executor:
        list(
            executor.map(
                lambda upload: create_or_update_upload_task(upload, existing_upload_tasks, existing_survey_tasks),
                thermal_uploads,
            )
        )

    upload_tasks_to_sort = [
        t
        for t in sorted(
            asana_interface.get_asana_tasks(section=_ASANA_SECTION_UPLOADS),
            key=lambda t: t["due_at"], reverse=True
        )
        if t.get("completed") is False
    ]

    # The more concurrent workers the more chance of there being error when sorting (based on timing).
    # The idea is that after 2-3 syncs it should stabilise
    with concurrent.futures.ThreadPoolExecutor(max_workers=_NUMBER_CONCURRENT_WORKERS) as executor:
        list(
            executor.map(
                lambda task: add_upload_task_to_section_ordered(task["gid"], upload_tasks_to_sort),
                upload_tasks_to_sort,
            )
        )

    complete_finished_uploads(thermal_uploads, upload_tasks_to_sort)

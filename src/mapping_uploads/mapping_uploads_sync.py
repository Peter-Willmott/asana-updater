import os
from itertools import groupby
import datetime
from dateutil.relativedelta import relativedelta

from src.interfaces.asana_interface import AsanaInterface
from src.utils.secrets import JOBS_SECRET

asana_interface = AsanaInterface(JOBS_SECRET["ASANA_API_KEY"])

_ASANA_PROJECT_ID = ""

_ASANA_SECTION_DRONE_SERVICE = ""
_ASANA_SECTION_DRONE_SERVICE_UPLOADS = ""

_ASANA_SECTION_SELF_SERVICED = ""

_ASANA_SECTION_SATELLITE = ""

_ASANA_FIELD_DRONE_SERVICE = ""
_ASANA_FIELD_SERVICE_TYPE = ""
_ASANA_FIELD_IMAGE_TYPE = ""
_ASANA_FIELD_CLIENT = ""
_ASANA_FIELD_FARM = ""
_ASANA_FIELD_PERCENTAGE_COMPLETE = ""
_ASANA_FIELD_BLOCKS_COMPLETED = ""
_ASANA_FIELD_BLOCKS_UPLOADED = ""
_ASANA_FIELD_SLA_ON_TRACK = ""

_ASANA_FIELD_MAPPING = {
    _ASANA_FIELD_SERVICE_TYPE: {
        "Serviced": "",
        "Self-Serviced": "",
    },
    _ASANA_FIELD_IMAGE_TYPE: {
        "Drone": "",
        "Satellite": "",
    },
    _ASANA_FIELD_SLA_ON_TRACK: {"Yes": "", "No": ""},
}

_UPDATE_TASK_ONLY_ON_COMPLETE_STATUS = os.getenv(
    "UPDATE_TASK_ONLY_ON_COMPLETE_STATUS", "True"
).lower() in ("true", "1", "t")


def get_unprocessed_uploads():
    gateway_api_client = get_sherlock_drf_client("gateway")
    six_months = datetime.datetime.today() + relativedelta(months=-6)
    unprocessed_uploads = sorted(
        get_response_assert_success(
            gateway_api_client.requester.get_request(
                f"/uploads/unprocessed/?upload_completed_on__gte={six_months}"
            )
        ),
        key=lambda u: u["id"],
    )

    # Don't return thermal data as it is already covered in the thermal uploads asana board
    uploads = [u for u in unprocessed_uploads if u["has_thermal_data"] == False]

    drone_flights = [ds for ds in uploads if ds["mapping_drone_service_id"]]

    drone_flights.sort(key=lambda x: x["mapping_drone_service_id"])
    ds_grouped_uploads = []
    for k, v in groupby(drone_flights, key=lambda x: x["mapping_drone_service_id"]):
        ds_grouped_uploads.append(list(v))

    satellite_flights = [u for u in uploads if u["satellite_task_id"]]
    self_serviced_flights = [
        u
        for u in uploads
        if u["satellite_task_id"] is None and u["mapping_drone_service_id"] is None
    ]

    return (ds_grouped_uploads, satellite_flights, self_serviced_flights)


def generate_description_for_upload(upload):
    return (
        f'<b>Farm: {upload["farm_name"]} ({upload["farm_id"]})</b>\n\n'
        f'<b>Client: {upload["client_name"]} ({upload["client_id"]})</b>\n\n'
        f'<b>Mapping Drone Service ID: {upload["mapping_drone_service_id"]}</b>\n\n'
        f'<b>Blocks Uploaded: {upload["count_orchards"]}</b>\n\n'
        f'<b>Blocks Completed: {upload["count_surveys_processed"]}</b>\n\n'
        f'<b>Blocks In-Progress: {upload["count_surveys_in_progress"]}</b>\n\n'
        f'<b>Blocks Voided: {upload["count_surveys_voided"]}</b>\n\n'
        f'<b>Percentage Completed: {((upload["count_surveys_processed"])/upload["count_orchards"])*100} %</b>\n\n'
    )


def handle_upload_tasks(upload, task_gid, existing_upload_tasks):

    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    uploads_task_data = sorted(
        [
            {
                "name": f"Upload: {u['id']}",
                "html_notes": f"<body>{generate_description_for_upload(u)}</body>",
                "approval_status": "pending",
                "completed": u["processed"],
                "followers": [],
                "parent": task_gid,
                "projects": [_ASANA_PROJECT_ID],
                "custom_fields": {
                    **{_ASANA_FIELD_CLIENT: f'{u["client_name"]} ({u["client_id"]})'},
                    **{_ASANA_FIELD_FARM: f'{u["farm_name"]} ({u["farm_id"]})'},
                    **{_ASANA_FIELD_BLOCKS_COMPLETED: u["count_surveys_processed"]},
                    **{_ASANA_FIELD_BLOCKS_UPLOADED: u["count_orchards"]},
                    **{
                        _ASANA_FIELD_DRONE_SERVICE: u["mapping_drone_service_id"],
                    },
                    **{
                        _ASANA_FIELD_IMAGE_TYPE: _ASANA_FIELD_MAPPING[
                            _ASANA_FIELD_IMAGE_TYPE
                        ]["Drone"]
                    },
                    **{
                        _ASANA_FIELD_SERVICE_TYPE: _ASANA_FIELD_MAPPING[
                            _ASANA_FIELD_SERVICE_TYPE
                        ]["Serviced"]
                    },
                    **{
                        _ASANA_FIELD_PERCENTAGE_COMPLETE: (
                            (u["count_surveys_processed"]) / u["count_orchards"]
                        )
                    },
                    **{
                        _ASANA_FIELD_SLA_ON_TRACK: _ASANA_FIELD_MAPPING[
                            _ASANA_FIELD_SLA_ON_TRACK
                        ]["Yes"]
                        if datetime.datetime.strptime(
                            u["sla_datetime"], "%Y-%m-%dT%H:%M:%S%z"
                        ).strftime("%Y-%m-%dT%H:%M:%S")
                        > now
                        else _ASANA_FIELD_MAPPING[_ASANA_FIELD_SLA_ON_TRACK]["No"]
                    },
                },
                "due_at": (
                    u["sla_datetime"].replace(" ", "T").split("+")[0] + ".000Z"
                    if u["sla_datetime"] is not None
                    else None
                ),
            }
            for u in upload
        ],
        key=lambda s: s["due_at"],
    )

    print("Uploads to create/update: ", len(uploads_task_data))
    for upload_task_data in uploads_task_data:
        existing_upload_tasks_by_name = [
            u for u in existing_upload_tasks if u["name"] == upload_task_data["name"]
        ]
        if existing_upload_tasks_by_name:
            task_gid = existing_upload_tasks_by_name[0]["gid"]
            # Properties which give issues updating and actually do not need to be updated
            upload_task_data.pop("approval_status")
            upload_task_data.pop("projects")
            upload_task_data.pop("followers")

            asana_interface.update_task_in_asana(task_gid, upload_task_data)
            asana_interface.add_task_to_section(
                task_gid, _ASANA_SECTION_DRONE_SERVICE_UPLOADS
            )

        else:
            task = asana_interface.create_task_in_asana(upload_task_data)
            task_gid = task["gid"]
            asana_interface.add_task_to_section(
                task_gid, _ASANA_SECTION_DRONE_SERVICE_UPLOADS
            )


def create_or_update_upload_task_for_drone_service(
    upload, existing_tasks, existing_ds_upload_tasks
):

    slas = [upload[i]["sla_datetime"] for i in range(len(upload))]
    slas.sort(key=lambda e: (e is None, e))

    blocks_completed = [u["count_surveys_processed"] for u in upload]
    blocks_in_upload = [u["count_orchards"] for u in upload]

    if len(upload) > 1:
        farms = [str(", ".join(set([u["farm_name"] for u in upload])))]
    else:
        farms = [f'{upload[0]["farm_name"]} ({upload[0]["farm_id"]})']

    custom_fields = {
        _ASANA_FIELD_CLIENT: f'{upload[0]["client_name"]} ({upload[0]["client_id"]})',
        _ASANA_FIELD_FARM: farms[0],
        _ASANA_FIELD_BLOCKS_COMPLETED: sum(blocks_completed),
        _ASANA_FIELD_BLOCKS_UPLOADED: sum(blocks_in_upload),
        _ASANA_FIELD_DRONE_SERVICE: upload[0]["mapping_drone_service_id"],
        _ASANA_FIELD_IMAGE_TYPE: _ASANA_FIELD_MAPPING[_ASANA_FIELD_IMAGE_TYPE]["Drone"],
        _ASANA_FIELD_SERVICE_TYPE: _ASANA_FIELD_MAPPING[_ASANA_FIELD_SERVICE_TYPE][
            "Serviced"
        ],
        _ASANA_FIELD_PERCENTAGE_COMPLETE: (
            sum(blocks_completed) / sum(blocks_in_upload)
        ),
    }

    earliest_sla_as_datetime = datetime.datetime.strptime(
        slas[0], "%Y-%m-%dT%H:%M:%S%z"
    ).strftime("%Y-%m-%dT%H:%M:%S")
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    if slas[0] is not None:
        if earliest_sla_as_datetime > now:
            custom_fields[_ASANA_FIELD_SLA_ON_TRACK] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_SLA_ON_TRACK
            ]["Yes"]
        if earliest_sla_as_datetime < now:
            custom_fields[_ASANA_FIELD_SLA_ON_TRACK] = _ASANA_FIELD_MAPPING[
                _ASANA_FIELD_SLA_ON_TRACK
            ]["No"]

    task_data = {
        "name": f"{upload[0]['client_name']} | DS: {upload[0]['mapping_drone_service_id']}",
        "completed": upload[0]["processed"],
        "approval_status": "pending",
        "followers": [],
        "projects": [_ASANA_PROJECT_ID],
        "custom_fields": custom_fields,
        "due_at": slas[0].replace(" ", "T").split("+")[0] + ".000Z",
    }
    existing_upload_tasks = [
        u for u in existing_tasks if u["name"] == task_data["name"]
    ]
    if existing_upload_tasks:
        task_gid = existing_upload_tasks[0]["gid"]
        # Properties which give issues updating and actually do not need to be updated
        task_data.pop("approval_status")
        task_data.pop("projects")
        task_data.pop("followers")

        asana_interface.update_task_in_asana(task_gid, task_data)
        asana_interface.add_task_to_section(task_gid, _ASANA_SECTION_DRONE_SERVICE)
    else:
        task = asana_interface.create_task_in_asana(task_data)
        task_gid = task["gid"]
        asana_interface.add_task_to_section(task_gid, _ASANA_SECTION_DRONE_SERVICE)

    handle_upload_tasks(upload, task_gid, existing_ds_upload_tasks)


def create_or_update_upload_task(
    upload, existing_tasks, section, image_type, service_type
):

    due_date_sla_micro = upload["sla_datetime"].replace(" ", "T").split("+")[0]
    due_date_sla = due_date_sla_micro.split(".")[0] + "+0000"
    sla_date = datetime.datetime.strptime(due_date_sla, "%Y-%m-%dT%H:%M:%S%z").strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    task_data = {
        "name": f"{upload['client_name']} | Upload: {upload['id']}",
        "completed": upload["processed"],
        "html_notes": f"<body>{generate_description_for_upload(upload)}</body>",
        "approval_status": "pending",
        "followers": [],
        "projects": [_ASANA_PROJECT_ID],
        "custom_fields": {
            **{_ASANA_FIELD_CLIENT: f'{upload["client_name"]} ({upload["client_id"]})'},
            **{_ASANA_FIELD_FARM: f'{upload["farm_name"]} ({upload["farm_id"]})'},
            **{_ASANA_FIELD_BLOCKS_COMPLETED: upload["count_surveys_processed"]},
            **{_ASANA_FIELD_BLOCKS_UPLOADED: upload["count_orchards"]},
            **{
                _ASANA_FIELD_DRONE_SERVICE: upload["mapping_drone_service_id"],
            },
            **{
                _ASANA_FIELD_IMAGE_TYPE: _ASANA_FIELD_MAPPING[_ASANA_FIELD_IMAGE_TYPE][
                    image_type
                ]
            },
            **{
                _ASANA_FIELD_SERVICE_TYPE: _ASANA_FIELD_MAPPING[
                    _ASANA_FIELD_SERVICE_TYPE
                ][service_type]
            },
            **{
                _ASANA_FIELD_PERCENTAGE_COMPLETE: (
                    (upload["count_surveys_processed"]) / upload["count_orchards"]
                )
            },
            **{
                _ASANA_FIELD_SLA_ON_TRACK: _ASANA_FIELD_MAPPING[
                    _ASANA_FIELD_SLA_ON_TRACK
                ]["Yes"]
                if sla_date > now
                else _ASANA_FIELD_MAPPING[_ASANA_FIELD_SLA_ON_TRACK]["No"]
            },
        },
        "due_at": due_date_sla,
    }
    existing_upload_tasks = [
        u for u in existing_tasks if u["name"] == task_data["name"]
    ]
    if existing_upload_tasks:
        task_gid = existing_upload_tasks[0]["gid"]
        # Properties which give issues updating and actually do not need to be updated
        task_data.pop("approval_status")
        task_data.pop("projects")
        task_data.pop("followers")

        asana_interface.update_task_in_asana(task_gid, task_data)
        asana_interface.add_task_to_section(task_gid, section)
    else:
        task = asana_interface.create_task_in_asana(task_data)
        task_gid = task["gid"]
        asana_interface.add_task_to_section(task_gid, section)


def asana_upload_sections(uploads, section, image, service):
    existing_tasks = asana_interface.get_asana_tasks(section=section)

    if image == "Satellite":
        print("Number of Satellite uploads: ", len(uploads))
        print("Number existing Satellite uploads: ", len(existing_tasks))
    else:
        print("Number of Self-service uploads: ", len(uploads))
        print("Number existing Self-service uploads: ", len(existing_tasks))

    for upload in uploads:
        print(f"---------- On Upload: {upload['id']} ----------")
        create_or_update_upload_task(upload, existing_tasks, section, image, service)


def sync_mapping_uploads():
    (
        drone_service_uploads,
        satellite_uploads,
        self_serviced_uploads,
    ) = get_unprocessed_uploads()

    # Drone Service Uploads
    print("Number of Drone services: ", len(drone_service_uploads))

    existing_drone_service_tasks = asana_interface.get_asana_tasks(
        section=_ASANA_SECTION_DRONE_SERVICE
    )
    existing_ds_upload_tasks = asana_interface.get_asana_tasks(
        section=_ASANA_SECTION_DRONE_SERVICE_UPLOADS
    )

    print("Number existing drone services: ", len(existing_drone_service_tasks))
    print("Number existing drone service uploads: ", len(existing_ds_upload_tasks))

    for upload in drone_service_uploads:
        print(
            f"---------- On drone service: {upload[0]['mapping_drone_service_id']} ----------"
        )
        create_or_update_upload_task_for_drone_service(
            upload, existing_drone_service_tasks, existing_ds_upload_tasks
        )

    # Self Service Uploads
    asana_upload_sections(
        self_serviced_uploads, _ASANA_SECTION_SELF_SERVICED, "Drone", "Self-Serviced"
    )

    # Satellite Uploads
    asana_upload_sections(
        satellite_uploads, _ASANA_SECTION_SATELLITE, "Satellite", "Serviced"
    )

import datetime

from src.interfaces.asana_interface import AsanaInterface
from src.interfaces.bitbucket_interface import BitbucketInterface
from src.utils.utilities import unmark
from src.utils.secrets import _JOBS_SECRET

# TODO: Should this be moved to a secret?
BITBUCKET_USER_TO_ASANA_MAPPING = {
    # 'Nicholas Coles': {
    #     'assignee_id': '1194547565118472',
    #     'project_id': '1196876844076184'
    # },
    "Josh Perry": {
        "assignee_id": "1160523081504297",
        "project_id": "1196431820953784",
    },
    "Nick Anderson": {
        "assignee_id": "1188006444939895",
        "project_id": "1198871414062117",
    },
}


def format_pr_for_asana(pr):
    return [
        {
            "assignee": r["user"]["display_name"],
            "task_name": pr["rendered"]["title"]["raw"],
            "link": pr["links"]["html"]["href"],
            "status": pr["state"],
            "approved": r["approved"],
            "description": unmark(pr["description"]),
        }
        for r in pr["participants"]
        if r["role"] == "REVIEWER"
    ]


def gather_bitbucket_information():
    print("--- Gathering information from bitbucket ---")
    access_token = BitbucketInterface.get_access_token()
    workspace_members = BitbucketInterface.get_workspace_members(access_token)
    bitbucket_pr_tasks = []

    for w in workspace_members:
        prs_for_user = BitbucketInterface.get_prs_for_user(access_token, w["uuid"])

        for pr_for_user in prs_for_user:
            pr_additional_info = BitbucketInterface.get_additional_info_for_pr(
                access_token, pr_for_user["links"]["self"]["href"]
            )
            asana_tasks = format_pr_for_asana(pr_additional_info)
            bitbucket_pr_tasks.extend(asana_tasks)

    return bitbucket_pr_tasks


def get_asana_tasks_to_create(bitbucket_pr_tasks, asana_tasks):
    # TODO: should we also be creating tasks for approved PRs? Is that useful?
    unapproved_bitbucket_prs = list(
        filter(lambda x: (not x["approved"]), bitbucket_pr_tasks)
    )
    return [
        t
        for t in unapproved_bitbucket_prs
        if t["task_name"] not in [a["name"] for a in asana_tasks]
    ]


def get_asana_tasks_to_complete(bitbucket_pr_tasks, asana_tasks):
    # Only leave un-approved PRs as incomplete Asana tasks
    asana_tasks_to_keep = [
        a
        for a in asana_tasks
        if a["name"]
        in [b["task_name"] for b in bitbucket_pr_tasks if not b["approved"]]
    ]
    asana_tasks_to_complete = [a for a in asana_tasks if a not in asana_tasks_to_keep]
    return asana_tasks_to_complete


def create_pr_task_in_asana(
    asana_client, assignee_id, project_id, title, description, link, followers
):
    task_data = {
        "approval_status": "pending",
        "assignee": assignee_id,
        "completed": False,
        "due_on": datetime.date.today().strftime("%Y-%m-%d"),
        "notes": f"{link} \n\n {description}",
        "name": title,
        "projects": [project_id],
        "followers": followers,
    }
    return AsanaInterface.create_task_in_asana(asana_client, task_data)


def sync_asana_tasks_from_bitbucket(bitbucket_pr_tasks):
    print("---- Getting asana data and syncing ----")

    for user in BITBUCKET_USER_TO_ASANA_MAPPING:
        print("On user: ", user)
        assignee_id = BITBUCKET_USER_TO_ASANA_MAPPING[user]["assignee_id"]
        project_id = BITBUCKET_USER_TO_ASANA_MAPPING[user]["project_id"]

        print("Key is: ", _JOBS_SECRET[f"{assignee_id}_ASANA_API_KEY"])

        asana_client = AsanaInterface.get_asana_client(
            _JOBS_SECRET[f"{assignee_id}_ASANA_API_KEY"]
        )

        bitbucket_pr_tasks_for_user = [
            b for b in bitbucket_pr_tasks if b["assignee"] == user
        ]

        asana_tasks = AsanaInterface.get_asana_tasks(asana_client, project_id)
        asana_tasks_to_create = get_asana_tasks_to_create(
            bitbucket_pr_tasks_for_user, asana_tasks
        )
        asana_tasks_to_complete = get_asana_tasks_to_complete(
            bitbucket_pr_tasks_for_user, asana_tasks
        )

        for a in asana_tasks_to_create:
            print("Creating task: ", a)
            resp = create_pr_task_in_asana(
                asana_client,
                assignee_id,
                project_id,
                a["task_name"],
                a["description"],
                a["link"],
            )
            # print(resp)

        for a in asana_tasks_to_complete:
            print("Updating task: ", a)
            resp = AsanaInterface.update_task_in_asana_to_completed(
                asana_client, a["gid"]
            )
            # print(resp)


def sync_asana_and_bitbucket_prs():
    bitbucket_pr_tasks = gather_bitbucket_information()
    sync_asana_tasks_from_bitbucket(bitbucket_pr_tasks)


if __name__ == "__main__":
    sync_asana_and_bitbucket_prs()

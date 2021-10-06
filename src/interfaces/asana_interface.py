import asana
import datetime

import requests


class AsanaInterface:
    @staticmethod
    def get_asana_client(api_key):
        return asana.Client.access_token(api_key)

    @staticmethod
    def get_asana_project(asana_client, project_gid):
        result = asana_client.projects.get_project(project_gid, opt_pretty=True)
        return result

    @staticmethod
    def get_asana_tasks(asana_client, project_id):
        today = datetime.date.today().strftime("%Y-%m-%d")
        result = asana_client.tasks.get_tasks(
            {
                "project": project_id,
                "completed_since": today,
                "opt_fields": "due_at,name,resource_type",
            },
            opt_pretty=True,
        )
        return list(result)

    @staticmethod
    def create_task_in_asana(asana_client, task_data):
        return asana_client.tasks.create_task(task_data, opt_pretty=True)

    @staticmethod
    def update_task_in_asana_to_completed(asana_client, task_gid):
        return AsanaInterface.update_task_in_asana(
            asana_client, task_gid, {"completed": True}
        )

    @staticmethod
    def update_task_in_asana(asana_client, task_gid, task_data):
        return asana_client.tasks.update_task(task_gid, task_data, opt_pretty=True)

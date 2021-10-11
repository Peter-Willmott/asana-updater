import asana
import datetime


class AsanaInterface:
    def __init__(self, api_key):
        self.asana_client = self.get_asana_client(api_key)

    @staticmethod
    def get_asana_client(api_key):
        return asana.Client.access_token(api_key)

    def get_asana_project(self, project_gid):
        result = self.asana_client.projects.get_project(project_gid, opt_pretty=True)
        return result

    def get_asana_tasks(self, project_id):
        today = datetime.date.today().strftime("%Y-%m-%d")
        result = self.asana_client.tasks.get_tasks(
            {
                "project": project_id,
                "completed_since": today,
                "opt_fields": "due_at,name,resource_type",
            },
            opt_pretty=True,
        )
        return list(result)

    def create_task_in_asana(self, task_data):
        return self.asana_client.tasks.create_task(task_data, opt_pretty=True)

    def update_task_in_asana_to_completed(self, task_gid):
        return self.update_task_in_asana(task_gid, {"completed": True})

    def update_task_in_asana(self, task_gid, task_data):
        return self.asana_client.tasks.update_task(task_gid, task_data, opt_pretty=True)

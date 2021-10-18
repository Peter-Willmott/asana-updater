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

    def get_asana_tasks(self, project_id=None, opt_fields="due_at,name,resource_type,completed", **filter_kwargs):
        today = datetime.date.today().strftime("%Y-%m-%d")
        filters = {
            "completed_since": today,
            "opt_fields": opt_fields,
            **filter_kwargs,
        }
        if project_id:
            filters["project"] = project_id
        result = self.asana_client.tasks.get_tasks(
            filters,
            opt_pretty=True,
        )
        return list(result)

    def get_subtasks(self, task_gid):
        return self.asana_client.tasks.get_subtasks_for_task(task_gid, opt_pretty=True)

    def get_task(self, task_gid):
        return self.asana_client.tasks.get_task(task_gid, opt_pretty=True)

    def add_task_to_section(self, task_gid, section_gid, **kwargs):
        return self.asana_client.sections.add_task_for_section(
            section_gid, {"task": task_gid, **kwargs}, opt_pretty=True
        )

    def create_task_in_asana(self, task_data):
        return self.asana_client.tasks.create_task(task_data, opt_pretty=True)

    def create_subtask(self, task_gid, subtask_data):
        return self.asana_client.tasks.create_subtask_for_task(
            task_gid, subtask_data, opt_pretty=True
        )

    def update_task_in_asana_to_completed(self, task_gid):
        return self.update_task_in_asana(task_gid, {"completed": True})

    def update_task_in_asana(self, task_gid, task_data):
        return self.asana_client.tasks.update_task(task_gid, task_data, opt_pretty=True)

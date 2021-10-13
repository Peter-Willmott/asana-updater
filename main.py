from src.bitbucket_pr.bitbucket_asana_sync import sync_asana_and_bitbucket_prs
from src.survey_issues.survey_issues_sync import sync_survey_issues_to_asana
from src.thermal_uploads.thermal_uploads_sync import sync_thermal_uploads


def sync_asana_and_bitbucket_prs_handler(event, context):
    return sync_asana_and_bitbucket_prs()


def sync_survey_issues_to_asana_handler(event, context):
    return sync_survey_issues_to_asana()


def sync_thermal_uploads_handler(event, context):
    return sync_thermal_uploads()


if __name__ == "__main__":
    sync_thermal_uploads_handler(None, None)

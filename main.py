from src.bitbucket_pr.bitbucket_asana_sync import sync_asana_and_bitbucket_prs
from src.survey_issues.survey_issues_sync import sync_survey_issues_to_asana


def sync_asana_and_bitbucket_prs_handler(event, context):
    return sync_asana_and_bitbucket_prs()


def sync_survey_issues_to_asana_handler(event, context):
    return sync_survey_issues_to_asana()


if __name__ == "__main__":
    sync_survey_issues_to_asana_handler(None, None)

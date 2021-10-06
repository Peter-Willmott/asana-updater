from src.bitbucket_pr.bitbucket_asana_sync import sync_asana_and_bitbucket_prs

from src.survey_issues.survey_issues_sync import sync_survey_issues_to_asana

RUN_BITBUCKET_ASANA_SYNC_JOB = True
RUN_SURVEY_ISSUES_JOB = False


def main():
    if RUN_BITBUCKET_ASANA_SYNC_JOB:
        sync_asana_and_bitbucket_prs()
    if RUN_SURVEY_ISSUES_JOB:
        sync_survey_issues_to_asana()


def lambda_handler(event, context):
    main()
    return {"success": True}


if __name__ == "__main__":
    lambda_handler(None, None)

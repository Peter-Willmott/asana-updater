from aeroclient.drf import get_response_assert_success
from aeroclient.sherlock import get_sherlock_drf_client


class GatewayInterface:
    gateway_api = get_sherlock_drf_client("gateway")

    @classmethod
    def get_survey_issues_data(cls) -> dict:
        return get_response_assert_success(
            cls.gateway_api_client.surveys_get_in_progress_latest_internal_job_status(
                override_http_method="get"
            )
        )

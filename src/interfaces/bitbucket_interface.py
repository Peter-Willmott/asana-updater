import requests

from src.utils.secrets import JOBS_SECRET


BITBUCKET_URL = "https://bitbucket.org/site/oauth2/access_token"
BITBUCKET_BASE = "https://api.bitbucket.org/2.0"
BITBUCKET_PR_URL = "https://api.bitbucket.org/2.0/pullrequests"
BITBUCKET_AEROBOTICS_MEMBERS_URL = (
    "https://api.bitbucket.org/2.0/workspaces/aerobotics/members"
)


class BitbucketInterface:
    @staticmethod
    def get_access_token():
        return requests.post(
            BITBUCKET_URL,
            headers={
                "content-type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "client_id": JOBS_SECRET["BITBUCKET_CLIENT_ID"],
                "client_secret": JOBS_SECRET["BITBUCKET_SECRET"],
                "expires_in": 1000,
            },
        ).json()["access_token"]

    @staticmethod
    def get_workspace_members(access_token):
        resp = requests.get(
            BITBUCKET_AEROBOTICS_MEMBERS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        ).json()
        return [
            {"uuid": r["user"]["uuid"], "display_name": r["user"]["display_name"]}
            for r in resp["values"]
        ]

    @staticmethod
    def get_additional_info_for_pr(access_token, pr_self_url):
        resp = requests.get(
            pr_self_url,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        ).json()

        return resp

    @staticmethod
    def get_prs_for_user(access_token, user_uuid):
        return requests.get(
            f"{BITBUCKET_PR_URL}/{user_uuid}",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        ).json()["values"]

import requests


class ForgeApi:
    def __init__(self, session):
        self.session = session
        self.forge_uri = "https://forge.laravel.com/api/v1"

    def get_nginx_config(self, server_id, site_id):
        try:
            response = self.session.get(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/nginx"
            )
            response.raise_for_status()
            return response.content.decode("utf-8")

        except requests.RequestException as e:
            raise Exception("Failed to get nginx config from Laravel Forge API") from e

    def set_nginx_config(self, server_id, site_id, nginx_config):
        try:
            response = self.session.put(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/nginx",
                json={"content": nginx_config},
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception("Failed to set nginx config from Laravel Forge API") from e

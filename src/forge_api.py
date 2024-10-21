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

    def update_site(self, server_id, site_id, **kwargs):
        try:
            response = self.session.put(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}",
                json={**kwargs},
            )
            response.raise_for_status()
            return response.json()["site"]
        except requests.RequestException as e:
            raise Exception("Failed to update site from Laravel Forge API") from e

    def list_certificates(self, server_id, site_id):
        try:
            response = self.session.get(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/certificates"
            )
            response.raise_for_status()
            return response.json()["certificates"]
        except requests.RequestException as e:
            raise Exception("Failed to list certificates from Laravel Forge API") from e

    def get_certificate_by_id(self, server_id, site_id, certificate_id):
        try:
            response = self.session.get(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/certificates/{certificate_id}"
            )
            response.raise_for_status()
            return response.json()["certificate"]
        except requests.RequestException as e:
            raise Exception(
                "Failed to get certificate by id from Laravel Forge API"
            ) from e

    def activate_certificate(self, server_id, site_id, certificate_id):
        try:
            response = self.session.post(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/certificates/{certificate_id}/activate"
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(
                "Failed to activate certificate from Laravel Forge API"
            ) from e

    def create_certificate(self, server_id, site_id, domains):
        try:
            response = self.session.post(
                f"{self.forge_uri}/servers/{server_id}/sites/{site_id}/certificates/letsencrypt",
                json={"domains": domains},
            )
            response.raise_for_status()
            return response.json()["certificate"]
        except requests.RequestException as e:
            raise Exception(
                "Failed to create certificate from Laravel Forge API"
            ) from e

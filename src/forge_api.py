import requests


class ForgeApi:
    def __init__(self, session):
        self.session = session
        self.forge_uri = "https://forge.laravel.com/api/v1"

    # --- Sites ---
    def get_all_sites(self, server_id):
        try:
            response = self.session.get(f"{self.forge_uri}/servers/{server_id}/sites")
            response.raise_for_status()
            sites = response.json()["sites"]
            return sites
        except requests.RequestException as e:
            raise Exception("Failed to get sites from Laravel Forge API") from e

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

    # --- nginx ---

    def get_nginx_templates(self, server_id):
        try:
            response = self.session.get(
                f"{self.forge_uri}/servers/{server_id}/nginx/templates"
            )
            response.raise_for_status()
            return response.json()["templates"]
        except requests.RequestException as e:
            raise Exception(
                "Failed to get nginx templates from Laravel Forge API"
            ) from e

    def create_nginx_template(self, server_id, name, content):
        try:
            response = self.session.post(
                f"{self.forge_uri}/servers/{server_id}/nginx/templates",
                json={
                    "content": content,
                    "name": name,
                },
            )
            response.raise_for_status()
            return response.json()["template"]["id"]
        except requests.RequestException as e:
            raise Exception(
                "Failed to create nginx template from Laravel Forge API"
            ) from e

    def get_nginx_template_by_id(self, server_id, template_id):
        try:
            response = self.session.get(
                f"{self.forge_uri}/servers/{server_id}/nginx/templates/{template_id}"
            )
            response.raise_for_status()
            return response.json()["template"]["content"]
        except requests.RequestException as e:
            raise Exception(
                "Failed to get nginx template by id from Laravel Forge API"
            ) from e

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

    # --- Certificates ---

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

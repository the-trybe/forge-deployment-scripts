import logging
import os
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from utils import replace_nginx_variables, replace_secrets_yaml, wait

load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    forge_uri = "https://forge.laravel.com/api/v1"
    forge_api_token = os.getenv("FORGE_API_TOKEN")
    if forge_api_token is None:
        raise Exception("FORGE_API_TOKEN is not set")

    try:
        with open("forge-deploy.yml", "r") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError as e:
        raise Exception("The configuration file 'forge-deploy.yml' is missing.") from e
    except yaml.YAMLError as e:
        raise Exception(f"Error parsing YAML file: {e}") from e

    # replace secrets
    secrets_env = os.getenv("SECRETS")
    if secrets_env:
        secrets = dict(
            line.split("=", 1) for line in secrets_env.strip().split("\n") if line
        )
        # convert keys to upper case
        secrets = {key.upper(): value for key, value in secrets.items()}

        try:
            data: dict = replace_secrets_yaml(data, secrets)  # type: ignore
        except Exception as e:
            raise Exception(f"Error replacing secrets: {e}") from e

    # TODO: validate data
    logger.debug("YAML data: %s", data)

    config = {
        "server_name": data["server_name"],
        "github_repository": data["github_repository"],
        "github_branch": data.get("github_branch", "main"),
        "sites": [],
    }
    for site in data.get("sites", []):
        root_dir = site.get("root_dir", ".")
        if root_dir.startswith("/"):
            root_dir = "." + root_dir
        web_dir = site.get("web_dir", "public")
        if web_dir.startswith("/"):
            web_dir = "." + web_dir

        config["sites"].append(
            {
                "site_domain": site["site_domain"],
                "root_dir": root_dir,
                "web_dir": web_dir,
                "project_type": site.get("project_type", "html"),
                "php_version": site.get("php_version", None),
                "deployment_commands": site.get("deployment_commands", []),
                "daemons": site.get("daemons", []),
                "environment": site.get("environment", {}),
                "aliases": site.get("aliases", []),
                "nginx_template": site.get("nginx_template", "default"),
                "nginx_config_variables": site.get("nginx_config_variables", {}),
                "certificate": site.get("certificate", False),
            }
        )

    logger.debug("Config: %s", config)

    headers = {
        "Authorization": f"Bearer {forge_api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(f"{forge_uri}/servers", headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception("Failed to get server from Laravel Forge API") from e

    server_id = next(
        (
            server["id"]
            for server in response.json()["servers"]
            if server["name"] == config["server_name"]
        ),
        None,
    )
    if not server_id:
        raise Exception(f"Server `{config["server_name"]}` not found")

    # sites
    for site_conf in config["sites"]:
        print("\n")
        logger.info(f"\t---- Site: {site_conf['site_domain']} ----")
        try:
            response = requests.get(
                f"{forge_uri}/servers/{server_id}/sites", headers=headers
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception("Failed to get sites from Laravel Forge API") from e
        site = next(
            (
                site
                for site in response.json()["sites"]
                if site["name"] == site_conf["site_domain"]
            ),
            None,
        )

        # create site
        if not site:
            # nginx template
            try:
                response = requests.get(
                    f"{forge_uri}/servers/{server_id}/nginx/templates", headers=headers
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(
                    "Failed to get nginx templates from Laravel Forge API"
                ) from e

            nginx_templates = response.json()["templates"]
            nginx_template_id = next(
                (
                    item["id"]
                    for item in nginx_templates
                    if item["name"] == site_conf["nginx_template"]
                ),
                None,
            )

            # if template isn't added in the server add it from nginx-templates folder
            if not nginx_template_id:
                logger.info("Nginx template not created in the server")
                logger.info("Creating nginx template...")
                if os.path.exists(
                    f"nginx_templates/{site_conf["nginx_template"]}.conf"
                ):
                    with open(
                        f"nginx_templates/{site_conf['nginx_template']}.conf", "r"
                    ) as file:
                        try:
                            response = requests.post(
                                f"{forge_uri}/servers/{server_id}/nginx/templates",
                                headers=headers,
                                json={
                                    "content": file.read(),
                                    "name": site_conf["nginx_template"],
                                },
                            )
                            response.raise_for_status()
                        except requests.RequestException as e:
                            raise Exception(
                                "Failed to create nginx template from Laravel Forge API"
                            ) from e
                        nginx_template_id = response.json()["template"]["id"]
                        logger.info("Nginx template created successfully")
                else:
                    raise Exception("Invalid nginx template name")

            create_site_payload = {
                "domain": site_conf["site_domain"],
                "project_type": site_conf["project_type"],
                "aliases": site_conf["aliases"],
                "directory": str(Path(site_conf["root_dir"]) / site_conf["web_dir"]),
                "isolated": False,
                "nginx_template": nginx_template_id,
            }

            # create site
            logger.info("Creating site...")
            try:
                response = requests.post(
                    f"{forge_uri}/servers/{server_id}/sites",
                    json=create_site_payload,
                    headers=headers,
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception("Failed to create site from Laravel Forge API") from e

            site = response.json()["site"]

            def until_site_installed(site):
                site = requests.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}",
                    headers=headers,
                ).json()["site"]
                return site["status"] == "installed"

            if not wait(lambda: until_site_installed(site)):
                raise Exception("Site creation timed out")

            logger.info("Site created successfully")

            # set site nginx variables
            try:
                response = requests.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx",
                    headers=headers,
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(
                    "Failed to get nginx config from Laravel Forge API"
                ) from e

            try:
                nginx_config = response.content.decode("utf-8")
                nginx_config = replace_nginx_variables(
                    nginx_config, site_conf["nginx_config_variables"]
                )
                response = requests.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx",
                    headers=headers,
                    json={"content": nginx_config},
                )
                response.raise_for_status()
            except Exception as e:
                raise Exception(f"Failed to set nginx config variables: {e}") from e

        else:
            logger.info("Site already exists")

        site_id = site["id"]
        logger.debug(f"Site: %s", site)

        # ---- php version ----

        try:
            res = requests.get(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}", headers=headers
            )
            res.raise_for_status()
            site_php_version = res.json()["site"]["php_version"]
        except Exception as e:
            raise Exception("Failed to get site php version") from e

        if site_conf["php_version"] and site_conf["php_version"] != site_php_version:
            # check if version is installed, if not install it
            res = requests.get(f"{forge_uri}/servers/{server_id}/php", headers=headers)
            res.raise_for_status()
            if site_conf["php_version"] not in [php["version"] for php in res.json()]:
                logger.info("Installing php version...")
                try:
                    response = requests.post(
                        f"{forge_uri}/servers/{server_id}/php",
                        headers=headers,
                        json={"version": site_conf["php_version"]},
                    )
                    response.raise_for_status()

                    # wait for installation
                    def until_php_installed():
                        res = requests.get(
                            f"{forge_uri}/servers/{server_id}/php", headers=headers
                        )
                        res.raise_for_status()
                        installed_php = next(
                            (
                                php
                                for php in res.json()
                                if php["version"] == site_conf["php_version"]
                            ),
                        )
                        return installed_php["status"] == "installed"

                    if not wait(until_php_installed):
                        raise Exception("Php installation timed out")
                except Exception as e:
                    raise Exception(f"Failed to install php version: {e}") from e

                logger.info(f"Php version {site_conf['php_version']} installed")

            # update site php version
            try:
                res = requests.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/php",
                    headers=headers,
                    json={"version": site_conf["php_version"]},
                )
                res.raise_for_status()
            except Exception as e:
                raise Exception(f"Failed to update site php version: {e}") from e
            logger.info(f"Php version set to {site_conf["php_version"]}")

        site_dir = str(
            Path("/home/forge/") / site_conf["site_domain"] / site_conf["root_dir"]
        )

        # add repository
        if site["repository"] != config["github_repository"]:
            logger.info("Adding repository...")
            try:
                response = requests.post(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/git",
                    headers=headers,
                    json={
                        "provider": "github",
                        "repository": config["github_repository"],
                        "branch": config["github_branch"],
                        "composer": False,
                    },
                )
                response.raise_for_status()

                site = response.json()["site"]

                def until_repo_installed():
                    site = requests.get(
                        f"{forge_uri}/servers/{server_id}/sites/{site_id}",
                        headers=headers,
                    ).json()["site"]
                    return site["repository_status"] == "installed"

                if not wait(until_repo_installed):
                    raise Exception("Adding repository timed out")
            except Exception as e:
                raise Exception(f"Failed to add repository: {e}") from e

            logger.info("Repository added successfully")

        # create daemons
        try:
            daemon_ids = []
            # get existing site daemons
            response = requests.get(
                f"{forge_uri}/servers/{server_id}/daemons", headers=headers
            )
            response.raise_for_status()
            # existing site daemons
            site_daemons = [
                daemon
                for daemon in response.json()["daemons"]
                if daemon["directory"] == site_dir
            ]
            # delete daemon if not in the config
            for dm in site_daemons:
                if dm["command"] not in [
                    daemon["command"] for daemon in site_conf["daemons"]
                ]:
                    response = requests.delete(
                        f"{forge_uri}/servers/{server_id}/daemons/{dm['id']}",
                        headers=headers,
                    )
                    response.raise_for_status()
                else:
                    daemon_ids.append(dm["id"])

            # add new daemons
            for daemon in site_conf["daemons"]:
                if daemon["command"] not in [dm["command"] for dm in site_daemons]:
                    response = requests.post(
                        f"{forge_uri}/servers/{server_id}/daemons",
                        headers=headers,
                        json={
                            "command": daemon["command"],
                            "user": "forge",
                            "directory": site_dir,
                            "startsecs": 1,
                        },
                    )
                    response.raise_for_status()
                    daemon_ids.append(response.json()["daemon"]["id"])
        except Exception as e:
            raise Exception(f"Failed to add daemons: {e}") from e

        logger.info("Daemons added successfully")

        # deployment script
        # if deployment_script not provided, the default deployment script generated by forge is kept
        if len(site_conf["deployment_commands"]) > 0:
            deployment_script = (
                f"# generated by deployment script, do not modify\n"
                + f"cd {site_dir}\n"
                + "git pull origin $FORGE_SITE_BRANCH\n"
            )

            for cmd in site_conf["deployment_commands"]:
                deployment_script += f"{cmd}\n"
            for d_id in daemon_ids:
                deployment_script += f"sudo -S supervisorctl restart daemon-{d_id}:*\n"

            try:
                response = requests.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/script",
                    headers=headers,
                    json={
                        "content": deployment_script,
                        # disabled auto_source because it causes a problem when code is not in root directory
                        # because forge creates the env file in the specified directory, but tries to source it from root
                        "auto_source": False,
                    },
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(f"Failed to add deployment script: {e}") from e

            logger.info("Deployment script added successfully")

        # set env
        try:
            env = ""
            for key, value in site_conf["environment"].items():
                env += f'{key}="{value}"\n'
            if len(env) > 0:
                response = requests.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/env",
                    headers=headers,
                    json={
                        "content": env,
                    },
                )
                response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to set environment variables: {e}") from e
        logger.info("Environment variables set successfully")

        # certificate
        if site_conf["certificate"] and not site["is_secured"]:
            try:
                response = requests.post(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/certificates/letsencrypt",
                    headers=headers,
                    json={"domains": [site_conf["site_domain"], *site_conf["aliases"]]},
                )
                response.raise_for_status()

                def until_cert_applied():
                    site = requests.get(
                        f"{forge_uri}/servers/{server_id}/sites/{site_id}",
                        headers=headers,
                    ).json()["site"]
                    return site["is_secured"]

                if not wait(until_cert_applied, max_retries=4):
                    raise Exception("Applying certificate timed out")
            except requests.RequestException as e:
                raise Exception(f"Failed to add certificate: {e}") from e

            logger.info("Certificate added successfully")

        # deploy site
        logger.info("Deploying site...")
        response = requests.post(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/deploy",
            headers=headers,
        )
        response.raise_for_status()
        site = response.json()["site"]

        def until_site_deployed():
            site = requests.get(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}", headers=headers
            ).json()["site"]
            return site["deployment_status"] == None

        if not wait(until_site_deployed):
            raise Exception("Deploying site timed out")

        # get deployment log
        response = requests.get(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/log",
            headers=headers,
        )
        response.raise_for_status()
        dep_log = response.content.decode("utf-8")
        logger.info("Deployment log:\n%s", dep_log)

        # check deployment status
        deployment = requests.get(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment-history",
            headers=headers,
        ).json()["deployments"][0]
        if deployment["status"] == "failed":
            raise Exception("Deployment failed")

        logger.info("Site deployed successfully")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.HTTPError as http_err:
        logger.error("HTTP error occurred: %s", http_err, exc_info=True)
        sys.exit(1)
    except Exception as err:
        logger.error("An error occurred:\n %s", err, exc_info=True)
        sys.exit(1)

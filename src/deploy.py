import logging
import os
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from utils import (
    cat_paths,
    load_config,
    parse_env,
    replace_nginx_variables,
    replace_secrets_yaml,
    validate_yaml_data,
    wait,
)

load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
WORKFLOW_REPO_PATH = os.getenv("GITHUB_WORKSPACE", "./")
DEPLOYMENT_FILE_NAME = os.getenv("DEPLOYMENT_FILE", "forge-deploy.yml")
FORGE_API_TOKEN = os.getenv("FORGE_API_TOKEN")
SECRETS_ENV = os.getenv("SECRETS", None)

logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    action_dir = cat_paths(os.path.dirname(__file__), "../")
    forge_uri = "https://forge.laravel.com/api/v1"
    if FORGE_API_TOKEN is None:
        raise Exception("FORGE_API_TOKEN is not set")

    dep_file = cat_paths(WORKFLOW_REPO_PATH, DEPLOYMENT_FILE_NAME)

    try:
        with open(dep_file, "r") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError as e:
        raise Exception(f"The configuration file {dep_file} is missing.") from e
    except yaml.YAMLError as e:
        raise Exception(f"Error parsing YAML file: {e}") from e

    # replace secrets
    if SECRETS_ENV:
        secrets = parse_env(SECRETS_ENV)

        try:
            data: dict = replace_secrets_yaml(data, secrets)  # type: ignore
        except Exception as e:
            raise Exception(f"Error replacing secrets: {e}") from e

    logger.debug("YAML data: %s", data)

    validate_yaml_data(data)

    config = load_config(data)

    logger.debug("Config: %s", config)

    session = requests.sessions.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {FORGE_API_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )

    try:
        response = session.get(f"{forge_uri}/servers")
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
    try:
        response = session.get(f"{forge_uri}/servers/{server_id}/sites")
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception("Failed to get sites from Laravel Forge API") from e
    sites = response.json()["sites"]
    for site_conf in config["sites"]:
        print("\n")
        logger.info(f"\t---- Site: {site_conf['site_domain']} ----")

        site = next(
            (site for site in sites if site["name"] == site_conf["site_domain"]),
            None,
        )

        # create site
        if not site:
            # nginx template
            try:
                response = session.get(
                    f"{forge_uri}/servers/{server_id}/nginx/templates"
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
            nginx_templates_dir = cat_paths(action_dir, "nginx_templates/")
            if not nginx_template_id:
                logger.info("Nginx template not created in the server")
                logger.info("Creating nginx template...")
                if os.path.exists(
                    cat_paths(
                        nginx_templates_dir, f"{site_conf["nginx_template"]}.conf"
                    )
                ):
                    with open(
                        cat_paths(
                            nginx_templates_dir, f"{site_conf["nginx_template"]}.conf"
                        ),
                        "r",
                    ) as file:
                        try:
                            response = session.post(
                                f"{forge_uri}/servers/{server_id}/nginx/templates",
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
            # else update the template if it changed
            else:
                response = session.get(
                    f"{forge_uri}/servers/{server_id}/nginx/templates/{nginx_template_id}"
                )
                response.raise_for_status()
                server_template = response.json()["template"]["content"]
                if os.path.exists(
                    cat_paths(
                        nginx_templates_dir, f"{site_conf["nginx_template"]}.conf"
                    )
                ):
                    with open(
                        cat_paths(
                            nginx_templates_dir, f"{site_conf["nginx_template"]}.conf"
                        ),
                        "r",
                    ) as file:
                        local_template = file.read()

                    if server_template != local_template:
                        try:
                            response = session.put(
                                f"{forge_uri}/servers/{server_id}/nginx/templates/{nginx_template_id}",
                                json={"content": local_template},
                            )
                            response.raise_for_status()
                            logger.info("Nginx template updated successfully")
                        except requests.RequestException as e:
                            raise Exception(
                                "Failed to update nginx template from Laravel Forge API"
                            ) from e

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
                response = session.post(
                    f"{forge_uri}/servers/{server_id}/sites",
                    json=create_site_payload,
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception("Failed to create site from Laravel Forge API") from e

            site = response.json()["site"]

            def until_site_installed(site):
                site = session.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}"
                ).json()["site"]
                return site["status"] == "installed"

            if not wait(lambda: until_site_installed(site)):
                raise Exception("Site creation timed out")

            logger.info("Site created successfully")

            # set site nginx variables
            try:
                response = session.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx"
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
                response = session.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx",
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
            res = session.get(f"{forge_uri}/servers/{server_id}/sites/{site_id}")
            res.raise_for_status()
            site_php_version = res.json()["site"]["php_version"]
        except Exception as e:
            raise Exception("Failed to get site php version") from e

        if site_conf["php_version"] and site_conf["php_version"] != site_php_version:
            # check if version is installed, if not install it
            res = session.get(f"{forge_uri}/servers/{server_id}/php")
            res.raise_for_status()
            if site_conf["php_version"] not in [php["version"] for php in res.json()]:
                logger.info("Installing php version...")
                try:
                    response = session.post(
                        f"{forge_uri}/servers/{server_id}/php",
                        json={"version": site_conf["php_version"]},
                    )
                    response.raise_for_status()

                    # wait for installation
                    def until_php_installed():
                        res = session.get(f"{forge_uri}/servers/{server_id}/php")
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
                res = session.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/php",
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
        if (
            site_conf["clone_repository"]
            and site["repository"] != config["github_repository"]
        ):
            logger.info("Adding repository...")
            try:
                response = session.post(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/git",
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
                    site = session.get(
                        f"{forge_uri}/servers/{server_id}/sites/{site_id}",
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
            response = session.get(f"{forge_uri}/servers/{server_id}/daemons")
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
                    response = session.delete(
                        f"{forge_uri}/servers/{server_id}/daemons/{dm['id']}"
                    )
                    response.raise_for_status()
                    logger.info(f"Daemon-{dm["id"]} `{dm["command"]}` deleted.")
                else:
                    daemon_ids.append(dm["id"])

            # add new daemons
            for daemon in site_conf["daemons"]:
                if daemon["command"] not in [dm["command"] for dm in site_daemons]:
                    response = session.post(
                        f"{forge_uri}/servers/{server_id}/daemons",
                        json={
                            "command": daemon["command"],
                            "user": "forge",
                            "directory": site_dir,
                            "startsecs": 1,
                        },
                    )
                    response.raise_for_status()
                    new_daemon = response.json()["daemon"]
                    daemon_ids.append(new_daemon["id"])
                    logger.info(
                        f"Daemon-{new_daemon["id"]} `{new_daemon["command"]}` created."
                    )
        except Exception as e:
            raise Exception(f"Failed to add daemons: {e}") from e

        # deployment script
        # if deployment_script not provided, the default deployment script generated by forge is kept
        if site_conf["deployment_commands"]:
            deployment_script = (
                f"# generated by deployment script, do not modify\n"
                + f"cd {site_dir}\n"
                + "git pull origin $FORGE_SITE_BRANCH\n"
            )

            deployment_script += site_conf["deployment_commands"] + "\n"
            for d_id in daemon_ids:
                deployment_script += f"sudo -S supervisorctl restart daemon-{d_id}:*\n"

            try:
                response = session.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/script",
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
            site_env = {}
            # read env file
            if site_conf["env_file"]:
                env_file_path = cat_paths(WORKFLOW_REPO_PATH, site_conf["env_file"])
                try:
                    with open(env_file_path, "r") as file:
                        logger.info(
                            "Loading environment variables from file `%s`",
                            site_conf["env_file"],
                        )
                        file_env = parse_env(file.read())
                        logger.debug("Env variables loaded from file:\n%s", file_env)
                        site_env.update(file_env)
                except FileNotFoundError as e:
                    raise Exception(
                        f"Environment file `{site_conf['env_file']}` not found"
                    ) from e

            if site_conf["environment"]:
                config_env = parse_env(site_conf["environment"])
                logger.debug("Env variables loaded from config:\n%s", config_env)
                site_env.update(config_env)

            env_str = "\n".join([f"{k}={v}" for k, v in site_env.items()])
            if len(env_str) > 0:
                response = session.put(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/env",
                    json={
                        "content": env_str,
                    },
                )
                response.raise_for_status()
                logger.info("Environment variables set successfully")

        except Exception as e:
            raise Exception(f"Failed to set environment variables: {e}") from e

        # certificate
        if site_conf["certificate"] and not site["is_secured"]:
            try:
                logger.info("Adding certificate...")
                response = session.post(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/certificates/letsencrypt",
                    json={"domains": [site_conf["site_domain"], *site_conf["aliases"]]},
                )
                response.raise_for_status()

                def until_cert_applied():
                    site = session.get(
                        f"{forge_uri}/servers/{server_id}/sites/{site_id}"
                    ).json()["site"]
                    return site["is_secured"]

                if not wait(until_cert_applied):
                    raise Exception("Applying certificate timed out")
            except requests.RequestException as e:
                raise Exception(f"Failed to add certificate: {e}") from e

            logger.info("Certificate added successfully")

        # deploy site
        if site_conf["clone_repository"]:
            logger.info("Deploying site...")
            response = session.post(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/deploy"
            )
            response.raise_for_status()
            site = response.json()["site"]

            def until_site_deployed():
                site = session.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}"
                ).json()["site"]
                return site["deployment_status"] == None

            if not wait(until_site_deployed, max_retries=-1):
                raise Exception("Deploying site timed out")

            # get deployment log
            try:
                response = session.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/log",
                )
                response.raise_for_status()
                dep_log = response.content.decode("utf-8")
                logger.info("Deployment log:\n%s", dep_log)
            except requests.exceptions.HTTPError as e:
                if response.status_code != 404:
                    raise Exception("Failed to get deployment log") from e

            # check deployment status
            deployment = session.get(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment-history",
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

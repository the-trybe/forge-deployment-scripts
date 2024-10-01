import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from utils import replace_secrets_yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


def deploy_site():
    forge_uri = "https://forge.laravel.com/api/v1"
    forge_api_token = os.getenv("FORGE_API_TOKEN")
    if forge_api_token is None:
        raise Exception("FORGE_API_TOKEN is not set")

    with open("forge-deploy.yml", "r") as file:
        data = yaml.safe_load(file)

        # replace secrets
        secrets_env = os.getenv("SECRETS")
        if secrets_env:
            secrets = dict(
                line.split("=", 1) for line in secrets_env.strip().split("\n") if line
            )
            # convert keys to upper case
            secrets = {key.upper(): value for key, value in secrets.items()}

            data: dict = replace_secrets_yaml(data, secrets)  # type: ignore

        # TODO: validate data
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

            config["sites"].append(
                {
                    "site_domain": site["site_domain"],
                    "root_dir": root_dir,
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

    headers = {
        "Authorization": f"Bearer {forge_api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    response = requests.get(f"{forge_uri}/servers", headers=headers)
    response.raise_for_status()
    server_id = next(
        (
            server["id"]
            for server in response.json()["servers"]
            if server["name"] == config["server_name"]
        ),
        None,
    )
    if not server_id:
        raise Exception("Server not found")

    # sites
    for site_conf in config["sites"]:
        logger.info(f"\n---- Site: {site_conf['site_domain']} ----\n")
        response = requests.get(
            f"{forge_uri}/servers/{server_id}/sites", headers=headers
        )
        response.raise_for_status()
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
            response = requests.get(
                f"{forge_uri}/servers/{server_id}/nginx/templates", headers=headers
            )
            response.raise_for_status()
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
                if os.path.exists(
                    f"nginx_templates/{site_conf["nginx_template"]}.conf"
                ):
                    with open(
                        f"nginx_templates/{site_conf['nginx_template']}.conf", "r"
                    ) as file:
                        response = requests.post(
                            f"{forge_uri}/servers/{server_id}/nginx/templates",
                            headers=headers,
                            json={
                                "content": file.read(),
                                "name": site_conf["nginx_template"],
                            },
                        )
                        response.raise_for_status()
                        nginx_template_id = response.json()["template"]["id"]
                else:
                    raise Exception("Invalid nginx template name")

            create_site_payload = {
                "domain": site_conf["site_domain"],
                "project_type": site_conf["project_type"],
                "aliases": site_conf["aliases"],
                "isolated": False,
                "nginx_template": nginx_template_id,
            }

            # create site
            logger.info("Creating site...")
            response = requests.post(
                f"{forge_uri}/servers/{server_id}/sites",
                json=create_site_payload,
                headers=headers,
            )
            response.raise_for_status()
            site = response.json()["site"]

            while site["status"] != "installed":
                time.sleep(1)
                site = requests.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site['id']}",
                    headers=headers,
                ).json()["site"]

            logger.info("Site created successfully")

            # set nginx site variables
            response = requests.get(
                f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx",
                headers=headers,
            )
            response.raise_for_status()
            nginx_config = response.content.decode("utf-8")

            pattern = re.compile(r"{{(.*?)}}")

            def replace_match(match):
                var_name = match.group(1).strip()
                return str(
                    site_conf["nginx_config_variables"].get(
                        var_name, f"{{{{{var_name}}}}}"
                    )
                )

            nginx_config = pattern.sub(replace_match, nginx_config)
            response = requests.put(
                f"{forge_uri}/servers/{server_id}/sites/{site["id"]}/nginx",
                headers=headers,
                json={"content": nginx_config},
            )
            response.raise_for_status()
        else:
            logger.info("Site already exists")

        site_id = site["id"]

        # ---- php version ----

        res = requests.get(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}", headers=headers
        )
        res.raise_for_status()
        site_php_version = res.json()["site"]["php_version"]

        if site_conf["php_version"] and site_conf["php_version"] != site_php_version:
            # check if version is installed, if no install it
            res = requests.get(f"{forge_uri}/servers/{server_id}/php", headers=headers)
            res.raise_for_status()
            if site_conf["php_version"] not in [php["version"] for php in res.json()]:
                logger.info("installing php version...")
                response = requests.post(
                    f"{forge_uri}/servers/{server_id}/php",
                    headers=headers,
                    json={"version": site_conf["php_version"]},
                )
                response.raise_for_status()

                # TODO: implement max retries for all waits
                # wait for installation
                while True:
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
                    if installed_php["status"] == "installed":
                        break
                    time.sleep(2)
                logger.info(f"Php version {site_conf['php_version']} installed")

            # update site php version
            res = requests.put(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/php",
                headers=headers,
                json={"version": site_conf["php_version"]},
            )
            res.raise_for_status()
            logger.info(f"Php version set to {site_conf["php_version"]}")

        site_dir = str(
            Path("/home/forge/") / site_conf["site_domain"] / site_conf["root_dir"]
        )

        # add repository
        if site["repository"] != config["github_repository"]:
            logger.info("adding repository...")
            response = requests.post(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/git",
                headers=headers,
                json={
                    "provider": "github",
                    "repository": config["github_repository"],
                    "branch": config["github_branch"],
                    "composer": True if site_conf["project_type"] == "php" else False,
                },
            )
            response.raise_for_status()
            site = response.json()["site"]

            while site["repository_status"] != "installed":
                time.sleep(2)
                site = requests.get(
                    f"{forge_uri}/servers/{server_id}/sites/{site_id}", headers=headers
                ).json()["site"]

            logger.info("Repository added successfully")

        # create daemons
        daemon_ids = []
        # get existing site daemons, delete, keep, add new
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
        # delete site daemons not in the config
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

        logger.info("Daemons added successfully")

        # deployment script
        # if deployment_script not provided, the default deployment script generated by forge is kept
        if len(site_conf["deployment_commands"]) > 0:
            deployment_script = (
                f"# generated by deployment script, don't modify\n"
                + f"cd {site_dir}\n"
                + "git pull origin $FORGE_SITE_BRANCH\n"
            )

            for cmd in site_conf["deployment_commands"]:
                deployment_script += f"{cmd}\n"
            for d_id in daemon_ids:
                deployment_script += f"sudo -S supervisorctl restart daemon-{d_id}:*\n"

            response = requests.put(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/script",
                headers=headers,
                json={
                    "content": deployment_script,
                    "auto_source": True if len(site_conf["environment"]) > 0 else False,
                },  # to make .env available for the build
            )
            response.raise_for_status()

        # set env
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

        # certificate
        if site_conf["certificate"] and not site["is_secured"]:
            response = requests.post(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}/certificates/letsencrypt",
                headers=headers,
                json={"domains": [site_conf["site_domain"], *site_conf["aliases"]]},
            )
            response.raise_for_status()
            logger.info("Certificate added successfully")
            # TODO: check if cert is applied (check is_secured)

        # deploy site
        logger.info("Deploying site...")
        response = requests.post(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment/deploy",
            headers=headers,
        )
        response.raise_for_status()
        site = response.json()["site"]

        while site["deployment_status"] != None:
            time.sleep(2)
            site = requests.get(
                f"{forge_uri}/servers/{server_id}/sites/{site_id}", headers=headers
            ).json()["site"]

        deployment = requests.get(
            f"{forge_uri}/servers/{server_id}/sites/{site_id}/deployment-history",
            headers=headers,
        ).json()["deployments"][0]
        if deployment["status"] == "failed":
            raise Exception("Deployment failed")
        logger.info("Site deployed successfully")


if __name__ == "__main__":
    try:
        deploy_site()
    except requests.exceptions.HTTPError as http_err:
        logger.error("HTTP error occurred: %s", http_err, exc_info=True)
        sys.exit(1)
    except Exception as err:
        logger.error("An error occurred: %s", err, exc_info=True)
        sys.exit(1)

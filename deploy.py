import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

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
                    "run_command": site.get("run_command", None),
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

    for site_conf in config["sites"]:
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

        site_id = site["id"]

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

        # create daemon
        daemon_id = None
        if site_conf["run_command"]:
            response = requests.get(
                f"{forge_uri}/servers/{server_id}/daemons", headers=headers
            )
            response.raise_for_status()
            daemon_id = next(
                (
                    daemon["id"]
                    for daemon in response.json()["daemons"]
                    if daemon["command"] == site_conf["run_command"]
                    and daemon["directory"] == site_dir
                ),
                None,
            )
            if not daemon_id:
                response = requests.post(
                    f"{forge_uri}/servers/{server_id}/daemons",
                    headers=headers,
                    json={
                        "command": site_conf["run_command"],
                        "user": "forge",
                        "directory": site_dir,
                        "startsecs": 1,
                    },
                )
                response.raise_for_status()
                daemon_id = response.json()["daemon"]["id"]

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
            if daemon_id:
                deployment_script += (
                    f"sudo -S supervisorctl restart daemon-{daemon_id}:*\n"
                )

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
        logger.error(f"An error occurred: %s", err, exc_info=True)
        sys.exit(1)

import os
import sys
import subprocess
from pathlib import Path

import pytest
import requests
import yaml
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from utils import cat_paths, parse_env

load_dotenv(".env.test")


# Forge API constants
FORGE_API_URL = "https://forge.laravel.com/api/v1"
FORGE_API_TOKEN = os.getenv("FORGE_API_TOKEN")
WORKFLOW_REPO_PATH = os.path.dirname(__file__)
DEPLOYMENT_FILE = "forge-deploy.test.yml"

# Test server name
test_server_name = "devops-tst"

# HTTP headers for authentication
headers = {
    "Authorization": f"Bearer {FORGE_API_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def get_server_id():
    response = requests.get(f"{FORGE_API_URL}/servers", headers=headers)
    response.raise_for_status()
    servers = response.json()["servers"]
    server = next(
        (server for server in servers if server["name"] == test_server_name), None
    )
    assert server is not None, f"Server '{test_server_name}' not found"
    return server["id"]


def load_deployment_config():
    dep_file = cat_paths(WORKFLOW_REPO_PATH, DEPLOYMENT_FILE)
    with open(dep_file, "r") as file:
        return yaml.safe_load(file)


def get_site(server_id, domain):
    response = requests.get(
        f"{FORGE_API_URL}/servers/{server_id}/sites", headers=headers
    )
    response.raise_for_status()
    sites = response.json()["sites"]
    return next((site for site in sites if site["name"] == domain), None)


def validate_site_configuration(server_id, site_config):
    site = get_site(server_id, site_config["site_domain"])
    assert (
        site is not None
    ), f"Site '{site_config['site_domain']}' not found on server '{test_server_name}'"

    # Validate PHP version
    if site_config.get("php_version"):
        assert site["php_version"] == site_config["php_version"], (
            f"PHP version mismatch for site '{site_config['site_domain']}'. "
            f"Expected: {site_config['php_version']}, Found: {site['php_version']}"
        )

    # Validate environment variables
    response = requests.get(
        f"{FORGE_API_URL}/servers/{server_id}/sites/{site['id']}/env", headers=headers
    )
    response.raise_for_status()
    env_content = response.content.decode("utf-8")
    expected_env = {}
    expected_env_str = ""
    if site_config.get("env_file"):
        env_file_path = cat_paths(WORKFLOW_REPO_PATH, site_config["env_file"])
        with open(env_file_path, "r") as file:
            file_env = parse_env(file.read())
            expected_env.update(file_env)
    expected_env.update(parse_env(site_config.get("environment", "")))
    expected_env_str += "\n".join([f"{k}={v}" for k, v in expected_env.items()])

    assert (
        expected_env_str == env_content
    ), f"Environment variable mismatch for site {site_config['site_domain']}."

    # Validate deployment script
    response = requests.get(
        f"{FORGE_API_URL}/servers/{server_id}/sites/{site['id']}/deployment/script",
        headers=headers,
    )
    response.raise_for_status()
    deployment_script = response.content.decode("utf-8")
    expected_commands = site_config.get("deployment_commands", "")
    assert (
        expected_commands in deployment_script
    ), f"Deployment script for site '{site_config['site_domain']}' does not match expected commands."

    # Validate daemons
    response = requests.get(
        f"{FORGE_API_URL}/servers/{server_id}/daemons", headers=headers
    )
    response.raise_for_status()
    daemons = response.json()["daemons"]
    site_dir = str(
        Path("/home/forge/") / site_config["site_domain"] / site_config["root_dir"]
    )
    site_daemons = [daemon for daemon in daemons if daemon["directory"] == site_dir]
    configured_daemons = [
        daemon["command"] for daemon in site_config.get("daemons", [])
    ]
    for daemon in site_daemons:
        assert (
            daemon["command"] in configured_daemons
        ), f"Daemon '{daemon['command']}' is missing or not properly configured for site '{site_config['site_domain']}'."


def run_deployment_script():
    subprocess.run(
        [sys.executable, "src/deploy.py"],
        check=True,
        env={  # type: ignore
            "GITHUB_WORKSPACE": WORKFLOW_REPO_PATH,
            "DEPLOYMENT_FILE": DEPLOYMENT_FILE,
            "FORGE_API_TOKEN": FORGE_API_TOKEN,
        },
    )


@pytest.fixture(scope="module")
def server_id():
    return get_server_id()


@pytest.fixture(scope="module")
def deployment_config():
    return load_deployment_config()


def test_deployment(server_id, deployment_config):
    # Run the deployment script
    run_deployment_script()

    # Validate the deployment
    for site_config in deployment_config.get("sites", []):
        validate_site_configuration(server_id, site_config)


if __name__ == "__main__":
    pytest.main()

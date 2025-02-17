import re
import time
from pathlib import Path

from cerberus import Validator

from schema import schema


def validate_yaml_data(data):
    v = Validator(schema, purge_unknown=False)  # type: ignore
    v.allow_default_values = True  # type: ignore
    if not v.validate(data, normalize=True):  # type: ignore
        raise Exception(f"YAML data validation failed: {v.errors}")  # type: ignore
    return v.document  # type: ignore


def replace_secrets_yaml(data, secrets):
    if isinstance(data, dict):
        return {
            key: replace_secrets_yaml(value, secrets) for key, value in data.items()
        }
    elif isinstance(data, list):
        return [replace_secrets_yaml(item, secrets) for item in data]
    elif isinstance(data, str):
        # regex matches all occurrences of secrets in the form ${{ secrets.SECRET_VAR }}
        pattern = re.compile(r"\$\{\{\s*secrets\.(\w+)\s*\}\}")

        def replace_match(match):
            secret_name = match.group(1).upper()
            if secret_name not in secrets:
                raise ValueError(f"Secret '{secret_name}' value is not set.")
            return secrets[secret_name]

        return pattern.sub(replace_match, data)
    else:
        return data


def replace_nginx_variables(nginx_conf, variables):
    pattern = re.compile(r"{{(.*?)}}")

    def replace_match(match):
        var_name = match.group(1).strip()

        try:
            var_value = variables[var_name]
        except KeyError:
            raise ValueError(f"Variable '{var_name}' value is not set.")

        return str(var_value)

    return pattern.sub(replace_match, nginx_conf)


def wait(callback, max_retries=8):
    retries = 0
    timeout = 0.5
    max_timeout = 30
    # max_retries < 0 means infinite retries
    while max_retries < 0 or retries <= max_retries:
        if callback():
            return True
        time.sleep(timeout)
        retries += 1
        timeout = min(timeout * 2, max_timeout)
    return False


def parse_env(env: str | None) -> dict:
    if not env:
        return {}
    parsed_env = {}
    for line in env.strip().split("\n"):
        if line:
            try:
                key, value = line.split("=", 1)
                parsed_env[key.strip().upper()] = value.strip()
            except ValueError:
                print(
                    f"Error: Could not parse line: '{line}'. Make sure each line has a key and a value separated by '='."
                )
    return parsed_env


def cat_paths(*paths):
    return str(Path(*paths))


def ensure_relative_path(path: str | None):
    if path and path.startswith("/"):
        return "." + path
    return path


def load_config(yaml_data):
    # TODO: remove default values, as they are set by the validate_yaml_data function
    config = {
        "server_name": yaml_data["server_name"],
        "github_repository": yaml_data["github_repository"],
        "github_branch": yaml_data.get("github_branch", "main"),
        "sites": [],
    }
    for site in yaml_data.get("sites", []):

        config["sites"].append(
            {
                "site_domain": site["site_domain"],
                "root_dir": ensure_relative_path(site.get("root_dir", ".")),
                "web_dir": ensure_relative_path(site.get("web_dir", "public")),
                "project_type": site.get("project_type", "html"),
                "php_version": site.get("php_version"),
                "deployment_commands": site.get("deployment_commands"),
                "daemons": site.get("daemons", []),
                "laravel_scheduler": site.get("laravel_scheduler"),
                "environment": site.get("environment"),
                "env_file": ensure_relative_path(site.get("env_file")),
                "aliases": site.get("aliases", []),
                "nginx_template": site.get("nginx_template", "default"),
                "nginx_template_variables": site.get("nginx_template_variables", {}),
                "nginx_custom_config": ensure_relative_path(
                    site.get("nginx_custom_config")
                ),
                "certificate": site.get("certificate", False),
                "clone_repository": site.get("clone_repository", True),
            }
        )
    return config


def get_domains_certificate(certificates, domains) -> dict | None:
    """Get the certificate for the given domains from the list of certificates."""
    for cert in certificates:
        cert_domains = cert["domain"].split(",")
        if set(cert_domains) == set(domains):
            return cert
    return None

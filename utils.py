import re
import time

from cerberus import Validator


def validate_yaml_data(data):
    schema = {
        "server_name": {"type": "string", "required": True},
        "github_repository": {"type": "string", "required": True},
        "github_branch": {"type": "string", "required": False, "default": "main"},
        "sites": {
            "type": "list",
            "schema": {
                "type": "dict",
                "schema": {
                    "site_domain": {"type": "string", "required": True},
                    "root_dir": {"type": "string", "required": False, "default": "."},
                    "web_dir": {
                        "type": "string",
                        "required": False,
                        "default": "public",
                    },
                    "project_type": {
                        "type": "string",
                        "required": False,
                        "default": "html",
                    },
                    "php_version": {"type": "string", "required": False},
                    "deployment_commands": {
                        "type": "string",
                        "required": False,
                    },
                    "daemons": {"type": "list", "required": False, "default": []},
                    "environment": {"type": "dict", "required": False, "default": {}},
                    "aliases": {"type": "list", "required": False, "default": []},
                    "nginx_template": {
                        "type": "string",
                        "required": False,
                        "default": "default",
                    },
                    "nginx_config_variables": {
                        "type": "dict",
                        "required": False,
                        "default": {},
                    },
                    "certificate": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                    },
                },
            },
            "required": False,
            "default": [],
        },
    }

    v = Validator(schema)  # type: ignore
    if not v.validate(data):  # type: ignore
        raise Exception(f"YAML data validation failed: {v.errors}")  # type: ignore


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
    while retries <= max_retries:
        if callback():
            return True
        time.sleep(timeout)
        retries += 1
        timeout *= 2
    return False

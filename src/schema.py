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
                "environment": {"type": "string", "required": False},
                "env_file": {"type": "string", "required": False},
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
                "nginx_custom_config": {
                    "type": "string",
                    "required": False,
                },
                "certificate": {
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "clone_repository": {
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
        },
        "required": False,
        "default": [],
    },
}

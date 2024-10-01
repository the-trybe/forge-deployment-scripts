import re


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
            secret_name = match.group(1)
            if secret_name not in secrets:
                raise ValueError(f"Secret '{secret_name}' value is not set.")
            return secrets[secret_name]

        return pattern.sub(replace_match, data)
    else:
        return data

# Deploy to Laravel Forge GitHub Action

This GitHub Action simplifies site creation, configuration, and deployment using a YAML configuration file.

## Key Features

- **Version-Controlled Site Configurations:** Manage and track your site configurations in a YAML file within your repository. This ensures that your sites configuration is versioned along with your application code, providing consistency across environments.
- **Automated Deployment:** Deploy multiple sites to Laravel Forge automatically using github actions.
- **Customizable Configurations:** Configure all aspects of your Laravel Forge sites, such as environment variables, deployment script, Nginx configurations, PHP versions, daemons, and SSL certificates, directly from the YAML file.
- **Secret Management:** Securely manage environment variables and secrets via GitHub Secrets or external secret management tools like 1Password. Secrets are easily replaced within the YAML configuration for safe deployment.

## Inputs

- `forge_api_token` (required): Laravel Forge API Token.
- `deployment_file` (optional): The deployment configuration file (default: `forge-deploy.yml`).
- `debug` (optional): Enable debug mode in logs (default: `false`).
- `secrets` (optional): Secrets to replace in the `forge-deploy.yml` file. The value should be a multi-line string with the format `VAR_NAME=VALUE`.

## Usage

To use this action, create a workflow file (e.g., `.github/workflows/deploy.yml`) in your repository with the following content:

```yaml
name: Deploy to Laravel Forge

on:
  push:
    branches:
      - main # Adjust to the branch that should trigger the deployment

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout the repository # required
        uses: actions/checkout@v4

      - name: Deploy to Laravel Forge
        uses: the-trybe/forge-deployment-scripts@v1
        with:
          forge_api_token: ${{ secrets.FORGE_API_TOKEN }}
          deployment_file: forge-deploy.yml # [Optional] The deployment configuration file (default: forge-deploy.yml).
          debug: false # [Optional] Enable debug mode in logs (default: false).
          secrets:
            | # [Optional] Secrets to replace in the forge-deploy.yml file. EX:
            DB_PASSWORD=${{ secrets.DB_PASSWORD }}
            DB_USER=${{ secrets.DB_USER }}
```

your repository should have a `forge-deploy.yml` file in the root of the repo.

```yaml
# forge-deploy.yml schema

# Server configuration
server_name: "my-server" # [Required] The name of your Laravel Forge server.
github_repository: "user/my-repo" # [Required] The GitHub repository for your site (format: user/repo).
github_branch: "main" # [Optional] The branch to deploy (default: "main").

# Sites Configuration - list of sites to configure and deploy
sites:
  - site_domain: "mywebsite.com" # [Required] The primary domain for the site.
    github_branch: "another-branch" #[Optional] site level branch config, if not set global branch is used.
    root_dir: "/client" # [Optional] The root directory relative to the repo root (default: "/").
    web_dir: "/public" # [Optional] The web directory (default: "/public").
    project_type: "php" # [Optional] The type of the project ("php" for Laravel projects, for other types don't include).
    php_version: "php81" # [Optional] PHP version to use (if not installed in the server, it will be installed).
    deployment_commands:
      | # [Optional] deployment commands to execute during deployment (if not included forge default will be used).
      composer install --no-interaction --prefer-dist --optimize-autoloader
      php artisan migrate --force
    env_file: ".env" # [Optional] The environment file to use (relative to the root of the repository)
    environment:
      | # [Optional] Environment variables, if both env_file and environment are provided, both will be used (environment will have precedence).
      APP_ENV="production"
      DB_CONNECTION="mysql"
      DB_HOST="127.0.0.1"
      DB_PORT=3306
      DB_DATABASE="mywebsite_db"
      DB_USERNAME=${{secrets.DB_USER}} # replacing secrets only works in the yaml file and not in external env files.
      DB_PASSWORD=${{secrets.DB_PASSWORD}}
    aliases: # [Optional] Additional domain aliases.
      - "www.mywebsite.com"
    nginx_template: "default" # [Optional] Nginx template to use from `nignx_templates` folder (default: "default").
    nginx_template_variables: # [Optional] Variables to replace in the Nginx template.
      PROXY_PASS_PORT: 8080
    nginx_custom_config: "path/to/nginx.conf" # [Optional] Custom Nginx config file relative to the repository root.
    certificate: true # [Optional] Boolean to enable or disable SSL certificate for this domain (default: false).
    clone_repository: true # [Optional] Boolean to clone the repository (default: true).
    laravel_scheduler: true # [Optional] Boolean to enable Laravel scheduler (default: false).
    daemons: # [Optional] List of daemons or processes to run in the background.
      - command: "php artisan queue:work"
      - command: "php artisan schedule:run"

  - site_domain: "myotherwebsite.com"
    root_dir: "/public_html" # Specify a different root directory.
    deployment_commands: |
      npm install
      npm run build
    environment: | # Example of a different environment configuration.
      API_URL="https://api.myotherwebsite.com"
      FEATURE_FLAG="enabled"
    nginx_template: "custom_template" # Custom Nginx template from the nginx_templates folder.
    nginx_template_variables:
      UPSTREAM_SERVER: "127.0.0.1"
      UPSTREAM_PORT: 8081
    certificate: false # SSL certificate disabled for this site.
    daemons: # Custom daemons for this site.
      - command: "node server.js"

  - site_domain: "api.mywebsite.com" # Example of an API-specific site.
    deployment_commands: |
      npm ci
      npm run build
    environment: |
      NODE_ENV="production"
      API_KEY="12345"
      DB_CONNECTION="postgres"
      DB_HOST="localhost"
      DB_PORT=5432
      DB_USER="api_user"
      DB_PASSWORD="apipassword"
    nginx_template: "reverse-proxy"
    nginx_template_variables:
      PROXY_PASS_PORT: 3000
    certificate: true
    daemons:
      - command: "pm2 start dist/server.js --name api-server"
```

Additional Configuration Options and Customization:

1. `root_dir` field: Specify the root directory relative to the repository root for each site.

2. `project_type` field: set to "php" if the project is a Laravel project, otherwise, don't include this field.

3. `php_version` field: Specify the PHP version to use (e.g., "php81", "php82"), if the version is not installed on the server it will get installed.

4. `deployment_commands` field: Commands to run during the deployment process. Useful for setting up the environment, building assets, or running migrations.

5. `environment` field: Environment variables specific to each site.

6. `nginx_template` field: Specify a custom Nginx template for each site (see the `nginx_templates` folder). you can add additional templates by creating a file in the `nginx_templates` folder.

7. `nginx_template_variables` field: Variables to replace in the Nginx template. variables should be in the template file as `{{ VARIABLE_NAME }}`, avoid using forge [reserved variables](https://forge.laravel.com/docs/servers/nginx-templates.html#template-variables).

8. `daemons` field: List of processes to run as daemons (e.g., queue workers, Node.js servers).

9. You can add multiple sites in the `sites` array, each with its own configuration. Each site will be configured separately on the Laravel Forge server.

10. You can add secrets to the `forge-deploy.yml` file in the form `${{ secrets.SECRET_VAR }}`. These secrets will be replaced by the values provided in the `secrets` input of the GitHub Action.

## Additional Examples

### Load secrets using One Password

```yaml
name: Deploy to Laravel Forge

on:
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout the repository
        uses: actions/checkout@v4

      - name: Load secret
        uses: 1password/load-secrets-action@v2
        with:
          export-env: true
        env:
          OP_SERVICE_ACCOUNT_TOKEN: ${{ secrets.OP_SERVICE_ACCOUNT_TOKEN }}
          DB_USER: op://vault-name/db/user
          DB_PASSWORD: op://vault-name/db/password

      - name: Deploy to Laravel Forge
        uses: the-trybe/forge-deployment-scripts@main
        with:
          forge_api_token: ${{ secrets.FORGE_API_TOKEN }}
          # in secrets use 'env.' instead of 'secrets.'
          secrets: |
            DB_USER=${{ env.DB_USER }}
            DB_PASSWORD=${{ env.DB_PASSWORD }}
```

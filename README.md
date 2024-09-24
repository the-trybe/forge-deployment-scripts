# Deploy to Laravel Forge GitHub Action

This GitHub Action deploys your site using the Laravel Forge API. It reads the deployment configuration from a `forge-deploy.yml` file, installs necessary dependencies, and executes the deployment script.

## Inputs

- `forge_api_token` (required): Laravel Forge API Token.
- `deploy_config` (required): Base64-encoded content of `forge-deploy.yml`.

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
      - name: Checkout the repository
        uses: actions/checkout@v4

      - name: Read forge-deploy.yml content
        id: read_forge_deploy
        run: |
          deploy_config=$(cat forge-deploy.yml | base64 | tr -d '\n')
          echo "deploy_config=$deploy_config" >> "$GITHUB_OUTPUT"
        shell: bash
        continue-on-error: false

      - name: Deploy to Laravel Forge
        uses: the-trybe/forge-deployment-scripts@main
        with:
          forge_api_token: ${{ secrets.FORGE_API_TOKEN }}
          deploy_config: ${{ steps.read_forge_deploy.outputs.deploy_config }}
```

your repository should have a `forge-deploy.yml` file in the root of the repo.

```yaml
# forge-deploy.yml schema

server_name: "your-server-name" # [Required] The name of your Laravel Forge server
site_domain: "your-site-domain.com" # [Required] The domain of your site
github_repository: "user/repo" # [Required] The GitHub repository URL for your site
github_branch: "main" # [Optional] The branch to deploy (default: "main")
project_type: "php" # [Optional] The type of the project (use "php" for laravel projects, otherwise don't include)
php_version: "php83" # [Optional] PHP version to use (the version should be already installed in your server)
build_commands: # [Optional] List of build commands to run during deployment
  - npm install
  - npm run build
run_command: "npm run start" # [Optional] Command to run a process like a daemon
environment: # [Optional] Environment variables for the site
  APP_ENV: "production"
  DB_HOST: "localhost"
  DB_USER: "forge"
  DB_PASSWORD: "yourpassword"
aliases: # [Optional] Additional domain aliases
  - "www.your-site-domain.com"
nginx_template: "default" # [Optional] Nginx template to use (default: "default") -- see nginx_templates folder
nginx_config_variables: # [Optional] variables to replace in the Nginx template
  PROXY_PASS_PORT: 3000
```

**Examples:**

You can find example `forge-deploy.yml` files in the `examples` folder of this repository. These examples provide configurations for different types of projects.

- [Laravel Example](examples/laravel/forge-deploy.yml)
- [Next.js Example](examples/nextjs/forge-deploy.yml)

## Nginx Templates

You can use custom Nginx templates by creating a new file in the `nginx_templates` folder.

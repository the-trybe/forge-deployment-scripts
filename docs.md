## Notes:

- **Domain change**: If the domain changes, a new site will be created.
- **Repository URL change**: The repository URL shouldn't be changed after the first deployment.
- **Run command change**: If the run command is modified, you need to delete the old daemon first otherwise the deployment will fail.

## Issues:

- To use the default Nginx template, an Nginx configuration named `default` must be manually created on the server.

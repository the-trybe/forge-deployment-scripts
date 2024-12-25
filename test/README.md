- to test logic (deploy.py script)
  create `.env.test` file in `test` with forge api token ex: `FORGE_API_TOKEN=your-token` then:

```bash
cd test
pytest
```

- to test action
  create a `.secrets` file in `test` directory, with a forge api token ex: `FORGE_API_TOKEN=your-token` then:

```bash
cd test
act
```

**note**: you need to install act first, refer to [act](https://github.com/nektos/act)

# Migrate CPython Sigstore bundles

```shell
git clone ssh://git@github.com/sethmlarson/migrate-cpython-sigstore-bundles
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python main.py
```

Then follow the prompts. If everything works out great and we're happy, run the `apply-changes.sh` script.
If after doing this we aren't happy, run the `restore-backup.sh` script.

## License

CC0-1.0

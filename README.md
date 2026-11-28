# learning-platform-data

Standalone Git repository for module content, Python-based generation, database
sync, and AI authoring instructions.

- `module/`: module data and Markdown Knowledge.
- `module-generate-agent/`: NEW file-first workflow instructions and legacy
  Gradle-based instructions, intentionally kept separate.
- `script/module-generate/`: STEP 1–6 NEW Python tools, status reports.
- `script/database/`: Oracle sync tools.
- `module-info-base.json`: canonical template for STEP 1 NEW.
- `temp-module/`: draft module structures.

## Clone / pull without java-learning

```powershell
git clone https://github.com/phuongnguyenit93/learning-platform-data.git
cd learning-platform-data
git pull --ff-only
```

This repository does **not** require the parent `java-learning` directory to
run the Python NEW workflow. The repository may be cloned to **any** path or
directory name. Always execute the commands below from the data repository
root. Python 3.11+ and `PyYAML` are required for YAML tools;
`python-oracledb` and configured Oracle access are only needed for database
commands.

```powershell
python -m pip install pyyaml oracledb
python script/module-generate/step1/activate_module.py --module "module/<path>" --dry-run
python script/module-generate/step2/generate-basic-info-skeleton.py --module "module/<path>" --lang vi --dry-run
python script/module-generate/step2/import-module-overviews.py --module SERVICE_NAME --lang vi --offline
python script/module-generate/step3/generate_menu_skeleton.py --module "module/<path>" --lang vi --dry-run
python script/module-generate/step5/generate-temp-file.py --module "module/<path>" --dry-run
python script/module-generate/step6/split_menu.py --module "module/<path>" --lang vi --dry-run
```

STEP 1 requires an intentionally activated module (`module_activate.json`
with `isModule: true`). `activate_module.py --apply` adds missing
`module-info.json` metadata but never overwrites existing values; filling
SERVICE_NAME and SERVICE_NAME_DESCRIBE is a separate reviewed AI step.
See `module-generate-agent/STEP_1_NEW.md` through `STEP_6_NEW.md`.

Oracle credentials belong in `.env.oracle-overview` at **this repository
root**, not its parent; the file is Git-ignored. Copy the field names from
`script/oracle-overview.env.example` into your private file. The Oracle
database/schema itself must already exist. Importers are offline/read-only by
default; `--apply` alone permits database MERGE.

Generated output under `build/` and STEP 6 scratch data under `temp/` are
Git-ignored and local to this repository.

## Legacy Gradle workflow

Legacy `STEP_1.md`–`STEP_12.md` use the **separate** `java-learning`
Gradle project and may require Google Sheets/Java build services. Those older
steps **do not run standalone**. The Python file-first
`STEP_<N>_NEW.md` workflow does not use legacy Gradle tasks.

When `learning-platform-data` is used as a Git submodule of `java-learning`,
update the parent's submodule pointer separately after committing/pushing a
data revision.

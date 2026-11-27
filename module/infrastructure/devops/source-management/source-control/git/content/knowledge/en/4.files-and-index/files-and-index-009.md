# Recognizing Empty Directories, Generated Files, and Machine-Local Configuration Files

When preparing a repository for collaborative development, you need to decide what belongs in Git and what should exist only on each developer's machine. Empty directories, build files generated when running the program, and configuration containing machine-specific paths or secrets usually require different handling from shared source code and documentation.

Git tracks file content along with paths and certain file metadata. Git does not store empty directories as independent objects. Generated files can be skipped via `.gitignore` if they are reproducible. Machine-local configuration should have a shared template in the repository while actual local values stay outside history.

## 1. Git Does Not Store Empty Directories

In Git's model, directories are represented indirectly through trees containing the entries inside them. A directory only appears in a commit when at least one entry is stored beneath it. If a directory contains no files, Git has no entry to record, so that directory does not appear in the commit's tree.

For example, a working structure might look like:

```text
sample-app/
├── src/
├── logs/          <- empty directory
├── uploads/       <- empty directory
└── README.md
```

After committing, `src/` will appear if it contains source files, whereas the empty `logs/` and `uploads/` directories will not be recreated when someone else clones the repository. This is normal Git behavior.

### Using a Placeholder File to Keep Directory Structure

If the application requires a directory to exist immediately after cloning, place a small file inside it. A common convention is naming it `.gitkeep`:

```text
sample-app/
├── logs/
│   └── .gitkeep
└── uploads/
    └── .gitkeep
```

`.gitkeep` is not a special filename recognized by Git. It is simply a community convention signaling that the directory should be kept. You can also use `README.md`, `.gitignore`, or a placeholder file named appropriately for the project.

Create placeholders and stage them:

```bash
mkdir -p logs uploads
touch logs/.gitkeep uploads/.gitkeep
git add logs/.gitkeep uploads/.gitkeep
git status --short
```

On PowerShell, you can create empty files with:

```powershell
New-Item -ItemType Directory -Force logs, uploads
New-Item -ItemType File -Force logs/.gitkeep, uploads/.gitkeep
git add logs/.gitkeep uploads/.gitkeep
```

If a placeholder exists solely to preserve structure, document it clearly in README or add an explanatory line inside the file so others understand why it is there. There is no need to create placeholders for every directory; only keep directories that the application, deployment workflow, or instructions genuinely require.

## 2. Keeping a Directory While Ignoring Generated Files Inside

A directory may need to exist in the repository while files generated inside it should not be committed. For example, the application needs `logs/`, yet runtime logs are specific to each machine.

You can use `.gitignore` at the repository root:

```gitignore
# Ignore all direct entries inside logs, but keep the placeholder
/logs/*
!/logs/.gitkeep
```

After committing `logs/.gitkeep`, the `logs/` directory will be recreated on clone. Log files created inside it will be ignored. The pattern `!/logs/.gitkeep` carves out an exception for the placeholder.

Another approach is placing `.gitignore` directly inside the directory to keep:

```gitignore
# logs/.gitignore
*
!.gitignore
```

Once `logs/.gitignore` is committed, the directory has one tracked file; all other contents in the directory are ignored. This approach is self-documenting right where the rule applies.

Note: when a parent directory is ignored completely, Git normally does not descend into that directory to look for an excepted child file. If you need an exception for a deeply nested path, you must ensure parent directories along the path can also be traversed. For simple cases like `logs/.gitkeep`, ignoring child entries and then directly excepting the file is easier to understand.

## 3. Classifying Generated Files Before Deciding to Ignore

Not every automatically generated file should be excluded from Git. Consider whether the file is reproducible, who needs to use it, and whether the repository must store its exact version.

| File Type | Example | Typical Appropriate Handling |
|---|---|---|
| Build output | `build/`, `target/`, `dist/` | Ignore if reproducible from source code and build configuration |
| Cache | `.cache/`, `.gradle/`, bundler caches | Ignore because environment-dependent or reproducible |
| Runtime logs | `logs/*.log`, `npm-debug.log` | Ignore; do not put runtime data into source history |
| Test output | `coverage/`, temporary test reports | Usually ignore; store CI artifacts if review is needed |
| Locally installed dependencies | `node_modules/`, virtual environments | Usually ignore and reinstall from manifest/lockfile |
| IDE/OS temporary files | personal workspaces, `.DS_Store`, `Thumbs.db` | Ignore per team convention or personal configuration |
| Distributable generated source | code generated from schemas/protobuf or client SDKs | May commit if repository consumers need it directly without running the generator |
| Dependency lockfiles | `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock` | Usually commit when the project needs reproducible dependency versions |
| Release artifacts | installers, binaries, images | Per release policy; usually stored in a registry or separate artifact system |

A helpful question is: **if this file is deleted, can the team reproduce it identically from already-managed inputs?** If yes, ignoring is usually sensible. If the file is an input, an output users must download directly, or reproduction is unstable, the team needs to decide explicitly how to version it.

### Do Not Ignore Everything Labeled “Generated”

Some automatically generated files are still an essential part of the project. Lockfiles are a classic example: they are produced by tooling yet ensure team members install the exact same dependency versions. Generated source may also need to be committed if downstream users do not install the generator or lack the source schema.

Conversely, local build binaries, caches, logs, and coverage reports are generally not the project's source of truth. Ignore them or store them in an artifact system instead of putting them into source code commits.

## 4. Creating `.gitignore` for Common Artifacts

A root `.gitignore` file can contain rules matching the project's stack. General example:

```gitignore
# Build output
/build/
/dist/
/target/

# Dependencies and caches
/node_modules/
/.cache/
.gradle/

# Logs and test output
*.log
/coverage/

# Operating system files
.DS_Store
Thumbs.db

# Local configuration - see machine-local config section
.env
.env.*
!.env.example
/config/app.local.yml
```

This is only an example; do not copy everything blindly without checking your project. For instance, a project that intentionally commits `dist/` to deploy a static site should not ignore that directory. A Java project using Maven may need to ignore `target/`, whereas another project might manage a `target` folder as input data.

Place `.gitignore` in the repository and commit it so everyone shares the same rules:

```bash
git add .gitignore
git diff --cached -- .gitignore
git commit -m "Add project ignore rules"
```

## 5. What Is a Machine-Local Configuration File?

Machine-local configuration files contain values valid only for one developer's environment or one deployment machine. Examples:

- Local paths to data directories or SDKs on the machine.
- Local service ports, development database names.
- Usernames, tokens, passwords, or API keys.
- Internal service addresses reachable only from a specific network.
- OS-dependent IDE or tool configuration.

If you commit these values, they can break the project on other machines, cause constant merge conflicts, or accidentally expose sensitive information. The common organization pattern is committing a **configuration template** and ignoring the **actual local configuration file**.

Example structure:

```text
sample-app/
├── .env.example          <- commit: variable names and illustrative values
├── .env                  <- ignore: machine-specific values
├── config/
│   ├── app.example.yml   <- commit: configuration template
│   └── app.local.yml     <- ignore: local configuration
└── .gitignore
```

`.env.example` can hold keys with dummy or placeholder values:

```dotenv
APP_ENV=development
APP_PORT=3000
DATABASE_URL=postgres://user:password@localhost:5432/sample_app
API_TOKEN=replace-with-your-local-token
```

Do not put real credentials into template files. Provide instructions so each team member copies the template and fills in local values:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

Then users edit `.env` on their own machine; `.gitignore` prevents this file from being added through normal commands.

## 6. Configuration Templates and Local Override Files

For YAML, JSON, or TOML configuration, you can use a template and local file pair:

```text
config/
├── app.example.yml
└── app.local.yml
```

`.gitignore`:

```gitignore
/config/app.local.yml
```

Committed template file:

```yaml
server:
  host: 127.0.0.1
  port: 8080
database:
  url: jdbc:postgresql://localhost:5432/sample_app
  username: local_user
  password: change-me
```

The values in the example are illustrative only; do not use real passwords in committed templates. Project documentation should explain how to create `app.local.yml` from the template and how the application loads overrides. Git only manages committed files; Git does not automatically know how the application merges two config files.

If configuration differs in only a few sensitive values, prefer environment variables or a secret manager instead of copying entire files. This keeps shared configuration less fragmented and reduces the risk of accidentally committing secrets.

## 7. Three Places to Put Ignore Rules

Not every ignore rule needs to be committed to the repository. Git provides several places to declare them:

| Declaration Location | Scope | When to Use |
|---|---|---|
| `.gitignore` in the project | Shared across the repository and committed | Build output, logs, local files per team convention |
| `.git/info/exclude` | Current local repository only | Temporary files or personal config not meant to be shared |
| Global ignore file via `core.excludesFile` | Repositories of the current user | Files generated by IDE, editor, or OS on a personal machine |

Example adding a local rule for a single repository using `.git/info/exclude`:

```gitignore
# Ignore only in the current clone
scratch-notes.txt
local-test-data/
```

This file resides inside the Git directory and is not committed with the project.

Set a global ignore file:

```bash
git config --global core.excludesFile ~/.config/git/ignore
```

Contents of the global ignore file might be:

```gitignore
.DS_Store
Thumbs.db
.idea/workspace.xml
```

Global rules suit personal or operating system files. If the whole team needs to ignore a project-specific build directory, put the rule in the committed `.gitignore` rather than asking everyone to configure it globally.

## 8. Ignoring Does Not Untrack Already-Committed Files

`.gitignore` only affects how Git handles untracked paths. If `.env` or `config/app.local.yml` has already been committed, adding them to `.gitignore` does not make Git stop tracking them. Changes to those files still appear in `git status`.

To remove files from the index while keeping local copies on disk:

```bash
# Add ignore rules first
printf '\n.env\n/config/app.local.yml\n' >> .gitignore

# Remove from index, keep files in working tree
git rm --cached -- .env config/app.local.yml

# Check changes ready to commit
git status
git diff --cached
```

Then commit the `.gitignore` update and the removal from the repository. Other team members will no longer receive the local files from new commits; they will need to create their own files from the configuration template.

If a file ever contained real passwords, tokens, or keys, removing it from a new commit **does not erase the secret from old history**. Revoke or rotate the credentials first, then clean history according to your project's security procedures. Do not treat `.gitignore` as a way to delete secrets that were already committed.

## 9. Checking Ignored Files and Tracked Files

Use `git check-ignore -v` to see which rule, file, and line number ignored a path:

```bash
git check-ignore -v .env
git check-ignore -v build/output.jar
```

If you need to check ignore rules against an already-tracked path, use `--no-index`:

```bash
git check-ignore -v --no-index config/app.local.yml
```

List status including ignored files:

```bash
git status --short --ignored
```

Check whether a path is currently tracked by Git:

```bash
git ls-files -- .env
```

If `git ls-files` prints the path, the file is currently in the index from the current commit or staged index. If the file does not appear yet `git check-ignore -v` finds a rule, it is ignored and untracked.

## 10. Distinguishing Ignored, Untracked, and Deleted

These three states are not the same:

| State | Meaning | How to Check |
|---|---|---|
| Untracked | New file, not yet in the index and not ignored | `git status --short` |
| Ignored | Untracked file matching an ignore rule | `git check-ignore -v <path>` or `git status --short --ignored` |
| Deleted | File was tracked but removed from the working tree | `git status --short` or `git diff --summary` |

If a local file disappears from `git status`, do not immediately conclude that Git deleted or untracked it. Check `git ls-files`, `git check-ignore -v`, and the filesystem state to know which state the file is actually in.

## 11. Previewing Impact Before Cleaning Generated Files

Build files, caches, and logs can be deleted to free space, but preview the list before executing. `git clean` can delete untracked and ignored files from the working tree.

```bash
# Preview untracked files/directories to be deleted (excluding ignored)
git clean -nd

# Preview specifically ignored files/directories to be deleted
git clean -ndX

# Preview all untracked files, including ignored
git clean -ndx
```

The `-n` (dry run) and `-d` (recurse into directories) options let you view the list without deleting. Run actual deletion only after carefully reviewing the list—for example, `git clean -fdX` deletes ignored files and directories. This command does not delete tracked files, but it can delete a local `.env` or runtime data you have not backed up.

To clean build output, prefer your build system's clean command if available. Only use `git clean` when you clearly understand the untracked/ignored scope in the repository.

## 12. Setup Workflow for a New Project

When preparing a repository for the whole team to use, you can follow this sequence:

1. List directories the application needs after cloning, such as `logs/`, `uploads/`, `tmp/`.
2. For empty directories to keep, add `.gitkeep`, `.gitignore`, or an explanatory README.
3. Classify artifacts by reproducibility and distribution needs; ignore build outputs, caches, logs, and locally installed dependencies if they are not inputs needing versioning.
4. Decide explicitly whether generated source, lockfiles, and release artifacts need to be committed per the project workflow.
5. Create template files like `.env.example` or `config/app.example.yml`, containing only dummy values and instructions.
6. Ignore local files like `.env`, `config/app.local.yml`, and machine-specific data.
7. Place personal rules in `.git/info/exclude` or a global ignore file.
8. Verify with `git status --short --ignored`, `git check-ignore -v`, and `git ls-files`.
9. Stage and review `.gitignore`, placeholders, and templates before committing.

Example desired state:

```text
sample-app/
├── .gitignore             <- tracked
├── .env.example           <- tracked
├── .env                   <- ignored
├── config/
│   ├── app.example.yml    <- tracked
│   └── app.local.yml      <- ignored
├── logs/
│   └── .gitkeep           <- tracked
├── build/                 <- ignored
└── src/                   <- tracked source
```

Checks before committing:

```bash
git status --short --ignored
git check-ignore -v .env config/app.local.yml build/output.jar
git ls-files -- .gitignore .env.example config/app.example.yml logs/.gitkeep
git diff --cached
```

## 13. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Git tracks empty directories | No. Git stores files; to keep a directory, there must be a placeholder or config file inside it. |
| `.gitkeep` is a special Git command or feature | No. It is a filename convention chosen by projects. |
| Every auto-generated file must be ignored | No. Lockfiles or generated source may need to be committed for reproducibility or downstream consumption. |
| Adding a file to `.gitignore` stops tracking it | No. Already-tracked files stay tracked; remove from the index with `git rm --cached` if keeping the local copy. |
| `.git/info/exclude` is shared with teammates | No. It applies only to the current local repository. |
| A global ignore file replaces the project `.gitignore` | No. Global ignore is for personal habits; shared project rules should be committed. |
| Deleting `.env` from a new commit removes the secret from history | No. Credentials must be revoked/rotated and history cleaned if secrets were exposed. |
| `git clean -fdX` only deletes harmless caches | No. It deletes all matching ignored items, which can include local config or unbacked-up data. |

## 14. Self-Check

1. **Why does Git not preserve an empty directory after cloning?**
   - Because Git trees store file entries and subdirectories; a directory with no entries is not represented independently.
2. **Does `.gitkeep` have any special meaning to Git?**
   - No. It is merely a convention for placing a placeholder file inside a directory.
3. **What should you do with reproducible build output?**
   - Usually add an appropriate ignore rule, unless the project workflow intentionally distributes or versions that artifact.
4. **Why should you commit `.env.example` but ignore `.env`?**
   - The template file shares variable names and structure; the actual file holds machine-specific values or secrets.
5. **How can you find out which rule ignored a file?**
   - Use `git check-ignore -v <path>`.
6. **Does an already-tracked file become untracked when added to `.gitignore`?**
   - No. Use `git rm --cached <path>` to remove it from the index while keeping the local file.
7. **Which command previews ignored files that `git clean` would delete?**
   - `git clean -ndX`.

## Conclusion

Git does not store empty directories, so use placeholders like `.gitkeep` or `.gitignore` when structure must be preserved. Generated files should be classified by reproducibility and distribution needs; build outputs, caches, and logs are typically ignored, while lockfiles or generated source may need to be committed. For machine-local configuration, commit template files and ignore local files containing private values. Use `.gitignore` for shared rules and `.git/info/exclude` or global ignore for personal needs, then verify with `git check-ignore`, `git status --ignored`, and `git ls-files` before committing or cleaning data.

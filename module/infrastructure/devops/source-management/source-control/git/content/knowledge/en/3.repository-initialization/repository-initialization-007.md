# Organizing Repository Structure and Boundaries for What Belongs in Git

A well-structured Git repository has clear boundaries: readers know where source code lives, how to build and test, which configuration is shared, and which files belong only to a personal machine. Directory structure directly affects searchability, code review, access control, automation, and history maintenance. Git can track nearly any kind of file, yet not every file in a workspace should become part of the repository.

The goal when organizing a repository is to keep what is necessary to develop, test, build, and understand the project; while excluding data that can be regenerated, depends on a personal environment, or contains secrets.

## 1. Determining the repository root before creating the structure

The repository root is the directory Git treats as the root of the working tree. When you run `git init` in a directory, Git creates repository management metadata there. Files and subdirectories beneath the root can be added to history, except paths that are ignored or left unstaged.

Example:

```text
customer-api/
  .git/
  README.md
  src/
  tests/
```

In this example, `customer-api/` is the repository root. `.git/` holds the object database, refs, index, and Git configuration; this directory is not committed as project content. The `src/`, `tests/` directories and `README.md` file are trackable project content.

Check the current repository root:

```bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
```

The first command returns the absolute path to the root. The second reports the relative path from the root to the current directory; if you are at the root, the output is empty.

Initialize Git at the right project level. If you run `git init` too high—such as in a directory containing multiple unrelated projects—Git can lump everything into an unintended history. If you run it too deep, shared files in the parent directory will sit outside the repository.

## 2. Principles for choosing what goes into the repository

Before creating directories, classify content by purpose:

| Content group | Usually belongs in Git? | Examples |
|---|---|---|
| Source code and assets required to run the app | Yes | `src/`, templates, static assets |
| Tests and small, non-sensitive test data | Yes | `tests/`, fixtures, mock data |
| Documentation and developer guides | Yes | `README.md`, `docs/`, ADRs |
| Build configuration and dependency manifests | Yes | `pom.xml`, `build.gradle`, `package.json`, lockfiles |
| Sample configuration without secrets | Yes | `.env.example`, `application-local.example.yml` |
| Build, test, migration, and dev scripts | Yes | `scripts/`, `Makefile`, CI workflows |
| Generated build files and caches | Usually no | `target/`, `build/`, `.gradle/`, `node_modules/` |
| Logs, temporary files, and IDE state | Usually no | `*.log`, `.idea/workspace.xml`, `.vscode/settings.local.json` |
| Credentials and personal data | No | `.env`, private keys, tokens, credential files |
| Large artifacts that can be downloaded or regenerated | Policy-dependent | archives, binary releases, models, videos |

A helpful question for each file is: *Does a new team member cloning the repository need this file to understand, build, test, or operate the project in the supported way?* If not, the file may be an output, cache, private data, or a dependency managed elsewhere.

## 3. A basic structure for a single project

For a standalone application or library, the structure can start simple:

```text
customer-api/
  .gitignore
  .gitattributes
  README.md
  LICENSE
  pom.xml
  src/
    main/
      java/
      resources/
    test/
      java/
      resources/
  docs/
  scripts/
```

Role of each component:

- `src/main/`: application source code and runtime resources.
- `src/test/`: automated tests, fixtures, and shareable test data.
- `docs/`: architecture documentation, guides, procedures, and technical decisions.
- `scripts/`: repeatable scripts for building, checking, development, or maintenance.
- `pom.xml`: build and dependency declarations; lockfiles or version catalogs should also be managed when supported by tooling.
- `.gitignore`: excludes local files, caches, and build outputs that do not need tracking.
- `.gitattributes`: line-ending, diff, merge, or LFS rules for specific file types.

There is no need to pre-create every directory if the project does not use it yet. The structure should reflect real components rather than creating empty layers just to look standardized.

## 4. Example structure for a Java project

A Java project using Maven or Gradle can be organized as follows:

```text
inventory-service/
  .gitignore
  .gitattributes
  README.md
  pom.xml
  mvnw
  mvnw.cmd
  .mvn/
    wrapper/
  src/
    main/
      java/com/example/inventory/
      resources/
    test/
      java/com/example/inventory/
      resources/
  docs/
    architecture.md
    local-development.md
  scripts/
    check.sh
```

Maven Wrapper files such as `mvnw`, `mvnw.cmd`, and the `.mvn/wrapper/` directory should generally be committed because they let team members use a consistent Maven version without installing Maven globally. For Gradle Wrapper, `gradlew`, `gradlew.bat`, and `gradle/wrapper/` are also typically committed. Check your organization's checksum and wrapper version policies.

Outputs such as Maven's `target/` or Gradle's `build/` are normally regenerated from source and build configuration, so put them in `.gitignore`. Do not ignore all of `src/main/resources/` simply because it contains some local configuration files; separate shared sample configuration from files containing secrets.

## 5. Example structure for a monorepo

A monorepo houses multiple related applications or packages in a single repository. The structure needs to help readers identify the boundaries of each component and how to build/test them independently:

```text
platform/
  README.md
  .gitignore
  .gitattributes
  docs/
  services/
    customer-api/
      README.md
      pom.xml
      src/
      tests/
    billing-worker/
      package.json
      src/
      tests/
  libraries/
    auth-client/
      pom.xml
      src/
  tools/
    release/
  scripts/
```

The root README explains the overall workspace, its components, dependencies between them, and common commands. READMEs inside each service can describe how to run that service individually. CI configuration should determine which components need to be built/tested when corresponding paths change.

A monorepo does not mean every component must share the same language, build tool, or release cadence. Keep directory boundaries clear, declare dependencies explicitly, and avoid having one service directly read internal files of another service when the shared interface should be a package or API.

## 6. When should you split into multiple repositories?

Not every project belongs in a monorepo. Multiple repositories may be appropriate when components:

- Have different release lifecycles and access permissions.
- Belong to independent owning teams and rarely change together.
- Have different security policies or licenses.
- Have separate dependencies and CI workflows without needing synchronized commits.
- Are reused as standalone products across multiple projects.

Conversely, a monorepo is often useful when multiple components need coordinated changes, share tooling, have tight internal dependencies, or require a single atomic commit updating multiple packages.

| Criterion | Monorepo | Multiple repositories |
|---|---|---|
| Committing changes across multiple components at once | Convenient; one commit can update multiple directories | Requires multiple commits/PRs or coordination workflows |
| Per-component access control | Can be more complex | Easy to separate permissions at the repository level |
| CI | Needs path- and dependency-based optimization | Each repository has its own pipeline |
| Sharing tooling and conventions | Easy to centralize | Requires synchronization across repositories |
| History and clone size | Can grow large as components accumulate | Each repository has its own history and size |

Choose boundaries based on how teams develop, release, and own software. Do not split repositories just to have extra folders, and do not merge unrelated systems into one history simply because they sit next to each other on disk.

## 7. Keeping shared configuration separate from local configuration

A repository should contain the configuration needed to understand how to run the application, but not credentials or settings valid only on one machine.

Example configuration layout:

```text
config/
  application.yml
  application-example.yml
  logging.yml
```

A sample file can contain dummy values or placeholders:

```yaml
database:
  url: ${DATABASE_URL:jdbc:postgresql://localhost:5432/inventory}
  username: ${DATABASE_USERNAME:app}
  password: ${DATABASE_PASSWORD:}
```

Sensitive values are passed through environment variables or a secret manager. Local files such as `.env` or `application-local.yml` holding real credentials should be ignored and never committed.

Provide a template file so newcomers know what needs to be declared:

```text
.env.example
```

This file should contain variable names and illustrative values, not real tokens or passwords. The README describes how to copy the template file to `.env` and retrieve credentials from organization-approved sources.

## 8. Excluding build outputs, caches, and installed dependencies from Git

Directories regenerated from source code and build configuration generally should not be committed:

| Tool | Typically ignored paths |
|---|---|
| Maven | `target/` |
| Gradle | `.gradle/`, `build/` |
| Node.js | `node_modules/`, certain cache directories |
| Python | `.venv/`, `__pycache__/`, `.pytest_cache/` |
| Java IDEs | `.idea/workspace.xml`, `.classpath`, `.project` depending on project policy |
| Operating systems | `.DS_Store`, `Thumbs.db`, `Desktop.ini` |

Not every file in this group is always ignored. For example, an Eclipse project might intentionally commit `.project` and `.classpath`; a web app might commit `dist/` if it is a deployed artifact under a specific workflow. Base your decision on how the project actually builds and releases.

Dependency manifests and lockfiles should generally be committed to ensure reproducible environments. Installed dependency directories generally should not be committed because they can be reinstalled from the manifest and lockfile.

## 9. Designing `.gitignore` along directory boundaries

`.gitignore` specifies untracked paths that Git should ignore. You can place a file at the root to apply to the entire project, or add files in subdirectories to group rules by component.

Example root `.gitignore` for a Java project:

```gitignore
# Maven / Gradle output
target/
build/
.gradle/

# Local environment and secrets
.env
.env.*
!.env.example
application-local.yml
*.pem
*.key

# IDE and OS local files
.idea/workspace.xml
.vscode/settings.local.json
.DS_Store
Thumbs.db

# Logs and temporary files
*.log
*.tmp
```

Patterns should be reviewed. For instance, `*.key` might also ignore mock key files used in tests; if the project has fixtures that must be committed, design specific exceptions and ensure the fixtures contain no real keys.

A `.gitignore` inside `services/customer-api/` can hold rules specific to that service. Patterns are relative to the `.gitignore` file's location; this helps teams manage rules close to where files are generated.

### 9.1. Checking why a file is ignored

Use:

```bash
git check-ignore -v path/to/file
```

Git displays the `.gitignore` file, line number, and matched pattern. If you want to check an already tracked file as well, add `--no-index`:

```bash
git check-ignore -v --no-index path/to/file
```

An already tracked file does not automatically stop being tracked just because you add it to `.gitignore`. If you genuinely want to stop tracking a file while keeping it on disk, run `git rm --cached path/to/file` and commit the change. Only do that after confirming the file no longer needs to be shared.

### 9.2. Do not use ignore rules to hide organizational issues

If `.gitignore` keeps growing with exceptions for personal files, the repository root may be too broad or the project may not have separated shared configuration from local state. Revisit directory boundaries, the build setup, and where private data is stored rather than adding broad patterns just to make `git status` look clean.

## 10. Secrets and sensitive data do not belong in the repository

Do not commit:

- `.env` files containing real tokens or passwords.
- Private keys, certificate keys, SSH keys, and signing keys.
- Cloud credential files, database dumps with real data, or user exports.
- Logs containing access tokens, session IDs, personal information, or authorization headers.
- Config files containing internal URLs with embedded usernames/passwords.

Git preserves history long-term. Deleting a file in a new commit does not remove sensitive data from older commits. If a secret has been committed or pushed, revoke/rotate the credential first, assess access exposure, and clean up history following a coordinated procedure.

To reduce risk:

1. Use a secret manager or environment variables for credentials.
2. Commit template config files with placeholders.
3. Add local files to `.gitignore` before making the first commit.
4. Use secret scanning in pre-commit hooks or CI.
5. Review `git diff --cached` before committing.

## 11. Large files, datasets, and artifacts

Not all large data should be stored in the repository. Distinguish between:

- **Small, stable, non-sensitive fixtures:** can be committed for reproducible tests.
- **Large or frequently changing datasets:** consider object storage, a data registry, or a data versioning system.
- **Binaries needing version alignment with source:** consider Git LFS if the host supports it and the team accepts quota/bandwidth implications.
- **Build or release artifacts:** should usually live in an artifact registry or release storage rather than being committed to the source repository.
- **Production data:** never put in Git; manage through appropriate data systems and backups.

If using LFS, declare patterns in `.gitattributes` and document how team members install Git LFS. If using object storage, the repository can store manifests, checksums, versions, or download scripts, while the actual payload resides in the separate storage system.

## 12. Beware of nested repositories

A subdirectory can contain its own Git repository, for example:

```text
workspace/
  .git/
  app/
  vendor-library/
    .git/
```

If you run `git add vendor-library`, Git may warn that you are adding an embedded Git repository. The staged entry may become a gitlink (mode `160000`) pointing to a commit in the child repository, rather than adding the child's files into the parent repository as normal files.

Anyone cloning the parent repository will not automatically get the child repository's contents if you only accidentally staged a gitlink. If you want an independent dependency with an explicit URL/commit, declare a submodule via `git submodule add`. If you want the contents inside the parent repository's own history, ensure the subdirectory no longer has its own `.git` metadata before adding it as a normal directory; only delete that metadata after confirming the child history is already saved elsewhere or no longer needed.

Check for gitlinks in the index or tree:

```bash
git ls-files --stage
git ls-tree HEAD
```

An entry with mode `160000` indicates the path is stored as a gitlink. Do not hastily delete `.git` inside a subdirectory: it may be an independent repository containing history worth preserving.

## 13. Symbolic links and special files

Git can track symbolic links on supported systems. The tree stores mode `120000` and the blob contains the link's target path, not the contents of the file the link points to.

This means a symlink pointing to a file outside the repository does not bring that external file's contents into Git. Anyone cloning may receive the symlink while the target does not exist on their machine. Avoid using symlinks to reference personal files or directories outside the repository if the project must run across multiple environments.

Git primarily tracks regular files, the executable bit on supported platforms, symlinks, and gitlinks. Other filesystem attributes such as ownership, ACLs, or timestamps are not stored as a full filesystem replica. If the project requires special permissions or metadata, use provisioning scripts or deployment tools to configure them.

## 14. Portable filenames and structure

Repositories are often cloned across Windows, macOS, and Linux. Therefore, avoid filenames that differ only in letter case, Windows reserved names, inconsistent path separators, or excessively long paths.

For example, two files named `Config.yml` and `config.yml` can coexist on a case-sensitive filesystem but cause checkout conflicts on certain Windows/macOS configurations. Pick a consistent naming convention, typically lowercase with hyphens or underscores.

Do not use filenames containing control characters or characters difficult to represent in a shell. For scripts processing path lists, prefer NUL-delimited options such as `git ls-files -z` instead of splitting output on whitespace.

## 15. README and documentation give structure meaning

A good directory layout still needs explanation. The root README should answer:

- What problem does the project solve and where are the main components located?
- What environment requirements and tools need to be installed?
- How do you build, run tests, and run the application?
- Where does local configuration come from and which environment variables must be set?
- Which directories hold source code, documentation, scripts, and test data?
- How are contributions, reviews, and releases handled?

In-depth documentation can live in `docs/`, while service-specific instructions belong right inside the service directory. Avoid duplicating the same instructions across multiple places since content easily drifts out of sync; the root README should link to detailed documentation.

## 16. Checking what will be included in a commit

Before committing the initial structure, inspect status:

```bash
git status --short --untracked-files=all
```

Stage paths intentionally instead of defaulting to `git add .` when the workspace contains many files of unclear origin:

```bash
git add README.md .gitignore .gitattributes pom.xml src/ tests/ docs/
```

Then review staged content:

```bash
git diff --cached --stat
git diff --cached --name-status
git diff --cached
```

Check ignored files:

```bash
git check-ignore -v .env target/example.class
```

Check which files are actually tracked:

```bash
git ls-files
```

If there are many files, combine `git ls-files` with filters or use `git ls-files -z` in scripts to handle filenames safely. Inspect large files, binaries, config files, and sensitive paths before creating a commit.

## 17. Workflow for designing a repository from scratch

A practical workflow can follow these steps:

1. **Define the scope:** a single application, a library, a monorepo, or multiple independent repositories.
2. **Choose the root:** place the repository in the exact directory containing the content and history to be shared.
3. **Sketch the directories:** separate source, tests, docs, sample config, scripts, and independent components.
4. **Classify files:** mark content to commit, regenerable files, local data, secrets, and artifacts.
5. **Create `.gitignore` and `.gitattributes`:** establish rules right from the start, before staging generated files.
6. **Write the README:** describe the structure, setup steps, build/test commands, and local configuration.
7. **Check for nested repositories:** determine which subdirectories are submodules vs. regular directories.
8. **Review the staging area:** use `git status`, `git diff --cached`, and `git ls-files` to verify scope.
9. **Commit the initial structure:** create a clear commit, such as `chore: initialize repository structure`.
10. **Verify on a clean clone:** confirm a new team member can clone, install dependencies, build, and test following the README.

## 18. Common mistakes

- **Initializing Git in an overly broad parent directory:** accidentally pulling multiple unrelated projects into the same history.
- **Initializing Git too deep:** omitting shared documentation or configuration located in the parent directory.
- **Committing build outputs and caches:** bloating the repository, creating noisy diffs, and causing frequent conflicts.
- **Accidentally ignoring source files or lockfiles:** preventing fresh clones from building or reproducing dependencies.
- **Committing `.env` or credential files:** secrets can remain in history even after the file is deleted.
- **Adding a child repository as a normal directory without noticing the gitlink:** people cloning do not receive the expected contents.
- **Creating too many directory levels:** making files hard to find and increasing the cost of moving or renaming.
- **Using symlinks to files outside the repository:** other environments lack the link target.
- **Inspecting only the working tree without checking the index:** the commit may contain a different version from the file open in the editor.
- **Never testing a clean clone:** personal configuration or cached dependencies on the author's machine hide missing files.

## 19. Comprehensive `.gitignore` example for a Java project

This is a starting point that can be adapted to your actual build tools and IDEs:

```gitignore
# Maven
target/

# Gradle
.gradle/
build/

# Local environment
.env
.env.*
!.env.example
application-local.yml

# IDE local state
.idea/workspace.xml
.vscode/settings.local.json
*.iml

# Logs and temporary files
*.log
*.tmp

# OS files
.DS_Store
Thumbs.db
Desktop.ini
```

If the project uses IntelliJ, Eclipse, or VS Code, agree on which configuration files should be shared and which belong to personal workspaces. Certain launch or formatter configs may be worth committing so everyone follows the same rules; do not mechanically ignore the entire IDE directory if the project needs to share configuration.

## 20. Key takeaways

The repository root defines the boundary of Git history. Organize inside the root by component and purpose: source code, tests, docs, sample configuration, scripts, and build metadata should be shared; build outputs, caches, installed dependencies, IDE state, credentials, and local data generally belong outside history. Use `.gitignore` to manage untracked files, inspect for nested repositories to avoid unintended gitlinks, and review the staging area before committing. A well-organized repository should allow any team member to perform a clean clone, understand the layout, and build/test according to the guide without needing secrets or private state from the creator's machine.

# Distinguishing Git Core, Extensions, and Hosting Service Features

When working with Git, you may run the `git` command in a terminal, install Git LFS, use a credential manager, install IDE plugins, and interact with GitHub, GitLab, or another hosting service. These components often appear in the same workflow, yet they do not belong to the same layer. Without distinguishing these boundaries, it is easy to assume a hosting feature is built into Git, or think that installing Git already gives you every tool you need.

The ecosystem can be divided into three main groups:

1. **Git core:** Git's data model, built-in commands, configuration, protocols, and version control mechanisms.
2. **Extensions and external tools:** programs that supplement or integrate with Git for specific needs, such as Git LFS, credential helpers, history-rewriting tools, and IDE plugins.
3. **Hosting service features:** pull requests/merge requests, reviews, branch protection, CI runners, issues, releases, webhooks, and access controls provided by the server platform.

All three groups can work together, yet they have different installation methods, configurations, operations, and compatibility limits. This lesson helps you identify which component is performing the work, know where to inspect when errors occur, and choose the right documentation.

## 1. What is Git core?

Git core is the foundation of the distributed version control system. It defines how Git stores objects, creates commits, manages branches and tags, compares content, exchanges data between repositories, and performs history management operations.

Core components include:

- **Object database:** stores blob, tree, commit, and tag objects.
- **Index (staging area):** prepares the snapshot for the next commit.
- **Refs:** branch names, tags, and other references pointing to objects.
- **Working tree:** files checked out for users to edit.
- **Configuration:** controls Git behavior at system, global, or local scope.
- **Transport/protocol:** exchanges objects and refs over local paths, SSH, HTTP(S), or the Git protocol.
- **Hooks and attributes:** integration mechanisms to run scripts or apply file-handling rules at specific points.

Familiar commands such as `git init`, `git clone`, `git status`, `git add`, `git commit`, `git switch`, `git merge`, `git rebase`, `git fetch`, `git push`, `git tag`, and `git log` belong to Git's command set. They operate on the repository and history according to the Git model.

Git also provides low-level (*plumbing*) commands for accessing internal structures, such as `git cat-file`, `git hash-object`, `git update-ref`, `git rev-parse`, and `git ls-tree`. High-level (*porcelain*) commands such as `git status`, `git log`, and `git switch` are designed for convenient day-to-day work.

## 2. Built-in features in Git

Some features may be used less often in basic workflows yet are still built-in Git functionality, requiring no separate extension installation.

| Feature | Representative command | Purpose |
|---|---|---|
| Managing multiple worktrees | `git worktree` | Create multiple working directories sharing the same repository |
| Selective checkout | `git sparse-checkout` | Limit which paths are populated into the working tree |
| Managing submodules | `git submodule` | Track child repositories using gitlinks and URL configuration |
| Object database maintenance | `git gc`, `git maintenance`, `git count-objects` | Measure, pack objects, and maintain the repository |
| Searching history | `git log`, `git blame`, `git bisect`, `git grep` | Trace commits, changes, and content |
| Object verification | `git fsck`, `git cat-file` | Check object structure and contents |
| Managing configuration | `git config` | Configure Git behavior by scope |
| Hooks and attributes | hook directory, `.gitattributes` | Integrate scripts and file-handling rules |

For example, `git worktree` and `git sparse-checkout` are not hosting products. They operate locally on the repository with a supporting Git client. You can use them when working with ordinary Git remotes, provided the Git version and environment support them.

Similarly, `git submodule` is a Git feature, though the child repository that the submodule points to still must be hosted in an accessible location. Git manages the gitlink and checkout process; permissions, availability, and server policies for the child repository belong to the hosting environment.

## 3. What are extensions and external tools?

An extension is a program or tool that adds capabilities to a Git workflow. It may be invoked from a Git command, configured as a helper/filter, triggered via hooks, or run inside an IDE. Not every external tool is an official Git extension; some are developed by the community, vendors, or organizations.

Some examples:

| Tool | Role | Common integration method |
|---|---|---|
| Git LFS | Store large file contents outside the normal Git object database | `git lfs` command, filters, and hooks |
| Git Credential Manager | Manage authentication credentials for remotes | Git credential helper |
| `git-filter-repo` | Filter or rewrite repository history | Standalone program run against a local repository |
| `git-annex` | Manage large files and content outside Git using its own model | Tool commands and metadata |
| IDE Git integration | Display diffs, branches, commits, and Git actions in the UI | Invokes the Git executable or integrated IDE APIs |
| GUI client | Provide a graphical interface for Git operations | Invokes Git or implements part of operations via its own library |

A tool may integrate deeply with Git yet still have its own installation lifecycle, versioning, and configuration. When an error occurs, identify whether the fault lies in Git core, an extension, the IDE, or the server rather than assuming everything is a Git bug.

## 4. Distinguishing built-in Git commands from external subcommands

When running a command like:

```bash
git status
git log
```

Git invokes commands built into its installation. However, some commands take the form:

```bash
git lfs version
git filter-repo --help
```

`git lfs` is typically provided by a separate executable named `git-lfs`. Git searches for external subcommands according to program lookup rules in the execution environment. Tools of this kind usually must be installed separately and be present in PATH.

You can list the Git commands recognized by the current installation:

```bash
git help -a
```

Check the executable path of Git and an external subcommand:

```bash
# macOS, Linux, or Git Bash
command -v git
command -v git-lfs

# Windows PowerShell
where.exe git
where.exe git-lfs
```

If `git lfs` reports command not found, Git core may still work normally; the issue may be that Git LFS is not installed or not in PATH. Verify with `git lfs version` and check the executable.

Not every name following `git` is an external subcommand. For example, `git co` might be a configured alias:

```bash
git config --get-regexp '^alias\.'
```

An alias is simply a configured shorthand, not necessarily a separate program. Distinguishing aliases, built-in commands, and external subcommands helps locate the right source when a command fails to run.

## 5. Git LFS: an example of an extension integrated with Git core

Git LFS is a classic example of an extension. Git core stores small pointer files in commits, while the Git LFS client transfers large binary contents to an LFS server.

After installing Git LFS, run:

```bash
git lfs version
git lfs install
git lfs track "*.psd"
```

`git lfs track` writes rules into `.gitattributes`. The `.gitattributes` file is committed to the repository so other clones know which paths use the LFS filter. Actual contents are transferred to the LFS endpoint during fetch/push via Git LFS mechanisms.

Three components collaborate here:

1. Git core manages commits, trees, index, refs, and regular push/fetch.
2. The Git LFS client executes clean/smudge filters and transfers LFS objects.
3. The hosting service provides the LFS endpoint, quota, authentication, and large-object storage.

If pushing commits succeeds while LFS objects fail to upload, others may clone the repository yet fail to retrieve the large file contents. Therefore, verifying Git refs and LFS objects are two separate checks.

## 6. Credential helpers: external authentication tools

Git core supports a credential helper mechanism to retrieve and store authentication credentials. A helper can be a program bundled with Git, a standalone program, or an OS integration.

Check configured helpers:

```bash
git config --show-origin --get-all credential.helper
```

Example configuring a helper:

```bash
git config --global credential.helper manager
```

Helper names and invocation vary by installation. On Windows, Git Credential Manager is commonly used to support HTTPS authentication and integrate with the OS credential store. Some macOS/Linux environments can also install and configure GCM separately.

Points to distinguish:

- Git core defines the protocol for invoking credential helpers.
- The credential manager handles storing, retrieving, or refreshing credentials.
- The hosting service decides whether the account/token/key has permission to access the repository.

If authentication fails, check the remote URL, configured helper, sign-in session, and account permissions on the hosting service. The fact that `git status` works does not prove remote authentication works, because `status` does not contact the server.

## 7. Hooks, filters, and attributes sit at the integration boundary

Git core provides the mechanism to invoke hooks and apply attributes/filters, while the script or program performing the work may be supplied by the project or an external tool.

### Hooks

For example, `pre-commit`, `commit-msg`, or `pre-push` are invoked by Git at defined lifecycle points. Git provides the hook points and input contract; the hook content is a script installed in the hooks directory or `core.hooksPath`.

```bash
git config --show-origin --get core.hooksPath
git rev-parse --git-path hooks
```

Local hooks enable early checks, but may not exist in other clones or may be skipped via certain options. If a rule is mandatory for everyone, enforce it additionally in CI or server-side policies.

### Attributes and filters

`.gitattributes` can declare how line endings, diffs, merges, or filters are handled for files. Git core reads the attributes, while the invoked filter program may be an external tool.

Inspect effective attributes:

```bash
git check-attr -a -- path/to/file
```

View configured filters:

```bash
git config --show-origin --get-regexp '^filter\.'
```

If a filter requires an executable missing on the machine, checkout or staging operations may fail. In that case, install the proper tool and verify filter configuration rather than arbitrarily altering commit contents.

## 8. Which features belong to the hosting service?

Git is a distributed system; a repository itself does not need a central website to create commits, branches, or local merges. Hosting services like GitHub, GitLab, Bitbucket, or self-hosted Git servers add web interfaces and collaboration workflows.

Features that typically belong to hosting:

| Feature | Hosting service's role |
|---|---|
| Pull request / Merge request | Provides a space to propose, review, and discuss changes between branches |
| Branch protection / Rulesets | Enforces conditions before updating protected branches |
| Review approval | Stores comments, approvals, and member review states |
| Issues / Boards | Tracks bugs, requests, and work items |
| CI/CD runners | Provides environments to run pipelines and stores results |
| Secrets / Variables | Stores sensitive configuration data for workflows or runners |
| Webhooks | Sends events to integrated systems when the repository changes |
| Release UI / Assets | Manages release pages and attached binaries |
| Package/Container registry | Stores packages or images published by pipelines and users |
| Access control | Manages members, groups, tokens, deploy keys, and repository permissions |

Some hosting platforms use Git refs and the Git protocol underneath, but reviews, approvals, issues, and policies are normally stored in the service's database. They do not automatically follow when merely mirroring a Git repository to another server.

## 9. Configuration files in the repository vs. features running on hosting

Some hosting features are declared via files stored inside the repository. This makes it easy to mistake the entire feature for a Git capability.

Examples:

- `.github/workflows/build.yml` contains workflow definitions for GitHub Actions.
- `.gitlab-ci.yml` contains pipeline configuration for GitLab CI/CD.
- Other pipeline configuration files may be read by external CI systems.

Git core tracks these files merely as ordinary text files. The hosting or CI service reads the file, provisions runners, supplies secrets, executes jobs, and stores results. If you clone the repository to a machine without that service, the config files still exist, yet pipelines do not run on their own.

Similarly, a `CODEOWNERS` file may be used by the hosting platform to suggest reviewers or enforce review rules. Git core only stores the file content; actual enforcement depends on the platform and repository settings.

## 10. Git protocol does not equal all hosting features

`clone`, `fetch`, and `push` exchange objects and refs between a Git client and server. Success of those operations only proves that the corresponding Git transport works.

Example:

```bash
git clone https://git.example.com/team/project.git
git fetch origin
git push origin feature/login
```

These commands do not automatically open a pull request, request approvals, run CI, or configure branch protection. Those actions require the hosting service's UI, API, webhooks, or automation.

A platform may expose special refs representing pull requests, yet review comments, approvals, checks, and merge states remain platform data. When migrating repositories, you must separately verify how to migrate that platform data.

## 11. Identifying whether an error lies in Git, an extension, or hosting

When an operation fails, categorize by where it executes.

| Symptom | First component to inspect |
|---|---|
| `git status` or `git commit` fails to run | Git client, local repository, index, hooks, or filesystem |
| `git lfs` is not recognized | Git LFS executable and PATH |
| Checkout reports a filter error | `.gitattributes`, filter config, and external tool |
| Clone/fetch reports authentication failed | Credential helper, SSH key/token, and hosting permissions |
| Push rejected due to protected branch | Branch protection rules on the server |
| Pull request does not appear | Hosting UI/API, permissions, and branch state; Git push succeeding is not enough |
| Pipeline does not run | CI config, webhooks, runners, secrets, and CI service status |
| Clone succeeds but LFS files are missing | LFS endpoint, permissions, and LFS objects |
| Submodule fails to check out | Child repository URL, gitlink commit, credentials, and submodule access permissions |

A concise diagnostic workflow:

1. Record the exact command and error message.
2. Determine whether the operation is local, external-tool, or server-side.
3. Check the Git version and required executables.
4. Inspect relevant configuration with `git config --show-origin`.
5. Check remotes and access permissions if the operation requires the server.
6. Check extension or hosting logs once the Git client has completed its step.

Do not share full configuration output or authentication logs publicly without reviewing for tokens, internal URLs, usernames, and sensitive details.

## 12. Checking the Git environment in use

The following commands help identify the toolset on your machine:

```bash
# Git core version.
git --version

# Git commands recognized by this installation.
git help -a

# Git executable location (macOS/Linux/Git Bash).
command -v git

# Check Git LFS if the project uses LFS.
git lfs version

# Configured remotes.
git remote -v

# Configuration with origins.
git config --show-origin --list
```

On PowerShell, use `where.exe git` instead of `command -v git`. `git config --show-origin --list` may reveal private information or internal configurations; share only the necessary parts after reviewing.

If an IDE has its own Git path setting, check which executable the IDE invokes. A machine can have multiple Git installations in PATH or an IDE using its own bundled Git; version differences can cause terminal and IDE behavior to diverge.

## 13. Example workflow involving all three layers

Suppose a team develops an application with source code, large design files, and a review workflow on a hosting platform.

**Step 1 — Git core:** the developer creates a branch, edits code, stages, and commits:

```bash
git switch -c feature/new-checkout
git add src/
git commit -m "feat: add checkout flow"
```

**Step 2 — Extension:** large design files are managed with Git LFS:

```bash
git lfs track "*.psd"
git add .gitattributes assets/checkout.psd
git commit -m "chore: track checkout design with LFS"
```

**Step 3 — Hosting:** push the branch to the server:

```bash
git push -u origin feature/new-checkout
```

Next, the developer opens a pull request or merge request on the hosting platform. The platform runs CI, requires reviews, and enforces branch protection. Once conditions pass, an authorized user merges the changes into the main branch.

In this workflow, Git core creates and transfers commits; Git LFS transfers large contents; hosting manages reviews, policies, and pipelines. If the pipeline fails to run despite a successful push, inspect hosting/CI. If reviewers cannot download the PSD file, inspect LFS. If local commits fail to create, inspect Git core or local hooks.

## 14. Choosing tools according to need

Not every project needs every extension installed or every hosting feature enabled. Choose based on actual needs:

| Need | Appropriate component |
|---|---|
| Tracking changes, branching, merging, and remotes | Git core |
| Working with large binary files | Git LFS or the project's chosen storage solution |
| Storing HTTPS credentials securely | Credential manager/helper |
| Splitting history across multiple working directories | Built-in `git worktree` in Git |
| Checking out only part of a monorepo | Built-in `git sparse-checkout` in Git |
| Reviewing changes and approving | Pull request/merge request on hosting |
| Automated checks before merging | CI service and branch protection |
| Automated notifications or deployments after push | Webhooks, CI/CD, or hosting automation |
| Complex history rewriting | Tools like `git-filter-repo`, under a controlled process |

Before installing a new tool, check whether Git core already provides a command that meets the need, then verify whether the extension is compatible with your Git version and hosting platform. Use tools supported by the project to minimize discrepancies between developer machines and CI.

## 15. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Installing Git includes Git LFS | Git LFS is a separate tool that must be installed and initialized |
| Pull request is a Git core command | Pull request/merge request is a hosting workflow, usually backed by Git refs and APIs |
| Push succeeding means CI ran | Push only updates refs; CI requires its own service, runners, and configuration |
| Branch protection is stored in commits | Branch protection rules belong to server/hosting configuration |
| `.gitlab-ci.yml` is a Git execution feature | Git only tracks the file; GitLab CI reads the file and runs the pipeline |
| A hook is a full Git plugin | Git provides the hook mechanism; the executed script may come from the project or an external tool |
| Every command starting with `git` is built-in | Some are aliases or external subcommands such as `git lfs` |
| Mirroring a repository transfers issues and reviews too | Mirroring transfers Git refs/objects; hosting data requires separate migration |

## 16. Key takeaways

Git core provides the object model, index, refs, working tree, history management commands, and repository transport protocol. Extensions such as Git LFS, credential managers, and history-rewriting tools add workflow capabilities but have their own executables, configs, or services. Hosting services provide reviews, branch protection, CI/CD, issues, access control, webhooks, and server-side collaboration features.

When investigating failures, pinpoint which component performs the operation: Git client, extension, IDE, transport, or hosting. Use `git --version`, `git help -a`, `git remote -v`, `git lfs version`, and `git config --show-origin` to inspect the environment. Understanding these boundaries helps you choose the right tool, consult the right documentation, and avoid expecting a Git command to control features that exist only on the hosting service.

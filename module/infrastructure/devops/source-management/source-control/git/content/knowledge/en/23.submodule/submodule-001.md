# A Submodule Is an Independent Repository Pinned by a Parent Repository at a Specific Commit

Git submodules allow one repository to use the contents of another Git repository as part of a project. The repository containing the submodule is called the **superproject** (parent repository); the embedded repository is the **submodule** (child repository). Both repositories have their own separate history, commits, and remotes, while the parent repository records the exact commit of the child repository that the project is using.

This organization works well when a project depends on an internal library, an independently developed component, or a repository shared across multiple products. The most important point is that the parent repository does not record the entire history of the child repository. Instead, it stores a special reference to a specific commit in the child repository, allowing others to reproduce the exact dependency version that the project was tested against.

## 1. What Is a Submodule?

Suppose the main project has the following structure:

```text
application/
├── src/
├── docs/
└── libs/
    └── shared-utils/   (submodule)
```

The `libs/shared-utils` directory is a separate repository. It has its own branches, commits, and remotes. The `application` repository tracks the submodule's location and the commit it requires.

You can visualize the relationship as follows:

```text
Superproject: application
  commit A
    |
    +-- src/ ...
    |
    +-- libs/shared-utils -> commit S1

Submodule: shared-utils
  commit S0 --- S1 --- S2
                  ^
                  |
          commit pinned by parent repository
```

In this example, the parent repository pins `shared-utils` at commit `S1`, even though the child repository already has a newer commit `S2`. When a team member clones the project, Git checks out `S1` so everyone uses the same dependency version.

Submodules have three key characteristics:

- **Independent repository:** the child repository has its own commit history, branches, tags, and remotes.
- **Pinned commit:** the parent repository stores a specific commit ID of the child repository and does not automatically follow the latest commit on a branch.
- **Declared path:** the parent repository stores the submodule path and repository URL in the `.gitmodules` file.

A submodule is not a copy of files managed directly by the parent repository. When working inside the submodule directory, you are operating on the child repository.

## 2. How Does the Parent Repository Store Submodule Information?

When you add a submodule, Git typically creates or updates two things in the superproject:

1. The `.gitmodules` file, which contains the submodule's name, path, and URL configuration.
2. A **gitlink** entry in the superproject's index/tree, storing the commit ID that the submodule is pinned to.

Example `.gitmodules` file:

```ini
[submodule "shared-utils"]
    path = libs/shared-utils
    url = https://example.com/team/shared-utils.git
```

- `submodule "shared-utils"` is the identifier name of the submodule in the configuration.
- `path` is the subdirectory location within the superproject.
- `url` is the repository address that Git uses to fetch the submodule.

A gitlink entry has a special mode `160000`. You can view it with:

```bash
git ls-tree HEAD libs/shared-utils
```

Example output:

```text
160000 commit 4a7b9c1...    libs/shared-utils
```

This indicates that the superproject records the submodule at commit `4a7b9c1...`. Git does not store the contents of the child directory as a regular file tree in the parent repository's tree; instead, it stores a link to the child repository's commit.

You can view gitlink changes between the index and a commit:

```bash
git diff --submodule
git diff --cached --submodule
```

The first command shows unstaged submodule changes in the superproject; the second shows staged gitlink changes. The `--submodule=log` option can help display the list of child commits between the two revisions:

```bash
git diff --submodule=log
```

The `.gitmodules` file is committed with the superproject so other team members receive the path and URL configuration. The actual configuration for each submodule also has a copy in the parent repository's local configuration, typically in `.git/config`. This explains why when the URL in `.gitmodules` changes, you may need to run `git submodule sync` to update the local configuration.

## 3. Adding a Submodule to a Project

To add a child repository to a project, run:

```bash
git submodule add https://example.com/team/shared-utils.git libs/shared-utils
```

Where:

- The URL is the repository address of the submodule.
- `libs/shared-utils` is the path where the submodule will appear in the superproject.

After running this command, Git creates the submodule directory, clones the child repository, and updates `.gitmodules` along with the gitlink entry in the index.

Inspect the result:

```bash
git status
git submodule status
git diff --cached
```

You will typically see `.gitmodules` and the submodule path appear in the parent repository's status. Stage and commit the superproject changes:

```bash
git add .gitmodules libs/shared-utils
git commit -m "Add shared-utils submodule"
```

This commit stores the submodule configuration and the child commit that the parent repository wants to use. The submodule's own commit history remains inside the child repository.

If the child repository requires authentication, make sure team members have permission to access that URL. An SSH URL only works when the account has an appropriate key configured; an HTTPS URL may require credentials according to server policy.

## 4. Cloning a Repository with Submodules

When cloning a superproject normally:

```bash
git clone https://example.com/team/application.git
cd application
```

Git downloads the parent repository, but the submodules may not yet be initialized. The submodule directory may be empty or not contain any checked-out content.

To download and check out all submodules immediately when cloning, use:

```bash
git clone --recurse-submodules https://example.com/team/application.git
```

If you have already cloned the parent repository earlier, initialize the submodules with:

```bash
git submodule update --init
```

For projects with nested submodules, run recursively:

```bash
git submodule update --init --recursive
```

What these options mean:

- `--init`: initializes the local configuration for submodules that have not yet been initialized.
- `update`: fetches the required contents and checks out the commit pinned by the superproject.
- `--recursive`: performs the same operation on submodules located inside other submodules.

After downloading completes, verify:

```bash
git submodule status --recursive
git status
```

If a submodule requires credentials or its URL is unreachable, the update command will report an error for that submodule. Check the URL in `.gitmodules`, access permissions, and network connectivity before retrying.

## 5. Why Is a Submodule Usually in Detached HEAD?

When you run:

```bash
git submodule update --init
```

Git normally checks out the submodule at the exact commit recorded in the superproject's gitlink. Checking out a specific commit instead of a branch puts `HEAD` in the submodule into a **detached HEAD** state.

This is normal behavior. The parent repository needs to pin an immutable commit so everyone receives the same version; if the submodule automatically followed a moving branch, the same superproject commit could produce different contents depending on when it was cloned.

Check the status inside the submodule:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils branch --show-current
git -C libs/shared-utils rev-parse --short HEAD
```

In detached HEAD state, `git branch --show-current` typically prints no branch name. You can still read files and run tests. If you need to develop new changes inside the submodule, you should create or switch to a branch first:

```bash
git -C libs/shared-utils switch -c fix/parse-edge-case
```

Then edit files, commit, and push inside the child repository following its own workflow. Once the new commit exists, update the superproject's gitlink to pin that commit.

Avoid creating commits in detached HEAD and leaving the submodule without saving the commit with a branch or another ref. The commit may remain in the reflog for a while, but it will be hard to find and may be garbage-collected if no ref points to it.

## 6. Updating a Submodule When the Parent Repository Changes the Pinned Commit

A superproject may be updated to point to a new submodule commit. When you pull or check out a new commit in the parent repository, the gitlink in the superproject may change.

To bring the submodule to the commit recorded by the parent repository, run:

```bash
git submodule update --init --recursive
```

This command checks out the submodule according to the gitlink in the current superproject commit. It does not mean always pulling the latest commit from a submodule branch.

Check the difference between the submodule's state and the commit required by the parent repository:

```bash
git submodule status
git status
```

Common line-prefix symbols in `git submodule status`:

| Symbol | Meaning |
|---|---|
| Space | Submodule is initialized and at the commit recorded by the superproject |
| `-` | Submodule has not been initialized yet |
| `+` | Current commit in the submodule differs from the commit recorded by the superproject |
| `U` | Gitlink has an unresolved conflict |

If you see `+`, inspect the current commit and the parent repository's gitlink before deciding whether to update the superproject or reset the submodule back to the old commit.

## 7. Updating a Submodule According to a Remote Branch

There are two distinct goals:

- Checking out the exact commit that the superproject has pinned.
- Actively updating the submodule to a new commit on a remote branch.

The first goal uses `git submodule update`. The second uses `--remote`:

```bash
git submodule update --remote libs/shared-utils
```

This command fetches from the submodule's remote and updates the submodule working tree according to the configured branch. If `.gitmodules` has a `branch` attribute, Git uses that branch; otherwise, Git uses the default remote branch according to the submodule's configuration.

Example of adding a branch to `.gitmodules`:

```ini
[submodule "shared-utils"]
    path = libs/shared-utils
    url = https://example.com/team/shared-utils.git
    branch = main
```

You can configure this with a command:

```bash
git submodule set-branch --branch main shared-utils
```

After updating from remote, the submodule may move to a newer commit. The superproject does not automatically save that new commit until you stage the gitlink:

```bash
git status
git add libs/shared-utils
git diff --cached --submodule=log
git commit -m "Update shared-utils submodule"
```

The parent repository's commit records the new commit ID. Other team members who then run `git submodule update --init --recursive` will check out that exact pinned commit without having to select a branch themselves.

Do not use `--remote` in reproducible build or deployment pipelines if the requirement is to fetch the exact dependency reviewed in the superproject commit. In those workflows, use the pinned commit; only update from remote when intentionally upgrading the dependency version.

## 8. Modifying Code Inside a Submodule and Updating the Parent Repository

Suppose you need to fix a bug in `shared-utils`. Because it is an independent repository, you must commit the changes in the child repository first:

```bash
# Switch to a working branch in the submodule
git -C libs/shared-utils switch -c fix/null-input

# After editing files
git -C libs/shared-utils status
git -C libs/shared-utils add src/parser.java
git -C libs/shared-utils commit -m "Handle null parser input"
```

If the branch needs to be shared, push the child repository's commit to the remote:

```bash
git -C libs/shared-utils push -u origin fix/null-input
```

Then return to the superproject and stage the submodule path:

```bash
git status
git add libs/shared-utils
git diff --cached --submodule=log
git commit -m "Use shared-utils null input fix"
```

There are two separate commits in this workflow:

1. A commit in `shared-utils` containing the library's code changes.
2. A commit in `application` updating the gitlink to point to the library's new commit.

The order of sharing is critical: push the submodule commit before pushing the superproject commit that references it. If you only push the parent repository while the child commit does not yet exist on a remote accessible to others, they will not be able to fetch the submodule at the pinned commit.

You can inspect the commit recorded by the parent repository:

```bash
git ls-tree HEAD libs/shared-utils
git -C libs/shared-utils log --oneline -5
```

## 9. Updating a Submodule URL

A submodule's URL is declared in `.gitmodules`. When the child repository moves servers or changes addresses, update this file:

```bash
git config -f .gitmodules submodule.shared-utils.url https://example.com/new-team/shared-utils.git
```

Then synchronize the new URL into the submodules' local configuration:

```bash
git submodule sync --recursive
```

Then fetch/update:

```bash
git submodule update --init --recursive
```

Inspect the URL:

```bash
git config -f .gitmodules --get submodule.shared-utils.url
git config --get submodule.shared-utils.url
```

The first command reads the URL stored in the shared `.gitmodules` file; the second reads the local configuration already initialized in the parent repository. After editing `.gitmodules`, commit that file in the superproject so the change is shared with other team members.

Some repositories use relative URLs such as `../shared-utils.git`. Git resolves relative URLs based on the superproject's remote URL. This is useful when multiple repositories live under the same server or organization, though you should check the URL structure before changing the parent repository's remote.

## 10. Checking Status and Troubleshooting Common Issues

Quick inspection commands:

```bash
git status
git submodule status --recursive
git diff --submodule
git -C libs/shared-utils status
git -C libs/shared-utils log --oneline -5
```

| Symptom | Common Cause | Resolution |
|---|---|---|
| Empty submodule directory after cloning | Submodules not yet initialized | Run `git submodule update --init --recursive` |
| `git submodule status` shows `-` | Submodule not initialized | Run `git submodule update --init` |
| Prefix shows `+` | Checked-out commit differs from parent's gitlink | Inspect child commit; run update to return to pinned commit or stage gitlink if intending to upgrade version |
| Submodule is in detached HEAD | Git checked out the commit pinned by superproject | Normal; create a branch if development is needed |
| Failed to fetch submodule | Incorrect URL, network issue, or insufficient permissions | Check `.gitmodules`, run `git submodule sync`, and verify remote authentication |
| Parent repository reports submodule modified | Commit pointer or contents inside submodule changed | Check child repository status and decide whether to update the gitlink |
| Others cannot check out submodule commit | Child commit not pushed to shared remote | Push child repository first, then share superproject commit |
| Nested submodules are missing | Only top-level init/update was run | Use `--recursive` |

When the parent repository reports that a submodule has changed, distinguish between two situations:

- **Commit pointer changed:** the submodule is at a different commit from the gitlink recorded in index/HEAD. This is a change that the superproject can stage with `git add <path>`.
- **Working tree inside submodule changed:** there are modified or untracked files inside the child repository. These changes must be handled and committed inside the child repository; staging only the gitlink in the parent repository will not include child file contents in the parent commit.

You can inspect details with:

```bash
git -C libs/shared-utils status --short
git diff --submodule=log
git diff --cached --submodule=log
```

## 11. Basic Submodule Workflow

A typical collaborative workflow can be summarized as follows:

**When cloning a project:**

```bash
git clone --recurse-submodules https://example.com/team/application.git
```

Or if already cloned:

```bash
git submodule update --init --recursive
```

**When updating the superproject to a new commit:**

```bash
git pull
git submodule update --init --recursive
```

**When modifying submodule code:**

```bash
git -C libs/shared-utils switch -c fix/something
git -C libs/shared-utils add .
git -C libs/shared-utils commit -m "Fix something"
git -C libs/shared-utils push -u origin fix/something

git add libs/shared-utils
git commit -m "Update shared-utils"
git push
```

In this example, `git add .` inside the submodule stages changes within the current directory scope; check `git status` beforehand to ensure you do not add generated files or unwanted data. Committing and pushing the submodule must finish before pushing the superproject.

**When intentionally upgrading a submodule to a remote branch:**

```bash
git submodule update --remote libs/shared-utils
git status
git add libs/shared-utils
git commit -m "Update shared-utils dependency"
git push
```

This workflow updates the gitlink in the parent repository after you review the new commits. If there are code changes inside the submodule, handle them inside the child repository first.

## Conclusion

A submodule is an independent Git repository referenced by a superproject via a gitlink to a specific commit. The `.gitmodules` file stores the path and URL so others know how to fetch the child repository; the gitlink stores the exact version the parent repository uses. Use `git clone --recurse-submodules` or `git submodule update --init --recursive` to initialize, and use `git submodule update` to check out the pinned commit. When modifying child code, commit and push in the child repository first, then stage the gitlink and commit the superproject to share the new dependency version.

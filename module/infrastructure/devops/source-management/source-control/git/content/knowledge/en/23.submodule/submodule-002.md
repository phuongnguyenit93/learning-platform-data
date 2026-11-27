# The Role of .gitmodules, Gitlinks, and Local Configuration

Git submodules allow a repository to reference another Git repository at a subdirectory. The superproject (parent repository) does not store the entire contents of the submodule as regular files; instead, it stores a **gitlink** pointing to a specific commit in the child repository. The `.gitmodules` file records metadata so other clones know which path the submodule resides at and which URL to fetch it from. Each clone also has local configuration in `.git/config` to control how submodules are initialized and updated.

These three components solve three distinct problems: `.gitmodules` describes the submodule for the entire team, the gitlink locks the submodule version that the superproject uses, and the local configuration stores clone-specific choices. Understanding their roles properly helps avoid situations where things work on one machine while a fresh clone fails to find the submodule or checks out the wrong commit.

## 1. Submodule and Superproject

Suppose the `storefront` application uses a `payment-core` library developed in a separate repository. Instead of copying the library code into the application repository, you can add that repository as a submodule:

```text
storefront/
|-- src/
|-- libs/
|   `-- payment-core/    # worktree of the submodule repository
|-- .gitmodules
`-- .git/
```

In this structure:

- `storefront` is the superproject, managing the application code and the pinned location/version of the library.
- `libs/payment-core` is the working tree of the child repository, with its own history, branches, remotes, and configuration.
- `.gitmodules` is a file committed in the superproject to publish the submodule path and URL.
- The gitlink in the superproject's index/tree stores the commit SHA that the application requires from the submodule.
- Local configuration in `.git/config` controls submodule behavior in the current clone.

A superproject commit only records that the path `libs/payment-core` must point to a specific commit. It does not embed the child repository's files into the parent commit. Therefore, when sharing the superproject, the commit referenced by the gitlink must also be reachable from the submodule's remote.

## 2. The Role of the .gitmodules File

`.gitmodules` is a Git-config-formatted file stored and version-controlled in the superproject. Each submodule has a section with an identifier name:

```ini
[submodule "libs/payment-core"]
    path = libs/payment-core
    url = https://git.example.com/platform/payment-core.git
```

The two most important keys:

- `path`: the path of the submodule inside the superproject.
- `url`: the repository address that other clones use to fetch the submodule.

The name in the section, such as `libs/payment-core`, is the **submodule name**. It often matches the path, though it does not have to. A submodule can have a name different from its path:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
```

When the name and path differ, configuration keys use the section name (`payment-library`), whereas `git submodule` commands typically accept the path (`vendor/payment-core`). Read `.gitmodules` instead of guessing the name from the folder.

In addition to `path` and `url`, `.gitmodules` can contain settings such as `branch`, `update`, `ignore`, or `shallow`. For example:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    branch = stable
    update = checkout
    ignore = dirty
```

These settings are shared defaults distributed with the repository. They do not contain the current commit SHA required by the superproject; that commit SHA lives in the gitlink.

### Absolute URLs and Relative URLs

An absolute URL specifies the full host and path:

```ini
url = https://git.example.com/platform/payment-core.git
```

A relative URL can be used when repositories sit alongside each other on the same server:

```ini
url = ../payment-core.git
```

Git resolves relative URLs against the superproject's default remote URL, typically `origin`, rather than a filesystem directory path on disk. This is useful when an organization migrates a group of repositories to another host while preserving their relative layout.

## 3. The Role of the Gitlink

A gitlink is a special entry in the superproject's index and tree. It has mode `160000` and its object ID is the commit SHA of the submodule repository. It is not a normal directory containing child file blobs.

Inspect the gitlink in the current commit:

```bash
git ls-tree HEAD libs/payment-core
```

Sample output:

```text
160000 commit 7f3a91c...    libs/payment-core
```

Inspect the entry in the index:

```bash
git ls-files --stage -- libs/payment-core
```

The output also shows mode `160000`, the object ID, and the path. The SHA here is the commit pinned by the superproject. If the submodule checks out a different commit, Git may report the submodule path as modified because the gitlink in the working tree no longer matches the recorded commit.

For example:

```text
Subproject commit 7f3a91c...   # commit recorded by the superproject
Subproject commit a4d82be...   # commit currently checked out in the submodule
```

When a parent commit is checked out, Git needs to align the submodule to the commit SHA specified by the gitlink. By default, `git submodule update` checks out that commit in a detached `HEAD` state; it does not automatically choose the submodule's latest branch commit.

### A Gitlink Does Not Replace the Submodule Repository

A gitlink only records the commit ID. To inspect the contents of that commit, a machine needs access to the submodule repository and the corresponding commit object. If the child commit has not been pushed to the remote referenced by the superproject, teammates can clone the superproject but will be unable to fetch the required submodule version.

This is why you should push the submodule's commit to its remote before committing the new gitlink in the superproject.

## 4. The Role of Local Configuration in .git/config

When cloning a repository, `.gitmodules` is downloaded along with the superproject. However, Git does not automatically activate and check out all submodules during every normal clone. The `git submodule init` command reads metadata from `.gitmodules` and registers the necessary configuration into the current clone's `.git/config`.

For example, `.gitmodules` contains the section:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = https://git.example.com/platform/payment-core.git
```

After initialization, the local configuration may contain:

```ini
[submodule "payment-library"]
    url = https://git.example.com/platform/payment-core.git
```

This configuration is local to the clone. It typically lives in the superproject's `.git/config` and is not committed along with `.gitmodules`.

Some common local keys:

| Key | Role |
|---|---|
| `submodule.<name>.url` | URL used in the current clone |
| `submodule.<name>.active` | Indicates whether the submodule is active in this clone |
| `submodule.<name>.update` | Local update strategy, if configured |
| `submodule.<name>.ignore` | Controls how status/diff displays submodule changes |

The `<name>` is the section name in `.gitmodules`, not necessarily equal to the path. Local configuration can override certain shared defaults, allowing each developer to use a mirror URL, update strategy, or display behavior suited to their environment.

`submodule.<name>.active` is an optional key to enable or disable a submodule in the current clone; `submodule.active` can use a pathspec to select a group of active submodules. Do not assume `git submodule init` always writes `active = true`: initialization primarily registers the URL and update strategy needed in the local configuration.

### Viewing Submodule Configuration

View shared metadata contents:

```bash
git config -f .gitmodules --get-regexp '^submodule\.'
```

View the local configuration of the current clone:

```bash
git config --local --get-regexp '^submodule\.'
```

View the URL of a single submodule by its section name:

```bash
git config -f .gitmodules --get submodule.payment-library.url
git config --local --get submodule.payment-library.url
```

If the two URLs differ, the local configuration used by the clone may differ from the default URL published in `.gitmodules`. This might be intentional, such as using an internal mirror. When debugging, inspect both sources.

## 5. Initializing and Updating Submodules

When cloning a superproject normally, submodule directories may not yet be initialized. Check with:

```bash
git submodule status
```

A line starting with `-` generally indicates the submodule has not been initialized. To register local configuration:

```bash
git submodule init
```

This command reads `.gitmodules` and writes the necessary configuration to `.git/config`; it does not download the child repository's contents or check out commits. To perform both initialization and updating:

```bash
git submodule update --init
```

If submodules contain nested submodules, use:

```bash
git submodule update --init --recursive
```

Or clone the superproject and initialize all submodules from the start:

```bash
git clone --recurse-submodules https://git.example.com/platform/storefront.git
```

`update` fetches the child repository if needed and checks out the commit SHA recorded by the gitlink. By default, the submodule is typically in detached `HEAD` because the superproject pins a commit rather than a branch name.

### Updating Local URLs When .gitmodules Changes

If the team changes a submodule's URL in `.gitmodules`, existing clones may still hold the old URL in `.git/config`. Resynchronize the local configuration with:

```bash
git submodule sync
git submodule sync --recursive
```

Then update the submodules:

```bash
git submodule update --init --recursive
```

`sync` updates local URLs to match the URLs published in `.gitmodules` for already-initialized submodules. It does not change the gitlink and does not automatically update the submodule to the latest commit on a branch.

## 6. Update Strategies and Branch Settings in .gitmodules

`.gitmodules` can declare a default update strategy:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    update = checkout
```

Common values for `submodule.<name>.update` include:

- `checkout`: checks out the commit specified by the gitlink; this is the default behavior.
- `merge`: merges the commit specified by the gitlink into the submodule's current branch.
- `rebase`: rebases the submodule's current branch onto the commit specified by the gitlink.
- `none`: skips updating the submodule automatically during a general update.

The strategy can be recorded in local configuration or overridden temporarily via update command options. A `!command` configuration may exist in local configuration, but it is not permitted as an arbitrary strategy in `.gitmodules`, preventing a remote repository from instructing another clone to execute arbitrary commands.

The `branch` key is used when you want to fetch the latest commit from a remote branch with `git submodule update --remote`:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    branch = stable
```

Then:

```bash
git submodule update --remote vendor/payment-core
```

This command fetches the submodule's remote and updates the working tree according to the configured branch (`stable` here). It differs from plain `git submodule update`, which checks out the commit pinned in the gitlink. After using `--remote`, the superproject may show the submodule as modified because the checked-out commit now differs from the recorded SHA. To share the new version, stage the gitlink and commit the superproject.

## 7. Understanding Submodule State via git submodule status

Run:

```bash
git submodule status --recursive
```

Example:

```text
-7f3a91c... vendor/payment-core
 a4d82be... vendor/ui-kit
+c18e5d2... vendor/logging
```

Meaning of the leading character:

| Prefix | Meaning |
|---|---|
| `-` | Submodule has not been initialized |
| `+` | Currently checked-out commit differs from the commit recorded by the superproject |
| `U` | Gitlink has a merge conflict |
| No prefix | Submodule is at the recorded commit |

If you see `+`, inspect the current commit in the submodule and the superproject's gitlink:

```bash
git -C vendor/payment-core rev-parse HEAD
git ls-tree HEAD vendor/payment-core
```

If you see `U`, resolve the gitlink conflict by selecting the desired submodule commit, checking out that commit in the submodule, and staging the submodule path in the superproject.

## 8. Changing a Submodule and Updating the Gitlink

Suppose you need to upgrade `payment-core` to a new commit.

First, work inside the child repository:

```bash
git -C vendor/payment-core switch stable
git -C vendor/payment-core pull --ff-only
git -C vendor/payment-core log -1 --oneline
```

After confirming the new commit, return to the superproject and check its status:

```bash
git status
git diff --submodule
```

Git will indicate that the submodule has checked out a different commit from the recorded gitlink. To update the gitlink in the index:

```bash
git add vendor/payment-core
git diff --cached --submodule
```

Then commit the change in the superproject:

```bash
git commit -m "Update payment-core submodule"
```

This commit only updates the gitlink SHA and any metadata such as `.gitmodules` if changed. It does not automatically commit contents inside the child repository.

**Before pushing the superproject, push the submodule's new commit to its remote.** Otherwise, teammates may receive a gitlink pointing to a commit that the submodule remote does not provide.

For example:

```bash
git -C vendor/payment-core push origin stable
git push origin main
```

Ensure the remote branch and access permissions match the project's configuration. In some workflows, submodule commits may be pushed by a pipeline or maintainer; the essential requirement is that the child commit is reachable before the new gitlink is shared.

## 9. Modifying .gitmodules and Local Configuration

When you want to change the default URL for the entire team, edit `.gitmodules` and commit the file:

```bash
git config -f .gitmodules submodule.payment-library.url https://git.example.com/platform/payment-core.git
git add .gitmodules
git commit -m "Update payment-core submodule URL"
```

After pulling the change, clones that already initialized the submodule need to synchronize their local URL:

```bash
git submodule sync --recursive
```

If only one developer wants to use a personal mirror, they can change the local URL without editing `.gitmodules`:

```bash
git config --local submodule.payment-library.url https://mirror.example.net/payment-core.git
```

This local change is not committed and takes effect only in the current clone. If `git submodule sync` is run later, the local URL may be synchronized back to `.gitmodules`.

Do not put tokens or passwords directly into URLs committed to `.gitmodules`. Use a credential manager or your environment's secure authentication mechanism.

## 10. Common Misconceptions

| Misconception | Reality |
|---|---|
| `.gitmodules` stores the submodule's commit SHA | `.gitmodules` records name, path, URL, and settings; the SHA is in the tree/index gitlink |
| A gitlink contains all files of the submodule | A gitlink only stores mode `160000` and a commit SHA |
| `git submodule init` downloads the child repository | `init` registers local configuration; `update` fetches and checks out the required content |
| `git submodule update` fetches the latest commit on a branch | By default, it checks out the exact commit pinned by the gitlink |
| Changing the URL in `.gitmodules` updates every clone automatically | Already-initialized clones need `git submodule sync` to synchronize local config |
| Committing the superproject saves new submodule commits | You must commit inside the submodule, push that commit, then stage and commit the gitlink in the superproject |
| `.git/config` is shared with teammates | It is local configuration for each clone and is not committed with the repository |

## 11. Hands-on Exercise

In two test repositories, create a superproject and a separate library repository. Do not use a production repository for this exercise.

1. Use `git submodule add` to add the library to the superproject, then read `.gitmodules`.
2. Run `git ls-files --stage` and `git ls-tree HEAD` after committing to locate the mode `160000` gitlink entry.
3. Run `git config -f .gitmodules --get-regexp '^submodule\.'` and `git config --local --get-regexp '^submodule\.'` to compare shared metadata with local configuration.
4. Clone the superproject into a new directory, run `git submodule status`, and then use `git submodule update --init --recursive` to initialize the submodule.
5. Change the URL in `.gitmodules`, pull the change into the other clone, and use `git submodule sync` to update the local URL.
6. Create a new commit in the child repository, push it to its remote, stage the gitlink in the superproject, and commit the change.
7. Explain why `.gitmodules`, the gitlink, and `.git/config` serve different roles.

You have completed the exercise when you can determine where a submodule is fetched from, which commit the superproject pins, which configuration is shared, and which configuration exists only in the current clone.

# Cloning with Submodules Using `--recurse-submodules`

A repository can use other Git repositories as dependent components through submodules. When cloning a parent repository the regular way, Git downloads the parent repository's history without automatically downloading submodule contents. If you forget the initialization step, submodule directories may appear without any source code inside. The `git clone --recurse-submodules` option clones the parent repository, initializes submodules, and downloads nested submodules at the commits recorded by the parent repository.

## 1. How Are Submodules Stored in the Parent Repository?

A submodule is an independent Git repository mounted at a path inside the parent repository, commonly called the *superproject*. The parent repository does not store all files of the submodule as ordinary files. Instead, Git stores a special entry in the tree called a **gitlink**, pointing to a specific commit ID in the child repository.

The `.gitmodules` file in the superproject records basic configuration for submodules, usually including name, path, and URL:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = https://git.example.com/team/shared-library.git
```

- `path` is the submodule's location inside the superproject's working tree.
- `url` is the repository address Git uses to fetch the submodule.
- The section name (`shared-library`) is the submodule's configuration name, commonly used in Git commands and settings.

The superproject's commit records the gitlink, which is the specific commit that the submodule must check out. Thus, `.gitmodules` tells Git where to fetch which repository, while the gitlink tells Git which version to use.

For example, the superproject might record:

```text
project/
  .gitmodules
  src/
  libs/
    shared-library/   -> commit 8f31c2a of the child repository
```

The commit pinned in the gitlink ensures everyone cloning the same superproject receives the same submodule version, rather than automatically pulling the latest commit on the child repository's default branch.

## 2. How Does a Regular Clone Differ from Cloning with Submodules?

Suppose the parent repository contains `libs/shared-library` as a submodule.

Regular clone:

```bash
git clone https://git.example.com/team/application.git
```

This command clones the superproject. Submodules are not initialized or downloaded yet; the corresponding paths may remain empty or lack the child repository's working tree.

Cloning with all submodules:

```bash
git clone --recurse-submodules https://git.example.com/team/application.git
```

`--recurse-submodules` instructs Git to initialize and update submodules after cloning the superproject. Git downloads the child repository, checks out the exact commit recorded in the gitlink, and then continues processing nested submodules.

You can specify a destination directory:

```bash
git clone --recurse-submodules https://git.example.com/team/application.git application
```

This command creates the `application` directory and places the superproject along with its submodules inside it.

## 3. What Steps Does Git Perform During a Recursive Clone?

Conceptually, `git clone --recurse-submodules` follows this sequence:

1. Clones the parent repository and checks out the selected branch or commit.
2. Reads the submodule declarations in `.gitmodules` of the newly checked-out commit.
3. Initializes the required submodule configuration in the local repository.
4. Clones or fetches the data for each child repository.
5. Checks out each submodule to the commit required by the superproject's gitlink.
6. Continues initializing and updating submodules inside those submodules when recursion is requested.

Therefore, this command does not only fetch URLs listed at the top level. When nested submodules exist, `--recurse-submodules` continues processing inner levels as well.

## 4. Choosing a Superproject Branch When Cloning

You can combine `--branch` to choose a branch or tag of the parent repository:

```bash
git clone --recurse-submodules --branch release/2.4 https://git.example.com/team/application.git application
```

Git checks out `release/2.4` of the superproject and then fetches submodules according to the gitlinks in that branch's commit. `--branch` selects the parent repository's revision; it does not tell each submodule to check out a branch with the same name or its latest branch.

This point is important when a project spans multiple versions of a child library. The submodule's `main` branch may have moved many commits ahead, while the superproject still pins an older tested commit. Recursive cloning preserves that exact pinned commit.

## 5. Submodules Are Usually in Detached HEAD State

After a recursive clone, inspect a submodule:

```bash
cd application/libs/shared-library
git status -sb
git branch --show-current
git rev-parse HEAD
```

Submodules are usually in **detached HEAD** state because Git directly checks out the commit recorded by the superproject rather than checking out a local branch of the child repository. In detached HEAD, `git branch --show-current` normally returns empty output.

This is a normal state. It guarantees the submodule is at the exact version required by the superproject. If you need to develop inside the submodule, explicitly check out a branch:

```bash
git switch -c feature/library-change
```

After committing changes in the submodule, the parent repository will see the gitlink pointing to a new commit. You must commit the gitlink change in the superproject if you want to share the new submodule version with others.

## 6. Verifying Submodules After Cloning

Return to the root directory of the superproject and check:

```bash
cd application
git status
git submodule status --recursive
```

`git submodule status --recursive` lists the commit each submodule currently has checked out, including nested submodules. The leading character helps identify the state:

| Leading Character | Meaning |
|---|---|
| Space | Submodule has checked out the exact commit recorded by the superproject |
| `-` | Submodule has not been initialized |
| `+` | Submodule has checked out a commit different from the one recorded in the superproject's index |
| `U` | Gitlink is in a conflict state |

With a successful recursive clone, active submodules typically appear with a leading space and a commit ID matching the gitlink. If you see `-`, the submodule has not been downloaded or initialized. If you see `+`, check whether someone checked out or committed a different version inside the submodule.

You can inspect submodule configuration in the superproject:

```bash
git config --file .gitmodules --get-regexp '^submodule\..*\.(path|url)$'
```

This command lists pairs of submodule names with `path` and `url`. If you need to inspect the contents of an individual submodule, use `git -C` to run commands at the corresponding path without changing directories:

```bash
git -C libs/shared-library status -sb
git -C libs/shared-library log -1 --oneline
```

## 7. When a Repository Was Cloned Without `--recurse-submodules`

You do not need to re-clone the entire superproject. From the parent repository root, run:

```bash
git submodule update --init --recursive
```

- `init` initializes local configuration for submodules that have not yet been initialized.
- `update` downloads and checks out the commit recorded in the gitlink.
- `--recursive` applies the same process to nested submodules.

This command is the standard way to complete the submodule setup after a regular clone. If you only want to initialize one specific submodule, you can pass its path:

```bash
git submodule update --init libs/shared-library
```

If that submodule contains nested submodules, add `--recursive`:

```bash
git submodule update --init --recursive libs/shared-library
```

When you need to fully restore all submodules to the commits recorded by the superproject, use the unrestricted command shown at the start of this section.

## 8. Useful Clone Options When a Repository Has Many Submodules

### 8.1. Cloning Submodules in Parallel with `--jobs`

Large repositories with many submodules can take time if downloaded sequentially. Use `--jobs` to control how many submodules are fetched concurrently:

```bash
git clone --recurse-submodules --jobs 4 https://git.example.com/team/application.git application
```

Git can fetch up to the specified number of submodules simultaneously. An appropriate value depends on network bandwidth, machine resources, and Git server load.

### 8.2. Shallow Cloning Submodules with `--shallow-submodules`

If you do not need the full history of child repositories, you can use:

```bash
git clone --recurse-submodules --shallow-submodules https://git.example.com/team/application.git application
```

`--shallow-submodules` causes submodules to be cloned with depth 1. This reduces the history downloaded, though it limits inspecting older logs, finding ancestor commits, or developing against deep submodule history.

You can combine it with a shallow clone of the superproject:

```bash
git clone --depth 1 --recurse-submodules --shallow-submodules https://git.example.com/team/application.git application
```

`--depth 1` limits the superproject's history; `--shallow-submodules` applies shallow cloning to submodules. The two options control different parts of the repository.

### 8.3. Being Careful with `--remote-submodules`

By default, a recursive clone checks out the submodule commit recorded in the superproject's gitlink. The `--remote-submodules` option changes how updates work: submodules use the state of their remote-tracking branch instead of the commit SHA recorded by the superproject.

```bash
git clone --recurse-submodules --remote-submodules https://git.example.com/team/application.git application
```

For projects requiring reproducible builds, make sure you understand the difference before using this option. Fetching the latest remote state can cause the cloned result to differ from the submodule version pinned and tested by the superproject. Do not use `--remote-submodules` as a default when the goal is to reproduce the exact state of a superproject commit.

## 9. Troubleshooting Errors When Cloning Submodules

Cloning the superproject may succeed while fetching submodules fails. Some common causes:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `Repository not found` | Incorrect submodule URL or account lacks read permission | Check `url` in `.gitmodules` and child repository permissions |
| `Authentication failed` or `Permission denied (publickey)` | Incorrect or missing HTTPS/SSH credentials | Verify tokens, SSH keys, and accounts for each child repository |
| `Could not resolve host` or timeout | DNS, VPN, proxy, or network connectivity | Check hostname, network, and proxy settings |
| Empty or uninitialized submodule directory | Cloned without recurse or submodule step was interrupted | Run `git submodule status`, then `git submodule update --init --recursive` |
| `fatal: remote error: upload-pack: not our ref` | Server does not provide the commit requested by the gitlink, or commit is no longer reachable | Verify the gitlink and child repository history with a maintainer |

An account might have read access to the superproject without having read access to every submodule. Verify permissions for each URL in `.gitmodules`, especially when child repositories belong to different groups or organizations.

If a submodule URL has been updated in `.gitmodules`, synchronize the URL into local config and update again:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

`sync` updates URLs in the submodule's local configuration to match the URL declared in `.gitmodules`. It does not modify `.gitmodules` itself; if the URL in that file is wrong, fix the configuration source and commit the change in the superproject first.

## 10. Understanding Relative URLs in `.gitmodules`

`.gitmodules` can use absolute URLs:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = https://git.example.com/team/shared-library.git
```

Or relative URLs:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = ../shared-library.git
```

Git resolves relative URLs against the superproject's default remote URL, usually the remote used for cloning. They are not resolved relative to the current local working directory. For instance, if the superproject's URL is `https://git.example.com/team/application.git`, the URL `../shared-library.git` typically resolves to `https://git.example.com/team/shared-library.git`.

Relative URLs are helpful when multiple repositories reside under the same group or namespace and may be mirrored to another host. However, if the superproject is cloned from a mirror with a different layout, verify that URLs resolve properly before cloning submodules.

## 11. Recursive Cloning in Projects with Nested Submodules

A submodule can contain its own `.gitmodules` and declare further submodules. For example:

```text
application/                       superproject
  .gitmodules
  libs/
    shared-library/                level-1 submodule
      .gitmodules
      vendor/
        codec/                     level-2 submodule
```

If you only fetch top-level submodules without recursion, `vendor/codec` may remain uninitialized. `--recurse-submodules` instructs Git to continue processing nested levels. When checking, use:

```bash
git submodule status --recursive
```

When a nested submodule fails to download, identify which level's repository owns the `.gitmodules` file and verify the URL from that exact level. A nested submodule's relative URL is resolved against the remote of the repository containing that submodule declaration.

## 12. How to Update Submodules After Cloning

Normally, when a teammate updates the superproject to point to a new submodule commit, you simply update the superproject and synchronize submodules:

```bash
git pull
git submodule update --init --recursive
```

The second command brings submodules to the exact commit recorded in the updated superproject version. If your team configures pull with rebase or merge, `git pull` follows that setting; understand the repository's pull policy before running it.

Do not confuse this operation with:

```bash
git submodule update --remote
```

`--remote` instructs Git to fetch the latest state from the submodule's configured remote-tracking branch instead of checking out the pinned gitlink commit. Using it may produce a new gitlink in the superproject, requiring review and committing as a dependency update.

## 13. Recommended Clone Workflow for New Team Members

When onboarding to a repository with submodules, follow this sequence:

1. Confirm Git is installed and you have read access to the superproject and all child repositories.
2. Read the project documentation for rules on HTTPS/SSH protocols, VPN, or credentials.
3. Clone with `--recurse-submodules`:

   ```bash
   git clone --recurse-submodules <repository-url> <directory>
   ```

4. Inspect the submodule list:

   ```bash
   git submodule status --recursive
   ```

5. Inspect the working tree of the superproject and submodules:

   ```bash
   git status --short
   git submodule foreach --recursive 'git status --short'
   ```

6. Verify submodules are at the exact commits required by the superproject; if you see `-`, `+`, or `U` states, resolve the cause before building.
7. Run build/test steps per project instructions once all dependencies are ready.

If you already cloned without submodules, run `git submodule update --init --recursive` from the superproject root to complete the setup.

## 14. Common Misconceptions

- **Assuming cloning the superproject automatically downloads all child repositories.** You need `--recurse-submodules` or must run `git submodule update --init --recursive` afterward.
- **Assuming submodules automatically check out the latest default branch.** By default, Git checks out the commit recorded in the gitlink.
- **Assuming `--branch` selects a branch for submodules too.** This option selects the branch or tag of the superproject.
- **Treating detached HEAD in a submodule as an error.** This is the normal state when a submodule is checked out at its pinned commit.
- **Checking only top-level submodules.** Use `--recursive` with update and status to include nested levels.
- **Assuming read access to the superproject implies read access to submodules.** Each URL can have its own access policy.
- **Using `--remote-submodules` without understanding the consequences.** This option changes commit selection and can break gitlink-based reproducibility.
- **Editing a URL in `.gitmodules` but forgetting to sync local config.** Run `git submodule sync --recursive` and then update again.

## 15. Key Takeaways

`git clone --recurse-submodules` clones the superproject, initializes and fetches submodules at the gitlink commits recorded by the superproject, and handles nested submodules. `.gitmodules` specifies paths and URLs; gitlinks determine which commits to check out. After cloning, verify with `git submodule status --recursive`, remember that detached HEAD is normal, and ensure you have access permissions for each child repository. If a clone missed submodules or fetching was interrupted, you can finish the setup with `git submodule update --init --recursive`.

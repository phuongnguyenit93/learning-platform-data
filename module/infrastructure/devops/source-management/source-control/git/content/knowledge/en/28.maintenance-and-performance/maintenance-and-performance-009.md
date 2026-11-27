# Bare repositories, mirror clones, and the meaning of mirror push

Git can store a repository without a working tree. This type of repository is called a **bare repository** and is commonly used as a central remote for multiple people to push to and fetch from. Another use case is creating a **mirror clone** to replicate Git refs and objects from a source repository. When syncing that copy to a destination, `git push --mirror` updates all refs, including overwriting or deleting refs at the destination.

These three concepts are related but not synonymous: bare describes a repository structure without a working tree; mirror clone describes how a repository is cloned and how refs are mapped; mirror push describes the scope of ref updates pushed to a remote. Understanding the differences helps you set up shared remotes, build backup replicas, and avoid accidentally deleting branches or tags on a server.

## 1. What is a bare repository?

A standard repository has a working tree, an index, and a Git metadata directory. You check out branches, edit files, stage, and commit inside that working tree. A bare repository contains only the core Git data—such as the object database, refs, and repository configuration—without a working tree for editing files in the usual way.

Simplified layout example:

```text
Standard repository                Bare repository
project/                           project.git/
|-- .git/                           |-- objects/
|   |-- objects/                    |-- refs/
|   |-- refs/                       |-- HEAD
|   `-- HEAD                        |-- config
|-- src/                            `-- ...
`-- README.md
```

In a standard repository, the `.git` directory holds metadata and the object database. In a bare repository, those contents sit directly at the root of `project.git`; there is no nested `.git` folder and no project files checked out into a working tree.

Bare repositories are well suited as remotes receiving pushes because the server does not need a branch checked out into a working tree. When clients push commits, Git updates the object database and refs inside the bare repository. Other users then fetch those refs into their own clones.

A bare repository does not automatically become a network service. It is simply a repository on disk; for others to access it, you must expose it over SSH, the Git protocol, HTTP(S), or an appropriate hosting mechanism and configure access permissions.

## 2. Creating a bare repository as a central remote

Create a new bare repository:

```bash
git init --bare --initial-branch=main /srv/git/storefront.git
```

`--bare` creates a repository with no working tree. `--initial-branch=main` sets the initial default branch to `main` on Git versions supporting that option. If your Git version does not support it, initialize the repository and set symbolic `HEAD`:

```bash
git init --bare /srv/git/storefront.git
git --git-dir=/srv/git/storefront.git symbolic-ref HEAD refs/heads/main
```

From a working repository, add the remote and push a branch:

```bash
git remote add origin ssh://git@git.example.com/srv/git/storefront.git
git push -u origin main
```

After pushing, the bare repository has `refs/heads/main` pointing to the pushed commit. Other teammates can clone it:

```bash
git clone ssh://git@git.example.com/srv/git/storefront.git
```

If multiple people share a bare repository, manage write permissions, SSH authentication, backups, and server-side hooks. Do not grant unrestricted write access to the repository directory; filesystem permissions and push-acceptance policies should match your deployment model.

### Inspecting a bare repository

If you are inside a bare repository, check:

```bash
git rev-parse --is-bare-repository
git show-ref
git symbolic-ref HEAD
```

A result of `true` confirms the current repository is bare. `show-ref` lists existing refs; `symbolic-ref HEAD` reports the default branch the bare repository's `HEAD` points to, if it is a symbolic ref.

You can also run commands from outside the directory by specifying the Git directory:

```bash
git --git-dir=/srv/git/storefront.git show-ref
```

Do not use `git switch` or `git checkout` to create a working tree inside a bare repository. Clone the repository into a standard working directory if you need to edit files.

## 3. Distinguishing git clone --bare and git clone --mirror

Both options create a repository without a working tree, but their ref scopes and configurations differ.

### `git clone --bare`

```bash
git clone --bare https://git.example.com/platform/storefront.git storefront-bare.git
```

This command creates a bare clone. Branch heads are copied directly as branch refs in the destination repository instead of creating remote-tracking branches as in a normal clone. A bare clone creates no working tree and does not configure full-ref mirroring behavior.

This is the right choice when you want a bare repository to store or serve standard branches. If the goal is to copy every ref advertised by the remote—including refs beyond standard branches and tags—look at `--mirror`.

### `git clone --mirror`

```bash
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

`--mirror` implies bare mode and configures the repository to mirror refs. Instead of fetching only standard branch heads and tags, it maps the entire `refs/*` namespace advertised by the remote into the same namespace locally. A mirror clone typically has configuration similar to:

```ini
[remote "origin"]
    url = https://git.example.com/platform/storefront.git
    fetch = +refs/*:refs/*
    mirror = true
```

The refspec `+refs/*:refs/*` maps refs from the remote to the exact same ref names in the mirror repository. The `+` allows updating refs even when non-fast-forward. The mirror setting also affects default push behavior toward that remote; therefore, check remotes before running push commands inside a mirror clone.

### Comparison table

| Criterion | Normal clone | `--bare` | `--mirror` |
|---|---|---|---|
| Has working tree | Yes | No | No |
| Has local branches and standard remote-tracking branches | Yes | Does not create standard remote-tracking branches | Does not map as remote-tracking; refs are placed in the same namespace |
| Fetches branches and tags | According to clone/fetch config | Branch heads and standard refs per bare-clone rules | All refs advertised by the remote within mirror scope |
| Configures fetch `+refs/*:refs/*` | No | Not by default | Yes |
| Serves as a full-ref mirror replica | Not the default purpose | Less complete than mirror | Yes |

Do not treat `--bare` and `--mirror` as interchangeable aliases. When backing up or replicating a repository by refs, `--mirror` states your intent clearly.

## 4. What does a mirror clone synchronize?

A mirror clone fetches the refs the remote allows the client to see and the Git objects reachable from those refs. Those refs may include:

- Branches under `refs/heads/`.
- Tags under `refs/tags/`.
- Notes, replace refs, or other custom namespaces if advertised by the server.
- Platform-specific workflow refs if permitted to be advertised over the protocol.

Because a mirror clone maps `refs/*`, it can retain refs outside `heads` and `tags` that a standard clone would not map into remote-tracking branches. However, a server may hide certain refs through configuration or hosting policy. A mirror cannot copy refs that the remote does not advertise or permit access to.

Inspect refs in a mirror clone:

```bash
git show-ref
git for-each-ref --format="%(refname) %(objectname)"
```

The second command lists ref names and OIDs for comparison against the source. If you need to check remotely, use:

```bash
git ls-remote --refs origin
```

`ls-remote` only displays refs advertised by the remote; it does not download objects locally.

## 5. Updating a mirror clone from the source

After creating a mirror clone, branches or tags at the source may change. To update refs in the mirror, fetch from the source remote:

```bash
git fetch --prune origin
```

Because a mirror clone has the refspec `+refs/*:refs/*`, fetching updates refs according to the configured namespace. `--prune` deletes local refs covered by the fetch refspec if they no longer exist on the remote, keeping the mirror aligned with ref deletions at the source.

You can inspect configuration before fetching:

```bash
git config --get-all remote.origin.fetch
git config --get remote.origin.mirror
```

With a mirror clone, do not assume a fetch behaves with the same scope as in a normal clone. Inspect the actual refspec to see which refs will be updated.

If there are multiple remotes or remote groups, `git remote update` can fetch multiple sources according to configuration. In a single-source mirror workflow, explicitly specifying `origin` keeps the scope bounded and easier to control.

## 6. What does git push --mirror mean?

The command:

```bash
git push --mirror <remote>
```

instructs Git to synchronize all refs under the local repository's `refs/` namespace to the destination remote. Its behavior includes three critical actions:

1. **Create new refs:** refs present locally but absent on the remote are created.
2. **Force-update existing refs:** destination refs can be moved to the local OID even when the update is non-fast-forward.
3. **Delete refs on the remote:** refs present on the remote that no longer exist locally are deleted.

Therefore, mirror push is not just pushing all branches. It can update tags, notes, and other ref namespaces while deleting any refs missing from the local mirror.

Example:

```bash
git push --mirror backup
```

This command is appropriate when `backup` is a destination repository managed as a mirror of the source. Do not use it casually against a remote holding independent branches or tags you want to preserve.

### Why can mirror push be dangerous?

Suppose the destination remote has three refs:

```text
refs/heads/main
refs/heads/release
refs/tags/v1.0
```

Meanwhile, the local mirror has only `main` and tag `v1.0`. Running `git push --mirror` can delete `refs/heads/release` on the remote because it does not exist in the local mirror. If local `main` had history rewritten, remote `main` can also be force-updated.

Therefore, before running a mirror push:

- Confirm the exact destination remote and repository.
- Inspect both local and remote refs.
- Confirm the destination is dedicated to mirroring or everyone agrees all destination refs must match the source.
- Check branch protection, ref deletion permissions, and hosting policies.
- Maintain backups or recovery paths in case a mirror push unexpectedly overwrites or deletes refs.

Do not use `git push --mirror` to update a few branches. For normal needs, use `git push origin main` or an explicit refspec to limit scope.

## 7. Workflow for creating and updating a backup mirror

Suppose the source repository is `origin` and you want to maintain a bare mirror on a backup server.

### Initial mirror clone setup

```bash
git clone --mirror https://git.example.com/platform/storefront.git storefront-mirror.git
```

This clone already has an `origin` remote pointing to the source. Add the backup remote:

```bash
cd storefront-mirror.git
git remote add backup ssh://git@backup.example.com/srv/git/storefront.git
```

The destination repository `storefront.git` should be created as bare and dedicated to the mirror. If it does not exist yet:

```bash
ssh git@backup.example.com 'git init --bare /srv/git/storefront.git'
```

Remote initialization requires shell access and appropriate directory write permissions. If your backup platform already provisioned a bare repository, there is no need to re-initialize it.

Push all local refs to backup:

```bash
git push --mirror backup
```

### Periodic mirror updates

On each synchronization cycle:

```bash
git fetch --prune origin
git push --mirror backup
```

The fetch updates the local mirror from the source and deletes local refs removed at the source according to the refspec. Mirror push then synchronizes local refs to the destination, including deleting destination refs no longer present locally.

If automating this, run the workflow in a job with read access to the source and write access to the backup, with logging, failure alerts, and run history. Avoid letting multiple mirror-push jobs write concurrently to the same destination repository without coordination.

### Post-sync verification

Compare refs:

```bash
git ls-remote --refs origin
git ls-remote --refs backup
git show-ref
```

Results should match your mirror policy. Some hosting platforms may reject internal or protected refs; in those cases, a mirror cannot be treated as complete without explicitly accounting for those differences.

## 8. Caution with remote.origin.mirror in a mirror clone

Mirror clones typically configure:

```ini
remote.origin.mirror = true
```

This setting tells Git that the remote is treated as a mirror for push behavior. Consequently, inside a mirror clone, never run `git push` without specifying a remote unless you have checked the default push configuration and target remote. Otherwise you risk mirror-pushing backward into the source repository.

Check configuration:

```bash
git remote -v
git config --show-origin --get-regexp '^remote\..*\.(url|mirror|fetch)$'
git config --get push.default
```

In a backup workflow, specify the destination remote explicitly:

```bash
git push --mirror backup
```

Do not edit `remote.origin.mirror` unless you understand its effect on mirror-clone fetch/push behavior. If you need a repository for another purpose, create a separate standard clone for daily work.

## 9. How bare remotes, mirror backups, and working clones differ

| Purpose | Suitable repository type | Reason |
|---|---|---|
| Central remote receiving pushes from multiple developers | Bare repository | No checked-out working tree; suited to receiving ref updates |
| Replica of refs/objects from another remote | Mirror clone | Maps all advertised refs and supports mirror push |
| Where developers edit files and commit | Standard clone | Has working tree, index, and working branches |
| Copy fetching only selected branches | Standard or bare clone with tailored refspec | No need to sync every ref namespace |

A bare repository can serve as a central remote without mirroring any other repository. Conversely, a mirror clone is also a bare repository, but configured with refspec and mirror settings to replicate refs from a source.

## 10. A mirror is not a full backup of a hosting service

`git clone --mirror` copies the Git refs and objects advertised and accessible on the remote. It does not automatically back up all data and settings of a hosting platform.

Components that may require separate backups include:

- **Pull requests/merge requests, issues, reviews, and comments:** typically stored in the hosting service's database.
- **Releases, artifacts, and attachments:** may be stored outside the Git object database.
- **Hooks, branch protection, access permissions, and deploy keys:** server-side configuration not copied by a mirror clone.
- **Reflogs:** local logs, not a ref namespace synchronized by mirror push.
- **Git LFS objects:** pointers live in Git, while LFS content resides at a separate endpoint. Appropriate Git LFS commands are required to download and push all LFS objects—such as `git lfs fetch --all origin` and `git lfs push --all backup`—after verifying endpoints and permissions.
- **Submodule repository contents:** the superproject stores only gitlink commit SHAs. Each submodule repository must be mirrored and backed up separately.
- **Hidden refs or refs not advertised by the server:** mirror clones cannot retrieve refs the server does not permit access to.
- **Default HEAD and repository config:** `HEAD` is a symbolic ref at the repository root rather than under `refs/`, so `git push --mirror` does not synchronize the default branch of a bare destination. Configure `HEAD` at the destination separately, and back up server config and hooks if you need to recreate the environment.

Therefore, clarify whether your backup target is the Git repository alone or the entire software development service. For comprehensive recovery capability, combine Git mirroring with backups of databases, hosting configuration, LFS storage, artifacts, and submodule repositories.

## 11. Notes on permissions, ref protection, and data safety

- **Use a dedicated destination for mirroring.** Never mirror-push into a repository containing personal branches or refs not originating from the source.
- **Limit write permissions.** Synchronization accounts should hold only the necessary permissions on the backup repository.
- **Protect the source.** A mirror clone is a replica; do not use it as a working clone for development or push back to the source.
- **Verify URLs.** Check `git remote -v` before every push to avoid mixing up source and destination.
- **Consider branch protection.** Servers may reject force updates or deletions of protected refs. Do not disable protection solely to make a mirror push succeed without proper approval.
- **Keep sync logs.** Record timestamps, source, destination, changed refs, and errors to investigate backup inconsistencies.
- **Test recoverability.** Periodically clone from the backup into a test directory and verify required branches, tags, and commits.

Mirror push synchronizes ref state; it is not an append-only operation. If a branch or tag is accidentally deleted on the source and then mirror-pushed, the backup can delete it as well. If you need backups capable of preserving history deleted from the source, maintain immutable point-in-time snapshots/backups alongside a continuously updated mirror.

## 12. Hands-on exercises

In a test environment, create a source repository containing a `main` branch, a `feature/demo` branch, a `v1.0` tag, and a custom ref if you know how to create one. Do not use production remotes for this exercise.

1. Create a bare repository using `git init --bare` and push branches to it.
2. Create a clone using `git clone --bare` and inspect refs with `git show-ref`.
3. Create another clone using `git clone --mirror`, and inspect `remote.origin.fetch` and `remote.origin.mirror`.
4. Create a dedicated bare destination repository for backup and add it as the `backup` remote in the mirror clone.
5. Run `git push --mirror backup`, then compare `git ls-remote --refs` between source and destination.
6. Delete a test branch at the source, run `git fetch --prune origin` in the mirror clone followed by `git push --mirror backup`; observe the corresponding branch being deleted at the destination.
7. Create a custom ref only on the destination in the test repository, then observe why the next mirror push can delete that ref.
8. List the hosting, LFS, and submodule data that a Git mirror does not back up automatically.

You have completed the exercise when you can explain how a bare repository serves as a remote, how `--bare` differs from `--mirror`, and why `git push --mirror` can create, overwrite, and delete refs on the destination remote.

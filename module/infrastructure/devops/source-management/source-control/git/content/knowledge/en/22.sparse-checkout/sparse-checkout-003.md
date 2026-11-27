# Extending history with --deepen and --unshallow

A repository cloned with a depth limit (shallow clone) contains only part of the commit history of the fetched branch. This cloning approach reduces download time and storage when you only need the latest source code, but it can lead to missing information when viewing history, finding a merge base, running bisect, or performing certain integration operations.

When you need more history, Git provides two important fetch options: `--deepen=<n>` downloads an additional number of commits from the current shallow boundary; `--unshallow` requests fetching all remaining available history from the remote. These two options add historical data into the existing repository without having to re-clone from scratch.

## 1. What is a shallow clone?

In a full clone, Git can access the commit history of fetched branches and tags, starting from the existing commits all the way back to their ancestors. In a shallow clone, Git downloads only a portion of the history and marks the commits at the boundary where history is truncated.

For example, cloning a repository with a depth of one commit:

```bash
git clone --depth=1 https://git.example.com/platform/payment-service.git
```

This command fetches the latest commit of the cloned branch along with the data needed to check it out. History prior to that commit has not been downloaded in full. When using `--depth`, Git defaults to cloning only a single branch (`--single-branch`), unless you specify `--no-single-branch`.

Check whether the repository is a shallow clone:

```bash
git rev-parse --is-shallow-repository
```

Output:

```text
true
```

indicates the repository still has a shallow limit. If the result is `false`, the repository is no longer in a shallow state.

You can also view the available history:

```bash
git log --oneline --graph --decorate --all
```

In a shallow clone, history can stop at the shallow boundary even though the actual commit on the remote still has older ancestors. Git records these boundaries in repository metadata, typically via the `shallow` file inside the Git directory. Do not edit this metadata file manually; use fetch commands to change the depth.

## 2. Why do you need to extend history?

Shallow clone is useful in CI, build containers, or environments that only need the latest snapshot. However, some tasks need visibility into additional ancestor commits:

- Viewing changes to a file from weeks or months ago.
- Finding a merge base between two branches before merging or rebasing.
- Running `git bisect` to find a commit that introduced a bug across a long span of history.
- Checking an old release tag or the commit a tag points to.
- Analyzing merge history, authors, and when a change first appeared.
- Running CI tools that require sufficient history to generate a changelog, compute a version, or compare against a previous tag.

When encountering errors due to missing history, you do not necessarily have to download the entire repository right away. You can increase the depth incrementally to fetch just enough commits.

## 3. Adding a number of commits with --deepen

Syntax:

```bash
git fetch --deepen=<n> <remote> [<refspec>...]
```

`<n>` is the number of commits to go deeper from the current shallow boundary. For example, if the repository was initially cloned with `--depth=1` and you want to fetch 50 more commits:

```bash
git fetch --deepen=50 origin
```

Git fetches more history from the `origin` remote according to the configured fetch refspec. If the clone tracks only a single branch, the command normally deepens only that branch.

Check history after fetching:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -60 origin/main
```

The repository may still return `true` because you only downloaded 50 more commits and have not reached the full ancestry yet. This is normal behavior for `--deepen`.

### Deepening a specific branch

If you want to specify the `main` branch and update the corresponding remote-tracking branch, you can use a full refspec:

```bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
```

The part before the colon is the ref on the remote; the part after is the local ref that will be updated. This notation is useful when you need precise control over which branch is fetched in repositories with multiple remotes or custom refspecs.

### Deepening multiple times

You can increase depth step by step:

```bash
git fetch --deepen=50 origin
git fetch --deepen=100 origin
```

These two commands sequentially fetch 50 and then another 100 commits from the new shallow boundary. If the initial depth was 1, the history depth along the branch can grow to around 151 commits, depending on the history structure and downloadable commits. `--deepen=100` does not set the total depth to 100; it adds 100 commits from the current boundary.

## 4. Distinguishing --deepen from --depth

The two options have different meanings:

| Option | Meaning | Example |
|---|---|---|
| `--deepen=<n>` | Adds `<n>` commits starting from the current shallow boundary | `git fetch --deepen=50 origin` |
| `--depth=<n>` | Sets the history depth limit starting from the tip of the fetched branch | `git fetch --depth=200 origin` |
| `--unshallow` | Fetches all remaining available history from the fetch source if the source has full history | `git fetch --unshallow origin` |

Suppose the repository currently has a depth of 20:

```bash
git fetch --depth=100 origin
```

The command above requests history with a total depth of 100 commits from the tip of the fetched branch. Meanwhile:

```bash
git fetch --deepen=100 origin
```

requests 100 additional commits starting from the current shallow boundary. Therefore, the result can be deeper than 100 commits from the branch tip.

If you just want to fetch a small amount of additional history to inspect, `--deepen` expresses that intent clearly. If you want to set a specific overall limit, use `--depth`.

## 5. Fetching full history with --unshallow

When you no longer want a history limit, use:

```bash
git fetch --unshallow origin
```

Git asks the remote to provide all missing history for the fetched refs. If the remote has full history, the local repository transitions from shallow to full.

Verify the result:

```bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all
```

When there are no remaining shallow boundaries, the check command returns:

```text
false
```

### If the source remote is also a shallow repository

If the source repository itself has a shallow limit, `--unshallow` can only download the history that the source provides. Git cannot synthesize ancestor commits that do not exist or are inaccessible on the remote side. In this situation, the result may still retain shallow boundaries.

Fetching also depends on whether the server allows shallow/deepen requests. Some Git servers or services may enforce limits on history, access permissions, or protocols.

## 6. Deepening a branch in a single-branch shallow clone

A clone with `--depth` usually enables single-branch mode unless specified otherwise. That means the default fetch refspec may track only the cloned branch.

Check the configured refspec:

```bash
git config --get-all remote.origin.fetch
```

If you need to fetch history for the `release/2.4` branch, fetch that branch with an explicit refspec:

```bash
git fetch --deepen=50 origin refs/heads/release/2.4:refs/remotes/origin/release/2.4
```

If you want to keep tracking that branch in future fetches, you can add the branch to the remote configuration:

```bash
git remote set-branches --add origin release/2.4
```

Then:

```bash
git fetch --deepen=50 origin
git branch -r
```

The `remote set-branches --add` command expands the list of branches that the `origin` remote will fetch according to its configuration. It does not automatically create a local branch. If you need to work on that branch, create a local branch following the appropriate workflow.

## 7. Tags and shallow history

A shallow clone may not download all tags in the repository. Git typically auto-follows tags associated with newly fetched objects, but that does not guarantee all old tags exist locally.

View existing tags:

```bash
git tag --list
```

Fetch all tags from the remote:

```bash
git fetch --tags origin
```

Or fetch a specific tag:

```bash
git fetch origin tag v1.8.0
```

If an old tag points to a commit outside the current shallow history, fetching the tag may pull in the required objects without necessarily turning the entire branch into full history. When you need to analyze history behind a tag, combine fetching the tag with `--deepen` or `--unshallow` as needed.

Inspect the tag and target commit:

```bash
git show --no-patch --decorate v1.8.0
git log --oneline v1.8.0
```

## 8. Fetching history does not automatically update local branches

`git fetch --deepen` and `git fetch --unshallow` update data and fetched refs, such as `origin/main`. They do not automatically move the local `main` branch or modify the current working tree.

Inspect both refs:

```bash
git log --oneline main -5
git log --oneline origin/main -10
```

If `origin/main` has been updated while the local `main` branch has not changed, you can integrate according to your team's workflow:

```bash
git switch main
git merge --ff-only origin/main
```

Only perform the integration step when you want to update the local branch. If you are working on a different branch, adding history to the remote-tracking ref may be all you need for analysis or inspection.

## 9. Impact and considerations when extending history

- **Increased storage:** each deepen downloads additional commits and associated objects, so the repository can grow substantially.
- **Network time:** long history, many large files, or many branches can make fetching take longer.
- **Refspecs determine scope:** only the fetched branches/refs receive additional history from that command.
- **Does not rewrite commits:** deepen/unshallow only adds objects and expands reachable history; it does not rewrite existing commit hashes.
- **Not the same as sparse checkout:** shallow clone limits the amount of commit history; sparse checkout limits which paths are placed in the working tree. Both features can be used together, but they solve different problems.
- **Do not edit metadata files manually:** to change shallow boundaries, use `git fetch --deepen`, `--depth`, or `--unshallow`.

If the repository is used in CI, choose depth according to pipeline needs. For example, a simple build can use a small depth; a pipeline generating a changelog or running `git describe` needs appropriate tags and history. For pipelines that must analyze the entire history, use `--unshallow` or a full clone.

## 10. Troubleshooting workflow for missing history

Suppose CI reports it cannot find an old release tag or `git log` shows only one commit. Check:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate --all -20
git config --get-all remote.origin.fetch
git tag --list
```

If the repository is shallow and only needs a moderate amount of additional history:

```bash
git fetch --deepen=100 origin
```

If full history is required:

```bash
git fetch --unshallow origin
```

If an untracked branch is needed:

```bash
git fetch origin refs/heads/release/2.4:refs/remotes/origin/release/2.4
```

Then verify again:

```bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all -50
git branch -r
git tag --list
```

Choose `--deepen` when you want controlled incremental fetching; choose `--unshallow` when tooling needs the entire history and the remote can provide it.

## 11. Practice exercises

Practice in a test repository or a separate clone to avoid altering the configuration of your working repository:

1. Clone a repository with `--depth=1` and check using `git rev-parse --is-shallow-repository`.
2. View history with `git log --oneline --all` and note the number of reachable commits.
3. Run `git fetch --deepen=20 origin`, then re-check the shallow status and history.
4. Compare `git fetch --depth=50 origin` with `git fetch --deepen=50 origin` in two independent test clones.
5. Run `git fetch --unshallow origin` and confirm the result with `git rev-parse --is-shallow-repository`.
6. Create a shallow clone with `--single-branch`, inspect `remote.origin.fetch`, then fetch another branch using an explicit refspec.
7. Explain why extending history does not automatically update local branches and why shallow clone differs from sparse checkout.

You have completed the exercises when you can choose properly between `--deepen`, `--depth`, and `--unshallow`, know how to check shallow state, and identify which refs will receive the added history.

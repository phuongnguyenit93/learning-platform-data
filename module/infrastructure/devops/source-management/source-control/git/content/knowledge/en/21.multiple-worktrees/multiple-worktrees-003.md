# Shared Data and Per-Worktree Data

Git worktree allows a repository to have multiple working directories at the same time. You can open one worktree for a feature under development, another worktree for a bug-fix branch, and yet another worktree to review commits. These worktrees share the object database and most Git references, while each directory has its own working tree, index, and `HEAD`. Understanding that boundary helps you know which changes are visible across all worktrees, which changes exist only in one directory, and why Git does not normally allow checking out the same branch in multiple worktrees.

## 1. One repository can have multiple worktrees

When cloning a repository in the usual way, you have one working directory and a `.git` administrative directory. With linked worktrees, Git creates an additional working directory while still sharing the Git repository of the original repo.

Example:

```text
workspace/
  project/                 main worktree
    .git/                  shared administrative directory
    src/
  project-hotfix/          linked worktree
    .git                    file pointing to the worktree's own metadata
  project-review/           linked worktree
    .git                    file pointing to the worktree's own metadata
```

In a linked worktree, `.git` is usually a text file containing the path to that worktree's administrative directory, rather than an independent `.git` directory. Per-worktree metadata is stored under the shared administrative directory, typically in `.git/worktrees/<id>/`. The actual layout may differ if the repository uses a custom gitdir or was created by another management tool; use Git commands to query it instead of assembling paths manually.

Create a new worktree from an existing branch:

```bash
git worktree add ../project-hotfix hotfix/urgent-fix
```

Create a new branch and a worktree at the same time:

```bash
git worktree add -b feature/report ../project-report main
```

Create a worktree in detached HEAD state to review a specific commit:

```bash
git worktree add --detach ../project-review <commit>
```

The commands above are run from a worktree belonging to the repository. The target path must be a suitable location for Git to create a new working directory.

## 2. What data is shared?

Worktrees belonging to the same repository share the following core data:

| Shared data | Meaning |
|---|---|
| Object database | Commit, tree, blob, and tag objects; content stored in Git can be accessed from any worktree |
| Branch refs | Local branches such as `main`, `feature/report` are shared repository refs |
| Tag refs | Local tags such as `v1.2.0` are shared |
| Remote-tracking refs | Refs such as `origin/main` are updated when fetching from any worktree |
| Standard repository configuration | Most local settings in the common config are shared |
| Stash stack | Stash entries belong to the repository and can be viewed from another worktree |
| Hooks and remote information | Usually use the shared repository configuration, unless customized through an appropriate mechanism |

For example, when running `git fetch origin` in one worktree, Git updates the shared remote-tracking refs. Another worktree can see the new `origin/main` immediately afterward without needing to fetch again.

Similarly, a commit created in one worktree becomes an object in the shared store. If the commit is attached to a shared branch ref, other worktrees can see the commit through that branch. A commit existing in the object database does not mean all worktrees automatically switch to that commit; each `HEAD` still keeps its own state.

Check branches and tags from any worktree:

```bash
git branch --all
git tag --list
git stash list
```

The lists of branches, tags, and stashes reflect shared repository data, not separate copies for each working directory.

## 3. What data belongs exclusively to each worktree?

Each worktree has independent state for the following:

| Per-worktree data | Meaning |
|---|---|
| Working tree | Files and directories on disk in that worktree |
| Index | Separate staging area; `git add` in one worktree does not stage files in another |
| `HEAD` | The commit or branch currently checked out by that worktree |
| In-progress operation state | Paused state of a merge, rebase, cherry-pick, or revert |
| Certain pseudo-refs and worktree management refs | For example, bisect or rebase state is stored separately per worktree |
| `HEAD` reflog | Records `HEAD` movements of the corresponding worktree |

For example, you edit `src/App.java` in `project-hotfix/` without touching `project/`. The two working trees can contain two different versions of the same path. When you stage the file in `project-hotfix/`, the index of `project/` remains unchanged.

This lets you keep unfinished work in one worktree while opening another worktree to handle an urgent request. You do not need to stash or commit just to switch to another working directory.

## 4. Why can a branch normally only be checked out in one worktree?

Branch refs are shared, while each worktree has its own index and working tree. If two worktrees check out the same branch, each place could create commits or move the branch tip in a different state. That easily causes confusion and breaks consistency between the branch and the `HEAD` in use.

Therefore, Git normally prevents you from checking out the same branch in two worktrees at the same time. For example, if `main` is checked out in the main worktree, the following command may be rejected:

```bash
git worktree add ../project-main-copy main
```

Git will report that the branch is already checked out in another worktree. Create the worktree from a different branch or use detached HEAD if the goal is only to read/review a commit:

```bash
git worktree add --detach ../project-main-review main
```

Detached HEAD does not create a new branch. If you create commits in this state, create a branch to keep the commits before removing the worktree or switching to another state:

```bash
git switch -c review/experiment
```

Do not try to force two worktrees to use the same branch just to avoid creating a separate branch. If you need to share progress, commit on the current worktree's branch and switch to that branch in the appropriate worktree following Git's rules.

## 5. Checking per-worktree and shared Git directories

The following commands help determine which administrative directories the current worktree is using:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

- `--show-toplevel` returns the root directory of the current working tree.
- `--git-dir` returns the Git directory for the current worktree.
- `--git-common-dir` returns the shared administrative directory of the repository, where shared data is stored.

In the main worktree, `--git-dir` and `--git-common-dir` usually point to the same `.git` directory. In a linked worktree, `--git-dir` usually points to a per-worktree metadata directory such as `.git/worktrees/<id>`, while `--git-common-dir` points to the repository's shared `.git`.

List registered worktrees:

```bash
git worktree list
git worktree list --porcelain
```

The output usually shows the path, current commit, and checked-out branch; the porcelain format is suitable for scripts because its structure is easier to parse.

## 6. Repository configuration is shared by default

Normally, local configuration resides in the common config and is shared by all worktrees. For example:

```bash
git config --local user.name
git config --local user.email
git config --local remote.origin.url
```

When configuring `remote.origin.url` or user information in one worktree with `--local`, you are changing the shared configuration of the repository. Other worktrees also see the new value.

If you need some per-worktree configuration, Git supports the `worktreeConfig` extension. When this extension is enabled, you can use `git config --worktree` to write to the worktree's own configuration file:

```bash
git config extensions.worktreeConfig true
git config --worktree user.name "Reviewer"
git config --worktree user.email "reviewer@example.com"
```

`--worktree` only writes to a separate configuration file when the extension is enabled; if not enabled, it behaves like `--local` and continues writing to the common configuration. Enabling the extension changes how Git reads configuration, and certain settings need to be placed in the right location. Read the Git documentation on `extensions.worktreeConfig` before enabling it in a shared repository.

Do not use per-worktree configuration to hide important settings that need to be uniform for the team. Use the shared configuration for remotes, project policies, and shared settings; only separate them when there is a specific need, such as different commit identities between a review worktree and a development worktree.

## 7. Merge, rebase, and cherry-pick states are isolated

One worktree can be paused in the middle of a merge due to conflicts, while another worktree can still be used to read code or work on a different branch. The paused state of an operation is stored separately per worktree, so `git status` in the conflicted worktree will show that operation; other worktrees do not automatically inherit this merge or rebase state.

Example:

```text
project/          main, clean state
project-hotfix/   hotfix/urgent-fix, merge paused due to conflict
project-review/   detached HEAD at a commit, read-only
```

In this situation, resolve conflicts in `project-hotfix/` using appropriate commands such as `git status`, editing files, `git add`, and `git merge --continue`. Do not run `git merge --continue` from the `project/` worktree, because that worktree has no paused merge state.

Commands to continue or abort an operation must be run in the exact worktree where the operation was started:

```bash
git rebase --continue
git rebase --abort
git cherry-pick --continue
git cherry-pick --abort
```

Before executing, use `git status` to confirm the type of operation in progress and the current working directory.

## 8. How do changes in one worktree affect another worktree?

| Action in worktree A | What does worktree B see? |
|---|---|
| Edit an unstaged file | Does not see the edited content in B's working tree |
| Run `git add` | B's index does not change |
| Create a commit on the checked-out branch | The commit object is stored in the shared store; the shared branch ref moves |
| Fetch remote | Remote-tracking refs and new objects are shared |
| Create or delete a local tag | The shared tag ref changes; B sees the new/old tag name and target |
| Create a stash | The stash entry is stored in the shared repository and can be listed from B |
| Merge/rebase conflict in progress | Operation state is local to A; B does not switch into that state |

There are several situations to note. If the `feature/report` branch is checked out in worktree A, Git will block checking out that branch in B in the normal way. However, other branches and tags are still shared. A fetch operation in B can update `origin/main`, so when you return to A, you see the newer remote-tracking ref even though you have not run fetch in A.

## 9. Managing the worktree lifecycle

View all worktrees:

```bash
git worktree list
```

Add a worktree for an existing branch:

```bash
git worktree add ../project-docs docs/update-guide
```

Create a new branch and worktree:

```bash
git worktree add -b feature/audit ../project-audit main
```

Remove a linked worktree when no longer needed:

```bash
git worktree remove ../project-docs
```

The remove command requires a clean worktree by default. If uncommitted changes remain, Git will refuse to prevent losing work. Commit, stash, or back up changes before removing. The `--force` option can bypass some protections; only use it after clearly inspecting what will be discarded.

If a worktree directory was deleted manually outside of Git, registration metadata may remain. Clean up invalid registrations with:

```bash
git worktree prune --dry-run
git worktree prune
```

`--dry-run` lists the metadata Git plans to prune without deleting anything yet. Only run the actual prune command after confirming the path is no longer a worktree to keep. If a worktree is on an external drive or temporary device and is currently offline, you can lock it to prevent accidental pruning:

```bash
git worktree lock --reason "External review workspace" ../project-review
```

Unlock when the worktree is ready to be managed again:

```bash
git worktree unlock ../project-review
```

## 10. Practical example: parallel feature development and bug fixing

You are developing a reporting feature on the `feature/report` branch. Suddenly the team asks for an urgent bug fix on `main`. With only a single working tree, you might have to temporarily commit or stash your work in progress. With worktrees, create a separate directory for the hotfix:

```bash
git worktree add -b hotfix/report-crash ../project-hotfix main
```

Now you have two directories:

```text
project/          feature/report
project-hotfix/   hotfix/report-crash
```

In `project-hotfix/`, fix the bug, run tests, and commit:

```bash
git status
git add src/main/ReportService.java
git commit -m "Fix report crash on empty input"
```

The `hotfix/report-crash` branch and the new commit are shared repository data. In `project/`, you still see that branch when running `git branch --list`, while the working tree and index of `feature/report` preserve your work in progress.

After the hotfix is integrated into `main`, return to the feature worktree and update the base according to the team workflow, such as fetching then merging or rebasing. There is no need to switch branches back and forth inside a single working directory just to handle two streams of work.

## 11. Common misconceptions

- **Assuming each worktree is an independent clone.** They share the object database, refs, and most repository configuration.
- **Assuming staging in one worktree stages in all.** Each worktree has its own index.
- **Assuming files edited in one working tree appear automatically in another working tree.** Uncommitted content stays in its own directory.
- **Assuming a local branch belongs exclusively to one worktree.** Branch refs are shared data; only `HEAD` indicates which branch the current worktree has checked out.
- **Checking out the same branch in two worktrees.** Git normally prevents this to avoid two `HEAD`s controlling the same branch ref.
- **Running merge/rebase continue commands in the wrong directory.** Operation state belongs to the worktree that started it.
- **Deleting a linked worktree directory with OS tools and forgetting the metadata.** Use `git worktree remove` or check before running `git worktree prune`.
- **Thinking `--local` configuration is per-worktree.** By default it writes to the common config; `extensions.worktreeConfig` must be enabled for per-worktree config via `--worktree`.

## 12. Checklist to identify shared vs. per-worktree data

When unsure whether a state affects other worktrees, check:

1. Run `git rev-parse --show-toplevel` to identify the current directory.
2. Run `git rev-parse --git-dir` and `git rev-parse --git-common-dir` to distinguish per-worktree metadata from shared metadata.
3. Run `git worktree list --porcelain` to inspect the branch and commit of each worktree.
4. Run `git status --short` in each worktree to check its own working tree and index.
5. Check `git branch`, `git tag`, `git remote -v`, and `git stash list` to view shared refs/configuration.
6. If per-worktree config is needed, verify `extensions.worktreeConfig` before using `git config --worktree`.
7. Before removing or pruning, confirm the worktree has no remaining changes to keep and is not a temporarily offline directory.

## 13. Key takeaways

Worktrees in the same repository share the object database, branch/tag refs, remote-tracking refs, stashes, and most configuration. Each worktree has its own working tree, index, `HEAD`, and operation state. Git enforces the rule that a branch can only be checked out in one normal worktree to avoid multiple places controlling a single branch ref. Use `git rev-parse` and `git worktree list` to determine the actual layout, and choose the right worktree when staging, resolving conflicts, continuing operations, or cleaning up working directories.

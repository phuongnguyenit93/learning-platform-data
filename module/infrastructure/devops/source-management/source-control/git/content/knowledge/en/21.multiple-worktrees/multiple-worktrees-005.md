# Listing, Moving, and Locking Worktrees

Git worktree allows a repository to have multiple working directories at the same time. Each worktree has its own working tree, index, and `HEAD`, while sharing the object database and most repository metadata. As a result, you can open a hotfix branch in a separate directory while continuing to work on a feature branch in the main directory.

As the number of worktrees grows, you need to know how to list them, move a worktree to a new location, and lock a worktree when its directory is temporarily unavailable. These commands help manage worktree metadata accurately and prevent Git from mistakenly treating an in-use worktree as deleted.

## 1. How are worktrees and metadata organized?

A repository can have a main worktree and multiple linked worktrees. Example:

```text
project/
├── .git/
└── src/

project-hotfix/
├── .git        (file pointing to the linked worktree's metadata)
└── src/

project-release/
├── .git        (file pointing to the linked worktree's metadata)
└── src/
```

The `.git` entry of a linked worktree is usually a file pointing to the worktree's own metadata area inside the shared Git directory. It is not an independent repository with its own object database.

Each worktree has its own checkout state. A branch is normally only checked out in one worktree at a time, to prevent two directories from updating the same branch ref and overwriting each other's changes. Objects and commit history are still shared among worktrees belonging to the same repository.

Example:

```text
project/           -> main
project-hotfix/    -> hotfix/login
project-release/   -> release/2.x
```

When a branch is already checked out in another worktree, `git switch` in the current worktree will normally refuse to check out that branch. You can use `git worktree list` to determine which directory currently holds the branch.

## 2. Listing worktrees

Basic command:

```bash
git worktree list
```

Example output:

```text
/work/project              a1b2c3d [main]
/work/project-hotfix       e4f5a6b [hotfix/login]
/work/project-release      9a8b7c6 [release/2.x]
```

Each line shows the worktree path, current commit, and checked-out branch. If a worktree is in detached HEAD state, Git displays the detached state instead of a branch name.

This command is useful when you need to answer questions like:

- How many worktrees are currently registered?
- Which worktree has checked out the branch I am looking for?
- Which commit is a worktree currently at?
- Which path is in use before moving or cleaning up?

For output easier to process in scripts, use porcelain mode:

```bash
git worktree list --porcelain
```

Porcelain output splits information into fields such as `worktree`, `HEAD`, `branch`, `detached`, `locked`, and `prunable` where applicable. This is a more stable format for automation tools than parsing human-readable text output.

Example:

```text
worktree /work/project
HEAD a1b2c3d...
branch refs/heads/main

worktree /work/project-hotfix
HEAD e4f5a6b...
branch refs/heads/hotfix/login
locked Keep for release validation
```

In this example, the hotfix worktree has been locked with the reason `Keep for release validation`. The `locked` entry describes worktree management state; it does not mean the branch is locked against commits or the directory becomes read-only.

If you want information about a specific worktree, you can run Git commands inside that directory itself:

```bash
git -C /work/project-hotfix status
git -C /work/project-hotfix branch --show-current
git -C /work/project-hotfix rev-parse --short HEAD
```

The `-C` option tells Git to run as if the command were invoked from the specified path. This is useful when you are in another directory but want to inspect that worktree.

## 3. Moving a linked worktree with git worktree move

When you need to relocate a directory, use the dedicated command:

```bash
git worktree move <worktree> <new-path>
```

For example, moving the hotfix worktree into a worktrees storage directory:

```bash
git worktree move ../project-hotfix ../worktrees/project-hotfix
```

After a successful move:

- Git moves the linked worktree directory to the new path.
- Linked metadata is updated so Git recognizes the new location.
- The checked-out branch and commit remain intact.
- Changes in the working tree and index are preserved with the moved directory.

Recheck the list:

```bash
git worktree list
git -C ../worktrees/project-hotfix status
```

Ensure the destination directory does not already exist and the parent directory is ready. Use the exact path obtained from `git worktree list` to avoid moving the wrong worktree. If the path contains spaces, wrap the path in quotes appropriate for your shell.

The `git worktree move` command is only used to move linked worktrees. You cannot move the main worktree with this command. Git also does not support moving a linked worktree that contains submodules in this way; in that case, follow the repository and submodule workflow rather than forcing the move command.

Do not move directories using File Explorer or OS commands as your default approach. If moved manually outside of Git, metadata may still record the old path and the worktree may be treated as no longer available. The next section describes how to fix links in that situation.

## 4. If the directory was moved manually

If the worktree directory was moved with an OS tool, Git might not yet know the new path. In that case, use:

```bash
git worktree repair <new-path>
```

For example, after manually moving the directory from `../project-hotfix` to `../worktrees/project-hotfix`, run the repair command from the main repository:

```bash
git worktree repair ../worktrees/project-hotfix
```

This command updates metadata links so Git recognizes the worktree at the new location. If the main repository structure or shared Git directory was also moved, `git worktree repair` can be run inside the main worktree to update metadata for the affected linked worktrees.

After repairing, check:

```bash
git worktree list
git -C ../worktrees/project-hotfix status
```

If the worktree is still not recognized, verify that the `.git` file inside the linked worktree still points to a valid Git directory and that the new path is correct. Do not delete metadata manually just because the list command shows the old path; determine the exact state of the link first.

Prefer `git worktree move` when initiating a move. `git worktree repair` is the tool for restoring links after a path change occurred outside of Git or when metadata has gone out of sync.

## 5. Locking a worktree with git worktree lock

A worktree may reside on a removable drive, network share, or location that is sometimes disconnected. When that path is temporarily unreachable, Git may view the worktree metadata as stale and mark it eligible for pruning after the configured expiration period.

To preserve the worktree metadata in this case, use the lock command:

```bash
git worktree lock <worktree>
```

You can record a lock reason so others understand why the worktree needs to be kept:

```bash
git worktree lock --reason "Keep for release validation" ../worktrees/project-release
```

The lock reason is displayed in the output of `git worktree list` or porcelain mode. This is helpful when multiple people manage a repository that has worktrees across different drives or environments.

A common workflow with an external drive:

1. While the worktree is still accessible, check `git status` and finish or safeguard work in progress.
2. Lock the worktree with `git worktree lock --reason "..." <path>`.
3. Disconnect the drive or temporarily make the path unavailable.
4. When reconnected, check `git worktree list` and continue working.
5. When protection against pruning is no longer needed, unlock with `git worktree unlock`.

The lock command does not lock the branch against commits and does not make the directory read-only. It marks the linked worktree to be retained when the path is unavailable so Git does not automatically prune its metadata. The locked state also prevents normal worktree management commands from moving or removing that worktree; unlock it before moving or removing.

## 6. Unlocking a worktree

When the worktree is reliably accessible again and no longer needs protection against pruning, use:

```bash
git worktree unlock <worktree>
```

Example:

```bash
git worktree unlock ../worktrees/project-release
git worktree list --porcelain
```

After unlocking, the `locked` field no longer appears for that worktree. If the path later ceases to exist, the metadata may be considered stale and eligible for pruning according to the configured expiration period.

Do not unlock a worktree just because you do not see it in File Explorer or because it is offline. First confirm with the person responsible that the worktree no longer needs to be retained, especially when it resides on an external drive or network share.

## 7. Distinguishing lock, prune, and remove

These operations serve different purposes:

| Command | Purpose | Effect |
|---|---|---|
| `git worktree lock` | Protect worktree metadata from automatic pruning when the path is unavailable | Records locked state and optional reason; prevents normal move/remove until unlocked |
| `git worktree unlock` | Remove protective state | Allows Git to consider pruning if the worktree becomes stale |
| `git worktree prune` | Clean up metadata of worktrees that no longer exist or are eligible stale entries | Deletes stale management info inside the Git directory |
| `git worktree remove` | Actively delete a linked worktree | Removes the worktree directory and its corresponding metadata if conditions are met |

`prune` is not a command to delete active worktrees. It cleans up metadata for worktrees that Git determines are no longer present and are not protected by a lock. `remove` is an intentional operation to remove a linked worktree, so check status and uncommitted changes before using it.

Before pruning, you can preview the items that will be cleaned up:

```bash
git worktree prune --dry-run --verbose
```

If the output shows a worktree you still need, check its path and lock state before running the actual prune. You can perform the prune after confirming:

```bash
git worktree prune --verbose
```

Git also lets you adjust the stale expiration threshold with `--expire`, for example:

```bash
git worktree prune --dry-run --verbose --expire now
```

`--expire now` requests immediate consideration of eligible stale metadata. Only use this threshold after careful verification, because an actual prune operation can remove metadata needed for Git to recognize an old worktree.

If you want to permanently remove an existing linked worktree, use `git worktree remove <path>` after checking that it has no work left to keep. Do not use `prune` as a substitute for remove on a worktree that still exists.

## 8. Workflow for managing multiple worktrees

Suppose the repository has the main worktree at `../project`, a hotfix worktree at `../project-hotfix`, and a release worktree on an external drive.

You can manage them with this workflow:

**Step 1: List and identify branches.**

```bash
git worktree list
git worktree list --porcelain
```

Check the branch and commit at each path before moving or locking.

**Step 2: Check changes in the worktree to be moved.**

```bash
git -C ../project-hotfix status
git -C ../project-hotfix log --oneline -5
```

Ensure work-in-progress changes are preserved and identify which branch that worktree is using.

**Step 3: Move using Git.**

```bash
git worktree move ../project-hotfix ../worktrees/project-hotfix
```

**Step 4: Lock the worktree on the external drive.**

```bash
git worktree lock --reason "Release worktree on removable drive" /mnt/releases/project-release
```

Perform the lock while the path is still accessible, before disconnecting the drive.

**Step 5: Verify status.**

```bash
git worktree list --porcelain
git -C ../worktrees/project-hotfix status
```

**Step 6: When the release worktree no longer needs to be kept, unlock and clean up intentionally.**

```bash
git worktree unlock /mnt/releases/project-release
git worktree list
```

If you want to delete an existing worktree, use `git worktree remove` after checking for changes. If the directory was already deleted or no longer exists, preview stale metadata with `git worktree prune --dry-run --verbose` before deciding to prune.

## 9. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Cannot check out branch | The branch is already checked out in another worktree | Run `git worktree list` to find the worktree using the branch |
| `git worktree move` fails | Destination path already exists, main worktree selected, or worktree contains submodules | Check source/destination; only move eligible linked worktrees |
| Git shows old path after manually moving directory | Metadata has not been updated | Run `git worktree repair <new-path>` |
| Worktree on external drive marked prunable | Path temporarily unavailable and not locked | Reconnect or lock the worktree before disconnecting next time |
| Cannot unlock worktree | Wrong path specified or worktree metadata no longer exists | Inspect `git worktree list --porcelain` and use the exact path |
| Prune proposes deleting worktree metadata | Git determined the worktree is stale per expiration threshold | Use `--dry-run --verbose`, verify, and lock if it needs to be kept |
| Worktree loses changes on remove | Working tree had unsaved changes or force option was used | Check status and commit/stash/copy work before removing |

## 10. Checklist before moving, locking, or pruning

Before managing a worktree, check:

1. Is the target worktree a linked worktree or the main worktree?
2. Is the current path obtained from `git worktree list` accurate?
3. Which branch and commit does the worktree have checked out?
4. Are there uncommitted changes or untracked files to preserve?
5. If moving, is the destination path ready and not already existing?
6. If the path will be temporarily offline, has the worktree been locked with a clear reason?
7. If pruning, have you previewed with `--dry-run --verbose`?

These steps help avoid moving the wrong directory, breaking metadata links, or accidentally cleaning up a worktree that is still in use.

## Conclusion

Use `git worktree list` to inventory the paths, commits, and branches of worktrees; use `git worktree move` to move linked worktrees and `git worktree repair` when a manual move caused metadata to go out of sync. Use `git worktree lock --reason` to preserve metadata for temporarily unavailable worktrees, then `unlock` when protection is no longer needed. Before pruning or removing, verify the path, status, and any changes you need to keep.

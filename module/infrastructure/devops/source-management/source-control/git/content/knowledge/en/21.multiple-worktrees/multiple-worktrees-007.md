# Repairing Links After Moving a Directory with git worktree repair

Git worktree allows a repository to have multiple working directories at the same time. Each worktree has its own working tree and can check out a different branch, while sharing the object database and most repository metadata. This layout is very convenient when you need to fix an urgent bug in a separate directory while keeping work in progress intact in another directory.

When you manually move a worktree directory using File Explorer, `mv`, or a file management tool, paths in the metadata may still point to the old location. Git may then report that the worktree is missing, fail to recognize the new directory, or be unable to operate on the moved worktree. The `git worktree repair` command updates administrative links so Git recognizes the new location properly.

## 1. How do linked worktrees work?

A repository can have a main worktree and multiple linked worktrees. The main worktree is usually the directory created when cloning or initializing the repository. Linked worktrees are added using `git worktree add`.

Example:

```text
project/                         # main worktree
├── .git/                        # common Git directory
├── src/
└── README.md

../project-hotfix/               # linked worktree
├── .git                         # file pointing to the worktree's own metadata
├── src/
└── README.md

../project-feature/              # linked worktree
├── .git                         # file pointing to the worktree's own metadata
├── src/
└── README.md
```

Unlike the main worktree, `.git` in a linked worktree is usually a **text file** containing the path to the worktree's own metadata directory inside the common Git directory. This metadata links back to the working directory. That way, Git knows which branch each directory has checked out and where the shared object database is located.

Administrative information for linked worktrees usually resides in:

```text
.git/worktrees/<worktree-id>/
```

It contains files such as `gitdir`, `HEAD`, `commondir`, and data related to the worktree's own state. Paths in these files help Git connect the working directory with its corresponding metadata.

When moving a directory manually, the filesystem changes its location, but metadata may still hold the old path. `git worktree repair` resynchronizes those links. Do not manually edit files inside `.git/worktrees/` or the contents of the `.git` file by hand unless you fully understand the internal structure.

## 2. Recognizing when to use git worktree repair

Suppose you created a linked worktree:

```bash
git worktree add ../project-feature feature/login
```

Afterward, you move the `project-feature` directory to another drive or location, for example:

```text
Before: D:/workspace/project-feature
After:  E:/worktrees/project-feature
```

Git may still store the old path in metadata. When running:

```bash
git worktree list
```

the worktree may be marked `prunable`, or Git may report that the old directory no longer exists. When accessing the new directory, Git may also fail to recognize the repository properly if the `.git` file inside still points to old metadata.

Some other signs:

- `git worktree list` displays the old path even though the directory has been moved.
- Git reports it cannot find the linked worktree directory or corresponding metadata.
- The new directory still exists, but Git does not recognize it as a linked worktree of the repository.
- A worktree management operation fails because the path in metadata is no longer valid.

If you only rename a file inside the working tree, switch branches with `git switch`, or create a new linked worktree with `git worktree add`, `repair` is normally not needed. This command is for fixing links after **moving a worktree directory at the filesystem level**.

## 3. Checking the worktree list before repairing

From an active worktree of the repository, run:

```bash
git worktree list
```

Example:

```text
D:/workspace/project             abc1234 [main]
D:/workspace/project-feature     def5678 [feature/login] prunable
D:/workspace/project-hotfix      987abcd [hotfix/payment]
```

The output shows the worktree path, checked-out commit, branch (if any), and special status. `prunable` usually indicates that Git considers the worktree registration eligible for cleanup because the associated directory is no longer at the recorded location. If you just moved the directory, this may be a sign that metadata has not been updated yet.

To view script-friendly output or inspect metadata, use:

```bash
git worktree list --porcelain
```

Example:

```text
worktree D:/workspace/project
HEAD abc1234...
branch refs/heads/main

worktree D:/workspace/project-feature
HEAD def5678...
branch refs/heads/feature/login
prunable
```

`--porcelain` displays each worktree as a group of fields, making it easy to clearly identify the path and branch. Note the exact new path before running repair. If the path contains spaces, wrap it in quotes when passing it to the command.

## 4. Repairing a moved linked worktree

When only a linked worktree has been moved, run `git worktree repair` from the main worktree or another linked worktree that is still in its original location and working normally. Pass the **new** path of the linked worktree to be repaired.

For example, the linked worktree was moved from `D:/workspace/project-feature` to `E:/worktrees/project-feature`. Open a terminal in the main worktree and run:

```bash
git worktree repair "E:/worktrees/project-feature"
```

Git will locate the linked worktree at the new path and update the relevant administrative files so the link between the working directory and the common Git directory is accurate again.

If multiple linked worktrees were moved, you can pass multiple paths at once:

```bash
git worktree repair "E:/worktrees/project-feature" "E:/worktrees/project-hotfix"
```

Each argument is the new location of a linked worktree. Make sure these paths actually contain worktrees of the repository being repaired; do not pass an ordinary project directory or a directory not registered as a linked worktree.

After repairing, verify:

```bash
git worktree list --porcelain
git -C "E:/worktrees/project-feature" status
```

The path in the list must be the new location, and `git status` from that directory must recognize the right repository along with its working tree state.

## 5. Repairing when the main worktree was moved

If you move the **main worktree** (the directory containing the common `.git` directory), linked worktree metadata may still point to the old main worktree location. In this case, open a terminal at the new location of the main worktree and run `git worktree repair` without paths:

```bash
cd "E:/workspace/project"
git worktree repair
```

Running the command from the new main worktree fixes the administrative files of linked worktrees so they reference the common Git directory at its new location.

Example:

```text
Main worktree before: D:/workspace/project
Main worktree after:  E:/workspace/project
Linked worktree:      D:/workspace/project-feature
```

After moving the main directory from `D:/workspace/project` to `E:/workspace/project`, run repair inside `E:/workspace/project`. Linked worktrees still in their old locations can continue to be recognized once metadata links are updated.

If the main worktree is new and one or more linked worktrees were also moved, run repair from the new main worktree and pass the new path of each linked worktree:

```bash
cd "E:/workspace/project"
git worktree repair "F:/worktrees/project-feature" "F:/worktrees/project-hotfix"
```

Then recheck the full list with `git worktree list --porcelain` and verify each new directory with `git -C <path> status`.

## 6. Distinguishing repair from prune

`git worktree repair` and `git worktree prune` both relate to worktree metadata, but their goals are completely different.

| Command | Purpose | When to use |
|---|---|---|
| `git worktree repair [<path>...]` | Update administrative links after a worktree was moved manually | The worktree directory still exists at the new location and you want to keep using it |
| `git worktree prune` | Delete registration metadata for worktrees that no longer exist or have expired per prune rules | The worktree was truly deleted and you want to clean up the stale registration |
| `git worktree list` | List worktrees and registration status | Inspect before and after repairing |

Do not use `prune` just because the list displays `prunable` after you moved a directory. That metadata may still be necessary for Git to recognize the worktree at its new location. Run `repair` with the right path first. If you truly no longer need the worktree and the directory has already been deleted, only then consider `prune`.

You can preview which metadata prune would remove with:

```bash
git worktree prune --dry-run --verbose
```

This command only simulates metadata cleanup. If the output includes a worktree you want to keep, stop and check the path or run repair before performing an actual prune.

## 7. Complete workflow when moving a worktree

Suppose you move the `feature/login` linked worktree to another drive. The workflow can be carried out as follows:

### Step 1: Confirm repository and worktree state

From an active main worktree:

```bash
git rev-parse --show-toplevel
git worktree list --porcelain
```

Note the branch, commit, and old path of the worktree to be moved. If the directory has uncommitted changes, leave them intact; `repair` is not intended for saving commits or cleaning up working content.

### Step 2: Move the directory using a filesystem tool

Example move:

```text
D:/workspace/project-feature
    -> E:/worktrees/project-feature
```

Move the entire worktree directory, including the `.git` file inside it. Do not copy only the source code and omit the `.git` file, because this file is the link to the worktree's administrative metadata.

### Step 3: Repair from an active worktree

```bash
git worktree repair "E:/worktrees/project-feature"
```

If the main worktree also moved, run the command from the new main worktree. If both main and linked worktrees moved, pass the new linked worktree paths as shown in the previous section's example.

### Step 4: Verify links and contents

```bash
git worktree list --porcelain
git -C "E:/worktrees/project-feature" status --short --branch
git -C "E:/worktrees/project-feature" rev-parse --show-toplevel
```

Check that the path, branch, and status match what they were before moving. Source contents, the current commit, and uncommitted changes should still be inside the new directory.

### Step 5: Continue working

Once links are repaired, you can continue using normal Git commands in the linked worktree:

```bash
git -C "E:/worktrees/project-feature" status
git -C "E:/worktrees/project-feature" log --oneline -5
```

There is no need to recreate the worktree with `git worktree add` if the moved directory still contains valid data and metadata; creating another new worktree could cause confusion or conflict with the checked-out branch.

## 8. Common errors when repairing

### Passing the old path instead of the new path

`git worktree repair` needs to know the current location of the moved directory. If you pass the old path, Git cannot find the linked worktree's `.git` file at that location. Check the path in File Explorer or use a filesystem command before running.

### Running the command from a directory not belonging to the repository

If you run repair from a directory unrelated to the repository, Git may report it is not a repository. Switch to the main worktree or an active linked worktree, then verify with:

```bash
git rev-parse --show-toplevel
```

### Moving without the .git file

A linked worktree usually uses a `.git` file to point to its own metadata. If you only copy the source directory and omit this file, `git worktree repair` cannot automatically recreate all omitted working state. Check whether the moved copy contains the `.git` file and compare with a backup before intervening on metadata.

### The new directory is not a worktree of this repository

The passed path must be the moved linked worktree directory. If you accidentally pass an independent clone, a manually copied source directory, or another repository, repair cannot turn it into a linked worktree of the current repository.

### Running prune before repair

If the worktree registration has already been pruned, Git may no longer have the metadata needed to relink the worktree's branch and separate state. When you discover the old path does not exist while the new directory still holds data, try repair first and avoid pruning during investigation.

## 9. Inspecting metadata without manual editing

To determine the main Git directory and common Git directory from a worktree:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
```

In the main worktree, both paths usually point to the `.git` directory. In a linked worktree, `--git-dir` usually points to its own metadata directory inside `.git/worktrees/<id>`, while `--git-common-dir` points to the shared common Git directory.

You can read the contents of the `.git` file in a linked worktree to understand the link:

```text
gitdir: D:/workspace/project/.git/worktrees/project-feature
```

The path in the example is illustrative. If the main worktree was moved, this path may still reflect the old location before repair. Although you can read it for diagnosis, do not directly edit `.git`, `gitdir`, or `commondir`; use `git worktree repair` so Git consistently updates the relevant links.

## 10. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| `git worktree repair` recreates missing source code | The command fixes metadata and administrative links; it does not restore files lost from the filesystem |
| You can run repair from any directory | It must be run from the main worktree or an active worktree, depending on what was moved |
| If a linked worktree moves, you must delete and re-add it | If the new directory still has intact metadata, repair can reconnect the existing registration |
| `prunable` always means the worktree is no longer needed | It may simply be because the directory was moved and metadata has not been updated yet |
| `git worktree repair` and `git worktree prune` are the same | Repair updates links; prune removes registration metadata that is no longer used |
| Repair changes commits or branches | The command fixes administrative links, not an integration or history-rewriting operation |
| You can delete old metadata files by hand so Git picks up the new path | Let `git worktree repair` update the relevant links |

## 11. Key takeaways

When a worktree directory is moved at the filesystem level, Git metadata may still hold the old path. `git worktree repair` is used to fix administrative links after moving:

- If a linked worktree moved, run from the main worktree or another active worktree and pass the new path.
- If the main worktree moved, run repair from the new location of the main worktree.
- If both the main and linked worktrees moved, run from the new main worktree and specify the new linked worktree paths.

Before repairing, inspect `git worktree list --porcelain` and verify the exact paths. After repairing, recheck the list along with `git status` from each new directory. Use `prune` only when you want to remove a worktree registration that is truly no longer in use; do not use it to handle a worktree that was just moved.

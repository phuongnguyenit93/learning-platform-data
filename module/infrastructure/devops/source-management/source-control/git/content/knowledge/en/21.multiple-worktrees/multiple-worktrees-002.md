# Creating Additional Working Directories with git worktree add

When you are developing a feature and need to switch to an urgent bug fix, you can create an additional working directory from the same repository using **Git worktree**. Each worktree has its own working tree and index, so you can keep two branches open in two different directories at the same time without stashing or cloning the repository again.

The command to create a worktree is `git worktree add`. You can use it to open an existing branch, create a new branch from a specific point, or check out a commit in detached `HEAD` state for review. Worktrees linked to the same repository share the object database and branch/tag references.

## 1. How do additional worktrees work?

A repository can have one main worktree and multiple linked worktrees. Each working directory has:

- Its own working tree: the files you open and edit reside in that directory.
- Its own index: the staging area of each worktree is independent.
- Its own `HEAD`: each worktree can check out a different branch or be in a detached state.
- Shared repository data: the object database, branches, tags, and most configuration are shared.

For example, you can have this structure:

```text
workspace/
|-- payment-service/       # main worktree, on main
|-- wt-payment/            # additional worktree, on feature/payment
`-- wt-hotfix/              # additional worktree, on hotfix/login
```

The directories above are not independent clones. Commits created in one worktree are visible from other worktrees because they share the same object database. However, uncommitted changes in the working tree and index of one worktree do not automatically appear in another worktree.

In a linked worktree, the `.git` file in the working directory is usually a file pointing to the worktree's own metadata inside the main repository. Do not delete or move that metadata file manually using filesystem operations; manage the worktree lifecycle with Git commands.

## 2. Basic syntax of git worktree add

General syntax:

```bash
git worktree add <path> [<commit-ish>]
```

- `<path>` is the new working directory. You can use a relative or absolute path.
- `<commit-ish>` is the branch, tag, or commit that the worktree will check out.
- If `<commit-ish>` is an existing branch and the branch is not already checked out in another worktree, Git will use that branch.

Example creating a worktree from an existing branch:

```bash
git worktree add ../wt-payment feature/payment
```

The command creates the `../wt-payment` directory and checks out the `feature/payment` branch in that directory. The current worktree keeps its branch and state unchanged.

To quickly check which branch is checked out in the current worktree:

```bash
git branch --show-current
```

After adding a worktree, you can inspect the branch in the new directory with:

```bash
git -C ../wt-payment branch --show-current
git -C ../wt-payment status
```

The `-C` option tells Git to run the command as if the current working directory were the specified path.

## 3. Creating a worktree and a new branch with -b

If the feature branch does not exist yet, use `-b` to create a new branch at the same time as creating the worktree:

```bash
git worktree add -b feature/refactor ../wt-refactor main
```

Meaning of the components:

- `-b feature/refactor`: creates a new branch named `feature/refactor`.
- `../wt-refactor`: creates a new working directory at that path.
- `main`: uses the tip commit of the `main` branch as the starting point for the new branch.

After the command, the new worktree checks out the `feature/refactor` branch; the `main` branch in the original worktree is not moved.

If you want the new branch to start from the repository's current commit, you can omit `<commit-ish>`:

```bash
git worktree add -b feature/docs ../wt-docs
```

When no branch or commit-ish is specified, Git also has a convenience behavior that creates a new branch based on `HEAD`, with the branch name derived from the last path component of the worktree path. For example:

```bash
git worktree add ../experiment
```

Git creates a new branch named `experiment` from the current `HEAD` (if that name does not already exist). In a team workflow, prefer using `-b` explicitly so readers of the command know which branch will be created.

### Creating a worktree from a remote-tracking branch

If you want to start a feature from `origin/main`, first update remote information:

```bash
git fetch origin
git worktree add -b feature/api ../wt-api origin/main
```

The command creates a local branch `feature/api` at the commit `origin/main` points to and checks out that branch in `../wt-api`. Depending on the `branch.autoSetupMerge` setting, Git may automatically set up an upstream when the new branch starts from a remote-tracking branch. Check with:

```bash
git -C ../wt-api branch -vv
```

If the upstream has not been set, you can configure it afterward:

```bash
git -C ../wt-api branch --set-upstream-to=origin/main feature/api
```

`git fetch` updates remote-tracking branches; it does not automatically change your active local branch.

## 4. Opening an existing branch in a new worktree

If the branch was created earlier and is not checked out in any other worktree, pass the branch name as `<commit-ish>`:

```bash
git worktree add ../wt-release release/2.4
```

Git checks out the `release/2.4` branch in the new worktree. Commits created in this worktree update the shared `release/2.4` branch; when you switch to another worktree, you will see the branch has advanced.

If the branch name does not exist, Git may guess a remote-tracking branch of the same name when there is only one matching remote. To avoid accidentally creating a branch from an unintended source, specify the starting point explicitly and use `-b` when the goal is to create a new local branch:

```bash
git fetch origin
git worktree add -b feature/search ../wt-search origin/feature/search
```

The command above creates a local `feature/search` branch from the remote-tracking branch of the same name. If that local branch already exists, do not use `-b`; check its status and open the existing branch appropriately.

## 5. Creating a worktree at detached HEAD

Sometimes you only want to inspect a commit or tag without creating a branch. Use `--detach`:

```bash
git worktree add --detach ../wt-review v2.4.0
```

The new worktree checks out the contents pointed to by tag `v2.4.0`, but `HEAD` is not attached to a local branch. This approach is useful for reviewing a release, running regression tests, or comparing behavior between two commits.

You can use a commit hash instead of a tag:

```bash
git worktree add --detach ../wt-old-build a1b2c3d
```

Check the detached state:

```bash
git -C ../wt-review status
git -C ../wt-review branch --show-current
git -C ../wt-review rev-parse HEAD
```

In a detached state, `git branch --show-current` prints no branch name. If you create commits in this worktree, the commits are still stored in the object database, but they do not automatically update a named branch. Create a branch if you want to continue developing from that commit:

```bash
git -C ../wt-review switch -c review/fix
```

The command above creates the `review/fix` branch from the current commit of the review worktree.

## 6. Common worktree creation options

| Option | Effect | When to use |
|---|---|---|
| `-b <branch>` | Creates a new branch from the starting point | Opening a new feature branch in a separate directory |
| `-B <branch>` | Creates or resets a branch to the specified starting point | Only use when intentionally moving/resetting an existing branch |
| `--detach` | Checks out a commit without attaching `HEAD` to a branch | Reviewing a commit or tag independently |
| `--lock` | Locks the worktree immediately after creation | The worktree is on a removable drive or a location that may become temporarily unreachable |
| `--no-checkout` | Creates the worktree without checking out contents | Special workflows that handle the checkout step manually afterward |

Example locking a worktree immediately on creation:

```bash
git worktree add --lock -b release/test ../external/release-test main
```

A locked worktree is protected from certain automatic prune operations. When you need to unlock it:

```bash
git worktree unlock ../external/release-test
```

`-B` can reset an existing branch to the specified commit. This is an operation that affects branch history, so confirm the branch is not being used by teammates and has no commits you need to keep before using it.

## 7. Limitation: a branch cannot be checked out in multiple worktrees

By default, Git prevents the same branch from being checked out simultaneously in multiple worktrees. For example, if the main worktree is on `main`, the following command will be rejected:

```bash
git worktree add ../wt-main main
```

Git enforces this rule to prevent two working trees from updating the same branch and causing confusion about `HEAD`/index state. Create a new branch if you need an independent workspace:

```bash
git worktree add -b experiment/main-copy ../wt-main-copy main
```

Or create a detached worktree from the current commit if you only need to read/inspect:

```bash
git worktree add --detach ../wt-main-review main
```

Do not use `--force` just to bypass the warning that the branch is already checked out elsewhere. The force option can allow a situation where multiple worktrees use the same branch, but it removes the safeguard Git provides and can easily lead to overwrites or hard-to-control branch updates.

## 8. Verifying worktrees after creation

After creating one or more worktrees, view the list:

```bash
git worktree list
```

Example output:

```text
/workspace/payment-service       5ab12cd [main]
/workspace/wt-payment            7cd34ef [feature/payment]
/workspace/wt-hotfix              8ef56ab [hotfix/login]
/workspace/wt-review              5ab12cd (detached HEAD)
```

To see information in a format easier for scripts to parse:

```bash
git worktree list --porcelain
```

Inspect the status of the new worktree individually:

```bash
git -C ../wt-payment status
git -C ../wt-payment log -1 --oneline --decorate
git -C ../wt-payment branch --show-current
```

If `git worktree add` reports an error, check whether the path already exists, whether the branch is already checked out in another worktree, whether the target commit is valid, and whether directory write permissions are sufficient.

## 9. Parallel workflow with worktrees

Suppose you are working on a payment feature on `main` and need to handle a login bug immediately. You can create a worktree for the hotfix branch:

```bash
git fetch origin
git worktree add -b hotfix/login ../wt-login origin/main
```

Open `../wt-login` in another IDE or terminal, fix the bug, and create a commit:

```bash
git -C ../wt-login status
git -C ../wt-login add src/auth/LoginService.java
git -C ../wt-login commit -m "Fix login validation"
```

Meanwhile, the original worktree preserves your in-progress changes on the feature branch. After finishing the hotfix, push the branch according to the team workflow:

```bash
git -C ../wt-login push -u origin hotfix/login
```

You can continue working in the main worktree or open another worktree for a release branch. Commits are shared within the same repository; uncommitted changes in each worktree remain separate.

## 10. Path and environment notes

- The worktree path must point to a directory that can be created or an empty directory; avoid accidentally choosing a directory that already contains data.
- Place worktrees alongside the main directory, such as `../wt-payment`, to make them easy to distinguish and clean up.
- On Windows, you can use paths like `..\wt-payment`; in Git Bash, paths like `/c/work/wt-payment` can also be used depending on the environment.
- Do not copy the entire `.git` folder or manually move a linked worktree directory via Explorer/File Manager. If you need to change its location, use the appropriate worktree commands.
- If a worktree is on a removable drive, lock it before disconnecting so Git does not attempt to clean up a temporarily unreachable worktree.
- Worktrees share branches and the object database, so removing a worktree does not delete created branches or commits. However, uncommitted changes in that directory may be lost if you delete the directory.

## 11. Practice exercise

In a test repository with a `main` branch, create three worktrees in different ways:

1. Use `git worktree add -b feature/demo ../wt-demo main` to create a new branch and worktree.
2. Create a commit in `../wt-demo`, then return to the main worktree and confirm the new commit appears in `git log --all`.
3. Use `git worktree add --detach ../wt-review HEAD~1` to create a detached worktree at the parent commit.
4. Try opening the `main` branch again in another worktree and observe how Git protects the checked-out branch.
5. Run `git worktree list --porcelain` to inspect the path, HEAD, and branch of each worktree.
6. Explain the difference between separate working trees/indexes and the shared object database/branches.

You complete the exercise when you can create a worktree from an existing branch, create a new branch with `-b`, check out a commit with `--detach`, and verify the state each directory is working on.

# Branches, HEAD, remotes, and remote-tracking branches

When working with Git, we often create branches to develop features, fix bugs, or experiment without disrupting the main branch. When multiple people collaborate, each machine can have its own local branches while exchanging commits with one or more remote repositories. To coordinate safely, you need to understand which commit a branch points to, what position `HEAD` represents, what address a remote stores, and what state a remote-tracking branch reflects.

In the Git section of the source code management module, these concepts connect the workflow from the working tree, staging area, and commits to merges, rebases, remotes, and tags. Mastering them helps you collaborate through branches, recognize teammates' changes, and keep project history easy to trace.

## 1. What is a branch in Git?

A branch is a named reference pointing to a commit. For example, the `main` branch usually points to the latest commit of the primary line of development; the `feature/login` branch points to the latest commit of work on the login feature.

Branches in Git are very lightweight: creating a branch mainly creates a new reference pointing to the current commit. When you create a new commit on the active branch, Git moves that branch's reference to the new commit. Older commits are preserved and can be shared across multiple branches.

Imagine history looking like this:

```text
                 C3  main
                /
C0 --- C1 --- C2
                \
                 C4  feature/login
```

`main` and `feature/login` both start from `C2`, then develop independently. Each branch is simply a name pointing to the tip commit of that branch; a branch is not a full copy of the project directory. Git updates the working tree when you switch branches.

### Why use branches?

- **Isolate work:** a new feature can be implemented on `feature/...` without affecting `main` yet.
- **Work in parallel:** multiple people or teams can develop different parts and integrate them later.
- **Experiment and fix bugs easily:** you can create short-lived branches to try an approach, then merge or discard the branch.
- **Review changes easily:** a pull request or merge request typically compares a working branch against a target branch.
- **Keep history meaningful:** branch names describe the purpose of a line of work, helping members recognize the scope of changes.

Branch names usually use lowercase letters and hyphens or slashes, such as `feature/user-profile`, `bugfix/payment-timeout`, `hotfix/security-patch`, and `release/2.4`. Avoid vague names like `test`, `new`, or `fix` when they do not help identify the purpose.

## 2. Creating, viewing, and switching local branches

The commands below operate on branches in the current repository.

| Need | Command | Meaning |
| --- | --- | --- |
| List local branches | `git branch` | Displays local branches; `*` marks the current branch |
| Show current branch name | `git branch --show-current` | Returns the branch name if `HEAD` is attached to a branch |
| Create branch at current commit | `git branch feature/login` | Creates the branch while staying on the current branch |
| Create and switch to new branch | `git switch -c feature/login` | Creates a new branch and switches the working tree to it |
| Switch to existing branch | `git switch main` | Points `HEAD` to `main` and updates the working tree |
| Rename current branch | `git branch -m feature/authentication` | Renames the branch you are currently on |
| Delete integrated branch | `git branch -d feature/login` | Deletes the local reference once Git confirms the branch is safely merged |

Example creating a branch to work on the login feature:

```bash
git switch main
git switch -c feature/login
git branch --show-current
```

The first command switches you to `main`; the second creates `feature/login` from the current commit of `main` and switches to it. Subsequent commits will advance the tip of `feature/login`.

`git branch feature/login` only creates the branch name. If you want to work on the newly created branch, switch to it with `git switch feature/login`. The older form `git checkout -b feature/login` is still common; in modern Git, `git switch` expresses the intent of switching branches more clearly.

### Deleting branches and checking integrated branches

```bash
git branch --merged main
git branch --no-merged main
git branch -d feature/login
```

The first two commands list branches that have or have not been integrated into `main`. `git branch -d` tells Git to perform a safety check before deleting. `git branch -D feature/login` skips that check and deletes the reference even if the branch has not been merged; use it only after confirming the branch's unique commits are no longer needed. Deleting a branch does not immediately delete commit objects, though if commits are no longer referenced or reachable from elsewhere, Git may garbage-collect them later.

## 3. HEAD represents the current position

`HEAD` is a special reference indicating the repository's current working position. In the normal case, `HEAD` points indirectly to the current branch. For example, when on `main`, the logical target of `HEAD` is a reference to `refs/heads/main`; `refs/heads/main` itself points to the branch tip commit.

```text
HEAD -> refs/heads/main -> commit C3
```

When you create a new commit on `main`, Git updates `refs/heads/main` to the new commit. Because `HEAD` points to the branch name, `HEAD` automatically follows the new commit without manual adjustment.

Several commands help inspect the current position:

```bash
git status -sb
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref --short HEAD
```

`git status -sb` displays the branch and working tree status in short form. `git rev-parse --short HEAD` outputs the abbreviated hash of the current commit. `git symbolic-ref --short HEAD` outputs the reference name `HEAD` points to; this command fails when in detached HEAD state.

### What is detached HEAD?

Detached HEAD occurs when `HEAD` points directly to a commit instead of pointing to a branch name. This can happen when checking out a commit hash, a tag, or a remote-tracking branch without creating a local branch.

```bash
git switch --detach <commit-id>
```

In this state, you can still read source code, run tests, and even create commits. However, new commits do not automatically advance any local branch because `HEAD` is not attached to a branch. If you switch elsewhere without saving a reference, the newly created commits can be harder to find, though they typically remain in the reflog for a while.

If you want to keep work created in detached HEAD, create a branch at the current position:

```bash
git switch -c rescue/keep-experiment
```

This command creates `rescue/keep-experiment` pointing to the current commit and switches `HEAD` to the new branch. You can then continue committing as normal.

## 4. What is a remote?

A remote is a configured name in the local repository representing another repository, typically located on a Git server or code hosting service. The remote tells Git which address to use when fetching or pushing commits. A remote is not a branch and is not an automatically continuously synced mirror.

The name `origin` is a common convention that `git clone` creates automatically for the source repository. You can use other names such as `upstream`, `company`, or `mirror` when a project needs multiple remotes. Remote names only have meaning inside your local repository's configuration.

### Viewing and managing remotes

```bash
git remote
git remote -v
git remote add origin https://example.com/team/project.git
git remote get-url origin
git remote set-url origin https://example.com/team/project-new.git
git remote rename origin upstream
git remote remove upstream
```

- `git remote` lists configured remote names.
- `git remote -v` shows the URLs used for fetch and push. The two URLs may be the same or different.
- `git remote add` registers a new remote with a name and URL.
- `git remote get-url` reads the configured URL.
- `git remote set-url` changes the URL for an existing remote.
- `git remote rename` renames a remote configuration.
- `git remote remove` deletes the remote configuration and its corresponding remote-tracking refs in the local repository; this command does not delete the repository on the server.

Example when working with a forked repository:

```bash
git remote -v
git remote add upstream https://example.com/original/project.git
git fetch upstream
```

In this example, `origin` is usually your personal or team fork, while `upstream` is the original repository. You fetch from `upstream` to see the latest changes from the original project.

## 5. Remote branches and remote-tracking branches

On the server reside the actual branches of the repository, such as `main` or `feature/login`. When fetching, Git updates local references reflecting the latest known state of those branches from the remote. These local references are called **remote-tracking branches**.

For example, `origin/main` is the remote-tracking branch for the `main` branch on the remote named `origin`. Inside the local repository, it is typically stored as `refs/remotes/origin/main`.

Distinguish the following three items:

| Name | Where does it live? | Role |
| --- | --- | --- |
| `main` | Local repository | A local branch you can commit onto directly when checked out |
| `main` on remote `origin` | Server repository | The actual branch shared by members on the remote |
| `origin/main` | Local repository | A remote-tracking ref recording the state of `origin`'s `main` branch as of the most recent update |

`origin/main` is not a local branch for you to commit onto directly. It is a reference point for comparing or integrating changes from the remote. You can view known branches with:

```bash
git branch -r
git branch -a
```

`git branch -r` lists remote-tracking branches. `git branch -a` lists both local branches and remote-tracking branches. This list reflects the references known to your local repository; if the remote has a new branch that you have not fetched yet, that branch may not appear yet.

### Updating remote-tracking branches with fetch

```bash
git fetch origin
```

`git fetch origin` contacts the `origin` remote, downloads the required Git objects, and updates remote-tracking refs according to the fetch configuration. This command does not automatically merge or rebase changes into your active local branch, nor does it alter your working tree. Therefore, fetch is a safe step to see what is new on the remote before deciding to integrate.

To fetch information from all remotes and prune remote-tracking refs deleted on the server:

```bash
git fetch --all --prune
```

`--all` fetches from all configured remotes; `--prune` removes remote-tracking refs whose corresponding branches no longer exist on the remote per the refspec. You can use `git remote prune origin` to clean up stale refs for a single remote.

If you need to check which branches currently exist on the server without relying on the locally fetched list, you can query:

```bash
git ls-remote --heads origin
```

This command lists the branches on remote `origin` at the moment of the query. The query output does not automatically update remote-tracking refs in your local repository; use `git fetch` to update them.

## 6. Upstream and tracking relationships

A local branch can be configured to track a remote branch, often called the upstream branch. For example, local `main` can track `origin/main`; local `feature/login` can track `origin/feature/login`.

The upstream relationship tells Git which branch to compare against when displaying ahead/behind status, and provides the default source for `git pull` or the default target for certain invocations of `git push`. This relationship is a configuration between a local branch and a remote-tracking branch; it does not keep the two branches automatically synchronized.

### Setting upstream on first push

```bash
git switch -c feature/login
# edit, stage, and commit changes
git add src/
git commit -m "Add login feature"
git push -u origin feature/login
```

`git push -u origin feature/login` sends the `feature/login` branch to remote `origin` and sets the upstream for the current local branch. The `-u` option is shorthand for `--set-upstream`. Afterward, while on `feature/login`, you can run `git push` or `git pull` without repeating the remote and branch names in standard cases.

If the branch already exists and you need to attach an upstream manually:

```bash
git branch --set-upstream-to=origin/feature/login feature/login
```

Check branches and their upstreams:

```bash
git branch -vv
```

The output typically displays the tip commit of each branch, the upstream name in square brackets, and ahead/behind counts if any. Ahead/behind counts are based on your current local remote-tracking refs; fetch first if you need to compare against the latest state on the server.

You can remove a branch's upstream relationship with:

```bash
git branch --unset-upstream feature/login
```

An upstream does not have to share the exact same name as the local branch. For example, local branch `work` can track `origin/develop` if configured that way.

## 7. Distinguishing fetch, pull, and push

These three operations are frequently used when collaborating, but their goals differ.

| Command | Primary transfer direction | Typical local effect |
| --- | --- | --- |
| `git fetch origin` | Remote → local | Downloads data and updates remote-tracking refs; does not integrate into the current branch |
| `git pull` | Remote → local | Fetches and then integrates into the current branch via merge or rebase per config/options |
| `git push origin feature/login` | Local → remote | Sends commits and updates the branch on the remote if the update is accepted |

### Fetch first, inspect, then integrate

An easy-to-control workflow is:

```bash
git fetch origin
git log --oneline --graph --decorate --all -15
git status -sb
```

After fetching, you can compare local `main` with `origin/main`, inspect new commits, and decide whether to merge or rebase. For example, if local `main` only needs to fast-forward to `origin/main`:

```bash
git switch main
git merge --ff-only origin/main
```

`--ff-only` permits only fast-forward updates. If the two branches have diverged and require a merge commit or rebase, the command stops instead of choosing an integration method on its own.

### How does pull integrate changes?

`git pull` essentially performs a fetch and then integrates the upstream branch into the current branch. The integration method can be merge or rebase depending on configuration and options. You can specify the choice explicitly to make the command more predictable:

```bash
git pull --ff-only
git pull --rebase
```

`git pull --ff-only` updates only when a fast-forward is possible. `git pull --rebase` replays local commits not yet on upstream on top of the newly received commits. Rebasing changes the IDs of recreated commits; avoid carelessly rebasing commits that have already been shared and are being depended on by others.

### Pushing changes to the remote

```bash
git push origin feature/login
```

This command sends the commits pointed to by local branch `feature/login` to the branch of the same name on `origin`. If the remote already has new commits making the update non-fast-forward, Git normally rejects the push to avoid overwriting history. When that happens, fetch and integrate the necessary changes first, then push again.

## 8. Branching workflow in a team

A common workflow when developing a feature can follow these steps.

### Step 1: Update the base branch

```bash
git fetch origin
git switch main
git merge --ff-only origin/main
```

We retrieve the latest state from the remote, switch to local `main`, and fast-forward to `origin/main`. This ensures the new feature branch starts from an up-to-date base.

### Step 2: Create a working branch

```bash
git switch -c feature/user-profile
```

Create a dedicated branch for the user profile feature. The branch name communicates intent and makes it easier for the team to locate the work.

### Step 3: Commit meaningful changes

```bash
git status
git add src/main/java/
git diff --cached
git commit -m "Add user profile page"
```

Before committing, inspect the working tree and staged content. Each commit should group one change with a clear purpose so reviewing, reverting, and tracing remain easy.

### Step 4: Push the branch to the remote and set upstream

```bash
git push -u origin feature/user-profile
```

After this step, other members can fetch the branch to review or continue collaborating. You can open a pull request/merge request from `feature/user-profile` into `main` according to the project's workflow.

### Step 5: Update the branch when the team has new commits

```bash
git fetch origin
git log --oneline --left-right main...origin/main
```

While developing on a feature branch, you can integrate the latest `main` into that branch using merge or rebase:

```bash
git switch feature/user-profile
git merge origin/main
```

Or, if the team agrees on rebase and the commits on the branch have not been shared in a way where rewriting history causes disruption:

```bash
git switch feature/user-profile
git rebase origin/main
```

Merge preserves branching relationships and may create a merge commit. Rebase replays the current branch's commits onto a new base, creating new commits with new identifiers. Whichever approach you choose, stay consistent with the team's collaboration conventions.

### Step 6: Clean up branches after completion

After the pull request/merge request has been integrated, the remote branch can be deleted according to project policy. If deleting the remote branch is permitted:

```bash
git push origin --delete feature/user-profile
git fetch --prune origin
```

The first command deletes the branch on the remote; the second cleans up stale remote-tracking refs locally. Unless you need to keep the local copy for reference, delete the local branch only after confirming the work is saved and the reference is no longer needed:

```bash
git branch -d feature/user-profile
```

## 9. Relationship diagram of HEAD, local branches, and remote-tracking branches

Suppose local `main` is at commit `C3`, the feature branch is at `C4`, and the most recent fetch shows `origin/main` at `C5`:

```text
                  C3 --- C4  feature/login
                 /
C0 --- C1 --- C2
                 \
                  C5  origin/main

HEAD -> refs/heads/feature/login -> C4
refs/heads/main -----------------> C3
refs/remotes/origin/main --------> C5
```

In the diagram, `HEAD` points to the local branch `feature/login`; that branch points to `C4`. Local `main` and `origin/main` are two distinct references that can point to different commits. Fetch can move `origin/main` when the remote receives new commits, without automatically moving local `main` or changing the current branch.

After running `git switch main` and `git merge --ff-only origin/main` in a fast-forwardable case, local `main` moves to `C5`. `feature/login` still points to `C4` until you commit, merge, or rebase on that branch.

## 10. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| `origin` is a mandatory remote name | `origin` is simply a common default name; a remote can have another name |
| `origin/main` is a branch on the server | It is a remote-tracking ref stored in the local repository, reflecting the most recently fetched state |
| `git fetch` updates the working tree | Fetch updates data and remote-tracking refs; to integrate into a local branch you need merge, rebase, or pull |
| `git branch -a` always shows every branch on the server | The command only displays local branches and remote-tracking refs the repository already knows about; fetch to update |
| `HEAD` is always the current branch name | In detached HEAD state, `HEAD` points directly to a commit |
| Deleting a remote with `git remote remove` deletes the server repository | The command only removes the remote configuration and tracking references in the local repository |
| Creating a local branch means the branch is already shared | A branch exists only locally until it is pushed to a remote |

### Handling common situations

**Teammate's branch is missing:** fetch the remote and re-check the list of remote-tracking branches.

```bash
git fetch origin
git branch -r
```

**Push rejected due to non-fast-forward:** the remote has history that local has not integrated yet. Fetch, inspect differences, merge or rebase per team conventions, then push again. Do not use force push merely to make the error message go away.

```bash
git fetch origin
git log --oneline --graph --decorate --all -20
```

**Branch reports upstream is gone:** the upstream branch may have been deleted on the remote or local info is stale. Fetch with prune, inspect branches again, and decide whether to set a new upstream or drop the old configuration.

```bash
git fetch --prune origin
git branch -vv
```

**In detached HEAD but created commits you want to keep:** create a branch right at the current position to keep an explicit reference.

```bash
git switch -c rescue/save-detached-work
```

## 11. Quick inspection command set

When you need to understand what state a repository is in, you can run the following group of commands:

```bash
# Current position and working tree status
git status -sb
git branch --show-current
git rev-parse --short HEAD

# Local and remote-tracking branches
git branch -vv
git branch -a

# Remotes and URLs
git remote -v

# Update information from remotes
git fetch --all --prune

# View history across branches together
git log --oneline --graph --decorate --all -20
```

These inspection commands answer in turn: which branch you are on, which commit `HEAD` points to, which upstream each local branch tracks, which remotes are configured, and how branch histories are diverging.

## 12. Practice

Practice in a test repository to observe how references change:

1. Create a new repository or use a test repository that already has commits.
2. Create branch `feature/notes` with `git switch -c feature/notes`.
3. Create a file, stage it, and commit the change on this branch.
4. Run `git status -sb`, `git branch -vv`, and `git log --oneline --graph --decorate --all` to identify `HEAD` and branch tips.
5. Configure an appropriate remote for the test repository, then push the branch with `git push -u <remote> feature/notes`.
6. Fetch the remote again and observe `git branch -r`, `git branch -a`.
7. From another clone or with another teammate, create and push a new commit to the base branch on the remote; return to your practice repository and fetch to see how the remote-tracking branch changes.
8. Try `git merge --ff-only <remote>/<branch>` in a fast-forward scenario and observe the local branch after integration.

After practicing, explain to yourself why `feature/notes`, `<remote>/feature/notes`, and `HEAD` can point to the same commit at a given moment while still remaining distinct references.

## 13. Knowledge check

1. What object does a branch in Git point to, and what happens to the branch reference when a new commit is created?
2. How does `HEAD` differ from a local branch name? In what situation does the detached HEAD state occur?
3. What two kinds of information do `origin` and `origin/main` represent?
4. Why can `git fetch origin` update `origin/main` without modifying the working tree?
5. Which operations does an upstream branch assist with when working on a local branch?
6. How does `git pull` differ from `git fetch` in the change integration step?
7. When a push is rejected as non-fast-forward, what should you inspect and handle before pushing again?

## Conclusion

A branch is a local reference that moves along with commits; `HEAD` identifies the current position; a remote stores connection details to another repository; a remote-tracking branch records the remote branch state known locally; and an upstream specifies the remote branch a local branch tracks. Once you distinguish these entities, you can fetch to update information, inspect history before integrating, push to share work, and manage branch lifecycles in a controlled way.

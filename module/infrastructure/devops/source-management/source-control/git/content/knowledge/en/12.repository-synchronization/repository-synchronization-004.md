# Choosing Pull Behavior: Fast-Forward Only, Merge, or Rebase

When working with a remote, the `git pull` command retrieves new information from the remote and integrates the upstream branch into the current branch. If the local and remote branches have progressed in different directions, Git needs to know how to handle that history. Three common choices are allowing fast-forward only, integrating via merge, or replaying local commits via rebase.

In the **Repository Synchronization** chapter of the **SOURCE_CONTROL_GIT** module, this lesson helps you choose the pull behavior that matches how your team manages history. You will understand what happens when two branches follow the same path, when local is simply behind remote, and when both sides have separate commits; as well as how to configure defaults and handle situations where pull cannot complete.

After this lesson, you will be able to:

- Explain how pull performs fetch and upstream integration.
- Distinguish fast-forward only, merge, and rebase through commit graphs.
- Choose pull behavior based on branch state and collaboration conventions.
- Configure pull behavior at the repository or user scope.
- Inspect divergence before integrating and continue after encountering conflicts.

## 1. What Does Pull Do?

`git pull` is an operation that combines two steps:

1. **Fetch**: downloads commits and updates remote-tracking branches, such as `origin/main`.
2. **Integrate**: integrates the tracked upstream branch into the current local branch using fast-forward, merge, or rebase depending on options and configuration.

A remote-tracking branch like `origin/main` is a local reference recording the remote branch's state as of the most recent fetch. It does not change automatically just because someone else pushed; a fetch is needed to update that information.

If the current branch tracks `origin/main`, the command:

~~~bash
git pull
~~~

is typically equivalent to fetching from the configured remote and then integrating the current branch's upstream. If no upstream has been set yet, you can specify the remote and branch explicitly:

~~~bash
git pull origin main
~~~

The fetch portion can succeed even if the integration step fails. When that happens, the remote-tracking branch has been updated, while the current branch may still require you to resolve divergence or conflicts.

## 2. Identifying Three States of Local and Upstream Branches

To choose how to pull, you first need to know the relationship between the two branches. Suppose:

- `L` is the current commit of the local branch.
- `R` is the latest commit of upstream after fetching.
- The symbols L and R mark the local and upstream pointers respectively.

### Local can advance directly to upstream

~~~text
A---B---C
    ^   ^
    L   R
~~~

In the diagram, `L` is local at commit `B`, and `R` is upstream at commit `C`. Local history is an ancestor of upstream. Git only needs to move the local branch pointer forward from `B` to `C`. This is a fast-forward.

### Local has its own commits, while upstream has not advanced

~~~text
A---B---C  (local)
    ^
    upstream
~~~

Local is ahead of upstream. There are no new commits from upstream to integrate, so pull usually reports already up to date. Being ahead locally does not by itself require merge or rebase.

### Local and upstream have diverged

~~~text
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)
~~~

Both branches share common ancestor `B`, but local has `L1`, `L2` and upstream has `R1`, `R2`. It is not possible to simply move the local pointer to upstream while preserving local commits. At this point, you must decide whether to create a merge commit or rebase local commits on top of upstream. If fast-forward only is selected, Git will refuse to integrate.

You can view a summary status with:

~~~bash
git status -sb
git branch -vv
~~~

To update remote information before analyzing:

~~~bash
git fetch
~~~

Then inspect commits unique to each side:

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

Lines marked `<` are commits only on the left side (HEAD/local); lines marked `>` are commits only on the right side (upstream). If you do not yet know which upstream the current branch has, check:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

## 3. Fast-Forward Only: Integrating Only When Advancing Straight Ahead

A fast-forward occurs when the current commit is an ancestor of the upstream commit. Git simply updates the local branch pointer to the new commit; no merge commit is created and existing commits are not rewritten.

~~~text
Before:
A---B---C---D
    ^       ^
    L       R

After:
A---B---C---D  (local, upstream)
~~~

Run once:

~~~bash
git pull --ff-only
~~~

Or configure as the default for the repository:

~~~bash
git config --local pull.ff only
~~~

Fast-forward only works well when a team wants every local update to follow a straight line of history and wants immediate notification whenever local commits cause divergence. This option is especially predictable in workflows where developers regularly update their branch before creating local commits or before pushing changes to the remote.

If local and upstream have diverged, `git pull --ff-only` stops with a message stating it cannot fast-forward. Git does not automatically create a merge commit or rebase for you. After inspecting both sides, you can choose merge or rebase for that case according to team conventions.

Fast-forward only does not mean every pull creates a new commit. If local is already at the upstream commit or is ahead of upstream, no update may be needed.

## 4. Merge: Preserving Commits on Both Sides and Joining Histories

Merge integrates two branches by creating a commit with two parents when they have diverged. Both local commits and upstream commits keep their commit IDs because past history is not rewritten.

~~~text
Before:
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)

After:
      L1---L2
     /       \
A---B         M  (local)
     \       /
      R1---R2  (upstream)
~~~

Run once:

~~~bash
git pull --no-rebase
~~~

This is the merge pull option. If upstream has simply moved ahead and a fast-forward is possible, Git usually fast-forwards; if both sides have diverged, Git creates a merge commit to join the two histories.

If the repository has `pull.ff=only` set, that policy still requires fast-forward and pull will be rejected when the two branches diverge. To use merge in such a repository, adjust the fast-forward policy according to team conventions.

If you want to always create a merge commit even when fast-forward is possible, you can use:

~~~bash
git pull --no-rebase --no-ff
~~~

To set merge as the default behavior when integrating two histories:

~~~bash
git config --local pull.rebase false
~~~

Merge fits well when a team wants to preserve branching structure, needs to show explicitly when integration happened, or is collaborating on commits that have already been shared. A merge commit indicates where two lines of history were combined. In return, history may contain multiple branches and require reading the commit graph to follow.

Merge does not mean a merge commit is always created. If one side is an ancestor of the other and `--no-ff` is not requested, Git can fast-forward.

## 5. Rebase: Replaying Local Commits on Top of Upstream

Rebase takes local commits not yet present in upstream and replays them one by one on top of the latest upstream commit. The result usually produces a linear history without needing a merge commit for that integration.

~~~text
Before:
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)

After:
A---B---R1---R2---L1'---L2'  (local)
             (upstream)
~~~

Commits `L1'` and `L2'` are newly created commits produced while replaying changes. They contain the corresponding changes from the old commits but have new parents, so their commit IDs change.

Run once:

~~~bash
git pull --rebase
~~~

To set rebase as the default behavior:

~~~bash
git config --local pull.rebase true
~~~

Rebase is suitable when local commits have not yet been shared and the team wants history that is easy to read along a single straight line. When reading the log, reviewers can follow changes sequentially with fewer merge commits created purely for synchronization.

Because rebase creates new commits, you should not arbitrarily rebase commits that have already been pushed and that others rely on. Changing commit IDs of shared commits can force teammates to deal with rewritten history, re-sync branches, or encounter duplicate commits. Align with your team before rewriting published history.

Rebase also does not automatically resolve semantic conflicts. If a replayed commit does not apply cleanly onto the new base, Git pauses for you to resolve conflicts and then continue or abort the rebase.

## 6. Comparing and Choosing Pull Behavior

| Criterion | Fast-forward only | Merge | Rebase |
| --- | --- | --- | --- |
| When local is simply behind upstream | Fast-forward | Usually fast-forward | Updates on top of upstream |
| When both branches diverge | Rejects integration | Creates merge commit | Replays local commits on top of upstream |
| Preserves local commit IDs | Yes, if fast-forward succeeds | Yes | No, replayed commits get new IDs |
| History shape | Linear when successful | Preserves branch and merge structure | Usually linear |
| Best suited when | You want pull to only move straight ahead and catch divergence early | You want clear merge points recorded and shared history preserved | You want clean history and local commits are unpublished |

A practical way to choose:

- **Choose fast-forward only** if your workflow requires local not to accumulate separate commits when updating. When rejected, inspect the divergence and explicitly decide the next step.
- **Choose merge** if the team needs to preserve branch structure, or local commits have already been shared and history must be kept intact.
- **Choose rebase** if local commits belong solely to your own work and the team prefers linear history.

No option is automatically right for every repository. Behavior should reflect how the team shares commits, performs reviews, and releases. If conventions are unclear, inspect status and talk with the team before altering published history.

## 7. Configuring Pull per Repository or User

Behavior can be configured specifically for a repository using `--local`, or as the default across your user repositories using `--global`.

**Require fast-forward only**

~~~bash
git config --local pull.ff only
~~~

**Choose merge when branches diverge**

~~~bash
git config --local pull.rebase false
~~~

**Choose rebase when branches diverge**

~~~bash
git config --local pull.rebase true
~~~

The commands above are distinct configuration choices. Choose according to your repository's policy rather than setting conflicting values and relying on implicit behavior.

Change `--local` to `--global` if you want to apply the default across your user repositories. Pick exactly one command matching the desired policy:

- Allow fast-forward only:

~~~bash
git config --global pull.ff only
~~~

- Use merge when branches diverge:

~~~bash
git config --global pull.rebase false
~~~

- Use rebase when branches diverge:

~~~bash
git config --global pull.rebase true
~~~

You can check current configuration values and which config file supplied them:

~~~bash
git config --show-origin --get-regexp '^(pull\.(ff|rebase)|branch\..*\.rebase)$'
~~~

Git also supports configuring rebase per branch via `branch.<name>.rebase`. This is useful when a repository has remote-tracking branches whose workflows differ by branch. When using per-branch configuration, inspect the branch name and upstream to know exactly which rule applies.

## 8. Choosing Behavior for a Single Pull

Command-line options let you decide specifically for the current run:

~~~bash
git pull --ff-only
git pull --no-rebase
git pull --rebase
~~~

If you want a merge commit even when fast-forward is possible:

~~~bash
git pull --no-rebase --no-ff
~~~

Specifying options directly on the command line is suitable when handling a special situation without changing repository defaults. When pulling from a specific remote and branch, you can write:

~~~bash
git pull --rebase origin main
~~~

To avoid depending on configuration of unclear origin, inspect your configuration and use explicit options when needed. Command-line options apply to that invocation only; they do not modify values saved in config.

## 9. Safe Workflow Before and After Pulling

### Step 1: check the working tree

~~~bash
git status
~~~

If there are uncommitted changes, identify which task they belong to. Commit completed changes or stash work in progress before pulling if the integration step might touch those files. Never start with a pull before knowing what the working tree contains.

### Step 2: fetch to see the latest upstream

~~~bash
git fetch
git status -sb
~~~

Fetch updates the remote-tracking branch without integrating changes into the current branch. This lets you inspect the state on both sides before deciding.

### Step 3: inspect commits unique to each side

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

If local has no separate commits and is only behind upstream, fast-forward is sufficient. If both sides diverged, use team conventions to pick merge or rebase. If local is ahead and upstream has no new commits, no integration is needed.

### Step 4: pull with an explicit choice

~~~bash
git pull --ff-only
~~~

Or replace with `--no-rebase` or `--rebase` depending on your decision. Do not run all three commands back to back as trial-and-error; each command represents a different integration approach.

### Step 5: verify the result

~~~bash
git status
git log --oneline --graph --decorate -12
~~~

Confirm the working tree is clean or retains only expected changes, and the commit graph reflects the chosen integration method. Run relevant tests before continuing work or pushing.

## 10. Handling Conflicts During Pull

Merge and rebase can pause midway if Git cannot combine changes automatically.

**If pull is performing a merge**, check status, edit the conflicted files, then stage and continue:

~~~bash
git status
git add -- path/to/file
git merge --continue
~~~

If you decide to cancel the merge in progress:

~~~bash
git merge --abort
~~~

**If pull is performing a rebase**, after editing files and staging:

~~~bash
git status
git add -- path/to/file
git rebase --continue
~~~

If you want to cancel the rebase and return to the state before the rebase began:

~~~bash
git rebase --abort
~~~

Read `git status` to know whether Git is in the middle of a merge or a rebase; only use the corresponding continue or abort command. After resolving, inspect the log again and run tests. Fast-forward only does not start a merge or rebase when rejected due to divergence, so there is normally no partial integration process to continue or abort.

## 11. Common Confusions

### Are fast-forward and merge mutually exclusive choices?

No. Fast-forward is a way of updating the pointer when history permits. A pull mode using merge can still fast-forward if there is no divergence. Only when two branches diverge does merge need to create a commit joining both sides.

### Does rebase lose local changes?

Rebase replays local commits onto a new base and creates new commits. If conflicts arise, Git pauses for the developer to decide. However, because history is rewritten, check status before starting and avoid rebasing shared commits without agreement.

### Does a rejected fast-forward only mean fetch failed?

No. Fetch may have succeeded and updated the remote-tracking branch. The integration step was rejected because local and upstream diverged. Inspect the log on both sides and choose merge or rebase according to conventions.

### Does setting pull.rebase=true always create new commits?

No. If there are no local commits to replay or local is simply behind upstream, Git can update without recreating local commits. Rebase only creates new commits for local commits that are replayed.

### Is changing global configuration right for every project?

Not necessarily. Teams may follow different conventions. Local configuration allows a repository to follow its own policy; command-line options allow choosing an integration method for a specific run.

## 12. Self-Check on Pull Choices

Suppose after fetching, the commit graph is:

~~~text
      C---D  (current feature)
     /
A---B
     \
      E---F  (origin/feature)
~~~

Answer these questions:

1. Why cannot `git pull --ff-only` integrate this state?
2. If C and D are only unshared local commits and the team wants linear history, which command should you choose?
3. If C and D have already been shared and the team wants to preserve commit IDs, which approach should you choose?
4. After pull is rejected by fast-forward only, which step helps inspect commits unique to each side?

**Hint:** The two branches diverged from B, so fast-forward is not possible. If local commits are unshared and the team chooses linear history, use `git pull --rebase`. If commits are already shared and history must be preserved, use `git pull --no-rebase` to merge. After fetching, use `git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'` to inspect commits unique to each side.

## Conclusion

Choose pull behavior based on the relationship between local and upstream along with your team's collaboration conventions. Fast-forward only detects divergence and permits only straight advancement; merge preserves both lines of history and joins them with a merge commit when needed; rebase replays local commits onto upstream to create linear history while changing commit IDs. Checking the working tree, fetching, and reading the commit graph before integrating will help you choose the right method and handle conflicts under control.

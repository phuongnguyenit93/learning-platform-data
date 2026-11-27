# Merging with a Merge Commit and Choosing `--ff-only`, `--no-ff`

When integrating a branch into the current branch, Git can either **move the ref via fast-forward** or **create a merge commit** to record the integration point of two lines of history. Which one Git chooses depends on the relationship between the two tips and the policy you request with `--ff`, `--ff-only`, or `--no-ff`.

These three options determine the shape of the history, not which code content is right. Regardless of the choice, you still need to verify the source branch, working tree status, merge result, and any conflicts.

This lesson belongs to the **Branch Merging** chapter of SOURCE_CONTROL_GIT. The content focuses on fast-forward conditions, merge commit structure, differences among the three options, default configuration, and workflows for selecting the right policy for each branch.

## 1. Two Ways Git Can Integrate a Branch

Suppose `main` and `feature/login` both start from commit `B`. The feature branch has two additional commits `C` and `D`; meanwhile, `main` has no new commits:

```text
A---B---C---D  feature/login
    ^
    main
```

The tip of `main` is an ancestor of the tip of `feature/login`. Git can update `main` from `B` to `D` without creating a new commit. This is a **fast-forward**.

If `main` also has its own commits:

```text
      E---F  main
     /
A---B
     \
      C---D  feature/login
```

The two branches have diverged. It is not possible to simply move `main` to `D` while keeping commits `E` and `F` in history. Git needs to create a merge commit (or the user chooses another workflow such as rebase).

### 1.1. Fast-forward

Fast-forward simply moves a branch ref to an existing commit:

```text
Before:
A---B---C---D  feature/login
    ^
    main

After:
A---B---C---D  main, feature/login
```

No new commit is created. The OID of `D` does not change; only the `main` ref is updated from `B` to `D`.

### 1.2. Merge commit

When two branches diverge, Git combines the two lines of history with a new commit:

```text
      E---F------M  main
     /          /
A---B          /
     \        /
      C---D---   feature/login
```

Commit `M` is a merge commit with two parents:

1. The first parent is the tip of the checked-out branch before the merge (`F` on `main`).
2. The second parent is the tip of the branch being merged in (`D` on `feature/login`).

The tree of `M` is the resulting merged snapshot. It can contain changes from both branches as well as edits you made while resolving conflicts.

## 2. Condition for Fast-Forward

A merge can fast-forward when the tip of the current branch is an ancestor of the source branch tip. If you are on `main` and want to merge `feature/login`, the condition is:

```bash
git merge-base --is-ancestor HEAD feature/login
```

Exit status `0` means `HEAD` is an ancestor of `feature/login`, so fast-forward is possible. Exit status `1` means there is no ancestry relationship in that direction; the merge cannot fast-forward this way. Other codes may indicate revision resolution or repository errors.

Check the reverse direction to see whether the source branch is already in the current history:

```bash
git merge-base --is-ancestor feature/login HEAD
```

If this command returns `0`, `feature/login` is already an ancestor of `HEAD`; typically there is nothing new to integrate and Git reports `Already up to date`.

### 2.1. Checking How Many Unique Commits Each Side Has

```bash
git rev-list --left-right --count HEAD...feature/login
```

The command returns two numbers:

- The number of commits reachable only from the left side (`HEAD`).
- The number of commits reachable only from the right side (`feature/login`).

For example, `0  3` indicates that `HEAD` has no unique commits relative to feature and feature has three commits not yet in `HEAD`; this is a situation where fast-forward can occur if no other constraints apply. A result of `2  3` shows that both sides have unique commits, meaning they have diverged.

### 2.2. Updating Remote Information Before Deciding

If the source branch resides on a remote, fetch first so the remote-tracking ref reflects the latest state received locally:

```bash
git fetch origin
git log --graph --oneline --decorate --all
```

Example of merging `origin/feature/login` into `main`:

```bash
git switch main
git merge --ff-only origin/feature/login
```

`origin/feature/login` is a local ref updated by the most recent fetch; it does not query the server when `git merge` is invoked.

## 3. Default Behavior and the `--ff` Option

The `--ff` option allows fast-forward when possible. If the two branches have diverged, Git creates a merge commit following the standard merge process.

```bash
git switch main
git merge --ff feature/login
```

This is the common default behavior when `merge.ff` has not been configured otherwise:

- If `HEAD` is an ancestor of the source branch, move the ref (fast-forward).
- If the two branches have diverged, create a merge commit after merging content.
- If the source branch is already integrated, create no new commit.

`--ff` does not mean "only allow fast-forward." If fast-forward is not possible, Git can still create a merge commit. To reject when the two branches have diverged, use `--ff-only`.

## 4. Allowing Fast-Forward Only with `--ff-only`

`--ff-only` instructs Git to update the branch only if a fast-forward is possible. If the two branches have diverged, Git stops and reports that it cannot fast-forward; it neither creates a merge commit nor rebases automatically.

```bash
git switch main
git merge --ff-only feature/login
```

### 4.1. When Fast-Forward Succeeds

Before:

```text
A---B---C  feature/login
    ^
    main
```

After `git merge --ff-only feature/login`:

```text
A---B---C  main, feature/login
```

`main` moves to `C`. No new merge commit is created.

### 4.2. When Two Branches Have Diverged

```text
      E---F  main
     /
A---B
     \
      C---D  feature/login
```

The command:

```bash
git merge --ff-only feature/login
```

will be rejected because `main` has commits `E` and `F` that are not in the history of `feature/login`. Git leaves the branch unchanged and requires you to resolve the history relationship first.

Next options might include:

- Fetch and review history, then use a merge commit if policy allows.
- Rebase the feature branch onto the new base, then try fast-forward.
- Have the team update branches according to the agreed integration workflow.

Do not use `reset --hard` or force push just to make `--ff-only` succeed. First understand which commits exist on each side.

### 4.3. When Should You Use `--ff-only`?

`--ff-only` is appropriate when the team wants the target branch to have a linear history and all integrated changes must be prepared beforehand so the branch can advance to the new tip without a merge commit. For example:

- Updating a local branch from an upstream branch organized linearly.
- Syncing a deployment branch where policy forbids merge commits.
- Verifying a branch can advance to a new tip without resolving diverged history.
- Using in scripts to avoid unintentionally creating merge commits.

If policy requires a merge commit for every feature integration, `--ff-only` is not suitable.

## 5. Forcing a Merge Commit with `--no-ff`

`--no-ff` requires creating a merge commit even when Git could fast-forward. This records an explicit integration point and preserves the boundary between the target branch and the feature branch in the commit graph.

```bash
git switch main
git merge --no-ff feature/login
```

### 5.1. When Fast-Forward Is Possible

Before:

```text
A---B---C---D  feature/login
    ^
    main
```

With `--no-ff`, Git creates merge commit `M`:

```text
A---B---------M  main
     \       /
      C---D     feature/login
```

`M` has two parents: `B` and `D`. The tree of `M` is usually identical to the tree of `D` when there are no additional edits or conflict resolutions, but the OID of `M` differs because it has two parents and its own metadata.

### 5.2. When Two Branches Have Diverged

If both branches already have separate commits, a standard merge already requires creating a merge commit. In that situation, `--no-ff` does not change the fundamental outcome compared to the default `--ff`: Git still creates a merge commit after combining the two lines of history.

The key difference of `--no-ff` appears when a fast-forward is possible. It forces recording a merge commit instead of merely moving the ref.

### 5.3. When the Source Branch Is Already Integrated

If the source branch tip is already an ancestor of `HEAD`, Git reports `Already up to date`. `--no-ff` does not create a new merge commit merely to record a merge with no new changes.

### 5.4. Why Do Teams Choose `--no-ff`?

Some benefits:

- History clearly shows where a feature branch was integrated.
- Integration history can be read via `git log --first-parent`.
- A group of feature commits can be viewed as a single integration unit.
- Reverting an integration can be organized around the merge commit, provided the mainline parent is understood correctly.
- Auditing or release review can easily identify feature boundaries.

In return, history contains extra merge commits and a more branched graph. For small features or teams wanting linear history, creating a merge commit for every integration can make the log longer and harder to scan.

## 6. Comparing `--ff`, `--ff-only`, and `--no-ff`

| Option | If fast-forward is possible | If the two branches have diverged | If source branch is already in HEAD |
|---|---|---|---|
| `--ff` | Fast-forwards, no new commit created. | Creates a merge commit. | Does nothing (`Already up to date`). |
| `--ff-only` | Fast-forwards, no new commit created. | Refuses, no merge commit created. | Does nothing (`Already up to date`). |
| `--no-ff` | Creates a merge commit. | Creates a merge commit. | Creates no new commit. |

Summary:

- Want Git to automatically choose fast-forward when possible and merge commit when needed: use `--ff` (typically the default).
- Want to allow fast-forward only, stopping otherwise: use `--ff-only`.
- Want to preserve a merge commit for an integration even when fast-forward is possible: use `--no-ff`.

## 7. Default Configuration via `merge.ff`

You can configure default merge behavior in Git config:

```bash
git config --get merge.ff
```

Common values:

| Value | Equivalent behavior |
|---|---|
| `true` | Allows fast-forward when possible; if diverged, creates a merge commit. |
| `false` | Equivalent to `--no-ff`. |
| `only` | Equivalent to `--ff-only`. |

Set for the current repository:

```bash
git config --local merge.ff only
```

Set for all repositories of the user:

```bash
git config --global merge.ff false
```

Inspect configuration source:

```bash
git config --show-origin --show-scope --get merge.ff
```

If no value is configured, the default behavior is to allow fast-forward when possible. Options specified directly on the command line such as `--ff`, `--ff-only`, or `--no-ff` choose the behavior for a single merge and override the default configuration.

### 7.1. Choosing the Right Scope

- `--local`: affects only the current repository.
- `--global`: affects the user's repositories, unless overridden by another configuration level.
- `--system`: affects the entire system and usually requires administrative privileges.

Merge policies vary across personal branches, integration branches, and release branches. Local configuration is usually more suitable when only one repository has specific requirements.

### 7.2. `merge.ff` and `pull.ff`

`git merge` uses `merge.ff`. `git pull` can have its own `pull.ff` setting to control the fast-forward behavior of the post-fetch integration step. If you notice `git merge` and `git pull` behaving differently, check both settings:

```bash
git config --show-origin --get merge.ff
git config --show-origin --get pull.ff
```

Do not assume every `merge.ff` setting is the only configuration affecting `git pull`.

## 8. Reviewing a Merge Before Creating the Commit

In some workflows, teams want to inspect the merged snapshot and run tests before recording a merge commit. Use:

```bash
git merge --no-commit --no-ff feature/login
```

`--no-commit` tells Git to stop before the merge commit creation step. Combine `--no-ff` to ensure Git does not fast-forward; fast-forward creates no commit, so there is no pre-commit pause point.

After the merge is prepared:

```bash
git status
git diff --cached --stat
git diff --cached
git diff
```

Run tests and inspect the snapshot. If the result is correct, finish:

```bash
git commit
```

If you need to cancel the paused merge:

```bash
git merge --abort
```

Before merging, preserve any local modifications. Uncommitted changes can cause the merge to be rejected or make returning to the initial state more complicated.

## 9. Handling Conflicts When Creating a Merge Commit

When two branches modify the same content region in a way Git cannot combine automatically, the merge stops for you to resolve conflicts. The `--ff`, `--ff-only`, and `--no-ff` policies do not resolve conflicts by themselves; they determine how history is updated once the merge can complete.

Check status:

```bash
git status
git ls-files -u
```

Open the conflicted file, choose or combine the desired content, then stage the result:

```bash
git add -- src/login.js
```

Once all conflicts are resolved:

```bash
git diff --cached
git merge --continue
```

If your Git version or merge state requires completing directly with a commit, `git commit` can also be used to record the merge commit. Do not commit until all conflicted paths have been resolved and staged.

To cancel the merge:

```bash
git merge --abort
```

## 10. Verifying the Merge Type After Completion

### 10.1. Inspecting the History Graph

```bash
git log --graph --oneline --decorate --all
```

Fast-forward advances the branch ref to an existing commit; there is no new merge node. A merge commit creates a new node joining two lines of history.

### 10.2. Checking Parents of HEAD

```bash
git rev-list --parents -n 1 HEAD
```

The output consists of the commit OID first, followed by parent OIDs:

- One parent: a regular commit (or a content-empty commit).
- Two parents: a standard merge commit.
- Three or more parents: an octopus merge or multi-input merge.
- No parents: a root commit.

### 10.3. Inspecting the Raw Merge Commit

```bash
git show --no-patch --pretty=raw HEAD
```

Inspect the `parent` lines to identify the first and second parents. The first parent is usually the tip of the target branch before the merge; the second parent is the tip of the source branch.

### 10.4. Reading Integration History via First-Parent

```bash
git log --first-parent --oneline --decorate main
```

If the team uses `--no-ff`, first-parent history helps you see the merge commit milestones on the main branch without diving into every commit inside feature branches.

### 10.5. Comparing the Merge Result Against Each Parent

```bash
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
```

The first command shows how the merge result differs from the target branch before the merge. The second command shows how the result differs from the source branch. With fast-forward, there is no new merge commit with two parents to inspect; check which commit the ref now points to.

## 11. Merge Commits and Reverting

A merge commit has multiple parents, so reverting it requires selecting the mainline parent. For example, to undo the integrated content on `main`:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` selects the first parent as the mainline. Git creates a new commit reversing the merge's changes relative to that parent; it does not delete the merge commit from history.

If you pick the wrong parent, the reversed content may not match your intent. Before reverting, inspect:

```bash
git show --no-patch --pretty=raw <merge-commit>
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
```

Fast-forward does not create a merge commit, so there is no single merge node to revert with `-m`. If you need to undo fast-forwarded commits, you typically revert the individual commits involved or create an appropriate corrective commit.

## 12. Choosing a Policy Based on Team Workflow

| Situation | Suggested option | Reason |
|---|---|---|
| Want linear history and stop if branches diverge | `--ff-only` | Avoids unexpected automatic merge commits. |
| Want Git to fast-forward when possible, merge commit when needed | `--ff` | Flexible, and is the common default behavior. |
| Want every feature integration to have its own milestone | `--no-ff` | Preserves the merge node and feature boundaries. |
| Main branch only accepts commits already rebased onto latest tip | `--ff-only` | Confirms target branch can advance directly to feature tip. |
| Need per-integration auditing | `--no-ff` | Easy to filter merge commits and first-parent history. |
| Script only permitted to update linearly | `--ff-only` | Rejects when history unexpectedly diverges. |

No single policy fits every repository. Agree on conventions with your team and apply them consistently on integration/release branches.

## 13. Practical Workflow: Integrating a Feature into Main

Suppose `feature/login` is complete and needs to be integrated into `main` with a merge commit to preserve the feature boundary.

**Step 1: Ensure local state is clear**

```bash
git status --short --branch
```

Commit or stash changes you want to keep before merging.

**Step 2: Update the source branch from remote if needed**

```bash
git fetch origin
git log --graph --oneline --decorate --all
```

**Step 3: Switch to the target branch**

```bash
git switch main
```

**Step 4: Check the history relationship**

```bash
git rev-list --left-right --count HEAD...feature/login
git merge-base HEAD feature/login
```

**Step 5: Create a merge commit even if fast-forward is possible**

```bash
git merge --no-ff feature/login
```

If conflicts occur, resolve each file, stage the result, and continue the merge.

**Step 6: Verify the result**

```bash
git log --graph --oneline --decorate -10
git rev-list --parents -n 1 HEAD
git show --stat --oneline HEAD
git status --short --branch
```

If team policy requires linear history, replace Step 5 with:

```bash
git merge --ff-only feature/login
```

The command will stop if the branches have diverged, allowing the team to handle history before integrating.

## 14. Common Mistakes

### 14.1. `--ff-only` Is Rejected

The two branches have diverged, or the current tip is not an ancestor of the source branch. Fetch, inspect the graph, and decide between a merge commit or rebase per policy. Do not reset or force push just to bypass the warning.

### 14.2. Using `--ff` Yet a Merge Commit Still Appears

This is normal behavior if the two branches have diverged. `--ff` only fast-forwards when possible; it does not forbid merge commits.

### 14.3. Using `--no-ff` Yet No New Merge Commit Appears

If the source branch is already in HEAD's history, Git reports `Already up to date`. There are no new changes to integrate, so `--no-ff` does not create an empty commit.

### 14.4. Assuming `--no-commit` Always Pauses Before a Commit

Fast-forward creates no commit, so `--no-commit` cannot pause before a commit that does not exist. Use `--no-commit --no-ff` when you need to inspect the result in a merge commit.

### 14.5. Global Config Overriding Repository Expectations

Check `merge.ff` with `--show-origin` and `--show-scope`. Use command-line options to choose behavior for a single merge, or set local config for repositories needing a specific policy.

### 14.6. Confusing a Merge Commit with a Squash Merge

A squash merge prepares changes in the index/working tree for you to create a regular commit; that commit does not have a parent pointing to the feature tip. If you need to record the relationship between two lines of history, use a merge commit.

## 15. Takeaways

- Fast-forward only moves the ref to an existing commit; no new commit is created.
- A merge commit creates a new commit with at least two parents, recording two or more lines of history.
- `--ff` allows fast-forward when possible; if branches diverge, Git creates a merge commit.
- `--ff-only` allows fast-forward only; if branches diverge, Git refuses and does not auto-rebase.
- `--no-ff` creates a merge commit even when fast-forward is possible; if already up to date, no new commit is created.
- The first parent of a merge commit is usually the tip of the target branch before the merge; the second parent is the tip of the source branch.
- `merge.ff=true`, `false`, `only` correspond to `--ff`, `--no-ff`, `--ff-only` as default behavior.
- Command-line options override configuration; `git pull` can also be affected by `pull.ff`.
- `--no-commit` must be combined with `--no-ff` if you want to be sure to pause before a merge commit.
- Use `git rev-list --parents`, `git show --pretty=raw`, and `git log --graph` to verify history.
- When reverting a merge commit, you must choose the right mainline parent with `git revert -m`.

Choose `--ff-only` when you need to protect linear history, `--no-ff` when you need to preserve integration milestones, and `--ff` when you want Git to choose based on the ancestry relationship. Most importantly, inspect the graph and understand what commit will be created before updating shared branches.

# When to use rebase and when to preserve the graph with merge

When a feature branch is developed in parallel with `main`, both branches can advance and form two diverged histories. Git provides two common ways to integrate them: **merge** combines existing histories, while **rebase** replays a branch's commits onto a newer base commit.

Both approaches can produce the same working tree content while generating different commit graphs. Choosing the right one depends on whether the branch is used by others, how much integration history the team wants to preserve, and the repository's history policy.

## 1. Understanding both integration approaches through the commit graph

Suppose `main` and `feature/payment` both originate from commit `B`. Later, `main` receives commit `C`, while the feature branch has two commits `D` and `E`:

```text
      D---E  feature/payment
     /
A---B---C    main
```

The two branches have diverged because each has commits that the other does not.

### Merge: keeping commits and connecting two histories

If you are on the feature branch and run:

```bash
git switch feature/payment
git merge main
```

Git combines the two branches with a merge commit `M` (if a fast-forward is not possible):

```text
A---B---C-------M  feature/payment
     \         /
      D---E---/
```

The merge commit has two parents: one is the tip of the current branch before the merge (`E`), and the other is the tip of the integrated branch (`C`). Commits `D`, `E`, and `C` keep their original identifiers. The graph clearly shows when the two histories were combined.

If the current branch's tip is an ancestor of the merged branch, Git can simply move the branch pointer forward. This is called a **fast-forward merge** and does not create a merge commit. To always record a merge commit even when fast-forward is possible, use `--no-ff`.

### Rebase: replaying commits onto a new base

Instead of merging `main` into the feature branch, you can replay the feature branch's commits onto `main`:

```bash
git switch feature/payment
git rebase main
```

Git takes the changes from `D` and `E`, then creates new commits `D'` and `E'` on top of `C`:

```text
A---B---C---D'---E'  feature/payment
```

The history becomes linear. However, `D'` and `E'` are new commits with different identifiers from `D` and `E`, because their parents have changed. Rebase does not move old commits; it creates replacement commits and updates the current branch to the new chain.

## 2. Key differences between merge and rebase

| Criterion | Merge | Rebase |
|---|---|---|
| How it works | Combines two histories via a merge commit or fast-forward | Replays the current branch's commits onto a new base |
| Old commit IDs | Preserved | Replayed commits get new IDs |
| History graph | Can retain branching paths and merge commits | Usually produces a linear history |
| Integration trail | Merge commit records where two branches joined | No merge commit for a standard replay |
| Conflict handling | Resolved once during the merge | May need to be resolved across multiple replayed commits |
| Best suited for | Shared branches, integration branches, or when a merge trail is needed | Unshared personal branches to update the base and keep history clean |

Merge does not automatically clutter history: if a fast-forward is possible, Git only moves the branch pointer. Nor does rebase automatically make history better: if the team needs to know through which steps a branch was integrated, a merge commit can provide important information.

## 3. When should you use rebase?

Rebase is usually suitable in the following situations:

- **The feature branch is managed only by you.** You can replay your commits without altering history that teammates rely on.
- **Updating a feature branch before opening a pull request.** Bring new commits from `main` underneath the feature commit chain to test your changes on the latest base.
- **The team requires linear history.** After rebasing, the branch can be integrated via fast-forward if `main` has not moved further.
- **Organizing commits before sharing.** `git rebase -i` lets you reorder, squash, edit, or drop commits within a selected range.

Example of updating a personal branch onto `origin/main`:

```bash
git switch feature/payment
git status
git fetch origin
git rebase origin/main
```

After rebasing, inspect the history and content:

```bash
git log --oneline --graph --decorate --all
git diff origin/main...HEAD
```

If the branch has never been pushed and checks pass, you can open a pull request or integrate according to your team's workflow. If the branch was already pushed but you are certain only you use it, updating the remote may require `--force-with-lease` per team policy; see the section on shared branches below.

Rebase is also useful when using `git pull --rebase` to update a personal branch:

```bash
git pull --rebase origin main
```

This command fetches changes from `origin` and then rebases local commits not yet on `origin/main` on top of that branch. Run it while on the branch you want to update and when you clearly understand which local commits will be replayed.

## 4. When should you use merge?

Merge is appropriate when history is already shared or when the integration event itself is information worth keeping:

- **Branches worked on by multiple people.** Preserves existing commit IDs so other clones do not have to deal with rewritten history.
- **Release, integration, or shared branches.** Merge records when and which two sides were combined.
- **When you need a trail of a pull request or integration.** A merge commit shows the convergence point of the feature branch and the target branch.
- **Updating a shared branch from `main` without rewriting commits.** Merging `main` into the current branch keeps existing commits intact.

Example of syncing a feature branch already used by multiple people:

```bash
git switch feature/payment
git fetch origin
git merge origin/main
```

If the two branches diverged, Git creates a merge commit after you resolve conflicts. Commits that teammates created on the branch retain their IDs. You can then push the updated branch following your team's workflow.

When integrating a feature branch into `main`, the team can choose one of the policies. If the repository allows fast-forward:

```bash
git switch main
git merge --ff-only feature/payment
```

If the team wants to always create a merge commit to record the integration:

```bash
git switch main
git merge --no-ff feature/payment
```

Choose the command matching the repository convention. Do not use `--no-ff` if the team intentionally keeps linear history; conversely, do not force fast-forward if a merge commit is a required audit trail.

## 5. Important rule for shared branches

Rebase changes the commit IDs of the replayed commits. If you rebase a branch that others have already checked out or built commits on top of, their history will no longer connect cleanly with the new history. They may have to rework commits, create duplicate commits, or perform complex recovery steps.

Therefore, the safe collaboration rule is:

- Rebase personal branches when no one else is building on those commits.
- Use merge to update shared branches or branches teammates are actively using.
- Do not rebase published stable branches like `main` or `release`, unless the team has an explicit history-rewriting procedure and has coordinated with everyone involved.

If a personal branch has already been pushed and you need to update it after a rebase, `--force-with-lease` helps avoid overwriting a remote update you have not fetched yet:

```bash
git fetch origin
git push --force-with-lease origin feature/payment
```

This option checks that the remote ref is still in the state your local repository expects before updating. It reduces the risk of overwriting new work on the remote, but it does not make rewriting a shared branch safe for people who already built on the old history. Only use it when the branch is truly under your control and the team permits rewriting history.

Avoid using `git push --force` as a default workaround. Force pushing can wipe out new commits that others have pushed to the remote.

## 6. Conflicts during merge and rebase

Both merge and rebase can encounter conflicts. The difference is that merge combines two branch tips in a single operation, whereas rebase replays commits one by one. If multiple replayed commits touch the same area of content, rebase can pause at multiple different steps.

### Resolving conflicts during merge

```bash
git switch feature/payment
git merge origin/main
```

If there are conflicts:

```bash
git status
# Open the files, combine the contents, and remove conflict markers
git add <resolved-file>
git merge --continue
```

If you decide not to continue the merge:

```bash
git merge --abort
```

### Resolving conflicts during rebase

```bash
git switch feature/payment
git rebase origin/main
```

When Git pauses at a commit:

```bash
git status
# Open the files, combine the contents, and remove conflict markers
git add <resolved-file>
git rebase --continue
```

If you want to skip the current commit, only use `git rebase --skip` once you have verified the commit's changes are no longer needed. If you want to cancel the entire in-progress rebase:

```bash
git rebase --abort
```

`--abort` restores the branch to the state before the rebase started. Before starting a merge or rebase, check `git status` and save uncommitted changes to avoid mixing unfinished work into the integration operation.

## 7. What if the branch already contains merge commits?

A standard rebase replays commits linearly and does not preserve intermediate merge commits on the branch. If a feature branch already has its own merge structure and that structure matters, consider preserving it with merge or using the advanced mode:

```bash
git rebase --rebase-merges origin/main
```

`--rebase-merges` instructs Git to attempt to recreate the merge structure when replaying history. The result is still a rewritten history; new merge commits may have different IDs and conflicts still need to be resolved. This option does not turn rebase into an operation that preserves all old commits intact.

If the goal is to preserve the exact integration graph that occurred and avoid changing commit IDs, a normal merge is usually easier to understand and less surprising.

## 8. Choosing in real-world workflows

| Situation | Usually suitable choice | Reason |
|---|---|---|
| Personal feature branch, not yet pushed | Rebase onto `origin/main` | Refreshes the base and keeps history linear |
| Personal feature branch already pushed, no one else depends on it | Can rebase if the team allows it | Requires a controlled remote update after rewriting history |
| Feature branch shared by multiple people | Merge `origin/main` into the branch | Preserves everyone's existing commit IDs |
| Pull request integration requiring an audit trail | Merge commit or platform merge policy | Records the convergence point of two histories |
| Repository requiring linear history | Rebase private branch before integrating, then fast-forward | Avoids creating unnecessary merge commits |
| Published release branch | Merge according to release policy | Keeps shared history stable |

Before deciding, ask yourself three questions:

1. Has anyone else pulled commits from this branch or started developing on top of it?
2. Does the team need to keep merge commits to trace integrations?
3. Does the repository require linear history or allow a branched graph?

If the branch is already shared and there is no history-rewriting process, merge is usually the less disruptive option. If the branch is still private and the team prefers linear history, rebase is usually appropriate.

## 9. Practice exercise

Create a test repository with `main` and `feature/demo` branches. Create one commit on `main`, then create two commits on `feature/demo`; finally switch back to `main` and create another commit so the two branches diverge.

1. Use `git log --oneline --graph --decorate --all` to inspect the graph before integration.
2. Create a test branch from `feature/demo`, then merge `main` into that branch. Observe the merge commit and the old commit IDs.
3. Create another test branch from `feature/demo`, then rebase that branch onto `main`. Compare the commit IDs before and after the rebase.
4. Try creating conflicts in both approaches. Note how many times Git pauses to ask for resolution and how to continue or abort the operation.
5. Explain how you would choose between merge and rebase if `feature/demo` were a personal branch, and then change your answer if that branch were used by three team members.

You have completed the exercise when you can read the commit graph, explain why rebase creates new commit IDs, and choose the right strategy based on how widely the branch is shared.

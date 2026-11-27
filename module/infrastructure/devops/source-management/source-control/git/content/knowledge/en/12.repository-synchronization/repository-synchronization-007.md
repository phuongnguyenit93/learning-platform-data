# Non-Fast-Forward Rejection: Causes and How to Handle It

When `git push` is rejected with a `non-fast-forward` message, Git is protecting the history already on the remote. The commit you intend to push does not contain the latest commit currently on the target branch, so updating the branch pointer normally would drop part of the remote history from that branch. The safe approach is to refresh remote information, inspect what changed on both sides, integrate the commits that need to be kept, and then push again.

## 1. What Are Fast-Forward and Non-Fast-Forward?

Every Git branch points to a commit. During a push, Git checks the relationship between the remote branch's current commit and the new commit the client wants to send.

A **fast-forward** occurs when the commit currently on the remote is an ancestor of the new commit. Git only needs to advance the remote branch pointer to the new commit without skipping any history.

For example, the remote is at `B`, while the local branch adds `C`:

```text
A---B---C
    ^   ^
 remote local
```

Pushing from local to remote can fast-forward from `B` to `C`.

A **non-fast-forward** occurs when the remote commit is not an ancestor of the commit you are trying to push. For example, after common commit `B`, both sides have their own commits:

```text
      C  (origin/main)
     /
A---B
     \
      D  (local main)
```

Local has `D`, and remote has `C`. If `D` were pushed directly to `main`, Git would make the remote branch bypass `C`. Because `C` is not yet in the history of `D`, that operation is rejected under normal push rules.

After integrating both sides, history can take one of two forms:

```text
Merge:
      C-------M
     /       /
A---B-------D

Rebase:
A---B---C---D'
```

Merge preserves commit `D` and creates combining commit `M`. Rebase replays the changes of `D` onto `C`, creating new commit `D'`. Both approaches can produce a history in which the remote tip is an ancestor of the new commit, allowing a normal push.

## 2. Common Causes

### 2.1. Someone else pushed before you

You and a teammate are working on the same branch. Since your last fetch, your teammate pushed additional commits to the remote. Your local branch does not have those commits yet, so the push is rejected to protect the new changes.

### 2.2. Local and remote branches have diverged

You have separate local commits while the remote also has new commits. Both branches share a common ancestor, but each moved in its own direction. The two histories must be integrated before pushing.

### 2.3. The remote-tracking branch is stale

`origin/main` is a local reference recording the remote branch state as of the most recent fetch. If you have not fetched for a while, `origin/main` may not reflect new commits on the server. `git status` and `git branch -vv` only compare against that local reference; they do not query the server at runtime.

### 2.4. You are pushing to a different target branch than intended

A refspec or upstream configuration may cause Git to push your local branch into a remote branch you did not intend to update. Verify the remote name, current branch, and push target before synchronizing.

### 2.5. The remote branch was updated while you were resolving

Even after fetching and integrating successfully, someone else can push new commits before your push reaches the server. Your push may then be rejected again. This is a normal collaboration scenario; fetch and integrate the newest changes once more.

## 3. Reading the Message to Identify the Exact Rejection Type

The message `failed to push some refs` is a general summary line and is not enough by itself to conclude the cause. Read the accompanying detail line.

| Indicator | Common Meaning | How to Handle |
|---|---|---|
| `[rejected] ... (non-fast-forward)` | The remote branch has history not yet included in the commit being pushed | Fetch, inspect differences, merge or rebase, then push again |
| `[remote rejected] ... (protected branch hook declined)` | The server rejected the push due to branch policy or hook | Use a pull request or the process defined by repository administrators |
| `Permission denied` or `403` | Identity or write permissions do not meet requirements | Check credentials, repository permissions, and branch update permissions |
| `stale info` when using `--force-with-lease` | The remote changed compared to the state the lease expected | Fetch, inspect new commits, and re-evaluate before overwriting history |
| `src refspec ... does not match any` | Source branch or ref does not exist, or no matching commit exists yet | Check branch names, refspec, and local commit state |

Rejections caused by branch protection, hooks, or access permissions cannot be resolved by merging or rebasing. First distinguish a true non-fast-forward error from server-side policies.

## 4. Diagnostic Workflow Before Integrating

Before modifying history, inspect the repository and current working branch:

```bash
git status -sb
git branch -vv
git remote -v
```

- `git status -sb` shows the current branch and working tree state.
- `git branch -vv` shows each branch's upstream and ahead/behind commit counts relative to local remote-tracking refs.
- `git remote -v` confirms the fetch/push URLs of the remote.

If the working tree has uncommitted changes, identify and save them according to your workflow before starting a merge or rebase. Do not let unsaved edits mix with conflict resolution.

Next, refresh information from the remote:

```bash
git fetch origin
```

`fetch` downloads required objects and updates remote-tracking refs such as `origin/main`. It does not alter the current local branch or merge content into the working tree.

Compare history on both sides:

```bash
git log --oneline --graph --decorate --left-right HEAD...origin/main
```

Replace `origin/main` with the actual upstream. With `--left-right`, commits unique to `HEAD` are marked `<`, while commits unique to `origin/main` are marked `>`. This shows where local and remote commits differ.

You can quickly check whether the remote tip is already an ancestor of local:

```bash
git merge-base --is-ancestor origin/main HEAD
```

If the command returns exit code `0`, `origin/main` is an ancestor of `HEAD`; a normal push can fast-forward in terms of history lineage. If it returns a non-zero exit code, investigate integration or another history condition before pushing. This command only compares existing local commits; therefore, fetch first so the remote-tracking ref is up to date.

## 5. Resolving with Merge

Merge is suitable when the team wants to preserve existing commit IDs and record the point where the two branches joined in history.

Suppose you are on the local `main` branch and need to integrate `origin/main`:

```bash
git fetch origin
git merge origin/main
```

If there are no conflicts, Git combines the histories. If conflicts occur, read `git status`, examine both sides, and edit the content to preserve the intended semantics. Then:

```bash
git add path/to/resolved-file
git diff --cached
git merge --continue
```

Repeat for every remaining conflicted file. Once the merge completes, push again:

```bash
git push origin main
```

If you are working on a feature branch, replace `main` with the corresponding branch name. When upstream is properly configured, `git push` may suffice; specifying the remote and branch explicitly helps avoid pushing to the wrong target.

If the merge cannot be completed or you decide to stop, `git merge --abort` can return the repository to the state before the merge started. Before aborting, check status and ensure any uncommitted changes of yours are safely saved.

## 6. Resolving with Rebase

Rebase is suitable when you want to replay unshared local commits on top of the latest remote history, producing a more linear line of history.

Example on feature branch `feature/report`:

```bash
git fetch origin
git switch feature/report
git rebase origin/feature/report
```

Git replays each local commit on top of `origin/feature/report`. If a conflict happens:

```bash
git status
```

Edit each file to preserve the intended behavior, then stage and continue:

```bash
git add path/to/resolved-file
git rebase --continue
```

If a subsequent commit also conflicts, continue resolving until the rebase finishes. To cancel the entire rebase in progress, use `git rebase --abort`.

After the rebase succeeds, push the feature branch:

```bash
git push origin feature/report
```

If the rebased commits were purely unshared local commits, a normal push usually succeeds because the new history is built on the remote tip just fetched. Rebase creates commits with new IDs. If the old commits had already been fetched by others or are shared, rewriting them can cause everyone's history to diverge; coordinate with the team beforehand and consider merging to preserve shared commits.

## 7. Choosing Merge or Rebase?

| Criterion | Merge | Rebase |
|---|---|---|
| Existing commits | Preserves commit IDs | Creates new commit IDs for replayed commits |
| History | Records join points with merge commits when needed | Can create linear history |
| Best suited when | Branch is shared or the team wants integration recorded | Unshared local commits need to sit on top of the new remote base |
| Conflict resolution | Can be resolved in a single merge | May need to be resolved across multiple replayed commits |
| Collaboration risk | Usually easy to follow because shared commits are not rewritten | Can force others to resync if shared history is rewritten |

There is no single right choice for every repository. Follow your team's conventions and consider who else uses the branch. For shared branches, merge usually causes less history disruption. For personal unshared branches, rebase can update the base cleanly before pushing.

## 8. When Is Force Push Allowed?

`git push --force` tells the server to update the ref regardless of fast-forward ancestry. If the remote holds commits you do not have saved elsewhere, force push can leave those commits unreferenced by the branch and lose teammates' work.

Therefore, never use force push merely to make a non-fast-forward error go away. Always fetch and integrate remote commits through the normal workflow first.

There is a case where history is rewritten intentionally—such as when you just rebased a personal branch that had previously been pushed and the team agrees to update that branch. In that situation, `--force-with-lease` is safer than `--force` because Git checks that the remote is still in the state you expect before replacing the ref:

```bash
git fetch origin
git log --oneline --graph --decorate HEAD origin/feature/report
git push --force-with-lease origin feature/report
```

Carefully verify the target branch and commits before executing. If the lease rejects because the remote changed, stop, fetch, and inspect the new commits; do not immediately switch to `--force`. `--force-with-lease` reduces the risk of overwriting unfamiliar new changes, yet still replaces remote history whenever the lease condition is satisfied. It is no substitute for coordinating with collaborators on the branch and may still be blocked by branch protection.

## 9. Avoiding History-Losing Fixes

- **Do not run `git push --force` reflexively.** It can make other people's commits disappear from the remote branch.
- **Do not run `git reset --hard origin/main` just to clear ahead/behind counts.** This command moves the local branch and overwrites the working tree/index, potentially losing unsaved local commits or changes.
- **Do not run `git pull` without knowing the configured integration strategy.** `pull` performs fetch followed by merge or rebase depending on configuration and options; while troubleshooting, running `fetch` separately to inspect history first is much clearer.
- **Do not discard a remote commit just because it is not on your machine.** Check whose work that commit belongs to and whether it needs to be kept.
- **Do not mistake permission or branch protection errors for non-fast-forward.** Read the full server message to choose the right fix.
- **Do not rebase a shared branch without agreement.** Anyone who based work on the old commits will have to adjust their local history.

## 10. Complete Practical Example

You are working on branch `feature/report`. At the last fetch, the remote was at commit `B`. You created local commit `D`. Meanwhile, a teammate pushed commit `C` to the same branch:

```text
      C  (origin/feature/report)
     /
A---B
     \
      D  (feature/report)
```

Push is rejected because the remote has `C` that local has not integrated. You check status and fetch:

```bash
git status -sb
git fetch origin
git log --oneline --graph --decorate --left-right HEAD...origin/feature/report
```

After confirming `C` is a change to keep, the team chooses merge to avoid rewriting shared commits:

```bash
git merge origin/feature/report
```

If conflicts arise, resolve them according to both changes' requirements, run tests, stage the result, and finish the merge. Then:

```bash
git status -sb
git log --oneline --graph --decorate -5
git push origin feature/report
```

If another teammate pushes a new commit between your fetch and push, the server may reject this push again. Repeat fetching, inspecting the new commit, and integrating it. Never force push to bypass a second rejection.

## 11. Takeaways

Non-fast-forward is a mechanism protecting remote history when the commit you intend to push does not yet contain the commits currently on the target branch. Fetch to learn the latest state, compare both sides, choose merge or rebase according to collaboration conventions, resolve conflicts, and push again. Only rewrite remote history with clear intent, after coordinating with those involved, and using safeguards like `--force-with-lease`.

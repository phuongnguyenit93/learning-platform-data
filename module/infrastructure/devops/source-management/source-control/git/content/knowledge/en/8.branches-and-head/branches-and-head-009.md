# Viewing Ahead/Behind Relationships with git branch -vv and git status

When working with a branch that has an upstream, Git can tell you how many commits the local branch has that have not yet been pushed to the upstream, and how many commits are missing from the upstream. These two states are commonly called **ahead** and **behind**.

You can view them quickly using `git branch -vv` and `git status`. This information helps decide when to push, pull, merge, or rebase. However, it is computed from the remote-tracking refs currently stored on your local machine. If you have not fetched, the counts may be stale compared to the real remote.

This lesson explains upstream/tracking branches, how to read ahead/behind counts, how to inspect the exact differing commits, and how to handle each state without accidentally losing work.

## 1. What Are a Local Branch and an Upstream?

A local branch is a ref in the current repository, for example `feature/payment`. An upstream is the branch that Git uses as a comparison and synchronization reference point for that local branch.

In a common workflow, the upstream is a remote-tracking branch such as `origin/main`, `origin/feature/payment`, or `upstream/develop`.

A remote-tracking branch is a local ref reflecting the state of a branch on the remote at the most recent fetch. For example, `origin/main` resides in the `refs/remotes/origin/` namespace, not as a live connection to the server every time you run `git status`.

You can visualize it as:

~~~text
Remote server                 Local machine
origin/main  ------------->   refs/remotes/origin/main
                                  |
                                  | upstream of
                                  v
                             refs/heads/main
                             local branch
~~~

When you run `git fetch origin`, Git updates remote-tracking refs with the newly received data. `git status` and `git branch -vv` then compare your local branch against these refs.

A branch can exist without an upstream. Git still allows committing to and managing that branch, but there is no default baseline to display ahead/behind or perform certain push/pull operations without specifying a target.

## 2. What Do Ahead and Behind Mean?

Suppose the local branch and the upstream both started from commit A:

~~~text
        B---C  local feature/payment
       /
A-----+
       \
        D      origin/feature/payment
~~~

In this example:

- Local has B and C which upstream does not have yet: local is **ahead 2**.
- Upstream has D which local does not have yet: local is **behind 1**.
- Both branches have diverged, because each side has its own commits.

| State | Meaning |
|---|---|
| Ahead N | Local has N commits not reachable from upstream |
| Behind N | Upstream has N commits not reachable from local |
| Ahead 0, behind 0 | Both branches have the same tip and same reachable history set |
| Ahead N, behind M with both greater than 0 | The two branches have diverged |
| No metrics shown | The branch has no upstream yet or the upstream no longer exists |

Ahead/behind count commits in the history graph. They do not count modified files, lines of code, or push attempts. A merge commit can affect the count because Git evaluates reachability in the DAG, rather than merely counting commits along a straight line.

## 3. How to Read git branch -vv

The command:

~~~bash
git branch -vv
~~~

lists local branches alongside their latest commit and upstream information if tracking has been configured for the branch.

Example:

~~~text
  main             8ac12f0 [origin/main] Merge pull request #42
* feature/payment  b91d2a4 [origin/feature/payment: ahead 2, behind 1] Add payment validation
  feature/search   2c41e9b [origin/search: gone] Add search endpoint
~~~

How to read it:

- The `*` symbol marks the current branch.
- The name inside square brackets is the upstream.
- `ahead 2` means local has two commits not yet on upstream.
- `behind 1` means upstream has one commit not yet on local.
- `gone` means the configured upstream ref no longer exists in the current local refs.

`git branch -vv` displays all local branches. It does not automatically fetch to query the server, so the numbers reflect previously fetched remote-tracking refs.

If you also want to view remote-tracking branches:

~~~bash
git branch -avv
~~~

If you only want to view remote-tracking branches:

~~~bash
git branch -r
~~~

`git branch -r` only lists remote-tracking refs already present in the local repository, not a live list queried directly from the server.

## 4. How to Read git status

The command:

~~~bash
git status
~~~

In addition to the working tree and staging area status, Git also reports whether the current branch is ahead or behind its upstream.

Example when the branch is ahead:

~~~text
On branch feature/payment
Your branch is ahead of 'origin/feature/payment' by 2 commits.
  (use "git push" to publish your local commits)

nothing to commit, working tree clean
~~~

Example when the branch is behind:

~~~text
On branch feature/payment
Your branch is behind 'origin/feature/payment' by 3 commits, and can be fast-forwarded.
  (use "git pull" to update your local branch)
~~~

Example when the branch has diverged:

~~~text
On branch feature/payment
Your branch and 'origin/feature/payment' have diverged,
and have 2 and 1 different commits each, respectively.
  (use "git pull" to integrate the remote branch with yours)
~~~

This message only describes commit relationships with the upstream. The "working tree clean" line or the list of modified/staged files is a separate status. You can simultaneously be ahead by 2 and have uncommitted files.

## 5. Using git status -sb for a Quick Overview

The `-s` option displays short status, and `-b` adds branch information:

~~~bash
git status -sb
~~~

Example:

~~~text
## feature/payment...origin/feature/payment [ahead 2, behind 1]
 M src/payment/service.ts
M  src/payment/controller.ts
?? notes/test-cases.txt
~~~

The first line shows the branch and its relationship with the upstream. Subsequent lines show changes in the working tree and index:

- ` M`: file modified in the working tree, not yet staged.
- `M `: file staged.
- `??`: file not tracked by Git.

Do not read `ahead` as the number of modified files or assume that an ahead branch has a clean working tree. Read both the branch header and the file status lines.

You can use `git status --branch` or `git status --short --branch` to request branch information display.

## 6. Why Fetch Before Trusting Ahead/Behind?

`git status` does not make network calls to query the remote. It compares the local branch against the remote-tracking ref stored on your machine.

Example:

~~~text
Actual remote:
A---B---C---D  origin/main

Local machine before fetch:
A---B---C      origin/main
         \
          L    main
~~~

If the remote just received commit D but local has not fetched yet, your machine may report `main` ahead 1 and behind 0. After fetching, Git updates `origin/main` and the result can become ahead 1, behind 1.

Refresh data:

~~~bash
git fetch origin
git status -sb
git branch -vv
~~~

`git fetch` downloads commits and updates remote-tracking refs. It does not automatically merge/rebase into the current branch and does not overwrite the working tree.

If you want to remove remote-tracking refs for branches deleted on the remote:

~~~bash
git fetch --prune origin
~~~

After pruning, a local branch whose upstream was deleted may show `[origin/branch: gone]`. If fetching fails due to network, permissions, or a remote error, the displayed numbers remain only the figures from the previous fetch.

## 7. A Remote-Tracking Branch Is Not a Branch on the Server

The name `origin/main` is often misunderstood as a branch existing directly on the server. In reality, it is a local ref updated by Git during fetch.

| Name | Type | Location |
|---|---|---|
| `main` | Local branch | Local repository |
| `origin/main` | Remote-tracking branch | Local repository, reflecting the most recent fetch |
| Branch `main` on origin | Actual remote branch | Repository on the server |

You can view the remote URL:

~~~bash
git remote -v
~~~

View the refs advertised by the server at the moment of query:

~~~bash
git ls-remote --heads origin
~~~

`git ls-remote` queries refs on the remote but does not update local remote-tracking refs. To update local tracking data, use `git fetch`.

## 8. Checking Whether a Branch Has an Upstream

View branch information:

~~~bash
git branch -vv
~~~

View the upstream of the current branch:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

If the branch does not have an upstream, the command above reports an error. You can inspect tracking configuration with:

~~~bash
git config --get branch.feature/payment.remote
git config --get branch.feature/payment.merge
~~~

These two settings respectively identify the remote and the branch that the local branch tracks.

If the first line of `git status -sb` only shows `## feature/payment` without `...origin/...`, the branch may not have an upstream configured yet. Also check whether the upstream was deleted or has not been fetched yet.

## 9. Setting, Changing, or Unsetting an Upstream

If the remote branch has been fetched and exists as `origin/feature/payment`, attach the upstream:

~~~bash
git branch --set-upstream-to=origin/feature/payment feature/payment
~~~

If you are currently on the branch to be configured, you can omit the final branch name:

~~~bash
git branch --set-upstream-to=origin/feature/payment
~~~

If the branch does not exist on the remote yet and you want to push for the first time while setting the upstream:

~~~bash
git push -u origin feature/payment
~~~

If creating a local branch from a remote-tracking branch, you can configure tracking right away:

~~~bash
git switch --track -c feature/payment origin/feature/payment
~~~

Change the upstream to another branch:

~~~bash
git branch --set-upstream-to=origin/develop feature/payment
~~~

Remove the upstream:

~~~bash
git branch --unset-upstream feature/payment
~~~

Unsetting the upstream does not delete the local branch, remote branch, or commits. Do not attach a feature branch to `origin/main` just to make ahead/behind messages go away; the upstream should accurately reflect the branch your team uses as its baseline.

## 10. Calculating Ahead/Behind with git rev-list

When you need to check counts independently of `git status` formatting, use:

~~~bash
git rev-list --left-right --count HEAD...'@{upstream}'
~~~

Example output:

~~~text
2    1
~~~

With the order `HEAD...@{upstream}`:

- The left number is commits reachable only from local HEAD: ahead.
- The right number is commits reachable only from upstream: behind.

You can calculate them separately:

~~~bash
git rev-list --count '@{upstream}'..HEAD
git rev-list --count HEAD..'@{upstream}'
~~~

The first command counts local commits not yet in upstream. The second counts upstream commits not yet in local. The `A..B` expression selects commits reachable from B but not reachable from A; `A...B` selects the symmetric difference of the two histories.

If using PowerShell, put revisions containing `@{}` inside single quotes as in the examples above so PowerShell does not interpret them as its own syntax.

## 11. Viewing Commits Only on Local or Upstream

To see commits that local has and upstream does not:

~~~bash
git log --oneline '@{upstream}'..HEAD
~~~

To see commits that upstream has and local does not:

~~~bash
git log --oneline HEAD..'@{upstream}'
~~~

To see both sides on the same graph:

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
~~~

Git uses `<` and `>` to distinguish the left side and right side in `--left-right` output:

- `<` is a commit reachable only from local HEAD.
- `>` is a commit reachable only from upstream.

This is a recommended step before merging, rebasing, or pushing when a branch has diverged. Looking only at counts does not reveal the changed contents or which commits might cause conflicts.

## 12. Ahead-Only: Local Has New Commits

Example:

~~~text
A---B---C---L1---L2  feature/payment
        ^
        origin/feature/payment
~~~

`git status -sb` may display:

~~~text
## feature/payment...origin/feature/payment [ahead 2]
~~~

Inspect local commits:

~~~bash
git log --oneline '@{upstream}'..HEAD
~~~

If the commits are ready to share and the remote has no new changes, push:

~~~bash
git push
~~~

If the push is rejected because the remote advanced after your last fetch, fetch again and inspect the new relationship:

~~~bash
git fetch origin
git status -sb
git branch -vv
~~~

Do not use force push just to get past a non-fast-forward error. First understand the new commits on the remote and integrate them according to your team's workflow.

## 13. Behind-Only: Upstream Has New Commits

Example where local has no unique commits and upstream advances:

~~~text
A---B---C  origin/feature/payment
    ^
    feature/payment (local is at B)
~~~

Inspect the commits to receive:

~~~bash
git log --oneline HEAD..'@{upstream}'
~~~

After fetching and confirming there are no local changes to preserve, you can fast-forward update:

~~~bash
git pull --ff-only
~~~

`--ff-only` instructs Git to update only if fast-forward is possible. If history has diverged, the command stops instead of creating a merge commit automatically.

You can separate the two steps explicitly:

~~~bash
git fetch origin
git merge --ff-only '@{upstream}'
~~~

If the working tree has uncommitted changes, commit or stash before integrating. Ahead/behind only describes commits; it does not guarantee the working tree is clean.

## 14. Diverged: Both Local and Upstream Have Their Own Commits

Example:

~~~text
        L1---L2  feature/payment
       /
A---B---C
       \
        R1      origin/feature/payment
~~~

Status:

~~~text
## feature/payment...origin/feature/payment [ahead 2, behind 1]
~~~

Before choosing an integration method, inspect both sides:

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
~~~

**Merge upstream into local:**

~~~bash
git merge '@{upstream}'
~~~

Merging preserves both local and upstream commits and can create a merge commit. This approach is appropriate when the team wants to preserve topology or when local commits have already been shared.

**Rebase local commits onto upstream:**

~~~bash
git rebase '@{upstream}'
~~~

Rebasing replays local commits onto the upstream tip, generating new OIDs for the rewritten commits. This approach is typically used for personal feature branches not yet widely shared.

If integrating via pull, you can specify explicitly:

~~~bash
git pull --no-rebase
git pull --rebase
~~~

Follow your team's policy. Do not arbitrarily rebase commits that others already depend on, because changing OIDs will cause their history to diverge.

## 15. Upstream Is Gone or Branch Has No Upstream Yet

`git branch -vv` may display:

~~~text
* feature/payment  b91d2a4 [origin/feature/payment: gone] Add payment validation
~~~

This means the local branch is configured to track `origin/feature/payment`, but that remote-tracking ref does not currently exist locally. The branch may have been deleted on the server and pruned locally, or the ref has not been fetched.

Refresh refs:

~~~bash
git fetch --prune origin
git branch -vv
~~~

Then determine your intent:

- If the remote branch was intentionally deleted, keep the local branch and unset its upstream or point it to another upstream.
- If the team wants to restore the branch on the remote, inspect local commits and push again with `-u`.
- If the branch was replaced by another branch, confirm the new upstream before changing tracking.
- If the remote is unreachable, do not conclude the branch was deleted; check connectivity and permissions.

Unset the upstream if tracking is no longer needed:

~~~bash
git branch --unset-upstream feature/payment
~~~

If you want to recreate the remote branch from local:

~~~bash
git push -u origin feature/payment
~~~

If a newly created branch does not have an upstream yet, `git status -sb` usually shows only the branch name. Configure it with `git push -u origin feature/payment` or `git branch --set-upstream-to=origin/feature/payment feature/payment` if the remote-tracking branch already exists.

## 16. Ahead/Behind Does Not Replace git diff

Ahead/behind reports differing commits in history, whereas `git diff` compares tree or file contents.

Some complementary commands:

~~~bash
git diff
git diff --cached
git diff '@{upstream}'...HEAD
git diff HEAD '@{upstream}'
~~~

- `git diff`: unstaged changes in the working tree.
- `git diff --cached`: staged changes relative to HEAD.
- `git diff '@{upstream}'...HEAD`: changes on the HEAD side since the merge base with upstream.
- `git diff HEAD '@{upstream}'`: compares the trees at the two tips.

Three-dot and two-dot diffs answer different questions. Before integrating a branch, combine `git log --left-right` and `git diff` to see both the commits and the content changes.

## 17. Ahead/Behind in Scripts and When Listing Many Branches

Do not parse human-friendly output strings from `git status` if a script needs a stable format. Git provides porcelain v2:

~~~bash
git status --porcelain=v2 --branch
~~~

Example:

~~~text
# branch.oid b91d2a4...
# branch.head feature/payment
# branch.upstream origin/feature/payment
# branch.ab +2 -1
~~~

`# branch.ab +2 -1` indicates local is ahead by 2 and behind by 1 relative to upstream. If there is no upstream, the `branch.upstream` and `branch.ab` lines may not appear; scripts must handle missing fields rather than defaulting to 0/0.

To review local branches sorted by most recent commit time:

~~~bash
git branch -vv --sort=-committerdate
~~~

You can use `git for-each-ref` to generate reports:

~~~bash
git for-each-ref --format="%(refname:short) %(upstream:short) %(upstream:track)" refs/heads/
~~~

- `%(refname:short)`: local branch name.
- `%(upstream:short)`: upstream name if present.
- `%(upstream:track)`: ahead/behind status or upstream gone info if present.

These reports still rely on local refs. Fetch first if you want figures reflecting the latest remote state.

## 18. Common Errors and Misunderstandings

| Symptom | Possible cause | How to check/resolve |
|---|---|---|
| Branch reports up to date even though a teammate just pushed | Have not fetched so the remote-tracking ref is stale | Run `git fetch`, then recheck status |
| `git branch -vv` shows no upstream section | Branch has no tracking configured yet | Use `git push -u` or `git branch --set-upstream-to` |
| Status reports both ahead and behind | Both sides have their own commits | Inspect `git log --left-right`, choose merge or rebase |
| Shows `[origin/foo: gone]` | Upstream ref no longer exists in local refs | Fetch/prune, verify the remote, and pick a new upstream or push again |
| Push rejected even though status only showed ahead | Remote may have advanced since the last fetch | Fetch again, inspect new commits, and integrate |
| `git pull` creates an unexpected merge commit | Pull config uses merge and the branch diverged | Check `pull.rebase`, use an explicit option per policy |
| `git pull --ff-only` stops | History cannot fast-forward | Inspect commits on both sides, then choose merge/rebase |
| `git status` shows modified files even though branch is up to date | Working tree dirtiness is independent of commit relationships | Check `git status --short`, `git diff`, and staging |
| `git branch -r` still shows a deleted branch | Local remote-tracking ref has not been pruned | Run `git fetch --prune origin` |
| Ahead/behind counts differ between two machines | The two machines fetched at different times or have different upstreams | Compare `git remote -v`, upstreams, and fetch fresh |

## 19. Pre-Push or Pre-Pull Inspection Workflow

When preparing to synchronize a branch, you can use this sequence:

**Step 1 — Identify the current branch**

~~~bash
git branch --show-current
git status -sb
~~~

**Step 2 — Check the upstream**

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git branch -vv
~~~

**Step 3 — Fetch new data**

~~~bash
git fetch --prune origin
~~~

**Step 4 — Recheck the relationship**

~~~bash
git status -sb
git branch -vv
git rev-list --left-right --count HEAD...'@{upstream}'
~~~

**Step 5 — Inspect differing commits and contents**

~~~bash
git log --left-right --graph --oneline HEAD...'@{upstream}'
git diff '@{upstream}'...HEAD
~~~

**Step 6 — Choose the action**

- Ahead-only: inspect local commits and push.
- Behind-only: if fast-forward is possible, use `git pull --ff-only`.
- Diverged: choose merge or rebase per team convention.
- Gone: verify whether the remote branch was deleted or renamed.
- No upstream: configure tracking if synchronization is needed.

**Step 7 — Verify again after the operation**

~~~bash
git status -sb
git branch -vv
~~~

## 20. Ahead/Behind Reading Checklist

- [ ] Identified the current local branch.
- [ ] Identified the tracked upstream branch.
- [ ] Fetched the remote recently before drawing conclusions.
- [ ] Understood ahead as commits present only on local.
- [ ] Understood behind as commits present only on upstream.
- [ ] Distinguished commit counts from modified file counts.
- [ ] Checked the working tree and staging area separately.
- [ ] Inspected local-only and upstream-only commits when the branch diverged.
- [ ] Checked whether the upstream is gone or not yet configured.
- [ ] Chose push, fast-forward, merge, or rebase according to team policy.
- [ ] Verified status after synchronization.

## 21. Key Points to Remember

- An upstream is the reference branch that a local branch compares against and syncs with; typically a remote-tracking branch such as `origin/main`.
- `git branch -vv` displays local branches, commit tips, upstreams, and ahead/behind counts.
- `git status` or `git status -sb` shows the current branch status and working tree state.
- Ahead counts commits present only on local; behind counts commits present only on upstream.
- Both ahead and behind greater than 0 means the two histories have diverged.
- Counts are based on local remote-tracking refs, so run `git fetch` before trusting them.
- `git fetch` updates refs without integrating commits into the current branch.
- `git fetch --prune` removes remote-tracking refs for branches deleted from the remote according to the refspec.
- `git push -u` creates/updates the remote branch and sets the upstream for subsequent runs.
- Use `git rev-list --left-right --count` and `git log --left-right` to check counts and contents on both sides.
- `git status --porcelain=v2 --branch` is suitable for scripts that need stable branch status parsing.
- Ahead/behind does not replace checking diffs, the working tree, and merge/rebase policy.

When you read ahead/behind relationships accurately, you know whether local has commits to push, is missing commits to pull, or has diverged from its upstream. Fetch first, inspect commits on both sides, and choose the right synchronization method; this helps avoid rejected pushes, unintended merges, or rewriting history that teammates are already using.

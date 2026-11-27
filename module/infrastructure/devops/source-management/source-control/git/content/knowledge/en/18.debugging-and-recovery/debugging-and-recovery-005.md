# Roles and Limitations of ORIG_HEAD, FETCH_HEAD, and MERGE_HEAD

When Git performs a fetch, merge, pull, or reset, you sometimes need to know which commit was just downloaded, which commit is being merged in, and where the current branch was before the operation. Git stores some of this information using pseudo-refs such as `FETCH_HEAD`, `MERGE_HEAD`, and `ORIG_HEAD`.

These three names frequently appear when troubleshooting synchronization errors or recovering from mistaken operations. However, they are not three interchangeable backup branches. Each serves a different moment in time, with its own lifecycle and limitations. Understanding them accurately helps you investigate repository state and choose the appropriate recovery method.

## 1. What Is a Pseudo-Ref?

In Git, a normal branch is a reference named something like `refs/heads/main`. A remote-tracking branch is named something like `refs/remotes/origin/main`. They generally persist long-term until moved or deleted.

The names `ORIG_HEAD`, `FETCH_HEAD`, and `MERGE_HEAD` are special references or metadata files inside the Git directory. Git updates them to record information supporting the current operation or an operation that just occurred.

You can inspect the Git directory path and the locations of these files with:

~~~bash
git rev-parse --git-dir
git rev-parse --git-path ORIG_HEAD
git rev-parse --git-path FETCH_HEAD
git rev-parse --git-path MERGE_HEAD
~~~

Use `git rev-parse --git-path` instead of assuming `.git/...` by default, because in a linked worktree, `.git` in the working directory may be a file pointing to the actual Git directory.

Overview of the three pseudo-refs:

| Name | What Does It Record? | Typically Useful When |
| --- | --- | --- |
| `ORIG_HEAD` | HEAD's position prior to a major history-moving operation | Reviewing or restoring the branch tip before a merge/reset |
| `FETCH_HEAD` | The commit or commits fetched in the most recent fetch | Inspecting newly downloaded content before integrating |
| `MERGE_HEAD` | The commit or commits currently being merged into the current HEAD | Investigating an in-progress merge or resolving conflicts |

## 2. ORIG_HEAD — Pre-Operation HEAD Marker

### 2.1. Role of ORIG_HEAD

`ORIG_HEAD` typically stores the commit that HEAD or the current branch pointed to before an operation that can significantly alter history. Git uses it in operations such as merge, reset, and certain history-rewriting scenarios so you can reference the previous position again.

For example, the current branch has the history:

~~~text
A --- B --- C  (HEAD -> main)
~~~

You start merging another branch. Before integrating, Git may record commit `C` into `ORIG_HEAD`. If you need to inspect the old marker:

~~~bash
git show -s --oneline ORIG_HEAD
~~~

The command displays the commit that `ORIG_HEAD` currently references. You can verify whether this name resolves to a valid commit:

~~~bash
git rev-parse --verify 'ORIG_HEAD^{commit}'
~~~

If the command does not return a commit hash, the pseudo-ref may not exist yet or may no longer point to a valid commit in the current repository.

### 2.2. Using ORIG_HEAD to Investigate a Completed Merge

Suppose you just merged `feature/payment` into `main`, then realized the integration result is wrong. Before making further changes, inspect:

~~~bash
git status
git log --oneline --graph --decorate -8
git show -s --oneline ORIG_HEAD
~~~

If that merge was the most recent operation updating HEAD and `ORIG_HEAD` still holds the pre-merge marker, you can compare that marker against current history to determine the scope of changes.

`ORIG_HEAD` only provides a reference marker; it does not undo the operation by itself. How you proceed depends on whether the merge has already finished or is still in progress, whether the branch has been shared, and what changes currently exist in the working tree.

### 2.3. Restoring the Branch Tip to ORIG_HEAD

If the merge has finished, you are on a personal branch, there is no new work to preserve, and you have confirmed `ORIG_HEAD` is indeed the pre-merge commit, you can bring the branch back to that marker:

~~~bash
git reset --hard ORIG_HEAD
~~~

This command is destructive: it moves the branch, updates the index, and rewrites the working tree. Uncommitted changes to Git-tracked files may be lost. Use it only when you truly want to discard the current state and have preserved any content that needs to be kept.

Before resetting, create a backup branch if you need to preserve the current marker:

~~~bash
git branch backup/after-unwanted-merge
git show -s --oneline ORIG_HEAD
~~~

After resetting, re-verify:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

If the merge has already been pushed or others have based work on that history, rewriting the shared branch can cause other clones to diverge. In that case, it is usually better to create a reverting commit using `git revert` per team workflow rather than resetting and force pushing.

### 2.4. Limitations of ORIG_HEAD

- `ORIG_HEAD` is not a backup with its own history. It typically holds only a single marker from before the most recent operation.
- A subsequent Git operation can overwrite this value. Do not assume it still points to the commit you need after multiple resets, merges, or rebases.
- It does not save the working tree or index. If there were uncommitted changes before the operation, `ORIG_HEAD` does not preserve those changes separately.
- It does not guarantee recovery from every operation. If you need to locate earlier HEAD movements, inspect the reflog.
- Before using it as a reset target, always inspect the actual commit with `git show` and cross-check with `git reflog`.

## 3. FETCH_HEAD — Result of the Fetch

### 3.1. Role of FETCH_HEAD

When running `git fetch`, Git downloads objects and updates information from the remote. Git writes the newly fetched commits into the `FETCH_HEAD` file in the Git directory. This file indicates what was just retrieved and can serve as input for a subsequent merge or pull operation.

Example:

~~~bash
git fetch origin main
~~~

Then you can inspect the fetched commit:

~~~bash
git show -s --oneline FETCH_HEAD
~~~

For a separately fetched branch, you can view commits present on the newly fetched side that are not yet in HEAD:

~~~bash
git log --oneline HEAD..FETCH_HEAD
~~~

These commands help you inspect content before integrating. If fetching multiple branches at once, `FETCH_HEAD` can contain multiple lines and multiple commits; some lines may be marked not-for-merge. Read the fetch output list before assuming it represents a single branch. The `git show FETCH_HEAD` and `git log HEAD..FETCH_HEAD` examples above assume the fetch retrieved only a single branch intended for integration.

### 3.2. Using FETCH_HEAD to Integrate Newly Fetched Commits

A clear workflow is to fetch first, inspect next, and only then merge:

~~~bash
git fetch origin main
git show -s --oneline FETCH_HEAD
git log --oneline HEAD..FETCH_HEAD
git merge FETCH_HEAD
~~~

Here:

1. `git fetch origin main` retrieves information for branch `main` from remote `origin`.
2. `git show` displays the commit recorded in `FETCH_HEAD`.
3. `git log` lets you view commits not yet in HEAD.
4. `git merge FETCH_HEAD` integrates the fetched commit into the current branch.

Before merging, confirm you are on the intended target branch:

~~~bash
git branch --show-current
git status -sb
~~~

Do not run merge merely because `FETCH_HEAD` exists. That file may be left over from an earlier fetch and no longer represent the data you currently want to integrate.

### 3.3. FETCH_HEAD Differs from a Remote-Tracking Branch

These two concepts are often confused:

- `FETCH_HEAD` records the most recent fetch results in a metadata file, serving the current fetch/pull operation.
- `origin/main` is a remote-tracking branch used to track the state of branch `main` on remote `origin`.

Remote-tracking branches are typically updated according to the configured fetch refspec and persist across multiple fetches. `FETCH_HEAD` is temporary information from the most recent fetch and can be overwritten on the next fetch.

View remote-tracking branches:

~~~bash
git branch -r
git log --oneline -5 origin/main
~~~

View the most recent fetch result:

~~~bash
git show -s --oneline FETCH_HEAD
~~~

If you need to track a remote branch long-term, use a remote-tracking branch like `origin/main`; do not treat `FETCH_HEAD` as a branch.

### 3.4. Limitations of FETCH_HEAD

- A new fetch typically overwrites the previous `FETCH_HEAD` contents. There is an `--append` option to append information, but this is not a long-term history storage mechanism.
- The file can contain multiple lines from multiple refs, including lines marked not-for-merge; you should not assume there is only one line or one branch.
- `FETCH_HEAD` is neither a branch nor a remote-tracking branch.
- It does not mean the commits have already been merged into the current branch.
- Fetch only downloads objects and updates references per configuration; it does not automatically integrate changes into the working tree.
- If you want to see the latest remote data, fetch the specific remote and ref again before inspecting.

## 4. MERGE_HEAD — Commit Being Merged into HEAD

### 4.1. Role of MERGE_HEAD

When Git performs a merge that needs to hold integration state in order to create a merge commit, Git records the commit being merged into `MERGE_HEAD`. In a standard merge, `HEAD` is the current branch (the side receiving changes), while `MERGE_HEAD` is the incoming commit.

Example:

~~~text
main:    A --- B --- C  (HEAD)
feature: A --- D --- E  (MERGE_HEAD)
~~~

While merging `feature/payment` into `main`:

- `HEAD` still points to `C` while the merge is in progress.
- `MERGE_HEAD` records commit `E` being integrated.
- The index may hold stages for conflicting files.
- The working tree contains content auto-combined by Git along with conflict markers requiring user resolution.

Check state:

~~~bash
git status
git show -s --oneline MERGE_HEAD
~~~

If `MERGE_HEAD` cannot be resolved, there may be no merge in progress or the merge has already finished/been aborted.

### 4.2. MERGE_HEAD Appears During a Merge

Example starting a merge:

~~~bash
git switch main
git merge feature/payment
~~~

If Git cannot fast-forward and needs to create a merge commit, it saves the merge state so you can resolve conflicts and complete it. When a merge has conflicts:

~~~bash
git status
git ls-files -u
git show -s --oneline HEAD
git show -s --oneline MERGE_HEAD
~~~

- `HEAD` shows the current branch's commit prior to completing the merge.
- `MERGE_HEAD` shows the incoming commit. In an octopus merge, this file can record multiple incoming commits; the `git show MERGE_HEAD` example in this lesson assumes a regular merge with a single incoming commit.
- `git ls-files -u` shows unmerged index entries and their associated stages.

Once conflicting files are resolved:

~~~bash
git add src/PaymentService.java
git status
git merge --continue
~~~

Git creates a merge commit with the corresponding parents and ends the merge state. After completion, `MERGE_HEAD` is removed.

### 4.3. Aborting an In-Progress Merge

If you decide not to continue the merge, use:

~~~bash
git merge --abort
~~~

This command tells Git to cancel the ongoing merge and return the working tree/index to the state before the merge started insofar as Git can restore it.

After aborting:

~~~bash
git status
git show -s --oneline HEAD
~~~

`MERGE_HEAD` no longer represents an ongoing merge. If there were uncommitted changes before starting the merge, Git may not restore them perfectly in every situation. Therefore, commit or stash important changes before merging.

### 4.4. MERGE_HEAD Does Not Always Exist

Not every command with the word merge creates `MERGE_HEAD`:

- A fast-forward merge simply advances the branch to the newer commit, without needing to hold state waiting to create a merge commit.
- `git merge --squash` prepares content in the index and working tree like a merge, but does not record a regular merge and does not create `MERGE_HEAD` to be finalized with a merge commit.
- After a merge commit completes or a merge is aborted, `MERGE_HEAD` is cleaned out of the operation state.

Therefore, you cannot use the presence or absence of `MERGE_HEAD` alone to conclude whether all changes have been merged. Combine `git status`, commit history, and branch state.

## 5. Distinguishing the Three Pseudo-Refs in the Same Scenario

Suppose you are on `main`, want to pull changes from `origin/main` and integrate them into the current branch, and a conflict arises.

General sequence:

~~~text
Before fetch:
HEAD -> commit A

Fetch:
FETCH_HEAD -> commit B (just retrieved from remote)

Start merge:
HEAD -> commit A
MERGE_HEAD -> commit B

ORIG_HEAD:
commit A (HEAD marker before the merge operation)
~~~

Role at each point in time:

| Point in Time | ORIG_HEAD | FETCH_HEAD | MERGE_HEAD |
| --- | --- | --- | --- |
| Before fetch | May hold a marker from an earlier operation; not necessarily recent | May be an older fetch result or absent | Usually absent if not merging |
| After fetch | Not the primary target of fetch | Records the newly fetched commit/ref | Absent if merge has not started |
| During pending merge | Usually holds the pre-merge HEAD marker | Still holds the fetch result unless overwritten by another fetch | Records the commit currently being merged |
| After merge commit | May still hold the pre-merge marker | Remains the latest fetch result until another fetch | Cleaned up after merge completes |
| After merge abort | May still reference the pre-operation marker | Does not automatically become a backup | Cleaned up when merge is aborted |

This is a general model. Exact values depend on the commands run and subsequent operations. Do not assume all three files always coexist or describe the same integration event.

## 6. Investigation Workflow When Pull or Merge Errors Occur

When `git pull` reports a conflict or the repository is in an incomplete merge state, check in sequence.

### Step 1 — Identify the Current Operation

~~~bash
git status
git branch --show-current
~~~

Git's messages indicate whether a merge is in progress, which files are unmerged, and the next steps to take.

### Step 2 — Inspect Pre-Operation Marker and Incoming Commit

~~~bash
git show -s --oneline ORIG_HEAD
git show -s --oneline FETCH_HEAD
git show -s --oneline MERGE_HEAD
~~~

Some commands may report that a pseudo-ref name was not found if the corresponding operation has not occurred or has already ended. This is useful diagnostic information, not a reason to manually create files or edit metadata.

### Step 3 — Inspect Related Commits and Contents

~~~bash
git log --oneline --graph --decorate -10
git diff
git diff --cached
git ls-files -u
~~~

Use history to identify the current branch, incoming commit, and conflicting files. If you need to compare two specific commits, use `git diff <commit-a> <commit-b>`.

### Step 4 — Choose Whether to Continue or Abort

If you want to continue:

~~~bash
git add <resolved-file>
git merge --continue
~~~

If you want to cancel the ongoing merge:

~~~bash
git merge --abort
~~~

Do not manually delete `MERGE_HEAD` or files in the Git directory to finish a merge. Use the appropriate Git command so the index, working tree, and metadata are updated consistently.

## 7. ORIG_HEAD and Reflog: Which to Use for Recovery?

`ORIG_HEAD` is convenient when you need the marker right before a recent operation. However, because it can be overwritten, reflog is usually more useful when you need to trace the movement history of HEAD.

Inspect the reflog:

~~~bash
git reflog --date=local
~~~

For example, the reflog may record:

- HEAD before the merge.
- HEAD after the merge.
- HEAD after a reset.
- Checkouts or rebases.

After identifying the commit to rescue, create a backup branch:

~~~bash
git branch rescue/before-merge <commit-to-rescue>
~~~

If the commit to rescue is `ORIG_HEAD` itself, you can use:

~~~bash
git branch rescue/before-merge ORIG_HEAD
~~~

A rescue branch creates a more stable reference to the commit in the repository. It still does not back up uncommitted changes in the working tree or index; if those also need to be preserved, save them separately before taking the next step.

Reflog is local data and has a retention limit. It does not replace repository backups or remotes.

## 8. Common Mistakes

- **Treating ORIG_HEAD as a permanent backup:** its value can be overwritten by the next Git operation. Check it early and create a backup branch if needed.
- **Confusing FETCH_HEAD with origin/main:** FETCH_HEAD records the most recent fetch result; a remote-tracking branch is a long-term reference tracking a remote branch.
- **Assuming fetch already merged:** fetch downloads objects and updates info; it does not automatically integrate changes into the current branch.
- **Assuming MERGE_HEAD is the target branch:** it records the commit being merged into HEAD, not the local branch name you have checked out.
- **Using reset --hard ORIG_HEAD while a merge is still in progress:** if the merge has not finished, `git merge --abort` is usually the more appropriate command.
- **Using ORIG_HEAD without inspecting the actual commit:** the pseudo-ref may have been updated by another operation. Check `git show` and `git reflog` before resetting.
- **Manually deleting metadata files in the Git directory:** this can leave the index and ongoing operation state inconsistent. Use `git merge --continue` or `git merge --abort`.
- **Assuming MERGE_HEAD exists in every kind of merge:** fast-forward and squash merges behave differently from standard merge commits.

## 9. Quick Reference Table

| Goal | Command |
| --- | --- |
| View marker before operation | `git show -s --oneline ORIG_HEAD` |
| Verify ORIG_HEAD is a valid commit | `git rev-parse --verify 'ORIG_HEAD^{commit}'` |
| View newly fetched commit | `git show -s --oneline FETCH_HEAD` |
| View commit currently being merged | `git show -s --oneline MERGE_HEAD` |
| View Git directory location | `git rev-parse --git-dir` |
| View pseudo-ref path | `git rev-parse --git-path FETCH_HEAD` |
| View HEAD movement history | `git reflog --date=local` |
| View merge/conflict status | `git status` |
| View unmerged entries | `git ls-files -u` |
| Continue merge | `git merge --continue` |
| Cancel ongoing merge | `git merge --abort` |
| Create rescue branch from ORIG_HEAD | `git branch rescue/before-merge ORIG_HEAD` |

## 10. Summary

`ORIG_HEAD`, `FETCH_HEAD`, and `MERGE_HEAD` help you understand where Git stands during a synchronization or integration cycle. `ORIG_HEAD` records the HEAD marker before certain major operations; `FETCH_HEAD` records the most recent fetch result; `MERGE_HEAD` records the commit being merged into HEAD while Git holds a merge state waiting for completion.

They are operational markers, not three backup branches you can rely on long-term. When investigating, combine them with `git status`, `git log`, `git diff`, and `git reflog`. When recovering, confirm the target commit and working tree state before resetting, continuing a merge, or aborting. This inspection discipline helps you handle synchronization incidents on solid evidence and preserve important repository history.

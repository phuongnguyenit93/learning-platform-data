# Moving a slice of history with git rebase --onto

During development, a feature branch is sometimes created from another branch instead of main. Later, plans may change: you want to move the feature branch's unique commits onto a new base. The **git rebase --onto** command lets you select a set of commits using a boundary reference and replay that set onto a different target point.

What makes **--onto** special is that it separates two concepts: **which commits to replay** and **where to replay them**. Understanding these two parameters helps you move the right piece of history without dragging along commits outside your scope of work.

After this lesson, you will be able to:

- Read and explain the git rebase --onto syntax.
- Identify the set of commits to be selected from a branch.
- Move a feature branch from an old base to a new base.
- Separate unique commits from a dependent branch.
- Inspect history before and after rebasing.
- Handle conflicts, recover from operations, and coordinate when a branch has been shared.

## 1. Syntax and meaning of each parameter

General syntax:

~~~bash
git rebase --onto NEWBASE UPSTREAM [BRANCH]
~~~

| Parameter | Meaning |
| --- | --- |
| NEWBASE | The target commit or branch onto which the selected commits will be replayed. |
| UPSTREAM | The boundary reference used to determine which commits belong to the range to replay. Commits reachable from upstream are excluded from the selected set. |
| BRANCH | The branch to rebase. If omitted, Git uses the current branch. |

You can visualize the operation as follows:

1. Identify commits reachable from BRANCH.
2. Exclude commits already reachable from UPSTREAM.
3. Replay the remaining commits in appropriate order, starting from NEWBASE.
4. Update the target branch to the new commit once complete.

For simple linear history, the selected set of commits corresponds to the range UPSTREAM..BRANCH.

This does not mean UPSTREAM and NEWBASE have to be the same branch. On the contrary, the ability to pick a separate boundary reference and a separate destination is why --onto is useful.

If BRANCH is specified, Git switches to that branch before rebasing. If omitted, the command operates on the currently checked-out branch:

~~~bash
# Rebase feature/ui onto main, using feature/auth as the boundary reference
git rebase --onto main feature/auth feature/ui

# Equivalent in goal if feature/ui is already checked out
git switch feature/ui
git rebase --onto main feature/auth
~~~

The name UPSTREAM in this syntax is a boundary parameter for the operation, not necessarily the upstream tracking branch configured via git branch --set-upstream-to.

## 2. Why separate the boundary reference and the destination

Suppose the team has a feature/auth branch building authentication functionality. While waiting for that branch to finish, you create feature/ui based on it to develop the user interface. Later, the team decides the UI work needs to move to main independently, without bringing in all the authentication commits.

Illustrative history:

~~~text
A---B---C---D             main
     \
      F1---F2---F3        feature/auth
                     \
                      U1---U2  feature/ui
~~~

In this example:

- feature/auth has commits F1, F2, F3.
- feature/ui was created from the tip of feature/auth after F3 and has commits U1, U2.
- main has advanced to D.
- You want to keep U1 and U2, drop the dependency on commits F1, F2, F3, and place the UI work on top of main.

Run:

~~~bash
git rebase --onto main feature/auth feature/ui
~~~

Git selects commits in feature/ui that are not in feature/auth, which are U1 and U2 in this simple history. Then, Git replays them onto main:

~~~text
A---B---C---D---U1'---U2'  feature/ui
            ^
            main
     \
      F1---F2---F3         feature/auth
~~~

Commits U1' and U2' are new commits. The feature/auth branch keeps its old history. After the operation, feature/ui points to the new history on main.

This is one way to detach a child branch from a dependent branch. However, verify that the UI code no longer needs APIs or changes that only exist in feature/auth. A rebase might apply patches cleanly while the application still breaks because a dependency was removed from the new base.

## 3. Preparing before running rebase --onto

Rebase rewrites commits, so you need to understand the repository state and the set of commits about to be moved. First, check the working tree:

~~~bash
git status --short --branch
~~~

If uncommitted changes remain, decide whether to save them with a commit or stash according to your workflow. Do not start a rebase while you are unsure what edits are sitting in the working tree or staging area.

Next, update remote information if the destination is a branch on the remote:

~~~bash
git fetch origin
~~~

Create a backup branch to preserve the old position:

~~~bash
git branch backup/feature-ui-before-onto feature/ui
~~~

A backup branch only creates another reference to the current commit; it does not copy the entire repository. If you need to go back or compare against the old history, you can still access the commits through this branch.

Inspect the graph and the expected commit set:

~~~bash
git log --oneline --graph --decorate --all
git log --oneline --reverse feature/auth..feature/ui
git merge-base feature/auth feature/ui
~~~

The command git log --reverse feature/auth..feature/ui displays the selected commits from oldest to newest in this linear example. Read each commit and confirm they all belong to the work you intend to move.

If you want to confirm feature/auth is an ancestor of feature/ui, you can check:

~~~bash
git merge-base --is-ancestor feature/auth feature/ui
~~~

The command returns exit code 0 when feature/auth is an ancestor of feature/ui; a non-zero exit code means the ancestor relationship is false or cannot be confirmed. This is useful when you expect one branch to have been created from another. If history already contains merges or multiple ancestor branches, inspect the graph rather than relying on a single linear assumption.

## 4. Full example: moving a child branch to main

Suppose feature/ui was developed on top of feature/auth, but now the unique UI commits need to move onto origin/main.

~~~bash
# 1. Check status and branches
git status --short --branch
git branch -vv

# 2. Update remote references
git fetch origin

# 3. Keep a reference to the old history
git branch backup/feature-ui-before-onto feature/ui

# 4. Inspect the commits to be moved
git log --oneline --reverse feature/auth..feature/ui

# 5. Move feature/ui's unique commits onto origin/main
git rebase --onto origin/main feature/auth feature/ui

# 6. Inspect history after moving
git log --oneline --graph --decorate --all -n 25
~~~

In the command in step 5:

- origin/main is the new destination.
- feature/auth is the boundary reference; commits already in this branch are not replayed.
- feature/ui is the branch being updated.

If there are no conflicts and patches apply cleanly, Git completes the rebase and moves feature/ui to the new commit. If conflicts occur, handle them according to the procedure in the section below.

## 5. Using --onto to drop part of a dependent history

Another case is when branch B was created from branch A, but you only want to keep the commits B itself added. In that case, branch A can serve as the boundary reference:

~~~bash
git rebase --onto main feature/A feature/B
~~~

The command takes commits in feature/B that are not in feature/A's history, and replays them onto main. This removes the commits inherited from branch A from B's new history.

Do not confuse this operation with deleting commits from every branch. Commits dropped from feature/B's new history may still be retained by feature/A, backup branches, tags, or other references. Rebase moves the selected branch; it does not automatically delete old objects from the repository.

Before removing a dependency, check:

- Are branch B's unique commits truly independent of changes in A?
- Does the code reference classes, functions, schemas, or configs that only exist in A?
- Do tests and builds pass on the new main base?
- Have any commits of B already been used or shared by others?

If B's commits require changes from A, removing A may prevent the code from compiling or cause incorrect behavior. In that case, extract the dependency into shared code, keep the needed commits, or pick another base that contains the dependency.

## 6. Using --onto to change a branch's base

Common general pattern:

~~~bash
git rebase --onto NEW-BASE OLD-BASE TOPIC-BRANCH
~~~

For example, suppose feature/export was initially created from release/1.x, but the team decides to move new development to main:

~~~bash
git fetch origin
git branch backup/export-before-move feature/export
git log --oneline --reverse release/1.x..feature/export
git rebase --onto origin/main release/1.x feature/export
~~~

Git selects commits in feature/export that are not in release/1.x's history and replays them onto origin/main. This is the operation of transplanting a set of commits to a new base.

The command is only accurate when release/1.x is the right boundary reference for the history you want to keep. If the export branch contains commits from multiple sources or complex merges, the selected commit set may be broader than expected. Check git log, git merge-base, and the graph before running.

## 7. Distinguishing rebase --onto from standard rebase

Standard rebase:

~~~bash
git rebase origin/main
~~~

While on feature/export, the command above uses upstream as both the boundary identifying which commits to replay and the new base. Git takes the current branch's unique commits relative to origin/main, and replays them onto origin/main.

Rebase with --onto:

~~~bash
git rebase --onto origin/main release/1.x feature/export
~~~

Here, the boundary reference is release/1.x, while the new base is origin/main. These two parameters can differ. Being able to separate them lets you move a selected slice of history onto a new base that standard rebase cannot directly express.

| Question | Standard rebase | Rebase --onto |
| --- | --- | --- |
| Which commits are replayed? | Branch's unique commits relative to upstream. | Branch's unique commits relative to the specified upstream boundary. |
| Where are they replayed? | Onto that same upstream. | Onto a separate newbase, which can differ from upstream. |
| Typical use case | Updating a feature branch onto latest main. | Detaching a child branch from a dependent branch or changing bases between two different branches. |

## 8. Rebasing with merge commits and the --rebase-merges option

By default, standard rebase replays history linearly and may not preserve the original merge commit structure. If a branch contains important merge commits, consider the option:

~~~bash
git rebase --rebase-merges --onto main feature/auth feature/ui
~~~

--rebase-merges instructs Git to attempt to recreate the merge structure in the replayed history. Recreated merge commits receive new identifiers and the process can still produce conflicts. Do not enable this option simply because the graph has many branches; first determine whether the merge commits carry integration meaning worth preserving.

Inspect the graph before and after:

~~~bash
git log --graph --oneline --decorate --all
~~~

If the history structure is complex, practice on a backup branch or in an appropriate working copy before applying it to a branch actively used by multiple people.

## 9. Handling conflicts during rebase

When a commit is replayed but cannot be applied automatically, Git pauses and reports the conflicting files. Check the status:

~~~bash
git status
git diff
~~~

Open the files reported as conflicted, read the conflict regions, and produce the final content matching the change's intent. After fixing each file:

~~~bash
git add path/to/file
git rebase --continue
~~~

Git continues replaying the remaining commits. You may need to repeat the edit, stage, and continue cycle multiple times.

If the current commit is no longer needed or its patch has already been incorporated into the new base in an equivalent way, you can skip that commit:

~~~bash
git rebase --skip
~~~

Only use --skip after confirming the commit's changes are no longer necessary. This command omits the commit currently being replayed from the new history.

If you want to cancel the entire process and return to the state before the rebase started:

~~~bash
git rebase --abort
~~~

Abort is the right choice when you realize you picked the wrong boundary or destination, conflicts are too complex, or you want to prepare again before retrying. The backup branch remains useful for reference if needed.

## 10. Quality verification after moving history

A successful rebase only proves Git created a new history; it does not prove the functionality is still correct. Verify the commit graph, change contents, and project behavior.

~~~bash
# View new history
git log --oneline --graph --decorate --all -n 30

# Compare old and new commit chains
git range-diff feature/auth..backup/feature-ui-before-onto origin/main..feature/ui

# View branch changes relative to the new base
git diff origin/main...feature/ui

# Check repository status
git status --short --branch
~~~

git range-diff helps compare the commit chains before and after rewriting, which is useful for spotting missing commits, unexpected patch changes, or reordered commits. The ranges must accurately represent the old and new commit chains for your current case.

Next, run the project's checks, such as unit tests, integration tests, builds, or documentation checks. For a branch detached from a dependency, pay special attention to testing components previously provided by the dependency branch.

Once you have confirmed the new branch is correct, you may keep the backup branch for a while per team policy. Only delete it when it is no longer needed for comparison or recovery.

## 11. Sharing the rebased branch

Rebase creates new commits, so the identifiers of replayed commits change. If the branch has never been pushed or used by others, a normal push is usually sufficient:

~~~bash
git push -u origin feature/ui
~~~

If the branch was pushed before rebasing, the remote still holds the old commits. A normal push may be rejected as non-fast-forward. For a personal branch where the team permits rewriting history, you can update it with:

~~~bash
git push --force-with-lease origin feature/ui
~~~

--force-with-lease verifies the remote position is still as expected before force-updating. If a teammate pushed another commit after your last fetch, Git may reject the push to avoid overwriting new changes. Fetch, inspect, and coordinate before retrying.

Do not force push shared branches or branches others rely on without an explicit agreement. For main, release, and integration branches, follow the repository's branch protection rules.

## 12. A practical checklist

~~~bash
# Confirm initial state
git status --short --branch

# Update remote if the destination is on the remote
git fetch origin

# Preserve branch position before rewriting
git branch backup/topic-before-onto topic

# Inspect the commit set to move
git log --oneline --reverse old-base..topic

# Move topic's unique commits onto new-base
git rebase --onto new-base old-base topic

# If conflicts occur: edit files, stage, continue
git status
git add path/to/resolved-file
git rebase --continue

# Inspect history and compare commit chains
git log --oneline --graph --decorate --all
git range-diff old-base..backup/topic new-base..topic

# Run project checks then share per team policy
git status --short --branch
git push
~~~

Replace old-base, new-base, topic, and file paths with actual names. If the branch has already been shared and rebasing is permitted by the team, align beforehand on how to update the remote; otherwise, consider merging or creating a new branch instead of rewriting shared history.

## 13. Common mistakes when using --onto

### Swapping newbase and upstream

The two parameters serve different roles. Newbase is where the new commits will be replayed; upstream is the boundary used to determine which commits to pick. Swapping them can make Git produce a history completely different from your goal. Re-read the command asking: "Which commits do I want to keep, and where do I want to place them?"

### Choosing an upstream boundary that is too old or too new

If the boundary is too old, the selected commit set may include changes that do not belong to the branch being moved. If the boundary is too new, some desired commits may be excluded because they are already in upstream's history. Inspect the list with git log --reverse upstream..branch before rebasing.

### Assuming rebase only moves a pointer

Rebase replays commits and creates new commit IDs. Commit signatures, timestamps, and parent relationships can change. If the branch is shared, this impacts other people.

### Overlooking commit dependencies

A commit may rely on classes, APIs, configs, or schemas from the branch excluded from the new history. Rebase may succeed while builds/tests fail. Check dependencies and run tests after moving.

### Using --skip just to keep rebase moving

Skip drops the current commit from the new history. Without understanding the commit's patch, you may accidentally drop needed functionality. Only skip when you have confirmed the change is redundant or no longer needed.

## 14. Summary

- git rebase --onto NEWBASE UPSTREAM BRANCH separates the destination from the commit-selection boundary.
- The selected commit set consists of commits reachable from branch but not reachable from upstream.
- For linear history, you can preview that set with git log --reverse upstream..branch.
- Use --onto to change bases or detach a child branch from a dependent branch.
- Create a backup branch and inspect the working tree before rewriting history.
- Resolve conflicts by editing files, git add, and git rebase --continue; use --abort to cancel or --skip to intentionally drop the current commit.
- Use git range-diff, log, diff, and tests to verify the new history.
- Coordinate before force-updating a shared branch; prefer --force-with-lease when policy permits.

git rebase --onto is a tool for moving an exact portion of history to a new base. When you accurately identify the boundary, destination, and commits to keep, you can reorganize dependencies between branches while staying in control of your work's content and history.

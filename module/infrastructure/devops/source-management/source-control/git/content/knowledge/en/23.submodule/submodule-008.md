# Detecting Dirty Submodules, Unpublished Commits, and Gitlink Conflicts

When working with Git submodules, the parent repository (superproject) only records the specific commit each submodule is pinned to. Files modified inside a submodule belong to the child repository's working tree; new commits also belong to the child repository's history. Therefore, a line like `modified: libs/shared-utils` in the parent repository can represent several different situations: modified child files, untracked files, the submodule sitting at a different commit than the recorded gitlink, or a conflict when two parent branches select different child commits.

You must distinguish these states before committing, switching branches, or completing a merge/rebase. If you only stage the submodule path in the parent repository without handling the contents inside the child repository, child file changes may remain uncommitted. Conversely, if a submodule commit has not been pushed to a remote accessible to teammates, they may receive the gitlink yet fail to download the referenced commit.

## 1. Three States to Distinguish

There are three common categories of issues:

| State | What Changed? | Where to Handle It |
|---|---|---|
| Dirty submodule | Tracked files modified or untracked files present inside the submodule | Child repository's working tree/index |
| Unpublished commit | Submodule has local commits not yet pushed to the remote used by the team | Child repository's branch/ref and remote |
| Gitlink conflict | Two sides of the superproject require two different commits for the same submodule | Superproject's index and child repository's history |

All three states can occur simultaneously. For example, you edit files in the submodule, commit on a local branch without pushing, and a teammate simultaneously updates the gitlink on another branch of the superproject. During merge, the parent repository may report a gitlink conflict while the child repository still has unpublished commits or uncommitted files.

Inspect each repository within its proper scope. Commands run in the superproject reveal gitlink status; commands run inside the submodule reveal child file and commit status.

## 2. Detecting a Dirty Submodule from the Parent Repository

Start with the overall status:

```bash
git status
git status --short --ignore-submodules=none
```

Depending on the state inside the submodule, Git may display descriptions such as:

- `modified content`: tracked file contents inside the submodule have changed.
- `untracked content`: untracked files exist inside the submodule.
- `new commits`: the submodule's HEAD differs from the commit recorded by the superproject.

If a submodule ignore setting is hiding certain changes, `--ignore-submodules=none` tells the status command to consider all changes. This option is useful when diagnosing issues rather than viewing filtered status.

Check each submodule's ignore configuration if status appears incomplete:

```bash
git config -f .gitmodules --get-regexp '^submodule\..*\.ignore$'
git config --show-origin --get-regexp '^submodule\..*\.ignore$'
```

Common values are `none` (consider both tracked and untracked files), `untracked` (ignore untracked files), `dirty` (ignore working tree changes while still reporting commit pointer differences), and `all` (ignore all submodule changes in status/diff). Local settings in `.git/config` can override values from `.gitmodules`; use `--ignore-submodules=none` when you need to force status to display changes.

To inspect pinned commit status and initialization status:

```bash
git submodule status --recursive
```

Leading characters typically mean:

| Symbol | Meaning |
|---|---|
| Space | Submodule is at the commit recorded by the superproject |
| `-` | Submodule has not been initialized |
| `+` | Current HEAD differs from the commit recorded by the superproject |
| `U` | Gitlink has an unresolved conflict |

This command is useful for checking commit pointers, though it does not replace running `git status` inside individual submodules to detect modified or untracked files.

You can view submodule commit changes in log format:

```bash
git diff --submodule=log
git diff --cached --submodule=log
```

The first command shows unstaged gitlink differences; the second shows staged differences in the superproject's index. These commands help reveal which child commits were added or removed between two revisions.

## 3. Inspecting Details Inside Each Submodule

Use `git -C` to run commands inside the child repository without switching terminals:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils status --short --untracked-files=all
git -C libs/shared-utils branch -vv
git -C libs/shared-utils log --oneline --decorate -8
```

These commands answer different questions:

- `status`: are there modified, staged, or untracked files?
- `status --short --untracked-files=all`: lists each individual file, including untracked files nested inside directories.
- `branch -vv`: which remote-tracking branch is the current branch following, and is it ahead/behind?
- `log`: what are the most recent commits that the submodule's HEAD points to?

If the repository has many submodules, you can run status across all initialized submodules:

```bash
git submodule foreach --recursive 'git status --short --branch'
```

The `foreach` command executes the command in each submodule; `--recursive` descends into nested submodules. It does not initialize submodules that have not yet been initialized. If you need to inspect one specific submodule, use `git -C <path>` to narrow the scope.

An important reminder: the superproject does not store file changes inside submodules. It only stores a gitlink to a child commit. Therefore, running `git add libs/shared-utils` in the parent repository does not stage individual modified files in `libs/shared-utils`; those files must be handled inside the child repository first.

## 4. Distinguishing Modified Files, Untracked Files, and New Commits

Example status inside a submodule:

```text
 M src/parser.java
?? tmp/debug-output.txt
```

- `M` indicates a modified tracked file.
- `??` indicates an untracked file.

If there is a new local commit, `git status` inside the submodule may be clean even while the superproject still reports the submodule has `new commits`. That is not a dirty file state; it means the child repository's HEAD has moved to a different commit from the gitlink.

For example:

```text
Superproject expects:  a1b2c3d
Submodule HEAD:        e4f5a6b
```

You can inspect the commit pointer recorded by the superproject:

```bash
git ls-tree HEAD libs/shared-utils
git ls-files --stage -- libs/shared-utils
```

`git ls-tree` inspects the gitlink in the parent repository's current commit; `git ls-files --stage` inspects the corresponding entry in the index. For a gitlink, the mode is normally `160000`.

To compare the commit currently checked out inside the submodule:

```bash
git -C libs/shared-utils rev-parse HEAD
git -C libs/shared-utils status --short
```

If HEAD differs from the gitlink while the child repository has no modified files, the change in the parent repository may simply be a dependency version update. If files inside remain dirty, resolve those files before deciding whether to record the new commit pointer.

## 5. Detecting Unpublished Submodule Commits

An unpublished local commit is a commit not yet present on the remote that the team intends to use to fetch the submodule. First, update remote-tracking refs inside the child repository:

```bash
git -C libs/shared-utils fetch --all --prune
```

Fetching only updates remote-tracking information and objects inside the child repository; it does not modify the working tree or the superproject's gitlink.

Inspect branches and upstreams:

```bash
git -C libs/shared-utils branch -vv
```

If the current branch has an upstream, inspect local commits not yet on upstream:

```bash
git -C libs/shared-utils log --oneline '@{upstream}..HEAD'
```

Each listed commit is reachable from HEAD but not reachable from the specified upstream. If there is no upstream, Git cannot infer which remote branch you intend to publish to; identify the right remote and branch before comparing.

You can check the ahead/behind commit counts:

```bash
git -C libs/shared-utils rev-list --left-right --count '@{upstream}...HEAD'
```

The first number is commits only in upstream (local is behind); the second is commits only in HEAD (local is ahead). Output `0 2` means the local branch has two commits not yet in upstream and is missing none from upstream.

If you want to view commits reachable from HEAD but not reachable from any remote-tracking branch:

```bash
git -C libs/shared-utils log --oneline HEAD --not --remotes
```

This is a broad check; a commit might already exist on another remote or another branch not used by the team. Therefore, when saying "unpublished," identify the specific target remote/branch rather than relying solely on whether the commit appears in any arbitrary remote-tracking ref.

To check which remote branches already contain a specific commit:

```bash
git -C libs/shared-utils branch -r --contains <commit-oid>
```

If no branch is listed, the commit is currently not reachable from fetched remote-tracking branches. That still does not prove the commit is absent from every server or hidden ref; check the exact remote your team uses.

If you want to test pushing without updating the remote, you can use `git push --dry-run` with an explicit remote and refspec. For example:

```bash
git -C libs/shared-utils push --dry-run origin HEAD:refs/heads/fix/parser-edge-case
```

Dry-run validates the planned push, though it does not replace verifying that teammates can access the commit through the proper remote/branch.

## 6. Handling Dirty Submodules Before Switching Branches or Committing the Parent Repository

If files inside the submodule are modified, decide whether to keep, commit, stash, or discard changes inside the child repository itself.

**If changes should be kept and shared**, commit inside the submodule:

Before switching branches, inspect and preserve all current changes. If a working branch does not exist yet, create a new branch; if it already exists, switch to it.

```bash
git -C libs/shared-utils status
# Run this command only if the branch does not exist yet
git -C libs/shared-utils switch -c fix/parser-edge-case
git -C libs/shared-utils add src/parser.java
git -C libs/shared-utils commit -m "Fix parser edge case"
```

Then push the child commit to the shared remote:

```bash
git -C libs/shared-utils push -u origin fix/parser-edge-case
```

Finally, return to the superproject and record the new gitlink:

```bash
git add -- libs/shared-utils
git diff --cached --submodule=log
git status
```

**If changes are not ready to commit**, you can stash inside the submodule:

```bash
git -C libs/shared-utils stash push -u -m "WIP before switching task"
```

The `-u` option includes untracked files in the stash. It does not include ignored files; if you need to preserve ignored files too, review carefully before using `-a`. Then verify:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils stash list
```

When you need to restore:

```bash
git -C libs/shared-utils stash pop
```

If you want to keep the stash until you have verified the result, use `git stash apply` first and drop the stash later. If conflicts occur during restoration, resolve them inside the child repository like a normal conflict.

**If files do not need to be kept**, delete them only after verifying exact paths and contents. Avoid running `git reset --hard` or `git clean -fdx` mechanically inside a submodule: those commands can delete local changes, untracked files, or ignored files you still need.

## 7. Why Do Gitlink Conflicts Occur in the Superproject?

A gitlink is an entry in the parent repository's tree/index pointing to a submodule commit. When two superproject branches both change the gitlink of the same path to two different commits, a merge may not be able to choose a version automatically.

For example, two branches start from gitlink `S0`:

```text
                  S1  (feature branch)
                 /
Superproject: A
                 \
                  S2  (release branch)

S0 = common submodule commit before branching
```

The feature branch updates the submodule to `S1`; the release branch updates it to `S2`. When merging the two superproject branches, Git must decide which commit the final gitlink points to.

If one commit is an ancestor of the other, Git can fast-forward the gitlink to the descendant commit. If both sides diverged, Git can only choose automatically if it finds a suitable merge commit that already combines both histories; otherwise, Git may report:

```text
Failed to merge submodule libs/shared-utils
CONFLICT (submodule): Merge conflict in libs/shared-utils
```

This is a commit-pointer-level conflict. Git cannot automatically merge files inside the child repository simply by blending two commit IDs. You must choose an appropriate commit or create a merge commit inside the submodule itself and then record the new gitlink in the parent repository.

## 8. Identifying the Sides of a Gitlink Conflict

In the superproject, check status:

```bash
git status
git diff --name-only --diff-filter=U
```

Then inspect the stages in the index:

```bash
git ls-files -u -- libs/shared-utils
```

Output may look like:

```text
160000 <base-oid>   1    libs/shared-utils
160000 <ours-oid>   2    libs/shared-utils
160000 <theirs-oid> 3    libs/shared-utils
```

Meaning:

| Stage | Meaning |
|---|---|
| 1 | Gitlink at the common base before either branch changed it |
| 2 | Gitlink from the ours side of the merge operation |
| 3 | Gitlink from the theirs side of the merge operation |

Mode `160000` confirms this is a gitlink. The OIDs are commits of the child repository, not blobs or tree files of the superproject. Therefore, you cannot use `git show :2:libs/shared-utils` as you would when reading an ordinary text file; retrieve the OIDs from `git ls-files -u` and inspect those commits inside the child repository.

Depending on the conflict type, stages 1, 2, and 3 are not always all present. For instance, if the submodule was added independently on both sides, there may be no base stage; if one side deleted the path, its corresponding stage may be absent.

You can inspect the history on each side with:

```bash
git -C libs/shared-utils show --no-patch --oneline <ours-oid>
git -C libs/shared-utils show --no-patch --oneline <theirs-oid>
git -C libs/shared-utils merge-base <ours-oid> <theirs-oid>
```

If a commit is not yet in the submodule's object database, fetch from the corresponding remote first. Do not assume every OID in the superproject's index has already been downloaded into the local child repository.

## 9. Resolving a Gitlink Conflict by Choosing One Side

If the team has decided only one of the two commits is needed, you can check out the chosen commit inside the child repository and then stage the gitlink in the parent repository.

Example selecting the commit from the ours side:

Before changing the submodule's HEAD, inspect the child working tree. If there are modified or untracked files to keep, commit or stash them first; checking out another OID may be rejected by Git or leave state hard to track.

```bash
git -C libs/shared-utils fetch --all
git -C libs/shared-utils status --short
# Proceed only when the working tree is clean or changes are preserved
git -C libs/shared-utils switch --detach <ours-oid>

# Run required checks inside the submodule
git -C libs/shared-utils status

# Return to superproject and stage the selected gitlink
git add -- libs/shared-utils
git status
git diff --cached --submodule=log
```

If selecting the theirs side, replace `<ours-oid>` with `<theirs-oid>`. Choosing one side only decides the final commit pointer; it does not integrate independent commits from the other side. Make sure the omitted changes are unnecessary or have already been integrated elsewhere.

After staging, check `git ls-files -u -- libs/shared-utils`. If no output remains for that path, the conflict stages have been replaced in the index by the selected gitlink.

## 10. Resolving by Merging Inside the Submodule

If both sides have changes that need to be preserved, combine the histories inside the child repository.

First, obtain the OIDs from stage 2 and stage 3 of the superproject, ensuring those commits are present in the submodule and the child working tree is clean:

```bash
git -C libs/shared-utils fetch --all
git -C libs/shared-utils status
```

Create a conflict-resolution branch starting from the ours commit:

```bash
git -C libs/shared-utils switch -c resolve/shared-utils-gitlink <ours-oid>
```

Merge the theirs commit into that branch:

```bash
git -C libs/shared-utils merge <theirs-oid>
```

If merging inside the submodule produces file conflicts, resolve them like a normal Git repository:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils add <resolved-file>
git -C libs/shared-utils commit
```

If Git creates a merge commit automatically, inspect the submodule's history and run tests. Once the resulting commit exists, push it to a remote accessible to other team members:

```bash
git -C libs/shared-utils push -u origin resolve/shared-utils-gitlink
```

Finally, in the superproject, stage the gitlink pointing to the new merge commit:

```bash
git add -- libs/shared-utils
git diff --cached --submodule=log
git status
```

The resulting commit in the superproject will record the new gitlink. When teammates pull the superproject commit, they must also have access to the pushed child commit so submodule update can check it out.

If the two commits do not share history or cannot be merged directly, do not fabricate an artificial merge commit just to silence the conflict. Inspect remotes, branches, and ancestry; you may need to fetch the right repository or coordinate with the submodule maintainers.

## 11. Completing the Merge/Rebase in the Superproject

After the gitlink conflict is resolved and staged, inspect the full state of the parent repository:

```bash
git status
git diff --cached --submodule=log
git diff --name-only --diff-filter=U
```

If other files remain unmerged, resolve them according to the appropriate workflow. When no conflicts remain, continue the paused operation:

```bash
# If merging
git merge --continue

# If rebasing
git rebase --continue

# If cherry-picking
git cherry-pick --continue
```

After the operation completes, verify again:

```bash
git status
git submodule status --recursive
git diff HEAD^ HEAD --submodule=log
```

The last command shows gitlink changes in the newly created commit (adjust the revision range if the operation produced multiple commits). If the superproject commit references a new submodule commit, ensure that commit was pushed to the child remote before pushing the superproject.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| `git add <submodule-path>` stages modified child files | It updates the gitlink in the superproject; child files must be staged/committed inside the submodule |
| Submodule reporting modified means only files were edited | It can mean dirty files, untracked content, or HEAD differing from the gitlink |
| `git submodule status` without `+` means the submodule is clean | It primarily reflects commit pointer/init/conflict; you still need `git -C <path> status` |
| A local child commit is enough for teammates to use | The commit must exist on a remote accessible to teammates |
| A gitlink conflict is a text conflict | It is a conflict between commit OIDs; choose a pointer or merge history in the child repository |
| Staging the gitlink resolves child file contents | Staging the gitlink does not commit dirty files inside the submodule |
| `git submodule update` always fetches the latest commit | By default it checks out the commit pinned by the superproject; `--remote` explicitly tracks remote branches |
| You can discard dirty state with reset/clean | Those commands can wipe out unpreserved work |

## 13. Checklist Before Committing or Pushing the Superproject

Before recording submodule changes in the parent repository, verify:

1. Is the submodule initialized? Run `git submodule status --recursive`.
2. Does the child working tree have modified tracked files or untracked files? Run `git -C <path> status --short --untracked-files=all`.
3. Does the child HEAD differ from the gitlink required by the superproject? Compare `git ls-tree HEAD <path>` with `git -C <path> rev-parse HEAD`.
4. Is the new child commit on a remote/branch used by the team? Fetch and compare against upstream.
5. If there is a gitlink conflict, have you inspected stages 1/2/3 with `git ls-files -u`?
6. If two child histories needed merging, has the merge commit been pushed to remote?
7. Does the superproject's staged diff point to the intended child commit? Check `git diff --cached --submodule=log`.
8. Have all other conflicted files in the superproject been resolved?

These checks help avoid committing a gitlink pointing to an unshared commit or overlooking file changes inside the child repository.

## Conclusion

Diagnose submodules at two levels: the superproject reveals commit pointers and gitlink conflicts; the child repository reveals dirty files, untracked files, and local commits. Use `git status --ignore-submodules=none`, `git submodule status`, `git submodule foreach`, and `git -C <path> status` to inspect the true state. Before sharing a new gitlink, push the child commit to the appropriate remote. For gitlink conflicts, inspect stages 1/2/3, select one commit if only one side is needed, or create a merge commit inside the submodule if both histories must be kept, then stage the gitlink and finish the operation in the parent repository.

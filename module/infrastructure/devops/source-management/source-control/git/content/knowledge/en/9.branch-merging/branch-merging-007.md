# Merging State: MERGE_HEAD, Index, and Working Tree

When a merge command has not yet completed, the state of the repository is reflected simultaneously across several places: pseudo-refs and state files in the Git directory, the index (staging area), the working tree, and the summary reported by `git status`. Understanding these components helps you know which commit Git is merging, which files were merged automatically, which files still have conflicts, and when you can continue or abort the operation.

A common misconception is that "currently merging" is synonymous with "currently has conflicts." Git may have merged all files successfully yet still be waiting for you to create the merge commit, such as when using `--no-commit`. Conversely, after you resolve all conflicts and stage the result, the repository remains in the merging state until the merge is finalized.

After this lesson, you will be able to:

- Explain the role of `MERGE_HEAD` and related state information.
- Identify the commit being merged into HEAD.
- Read stages in the index and distinguish merged files from unresolved files.
- Understand working tree contents when a merge succeeds or has conflicts.
- Combine `git status`, `git ls-files`, `git diff`, and `git rev-parse` for diagnostics.
- Complete a merge with `git merge --continue` or `git commit`.
- Distinguish `--abort` from `--quit` and understand how fast-forward differs.

## 1. Three State Areas During a Merge

A merge affects three working components:

| Component | Role during merge |
| --- | --- |
| HEAD and merge state | Identify the current commit and the incoming commit; store state so Git knows a merge is in progress. |
| Index | Stores automatically merged results and the versions needed to resolve conflicts. |
| Working tree | Contains file contents after automatic merging or contents with conflict markers for you to edit. |

In a normal two-branch merge, HEAD continues pointing to the current branch's commit throughout the pending merge state. The commit of the branch being merged in is recorded in `MERGE_HEAD`. When creating the merge commit, the new commit normally has the current HEAD as its first parent and the commit from `MERGE_HEAD` as its second parent.

~~~text
                 merge feature
main:     A---B---C  (HEAD)
                  \
feature:           D---E

While merge is pending:
HEAD       -> C
MERGE_HEAD -> E
Index      -> merged result + conflict entries
Working tree -> merged files or conflicted files

After merge commit:
                 M  (HEAD)
                / \
main:     A---B---C   E
                  \ /
feature:           D
~~~

The diagram only illustrates a two-branch merge. In an octopus merge, multiple commits may be recorded in `MERGE_HEAD` and the merge commit has more than two parents.

## 2. What Is MERGE_HEAD?

`MERGE_HEAD` is a pseudo-ref used by Git during a merge to record the object ID of the commit or commits being merged into HEAD. In a normal two-branch merge, this file contains the single OID of the incoming commit.

For example, suppose you are on `main` and run:

~~~bash
git merge feature/search
~~~

If Git starts a real merge and has not completed it yet, `MERGE_HEAD` stores the tip commit of `feature/search` being brought in. HEAD continues pointing to the current commit of `main` until the merge commit is created.

`MERGE_HEAD` holds a commit identifier, not a branch name. The name `feature/search` is what you passed to the merge command; during processing, Git works with the commit that ref resolves to.

Check the state:

~~~bash
git rev-parse --verify MERGE_HEAD
~~~

If the command resolves `MERGE_HEAD`, the repository has a corresponding merge state. If it fails to resolve, there may be no merge pending completion or you may be in a different operation state.

Inspect the incoming commit:

~~~bash
git show --no-patch --oneline MERGE_HEAD
git show -s --format=fuller MERGE_HEAD
~~~

To find where the Git directory stores this file, use:

~~~bash
git rev-parse --git-path MERGE_HEAD
~~~

Do not assume the path is always `.git/MERGE_HEAD`. Linked worktrees and special repository layouts may place the Git directory elsewhere.

## 3. Related State Information

During an ongoing merge, you may encounter the following administrative files or refs:

| Name | Role |
| --- | --- |
| `MERGE_HEAD` | Commit or commits being merged into HEAD. |
| `MERGE_MSG` | Prepared merge message to be used when creating the merge commit. |
| `MERGE_MODE` | Merge mode information used by Git in certain processing flows. |
| `ORIG_HEAD` | Stores HEAD's position prior to certain operations that move HEAD, including merge. |
| `AUTO_MERGE` | Ref that may be created by the `ort` merge strategy on conflict, pointing to the auto-merged tree before your resolution. |

Not every repository or every merge type has all of these files/refs. They are state details managed by Git; use Git commands to inspect them instead of editing or deleting them manually.

### MERGE_MSG

Git can prepare a default message for the merge commit. View the commit message content after the merge completes with:

~~~bash
git log -1 --format=%B
~~~

If you need to locate the message file during a merge:

~~~bash
git rev-parse --git-path MERGE_MSG
~~~

When finishing with `git commit`, Git usually opens the editor with the default merge message if configuration and options allow. You can edit the message to explain the purpose of the integration.

### ORIG_HEAD

`ORIG_HEAD` normally records the commit HEAD pointed to before the merge operation began:

~~~bash
git show -s --oneline ORIG_HEAD
~~~

This is a useful reference point for checking the original position. However, `ORIG_HEAD` is also used by other operations, so do not treat it as a permanent backup or assume it always points to the merge baseline if you subsequently run other commands that overwrite it.

### AUTO_MERGE

With the `ort` merge strategy, when conflicts occur, Git may create an `AUTO_MERGE` ref pointing to the working tree automatically generated at the time of conflict. You can inspect the difference between that automatic state and the current working tree using:

~~~bash
git diff AUTO_MERGE
~~~

This command can help you see what you edited after Git paused at a conflict. `AUTO_MERGE` is not created in every merge type or every Git version.

## 4. How Does the Index Store Merge Results?

The index does not only hold a single version per file in every situation. When automatic merging succeeds for a path, Git normally records the result at stage 0. When a path is not yet resolved, the index can hold multiple entries at stages 1, 2, and 3.

| Stage | Meaning in a two-branch merge |
| --- | --- |
| 0 | Normal staged version, no unmerged entries remaining for that path. |
| 1 | Common base version (merge base). |
| 2 | Current side version (ours), typically taken from HEAD before the merge. |
| 3 | Incoming side version (theirs), from the commit being merged in. |

For a conflicted path, stage 0 normally does not exist yet. Instead, Git keeps the necessary stages so you can compare contents. Not every conflict has all three stages 1, 2, and 3; for example, an add/add conflict may have no base stage.

List unmerged entries:

~~~bash
git ls-files --unmerged
~~~

List the entire index with mode, OID, and stage:

~~~bash
git ls-files --stage
~~~

Example of a modify/modify path:

~~~text
100644 111aaa... 1    src/Search.java
100644 222bbb... 2    src/Search.java
100644 333ccc... 3    src/Search.java
~~~

The output shows that Git holds the base, current version, and incoming version for `src/Search.java`.

## 5. Automatically Merged Files vs. Conflicted Files

In a merge containing both clean and conflicted files:

- Files Git merged automatically normally have a single stage 0 entry in the index.
- Unresolved files have unmerged entries at stages 1/2/3 depending on the conflict type.
- The working tree contains the merged result content for clean files.
- The working tree for text-conflicted files typically contains conflict markers.

Example:

~~~text
<<<<<<< HEAD
return normalize(query);
=======
return sanitize(query);
>>>>>>> feature/search
~~~

Markers help you edit the final content. They are not the stage 1/2/3 data itself; the original versions remain stored in the index until you stage the resolved result.

For binary files or certain rename/delete conflicts, Git cannot insert text markers in this way. You must select or produce the final content using an appropriate tool, then stage the result.

## 6. State of the Working Tree During a Merge

The working tree is where you see the results to review and edit:

- Automatically merged files contain the combined content.
- Text-conflicted files usually contain markers.
- Files deleted on one side may be absent from the working tree or retained depending on how you resolve them.
- New files created by one side may appear in the working tree.

View overall status:

~~~bash
git status
~~~

View unstaged changes in the working tree:

~~~bash
git diff
~~~

View changes currently in the index relative to HEAD:

~~~bash
git diff --cached
~~~

For unmerged paths, also use:

~~~bash
git ls-files -u
git diff --cc
~~~

`git diff --cc` displays a combined diff for unmerged files, useful for reviewing conflicted regions alongside markers. Directly reading the file in the working tree is still necessary to understand the exact content you will stage.

## 7. git status Shows What Stage the Merge Is In

During a merge, `git status` normally shows the current branch, the branch being merged, and the list of paths needing resolution. Example:

~~~text
On branch main
You have unmerged paths.
  (fix conflicts and run "git commit")

Unmerged paths:
  both modified:   src/Search.java
~~~

After you resolve and stage all conflicted paths, the message can change to:

~~~text
All conflicts fixed but you are still merging.
  (use "git commit" to conclude merge)
~~~

This second message is crucial: the index has no more conflicts, yet the merge is not finished. `MERGE_HEAD` still exists until Git creates the merge commit or you abort/quit the merge state.

You can check quickly:

~~~bash
git status --short --branch
git ls-files --unmerged
git rev-parse --verify MERGE_HEAD
~~~

These three commands answer three questions:

1. What are the current branch and file statuses?
2. Are any conflict entries left in the index?
3. Does Git still have a merge state with `MERGE_HEAD`?

## 8. An Ongoing Merge Does Not Necessarily Have Conflicts

You can ask Git to pause before creating a merge commit:

~~~bash
git merge --no-commit --no-ff feature/search
~~~

`--no-commit` asks Git to pause before the commit creation step so you can inspect the result. `--no-ff` forces creating a merge commit instead of fast-forwarding, since a fast-forward has no merge commit to pause before.

In this case:

- Git may have merged all files automatically.
- `git ls-files --unmerged` may return nothing.
- `MERGE_HEAD` still exists because the merge commit has not been created yet.
- `git status` shows you are still in a merge.

Therefore, do not use `git ls-files -u` alone to conclude whether a merge state exists. That command only checks whether unmerged entries remain.

## 9. Fast-Forward vs. a Merge Waiting for Commit

If the current branch is a direct ancestor of the target branch, Git can fast-forward:

~~~bash
git merge feature/search
~~~

Git merely moves the current branch ref to the newer commit. No merge commit is needed and the operation typically completes immediately, so once the command finishes there is no pending `MERGE_HEAD`.

If you want to force a merge commit:

~~~bash
git merge --no-ff feature/search
~~~

If you want to pause before committing to review:

~~~bash
git merge --no-ff --no-commit feature/search
~~~

| Merge type | Result | Merge state still pending after command returns? |
| --- | --- | --- |
| Fast-forward | Moves branch pointer, no merge commit created | Normally no |
| Non-fast-forward auto-completes | Creates merge commit | No |
| Non-fast-forward with `--no-commit` | Index/working tree merged, waiting for commit | Yes |
| Merge with conflicts | Stops for resolution | Yes |

This is why you must distinguish "the merge command ran" from "the merge operation is still in progress."

## 10. Inspecting the Incoming Commit and Initial Baseline

While a merge is in progress:

~~~bash
# Current commit before merge commit is created
git show -s --oneline HEAD

# Incoming commit
git show -s --oneline MERGE_HEAD

# HEAD position before operation
git show -s --oneline ORIG_HEAD
~~~

In a two-branch merge, `HEAD` typically stays on the current side and `MERGE_HEAD` is the incoming side. Once the merge finishes, the new commit will have both as parents. Inspect the merge commit's parents:

~~~bash
git show -s --format=%P HEAD
~~~

The output lists the parent OIDs of the current commit. For a two-branch merge, there are usually two OIDs; for an octopus merge, there may be more.

Do not confuse `FETCH_HEAD` with `MERGE_HEAD`. `FETCH_HEAD` records refs/commits received from the most recent fetch; `MERGE_HEAD` represents the commit being merged into HEAD during an ongoing merge.

## 11. Reading Each Version's Content from the Index

For a path that has all stages present:

~~~bash
# Base
git show :1:src/Search.java

# Ours: current side
git show :2:src/Search.java

# Theirs: incoming side
git show :3:src/Search.java
~~~

If a stage does not exist, the corresponding command fails. This is normal in conflict types where one side has no version.

In a normal merge, stage 2 is the current side and stage 3 is the incoming side. During a rebase, the ours/theirs labels can feel counterintuitive because Git is replaying commits onto the target branch; this lesson focuses on two-branch merges, so clearly identify the active operation before choosing content.

## 12. Staging the Conflict Resolution Result

After editing the file content in the working tree:

~~~bash
git add src/Search.java
~~~

Git writes the final content into the index at stage 0 and removes the unmerged entries for that path. When resolving by deleting the file:

~~~bash
git rm -- src/Search.java
~~~

Then verify:

~~~bash
git ls-files --unmerged
git ls-files --stage -- src/Search.java
git diff --cached
git status
~~~

If `git ls-files --unmerged` no longer lists the path, the conflict entries for that path have been resolved. If every path has been handled, status will report that all conflicts are fixed while the merge is still waiting to be concluded.

Staging the result does not automatically create the merge commit. It only updates the index so Git knows the final snapshot for each path.

## 13. Completing the Merge

Once all conflicts are resolved and you have reviewed the index:

~~~bash
git status
git diff --cached
git ls-files --unmerged
~~~

Finish with:

~~~bash
git merge --continue
~~~

Or create the commit directly:

~~~bash
git commit
~~~

`git merge --continue` tells Git to continue the ongoing merge operation. In a standard merge, the command creates the merge commit once the index has no remaining conflicts. `git commit` can also conclude the merge by creating a commit from the index and existing merge metadata.

After completion:

~~~bash
git status --short --branch
git log -1 --oneline --decorate
git show -s --format=%P HEAD
git rev-parse --verify MERGE_HEAD
~~~

The merge state is cleaned up upon a successful commit; `MERGE_HEAD` no longer resolves. The new commit has parents reflecting the merged histories.

## 14. Canceling a Merge with git merge --abort

If you want to discard an ongoing merge and return to the state before it started:

~~~bash
git merge --abort
~~~

Git attempts to restore the index and working tree to the pre-merge state. Then verify:

~~~bash
git status --short --branch
git log -1 --oneline
git rev-parse --verify MERGE_HEAD
~~~

If the merge began when the working tree already had uncommitted changes, restoration may not perfectly reconstruct those changes in every scenario. Therefore, commit or stash local work before merging if you need guaranteed preservation.

`--abort` is the option when you want to discard merge results and return to the initial state. Do not manually delete `MERGE_HEAD` or state files as a substitute for this command.

## 15. Exiting Merge State with git merge --quit

`git merge --quit` serves a different purpose:

~~~bash
git merge --quit
~~~

The command forgets the ongoing merge state while leaving the index and working tree intact. It does not restore files to pre-merge state and does not resolve conflicts automatically.

After `--quit`, you may still have merged content in the working tree or unmerged entries in the index, but Git no longer treats the operation as a merge awaiting continuation. Therefore:

| Command | Effect |
| --- | --- |
| `git merge --continue` | Continues and completes the ongoing merge. |
| `git merge --abort` | Attempts to return to the state before the merge. |
| `git merge --quit` | Removes merge state, keeps the current index and working tree. |

Only use `--quit` when you intentionally want to keep the current file state without continuing the merge session under the current merge mechanism. It is not a normal way to clean up conflicts.

## 16. Do Not Manually Edit State Files in the Git Directory

While a merge is in progress, avoid:

- Deleting `MERGE_HEAD` using filesystem tools.
- Manually editing the OID inside `MERGE_HEAD`.
- Deleting `MERGE_MSG`, `ORIG_HEAD`, or the index file to "clean up" the state.
- Copying `.git/index` from another repository.

These files work together so Git understands the current state. Manual intervention can deprive Git of the ability to properly continue or abort the merge.

Use the high-level commands instead:

~~~bash
git status
git merge --continue
git merge --abort
git merge --quit
~~~

If you suspect repository corruption, record diagnostic output and make a safe backup before attempting repairs.

## 17. Distinguishing Merge from Other In-Progress Operations

Git uses different pseudo-refs for different operations:

| Name | Related operation |
| --- | --- |
| `MERGE_HEAD` | Commit or commits being merged into HEAD. |
| `CHERRY_PICK_HEAD` | Commit currently being cherry-picked. |
| `REVERT_HEAD` | Commit currently being reverted. |
| `REBASE_HEAD` | Commit currently being replayed in certain rebase states. |

When `git status` reports an operation in progress, read the specific message. Do not infer that every conflict is a merge; cherry-pick, revert, and rebase can also produce unmerged entries in the index.

Check merge state:

~~~bash
git rev-parse --verify -q MERGE_HEAD
~~~

Check cherry-pick state:

~~~bash
git rev-parse --verify -q CHERRY_PICK_HEAD
~~~

These commands can return a non-zero exit code if the pseudo-ref does not exist. Use exit codes in scripts rather than only checking output strings.

## 18. Workflow for Diagnosing an Ongoing Merge

When Git pauses mid-merge, inspect in order:

~~~bash
# 1. Branch and file overview
git status --short --branch

# 2. Identify merge state
git rev-parse --verify MERGE_HEAD

# 3. Inspect incoming commit
git show -s --oneline MERGE_HEAD

# 4. List unresolved paths
git ls-files --unmerged

# 5. Inspect changes in index and working tree
git diff --cached
git diff

# 6. Check state file locations if needed
git rev-parse --git-path MERGE_HEAD
git rev-parse --git-path MERGE_MSG
git rev-parse --git-path ORIG_HEAD
~~~

Then choose how to proceed:

- Conflicts remain: edit the working tree, `git add` or `git rm`, then re-check.
- No conflicts remain, yet merge is still pending: review the staged diff, then run `git merge --continue` or `git commit`.
- Want to return to pre-merge state: `git merge --abort`.
- Want to keep index/working tree as-is but drop merge state: only use `git merge --quit` once you understand the consequences.

After each action, re-run `git status` and check `MERGE_HEAD` to confirm the actual state.

## 19. Common Mistakes

### Seeing git ls-files -u Empty and Assuming the Merge Is Done

The command only tells you the index has no unmerged entries left. `MERGE_HEAD` can still exist if the merge is waiting to be committed, e.g., after `--no-commit`.

### Thinking MERGE_HEAD Contains a Branch Name

`MERGE_HEAD` contains the object ID of the commit being merged in, not the branch name the user typed.

### Thinking Every Merge Leaves MERGE_HEAD Around After the Command

Fast-forward updates the branch pointer and normally finishes immediately, leaving no pending merge state awaiting commit. Only merge commits or paused merges leave a pending state.

### Staged All Conflicts Yet Still Seeing "still merging"

This is normal. You resolved the conflicts, but still need to create the merge commit with `git merge --continue` or `git commit`.

### Using git merge --quit to Undo a Merge

`--quit` only forgets the merge state; it does not restore the index or working tree. Use `--abort` if you want to cancel the merge and return to the prior state.

### Manually Deleting MERGE_HEAD

This can leave the repository in an inconsistent state. Use `git merge --continue`, `--abort`, or `--quit`.

### Assuming Stages 1/2/3 Are Always All Present

Add/add, modify/delete, and rename conflicts can lack one or more stages. Read the actual entries reported by `git ls-files --unmerged`.

## 20. Takeaways

- `MERGE_HEAD` records the object ID of the commit or commits being merged into HEAD.
- During a pending two-branch merge, HEAD normally remains on the current commit; the incoming commit is stored in `MERGE_HEAD`.
- `MERGE_MSG` holds the prepared merge message; `ORIG_HEAD` normally saves the pre-operation HEAD; `AUTO_MERGE` may appear with the `ort` strategy.
- The index uses stage 0 for normal entries and stages 1/2/3 for conflict-related versions.
- Clean auto-merged files normally have stage 0; conflicted files have unmerged entries and the working tree may contain conflict markers.
- `git status` indicates merge state; `git ls-files -u` only checks for conflict entries and does not prove the merge is finished.
- A merge can be waiting for commit even without conflicts, such as when using `--no-commit --no-ff`.
- Fast-forward normally finishes immediately and leaves no pending `MERGE_HEAD`.
- `git merge --continue` or `git commit` completes the merge; `git merge --abort` attempts to restore pre-merge state; `git merge --quit` only drops merge state and leaves index/working tree unchanged.
- Use `git rev-parse --git-path` to locate state files instead of hardcoding `.git`.
- Never manually edit or delete merge state files.

The merging state is the coordination between `MERGE_HEAD`, the index, and the working tree. `MERGE_HEAD` tells you the incoming commit, the index tells you which versions are merged or still conflicted, and the working tree is where you review and finalize content. Inspecting all three together with `git status` lets you know exactly which stage the merge is in and choose the appropriate way to continue, abort, or quit.

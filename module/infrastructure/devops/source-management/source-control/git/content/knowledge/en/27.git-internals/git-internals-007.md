# The Index: Representing the Proposed Tree and Conflict Stages

In Git, the staging area is commonly understood as the place where content is prepared for the next commit. Internally, it is stored as the **index**: a data structure recording the path, mode, object ID, and state of each entry. When a repository is in a normal state, each tracked path typically has one index entry at stage 0. When a merge or other integration operation produces a conflict, a path can have multiple entries at stages 1, 2, and 3 to preserve the versions needed for resolution.

Understanding the index lets you see what directory tree Git is preparing to commit, why a conflicted file has multiple versions, and which commands turn those versions into the final result. This lesson focuses on index structure, the meaning of stages 0–3, inspection via plumbing commands, and a safe conflict resolution workflow.

## 1. What is the index and where does it live?

### 1.1. The index is the staging area

The index is the data structure Git uses to record the proposed snapshot for the next commit. When running:

~~~bash
git add src/PaymentService.java
~~~

Git reads the file contents in the working tree, creates or finds the corresponding blob object, and updates the entry in the index. From that moment on, the staged content is held in the index even if you continue editing the file on disk.

You can inspect all three states with:

~~~bash
git status
git diff
git diff --cached
~~~

- **git diff** compares the working tree against the index, showing unstaged changes.
- **git diff --cached** compares the index against `HEAD`, showing changes staged for commit.
- **git status** summarizes the state of the branch, index, and working tree.

The index is not a verbatim copy of the entire working tree. It records the content chosen for the next snapshot. Therefore, a file can simultaneously have both staged and unstaged changes if you edit it after running `git add`.

### 1.2. Location of the index file

In a standard repository, the index typically lives at `.git/index`. However, you should not assume that path is always fixed, because linked worktrees and certain repository layouts may use separate Git directories.

Get the exact path:

~~~bash
git rev-parse --git-path index
~~~

Inspect the Git directory and working tree root:

~~~bash
git rev-parse --git-dir
git rev-parse --show-toplevel
~~~

The index is a binary file managed by Git. Never edit it directly with a text editor or arbitrary scripts. Use commands like `git add`, `git rm`, `git restore --staged`, and equivalent Git commands to modify the index.

### 1.3. What information does the index store?

A typical index entry tracks:

- **Path:** relative path from the root of the working tree.
- **Mode:** entry type and executable permission.
- **Object ID (OID):** identifier of the referenced blob or gitlink.
- **Stage:** stage number indicating whether the entry is normal or one version of a conflicted path.
- **Flags and metadata:** information used for performance, status tracking, and how Git processes the entry.

The index does not store full file contents directly inside the entry. Content normally resides in the Git object database; the index references objects by OID.

## 2. Stage 0 and conflict stages

### 2.1. Stage 0 is the normal entry

When there is no conflict, a path normally has a single entry at stage 0. This is the content currently selected in the index for the next commit's tree.

Example:

~~~bash
git ls-files --stage -- src/PaymentService.java
~~~

Sample output:

~~~text
100644 6f1a... 0    src/PaymentService.java
~~~

Structure of each line:

~~~text
<mode> <object-id> <stage><TAB><path>
~~~

Where:

- **100644:** regular file without the executable bit.
- **100755:** regular file with the executable bit.
- **120000:** symbolic link; the OID points to the link target stored as a blob.
- **160000:** gitlink; the OID points to a submodule commit.
- **6f1a...:** OID of the object referenced by the index.
- **0:** stage 0, normal entry.
- **src/PaymentService.java:** path.

**Stage 0 does not mean "unstaged."** The stage number classifies index entries; stage 0 is still content already present in the staging area. Staged/unstaged status and stage numbers are two distinct concepts.

### 2.2. Stages 1, 2, and 3 store conflict versions

When Git cannot automatically combine a path during a merge, the index can hold up to three versions:

| Stage | Meaning | Common name |
| --- | --- | --- |
| 1 | Version from the common merge base | Base |
| 2 | Version from the side receiving changes | Ours |
| 3 | Version from the side being integrated | Theirs |

For example, if two branches both modify the same line:

- Base: `timeout=30`
- Ours: `timeout=45`
- Theirs: `timeout=60`

The index may contain:

~~~text
100644 <oid-base>   1    config/app.properties
100644 <oid-ours>   2    config/app.properties
100644 <oid-theirs> 3    config/app.properties
~~~

The conflicted path has multiple entries sharing the same name but with different stage numbers. Git does not yet have a single resolved stage-0 outcome for that path.

Once you edit the final content and run `git add`, Git writes a new blob into the index at stage 0 and removes the conflict entries at stages 1, 2, and 3 for that path.

### 2.3. Stages are not three copies in the working tree

The index holds the base, ours, and theirs versions as references to objects. The working tree normally has only one physical path for that file name.

For text conflicts, Git writes conflict markers into the working tree:

~~~text
<<<<<<< HEAD
timeout=45
=======
timeout=60
>>>>>>> feature/tune-timeout
~~~

Markers help users see the regions needing resolution. They are not the three stages inside the index, nor should they be committed automatically as the intended result. You must edit the content into the final version and re-stage it.

For binary files, Git cannot insert meaningful text markers. You must choose or construct the final binary content using appropriate tools and then stage the file.

## 3. Reading the index with git ls-files

### 3.1. Viewing all entries and stages

Command:

~~~bash
git ls-files --stage
~~~

Displays entries in the index along with mode, OID, and stage. This is the most useful command for directly observing index structure.

Limit to one file:

~~~bash
git ls-files --stage -- config/app.properties
~~~

Limit to one directory:

~~~bash
git ls-files --stage -- src/
~~~

In large repositories, constrain the path so the output remains readable.

### 3.2. Viewing only unmerged entries

Use:

~~~bash
git ls-files --unmerged
~~~

Or:

~~~bash
git ls-files -u
~~~

Both forms list unmerged entries, typically stages 1, 2, and 3. If there is no output, the index currently has no unmerged entries as reported by Git.

You can combine with a path:

~~~bash
git ls-files -u -- config/
~~~

This helps identify which files in the config directory still have conflicts.

### 3.3. Viewing detailed metadata for an index entry

Use:

~~~bash
git ls-files --debug -- config/app.properties
~~~

The `--debug` option adds internal details such as entry flags and metadata. Output is primarily for investigation; its format may change across Git versions, so do not treat it as a stable interface for scripts.

### 3.4. Distinguishing the index from the commit tree

The index is the snapshot being prepared. The commit tree is the structure already recorded in a commit.

View the tree of the current commit:

~~~bash
git ls-tree -r HEAD
~~~

View entries in the index:

~~~bash
git ls-files --stage
~~~

The two outputs differ when you have staged changes that are not yet committed. The commit tree reflects `HEAD`'s snapshot; the index reflects the proposed snapshot for the next commit.

## 4. Reading individual versions with stage syntax

### 4.1. Using git show :<stage>:<path>

Git lets you access the contents of each stage using a revision of the form colon, stage number, colon, and path. For example, to read stage 2 of a file, use the concrete commands shown below. Placeholder labels like stage name or path in documentation are not literal arguments to type verbatim into the shell.

Example:

~~~bash
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

These three commands display the base, ours, and theirs versions of the conflicted path respectively.

If a stage does not exist, the command returns an error. This is valid for certain conflict types and does not necessarily indicate index corruption.

You can also use `git cat-file -p` to read the object referenced by a stage:

~~~bash
git cat-file -p :2:config/app.properties
~~~

### 4.2. Note on paths with special characters

If a path contains spaces or shell special characters, enclose it in quotes:

~~~bash
git show ':2:config/production settings.yml'
~~~

The stage revision syntax is parsed by Git; quotes ensure the shell passes the argument intact without splitting or interpreting characters in the path.

### 4.3. Comparing against the working tree

During a conflict, you can compare what is currently in the working tree against each stage using dedicated diff options:

~~~bash
git diff --base -- config/app.properties
git diff --ours -- config/app.properties
git diff --theirs -- config/app.properties
git diff --cc -- config/app.properties
~~~

- **--base:** compares the working tree against stage 1.
- **--ours:** compares the working tree against stage 2.
- **--theirs:** compares the working tree against stage 3.
- **--cc:** displays a combined diff for conflicted regions.

These comparison options are only meaningful when the corresponding stage exists. If stage 1 or one side is missing, check `git ls-files -u` before using them.

## 5. Why does Git create multiple stages?

### 5.1. Content conflict during merge

Suppose `main` and `feature` both edit the same line in `config/app.properties`. Git finds the merge base, retrieves the versions from both branches, and attempts to combine them.

If the changes do not overlap, Git can merge automatically. If both modified the same region and cannot be combined automatically, Git retains the three versions at stages 1, 2, and 3 for the user to decide.

State:

~~~text
HEAD (main)       -> ours version
MERGE_HEAD        -> theirs version
Index:
  stage 1         -> merge base
  stage 2         -> ours
  stage 3         -> theirs
Working tree      -> content awaiting user resolution
~~~

In a normal merge, stage 2 corresponds to the current branch and stage 3 corresponds to the branch being merged in.

### 5.2. Add/add conflict

If both branches independently create a new path with different contents, no common version exists in the merge base.

Example:

- The current branch adds `config/new-feature.yml`.
- The merged branch also adds the same path with different contents.

The index may contain only stage 2 and stage 3; stage 1 does not exist because the file did not exist in the base.

~~~text
100644 <oid-ours>   2    config/new-feature.yml
100644 <oid-theirs> 3    config/new-feature.yml
~~~

Do not treat the absence of stage 1 as an error. This is the expected state for an add/add history.

### 5.3. Modify/delete conflict

One branch edits a file while the other branch deletes it. The index only has a version from the side that kept the file; the deleting side's stage has no entry.

For example, if ours edited and theirs deleted:

~~~text
100644 <oid-ours> 2    docs/old-guide.md
~~~

In the reverse case, the entry appears only at stage 3. Check `git status` and `git ls-files -u` to see which side still has content.

### 5.4. Rename and directory/file conflicts

Rename conflicts or file-vs-directory conflicts can cause paths in the index to differ from the name you expect. Not every conflict appears as three lines under a single path.

When encountering this case:

~~~bash
git status
git ls-files -u
~~~

Read all listed paths, compare the history of both branches, and decide on the final layout. Do not just run `git show :1:old-path` if Git renamed the path on one side.

## 6. Workflow for inspecting and resolving conflicts

### Step 1 — Identify the in-progress operation

~~~bash
git status
git branch --show-current
~~~

Git's status messages indicate whether a merge, rebase, cherry-pick, or revert is in progress. The same index stages can appear across multiple integration operations; you need to know which operation is active to run the right continue command.

### Step 2 — List unmerged paths

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

The first command lists unmerged paths according to diff state. The second shows the index entries and their respective stages.

### Step 3 — Read each version

For each file with all three stages:

~~~bash
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

Compare base, ours, and theirs to understand what each branch changed. When a stage is missing, use the available versions and commit history to determine the intended result.

### Step 4 — Edit the final content in the working tree

Open the file and resolve the markers:

~~~text
<<<<<<< HEAD
timeout=45
=======
timeout=60
>>>>>>> feature/tune-timeout
~~~

For example, after deciding on the proper value:

~~~properties
timeout=60
~~~

Remove all conflict markers and verify surrounding context. Do not mechanically pick one side if changes from both sides need to be preserved.

### Step 5 — Record the result at stage 0

If keeping the file with resolved content:

~~~bash
git add -- config/app.properties
~~~

If deciding to delete the file:

~~~bash
git rm -- docs/old-guide.md
~~~

`git add` records the working tree content as a normal stage-0 entry and clears the conflict entries for that path. `git rm` records the deletion decision by removing the path from the index.

### Step 6 — Confirm no conflict stages remain

~~~bash
git ls-files -u
git ls-files --stage -- config/app.properties
git status
~~~

Once a path is resolved, `git ls-files -u` no longer lists it. For an existing file, `git ls-files --stage` normally displays a single entry at stage 0. For a path resolved by deletion, it no longer has any entry in the index.

### Step 7 — Inspect the prepared commit snapshot

~~~bash
git diff --cached
git diff
git status
~~~

Verify both staged and remaining unstaged changes. Run relevant tests to confirm the merge result is functionally correct.

### Step 8 — Complete the integration operation

If merging:

~~~bash
git merge --continue
~~~

If rebasing:

~~~bash
git rebase --continue
~~~

If cherry-picking:

~~~bash
git cherry-pick --continue
~~~

Each operation has its own continuation command. Use the command matching the state Git reports rather than substituting `git commit` blindly.

## 7. Choosing ours or theirs with Git commands

### 7.1. Checking out one side into the working tree

If after inspection you decide to take the entire `ours` version:

~~~bash
git restore --ours -- config/app.properties
git add -- config/app.properties
~~~

If choosing `theirs`:

~~~bash
git restore --theirs -- config/app.properties
git add -- config/app.properties
~~~

`git restore --ours` pulls content from stage 2; `git restore --theirs` pulls content from stage 3. Afterward you must re-stage to replace the unmerged entries with a stage-0 entry.

These commands only apply when the corresponding stage exists. In a delete/modify conflict, the side you want may have no content to restore; when choosing deletion, use `git rm`.

### 7.2. Be careful with ours/theirs meaning during rebase

In a normal merge:

- `Ours` is usually the current branch receiving the merge.
- `Theirs` is usually the branch being merged in.

During a rebase, Git replays your commits onto a new base. In that context, `ours` is usually the base branch you are rebasing onto, while `theirs` is the commit being replayed. This can be the reverse of how people casually describe "my branch" and "their branch."

Before using `--ours` or `--theirs` during a rebase, check the operation state, the commit being replayed, and the contents of each stage. Never choose based solely on branch names or assuming `ours` is always your work.

### 7.3. Picking one side is not always the right solution

If both branches contain necessary changes, taking all of `ours` or all of `theirs` discards logic from the other side. In such cases, reading each version and editing the final result manually is usually appropriate.

Even after picking one side, always run:

~~~bash
git diff
git add -- config/app.properties
git diff --cached
~~~

to confirm the content placed in the index matches what you intended.

## 8. How does the index turn into a tree and commit?

### 8.1. From the index to a tree object

Once the index has no unmerged entries, Git can create a tree object representing the proposed snapshot:

~~~bash
git write-tree
~~~

This command writes tree objects based on valid entries in the index and prints the OID of the new root tree. It is a useful plumbing command for understanding the relationship between the index and trees.

If the index still has unresolved stage 1, 2, or 3 entries, Git cannot build a standard tree from that state and `git write-tree` fails with an error.

### 8.2. Tree objects and commit objects

A tree object records entry names, modes, object types, and OIDs of files or subdirectories. A commit object references a tree along with parent, author, committer, and message metadata.

Conceptual flow:

~~~text
Working tree
    |
    | git add
    v
Index (stage 0 entries)
    |
    | git write-tree
    v
Tree object
    |
    | git commit
    v
Commit object
~~~

When committing, Git creates a tree from the index and then creates a commit referencing that tree. Therefore, unstaged content in the working tree does not automatically appear in the commit.

### 8.3. Why can't you commit while unmerged entries remain?

A commit must reference a consistent directory tree. Stages 1, 2, and 3 are intermediate versions awaiting user resolution, not three files to place together in the final tree.

If unmerged paths remain, Git refuses to commit and requires resolving them first. Verify with:

~~~bash
git ls-files -u
git status
~~~

Only once all conflicts are resolved and the index is in a valid state can Git create a normal commit snapshot.

## 9. Conflict states and status codes in git status

During a conflict, `git status` may display codes such as:

| Code | Common situation |
| --- | --- |
| DD | Both sides deleted the path |
| AU | Added by us, unresolved |
| UD | Modified by us, deleted by them |
| UA | Added by them, unresolved |
| DU | Deleted by us, modified by them |
| AA | Both sides added |
| UU | Both sides modified |

The exact code depends on the conflict type and how Git formats status. Use `git ls-files -u` to inspect the actual stages rather than relying solely on the two-letter codes.

You can view the short format with:

~~~bash
git status --short
~~~

Unmerged paths are marked with unmerged status codes. Once the resolved result is staged, the status transitions to staged, or disappears from the list if the file was deleted.

## 10. Practical scenarios

### 10.1. Both sides edit a configuration file

Both branches edit `config/app.properties`. During merge, inspect:

~~~bash
git ls-files -u -- config/app.properties
git show :1:config/app.properties
git show :2:config/app.properties
git show :3:config/app.properties
~~~

Choose the final value, edit the working tree, stage, and verify:

~~~bash
git add -- config/app.properties
git ls-files --stage -- config/app.properties
git diff --cached -- config/app.properties
~~~

### 10.2. Both branches add the same file

In an add/add conflict, stage 1 may not exist:

~~~bash
git ls-files -u -- config/new-feature.yml
~~~

Inspect stages 2 and 3, combine the appropriate contents, and record the result:

~~~bash
git show :2:config/new-feature.yml
git show :3:config/new-feature.yml
git add -- config/new-feature.yml
~~~

### 10.3. One branch deletes while the other modifies

Check which stages exist:

~~~bash
git ls-files -u -- docs/old-guide.md
~~~

If deciding to keep the modified version, ensure the working tree has the desired content and stage it with `git add`. If deciding to delete:

~~~bash
git rm -- docs/old-guide.md
~~~

Then verify no unmerged entries remain.

### 10.4. Aborting a merge instead of resolving

If you do not want to continue the in-progress merge:

~~~bash
git merge --abort
~~~

This asks Git to return to the state prior to starting the merge to the extent Git can restore it. Pre-existing local changes present before the merge can complicate restoration; commit or stash your work before starting an integration.

After aborting:

~~~bash
git status
git ls-files -u
~~~

If no merge conflicts remain, the unmerged list will be empty.

## 11. Common mistakes

- **Confusing stage 0 with unstaged:** stage 0 is the normal entry in the index, meaning content that is already staged; stage numbers are not staged/unstaged flags.
- **Assuming every path always has one entry:** during a conflict, the same path can have entries at stages 1, 2, and 3.
- **Assuming stage 1 always exists:** add/add conflicts or cases without an applicable merge base can lack stage 1.
- **Thinking conflict markers are the index contents:** markers live in the working tree; the index holds separate versions by stage.
- **Running `git add -A` without reviewing:** this can stage unrelated changes. Stage only the resolved paths.
- **Picking `ours`/`theirs` without reading the contents:** this can silently drop required logic from the other side.
- **Applying merge's `ours`/`theirs` intuition to rebase:** during rebase, the perspective is usually reversed relative to "my branch."
- **Editing `.git/index` manually:** this can corrupt repository state. Use Git commands to update the index.
- **Attempting to commit while unmerged entries remain:** Git requires a valid tree, so all conflicts must be resolved first.
- **Looking only at `git status` without checking stages:** `status` tells you conflicts exist, while `git ls-files -u` shows the specific versions.

## 12. Quick reference table

| Goal | Command |
| --- | --- |
| View index file path | `git rev-parse --git-path index` |
| View all index entries and stages | `git ls-files --stage` |
| View unmerged entries | `git ls-files -u` |
| View entries by directory | `git ls-files --stage -- src/` |
| View base version | `git show :1:path/to/file` |
| View ours version | `git show :2:path/to/file` |
| View theirs version | `git show :3:path/to/file` |
| View combined conflict diff | `git diff --cc` |
| Restore ours into working tree | `git restore --ours -- path/to/file` |
| Restore theirs into working tree | `git restore --theirs -- path/to/file` |
| Stage resolved result | `git add -- path/to/file` |
| Mark deletion as resolved | `git rm -- path/to/file` |
| Verify index after resolution | `git ls-files --stage -- path/to/file` |
| Build tree from index | `git write-tree` |
| View current commit tree | `git ls-tree -r HEAD` |
| Abort in-progress merge | `git merge --abort` |

## 13. Summary

The index is the snapshot Git prepares for the next commit. In a normal state, each tracked path has an entry at stage 0. During a conflict, Git retains the base, ours, and theirs versions at stages 1, 2, and 3 so the user can compare them and decide on the final content.

Use `git ls-files --stage` and `git ls-files -u` to inspect index structure; use `git show :1:path`, `:2:path`, and `:3:path` to read each version. After editing the result, `git add` or `git rm` moves the path to a resolved state. Once no unmerged entries remain, Git can build a tree object from the index and proceed with the commit or finish the merge/rebase.

Understanding the relationship among the working tree, index, trees, and commits explains why Git retains multiple stages during conflicts and how to turn them into a consistent snapshot without losing important changes.


# Inspecting the Index with git ls-files and Merge Stages

Git does not only track the files visible in the working tree. Git also maintains an index that records the content versions and metadata of paths that will go into the next commit. When you need to know exactly what the index currently contains, the **git ls-files** command is an essential tool. This command can list tracked paths, display the object ID and stage of each entry, find modified or deleted files, and especially help inspect entries in a conflicted state during a merge or rebase.

During a conflicted merge operation, a single path can have multiple entries in the index instead of one normal entry. These entries are numbered stages 1, 2, and 3 to hold the base version along with the two sides being merged. Understanding how to read these stages helps you determine which versions Git is holding, choose the right resolution, and confirm the conflict has truly been handled.

After this lesson, you will be able to:

- List tracked files and current entries in the index using git ls-files.
- Read mode, object ID, and stage via --stage.
- Find unmerged paths using --unmerged.
- Distinguish stage 0, stage 1, stage 2, and stage 3.
- Use options to find modified, deleted, untracked, and ignored files.
- Combine git status, git diff, and git ls-files to investigate conflicts.
- Resolve conflicts, stage the result, and verify the index has returned to normal state.

## 1. What Does the Index Store?

The index is the intermediate area between the working tree and commits. When you run git add, Git writes selected content into the index. When you run git commit, Git creates a snapshot from the index at that moment.

~~~text
Working tree                 Index                       Commit
file being edited   --add--> staged version   --commit--> snapshot
        ^                          |
        |                          |
        +------ restore -----------+
~~~

A normal entry in the index contains information such as:

- File path relative to the repository root.
- File mode, such as regular file or symbolic link.
- Object ID of the content stored in the object database.
- Stage number.
- Stat metadata and internal flags.

The index is not simply a list of filenames. It stores the staged content version. Therefore, the same file can differ across HEAD, the index, and the working tree.

Example:

~~~bash
git add src/Search.java
git status --short
git ls-files --stage -- src/Search.java
~~~

git status shows which area the file is modified in; git ls-files --stage shows which object a specific index entry points to and which stage it is at.

## 2. Listing Tracked Files

Run the basic command:

~~~bash
git ls-files
~~~

By default, Git lists the paths present in the index—meaning files tracked by Git in the current standard snapshot of the index. The command does not list every file in the working tree and does not automatically list untracked files.

To view full paths from the root instead of paths shortened relative to the current directory:

~~~bash
git ls-files --full-name
~~~

To filter results by a pathspec:

~~~bash
git ls-files -- src/
git ls-files -- '*.java'
~~~

`--` separates options from pathspecs so filenames starting with a hyphen are not misinterpreted as options. When writing scripts, quote pathspecs according to your shell's syntax.

To make the command report an error when a pathspec matches no file in the index:

~~~bash
git ls-files --error-unmatch src/DoesNotExist.java
~~~

This is useful in scripts that need to distinguish a file absent from the index from a valid empty result.

## 3. Viewing Object ID, File Mode, and Stage with --stage

Use:

~~~bash
git ls-files --stage
~~~

Or the short form:

~~~bash
git ls-files -s
~~~

Output has the structure:

~~~text
<mode> <object-id> <stage><TAB><path>
~~~

Example:

~~~text
100644 7a1b... 0    README.md
100644 91c2... 0    src/Search.java
100755 a83d... 0    scripts/build.sh
~~~

Column meanings:

| Component | Meaning |
| --- | --- |
| mode | File type and permissions recorded by Git, e.g., 100644 is a non-executable regular file, 100755 is an executable regular file. |
| object-id | OID of the blob or object that the entry points to. |
| stage | Stage number of the entry in the index. |
| path | File path in the repository. |

In a normal index, entries have stage 0. When a path is conflicted, Git can hold multiple entries at stages 1, 2, and 3 for the same path.

The OID here represents staged content or a version participating in conflict resolution. It does not necessarily equal the OID of the current file in the working tree.

## 4. What Do Stages 0, 1, 2, and 3 Mean?

The index uses stage numbers to represent merge state:

| Stage | Meaning | Role |
| --- | --- | --- |
| 0 | Normal entry, no remaining conflict for that path. | Content currently staged. |
| 1 | Base version (merge base). | Common ancestor before the two sides diverged. |
| 2 | Current side version, usually called ours in a merge. | Content from HEAD/current side. |
| 3 | Incoming side version, usually called theirs in a merge. | Content from the incoming side. |

When a conflict occurs, Git keeps the necessary versions in the index so you can compare and decide how to combine them. For an unmerged path, stage 0 normally does not exist yet; instead there are one or more entries at stages 1, 2, 3.

Not every conflict type has all three stages:

- For modify/modify conflicts, stages 1, 2, and 3 are normally present.
- For add/add conflicts, both sides added a new file so only stages 2 and 3 may exist, with no base stage 1.
- For modify/delete conflicts, one side lacks the file so only base and the entry from the remaining side exist.
- For rename or rename/delete conflicts, relationships between paths can be more complex; inspect all unmerged paths.

Stage numbers are metadata in the index, not three separate files created by Git in the working tree.

## 5. Finding Unmerged Paths

When a merge or rebase hits a conflict, use:

~~~bash
git ls-files --unmerged
~~~

Or the short form:

~~~bash
git ls-files -u
~~~

This option displays unmerged entries and includes stage information. Example:

~~~text
100644 111aaa... 1    src/Search.java
100644 222bbb... 2    src/Search.java
100644 333ccc... 3    src/Search.java
~~~

The output shows src/Search.java has three versions in the index:

- Stage 1: common content before both sides edited it.
- Stage 2: current side content.
- Stage 3: incoming side content.

To see both normal entries and conflicted entries:

~~~bash
git ls-files --stage
~~~

To inspect just one file:

~~~bash
git ls-files --unmerged -- src/Search.java
~~~

If output has no lines, the index no longer has unmerged entries listed by this command. However, still check git status and the merge/rebase state to confirm the entire operation is complete.

## 6. Viewing the Content of Each Stage

Once you have the OIDs from git ls-files --unmerged, you can read the content of each version using git show or git cat-file.

For a conflicted file:

~~~bash
# View base content
git show :1:src/Search.java

# View ours content
git show :2:src/Search.java

# View theirs content
git show :3:src/Search.java
~~~

The syntax :<stage>:<path> references an entry in the index. If the corresponding stage does not exist, the command will fail. This commonly happens in add/add or modify/delete conflicts.

You can also use the OID retrieved from git ls-files -u:

~~~bash
git cat-file -p 111aaa...
~~~

git show :2:path is convenient when you already know the stage and path; git cat-file -p is convenient when you already have the OID. Both let you view object content without overwriting the working tree.

### Note on ours and theirs During Rebase

In a regular merge, stage 2 is the current side and stage 3 is the side being merged in. During a rebase, Git is replaying your commits onto a new base, so the labels “ours” and “theirs” can feel reversed from intuition: stage 2 is usually the branch being rebased onto, while stage 3 is the commit being replayed. Inspect stage contents and history targets rather than relying solely on the labels.

## 7. Useful File-Filtering Options

git ls-files can filter the index and working tree by various state categories:

| Option | Meaning |
| --- | --- |
| --cached | Lists files in the index; this is the default behavior. |
| --stage | Displays mode, OID, and stage of each entry. |
| --unmerged | Lists only unmerged entries; implies showing stage info. |
| --modified | Lists tracked files whose working-tree content differs from the index. |
| --deleted | Lists tracked files deleted from the working tree. |
| --others | Lists files not in the index, i.e., untracked. |
| --ignored | Includes ignored files; must be combined with --cached or --others. |
| --exclude-standard | Uses standard ignore rules such as .gitignore, .git/info/exclude, and global excludes. |

Example:

~~~bash
# Tracked files in index
git ls-files --cached

# Tracked files modified in working tree
git ls-files --modified

# Tracked files deleted from working tree
git ls-files --deleted

# Untracked files, excluding ignored files
git ls-files --others --exclude-standard

# Untracked files ignored per standard rules
git ls-files --others --ignored --exclude-standard
~~~

These options help investigate specific file states. They do not replace git status, which summarizes branch, index, working tree, and upstream states in a more readable view.

## 8. Distinguishing ls-files from status and diff

These three commands answer different questions:

| Command | Primary Question |
| --- | --- |
| git status | What changes exist in the repository and what state is the branch in? |
| git diff / git diff --cached | What are the content changes across the working tree, index, and HEAD? |
| git ls-files | Which paths and entries are in the index, and what stages are they at? |

Example during a conflict:

~~~bash
git status --short
git diff
git diff --cached
git ls-files --unmerged
git ls-files --stage
~~~

git status helps identify conflicted paths. git diff may show conflicted content or differences depending on state. git ls-files --unmerged reveals the exact stage entries remaining in the index.

When you need to know which version of a file is staged, git ls-files --stage provides the OID and stage. When you need to read changed content in a human-friendly way, git diff is usually better suited.

## 9. How Are Merge Conflicts Stored in the Index?

Suppose two branches edit src/Search.java in a region that cannot be automatically merged. During the merge, Git cannot produce a single stage 0 content for that file. Instead, the index retains the versions:

~~~text
stage 1  common ancestor
stage 2  current branch
stage 3  branch being merged
~~~

The working tree normally contains the file with conflict markers like:

~~~text
<<<<<<< HEAD
return normalize(query);
=======
return sanitize(query);
>>>>>>> feature/sanitize
~~~

Markers are how Git represents text conflicts in the working tree. The index still retains separate stage entries so each side can be retrieved. For binary conflicts or certain rename/delete conflicts, the file may not contain text markers like the example.

To view conflicted paths:

~~~bash
git ls-files -u
~~~

To view each side's content:

~~~bash
git show :1:src/Search.java
git show :2:src/Search.java
git show :3:src/Search.java
~~~

After deciding on the final content, edit the working tree and stage the result. Git replaces the unmerged entries with a stage 0 entry.

## 10. Resolving Conflicts by Editing Content

Common workflow:

~~~bash
# 1. Identify conflicted files
git status
git ls-files --unmerged

# 2. Open the file and combine content appropriately
#    Remove conflict markers after resolving

# 3. Stage the resolved result
git add src/Search.java

# 4. Confirm the file has no remaining unmerged entries
git ls-files --unmerged
git ls-files --stage -- src/Search.java

# 5. Review content about to be committed
git diff --cached
~~~

After git add, the resolved file normally appears at stage 0:

~~~text
100644 444ddd... 0    src/Search.java
~~~

If git ls-files --unmerged no longer lists that path, the path's stages 1/2/3 have been cleared from the index. This is a key sign that Git has recorded the resolution.

If you decide to keep the file deletion, use:

~~~bash
git rm -- src/Search.java
~~~

This stages the deletion and removes the corresponding conflict entries from the index. Use it only when the final decision is that the file no longer exists in the merged result.

## 11. Picking One Side with ours or theirs

If you want to use the entire content from one side for a conflicted file, you can check out the corresponding version:

~~~bash
# Pick current side content
git checkout --ours -- src/Search.java

# Or pick incoming side content
git checkout --theirs -- src/Search.java
~~~

These commands update the working tree from stage 2 or stage 3. They do not finish resolving the conflict in the index yet. After choosing, stage the result:

~~~bash
git add src/Search.java
git ls-files --unmerged
~~~

In modern Git, you can use git restore to pull one side from the index into the working tree:

~~~bash
git restore --ours --worktree -- src/Search.java
git add src/Search.java
~~~

Picking ours or theirs is only appropriate when you understand that side's content and accept discarding the other side's changes for the path being handled. Especially during rebase, double-check what both sides mean because the perspective may be inverted from typical expectations.

## 12. Tracking Conflict State in Merge and Rebase

After resolving all conflicted paths, Git still needs to finish the in-progress operation.

For merge:

~~~bash
git status
git ls-files --unmerged
git diff --cached
git commit
~~~

If the merge was started with git merge, once all conflicts are staged, create the merge commit with git commit or the appropriate continue command for your workflow.

For rebase:

~~~bash
git status
git ls-files --unmerged
git diff --cached
git rebase --continue
~~~

If you need to cancel an in-progress rebase:

~~~bash
git rebase --abort
~~~

If you need to cancel an in-progress merge:

~~~bash
git merge --abort
~~~

Do not run --continue while unmerged paths remain. Use git ls-files -u to confirm the index has no conflict entries before continuing.

## 13. Add/Add, Modify/Delete, and Rename Conflicts

Not every conflict looks like modify/modify:

### Add/Add

Both sides create the same new path with different contents. Because no file existed in the merge base, the index typically has stages 2 and 3 without stage 1. Use:

~~~bash
git ls-files --unmerged
git show :2:docs/guide.md
git show :3:docs/guide.md
~~~

Combine both versions in the working tree, then run git add.

### Modify/Delete

One side modifies the file while the other side deletes it. The index may hold the base and the modified version from one side, while the deleting side has no corresponding blob. Decide whether to keep the modified content or keep the deletion:

~~~bash
# To keep the modified file
git add path/to/file

# To keep the deletion decision
git rm -- path/to/file
~~~

### Rename Conflicts

When both sides rename a file or rename while editing content, Git may report conflicts on one or more paths. Do not look at just one line of output; check everything:

~~~bash
git status --short
git ls-files --unmerged
git ls-files --stage
~~~

After picking the final target name and content, stage the exact path to keep. Check both the old and new paths to avoid accidentally keeping two copies or losing the file.

## 14. Resolve-Undo Entries

Git can retain information about prior conflict entries in the index after you have resolved conflicts. Use:

~~~bash
git ls-files --resolve-undo
~~~

Resolve-undo information can help recreate a previous conflict state using supporting commands such as:

~~~bash
git checkout -m -- path/to/file
~~~

This is an advanced capability and not every path has a resolve-undo entry. If the command returns nothing, Git may no longer hold that information for the path being inspected.

Do not confuse resolve-undo with unmerged stages 1/2/3. --unmerged shows conflicts that still exist; --resolve-undo shows saved information about conflicts already resolved.

## 15. Using -z When Handling Special Filenames

Filenames in a repository can contain spaces, tabs, or newline characters. If a script parses output line by line, filenames can break the data structure.

Use:

~~~bash
git ls-files -z
git ls-files --unmerged -z
git ls-files --stage -z
~~~

The -z option separates records with NUL bytes and does not quote special characters the way human-oriented output does. Scripts should parse records by NUL rather than splitting by newline or space.

For example, in a shell you can pipe output to a NUL-aware tool:

~~~bash
git ls-files -z | xargs -0 -r printf '%s\n'
~~~

xargs -0 behavior is common on GNU and several Unix environments; on Windows or other environments, pick a tool with appropriate NUL support.

## 16. Complete Diagnostic Workflow During a Conflict

When a merge or rebase stops due to a conflict, follow these steps:

~~~bash
# 1. View overall status
git status --short --branch

# 2. List unmerged paths and stages
git ls-files --unmerged

# 3. View all index entries for relevant paths
git ls-files --stage

# 4. Read each version if needed
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file

# 5. After editing and staging
git add path/to/file

# 6. Confirm no unmerged entries remain
git ls-files --unmerged

# 7. View snapshot about to be recorded
git diff --cached
~~~

If step 6 still returns output, unresolved conflicted paths remain. Continue handling each path, including deleting with git rm where chosen.

Once the unmerged list is empty, check git status to see if any other unstaged or untracked changes remain. An index free of conflicts does not mean the entire working tree is clean.

## 17. Common Errors

### git ls-files Does Not Show New Files

By default the command lists paths in the index, not untracked files. Use git ls-files --others --exclude-standard or git status to see untracked files.

### git ls-files --stage Only Shows Stage 0

The repository currently has no unmerged entries for the listed paths. If investigating conflicts, use git ls-files --unmerged to filter specifically for stage 1/2/3 entries.

### Seeing Conflict Markers Yet git ls-files -u Returns Nothing

The file may contain manually typed markers or was already staged as normal content. Git relies on index stages to recognize conflicts, not scanning file contents for the string <<<<<<<. Check git status and staged content.

### Ran git add Yet Conflicts Remain

You may have staged only some files while other paths remain unmerged. Run git ls-files -u to find all remaining paths.

### Chose --ours During Rebase and Got the Wrong Content

During a rebase, ours/theirs can feel backwards because HEAD is on the target branch onto which commits are replayed. Inspect git show :2:path and git show :3:path before choosing.

### Assuming Stage 1 Always Exists

Add/add conflicts have no base version for that path, so stage 1 may not appear. Modify/delete conflicts can also lack a stage for the deleted side.

### Parsing Output with Special Filenames by Whitespace

Filenames can contain spaces or newlines. Use -z and a NUL-safe parser when writing scripts.

## 18. Key Takeaways

- git ls-files lists paths in the index by default, not every file in the working tree.
- git ls-files --stage shows the mode, OID, and stage of each entry.
- Stage 0 is a normal entry; stage 1 is base; stage 2 is current/ours; stage 3 is incoming/theirs in a regular merge.
- git ls-files --unmerged or -u lists remaining conflict entries in the index.
- Not every conflict has all of stages 1, 2, and 3.
- Use git show :1:path, :2:path, :3:path to view each stage's content when that entry exists.
- git add stages the resolved result; git rm stages a file deletion decision.
- After resolving, confirm git ls-files -u returns nothing before continuing a merge or rebase.
- git ls-files --others, --modified, --deleted, and --ignored help filter different groups of files.
- Use -z when scripts need to safely handle filenames with special characters.

git status gives you the high-level picture, while git ls-files lets you look directly at index entries. Once you understand stages 1/2/3 and how to inspect them, you can pinpoint the exact data Git holds during a conflict, resolve each path, and confirm the index is ready for committing or the next step of a rebase.

# Checking Integrity with git fsck and Finding Unreferenced Objects

Git stores commits, trees, blobs, and tags as objects in the object database. Branches, tags, and other references help Git locate those objects. When history is rewritten, a branch is deleted, or a recovery operation is left incomplete, objects can still remain in the repository while no longer referenced from familiar starting points.

The **git fsck** command verifies the validity and connectivity of the object database. It helps detect missing objects, broken links, invalid data, and locates unreachable objects such as commits, trees, or blobs. It is a key diagnostic tool when investigating an abnormal repository or finding commits after a reset, amend, rebase, or branch deletion.

In the **Debugging and Recovery** chapter of the **SOURCE_CONTROL_GIT** module, this lesson covers how to read fsck output, distinguish dangling objects from unreachable objects, trace remaining contents, and create rescue references when you find commits that need to be preserved. The goal is methodical inspection and preserving objects before they are cleaned out of the repository.

After this lesson, you will be able to:

- Explain the Git object database and basic object types.
- Run fsck to verify integrity and connectivity.
- Distinguish dangling objects, unreachable objects, and missing or corrupt objects.
- Understand the role of refs, the index, and reflogs when Git determines object reachability.
- Inspect located commits, trees, and blobs using cat-file, show, and ls-tree.
- Create a rescue branch or save needed content without losing track of original objects.
- Recognize when objects need to be retrieved from a remote or backup.

## 1. Git Stores Data in the Object Database

Git does not store history merely as filenames or a list of diffs. Content is stored as objects identified by hashes derived from their content and metadata.

Main object types:

| Object Type | What Does It Contain? | Usage Example |
| --- | --- | --- |
| **blob** | Content of a single file, without storing filename or path | Source code content, documents, or binaries |
| **tree** | List of entries containing name, mode, and referenced object | Directory and file structure at a snapshot |
| **commit** | Reference to root tree, parent commits, and commit metadata | A point in development history |
| **tag** | Metadata of an annotated tag and the object the tag points to | Version milestone with a message or signature |

For example, a commit typically points to a tree; the tree points to blobs and subtrees; the commit also points to parent commits:

~~~text
        commit C
        /      \
   parent B   tree T
                |
          +-----+------+
          |            |
       blob A       tree src
                         |
                       blob B
~~~

Branches and tags are named references to objects. They help Git determine starting points for traversing history and content. Reflog records certain local reference updates. The index can also hold references to blobs currently staged.

When a branch is deleted or moved, older objects may no longer be referenced by that branch. That does not mean the objects vanish immediately. They can remain in the object database and be recovered until Git cleans up unneeded objects.

## 2. What Does git fsck Check?

The name fsck originates from the concept of filesystem consistency checking. In Git, this command checks the object database and links between objects.

Run a basic check:

~~~bash
git fsck
~~~

You can request a full check:

~~~bash
git fsck --full
~~~

fsck verifies whether objects are readable and structurally valid, as well as the links needed to build history and snapshots. Depending on repository state, results may include:

- Valid and connected objects.
- Dangling objects not directly used by another object as determined by Git.
- Unreachable objects not reachable from the roots considered in the check.
- Missing objects, links pointing to nonexistent objects, or object data failing hash verification.

By default, fsck usually prints only dangling objects rather than listing every unreachable object. It may print nothing when no reportable issues are found. Having no output does not mean every file in the working tree is valid; fsck focuses on the object database, not replacing tests, checks on untracked files outside Git, or application logic validation.

You can enable stricter checking:

~~~bash
git fsck --full --strict
~~~

The strict option tells Git to check additional object format constraints. It is useful when inspecting a repository showing signs of corruption or when performing a deeper object quality audit.

## 3. Understanding Reachable, Unreachable, and Dangling

These three terms describe how objects relate to starting points and other objects.

### Reachable

An object is reachable if Git can traverse to it from the roots considered during the check, such as refs, the index, and reflogs under default settings. For example, a branch tip commit and every object needed to reconstruct that commit's snapshot are reachable.

~~~text
main -> commit C -> tree T -> blob A
                    |
                    +------> blob B
~~~

From branch main, Git can traverse commits, trees, and blobs to reconstruct the snapshot.

### Unreachable

An object is unreachable if Git cannot reach it from the roots currently being evaluated. For example, after moving a branch off an old commit, that commit and part of the objects used exclusively by the old history may become unreachable.

~~~text
main -> commit D -> new tree

commit C -> old tree -> old blob
   ^
   no longer pointed to by any branch or considered root
~~~

Unreachable does not mean the object has been deleted. It can still exist in the object database and be recovered if garbage collection has not cleaned it up yet.

### Dangling

Dangling describes an object that exists but is not directly used by any other object as determined by fsck. In common recovery scenarios, this is often the tip commit of history dropped from a branch. This concept refers to whether an object is directly referenced by another object; do not equate the --dangling option with --unreachable because the two options report according to different criteria.

~~~text
main -> A---B---D

        C---E
            ^
       dangling commit E
~~~

In the example, commit E is no longer referenced by any branch. If E is the tip of an unreachable commit chain, it may be reported as a dangling commit. Parent commits, trees, and blobs within that chain may also be unreachable, though not every individual object will necessarily be reported as dangling.

Therefore:

- **Unreachable**: an object that cannot be reached from the considered roots.
- **Dangling**: an object not directly used by another object; in history recovery scenarios, it is often the tip of an unreachable chain.
- A dangling object can be a commit, tag, tree, or blob; not every dangling object is a commit that can be checked out.

## 4. Roots That Affect fsck Results

fsck results depend on which starting points Git uses to compute reachability.

Normally, Git considers references such as branches, tags, and certain other refs; the index and reflog can also keep objects reachable. This explains why a commit after a reset sometimes does not appear in the unreachable list yet: the reflog still records HEAD's previous position.

To also check objects held solely by the reflog, you can instruct fsck to ignore reflogs when computing reachability:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

The **--no-reflogs** option tells fsck not to treat commits referenced only by reflogs as reachable. This command is useful when searching for objects after a reset or rebase. It may list more objects than a default run.

If you only want to view unreachable objects:

~~~bash
git fsck --unreachable
~~~

If you want to view dangling objects without listing all unreachable objects, you can run:

~~~bash
git fsck --dangling
~~~

This is also the category of info fsck typically reports by default. You can hide dangling notices when focusing on other errors:

~~~bash
git fsck --no-dangling
~~~

Do not compare the results of two fsck runs with different root options without noting the difference. An object may be reachable in a default check yet become unreachable when adding --no-reflogs.

## 5. Running fsck and Reading Output

### Initial Checks

~~~bash
git status -sb
git fsck --full
~~~

The status command reports the branch and changes in the working tree; fsck inspects the object database. Both commands serve different purposes and should be read together during investigation.

Some common output formats:

~~~text
dangling commit 0123456789abcdef...
dangling blob abcdef0123456789...
unreachable commit 1234567890abcdef...
missing blob fedcba9876543210...
broken link from tree 0123... to blob 4567...
~~~

General meaning:

| Message | Interpretation |
| --- | --- |
| dangling commit | There is an unreferenced commit not directly used by another object as determined by fsck. It may be the tip of old history. |
| dangling blob | There is file content not directly used by another object as determined by fsck. Blobs do not store filenames, so further investigation is needed. |
| unreachable commit | A commit not reachable from the evaluated roots. It may be a commit in the middle of an unreachable history chain. |
| missing blob | A required object is referenced but not found in the object database. This is a sign that integrity needs investigation. |
| broken link | An object contains a link to a target object that does not exist or is invalid. |

Exact wording and line ordering can vary by Git version and repository state. Save the object hashes for further inspection.

### Distinguishing Warnings from Data Corruption

Dangling or unreachable objects normally appear after valid operations such as commit amends, rebases, resets, branch deletions, or recreating commits. They do not automatically prove repository corruption.

Missing objects, broken links, hash mismatches, or object read errors are much more concerning. They can indicate an incomplete object database or corrupted data. Save the fsck log, identify which objects are affected, and check another copy before attempting repairs.

## 6. Finding Unreferenced Objects

When the goal is to locate old commits or files after a history-rewriting operation, use:

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

This command can return many object types. Focus on the unreachable commit lines first, then inspect related objects.

If you only need to find dangling commits:

~~~bash
git fsck --full --no-reflogs --dangling
~~~

Example output:

~~~text
dangling commit 9a1b2c3d4e5f...
dangling commit 7f8e9d0c1b2a...
~~~

These hashes are illustrative examples. Do not choose a commit solely by its hash or creation date; inspect its contents and parents to determine which history needs recovery.

## 7. Inspecting a Dangling Commit

Commits are the most convenient object type to recover because they hold references to a tree and parent commits.

View commit info:

~~~bash
git show --no-patch --format=fuller <commit-hash>
git show --stat <commit-hash>
~~~

Read the message, author, creation date, parents, and list of changed files. To view history starting from that commit:

~~~bash
git log --oneline --graph --decorate <commit-hash>
~~~

If the commit has multiple parents, it may be a merge commit. Inspect both the graph and contents to avoid restoring the wrong history branch by mistake.

View the commit diff:

~~~bash
git show --format=fuller --no-ext-diff <commit-hash>
~~~

Once you confirm this is the commit to keep, create a rescue branch:

~~~bash
git branch rescue/recovered-work <commit-hash>
~~~

The new branch creates a ref pointing to the commit, making the commit and its ancestor history reachable again. Afterward, you can check out the rescue branch, cherry-pick needed commits, or compare against the current branch.

If you want to move the current branch to that commit, verify carefully before resetting. Creating a rescue branch first preserves the found milestone even if your next decision turns out wrong.

## 8. Inspecting Dangling Trees and Blobs

Not every found object is a commit. When only a tree or blob remains, you can still inspect its contents, though you must determine filenames and paths differently.

### Check Object Type and Size

~~~bash
git cat-file -t <object-hash>
git cat-file -s <object-hash>
~~~

The first command returns the object type such as commit, tree, blob, or tag. The second prints the size of the object's content.

### View a Tree

~~~bash
git ls-tree <tree-hash>
git ls-tree -r <tree-hash>
~~~

A tree stores directory structure and child objects. The -r option recursively lists entries inside. If the tree belongs to an old snapshot, the output helps locate the corresponding paths and blobs.

### View a Blob

~~~bash
git cat-file -p <blob-hash>
~~~

A blob stores only file content, not the filename or path. If the content is text, you can read it to recognize it. If it is binary, avoid printing it directly to the terminal; check its type and size, then write the content to a separate recovery file to open with an appropriate tool.

Example saving a blob to a file:

~~~bash
git cat-file blob <blob-hash> > recovered-file
~~~

The file recovered-file is a copy of the blob's content; it is not automatically tracked by Git and does not prove the original path. Determine the proper name, location, and version before bringing the file into the working tree.

### Finding Blobs Related to a Commit

If you find a dangling commit, prioritize inspecting that commit's tree rather than hunting for loose blobs:

~~~bash
git show --format=raw --no-patch <commit-hash>
git ls-tree -r <commit-hash>
~~~

The show command reveals the commit's tree hash. The ls-tree command lists the files and blobs used by that snapshot. This lets you identify each blob's path from the tree, information that the blob itself does not store.

## 9. Using --lost-found to Record Discovered Objects

The **--lost-found** option tells fsck to write dangling objects into the lost-found directory inside the Git directory:

~~~bash
git fsck --full --no-reflogs --lost-found
~~~

Git typically writes dangling commits into the **lost-found/commit** directory and other object types into **lost-found/other** inside the Git directory. These records make it easier for developers to open and inspect contents; they do not automatically create branches or restore history into the working branch.

The Git directory path can differ across regular repositories, worktrees, and environments using a custom git-dir. You can ask Git for the actual path:

~~~bash
git rev-parse --git-path lost-found
~~~

After running lost-found, inspect the written objects and create rescue refs for commits you need to keep. Do not treat the presence of files in lost-found as a completed recovery; you still need to identify objects, verify contents, and create stable references.

## 10. Investigation Workflow After Reset, Rebase, or Branch Deletion

Suppose you accidentally reset a feature branch to an older commit, then discover a commit containing important changes has left the branch tip.

### Step 1: Stop Object Cleanup Operations

Do not run git prune, git gc with an immediate prune window, or object-deletion commands while investigating. These operations can remove the unreachable objects you are trying to recover.

### Step 2: Check Reflog First

~~~bash
git reflog --date=local
~~~

Reflog is usually the fastest place to find the commit from before a reset or rebase. If you locate the hash, inspect the commit and create a rescue branch.

### Step 3: Use fsck If Reflog Is Insufficient

~~~bash
git fsck --full --no-reflogs --unreachable
~~~

Look for commits matching the timestamp and content of your work. Because the command can return many objects, inspect each candidate commit with show, log, and tree commands.

### Step 4: Verify the Commit and History

~~~bash
git show --stat <candidate-commit>
git log --oneline --graph <candidate-commit>
~~~

Cross-check the message, modified files, parents, and contents. If it is the desired commit, save the hash.

### Step 5: Create a Rescue Branch

~~~bash
git branch rescue/feature-before-reset <candidate-commit>
~~~

This branch establishes a stable reference to the commit. Verify:

~~~bash
git show --no-patch --oneline rescue/feature-before-reset
git log --oneline --decorate -8 rescue/feature-before-reset
~~~

### Step 6: Choose How to Bring Changes Back

Depending on your goal, you can:

- Check out the rescue branch to continue working on the old history.
- Cherry-pick one or more needed commits onto the current branch.
- Compare trees and files and restore selectively.
- Keep the rescue branch for team review before integrating.

Do not immediately reset the main branch as soon as you find the commit. First anchor the object with a rescue branch, then choose the appropriate integration strategy.

## 11. When fsck Reports Missing or Corrupt Objects

Dangling objects are usually a normal byproduct of rewriting history. By contrast, a missing object or broken link message indicates that a referenced object cannot be read or does not exist where Git expects it.

Investigation workflow:

1. Save the entire fsck output, including hashes and object types.
2. Identify whether the missing object is a commit, tree, blob, or tag.
3. Check whether another repository, remote, or backup contains that object.
4. If the remote has the object and related ref, fetch from the trusted source.
5. Re-run fsck to confirm the issue is resolved.

Example checking an object:

~~~bash
git cat-file -t <object-hash>
git cat-file -p <object-hash>
~~~

If an object cannot be read, running fsck again cannot recreate the lost content on its own. You must retrieve the object from a repository copy with valid data or from a backup. Do not manually fabricate object files by editing the .git/objects directory directly.

If a remote has a branch or tag containing the needed commit, you can fetch the corresponding reference:

~~~bash
git fetch origin <branch-name>
~~~

After fetching, re-check the object and history. A remote that does not contain the lost commit cannot supply that object; in that case, search another clone or backup.

## 12. Preserving Found Objects

When you locate an important commit or object, create a stable ref as soon as possible. A rescue branch is the clearest approach for commits:

~~~bash
git branch rescue/found-commit <commit-hash>
~~~

If you need to preserve a tag object or non-commit object, consider creating an appropriate ref after verifying the object type and repository conventions. Do not create a branch pointing to a blob or tree because branches in standard workflows must point to commits.

Save the fsck output and note the hash, object type, source where it was found, and actions taken. Once a stable ref exists, the object becomes reachable via that ref and is far less at risk of being cleaned up as an unreferenced object.

Do not run the following commands while trying to recover data:

~~~bash
git prune
git gc --prune=now
~~~

Prune and garbage collection can delete unreachable objects eligible for cleanup. If you are not yet sure which objects must be kept, finish investigating and create rescue refs before running scheduled cleanup tasks.

## 13. Common Misconceptions

### Does having dangling objects mean the repository is corrupted?

No. Dangling objects commonly appear after an amend, rebase, reset, or branch deletion. They are simply objects no longer referenced by the current structure, not necessarily data corruption.

### Does fsck automatically recover commits?

No. fsck checks and reports objects. The lost-found option can write copies of dangling objects into a helper directory, but to keep a commit in working history, you must create a branch or appropriate ref.

### Why doesn't a commit after reset show up in default fsck?

The commit may still be reachable through the reflog. Use --no-reflogs when searching for objects retained only by the reflog.

### Are unreachable and dangling the same thing?

No. Unreachable is the broader category. Dangling is a specific case typically not directly used by another object. A commit in the middle of an unreachable history chain may not be reported as dangling because a child commit still points to it.

### Does a blob tell you the original filename?

No. A blob contains only content. You need to find a tree or commit referencing that blob to learn the associated path and snapshot.

### Can you run git gc to clean up dangling objects right away?

You should not while investigating or when recovery may still be needed. Preserve objects with rescue refs and verify data before allowing Git to clean up unreferenced objects.

## 14. Self-Check

After a mistaken rebase, you see the output:

~~~text
dangling commit 111111...
unreachable commit 222222...
dangling blob 333333...
~~~

Answer the following:

1. Why is a dangling commit not necessarily an error?
2. Why can commit 222222 be unreachable yet not dangling?
3. Which command displays the contents and parents of commit 111111?
4. Which command creates a rescue branch pointing to a commit to preserve?
5. If only blob 333333 is found, can the original filename be inferred from the blob alone?
6. Why should git prune or git gc --prune=now be avoided before recovery?
7. If fsck reports a missing blob, does creating a rescue branch automatically fix that error?

**Hint:** A dangling commit can be the tip of old history after a rebase. Commit 222222 may be used by another unreachable commit and therefore is not dangling. Use git show and git log to inspect commits; use git branch rescue/recovered 111111 to create a rescue ref after confirming the right object. Blobs do not store filenames; a tree or commit is needed to find the path. Prune/gc can delete unreachable objects; a rescue branch only preserves existing objects and cannot regenerate missing blobs.

## Conclusion

git fsck checks the object database and uncovers dangling, unreachable objects or broken links. When searching for old commits, inspect hashes with git show, trace history, and create a rescue branch to keep objects reachable. For trees and blobs, check the object type and follow snapshot relationships to determine contents and paths. Dangling objects do not equal repository corruption; missing objects or broken links require investigation and restoration from a reliable remote or backup. Only run prune or garbage collection after all objects needing recovery have been safely preserved.

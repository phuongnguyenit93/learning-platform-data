# Creating an Intentional Conflict and Verifying Resolution Results

A merge conflict occurs when Git cannot automatically combine changes from different branches. To understand how to handle it, create a controlled scenario: two branches edit the same line in the same file with different content, then merge them so Git reports a conflict.

This lab walks through the entire workflow: preparing a clean repository, creating two branches with independent edits, triggering a conflict, reading the status and index stages, crafting the final content, staging the result, finalizing the merge, and verifying the commit. Perform this in a separate lab directory so experimental steps do not affect any active project.

## 1. Practice Goals and Prerequisites

After this lab, you will be able to:

- Create a reproducible text conflict by having two branches edit the same line.
- Identify the current branch and the branch being merged in.
- Read conflict messages, unmerged status, and the stage entries stored in the index.
- Choose or combine content from both sides to produce the required result.
- Mark each resolved file by staging the outcome.
- Complete the merge and verify file contents, two-parent history, and working tree state.

The commands in this lab use Bash, Git Bash, or WSL. If using PowerShell, you can create or edit files with your editor, keeping the illustrative contents intact, and run the corresponding Git commands. Before starting, Git must be installed and your commit identity configured.

## 2. Creating the Lab Repository and Baseline Commit

Create a dedicated directory and initialize a repository with main as the primary branch:

```bash
mkdir git-conflict-lab
cd git-conflict-lab
git init --initial-branch=main

# Configure a local identity for the practice repository
git config user.name "Git Learner"
git config user.email "learner@example.test"
```

Create settings.txt with two lines:

```bash
printf 'message=Hello\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Add initial settings"
```

Check status and the baseline commit:

```bash
git status --short
git log --oneline --decorate -1
cat settings.txt
```

Expected output:

```text
message=Hello
format=plain
```

The repository must be clean before creating a merge conflict. Check with git status; if uncommitted changes remain, handle them first. A clean working tree makes aborting a merge or analyzing conflicts much more predictable.

## 3. Creating a Feature Branch and Editing the First Line

Create the feature/greeting branch from the baseline commit:

```bash
git switch -c feature/greeting
```

On this branch, change the message line to its own content:

```bash
printf 'message=Hello from feature\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Customize greeting in feature branch"
```

Inspect the commit and contents:

```bash
git log --oneline --decorate -2
cat settings.txt
```

The feature/greeting branch now has one new commit ahead of main. The baseline commit remains the common ancestor of both branches.

## 4. Returning to main and Editing the Same Line Differently

Switch back to main:

```bash
git switch main
```

On main, replace the exact same message line with content different from the feature branch:

```bash
printf 'message=Hello from main\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Customize greeting in main branch"
```

At this point, both branches started from the same commit but modified the same line in different ways. Verify the history:

```bash
git log --oneline --graph --decorate --all
git status --short
```

Conceptual pre-merge graph:

```text
          feature commit
         /
base ----
         \
          main commit
```

The two new commits are independent branch tips. Because both edited the first line in settings.txt, Git cannot automatically decide which content should be kept.

## 5. Triggering the Conflict With Merge

While on main, merge feature/greeting:

```bash
git merge feature/greeting
```

Git reports a conflict and stops before creating a merge commit. The command exits with a non-zero status; in this lab, that is the expected outcome. Inspect the status:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cc -- settings.txt
```

You will typically see settings.txt listed under unmerged paths with status both modified. Git has identified the conflicted file but does not yet have a final result to write to the index.

The working tree file contains conflict markers:

```text
<<<<<<< HEAD
message=Hello from main
=======
message=Hello from feature
>>>>>>> feature/greeting
format=plain
```

Meaning of the merge conflict delimiters:

- The line starting with `<<<<<<< HEAD` opens the content from the current branch, which is main in this example.
- The `=======` line separates the two sides.
- The line starting with `>>>>>>> feature/greeting` closes the content from the branch being merged in.
- Content outside the markers, such as format=plain, does not conflict and is preserved.

The labels shown on markers depend on the operation and configuration. During a merge, HEAD typically represents the current branch; the other side is the branch being merged in.

## 6. Reading the Three File Versions in the Index

While a conflict remains unresolved, the index can store three versions for the same path:

| Stage | Common name | Contents |
|---|---|---|
| 1 | Base | Version at the common ancestor, before the two branches diverged |
| 2 | Ours | Version from the current branch, here main |
| 3 | Theirs | Version from the branch being merged in, here feature/greeting |

View the unmerged entries:

```bash
git ls-files -u -- settings.txt
```

Illustrative output:

```text
100644 <base-blob-oid>   1 settings.txt
100644 <ours-blob-oid>   2 settings.txt
100644 <theirs-blob-oid> 3 settings.txt
```

The OIDs shown are placeholders for actual values generated by the repository. Read each version individually:

```bash
# Version at the common ancestor
git show :1:settings.txt

# Version from the current branch (main)
git show :2:settings.txt

# Version from the branch being merged in (feature/greeting)
git show :3:settings.txt
```

These commands let you inspect each side's contents even while the working tree contains conflict markers. Not every conflict type has all three stages. For example, add/add or modify/delete conflicts have different stage entries; use git ls-files -u to inspect the exact index state for each path.

## 7. Choosing How to Resolve the Conflict

There is no rule that you must always pick ours or theirs. Base your decision on functional requirements and an understanding of both sides.

For this lab, suppose the final requirement is a message reflecting contributions from both branches. Open settings.txt, remove all markers, and replace the message line with the combined content:

```text
message=Hello from main and feature
format=plain
```

Inspect the file in your editor or via:

```bash
cat settings.txt
```

If you decide to keep one side verbatim, you can also check out the corresponding version:

```bash
# Take content from the current branch during a merge
git restore --ours -- settings.txt

# Or take content from the branch being merged in
git restore --theirs -- settings.txt
```

After running restore, you still must verify the content and stage the file. Ours/theirs only selects one version for that path; it does not resolve other conflicts or confirm the result satisfies business requirements.

When resolving multiple files, handle each file in context. Conflicts may be:

- **Content conflict:** both sides edited the same text region; usually displays conflict markers.
- **Add/add:** both branches added the same new path with different contents.
- **Modify/delete:** one side modified a file while the other deleted it.
- **Rename-related:** both sides renamed or modified files in ways Git cannot combine automatically.
- **Binary conflict:** binary files cannot be merged by inserting text markers.

Conflicts do not always show text markers. Use git status and git ls-files -u to classify them instead of only searching for `<<<<<<<` lines in files.

## 8. Staging the Result to Mark It Resolved

Once the final content is correct, add the file to the index:

```bash
git add settings.txt
```

Staging the result signifies that you have chosen the final content for that path. Check unmerged status:

```bash
git ls-files -u
git status
```

If settings.txt is resolved and no other conflicted paths remain, git ls-files -u prints nothing. In the index, the staged path becomes stage 0, replacing stages 1, 2, and 3.

Inspect the staged content:

```bash
git ls-files --stage -- settings.txt
git diff --cached -- settings.txt
git diff --cached --check
```

The expected output of git ls-files --stage is a single stage 0 entry for settings.txt. git diff --cached shows the staged changes; git diff --cached --check checks for whitespace errors in the staged changes.

Before finishing the merge, inspect the overall status and ensure no unmerged paths remain:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cached --stat
```

If unmerged files remain, continue resolving and staging each one. Do not run git add . blindly without checking the list; it may stage unrelated changes outside the merge.

## 9. Finalizing the Merge Commit

Once all conflicts are resolved and staged, complete the merge:

```bash
git merge --continue
```

Git may open your editor to confirm the merge commit message. Keep or adjust the message as appropriate, save, and close the editor. You can also run git commit to finalize a merge after staging everything; when a merge state is active, git commit creates a merge commit.

After finishing, verify:

```bash
git status
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
```

The merge commit normally has two parent lines: the first parent is the tip of the current branch before the merge (main), and the second parent is the tip of the merged-in branch (feature/greeting). This serves as historical proof that both sides were recorded.

## 10. Verifying Results After the Merge

Do not stop just because Git reports the merge succeeded. Verify the contents, repository state, and history structure.

### Checking the Final Contents

```bash
cat settings.txt
git show HEAD:settings.txt
```

Both outputs must reflect the chosen content:

```text
message=Hello from main and feature
format=plain
```

### Confirming No Conflicts Remain

```bash
git status --short
git ls-files -u
git diff --check
git diff --cached --check
```

After the merge commit, the working tree and index should be clean. git ls-files -u should return no entries. Both diff --check commands should report no whitespace errors in the checked changes.

### Checking the Two Parents of the Merge Commit

```bash
git rev-list --parents -n 1 HEAD
git show --no-patch --format=fuller HEAD
git log --graph --oneline --decorate --all
```

git rev-list --parents prints the OID of the merge commit followed by its parent OIDs. For a normal two-branch merge, that line contains three OIDs: the merge commit and its two parents. git log --graph helps visualize the two branches converging at the merge commit.

### Comparing the Merge Content Against Each Parent

```bash
# Changes introduced by the merge commit compared to its first parent
git diff HEAD^1 HEAD -- settings.txt

# Changes introduced by the merge commit compared to its second parent
git diff HEAD^2 HEAD -- settings.txt
```

These two comparisons help verify the final result against each side. If your project has related tests or build checks, run them after merging to confirm the resolution remains functionally valid.

## 11. Aborting an Unfinished Merge

If you realize you started a merge by mistake or do not want to continue, you can cancel the active merge:

```bash
git merge --abort
```

This command asks Git to return to the pre-merge state, to the extent Git can restore it. Behavior is most predictable when the working tree was clean before the merge. If there were uncommitted changes before merging, Git may not be able to restore everything cleanly; always commit or stash your work before starting a merge.

After aborting, check:

```bash
git status
git log --oneline --decorate -3
cat settings.txt
```

Do not use git reset --hard merely to exit a conflict unless you are certain which changes to keep. In this lab, you can try aborting before resolving, then re-running the merge to practice the entire workflow.

## 12. Distinguishing Conflicts From Other Merge Errors

Not every stopped merge is a content conflict:

| Situation | Symptom | Resolution approach |
|---|---|---|
| Content conflict | Git reports CONFLICT and lists unmerged paths | Resolve contents, stage, and continue the merge |
| Local changes would be overwritten | Working tree has uncommitted edits that would be overwritten | Commit or stash changes before merging |
| Already up to date | Current branch already contains the other branch's commits | No merge needed |
| Fast-forward | Current branch can advance directly to the other branch's tip | Git updates the ref without a merge commit |
| Refusing to merge unrelated histories | The two histories share no common ancestor | Verify the right repository and intent before considering allowing it |

When Git reports a conflict, read the message and status before running the next command. Never assume every merge failure is solved by editing conflict markers.

## 13. Common Mistakes When Resolving Conflicts

| Mistake | Consequence | How to avoid |
|---|---|---|
| Deleting markers but forgetting needed content | File may lose logic from one or both sides | Read base, ours, and theirs before editing |
| Blindly picking ours/theirs for all files without review | May discard valid changes from the other side | Decide per file based on functional requirements |
| Forgetting to stage a resolved file | Git still treats the path as unmerged and blocks completion | Run git add on each verified result |
| Checking only the working tree | Index contents may differ from disk contents | Check both git diff and git diff --cached |
| Trying to commit while unmerged paths remain | Git refuses to create the merge commit | Check git ls-files -u before continuing |
| Running git add . when unrelated changes exist | May stage files outside the merge scope | Stage the exact resolved paths |
| Skipping tests after merging | Text conflicts may be gone while logic is broken | Run tests and verify behavior after merging |
| Using reset --hard to escape a conflict | Can lose local changes | Use git merge --abort when canceling a merge and understand pre-merge state |

## 14. Verification Checklist Before Finishing

Before considering a conflict resolved, verify:

- [ ] Identified the current branch and the branch being merged in.
- [ ] Read contents from both sides and the base when needed.
- [ ] Removed all leftover conflict markers in text files.
- [ ] Handled every unmerged path, including add/add, modify/delete, or binary conflicts.
- [ ] Staged the final result for each path.
- [ ] git ls-files -u lists no remaining entries.
- [ ] git diff --cached reflects the exact content ready to commit.
- [ ] The merge commit has all expected parents.
- [ ] Working tree is clean and relevant tests pass.

## 15. Self-Check Questions

1. **Why do two branches editing the same line differently produce a conflict?**
   - Because Git cannot automatically determine which content is the right choice when combining two edits in the same region.
2. **In a merge from feature into main, which side does stage 2 typically represent?**
   - Ours, meaning the current branch main.
3. **What does stage 1 in the index hold?**
   - The base version at the common ancestor of both branches.
4. **Which commands list currently unmerged paths?**
   - git ls-files -u or git diff --name-only --diff-filter=U.
5. **Why must you run git add after editing a conflict?**
   - To replace the conflict stages with the resolved result at stage 0 and mark the path complete.
6. **How do you confirm a merge commit has two parents?**
   - Use git rev-list --parents -n 1 HEAD or git show --no-patch --pretty=raw HEAD.
7. **Which command cancels an in-progress merge before committing?**
   - git merge --abort.

## Conclusion

Creating an intentional conflict by having two branches edit the same line lets you clearly observe how Git stores base, ours, and theirs in the index. To resolve it, inspect the status, understand both sides' contents, craft the required final result, stage each file, and confirm no unmerged paths remain. Then finalize the merge and verify the file contents, the two parents of the merge commit, a clean working tree, and passing tests. This workflow turns conflict resolution into verifiable steps rather than guessing one side by intuition.

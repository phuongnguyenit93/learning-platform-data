# Meaning of ours and theirs in merge, rebase, and cherry-pick

When Git cannot automatically combine two changes, it marks the conflicted files and keeps the necessary versions in the index so the user can decide the final outcome. The two labels **ours** and **theirs** help distinguish the sides of the running operation. They are very useful when reading conflict markers, inspecting individual versions, or quickly selecting one side with Git commands.

The key point to remember is that **ours is always stage 2 and theirs is always stage 3 in a conflict's index**, while which branch each corresponds to depends on the operation. With merge and cherry-pick, the interpretation is usually intuitive: ours is the current side, and theirs is the incoming change. With rebase, this interpretation easily causes confusion because Git is replaying individual commits onto a new base.

## 1. Ours and Theirs in a Conflict

Suppose the same line in a file is edited differently by two sides. Git may leave a marked block like this:

```text
<<<<<<< HEAD
const timeout = 30;
=======
const timeout = 60;
>>>>>>> feature/timeout
```

This block has three parts:

- The section after `<<<<<<<` is the content from the **ours** side.
- The section between `=======` and `>>>>>>>` is the content from the **theirs** side.
- The delimiters are added by Git for you to edit and produce a merged result.

The name displayed after `<<<<<<<` or `>>>>>>>` is the label Git uses for the current operation. Do not just look at the branch name in the marker and conclude which branch originated the work; check `git status` to see whether Git is performing a merge, rebase, or cherry-pick.

In the index, Git stores up to three unmerged versions of a path:

| Stage | Meaning | Role |
|---|---|---|
| 1 | Base | Common base version Git uses for comparison |
| 2 | Ours | Version of the current side in the operation |
| 3 | Theirs | Version of the incoming side brought into the operation |

While the file still has conflicts, Git has not yet created stage 0 (the resolved version) for that file. After you edit it and run `git add`, the current content is recorded as stage 0; the conflict stages are removed.

Not every conflict has all three stages. For example, an add/add conflict may lack stage 1 because the file did not exist in the base. A modify/delete conflict may lack the stage for the side that deleted the file. Therefore, if a `git show :1:...`, `:2:...`, or `:3:...` command reports that the object was not found, check the conflict type instead of assuming the repository is corrupted.

## 2. Comparing the Interpretation Across Operations

| Operation | Ours (stage 2) | Theirs (stage 3) | Continue command |
|---|---|---|---|
| Merge | The branch checked out before merging | The branch being merged in | `git merge --continue` |
| Rebase | The new base: upstream plus already-replayed commits | The branch commit currently being replayed at this step | `git rebase --continue` |
| Cherry-pick | The current branch receiving the commit | The commit being cherry-picked | `git cherry-pick --continue` |

### Merge: ours is the current branch

For example, you are on branch `main` and run:

```bash
git switch main
git merge feature
```

If a conflict occurs:

- **Ours** is the content from `main`, i.e., the currently checked-out branch.
- **Theirs** is the content from `feature`, i.e., the branch being merged in.

In this case, `<<<<<<< HEAD` usually represents the `main` side; the end usually carries the label of the `feature` branch. This is the most common mental model when merging.

### Rebase: ours is the new base, theirs is the commit being replayed

Rebase is the easiest case to misunderstand. Consider the command:

```bash
git switch feature
git rebase main
```

Git takes the commits unique to `feature`, moves the branch's starting point to `main`, and replays each commit one by one onto the new base. When a commit being replayed causes a conflict:

- **Ours** is `HEAD` at that moment: the new base starting from `main`, plus any commits already replayed successfully before this one.
- **Theirs** is the `feature` commit that Git is attempting to replay at the current step.

Therefore, during a rebase, `git restore --ours -- path/to/file` keeps the version from the new base; `git restore --theirs -- path/to/file` keeps the version from the `feature` commit being applied. This can be counterintuitive to the assumption that "ours is the code on the branch I'm working on".

If the rebase involves multiple commits, Git may stop at several different conflicts. Theirs at each stop is the commit being applied at that step, not necessarily the entire final state of the `feature` branch. Use `git show REBASE_HEAD` or `git rebase --show-current-patch` to inspect the current commit/patch.

### Cherry-pick: ours is the branch receiving the commit

For example, you are on `release` and want to bring in a specific commit from another branch:

```bash
git switch release
git cherry-pick abc123
```

If a conflict occurs:

- **Ours** is the existing content on `release`.
- **Theirs** is the change from commit `abc123` being applied.

You can use `git show CHERRY_PICK_HEAD` to inspect the commit being cherry-picked. If cherry-picking a range of commits, Git processes them one by one; the current conflict is tied to the commit currently being applied.

## 3. Inspecting Both Sides Before Deciding

Do not choose ours or theirs based on the name alone. First, identify the operation and see where Git is conflicting:

```bash
git status
git diff --name-only --diff-filter=U
```

For a specific file, inspect the combined and per-stage diffs:

```bash
git diff --cc -- path/to/file
git diff --base -- path/to/file
git diff --ours -- path/to/file
git diff --theirs -- path/to/file
```

You can also read the versions Git stores in the index directly:

```bash
git ls-files -u -- path/to/file

git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
```

The commands `:1:`, `:2:`, and `:3:` read base, ours, and theirs, respectively. They are especially helpful when conflict markers are hard to read, the file has been partially edited, or you need to compare both sides intact. For filenames containing spaces, enclose the path in quotes appropriate for your shell.

To identify the source of changes per operation, you can also inspect:

```bash
# During merge
git show MERGE_HEAD

# During rebase
git show REBASE_HEAD
git rebase --show-current-patch

# During cherry-pick
git show CHERRY_PICK_HEAD
```

Only run the command corresponding to the active operation; that pseudo-ref may not exist during other operations.

## 4. Choosing One Side or Manually Combining Content

If you are certain you want to use the entire file from one side, you can ask Git to restore that version into the working tree:

```bash
# Take the entire file from ours (stage 2)
git restore --ours -- path/to/file

# Or take the entire file from theirs (stage 3)
git restore --theirs -- path/to/file
```

Common older equivalents are `git checkout --ours -- path/to/file` and `git checkout --theirs -- path/to/file`. `git restore` expresses the file restoration intent more clearly.

These commands replace the entire file content with one side's version. They do not select individual lines or hunks. If both sides have changes worth keeping, open the file, remove the conflict markers, and edit it into the desired result. You can use a visual diff/merge tool:

```bash
git mergetool
```

For file-level conflicts, such as one side deleting a file while the other edits it, decide clearly on the final outcome to keep. If the outcome is to delete the file, use `git rm -- path/to/file`; if keeping the file, create the final content and run `git add -- path/to/file`.

After resolving, mark the file as handled:

```bash
git add -- path/to/file
```

`git add` puts the current working tree content into the index and tells Git that the file's conflict is resolved. If you choose to delete the file, use `git rm`. Verify before continuing:

```bash
git status
git diff --cached
git diff --check
```

## 5. Safe Conflict Resolution Workflow

A workflow applicable to all three operations:

1. **Identify the paused operation.** Run `git status`; look for messages such as "merging", "rebasing", or "cherry-picking".
2. **List conflicted files.** Use `git diff --name-only --diff-filter=U` to know the scope to handle.
3. **Determine what ours/theirs means in that operation.** Use the table in Section 2; for rebase specifically, remember theirs is the commit being replayed.
4. **Read base and both sides.** Use conflict markers, `git diff`, or the stages in the index. Understand the purpose of each change before combining.
5. **Produce the final content.** You may pick one side for the whole file or combine the necessary parts. Remove all remaining markers.
6. **Mark the file as resolved.** Use `git add` or `git rm`, then review the staged diff.
7. **Continue the right operation.** Use the corresponding continue command and handle subsequent conflicts if Git stops again.
8. **Verify the result.** Run appropriate tests/builds, check `git status`, and inspect the final commit.

Commonly used continue and abort commands:

```bash
# Merge
git merge --continue
git merge --abort

# Rebase
git rebase --continue
git rebase --abort

# Cherry-pick
git cherry-pick --continue
git cherry-pick --abort
```

`--abort` cancels the operation in progress and returns the repository to the state before the operation started, insofar as Git can restore it. If the working tree already had uncommitted changes beforehand, be cautious and preserve them before starting a merge/rebase/cherry-pick; do not use `git reset --hard` as a way to resolve conflicts because it can destroy changes you need to keep.

## 6. Distinguishing `-X ours` from Picking the Entire File

Besides `git restore --ours` and `--theirs`, Git also has strategy options such as `-X ours` or `-X theirs`. For merge, for example:

```bash
git merge -X ours feature
```

`-X ours` tells the merge strategy to prefer the ours side **in conflicting hunks**. Non-conflicting changes from the other side can still be included in the result. Similarly, `-X theirs` prefers the theirs side in conflicting hunks.

This differs from:

```bash
git merge -s ours feature
```

`-s ours` selects the `ours` merge strategy, producing a merge result using the entire tree of the current branch and ignoring the content of the branch being merged in. This is a strategy-level decision that can discard a large amount of changes. Do not use it merely to quickly get past a few conflicts. When using these options with rebase, be sure to double-check the meaning of ours/theirs in the rebase context described above.

## 7. Common Misconceptions

- **Assuming ours is always the branch you just checked out.** This holds for standard merge and cherry-pick, but in a rebase, ours is the new base onto which commits are being replayed.
- **Assuming theirs is always the target branch or source branch.** Theirs is the version from the other side of the current operation; in a rebase, it is the commit being applied.
- **Picking one entire side without checking the rest.** `git restore --ours` and `--theirs` replace the whole file. Valid changes on the other side can be lost from the result.
- **Thinking removing markers resolves the conflict.** Git only treats a file as handled after the content is staged into the index with `git add` or the deletion is recorded with `git rm`.
- **Confusing `-X ours` with `-s ours`.** One option sets a preference when resolving conflicting hunks; the other selects a strategy that keeps the entire tree of ours.
- **Continuing the wrong operation.** Merge, rebase, and cherry-pick each have their own continue command. Read `git status` before running a command.

## Conclusion

Remember the two layers of meaning: in the index, ours is stage 2 and theirs is stage 3; which branch or commit stage 2 and stage 3 represent must be determined from the active operation. Merge and cherry-pick usually follow the intuitive "current side" and "incoming side" meanings. Rebase flips that intuition: ours is the new base, theirs is the commit being replayed. When uncertain, check `git status`, read the file's stages, and inspect the commit being applied before choosing a side.

# Recreating Conflict Markers to Re-Evaluate a Resolution

During a merge or rebase, Git may stop because both sides modified the same content region. You usually open the file, read the `<<<<<<<`, `=======`, and `>>>>>>>` markers, and manually combine the changes. Sometimes after editing, you realize you chose too hastily or want to inspect both sides again before confirming the result.

If the file is still in a conflicted state in the index, Git can recreate the conflict markers in the working tree. The primary command is `git restore --merge`. This operation lets you return to a state where you can inspect each conflicted section while still retaining the versions of each side that Git stores in the index.

## 1. Where Does Git Store Conflict State?

When a file is in conflict, Git keeps multiple versions of that file in the **index** (staging area). Instead of a single resolved entry at stage 0, a conflicted file can have the following entries:

| Stage | Content | Common meaning |
|---|---|---|
| 1 | Base | Common ancestor version before the two sides diverged |
| 2 | Ours | Version from the current side of the integration operation |
| 3 | Theirs | Version from the other side being integrated |

Not every conflict type has all three stages. For example, when two branches independently create a new file at the same path, stage 1 may not exist because that file did not exist in the common ancestor.

Check the repository status and unmerged entries:

```bash
git status
git ls-files -u -- src/config.yml
```

The output of `git ls-files -u` includes the mode, blob hash, stage number, and path. Illustrative example:

```text
100644 <blob-base> 1 src/config.yml
100644 <blob-ours> 2 src/config.yml
100644 <blob-theirs> 3 src/config.yml
```

You can read each version stored in the index without overwriting the file in the working tree:

```bash
git show :1:src/config.yml
git show :2:src/config.yml
git show :3:src/config.yml
```

The commands `git show :1:path`, `:2:path`, and `:3:path` read the contents of stages 1, 2, and 3, respectively. If a stage does not exist, Git reports that the corresponding object was not found.

## 2. Recreating Conflict Markers in the Working Tree

Suppose `src/config.yml` previously had conflict markers, and you edited it into a single unified version but have not yet run `git add`. The index still contains the unmerged stages. Run:

```bash
git restore --merge --worktree -- src/config.yml
```

Git reconstructs the conflicted content for the file in the working tree from the versions currently in the index. The conflict markers reappear in the file so you can read them and decide how to combine the changes. The index still retains the unmerged state, so `git status` continues to report the file as conflicted.

The command above replaces the current content of the file in the working tree. If you have edits you want to preserve, back up the file to a safe location before running it.

### Choosing the Conflict Marker Style

Git supports different display styles. You can request a style directly in the command:

```bash
git restore --merge --worktree --conflict=merge -- src/config.yml
git restore --merge --worktree --conflict=diff3 -- src/config.yml
git restore --merge --worktree --conflict=zdiff3 -- src/config.yml
```

- `merge`: displays the two conflicting sides; this is the traditional style.
- `diff3`: adds the base content so you can see the original version before both sides edited it.
- `zdiff3`: also displays the base, while compacting certain common lines around the conflict region so differences are easier to read.

You can also set the default style for the repository:

```bash
git config merge.conflictStyle diff3
```

The configuration value can be `merge`, `diff3`, or `zdiff3` depending on your Git version. The `--conflict` option in `restore` lets you select a specific style for that restoration alone.

On older Git versions without `git restore`, you can use the equivalent `checkout` syntax:

```bash
git checkout -m -- src/config.yml
git checkout --conflict=diff3 -- src/config.yml
```

These commands also rebuild the conflict in the working tree from the unmerged index entries. When possible, prefer `git restore` because it expresses file restoration more clearly.

## 3. Re-Reading the Conflict Content

With the `merge` style, a conflict region typically looks like:

```text
<<<<<<< HEAD
timeout: 20
=======
timeout: 45
>>>>>>> feature/longer-timeout
```

- The section after `<<<<<<<` is content from the ours side.
- The section between `=======` and `>>>>>>>` is content from the theirs side.
- The `=======` line separates the two choices.
- The labels after `<<<<<<<` and `>>>>>>>` help identify the sides involved; they may be branch names, `HEAD`, or commit hashes depending on the operation.

With the `diff3` style, Git adds the base section between ours and theirs:

```text
<<<<<<< HEAD
timeout: 20
||||||| 9ac12ef
timeout: 30
=======
timeout: 45
>>>>>>> feature/longer-timeout
```

In this example, the original value was `30`, the current branch changed it to `20`, and the branch being integrated changed it to `45`. Knowing the base value helps you understand each side's intent and decide the final value based on actual requirements.

One common source of confusion is the meaning of ours and theirs during a rebase. In a standard merge, ours is the current branch and theirs is the branch being merged in. During a rebase, Git usually treats the target branch along with already-replayed commits as ours, and the commit currently being replayed as theirs. Therefore, read the labels and the operation context rather than assuming theirs is always the remote branch.

## 4. Workflow for Reviewing and Re-Resolving

You can follow this workflow whenever you doubt a conflict resolution decision:

1. **Confirm the file is still unmerged.** Run `git status` and `git ls-files -u -- <file>` to verify the index still has conflict stages.
2. **Preserve any needed edits.** If the working tree has content you want to reference, back up the file before restoring conflict markers.
3. **Recreate the conflict markers.** Run `git restore --merge --worktree --conflict=diff3 -- <file>` to view both sides and the base.
4. **Evaluate each region.** Compare both sides' intent against the base; review business requirements, configuration, and related use cases.
5. **Edit manually into a complete result.** Remove all `<<<<<<<`, `|||||||`, `=======`, `>>>>>>>` markers and keep valid content.
6. **Verify before marking resolved.** Run relevant tests, review the file, and run `git add <file>` once the result is right.

Example with a configuration file:

```bash
git status
git ls-files -u -- src/config.yml
git restore --merge --worktree --conflict=diff3 -- src/config.yml
```

After finishing edits:

```bash
git diff -- src/config.yml
git diff --check
git add src/config.yml
git status
```

`git diff --check` helps detect certain whitespace errors and leftover conflict markers. Inspect the actual content and run project tests; this command does not replace verifying logic. Once all files are resolved, continue the paused operation:

```bash
git merge --continue
```

Or if rebasing:

```bash
git rebase --continue
```

Only use the continue command matching the active operation. If unresolved files remain, Git will ask you to handle them first.

## 5. What If the File Has Already Been Staged?

This is an important limitation of recreating conflict markers. When you run:

```bash
git add src/config.yml
```

Git writes the resolved result into stage 0 and removes the conflict entries (stages 1, 2, 3) for that file. If you change your mind afterward, `git restore --merge` no longer has unmerged data in the index to reconstruct the original conflict markers.

`git restore --staged` does not recreate the conflict stages either. That command only restores index content from a specified source; it does not restore a previous merge state.

If the merge or rebase is still in progress and you need to regenerate the entire conflict, you can abort the operation and run it again:

```bash
git merge --abort
git merge <branch-name>
```

Or with rebase:

```bash
git rebase --abort
git rebase <target-branch>
```

The `--abort` commands attempt to return the repository to the state prior to the paused merge or rebase. They can discard edits made during that process; in particular, if you started a merge with many uncommitted changes already present, Git may not be able to fully restore the original state. Save any work you need to keep separately before aborting. If the merge has already been committed, inspect history and create a fixup commit or follow an appropriate revert workflow; `git restore --merge` cannot reconstruct an already-completed conflict.

## 6. Common Misconceptions

| Operation | Result | Does it recreate conflict markers? |
|---|---|---|
| `git restore --merge --worktree -- file` | Rebuilds conflict content from unmerged stages in the index | Yes, if the index still has suitable conflict data |
| `git restore --ours --worktree -- file` | Takes the exact ours version from the index | No; selects one side |
| `git restore --theirs --worktree -- file` | Takes the exact theirs version from the index | No; selects one side |
| `git show :2:path` or `git show :3:path` | Reads one side stored in the index individually | No; displays content only |
| `git add file` | Marks the current result as resolved | No; removes the file's conflict stages from the index |

Some conflicts cannot be represented by markers in a text file, such as binary file conflicts or certain rename/delete cases. In those cases, check `git status` to see the conflict type and handle each path according to its state; `git restore --merge` cannot always produce a meaningful marker block.

Do not confuse recreating conflict markers with `git rerere`. `rerere` remembers and can reapply a previously encountered conflict resolution; `git restore --merge` rebuilds conflict content from the versions still stored in the index for manual review.

## 7. Hands-On Exercise

Suppose while merging branch `feature/longer-timeout`, `src/config.yml` conflicts on the `timeout` attribute. You edited it to `timeout: 40`, but want to re-examine it because you are unsure whether that choice is right.

1. Run `git status` and `git ls-files -u -- src/config.yml`. Check whether the file still has stages 1, 2, and 3.
2. Use `git show :1:src/config.yml`, `git show :2:src/config.yml`, and `git show :3:src/config.yml` to inspect the base and both sides.
3. Run `git restore --merge --worktree --conflict=diff3 -- src/config.yml` to recreate conflict markers including the base.
4. Explain why the two branches chose different values, then edit the file to a value matching the application's requirements.
5. Inspect the file, run related tests, run `git add src/config.yml`, and confirm the state with `git status`.

You have completed the exercise when you can explain which data in the index lets Git reconstruct the conflict, the difference between `--merge` and `--ours`/`--theirs`, and why staging the result removes that file's conflict stages.

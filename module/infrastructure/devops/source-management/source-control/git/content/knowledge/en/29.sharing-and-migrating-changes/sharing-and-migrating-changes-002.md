# Creating Commit Patches with git format-patch

Git can package commits into a patch series to send to others for review or to transfer changes between repositories without pushing directly to a shared remote. The **git format-patch** command creates email-formatted (mbox-style) files containing commit metadata, the commit message, and the diff. Recipients can apply the series using **git am**, recreating the commits with their contents and author information preserved.

This approach is useful when collaborating over email, submitting patches to a maintainer, working in an environment without push access, or transferring a selected set of commits to another repository. The key is choosing the right revision range, preserving patch ordering, and verifying that the patches are generated from finalized commits.

## 1. What is git format-patch used for?

`git format-patch` turns one or more commits into standalone patches. Each commit normally produces a separate patch file containing:

- An email subject generated from the commit subject.
- Author name and author date.
- Commit message, including the subject and body description.
- A diff showing the commit's changes relative to its parent.
- Additional information such as diffstat and Git version signature, depending on options.

For example, a branch has three new commits compared to `main`:

```text
A---B---C---D---E
    ^           ^
   main        topic

Commits to send: C, D, E
```

Run:

```bash
git format-patch main..topic
```

Git generates three files corresponding to the three commits in the range. Filenames typically include a sequence number and a sanitized subject, for example:

```text
0001-Add-input-validation.patch
0002-Fix-parser-boundary.patch
0003-Document-new-option.patch
```

These files are not a copy of the entire repository. They are patch messages that can be read, reviewed, and applied by Git.

`git format-patch` only packages commits that already exist in history. It does not include uncommitted changes in the working tree or index in the patch series. If you have uncommitted changes, inspect and commit them first, or use a different diff mechanism if the goal is to send uncommitted changes.

## 2. Selecting the right revision range

The most common usage is specifying a base commit and a tip commit:

```bash
git format-patch <base>..<tip>
```

The range `<base>..<tip>` selects commits reachable from `<tip>` that are not reachable from `<base>`. In other words, Git takes the commits present in the tip's history that are not yet in the base's history.

Example:

```bash
git format-patch origin/main..HEAD
```

The command generates patches for the commits on `HEAD` that are not yet in `origin/main`. This assumes `origin/main` has been recently fetched and is the base you want to compare against.

Before generating patches, inspect the commit list:

```bash
git fetch origin
git log --oneline --decorate --reverse origin/main..HEAD
```

`--reverse` displays commits from oldest to newest. You can verify whether the base is an ancestor of the tip:

```bash
git merge-base --is-ancestor origin/main HEAD
```

If the command returns exit code 0, `origin/main` is an ancestor of `HEAD`. Otherwise, history has diverged or the base is not in `HEAD`'s history; inspect the graph and re-select the range before packaging.

Some commonly used commit selection patterns:

| Command | Scope |
|---|---|
| `git format-patch -1 HEAD` | Generate a patch for the `HEAD` commit |
| `git format-patch -3` | Generate patches for the 3 newest commits from `HEAD` |
| `git format-patch base..HEAD` | Generate patches for commits in `HEAD` not in `base` |
| `git format-patch --root HEAD` | Generate patches for history reachable from `HEAD`, including the root commit |

Be careful with revision ranges. `A..B` does not mean "every commit lying between A and B on a straight line" in all branching graphs; it is a reachability-based selection. If the branch contains merges, the commit set may include commits from side branches.

Do not confuse `A..B` with `A...B`. The three-dot form selects the symmetric difference between both sides, which is usually not the patch set you want to send from a topic branch based on a base.

## 3. In what order are patches exported?

When generating a patch series from a revision range, Git exports commits in the proper order for applying from the oldest commit to the newest commit. This matters because later commits may depend on changes from earlier commits.

Example history:

```text
A---B---C---D---E
    ^
   base

Patch order:
1. C
2. D
3. E
```

You can check the expected order before generating:

```bash
git log --oneline --reverse base..HEAD
```

After running `git format-patch`, filenames are normally numbered `0001`, `0002`, `0003` in application order. When transferring patches to a recipient, keep the files and sequence numbers intact. Do not re-sort them by subject or file modification date.

If `--stdout` is used, Git writes the patch messages sequentially into a single mbox stream. The order within the stream is also the application order.

## 4. Generating patches for a single commit or a group of commits

To export the latest commit:

```bash
git format-patch -1 HEAD
```

To export the five most recent commits:

```bash
git format-patch -5
```

To export a group of commits on a topic branch relative to a base:

```bash
git format-patch origin/main..feature/login
```

If you want to output patches into a separate directory, use `-o` or `--output-directory`:

```bash
git format-patch -o patches origin/main..feature/login
```

Git creates the patch files inside the `patches` directory. Use a new directory or a properly cleaned directory to avoid mixing old files with patches from the current run.

Check the file list after generating:

```bash
git status --short
```

If the patch directory is inside the repository and not ignored, patch files may appear as untracked files. That is normal; patches are generated artifacts and do not automatically become commits in the project.

## 5. Combining a patch series into one file with --stdout

If you want to create a single mbox file instead of multiple separate files, use `--stdout`:

```bash
git format-patch --stdout origin/main..HEAD > feature-login.mbox
```

The `feature-login.mbox` file contains the sequential patch messages. The recipient can apply the entire series with:

```bash
git am feature-login.mbox
```

This is convenient when sending a single artifact or archiving a patch series. Do not use `git apply` on an mbox file as if it were a simple unified diff; `git am` understands the email structure and commit metadata produced by `format-patch`.

If you need to inspect the file contents before sending, you can open it in a text editor or view the beginning:

```bash
head -n 40 feature-login.mbox
```

In PowerShell, you can use `Get-Content -TotalCount 40 feature-login.mbox`. An mbox file may contain multiple email headers and diff sections, so avoid manually editing metadata fields unless you understand the format.

## 6. Creating a cover letter for a patch series

When sending multiple commits, reviewers often need an introduction explaining the overall goal, scope, and patch ordering. Use `--cover-letter`:

```bash
git format-patch --cover-letter origin/main..HEAD
```

Git creates an additional cover letter file, typically numbered `0000`, alongside the patches numbered starting from `0001`.

The cover letter is where you explain:

- The problem or goal of the entire patch series.
- How the patches depend on or follow each other.
- Specific areas reviewers should pay attention to.
- Relevant test results.
- Changes compared to the previous submission if this is an updated version.

Git generates a cover letter template; you need to open the file and fill in the content before sending. Do not leave placeholder text or boilerplate descriptions if recipients expect an actual explanation.

Example creating both a cover letter and saving into a directory:

```bash
git format-patch --cover-letter -o patches origin/main..HEAD
```

Then open the `0000` file created in the `patches` directory and complete its contents. The exact filename depends on the subject. Keep the cover letter together with the patches belonging to the same series.

## 7. Setting the subject prefix and submission version numbering

By default, patch subjects usually start with `[PATCH]` or `[PATCH n/m]`. You can change the prefix:

```bash
git format-patch --subject-prefix="RFC PATCH" origin/main..HEAD
```

This helps recipients identify the type of proposal or project convention. Agree on the prefix with the maintainer or review workflow.

When resending a patch series that has been reviewed, use the reroll count:

```bash
git format-patch -v2 --cover-letter -o patches-v2 origin/main..HEAD
```

`-v2` produces subjects with version `v2`, distinguishing it from the previous series. For the next iteration, you can use `-v3`. Use a separate directory for each submission so old and new patches are not mixed.

You can adjust the starting number with `--start-number`:

```bash
git format-patch --start-number=5 -4 HEAD
```

This option changes the sequence number in patch filenames/subjects without altering commits or history order. For most standard patch series, let Git number from 1.

## 8. Preserving threading and recipient information

If the patch series is sent via email, Git can generate headers so that messages in the series appear in the same thread:

```bash
git format-patch --thread --cover-letter origin/main..HEAD
```

`--thread` adds cross-message reference headers. `--no-thread` disables this mechanism. You can specify recipient addresses in the headers using `--to` or `--cc`:

```bash
git format-patch --to=maintainer@example.com --cc=reviewer@example.com origin/main..HEAD
```

These options only generate headers in the patch files; they do not send emails automatically. You still need to use an email sending tool or review platform approved by the team. Do not include unnecessary recipient addresses in patch metadata.

If submitting through another review system, email headers may not be needed. In that case, you can generate patches normally and attach the artifacts according to that system's workflow.

## 9. Including binary files and full diffs

Standard text patches represent line-by-line changes. For binary files, the default diff may only report that the file changed without containing enough data to reconstruct the new content.

If the patch series needs to transfer binary file changes as well, use `--binary`:

```bash
git format-patch --binary -1 HEAD
```

This option generates a binary diff that can be applied by compatible Git tools. For tools requiring full OIDs in the diff, you can add `--full-index`:

```bash
git format-patch --binary --full-index origin/main..HEAD
```

Not all review systems or external patch-handling tools display binary diffs nicely. If a series contains large files or auto-generated artifacts, consider transferring them through an artifact repository or appropriate distribution mechanism instead of putting everything into email patches.

## 10. Verifying patches before sharing

Before sending, confirm that the patches were created from the right commits and contain no unintended changes.

Inspect the commit list:

```bash
git log --oneline --decorate --reverse origin/main..HEAD
```

Check working tree status:

```bash
git status --short
git diff
git diff --cached
```

The last two diff commands show unstaged and staged changes. They are not packaged by `git format-patch` if they have not been committed.

Generate patches into a separate directory:

```bash
git format-patch -o patches origin/main..HEAD
```

Inspect statistics per patch or commit contents:

```bash
git show --stat --oneline <commit>
git show <commit>
```

You can inspect a patch file with `git apply --stat` to view change statistics, though that command only checks the diff portion and does not fully verify email/commit metadata like `git am`.

If you want to test applicability in a temporary worktree or clone, use a clean working copy at the exact base and run `git am` according to project policy. Do not test applying patches on a working tree that has uncommitted work.

## 11. Applying a patch series with git am

The recipient normally starts from a branch with a base compatible with the patch series. Then they apply the patch files in order. For example, if the series has three patches:

```bash
git am patches/0001-Add-input-validation.patch
git am patches/0002-Fix-parser-boundary.patch
git am patches/0003-Document-new-option.patch
```

The filenames in the example are illustrative; use the actual names generated by `git format-patch`. If there is a cover letter, do not pass the `0000` file to `git am`; the cover letter is not a regular commit patch.

If using a single mbox file generated with `--stdout`:

```bash
git am feature-login.mbox
```

`git am` reads the email/patch metadata and creates the corresponding commits. Author name and author date from the patch are preserved; the committer is the person applying the patch according to the receiving environment's Git configuration.

After applying, verify:

```bash
git log --oneline --decorate -5
git status
```

If the patch was generated from a different base or the contents on the receiving branch have changed, applying it may conflict or fail.

## 12. Handling conflicts during git am

If a patch does not apply cleanly, Git pauses the series and leaves an in-progress `am` state. Check status:

```bash
git status
```

Resolve conflicted files as you would during a merge:

1. Open the conflicted file and combine the appropriate contents.
2. Stage the resolved file.
3. Continue the series with `git am --continue`.

Example:

```bash
git add src/parser.java
git am --continue
```

If you want to skip the current patch and proceed to the next patch:

```bash
git am --skip
```

Only skip once you have confirmed the changes in that patch are unnecessary or have already been integrated another way. If you want to cancel the entire in-progress application:

```bash
git am --abort
```

`--abort` restores the repository to the state before the `am` series started. If you need to retry with a different base, check status after aborting before starting again.

When the patch contains sufficient blob information in the diff, you can tell Git to attempt a 3-way merge:

```bash
git am --3way patches/0001-Add-input-validation.patch
```

`--3way` allows Git to attempt a merge based on the base blob when direct application fails and the necessary objects are available. It does not guarantee all conflicts will resolve automatically; if conflicts still remain, resolve them and then use `--continue`, `--skip`, or `--abort`.

## 13. Distinguishing git format-patch, git diff, and git bundle

The three tools serve different purposes:

| Tool | What does it package? | Preserves commit metadata? | Primary usage |
|---|---|---|---|
| `git format-patch` | A sequence of commits as email patches | Yes: author, date, message, and diff | Reviewing/transferring commits with `git am` |
| `git diff` | Difference between two states/paths | Does not package commit metadata | Inspecting or applying changes with `git apply` |
| `git bundle` | Objects and refs/history required by scope | Yes, because it carries real commit objects | Transferring Git history without a direct remote |

If you need to transfer individual commits and want the recipient to create corresponding commits, use `format-patch`/`git am`. If you only need a diff without commit metadata, use `git diff`/`git apply`. If you need to preserve the graph, branches, and object history (including merge structure), consider `git bundle` or exchanging via a remote.

`format-patch` is not a complete copy of a repository. By default, merge commits are not exported as regular commit patches; a patch series also does not preserve branch/merge topology. If merge history is an essential part of the requirement, use an appropriate object/ref transfer method rather than expecting a patch series to reconstruct the original graph.

## 14. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| No patch files generated | Empty range or no matching commits | Check `git log base..tip` |
| Patches contain unwanted commits | Wrong base or range selected | Inspect the graph and verify ancestor before generating |
| Patch lacks current edits | `format-patch` only packages commits | Commit changes to send or use diff for uncommitted changes |
| Patches apply out of order | Files renamed/re-sorted or multiple series mixed | Preserve sequence numbers and use separate directories |
| `git am` reports patch cannot apply | Different base, changed content, or conflict | Try `--3way`, resolve conflicts, then continue |
| Binary files not recreated | Patch lacks binary data | Regenerate with `--binary` |
| Recipient unsure of series goal | Missing overall description | Generate `--cover-letter` and fill in content |
| Merge history not reconstructed | `format-patch` does not preserve merge topology | Use `bundle` or a remote to transfer history |

## 15. Practical workflow: sending three commits to a maintainer

Suppose you are developing on branch `feature/login`, based on `origin/main`, and already have three finalized commits. You want to send a series with a cover letter.

**Step 1: Update the base and inspect the commit list.**

```bash
git fetch origin
git log --oneline --reverse origin/main..feature/login
git status
```

Ensure the working tree/index has no uncommitted changes that belong in the series.

**Step 2: Generate the patch series in a separate directory.**

```bash
git format-patch --cover-letter -o patches origin/main..feature/login
```

**Step 3: Complete the cover letter.**

Open the `0000` file generated in the `patches` directory and write the goal, patch ordering, testing instructions, and notes for reviewers.

**Step 4: Inspect the patches.**

```bash
git log --oneline --reverse origin/main..feature/login
git status --short
```

Cross-check the number and order of patches against the commit list. Read each patch's contents to ensure there are no out-of-scope changes.

**Step 5: Share the entire series.**

Send the cover letter along with all patch files via the channel your team uses. Keep filenames and sequence numbers intact; do not send a single patch that depends on an earlier patch without explaining the base and order.

**Step 6: Recipient applies and verifies.**

On a receiving branch based on a compatible base, apply each patch in order and omit the cover letter:

```bash
git am patches/0001-Add-input-validation.patch
git am patches/0002-Fix-parser-boundary.patch
git am patches/0003-Document-new-option.patch
git log --oneline --decorate -5
git status
```

The filenames here are examples. Multiple patches can be applied in a single invocation once the exact file list is selected and the cover letter is excluded. After completion, run project tests before merging or releasing.

## 16. Checklist before creating and sending patches

- [ ] Base and tip are properly identified.
- [ ] Remote-tracking refs have been fetched if using a base from a remote.
- [ ] The commit list in the range has been reviewed.
- [ ] All changes to be sent have been committed.
- [ ] Patches are generated in a separate directory or into a controlled mbox file.
- [ ] Patch ordering is preserved.
- [ ] A cover letter is included if the series needs an overall explanation.
- [ ] Binary diffs are included if binary files need to be transferred.
- [ ] Patches are inspected before sending.
- [ ] The recipient knows the required base and how to apply with `git am`.

## Conclusion

Use `git format-patch <base>..<tip>` to create one patch per commit in the range to share; use `-1`, `-n`, `-o`, or `--stdout` to adjust the count and output format. Add `--cover-letter` when you need to describe the whole series, `-v2` when resending an updated version, and `--binary` if binary file changes need to be transferred. Recipients apply them with `git am`, preserving author metadata and creating new commits in their repository. Remember that `format-patch` transfers commit contents as patches and does not carry the full object graph or merge topology like `git bundle`.

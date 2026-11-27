# Creating fixup commits and auto-arranging with `--autosquash`

During development, we sometimes realize an earlier commit is missing a validation check, has a minor bug, or needs a documentation update. We could create another commit to fix it, but if the branch has not been shared and we want a clean history, it is usually better to fold that fix into the original commit. Git supports this workflow with **fixup commits** and the `--autosquash` option of interactive rebase.

`git commit --fixup=<commit>` creates a corrective commit whose title is prefixed with `fixup!` and points to a specific target commit. When you run `git rebase -i --autosquash <base>`, Git automatically finds the target commit, moves the fixup commit right after it, and marks its action as `fixup`. Once the rebase finishes, the changes are folded into the target commit and the fixup commit no longer appears separately in history.

This is a useful way to organize history when working on a feature branch, preparing a pull request, or tidying up commits before sharing. Because rebase rewrites history, you must understand which commits will receive new IDs and align with your team before applying it to a branch someone else is already using.

## 1. What problem does a fixup commit solve?

Suppose you created the commit `Add login validation`, and later discover an input validation condition is missing. If you make a normal commit, the history might look like:

```text
A --- B --- C --- D
      ^           ^
      |           HEAD
      commit to fix
```

You create another commit `Fix login validation` at the end of the branch. The history now has a fix commit sitting far away from the original commit:

```text
A --- B --- C --- D --- F
      ^                   ^
      |                   HEAD
      commit to fix       follow-up fix commit
```

In terms of content, the change in `F` belongs to the work done in `B`. If you keep this history as is, reviewers have to read an extra small commit to understand part of earlier work. On a feature branch with many revisions, history easily becomes fragmented.

A fixup commit explicitly records the target commit at creation time. Later, autosquash moves the fixup into the right position so you can review and fold it in a single rebase:

```text
Before autosquash:
A --- B --- C --- D --- F
      ^                   ^
      target commit       fixup! B

After rebase --autosquash:
A --- B' --- C' --- D'
      ^
      B' contains both original changes and the fix from F
```

Commits after `B` are recreated during the rebase, so their commit IDs change even though their contents may stay the same. The new commit `B'` contains both `B`'s original content and the fix from `F`; commit `F` no longer exists as a separate commit.

## 2. Creating a fixup commit with `git commit --fixup`

First, find the commit that needs fixing:

```bash
git log --oneline --decorate -10
```

Example output:

```text
8c42d19 (HEAD -> feature/login) Add login error response
7b31a20 Add login validation
51d0a87 Create login endpoint
```

You want to add a validation check to commit `7b31a20`. After editing the file, stage the exact changes and create a fixup commit:

```bash
git add src/main/java/example/LoginValidator.java
git commit --fixup=7b31a20
```

Git creates a new commit with a title like:

```text
fixup! Add login validation
```

The content of the fixup commit is whatever is currently staged. Git uses the specified commit to generate a title that can be matched automatically during the autosquash step. Therefore, pass the right target commit, usually a commit hash or an unambiguous reference.

Verify the result:

```bash
git log --oneline --decorate -5
git show --stat --oneline HEAD
```

You will see the `fixup! ...` commit at the tip of history. At this point, the change is still a standalone commit; it is only folded in when you run an autosquash rebase.

### Only include the needed fix in the fixup

If your working tree has multiple changes serving different purposes, do not blindly stage everything. You can select individual files:

```bash
git add src/main/java/example/LoginValidator.java
```

Or select individual hunks within a file:

```bash
git add -p
```

Then inspect the staged contents before committing:

```bash
git diff --cached
git status --short
```

`git commit --fixup` builds a commit solely from staged content just like a normal commit. If you stage the wrong file or include unfinished work, the fixup commit will carry those changes and can corrupt the result once folded.

## 3. Auto-arranging with `git rebase -i --autosquash`

After creating one or more fixup commits, run interactive rebase with a base commit prior to the target commit:

```bash
git rebase -i --autosquash <base>
```

`<base>` is the commit you want to use as the starting point for replaying history; commits after `<base>` fall within the rebase scope. If the target commit is `7b31a20` and its parent commit is `51d0a87`, you can run:

```bash
git rebase -i --autosquash 51d0a87
```

The key point is that `<base>` must come before the target commit. If you pick the target commit itself as the upstream, Git will exclude it from the rebase list and will not be able to fold the fixup into it.

Before autosquash, history might look like:

```text
51d0a87 --- 7b31a20 --- 8c42d19 --- f93e0b1
              ^                         ^
              target commit             fixup commit at HEAD
```

In the interactive rebase todo list, Git automatically moves the fixup right after the target commit and changes its command to `fixup`:

```text
pick 7b31a20 Add login validation
fixup a12bc34 fixup! Add login validation
pick 8c42d19 Add login error response
pick f93e0b1 Update login endpoint documentation
```

Meaning:

- `pick`: apply the commit as a separate commit.
- `fixup`: apply the current commit's changes into the previous commit and discard the current commit's message.
- `squash`: fold changes into the previous commit and allow combining commit messages.

With `--autosquash`, you can still review and edit the todo list before saving and exiting the editor to start the rebase. If there are multiple fixup commits for the same target commit, Git arranges them adjacent to that commit so fixes are applied in sequence.

After a successful rebase, the history becomes:

```text
51d0a87 --- b6e4c91 --- 9a2f7d0 --- 4c0e1b3
              ^                         ^
              commit with fixup merged  new HEAD
```

The new commit IDs are examples only. The target commit and subsequent commits are recreated; the fixup commit is absorbed into the target commit and no longer appears as a separate entry.

## 4. End-to-end workflow from fixing to inspecting history

Perform this on a private feature branch with commits whose old IDs do not need to be preserved.

### Step 1: Identify the commit to modify

```bash
git status -sb
git log --oneline --decorate --graph -10
```

Make sure you are on the right branch and accurately identify the commit to fix. You can inspect the full commit to confirm its contents and message:

```bash
git show --stat 7b31a20
git show 7b31a20
```

### Step 2: Edit contents and stage changes

Edit the source code, inspect the diff, then stage:

```bash
git diff
git add -p
git diff --cached
```

Ensure the staged changes belong solely to the target commit. If you have several independent changes, create separate fixup commits for each corresponding commit so history remains clear after autosquashing.

### Step 3: Create the fixup commit

```bash
git commit --fixup=7b31a20
```

Verify the fixup title and contents:

```bash
git log --oneline -5
git show --stat HEAD
```

### Step 4: Identify the base commit

Find the parent commit of the target commit:

```bash
git rev-parse 7b31a20^
```

If the output is `51d0a87`, that is the starting point you can use in this example. For the repository's initial root commit, there is no parent commit; when rewriting from the root commit is necessary, you can use `--root`, though carefully consider the scope of history being recreated.

### Step 5: Run autosquash

```bash
git rebase -i --autosquash 51d0a87
```

Inspect the todo list arranged by Git. Confirm each `fixup!` line sits immediately after the desired target commit, then save and close the editor to proceed.

### Step 6: Verify after rebasing

```bash
git status -sb
git log --oneline --decorate --graph -10
git show --stat HEAD
```

Confirm the target commit now includes the fix, the fixup commit no longer exists separately in the new history range, and the working tree has no unexpected changes. Re-run tests or checks related to the modified code.

If you are editing a long chain of commits, you can use `git range-diff` to compare the commit chain before and after rebasing. This tool helps detect if any patch changed unexpectedly when commits were recreated.

## 5. Distinguishing `fixup`, `squash`, and `autosquash`

These concepts are related, not synonymous:

| Mechanism | How it works | Commit message after combining |
| --- | --- | --- |
| `fixup` in todo list | Folds changes into the immediately preceding commit | Keeps the preceding commit's message, discards the fixup message |
| `squash` in todo list | Folds changes into the immediately preceding commit | Combines commit messages, allows editing |
| `--autosquash` | Automatically finds and places `fixup!`/`squash!` commits next to their target commit in interactive rebase | Final action depends on prefix and todo list |

`--autosquash` does not create fixup commits itself. It only arranges commits already marked with matching titles when running interactive rebase. Conversely, `git commit --fixup=<commit>` creates a commit with a marker for autosquash to recognize, but does not perform the rebase itself.

If you want to combine commit messages as well, you can use `git commit --squash=<commit>` to create a commit prefixed with `squash!`. When autosquashing, Git marks that commit with the `squash` action instead of `fixup`.

## 6. Variants `--fixup=amend` and `--fixup=reword`

In addition to regular fixups, newer Git versions support variants to also update the target commit's message.

### `--fixup=amend:<commit>`

```bash
git commit --fixup=amend:7b31a20
```

This variant creates a commit titled `amend! ...`. When autosquashing, Git uses the `fixup -C` action: the content changes are folded into the target commit and the target commit's message is replaced with the message from the amend commit. This is a good fit when a fix also requires rewriting the original commit message for accuracy.

### `--fixup=reword:<commit>`

```bash
git commit --fixup=reword:7b31a20
```

This variant creates a commit solely meant to change the target commit's message. It is equivalent to `--fixup=amend:<commit> --only`, so staged changes are not included in the reword commit. When autosquashing, the target commit's content is preserved and its message is replaced with the new message.

The `amend` and `reword` variants require a Git version that supports them. If Git reports it does not recognize the syntax, check `git --version` and the documentation for your installed version. For normal source-code fix folding, `git commit --fixup=<commit>` remains the simplest choice.

## 7. Enabling autosquash automatically in interactive rebase

If you frequently use fixup commits, you can enable the configuration:

```bash
git config --global rebase.autoSquash true
```

Once enabled, interactive rebase runs will automatically apply autosquash per configuration, for example:

```bash
git rebase -i <base>
```

To inspect the current setting:

```bash
git config --show-origin --get rebase.autoSquash
```

To disable the global setting:

```bash
git config --global --unset rebase.autoSquash
```

You can specify `--no-autosquash` for a single rebase if you want to leave marked commits in their original positions. Global configuration affects all of a user's repositories, so only enable it if your workflow regularly relies on this behavior.

## 8. Handling conflicts during autosquash

A fixup commit is applied at the target commit's position. If intervening commits modified the same lines of code, the fix may trigger conflicts as Git replays history.

When rebase pauses, check status:

```bash
git status
```

Open the conflicted files, choose the right content aligned with the target commit's goal, remove conflict markers, and stage the result:

```bash
git add src/main/java/example/LoginValidator.java
git rebase --continue
```

Git continues applying the remaining commits. You may need to repeat this process if another commit also conflicts.

If you realize you are fixing things incorrectly or do not want to continue rebasing:

```bash
git rebase --abort
```

This command cancels the ongoing rebase session and restores the branch to its pre-rebase state. `git rebase --skip` skips the current commit; only use it when you have confirmed the change is no longer needed or was applied another way. Skipping a fixup can discard the fix you intended to fold in.

Do not resolve conflicts by habitually picking one side wholesale. Identify the content to keep in the target commit, cross-check against the original change, and re-run relevant checks once the rebase finishes.

## 9. Limitations and caveats when using autosquash

### The target commit must be within the rebase range

Autosquash can only arrange commits present in the interactive rebase list. If `<base>` is at or after the target commit, the target commit is not replayed and the fixup cannot be folded into it. Choose the target commit's parent or an appropriate older base.

### Commit titles should be clear enough to identify

Git generates the `fixup!` prefix based on the target commit's title. If the project has multiple commits with identical titles, review the todo list carefully before confirming. Use the exact commit ID when creating the fixup and verify the position autosquash selects to avoid folding into the wrong commit with a duplicate title.

### Rebase rewrites history

When a commit is folded or edited, it receives a new ID. Child commits after it are also recreated because their parents change. This affects other branches or clones relying on the old commit IDs.

Prefer autosquashing before sharing a branch. Do not arbitrarily rebase a shared branch or commits teammates already depend on, unless the team has agreed on a history-update plan.

### If the branch has already been pushed

After rebasing a branch that already exists on the remote, local history is no longer a fast-forward of the old remote history. If the team permits updating a rewritten branch, fetch first, verify no one else pushed new commits, and use `--force-with-lease` to reduce the risk of overwriting new changes:

```bash
git fetch origin
git log --oneline --left-right origin/feature/login...feature/login
git push --force-with-lease origin feature/login
```

`--force-with-lease` verifies the remote ref still holds the value local expects before updating. It is safer than `--force`, but it still rewrites the remote branch's history; follow your team's review and coordination process. Do not force push on protected or shared branches without permission.

## 10. Common errors and troubleshooting

| Situation | Possible cause | How to check or resolve |
| --- | --- | --- |
| Autosquash does not move fixup to desired commit | Wrong base chosen or duplicate commit titles | Inspect todo list; choose a base before the target commit and verify the marked commit |
| Fixup still appears as a separate commit | Rebase has not been run or fixup is outside rebase range | Run interactive rebase with `--autosquash` and an appropriate base |
| Git reports nothing to commit | Fix changes are not staged or content matches target commit | Check `git status`, `git diff`, and `git diff --cached` |
| Rebase stops with a conflict | Fixup patch does not apply cleanly onto target commit | Resolve files, stage, and run `git rebase --continue` |
| Push is rejected after rebase | Remote history still has old commits | Fetch, compare both sides, and only use `--force-with-lease` with team permission |
| Commits after rebase have different IDs | Rebase recreated the commits | Expected behavior; verify contents with log, show, and range-diff |

Some helpful diagnostic commands:

```bash
git status
git log --oneline --decorate --graph --all -20
git log --oneline --grep='fixup!'
git show --stat <commit>
git diff <base>..<branch>
```

## 11. Practice

Practice in a test repository or an unshared personal branch:

1. Create three commits with distinct contents on branch `feature/autosquash`.
2. Pick the first or second commit to add a small change to.
3. Stage the exact file or diff hunk, then run `git commit --fixup=<commit-id>`.
4. Use `git log --oneline --graph --decorate` to observe the `fixup!` commit at the top of history.
5. Identify the target commit's parent and run `git rebase -i --autosquash <parent-id>`.
6. Inspect the todo list to confirm the fixup is placed right after the target commit with the `fixup` action.
7. Complete the rebase, and check the log and commit contents after merging.
8. Run relevant tests and compare the commit chain before/after with `git range-diff` if needed.

Try adding another fixup for a different commit, then create a `squash!` commit with `git commit --squash=<commit-id>` to compare how Git handles commit messages. If your Git version supports it, try `--fixup=amend:` or `--fixup=reword:` on a test branch to observe how commit messages are updated.

## 12. Knowledge check

1. What characteristics does a commit created by `git commit --fixup=<commit>` have?
2. Why must you select a base commit prior to the target commit when running `git rebase -i --autosquash`?
3. How does autosquash modify the todo list for `fixup!` commits?
4. How does the `fixup` action differ from `squash` in handling commit messages?
5. What happens to the commit IDs of commits following an edited commit?
6. When rebase pauses due to a conflict, what must you do to continue or cancel the operation?
7. Why should you finish autosquashing before sharing a branch with teammates?
8. When a branch has been pushed and the team permits rewriting history, why is `--force-with-lease` preferable to `--force`?

## Conclusion

Fixup commits link new fixes directly to their original commit at creation time. `git rebase -i --autosquash` automatically places `fixup!` or `squash!` commits into the right spot in the todo list so you can fold them in a controlled way. Choose the right target commit and base, verify the todo list, handle conflicts carefully, and verify history after rebasing. Because rebase changes commit IDs, perform it before sharing a branch or coordinate with your team before updating pushed history.

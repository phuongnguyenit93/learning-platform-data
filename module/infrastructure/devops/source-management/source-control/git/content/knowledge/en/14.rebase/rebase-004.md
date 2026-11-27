# Interactive rebase: reword, edit, squash, fixup, and drop

During development, a branch can accumulate many small commits: typo fixes, added tests, edits touching the same block of code, or commits with unclear messages. Before opening a pull request, you may want to organize those commits into a cleaner, easier-to-review sequence. Git provides **interactive rebase** to inspect and adjust the list of commits to be replayed, such as changing messages, pausing to edit contents, combining multiple commits, or dropping a commit.

This lesson belongs to the **Rebase** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; while building skills in collaborating across branches, resolving conflicts, tracking down changes, and recovering from mistakes without losing important history. Interactive rebase is a useful tool for clarifying a private branch's history before integration, provided you understand which commits will be rewritten and who relies on them.

## 1. What is interactive rebase?

A standard rebase replays the current branch's commits onto a different base commit. With the interactive option, Git opens a list of commits to be processed and lets you choose an action for each commit. This list is commonly called the **todo list**.

You can:

- Keep a commit as is with <code>pick</code>.
- Change a commit's message with <code>reword</code>.
- Pause to edit a commit's contents with <code>edit</code>.
- Combine a commit into the preceding commit with <code>squash</code> or <code>fixup</code>.
- Remove a commit from the new history with <code>drop</code>.
- Reorder commits in the list if the changes can still apply cleanly in the new order.

Interactive rebase does not modify old commits directly. Git creates a new commit chain by replaying the changes according to the todo list. Because a commit's identity depends on its content, parent commit, and metadata, replayed commits typically receive new hashes, even if the source code content does not change.

## 2. Selecting the right commit range

Before running interactive rebase, identify the base commit and the commits to include in the todo list. Common syntax:

~~~bash
# Edit the 4 most recent commits on the current branch
git rebase -i HEAD~4

# Edit commits on the current branch not yet in origin/main
git fetch origin
git rebase -i origin/main
~~~

With <code>git rebase -i HEAD~4</code>, <code>HEAD~4</code> is the base commit; the todo list contains the four commits after it in the current linear history. The base commit does not appear in the list. If you select the wrong range, you may accidentally modify commits outside the work you are doing.

With <code>git rebase -i origin/main</code>, Git identifies the commits on the current branch not yet in upstream and replays them onto the upstream base. Fetch first so the remote-tracking branch reflects the latest data. If the branch has complex branching history or merge commits, inspect the commit graph before choosing how to rebase.

Useful inspection commands:

~~~bash
# View current branch and working tree status
git status
git branch --show-current

# View history as a graph
git log --oneline --graph --decorate -15

# View commits that will be in range relative to the base branch
git log --oneline origin/main..HEAD
~~~

If you want to include the entire history from the root commit in an interactive rebase, you can use <code>git rebase -i --root</code>. This is a very broad scope and is usually unnecessary when you only want to tidy up a few commits on a feature branch.

## 3. Preparing before rewriting history

Interactive rebase should be performed with a clean working tree and a clear understanding of the commits in scope. Before starting:

1. Check for uncommitted changes.
2. Confirm the right branch and base commit.
3. Read the contents of commits that may be changed, combined, or dropped.
4. Create a backup reference if the history is valuable or you are unfamiliar with the operation.
5. Confirm that commits in scope have not been shared or that the team has agreed to allow rewriting.

For example:

~~~bash
git status
git log --oneline --graph --decorate -10

# Create a backup branch pointing to the pre-rebase state
git branch backup/feature-before-rebase
~~~

The backup branch preserves the original commit position so you can compare or recover if needed. Choose a name that does not already exist and delete the backup branch once you have verified the result, following your project's branch management workflow.

If the working tree has uncommitted changes, commit them or save them safely before rebasing. Rebase may refuse to start if changes would be overwritten; do not try to proceed by deleting changes without understanding their contents.

**Important:** only rewrite your own private history. Commits pushed to a multi-person branch, the main branch, a release branch, or commits that teammates have branched off of are considered shared history. Coordinate before rebasing those commits. When you need to fix a change already integrated into shared history, it is usually better to create a new commit or use <code>git revert</code>.

## 4. Opening the todo list and understanding its structure

Suppose the current branch has six new commits since the base commit:

~~~text
a1b2c3d feat: add export endpoint
b2c3d4e docs: add export API docs
c3d4e5f feat: validate export filters
d4e5f6a test: add export validation tests
e5f6a7b fix: correct filter edge case
f6a7b8c chore: add temporary debug logging
~~~

Run:

~~~bash
git rebase -i HEAD~6
~~~

Git opens your editor with a todo list similar to:

~~~text
pick a1b2c3d feat: add export endpoint
pick b2c3d4e docs: add export API docs
pick c3d4e5f feat: validate export filters
pick d4e5f6a test: add export validation tests
pick e5f6a7b fix: correct filter edge case
pick f6a7b8c chore: add temporary debug logging

# Rebase a1b2c3d..f6a7b8c onto ...
# Commands:
# p, pick <commit> = use commit
# r, reword <commit> = use commit, but edit the commit message
# e, edit <commit> = use commit, but stop for amending
# s, squash <commit> = use commit, but meld into previous commit
# f, fixup [-C | -c] <commit> = like squash, but discard this commit's log message
# d, drop <commit> = remove commit
~~~

Each line starts with a command, followed by the commit hash and message. Comment lines starting with <code>#</code> only explain the syntax and are not executed.

The todo list is usually ordered from oldest commit to newest commit. Git executes each line sequentially from top to bottom. When you save and close the editor, Git begins the rebase using the actions you selected.

## 5. Key commands in interactive rebase

### pick – keep the commit

~~~text
pick a1b2c3d feat: add export endpoint
~~~

<code>pick</code> tells Git to replay the commit with its corresponding changes and message. This is the default action when you do not need to modify a specific commit. The new commit may still have a different hash because it is recreated on a new base or a preceding commit was rewritten.

### reword – change the commit message

~~~text
reword b2c3d4e docs: add export API docs
~~~

<code>reword</code> keeps the commit's source code changes but prompts you to enter a new message. After saving the todo list, Git opens the message editor for that commit. For instance, you can change a generic message to:

~~~text
docs: document export endpoint parameters
~~~

Choose <code>reword</code> when the change content is already right but the message does not clearly describe the purpose. Because the message is part of commit metadata, the commit is recreated and its hash changes.

### edit – pause to modify commit contents

~~~text
edit c3d4e5f feat: validate export filters
~~~

<code>edit</code> tells Git to replay that commit and then pause so you can edit its contents. When rebase pauses, HEAD is at the commit selected for editing. You can update files, stage changes, and amend the commit:

~~~bash
# Check status while rebase is paused
git status

# Edit the file in your editor, then stage what should go into the commit
git add src/ExportFilter.java

# Replace the paused commit with the edited version
git commit --amend

# Continue replaying the remaining commits
git rebase --continue
~~~

If you only want to edit the message without changing contents, you can use <code>git commit --amend</code> and keep or enter the appropriate message. If you want to keep the existing message unchanged, use <code>git commit --amend --no-edit</code> after staging changes.

While paused at <code>edit</code>, you can also split a commit into multiple smaller commits. Operate carefully with HEAD, the index, and the working tree; check <code>git status</code> and inspect diffs before recreating each commit. Once done, run <code>git rebase --continue</code> so Git replays the rest.

### squash – combine commits and merge messages

~~~text
pick c3d4e5f feat: validate export filters
squash d4e5f6a test: add export validation tests
~~~

<code>squash</code> folds the current commit's changes into the nearest selected commit above it in the todo list. Git combines the commit messages and typically opens the editor so you can refine the final message.

In the example, the test changes are folded into the commit adding filter validation. The new commit might carry the message:

~~~text
feat: validate export filters

Add tests for accepted and rejected filter values.
~~~

The squashed commit no longer appears as a separate commit in the new history, though its changes remain in the resulting snapshot unless edited or conflicted.

<code>squash</code> requires a preceding commit to fold into. Do not place a <code>squash</code> line at the top of the todo list when no commit is kept before it.

### fixup – combine commits and discard the later message

~~~text
pick c3d4e5f feat: validate export filters
fixup e5f6a7b fix: correct filter edge case
~~~

<code>fixup</code> also folds the current commit's changes into the previous commit, but discards the folded commit's message. The previous commit's message is kept. Use <code>fixup</code> when the later commit is just a follow-up adjustment, typo fix, or minor bug fix belonging to the same change, and you do not want a separate message for it.

Comparison:

| Command | Source code changes | Message after combining |
|---|---|---|
| <code>squash</code> | Folded into previous commit | Combines messages, allows editing |
| <code>fixup</code> | Folded into previous commit | Discards folded commit's message, keeps previous commit's message |

### drop – remove a commit from the new history

~~~text
drop f6a7b8c chore: add temporary debug logging
~~~

<code>drop</code> removes that commit from the recreated history chain. You can also delete the corresponding line from the todo list altogether; Git treats omitted commits as dropped.

Only use <code>drop</code> when you have confirmed the commit's changes are no longer needed. If the commit contains part of a bug fix or a change that later commits depend on, dropping it can prevent subsequent commits from applying or cause broken product behavior.

Before dropping, inspect the contents:

~~~bash
git show --stat f6a7b8c
git show f6a7b8c
~~~

If you only want to remove part of the changes, consider using <code>edit</code> to modify the commit instead of dropping the whole thing.

## 6. Complete example: cleaning up six commits

Suppose the feature branch has six commits as in the example above. Goal:

- Keep the commit adding the endpoint.
- Reword the documentation commit message for clarity.
- Pause at the validation commit to add a condition.
- Fold the test commit into the validation commit.
- Fold the edge-case fix commit into the same validation change without keeping a separate message.
- Drop the temporary debug commit.

First, inspect and create a backup branch:

~~~bash
git status
git log --oneline --graph --decorate -10
git branch backup/feature-before-rebase
~~~

Open the todo list:

~~~bash
git rebase -i HEAD~6
~~~

Edit the lines to:

~~~text
pick a1b2c3d feat: add export endpoint
reword b2c3d4e docs: add export API docs
edit c3d4e5f feat: validate export filters
squash d4e5f6a test: add export validation tests
fixup e5f6a7b fix: correct filter edge case
drop f6a7b8c chore: add temporary debug logging
~~~

After saving and closing the todo list:

1. Git processes the first commit.
2. Git pauses at the commit marked <code>reword</code> for you to enter the new message.
3. Git replays the <code>edit</code> commit and pauses. You edit the source code, run necessary checks, stage, and amend the commit.
4. Run <code>git rebase --continue</code>. Git folds the test commit using <code>squash</code> and asks you to edit the combined message.
5. Git folds the edge-case fix commit using <code>fixup</code>, discarding its separate message.
6. Git skips the debug commit marked <code>drop</code> and finishes the remaining steps.

Once complete, verify the history and contents:

~~~bash
git status
git log --oneline --graph --decorate -10
git diff backup/feature-before-rebase..HEAD
git show --stat HEAD
~~~

Compare the diff between the backup branch and the new branch to check the overall changes. If the rebase's goal was to organize history without altering the product, the final content should match what existed before the rebase, aside from changes you intentionally edited or removed. For complex ranges, run tests and review each new commit before pushing.

## 7. Reordering commits

The todo list allows moving lines up or down. Git replays commits in the new order. This is useful when you want to place a foundational commit before a dependent commit or group related changes together.

For example:

~~~text
pick aaaaaaa feat: add export model
pick bbbbbbb test: add export model tests
pick ccccccc docs: document export model
~~~

You can reorder them to:

~~~text
pick aaaaaaa feat: add export model
pick ccccccc docs: document export model
pick bbbbbbb test: add export model tests
~~~

However, the new order may introduce conflicts or make a commit fail to apply because it depends on changes from a commit placed later. Only reorder when you understand the dependencies between changes. If a reordered todo list produces conflicts, handle them using the standard rebase conflict workflow.

## 8. Handling conflicts during interactive rebase

Rebase replays commits one by one. If a commit's changes cannot be applied automatically onto the current state, Git pauses and reports the conflicting paths.

Workflow:

~~~bash
# View conflicting files
git status

# Open the files, resolve to the desired content
# Then mark each file as resolved
git add src/ExportFilter.java

# Continue the rebase
git rebase --continue
~~~

If multiple files conflict, resolve and stage each file. Then review the staged contents before continuing:

~~~bash
git diff
git diff --staged
git status
git rebase --continue
~~~

When rebase pauses due to a conflict:

- <code>git rebase --continue</code> continues replaying the remaining commits after you resolve the conflicts.
- <code>git rebase --skip</code> skips the commit currently being replayed. Only use when intentionally discarding all of that commit's changes from the new history.
- <code>git rebase --abort</code> cancels the entire rebase session and returns the branch to its state before starting.

Do not use <code>--skip</code> just to get past a conflict error. The paused commit may contain important changes. If unsure, inspect the commit being applied and consult the owner before deciding.

## 9. Editing the todo list while rebase is paused

If you are in the middle of an interactive rebase session and realize you need to change actions for unprocessed commits, you can reopen the list:

~~~bash
git rebase --edit-todo
~~~

Edit the remaining lines, save, and continue with:

~~~bash
git rebase --continue
~~~

This command only edits the portion of the todo list not yet executed. It does not automatically undo commits already replayed in the current session. If you chose the wrong action earlier and need to redo the entire process, you can abort and restart with the right range and todo list after checking the status.

## 10. Autosquash with fixup commits

While developing, you can create a small commit to fix an earlier commit without immediately opening interactive rebase. Git supports creating commits with recognizable messages via <code>--fixup</code>:

~~~bash
# Create a follow-up fix commit for an existing commit
git add src/ExportFilter.java
git commit --fixup=c3d4e5f
~~~

The new commit has a message formatted as <code>fixup! ...</code>. Before finalizing the branch, run:

~~~bash
git rebase -i --autosquash origin/main
~~~

Git automatically moves the fixup commit next to its target commit and marks its action as <code>fixup</code> in the todo list. You should still review the list before saving to make sure the commit is folded into the intended target.

Similarly, <code>git commit --squash=&lt;commit&gt;</code> creates a commit with a recognizable <code>squash! ...</code> message; the <code>--autosquash</code> option arranges it for squashing. Autosquash only assists in ordering the todo list; it does not prove on its own that changes can be combined safely.

## 11. Finalizing, verifying, and updating the remote

When Git reports the rebase is complete, do not rush to push. Inspect first:

~~~bash
git status
git log --oneline --graph --decorate -15
git diff origin/main...HEAD
~~~

Then:

- Run tests and required project checks.
- Inspect each new commit to confirm reasonable messages and change scope.
- Verify that intentionally dropped changes are genuinely absent from the result.
- Check that no temporary files, debug logs, or sensitive data were committed.

If this is your own private branch and no one else depends on the previously pushed history, updating the remote may require a conditional force push:

~~~bash
git push --force-with-lease origin feature/export
~~~

Only do this after confirming team policy permits rewriting that branch. If the remote already has new commits you have not fetched or handled, <code>--force-with-lease</code> will typically reject the push; stop, fetch, and inspect history rather than retrying with <code>--force</code>.

If commits have already been shared or multiple people work on the branch, do not force push just to make history look prettier. Keep the shared history and add corrective commits, or coordinate with everyone involved if rewriting is truly necessary.

## 12. Recovering when rebase results are not as expected

### Canceling an in-progress rebase session

If you have not finished the rebase and want to return to the state before starting:

~~~bash
git rebase --abort
~~~

Git cancels the current rebase session and restores the branch to its original position. This is the right approach when you realize you picked the wrong range or todo list, or do not want to continue resolving conflicts.

### Rebase finished, but you want to go back

If the rebase has finished and you want to find the previous position, check the reflog:

~~~bash
git reflog
~~~

The reflog records local reference updates, including rebase operations. Find the entry before the rebase, confirm the exact commit, and then create a recovery branch pointing to that commit:

~~~bash
git branch recovery/before-rebase <commit-hash>
~~~

After confirming the recovery branch has the right contents, decide how to restore your working branch. Do not run reset or force push immediately before verifying the commit hash and any changes created after the rebase.

The backup branch created earlier is also a useful reference point. Reflog and backup branches help locate commits, but do not replace proper backups or coordination when working on shared history.

## 13. Common errors and misconceptions

| Symptom or misconception | Explanation and resolution |
|---|---|
| Reword did not change source code, yet commit hash changed | The commit message is part of metadata; the commit is recreated, so the hash changes. |
| Squash reports there is no previous commit | <code>squash</code> must follow a commit already selected to fold into. |
| Fixup still keeps the old commit message | <code>fixup</code> discards the folded commit's message and keeps the preceding commit's message. |
| Edit pauses rebase and you do not know how to continue | Edit files, stage, amend the commit, then run <code>git rebase --continue</code>. |
| Drop loses needed changes | Inspect the commit with <code>git show</code> and check whether later commits depend on it before dropping. |
| Rebase produces conflicts | Resolve each file, stage the result, then continue; abort if you need to cancel the entire session. |
| Push is rejected after rebase | The remote may still hold old history or have new commits. Fetch and inspect before deciding. |
| Force-with-lease is always safe | It only checks the remote ref against the client's expectation; it does not know who used old commits. |
| Any pushed branch can be rebased | Shared branches require coordination; on shared branches prefer new fix commits or revert. |

## 14. Self-check exercises

Practice in a test repository on an unshared branch:

1. Create five small commits on a feature branch, each with a distinct purpose.
2. Run <code>git rebase -i HEAD~5</code> and identify the base commit and the order of the todo list.
3. Change one commit's message using <code>reword</code>; inspect the commit hash before and after.
4. Select a commit with <code>edit</code>, modify its contents, stage and amend, then continue the rebase.
5. Fold a test commit into a feature commit with <code>squash</code>, then fold a small fix commit with <code>fixup</code>.
6. Inspect the contents of a temporary commit and use <code>drop</code> to remove it from the new history.
7. Compare the overall diff before and after the rebase to confirm desired changes remain.
8. Try creating a conflict during rebase, resolve it, and continue; repeat in another attempt and use abort.
9. Create a <code>--fixup</code> commit and run <code>git rebase -i --autosquash</code> to observe how Git arranges the todo list.
10. Explain why you should not force push new history onto a branch teammates are already basing work on.

When you become proficient with <code>reword</code>, <code>edit</code>, <code>squash</code>, <code>fixup</code>, and <code>drop</code>, you can organize a feature branch's history into clear, focused, easy-to-review commits. Do this before the history is widely shared, and preserve the team's shared history unless everyone has coordinated for an intentional rewrite.

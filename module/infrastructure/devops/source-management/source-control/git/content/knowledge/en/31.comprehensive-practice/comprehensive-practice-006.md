# Cleaning Up a Branch Before Handover With Interactive Rebase

During feature development, the commit history on a personal branch often captures experimental steps: fixing typos, adding debug logs, adjusting tests, renaming variables, or amending a commit you just made. These small commits are helpful while working, but if handed over as-is, reviewers may have to wade through fragmented changes to understand one finished result.

`git rebase -i` (interactive rebase) lets you reorder, combine, reword, edit, or drop commits before handing off a branch. This lab walks through the entire workflow: inspecting the branch, backing up the original history, updating the base reference, tidying commits, resolving conflicts, running checks, and delivering a clear history.

This is a history-rewriting operation. Commit hashes change, so confirm whether the branch has been shared and coordinate with your team before rewriting a branch others rely on.

## 1. Expected Outcomes

After this lab, you will be able to:

- Identify the exact commits unique to a feature branch relative to its base branch.
- Protect the current state with a backup branch and record commit hashes.
- Use interactive rebase to reorder, combine, reword, and drop commits.
- Use `fixup!` with `--autosquash` to fold follow-up fix commits.
- Resolve conflicts while replaying commits and know when to continue, skip, or abort a rebase.
- Inspect history after cleanup and verify the feature's contents remain complete.
- Hand off a branch using the workflow suited to whether it has already been pushed.

## 2. Practice Scenario

Suppose a team is building a payment feature. The base branch is `main`, and your working branch is `feature/payment-summary`. During development, you created these commits:

```text
main: A --- B --- C
                  \
feature:           D --- E --- F --- G --- H
```

Purpose of each commit:

| Commit | Current contents | Planned handling |
| --- | --- | --- |
| D | Add payment summary model | Keep |
| E | Fix typo in model | Fold into D |
| F | Add total calculation service | Keep |
| G | Add tests for service | Keep or fold into F depending on review policy |
| H | Fix log message and variable name | Fold into the appropriate commit |

The goal is an easy-to-review history, for example:

```text
main: A --- B --- C
                  \
feature:           D' -------- F' --- G'
```

Here each commit describes a meaningful unit of change. There is no mandatory rule that every branch must be squashed to one commit; what matters is that history reflects logical, verifiable units of change.

## 3. Preparing the Repository and Identifying the Commit Range

Before rewriting history, inspect the repository:

```bash
git status -sb
git branch --show-current
git log --oneline --decorate --graph -15
```

Confirm you are on `feature/payment-summary`. If the working tree or index has uncommitted changes, address them first:

- Commit unfinished work if it already forms a meaningful unit.
- Or stash temporary changes you want to carry over after the rebase.
- Back up important untracked files separately because default stashing excludes them.

Interactive rebase normally requires a clean working tree. Never start with unprotected edits, as rebase may refuse to run or conflict resolution will get mixed up with active work.

### Refreshing Information From the Remote

```bash
git fetch origin
git status -sb
```

`fetch` updates remote-tracking refs without merging or rebasing changes into your current branch. Verify the feature's actual base branch; this lab uses `origin/main`.

Inspect commits unique to your branch:

```bash
git log --oneline --decorate origin/main..HEAD
```

The `origin/main..HEAD` range lists commits reachable from `HEAD` but not reachable from `origin/main`. This is typically the range fed into interactive rebase:

```bash
git rebase -i origin/main
```

If your project's base branch is `develop`, `release/2.x`, or another branch, replace `origin/main` with the agreed upstream ref. Never guess the base branch purely from the branch name.

### Checking the Merge Base

```bash
git merge-base origin/main HEAD
```

The merge base is the best common ancestor between the two history tips. Interactive rebase onto `origin/main` replays your branch's commits after that common point onto the new tip of `origin/main`. If history has multiple merges or complex base changes, check the merge base and graph before proceeding.

## 4. Protecting History Before Rebasing

Create a backup branch pointing to the current state:

```bash
git branch backup/feature-payment-summary-before-rebase
```

Record the current commit:

```bash
git rev-parse HEAD
git show --no-patch --oneline HEAD
```

A backup branch is a ref retaining the commit and all history reachable from it. If the rebase outcome is unsatisfactory, you can still compare against or recreate your branch from this checkpoint.

Verify the backup branch:

```bash
git branch --list "backup/*"
git log --oneline --decorate backup/feature-payment-summary-before-rebase -10
```

Do not delete the backup branch right after rebasing. Only clean it up once the rewritten branch, CI, and review are all verified and the team no longer needs to revert to pre-rebase history.

### Reflog as a Recovery Safety Net

Git records movements of `HEAD` and branches in the reflog:

```bash
git reflog --date=local
```

Reflog is useful if you accidentally move a branch or need to find a pre-rebase commit. However, reflog is strictly local and expires over time; an explicit backup branch is clearer and safer when preparing to rewrite history.

## 5. Opening Interactive Rebase

Run:

```bash
git rebase -i origin/main
```

Git opens your editor with a commit list ordered from oldest to newest. For example:

```text
pick 1a2b3c4 Add payment summary model
pick 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
pick 5e6f7a8 Improve payment log message
```

Each line starts with a command and a commit hash. You can change the command or reorder lines. Git replays the commit sequence in the order shown in the todo list.

By default, the editor displays a guide of supported commands at the bottom. Edit only the commit command lines at the top; leave the instructional comments intact.

## 6. Common Interactive Rebase Commands

| Command | Alias | Effect |
| --- | --- | --- |
| `pick` | `p` | Keep the commit as-is |
| `reword` | `r` | Keep the changes but edit the commit message |
| `edit` | `e` | Pause at the commit to amend content or metadata, then continue |
| `squash` | `s` | Fold the commit into the previous commit and edit the combined message |
| `fixup` | `f` | Fold the commit into the previous commit, discarding its message |
| `drop` | `d` | Remove the commit from the recreated history |
| `exec` | `x` | Run a shell command at that point during the rebase |
| `break` |  | Pause at that point for manual inspection before continuing |

When using `squash` or `fixup`, the commit being folded must follow a target commit in the todo list. If a commit is marked to be folded with no suitable preceding commit, rebase reports an error or fails to behave as intended.

Advanced commands such as `label`, `reset`, and `merge` appear in the todo list when rebasing while preserving merge topology, typically with `--rebase-merges`. This lab focuses on linear history for clarity; do not manually delete or alter Git-generated merge lines without understanding the branch topology.

## 7. Combining Commits With squash and fixup

### Squash: Combine and Edit the Message

Example todo list:

```text
pick 1a2b3c4 Add payment summary model
squash 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
squash 5e6f7a8 Improve payment log message
```

Git folds commit `2b3c4d5`'s changes into the preceding commit. Because `squash` is used, Git opens the editor to combine or rewrite the commit message. Similarly, the log message commit is folded into the test commit right before it in this example.

After folding, write a message describing the final result, for example:

```text
Add payment summary model
```

or:

```text
Add payment calculation tests and improve diagnostics
```

Do not leave behind fragmented lines like "fix", "again", or "typo" if the combined commit should stand on its own for reviewers.

### Fixup: Combine and Discard the Secondary Message

If a commit merely fixes a detail in the preceding commit, `fixup` is usually a better fit:

```text
pick 1a2b3c4 Add payment summary model
fixup 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
```

`fixup` keeps the first commit's message and discards the folded commit's message. Code changes from both commits are still combined.

### Don't Fold Every Commit Out of Habit

A test commit may be worth keeping separate if the team likes reviewing logic and tests as two distinct units. A migration or API-change commit might need to stay separate for easy cherry-picking. Choose structure based on how your team reviews, releases, and maintains code.

## 8. Fixing Commit Messages With reword

If a commit's code is right but its message is unclear:

```text
pick 1a2b3c4 Add payment summary model
reword 3c4d5e6 Add service
pick 4d5e6f7 Add tests for payment calculation
```

When rebase reaches commit `3c4d5e6`, Git opens your editor to enter a new message. For example:

```text
Add service to calculate payment totals
```

Messages should describe the specific change and follow your project's commit conventions. Never put secrets, customer data, or tokens in a commit message.

## 9. Modifying Commit Contents With edit

When you need to adjust code inside an older commit, change `pick` to `edit`:

```text
pick 1a2b3c4 Add payment summary model
edit 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
```

Git pauses right after applying the commit marked `edit`. You can now edit files, stage, and amend:

```bash
git status
# Edit the necessary files
git add src/main/java/PaymentService.java
git commit --amend
```

If you only want to edit the message, you can use `git commit --amend -m "Add payment calculation service"`; to open the editor, run `git commit --amend`.

After amending, resume replaying the remaining commits:

```bash
git rebase --continue
```

The amended commit and every commit replayed after it will receive new hashes. If your amended change prevents a later commit from applying cleanly, Git stops with a conflict; resolve it as shown in the conflict section below.

## 10. Removing Commits With drop

If a commit was an experiment that should not be kept:

```text
pick 1a2b3c4 Add payment summary model
drop 2b3c4d5 Add temporary debug output
pick 3c4d5e6 Add payment calculation service
```

`drop` removes the commit from the new history. Before dropping, inspect the commit's diff:

```bash
git show --stat 2b3c4d5
git show 2b3c4d5
```

Never drop a commit merely because its message is poor or it is small. If it contains necessary logic, combine or edit it rather than deleting it. Dropping a commit that later commits depend on can cause conflicts or broken behavior downstream.

## 11. Reordering Commits

You can move lines around in the todo list. For example:

```text
pick 1a2b3c4 Add payment summary model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
```

Commit order should reflect dependencies. A commit creating a model should precede a commit using that model; test commits can follow the code they verify. Reversing dependent commits can leave intermediate commits unable to build or pass tests.

Reordering commits does not merely alter log display. Git actually replays patches in the new order; patches may fail to apply cleanly or create invalid intermediate states.

If two commits are tightly coupled, consider combining them. If every commit must remain buildable, verify each intermediate state after rebasing or use `exec` to run tests at key points.

## 12. Auto-Folding Follow-Up Commits With autosquash

Git supports creating commits prefixed with `fixup!` or `squash!` to target an earlier commit.

For example, after committing the model, you spot a small bug to fix:

```bash
git add src/main/java/PaymentSummary.java
git commit --fixup=1a2b3c4
```

Git creates a commit with a message like `fixup! Add payment summary model`. Next, run:

```bash
git rebase -i --autosquash origin/main
```

Git automatically moves `fixup!` and `squash!` commits right after their target commits and marks them with `fixup` or `squash` in the todo list.

You can enable autosquash by default:

```bash
git config --global rebase.autoSquash true
```

Or pass `--autosquash` for a single rebase. When creating a fixup commit, specify the target commit clearly using its hash or Git-supported syntax. Review the todo list before saving to make sure every commit folds into the right target.

## 13. Using exec for Automated Checks During Rebase

`exec` inserts a shell command into the todo list. Git runs that command at the corresponding point during replay.

Example:

```text
pick 1a2b3c4 Add payment summary model
exec ./gradlew test --tests PaymentSummaryTest
pick 3c4d5e6 Add payment calculation service
exec ./gradlew test --tests PaymentServiceTest
pick 4d5e6f7 Add tests for payment calculation
```

If an `exec` command fails, rebase pauses so you can inspect. Fix the issue or adjust history, then continue with `git rebase --continue`; if the approach is no longer viable, cancel with `git rebase --abort`.

You can also pass `--exec` directly:

```bash
git rebase -i --exec "./gradlew test" origin/main
```

The test command must be runnable at every intermediate commit. If the first commit does not yet include the tests or build configuration, `exec` can fail even when the final state is valid. Pick stage-appropriate tests or run them only at relevant checkpoints.

## 14. Handling Conflicts During Interactive Rebase

A conflict occurs when the patch of a replayed commit cannot apply cleanly onto the current state. Git pauses and reports which files need attention:

```bash
git status
git diff --name-only --diff-filter=U
```

Open the files, examine the conflict markers, or launch your configured merge tool. After deciding on and editing the final contents:

```bash
git add src/main/java/PaymentService.java
git status
git rebase --continue
```

Repeat if subsequent commits also conflict. Never run `git commit` manually in place of `git rebase --continue` during an active rebase; Git needs to manage the replay state and metadata.

### Three Options When Facing a Conflict

| Command | When to use | Effect |
| --- | --- | --- |
| `git rebase --continue` | Conflict is resolved and staged | Resumes replaying commits |
| `git rebase --skip` | Current commit is no longer needed or its changes are already integrated elsewhere | Drops the commit currently being replayed |
| `git rebase --abort` | You want to cancel the entire rebase | Restores the state before rebase began |

Never use `--skip` just to bypass a hard conflict. It discards the entire current commit from the new history. Inspect `git show REBASE_HEAD` or the commit being replayed to understand its contents before deciding.

### Checking Status After a Conflict

```bash
git diff
git diff --cached
git ls-files -u
```

Once resolved and staged, `git ls-files -u` no longer lists the fixed files. Run relevant tests before continuing if the conflict touched critical logic.

## 15. Aborting a Rebase and Recovering From Unexpected Outcomes

If you are still mid-rebase and want to return to the starting state:

```bash
git rebase --abort
```

If the rebase already finished but the result is wrong, the backup branch created earlier gives you a clear recovery point:

```bash
git log --oneline --decorate backup/feature-payment-summary-before-rebase -10
```

You can create a new branch from the backup to inspect:

```bash
git switch -c rescue/payment-summary-before-rebase backup/feature-payment-summary-before-rebase
```

If you did not create a backup, reflog can help locate the pre-rebase position:

```bash
git reflog --date=local
```

Create a rescue branch from the right commit before trying other recovery actions:

```bash
git branch rescue/before-interactive-rebase <commit-id>
```

Do not run `git gc --prune=now` or expire the reflog while trying to recover commits. When a backup branch exists, keep it until handover and verification are complete.

## 16. Inspecting History After Cleanup

After the rebase finishes:

```bash
git status -sb
git log --oneline --decorate --graph origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Verify that:

- The working tree is clean.
- The commit list contains only feature-related changes.
- Messages clearly describe each change.
- No debug commits or unnecessary temporary edits remain.
- Commit ordering is logical and easy to review.
- The final diff delivers the full expected functionality.

Compare contents before and after rebasing using the backup branch:

```bash
git diff backup/feature-payment-summary-before-rebase HEAD
```

This compares the final snapshots of both branch tips. Because rebasing aims to clean up history rather than change the end product, the diff between the two tips should usually be empty or show only intentional differences. If there is an unexpected large diff, inspect commits you dropped, fixed up, or reordered.

### Checking Branch-Specific Commits Against the Base Branch

```bash
git log --oneline origin/main..HEAD
git diff origin/main...HEAD
```

`git log origin/main..HEAD` lists commits unique to your branch. `git diff origin/main...HEAD` compares changes from the merge base to the branch tip, ideal for reviewing what the feature contributes relative to the base branch.

## 17. Running Checks Before Handover

Run the checks required by your project. For example, for a Java project using Gradle:

```bash
./gradlew clean test
```

If the project uses Maven:

```bash
mvn clean verify
```

Do not run both if the project only uses one build tool. Use the exact command specified in the repository and verify tests cover your changes.

Check for whitespace errors and leftover conflict markers:

```bash
git diff --check origin/main...HEAD
git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- .
```

`git grep` returns a non-zero exit code when no markers are found; that is usually the expected outcome. If the project includes documentation files illustrating conflict markers, inspect manually to distinguish valid examples from unresolved conflicts.

Check final status:

```bash
git status -sb
git diff --stat origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

## 18. Unpushed Branches vs. Shared Branches

Before rebasing, determine sharing status:

| Branch state | How to handle |
| --- | --- |
| Local only, never pushed | Safe to rebase after backing up and checking |
| Pushed, used only by you | May need a force update after aligning with team workflow |
| Checked out or built upon by others | Do not rewrite unilaterally; coordinate a sync plan first |
| Shared `main`/release branch | Never interactively rebase unilaterally; follow branch protection rules |

Rebase creates new commits, changing commit hashes. If a branch was pushed, the remote still holds the old commits until updated. Others might already depend on the old commits; an unannounced force push causes their local history to diverge from the remote.

For a personal branch already pushed and approved for rewriting, update the remote with `--force-with-lease` after confirming the remote has no new commits you need to keep:

```bash
git push --force-with-lease origin feature/payment-summary
```

`--force-with-lease` verifies that the remote ref is still at the commit your local repository expects before updating it. It is safer than `--force`, though it does not replace talking with teammates. If the remote changed, the push is rejected; fetch, inspect the new commits, and decide how to integrate before retrying.

Never force-push to `main`, release branches, or protected branches without an explicit governance process.

## 19. Handing Over the Branch After Rebasing

Before opening a pull request or requesting review:

1. Confirm you are on the right feature branch.
2. Confirm `git status` is clean.
3. Confirm the final diff against the base branch matches your goal.
4. Run tests, linters, and any team-required checks.
5. Re-read commit messages and commit ordering.
6. Push the branch per your team's workflow.
7. Create or update the pull request, summarizing the behavior and anything reviewers should pay special attention to.

Example pushing an unpublished branch:

```bash
git push -u origin feature/payment-summary
```

If the branch already exists on the remote and was just rewritten, use force-with-lease only when permitted by team policy:

```bash
git push --force-with-lease origin feature/payment-summary
```

In the pull request description, highlight functionality, testing approach, and key technical decisions. There is no need to list every minor fixup that was folded away; the clean history should speak for itself.

## 20. Complete Todo List Example

Suppose the initial history has five commits:

```text
pick a111111 Add payment summary model
pick b222222 Fix typo in payment model
pick c333333 Add payment calculation service
pick d444444 Add tests for payment calculation
pick e555555 Improve payment log message
```

One clean way to organize it:

```text
pick a111111 Add payment summary model
fixup b222222 Fix typo in payment model
pick c333333 Add payment calculation service
pick d444444 Add tests for payment calculation
fixup e555555 Improve payment log message
```

The result leaves three meaningful commits:

```text
Add payment summary model
Add payment calculation service
Add tests for payment calculation
```

If team conventions prefer tests in the same commit as the service, you can squash or fixup the test commit into the service commit. If reviewers prefer evaluating tests independently, keep the test commit separate. Good history helps others understand and verify changes, not necessarily the history with the fewest commits.

## 21. Common Issues

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `rebase` reports dirty working tree | Uncommitted changes or blocking untracked files | Commit/stash and back up untracked files you need to keep |
| Expected commits missing from todo list | Wrong upstream chosen or commits already reachable from upstream | Check `git log upstream..HEAD` and merge base |
| `squash` folds into the wrong commit | Squash line is not immediately below the target commit in the todo list | Reorder the todo list and verify sequence |
| Rebase conflict after reordering | A commit depends on edits from an earlier commit | Restore logical order or combine dependent commits |
| `--autosquash` does not move commits | Message does not match target commit or lacks fixup/squash prefix | Check commit messages and todo list |
| Test in `exec` fails | Intermediate commit lacks required structure/tests/dependencies | Pick stage-appropriate tests or amend intermediate commits |
| Rebase finished but final diff differs significantly | Accidentally dropped or mis-folded a commit | Compare with backup branch and recover needed commits |
| Push rejected after rebase | Remote changed or branch is protected | Fetch, inspect new commits, and coordinate with the team; do not jump straight to `--force` |
| Teammates cannot push old branch | Their local history is based on pre-rewrite commits | Notify them and guide them to fetch and rebase/cherry-pick their own work |

## 22. Complete Practice Lab

Perform this in a sandbox repository or an unshared personal branch:

### Phase A — Create History With Follow-Up Commits

1. Create branch `feature/rebase-lab` from the base branch.
2. Add the model and commit `Add payment summary model`.
3. Fix a typo in the model and commit `Fix typo in payment model`.
4. Add the service and commit `Add payment calculation service`.
5. Add tests and commit `Add tests for payment calculation`.
6. Improve a log message and commit `Improve payment log message`.
7. Inspect history with `git log --oneline --graph`.

### Phase B — Back Up and Clean Up

1. Check `git status -sb` and ensure the working tree is clean.
2. Fetch the base branch.
3. Create a backup branch.
4. Run `git rebase -i <upstream>`.
5. Use `fixup` to fold the typo fix into the model commit.
6. Keep service and tests separate or combine them per review policy.
7. Use `reword` if any message does not accurately describe the change.
8. Complete the rebase and re-check the log.

### Phase C — Try Autosquash and Conflicts

1. Create a follow-up fix commit with `git commit --fixup=<commit-id>`.
2. Run `git rebase -i --autosquash <upstream>`.
3. If a conflict occurs, inspect `git status` and diffs.
4. Resolve files, stage, and run `git rebase --continue`.
5. In your sandbox repository, try `git rebase --abort` to observe returning to the pre-rebase state.

### Phase D — Verify and Hand Over

1. Compare the new tip against the backup branch.
2. Inspect `git log --oneline <upstream>..HEAD`.
3. Run tests and `git diff --check`.
4. Confirm the working tree is clean.
5. Push to a test remote or open a pull request following team workflow.
6. Keep the backup branch until handover is confirmed successful.

Do not use `--force` on shared branches during practice. To simulate an already-pushed branch, use only a test remote you control.

## 23. Pre-Handover Checklist

- [ ] On the correct feature branch.
- [ ] Working tree and index are clean.
- [ ] Fetched the latest upstream.
- [ ] Confirmed the exact `upstream..HEAD` range.
- [ ] Created a backup branch or clear recovery checkpoint.
- [ ] Reviewed which commits to keep, combine, reword, or drop.
- [ ] Todo list has a logical order.
- [ ] Resolved all conflicts with no in-progress rebase state remaining.
- [ ] Final diff against upstream matches the goal.
- [ ] Tests, linters, and quality checks pass.
- [ ] Coordinated with the team if rewriting an already-pushed branch.
- [ ] Pushed properly and updated the pull request.

## 24. Self-Check Questions

1. Why should you run `git fetch` before interactive rebase?
2. What range does `git log origin/main..HEAD` identify?
3. Why create a backup branch before rewriting history?
4. How do `pick`, `reword`, `edit`, `squash`, `fixup`, and `drop` differ?
5. Why does folding with `squash` open the editor while `fixup` drops the secondary message?
6. How does `git commit --fixup` work together with `--autosquash`?
7. When should you use `edit` instead of `reword`?
8. How do `git rebase --continue`, `--skip`, and `--abort` differ?
9. Why should you avoid unilaterally rebasing a branch others have checked out?
10. What does `--force-with-lease` protect against, and what coordination step does it not replace?
11. How do you verify the final contents did not change after combining commits?
12. Why is the fewest number of commits not always the best history?

## Conclusion

Interactive rebase turns a messy development commit sequence into a clear history before handover. Identify the right upstream, protect the current branch, apply `pick`, `reword`, `edit`, `squash`, `fixup`, and `drop` intentionally, and handle conflicts deliberately with `--continue`, `--skip`, or `--abort`. After rebasing, diff against your backup branch, run tests, and confirm a clean working tree. If the branch was already shared, coordinate with your team before updating the remote, use `--force-with-lease` per agreed process, and guide affected clones to synchronize with the updated history.

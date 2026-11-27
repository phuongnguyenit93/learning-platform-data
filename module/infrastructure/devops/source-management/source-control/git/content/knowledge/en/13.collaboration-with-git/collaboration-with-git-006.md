# Updating a Branch Under Review After Receiving Feedback

When a Pull Request (PR) or Merge Request (MR) is open, the source branch often continues changing throughout the review process. Reviewers may request logic fixes, additional tests, renames, documentation updates, or adjustments to the implementation approach. The developer must update the exact source branch so that new commits appear inside the active review request.

Git provides branch, commit, fetch, merge, rebase, and push operations to accomplish this. The key is identifying the right source branch, the remote hosting that branch, and the team's history-update policy. Creating a different branch or pushing to the wrong destination may prevent the changes from appearing in the current PR/MR.

This lesson explains how to receive feedback, make edits on the branch under review, sync when the target branch gains new commits, push updates to the right remote, and follow up on the next review round.

## 1. Understanding the Relationship Between a PR/MR and Git Branches

### 1.1. A PR/MR Tracks a Pair of Branches

A review request typically specifies:

- **Source branch:** holds the commits proposing the changes.
- **Target/base branch:** where the team plans to integrate the changes, usually `main`, `develop`, or a release branch.

For example, a PR might propose integrating:

- Source: `feature/payment-validation`
- Target: `main`

A PR/MR is a feature of code hosting platforms such as GitHub, GitLab, or similar services. Git manages commits and branches; the review platform displays diffs, comments, check statuses, and approval decisions.

When you push new commits to the exact source branch, the PR/MR tracking that branch automatically updates its diff. There is no need to open a new review request just because you modified code based on feedback.

### 1.2. Distinguishing the Local Source Branch from the Remote Source Branch

Suppose the local repository has:

- `feature/payment-validation`: the active local branch.
- `origin/feature/payment-validation`: the remote-tracking branch recording the latest fetch from the `origin` remote.
- The PR/MR is reading the `feature/payment-validation` source branch from the `origin` repository.

When you create a new commit on the local branch, the remote branch does not change until a push succeeds. After pushing, the review platform receives the new commit and updates the review request content.

You can check the current branch and tracking branch with:

~~~bash
git branch --show-current
git branch -vv
git status -sb
~~~

Do not rely on the branch name displayed in an editor UI or an old terminal window. Verify directly in the repository before making edits and pushing.

### 1.3. The Source Branch's Remote May Differ from the Target Branch's Remote

In a fork workflow, a PR may take its source branch from the `origin` fork while the target branch resides in the canonical `upstream` repository.

For example:

- `origin/feature/payment-validation`: the source branch in the fork.
- `upstream/main`: the target branch in the main repository.

When addressing review feedback, you typically push to `origin`. When pulling new changes from the target branch, you fetch from `upstream`. Clearly distinguish both remotes to avoid sending commits to the wrong repository.

Verify with:

~~~bash
git remote -v
git branch -vv
~~~

## 2. Reading and Categorizing Review Feedback

Before making edits, read all open feedback and determine the scope of work. Comments may be mandatory change requests, questions needing explanation, optional suggestions, or newly spotted bugs.

A helpful categorization:

| Feedback Type | Action Needed |
| --- | --- |
| Logic bug or incorrect behavior | Identify root cause, fix code, and retest |
| Missing edge case | Add handling and tests for that scenario |
| Missing or inadequate tests | Add, update, or rerun relevant tests |
| Naming, structure, or maintainability | Adjust according to project conventions |
| Unclear or inaccurate documentation | Update docs and examples |
| Question or ambiguous suggestion | Clarify requirements before changing behavior |

Not every comment requires a code edit. If a reviewer asks why a particular implementation was chosen, you can reply with technical reasoning and test evidence. If a suggestion alters scope or business requirements, align before expanding the work.

Keep track of items to address and tie each change to its corresponding comment. This helps ensure no feedback is missed when a PR has multiple reviewers.

## 3. Updating the Exact Source Branch Under Review

### 3.1. Checking the Working Tree Before Switching Branches

Before starting, check status:

~~~bash
git status --short --branch
git branch --show-current
git branch -vv
~~~

If there are uncommitted changes, determine which task they belong to. Commit or stash changes per team workflow before switching branches. Never run `git reset --hard` solely to clean the working tree unless any needed content is preserved.

### 3.2. Switching to the Active Source Branch

If the source branch already exists locally:

~~~bash
git switch feature/payment-validation
~~~

If the branch does not exist locally yet but exists on the remote:

~~~bash
git fetch origin
git switch --track origin/feature/payment-validation
~~~

The second command creates a local branch tracking the remote branch. Use the exact remote hosting the PR/MR's source branch. If the branch already exists locally, do not create a new branch for the same task just to address review comments.

Double-check:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

The branch name must match the review request's source branch. If the PR was opened from a fork, the source branch must belong to that exact fork repository.

### 3.3. Syncing New Commits on the Source Branch Itself

Before editing, fetch the latest state from the remote hosting the source branch:

~~~bash
git fetch origin
git status -sb
~~~

If the local branch is properly tracking `origin/feature/payment-validation`, the ahead/behind count in `git status -sb` or `git branch -vv` reveals whether the two sides differ.

You can view commits unique to either side:

~~~bash
git log --oneline --left-right HEAD...origin/feature/payment-validation
~~~

The `<` and `>` symbols distinguish commits present on only one side. If the remote branch has new commits from someone else, inspect and integrate them before proceeding. Do not overwrite a teammate's commits simply because your local branch has an older state.

If only you manage the branch and the remote has no new commits, you can begin editing directly on the local branch.

## 4. Addressing Feedback and Creating Commits

### 4.1. Making Small, Purposeful Changes

Address related groups of feedback together. For example, if a reviewer asks for input validation and additional tests, a single commit can include both the logic fix and its corresponding tests.

Before editing, you can inspect the branch diff:

~~~bash
git diff origin/feature/payment-validation...HEAD
~~~

After editing, check modified files:

~~~bash
git status
git diff
~~~

If there are multiple independent pieces of feedback, consider separating them into distinct commits. Clear history helps reviewers see which change addresses which comment.

### 4.2. Running Appropriate Tests

Do not rely solely on the code compiling successfully. Choose tests based on the type of change:

- Logic fix: run relevant unit tests and regression tests.
- Added edge case: run new tests alongside existing tests.
- API or contract change: check callers and related documentation.
- Configuration or build change: run appropriate build checks.
- Documentation change: verify paths, commands, and examples remain accurate.

Record test results so you can report back to reviewers. If tests cannot run in the current environment, explicitly state that limitation when replying.

### 4.3. Staging and Committing Changes

Inspect content before staging:

~~~bash
git diff
git status --short
~~~

Stage the relevant files:

~~~bash
git add src/PaymentValidator.java
git add src/test/PaymentValidatorTest.java
~~~

Inspect staged content:

~~~bash
git diff --cached
git status
~~~

Create a commit with a clear, purposeful message:

~~~bash
git commit -m "Handle empty payment reference"
~~~

Adding follow-up commits after review is usually easiest to track because earlier commits remain intact and reviewers can inspect the new updates separately. If the team requires a compact history, commits can be squashed at integration time per agreed workflow.

### 4.4. Should You Amend the Old Commit?

`git commit --amend` replaces the last commit with a new commit. This is useful when fixing a minor mistake in an unshared local commit or when the team requires preparing history before pushing.

~~~bash
git add src/PaymentValidator.java
git commit --amend
~~~

If the commit has already been pushed to a source branch that reviewers or teammates are tracking, amending rewrites history and changes the commit hash. Updating the remote afterward requires a force push. This can drop someone else's new commits if not coordinated.

For a branch actively under review, the least disruptive approach is usually creating a new commit for the feedback. Only amend or squash already-shared commits when team process allows it and everyone working on the branch agrees.

## 5. Pushing Updates to the Right Branch So the PR/MR Refreshes

### 5.1. Checking Remote and Upstream

Before pushing:

~~~bash
git branch --show-current
git branch -vv
git remote -v
git status -sb
~~~

Confirm:

- The current branch is the PR/MR's source branch.
- The push remote is the repository containing the source branch.
- Upstream points to the right remote branch if you plan to run a bare push command.
- The new commits are the exact changes you intend to share.

In a fork workflow, the push remote is typically `origin`, while the remote for the target branch may be `upstream`.

### 5.2. Pushing to the Same Source Branch

If upstream is already configured properly:

~~~bash
git push
~~~

If you want to specify the destination explicitly:

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

This command uses `HEAD` as the source and spells out the full remote branch ref as the destination. It clearly indicates that the current commit updates the `feature/payment-validation` source branch on `origin`.

If this is the first time pushing the branch to the remote and you want to set upstream:

~~~bash
git push -u origin HEAD:refs/heads/feature/payment-validation
~~~

After a successful push, the review platform automatically adds the new commits to the active PR/MR because the source branch remains unchanged. If no update appears, check the source repository, branch name, push permissions, and platform sync status.

### 5.3. Do Not Create a New PR/MR for the Same Branch

If the current review request is still open and you continue working on that source branch, new commits update the existing review request. Opening another PR/MR for the same change creates duplicate review threads and makes it confusing for reviewers to know where to respond.

Only create a new review request when the team intentionally splits scope, changes the source branch, or the workflow requires an independent request.

## 6. Updating the Source Branch When the Target Branch Gains New Commits

During review, the target branch such as `main` may continue receiving commits. The source branch may then need to integrate new changes to resolve conflicts or rerun tests against the updated base.

Two common approaches exist: merging the target branch into the source branch or rebasing the source branch onto the target branch. Choose based on team convention and whether the source branch is shared.

### 6.1. Merge Approach — Preserving Shared Commits

Suppose the target branch is `main` on `upstream`, while the source branch resides on `origin`:

~~~bash
git fetch upstream
git switch feature/payment-validation
git merge upstream/main
~~~

If conflicts occur, resolve the content and stage the handled files:

~~~bash
git status
git add src/PaymentValidator.java
git merge --continue
~~~

Rerun tests and inspect history:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

Then push the merge commit and changes to the source branch:

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

Merge creates a commit recording the integration of the two history lines when a fast-forward is not possible. Because already-shared commits remain untouched, this approach is usually easier to coordinate when multiple people use the source branch.

### 6.2. Rebase Approach — Replaying Source Branch Commits on a New Base

Rebase replays the source branch's commits onto a new base commit, generating new commit hashes for the replayed commits.

Before rebasing an already-pushed branch, update both the remote hosting the source branch and the remote hosting the target branch. Check whether the remote source branch has new commits missing locally:

~~~bash
git fetch origin
git fetch upstream
git switch feature/payment-validation
git log --oneline --left-right HEAD...origin/feature/payment-validation
~~~

If the remote has commits not yet integrated locally, inspect them and coordinate with whoever is working on the branch. Integrate those commits or agree on how to proceed before rewriting history. Never use force push to discard uninspected remote commits.

After confirming the source branch is synced and the target branch has been fetched, perform the rebase:

~~~bash
git rebase upstream/main
~~~

If conflicts occur:

1. Check conflicted files with `git status`.
2. Edit the content to keep the right outcome.
3. Stage resolved files with `git add`.
4. Continue with `git rebase --continue`.

~~~bash
git status
git add src/PaymentValidator.java
git rebase --continue
~~~

If you need to cancel the entire ongoing rebase:

~~~bash
git rebase --abort
~~~

After a successful rebase, rerun tests and inspect history. Because commits were replayed, the remote source branch may no longer be an ancestor of local history. If the branch was pushed earlier, updating the remote usually requires:

~~~bash
git push --force-with-lease origin HEAD:refs/heads/feature/payment-validation
~~~

Use this only when the team permits rewriting source branch history and you have checked the latest remote branch. `--force-with-lease` rejects the update if the remote branch changed since the fetch used as the condition. However, it does not detect if you fetched a remote commit without integrating it locally; therefore, checking divergence before rebasing is mandatory. If multiple people push to the source branch, coordinate before rebasing and force pushing.

### 6.3. Choosing Merge or Rebase?

| Criterion | Merge | Rebase |
| --- | --- | --- |
| Shared commit history | Preserves existing commits | Recreates replayed commits |
| Representing target branch integration | Creates a merge commit when needed | Produces a more linear history |
| Collaborating on the same source branch | Usually less disruptive | Requires coordination when force pushing |
| Conflict resolution | Handled once during the merge | May need to be resolved commit by commit |
| Team convention | Fits teams preserving integration history | Fits teams requiring linear history |

No choice fits every repository. Follow the project's review and integration policy. Avoid rebasing a shared branch without aligning with everyone working on it.

## 7. Following Up on the Next Review Round

After pushing, return to the PR/MR and verify:

- New commits appear in the review request's commit list.
- The current diff accurately reflects the edits made for feedback.
- Relevant comments can be marked resolved after the corresponding changes are pushed.
- Threads needing explanation have received replies.
- Automated CI, builds, and tests have rerun on the new commits.
- Reviewers can inspect the new updates without hunting in a different branch.

Do not mark a comment as resolved merely because you fixed it locally. Confirm the changes are pushed and meet the requirement. If you disagree with a piece of feedback, explain your reasoning and cite evidence such as tests, documentation, or agreed technical decisions.

If CI fails after updating, read the logs to determine whether the failure comes from the new commits, changes in the target branch, or the test environment. Fix it on the same source branch, create a follow-up commit, and push again to update the PR/MR.

## 8. Complete Example: Addressing Feedback and Updating a PR

Suppose a PR proposes merging `feature/payment-validation` into `main`. A reviewer notices the payment reference validation function does not handle empty strings and requests additional tests.

**Step 1 — Switch to the source branch and fetch the latest state**

~~~bash
git fetch origin
git switch feature/payment-validation
git status -sb
git branch -vv
~~~

**Step 2 — Fix the logic and add tests**

After updating `PaymentValidator` and `PaymentValidatorTest`, check the diff:

~~~bash
git diff
git status --short
~~~

**Step 3 — Run relevant tests**

~~~bash
./gradlew test
~~~

This command is an example for a Gradle project; run your repository's actual test command.

**Step 4 — Create a commit for the feedback**

~~~bash
git add src/PaymentValidator.java
git add src/test/PaymentValidatorTest.java
git diff --cached
git commit -m "Reject empty payment reference"
~~~

**Step 5 — Push to the exact source branch**

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

**Step 6 — Verify the PR**

Reopen the active PR, confirm the new commit and diff are updated, wait for CI to complete, and reply to the reviewer detailing the empty-string handling and added tests.

If the target branch gained new commits during review, the team can merge or rebase per policy. Afterward, rerun tests and push to the same source branch.

## 9. Common Mistakes

- **Editing on a branch other than the source branch:** commits do not appear in the open PR/MR. Check `git branch --show-current` before working.
- **Creating a new PR/MR for every fix:** fragments reviews and comments. Keep pushing to the active request's source branch.
- **Pushing to the target branch's remote instead of the source branch's remote:** sends changes to the wrong repository. Check `git remote -v` and `git branch -vv`.
- **Amending shared commits without coordination:** changes commit hashes and forces rewriting remote history. Prefer follow-up commits unless the team agrees otherwise.
- **Force pushing after rebase without checking the remote:** can overwrite others' new commits. Fetch, inspect divergence, and use `--force-with-lease` per workflow.
- **Marking comments resolved before pushing:** reviewers cannot yet verify changes on the review branch. Wait until the push succeeds before updating comment status.
- **Not rerunning tests:** new commits can introduce regressions or conflict with target branch changes. Run appropriate tests and monitor CI.
- **Bundling unrelated feedback into one large commit:** harder for reviewers to inspect. Split commits by purpose when it improves history clarity.

## 10. Quick Reference Table

| Need | Command |
| --- | --- |
| Check current branch | `git branch --show-current` |
| View upstream and ahead/behind state | `git branch -vv` |
| View remotes | `git remote -v` |
| Fetch updates from source remote | `git fetch origin` |
| Switch to source branch | `git switch feature/payment-validation` |
| Compare differing commits against remote branch | `git log --oneline --left-right HEAD...origin/feature/payment-validation` |
| View unstaged changes | `git diff` |
| View staged changes | `git diff --cached` |
| Push to the exact source branch | `git push origin HEAD:refs/heads/feature/payment-validation` |
| Merge target branch into source branch | `git merge upstream/main` |
| Rebase source branch onto target branch | `git rebase upstream/main` |
| Continue rebase after resolving conflicts | `git rebase --continue` |
| Abort an ongoing rebase | `git rebase --abort` |
| Push after rebase under approved workflow | `git push --force-with-lease origin HEAD:refs/heads/feature/payment-validation` |

## 11. Summary

When receiving review feedback, return to the PR/MR's exact source branch, fetch the latest remote status, address feedback by related group, run tests, and create clear, purposeful commits. Push new commits to the same source branch so the active review request updates automatically.

If the target branch has new changes, choose merge or rebase according to team convention. Merge preserves shared history; rebase recreates commits and requires coordination when updating an already-pushed branch. After each update, verify the diff, CI, and comments so reviewers can confirm the changes are complete.

An effective review round is a continuous loop: receive feedback, update the branch, run tests, push, and re-verify on the review request. Keeping the right source branch and understandable history enables teams to collaborate without losing the context of prior decisions.

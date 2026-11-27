# Preparing a Focused Commit Around One Meaningful Change

A good commit is a unit of change that can be read, tested, reviewed, and reverted with minimal guesswork. When a commit bundles multiple unrelated tasks, reviewers struggle to understand its intent, bugs become harder to trace, and reverting part of it can pull along unintended changes. Conversely, splitting every edited line into tiny, fragmented commits also makes history difficult to follow.

The goal is to create a commit focused on **one meaningful, cohesive change**. A commit may include source code, tests, documentation, and configuration if they all serve the same objective. Independent tasks such as bulk reformatting, upgrading unrelated dependencies, or fixing a separate bug should be split apart.

This lesson explains how to define scope, choose what goes into the index, stage by file or hunk, inspect the snapshot to be committed, run appropriate tests, and write a message that helps readers understand the change.

## 1. What Makes a Commit Focused?

### 1.1. A Commit Is an Understandable Unit of Change

A focused commit answers the question: **What does this commit change, and why is that change needed?**

Examples of a clear objective:

- Add billing address validation before creating an order.
- Fix total rounding error when applying a discount code.
- Update the environment variable configuration guide for the service.
- Change the client timeout to handle an identified connection error.

A commit can modify multiple files if they are necessary parts of the same change. For example, adding billing address validation might require:

- Input validation code.
- Unit tests for valid and invalid cases.
- API tests verifying the response.
- API documentation if the external contract changes.

These files belong to the same objective, so they can live in a single commit.

### 1.2. Distinguish Related Changes from Coincidental Changes

While working on a feature, you might spot a typo in another document, an old log file, or a code snippet that needs formatting. Not every change present in the working tree belongs in the same commit.

For example:

| Change | Should It Go Into the Address Validation Commit? | Reason |
| --- | --- | --- |
| Validation for the address | Yes | It is the core part of the objective |
| Unit tests for validation | Yes | Proves the new behavior |
| API tests for error responses | Yes | Verifies the API contract |
| Documentation describing required address fields | Yes | Updates how the feature is used |
| Reformatting an entire unrelated module | No | Hard to review and unnecessary for the objective |
| Fixing a logging bug in another service | No | Independent piece of work |
| Upgrading an unrelated dependency | No | Increases the commit's scope and risk |

This is a principle about relevance, not a rule about file count. A commit can modify many files or just one; what matters is that readers can see how they work together toward one outcome.

### 1.3. Keep Required Dependent Parts in the Same Commit

Sometimes a change cannot build or pass tests without an accompanying piece. For example, updating an API may require updating the interface, implementation, tests, and generated lockfile because a required dependency changed. If these parts need one another to form a consistent state, keep them in the same commit.

Do not split a commit to the point where intermediate commits fail to build, fail tests, or create states that cannot be reviewed independently, unless the project has a clear convention for such commit chains.

### 1.4. Self-Check Scope in One Sentence

Before staging, try describing the commit in a single sentence:

- "Add billing address validation before creating an order."
- "Fix total calculation when percentage discounts are applied."
- "Add instructions for running migrations in the staging environment."

If you have to use multiple unrelated sentences to describe one commit, consider splitting it into separate commits.

## 2. Inspect All Changes Before Choosing Commit Scope

### 2.1. Confirm the Branch and Repository State

Start with:

~~~bash
git status --short --branch
git branch --show-current
git log -1 --oneline
~~~

These commands tell you:

- Which branch you are on.
- Whether there are staged, unstaged, or untracked changes.
- Which commit is currently checked out.

If you are in a detached HEAD state or on the wrong branch, stop and verify the workflow before committing. Do not create a commit on the wrong branch just because the working tree has content you want to save.

### 2.2. View the List of Changed Files

~~~bash
git status
git diff --name-status
git diff --cached --name-status
git ls-files --others --exclude-standard
~~~

Meaning:

- git diff --name-status: tracked files with unstaged changes compared to the index.
- git diff --cached --name-status: staged changes compared to HEAD.
- git ls-files --others --exclude-standard: untracked files that are not ignored.

View statistics:

~~~bash
git diff --stat
git diff --cached --stat
~~~

The file list helps catch out-of-scope changes before reading details.

### 2.3. Read Unstaged Changes

~~~bash
git diff
~~~

This command displays differences between the working tree and the index. Use it to understand what is on disk but not yet staged.

Limit to one file:

~~~bash
git diff -- src/BillingService.java
~~~

You can also use:

~~~bash
git diff --word-diff
~~~

to observe changes at the word or token level, which is useful for documentation or long configuration lines.

### 2.4. Read Staged Changes

~~~bash
git diff --cached
~~~

This is a critical step because a regular commit takes content from the index, not the entire working tree.

If you staged changes earlier, do not assume the staged portion still belongs to the current task. Re-read the entire staged diff to catch leftover files or changes from previous work.

### 2.5. Compare All Changes Against HEAD

~~~bash
git diff HEAD
~~~

This command shows the total difference of both the working tree and the index compared to the current commit. It is useful for getting the big picture before selecting what goes into the commit.

However, to know the exact content of the next commit, you still need to check git diff --cached because that is the snapshot currently in the index.

## 3. Plan Commit Scope Before Staging

### 3.1. Write Down the Objective and Required Parts

For example, objective: "Add billing address validation before creating an order".

The list might include:

~~~text
src/order/CheckoutService.java
src/order/AddressValidator.java
test/order/CheckoutServiceTest.java
docs/api/checkout.md
~~~

Each file has a reason to be in the commit:

- CheckoutService calls the validator.
- AddressValidator contains the validation rules.
- Tests verify the behavior.
- Documentation describes the address requirement.

If git status also shows an IDE configuration file or a formatting change in another module, do not stage it just because it happens to be there.

### 3.2. Separate Independent Changes

Suppose you simultaneously:

1. Fix an address validation bug.
2. Reformat all whitespace in the module.
3. Bump the version of an unrelated dependency.

These three tasks can be reviewed and tested independently. Prepare separate commits for each objective if the project needs all three.

If a formatting change is a prerequisite for performing a refactor or bug fix, explain the relationship and consider keeping the required part in the same commit. Do not split mechanically by file type.

### 3.3. Do Not Separate Tests from the Behavior They Protect

A commit that adds validation without corresponding tests can be hard to review and prone to regressions. If tests are needed to prove the change, include them in the same commit.

Similarly, when changing a public API or configuration approach, update the necessary documentation in the same commit so the snapshot represents a complete change.

## 4. Stage the Right Content with git add

### 4.1. Stage Related Files by Path

When changes are cleanly separated into files:

~~~bash
git add -- src/order/CheckoutService.java
git add -- src/order/AddressValidator.java
git add -- test/order/CheckoutServiceTest.java
git add -- docs/api/checkout.md
~~~

You can stage multiple paths at once:

~~~bash
git add -- src/order/CheckoutService.java src/order/AddressValidator.java test/order/CheckoutServiceTest.java docs/api/checkout.md
~~~

The -- marker ends options parsing, preventing paths starting with a hyphen from being misinterpreted as options.

Staging by path works well when each file contains changes for only one objective.

### 4.2. Understand the Scope of git add -A and git add -u

~~~bash
git add -A
~~~

updates the index for all changes in the working tree: additions, modifications, and deletions. Without a pathspec, the scope is the entire working tree.

~~~bash
git add -u
~~~

stages modifications and deletions of already-tracked paths; it does not add new untracked files.

You can narrow the scope:

~~~bash
git add -A -- src/order/
git add -u -- src/order/
~~~

When aiming for a focused commit, avoid running git add -A out of habit before reviewing the change list. It can pull unrelated files into the index.

### 4.3. Stage Selectively with git add -p

A single file can contain multiple changes belonging to different objectives. In that case, staging the whole file puts every hunk into the same commit.

Use:

~~~bash
git add -p -- src/order/CheckoutService.java
~~~

Git displays each hunk and asks how you want to handle it. Common choices:

| Choice | Effect |
| --- | --- |
| y | Stage the current hunk |
| n | Skip the current hunk |
| s | Split the hunk if possible |
| e | Manually edit the patch |
| q | Quit interactive mode |
| ? | Show help for choices |

For example, CheckoutService contains both a validation change and an unrelated debug log snippet. You can stage the validation hunk, skip the log hunk, and handle the log in a separate commit.

After finishing, verify:

~~~bash
git diff --cached -- src/order/CheckoutService.java
git diff -- src/order/CheckoutService.java
~~~

The first command shows what was selected; the second shows what remains unstaged.

### 4.4. Split Hunks for More Precise Selection

If a hunk contains multiple changed lines and Git can split it down, choose s in git add -p mode.

If Git cannot split it automatically, you can:

- Choose to stage the whole hunk if every line is related.
- Use e to edit the patch if you understand patch format.
- Reorganize changes in the working tree into pieces that are easier to stage.

Avoid manually editing patches unless you understand context lines, plus/minus markers, and hunk headers. A malformed patch may be rejected or create a snapshot different from what you intended.

### 4.5. Stage an Edited Patch Using an Editor

~~~bash
git add -e -- src/order/CheckoutService.java
~~~

This command opens the patch in your editor so you can adjust which lines will be staged. This is an advanced technique, useful when you need to select exact portions of a change within a file.

After saving the patch, Git validates and applies it to the index. Check immediately:

~~~bash
git diff --cached -- src/order/CheckoutService.java
git diff -- src/order/CheckoutService.java
~~~

Do not assume an edited patch reflects your intent simply because Git accepted it.

## 5. Inspect and Adjust the Index

### 5.1. View the Exact Files That Will Be Committed

~~~bash
git diff --cached --name-only
git diff --cached --name-status
~~~

Read this list and confirm every path belongs to the commit objective.

View statistics:

~~~bash
git diff --cached --stat
~~~

If there is an unrelated file, unstage just that file:

~~~bash
git restore --staged -- path/to/unrelated-file
~~~

This command resets the index entry to HEAD's state for that path while keeping the content in the working tree. The file will continue to appear as modified or untracked depending on its initial state.

### 5.2. Review the Patch That Will Be Committed

~~~bash
git diff --cached
~~~

Read the entire patch, not just the top or statistics. Check:

- Does the logic match the objective?
- Are there debug lines or experimental code?
- Are there unnecessary formatting changes?
- Are there auto-generated or temporary files?
- Are there passwords, tokens, private keys, or personal data?
- Was any file deleted by mistake or a related update missed?
- Do tests accurately reflect the new behavior?

If the commit contains binary files, the diff may not display content. Check the filename, size, file type, and data source before committing.

### 5.3. Check for Whitespace Errors

~~~bash
git diff --cached --check
~~~

This command checks for common whitespace errors in the staged patch, such as trailing whitespace or problematic newlines. It does not replace a formatter, linter, or code review.

### 5.4. Check the Unstaged Portion as Well

~~~bash
git diff
git status --short
~~~

The unstaged portion may be changes you intentionally set aside for a later commit. Confirm they do not mislead you into thinking the current commit already includes everything visible in your editor.

If a file has both staged and unstaged changes, short status may show MM or corresponding markers. Read both columns to distinguish changes in the index from additional changes in the working tree.

### 5.5. Remove a File from Staging

If you accidentally staged an entire file:

~~~bash
git restore --staged -- src/UnrelatedService.java
~~~

If you only want to unstage specific hunks, you can use:

~~~bash
git restore --staged -p -- src/order/CheckoutService.java
~~~

In older Git versions, you can use:

~~~bash
git reset -p HEAD -- src/order/CheckoutService.java
~~~

These commands modify the index; they are not meant to delete working tree content. After unstaging, review both git diff and git diff --cached.

## 6. Test the Exact Changes to Be Committed

### 6.1. Choose Tests Appropriate for the Scope

A focused commit should have corresponding test evidence. For example:

- Handler function changes: run relevant unit tests.
- API changes: run appropriate API/integration tests.
- Migration changes: verify the migration on a test database.
- Build configuration changes: run the build or configuration verification task.
- Documentation changes: check links, syntax, or documented commands if applicable.

Not every commit needs to run the entire test suite. Choose tests sufficient to verify the objective and clearly note limitations if some tests were not run.

### 6.2. Test After Staging

A good workflow is to stage the relevant changes, review the patch, and then run tests before committing. This ensures you know the exact snapshot destined for history.

However, if a file has both staged and unstaged changes, test runners typically read from the working tree, meaning they may include unstaged edits. In that case, test results do not necessarily prove that the exact snapshot in the index works.

### 6.3. Isolate Unstaged Changes When Precise Testing Is Needed

If you have staged specific hunks and want to test the exact staged version, you can temporarily stash the rest:

~~~bash
git stash push --keep-index -u -m "Temporarily save unstaged work"
~~~

The --keep-index option keeps staged changes in both the index and the working tree; unstaged changes along with untracked files (when using -u) are moved into the stash. Then run tests against the remaining content in the working tree.

Once testing is complete, restore the stashed work:

~~~bash
git stash pop
~~~

Note that stash pop can produce conflicts if the repository state changed. Check git status before and after the operation; do not drop the stash until you confirm the changes have been restored.

If your workflow does not require staging individual hunks within the same file, a simpler approach is to finish one group of changes, stage and test it, before starting the next group.

### 6.4. Re-check After Hooks Modify Content

A repository may have pre-commit hooks or automatic formatting/linting tools configured. Some hooks only validate; others modify files or the index.

After running a commit or hook, re-check:

~~~bash
git status
git diff
git diff --cached
~~~

If a hook modified content, inspect the diff, stage what is needed, and re-run appropriate checks before creating the final commit.

## 7. Write a Clear Commit Message

### 7.1. The Subject Should Describe the Change

A commit message with a concise subject helps readers understand the goal directly in the log.

Good example:

~~~text
Validate billing address before checkout
~~~

Some unclear examples:

~~~text
Update code
Fix bug
Changes
Work in progress
~~~

The subject should use an active imperative verb describing the action or outcome. You do not need to put every implementation detail into the first line.

### 7.2. Use the Body to Explain the Why

When a change needs more context, use the body:

~~~text
Validate billing address before checkout

Reject checkout requests when the billing address is missing
or incomplete. This prevents orders from being created with
unusable billing information.

Add unit and API tests for valid and invalid address cases.
~~~

The body should explain why the change is needed, what behavior changed, and what reviewers should pay attention to. Do not repeat the subject in different words.

### 7.3. Follow a Consistent Subject Convention

Some teams use Conventional Commits:

~~~text
feat: validate billing address before checkout
fix: round discounted totals correctly
docs: explain staging deployment settings
test: cover invalid checkout addresses
~~~

This is an optional project convention, not a mandatory Git requirement. If the repository already has a CONTRIBUTING.md or commit convention, follow your team's rules.

Common recommendations:

- Use a short, readable subject line for logs.
- Avoid a trailing period on the subject unless team convention requires it.
- Use the body for rationale and context.
- Reference issues or tickets in the project's format when appropriate.
- Avoid putting secrets or personal data in commit messages.

### 7.4. Create a Commit with -m or an Editor

Single-line commit:

~~~bash
git commit -m "Validate billing address before checkout"
~~~

Commit with a body:

~~~bash
git commit -m "Validate billing address before checkout" -m "Reject incomplete addresses before creating an order. Add unit and API coverage for invalid input."
~~~

Or open the editor:

~~~bash
git commit
~~~

The editor lets you write a multi-line subject and body. Git normally treats the first line as the subject; a blank line separates the subject from the body.

### 7.5. Check Commit Identity

If Git reports missing author identity, check:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Configure for the current repository:

~~~bash
git config user.name "Developer Name"
git config user.email "developer@example.com"
~~~

Only use the identity details required by your organization or project. Do not put personal emails or private information into the repository if policy requires a no-reply address.

## 8. Create the Commit and Verify the Result

### 8.1. Final Check Before Committing

~~~bash
git status
git diff --cached --name-status
git diff --cached --check
git diff --cached
~~~

Confirm:

- Right branch.
- Right files and hunks.
- No leftover debug content or secrets.
- Appropriate tests have been run.
- Commit message accurately describes the objective.

### 8.2. Create the Commit

~~~bash
git commit -m "Validate billing address before checkout"
~~~

Git creates the commit from the current index. Changes that only exist in the working tree and have not been staged are not included in the commit.

### 8.3. Verify the New Commit

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
git status --short --branch
~~~

Review the commit to confirm the right content was recorded. If unstaged or untracked changes remain, they will still show up in the repository status after the commit.

### 8.4. Committing Does Not Mean Pushing

git commit records a snapshot in local history. It does not automatically send the commit to a remote.

Only once you have reviewed and are ready to share should you push according to your team's workflow:

~~~bash
git push
~~~

Focused commits make it easier for others to review after you push or open a pull request.

## 9. Practical Example: Separating One Change from Work in Progress

Suppose you are working on the checkout feature and the working tree has these changes:

~~~text
 M src/order/CheckoutService.java
 M src/order/AddressValidator.java
 M test/order/CheckoutServiceTest.java
 M docs/api/checkout.md
 M src/report/MonthlyReport.java
?? tmp/request-dump.txt
~~~

The current commit objective is adding billing address validation. The MonthlyReport changes and the dump file do not belong to this objective.

### Step 1 — Inspect diffs and define scope

~~~bash
git diff -- src/order/CheckoutService.java
git diff -- src/order/AddressValidator.java
git diff -- test/order/CheckoutServiceTest.java
git diff -- docs/api/checkout.md
git diff -- src/report/MonthlyReport.java
~~~

Confirm the dump file does not contain data that needs saving. Do not stage the temporary file.

### Step 2 — Stage related files

~~~bash
git add -- src/order/CheckoutService.java src/order/AddressValidator.java test/order/CheckoutServiceTest.java docs/api/checkout.md
~~~

### Step 3 — Inspect the staged snapshot

~~~bash
git diff --cached --name-status
git diff --cached
git diff --cached --check
~~~

If MonthlyReport content or tmp/request-dump.txt appears in the staged diff, unstage it or fix the scope before proceeding.

### Step 4 — Run tests

For example:

~~~bash
./gradlew test --tests "com.example.order.CheckoutServiceTest"
~~~

Choose the task and test name matching the actual project. If tests depend on other unstaged changes, isolate them or explicitly note testing limitations.

### Step 5 — Commit

~~~bash
git commit -m "Validate billing address before checkout"
~~~

### Step 6 — Verify what remains

~~~bash
git status --short
git show --stat --oneline HEAD
~~~

The MonthlyReport changes and temporary file are not part of the commit. They remain in the working tree to be handled in separate work.

## 10. Common Mistakes

- **Staging everything out of habit:** git add -A can pull unrelated changes into the index. Check status and diff before staging.
- **Only checking the file list without reading the patch:** one file can contain multiple different objectives. Use git diff --cached to read the actual content.
- **Separating tests from the feature:** the commit may fail to prove the new behavior. Keep related tests in the same unit of change.
- **Mixing broad reformatting with logic fixes:** reviews struggle to distinguish functional changes. Separate independent formatting unless required for the objective.
- **Assuming commit grabs everything in the editor:** a regular commit takes the index. Check the staged diff before committing.
- **Ignoring unstaged changes in the same file:** a file can contain both a staged version and new edits. Check both git diff and git diff --cached.
- **Running tests on the working tree and assuming the staged snapshot was tested:** when the same file has unstaged edits, tests may run against the unstaged portion too.
- **Overly vague commit messages:** readers cannot understand the goal or reason. Write a specific subject and a body when needed.
- **Committing secrets:** review diffs to avoid leaking tokens, passwords, private keys, or sensitive data.
- **Assuming a commit is already shared:** a commit stays only in local history until pushed or exchanged by another mechanism.

## 11. Pre-Commit Checklist

- [ ] Confirmed branch and change objective.
- [ ] Can describe the commit in one clear sentence.
- [ ] All files in the commit serve the same objective.
- [ ] Independent changes have been separated.
- [ ] Checked both staged and unstaged diffs.
- [ ] Staged the exact files or hunks needed.
- [ ] Read the entire git diff --cached.
- [ ] Checked whitespace with git diff --cached --check.
- [ ] No debug code, temporary files, secrets, or unnecessary data.
- [ ] Ran appropriate tests, build, or checks.
- [ ] If unstaged parts exist in the same file, understood what content tests ran against.
- [ ] Commit message clearly describes the action and rationale.
- [ ] Re-checked git show and git status after committing.

## 12. Quick Reference Table

| Goal | Command |
| --- | --- |
| View branch and status | git status --short --branch |
| View unstaged changed files | git diff --name-status |
| View staged files | git diff --cached --name-status |
| View all changes compared to HEAD | git diff HEAD |
| Stage a specific file | git add -- path/to/file |
| Stage all changes | git add -A |
| Stage changes to tracked files | git add -u |
| Stage by hunk | git add -p -- path/to/file |
| Edit patch before staging | git add -e -- path/to/file |
| View staged patch | git diff --cached |
| Check whitespace | git diff --cached --check |
| Unstage an entire file | git restore --staged -- path/to/file |
| Unstage by hunk | git restore --staged -p -- path/to/file |
| Temporarily stash unstaged work for testing | git stash push --keep-index -u |
| Restore stashed work | git stash pop |
| Create a commit with subject | git commit -m "message" |
| View the newly created commit | git show --stat --oneline HEAD |
| Check status after commit | git status --short --branch |

## 13. Summary

A focused commit gathers the changes needed to produce a single cohesive result that can be understood, reviewed, tested, and reverted. Start by defining the objective, inspecting all changes, separating independent parts, and then staging the right files or hunks.

Before committing, read git diff --cached, check whitespace, run appropriate tests, and write a message that clearly describes the action and rationale. Remember that a commit takes content from the index; whatever remains in the working tree is not automatically included in history.

A history with clear commits makes code review, root-cause analysis, cherry-picking, and reverting much easier to control. Commit quality is determined by the cohesion of the change, not by the number of files or changed lines.

# Preparing Small Change Branches for Easy Review

## Why Keep Change Branches Small in Scope?

In a development team, a Git branch typically serves as a collection of commits for a single piece of work before being integrated into a shared branch. When a branch contains a change with a clear objective, reviewers can understand the problem, trace the solution, and verify behavior much faster.

A small change branch usually has these characteristics:

- Solves a single objective or unit of work that can be described in one sentence.
- Modifies only the components necessary to achieve that objective.
- Includes tests or evidence verifying the relevant behavior.
- Does not mix unrelated tasks such as upgrading dependencies, reformatting the entire codebase, or performing mass renames.
- Has commits and descriptions clear enough for others to understand the change.

For example, a request to "add a creation date filter to the report export screen" may require updating the API, query handling, UI, and tests. Those changes all serve one outcome, so they can live in a single branch. If while working you discover the framework needs a system-wide upgrade, that is usually a separate task and should be split out for independent review.

**Small does not mean minimal lines at any cost.** A change that requires many lines to implement properly and include thorough tests can still be easy to review if every part serves the same goal. Conversely, a change of only a few lines that does multiple unrelated things can be hard to evaluate.

## Defining Scope Before Creating a Branch

Before editing code, express the desired outcome in one concrete sentence. Then identify what needs to change and how to prove the result.

Example:

| Item | Example |
|---|---|
| Objective | Allow filtering reports by creation date |
| Code scope | Request filter, report query, and export screen |
| Testing | Data within date range, outside date range, and empty results |
| Documentation | Update parameter descriptions if the public API changes |
| Out of scope | Upgrading the framework or reformatting the entire module |

A clear scope helps answer three questions before starting:

1. What change will the user or system receive?
2. Which files or components actually need modification to achieve that outcome?
3. What checks demonstrate that the change works properly and does not break existing behavior?

If you cannot answer these questions yet, clarify the requirements or break the work into smaller steps before creating a branch.

### Knowing Which Changes Belong Together vs. Apart

Keep parts in the same branch when they depend directly on each other to form a complete behavior. For instance, updating source code, corresponding tests, and documentation describing that exact feature usually belong to the same scope.

Split into separate branches when changes can be deployed or reviewed independently, for example:

- One change fixes an authentication bug, another upgrades a library version.
- One change adds a data field, another cleans up formatting across an entire module.
- One change fixes a release-blocking bug, another adds an unrelated new feature.

If two parts are tightly coupled, do not split them mechanically just to reduce line count. Prioritize a complete unit of change that can be understood and tested.

## Checking the Repository Before Branching

Start by checking your current location and status:

~~~bash
git status
git branch --show-current
git branch --list
~~~

The `git status` command shows whether the working tree has uncommitted changes. If there is work in progress, clarify whether it belongs to the current request or another task. Avoid pulling unrelated changes into the new branch.

If the working tree has independent changes, finish or isolate them according to team workflow before switching branches. You can use a separate worktree when working on multiple tasks in parallel; avoid casually stashing changes and forgetting what was saved.

Identify the target branch the team uses for integration, usually `main` or a designated development branch. Do not assume every project uses `main`.

## Updating the Base Branch and Creating a Task Branch

A new branch should start from the latest version of the base branch to minimize unnecessary differences during review and integration.

For example, if the team uses `main` as the integration branch and the remote is named `origin`:

~~~bash
# Check the working tree before switching branches
git status

# Fetch updates from the remote
git fetch origin

# Switch to the base branch
git switch main

# Update main via fast-forward
git pull --ff-only origin main

# Create a branch for a specific objective
git switch -c feature/123-add-export-date-filter
~~~

The `--ff-only` option tells Git to update only if it can advance via fast-forward. If the local `main` branch has its own commits and cannot fast-forward, Git stops instead of automatically creating a merge commit. In that case, inspect the history and handle it according to team convention.

You can create a branch directly from a remote-tracking branch after fetching:

~~~bash
git fetch origin
git switch -c feature/123-add-export-date-filter origin/main
~~~

This is useful when you want to start from the exact current state of `origin/main`. Replace the remote and base branch names in the example with your project's actual names.

### Naming Branches Clearly

Branch names should help other team members identify the type of work and objective without opening the code. Some common conventions:

| Prefix | Purpose | Example |
|---|---|---|
| feature/ | New feature | feature/123-add-export-filter |
| fix/ | Bug fix | fix/245-handle-empty-report |
| docs/ | Documentation | docs/update-branch-guide |
| refactor/ | Refactoring | refactor/report-query |
| test/ | Adding or fixing tests | test/report-permission-cases |
| chore/ | Maintenance work | chore/update-build-plugin |

These are naming conventions, not mandatory Git syntax. Follow your repository's policy. If the team uses issue or ticket IDs, including the ID helps link the branch to the work item.

Avoid generic names such as `temp`, `test`, `update`, or `fix-final`. A branch with a specific name makes communication, searching, and cleanup after merging much easier.

## Making Changes in Small Steps

After creating the branch, verify you are on the right branch:

~~~bash
git branch --show-current
git status
~~~

Implement changes in verifiable increments. For a feature, the sequence might be:

1. Update the necessary processing logic or data contracts.
2. Add or update tests for the new behavior.
3. Update the UI or call sites if required by the feature.
4. Update related documentation and configuration.
5. Run checks after each major part to catch errors early.

Avoid changes that create noise in reviews:

- Do not reformat unrelated files.
- Do not perform mass renames just because you are touching an area.
- Do not add temporary logs, debug code, or unnecessary test data.
- Do not commit build artifacts, caches, IDE files, or auto-generated files unless the repository expects them to be tracked.
- Do not put tokens, passwords, private keys, or sensitive production data into source code.

If refactoring is needed to implement the feature, keep the refactoring minimal and explain its connection to the objective. A single change branch can contain multiple commits, provided all commits serve the defined scope.

## Selecting Content to Stage into Commits

The staging area lets you select the exact changes recorded in a commit. It is an essential tool for keeping commits focused.

View unstaged changes:

~~~bash
git status --short
git diff
~~~

Stage a relevant file:

~~~bash
git add src/report/ReportService.java
~~~

If a file contains both related and unrelated changes, select hunks interactively using patch mode:

~~~bash
git add -p
~~~

Git displays each hunk for you to choose whether to stage it. Common options include:

- y: stage the current hunk.
- n: skip the current hunk.
- s: split the hunk into smaller parts if possible.
- e: manually edit the patch when you understand diff syntax well.
- q: quit selecting.

After staging, review what will be committed:

~~~bash
git diff --cached
git diff --cached --stat
git diff --cached --check
~~~

If you spot content that does not belong to the objective, unstage the file or selection and redo it:

~~~bash
git restore --staged path/to/file
~~~

This removes content from the staging area while preserving changes in the working tree. Do not confuse it with `git restore path/to/file`, which can overwrite unstaged changes in the file.

### Creating Meaningful Commits

A commit should represent a step of change that can be explained and reviewed. For example:

~~~bash
git commit -m "Add export date filter"
~~~

Commit messages should describe the outcome or intent. Avoid messages like `update`, `fix bug`, `changes`, or `test` because they do not tell anyone what the commit did.

If there are multiple logical steps within the same branch, you can create multiple commits:

~~~bash
git add src/report/ReportFilter.java
git commit -m "Add report date filter model"

git add src/report/ReportRepository.java
git commit -m "Apply date filter to report query"

git add src/test/java/report/ReportRepositoryTest.java
git commit -m "Test report date filtering"
~~~

The example above merely illustrates splitting commits. In real projects, tightly coupled parts can be combined into a single commit so reviewers understand the complete change. There is no need to make a commit for every line or every file save.

Inspect the branch history:

~~~bash
git log --oneline --decorate main..HEAD
~~~

If the base branch is `origin/main` and has been updated via fetch, you can use:

~~~bash
git log --oneline origin/main..HEAD
~~~

These commands display commits present in the current branch that are not yet in the specified base branch.

## Reviewing All Changes Before Sharing

Before pushing, compare the current branch against the base branch. Use the triple-dot syntax to see changes on the current branch since the common divergence point:

~~~bash
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
git diff --check origin/main...HEAD
git diff origin/main...HEAD
~~~

Replace `origin/main` with the base branch your pull request will target. Triple-dot syntax keeps the diff focused on the task branch's changes relative to the merge base, rather than comparing the two branch tips as double-dot syntax does.

When reading the diff, check across these categories:

| Check Category | Question |
|---|---|
| Scope | Do all files serve the same objective? |
| Logic | Are processing flows and edge cases handled accurately? |
| Compatibility | Do APIs, data structures, and configurations remain compatible? |
| Testing | Are new behaviors and affected legacy behaviors tested? |
| Documentation | Do guides or descriptions need updating? |
| Cleanliness | Are there debug statements, temp files, secrets, or unrelated formatting edits? |
| Reviewability | Can someone else understand the objective and rationale from the diff? |

If the diff is too large because of extensive reformatting or auto-generated files, consider removing the noise or splitting the work. If the change is large because a single behavior genuinely requires multiple coordinated parts, organize those parts cleanly and explain them clearly in the review description.

### Keeping the Branch Up to Date with the Base Branch

During development, the base branch may continue receiving new commits. Before requesting review or when conflicts arise, update remote information:

~~~bash
git fetch origin
~~~

If the team uses rebase to maintain linear history and your branch is not yet relied upon by others:

~~~bash
git rebase origin/main
~~~

After rebasing, recheck the diff and rerun affected tests. Rebasing changes the branch's commit hashes, so do not arbitrarily rebase a shared branch that others are developing on. If the team mandates merging instead of rebasing, follow that workflow.

## Pushing the Branch and Creating a Review Request

Once changes have been verified, share the branch to the remote:

~~~bash
git push -u origin feature/123-add-export-date-filter
~~~

The `-u` option sets the upstream for the local branch. Subsequent pushes can use `git push` based on the branch configuration.

After pushing, create a pull request or merge request on the platform your team uses. Select the right target branch, usually `main` or an integration branch per project policy.

A useful review description typically answers:

- **Problem:** What needs to be solved?
- **Changes:** What behaviors changed and in which parts?
- **Verification:** Which tests, builds, or manual checks were run?
- **Impact:** Are there API, configuration, schema, or usage changes?
- **Points of attention:** Are there technical decisions reviewers should inspect closely?

Example description:

~~~text
Objective
Allow users to filter reports by creation date.

Changes
- Added fromDate and toDate to the report filter.
- Applied date conditions to the query.
- Added tests for date ranges and empty data cases.

Verification
- Ran ReportRepository unit tests.
- Ran report export API tests.

Notes
If only one date boundary is provided, the system applies the corresponding condition for that boundary.
~~~

Descriptions must be honest about what was actually executed. Do not write "tested" if tests were not run; if any check was skipped, state so explicitly.

## When the Scope Starts to Grow

While working, you may uncover additional related issues. Before expanding the branch, evaluate how the new issue relates to the original objective.

- If the new issue is a prerequisite for the feature to work properly, keep it in the same branch and update the scope description.
- If the issue can be released independently, create a separate issue or branch to handle it later.
- If multiple interdependent branches are needed, discuss the integration order and per-part review approach with the team.
- If the branch has already grown too broad, consider splitting out independent parts before sending for review.

Do not split a single change into multiple pull requests if reviewers cannot understand or test each part independently. When branches depend on one another, clearly document which branch must be integrated first and which branch builds on it.

If a task is no longer needed or has been superseded, discuss with the team before closing the review and deleting the branch per repository process.

## Complete Example Workflow

Example creating a branch to add a date filter for reports:

~~~bash
# Check status and update the base branch
git status
git fetch origin
git switch main
git pull --ff-only origin main

# Create a branch with a task-descriptive name
git switch -c feature/123-add-export-date-filter

# Make source code edits and add tests
# Then review the changes
git status --short
git diff

# Select the exact relevant changes
git add -p
git diff --cached
git diff --cached --check

# Create a purposeful commit
git commit -m "Add export date filter"

# Check branch history and scope
git log --oneline main..HEAD
git diff --stat origin/main...HEAD
git diff origin/main...HEAD

# Share the branch to the remote
git push -u origin feature/123-add-export-date-filter
~~~

Next, open a pull request or merge request targeting the base branch. During review, incorporate feedback, make edits on the same branch if they remain within the original objective, rerun tests, and push follow-up commits.

## Pre-Review Checklist

- [ ] Branch was created from the right base branch and has a goal-descriptive name.
- [ ] Branch scope focuses on one explainable outcome.
- [ ] Unrelated changes have been separated out.
- [ ] Necessary tests have been added or updated.
- [ ] Both staged and unstaged changes have been reviewed.
- [ ] Diff against the base branch has been inspected.
- [ ] No debug code, temporary files, or secrets remain.
- [ ] Commit messages clearly describe intent.
- [ ] Branch has been pushed to the correct remote.
- [ ] Review description states the problem, changes, and test results.

## Key Takeaways

A review-friendly branch starts with a clear scope, is created from an up-to-date base branch, and contains only changes serving a single objective. While working, select content carefully into the staging area, create meaningful commits, reread the diff against the base branch, run appropriate tests, and honestly describe the results before sharing. The branch size should be small enough for others to understand and verify, while still preserving a complete change that can be tested and integrated safely.

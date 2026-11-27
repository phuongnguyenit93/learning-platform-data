# Checking for Leftover Markers and Verifying Behavior After Resolving Conflicts

## Why Must You Verify After Resolving Conflicts?

When Git detects that two branches modified the same content region in ways that cannot be combined automatically, Git asks the developer to resolve the conflict. Editing files to select, combine, or rewrite content is only part of the work. After editing, you must confirm that:

- Every conflicted path has been handled.
- No conflict delimiter markers remain accidentally in source code or configuration.
- The final result preserves the intent of the involved changes.
- Files have been properly added to the staging area.
- The application still compiles, passes tests, and works correctly after combining the changes.
- The merge, rebase, or cherry-pick operation has been completed following the right workflow.

A merge may no longer report conflicts and still introduce a logic bug. For instance, one branch adds an access permission check while the other adds a data export feature. If conflict resolution keeps only the data export and drops the permission check, the source code may compile cleanly while leaking data. Therefore, post-conflict verification must examine both Git state and application behavior.

## Determining the Current Git State

Start by checking the repository status:

~~~bash
git status
git status --short
~~~

`git status` tells you whether Git is in the middle of a merge, rebase, or cherry-pick, which files remain conflicted, which files are resolved, and which changes are waiting to be committed.

To list only paths still in an unmerged state:

~~~bash
git diff --name-only --diff-filter=U
~~~

If the command prints no paths, Git no longer records unresolved files in the index. You can further inspect unmerged entries with:

~~~bash
git ls-files -u
~~~

While conflicts remain, `git ls-files -u` may display multiple entries for the same path. For standard content conflicts, the stages mean:

| Stage | Content |
|---|---|
| 1 | Common base version (merge base), if present |
| 2 | Current side version (ours) |
| 3 | Incoming side version (theirs) |

Once a file is resolved and staged, the corresponding unmerged entries disappear. These two inspection commands confirm Git's state, but they do not prove the content is functionally right.

### Understanding ours and theirs Correctly

In a standard merge, ours is the current branch and theirs is the branch being merged in. In a rebase, this interpretation is often inverted from intuition: ours is typically the base branch onto which commits are being replayed, while theirs is the change from the commit currently being applied. This is why ours/theirs options during a rebase are easy to confuse. Do not choose content based solely on the names of the two sides. Check the active operation message, commit history, and goal of each change to understand what needs to be kept.

You can inspect the versions stored in the index while a file is still unmerged:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

Some conflict types such as add/add, modify/delete, or rename conflicts may not have all three stages. If a `git show` command does not find the corresponding stage, that may simply be a property of the current conflict type rather than a corrupted repository.

## Checking for Leftover Conflict Delimiters

### Identifying the Markers

When Git inserts conflict markers into a text file, the content usually looks like:

~~~text
<<<<<<< HEAD
Content on the current side
=======
Content on the incoming side
>>>>>>> feature/new-report
~~~

If using `diff3` or `zdiff3` display style, Git also shows the base version with a marker starting with `|||||||`:

~~~text
<<<<<<< HEAD
Content on the current side
||||||| 1a2b3c4
Content at the merge base
=======
Content on the incoming side
>>>>>>> feature/new-report
~~~

After resolving, all `<<<<<<<`, `=======`, `>>>>>>>`, and `|||||||` markers from the conflict region must be removed from the final content. Check source files, configuration files, documentation, and any files created or modified during resolution. Not every conflict type inserts markers into files: binary, add/delete, or rename conflicts generally must be identified through Git status and resolved with an explicit decision on the final version or path.

### Searching for Markers in Recently Changed Files

If you already know which files conflicted, search for markers by path:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/service.java config/application.yml
~~~

`rg` (ripgrep) prints line numbers and matching content. If there is no output and the exit code is 1, no matching lines were found. An exit code greater than 1 typically indicates an error running the command, such as a nonexistent path or unreadable file; do not treat such an error as confirmation that markers are clean.

You can search across the entire codebase scanned by ripgrep:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' .
~~~

However, searching the whole repository may match illustrative examples, test fixtures, or documentation that intentionally includes marker strings. Focus on the conflicted files and inspect each match before concluding. A `=======` line inside documentation or test data does not automatically mean an unresolved conflict.

If the project does not have ripgrep installed, you can use your IDE search or an equivalent CLI tool. The key is searching the exact files you handled, including configuration and non-code files.

## Re-Reading the Final Diff

After finishing edits to a file, read back the entire diff in context. These two commands show differences across the working tree, staging area, and current commit:

~~~bash
# Unstaged changes
git diff

# Staged changes
git diff --cached
~~~

You can narrow the scope to a single file:

~~~bash
git diff -- src/service.java
git diff --cached -- src/service.java
~~~

Once a file is staged, the content prepared for commit lives in `git diff --cached`. If you keep editing the file after staging, the new edits appear in `git diff`. Thus, checking only one of the two diffs can miss remaining changes.

To view statistics and path lists:

~~~bash
git diff --stat
git diff --cached --stat
git diff --name-status
git diff --cached --name-status
~~~

When reviewing the diff, ask yourself:

- Is sufficient behavior preserved from both branches?
- Were any important conditions, permission checks, error handlers, or logs accidentally deleted?
- Are function signatures, data types, field names, APIs, and data structures used by callers intact?
- Were environment configs, dependencies, schemas, or migrations changed without updating related parts?
- Were unrelated changes accidentally pulled into the resolution?
- Was any file deleted or renamed unexpectedly?

Do not inspect only the lines that had conflict markers. Git can combine separate regions automatically, yet an automatic result can still be logically broken when two changes depend on each other.

## Checking Whitespace and Diff Formatting

`git diff --check` detects certain whitespace errors in unstaged changes, such as trailing whitespace or whitespace errors per Git's rules:

~~~bash
git diff --check
~~~

To check staged changes:

~~~bash
git diff --cached --check
~~~

If you want to inspect the overall difference between `HEAD` and the working tree, you can use:

~~~bash
git diff HEAD --check
~~~

These commands detect formatting errors; they do not check program syntax or logic. A clean diff does not replace a compiler, linter, or tests.

## Confirming Staged Content

After reviewing the content and verifying the result is right, stage each resolved file into the staging area:

~~~bash
git add -- src/service.java config/application.yml
~~~

If the final decision is to delete a file, run:

~~~bash
git rm -- path/to/obsolete-file
~~~

For renames, add/delete, or multiple related files, inspect `git status` and `git diff --cached` carefully to verify Git is recording the intended operations. Do not run `git add .` mechanically if the working tree holds independent changes that should not go into the commit.

Re-verify:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
~~~

The expected outcome is zero remaining unmerged paths, resolved files staged, and the staged diff reflecting the exact intended content. If you edit anything further after this step, re-read the diff and stage the new updates.

## Verifying Application Behavior

### Start with Narrowly Scoped Checks

Run checks closest to the area just handled first. For example:

- Compile the module containing the edited class.
- Run unit tests for the affected class or package.
- Run the linter, formatter, or type checker on the modified files.
- Validate syntax and configuration loading if the conflict was in YAML, JSON, TOML, or another config file.
- Run integration tests if the two changes affect communication between multiple components.

Once narrow checks pass, run broader test suites following the project's workflow. If the changes affect APIs, databases, authorization, or critical business flows, verify the relevant use cases instead of relying on compilation alone.

There is no single test command for every project. Use the build and test commands specified by the project, and clearly record which checks ran, which did not, and why.

### Testing Behavior Cases from Both Branches

Suppose branch `feature/export` adds report export functionality, while branch `security/permission-check` adds an access permission check. Both branches modify the same method:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // conflict between permission check and report generation
}
~~~

A sound resolution must preserve both requirements: verify the user has permission before exporting, then generate the report according to the filter. Illustrative example:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

After resolving, do not merely check whether the method compiles. Verify at least these cases:

| Case | Behavior to verify |
|---|---|
| Authorized user | Report is generated according to the requested filter |
| Unauthorized user | Request is rejected without generating or returning report data |
| Invalid filter | Appropriate validation error is returned without generating a bad report |
| Non-existent data | Empty-data behavior aligns with the feature contract |

This illustrates how to think when verifying: identify the requirements introduced by each branch, find dependency points between them, and test the cases potentially affected by combining them. Do not copy the example verbatim into production if actual class names or business rules differ.

### Checking Configuration, Dependencies, and Data

Conflicts do not happen only in source code. When resolving the following files, check their corresponding aspects:

- **Configuration files:** verify keys, data types, default values, profiles, and environment variables. Watch out for cases where one branch adds a new key while the other renames or deletes an old key.
- **Dependency manifests and lockfiles:** verify library versions, compatibility constraints, and that lockfile contents are generated consistently with the manifest.
- **Database migrations:** check migration ordering, object names, executability against current data state, and whether both branches created duplicate changes.
- **APIs and schemas:** check request/response payloads, field names, data types, error codes, and call sites.
- **Documentation and examples:** update descriptions, sample configs, and guides if actual behavior changed.

For sensitive data, never put real secret values into test examples or logs. Use dummy data and the project's secure configuration mechanisms.

## Completing the Active Operation Properly

Once all conflicts are resolved, the right files are staged, diffs have been reviewed, and appropriate checks pass, complete the pending Git operation.

### If Merging

Check status:

~~~bash
git status
~~~

If Git confirms all conflicts are resolved and necessary changes are staged, continue the merge:

~~~bash
git merge --continue
~~~

Git may open an editor to confirm the merge message. After finishing, check:

~~~bash
git status
git log -1 --oneline
~~~

Some merges may be fast-forwarded and create no merge commit. Rely on the actual operation status and outcome rather than assuming there must always be a merge commit.

### If Rebasing

After resolving and staging the files for the current commit:

~~~bash
git rebase --continue
~~~

The rebase may stop on the next commit if that commit also conflicts. Repeat the inspect, resolve, stage, and continue cycle until the rebase completes. Then check history and status:

~~~bash
git status
git log --oneline --decorate -n 8
~~~

### If Cherry-Picking

After resolving and staging the files:

~~~bash
git cherry-pick --continue
~~~

If cherry-picking multiple commits, Git may continue processing the remaining commits. Check `git status` to confirm the operation has finished.

Do not mix up `--continue` commands. Use the command matching the operation that `git status` reports as in progress. If you intentionally want to cancel the operation, understand the impact of `git merge --abort`, `git rebase --abort`, or `git cherry-pick --abort` on current changes before running it.

## Sample End-to-End Workflow from Resolution to Verification

Example of merging branch `feature/report` into `main`:

~~~bash
# Check status and remaining conflicted files
git status
git diff --name-only --diff-filter=U

# After editing conflicted files, search for leftover markers
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/report.java config/application.yml

# Re-read both unstaged and staged diffs
git diff
git diff --cached

# Check whitespace
git diff --check
git diff --cached --check

# Stage resolved files
git add -- src/report.java config/application.yml

# Confirm index has no unmerged entries and inspect diff ready to commit
git status
git ls-files -u
git diff --cached

# Run checks appropriate for the project
# Example: run unit tests or build per project guidelines

# Continue merge once all necessary checks pass
git merge --continue

# Confirm status after merge
git status
git log -1 --oneline
~~~

The marker search and diff check commands are examples to adapt to your actual paths. If the marker search returns no output, check its exit code and confirm the tool was able to read the files. If tests fail, read the error output and determine whether the failure relates to the newly combined changes or the test environment.

## Reading the Final Result and Recording Evidence

After the merge, rebase, or cherry-pick completes, run a final check:

~~~bash
git status --short
git status
git log --oneline --decorate -n 8
~~~

Confirm that:

1. No unexpected merge/rebase/cherry-pick state remains in progress.
2. No unmerged paths remain.
3. Resolved files have the right final content and are recorded in the expected commit.
4. Selected checks all have clear results.
5. No out-of-scope changes were accidentally included in the commit.

If the project requires review before pushing, inspect the commit and create a pull request or merge request following your team's workflow. After pushing, check CI results and review feedback if any. A passing test run on a personal machine does not guarantee every CI or production environment behaves identically.

You can record verification evidence in the pull request description or work report: conflict types, handled files, tested behaviors, test commands executed, and results. Do not include tokens, credentials, or customer data in the report.

## Common Mistakes During Post-Conflict Verification

| Mistake | Consequence | How to handle |
|---|---|---|
| Only removing markers and concluding you are done | May lose part of a branch's logic | Re-read the entire function or config and cross-check both sides' requirements |
| Only inspecting `git diff` | Misses staged content | Inspect both `git diff` and `git diff --cached` |
| Seeing no markers left without checking unmerged paths | Unhandled files or wrong conflict type may remain | Use `git diff --name-only --diff-filter=U` and `git ls-files -u` |
| Staging everything with `git add .` | Accidentally commits independent changes | Stage by path and re-inspect the staged diff |
| Only running the build | Business logic bugs may go undetected | Run tests for affected behaviors and edge cases |
| Running `git commit` while rebasing | Breaks the workflow or causes confusion | Use `git rebase --continue` when a rebase is waiting |
| Skipping config files or lockfiles | App may misbehave in other environments | Check related dependencies, profiles, schemas, and migrations |
| Not checking status after continue | Rebase/cherry-pick may have another commit requiring handling | Run `git status` after each continue step |

## Key Takeaways

Conflict resolution is only complete when Git no longer records unmerged paths, final content has been re-read, changes are properly staged, and affected behaviors are verified. Use `git status`, `git diff --name-only --diff-filter=U`, and `git ls-files -u` to check state; search for markers in edited files; inspect both staged and unstaged diffs; run appropriate checks; and finally continue the right merge, rebase, or cherry-pick operation. The goal is to preserve the intent of the combined changes and keep the application working properly after history is updated.

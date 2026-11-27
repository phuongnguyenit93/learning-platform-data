# Checking for Whitespace Errors with git diff --check

Extra whitespace rarely breaks a program immediately, but it adds noise to diffs, makes code reviews harder, and can violate project conventions. Common issues include trailing spaces or tabs at the end of lines, extra blank lines at the end of a file, and spaces before tabs in indentation.

Git provides **git diff --check** to detect configured whitespace errors in changed lines. This command is useful before committing, before generating patches, and in CI. It helps catch issues early without visually scanning every diff line.

## 1. Inspection Scope

Without arguments, **git diff --check** compares the working tree with the index, meaning it primarily checks unstaged changes:

~~~sh
git diff --check
~~~

To check staged content against HEAD:

~~~sh
git diff --cached --check
~~~

To check the final state of tracked files against the current commit, including both staged edits and subsequent unstaged edits:

~~~sh
git diff HEAD --check
~~~

These three commands cover different scopes. Running only the default command can miss errors already sitting in the staging area.

The command does not scan every file in the directory. Unchanged files, untracked files, and ignored files are excluded from normal diffs. Already-committed content must be checked by specifying explicit revisions.

## 2. Common Error Types

| Error Type | Illustrative Example | Meaning |
|---|---|---|
| Trailing whitespace | **const n = 1;··** | Spaces or tabs at the end of a line |
| Trailing tab | **return result;→** | Tab appearing after content |
| Blank at EOF | Multiple blank lines after final content | Extra blank lines at the end of a file |
| Space before tab | **··→target:** | Spaces preceding a tab in indentation |
| Conflict marker | **<<<<<<< HEAD** | Leftover conflict marker in newly added lines |

In the table, dots represent spaces and arrows represent tabs; those are visual explanations, not literal characters to type into a file.

Example output:

~~~text
src/config.yml:27: trailing whitespace.
+  timeout: 30··
Makefile:8: space before tab in indent.
+ 	$(CC) $(FLAGS) -o app main.c
~~~

The message reports the filename, line number, and error type. The plus sign denotes a new line in the diff. Open the exact line in your editor, turn on visible whitespace if needed, remove the extra characters, and re-run the command.

### 2.1. Trailing Whitespace

Trailing whitespace consists of spaces or tabs appearing after the last content character on a line. It often happens when pressing Space after a semicolon, copying text from documents, or using an editor that preserves trailing spaces.

~~~text
// Avoid: trailing spaces at end of line
const enabled = true;··

// Preferred
const enabled = true;
~~~

Editors can automatically strip trailing whitespace on save. After enabling that setting, check your diff because saving may unexpectedly touch many older lines.

### 2.2. Blank Line at End of File

The blank-at-eof rule detects extra blank lines at the end of a file. Do not confuse it with the final newline terminating a file: standard text files should end with a single trailing newline; that single newline itself is not a blank-at-eof error.

### 2.3. Space Before Tab in Indentation

Some formats, notably Makefiles, require tabs to start recipes. Spaces appearing before a tab can break or inconsistently format indentation.

~~~text
··→$(CC) -o app main.c
~~~

If your project requires recipes to begin with a tab, remove the spaces preceding the tab.

### 2.4. Conflict Markers

When resolving merge or rebase conflicts, it is possible to accidentally leave behind:

~~~text
<<<<<<< HEAD
current implementation
=======
incoming implementation
>>>>>>> feature/new-flow
~~~

**git diff --check** can warn about conflict markers added in a diff. However, still inspect git status and review the post-merge logic; this command does not replace proper conflict review.

## 3. Checking Staged and Unstaged Changes

While editing files, run:

~~~sh
git status --short
git diff --check
~~~

Before committing, run:

~~~sh
git diff --cached --check
git diff --cached
~~~

If a file was staged and then edited again, status may display MM. In that case, the index holds the staged version while the working tree holds additional edits. Check each scope separately:

~~~sh
git diff --check
git diff --cached --check
git diff HEAD --check
~~~

If you edit a file without re-staging it, the index still holds the old content. Re-stage the file and inspect the staged diff again to confirm the commit will contain the fixed content.

## 4. Understanding Exit Codes and Using in Scripts

When no issues are found, the command normally prints nothing and returns exit code 0. When whitespace errors or conflict markers are found in the diff, Git prints diagnostics and returns a non-zero exit code.

~~~sh
git diff --check
result=$?
if [ "$result" -ne 0 ]; then
    echo "Whitespace check failed"
    exit "$result"
fi
~~~

In pipelines, let the check fail the CI step directly rather than ignoring the exit code. Do not append **|| true** to this command if the goal is to block commits containing whitespace errors.

## 5. Configuring core.whitespace

Git uses core.whitespace to define which whitespace issues are treated as errors. Common values:

| Value | Meaning |
|---|---|
| blank-at-eol | Spaces or tabs at the end of a line |
| blank-at-eof | Extra blank lines at the end of a file |
| space-before-tab | Spaces before tabs in indentation |
| indent-with-non-tab | Spaces used for indentation when tabs are required |
| tab-in-indent | Tabs appearing in indentation |
| cr-at-eol | Treat CR at the end of a line as part of the line ending |
| tabwidth=n | Tab width used when checking certain indentation rules |

Common defaults enable blank-at-eol, blank-at-eof, and space-before-tab. Additional rules can be enabled according to project standards.

Inspect configuration:

~~~sh
git config --show-origin --get core.whitespace
git config --local --get core.whitespace
git config --global --get core.whitespace
~~~

If no value is set, Git uses its built-in defaults. You can test a setting temporarily without saving it:

~~~sh
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab diff --check
~~~

If the team agrees on a local configuration:

~~~sh
git config --local core.whitespace blank-at-eol,blank-at-eof,space-before-tab
~~~

Local config lives in .git/config and is not automatically shared across team members. If shared rules are needed, document them in project docs or set them up via onboarding tooling and CI. Do not disable rules just to force a commit through the check.

## 6. CRLF and LF Line Endings

On Windows, files may use CRLF; on Linux and macOS, they usually use LF. Git can normalize line endings via .gitattributes and core.autocrlf.

~~~sh
git config --show-origin --get core.autocrlf
git check-attr text eol -- path/to/file
~~~

Example project rules:

~~~text
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
~~~

After changing line-ending settings, inspect git diff to catch unintended mass conversions. If Git reports CR at the end of lines, determine whether the file is intentionally supposed to use CRLF. cr-at-eol changes how Git interprets trailing CR; do not use it to mask an accidental line-ending change.

## 7. Choosing the Right Revision to Check

| Goal | Command |
|---|---|
| Unstaged changes | git diff --check |
| Staged changes | git diff --cached --check |
| Total tracked changes vs. HEAD | git diff HEAD --check |
| A specific file | git diff --check -- path/to/file |
| A commit vs. its parent | git diff --check HEAD^ HEAD |
| Contents of a commit | git show --check --format=oneline HEAD |
| Branch vs. divergence point | git diff --check main...feature/report |
| Two specific revisions | git diff --check <base> <target> |

### 7.1. Checking the Most Recent Commit

~~~sh
git show --check --format=oneline HEAD
git diff --check HEAD^ HEAD
~~~

For merge commits with multiple parents, specify which parent to compare against, such as HEAD^1. Do not assume the first parent is always the appropriate business baseline.

### 7.2. Checking a Branch Before a Pull Request

~~~sh
git fetch origin
git diff --check origin/main...HEAD
~~~

Three dots in git diff compare the current tip against the merge base of the two revisions. This is usually the right scope for validating changes proposed in a pull request. Replace origin/main with your actual base branch and fetch first if remote-tracking refs may be stale.

### 7.3. Checking Untracked Files

Untracked files are excluded from normal diffs. If you need to check a new file before staging it:

~~~sh
git add -N path/to/new-file
git diff --check -- path/to/new-file
~~~

git add -N creates an intent-to-add entry so Git shows the file's content in diffs without staging all of it like a regular git add. Check status afterward and stage properly when ready.

## 8. Integrating into Your Workflow

### 8.1. Before Committing

~~~sh
git status -sb
git diff --check
git diff --cached --check
git diff --cached
git commit -m "fix: normalize whitespace"
~~~

Run both unstaged and staged checks to catch issues in both layers. If you are only committing staged content, the staged check is the most critical step.

### 8.2. Using a pre-commit Hook

You can place a script in .git/hooks/pre-commit:

~~~sh
#!/bin/sh

git diff --cached --check
status=$?

if [ "$status" -ne 0 ]; then
    echo "Commit blocked: please fix whitespace errors in staged changes." >&2
    exit "$status"
fi

exit 0
~~~

The hook runs before a commit is created. If the check fails, Git aborts the commit so you can fix the content. The hook file must have executable permissions on systems that enforce them. Hooks in .git/hooks are normally not committed or shared automatically; teams should distribute hooks through a hook manager or enforce the check again in CI.

### 8.3. Checking in CI

In a pull request pipeline, resolve a reliable base commit and run:

~~~sh
git diff --check "$BASE_SHA" HEAD
~~~

BASE_SHA must be a fetched and verified base commit. Quote the variable. If the base commit is missing in a shallow clone, the pipeline must fetch deeper history before comparing.

When the command exits non-zero, fail the job and surface the offending file paths and line numbers so developers can fix them. Do not downgrade failures to non-blocking warnings if project conventions require clean diffs.

### 8.4. Not a Replacement for Formatters or Linters

**git diff --check** only validates certain whitespace errors in the diff. It does not replace formatters like Prettier, Black, or gofmt; linters; line-length checks; encoding checks; or unit tests. A file can pass this command and still have broken formatting or faulty logic.

## 9. Complete Practice Workflow

Suppose you just edited a Java file and are preparing to commit.

**Step 1 — check status**

~~~sh
git status -sb
~~~

**Step 2 — check unstaged changes**

~~~sh
git diff --check
git diff
~~~

Fix any reported errors in your editor and re-run the command.

**Step 3 — stage the file**

~~~sh
git add src/report/ReportService.java
~~~

**Step 4 — check staged changes**

~~~sh
git diff --cached --check
git diff --cached
~~~

**Step 5 — commit**

~~~sh
git commit -m "fix(report): clean whitespace in report service"
~~~

**Step 6 — verify the new commit**

~~~sh
git show --check --format=oneline HEAD
git status -sb
~~~

Expected result: zero whitespace errors in the checked changes, commit created cleanly, and no unexpected edits remaining in the working tree.

## 10. Common Troubleshooting

**The command reports no errors, yet the file still has extra whitespace.**

- The file may not be included in the diff, may be untracked, or may be ignored.
- Run git status --short and verify the exact scope.
- For untracked files, consider git add -N to bring the content into the diff.

**Running only git diff --check and missing staged changes.**

- Also run git diff --cached --check.
- Or use git diff HEAD --check to inspect total tracked changes against HEAD.

**Git reports space before tab in indent.**

- Enable visible tabs and spaces in your editor.
- Remove spaces preceding tabs at the start of the line.
- Check indentation rules for the file format, especially Makefiles.

**Git reports trailing whitespace.**

- Remove trailing spaces or tabs at the end of the line.
- Enable trim-trailing-whitespace on save in your editor if appropriate.
- Review the diff after saving to avoid accidentally modifying unrelated lines.

**CI fails while local checks pass.**

- Verify whether CI is comparing against the right base SHA.
- Compare Git versions and core.whitespace settings.
- Inspect line endings and .gitattributes.
- Confirm CI is checking the exact intended revision.

**Wanting to suppress errors via configuration.**

- Identify why the rule does not fit the file.
- Agree on the change across the team.
- Narrow the configuration change to the smallest necessary scope.
- Do not disable whitespace checks globally just to get a single commit through.

## 11. Whitespace Check Checklist

**Before staging**

- [ ] Run git diff --check.
- [ ] Fix trailing spaces and trailing tabs.
- [ ] Check for extra blank lines at the end of the file.
- [ ] Check for spaces before tabs in indentation.
- [ ] Re-check changed lines after fixing.

**Before committing**

- [ ] Run git diff --cached --check.
- [ ] Inspect git diff --cached to confirm what will be committed.
- [ ] If you made edits after staging, re-stage the file.
- [ ] Re-run the check after staging.

**Before sending a patch or pull request**

- [ ] Pick the right base and target revisions.
- [ ] Run git diff --check <base> <target> or the appropriate three-dot syntax.
- [ ] Fetch the latest base if needed.
- [ ] Check untracked files if they belong in the deliverable.
- [ ] Ensure CI enforces the same whitespace rules as the project.

## 12. Conclusion

**git diff --check** is a quick check to catch whitespace errors and conflict markers introduced in your changes. Keep in mind that the default scope only compares the working tree with the index; use --cached to validate staged changes and specify explicit revisions when checking commits or branches.

The command does not edit files on its own and does not scan the entire repository. Fix issues at the source, re-stage if necessary, run the check again, and inspect the diff. When integrated into pre-commit hooks and CI, it helps keep diffs clean, reviewable, and consistent across contributors.

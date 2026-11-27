# Timing of pre-commit, prepare-commit-msg, and commit-msg

Git supports **hooks** to run programs at specific points in the workflow. Three hooks commonly used when creating a commit are `pre-commit`, `prepare-commit-msg`, and `commit-msg`. They run at different stages: checking staged content, preparing the commit message, and validating the message before Git creates the commit object.

Understanding the exact timing of each hook helps you place checks in the right spot. Source code and quality checks belong in `pre-commit`; adding context to the message belongs in `prepare-commit-msg`; validating message format or conventions belongs in `commit-msg`.

## 1. Where the Three Hooks Fit in the Commit Flow

When running `git commit`, Git performs the main steps in this order:

```text
User runs git commit
          |
          v
     pre-commit
          |
          v
Prepare default commit message
          |
          v
  prepare-commit-msg
          |
          v
Open editor (if editing is needed)
          |
          v
      commit-msg
          |
          v
   Create commit object
```

If a hook returns a non-zero exit code, Git aborts the commit creation flow. Each hook can inspect or modify data at the stage where it is invoked. `prepare-commit-msg` is allowed to directly modify the message file; `commit-msg` typically validates the finalized message and can reject the commit if it does not meet conventions.

These three hooks are client-side hooks. They run on the committer's machine and may not be installed in every clone. Therefore, they support code quality and developer workflow, but should not be the sole control layer for mandatory project-wide policies.

## 2. `pre-commit`: Checking Before Creating the Commit Message

The `pre-commit` hook runs after Git determines the commit command can proceed, but before Git prepares the commit message and opens the editor. This hook is commonly used to:

- Check whitespace and formatting errors in staged changes.
- Run linters, formatters, or static checks.
- Run fast tests required before committing.
- Prevent commits when inappropriate files, secrets, or convention violations are detected.

The `pre-commit` hook takes no required arguments. It can read the index and working tree using standard Git commands. Specifically, `git diff --cached` shows the staged content, which is what is slated to go into the commit.

### Example: Rejecting a Commit on Whitespace Errors

Create a hook file named `pre-commit` in the hooks directory currently used by Git:

```sh
#!/bin/sh

if ! git diff --cached --check; then
    echo "Commit rejected: please fix whitespace errors in staged changes."
    exit 1
fi

exit 0
```

`git diff --cached --check` checks for whitespace errors in staged changes, such as trailing whitespace at the end of lines or whitespace issues flagged by diff rules. If the command returns an error, the hook exits with a non-zero code and Git does not create the commit.

On POSIX operating systems, set execute permission on the hook:

```bash
chmod +x .git/hooks/pre-commit
```

The `.git/hooks` path is the default location in a standard repository. If the repository configures `core.hooksPath`, Git looks for hooks in the configured directory instead.

### Checking the Exact Content About to Be Committed

A common design mistake is running a formatter or tests across the entire working tree without checking the staged content. A user might stage one version of a file and then keep editing it; the working tree and index now differ.

```bash
# View staged changes
git diff --cached

# View unstaged changes
git diff
```

The hook must be clear about which data it inspects. For diff-based checks, use `git diff --cached`. For tests running against the working tree, understand that tests may read unstaged changes as well; if test results must correspond strictly to the commit, the workflow should check the staged snapshot or use a tool specifically built to handle staged files.

If the hook modifies files itself, those modifications do not automatically become staged content. The hook or accompanying tool must intentionally update the index, and the user should review `git diff --cached` before committing.

## 3. `prepare-commit-msg`: Preparing the Message File

The `prepare-commit-msg` hook runs after Git creates the initial commit message and before opening the editor. The hook receives these arguments:

| Argument | Content |
|---|---|
| `$1` | Path to the file containing the commit message to be prepared |
| `$2` | Source of the message, if any; such as `message`, `template`, `merge`, `squash`, or `commit` |
| `$3` | OID of the source commit when the message is taken from a commit, such as with `-C`, `-c`, or amend |

The hook can read or modify the file at `$1`. It is commonly used to:

- Add a ticket ID extracted from the branch name.
- Add context when creating a merge commit.
- Generate an introductory section or template content for the message.
- Prepare content according to project conventions before the user edits it.

### Example: Adding the Branch Name as a Comment in the Message

The example below appends the branch name as a comment line so the user sees it when opening the editor. Git strips comment lines matching the configured comment character when creating the commit:

```sh
#!/bin/sh

message_file=$1
branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)

if [ -n "$branch" ]; then
    printf '\n# Branch: %s\n' "$branch" >> "$message_file"
fi

exit 0
```

This example uses the default `#` character as the comment character. If the project configures a different `core.commentChar`, adjust the script accordingly. The hook only adds reference information; the user still decides the final message content.

### This Hook Is Not Bypassed by `--no-verify`

Unlike `pre-commit` and `commit-msg`, `prepare-commit-msg` is not skipped when running:

```bash
git commit --no-verify
```

Therefore, avoid placing optional checks or operations that could fail unexpectedly inside this hook if users need the ability to bypass them with `--no-verify`. Reserve this hook for predictable and safe message preparation.

## 4. `commit-msg`: Validating the Message Before Creating the Commit

The `commit-msg` hook runs after the message has been prepared and edited by the user (if applicable), but before the commit object is created. The hook receives one argument:

| Argument | Content |
|---|---|
| `$1` | Path to the file containing the final commit message being checked |

The hook can read this file, check rules, and return a non-zero exit code to reject the commit. It can also edit the message file, though it should usually focus on validation to avoid silently altering text the user just entered.

### Example: Validating Subject Format

Suppose the team requires the first line to follow this convention:

```text
feat: add account endpoint
fix(auth): reject expired token
docs: clarify installation steps
```

A `commit-msg` hook can validate the subject as follows:

```sh
#!/bin/sh

message_file=$1
subject=$(sed -n '1p' "$message_file")

if ! printf '%s\n' "$subject" | grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([^)]+\))?: .{1,72}$'; then
    echo "Commit rejected: subject must follow type(scope): description, up to 72 characters."
    exit 1
fi

exit 0
```

The hook reads the first line and validates the commit type, optional scope, colon, and description. If it does not match, it returns exit code `1`, causing Git to abort the commit. The regular expression rules should be adjusted to match the team's actual conventions, such as length limits, casing, or allowed type list.

### Why Not Validate Only in `pre-commit`?

`pre-commit` runs before the final message is entered. It is suitable for checking source code and the index, but not the right place to validate a subject line the user has not finished writing. `commit-msg` is called at the exact moment the message is ready to be checked.

## 5. Comparing the Three Hooks

| Hook | Timing | Arguments | Suitable Tasks | Can Block Commit? |
|---|---|---|---|---|
| `pre-commit` | Before preparing the message | No required arguments | Lint, tests, staged diff checks, secret detection | Yes, if returning non-zero |
| `prepare-commit-msg` | After creating initial message, before editor | Message file, source, OID when applicable | Adding context, creating initial content, auto-adding ticket | Yes, if returning non-zero |
| `commit-msg` | After message is prepared, before creating commit | Message file | Format checks, ticket ID, subject length, content rules | Yes, if returning non-zero |

Place each check at its appropriate stage. For example, run unit tests in `pre-commit`, add branch info to the message in `prepare-commit-msg`, and validate the subject in `commit-msg`.

## 6. Installing and Testing Hooks in a Repository

Git usually pre-creates sample files in `.git/hooks` with a `.sample` extension. These sample files do not run automatically. To enable a hook, create a file with the exact name, such as `pre-commit`, `prepare-commit-msg`, or `commit-msg`, and ensure Git can execute it.

Check the default hooks directory and any alternative configuration:

```bash
# View the repository's default hooks directory
git rev-parse --git-path hooks

# Check hooksPath configuration if set
git config --show-origin --get core.hooksPath
```

If you want to store hooks in a directory committed with the project, you can use `.githooks`:

```bash
mkdir -p .githooks
git config --local core.hooksPath .githooks
```

Then create the files `.githooks/pre-commit`, `.githooks/prepare-commit-msg`, or `.githooks/commit-msg`. On POSIX, set execute permissions:

```bash
chmod +x .githooks/pre-commit
chmod +x .githooks/prepare-commit-msg
chmod +x .githooks/commit-msg
```

Note that `core.hooksPath` is a local repository configuration and is not automatically shared just because `.githooks` is committed. The project needs bootstrap instructions or a setup script so each team member enables this setting. If hooks rely on tools such as Node.js, Python, or a specific formatter, the team must also document how to install the required versions and dependencies.

## 7. Checking Execution Order and Handling Rejected Commits

When a commit is blocked, read the hook's output to identify which step failed. Inspect files and configuration:

```bash
# View staged changes
git diff --cached

# View current status
git status

# View effective hooksPath
git config --show-origin --get core.hooksPath
```

If `pre-commit` rejects the commit, fix the source code or staged diff issue and re-stage the intended changes. If `commit-msg` rejects it, fix the subject line in the message and re-run the commit. If `prepare-commit-msg` modifies the message unexpectedly, inspect the script and the message source passed to the hook.

Do not delete hooks or disable checks just to force a commit through. If a hook has a technical bug, fix the script or configuration so it checks the right content and returns the appropriate exit code.

## 8. `--no-verify` and the Limits of Client-Side Hooks

The `--no-verify` option bypasses two hooks:

```bash
git commit --no-verify
```

- Skips `pre-commit`.
- Skips `commit-msg`.
- Does not skip `prepare-commit-msg`.

This means client-side hooks cannot be the sole guarantee for mandatory rules. Users may skip certain checks, hooks may not be installed on a fresh clone, or a machine may lack required dependencies.

For policies that must apply to every contribution, add checks in CI or server-side hooks / branch protection rules on the hosting platform. Client hooks provide fast feedback right on the developer's machine; CI and the server re-verify changes before they are integrated into shared branches.

## 9. Security and Reliability Considerations

A hook is a program that can execute commands on the user's machine. Before enabling hooks from a repository, read their contents and understand what they do. A hook can run formatters, access files, invoke external programs, or modify the working tree/index.

When designing hooks for a team:

- Keep hooks short, with specific error messages and clear exit codes.
- Never write tokens, passwords, or sensitive data to logs.
- Do not assume every machine has the same runtime or tool versions.
- Modify the message or index only when that behavior is documented and the user can review it.
- Separate fast local checks from long-running integration tests in CI.
- Do not treat local hook results as the sole proof that a commit is safe or compliant with policy.

## 10. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| `pre-commit` can check the final commit message | This hook runs before the message is prepared; use `commit-msg` to validate the final message. |
| `prepare-commit-msg` only runs when opening an editor | The hook runs after Git prepares the message and before the editor; it still runs when the message is supplied via command-line options. |
| `prepare-commit-msg` is skipped by `--no-verify` | No. That option skips `pre-commit` and `commit-msg`, not `prepare-commit-msg`. |
| `commit-msg` cannot reject a commit | It can return a non-zero exit code to make Git abort the commit. |
| `.sample` files in `.git/hooks` run automatically | Sample files remain inactive until installed as a hook with the proper name. |
| Hooks in `.git/hooks` are automatically shared on push | The `.git` directory is not committed; an installation mechanism or `core.hooksPath` pointing to a project-managed directory is required. |
| Local hooks guarantee everyone follows policy | Hooks might not be installed or can be bypassed; mandatory policies must also be enforced in CI/server. |

## 11. Self-Check

1. **Which hook is suitable for running lint on staged changes?**
   - `pre-commit`.
2. **Which hook can add information to the message file before opening the editor?**
   - `prepare-commit-msg`.
3. **Which hook is suitable for validating the final subject convention?**
   - `commit-msg`.
4. **What arguments does `prepare-commit-msg` receive?**
   - Path to the message file, message source if present, and source commit OID when applicable.
5. **Which of the three hooks does `git commit --no-verify` skip?**
   - It skips `pre-commit` and `commit-msg`; it does not skip `prepare-commit-msg`.
6. **Why are additional checks needed in CI or on the server side?**
   - Because client-side hooks may not be installed or may be bypassed; CI/server is where repository-wide policies are enforced.

## Conclusion

`pre-commit`, `prepare-commit-msg`, and `commit-msg` are called at three different points in the commit creation workflow. Use `pre-commit` to inspect source code and staged content, `prepare-commit-msg` to prepare the message file, and `commit-msg` to validate the final message. Hooks can block a commit with a non-zero exit code, yet `--no-verify` still bypasses `pre-commit` and `commit-msg`. Therefore, use hooks to accelerate early developer feedback and use CI or server-side policies for mandatory team requirements.

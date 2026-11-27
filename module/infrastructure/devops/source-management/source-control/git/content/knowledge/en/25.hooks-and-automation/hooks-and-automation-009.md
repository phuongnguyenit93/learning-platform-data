# Reading Results, Handling Exit Codes, and Avoiding Human-Readable Output Parsing

A Git hook is a program invoked by Git at specific points, such as before committing or pushing. A hook can inspect data, run tests, format code, or reject an operation if conditions are not met. For a hook to behave reliably, you must distinguish three kinds of information: **command exit status**, **machine-readable output**, and **user-facing messages**.

A common mistake is writing scripts that rely on text Git prints to the terminal, such as searching for the string `nothing to commit` or `Everything up-to-date`. Those messages are designed for humans; they can change across versions, locales, options, and contexts. Hooks should rely on exit status and structured formats like `--porcelain`, `-z`, or `--format`, and then emit clear messages of their own to the user.

This lesson is part of hooks and automation in the Git workflow: checking changes before committing, checking refs before pushing, reporting useful errors, and ensuring a "no changes" result is never mistaken for an execution failure.

## 1. Three Information Channels When Running a Command

When a Git command runs, it can produce three kinds of results:

| Component | Purpose | Example |
|---|---|---|
| Exit status | Tells the calling program whether the operation succeeded, failed, or hit a specific condition. | `0`, `1`, `2` |
| Standard output (`stdout`) | Primary data or output of the command. | Ref list, filenames, commit hashes |
| Standard error (`stderr`) | Warnings, diagnostics, and error messages. | Auth errors, connection errors, remediation hints |

Example:

```bash
git status --short
```

The command can print a list of changes to `stdout` and exit with code `0`. A dirty working tree does not mean `git status` failed. The exit code indicates that querying status succeeded; the status content tells whether the repository has changes.

This is a fundamental principle: **never treat exit codes as a summary of every business state in the repository**. Know the exact exit-code contract defined by each command.

## 2. What Does Exit Status Mean?

By standard operating system and shell conventions:

- `0`: the command completed successfully.
- Non-zero: the command reports a special condition or an error.

However, `1` does not always mean a fatal error. Some commands use `1` to report "not found", "differences exist", or "condition false". Scripts must understand each command's contract.

### 2.1. Examples with Git Commands

| Command | Code `0` | How to Interpret Non-Zero? |
|---|---|---|
| `git status --short` | Status read succeeded; may be clean or have changes. | Usually an error querying the repository or environment. |
| `git diff --quiet` | No differences in the compared scope. | `1` means differences exist; higher codes may indicate execution errors. |
| `git diff --cached --quiet` | No staged changes compared to HEAD. | `1` means staged changes exist; not necessarily an error. |
| `git merge-base --is-ancestor A B` | `A` is an ancestor of `B`. | `1` means not an ancestor; other codes may indicate errors. |
| `git rev-parse --verify <ref>` | Ref resolved successfully. | Ref does not exist or invalid name; inspect context. |
| `git push` | Push completed as reported by Git. | Could be non-fast-forward, permissions, network, hook, or server policy. |

Read the documentation for each specific command before deciding which exit codes should block a hook. One command may use `1` for a normal check outcome, while another uses `1` to signal failure.

### 2.2. `git status` Returning `0` Does Not Mean the Working Tree Is Clean

This is a frequent logic bug in hooks:

```bash
if git status; then
    echo "Repository clean"
fi
```

The condition above only checks whether `git status` executed successfully. Git still returns `0` when the working tree contains modified, staged, or untracked files.

To determine whether staged changes exist, use a command designed for that check:

```bash
git diff --cached --quiet
rc=$?
```

Then interpret `rc` according to the contract of `git diff --quiet`.

## 3. Reading Exit Codes Properly in Shell

### 3.1. Capture `$?` Immediately After the Checked Command

In POSIX shell and Bash, `$?` holds the exit status of the most recent command. Capture it immediately after the command being checked:

```bash
git diff --cached --quiet
rc=$?

if [ "$rc" -eq 0 ]; then
    printf '%s\n' "No staged changes."
elif [ "$rc" -eq 1 ]; then
    printf '%s\n' "Staged changes exist."
else
    printf '%s\n' "Unable to inspect staging area." >&2
    exit "$rc"
fi
```

If you run another `echo`, `printf`, or any command before saving `$?`, its value is overwritten with that command's exit status.

### 3.2. Use `if` to Handle Errors Without Losing the Exit Code

You can place the command in a condition and capture the exit code in the `else` branch:

```bash
if git diff --cached --check; then
    printf '%s\n' "Whitespace check passed."
else
    rc=$?
    printf '%s\n' "Commit blocked: fix whitespace errors in staged changes." >&2
    exit "$rc"
fi
```

`git diff --cached --check` returns non-zero when whitespace errors are found or an execution error occurs. The hook above preserves the original exit code and halts the commit. If finer distinction between error types is needed, use dedicated inspection tools or parse structured data they emit.

### 3.3. Be Careful with Pipelines

In many shells, a pipeline's exit code defaults to the exit code of the last command. For example:

```bash
git status --short | grep '^ M'
```

The `$?` value after this pipeline is normally `grep`'s exit code, not `git status`'s. If `grep` finds no matching lines, it returns `1`; that may simply mean "no matching lines", not a Git failure.

In Bash, `set -o pipefail` makes a pipeline return non-zero if any command in the pipeline fails, yet you still must interpret each program's exit codes. POSIX shell does not mandate `pipefail` support.

When you need to know accurately whether a Git command succeeded, prefer invoking it directly and saving its exit code before processing output. The example below writes to a temporary file to preserve NUL bytes; shell variables cannot safely hold NUL-containing data:

```bash
tmp_file=$(mktemp) || exit $?
trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

git status --porcelain=v1 -z > "$tmp_file"
rc=$?
if [ "$rc" -ne 0 ]; then
    printf '%s\n' "Unable to read Git status." >&2
    exit "$rc"
fi

# Read "$tmp_file" using a NUL-safe parser.
```

Then parse the output file with a program capable of handling NUL delimiters when using `-z`.

### 3.4. `set -e` Does Not Replace Explicit Exit Status Handling

`set -e` causes a script to exit when a command returns non-zero, yet the rule has exceptions inside `if`, `while`, `&&`, `||`, pipelines, functions, and command substitutions. This easily causes surprises when commands return `1` for normal states.

For hooks with conditional logic, check exit statuses explicitly instead of relying solely on `set -e`. If using `set -e`, design and test branches that return special exit codes.

## 4. Reading Exit Codes in PowerShell

On Windows, when calling native programs like `git.exe`, PowerShell provides:

- `$LASTEXITCODE`: integer exit code of the most recent native program.
- `$?`: boolean success/failure status of the most recent PowerShell statement; this is a boolean, not the full numeric exit code.

Example checking staged changes:

```powershell
git diff --cached --quiet
$gitExitCode = $LASTEXITCODE

if ($gitExitCode -eq 0) {
    Write-Output "No staged changes."
}
elseif ($gitExitCode -eq 1) {
    Write-Output "Staged changes exist."
}
else {
    [Console]::Error.WriteLine("Unable to inspect staging area. Git exit code: $gitExitCode")
    exit $gitExitCode
}
```

Save `$LASTEXITCODE` immediately after the Git command. Calling another native program before saving it overwrites the exit code.

`$ErrorActionPreference = 'Stop'` does not automatically turn non-zero exit codes from native programs into exceptions in Windows PowerShell 5.1. Therefore, when writing hooks or automation scripts in PowerShell, always check `$LASTEXITCODE` explicitly.

## 5. Avoiding Human-Readable Output Parsing

### 5.1. Why Not `grep` Git's Prose Messages?

Avoid writing logic like:

```bash
git status | grep "nothing to commit"
git push | grep "Everything up-to-date"
```

Human-facing prose can change due to:

- Git version.
- Environment language or locale.
- Color, pager, or formatting options.
- Command context, remote type, and user configuration.
- Wording changes in future releases.

Human-readable output can also include filenames, quotes, or special characters that make simple grep checks inaccurate.

### 5.2. Use Machine-Readable Formats

Git provides more stable formats for scripts:

| Need | Recommended Approach |
|---|---|
| Read working tree status | `git status --porcelain=v1` or `--porcelain=v2` |
| Handle filenames with spaces/special characters | Combine with `-z` to use NUL as delimiter |
| List changed paths | `git diff --name-only -z` |
| List tracked files | `git ls-files -z` |
| Retrieve commit metadata | `git log --format=<placeholder>` or `git show --format=...` |
| List refs | `git for-each-ref --format=...` |
| Check attributes | `git check-attr` with structured output |

Examples:

```bash
git status --porcelain=v1 -z
git diff --cached --name-only -z
git log -5 --format='%H%x09%an%x09%s'
git for-each-ref --format='%(refname)%09%(objectname)'
```

`--porcelain` is designed for scripts and provides a much more stable format than regular output. `-z` uses NUL bytes to separate paths, preventing ambiguity when filenames contain spaces, tabs, or newlines. Programs reading the output must handle NUL properly; never use `for file in $(...)` because the shell splits on whitespace and corrupts filenames.

### 5.3. Never Ignore Quoting and Special Characters

Filenames in a repository can contain spaces, quotes, `*`, `;`, or newlines. When handling paths:

- Prefer NUL output with `-z`.
- Pass paths as separate arguments rather than concatenating into a shell command string.
- Quote shell variables like `"$path"`.
- Never use `eval` on data retrieved from Git.
- Never assume one output line equals one path if filenames may contain newlines.

This is both a correctness requirement and a safeguard against injection bugs when repositories contain contributor-supplied data.

## 6. Distinguishing Data Received via stdin, Arguments, and Output

Not every hook receives data by reading Git's stdout. Many hooks receive parameters via arguments or data via stdin.

| Hook | Primary Input Data | Role |
|---|---|---|
| `pre-commit` | No special arguments; reads index/working tree via Git commands. | Checks before creating a commit. |
| `prepare-commit-msg` | Message file path, message source, and optionally commit ID. | Prepares commit message content. |
| `commit-msg` | Commit message file path. | Validates or edits message before commit. |
| `pre-push` | Remote name and URL via arguments; list of ref updates via stdin. | Checks content about to be pushed. |
| `post-checkout` | Old HEAD OID, new HEAD OID, and branch checkout flag. | Notifies or updates workspace after checkout. |
| `post-merge` | Flag indicating whether the merge was a squash merge. | Runs post-merge tasks. |

For example, `pre-push` receives each stdin line formatted with local ref, local object name, remote ref, and remote object name. The hook should read stdin field by field rather than calling `git push` again or trying to infer what is already provided in its input.

Minimal shell example:

```bash
#!/bin/sh

remote_name=$1
remote_url=$2

while IFS=' ' read -r local_ref local_oid remote_ref remote_oid
do
    [ -n "$local_ref" ] || continue
    printf 'Checking %s -> %s\n' "$local_ref" "$remote_ref" >&2
done

exit 0
```

Ref names do not contain spaces, so splitting four fields according to the contract above works well. For arbitrary path data, use NUL-delimited formats or a dedicated parser.

## 7. Exit Status Determines Whether Certain Hooks Block an Operation

Hooks are commonly categorized into gating hooks (which can reject an operation) and notification hooks (which run after the operation completes).

### 7.1. Key Client-Side Hooks

| Hook | Timing | If Returning Non-Zero |
|---|---|---|
| `pre-commit` | Before creating a commit | Aborts commit. Can be bypassed with `git commit --no-verify`. |
| `prepare-commit-msg` | After Git prepares the message, before opening editor | Aborts commit. Not bypassed by `--no-verify`. |
| `commit-msg` | After user prepares the message | Aborts commit. Can be bypassed with `git commit --no-verify`. |
| `pre-push` | Before updating remote | Aborts push. Can be bypassed with `git push --no-verify`. |
| `post-commit` | After a successful commit | Cannot abort the created commit. |
| `post-checkout` | After checkout/switch | Cannot fail the checkout via exit status. |
| `post-merge` | After a successful merge | Cannot abort the completed merge. |

These are common hooks, not an exhaustive list. Exact behavior of every hook is documented in the `githooks` manual for your Git version.

### 7.2. Gating Hooks Should Return Non-Zero When Conditions Fail

Example `pre-commit` checking whitespace in staged changes:

```bash
#!/bin/sh

if git diff --cached --check; then
    exit 0
else
    rc=$?
    printf '%s\n' "Commit blocked: fix whitespace errors in staged changes." >&2
    exit "$rc"
fi
```

Git aborts the commit if the hook returns non-zero. The message is written to `stderr` so the user sees why. The hook does not parse Git's printed text; it uses the check's exit status.

### 7.3. Notification Hooks Cannot Undo an Already Completed Outcome

`post-commit` runs after the commit has been created. If this hook detects an error and returns `1`, the commit still exists. The hook can report an error, send notifications, or log events, yet should not present its exit code as if the commit were rejected.

If a task must block a commit, place the check in an appropriate pre-commit hook such as `pre-commit` or `commit-msg`.

### 7.4. `--no-verify` Does Not Skip Every Hook

`git commit --no-verify` skips `pre-commit` and `commit-msg`; it does not skip `prepare-commit-msg`. `git push --no-verify` skips `pre-push`. Never treat `--no-verify` as a fix for hook bugs; if used in an emergency, re-run the skipped checks through an alternative process and record the reason.

## 8. Hook Examples Using Exit Codes Instead of Message Parsing

### 8.1. Blocking a Commit If Staged Diff Has Whitespace Errors

Create a `pre-commit` hook:

```sh
#!/bin/sh

if git diff --cached --check; then
    printf '%s\n' "Pre-commit: whitespace check passed."
    exit 0
else
    rc=$?
    printf '%s\n' "Pre-commit failed: whitespace check did not pass." >&2
    exit "$rc"
fi
```

The hook calls `git diff --cached --check` directly and uses its exit status to decide. It does not search for `no whitespace errors` in output. When the check fails, Git receives a non-zero code and aborts the commit.

### 8.2. Checking Whether a Staged Diff Exists

```sh
#!/bin/sh

git diff --cached --quiet
rc=$?

case "$rc" in
    0)
        printf '%s\n' "No staged changes."
        ;;
    1)
        printf '%s\n' "Staged changes ready to commit."
        ;;
    *)
        printf '%s\n' "Unable to read staged diff." >&2
        exit "$rc"
        ;;
esac

exit 0
```

Code `1` in this example means differences exist, not a Git error. Treating every non-zero code as a failure could cause a hook to block a valid operation.

### 8.3. Checking Whether the Current Branch Is Behind the Remote

A hook or script can check ancestry relationships with:

```bash
git merge-base --is-ancestor origin/main HEAD
rc=$?

case "$rc" in
    0)
        printf '%s\n' "HEAD contains origin/main history."
        ;;
    1)
        printf '%s\n' "HEAD does not yet contain origin/main; update your base branch."
        exit 1
        ;;
    *)
        printf '%s\n' "Unable to check history relationship." >&2
        exit "$rc"
        ;;
esac
```

This condition is meaningful only if `origin/main` was fetched recently and is the intended base branch. If the remote-tracking ref is stale, the conclusion may not reflect the current server state. A `pre-push` hook should never assume local refs are always newer than the remote.

## 9. Using Machine-Readable Output in Hooks

### 9.1. Inspecting Staged Files with Porcelain

```bash
git status --porcelain=v1
```

Example output:

```text
M  src/payment.js
?? tests/payment-timeout.test.js
```

The porcelain v1 format uses two status characters at the start of each line. However, to handle filenames safely, add `-z` and use a NUL-safe parser:

```bash
git status --porcelain=v1 -z
```

For hooks inspecting content to be committed, staged paths are usually all you need:

```bash
git diff --cached --name-only -z
```

Never parse human-readable `git status` output by grepping for `modified:` or `new file:`, as that output is not a scripting interface.

### 9.2. Retrieving Commit Metadata with Custom Formatting

```bash
git log -1 --format='%H%n%an%n%ae%n%s'
```

`--format` lets you select exact fields instead of parsing the default log table. If a field may contain a delimiter, pick an unambiguous delimiter or use a parser with proper escaping rules. For filenames, prefer `-z`.

### 9.3. Disabling Pager and Colors in Automation

In scripts, avoid terminal-dependent output:

```bash
git --no-pager log --no-color --oneline -5
```

However, turning off the pager or colors only makes output easier to read; it does not turn human-readable output into a stable API. Whenever porcelain or custom format options exist, still prefer those.

## 10. Designing User-Facing Messages

Hooks should display short, specific, actionable messages:

```text
Commit blocked: whitespace errors detected in staged changes.
Run git diff --cached --check, fix the flagged lines, and re-stage.
```

A good message should state:

- Which operation was blocked (commit or push).
- Which check failed.
- Which scope is affected (file, branch, or ref if applicable).
- What command to run or what to fix next.

Write error and diagnostic messages to `stderr`. `stdout` can be used for primary output or success messages. Never print tokens, passwords, private keys, secret contents, or full environment dumps into hook logs.

For lengthy failures, write logs to an appropriate location or provide a log path; avoid printing thousands of lines that obscure the root cause. When debugging is needed, provide an explicitly enabled verbose mode.

## 11. Installing and Testing Hooks

### 11.1. Locating the Hooks Directory

By default, hooks reside in the hooks directory of the Git directory. You can check:

```bash
git rev-parse --git-path hooks
git config --show-origin --get core.hooksPath
```

If `core.hooksPath` is configured, Git uses that directory instead of the default location. Hook managers or projects commonly use this to organize scripts.

### 11.2. Hooks Are Not Automatically Shared Just by Being in `.git/hooks`

The `.git/hooks` directory belongs to the Git directory and is not committed like regular source code. Thus, fresh clones do not automatically inherit local hooks stored in this directory.

If a team wants to share hooks, manage scripts inside the repository or use a hook manager tool, paired with a clear installation step to configure `core.hooksPath` or copy hooks into the location Git uses. Document installation steps and tool versions.

### 11.3. Execute Permissions and Environment

On Linux/macOS, hook scripts require execute permissions and a valid shebang, such as `#!/bin/sh`. On Windows, Git for Windows typically provides a shell environment for running shell-based hooks; still verify setup, paths, line endings, and runtime behavior in practice.

Hooks should avoid assuming the working directory is always a specific subdirectory. You can determine the root with:

```bash
repo_root=$(git rev-parse --show-toplevel) || exit $?
```

Then use absolute paths or change directories intentionally.

### 11.4. Testing Hooks in a Test Repository

Before rolling out to the team:

1. Create a test repository or dedicated branch.
2. Run valid cases to verify the hook returns `0`.
3. Trigger a violation case to verify the hook returns non-zero and blocks the operation if it is a gating hook.
4. Test "empty/no-result" cases such as `git diff --quiet` returning `1` when it is not an error.
5. Test filenames containing spaces or special characters if the script handles paths.
6. Test across all shells and operating systems supported by the team.
7. Confirm the hook prints no secrets and messages clearly explain how to remediate.

Some Git versions support `git hook run <hook-name>` to execute a hook in a Git-managed way; check `git hook run --help` for your version. For context-dependent hooks like `pre-push`, supply appropriate stdin and arguments or test through real Git operations in a test repository.

## 12. Server-Side Hooks

In addition to client-side hooks, a Git server can run server-side hooks when receiving pushes. For example:

- `pre-receive`: receives the list of ref updates via stdin; returning non-zero rejects the entire push.
- `update`: invoked per ref; returning non-zero rejects updating that corresponding ref.
- `post-receive`: runs after refs are updated; cannot undo the update via exit status.

Server hooks are useful for enforcing centralized policies, such as blocking force pushes to main branches, checking commit signatures, or recording deployment events. Never rely solely on local hooks to guard critical rules, because users may skip installing hooks or bypass certain hooks with appropriate flags.

## 13. Common Design Mistakes

### 13.1. Treating Every Non-Zero Exit Code as an Error

`git diff --quiet` returns `1` when differences exist; `git merge-base --is-ancestor` returns `1` when the ancestry relation is false. These can be normal logic outcomes to handle, not execution errors.

### 13.2. Treating Exit Code `0` as a Clean Repository

`git status` returns `0` whenever reading status succeeds, even if the repository has changes. Use porcelain output or dedicated check commands.

### 13.3. Parsing Terminal Prose

Do not grep English or Vietnamese sentences from `git status`, `git push`, or `git commit`. Use exit status, porcelain, `-z`, and `--format`.

### 13.4. Letting Pipelines Mask Git Failures

A pipeline may return the exit code of its last command instead of the Git command. Capture the exit code directly or use `pipefail` where the shell supports it and its behavior is understood.

### 13.5. Printing an Error to stdout and Letting the Hook Exit `0`

If a gating hook fails its check yet still exits `0`, Git proceeds with the operation. Write diagnostics to `stderr` and return a non-zero code when rejecting.

### 13.6. Using Notification Hooks to Try to Block Operations

`post-commit` runs after the commit is already finalized. To prevent a commit, the check must live in a pre-commit hook.

### 13.7. Assuming Every Member Runs Local Hooks

Local hooks may be uninstalled or bypassed. Mandatory policies must be re-checked in CI or server-side hooks.

## 14. Workflow for Troubleshooting a Failed Hook

Suppose `git commit` is blocked by `pre-commit`:

**Step 1: Read the message and identify the hook**

Look for the hook name in the output or check `core.hooksPath` configuration. Do not rush to use `--no-verify`.

**Step 2: Inspect repository status**

```bash
git status --short --branch
git diff --cached --check
git diff --cached --stat
```

**Step 3: Re-run the exact check command**

Observe the exit status and output separately. Distinguish check failures from states like "changes exist" or "not found".

**Step 4: Fix the data or script**

If the staged diff violates a rule, fix the file, re-stage, and re-run the check. If the hook script has a bug, inspect arguments, stdin, environment variables, execute permissions, and runtime.

**Step 5: Verify exit codes and messages**

Test both passing and failing cases to confirm the hook returns the right code. Ensure output goes to the proper stream and does not depend on Git's prose wording.

**Step 6: Retry the Git operation**

Commit or push only after checks pass. If bypassing a hook is unavoidable in an emergency, run alternative checks and document the reason per team process.

## 15. Key Takeaways

- Exit status reports how the command executed; stdout/stderr carry data and messages.
- Exit code `0` normally indicates success, yet code `1` can represent a normal logical outcome.
- `git status` returning `0` does not mean the working tree is clean.
- `git diff --quiet`: `0` means no differences, `1` means differences exist; distinguish this from execution error codes.
- Capture `$?` in shell or `$LASTEXITCODE` in PowerShell immediately after the native command being checked.
- Do not rely entirely on `set -e`; handle special exit codes explicitly.
- Avoid parsing human-readable output; use `--porcelain`, `-z`, `--format`, and script-oriented options.
- Handle filenames with NUL-safe parsers, quote arguments, and never pass repository data to `eval`.
- Hooks receive data via arguments, stdin, or Git commands depending on hook type; read each hook's exact contract.
- Gating hooks return non-zero to reject operations; post-operation notification hooks cannot undo completed results.
- Local hooks are not the sole protective layer; critical rules should also be verified in CI or on the server.

A well-written hook never guesses Git state from terminal prose. It invokes the right command, interprets exit codes accurately, reads machine-formatted data, and emits messages clear enough for users to know what to do next.

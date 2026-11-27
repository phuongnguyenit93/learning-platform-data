# Hook Exit Codes, Arguments, Input, and Execution Environment

A Git hook is a program that Git invokes at specific moments, such as before creating a commit, before pushing, or after receiving updates from a remote. To write hooks correctly, you need to understand four parts of the execution contract: **exit codes**, **command-line arguments**, **data via standard input (stdin)**, and **environment variables** provided by Git.

Hooks do not share a single set of arguments. Each hook has its own timing and contract. Some hooks receive paths or remote names via `$1`, `$2`; some read a list of refs from stdin; others receive no arguments at all. Exit codes also carry different meanings depending on the hook: pre-action hooks can reject an operation, whereas post-action hooks typically serve only for notifications or side-effect tasks.

## 1. When and Where Does Git Invoke Hooks?

Git provides both client-side and server-side hooks. Client-side hooks run on the user's machine when performing operations like commit, checkout, merge, rebase, or push. Server-side hooks run on the machine receiving pushes, typically inside a bare repository.

Commonly used hooks:

| Hook | Timing | Common Purpose |
|---|---|---|
| `pre-commit` | Before creating a commit | Check staged diff, lint, or run fast tests |
| `prepare-commit-msg` | After Git generates initial commit message content, before opening the editor | Prepare or adjust the message based on context |
| `commit-msg` | After the user edits the message, before the commit is created | Validate commit message format |
| `post-commit` | After a successful commit | Send notifications or record events |
| `pre-rebase` | Before rebase begins | Check whether rebasing the branch is allowed |
| `post-checkout` | After a successful checkout or switch | Update working environment or dependencies |
| `post-merge` | After a successful merge | Run required post-integration tasks |
| `pre-push` | Before Git sends refs to a remote | Check commits about to be pushed or run tests |
| `pre-receive` | On the server, before updating received refs | Check the entire push and reject if policy is violated |
| `update` | On the server, before updating each ref | Check individual branches or tags |
| `post-receive` | On the server, after refs are successfully updated | Trigger deployment, notifications, or post-processing |

Hooks are looked up in the repository's hooks directory or the directory specified by `core.hooksPath`. In the default `.git/hooks` directory, sample files typically have a `.sample` suffix; Git does not automatically execute those sample files. A hook must have the exact hook name and execute permissions appropriate for the environment.

## 2. What Do Hook Exit Codes Mean?

A hook program terminates with an exit status. By standard shell convention:

- `0`: the program completed successfully.
- Non-zero: the program reports an error or rejects a condition.

Git interprets the exit code according to each hook's contract. For many verification hooks running **before** an operation, a non-zero code causes Git to abort the operation. For example, if `pre-commit` returns `1`, the commit is not created; if `pre-push` returns non-zero, the push is canceled.

For hooks running **after** an operation, a non-zero code cannot automatically undo what has already happened. For example, `post-commit` runs after the commit is already created; `post-receive` runs after the server has updated refs. A hook can log errors or warnings, but cannot use an exit code to retroactively reject an already completed commit or push.

Do not mechanically apply the rule "non-zero always cancels the Git command" to every hook. Always check the contract of the specific hook, especially server hooks whose behavior varies by stage.

### Pre-Operation Verification Hooks

Example `pre-commit` running a whitespace check on staged content:

```sh
#!/bin/sh

if git diff --cached --check; then
    exit 0
fi

echo "Commit aborted: please fix whitespace errors in staged changes." >&2
exit 1
```

If `git diff --cached --check` detects errors, the hook returns `1`; Git does not create the commit. The user fixes the content, re-stages, and runs commit again.

### Post-Operation Hooks

Example `post-commit` logging a notification:

```sh
#!/bin/sh

echo "Commit created: $(git rev-parse --short HEAD)"
exit 0
```

This hook does not control whether the commit is created because it only runs after the commit succeeds. If it fails, the commit still exists.

## 3. Command-Line Arguments and stdin Are Two Separate Channels

Git passes data to hooks in two ways:

1. **Argument vector:** arguments following the hook program name, readable as `$1`, `$2`, `$3` in shell.
2. **Standard input:** data written by Git to the hook process's stdin; scripts read it via `read`, loops, or data-processing programs.

Not every hook uses both. For example, `pre-push` receives the remote name and URL via arguments, while receiving the list of refs via stdin. If a script only reads `$1` and `$2`, it will not know which commits or refs are being pushed. Conversely, do not wait for stdin in hooks that do not provide data through that channel.

A snippet illustrating reading arguments:

```sh
remote_name=$1
remote_url=$2
```

An example reading stdin:

```sh
while read old_oid new_oid ref_name; do
    printf 'Ref %s: %s -> %s\n' "$ref_name" "$old_oid" "$new_oid"
done
```

The exact format of each line depends on the hook. Never substitute this generic example for the input specification of the hook you are implementing.

## 4. Arguments and Input of Common Client-Side Hooks

### pre-commit

`pre-commit` takes no standard command-line arguments and has no Git-defined stdin payload. Hooks commonly inspect the index state using commands such as:

```bash
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

Note that the hook should inspect **staged** content, since that is what is slated to enter the commit. Inspecting only the working tree with `git diff` may miss changes sitting in the index.

### prepare-commit-msg

This hook receives these arguments:

| Argument | Meaning |
|---|---|
| `$1` | Path to the file containing the initial commit message |
| `$2` | Source of the message, if any; such as `message`, `template`, `merge`, `squash`, or `commit` |
| `$3` | Commit ID, when the source is an applicable commit |

Example inspecting inputs:

```sh
#!/bin/sh

message_file=$1
message_source=${2-}
source_commit=${3-}

printf 'Message file: %s\n' "$message_file"
printf 'Source: %s\n' "$message_source"
printf 'Source commit: %s\n' "$source_commit"
```

The hook may modify the passed-in message file. It runs before the editor, so the user can still edit the content afterward. If you want to validate the final message after user input, use `commit-msg`.

### commit-msg

This hook receives one argument:

- `$1`: path to the file containing the commit message.

Example validating a simple message convention:

```sh
#!/bin/sh

message_file=$1

if grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([^)]+\))?: .+' "$message_file"; then
    exit 0
fi

echo "Commit message must follow type(scope): subject or type: subject." >&2
exit 1
```

If the hook returns non-zero, the commit is rejected and the user can edit the message and retry. Adjust the regex check to match the team's actual conventions; the example above only illustrates a simplified Conventional Commits pattern.

### post-checkout

The hook receives three arguments:

| Argument | Meaning |
|---|---|
| `$1` | Commit ID before checkout |
| `$2` | Commit ID after checkout |
| `$3` | `1` if checking out/switching a branch; `0` if checking out paths/files |

Example:

```sh
#!/bin/sh

old_head=$1
new_head=$2
branch_checkout=$3

if [ "$branch_checkout" = "1" ]; then
    echo "Switched branch to $new_head"
fi
```

This hook runs after a successful checkout. It can be used to notify or update caches, but cannot reject an already completed checkout operation.

### post-merge

The hook receives one argument:

- `$1` is `1` if the merge was performed with the squash option; otherwise `0`.

Example:

```sh
#!/bin/sh

if [ "$1" = "1" ]; then
    echo "Squash merge completed."
else
    echo "Merge completed."
fi
```

The hook runs after a successful merge. It cannot cause the merge to be rejected by returning a non-zero code.

### pre-rebase

The hook receives the upstream as the first argument and the branch being rebased as the second argument if specified. If no branch is specified, Git may omit the second argument.

```sh
#!/bin/sh

upstream=$1
branch=${2-}

printf 'Rebase upstream: %s\n' "$upstream"
printf 'Branch: %s\n' "$branch"
```

The hook can return a non-zero code to refuse starting the rebase, for example when the branch is on a list of branches not allowed to be rebased under team workflow rules.

## 5. pre-push: Remote Arguments and Ref List via stdin

`pre-push` is a classic example of a hook that uses both input channels simultaneously.

Git invokes the hook with:

- `$1`: remote name, for example `origin`.
- `$2`: URL of the remote.
- stdin: one line per ref being pushed, consisting of four space-separated fields:

```text
<local-ref> <local-object-name> <remote-ref> <remote-object-name>
```

Example:

```text
refs/heads/feature/login 1234567890abcdef refs/heads/feature/login 0987654321abcdef
refs/tags/v1.2.0 abcdef1234567890 refs/tags/v1.2.0 0000000000000000000000000000000000000000
```

Where:

- `local-ref`: the local ref being sent.
- `local-object-name`: the local object ID; length depends on the repository's hash format.
- `remote-ref`: the destination ref on the remote.
- `remote-object-name`: the current object ID on the remote; an all-zero string indicates the destination ref does not exist yet, typically a push creating a new ref.

If the local object ID is an all-zero string, it is a ref deletion. The hook should handle this case separately rather than attempting to read a nonexistent object.

Example hook that logs pushed refs and rejects attempts to delete the main branch. To avoid hardcoding OID length to SHA-1, the script matches strings consisting solely of `0` digits:

```sh
#!/bin/sh

remote_name=$1
remote_url=$2

echo "Checking push to $remote_name ($remote_url)"

while read local_ref local_oid remote_ref remote_oid; do
    case "$local_oid" in
        *[!0]*|'') ;;
        *)
            if [ "$remote_ref" = "refs/heads/main" ]; then
                echo "Deleting the main branch is not allowed." >&2
                exit 1
            fi
            ;;
    esac
done

exit 0
```

This is only a client-side check on the user's machine. It can be bypassed or left uninstalled in other clones; official branch protection rules must be enforced on the server or hosting platform.

## 6. Arguments and Input of Server-Side Hooks

Server-side hooks are configured on the repository receiving pushes. These hooks are the right place to enforce shared policies because every client pushing to the repository goes through the server.

### pre-receive

`pre-receive` takes no standard command-line arguments. Git sends via stdin one line for each proposed ref update:

```text
<old-oid> <new-oid> <ref-name>
```

Example:

```text
1111111111111111111111111111111111111111 2222222222222222222222222222222222222222 refs/heads/main
0000000000000000000000000000000000000000 3333333333333333333333333333333333333333 refs/heads/feature/search
```

`old-oid` is the current object ID of the ref; `new-oid` is the proposed object ID. An all-zero string in `old-oid` indicates a new ref. An all-zero string in `new-oid` indicates a ref deletion.

If `pre-receive` returns a non-zero code, the entire push is rejected, even when the push contains multiple refs. This hook is suitable for enforcing policies that apply simultaneously to the entire push.

### update

The `update` hook is called separately for each ref and receives three arguments:

| Argument | Meaning |
|---|---|
| `$1` | Name of the ref being updated, e.g., `refs/heads/main` |
| `$2` | Current object ID of the ref |
| `$3` | Proposed new object ID |

Example check preventing direct updates to release branches:

```sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

case "$ref_name" in
    refs/heads/release/*)
        echo "Release branches can only be updated via the release workflow." >&2
        exit 1
        ;;
esac

exit 0
```

If `update` returns non-zero, the corresponding ref is rejected. Other refs in the same push may still be updated if not rejected by other hook invocations or policies. This differs from `pre-receive`, which rejects the entire push.

### post-receive

`post-receive` takes no standard command-line arguments. Stdin contains the list of successfully updated refs, in the same three-field format as `pre-receive`:

```text
<old-oid> <new-oid> <ref-name>
```

This hook is typically used to send notifications, write audit logs, or trigger deployment systems. Because refs have already been updated before the hook runs, a non-zero exit code cannot reject a successful push.

## 7. Environment Variables Provided by Git to Hooks

Because hooks execute in a Git context, they often inherit environment variables that identify the repository, index, editor, and commit metadata. Common variables include:

| Variable | General Meaning |
|---|---|
| `GIT_DIR` | Path to the active Git metadata directory |
| `GIT_WORK_TREE` | Path to the working tree if explicitly set |
| `GIT_INDEX_FILE` | Path to the active index file; may not be the default `.git/index` |
| `GIT_PREFIX` | Path prefix relative to the current directory when Git is invoked from inside the repository |
| `GIT_EDITOR` | Editor Git will use for operations requiring content editing |
| `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL` | Environment variables that may be set to identify the commit author |
| `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` | Environment variables that may be set to identify the committer |

The identity variables in the table above may be inherited from the calling process's environment; do not assume Git always sets them for every hook. Git may also provide timestamp, configuration, or operation-specific variables. Never assume every variable always exists; check before using them and prefer commands like `git rev-parse` or `git config` to retrieve needed repository information.

Example printing diagnostic information:

```sh
#!/bin/sh

printf 'GIT_DIR=%s\n' "${GIT_DIR-}"
printf 'GIT_WORK_TREE=%s\n' "${GIT_WORK_TREE-}"
printf 'GIT_INDEX_FILE=%s\n' "${GIT_INDEX_FILE-}"
printf 'Repository root: '
git rev-parse --show-toplevel 2>/dev/null || echo "no working tree"
```

In a bare repository, `git rev-parse --show-toplevel` has no working tree to return. Server hooks should never assume a checked-out source directory always exists.

## 8. Working Directory and Calling Git from Inside a Hook

The current working directory context depends on the hook type and repository. Many client-side hooks run from the working tree root; some hooks in bare repositories or push-receiving hooks run inside the Git directory. Therefore, never assume `pwd` is always the project directory containing source code.

When you need the working tree root, you can use:

```sh
repo_root=$(git rev-parse --show-toplevel) || exit 1
```

When accessing a file inside the repository, compute the path from the root rather than relying on the current directory:

```sh
config_file="$repo_root/.editorconfig"
```

### Calling Git in Another Repository

Git passes environment variables such as `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE` to hooks so child Git commands continue operating on the current repository. If a hook needs to run commands in a **different** repository, these variables can cause Git to misread the context.

You can unset repository-local environment variables before calling Git in another repository:

```sh
for var in $(git rev-parse --local-env-vars); do
    unset "$var"
done

git -C /path/to/another/repository status
```

Only do this when you genuinely intend to switch to another repository. If you are still operating on the current repository, preserve the Git environment that the hook received.

## 9. Configuring Hook Location with core.hooksPath

By default, Git looks for hooks in the repository's hooks directory. You can inspect the default location:

```bash
git rev-parse --git-path hooks
```

You can configure a different hooks directory using `core.hooksPath`:

```bash
git config --local core.hooksPath .githooks
```

Example repository structure:

```text
project/
├── .githooks/
│   ├── pre-commit
│   └── commit-msg
├── src/
└── .git/
```

The `.githooks` directory can be committed to share hook contents within the repository. However, `core.hooksPath` is a local setting per clone; new team members must run the setup command or use the project's bootstrap script.

Inspect the setting and its origin:

```bash
git config --show-origin --get core.hooksPath
```

Hooks must have the exact filename, code runnable in the target shell environment, and proper execute permissions. On Unix, this typically requires:

```bash
chmod +x .githooks/pre-commit
chmod +x .githooks/commit-msg
```

On Windows, Git for Windows provides a compatible hook execution environment; verify the shell and script format chosen by the team. Avoid using interpreter paths or commands that exist on only one machine if the hook needs to run across the entire team.

## 10. Hooks Can Be Bypassed and Are Not a Security Boundary

Several commands support options to bypass client-side hooks:

```bash
git commit --no-verify
git push --no-verify
```

`git commit --no-verify` bypasses the `pre-commit` and `commit-msg` hooks; it does not mean every commit-related hook is skipped. `git push --no-verify` bypasses `pre-push`. Moreover, users with access to their machine can modify or omit installing local hooks.

Therefore:

- Use client-side hooks for early feedback, helping developers catch errors directly on their machine.
- Use CI, branch protection, or server-side hooks to enforce mandatory conditions for shared repositories.
- Never place secrets or critical credentials inside hooks committed to a repository; users can read those contents.
- Clearly document how to install hooks and how to update hook versions in project documentation.

Server hooks must also be deployed and administered carefully; direct access to the server or Git hosting configuration can affect policy enforcement.

## 11. Common Mistakes When Writing Hooks

| Error | Cause | Resolution |
|---|---|---|
| Hook always fails | Script exits with a non-zero code or an intermediate command returns an error | Check each command and only `exit 0` when all conditions pass |
| `pre-commit` does not see changes | Script uses `git diff` instead of the index diff | Use `git diff --cached` to inspect content about to be committed |
| `pre-push` does not know which branch is being sent | Reads only `$1`, `$2` and ignores stdin | Read each four-field line from stdin per the pre-push contract |
| Script reads wrong arguments | Assumes all hooks receive the same number of arguments | Check the specific hook contract and use `${2-}` when an argument may be absent |
| Hook invokes Git on the wrong repository | Git environment variables from parent process remain active | Keep the environment for the current repo; unset local Git env before calling another repo |
| Hook does not run | Wrong filename, wrong `core.hooksPath`, missing execute permission, or only `.sample` file exists | Verify hook path, name, and permissions |
| Local hook is bypassed | User passes `--no-verify` or skips hook installation | Move mandatory checks to CI/server-side policy |
| `post-*` hook fails yet operation succeeded | Hook runs after Git completes the action | Design post-processing with retries/logging; do not expect exit codes to undo the action |

When debugging, write logs to stderr to avoid interfering with output parsed by other tools. Avoid printing tokens, passwords, or all environment variables to logs.

## 12. Workflow for Designing and Testing Hooks

Before writing a hook, clearly determine:

1. Does the hook run on the client or the server?
2. Does the hook run before or after the operation being controlled?
3. What arguments does Git pass via the argument vector?
4. Is any data sent via stdin, and what is the line-by-line format?
5. Which environment variables are needed, and which might be absent?
6. Which exit codes allow continuation, and which reject the operation?
7. Does the hook need to run on Windows, macOS, Linux, or a specific server environment?
8. Can the hook be bypassed, and are mandatory conditions verified in CI/server?

A simple way to test is to create a test repository, install the hook in the proper location, perform the corresponding operation, and verify both success and failure cases. For example, with `commit-msg`, test a valid message and an invalid message; with `pre-push`, test pushing a new branch, updating an existing branch, and deleting a ref in the test repository.

Do not test hooks capable of rejecting pushes or ref updates directly on production repositories. Use a test repository or a dedicated remote to verify arguments, stdin, exit codes, and actual behavior.

## 13. Key Takeaways

The hook contract consists of four elements to verify individually: execution timing, command-line arguments, stdin data, and environment variables. `pre-commit` typically inspects the index; `commit-msg` receives the path to the message file; `pre-push` receives the remote name/URL via `$1` and `$2` along with the ref list via stdin; `pre-receive` receives ref updates via stdin; `update` receives the ref name along with old/new OIDs via three arguments.

Exit code `0` typically allows the hook to succeed; a non-zero code can reject an operation if the hook runs beforehand and its contract specifies it. Post-operation hooks cannot use error codes to reverse an already completed action. Finally, local hooks enable early checks but can be bypassed; mandatory policies must be enforced in CI or on the server side.

# Preventing Hooks from Rewriting History or Causing Unintended Side Effects

A Git hook is a program invoked by Git at a point in a workflow such as commit, checkout, merge, rebase, or push. A hook can inspect data, prepare a message, or run an automated task. However, hooks execute with the user's privileges and can invoke other shell or Git commands. If a script is not tightly scoped, an operation as routine as `git commit` can inadvertently modify the index, alter the working tree, create nested commits, rewrite history, or call an external service.

A safe hook should have a narrow scope, predictable behavior, and idempotent execution. For most pre-commit checks, favor reading data and reporting errors. If files or metadata must be modified automatically, define strictly which data may change, notify the user, and let them review the result.

## 1. Hooks Are Not Sandboxed

Git invokes a hook as an ordinary program. A hook can read and write files, execute OS commands, run Git, access the network, or affect external tools if the environment permits. Git does not automatically restrict hooks to read-only repository access or a subset of data.

A hook can produce several kinds of side effects:

| Scope | Example Side Effects |
|---|---|
| Working tree | Formatter rewrites files, script deletes temp files, or alters configuration |
| Index (staging area) | `git add`, `git reset`, or index-updating commands change what will be committed |
| History and refs | Creating new commits, amending, resetting branches, rebasing, or updating refs |
| Other repositories | Running Git commands with the wrong `GIT_DIR`, `GIT_WORK_TREE`, or index from the current repository |
| External systems | Sending notifications, updating tickets, calling APIs, uploading artifacts, or deploying applications |
| Machine environment | Editing Git config, installing tools, changing environment variables, or writing to shared directories |

Hooks have no automatic transaction mechanism to roll back all side effects if a later step fails. For instance, if a hook sends a notification to an external system and another hook subsequently rejects the commit, Git cannot retract that notification.

## 2. Principles for Designing Safe Hooks

Before writing a hook, clearly define its purpose and boundaries. The following principles help prevent unintended changes:

1. **Prefer read-only checks:** use `git status`, `git diff`, `git diff --cached`, `git rev-parse`, or `git log` to gather data. Do not modify data when the goal is purely validation.
2. **Limit scope:** process only paths or messages relevant to the current operation. Do not scan and mutate the entire repository unnecessarily.
3. **Never rewrite history automatically:** avoid `git commit`, `git commit --amend`, `git reset`, `git rebase`, `git merge`, `git cherry-pick`, `git update-ref`, or force-pushes inside ordinary commit hooks.
4. **Never switch branches automatically:** avoid `git checkout`, `git switch`, deleting branches, or changing HEAD while Git is performing another operation.
5. **Never bulk-stage files:** avoid `git add -A` or `git add .` inside hooks because they can pull unrelated changes into the commit.
6. **Design for idempotency:** the same input should not produce repeated mutations or unnecessary duplicate side effects.
7. **Report clearly:** if a hook rejects or modifies content, specify the exact file and reason the operation was stopped.
8. **Separate checks from deployment:** never deploy, publish releases, or update shared services merely because a local commit was just created.

These principles are especially important for hooks triggered automatically during merge, rebase, cherry-pick, or amend, because those operations can re-invoke certain hooks in ways the user may not anticipate.

## 3. Avoiding Nested Commits and Hook Loops

A dangerous bug is invoking `git commit` from inside a hook triggered by `git commit` itself. For example, `pre-commit` runs a script and that script runs `git commit`. The second commit command can trigger `pre-commit` again, leading to recursion or unexpected commit chains.

Do not place the following commands inside ordinary commit hooks:

```sh
# Unsafe examples inside a commit hook
git commit -m "automatic follow-up"
git commit --amend --no-edit
git reset --hard
git rebase main
git push --force
```

These commands can create nested commits, move HEAD, discard working tree changes, or overwrite remote history. If an automated commit is needed, perform it via a separate command or workflow explicitly run by the user, with clear inputs and outputs. Never turn a verification hook into an agent that unilaterally alters history.

If a specialized workflow genuinely requires creating commits from automation, design it as a standalone step with pre- and post-state checks, concurrency locks, target ref restrictions, and review controls. Never rely on silently disabling hooks to avoid recursion; bypassing hooks must be documented and applied only to the exact command that needs it.

## 4. Protecting the Index and Working Tree

When running `git commit`, the content in the index is what enters the commit. The working tree may contain newer edits that have not been staged yet. Therefore, hooks must distinguish between these two areas.

```bash
# Staged content slated for the commit
git diff --cached

# Unstaged content in the working tree
git diff

# Overall status
git status --short
```

For example, a developer stages `src/app.js` and then continues editing that file. The index holds the first version, while the working tree holds the second version. If a hook runs a formatter on the working tree without updating the index, the commit still records the pre-formatter staged version. Conversely, if the hook runs `git add -A`, it can accidentally stage other changes the user did not intend to commit.

### Prefer Running Formatters in Check Mode

If the tool supports a check mode, use that mode inside the hook:

```sh
#!/bin/sh
set -eu

# Only check file formatting according to project rules.
# The tool must run in check mode and must not rewrite files.
npm run format:check
```

Replace the illustrative command with the project's actual script. The goal is reporting formatting errors without modifying files or the index during commit.

### When Auto-Formatting Is Needed

It is best to provide a separate command such as `npm run format` for users to run intentionally before staging. After the formatter edits files, the user inspects the diff, stages the exact paths, and verifies again:

```bash
npm run format
git diff
git add src/app.js
git diff --cached
```

If a team decides to auto-fix inside a hook, specify clearly whether the hook modifies the working tree or the index. Update only the exact selected paths; never use `git add -A`. After modifying files, notify the user and ensure they can inspect both `git diff` and `git diff --cached` before continuing.

### Never Discard Unstaged Work

Hooks must never run `git checkout -- .`, `git restore .`, `git reset --hard`, or `git clean -fd` to create a clean working tree. Those commands can destroy the user's work. If a tool needs a clean environment, use a separate temporary clone or worktree, then clean up only the temporary directory created by that workflow.

## 5. Keeping Message-Checking Hooks Narrowly Scoped

`prepare-commit-msg` can edit the commit message file, while `commit-msg` can inspect and reject messages. These are easy places to surprise users if a hook rewrites text the user just entered.

In `prepare-commit-msg`, add only clearly ruled metadata, such as a ticket ID if not already present. Before appending, check existing content to avoid duplicating entries if the hook is invoked again. Never silently replace the subject or delete text written by the user.

In `commit-msg`, prefer reading the file and validating:

```sh
#!/bin/sh
set -eu

message_file=$1
subject=$(sed -n '1p' "$message_file")

if [ -z "$subject" ]; then
    echo "Commit rejected: subject cannot be empty."
    exit 1
fi

exit 0
```

This example checks only the first line and does not alter the message. If it fails the rule, the hook returns a non-zero code so the user can edit it themselves. This keeps authorship control with the person creating the commit.

## 6. Avoiding External Side Effects in Local Hooks

Never use local hooks to automatically deploy to production, publish packages, send emails to customers, transition tickets to final states, or write irreversible data to external systems. Local hooks can run when commits have not even been pushed yet, or when a user creates temporary commits and later amends or rebases them.

For example, `post-commit` runs after a commit is created in the local repository. It does not prove the commit has been pushed, reviewed, or integrated into the main branch. If a `post-commit` hook calls a deployment API, the application could be deployed from an unshared or unverified commit.

Choose the appropriate automation placement:

| Goal | Better Placement |
|---|---|
| Fast source code checks before commit | Client-side `pre-commit` |
| Commit message convention checks | Client-side `commit-msg` and re-check in CI |
| Full test suite for pull requests | CI after pushing or opening a pull request |
| Deployment after changes are approved and integrated | CI/CD triggered by events on protected branches or tags |
| Reacting to updated refs on a self-hosted Git server | Server-side hooks such as `post-receive` or platform equivalent |
| Sending local notifications to the developer themselves | Local hook, if side effects are idempotent and do not affect shared state |

External tasks should have idempotency, logging, retries, and dedicated error handling. If a notification or API call fails after a commit, log it for reprocessing; never rewrite a commit just to re-trigger an external task.

## 7. Understanding Post-Operation Hooks Properly

Hooks prefixed with `post-` typically run after the main operation has completed. They fit notifications or metadata syncing, yet errors in them do not automatically roll back the completed operation.

| Hook | When It Runs | Safety Note |
|---|---|---|
| `post-commit` | After creating a commit | Cannot reject or cancel the created commit; should not amend the commit again |
| `post-merge` | After a merge completes | Avoid auto-checking out, resetting, or creating another merge |
| `post-checkout` | After a successful checkout or switch | Do not switch branches again; may also be invoked when creating a worktree |
| `post-rewrite` | After commits are rewritten, e.g., amend or rebase | Receives old/new commit mappings; use for controlled metadata sync, never start another rewrite |

The `post-rewrite` hook warrants special caution: it runs after an operation that has already rewritten commits. If the hook goes on to run `rebase`, `commit --amend`, or uncontrolled ref updates, the workflow can loop or make history hard to trace. Restrict it to well-defined post-processing tasks, such as updating dependent references using the old/new commit mapping.

## 8. Avoiding Repository and Index Confusion via Environment Variables

Git sets several environment variables when invoking hooks, such as `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, and `GIT_PREFIX`. They ensure Git commands inside the hook operate on the repository and index currently performing the operation.

If a hook invokes Git in a different repository, these environment variables can make the command think it is operating on the current repository or using the wrong index. When you genuinely need to interact with another repository, run inside a subshell and unset the repository-local environment variables provided by Git:

```sh
other_repo="../tools-repo"

(
    unset $(git rev-parse --local-env-vars)
    git -C "$other_repo" status --short
)
```

The example above only reads the status of another repository. The subshell scopes unsetting environment variables to the child commands without altering the environment for the rest of the hook. Use this technique only when truly accessing another repository; for Git commands targeting the repository running the hook, preserve the Git environment received by the hook.

## 9. Restricting Mutation Scope and Controlling Paths

Hooks processing filenames must be careful because paths can contain spaces, tabs, or newline characters. Avoid splitting path lists using whitespace-based shell loops:

```sh
# Unsafe for paths containing spaces or newlines
for file in $(git diff --cached --name-only); do
    ...
done
```

When processing path lists in POSIX scripts, prefer NUL-delimited formats and NUL-aware tools, such as `git diff --cached --name-only -z`. If a script cannot handle arbitrary pathnames safely, restrict filename conventions or use dedicated tooling instead of guessing how to split strings.

Never splice branch names, filenames, commit messages, or commit contents into shell commands via unquoted interpolation. Always quote variables and treat repository data as untrusted input data, not commands to execute.

## 10. Testing Hooks in a Temporary Environment

Before rolling out a hook to the whole team, test it in a test repository or temporary clone/worktree. A testing checklist can include:

1. Create a test repository with a few tracked and untracked files.
2. Make staged changes and unstaged changes in the same file to verify the hook distinguishes both areas.
3. Create a file with spaces in its name to verify path handling.
4. Run the hook with valid input, invalid input, and missing dependencies.
5. Compare `git status`, `git diff`, `git diff --cached`, and `git log` before and after to catch unexpected changes.
6. Re-run the hook to confirm it does not duplicate metadata or create extra commits.
7. Test related operations such as amend, rebase, or merge if the hook is invoked in those flows.

You can specify a custom hooks directory for a single test command using `core.hooksPath`:

```bash
git -c core.hooksPath=.githooks commit -m "test hook behavior"
```

This command applies the `core.hooksPath` setting only to that single Git invocation. Run it inside a test repository with reviewed hooks, and make sure test commits do not affect real repositories.

## 11. Recovering When a Hook Causes Unintended Side Effects

If a hook modified the working tree or index, stop running further commands and inspect what changed:

```bash
git status --short
git diff
git diff --cached
git log --oneline -5
```

If a hook created commits or updated refs, inspect history and the reflog before recovering:

```bash
git reflog --date=local -10
git show --stat --oneline HEAD
git branch -avv
```

Do not immediately run `git reset --hard` or `git clean` to wipe traces. Those commands can erase legitimate user work. Back up or create a ref preserving needed commits, determine exactly what the hook did, and then choose an appropriate recovery path.

If the hook called an external service, check that service's logs and state. A Git reset cannot undo sent emails, updated tickets, or executed deployments. Handle external side effects through compensating workflows or recovery procedures in that external system itself.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Hooks can only read the repository | Hooks are normal programs and can modify files, the index, refs, or call external systems. |
| If `pre-commit` runs a formatter, changes are guaranteed to be in the commit | Commits read from the index; a formatter that only edits the working tree has not updated staged content. |
| `git add -A` in a hook is a safe way to stage formatter output | That command can also stage unrelated changes the user had not selected. |
| Hooks can run `git commit --amend` without affecting history | That creates a new commit and may re-trigger hooks; the OID and history change. |
| `post-commit` can reject a commit if deployment fails | The commit has already been created; post-processing hooks cannot cancel it. |
| Local hooks guarantee every member runs the same checks | Hooks may not be installed or can be bypassed; mandatory policies must be checked in CI or on the server. |
| Running Git in another repository only needs `-C` | The hook's Git environment variables may still point to the current repository; clear them in a subshell when switching repositories. |
| Resetting the repository undoes all hook side effects | Reset only affects Git state; it cannot retract notifications, API calls, or external system changes. |

## 13. Self-Check

1. **Why should a hook never run `git commit` inside a commit hook?**
   - It can re-trigger hooks repeatedly, create nested commits, or alter history unexpectedly.
2. **Why can `git add -A` inside a hook be dangerous?**
   - It can stage unrelated files and changes that the user did not choose to commit.
3. **If a formatter only edits the working tree, which version enters the commit?**
   - The version already in the index, unless the hook or user updates the index afterward.
4. **Can `post-commit` cancel a commit if an external task fails?**
   - No. The commit has already been created; external tasks need separate retry or compensating mechanisms.
5. **Why must Git environment variables be cleared when a hook operates on another repository?**
   - So Git commands in the other repository do not accidentally use `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE` from the repository invoking the hook.
6. **Where should production deployments be placed?**
   - In CI/CD or server-side workflows tied to approved branches/tags, not in local commit hooks.

## Conclusion

Hooks run with user privileges and can affect the working tree, index, Git history, or external systems. Design hooks to be read-only whenever possible, keep scope tight, avoid nested commits or history rewrites, avoid bulk staging, and never deploy from local commits. Test in temporary repositories, inspect before/after state, and use CI or server-side automation for tasks that must be enforced uniformly. When a hook has caused side effects, assess Git changes and external system changes separately before recovering.

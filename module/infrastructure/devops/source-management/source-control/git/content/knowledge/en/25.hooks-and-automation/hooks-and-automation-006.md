# Limitations of Hook Sharing and Why Local Checks Do Not Replace Server Policy

Git hooks are programs that Git invokes at specific moments, such as before creating a commit, before pushing, or after receiving changes. Teams can use hooks to run formatters, check basic errors, validate commit messages, or perform automated tasks. However, hooks installed in an individual's clone are not automatically shared when pushing and cloning a repository.

Therefore, a local hook is very useful for early feedback, yet cannot serve as the sole place to enforce mandatory team rules. Users might not have hooks installed, may use a different configuration, or may bypass certain hooks. Rules that must be applied consistently must be checked on the push-receiving server, in CI, and/or through platform branch protection policies.

This lesson explains where hooks are stored, how to share hook code inside a repository, how to install them per clone, the limitations around bypassing them, and how to move critical rules into centralized enforcement mechanisms.

After this lesson, you will be able to:

- Distinguish local hooks from server-side hooks.
- Explain why the .git/hooks directory is not pushed to the remote.
- Share hook scripts using a tracked directory in the repository.
- Configure core.hooksPath and verify which hooks are currently active.
- Recognize ways hooks can be bypassed and their limitations.
- Choose the appropriate enforcement layer for convenience checks versus mandatory policies.
- Combine hooks, CI, and branch protection to build a reliable workflow.

## 1. How Do Git Hooks Work?

A hook is a program or script whose name corresponds to a Git event. Git looks for hooks in the repository's hooks directory or the path configured by core.hooksPath. When the event occurs, Git runs the corresponding hook and passes arguments or data via standard input depending on the hook type.

Commonly used hooks:

| Hook | Timing | Common Purpose |
| --- | --- | --- |
| pre-commit | Before creating a commit | Run lint, formatter check, or fast checks. |
| prepare-commit-msg | After Git creates the draft commit message | Prepare or supplement the message. |
| commit-msg | After the user enters the message, before commit is created | Validate commit message format. |
| post-commit | After a successful commit | Write logs or local notifications. |
| pre-push | Before Git starts sending refs to the remote | Run checks before pushing. |
| post-checkout | After checkout or switch | Update the local environment. |
| post-merge | After a successful merge | Install or sync required components. |
| pre-rebase | Before rebase starts | Prevent rebasing in disallowed local scenarios. |

A hook can cause Git to stop an operation if that hook supports rejection and the script returns a non-zero exit code. Post-event notification hooks, such as post-commit, cannot roll back an already created commit simply by returning an error code.

A hook is usually an executable script. On Unix systems, execute permissions must be set. On Windows, Git for Windows typically runs shell hooks via the Git Bash environment; use a compatible shebang and syntax, or invoke programs available in the team's environment.

## 2. Why Is .git/hooks Not Shared via Remote?

When initializing a repository, Git typically creates a .git/hooks directory containing example files like pre-commit.sample or commit-msg.sample. Files ending in .sample are purely illustrative documentation; Git does not run them as active hooks.

Actual hooks are normally placed inside .git/hooks, and the .git directory is local administrative data for that clone. It does not belong to the file tree committed on branches. Consequently:

- Pushing a branch does not send hooks inside .git/hooks to the remote.
- Cloning a repository does not automatically pull the pusher's local hooks.
- Each clone can have different hooks and configurations.
- Installing a hook on one machine does not mean another machine has the same hook installed.

Check the current Git directory and hook path:

~~~bash
git rev-parse --git-dir
git config --show-origin --get core.hooksPath
~~~

If core.hooksPath is not configured, Git uses the default hooks directory inside the Git directory. If the config command returns no output, that usually means no core.hooksPath value has been set.

Do not attempt to commit .git/hooks directly. Instead, store hook scripts in a regular directory inside the repository, then guide each clone to configure Git to use that directory.

## 3. Sharing Hook Code in the Repository

A common convention is placing shared hooks in .githooks/:

~~~text
product/
|-- .git/
|-- .githooks/
|   |-- pre-commit
|   |-- commit-msg
|   +-- pre-push
|-- scripts/
|   |-- lint.sh
|   +-- check-commit-message.sh
|-- src/
+-- README.md
~~~

The .githooks directory is a normal directory, so Git can track and share it. Scripts inside it should be reviewed like any other source code: check their contents, execute permissions, dependencies, and failure behavior.

Example pre-commit hook:

~~~sh
#!/bin/sh
set -eu

echo "Running local checks before commit..."
./scripts/lint.sh
~~~

Example commit-msg hook receiving the commit message file path as its first argument:

~~~sh
#!/bin/sh
set -eu

message_file="$1"

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([a-z0-9-]+\))?: .+' "$message_file"; then
    echo "Commit message must follow the team format."
    echo "Example: feat(search): add filtering"
    exit 1
fi
~~~

This example illustrates one commit message convention. If the project uses a different convention, adjust the regex and error message. The hook must return code 0 when valid and a non-zero code when blocking the commit.

Avoid stuffing all checking logic directly into the hook. Extract shared logic into scripts under scripts/ so CI can invoke the exact same commands. That way, local hooks and CI enforce the exact same rules rather than drifting into two separate implementations.

## 4. Configuring core.hooksPath for Each Clone

Once the repository has a .githooks directory, users can configure the current clone:

~~~bash
git config --local core.hooksPath .githooks
~~~

--local saves the setting into the current clone's .git/config. This value is not shared through commits. Each new clone must run the corresponding setup step.

Verify:

~~~bash
git config --show-origin --get core.hooksPath
git config --local --get core.hooksPath
~~~

If you want to remove the custom setting and return to the default hooks path:

~~~bash
git config --local --unset core.hooksPath
~~~

When core.hooksPath is configured, Git looks for hooks in that path instead of the default directory. Therefore, ensure the directory contains all the hooks the team intends to enable. An empty hooksPath directory or an incorrect path can stop previously working local hooks from running.

### Setup Script for New Team Members

The repository can provide a simple setup script:

~~~sh
#!/bin/sh
set -eu

git config --local core.hooksPath .githooks
echo "Git hooks are configured for this clone."
~~~

Save the script, for example as scripts/install-hooks.sh, and instruct members to run it once after cloning:

~~~bash
sh scripts/install-hooks.sh
~~~

The setup script only modifies the local configuration of the current repository. Read and review the script before running it because it changes how Git executes programs on the machine.

A project may also use a hook management tool such as pre-commit, Husky, or Lefthook. These tools help install and coordinate hooks, yet do not change the underlying principle: the configuration and programs running on a member's machine still have to be installed, and local checks can still be bypassed.

## 5. Local Hooks Can Be Bypassed

Local hooks are a workflow-assistance mechanism, not a security boundary. There are many reasons why a hook may not run or may fail to block an operation:

- The team member has not run the hook setup script yet.
- core.hooksPath points to a different directory.
- The hook file does not exist or lacks execute permission.
- The local environment is missing a runtime or dependency required by the hook.
- The user intentionally uses a hook-bypass option supported by Git.
- The user modifies or deletes the hook in their clone.

Some specific bypass options:

~~~bash
# Skip pre-commit and commit-msg for this commit
git commit --no-verify -m "temporary commit"

# Skip pre-push for this push
git push --no-verify origin feature/search
~~~

--no-verify does not disable all hook types. With git commit, it skips pre-commit and commit-msg; the prepare-commit-msg hook is not skipped that way. With git push, it skips pre-push. Exact behavior depends on the command and hook type; do not generalize it as a master switch that disables every hook.

Furthermore, local configuration can be altered, scripts can be edited, or users can run Git from an environment without hooks. Therefore, a "local hook passed" result only proves that specific check succeeded in that environment.

Never use local hooks as the sole place to enforce mandatory conditions such as forbidding direct pushes to the main branch, requiring code reviews, or preventing secrets from entering history. Those conditions must be enforced where users cannot alter them inside their own clone.

## 6. Where Are Server-Side Hooks Enforced?

Git supports server-side hooks in repositories receiving pushes. They are configured on the server or repository hosting environment, not inside each contributor's clone.

Key hooks:

| Hook | Timing | Capability |
| --- | --- | --- |
| pre-receive | Once before updating the refs received in a push | Inspects all updates; returning a non-zero code rejects the push. |
| update | For each ref about to be updated | Can accept or reject each ref individually. |
| post-receive | After refs have been successfully updated | Sends notifications, triggers deployments, or records events; cannot reject an already completed update. |

The pre-receive hook receives the list of updates via standard input. Each line contains the old object ID, new object ID, and ref name. The hook can use that information to enforce policies, such as blocking deletion of release branches or requiring signed commits.

The update hook is invoked individually per ref and receives the ref name along with old/new object IDs via arguments. It is useful when deciding whether to permit an update to a specific branch or tag.

The post-receive hook runs after refs are updated. It suits sending notifications, updating tracking systems, or triggering pipelines. If a push needs to be rejected, the logic must run before refs are updated, such as in pre-receive or update.

These server-side hooks must be installed and administered by someone with permissions on the server. A user cloning the repository cannot modify hooks on the push-receiving repository by editing their own .githooks.

## 7. Git Hosting Platforms Can Provide Centralized Policies

Not every team administers a Git server directly. On GitHub, GitLab, Bitbucket, or similar services, administrators typically configure policies at the repository or project level:

- Protected branches or branch rules.
- Requiring pull requests/merge requests before integration.
- Requiring a minimum number of approvals.
- Required status checks from CI.
- Restricting force pushes or branch deletions.
- Requiring signed commits or platform-appropriate validation rules.

Feature names and enforcement scopes vary across providers, service tiers, and repository types. Configure them according to the documentation of the platform you are using.

For example, if a team forbids direct updates to main, branch protection must be enabled on the platform or server. A pre-push hook in a contributor's clone can remind them not to push to main, yet a user can bypass the hook or use a clone without hooks installed.

Required status checks also mean something different from a local hook passing. The platform permits merging only when designated CI jobs report passing statuses. If direct pushes also need protection, configure push permissions and branch protection rules accordingly; requiring CI only on pull requests may not cover every update path.

## 8. Dividing Checks Across Local Hooks, CI, and Server Policy

Choose the enforcement layer based on the goal and strictness required:

| Check | Local Hook | CI | Server/Platform Policy |
| --- | --- | --- | --- |
| File formatting on commit | Ideal for fast feedback | Can re-verify | Usually no separate policy needed if CI is required |
| Lint and unit tests | Can run a small subset | Runs full suite consistently | Required status check if it must pass before merge |
| Commit message format | Can remind and check early | Can check commit history/PR | Server hook can reject commits/pushes by policy |
| No direct push to main | Reminder only | Not the primary mechanism to block pushes | Protected branch or server hook |
| Require code review | Cannot fully verify on its own | Can check review status via API depending on system | Platform pull/merge request rules |
| Prevent forbidden ref updates | Unreliable | Can only detect after push | pre-receive, update, or ref protection permissions |

A pattern that works well in practice:

1. Local hooks run fast checks to catch errors right before commit or push.
2. CI re-runs checks in a clean environment with controlled tool and dependency versions.
3. The platform requires status checks, reviews, and branch rules before merging.
4. The Git server uses receive hooks if the team manages the server and needs ref-level push rejection.

Never run a check only in a local hook and treat that as proof that policy was satisfied. CI and server policy must independently enforce required conditions.

## 9. Example: Sharing a Commit-Check Hook While Still Verifying in CI

Suppose a team agrees that commit messages must include a change type such as feat, fix, or docs. The repository contains:

~~~text
.githooks/
+-- commit-msg
scripts/
+-- check-commit-message.sh
~~~

Shared verification script:

~~~sh
#!/bin/sh
set -eu

message_file="$1"

grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([a-z0-9-]+\))?: .+' "$message_file"
~~~

Hook calling the script:

~~~sh
#!/bin/sh
set -eu

./scripts/check-commit-message.sh "$1" || {
    echo "Invalid commit message format."
    exit 1
}
~~~

Team member installs the hook:

~~~bash
git config --local core.hooksPath .githooks
~~~

CI also invokes the same script on commit messages or commits within the pull request scope. How commit lists and messages are extracted depends on the CI system, while the rule logic lives in a single shared script.

Even if a contributor runs git commit --no-verify, CI still catches the invalid message and a required status check blocks the merge. If policy requires rejecting the push itself to the central repository, deploy a receive hook or equivalent platform feature.

## 10. Installing Hooks Safely and Maintaining Them Across Versions

Because hooks can run commands on a user's machine, sharing hooks means sharing executable code. Teams should:

- Review scripts like executable source code, especially changes to shell commands.
- Use clear relative paths and avoid relying on unexpected working directories.
- Check dependencies before running; print installation instructions if missing.
- Keep local execution time reasonable so commits do not drag.
- Never print tokens, passwords, or sensitive data to logs.
- Ensure errors propagate via non-zero exit codes when blocking an operation.
- Clearly document how to install, update, and remove hook configuration in project docs.

If the repository updates the contents of .githooks, clones with core.hooksPath configured will use the updated files after pulling the commit containing those changes. However, if a member has not configured hooksPath, they still will not automatically run hooks in .githooks.

The setup script can be updated to verify current configuration:

~~~sh
#!/bin/sh
set -eu

git config --local core.hooksPath .githooks
echo "Configured hooksPath: $(git config --local --get core.hooksPath)"
~~~

To remove the configuration:

~~~bash
git config --local --unset core.hooksPath
~~~

This command does not delete the .githooks directory in the working tree; it only removes the local configuration so Git falls back to the default hook path. If the team uses a hook management tool, follow that tool's install/uninstall mechanism.

## 11. Common Misconceptions

### Committing .githooks Makes Everyone Run Hooks Automatically

Incorrect. Committing only shares the scripts. Each clone must configure core.hooksPath or install a hook manager for Git to execute those scripts.

### Pushing Local Hooks Installs Them on the Server

Incorrect. .git/hooks is a local administrative directory and is not pushed. Server-side hooks must be installed on the push-receiving repository or configured via the platform.

### --no-verify Skips All Hooks

Incorrect. This option skips only the hooks specified by the command's documentation, such as pre-commit and commit-msg for git commit, and pre-push for git push.

### A Passing Local Hook Guarantees Policy Compliance

Incorrect. Hooks might not be installed, may be modified, or may be bypassed. Mandatory policies must be re-verified in CI or enforced on the server/platform.

### post-receive Can Reject a Push

Incorrect. This hook runs after refs have already been updated. Use pre-receive or update when rejection before updating is required.

### CI Completely Replaces Protected Branches

Not necessarily. CI produces check results, while the platform must be configured to require those results before merging. Direct push permissions and force push permissions also need separate controls.

## 12. Key Takeaways

- Local hooks run inside each individual's clone; the .git/hooks directory is not shared through push/clone.
- Scripts can be shared in .githooks and each clone configured with git config --local core.hooksPath .githooks.
- core.hooksPath is a local setting, so new clones require a setup step.
- --no-verify skips only specific hooks; it is not a master switch to disable every hook.
- Client-side hooks fit fast feedback and supporting workflow habits.
- Server-side hooks like pre-receive and update can reject ref updates; post-receive fits notifications and post-push tasks.
- CI must be configured as a required status check if results must pass before merging.
- Protected branches and platform policies enforce reviews, push permissions, force pushes, and integration rules.
- Mandatory rules must never rely solely on local hooks; enforce them where contributors cannot alter them independently.

Local hooks catch bugs early and shorten feedback loops, while CI and server policies create consistent checkpoints for the entire team. By sharing hook code yet placing mandatory conditions on the push-receiving side or platform, the workflow stays both developer-friendly and centrally controlled.

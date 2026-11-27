# Client-Side Hooks and Server-Side Hooks

Git hooks are programs that Git invokes automatically at specific points in the lifecycle of Git operations. They can inspect content before creating a commit, validate commit messages, run tests before pushing, record activity after a merge, or check refs before a server accepts a push.

Git divides hooks into two groups based on where they run:

- **Client-side hooks:** run on the developer's machine, inside the local repository.
- **Server-side hooks:** run on the Git server when the server receives or processes changes.

Both groups can support the same workflow, yet they differ in control and enforcement reliability. Client hooks provide early feedback and improve the developer experience. Server hooks enforce centralized policies for everyone sending changes to the repository. For mandatory rules such as protecting main branches, release permissions, or policy checks, enforcement must happen on the server side or the repository management platform.

## 1. What Is a Git Hook?

A hook is a script or program named after an event supported by Git. When that event occurs, Git looks for the corresponding hook and executes it. A hook can read arguments, receive data via standard input, inspect repository state, invoke external tools, or reject the operation with a non-zero exit code if that hook type allows it.

For example:

- **pre-commit** runs before Git creates a commit.
- **commit-msg** checks the file containing the commit message.
- **pre-push** runs before Git sends refs to a remote.
- **pre-receive** runs on the server when receiving a push.
- **post-receive** runs after the server successfully updates refs.

A hook is not a commit and does not automatically become part of project history. A hook is executable code configured in the repository or server environment.

### 1.1. What Do Hooks Help Automate?

Common goals include:

- Checking whitespace, formatting, and linting before committing.
- Validating commit message structure.
- Running fast tests before pushing.
- Preventing unauthorized ref updates on the server.
- Logging, sending notifications, or queuing deployment jobs after receiving a push.
- Aligning verification workflows with team policies.

Hooks are well suited for tasks with a clear trigger point and an automatically determinable result. For long-running checks, checks with many service dependencies, or resource-intensive tasks, consider CI instead of making commit or push operations take too long.

## 2. Client-Side and Server-Side Hook Lifecycle

A typical change may go through these steps:

~~~text
Developer Machine                            Git Server

Edit file
   |
   v
git add
   |
   v
pre-commit
   |
   v
commit-msg
   |
   v
Create commit
   |
   v
pre-push
   |
   +---------------------------------------> pre-receive
                                               |
                                               v
                                           update (per ref)
                                               |
                                               v
                                          Update refs
                                               |
                                               v
                                           post-receive
                                               |
                                               v
                                      Notifications / CI-CD queue
~~~

The diagram shows a high-level flow. Depending on the operation, Git may invoke different hooks; not every operation passes through every hook in the diagram.

Client hooks can catch issues right before changes are shared. Server hooks validate again where the push is received. CI typically continues running checks after the changes are received or after a pull request is created.

## 3. Client-Side Hooks

Client-side hooks run in the user's local repository. They are commonly used to improve change quality before committing or pushing.

### 3.1. Commit-Related Hooks

| Hook | When It Runs | Purpose |
|---|---|---|
| pre-commit | Before creating a commit | Inspect staged content, run lint or fast tests |
| prepare-commit-msg | After Git creates the initial message content, before opening the editor | Automatically prepare or edit the message content |
| commit-msg | After the user enters the message, before creating the commit | Validate or reject the message |
| pre-merge-commit | After a successful merge, before creating the merge commit | Check before finalizing the merge commit |
| post-commit | After the commit is created | Send notifications or record events |

pre-commit and commit-msg can reject a commit by returning a non-zero exit code. post-commit runs after the commit has already been created, so it cannot be used to abort that commit.

prepare-commit-msg receives the path to the message file and information about the source of the message. This hook can modify the file content. It is not bypassed by the git commit --no-verify option; this differs from pre-commit and commit-msg.

### 3.2. Patch-Applying and Email Hooks

Git provides hooks for workflows that send patches via email or apply patches:

- applypatch-msg: checks the message when applying a patch with git am.
- pre-applypatch: runs before a patch is applied as a commit.
- post-applypatch: runs after a patch has been applied.
- sendemail-validate: validates content before sending patches with git send-email.

These hooks are useful in projects using patch-based workflows. For teams working via pull requests, they are typically used less often.

### 3.3. Branch and Synchronization Hooks

| Hook | When It Runs | Purpose |
|---|---|---|
| pre-rebase | Before starting a rebase | Prevent rebase if the branch or state violates policy |
| post-checkout | After checking out a branch or commit | Update local environment, remind to install dependencies |
| post-merge | After a merge completes | Update generated files or remind to sync the environment |
| pre-push | Before sending refs to a remote | Run tests or checks before sharing |
| post-rewrite | After history-rewriting operations such as amend or rebase | Record mapping between old and new commits |

Some hooks can run in multiple situations. For example, post-checkout receives the previous commit ID, the new commit ID, and a flag indicating whether the operation was a branch checkout.

pre-push receives the remote name and remote address as arguments, as well as the list of refs being pushed via standard input. The hook can reject the push with a non-zero exit code.

## 4. Server-Side Hooks

Server-side hooks run on the Git server. For self-managed Git repositories, hooks usually reside in the hooks directory of a bare repository or the repository receiving pushes. They are invoked by the process handling incoming Git data, typically receive-pack.

Important server-side hooks:

| Hook | When It Runs | Scope |
|---|---|---|
| pre-receive | Once for the entire push, before updating refs | Can reject the entire push |
| update | Once for each updated ref | Can reject individual refs |
| post-receive | After refs are successfully updated | Notify or trigger downstream workflows |
| post-update | After refs are successfully updated | Receives the list of updated ref names |
| push-to-checkout | When a push updates the currently checked-out branch in a repository with a working tree and receive.denyCurrentBranch=updateInstead enabled | Coordinates updating the working tree on the receiving side |

A bare repository is usually the right choice for a server receiving pushes because it does not have a working tree being used as an active workspace.

### 4.1. pre-receive: Checking the Entire Push

pre-receive runs once when the server receives a push. Git passes one line per ref update via standard input:

~~~text
<old-object-id> <new-object-id> <ref-name>
~~~

Where:

- old-object-id: the current object of the ref on the server.
- new-object-id: the object the pusher wants to update to.
- ref-name: the full name of the ref, such as refs/heads/main or refs/tags/v1.2.0.

For a new ref, the old value is an all-zero object ID. For a ref deletion, the new value is an all-zero object ID.

If pre-receive returns a non-zero exit code, the entire push is rejected. This is the right place to enforce a policy that applies uniformly to all refs in the same push.

Skeleton example allowing updates only to branches starting with feature/ in a test repository:

~~~sh
#!/bin/sh

while read old_oid new_oid ref_name
do
    case "$ref_name" in
        refs/heads/feature/*)
            ;;
        *)
            echo "Only feature/* branch updates are allowed in the test repository." >&2
            exit 1
            ;;
    esac
done

exit 0
~~~

This only illustrates how to read the ref list and reject a push. Actual policies must match how the team integrates changes. If a platform creates merge commits using its own mechanism, check how the platform interacts with hooks before applying rules.

### 4.2. update: Checking Each Ref

The update hook is invoked separately for each ref. It receives three arguments:

~~~text
<ref-name> <old-object-id> <new-object-id>
~~~

Skeleton example rejecting updates to a protected branch:

~~~sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

if [ "$ref_name" = "refs/heads/main" ]; then
    echo "Branch main must be updated through the review workflow." >&2
    exit 1
fi

exit 0
~~~

If update returns a non-zero code, that specific ref is rejected. Other refs in the same push can still be updated if the remaining checks succeed. This is an important difference compared to pre-receive, which rejects the entire push.

### 4.3. post-receive: Processing After Refs Are Updated

post-receive runs after the server successfully updates refs. It receives the list of old objects, new objects, and ref names via standard input just like pre-receive.

This hook is suitable for:

- Sending notifications about new commits.
- Recording release events.
- Queuing build or deployment jobs.
- Updating change-tracking systems.

post-receive cannot reject a push because the refs have already been updated. If downstream work fails, report an error or create a separate remediation task; you cannot use the hook's exit code to roll back a successful push.

Avoid running a long deployment pipeline directly inside post-receive if doing so holds the push-receiving process open for too long. It is better to enqueue an event or call an orchestration service with explicit timeouts and retry mechanisms.

## 5. Installing Client Hooks in a Local Repository

### 5.1. Finding the Default Hooks Directory

Inside the repository, run:

~~~sh
git rev-parse --git-path hooks
~~~

This command returns the path to the hooks directory inside the Git directory. Typically, sample hooks are located in this directory with a .sample suffix. If core.hooksPath is configured, Git uses the configured directory instead of the default one; check that value when troubleshooting.

For example:

~~~text
pre-commit.sample
commit-msg.sample
pre-push.sample
~~~

Git does not automatically run files with the .sample suffix. To install a hook, create or rename the file to the exact hook name, such as pre-commit, and ensure the file has execute permissions on operating systems that enforce those permissions.

### 5.2. Creating Your First Hook

Create a pre-commit file in the hooks directory:

~~~sh
#!/bin/sh
set -eu

echo "Checking whitespace in staged changes..."
git diff --cached --check
~~~

This hook checks staged content before committing. If git diff --cached --check detects whitespace errors, the command returns a non-zero exit code and the commit is aborted.

On Linux or macOS, grant execute permission:

~~~sh
chmod +x .git/hooks/pre-commit
~~~

The .git/hooks path in the example is the default location for a standard repository. If Git uses core.hooksPath or a different git directory, use the path returned by git rev-parse --git-path hooks.

### 5.3. Verifying Whether the Hook Runs

Make a test change, stage it, and commit:

~~~sh
git add README.md
git commit -m "docs: update readme"
~~~

Observe the hook's output. If the hook returns a non-zero exit code, Git will not create the commit. If the hook does not run, check:

- The filename matches the exact hook name without .sample.
- The file has execute permission.
- The hook is inside the directory Git is currently using.
- The shebang points to an existing interpreter.
- Whether core.hooksPath is configured to point to a different directory.

## 6. Using core.hooksPath to Manage Hooks in a Repository

By default, hooks live inside the internal Git directory and are not committed like regular source code. To store hook scripts in the repository, a team can place them in a tracked directory, such as .githooks.

Structure:

~~~text
store-app/
├── .githooks/
│   ├── pre-commit
│   ├── commit-msg
│   └── pre-push
├── .gitignore
└── src/
~~~

Some hooks, especially push-related hooks, may run from the Git directory rather than the working tree. To ensure the same hooks directory is found in every context, configure an absolute path:

~~~sh
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

This command stores the absolute path in the local configuration of the current repository. The .git/config file is not shared through clone, so the team needs to provide a clear setup step.

On Windows, how scripts are executed and how execute permissions behave depend on Git for Windows, the shell, and the core.filemode setting. Use an interpreter available in the team's environment and test hooks across all supported operating systems.

### 6.1. Marking Hook Files as Executable

For repositories using a filesystem that supports executable bits:

~~~sh
chmod +x .githooks/pre-commit
git add .githooks/pre-commit
git ls-files --stage .githooks/pre-commit
~~~

Git normally records mode 100755 for executable files and 100644 for regular files. Checking the mode helps avoid cases where a hook is committed but fails to execute on Linux/macOS machines.

### 6.2. Installing Hooks After Cloning

Because local configuration is not cloned with the repository, teams can provide a setup script:

~~~sh
#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
echo "Git hooks configured for this repository."
~~~

Users run the script after inspecting its contents and understanding which hooks will be enabled. Never automatically run hook code from an untrusted repository without reviewing it, because hooks can execute commands with the user's privileges.

## 7. Client-Side Hook Examples

### 7.1. pre-commit Checking Staged Content

File .githooks/pre-commit:

~~~sh
#!/bin/sh
set -eu

git diff --cached --check
~~~

This hook only checks staged content. If a file has been modified but not staged, those changes are outside the scope of git diff --cached.

If you want to run a formatter or linter only on staged files, determine the file list and invoke the appropriate tool. Avoid running a formatter across the entire repository and accidentally modifying files that do not belong to the current commit.

### 7.2. commit-msg Checking Message Conventions

File .githooks/commit-msg:

~~~sh
#!/bin/sh
set -eu

message_file=$1

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]_.-]+\))?: .+' "$message_file"; then
    echo "Commit message must follow the format type(scope): subject." >&2
    echo "Example: feat(auth): add refresh token support" >&2
    exit 1
fi
~~~

The hook receives the path to the message file as its first argument. If the content does not match the convention, the hook returns exit code 1 and the commit is rejected.

The regex in the example is a simple convention. If a project has more complex rules, use a single unified validator in both local hooks and CI to avoid divergent interpretations.

### 7.3. pre-push Running Checks Before Sharing

File .githooks/pre-push:

~~~sh
#!/bin/sh
set -eu

echo "Running tests before push..."
npm test
~~~

If npm test fails, the push is aborted. This example fits a Node.js repository; projects using other tools should substitute the corresponding test command.

pre-push may run once for a push operation involving multiple refs. If you need to check each ref individually, the hook can read the ref list from standard input. Avoid assuming the hook only runs when pushing a single branch.

### 7.4. post-merge Updating the Local Environment

A post-merge hook can remind users to install dependencies after merging:

~~~sh
#!/bin/sh
echo "If dependencies changed, run the installation command according to the project guide."
~~~

This hook only runs after the merge completes. It cannot cancel the merge if a command inside the hook fails. For checks that must be mandatory, place them in a step capable of rejecting before completion or in CI.

## 8. Which Hooks Can Reject an Operation?

Not every hook has the same level of control. It is important to distinguish hooks that run before an event from those that run after it.

| Hook | Can Abort the Main Operation? | Notes |
|---|---|---|
| pre-commit | Yes | Non-zero exit code prevents creating the commit |
| prepare-commit-msg | Can cause the command to fail if the hook errors | Used to prepare the message; not bypassed by --no-verify |
| commit-msg | Yes | Non-zero exit code prevents creating the commit |
| pre-merge-commit | Yes | Can prevent creating the merge commit |
| post-commit | No | The commit has already been created |
| pre-rebase | Yes | Can refuse to start the rebase |
| pre-push | Yes | Non-zero exit code prevents the push from the client |
| pre-receive | Yes | Can reject the entire push on the server |
| update | Yes | Can reject a specific ref |
| post-receive | No | Refs have already been updated |
| post-update | No | Runs after refs have been updated |

When designing a workflow, place blocking checks at the right point. Do not use post-event hooks to try to prevent an operation that has already completed.

## 9. How Do Client Hooks and Server Hooks Differ?

| Criterion | Client-Side Hook | Server-Side Hook |
|---|---|---|
| Where It Runs | Developer's machine | Server receiving or hosting the repository |
| Who Manages It? | User or team setup script | Server administrator or platform |
| Timing | Before/after commit, checkout, rebase, push... | Before/after the server receives and updates refs |
| Primary Purpose | Early feedback, assisting local operations | Enforcing centralized policies |
| Can Users Bypass It? | Some hooks can be bypassed or disabled | Cannot be bypassed via client --no-verify options |
| Automatically Cloned? | No, the hooks directory and local config are not shared by default | No, installed on the server |
| Examples | pre-commit linting, pre-push testing | branch protection, ref validation, push logging |

Client hooks help users avoid submitting broken changes, but they should never be the sole control layer for critical policies. Users may skip installing hooks or bypass some of them. Server hooks or branch protection are where centralized policies are enforced.

## 10. Can Hooks Be Bypassed?

Several Git commands support options to bypass client-side hooks:

~~~sh
git commit --no-verify
git push --no-verify
~~~

git commit --no-verify bypasses pre-commit and commit-msg hooks. It does not bypass prepare-commit-msg.

git push --no-verify bypasses the client-side pre-push hook. Server-side hooks still run when the server receives the push.

Additionally, users can configure core.hooksPath to point to another directory or one with no hooks. Therefore:

- Use client hooks for fast feedback and convenience.
- Use CI to verify changes in a controlled environment.
- Use server hooks or branch protection policies to enforce mandatory rules.

Avoid overusing --no-verify. If a hook must be bypassed due to an environment issue or emergency, clearly document the reason and run the alternative checks according to team process.

## 11. Hooks Are Not Automatically Shared via Clone or Push

The default hooks directory resides inside the Git directory, typically .git/hooks. The .git directory is not committed like regular source code. When others clone the repository, sample hooks may appear, but they are not automatically configured to execute.

This means:

- Committing a .githooks/pre-commit file does not automatically run the hook on teammates' machines.
- Pushing a repository does not automatically install server hooks on the remote.
- Local core.hooksPath configuration does not travel with a clone.
- Each person must run the setup step or use the agreed hook management tool.

Some projects use frameworks such as pre-commit, Husky, or Lefthook to manage hook installation and execution. These tools are a convenience layer on top of Git's hook mechanism; the team still needs to understand where hooks are installed and which checks are actually running.

For organization-managed servers, hooks must be installed and maintained on the server. When using a Git hosting service, the ability to install custom server hooks depends on the service plan and administrative permissions. You may need to rely on the platform's branch protection, required status checks, or merge rules instead.

## 12. Designing Reliable Hooks

A good hook should be fast, clear, and produce consistent results.

### 12.1. Keep Hooks Short and Focused

Each hook should have one primary responsibility. For example:

- pre-commit: whitespace checks and fast linting.
- commit-msg: message structure validation.
- pre-push: running relevant tests before sharing.
- pre-receive: enforcing ref policies on the server.
- post-receive: queuing events.

If a single hook performs too many tasks, it becomes difficult to tell which step caused a commit or push to fail. You can split scripts into smaller programs and call them from the hook.

### 12.2. Error Messages Must Explain How to Fix the Issue

A message like "hook failed" does not help the user resolve the problem. State:

- Which check failed.
- The related file or commit.
- The command to re-run the check.
- How to fix it or which documentation to read.

Example:

~~~sh
echo "Commit message does not follow the convention." >&2
echo "Use: feat(scope): description of the change" >&2
exit 1
~~~

### 12.3. Avoid Unstable Environment Dependencies

Hooks may run across multiple operating systems and shells. Avoid assuming:

- An absolute path that exists only on the author's machine.
- A specific runtime or package manager version is already installed.
- The network is always available.
- External services always respond quickly.
- Everyone uses the same shell.

If dependencies are required, check for them explicitly and print installation instructions. Use timeouts for tasks that risk hanging indefinitely. For heavy checks or checks requiring external services, CI is usually a better fit.

### 12.4. Preserve Staging State

pre-commit should inspect only the staged content. If a hook automatically formats files in the working tree, it can make the working tree differ from the index. As a result, the created commit may not contain what the user just observed.

If a hook modifies files, there must be a re-staging workflow or a tool that processes only staged content. Always document clearly whether a hook modifies files automatically or only checks them.

### 12.5. Protect Data and Execution Privileges

A hook is a program executing with the privileges of the account running Git. A malicious hook can read files, make network requests, or run system commands within those privileges.

Therefore:

- Review hooks just like regular source code.
- Do not run hooks from untrusted repositories without inspecting them first.
- Do not hardcode tokens or passwords into hook scripts.
- Do not print secrets to the terminal or logs.
- Restrict the permissions of the server account running hooks.
- Validate inputs from ref names, commit messages, and standard input before using them in a shell.
- Avoid interpolating input strings directly into shell commands without proper escaping or handling.

## 13. Organizing Checks Across Hooks, CI, and Server Policies

Do not cram every check into a single hook. Each layer has a distinct role:

| Layer | Appropriate Checks | Benefits |
|---|---|---|
| pre-commit | whitespace, fast formatting, linting staged files | Immediate feedback on the developer's machine |
| commit-msg | message structure, ticket IDs | Keeps commit history consistent |
| pre-push | fast unit tests, local branch checks | Catches errors before sending |
| CI | clean build, full test suite, security scans | Consistent environment, centralized logs and results |
| Server hook / branch protection | ref update permissions, required reviews, required checks | Enforces policy for every contributor |
| post-receive | notifications, queuing builds/deployments | Triggers workflows after changes are received |

For example, a team might run fast linting in pre-commit, selective unit tests in pre-push, full tests and security scans in CI, and require passing CI plus code review before merging into main.

Checks should have a single source of truth. If local hooks and CI use two different rule sets, developers may see hooks pass while CI fails. Share common check scripts whenever appropriate.

## 14. Example Policy Implementation Flow

Suppose a team wants to:

- Check whitespace before committing.
- Enforce commit message conventions.
- Run tests before pushing.
- Prevent direct pushes to the main branch on the server.
- Trigger CI after the server receives a branch.

One way to organize this:

1. Store the pre-commit, commit-msg, and pre-push scripts in .githooks.
2. Provide a setup script to configure core.hooksPath.
3. Install pre-receive or configure branch protection on the server to protect main.
4. Configure CI to run when branches are pushed or pull requests are updated.
5. Use post-receive to send events to a queue or notify the CI system if the architecture requires it.
6. Require code review and passing CI before merging.

This flow provides early feedback on the developer's machine and centralized verification where the repository is hosted. If a user bypasses client hooks, the server and CI still enforce the mandatory conditions.

## 15. Git Hooks Implementation Checklist

**Choosing Hook Location and Type**

- [ ] Identify the event that needs to be checked or automated.
- [ ] Choose a client hook or server hook based on where enforcement is required.
- [ ] Distinguish between hooks that can reject an operation and post-event hooks.
- [ ] Place mandatory policies on the server or repository management platform.

**Installation**

- [ ] Check the hooks directory with git rev-parse --git-path hooks.
- [ ] Name the file to match the exact hook name, removing the .sample suffix.
- [ ] Ensure the interpreter and execute permissions are properly set.
- [ ] If using .githooks, configure core.hooksPath and provide a setup step.
- [ ] Test on all operating systems and shells supported by the team.

**Operations**

- [ ] Hooks run fast enough and include timeouts where needed.
- [ ] Error messages clearly state the cause and how to fix it.
- [ ] Do not unexpectedly modify staged content.
- [ ] Do not log or expose secrets.
- [ ] Include logging and error handling for server hooks.
- [ ] Re-verify critical conditions in CI.

**Maintenance**

- [ ] Review hook changes like source code.
- [ ] Verify compatibility when upgrading Git or runtime versions.
- [ ] Remove hooks that are no longer used.
- [ ] Document how to install, test, and bypass hooks when permitted.

## 16. Conclusion

Client-side hooks and server-side hooks both help automate Git workflows, yet they serve two different roles. Client-side hooks run close to the developer, catching errors early before a commit or push. Server-side hooks run where changes are received, enforcing centralized policies and handling events after refs are updated.

Use client hooks for fast feedback, CI for consistent verification, and server hooks or branch protection for mandatory rules. Manage hooks as executable code requiring code review, clear installation steps, and understandable output. This division keeps automation useful while preserving control and traceability across the collaborative workflow.

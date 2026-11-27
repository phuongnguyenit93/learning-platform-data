# Organizing Shared Hooks with core.hooksPath

## Why Organize Shared Hooks?

Git hooks are programs that Git invokes automatically at specific points in a workflow, such as before committing, after checking out, or before pushing. Hooks can check formatting, run tests, validate commit messages, inspect staged changes, or perform other automated tasks.

By default, Git looks for hooks in the repository's hooks directory, usually .git/hooks. Sample files there typically have a .sample extension and are not executable. This directory resides inside the clone's internal Git metadata, not as content committed alongside source code. Consequently, hooks created directly in .git/hooks normally exist only on the machine where they were installed.

When a team wants every member to use the same set of hooks, they can place the scripts in a Git-tracked directory such as .githooks/, then configure core.hooksPath so Git looks for hooks there.

This organization enables:

- Storing hook scripts in repository history for everyone to review and update.
- Using consistent verification rules before commits or pushes.
- Reducing manual copying of scripts into .git/hooks by each member.
- Versioning hooks through commits and pull requests.
- Separating project hook scripts from personal hooks used across multiple repositories.

It is important to understand that core.hooksPath only tells Git which directory to search for hooks. It does not automatically download, install, or execute scripts from the repository upon clone. Each clone must be configured to use the project's hooks directory.

## Where Does Git Look for Hooks?

If core.hooksPath is not configured, Git uses the default hooks directory inside the repository's Git directory, typically .git/hooks.

Check the Git directory path:

~~~bash
git rev-parse --git-dir
~~~

If you want to see the repository's root path:

~~~bash
git rev-parse --show-toplevel
~~~

When core.hooksPath is configured, Git searches for hooks in the specified directory instead of the default hooks directory. For example:

~~~bash
git config --local core.hooksPath .githooks
~~~

If the repository has the structure:

~~~text
inventory-app/
├── .git/
├── .githooks/
│   ├── pre-commit
│   ├── commit-msg
│   └── pre-push
├── src/
└── README.md
~~~

Git will look for files with exact names like pre-commit, commit-msg, and pre-push inside .githooks/.

Hook filenames must match the exact hook name that Git invokes. Do not add a .sh extension if you want Git to find the hook by its standard name. For instance, .githooks/pre-commit.sh will not be recognized automatically by Git as the pre-commit hook; the filename must be .githooks/pre-commit.

### core.hooksPath Replaces the Default Directory

When core.hooksPath is set, Git uses that directory instead of the default hooks directory. Git does not automatically merge both directories.

This means:

- Hooks located in .git/hooks may no longer be invoked.
- Hooks located in the new core.hooksPath directory will be looked up by standard names.
- If you want to retain both personal hooks and project hooks, you need a chaining mechanism or merged logic.

Never assume that setting core.hooksPath adds a second search directory.

## Creating a Git-Managed Hooks Directory

In the repository root, create .githooks:

~~~bash
mkdir -p .githooks
~~~

On PowerShell, you can use:

~~~powershell
New-Item -ItemType Directory -Force .githooks
~~~

Then create the required hook files. For example:

~~~text
.githooks/
├── pre-commit
├── commit-msg
└── pre-push
~~~

Add only hooks that genuinely serve the project workflow. Each hook should have a clear responsibility, understandable error messages, and an execution time appropriate for when it is invoked.

A repository may only need pre-commit to check whitespace and formatting; it is not necessary to install every hook Git supports.

### Placing Hook Scripts in the Repository

Example of a simple pre-commit hook:

~~~sh
#!/bin/sh
set -eu

echo "Checking staged changes..."

if ! git diff --cached --check; then
    echo "Commit stopped: fix whitespace errors in staged changes."
    exit 1
fi

echo "Staged changes passed the whitespace check."
~~~

This hook checks staged changes. If Git detects whitespace errors, the script returns a non-zero exit code and Git stops the commit operation.

Use git diff --cached instead of git diff because the goal of pre-commit is typically to inspect the exact content slated to be written into the commit. Running only git diff may overlook staged changes.

Example commit-msg validating message conventions:

~~~sh
#!/bin/sh
set -eu

message_file=$1

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]./_-]+\))?: .+' "$message_file"; then
    echo "Commit message must follow: type(scope): description"
    exit 1
fi
~~~

Git passes the path of the commit message file as the first argument to the commit-msg hook. The script reads that file and returns a non-zero code if the message does not follow the convention.

Minimal pre-push example:

~~~sh
#!/bin/sh
set -eu

echo "Running checks before push..."
./gradlew test
~~~

This example assumes the repository has Gradle Wrapper and the hook execution environment can run that command. If the project uses Maven, Node.js, or another tool, substitute the appropriate command. Do not put a tool-specific test command into a shared hook if team members lack the required runtime or dependencies.

The scripts above are illustrative examples. When implementing for real projects, define the supported shells, runtimes, tool paths, and operating systems.

## Configuring core.hooksPath for the Repository

Once .githooks contains the scripts, configure the repository locally:

~~~bash
git config --local core.hooksPath .githooks
~~~

Verify the value:

~~~bash
git config --local --get core.hooksPath
git config --show-origin --show-scope --get core.hooksPath
~~~

Local settings are stored in the current clone's configuration, typically .git/config. The .git/config file is not committed with the repository, so other team members will not automatically receive this setting upon pull.

To avoid depending on the current working directory or how Git invokes a hook, you can configure an absolute path computed from the repository root.

Bash example:

~~~bash
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

PowerShell example:

~~~powershell
$repoRoot = git rev-parse --show-toplevel
$hooksPath = Join-Path $repoRoot ".githooks"
git config --local core.hooksPath $hooksPath
~~~

Git accepts either relative or absolute paths. For relative paths, Git resolves them relative to the hook's working directory; most hooks in non-bare repositories run from the working tree root, though differences exist across hook types and repository contexts. Using an absolute path in setup scripts avoids this confusion.

Never commit a personal machine's absolute path into tracked files. Let the setup script calculate the path in each clone and write it to local config.

## Granting Execute Permissions to Hooks

Git only runs a hook if the hook file is executable in the environment. On Linux and macOS, set the executable bit:

~~~bash
chmod +x .githooks/pre-commit
chmod +x .githooks/commit-msg
chmod +x .githooks/pre-push
~~~

Stage the file mode changes so Git records the executable bit:

~~~bash
git add .githooks
git ls-files --stage -- .githooks
~~~

An executable file normally has mode 100755; a regular file has mode 100644.

On Windows, behavior depends on Git for Windows, the shell, and the execution environment. Git Bash typically provides a shell for running POSIX scripts; test actual hooks on the Git for Windows version supported by the team. You can set the executable mode in the index with:

~~~bash
git add .githooks/pre-commit
git update-index --chmod=+x .githooks/pre-commit
git ls-files --stage -- .githooks/pre-commit
~~~

If a file was already staged before changing modes, re-check git ls-files --stage and re-stage as needed.

### Using Appropriate Line Endings

Shell scripts should use LF to avoid errors like /bin/sh^M when running in POSIX environments. You can enforce this in .gitattributes:

~~~gitattributes
.githooks/* text eol=lf
~~~

This rule ensures Git checks out hooks in .githooks with LF line endings. If the repository has dedicated Windows scripts, configure appropriate attributes per file type.

Avoid converting line endings in bulk when you only intend to add hooks. Inspect diffs and attributes for the exact files affected.

## Sharing Hooks with New Team Members

Because core.hooksPath is configured locally, an onboarding step is needed so every member enables hooks after cloning.

A common workflow:

1. Clone the repository.
2. Read the hook guide and inspect the scripts in .githooks.
3. Run the project's setup script or local git config command.
4. Verify core.hooksPath and execute permissions.
5. Make a test commit on a personal branch or run an appropriate hook test command.

You can document the setup command in onboarding docs:

~~~bash
git config --local core.hooksPath .githooks
~~~

Or provide a setup script to compute the path automatically:

~~~sh
#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"

echo "Git hooks are configured from $repo_root/.githooks"
~~~

This example can be saved in scripts/setup-hooks.sh. Team members run it once after cloning:

~~~bash
sh scripts/setup-hooks.sh
~~~

Setup scripts should be reviewed just like any other script in the repository. git clone does not automatically run setup scripts nor automatically configure core.hooksPath from committed files.

### Why Does Git Not Automatically Enable Hooks from a Cloned Repository?

A hook is a program capable of running arbitrary commands on the user's machine. If cloning any repository automatically activated hook scripts provided by that repository, malicious code could execute during subsequent commits or pushes.

Therefore, Git does not automatically install hooks committed inside a project directory. Users must actively configure core.hooksPath after inspecting and trusting the script contents.

This is a critical security boundary: review hooks before enabling them, especially for repositories outside your organization.

## Using core.hooksPath Globally and Locally

core.hooksPath can be configured at multiple scopes.

### Global Configuration for Personal Hooks

If you want to use a personal set of hooks across multiple repositories, create a directory outside your repositories, such as:

~~~text
~/.config/git/hooks/
├── pre-commit
└── post-checkout
~~~

Global configuration:

~~~bash
git config --global core.hooksPath ~/.config/git/hooks
~~~

This setting applies to repositories of the current user unless overridden by a higher-precedence config.

This suits personal hooks like reminders, local tool checks, or utility tasks. Do not place mandatory project rules in a personal directory that is not centrally managed.

### Local Configuration for Project Hooks

Inside a repository that needs project hooks:

~~~bash
git config --local core.hooksPath .githooks
~~~

Local config takes higher precedence than global config for the single-valued core.hooksPath key. Thus, the repository can use the project's hook set instead of the personal hook set.

### Two Hook Directories Are Not Automatically Combined

If global points to a personal hooks directory and local points to the project's .githooks, Git uses the local value. It does not automatically search for hooks in both places.

If a team needs both organization-wide hooks and project-specific hooks, you can:

- Create a hook dispatcher in the chosen directory that calls sub-scripts in sequence.
- Package shared hooks as a library/script invoked by project hooks.
- Use a hook management tool capable of merging configurations with clear documentation.

A dispatcher must check errors and return the appropriate exit code. If a child hook fails, the dispatcher must propagate the failure back to Git when the goal is to block the operation.

Do not set two core.hooksPath configs expecting Git to automatically merge the contents of two directories.

## Choosing the Right Hook for Each Stage

Git provides many hook types. Common hooks include:

| Hook | Timing | Common Purpose |
|---|---|---|
| pre-commit | Before creating a commit | Lint, format check, staged diff check |
| prepare-commit-msg | After Git creates initial content, before opening editor | Prepare or supplement message |
| commit-msg | After user enters message, before commit | Validate commit message convention |
| post-commit | After commit completes | Notifications or auxiliary tasks |
| pre-push | Before pushing refs to remote | Run tests or check sharing conditions |
| pre-rebase | Before rebase starts | Prevent rebase in certain situations |
| post-checkout | After checkout or switch | Update branch-dependent tooling |
| post-merge | After merge completes | Update dependencies or notify |

Hooks may receive arguments and data via stdin depending on type. Before writing a script, read the documentation for that exact hook to understand its invocation contract.

For example, pre-push receives the remote name and URL via arguments, while the ref list is sent via stdin. Scripts must parse the exact format to inspect branches or commits being pushed. Never assume all hooks receive the same arguments.

### Choosing Fast Checks for pre-commit

Pre-commit typically runs on every commit creation, so prioritize fast checks on staged content. Long tasks like full integration test suites can slow down development if run on every commit.

Checks can be divided as follows:

- pre-commit: whitespace, formatting, fast lint, secret scanning on staged files.
- commit-msg: message convention and issue IDs.
- pre-push: unit tests or broader checks.
- CI: full test suite, integration tests, and environment checks.

This division gives developers early feedback without waiting for an entire pipeline before every commit.

## Designing Maintainable Hooks

A shared hook suite should have these traits:

- **Clear purpose:** each hook enforces an explainable rule.
- **Idempotent:** running multiple times does not produce unintended changes.
- **Clear messages:** identifies the file or condition needing correction.
- **Appropriate speed:** avoid running heavy tasks on every commit if they can move to pre-push or CI.
- **Minimal dependencies:** rely on tools already in the team's environment or check availability before running.
- **Cross-platform compatibility:** standardize supported shells, runtimes, and line endings.
- **No data leaks:** never print or store tokens, passwords, or secret contents.
- **Testable:** scripts can run standalone or hooks can be triggered in a test repository.

Avoid letting hooks silently auto-modify files in bulk without notifying the user. If a formatter hook alters content, require the user to inspect the diff and re-stage changes after confirmation.

Hooks should exit with code 0 when checks pass. For blocking hooks, return a non-zero exit code when conditions fail and print remediation instructions. Post-event hooks such as post-commit run after the operation has finished; they cannot abort a newly created commit.

## Inspecting and Debugging Hooks

If a hook does not run, check in order:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
git rev-parse --show-toplevel
git status
git ls-files --stage -- .githooks
~~~

Confirm:

1. core.hooksPath points to the right directory.
2. The hook file has the exact name, such as pre-commit.
3. The file exists inside the configured directory.
4. The file has execute permissions for the environment.
5. The shebang points to an available shell.
6. Line endings and encoding are appropriate.
7. The script does not rely on missing environment variables or uninstalled tools.
8. The hook is being triggered by the right Git operation.

You can run the script directly from a shell to check syntax and internal commands, keeping in mind that environment variables and arguments may differ when Git invokes the hook. For hooks receiving arguments or stdin, test in a temporary repository simulating the exact input data.

Some Git versions support a hook testing command:

~~~bash
git hook run pre-commit
~~~

If your Git version lacks this command, trigger the corresponding operation in a test repository or run the script directly with sample input.

### Checking Whether Hooks Use the Default Directory

Once core.hooksPath is set, hooks in .git/hooks may no longer be called. If an older hook stops working after configuring .githooks, verify whether that script needs to be migrated or called from the new hook suite.

You can remove the local setting to revert to the default directory:

~~~bash
git config --local --unset core.hooksPath
~~~

If global still sets core.hooksPath, Git will use the global value. If no value is set at other scopes, Git falls back to the default hooks directory.

To unset global configuration:

~~~bash
git config --global --unset core.hooksPath
~~~

Always verify the effective value after unsetting:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
~~~

## Handling Bypassed or Non-Executing Hooks

Some commands support options to skip certain hooks, for example:

~~~bash
git -c core.hooksPath=/dev/null commit -m "Temporary local commit"
~~~

Or:

~~~bash
git commit --no-verify
git push --no-verify
~~~

The --no-verify option bypasses certain blocking hooks such as pre-commit, commit-msg, or pre-push depending on the command. Not all hooks are bypassed by this option; for example, prepare-commit-msg is not bypassed that way.

Bypassing hooks can be useful in team-approved emergencies, but should not become a routine way to evade quality rules. If a rule is mandatory, enforce it in CI or on the server as well.

The /dev/null path is a common way to disable hooks on Unix-like environments. On Windows, check how Git for Windows handles special paths before using them in shared scripts or guides.

## Client-Side Hooks Do Not Replace Server-Side Checks

Hooks configured via core.hooksPath run on the user's machine. Users might not install hooks, might use a different configuration, or might bypass certain hooks. Thus, client hooks are good for early feedback and encouraging convention compliance, but are not the sole protective boundary.

If a policy must apply to every change, verify it where centralized enforcement is possible:

- CI running on pull requests.
- Branch protection or merge checks.
- Server-side hooks such as pre-receive or update if the platform supports them.
- Code review and approval workflows.

For example, pre-commit secret scanning catches leaks early on the developer's machine. CI or server-side controls must still scan as well in case hooks were bypassed or never installed.

## Sample Workflow for Deploying Shared Hooks

Suppose a team wants every commit to check whitespace and every commit message to follow type(scope): description.

### Step 1: Create the Directory and Hooks

~~~bash
mkdir -p .githooks
~~~

Create .githooks/pre-commit:

~~~sh
#!/bin/sh
set -eu

git diff --cached --check
~~~

Create .githooks/commit-msg:

~~~sh
#!/bin/sh
set -eu

message_file=$1
if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]./_-]+\))?: .+' "$message_file"; then
    echo "Use: type(scope): description"
    exit 1
fi
~~~

### Step 2: Ensure Execute Permissions and Line Endings

On Linux/macOS or Git Bash:

~~~bash
chmod +x .githooks/pre-commit .githooks/commit-msg
~~~

You can add a rule in .gitattributes:

~~~gitattributes
.githooks/* text eol=lf
~~~

Stage and verify modes:

~~~bash
git add .githooks .gitattributes
git ls-files --stage -- .githooks
~~~

### Step 3: Configure core.hooksPath

~~~bash
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

Verify:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
~~~

### Step 4: Test the Hooks

Stage a change and try committing with a valid message:

~~~bash
git add src/example.txt
git commit -m "docs(readme): update setup instructions"
~~~

Try an invalid message in a test repository:

~~~bash
git commit -m "update stuff"
~~~

The commit-msg hook should reject the non-compliant message. When a commit is rejected, fix the message and try again.

### Step 5: Share and Document Installation

Commit .githooks and .gitattributes to the repository. Update project onboarding documentation so new team members run the local configuration command after cloning.

Do not commit .git/config or machine-specific absolute paths. Each person configures core.hooksPath in their own clone via a reviewed setup script or guide.

## Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Hook in .githooks does not run | core.hooksPath not yet configured | Set local config and verify origin |
| Hook in .git/hooks stopped running | core.hooksPath replaced the default directory | Move retained logic to the new directory or a dispatcher |
| Hook not found | Filename has an extension or wrong standard name | Use exact names such as pre-commit, commit-msg |
| Hook ignored on Linux/macOS | Missing executable bit | Run chmod +x and check mode 100755 |
| Hook fails with /bin/sh^M | File uses CRLF | Normalize shell scripts to LF |
| Hook runs on one machine but fails on another | Missing shell/runtime or dependent command | Standardize environment and check tools before running |
| Hook takes too long | Heavy full test suite placed in pre-commit | Move broad tests to pre-push or CI |
| Team member clones but has no hooks | Git does not auto-enable scripts from repository | Provide setup step and clear instructions |
| Personal hooks vanish when enabling project hooks | Local core.hooksPath overrides global | Use a dispatcher or invoke shared hooks from project hooks |
| Rules still violated despite having hooks | User bypassed or skipped installing hooks | Add mandatory checks in CI/server |

## Checklist for Organizing Shared Hooks

- [ ] Hooks are stored in a Git-managed directory, such as .githooks/.
- [ ] Filenames match Git-supported hook names.
- [ ] Scripts have appropriate shebang, line endings, and execute permissions.
- [ ] core.hooksPath is properly configured for each clone.
- [ ] New members have setup instructions or a setup script.
- [ ] Scripts are reviewed before enabling and provide clear error messages.
- [ ] Each hook runs only checks appropriate for its invocation stage.
- [ ] Shared hooks are compatible with the team's operating systems and toolchain.
- [ ] Hooks do not print or store secrets.
- [ ] Mandatory rules are also verified in CI/server.
- [ ] A strategy for combining project hooks with personal hooks is defined if needed.
- [ ] Hooks have been tested in a test repository before broad rollout.

## Key Takeaways

core.hooksPath lets Git locate hooks in a directory of your choice instead of .git/hooks. Teams can store scripts in .githooks/ for review and version control, then instruct each clone to configure core.hooksPath locally. Git does not auto-enable hooks on clone and does not combine multiple hook directories; a local setting overrides a global setting. Ensure exact filenames, execute permissions, and line endings, design fast and understandable scripts, audit security before enabling, and rely on CI or server-side checks for rules that must be enforced strictly.

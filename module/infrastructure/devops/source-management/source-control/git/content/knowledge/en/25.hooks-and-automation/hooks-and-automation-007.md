# Checking Formatting, Messages, and Secrets in the Commit Flow

A good commit needs more than a technically accurate diff. Files should follow the project's formatting style, commit messages must clearly explain the change, and content committed into history must never contain tokens, passwords, or secret keys. Git hooks enable automatic verification of these rules at the right points in the commit and push workflow. When properly designed, checks run early, report actionable errors, and help the team keep history quality consistent.

## 1. The Commit Flow and Appropriate Placement for Each Check

Git provides hooks that run at different moments. For checking formatting, messages, and secrets, the most important hooks are usually:

| Hook | Execution Timing | Suitable Checks |
|---|---|---|
| `pre-commit` | Before Git creates a commit | Formatting, lint, fast tests, secret scanning in staged content |
| `prepare-commit-msg` | After Git prepares the message file, before opening the editor | Adding templates or contextual info to the message |
| `commit-msg` | After the message has been prepared, before creating the commit | Validating message structure, conventions, and clarity |
| `post-commit` | After a successful commit | Notifications or event logging; cannot block the commit just created |
| `pre-push` | Before Git sends refs to a remote | Additional checks, broader tests, or pre-sharing scans |

Simple flow:

```text
git add
   |
   v
git commit
   |
   v
pre-commit  ---- error? ----> stop commit
   |
   v
prepare-commit-msg
   |
   v
user confirms message
   |
   v
commit-msg  ---- error? ----> stop commit
   |
   v
create commit
   |
   v
post-commit
   |
   v
git push
   |
   v
pre-push    ---- error? ----> stop push
   |
   v
remote receives updates
```

`pre-commit` fits checking the content about to be committed; `commit-msg` fits validating the message because the hook receives the path to the message file as its first argument. Do not use `post-commit` to prevent commits because it only runs after the commit has already been created.

## 2. Where Does Git Look for Hooks?

By default, hooks live in the `hooks` directory of the Git directory, usually `.git/hooks/`. Git creates several sample files with a `.sample` suffix; these sample files do not run automatically. Hooks need the exact name and execute permissions.

Check the hooks path and custom configuration:

```bash
git rev-parse --git-path hooks
git config --show-origin --get core.hooksPath
```

If `core.hooksPath` is configured, Git uses that directory instead of the default location. This is useful when a team stores hooks inside the repository, such as `.githooks/`:

```bash
git config core.hooksPath .githooks
```

Then scripts in `.githooks/` can be committed and shared with the project. However, each clone still needs to be configured to use that directory; cloning a repository does not automatically activate hooks stored in the source tree.

On shell-based systems, hooks are usually scripts with a shebang and execute permission. For example:

```sh
#!/bin/sh
echo "Running pre-commit checks..."
```

In Git for Windows, Git Bash provides a shell environment to run this kind of hook. If using a hook management tool like pre-commit or Husky, follow the installation guide for that tool and the version in use.

## 3. Checking Formatting in `pre-commit`

Formatting checks catch files that violate project style rules before creating a commit. You can use a language-appropriate formatter or linter:

| Project Type | Example Check Command |
|---|---|
| JavaScript/TypeScript with Prettier | `npx prettier --check .` |
| Python with Ruff | `ruff format --check .` |
| Python with Black | `black --check .` |
| Go | `gofmt -d .` |
| Java with Maven Spotless | `mvn spotless:check` |

The commands above are examples; use the formatter and configuration standardized by the repository. A simple hook can run a project-wide check:

```sh
#!/bin/sh
set -eu

npm run format:check
```

Save the script as `pre-commit` in the active hooks directory and grant execute permission. When the command returns a non-zero exit code, Git stops the commit so you can fix formatting and try again.

Running a project-wide check is easy to set up, though it can be slow in large repositories. For projects with many files, check only files relevant to the commit.

## 4. Checking the Exact Staged Content

A key concept in Git is that the working tree and the index can hold two different versions of the same file. Commits take content from the index, so checking only the working tree may miss what will actually be committed.

For example:

1. You edit `src/app.ts` and run `git add src/app.ts`.
2. Next, you keep editing the file without running `git add` again.
3. The working tree now has the newer version, while the index retains the previously staged version.
4. `git commit` will record the content from the index.

If a formatter checks the working tree, it might report the current file is properly formatted while the staged version is still unformatted. Therefore, hooks must inspect the exact staged snapshot.

A common approach is using `lint-staged` to run tools only on staged files. Example configuration in `package.json`:

```json
{
  "lint-staged": {
    "*.{js,jsx,ts,tsx,json,md,css}": "prettier --write",
    "*.py": "ruff format"
  }
}
```

Then the `pre-commit` hook calls:

```sh
#!/bin/sh
set -eu
npx --no-install lint-staged
```

`lint-staged` identifies staged files, runs the corresponding tool, and updates the formatted changes back into the index as part of its workflow. As a result, the commit contains the formatted version.

If you are not using an auto-staging tool, run the formatter in check mode such as `prettier --check` or `ruff format --check`, and ask the user to fix and re-stage. Avoid running a file-writing formatter across the entire working tree without accounting for unstaged edits, as doing so can alter work not yet intended for commit.

## 5. Checking Commit Messages with `commit-msg`

A commit message is concise documentation attached to history. A clear convention helps with reviews, searching, changelog generation, and understanding why a change was made. Many teams adopt Conventional Commits with the format:

```text
<type>(<scope>): <description>
```

Examples:

```text
feat(auth): add refresh token rotation
fix(api): handle empty request body
docs(git): explain worktree cleanup
refactor(parser): extract token validation
```

Commonly used `type` values are `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, and `revert`. `scope` is optional depending on team convention. An exclamation mark `!` before the colon can denote a breaking change, such as `feat(api)!: remove legacy endpoint`.

The `commit-msg` hook receives the path to the message file in `$1`. Example shell script validating the subject against a simple convention:

```sh
#!/bin/sh
set -eu

message_file=$1
subject=$(sed -n '1p' "$message_file")

if ! printf '%s\n' "$subject" | grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([[:alnum:]./_-]+\))?!?: .+'; then
    echo "Commit message must follow: type(scope): description" >&2
    exit 1
fi
```

Save the script as `commit-msg` in the active hooks directory and grant execute permission. This is an illustrative policy; adapt the list of types, scopes, and handling of automated commits to project conventions. Some teams need to allow default merge or revert messages generated by Git.

This hook validates the first line's syntax, not content quality. A syntactically valid message like `fix(api): update code` can still be too vague. Human review remains essential to ensure the description clearly states what changed and why.

## 6. Useful Rules for Writing Commit Messages

Beyond syntax validation, teams can agree on principles:

- Use imperative mood or concise action descriptions in the subject, consistent with the team's language.
- Include the change type and scope on the first line when appropriate.
- Explain the reason, context, impact, or key technical trade-offs in the body.
- Use footers for issue IDs, ticket links, or breaking change notices per convention.
- Avoid generic messages like `fix`, `update`, `changes`, or `wip` on branches being prepared for sharing.

Example of a commit message with a body:

```text
fix(auth): reject expired refresh tokens

Reject refresh tokens after their configured expiration time so that
expired sessions cannot obtain a new access token.

Refs: AUTH-241
```

Hooks can check structure, yet should not try to automatically judge full explanation quality. Use code reviews and templates to support semantic clarity.

## 7. Scanning for Secrets Before Committing

Secret scanning searches for values that might be credentials, such as:

- API keys, access tokens, and refresh tokens.
- Passwords and connection strings containing credentials.
- Private keys or signing keys.
- Cloud credentials, service account keys, and webhook secrets.
- High-entropy strings or strings matching provider token patterns.

Scanning in `pre-commit` catches leaks early before data enters a commit. Use dedicated tools like Gitleaks rather than searching for a few keywords with `grep`: secrets take many formats, use varied variable names, and may be encoded or split across lines.

Example adding Gitleaks to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.2
    hooks:
      - id: gitleaks
```

`rev` is a pinned version in the example; teams should choose an approved version and update it in a controlled manner. Install the pre-commit framework and hooks in the repository:

```bash
pre-commit install
pre-commit run --all-files
```

The first command installs the local hook to run before commits. The second runs configured checks across all tracked files, which is useful during initial setup or repository audits. In the commit workflow, the Gitleaks hook is configured to scan staged changes.

If using a custom hook script, ensure the scanner targets staged diffs or staged files. Scanning the entire working directory can miss differences between the working tree and the index or report results that do not match the commit content.

## 8. Handling Detected Secrets

When a scanner flags a string as a potential secret:

1. Abort the commit and identify the flagged file, line, or diff.
2. Verify whether it is a real secret or a false positive; never print the full secret value into logs or tickets.
3. If it is a real secret, remove it from staged content and retrieve the credential from a secret manager or environment variables at runtime.
4. Re-stage the fixed file and run the scanner again.
5. If the credential was ever committed or pushed, treat it as compromised: revoke or rotate it immediately, then assess access scope and usage logs.

Deleting a secret in a new commit does not remove its value from older commits. If a secret already entered history, handle history removal separately and coordinate with repository users; rewriting history does not replace credential revocation.

False positives can be handled via a narrowly scoped allowlist with a documented reason and review expiration. Avoid adding broad ignore rules such as an entire config directory or all token-like strings, as that can mask real secrets.

## 9. Do Not Rely Solely on Local Hooks

Local hooks normally reside in `.git/hooks/` and are not automatically shared when others clone the repository. Even when hooks are stored in `.githooks/` or configured with a tool like pre-commit, each clone still requires a setup step.

Users can also bypass certain hooks with appropriate flags, for example:

```bash
git commit --no-verify
git push --no-verify
```

`git commit --no-verify` bypasses `pre-commit` and `commit-msg`; `git push --no-verify` bypasses `pre-push`. Therefore, local hooks provide a fast feedback layer for developers, not the sole security boundary.

To enforce policies for everyone, organizations should add server-side and CI checks:

- Server-side `pre-receive` or platform push rules can reject updates containing disallowed data.
- CI can run formatters, linters, tests, and secret scans on commits or pull requests.
- Branch protection rules require status checks to pass before merging.
- Platform-level secret scanning can detect credentials in pushed content or history.

Server-side hooks and CI must inspect the exact commit range being updated, including newly pushed commits; never rely only on a personal machine's working tree.

## 10. Organizing Hooks for Team-Wide Use

Hooks can be stored in the repository, for example:

```text
project/
  .githooks/
    pre-commit
    commit-msg
    pre-push
  .pre-commit-config.yaml
  package.json
```

Set the hooks directory for the repository:

```bash
git config core.hooksPath .githooks
```

After cloning, team members must run the project's documented bootstrap step to configure hooks and install tool dependencies. Setup commands can be placed in onboarding documentation or a project setup script.

If using the pre-commit framework, store `.pre-commit-config.yaml` in the repository and instruct everyone to run `pre-commit install`. When updating hook versions, review configuration file changes like dependency code to ensure everyone runs the same set of checks.

Never store tokens or private keys in hook scripts, committed config files, or command-line arguments. Hooks should invoke installed secret scanners and formatters, while credentials must come from the environment's security mechanisms.

## 11. Pre-Push Checks

`pre-push` can run more time-consuming checks than `pre-commit`, such as integration tests, branch checks, or additional scans. This hook receives information about the remote and the refs about to be pushed via standard input; if you need to analyze the exact scope, consult Git's hook documentation and process each input line rather than assuming only a single branch is pushed.

Example simple hook running a fast test suite:

```sh
#!/bin/sh
set -eu

npm test
```

If tests fail, the hook returns a non-zero exit code and Git stops the push. Avoid putting long full test suites on every local push if that drives the team to disable hooks; run fast checks before pushing and full checks in CI.

## 12. Troubleshooting When Hooks Do Not Run or Misbehave

When a commit does not trigger a hook as expected, check:

```bash
git config --show-origin --get core.hooksPath
git rev-parse --git-path hooks
git status --short
```

Common causes:

- The hook file still has a `.sample` suffix or the wrong filename (`pre-commit`, `commit-msg`).
- The script lacks execute permissions or has an invalid shebang.
- `core.hooksPath` points to a different directory from the one you edited.
- A tool invoked inside the hook is not in the `PATH` of the Git process.
- The hook assumes the working tree is the data source while the commit takes content from the index.
- The hook runs across the entire project, making it too slow or failing on unrelated files.
- A command inside the script failed, yet the script did not propagate the non-zero exit code.
- The user passed `--no-verify` or the CI environment is configured to skip hooks.

To test a commit message hook, make a test commit on a test branch or run `git commit` in a sandbox repository. Never test by putting real secrets into a repository; use a dummy string matching an illustrative pattern and confirm the scanner flags it as configured.

## 13. Example Configuration of a Verification Flow

A JavaScript project can combine staged file formatting, secret scanning, and commit message validation as follows:

1. Install the formatter, `lint-staged`, pre-commit framework, and Gitleaks at team-approved versions.
2. Configure `lint-staged` in `package.json` to format staged files.
3. Declare Gitleaks in `.pre-commit-config.yaml` to scan staged content.
4. Install the pre-commit hook via `pre-commit install`.
5. Add a `commit-msg` script to validate Conventional Commits formatting.
6. Install the hooks in the chosen directory and verify with a test commit containing no real secrets.
7. Configure CI to re-run formatting, linting, tests, and secret scanning independently of the local machine.

Flow during commit:

```text
git add
  |
  v
pre-commit
  |-- format staged files
  |-- scan staged changes for secrets
  |
  v
commit-msg
  |-- validate subject and message policy
  |
  v
commit created
  |
  v
CI rechecks commit / pull request
```

When a check fails, fix the root cause, re-stage the intended content, and re-run. Never delete hooks or add broad allowlists just to force a commit through.

## 14. Key Takeaways

Place checks at the right stage: formatting and secret scanning in `pre-commit`, message conventions in `commit-msg`, and additional pre-sharing checks in `pre-push`. Inspect staged content because that is the data Git commits, ensure scripts return clear exit codes, and share hook setup instructions alongside the repository. Local hooks catch issues early yet can be bypassed; CI and server-side policies provide the shared enforcement layer. If a secret has entered history, revoke the credential first and handle history cleanup through a coordinated process.

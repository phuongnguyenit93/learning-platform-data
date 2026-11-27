# Inspecting a clean clone to detect environment differences

## Why test with a clean clone?

When a bug occurs on only one team member's machine, it is easy to conclude that the source code has a problem. However, the root cause may lie in local state or the runtime environment: uncommitted files, ignored files, Git config, line endings, uninitialized submodules, unfetched Git LFS data, different runtime versions, or mismatched environment variables.

A **clean clone** is a fresh clone taken from the Git repository and checked out at the exact commit under investigation. This copy helps determine whether the bug still occurs without carrying over local files and working tree history from the existing workspace.

A comparison is valid only when both sides use the same commit. If the current working copy is at commit A while the clean clone is at commit B, differing results cannot be attributed to the environment. Therefore, record the commit hash first, then bring the clean clone to the exact same commit and run the same verification procedure.

This check helps answer three questions:

1. Does the bug reproduce in a clean checkout of the same commit?
2. If only the old machine or working tree fails, which difference is affecting the outcome?
3. If both copies fail, does the issue lie in source code, dependencies, or repository-managed configuration?

A clean clone is a diagnostic test. It does not by itself prove that environments are completely identical, because a fresh clone is still influenced by the operating system, global Git config, credential helpers, runtimes, build tools, and external services.

## Recording the commit and state of the current working copy

Before creating a new copy, record the repository, branch, commit, and file status:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --porcelain=v2 --branch
git log -1 --oneline --decorate
~~~

Where:

- git rev-parse --show-toplevel identifies the repository root directory.
- git branch --show-current shows the checked-out branch; if HEAD is detached, output may be empty.
- git rev-parse HEAD records the exact commit being inspected.
- git status --porcelain=v2 --branch provides machine-readable status, including branch info and changes.
- git log -1 shows the latest commit along with reference decorations if any.

Save the full commit ID to use when checking out the clean clone. Do not record only the branch name, because a branch can move when the remote receives new commits.

### Determining whether the working tree is clean

Check unstaged and staged changes:

~~~bash
git diff --exit-code
git diff --cached --exit-code
~~~

If a command returns exit code 0, there are no corresponding differences in tracked files. If it returns exit code 1, there are differences to inspect. Other exit codes may indicate execution errors.

List untracked files:

~~~bash
git ls-files --others --exclude-standard
~~~

Also check ignored files:

~~~bash
git status --short --ignored
~~~

Some files do not appear in a regular diff because they are untracked or ignored by Git. They can still cause the application to behave differently, such as personal machine configs, generated files, caches, or stale test data.

To preview ignored files that would be removed by a clean operation, use dry-run mode:

~~~bash
git clean -ndX
~~~

To preview all untracked files and directories that could be removed:

~~~bash
git clean -ndx
~~~

The commands above only list candidates and do not delete files. Do not run git clean with execution flags during diagnostics unless you have verified every path and safeguarded needed data.

### Checking special index states

Certain index flags can prevent file changes from being reported normally. You can view the file list along with flags:

~~~bash
git ls-files -v
~~~

In this mode, lowercase letters can indicate files carrying the assume-unchanged flag. If skip-worktree or sparse checkout is suspected, check further:

~~~bash
git ls-files -t
git sparse-checkout list
git rev-parse --is-shallow-repository
~~~

The results help detect a checkout containing only part of the directory tree or a shallow clone. A sparse working copy can lack files present in a full clone even when no checkout error occurred.

Do not arbitrarily clear flags or disable sparse checkout solely to make status look cleaner. Record the configuration first and determine whether it relates to the bug.

## Creating a clean clone at the exact commit

Choose a test directory outside the current repository to avoid mixing files from the two copies. Clone from the exact remote the team uses as the integration source:

~~~bash
git clone <repository-url> clean-check
cd clean-check
~~~

A fresh clone typically checks out the remote's default branch. To compare the exact same source code, switch to the exact commit recorded from the original working copy:

~~~bash
git switch --detach <commit-id>
git rev-parse HEAD
git status --short
~~~

The printed commit hash must match the recorded commit ID. If the commit is not yet in the clone, fetch the branch containing that commit and check out again:

~~~bash
git fetch origin <branch-name>
git switch --detach <commit-id>
~~~

Do not use a branch name in place of verifying the commit. The remote branch may have advanced since the issue occurred.

### If the commit exists only locally

A clone from a remote cannot retrieve commits that have not been pushed or shared to that remote. In this case, there are two options:

- Use git worktree add to create a separate working tree from the local commit. This keeps the original repository's object database and repository-level configuration, making it suitable for testing differences caused by the working tree.
- Package the commit and required refs with git bundle, then clone the bundle into another directory. This creates a more isolated repository, though you must identify which refs belong in the bundle.

Example of creating a clean worktree from the current commit:

~~~bash
git worktree add --detach ../clean-check <commit-id>
~~~

The new worktree has its own working tree while sharing the original repository's object database and some configuration. It does not completely replace testing with an independent clone when investigating differences in Git config or repository settings.

If you need to test a commit existing only on a local machine with an independent clone, share the commit per team workflow or create a bundle containing the target ref. Do not modify a shared remote solely for a diagnostic test without an appropriate plan.

### Confirming the clone is genuinely clean

Inside the clean-check directory:

~~~bash
git rev-parse HEAD
git status --porcelain=v2 --branch
git diff --exit-code
git diff --cached --exit-code
git ls-files --others --exclude-standard
~~~

The goal is to confirm:

- HEAD matches the target commit for comparison.
- No unstaged tracked changes exist.
- No staged tracked changes exist.
- No unexpected untracked files exist.
- The branch is in the expected state; if checked out detached, that is understood and recorded.

A fresh clone can still contain files generated by hooks, filters, LFS, or setup tools. Inspect actual state rather than relying only on the directory name clean-check.

## Comparing repository contents between the two copies

When two copies are at the same commit, the Git content stored in the commit is identical. If the working tree shows differences, look for the cause in how Git converts content or in local files.

In each copy, run:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
~~~

If you need to verify a specific file, compare the working tree with the commit:

~~~bash
git diff <commit-id> -- src/config/application.yml
~~~

If the diff has no output, the tracked content of that file matches the commit snapshot as Git interprets it. If differences exist, inspect the contents to determine whether line endings, filters, local edits, or restoration errors are responsible.

You can view the blob a commit stores for a file:

~~~bash
git rev-parse <commit-id>:src/config/application.yml
~~~

This object ID identifies the blob content in Git. Two copies at the same commit and path will point to the same blob when the file is managed normally. Working tree differences may stem from clean/smudge filters, line endings, or uncommitted edits.

Do not compare hashes of files on disk directly and conclude the repositories differ without checking Git attributes. Git may convert line endings or apply filters during checkout.

## Inspecting Git configuration that can alter checkout

Git has configuration at multiple levels: system, global, repository local, worktree, and command. Two clones of the same commit can receive different configurations due to the user's machine or repository settings.

View the source of key settings:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
git config --show-origin --get core.filemode
git config --show-origin --get core.symlinks
git config --show-origin --get core.ignorecase
git config --show-origin --get core.hooksPath
~~~

An unset key can make the command exit with code 1; that is not necessarily a repository error. Compare the present values and configuration sources between the two environments.

Meaning of some settings:

| Setting | Possible impact |
|---|---|
| core.autocrlf | Converts line endings on checkout and when adding content to the index |
| core.eol | Line-ending style used in certain checkout scenarios |
| core.filemode | Whether Git recognizes executable bit changes |
| core.symlinks | Whether Git creates symbolic links or checks them out as regular files in certain environments |
| core.ignorecase | How Git handles path case differences |
| core.hooksPath | Location containing hooks executed when running certain Git commands |

Do not copy the full output of git config --list into a public report. Configuration may contain remote URLs, usernames, internal paths, or sensitive details. Gather only the necessary keys and redact credentials before sharing.

### Checking remotes and source refs

Ensure both copies come from the same repository and the right source branch. When inspecting remote URLs, verify the host and repository path; if a URL contains credentials, redact that part before logging.

~~~bash
git remote -v
git branch -avv
git show-ref --heads --tags
~~~

Remote-tracking branches reflect the state as of the last fetch. If you need to compare against the latest server state, run fetch first and record the check timestamp. Do not compare an updated fetched copy with an unfetched copy and assume they reflect the same remote state.

## Checking line endings and Git attributes

Differences across Windows, Linux, and macOS can make line endings a source of noise. Repositories should declare an appropriate policy in .gitattributes, for example:

~~~text
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.java text
~~~

This is only an example. Actual policy depends on the project's tools and file formats.

View attributes applied to a path:

~~~bash
git check-attr -a -- src/Main.java
git check-attr text eol -- scripts/build.sh
~~~

Read line-ending configuration:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

If one machine checks out CRLF while another checks out LF, file contents on disk may differ while Git still normalizes content according to attributes during comparisons and commits. Check .gitattributes, Git config, and diffs before altering policy.

Do not run git add --renormalize . casually while investigating. This command can create mass changes in the index; use it only when the team has decided to normalize line endings and has a dedicated review plan.

### Checking filters and Git LFS

Some repositories use filters to transform content on checkout or staging. Git LFS is a common example: Git stores a pointer in the repository while large file contents are fetched from an LFS server.

Check attributes and filters:

~~~bash
git check-attr -a -- path/to/large-file.bin
git lfs version
git lfs ls-files
git lfs status
~~~

If the project uses LFS, the clean clone needs Git LFS installed and access to the LFS server. After cloning, you may need to fetch contents according to project instructions:

~~~bash
git lfs pull
~~~

If one machine has the actual content while another has only the pointer, the application may produce different results even though both copies are at the same commit. Check LFS status and download logs before concluding the source code is broken.

Custom filters may also depend on external programs, tool versions, or environment variables. Compare filter configuration and program versions between the two machines.

## Checking submodules and sparse checkout

A submodule is a repository nested inside a main repository. Commits in the main repository record only the commit ID the submodule should point to; a fresh clone may not yet have downloaded submodule contents.

Check status:

~~~bash
git submodule status --recursive
~~~

Leading symbols typically indicate status:

- Space: the submodule is at the commit requested by the main repository.
- Minus sign: the submodule is not yet initialized.
- Plus sign: the submodule is checked out at a commit different from the one recorded in the main repository.
- Letter U: the submodule has unresolved conflicts.

Initialize and check out the exact recorded commits:

~~~bash
git submodule update --init --recursive
git submodule status --recursive
~~~

If a submodule requires separate access permissions, verify credentials and URLs in .gitmodules. Do not embed tokens in URLs or reports.

Sparse checkout fetches only part of the directory tree. Check:

~~~bash
git sparse-checkout list
git config --show-origin --get core.sparseCheckout
~~~

A full clean clone may contain files absent from a sparse working tree. If an error occurs only when a directory is missing, confirm sparse checkout settings before investigating application logic.

## Comparing operating system, runtime, and build tools

Once the commit and Git configuration have been cross-checked, inspect components outside the repository.

Depending on the project, you can record:

~~~bash
git --version
java -version
./gradlew --version
node --version
npm --version
python --version
~~~

Run only the commands relevant to the project's stack. A Java project does not need Node checks if Node is not involved in the build or frontend.

Compare the following items:

| Component | Differences to inspect |
|---|---|
| Operating system | Windows, Linux, macOS, and OS version |
| Git | Git version, configuration, and filters |
| Runtime | JDK, Node.js, Python, .NET, or actual runtime |
| Build tool | Gradle, Maven, npm, pnpm, pip, dotnet, and version |
| Dependencies | Lockfiles, dependency caches, and download sources |
| Shell | PowerShell, CMD, Bash, or other shell scripts |
| Locale | Encoding, locale, number and date/time formatting |
| Timezone | Time conversion rules and timezone-dependent tests |
| Filesystem | Case sensitivity, symlinks, execute permissions, and path limits |
| Container | Image tag or digest, CPU architecture, and mount configuration |

If the project provides a wrapper such as Gradle Wrapper or Maven Wrapper, prefer using the committed wrapper to minimize tool version differences. Wrappers still depend on the JDK, network, proxy settings, and dependency repositories.

### Selectively inspecting environment variables

Environment variables can point an application to a different database, activate a different profile, or alter test behavior.

Identify the list of variables the application actually uses, for example:

- APP_ENV or SPRING_PROFILES_ACTIVE.
- TZ or locale relied upon by the application.
- JAVA_HOME or runtime paths.
- Dependent service URLs in the test environment.
- Non-secret feature flag configuration variables.

Do not dump the entire environment using env, set, or Get-ChildItem Env: into shared logs. Those commands can expose tokens, passwords, API keys, and credentials. Inspect only the required variable names, redact sensitive values, and compare profiles or sanitized states.

### Checking local configuration files

A .env, application-local.yml, or configuration file in an ignored directory may exist on the old machine while missing from the clean clone. This is a common reason two machines running the same commit yield different results.

Identify configuration files supported by the project and compare key names and profiles without copying secrets. Use template files such as .env.example or application-example.yml if provided by the project. Create local configuration from templates per project guidelines and obtain secrets from a secret manager or appropriate provisioning mechanism.

Do not commit configuration files containing credentials just to make a clean clone run like a personal machine.

## Running the same verification procedure on both copies

After checking out the same commit and preparing required dependencies, run the exact same sequence of build/test commands on both copies.

Illustrative example for a Java project using Gradle Wrapper:

~~~bash
./gradlew clean test
~~~

If the project uses Maven Wrapper:

~~~bash
./mvnw clean verify
~~~

Choose the right command according to repository documentation. Do not assume both commands need to be run.

Record for each run:

- Full commit.
- Branch or detached HEAD state.
- Operating system and Git version.
- Runtime and build tool.
- Submodule and LFS status.
- Profile or environment variable group used, without recording secrets.
- Build/test command and exit code.
- Which tests PASS, FAIL, were skipped, or did not run.

If the current working copy fails while the clean clone succeeds, inspect differences in the working tree, ignored files, local config, caches, hooks, index flags, and toolchain. If both fail, focus on the commit, dependencies, repository-managed configuration, or dependent services.

If the clean clone fails while the old copy succeeds, check missing local files, unprovisioned secrets, submodules/LFS, uninstalled hooks, dependency caches, or environment bootstrap steps.

## Interpreting comparison results to narrow down the cause

The following table helps choose the next direction of investigation:

| Outcome | Cause group to inspect |
|---|---|
| Old copy fails, clean clone at same commit succeeds | Local changes, ignored files, caches, index flags, Git config, or hooks |
| Both fail on the same test | Source code, dependencies, committed config, or dependent services |
| Old copy succeeds, clean clone fails | Missing local config files, secrets, submodules, LFS, or setup steps |
| Same commit yet tracked diff differs | Line endings, attributes, filters, symlinks, or local edits |
| HEAD differs | Not comparing the same snapshot; fetch or check out the exact commit |
| Build differs despite clean diff | Runtime, build tool, environment variables, locale, timezone, or caches |
| Only CI yields a different result | Image, runner, secrets, services, architecture, or CI configuration |

These are investigation leads, not automatic conclusions. Change one factor at a time if possible to isolate which factor changes the outcome.

## Checking caches and auto-generated state

Build tools often store caches outside the repository or in ignored directories. Stale caches can mask missing dependencies or cause builds to differ between two machines.

Some examples:

- Gradle cache in the user directory.
- Maven local repository.
- npm, pnpm, or Yarn cache.
- Python virtual environments and package caches.
- Build outputs such as build/, target/, dist/, or out/.

A clean clone does not necessarily have an empty user-level cache. To test cache effects, use the build tool's clean mechanism or an isolated cache directory per project instructions. Record configuration changes and results; avoid wiping machine-wide caches without knowing whether other projects rely on them.

Distinguish a build tool's clean command from git clean. Build clean typically deletes outputs generated by the tool; git clean can delete untracked files inside the repository. They have different scopes and risks.

## Creating a reproducible clean copy

To make bugs reproducible for the team, standardize the procedure:

1. Select the source repository and full commit.
2. Create a fresh clone in a test directory.
3. Check out detached at the exact commit.
4. Initialize submodules and pull LFS if used by the project.
5. Install runtime and dependencies according to the wrapper or lockfile.
6. Create environment configuration from template files and a secret manager.
7. Run the same test/build commands.
8. Record results and environment details.
9. Keep necessary logs while stripping credentials and sensitive data.
10. Delete the test copy once no longer needed per the team's retention policy.

You can use a directory name containing the commit hash to avoid confusing test runs:

~~~text
clean-check-4a5b6c7/
clean-check-8d9e0f1/
~~~

Do not reuse an old clone directory without checking its status, because it may have accumulated generated files, local changes, or different settings from a previous test.

### End-to-end example workflow

Suppose the current working copy fails when running a report export test. The team wants to verify whether the error stems from a local configuration file.

In the original repository:

~~~bash
git rev-parse HEAD
git status --porcelain=v2 --branch
git diff --exit-code
git diff --cached --exit-code
git ls-files --others --exclude-standard
~~~

Record the commit, then create a fresh clone from the remote:

~~~bash
git clone <repository-url> clean-check
cd clean-check
git switch --detach <commit-id>
git rev-parse HEAD
git status --short
~~~

If the project uses submodules or LFS:

~~~bash
git submodule update --init --recursive
git submodule status --recursive
git lfs pull
~~~

Prepare the runtime, configuration, and dependencies per project instructions. Then run the same test command as on the original working copy:

~~~bash
./gradlew clean test
~~~

Record the result and compare against the previous run. If the clean clone passes, inspect ignored files and local configuration in the old copy. If the clean clone also fails, check tests, dependencies, committed configuration, and external services.

This example uses Gradle for illustration. Replace the command with the repository's actual build/test workflow.

## Reporting inspection results

A report can be brief, but it needs enough data for others to reproduce:

| Field | Example content |
|---|---|
| Repository | Repository name and remote with credentials redacted |
| Commit | Full SHA of the inspected commit |
| Copy | Current working tree or clean clone |
| Git | Git version and relevant configuration |
| Environment | OS, runtime, build tool |
| Subcomponents | Submodule and LFS status |
| Configuration | Profile and required environment variable names |
| Command | Actual build/test command executed |
| Result | PASS, FAIL, BLOCKED, or not run |
| Differences | Factors identified between the two copies |

If the bug appears only in the old working copy, clearly state the confirmed differences with evidence such as diffs, ignored files, Git config, or runtime versions. If the root cause has not yet been found, list hypotheses and next verification steps rather than asserting the environment is at fault.

## Common misconceptions

- **“A fresh clone always has a completely clean environment.”** A fresh clone has a new working tree and repository config, yet still uses the machine's global Git config, runtime, user caches, credentials, and services.
- **“Same branch name means identical source code.”** Branches can point to different commits. Compare full SHAs.
- **“Clean git status means no files interfere.”** Ignored files, environment variables, and external data can still affect the application.
- **“Different line endings always mean different commits.”** Attributes and Git config can normalize line endings; check diff and check-attr.
- **“A clean clone automatically downloads all subcomponents.”** Submodules and Git LFS may require separate initialization or pull steps.
- **“A passing build on the old machine proves the clean clone will run too.”** The old machine may depend on local files, caches, or secrets not documented in the setup process.

## Checklist before concluding an environment difference

- [ ] Recorded the full commit of the original working copy.
- [ ] Clean clone checked out the exact same commit.
- [ ] Confirmed working tree and staging area status.
- [ ] Checked untracked, ignored files, and special index flags.
- [ ] Cross-checked remotes and fetch status.
- [ ] Inspected relevant Git config along with configuration sources.
- [ ] Checked line endings, attributes, and filters.
- [ ] Confirmed submodules and LFS are in the expected state.
- [ ] Compared operating system, runtime, and build tools.
- [ ] Prepared matching profiles and environment configuration without exposing secrets.
- [ ] Executed the exact same build/test commands on both copies.
- [ ] Recorded reproducible results and evidence.

## Takeaways

To detect environment differences, create a fresh clone and check out the exact commit exhibiting the bug. Compare file status, index, ignored files, Git config, attributes, submodules, LFS, and toolchain; then run the same build/test commands with equivalent configuration. If the clean clone succeeds while the old copy fails, focus on local state and machine-specific configuration. If both fail, investigate the commit, dependencies, and related services. A sound conclusion must rest on the same commit, the same verification procedure, and clearly documented differences.

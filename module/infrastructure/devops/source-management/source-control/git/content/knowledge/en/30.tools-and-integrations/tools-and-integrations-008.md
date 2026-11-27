# Limiting .git Cache Copying and Protecting Credentials in Logs

The .git directory is often treated as an auxiliary folder that can be copied or deleted at will. In reality, it is the core data area of the repository: it stores the object database, branches and tags, index, local configuration, reflogs, hooks, and metadata for worktrees or submodules. Copying this entire directory can expose history deleted from the current version, internal remote URLs, authentication settings, or automatically executed scripts. Conversely, deleting it like an ordinary cache can turn the source directory into a non-Git folder.

Diagnostic logs can also contain authentication credentials. When enabling traces to troubleshoot fetch, pull, or push errors, output may record URLs, HTTP headers, command arguments, machine paths, and environment data. Therefore, restrict copying .git strictly to valid purposes, choose an appropriate clone or export method, and treat logs as data that may contain secrets.

## 1. .git is repository metadata, not just a cache

In a normal repository, .git is typically the directory holding internal data and configuration that Git uses to manage history. It is not merely a cache that can be deleted and regenerated without consequences.

Common components include:

| Component | Role | Caution when copying |
|---|---|---|
| objects/ | Commit, tree, blob, and tag objects | May contain full history and old contents |
| refs/ and packed-refs | Branches, tags, and other refs | Reveals branch names, release milestones, and referenced history |
| HEAD | Current branch or commit | Reflects checkout state |
| index | Current staging snapshot | Working state, not distribution data |
| config | Local and remote configuration | May contain internal URLs, headers, or paths |
| logs/ | Reflogs of HEAD and refs | May reveal operation history and metadata |
| hooks/ | Scripts executed when Git runs certain operations | Can execute commands with the user's privileges |
| modules/ | Submodule repository metadata | May hold multiple objects and separate configurations |
| worktrees/ | Linked worktree metadata | Cannot be arbitrarily detached from related working trees |
| rr-cache/ | Recorded conflict resolution data | May contain content from file versions |
| lfs/ | Git LFS object cache if used | May contain large files, internal data, or customer data |
| objects/info/alternates | Path to an external object database | Copies may miss objects if the referenced store is not included |

Depending on version, configuration, and repository type, the actual structure may vary. Do not rely on a fixed list to manually cherry-pick files inside .git for copying.

### 1.1. The object database can retain data deleted from a branch

When a file is committed and later deleted in a subsequent commit, objects containing the old content may still exist in history. Creating a full copy of the repository or bundling all refs can carry that content along with the copy.

Example:

~~~text
Commit A: adds config/local.env containing a token
       |
       v
Commit B: deletes config/local.env
       |
       v
Current main branch no longer has the file
But history still contains Commit A and the file's content
~~~

Deleting a file from the working tree or adding it to .gitignore does not remove old content from prior commits. Therefore, checking only the current file tree before sharing .git is insufficient.

### 1.2. Local configuration can contain sensitive information

The .git/config file typically contains remote URLs, upstream branches, and repository-specific settings. Some HTTP configurations may store extra headers or authentication details; includes can pull additional settings from other files.

Inspect configuration with care:

~~~sh
git config --local --list --show-origin
git remote -v
~~~

These commands can display sensitive values if credentials were ever embedded in URLs or header configs. Only inspect them on authorized machines and never paste raw output into tickets, chats, or public logs.

### 1.3. .git may be a file instead of a directory

In linked worktrees and submodules, the .git entry in the working tree can be a file pointing to the real Git directory, for example:

~~~text
gitdir: ../.git/worktrees/feature-a
~~~

Consequently, copying only the working tree or only the .git file can break the link to the shared Git directory. Use Git to determine the paths:

~~~sh
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

Do not assume every repository has a standalone .git directory located directly at its root.

## 2. Determine the goal before copying

Before copying a repository, determine what the recipient actually needs.

| Purpose | Common appropriate method | Is the entire .git needed? |
|---|---|---|
| Run or build a source version | Source archive or clean checkout | No |
| Review a change | Pull request, patch, or ref-limited bundle | Not the entire thing |
| Continue developing history | Clone from remote or bundle | Use Git to create the copy |
| Create a mirror for repository migration | git clone --mirror | Needs selected history/refs, not a verbatim copy of all metadata |
| Back up exact local working state | Controlled filesystem backup/snapshot | May be needed; must preserve both working tree and Git directory |
| Collect incident evidence | Forensic process and consistent snapshot | Follow evidence procedures; do not modify arbitrarily |

Do not send the whole .git folder just because the recipient needs to inspect a single file or commit. Choose the smallest output scope that satisfies the goal.

## 3. When should you avoid copying .git?

Do not include .git in:

- Installation packages or application release artifacts.
- Container build contexts if the build does not need Git history.
- ZIP files sent to customers or vendors who only need source code.
- Support tickets that only need logs or a specific patch.
- Public shared folders or personal cloud drives.
- Unencrypted temporary backups without access control.

A copy of .git can expose history, branches, and deleted files. If the repository ever held secrets or private data, recipients can access that content even if the current working tree is clean.

### 3.1. Do not rely on .gitignore to control ZIP packages or build contexts

.gitignore only controls whether Git ignores untracked files. It does not automatically exclude .git from:

- Directory compression commands using ZIP or TAR.
- Docker build contexts.
- Artifacts packaged by CI.
- File synchronization tools.
- Directory copies over disk or network.

Configure separate exclusions for each tool.

Example .dockerignore file:

~~~text
.git
.git/**
.env
.env.*
*.pem
*.key
~~~

Secret patterns above are only examples. Adjust them according to your project's structure and legitimate files. Do not exclude data that the build genuinely needs without designing a secure alternative way to supply it.

With rsync, you can exclude the Git directory:

~~~sh
rsync -a --exclude='.git' ./ ../source-export/
~~~

Inspect the destination directory and included files carefully before sharing. Copying a working directory can still include ignored or untracked files unless additional exclusions are specified.

## 4. Use git archive when only source code is needed

If the recipient only needs a snapshot of a commit, git archive creates an archive from the Git-tracked tree without carrying the object database and history.

Create a ZIP file:

~~~sh
git archive --format=zip --output=../source-main.zip HEAD
~~~

Create a TAR file:

~~~sh
git archive --format=tar --output=../source-main.tar HEAD
~~~

The archive contains the tree content at the selected commit. It does not include uncommitted changes, untracked files, or .git metadata.

Verify before creating:

~~~sh
git status -sb
git show --stat --oneline HEAD
~~~

If uncommitted changes must be included in an archive, commit them to a dedicated branch or create a controlled temporary tree/commit. Do not assume git archive picks up files open in an IDE.

### 4.1. Limitations with submodules and Git LFS

git archive does not automatically package submodule repository contents. In the parent repository's tree, a submodule is represented by a gitlink pointing to a child repository commit. If the recipient needs submodule contents, provide the child repository or a separate package.

With Git LFS, trees typically hold pointer files; actual large objects are stored outside the Git object database. An archive may contain only pointers rather than actual file contents, depending on how it is built and configured. Verify LFS handling separately before releasing an archive.

## 5. Use clone or bundle when history is needed

If the recipient needs to keep working with Git, use Git commands rather than manually copying parts of .git.

### 5.1. Cloning a working repository

~~~sh
git clone https://example.com/team/project.git project-copy
~~~

Cloning creates a new repository with the history and remote needed for work. However, a standard clone only fetches refs per fetch configuration and does not copy all local metadata, server hooks, reflogs, or uncommitted files.

Do not use URLs with embedded tokens or passwords. Use a credential manager or an organization-approved SSH mechanism.

### 5.2. Creating a mirror for migration

~~~sh
git clone --mirror https://example.com/team/project.git project.git
~~~

A mirror clone is suited for migrating or syncing refs exposed by a remote. It is not a verbatim copy of the original .git directory: local configs, hooks, reflogs, index, and working tree are not transferred like a filesystem backup.

A mirror also copies only objects reachable through the fetched refs. Unreachable objects or data existing only in reflogs may not appear in the mirror.

### 5.3. Repositories using object alternates or shared clones

A repository can borrow objects from another object database via objects/info/alternates. This commonly occurs when creating a shared clone:

~~~sh
git clone --shared /path/to/source.git shared-copy
~~~

A shared clone saves disk space by referencing objects from the source repository. If the source is deleted or runs garbage collection while the copy still needs borrowed objects, the copy can end up missing objects.

If you want to borrow objects from a reference repository to speed up cloning without keeping the dependency afterward, use --reference together with --dissociate:

~~~sh
git clone --reference /path/to/reference.git --dissociate https://example.com/team/project.git independent-copy
~~~

If you already have a clone created with --shared and want to decouple objects from the source, you can pack required objects into the local store:

~~~
git repack -a
git fsck --full
~~~

Only retire the source object store after confirming the copy operates independently and has proper backups. If you receive an existing copy, inspect its alternates path and ensure all needed objects are supplied before moving it.

### 5.4. Using Git bundles for offline exchange

~~~sh
git bundle create ../project-main.bundle refs/heads/main
git bundle verify ../project-main.bundle
~~~

A bundle carries selected objects and refs, though it does not package all local config, hooks, credentials, working tree, or unreachable objects. Select minimal refs and inspect for sensitive history before transferring.

## 6. Do not manually delete or edit files in .git like an ordinary cache

Some data inside .git can be regenerated or optimized by Git, yet it should not be deleted manually through a file manager.

For instance, the index, packfiles, commit-graph, and other caches have their own consistency rules. Deleting the wrong file can wipe staging state, degrade performance, or corrupt the repository.

When you need to optimize the object database, use Git commands:

~~~sh
git gc
git maintenance run
~~~

Only run maintenance tasks when appropriate for the environment and repository workflow. Do not run cleanup to try to erase secrets from history: objects can still be referenced by branches, tags, reflogs, or other clones.

### 6.1. Do not copy .git while Git is writing

A commit, fetch, repack, or gc operation can modify multiple metadata files. Copying .git while a process is running risks capturing an inconsistent snapshot.

If a verbatim backup is required:

1. Identify all Git processes and IDEs using the repository.
2. Stop or wait for write operations to finish per procedure.
3. Take a consistent filesystem snapshot or use a snapshot-capable backup tool.
4. Preserve file permissions, symlinks, and directory structure.
5. Restore into a test environment and verify the repository before trusting the backup.

Do not copy objects/ or refs/ alone while Git is actively updating them.

### 6.2. Verifying a repository after receiving a copy

~~~sh
git status
git show-ref
git fsck --full
~~~

git fsck can detect inconsistent objects or links, yet it does not prove the copy contains all expected data. Cross-check branches, tags, remotes, worktrees, and backup goals as well.

## 7. Sources of credential leaks in logs

Credentials can appear across many layers:

| Source | Examples of potentially exposed data |
|---|---|
| Remote URL | Username, password, or token embedded in the URL |
| Git config | http.extraHeader, URL rewrites, credential settings |
| Shell history | Tokens in command arguments |
| Process arguments | Credentials passed directly via command line |
| Git trace | Commands, paths, transport activity, and metadata |
| HTTP/cURL trace | URLs, headers, cookies, or authentication details |
| SSH debug log | Host, username, key paths, and connection details |
| CI log | Environment variables, debug commands, script output |
| IDE log | Authentication errors, remote URLs, workspace paths |
| Tickets or attachments | Unfiltered logs, terminal screenshots, config files |

Not every log always records secrets. However, treat debug-enabled logs as sensitive data until they have been inspected and scrubbed.

## 8. Avoid embedding credentials in remote URLs

Do not configure a remote like this:

~~~sh
git remote set-url origin https://user:token@example.com/team/project.git
~~~

The value can appear in .git/config, git remote -v output, logs, screenshots, or copied configuration files.

Use a credential-free URL:

~~~sh
git remote set-url origin https://example.com/team/project.git
git remote -v
~~~

Then authenticate using a credential manager or an approved sign-in method.

For SSH, use a remote format like:

~~~sh
git remote set-url origin git@example.com:team/project.git
~~~

Private keys must be protected separately, preferably with a passphrase and an SSH agent. Never place private keys in a repository or shared folder.

### 8.1. Credential helpers

A credential helper lets Git obtain credentials from a storage mechanism rather than writing tokens into remote URLs or scripts.

Common options:

- Git Credential Manager integrated with the operating system's credential store.
- SSH agent to manage keys during a working session.
- Organization-provided credential helper.
- Short-lived credential cache when supported by the environment.

Avoid helpers that store credentials in plain text if organizational policy prohibits it. For example, the store helper may write credentials to a user file like .git-credentials in plain text.

Do not share credential helper files or home directories just to help someone else clone a repository. Provision separate access for each person.

### 8.2. Do not pass tokens directly via the command line

Avoid:

~~~sh
git -c http.extraHeader="Authorization: Bearer <token>" fetch origin
~~~

Credentials in arguments can be captured in shell history, process listings, traces, or orchestration tool logs. Use a credential manager or secret injection designed for automated tools.

Do not print environment variables containing tokens using echo, set, env, or commands that dump the entire environment.

## 9. Protecting Git traces and diagnostic logs

Git provides several environment variables to record traces when investigating errors. These modes are useful but need boundaries.

| Variable or mode | Purpose | Risk |
|---|---|---|
| GIT_TRACE | Trace Git command activity | May record arguments, paths, and internal operations |
| GIT_TRACE_CURL | Trace HTTP/cURL | May record URLs, headers, and transport details |
| GIT_CURL_VERBOSE | Enable verbose cURL output | May cause logs to contain sensitive connection details |
| GIT_TRACE_PACKET | Trace packet protocol | May record exchanged data and ref names |
| GIT_TRACE2_EVENT | Record structured trace2 events | May record command, argv, paths, and environment metadata |

Redaction of sensitive data depends on Git version, trace type, and configuration. Never assume every token or header is automatically masked.

### 9.1. Enable traces only for as long as needed

On POSIX shells, you can scope a trace to a single command and a dedicated file:

~~~sh
umask 077
GIT_TRACE=1 git fetch origin 2>git-fetch-trace.log
~~~

For HTTP traces:

~~~sh
umask 077
GIT_TRACE_CURL=1 git fetch origin 2>git-http-trace.log
~~~

Only enable GIT_TRACE_CURL when genuinely investigating transport issues. Do not enable broad tracing across an entire session or production CI without reason.

On Windows PowerShell, scope the environment variable to a single command and remove it right after running:

~~~powershell
$env:GIT_TRACE = "1"
git fetch origin 2> git-fetch-trace.log
Remove-Item Env:GIT_TRACE
~~~

The log file path must reside in a directory with restricted access. Never commit trace files or include them in default artifacts.

### 9.2. Do not enable shell debugging around commands with secrets

In shell scripts, set -x can print commands after variable expansion. If a command contains a token, password, or authentication header, the expanded value can appear in logs.

Do not enable set -x for script sections handling credentials. If debugging is needed, log step names and status codes, not secret values.

### 9.3. Restricting CI logs

In CI/CD:

- Store secrets in the platform's secret store.
- Use masked/protected variables if supported by the platform.
- Never echo secrets or dump the entire environment.
- Turn off verbose/trace modes once investigation finishes.
- Never upload raw logs as broadly accessible artifacts.
- Restrict log read permissions and retention periods.
- Review failed job logs before sending them externally.

CI masking features may not catch every encoding, substring, or transformation of a secret. Do not rely solely on masking; keep secrets out of output from the start.

## 10. Reviewing logs before sharing

Before attaching logs to a ticket or sending them to a vendor, check for:

- Authorization and Proxy-Authorization headers.
- Cookie, Set-Cookie, and session IDs.
- Access tokens, refresh tokens, API keys, and passwords.
- URLs with userinfo or query parameters containing credentials.
- Private keys or private certificate contents.
- Home paths, usernames, and internal hostnames.
- Unpublished repository URLs, branch names, and project codes.
- Customer data, requests/responses, or file contents.

If logs must be preserved intact as evidence, store the original in a restricted-access evidence area. Create a redacted copy for sharing. Record who scrubbed it, which fields were redacted, and when it was done.

### 10.1. Redacting properly

Replace values with meaningful placeholders:

~~~text
Authorization: Bearer [REDACTED]
Cookie: [REDACTED]
remote: https://example.com/team/project.git
token=[REDACTED]
~~~

Do not merely mask the first or last few characters of a token. Do not send screenshots with a terminal behind them still displaying secrets. Check filenames, metadata, and compressed contents as well before sharing.

Do not modify the original log during an investigation. Keep the original separate, produce a scrubbed copy, and clearly mark it as the shareable version.

## 11. Checking credentials in the repository and environment

### 11.1. Checking remotes

~~~sh
git remote -v
git config --local --get-regexp '^remote\.'
~~~

These commands can reveal sensitive URLs. Only run them in trusted environments and do not paste raw output without reviewing it first.

### 11.2. Checking HTTP configurations

Some settings like http.extraHeader can hold authentication headers. Do not print values into support logs. If inspection is needed, view local configuration using authorized admin tools and treat the output as a secret.

~~~sh
git config --show-origin --get-regexp '^http\.'
~~~

Do not share raw output of this command. After inspecting, remove or replace configs containing credentials per procedure; revoke tokens if exposure is possible.

### 11.3. Checking credential files outside the repository

Credential helpers can store data outside .git, such as in the user's home directory. When preparing a machine handover or creating a profile backup, check credential locations per OS and organizational policy.

Do not copy an entire home directory just to transfer a repository. Use proper access provisioning and sign in again on the receiving machine.

## 12. Handling a credential that appeared in logs

If a token, password, or private key entered logs, screenshots, artifacts, or shared files, assume it may have been compromised.

Basic workflow:

1. Identify the credential type, issuing system, and permissions it holds.
2. Revoke or rotate the credential immediately per procedure.
3. Inspect access logs for unusual activity.
4. Identify every copy: CI logs, artifacts, tickets, chats, emails, backups, and personal machines.
5. Restrict access or delete copies according to retention/evidence policy.
6. Clean up remote URLs, configs, scripts, and pipelines so secrets are no longer written.
7. Document the incident and preventive measures against recurrence.

Rewriting Git history does not revoke a credential. If a secret was in a commit, handle the credential first, and only afterward decide on rewriting history and updating clones.

## 13. Safe repository sharing workflow

Suppose a teammate needs to investigate a bug occurring at the latest commit.

**Step 1 — Confirm the right repository and commit**

~~~sh
git rev-parse --show-toplevel
git status -sb
git log -5 --oneline
~~~

**Step 2 — Choose the type of data to send**

- Only need a source snapshot: use git archive.
- Need a single change: create a patch or pull request.
- Need Git history: clone or bundle with limited refs.
- Need an exact local copy: use a controlled backup/snapshot.

**Step 3 — Check for secrets and metadata**

Review history, URLs, logs, and included files. Do not send .git if the recipient does not need history.

**Step 4 — Share via an approved channel**

Limit recipient access, encrypt per policy, and set a retention expiration.

**Step 5 — Revoke access and clean up copies**

Once work is done, revoke temporary access and delete intermediate files per retention policy.

## 14. Common mistakes

**Treating .git as a deletable cache.** .git contains repository history and state. Use Git for maintenance; do not delete it arbitrarily.

**Compressing the entire project folder to send source code.** The archive may include .git, ignored files, .env, and logs. Use git archive or an explicit allowlist.

**Thinking .gitignore excludes .git from Docker or ZIP.** Those tools have their own exclusion mechanisms. Configure .dockerignore or packaging file lists.

**Copying .git while fetch or gc is running.** The snapshot can be inconsistent. Use controlled filesystem snapshots or clone/bundle.

**Thinking clone --mirror is a verbatim backup.** A mirror does not carry all local configs, reflogs, hooks, and the working tree. Clarify backup requirements.

**Enabling GIT_TRACE_CURL and sending raw logs.** Traces can contain sensitive connection data. Save separately, inspect, and redact before sharing.

**Embedding tokens in remote URLs.** URLs can be stored in .git/config, outputs, and logs. Use a credential manager.

**Enabling set -x in an authentication pipeline.** The shell can print variable values after expansion. Turn off debugging around secret-handling sections.

**Only deleting logs after a token leaked.** Someone may already have downloaded a copy. Revoke the credential and assess scope first.

## 15. Checklist for copying .git and protecting logs

**Before copying**

- [ ] Determine whether the recipient needs source, a patch, history, or a local backup.
- [ ] Exclude .git from archives/build contexts if unnecessary.
- [ ] Check object history, refs, configs, and hooks for sensitive data.
- [ ] Identify linked worktrees, submodules, LFS, and object alternates.
- [ ] Do not copy .git while Git is writing.

**Before enabling traces**

- [ ] Identify the error to investigate and the minimal trace type needed.
- [ ] Use a separate log file with restricted access permissions.
- [ ] Do not enable broad traces in production CI unnecessarily.
- [ ] Do not use set -x around commands containing credentials.
- [ ] Disable traces immediately after collecting sufficient data.

**Before sharing logs**

- [ ] Check Authorization, cookies, tokens, and passwords.
- [ ] Check URLs, headers, query parameters, and internal paths.
- [ ] Check customer data and metadata.
- [ ] Keep the original separately if needed for investigation.
- [ ] Redact on a copy and verify again before sending.

**When a leak is detected**

- [ ] Revoke or rotate the credential.
- [ ] Check access logs and exposure scope.
- [ ] Identify related CI artifacts, tickets, chats, emails, and backups.
- [ ] Restrict permissions or handle copies per policy.
- [ ] Fix configs and workflows to prevent recurrence.

## 16. Conclusion

.git is core repository metadata, not a harmless cache. It can hold historical objects, refs, local configuration, hooks, reflogs, and worktree or submodule metadata. Only copy it in full when the goal truly requires a controlled backup; if only source code, a patch, or selected history is needed, use git archive, patches, clones, or bundles appropriately.

Diagnostic logs must also be protected as data that can contain credentials. Use a credential manager, avoid tokens in URLs and command lines, limit trace duration, never print secrets in CI, and scrub logs before sharing. When a credential has been exposed, revoke it first, then address logs, artifacts, history, and related copies.

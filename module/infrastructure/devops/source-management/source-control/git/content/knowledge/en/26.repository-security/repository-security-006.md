# Removing Sensitive Data from History and Limits for Clones, Caches, and Forks

Once a token, password, private key, or sensitive data has been committed to Git, deleting the file from the working tree or creating a fixup commit is not enough. The old content can still reside in earlier commits, tags, branches, teammates' clones, forks, CI caches, and backups.

Proper remediation requires two things in parallel: **revoking or replacing the exposed secret** and **removing the content from Git refs you control**. Afterward, you must evaluate copies outside the primary repository. Rewriting history reduces the ability to keep accessing the data through Git, yet it cannot guarantee every copy has disappeared.

## 1. First response when sensitive data is detected

If a credential has appeared in a commit, treat it as exposed. Even in a private repository, authorized users, bots, CI runners, forks, or clones may already have read the data.

Order of priority:

1. **Revoke or rotate the secret immediately.** Disable the exposed token, password, API key, deploy key, or certificate; issue a new value through a secret management system.
2. **Assess the blast radius.** Identify the credential type, the permissions it grants, the exposure window, repositories, branches, tags, PRs/MRs, and accessed systems.
3. **Restrict access if needed.** For public repositories or severe incidents, coordinate with maintainers to temporarily restrict access during remediation.
4. **Plan history cleanup.** Identify which refs must be rewritten, the tool to use, who will execute it, and how teammates will resynchronize.
5. **Audit copies outside the primary repository.** Include forks, clones, caches, artifacts, logs, and backups.

Never wait until history rewriting finishes before revoking credentials. Git history can be cleaned, yet a copied token can still be used until it is invalidated.

If the data is subject to incident reporting, personal data rules, or customer confidentiality, follow your organization's incident response and evidence-preservation procedures. Never arbitrarily delete logs or backups needed for investigation.

## 2. Why deleting the file or adding .gitignore is not enough

Git stores commits as immutable objects. An older commit can continue holding sensitive blobs even after the current branch deletes the file.

For example:

~~~text
A---B---C---D  main
     |
     +-- B contains secret.env
              C deletes secret.env
              D adds .gitignore
~~~

In the current state, the file may no longer be in the working tree. However, commit B still holds the file content. Anyone with permission to read history can check out B or read the blob directly.

| Action | What actually happens |
|---|---|
| Delete file and commit | Creates a new commit without the file in the current state; old commits still keep the blob |
| Add path to .gitignore | Prevents untracked files from being added automatically; does not remove old commits |
| Run git rm | Removes the file from the current version and staging area; does not rewrite earlier commits |
| Delete local branch | Deletes a reference; objects may still remain in the reflog or other refs |
| Delete remote branch | Deletes the ref on the remote; does not guarantee objects, forks, or caches are purged |
| Delete or close PR/MR | Does not guarantee all platform internal refs, previews, or caches have vanished |

To remove content from shared history, you must rewrite the commits containing that content and update the affected refs on the remote. This changes commit hashes and affects everyone whose work rests on the old history.

## 3. Identifying the data and scope to clean

Before running a history-rewriting tool, list out:

- The sensitive values or data categories to remove.
- File paths that ever contained the data, including former names prior to renames.
- Commits, branches, tags, or other refs that may contain the content.
- Whether the content appears in commit messages, annotated tag messages, issues, PRs/MRs, or logs.
- Whether the file was stored via Git LFS.
- Whether the repository has submodules, forks, or separate mirrors.

Useful commands for path-based investigation:

~~~bash
git log --all --oneline -- config/production.env
git log --all --stat -- config/production.env
git rev-list --objects --all
~~~

If you need to search for specific strings in history, use an organization-approved secret scanning tool. Avoid passing secret values directly in commands or shell history, because terminals, command logs, and CI records may retain arguments.

You can use content search commands like <code>git log -S</code> in a controlled environment, but pass patterns via a file or appropriate tool so secrets are not recorded in shell history. Never print secrets to shared terminals or automated logs.

### Checking filenames that changed across commits

If a file was ever renamed, find all relevant historical paths. A Git filter targeting only the current path can miss older names.

~~~bash
git log --all --follow --name-status -- config/production.env
~~~

The <code>--follow</code> option helps trace a single file across renames along one history path. For repositories with multiple branches or multiple renames, inspect refs and old paths separately; never assume one command found every variant.

## 4. Choosing a history-rewriting tool

The commonly recommended tool for rewriting Git history is **git-filter-repo**. It is flexible, fast, and replaces legacy workflows based on <code>git filter-branch</code>.

| Tool | Purpose | Notes |
|---|---|---|
| git-filter-repo | Filter files, paths, blob contents, commit messages, and refs | Standard choice for history cleanup |
| BFG Repo-Cleaner | Remove large files or replace sensitive strings in history | Simpler interface for certain scenarios; still requires coordinating ref updates |
| git filter-branch | Rewrite history via shell filters | Legacy, slow, and error-prone; avoid for new workflows |

Install git-filter-repo according to your operating system or organizational guidelines. Verify:

~~~bash
git filter-repo --version
git filter-repo --help
~~~

Depending on the version, options tailored for sensitive data removal such as <code>--sensitive-data-removal</code> may be available. Check your installed version and accompanying documentation before use. The examples below focus on common history-filtering options such as <code>--invert-paths</code> and <code>--replace-text</code>.

## 5. Preparing a clean clone for rewriting

Do not experiment on the sole clone the team actively works in. Create a fresh mirror clone to get all refs and preserve the active repository as a reference.

~~~bash
git clone --mirror https://example.com/team/app.git app-clean.git
cd app-clean.git
git rev-parse --is-shallow-repository
git show-ref
~~~

A mirror clone is a bare repository containing refs fetched from the remote. The output of <code>git rev-parse --is-shallow-repository</code> should be <code>false</code> so you have full history to filter. If the source repository or clone is shallow, fetch full history before rewriting.

Before running a filter, verify:

- Correct URL and correct repository.
- A secure backup exists per incident response policy.
- All writable branches, tags, and refs have been identified.
- Everyone with push permissions has been notified to pause updates.
- A plan exists to rotate credentials and handle forks/caches.
- The cleanup clone is a dedicated working copy, not a working tree holding personal uncommitted changes.

<code>git-filter-repo</code> normally requires the repository to look like a fresh clone to prevent accidental rewrites. A fresh mirror clone is the right choice. Avoid passing <code>--force</code> just to bypass safety checks unless you understand why the tool refused.

## 6. Removing entire sensitive files from history

If a file like <code>config/production.env</code> contained tokens or passwords, you can strip that path from every commit:

~~~bash
git filter-repo --invert-paths --path config/production.env
~~~

The <code>--path</code> option selects the path to filter; <code>--invert-paths</code> keeps everything else and removes the specified path from history.

If the file previously resided in multiple locations, list every known path:

~~~bash
git filter-repo --invert-paths --path config/production.env --path deploy/production.env --path old/config.env
~~~

If you want to remove an entire directory containing sensitive data:

~~~bash
git filter-repo --invert-paths --path private-config/
~~~

After filtering, the file no longer exists in historical commits. If the application still needs that configuration, replace it with an external secret management mechanism, such as a secret manager, deployment system environment variables, or a template file containing no real values.

### Do not forget old paths

If the file was renamed, supply every old name to the filter. Filtering only the current path can leave blobs at old paths intact in history.

Inspect commits and refs before running. Never rely solely on the current working tree state to infer all historical paths.

## 7. Replacing a secret value inside file contents

Sometimes only a sensitive string appears inside a configuration file or source file while the rest of the file must be kept. You can use <code>--replace-text</code> with an expressions replacement file.

Create the expressions file in a protected location outside the repository being filtered. Example format:

~~~text
literal:OLD_SECRET_VALUE==>***REMOVED***
~~~

<code>OLD_SECRET_VALUE</code> is a placeholder, not a real value. In the actual file, substitute the string to remove. Restrict read permissions on the expressions file and never commit it.

Run:

~~~bash
git filter-repo --replace-text ../redact-expressions.txt
~~~

The tool replaces matching strings in blob contents across history. Afterward, scan the rewritten files and commits with an approved secret scanner.

If the sensitive string appears in commit messages or tag messages, use the dedicated message filtering option:

~~~bash
git filter-repo --replace-message ../redact-expressions.txt
~~~

Some binary data formats cannot be processed like plain text. For binary files containing sensitive data, remove the path or replace the file with a clean version, and address any LFS objects as well.

### Protecting the replacement expressions file

- Never put real secrets into examples, tickets, chats, or logs.
- Never commit the expressions file to a repository.
- Restrict file read permissions and delete it per procedure once finished.
- Avoid passing secrets as command-line arguments because shell history can record them.
- Never treat a revoked value as if it were no longer sensitive; handle copies according to policy.

## 8. Sensitive data in commit messages, tags, and metadata

Secrets can appear outside file contents:

- Commit messages.
- Annotated tag messages.
- Branch or tag names.
- Git notes.
- Content embedded in binary files.
- Metadata or URLs containing credentials.

<code>--replace-message</code> can process commit messages and tag messages using replacement expressions. For ref names, rename or delete refs with sensitive names. For Git notes or other metadata, identify the exact ref type and apply the appropriate filtering tool.

Rewriting commits changes the hashes of all descendant commits. GPG/SSH signatures on old commits or annotated tags will no longer validate against the rewritten content. If the project requires signing, generate new signatures following your release workflow.

Do not assume filtering files alone is sufficient. Check every place a secret can appear and every ref that can reach objects containing that data.

## 9. Reviewing results before updating the remote

After filtering, inspect refs and history in the clean clone:

~~~bash
git show-ref
git log --all --oneline --decorate
git rev-list --objects --all
~~~

Verify the removed path no longer appears in referenced history:

~~~bash
git log --all -- config/production.env
git rev-list --objects --all
~~~

For string-based secrets, run a secret scanner across all refs after rewriting. Avoid printing secret values in output. Also inspect commit messages, tag messages, and renamed files.

You cannot conclude success merely because <code>git status</code> is clean or the file is gone from the current branch. The goal is to verify all reachable refs and objects in the filtered repository.

If you find commits or refs still containing the data, fix your filter rules and re-run on a fresh clean clone. Never push an unverified cleanup.

## 10. Updating the remote after rewriting history

Local rewriting does not automatically alter the remote. You must update refs on the server so branches and tags no longer point to the old history.

First, save the remote URL because git-filter-repo may delete the remote configuration as a safety measure:

~~~bash
git remote -v
~~~

If the <code>origin</code> remote was removed after filtering, add it back:

~~~bash
git remote add origin https://example.com/team/app.git
~~~

In a thoroughly verified mirror repository, you can synchronize refs with:

~~~bash
git push --force --mirror origin
~~~

**Caution:** <code>--mirror</code> synchronizes all refs and can delete refs on the remote that no longer exist in the clone. Use it only after inventorying refs, coordinating with administrators, and understanding server policies. Some platforms maintain internal refs for Pull Requests/Merge Requests that users cannot write to; those refs may require provider intervention.

If you do not use a mirror push, explicitly update all permitted branches and tags while ensuring no old refs still retain sensitive objects. Force pushing may be blocked by branch protection; maintainers must coordinate temporary policy changes during a maintenance window per organizational procedure.

Never use <code>--force</code> casually on a repository where others are actively pushing. Freeze updates, announce the change window, and designate a single responsible operator to avoid overwriting teammates' new commits.

## 11. Limits regarding remotes, PRs/MRs, and platform caches

After force pushing, branches and tags may point to the new history. That does not guarantee the platform has immediately purged every internal copy.

Git platforms may store:

- Internal refs for Pull Requests/Merge Requests.
- Cached diffs or file view pages.
- Downloadable archives, raw file caches, or build snapshots.
- Uncollected old objects awaiting garbage collection.
- Replicas used for search, analytics, or replication.

Some internal refs cannot be updated by normal Git pushes. If the secret appeared in a PR/MR, commit view, raw URL, or public repository, contact your platform administrators or provider support to purge caches and internal refs per their process.

Do not assume deleting or closing a PR or force pushing automatically erases every preview. Document the requested cleanup scope and verify according to platform guidelines.

## 12. Forks and mirrors are independent copies

A fork is a separate repository that can retain old branches and commits. When the upstream repository rewrites history, forks are not automatically cleaned.

If a secret reached forks:

1. Identify accessible internal and external forks.
2. Notify fork owners following incident response procedures.
3. Ask them to clean history or delete the fork if it is no longer needed.
4. Contact the provider if the fork network, hidden refs, or copies cannot be fixed by owners directly.
5. Check mirror repositories and copies synchronized to other systems.

A fork can continue serving old commits even after the main branch is clean. If a user creates a new branch from old history and opens a PR back, commits containing the data can return to the upstream repository.

Therefore, after cleaning, clearly instruct contributors never to merge or push old history back. Contributors should create a fresh clone from the cleaned repository.

## 13. Teammates' clones and developer machines

Each clone is an independent copy of the object database. Force pushing on the server does not delete old commits inside the <code>.git</code> directory of machines that already cloned.

The safest approach after rewriting history is:

1. Pause pushes from old clones.
2. Preserve uncommitted work safely without re-copying the secret.
3. Re-clone the cleaned repository.
4. Transfer valid unshared changes to the fresh clone via inspected patches or cherry-picks.
5. Never merge old branches into new branches if old commits could reintroduce the secret.
6. Delete old clones and local copies per organizational policy.

If an old clone must be kept, understand that fetching does not automatically purge old objects from the object database. Resetting local branches does not guarantee removing reflogs or unreferenced objects either. Creating a fresh clone is usually easier to control.

For uncommitted work, inspect patches or copies before transferring. If a patch contains the secret, clean the patch first; never send patches via unauthorized email, chat, or tickets.

## 14. Cleaning local reflogs and unreferenced objects

After local refs are rewritten, old commits may remain in the reflog or object database. In a clone confirmed to have no remaining work to keep, you can expire reflogs and prune unreferenced objects:

~~~bash
git reflog expire --expire=now --all
git gc --prune=now
~~~

These commands affect the current local repository. They do not delete other people's clones, forks, provider caches, or objects on remote servers.

Run this only in a verified clone with an appropriate backup. Never use object cleanup commands as a substitute for rewriting refs and cleaning the remote.

To inspect local state, you can run:

~~~bash
git fsck --full
git show-ref
~~~

<code>git fsck</code> helps verify object database consistency; it is not a tool to confirm that every copy of a secret has vanished across systems.

## 15. CI caches, artifacts, logs, and backups

Sensitive data can be copied outside Git during build and deployment processes.

| Where copies may reside | What to check |
|---|---|
| CI workspace and cache | Delete or invalidate caches containing .git, config files, or secrets |
| Build artifacts | Determine whether archives, packages, or binaries embed sensitive files |
| Pipeline logs | Check whether secrets were printed to stdout, debug logs, or traces |
| Container images/layers | Check whether secrets sit in old layers, image registries, or build caches |
| Release assets | Check whether downloadable assets contain credentials or sensitive configs |
| Backups and snapshots | Apply access restrictions, retention periods, and secure deletion policies |
| IDEs and dev tools | Check local history, temp files, crash dumps, or workspace caches |
| Package registries and artifact stores | Check whether published packages contain sensitive data |

Clearing a CI cache may not delete published artifacts. Deleting the latest artifact does not necessarily remove older versions or copies in mirror registries.

Never arbitrarily delete backups subject to retention obligations. Coordinate with security, operations, or legal teams to apply appropriate retention rules, access restrictions, and disposal schedules.

## 16. Files managed by Git LFS

If a sensitive file was stored with Git LFS, the Git repository holds only a pointer; the actual content lives in LFS storage.

Filtering or deleting the pointer from Git history does not necessarily delete the LFS object already uploaded to the server. The object can remain in LFS storage or caches even when no Git ref points to it.

Additional actions required:

- Identify the LFS OID and pointers that referenced the object.
- Check whether the object still resides in the local LFS cache, CI caches, or the LFS server.
- Contact administrators/platform support to handle server-side LFS objects as supported.
- Check forks or clones that might fetch the object using an old pointer.
- Do not treat <code>git lfs prune</code> as a server-side deletion command; it only cleans the local cache.

If an LFS file contained a secret, revoke the secret first and clean both pointer history and LFS storage according to service procedures.

## 17. Submodules and related repositories

If sensitive data resides in a submodule repository, filtering the parent repository does not automatically filter the submodule's history. The parent Git repository only stores a gitlink pointing to a commit in the child repository.

You must remediate the repository holding the actual data:

1. Identify which submodule contains the file or secret.
2. Clean history in the submodule repository via its own remediation process.
3. Update the gitlink in the parent repository to point to the new submodule commit.
4. Handle clones, forks, and caches of the submodule repository.
5. Check whether scripts or pipelines fetch submodules from an old URL.

Similarly, if a secret was copied across multiple repositories, remediate each repository and copy location individually. Cleaning one repository does not clean related repositories.

## 18. Guiding teammates after history has been rewritten

Once maintainers announce that history has been cleaned and the remote updated, team members must synchronize using clear instructions.

**Recommended: fresh clone**

~~~bash
git clone https://example.com/team/app.git app-clean
cd app-clean
git status
git log --all --oneline --decorate
~~~

Then bring valid unshared changes over to the fresh clone. Never copy the entire <code>.git</code> directory from an old clone and never merge old branches containing commits with secrets.

**If an old clone must be kept**

Stop pushing, save inspected uncommitted work, fetch new refs, and create a new working branch from clean history. Only cherry-pick safe commits after confirming each commit does not carry the secret itself or reintroduce tainted ancestors. Once done, delete the old clone per policy.

Team announcements should include:

- When history was rewritten.
- Which branches/tags were updated.
- Requirement for a fresh clone or exact sync procedure.
- List of forks/mirrors requiring remediation.
- Verification commands or procedure.
- Point of contact if old commits or secrets reappear.

## 19. Post-cleanup verification

Verification must cover both Git refs and related storage systems.

In a clean clone:

~~~bash
git rev-parse --is-shallow-repository
git show-ref
git log --all --oneline --decorate
git rev-list --objects --all
~~~

Next:

- Run a secret scanner across all refs.
- Check known old and new file paths.
- Check commit messages, tag messages, and Git notes if present.
- Inspect branches/tags on the remote.
- Ask the provider to purge PR/MR refs or caches users cannot update directly.
- Verify forks, mirrors, and CI caches have been handled within authorized scope.
- Test the new credential and confirm the old credential is revoked.

<code>git ls-remote --heads --tags origin</code> shows branches/tags publicly advertised on the remote, yet it does not prove the server has purged every old object or internal cache.

Never reprint the secret in verification reports. Record only status, scope, commit hashes, or incident IDs per security policy.

## 20. Common mistakes

| Mistake | Consequence | Right approach |
|---|---|---|
| Only deleting the file in a new commit | Secret remains in older commits | Rewrite all affected history |
| Only adding .gitignore | Does not affect already-committed blobs | Remove from history and add rules to prevent recurrence |
| Force pushing only the main branch | Tags, other branches, or other refs may still hold old commits | Inventory and remediate all writable refs |
| Failing to revoke the token | Anyone who copied the token can still use it | Rotate/revoke before cleaning history |
| Assuming forks auto-update from upstream | Forks can still retain old commits | Remediate each fork and contact platform support if needed |
| Letting teammates keep pushing from old clones | History containing the secret can be reintroduced | Pause pushes, re-clone fresh, and transfer safe commits |
| Deleting only the Git pointer for LFS | Actual LFS object may remain on the server | Remediate LFS storage and caches separately |
| Running git gc on one machine and assuming complete removal | Only cleans local objects on that machine | Check servers, forks, CI, backups, and clones |
| Printing the secret in commands or tickets | Creates unnecessary additional copies | Use scanners/protected files and omit secret values from reports |
| Running --mirror without inventorying refs | Can delete or overwrite unintended refs | Audit refs and coordinate with maintainers before pushing |

## 21. Preventing recurrence

After remediation, strengthen safeguards:

- Store credentials in a secret manager or protected environment variables.
- Commit template files like .env.example containing only variable names, never real values.
- Add sensitive files to .gitignore when they do not belong in the repository.
- Enable secret scanning or pre-commit/pre-receive scanning per organizational policy.
- Protect critical branches and restrict push permissions.
- Train contributors on what to do when a secret is found staged or committed.
- Scope tokens to minimum required permissions and lifetimes.
- Rotate credentials regularly or whenever exposure is suspected.
- Audit CI logs, artifacts, and caches to avoid accidentally publishing secrets.

<code>.gitignore</code> helps prevent certain files from being newly added, but it is not a secret management system. Secrets still require proper provisioning, storage, revocation, and access control in appropriate systems.

## 22. Sample remediation workflow

Suppose a <code>config/prod.env</code> file containing a production access token was pushed to a remote.

**Step 1 — Revoke the token**

Invalidate the old token, issue a new token in the secret manager, and inspect usage logs to evaluate anomalous activity.

**Step 2 — Pause pushes**

Notify the team to halt pushes to the repository during history rewriting. Inventory affected branches/tags/PRs and forks.

**Step 3 — Create a clean mirror clone**

~~~bash
git clone --mirror https://example.com/team/app.git app-clean.git
cd app-clean.git
git rev-parse --is-shallow-repository
git show-ref
~~~

**Step 4 — Remove the file from history**

~~~bash
git filter-repo --invert-paths --path config/prod.env
~~~

If the file previously had other names, add each historical path to the command.

**Step 5 — Verify the result**

~~~bash
git log --all -- config/prod.env
git show-ref
git rev-list --objects --all
~~~

Run a secret scanner across all refs and check other locations that might contain the token.

**Step 6 — Update the remote**

If the filter deleted the <code>origin</code> remote, add back the verified URL. After inventorying refs and receiving maintainer approval, synchronize the cleaned refs. For a mirror workflow, <code>git push --force --mirror origin</code> can be used once ref scope and delete/overwrite effects are fully understood.

**Step 7 — Handle copies**

Contact the platform to purge caches and internal refs; request forks/mirrors to be cleaned; delete or replace CI caches/artifacts containing the file; apply policy to backups.

**Step 8 — Resynchronize teammates**

Require fresh clones. Transfer inspected valid changes; never merge old history back in.

**Step 9 — Verify and close the incident**

Run scanners, check remote refs, confirm the old credential is invalid, and document all remediated systems. Reports must not contain secret values.

## 23. Checklist for handling sensitive data in Git

- [ ] Revoked or replaced the exposed credential.
- [ ] Identified data category and blast radius.
- [ ] Checked all branches, tags, commits, and historical paths.
- [ ] Checked commit messages, tag messages, PRs/MRs, and notes as needed.
- [ ] Created a full mirror clone and secure backup.
- [ ] Used git-filter-repo or an appropriate tool to rewrite history.
- [ ] Verified results with a secret scanner across all refs.
- [ ] Updated remote refs according to the approved plan.
- [ ] Requested the provider to purge caches or internal refs if needed.
- [ ] Checked forks, mirrors, clones, CI caches, artifacts, logs, and backups.
- [ ] Handled Git LFS or submodules separately if applicable.
- [ ] Instructed teammates to re-clone fresh and avoid reintroducing old history.
- [ ] Confirmed old credentials are disabled and preventive controls are added.

## 24. Key takeaways

- A committed secret must be treated as exposed; revoke or rotate the credential before cleaning history.
- Deleting the file in a new commit or adding .gitignore does not remove blobs in older commits.
- git-filter-repo is a standard tool for removing paths or replacing content across history.
- Rewriting history changes commit hashes, can invalidate signatures, and requires force-updating refs.
- Audit all writable branches, tags, and refs; mirror pushes can delete remote refs, so inventory first.
- Force pushing does not automatically purge forks, clones, caches, PR/MR refs, artifacts, logs, or backups.
- Git LFS objects and submodule repositories require separate remediation if they hold sensitive data.
- A fresh clone is usually the most reliable way for teammates to resume from clean history.
- Secret scanners and credential management workflows reduce the risk of repeat incidents.

Cleaning Git history is part of incident response, not a substitute for revoking secrets. Revoke the credential, rewrite controllable refs, coordinate cleanup of forks/caches/copies, and verify thoroughly afterward. Only when these steps are executed together is the risk of continued unauthorized access meaningfully reduced.

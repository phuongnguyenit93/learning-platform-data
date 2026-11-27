# Incident Drill: Committed Secret and Coordinating Revocation and History Cleanup

A developer accidentally commits a configuration file containing an API token to a feature branch, pushes it to the remote, and opens a pull request. The token is now in commit history and may already have been downloaded by the Git server, CI, reviewers, forks, or teammates' clones. Deleting the file in the latest commit does not remove the token from older commits; rewriting history does not invalidate the token and does not automatically erase copies already made.

This lab simulates how a team handles the incident from detection through closure: containing exposure, revoking the secret at the issuing system, scoping the exposure, cleaning history with dedicated tooling, updating the remote, and coordinating clone resynchronization. The focus is on action ordering and responsibilities across developers, repository maintainers, secret owners, and CI/CD operators.

In Git source management, protecting history is only part of incident response. The secret must be revoked or rotated at its issuer before cleaning up Git. Existing copies, logs, artifacts, and caches must be handled separately per organizational security policy.

## 1. Drill Objectives

After this lab, the team can:

- Recognize a committed secret and assess whether it has been pushed.
- Contain exposure and revoke credentials at the issuing system.
- Record required evidence without copying the secret into tickets or logs.
- Identify commits, branches, tags, pull requests, and systems that may hold the secret.
- Use `git filter-repo` to remove paths or replace content across history.
- Verify the cleaned history before updating the remote.
- Coordinate force-updating branches/tags, handle platform-managed refs, and guide members to resync clones.
- Clean CI workspaces, caches, artifacts, forks, and LFS within the proper scope.
- Verify the incident is contained and complete incident closure documentation.

## 2. Simulated Scenario

A developer adds `config/production.env` to run the application locally. The file contains an API token used to call the payment service. The developer commits this file alongside a feature change:

```text
A --- B --- C --- D  feature/payment
                  ^
                  D contains config/production.env
```

The branch is then pushed to the remote and a pull request is opened. CI ran on commit D; a reviewer fetched the branch; another team member may have cloned the repository.

Simulated incident details:

| Attribute | Simulated value |
| --- | --- |
| Repository | `team/payment-service` |
| Branch | `feature/payment` |
| Exposed file | `config/production.env` |
| Secret type | API token with permission to call the payment service |
| Detected commit | `D` |
| Status | Pushed to remote, pull request open |
| Affected systems | Secret provider, Git host, CI, developer clones, pull request |

All repository names, file paths, and commit IDs in this lab are illustrative. Never put real tokens into practice materials, screenshots, chats, shell commands, or documentation.

## 3. Incident Response Principles

**Revoke or disable the secret before rewriting history.** As long as the token remains valid, anyone holding an old commit copy can still use it. Git cleanup takes time and cannot revoke credentials at the provider.

Principles to follow:

1. Treat any secret pushed to a remote as potentially compromised, even in a private repository.
2. Do not wait to confirm unauthorized usage before revoking the token.
3. Never paste the secret into issues, chats, emails, terminal output, or incident reports.
4. Do not force push before inventorying refs and announcing a write freeze.
5. Keep required audit evidence in access-restricted storage; do not replicate the secret across routine backups.
6. Prevent stale clones or stale pipelines from pushing pre-rewrite history back to the remote.
7. Handle non-Git copies such as CI logs, artifacts, forks, caches, and LFS separately.

Rewriting history changes commit IDs. It does not replace secret management, access investigation, or incident notification required by organizational policy.

## 4. Roles in the Drill

| Role | Responsibilities |
| --- | --- |
| Reporter | Reports the incident through the security channel, providing the repository, commit, and affected path; does not share the secret value |
| Incident commander / coordinator | Assesses severity, assigns owners, decides when to freeze and reopen writes |
| Secret owner / service owner | Revokes the old token, issues new credentials, checks access logs and permission scope |
| Repository maintainer | Inventories refs, backs up, runs filters, verifies, and updates the remote |
| CI/CD owner | Rotates secrets in pipelines, pauses write-capable jobs, clears workspaces/caches/artifacts per policy |
| Developers and reviewers | Stop pushing, protect local work, re-clone or port verified work |
| Security / platform team | Inspects audit logs, forks, hidden refs, server caches, and copies not managed by developers |

One person may cover multiple roles in a small team, yet it must be clear who owns secret revocation and who is authorized to update the remote.

## 5. Phase 1 — Intake and Incident Containment

Immediately upon detection:

1. Record the detection timestamp and reporter.
2. Identify the repository, branch, commit, and path(s) that may contain the secret.
3. Notify the incident commander and secret owner through approved channels.
4. Pause jobs or workflows that might use the exposed credential.
5. Ask the team to halt pushes, merges, tag creation, and updates to affected branches during the remediation window.
6. Restrict repository access if risk assessment requires it; performed by the repository/security owner per policy.

Do not immediately delete the repository, branch, or pull request upon detection. Preserve necessary metadata and audit evidence for investigation first, while avoiding copying secret contents outside controlled scope.

### Information to Record

- Repository URL and branch name.
- Suspect commit ID containing the secret.
- File path and credential type.
- Commit, push, and detection timestamps.
- Related pull requests, pipeline runs, and artifacts.
- Users or systems with access during the exposure window.

Never write token values, passwords, or private keys into an incident ticket. To reference a secret, use a fingerprint or identifier provided by the secret provider per internal security procedures.

## 6. Phase 2 — Revoking and Rotating the Secret

The secret owner revokes the credential at the issuing system. Examples:

| Secret type | Containment action |
| --- | --- |
| Personal access token / API token | Revoke old token; issue a new least-privilege token if still needed |
| Database password | Rotate password; check users/service accounts and connection pools |
| Private key | Revoke or replace the corresponding key/certificate; update auth systems |
| OAuth refresh token | Revoke associated tokens/sessions and re-authenticate the app |
| Cloud access key | Disable old key; create a new identity/key or switch to short-lived identities |
| Signing key | Execute key compromise procedure; revoke certificates or rotate keys per issuing policy |

General workflow:

1. Identify the secret owner and issuing system.
2. Disable the old secret as soon as you have enough details to identify it.
3. Review provider audit logs across the potential exposure window.
4. Determine what permissions and resources the token could access.
5. Issue a replacement credential with least privilege and appropriate expiration.
6. Update secret stores, deployments, and authorized applications with the new credential.
7. Verify the application works with the new credential.
8. Confirm the old credential no longer works.

Do not copy the new token into committed configuration files. Use a secret manager or organization-approved credential injection mechanism.

### Checking for Unauthorized Usage

The service owner should inspect audit logs for:

- Logins or API calls from unusual IP addresses, devices, or regions.
- Access to repositories, packages, data, or resources outside normal usage.
- Permission changes, newly created credentials, or unexpected admin actions.
- Activity occurring after commit/push and before revocation.

Never assume absence of audit events means the token was unused. Logging coverage depends on the service and log retention periods.

## 7. Phase 3 — Scoping the Secret in Git

Once the credential is revoked or disabled, the repository maintainer scopes the history requiring cleanup.

### Inspecting Current State

In an investigation clone:

```bash
git status -sb
git branch -a
git tag --list
git log --all --oneline --decorate -- config/production.env
```

These commands show working tree state, local branches/tags, and commits modifying the specified path. `git log --all -- <path>` alone does not prove every server copy or hidden ref is clean; it only inspects refs known to the current clone.

### Inventorying Refs

```bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
```

Record advertised branches and tags. For pull request refs, forks, or internal Git-host refs, check using admin tools or ask the platform owner because standard clones may not fetch all refs.

### Finding Former Paths

If the file was ever renamed or moved, list every path that may have held the secret. For example:

```text
config/production.env
deploy/legacy/production.env
ops/credentials/payment.env
```

Filtering only the current path can miss older copies at previous paths. Check rename history and related commits without printing secret values to output.

### Identifying Content Outside That File

The secret may also have been committed in:

- Config files or source code.
- Commit messages or annotated tag messages.
- Scripts, fixtures, documentation, or template files.
- CI-generated logs and output files.
- Binary files or LFS objects.

If the secret appears in blob contents across multiple files, use a secret scanner or content-replacement rules across all history. If the secret resides solely in a dedicated file, path filtering may be cleaner.

## 8. Phase 4 — Freezing Writes and Creating an Isolated Working Copy

Before rewriting history:

- Clearly announce the maintenance window start and end times.
- Pause pushes, merges, tag creation, and write-capable workflows.
- Instruct developers not to push from old clones.
- Record current refs and branch tip commits to be processed.
- Confirm who is authorized to run filters and update remotes.

Create a fresh mirror clone from the remote:

```bash
git clone --mirror https://git.example.com/team/payment-service.git payment-service-rewrite.git
```

A mirror clone is a bare repository suited for working across all branches and tags. Enter the directory:

```bash
cd payment-service-rewrite.git
git show-ref
git remote -v
```

`git filter-repo` normally requires a fresh clone to prevent accidentally rewriting a repository with local work. If the tool refuses because the repo is not recognized as a fresh clone, create a fresh mirror clone instead of casually passing `--force`.

### Protecting Copies and Evidence

The pre-filter mirror clone still contains the secret. If you must retain a copy for investigation or recovery, store it in an encrypted, isolated location with restricted access and an explicit expiration date. Never use it as a working clone or normal remote.

Prefer retaining audit metadata, commit IDs, ref maps, and incident timelines per policy. If policy requires purging every copy of the secret, coordinate with the security owner to handle old backups; never keep a secret-bearing backup indefinitely on your own.

If the repository uses Git LFS, a Git mirror clone does not guarantee all LFS contents are downloaded. Fetch/back up LFS objects in an isolated area only when investigation requires it and proper access is authorized:

```bash
git lfs fetch --all origin
```

## 9. Phase 5 — Choosing the History Cleanup Approach

Before filtering, select the right approach:

| Scenario | Approach |
| --- | --- |
| Secret exists only in one config file | Remove that path from all history |
| Secret was copied into multiple text files | Replace strings across history and verify with a scanner |
| Config file needs a template kept without credentials | Replace with safe placeholders or drop the file and add a clean template |
| Secret existed under multiple former paths | Filter every path ever used |
| Secret sits in an LFS object | Clean pointers in Git and purge LFS storage via host procedure |
| Secret sits in non-Git logs/artifacts | Delete or restrict artifacts/logs via CI and storage procedures |

Running `git rm` and committing only removes the file from the latest snapshot. `git revert` creates a commit reversing the change, yet the older commit still holds the secret. Removing content from historical commits requires rewriting history.

## 10. Using git-filter-repo to Remove a File From All History

Suppose `config/production.env` contains the secret and no version of that file needs to stay in Git. Inside the fresh mirror clone, run:

```bash
git filter-repo --path config/production.env --invert-paths
```

If the file previously existed at multiple paths:

```bash
git filter-repo \
  --path config/production.env \
  --path deploy/legacy/production.env \
  --path ops/credentials/payment.env \
  --invert-paths
```

`--invert-paths` inverts the selection, removing the listed paths from filtered history. Paths are relative to the repository root. Verify all old and new names before running.

If you want to keep a secret-free template file, recreate it after filtering using reviewed template content, for example:

```dotenv
PAYMENT_API_TOKEN=
PAYMENT_API_URL=https://api.example.test
```

The template declares only variable names; the application reads real values from a secret store or protected environment. Never commit real tokens.

## 11. Replacing a Secret That Appeared in Multiple Files

If the token was copied into several text files, `git filter-repo` supports `--replace-text`. Create a replacement file outside the rewrite repository, such as `../secret-replacements.txt`, formatted as:

```text
literal:EXAMPLE_OLD_TOKEN_VALUE==>***REDACTED***
literal:EXAMPLE_OLD_PASSWORD==>***REDACTED***
```

These strings are illustrative placeholders. In a real incident, the replacement file may need the real secret string to match accurately; create and store it in an access-restricted location, and never print its contents to a terminal or put it inside the repository.

Run:

```bash
git filter-repo --replace-text ../secret-replacements.txt
```

You can combine path removal and text replacement when needed:

```bash
git filter-repo \
  --path config/production.env \
  --invert-paths \
  --replace-text ../secret-replacements.txt
```

`--replace-text` operates on text blob contents; it does not alter commit messages or annotated tag messages. Expression files support formats like `literal:`, `regex:`, or `glob:` depending on tool version; check `git filter-repo --help` before using complex patterns. If the secret appears in messages, use `--replace-message` with a dedicated expression file:

```bash
git filter-repo --replace-message ../message-replacements.txt
```

`--replace-message` applies to commit and tag messages. Protect that expression file just like the content-replacement file if it contains real secret strings. If the secret sits inside a binary blob, `--replace-text` is not suitable; identify the file holding the data and remove its path or use a format-specific procedure.

Never pass real secrets in CLI arguments, shell history, or commands copied into tickets. When a replacement file must hold real values, protect it with OS file permissions and securely delete it per procedure once done.

Replacing content in Git does not revoke the token. The secret must still be revoked/rotated at the provider, even after scanners confirm the string is gone from rewritten history.

## 12. Verifying Cleaned History

Do not push immediately after filtering finishes. Verify the results inside the mirror clone first:

### Checking Paths

```bash
git log --all --oneline -- config/production.env
git log --all --oneline -- deploy/legacy/production.env
git show-ref
```

Path-filtered logs should show no commits touching the removed files across the filtered refs. Double-check the ref list to confirm the expected scope was processed.

### Checking Integrity

```bash
git fsck --full
git count-objects -vH
```

Review `fsck` output and resolve any missing/corrupt object errors. Dangling/unreachable notices should be evaluated against repository state; do not confuse them with proof that the secret remains reachable from branches/tags.

### Scanning Secret Across All History

Run an organization-approved secret scanner against the rewritten repository and relevant refs. Configure the scanner to scan full history, branches, and tags; scanning only the current working tree is insufficient.

Scanner reports must not print raw secret values. Record only finding type, path, commit ID, and remediation status in a safe format.

### Checking Commit and Ref Maps

`git filter-repo` can write metadata such as `commit-map` and `ref-map` in its metadata directory. These maps help correlate old and new commits/refs and update references in external systems.

Store necessary metadata in controlled incident records. Do not place sensitive content or copies of old history in public storage.

### Checking Post-Filter State

```bash
git log --all --oneline --decorate -20
git branch --all
git tag --list
git rev-parse --is-bare-repository
```

For a mirror clone, `git rev-parse --is-bare-repository` confirms the repository is bare. Focus verification on refs, the commit graph, the scanner, and the object database.

## 13. Phase 6 — Restoring the Remote and Updating Branches/Tags

`git filter-repo` normally removes the `origin` remote from config to prevent accidentally pushing rewritten history. Check:

```bash
git remote -v
```

If no remote remains, add the official URL back:

```bash
git remote add origin https://git.example.com/team/payment-service.git
git remote -v
```

Verify the URL points to the exact target repository and contains no username/token.

Only update the remote when:

- The old secret has been revoked or disabled.
- Filter results have been inspected and cleared by the scanner.
- Backups/evidence are secured per policy.
- Developers and CI have been instructed not to push from old clones.
- The repository maintainer is authorized to update refs.

### Updating Branches

```bash
git push --force --all origin
```

This updates local branches onto the remote. It does not automatically delete remote branches absent locally and does not clean up hidden platform-managed refs.

### Updating Tags

```bash
git push --force --tags origin
```

Verify release tags after rewriting. Annotated tags may be recreated and old signatures will no longer verify against the new objects. If a tag must be removed completely, delete it explicitly by name after release-owner approval:

```bash
git push origin --delete v2.4.0
```

Never delete release tags solely because of a rewrite; follow your project's versioning and audit policies.

### Special Git Host Refs

Pull request refs, merge request refs, internal refs, or host-managed refs cannot always be cloned or pushed like normal branches. Repository maintainers must coordinate with platform owners or provider support to clear cached views, PR refs, and server-side copies users cannot update directly.

Avoid mechanically running `git push --mirror` against a shared remote. A mirror push can delete refs not present in your mirror clone, including platform-managed refs. Scope branch/tag pushes explicitly and handle special refs per your host's instructions.

## 14. Phase 7 — Resynchronizing Developer Clones

Old clones still hold commits containing the secret. If a team member pushes an old branch, the old history can be reintroduced onto the remote. Instruct everyone to stop using old clones and switch to the cleaned history.

### Recommended Approach: Fresh Re-Clone

1. Save unshared local work using a safe workflow.
2. Never archive or send old clones over chat or email.
3. Move old clones to quarantine if needed for investigation; otherwise dispose of them per data deletion policy.
4. Re-clone from the cleaned remote.
5. Verify branches, tags, and run a scanner on the new clone.
6. Reapply reviewed local changes, ensuring patches contain no secrets.
7. Never merge an old branch into a new branch, as that reattaches the old history.

Example:

```bash
git clone https://git.example.com/team/payment-service.git payment-service-clean
```

### If Local Changes Must Be Kept

Do not blindly cherry-pick or merge commits from an old clone. A commit may contain a secret in its diff or in a file no longer visible at the tip. Review the changes you need to keep, strip any secrets, and apply only the valid logic onto the new branch via an inspected patch or manual edits.

If cherry-picking, select only commits verified not to reintroduce secrets or old parent history. Cherry-picking creates a new commit on current history, yet it can still reapply secret content if that commit's diff includes it.

### Preventing Pushes From Old Clones

Communicate clearly:

- Do not push old branches.
- Do not reopen PRs from old commits.
- Do not merge backup branches containing secrets into cleaned branches.
- Do not use old tags pointing to pre-rewrite commits.
- Alert the maintainer immediately if old commits reappear on the remote.

## 15. Phase 8 — Cleaning CI/CD, Forks, and Artifacts

The Git remote is not the only place commit content is stored. CI and auxiliary systems can hold old snapshots.

### CI/CD

The CI owner should:

1. Revoke/rotate credentials stored in pipeline secret stores.
2. Halt old jobs capable of pushing or publishing.
3. Clear Git workspaces and caches according to runner procedures.
4. Inspect logs, test reports, artifacts, and build outputs that might contain the secret.
5. Delete or restrict access to affected artifacts/logs per retention policy.
6. Re-clone/re-fetch from the cleaned history.
7. Verify new jobs do not use old credentials or push old refs.

Never enable debug logging or print environment variables to verify secrets. Rely on secret provider status and approved verification mechanisms.

### Forks and Pull Requests

Forks may still retain old commits. Fork owners and platform owners must coordinate to sync or delete forks per policy. Pull requests can preserve diffs, comments, patches, or internal refs; rewriting a branch does not guarantee every PR copy is erased.

Check:

- Organization forks and accessible personal forks.
- Open or closed PRs/MRs.
- Patch downloads, review bundles, and commit links.
- Cached diff views retained by the host.

If users lack permission to clear refs or caches, escalate the request to platform administrators or provider support.

### Git LFS and Artifact Storage

If the secret-bearing file was tracked by Git LFS, filtering pointers in Git does not delete the binary object from the LFS server. Identify the OID and follow the provider's LFS purge procedure after confirming no valid version still needs to be retained.

If the file was published into a package, release asset, container image, or CI artifact, remediate it in the corresponding system. Deleting a commit does not remove published packages or container images.

## 16. Phase 9 — Verifying the Remote After Updating

After force-updating refs, create a fresh independent clone from the remote:

```bash
git clone https://git.example.com/team/payment-service.git payment-service-verify
cd payment-service-verify
git show-ref
git log --all --oneline --decorate -20
```

Run a secret scanner across the full cloned history. Verify:

- Sensitive files or strings no longer appear in advertised branches or tags.
- Expected branches and tags point to the new commits.
- Pull requests and special refs were handled per host procedure.
- No developer or pipeline pushed old commits back.
- New CI runs succeed with rotated credentials.
- Applications consume the new secret from the secret store.

Monitor the remote for a period after reopening writes. If old commits reappear, halt pushes immediately, identify the source actor/ref, and repeat cleanup from that source.

## 17. Protecting Backups and Handling Secret-Bearing Copies

Pre-rewrite backups can hold the revoked secret. Classify each copy:

| Copy | Handling |
| --- | --- |
| Investigation mirror backup | Isolate, encrypt, restrict access, and set a deletion deadline |
| Developer local clones | Re-clone; delete or quarantine old clones per policy |
| CI workspaces/caches | Wipe old workspaces/caches and issue new credentials |
| Logs/artifacts | Scope exposure, restrict access, or purge per retention |
| Forks | Coordinate with owners/platform to sync or delete |
| LFS objects | Execute host's LFS purge workflow |
| Releases/packages/container images | Revoke or replace artifacts per release procedure |

Never retain a secret-bearing backup indefinitely just in case a rollback is needed. If evidence preservation is required, prefer audit metadata and controlled isolated copies; retention or destruction of sensitive material must follow incident commander and security owner approval.

## 18. Timeline Coordination Playbook

| Milestone | Responsible owner | Action | Completion evidence |
| --- | --- | --- | --- |
| T0 — Detection | Developer | Report repository, commit, file, and secret type via security channel | Ticket has metadata without secret values |
| T0+ | Secret owner | Revoke old token, check audit logs, issue replacement credential if needed | Provider confirms old token is invalidated |
| T1 | Incident commander | Freeze pushes/merges and assign owners | Maintenance notice sent |
| T1 | Repository maintainer | Inventory refs, PRs, tags, and path scope | List of affected refs and commits |
| T2 | Repository maintainer | Isolate backup, run filter in mirror clone | Commit map/ref map and operation logs |
| T2 | Security owner | Scan rewritten history | Scanner confirms no actionable findings remain |
| T3 | Repository maintainer | Force update approved branches/tags | Remote refs point to new history |
| T3+ | Platform/CI owner | Remediate PR refs, caches, CI, LFS, and artifacts | Confirmation that auxiliary systems are cleaned |
| T4 | Developers | Re-clone and reapply inspected local changes | Developers confirm using new history |
| T5 | Incident commander | Reopen writes, monitor, and close incident | Verification log and preventive action items |

Milestones represent coordination ordering, not SLAs. Severe incidents may require longer freezes or specialized response workflows.

## 19. Secret-Free Internal Notification Template

When notifying the team, include only essential details:

```text
Subject: Temporary push freeze on payment-service for credential incident remediation

A credential appeared in Git history on branch feature/payment.
The old credential is being revoked / has been revoked by the service owner.

During the remediation window:
- Pause pushing, merging, and creating tags in the repository.
- Stop pushing from existing local clones.
- Do not copy or send suspect configuration files over chat or email.
- Wait for re-clone instructions once the maintainer verifies the cleaned history.

The repository maintainer will notify everyone once the remote and CI are verified.
If you have unpushed local changes, keep them locally and contact the
maintainer to port inspected work safely.
```

Never attach tokens, config files, screenshots showing credentials, or diffs containing secrets.

## 20. Common Mistakes in Incident Response

| Mistake | Why it is insufficient or dangerous | Proper approach |
| --- | --- | --- |
| Only deleting the file in the latest commit | Older commits still contain the blob | Revoke secret and rewrite all affected history |
| Reverting the secret-exposing commit | Old commit remains reachable in history | Revoke token; use dedicated history filtering to strip from history |
| Rewriting history before revoking the token | Token remains usable during remediation | Revoke/disable immediately at the provider first |
| Scanning only the current working tree | Secret may still exist in older commits or tags | Scan full history and all advertised refs |
| Filtering only the current filename | Older copies may sit under pre-rename paths | List all historical paths |
| Force pushing immediately after filtering | May miss refs, overwrite new commits, or delete host refs | Freeze writes, inventory, and update refs per plan |
| Running `--mirror` without checking | Can delete special platform refs on the remote | Push scoped branches/tags and coordinate with platform owners for hidden refs |
| Letting developers keep using old clones | Old commits can be pushed back | Require fresh clones or porting inspected patches |
| Forgetting CI caches and artifacts | Secret persists outside Git | Remediate workspaces, logs, artifacts, and secret stores separately |
| Assuming deleting an LFS pointer deletes the LFS object | Binary may remain on the LFS server | Execute the host's LFS purge workflow |
| Storing secret-bearing backups in normal locations | Creates extra exposed copies | Isolate, encrypt, restrict permissions, and enforce retention |

## 21. Incident Closure Checklist

### Credentials

- [ ] Old secret revoked/disabled.
- [ ] Replacement credential issued with least privilege.
- [ ] Applications and pipelines switched to the new credential.
- [ ] Audit logs reviewed within available scope.

### Git History

- [ ] Inventoried affected branches, tags, and refs.
- [ ] Filtered all old/new paths or identified secret contents.
- [ ] Secret scanner scanned full rewritten history.
- [ ] `git fsck --full` reported no missing/corrupt objects.
- [ ] Remote branches/tags updated according to plan.
- [ ] Hidden refs and pull request refs handled by platform owner.

### Copies and Auxiliary Systems

- [ ] Developers re-cloned or resynchronized per instructions.
- [ ] No stale clones remain authorized to push.
- [ ] CI workspaces/caches and credentials remediated.
- [ ] Logs, artifacts, releases, packages, and container images evaluated.
- [ ] Forks and LFS objects resolved.
- [ ] Old backups quarantined or destroyed per policy.

### Monitoring and Prevention

- [ ] Repository writes reopened after owner sign-off.
- [ ] Monitored to ensure old commits do not reappear.
- [ ] Enabled or tuned secret scanning / pre-commit controls.
- [ ] Updated guidance on secret managers and template files.
- [ ] Documented lessons learned and preventive action owners.

## 22. Practicing in a Simulated Repository

Use only fake tokens—never real credentials or production data.

### Phase A — Create the Incident

1. Create a test repository with a file `config/demo.env`.
2. Put a fake string such as `DEMO_TOKEN_DO_NOT_USE` into the file.
3. Commit the file and make one additional commit.
4. Create a test branch/tag and push to a remote you control.
5. Record the commit IDs, branches, and tags containing the file.

### Phase B — Simulated Revocation and Scoping

1. Freeze writes on the test remote.
2. Record refs with `git show-ref`.
3. Inspect file history with `git log --all -- config/demo.env`.
4. Identify any former paths if the file was renamed.
5. Record incident metadata without putting the fake string into a public ticket.

### Phase C — Cleanup

1. Create a fresh mirror clone.
2. Run `git filter-repo --analyze` if needed.
3. Run `git filter-repo --path config/demo.env --invert-paths`.
4. Inspect refs and history after filtering.
5. Run a test scanner or verify path history across all refs.
6. Re-add the official remote for your lab environment.
7. Force-update branches/tags on the test remote.

### Phase D — Resync and Verify

1. Re-clone the remote into a new directory.
2. Confirm the demo file is gone from the new history.
3. Simulate a developer with an old clone and explain why pushing from it is prohibited.
4. Port a valid change into the new clone via a reviewed patch.
5. Complete the incident closure checklist and note non-Git systems requiring attention.

Never force-push to shared or production repositories during a lab.

## 23. Knowledge Self-Check

1. Why must you revoke a token before rewriting Git history?
2. Why must a private repository still treat a pushed token as potentially compromised?
3. Do `git rm` and `git revert` remove a secret from older commits?
4. When should you use `--path ... --invert-paths` vs. `--replace-text`?
5. Why must you check all historical paths after a file has been renamed?
6. Why must a pre-rewrite mirror backup clone be isolated?
7. Which refs do `git push --force --all` and `git push --force --tags` update?
8. Why should you avoid mechanically running `git push --mirror` against a Git host?
9. Which systems can retain a secret outside the Git object database?
10. Why should developers re-clone rather than merge an old branch into the new history?
11. What scope must a secret scanner cover to verify results?
12. What conditions must be met before reopening push permissions?

## Conclusion

When a secret is committed and pushed, treat it as a credential incident: contain exposure, revoke or disable the secret at the provider, review audit logs, and only then clean Git history. Use `git filter-repo` inside an isolated mirror clone to remove paths or replace content, scan full history, and verify refs before updating the remote. After rewriting, coordinate developer re-clones, clean CI/caches/artifacts/forks/LFS, and block old clones from pushing old commits back. Close the incident only once the old credential is invalidated, rewritten history is verified, and non-Git copies have assigned owners and confirmed remediation.

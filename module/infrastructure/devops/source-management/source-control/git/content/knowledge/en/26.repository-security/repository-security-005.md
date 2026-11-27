# Revoking Exposed Secrets Before Cleaning History

When an API key, password, access token, or private key appears in a Git commit, treat it as a security incident. Deleting the line containing the secret from the file or creating a new commit does not remove the old data from history. Anyone who can read the older commit can still retrieve the exposed value and attempt to use it.

The order of operations matters: **invalidate or revoke the exposed secret, issue and deploy replacement credentials, and only then clean Git history and coordinate updating copies**. If you only rewrite history without revoking the credential, anyone who already obtained the old value can still use it. If you only revoke the credential without cleaning history, the secret remains in the repository, clones, caches, or artifacts and can continue to be discovered.

This lesson belongs to the **Repository Security** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also trains branch-based collaboration, conflict resolution, change tracking, and recovering from mistakes while preserving important history. This lesson focuses on the response workflow once a secret has been committed or shared via a repository.

## 1. What counts as an exposed secret?

A secret is information that can grant access or expose data that unauthorized parties should not know. In software projects, common types include:

- Third-party service API keys.
- Access tokens, refresh tokens, personal access tokens, or deploy tokens.
- Database, service account, or administrator passwords.
- SSH, TLS, or signing private keys.
- Client secrets, webhook secrets, and signing secrets.
- Connection strings containing authentication credentials.
- Environment configuration files containing real passwords or tokens.
- Cloud, registry, CI/CD, or monitoring system credentials.

Not every token-like string is an active credential. However, until its scope and status are verified, protect the value like a real secret. Never paste a secret into issues, pull requests, chats, logs, or shell commands just to ask someone else to check it.

## 2. Why revoke before rewriting history?

Git stores snapshots by commit. If an older commit contains a secret, that commit may still be reachable via branches, tags, pull requests, reflogs, or teammates' clones. Deleting the file in a new commit only changes the latest snapshot.

Suppose the history looks like this:

~~~text
A: add config/prod.env (contains credentials)
|
B: update application
|
C: remove config/prod.env
~~~

At commit C, the file is no longer in the current snapshot. Yet commit A still contains the credentials. If someone checks out A or views the diff of that commit, they can still read the old values.

Rewriting history can give commit A and its descendant commits new hashes, but it does not automatically invalidate the old credential. An older clone or a cached copy may still contain that content. Therefore:

1. Revoke or disable the exposed credential.
2. Issue a new credential and update the systems using it.
3. Determine the exposure scope and audit for suspicious activity.
4. Only then clean history and related copies.

This sequence reduces the risk of the credential continuing to be used while the team cleans up the repository.

## 3. Distinguishing credential revocation and rotation

These two actions often go together, yet they serve different purposes:

| Action | Meaning | Examples |
|---|---|---|
| Revoke / disable | Make the old credential no longer accepted | Disable API key, revoke token, revoke certificate |
| Rotate | Create a replacement credential and switch systems to the new value | Generate new API key, change database password, replace private key |

For some services, you can create a new credential, deploy it to the application, and revoke the old credential immediately after verifying operation. If there are signs of active exploitation, prioritize disabling the exposed credential per incident response procedures, even if doing so requires coordination to restore the service.

Examples by credential type:

- **API keys or tokens:** disable or revoke the old value in the provider's admin console; create a new key with the minimum required permissions.
- **Database passwords:** change the password or create a new service account; update secret stores, environment variables, and affected workloads.
- **Private keys:** replace the key pair, update the public key or certificate on trusted systems, and revoke the old key/certificate if supported by the mechanism.
- **Cloud credentials:** disable the exposed access key, create a replacement key, or migrate the workload to a short-lived identity.
- **Webhook/signing secrets:** replace the secret on both the sender and verifier sides, then confirm new signatures are accepted.

Never put the new credential into Git to replace the old one. Store it in a secret manager, protected configuration store, or the deployment platform's credential provider.

## 4. Immediate actions when a secret is found in a commit

When a secret is discovered, start with these steps:

1. Report the incident through your internal security channel or system owner.
2. Identify the credential type, provider, granted permissions, and environment in use.
3. Revoke or disable the old credential; issue and deploy a replacement value.
4. Check access logs, audit logs, billing, or anomalous activity starting from when the credential may have been exposed.
5. Record the repository, commit hash, branch/tag, file path, and discovery time; never copy the secret value into the report.
6. Pause pushes or merges to affected branches while preparing to clean history.
7. Identify which remotes received the repository, who has access, and whether any forks or mirrors are involved.

If the secret was only committed locally and never left the machine, the exposure scope may be smaller. Even so, verify backups, logs, folder sync tools, and other utilities that could have copied the data. Deciding whether to rotate must be based on security policy and evidence of exposure; for any credential that could have been shared, treat it as compromised.

## 5. Identifying where the secret appeared

Before modifying history, map out the scope to handle:

- The first commit containing the secret.
- Subsequent commits that copied or edited that value.
- Which branches and tags point to the affected commits.
- Whether the secret appears in multiple files, filenames, scripts, test fixtures, or documentation.
- Which remotes received the commit: origin, forks, mirrors, or other repositories.
- Which pull requests, releases, CI artifacts, packages, images, or logs might contain the content.
- Team members' local clones and build machines that may still retain old history.

Useful commands to locate related paths and history:

~~~bash
# View commits that modified a path
git log --all --oneline -- config/prod.env

# View existing refs and tags
git branch -a
git tag --list

# Inspect a suspicious commit without printing secret values into reports
git show --stat <commit-hash>
~~~

If you need to search for specific content, run an approved secret scanner in a secure environment with value masking enabled. Never run commands that print full lines containing secrets to shared terminals or CI logs. When sharing findings, record only the secret type, file path, commit hash, and remediation status.

## 6. Cleaning current files

Once the old credential has been revoked, fix the working tree so new snapshots no longer store the secret.

### If the file holds only local configuration

Suppose <code>config/prod.env</code> is meant only for a machine or deployment environment; you can stop tracking the file while keeping it on disk:

~~~bash
# Remove file from index while keeping local file on disk
git rm --cached -- config/prod.env
~~~

Add an appropriate rule to <code>.gitignore</code>:

~~~gitignore
config/prod.env
~~~

If the team needs a configuration example, create a template file containing only variable names and dummy values:

~~~text
DB_HOST=localhost
DB_USER=app_user
DB_PASSWORD=replace-me-locally
API_TOKEN=replace-me-locally
~~~

Save that template under a name like <code>config/prod.env.example</code>, then instruct each environment to create the real file from a secret manager or environment variables.

If the real file remains on the machine, delete the revoked value and load the new credential from a protected source. If that local file is no longer needed, delete it following your machine's data handling policy. Ignore rules only prevent Git from tracking untracked files; they do not delete local copies or copies outside the repository.

### If the file must remain versioned

Remove the secret value from the file content, replacing it with an environment variable or secret manager reference:

~~~yaml
database:
  password: ${DB_PASSWORD}
service:
  apiToken: ${SERVICE_API_TOKEN}
~~~

Ensure the application has a mechanism to load values at runtime. Never commit real values into template files, tests, scripts, or documentation.

### Why editing only the current file is not enough

The steps above protect future snapshots. If the secret ever appeared in an earlier commit, it can still be read from history. In that case, evaluate rewriting history as covered in the following sections.

## 7. When a commit containing a secret has not been pushed yet

If the secret only exists in unshared local commits, cleanup scope may be simpler, but you must still check all related local commits and any locations where the repository was backed up.

If the secret is only in the latest commit, you can fix the snapshot and replace that commit:

~~~bash
# Remove local config file from index while keeping file on machine
git rm --cached -- config/prod.env

# Update .gitignore and safe template file
git add .gitignore config/prod.env.example

# Replace latest commit with edited content
git commit --amend
~~~

Before amending, confirm the index contains only the content you want in the commit. If the file needs to stay in the repository, edit the value inside it and stage the safe version rather than just removing the file from the index.

If the secret appears across multiple local commits, you must fix or remove every affected commit, such as with an interactive rebase when the scope is small and clearly defined. Do not fix only the final commit if older commits still contain the value.

After cleaning up, scan local refs with a secret scanner and verify that the old commits are no longer reachable from any branch or tag. If backups or other clones hold the old history, they can still retain the secret even though the current repository is clean.

Note: amending or rebasing changes branch history, yet old commits may remain in the local reflog and object database until cleaned up per policy. If incident requirements call for removing unreachable objects from the machine as well, inventory refs, keep a secure backup per policy, and only then consider expiring the reflog and pruning objects:

~~~bash
git reflog expire --expire=now --all
git gc --prune=now
~~~

This operation affects your ability to recover prior states and should not be run casually. It only affects the local repository being operated on; it does not clean remotes, other clones, backups, or caches.

## 8. When the secret has already been pushed to a remote

If the commit has been pushed, treat the secret as shared with every person or system that had read access to the repository during that window. Rewriting history on the remote is only part of the process.

The workflow typically includes:

1. Complete credential revocation and rotation.
2. Notify repository maintainers and agree on a push/merge freeze window.
3. Create a separate working copy to rewrite history; retain a secure backup per policy.
4. Remove the secret from all affected commits and refs.
5. Verify results with a secret scanner and history audit.
6. Update the remote via controlled force pushes for the cleaned refs.
7. Instruct team members to create a fresh clone or synchronize as directed; do not merge old branches back in.
8. Address caches, forks, pull requests, artifacts, and copies retained by the platform.

Do not force push before identifying which branches, tags, and refs will be affected. Rewriting history can impact pull requests, releases, pipelines, and teammates' unpushed work.

## 9. Using git-filter-repo to remove secrets from history

For rewriting history, <code>git-filter-repo</code> is generally recommended over <code>git filter-branch</code> because its design and performance are better suited for history filtering tasks. Install and verify the version according to the tool's official documentation and developer machine policies.

Before running it, distinguish two cases:

- **Remove an entire file from history:** use a path filter if the file never needs to exist in any commit.
- **Keep the file but replace secret values:** use replace-text to substitute sensitive strings across historical blobs.

Perform this on a clean, separate clone. Never run a rewrite directly inside the team's sole working repository.

### Preparing a mirror clone

~~~bash
git clone --mirror <repository-url> repo-clean.git
cd repo-clean.git
~~~

A mirror clone fetches all refs published by the remote and creates a bare repository suitable for whole-history operations. Inspect remotes and refs before filtering:

~~~bash
git show-ref
git remote -v
~~~

Keep the original clone and backup per security procedures until the team confirms cleanup is complete.

### Removing an entire file containing a secret

If the file was purely local configuration committed by mistake and does not need to remain in history:

~~~bash
git filter-repo --sensitive-data-removal --path config/prod.env --invert-paths
~~~

This command removes the path <code>config/prod.env</code> from the filtered commits. If the file was ever stored under multiple paths or names, include all corresponding paths. Check history so renamed copies are not missed.

Depending on your <code>git-filter-repo</code> version, the <code>--sensitive-data-removal</code> flag may not be supported yet. Check the help output for your installed version and follow its documentation; do not blindly ignore warnings or run commands you do not understand.

### Replacing secret values while keeping the file

If the file must remain in history while the value must be removed, create a temporary replacement file outside the repository. Syntax illustration:

~~~text
literal:EXAMPLE-LEAKED-VALUE==>***REMOVED***
~~~

In practice, replace <code>EXAMPLE-LEAKED-VALUE</code> with the string to remove inside a protected local environment. Do not commit the replacement file, do not attach it to issues or logs, and restrict read permissions on the file. Once done, dispose of the temporary file according to your organization's data protection policy.

Run:

~~~bash
git filter-repo --sensitive-data-removal --replace-text ../replacements.txt
~~~

<code>--replace-text</code> replaces matching strings inside blob contents according to the file's rules. If the secret appears in multiple encodings, escapes, or variants, identify and handle every relevant form. Never assume a single replacement string will remove every representation of a credential.

If your tool version does not support <code>--sensitive-data-removal</code>, consult help for compatible syntax. Do not use <code>git filter-branch</code> as a quick substitute without a testing plan and clear understanding of which refs it modifies.

### Verifying after filtering

After rewriting, verify:

- Required branches and tags still exist.
- The secret file or value has vanished from all reachable commits.
- Current configuration files use environment variables or a secret manager.
- New commit history no longer contains variants of the credential.
- Applications and pipelines still work using the new credential.

You can check paths:

~~~bash
git log --all --oneline -- config/prod.env
git rev-list --objects --all
git show-ref
~~~

For string replacements, run an approved secret scanner across all reachable history after the rewrite. Do not check only the current working tree.

## 10. Updating the remote after rewriting history

<code>git-filter-repo</code> may remove the <code>origin</code> remote as a safety measure to prevent accidental pushes. Check:

~~~bash
git remote -v
~~~

If the remote was removed and the team has confirmed the rewritten version is ready to publish, re-add the remote:

~~~bash
git remote add origin <repository-url>
~~~

Before pushing, confirm the correct URL, access permissions, and cleaned branches and tags. With coordination from repository maintainers, update the corresponding branches and tags:

~~~bash
git push --force --all origin
git push --force --tags origin
~~~

These two commands update branches and tags. They do not cover all custom refs or internal refs created by a hosting platform. If the repository uses notes, release refs, pull request refs, or custom refs, inventory and handle them per provider documentation.

Never run <code>git push --mirror</code> mechanically. A mirror push can delete refs on the remote that do not exist locally; use it only after a complete inventory and exact understanding of its impact. Protected branches may require separate administrative workflows to permit history updates.

## 11. Coordinating with people holding old clones

After rewriting the remote, teammates' clones may still contain old commits and old secrets. If they push or merge old branches back, history containing the secret can be reintroduced to the remote.

For sensitive incidents, the most controllable approach is usually:

1. Announce when the new history has been published.
2. Instruct team members to stop pushing from old clones.
3. Create a fresh clone from the cleaned remote.
4. Transfer unshared local changes to the fresh clone via inspected patches or cherry-picks.
5. Never merge old branches containing pre-rewrite commits.
6. Delete or quarantine old clones according to retention and incident response policies.

If creating a fresh clone is not possible, project maintainers must provide exact synchronization instructions per branch and verify no local refs retain old history. Do not tell everyone to run a regular <code>git pull</code> after a rewrite because that operation can splice old history back in.

## 12. Copies outside the Git remote must also be handled

Force pushing only updates refs on the remote you manage. The secret may still remain in:

- Forks owned by team members or other organizations.
- Pull request diffs, review comments, or platform-generated refs.
- Commit caches, file view pages, or provider mirrors.
- CI logs, build artifacts, packages, container images, and release bundles.
- Backups, disk snapshots, and clones on developer machines.
- Source analysis tools, secret scanners, or observability systems that stored the content.

Contact administrators or the platform provider to purge caches, pull request refs, or copies the team cannot manage directly. Some providers have dedicated support processes for removing sensitive data from history; follow those processes after revoking the credential.

Backups may have to be retained due to legal requirements or retention policies. In that case, restrict access permissions, record the retention period, and ensure credentials inside backups have been invalidated. Never arbitrarily delete backups governed by mandatory retention policies.

## 13. Verifying the incident is resolved

An incident should only be closed when the team has evidence for both parts: the old credential is no longer usable and the sensitive data has been remediated within controlled scope.

### Credential checks

- Old credential status is revoked/disabled or expired.
- New credential has been deployed via secret manager or protected mechanism.
- Dependent services operate properly using the new credential.
- Audit logs have been reviewed across the potential exposure window.
- Permissions on the new credential are scoped strictly to what is needed.

### Git checks

- Remote branches and tags point to the cleaned history.
- Secret scanner detects no old values in reachable history.
- Current configuration files contain no real credentials.
- Old clones and unpushed branches have been addressed.
- No old commits have been merged or pushed back.
- Related pull requests, caches, artifacts, and forks have been reviewed.

Document commit hashes before and after the rewrite, updated refs, revocation timestamp, new credential deployment timestamp, and checked systems. The report does not need to contain the secret value.

## 14. Preventing recurrence

After resolving the incident, improve workflows so secrets are less likely to enter Git:

- Store credentials in a secret manager or the platform's secure configuration system.
- Use environment variables or workload identities when applications need credentials at runtime.
- Commit template files like <code>.env.example</code> containing only placeholders, never real values.
- Add <code>.gitignore</code> rules for local configuration files and secret files.
- Enable secret scanning on the repository and in pipelines.
- Use pre-commit hooks or CI checks to detect secrets before merging.
- Restrict repository read access, tokens, and service accounts using least privilege.
- Regularly rotate credentials and audit access logs.
- Train team members how to report incidents without copying secrets into public channels.

Example structure:

~~~text
project/
|-- .env.example       # safe placeholder, committed
|-- .env               # local values, ignored
|-- config/
|   |-- app.example.yml
|   |-- app.local.yml   # ignored if it contains credentials
|-- src/
~~~

Illustrative ignore rules:

~~~gitignore
.env
.env.*
!.env.example
config/*.local.yml
~~~

Adjust patterns to match your actual structure. Ensure template files allowed to be committed contain no real secrets, and untrack any previously tracked local files from the index when needed.

## 15. Common mistakes when handling exposed secrets

| Wrong approach | Why it is insufficient | Right approach |
|---|---|---|
| Only deleting the secret line in a new commit | Older commits still contain the value | Revoke/rotate the credential and clean history when needed |
| Only adding the file to <code>.gitignore</code> | Ignoring does not affect history or tracked files | Untrack from index and clean older commits |
| Only running <code>git gc</code> | Objects reachable from old commits are retained | Rewrite refs holding old commits, then handle copies per policy |
| Rewriting history before revoking | Old credential may still work during remediation | Revoke or disable the credential first |
| Force pushing only one branch | Tags, other branches, or other refs may still retain the secret | Inventory and clean all affected refs |
| Telling everyone to pull the new branch | Old clones can splice history containing the secret back in | Create a fresh clone or follow verified synchronization instructions |
| Cleaning only the primary remote | Forks, caches, artifacts, and backups may still hold the data | Inspect off-remote copies and coordinate with the provider |
| Passing the secret in shell commands or issues to search | Shell history, logs, and ticketing systems can create extra copies | Use a secret scanner and protected temporary files |
| Purging history without rotating the credential | Anyone who already grabbed the secret can still use it | Revoke/rotate and review audit logs |

## 16. Sample response workflow

When a token has been committed and pushed to a remote, you can follow this sequence:

~~~text
Secret detected in commit
        |
        v
Report incident and identify credential type
        |
        v
Revoke/disable old credential
        |
        v
Issue new credential and update workloads
        |
        v
Audit logs and assess exposure scope
        |
        v
Freeze pushes/merges on affected refs
        |
        v
Rewrite history in a clean clone
        |
        v
Secret scan and verify cleaned refs
        |
        v
Controlled force push; address clones/forks/caches/artifacts
        |
        v
Confirm old credential is invalid and no path reintroduces old history
~~~

This sequence may need adjustment based on the provider and severity. For credentials under active exploitation, disabling them and blocking unauthorized access may need to happen immediately in parallel with restoring service using new credentials.

## 17. Self-check exercises

Practice in a test repository using a dummy string with no real access value:

1. Create a configuration file containing a fake placeholder string and commit it.
2. Add another commit modifying source code, then delete the configuration file in the following commit.
3. Use <code>git log --all --oneline -- &lt;path&gt;</code> to observe that the file still appears in earlier history.
4. Practice untracking the file from the index, adding an ignore rule, and creating a safe template file.
5. Create a separate mirror clone and use <code>git-filter-repo</code> to strip the fake file from history.
6. Inspect branches, tags, and reachable objects after the rewrite.
7. Explain why <code>git gc</code> and a deletion commit cannot replace a history rewrite.
8. Draft a remediation plan for a pushed dummy credential: who revokes it, who issues the replacement, which refs must be rewritten, and which clones need refreshing.
9. Write an incident report containing no secret value—recording only credential type, scope, commit hash, and remediation status.

When handling exposed secrets, prioritize rendering the old credential unusable first, then clean history and every copy within your control. Verification must cover the systems using the credential, remote repositories, teammates' clones, and any artifacts or caches that might retain old content.

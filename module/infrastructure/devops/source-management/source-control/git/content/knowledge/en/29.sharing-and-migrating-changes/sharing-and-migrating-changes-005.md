# Offline Exchange with git bundle create, verify, and clone

Git collaboration normally goes through remotes like GitHub, GitLab, or an internal Git server. However, there are times when two machines cannot connect directly: network-isolated environments, development machines without Internet access, transferring source code via storage media, or sending a set of commits to a team at another location. In those situations, **git bundle** lets you package the required objects and refs into a single file for offline transfer.

A bundle can be used as a source to clone a new repository or fetch commits into an existing repository. The recipient can inspect the bundle, list the refs the bundle provides, verify required base commits, and then import the changes into their own history.

A bundle is not an encrypted copy. It can contain source code, old history, branches, and tags; therefore, you must verify data scope, protect the file during storage/transfer, and verify its origin before using it.

## 1. What problem does git bundle solve?

git bundle creates a Git-formatted file containing the required objects along with ref information and, for an incremental bundle, the prerequisites the recipient must already have.

Bundles are useful when:

- Transferring a repository between two environments without a direct network connection.
- Sending a branch or group of commits for offline review.
- Moving Git history over USB or controlled intermediate storage.
- Providing a snapshot with history for an isolated build environment.
- Creating an incremental package to transfer only new commits since a known reference point.

A bundle retains the Git metadata needed to continue working with commits and refs. Recipients can clone from the bundle or fetch the advertised refs into an existing repository.

### 1.1. How does a bundle differ from a source archive?

| Criterion | Git bundle | Source archive (tar/zip) |
|---|---|---|
| Contents | Selected Git objects and refs | File snapshot of a tree |
| Commit history | Yes, within bundle scope | No |
| Can clone/fetch | Yes | No |
| Can contain multiple branches/tags | Yes, if those refs are selected | No |
| Used to continue Git development | Yes | Must initialize a new repository if tracking with Git |
| Best suited for | Offline exchange of history and commits | Distributing source code at a specific version |

If the recipient only needs to run the application from one version, a source archive may be more suitable. If the recipient needs to inspect history, create branches, merge, or continue committing, a bundle is more suitable.

### 1.2. Bundles do not replace backups or long-term remotes

A bundle is a transfer file. It does not automatically sync two-way after creation. If the sender continues committing after creating a bundle, the old bundle file does not update automatically.

When multiple rounds of exchange are needed, generate a new bundle or an incremental bundle based on a base commit agreed upon by both sides.

## 2. Inspecting the repository before creating a bundle

Before packaging, verify the repository, working tree status, and refs to be shared.

~~~sh
git rev-parse --show-toplevel
git status -sb
git branch --all
git tag --list
git remote -v
~~~

Bundles are created from commits and refs stored in Git. Uncommitted changes or untracked files in the working tree are not automatically included in the bundle. If you need to share those changes, commit them to a dedicated branch or use an appropriate patch mechanism.

### 2.1. Selecting the right refs

You should not always send the entire repository. Determine whether the recipient needs:

- A single branch such as main or feature/report.
- A release tag such as v2.1.0.
- Several related branches and tags.
- All existing refs for repository backup or migration.

Inspect shareable refs:

~~~sh
git for-each-ref --format="%(objectname) %(refname)" refs/heads/ refs/tags/
~~~

Note that the --all option may include more refs than the recipient needs, such as local branches, tags, and remote-tracking refs. Before using it, inspect the ref list and consider what information they expose.

### 2.2. Checking for sensitive data

A bundle can contain old history, including files that have already been deleted from the current branch. Before creating one:

- Scan for secrets across relevant refs and history.
- Check commit messages, author metadata, and branch/tag names.
- Do not include customer data or local configuration files in commits.
- Confirm the recipient is authorized to view the entire packaged history.
- Use storage and transfer channels approved by your organization.

If a secret was ever committed, deleting the file in a newer commit does not remove the secret from the bundle if the history includes that older commit.

## 3. Creating a full bundle with git bundle create

### 3.1. Bundle containing one branch

Suppose you need to send the main branch:

~~~sh
git bundle create ../project-main.bundle refs/heads/main
~~~

The command creates project-main.bundle in the parent directory of the current repository. The bundle contains the objects needed for main's history and advertises that ref to the recipient.

If you want the recipient to work with another branch, replace the ref name with the ref to share, for example:

~~~sh
git bundle create ../feature-report.bundle refs/heads/feature/report
~~~

Using full ref names makes it explicit which branch is packaged.

### 3.2. Bundle containing multiple selected branches and tags

You can specify multiple refs:

~~~sh
git bundle create ../release-transfer.bundle refs/heads/main refs/heads/release/2.x refs/tags/v2.0.0
~~~

The recipient will be able to see the refs advertised by the bundle. This works well when transferring a development branch along with related release milestones.

### 3.3. Bundle all refs

To create a bundle from all enumerable refs in the repository:

~~~sh
git bundle create ../project-all.bundle --all
~~~

This is a convenient option for backups or repository migrations. However, the bundle may carry more branches, tags, and remote-tracking refs than needed. Inspect the ref list before sharing.

Do not use --all just to "make sure nothing is missing" if the recipient only needs a single branch. The larger the scope, the heavier the file and the higher the risk of exposing unnecessary history.

## 4. Full bundles vs. incremental bundles

A full bundle can provide all history required for the selected refs. An incremental bundle contains only new history and records prerequisites that the receiving repository must already possess.

### 4.1. Creating a full bundle

Example:

~~~sh
git bundle create ../main-full.bundle refs/heads/main
~~~

This bundle contains the history needed for the recipient to recreate the main branch without a preexisting base repository, provided the necessary refs and objects are included.

### 4.2. Creating an incremental bundle from a base commit

Suppose both sides already have base commit A. The sender wants to transfer new commits on branch feature/report since A:

~~~sh
git bundle create ../feature-incremental.bundle refs/heads/feature/report ^<base-commit>
~~~

Where <base-commit> is a commit already present in the recipient's repository. The ^<base-commit> part excludes the base commit and its ancestors from the object set to transfer; the bundle records the base commit as a prerequisite.

You can use an equivalent revision range expression:

~~~sh
git bundle create ../feature-incremental.bundle <base-commit>..refs/heads/feature/report
~~~

When creating an incremental bundle, agree on the exact base commit with the recipient. If the recipient lacks the prerequisite, they cannot fully import the changes from that bundle alone.

### 4.3. When should you use an incremental bundle?

Incremental bundles are suitable when:

- Both sides previously exchanged a full bundle.
- The recipient has a clone or repository containing the base commit.
- New history represents only a small portion compared to the full repository.
- Bandwidth is limited and transfer size must be minimized.

If you are unsure which base commits the recipient has, send a full bundle or exchange a base bundle first. Do not assume two repositories share the same history just because they have branches with the same name.

## 5. Checking a bundle with git bundle verify

Before using a bundle, the recipient should verify its structure and prerequisites.

~~~sh
git bundle verify ../project-main.bundle
~~~

git bundle verify checks the bundle and reports the refs it provides, while verifying that its prerequisites exist in the current repository. For a full bundle without prerequisites, it can be verified inside an empty repository.

### 5.1. Verifying an incremental bundle

For an incremental bundle, run verify inside a repository that already has the base commit:

~~~sh
git bundle verify ../feature-incremental.bundle
~~~

If a prerequisite is missing, Git reports that the bundle cannot be applied in the current repository. In that case:

1. Identify the listed prerequisite commits.
2. Check whether the repository has the right base history.
3. Request a full bundle or the required base bundle if the commit is missing.
4. Re-run verify before fetching.

Do not ignore missing prerequisite messages. Missing a base commit can cause history import to fail or prevent the recipient from accurately recreating the branch.

### 5.2. Verify does not prove who created the bundle

git bundle verify checks the bundle structure and prerequisite satisfaction. It does not authenticate the sender's identity and does not prove the contents were issued by an authorized party.

To verify origin, use digital signatures or checksums transmitted over a trusted channel:

- Compare the checksum against the value received through a verified channel.
- Verify the digital signature if your organization signs bundles or manifests.
- Cross-check commit SHAs with confirmed release information.

A checksum detects file tampering but does not prove who created the file on its own. If an attacker can replace both the bundle and the checksum on the same channel, that comparison is insufficient to authenticate the source.

## 6. Viewing advertised refs with git bundle list-heads

Before cloning or fetching, you can list the refs inside the bundle:

~~~sh
git bundle list-heads ../project-all.bundle
~~~

The output includes object IDs and ref names. Example:

~~~text
<commit-id> refs/heads/main
<commit-id> refs/heads/feature/report
<tag-object-id> refs/tags/v2.0.0
~~~

The list confirms whether the bundle contains the expected branches or tags. If the bundle does not advertise the required ref, re-check the create command on the sender's side.

For annotated tags, the listed object ID may be the tag object rather than the commit directly. This is normal behavior.

## 7. Cloning a new repository from a bundle

If the recipient does not yet have a repository, they can clone directly from the bundle:

~~~sh
git clone --branch main ../project-main.bundle project-offline
~~~

The command creates a new repository in the project-offline directory and checks out the main branch provided by the bundle. If the bundle does not have a branch named main, choose another branch from the list-heads output.

After cloning:

~~~sh
cd project-offline
git status -sb
git branch -a
git log --oneline --decorate -10
git remote -v
~~~

Check the current branch, history, and configured remote. When cloning from a bundle path, the origin remote may point to the bundle file or original source path; that does not establish a network server. The user must update the remote per offline procedures or configure a new remote once connected.

### 7.1. If the bundle contains multiple branches

Select the default branch using the --branch option during clone:

~~~sh
git clone --branch release/2.x ../release-transfer.bundle project-release
~~~

If you do not know the branch names yet, run git bundle list-heads first. Avoid assuming the bundle's default branch is always main or master.

### 7.2. Cloning a full bundle and continuing work

After cloning, the recipient can create a new branch:

~~~sh
git switch -c feature/offline-adjustment
~~~

Edit files, stage, and commit just like a normal repository:

~~~sh
git add src/
git commit -m "Apply offline adjustment"
~~~

New commits exist only in the local clone until transferred back via another bundle or an accessible remote.

## 8. Fetching a bundle into an existing repository

If the recipient already has a repository and only wants to import one branch from the bundle, use git fetch with the bundle file path.

Example:

~~~sh
git fetch ../feature-report.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
~~~

The command fetches refs/heads/feature/report from the bundle and updates the local ref refs/remotes/offline/feature/report. No full re-clone is required.

Verify:

~~~sh
git show-ref refs/remotes/offline/feature/report
git log --oneline --decorate -10 refs/remotes/offline/feature/report
~~~

Create a local branch for review:

~~~sh
git switch -c review/feature-report refs/remotes/offline/feature/report
~~~

After reviewing, you can merge or cherry-pick according to the project workflow:

~~~sh
git switch main
git merge --no-ff review/feature-report
~~~

Do not merge simply because the fetch succeeded. Inspect the diff, run tests, and confirm the commits came from the right sender.

## 9. Fully offline two-way exchange

Bundles can be used to send changes out and receive changes back.

### 9.1. Sender creates a bundle for the working branch

~~~sh
git bundle create ../feature-payment.bundle refs/heads/feature/payment
git bundle verify ../feature-payment.bundle
git bundle list-heads ../feature-payment.bundle
~~~

Transfer the bundle file and checksum/manifest via approved storage media.

### 9.2. Recipient fetches and develops

~~~sh
git bundle verify /media/transfer/feature-payment.bundle
git fetch /media/transfer/feature-payment.bundle refs/heads/feature/payment:refs/remotes/offline/feature/payment
git switch -c feature/payment refs/remotes/offline/feature/payment
~~~

The recipient can edit, commit, and create a return bundle:

~~~sh
git bundle create ../payment-feedback.bundle refs/heads/feature/payment
~~~

### 9.3. Sender imports the return bundle

~~~sh
git bundle verify ../payment-feedback.bundle
git fetch ../payment-feedback.bundle refs/heads/feature/payment:refs/remotes/offline/feature/payment-feedback
git log --oneline --graph --decorate main..refs/remotes/offline/feature/payment-feedback
~~~

After reviewing, the sender can merge or cherry-pick the appropriate commits. Both sides should agree on offline ref naming conventions to avoid overwriting existing local branches or remote-tracking branches.

## 10. Incremental bundle workflow across multiple transfers

When both sides already share a base commit, transfer size can be reduced with incremental bundles.

Suppose:

- The first bundle gave the recipient commit A.
- The sender continues creating commits B and C on branch feature/report.
- The recipient does not yet have B and C.

The sender creates a bundle from A to the current tip:

~~~sh
git bundle create ../report-update.bundle refs/heads/feature/report ^<A>
~~~

The recipient verifies in a repository that already has A:

~~~sh
git bundle verify ../report-update.bundle
~~~

Then fetches the branch:

~~~sh
git fetch ../report-update.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
~~~

For the next transfer, both sides must agree on the new base commit that was successfully received. Do not reuse an old base out of habit if history has changed or the branch was force-pushed.

If the branch was rebased or had history rewritten, an incremental bundle based on an old commit may no longer fit. In that case, re-establish the common point or create a full bundle.

## 11. Handling errors when creating or receiving a bundle

**Cannot create bundle due to missing objects.** Check whether the repository has all required objects. If the clone is shallow or partial, you may need to fetch additional data from the remote before creating the bundle.

**Bundle verify reports missing prerequisite.** This is an incremental bundle and the receiving repository lacks the base commit. Transfer the base bundle or create a full bundle.

**Desired branch missing from list-heads.** The sender may have omitted that ref from the create command. Recreate the bundle with the full ref name.

**Clone reports selected branch does not exist.** Check the ref list and use the exact name in the --branch option.

**Fetch does not update ref.** Check the source ref in the bundle, destination ref, write permissions, and fast-forward rules for the target ref. If the target ref already has divergent history, do not force-overwrite before reviewing.

**Bundle is too large.** Package only necessary branches/tags, and consider incremental bundles if the recipient has a base commit. Avoid --all when unnecessary.

**Bundle corrupted during transfer.** Compare checksums, re-copy the file from a trusted source, and run verify before importing.

**Bundle is valid but untrusted.** Verify does not prove the creator's identity. Cross-check signatures, checksums over an independent channel, and commit SHAs with the sender.

## 12. Protecting bundles during storage and transfer

A bundle is a file that can contain source code and history. It does not automatically encrypt or restrict readers.

Before transferring:

- Determine which refs and history are included.
- Scan for secrets and personal data in relevant commits.
- Use approved media or storage locations.
- Encrypt when policy requires it.
- Restrict who can access the file.
- Generate a checksum and, if needed, sign a manifest.
- Record the creator, recipient, timestamp, and purpose.

After receiving:

- Verify the checksum or signature via a trusted channel.
- Run git bundle verify.
- Inspect git bundle list-heads.
- Clone/fetch into a sandbox repository if the origin is uncertain.
- Review history and diff before merging.
- Delete intermediate files according to retention policy.

### 12.1. Checksum examples

On Linux:

~~~sh
sha256sum project-main.bundle
~~~

On macOS:

~~~sh
shasum -a 256 project-main.bundle
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\project-main.bundle -Algorithm SHA256
~~~

Send the checksum through a channel independent of where the bundle is transferred if the goal is to detect file substitution. If both the file and checksum come from the same unverified source, comparing them does not prove origin.

## 13. Bundles and repository migration scenarios

### 13.1. Moving a repository between two offline machines

1. The sender creates a bundle from the required refs.
2. The sender checks list-heads and verify.
3. Generate a checksum or signature per policy.
4. Transfer the file via approved media.
5. The recipient verifies checksum/signature and the bundle.
6. Clone or fetch into the repository.
7. Check branches, tags, logs, and run tests.

### 13.2. Migrating a repository to a new server

Bundles can transfer history between environments, but you must clearly define which refs must be preserved. For a full migration, check:

- Required branches and tags.
- Whether remote-tracking refs need to be kept.
- Notes or project-specific special refs.
- Git LFS or content outside the object database.
- Submodules and child repositories.
- Hooks, config, permissions, and CI/CD workflows.

A bundle contains only selected Git objects and refs. It does not automatically transfer Git config, server hooks, credentials, uncommitted working trees, external Git LFS objects, or submodule contents. Those components require a separate migration plan.

### 13.3. Bundles do not automatically sync multiple remotes

When a recipient clones from a bundle, the configured remote may point to the bundle path. That is not an always-up-to-date server remote. If network connectivity becomes available later, set the proper remote URL:

~~~sh
git remote set-url origin https://example.com/team/project.git
git remote -v
git fetch origin
~~~

Before pushing, compare history and check whether branches have diverged. Do not force-push just to make two repositories "look the same".

## 14. Complete example: transferring a branch via storage device

Suppose machine A holds the project repository, and machine B is in an offline environment needing to receive branch feature/report.

**On machine A — create the bundle**

~~~sh
git status -sb
git log --oneline -10 refs/heads/feature/report
git bundle create ../feature-report.bundle refs/heads/feature/report
git bundle list-heads ../feature-report.bundle
git bundle verify ../feature-report.bundle
~~~

Generate checksum:

~~~sh
sha256sum ../feature-report.bundle
~~~

Transfer the bundle and checksum via approved media.

**On machine B — verify and import**

~~~sh
git bundle verify /media/transfer/feature-report.bundle
git bundle list-heads /media/transfer/feature-report.bundle
git fetch /media/transfer/feature-report.bundle refs/heads/feature/report:refs/remotes/offline/feature/report
git switch -c review/feature-report refs/remotes/offline/feature/report
~~~

Review:

~~~sh
git log --oneline --graph --decorate -20
git diff main...review/feature-report
~~~

Run tests, then merge if approved:

~~~sh
git switch main
git merge --no-ff review/feature-report
~~~

If machine B needs to send results back to machine A, create a new bundle from the updated branch and transfer it following the same workflow.

## 15. Checklist for using git bundle

**Before creating**

- [ ] Identified branches/tags/refs to transfer.
- [ ] Checked working tree and commits to share.
- [ ] Scanned for secrets, private data, and metadata.
- [ ] Decided between full or incremental bundle.
- [ ] If incremental, agreed on prerequisite commit with the recipient.

**After creating**

- [ ] Bundle file created successfully.
- [ ] Ran git bundle list-heads.
- [ ] Ran git bundle verify in an appropriate repository.
- [ ] Generated checksum or signature if policy requires.
- [ ] Stored file in a location with appropriate access permissions.

**When receiving**

- [ ] Verified origin and integrity through a trusted channel.
- [ ] Ran verify and checked prerequisites.
- [ ] Confirmed required refs are present in the bundle.
- [ ] Cloned or fetched into the right repository.
- [ ] Reviewed log/diff and ran tests before merging.

**After exchange**

- [ ] Updated base commit for the next bundle transfer.
- [ ] Recorded necessary handoff metadata.
- [ ] Deleted intermediate files per retention policy.
- [ ] Handled Git LFS, submodules, hooks, and config separately if migration requires.

## 16. Conclusion

git bundle enables exchanging Git history when a direct remote connection is unavailable. git bundle create packages selected objects and refs; git bundle verify checks the bundle and its prerequisites; git bundle list-heads shows the advertised refs; git clone or git fetch lets recipients create a new repository or import changes into an existing repository.

Select minimal refs, distinguish full bundles from incremental bundles, and ensure the recipient has prerequisites before importing. Verify does not authenticate the sender, checksums do not encrypt data, and bundles can contain full sensitive history. Combine origin verification, file protection, history review, and copy management for safe and reproducible offline exchanges.

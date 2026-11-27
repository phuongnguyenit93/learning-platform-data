# Exchanging Patches, Creating Bundles, and Verifying Offline Recovery

This lab simulates a scenario where two development teams must exchange Git changes without a shared remote or direct network connectivity. The sending team needs to deliver a feature branch to the receiving team. The receiving team must inspect the patch, import the commits into their repository, and also have a bundle capable of restoring the repository in an offline environment.

You will practice two complementary exchange methods:

- **Patch:** transfers changes as a diff or series of email-style patches. Patches work well for code review, sending individual commits, and applying onto a repository with a compatible base history.
- **Git bundle:** packages objects and refs into a single file. Bundles allow cloning or fetching Git history without a live remote connection.

At the end of the lab, you will restore a test repository from the bundle into a new directory and verify branches, commits, tags, and file contents. Restoring into a separate directory validates recoverability without overwriting your active repository.

## 1. Practice Objectives

Upon completion, you will be able to:

1. Prepare a clean feature branch for handover.
2. Generate both diff patches and format-patches from a base commit.
3. Inspect a patch before applying it.
4. Apply patches with git apply or git am matching the patch type.
5. Create both full bundles and incremental bundles.
6. Verify prerequisites and refs advertised by a bundle.
7. Clone or fetch from a bundle in an offline environment.
8. Restore a repository into a new directory and cross-check the results.
9. Verify the integrity and provenance of handover files.

## 2. Scenario and Lab Diagram

Suppose there are two machines:

- **Machine A — Sender:** holds the source repository and the developed feature/offline-report branch.
- **Machine B — Receiver:** holds a repository cloned from the base commit before receiving the changes.

The two machines have no direct network connection. Patch files, bundles, and a manifest are transferred via an intermediate directory or organization-approved storage media.

~~~text
Machine A: Sender
  Source repository
      |
      +--> Create diff patch
      |
      +--> Create format-patch (mbox)
      |
      +--> Create Git bundle
      |
      v
  Handover package + checksums/manifest
      |
      |  USB / transfer folder / offline store
      v
Machine B: Receiver
  Repository with base commit
      |
      +--> Inspect patch --> git apply or git am
      |
      +--> Verify bundle --> fetch or clone
      |
      v
  Review, compare history, and run tests
      |
      v
  Clone bundle into restore-test directory
      |
      v
  Verify recoverability
~~~

Patches and bundles serve different purposes. A patch represents changes to review or apply; a bundle carries objects and refs to keep working with history. A thorough handover workflow can provide both so the recipient can inspect changes easily and still have a recovery artifact.

## 3. Preparing the Repository and Base Commit

Pick a sandbox repository containing no credentials or customer data. If using a work repository, make sure you are authorized to create branches and handover files.

On both machines, you need Git installed and a dedicated working directory. Check your Git version:

~~~sh
git --version
~~~

### 3.1. On Machine A — Check Initial State

Enter the source repository:

~~~sh
git rev-parse --show-toplevel
git status -sb
git branch --show-current
git log --oneline --decorate -5
~~~

Before creating patches or bundles:

- Working tree has no changes outside the lab scope.
- Base branch is identified, e.g., main.
- Base commit present on Machine B is identified.
- No secrets or local config files exist in the commits to be shared.

Record the base commit:

~~~sh
git rev-parse main
~~~

Save this commit hash in your lab handover notes. It serves as the reference point for comparing history and building incremental bundles.

### 3.2. On Machine B — Prepare the Receiving Repository

If Machine B can prepare before going offline, clone the repository and check out the base branch:

~~~sh
git clone <repository-url> receiver-project
git clone <repository-url> receiver-am
git clone <repository-url> receiver-bundle
git -C receiver-project switch main
git -C receiver-project rev-parse HEAD
git -C receiver-project status -sb
~~~

The three clones are used independently to test git apply, git am, and fetching from a bundle. The commit hash of main in each clone must match the base commit recorded on Machine A. If the two sides do not share the same base commit, do not assume patches or incremental bundles will apply cleanly. Resynchronize first or use a full bundle.

If there is no remote in your lab environment, you can seed the receiving repositories from a local clone or pre-built base bundle. The goal is for Machine B to share the exact starting commit used by Machine A.

## 4. On Machine A — Create a Branch and Commit Changes

Create the working branch:

~~~sh
git switch -c feature/offline-report
~~~

Make changes in one or more project files—for example, updating report generation and adding tests. Then inspect:

~~~sh
git status --short
git diff
~~~

Stage only the files meant for handover:

~~~sh
git add src/report/
git add tests/report/
git diff --cached --check
git diff --cached
~~~

If partial staging is needed:

~~~sh
git add -p src/report/report-service.java
~~~

Create a commit with a clear descriptive message:

~~~sh
git commit -m "feat(report): add offline report export"
~~~

For larger changes, split them into multiple small, purpose-focused commits. This helps the recipient review step by step and lets format-patch generate an easy-to-follow commit series.

### 4.1. Inspect History After Committing

~~~sh
git status -sb
git log --oneline --decorate main..feature/offline-report
git diff --stat main...feature/offline-report
git diff --check main...feature/offline-report
~~~

Expected outcome:

- Current branch is feature/offline-report.
- No unintended uncommitted files remain.
- Log lists the new commits relative to main.
- Diff covers only the feature work intended for handover.
- No common whitespace errors appear.

If status still shows changes, decide explicitly whether to commit them or keep them on Machine A. Never let uncommitted edits get accidentally omitted from patches and bundles.

## 5. Creating a Diff Patch to Transfer Changes

A diff patch records the difference between two trees. It does not preserve full commit metadata like format-patch, and applying it with git apply does not automatically create a commit.

Generate a patch from main to the feature branch:

~~~sh
git diff --binary --full-index main..feature/offline-report > ../offline-report.diff
~~~

- --binary represents binary changes in Git's patch format.
- --full-index writes full object IDs in the diff index headers.
- main..feature/offline-report compares the tree at main with the tree at the feature branch tip.

This patch describes the net final diff between the two points. To preserve individual commit boundaries, use format-patch in the next section.

### 5.1. Inspecting the Patch Before Sending

View patch statistics:

~~~sh
git apply --stat ../offline-report.diff
~~~

Applicability must be verified on a clean working tree sitting at the base commit main. Section 5.2 performs that check on Machine B; do not test it on the feature branch that already contains this patch. The check command only verifies whether the patch applies cleanly to the current state; it does not prove the change is functionally right or safe. Read the patch contents, checking filenames, paths, added/removed lines, and any sensitive data before sending.

### 5.2. Applying the Diff Patch on Machine B

Ensure Machine B is on the exact base commit with a clean working tree:

~~~sh
git switch main
git status -sb
git rev-parse HEAD
~~~

Dry-run the check first:

~~~sh
git apply --check ../offline-report.diff
~~~

If the check passes, apply the patch:

~~~sh
git apply ../offline-report.diff
git status --short
git diff
~~~

git apply updates the working tree without creating a commit. If you want to stage at the same time, you can pass git apply --index, though in this lab it is better to inspect contents first before staging.

After reviewing:

~~~sh
git add src/report/ tests/report/
git diff --cached
git commit -m "feat(report): add offline report export"
~~~

The commit on Machine B will likely have a different SHA than the commit on Machine A because a diff patch does not carry full commit metadata and Git creates a fresh commit with current timestamps and committer details. That is normal behavior for a diff-patch workflow.

If git apply --check fails, do not force-apply. Verify the base commit, check whether the patch was already partially applied, and request the correct patch or reconcile intentional differences.

## 6. Creating a Format-Patch to Preserve Commit Metadata

When you want to send individual commits along with author, date, subject, and message, use git format-patch. This format fits email-based patch workflows or mbox files.

On Machine A:

~~~sh
git format-patch --stdout --binary --full-index main..feature/offline-report > ../offline-report.mbox
~~~

If the branch has multiple commits, the mbox file contains the series of patches corresponding to commits in that range. The recipient can apply them with git am to recreate commits while preserving author metadata from each patch.

### 6.1. Distinguishing git apply and git am

| Criterion | git apply | git am |
|---|---|---|
| Typical input | Diff patch | Email-formatted patch from format-patch |
| Preserves commit boundaries | Does not create commits automatically | Yes, each patch message creates one commit |
| Preserves author metadata | Does not create commits | Preserves author info from the patch |
| Updates working tree | Yes | Yes, while also creating commits |
| Pre-check support | git apply --check | Read patch, verify base, and test on a clone |
| On conflict | Apply fails; inspect working tree | Enters am state; resolve conflicts then --continue or --abort |

Do not feed a plain diff file without email headers into git am. Do not use git apply when your goal is to recreate a commit sequence automatically from format-patch output.

### 6.2. Applying the mbox on Machine B

On Machine B, use the separate receiver-am clone to test format-patch. Do not reuse receiver-project where you applied the diff patch earlier:

~~~sh
cd receiver-am
git switch main
git status -sb
git rev-parse HEAD
~~~

Create a branch for receiving the patch series:

~~~sh
git switch -c review/offline-report-am
~~~

Apply the patch series:

~~~sh
git am --3way ../offline-report.mbox
~~~

The --3way option lets Git fall back to a three-way merge using blob info in the patch and local repository objects if direct application fails. This only works when the required base blobs exist locally and the patch includes full index metadata.

Inspect the result:

~~~sh
git status -sb
git log --oneline --decorate main..HEAD
git show --stat --oneline HEAD
~~~

If the mbox contains multiple commits, confirm the count and ordering match Machine A. Author info is preserved from the patch, while committer is typically the person applying it; commit SHAs may differ.

### 6.3. Handling Conflicts During git am

If Git pauses on a conflict:

~~~sh
git status
git am --show-current-patch=diff
~~~

Read the current patch and resolve conflicted files. Then:

~~~sh
git add <resolved-file>
git am --continue
~~~

Repeat until the patch series finishes. To cancel:

~~~sh
git am --abort
~~~

Abort ends the in-progress am session and restores the state prior to starting it. Read status before aborting or continuing so you understand what step Git is on.

## 7. Creating a Full Git Bundle to Transfer History

Patches carry only diffs; bundles carry selected objects and refs. On Machine A, create a bundle containing the base branch, feature branch, and any related release tag:

~~~sh
git bundle create ../offline-report-full.bundle refs/heads/main refs/heads/feature/offline-report
~~~

To also include a tag:

~~~sh
git bundle create ../offline-report-release.bundle refs/heads/main refs/heads/feature/offline-report refs/tags/v1.0.0
~~~

A full bundle packs all objects needed to reconstruct the chosen refs without requiring the receiving repository to have prior base commits. Its exact scope depends on the refs specified; never assume a bundle contains every branch/tag unless explicitly included.

### 7.1. Listing Refs and Verifying the Bundle on the Sender

~~~sh
git bundle list-heads ../offline-report-full.bundle
git bundle verify ../offline-report-full.bundle
~~~

list-heads shows the object IDs and refs advertised by the bundle. verify checks bundle format and prerequisites. For a full bundle, no external history prerequisites are required.

Confirm the list includes:

- refs/heads/main
- refs/heads/feature/offline-report
- Any tags you chose to include.

If a ref is missing, regenerate the bundle with the complete ref list. Never edit a bundle file with a text editor.

### 7.2. Why Use a Full Bundle?

A full bundle fits when:

- The receiving machine has no repository yet or you are unsure which base commit it has.
- You need a self-contained recovery artifact.
- Transferring a repository across air-gapped network zones.
- You want to verify cloneability without relying on an existing remote.

In trade-off, full bundles can be large because they pack the entire reachable history of the included refs. If the recipient is guaranteed to have the base commit, an incremental bundle can be used.

## 8. Creating an Incremental Bundle When Both Sides Share a Base Commit

Suppose Machine B already has the same base commit as Machine A. On Machine A, record the base commit SHA:

~~~sh
git rev-parse main
~~~

Create a bundle containing only the new objects on the feature branch since that base:

~~~sh
git bundle create ../offline-report-incremental.bundle refs/heads/feature/offline-report ^<base-commit>
~~~

Replace <base-commit> with the agreed SHA. This syntax declares the base commit as a prerequisite. Machine B must already hold that object before the bundle can be fetched.

You can also specify a revision range:

~~~sh
git bundle create ../offline-report-incremental.bundle <base-commit>..refs/heads/feature/offline-report
~~~

### 8.1. Verifying an Incremental Bundle on Machine B

On Machine B, enter the receiver-bundle repository that holds the base commit and verify:

~~~sh
cd receiver-bundle
git rev-parse <base-commit>
git bundle verify ../offline-report-incremental.bundle
~~~

If a prerequisite is missing, Git reports that the repository lacks the required commits. Never ignore this error. Obtain the base bundle or a full bundle, then re-verify.

### 8.2. Fetching From an Incremental Bundle

After verification succeeds, fetch using the receiver-bundle clone that has the untouched base commit:

~~~sh
git fetch ../offline-report-incremental.bundle refs/heads/feature/offline-report:refs/remotes/offline/incremental/feature/offline-report
git log --oneline --decorate main..refs/remotes/offline/incremental/feature/offline-report
~~~

Fetch updates the remote-tracking ref offline/incremental/feature/offline-report. You can then create a local branch to review:

~~~sh
git switch -c review/offline-report-incremental refs/remotes/offline/incremental/feature/offline-report
~~~

If Machine B lacks the base commit or history was rebased/force-pushed, an incremental bundle may no longer apply. Re-establish the base or switch to a full bundle.

## 9. Verifying Integrity and Provenance of Handover Files

Bundle verification checks file structure and prerequisites, yet it does not prove who created the bundle. Patches can also be altered in transit. Use checksums to detect file tampering or corruption, and use digital signatures or an independent verification channel to confirm provenance when required.

On Linux:

~~~sh
sha256sum ../offline-report.diff ../offline-report.mbox ../offline-report-full.bundle
~~~

On macOS:

~~~sh
shasum -a 256 ../offline-report.diff ../offline-report.mbox ../offline-report-full.bundle
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\offline-report.diff -Algorithm SHA256
Get-FileHash .\offline-report.mbox -Algorithm SHA256
Get-FileHash .\offline-report-full.bundle -Algorithm SHA256
~~~

Record checksums in a manifest:

~~~text
offline-report.diff        SHA256: <hash>
offline-report.mbox        SHA256: <hash>
offline-report-full.bundle SHA256: <hash>
base-commit                <commit-sha>
feature-tip                <commit-sha>
sender                     <team-or-person>
created-at                 <timestamp>
~~~

A manifest only provides verification value if the recipient obtains it from a trusted channel. If both the files and the checksums are fetched from an untrusted source, an attacker could alter both together.

Before sending:

- Scan patches and history for secrets.
- Verify exact refs and commits.
- Store bundles, patches, and manifests only in authorized locations.
- Encrypt files when policy requires.
- Restrict recipients and retention duration.

## 10. Restoring the Repository From a Bundle Into a New Directory

This is the most critical check in the lab. Generating a bundle is not enough; you must prove the recipient can reconstruct a working repository from that file.

On Machine B, choose a new non-existent destination path, such as restore-test:

~~~sh
git clone --branch feature/offline-report ../offline-report-full.bundle restore-test
~~~

Cloning from a bundle creates an independent repository and checks out feature/offline-report. If the bundle does not contain that branch, inspect list-heads and pass the exact ref name.

Enter the restored directory:

~~~sh
cd restore-test
git status -sb
git branch -a
git tag --list
git log --oneline --decorate --graph --all
~~~

Verify:

- Branch feature/offline-report exists and is checked out.
- Tip commit matches the SHA recorded in the manifest.
- Included tags are present.
- Working tree is clean right after cloning.
- File contents match the handed-over version accurately.

### 10.1. Comparing Commit Tips

On Machine A:

~~~sh
git rev-parse refs/heads/feature/offline-report
~~~

In the restore-test repository:

~~~sh
git rev-parse HEAD
~~~

Both SHAs must match if the bundle was built from the exact same ref with no subsequent history rewriting.

### 10.2. Comparing Trees

On Machine A:

~~~sh
git rev-parse "refs/heads/feature/offline-report^{tree}"
~~~

On Machine B:

~~~sh
git rev-parse "HEAD^{tree}"
~~~

The tree SHAs must be identical when comparing the same commit. This confirms the file snapshot was restored accurately.

### 10.3. Verifying the Object Database

~~~sh
git fsck --full
~~~

git fsck checks object integrity and connectivity inside the repository. It may report dangling/unreachable objects in some repositories; interpret warnings in context rather than assuming every notice is a restore failure.

### 10.4. Verifying Builds and Tests

A clean Git-level restore does not guarantee the application runs properly. Run tests or builds per project instructions after ensuring required dependencies and data are available.

For repositories with submodules:

~~~sh
git submodule status
git submodule update --init --recursive
~~~

In an offline environment, child repositories also need their own accessible data sources; update may fail if submodule URLs are unreachable.

For Git LFS:

~~~sh
git lfs ls-files
git lfs pull
~~~

Standard Git bundles do not automatically include LFS objects stored outside the Git object database. Transfer LFS objects via a dedicated process or ensure the receiving machine has a valid LFS cache/remote.

## 11. Restoring From a Bundle Into an Existing Repository

A fresh clone is not always required. If Machine B already has a repository and wants to import a branch:

~~~sh
git bundle verify ../offline-report-full.bundle
git bundle list-heads ../offline-report-full.bundle
git fetch ../offline-report-full.bundle refs/heads/feature/offline-report:refs/remotes/offline/full/feature/offline-report
~~~

Inspect history:

~~~sh
git log --oneline --graph --decorate main..refs/remotes/offline/full/feature/offline-report
git diff --stat main...refs/remotes/offline/full/feature/offline-report
~~~

After reviewing, create a local branch:

~~~sh
git switch -c review/offline-report-bundle refs/remotes/offline/full/feature/offline-report
~~~

A fresh clone is ideal for testing standalone recoverability. Fetching is ideal when importing a ref into an existing repository. Both require verifying the bundle and specifying the exact refs.

## 12. Comparing Patch and Bundle Outcomes

Patches and bundles can be produced from the same branch while yielding different import outcomes.

| Criterion | Diff patch + git apply | Format-patch + git am | Bundle + clone/fetch |
|---|---|---|---|
| Change contents | Yes | Yes | Yes via objects |
| Commit metadata | Not carried in full | Carries author/message per commit | Preserves exact commit objects |
| Preserves commit SHAs | Does not create commits | Usually generates new SHAs on apply | Yes, fetches exact objects |
| Base requirement | Needs compatible tree | Needs compatible base history | Full bundle is standalone; incremental needs prerequisites |
| Output | Working tree (or index with --index) | New commits | Fetched/cloned refs and objects |
| Suitability for review | Very good | Very good | Inspectable via history and diff |
| Suitability for repository recovery | No | Incomplete | Suitable within scope of bundled refs |

If the recipient needs exact commit SHAs and full connected history, a bundle fits better than a patch. If the goal is content review and selective application, patches are more convenient.

## 13. Troubleshooting Practice Issues

**Patch fails to apply.**

- Check the base commit and working tree status.
- Run git apply --check before applying.
- Check whether the patch was already partially applied.
- Do not force past errors if the patch does not match.

**git am stops on a conflict.**

- Use git status and git am --show-current-patch=diff.
- Fix conflicts, stage resolved files, and run git am --continue.
- Use git am --abort to cancel the entire session if needed.

**Bundle verify reports missing prerequisites.**

- Check the base SHA on the receiving machine.
- Confirm whether the bundle is incremental.
- Transfer the prerequisite bundle or request a full bundle.

**Bundle lacks an expected ref.**

- Run git bundle list-heads.
- Check the ref names passed to bundle create.
- Regenerate the bundle with the complete refs.

**Bundle clone fails to check out a branch.**

- List advertised refs.
- Pass the exact branch name to --branch.
- If the bundle only holds tags or custom refs, fetch the specific ref instead of assuming a default branch.

**Restore clone succeeds but SHA does not match.**

- Check the manifest and received bundle.
- Verify whether the source branch was updated after creating the bundle.
- Check whether a rebase or history rewrite happened after handover.
- Never manually force refs to match a SHA without understanding the root cause.

**Restored repository is missing LFS files or submodules.**

- Check LFS pointers and gitlinks.
- Transfer LFS objects and child repositories via their own processes.
- Do not conclude a bundle is corrupt when missing data lives outside the Git object database.

## 14. Handing Over Files and Information to the Recipient

A handover package should follow a clear layout:

~~~text
offline-handoff/
├── offline-report.diff
├── offline-report.mbox
├── offline-report-full.bundle
├── SHA256SUMS.txt
└── HANDOFF.txt
~~~

HANDOFF.txt should document:

- Repository name and purpose of the transfer.
- Base branch and base commit.
- Feature branch tip and relevant tags.
- Whether the bundle is full or incremental.
- Prerequisites, if any.
- Recommended verify, clone, or fetch commands.
- Checksums/signatures and how to verify them.
- Sender, timestamp, and authorized contact channel.

Never write tokens, passwords, private keys, or customer data into HANDOFF.txt. Never include local config files or credential helpers in a handover package.

## 15. Lab Completion Criteria

Mark complete when all applicable criteria are met:

- [ ] Machine A has branch feature/offline-report with verified commits.
- [ ] Created a diff patch and checked it with git apply --check.
- [ ] Created a format-patch mbox and understand how to apply it with git am.
- [ ] Machine B successfully applied at least one patch type onto the right base commit.
- [ ] Created a full bundle and verified it successfully.
- [ ] Listed and confirmed refs inside the bundle.
- [ ] Tested an incremental bundle or clearly explained prerequisites.
- [ ] Created a checksum/manifest and verified received files.
- [ ] Cloned the bundle into a separate restore-test directory.
- [ ] Restored commit and tree SHAs match the source.
- [ ] Checked clean git status after cloning and ran git fsck.
- [ ] Identified Git LFS, submodules, configs, and hooks requiring separate transfer.
- [ ] Excluded credentials and private data from the handover package.

## 16. Self-Assessment Questions

1. Why do diff patches and format-patches require different apply commands?
2. When is git apply more appropriate than git am?
3. Why can git am produce different commit SHAs from the sender's machine?
4. How does a full bundle differ from an incremental bundle regarding prerequisites?
5. Why should you run git bundle verify on the receiving repository?
6. Does a checksum prove who created a bundle? Why or why not?
7. When should you clone from a bundle vs. fetch from a bundle?
8. Why should you clone into a restore-test directory instead of overwriting an active repository?
9. Does a Git bundle automatically transfer Git LFS objects, submodules, hooks, and credentials?
10. If a restore clone produces a different SHA from the source, what do you check before modifying refs?

## 17. Conclusion

Safe offline exchange combines the right tools with verification of the outcomes. Diff patches transfer net changes; format-patch and git am recreate commit sequences with author metadata; Git bundles package objects and refs for cloning or fetching without a direct remote.

Do not stop just because file generation succeeded. Verify patches, prerequisites, refs, checksums, and provenance; then clone the bundle into a fresh directory, compare commit and tree SHAs, check the object database, and run relevant tests. A handover is only trustworthy once the recipient can validate and restore it under expected conditions.

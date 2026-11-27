# Editing Commit Author, Email, and Timestamps Within the Right Scope

Every Git commit stores two sets of identity and timestamp metadata: **author** (the person who originally wrote the change) and **committer** (the person who created the current commit object). These two sets can match, yet often differ when a commit is cherry-picked, rebased, or reapplied by someone else.

When you discover a commit used the wrong email, author name, or timestamp, first identify exactly which field is wrong and whether the commit has already been shared. Changing Git configuration only affects future commits; to change metadata on an existing commit, Git must create a new commit object. For the latest commit, you can use `git commit --amend`; for older commits, interactive rebase is usually required. This changes the commit ID and can affect child commits, tags, signatures, and anyone relying on the old history.

This lesson explains how to inspect metadata, configure identity at the right scope, fix author/committer and timestamps on new or existing commits, choose between amend and rebase, and safely verify the result.

## 1. Author and Committer Are Two Distinct Roles

### 1.1. Author — the Creator of the Change

The author is the person credited with writing or creating the change content. A commit stores:

- Author name.
- Author email.
- Author date.

For example, a developer creates a patch and sends it to a maintainer to apply to the repository. The author is typically the developer who wrote the patch.

### 1.2. Committer — the Creator of the Commit Object

The committer is the person who created the commit object stored in the current history. A commit stores:

- Committer name.
- Committer email.
- Committer date.

If you write code and commit it yourself, author and committer are usually the same. If you cherry-pick someone else's commit or rebase a commit, the author can remain the original contributor while the committer becomes the person running the operation that creates the new commit.

### 1.3. Author Date and Committer Date

The two timestamps also carry distinct meanings:

| Field | Meaning |
| --- | --- |
| Author date | The recorded timestamp when the author created the change |
| Committer date | The timestamp when the current commit object was created |

For example:

- Alice writes a change on March 10.
- Bob cherry-picks that change onto the integration branch on March 12.

The new commit can record Alice as the author with an author date of March 10, and Bob as the committer with a committer date of March 12.

Do not treat these two dates as the same field or try to force them to match if doing so misrepresents history.

### 1.4. Metadata Lives Inside the Commit Object

A commit object stores the tree, parents, author, committer, and message. These fields are part of the commit's content, so changing any field produces a new OID/hash.

A commit cannot be edited in place like a row in a database. Operations like amend or rebase create new commit objects and update refs to point to the new history.

## 2. Inspecting Current Metadata

### 2.1. View Author and Committer of the Latest Commit

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

The output typically includes lines like:

~~~text
Author:     Alice Example <alice@example.com>
AuthorDate: 2025-03-10T09:30:00+07:00
Commit:     Bob Example <bob@example.com>
CommitDate: 2025-03-12T14:15:00+07:00
~~~

This is a quick way to identify which field is incorrect.

### 2.2. Print Each Field in a Clear Format

~~~bash
git show -s --format="Author: %an <%ae>%nAuthor date: %aI%nCommitter: %cn <%ce>%nCommitter date: %cI" HEAD
~~~

Common placeholders:

| Placeholder | Value |
| --- | --- |
| %an | Author name |
| %ae | Author email |
| %aI | Author date in strict ISO 8601 format |
| %cn | Committer name |
| %ce | Committer email |
| %cI | Committer date in strict ISO 8601 format |
| %H | Full commit hash |
| %s | Commit subject |

To inspect a specific commit, replace `HEAD` with a tag, branch, or commit ID.

### 2.3. View Raw Commit Object Data

~~~bash
git cat-file -p HEAD
~~~

The commit object displays fields such as:

~~~text
tree <tree-oid>
parent <parent-oid>
author Alice Example <alice@example.com> 1741573800 +0700
committer Bob Example <bob@example.com> 1741763700 +0700

Commit message
~~~

Git stores timestamps as Unix time alongside a timezone offset. Raw data is useful for exact investigation, though `git log --format=fuller` is usually easier to read.

### 2.4. Identify the Exact Commit Before Editing

View several recent commits:

~~~bash
git log --oneline --decorate -10
~~~

View commits with metadata:

~~~bash
git log --format=fuller --date=iso-strict -5
~~~

Do not rely on display position in a condensed log when editing a commit. Identify the commit by hash or sufficiently certain details, especially when multiple commits share the same subject.

## 3. Configuring Identity for Future Commits

### 3.1. Check Active Configuration

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

This command shows values alongside their configuration source, helping distinguish system, global, and local config.

You can check the identity Git will actually use:

~~~bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
~~~

These commands report the effective identity in the current environment. Environment variables such as `GIT_AUTHOR_NAME` or `GIT_COMMITTER_EMAIL` can override configuration.

### 3.2. Configure for One Repository

If a work email should apply only to the current repository:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

Local config is stored in the repository's Git config and applies only there, unless overridden by higher-priority configuration or environment variables.

Verify:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

### 3.3. Global Configuration for the Current User

If this identity fits most of your repositories:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

Avoid setting a work email globally if you also use the machine for personal repositories with different identity rules. In that case, local configuration is more appropriate.

### 3.4. Correct Configuration Does Not Fix Old Commits

`git config user.name` and `git config user.email` only affect the identity used for new commits. They do not change the author or committer already recorded in older commits.

If the latest commit used the wrong email, recreate the commit with amend. If an older commit is wrong, you must rewrite history or accept keeping the shared history per team convention.

## 4. Distinguishing Ways to Set Author and Committer

### 4.1. Using --author to Set the Author

The option:

~~~bash
git commit --author="Nguyen Van An <an@company.example>" -m "Add invoice validation"
~~~

sets the author for the commit being created. It is not an option for setting the committer.

Normally, the committer is taken from the current Git identity (matching config and environment variables).

### 4.2. Using --date to Set the Author Date

For example:

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Add invoice validation"
~~~

`--date` controls the **author date**. It does not directly set the committer date.

To display clearly after committing:

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

Use date-time strings with an explicit timezone offset, such as `+07:00`, to avoid ambiguity when collaborating across regions.

### 4.3. Environment Variables for Author and Committer

Git supports these environment variables:

| Variable | Field Set |
| --- | --- |
| GIT_AUTHOR_NAME | Author name |
| GIT_AUTHOR_EMAIL | Author email |
| GIT_AUTHOR_DATE | Author date |
| GIT_COMMITTER_NAME | Committer name |
| GIT_COMMITTER_EMAIL | Committer email |
| GIT_COMMITTER_DATE | Committer date |

These variables can be set for a single command so long-term configuration stays untouched.

In Bash:

~~~bash
GIT_AUTHOR_NAME="Nguyen Van An" \
GIT_AUTHOR_EMAIL="an@company.example" \
GIT_AUTHOR_DATE="2025-03-10T09:30:00+07:00" \
GIT_COMMITTER_NAME="Build Maintainer" \
GIT_COMMITTER_EMAIL="maintainer@company.example" \
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit -m "Add invoice validation"
~~~

In PowerShell, set the variables for the current shell session before calling Git:

~~~powershell
$env:GIT_AUTHOR_NAME = "Nguyen Van An"
$env:GIT_AUTHOR_EMAIL = "an@company.example"
$env:GIT_AUTHOR_DATE = "2025-03-10T09:30:00+07:00"

git commit -m "Add invoice validation"
~~~

Afterward, restore or clear the environment variables you set so they do not affect subsequent Git commands. If a variable already existed beforehand, save and restore its original value rather than deleting it indiscriminately.

### 4.4. Do Not Confuse --date with Committer Date

For example:

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Add invoice validation"
~~~

sets the author date to the specified value. The committer date remains the moment the commit object is created, unless you set `GIT_COMMITTER_DATE`.

When verifying, always read both AuthorDate and CommitDate to make sure you modified the right field.

## 5. Fixing the Latest Commit's Metadata with Amend

### 5.1. When to Use git commit --amend?

`git commit --amend` creates a new commit replacing the current branch tip. It is appropriate when you just created the latest commit and discover the author, email, date, or message is wrong.

Before amending, inspect:

~~~bash
git status --short --branch
git diff --cached
git log -1 --format=fuller --date=iso-strict
~~~

Pay special attention to the index: any staged changes will be included in the amended commit. If your goal is only fixing metadata, make sure no unintended staged changes exist.

### 5.2. Change Author Name and Email, Keep Commit Message

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

`--no-edit` preserves the current commit message. `--author` replaces author metadata; the new commit's committer comes from your current identity.

If you need to explicitly preserve the old author date, capture its value before amending:

~~~bash
git show -s --format=%aI HEAD
~~~

Then pass the desired date via `--date`:

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>" --date="2025-03-10T09:30:00+07:00"
~~~

Use the verified author date value rather than guessing the date.

### 5.3. Change Author Date

~~~bash
git commit --amend --no-edit --date="2025-03-10T09:30:00+07:00"
~~~

This command changes the author date for the new commit. It does not set the committer date to that value; the committer date defaults to the time the amend is performed.

### 5.4. Set the Current Author and Refresh Author Date

If the goal is recording the person performing the amend as the author, run:

~~~bash
git commit --amend --reset-author --no-edit
~~~

`--reset-author` sets the author to the current committer identity and refreshes the author timestamp. Do not use this option if you need to preserve the original creator of the change.

### 5.5. Fix Committer Identity

If the latest commit's committer name/email is wrong, set the right identity for the amend command using environment variables. For example, in Bash:

~~~bash
GIT_COMMITTER_NAME="Release Maintainer" \
GIT_COMMITTER_EMAIL="release@company.example" \
git commit --amend --no-edit
~~~

The amended commit keeps the current commit's author unless `--author` or `--reset-author` is specified. The committer identity is read from the environment variables for this newly created commit.

If you want to fix both author and committer, combine `--author` with the `GIT_COMMITTER_*` variables.

### 5.6. Fix Committer Date

To set the committer date, use `GIT_COMMITTER_DATE`, not `--date`.

In Bash:

~~~bash
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit --amend --no-edit
~~~

This can be combined with author options:

~~~bash
GIT_COMMITTER_DATE="2025-03-12T14:15:00+07:00" \
git commit --amend --no-edit \
  --author="Nguyen Van An <an@company.example>" \
  --date="2025-03-10T09:30:00+07:00"
~~~

In PowerShell, set `$env:GIT_COMMITTER_DATE` for the amend command and restore its previous value afterward. If there is no need to alter the committer date, let Git record the actual time of the amend operation.

### 5.7. Edit Commit Message Along with Metadata

If you also need to edit the message:

~~~bash
git commit --amend --author="Nguyen Van An <an@company.example>"
~~~

Git opens the editor to adjust the message. Or pass a new message directly:

~~~bash
git commit --amend --author="Nguyen Van An <an@company.example>" -m "Validate invoice before payment"
~~~

Do not pass `--no-edit` if your goal includes changing the message.

## 6. Fixing Metadata on Older Commits

### 6.1. Why Is Interactive Rebase Needed?

`git commit --amend` only replaces the current tip commit. If the commit needing adjustment sits deeper in history, you can use interactive rebase to pause at that commit, amend it, and replay subsequent commits.

Example history:

~~~text
A --- B --- C --- D  (HEAD)
      ^
      commit B has the wrong email
~~~

You want to fix B. Commits C and D are descendants of B, so during rebase, Git must recreate them on top of the new commit B.

### 6.2. Create a Recovery Point Before Rewriting History

Before starting:

~~~bash
git status --short --branch
git log --oneline --decorate
git branch backup/before-metadata-fix
~~~

Make sure the working tree and index are clean or all edits you want to keep are preserved. The backup branch lets you return to the pre-rewrite history if anything goes wrong.

The backup name should follow team conventions and not collide with existing refs.

### 6.3. Start Interactive Rebase from the Parent of the Target Commit

If the target commit is B:

~~~bash
git rebase -i B^
~~~

Replace B with the actual hash. Git opens a todo list containing B and the commits after it.

For a root commit with no parent, use:

~~~bash
git rebase -i --root
~~~

If history includes merge commits and topology must be preserved, read the documentation for `--rebase-merges` and choose an appropriate rewrite method. Default interactive rebase can alter merge structure.

### 6.4. Mark the Target Commit with edit

The todo list might look like:

~~~text
pick <hash-B> Add invoice validation
pick <hash-C> Add invoice tests
pick <hash-D> Update API documentation
~~~

Change `pick` to `edit` on B's line:

~~~text
edit <hash-B> Add invoice validation
pick <hash-C> Add invoice tests
pick <hash-D> Update API documentation
~~~

Save and close the editor. Rebase pauses at commit B so you can edit it.

### 6.5. Amend the Commit Being Rebased

Inspect the current commit:

~~~bash
git log -1 --format=fuller --date=iso-strict
~~~

Fix the author:

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

Or fix both author and author date:

~~~bash
git commit --amend --no-edit \
  --author="Nguyen Van An <an@company.example>" \
  --date="2025-03-10T09:30:00+07:00"
~~~

If you need to adjust the committer date, set `GIT_COMMITTER_DATE` for just the amend command. Otherwise, Git records the committer identity and timestamp of the person performing the operation.

### 6.6. Continue the Rebase

After amending:

~~~bash
git rebase --continue
~~~

Git replays the commits after B. Conflicts may arise if later changes no longer apply cleanly on top of the new commit.

Resolve conflicts using the normal process, run tests, then continue:

~~~bash
git status
git diff
git add -- path/to/resolved-file
git rebase --continue
~~~

Repeat if more commits or conflicts remain.

### 6.7. Verify the Entire History After Rebase

~~~bash
git log --format=fuller --date=iso-strict --oneline
git show -s --format=fuller --date=iso-strict <new-hash>
git status --short --branch
~~~

Verify:

- The target commit has the right author/email/date.
- Committer identity/date match the person who performed the rewrite.
- Child commits are still present and in the right order.
- Tree contents and tests were not unintentionally altered.
- The working tree is clean or has only known changes.

If the rebase encounters issues and you have not finished it yet, you can consider `git rebase --abort` to return to the pre-rebase state. The backup branch also retains the old reference point.

## 7. Setting Metadata for New Commits Without Rewriting Old History

### 7.1. Use Local Config for Future Work

If the repository should use a different identity from now on:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

New commits will use this identity unless overridden by environment variables or command-line options.

### 7.2. Set a Specific Author for One Commit

You can run:

~~~bash
git commit --author="Original Contributor <contributor@example.com>" -m "Apply contributor patch"
~~~

This is useful when applying a patch created by someone else and wanting to preserve accurate author attribution. The committer remains the person creating the commit.

### 7.3. Set Author Date for a New Commit

~~~bash
git commit --date="2025-03-10T09:30:00+07:00" -m "Apply contributor patch"
~~~

Use this when the author date has been verified from a trusted source. Do not set fabricated dates to make history look older or alter the apparent order of work.

### 7.4. Do Not Change Global Config to Spoof a Single Commit

Changing global `user.name` and `user.email` just to fix one commit can cause other repositories to use the wrong identity. For changes that apply to a single repository, use `--local`; for a single commit, use the appropriate option or environment variables.

## 8. Commit Timestamps and Timezones

### 8.1. Prefer Timestamps with Timezones

Recommended date-time format:

~~~text
2025-03-10T09:30:00+07:00
~~~

The `+07:00` offset tells Git the exact moment in a defined timezone. Entering a date without a timezone can produce results dependent on the environment and how Git parses the string.

### 8.2. Distinguish Displayed Time from Stored Time

Git stores a timestamp and offset. Display options like `--date=iso-strict` control presentation only and do not modify the timestamp inside the commit.

For example:

~~~bash
git log -1 --date=iso-strict --format=fuller
~~~

is a read-only command for formatting output clearly. It does not alter the author date or committer date.

### 8.3. Do Not Arbitrarily Backdate

Sometimes you need to restore an accurate author date from a patch or change management system. In those cases, use verified sources such as patch emails, review system timestamps, or organizationally stored metadata.

Do not set arbitrary dates or times to hide when work happened, bypass release controls, or distort the audit trail. Commit dates are not a tool for replacing official change logs.

## 9. Consequences of Rewriting Existing Commits

### 9.1. Commit Hashes Change

Because author, committer, and timestamps are part of the commit object, modifying them generates a new hash even if the tree and message are unchanged.

For example:

~~~text
Before: A --- B --- C
After:  A --- B' --- C'
~~~

B' has updated metadata. C' is recreated because its parent is now B', and therefore its hash changes too. Every subsequent descendant must be recreated.

### 9.2. Remote Branches Can Diverge

If the commit was already pushed and teammates based work on it, rewriting local history produces a history different from the remote.

Do not force push unexpectedly. Before rewriting shared history:

1. Communicate with people using the branch.
2. Identify any new commits created after the common point.
3. Create a backup ref.
4. Agree on the update timing.
5. Push according to team-approved workflow, typically using `--force-with-lease` if approved.

`--force-with-lease` prevents overwriting a remote ref that changed unexpectedly, yet it does not replace coordinating with the team.

### 9.3. Commit Signatures and Tags

If the old commit was GPG/SSH signed, amending or rebasing creates a new commit and the old signature no longer validates the new commit. Re-sign according to project policy if commits must be signed.

Tags pointing to the old commit do not move automatically to the new commit. If a tag needs to move, follow release and tag governance procedures; signed tags must also be recreated.

### 9.4. Other Clones and References

Rewriting a branch does not automatically update:

- Teammates' local clones.
- Forks.
- Open pull requests.
- Other tags or branches pointing to the old commit.
- Previously generated artifacts, logs, or backups.

Therefore, rewriting history requires a synchronization plan and checking all related references.

### 9.5. When Should Old History Be Preserved?

If a commit has been widely shared, sits on a protected branch, or is part of a release, it is often better to keep the existing history and create a new commit explaining or addressing the issue.

A new commit does not alter the old commit's metadata, yet avoids forcing everyone to synchronize rewritten history. Follow repository rules and audit requirements.

## 10. Common Mistakes

- **Confusing author and committer:** the original change creator and the commit object creator can differ. Inspect both fields.
- **Thinking git config fixes old commits:** config affects only new commits; existing commits require amend or history rewriting.
- **Using --date to fix committer date:** --date sets the author date. Use GIT_COMMITTER_DATE if you genuinely need to set the committer date.
- **Using --reset-author when you need to keep the original author:** that option replaces the author with the current identity and refreshes the author timestamp.
- **Amending when the index holds unrelated staged changes:** those changes will enter the new commit. Check git diff --cached first.
- **Using amend for non-tip commits:** amend replaces only the current commit; older commits require interactive rebase or an appropriate rewrite workflow.
- **Forgetting that child commits get new hashes:** rebase recreates descendants of the edited commit.
- **Rewriting a shared branch without notifying the team:** can cause diverged histories and extra sync effort.
- **Assuming tags and signatures update automatically:** tags can still point to old commits; old signatures do not validate new commits.
- **Entering dates without clear timezones:** results may not match the intended instant. Use ISO 8601 with an offset.
- **Setting fabricated timestamps:** distorts history and the audit trail. Edit only with valid justification.

## 11. Sample Workflow: Fixing the Email of the Latest Commit

Suppose the HEAD commit used an old email while its content and message are both right.

**Step 1 — Check status and metadata**

~~~bash
git status --short --branch
git diff --cached
git log -1 --format=fuller --date=iso-strict
~~~

**Step 2 — Configure the right identity for the repository if needed**

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

**Step 3 — Amend author, keeping message**

~~~bash
git commit --amend --no-edit --author="Nguyen Van An <an@company.example>"
~~~

If you need to set an exact author date, add `--date` with the verified timestamp. The committer will be your current identity and the time of the amend, unless you explicitly set committer environment variables.

**Step 4 — Verify**

~~~bash
git show -s --format=fuller --date=iso-strict HEAD
git status --short --branch
~~~

**Step 5 — If the commit was already pushed**

Stop before pushing an overwrite. Coordinate with the team and check whether the branch permits rewriting. If shared history cannot be rewritten, keep the old commit and handle it per project procedure.

## 12. Pre- and Post-Metadata-Edit Checklist

- [ ] Identified the exact commit by hash or ref.
- [ ] Distinguished author from committer.
- [ ] Determined whether the wrong field is name, email, author date, or committer date.
- [ ] Verified the correct value from a trustworthy source.
- [ ] Checked working tree and index before amending/rebasing.
- [ ] Created a backup ref before rewriting older commits.
- [ ] Chose amend for the tip or interactive rebase for older commits.
- [ ] Understood that commit hashes and descendants will change.
- [ ] Considered remotes, tags, signatures, and other clones.
- [ ] Coordinated if the branch has already been shared.
- [ ] Verified author/committer and both timestamps after the operation.
- [ ] Ran appropriate tests if commit content was rewritten/rebased.
- [ ] Synced with remote per team policy.

## 13. Quick Reference Table

| Goal | Command |
| --- | --- |
| View author, committer, and timestamps | git log -1 --format=fuller --date=iso-strict |
| View author email | git show -s --format=%ae HEAD |
| View committer email | git show -s --format=%ce HEAD |
| View author date | git show -s --format=%aI HEAD |
| View committer date | git show -s --format=%cI HEAD |
| View configured identity | git config --show-origin --get user.name and user.email |
| View effective author identity | git var GIT_AUTHOR_IDENT |
| View effective committer identity | git var GIT_COMMITTER_IDENT |
| Configure local identity | git config --local user.name / user.email |
| Fix author on latest commit | git commit --amend --no-edit --author="Name <email>" |
| Fix author date | git commit --amend --no-edit --date="ISO-8601-with-offset" |
| Set author to current committer | git commit --amend --reset-author --no-edit |
| Fix committer date | Set GIT_COMMITTER_DATE for git commit --amend |
| Edit an older commit | git rebase -i <commit>^ |
| Rebase from root commit | git rebase -i --root |
| Continue rebase | git rebase --continue |
| Abort active rebase | git rebase --abort |
| Inspect history again | git log --format=fuller --date=iso-strict |

## 14. Summary

Git stores separate author and committer identities and timestamps. Author describes the original creator of the change; committer describes the creator of the current commit object. `--author` sets the author, `--date` sets the author date, and `GIT_COMMITTER_*` variables control committer metadata.

Configuring `user.name` and `user.email` applies only to new commits. To fix the tip commit, use `git commit --amend`; to fix older commits, use interactive rebase and mark the target commit with `edit`. Before acting, inspect the index to avoid pulling unintended staged changes, confirm exact timestamps, and create a recovery point.

Any metadata change produces a new commit hash. If the commit has already been shared, evaluate impacts on child commits, remote branches, tags, signatures, and other clones. Only rewrite history with valid reason and coordination; if history must remain stable, follow your team's established convention.

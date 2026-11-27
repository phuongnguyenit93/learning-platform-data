# Replacing the Latest Commit with git commit --amend

When the latest commit has an unclear message, is missing a file, or contains an edit that needs adjustment, Git lets you replace that commit using `git commit --amend`. This command creates a new commit object from the current index state, replaces the branch tip with the new commit, and retains the old commit in the reflog for a period of time. It does not edit the old object in place.

In the **Creating Commits** chapter of the **SOURCE_CONTROL_GIT** module, this lesson teaches how to amend the latest commit intentionally. You will learn where amend pulls content from, how to edit the message, add or remove files, update author metadata, and handle commits that have already been pushed. You will also learn how to recover via the reflog if you amend by mistake while preserving the work you want to keep.

After this lesson, you will be able to:

- Explain how amend creates a new commit and moves the current ref.
- Check repository state before amending to know what content will enter the commit.
- Edit the commit message or keep the existing message with --no-edit.
- Add forgotten files and update the commit snapshot.
- Remove files or changes that should not be in the commit.
- Distinguish author, committer, and timestamps after amending.
- Re-sign a commit or add sign-off when needed.
- Understand the impact of amend on shared history and push safely.
- Find the old commit via reflog and recover selectively.

## 1. How Does Amend Replace the Tip Commit?

A Git commit is an immutable object. When you run git commit --amend, Git creates a new commit object, typically using:

- A tree built from the current index.
- The parent of the old tip commit.
- Author metadata from the old commit, unless you ask to change it.
- New committer metadata from the amend operation.
- The old message or a new message you provide.
- A new signature if the commit is signed.

Git then moves the current branch (or HEAD in detached state) to the new commit. The old commit's content is untouched.

Before amend:

~~~text
A --- B
      ^
      main / HEAD
~~~

After amend:

~~~text
A --- B'
      ^
      main / HEAD

B remains the old commit object, no longer the tip of main.
~~~

The new commit B' usually shares the same parent as B, while its tree, message, or metadata may differ. Because the commit object's content changed, the object ID of B' differs from B.

### Amend Does Not Edit Files Inside the Commit Object

Git does not open commit B and overwrite it. Object B stays intact; Git creates object B' and updates the ref. Therefore:

- The commit hash changes.
- Child commits of B, if any, will still point to the old B.
- Tags pointing to B still point to B.
- A remote holding B does not automatically switch to B'.
- The reflog typically records HEAD moving from B to B'.

This is a history-rewriting operation. Check whether the commit has already been shared before amending.

## 2. Amend Takes Content from the Index

The most important point when using amend is that the new commit builds its snapshot from the **index**, just like a normal commit. Unstaged changes in the working tree are not automatically included in the commit.

Check before amending:

~~~bash
git status --short
git diff --cached
git diff
git diff HEAD
~~~

Meaning:

- git diff --cached: staged content compared to the current commit.
- git diff: edits on disk that are not yet staged.
- git diff HEAD: total difference of the working tree compared to HEAD.

For example, a file has status MM:

~~~text
MM src/service.js
~~~

Column X indicates the index differs from HEAD; column Y indicates the working tree differs from the index. When amending, Git uses the content in the index. Changes appearing only in git diff remain outside the new commit.

If you want to include the latest edits in the amend, stage them first:

~~~bash
git add -- src/service.js
git diff --cached -- src/service.js
~~~

Only then run amend. If you want to keep unstaged edits for later work, do not stage them.

## 3. Editing the Latest Commit Message

When running the command without a message option:

~~~bash
git commit --amend
~~~

Git opens your editor to revise the commit message. You can edit the subject, body, or trailers, then save and close the editor to create the new commit.

If you only want to replace the message with a single line:

~~~bash
git commit --amend -m "fix(api): validate empty request body"
~~~

The command above replaces the tip commit's message with the new text. Any changes already staged in the index are also included in the new commit's tree.

### Keep the Message and Only Change Commit Content

If you staged a forgotten file or additional edits, and want to keep the existing message:

~~~bash
git add -- src/validator.js
git commit --amend --no-edit
~~~

--no-edit tells Git to keep the current message without opening the editor. A new commit is still created with the tree from the index; committer metadata and hash may change.

### Change Both Message and Content

~~~bash
git add -- src/validator.js
git commit --amend -m "fix(validation): reject malformed input"
~~~

This creates a new commit containing both the index content and the new message. Before running it, check git diff --cached to ensure the index has no out-of-scope changes.

## 4. Adding a Forgotten File After Committing

A common situation is realizing right after committing that you forgot to stage a needed file.

Suppose the latest commit modified src/api.js but missed test/api.test.js.

### Step 1: check the forgotten file

~~~bash
git status --short
git diff -- test/api.test.js
~~~

If the new file is untracked, git status typically shows ??; standard git diff does not display untracked file contents.

### Step 2: stage the missing file

~~~bash
git add -- test/api.test.js
git diff --cached -- test/api.test.js
~~~

Verify the file's content was added to the index as intended.

### Step 3: replace the tip commit

~~~bash
git commit --amend --no-edit
~~~

The new commit keeps the old message and includes the newly staged content. If the old commit has not been shared, this is usually a clean way to complete the commit.

### Step 4: verify

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD
git status --short
~~~

Confirm the test file is in the new commit and the working tree remains in the expected state.

## 5. Removing Files or Content from a Commit

If the latest commit accidentally recorded an unwanted file, update the index and amend.

### Delete the File from the Repository and Commit

~~~bash
git rm -- src/debug.log
git commit --amend --no-edit
~~~

git rm stages the file deletion; amend creates a new commit whose tree no longer contains that file.

### Remove the File from the Commit While Keeping a Copy on Disk

If you want the file to remain locally but not be tracked in the commit:

~~~bash
git rm --cached -- local-secrets.txt
git commit --amend --no-edit
~~~

--cached removes the file from the index while preserving it in the working tree. After amending, the file is absent from the new commit's tree. If the file contained secrets and was already pushed, amending does not remove copies on the remote, other clones, caches, or duplicated history. Handle leaks per your project's security process; rewriting a commit alone does not replace credential revocation.

### Fix File Content Inside the Commit

Open the file, edit it, and stage the corrected version:

~~~bash
git add -- src/config.js
git diff --cached -- src/config.js
git commit --amend --no-edit
~~~

If the index already had other staged changes, amend will include everything in the index in the new tree. Inspect the full git diff --cached, not just the file you edited.

## 6. Editing Author and Committer Metadata

Amend can alter commit metadata. By default, Git preserves the old commit's author information while recording the person running amend as the committer.

View metadata before amending:

~~~bash
git show -s --format=fuller HEAD
~~~

### Set a Specific Author

~~~bash
git commit --amend --author="Lan Nguyen <lan@example.com>" --no-edit
~~~

--author sets the new commit's author name and email. The committer remains the current identity running the command, unless overridden by config or environment variables.

### Reset Author to the Person Amending

~~~bash
git commit --amend --reset-author --no-edit
~~~

--reset-author sets the author to the current identity and refreshes the author date. Use this when you want to claim authorship of the recreated commit, not merely update the committer.

### Change Author Date

~~~bash
git commit --amend --date="2026-11-17T10:00:00+07:00" --no-edit
~~~

--date sets the author date for the new commit. The committer date is generated for the current amend operation unless explicitly controlled via environment variables.

Do not alter authors or timestamps just to make history look tidier. Metadata should accurately reflect change origin and collaboration workflow.

## 7. Changing the Commit Message and Trailers

The commit message is part of the commit object. Editing the message causes Git to generate a new object ID even if the tree is unchanged.

You can edit in your editor:

~~~bash
git commit --amend
~~~

Or replace the entire message:

~~~bash
git commit --amend -m "docs: clarify installation steps"
~~~

If multiple paragraphs are needed:

~~~bash
git commit --amend -m "fix(auth): reject expired sessions" -m "Check expiry before loading the user session.
Return a clear error so clients can refresh credentials."
~~~

Each -m option creates a message paragraph; Git places a blank line between the subject and body.

### Add a Sign-off Trailer

~~~bash
git commit --amend --signoff --no-edit
~~~

--signoff (short form -s) appends a Signed-off-by trailer using the committer identity. This trailer is an attestation under the DCO convention; it is not a cryptographic signature.

### Re-sign the Commit

~~~bash
git commit --amend -S --no-edit
~~~

-S requests signing the new commit using the configured format and key, such as GPG or SSH. If the old commit had a signature, that signature cannot be reused for the new commit because the object content changed. Re-verify:

~~~bash
git verify-commit HEAD
~~~

## 8. Amending a Root Commit

A root commit is the first commit in a history and has no parent. You can still replace the latest root commit if HEAD currently points to that root:

~~~bash
git commit --amend -m "chore: initialize project structure"
~~~

The new commit still has no parent, while its tree, metadata, or message may change and a new object ID is created. If the repository has other branches or refs pointing to the old root commit, they are not updated automatically.

Check parents:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

If the output shows only a single commit OID with no parent OIDs, it is a root commit.

## 9. Amend Only Affects the Latest Commit

git commit --amend replaces the commit currently pointed to by HEAD. It does not look up an arbitrary older commit by message or hash.

If you need to modify a commit deeper in history, rewrite the commit sequence with interactive rebase or an appropriate tool:

~~~bash
git rebase -i <parent-of-target>
~~~

In the rebase editor, change the action for the target commit to edit, then Git pauses at that commit for you to run amend. Subsequent commits are replayed and receive new hashes.

Use this only when you understand the scope of history being rewritten. If the older commit has already been shared, coordinate with anyone relying on that history.

## 10. Verifying the Result After Amending

Do not just see a success message and move on. Confirm the tree, message, metadata, and working tree state.

### View the New Commit

~~~bash
git show --stat --oneline HEAD
git show --format=fuller --no-patch HEAD
~~~

### View Commit Contents

~~~bash
git show --format=fuller --find-renames HEAD
~~~

### View Tree and Parents

~~~bash
git show -s --format="commit=%H%ntree=%T%nparent=%P" HEAD
~~~

### Check the Working Tree

~~~bash
git status --short
git diff
git diff --cached
~~~

If amend was used to add a forgotten file, verify the file is in the tree:

~~~bash
git ls-tree -r --name-only HEAD
~~~

If you want to compare the new commit with the old commit, first obtain the old OID from the reflog or where you noted it:

~~~bash
git diff <old-commit> HEAD
git show --stat <old-commit>
git show --stat HEAD
~~~

Comparing the two commits helps confirm which changes were added, removed, or modified.

## 11. Finding the Old Commit After Amending via Reflog

Because amend moves HEAD from the old commit to the new commit, the reflog usually records this transition.

View recent HEAD movements:

~~~bash
git reflog -n 10
~~~

Example:

~~~text
9f8e7d6 HEAD@{0}: commit (amend): fix(api): validate input
3a2b1c0 HEAD@{1}: commit: fix(api): validate
...
~~~

In this example:

- HEAD@{0} is the commit after amending.
- HEAD@{1} is the commit before amending.

The reflog is local data with a configured expiration period. It is not pushed to remotes and does not replace long-term backups.

### Preserve the Old Commit with a Rescue Branch

If you want to preserve the old commit before performing recovery steps:

~~~bash
git branch backup-before-amend <old-commit>
~~~

Replace <old-commit> with the verified OID from the reflog. The new branch keeps a ref pointing to the old commit so you can compare or restore later.

## 12. Recovering After an Accidental Amend

First, stop performing further history-rewriting operations and inspect the reflog:

~~~bash
git reflog -n 10
git status --short
~~~

Identify the exact pre-amend OID. Do not blindly rely on HEAD@{1} if additional checkouts, resets, or commits happened afterward; read the reflog entries carefully.

### Return to the Old Commit While Keeping Amended Content in the Index

If the goal is moving the branch back to the old commit while keeping the new commit's snapshot as staged changes:

~~~bash
git reset --soft <old-commit>
~~~

--soft moves HEAD/ref to the old commit while leaving the index and working tree untouched. The difference between the old commit and the amended snapshot will sit in the index. You can inspect:

~~~bash
git status --short
git diff --cached
git diff
~~~

This is usually the right approach when you want to undo the amend while keeping the added content for further editing.

### Just Keep the Old Commit as a Reference Backup

If you are unsure whether to restore immediately, create a backup branch as shown earlier. Then compare:

~~~bash
git show <old-commit>
git show HEAD
git diff <old-commit> HEAD
~~~

Choose a recovery plan once you understand the tree and differing changes.

### Reflog Does Not Store Uncommitted Edits

The reflog records ref movements, not full copies of the working tree. If you had unstaged or untracked changes prior to amending, subsequent reset/restore operations could affect them. Check status and separately save any work you need to preserve before recovering.

## 13. What Happens If the Commit Was Already Pushed?

If the old commit was already pushed, the remote branch still points to the old commit. After amending, the local branch points to a new commit with the same parent but a different object ID. On a normal push, Git usually rejects it because the update is not a fast-forward.

~~~text
Remote before amend:
A --- B (origin/main)

Local after amend:
A --- B' (main)
~~~

B' is not a descendant of B; it shares parent A but is a different object. A normal push cannot move origin/main from B to B'.

### Prefer Avoiding Amending Shared Commits

If others have already fetched or built commits on top of B, replacing B with B' can cause their histories to diverge. They may need to rebase, reset, or deal with duplicate commits. On shared branches, the least disruptive approach is usually creating a new follow-up fix commit rather than rewriting a published commit.

### If the Team Agrees to Rewrite the Branch

Only with consensus and after verifying the remote tip should you use this workflow:

~~~bash
git fetch origin
git log --oneline --decorate --graph --left-right main...origin/main
git push --force-with-lease origin main
~~~

Before pushing, read the comparison output to be sure no new teammate commits need to be integrated. --force-with-lease requires the remote ref to still match the value your local repo expects, preventing overwriting an update that arrived after your check. Even so, it does not replace coordinating with teammates, checking remote history, and confirming the right branch.

If the remote has advanced with new teammate commits, stop and integrate the new history before deciding to rewrite. Force-with-lease will reject if the remote is no longer at the expected value; fetch and re-inspect rather than overriding the safeguard.

### Protected Branches

Some platforms or repositories are configured to reject force pushes to main, release, or protected branches. This is a server-side policy. Use a follow-up fix commit or an approved team workflow instead.

## 14. Impact on Tags, Signatures, and Pipelines

Amend creates a commit with a new OID. Other references do not move along automatically:

- Tags pointing to the old commit keep pointing to the old commit.
- Other branches keep pointing to the old commit.
- Remote branches do not change automatically.
- Pull requests or CI may continue referencing the old commit until the branch is updated.

If a release tag already points to the old commit, do not unilaterally move a published tag. Follow your team's release policy; moving a tag can leave other users with two different meanings for the same version.

The old commit's signature also does not apply to the new commit. If the project requires signed commits, re-sign:

~~~bash
git commit --amend -S --no-edit
git verify-commit HEAD
~~~

When you push the new commit, CI or automation may re-run. Check build status, reviews, and release pipelines tied to the branch.

## 15. Common Amend Scenarios

| Goal | Suggested Command | Result |
| --- | --- | --- |
| Edit message in editor | git commit --amend | Creates new commit with edited message |
| Replace message directly | git commit --amend -m ... | Replaces message and uses current index |
| Add a forgotten file | git add file then git commit --amend --no-edit | Adds file to new commit tree, keeps message |
| Fix already-committed content | Edit file, git add file, then amend | New commit tree includes staged content |
| Keep message, update tree only | git commit --amend --no-edit | Uses current index snapshot |
| Change author | git commit --amend --author=... | Records new author |
| Set author to person amending | git commit --amend --reset-author | Resets author and author date |
| Sign the new commit | git commit --amend -S --no-edit | Generates new signature |
| Add DCO sign-off | git commit --amend -s --no-edit | Appends Signed-off-by trailer |
| Remove file from commit, keep locally | git rm --cached file then amend | Removes entry from new tree, keeps file on disk |

All these commands replace the tip commit. Before running them, check git status, git diff, and git diff --cached to verify exactly what the new tree will contain.

## 16. Common Misconceptions

### Does --amend edit the old commit object in place?

No. Git creates a new commit object and moves the ref. The old commit continues to exist until it is no longer held by any ref/reflog and may be pruned later.

### Does amend automatically include all edits on disk in the commit?

No. The new tree is taken from the index. Unstaged changes remain in the working tree.

### Does --no-edit only change the timestamp?

No. It keeps the commit message and skips opening the editor. The tree is still taken from the index; committer metadata and hash can still change.

### Can an amended commit that was pushed be pushed normally?

Usually not, because the new commit is not a descendant of the old commit. Coordination is required to rewrite history, using force-with-lease when permitted.

### Does amending an older commit require interactive rebase?

Yes. --amend only replaces the commit currently pointed to by HEAD. To modify an earlier commit, use interactive rebase or an appropriate history-rewriting workflow.

### Do tags automatically move to the commit after amending?

No. Tags are separate refs. If a tag points to the old commit, it keeps pointing there until an action explicitly updates the tag.

### Is the reflog a permanent backup?

No. The reflog is only local ref history and can expire or be pruned. Create a backup branch or save the OID if you need to preserve an old commit.

## 17. Self-Check

You just committed fix(api): validate request, then realized you forgot to add test/api.test.js. The working tree has the new test file and no other changes. The commit has not been pushed.

Answer the following:

1. Why do you need to run git add before amending?
2. Which command adds the test file to the commit while keeping the same message?
3. Does the new commit keep the old OID?
4. Do author and committer necessarily stay identical after amending?
5. Which command verifies that the new commit has a valid signature?
6. If you amend by mistake, how do you find the old commit's OID?
7. If the old commit was already pushed to a shared branch, why should you coordinate before force pushing?

**Hint:** git add places the file into the index; git commit --amend --no-edit creates a new commit from the index and keeps the message. The new OID differs from the old OID. Author is usually preserved while committer is the person running amend. Use git verify-commit HEAD to check the signature. Use git reflog to find the old commit. Rewriting shared history can cause teammates' branches to diverge or drop their commits from the tip; force push only when the team agrees and the remote has been verified.

## Conclusion

git commit --amend replaces the tip commit with a new commit object, taking its tree from the index and keeping or replacing message/metadata based on options. Use it to fix a message, add forgotten files, or adjust content before sharing history. Inspect staged and unstaged changes before amending, and verify the tree, message, and signature afterward. If you amend by mistake, the reflog helps locate the old commit; reset --soft can move the branch back to that commit while keeping the new snapshot in the index. If the commit has already been pushed or others depend on it, coordinate before rewriting history and only force push according to team policy.

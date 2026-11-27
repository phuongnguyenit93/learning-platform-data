# Creating a tag on a past commit and inspecting the target object

Git allows you to create a tag pointing to any commit present in the repository, even a commit deep in history. You do not need to check out that commit or reset the current branch back in time. Simply identify the right commit, create a tag pointing to it, and verify the object the tag references.

In the **Tags and Version Milestones** chapter of the **SOURCE_CONTROL_GIT** module, this lesson guides you through marking a past milestone, such as a commit that was already released but never tagged. You will distinguish between lightweight tags and annotated tags, verify whether a tag actually points to the intended commit, and share tags with a remote without accidentally altering a published release milestone.

After this lesson, you will be able to:

- Locate and confirm the commit to mark in history.
- Create a lightweight tag or annotated tag on a past commit.
- Check whether a tag points directly to a commit, a tag object, or another object type.
- Compare the actual target commit against the expected commit.
- Push tags to a remote and verify they have been shared.
- Handle duplicate tag names or misapplied release tags.

## 1. A tag marks an object in history

A tag is a named reference in the refs/tags namespace. Tags are commonly used to mark release versions, handoff milestones, tested builds, or important commits you need to find again.

Example history:

~~~text
A---B---C---D---E  (main)
        ^
        v1.0.0
~~~

The tag v1.0.0 points to commit C, even though the main branch has progressed to E. When creating a tag on an old commit, Git does not move main, does not check out C, and does not modify the working tree. Git simply creates a new reference named v1.0.0 pointing to the selected object.

Key differences between a branch and a tag:

- A branch typically moves when new commits are created on that branch.
- A tag is normally treated as a fixed milestone. Git does not automatically move a tag as the branch continues developing.
- A tag stays in the local repository until pushed to a remote.

A tag can point to a commit, tree, blob, or another tag object. In software release workflows, teams generally want a tag to ultimately resolve to a specific commit so the version's source code can be reconstructed.

## 2. Finding the past commit to tag

Before creating a tag, identify the exact commit to mark. Do not rely on relative positions like "the previous commit" if history has changed or the current branch has moved forward.

### Viewing commit history

~~~bash
git log --oneline --decorate --all
~~~

This command displays history reachable from existing references, including branches and tags. Use the following options to narrow results:

~~~bash
git log --oneline --decorate --all -- path/to/file
git log --format=fuller --all
~~~

The first command helps find commits that modified a specific file. The second displays additional author and committer details and timestamps to cross-reference a release milestone.

### Inspecting commit contents

Once you have a candidate hash or revision, inspect the commit details:

~~~bash
git show --stat <commit>
git show --format=fuller --no-ext-diff <commit>
~~~

Check the list of changed files, diff contents, commit message, and related metadata. If the tag represents a release, confirm that the commit matches the source code that was tested and released.

### Normalizing to a commit hash

You can ask Git to verify that a revision resolves to a commit:

~~~bash
git rev-parse --verify '<commit>^{commit}'
~~~

Replace `<commit>` with the hash or revision to check. The `^{commit}` suffix instructs Git to resolve the object to a commit. If the revision does not exist or cannot be resolved to a commit, the command fails.

After verification, record the full hash to use in the tag creation command. Using an explicit hash avoids mistakes when branches or references move during release preparation.

## 3. Lightweight tag: a direct reference

A lightweight tag is essentially a reference name pointing directly to the chosen object. It does not create a separate tag object, store a tagger message, or carry a tag signature.

Create a lightweight tag at a past commit:

~~~bash
git tag v1.0.0 <commit>
~~~

If you omit the commit argument:

~~~bash
git tag v1.0.0
~~~

Git creates the tag at the commit HEAD currently points to.

Lightweight tags are suitable for temporary local markers, testing checkpoints, or cases where you only need a short name pointing to an object. For release milestones where you need to record the creator, tagging timestamp, message, and signature, annotated tags are generally more appropriate.

You can list tags:

~~~bash
git tag --list
git tag --list 'v1.*'
~~~

To view the commit a lightweight tag points to:

~~~bash
git show --no-patch --oneline v1.0.0
git rev-parse 'v1.0.0^{commit}'
~~~

## 4. Annotated tag: a tag object with metadata

An annotated tag creates a dedicated tag object. This object contains:

- The hash of the target object.
- The target object type, such as commit.
- The tag name.
- Tagger information and tag creation timestamp.
- The tag message.
- A signature, if the tag is signed.

Create an annotated tag at a past commit:

~~~bash
git tag -a v1.0.0 <commit> -m "Release v1.0.0"
~~~

If no commit is specified, Git uses the current HEAD:

~~~bash
git tag -a v1.0.0 -m "Release v1.0.0"
~~~

The first command is suitable when tagging a commit already in history without checking it out. The second is convenient when you are already on the exact commit to be released.

Annotated tags can be signed if the environment has a signing key configured:

~~~bash
git tag -s v1.0.0 <commit> -m "Release v1.0.0"
~~~

The signature lets recipients verify the signer's identity and the integrity of the tag object per verification settings. To check a signature:

~~~bash
git tag -v v1.0.0
~~~

Verification requires the corresponding public key and configuration. An unsigned tag is still a valid annotated tag; signing is an additional requirement of the release workflow.

## 5. Tagging a past commit does not change the commit's date

When creating an annotated tag today for an older commit, there are two distinct timestamps:

- **Commit date**: the time the commit was created or recorded in the commit metadata.
- **Tagger date**: the time the annotated tag creator marked the version milestone.

The tagger date is when the tag object was created, not when the old commit was created. Applying tag v1.0.0 today to a commit from last month does not give that commit a new date, nor does it make the tag proof that the version was released last month.

If you need to reconstruct a historical release milestone, check actual release records from your release system, CI, artifact registry, or project documentation. Do not backdate tag timestamps to make metadata look like an old release date if it does not reflect the actual event.

Example:

~~~bash
git show --no-patch --format=fuller <commit>
git cat-file -p v1.0.0
~~~

The first command inspects commit metadata. The second inspects the annotated tag object's contents, including the tagger field and tagging timestamp.

## 6. Checking which object a tag points to

The mere existence of a tag name does not prove it points to the right commit. You need to verify the object type and target hash.

### Determining the object type directly under the tag name

~~~bash
git cat-file -t v1.0.0
~~~

Common outputs:

- Lightweight tag pointing directly to a commit: output is commit.
- Annotated tag: output is tag, because the tag name points to a tag object.

Therefore, seeing tag as the result does not mean the tag is wrong. You need to peel the tag object layer to inspect the final target object.

### Inspecting the contents of an annotated tag object

~~~bash
git cat-file -p v1.0.0
~~~

An annotated tag typically looks like this:

~~~text
object 0123456789abcdef...
type commit
tag v1.0.0
tagger Developer <developer@example.com> 1730000000 +0700

Release v1.0.0
~~~

The object field contains the hash of the tagged object. The type field indicates that object's type. If type is commit, the tag object points directly to a commit. If type is tree or blob, the tag does not mark a commit as expected for a source code release milestone.

### Peeling a tag to its target commit

Use the peel operator:

~~~bash
git rev-parse 'v1.0.0^{commit}'
~~~

This command asks Git to resolve the tag to a commit. It works with lightweight tags, annotated tags, and nested tag chains as long as they ultimately resolve to a commit.

Compare with the expected commit:

~~~bash
git rev-parse '<commit>^{commit}'
git rev-parse 'v1.0.0^{commit}'
~~~

Both hashes must match if the tag was attached to the chosen commit. This is a more direct and reliable check than merely looking at the tag name in a list.

You can inspect the details of the commit the tag resolves to:

~~~bash
git show --no-patch --format=fuller 'v1.0.0^{commit}'
~~~

This command displays the metadata of the target commit after peeling the tag, helping confirm the commit message, author, and timestamp.

## 7. Inspecting tags and commits from multiple perspectives

Several commands are helpful when auditing release milestones:

~~~bash
git tag --list --sort=-version:refname
git tag --points-at <commit>
git show --no-patch --decorate <commit>
git for-each-ref refs/tags
~~~

- The first command lists tags in version order, useful when tag names follow versioning conventions.
- The second command finds tags pointing directly to the selected commit.
- The third command displays the commit along with associated references.
- The fourth command lists tag refs and their metadata; you can add format options to display specific fields.

Example showing tag name, object hash, and object type:

~~~bash
git for-each-ref --format='%(refname:short) %(objectname) %(objecttype)' refs/tags
~~~

For annotated tags, objecttype is tag. For lightweight tags pointing directly to a commit, objecttype is commit. If you need the final commit each tag represents, use a peel expression or inspect each tag individually.

## 8. Ensuring the past commit is reachable

Git only creates a tag when the target object exists in the repository. If you have the hash of an old commit but the current repository lacks that object, tag creation will fail.

Check the commit:

~~~bash
git cat-file -t <commit>
git show --no-patch --oneline <commit>
~~~

If the commit is missing from the repository, check whether the clone is a shallow clone or has truncated history. You may need to fetch additional history from a remote containing the commit. Never create a tag based on an unverified hash or a commit of unclear origin.

Once created, the tag holds a reference to the target object and keeps that object reachable via the ref. This is especially useful if the old commit is no longer at the tip of an active branch.

## 9. Sharing tags with a remote

Newly created tags exist only in the local repository. To make them visible to teammates or CI/CD pipelines, push the tags to the remote.

### Pushing a specific tag

~~~bash
git push origin v1.0.0
~~~

This is the explicit approach when you only want to share one milestone. It avoids pushing unrelated local tags to the remote.

### Pushing annotated tags associated with pushed commits

~~~bash
git push --follow-tags origin main
~~~

The follow-tags option pushes annotated tags missing on the remote that are reachable from the commits being pushed. It does not push every local lightweight tag.

### Pushing all tags

~~~bash
git push origin --tags
~~~

This command pushes all local tags not yet on the remote. Only use it when the team intentionally wants to synchronize all tags; if the local repository has experimental or unrelated tags, they may be shared as well.

### Checking tags on the remote

~~~bash
git ls-remote --tags origin
git ls-remote --tags origin 'v1.0.0'
~~~

For annotated tags, the output may include two lines: one for the tag object and one with a `^{}` suffix for the final peeled object. The peeled line helps verify the commit the annotated tag ultimately represents.

To fetch tags from the remote to local:

~~~bash
git fetch origin --tags
~~~

After fetching, use git show or git rev-parse to re-verify the local tag.

## 10. Naming conventions and managing release tags

Tag names should be consistent, readable, and aligned with how the team numbers versions. A common convention is Semantic Versioning:

- v1.2.0: official release version.
- v1.2.1: backward-compatible bug-fix patch.
- v1.3.0: backward-compatible feature addition.
- v2.0.0: changes that may break compatibility.

This is a naming convention, not a Git requirement. If a project uses a release calendar or custom build codes, another format can be chosen, provided each component's meaning is clearly documented.

For release tags, teams should generally:

- Use annotated tags to store the message and tagger.
- Only tag commits that have been reviewed, tested, and confirmed as release content.
- Attach tags to commits on the release branch or approved commits.
- Verify the tag peels to the right commit before pushing.
- Record release notes and related artifacts for traceability.
- Avoid moving or reusing published tag names.

A tag alone does not guarantee an artifact was built from that commit. Release pipelines should store the commit hash alongside the tag in artifact metadata so users can verify the exact source code that produced the release package.

## 11. Handling duplicate or misapplied tags

Git will not create a new tag with an existing name unless forced to overwrite. First, inspect the existing tag:

~~~bash
git show --no-patch --decorate v1.0.0
git rev-parse 'v1.0.0^{commit}'
~~~

If the tag has never been shared and you confirm you want to change the local tag, you can delete and recreate it:

~~~bash
git tag -d v1.0.0
git tag -a v1.0.0 <correct-commit> -m "Release v1.0.0"
~~~

Or use the force option to move the local tag:

~~~bash
git tag -f -a v1.0.0 <correct-commit> -m "Release v1.0.0"
~~~

Do not use force merely to bypass a "tag already exists" error. Modifying a tag can cause others or pipelines relying on the old hash to misinterpret the release milestone.

If the tag has already been pushed, do not overwrite or delete it on the remote on your own. Notify the team, identify which systems have consumed the tag, and agree on how to remediate. For a published release, the clearest approach is usually to keep the old tag intact and release a new tag such as v1.0.1 or a fix version per project policy.

If the team genuinely allows moving a remote tag, do so deliberately and notify all consumers. Git supports force-pushing updates to an existing tag, but that rewrites a shared reference; do not treat it as the default fix.

## 12. Workflow for creating and verifying a tag on a past commit

Suppose the team discovers version 1.0.0 was released from an older commit, but the repository lacks the tag. You can follow this workflow.

### Step 1: Update remote information and inspect history

~~~bash
git fetch origin
git log --oneline --decorate --all
~~~

Find the released commit based on release records, CI logs, or artifact metadata. Do not pick a commit simply because it happens to be the current HEAD of main.

### Step 2: Inspect the target commit

~~~bash
git show --stat <release-commit>
git show --format=fuller --no-ext-diff <release-commit>
git rev-parse --verify '<release-commit>^{commit}'
~~~

Verify the diff, metadata, and full hash. When needed, cross-check against the hash recorded in artifacts or build logs.

### Step 3: Verify the tag name is unused

~~~bash
git tag --list 'v1.0.0'
git ls-remote --tags origin 'v1.0.0'
~~~

If the tag already exists locally or on the remote, stop and inspect where it points. Do not overwrite an existing tag of the same name.

### Step 4: Create an annotated tag at the past commit

~~~bash
git tag -a v1.0.0 <release-commit> -m "Release v1.0.0"
~~~

Replace `<release-commit>` with the hash verified in Step 2. The tag is created at that commit even if HEAD is currently at a newer commit.

### Step 5: Verify object type and target commit

~~~bash
git cat-file -t v1.0.0
git cat-file -p v1.0.0
git rev-parse 'v1.0.0^{commit}'
git show --no-patch --format=fuller 'v1.0.0^{commit}'
~~~

For an annotated tag, the first command returns tag. The tag object content must show the target object has type commit. The hash from rev-parse must match the verified release-commit hash.

### Step 6: Push the tag and verify on the remote

~~~bash
git push origin v1.0.0
git ls-remote --tags origin 'v1.0.0'
~~~

Confirm the remote has the tag and the annotated tag's peel line points to the intended commit. Record the tag, commit hash, and artifact details in the release notes.

## 13. Common misconceptions

### Does tagging an old commit change the current branch?

No. Git simply creates a tag reference pointing to the selected object. HEAD, the current branch, and the working tree are not moved by the tag command.

### Does a tag name prove it points to the right release commit?

No. A name like v1.0.0 is just a reference name. Check the object type, peel the tag to a commit, and compare its hash against the confirmed commit.

### Does an annotated tag always point directly to a commit?

No. A tag object can point to a commit, tree, blob, or another tag object. Use the `^{commit}` expression to verify the final target resolves to a commit.

### Does a lightweight tag store its own tag creation date?

There is no separate tag object to store a tagger and tagger date. Tools may display the date from the commit the lightweight tag points to; do not interpret that date as the time the tag was created.

### Does creating a local tag automatically make it appear on the remote?

No. You must push the specific tag, use follow-tags, or push all tags according to your team's policy.

### Should you edit a published release tag if it was applied to the wrong commit?

Do not unilaterally move a shared tag. Changing it can cause users, pipelines, and artifacts to reference different commits under the same name. Coordinate with the team and prefer issuing a new corrective tag per release policy.

## 14. Self-check

Suppose the main branch is at commit H. Version 2.1.0 was actually released from commit F, but the tag v2.1.0 does not exist yet. The repository has the following commits:

~~~text
A---B---C---D---E---F---G---H  (main)
                  ^
                  2.1.0 release commit
~~~

Answer the following:

1. Do you need to check out F before creating the tag?
2. Which command creates the annotated tag v2.1.0 at F?
3. Which command verifies that the tag name resolves to a commit?
4. Why might git cat-file -t v2.1.0 return tag instead of commit?
5. How do you compare the commit the tag points to with F's hash?
6. After creating the local tag, what must you do so CI on the remote sees the tag?
7. If tag v2.1.0 was already pushed but mistakenly points to E, how should the team handle it?

**Hint:** You do not need to check out F. Use git tag -a v2.1.0 F -m "Release v2.1.0". Use git rev-parse 'v2.1.0^{commit}' to verify the tag resolves to a commit and compare it with git rev-parse 'F^{commit}'. For an annotated tag, the tag name points to a tag object, so cat-file -t returns tag; peeling is needed to see the target commit. Use git push origin v2.1.0 and verify with git ls-remote. If an incorrect tag was already published, coordinate with the team and prefer releasing a new corrective tag rather than unilaterally moving the old milestone.

## Conclusion

Creating a tag on a past commit only requires identifying the right commit and creating a reference pointing to it; no checkout or moving the current branch is needed. A lightweight tag is a direct reference, while an annotated tag stores metadata and can be signed, making it well suited for releases. After creating a tag, inspect the object type, peel the tag to a commit, and compare its hash against the confirmed release commit. Finally, push the tag to the remote and verify on the remote so all team members, CI systems, and artifacts rely on the exact same milestone.

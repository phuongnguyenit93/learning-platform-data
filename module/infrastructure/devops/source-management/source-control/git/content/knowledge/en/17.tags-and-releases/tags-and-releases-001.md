# Tags are fixed references by convention, unlike branches

In Git, both branches and tags are named references pointing to an object in a repository, typically a commit when managing source code. However, they serve different purposes. A branch is a movable pointer updated when new commits are created; a tag is typically used to mark a meaningful milestone such as a release version and is kept unchanged after creation.

The key point to understand accurately is that Git does not inherently make tags immutable. Tags are treated as fixed milestones by team convention. Users with appropriate permissions can still delete or move a tag. Therefore, a release process should protect tags on the server, verify the target commit, and record release information so everyone can rely on the same milestone.

## 1. What is a Tag?

A tag is a named reference in a repository, typically used to mark an important commit. For example:

- v1.0.0: the first released version.
- v1.1.0: a version adding backward-compatible features.
- v1.1.1: a bug-fix release.
- v2.0.0: a version with major or breaking changes.

When you create the tag v1.1.0 at commit A, the tag name continues pointing to commit A even when the main branch gains commits B, C, or D. This allows the team to retrieve the exact source code snapshot labeled with that version.

Example:

~~~text
A---B---C---D  main
 \
  v1.0.0
~~~

After main advances with more commits:

~~~text
A---B---C---D---E---F  main
 \
  v1.0.0
~~~

The tag v1.0.0 still points to A. The main branch moves from commit to commit as new commits are added, whereas the tag stays on the marked milestone by convention.

Tags are commonly used for:

- Marking release versions.
- Recording handoff milestones or stable checkpoints.
- Providing deterministic inputs for build and deploy pipelines.
- Cross-referencing the source code of a release when investigating bugs.
- Verifying provenance via tag signatures in security workflows.

A tag does not contain the entire installation package or built artifacts. It marks an object in Git history; artifacts, release notes, and release assets are usually managed by other systems.

## 2. How do Tags and Branches differ?

Branches and tags are both refs, but their usage differs:

| Criterion | Branch | Tag |
|---|---|---|
| Purpose | Track a line of development | Mark a specific milestone |
| When a new commit is created on the branch | The branch ref is typically moved to the new commit | A tag does not move automatically |
| Common use cases | Feature development, bug fixes, version maintenance | Marking releases, stable milestones, test checkpoints |
| Ref namespace stored in Git | refs/heads/ | refs/tags/ |
| Can it be deleted or moved? | Yes | Yes, but should be avoided for published tags |
| Collaboration practice | Frequently updated | Kept unchanged after release |

Put simply: a branch is like a pointer tracking where work is ongoing; a tag is like a label attached to a historical milestone that the team wants to reference again.

### 2.1. A branch is a movable reference

When on the main branch and creating a new commit:

~~~
git switch main
git commit -m "Add order search"
~~~

Git updates the main ref to point to the new commit. The previous commit still exists in history, but the branch has moved forward.

### 2.2. A tag does not automatically advance with a branch

Create a tag at the current commit:

~~~
git tag v1.0.0
~~~

The tag v1.0.0 points to the commit that HEAD refers to at the time of creation. When main receives subsequent commits, the tag stays in place. If you want to mark a new version, create a new tag:

~~~
git tag v1.1.0
~~~

You should not reuse a published version tag to represent different commits. Moving an existing tag causes the same version name to point to different content across machines or build systems.

## 3. Lightweight tags and annotated tags

Git has two common types of tags: lightweight tags and annotated tags.

### 3.1. Lightweight tag

A lightweight tag is a simple ref pointing directly to the tagged object. When used on a commit, it points straight to that commit. It does not create an extra tag object containing separate metadata.

Create a lightweight tag:

~~~
git tag v1.2.0
~~~

Or specify a particular commit:

~~~
git tag v1.2.0 3f2a9c1
~~~

Lightweight tags are useful when you need temporary markers, internal milestones, or a checkpoint that does not require release metadata. However, they do not store the tagger, creation timestamp, tag message, or tag signature.

### 3.2. Annotated tag

An annotated tag creates a separate tag object. This object stores the tagger information, timestamp, message, and tagged object. This is the type generally suitable for marking release versions.

Create an annotated tag:

~~~
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

Explicitly specify a commit:

~~~
git tag -a v1.2.0 3f2a9c1 -m "Release version 1.2.0"
~~~

Annotated tags store the rationale and details of the release milestone right inside Git. You can inspect its contents:

~~~
git show v1.2.0
~~~

For an annotated tag, git show typically displays the tagger information, creation date, message, and tagged commit. For a lightweight tag, git show displays the details of the commit the tag points to.

### 3.3. Comparing the two tag types

| Criterion | Lightweight | Annotated |
|---|---|---|
| Structure | Ref pointing directly to an object | Ref pointing to a tag object |
| Tagger and timestamp | No separate tag metadata | Yes |
| Tag message | No | Yes |
| Tag signature | No separate tag signature | Can be signed |
| Best suited for | Temporary or internal milestones | Release versions and auditable milestones |

When creating official releases, prefer annotated tags to retain release metadata and enable signature verification. Lightweight tags can still be useful in daily work, but they do not provide equivalent metadata.

## 4. Tag naming and versioning conventions

Tag names are strings defined by the team. Git does not enforce Semantic Versioning for tags, though many projects use SemVer to communicate the scope of changes.

### 4.1. Semantic Versioning

A basic SemVer version has the format:

~~~text
MAJOR.MINOR.PATCH
~~~

- **MAJOR:** Incremented when making incompatible changes to the public API or previous behavior.
- **MINOR:** Incremented when adding functionality in a backward-compatible manner.
- **PATCH:** Incremented when making backward-compatible bug fixes.

Examples:

| Version | Illustrative meaning |
|---|---|
| 1.0.0 | First stable release milestone |
| 1.1.0 | Adding compatible features |
| 1.1.1 | Bug fixes, maintaining compatibility |
| 2.0.0 | Major changes that may require users to update their integration |

SemVer is a convention for version semantics. Git only stores the tag name and the object it points to; Git does not automatically validate whether MAJOR, MINOR, or PATCH increments match the actual changes.

### 4.2. Pre-release versions

SemVer supports pre-release labels after a hyphen:

~~~text
2.0.0-alpha.1
2.0.0-beta.1
2.0.0-rc.1
~~~

These labels are commonly used during testing phases:

- alpha: early version where features or interfaces may still change.
- beta: version with broader scope for testing.
- rc: release candidate, a candidate for release if no critical bugs remain.

These are common project interpretations; specific meanings and promotion criteria should be agreed upon by the team. Pre-release versions have lower precedence than the corresponding normal version—for example, 2.0.0-rc.1 precedes 2.0.0 according to SemVer rules.

### 4.3. Choosing a consistent naming convention

Some projects prefix tag names with v:

~~~text
v1.0.0
v1.1.0
v1.1.1
~~~

Some projects use the version number directly:

~~~text
1.0.0
1.1.0
1.1.1
~~~

Both work in Git. What matters is choosing one consistent convention so scripts, pipelines, documentation, and users never have to guess version names.

## 5. Creating, viewing, and finding tags

### 5.1. Listing tags

View all tags:

~~~
git tag
~~~

Filter by pattern:

~~~
git tag -l "v1.*"
~~~

Sort by version:

~~~
git tag --sort=-version:refname
~~~

Version sorting is more useful than standard lexicographical sorting. For example, lexicographical order may place v1.10.0 before v1.2.0 due to character comparison; version sort understands numeric version components.

### 5.2. Inspecting what a tag points to

View tag details and commit:

~~~
git show v1.2.0
~~~

Get the commit SHA that a tag resolves to:

~~~
git rev-parse "v1.2.0^{commit}"
~~~

The `^{commit}` syntax asks Git to resolve the tag to the tagged commit, even when the tag is an annotated tag pointing through a tag object.

You can inspect the object type and the tagged object:

~~~
git cat-file -t v1.2.0
git cat-file -p v1.2.0
~~~

With a lightweight tag, the first command usually returns commit. With an annotated tag, it returns tag, and the second command displays the tag object's metadata along with the target object.

### 5.3. Finding the nearest tag from a commit

The git describe command helps produce a human-readable name for a commit based on the nearest tag in history:

~~~
git describe --tags
git describe --tags --always
~~~

If the current commit is directly at a tag, the output may be just the tag name. If there are newer commits after the nearest tag, the output typically includes the tag name, the number of commits ahead, and an abbreviated SHA.

git describe is useful for displaying development versions in applications or build logs. It relies on reachable tags in the repository and is not the sole source of truth for identifying production artifacts. Pipelines should still record the exact commit SHA.

## 6. Which commit can a tag be created on?

If no commit is specified, git tag defaults to HEAD. However, in release workflows, you should explicitly identify the commit to be tagged.

Example of viewing history:

~~~
git log --oneline --decorate -8
~~~

Create an annotated tag at the chosen commit:

~~~
git tag -a v1.4.0 8d3c2f1 -m "Release version 1.4.0"
~~~

Verify again:

~~~
git show --no-patch --decorate v1.4.0
git rev-parse "v1.4.0^{commit}"
~~~

A tag should point to the commit representing the exact content being released. You should not create a tag with uncommitted changes in the working tree and assume the tag includes those changes. Tags mark objects in history, not uncommitted file states.

A release workflow typically creates a tag after changes have been reviewed and integrated into a release branch or main branch. If the team tags a merge commit, ensure it is a commit that has been tested and qualifies for release.

## 7. Sharing tags with a remote

Newly created local tags do not appear on the remote automatically. You need to push tags so other team members and pipelines can access them.

### 7.1. Pushing a specific tag

~~~
git push origin v1.4.0
~~~

This is the explicit way when you only want to publish a single tag. You can use the full ref:

~~~
git push origin refs/tags/v1.4.0
~~~

### 7.2. Pushing all tags

~~~
git push origin --tags
~~~

This command pushes all local tags to the remote. If the remote already has a tag with the same name pointing to a different object, the update may be rejected. Only use this when you have reviewed the tag list and verified that all of them are safe to share. In larger teams, pushing specific tags is easier to control.

### 7.3. Pushing annotated tags automatically alongside commits

~~~
git push --follow-tags
~~~

The --follow-tags option pushes annotated tags missing from the remote that point to commits reachable by that push. It does not push lightweight tags. Keep this distinction in mind when designing release scripts.

### 7.4. Checking tags on the remote

List tags advertised by the remote:

~~~
git ls-remote --tags origin
~~~

You can filter for a specific name in the shell:

~~~
git ls-remote --tags origin "refs/tags/v1.4.0*"
~~~

For annotated tags, the remote may display both the tag object ref and a peeled ref ending in `^{}` pointing to the tagged object. This is normal: the tag object and the target commit have different SHAs.

After pushing, another machine can retrieve tags via fetch:

~~~
git fetch origin --tags
~~~

Git normally auto-fetches tags associated with fetched commits by default, but --tags requests fetching all tags advertised by the remote. Use this command when you need to synchronize the full tag list.

## 8. Deleting or moving tags

Git allows modifying tags, but published tags should be treated as historical milestones to preserve. Changing a release tag can cause two people using the name v1.4.0 to actually build from two different commits.

### 8.1. Deleting a local tag

~~~
git tag -d v1.4.0
~~~

This command deletes the tag ref in the local repository. It does not automatically delete the tag on the remote, nor does it immediately delete the objects the tag pointed to.

### 8.2. Deleting a tag on the remote

~~~
git push origin --delete v1.4.0
~~~

This operation deletes the tag on the remote. Anyone who already fetched the tag may still retain it locally. Clear communication and sync instructions are necessary if deletion is part of correcting a mistake.

### 8.3. Moving a local tag

You can force-recreate a tag:

~~~
git tag -f -a v1.4.0 <new-commit> -m "Release version 1.4.0"
~~~

The command above modifies the local tag. If the old tag has already been published, do not use this as a quick fix without coordination. Pushing a moved tag to the remote is typically rejected as a non-fast-forward update.

### 8.4. Updating an existing tag on the remote

In exceptional cases, an administrator may delete the old tag on the remote and push the new one, or use a force update per server policy. This operation affects everyone relying on that tag.

If a release has a bug, it is usually better to create a new version, such as v1.4.1, rather than moving a published v1.4.0 tag. This keeps release history transparent and prevents build systems, users, repository clones, and documentation from disagreeing on the same tag name.

## 9. Signed tags and provenance verification

Annotated tags can be signed using a GPG key or another signing mechanism supported by Git. A signature lets recipients verify that the tag was signed by a key they trust and that the tag object content has not been altered after signing.

### 9.1. Creating a signed tag

~~~
git tag -s v1.5.0 -m "Release version 1.5.0"
~~~

If you need to select a specific signing key:

~~~
git tag -u <key-id> v1.5.0 -m "Release version 1.5.0"
~~~

The private key must be protected, and only authorized individuals or systems should have access to use it. Never store private keys inside the repository.

### 9.2. Verifying a signature

~~~
git tag -v v1.5.0
~~~

Git checks the signature according to the configured signing mechanism and displays the verification result. To conclude that a tag is trustworthy, the recipient also needs to know who owns the public key and whether that key belongs to the organization's trusted list. A valid signature from an untrusted key does not prove an authorized releaser.

### 9.3. Tag signatures and server-side tag protection

A signature verifies the tag object content and the signing key identity per trust configuration. It does not prevent someone with permissions from deleting a tag or creating a different tag with the same name on the remote. Combine:

- Server-side release tag protection rules.
- Restricted permissions for creating, deleting, or updating tags.
- Release approval workflows.
- Tag signing and trusted key checks.
- Recording commit SHAs and artifact checksums.

For critical releases, pipelines can verify the signature before building or deploying. This verifies that the release input is a milestone signed by an authorized key.

## 10. How do Tags and Releases differ?

A tag is a Git concept. A release is typically an object provided by a hosting platform or release process, linked to a tag, which may include additional information.

| Component | Role |
|---|---|
| Git tag | Marks a commit or object in the repository |
| Release notes | Describes features, bug fixes, breaking changes, and upgrade instructions |
| Artifact | Build package, binary, container image, or installer file |
| Checksum | Helps verify artifact integrity |
| Signature | Helps verify provenance and integrity against trusted keys |
| Platform release | Combines a tag with descriptions, attached files, timestamps, and release metadata |

Creating a tag does not automatically build the application, generate release notes, or upload artifacts. These steps require a pipeline or release platform.

A release may contain:

- The version name and corresponding tag.
- Release date and release notes.
- Artifacts or links to container images.
- Artifact checksums or signatures.
- Installation, upgrade, and rollback instructions.
- List of changes or closed issues.

## 11. Tagging and release workflow

A controlled release workflow may include:

1. **Lock scope:** Identify the features, fixed bugs, and changes to be released.
2. **Prepare commit:** Integrate reviewed changes into the release branch or main branch.
3. **Verify:** Run tests, security checks, trial builds, and compatibility validation.
4. **Select commit:** Record the exact commit SHA to be released.
5. **Create tag:** Create an annotated or signed tag per policy, using the agreed version name.
6. **Verify tag:** Use git show, git rev-parse, and git tag -v (if signed) to confirm the tag points to the right commit.
7. **Push tag:** Publish the specific tag to the remote.
8. **Build artifacts:** Pipeline builds from the tagged commit, recording checksums and traceability metadata.
9. **Create release:** Attach release notes, artifacts, and upgrade instructions on the release platform.
10. **Deploy and monitor:** Deploy the identified artifact and monitor post-release health, metrics, and logs.

Example:

~~~
git switch main
git fetch origin
git pull --ff-only
git log --oneline --decorate -5
git tag -a v1.4.0 HEAD -m "Release version 1.4.0"
git show v1.4.0
git rev-parse "v1.4.0^{commit}"
git push origin v1.4.0
~~~

This example assumes HEAD has already been reviewed and tested, the main branch is the team's accepted release source, and the tag v1.4.0 does not already exist. In workflows requiring signatures, use a signed tag instead of a regular annotated tag and verify the signature before publishing.

If the pipeline is configured to trigger on new tags, pushing a tag can start a build or deployment. Check pipeline triggers and target environments before publishing a tag, as a tag name may serve as an automated release signal.

## 12. Tags in multi-version maintenance

Some projects must maintain multiple versions in parallel. In that case, branches and tags work together:

~~~text
main:       ---A---B---C---D---E
                 \
release/1.x:      R1---R2
                  |     |
                v1.0.0 v1.0.1
~~~

The release/1.x branch continues receiving bug-fix commits for the 1.x version line. Tags v1.0.0 and v1.0.1 mark individual releases on that line. Meanwhile, main can continue developing the next version.

A workflow might:

- Create a release branch when a version line needs stabilization.
- Only accept approved bug fixes into the release branch.
- Create a new tag after each patch release.
- Port necessary fixes back to main via cherry-pick or merge per policy.
- Clearly document which versions remain supported and their end-of-support dates.

Tags do not replace maintenance branches. Tags mark release milestones; branches allow ongoing development on that version line.

## 13. Common mistakes when working with tags

**Creating a tag while on the wrong branch or wrong commit.** Before tagging, verify the current branch and commit SHA. When needed, specify the commit explicitly instead of relying on HEAD.

**Assuming tags appear on the remote automatically.** Locally created tags must be pushed. Use git ls-remote --tags origin to confirm the tag is published.

**Using tags like branches.** Tags do not advance when new commits are created. If you need to continue development, create or check out an appropriate branch.

**Reusing published tag names.** Moving a tag can cause environments and users to point to different commits. When a release needs fixing, prefer creating a new version.

**Relying solely on tag names to verify artifacts.** Always record the commit SHA, artifact checksum, and pipeline metadata.

**Confusing tags with releases.** A tag marks a Git object; a platform release can add notes and build files. Creating a tag does not mean artifacts have been released.

**Skipping signature or trusted key verification.** A valid signature must be checked against trusted public keys and the organization's authorization policy.

## 14. Tag and release management checklist

**Before creating a tag**

- [ ] Confirmed the correct repository and remote.
- [ ] Identified the release branch and commit SHA to mark.
- [ ] Changes have been reviewed and tested per policy.
- [ ] Version name follows the project's convention.
- [ ] Tag does not exist yet, or there is a clear decision on how to handle it.

**When creating and publishing a tag**

- [ ] Use an annotated tag for release milestones needing metadata.
- [ ] Sign the tag if required by the workflow.
- [ ] Inspect the tag with git show and git rev-parse.
- [ ] Verify the signature and trusted key if applicable.
- [ ] Push the specific tag to the right remote.
- [ ] Confirm the tag appears on the remote.

**When releasing**

- [ ] Build artifacts from the identified commit.
- [ ] Record checksums and traceability information.
- [ ] Prepare release notes and upgrade instructions.
- [ ] Attach artifacts to the release or appropriate registry.
- [ ] Monitor deployment results and have an incident response plan ready.

**After releasing**

- [ ] Keep published tags stable.
- [ ] Protect permissions for creating, deleting, and updating release tags.
- [ ] Create a new version tag for bug-fix releases.
- [ ] Maintain release history and version support status.

## 15. Conclusion

A tag is a named reference used to mark a historical milestone in Git. Branches move with new commits, whereas tags are typically kept fixed to represent an agreed-upon version or checkpoint. Nevertheless, Git still allows deleting or moving tags; immutability comes from team conventions, access controls, and protection policies.

For official releases, annotated tags or signed tags are generally more suitable than lightweight tags because they store metadata and support verification. Confirm the tag points to the right commit, push the tag to the remote, generate artifacts and release notes through a dedicated release process, and keep published tags stable so everyone references the exact same version.

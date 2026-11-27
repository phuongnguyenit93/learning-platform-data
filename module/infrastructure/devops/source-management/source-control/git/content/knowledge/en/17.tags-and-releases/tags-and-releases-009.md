# Boundaries between Git tags, software versions, and platform releases

When a team prepares to ship software to users, people often refer to tags, versions, and releases as if they were a single concept. In Git and release workflows, these three concepts are related but serve distinct roles:

- **A Git tag** is a reference in the repository, typically used to mark a specific commit in history.
- **A software version** is a version label following the project's convention, such as 2.4.1 or 2.5.0-rc.2.
- **A platform release** is a release entry managed by a source code hosting service or distribution system, usually linked to a tag and potentially containing notes, installer files, signatures, checksums, and release metadata.

A project might name a tag v2.4.1, treat it as version 2.4.1, and create a release on GitHub, GitLab, or another platform from that tag. However, Git does not inherently understand a project's versioning policy, and creating a tag does not automatically create a release page across platforms.

After this lesson, you will be able to:

- Distinguish between tags, versions, and releases.
- Explain lightweight tags and annotated tags.
- Create, list, inspect, sign, and share tags.
- Apply versioning conventions such as Semantic Versioning.
- Link a tag to a specific commit and release.
- Handle modifying, deleting, or replacing tags in a controlled manner.

## 1. Three concepts and their boundaries

| Concept | Where is it managed? | Which question does it answer? |
| --- | --- | --- |
| Git tag | In the Git repository, under the refs/tags namespace. | Which historical milestone is marked? |
| Software version | By the project or product's versioning convention. | What version line and level of change is this? |
| Platform release | In a release management service or distribution system. | Which release notes can users read and which packages can they download? |

For example, a team might decide:

- Commit 8f31abc contains the content to be released.
- Tag v2.4.1 points to that commit.
- The published product version is 2.4.1.
- The platform release is titled "Product 2.4.1", with bug-fix notes and installers for Windows, macOS, and Linux.

The tag indicates a position in Git history. The version expresses an identifier per product policy. The release is the distribution bundle of release information for users or deployment systems. A tag can exist without a platform release; a platform can also create a release from an existing tag.

Git stores tags in the repository. Release pages, draft status, attached assets, or a "latest" badge are platform features and can vary across providers. Do not assume a Git command has completed all release tasks.

## 2. What is a Git tag?

A tag is a reference name you can use to locate a Git object, typically a commit. Instead of memorizing a long commit hash, you can use a tag name to refer to an important milestone:

~~~bash
git show v2.4.1
~~~

Tags are commonly placed at milestones such as:

- Released software versions.
- Builds handed off for testing or deployment.
- Stable checkpoints before making major changes.
- Library versions that another application depends on.

Git does not require tags to look like version numbers. You can name tags release-candidate, demo-2026-11, or migration-baseline. However, the team should agree on a naming convention so others understand each tag's purpose.

Tags differ from branches in normal usage. A branch is a reference that moves when new commits are created on it; a tag is typically used as a fixed milestone identifying an object in history. Git still permits moving or deleting tags, so the immutability of release tags relies primarily on team conventions and policies.

## 3. Lightweight tags and annotated tags

Git supports two common types of tags.

### Lightweight tag

A lightweight tag is a simple reference pointing directly to an object, usually a commit. Create the tag:

~~~bash
git tag v2.4.1
~~~

If no commit is specified, the tag is created at the current HEAD. You can specify another commit:

~~~bash
git tag v2.4.1 8f31abc
~~~

Lightweight tags suit internal milestones or temporary markers when the team does not need separate tag metadata. They do not contain a tagger message like annotated tags.

### Annotated tag

An annotated tag creates a separate tag object containing tagger information, timestamp, message, and the tagged object. Create the tag:

~~~bash
git tag -a v2.4.1 -m "Release version 2.4.1"
~~~

Or attach the tag to a specific commit:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

For official release milestones, annotated tags are generally more suitable because they store descriptive details about the release milestone. Many release workflows also require signed tags to verify the creator.

### Comparison

| Characteristic | Lightweight tag | Annotated tag |
| --- | --- | --- |
| Structure | Direct reference to an object. | Has its own tag object. |
| Message | No tag message metadata. | Has a tag message. |
| Tagger and timestamp | Does not store separate tag metadata. | Stores tagger and timestamp. |
| Tag signature | Not signed via the annotated tag mechanism. | Can be signed with the -s or -u options. |
| Common use cases | Temporary markers or simple internal checkpoints. | Official release versions and milestones. |

You can inspect the object type a tag name resolves to:

~~~bash
git cat-file -t v2.4.1
~~~

For a lightweight tag pointing to a commit, the output is usually commit. For an annotated tag, the output is tag. The following command displays the tagged object's contents:

~~~bash
git show v2.4.1
~~~

## 4. A tag must point to the right commit

A release tag must point to the exact content that has been tested and approved. Do not blindly create a tag at HEAD because HEAD may be on a different branch or commit than intended.

Before tagging, inspect:

~~~bash
git status --short --branch
git log --oneline --decorate -n 10
git show --stat 8f31abc
~~~

After confirming the commit:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
git show --no-patch --decorate v2.4.1
~~~

The tag command does not create a commit and does not alter the working tree. It only creates a reference or tag object pointing to the specified object. If a tag points to an older commit, the release represents the content at that commit, not the latest content on the branch.

If the project builds from tagged commits, record the commit hash, tag, and build information in the CI/CD system or release metadata. This helps trace a binary package back to the exact source that produced it.

## 5. Software version naming

Git permits arbitrary tag names; version numbering rules are a product policy. A common convention is **Semantic Versioning (SemVer)** with the structure:

~~~text
MAJOR.MINOR.PATCH
~~~

- MAJOR increments when making incompatible changes to the public API.
- MINOR increments when adding backward-compatible functionality.
- PATCH increments when making backward-compatible bug fixes.

Examples:

| Version | Illustrative meaning |
| --- | --- |
| 2.4.0 | Added backward-compatible functionality in the 2.x line. |
| 2.4.1 | Backward-compatible bug fix for version 2.4.0. |
| 2.5.0 | Added new features compatible with the 2.x API. |
| 3.0.0 | Changed the public API in a way incompatible with 2.x. |

SemVer describes the meaning of version numbers based on a public API. For applications without a public API or products using date-based release calendars, a team may choose a different convention; what matters is documenting the rules and applying them consistently.

### Pre-release versions

A version may carry a prerelease identifier:

~~~text
2.5.0-alpha.1
2.5.0-beta.2
2.5.0-rc.1
~~~

Labels like alpha, beta, and rc typically denote testing stages prior to a stable release. Under SemVer, a version with a prerelease portion has lower precedence than the corresponding official release version. For example, 2.5.0-rc.1 is lower than 2.5.0.

### Build metadata

SemVer allows appending metadata after a plus sign:

~~~text
2.5.0+build.184
~~~

Build metadata can record build numbers or environment details. Per SemVer rules, this metadata does not affect version precedence. Do not use build metadata as a substitute for prerelease identifiers when distinguishing test builds from stable releases.

### The v prefix in Git tags

Many projects name tags v2.5.0 instead of 2.5.0. The letter v is a tag naming convention; it is not a required part of SemVer. Standardize on one convention in the repository and release tooling to avoid creating both v2.5.0 and 2.5.0 for the same release.

Git does not automatically check whether a tag complies with SemVer. Git treats tag names as strings; parsing and comparing versions must be handled by appropriate workflows or tools.

## 6. Listing, searching, and comparing tags

List tags:

~~~bash
git tag
~~~

Filter tags by pattern:

~~~bash
git tag -l "v2.*"
git tag -l "*-rc.*"
~~~

View tag details:

~~~bash
git show v2.4.1
git show --no-patch --format=fuller v2.4.1
~~~

Sort in version order:

~~~bash
git tag --sort=-version:refname
~~~

Sorting by version makes numeric tags easier to read than standard alphabetical sorting. Still, results depend on tag naming; maintain consistent conventions to prevent confusing orderings.

View commits between two milestones:

~~~bash
git log --oneline v2.3.0..v2.4.1
~~~

The command above lists commits reachable from v2.4.1 but not reachable from v2.3.0. You can inspect content changes:

~~~bash
git diff v2.3.0..v2.4.1
~~~

If you want to view changes since the common branching point between two milestones:

~~~bash
git diff v2.3.0...v2.4.1
~~~

Choose the comparison operator based on your question: comparing the two endpoint trees or inspecting one side's changes since their merge base.

## 7. Checking where a tag points

To obtain the commit ID a tag resolves to:

~~~bash
git rev-parse v2.4.1^{commit}
~~~

In some shells, special characters in the expression may need to be quoted:

~~~bash
git rev-parse "v2.4.1^{commit}"
~~~

To compare against a branch's commit:

~~~bash
git rev-parse main
git rev-parse "v2.4.1^{commit}"
~~~

Both commit IDs match when the tag points to the exact tip commit of main at the time of inspection. However, main may keep moving after a release; therefore, do not expect a tag to always equal the HEAD of an active branch.

To describe the latest commit using the nearest tag:

~~~bash
git describe --tags
~~~

You can add `--dirty` to flag a working tree with uncommitted changes, or `--always` as a fallback when no matching tag is found:

~~~bash
git describe --tags --dirty --always
~~~

This command is commonly used in build scripts to generate version strings from Git history. Results depend on tags present in the local repository; in a shallow clone or before fetching tags, the output may be incomplete.

## 8. Signing and verifying tags

For releases requiring provenance verification, teams can use signed tags. Create a signed tag:

~~~bash
git tag -s v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Depending on configuration, Git uses the configured signing key, typically via GPG or another supported signing mechanism. If you need to select a specific key, use the `-u` option with the appropriate key identifier:

~~~bash
git tag -u KEY-ID v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Verify the signature:

~~~bash
git tag -v v2.4.1
~~~

The verification output indicates whether the signature is valid according to the key used. Recipients still need a basis to trust that key, such as a key verified through an internal channel or an official release key list. A valid signature only verifies the signed content and signing key; it does not by itself prove the source code is safe or that build artifacts were not substituted.

If a team has not configured tag signing, annotated tags can still be used to record the creator and message. Platform tag protection policies can also restrict who is allowed to create, update, or delete release tags.

## 9. Sharing tags with a remote

Unlike branches, which are pushed by default in many situations, tags are not always sent to the remote when you push a branch. Actively share release tags.

Push a specific tag:

~~~bash
git push origin v2.4.1
~~~

Push all local tags:

~~~bash
git push origin --tags
~~~

The `--tags` command may send internal or experimental tags you did not intend to publish. Before using it, inspect the tag list and repository policy.

If you want to push a branch along with annotated tags reachable from the commits being pushed:

~~~bash
git push --follow-tags
~~~

`--follow-tags` only adds matching annotated tags along the history of the pushed refs; it is not equivalent to sending all local tags.

Check tags advertised by the remote:

~~~bash
git ls-remote --tags origin
~~~

This command queries tag references on the remote without updating them locally. After fetching tags:

~~~bash
git fetch origin --tags
~~~

Tags are stored in the refs/tags namespace, not as remote-tracking branches like origin/main. Therefore, there is no `origin/v2.4.1` concept analogous to `origin/main` in standard usage.

## 10. Git tags and platform releases

Once a tag has been pushed to the remote, the team can create a release on the source hosting platform or release system. A release typically contains:

- A tag or commit as the content source.
- A human-readable release title, e.g. Product 2.4.1.
- Release notes describing new features, fixed bugs, and impactful changes.
- Binary files, installer packages, container images, or release documentation.
- Checksums and signatures so users can verify downloaded files.
- Draft, prerelease, or published status depending on the platform.

Example workflow on a Git hosting platform:

1. Create tag v2.4.1 at a tested commit.
2. Push the tag to origin.
3. Open the platform's Releases page or release management UI.
4. Create a release based on tag v2.4.1.
5. Write notes, attach artifacts, and review details.
6. Publish the release per team permissions and process.

Creating a platform release is not a standard Git command. Depending on the provider, it may be done via web UI, CLI, API, or CI/CD pipelines. Field names, statuses, and file attachment capabilities also vary.

A release can point to an existing tag. If the platform allows creating the release and tag simultaneously, verify which commit the tag is created on before publishing. Avoid letting the UI automatically create a new tag from the default branch when you intend to release a different commit.

## 11. Release workflow from commit to release

A simple workflow can be broken into steps:

~~~text
Select approved commit
          |
          v
Inspect history and working tree
          |
          v
Create annotated or signed tag
          |
          v
Verify tag and target commit
          |
          v
Push tag to remote
          |
          v
CI/CD builds and verifies artifacts
          |
          v
Create release notes and attach artifacts
          |
          v
Publish per team workflow
~~~

Example commands in the repository:

~~~bash
# Check status
git status --short --branch

# Verify the commit to release
git show --stat 8f31abc

# Create an annotated tag at that commit
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"

# Inspect tag and commit
git show --no-patch --decorate v2.4.1
git rev-parse "v2.4.1^{commit}"

# Share tag
git push origin v2.4.1
~~~

After the pipeline builds artifacts, store checksums and build metadata per release policy. Release notes should accurately reflect what is in the tag; if needed, generate notes from the commit list between two tags:

~~~bash
git log --oneline v2.4.0..v2.4.1
~~~

Do not automatically treat every commit in this range as a user-facing change. Curate and review notes by features, bug fixes, compatibility changes, and notable issues.

## 12. Published tags should be treated as stable milestones

Git allows moving tags, but published tags are normally treated as immutable milestones by convention. If tag v2.4.1 initially pointed to commit A and was later moved to commit B, users might have downloaded artifacts built from A while the repository shows the tag pointing to B. This breaks traceability.

Do not modify a published release tag just to point it to a newer commit. If a bug is found, usually create the next version, such as v2.4.2, and release new artifacts and fix notes. This preserves the audit trail of the older version.

If a tag is strictly an unshared internal tag whose position needs fixing, you can update it locally with:

~~~bash
# Move lightweight tag to a new commit
git tag -f v2.4.1 8f31abc

# Move annotated tag while retaining annotated metadata
git tag -fa v2.4.1 8f31abc -m "Release version 2.4.1"
~~~

Only do this when you clearly understand the tag is being moved and no one else relies on it yet. The `-f` option overwrites the local tag; add `-a` to keep the tag as annotated. If the tag already exists on the remote, updating the remote requires dedicated permissions and procedures; do not treat force-pushing a tag as a routine edit.

## 13. Deleting or replacing tags

Delete a local tag:

~~~bash
git tag -d v2.4.1
~~~

Delete a tag on the remote:

~~~bash
git push origin --delete v2.4.1
~~~

An alternative syntax to delete the ref on the remote:

~~~bash
git push origin :refs/tags/v2.4.1
~~~

Deleting a tag does not delete the commit it points to. The commit may still be retained by branches, other tags, or other referencing objects.

If you need to rename a tag, Git has no direct tag rename operation. The usual process is creating a new tag at the same commit, verifying the new tag, sharing the new tag, and then deleting the old tag per policy:

~~~bash
git tag -a v2.4.1 8f31abc -m "Release version 2.4.1"
git show v2.4.1
git push origin v2.4.1
~~~

If the old tag was already used in a public release, consider keeping it intact and explaining via release notes or issuing a bug-fix version. Deleting an old tag can break download links, deployment scripts, or references in user documentation.

## 14. Useful commands when working with tags

| Purpose | Command |
| --- | --- |
| List tags | git tag |
| Filter tags by pattern | git tag -l "v2.*" |
| Create lightweight tag | git tag v2.4.1 |
| Create annotated tag | git tag -a v2.4.1 -m "Release version 2.4.1" |
| Create signed tag | git tag -s v2.4.1 -m "Release version 2.4.1" |
| View tag | git show v2.4.1 |
| Verify signature | git tag -v v2.4.1 |
| Find nearest tag | git describe --tags |
| Sort by version | git tag --sort=-version:refname |
| Push one tag | git push origin v2.4.1 |
| Push all local tags | git push origin --tags |
| Fetch tags | git fetch origin --tags |
| View tags on remote | git ls-remote --tags origin |
| Delete local tag | git tag -d v2.4.1 |
| Delete remote tag | git push origin --delete v2.4.1 |

## 15. Common misconceptions

### Creating a tag means creating a release

Incorrect. A tag is a reference in Git. A platform release is a separate release entry that can link to a tag and hold metadata or artifacts.

### Git inherently understands version numbers

Incorrect. Git stores tag names as strings. Rules for MAJOR.MINOR.PATCH, prereleases, and build metadata belong to the project's versioning policy.

### Every tag has a message and creator

Incorrect. A lightweight tag is just a simple reference. Only annotated tags have dedicated tag metadata.

### Tags are always immutable

Technically incorrect. Git allows moving and deleting tags. Release tag immutability must be enforced through conventions, permissions, and processes.

### Pushing a branch always pushes related tags

Do not assume this. Push specific tags, use `--follow-tags` when appropriate, or push `--tags` after reviewing the tag list.

### A tag signature proves artifacts are safe

A signature verifies that the tag object was signed by the corresponding key. It does not by itself verify the entire pipeline, dependencies, binaries, or deployment environment. Artifacts require their own checksums, signatures, and verification processes if the product demands them.

## 16. Key takeaways

- A Git tag marks an object in history; a software version is a convention-based identifier; a platform release is a release entry with metadata and artifacts.
- A lightweight tag is a simple reference; an annotated tag stores creator, timestamp, and message information.
- For official versions, teams generally choose annotated tags and may require signed tags.
- A tag must point to the exact commit that has been tested and approved.
- SemVer defines the meaning of MAJOR, MINOR, PATCH, and prereleases; Git does not enforce these rules automatically.
- Pushing tags to a remote is a separate step; creating a tag does not automatically create a platform release.
- Treat published release tags as stable milestones. When bugs occur, typically release a new version to preserve traceability.
- Release notes, artifacts, checksums, and signatures must reflect the exact commit/tag released.

By clearly distinguishing between Git tags, versions, and releases, a team can trace a release back to the exact commit, explain what a version means, and deliver verifiable artifacts. These three components work together in the release workflow, yet each retains its own lifecycle and responsibilities.

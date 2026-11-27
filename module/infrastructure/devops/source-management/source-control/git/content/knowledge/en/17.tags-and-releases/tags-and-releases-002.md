# Creating lightweight tags and annotated tags

A tag is a named label attached to a Git object, typically a commit. Tags help mark important milestones such as release versions, tested builds, or reference points in history. Unlike a branch, a tag normally does not move with new commits: it remains on the marked milestone until a user actively modifies or deletes it.

Git has two common types of tags: **lightweight tags** and **annotated tags**. Both give a name to a point in history, but how Git stores them and how much information accompanies them differ. Understanding this difference helps you choose the right tag type when marking versions and sharing release milestones with your team.

## 1. What is a Tag?

A tag is a named reference in the `refs/tags/` namespace. For example, the tag `v1.2.0` typically points to the commit containing the source code for version 1.2.0.

Consider a repository with the following history:

~~~text
A---B---C---D---E  main
        ^
        |
      v1.0.0
~~~

The tag `v1.0.0` marks commit `C`. When the `main` branch continues gaining commits `D` and `E`, the tag still points to `C`. This is an important difference from a branch: a branch is a reference that moves with new commits when you commit on that branch, whereas a tag is typically used as a fixed milestone.

A tag is not a copy of the repository, nor does it create a new commit in the development history. Creating a tag only adds a reference or a tag object, depending on the tag type chosen.

## 2. Distinguishing lightweight tags and annotated tags

Git provides two ways to create a tag:

| Characteristic | Lightweight tag | Annotated tag |
|---|---|---|
| Storage | A ref pointing directly to the tagged object, usually a commit | Creates a separate tag object that points to the target object |
| Creator information | Does not store separate tag metadata | Includes tagger, creation timestamp, and message |
| Descriptive message | None | Yes |
| Cryptographic signature | None inside the tag | Can be signed with GPG/SSH depending on configuration |
| Common use cases | Temporary markers or personal checkpoints | Marking versions, releases, or milestones needing official sharing |

### Lightweight tag

A lightweight tag is like a simple reference label. Git creates a ref under `refs/tags/` pointing directly to the specified object. If the tag is created on a commit, the ref points straight to that commit.

Example:

~~~bash
git tag v1.2.0
~~~

This command creates the tag `v1.2.0` at the current commit (HEAD). Git does not create a tag object and does not record a tagger or accompanying message.

### Annotated tag

An annotated tag creates a dedicated tag object. This object contains the target object type, tag name, tagger information, timestamp, and message. The tag can be digitally signed so recipients can verify its origin.

Example:

~~~bash
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

The `-a` option instructs Git to create an annotated tag; `-m` provides the message. If `-m` is omitted, Git opens the text editor to enter the content.

For official releases, an annotated tag is generally more suitable because it stores descriptive information about the release milestone and can be digitally signed. Lightweight tags are suitable for personal labels or simple checkpoints when metadata is unnecessary.

## 3. Creating a lightweight tag at the current commit

Before creating a tag, verify that you are in the right repository and on the intended commit:

~~~bash
git status
git branch --show-current
git log -1 --oneline
~~~

If you want to mark the current commit with a lightweight tag:

~~~bash
git tag v1.2.0
~~~

Running the command without `-a`, `-s`, or `-m` creates a lightweight tag. To inspect the tag you just created:

~~~bash
git tag --list
git show v1.2.0
~~~

`git show` displays the object the tag points to. For a lightweight tag pointing to a commit, the output typically shows the commit information and its corresponding diff.

If the tag name already exists, Git refuses to create a duplicate tag. Check existing tags before deciding to use another name or update the tag.

## 4. Creating an annotated tag at the current commit

To mark a version with a message:

~~~bash
git tag -a v1.2.0 -m "Release version 1.2.0"
~~~

You can include useful details in the message, for example:

~~~bash
git tag -a v1.2.0 -m "Release 1.2.0

- Add payment retry handling
- Improve report export
- Fix session timeout"
~~~

An annotated tag's message serves as descriptive context attached to the version milestone. Keep the content concise, searchable, and aligned with the project's release notes.

If you want to enter the message using an editor:

~~~bash
git tag -a v1.2.0
~~~

Git opens the editor configured via `core.editor` or the corresponding environment variable. Save and close the editor to finish creating the tag.

## 5. Creating a tag for a specific commit

You do not have to check out the commit you want to mark. You can pass a commit hash or a reference expression as an argument:

~~~bash
git log --oneline --decorate -8
git tag -a v1.2.0 4f8c2a1 -m "Release version 1.2.0"
~~~

In the example, `4f8c2a1` is an illustrative commit hash. Replace it with the actual hash from your repository.

You can use a branch name, tag, or Git revision expression:

~~~bash
git tag -a v1.2.0 main -m "Release version 1.2.0"
git tag -a v1.1.1 "v1.1.0^{}" -m "Release version 1.1.1"
~~~

The second example uses the `^{}` expression to peel an annotated tag down to its target object. Quotes ensure the revision expression is passed intact to Git in shells with special character parsing rules. In practice, using a verified commit hash remains the simplest and clearest approach.

For a lightweight tag, the syntax is similar:

~~~bash
git tag v1.2.0 4f8c2a1
~~~

Key reminder: the tag is created at the specified commit, not necessarily HEAD. Before marking a release, verify that the commit includes the exact changes intended for release.

## 6. Creating a digitally signed tag

Annotated tags can be digitally signed so recipients can verify the tag was created by the owner of the corresponding key. Git supports signing tags with GPG or SSH depending on the Git version and configuration.

Sign a tag with GPG:

~~~bash
git tag -s v1.2.0 -m "Signed release version 1.2.0"
~~~

The `-s` option creates a signed annotated tag. If you have multiple keys, you can specify the signing key with `-u`:

~~~bash
git tag -s -u <key-id> v1.2.0 -m "Signed release version 1.2.0"
~~~

To verify a signature:

~~~bash
git tag -v v1.2.0
~~~

Successful verification indicates the signature is valid according to a key trusted by your environment. The team still needs to distribute and verify the releaser's fingerprint/public key through a trusted channel. A valid signature does not by itself prove that the release content is secure or has passed review.

If no signing key is configured, the signing command will fail with an error. You can use an unsigned annotated tag when project policy does not require signatures.

## 7. Viewing, searching, and filtering tags

List all tags:

~~~bash
git tag
~~~

List tags along with the first few lines of the annotated tag message:

~~~bash
git tag -n
git tag -n99
~~~

Search tags by pattern:

~~~bash
git tag --list "v1.*"
git tag --list "v*"
~~~

Sort by version name:

~~~bash
git tag --sort=-version:refname
~~~

Version sorting places `v1.10.0` before `v1.9.0` in version order, rather than comparing characters lexicographically. If the project uses a custom naming convention, use an appropriate filter pattern.

Inspect the contents of a tag:

~~~bash
git show v1.2.0
~~~

Check which commit a tag points to:

~~~bash
git rev-parse v1.2.0
git rev-parse "v1.2.0^{commit}"
~~~

For an annotated tag, the first command returns the object ID of the tag object, whereas the `^{commit}` expression asks Git to resolve the tag to the marked commit (if the tag ultimately points to a commit).

You can inspect tag references in the repository:

~~~bash
git show-ref --tags
~~~

## 8. Inspecting tag types and internal structure

You can use `git cat-file` to distinguish between the two tag types.

For a lightweight tag pointing to a commit:

~~~bash
git cat-file -t v1.2.0
~~~

The output is typically:

~~~text
commit
~~~

For an annotated tag:

~~~bash
git cat-file -t v1.2.0
~~~

The output is:

~~~text
tag
~~~

This happens because a lightweight tag points straight to a commit object, while an annotated tag points to a dedicated tag object.

To inspect the contents of a tag object:

~~~bash
git cat-file -p v1.2.0
~~~

Illustrative output:

~~~text
object 4f8c2a1...
type commit
tag v1.2.0
tagger Nguyen Van A <dev@example.com> 1794900000 +0700

Release version 1.2.0
~~~

The hash, tagger name, email, and timestamp above are examples only. For a signed tag, the object contents also include the signature block.

You can check the object type a ref points to using `git cat-file -t`, instead of guessing solely from the tag name or versioning scheme.

## 9. Sharing tags to a remote

Tags created in a local repository are not automatically pushed to the remote just by running `git push origin main`. You must specify the tag or use an appropriate option.

Push a specific tag:

~~~bash
git push origin v1.2.0
~~~

Push all local tags:

~~~bash
git push origin --tags
~~~

The `--tags` option requests pushing all local tags to the remote. If the remote already has a tag with the same name pointing to a different object, Git generally rejects updating that tag rather than overwriting it automatically; inspect and handle it separately if project policy permits replacement. Only use this when you genuinely want to share the entire set of tags, as a repository may contain experimental or personal tags.

Push annotated tags reachable from the commits being pushed:

~~~bash
git push --follow-tags origin main
~~~

`--follow-tags` automatically pushes annotated tags missing from the remote that point to objects reachable from the refs being pushed. It does not push all local lightweight tags. This is a useful option when pushing a release branch along with its related annotated tags.

After pushing, check tags on the remote:

~~~bash
git ls-remote --tags origin
~~~

For an annotated tag, the output may have two lines: the tag object ref and a line with the `^{}` suffix representing the object the tag peels to, usually a commit. A lightweight tag usually has only a ref line pointing directly to the commit.

## 10. Fetching tags from a remote

When you need to retrieve tags from a remote:

~~~bash
git fetch origin --tags
~~~

This command downloads tags from the `origin` remote and the required objects. You can verify:

~~~bash
git tag --list
git show v1.2.0
~~~

Normally, `git fetch` also retrieves tags pointing to downloaded objects via auto-follow rules. `--tags` requests fetching all tags from the remote, including tags that do not point to objects fetched via the branch refspec.

In a standard repository clone, Git usually retrieves tags associated with the cloned history. In certain custom fetch configurations or shallow clones, the set of tags may differ; check with `git tag` and fetch further as needed.

## 11. Checking out a tag and creating a branch from a tag

A tag is a reference milestone, not a working branch. When switching directly to a tag:

~~~bash
git switch --detach v1.2.0
~~~

HEAD enters a detached state (not attached to any branch). You can inspect the source code at that exact version and run tests. If you create new commits in this state without creating a branch, those commits can be difficult to find again once you switch elsewhere.

If you want to continue development or fix a bug from that version, create a new branch:

~~~bash
git switch -c hotfix/1.2.x v1.2.0
~~~

The `hotfix/1.2.x` branch starts at the commit marked by the `v1.2.0` tag. New commits move the hotfix branch forward, while the tag remains at the original milestone.

## 12. Deleting local and remote tags

Delete a tag in the local repository:

~~~bash
git tag -d v1.2.0
~~~

This command only deletes the local tag ref; it does not delete the tag on the remote.

Delete a tag on the remote:

~~~bash
git push origin --delete v1.2.0
~~~

Or use a refspec with an empty source:

~~~bash
git push origin :refs/tags/v1.2.0
~~~

Deleting a published tag can impact users, pipelines, documentation, or deployment systems referencing that version. Coordinate with your team before deleting a public tag.

## 13. Updating or replacing a tag

Git allows moving a local tag with `-f`:

~~~bash
git tag -f v1.2.0 <new-commit>
~~~

For an annotated tag, recreate the tag with the same name and a new message:

~~~bash
git tag -f -a v1.2.0 <new-commit> -m "Corrected release tag"
~~~

If the tag already exists on the remote, a normal push usually refuses to update an existing tag. You can force push:

~~~bash
git push --force origin refs/tags/v1.2.0
~~~

This replaces a published milestone. Other users may have already fetched the old tag and will not automatically know it was moved. For release versions, safe practice is not to modify or reuse published tag names; if a fix is needed, create a new version such as `v1.2.1` and explain it in the release notes.

If replacing a tag is unavoidable per project policy, clearly announce the old and new hashes, the reason for the change, how users can update their local tags, and the impact on pipelines or published artifacts.

## 14. Sample workflow for tagging a version

Suppose the team is preparing to release `v2.0.0` from the `main` branch.

**Step 1 — Check repository state and release commit**

~~~bash
git status
git switch main
git pull --ff-only
git log -1 --oneline
~~~

Ensure the working tree is clean and the current commit has passed all required checks.

**Step 2 — Create an annotated tag**

~~~bash
git tag -a v2.0.0 -m "Release version 2.0.0"
~~~

If the project requires tag signing, use `git tag -s` and verify with `git tag -v`.

**Step 3 — Inspect the tag**

~~~bash
git show v2.0.0
git cat-file -t v2.0.0
~~~

For an annotated tag, the object type will be `tag`. Confirm the tag points to the right commit and the message accurately describes the version.

**Step 4 — Push the tag to the remote**

~~~bash
git push origin v2.0.0
~~~

**Step 5 — Confirm the remote received the tag**

~~~bash
git ls-remote --tags origin v2.0.0
~~~

Once the tag is shared, the team can create a release on the Git hosting platform, attaching release notes and corresponding build artifacts. The tag marks the source commit; the release page and artifacts are supplemental items managed by the platform or release workflow.

## 15. Common errors when working with tags

| Situation | Common cause | Resolution |
|---|---|---|
| `fatal: tag 'v1.2.0' already exists` | Tag name already exists locally | Inspect with `git show v1.2.0`; choose a new name or update only when intentional |
| Tag push rejected because tag already exists | Remote already has a tag with the same name; Git does not overwrite automatically | Verify the remote tag; prefer creating a new version |
| Tag does not appear after pushing a branch | Pushing a branch does not automatically send all tags | Push the specific tag, `--tags`, or `--follow-tags` |
| Cannot see a teammate's tag | Tag has not been fetched or custom fetch refspec is configured | Run `git fetch origin --tags` |
| `git describe` does not recognize the desired tag | By default the command may only consider annotated tags | Use `git describe --tags` if you want to include lightweight tags |
| Checked out a tag and committed, but commit does not show on any branch | HEAD is detached | Create a branch with `git switch -c <branch> <tag>` before developing |

When encountering an error, check the tag name, tag type, target commit, and local/remote state before deleting or overwriting anything.

## 16. Key takeaways

- A lightweight tag is a simple ref pointing directly to an object; an annotated tag creates a tag object with a tagger, timestamp, and message.
- Use `git tag <name>` to create a lightweight tag at HEAD.
- Use `git tag -a <name> -m "<message>"` to create an annotated tag.
- You can pass a commit hash or revision to attach a tag to a specific commit.
- Annotated tags are suitable for marking releases; signed tags enable signature verification if the team manages trusted keys.
- Use `git show`, `git tag --list`, `git cat-file -t`, and `git ls-remote --tags` to inspect tags.
- Local tags are not automatically pushed with branches; explicitly push tags or choose `--tags` / `--follow-tags`.
- Checking out a tag results in a detached HEAD; create a branch from the tag if you need to continue committing.
- Avoid moving or reusing published release tags. Creating a new version tag keeps release history stable and easy to audit.

A tag is a named milestone enabling team members and release systems to reference the exact same version. When using annotated tags for releases and sharing tags deliberately, a team can preserve the provenance, description, and integrity of each release milestone.

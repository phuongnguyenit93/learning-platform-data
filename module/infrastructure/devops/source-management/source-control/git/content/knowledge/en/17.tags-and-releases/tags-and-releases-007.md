# Changing or deleting local tags, remote tags, and coordinating with users who fetched them

A tag is a reference label pointing to a Git object, typically used to mark a version or release milestone. When a tag is created by mistake, points to the wrong commit, or needs to be removed, you can change or delete the tag locally and on the remote. However, tags that teammates have already fetched or that are tied to a release must be handled with coordination: changing a tag on the server does not automatically update the copies others hold.

## 1. What does a tag point to?

A tag is a named ref, usually under `refs/tags/`. Unlike a branch, a tag is typically used as a fixed milestone referencing a commit, such as `v1.2.0` or `release-2026-11`.

Git has two common tag types:

| Tag type | Characteristics |
|---|---|
| Lightweight tag | Direct ref pointing to an object, usually a commit; does not create a separate tag object |
| Annotated tag | Creates a tag object containing tagger, timestamp, message, and optionally a signature; the tag object points to a commit or another Git object |

Annotated tags are generally suitable for releases because they carry descriptive information and can be signed to verify provenance. Lightweight tags are useful for local labels or temporary milestones.

Inspect local tags:

```bash
git tag --list
git tag --list "v1.*"
git show-ref --tags
```

Inspect a specific tag:

```bash
git show v1.2.0
```

For an annotated tag, `git show` displays the tag metadata along with the contents of the referenced commit. For a lightweight tag, the command displays the object the ref points to directly.

## 2. Identifying where a tag points before making changes

Before changing or deleting a tag, verify the exact name and target commit:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
git cat-file -t v1.2.0
```

- `git show` helps inspect the tag and referenced commit.
- `git rev-parse "v1.2.0^{}"` resolves the tag to its final target object; for an annotated tag, this expression peels the tag object to retrieve the labeled commit.
- `git cat-file -t` shows the object type the ref points to directly, typically `tag` for an annotated tag or `commit` for a lightweight tag.

You can check tags on the remote without fetching the whole repository:

```bash
git ls-remote --tags origin
git ls-remote --tags origin v1.2.0
```

For an annotated tag, the output usually has two lines: one for the tag object and one with a `^{}` suffix for the peeled target object. This helps compare local tags with tags on the server.

Do not rely solely on tag names. Two repositories can both have `v1.2.0` while the tags point to two different commits.

## 3. Changing a local tag

Git does not edit an existing tag object in place. When you want to point a local tag to a different commit, you update the tag ref to point to the new object. Use `-f` (`--force`) to allow replacing a tag with the same name.

### 3.1. Updating a lightweight tag

Example moving `v1.2.0` to a new commit:

```bash
git tag -f v1.2.0 <new-commit>
```

This command updates the local `v1.2.0` tag to point to `<new-commit>`. Replace the placeholder with a verified hash or ref. If the target argument is omitted, Git uses `HEAD` as the target.

### 3.2. Recreating an annotated tag

To replace an annotated tag and create a new tag object:

```bash
git tag -f -a -m "Release v1.2.0" v1.2.0 <new-commit>
```

The new tag object has new metadata and message. If the old tag was signed, recreating the tag generates a new signature; the old signature will no longer verify the new tag.

If the organization requires signed tags, use the configured signing workflow, such as `-s` instead of `-a`, and confirm the right signing key before publishing.

### 3.3. Verifying after changing

After updating, confirm the tag points to the right commit:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
git cat-file -t v1.2.0
```

Verify the tag name, target commit, message, and signature (if any). Changing a local tag does not modify the tag on the remote, nor does it automatically update tags on teammates' machines.

## 4. Deleting a local tag

To delete a local tag:

```bash
git tag -d v1.2.0
```

This command deletes the `refs/tags/v1.2.0` ref in the current repository. It does not delete the commit the tag pointed to, does not delete the tag on the remote, and does not affect tag copies in other repositories.

Verify the tag has been removed from the local list:

```bash
git tag --list v1.2.0
```

If there is no output, the tag is no longer in the local tag list. The commit may still be retained by branches, other tags, the reflog, or other refs.

## 5. Pushing a new tag to a remote

Tags are not automatically pushed in every normal `git push` operation. To send a specific tag:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Or use the shorter form when pushing a specific tag:

```bash
git push origin v1.2.0
```

Specify the exact tag rather than using `git push --tags` if you only want to publish one milestone. `--tags` may push all local tags missing from the remote, including temporary or unreviewed tags.

Check the tag after pushing:

```bash
git ls-remote --tags origin v1.2.0
```

Compare the object ID and peeled commit against the local tag to confirm the server holds the expected tag.

## 6. Changing an existing tag on a remote

Changing a published tag rewrites a reference milestone on the server. It can cause pipelines, release packages, checksums, documentation, and user machines to point to different content under the exact same version name.

By safe convention, published release tags should be treated as immutable. If a `v1.2.0` release is found to be faulty, the better option is usually to create a new fix release, such as `v1.2.1`, with a clear commit and release notes. Keeping the old tag lets everyone identify the exact content previously released.

Only change a remote tag when your organization permits it and everyone relying on the tag has been notified and aligned. Before updating, inspect both local and remote:

```bash
git show --no-patch --decorate v1.2.0
git ls-remote --tags origin v1.2.0
```

After updating the local tag and confirming the right target object, you can update the ref on the remote via force push with an explicit refspec:

```bash
git push --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

`--force` allows replacing an existing tag on the remote. This command may be rejected by the server due to permissions or tag protection policies. Do not use it as the default fix for a published release tag.

After updating, verify the tag from the server again:

```bash
git ls-remote --tags origin v1.2.0
```

Check both the tag object line and the peeled `^{}` line if the tag is annotated. Cross-check against local output to ensure the remote tag points to the right commit.

## 7. Deleting a tag on a remote

Deleting a local tag and deleting a remote tag are two independent operations. To delete a tag on the `origin` remote:

```bash
git push origin --delete refs/tags/v1.2.0
```

An equivalent refspec form is:

```bash
git push origin :refs/tags/v1.2.0
```

Both approaches instruct the server to delete the tag ref. They do not delete your local tag or anyone else's. Afterward, verify:

```bash
git ls-remote --tags origin v1.2.0
```

If there is no output, the remote is no longer advertising that tag at the time of the query. Some servers enforce tag protection policies or deletion restrictions; in that case, follow your repository administration procedure.

## 8. What will users who already fetched the tag see?

Tags are not like remote-tracking branches. When someone fetches a tag, Git creates a local tag ref in their repository, such as `refs/tags/v1.2.0`. This local ref does not automatically move when the tag on the server is changed or deleted.

### 8.1. Remote tag is deleted

If the remote deletes `v1.2.0`, someone who fetched the tag earlier will still see it locally:

```bash
git tag --list v1.2.0
```

That is because deleting a ref on the remote does not broadcast a local ref deletion to all clones. Users must verify the team's announcement before deleting their local tag:

```bash
git tag -d v1.2.0
```

Then, if you need to confirm the tag is gone from the remote, query again:

```bash
git ls-remote --tags origin v1.2.0
```

`git fetch --prune --prune-tags origin` can synchronize pruning local tags against the set advertised by the remote, but be careful: depending on refspecs and fetch configuration, this operation can delete local-only tags that do not exist on the remote. Review your configuration and tag list before running it, especially in repositories with private local-only tags.

### 8.2. Remote tag is moved to a different commit

If `v1.2.0` was fetched previously and the remote later moves the tag to a new commit, the user's machine still retains the old local ref. A normal fetch may refuse to update an existing tag or warn that the tag would clobber, because Git does not automatically overwrite existing local tags.

After confirming with the team that the tag was moved intentionally, users can delete the old local tag and re-fetch the new one:

```bash
git tag -d v1.2.0
git fetch origin tag v1.2.0
```

Or use force fetch for that specific verified tag ref:

```bash
git fetch --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Then verify again:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse "v1.2.0^{}"
```

Do not run force fetch or delete local tags simply because you noticed a mismatch. Make sure the tag change announcement is official and the new target commit has been verified.

### 8.3. Users who created a branch or checked out from the old tag

If someone already created a branch from the old commit or is in detached HEAD state at the old tag, changing the tag does not move their branch or HEAD. A tag is just a named ref; checked-out branches and commits retain their relationship with the commit they previously pointed to.

If they need to switch to the new content, they must actively update their branch or check out the new commit following team instructions. Do not assume updating a local tag automatically changes the working source code.

## 9. Coordination workflow when a release tag must be changed or deleted

Before changing a published tag, the release owner should clearly announce:

1. The affected tag name, e.g. `v1.2.0`.
2. The current object ID and target commit on the remote.
3. The reason for changing or deleting the tag and the new target commit, if any.
4. The execution time and responsible owner.
5. Instructions for users who fetched the tag, pipelines, or deployment environments using that tag.
6. The replacement tag if applicable, along with updated release notes.

Users who already downloaded the tag need to verify the details before deleting or updating their local tag. If the tag was already used to build artifacts or deploy, the team must determine whether old artifacts are still valid, whether re-release is needed, and how to distinguish old vs. new artifacts.

A controlled workflow might look like this:

```text
Inspect local and remote tags
          |
          v
Is the tag a published release milestone?
          |
     +----+----+
     |         |
    No        Yes
     |         |
     v         v
Edit local tag  Notify and align with dependents
     |         |
     v         v
Re-verify      Consider releasing a new tag instead of retagging
     |         |
     +----+----+
          |
          v
Push or delete tag per permissions and policy
          |
          v
Verify remote and share local sync instructions
```

## 10. Common mistakes and risks

- **Assuming `git tag -d` deletes the tag on the server.** This command only deletes the local tag; a push delete command is required to remove the remote tag.
- **Assuming deleting a remote tag deletes it on every machine.** Each clone has its own local tag refs; users must update per instructions.
- **Using `git push --tags` to push a single tag.** This command may publish many unrelated local tags. Use a refspec for the specific tag.
- **Force-pushing a release tag without notice.** Users, CI, and artifacts may share the same tag name while pointing to different contents.
- **Not inspecting the annotated tag object.** Two tags may point to the same commit while having different messages, taggers, or signatures; recreating a tag changes these metadata fields.
- **Deleting a tag and assuming the commit is also deleted.** The commit may still be retained by branches, other tags, the reflog, or other refs.
- **Pruning all tags without checking configuration.** You could lose local-only tags that exist solely in your repository.
- **Failing to guide users who checked out the old tag.** Moving a tag does not automatically move branches or HEADs created from the old commit.

## 11. Practical example: fixing a mistakenly created release tag

Suppose the team discovers that tag `v2.3.0` points to a test commit instead of the release commit. First, verify the state:

```bash
git show --no-patch --decorate v2.3.0
git rev-parse "v2.3.0^{}"
git ls-remote --tags origin v2.3.0
```

If the tag has not been published and is only wrong locally, update the local tag to the verified release commit:

```bash
git tag -f -a -m "Release v2.3.0" v2.3.0 <release-commit>
git show --no-patch --decorate v2.3.0
```

If the tag has already been published, prefer creating a new corrective version tag per release policy, such as `v2.3.1`. If the organization decides the existing tag must be fixed, notify everyone and update the remote following the approved process:

```bash
git push --force origin refs/tags/v2.3.0:refs/tags/v2.3.0
git ls-remote --tags origin v2.3.0
```

Users who fetched the old tag must confirm the notice, delete their old local tag, and re-fetch. Pipelines and artifacts built from the old tag must also be audited; moving a ref does not automatically alter existing builds.

## 12. Key takeaways

Changing or deleting a local tag only affects the current repository; changing or deleting a remote tag requires a separate push operation. Users who already fetched a tag retain the old local copy until they actively update it. For published release tags, prefer keeping the milestone immutable and issuing a new corrective tag; if retagging or deletion is unavoidable, verify the target commit, notify dependents, provide sync instructions, and re-check pipelines and artifacts.

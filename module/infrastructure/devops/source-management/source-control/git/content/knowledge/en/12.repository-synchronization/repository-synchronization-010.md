# Synchronizing Tags Explicitly and Tag Update Limitations

Tags attach a memorable name to a Git object, usually a commit representing a release version such as `v1.2.0`. When working with remotes, synchronizing branches and tags follows different rules: Git can automatically retrieve some tags during fetch, whereas pushing tags requires an explicit request or enabling a specific policy.

Understanding these rules helps you avoid missing release tags when cloning/fetching, avoid accidentally pushing internal tags to the server, and avoid unintentionally changing a tag your team already uses to identify a version.

## 1. Where Are Tags Stored and How Do They Differ from Branches?

A branch is a reference that regularly advances to new commits as you commit. A tag is typically used to mark a stable milestone, such as a release version. Tag names reside in the repository's `refs/tags/` namespace.

Git has two common types of tags:

- **Lightweight tag** is simply a direct reference to the tagged object. Create quickly with `git tag v1.2.0`.
- **Annotated tag** is a dedicated tag object that can store tagger, timestamp, message, and signature. Create with `git tag -a v1.2.0 -m "Release v1.2.0"`.

Example of creating and viewing a tag:

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git tag --list
git show v1.2.0
```

For signed tags, you can verify with:

```bash
git tag -s v1.2.0 -m "Release v1.2.0"
git tag -v v1.2.0
```

The `git tag -s` command requires a configured signing environment, such as a GPG key. Fetching a signed tag only downloads the tag object and signature; Git does not automatically verify that the signature is trusted. Run `git tag -v` and verify the signer's identity according to your team's policy.

Tags are local references in the repository, not remote-tracking branches like `origin/main`. When you fetch a tag from a remote, the tag is created in `refs/tags/` of the current repository. If you fetch the same tag name from another remote, Git still has to share that single tag name; there are no separate namespaces like `origin/v1.2.0` and `upstream/v1.2.0`.

## 2. How Does Git Automatically Fetch Tags During Fetch?

Normal fetch command:

```bash
git fetch origin
```

Besides refs configured for fetching, Git has an *auto-follow* mechanism: when a downloaded object has a tag pointing to it, Git can automatically retrieve that associated tag. Therefore, you may see new tags after fetching a branch even without passing `--tags`.

Auto-follow does not mean Git always downloads every tag on the remote. If you need to sync all tags from a remote, specify it explicitly:

```bash
git fetch --tags origin
```

This command retrieves all tags from `origin` along with the required objects. Branch refs are still fetched according to existing fetch refspecs and configuration; `--tags` does not mean fetch tags only.

If a repository should not automatically pull tags during normal fetches, you can use:

```bash
git fetch --no-tags origin
```

`--no-tags` disables auto-follow for that fetch. It does not delete tags already present in the local repository. You can still retrieve a specific tag with an explicit fetch command.

You can configure auto-follow behavior per remote:

```bash
git config remote.origin.tagOpt --no-tags
```

After this setting, normal fetches from `origin` will not auto-follow tags. Whenever you need all tags, you can still run `git fetch --tags origin`.

## 3. Fetching a Specific Tag

When only a single version is needed, fetching the exact tag is clearer than downloading all tags:

```bash
git fetch origin tag v1.2.0
```

The syntax above tells Git to retrieve tag `v1.2.0` from `origin` and write it to the local tag of the same name. An explicit refspec equivalent is:

```bash
git fetch origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

Verify the tag exists locally:

```bash
git tag --list v1.2.0
git show v1.2.0
```

To view tags advertised by the remote:

```bash
git ls-remote --tags origin
```

For an annotated tag, the output usually has two lines: one for the tag object at `refs/tags/v1.2.0` and one with suffix `^{}` for the peeled object that the tag points to, typically a commit. A lightweight tag usually has only the direct reference line. This is a useful way to compare tags on the server with local tags without needing to fetch first.

## 4. Pushing Tags to the Remote

Git does not push all tags by default when you push branches. There are three common approaches.

### Pushing a selected tag

When creating a release tag, the safest and most controllable approach is to push only that tag:

```bash
git push origin v1.2.0
```

This command pushes tag `v1.2.0` to `origin`. You can also write the refspec explicitly:

```bash
git push origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

### Pushing all local tags

```bash
git push --tags origin
```

`--tags` pushes every local tag under `refs/tags/`, including both lightweight and annotated tags. Check `git tag --list` before running it because the repository may contain experimental tags, personal tags, or tags outside the current release scope.

### Pushing annotated tags associated with pushed commits

```bash
git push --follow-tags origin main
```

`--follow-tags` additionally pushes annotated tags missing on the remote that are reachable from the refs being pushed. This option does not push every tag in the repository and does not automatically push lightweight tags. It fits well when release workflows use annotated tags and want related tags pushed alongside the branch.

You can enable this behavior by default for pushes with:

```bash
git config push.followTags true
```

Once set, normal pushes apply the follow-tags policy. Align this setting with your team's workflow to avoid surprises during releases.

| Need | Command | Scope of Tags Pushed |
|---|---|---|
| Push a specific version | `git push origin v1.2.0` | Only the specified tag |
| Sync all local tags | `git push --tags origin` | All local lightweight and annotated tags |
| Push release tags related to a branch | `git push --follow-tags origin main` | Annotated tags missing on remote and reachable from pushed refs |

## 5. Verifying Before and After Synchronizing

Before pushing a tag, confirm the tag points to the intended commit:

```bash
git show --no-patch --decorate v1.2.0
git rev-parse 'v1.2.0^{commit}'
git status
```

If the tag is signed, verify its signature:

```bash
git tag -v v1.2.0
```

After pushing, verify the remote:

```bash
git ls-remote --tags origin v1.2.0
```

You can also fetch the specific tag into another clone to verify that other users can pull the exact release milestone:

```bash
git fetch origin tag v1.2.0
git show v1.2.0
```

Note that `git ls-remote` shows the ref advertised by the remote; it does not verify tag signatures. To verify a signature, you must have the tag object locally and run `git tag -v`.

## 6. When Tags Share the Same Name but Point to Different Objects

Release tags are generally treated as immutable. Once `v1.2.0` has been published, the team should keep the target the tag points to unchanged. If a bug is discovered in a release, normally create a new version tag or release a patch instead of silently moving the old tag.

Git protects existing tags from accidental modification. When fetching a tag with the same name that points to a different object, modern Git versions normally refuse to update it unless you request force. Pushing a tag that already exists on the remote pointing to a different object is also normally rejected.

Before resolving the conflict, compare the local and remote tag objects:

```bash
git rev-parse v1.2.0
git ls-remote --tags origin v1.2.0
```

For an annotated tag, the tag object ID and the peeled commit ID can differ. To compare the exact commit target, inspect the `^{}` line from `git ls-remote` or use `git rev-parse 'v1.2.0^{commit}'` locally.

If the team has agreed to update a specific local tag from the remote, use a refspec with a `+` sign for that exact tag:

```bash
git fetch origin +refs/tags/v1.2.0:refs/tags/v1.2.0
```

The `+` sign permits updating the destination ref even when it is not a fast-forward. Do this only after confirming the remote tag is the authoritative source, because this replaces the local tag of the same name.

If there is explicit approval to replace a tag on the remote, you can force push that specific tag:

```bash
git push --force origin refs/tags/v1.2.0:refs/tags/v1.2.0
```

This operation alters a published reference. Other clones may still retain the old tag and will need coordination to update. Never use force push on tags as a routine way to fix release mistakes.

## 7. Deleting Tags and Prune Limitations

Delete a tag locally:

```bash
git tag -d v1.2.0
```

Delete a tag on the remote:

```bash
git push origin --delete v1.2.0
```

These two operations are independent. Deleting a tag on the remote does not automatically remove tags already in teammates' clones; each clone must delete the local tag if it needs to be removed.

Normally, `git fetch --prune origin` cleans up remote-tracking refs no longer present on the remote according to the fetch refspec. Tag auto-follow is not a refspec mapping all of `refs/tags/*`, so `--prune` alone does not automatically delete local tags absent from the remote.

If you want to sync the local tag set to match the remote and delete local tags no longer present on the remote, you can use:

```bash
git fetch --prune --prune-tags origin
```

`--prune-tags` adds an explicit tag mapping combined with pruning. This command can delete local tags not present on `origin`, including personal tags or tags fetched from another remote. Tags with the same name pointing to different objects are still subject to Git's tag update protection rules; pruning does not equate to force-overwriting tags. Because all remotes share the `refs/tags/` namespace in a repository, pruning against one remote can affect tags you need for another remote.

If you simply want to inspect what tags exist on the remote before cleaning up, check:

```bash
git tag --list
git ls-remote --tags origin
```

Do not confuse `git remote prune origin` with tag cleanup. That command cleans up stale remote-tracking branches for the remote; it is not a command to sync or delete local tags.

## 8. Team Tag Synchronization Workflow

A release workflow can follow this order:

1. **Create the tag after confirming the commit.** Use an annotated tag, or a signed tag if policy requires.
2. **Verify the tag.** Inspect the target commit with `git show` or `git rev-parse`; verify signatures if present.
3. **Push the exact release tag.** Use `git push origin v1.2.0`; use `--tags` only when intentionally syncing all local tags.
4. **Confirm on the remote.** Run `git ls-remote --tags origin v1.2.0` to verify the tag has been published.
5. **Instruct other clones to update.** Use `git fetch origin tag v1.2.0` or `git fetch --tags origin` depending on need.
6. **Keep release history stable.** If a published tag needs adjustment, discuss with the team and agree on how to proceed before force updating or deleting.

Full example:

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git show --no-patch v1.2.0
git push origin v1.2.0
git ls-remote --tags origin v1.2.0
```

In another clone:

```bash
git fetch origin tag v1.2.0
git show v1.2.0
```

## 9. Practice Exercise

Suppose your team is preparing to release `v2.4.0`. Your local repository contains several old experimental tags, so you want to publish only this release tag.

1. Create an annotated tag `v2.4.0` pointing to the verified release commit.
2. Use `git show v2.4.0` to inspect the tag details and target commit.
3. Use `git push origin v2.4.0` to push this tag individually.
4. Use `git ls-remote --tags origin v2.4.0` to confirm the remote received the tag.
5. In another clone, run `git fetch origin tag v2.4.0` and inspect the tag.
6. Compare the outcomes of `git push --tags` and `git push --follow-tags` in a test repository containing both lightweight tags and annotated tags.

You have completed the exercise when you can explain why a normal fetch may retrieve only some tags, the differences among the three ways of pushing tags, and the risks of force-updating or pruning tags.

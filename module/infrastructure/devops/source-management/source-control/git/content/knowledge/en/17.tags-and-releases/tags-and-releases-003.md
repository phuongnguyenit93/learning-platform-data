# Listing, filtering, and viewing tag details

A tag is a named reference used to mark a specific point in Git history, typically a commit corresponding to a software version such as `v1.0.0` or `v2.3.1`. When preparing a release, verifying previously created versions, or finding a tagged commit, you need to know how to list and inspect tag information.

Git provides `git tag --list` to view tags in the local repository, filters to search tag groups by name or commit relationship, and `git show` to inspect the contents at a tag. You should distinguish between local tags and tags advertised by a remote: by default, listing tags reads refs present in the local repository and does not query the server.

## 1. How are tags stored?

Tags are refs located in the `refs/tags/` namespace. For example, the tag `v1.2.0` corresponds to the ref `refs/tags/v1.2.0`. Unlike branches that typically move as new commits are created, tags are generally used as stable milestones to reference a version.

Git has two common tag types:

- **Lightweight tag:** a simple ref pointing directly to the tagged object, usually a commit. It has no separate tag message, tagger, or tag creation timestamp.
- **Annotated tag:** a tag object containing the target object, tag name, tagger information, timestamp, and message. This type is suitable for marking official releases because it stores release metadata.

Example of creating both tag types:

```bash
# Lightweight tag.
git tag v1.0.0

# Annotated tag with a message.
git tag -a v1.1.0 -m "Release version 1.1.0"
```

The commands in this article primarily read and filter existing tags. When creating a new tag, choose the appropriate tag type and target commit according to your team's release conventions.

## 2. Listing tags with git tag --list

To list all local tags:

```bash
git tag --list
```

Common shorthand form:

```bash
git tag -l
```

Example output:

```text
v1.0.0
v1.1.0
v1.2.0
v2.0.0-rc.1
v2.0.0
```

Each line is the name of a tag present in the local repository. This command only displays names; it does not show which commit a tag points to, whether a tag is lightweight or annotated, or the release message content.

If the repository has no tags yet, the command may print nothing. That only indicates there are no matching tags in the current local repository; you cannot conclude from it that the remote has no tags either.

## 3. Filtering tags by name using patterns

`git tag --list` accepts one or more glob-style patterns to filter tag names. For example:

```bash
# List only tags in the 1.x line.
git tag --list "v1.*"

# Find release candidate tags.
git tag --list "*-rc.*"

# Find tags with the beta prefix.
git tag --list "beta-*"
```

Enclose patterns in quotes so the shell does not expand `*` before passing arguments to Git. Patterns apply to tag names, not commit messages or source code contents.

You can pass multiple patterns:

```bash
git tag --list "v1.*" "v2.*"
```

Git lists tags matching any of the patterns. This is helpful when you want to view several version lines at once.

## 4. Sorting tags by version or timestamp

By default, tag names may be sorted lexicographically. For version numbers, lexicographical order is sometimes not what you want: `v1.10.0` can appear before or after `v1.2.0` depending on string comparison rather than the numeric value of each version segment.

Use `--sort=version:refname` to sort with version awareness:

```bash
# Ascending by version.
git tag --list --sort=version:refname

# Descending, newer version tags typically appear at the top.
git tag --list --sort=-version:refname
```

You can use the alias `v:refname` for `version:refname`:

```bash
git tag --list --sort=-v:refname
```

If you want to sort by creation date, use:

```bash
git tag --list --sort=-creatordate
```

`creatordate` is a suitable date field for sorting both lightweight and annotated tags: for annotated tags, Git uses the tagger date; for lightweight tags, this field is derived from the referenced object, usually the commit date. Therefore, it is not necessarily the exact time a lightweight tag was created on your machine.

The default sort order may also be affected by the `tag.sort` configuration. If results must be consistent in scripts or release documentation, specify `--sort` explicitly in the command rather than relying on each machine's local configuration.

## 5. Displaying short messages with git tag -n

To list tags along with part of their message:

```bash
git tag -n
```

By default, Git shows the first line of the annotation for annotated tags; for lightweight tags, Git shows the first line of the commit message at the tagged commit. You can request more lines:

```bash
git tag -n5
```

Example:

```text
v1.0.0          Initial stable release
v1.1.0          Release version 1.1.0
v2.0.0-rc.1     Release candidate 1 for version 2.0.0
```

`-n` is useful for quickly scanning a release list. However, it is only a summary; if you need to view the full tag message, tagger, creation date, and target commit, use `git show`.

## 6. Viewing tag details with git show

The most common command for inspecting a tag and the content it marks:

```bash
git show v1.1.0
```

For an annotated tag, the output usually includes tag object details such as the tagger, creation date, and message, followed by the tagged object's contents (typically the commit and diff). For a lightweight tag, the ref points directly to the commit, so `git show` displays the commit information and corresponding changes.

If you only want to see the commit a tag resolves to:

```bash
git rev-parse 'v1.1.0^{commit}'
```

The command returns the commit's object ID. The `^{commit}` syntax instructs Git to resolve the tag to a commit; it is also useful when a tag points indirectly through an annotated tag object.

To view a few lines of history around a tag:

```bash
git log --oneline --decorate -5 v1.1.0
```

This command displays history starting from the commit referenced by the tag. It helps identify which commit in the development stream the tag marks.

## 7. Distinguishing lightweight and annotated tags during inspection

You can check the object type that a tag name points to:

```bash
git cat-file -t v1.0.0
git cat-file -t v1.1.0
```

Example:

```text
commit
tag
```

If the result is `commit`, the tag is typically a lightweight tag pointing directly to a commit. If the result is `tag`, the ref points to an annotated tag object.

To read the raw contents of an annotated tag object:

```bash
git cat-file -p v1.1.0
```

Example contents:

```text
object 4a5b6c7d8e9f00112233445566778899aabbccdd
type commit
tag v1.1.0
tagger Dev Example <dev@example.com> 1735689600 +0700

Release version 1.1.0
```

The lines show the target object, object type, tag name, tagger, and message. This is useful when you need to inspect release metadata or analyze why `git show` displays a tag in a certain way.

## 8. Filtering tags by commit relationship

In addition to name patterns, Git lets you filter tags based on the relationship between the tagged commit and another commit.

### Tags containing a commit: --contains

```bash
git tag --contains <commit>
```

This command lists tags whose tagged commit history contains the specified commit. If `<commit>` is omitted, Git uses the current HEAD. Example:

```bash
git tag --contains HEAD
```

This is useful when you want to know which tags already include the current commit in their history.

### Tags merged into a commit: --merged

```bash
git tag --merged main
```

This command lists tags whose tagged commits are already reachable in the history of `main`. It helps find release milestones that have been integrated into that branch.

Conversely:

```bash
git tag --no-merged main
```

This command lists tags whose commits are not yet in the history of `main`. The output helps review releases or experimental tags not yet integrated into the branch being checked.

### Tags pointing to an object: --points-at

```bash
git tag --points-at HEAD
```

This command lists tags pointing to the specified object, such as the current commit. If you want to check a specific commit:

```bash
git tag --points-at 4a5b6c7
```

These filters are based on object relationships and commit history, not just tag names. They are especially useful when a repository has many releases, hotfixes, and experimental tags.

## 9. Customizing output with git tag --format

When you need a more structured list, `--format` lets you choose which fields to display:

```bash
git tag --list --sort=-version:refname --format="%(refname:short) %(objectname:short) %(creatordate:short) %(subject)"
```

Example output:

```text
v2.0.0  7a8b9c0  2026-04-10  Release version 2.0.0
v1.1.0  4d5e6f7  2026-02-18  Release version 1.1.0
v1.0.0  1a2b3c4  2025-12-01  Initial stable release
```

Some useful placeholders:

| Placeholder | Meaning |
|---|---|
| `%(refname:short)` | Shortened tag name without the `refs/tags/` prefix |
| `%(objectname:short)` | Abbreviated object ID that the tag ref points to |
| `%(creatordate:short)` | Creation date appropriate to the referenced object type |
| `%(subject)` | Subject line of the corresponding tag or commit content |
| `%(taggername)` | Tagger name for annotated tags; may be empty for lightweight tags |

If you need complete data for script processing, consider `git for-each-ref` with the `refs/tags/` namespace. That command supports many placeholders and ref filters, making it well suited for building automated release reports.

## 10. Local tags vs. remote tags

`git tag --list` only lists tags currently present in the local repository. It does not query the remote to check the latest tag list on the server.

To list tags advertised by the remote:

```bash
git ls-remote --tags origin
```

To fetch tags from the remote to local:

```bash
git fetch --tags origin
```

After fetching, re-check the local list:

```bash
git tag --list --sort=-version:refname
```

Git automatically fetches some tags pointing to history being fetched. `git fetch --tags` requests retrieving all tags advertised by the remote. Therefore, if you need to synchronize the full tag list from the remote, use this option and verify the results after fetching.

Do not assume that a local tag has already been pushed to the server. To inspect tags on the remote, use `git ls-remote`; to share a new tag, use a tag push command per your release workflow, such as `git push origin v2.0.0` or `git push --tags` if you genuinely want to send all appropriate local tags.

## 11. Workflow for reviewing tags before a release

Suppose a team needs to identify existing version tags, inspect release messages, and check which commit the `v2.0.0` tag points to.

```bash
# 1. List tags in descending version order.
git tag --list --sort=-version:refname

# 2. Find tags in the 2.x line.
git tag --list "v2.*" --sort=-version:refname

# 3. View short messages of the tags.
git tag --list -n5 "v2.*"

# 4. View details of a release tag.
git show v2.0.0

# 5. Get the commit ID that the tag resolves to.
git rev-parse 'v2.0.0^{commit}'

# 6. Check whether the local tag already exists on the remote.
git ls-remote --tags origin "refs/tags/v2.0.0"
```

If the tag is not yet local but has already been published on the remote, fetch tags first before inspecting details. If the tag exists locally but has not been published to the remote, coordinate with the release owner before pushing to avoid releasing the wrong milestone.

## 12. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| `git tag --list` lists tags on the server | This command reads local tags; use `git ls-remote --tags <remote>` to see tags advertised by the remote |
| Lightweight and annotated tags are the same | Annotated tags have a dedicated tag object and metadata; lightweight tags are direct refs to the marked object |
| `git tag -n` displays full release notes | It only displays the requested number of annotation/commit message lines, defaulting to one line |
| Tag names automatically sort by proper version | Use `--sort=version:refname` to sort by version |
| `git show <tag>` only prints the tag name | It displays the tag object and the contents of the tagged object, depending on the tag type |
| Creating a local tag means the release is shared | Tags remain local until pushed or shared through another mechanism |

## 13. Key takeaways

To list local tags, use `git tag --list`; to filter by name, pass a glob pattern; to sort by version, use `--sort=-version:refname`; to view short messages, use `-n`; and to read details of a milestone, use `git show <tag>`.

When you need to inspect tag metadata, combine `git cat-file -t` and `git cat-file -p`. When filtering by history, use `--contains`, `--merged`, `--no-merged`, or `--points-at`. Finally, distinguish local tags from remote tags: use `git ls-remote --tags` to check the server and `git fetch --tags` to bring tags into the local repository.

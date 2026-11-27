# Working with tags in detached HEAD state

In Git, a tag is a named reference to a specific milestone in history, typically used to mark a release version such as `v1.4.0`. When you check out or switch directly to a tag, Git updates the working tree to match the commit the tag points to. At that moment, `HEAD` is no longer attached to a branch and instead points straight to the commit, creating a **detached HEAD** state.

Detached HEAD is very suitable for inspecting source code at a specific version, running tests, hunting down bugs, or prototyping a fix. However, if you create new commits in this state, no branch automatically advances to retain those commits. You need to understand how tags and HEAD relate to avoid losing track of your work after switching to another branch.

## 1. How do HEAD, branches, and tags relate?

In a normal state, `HEAD` typically points to the current branch. The branch, in turn, points to its latest commit:

```text
HEAD -> main -> C
```

When a new commit is created on `main`, Git updates the `main` ref to point to the new commit; `HEAD` remains attached to that branch.

A tag is also a ref, but it is used to name a historical milestone. For example:

```text
HEAD -> main -> C
                 ^
                 |
              v1.2.0
```

When switching directly to a tag:

```bash
git switch --detach v1.2.0
```

Git places `HEAD` directly on the commit referenced by the tag:

```text
HEAD ------> C
             ^
             |
          v1.2.0

main ------> D
```

In this example, `main` remains at commit `D`, while `HEAD` is viewing commit `C`. No branch is checked out. This is detached HEAD.

You can check the status with:

```bash
git status
git branch --show-current
git rev-parse --short HEAD
git tag --points-at HEAD
```

When detached, `git status` displays a corresponding notice; `git branch --show-current` typically prints no branch name; `git rev-parse --short HEAD` reports the current commit; `git tag --points-at HEAD` lists tags pointing directly to that commit.

Detached HEAD does not mean the repository is read-only. You can still edit files, stage changes, and create commits. The difference is that new commits do not move a branch ref.

## 2. Switching to a tag to inspect a version

Before switching, check the working tree for uncommitted changes:

```bash
git status
```

List tags:

```bash
git tag --list
git tag --list 'v1.*'
git tag --sort=-version:refname
```

The last command sorts tag names in version order if the tag names follow a version convention recognized by Git.

Check where a tag points and inspect commit contents:

```bash
git show v1.2.0
git rev-parse v1.2.0
```

Switch to the tag in detached HEAD:

```bash
git switch --detach v1.2.0
```

The older equivalent command is:

```bash
git checkout --detach v1.2.0
```

Using `git switch --detach` clearly expresses the intent to move to a commit without checking out a branch. After switching, the working tree reflects the contents at tag `v1.2.0`; you can read the source code, run tests, or inspect that version's behavior.

Common use cases for detached HEAD:

- Reproducing a bug that only appears in a released version.
- Comparing behavior between two tags.
- Running tests on a tagged commit.
- Inspecting release contents without altering development branches.
- Creating a bug-fix branch starting from an older version.

Example of comparing two milestones:

```bash
git diff v1.1.0..v1.2.0
git log --oneline v1.1.0..v1.2.0
```

The two commands above do not require checking out a tag; they display the changes between milestones.

## 3. Creating a tag while in detached HEAD

Once you have moved to the exact commit to mark, you can create a tag right at `HEAD`. Git supports two common tag types.

A **lightweight tag** is a simple ref pointing directly to the specified object, usually a commit:

```bash
git tag v1.2.1
```

Because it does not record extra metadata such as the tagger, timestamp, and message, a lightweight tag is suited for internal checkpoints or temporary labels.

An **annotated tag** creates a tag object containing the tagger, creation date, message, and optionally a signature:

```bash
git tag -a v1.2.1 -m "Release 1.2.1"
```

Annotated tags are generally suitable for release milestones because they store version-descriptive information. You can inspect the tag:

```bash
git show v1.2.1
git cat-file -t v1.2.1
git rev-parse "v1.2.1^{commit}"
```

For an annotated tag, `git cat-file -t v1.2.1` returns `tag`; for a lightweight tag pointing directly to a commit, the output is usually `commit`. The `^{commit}` syntax instructs Git to resolve the tag to the commit it points to.

When detached at commit `C`, creating a tag gives a name to `C`:

```text
HEAD ------> C
             ^
             |
          v1.2.1
```

The tag does not move the `main` branch, create a new commit, or attach HEAD back to a branch. It merely adds a reference name to the current milestone.

If the tag already exists, Git refuses to create a duplicate tag by default. Check beforehand:

```bash
git tag --list v1.2.1
```

Do not use `git tag -f` merely to bypass a duplicate-name error. Force-updating a tag can change the meaning of a published version and cause discrepancies across clones. For shared release tags, keep tags immutable; if a revision must be released, choose a new version number according to the project's convention.

## 4. Creating new commits while in detached HEAD

You can edit files and create commits while detached:

```bash
git switch --detach v1.2.0

# Edit files, then:
git add -- src/fix.java
git commit -m "Try a fix on release 1.2.0"
```

After committing, `HEAD` points to the new commit, while `main` or other branches remain at their old positions:

```text
A---B---C---D       (main)
         \
          E        (HEAD, detached)
```

Commit `E` has been created and exists in the object database. However, no branch holds it via a branch ref. If you switch away without creating a retaining ref, the commit may only remain findable through the reflog for a limited time; once the reflog expires and garbage collection cleans up unreachable objects, recovery becomes much harder.

If you want to keep your work, create a branch right at the current commit:

```bash
git switch -c fix/release-1.2.0
```

This command creates a new branch pointing to the current commit and switches HEAD to that branch:

```text
A---B---C---D       (main)
         \
          E        (fix/release-1.2.0, HEAD)
```

From here, subsequent commits advance the `fix/release-1.2.0` branch as usual.

If you only want to place a rescue marker without continuing work on a branch yet, you can create a tag:

```bash
git tag rescue/release-1.2.0
```

A tag retains the current commit, though a branch is usually more convenient when you plan to develop further commits.

## 5. Returning to a branch after inspecting a tag

If you only read source code or ran tests without creating commits, you can switch back to a branch:

```bash
git switch main
```

If you created commits while detached and want to keep developing them, create a branch before switching away:

```bash
git switch -c fix/from-v1.2.0
```

If a detached commit was created and you already switched to another branch, you can still find the commit via the reflog and create a branch pointing to it:

```bash
git reflog
git switch -c rescue/detached-work <commit-id>
```

Replace `<commit-id>` with the commit hash found in the reflog. The command creates a new branch at that commit; you can then review the contents and continue working.

If you want to bring a commit created in detached HEAD into an existing branch, note its commit ID and cherry-pick it:

```bash
git switch main
git cherry-pick <commit-id>
```

Cherry-pick creates a new commit on `main` with the corresponding changes. The original commit from detached HEAD can still be preserved by a rescue branch or tag if you created a ref for it.

Do not use `git reset --hard` as a routine way to exit detached HEAD. That command can discard uncommitted changes in the working tree and index.

## 6. Releasing a tag from detached HEAD and pushing to a remote

A common workflow is verifying the exact commit, creating an annotated tag, and pushing the tag to the remote:

```bash
# Fetch recent tags from the remote before selecting a version
git fetch origin --tags

# Switch to the commit chosen as the release content
git switch --detach <release-commit>

# Verify the commit and run tests
git show --no-patch --format=fuller HEAD
git status

# Create the new release tag on the current commit
git tag -a v1.2.1 -m "Release 1.2.1"

# Inspect the newly created tag
git show v1.2.1

# Push only the specific tag to the remote
git push origin v1.2.1
```

Replace `<release-commit>` with the commit ID verified and selected as the content for version `v1.2.1`. Do not assume a new tag should point to the previous version tag's commit.

Pushing a specific tag with `git push origin v1.2.1` sends that tag to the remote. The command does not move remote branches such as `main`. To push all local tags missing from the remote, Git has:

```bash
git push origin --tags
```

Only use `--tags` when you genuinely want to push all eligible local tags; a repository may contain experimental or internal tags that should not be published. For a specific release, pushing the explicit tag name is easier to control.

You can check which tags exist on the remote with:

```bash
git ls-remote --tags origin
```

If others need to fetch the new tag, they can run:

```bash
git fetch origin --tags
```

## 7. Modifying or deleting tags

Tags are generally treated as immutable milestones once published. If a local tag was created by mistake and has not been shared, you can delete and recreate it after verification:

```bash
git tag -d v1.2.1
git tag -a v1.2.1 -m "Release 1.2.1" <correct-commit>
```

Replace `<correct-commit>` with the right commit ID. Deleting a local tag does not delete it on the remote.

If the tag has already been pushed, deleting the remote tag is a separate operation:

```bash
git push origin --delete refs/tags/v1.2.1
```

Do not delete or move a published release tag without coordinating with everyone using that tag. Other clones may still retain the old tag, causing the same tag name to point to different commits across machines. If a release has a bug, it is usually better to create a new version tag instead of reusing the old name.

## 8. Common situations and how to handle them

| Situation | What is happening | Resolution |
|---|---|---|
| `git status` reports detached HEAD | HEAD points directly to a commit | Normal when inspecting a tag; create a branch if you need to develop |
| `git branch --show-current` prints no name | No branch is currently checked out | Use `git status` and `git rev-parse HEAD` to verify |
| Created a commit then switched branches | The detached commit is not held by any branch | Create a branch or rescue tag before switching away |
| `git tag` reports tag already exists | The tag name is already in use | Inspect `git show <tag>`; pick a new name or handle per policy |
| Tag exists locally but not on remote | The tag has not been pushed yet | Use `git push origin <tag>` |
| Remote tag differs from local tag | Both sides have different values for the tag | Stop overwriting, verify the source, and coordinate before fixing |
| Want to edit code at a release tag | A tag is only a reference milestone | Create a branch from the tag with `git switch -c <branch> <tag>` |

## 9. Checklist before leaving detached HEAD

Before switching to another branch, check yourself:

1. Which commit am I on? Use `git rev-parse --short HEAD`.
2. Is HEAD detached or attached to a branch? Use `git status`.
3. Are there uncommitted changes? Use `git status --short`.
4. Did I create new commits while detached? Check `git log --oneline --decorate -5`.
5. If there are new commits, are they retained by a branch or tag?
6. Is the tag I created the right type, right name, and on the right commit?
7. If the tag needs to be shared, did I push the right tag to the right remote?

This checklist helps separate three distinct actions: inspecting a commit, creating new commits, and naming a milestone. They can happen together, but one does not automatically replace another.

## Conclusion

When using `git switch --detach <tag>`, Git moves HEAD directly to the commit the tag points to without checking out a branch. You can inspect a version or create experimental commits in this state. If new commits need to be kept long-term, create a branch with `git switch -c <branch>` or a rescue tag before leaving. When creating a release tag, verify the commit, prefer annotated tags, push tags explicitly, and treat published tags as milestones to keep stable.

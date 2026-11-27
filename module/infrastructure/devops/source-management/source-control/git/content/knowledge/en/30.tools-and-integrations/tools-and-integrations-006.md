# Checkout in Automated Environments: Detached HEAD and Shallow History

In CI/CD pipelines, Git typically checks out a specific commit to build, run tests, or generate artifacts. Because checking out by commit hash is not necessarily tied to a local branch, the repository can be in a **detached HEAD** state. Many pipelines also use a **shallow clone** to fetch less history and speed up checkout.

These two states serve different purposes: detached HEAD describes how HEAD points to a commit; shallow clone describes how much history has been downloaded. They can occur together or independently. Understanding both helps you reproduce the exact source code under test, avoid assuming a branch exists, and know when to fetch deeper history to generate changelogs, compute versions, or perform a merge/rebase.

## 1. Why do automated environments usually check out a single commit?

A pipeline is usually triggered by a specific event: pushing to a branch, creating a tag, opening a pull request, or running on a schedule. When the pipeline starts, the system identifies a target commit to test.

For example:

```text
main:       A --- B --- C
                         \
feature:                  D --- E

Pipeline is asked to test commit E
```

The pipeline can fetch commit E directly and check it out. The goal is to build the exact requested snapshot, even if the branch later moves forward to newer commits.

Using the commit ID keeps results traceable:

```bash
git rev-parse HEAD
git show -s --format=fuller HEAD
```

These two commands reveal the OID and metadata of the commit actually checked out. When storing build logs, recording this OID lets you correlate artifacts back to the source commit.

For pull requests, the tested commit might be the contributor's branch head or a temporary merge commit created by the CI platform to simulate merging into the target branch. Do not assume every pull request pipeline builds the same kind of commit. Check your pipeline's checkout configuration and record the actual OID with `git rev-parse HEAD`.

## 2. What is detached HEAD?

In the normal state, `HEAD` is a symbolic ref pointing to the current branch:

```text
HEAD -> refs/heads/main -> commit C
```

When checking out a commit, tag, or remote-tracking ref directly, Git can switch to detached HEAD:

```text
HEAD --------------------> commit E

refs/heads/main ----------> commit C
refs/heads/feature -------> commit E
```

`HEAD` points directly to commit E rather than through a local branch. This is a valid state and very common in CI.

For example:

```bash
git checkout --detach <commit-oid>
```

Or using the modern `switch` command:

```bash
git switch --detach <commit-oid>
```

Checking out a tag also typically leads to detached HEAD:

```bash
git switch --detach v2.4.0
```

You can still read files, run builds, tests, linters, and produce artifacts. Detached HEAD does not make the repository read-only. The thing to note is that if you create a new commit while detached, that commit is not automatically attached to any branch.

Check status:

```bash
git status --short --branch
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref -q --short HEAD
```

When in detached HEAD:

- `git status --short --branch` typically displays the header `## HEAD (no branch)`; the full `git status` may say `HEAD detached at ...`.
- `git branch --show-current` returns an empty string because there is no current local branch.
- `git rev-parse HEAD` still returns the commit OID.
- `git symbolic-ref` cannot resolve `HEAD` to a branch and exits with a non-zero status code.

Do not interpret an empty result from `git branch --show-current` as a failed checkout. Check `git status` and `git rev-parse HEAD`.

## 3. Detached HEAD and shallow clone are two independent concepts

Detached HEAD describes the position of `HEAD`; shallow clone describes the depth of history present in the repository.

| Scenario | HEAD | History |
|---|---|---|
| Full branch checkout | Points through a branch | Has history fetched for the ref |
| Commit checkout in a full clone | Points directly to a commit | Has full fetched history |
| Commit checkout in a shallow clone | Points directly to a commit | Only has partial history |
| Branch checkout in a shallow clone | Points through a branch | Branch only has shallow fetched history |

You can check the two states separately:

```bash
git status --short --branch
git rev-parse --is-shallow-repository
```

The first command shows whether HEAD is attached or detached. The second prints `true` if the repository is shallow, `false` otherwise.

Because the two states are independent, creating a new branch from detached HEAD does not automatically fetch more history. Likewise, fetching more history does not automatically attach HEAD to a branch.

## 4. Creating a shallow clone for fast checkout

A shallow clone downloads only part of the history instead of the entire ancestry of a branch. The simplest form:

```bash
git clone --depth 1 https://example.com/team/app.git
```

`--depth 1` requests shallow history with one commit at the tip of the fetched branch. When using `--depth`, Git by default also limits history retrieval to a single branch (equivalent to `--single-branch`), unless `--no-single-branch` is specified.

You can specify the branch explicitly:

```bash
git clone --depth 1 --branch main --single-branch https://example.com/team/app.git
```

This command fetches the `main` branch with depth 1. It fits when the pipeline only needs the current snapshot to build or test and does not need to query older history.

After cloning, verify:

```bash
cd app
git rev-parse --is-shallow-repository
git log --oneline --decorate
git status --short --branch
```

A shallow repository still contains the checked-out commit and all objects required to reconstruct that commit's snapshot. However, parent commits beyond the shallow boundary may not exist in the object database.

Shallow clone does not mean Git downloads incomplete files or truncates source code. It limits the commit history fetched; the checked-out commit's snapshot can still be used normally.

## 5. Checking out a specific commit in CI

In a pipeline, check out the exact ref or commit requested by the triggering event. General workflow:

1. Fetch the repository and necessary refs.
2. Determine the OID of the commit to build.
3. Check out that OID in detached HEAD.
4. Log the OID and repository state.
5. Run builds/tests on the selected snapshot.

Example with an already cloned repository:

```bash
git fetch origin
git checkout --detach <commit-oid>
git rev-parse HEAD
git status --short --branch
```

If the pipeline needs only one commit and the server supports fetching a specific refspec, you can fetch the required ref with minimal depth:

```bash
git fetch --depth=1 origin <refspec>
git checkout --detach FETCH_HEAD
```

`<refspec>` must be a ref the remote allows fetching, such as a branch or a pull request ref supplied by the CI system. Not every server allows fetching an arbitrary OID directly. If fetching fails, fetch the ref containing that commit and then check out the corresponding OID.

After checkout, verify `HEAD` matches the commit requested by the pipeline:

```bash
git rev-parse HEAD
git show -s --format='%H %s' HEAD
```

Do not rely solely on branch names in pipeline logs: a branch can move while a job is running, whereas an OID uniquely identifies the specific commit.

## 6. When do you need to create a branch from detached HEAD?

Most pipelines only read source code, build, and test. For those tasks, detached HEAD is appropriate; there is no need to create a local branch.

You need a branch if the pipeline must create a new commit and keep it referenced by a named ref, for example:

- Creating a commit to update a version or changelog.
- Generating Git-tracked files and committing the result.
- Running an automated code-fix step and committing for review.
- Preparing a temporary branch to push results to the remote.

Create a branch from the current commit:

```bash
git switch -c ci/update-generated-files
```

Or use the equivalent checkout command:

```bash
git checkout -b ci/update-generated-files
```

Then you can stage and commit:

```bash
git add -- CHANGELOG.md
git commit -m "Update generated changelog"
```

The new branch keeps the newly created commit. If you create a commit while detached and then switch to another commit, that commit may no longer be referenced by any branch and could later be cleaned up by garbage collection if no other ref retains it.

In parallel CI runs, temporary branch names must avoid collisions between jobs. If the target branch already exists, `git switch -c` will refuse to recreate it. Use a unique name with a system-provided job ID or run ID, and verify push permissions beforehand.

If the pipeline does not need to share commits, do not create a branch just to make `git status` show a branch name.

## 7. Pushing results from a pipeline

If the pipeline created a branch and needs to share commits, push the specific ref:

```bash
git push origin HEAD:refs/heads/ci/update-generated-files
```

The left side `HEAD` is the current commit; the right side is the target branch on the remote. Writing the full refspec avoids confusion between local and remote branch names.

Before pushing, check:

```bash
git status
git log -1 --oneline
git remote -v
```

The pipeline also needs appropriate authentication and write permissions. Many CI jobs are granted only read access to the repository; creating a local commit may succeed while pushing gets rejected.

Do not use `git push --force` as the default fix for push errors from a pipeline. If the target branch has changed, fetch and inspect history before deciding how to integrate.

If commits are solely for build/test, there is usually no need to push a temporary branch. Let build artifacts and logs reference the source OID instead of creating unnecessary branches.

## 8. Why does shallow history cause some commands to return incomplete results?

In a shallow clone, Git may know the current commit without knowing all of its parent commits. The shallow boundary is recorded in repository metadata. Git treats commits at that boundary as the starting point of the locally available history.

This affects operations that traverse backward through history:

| Need | Potential impact in a shallow clone |
|---|---|
| Viewing long logs | `git log` only displays the downloaded commits |
| Counting commits from root | `git rev-list --count` may undercount |
| Finding merge base | May fail to find an ancestor because required history was not downloaded |
| Generating changelogs | May omit commits since a tag or release milestone |
| `git describe` | Cannot find older tags outside the fetched history |
| `git blame` | Cannot trace back to a line's original commit if ancestry is missing |
| Merge/rebase | Some operations may be restricted or require more history |

For example, the command:

```bash
git log --oneline --all
```

only displays commits reachable from existing refs and downloaded objects. It cannot show commits that have not been fetched.

If the command:

```bash
git merge-base origin/main HEAD
```

prints no OID, do not immediately conclude the two branches share no common ancestor. In a shallow repository, the common commit may lie beyond the current history boundary. Check shallow state and fetch the needed history.

## 9. Fetching more history with deepen

If you only need a bit more history, use `git fetch --deepen`:

```bash
git fetch --deepen=50 origin main
```

This command fetches 50 more commits beyond the current shallow boundary for the `main` branch. It is useful when a pipeline initially fetches very few commits but a later step needs extra history to compute a changelog or compare against a base commit.

Another approach is specifying a new depth counted from the branch tip:

```bash
git fetch --depth=100 origin main
```

`--depth=100` requests history with a depth of 100 commits from the fetched tip. This differs from `--deepen=100`, which adds 100 commits to the existing shallow history.

You can also fetch history by timestamp:

```bash
git fetch --shallow-since="2026-01-01" origin main
```

Or exclude history reachable from a ref:

```bash
git fetch --shallow-exclude=refs/tags/v1.0.0 origin main
```

These options fit when a pipeline only needs enough history for a specific task. After fetching, verify again:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -20
```

The repository may still be shallow after deepening. That is normal if you only increased the depth partially.

## 10. Converting a shallow repository to full history

If the pipeline needs the complete ancestry of fetched refs, run:

```bash
git fetch --unshallow origin
```

This command fetches the missing history to convert a shallow repository into a full repository, provided the remote has full history and the required refspecs are fetched. If the remote itself is shallow or the server does not provide the needed history, unshallowing may not complete as expected.

Check the result:

```bash
git rev-parse --is-shallow-repository
```

A result of `false` indicates the repository is no longer shallow.

If the initial clone fetched only a single branch, pay attention to the fetch refspec. Unshallowing the history of the fetched branch does not automatically bring in all other remote branches locally. When multiple branches are needed, fetch the corresponding refs or configure explicit refspecs.

If tags and tag-associated history are needed, you can fetch tags:

```bash
git fetch --tags origin
```

However, fetching tags alone is not a substitute for deepening/unshallowing when full ancestry is required. The tag may be downloaded while parent commits needed for comparison still lie outside the shallow boundary.

## 11. Shallow clone is not partial clone

Both shallow clones and partial clones reduce downloaded data, but they restrict different things:

| Mechanism | What does it limit? | Example |
|---|---|---|
| Shallow clone | Depth of commit history | `git clone --depth 1 <url>` |
| Partial clone | Which object types are downloaded upfront; missing objects can be fetched on demand | `git clone --filter=blob:none <url>` |

A shallow clone truncates history at a commit boundary. A partial clone can preserve commit/tree relationships while deferring download of certain objects such as blobs. The two mechanisms can be combined if the server supports them.

Do not use `--filter=blob:none` to fix missing-ancestor errors caused by shallow history; it addresses object payload size rather than extending commit history. Similarly, `--unshallow` does not mean downloading every blob immediately in a partial clone.

## 12. Tags, versions, and changelogs in CI

Many pipelines compute versions based on the nearest tag, such as with `git describe`. In a shallow clone, the tag or tagged commit may not be inside the downloaded history yet.

Check available tags:

```bash
git tag --list
git describe --tags --always
```

If the pipeline cannot find the expected tag, first fetch tags:

```bash
git fetch --tags origin
```

Then check again:

```bash
git describe --tags --always
```

If the tag is present but ancestor commits needed to compute distance still lie beyond the shallow boundary, deepen or unshallow the relevant branch's history.

Example generating a changelog from the latest release tag to HEAD:

```bash
git log --oneline v2.3.0..HEAD
```

This command is only reliable if tag `v2.3.0` and the required commits exist in the repository and the history range matches the branch being built. In release pipelines, specify the baseline tag explicitly rather than relying on a "nearest tag" that could shift depending on which refs were fetched.

## 13. Example pipelines: fast build vs. history-aware pipeline

**Standard build/test pipeline**

If you only need to validate the requested snapshot, a shallow checkout is usually sufficient:

```bash
git clone --depth 1 --branch main --single-branch https://example.com/team/app.git
cd app
git status --short --branch
git rev-parse HEAD
./gradlew test
```

The job only needs the current source code and does not run operations that depend on deep history.

**Changelog or version generation pipeline**

If you need to compare against a release tag or count commits:

```bash
git clone --depth 1 --branch main https://example.com/team/app.git
cd app

git fetch --tags origin
git fetch --unshallow origin

git describe --tags --always
git log --oneline v2.3.0..HEAD
```

Here the pipeline fetches tags and expands history so version/changelog commands have sufficient data. If the remote lacks full history or branch/tag refs have not been fetched, adjust the refspec accordingly.

**Pipeline that needs to create commits**

If the job must create a commit, create a branch from the checked-out commit:

```bash
git switch -c "ci/generated-$CI_RUN_ID"
# Create or update files
git add -- CHANGELOG.md
git commit -m "Update generated changelog"
git push origin "HEAD:refs/heads/ci/generated-$CI_RUN_ID"
```

In this example `CI_RUN_ID` is a variable provided by the CI system; replace it with your platform's actual variable. Branch names must be unique across jobs. The pipeline also needs write permissions and should inspect the diff before committing to avoid introducing unrelated files into history.

## 14. Common issues

| Symptom | Common cause | How to handle |
|---|---|---|
| `git branch --show-current` prints nothing | HEAD is detached | Use `git rev-parse HEAD`; only create a branch if you need to keep new commits |
| `git log` shows only a few commits | Clone used `--depth` | Check `git rev-parse --is-shallow-repository`, then deepen if needed |
| `git merge-base` finds no ancestor | Common commit lies outside the shallow boundary | Fetch more history or unshallow |
| `git describe` cannot find version tag | Tag or related history has not been fetched | Fetch tags and expand history |
| `git checkout <commit>` reports object not found | Commit is not in the object database yet | Fetch the ref containing the commit or the right refspec first |
| Commit created in CI does not appear on a branch | Job ran in detached HEAD and created no ref pointing to the commit | Create a branch before committing or push the OID to a suitable ref |
| Push from CI is rejected | Token/SSH key lacks write permission or branch protection blocks it | Check permissions and remote branch rules |
| `--unshallow` fails to fetch full history | Remote is also shallow, refspec is wrong, or server restricts it | Inspect remote and fetch required refs |
| Fetched tags but changelog is still incomplete | Tags were downloaded while ancestry remains shallow | Deepen or unshallow the relevant branch |

## 15. CI checkout design checklist

Before choosing a checkout configuration, determine:

1. Does the pipeline need to build a branch tip, a tag, or an exact commit SHA?
2. For pull requests, should it test the contributor's commit or the merge result?
3. Does the job need to create commits/branches, or only build and test?
4. Does the task need full history to compute versions, changelogs, blame, or merge-base?
5. Have required tags and branches been fetched?
6. If cloning shallowly, is the current depth sufficient for the task?
7. Do build logs record the actual OID of `HEAD`?
8. If creating commits, is a branch/ref keeping them and does the remote grant push permission?

Do not download full history for every job if only a snapshot is needed for testing. Conversely, do not keep a depth-1 clone when a release step needs to compare tags, count commits, or find a merge-base. Choose depth based on actual pipeline needs and verify results before relying on history.

## Conclusion

In automated environments, detached HEAD is a normal state when Git checks out a specific commit; it does not prevent building or testing. Only create a branch when the job needs to retain new commits under a named ref. Shallow clones limit downloaded history, speeding up checkouts, though they can cause incomplete results for log, merge-base, describe, blame, and changelogs. Use `git rev-parse --is-shallow-repository` to check, `git fetch --deepen` to fetch a portion more, or `git fetch --unshallow` when full history is required. Always record the actual OID built and choose a fetch scope matched to the pipeline's task.

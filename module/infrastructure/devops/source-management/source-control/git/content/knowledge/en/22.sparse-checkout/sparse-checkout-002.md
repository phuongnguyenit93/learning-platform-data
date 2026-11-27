# Limiting history depth with --depth and --shallow-since

A full Git repository can contain years of history with thousands or millions of commits. When you only need to fetch source code to build, run tests, or deploy a recent version, downloading the entire history can waste time and storage unnecessarily. **Shallow clone** allows you to fetch a repository with limited history, reducing the number of commits and objects that must be downloaded initially.

Git provides two common ways to choose the history boundary:

- `--depth=<n>` limits the depth by number of commits starting from the tip of the fetched branch.
- `--shallow-since=<date>` limits history by a point in time, keeping only commits reachable after the specified date.

These two options change the portion of commit history the repository can see. They do not select directories in the working tree, nor do they filter individual file contents. To understand the scope properly, it is important to distinguish shallow clone from partial clone and sparse checkout.

## 1. What is a shallow clone?

A shallow clone is a clone whose history is truncated at one or more boundaries. Git downloads the commits and objects needed for the selected slice of history, without downloading all ancestors of those commits.

For example, suppose the full repository has this history:

~~~text
A---B---C---D---E---F---G  main
~~~

If cloned with `--depth=3`, the visible history may include only the three commits near the tip:

~~~text
        E---F---G  main
        ^
        shallow boundary
~~~

Commits A through D are absent from the cloned history. Commit E is treated as the start of local history even though in the original repository its parent is D.

Git stores shallow boundary information in repository metadata. Consequently, history traversal commands know not to follow parents past that boundary.

A shallow clone is still a normal Git repository for basic operations: it has a working tree, index, branches, commits, and remotes. You can edit files, create new commits, and push in cases permitted by the server. The difference is that operations requiring full ancestor history may be limited.

## 2. How does a shallow clone differ from a regular clone?

| Characteristic | Full clone | Shallow clone |
|---|---|---|
| Commit history | Fetches history for the cloned ref scope, usually complete | Truncated by depth or date boundary |
| Initial size | Can be large if history spans many years | Usually smaller because older history is omitted |
| Clone speed | Depends on the volume of objects to download | Usually faster on repositories with large history |
| Long-term history traversal | Can trace all cloned history | Stops at the shallow boundary |
| Merge/rebase/merge-base | Has full cloned ancestry | May lack necessary ancestors |
| Best suited for | Long-term development, history analysis, releases | CI, builds, or tasks needing only recent history |

Shallow clone does not mean downloading only one file or one directory. If you clone a normal branch, Git still checks out that branch's directory tree; what is limited is the commit history.

## 3. Creating a shallow clone with --depth

The `--depth=<n>` option limits history by the number of commits from the tips of fetched branches.

Clone fetching only the latest commit of the main branch:

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
~~~

In the example:

- `--depth=1` fetches only one commit level from the tip.
- `--branch main` selects the main branch to check out.
- `--single-branch` fetches history only for the specified branch.

When using `--depth`, Git implicitly applies single-branch behavior by default unless you specify `--no-single-branch`. Writing `--single-branch` explicitly is still useful because it makes the command's intent clear.

Clone with depth 20:

~~~bash
git clone --depth=20 --branch main https://example.com/team/app.git
~~~

This clone can traverse roughly 20 commits from the tip of the main branch, depending on the commit graph structure and the fetched branches/refs.

### Fetching multiple branches with limited depth

If you want to fetch remote branches instead of just one branch, use `--no-single-branch`:

~~~bash
git clone --depth=10 --no-single-branch https://example.com/team/app.git
~~~

Git fetches the branches within the clone scope while limiting their history to the chosen depth. This command is useful when a pipeline needs to compare multiple branches or inspect several release branches.

Consider how many branches you actually need. Fetching many branches with a depth limit can still download significantly more objects than cloning a single branch.

## 4. Depth is commit count, not number of days

`--depth` expresses history depth in commits, not a time interval.

Suppose repositories have different development velocities:

- One project might create 100 commits in a single day.
- Another project might create only 10 commits in a month.

With `--depth=50`, both fetch a scope of at most 50 commits from the selected tip, even though the historical time span covered is very different.

In a graph with merge commits, history is not always a straight line. A tip can have multiple parents and Git must traverse ancestry following the graph structure. Therefore, you should not interpret depth as "the 50 most recent commits chronologically across the entire repository" or "50 commits on a single linear branch".

If the goal is to keep a recent time window, `--shallow-since` usually expresses that requirement more clearly.

## 5. Limiting history by date with --shallow-since

The `--shallow-since=<date>` option creates a shallow clone with history consisting of commits reachable after the specified point in time.

For example, fetching history since January 1, 2025:

~~~bash
git clone --shallow-since="2025-01-01" https://example.com/team/app.git
~~~

You can specify the branch and remote branch to fetch:

~~~bash
git clone --shallow-since="2025-01-01" --branch main --single-branch https://example.com/team/app.git
~~~

Unlike `--depth`, `--shallow-since` does not automatically imply single-branch mode. `--branch main` selects the branch to check out; if you only want history for that branch, add `--single-branch` as in the example above.

Git uses the timestamp to determine the history boundary. Commits older than the threshold can be omitted from the clone, even though they remain ancestors of newer commits in the original repository.

Example:

~~~text
2024-10   A---B
               \
2025-01         C---D---E
                    main
~~~ 

If you choose `--shallow-since="2025-01-01"`, Git can fetch commits C, D, and E, while placing the boundary at C instead of walking further to older parents.

### Choosing a date format

Git accepts date formats understood by Git's date parser. To keep commands readable and consistent across environments, prefer ISO dates:

~~~bash
git clone --shallow-since="2025-01-01T00:00:00Z" https://example.com/team/app.git
~~~

You can use relative date expressions if needed:

~~~bash
git clone --shallow-since="6 months ago" https://example.com/team/app.git
~~~

Put the date value in quotation marks so the shell passes the entire string as a single argument. For reproducible pipelines, absolute dates are usually better than relative dates because the same command produces the same cutoff across different runs.

## 6. Comparing --depth and --shallow-since

| Criterion | `--depth=<n>` | `--shallow-since=<date>` |
|---|---|---|
| How the boundary is set | By commit count from tip | By timestamp |
| Best when | Only a few most recent commits are needed | History within a recent time window is needed |
| Effect when commit frequency changes | Commit count remains bounded by depth | Commit count can grow or shrink with project activity |
| Example | `--depth=30` | `--shallow-since="2025-01-01"` |
| How it expresses the goal | "Fetch 30 commit levels near the tip" | "Fetch history after the chosen date" |

Neither option is universally better. If CI only needs the latest source code, a small depth may suffice. If a team needs to analyze changes over the past three months, a date cutoff may make more sense.

A repository with many commits in a single day can produce a very large shallow clone with `--shallow-since`. Conversely, a repository with few commits might contain only a handful of commits over several months. Choose based on the actual task and measure time/storage in your pipeline.

## 7. Checking whether a repository is shallow

After cloning, you can check the state with:

~~~bash
git rev-parse --is-shallow-repository
~~~

Output:

~~~text
true
~~~

means the repository is currently a shallow repository. A result of `false` means Git does not mark this repository as shallow.

View remote and branch configuration:

~~~bash
git remote -v
git branch -vv
git branch -r
~~~

Inspect available history:

~~~bash
git log --oneline --graph --decorate --all
~~~

If history stops abruptly at an old commit when you know the original repository has earlier ancestors, the clone may be depth-limited. Use `git rev-parse --is-shallow-repository` to confirm instead of relying solely on the line count in `git log`.

You can ask Git for the shallow metadata path:

~~~bash
git rev-parse --git-path shallow
~~~

This path points to the internal file recording the shallow boundaries. Use it to understand the state or aid diagnostics; do not edit this file manually. Change depth using the fetch commands supported by Git.

## 8. Expanding history after a shallow clone

A pipeline can start with a small depth to save time, then fetch additional history when needed.

### Setting a target depth with --depth

Suppose the repository initially has depth 10, and now needs deeper history up to 100 commits:

~~~bash
git fetch --depth=100 origin refs/heads/main:refs/remotes/origin/main
~~~

When fetching into a shallow repository, `--depth=<n>` sets the target depth from the tip of the fetched branch. This value can make history deeper or shallower than the previous state.

### Extending by a number of commits with --deepen

If you want to extend by 50 additional commits from the current shallow boundary:

~~~bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
~~~

Distinction:

- `--depth=100`: requests a total depth of 100 from the tip.
- `--deepen=50`: extends by 50 commits from the current shallow boundary.

The two options address two different ways of specifying the extension. When a pipeline runs iteratively, `--deepen` can be useful if you want to grow history step by step; `--depth` fits when you want a specific total depth.

### Extending by timestamp

If you initially cloned by date, you can request more history using an earlier cutoff:

~~~bash
git fetch --shallow-since="2024-07-01" origin refs/heads/main:refs/remotes/origin/main
~~~

The command requests history including commits reachable after the new date cutoff. Pick an earlier date to fetch older history.

### Fetching full history with --unshallow

When full history is needed and the remote has full history:

~~~bash
git fetch --unshallow origin
~~~

This command converts a shallow repository into one without shallow boundaries by fetching the missing history. If the source repository on the remote is also shallow, Git can only fetch the history that source has.

After fetching, verify again:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all
~~~

A result of `false` indicates the local repository is no longer in a shallow state.

## 9. Combining with branches and refspecs when fetching

A shallow clone is often created for a single branch. When you need to fetch another branch, specify the remote and refspec explicitly to avoid fetching out of scope.

Example of fetching an additional release branch:

~~~bash
git fetch --depth=30 origin refs/heads/release/2.x:refs/remotes/origin/release/2.x
~~~

Then inspect:

~~~bash
git branch -r
git log --oneline --decorate origin/release/2.x
~~~

Fetch updates the remote-tracking ref. It does not automatically switch your current local branch to the fetched branch, nor does it merge commits into the working tree.

If you need to work on that branch:

~~~bash
git switch -c release/2.x --track origin/release/2.x
~~~

In a shallow repository, creating a branch from a remote-tracking ref is still possible, but the ancestry history of the new branch remains limited by the existing shallow boundaries.

## 10. Shallow clones and tags

A tag is a label attached to an object, usually a commit. In a shallow clone, tags associated with the fetched history may be retrieved automatically, but you should not assume every old tag in the repository is already local.

Check existing tags:

~~~bash
git tag --list
~~~

If a specific tag is needed:

~~~bash
git fetch origin tag v2.0.0
~~~

A tag may point to a commit outside the currently available history. Fetching a tag does not mean all ancestors of that commit have been downloaded. If you need to inspect history prior to that version, you may need to deepen or unshallow further.

Some commands like `git describe` rely on tags and may produce different results than a full clone if the relevant tag wasn't fetched or the ancestor commit lies beyond the shallow boundary. In CI that generates version strings, ensure the fetch strategy retrieves the tags and history the command requires.

## 11. Impact of shallow boundaries on Git operations

Shallow clones are well suited for short-lived tasks, but truncated history can affect operations that rely on ancestry.

| Operation | Possible impact |
|---|---|
| `git log` | History stops at the shallow boundary |
| `git merge-base` | May fail to find a merge base due to missing ancestors |
| `git merge` | May need to fetch additional history to compute ancestry relationships |
| `git rebase` | May lack the base commit or history to select the right commit set |
| `git blame` | Cannot trace authors/changes prior to the boundary |
| `git bisect` | Cannot test commits outside the downloaded history |
| `git describe` | May lack tags or ancestors needed to find the nearest tag |
| Release/changelog analysis | May miss commits and tags from previous versions |

Not all of these commands always fail in a shallow clone. They are only limited when the task needs history that hasn't been downloaded. When encountering missing results or failing to find a merge base, check the shallow status and fetch more history before concluding the repository lacks the commit you are looking for.

## 12. Limitations when pushing from a shallow repository

Shallow clones primarily optimize data retrieval. When pushing, the server needs to verify the historical relationship between the pushed commits and the target ref.

If a shallow boundary omits commits needed to verify the update, the server may reject the push or require fetching additional history. Exact behavior also depends on server configuration and protocol.

If a push is rejected due to shallow history:

1. Read the error message and identify which ref was rejected.
2. Fetch more history from the remote.
3. Check the relationship between the local branch and the remote-tracking branch.
4. Integrate changes according to the team's workflow.
5. Push again after confirming the history is consistent.

Example:

~~~bash
git fetch --unshallow origin
git log --oneline --graph --decorate --all
git push origin feature/payment
~~~

Do not use force push to bypass missing-history issues. Force pushing can overwrite remote history and cause other contributors' commits to be lost.

## 13. Shallow clones in CI/CD

Shallow clones are often useful in pipelines because runners only need the source code of the commit being built or a short history span to run tests.

Example pipeline that needs to build the current commit:

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
cd app
git rev-parse --short HEAD
./gradlew test
~~~

If the pipeline needs to compare against a base commit—for example, checking changes between the current branch and main—depth 1 may not be enough. You need to fetch the target branch and required history:

~~~bash
git fetch --depth=100 origin refs/heads/main:refs/remotes/origin/main
git merge-base HEAD origin/main
~~~

If the pipeline generates a changelog from the latest tag, it needs to fetch the appropriate tags and sufficient ancestry:

~~~bash
git fetch --tags --unshallow origin
git describe --tags --abbrev=0
~~~

The example above uses unshallow when full history is required. If the repository is very large, you can choose a sufficient depth or shallow-since instead of always downloading everything.

### Choosing depth by pipeline goal

| CI goal | Common choice |
|---|---|
| Build a single commit, run unit tests | `--depth=1` |
| Compare a few recent commits | Depth large enough for the comparison range |
| Generate changelog per release | Fetch tags and history since the previous release milestone |
| Run `git bisect` | Needs the entire commit range to search for the bug |
| Check a merge request | Fetch both target branch and enough history to compute merge base |
| Generate version with `git describe` | Fetch tags and required ancestry |

A smaller depth generally makes the clone lighter, but the pipeline may have to fetch more in later steps. Balance clone time against the requirements of each job.

## 14. Distinguishing shallow clone, partial clone, and sparse checkout

This chapter groups techniques for reducing the footprint of a Git copy. The three techniques have different targets:

| Technique | What does it limit? | Primary mechanism | Example |
|---|---|---|---|
| Shallow clone | Commit history | Truncates ancestry at shallow boundaries | `git clone --depth=20` |
| Partial clone | Downloaded objects | Filters objects, can fetch missing objects on demand | `git clone --filter=blob:none` |
| Sparse checkout | Paths in the working tree | Materializes only selected directories/files | `git sparse-checkout set src docs` |

### Shallow clone

Reduces the amount of commit history downloaded. The working tree can still contain all files of the checked-out branch. Commits older than the boundary are absent from local history.

### Partial clone

Reduces objects downloaded from the server using object filters. For example, `--filter=blob:none` defers downloading blobs until needed. Commit history can remain complete if not combined with a shallow option.

Partial clone requires server-side filtering support and the promisor remote mechanism. When a tool accesses a blob that is not yet present, Git can retrieve that object from the remote via lazy fetch.

### Sparse checkout

Reduces the number of paths appearing in the working tree. The repository may still have the full history and needed objects; only the set of files materialized in the working tree is restricted. Sparse checkout is useful in monorepos when users work with only a subset of directories.

Techniques can be combined when appropriate:

- Shallow clone to limit history.
- Partial clone to reduce initially downloaded blobs.
- Sparse checkout to restrict files appearing in the working tree.

Combining multiple mechanisms makes configuration and troubleshooting more complex. Choose based on the actual bottleneck: overly large history, overly large file objects, or a working tree with too many directories.

## 15. When should and shouldn't you use shallow clone?

Shallow clone is a good fit when:

- CI only needs to build/test the latest commit.
- Runners or ephemeral environments need fast checkouts.
- A job only needs a short window of history.
- The repository is large and the pipeline does not perform operations requiring deep ancestry.
- Runner disk storage is constrained.

Consider a full clone when:

- Doing long-lived feature development with frequent rebases/merges.
- Investigating bugs requiring `git blame` or `git bisect` across old history.
- Generating changelogs, release notes, or versions based on longstanding tags.
- Auditing history, verifying commit provenance, or comparing multiple long-lived branches.
- Build tools require a merge base or full ancestry.

Shallow clone is not the best default for every repository. If a task routinely has to unshallow right after cloning, either the initial depth is too small or shallow clone is not suitable for that pipeline.

## 16. Common errors and how to resolve them

| Symptom | Possible cause | Resolution |
|---|---|---|
| `git log` stops at an old commit | Repository is shallow | Check `git rev-parse --is-shallow-repository`, fetch more history |
| `git merge-base` finds no result | Missing ancestors due to shallow boundary, or the two branches genuinely share no common ancestor | Fetch target branch and deepen/unshallow, then retry |
| Old release tags are missing | Tags are not in the fetched ref/object set | Fetch required tags and related history |
| Rebase or merge fails with shallow-related error | Missing base commit or ancestry | Fetch more history before integrating |
| Pipeline builds, but changelog is wrong/incomplete | Depth is insufficient for the changelog tool | Fetch from the previous tag or release milestone |
| Clone with small depth still downloads lots of data | Multiple branches/refs fetched or large file objects | Check single-branch and consider partial clone |
| `git fetch --unshallow` does not retrieve full history | Source remote is also shallow or server restricts it | Check remote source and server policy |
| Push is rejected | Server cannot verify update relationship from truncated history | Fetch more history, inspect log, then push again |

Do not edit the shallow metadata file directly to fix issues. Use the fetch options provided by Git and check status after each history expansion.

## 17. Sample workflow: lightweight clone, then expand when needed

Suppose a pipeline builds the main branch and only needs the single latest commit for most jobs.

**Step 1 — Shallow clone**

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
cd app
~~~

**Step 2 — Confirm state**

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -5
~~~

**Step 3 — Run tasks that do not need deep history**

~~~bash
./gradlew test
~~~

**Step 4 — When comparing against main or generating a changelog, fetch more history**

~~~bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
git log --oneline --graph --decorate --all
~~~

**Step 5 — If the task requires full history, unshallow**

~~~bash
git fetch --unshallow origin
git rev-parse --is-shallow-repository
~~~

**Step 6 — Continue the task**

~~~bash
git merge-base HEAD origin/main
~~~

This approach keeps the initial clone step lightweight while still letting the pipeline fetch additional data right when needed. In a stable workflow, measure time and storage to determine a sensible initial depth.

## 18. Checklist before choosing history depth

- [ ] How many commits does the job need to build/test?
- [ ] Is a merge-base with the target branch required?
- [ ] Are `git describe`, a changelog, or old tags needed?
- [ ] Will `blame`, `bisect`, `rebase`, or history analysis be run?
- [ ] Is one branch or multiple branches needed?
- [ ] Choose depth by commit count or by timestamp?
- [ ] Does the remote support fetching more or unshallowing?
- [ ] Does the pipeline include a step to expand history when needed?
- [ ] Have you verified with `git rev-parse --is-shallow-repository`?
- [ ] Could partial clone or sparse checkout address a different bottleneck?

## 19. Key points to remember

- A shallow clone is a repository whose commit history is truncated at shallow boundaries.
- `--depth=<n>` limits depth by commit count from the tip; not number of days and not number of files.
- `--shallow-since=<date>` limits history by a timestamp.
- `--depth` implies single-branch by default unless `--no-single-branch` is used.
- Use `git rev-parse --is-shallow-repository` to check the status.
- Use `git fetch --depth`, `--deepen`, or `--shallow-since` to fetch more history; `--unshallow` to retrieve everything when the remote has it.
- Shallow boundaries can affect merge-base, merge, rebase, blame, bisect, describe, and changelogs.
- Shallow clone limits history; partial clone filters objects; sparse checkout limits paths in the working tree.
- Choose depth based on the actual needs of CI/CD or development work, and expand history when the task requires it.

Shallow clone helps reduce the time and storage required to fetch a repository by downloading only part of the history. When you choose appropriately between commit count and timestamp, while understanding ancestry limits, you can speed up pipelines and still fetch enough history for each task.

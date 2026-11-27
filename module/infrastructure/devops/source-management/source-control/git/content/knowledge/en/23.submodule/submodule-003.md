# Adding a Submodule and Recording Changes in the Parent Repository

When a project needs to use another Git repository as a library or independent component, you can add that repository to the project as a **submodule**. The repository containing the submodule is called the parent repository (superproject); the embedded repository is the child repository (submodule). The two repositories have separate commit histories, while the parent repository records the exact commit that each submodule must use.

The key point is that the parent repository does not include all the submodule's files in its own history. Instead, it stores a reference to a commit in the child repository, along with URL and path information in `.gitmodules`. Consequently, when you modify source code inside a submodule, you must commit the change in the child repository first, then update and commit the submodule pointer in the parent repository.

## 1. What Components Make Up a Submodule?

Suppose an application project has the following structure:

```text
sample-app/
├── .git/
├── .gitmodules
├── src/
└── libs/
    └── math-core/     <- an independent Git repository
```

Here:

- `sample-app` is the parent repository, with its own `.git` and commit history.
- `libs/math-core` is a submodule, with its own repository and commit history.
- `.gitmodules` stores information so Git knows which submodule resides at which path and which URL to fetch it from.
- The parent repository's tree contains a gitlink entry pointing to a specific commit of the submodule.

A submodule has two main pieces of information in the parent repository:

| Component | Role |
|---|---|
| `.gitmodules` | Configuration file committed in the parent repository, mapping submodule name, path, and URL; may declare branch or update strategy |
| Gitlink | Entry in the parent repository's tree/index, mode `160000`, pointing to the OID of the submodule commit to check out |

A gitlink is a reference to a commit, not a directory containing the submodule's blobs. When checking out a parent commit, Git knows which commit the submodule needs to be at; submodule commands fetch the child repository and check out that exact commit.

## 2. Adding a Submodule to the Parent Repository

Suppose you are in the root directory of `sample-app` and want to add a library from a repository:

```bash
git submodule add https://github.com/example-org/math-core.git libs/math-core
```

This command performs the following main actions:

1. Clones the `math-core` repository into the path `libs/math-core`.
2. Registers the submodule in the parent repository's configuration.
3. Creates or updates the `.gitmodules` file.
4. Stages `.gitmodules` and the submodule's gitlink into the parent repository's index.

If you omit the destination path, Git typically uses the repository name as the submodule directory. Specify an explicit path so the project structure stays clear and predictable.

If you want the submodule to track a specific branch when running `git submodule update --remote`, you can add `-b`:

```bash
git submodule add -b main https://github.com/example-org/math-core.git libs/math-core
```

The `-b main` option writes the tracked branch setting into `.gitmodules`. It does not cause the parent repository to automatically pull every new commit from that branch; the parent repository still only records a gitlink commit when you update and commit changes in the parent repository.

If the target directory already exists and is non-empty, or is already a repository managed differently, `git submodule add` may refuse the operation. Choose a non-existent path or reconcile the existing directory's repository state before adding.

## 3. Inspecting `.gitmodules` and the Gitlink

After adding, check the parent repository's status:

```bash
git status
git diff --cached
git diff --cached --submodule=log
```

Normally, `git submodule add` has already staged two changes: `.gitmodules` and the gitlink at `libs/math-core`. The contents of `.gitmodules` will look similar to:

```ini
[submodule "libs/math-core"]
    path = libs/math-core
    url = https://github.com/example-org/math-core.git
    branch = main
```

`branch = main` appears only if you configured a tracked branch, for example with `git submodule add -b main`. If not specified, Git does not write a `branch` field into `.gitmodules`.

Inspect the gitlink entry in the index:

```bash
git ls-files --stage -- libs/math-core
```

The output has the form:

```text
160000 <submodule-commit-oid> 0    libs/math-core
```

Mode `160000` indicates this is a gitlink. The OID following it is the commit that the parent repository is recording for the submodule. You can inspect the commit stored in the parent commit's tree with:

```bash
git ls-tree HEAD -- libs/math-core
```

If the submodule has only been staged and not yet committed in the parent repository, `git ls-tree HEAD` still shows the state of the previous parent commit; use `git ls-files --stage` to inspect the staged value in the index.

## 4. Committing the Submodule Addition in the Parent Repository

After verifying the URL, path, and gitlink commit, create a commit in the parent repository:

```bash
git diff --cached -- .gitmodules
git diff --cached --submodule=log
git commit -m "Add math-core submodule"
```

This commit records:

- The `.gitmodules` file with the submodule's path and URL.
- The mode `160000` gitlink with the `math-core` commit OID.

It does not copy the source code contents of `math-core` into the parent repository. When others clone the parent repository, they need to initialize the submodule to fetch the child repository's contents.

After committing, verify:

```bash
git show --summary --submodule=log HEAD
git ls-tree HEAD -- libs/math-core
```

If the parent repository has a remote, push the commit containing `.gitmodules` and the gitlink according to the team's workflow:

```bash
git push origin main
```

Before pushing the parent repository, make sure the referenced submodule commit already exists on a remote accessible to collaborators. If the commit only exists in your local clone, others can clone the parent repository but will fail to download the right submodule commit.

## 5. Modifying Source Code Inside the Submodule

Because a submodule is an independent repository, run Git commands inside the submodule directory. For example, update the library and create a commit:

```bash
# Enter the child repository
cd libs/math-core

# Check the child repository's branch and status
git status
git branch --show-current

# Create a working branch to hold the new commit
git switch -c feature/matrix-helper

# Edit library source code
git add src
git commit -m "Add matrix helper"

# Push the new commit to the child repository's remote
git push -u origin feature/matrix-helper

# Return to the parent repository root
cd ../..
```

Running `git commit` inside `libs/math-core` only updates the child repository's history. The parent repository does not automatically change its gitlink just because you made a commit inside the submodule. The example above creates a dedicated branch before committing because a submodule is usually in detached HEAD after the parent repository checks out a specific gitlink. The commit OID recorded by the parent repository can belong to any branch; what matters is that the commit is reachable from a remote that other team members are allowed to fetch.

## 6. Updating the Gitlink in the Parent Repository

After committing inside the submodule, return to the parent repository and check its status:

```bash
git status
git diff --submodule=log
```

When the submodule's HEAD differs from the OID recorded by the parent repository, Git displays the submodule as modified. To update the gitlink in the parent repository's index, run:

```bash
git add libs/math-core
```

This command stages the commit OID currently checked out in the submodule. It does not stage individual files inside the child repository; those files must be committed in the child repository first.

Inspect the staged changes:

```bash
git diff --cached --submodule=log
git ls-files --stage -- libs/math-core
```

Then create a commit in the parent repository:

```bash
git commit -m "Update math-core submodule"
```

The new commit in the parent repository now points to the new commit in `math-core`. Two commits are stored in two separate repositories: the library commit lives in the child repository; the pointer-update commit lives in the parent repository.

## 7. Push Order So Teammates Can Fetch the Submodule

When changing both the submodule's source code and the parent repository's gitlink, push the child repository first and then push the parent repository:

```bash
# Push the child repository's commit first
git -C libs/math-core push origin feature/matrix-helper

# After the gitlink has been staged and committed in the parent repository
git push origin main
```

This order ensures the commit referenced by the gitlink already exists on the submodule remote before the parent repository publishes that OID. If you push the parent repository first while the submodule commit has not yet been shared, others will encounter errors when initializing or updating submodules.

If the submodule commit was pushed to a feature branch instead of `main`, verify the remote and teammates' permissions. The gitlink stores a commit OID, not a branch name. The `branch` field in `.gitmodules` only helps select a branch for remote update operations; it does not replace the OID recorded by the parent repository.

## 8. Cloning the Parent Repository and Initializing Submodules

Collaborators can clone the parent repository along with all submodules recursively:

```bash
git clone --recurse-submodules https://github.com/example-org/sample-app.git
```

If the parent repository was already cloned without submodules, run:

```bash
git submodule update --init --recursive
```

Meaning of the options:

- `--init` registers and initializes the submodules declared in `.gitmodules`.
- `--recursive` continues initializing submodules nested inside other submodules.
- `update` checks out submodules at the commit recorded by the current parent commit.

This command brings submodules to the exact gitlink commit, typically in detached HEAD. This is expected behavior: the parent repository requires a specific version of the child repository, not everyone automatically tracking the latest branch tip.

Check status:

```bash
git submodule status --recursive
git status
```

In `git submodule status` output, the leading character identifies the state:

| Prefix | Meaning |
|---|---|
| Space | Submodule is at the commit recorded by the parent repository |
| `-` | Submodule has not been initialized |
| `+` | Submodule has checked out a different commit from the parent repository's gitlink |
| `U` | Gitlink is in a merge conflict state |

## 9. Updating a Submodule to a New Commit from Remote

There are two common ways to update a submodule.

### Switching Branches and Updating Manually

If you want to choose a branch explicitly inside the child repository:

```bash
git -C libs/math-core fetch origin
git -C libs/math-core switch main
git -C libs/math-core pull --ff-only origin main
```

Once the submodule is at the new commit, return to the parent repository, stage the gitlink, and commit:

```bash
git add libs/math-core
git diff --cached --submodule=log
git commit -m "Advance math-core submodule"
```

### Updating According to the Branch Configured in `.gitmodules`

If `.gitmodules` has `branch = main`, you can tell Git to fetch the latest commit on that branch:

```bash
git submodule update --remote libs/math-core
```

The `--remote` flag fetches the configured remote-tracking branch for the submodule and updates the checkout to the new commit. If no branch is configured, Git uses the default remote HEAD branch. Afterward, the parent repository still needs to stage and commit the gitlink:

```bash
git status
git add libs/math-core
git diff --cached --submodule=log
git commit -m "Update math-core submodule pointer"
```

`git submodule update --remote` does not automatically commit the gitlink change in the parent repository. Updating which commit is used should be reviewed like a dependency update: inspect releases, API compatibility, tests, and the child repository's commit log before committing the new pointer.

## 10. Distinguishing Changes Inside the Child Repo from Pointer Changes in the Parent Repo

When working with submodules, there are two layers of state:

| Location | Change | Inspection Commands |
|---|---|---|
| Inside child repository | Files modified, staged, or committed in the library | `git -C libs/math-core status`, `git -C libs/math-core log` |
| In parent repository | Gitlink OID changed compared to the referenced parent commit | `git status`, `git diff --submodule=log`, `git ls-files --stage` |

If you modify files inside a submodule without committing them, the parent repository may display the submodule status as having modified content. Running `git add libs/math-core` does not turn those modifications into a commit in the child repository. Commit inside the submodule first, and only then stage the gitlink in the parent repository.

A two-layer inspection sequence:

```bash
# Inspect the child repository
git -C libs/math-core status
git -C libs/math-core log -1 --oneline

# Inspect the pointer recorded by the parent repository
git ls-tree HEAD -- libs/math-core
git ls-files --stage -- libs/math-core

# View gitlink differences
git diff --submodule=log
git diff --cached --submodule=log
```

The first commands inspect the current status and commit in the child repository. The `ls-tree` and `ls-files` commands show the committed OID and staged OID in the parent repository, respectively. `git diff --submodule=log` lets you read the commits changed between two OIDs instead of looking only at a hash.

## 11. Handling Changes to a Submodule's URL or Access Permissions

A submodule's URL is stored in `.gitmodules`. If the child repository moves to a new server, update the URL in the parent repository:

```bash
git config -f .gitmodules submodule.libs/math-core.url https://github.com/new-org/math-core.git
git add .gitmodules
git commit -m "Update math-core submodule URL"
```

After updating `.gitmodules`, synchronize the submodule's local configuration:

```bash
git submodule sync -- libs/math-core
```

If there are nested submodules, you can use `git submodule sync --recursive`. The `sync` command updates URLs in local configuration from `.gitmodules`; it does not change the gitlink commit.

If teammates cannot clone a submodule, check:

1. Whether the URL in `.gitmodules` is accurate and reachable.
2. Whether the commit OID referenced by the gitlink has been pushed to the submodule's remote.
3. Whether collaborators have read access to the child repository.
4. Whether the child repository requires an SSH key, token, or separate organization permissions.
5. Whether the submodule is nested and requires `--recursive`.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| The parent repository stores all submodule source code | The parent repository stores `.gitmodules` and a mode `160000` gitlink pointing to a commit of the child repository. |
| Committing inside the submodule automatically updates the parent repository | No. You must run `git add <submodule-path>` and then commit in the parent repository. |
| `git add libs/math-core` stages all modified files inside the submodule | No. It updates the gitlink to the currently checked-out commit; files inside the submodule must be committed in the child repository. |
| `.gitmodules` contains the submodule's commit OID | `.gitmodules` stores configuration such as path, URL, and branch; the OID is stored in the gitlink of the parent repository's tree/index. |
| A gitlink stores the branch name `main` | A gitlink stores a specific commit OID. Branch names are not what the parent repository uses to pin a version. |
| `git submodule update --remote` automatically commits changes in the parent repository | No. You still need to stage and commit the gitlink in the parent repository. |
| Cloning the parent repository always downloads all submodules completely | You need `--recurse-submodules` when cloning or run `git submodule update --init --recursive` afterward. |
| You can push the parent repository before pushing submodule commits | This can create a reference to an unshared commit; teammates may be unable to fetch that commit. Always push the child repository first. |

## 13. Self-Check

1. **Which command adds another repository as a submodule?**
   - `git submodule add <url> <path>`.
2. **Which file records the submodule's URL and path in the parent repository?**
   - `.gitmodules`.
3. **What mode does a gitlink have, and what information does it store?**
   - Mode `160000`, storing the commit OID required by the parent repository for the submodule.
4. **After committing changes in the child repository, what must be done in the parent repository?**
   - Stage the submodule path with `git add <path>`, inspect the gitlink, and commit the parent repository.
5. **Which command clones the parent repository along with nested submodules?**
   - `git clone --recurse-submodules <url>`.
6. **Why should the submodule be pushed before the parent repository?**
   - So the commit referenced by the gitlink already exists on the remote and teammates can download it.

## Conclusion

Adding a submodule with `git submodule add` registers the child repository in `.gitmodules` and stages a mode `160000` gitlink in the parent repository. All source code changes must be committed in the child repository; only then should the parent repository stage the submodule path to record the new commit OID. When sharing, push the child repository first and then push the parent repository. Collaborators clone with `--recurse-submodules` or initialize with `git submodule update --init --recursive` to check out the exact commit pinned by the parent repository.

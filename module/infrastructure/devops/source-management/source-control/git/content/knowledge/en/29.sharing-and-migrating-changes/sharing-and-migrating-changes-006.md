# Importing History from Another Git Repository and Preserving History Relationships

When merging two Git projects, you must decide whether to bring the source repository's entire history into the target repository, take only selected changes, or copy only the current file state. That decision affects author traceability, reviewing past commits, merging future updates, and maintaining dependencies. Git can connect two histories that share no common commit using `git merge --allow-unrelated-histories`; if you want to place a project into a subdirectory, `git subtree` or rewriting history paths with a specialized tool may be more suitable.

## 1. Two repositories can have independent histories

Every Git repository has its own commit graph. When two repositories are created independently, their root commits share no common ancestor.

Example:

```text
Target repository:               Source repository:

A---B---C  main                   X---Y---Z  main
```

`C` and `Z` have no parent-child relationship and no common ancestor commit. If you add the source repository as a remote and merge normally, Git will refuse because the two histories are unrelated.

This commonly happens when:

- A new project was started in a separate repository and later needs to be imported into a monorepo.
- Two teams developed independently and decide to consolidate products.
- An older repository needs to be moved into a new repository while keeping commit traceability.
- The target repository already has its own README or initial commit, while the source repository also has its own history.

Before importing, define the goal: merge the histories into one graph, keep the source project as an independent component in a subdirectory, bring in selected commits, or take only the current snapshot. There is no single approach that fits every case.

## 2. Inspecting both histories before importing

First, inspect the target repository and working state:

```bash
git status -sb
git log --oneline --graph --decorate --all
```

The working tree should be clean before a merge operation. If there are uncommitted changes, commit or stash them per your workflow to avoid mixing in-progress work into the history import.

Add the source repository as a remote and fetch refs:

```bash
git remote add legacy https://git.example.com/team/legacy-app.git
git fetch legacy
```

`git fetch` downloads objects and updates remote-tracking refs such as `legacy/main`; it does not modify the current branch or working tree. View the source branches:

```bash
git branch --remotes
git log --oneline --graph --decorate legacy/main
```

Check whether the two tips share a common ancestor:

```bash
git merge-base main legacy/main
```

If the command returns a commit ID, the two histories share a common ancestor and can be integrated with a regular merge. If there is no output and it exits with a non-zero code, the two histories may be unrelated; confirm the right branches and repositories before choosing an import method.

You can check more explicitly with:

```bash
git merge-base --is-ancestor main legacy/main
git merge-base --is-ancestor legacy/main main
```

These two commands check ancestry in each direction. Exit code `0` means the first commit is an ancestor of the second; a non-zero exit code means that relationship does not hold. If neither is an ancestor of the other yet `git merge-base main legacy/main` produces output, the two branches have diverged while still sharing history. If there is no merge base, the histories may be independent.

## 3. Preserving state before importing

Before an operation that can introduce broad changes, create a branch marking the current state:

```bash
git switch main
git branch backup/main-before-import
```

The backup branch preserves the current tip so you can compare or revert if the import needs to be redone. If the repository has release tags or critical refs, record them according to your team's backup policy.

Check remotes and the source URL:

```bash
git remote -v
git config --get-regexp '^remote\.'
```

Verify the URL, access permissions, and source commits with the repository maintainers. When importing code from an unverified source, review `.gitattributes`, `.gitmodules`, `.lfsconfig`, hooks/bootstrap scripts, and dependencies before checking out or running builds.

## 4. Connecting two histories with `--allow-unrelated-histories`

If you want to preserve the history of both the target and source repositories in the same graph, use:

```bash
git switch main
git merge --allow-unrelated-histories legacy/main
```

The `--allow-unrelated-histories` option tells Git to create a merge between two tips with no common ancestor. Git does not rewrite the old commits from either side; it creates a new merge commit with two parents:

```text
      A---B---C---------M  main
                         /
X---Y---Z---------------
```

In the diagram, `M` is the new merge commit. One parent is the tip of the target history (`C`), and the other parent is the tip of the source history (`Z`). Old commits retain their object IDs; the graph now has a connection point.

This is the right choice when:

- Two projects must become a single repository and both histories need to be preserved.
- You want to keep tracing commits, authors, timestamps, and parent-child relationships of the source repository.
- A merge commit joining the two history roots is acceptable.

The new merge commit only connects the histories; it does not automatically resolve filename or project structure conflicts.

## 5. Handling conflicts when both repositories share root files

Two independent repositories often both contain files like `README.md`, `.gitignore`, `LICENSE`, or build configs. During the merge, Git may report conflicts because both histories created content at the same paths without a common ancestor to compare changes against.

Check status:

```bash
git status
git diff --name-only --diff-filter=U
```

Open each conflicted file and decide the final content. Example:

```text
<<<<<<< HEAD
# Application Platform
=======
# Legacy Service
>>>>>>> legacy/main
```

The markers above are illustrative. Combine the desired content, remove the markers, and stage the resolved files:

```bash
git add README.md .gitignore
git status
git diff --cached
git commit
```

When a merge stops due to conflicts, running `git commit` after staging everything completes the merge if Git expects a merge commit. You can also use `git merge --continue` in the corresponding merge workflow.

If you realize you chose the wrong source or want to redesign the import approach, abort the paused merge:

```bash
git merge --abort
```

Then check the backup branch and repeat the workflow with the right scope. Do not manually delete files inside `.git` to exit a merge state.

## 6. Verifying the graph after merging

After the merge completes:

```bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
git rev-list --count main
```

For a merge commit, `git show --pretty=raw` displays two `parent` lines. Confirm that both the old history tip and the source tip are ancestors of the merge commit:

```bash
git merge-base --is-ancestor backup/main-before-import HEAD
git merge-base --is-ancestor legacy/main HEAD
```

If both commands return exit code `0`, the current merge commit contains both histories by ancestry. Inspect the tree contents and run required tests/builds to confirm integration.

Once verified, you can keep the `legacy` remote to continue fetching source changes, or remove the remote if it was only for a one-time import:

```bash
git remote remove legacy
```

Removing the remote only removes local config and related remote-tracking refs; it does not delete the source repository or commits already connected into the target history.

## 7. When you want to import the source repository into a subdirectory

If the target repository is a monorepo and you want to place the entire source repository inside a directory such as `components/legacy-app/`, merging directly at the root can cause many filename conflicts and mix project structures.

In this case, `git subtree` is often suitable. Subtree places the source repository's contents under a prefix in the target repository and can preserve source history in the commit graph.

Example:

```bash
git remote add legacy https://git.example.com/team/legacy-app.git
git fetch legacy
git subtree add --prefix=components/legacy-app legacy main
```

The command above imports the contents of `legacy/main` into `components/legacy-app/` and creates a merge commit connecting the histories. Omit `--squash` if the goal is to keep the traceable source commit chain.

If you only want to record a single combined commit for the import, use:

```bash
git subtree add --prefix=components/legacy-app --squash legacy main
```

With `--squash`, Git creates one squashed commit representing the source contents at import time instead of bringing the entire source commit chain into the target history as a full subtree. This keeps the main project's visible history shorter, at the cost of not seeing individual source commits directly in the main graph.

`git subtree` may not be pre-installed in every Git distribution or minimal environment. If Git reports `subtree` is not a valid command, install or enable the Git subtree component using your environment's package management. Do not substitute an unverified script downloaded from an untrusted source.

## 8. Rewriting source history to move all files into a prefix

Another option is rewriting the source repository's history so every commit places its contents under a subdirectory. The `git filter-repo` tool supports this, for example:

```bash
git clone --no-local https://git.example.com/team/legacy-app.git legacy-filtered
cd legacy-filtered
git filter-repo --to-subdirectory-filter components/legacy-app
```

After the operation, the source commits are recreated with trees shifted into `components/legacy-app/`. Internal parent-child relationships in the commit chain are preserved, but object IDs change because tree and commit contents changed. Old commit signatures will no longer validate for the rewritten commits.

Afterward, you can fetch the filtered history into the target repository and connect them via an unrelated-histories merge. This workflow is more complex than subtree and requires checking refs, tags, branches, signed commits, and external repository references before applying.

Only use `git filter-repo` when there is a clear reason, such as needing to move the entire history into a prefix, strip sensitive data, or standardize repositories. Back up the source repository, notify users, and plan force-updates on remotes if shared history is rewritten.

## 9. Taking only specific commits with cherry-pick

If you do not need the entire source history, but want to bring specific changes into the target repository, you can use `cherry-pick`.

After fetching:

```bash
git log --oneline legacy/main
git switch -c import/fix-selected main
git cherry-pick <commit-id>
```

Git applies the changes of the selected commit onto the current branch and creates a new commit. The new commit's parent is in the target history, so it does not preserve ancestry with the source commit. Author information is normally preserved, while the committer and commit ID reflect the commit created in the target repository.

Cherry-pick is appropriate when:

- Only an independent bug fix or feature is needed.
- You do not want to bring the entire source repository into the target history.
- The team accepts new history recording re-applied changes instead of joining the two graphs.

If you need to bring over multiple interdependent commits, choose the range and ordering carefully. After cherry-picking, run tests and inspect diffs; do not assume the new commit is identical to the source object.

## 10. Copying only the current snapshot

If you only need current file contents without source history, you can copy the files into the target repository and commit them as a new change. For example, using archive to extract a snapshot of the source branch:

```bash
mkdir -p imported-files
git archive --format=tar legacy/main | tar -xf - -C imported-files
```

Then place the selected contents into the target directory and commit:

```bash
git add imported-files/
git commit -m "Import legacy application snapshot"
```

This method imports only the exported snapshot; the source repository's commit history does not become an ancestor of the target repository. Record the source, branch, commit ID, and import date in the commit message or documentation for future traceability.

If files belong in a subdirectory, extract the archive directly into the target directory from the start or move contents before staging. Check paths carefully to avoid overwriting existing files.

## 11. Comparing history import options

| Approach | Source history | Commit relationship | Best suited for |
|---|---|---|---|
| `merge --allow-unrelated-histories` | Preserves full history | Joins both graphs with a merge commit | Merging two repositories under a shared root |
| `git subtree add` | Can preserve source history | Connects history and places content under prefix | Importing a project as a subdirectory in a monorepo |
| `git subtree add --squash` | Does not bring each source commit into main graph in full | Records one combined commit for imported snapshot | Only needing source state at import time |
| `git filter-repo --to-subdirectory-filter` | Preserves internal change sequence after rewrite | Commit IDs change; filtered history can be merged | Moving entire history into a prefix or normalizing history |
| `cherry-pick` | Takes only selected changes | Creates new commits on target history | Picking selective bug fixes/features |
| Snapshot copy | Does not preserve source history | Creates only a new commit recording copied files | Only needing current contents |
| Submodule | History stays in separate repository | Superproject stores gitlink to source commit | Keeping component independent and updated separately |

Choose based on how the team will maintain the content after importing. If the component continues to be developed independently, a submodule or subtree may be better than mixing all files into the root. If full traceability in one repository is needed, a merge or non-squashed subtree is usually suitable.

## 12. Migrating history in environments without network connectivity

If the source repository is not directly reachable from the target machine, history can be transferred via a Git bundle. From the source repository:

```bash
git bundle create ../legacy-repository.bundle --all
git bundle verify ../legacy-repository.bundle
```

The bundle contains the objects and refs selected by the bundle creation scope. Transfer the bundle file over an approved internal channel, then in the target repository:

```bash
git fetch ../legacy-repository.bundle main:refs/remotes/legacy/main
```

After fetching, inspect the history:

```bash
git log --oneline --graph --decorate refs/remotes/legacy/main
```

Proceed with merge, subtree, or cherry-pick as covered earlier. A bundle does not decide how histories are joined; it only transfers objects and refs so the target repository can access them.

## 13. What to check after importing

After merging, subtree-adding, or cherry-picking, inspect both the graph and contents:

```bash
git status -sb
git log --oneline --graph --decorate --all
git diff backup/main-before-import...HEAD
git ls-tree -r --name-only HEAD
```

Points to verify:

- Are source commits present in history as intended?
- Does the merge commit have the expected parents?
- Are files at the right paths, especially when importing under a prefix?
- Do `.gitignore`, `.gitattributes`, `.gitmodules`, LFS, and build configurations conflict?
- Are there duplicate filenames or licenses that need reconciliation?
- Do build, tests, lint, and CI workflows pass after the import?
- Do README or docs record the origin, branch, and commit imported?

If importing a source repository with tags, check for duplicate tag names. Tags share a namespace in the target repository; two repositories might have the same tag name pointing to different commits. Never overwrite existing release tags without agreement.

## 14. Common misconceptions

- **Using a normal merge when two histories share no common ancestor.** Git refuses; only use `--allow-unrelated-histories` after confirming both repositories are right.
- **Assuming `--allow-unrelated-histories` rewrites old commits.** This option allows joining the graphs; old commits keep their object IDs.
- **Assuming merge automatically resolves identically named files.** Root files like README or LICENSE can conflict and require manual decisions.
- **Using cherry-pick and thinking the source commit remains an ancestor.** Cherry-pick creates a new commit on the target branch; source ancestry is not preserved.
- **Using `--squash` while expecting individual source commits in main history.** Squash combines changes into one commit rather than linking the full source commit chain.
- **Using filter-repo without notifying stakeholders.** Rewriting history changes hashes and can break clones, tags, signatures, and pipelines.
- **Copying files only and forgetting to record origin.** Later it becomes hard to tell which branch or commit the snapshot came from.
- **Importing a repository while ignoring licenses and configurations.** Technical merging does not automatically resolve licensing rights, dependencies, or security policies.

## 15. Practical workflow: merging two repositories while preserving history

Suppose repository `platform` has branch `main`, and repository `legacy-app` also has branch `main`. Both repositories were created independently, and the team wants to keep both histories in a single repository.

1. Verify the target repository is clean and create a backup branch:

   ```bash
   git status -sb
   git switch main
   git branch backup/main-before-legacy-import
   ```

2. Add the remote and fetch the source repository:

   ```bash
   git remote add legacy https://git.example.com/team/legacy-app.git
   git fetch legacy
   ```

3. Inspect history and confirm there is no merge base:

   ```bash
   git log --oneline --graph --decorate main legacy/main
   git merge-base main legacy/main
   ```

4. Join the two histories:

   ```bash
   git merge --allow-unrelated-histories legacy/main
   ```

5. Resolve conflicted files, stage, and complete the merge.
6. Confirm both previous tips are ancestors of `HEAD`:

   ```bash
   git merge-base --is-ancestor backup/main-before-legacy-import HEAD
   git merge-base --is-ancestor legacy/main HEAD
   ```

7. Run tests, verify licenses, documentation, and pipelines.
8. Push the integrated branch according to your team's review process:

   ```bash
   git push origin main
   ```

Do not push directly to a protected branch if the workflow requires a pull request. After importing, keep the `legacy` remote if ongoing sync is needed; if it was a one-time import, remove the remote config once you have verified the source history is connected.

## 16. Key takeaways

Before importing another repository, determine whether the two histories share a common ancestor and decide whether to keep full history, selected commits, or only a snapshot. `git merge --allow-unrelated-histories` joins two graphs with a merge commit without rewriting old commits. `git subtree` works well when placing content into a subdirectory; `filter-repo` can shift entire histories into a prefix but changes hashes; `cherry-pick` and snapshot copying import only selected changes. Create a backup, verify the source, validate the graph, and run tests before sharing the result.

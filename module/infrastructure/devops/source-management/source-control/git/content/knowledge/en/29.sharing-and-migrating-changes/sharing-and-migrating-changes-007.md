# Merging Two Independent Histories with --allow-unrelated-histories

## When are two histories considered independent?

Normally, Git only merges two branches when they share at least one common ancestor commit. That shared commit serves as the merge base, allowing Git to determine what changed on each branch since the split and combine both sides.

There are cases where two repositories were initialized independently and later need to be brought into a single history:

- A project was created with git init and already has its own commits, then is connected to a new repository on GitHub or GitLab that already has a README or LICENSE commit.
- Two teams developed the same product in two separate repositories and decide to merge their histories.
- An old repository needs to be imported into a new repository while retaining original commits.
- A codebase was initialized independently in two places and needs to be connected into one shared repository.

For example, repository A has history:

~~~text
A1---A2---A3  main
~~~

Repository B has its own history:

~~~text
B1---B2  main
~~~

There is no common commit between the two graphs. When Git searches for a merge base between the two branch tips, it finds no shared ancestor. Therefore, a normal merge command refuses:

~~~bash
git merge imported/main
~~~

Common error message:

~~~text
fatal: refusing to merge unrelated histories
~~~

The `--allow-unrelated-histories` option lets Git proceed with the merge even without a shared merge base:

~~~bash
git merge --allow-unrelated-histories imported/main
~~~

This option does not fabricate a fake common ancestor and does not rewrite the two histories into a single linear chain. Git creates a merge commit with two parents, connecting the two independent history graphs into a single reachable history.

## Understanding a merge commit with no common ancestor

When two branches share history, Git normally uses the common ancestor commit as the merge base to compute changes from both sides. For two independent histories, no such commit exists. When allowing the merge, Git treats the situation as combining two content trees without a shared commit baseline.

Suppose the current branch is main in repository A, and imported/main is a branch fetched from repository B.

Before merging:

~~~text
A1---A2---A3  main

B1---B2       imported/main
~~~

After merging successfully:

~~~text
A1---A2---A3------M  main
                  /
B1---------------B2  imported/main
~~~

The diagram illustrates parent relationships only. Merge commit M has two parents: A3 and B2. Parent order depends on the current branch and the merged branch:

- The first parent is the HEAD commit of the current branch before the merge.
- The second parent is the tip commit of the merged branch.

You can inspect this with:

~~~bash
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

If the merge creates commit M as shown, M has two distinct parent IDs. Commits A1–A3 and B1–B2 keep their original IDs; Git does not alter original commits simply because two histories are connected.

The merge commit creates a junction from which both branches are ancestors of the merged history. Later, Git can compute merge bases for subsequent operations based on the connected graph.

## Distinguishing unrelated histories errors from shallow repositories

Not every case where Git fails to find a merge base means the two repositories are truly independent.

Another cause is a **shallow clone**: a clone that downloaded only part of the history, so the common ancestor commit may not exist in the local object database yet.

Check whether the repository is a shallow clone:

~~~bash
git rev-parse --is-shallow-repository
~~~

If the result is true, fetch more history before concluding the two branches are unrelated. With a supporting remote, you can fetch full history:

~~~bash
git fetch --unshallow origin
~~~

Or deepen by a number of commits:

~~~bash
git fetch --deepen=100 origin
~~~

Substitute the remote and depth according to your actual repository. If the two branches belong to two different remotes, fetch sufficient history from the remote containing the respective branch.

Then check again:

~~~bash
git merge-base main imported/main
~~~

If Git returns a commit ID, the two branches share a common ancestor and can be merged via the normal workflow. If no merge base is found after confirming full history, the two histories may genuinely be independent.

Do not use `--allow-unrelated-histories` merely to paper over an incomplete history fetch. Verify the root cause first.

## Checks before merging

Merging two independent histories can bring many files, configs, and rules from another source into the current repository. Before merging, confirm the right repository, branch, and working tree state.

### Confirming the current repository and branch

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status
git rev-parse HEAD
git log --oneline --decorate -n 10
~~~

Record the current commit of the target branch. If there are uncommitted changes, commit or save them per your workflow before merging. Merging with a dirty working tree may be refused by Git or make comparison difficult.

In particular, do not begin a history import while the index still has unmerged entries from a previous operation.

### Checking remotes and the source branch

List configured remotes:

~~~bash
git remote -v
~~~

List local and remote-tracking branches:

~~~bash
git branch -avv
~~~

If the source repository is not yet registered as a remote, add it with a clear name:

~~~bash
git remote add imported https://example.com/team/legacy-app.git
~~~

The name imported is just an example. If the name already exists, choose another remote name or inspect the existing remote rather than overwriting an unknown configuration.

Fetch refs and objects from the remote:

~~~bash
git fetch imported
~~~

Inspect the newly fetched source branch:

~~~bash
git log --oneline --decorate imported/main
git show --stat --oneline imported/main
~~~

Verify the URL, owning organization, and source commit before bringing history into the target repository. Do not merge an untrusted repository simply because its name or content resembles the project.

### Confirming there is no shared merge base

Run:

~~~bash
git merge-base main imported/main
~~~

If a merge base exists, Git prints the shared commit ID. If not, the command exits with a non-zero code.

You can check more explicitly with:

~~~bash
git merge-base --is-ancestor main imported/main
git merge-base --is-ancestor imported/main main
~~~

These two commands check ancestry in each direction. If both are false, that is still insufficient to conclude unrelated histories if the clone is shallow or missing objects.

Inspect the root commits of both histories:

~~~bash
git rev-list --max-parents=0 main
git rev-list --max-parents=0 imported/main
~~~

If the two branches are truly independent, they usually have different root commits. A single repository can have multiple root commits if history was previously grafted from multiple sources or contains other unrelated refs; therefore, scope the query to the exact two branches being merged.

### Checking overlapping paths

List files on both branch tips:

~~~bash
git ls-tree -r --name-only main
git ls-tree -r --name-only imported/main
~~~

If both histories have README.md, LICENSE, .gitignore, or the same source directory, Git may report conflicts during the merge. That does not mean the merge failed completely; you must decide the final content for each path.

Also check files that affect builds or execution:

- Build files such as pom.xml, build.gradle, package.json, or lockfiles.
- Deployment and CI configuration files.
- Automation workflows in .github/workflows or equivalent directories.
- Installation, build, and release scripts.
- Files containing credentials or environment configuration.
- License, NOTICE, and source documentation.

Two independent repositories may use the same filenames with different contents and purposes. Do not automatically pick all contents from one side without reviewing.

## Creating a recovery point before merging

Before running the merge, save the current commit with a backup branch. Example:

~~~bash
git branch backup/main-before-unrelated-merge main
~~~

The backup branch holds a ref to the pre-merge commit. If something goes wrong afterward, you can still reference the original state.

Create a dedicated integration branch:

~~~bash
git switch -c integrate/legacy-history main
~~~

Working on this branch lets you review the result before bringing it into main. If your team has a naming convention for integration branches, follow that convention.

Re-confirm the state:

~~~bash
git status
git rev-parse HEAD
git branch --show-current
~~~

The starting point of the integration branch must match the main commit recorded earlier.

## Performing the merge with --allow-unrelated-histories

Once you have confirmed the two histories truly share no common ancestor and the local state is ready, run:

~~~bash
git merge --no-commit --no-ff --allow-unrelated-histories imported/main
~~~

Meaning of the options:

- `--allow-unrelated-histories`: permits merging two histories without a common merge base.
- `--no-commit`: pauses before creating the merge commit so you can review the result and resolve remaining issues.
- `--no-ff`: requires creating a merge commit instead of fast-forwarding if a situation permits fast-forward.

With two independent histories, there is no standard fast-forward relationship. `--no-ff` is written explicitly here to express the intent of keeping a merge commit as a history junction.

If you want Git to create the merge commit automatically when there are no conflicts, you can omit `--no-commit`. However, when importing an independent repository, pausing to review often catches duplicate files, unexpected configurations, and unintended changes.

### Checking status after running merge

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

If there are no conflicts, the index already holds the merge result and Git is waiting for you to complete the commit because `--no-commit` was used.

If there are conflicts, git status lists the paths that need resolution. With two independent histories, paths added on both sides are usually the first group to inspect.

## Resolving conflicts when both repositories have identically named files

For example, both repositories have README.md:

- The current repository has build instructions and project A's structure.
- The imported repository has run instructions and project B's structure.

Git cannot automatically decide which content should be kept. Open the conflicted file, inspect both versions, and edit it into unified content aligned with the new repository's goal.

Check conflict status:

~~~bash
git status
git diff -- README.md
git ls-files -u -- README.md
~~~

After editing the content:

~~~bash
git add README.md
~~~

Repeat for each path. Do not run commands choosing --ours or --theirs across the entire repository without understanding the consequences; doing so can discard documentation or configs needed from one side.

Confirm no unmerged paths remain:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

If the unmerged list is empty, inspect staged contents:

~~~bash
git diff --cached --stat
git diff --cached
~~~

`git diff --cached` at this point lets you review the intended snapshot of the merge commit, including files imported from the source history.

### Distinguishing keeping both files from merging content

If two files share a name but serve different purposes, you can rename one file to keep both versions, for example:

~~~text
README.md
docs/legacy-project-README.md
~~~

Then update links and documentation references. For configurations such as build files, do not keep both merely by renaming if the build tool only reads one standard file; you must decide how to combine dependencies, plugins, and tasks.

For LICENSE or NOTICE files, review licensing obligations from both sources before choosing final contents. A technical merge does not replace evaluating source code licensing rights.

## Finalizing the merge commit

Once all conflicts are resolved and the staged diff is reviewed, create the merge commit:

~~~bash
git commit
~~~

Git normally opens an editor with a default merge message. Keep a message that clearly identifies the imported history source, for example:

~~~text
Merge legacy-app history into inventory-app
~~~

Inspect the newly created commit:

~~~bash
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

The merge commit must have two parents: the current branch commit before the merge and the imported/main branch commit.

View the history graph:

~~~bash
git log --oneline --graph --decorate --all
~~~

Confirm both history tips are ancestors of the merge commit:

~~~bash
git merge-base --is-ancestor main HEAD
git merge-base --is-ancestor imported/main HEAD
~~~

If both commands return exit code 0, both branch tips are in the ancestor history of HEAD. This verifies that the merge commit connected both histories.

## If the merge fails or needs to be canceled

If a merge is in progress and you want to return to the state before starting, you can use:

~~~bash
git merge --abort
~~~

This command cancels the ongoing merge. It does not replace protecting local changes that existed before the merge; that is why you should start from a clean working tree and have a backup ref.

After aborting, check:

~~~bash
git status
git rev-parse HEAD
git log -1 --oneline --decorate
~~~

HEAD should return to the pre-merge commit and no merge state should remain in progress.

If the merge has already completed and the merge commit has been created, `git merge --abort` is no longer applicable. When the commit has been created locally and not yet shared, you can switch back to the backup branch or create a new branch from the backup commit after assessing state. If the merge commit has already been pushed to a remote or others have built on top of it, coordinate with your team and prefer an intentional revert commit rather than rewriting shared history.

Do not run `git reset --hard` reflexively to fix a bad merge. Determine whether the merge has been committed, which commits must be kept, and which local changes could be lost.

## Verifying results after merging

A merge succeeding at the Git level only proves two snapshots were combined into a commit. You still need to verify the contents and buildability of the new repository.

### Checking history

~~~bash
git log --graph --oneline --decorate --all
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

Verify:

- The merge commit has the expected two parents.
- Source commits still appear in history.
- The backup branch still points to the pre-merge commit.
- The integration branch sits at the new commit.
- No refs were moved unintentionally.

### Checking contents and configurations

~~~bash
git status
git diff HEAD^1 HEAD --stat
git diff HEAD^2 HEAD --stat
~~~

These two diff commands compare the merge commit snapshot against each parent, showing what differs between the merged result and each side.

Review conflict-prone areas:

- README and guide documentation.
- Build configuration and dependency files.
- CI workflows and automation scripts.
- .gitignore and .gitattributes.
- License and NOTICE.
- Submodules/gitlinks if present.
- Deployment and environment configuration files.

If both repositories have submodules, after merging check .gitmodules and gitlinks, then initialize per project instructions:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
git submodule status --recursive
~~~

Do not assume submodules from both sides are automatically configured properly just because the superproject merge had no conflicts.

### Running project checks

Run the appropriate commands for the repository after importing:

- Build modules or the entire project.
- Unit tests and integration tests.
- Lint and format checks.
- Dependency and lockfile checks.
- CI script checks.
- Deployment configuration checks.
- Core flows from both sources.

Do not assume a single build command works for two newly merged projects. You may need to unify directory layout, build tools, or startup scripts before running comprehensive tests.

## Sharing merge results to the remote

Once the merge commit has been reviewed and tested, push the integration branch to the remote:

~~~bash
git push -u origin integrate/legacy-history
~~~

If main is protected, create a Pull Request or Merge Request from the integration branch into main. The server still enforces access permissions, reviews, and status checks like any other change.

Do not push directly to a protected branch simply because the merge commit was created locally. Creating a local commit does not grant permission to update the remote.

After approval and merging into main, verify the remote state:

~~~bash
git fetch origin
git log --graph --oneline --decorate origin/main -n 30
~~~

Keep the imported remote if the team still needs to reference or update from the old source. If no longer needed, you can remove the local remote config after recording origin information in an appropriate place:

~~~bash
git remote remove imported
~~~

This command deletes the remote configuration along with remote-tracking refs belonging to that remote in the current clone; it does not delete the source repository. Merged commits remain kept because they are still reachable from the merge commit. If there are unintegrated source branches or tags only referenced by the imported remote's refs, save or transfer the required refs before removing the remote.

## What is not automatically imported when merging histories

`--allow-unrelated-histories` combines two commit histories and their snapshots. It does not automatically migrate all data or settings from the hosting platform.

Items that normally require separate handling:

- Issues, Pull Requests/Merge Requests, and review discussions.
- Member permissions, teams, tokens, and deploy keys.
- Branch protections, rulesets, and CI secrets.
- Webhooks, runners, and deployment configurations.
- Wikis or documentation stored outside the repository.
- Release metadata and artifacts.
- Tags or branches not in the history of the two merged branch tips.

If tags need to be migrated, list and review them separately before pushing:

~~~bash
git tag --list
git show-ref --tags
~~~

Do not push all tags from another source without checking for name collisions, target commits, and version meaning. Two independent repositories may have used the same tag name for two different commits.

Similarly, transfer branches separately according to plan. Merging two branch tips does not automatically create all remote branches of the source repository inside the target repository.

## When to use another approach instead of --allow-unrelated-histories?

Not every repository import requirement calls for joining two independent histories with a merge commit.

| Goal | Commonly suitable approach |
|---|---|
| Connect two histories and preserve both commit graphs | `git merge --allow-unrelated-histories` |
| Take only selected commits from source repository | `git cherry-pick` |
| Import a project directory and preserve path history | History filtering tool such as git filter-repo, then merge |
| Place a project in a subdirectory while continuing separate sync | Git subtree or submodule, depending on model |
| Take only current snapshot without source history | Controlled content copy then commit in target repository |
| Migrate repository with branches and intact history | Clone/mirror or platform migration workflow |

If you only need to import one directory from an old repository into a monorepo, merging both roots directly can clutter the directory tree and make history hard to read. In that case, filtering history to place all paths under a subdirectory before merging may be more suitable.

If you want two projects to continue developing independently, a submodule or subtree may express the relationship more clearly than merging the entire history into one branch.

## Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| refusing to merge unrelated histories | No common merge base found | Verify full history, then use `--allow-unrelated-histories` if truly needed |
| Merge base not found in shallow clone | Clone lacks ancestor commits | Use fetch --unshallow or --deepen then check again |
| Many conflicts in README and config files | Both root commits added the same paths | Review and merge each file, do not pick one side in bulk |
| Submodule fails to check out after merge | .gitmodules, URL, or gitlink inconsistent | Inspect, sync, and update submodules |
| Merge commit has only one parent | Not the expected two-history merge commit or another method was used | Check `git rev-list --parents -n 1 HEAD` |
| Push of integration branch rejected | Missing permissions, protected branch, or remote has new history | Check policy and open a Pull Request/Merge Request |
| Same-named tag points to different commit | Both repositories have independent tag namespaces | Review and decide how to rename or keep tags |
| Build fails after merge | Configs or dependencies of both projects conflict | Align build, lockfiles, and configs, then re-run tests |

## Sample end-to-end workflow

Suppose the current repository is inventory-app and needs to import history from legacy-app.

~~~bash
# 1. Confirm current repository state
git status
git rev-parse HEAD
git branch --show-current

# 2. Save recovery point
git branch backup/main-before-import main

# 3. Add and fetch source repository
git remote add imported https://example.com/team/legacy-app.git
git fetch imported

# 4. Inspect history and confirm no merge base
git merge-base main imported/main
git rev-list --max-parents=0 main
git rev-list --max-parents=0 imported/main

# 5. Create dedicated integration branch
git switch -c integrate/legacy-history main

# 6. Merge both histories, pausing for review
git merge --no-commit --no-ff --allow-unrelated-histories imported/main

# 7. Inspect conflicts and staged results
git status
git diff --name-only --diff-filter=U
git diff --cached --stat

# 8. Fix each conflict, then stage results
git add <resolved-path>

# 9. Confirm no conflicts remain and review
git diff --name-only --diff-filter=U
git diff --cached

# 10. Create merge commit
git commit

# 11. Confirm merge has two parents and preserves both histories
git rev-list --parents -n 1 HEAD
git log --graph --oneline --decorate --all

# 12. Verify build/tests then push integration branch
git push -u origin integrate/legacy-history
~~~

Placeholders like URLs, branch names, and paths must be substituted for your actual repository. If `git merge-base` finds a common ancestor, use the normal merge workflow instead of enabling the unrelated histories option.

## Checklist before and after using --allow-unrelated-histories

- [ ] Confirmed the right target and source repositories.
- [ ] Working tree and index are clean before starting.
- [ ] Recorded current commit and created a backup ref.
- [ ] Fetched full history from the source remote.
- [ ] Checked shallow clone status and ruled out missing history.
- [ ] Confirmed the two branches truly share no common merge base.
- [ ] Inspected root commits and overlapping paths.
- [ ] Reviewed build files, configs, workflows, scripts, and licenses.
- [ ] Merged on a dedicated integration branch.
- [ ] Resolved each conflict and inspected staged diff.
- [ ] Merge commit has the expected two parents.
- [ ] Both source histories are ancestors of the merge commit.
- [ ] Checked submodules, tags, and refs needing separate migration.
- [ ] Ran appropriate builds/tests.
- [ ] Pushed through the team's review and branch protection workflow.

## Key takeaways

`--allow-unrelated-histories` lets Git connect two histories without a common ancestor commit using a merge commit with two parents. Before using it, make sure you are dealing with two genuinely independent repositories, not a shallow clone missing history. Create a backup ref, fetch and inspect the source, merge on a dedicated branch, review overlapping files, and resolve conflicts step by step. Once complete, verify the two parents, preserve source commits, run builds/tests, and share through your team's review process. This option preserves both commit graphs; it does not automatically migrate issues, access permissions, CI secrets, tags, or platform settings.

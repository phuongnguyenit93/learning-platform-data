# Working With Two Clones to Observe Fetch, Pull, and Diverged Branches

## Practice Objectives

In this lab, you will simulate two team members collaborating on one repository using two independent clones. A bare repository acts as the central remote for both clones to exchange commits.

This lab lets you directly observe:

- Why two clones do not automatically know about each other's changes.
- `git fetch` downloads commits and updates remote-tracking branches without integrating them into the current branch.
- `git pull` performs a fetch and then integrates history via fast-forward, merge, or rebase depending on options/configuration.
- Why a local branch can be both ahead and behind after two people commit concurrently.
- When `git pull --ff-only` succeeds or aborts.
- How to integrate diverged branches using merge and rebase.
- How to resolve a conflict when two clones edit the same line.
- How to inspect the commit graph to verify that history was integrated properly.

All operations take place inside a fresh lab directory. Do not use a real work repository to test creating conflicts, merges, or rebases.

## Lab Model

We create a bare remote named `central.git`, then create two clones named `clone-a` and `clone-b`.

~~~text
                    central.git
                   (bare remote)
                    /        \
                   /          \
                  v            v
             clone-a          clone-b
           Developer A      Developer B
~~~

`central.git` stores only Git objects and refs, with no working tree for direct file edits. The two developers work in separate clone directories. When one pushes, the remote is updated; the other clone only learns about the changes after running fetch or pull.

A `seed` repository is used once to create the initial commit for the remote. Once the two clones are created, all collaboration scenarios happen between `clone-a`, `clone-b`, and `central.git`.

## Environment Setup

You need Git installed and runnable from the terminal:

~~~bash
git --version
~~~

The initialization examples use `--initial-branch=main`, available since Git 2.28. If your Git version is older, update Git or create the `main` branch accordingly before pushing the first commit.

The examples below use PowerShell to create files, suited for Windows. The Git commands work in PowerShell, Git Bash, macOS, or Linux; if using another shell, adjust the file/directory creation commands for that shell.

Create a dedicated directory for the lab and enter it:

~~~powershell
New-Item -ItemType Directory -Force git-two-clones-lab | Out-Null
Set-Location git-two-clones-lab
~~~

All paths in this lab are relative to `git-two-clones-lab`.

## Step 1: Create the Bare Remote and Initial Commit

Create the bare remote:

~~~bash
git init --bare --initial-branch=main central.git
~~~

Create the `seed` repository with branch `main`:

~~~bash
git init --initial-branch=main seed
~~~

Configure a local identity for the seed repository:

~~~bash
git -C seed config user.name "Lab Seed"
git -C seed config user.email "seed@example.test"
~~~

Create the initial file and commit:

~~~powershell
Set-Content -NoNewline seed/README.md "Project status: initialized"
~~~

~~~bash
git -C seed add README.md
git -C seed commit -m "chore: initialize demo project"
~~~

Connect `seed` to the bare remote and push the `main` branch:

~~~bash
git -C seed remote add origin ../central.git
git -C seed push -u origin main
~~~

Verify the remote has the `main` branch:

~~~bash
git --git-dir=central.git branch --list
git --git-dir=central.git symbolic-ref HEAD
~~~

Expected result: the `main` branch exists and the bare repository's HEAD points to `refs/heads/main`.

If your Git does not support `git init --bare --initial-branch=main`, you can create the bare repository and set its HEAD:

~~~bash
git init --bare central.git
git --git-dir=central.git symbolic-ref HEAD refs/heads/main
~~~

With the same older Git version, create `seed` and switch to an orphan `main` branch before the first commit:

~~~bash
git init seed
git -C seed checkout --orphan main
~~~

Then configure the identity, create the README, make the initial commit, and push as in the steps above.

## Step 2: Create Two Clones

From the lab directory, clone the remote twice:

~~~bash
git clone central.git clone-a
git clone central.git clone-b
~~~

The two directories `clone-a` and `clone-b` are two independent working copies. Each clone has its own object database, local branches, index, and working tree. Both share a configured `origin` remote pointing to `central.git`.

Configure an identity for each clone:

~~~bash
git -C clone-a config user.name "Developer A"
git -C clone-a config user.email "developer-a@example.test"

git -C clone-b config user.name "Developer B"
git -C clone-b config user.email "developer-b@example.test"
~~~

Verify both clones:

~~~bash
git -C clone-a status -sb
git -C clone-b status -sb

git -C clone-a remote -v
git -C clone-b remote -v

git -C clone-a branch -vv
git -C clone-b branch -vv
~~~

Both clones should be on branch `main`, have clean working trees, and have their local branch tracking `origin/main`.

Inspect the initial commit:

~~~bash
git -C clone-a log -1 --oneline --decorate
git -C clone-b log -1 --oneline --decorate
~~~

Both clones must share the same initial commit. Note that commit hash for easy reference when needed.

## Step 3: Observe That Fetch Does Not Auto-Integrate Into the Current Branch

First, Developer A creates a new file, commits, and pushes:

~~~powershell
Set-Content -NoNewline clone-a/a-note.txt "Created by Developer A"
~~~

~~~bash
git -C clone-a add a-note.txt
git -C clone-a commit -m "docs: add note from developer A"
git -C clone-a push origin main
~~~

At this point `central.git` has the new commit. However, `clone-b` has not fetched yet, so the remote-tracking ref `origin/main` in clone B still holds the old commit hash.

Check clone B's status before fetching:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-parse main
git -C clone-b rev-parse origin/main
~~~

Because clone B does not yet know the remote changed, `git status` may still report the branch is up to date with `origin/main`. This compares against the locally stored remote-tracking ref, not by querying the server live on every run.

Run fetch:

~~~bash
git -C clone-b fetch origin
~~~

Fetch downloads missing objects and updates the remote-tracking ref `origin/main`. It does not move the local `main` branch or update files in the working tree.

Re-check:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-parse main
git -C clone-b rev-parse origin/main
git -C clone-b log --oneline --decorate main..origin/main
~~~

Expected result:

- `main` still points to the old commit.
- `origin/main` points to the new commit from Developer A.
- `git status -sb` reports the local branch is behind by 1 commit.
- `git log main..origin/main` lists commits present on the remote that are missing from the local branch.

You can inspect the changes before integrating them:

~~~bash
git -C clone-b diff --stat main..origin/main
git -C clone-b diff main..origin/main
~~~

Verify that `a-note.txt` has not appeared in clone B's working tree yet. Fetch only updates objects and remote-tracking refs; files only update when you integrate the commits into the branch/working tree.

### Inspecting the Graph After Fetch

~~~bash
git -C clone-b log --graph --oneline --decorate --all
~~~

Before pulling, the graph can be visualized like this:

~~~text
S---A  origin/main
|
main
~~~

Here S is the initial commit and A is the commit Developer A just pushed. Clone B's `main` is still at S, while `origin/main` has moved to A.

This is the core distinction: fetch refreshes information about the remote while leaving the current branch untouched.

## Step 4: Using Pull to Update When the Branch Is Only Behind

In clone B, the local branch has no unique commits of its own and only needs to receive commit A. This is a fast-forward case.

Run:

~~~bash
git -C clone-b pull --ff-only origin main
~~~

`git pull` performs a fetch and then integrates the result into the current branch. The `--ff-only` option requires a fast-forward update; if the branch has diverged, Git aborts instead of creating a merge commit or rebasing.

Verify:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
git -C clone-b show --stat --oneline HEAD
~~~

Expected result:

- Clone B's `main` branch advances to commit A.
- `a-note.txt` appears in the working tree.
- `main` and `origin/main` point to the same commit.
- The working tree is clean.

The graph is now:

~~~text
S---A  main, origin/main
~~~

A fast-forward simply moves the local branch to the new commit because the old commit is an ancestor of the new one. No merge commit is needed.

### Summary of Fetch and Pull Observations

| Operation | Remote-tracking ref | Local branch | Working tree |
|---|---|---|---|
| Before fetch | May be stale | Unchanged | Unchanged |
| After `git fetch` | Updated | Unchanged | Unchanged |
| After `git pull --ff-only` when behind only | Updated | Fast-forwarded | Updated to new commit |

## Step 5: Creating Diverged Branches From Two Clones

Now both clones are synchronized at commit A. We will have both team members make commits starting from that shared point.

Developer A creates a file and pushes:

~~~powershell
Set-Content -NoNewline clone-a/from-a.txt "Work committed by Developer A"
~~~

~~~bash
git -C clone-a add from-a.txt
git -C clone-a commit -m "docs: add work from developer A"
git -C clone-a push origin main
~~~

Developer B creates a different file and commits locally without pushing:

~~~powershell
Set-Content -NoNewline clone-b/from-b.txt "Work committed by Developer B"
~~~

~~~bash
git -C clone-b add from-b.txt
git -C clone-b commit -m "docs: add work from developer B"
~~~

At this point the two clones have different histories:

- `clone-a` has A's commit pushed to the remote.
- `clone-b` has B's commit unpushed locally.
- `origin/main` in clone B has not fetched yet, so it still points to the earlier commit A.

Check clone B before fetching:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
~~~

Because the remote-tracking ref has not been updated, status may only report local ahead by 1. Clone B cannot yet see A's new commit via `origin/main`.

Fetch from the remote:

~~~bash
git -C clone-b fetch origin
~~~

Re-check:

~~~bash
git -C clone-b status -sb
git -C clone-b log --left-right --graph --oneline main...origin/main
git -C clone-b log --graph --oneline --decorate --all
~~~

Now `git status -sb` should display `ahead 1, behind 1` relative to upstream.

Meaning:

- **Ahead 1:** the local `main` branch has one commit that `origin/main` does not have: B's commit.
- **Behind 1:** `origin/main` has one commit that the local `main` branch does not have: A's commit.

Diverged graph:

~~~text
       A  origin/main
      /
S----+
      \
       B  main
~~~

S is the shared commit. Both A and B were created from S, and neither commit is an ancestor of the other.

### Reading Commits Unique to Each Side

Command:

~~~bash
git -C clone-b log --left-right --graph --oneline main...origin/main
~~~

Symbols:

- `<` indicates commits reachable only from the left argument (`main`).
- `>` indicates commits reachable only from the right argument (`origin/main`).

You will see B's commit on the local side and A's commit on the remote side. This is a quick way to identify what each side contributes before integrating.

You can check the merge base:

~~~bash
git -C clone-b merge-base main origin/main
~~~

The result should be commit S, the common ancestor before the two clones diverged.

## Step 6: Observing pull --ff-only Rejecting Diverged Branches

When the local branch has its own commit and the remote also has its own commit, a fast-forward cannot move the local branch to the remote without dropping commit B.

Try:

~~~bash
git -C clone-b pull --ff-only origin main
~~~

Git will abort with a message similar to:

~~~text
fatal: Not possible to fast-forward, aborting.
~~~

This is intentional behavior. `--ff-only` does not auto-create a merge commit and does not rewrite local commits. It helps you recognize that the branch has diverged so you can choose how to integrate.

Re-check:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
~~~

Both commits A and B remain intact. The remote-tracking ref `origin/main` has been fetched and the local branch still points to commit B.

In this situation, the two common integration approaches are merge or rebase. The choice depends on your team's history conventions.

## Step 7: Integrating Diverged Branches With Merge

In this lab, we choose merge to preserve both lines of development and create a merge commit.

Run in clone B:

~~~bash
git -C clone-b pull --no-rebase --no-ff origin main
~~~

Meaning:

- `--no-rebase`: instructs Git to integrate via merge.
- `--no-ff`: creates a merge commit during integration, preserving the junction of both branches.
- `origin main`: uses the `main` branch from remote `origin` as the integration source.

Because the two developers added different files, this example produces no conflict. Git automatically combines both snapshots and creates a merge commit.

Verify:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-list --parents -n 1 HEAD
git -C clone-b log --graph --oneline --decorate --all
~~~

The merge commit has two parents:

1. Commit B on the local branch before the merge.
2. Commit A on `origin/main` being merged in.

The post-merge graph looks like:

~~~text
       A --------\
      /           \
S---+              M  main
      \           /
       B --------/
origin/main -> A
~~~

After the merge, `main` points to M; `origin/main` still points to A until B pushes the merge commit.

Push the result to the remote:

~~~bash
git -C clone-b push origin main
~~~

Now remote `main` points to merge commit M. Clone A does not automatically know this. Fetch and fast-forward clone A:

~~~bash
git -C clone-a fetch origin
git -C clone-a status -sb
git -C clone-a pull --ff-only origin main
~~~

Inspect both clones:

~~~bash
git -C clone-a status -sb
git -C clone-b status -sb
git -C clone-a log --graph --oneline --decorate --all
~~~

Both clones should be synchronized at merge commit M.

### If You Prefer Direct Merge Over Pull

`git pull --no-rebase` is essentially fetch followed by merge. You can also split those two steps to observe each clearly:

~~~bash
git -C clone-b fetch origin
git -C clone-b merge --no-ff origin/main
~~~

Splitting them is useful when you want to review the graph after fetching before integrating. Do not run both sequences back-to-back on the same state, as that may create a duplicate merge or leave nothing to merge.

## Step 8: Creating a Conflict When Both Clones Edit the Same Line

At this point both clones are synchronized. We will create an intentional conflict by having both clones edit the same line in `README.md`.

Developer A edits and pushes:

~~~powershell
Set-Content -NoNewline clone-a/README.md "Project status: updated by A"
~~~

~~~bash
git -C clone-a add README.md
git -C clone-a commit -m "docs: update project status from A"
git -C clone-a push origin main
~~~

Developer B has not fetched A's commit yet. In clone B, edit the same line with different content and commit locally:

~~~powershell
Set-Content -NoNewline clone-b/README.md "Project status: updated by B"
~~~

~~~bash
git -C clone-b add README.md
git -C clone-b commit -m "docs: update project status from B"
~~~

Fetch and try integrating via merge:

~~~bash
git -C clone-b fetch origin
git -C clone-b pull --no-rebase --no-ff origin main
~~~

The separate fetch lets you inspect the remote-tracking ref before integrating. The pull command still runs fetch once more; if the remote did not change in the meantime, no extra commits are downloaded.

Git cannot decide automatically whether to keep A's content or B's content because both changed the same line from the same base version. Pull stops in a conflicted state.

Inspect:

~~~bash
git -C clone-b status
git -C clone-b diff --name-only --diff-filter=U
git -C clone-b diff --cc README.md
~~~

`README.md` in clone B will contain conflict markers similar to:

~~~text
<<<<<<< HEAD
Project status: updated by B
=======
Project status: updated by A
>>>>>>> origin/main
~~~

Meaning:

- `HEAD` is the version on B's current local branch.
- The section after the separator is the version from the remote branch being merged in.
- The markers exist in the working file only while the conflict is unresolved; they must not remain in the final file content.

### Resolving the Conflict

Open `clone-b/README.md` and decide the final content. In this example, we keep information from both developers:

~~~powershell
Set-Content -NoNewline clone-b/README.md "Project status: updated by A and B"
~~~

Stage the resolved file:

~~~bash
git -C clone-b add README.md
~~~

Confirm there are no remaining unmerged paths:

~~~bash
git -C clone-b diff --name-only --diff-filter=U
git -C clone-b status
git -C clone-b diff --cached
~~~

If the unmerged list is empty and the staged content is right, finalize the merge commit:

~~~bash
git -C clone-b commit
~~~

Push the merge commit:

~~~bash
git -C clone-b push origin main
~~~

Update clone A:

~~~bash
git -C clone-a pull --ff-only origin main
~~~

Inspect the README file and history in both clones. The merge commit retains both parents and the final file contains the content you chose.

### Aborting a Merge if You Are Not Ready to Resolve

If you want to cancel an in-progress merge:

~~~bash
git -C clone-b merge --abort
~~~

This command returns the repository to its pre-merge state, within the limits Git can restore that state. Always start from a clean working tree and save any changes you want to keep before attempting a merge.

After aborting, check:

~~~bash
git -C clone-b status
git -C clone-b log -1 --oneline --decorate
~~~

Do not reflexively use `git reset --hard` to deal with conflicts; that command can discard unsaved local changes.

## Step 9: Integrating Diverged Branches With Rebase

Merge preserves both branches and creates a merge commit. Rebase takes another approach: replaying local commits on top of the new commits from the remote, producing a linear history.

We create another divergence after both clones are synchronized from the previous step.

Developer A creates a new commit on `main` and pushes:

~~~powershell
Set-Content -NoNewline clone-a/from-a-rebase.txt "Remote work before rebase"
~~~

~~~bash
git -C clone-a add from-a-rebase.txt
git -C clone-a commit -m "docs: add remote work before rebase"
git -C clone-a push origin main
~~~

Developer B creates a local commit on `main` without pushing:

~~~powershell
Set-Content -NoNewline clone-b/from-b-rebase.txt "Local work to replay"
~~~

~~~bash
git -C clone-b add from-b-rebase.txt
git -C clone-b commit -m "docs: add local work for rebase"
~~~

Integrate with pull rebase:

~~~bash
git -C clone-b pull --rebase origin main
~~~

The command fetches and then replays B's local commit on top of the latest commit from the remote. As a result, commit A sits before the newly recreated commit B.

Graph before rebase:

In both diagrams below, S represents the current shared commit after the merge/conflict in the previous step; A and B are the two new commits created from that point.

~~~text
       A  origin/main
      /
S----+
      \
       B  main
~~~

Graph after rebase:

~~~text
S---A---B'  main
    ^
    origin/main
~~~

`B'` is the new commit created when replaying B's changes. The content change may match the original commit, but its parent and committer metadata can differ, so the commit ID typically changes.

Verify:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
git -C clone-b show --no-patch --pretty=raw HEAD
~~~

Push the rebased branch:

~~~bash
git -C clone-b push origin main
~~~

Because the original commit B was never pushed and the remote branch only has commit A, pushing the rebased result is a fast-forward from the remote to `B'`. No force push is needed.

Update clone A:

~~~bash
git -C clone-a pull --ff-only origin main
~~~

### If Rebase Encounters a Conflict

When a commit being replayed does not apply cleanly onto the new base, Git pauses for conflict resolution.

Check status:

~~~bash
git -C clone-b status
~~~

Fix the file, stage the result, and continue:

~~~bash
git -C clone-b add README.md
git -C clone-b rebase --continue
~~~

Repeat if subsequent commits also conflict. To cancel the entire in-progress rebase:

~~~bash
git -C clone-b rebase --abort
~~~

Do not use `git commit` to finish a rebase paused on a conflict; use `git rebase --continue`. `git commit` is the step used to complete a merge conflict, whereas rebase has its own continuation workflow.

### Choosing Merge or Rebase?

| Criterion | Merge | Rebase |
|---|---|---|
| History | Keeps diverged branches and creates a merge commit | Replays commits onto the new base, usually linear |
| Local commits | Preserves original commits | Creates new commits for the replayed work |
| Collaboration visibility | Clearly shows integration points | Cleaner history with fewer merge commits |
| Conflicts | Resolved during the merge | May occur at each replayed commit |
| Best suited for | Shared branches or teams wanting merge history | Unshared personal branches, or teams requiring linear history |

Do not rebase commits already used by others without coordinating. Rebase rewrites commits and can force teammates to reconcile altered history.

## Understanding Ahead and Behind States

`git status -sb` compares the local branch against the upstream/remote-tracking branch it is configured to track.

| Status | Meaning |
|---|---|
| up to date | Local and upstream point to the same commit according to current local knowledge |
| ahead 1 | Local has one commit that upstream does not have |
| behind 1 | Upstream has one commit that local does not have |
| ahead 2, behind 3 | Both sides have separate histories; local has 2 unique commits and upstream has 3 unique commits |
| no upstream | Git has no tracking branch configured to compute ahead/behind |

Key reminder: ahead/behind status is only as accurate as the latest local remote-tracking ref. If you have not fetched, `origin/main` may be stale and Git will not know the remote received new commits.

Inspect upstream configuration:

~~~bash
git branch -vv
git status -sb
~~~

Inspect commits unique to local and remote after fetching:

~~~bash
git log --left-right --oneline main...origin/main
~~~

## Distinguishing Fetch, Pull, Merge, and Rebase

| Command | Primary effect | Auto-updates working tree? |
|---|---|---|
| `git fetch origin` | Downloads objects and updates remote-tracking refs | No |
| `git pull --ff-only` | Fetches, then integrates only if fast-forward is possible | Yes, if branch advances |
| `git pull --no-rebase` | Fetches, then merges | Yes; may pause on conflict |
| `git pull --rebase` | Fetches, then rebases local commits | Yes; may pause on conflict |
| `git merge origin/main` | Integrates the remote-tracking branch into the current branch | Yes; may pause on conflict |
| `git rebase origin/main` | Replays local commits onto the remote base | Yes; may pause on conflict |

A GUI may label operations Sync, Update, Pull, Rebase, or Integrate. Before clicking, verify whether the tool is performing fetch, merge, or rebase.

## Configuring Pull Strategy

If running `git pull` prompts you to specify how to reconcile diverged branches, you can specify the strategy explicitly on the command:

~~~bash
git pull --ff-only
git pull --no-rebase
git pull --rebase
~~~

Or configure a default matching your personal/repository convention:

~~~bash
# Default pull to merge
git config --local pull.rebase false

# Or default pull to rebase
git config --local pull.rebase true

# Only allow fast-forward
git config --local pull.ff only
~~~

These are mutually exclusive alternatives depending on the desired policy; you do not need to set all three mechanically. Check the active setting and its config source:

~~~bash
git config --show-origin --show-scope --get pull.rebase
git config --show-origin --show-scope --get pull.ff
~~~

In a lab, prefer explicit flags on each command so outcomes are predictable and do not depend on machine-wide global config.

## Troubleshooting Common Situations

| Symptom | Possible cause | How to check and resolve |
|---|---|---|
| Clone B does not see commit A just pushed | Haven't fetched yet; remote-tracking ref is stale | Run `git fetch origin` then inspect `git log --all` |
| `git status` still says up to date despite new remote commits | Local upstream tracking ref hasn't been updated | Fetch before reading ahead/behind |
| `pull --ff-only` aborts | Local and remote branches have diverged | Inspect the graph, then choose merge or rebase |
| Push rejected as non-fast-forward | Remote has commits not yet integrated locally | Fetch, integrate history, then push |
| Pull stops on conflict | Both sides edited the same region or made incompatible changes | Edit files, stage, then commit or `rebase --continue` depending on operation |
| No ahead/behind shown | Branch has no upstream configured | Check `git branch -vv`, set upstream if needed |
| Pull asks you to choose a strategy | No strategy configured or branches diverged | Pass `--ff-only`, `--no-rebase`, or `--rebase` explicitly |
| Authentication failed | Invalid credentials or remote access permissions | Check remote URL, SSH keys, or credential manager |
| Local files would be overwritten by pull | Working tree has edits conflicting with files to check out | Commit/stash changes you want to keep, then retry |

### Quick Check When Unsure of State

Run these commands before deciding to pull, merge, or rebase:

~~~bash
git status -sb
git branch -vv
git remote -v
git fetch origin
git status -sb
git log --graph --oneline --decorate --all
git log --left-right --oneline main...origin/main
~~~

## Self-Check Exercises

### Exercise 1: Does Fetch Advance the Local Branch?

1. Create a commit in clone A and push.
2. Run `git status -sb` in clone B before fetching.
3. Run `git fetch origin`.
4. Compare `git rev-parse main` and `git rev-parse origin/main`.

Result to explain: fetch updates the remote-tracking ref, while the local branch keeps pointing to the old commit.

### Exercise 2: When Does Fast-Forward Pull Succeed?

1. Leave clone B with no unique local commits.
2. Push a new commit from clone A.
3. Run `git pull --ff-only origin main` in clone B.

Result to explain: the local branch can advance directly to the remote commit because the old commit is an ancestor of the new one.

### Exercise 3: Why Is a Branch Both Ahead and Behind?

1. Synchronize both clones.
2. Create and commit a change in clone A, then push.
3. Create and commit a different change in clone B without pushing.
4. Fetch in clone B.
5. Read `git status -sb` and `git log --left-right`.

Result to explain: each side has its own commit created from the same common ancestor.

### Exercise 4: Comparing Merge and Rebase

From a backed-up diverged state:

1. Integrate via merge and check the parent count of the new commit.
2. Recreate the diverged state in another lab directory.
3. Integrate via rebase and inspect the graph.
4. Compare commit IDs before and after rebase.

Result to explain: merge creates a junction commit with multiple parents; rebase replays commits and typically produces new IDs.

### Exercise 5: Resolving a Conflict

1. Have both clones edit the same line in README.
2. Commit on both sides; push one side.
3. Pull on the other side to trigger a conflict.
4. Combine content from both sides, stage, and finalize the merge.
5. Push the result and update the other clone.

Result to explain: Git requires the user to decide the final content when it cannot automatically combine changes.

## Lab Completion Checklist

- [ ] Created bare remote `central.git`.
- [ ] Created two clones `clone-a` and `clone-b`.
- [ ] Verified both clones started from the same commit.
- [ ] Observed remote-tracking ref status before and after fetch.
- [ ] Verified fetch does not auto-update the local branch or working tree.
- [ ] Used fast-forward pull to update a behind clone.
- [ ] Created independent commits in both clones.
- [ ] Observed ahead/behind status after fetch.
- [ ] Observed `pull --ff-only` aborting when branches diverged.
- [ ] Integrated once using merge and inspected its two parents.
- [ ] Resolved a conflict when both clones edited the same line.
- [ ] Integrated once using rebase and observed recreated commits.
- [ ] Pushed results and updated the other clone.
- [ ] Inspected the graph and verified both clones are synchronized.

## Key Takeaways

Two clones maintain independent working trees, branches, and remote-tracking refs. When one clone pushes, the other clone does not change automatically. `git fetch` updates objects and remote-tracking info while leaving the current branch untouched; `git pull` fetches and then integrates via fast-forward, merge, or rebase. When both clones commit from a common ancestor, the branch diverges and reports ahead/behind after fetching. `--ff-only` rejects that state so you can intentionally choose merge or rebase. Inspect `git status -sb`, `git log --graph`, and `git log --left-right` before integrating, resolve conflicts according to the active operation, and then push and update the remaining clone.

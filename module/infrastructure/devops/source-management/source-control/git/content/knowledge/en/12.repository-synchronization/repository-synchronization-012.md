# Handling Diverged Branches and Concurrent Updates from Multiple Collaborators

In a repository with multiple developers collaborating, a branch on the server can change while you are working. Teammates may have pushed new commits while you also created your own commits based on an older version. When that happens, the local branch and remote branch no longer lie on the same line of history: each side has commits the other does not. Git calls this situation **diverged branches**.

Divergence is a normal part of collaboration. What matters is recognizing it, pulling the latest information from the remote, inspecting the commits on both sides, and choosing the appropriate integration method. If multiple people push to a branch at nearly the same time, Git protects history by rejecting non-fast-forward updates; the later pusher must synchronize and integrate the new commits before trying again.

After this lesson, you will be able to:

- Recognize the ahead, behind, and diverged states of a branch.
- Identify commits present only locally or only on the remote.
- Explain why a push can be rejected due to non-fast-forward.
- Synchronize diverged branches using merge, rebase, or fast-forward-only.
- Handle scenarios where multiple people update the same branch.
- Complete integration, verify the result, and push safely.

## 1. Why Branches Diverge

Suppose you and a teammate both start from commit C on the main branch. You create commit A1, while your teammate creates commit B1 and pushes to origin/main. Afterward, you create A2 without fetching your teammate's changes.

History now looks like this:

~~~text
             A1---A2  main (local)
            /
           C
            \
             B1      origin/main
~~~

Both branches share ancestor C but have grown in two directions. Local has A1 and A2; remote has B1. It is not possible to simply move the main pointer to B1 while keeping A1 and A2, because doing so would drop the local commits from the branch's history.

There are four common states when comparing a local branch with its upstream (or three non-up-to-date states alongside up-to-date):

| Status | Meaning | Common Action |
| --- | --- | --- |
| Up-to-date | Local and upstream point to the same commit. | Continue working. |
| Ahead | Local has new commits that upstream does not have. | Review and push. |
| Behind | Upstream has new commits that local does not have. | Fetch, then update local per team conventions. |
| Diverged | Both local and upstream have their own commits. | Fetch, inspect both sides, then merge or rebase. |

Ahead and behind are relative relationships between two references. A branch can be both ahead and behind: for example, local ahead 2, behind 3 means local has two unique commits while upstream has three unique commits.

## 2. Checking Upstream and Branch Status

Before synchronizing, confirm which branch you are on and which upstream it tracks:

~~~bash
git status --short --branch
git branch -vv
git branch -r
~~~

- git status --short --branch shows the current branch and can display ahead/behind counts if upstream is configured and remote info is up to date.
- git branch -vv displays local branches along with the upstreams they track.
- git branch -r lists remote-tracking branches currently in the local repository.

If a branch does not yet have an upstream, you can set it on the first push:

~~~bash
git push -u origin feature/report-export
~~~

The -u option sets the upstream for the local branch once the push succeeds. If the branch already exists on the remote and you need to reconfigure upstream, run:

~~~bash
git branch --set-upstream-to=origin/feature/report-export feature/report-export
~~~

Make sure the local and remote branch names are right before changing tracking settings. Upstream helps default status, pull, and push commands know which branches correspond.

## 3. Fetching Before Deciding How to Integrate

Ahead/behind information is trustworthy only when remote-tracking refs have been updated recently. Fetch first:

~~~bash
git fetch origin
git status --short --branch
~~~

Fetch retrieves new data and updates remote-tracking references such as origin/main. It does not automatically modify the local branch or working tree. That lets you inspect both sides before selecting how to integrate.

Suppose the current branch has an upstream configured. The following command counts commits unique to each side:

~~~bash
git rev-list --left-right --count HEAD...@{upstream}
~~~

The output consists of two numbers separated by a tab:

~~~text
2    3
~~~

With the order HEAD...@{upstream}, the first number is commits unique to HEAD (local); the second is commits unique to upstream. For instance, 2 and 3 means local has two unique commits and upstream has three unique commits.

To inspect the specific commits:

~~~bash
# View commits unique to each side in a single graph
git log --oneline --left-right --graph HEAD...@{upstream}

# View only commits local has that upstream does not
git log --oneline @{upstream}..HEAD

# View only commits upstream has that local does not
git log --oneline HEAD..@{upstream}
~~~

In --left-right output, < marks commits present only on the left side (HEAD), and > marks commits present only on the right side (upstream). This view helps confirm teammates' commits and local commits before altering history.

If you want to find which commit the two branches diverged from, run:

~~~bash
git merge-base HEAD @{upstream}
~~~

The command returns the commit ID of the nearest common ancestor (merge base) in normal history. This is the commit Git uses as the baseline to compute a three-way merge.

## 4. Choosing How to Update the Local Branch

Once you understand which commits exist on both sides, choose an integration method matching your team's policy and history state.

### Fast-forward when local has no separate commits

If upstream has simply moved forward and HEAD is an ancestor of upstream, Git can update the local branch by advancing the pointer to the new commit:

~~~text
C---D---E  origin/main
     ^
     main (local before update)
~~~

Run:

~~~bash
git merge --ff-only @{upstream}
~~~

The --ff-only option permits fast-forward only. If the two branches have diverged, the command stops instead of creating a merge commit. This is useful when updating a stable branch and requiring history to move straight ahead.

### Merge when you want to preserve history on both sides

Merge combines two lines of history while keeping existing commits intact:

~~~bash
git merge @{upstream}
~~~

If the two branches have diverged, Git normally creates a merge commit with two parents once merging succeeds. The history graph clearly shows that local commits and upstream commits were combined.

~~~text
          A1---A2
         /       \
C-------+---------M  main
         \       /
          B1---B2    upstream
~~~

Merge fits when the team wants to preserve shared history, when multiple people work on the same branch, or when explicitly showing merge points matters to the review workflow. If conflicts occur, Git prompts you to resolve them before creating the merge commit.

### Rebase when you want to place private commits on a new base

Rebase takes the local branch's unique commits and replays them on top of upstream:

~~~bash
git rebase @{upstream}
~~~

Before rebase:

~~~text
             A1---A2  main
            /
C----------+
            \
             B1---B2  upstream
~~~

After successful rebase:

~~~text
C---B1---B2---A1'---A2'  main
~~~

Commits A1' and A2' receive new commit IDs because their parents and commit objects are recreated. Rebase typically produces a linear, easy-to-read history, but should only be used on personal commits that others have not built upon, unless the team has agreed on rewriting history.

Do not arbitrarily rebase a shared branch or published commits that teammates are building on top of. Changing commit IDs can force others to rework their local history.

### Quick selection table

| Method | History Result | When Appropriate |
| --- | --- | --- |
| merge | Preserves both commit lines and adds a join point when needed. | Shared branches, when integration points must be recorded or shared commits kept intact. |
| rebase | Replays local commits on top of upstream; local commit IDs change. | Private, unshared local commits when the team wants linear history. |
| merge --ff-only | Moves the branch only if upstream is a descendant of local. | Safe updates without creating a merge commit or rewriting history. |

No single choice fits every repository. Follow team conventions, especially for main, release, and branches used by multiple collaborators.

## 5. Pull and Configuring Integration Behavior

The pull command fetches and then integrates retrieved data into the current branch. Integration behavior depends on command options and configuration:

~~~bash
# Accept fast-forward only
git pull --ff-only

# Fetch then rebase local commits onto upstream
git pull --rebase

# Fetch then merge upstream into the current branch
git pull --no-rebase
~~~

If you want a repository to always follow an explicit policy, configure it specifically for the current repository:

~~~bash
# Reject pull if the branch has diverged
git config pull.ff only

# Or prefer rebase on pull
git config pull.rebase true

# Or prefer merge on pull
git config pull.rebase false
~~~

Pick one policy matching your team's workflow. If you are unsure which setting is active, check with:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
~~~

Fetching separately and inspecting the log is usually easier to evaluate when a branch has diverged or multiple people update the repository concurrently. Pull is convenient for daily routine once you understand and agree on the integration policy.

## 6. Why Concurrent Pushes Can Be Rejected

Git does not allow a normal push to drop commits currently referenced on the remote. When the server receives a push, it checks whether the ref update can advance as a fast-forward.

Example:

1. Both you and a teammate have local copies starting from commit C.
2. Your teammate creates A1 and pushes; origin/main moves from C to A1.
3. You create B1 based on C and push.
4. The server rejects it because updating C to B1 would drop A1 from the remote branch.

Common message:

~~~text
! [rejected] main -> main (non-fast-forward)
error: failed to push some refs
~~~

This is a history-protection mechanism. A rejected push does not mean local commits are lost; your commits are still in your local repository. You need to fetch the new changes, integrate them into your local branch, and push again.

Resolution workflow:

~~~bash
# 1. Retrieve latest state
git fetch origin

# 2. Inspect commits on both sides
git log --oneline --left-right --graph HEAD...@{upstream}

# 3. Choose merge or rebase per convention
git rebase @{upstream}

# 4. Run appropriate checks, then push again
git push
~~~

This example uses rebase as an option for private, unshared commits. If the branch is shared or the team requires keeping merge commits, use merge instead of rebase.

## 7. Multiple People Pushing Nearly Simultaneously

Imagine A and B both fetch origin/main when the remote is at C. A creates A1 and pushes successfully first. B creates B1 from C and pushes afterward. Because origin/main has already advanced to A1, B's push is no longer a fast-forward and is rejected.

~~~text
Initially:
C  origin/main, A/main, B/main

After A pushes:
C---A1  origin/main
 \
  B1    B/main
~~~

B needs to fetch and integrate A1:

~~~bash
git fetch origin
git log --oneline --left-right --graph HEAD...origin/main
git rebase origin/main
~~~

After rebase:

~~~text
C---A1---B1'  B/main
      ^
      origin/main
~~~

B runs tests and pushes again. If, while B is resolving, a third person pushes A2, B's push may be rejected again because the remote changed further. In that case, B fetches again, inspects the new commit, integrates A2, and only then pushes. Repeating this cycle is normal when a branch sees heavy activity.

The server updates references in a controlled manner so concurrent pushes never silently overwrite one another. A push succeeds only if the ref-update condition still holds at the moment the server applies it. Therefore, never treat a prior fetch result as a guarantee that the remote will stay still until you push.

## 8. Handling Conflicts During Integration

If both sides edit the same region in a way Git cannot automatically combine, merge or rebase may pause with a conflict. Identify the conflicted files:

~~~bash
git status
git diff
~~~

Open each file, read the conflict regions, and decide on the final content based on the requirements of both changes. After editing:

~~~bash
# Mark file as resolved during merge or rebase
git add path/to/file
~~~

If merging, complete with a commit when Git prompts:

~~~bash
git merge --continue
~~~

If rebasing:

~~~bash
git rebase --continue
~~~

Re-run appropriate tests after resolving. If you need to return to the state before the integration process began:

~~~bash
git merge --abort
git rebase --abort
~~~

Only run the abort command corresponding to the operation in progress. Abort cancels an incomplete merge or rebase; it is no substitute for safely saving other independent edits. Before starting integration, check the working tree and commit or stash work in progress.

## 9. Protecting Shared Branches and Handling Force Push

For shared branches like main, release, or a team integration branch, prefer fast-forward pushes and use merge requests/pull requests alongside branch protection rules whenever possible. Never use git push --force to bypass a non-fast-forward error on a shared branch: that command can lose commits others have pushed.

In some cases, you own a private feature branch and need to update previously pushed history—such as after an intentional rebase. When team policy permits, use:

~~~bash
git push --force-with-lease origin feature/report-export
~~~

--force-with-lease checks the expected position of the remote ref before overwriting. If the remote changed unexpectedly, Git rejects it to protect new commits. Even with this safeguard, notify and coordinate with anyone using the branch before rewriting history. This option does not make force push suitable for shared branches.

If your team does not permit rewriting published history, create a follow-up fix commit or merge instead of force pushing.

## 10. A Repeatable Synchronization Workflow

When you detect that local and upstream branches may have changed concurrently, you can follow this workflow:

~~~bash
# 1. Inspect branch and uncommitted edits
git status --short --branch
git branch -vv

# 2. Save work in progress by committing or stashing if needed
# Do not start integration without knowing where local changes stand.

# 3. Retrieve latest state from the remote
git fetch origin

# 4. Count and inspect commits unique to each side
git rev-list --left-right --count HEAD...@{upstream}
git log --oneline --left-right --graph HEAD...@{upstream}

# 5. Integrate according to team conventions
git rebase @{upstream}

# 6. Verify history and run tests
git status --short --branch
git log --oneline --decorate --graph -n 15

# 7. Share the result
git push
~~~

The rebase example in step 5 is for private, unshared local commits. For shared branches, substitute merge per team policy. If the branch has not diverged and only needs to advance to upstream, you can use merge --ff-only. If the push is rejected again because the remote kept changing, return to the fetch-and-inspect step; never repeat push assuming the remote stayed unchanged.

## 11. Collaboration Habits That Reduce Divergence

- Fetch regularly before starting a long piece of work and before integrating changes.
- Keep feature branches short-lived, breaking work into small commits with clear intent.
- Avoid multiple people editing a shared branch directly when the workflow can use personal branches and pull requests.
- Align across the team on using merge, rebase, or fast-forward-only.
- Check upstream and staged/unstaged changes before pulling, merging, or rebasing.
- Push after integrating and running checks; if rejected, fetch and re-evaluate.
- Never force push shared branches or commits others rely on.
- Coordinate before rewriting history on a shared branch.

Diverged branches reflect multiple people making independent progress on the same history. Fetch makes new changes visible; log and diff clarify differences; merge or rebase combines lines of work according to team policy. When everyone follows a clear workflow, concurrent updates can be handled repeatedly without losing each other's commits.

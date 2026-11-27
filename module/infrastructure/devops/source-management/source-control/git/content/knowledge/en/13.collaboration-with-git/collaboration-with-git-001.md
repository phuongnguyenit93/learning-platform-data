# Branch Ownership and the Principle of Not Rewriting Shared History

When multiple people work together on a repository, Git allows each person to develop on a separate branch and then integrate changes into a shared branch. However, if multiple people update the same branch without clear conventions, they can overwrite each other's work or lose commits that teammates are relying on. An important collaboration principle is that **each branch must have a clearly responsible person or role, and shared history must not be rewritten without coordinating with everyone involved**.

This lesson belongs to the **Collaboration with Git** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracking changes, and recovering from mistakes while preserving important history. Conventions around branch ownership and shared history help teams coordinate safely when pushing, pulling, reviewing, merging, and undoing changes.

## 1. Why Does a Team Need Branch Ownership Conventions?

In Git, a branch is fundamentally a named reference pointing to a commit. Each time a commit is created on the current branch, the branch reference is updated to point to the new commit. Git does not inherently know who owns a branch, nor does it automatically prevent two people from pushing to the same branch.

This means branch ownership is a **team working convention**, supported by access permissions, review workflows, and branch protection on the server. If the team does not agree on who is responsible for updating a branch, two people can create separate histories and push at different times. A rejected push may simply indicate that the remote has moved forward; an uncoordinated force push can make someone else's commits disappear from the tip of the branch they are tracking.

Ownership conventions help answer practical questions:

- Who decides the scope and purpose of the branch?
- Who is allowed to push directly, merge, or delete the branch?
- Who must be notified when a rebase or history change is needed?
- Who is responsible for handling errors when the branch has a faulty commit or an accidental push?
- When the branch is no longer needed, who confirms closing and deleting it?

A branch can have multiple contributors, but there should be one person or role responsible for coordinating it. Clear ownership does not mean that person does all the work; it means the team knows who holds responsibility for updating and communicating the status of the branch.

## 2. Distinguishing Local, Remote-Tracking, and Server Branches

Before establishing ownership, it is necessary to understand the types of branches:

| Reference Type | Example | Meaning |
|---|---|---|
| Local branch | <code>feature/payment</code> | A reference in the current clone, updated when creating commits or performing local branch operations |
| Remote-tracking branch | <code>origin/feature/payment</code> | A local reference recording the branch position on the remote after the most recent fetch |
| Server branch | The <code>feature/payment</code> branch in the repository on the <code>origin</code> server | The actual reference that team members access and update via push |

A remote-tracking branch is not the branch on the server, nor is it an ownership lock. It is local information updated by Git via <code>git fetch</code>. Therefore, before concluding whether the remote has changed, fetch the latest data:

~~~bash
git fetch origin
git branch -vv
git branch -r
~~~

If <code>feature/payment</code> is tracking <code>origin/feature/payment</code>, that indicates the local branch has an upstream configured. It does not prove that only one person is working on that branch. The team still needs to agree on the owner and how to coordinate.

## 3. Common Branch Ownership Models

There is no single model that fits every team. What matters is that the convention is easy to understand, consistently applied, and suited to the project's pace of development.

### Feature Branch Owned by One Person

This is a simple model for small teams or well-scoped work. The owner creates a branch from the base branch, develops on it, and pushes it. Teammates can review or contribute by agreement, while the owner coordinates integration.

Example:

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment-validation

# Make changes, then create a commit
git add src/
git commit -m "feat: validate payment requests"

# Push the branch to the remote and set upstream
git push -u origin feature/payment-validation
~~~

The branch can be shared for review, but the owner must notify others before performing operations that alter already-pushed history.

### Integration Branch Owned by Maintainers

For shared branches such as <code>main</code>, <code>develop</code>, or release branches, maintainers are typically responsible for integrating changes. Members develop on feature branches and submit pull requests or merge requests. Maintainers verify reviews, CI, and branch protection policies, and perform the merge.

In this model, many people can create commits on their own branches, but only a designated role is permitted to update the integration branch directly. This reduces the risk of accidentally overwriting shared history.

### Collaborative Branch Updated by Multiple People

Some work requires multiple people to edit the same branch, such as a short-lived integration branch for a release. In that case, the team needs to designate a coordinator, agree on how to pull the latest changes, and avoid rewriting commits that others have already fetched.

The team can agree on the following:

- The branch coordinator is responsible for notifying everyone before merging or changing history.
- Every member fetches frequently to see when the remote has advanced.
- Each commit has a clear purpose and does not include out-of-scope changes.
- Do not force push without consensus and a recovery plan.
- When the branch is complete, the maintainer verifies the result and then closes or deletes the branch according to process.

## 4. What Is Shared History?

Git stores history as a commit graph. Each commit contains snapshot content and links to its parent commit(s). Once a commit has been pushed to a remote branch, others can fetch it, branch off it, merge it, or build on top of it.

A commit is considered **shared** when there is a possibility that another person or system has used it as a base. For example:

- The commit has been pushed to a remote branch that teammates are tracking.
- The commit resides in a shared branch such as <code>main</code>, <code>develop</code>, or release.
- The commit has been used as the base for another branch, pull request, release pipeline, or traceable build.
- The commit has been fetched or checked out by someone else, even if the remote branch no longer points directly to that commit.

You do not always know who has fetched a commit. Therefore, the safe rule is to treat commits pushed to a shared branch as shared history. A branch having a personal name does not automatically prove its commits are private; if someone else has already based work on those commits, altering history can still cause disruption.

## 5. Why Can Rewriting History Cause Trouble?

Operations such as <code>git commit --amend</code>, <code>git rebase</code>, and <code>git reset</code> can change the position or identity of commits. When the content, parent commit, author, timestamp, or message changes, Git typically creates a new commit with a different hash.

For example, one team member pushes commit <code>A</code> to a branch:

~~~text
P---A   origin/feature/report
~~~

A teammate fetches and creates commit <code>B</code> based on <code>A</code>:

~~~text
P---A---B   colleague/feature/report
     \
      (A has already been used as a base)
~~~

If the first person rebases or resets to replace <code>A</code> with a new commit <code>A'</code>, the remote history may become:

~~~text
P---A'   origin/feature/report
~~~

The teammate's branch still contains the old history:

~~~text
P---A---B   colleague/feature/report
 \
  A'       origin/feature/report
~~~

The two sides no longer share the same ancestor chain. When the teammate pushes or pulls, Git may report a non-fast-forward error, require integrating the two history lines, or produce commits that duplicate content. If the first person uses force push, the remote reference skips <code>A</code>, even though that commit still exists in the teammate's clone.

Key point: force push moves the reference on the server. It does not immediately delete every copy of the commit across everyone's machines, but it changes the public history of the branch and forces clones relying on the old history to be reconciled.

## 6. Rules Before and After Sharing a Commit

Practical rules can be summarized as follows:

| Commit State | Usually Safe Operations | What to Avoid |
|---|---|---|
| Exists only locally, unused by anyone else | Amend, interactive rebase, reset to organize or fix commits | Losing local data due to unchecked reset or restore |
| Pushed to a personal branch, confirmed nobody relies on it | Can coordinate to edit history if the team allows it | Force pushing unilaterally just because the branch has a personal name |
| Pushed to a branch used by multiple people | Create a new commit to fix or revert | Rebasing, amending, resetting, and force pushing without coordination |
| Integrated into main or a release branch | Prefer revert and follow-up fix commits | Rewriting history that has been released or built upon by other branches |

### When Commits Are Still Private

If commits exist only locally and have not been used by others, you can edit history to make commits cleaner and clearer:

~~~bash
# Edit the message or add changes to the most recent commit
git commit --amend

# Reorder, squash, or edit recent local commits
git rebase -i HEAD~3

# Move the local branch back to the previous commit, keeping changes in the working tree
git reset --mixed HEAD~1
~~~

Use these operations only when you understand the state of your working tree and index. <code>git reset --hard</code> can discard uncommitted changes in the working tree and index; do not use it unless you are certain any needed data is backed up.

### When Commits Have Already Been Shared

If a commit is already on a shared branch, preserve the existing history and add a new commit to fix the issue. For example, if a previous commit introduced a bug, fix the source code and create a remediation commit:

~~~bash
git add src/
git commit -m "fix: handle empty payment response"
git push
~~~

If you need to undo the effect of a shared commit, use <code>git revert</code>:

~~~bash
git revert <commit-hash>
git push
~~~

<code>git revert</code> creates a new commit that applies the inverse changes of the selected commit. The old commit remains in history, so clones that already fetched the old commit can still integrate history consistently.

For a merge commit, you must specify the mainline parent you want to keep. The command takes the form:

~~~bash
git revert -m 1 <merge-commit-hash>
~~~

Do not pick <code>-m 1</code> out of habit without checking the parent order and intended outcome. Reverting a merge commit affects how Git handles subsequent merges; review the generated diff and coordinate with the maintainer before pushing.

## 7. Comparing Amend, Rebase, Reset, Revert, and Force Push

These commands solve different problems. Understanding them properly helps you choose the right fix based on whether the commit has been shared.

| Command | Primary Effect | Appropriate When |
|---|---|---|
| <code>git commit --amend</code> | Replaces the most recent commit with a new commit | Commit is unshared or rewriting has been agreed upon |
| <code>git rebase</code> | Replays commits onto a new base, creating new commit history | Unshared private branch or team-coordinated update |
| <code>git reset</code> | Moves the current branch and optionally updates index/working tree depending on mode | Editing unshared local history |
| <code>git revert</code> | Creates a new commit that reverses changes from an earlier commit | Undoing already-shared changes |
| <code>git push --force</code> | Forces the remote ref to match local history | Only in authorized situations with a clear plan and coordination |
| <code>git push --force-with-lease</code> | Conditional force push based on the expected remote ref value | Reducing risk of overwriting unknown remote updates when rewriting is team-approved |

### Why Does Force-With-Lease Not Replace Coordination?

<code>git push --force-with-lease</code> checks that the remote ref is still at the value the client expects before updating it. This helps prevent overwriting a new change on the remote that you are unaware of, such as a teammate pushing additional commits after your last fetch.

However, this command cannot know whether a teammate has fetched the old commit, created a branch from it, or referenced it in a pull request. Even if the remote is still at the expected value, if someone else has already built on that history, force-with-lease will still rewrite the branch and require their work to be recovered or reintegrated.

Therefore:

- Prefer not rewriting history on shared branches.
- If there is a legitimate reason to rewrite, notify everyone involved and agree on a time window.
- Ask everyone to pause pushing during the change window.
- Fetch and verify the remote ref before operating.
- Use <code>--force-with-lease</code> instead of <code>--force</code> if policy allows force updates.
- Afterward, announce the new commit and instruct teammates on how to resync their branches.

Force-with-lease is an additional technical safeguard, not a substitute for collaborative processes.

## 8. Feature Branch Workflow

An easy-to-follow workflow gives each task its own branch, a clear owner, and integrates into the shared branch only after review:

~~~mermaid
flowchart TD
    A["Maintainer updates main"] --> B["Owner creates feature branch"]
    B --> C["Commit small, purposeful changes"]
    C --> D["Push branch and open pull request"]
    D --> E["Review and run checks"]
    E --> F{"Meets requirements?"}
    F -->|"No"| G["Owner fixes and pushes new commits"]
    G --> D
    F -->|"Yes"| H["Maintainer integrates into main"]
    H --> I["Close pull request and clean up branch"]
~~~

Example basic commands:

~~~bash
# Update the base branch using fast-forward
git switch main
git fetch origin
git pull --ff-only origin main

# Create a dedicated branch for the task
git switch -c feature/customer-export

# After editing source code
git status
git add src/
git diff --staged
git commit -m "feat: export customer records"

# Push the branch to the remote
git push -u origin feature/customer-export
~~~

During review, if changes are needed, the owner can add new commits and push them. If the team requires a clean branch history before merging, confirm whether anyone else is using the branch. Only rebase or squash on a shared branch when everyone agrees and knows how to resync.

After the pull request is integrated, the maintainer confirms the branch is no longer needed and deletes it according to repository policy. Deleting the branch does not delete the integrated commits; the commits remain part of the target branch's history.

## 9. Configuring Shared Branch Protection Rules

Local Git does not have a built-in mechanism to enforce branch ownership across team members. Git servers such as GitHub, GitLab, or Bitbucket provide branch protection or rulesets to enforce part of these conventions.

Commonly used policies:

- Block direct pushes to the main branch.
- Require a pull request or merge request before integration.
- Require at least one or more reviews.
- Require CI, tests, or security checks to pass before merging.
- Restrict force pushes and branch deletions on important branches.
- Grant merge permissions only to maintainers or designated groups.
- Require branches to be up to date with the base branch before merging if the project needs it.

Branch protection helps reduce accidental actions, but it does not replace communication. An unprotected feature branch may still contain history that teammates rely on. The team must uphold the rule of not rewriting shared history on any branch used by multiple people or systems.

## 10. When Shared History Must Be Rewritten

There are cases where a team is forced to rewrite history, such as discovering a committed secret, needing to purge sensitive data from the entire history, or restructuring commits prior to a release. This is a repository-level coordinated effort, not an individual operation on an active shared branch.

Before proceeding:

1. Identify the exact scope of affected refs: branches, tags, pull requests, forks, and clones.
2. Notify contributors and maintainers; designate a single coordinator.
3. Pause pushes and merges to the affected refs.
4. Record the necessary commit hashes and ref states so they can be cross-checked or restored.
5. Perform the rewrite in a verifiable environment, review the results, and confirm the target data is completely removed.
6. Update the remote according to the approved plan, then clearly announce the new commits/refs.
7. Instruct team members on how to resync their clones; do not leave each person guessing whether to reset, rebase, or merge.

If the reason is an exposed token, password, or private key, rewriting history does not automatically invalidate that secret. Revoke or rotate the credentials immediately according to security procedures while cleaning history following the hosting platform's guidelines.

If an accidental force push has rolled back a remote branch to an older history:

- Stop further pushes to avoid making recovery harder.
- Notify maintainers and anyone working on the branch.
- Gather commit hashes still available in local clones or saved references.
- Identify the exact commits that need to be restored and inspect any new commits created afterward.
- Have the maintainer coordinate restoring the ref and then guide each member in reintegrating their work.

Do not run another force push simply assuming it will restore the branch to its prior state. Before updating the ref, know exactly which commits are missing and who has created changes based on the current history.

## 11. Common Collaboration Scenarios

| Scenario | Recommended Handling |
|---|---|
| Most recent commit has a wrong message, not yet pushed | Use <code>git commit --amend</code> |
| Multiple small commits on a private local branch, unused by others | Can use <code>git rebase -i</code> to reorder or squash |
| Teammate pushed additional commits to a shared branch | Fetch, inspect history, and integrate via merge or rebase per convention; do not reset remote |
| Buggy commit has entered <code>main</code> | Create a fix commit or use <code>git revert</code> |
| Want to update a feature branch with <code>main</code> | Fetch then merge or rebase per team policy; confirm who is using the branch |
| Personal branch was pushed, and a teammate branched off it | Treat the branch as shared; coordinate before any history rewrite |
| Release branch needs to remove an integrated change | Follow the release process, usually creating a reviewed revert commit or hotfix |

### When a Push Is Rejected Due to Non-Fast-Forward

A non-fast-forward error usually means the remote branch has moved ahead with one or more commits that the local branch does not contain. This is a signal to fetch and inspect history:

~~~bash
git fetch origin
git log --oneline --graph --decorate --all -20
~~~

If both sides have separate commits, integrate according to team convention. For example, using merge:

~~~bash
git switch feature/customer-export
git merge origin/feature/customer-export
~~~

Or rebase if the branch is under your coordination and the team agrees on this approach:

~~~bash
git switch feature/customer-export
git rebase origin/feature/customer-export
~~~

After resolving conflicts and verifying the result, perform a normal fast-forward push. Never treat non-fast-forward as a default reason to run <code>git push --force</code>; this error usually protects existing remote commits from being overwritten.

## 12. Team Branch Ownership Checklist

Before starting a branch, agree on:

- Branch name and task objective.
- Responsible owner or maintainer coordinating the branch.
- Who can push directly and who has merge permissions.
- Whether the branch is shared for multiple contributors to commit or only for review.
- Whether updates from the base branch use merge or rebase.
- Whether history rewriting is allowed after pushing, and if so, whose approval is required.
- When finished, who closes the pull request and cleans up the branch.

Before editing history, self-check:

- Do the commits still exist only in my local repository?
- Has anyone fetched, checked out, branched from, or committed on top of them?
- Are the commits in a shared branch, tag, release, or traceable pipeline?
- Can this be resolved with a new commit or a revert instead?
- If rewriting is unavoidable, does everyone involved know and agree?

If you have not verified who is using that history, treat it as shared history and choose to fix it with a new commit.

## 13. Self-Check Exercises

Practice in a test repository with two clones or two users:

1. Create a branch <code>feature/shared-demo</code>, commit a change, and push it to the remote.
2. In the second clone, fetch and create a new commit based on that branch.
3. Return to the first clone, try amending the already-pushed commit, and observe why the commit hash changes.
4. Compare the histories of both clones using <code>git log --oneline --graph --decorate --all</code>.
5. Try a normal push and explain why Git rejects it as non-fast-forward.
6. Restore the collaborative state using merge or rebase according to a chosen convention, without force pushing.
7. Create a faulty commit on a shared test branch and use <code>git revert</code>. Observe that the old commit remains in history.
8. Write a short team convention: who owns a branch, when rebasing is allowed, and how to notify others before altering pushed history.

When a team clearly knows who coordinates each branch, distinguishes private commits from shared commits, and chooses revert over rewriting shared history when undoing work, collaboration becomes far more predictable and recoverable. This provides the foundation for consistently applying pull requests, reviews, merges, and release workflows.

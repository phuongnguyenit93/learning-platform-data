# Agreeing on Merge, Squash, or Rebase When Integrating

When a task branch is ready to enter the target branch, the team must agree on how changes are recorded into Git history. **Merge**, **squash**, and **rebase** all bring changes from the task branch into the target branch, but they produce different histories. This choice affects not only the shape of the commit graph, but also traceability, reviews, reverts, and how work continues on branches after integration.

Within the **Collaboration with Git** chapter of the **SOURCE_CONTROL_GIT** module, this lesson focuses on establishing an integration agreement that the entire team can apply consistently. We will distinguish the three strategies, identify suitable scenarios, align rules around pull requests, and handle exceptions such as shared branches, hotfixes, or multi-part changes requiring separate traceability.

After this lesson, you will be able to:

- Explain the history produced by a merge commit, squash merge, and rebase.
- Choose a strategy based on review, traceability, history preservation, and operational goals.
- Distinguish rebasing to update a task branch from rebasing as the final integration method.
- Propose conventions for feature branches, pull requests, release branches, and shared branches.
- Inspect integration results and select an appropriate revert method.

## 1. Why Does a Team Need an Agreement?

Suppose the target branch is main and a team develops a login feature on the feature/login branch. During development, the feature branch may accumulate multiple commits:

- Build the login screen.
- Add input validation.
- Fix issues after review.
- Update tests.
- Complete documentation.

When integrating, the team can keep all those commits and record a merge point, combine the changes into a single commit, or replay each commit onto the new tip of the target branch. All three approaches can produce the exact same final working tree content, yet the recorded history differs.

If each member picks a different method, the repository history becomes hard to read and unpredictable. One pull request might create a merge commit, another only a squashed commit, while someone else rebases a branch already used by teammates. When tracking down bugs or reverting, the team has to interpret multiple history styles and spends extra time determining how a change entered.

A shared agreement answers key questions upfront:

- Does the team want history to explicitly show task branches, or should each pull request become one commit?
- Do small development commits need to be preserved for traceability?
- Are members allowed to rewrite history on already-pushed branches?
- Can a feature branch continue being used after integration?
- When does a change need to preserve individual commits, such as release fixes or multi-step independent changes?
- Who is responsible for resolving conflicts and verifying CI before integration?

## 2. Merge: Keeping Commits and Recording the Integration Point

Merge combines the history of the task branch with the target branch. When the two branches have diverged, Git creates a merge commit with two parents. The original commits from both branches preserve their identifiers and ancestor relationships.

Suppose both branches started from B:

~~~text
Before merge:
      C1---C2  (feature/login)
     /
A---B
     \
      D1---D2  (main)
~~~

After merge:

~~~text
      C1---C2
     /       \
A---B         M  (main)
     \       /
      D1---D2
~~~

Commit M records the moment the two lines of history were combined. Readers can inspect the individual feature branch commits, follow the development sequence, and see which branch was integrated.

You can perform the merge from the target branch:

~~~bash
git switch main
git merge --no-ff feature/login
~~~

The **--no-ff** option instructs Git to create a merge commit even when a fast-forward is possible. Without this option, Git may simply move the branch pointer when history permits; when the two branches have diverged, Git still needs a merge commit to join them.

**When should a team agree to use merge?**

- The team wants to preserve branch structure and integration timing.
- The task branch contains multiple meaningful commits worth keeping separately.
- Commits have already been shared and need their identifiers and ancestry preserved.
- It is important to inspect the development process or trace individual commits within a pull request.
- The repository has a release workflow that treats merge commits as integration milestones.

Merge preserves full history, though the commit graph can become heavily branched. If a team creates merge commits for every minor change, the log may fill up with commits that merely serve synchronization. Determine whether merge commits truly provide information the team wants to keep.

## 3. Squash: Combining Changes into One Commit

Squash takes the net changes of the task branch relative to its common base with the target branch and records them as a single commit on the target branch. Individual commits from the task branch do not become ancestors of the squash commit.

Before squash:

~~~text
      C1---C2---C3  (feature/login)
     /
A---B---D1  (main)
~~~

After squash and creating commit S:

~~~text
A---B---D1---S  (main)
     \
      C1---C2---C3  (feature/login, old history)
~~~

Commit S contains the combined result of changes from C1 through C3, but has no parent pointing to C3. Therefore, Git does not consider commits C1, C2, and C3 to be integrated in the ancestry graph, even though their content entered main via S.

You can perform a squash in Git with:

~~~bash
git switch main
git merge --squash feature/login
git diff --cached
git commit -m "feat(auth): add login flow"
~~~

The **git merge --squash** command prepares the working tree and index as if the changes were merged, without creating a merge commit or automatically creating a regular commit. After inspecting the staged changes, the developer creates a new commit with **git commit**. If conflicts occur, resolve the files, stage the result, and create the squash commit.

Many pull request platforms also offer a **Squash and merge** button or option. The platform creates the combined commit on the target branch following the pull request workflow. While the UI operation differs from local Git commands, the underlying historical meaning is identical: changes are recorded as one new commit without keeping the feature branch commits as ancestors of the target branch.

**When should a team agree to use squash?**

- Each pull request represents a single, clearly scoped unit of change.
- Commits on the feature branch are mostly drafts, review fixes, or checkpoints.
- The team wants a concise main branch log where each commit corresponds to one pull request or one logical change.
- The team wants to revert an integrated feature by identifying a single combined commit.

Squash keeps the target branch history clean, but removes individual feature branch commit structure from the target branch's ancestry. If small commits carry vital details such as individual migration steps, independent changes, or debugging milestones, combining them can reduce traceability.

After squashing, close or delete the integrated feature branch. If you continue developing on that same branch, the old commits are still not ancestors of the squash commit on main. Subsequent integrations may force the team to re-review old changes or encounter confusing diffs. If work continues after a pull request has been squashed, create a new branch from the updated target branch.

## 4. Rebase: Replaying Commits onto a New Base

Rebase takes the commits on the task branch that are not yet in the target branch and replays them one by one onto the latest commit of the target branch. Git creates new commits because their parents change; consequently, the commit identifiers also change.

Before rebase:

~~~text
      C1---C2  (feature/login)
     /
A---B
     \
      D1---D2  (main)
~~~

After rebase:

~~~text
A---B---D1---D2---C1'---C2'  (feature/login)
             (main)
~~~

C1' and C2' are new commits replayed from the changes in C1 and C2. The post-rebase history is linear and has no merge commits created solely to update the feature branch.

Workflow for updating a feature branch onto the latest main:

~~~bash
git fetch origin
git switch feature/login
git rebase origin/main
~~~

After a successful rebase, you can integrate into main via fast-forward if main is still at the exact base onto which the feature branch was rebased:

~~~bash
git switch main
git merge --ff-only feature/login
~~~

On pull request platforms, teams can also choose the **Rebase and merge** strategy. The platform replays the pull request's commits onto the target branch and places the new commits on the target branch without creating a merge commit. Whether the source branch itself is updated depends on the platform and action; never assume a pull request integration automatically updates your local branch.

**When should a team agree to use rebase?**

- The feature branch is still owned by one person or a team that has agreed to rewrite history.
- Individual commits are meaningful and worth preserving after integration.
- The team wants a linear history while still viewing individual commits instead of collapsing them into a single squash commit.
- The branch needs updating onto a fresh target base before review or integration.

Rebase preserves commits step by step, but generates new commit identifiers. Never arbitrarily rebase a branch that has already been pushed and is actively used by others. If rewriting a remote branch has been agreed upon, notify collaborators and push with a safe mechanism such as **--force-with-lease** after checking the remote state:

~~~bash
git fetch origin
git push --force-with-lease origin feature/login
~~~

**--force-with-lease** checks that the remote is still at the state expected locally before updating the reference. It reduces the risk of overwriting someone else's new commits compared to a regular force push, though it does not replace coordination and verification. If a branch is used by multiple people, the safer approach is usually to avoid rewriting shared history.

## 5. Distinguishing Updating a Branch via Rebase vs. Integrating via Rebase

Both actions are often referred to simply as rebase, yet they serve two different purposes:

1. **Updating a task branch**: replaying local commits onto the latest main base so the task branch can be verified against recent changes. Afterward, the team can still choose a merge commit or squash when integrating the pull request.
2. **Integrating via rebase**: using rebase as the final strategy to bring the task branch's commits into the target branch, typically via the platform's Rebase and merge option or rebasing followed by a fast-forward.

For example, a pull request might be updated using:

~~~bash
git fetch origin
git switch feature/login
git rebase origin/main
~~~

Afterward, the team can still pick **Squash and merge** so each pull request produces just one commit on main. Having rebased the task branch does not obligate you to perform the final integration via rebase. Similarly, a pull request can be merged using a merge commit without rebasing the source branch first if the team accepts the existing history structure.

When writing conventions, specify both decisions separately: **how to update feature branches** and **how to integrate pull requests**. This avoids the misconception that choosing rebase to sync branches requires using Rebase and merge at the final step.

## 6. Comparing the Three Strategies

| Criterion | Merge | Squash | Rebase |
| --- | --- | --- | --- |
| Do feature branch commits become ancestors of the target branch? | Yes, via merge commit or fast-forward integration | No | Yes, as replayed commits with new identifiers |
| Creates a merge commit? | Yes when branches diverged; can be forced with --no-ff | No | No |
| Preserves individual feature branch commits? | Yes | No in target branch history | Yes, though commits are recreated |
| Changes old commit identifiers? | No | Combined commit gets a new ID; old branch commits remain intact on source branch | Yes for replayed commits |
| History shape | Can have branches | Clean, typically linear | Typically linear |
| Best suited for | Recording branch structure and merge points | One pull request representing one unit of change | Keeping individual commits with linear history |
| Caveat | Graph may contain many merge commits | Does not preserve source commit ancestry | Avoid rewriting already-shared commits |

No strategy is universally superior to the other two. Teams should choose based on what information needs to be preserved in history and how people use that history for reviews, releases, investigations, and recovery.

## 7. Criteria to Align On Within the Team

### Purpose of a Commit on the Main Branch

The team needs to agree on what a commit on main represents:

- One pull request or one change request: squash is usually appropriate.
- One integration of multiple independently meaningful commits: merge or rebase may be appropriate.
- An integration milestone between long-lived branches: merge commits clearly express branch relationships.

A commit should have a message clear enough for readers to understand the change without opening the entire pull request. If squashing, you can use the pull request title as the commit message by convention, accompanied by a ticket ID or scope.

### Traceability and Bug Investigation

When using merge or rebase, the team can use the log to trace individual commits within the feature branch. With squash, target branch history contains only the combined commit; detailed content and discussions must be preserved in the pull request, issue, or review system.

If the team frequently uses **git bisect** to track down bug-introducing commits, consider commit granularity. Squash creates a large step that may contain many edits; merge and rebase keep smaller steps, though each small commit must remain buildable and testable for bisect to work effectively.

### How to Undo Changes

With squash, one pull request usually corresponds to one commit, so that single commit can be reverted:

~~~bash
git revert <squash-commit>
~~~

With a merge commit, you can revert the entire integrated result by specifying the mainline parent:

~~~bash
git revert -m 1 <merge-commit>
~~~

The **-m 1** flag selects the first parent as the mainline in the standard case of merging a feature branch into main. Before running it, inspect parent order using log or show; picking the wrong parent produces the opposite of what you want. Reverting a merge commit also affects how Git handles future merges, so understand the impact before applying it.

With rebase, replayed commits exist as individual commits on the target branch. You can revert individual commits or a planned range of commits, provided you identify the exact commits and dependency order. Revert creates new commits to reverse changes without erasing published history.

### Shared State of a Branch

Before rebasing, ask whether commits have already been pushed or relied upon by others. Commits that exist only locally are much easier to rewrite. Shared remote branches require explicit coordination rules; otherwise, a single force push can drop references to a teammate's new work.

### How the Team Reviews and Tests

Squash does not replace per-part review. A pull request still needs descriptions of objective, scope, impact, and test results. If using merge or rebase to preserve individual commits, the team may require each commit to have focused content, clear messages, and no broken builds.

Define minimum integration conditions:

- Review has been approved per policy.
- CI and mandatory checks have succeeded.
- Conflicts have been resolved, with the resolver understanding both sides' changes.
- The target branch has been updated per team sync policy.
- Titles and commit messages are clear enough for future traceability.

## 8. A Reference Decision Matrix

| Situation | Usually Suitable Strategy | Reason |
| --- | --- | --- |
| Small pull request, single goal, multiple review-fix commits | Squash | Main branch gets a single commit representing the final change. |
| Pull request with multiple independent, meaningful, tested commits | Merge or rebase | Preserves development steps for traceability. |
| Need to clearly see when two long-lived branches integrated | Merge commit | Graph preserves the relationship between the two lines of history. |
| Unshared personal feature branch needing update onto latest main | Rebase source branch | Local commits are replayed onto the fresh base. |
| Feature branch shared among multiple people | Merge or coordinated rebase workflow | Avoids rewriting history that others depend on. |
| Release or hotfix branch needing milestones and change order preserved | Usually merge or rebase per release convention | History must reflect relationships between development and release branches. |

These are discussion guidelines, not rigid rules. For example, a large pull request may still need a merge commit if branch structure matters; a small change may still need individual commits preserved if each commit represents a verifiable migration step.

## 9. Example of an Actionable Integration Policy

A team can start with the following convention and adjust as needed:

| Scope | Sample Convention |
| --- | --- |
| Short-lived feature branch | Each pull request addresses one goal with full description, review, and CI. |
| Updating a feature branch | Fetch then rebase onto main when commits are unshared; if shared, coordinate before rewriting history. |
| Integrating standard pull requests | Squash and merge so main has one commit per pull request. |
| Pull requests needing individual commits kept | Allow merge or rebase and merge when commits have distinct value and the team agrees. |
| Release or long-lived branches | Use merge commits when clear cross-branch integration relationships must be preserved. |
| After squash integration | Close or delete the source branch; create a new branch from main if continuing work. |
| Undoing changes | Revert the squash commit or integration commit per the branch owner's instructions. |

This example fits teams using short-lived pull requests that want a clean main branch. Teams with release workflows, auditing needs, or commit-level traceability requirements may default to merge instead of squash. What matters is explicitly documenting exceptions and who is authorized to approve them.

## 10. Pre-Integration Alignment Workflow

### Step 1: Identify the Target Branch and Change Objective

Explicitly note whether the pull request goes into main, develop, or a release branch. Verify whether the pull request contains a single logical goal or bundles multiple independent changes. The clearer the goal, the easier it is to decide between a single squash commit or preserving multiple commits.

### Step 2: Check Branch State and History

~~~bash
git status -sb
git fetch origin
git log --oneline --graph --decorate --left-right 'HEAD...origin/main'
~~~

Ensure the working tree has no unexpected changes. Determine whether the branch has diverged, whether any commits are already shared, and whether the source branch will continue being used after integration.

### Step 3: Select the Strategy per Convention

Before clicking merge on the platform or running commands, confirm whether the pull request uses:

- Merge commit to preserve branch structure.
- Squash and merge to combine into one commit.
- Rebase and merge to keep individual commits while replaying them onto the target branch.

Do not confuse the option of updating the source branch via rebase with the pull request's Rebase and merge strategy. These are two independent decisions.

### Step 4: Review and Verify

Review the final diff, verify commit messages, check CI, and ensure conflicts were resolved accurately. If a rebase strategy creates new commits, re-verify test status on the post-rebase history according to CI policy.

### Step 5: Integrate and Inspect the Target Branch

After integration, inspect history:

~~~bash
git fetch origin
git log --oneline --graph --decorate -12 origin/main
~~~

Confirm the changes appear on the target branch, the history matches the chosen strategy, and the pull request is closed in the expected state. If squashed, keep a link to the pull request or issue so readers can locate discussions and review evidence.

### Step 6: Clean Up Branches and Notify

If the source branch is no longer in use, delete it according to team policy. For squashed branches, do not continue developing on the old history without a clear reason; create a new branch from the target branch. If a branch is kept for ongoing work, define how it will be synced to avoid repeatedly integrating old changes.

## 11. Common Misconceptions

### Is a Squash a Merge Commit?

No. Squash places the net changes into the index to create a regular commit on the target branch. That commit does not have two parents like a merge commit, nor does it record the source branch commits as ancestors.

### Does Rebase Delete Old Commits?

Rebase creates new commits from old changes. The old commits may still exist in the source branch, remote, or reflog until no references remain and they are garbage collected. What changes is that the rebased branch points to the new history; do not view rebase as immediately deleting all old records.

### Can You Rebase a Branch and Still Squash When Integrating?

Yes. Rebase can be used to update the source branch onto the latest main. When the pull request is ready, the team can still choose squash to create a single commit on main.

### Does Squash Preserve Review Content?

Squash only determines how commits are stored in Git. Discussions, reviews, CI, and issue links depend on the pull request platform and team retention policies. Therefore, use commit messages and pull request links to preserve traceability.

### Is a Merge Commit Always Better Because It Keeps More Information?

No. It preserves branch relationships and integration points, but it also makes the graph more complex. If commits on the branch are merely checkpoints or minor fixes, keeping all of them can make history harder to read.

### Does Rebase Always Require a Force Push?

No. Rebasing a local-only branch does not require pushing. If the branch has already been pushed and rebasing alters commits on the remote, updating the remote requires a history-rewriting push; perform this only after coordinating with anyone using the branch and checking with force-with-lease.

## 12. Strategy Selection Self-Check

A pull request adding a report export feature has three commits:

- E1: add data filter.
- E2: add CSV format.
- E3: fix tests and docs after review.

Consider:

1. If E1, E2, and E3 are just completion steps for a single feature and the team wants one representative commit on main, what should you choose?
2. If E1 and E2 are two independent changes needing separate traceability and E3 is simply a test fix, which strategy preserves commit history?
3. If the report export branch has already been pushed and used by two team members, what must be considered before rebasing?
4. If the team wants to update the source branch onto the latest main yet still squash the pull request, can both be done?

**Hint:** Squash suits a single-goal feature when one commit on main is desired. Merge or rebase suits keeping individual commits; choosing between them depends on whether the team needs merge commits and branch relationships. On a shared branch, coordinate before rewriting history; merge generally avoids changing identifiers of shared commits. You can rebase the source branch to stay up to date and still choose squash when integrating the pull request.

## Conclusion

Merge preserves commits and records integration points; squash combines net changes into a new commit on the target branch; rebase replays each commit onto a new base and assigns new commit identifiers. An effective agreement clearly specifies how task branches are updated, the pull request integration strategy, rules for shared branches, commit message standards, review/CI conditions, and how to revert. When everyone follows the same convention, Git history becomes easier to read and maintain.

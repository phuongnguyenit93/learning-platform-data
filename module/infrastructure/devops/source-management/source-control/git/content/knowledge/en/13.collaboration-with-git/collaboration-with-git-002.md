# Workflow for Receiving Tasks, Branching, Committing, Syncing, and Handover

Git enables multiple people to develop a project together by storing change history and allowing each person to work on a dedicated branch. However, merely having Git in a project is not enough for smooth collaboration. A team needs a consistent workflow: receiving requirements, updating the base source code, creating a branch, making changes, committing, syncing, reviewing, and handing over results.

A clear workflow helps everyone know who is working on what, where changes live, which version has been tested, and what next step the recipient needs to take. This lesson presents the collaboration workflow commonly used in development teams, from receiving a task to integrating and handing over the branch.

## 1. The Big Picture of a Task

A task typically goes through the following steps:

1. **Receive the task:** Read the requirements, clarify the expected outcome, scope, and completion criteria.
2. **Prepare:** Inspect the repository, remote, and working tree, and update the base branch.
3. **Create a branch:** Create a dedicated branch from the latest base commit to isolate changes.
4. **Implement:** Edit source code, run checks, and organize changes into meaningful commits.
5. **Sync:** Fetch new changes from the remote and integrate them into the task branch according to team convention.
6. **Share and review:** Push the branch, open a pull request or merge request, explain the changes, and address feedback.
7. **Integrate:** Merge the branch according to project policy after meeting review and check requirements.
8. **Hand over:** Provide status, commits, test results, remaining items, and essential information to the recipient.

~~~mermaid
flowchart TD
    A[Receive requirements and completion criteria] --> B[Inspect repository and update base branch]
    B --> C[Create task branch]
    C --> D[Edit code and run checks]
    D --> E[Review diff and create commit]
    E --> F[Fetch and sync new changes]
    F --> G[Push branch and open PR/MR]
    G --> H[Review, address feedback, and retest]
    H --> I{Integration conditions met?}
    I -- No --> D
    I -- Yes --> J[Merge per project policy]
    J --> K[Hand over and clean up branch]
~~~

Steps can repeat. For instance, if a reviewer requests additional changes, the author continues committing and pushing to the same branch; the pull request typically updates automatically with the new commits.

## 2. Receiving the Task and Agreeing on Scope

Before editing code, understand what needs to change. A ticket or task request should help answer:

- What is the current issue and who is affected?
- What is the expected behavior after completion?
- What is in scope and what does not need to be handled yet?
- Are there specific acceptance criteria or test cases?
- Are there dependencies on APIs, data, configuration, or someone else's work?
- Who will review and who has permission to integrate the changes?

For example, a request to "add a status filter to the order list" needs clarification on which statuses the filter includes, whether it combines with existing search, how to handle empty results, and how the UI should preserve the filter state.

If requirements remain ambiguous, discuss them with the requester before expanding scope based on assumptions. Important decisions can be recorded in the ticket or pull request so reviewers and handover recipients share the same context.

A sufficiently clear task usually has:

- Objective and expected outcomes.
- Expected scope of affected files or components.
- Verifiable acceptance criteria.
- Risks, dependencies, and people to coordinate with.

Branch names and commit messages should reflect the agreed-upon task. Avoid using one shared branch for multiple unrelated tickets, as it makes reviews, rollbacks, and root-cause investigation harder.

## 3. Preparing the Repository Before Branching

### 3.1. Checking the Repository and Remote

If you do not have a local repository yet, clone from the address provided by the team:

~~~
git clone https://example.com/team/store.git
cd store
~~~

If the repository is already on your machine, navigate into the project directory and check:

~~~
git rev-parse --show-toplevel
git remote -v
git status -sb
git branch -vv
~~~

These commands help verify:

- git rev-parse --show-toplevel shows the root directory of the repository.
- git remote -v shows the fetch and push URLs.
- git status -sb shows the current branch and working tree status.
- git branch -vv shows local branches and the upstreams they track.

If the remote points to the wrong project or the account lacks access permissions, resolve that before continuing. Do not push source code to an unverified remote.

### 3.2. Checking Existing Changes

Before switching branches or syncing, check the current state:

~~~
git status
git diff
git diff --cached
~~~

If there are work-in-progress changes, determine which task they belong to. You can commit when the changes form a meaningful unit, or stash when you need to temporarily set them aside to switch context:

~~~
git stash push -m "WIP: save local filter changes"
git stash list
~~~

After returning to the right branch, you can restore the stash:

~~~
git stash apply
~~~

git stash apply keeps the stash so you can verify it. Only after confirming the content has been safely restored should you consider deleting the stash with git stash drop. git stash pop both applies and removes the stash if successful, so understand the operation before using it.

Do not run git reset --hard or git clean -fd just to clean the working tree when you do not yet know what the existing changes are. These commands can cause loss of unsaved work.

### 3.3. Updating the Base Branch

Assuming the team uses main as the base branch and the local branch tracks origin/main:

~~~
git switch main
git fetch origin
git status -sb
git pull --ff-only
~~~

fetch updates information from the remote; pull --ff-only advances local main when a fast-forward is possible. If Git rejects it because histories have diverged, inspect the commits on both sides and follow the team's sync policy. Do not arbitrarily reset the base branch to force it to match the remote.

Some projects use develop, trunk, or a release branch as the base. Use the branch designated by the project rather than assuming every repository uses main.

## 4. Creating a Dedicated Branch for the Task

### 4.1. Why Work on a Separate Branch?

A branch isolates the changes for a single task. The author can commit multiple times, experiment, and receive reviews without directly altering the base branch. Multiple people can also develop different features in parallel.

Create a branch from the freshly updated base branch:

~~~
git switch -c feature/order-status-filter
~~~

Or use a branch name tied to the ticket ID:

~~~
git switch -c feature/ORD-142-status-filter
~~~

Branch names should be short, readable, free of spaces, and help others understand the purpose. Some common conventions:

| Prefix | Purpose | Example |
|---|---|---|
| feature/ | New feature | feature/order-filter |
| fix/ | Bug fix | fix/order-total-rounding |
| docs/ | Documentation | docs/deployment-guide |
| refactor/ | Refactoring | refactor/payment-service |
| chore/ | Maintenance work | chore/update-build-tool |

Prefixes are just conventions; prioritize the naming standard already used by the repository. A branch should serve a single objective that can be reviewed and integrated independently.

### 4.2. Confirming the Branch Before Making Edits

After creating the branch, verify:

~~~
git branch --show-current
git status -sb
git log --oneline --decorate -5
~~~

Ensure the current branch is the newly created task branch and that its starting point matches the base branch. If you accidentally branched from an outdated commit, you may need to update the branch before starting; do that before creating many separate commits.

## 5. Making Changes and Creating Commits

### 5.1. Making Changes in Small Units

While working, break changes down into parts that can be explained and verified. For example, adding an order filter might include:

1. Adding the status parameter to the query layer.
2. Adding status handling in the API.
3. Adding filter controls in the UI.
4. Adding tests for the statuses and empty-result cases.

Not every step necessarily has to be a separate commit. The goal is to keep the diff easy to understand and ensure each commit represents a complete, meaningful change. An overly large commit is hard to review; too many tiny commits like "fix", "try again", or "update" also make history hard to read.

### 5.2. Reviewing Changes Before Staging

The following commands help inspect the content:

~~~
git status
git diff
git diff --check
~~~

git diff --check detects certain whitespace issues such as trailing whitespace. Review modified files and avoid committing auto-generated files, logs, personal data, environment files, or changes outside the ticket scope.

### 5.3. Staging and Committing Purposefully

Stage the exact relevant files:

~~~
git add src/orders/order-query.ts
git add tests/orders/order-query.test.ts
git diff --cached
git status
~~~

If all changes in the working tree belong to the task and have been reviewed, you can use git add -A. Avoid running git add . out of habit without inspecting new or sensitive files first.

Create a commit with a message describing the outcome:

~~~
git commit -m "Add order status filter"
~~~

A good commit message helps others understand the change without immediately opening every file. You can use the structure:

~~~
<type>: <short description>

<reason or context if needed>
~~~

Example:

~~~
feat: add order status filter

Allow users to narrow the order list by its current status.
~~~

Types like feat, fix, docs, refactor, or test are common conventions, not mandatory Git requirements. Follow the project's conventions.

After committing, verify:

~~~
git status -sb
git log -1 --oneline
git show --stat --oneline HEAD
~~~

If the working tree still has changes, determine whether they are unfinished work or content accidentally left out. Do not assume a commit contains every change just because the commit command succeeded.

## 6. Syncing the Task Branch with New Changes

While you are working, teammates may update the base branch. If a task branch lives for a long time, sync periodically to catch conflicts early.

First fetch the latest data:

~~~
git fetch origin
git log --oneline --graph --decorate --all
~~~

Then choose the integration method according to team convention.

### 6.1. Merging the Base Branch into the Task Branch

~~~
git switch feature/order-status-filter
git merge origin/main
~~~

Merge creates a combining commit when histories on both sides have diverged. This approach preserves already-shared commits and clearly shows the integration point. It is usually suitable when the branch is used by multiple people or the team wants to avoid rewriting history.

### 6.2. Rebasing the Task Branch onto the Base Branch

~~~
git switch feature/order-status-filter
git rebase origin/main
~~~

Rebase replays the branch's own commits on top of a newer base, producing a linear history. Because replayed commits receive new identifiers, only rebase branches that you own or branches no one else has built upon, unless the team has agreed on a coordination plan.

There is no single merge or rebase choice that is right for every team. Follow the repository's policy and stay consistent within the same task branch.

## 7. Resolving Conflicts During Sync

Conflicts occur when Git cannot automatically combine changes. They usually happen when two branches modify the same region of content or one side deletes a file that the other side continues editing.

When a merge or rebase pauses due to a conflict, start with:

~~~
git status
~~~

Git will list the files that need attention. Inside a conflicted file, you may see:

~~~
<<<<<<< HEAD
const statusLabel = "Processing";
=======
const statusLabel = "In progress";
>>>>>>> origin/main
~~~

The markers <<<<<<<, =======, and >>>>>>> separate content from the two sides. Read the context, discuss with the author of the other change if the business intent is unclear, and edit to produce the final result. Do not simply pick one side just to clear the conflict markers.

After editing:

~~~
git diff
git add src/orders/status-label.ts
git status
~~~

If merging, complete with a commit as requested by Git:

~~~
git commit
~~~

If rebasing, continue:

~~~
git rebase --continue
~~~

If you realize you took the wrong direction or want to return to the state before the ongoing operation, you can cancel the process:

~~~
git merge --abort
~~~

or:

~~~
git rebase --abort
~~~

Only use the abort command when the corresponding operation is actively in progress. After completing, rerun relevant checks and inspect the diff to ensure conflict resolution did not drop logic from either side.

## 8. Pushing the Branch and Opening a Review Request

### 8.1. Pushing the Branch for the First Time

Once you have commits, share the branch to the remote:

~~~
git push -u origin feature/order-status-filter
~~~

The -u option sets the upstream for the local branch. Subsequent pushes can usually just use:

~~~
git push
~~~

If the push is rejected due to non-fast-forward, the remote may have new commits. Fetch, inspect history, integrate those changes via merge or rebase per team policy, and push again. Do not use git push --force as a default fix because it can overwrite others' commits.

### 8.2. Creating a Pull Request or Merge Request

On the Git hosting platform, create a pull request (PR) or merge request (MR) from the task branch into the target branch. The name depends on the platform; the purpose is to ask the team to review and integrate the changes.

A helpful PR/MR should provide:

- **Objective:** Ticket link and description of the problem solved.
- **Key changes:** Important behaviors, APIs, structures, or files modified.
- **How it was tested:** Tests run, commands used, and results.
- **Impact:** Schema, configuration, dependency, data, or compatibility changes.
- **Risks and limitations:** Unhandled edge cases or things reviewers should pay attention to.
- **Visuals:** For UI changes, attach screenshots or short videos when helpful.

Select reviewers based on code ownership and required domain knowledge. Avoid assigning reviewers without providing context on what needs attention.

### 8.3. Review Is a Collaborative Conversation

Reviewers typically look for:

- Do the changes meet the requirements without expanding scope?
- Is the logic correct for edge cases and error paths?
- Are there sufficient tests for the new behavior?
- Do naming, structure, and error handling follow conventions?
- Are any secrets, personal data, or internal information exposed?
- Do the changes affect performance, security, compatibility, or operations?

When receiving feedback, ask for clarification if a comment is not specific enough. If you agree, update the code, rerun checks, and commit. Push the new commit to the same branch so the PR/MR updates.

Do not silently alter an important business logic change without explanation. If you disagree with a suggestion, present your technical reasoning and align on an approach with the reviewer.

## 9. Integration Conditions and Completing the Task

Before merging, verify the conditions defined by the project. Typically these include:

- Reviews have been approved by the right people or required number of reviewers.
- CI ran successfully and mandatory checks passed.
- The branch has no remaining conflicts with the target branch.
- Important discussion threads have been resolved.
- Documentation, migrations, configuration, and release notes have been updated if needed.
- Authorized approvers have signed off when changes carry risk or affect production.

Platforms may support merge commit, squash merge, or rebase merge. Each produces a different history:

| Integration Method | Characteristics | Commonly Used When |
|---|---|---|
| Merge commit | Preserves branch commits and creates a merge commit | You want to record the milestone when the branch was integrated |
| Squash merge | Combines branch changes into a single commit on the target branch | You want a clean main branch history with each PR as one unit |
| Rebase merge | Replays branch commits onto the target branch and integrates linearly | The team requires linear history and individual commits already have high quality |

Choose the method specified by the repository. After merging, update the local base branch:

~~~
git switch main
git fetch origin
git pull --ff-only
~~~

If the team uses a different base branch, replace main with the corresponding branch name. Merged task branches can usually be deleted according to project policy:

~~~
git branch -d feature/order-status-filter
git fetch --prune origin
~~~

git branch -d only deletes the local branch when Git confirms the branch has been integrated. If the branch needs to be kept for investigation or follow-up work, follow team policy. Deleting the remote branch is typically done through the platform after merging or via an approved workflow.

## 10. Handing Over Work to Someone Else

Handover is not just sending a repository link. The recipient needs to know the current status and how to proceed without having to guess.

### 10.1. If the Work Is Complete and Merged

Document:

- Completed ticket or requirement.
- Associated PR/MR and commit or merge commit.
- Review and CI results.
- Configuration, migration, or operational changes to watch out for.
- Documentation or where usage guides live.
- Next steps still dependent on release or deployment.

Do not claim a change is running in production solely because the PR has been merged. Deployment status must be confirmed through the pipeline or operational system.

### 10.2. If the Work Is Still in Progress

Clearly hand over:

- Branch name and corresponding remote/upstream.
- Latest pushed commit and which parts remain incomplete.
- Files still modified in the working tree or staging area.
- Verification commands executed and their results.
- Steps to reproduce the issue, logs, or necessary screenshots.
- Agreed-upon decisions and open questions.
- Risks, dependencies, and recommended next steps.

If possible, commit parts that are in a consistent state with a message clearly indicating work in progress, then push the branch so the recipient can fetch it. If committing is not yet possible, explicitly note the uncommitted changes and hand them over via an agreed-upon safe method.

Before ending your session, you can run:

~~~
git status -sb
git log --oneline --decorate -5
git diff
git diff --cached
git branch -vv
~~~

These commands help create a concise status snapshot for the recipient. Never send credentials, tokens, .env files, or sensitive data in handover notes.

### 10.3. Handing Over Between Two People on the Same Branch

If two people take turns working on the same branch:

1. The current contributor pushes the latest commits to the remote.
2. Send the recipient the branch name, commit SHA, and task status.
3. The recipient fetches and checks out the branch:

~~~
git fetch origin
git switch --track origin/feature/order-status-filter
~~~

If the local branch already exists, switch to it and update from upstream instead of recreating it. Before editing, the recipient checks git status to ensure the working tree is clean or understands any leftover work-in-progress changes.

Avoid having two people push different commits to the same branch without communicating. If parallel work is needed, create separate branches for each part and integrate via PR/MR.

## 11. Collaboration Conventions That Reduce Conflicts

Git can combine many changes, but it cannot automatically resolve every disagreement in design or business logic. Teams can reduce coordination overhead with the following conventions:

- Focus each branch on one ticket or reviewable objective.
- Update the base branch before starting and sync periodically when work spans a long period.
- Commit in small, clear units and avoid mixing unrelated changes.
- Push regularly once commits are in a shareable state.
- Open a PR/MR early as a draft when implementation direction needs discussion.
- Keep diffs concise; separate broad refactors from functional changes when possible.
- Notify others before modifying files or APIs edited by many people.
- Do not rebase or force push shared branches without coordination.
- Enable base branch protection, required reviews, and CI proportional to project risk.
- Record decisions and test results so others can pick up the work.

Some conflicts can be reduced by dividing modules cleanly, avoiding having multiple people edit the same large file, and standardizing formatting or code generation. However, tools cannot replace communication when two changes have conflicting business semantics.

## 12. End-to-End Example from Task Intake to Handover

Suppose you receive ticket ORD-142: add a status filter to the order list. The team uses main as the base branch, PRs for review, and squash merge for integration.

**Step 1 — Update and create the branch**

~~~
git switch main
git fetch origin
git pull --ff-only
git switch -c feature/ORD-142-status-filter
~~~

**Step 2 — Edit code and inspect**

After updating the API, UI, and tests:

~~~
git status
git diff
git diff --check
~~~

**Step 3 — Stage and commit**

~~~
git add src/orders/order-query.ts
git add src/orders/order-list.tsx
git add tests/orders/order-query.test.ts
git diff --cached
git commit -m "feat: add order status filter"
~~~

**Step 4 — Share the branch**

~~~
git push -u origin feature/ORD-142-status-filter
~~~

Create a PR into main, link the ticket, describe the new behavior, list the tests run, and assign reviewers.

**Step 5 — Sync and address feedback**

If main has new changes, fetch and then merge or rebase per convention. Address review comments, rerun tests, and push additional commits. The PR/MR will update with the new content.

**Step 6 — Integrate and hand over**

Once reviews and CI pass, squash merge the PR. Update local main and record the PR, integration commit, and test results. If there are subsequent deployment steps, clearly state who is responsible and the pipeline status.

This workflow creates a traceability trail from requirement to branch, commits, review, and integration outcome. Others can inspect the history and understand why the change was made.

## 13. Pre-Completion Checklist

**Before starting**

- [ ] Understand the objective, scope, and acceptance criteria.
- [ ] Verify the correct repository, remote, and base branch.
- [ ] Check the working tree so ongoing changes are not overlooked.
- [ ] Update the base branch and create a dedicated branch for the task.

**During implementation**

- [ ] Break changes into easily reviewable units.
- [ ] Inspect the diff and stage the exact files needed.
- [ ] Write commit messages describing the actual content.
- [ ] Run appropriate tests and checks.
- [ ] Sync new changes according to team convention.
- [ ] Push the branch to share and back up your work.

**Before integration**

- [ ] PR/MR includes context, ticket link, and testing instructions.
- [ ] Review has been approved.
- [ ] CI and mandatory checks have passed.
- [ ] Conflicts have been resolved and retested.
- [ ] Select the repository's prescribed merge strategy.

**During handover**

- [ ] State the relevant branch, commits, and PR/MR.
- [ ] Record test results, unfinished items, and risks.
- [ ] Clearly state integration and deployment status.
- [ ] Instruct the recipient on how to fetch the branch or continue the work.
- [ ] Leave no local changes uncommunicated during handover.

## 14. Conclusion

An effective Git collaboration workflow starts with clear requirements, uses dedicated branches to isolate work, commits purposefully to preserve history, syncs deliberately to stay aligned with teammates, and uses PRs/MRs for review before integration. A thorough handover ensures the recipient knows where the code stands, what has been tested, and what the next step is.

Git provides the tools to manage history and exchange changes. Collaboration quality comes from how a team organizes work, agrees on conventions, communicates when conflicts arise, and documents enough context for others to continue.

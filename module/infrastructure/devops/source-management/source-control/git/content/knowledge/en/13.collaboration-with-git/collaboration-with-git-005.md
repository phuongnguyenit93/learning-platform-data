# Pull Requests and Merge Requests as the Platform Collaboration Layer

Git provides commits, branches, merges, and data exchange operations between repositories. When multiple people develop a project together, the team also needs a place to propose changes, inspect source code, hold discussions, run automated checks, and decide when changes enter the main branch. Git hosting platforms such as GitHub and GitLab provide this workflow through **Pull Requests (PR)** or **Merge Requests (MR)**.

A PR/MR is a platform collaboration feature built around Git branches and commits. A PR/MR typically describes changes from a source branch to a target branch, displays the diff, records review comments, CI results, and approval status. It helps teams make informed decisions before updating the target branch.

## 1. What Is a PR/MR and Why Is a Collaboration Layer Needed?

A Pull Request is a proposal to bring changes from one branch into another. GitHub calls it a **Pull Request**; GitLab calls it a **Merge Request**. Although the names differ, the shared goal is to create a workspace for reviewing and integrating changes.

For example, a project has a main branch `main`. A team member creates a `feature/payment` branch, implements payment functionality, and pushes that branch to the server. Instead of committing directly to `main`, the member opens a PR/MR with:

- **Source/head branch**: `feature/payment` — the branch containing the proposed changes.
- **Target/base branch**: `main` — the branch expected to receive the changes.

Authorized participants can read the description, inspect commits and diffs, leave comments, request modifications, approve, or reject integration. A CI pipeline can run to verify the source code. When project rules are satisfied, an authorized person merges the proposal.

A PR/MR is not a special commit type in Git, nor does it automatically replace the merge operation. It is a platform-managed object tied to the repository, source branch, target branch, review content, check runs, and processing status. The final integration action still updates Git history or refs according to the chosen merge strategy.

## 2. How Do PRs/MRs Work Across Branches?

The basic workflow typically follows this sequence:

~~~text
Branch main
    |
    +---- create branch feature/payment
                    |
                    +---- commit changes
                    |
                    +---- push branch to remote
                                  |
                                  +---- open PR/MR to main
                                               |
                                  diff + review + CI checks
                                               |
                                   eligible for integration
                                               |
                                          merge into main
~~~

A PR/MR compares the source branch against the target branch in their current states. When new commits are pushed to the source branch, the platform typically updates the comparison and associated checks. As a result, a PR/MR can span multiple review rounds: the author edits code, pushes new commits, and reviewers inspect again and continue the discussion.

Example branch preparation:

~~~bash
git switch main
git pull --ff-only

git switch -c feature/payment
# edit source code
git add .
git commit -m "Add payment processing"

git push -u origin feature/payment
~~~

After pushing, open the platform UI and create a PR/MR from `feature/payment` to `main`. The Git commands above prepare and publish the branch; creating the PR/MR is done via the platform's web interface, API, or integrated tooling.

When working in a fork model, the source branch may live in the author's fork repository while the target branch lives in the canonical repository. Within a single repository, both branches usually belong to the same remote. Platforms may display source and target repositories separately to prevent confusion.

## 3. Source/Head and Target/Base Branches

Choosing the right source branch and target branch is an essential step when opening a PR/MR.

| Component | Meaning | Example |
|---|---|---|
| Source branch / head | Holds the proposed commits | `feature/payment` |
| Target branch / base | Where changes will be integrated | `main` |
| Source repository | Repository containing the source branch | Author's fork or team repository |
| Target repository | Repository containing the target branch | Project's canonical repository |

A minor fix might be proposed into `main`, whereas a change preparing for the next release might need to target `release/2.x`. Picking the wrong target branch can cause the PR/MR to show too many unrelated changes or introduce code into the wrong development line.

Before creating one, confirm:

1. The source branch contains the exact commits intended for review.
2. The target branch is the branch the team wants to receive the changes.
3. Both source and target repositories are correct, especially when working across forks.
4. The diff includes only changes within the proposed scope.

If you accidentally select the wrong target branch, many platforms allow changing the target after creating the PR/MR. However, changing the target alters the displayed commit set and diff; you must reread the entire comparison.

## 4. Contents of a Good PR/MR

A PR/MR is documentation explaining changes so others can evaluate them. A good proposal usually contains:

- **Clear title**: describes the outcome or objective, for example `Add retry handling for payment requests`.
- **Context**: what problem is being solved, linking related issues or requirements if any.
- **Scope**: what changed and what is excluded from the proposal.
- **How to test**: test commands, manual scenarios, or verification results.
- **Visuals**: if changes affect the UI or user experience.
- **Risks and deployment notes**: migrations, configuration, feature flags, or dependencies requiring coordination, if applicable.

Example description:

~~~markdown
## Objective
Handle slow responses from the payment service with a bounded retry mechanism.

## Changes
- Added retries for transient errors.
- Capped retry attempts and backoff intervals.
- Added logging when retries are exhausted.

## Verification
- Ran unit tests for success and timeout scenarios.
- Tested behavior when the payment provider is unresponsive.

## Notes
Do not retry invalid input errors or authentication failures.
~~~

The description should help reviewers understand the rationale behind the changes, how to verify them, and what to watch out for. Avoid writing only "fix bug" or "update code" without further context.

Some repositories provide a PR/MR template to standardize structure. Use the project's template and fill in the relevant sections rather than deleting required items.

## 5. Reading the Diff and Commit List

Platforms typically display similar tabs or sections:

- **Conversation/Overview**: PR/MR description, discussions, status, and events.
- **Commits**: list of commits included in the proposal.
- **Files changed/Changes**: diff between the source branch and target branch.
- **Checks/Pipelines**: automated check results.
- **Reviewers/Approvals**: requested reviewers and approval status.

Tab names and layouts vary by platform, but the core content is similar.

When reading a diff, reviewers should examine both context and impact:

1. Do the changes properly solve the requirement?
2. Are edits within scope and free of unrelated changes?
3. Are there logic bugs, edge-case issues, security concerns, or performance impacts?
4. Do tests cover new behaviors and error scenarios?
5. Do documentation, configuration, migrations, or logs need updating?

Diffs are usually displayed file by file and hunk by hunk. Reviewers can leave comments directly on relevant lines. If the source branch receives new commits, the platform updates the diff; comments attached to modified lines may be marked as outdated or needing re-review.

Do not read only commit titles or the description. The diff itself shows the exact code that will enter the target branch.

## 6. Reviews, Comments, and Approvals

Review is the process of evaluating changes prior to integration. Depending on the platform and project configuration, reviewers can:

- Leave a general comment on the entire PR/MR.
- Leave a comment attached to a specific line or diff hunk.
- Bundle multiple review comments and submit them together.
- Approve the changes (Approve).
- Request changes (Request changes).
- Close the PR/MR or discuss adjustments to the implementation approach with the author.

A comment is a remark or question. It does not necessarily mean the PR/MR has been approved or blocked. Approval is a formal review state governed by platform and repository policy. Some projects require one or more approvals; others require approval from someone holding a specific role.

### Distinguishing Comment vs. Request Changes

| Action | Meaning |
|---|---|
| Comment | Asks questions, shares observations, or makes suggestions without necessarily changing approval state |
| Approve | Confirms the changes meet the reviewer's acceptance bar |
| Request changes | Requires the author to address issues before integration |
| Resolve conversation | Marks a discussion thread as handled; does not necessarily constitute approval |

The author should respond to comments by explaining or updating the code. When fixes are needed, commit and push to the exact source branch of the PR/MR. The platform updates the diff and check statuses according to configuration.

A resolved conversation does not automatically prove the code is correct. Reviewers still need to verify the updated edits. Similarly, an approval may be invalidated or require re-review when new commits are pushed, depending on platform rules and repository policy.

## 7. CI Checks and Pipeline Status

PRs/MRs are commonly connected to a CI system to automatically verify changes. When new commits arrive, a pipeline may run:

- Unit tests and integration tests.
- Lint and format checks.
- Application builds.
- Type checking or static analysis.
- Vulnerability, dependency, or secret scanning.
- Migration or deployment configuration validation.

The platform displays statuses such as passed, failed, running, or skipped. Exact labels vary by platform and CI integration.

| Status | Interpretation |
|---|---|
| Passed / Success | Check ran and met requirements |
| Failed | At least one check failed |
| Pending / Running | Check has not finished yet |
| Skipped / Neutral | Check did not run or does not apply per configuration |
| Required check missing | A mandatory check does not yet have a valid status |

If a required check fails, the platform can block merging. The author must inspect job logs, identify the cause, fix the code or configuration, and push a new commit. Do not assume an earlier passing pipeline suffices if the PR/MR has received new commits and checks must rerun.

A green check only indicates that the configured automated checks passed. It does not guarantee the software is bug-free; thorough reviews, appropriate tests, and domain understanding remain essential.

## 8. Draft PRs/MRs and Proposal Lifecycle

Not every pushed change is immediately ready for review. A Draft PR/MR (or an equivalent status such as Work in Progress) signals that the author is sharing progress without formally requesting a merge yet.

Drafts are useful when:

- Seeking early feedback on design direction.
- Wanting CI to run on an active development branch.
- Showing progress to the team or discussing architecture.
- Code is incomplete or tests are not yet finished.

When ready, the author transitions the PR/MR to Ready for review. Reviewers can then begin the formal review process per team rules.

Common lifecycle states:

~~~text
Open / Draft
     |
     +---- push commits and discuss
     |
Ready for review
     |
     +---- review + CI + revisions
     |
     +---- eligible -----------> Merged
     |
     +---- discontinued -------> Closed
~~~

Closed and Merged are two different outcomes. Closed means the proposal was closed; the changes may not have entered the target branch. Merged means the platform executed or recorded a successful integration.

If a PR/MR was closed by mistake or needs to continue, some platforms allow reopening it under the right conditions. If the source branch was deleted or permissions changed, restore or re-push the branch following project procedures.

## 9. Ways to Merge a PR/MR

Once a PR/MR meets requirements, the platform may offer multiple integration strategies. Exact button labels and options depend on the platform, repository configuration, and service version.

| Strategy | History Result | Commonly Used When |
|---|---|---|
| Merge commit | Creates a merge commit connecting source and target branch histories | You want to preserve branch structure and integration milestones |
| Squash and merge | Combines PR/MR changes into a single commit on the target branch | You want a clean main branch history, one commit per proposal |
| Rebase and merge | Places source branch commits onto the tip of the target branch without a standard merge commit | You want linear history while keeping individual commits |

### Merge Commit

A merge commit has two parents (in a standard merge), recording the unification of two lines of history. It preserves branching structure and makes it easy to identify when a branch was integrated.

### Squash and Merge

The platform creates a single new commit representing all changes in the PR/MR and adds that commit to the target branch. The original commits on the source branch still exist in the source branch history, while the target branch receives only the squashed commit. This strategy works well when the team wants a concise main history without keeping individual experimental commits.

### Rebase and Merge

The platform applies the source branch commits onto the latest history of the target branch, usually creating new commits with different hashes because their parents changed. The result is linear without a merge commit showing branch structure.

Before choosing, check project policy. If the team wants to trace a PR/MR as an integration unit, a merge commit may fit best. If a concise main history is desired, squash may fit. If you want to preserve individual commits while avoiding merge commits, rebase and merge is an option.

These strategies may be subject to additional rules such as fast-forward, linear history, or merge methods enabled/disabled by administrators. Not every PR/MR has all options available.

## 10. Branch Protection and Merge Rules

Repositories commonly protect critical branches such as `main`, `develop`, or release branches. Branch protection/rulesets allow administrators to enforce conditions before a branch can be updated.

Rules may include:

- Disallowing direct pushes or restricting who can push.
- Requiring a PR/MR before integration.
- Requiring a minimum number of approvals.
- Requiring reviews from specific teams or code owners.
- Requiring specific status checks to pass.
- Requiring all conversations to be resolved.
- Requiring the branch to be up to date with the target branch or go through a merge queue.
- Restricting force pushes and branch deletions.

For example, a team might mandate: every change to `main` must go through a PR/MR, have at least one approval from someone other than the author, pass CI, and have no unresolved review threads. In that case, the PR/MR creator cannot self-merge if conditions are unmet or they lack permission.

Names and configuration options for branch protection differ across GitHub, GitLab, and self-hosted platforms. Some policies are configured at the repository level, others at the organization or group level. Read project guidelines before attempting to bypass or troubleshoot a blocked merge.

## 11. Updating a PR/MR When the Target Branch Changes

While a PR/MR is open, the target branch may receive commits from others. This can cause the proposal to become out-of-date or develop conflicts.

One way to update the source branch is merging the target branch into the source branch:

~~~bash
git fetch origin
git switch feature/payment
git merge origin/main
# resolve conflicts if any
git push origin feature/payment
~~~

Another approach is rebasing the source branch onto the new target branch:

~~~bash
git fetch origin
git switch feature/payment
git rebase origin/main
# resolve conflicts if any
git push --force-with-lease origin feature/payment
~~~

Rebasing rewrites commits on the source branch, so pushing afterward may require a force update. Only do this when the branch is under your control and the team permits rewriting history. If multiple people are working on the source branch, coordinate before rebasing.

Some platforms provide an Update branch button or equivalent option. This button may create a merge commit or use a platform-configured update method. Check the platform's behavior before using it, especially if the team requires linear history.

## 12. Handling Conflicts in a PR/MR

Conflicts occur when changes on the source and target branches modify the same region of content in a way Git cannot automatically combine. The platform may report that the PR/MR has conflicts and block merging.

You can resolve conflicts locally:

~~~bash
git fetch origin
git switch feature/payment
git merge origin/main
~~~

If Git reports conflicts:

1. Run `git status` to see which files need resolution.
2. Open each file, read the conflict marker sections, and decide on the final content.
3. Remove conflict markers, keep the right code, and verify related changes.
4. Stage resolved files using `git add <file>`.
5. Complete the merge with `git commit` if Git prompts for a merge commit.
6. Run appropriate tests and push the source branch to the remote.

With rebase, after resolving and staging files, continue using `git rebase --continue`. If you need to abort an active rebase, run `git rebase --abort`. Never run a merge completion command during a rebase session.

After pushing, the PR/MR updates the diff and the platform may rerun CI. Resolving conflicts only means Git can combine the histories; it does not prove the conflict resolution is functionally correct. Run tests and review the combined code.

## 13. Roles of Author, Reviewer, and Maintainer

| Role | Primary Responsibilities |
|---|---|
| Author | Creates the proposal, documents context, keeps diffs scoped, responds to reviews, and updates the source branch |
| Reviewer | Reads diffs, evaluates logic, quality, security, and maintainability; provides comments or approvals |
| Maintainer | Upholds project processes, decides integration per policy, manages permissions and branch protections |
| CI/system | Runs automated checks and reports status back to the PR/MR |

In small teams, one person may wear multiple hats. However, rules such as requiring approval from someone other than the author provide an independent verification step.

Reviews should focus on behavior and risks of the change, not merely personal style preferences. If formatting or linting rules exist, automate them with tooling so review time stays focused on logic and design.

## 14. End-to-End Sample Collaboration Workflow

Suppose a team is developing a payment API on GitHub or GitLab.

**Step 1 — Sync the main branch and create a task branch**

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment
~~~

**Step 2 — Develop and create commits**

~~~bash
# edit source code
git status
git diff
git add src/
git commit -m "Add payment endpoint"
~~~

**Step 3 — Push the source branch**

~~~bash
git push -u origin feature/payment
~~~

**Step 4 — Open a PR/MR**

On the platform, choose the source repository, source branch `feature/payment`, target branch `main`, enter a title and description, and create the PR/MR. If the code is not ready yet, create it as a Draft.

**Step 5 — Run checks and review**

CI runs tests/build/lint per configuration. Reviewers inspect the commit list and diff, leaving comments or approvals. The author responds and updates code when needed.

**Step 6 — Update the source branch**

~~~bash
git add src/
git commit -m "Handle payment timeout"
git push
~~~

The PR/MR updates with the new commit. Required checks rerun and reviewers inspect the follow-up changes.

**Step 7 — Meet requirements and merge**

Once reviews, approvals, and checks satisfy project policy, an authorized person chooses a team-approved merge strategy. The platform updates the target branch and transitions the PR/MR to Merged.

**Step 8 — Clean up the branch**

After integration, the feature branch can usually be deleted on the remote via the platform UI or command:

~~~bash
git push origin --delete feature/payment
~~~

Then update your local branches:

~~~bash
git switch main
git pull --ff-only
git branch -d feature/payment
~~~

Delete a branch only when certain no further development is needed on it. Some platforms automatically delete the source branch after merging if the repository enables that option.

## 15. Common Errors and Misconceptions

| Situation | Cause or Correct Understanding |
|---|---|
| PR/MR opened but no changes appear | Wrong source/target selected, branch not pushed, or diff has no new commits |
| PR/MR displays too many files | Source branch may contain out-of-scope commits or wrong target branch selected |
| CI passed but cannot merge | Missing approval, unresolved conversations, branch protection, or insufficient permissions |
| Reviewer commented but status is still unapproved | Commenting and approving are two separate actions |
| Comment resolved yet changes are still requested | Resolving a thread only closes the discussion; code must still be fixed and accepted by the reviewer |
| PR/MR has conflicts | Source and target branches have changes that cannot auto-merge; update source branch and resolve conflicts |
| Pushed new commit but checks are still running | Pipeline needs time to finish; merging may be blocked by required checks |
| PR/MR is Closed | Proposal was closed; changes were not necessarily merged |
| Merged, yet commit hash differs | Squash or rebase creates new commits; this is expected behavior for those strategies |

When a merge is blocked, read the platform message to identify which condition is unmet. Avoid trying to bypass branch protection or required checks when they represent team policy.

## 16. Security When Collaborating via PR/MR

PRs/MRs can come from internal members or external contributors, particularly in projects using forks. Therefore, reviews must inspect both source code and how pipelines execute.

Key points to watch:

- Never put tokens, passwords, private keys, or sensitive information into commits, descriptions, or comments.
- Check which secrets a CI workflow can access when running on branches from forks.
- Never run untrusted scripts or binaries on machines holding critical credentials.
- Inspect new dependencies, install scripts, access permissions, and configuration edits.
- Verify whether migrations and schema changes affect existing data.
- For sensitive changes, require appropriate reviewers and apply repository approval rules.

Platforms maintain their own policies for fork pipelines, contributor permissions, and secrets. Maintainers should configure least-privilege permissions and understand what code executes in CI before enabling automation.

## 17. Key Points to Remember

- PR (GitHub) and MR (GitLab) are Git hosting platform collaboration features used to propose integrating changes between two branches.
- Source/head is the branch containing the changes; target/base is the branch receiving them.
- A PR/MR brings together description, commits, diff, discussions, reviews, approvals, and CI results.
- Comment, approve, request changes, and resolve conversation have distinct meanings.
- Draft indicates the proposal is not ready for formal review; Closed does not mean Merged.
- Merge commit, squash, and rebase produce different histories; choose according to team convention.
- Branch protection and required checks help ensure changes are reviewed and verified before entering critical branches.
- When the target branch changes, update the source branch via merge or rebase, then recheck the diff and CI.
- PRs/MRs support collaborative decision-making; ultimate quality still depends on responsible reviews, solid tests, and repository protection policies.

Treat a PR/MR as an inspectable, discussable proposal: the author explains the changes, reviewers evaluate them, the system runs checks, and an authorized person integrates once all project conditions are satisfied.

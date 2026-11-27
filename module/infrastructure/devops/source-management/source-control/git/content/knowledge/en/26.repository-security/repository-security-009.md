# The Role of Server Permissions and Branch Protection in Git Operations

## Why does Git need server permissions and branch protection?

Git is a distributed version control system. Each clone has its own repository, object database, branches, and history. You can create commits, create branches, merge, or rebase on your local machine without connecting to a server. Those operations modify only your local repository.

When you want to share commits with your team, you send changes to the remote using git push or through a Pull Request/Merge Request workflow. At that point, the server authenticates your identity, checks access permissions, and enforces repository or target-branch policies.

This creates two distinct layers of control:

- **Repository permissions:** determine who can read, write, or administer the repository.
- **Branch protection:** determines which conditions must be met when creating, updating, deleting, or merging into critical branches.

For example, a member with repository write permission may push to feature/payment yet still be blocked from pushing directly to main. That member can still commit and merge locally; the server only rejects updating main if the operation fails branch protection rules.

The Git client does not make the final decision on remote permissions. The Git server or hosting platform enforces permissions and final policies.

## Distinguishing authentication and authorization

These two concepts often appear together yet answer two different questions.

- **Authentication:** the server determines who you are.
- **Authorization:** once identity is known, the server determines which actions you are permitted to perform.

Common authentication methods:

- SSH keys.
- HTTPS combined with a credential manager or access token.
- User accounts and organizational SSO mechanisms.
- Service or bot identities in CI/CD.

After authentication, the server checks repository read or write permissions and the rules governing the target ref.

Examples:

~~~bash
git clone <repository-url>
git fetch origin
git push origin feature/payment
~~~

Clone and fetch typically require read access. Push requires appropriate write access. If a push is rejected, the cause may be missing repository write permissions, a protected target branch, commits failing rules, or the server rejecting the ref update.

A valid SSH key only proves the server recognizes the corresponding identity. It does not automatically grant write access to every repository or every branch.

### Repository permissions are typically role-based

Role names differ across GitHub, GitLab, Bitbucket, and self-hosted Git servers. A common model:

| General role | Typical permissions |
|---|---|
| Read | Clone, fetch, view code and history |
| Triage or equivalent | Read and handle items like issues; not necessarily allowed to push |
| Write/Developer | Push allowed branches, open Pull Requests/Merge Requests |
| Maintain/Maintainer | Manage selected settings, labels, branches, and repository workflows |
| Admin/Owner | Administer member permissions, policies, and protection settings |

This is a generalized model, not an exact permission table across every platform. A role with repository write permission can still be restricted on protected branches.

### Which operations do read and write permissions affect?

| Operation | Where it runs | Permissions typically required |
|---|---|---|
| git status, git log, git diff | Local | No server connection needed |
| git add, git commit | Local | No remote permissions needed |
| git branch, git switch, local git merge | Local | No remote permissions needed |
| git clone, git fetch | Remote | Read permission |
| git push | Remote | Write permission and permitted ref policy |
| Open Pull Request/Merge Request | Hosting platform | Repository access and request creation permission |
| Merge Pull Request into a protected branch | Platform or server | Merge permission and all branch protection checks |
| Modify branch protection/rulesets | Platform admin | Appropriate administrative permissions |

You can create commits successfully even if your account only has read access to the repository. Those commits exist in your local clone; the server enforces permissions when you try to share them.

## What does the server check when receiving a push?

When running git push, the Git client sends required objects and requests updating one or more refs on the remote. The server validates the request before updating any ref.

Example pushing a branch:

~~~bash
git push -u origin feature/payment
~~~

The server may check:

1. Identity has been authenticated.
2. Identity has write permission on the repository.
3. Target branch falls within allowed push scope.
4. Whether the update is a fast-forward per Git rules.
5. Whether the branch is governed by branch protection or a ruleset.
6. Whether required status checks, reviews, commit signatures, or other criteria have passed.
7. Whether policies prohibit force pushes, branch deletion, or tag updates.

If any mandatory condition fails, the server can reject the ref update and return an error message to the client.

A single push can update multiple refs. Accordingly, a server-side hook may validate each ref individually or reject the entire transaction depending on server mechanics and policy.

### Fast-forward checks and server permissions are separate checks

Git normally rejects non-fast-forward pushes to avoid losing existing history on the remote. This is a commit-ancestry check, not a member-permission check.

For example, remote main has a new commit that the local branch has not integrated yet:

~~~text
A---B---C  origin/main
     \
      D    local main
~~~

Pushing local main to origin/main may be rejected because the update is not fast-forward. You must fetch and integrate history per team workflow.

Even when an update is fast-forward, the server may still reject it because main is protected or the pusher lacks permission. Conversely, having write permission does not make a non-fast-forward push automatically safe.

## What is branch protection?

Branch protection is a policy placed on one or more branches to govern how they are updated. This feature is typically provided by the Git hosting platform; local Git itself has no universal branch protection mechanism enforced across servers.

Commonly protected branches:

- main or master.
- release/*.
- stable/*.
- Long-lived release branches.
- Branches used for production deployments.

The goal is to ensure critical branches only accept changes that have been reviewed, tested, and approved per workflow.

A policy for main may require:

- Updates only via Pull Request/Merge Request.
- At least one or two valid approvals.
- Required status checks must pass.
- No unresolved review conversations remaining.
- Force pushes prohibited.
- Branch deletion prohibited.
- Signed commits or linear history if adopted by the team.
- Only a specific team or role permitted to merge.

Names and configuration options vary by platform. Branch protection can also be expressed via rulesets applied by branch name, pattern, repository, or user group.

## A workflow when main is protected

Suppose main is the primary integration branch and the team prohibits direct pushes to it.

~~~text
Developer
    |
    v
Create feature/payment branch
    |
    v
Commit changes locally
    |
    v
Push feature/payment
    |
    v
Open Pull Request
    |
    +----> Review and approve
    |
    +----> CI runs status checks
    |
    +----> Resolve review comments
    |
    v
Meets branch protection requirements
    |
    v
Merge into main
    |
    v
Server updates main ref
~~~

Typical Git steps:

~~~bash
git switch -c feature/payment
# Edit and test source code
git add src/
git commit -m "feat(payment): add payment validation"

git push -u origin feature/payment
~~~

Then open a Pull Request/Merge Request on your team's platform. Reviewers inspect the changes, CI runs tests, and the server evaluates branch protection conditions.

Only when all conditions are satisfied and the user has merge permission does the platform update main using the configured merge method.

Successfully pushing to feature/payment does not mean you are allowed to push directly to main. Repository write permission and per-branch update permissions can differ.

## Common rules in branch protection

### Require a Pull Request/Merge Request

Policies can prohibit direct pushes to a protected branch and require every change to go through a merge request.

Benefits:

- Provides a centralized place for review and discussion.
- Records who approved the change.
- Associates CI and check results with commits.
- Can require updating the source branch before merging.
- Preserves a record of integration decisions.

If direct push is rejected, push a feature branch and open a Pull Request/Merge Request per workflow.

Not every platform uses the same name. GitHub commonly uses Pull Request, GitLab uses Merge Request; other systems have their own terms.

### Require review approvals

Branch protection can require a minimum number of approvals before merging. Some platforms support requiring reviewers from specific teams or CODEOWNERS of modified paths.

For example, changes inside a security directory may require code owner approval. Policies can also require fresh reviews after new commits or dismiss stale approvals when additional changes are pushed.

Read your platform's exact rules: approval count, who counts as a reviewer, how dismissed reviews behave, and bypass exceptions.

### Require status checks

A status check is a check result attached to a commit or branch, typically reported by CI and integrated apps.

Examples of required checks:

- Build.
- Unit tests.
- Integration tests.
- Lint and formatting.
- Security scans.
- License or dependency checks.
- Repository policy checks.

A status check is only meaningful when reported by a trusted source and configured accurately in branch protection. Duplicate check names coming from different sources can cause confusion depending on the platform.

If a required check is pending or failing, the server usually blocks merging. Open the CI logs, locate the failing job, and fix the root cause on the source branch.

### Require resolving review discussions

Some platforms allow requiring all review conversations or threads to be marked resolved before merging.

This ensures important feedback is not overlooked. Marking a thread resolved is only meaningful once the issue has been addressed or the reviewer agrees; do not close threads merely to turn the merge button green.

### Block force pushes

Force pushing can move a remote ref to a different history, leaving commits relied upon by others orphaned from that branch.

Critical branches usually block force pushes to preserve shared history. When rejected, fetch and integrate history following team workflow instead of trying to bypass protection.

Even the command:

~~~bash
git push --force-with-lease origin main
~~~

cannot bypass a server policy prohibiting force pushes. --force-with-lease is a client-side safeguard to reduce the risk of overwriting new commits you have not seen yet; it grants no extra permissions and does not replace branch protection.

### Block branch deletion

Default or release branches can be protected against deletion. This policy prevents losing critical refs due to accidental actions or compromised accounts.

For example, a remote branch delete command:

~~~bash
git push origin --delete main
~~~

can be rejected by the server if the branch is protected or the user lacks delete permissions. For completed feature branches, the platform may allow deletion after merging per policy.

### Require linear history or specific merge methods

Some teams require linear history for readability and traceability. Policies may disallow merge commits or permit only squash/rebase merges through the platform UI.

These options affect how commits enter the target branch:

- Merge commit preserves the merge commit and two-parent branch relationship.
- Squash merge combines the source branch's changes into one commit on the target branch.
- Rebase merge replays commits sequentially on top of the target branch, typically producing linear history.

Branch protection can restrict allowed merge methods. Use the merge method configured by your team rather than assuming local git merge behavior applies.

### Require signed commits

An organization can require commits with valid signatures to verify provenance and metadata integrity per policy.

Git supports signing commits with GPG or SSH depending on configuration. For example:

~~~bash
git config --global commit.gpgsign true
~~~

This setting tells Git to sign commits using the configured signing mechanism. Enabling the option does not create a key or guarantee the server accepts the signature. You must configure your key, public key, and identity per platform guidelines.

If commits fail verification per policy, status checks or branch rules can block merging.

## Distinguishing push permission and merge permission

Pushing and merging are distinct actions and can be assigned to different roles.

| Scenario | Meaning |
|---|---|
| Has push permission on feature branch | Can push commits to feature branch if rules permit |
| Lacks push permission on main | Server rejects direct updates to main |
| Has permission to open Pull Request | Can propose integrating changes |
| Has approve permission | Can approve under review rules |
| Has merge permission | Can perform the merge once all required criteria pass |
| Has admin permission | Can manage selected repository settings and branch rules |

Someone may be able to open a Pull Request without having merge permission. Someone else with merge permission completes it once reviews and CI pass.

On some platforms, the merge executes under the account of the person clicking the button; on others, a bot or service account updates the ref. Regardless of mechanism, branch protection policies are evaluated against the relevant configuration and permissions.

## Server-side hooks and server-level control in Git

Beyond platform branch protection, self-hosted Git servers can use server-side hooks to validate pushes.

Key hooks:

| Hook | Timing | Role |
|---|---|---|
| pre-receive | Before updating pushed refs | Inspects the full request and rejects the transaction on violation |
| update | Before updating each individual ref | Inspects each ref separately and can reject that ref |
| post-receive | After refs have been updated | Sends notifications, triggers CI, or runs post-processing tasks |

The pre-receive hook receives lines via stdin in the format:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

Each line describes one ref requested for update. The hook can check the target branch, new commits, commit messages, or internal policies. If the hook returns a nonzero exit code, the server rejects the corresponding receive transaction.

The update hook is usually invoked once per ref and receives the ref name along with old/new commit IDs as arguments. This hook can reject a specific ref.

The post-receive hook runs after refs are updated. It is suitable for sending notifications or triggering downstream jobs; returning an error code at this stage cannot undo the completed ref update.

Server-side hooks are installed and controlled by administrators on the server. Users cloning a repository cannot install a remote pre-receive hook simply by committing a file into the project.

### Server settings that reject unsafe updates

On self-hosted Git servers, administrators can use receive settings such as:

- receive.denyNonFastForwards: rejects non-fast-forward updates in configured scenarios.
- receive.denyDeletes: rejects ref deletion requests.
- receive.denyCurrentBranch: controls pushes to the currently checked-out branch in non-bare repositories.

These settings belong to server administration, not local config commands users run to grant themselves permissions. Actual behavior also depends on repository type and server setup.

Do not confuse server-side hooks with client-side hooks:

- pre-push runs on the user's machine before sending a push.
- pre-receive and update run on the server when receiving a push.
- Client-side hooks can be skipped or left uninstalled.
- Server-side hooks sit within server control and execute on every request passing through that receive path.

## Branch protection does not replace repository permissions

A protected branch does not mean everyone has read access to the repository. Read and write permissions are still enforced at the repository or organization level.

Similarly, repository write permission does not mean permission to update every branch. A developer may push personal feature branches while being blocked on main.

You can picture the evaluation order like this:

1. Authenticate identity.
2. Check repository access permissions.
3. Determine target ref and ref update permission.
4. Apply branch protection, rulesets, and server-side policies.
5. Check commit ancestry and mandatory conditions.
6. Accept or reject the update.

Implementation details vary by platform. Some checks execute in different layers or order, yet the principle holds that repository permissions and branch policies together determine whether an operation is accepted.

## Example policy for a team repository

Suppose a team has three branch categories:

- main: integration and release branch.
- release/*: version maintenance branches.
- feature/*: feature development branches.

A policy might be designed as follows:

| Rule | main | release/* | feature/* |
|---|---|---|---|
| Direct push | Blocked | Maintainer only | Allowed with write access |
| Pull/Merge Request | Required | Required | Not required |
| Review | 2 approvals | 1 approval | Per team convention |
| Required CI | Build, test, security | Build, regression | Basic CI |
| Force push | Blocked | Blocked | Per policy |
| Branch deletion | Blocked | Blocked while supported | Deletable after merge |
| Merge method | Squash or merge commit per convention | Merge commit per release workflow | Optional |

This is an example for discussion, not a universal default. Teams must choose rules based on branch criticality, test coverage, review capacity, and release process.

### Granting permissions by team rather than individuals

For long-term maintainability, grant permissions through teams or groups:

- Developer: push feature branches and open merge requests.
- Reviewer: review and approve within ownership scope.
- Release manager: merge or manage release branches.
- Repository administrator: modify branch protection and memberships.

Group-based permissions make onboarding and offboarding more consistent. When a member changes roles, administrators update group membership instead of editing dozens of individual permissions.

Apply least privilege: grant only permissions needed for the role. Limit the number of people allowed to bypass branch protection or alter rulesets.

## How to diagnose rejected pushes or merges

When encountering an error, first read the complete message from the server. Messages vary across platforms and languages.

### Inspect remote and current branch

~~~bash
git remote -v
git branch --show-current
git status -sb
git branch -vv
~~~

Confirm you are pushing to the intended remote and branch. If the remote URL is wrong, you may be sending commits to a different repository or using the wrong credential.

Check read access with fetch:

~~~bash
git fetch origin
~~~

A successful fetch indicates your identity can read the remote and access permitted refs. It does not prove write permission.

You can list visible remote branches:

~~~bash
git ls-remote --heads origin
~~~

Output depends on read permissions and server configuration; some refs may be hidden by policy.

### Categorizing error messages

| Message or symptom | Possible cause | Resolution |
|---|---|---|
| Authentication failed | Invalid credential or SSH key | Check account, key, and credential manager |
| Repository not found | Wrong URL or account lacks read access | Verify URL and access permissions |
| Permission denied | Missing write access or wrong authentication | Verify identity and repository role |
| Protected branch hook declined | Branch is protected or violates branch rule | Open a Pull Request/Merge Request and satisfy policy |
| Required status check is missing | CI has not run or required check has not reported | Check pipeline and check name |
| Review required | Insufficient approvals | Wait for valid reviews and address feedback |
| Non-fast-forward | Remote has commits local has not integrated | Fetch and merge/rebase per team convention |
| Force push prohibited | Server prohibits rewriting branch history | Follow the team-approved history update workflow |
| Cannot delete protected branch | Branch is protected against deletion | Keep the branch or ask an administrator per procedure |

Never use git push --force to fix arbitrary push errors. Force pushing does not fix authentication failures, missing permissions, or failing status checks; it can also destroy history if permitted by the server.

### Workflow when main is protected

If you committed on local main and the push is rejected due to branch protection, check policy and move the commits onto a feature branch to open a merge request.

You can create a branch from the current commit:

~~~bash
git switch -c feature/recover-main-work
git push -u origin feature/recover-main-work
~~~

Then open a Pull Request/Merge Request into main. If local main holds commits the remote has not accepted yet, the new branch preserves those commits for review. Inspect history and status before moving or resetting local main; never delete commits simply because direct push was rejected.

## Handling urgent updates

Some production incidents require urgent hotfixes. Branch protection processes should still be respected per organizational policy.

An emergency flow may include:

1. Create a hotfix branch from the appropriate release commit.
2. Implement a small, tightly scoped fix.
3. Run targeted tests.
4. Request expedited review from responsible owners.
5. Satisfy the defined minimum status checks.
6. Merge into the release branch and main per procedure.
7. Document the reason, approver, and post-incident verification steps.

If the organization has an incident bypass mechanism, only authorized people or roles should use it. Log the rationale and audit afterward. Never grant permanent bypass rights to all members merely to reduce wait times.

## Protecting tags and release branches

Tags are commonly used to mark release versions. A published tag may be referenced by deployment systems or external users.

Some platforms support protecting tags by pattern such as v* or release-*. Policies can restrict who can create, update, or delete tags.

Example creating and pushing a tag:

~~~bash
git tag -a v2.1.0 -m "Release v2.1.0"
git push origin v2.1.0
~~~

The server may reject the push if the user is not authorized to create tags matching a protected pattern. Never delete or move a shared release tag unless an approved release procedure permits it.

Annotated tags carry metadata and optional signatures depending on configuration. Tag protection keeps release milestones stable and limits unintended changes.

## What branch protection does not do

Branch protection is one layer controlling ref updates, not a complete security solution.

It does not automatically:

- Revoke clones or data already downloaded by members earlier.
- Prevent users with read access from copying source code.
- Detect every secret already residing in history.
- Replace dependency, malware, or vulnerability scanning.
- Protect exposed credentials.
- Replace backups and recovery plans.
- Guarantee CI is configured properly or that all tests are high quality.

If access must be revoked, administrators must update memberships, tokens, SSH keys, or SSO per procedure. If a credential is exposed, revoke or rotate it and assess impact; merely deleting the secret line in a new commit is not enough.

## Checklist for designing permissions and branch protection

- [ ] Clearly separate read, write, review, merge, and admin permissions.
- [ ] Grant permissions by group using least privilege.
- [ ] Protect the default branch and critical release branches.
- [ ] Specify which branches allow direct pushes.
- [ ] Require Pull Requests/Merge Requests where appropriate.
- [ ] Define required reviewer counts and ownership scope.
- [ ] Require status checks from trusted CI.
- [ ] Define rules for unresolved review conversations.
- [ ] Block force pushes and deletion of critical branches.
- [ ] Choose allowed merge methods and require signatures if needed.
- [ ] Restrict bypass permissions and log exceptions.
- [ ] Protect release tags by naming convention.
- [ ] Use server-side hooks or CI for centrally enforced policies.
- [ ] Audit access during onboarding, role changes, and offboarding.

## Checklist when operating Git on a repository with protected branches

- [ ] Confirmed remote and target branch.
- [ ] Fetched required remote state.
- [ ] Worked on an appropriate feature or hotfix branch.
- [ ] Committed and pushed the source branch.
- [ ] Opened a Pull Request/Merge Request if required by policy.
- [ ] Obtained required reviews and status checks.
- [ ] Resolved required review comments.
- [ ] Used an allowed merge method.
- [ ] Verified results after merging.
- [ ] Avoided force pushing or bypassing outside approved procedures.

## Takeaways

Git lets you create commits and manipulate history in your local repository, yet the server decides who can read, push, merge, or administer the repository. Branch protection adds rules to critical branches such as main and release: requiring reviews, status checks, blocking direct pushes, force pushes, or branch deletion. Repository write permission does not equate to permission to update every branch. When a push is rejected, distinguish authentication failures, repository permissions, branch policy, and non-fast-forward rejections; then follow the Pull Request/Merge Request workflow and satisfy server criteria. Client-side hooks provide early feedback, while CI, branch protection, and server-side hooks are where policies are enforced centrally.

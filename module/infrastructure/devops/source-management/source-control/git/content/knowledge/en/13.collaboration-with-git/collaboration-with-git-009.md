# The Boundary Between Git Commands, Branch Policies, and Team Branching Strategies

When multiple people collaborate on a repository, the team usually agrees on branch naming conventions, pre-integration review rules, testing requirements, and how changes enter the main branch. These rules are often grouped together as a collaboration workflow or branch policy. However, not every rule is enforced by Git itself.

Git provides the operations and structures to create branches, commit, merge, rebase, fetch, and push. A branching strategy is how the team organizes the use of those operations. Branch protection policies and integration permissions are typically configured on a Git server or collaboration platform such as GitHub, GitLab, or Bitbucket. Understanding the boundary between these three layers helps a team know which rules are merely agreements, which are checked by tools, and where to configure controls when preventing unwanted actions.

## 1. Three Layers to Distinguish

| Layer | Who or What Decides? | Examples | Role |
|---|---|---|---|
| Git commands and data model | Git client and repository | `git branch`, `git commit`, `git merge`, `git rebase`, `git push` | Operates on commits, refs, and repository content |
| Branching strategy | Chosen by the development team | Trunk-based development, GitHub Flow, Git Flow | Organizes branches and integration flows around how the team works |
| Branch policies and integration permissions | Repository administrators, Git server, or hosting platform | Mandatory pull requests, required passing CI, blocking force-pushes to `main` | Controls who can update which branches and the conditions for accepting changes |

The three layers are related, yet do not replace one another. For instance, Git lets users create a branch named `feature/payment`; team convention may require all features to use the `feature/` prefix; and the server may reject a push if the user lacks permissions or the target branch is protected.

## 2. What Does Git Provide?

Git is a distributed version control system. It manages content and history through objects, commits, and references such as branches and tags. Core operations include:

- `git branch` creates, lists, renames, or deletes local branches.
- `git switch` switches the working tree to another branch or commit.
- `git commit` records staged content as a commit in the local repository.
- `git merge` integrates history from another branch into the current branch.
- `git rebase` replays commits onto a new base, creating new commits with new identifiers.
- `git fetch` downloads objects and updates remote-tracking refs per fetch configuration.
- `git push` asks a remote to accept objects and update refs per refspec, if the server allows it.

For example, Git does not force branch names to follow a specific pattern. You can create a branch with:

```bash
git switch -c feature/payment
```

The name `feature/payment` is a naming choice made by the user. Git treats it as a branch ref; it does not automatically infer whether that branch is a feature, bugfix, or release.

Similarly, `git merge` does not inherently require a pull request or reviewer. If you have direct write access to a remote branch and the server imposes no restrictions, a user can push changes via Git's technical workflow. Review requirements must be configured as policies at the receiving end or practiced by the team through a collaboration process.

## 3. Branching Strategy Is a Work Organization Convention

A *branching strategy* describes how a team creates, maintains, and integrates branches. Git does not impose a single strategy; teams choose based on size, release cadence, required stability, and how software is deployed.

### 3.1. Trunk-Based Development

The team centers development around a single main branch (*trunk*), typically `main`. Members integrate small changes frequently; feature branches, if used, are short-lived. CI and techniques such as feature flags help safely land changes into the trunk.

```text
main:       A---B---C---D---E
                 \     /
feature:          F---G
```

The goal is to minimize how long branches diverge from the main branch and catch integration issues early. This model requires solid automated testing and disciplined frequent integration.

### 3.2. GitHub Flow

A simple workflow that uses one deployable main branch and short-lived branches for each change. Members create a branch, push to the remote, open a pull request, review, and integrate once repository conditions are met.

```text
main:          A---B-----------M
                    \         /
feature/profile:     C---D---E
```

GitHub Flow is a popular workflow convention, not a special mode toggled inside Git. Pull requests are a feature of the hosting platform; the Git client provides branch, commit, push, and merge/rebase to execute the corresponding steps.

### 3.3. Git Flow

Git Flow uses branches with relatively distinct roles, typically `main` for release history, `develop` for development integration, alongside short-lived branches such as `feature/*`, `release/*`, and `hotfix/*`.

```text
main:       A-------------------R---------H
             \                 /         /
develop:      B---C---D---E----/---------/
                    \       /
feature:             F-----G
```

This model can suit products released in versioned cycles that need dedicated release preparation branches. In exchange, the team must manage more long-lived branches and handle syncing across role branches. Git Flow is also a branch organization convention; Git does not automatically create or protect those branches unless the team configures supporting tools or workflows.

No strategy suits every team. What matters is choosing a clear approach, documenting the rules, and ensuring tools enforce the necessary conditions.

## 4. Where Are Branch Policies Enforced?

A branch policy (or branch protection rule) consists of conditions controlling updates to a branch, especially critical branches like `main` or `release/*`.

Common requirements include:

- Only specific groups or roles may push directly.
- Changes must go through a pull request or merge request.
- At least one or more reviewer approvals are required.
- Required CI checks must pass before merging.
- Force-pushing or deleting protected branches is disallowed.
- Conversations must be resolved before integration.
- Restricting who can create, update, or delete branches matching a pattern.

Platforms like GitHub, GitLab, and Bitbucket provide corresponding configurations, with names and scopes varying by product, version, and service tier. On a self-hosted Git server, administrators can use access controls and server-side hooks to inspect or reject ref updates.

Examples of the difference:

| Rule | Documented Only in Team Docs | Enforceable by Tooling |
|---|---|---|
| Name branches `feature/*` | Members comply manually | Server or platform can validate patterns on branch create/push |
| Every change needs a reviewer | Reviewers remember to do it | Mandatory pull requests and minimum approval counts |
| Tests must pass | Members run tests manually | Required status checks or mandatory pipelines |
| No direct pushes to `main` | Members avoid it manually | Branch protection, write permissions, or server-side hooks |
| Commit messages follow convention | Members write them properly | Hooks or commit-message validation workflows |

A line in a README only communicates a rule; by itself, it does not block a push command. If a requirement must apply consistently to everyone, configure enforcement at the receiving endpoint and verify access permissions.

## 5. Local Hooks vs. Server-Side Hooks

Git supports hooks to execute scripts at specific points in an operation's lifecycle.

### Client-Side Hooks

Client-side hooks run on the user's machine, for example:

- `pre-commit`: runs before creating a commit.
- `commit-msg`: validates the commit message.
- `pre-push`: runs before pushing.

Teams can use them to run formatters, linters, fast tests, or commit convention checks. However, client-side hooks live in each user's local environment; if not installed or configured properly, they do not form a reliable enforcement boundary for a shared repository. Some hooks can also be bypassed using flags like `--no-verify` on operations supporting that option.

### Server-Side Hooks

On self-hosted Git servers, hooks such as `pre-receive`, `update`, and `post-receive` run on the server receiving pushes. A `pre-receive` or `update` hook can reject a ref update when policy conditions are unmet. A user pushing from a personal machine cannot disable a server-side hook simply by adding flags to a local command.

Code hosting platforms typically provide branch protection, rulesets, merge checks, or pipelines instead of requiring users to write server hooks themselves. Whichever mechanism is used, critical conditions must be verified on the side authorized to accept or reject updates.

## 6. Merge Strategy Is Also a Process Decision

When a pull request is approved, the team must agree on how commits enter the target branch. Platforms commonly offer several options:

| Integration Method | History Result | When It May Fit |
|---|---|---|
| Merge commit | Creates a merge commit, preserving branch relationships and both histories | When you want to clearly preserve integration points and branch history |
| Squash merge | Combines branch changes into a single commit on the target branch | When you want a concise main branch history per change |
| Rebase and merge | Replays branch commits onto the new base and integrates | When you want linear history and the team accepts recreated commits |

Git provides the `merge` and `rebase` commands; the pull request interface and how a team selects squash or rebase merge are typically governed by the platform and repository policy. A UI squash merge is not strictly identical to `git merge --squash` in every workflow detail, because the platform also manages the resulting commit and pull request state.

The team should agree on the integration method so developers understand how history will be recorded, especially when a branch is shared or multiple people work on it.

## 7. Example: Turning Conventions into Controllable Workflows

Suppose a team chooses these rules:

1. All features are developed on `feature/<feature-name>` branches.
2. The `main` branch does not accept direct pushes from developers.
3. All changes into `main` must go through a pull request.
4. Pull requests require at least one approval, and mandatory CI checks must pass.
5. Integration uses a merge commit to preserve merge points in history.

A developer might work in Git as follows:

```bash
# Update information from remote.
git switch main
git pull --ff-only

# Create a feature branch.
git switch -c feature/user-profile

# Make changes and create a commit.
git add src/profile/UserProfileService.java
git commit -m "feat: add user profile service"

# Push branch to remote.
git push -u origin feature/user-profile
```

Next, the developer opens a pull request on the hosting platform. The platform checks reviewers and CI according to branch protection. Once conditions are met, an authorized person merges the pull request using the team's agreed method.

The commands above create a branch, commit, and push; they do not automatically create a pull request, require approval, or trigger CI. Those conditions must be configured on the hosting platform or in team workflows.

## 8. How to Tell If a Rule Is Enforced or Merely an Agreement

When handed a collaboration workflow, ask yourself:

1. **Which operation does the rule target?** For example, creating a branch, committing, pushing, or merging.
2. **Who checks the rule?** Git client, local hook, Git server, hosting platform, or team members?
3. **What happens if it is violated?** Is an error returned and the action rejected, or is there only documentation expecting users to comply?
4. **Does the rule apply to everyone with write access?** If not, review permissions or protection scope.
5. **Where can the configuration be verified?** For example, branch rulesets, protected branches, required checks, repository permissions, or server hooks.

A rule is only considered enforced when the control mechanism is actually enabled and covers the exact branches, users, and operation types needing protection. Writing a rule in documentation or adding a local hook on some machines is not enough to conclude all pushes are controlled.

## 9. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Git automatically enforces Git Flow | Git only provides operations and branch structures; Git Flow is a team-chosen strategy |
| Naming a branch `main` makes it automatically protected | A branch name does not grant permissions or protection policies |
| `git merge` always requires a pull request | Pull requests are a collaboration platform workflow; Git can merge directly if repository and permissions allow |
| Having a guideline file prevents bad pushes | Documentation communicates rules; branch protection, permissions, or server-side hooks are needed for enforcement |
| A pre-commit hook guarantees every commit is checked | Local hooks may be uninstalled or bypassed; mandatory checks should be enforced on the server/CI as appropriate |
| Upstream automatically determines who can push | Upstream defines tracking relationships; write permissions and push policies are managed by the remote/server |
| Choosing rebase enables a branching strategy | Rebase is an operation that replays commits onto a new base; a branching strategy is the broader convention for how the team uses branches |

## 10. Key Takeaways

Git provides the technical foundation for storing history and coordinating changes. Teams choose a branching strategy to organize work. Administrators configure policies on the Git server or hosting platform to control permitted operations.

When designing a collaboration workflow, clearly define which branches serve which purposes, how changes are reviewed and integrated, and which mechanism enforces each condition. This clear separation helps team members know which Git commands to run, while administrators know where to configure permissions, hooks, or branch protections.

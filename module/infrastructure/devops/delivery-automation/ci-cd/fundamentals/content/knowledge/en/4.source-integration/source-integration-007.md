# Keeping the Main Branch Healthy and Standardizing Broken-Build Remediation

The main branch (`main`, or an equivalent default branch name) is where development work converges. Every change integrated into this branch can become the baseline for the next pull request, the next artifact build, and testing or release environments. Therefore, teams must keep the main branch in a state that compiles and passes required checks.

A healthy main branch lets a team quickly answer three questions: can current code integrate, did a new change break anything, and can the team continue building on a shared baseline? Achieving this requires combining sound Git practices, branch protection policies, fast-feedback pipelines, and an agreed process when builds fail.

Within CI/CD, **keeping the main branch healthy** means every revision accepted into main passes agreed quality checks, has results tied to a specific commit, and never leaves unresolved failures lingering. This does not automatically prove the application is ready for production; further testing, security, approval, and release verification gates may still be needed downstream.

## 1. What Does a Healthy Main Branch Mean?

A healthy main branch is one the team can rely on as a shared foundation for development and integration. That state should be defined by observable criteria rather than a gut feeling that "everything seems fine."

A baseline set of criteria typically includes:

- Source code can be checked out and built using documented procedures.
- Required checks such as compilation, unit tests, and critical integration tests pass on the current revision.
- Pipelines trigger properly, complete within reasonable times, and report statuses bound to commit SHAs.
- Necessary artifacts can be built and identified by the built revision.
- Incomplete changes can be integrated without exposing unready behavior to users.
- When a required check fails, the team has clear ownership and recovery procedures.

"Always green" does not mean failures never happen. Failures still occur from regressions, dependencies, runners, registries, or test services. What matters is catching failures at the right gate, never ignoring them, and resolving them quickly enough for the main branch to return to a trustworthy state.

Teams must also agree on what green means. For example, if only compile and unit tests run on pull requests, a green status proves only those checks. It does not prove database migrations, external service integrations, or post-deployment behavior work correctly. Each gate's name and scope must accurately reflect the evidence it provides.

## 2. Why Integrate Frequently?

When a feature branch lives for a long time, it diverges from the main branch. Meanwhile, teammates may change APIs, update dependencies, alter data schemas, or modify pipelines. By merge time, the team must resolve numerous conflicts and may uncover bugs that only emerge when changes combine.

Frequent integration shrinks each change's size and shortens the distance between cause and effect. When a small commit breaks a build, the investigation scope is far narrower than a merge containing weeks of changes.

### Keep Working Branches Short-Lived

A common approach is trunk-based development: feature branches are short-lived, changes are split into small pieces, and integration into the main branch happens frequently. Teams can still use pull requests for review, provided pull requests stay small enough for peers to understand, test, and give rapid feedback.

The workflow can look like this:

1. Branch off the latest revision of the main branch.
2. Implement one clearly scoped change, avoiding bundling unrelated tasks in the same pull request.
3. Run relevant checks locally and open a pull request.
4. The pipeline verifies the pull request's revision; reviewers evaluate both code and integration impact.
5. Once required conditions pass, merge the change into the main branch.
6. The main branch pipeline verifies the post-merge revision and produces artifacts if configured.

Teams do not need to merge half-baked commits straight into the main branch. Instead, split a large feature into small increments while keeping new behavior disabled until complete.

### Use Feature Flags to Integrate Unactivated Code

Feature flags allow new code to be integrated and deployed while new behavior stays off for users. This helps when a feature spans multiple pull requests or multiple teams.

Simple Java example:

```java
public OrderView getOrder(String orderId) {
    Order order = orderRepository.findById(orderId);

    if (featureFlags.isEnabled("new-order-summary")) {
        return newOrderSummaryMapper.toView(order);
    }

    return legacyOrderSummaryMapper.toView(order);
}
```

The main branch can hold both the new mapper and the control flag while users still receive legacy behavior until the team enables the feature. Flags need an owner, purpose, and removal plan. Flags lingering too long multiply conditional paths to test, obscure application behavior, and can create untested configuration combinations.

Feature flags do not replace testing. Even when a behavioral branch is off, the code must still compile and relevant paths must be tested appropriately. For schema or API changes, design backward compatibility so old and new versions can coexist during transition.

## 3. Setting Rules to Protect the Main Branch

Branch protection policies turn team expectations into enforceable conditions. If a doc merely says "please run tests before merging," outcomes depend on whether everyone remembers and complies fully.

Common rules include:

| Rule | Purpose | Implementation Notes |
|---|---|---|
| Require pull requests | All changes go through review and checks | Restrict direct push permissions to the main branch |
| Required status checks | Allow merge only when mandatory jobs pass | Select the exact check names and emitting workflows |
| Required reviews | Ensure peer review of changes | Configure reviewer count or groups by risk level |
| Resolve review conversations | Prevent unaddressed comments from being overlooked | Allow merge only after necessary discussions resolve |
| Require up-to-date base | Verify changes against the latest codebase | Consider merge queues when multiple PRs contend |
| Restrict admin and bypass rights | Preserve gate integrity | Exceptions require accountable owners and audit logs |

Not every project needs every rule enabled. Choose based on risk level, team size, and maintainability. Still, checks determining buildability and integration quality must be clearly defined, owned, and applied consistently.

### Required Status Checks Must Represent Real Verifications

A status check is only useful when it reflects a concrete condition and runs on the exact revision to be merged. If a workflow is skipped due to misconfigured triggers, the check may hang indefinitely or fail to provide the evidence the team assumes it has.

When configuring, verify:

- Does the workflow run on pull requests from the branches and change types requiring protection?
- Are check names stable and free of collisions across jobs?
- Are results bound to the corresponding head SHA or merge candidate?
- Does the job properly fail when verification commands return errors?
- Are any steps using `continue-on-error` or skip conditions that mask failures?

If a check is no longer appropriate, update policy and workflow together. Never delete a required check merely to clear a pending state without understanding the cause.

### Merge Queues for Concurrent Changes

In repositories with heavy pull request traffic, two changes may each be green individually yet incompatible when combined. A merge queue builds integration candidates sequentially and re-runs checks on the combined state before landing changes on the target branch.

Merge queues help when the main branch receives frequent pull requests or when check runtimes are long enough that multiple pull requests base themselves on the same stale state. Queues add some wait time, yet cut the risk of two independent changes passing alone and breaking main when merged closely together.

For queues to work properly, workflows must support the events and revisions the platform uses for merge groups or merge trains. If a workflow triggers only on `pull_request` and `push` without supporting the queue event, the queue may never receive required checks.

## 4. Maintaining Integration Quality Without Slowing the Team Down

A healthy main branch depends on CI feedback quality. If changes wait too long, teams look for ways to skip checks or merge massive batches at once. If checks are unstable, developers lose trust in green and red signals.

### Tier Verification

Organize checks by duration and risk level:

- Syntax, formatting, linting, and compilation normally run early.
- Unit tests run on every pull request and on the main branch.
- Critical integration tests run before merge or on merge candidates.
- Time-consuming suites such as performance, load, or cross-platform tests can run on schedule or before an appropriate release gate.

Tiering must be agreed upon with both product and engineering teams. A check should move off the merge gate only after assessing risk and establishing compensating controls. Never push critical checks post-merge merely to shorten the pull request queue.

### Optimize CI Runtime

Common ways to shorten feedback loops include caching dependencies, running impacted jobs conditionally for matching changes, splitting tests into independent shards, and running in parallel on adequately provisioned runners. Measure runner queue time, setup time, and execution time separately to see what slows the pipeline down.

Caches must be keyed by OS, runtime version, lockfile, or other factors affecting dependencies. Poorly keyed caches can feed stale files into builds and create hard-to-reproduce bugs. When builds rely on caches, teams still need a clean-build path for diagnosis.

### Unstable Tests

A flaky test passes or fails intermittently despite unchanged source code and inputs. Common causes include shared state, execution order dependencies, race conditions, timing, networking, or external services.

When flaky tests occur:

1. Record the test, revision, environment, and logs from both passing and failing runs.
2. Reproduce repeatedly under controlled conditions.
3. Separate test bugs, application bugs, and environment issues.
4. Fix the test to isolate data, control time, or remove unnecessary dependencies.
5. Re-run an appropriate number of times and restore the test to the required gate if it was quarantined.

Bounded retries can mitigate transient infrastructure hiccups, provided the final record preserves evidence of the failure. Never use infinite retries or automatic test skipping to fabricate a green signal that misrepresents real quality.

## 5. Standardizing the Response When the Main Branch Build Fails

When a main branch build fails, the whole team must respond via a single agreed process. A standard playbook cuts debate time, prevents multiple people from stepping on each other's fixes, and preserves diagnostic evidence.

### Response Principles

- **A pipeline-blocking failure needs one coordinating owner.** Others can assist, but everyone must know who leads recovery.
- **Pause risky new changes onto the broken branch.** Keep pauses scoped to the affected repository or stream; independent work can proceed if it does not complicate recovery.
- **Fix the root cause or revert the offending change.** Never turn a pipeline green by deleting tests or bypassing required gates.
- **Re-verify on the new revision.** A green run on an older commit does not prove a fix commit is safe.
- **Communicate status clearly.** Everyone needs to know the issue is being handled, who owns it, and when the next update arrives.

### Five-Step Remediation Process

#### Step 1: Announce the Red Build and Scope Impact

When the main branch pipeline fails, the discoverer immediately posts to the team's channel or incident tracker. Initial info should include links to the workflow run, branch, commit SHA, failing job, and discovery time.

Determine whether the failure truly affects the main branch or only an isolated pull request. Check which job failed first, which jobs were merely skipped due to dependencies, and whether multiple runs report the same error.

#### Step 2: Assign an Owner and Restrict New Merges

The coordinator may be the author of the offending commit, the build duty engineer, or a repository maintainer per team convention. If the cause is unclear, the build duty engineer coordinates evidence gathering and pulls in the right domain team.

While mainline is red, restrict non-urgent merges. If an urgent change is required to resolve a production incident, evaluate it separately and document the decision. Avoid letting unrelated commits pile onto the branch, as they multiply hypotheses to investigate.

#### Step 3: Locate the First Failure and Reproduce

Open the logs of the first failing job, find the command returning a non-zero exit code, and read the preceding output. Compare the failing revision against the last green run to narrow down changes. Check dependencies, configuration, secrets, runners, and test services if signs point outside application code.

For a Gradle project, start with commands like these in an appropriate working tree:

```bash
# Check current status and recent commits
git status --short
git log --oneline -n 10

# Re-run primary checks
./gradlew --no-daemon clean check

# Run a specific module's tests once identified
./gradlew :order-service:test
```

Adjust task and module names to your project. `clean` clears stale build outputs, though it cannot replicate every difference in runners, environment variables, or external services. If a failure occurs only in CI, compare JDK versions, Gradle versions, OS, config variables, and dependencies between CI and local workstations.

#### Step 4: Fix Forward or Revert

Choose recovery based on root-cause certainty and turnaround time:

| Situation | Typical Appropriate Action |
|---|---|
| A recently merged commit clearly caused the failure and the fix takes time | Revert the offending commit to restore mainline, then fix on a separate branch |
| Cause is clear and fix is small and fully testable | Open an urgent fix PR, focus-review it, and run required gates |
| Runner, registry, or test service outage | Restore the service or configuration, then re-run on the exact revision |
| Flaky test turned the pipeline red | Confirm flakiness, fix the test, or quarantine with strict time bounds |
| Multiple commits could be at fault and cause is unknown | Freeze new merges, investigate by revision, and use tools like `git bisect` as needed |

`git revert` creates a new commit reversing an existing historical change, suitable for shared branches. Never arbitrarily rewrite main branch history via reset or force push, as that can discard commits and diverge teammates' histories. Special history interventions must follow repository governance rules.

#### Step 5: Verify, Reopen Integration, and Document

After fixing or reverting, re-run all required status checks on the new revision. Confirm builds, tests, artifacts, and dependent jobs complete. If merges were paused, the coordinator announces when the main branch is green again and integration can resume.

Document the root cause, detection method, impact duration, recovery action, and preventive measures. If resolved via a workaround, file a follow-up ticket to complete the proper fix and restore any temporarily relaxed checks.

## 6. Defining Roles to Avoid Overlapping Work

In small teams, one person may wear several hats. Even so, responsibilities must be clear so everyone knows who coordinates and who clears the path to resume integration.

| Role | Primary Responsibilities |
|---|---|
| Change author | Provide context, related commits, reproduction steps, and help fix issues caused by their change |
| Build duty or coordinator | Spot red builds, announce status, assign owners, track recovery time, and confirm green restoration |
| Reviewer | Inspect urgent fixes, assess risks, and verify changes do not weaken quality gates |
| Service or platform owner | Investigate shared runners, registries, dependencies, environments, and integration services |
| Repository maintainer | Maintain branch protection, required checks, and exception permissions |

Some teams rotate a **build sheriff** or **build cop** role daily or weekly. The duty engineer does not have to fix every bug personally; their main job is ensuring every failure has an owner, visibility, and follow-through to closure. Rotation spreads pipeline knowledge and avoids single-person bottlenecks.

## 7. Broken-Build Notification Templates

Incident notices should be concise, actionable, and updated as status evolves. Channel template:

```text
[MAIN BUILD BROKEN]
Repository: <repository>
Branch: main
Commit: <commit-sha>
Workflow run: <link>
Failing job/step: <job-and-step>
Impact: <merge-blocked / artifact-unavailable / other>
Owner: <person-or-team>
Current action: <investigating / reverting / fixing>
Next update: <time-or-condition>
```

Once restored, send a closure notice:

```text
[MAIN BUILD RESTORED]
Repository: <repository>
Verified commit: <commit-sha>
Workflow run: <link>
Required checks: <passed-checks>
Recovery: <fix-or-revert>
Follow-up: <issue-or-none>
```

Never include tokens, passwords, secret values, or sensitive data in notifications or logs. When sharing logs, use links with proper access controls and confirm logs contain no authentication credentials.

## 8. Example Pre-Merge Verification Workflow

The GitHub Actions example below illustrates a verification job for a Gradle project. The job's result can serve as a required status check in branch protection policies.

```yaml
name: Mainline verification

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: verify-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    name: verify
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run required checks
        run: ./gradlew --no-daemon clean check
```

The `verify` job is named explicitly so teams pick the right check in branch protection. `pull_request` verifies changes pre-merge; `push` to `main` verifies post-integration state. `timeout-minutes` prevents runs from hanging indefinitely.

The `concurrency` block is an example requiring thought before adoption. On the same ref, a new run cancels an in-progress run. That works well for some latest-state check workflows, but not for jobs producing retained artifacts, deployment jobs, or tasks that cannot safely be cancelled. When adopting it, verify how your platform handles pull requests, merge queues, and runs that must finish independently.

This example also omits integration tests, security scans, coverage reports, or artifact uploads. Add real-world conditions to jobs and configure required checks accurately. If using a merge queue, add the queue trigger and confirm compatibility with your platform's merge group events.

## 9. Process Mistakes That Commonly Destabilize the Main Branch

| Habit | Consequence | Improvement |
|---|---|---|
| Feature branches living too long | Accumulates conflicts and drift from main | Keep changes small and integrate frequently |
| Merging when required checks have not passed | Bugs land straight on the main branch | Enable branch protection and audit truly required checks |
| Checking only pull requests, not post-merge | Misses integration or main-branch config errors | Run pipelines on pushes to main or merge candidates |
| Multiple people fixing the build uncoordinated | Conflicting fixes and lost root-cause clues | Assign one coordinator and split tasks clearly |
| Disabling tests to turn builds green | Loses regression detection | Fix tests or time-box quarantine with compensating checks |
| Re-running repeatedly without investigating | Masks flaky tests or environment issues | Retain logs, classify, and reproduce under control |
| Failing to record revert or bypass decisions | Hard to audit and easy to repeat mistakes | Record reason, decision-maker, and follow-up steps |
| No duty owner or alert channel | Red builds linger with nobody accountable | Establish ownership and notification rules |

Above all, never treat "green build" as an isolated target. If a team achieves green by dropping checks, lowering thresholds arbitrarily, or hiding failures, the main branch loses credibility. Every change to quality gates needs justification, an owner, and a verification plan.

## 10. Measuring Main Branch Health

Teams can track several metrics to verify whether their process genuinely keeps mainline stable:

| Metric | Interpretation | Signs to Investigate |
|---|---|---|
| Mainline green percentage | Share of time the main branch passes required checks | Sustained drops indicate poorly handled integration or environment errors |
| Build recovery time | Time from main build breakage until required checks pass again | Spikes point to missing ownership, logs, or revert procedures |
| Main build failure count | Frequency of regressions or pipeline incidents | Categorize by root cause to find recurring failure classes |
| Pull request wait time | Time from opening a PR until merge eligibility | Separate review wait, runner queue, and fix time to optimize properly |
| Flaky test rate | Stability of verification checks | High rates erode confidence in required checks |
| Quality gate bypass count | Frequency of policy exceptions | Repeated exceptions signal miscalibrated policies or test capacity |

Define calculations consistently. For instance, build recovery time can start at the first run confirming mainline failed and end at the passing run on the fixed or reverted revision. Distinguish active incident time from status-update wait time to pinpoint real bottlenecks.

Never rely on a single metric to judge effectiveness. High mainline green percentage paired with excessive pull request wait times may mean too many checks sit at a single gate. Short recovery times alongside rising bypasses may signal prioritizing green badges over quality. Read metrics alongside context, trends, and developer feedback.

## 11. Checklist for Keeping the Main Branch Healthy

When setting up or auditing a repository, use this checklist:

- [ ] Clear definitions exist for a green mainline state and required checks.
- [ ] The main branch is protected; direct pushes and bypass permissions are restricted.
- [ ] Pull requests are appropriately sized, reviewed, and linked to related work.
- [ ] Feature branches integrate frequently; incomplete changes use feature flags where appropriate.
- [ ] Pipelines verify the exact revision pre-merge and re-verify post-integration.
- [ ] Required status checks have stable names, run on the right triggers, and never mask errors.
- [ ] Merge queues are considered when multiple pull requests frequently contend for the same branch.
- [ ] Flaky tests have an investigation process, owner, and remediation deadline.
- [ ] When mainline turns red, the team has a coordinator, notification channel, and unified fix-or-revert workflow.
- [ ] Fixes are verified on a new commit before reopening the merge stream.
- [ ] Exceptions and workarounds are recorded with expiration dates and follow-up items.
- [ ] The team tracks mainline downtime, pull request wait times, and flaky test rates.

Keeping the main branch healthy is a shared team discipline. Small changes, frequent integration, meaningful check gates, and a consistent broken-build response keep everyone working on a reliable codebase. When a build breaks, teams must quickly assign an owner, recover in a verifiable manner, and resume integration only once the new revision clears all required checks.

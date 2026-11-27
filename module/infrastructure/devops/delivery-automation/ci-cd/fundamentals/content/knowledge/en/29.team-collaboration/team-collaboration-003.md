# Prioritizing Broken Main Branches or Pipelines

## 1. Why Broken Main Branches and Pipelines Must Be Prioritized

The main branch (typically `main` or `trunk`) is the team's shared integration point. Developers branch from it to start work, pull requests validate integration against it, and pipelines commonly use it as the source for building artifacts or releasing. If the main branch cannot build, mandatory tests keep failing, or the pipeline cannot run, many people can be blocked at once.

A bug on a feature branch is usually confined to a single change or a small group. A failure on the main branch or a shared pipeline can affect every pull request, every dependent team, and even the ability to ship emergency fixes. Therefore, when the two types of work compete for capacity, restoring shared integration capability usually delivers higher value than continuing to optimize an isolated feature.

Prioritizing a broken main branch or pipeline does not mean every error must halt all engineering activity. The team must determine the scope, impact, root cause, and fastest recovery path that preserves quality. Sometimes the right action is reverting a recently merged commit; sometimes a runner, registry, or credential must be fixed; sometimes a single flaky test needs time-bound quarantine.

The objective is to return the system to a state where new changes can be integrated, verified, and released reliably.

## 2. Distinguishing a Broken Main Branch from a Broken CI Platform

Two different situations share the same symptom—a red pipeline—but require different responses.

| Situation | Symptoms | Initial Response |
|---|---|---|
| Main branch broken by code | Build/tests fail after a specific commit or merge; failure is reproducible | Identify offending commit, revert or fix code |
| Pipeline definition broken | Multiple jobs fail to generate, workflow syntax error, broken stage dependencies | Fix pipeline-as-code and verify with a small pipeline |
| Runner/platform failure | Jobs stay unassigned, runners offline, executor errors, or corrupted workspaces | Restore runner/control plane; do not edit source to mask the error |
| Dependency outage | Registry, package repository, cloud API, or test database unavailable | Verify dependency, reduce retries, apply controlled workaround |
| Test instability | Tests pass and fail intermittently on the exact same revision | Identify flaky test, quarantine with expiry, open root-cause issue |
| Policy/configuration failure | Incorrect credentials, permissions, branch protection, or environment lock | Restore proper policy/config and check audit logs |

Before changing application code, check whether the failure occurs across multiple branches/repositories or multiple runner pools. If every job began failing at the same time after a runner image update, the root cause is likely in the platform. If only a new commit causes a specific test to fail consistently in a stable environment, the cause is likely in code.

Never misclassify a platform failure as an application bug just because the pipeline returned a failed status. Misclassification wastes time fixing the wrong thing and can introduce unnecessary commits onto the main branch.

## 3. Prioritizing by Impact

When multiple issues occur simultaneously, teams should prioritize by blast radius and blocking severity:

1. **Main branch cannot build/test:** blocks integration and can base all pull requests on a broken revision.
2. **Shared pipeline is down:** prevents verifying changes, publishing artifacts, or deploying.
3. **Security/quality gate disabled or misfiring:** may allow unsafe changes through or block all valid changes.
4. **Production/release pipeline broken:** impairs incident mitigation and release capability.
5. **A job group or runner pool failing:** affects a subset of developers/workloads.
6. **An individual pipeline or test failing:** smaller scope, handled by its owner according to impact.

This ordering is a starting guide, not a rigid rule. A critical security vulnerability or production outage may outrank a main build failure. Evaluate based on real-world impact, duration, number of blocked teams, and the risk of delay.

## 4. Using Severity and Scope to Coordinate

A straightforward approach is classifying pipeline incidents by severity:

| Level | Scope/Impact | Response |
|---|---|---|
| SEV-1 | Main branch cannot integrate broadly, shared CI is down, urgent release is blocked, or critical security risk exists | Trigger incident coordination, rally key responders, post regular updates |
| SEV-2 | An important pool, critical pipeline, or large team is impacted; workaround exists but productivity drops sharply | Assign an owner, track progress, notify affected teams |
| SEV-3 | A single job/test or one project is affected with a clear workaround | Assign an owner, handle under normal SLA/priority |
| SEV-4 | Minor issue, does not block primary work | Add to backlog and address as planned |

Severity labels and response times must align with organizational processes. Avoid inventing universal time commitments without supporting SLOs or on-call policies. What matters is that each level carries consistent meaning and drives concrete action.

## 5. Response Workflow in the First Few Minutes

When a broken main branch or shared pipeline is detected:

1. Confirm the failure and when it started; avoid reacting to a single unverified notification.
2. Determine the scope: main, pull requests, one repository, multiple repositories, one runner pool, or all of CI.
3. Record the relevant commit, pipeline run, job, stage, runner, and dependencies.
4. Designate one coordinator and one technical owner for each investigation track.
5. Broadcast a concise notice that main/the pipeline is degraded, including any verified workaround.
6. Pause changes that could widen the incident scope if necessary.
7. Pick the recovery action with the lowest risk and shortest time to restore.
8. Verify main and the pipeline with a full run before announcing recovery.

Do not let multiple people edit the same pipeline file or push competing fixes to main without coordination. Split work into independent tracks: one person isolates the root cause, one checks runners/dependencies, one prepares the revert or fix, and one communicates status to the team.

## 6. Protecting the Main Branch to Contain Incidents

Branch protection is a control layer that limits unverified changes from entering the main branch. Depending on the platform, policies may include:

- Requiring pull requests instead of direct pushes.
- Requiring critical status checks to pass.
- Requiring reviews from owners or responsible teams.
- Blocking force pushes and deletion of the main branch.
- Requiring branches to be up to date with the base branch before merging.
- Using CODEOWNERS or equivalent mechanisms for pipelines, release configs, and policies.
- Restricting bypass permissions and auditing every bypass.

Do not disable branch protection just to merge a fix quickly without evaluating risk. In emergencies, if policy permits a bypass, record an accountable person, rationale, scope, expiration, and follow-up verification step. Bypassing should never become the default path for fixes.

## 7. When to Revert Instead of Fixing Forward on Main

Reverting removes an offending change from the main branch via a new commit that reverses the prior commit's effect. It is typically the right choice when:

- A recent commit is clearly tied to the failure.
- A safe fix cannot be identified quickly.
- A newly merged change prevents main from building or passing mandatory tests.
- The change can be reversed without breaking migrations or generated data.
- The immediate goal is restoring integration for the whole team.

Reverting is usually far more traceable than rewriting history via reset/force-push on a shared branch. It creates a new commit and preserves shared history.

Never revert blindly when the error actually stems from a runner, registry, or external dependency. Nor should you revert a destructive data migration if reversing it could erase valid data. Before reverting, assess impacts on schemas, events, configs, side effects, and already-deployed releases.

## 8. Safe Revert Workflow

A typical workflow:

1. Identify the offending commit or merge commit using logs, pipeline runs, and change scope.
2. Check whether subsequent commits depend on that change.
3. Evaluate migrations, configs, API/event contracts, and written data.
4. Create the revert commit on a repair branch or emergency pull request.
5. Run builds, tests, and required gates as far as possible.
6. Obtain a fast review from an authorized reviewer per process.
7. Merge the revert into main.
8. Re-run the full pipeline and verify main's status.
9. Announce that main is restored and file a follow-up to fix the root cause.

Example reverting a regular commit:

~~~bash
git log --oneline -10
git revert <commit-sha>
git push origin HEAD:refs/heads/fix/restore-main
~~~

This is an illustrative example; pushing must follow your repository's branch/PR workflow. For a merge commit, Git needs to know the mainline parent:

~~~bash
git revert -m 1 <merge-commit-sha>
~~~

The `-m 1` flag assumes the first parent was the main branch before the merge. Verify the merge commit's parent structure before running it. Reverting a merge commit can affect bundled commits; if you later want to re-merge the reverted change, understand how Git tracks history, as you may need to revert the revert commit itself.

## 9. When to Hotfix Instead of Reverting

A hotfix may be appropriate when:

- The root cause is clear and the fix is small and quickly testable.
- Reverting would strip out a critical change or create an incompatible state.
- A security or data bug requires a direct fix.
- A bad dependency/config can be fixed independently.
- The team already has a reproduction test and a way to verify the fix.

A hotfix must never become an excuse to skip review, testing, or auditability. At minimum, define scope, run relevant regression tests, obtain proper review, and run post-merge verification pipelines. If the full suite cannot run because the CI platform itself is broken, establish an alternative verification plan, obtain risk sign-off, and run the full suite once CI recovers.

Another option is to revert first to restore main, then develop the hotfix cleanly on a new branch. This decouples fast recovery from fixing the root cause.

## 10. When Pipelines Fail Due to Configuration or Platform Issues

If multiple commits or repositories fail at the same step simultaneously, inspect the pipeline service before touching application source:

- Is the scheduler creating and assigning jobs?
- Are runner agents online with the right labels and versions?
- Was a runner image recently upgraded or were system dependencies altered?
- Did secrets/identities expire or did policies change?
- Is the registry/package repository experiencing errors, throttling, or certificate issues?
- Does the artifact store have quota, permission, or network issues?
- Did a workflow template or shared action change recently?
- Are concurrency limits or resource locks leaving jobs queued indefinitely?

Recovery actions may include rolling back a runner image, restoring a shared workflow template, re-issuing credentials per policy, adjusting quotas, or temporarily shifting jobs to a healthy pool. Every platform change must be documented and verified on a representative pipeline before rolling out broadly.

Avoid patching individual repositories to work around a shared platform defect when it can be fixed at the source. Per-repository workarounds create config drift and raise maintenance overhead.

## 11. Handling Flaky Tests Without Hiding Real Bugs

A flaky test produces inconsistent results on the exact same revision under equivalent conditions. It can make main appear broken even when code hasn't changed, yet it can also mask real regressions if teams repeatedly rerun until it passes.

When a flaky test is suspected:

1. Check pass/fail history by test, runner, OS, and timestamp.
2. Perform bounded reruns to confirm non-determinism; preserve all run results.
3. Investigate dependencies on timing, execution order, shared data, networking, or concurrency.
4. Create an issue with an owner and a fix deadline.
5. If quarantine is necessary, explicitly document which test is bypassed, its impact scope, and its expiration date.
6. Keep all other gates active and do not turn the entire suite non-blocking.
7. Restore the test to the mandatory gate once fixed and proven stable.

Time-bound quarantine is a congestion-relief measure, not a final resolution. If the test covers security, data integrity, or critical business flows, put compensating controls in place before allowing merges.

## 12. When to Pause Merges

A merge freeze temporarily halts or restricts merges into main during incident handling. It is useful when:

- Main is in an unbuildable or untestable state.
- A shared pipeline gate cannot verify changes.
- Continuous incoming commits would obscure root-cause isolation.
- A migration or platform change is in an inconsistent state.
- The team needs to keep main stable for a hotfix or rollback.

A freeze should have clear scope and duration. You may restrict merges only for specific file paths, a single repository, or a certain change type. Independent, low-risk pull requests may still proceed if relevant gates remain operational.

When a full freeze is needed, announce the reason, decision maker, reopening criteria, and how queued PRs will be handled. Avoid indefinite freezes or leaving developers guessing about status.

## 13. Reopening Merges After Recovery

Do not reopen merges merely because one fix commit merged or a single job turned green. Reopening criteria must be explicit:

- Main builds cleanly from the current revision.
- Critical required checks run and pass.
- Relevant pipeline templates and runner pools are operating stably.
- Artifacts and reports upload and are retrievable if required by the workflow.
- No incomplete deployment or migration states remain that affect main.
- Quarantined tests have owners, expiry dates, and compensating controls.
- The team clearly announces that merges are open again.

For multi-stage pipelines, run at least one representative end-to-end pipeline from checkout through tests and artifacts. If the incident affected multiple runner pools or repositories, verify each affected pool/scope before declaring full recovery.

## 14. Assigning Roles to Prevent Collisions

During incidents impacting multiple teams, clear role assignments prevent duplicate effort and conflicts:

| Role | Responsibility |
|---|---|
| Incident coordinator | Sets priorities, assigns tasks, tracks status, and coordinates communications |
| Main branch owner | Evaluates offending commits, chooses revert/hotfix, and verifies main |
| CI platform owner | Investigates scheduler, runners, templates, artifacts, and dependencies |
| Test owner | Analyzes test failures/flakiness and defines alternative test scope |
| Release owner | Evaluates impact on artifacts, deployments, environments, and active releases |
| Communicator | Updates developers, dependent teams, and stakeholders on a steady cadence |

One person can cover multiple roles on a small team, provided it is clear who decides and who executes. Every action should have one owner accountable for seeing it through, avoiding a state where everyone watches and no one finishes the fix.

## 15. Incident Communication Channels and Cadence

Incident updates should be brief, structured, and focused on what others need to know:

- Current status: where main/the pipeline is failing.
- Scope: which repositories, pools, teams, or stages are affected.
- Impact: whether merges, tests, releases, or deployments are blocked.
- Owner: who is investigating or fixing.
- Action underway: revert, hotfix, runner recovery, or freeze.
- Workaround: verified temporary steps people can take.
- Next update: when the team can expect the next status check.

Example announcement:

~~~text
CI incident: main branch checks are failing at integration-test.
Scope: order-service repository; unit test jobs remain operational.
Impact: pausing merges to main while investigating.
Owner: service owner investigating recent commits; CI platform checking database runner.
Workaround: continue working on feature branches; do not bypass required checks.
Next update: once root-cause triage completes.
~~~

Never post secrets, tokens, customer payloads, or sensitive logs into public channels. Share permission-scoped links to the incident record and sanitized logs.

## 16. Preserving Momentum and Reducing Context Switching

Main or pipeline incidents often pull many developers away from active work. Good coordination limits how many people are disrupted:

- Pull only people with needed expertise into the active response group.
- Assign independent investigation tracks to specific owners.
- Ask non-responders to continue work that does not depend on main where feasible.
- Log tested hypotheses and results so effort isn't duplicated.
- Maintain a single shared incident timeline.
- Avoid rapid-fire speculative small fixes without a hypothesis and verification criteria.
- After recovery, move long-term investigation into follow-up tasks with owners.

A small, clearly coordinated response group is usually more effective than pulling the entire engineering org into a single troubleshooting thread.

## 17. Controlling Changes While Main Is Broken

While main is unstable, each new commit can make root-cause isolation harder. Teams can apply:

- Pause merging non-urgent changes.
- Allow only owner-approved reverts or hotfixes.
- Freeze runner images/templates during investigation unless identified as the cause.
- Log every change to configuration, quotas, secrets, or permissions.
- Avoid making multiple independent changes to the same environment at once.
- Use dedicated repair branches and tightly scoped pull requests.
- When a bypass is required, log the actor, rationale, revision, and compensating verification.

Avoid locking down all activity unnecessarily. If main is broken due to one test while lint/build pipelines remain trustworthy, work independent of the failing gate may continue under clear policy. What matters is never presenting that state as a fully green main branch.

## 18. Step-by-Step Main Branch Recovery Flow

~~~mermaid
flowchart TD
    A[Detect main or shared pipeline failure] --> B[Confirm scope and impact]
    B --> C[Classify source, pipeline, runner or dependency]
    C --> D[Assign incident and technical owners]
    D --> E{Main integrity at risk?}
    E -- Yes --> F[Freeze or restrict merges]
    E -- No --> G[Keep unaffected work moving]
    F --> H{Known safe revert?}
    G --> H
    H -- Yes --> I[Revert offending change]
    H -- No --> J[Prepare reviewed hotfix or platform repair]
    I --> K[Run required validation]
    J --> K
    K --> L{Main and pipeline healthy?}
    L -- No --> M[Continue investigation / recovery]
    M --> K
    L -- Yes --> N[Reopen merge and communicate]
    N --> O[Root cause and follow-up]
~~~

The workflow can iterate if the first fix does not resolve the failure. Each cycle needs a hypothesis, a small change, verification evidence, and a next decision. Avoid changing multiple components at once, as it makes it hard to tell which action actually restored the system.

## 19. Example: Main Broken After Merging a Dependency Update

Suppose a pull request bumps an HTTP library version. After merging, unit tests still pass, but integration tests on main fail due to altered TLS handling. Other pull requests are blocked because the required check is shared.

Team response:

1. The coordinator confirms the failure only began after the merge commit and is isolated to `integration-test`.
2. The main owner inspects the commit and confirms it can be reverted without impacting migrations or data.
3. The test owner writes a reproduction test to ensure the fault is understood.
4. The release owner checks whether any artifact from the broken revision was published or deployed.
5. The team merges a revert commit without force-pushing main's history.
6. The full pipeline re-runs, verifying integration tests and the artifact stage.
7. The team announces merges are reopened once required checks pass.
8. A follow-up task is created to update the dependency on a separate branch with compatibility tests.

If a faulty artifact already reached production, the team must separately evaluate a release rollback and data/runtime state. Restoring main does not automatically restore production.

## 20. Example: Runner Pool Failing While Main Code Is Healthy

Suppose numerous Linux pipelines begin failing at checkout with disk-full errors. Windows jobs continue running; Linux pipelines fail regardless of commit.

Analysis:

- Compare failures across multiple repositories and revisions.
- Inspect free disk/inodes and workspace cleanup on the runner pool.
- Identify that a new runner image stopped cleaning up stale caches.
- Drain or isolate the affected pool and stop scheduling new jobs onto it.
- Route eligible jobs to a fallback pool if available.
- Fix the image/cleanup policy, provision fresh runners, and run a representative pipeline.
- Verify queue wait times, checkout success, and artifact uploads before restoring the pool.

In this scenario, reverting application code will not solve the error. The team must restore the runner platform and leave main code untouched.

## 21. Handling When Required Checks Cannot Run

Certain CI outages prevent required status checks from completing. Depending on the platform, PRs may stay pending or blocked. This is a safeguard, not an error to bypass immediately.

Before considering a bypass:

- Identify which check is not running and why.
- Check whether an equivalent trusted check exists.
- Assess the change type and risk level.
- Determine if the check can be restored within a reasonable timeframe.
- If policy permits an exception, require an authorized approver, rationale, scope, and audit record.
- Document mandatory compensating checks once CI returns.

Never configure a dummy status check that always passes just to unblock merges. Doing so defeats branch protection and can leave dangerous configuration behind after the incident.

## 22. Tracking Recovery Time and Response Quality

To improve the process, track:

- Time to detect: elapsed time from failure onset to team detection.
- Time to acknowledge: elapsed time until an owner picks up the issue.
- Time to classify: elapsed time to determine whether the fault is code, pipeline, runner, or dependency.
- Time to restore main: elapsed time until main returns to an integratable state.
- Time to restore CI: elapsed time until shared pipelines stabilize.
- Blocked developer time: duration or count of people blocked from working.
- Reopen rate: percentage of incidents that recur after recovery was declared.
- Follow-up completion: percentage of preventive action items completed.

Do not optimize time-to-restore by skipping mandatory checks. Opening main prematurely and having to freeze again can lengthen total disruption and erode team trust.

## 23. Post-Recovery: Root Cause and Prevention

Once main and the pipeline stabilize, the team should shift from response to improvement:

- Reconstruct the timeline from commits, pipeline runs, runner events, and deployment records.
- Identify the root cause and contributing factors.
- Distinguish technical defects from process gaps or missing observability.
- Add reproduction tests or pipeline checks.
- Fix runner images, templates, or shared workflows if implicated.
- Add alerts for earlier detection signals.
- Strengthen branch protection or ownership rules if needed.
- Update runbooks, dependency policies, and rollback plans.
- Assign an owner and deadline to every action item.

Post-incident reviews should examine systems and decisions rather than blaming individuals. The goal is reducing recurrence likelihood and shortening recovery time next time.

## 24. Common Anti-Patterns

| Anti-Pattern | Consequence | How to Improve |
|---|---|---|
| Continuing to merge while main cannot be verified | Failures pile up, making offending commits hard to isolate | Freeze or restrict merges by scope |
| Reverting every pipeline failure | Unrelated source changes get rolled back | Triage code vs. platform vs. dependency first |
| Force-pushing to erase commits on main | Shared history is rewritten, breaking traceability | Use revert commits per policy |
| Hotfixing without a reproduction test | May only mask symptoms | Add a test or minimal before/after verification evidence |
| Disabling required checks to merge fast | Loss of quality control and auditability | Use scoped exceptions with owner and compensating checks |
| Multiple people editing one pipeline concurrently | Merge conflicts and poor coordination | Assign roles and one owner to integrate changes |
| Rerunning flaky tests until green | Hides defects and skews metrics | Limit retries, apply time-bound quarantine, fix root cause |
| Restarting all runners when CI slows down | Can increase load and destroy evidence | Investigate scheduler, resources, and dependencies |
| Reopening merges after one green job | Misses broken downstream stages or pools | Run scoped end-to-end validation |
| Closing incidents without follow-up | Root causes persist | Track action items with owners, deadlines, and reviews |

## 25. Checklist for Prioritizing Broken Main or Pipeline

When main or a shared pipeline breaks, verify:

- [ ] The failure is confirmed and its start time is recorded.
- [ ] Affected repositories, branches, runner pools, stages, and teams are clear.
- [ ] Initial triage classifies the cause: source, pipeline definition, runner, dependency, or policy.
- [ ] A clear coordinator and technical owner are assigned.
- [ ] The team has communicated status, impact, and verified workarounds.
- [ ] Any merge freeze or restriction is grounded in actual risk.
- [ ] The offending commit and dependencies with subsequent commits have been checked.
- [ ] Reverts/hotfixes account for migrations, data, artifacts, and side effects.
- [ ] Required checks are not disabled arbitrarily; any bypass is audited.
- [ ] Repair changes are tightly scoped and backed by test evidence.
- [ ] Main builds/tests and a representative end-to-end pipeline pass.
- [ ] Relevant runner pools, artifact uploads, and status callbacks are healthy.
- [ ] Reopening conditions for merges have been clearly communicated.
- [ ] Incident timeline and preventive action items are recorded.

## 26. Core Operating Principles

1. Prioritize restoring shared integration because main and shared pipelines affect multiple teams.
2. Separate code faults from pipeline, runner, dependency, and policy faults before making edits.
3. Assess severity by scope, user impact, and release capability.
4. Designate a coordinator and owner; avoid uncoordinated edits in the same spot.
5. Use reverts for fast recovery when the offending change can be safely reversed.
6. Use hotfixes when the cause is clear, tests exist, and proper review is followed.
7. Protect main with branch protection; every bypass requires rationale, scope, and audit.
8. Keep merge freezes scoped with explicit reopening criteria and clear communication.
9. Verify main and the pipeline end-to-end before declaring recovery.
10. After the incident, add tests, telemetry, runbooks, and action items to prevent recurrence.

Prioritizing a broken main branch or pipeline is a coordination decision to protect the shared delivery stream. When teams classify root causes accurately, assign clear roles, choose reverts or hotfixes with evidence, and reopen merges only after verification, outage duration drops while release quality stays intact.

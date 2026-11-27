# Reviewing Small Changes to Reduce Integration Wait Time

In CI/CD, code can be built and tested automatically yet still sit for hours or days in an unreviewed pull request. When multiple long-lived branches modify the same area, teams face merge conflicts, late integration, and interaction bugs discovered right before release. Review wait time therefore becomes a substantial share of total lead time.

One way to improve this is breaking work into small changes that have a clear goal, can be reviewed independently, and are integrated frequently. Small changes help reviewers grasp scope quickly, authors get early feedback, and CI verify each step. However, "small" does not merely mean fewer lines of code. A small change must have a sensible business boundary, explainable behavior, appropriate tests, and assessable risk.

Reviewing small changes is a team collaboration practice: authors prepare understandable changes; reviewers give focused feedback; CI provides fast feedback; and the team limits work in progress and integrates regularly. The goal is reducing wait time and coordination overhead while preserving technical quality, security, and release traceability.

## 1. Why Integration Wait Time Grows

A change typically passes through several states: in development, awaiting review, under review, awaiting CI, changes requested, approved, awaiting merge, and integrated. When any waiting state stretches out, downstream work backs up.

Common causes include:

- Pull requests are too large, forcing reviewers to read many files and understand multiple decisions at once.
- PRs mix refactors, behavioral changes, formatting, and unrelated dependency updates.
- No reviewer owner is assigned, or requested reviewers are overloaded.
- PRs lack descriptions, test evidence, or verification instructions, forcing reviewers to ask clarifying questions.
- CI runs slowly, runner queues are long, or the entire pipeline re-runs after every minor tweak.
- Multiple PRs edit the same file or API, increasing dependencies and conflicts.
- Teams keep branches open for a long time and only merge near the end of a sprint or before release.
- Review comments do not clarify whether they are blocking or mere suggestions, prolonging back-and-forth cycles.
- Authors do not follow up on feedback, or reviewers have no response-time commitment.

Not all wait time is waste. A change affecting data, access permissions, or production requires thorough review and proper approval. What needs reduction is idle wait time that adds neither evidence nor risk reduction.

## 2. What Makes a Change Small?

A small change can be understood through four characteristics:

1. **Narrow scope:** solves one primary objective without bundling multiple independent tasks.
2. **Easy to understand:** a reviewer can grasp the context, intent, and impact in one reasonable read.
3. **Verifiable:** tests, static analysis, or manual evidence confirm correct behavior.
4. **Safely integratable:** the change does not leave the system in a dangerous intermediate state when merged.

Diff line count is a reference signal, not the sole metric. A 30-line change can be very hard to review if it alters authorization or transaction boundaries. A 400-line auto-generated change can be easy to verify if output comes from a reviewed schema and contains no complex hand-written logic.

When judging PR size, look at file count, number of modified concepts, affected dependencies, behavioral complexity, and the context required to understand it. If a reviewer must jump across many modules to figure out what a change means, consider splitting it or adding a diagram/explanation.

## 3. Slicing Vertically Instead of Only by Technical Layer

A common way to split work is creating one PR for the database, one PR for the backend, and one PR for the frontend. This can fit independent schema changes, but often each PR produces no testable behavior on its own and pieces end up waiting on each other.

Vertical slicing splits work along a thin slice of a business journey, cutting across the necessary layers to produce a verifiable outcome. For example, an order-history display feature could be sliced as:

- Slice 1: API returning minimal history with contract tests.
- Slice 2: UI displaying the list using existing data.
- Slice 3: add pagination and empty-state handling.
- Slice 4: add date-range filtering.

Each slice can be merged and deployed once it meets gates, while a feature flag keeps the unfinished capability off. This approach generates early feedback from CI and reviews instead of waiting for the entire feature to be finished.

Do not force every change into a vertical slice if the work is genuinely foundational infrastructure or a migration. In those cases, split into compatible steps with clear verification checkpoints.

## 4. Separating Refactors from Behavioral Changes

When a PR changes behavior and performs a major structural refactor at the same time, reviewers struggle to distinguish bugs caused by new logic from regressions introduced by refactoring. Separating the two goals keeps reviews focused:

1. First PR refactors or introduces an abstraction while preserving existing behavior; tests must prove outcomes remain unchanged.
2. Next PR changes behavior through the new abstraction; the diff clearly highlights business logic.
3. Final PR cleans up old code or temporary abstractions once the migration stabilizes.

For example, when migrating from a legacy pricing engine to a new engine, introduce the interface/router first, then add the new implementation afterward. If gradual rollout is needed, use a feature flag and keep a fallback during the compatibility window.

However, do not split mechanically when refactoring and behavior are tightly coupled or would create an uncompilable intermediate state. Every PR must still build, pass tests, and make sense for independent review.

## 5. Avoiding Giant PRs and Long-Lived Branches

Large PRs raise cognitive load. Reviewers must track many decisions, files, and interactions; a single comment can ripple across other parts. If a fix is needed, the author may have to rebase or re-run CI for the entire diff.

Long-lived branches also create divergence: the main branch keeps moving while the feature branch holds an old snapshot. On merge, conflicts can arise in both syntax and semantics. Two separate changes might each pass tests yet fail when integrated together.

Countermeasures include:

- Merge into mainline frequently in small slices.
- Use feature flags to hide unfinished behavior.
- Break large migrations into compatible stages.
- Avoid maintaining a single integration branch for an entire sprint.
- When a PR must be large for valid reasons, organize it into ordered commits/sections and provide a review guide.
- Open a draft PR early to solicit design feedback before finishing all implementation code.

Do not enforce a rigid line limit for every PR. Warning thresholds can encourage authors to reconsider scope, while still allowing justified exceptions.

## 6. What a Good PR Needs to Provide

Reviewers should never have to guess why a change exists. A PR description should cover:

- **Problem:** the issue or requirement being addressed.
- **Approach:** the chosen solution and why.
- **Scope:** what is changed and what is explicitly out of scope.
- **Behavior:** before/after behavior or input/output examples.
- **Tests:** tests run, results, and any untested boundaries.
- **Risk:** impacts on APIs, databases, security, performance, or operations.
- **Rollout:** feature flags, migrations, configuration, or activation steps if applicable.
- **Evidence:** screenshots, test reports, traces, benchmarks, or related links when helpful.

Description template:

~~~markdown
## Problem
Users cannot see delivery status on the order details page.

## Changes
- Added `deliveryStatus` field to the response.
- Displayed status on the details page.
- Kept the new field optional so older clients remain compatible.

## Testing
- Unit tests: passed
- API contract tests: passed
- UI component tests: passed

## Risk and Rollout
- No database schema changes.
- New UI is gated behind the `delivery-status-ui` feature flag.
- Flag can be turned off immediately if display issues occur.

## Attention for Reviewers
- Semantics of the status before the order is handed off to the carrier.
~~~

This is a suggested structure. You do not need lengthy documentation for a trivial bug fix; provide just enough context for reviewers to make a sound decision.

## 7. Keeping a PR Focused on One Goal

A focused PR answers one primary question: what does this change solve? Avoid bundling the following into the same PR when they can be reviewed and shipped independently:

- Reformatting the entire repository.
- Bulk renaming packages or files.
- Unrelated dependency upgrades.
- Refactoring multiple unrelated modules.
- Altering unrelated business rules.
- Modifying pipelines or permissions unrelated to the feature.
- Updating documentation on unrelated topics.

If a secondary change is a hard prerequisite for the primary change, state the dependency and merge order. Otherwise, split it out so reviewers can approve the independent piece first.

Changes to generated files should specify the source schema/tool and regeneration command. Do not mix generated output with manual edits without a verification process.

## 8. Using Draft PRs for Early Feedback

Draft PRs are useful when an author wants design input before code is complete. Reviewers can weigh in on APIs, boundaries, naming, data models, or rollout strategy before the author invests in full implementation details.

A good draft should state:

- The problem and objective.
- The design under consideration.
- What is complete and what remains unfinished.
- Specific questions where reviewer input is needed.
- Which tests have not been run yet and why.

Drafts should not be treated as ready-to-merge. When transitioning to formal review, the author must confirm the diff is updated, test evidence is current, and prior comments have been addressed or clearly tracked.

Early feedback is most valuable while changes are still cheap to adjust. Do not wait until a PR reaches hundreds of lines before asking reviewers whether the architecture fits.

## 9. Selecting Reviewers by Ownership and Risk Type

The right reviewer understands the code area or risk being modified. Multiple perspectives may be needed:

| Change Type | Appropriate Reviewer |
|---|---|
| Service business logic | Service owner or maintainer |
| API/schema contract | API owner and representative consumer |
| Database migration | Database owner or data operations specialist |
| Authentication/authorization | Security owner or qualified reviewer |
| CI workflow/runner/secret | Platform/DevOps owner |
| UI behavior/accessibility | Frontend maintainer or UX/accessibility reviewer |
| Performance-critical path | Workload owner and someone able to evaluate benchmarks |

CODEOWNERS or equivalent mechanisms can suggest reviewers automatically by file path. However, ownership files must stay updated as teams evolve; otherwise PRs continually route to people no longer responsible.

Do not require excessive reviewers for every PR. One reviewer familiar with the code may suffice for low-risk changes; changes impacting security, data, or production may require additional policy approvals.

## 10. Balancing Review Load and Having Backups

If every PR routes to a single senior engineer, that person becomes a bottleneck. Teams must distribute reviews based on capability, ownership, and current load.

Helpful practices:

- Maintain primary and backup reviewer lists for each area.
- Rotate reviews within the team to share knowledge.
- Limit the number of pending review requests per reviewer.
- Reserve domain specialists for high-risk changes rather than gating every minor edit on them.
- Allow reviewers to reassign requests to the appropriate owner with rationale and context.
- Monitor review load to spot individuals becoming bottlenecks.

Backup reviewers need sufficient context and access permissions. Do not assign reviewers just to inflate headcount; reviewers unfamiliar with the code create extra back-and-forth without improving quality.

## 11. Committing to Review Response Times

Review SLAs help authors predict when feedback arrives and help teams detect congested queues. SLAs should specify business hours, change types, and priority levels.

Example internal agreement:

| Priority Level | Target First Response | Handling |
|---|---|---|
| Urgent production fix | Per incident/on-call policy | Page accountable responder directly and audit |
| High-risk change | Within the business day | Select domain reviewer and allocate review focus |
| Standard PR | Within one business day | Reviewer acknowledges or reassigns to owner |
| Design-feedback draft | Per scheduled agreement | Feedback on specific design questions |

These targets are examples only. Teams should set SLAs around time zones, working hours, and actual impact. First response does not necessarily mean approval; it can be acknowledging the review, giving an ETA, or requesting missing context.

Never use SLAs to pressure reviewers into skipping necessary checks. If a review requires more time, the reviewer should update status and reason so the author can adjust plans.

## 12. Distinguishing Blocking Comments from Non-Blocking Comments

Comments should clearly signal impact severity:

- **Blocking:** issues that must be fixed or explicitly resolved before merge—such as correctness bugs, security flaws, data loss, contract breaks, or failing mandatory tests.
- **Non-blocking suggestion:** helpful improvements not required for the current PR, such as naming preferences or minor refactors.
- **Question:** asks the author to explain intent or behavior.
- **Nit:** minor style/formatting details that do not affect correctness.

Reviewers should explicitly mark whether a comment blocks merging. Authors should never have to guess if a suggestion is mandatory. When a concern poses real risk, explain the scenario and consequence rather than just writing "please change".

Resolving a comment thread does not automatically mean the underlying issue is fixed. Author and reviewer must confirm the change or rationale for not applying it. When a blocking comment is resolved via an alternative decision, record the rationale for future reference.

## 13. Writing Actionable Review Comments

Good comments state location, issue, scenario, and suggested direction or question. Example:

~~~text
Blocking: the request may be retried after a timeout even though the first attempt already committed.
If the handler does not check the idempotency key, an order could be created twice.
Please add a test for retrying with the same key before merging.
~~~

Unhelpful comment:

~~~text
This is wrong. Fix it.
~~~

Focus on the code and its impact, not the author's ability or intent. When multiple solutions exist, state the criteria to satisfy and let the author choose the right implementation.

Reviewers should also distinguish definite defects from questions. Use "I don't understand the case where..." when seeking clarification rather than declaring code wrong without full context.

## 14. Reviewing by Risk, Not Just Line Count

An effective review prioritizes risks with major consequences:

1. Correctness and business invariants.
2. Security, authorization, and secret handling.
3. Data integrity, transactions, and migration compatibility.
4. API/event contracts and backward compatibility.
5. Concurrency, retries, and idempotency.
6. Performance, resource usage, and failure behavior.
7. Observability, rollback, and operations.
8. Readability, maintainability, and style.

Order may shift by system. For a pipeline change, token permissions and trust boundaries outweigh style. For a data migration, lock duration, backfills, and rollback must be reviewed before naming.

Do not turn reviews into manual comma-checking when formatters and linters automate it. Let machines enforce mechanical rules and dedicate human attention to semantics, design, and risk.

## 15. Concise Review Checklist

Reviewers can apply a checklist tailored to the change type:

- [ ] PR solves one primary goal and explains why.
- [ ] Diff is reasonably scoped; generated files/minor refactors are explained.
- [ ] New and existing behaviors are clearly understood.
- [ ] Tests cover happy paths, edge cases, and key failure paths.
- [ ] APIs/schemas/events do not break supported consumers.
- [ ] Authorization and validation remain enforced server-side.
- [ ] No secrets, tokens, or sensitive data appear in diffs/logs.
- [ ] Retries, timeouts, and side effects have clear semantics where relevant.
- [ ] Migrations include rollout ordering and rollback/recovery plans.
- [ ] Metrics/logs/traces are sufficient to observe the change.
- [ ] Rollout/feature flags have an owner and fallback if needed.
- [ ] CI evidence matches the exact commit/artifact under review.

Not every PR needs every item. Author and reviewer should pick checks relevant to the change type without bypassing mandatory policy gates.

## 16. Making CI Deliver Fast Feedback

Reviews drag when every one-line fix forces an author to wait 40 minutes just to discover a lint error. Order checks from fastest to slowest and fail fast:

1. Formatting, linting, and static checks.
2. Unit tests.
3. Build/compile.
4. Component or contract tests.
5. Integration tests.
6. Security/dependency scans.
7. E2E, performance, or environment tests.

Actual ordering depends on the dependency graph. Some scans can run in parallel with tests; builds may precede tests. What matters is that fast checks give early signals and mandatory gates are never skipped.

Optimize CI time with properly keyed dependency caches, reliable test selection, adequate runner capacity, and artifact reuse. Never shave time by dropping critical tests or using caches without proper invalidation.

## 17. Separating Fast Feedback from Unreliable Feedback

Fast feedback only helps if it reflects the current commit and artifact. Sources of false confidence include:

- Tests using stale caches or dependencies mismatched against lockfiles.
- Jobs skipped due to bad conditions while the pipeline still reports green.
- Test reports belonging to a different attempt or commit.
- CI running on an outdated merge base after the target branch moved.
- A flaky test succeeding on retry without preserving the initial failure.
- Scans skipped due to timeout yet treated as passing.

Every check needs an explicit status: passed, failed, skipped, cancelled, timed out, or inconclusive. Mandatory gates that skip or time out must be handled per policy, never defaulted to pass.

## 18. Reducing WIP to Increase Completion Speed

WIP (*Work in Progress*) is the amount of work started but not yet finished. When someone opens many PRs at once, they constantly context-switch between changes, and reviewers receive more requests than they can process. Review queues back up even though everyone looks busy.

Limiting WIP helps the team prioritize finishing and integrating open work before starting new tasks. For example, a developer might focus on getting a reviewed PR merged rather than opening two more feature branches.

Little's Law describes the relationship between work in the system, throughput, and completion time:

~~~text
WIP = Throughput x Cycle Time
~~~

Assuming constant throughput, higher WIP typically produces longer cycle times. This formula models steady-state systems; do not use it as an exact predictor for individual PRs. It helps teams understand why starting more work does not necessarily finish more work.

When the review queue grows, the team should swarm to clear the queue rather than reflexively starting new items.

## 19. Reducing Batch Size and Integrating Frequently

Batch size is the volume of changes bundled into a single review, merge, or release. Large batches multiply interactions to check and lengthen feedback loops. Small batches deliver rapid feedback and make CI failure causes easy to isolate.

To reduce batch size:

- Break features into testable behavioral increments.
- Separate mechanical refactors from logic changes.
- Use feature flags to merge unreleased code.
- Keep branches short-lived and sync with mainline regularly.
- Merge independent PRs as soon as gates pass instead of waiting for the entire feature.
- Automate formatting, linting, testing, and metadata checks.

Small batches do not mean splitting one change into dozens of tightly coupled PRs where none build independently. A PR chain only works when each step can be reviewed, verified, and merged in a defined order.

## 20. Trunk-Based Development and Short-Lived Branches

Trunk-based development encourages developers to integrate small changes into the main branch frequently. Working branches stay short-lived; unfinished features are guarded by flags or abstractions.

Benefits:

- Reduces divergence and merge conflicts.
- Catches integration errors early.
- Keeps mainline buildable and testable.
- Makes offending commits easier to isolate because batches are small.
- Supports frequent releases and progressive delivery.

Prerequisites:

- Fast and reliable CI.
- Clear branch protection and required checks.
- Feature flags with lifecycle and cleanup plans.
- Backward-compatible migration/API changes.
- Team discipline around continuous review and integration.

Trunk-based does not mean merging untested code or skipping reviews. It demands small changes, automated tests, and fast feedback so mainline remains continuously usable.

## 21. Merge Queues and Testing on the Latest Integration State

When multiple PRs await merge into main, a PR may pass on an older branch snapshot yet fail when combined with a PR merged moments earlier. A merge queue validates changes against a speculative integrated state before updating the target branch.

Conceptual flow:

~~~mermaid
flowchart TD
    A[PR passes required checks] --> B[Approved and enters merge queue]
    B --> C[Create candidate merge group]
    C --> D[Run required checks on candidate]
    D --> E{Candidate passes?}
    E -->|Yes| F[Merge into target branch]
    E -->|No| G[Remove or rebase affected PRs]
    G --> H[Author fixes or updates PR]
    H --> A
~~~

Merge queues shine when repositories have many contributors and continuous merges. They do not replace code review; they verify post-review integration state. Required checks must match consistently between PRs and merge groups, or pipelines may behave differently across the two contexts.

If a repository lacks a merge queue, teams can use merge trains or an appropriate serialized merge process. Avoid allowing multiple concurrent merges when branch protection cannot guarantee safe updates.

## 22. Stacked PRs for Dependent Changes

Stacked PRs are a chain of changes where each PR builds on the previous one. This technique lets reviewers inspect small layers when a feature has clear sequential dependencies.

Example:

~~~text
main
  └── PR A: introduce pricing interface
        └── PR B: add new pricing implementation
              └── PR C: route eligible tenants to new implementation
                    └── PR D: remove legacy implementation
~~~

The advantage is narrow scope per PR. The drawback is downstream coupling: if PR A changes significantly, stacked PRs above it must be rebased and CI must re-run. Reviewers need visibility into each PR's base branch and merge order.

Use stacked PRs only when dependencies are genuinely meaningful. If every PR depends on a long-lived feature branch, the team may simply recreate the long-lived branch problem in another form.

## 23. Feature Flags Enable Early Merges—With Compatibility

Feature flags let teams merge new code while keeping new behavior turned off. They are a powerful enabler for trunk-based development and vertical slicing.

When using flags:

- Default to off for unfinished features.
- The off code path must continue working and remain tested.
- The on code path requires independent testing.
- Never use feature flags as a substitute for authorization.
- Schemas/APIs/events must stay compatible with older versions.
- Every flag needs an owner, rollout plan, and expiry/review date.
- Once the feature stabilizes, remove the old branch and temporary flag.

Never merge a PR just because code is behind a flag if it breaks compilation, fails startup, or causes side effects while off. Flags hide behavior; they do not hide build errors or initialization risks.

## 24. Reviewing API, Schema, and Migration Changes in Sequence

Even a small PR can have major impact if it alters a contract. When multiple versions run concurrently, review the sequence:

1. Expand: add fields/tables/endpoints without breaking current code.
2. Deploy readers compatible with both old and new data.
3. Switch writers or producers to the new format.
4. Backfill and verify data integrity.
5. Monitor old consumers, queues, and clients.
6. Contract: remove old structures in a later release after dependencies and the rollback window close.

Reviews must check whether old code works against the new schema, whether new code reads old data, whether event backlogs contain old payloads, and whether rollback remains safe.

If a migration involves heavy locking or large backfills, separate schema changes, migration jobs, and code adopting the new schema into observable steps. Do not lump everything into one massive PR and hope deployment happens atomically.

## 25. Reviewing Security and CI Workflows

Pipeline changes can grant permissions to code running in CI. PRs editing workflows, actions, runner labels, secret mappings, or deployment permissions must be reviewed as privileged infrastructure changes.

Reviewers should check:

- Are token permissions least-privilege?
- Can pull requests from forks access secrets or privileged runners?
- Are actions/plugins pinned and sourced from trusted origins?
- Are OIDC trust policies scoped to the repository/workflow/environment?
- Are produced and consumed artifacts linked by digest?
- Could logs leak secrets?
- Are approvals bound to the exact artifact/plan?
- Could the workflow execute untrusted scripts in a privileged context?

Never use a small diff size as an excuse to skip security review. A one-line edit can open write access across the entire repository or enable production deployment.

## 26. Handling CI Flakiness Without Hiding Real Failures

Flaky tests erode pipeline trust and increase wait times. Retries can help distinguish transient errors, but must never turn a failed test into a pass without preserving evidence.

Best practices:

- Record each attempt and its outcome explicitly.
- Separate flaky classification from final pass/fail status.
- Track tests with high retry rates.
- Preserve seeds, environment details, and reports for reproduction.
- Assign an owner and deadline to fix flaky tests.
- Use time-bounded quarantine with policy and telemetry if a test cannot block releases immediately.

Do not allow tests to retry indefinitely. Even if a retry succeeds, surface the initial failure and track overall suite reliability.

## 27. Syncing Reviews with CI Status

Reviewers need to know which commit CI ran on. If an author pushes new commits after review starts, older results may no longer apply.

Practices:

- Display the reviewed commit SHA alongside the commit SHA of required checks.
- Reset approvals after significant code changes if required by policy.
- Re-run checks after edits affecting behavior or workflows.
- Use a merge queue to validate the latest integration candidate.
- Never merge while required checks are pending, stale, or ran on a different revision.
- Record which tests ran on each attempt.

Do not force reviewers to re-read an entire PR after every minor fix. Authors can summarize new commits, resolved comments, and changed diff hunks. Reviewers still need to verify impacted areas.

## 28. Handoff Between Author and Reviewer

An effective review cycle needs clear handoff states:

1. Author opens the PR and assigns reviewers by ownership.
2. Reviewer acknowledges or shares an expected response window.
3. Reviewer leaves comments tagged blocking vs. non-blocking.
4. Author replies to each thread, updates code, or explains decisions.
5. Author marks the PR ready and points out new commits.
6. Reviewer verifies blocking comments and required checks.
7. PR is approved and merged through branch protections.
8. Author or release owner confirms the change integrated cleanly.

If a reviewer cannot continue, hand off to a backup reviewer with context and open comments. Never leave a PR stuck in "review requested" with no one accountable.

## 29. Real-World Example: Breaking Down a Large Checkout Feature

Suppose a team wants to add a new payment method. A single giant PR might simultaneously add tables, APIs, UI, provider integration, telemetry, and rollout rules. Such a change is hard to review and hard to debug if something fails.

It can be split sequentially:

| PR | Scope | Review Evidence |
|---|---|---|
| A | Add `PaymentProvider` interface and legacy adapter | Unit/contract tests proving existing behavior is unchanged |
| B | Add new provider adapter in disabled mode | Sandbox tests and error mapping |
| C | Add optional API capability | API contract tests; older clients remain compatible |
| D | Add UI behind default-off feature flag | Component/E2E tests for flag on and off |
| E | Add telemetry and rollout targeting | Dashboards, privacy review, and test assignment |
| F | Enable internally, then canary by cohort | Operational guardrails and release evidence |
| G | Remove legacy adapter once migration completes | Regression tests and verification of zero remaining consumers |

Each PR merges once independently safe. If a later PR depends on an earlier one, note the order explicitly or use stacked PRs. Artifacts are built by the pipeline and promoted by digest; feature flags control when users see the new payment method.

## 30. Metrics to Improve Review and Integration Flow

Measurement reveals where bottlenecks live. Useful metrics include:

| Metric | Interpretation |
|---|---|
| PR size | Lines/files/concepts changed; spots oversized batches |
| Time to first review | Time from PR ready to first reviewer response |
| Review cycle time | Time from first review to approval/merge |
| PR age | Age of open unmerged PRs |
| Review queue depth | Number of PRs waiting for reviewers |
| Time in changes requested | Time authors spend addressing feedback |
| CI feedback time | Time from push to required check completion |
| Merge wait time | Time from approval to integration |
| Rework rate | Number of revision cycles or reopened PRs |
| Change failure rate | Percentage of changes causing incidents/rollbacks per org definition |
| Deployment frequency | Frequency of deploying valuable changes |

Never optimize a single metric in isolation. Optimizing PR size alone can spawn too many dependent PRs and extra handoffs. Optimizing review speed alone can erode review rigor. Optimizing deployment frequency alone can produce frequent tiny releases with no real value.

Measure at the team and change-type level—never use metrics to rank individuals. Pair wait-time metrics with post-merge quality metrics so teams aren't incentivized to rubber-stamp approvals.

## 31. Team Working Agreement

A concise working agreement can align on:

- PRs focus on one goal and describe sufficient context.
- Authors self-review diffs, tests, and secret hygiene before requesting review.
- Reviewers are chosen by ownership/risk with designated backups.
- Reviewers acknowledge within the agreed SLA.
- Comments explicitly mark blocking vs. suggestion.
- Authors respond promptly or update status when needing more time.
- Required checks must match the exact commit under review.
- Merges go through branch protection/merge queues.
- Feature flags and migrations have owners and cleanup plans.
- Overdue PRs follow an escalation or reassignment path.
- The team prioritizes finishing WIP before starting new work.

Working agreements should adapt to team size and working hours. A team distributed across multiple time zones needs stronger asynchronous reviews and explicit handoffs than a co-located team.

## 32. Common Anti-Patterns

| Anti-Pattern | Consequence | How to Improve |
|---|---|---|
| PRs bundling multiple goals | Hard to understand, slow to review, hard to revert cleanly | Split by testable goal or vertical slice |
| Branches living for weeks | Divergence and conflicts multiply | Merge small changes frequently to mainline |
| Waiting for complete feature before opening PR | Feedback arrives too late | Use draft PRs and vertical slicing |
| Routing every PR to one senior engineer | Reviewer becomes a bottleneck | Establish primary/backup ownership and load sharing |
| Unclassified review comments | Authors don't know what blocks merge | Tag blocking, suggestion, question, nit |
| Manual style reviewing | Wastes human attention | Automate formatters and linters |
| Approving stale commits | Evidence doesn't match code being merged | Verify commit SHA and reset approvals per policy |
| Merging multiple PRs without integration checks | Mainline can break | Use merge queues or candidate validation |
| Using flags to skip compatibility | Disabling flag still fails to recover schema/data | Use expand-contract and mixed-version tests |
| Retrying flaky tests until green | Masks low reliability | Log attempts, quarantine with expiry, fix root cause |
| Minimizing PR line count at all costs | Spawns overly coupled PR chains | Optimize cognitive scope and cycle time |
| Using review speed metrics to penalize individuals | Reviewers rubber-stamp approvals | Use metrics to improve team-level flow |

## 33. Author Checklist Before Requesting Review

- [ ] PR has one primary goal and a title accurately describing the change.
- [ ] Description states problem, approach, scope, and risks.
- [ ] Diff contains no unrelated formatting, refactors, or dependency bumps.
- [ ] Self-reviewed the diff and removed debug code.
- [ ] Appropriate tests ran and evidence matches the current commit.
- [ ] No secrets, tokens, or personal data appear in code or logs.
- [ ] API/schema/event changes have a compatibility plan.
- [ ] Feature flags have defaults, fallbacks, owners, and expiries if used.
- [ ] Migrations include rollout ordering and recovery plans.
- [ ] Reviewers are selected based on ownership and risk level.
- [ ] Specific questions for reviewers are called out clearly.

## 34. Reviewer Checklist Before Approving

- [ ] Understand the PR's goal and scope.
- [ ] Verified correctness and business invariants.
- [ ] Checked security, authorization, and secret handling.
- [ ] Checked data/API/event compatibility.
- [ ] Checked retries, concurrency, and failure behavior where relevant.
- [ ] Confirmed test evidence matches the exact commit.
- [ ] Verified migration, rollout, observability, and rollback details.
- [ ] Comments are clearly categorized and actionable.
- [ ] Blocking comments are resolved or have recorded decisions.
- [ ] Required checks and branch protections pass.
- [ ] Approval remains valid for the revision about to be merged.

## 35. Conclusion

Reviewing small changes reduces integration wait time when every PR has a clear goal, understandable scope, complete test evidence, and the right reviewers. Vertical slicing, draft PRs, short-lived branches, feature flags, and merge queues allow teams to integrate incrementally while controlling behavior and mainline health.

Review speed does not come from skimming or skipping checks. It comes from shrinking batch size, clarifying ownership, committing to SLAs, automating mechanical checks, and delivering fast feedback on the exact commit. When teams limit WIP, keep handoffs explicit, and measure both wait time and post-merge quality, changes move from idea to integration with fewer stalls and controlled risk.

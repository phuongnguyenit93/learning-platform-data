# Distinguishing Pre-Integration Checks from Post-Integration Checks

In a CI/CD flow, source code typically passes through two critical verification points: before a change is merged into a shared branch, and after the change becomes part of the integrated state. These two points answer different questions. Pre-integration checks determine whether a proposed change qualifies to join the shared branch. Post-integration checks verify that the actual merged codebase still works properly when combined with other changes and related components.

Properly distinguishing these two check layers helps development teams get fast feedback while keeping release risk under control. If you only check before merging, the team can miss defects that appear only when multiple changes coexist. If you only check after merging, defects may already enter the main branch, affect other contributors, and disrupt the delivery flow. Therefore, pipelines must coordinate both layers with different objectives, scopes, feedback times, and blocking rules.

## 1. Identifying the Integration Point in the Delivery Flow

In this lesson, **integration** primarily refers to bringing a source code change into the shared branch a team uses for development or release, usually through a pull request or merge request. Depending on the platform and workflow, the shared branch may be **main**, **master**, **develop**, or a dedicated integration branch.

A change typically moves through the following states:

1. A developer creates commits on a working branch.
2. A pull request is opened requesting to merge the change.
3. The pipeline runs pre-integration checks on the commit or projected merge result.
4. Once mandatory conditions pass, the change is merged into the shared branch.
5. The post-integration pipeline runs on the merged commit.
6. If subsequent conditions pass, the system builds or promotes an artifact, deploys it to an environment, and verifies the result.

The diagram below illustrates both check layers and their relationship to release progression:

~~~mermaid
flowchart TD
    A["Commit on working branch"] --> B["Open or update pull request"]
    B --> C["Pre-integration checks"]
    C --> D{"Mandatory gates passed?"}
    D -- "No" --> E["Return feedback, fix change"]
    E --> B
    D -- "Yes" --> F["Review and merge"]
    F --> G["Integrated commit on shared branch"]
    G --> H["Post-integration checks"]
    H --> I{"Integrated state passes?"}
    I -- "No" --> J["Investigate, fix, or revert"]
    I -- "Yes" --> K["Package and store artifact"]
    K --> L["Deploy to environment"]
    L --> M["Smoke tests and verification"]
    M --> N["Ready for release / continue rollout"]
~~~

Remember that pre-integration and post-integration checks differ in more than just execution timing. They differ in **inputs**, **objectives**, **isolation level**, **test scope**, and **the decision their results support**.

Beyond merging source code, a system may also integrate services, databases, message brokers, or third-party APIs. Checks at both stages must still make clear whether they are testing repository-level changes, component interactions, or whole-system behavior.

## 2. What Are Pre-Integration Checks?

**Pre-integration checks** are checks performed before a change is accepted into the shared branch. In pull request workflows, they are usually triggered when a pull request is created or updated.

Their primary purpose is to catch defects belonging to the proposed change early and provide evidence for reviewers to decide whether to merge. Developers receive feedback while the change is still under their own control, so fixes cause less ripple disruption.

Common check categories include:

- **Formatting and convention checks:** catching code that violates project style rules.
- **Static analysis:** spotting detectable issues without running the full application.
- **Unit tests:** verifying the logic of functions, classes, or small components.
- **Component tests:** testing a single component in isolation, potentially replacing external dependencies with mocks or fakes.
- **Compilation and build checks:** confirming the change compiles or packages with the project configuration.
- **Targeted contract tests:** verifying the change still conforms to published API or message contracts.
- **Security and dependency checks:** catching committed secrets, problematic dependencies, or policy-violating configurations.
- **Selected integration tests in ephemeral environments:** when verifying a change against dependent services before merging is necessary.

There is no rule stating every pre-integration check must be a unit test. An integration test can run pre-merge if it tests the change in an isolated environment at reasonable cost. A check layer is defined by its timing and purpose in the flow, whereas a test type is defined by the scope of interaction it covers.

### 2.1. Inputs to Pre-Integration Checks

The pipeline must pinpoint exactly which code is being tested. Common strategies include:

- **Pull request branch commit:** testing the latest commit pushed by the author.
- **Merge candidate:** testing the simulated result of merging the pull request branch into the current target branch.
- **Merge queue or merge train:** the platform builds an ordered integration candidate, testing the combined result alongside other changes queued to merge.

Testing only the pull request branch commit may miss behavioral conflicts with recent changes on the target branch. For instance, the target branch may have just changed a function signature while the feature branch still calls the old one. Tests on the feature branch alone can pass because it runs against older base code; testing the merge candidate exposes the compilation or test failure.

Consequently, for repositories with many concurrent pull requests, testing the projected merge result or using a merge queue increases reliability. The key requirement is that the tested state must match the state that actually gets merged. If the target branch advances after checks run, the pipeline should re-run or re-verify the updated merge candidate.

### 2.2. Criteria for a Pre-Integration Check Suite

A pre-integration check suite should prioritize:

- Feedback fast enough not to stall the development loop.
- Stable and repeatable results.
- Pinpointing the exact commit, job, and step that failed.
- Ability to re-run on identical inputs to reproduce an issue.
- Blocking merges when any mandatory check fails.
- Never granting permissions or secrets beyond what untrusted changes need.

Fast checks like linting, static analysis, and unit tests usually run early. Heavy integration tests or end-to-end tests can be selected based on risk, run in parallel, or deferred to a later stage if pull request turnaround grows too slow. Still, checks designated as mandatory branch protections must have explicit rules and never be bypassed arbitrarily.

## 3. What Are Post-Integration Checks?

**Post-integration checks** are checks that run after a change has been merged into the shared branch. The pipeline is usually triggered by a push or merge event on that branch.

The goal is to validate the latest codebase state in a realistic integrated context. At this point, the system may contain multiple accepted changes, so the team needs to know whether those changes are mutually compatible and still satisfy product requirements.

Common check categories include:

- **Shared-branch build:** confirming the integrated commit produces a valid output.
- **Integration tests:** verifying interactions across modules, services, databases, or message brokers.
- **System-wide contract tests:** checking compatibility between the combined producers and consumers.
- **Regression tests:** confirming previously working flows still behave properly after integration.
- **System or end-to-end tests:** exercising business flows across multiple components.
- **Migration and data compatibility checks:** verifying schema or data changes work alongside relevant application versions.
- **Broader security scans:** scanning final artifacts, container images, or resolved dependency sets.
- **Artifact quality checks:** confirming outputs carry metadata, digests, and can be stored in a registry.
- **Deployment checks and smoke tests:** verifying the application operates after deployment to integration, test, or staging environments.

Not every project runs all of these immediately after every merge. Scope depends on runtime, architecture, and risk. Some system tests may run on a schedule, before release, or after deploying to staging. However, checks used to decide whether release progression continues must sit at the appropriate stage in the pipeline with traceable results.

### 3.1. Why Re-Verify After Merging?

Even when every pull request passes individually, the merged state can still fail:

- Two separate changes modify a shared assumption in incompatible ways.
- One change updates a producer while another consumer has not been updated yet.
- A database migration conflicts with a still-running application version.
- Build configuration on the main branch differs from the pull request's local context.
- A change breaks an existing business flow not covered by the pull request's own test suite.
- Concurrent changes combine to inflate startup time, memory usage, or service call volume.
- Artifacts built from the integrated state pull different components or dependencies than the pre-merge check environment.

Post-integration checks provide an independent confirmation layer on the shared source of truth. They catch integration defects before that state is used to cut a release or deploy to sensitive environments.

## 4. Comparing the Two Check Layers

| Criterion | Pre-Integration | Post-Integration |
|---|---|---|
| Timing | While change is proposed, before merge | After change enters the shared branch |
| Input | Pull request commit or merge candidate | Integrated commit on the shared branch |
| Core question | Is this change eligible to be merged? | Does the new integrated state work properly? |
| Primary focus | Local defects, change quality, projected compatibility | Cross-change interactions, regressions, whole-system behavior |
| Environment | Often isolated, ephemeral, or using mocked dependencies | Can use integration environments with real or near-real services |
| Desired speed | Fast feedback to support review | Can take longer when deeper checks are needed |
| Decision | Allow or block merge | Allow or block packaging, promotion, or release |
| Failure blast radius | Primarily affects the proposed pull request | Can impact the shared branch and dependent teams |
| Evidence | PR check statuses, logs, test reports | Integrated commit pipeline results, reports, and linked artifacts |

This distinction does not mean a given test type may only run on one side. Unit tests can run both pre- and post-integration. Contract tests can also run at both times. What matters is that **every execution has a clear purpose and validates the right risk for that moment**.

For example, unit tests on a pull request help the author catch bugs in their change. Re-running unit tests on the main branch confirms the integrated build remains consistent with shared-branch configuration and inputs. Both runs may execute the same suite yet answer two distinct operational questions.

## 5. Allocating Test Types by Risk and Feedback Time

Never design a pipeline by dumping every test into one monolithic group. Categorize checks by runtime, reliability, dependency footprint, and severity if a defect escapes.

| Check Group | Pre-Integration | Post-Integration | Rationale |
|---|---|---|---|
| Format, lint, static analysis | Usually mandatory | May re-run or reuse shared build check | Rapid feedback on change quality |
| Unit tests | Usually mandatory | Usually part of shared-branch validation | Verify logic and integrated build state |
| Component tests | Scoped to changed components | May run in regression suite | Verify component boundaries |
| Integration tests | Selective, using ephemeral setup | Usually expanded scope | Verify real interactions among components |
| Contract tests | Can check affected contracts | Verify integrated producer/consumer | Prevent API or message incompatibility |
| End-to-end tests | Selective for critical paths | Run on integrated state or target env | Verify cross-system business flows |
| Security scans | Scan diff, secrets, and dependencies | Scan final artifact or image | Catch risks in both source and output |
| Post-deploy smoke tests | Not applicable if not deployed | Run after environment deployment | Confirm the live application is ready |

A pragmatic rule is placing low-cost, high-signal checks at the start of the pipeline. Longer-running checks execute once baseline checks pass, or in an appropriate environment. Parallelism shortens overall duration, provided jobs do not contend over shared resources or state.

Do not use execution time as the sole criterion. An end-to-end test may be slow yet protect a critical checkout flow; a security scan may take time yet remain indispensable prior to release. Determine the risk each check covers, how frequently it needs to run, and when its results must be ready.

## 6. Designing a Pipeline with Two Clear Gates

A pipeline can be divided into two primary stage groups: pre-merge change validation and post-merge state validation. Job names vary by platform, but dependency relationships should remain explicit.

~~~yaml
# Conceptual model, not syntax for any specific CI/CD platform.
pipeline:
  on_pull_request:
    jobs:
      fast_checks:
        steps:
          - checkout_pull_request
          - format_and_lint
          - static_analysis
          - unit_tests
          - build_candidate

      focused_integration:
        needs: [fast_checks]
        steps:
          - start_temporary_dependencies
          - run_affected_integration_tests
          - contract_checks

      merge_gate:
        needs: [fast_checks, focused_integration]
        condition: all_required_checks_pass

  on_push_to_shared_branch:
    jobs:
      integrated_validation:
        steps:
          - checkout_integrated_commit
          - build
          - unit_tests
          - integration_tests
          - regression_tests

      package:
        needs: [integrated_validation]
        steps:
          - create_artifact
          - calculate_digest
          - publish_artifact

      environment_validation:
        needs: [package]
        steps:
          - deploy_to_test_environment
          - smoke_tests
          - verify_running_version
~~~

The example above illustrates stage organization only. Real configurations must use the syntax and primitives of your chosen CI/CD platform.

### 6.1. The Pre-Integration Gate

The pre-integration gate should define a list of mandatory checks, surface clear statuses on the pull request, and enforce branch rules requiring those checks to pass before merging.

Key decisions to establish:

- Is peer review mandatory?
- Must the pull request stay up to date with the target branch?
- When the target branch changes, must merge candidate checks re-run?
- Which tests are blocking vs. purely informational?
- Who is authorized to grant exceptions, and where are exceptions logged?

Never allow an optional job to fail in a way that misleads reviewers into thinking a mandatory gate passed. Check names and statuses should communicate the actual conditions accurately.

### 6.2. The Post-Integration Gate

The post-integration gate validates the state of the shared branch before packaging, promoting, or releasing proceeds. Define:

- Which build and test suites must pass on the merged commit?
- Are integration tests against real services or ephemeral environments required?
- Is the artifact produced from the exact commit that passed verification?
- If checks fail, how is the shared branch handled?
- Does a failure halt the release pipeline or block artifact promotion?
- Who is accountable for investigating and restoring the branch?

If the main branch is protected, teams may enforce fast-fix, revert, or hotfix procedures when post-integration checks fail. With merge queues, pre-merge checks on merge candidates reduce the chance of introducing broken states into the shared branch, yet post-merge verification remains necessary once the real commit is created.

## 7. Managing Inputs, Artifacts, and Consistency

One reason pre- and post-integration results become hard to compare is that the two pipelines test different inputs or use different build processes.

Record at minimum:

- Pull request branch commit SHA.
- Target branch commit SHA at check time.
- Merge candidate or merge commit SHA if applicable.
- Pipeline run ID and pipeline configuration version.
- Runtime, compiler, build tool, and dependency versions.
- Test environment and dependent service versions.
- Test results, logs, and reports.
- Artifact digest if the pipeline produces an artifact.

For release workflows, build the release artifact from the integrated commit that passed post-merge gates, then promote that exact artifact through test, staging, and production. If the pre-merge pipeline also builds temporary candidate artifacts for testing, clearly separate candidate artifacts from release artifacts. Never accidentally deploy an artifact built from a pull request commit that differs from the merged commit.

When a merge queue generates and validates a merge candidate, the platform may allow reusing results if the resulting merged commit matches the exact tested inputs and environment, configuration, and dependency conditions still hold. If inputs change, prior results no longer constitute valid evidence for the new state.

## 8. Handling Check Failures

Responses to pre- and post-integration failures differ because their blast radii differ.

### 8.1. Pre-Integration Failures

When a check on a pull request fails:

1. Keep the pull request blocked from merging.
2. Surface the failing job, step, and actionable error details.
3. Determine whether the failure stems from the code change, test environment, or CI infrastructure.
4. The author updates the commit or operators fix the infrastructure.
5. Re-run required checks on the latest inputs.
6. Allow merging only once all mandatory gates pass.

Never allow merging based on a previous green run if new commits were pushed to the pull request. Check statuses must bind strictly to the current commit or merge candidate.

### 8.2. Post-Integration Failures

When a check on the shared branch fails:

1. Identify the affected integrated commit and pipeline run.
2. Halt packaging, promotion, or release steps depending on that result.
3. Notify the change owner and dependent teams.
4. Triage the failure: source defect, integration conflict, configuration, dependency, or test infrastructure.
5. Choose the right recovery action: forward fix, revert commit, hotfix, or environment repair.
6. Re-run the verification suite once state is repaired.
7. Record the outcome and root cause to improve the process.

If the shared branch feeds releases, a prolonged red state can block multiple teams. Establish clear priority conventions for restoring the shared branch, designate ownership, and set up unambiguous alerting.

Not every post-merge failure demands an immediate revert. The decision depends on impact severity, isolatability, fix time, and risk of bad releases. Regardless, the pipeline must prevent an unverified state from advancing through defined release gates.

## 9. Common Pitfalls

### Testing Only the Pull Request Branch, Not the Merge Result

A pull request can pass against an older snapshot of the target branch yet fail when combined with newer commits. Mitigate this by testing merge candidates, requiring branch updates, or using a merge queue.

### Treating Post-Merge Checks as Redundant Duplicates

Re-running the same test suite can look wasteful, yet post-merge checks verify a specific commit and configuration on the shared branch. Optimize via caching, test splitting, or conditional result reuse while ensuring evidence still reflects actual inputs.

### Cramming Every Heavy Test into Pull Requests

This slows feedback, tempts developers to bypass checks, and hurts review throughput. Tier checks by risk, parallelize, and place checks at the appropriate stage. Conversely, do not push a critical check past merge purely to speed up pull requests if doing so repeatedly breaks the shared branch.

### Running Only End-to-End Tests

End-to-end tests cover broad flows but are slow, hard to diagnose, and environment-sensitive. Combine unit, component, integration, and end-to-end tests at appropriate scopes.

### Ignoring Flaky Tests

Tests that randomly pass and fail erode trust in quality gates. Track flake frequency, preserve evidence, assign owners, and fix root causes. Automatic retries can aid short-term triage, yet flaky failures must never become an accepted permanent norm.

### Exposing Production Secrets in Pull Request Pipelines

Code from pull requests—especially from forks or untrusted sources—can execute arbitrary commands during build/test steps. Never provide production deployment secrets to those jobs. Enforce least privilege, environment-scoped secrets, and short-lived credentials when supported.

### Failing to Bind Check Results to Commits

A green checkmark means nothing without knowing which commit it tested. Every result must tie to a concrete commit SHA or merge candidate. Whenever inputs change, prior status must be invalidated for the new state.

## 10. Illustrative Scenario: Two Pull Requests Modifying the Same Contract

Suppose a team maintains an order service and a payment service. Two pull requests are developed concurrently:

- Pull request A changes a data field in the payment request payload.
- Pull request B updates the consumer to read the new field.

Each pull request can run its own unit tests and build. If A tests against an older consumer mock or B tests against an older producer mock, both may pass in isolation depending on how dependencies are stubbed. When both changes integrate out of order—or only one merges—compatibility errors arise.

A suitable verification flow looks like this:

1. Pre-integration, pull request A runs linting, unit tests, contract tests for the new schema, and compatibility checks against current consumers.
2. Pre-integration, pull request B runs unit tests, contract tests, and verifies the consumer handles data per the agreed contract.
3. If the two pull requests depend on each other, the team uses a merge queue or a temporary integration branch to validate the combined changes.
4. Post-merge, the pipeline runs integration tests between producer and consumer on the shared state.
5. Regression suites verify end-to-end order creation and payment flows.
6. If everything passes, the pipeline packages the artifact, deploys to the test environment, and runs smoke tests.

This scenario demonstrates that testing changes individually cannot replace post-integration interaction testing. At the same time, pre-merge contract tests catch incompatible changes before they pollute the shared branch.

## 11. Measuring Effectiveness Across Both Layers

To improve pipelines, measure both feedback speed and defect detection capability. Useful metrics include:

| Metric | Meaning | How to Use |
|---|---|---|
| Pull request feedback time | Time from PR open/update until required results arrive | Identify jobs slowing the review loop |
| PR revision rate due to check failures | Share of defects caught prior to merge | Categorize recurring bugs and improve guidance |
| Post-merge pipeline failure rate | Stability of the integrated state | Spot interaction bugs or gaps in pre-merge checks |
| Shared branch recovery time | Time from failure detection to restored integrated state | Evaluate incident response workflow |
| Flaky test rate | Reliability of test suites | Prioritize fixing tests eroding confidence |
| Defect escape rate | Bugs caught only in later environments or by users | Identify testing coverage gaps |
| Merge-to-artifact-ready time | Latency from integration to releasable output | Optimize post-integration stages |

Never optimize a single metric in isolation. Cutting pull request time by stripping checks can spike post-merge failures. Conversely, piling on checks without watching speed and reliability tempts teams to bypass the pipeline. The goal is choosing a check set that catches key risks at sustainable cost and turnaround.

## 12. Hands-On Practice Path

You can practice these concepts in a sample repository following these steps:

1. **Define the integration point:** select the shared branch, pull request rules, and pipeline trigger events.
2. **Create pre-integration checks:** add formatting, linting, static analysis, unit tests, and a candidate build.
3. **Attach a pull request gate:** configure required status checks and intentionally push a breaking change to confirm merging is blocked.
4. **Test merge candidates:** create two independent feature branches, advance the target branch, and verify the pipeline catches conflicts or combined failures.
5. **Create the post-merge pipeline:** trigger on commits to the shared branch, running build and integration test suites.
6. **Add system checks:** run contract tests, regression tests, or end-to-end tests in an appropriate environment.
7. **Manage artifacts:** build an artifact from the integrated commit, store its digest and metadata, and deploy that artifact to the test environment.
8. **Exercise the failure path:** introduce a bug that manifests only when two components interact, confirming the post-merge pipeline blocks release progression.
9. **Verify traceability:** starting from pipeline output, trace back to the commit, test reports, artifact, and verified environment.

### Completion Criteria

Learners can consider this practice complete when they can demonstrate:

- Explaining the purpose and timing of pre-integration vs. post-integration checks.
- Distinguishing pull request commits, merge candidates, and integrated commits.
- Selecting checks appropriate to each stage's risk profile and feedback target.
- Configuring mandatory pre-merge gates.
- Running checks on the actual integrated source state post-merge.
- Explaining why a passing pull request can still break the post-merge pipeline.
- Handling pre-merge and post-merge failures according to their blast radius.
- Linking check outcomes to the relevant commit, pipeline run, and artifact.

## Conclusion

Pre-integration checks protect the shared branch by evaluating changes while they are still proposals. Post-integration checks protect the shared state by verifying merged changes work together. Both layers can share test types, yet must keep inputs, objectives, pass criteria, and supported decisions distinct.

A solid software delivery flow delivers fast feedback to pull requests, validates the actual merged state, records commit-linked evidence, and proceeds to packaging or release only when required gates pass. Organizing both verification layers this way reduces broken commits on the shared branch, speeds up root-cause investigation, and maintains end-to-end traceability from source changes to deployed artifacts.

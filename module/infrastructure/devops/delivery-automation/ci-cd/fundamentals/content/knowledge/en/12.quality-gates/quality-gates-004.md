# Distinguishing Required Checks from Advisory Results

A CI/CD pipeline can produce many outputs: build pass/fail, unit tests, coverage, source analysis, vulnerability scans, license checks, API quality checks, and performance reports. If every output is treated as a merge blocker, teams get stuck over minor warnings or reports unrelated to their change. Conversely, if every check is purely informational, severe defects can pass the integration gate and reach release environments.

A **quality gate** is the set of conditions used to decide whether a change may advance to the next step. Within that gate, distinguish clearly between:

- **Required check:** must pass per policy before merging, releasing, or deploying.
- **Advisory result:** provides information for the team to review and improve, without blocking the workflow by itself.

This classification must be published in advance, tied to a control objective, and assigned an owner. A red result does not automatically mean a mandatory block; a green result does not prove every risk has been eliminated.

## 1. Where do quality gates sit in the CI/CD flow?

A change typically passes through multiple decision points:

1. **Pre-merge:** verify the change builds, passes tests, and satisfies policies needed to enter the shared branch.
2. **Post-merge:** verify main branch health, produce artifacts, and check integrated build conditions.
3. **Pre-release:** verify version, dependencies, security, licenses, signatures, and artifact provenance evidence.
4. **Pre-production deploy:** verify approvals, target environment, rollout plan, and operational readiness conditions.
5. **Post-deploy:** check health, smoke tests, telemetry, and conditions to continue or roll back.

A check can be required at one point yet advisory at another. For example, a repository-wide coverage report might track trends on each pull request while new-code coverage is a mandatory pre-merge condition. Likewise, a security scan on a development branch might only warn on a low-severity vulnerability covered by a time-bound waiver, whereas a leaked secret or critical vulnerability blocks release.

### Distinguishing check, gate, and decision

- **Check:** a specific verification, such as `unit-tests`, `dependency-scan`, or `license-audit`.
- **Gate:** a collection of checks and the rules that evaluate them.
- **Decision:** the conclusion permitting or denying progression—for example, ready to merge, needs fixes, or requires exception approval.

A gate can contain multiple checks: required checks, advisory checks, and conditional checks that apply only when specific criteria hold. Do not equate a CI job name with the entire quality policy.

## 2. What is a required check?

A check is required when its outcome is a prerequisite for permitting a critical action. If the check fails, has not completed, or lacks valid evidence, the action must be held per policy.

Checks commonly designated as required include:

| Check category | Examples | Why it may be required |
|---|---|---|
| Build | Compilation and packaging succeed | Prevents merging code that cannot produce a runnable version |
| Core tests | Unit tests and critical integration tests | Detects behavioral regressions on core paths |
| Types and structure | Type checking, schema validation, API contracts | Preserves contracts between components |
| Critical security | Secret scans, vulnerabilities above policy thresholds | Prevents credential leaks or unacceptable risk |
| Dependencies and licenses | Prohibited dependencies or disallowed licenses | Enforces supply-chain and legal compliance |
| Artifacts | Valid digest, signature, or provenance | Ensures artifacts are traceable and trusted |
| Approvals | Owner review or production approval | Ensures changes have human accountability |

This list is not a universal default for every project. Teams must select checks based on risk, architecture, compliance requirements, and controllability. A slow test may move to a later stage if not needed for merge decisions, but must never be dropped if it is the sole control protecting a major risk.

### Criteria for a good required check

A required check should have:

- A clear objective and scope.
- A deterministic outcome: passed, failed, or inconclusive.
- Logs and evidence for investigation.
- An accountable owner when it fails.
- A feedback time suited to the blocking point.
- Handling for infrastructure or external-service failures.
- Execution against the exact commit, merge result, or artifact under verification.

If a check fails frequently due to flaky tests, unstable configuration, or unreliable external services, it can stall the entire flow. Teams must fix the root cause and establish clear handling rather than downgrading the check to advisory just to keep the pipeline green.

## 3. What is an advisory result?

Advisory results help teams observe trends, detect risks early, or supply context for human decisions. They do not automatically block merges or releases.

Examples:

| Result | Advisory usage |
|---|---|
| Overall coverage | Track test quality trends across versions |
| Low-severity maintainability or code smells | Build improvement backlog, assess per module |
| Low-severity vulnerabilities with a remediation plan | Log, assign owner, and set due date |
| Performance benchmarks without stable thresholds | Observe trends before setting blocking limits |
| Artifact size report | Watch bundle size and growth trends |
| Experimental tests or unstabilized checks | Gather data to assess reliability |
| Supplemental architecture analysis | Assist code review without replacing mandatory contract checks |

Advisory does not mean ignorable forever. Every important advisory result should have an owner, a priority, and a path to becoming required once the tool is sufficiently reliable. If warnings go unread, unaddressed, and untracked, they only add noise to the pipeline.

### Warnings and errors are different kinds of signals

A tool may report warnings while exiting with code 0, or fail with an error because it could not reach an analysis service. Distinguish:

- Policy-violating findings.
- Risk findings needing review.
- Tool execution failure or missing evidence.
- Checks skipped because applicability conditions were not met.

Do not collapse everything into a single green badge or success line without preserving details. Aggregate statuses must link to reports showing what was actually verified.

## 4. Required vs. advisory matrix

Before configuring CI, build a matrix per stage:

| Check | Pre-merge | Pre-release | Post-deploy | Suggested classification |
|---|---|---|---|---|
| Compile/build | Required | Required if artifact is rebuilt | Not applicable | Required |
| Core unit tests | Required | May rerun on matching build/artifact | Not applicable | Required |
| Integration/contract tests | Required for affected contracts | Required if risk warrants | Possible smoke tests | Scoped required |
| Coverage report | Report; may enforce threshold on new code | Track trends | Not applicable | Advisory or threshold-required |
| Secret scan | Required | Required on release artifact/source | Not applicable | Required |
| Vulnerability scan | Block per policy threshold | Required per release policy | Monitor as needed | Mix of required/advisory |
| License report | Block prohibited licenses | Required before distribution | Not applicable | Policy-required |
| Artifact signature/provenance | May not be needed yet | Required | Verify deployed artifact | Required |
| Benchmark | Trend reporting | Required if explicit performance SLO exists | Telemetry monitoring | Usually advisory; required with SLO |
| Smoke test/health | Not applicable | Can run on staging | Required before completing rollout | Required |

The matrix should state applicability rules explicitly. For instance, API schema checks need to run only when changes touch schemas; license checks apply to new dependencies or dependency-graph changes; benchmarks might run only on the main branch or pre-release.

A solid policy specifies both run conditions and skip conditions. When a check does not apply, the system must record `skipped` or `not applicable` with a reason. Never interpret not running as having passed.

## 5. Interpreting check statuses accurately

CI platforms use different status names, which map to these core meanings:

| Status | Meaning | Handling for required checks |
|---|---|---|
| Success / Passed | Executed and met criteria | Can pass the gate |
| Failure / Failed | Executed and violated criteria | Block next step |
| Pending / In progress | No final conclusion yet | Wait for result; do not treat as passed |
| Error / Infrastructure failure | Tool or infra could not verify | Hold gate until retry or policy decision |
| Skipped / Not applicable | Did not run because condition did not apply | Accept only if gate rules permit and reason is valid |
| Cancelled | Canceled before a final result | Never treat as pass; rerun or handle per policy |
| Neutral / Informational | Result yields no standard pass/fail verdict | Explicitly define whether it satisfies the required condition |

**Never equate skipped with passed.** A check may be skipped due to path filters, job conditions, or misconfiguration. If it is a required check, ensure skipping is explicitly permitted by policy—for example, when the change does not touch that component and an aggregator check still reports the accurate outcome.

Similarly, an infrastructure failure does not prove the source code is broken, nor is it proof the code is safe. For required checks, an inconclusive status should normally hold the gate until a valid run completes or an approved exception is recorded.

### Preventing required checks from hanging

Some platforms leave a required check in `pending` forever if a workflow is completely skipped by branch or path filters. This blocks merges even though no job failed. When configuring filters, verify how your platform emits check runs and final statuses.

A common pattern is an always-running aggregator check that collects child job statuses and concludes clearly:

- Pass if all applicable required checks pass.
- Pass per policy if checks are legitimately not applicable.
- Fail if any required check fails.
- Inconclusive if a required check did not run or lacks valid evidence.

The aggregator check must verify that results belong to the exact commit or merge group. Never accept a stale status from a previous commit.

## 6. Configuring required checks in GitHub Actions

Workflows define jobs and emitted checks; branch protection policies or repository rulesets decide which checks are required before merging. Merely naming a job in YAML does not make it a required check.

Example workflow with one required check job and one advisory report job:

~~~yaml
name: Pull request quality

on:
  pull_request:
    branches:
      - main

jobs:
  required-validation:
    name: required-validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./gradlew clean check

  advisory-report:
    name: advisory-report
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - name: Generate advisory report
        run: ./gradlew qualityReport
~~~

In the repository, configure branch protection or a ruleset to require the `required-validation` check. The `advisory-report` check provides information without appearing in the required list. `continue-on-error` illustrates how a job can avoid failing the workflow; it does not replace classifying checks in repository policy.

Required check names must stay stable. When renaming a workflow or job, update branch protection rules accordingly and verify the new status. If multiple workflows emit checks with the same name, results become ambiguous; name checks clearly by purpose and origin.

### Notes on required checks and path filters

If a workflow is skipped at the workflow level due to branch/path filters, the platform may never create a final check result, leaving the required check pending. For required checks, consider:

- Always triggering the workflow and placing conditions at the job level.
- Using an always-running aggregator check to conclude when a check group is not applicable.
- Ensuring every conditional branch emits a check result with a stable name.
- Testing on pull requests that modify only docs, source code, or build configs.

Do not use path filters in ways that accidentally bypass security or dependency checks whose scope extends beyond the source directory.

## 7. Configuring allow_failure in GitLab CI

GitLab CI distinguishes pipeline-blocking jobs from jobs that can fail without halting the pipeline via `allow_failure`.

~~~yaml
stages:
  - validate
  - report

required-tests:
  stage: validate
  script:
    - ./gradlew clean check
  allow_failure: false

advisory-quality-report:
  stage: report
  script:
    - ./gradlew qualityReport
  allow_failure: true
~~~

In this example, `required-tests` blocks the pipeline upon failure. `advisory-quality-report` can fail while the pipeline still registers as successful, though its output must still be visible and tracked. Also check merge request approval rules, protected branches, and related policies to ensure merge eligibility matches project requirements.

`allow_failure` should not be used to soften every unstable job. When a critical check fails frequently, address its reliability or build controlled retry/exception mechanisms.

## 8. Setting thresholds for quality gates

Some tools return numeric scores or finding counts. Turning them into gates requires explicit thresholds:

- Coverage is not below the minimum for newly added code.
- Zero critical or high vulnerabilities within policy scope.
- Zero detected secrets.
- Zero dependencies using prohibited licenses.
- Zero contract or schema compatibility errors.
- Artifacts carry valid signatures and provenance prior to release.

Do not pick thresholds simply because a tool supports them. Thresholds must reflect risk and rely on dependable measurements.

### Coverage

Overall coverage can be dominated by legacy code and fail to reflect the quality of the current change. One approach is tracking coverage on new or modified code while monitoring overall trends. When setting a required threshold, define:

- Tool and coverage calculation method.
- Code scope included and excluded.
- Minimum threshold.
- Handling for generated code, test fixtures, and untestable code.
- Rule when coverage reports fail to generate.

Never treat a missing report as 100% coverage or let it pass the gate automatically.

### Security findings

Security thresholds should account for severity, exploitability, exposure, application reachability, and organizational policy. Not every dependency vulnerability carries equal real-world risk, yet every assessment must be evidence-based and recorded.

A policy can block secret leaks and threshold-breaching vulnerabilities while logging lower findings as advisories with owners and deadlines. Avoid relying on a single CVSS number for the entire decision when your organization has exploitability or reachability data.

### Performance and artifact size

Benchmarks are often noisy due to runners, system load, and input data. Before enforcing a gate, establish a stable baseline, adequate iterations, and meaningful thresholds. A 1% regression alert on an unstable benchmark may be noise; a reliably measured SLO breach may need to block release.

For artifact size, define file types, measurement methods, and limits. A warning when a JAR grows may be advisory; exceeding an image deployment quota or distribution policy may be required.

## 9. Exceptions to required checks

In practice, teams sometimes must merge or release even when a check has not passed—for example:

- A production incident needing an urgent hotfix.
- An external scanning service outage.
- A confirmed false positive backed by evidence.
- A flaky test under investigation when the change does not touch that area.
- A special business requirement with an explicit deadline.

Exceptions must not turn a required check into a permanent advisory. An exception workflow should include:

1. **Specific justification:** which check did not pass and why progression is still necessary.
2. **Scope:** repository, commit, artifact, environment, and permitted action.
3. **Approver:** risk owner or delegated authority.
4. **Expiration:** exact deadline or re-evaluation trigger.
5. **Mitigation:** rollout limits, feature flags, enhanced monitoring, or rollback plan.
6. **Audit trail:** requester, approver, timestamp, evidence, and outcome.
7. **Post-exception follow-up:** verify the risk was resolved and close the exception.

Do not allow change authors to self-approve exceptions for their own changes when policy requires separation of duties. For critical vulnerabilities or secrets, organizational policy may prohibit exceptions entirely.

### Separating tool errors from quality failures

If a scanner fails to start because an external service is unreachable, that is a verification failure, not a clean scan. If the tool completes and detects a violation, that is a policy failure. Both cases demand different handling:

- Tool error: bounded retry, fallback source, or policy-governed exception approval.
- Quality failure: fix the root cause, update dependencies, or submit false-positive evidence for review.

Never flip a failed tool status to `passed` just to unblock the pipeline.

## 10. Ensuring gates evaluate the right target

A result is valid only when bound to the exact input under evaluation. Pre-merge, the target may be the head commit or merge result; pre-release, the artifact digest; pre-deploy, the specific version and target environment.

A gate should record:

- Repository and branch/ref.
- Commit SHA or merge group ID.
- Workflow, job, and check name.
- Tool version and policy configuration.
- Artifact digest if checking an artifact.
- Target environment if checking a deployment.
- Execution timestamp and final result.
- Reports or links to evidence.

Never use a green check from an older commit to allow merging a new commit. Never use one artifact's scan report to prove a different artifact is safe. If an artifact is built once and promoted through staging to production, verify its digest to ensure the exact same artifact is deployed.

### Controlling ordering and result freshness

When a pull request receives new commits, checks from older commits become stale. Merge queues can also generate new merge results after the target branch advances. Systems must ensure required checks apply to the exact state being merged.

If a check was canceled or is still running, never treat a prior run's result as valid for the new commit. When using concurrency controls to cancel superseded runs, aggregator checks must wait for the newest run or report an inconclusive status.

## 11. Designing reports so readers grasp criticality

A good results UI should distinguish clearly:

- **Blocking:** a required check failed; the next action is blocked.
- **Passed:** required checks passed.
- **Pending:** no conclusion yet; waiting.
- **Advisory:** warnings or informational findings to review, non-blocking.
- **Not applicable:** check omitted per defined applicability rules.
- **Infrastructure error:** check could not complete due to tool or environment issues.

Do not show only a total error count. Readers need to know which check is a blocker, which is advisory, who owns it, and what to do next. Links to logs and reports must point to the exact run and commit.

Example summary report:

~~~text
Pull request: #248
Commit: 9f3a2c1

Required
  Build                 PASSED
  Unit tests            PASSED
  API contract          PASSED
  Secret scan           PASSED
  Dependency policy     FAILED

Advisory
  Coverage trend        78.4% (informational)
  Maintainability       3 low-priority findings
  Benchmark             +1.2% (below alert threshold)

Decision: BLOCKED
Reason: Dependency policy has an unresolved required finding.
Owner: Platform security
~~~

This example illustrates presentation format. Real values must come from the corresponding run; never use placeholder numbers to make merge decisions.

## 12. Governing quality gate policies

Quality gates evolve alongside architecture, risk levels, and tooling. Manage gate policies as part of the delivery system:

### Clear ownership

Each required check needs a team or role accountable for:

- Pass criteria and thresholds.
- Tool configuration.
- Response times and failure support.
- False-positive triage.
- Tool upgrades and compatibility maintenance.
- Exception workflows.

Never leave a required check without an owner. When it breaks, the team will not know who has authority to resolve it.

### Reviewing policy changes

Downgrading a check from required to advisory weakens pipeline protection. Upgrading one can lengthen merge times and impact developer productivity. Therefore, policy changes should include:

- Rationale and risk addressed.
- Applicable repositories and branches.
- Impact on existing checks.
- How it will be tested before broad rollout.
- Reviewers and approvers.
- Communication plan and post-change monitoring.

### Monitoring the health of the gate itself

Gates should also be measured:

| Metric | Question |
|---|---|
| Required check failure rate | Are required checks failing due to real bugs or tooling failures? |
| Time to green | How long does a change take to pass all required checks? |
| Flaky rate | Does a check return varying outcomes for the same input? |
| Advisory finding age | How long do advisory warnings sit unaddressed? |
| Exception frequency | How often must the gate be bypassed? |
| False positive rate | Does the tool generate excessive inaccurate findings? |
| Gate bypass count | How many times was policy overridden and why? |
| Missing/pending checks | Are required checks failing to emit results? |

If exception rates climb steadily, thresholds may be too strict, tools unstable, or workflows misaligned. Never lower standards merely to make metrics look good; investigate root causes and adjust with evidence.

## 13. Common mistakes

### Making every check required

Pipelines slow down and get blocked by low-value reports. Select required checks by risk and decision point; keep trend metrics advisory.

### Leaving every check advisory

Build failures, core test regressions, secret leaks, or serious policy violations can slip past merge and release. Define minimum conditions that must pass before advancing.

### Treating unexecuted checks as passed

A job skipped due to path filters or faulty conditions does not prove quality was verified. Record `not applicable` explicitly and have an aggregator check evaluate that state.

### Relying solely on an overall green badge

A green pipeline may hide failed advisory jobs or required jobs that never evaluated the latest commit. Surface individual check statuses and evidence.

### Granting open-ended exceptions

A permanently waived warning turns into a policy loophole. Exceptions require scope, approver, expiration, and mitigations.

### Reusing stale results for new commits or artifacts

Checks must bind to the exact SHA, merge group, or artifact digest. Old results must never apply automatically to changed inputs.

### Downgrading controls when tools are unstable

When a scanner or test is flaky, turning it advisory removes protection without fixing the root cause. Separate infrastructure errors from quality failures and improve reliability.

## 14. Quality gate design checklist

- [ ] Every check has a clear objective and applicable stage.
- [ ] Required vs. advisory classifications are openly documented.
- [ ] Required checks have pass criteria, owners, and retained evidence.
- [ ] Checks bind to the exact commit, merge result, or artifact digest.
- [ ] Pending, failed, skipped, cancelled, and infrastructure error states are handled distinctly.
- [ ] Non-applicable checks state a rationale and are never mistaken for passing runs.
- [ ] Path filters and job conditions never silently drop required checks.
- [ ] Advisory results still have owners and remediation timelines when warranted.
- [ ] Exceptions record approver, scope, expiration, and audit trail.
- [ ] Policy changes undergo review and are tracked via metrics.
- [ ] A green pipeline never masks skipped required checks or stale-input evaluations.

Distinguishing required checks from advisory results helps CI/CD balance speed with assurance. Required checks enforce non-negotiable conditions before advancing; advisory results give teams improvement signals without stalling delivery over minor warnings. With explicit policies, exact input binding, and transparent exception handling, teams can make consistent, traceable merge and release decisions.

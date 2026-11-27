# Keeping the Main Branch Releasable

In CI/CD, the main branch (typically named `main`, sometimes still `master`) is the reliable integration point of the product. The principle of **keeping the main branch in a releasable state** requires that every change introduced into this branch go through a repeatable, evidence-backed verification process fast enough for the team to catch issues before they accumulate.

A releasable main branch does not mean the software has zero bugs, that every feature is turned on, or that every commit must go straight to production. It means the team can take a version built from the main branch, deploy it following a defined process, verify its behavior, and release it in a controlled manner. Unready features can stay behind a feature flag; changes that do not meet standards must stay off the main branch.

This is a foundational principle of **DEVOPS_CI_CD_FUNDAMENTALS**: connecting Git events to pipeline-as-code, automated builds and tests, artifact and environment management, applying quality gates, protecting secrets, maintaining traceability, post-deployment verification, and preparing rollback capability.

## 1. Why Must the Main Branch Always Be Releasable?

The main branch is where changes from many contributors converge. If feature branches live too long, the differences between them grow larger. When merging, the team must resolve source code conflicts, API contract differences, data schema changes, and diverged assumptions. Integration bugs often surface only when multiple changes are combined, making root-cause analysis harder.

Keeping the main branch releasable reduces risk in four ways:

- **Early detection:** checks run as soon as a pull request (PR) is opened or updated, while the change scope is small and the author still clearly remembers the intent.
- **Smaller batch sizes:** short-lived branches and small PRs encourage frequent integration, reducing conflicts and shortening feedback loops.
- **Bounded incident scope:** each merge introduces a traceable amount of change. When the pipeline turns red, the team can focus on the most recent commit or PR.
- **Preserved release optionality:** the team can deploy a verified build at the right time, enable features for specific user groups, or fall back to the last known good artifact.

This principle shifts the focus from "is the feature finished?" to "is this change safely integrated and ready to be included in a release?". A feature can be in progress while the main branch still remains functional.

## 2. Distinguishing Integration, Deployment, and Release

Three concepts are often conflated:

| Concept | Meaning | Example |
| --- | --- | --- |
| Integration | Bringing changes into the shared codebase after passing mandatory checks | Merging a PR into main |
| Deployment | Installing an artifact into an environment so it can run | Rolling out an image with a specific digest to staging |
| Release | Making a version or feature available to users according to product policy | Turning on a feature flag for 10% of users and then expanding |

A commit on `main` may be integrated without yet being deployed to production. An artifact may be deployed to staging without yet being released to users. Separating these concepts allows the team to integrate continuously without being forced to expose every feature immediately.

**Releasable** is a technical and operational state: the artifact is built from an identified source revision, required quality gates have passed, environment configuration is managed, the deployment process can be executed, and there is a way to verify or roll back. This is a far more practical standard than claiming "the build succeeded".

## 3. Git Workflow Rules to Reduce Integration Risk

### 3.1. Keep Working Branches Short-Lived and Changes Small

Feature branches should be created from the latest version of the main branch and exist for a short time. Break work into small PRs, with each PR addressing one purpose that can be described and reviewed independently. Small PRs help reviewers understand intent, assess impact, and spot defects faster.

For example, instead of keeping a branch open for weeks to finish an entire payment flow, the team can merge compatible pieces incrementally: add data types, add an unexposed endpoint, add background processing, and then enable the feature with a feature flag after verification. At every step, the version on `main` must still compile, pass tests, and run.

Before opening a PR, update the working branch from the main branch according to team conventions. Either rebase or merge can be used to sync; what matters is resolving conflicts on the working branch and re-running checks after the content changes. Never treat CI results from an older commit as evidence for a newer commit.

### 3.2. Use PRs as Change Control Checkpoints

A PR should provide enough information for others to evaluate:

- Goal and before/after behavior of the change.
- Impact scope: APIs, data, configuration, access permissions, infrastructure, and dependent services.
- How it was tested, test results, and any untested scenarios.
- How to enable/disable the feature, deploy, monitor, and roll back when the change has operational impact.

Reviewers check correctness, maintainability, backward compatibility, security risks, and architectural fit. For sensitive areas, CODEOWNERS rules or equivalent mechanisms can require approval from subject-matter owners.

Do not merge just because one approval was granted. Checks must apply to the exact commit intended for merge. If the author updates code after approval, the team should require re-approval per policy and re-run affected checks.

### 3.3. Protect the Main Branch with Enforceable Policies

Written conventions only work when the Git platform enforces them. Branch protection settings should consider:

- Allowing changes only through PRs or a merge queue.
- Requiring an appropriate number of approvals and code-owner approval for critical areas.
- Requiring mandatory status checks to succeed on the latest commit.
- Dismissing stale approvals when new changes are pushed, if policy requires it.
- Blocking force pushes and deletion of the main branch.
- Restricting bypass permissions; any exception must have an accountable person and an audit trail.
- Using a merge queue when many PRs frequently compete to merge, to test commit combinations close to the state that will enter the main branch.

Configuration names and options differ across GitHub, GitLab, Bitbucket, and self-hosted Git servers. Choose the equivalent mechanism on your platform, then verify with a test PR that the branch actually blocks merging when a required check fails.

Not every team needs the exact same rules. For example, requiring two approvals for every documentation change might slow the team down without reducing risk proportionally. Classify areas by impact level and set proportional policies, while never bypassing mandatory technical checks.

## 4. Designing Pipelines to Safeguard Main Branch Quality

The pipeline needs to give early feedback on PRs and re-verify the integrated state on the main branch. Pipelines are stored as code and versioned alongside the product so anyone can see who changed the workflow, when it changed, and which builds were affected.

### 4.1. Run Checks on the Exact Commit

Git events that commonly trigger pipelines:

| Event | Verification Objective |
| --- | --- |
| Open or update PR | Verify the content intended to be merged; give fast feedback to the author |
| Push to main branch | Confirm post-integration state and produce a traceable artifact |
| Create tag or release request | Identify the release version and apply corresponding release gates |

The pipeline must check out the exact commit SHA being verified. Do not use a moving reference like `latest` to identify the source code for a build. CI results are bound to a specific commit; when the commit changes, previous evidence is no longer sufficient to allow merging.

### 4.2. Order Checks by Speed and Risk Level

A practical check sequence might include:

1. **Structure and style checks:** formatting, linting, naming rules, configuration validation.
2. **Compilation and type checking:** catching syntax errors, type mismatches, and invalid dependencies.
3. **Unit tests:** verifying small functions and components with controlled data.
4. **Integration and contract tests:** checking interactions across components, services, databases, and API contracts.
5. **System or critical flow checks:** verifying end-to-end behavior in an environment close to production.
6. **Security and dependency checks:** detecting exposed secrets, vulnerabilities in dependencies, source code, or images; enforcing license policies where needed.
7. **Artifact and deployment configuration checks:** confirming output packages, manifests, migrations, and configurations meet environment requirements.

It is not necessary to run every heavy check on every code save. Fast checks can run first for early feedback, followed by deeper integration, security, or performance checks depending on the change and risk level. However, checks required to protect the main branch must be executed before merging or before allowing a release per policy.

Tests are only valuable when they are reliable. Test environments need controlled data and dependencies; tests should be independent, deterministic, and clean up resources after running. Flaky tests erode confidence in the pipeline. When discovered, record an owner, root cause, and resolution deadline; if temporary quarantine is unavoidable, put an alternative control in place so that risk remains covered. Do not turn "re-run until green" into a way of ignoring failures.

### 4.3. Define Clear Quality Gates

A quality gate is a set of conditions a change or artifact must meet before advancing. Examples:

- Build and mandatory test suites succeed.
- No secrets are detected in the changes.
- No policy-blocking severity vulnerabilities exist.
- Migrations can run in the designed deployment sequence.
- Contract and API compatibility checks pass.
- The artifact is built, stored, and identified by digest.

Each gate needs an owner, scope of application, data source, pass/fail criteria, and exception handling process. Criteria must be automatically verifiable at an appropriate level. Writing only "code must be good" or "no critical bugs" without defining detection sources and thresholds makes the gate hard to enforce consistently.

Do not set a single test coverage threshold as a proxy for quality. High coverage can still miss critical behavior; low coverage in a high-risk area can signal the need for more tests. Combine coverage with business flow tests, contract checks, security analysis, and change reviews.

### 4.4. Example Pipeline-as-Code Flow

The snippet below is platform-agnostic. Key names and syntax should be adapted to the CI system in use:

~~~yaml
pipeline:
  on:
    - pull_request
    - push_to_main

  jobs:
    validate:
      steps:
        - checkout: exact_commit_sha
        - install: locked_dependencies
        - run: format_check
        - run: lint
        - run: compile
        - run: unit_tests
        - run: integration_and_contract_tests
        - run: secret_and_dependency_scans

    build:
      needs: [validate]
      only: push_to_main
      steps:
        - build: application
        - package: immutable_artifact
        - calculate: artifact_digest
        - publish: artifact_and_provenance

    verify_staging:
      needs: [build]
      steps:
        - deploy: artifact_by_digest
        - run: smoke_tests
        - verify: health_and_critical_flows

    release:
      needs: [verify_staging]
      when: release_policy_allows
      steps:
        - promote: same_artifact_digest
        - verify: production_health
        - rollback: last_known_good_artifact_if_needed
~~~

This example illustrates three key points: verifying PRs on a specific commit; building artifacts only after required checks pass; and deploying the exact same verified artifact across environments. Real pipelines may split jobs, add manual approvals, or roll out by traffic percentage depending on service requirements.

## 5. Build Once, Manage Immutable Artifacts

A common design mistake is rebuilding source code in each environment. If staging and production are built independently, they may receive different artifacts due to changing dependencies, build timestamps, environment variables baked into packages, or inconsistent build tools. In that case, staging running well does not prove the production artifact will run well.

The rule to follow is **build once and promote the same artifact**:

1. The pipeline fetches source code at a specific commit SHA.
2. Dependencies are version-locked and built in a reproducible environment.
3. The pipeline produces an artifact, such as a JAR, package, or container image.
4. The artifact is stored in a registry or artifact repository with access control.
5. The system records the digest, commit SHA, build ID, and provenance information.
6. Staging and production receive the same artifact by digest; environment configuration is supplied separately.

An immutable artifact means published content is never overwritten under the same identifier. Human-readable tags like `1.8.0` are helpful for people, but the content digest is the authoritative identifier for an image or package. If a new build produces different content, it must have a new identifier.

Metadata should link an artifact to:

- Commit SHA and source branch.
- Build ID, tool versions, and critical dependencies.
- Test results and quality gates passed.
- Digest, SBOM (Software Bill of Materials), and provenance if required by process.
- Person or workflow that approved the release.
- Environment, deployment timestamp, and verification results.

As a result, during an incident, the team can answer: which artifact is production running, which commit built it, which checks ran, and what previous artifact can be restored.

## 6. Keep Incomplete Features Out of the User Experience

A team may need to merge code early to avoid long-lived branches, even when the feature is not ready for users. Feature flags separate **code deployment** from **feature activation**:

- New code is integrated, but the flag defaults to off.
- Only internal users or test groups are allowed to turn it on.
- Once sufficient evidence is gathered, gradually expand usage scope.
- If a bug occurs, turn off the flag to reduce impact while the team investigates.

Feature flags need an owner, description, default value, targeting rules, and a review or removal deadline. Long-lived flags can create many behavioral branches and increase testing cost. Do not use feature flags to hide a breaking compatibility change or to bypass security checks.

For APIs and data, design for compatibility during the transition phase. For example, when renaming an API field, you can roll it out in sequence: add the new field while still reading the old field; update clients; observe usage of the old field; and only then remove the old field in a separate change. This lets old and new versions coexist during rollout.

For databases, the **expand–migrate–contract** strategy typically reduces risk:

1. **Expand:** add new tables or columns in a way that does not break the current application.
2. **Migrate:** backfill data in batches that are safe to re-run and monitor progress.
3. **Switch:** deploy the application reading/writing the new structure, with verification steps.
4. **Contract:** remove the old structure only after confirming no application version still depends on it.

Destructive or irreversible migrations need separate review. Rolling back an application does not automatically restore transformed data; therefore, you must have a compatibility plan, backups, and a tested recovery procedure.

## 7. Managing Environments, Secrets, and Deployment Permissions

Releasability depends on the runtime environment. Development, test, staging, and production environments should have clearly managed purposes, access controls, and configurations. Staging needs to resemble production closely enough to catch issues with connectivity, permissions, migrations, and configuration, but sensitive data must never be copied arbitrarily.

Keep configuration separate from the artifact. The same artifact can receive different endpoints, resource limits, or feature flags per environment via a controlled configuration mechanism. Never embed passwords, tokens, or private keys in source code, images, or logs.

Pipelines should follow the principle of least privilege:

- Grant read or write access to registries, environments, and repositories only when a job genuinely needs it.
- Prefer short-lived credentials or OIDC federation between CI and the target provider over long-lived keys.
- Never expose production secrets to jobs running code from untrusted forks or PRs.
- Mask sensitive values in logs and avoid printing the entire process environment.
- Record who or which process approved and executed a deployment.

The fact that a pipeline can deploy to production does not mean every job needs production permissions. Separating build, test, and deployment permissions limits blast radius if a step is compromised or misconfigured.

## 8. Controlled Releases and Post-Deployment Verification

Passing quality gates is necessary, yet systems can still encounter errors that only appear in live environments. Before releasing, define verification signals and stop conditions. Minimum post-deployment checks should include:

- The application starts up and readiness/liveness probes pass.
- Key endpoints respond properly.
- Connections to databases, message brokers, and dependent services work.
- Core business flows can be executed.
- Error rates, latency, resource usage, and queues stay below alert thresholds.

For high-risk services, use canary or blue-green deployments. Canary sends the artifact to a small percentage of traffic first, compares metrics against a baseline, and only then expands. Blue-green maintains two equivalent environments and switches traffic once the new environment is verified. Rolling deployments replace groups of instances incrementally; ensure old and new versions can coexist during the transition.

Continue or stop conditions must be defined upfront, such as rising error rates, p95 latency exceeding thresholds, failing health checks, or disrupted checkout flows. If a stop condition triggers, the pipeline or on-call operator must have the authority to halt rollout expansion and fall back to the last known good artifact per the runbook.

Post-deployment observability should be tied to the version. Logs, metrics, traces, and deployment events should include a version or release ID so operators can compare before/after, isolate related changes, and determine blast radius.

## 9. When the Main Branch Breaks: Restoring Green State

A main branch cannot stay 100% green forever. What defines engineering discipline is how the team responds when a required check fails or a defect is discovered after merge.

The handling procedure should be clear:

1. **Stop introducing more changes into the broken area.** Pause merges if the failure breaks builds, tests, or releasability.
2. **Identify the starting point.** Find the first commit that turned the pipeline from green to red; compare logs and artifacts to narrow down the cause.
3. **Choose fix or revert.** If a fast, safe fix is possible, open a small remediation PR. If the offending change is reversible, revert it to restore a known good state.
4. **Re-run all relevant checks.** Never skip checks just to make the status indicator turn green.
5. **Verify artifacts and environments.** If the defect reached production, execute a rollback or hotfix per the runbook, then verify health and business flows.
6. **Document root cause and preventive actions.** Add tests, improve quality gates, refine the workflow, or update operational runbooks.

Example commands to revert a normal commit:

~~~bash
git revert <commit-sha>
git push origin <recovery-branch>
~~~

Then open a recovery PR according to team policy. For merge commits, identify the correct parent when reverting; do not run the command mechanically because choosing the wrong parent can produce unintended results.

Production rollbacks should redeploy a stored, known-good artifact by digest or immutable identifier. Do not rebuild old code and assume the output will be identical. If an incompatible data change occurred, rolling back the application alone may not be enough; execute the data recovery plan or a compatible hotfix.

The team should agree on one operational rule: **fix the main branch state before resuming normal work**. Letting a red pipeline linger weakens the meaning of status checks and makes new changes harder to evaluate.

## 10. Practical Example: Adding a New Endpoint

Suppose a team needs to add an order status lookup endpoint. Designing it under the releasable main branch principle looks like this:

1. The author creates a short-lived branch from `main`, adds the endpoint in an unpublished state, and writes unit tests for the business rules.
2. The PR describes the request/response contract, access permissions, error handling, and client impact. CI runs lint, compile, unit tests, contract tests, dependency checks, and secret scans.
3. Reviewers inspect authorization, compatibility with existing clients, and logging. Required status checks pass before merging.
4. After merging, the pipeline on `main` builds an image, tags it with the commit SHA and digest, and stores provenance alongside test results.
5. The pipeline deploys that exact image to staging, runs smoke tests, and tests the lookup flow using an appropriately privileged account.
6. When authorized for release, the same digest is deployed via canary. A feature flag enables it only for a pilot user group.
7. The team monitors error rate, latency, and logs by release ID. If metrics cross thresholds, stop the rollout and turn off the flag or roll back to the last known good artifact.
8. Once the flow is stable, expand the flag according to plan and schedule removal of the temporary flag code once no longer needed.

Throughout the entire process, the main branch always holds buildable, testable code; the new feature becomes available only after passing verification and release approval.

## 11. Signs That the Principle Is Not Being Practiced Well

| Sign | Risk | Improvement Direction |
| --- | --- | --- |
| Feature branches live for weeks | Higher conflict rates and integration costs | Break changes into smaller slices; merge frequently |
| Merging allowed when CI hasn't run or is failing | Main branch receives unverified code | Enable required status checks on the latest commit |
| Tests run only on local machines | Lacks consistent evidence and hard to reproduce | Move required checks into the pipeline |
| Rebuilding in staging and production | Artifacts may differ across environments | Build once, promote by digest |
| Deploying with the `latest` tag | Hard to know the exact content running | Pin immutable versions or digests |
| Secrets stored in repository or logs | Risk of leaking system access | Secret manager, OIDC, and least privilege |
| Incomplete features break existing flows | Integration becomes tightly coupled to release timing | Design for compatibility and use feature flags properly |
| Pipeline is red yet the team keeps merging | Loss of trust in quality gates | Stop merges, restore green state, and fix root cause |
| Unknown which commit production is running | Hard to investigate and roll back | Attach commit, build ID, digest, and release ID to deployments |
| Checking only deployment success, not behavior | Runtime bugs can slip through | Smoke tests, health checks, and post-deployment metric monitoring |

## 12. Metrics to Evaluate Effectiveness

Do not evaluate this principle solely by how often the pipeline is green. A pipeline can stay green because it checks too little or because the team routinely ignores failures. Combine multiple metrics:

- **Main branch pipeline success rate:** indicates integration stability; requires deeper analysis of failure causes.
- **Time to restore main branch:** time from detecting a red state to restoring a releasable state.
- **PR and branch lifetime:** review wait time, number of updates, and change size help identify integration bottlenecks.
- **Lead time for changes:** time from committing a change to running in production.
- **Change failure rate:** percentage of released changes that cause an incident requiring remediation, rollback, or hotfix.
- **Deployment frequency:** shows the ability to deliver verified changes to target environments.

Metrics must be read together. Increasing deployment frequency while change failure rate also rises may indicate quality controls are not keeping pace. Shortening pipeline time by dropping critical checks can raise future incident costs. The goal is fast feedback, evidence-backed quality, and strong recovery capability.

## 13. Adoption Checklist

Before merging a PR:

- [ ] PR is small, focused, and clearly describes impact.
- [ ] Working branch is synced with the main branch per conventions.
- [ ] Required reviews and approvals are complete.
- [ ] Required checks ran on the latest commit and all passed.
- [ ] No exposed secrets or policy-blocking vulnerabilities.
- [ ] API, data, and configuration changes are compatible with the transition phase.
- [ ] Unready features are guarded by an appropriate mechanism.

Before releasing:

- [ ] Artifact is built from an identified commit and has an immutable digest.
- [ ] Test results, provenance, and version info are traceable.
- [ ] Artifact has been verified in an appropriate environment.
- [ ] Configuration and secrets are scoped per environment with least privilege.
- [ ] Rollout continue/stop criteria, owner, and runbook are in place.
- [ ] Last known good artifact and migration handling plan (if needed) are ready.

After releasing:

- [ ] Health checks and critical business flows pass.
- [ ] Metrics, logs, and traces can be correlated with the release ID.
- [ ] Error rate, latency, and resource usage are within operational thresholds.
- [ ] Rollout is expanded or halted according to defined signals.
- [ ] Incidents and exceptions are recorded as concrete improvement actions.

## Conclusion

Keeping the main branch in a releasable state is a continuous discipline shared by both development and operations teams. Short-lived branches, small PRs, accountable reviews, reliable pipelines, clear quality gates, and Git protection policies create a controlled integration stream. Building once, managing immutable artifacts, separating configuration and feature flags, verifying deployments, and preparing rollbacks enable teams to release frequently while keeping risk under control.

When the main branch breaks, prioritize restoring its releasable state and addressing the root cause before resuming merges. When every change has traceable commits, checks, artifacts, environments, and deployment outcomes, CI/CD becomes an evidence-backed release process rather than just a sequence of automated commands.

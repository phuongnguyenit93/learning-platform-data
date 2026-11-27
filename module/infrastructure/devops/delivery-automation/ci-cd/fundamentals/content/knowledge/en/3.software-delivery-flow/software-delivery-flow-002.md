# Defining Inputs, Outputs, and Gate Conditions Across Each Stage

A reliable software delivery flow must answer three questions at every stage: **what inputs does this stage receive, what artifacts or evidence does it produce, and what criteria determine whether it can advance?** When these three questions lack clear answers, a pipeline easily turns into an automated chain of commands that is hard to control: the wrong version may get deployed, tests may be skipped, unverified artifacts may be released, or the team may have no idea where to roll back during an incident.

In CI/CD, each stage should be designed as a verifiable contract. This contract keeps pipeline runs consistent, helps approvers understand exactly what they are approving, and enables operations teams to trace the path from a Git change to the running version.

## 1. The Contract Model for a Stage

A stage in the software delivery flow should declare at least five components:

| Component | Question to Answer | Examples |
|---|---|---|
| Inputs | What data does the stage require? | commit SHA, build config, tool versions, artifact digest |
| Actions | What work does the stage perform? | lint, run tests, package, deploy |
| Outputs | What products or results does the stage produce? | test report, container image, deployment revision |
| Gate | What evidence proves it can proceed? | all mandatory checks pass, artifact has been scanned |
| On failure | Stop, retry, or revert to which step? | block merge, retain logs, roll back deployment |

Inputs must have an identifiable origin. Outputs must carry a name, version, or identifier clear enough for the next stage to consume. Gate conditions must be machine-verifiable or confirmed by an authorized person following a defined process. Avoid vague conditions such as "the build looks fine" or "tests are mostly sufficient."

This contract can be expressed using the conceptual structure below. This is a design illustration, not configuration syntax for a specific CI/CD platform:

```yaml
stage: test
inputs:
  - source_commit
  - dependency_lockfiles
  - test_configuration
outputs:
  - test_report
  - coverage_report
  - test_status
pass_when:
  - required_tests_pass
  - coverage_meets_policy
on_failure:
  - stop_pipeline
  - retain_reports_and_logs
```

A gate is only meaningful when it validates the exact output of the preceding stage. For example, a deployment step must consume an artifact that was already built and verified; it should not rebuild from a branch that may have changed in the meantime.

## 2. Inputs, Outputs, and Gates Across Each Stage

A typical flow progresses from a Git event, source verification, quality checks, build, artifact storage, environment deployment, release approval, to post-deployment verification. Stage names and counts may vary by project, but each stage's contract must remain clear.

### 2.1. Receiving the Git Event

**Purpose:** identify which change should trigger the pipeline and why the pipeline was started.

- **Inputs:** push event, pull request, tag creation, manual run request, or scheduled trigger; repository; branch or tag; commit SHA; triggering user or system; permitted parameters.
- **Outputs:** a pipeline run with a unique ID; event type; target commit SHA; timestamp and identity of the triggering actor.
- **Gate:** the event is within allowed scope; the branch/tag complies with policy; input parameters are valid; the pipeline can pinpoint the exact commit to process.
- **On failure:** reject invalid requests and record the reason. For consecutive pushes, supersede and cancel stale runs if project policy permits.

Never use a branch name as the sole identifier for a source code version, because branch contents change over time. Record the commit SHA from the very beginning. Pipelines triggered by pull requests from forks must also be treated as untrusted sources: do not expose deployment secrets or registry write permissions to untrusted code.

### 2.2. Fetching and Verifying Source Code

**Purpose:** ensure every subsequent step operates on the exact same source code snapshot.

- **Inputs:** repository, commit SHA, checkout configuration, submodules, and lockfiles if used by the project.
- **Outputs:** checked-out source workspace; actual commit SHA; version metadata for tools and input dependencies.
- **Gate:** checkout succeeds on the exact requested commit; submodules resolve to the right revisions; dependencies resolve according to lockfiles; workspace state matches the project's build expectations.
- **On failure:** stop the pipeline and preserve checkout or dependency resolution error details.

If the pipeline supports building from release tags, verify which commit the tag points to and whether the tag meets the project's protection or signing policies. Never silently fall back to building the latest commit on a branch when the original commit is no longer accessible.

### 2.3. Source Code Quality and Security Checks

**Purpose:** catch defects early before consuming build and deployment resources.

- **Inputs:** source snapshot; lint and static analysis configurations; test suites; coverage policy; rules for secret, dependency, and vulnerability scanning.
- **Outputs:** lint results; static analysis reports; unit test and other required test results; coverage reports; secret and dependency scan results.
- **Gate:** all mandatory checks succeed; zero secrets detected; no vulnerabilities exceed policy thresholds; coverage meets configured thresholds if required; reports are archived for traceability.
- **On failure:** block merging or block progression to the next stage; surface clear errors and reports so developers can fix them.

Not every project needs every check on every run. Define clearly which checks are mandatory for pull requests, which run on a schedule, and which are mandatory before release. If a check is skipped due to misconfiguration or missing tooling, the pipeline must report a "not executed" status rather than treating it as a pass.

Tests are commonly organized into layers:

| Test Layer | What It Verifies | Typical Placement |
|---|---|---|
| Unit test | Behavior of small units of code | Every pull request |
| Integration test | Interaction between modules or services | Pull request or post-build |
| Contract test | Compatibility between communicating parties | Before integration/release |
| End-to-end test | Business flows across the system | Test or staging environment |
| Smoke test | Essential functions and endpoints remain operational | Immediately after deployment |

Test results must be tied to the commit SHA and pipeline run. A bare "test passed" checkmark with no reference to a concrete report is of little help when investigating an incident.

### 2.4. Building the Software

**Purpose:** transform verified source code into a packageable, releasable product.

- **Inputs:** commit SHA; build script; version-locked dependencies; compiler, runtime, and tool versions; non-sensitive build parameters.
- **Outputs:** binary, package, or image; build logs; metadata about commit, tools, and dependencies; checksum or digest of the output.
- **Gate:** build completes; output artifacts exist in the expected format; metadata references the right commit; required product-level checks pass.
- **On failure:** stop before the publish step; retain build logs and build environment details.

To improve reproducibility, pin tool and dependency versions, use lockfiles, control environment variables, and avoid relying on undeclared state on the build machine. If the same commit and inputs produce different results, the team must be able to identify whether the difference came from the toolchain, dependencies, configuration, or external data.

Deployment secrets are generally unnecessary during the build step. Never pass production secrets via build arguments, write secrets to logs or metadata, or bake secrets into artifacts.

### 2.5. Verifying, Packaging, and Storing Artifacts

**Purpose:** produce an immutable version that can be inspected, retained, and deployed repeatedly.

- **Inputs:** build output; checksums; build metadata; artifact retention and scanning policies.
- **Outputs:** artifact stored in a package repository or container registry; immutable digest or version; scan report; SBOM or provenance if required by the process.
- **Gate:** upload succeeds; the artifact can be pulled back; the stored digest matches the computed digest; the artifact meets security and retention policies.
- **On failure:** block deployment; retain logs and upload diagnostics for investigation.

Artifacts must be identified by an immutable digest or immutable version. Human-readable tags like `latest` can be handy for lookups, yet they cannot prove the exact content deployed because tags can be reassigned. The pipeline should store both the artifact name and its actual digest.

A fundamental principle is **build once, promote the same artifact across environments**. For instance, the image tested in staging must be the exact image deployed to production. If production rebuilds from source, the output may differ from the version that was approved.

### 2.6. Deploying to Integration or Test Environments

**Purpose:** verify that the artifact works with environment configuration and dependent services in a realistic setting.

- **Inputs:** approved artifact digest; environment configuration; references to secrets provisioned for the environment; infrastructure and dependent services.
- **Outputs:** deployment revision; target environment and deployment timestamp; rollout status; deployment logs; endpoints or access details for testing.
- **Gate:** the exact digest is deployed; workloads reach ready state; configuration is valid; smoke tests and post-deployment checks pass.
- **On failure:** halt promotion; collect logs and workload status; restore the previous version if the change impacted a shared environment.

Configuration may differ across development, test, staging, and production, but the artifact must remain unchanged. Secrets should be fetched from a secret manager or platform provisioning mechanism at deployment time. Access permissions must be scoped by environment and job; a test job does not need production write access.

### 2.7. Production Approval and Deployment

**Purpose:** control release timing and confirm the version is authorized to reach users.

- **Inputs:** artifact digest; test and scan results; staging verification results; release notes; deployment plan; rollback plan; change request or approvals if required by organizational process.
- **Outputs:** approval decision with identity and timestamp; production deployment revision; rollout history; links to the artifact and pipeline run.
- **Gate:** all mandatory checks have passed; an authorized approver signs off within scope; release window and operational conditions are appropriate; recovery plan is ready.
- **On failure:** do not start the rollout, or halt the rollout according to policy; record the rejection reason and supporting evidence.

Manual approvals require an audit trail: who approved, which exact version they approved, when, and based on what evidence. An "Approve" button not bound to a specific artifact digest can result in approving one version while deploying another.

Incremental rollouts such as rolling updates, canary, or blue-green can be used. For canary releases, the gate must specify the observation window, traffic percentages, and allowable error thresholds before expanding scope. For database changes, consider backward compatibility: roll out new application code and new schemas in compatible steps, avoiding destructive data migrations before a safe recovery path exists.

### 2.8. Post-Deployment Verification and Release Completion

**Purpose:** confirm the system actually works after rollout, rather than merely confirming the deploy command returned success.

- **Inputs:** deployment revision; endpoints and smoke test scenarios; health checks; metrics, logs, and traces; service SLI/SLO or alerting thresholds.
- **Outputs:** smoke test or synthetic test results; health status; telemetry observations over a defined window; release conclusion; links to dashboards and logs.
- **Gate:** essential endpoints respond properly; error rates and latency remain within thresholds; no new critical alerts fire; key business flows operate normally.
- **On failure:** halt rollout, shift traffic back to the stable version, or trigger the rollback/roll-forward procedure; notify the responsible owner per operational procedure.

Always distinguish between "deployment succeeded" and "service verified." A deploy command can complete while the application still fails due to configuration, database connectivity, permissions, or external dependencies. Verification must therefore test the live behavior of the service.

## 3. Summary Control Table

The table below serves as a starting point when designing a pipeline. Stage names may vary, but every row needs a clear owner and concrete evidence.

| Stage | Primary Inputs | Outputs / Evidence | Typical Gate Condition |
|---|---|---|---|
| Git event | Event, ref, commit SHA, actor | Pipeline run ID, trigger source | Valid event and ref |
| Checkout | Repository, commit SHA, lockfiles | Source snapshot, actual commit | Exact commit, resolved dependencies |
| Quality | Source, test and scan policies | Test report, coverage, scan report | Mandatory checks meet policy |
| Build | Source, toolchain, build config | Binary/package/image, build metadata | Build succeeds, matches source |
| Artifact | Build output, digest | Stored artifact, digest, scan result | Pullable, digest matches, meets policy |
| Test environment | Artifact digest, config, secret reference | Deployment revision, smoke-test result | Workload ready, tests pass |
| Production release | Artifact, evidence, approval | Production revision, approval record | Approved, rollout within thresholds |
| Post-deploy | Revision, health checks, telemetry | Verification report, release status | Service healthy over observation window |

Do not store only the final result of a pipeline. Retain evidence per stage so that when a gate fails, the team knows exactly which inputs were used and which condition fell short.

## 4. Maintaining End-to-End Traceability Across the Pipeline

An auditable release flow should link the following identifiers:

```text
Git event
  -> repository + commit SHA
  -> pipeline run ID
  -> test / scan reports
  -> build metadata
  -> artifact name + immutable digest
  -> deployment revision + environment
  -> approval record
  -> post-deploy verification
  -> rollback or release completion
```

Every deployment should record at minimum: service, environment, artifact digest, commit SHA, pipeline run ID, deployment revision, initiating user or system, timestamp, and verification outcome. During an incident, this information quickly answers: which version is running, which commit built it, which checks it passed, and which stable artifact we can revert to.

If the platform supports provenance or attestation, attach evidence covering the source code, build environment, and artifact creation process. An SBOM reveals which dependencies are embedded inside the product. These records complement one another: an SBOM describes the components, while provenance describes the origin and build process of the artifact.

## 5. Designing Safe and Operable Gates

A well-designed gate satisfies the following principles:

1. **Concrete conditions:** rely on test results, scans, digests, health checks, or identified approvals; avoid criteria based purely on subjective opinion.
2. **Explicit policies:** document error thresholds, coverage minimums, vulnerability severities, observation windows, and authorized approvers.
3. **Fail closed on mandatory checks:** if a required security or quality check result cannot be obtained, never treat missing data as a pass.
4. **Traceability:** retain logs, reports, and input/output identifiers; avoid storing only a binary green/red status.
5. **Least privilege:** each job receives only the permissions it needs; separate build, publish, and deploy permissions; protect secrets and production environments.
6. **Safe retries:** operations with side effects must be idempotent or use run identifiers to prevent duplicate resource creation or duplicate releases.
7. **Clear failure handling:** define when to retry, when to stop, who gets notified, and what conditions trigger a rollback.

In particular, restrict where secrets are used. Never place secrets in source code, artifacts, logs, caches, or command-line arguments that might be recorded. Prefer short-lived credentials or workload identity mechanisms if the platform supports them. For pull requests from untrusted sources, never grant access to production secrets or release artifact publishing permissions.

## 6. Distinguishing Retry, Rollback, and Roll-Forward

These three actions address different classes of failures:

- **Retry:** re-running an operation that failed due to a transient error, such as a registry timeout or a temporarily unavailable test service. Only retry when the operation can be safely repeated and with a bounded retry limit.
- **Rollback:** reverting the service to a previously known stable version. Requires retaining the prior artifact, its matching configuration, and a traffic-shifting mechanism. Rolling back the application does not automatically revert data changes.
- **Roll-forward:** fixing the defect in a new version and deploying onward. Suitable when rolling back is unsafe, such as when schemas or data have changed irreversibly.

Before releasing, the team should define rollback triggers: which error rate over what duration, which failing health check, or which impacted business flow. Decisions must be grounded in telemetry and real user impact, not solely on deploy job status.

## 7. End-to-End Example: From Pull Request to Production

Suppose a team develops an API service and prepares to release commit `a1b2c3d`.

1. A pull request is opened. The pipeline records the repository, pull request, commit SHA `a1b2c3d`, and initiator.
2. Checkout verifies the workspace matches that exact commit. Linting, unit tests, integration tests, and dependency scans run according to project policy.
3. Once mandatory checks pass, the pipeline builds the image. Build metadata captures the commit, toolchain versions, and pipeline run.
4. The image is pushed to the registry. The pipeline records the digest—such as `sha256:...`—then verifies the image can be pulled by digest and that scan results pass policy.
5. That exact digest is deployed to the staging environment. Smoke tests, contract tests, and critical business scenarios run against the newly deployed revision.
6. An authorized approver reviews the reports and records an approval bound to the digest and release request. The pipeline deploys the approved digest to production.
7. After rollout, smoke tests and telemetry are observed for the designated period. If all thresholds hold, the release is marked complete. If error rates exceed thresholds, the pipeline stops ramping traffic and executes the defined recovery procedure.

In this example, the commit SHA identifies the source code, the pipeline run ID identifies the execution, the artifact digest identifies the exact product, and the deployment revision identifies the version running in the environment. All four identifiers must link cleanly to one another.

## 8. Checklist When Designing or Reviewing a Pipeline

Before putting a pipeline into production use, verify:

- [ ] Every stage has documented inputs, outputs, and gate conditions.
- [ ] The commit SHA is recorded and preserved across every step.
- [ ] Mandatory checks produce reports and enforce clear threshold policies.
- [ ] Builds use pinned toolchain and dependency versions.
- [ ] Artifacts have immutable identifiers and their digests are recorded.
- [ ] The same artifact is promoted across environments.
- [ ] Secrets are scoped per job and per environment under least privilege.
- [ ] Production has an approval mechanism that records the approver's identity.
- [ ] Post-deployment smoke tests and telemetry checks are in place.
- [ ] Rules exist for retry, rollback, or roll-forward, with clear ownership.
- [ ] Any running deployment can be traced back to its artifact, pipeline run, reports, and source commit.

When these contracts are expressed in the pipeline as code and reviewed alongside application code, CI/CD becomes a repeatable and verifiable software delivery process. The team knows which steps every change passed through, what product was built, why it was authorized for release, and how to respond when a condition fails.

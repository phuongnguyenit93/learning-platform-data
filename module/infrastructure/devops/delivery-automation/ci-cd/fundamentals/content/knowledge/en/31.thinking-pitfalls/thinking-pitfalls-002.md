# Conflating Continuous Delivery with Continuous Deployment

In CI/CD, the two terms Continuous Delivery and Continuous Deployment are often abbreviated together as CD. Because they appear in the same pipeline and both aim to get software to production faster, they are easily used interchangeably. However, the two concepts describe two different levels of automation at the final release decision.

**Continuous Delivery** means every change that passes through the pipeline is in a safely releasable state. Deploying to production may be automatic or require an approval/decision before execution. **Continuous Deployment** goes one step further: every change that passes automated conditions is deployed to production without requiring a person to approve each release.

Continuous Deployment is a way of implementing Continuous Delivery at a higher level of automation. Both require reproducible builds, automated testing, artifact management, configuration control, observability, and recovery mechanisms. The distinction lies in who or what decides when each change enters production.

## 1. The Two Concepts and Core Differences

### 1.1. Continuous Delivery

Continuous Delivery is the capability to keep software continuously in a releasable state. Every change passes through automated checks, produces a deployable artifact, and is verified in appropriate environments. Once the pipeline completes, the team can release that version according to business needs.

A Continuous Delivery flow typically has these characteristics:

- Commits are built and tested automatically.
- Artifacts are packaged, identified, and stored with traceability.
- Artifacts are deployed automatically to test or staging environments.
- Quality gates and post-deployment validations are executed.
- Production deployment may wait for approval, a release schedule, or an operational decision.
- Once approved, the exact same verified artifact is promoted to production.

Approval in production is a release control point. It does not mean the team must rebuild, manually copy files, or run an unmanaged set of deployment commands. A system can still be Continuous Delivery even if the final step requires a human to decide the timing of the release.

### 1.2. Continuous Deployment

Continuous Deployment automatically deploys every change that passes mandatory gates to production. There is no separate human approval step for each routine deployment.

A Continuous Deployment flow typically has these characteristics:

- Every eligible commit is built and tested automatically.
- Artifacts are deployed across environments according to policy.
- Canary, progressive rollout, or an equivalent mechanism limits the blast radius.
- The system automatically evaluates telemetry and quality gates.
- When all conditions pass, rollout continues to all of production.
- When a condition fails, rollout stops automatically, shifts traffic, or triggers a recovery action per policy.

Continuous Deployment does not mean every commit regardless of quality gets pushed to production. Changes are only deployed when the pipeline proves all defined conditions pass. A failing gate must block the rollout.

### 1.3. Comparison Table

| Aspect | Continuous Delivery | Continuous Deployment |
|---|---|---|
| Goal | Every change is always ready to release | Every change passing automated gates is released |
| Build and test | Automated | Automated |
| Artifact | Built and traceable | Built and traceable |
| Deploy to staging | Usually automated | Usually automated |
| Production decision | May require approval or a release schedule | Automated by policy |
| Human role | May decide release timing | Designs policy, monitors exceptions, and improves the system |
| Speed to production | Follows the chosen release cadence | Follows the pace at which changes pass gates |
| Automation requirement | High | Very high, including rollout and recovery |
| Best suited for | Environments with release windows or mandatory approvals | Services with mature testing, telemetry, and risk controls |

The distinguishing point is not whether the pipeline automatically deploys to staging. Both models can automate most of the pipeline. The deciding question is: **does every change that passes gates go straight to production automatically, or does it wait for a release decision?**

## 2. Relationship Between the Two Models

Continuous Delivery can be viewed as the foundation, while Continuous Deployment is the level of production release automation built on top of that foundation.

~~~mermaid
flowchart TD
    A["Commit / merge"] --> B["Automated build and tests"]
    B --> C["Immutable, traceable artifact"]
    C --> D["Deploy and verify staging"]
    D --> E["Quality gate"]
    E --> F{"Gates pass?"}
    F -- "No" --> X["Stop, investigate, and fix"]
    F -- "Yes" --> G{"Release model"}
    G -- "Continuous Delivery" --> H["Artifact ready to release"]
    H --> I["Approval / schedule / release decision"]
    I --> J["Deploy production"]
    G -- "Continuous Deployment" --> K["Automated production rollout"]
    J --> L["Post-deployment validation"]
    K --> L
    L --> M["Monitor and recover per policy"]
~~~

Both models require a pipeline that generates evidence that an artifact has been built and verified. Continuous Deployment can only make automated production decisions if gates, thresholds, telemetry, and failure actions are defined clearly enough.

If an organization cannot yet automate the production release decision, it can still achieve Continuous Delivery by ensuring versions are always ready and having the approval step only decide release timing.

## 3. Distinguishing Deploy from Release

Another source of confusion is using deploy and release as the same action.

- **Deploy** is placing an artifact or application version into a running environment, such as a production cluster.
- **Release** is making that capability or change available to users or a specific group of users.

An artifact may already be deployed to production while the feature remains turned off behind a feature flag. Only when the flag is enabled is the new functionality actually released to users.

This allows separating the technical risk of deployment from the business decision of when to deliver a feature.

### 3.1. Feature Flags Help Separate Deploy from Release

For example, a change adding a new payment flow can be deployed to production but enabled only for internal staff or 1% of traffic. The team can inspect logs, latency, error rate, and business behavior before expanding exposure.

Feature flags need:

- An accountable owner.
- A safe default state.
- A clear user or cohort scope.
- An audited toggle mechanism.
- A review deadline and plan to clean up stale flags.
- Compatibility checks between new code and old code.

Feature flags do not replace testing. A disabled code path still needs to be built and tested. Flags also do not automatically guarantee safe rollback if the database schema or data has changed.

### 3.2. Dark Launch and Progressive Exposure

A dark launch can deploy new code and have the system process a portion of traffic or data without exposing the results to users. Progressive exposure gradually opens a feature by cohort, tenant, or traffic percentage.

These techniques can be used in both Continuous Delivery and Continuous Deployment. They are ways to control risk during deploy/release, not criteria that define the two models.

## 4. Typical Continuous Delivery Pipeline

A Continuous Delivery pipeline can automate nearly the entire process up to a production-ready state while retaining an intentional release decision.

Reference flow:

1. A Git event triggers the pipeline.
2. Source checks, linting, unit tests, and security scans run.
3. The artifact is built once and tagged with commit SHA, version, and digest.
4. The artifact is stored in a registry or artifact repository.
5. The same artifact is deployed to integration/staging.
6. Integration tests, contract tests, smoke tests, and post-deployment validation run.
7. Quality gates are evaluated and release evidence is generated.
8. The version is marked eligible or ready for production.
9. Wait for approval, a change window, or a release decision per policy.
10. Promote the exact verified artifact to production.
11. Check post-deploy health and record the release record.

Approvals should sit on a controlled deployment flow. Approvers need to see the version, commit, artifact digest, test results, scan results, change summary, and rollback plan. Approval should never be a button clicked without context.

### 4.1. Continuous Delivery Pipeline Example

The YAML below is a conceptual configuration, not tied to a specific CI provider's schema:

~~~yaml
stages:
  - validate
  - build
  - verify
  - stage
  - release_ready
  - production

validate:
  run:
    - lint
    - unit_test
    - dependency_scan

build:
  needs: [validate]
  run:
    - build_once
    - create_immutable_artifact
    - record_commit_and_digest

verify:
  needs: [build]
  run:
    - integration_test
    - contract_test
    - artifact_scan

staging:
  needs: [verify]
  run:
    - deploy_artifact_to_staging
    - smoke_test
    - post_deployment_checks

release_ready:
  needs: [staging]
  run:
    - publish_release_evidence
    - mark_artifact_production_ready

production:
  needs: [release_ready]
  approval: required
  run:
    - promote_same_artifact
    - verify_production
~~~

In this model, build, test, and staging deployment are all automated. Approval only decides whether to promote the already-verified artifact to production. Do not rebuild after approval because a newly built artifact may differ from the artifact that was verified.

## 5. Typical Continuous Deployment Pipeline

Continuous Deployment uses the same build and verification foundation, but the production rollout is driven by automated policy.

Reference flow:

1. A Git event triggers the pipeline.
2. Build, test, scan, and produce an immutable artifact.
3. Deploy to a verification environment.
4. Run smoke tests and post-deployment checks.
5. Route a small percentage of traffic to the canary candidate.
6. Compare error rate, latency, saturation, and business metrics against baseline/control.
7. If sample size is sufficient and gates pass, increase the traffic percentage.
8. If thresholds are violated, stop the rollout and execute the defined action.
9. When all conditions pass, complete the production rollout.
10. Record the release marker, artifact digest, and validation results.

### 5.1. Continuous Deployment Policy Example

~~~yaml
deployment:
  mode: continuous
  artifact:
    immutable: true
    require_digest: true

  pre_production:
    required:
      - unit_tests
      - integration_tests
      - security_scan
      - staging_smoke_test

  production:
    strategy: canary
    stages:
      - traffic_percent: 5
        observation_window: 5m
      - traffic_percent: 25
        observation_window: 10m
      - traffic_percent: 50
        observation_window: 10m
      - traffic_percent: 100

    gates:
      require_minimum_samples: true
      max_error_rate: service_policy
      max_latency_regression: service_policy
      business_success_rate: service_policy

    on_inconclusive: hold
    on_failure: stop_and_apply_recovery_policy
~~~

Thresholds in the example must be defined according to SLOs and each service's characteristics. Insufficient data must not automatically be treated as a pass. The system can hold the current traffic percentage, retry measurement, or require investigation per policy.

Continuous Deployment does not mean production must receive 100% of traffic immediately after a single deploy. Canary and progressive rollouts are still automated deployments; they simply divide the process into conditional steps.

## 6. Approval Does Not Equal Quality Control

A common misconception is assuming Continuous Delivery is safer than Continuous Deployment because it has approval. Approval only has value when the approver receives evidence and has clear decision criteria.

A person clicking approve cannot replace:

- Automated tests.
- Security and compliance scans.
- Artifact provenance.
- Deployment validation.
- Monitoring and alerting.
- A rollback or recovery plan.
- A traceable change management process.

Conversely, Continuous Deployment does not eliminate governance responsibility. Controls can be encoded into policies, required checks, deployment permissions, audit logs, and automated guardrails.

### 6.1. When Does Approval Make Sense?

Approval may be necessary when:

- There are mandated change windows.
- A release requires coordinating multiple systems or operations teams.
- There are regulatory, contractual, or separation-of-duties requirements.
- A change has large impact or carries risks that cannot yet be evaluated automatically.
- A business decision is needed on when to enable a feature.

Approvals should be bound to a specific release candidate. If the commit or artifact digest changes after approval, the previous approval must not automatically apply to the new artifact.

### 6.2. When Should the Decision Be Automated?

Production deployment can be automated when:

- Quality gates are reliable and actively maintained.
- Artifacts and configurations are traceable.
- Rollouts can limit blast radius.
- Telemetry is sufficient to detect regressions.
- The system has clear stop/rollback or forward recovery actions.
- Data and schema changes have compatibility strategies.
- Production permissions are scoped via workload identity and policy.

If an essential condition is missing, strengthen that condition before automating high-risk decisions.

## 7. Quality Gates in Both Models

A quality gate is a condition for the pipeline to continue. Both Continuous Delivery and Continuous Deployment require gates; the difference is that the final gate can either lead to a production-ready state awaiting a decision, or automatically open the path for production rollout.

Common gate categories:

| Category | Check Examples |
|---|---|
| Source quality | Lint, format, static analysis |
| Functional | Unit, integration, contract, and end-to-end tests |
| Security | Dependency scan, secret scan, image scan, SAST |
| Artifact | Digest, signature, provenance, and metadata |
| Compatibility | API/schema compatibility, database migration |
| Operational | Readiness, health, smoke test, capacity |
| Post-deployment | Error rate, latency, saturation, business metrics |

Gates need clear states:

- **PASS**: sufficient data and all mandatory conditions met.
- **FAIL**: a condition is violated.
- **INCONCLUSIVE**: insufficient data or observability system is unreliable.

Never turn **INCONCLUSIVE** into **PASS** just to let the pipeline proceed. In Continuous Deployment, this state must typically hold the rollout, cap traffic, or stop according to policy.

## 8. Progressive Delivery, Canary, and Blue-Green

Progressive delivery is a step-by-step release approach that uses live signals to decide expansion. It can support both models.

### 8.1. Canary

Canary routes a small percentage of traffic to the new version first. The system compares the candidate against the control and only increases traffic when guardrails pass.

Canary is especially useful for Continuous Deployment because it enables automated decisions based on telemetry. However, canary is only effective when traffic is representative enough, metrics are split by version, and observation windows are appropriate.

### 8.2. Blue-Green

Blue-green maintains two environments or two sets of workloads. The new version is deployed to green, verified, and then traffic is switched from blue to green.

Blue-green can be used in Continuous Delivery with approval before switching traffic, or in Continuous Deployment with fully automated traffic-switching conditions.

### 8.3. Feature Flags

Feature flags separate deploying code from enabling features. They can allow code to be deployed automatically while controlling user release separately.

Remember that feature flags create additional state to manage. Stale flags, untested flag combinations, or incorrect default states can create hard-to-reproduce bugs.

## 9. Rollback and Recovery Are Not Exclusive to One Model

Both models need recovery capabilities. Continuous Deployment makes the need for fast automated detection and handling more explicit, but Continuous Delivery also needs reliable rollback or forward fixes.

Before rolling out, verify:

- Is the previous version's artifact still available?
- Can the previous configuration be restored?
- Is the database schema backward-compatible?
- Are event/message contracts compatible with older consumers?
- Can the feature flag be turned off safely?
- Can traffic be shifted back without data loss?
- Are readiness, smoke, and business validations run after rollback?

### 9.1. Rollback and Roll-Forward

Rollback reverts to the previous version. Roll-forward deploys a new fix to resolve the issue. For irreversible data migrations, roll-forward may be safer than rolling back old code.

Do not treat a rollback command returning exit code 0 as proof the system has recovered. Verify the running version/digest, traffic routing, health, and business metrics.

### 9.2. Automatic Recovery in Continuous Deployment

Policies can automatically:

- Stop increasing traffic when a gate fails.
- Shift traffic back to the stable version.
- Disable problematic feature flags.
- Hold rollout when data is missing.
- Create an incident or page an operator when safe recovery is impossible.

Automatic recovery must have bounds and auditing. An infinite rollback/redeploy loop can cause further disruption. Include a retry budget, a cap on automatic recovery attempts, and a clear terminal state.

## 10. Change Governance and Access Control

Continuous Delivery typically has an explicit production decision point. Continuous Deployment shifts many routine decisions to automated policy, so permissions and responsibilities must be designed directly into the pipeline.

Principles:

- Use workload identity or short-lived credentials for pipelines.
- Separate permissions for building, publishing artifacts, and deploying to production.
- Do not grant production permissions to jobs running from untrusted pull requests.
- Protect required-check policies and deployment environments.
- Record audit logs for approvals, policy decisions, and deployment actions.
- Link commits, artifact digests, config revisions, and release IDs.
- Separate those who modify source code, those who manage policies, and exception-handling operators.
- Maintain a controlled and logged break-glass process.

Manual approval does not replace access control. Even with approval, the pipeline must verify that the approver has the appropriate authority and that the approval applies to the exact artifact.

## 11. Common Misconceptions

| Misconception | Reality |
|---|---|
| Continuous Delivery and Continuous Deployment are the same | Delivery keeps software always releasable; Deployment automatically pushes gate-passing changes to production |
| Continuous Delivery must always deploy to production manually | Production can deploy automatically after approval or on a release schedule; the decision point still sits outside full automation via a human/policy |
| Continuous Deployment means deploying every commit regardless of outcome | Only changes passing gates are rolled out automatically |
| Having approval makes a pipeline safe | Approval does not replace tests, scans, telemetry, and recovery |
| No approval means no governance | Governance can be enforced through automated policies, permissions, and audits |
| Deploying to production means users already see the feature | Feature flags and progressive exposure can keep a feature off or limited to a cohort |
| Canary is only for Continuous Deployment | Canary can also serve as a verification step prior to approval in Continuous Delivery |
| Continuous Deployment does not need humans | Humans still design policies, handle exceptions, investigate incidents, and make decisions on high-risk changes |
| Rollback is always simple | Schemas, data, and side effects can make rollback unsafe |
| More automation is always better | Only automate decisions when adequate data, guardrails, and recovery exist |

A quick litmus test: if routine production releases still wait for someone to approve each one, that process is Continuous Delivery. If changes passing automated gates are deployed to production by policy without waiting for per-release approval, that is Continuous Deployment.

## 12. Choosing the Right Model for Your Context

Not every service in an organization needs to use the same model. Automation levels can vary by risk, regulatory requirements, architecture, and operational maturity.

| Context | Typically Suitable Model | Reason |
|---|---|---|
| Web product with mature tests and telemetry | Continuous Deployment | Can release small changes frequently with automated guardrails |
| System with fixed change windows | Continuous Delivery | Artifacts are always ready, but production must align with the schedule |
| Financial service or system with mandatory approval | Continuous Delivery with policy/approval | Separates technical readiness from control decisions |
| Internal service with small blast radius | Can progress toward Continuous Deployment | Easy to experiment with automated rollouts and recovery |
| Legacy system lacking automated tests | Start with Continuous Delivery | Must improve reliability before automating production |
| High-risk schema changes or migrations | Continuous Delivery or deployment with specialized gates | Requires compatibility checks and data planning |

### 12.1. Assessing Readiness

Before moving from Continuous Delivery to Continuous Deployment, evaluate:

- Do automated tests catch critical regressions?
- Does the build produce immutable, traceable artifacts?
- Can the same artifact be deployed across multiple environments?
- Are health checks, smoke tests, and business validations in place?
- Does telemetry distinguish version/canary and provide sufficient sample size?
- Are SLOs, guardrails, and rollout stop thresholds defined?
- Have rollback/roll-forward procedures been rehearsed?
- Do databases and APIs have compatibility strategies when multiple versions run concurrently?
- Are production policies and pipeline permissions protected?
- Can incident response handle cases automated policies cannot resolve?

If several conditions are missing, strengthen Continuous Delivery first. A production-ready state has value even when the organization does not yet automatically deploy every change.

## 13. Metrics to Track

To evaluate the effectiveness of either model, track both release speed and operational quality.

| Metric | Meaning |
|---|---|
| Deployment frequency | Frequency of production deployments |
| Lead time for changes | Time from commit to production |
| Change failure rate | Percentage of deployments causing degradation or requiring remediation |
| Time to restore service | Time to restore service after an incident |
| Release-ready age | Time an artifact has been ready but not yet released |
| Approval wait time | Time spent waiting for a release decision in Continuous Delivery |
| Automated rollout success | Percentage of automated rollouts completing per policy |
| Rollback/roll-forward rate | Frequency of needing recovery after a release |
| Gate failure rate | Percentage of changes blocked at each quality gate |

Continuous Deployment typically increases deployment frequency, but high deployment frequency alone does not prove high quality. It must be read alongside change failure rate, recovery time, and business impact.

In Continuous Delivery, release-ready age or approval wait time can show that the pipeline prepares releases quickly while the organization spends a lot of time on the release decision. This may be an intentional choice or a bottleneck to improve.

## 14. Roadmap from Continuous Delivery to Continuous Deployment

The transition should happen based on capability, not merely by deleting the approval step.

1. Standardize builds and tests so every commit produces trustworthy results.
2. Produce immutable artifacts and store digests, provenance, and commit SHAs.
3. Automatically deploy artifacts to staging and run post-deploy verification.
4. Standardize quality gates, SLOs, and business guardrails.
5. Rehearse rollback/roll-forward and verify data after recovery.
6. Adopt feature flags to separate deploy from release where appropriate.
7. Pilot canary on a service with a small blast radius.
8. Automate traffic-increase decisions when sample sizes are sufficient and gates pass.
9. Configure hold/stop policies for missing data or anomalous signals.
10. Expand to other services after reviewing change failure rate and recovery time.
11. Retain approval for exceptional or high-risk changes per policy.
12. Periodically evaluate false positives, false negatives, and gate effectiveness.

You can keep Continuous Delivery for some systems and use Continuous Deployment for others. The goal is to choose the level of automation suited to each service's risk and operational capability.

## 15. Sample Scenario: One Commit, Two Release Paths

Suppose a team develops an addition to an order-history API.

**Under Continuous Delivery:**

1. The commit is merged and the pipeline runs linting, unit tests, integration tests, and security scans.
2. The artifact is built once, tagged with a digest, and stored in the registry.
3. The artifact is deployed to staging, running smoke tests and contract tests.
4. The pipeline marks the release candidate as production-ready.
5. Product/operations choose the release timing and approve per change policy.
6. The pipeline promotes the exact artifact digest to production.
7. The system verifies health and stores the release record.

**Under Continuous Deployment:**

1. The commit is merged and the pipeline runs the same mandatory check suite.
2. The artifact is built once and stored with a digest.
3. The artifact is deployed to staging and verified.
4. Production rollout starts at a 5% canary.
5. The system compares error rate, p95 latency, and business signals against control.
6. If sample size is sufficient and gates pass, traffic increases through 25%, 50%, and 100%.
7. If errors exceed thresholds, the rollout stops and the recovery policy shifts traffic back to the stable version.
8. If all gates pass, the release is recorded automatically.

Both approaches can use the same artifact, the same tests, and the same canary strategy. The difference is that Continuous Delivery retains a production release decision; Continuous Deployment lets policy automatically push gate-passing changes to production.

## 16. Practice Roadmap

You can practice on a sample service using these steps:

1. **Describe the current process:** list triggers, build, tests, artifacts, staging, and the production decision.
2. **Classify the model:** determine whether production releases currently require per-release approval or are automated by policy.
3. **Separate deploy and release:** add a simple feature flag in a test environment.
4. **Create a Delivery pipeline:** automate build, test, staging deployment, artifact storage, and waiting for production approval.
5. **Verify artifact identity:** ensure the promoted artifact has the same digest as the tested artifact.
6. **Define gates:** select tests, scans, smoke tests, SLOs, and business guardrails.
7. **Rehearse approval:** verify approval is bound to the exact release candidate and audited.
8. **Rehearse canary:** deploy a candidate to a portion of traffic and compare against control.
9. **Simulate gate failure:** confirm the pipeline stops or holds the rollout per policy.
10. **Rehearse recovery:** rollback or roll-forward, then run readiness and business validation.
11. **Automate the decision:** only in a test environment, remove routine approval once all automated conditions are verified.
12. **Compare the two models:** record deployment frequency, lead time, approval wait, change failure rate, and time to restore.

### Completion Criteria

Learners can consider the exercise complete when they can demonstrate:

- Accurately explaining Continuous Delivery and Continuous Deployment.
- Identifying the production decision point in each model.
- Distinguishing deploy from release and explaining the role of feature flags.
- Designing a Continuous Delivery pipeline with immutable artifacts and evidence-backed approvals.
- Designing an automated production rollout governed by quality gates.
- Using canary/progressive delivery in both models.
- Handling pass, fail, and inconclusive states.
- Having a rollback/roll-forward plan and post-recovery verification.
- Assessing readiness before removing routine approvals.
- Selecting a model based on risk and operational requirements.
- Measuring effectiveness via deployment frequency, lead time, change failure rate, and time to restore.

## Conclusion

Continuous Delivery and Continuous Deployment both aim to deliver changes to users with short feedback loops and controllable quality. Continuous Delivery ensures every change is always releasable; production release may wait for approval, a schedule, or a policy decision. Continuous Deployment automatically pushes every change that passes gates to production.

Both models can share builds, tests, artifacts, staging, canary, feature flags, and monitoring. The difference lies in the production release decision, not in whether the pipeline is automated. To advance to Continuous Deployment, an organization needs traceable artifacts, reliable quality gates, telemetry with sufficient data, rollouts with bounded blast radius, and rehearsed recovery capabilities. Choosing the right model balances speed, risk, and governance requirements for each service.

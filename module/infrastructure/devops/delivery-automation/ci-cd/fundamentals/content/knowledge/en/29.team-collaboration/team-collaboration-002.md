# Designing a Definition of Done That Includes Deployability and Observability

A feature may work on a developer's machine and pass unit tests, yet still not be ready for release. When deployed to a real environment, it may lack configuration, permissions, health checks, contextual logs, metrics to detect failures, or a rollback procedure when an incident occurs.

Therefore, the Definition of Done (DoD) must encompass both deployability and observability. The team must define upfront how the change will be packaged, configured, released, verified, and operated; at the same time, signals must exist to tell whether the system is operating properly or degrading.

DoD is not a bureaucratic checklist to sign off for compliance. It is a shared quality agreement across development, testing, operations, security, and the product owner. Every criterion needs a verification method, an accountable owner, and reviewable evidence.

## 1. Feature Completion Does Not Equal Deployment Readiness

A change typically progresses through several stages of completion:

- **Code complete:** code within the agreed scope has been written.
- **Test complete:** required checks have been executed and passed.
- **Deployable:** the artifact, configuration, permissions, and deployment prerequisites are ready.
- **Operationally ready:** the change can be monitored, diagnosed, mitigated, and recovered while running.
- **Release complete:** deployed to the target, verified post-deployment, and evidence recorded.

These stages are related but do not substitute for one another. A green build does not prove the application has permission to access the production database. A deployment controller reporting rollout completion does not prove critical business flows are working.

A team must clearly define what "Done" means for each type of work. For a documentation-only change, deployment requirements may not apply. For a production service change, deployability and observability are usually mandatory prerequisites before closing the work.

## 2. Distinguishing Acceptance Criteria, Definition of Done, and Release Readiness

These three concepts are often conflated.

| Concept | Question Answered | Scope |
|---|---|---|
| Acceptance Criteria | How must the feature behave to be accepted? | A single story or requirement |
| Definition of Done | What quality standards must every change meet? | Team or product |
| Release Readiness | Is a specific version ready to be released? | A single release/deployment |

Example for an order-creation feature:

- Acceptance Criteria: authorized users can create an order; each order has a unique ID; total amount is calculated per agreed rules; invalid requests receive an appropriate error.
- DoD: includes unit/integration tests; API is documented; required logs and metrics are added; configs and secrets are managed; migrations are compatible; dashboards and runbooks exist.
- Release Readiness: artifact has been verified; target is correct; migrations are complete; smoke tests pass; error rate and latency are within thresholds; rollback or forward-fix is defined.

Acceptance Criteria describe the outcome of a feature. DoD describes the quality standard applied consistently across work. Release Readiness evaluates a specific version and environment at release time.

## 3. Embedding Deployability into the DoD from Planning

Deployability should not only be asked about at the end of a sprint. During refinement, the team must identify how a change impacts runtime, databases, configuration, permissions, infrastructure, and rollout mechanics.

Questions to ask early:

- Are any new dependencies or system packages added?
- Are there changes to environment variables, config keys, or secret references?
- Are IAM/RBAC or network rule changes required?
- Is there a schema migration or data backfill?
- Can old and new versions coexist during a rolling deployment?
- Are feature flags, canary releases, or initial traffic limits needed?
- Does it affect startup, readiness, graceful shutdown, or capacity?
- If deployment fails, can the application be rolled back? Are schema and data compatible?
- Are any manual steps or approvals needed beforehand?

If answers only emerge on release day, the team may discover too late that the artifact lacks configuration, a migration is incompatible, or workload permissions were never granted.

## 4. Layers of Deployability

A deployable change needs sufficient information and components to be promoted into an environment through the established workflow.

| Layer | Conditions to Consider | Suggested Evidence |
|---|---|---|
| Artifact | Build succeeded, immutable identifier, right target | Build result, digest, provenance |
| Configuration | Config keys have schema, defaults, and validation | Config reference, validation test |
| Secrets | Secrets referenced from secret manager, with owner and rotation | Secret reference, permission check |
| Identity/access | Workload runs with least-privilege permissions | IAM/RBAC review, authorization test |
| Dependencies | Databases, queues, APIs, or dependent services are ready | Contract/integration test |
| Data/schema | Migrations are compatible across coexisting versions | Migration result, compatibility test |
| Runtime | Resource requests/limits, ports, probes, and shutdown are valid | Deployment manifest validation |
| Rollout | Strategy, timeout, pause, and promotion conditions exist | Deployment policy |
| Recovery | Appropriate rollback or forward-fix plan exists | Recovery procedure |
| Verification | Smoke checks and post-deploy criteria exist | Test report, evidence record |

Not every change needs every item. The DoD can use an "apply if applicable" rule, provided it explicitly states who determines scope and how non-applicable items are recorded.

## 5. Artifacts Must Be Release-Ready

An artifact is the input to deployment. The DoD should require artifacts to be produced by a controlled pipeline and traceable to a source revision.

Commonly required conditions:

- Mandatory builds and tests have passed.
- The artifact has an immutable version or digest.
- Metadata links the artifact to the commit, build run, and pipeline definition.
- Dependencies are locked according to project mechanisms.
- The package or container image matches the target OS/architecture.
- The artifact is stored in a registry/repository with appropriate access controls.
- No secrets or sensitive environment config files are bundled inside.
- SBOM/provenance is included if required by product policy.

Never use a mutable tag as the sole identifier for a release. Deployments should reference an immutable digest or artifact ID. This allows the team to verify exactly what was tested matches what is running.

If you build once and promote through staging and production, keep the exact same artifact digest. Rebuilding separately for production can produce content different from the artifact verified in staging.

## 6. Configuration Must Have a Contract and Validation

Environment configuration is a frequent source of post-deploy failures. A new key may be missing in production; a value may have the wrong type; or a default suitable locally may fail in a real environment.

For each critical config key, define:

- Name and data type.
- Whether it is required.
- Default value and valid range.
- Environments or services that use it.
- Source managing the value.
- Behavior when missing or invalid.
- How to change it without rebuilding the artifact.

The application should validate configuration at startup or before accepting traffic. If a required config is missing, the service must fail clearly and emit an error message that does not expose secrets.

Example configuration contract:

```yaml
server:
  port: 8080

orders:
  max-items-per-request: 50
  request-timeout: 3s

database:
  url: required
  username: required
  password-ref: secret-manager://prod/orders/db-password
```

This is an illustrative structure; actual syntax depends on the framework. Sensitive values should be retrieved from a secret manager or via workload identity. Never commit real passwords into configuration files or print them in logs when validation fails.

## 7. Identity and Access Permissions Must Be Prepared

A service may start up yet fail to perform its work because the workload lacks permissions to a database, queue, object storage, or internal API.

The DoD should verify:

- The workload runs under its intended identity.
- Permissions follow least privilege.
- Each environment uses its own permission scope.
- Personal developer credentials are never used at runtime.
- Tokens have appropriate lifetimes and audiences when using workload identity.
- Secret read access is granted only to components that need it.
- Revocation or rotation procedures are defined.
- Sensitive operations leave an audit trail.

Do not verify permissions merely by checking that a credential exists. Verify that the service can perform the exact operations required and is denied operations outside its scope. For example, an order-processing service can write to the orders table but must not be allowed to read the payment service's secrets.

## 8. Migrations and Cross-Version Compatibility

Database changes increase risk during rolling or blue-green deployments because old and new application versions may access the schema concurrently for a period.

A DoD for data changes should specify:

- Migrations are versioned and reviewed.
- Expand changes are deployed before new code depends on the new structure.
- Old and new app versions are compatible during the rollout window.
- Backfills use batching, checkpoints, and safe re-run mechanisms if needed.
- Reconciliation or invariants exist to verify data integrity.
- Contract migrations run only after old consumers are gone and the rollback window has closed.
- Data recovery procedures are reviewed according to risk level.

Do not automatically downgrade a schema when an application deployment fails. Application rollback and data rollback are two separate decisions. If a schema changed in a way that cannot be safely reversed, the team needs a forward-fix or compensating migration.

## 9. Health Checks Must Reflect Meaningful State

Health endpoints are part of deployability, but each probe type serves a distinct purpose.

- **Liveness:** the process is running and not deadlocked by the application's criteria.
- **Readiness:** the instance is ready to accept traffic.
- **Startup probe:** gives the application enough time to initialize before other probes apply.
- **Synthetic/business check:** verifies a business flow via UI or API.

Liveness should not depend on every external dependency. If a database slows down temporarily, failing liveness across all instances can cause the orchestrator to restart pods continuously and worsen the outage. Readiness may reflect dependencies the service needs to serve traffic; liveness should detect unrecoverable process states.

The DoD should specify probe endpoints, timeouts, initial delays, failure thresholds, and failure behavior. Values must be based on startup time and system characteristics rather than copied blindly across services.

## 10. Graceful Shutdown and In-Flight Request Handling

During a rollout or scale-in, the orchestrator may send a termination signal to an instance. If the application exits immediately, in-flight requests may be dropped or messages being consumed may be lost.

The DoD should verify:

- The application stops accepting new requests when shutdown begins.
- Readiness transitions to unready so it stops receiving traffic.
- In-flight requests are allowed to finish within a reasonable deadline.
- Consumers stop pulling new messages and process/acknowledge according to rules.
- Connection pools, threads, and resources are closed in proper order.
- The process exits before the termination grace period expires.
- A shutdown timeout and timeout-exceeded behavior are defined.

For message workers, define what happens when terminated mid-task. If messages can be redelivered, handlers must be idempotent or use deduplication. Otherwise, a rollout can produce duplicate side effects.

## 11. Observability Is Part of the Product

Observability enables the team to infer the internal state of a system from the signals it emits. The three common telemetry pillars are logs, metrics, and traces.

- **Logs:** detailed timestamped events with context for investigation.
- **Metrics:** aggregated numeric time series to detect trends and impact scope.
- **Traces:** the path of a request across multiple services and dependencies.

Dashboards, alerts, and runbooks are the layer that uses these signals to support decisions. Simply adding logs does not equal observability. The team must know which logs, metrics, or traces answer specific operational questions.

A change is complete when the required signals are emitted, collected, queryable, and have an assigned owner.

## 12. Designing Structured and Safe Logs

Logs should be consistently structured so they can be filtered by service, version, environment, and request.

Commonly useful fields:

- UTC timestamp.
- Severity/level.
- Service name and service version.
- Environment.
- Event name.
- Request ID or correlation ID.
- Trace ID/span ID if available.
- Operation or route.
- Outcome and error category.
- Duration if the operation is timed.

Example:

```json
{
  "timestamp": "2026-11-18T08:30:12Z",
  "level": "ERROR",
  "service": "orders-api",
  "version": "3.8.1",
  "environment": "production",
  "event": "order.persistence.failed",
  "request_id": "req-7f31",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error_type": "database_timeout",
  "duration_ms": 1200
}
```

This example contains no order payload or credentials. Never log access tokens, passwords, private keys, session cookies, or personal data unless justified and protected by policy. If a user identifier must be logged, use a pseudonymized or masked representation per policy.

The DoD should also require inspecting logs on failure paths: does the message carry enough context to investigate, is an appropriate stack trace included, does it accidentally leak data, and is the log level noisy?

## 13. Metrics Must Answer Operational Questions

Metrics should be chosen based on service behavior and risks, not solely what instrumentation libraries emit by default.

A baseline set for an API typically includes:

- Request rate: requests over time.
- Error rate: ratio of failed requests by error type or status class.
- Latency: p50, p95, p99.
- Saturation: CPU, memory, connection pools, queues, or worker capacity.
- Dependency health: timeouts, retries, connection failures.
- Business metrics: orders created, successful payments, or task completion rates.

Avoid high-cardinality labels such as raw user IDs, request IDs, or emails. Those belong in controlled logs or traces rather than metric labels. High cardinality increases cost and can overload the metrics backend.

The DoD should specify key metrics, units, labels, calculations, and where they are displayed. Metrics must maintain consistent names and semantics across versions so dashboards do not break on deploy.

## 14. Traces and Cross-Service Correlation

When a request traverses an API gateway, orders service, inventory service, and database, per-service logs alone may not suffice to reconstruct ordering and timing.

Distributed tracing links spans via trace context. A DoD for changes spanning multiple dependencies should specify:

- Trace context is propagated across HTTP/messaging boundaries where appropriate.
- Spans represent significant operations.
- Errors and timeouts are marked.
- Dependency calls record duration and outcome.
- Sampling policies provide enough visibility without unnecessary overhead.
- Traces do not capture sensitive payloads outside policy.
- Service name/version are attached to resource attributes.

You do not need a span for every internal function. Focus on request boundaries, dependencies, and asynchronous work with diagnostic value.

## 15. From Metrics to SLIs and SLOs

An SLI (Service Level Indicator) is a measurement of service quality. An SLO (Service Level Objective) is the target for an SLI over a time window.

Illustrative example for an order-creation API:

- Availability SLI: proportion of valid requests handled successfully.
- Latency SLI: proportion of requests completing under a defined threshold.
- SLO: 99.9% of valid requests succeed over a 30-day rolling window.
- Latency objective: 95% of requests complete within 300 ms under agreed traffic conditions.

These numbers are examples only; teams must choose thresholds from product requirements and real data. Do not apply an identical SLO to every endpoint.

A DoD for reliability-impacting changes should identify which SLIs/SLOs are relevant, whether metrics already exist, and whether the release affects the error budget. If a service lacks formal SLOs yet, it must at minimum emit error, latency, and saturation signals to detect degradation.

## 16. Alerts Must Be Actionable and Routed to an Owner

An alert is not just a metric crossing a threshold. A useful alert must answer:

- What is wrong?
- Which users or services are impacted?
- How severe is it?
- Who is responsible for responding?
- Which dashboard or runbook should be opened?
- What condition closes the alert?

Alerts should focus on user-facing symptoms or imminent risk. For example, a sustained error rate spike over a meaningful window may page on-call; a brief CPU spike may only warrant logging or a low-severity warning.

Avoid alerting on every ERROR log. That creates noise and causes responders to ignore critical signals. Alerts need an owner, routing, severity, threshold, evaluation window, and runbook link.

A DoD for a change introducing a new failure mode should evaluate corresponding alerts. If a failure could cause data loss or severe outage, detection signals and response actions must be defined before release.

## 17. Dashboards Must Serve a Specific Question

A dashboard is not a dumping ground for every metric. Each dashboard should help a specific audience answer a specific question.

For example:

- Service overview: is the service healthy?
- Release dashboard: which version is running and how is the rollout progressing?
- Dependency dashboard: is a database or queue causing a bottleneck?
- Business dashboard: is the order-creation flow succeeding?
- SLO dashboard: how fast is the service burning its error budget?

A dashboard should include:

- Service/environment/version filters.
- Key metrics and reference thresholds.
- Links to log queries and traces if available.
- Deployment or migration annotations.
- Reading guide and owner.
- A default time range suited to its goal.

When deploying a new version, dashboards should allow before/after comparisons and filtering by version or revision. If metrics lack a version label, isolating the impact of a new release becomes much harder.

## 18. Runbooks Are Part of the Definition of Done

A runbook describes how operators diagnose and mitigate a situation. It should focus on concrete actions, not merely explain architecture.

A useful runbook includes:

1. Symptoms and impact scope.
2. Related alerts or dashboards.
3. Initial verification steps.
4. Read-only diagnostic commands or queries.
5. Escalation thresholds.
6. Safe mitigation actions.
7. Conditions for rollback or forward-fix.
8. Owner and escalation channels.
9. How to verify the system has recovered.

For example, a database timeout runbook might guide operators to check connection pools, query latency, lock waits, and database availability before recommending a restart. Destructive or data-mutating actions require explicit conditions and authorization.

Simply having a runbook file exist is not enough. Someone other than the author should walk through the steps to confirm the instructions are usable.

## 19. Deployability and Observability Must Link Together

Deployability and observability are not two isolated checklists. A deployment decision needs signals to verify its outcome; a signal is only useful when tied to the version and target being deployed.

For example:

- Artifact digest identifies the exact content running.
- Service version in metrics/logs allows filtering signals by release.
- Deployment annotations mark release timestamps on dashboards.
- Smoke tests carrying a trace ID help locate request paths.
- Migration run IDs link data issues to schema changes.
- Rollout revisions show which instances received the new version.

The DoD should require essential correlation IDs to flow across build, deploy, and verification. Never rely on a generic version name if multiple different digests could be deployed under the same tag.

## 20. Post-Deployment Verification

After the deployment controller reports completion, the pipeline must run checks against the live target.

A baseline flow:

1. Confirm the exact environment, cluster, namespace, and workload.
2. Confirm the live digest/revision matches the approved artifact.
3. Wait for rollout and readiness to succeed.
4. Run smoke tests against critical endpoints and flows.
5. Observe error rate, latency, saturation, and dependencies.
6. Verify migration/data invariants if applicable.
7. Maintain an observation window suited to traffic patterns.
8. Record results and decide to promote, pause, roll back, or mark inconclusive.

A health endpoint returning 200 does not prove the entire feature works. Smoke tests should verify meaningful behavior without causing unintended side effects. If tests create data, provide a cleanup mechanism or a dedicated test tenant.

If the telemetry backend is unavailable, do not automatically mark the observability gate as passed. Policy must define when to retry, wait, or require authorized human evaluation.

## 21. Rollout Strategy and Rollback Capability

The DoD should define a release strategy aligned with risk:

- **Rolling deployment:** replaces instances in batches; requires version compatibility and graceful shutdown.
- **Blue-green:** runs two environment groups and switches traffic; requires checking schemas, sessions, and shared state.
- **Canary:** shifts traffic incrementally; requires metrics and promote/rollback thresholds.
- **Feature flag:** decouples code deployment from behavior activation; requires an owner and a disable plan.

The rollback plan must account for application, schema, and data. If a migration dropped a column needed by the old version, rolling back the binary may fail. In that case, a forward-fix or compensating migration is required.

For each risky release, document:

- Rollout stop conditions.
- Metrics or checks that trigger rollback.
- Who or which policy has decision authority.
- Target version/artifact to revert to.
- Schema and data impact.
- Post-rollback verification steps.
- Actions if rollback is not feasible.

Never write "can roll back" unless the team has identified which artifact to revert to and confirmed current schema compatibility.

## 22. Security and Privacy in Operations

Observability can inadvertently introduce data leak paths. Logs, traces, dashboards, and reports all require data classification.

The DoD should verify:

- Secrets never appear in logs, artifacts, or test reports.
- PII is masked or stripped per policy.
- Dashboards and log stores enforce appropriate access controls.
- Service accounts have only necessary permissions.
- Debug endpoints are not unintentionally exposed publicly.
- Metric labels do not contain sensitive data or personal identifiers.
- Runbooks do not contain credentials or long-lived access secrets.
- Retention matches purpose and data governance requirements.

Enabling debug logging in production can help during investigations, but its duration, scope, and logged fields must be controlled. If a temporary debug mode exists, the DoD should require an owner, expiration time, and audit record.

## 23. Sharing Responsibilities Across Roles

The DoD is a whole-team agreement. One person may fill multiple roles, but responsibilities must be explicit.

| Role | Primary Contribution | Evidence or Decision |
|---|---|---|
| Product owner | Defines value, acceptance criteria, and user risk | Accepted requirements, release scope |
| Developer | Code, tests, config, instrumentation, and deploy manifests | PR, test reports, metric/log/tracing changes |
| QA | Test design, negative cases, and behavior verification | Test results, defect records |
| Platform/DevOps | Pipeline, identity, environment, rollout, and recovery | Pipeline results, deployment evidence |
| SRE/Operations | SLIs/SLOs, alerts, dashboards, runbooks, and response | Operational readiness review |
| Security | Permissions, secrets, dependencies, and threat/risk review | Security checks, approval when required |
| On-call/service owner | Accepts operational ownership and confirms supportability | Ownership, escalation, and runbook acceptance |

Do not push all observability work onto Operations at the end of a project. Developers know the code paths and failure contexts best; they must add instrumentation while building the feature. Operations/SRE helps define the right signals and response procedures.

## 24. Organizing Cross-Functional Reviews

A change may require review from multiple roles, yet not every PR needs a large meeting.

Effective coordination checkpoints include:

- **Refinement:** identify deployment, data, security, and observability impacts.
- **Design review:** align on SLIs, instrumentation, rollout, and recovery for high-risk changes.
- **Pull request review:** inspect code, tests, config, logs/metrics, and documentation.
- **Pre-release review:** confirm release evidence, target, migrations, approvals, and rollback readiness.
- **Post-deploy review:** evaluate post-deployment signals and record issues.

Using templates to collect answers does not mandate a meeting. Reserve meetings for trade-off decisions or risks that documentation alone cannot resolve.

## 25. Example: DoD for an Order-Creation Feature

Suppose a team adds a `POST /orders` API. The order-creation feature requires functional, deployment, and operational verification.

**Acceptance Criteria:**

- Authorized users can create an order with a valid payload.
- Invalid payloads return a structured error.
- Each request is handled according to agreed idempotency rules.
- Order totals and statuses conform to business rules.
- Unauthorized requests create no orders or side effects.

**Deployability:**

- Artifact is built and traceable to a commit.
- Config keys for item limits and timeouts are validated.
- Workload identity has required permissions to the database and message broker.
- Migrations are compatible with the older app version during rolling deployment.
- Readiness probes and graceful shutdown work properly.
- Rollout timeout and recovery plan exist.

**Observability:**

- Logs record order-creation events, outcome, request ID, and trace ID without sensitive payloads.
- Metrics count requests, successes/errors, latency, and dependency failures.
- Traces link the API to the database and message broker.
- Dashboards show traffic, error rate, and latency by service version.
- Alerts fire on sustained error rate spikes or dependency timeouts.
- Runbook guides investigation of order-creation errors and queue backlogs.

**Release Verification:**

- Exact expected artifact digest is running.
- Rollout reaches full ready replica count.
- Smoke test creates a test order in a dedicated tenant and verifies the result.
- Metrics during the observation window remain within thresholds.
- No migration/data reconciliation failures occur.
- Evidence is stored alongside the release ID.

Separating criteria this way helps the team know what must be finished inside the story and what serves as a release gate.

## 26. Example DoD in a Ticket

A ticket can capture criteria in a concise, easy-to-review format:

```markdown
### Acceptance criteria
- [ ] Valid request creates an order and returns an order ID.
- [ ] Invalid request returns a structured error.
- [ ] Retry with the same idempotency key does not create a duplicate order.

### Definition of Done
- [ ] Unit and integration tests pass.
- [ ] API contract and config schema are updated.
- [ ] Migration is compatible with the currently running version.
- [ ] Logs include request/trace IDs and do not expose sensitive data.
- [ ] Metrics for requests, errors, and latency are queryable.
- [ ] Relevant dashboards and alerts are updated.
- [ ] Runbook includes diagnostic steps for new failure modes.
- [ ] Artifact and deployment config are reviewed.
- [ ] Recovery/rollback plan is defined.

### Release verification
- [ ] Exact artifact digest is deployed.
- [ ] Rollout and smoke tests pass.
- [ ] Post-deploy metrics stay within defined thresholds.
- [ ] Evidence is saved to the release record.
```

Templates must be tailored to the work type. A change with no schema impact can mark migrations as not applicable with a reason. Do not force every ticket to create a new dashboard if existing dashboards already answer the operational questions.

## 27. Example Pipeline Enforcing DoD

A pipeline can map these conditions into explicit jobs:

```yaml
jobs:
  validate:
    steps:
      - validate source and configuration
      - run unit and integration tests
      - build immutable artifact
      - validate deployment manifests

  security:
    steps:
      - scan dependencies and artifact
      - verify secret references and permissions

  deploy:
    needs: [validate, security]
    steps:
      - verify target and approval
      - apply compatible migration
      - deploy artifact by digest
      - wait for rollout readiness

  verify:
    needs: [deploy]
    steps:
      - run smoke and business checks
      - collect metrics, logs and traces
      - evaluate post-deploy thresholds
      - store deployment evidence

  release-decision:
    needs: [verify]
    steps:
      - promote, pause, rollback or mark inconclusive
```

This is a conceptual structure that must be translated into your CI platform's syntax. Security, approval, and migration steps may be organized differently depending on risk. What matters is that every DoD condition has a corresponding check or piece of evidence.

A pipeline cannot automatically validate non-automated elements, such as whether a runbook is easy to follow or whether an alert routes properly. Those items require human review or drills, with outcomes recorded.

## 28. Handling Non-Applicable Items and Exceptions

Not every criterion applies to every change. However, "N/A" must not become a shortcut to skip a hard requirement.

An item may be marked not applicable when:

- The change produces no runtime artifact.
- There are no schema/data changes.
- No new dependencies or permissions are added.
- Existing dashboards/runbooks already cover the behavior and need no edits.
- The release does not alter production behavior.

When marking N/A, record the rationale and confirmer. For risk-bearing exceptions, record:

- Which criterion is waived.
- Rationale and impact.
- Temporary compensating controls.
- Authorized approver.
- Owner responsible for closing the gap.
- Expiration date or target release for completion.

Exceptions must never become permanent. If a criterion is waived frequently, either the DoD or the implementation approach may be misaligned; the team should revisit the design.

## 29. Measuring the Quality of the DoD

A useful DoD catches issues early and reduces post-release rework. Useful metrics to track include:

- Percentage of deployments requiring rollback or hotfix.
- Percentage of incidents linked to missing instrumentation or runbooks.
- Time from deployment to defect detection.
- Time from alert to root-cause identification.
- Percentage of releases with complete post-deploy evidence.
- Rate of post-deploy config/permission failures.
- Number of migrations causing incompatibilities.
- Number of overdue DoD exceptions.
- Ratio of actionable alerts to noisy alerts.
- Percentage of services with clear owners, SLIs/SLOs, and runbooks.

Do not rely solely on counts of logs, dashboards, or tests. The goal is the ability to detect, understand, and resolve issues; more telemetry without owners or actions may simply increase cost.

Teams should revisit the DoD after incidents and major releases. If an incident happened due to a missing health check or unknown running version, add specific criteria to prevent recurrence.

## 30. Common Anti-Patterns

| Poor Practice | Consequence | How to Improve |
|---|---|---|
| DoD only requires code review and unit tests | Missing deployment and operational readiness | Add risk-based deployability/observability criteria |
| Waiting until sprint end to ask about deployment | Late discovery of missing config, migrations, or permissions | Evaluate starting in refinement |
| Treating logs as all of observability | Hard to measure trends and trace requests | Combine logs, metrics, and traces |
| Dashboards with no owner | Nobody maintains or responds to them | Assign a service owner and recipient |
| Alerting on every error | Noise and alert fatigue | Alert on symptoms, severity, and actionability |
| Checking only a health endpoint | Misses business-logic failures | Add smoke/synthetic/business checks |
| Claiming rollback without checking schema | App rollback may fail to run | Verify app/schema/data compatibility |
| Logging full request/response payloads | Leaks PII or secrets | Select necessary fields and apply masking |
| Marking N/A without rationale | Hides incomplete criteria | Record rationale, owner, and confirmer |
| Runbooks exist only on paper | On-call cannot resolve incidents | Rehearse and review runbooks |
| Observability bolted on last by another team | Lacks code-level context | Developers add instrumentation with the feature |
| Release gates store no evidence | Hard to audit decisions | Store artifact, target, checks, and decision |

## 31. Team Adoption Roadmap

You can start with a high-frequency deployment service:

1. **Select a service and owner:** identify who is ultimately accountable for runtime and releases.
2. **Review the support/acceptance contract:** identify user behavior and quality levels to uphold.
3. **Audit current DoD:** identify existing items and common post-deploy failures.
4. **Add deployability criteria:** artifacts, config, identity, migrations, rollout, and recovery.
5. **Add observability criteria:** logs, metrics, traces, SLIs/SLOs, dashboards, alerts, and runbooks.
6. **Map to the pipeline:** automate machine-verifiable gates.
7. **Define manual reviews:** assign owners for runbooks, alert routing, and exceptions.
8. **Run a game day:** deploy to a test environment, inject a controlled fault, and test detection/diagnosis.
9. **Gather feedback:** ask developers, QA, and on-call which criteria help or create waste.
10. **Iterate the DoD:** refine based on incidents, releases, and architectural changes.

You do not need to apply every criterion to every work type on day one. Start with conditions that have high user and recovery impact, then expand based on data.

## 32. Definition of Done Checklist

### Functionality and Quality

- [ ] Acceptance criteria have been verified.
- [ ] Code review is complete.
- [ ] Relevant unit/integration/contract tests pass.
- [ ] Known bugs and limitations are documented.
- [ ] API or behavioral documentation is updated.

### Deployability

- [ ] Artifact has an immutable identifier and is traceable.
- [ ] Config is declared, validated, and has clear value sources.
- [ ] Secrets are securely referenced.
- [ ] Workload identity has least-privilege permissions required.
- [ ] Dependencies and targets have been verified.
- [ ] Migrations are compatible across coexisting versions.
- [ ] Health probes and graceful shutdown function properly.
- [ ] Rollout strategy and timeout are defined.
- [ ] Rollback/forward-fix plan aligns with schema and data.

### Observability and Operations

- [ ] Logs are structured, include correlation IDs, and leak no sensitive data.
- [ ] Metrics for traffic, errors, latency, and saturation are queryable.
- [ ] Traces link critical dependencies where needed.
- [ ] SLIs/SLOs or operational thresholds are defined.
- [ ] Dashboards have owners and display version/deployment markers.
- [ ] Alerts have routing, severity, and actionable responses.
- [ ] Runbooks are executable and reviewed.
- [ ] Post-deploy smoke/business checks have results.
- [ ] Evidence links release, artifact, target, and decision.

### Collaboration and Handoff

- [ ] Service owner and on-call rotation are identified.
- [ ] QA, developers, and operations agree on acceptance conditions.
- [ ] N/A items have rationale and confirmation.
- [ ] Exceptions have owners, mitigations, and expiration dates.
- [ ] Deployment outcomes are shared with responsible teams.

## Conclusion

Designing a Definition of Done that includes deployability and observability enables teams to define quality across the entire lifecycle of a change. A feature is only truly ready when the artifact, configuration, permissions, migrations, rollout, and recovery have been addressed—and when the system emits logs, metrics, and traces backed by dashboards, alerts, and runbooks so accountable owners understand what is happening.

Embedding these criteria into refinement, reviews, and release gates aligns developers, QA, platform, security, and operations around a shared expectation. Every item needs a verification method and evidence; exceptions must have rationale, an owner, and an expiration date. In doing so, "Done" means the team can release, observe outcomes, and respond effectively when the system falls short of expectations.

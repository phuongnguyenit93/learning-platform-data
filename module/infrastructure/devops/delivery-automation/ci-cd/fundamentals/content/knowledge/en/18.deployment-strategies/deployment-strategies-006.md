# Selecting Deployment Signals and Halt Conditions

## 1. Why do we need deployment signals and halt conditions?

A technically successful deployment does not necessarily produce a safe release. Containers may start, Pods may be Ready, and the pipeline may report green, yet users still encounter payment failures, elevated latency, or a disrupted critical business flow.

Controlled deployment must answer two questions:

- **Which signals indicate that the new version is operating well?**
- **When must we stop increasing traffic, abort the rollout, or roll back?**

Without defining these upfront, teams often decide based on a few recent logs or the on-call engineer's gut feel. That makes it easy to miss slow-emerging bugs, overreact to short-term noise, or continue rolling out while key indicators are already degrading.

Within **DEVOPS_CI_CD_FUNDAMENTALS**, a release strategy requires traceability from commits and artifacts through environments, quality gates, post-deployment verification, and rollback. Deployment signals provide evidence for deciding whether to proceed or halt. Halt conditions are predefined policies protecting users and systems when evidence shows the new version carries risk.

A strong process does not merely ask "did the deploy finish?"—it asks "does the service continue meeting its SLOs and is business behavior still correct?"

## 2. Progressive deployment is a decision-making process

With rolling deployment, canary, or blue-green, the new version is typically introduced to part of the system before replacing the old version completely. Each step creates an opportunity to observe and decide.

~~~mermaid
flowchart TD
    A["Define baseline and criteria"] --> B["Preflight: check telemetry"]
    B --> C{"Sufficient observational data?"}
    C -- "No" --> H["HOLD: do not increase traffic"]
    C -- "Yes" --> D["Deploy to small scope"]
    D --> E["Collect signals over window"]
    E --> F{"Evaluate policy"}
    F -- "Pass" --> G["Gradually expand scope"]
    F -- "Needs investigation" --> H
    F -- "Severe violation" --> I["ABORT / ROLLBACK"]
    G --> J{"Full scope reached?"}
    J -- "No" --> E
    J -- "Yes" --> K["Complete and continue monitoring"]
    H --> E
~~~

This model applies to canary, rolling updates, blue-green, or feature-flag releases. The shared requirement is that each scope expansion relies on evidence from the version being deployed.

Traffic increments such as 1%, 5%, 20%, 50%, and 100% are examples only. Appropriate steps depend on traffic volume, risk level, infrastructure capacity, request processing time, and version isolation capability. A low-traffic service may require longer observation windows or a representative test environment before expanding.

## 3. Classifying deployment signals

Do not rely on a single metric. Signals should cover multiple dimensions of the system.

| Signal category | What you need to know | Examples |
|---|---|---|
| Deployment state | Did the new version launch properly? | Pod Ready, rollout progress, restart count, image digest |
| Technical health | Is the service responding and processing requests stably? | Availability, error rate, latency, throughput |
| Resources and dependencies | Is the system overloaded or bottlenecked elsewhere? | CPU, memory, queue lag, database connections, timeouts |
| Business | Are users completing critical workflows? | Payment success, login, order creation, checkout rate |
| Security and data | Is there dangerous behavior or data corruption? | Abnormal access denied, authorization errors, integrity checks |
| Telemetry quality | Is there enough data to make a decision? | Metrics arriving reliably, traces/logs tagged with version, sample count |

Pod Ready status only indicates certain probe-based readiness conditions. It does not prove every API or business flow works properly. Likewise, low CPU does not mean a service is healthy if the database is rejecting connections.

## 4. Using SLIs and SLOs as a foundation

An SLI (Service Level Indicator) measures a service attribute users care about. An SLO (Service Level Objective) sets the target for an SLI over a time window.

Common SLIs include:

- **Availability:** proportion of valid requests handled successfully.
- **Latency:** request processing duration, typically tracked at p50, p95, and p99.
- **Correctness:** proportion of responses or stored data that are accurate.
- **Durability:** degree to which data is safely persisted, relevant for storage services.
- **Freshness:** data recency, relevant for streaming or synchronization systems.

For example, an API has a 99.9% availability SLO over a 30-day window. During a canary, the team monitors the new version's error rate and error budget burn. If the new version accelerates budget consumption, the rollout must halt per policy.

Do not take a long-term SLO and apply it mechanically as a short-term threshold. SLOs define the service level to protect; rollout decisions also need observation windows, baselines, and adequate request volume.

### 4.1. Common technical indicators

- **Error rate:** failed requests divided by total eligible requests.
- **Latency percentiles:** p95 or p99 surface slow request tails hidden by averages.
- **Throughput:** requests or tasks processed per unit time.
- **Availability:** proportion of requests served per SLI definition.
- **Saturation:** utilization or queuing of bounded resources such as CPU, memory, connection pools, workers, or queues.
- **Restart/crash rate:** how often processes or containers restart.
- **Queue lag:** processing delay for queued messages or pending jobs.

Clearly define which requests belong in the denominator. For example, 4xx errors from invalid user input should not be counted identically to server-side 5xx errors. If different service teams define error rates differently, cross-version comparisons become misleading.

### 4.2. Error budget and burn rate

An error budget is the allowable amount of unreliability under an SLO target. Burn rate describes how fast the error budget is being consumed relative to the sustainable rate.

If burn rate spikes while a canary receives traffic, it is a strong signal to hold or halt the rollout. Many organizations combine multiple time windows to balance rapid detection with confirmation that an issue persists. Window lengths and thresholds must reflect the service's SLO, traffic volume, and variance.

Do not copy a burn-rate threshold from another service without considering request cycles, criticality, and fault tolerance of the service itself.

## 5. Tracking golden signals and resources

Four golden signals are commonly used to observe services:

1. **Latency:** how long requests take to complete.
2. **Traffic:** volume of requests or work entering the system.
3. **Errors:** rate of failing requests.
4. **Saturation:** which resources or components are nearing limits.

During rollout, separate the new version's signals from the overall service. If a dashboard only displays aggregates, errors in a 5% canary can be masked by 95% legacy-version traffic.

Telemetry should include labels or attributes enabling filtering by:

- Service and environment.
- Version, image digest, or deployment revision.
- Canary/control cohort.
- Region, zone, or cluster.
- Endpoint or business domain.
- Release ID and deployment start timestamp.

Do not put user IDs, request IDs, or ultra-high-cardinality fields into metric labels without clear justification. Use traces or logs for detailed investigation.

### 5.1. Tie resource signals to symptoms

Rising CPU can be normal when traffic grows. Steadily rising memory may indicate a leak. Rising queue lag alongside falling throughput may show consumers falling behind. Database connection pool exhaustion can drive up latency even while application CPU stays low.

Therefore, inspect relationships across signals rather than halting a rollout over a brief fluctuation in one resource metric. A resource signal becomes a strong halt condition when paired with user-impacting symptoms or approaching instability limits.

## 6. Selecting business signals

Technical indicators tell you how the system is running; business indicators tell you whether users are accomplishing what they need.

Examples:

| Service type | Business signals |
|---|---|
| E-commerce | Add-to-cart rate, successful checkouts, orders created |
| Payments | Authorize/capture success rate, anomalous duplicate or declined transactions |
| Authentication | Login success rate, MFA completion, session creation errors |
| Fulfillment | Shipment creation rate, confirmation latency, duplicate-processed events |
| Data platform | Valid record counts, data freshness lag, rejected record rate |
| Internal APIs | Task completion rate, inter-service retries, timeouts |

A new version may return HTTP 200 yet write corrupted data, miscalculate fees, or create duplicate transactions. For critical flows, enforce invariants or output correctness checks—not just health endpoints.

Business signals must be defined precisely enough to avoid confusing user-behavior shifts with deployment bugs. For instance, checkout conversion might dip because a marketing campaign brings unusual traffic; compare across appropriate cohorts, transaction types, or user segments.

## 7. Establishing baselines and control groups

A metric only makes sense relative to its normal range. Baselines can come from:

- The window immediately preceding deployment.
- The same hour or day of week from prior periods.
- The stable version serving concurrently.
- A control group not receiving the new version.
- Agreed SLOs and operational thresholds.

In a canary, comparing the new version against a control group reduces confounding from system-wide traffic fluctuations. For example, if both groups see rising latency due to a slow external database, the release itself may not be the cause. If latency rises only on the canary, the change is far more likely to be responsible.

However, the control group must match in request types, regions, data, and processing conditions. If the canary receives heavier requests or a different user population, comparisons can mislead.

### 7.1. Relative and absolute comparisons

Combine both condition types:

- **Absolute thresholds:** the service must stay within predefined upper or lower bounds.
- **Relative change:** the new version must not degrade excessively compared to baseline or control.

For example, p95 latency might stay under the SLO ceiling yet double relative to the stable version. Conversely, a small uptick may be negligible on a naturally noisy metric. Combining both prevents decisions based on a single number.

## 8. Observation windows and minimum data volume

Do not decide to advance a rollout after just the first few requests. Allow enough time and sample volume to separate real signal from noise.

The observation window depends on:

- Average traffic and canary traffic percentage.
- Maximum request latency.
- Batch or message processing cycles.
- Metric and alert propagation delay.
- Hourly or daily variance patterns.
- Delayed effects, such as scheduled jobs or end-of-day reports.

For high-traffic APIs, a few minutes may generate enough samples for some signals. For batch systems or infrequent transactions, longer windows or supplemental test-data checks are needed.

### 8.1. Minimum sample size

If a canary receives very few requests, a single error can spike the error rate sharply. With ultra-low traffic, seeing zero errors also proves nothing about safety.

Policies should specify minimum sample sizes or data-sufficiency criteria per signal type. Until met, status must remain `INSUFFICIENT_DATA` and the rollout should hold at its current scope rather than automatically ramping traffic.

### 8.2. Noise and multiple windows

Metrics can fluctuate due to retries, batches, autoscaling, dependency deployments, or anomalous traffic. Techniques include:

- Short windows to catch severe outages fast.
- Longer windows to confirm trends.
- Sustained threshold breaches across multiple evaluation intervals.
- Canary-vs-control comparisons.
- Per-endpoint or per-cohort breakdowns.

Do not delay responding to severe failures just to wait out multiple windows. For data loss, authorization flaws, or widespread crashes, halt conditions should fire as soon as credible evidence exists.

## 9. Defining halt conditions before deployment

Halt conditions must be codified in policy before starting the rollout. Do not wait until dashboards turn red to negotiate whether to stop.

A policy can be organized into tiers:

### 9.1. Hard stop conditions

Typically trigger abort or rollback per runbook:

- The new version fails to start or crash-loops continuously.
- Mandatory readiness or health checks fail past thresholds.
- Error rate or latency severely breaches SLO and is attributable to the canary.
- Evidence of corrupted data, data loss, or duplicate transactions.
- Authorization bugs, data leaks, or severe security regressions detected.
- Critical dependencies lose connectivity due to the new change.
- Resources approach collapse thresholds without self-recovery capability.

For data or security failures, you do not need to wait for statistical metrics to cross a threshold. Verified evidence of severe corruption is enough to halt immediately.

### 9.2. Hold or investigation conditions

Do not necessarily require immediate rollback, but forbid expanding scope:

- Minor metric degradation without enough samples yet.
- New version telemetry is missing or delayed.
- A resource alert fires without user impact yet.
- Business metrics shift without a clear cause yet.
- Both control and canary experience errors, suggesting a shared dependency.
- A mandatory check returns an unknown state.

Holding the rollout gives the team time to investigate while limiting how many users are exposed.

### 9.3. Proceed conditions

Increase traffic only when:

- Mandatory signals have valid data.
- Health and readiness are stable.
- Error rate, latency, and SLIs satisfy policy.
- No new severe findings appear.
- Critical business indicators have not degraded past allowed limits.
- Observation window and minimum sample size are satisfied.
- No hold or hard-stop conditions remain open.

## 10. Distinguishing pause, abort, and rollback

These three actions serve distinct purposes.

| Action | Meaning | When appropriate |
|---|---|---|
| Pause / Hold | Keep rollout at current scope, stop increasing traffic | Need more data or time to investigate an unclear signal |
| Abort | Stop the rollout plan and keep the new version off unshifted scope | Canary has errors or release conditions are no longer met |
| Rollback | Return traffic or workloads to a known-good previous version | The new version is causing impact and the old version remains safe and compatible |

In blue-green, abort may simply mean not switching traffic to green. In canary, it can mean setting canary traffic to 0%. In a rolling update, some new instances have already replaced old ones, so rollback or roll-forward is required.

Not every hold demands a rollback. Conversely, when a severe bug impacts users, merely pausing the rollout is insufficient; reduce or shift traffic away from the faulty version.

## 11. Decision rules when signals conflict

Signals can point in different directions:

- Pods are Ready, yet error rates rise.
- CPU looks normal, yet checkout success drops.
- SAST/SCA passes, yet the application writes incorrect data.
- Canary latency rises while control latency also rises.
- Technical metrics look healthy, yet business telemetry has no data.

Establish a clear priority order:

1. **Data safety and security:** data corruption, leaks, or privilege escalation are strong stop triggers.
2. **User impact and SLOs:** availability, error rate, latency, and critical business workflows.
3. **Operability:** crashes, saturation, queue lag, dependency health.
4. **Evidence quality:** whether data is complete, properly version-tagged, and meets sample minimums.

A PASS on one signal cannot compensate for a hard stop in another category. For instance, low CPU never makes duplicate-transaction bugs acceptable.

When missing data prevents a conclusion, the result must be `UNKNOWN` or `INSUFFICIENT_DATA`, never `PASS`.

## 12. Linking signals to version and deployment scope

To tell which changes the new version caused, telemetry must carry release markers.

Record:

- Release ID or deployment ID.
- Git commit SHA.
- Artifact digest.
- Application version.
- Environment and region.
- Start/end timestamps of each rollout stage.
- Canary and control traffic weights.
- Pauses, aborts, rollbacks, and approvers.

Dashboards must filter by version and cohort. Aggregate views alone allow errors in a small canary to hide behind the old version.

Also ensure metric labels contain no personal data or unbounded cardinality. Request-level details belong in traces or logs with appropriate access controls.

## 13. Example policy for a canary

The example below illustrates a platform-neutral structure. Field names and actual thresholds must be tailored to each service's monitoring stack, SLOs, and traffic.

~~~yaml
deployment_policy:
  strategy: canary

  stages:
    - traffic: small
      observe_for: service_defined_window
    - traffic: medium
      observe_for: service_defined_window
    - traffic: full
      observe_for: post_rollout_window

  data_requirements:
    require_telemetry: true
    minimum_sample_size: service_defined_minimum
    insufficient_data_action: HOLD

  hard_stop:
    - signal: confirmed_data_integrity_failure
      action: ABORT_AND_ESCALATE
    - signal: confirmed_security_regression
      action: ABORT_AND_ESCALATE
    - signal: severe_slo_breach_attributable_to_canary
      action: ROLLBACK

  hold:
    - signal: latency_regression_needs_more_samples
      action: PAUSE
    - signal: telemetry_missing_or_delayed
      action: HOLD
    - signal: shared_dependency_degradation
      action: HOLD_AND_INVESTIGATE

  promote_requires:
    - health_checks_passed
    - slo_policy_passed
    - business_guardrails_passed
    - minimum_sample_size_reached
    - no_open_hard_stop
~~~

This policy omits concrete latency or error-rate thresholds because every service has unique SLOs, traffic patterns, and characteristics. Thresholds must be derived from operational data and versioned alongside rollout configuration.

## 14. Example: canary deployment for a payment service

Suppose the payment service releases a new version changing how it calls the payment provider.

Before deployment, the team identifies:

- API availability and latency SLIs.
- Authorize/capture success rate.
- Anomalous duplicate or declined transaction rate.
- Error rates broken down by response type.
- Timeouts and connection pools to the payment provider.
- Baseline and the control group running the stable version.

When starting the canary:

1. Shift a small, representative slice of traffic to the new version.
2. Verify Pod Ready status and confirm the image digest matches the release record.
3. Wait for sufficient transactions and the observation window.
4. Compare error rate, p95 latency, and payment success rate between canary and control.
5. Check invariants such as each payment request creating only one valid transaction.
6. Increase traffic only if all mandatory criteria pass.

If payment success drops markedly only on the canary, stop increasing traffic and route traffic back to the stable version per runbook. If duplicate transactions are detected, trigger a hard stop, preserve evidence, and remediate data via the incident process.

If both canary and control drop because the payment provider has an outage, hold the rollout and investigate the shared dependency. Never blame the new version from an aggregate dashboard alone.

## 15. Automating decisions while preserving control

Signal evaluation and rollout actions can be automated. However, policies must be explainable and bounded by clear permissions.

A rollout controller should:

- Query metrics scoped to the exact release, version, and cohort.
- Check minimum sample size and data freshness.
- Evaluate hard stops before promotion conditions.
- Refuse to increase traffic if any mandatory condition is unclear.
- Log decisions, input data, and timestamps.
- Bound automatic retries or re-evaluations.
- Prevent concurrent rollouts from modifying traffic or workloads on the same service.
- Support manual pause and escalation to on-call responders.
- Never automatically roll back irreversible data changes without a dedicated runbook.

Automation should execute only pre-approved actions. For example, a policy might automatically drop canary traffic to 0% upon critical failures, while also opening an incident and retaining diagnostics for investigation.

### 15.1. Who has authority to override decisions?

Specify who can:

- Pause a rollout.
- Resume after investigation.
- Abort a release.
- Trigger a rollback.
- Approve exceptions.
- Modify thresholds or observation windows.

Every override must log the actor, reason, timestamp, scope, and expiration. Never allow a single "continue" click to bypass all hard stops without an audit trail.

## 16. Rollback must account for data and compatibility

Application rollback is not always safe. The new version may have:

- Altered the database schema.
- Written data in a new format.
- Emitted messages the old version cannot parse.
- Executed irreversible external transactions.
- Changed inter-service API contracts.

Before release, verify:

- Is the old version compatible with the current schema?
- Do migrations support expand-contract?
- Can consumers pause or traffic shift without losing messages?
- Do already-executed transactions require compensation?
- Does a roll-forward plan exist if rollback is unsafe?

For databases, expand-contract usually lowers risk: add compatible structures first, deploy application code handling both old and new schemas, migrate data if needed, and remove old structures in a later release.

Rollback should redeploy a saved, verified artifact rather than arbitrarily rebuilding an old commit. Alongside the artifact digest, retain release records, environment configuration, and matching runbooks.

## 17. Testing halt conditions before production use

A policy can look sound on paper yet break when wired to metrics or a rollout controller. Test scenarios including:

- Healthy: good signals and enough samples advance the rollout.
- Hard stop: severe errors trigger abort or rollback with the right action.
- Hold: insufficient metric samples prevent traffic increases.
- Telemetry failure: stale, missing, or mis-versioned data returns `UNKNOWN`.
- Shared dependency: simultaneous control and canary errors trigger appropriate investigation.
- Recovery: after fixing issues, resuming or restarting stays traceable.
- Override: manual actions enforce permissions and audit trails.
- Rollback failure: the system alerts and falls back to contingency runbooks.

Use synthetic data, staging, or test environments to verify policies before enabling automated production halts. Ensure halt conditions cannot be silently disabled by broken queries, missing labels, or renamed metrics.

## 18. Common anti-patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Relying only on Pod Ready | Misses API and business failures | Combine health, SLIs, and business metrics |
| Watching only service-wide metrics | Small canary hidden by legacy version | Split by version and cohort |
| Halting on a single spike | Rollbacks triggered by noise | Use appropriate windows, baselines, and confirmation rules |
| Waiting for full samples on all error types | May keep rolling out through severe failures | Enforce hard stops for data, security, and obvious outages |
| No minimum sample size | Draws conclusions from a handful of requests | Enforce `INSUFFICIENT_DATA` state |
| Identical thresholds across every service | Fails to reflect actual SLOs and traffic | Define per-service policies |
| Metrics lacking release/version labels | Cannot attribute regressions to a version | Attach deployment markers and versions |
| Treating missing telemetry as healthy | Promotes without evidence | `UNKNOWN` must hold the rollout |
| Auto-rolling back every alert | Causes churn or data corruption | Distinguish hold, abort, and rollback |
| Skipping data compatibility checks | Old version breaks after rollback | Prepare migration and roll-forward plans |
| Unlogged overrides | Decisions cannot be audited | Record actor, reason, timestamp, and scope |

## 19. Checklist for selecting signals and halt conditions

**Signals**

- [ ] SLIs/SLOs fit the service.
- [ ] Latency, traffic, errors, and saturation are monitored.
- [ ] Health/readiness and dependency signals are included.
- [ ] Business metrics cover critical workflows.
- [ ] Telemetry distinguishes version, release, and cohort.
- [ ] Appropriate baseline and control group exist.

**Thresholds and data**

- [ ] Thresholds derive from SLOs and real operational data.
- [ ] Absolute limits combine with relative changes vs. baseline.
- [ ] Minimum sample size is defined.
- [ ] Observation windows match traffic patterns.
- [ ] `PASS`, `FAIL`, `UNKNOWN`, and `INSUFFICIENT_DATA` are distinguished.
- [ ] Handling is defined for delayed or missing metrics.

**Conditions and actions**

- [ ] Hard stops and holds are defined before rollout.
- [ ] Proceed/promote criteria are explicit.
- [ ] Pause, abort, and rollback are clearly separated.
- [ ] Rules exist when both control and canary fail simultaneously.
- [ ] Owners and override procedures are established.
- [ ] Decisions are captured in an audit trail.

**Recoverability**

- [ ] Prior artifacts remain stored and verified.
- [ ] Rollback uses a known-good digest.
- [ ] Database and message compatibility have been evaluated.
- [ ] Roll-forward or compensation plans exist when rollback is unsafe.
- [ ] Post-deploy verification runs after promotion or rollback.
- [ ] Policies have been tested for healthy, hard-stop, and telemetry-failure cases.

## 20. Conclusion

Deployment signals must reflect technical state, user experience, business outcomes, and observability data quality. SLIs/SLOs, golden signals, baselines, and control groups place the new version in proper context. Observation windows and minimum sample sizes prevent decisions driven by noise or sparse data.

Halt conditions must be defined beforehand, separating hard stops from holds and binding each state to the right action: proceed, pause, abort, or roll back. When telemetry is missing, the system must surface an unknown status rather than treating it as passing. Combining explainable policies, immutable artifacts, data compatibility checks, and audit trails enables automated rollouts that still safeguard services and users.

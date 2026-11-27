# Monitoring Errors, Latency, and Business Signals After a Change

A deployment completing technically does not mean the system is working well. The deploy command may return success, pods may be in the Ready state, and the health endpoint may return HTTP 200, yet users may still encounter payment failures, rising response times, or unrecorded orders. Therefore, CI/CD needs a post-deployment validation step grounded in actual system data.

Post-deployment validation is the process of observing an application after a change is introduced into an environment, comparing operational and business signals against the prior state or a control group, and deciding whether to continue the rollout, pause, roll back, or request operator investigation.

This lesson focuses on three key signal groups: **errors, latency, and business outcomes**. Signals must be linked to the version, artifact digest, configuration, and deployment timestamp so the team knows which change may be causing an effect. The goal is to detect user impact early, determine scope, and make evidence-based release decisions.

## 1. Why Post-Deployment Validation Is Needed

CI tests typically run on controlled data and environments. Staging approximates production, but cannot fully simulate live traffic, data, user behavior, and real dependencies. Some changes only reveal problems under real traffic or when combined with production configurations, data, and other service versions.

Common scenarios include:

- The API still returns responses, but HTTP 5xx rates spike for a subset of requests.
- Average response time barely moves, yet p95 or p99 latency climbs sharply.
- Health checks pass, but the order-creation flow fails due to a dependency.
- Consumers stay alive, yet queue lag grows continuously.
- The new release handles requests successfully, yet records the wrong business state.
- One region or tenant group is affected while aggregate figures look normal.
- Error rates only climb after several minutes due to connection pool exhaustion or rising memory usage.

Therefore, validation must examine both technical health and the outcomes users actually receive. A deployment should only be considered stable when critical signals stay within acceptable thresholds over an appropriate observation window.

~~~mermaid
flowchart TD
    A["Deploy new artifact"] --> B["Attach release marker and metadata"]
    B --> C["Check readiness / smoke tests"]
    C --> D["Observe errors and latency"]
    D --> E["Observe saturation and dependencies"]
    E --> F["Observe business signals"]
    F --> G{"Do signals meet policy?"}
    G -- "Pass" --> H["Continue rollout / confirm release"]
    G -- "Unclear" --> I["Hold traffic ratio and investigate"]
    G -- "Threshold breached" --> J["Halt rollout / roll back per policy"]
    I --> D
~~~

Post-deployment validation does not replace continuous monitoring. It is a phase of heightened observation around a specific change where the team correlates signals with the release and makes explicit decisions.

## 2. Identifying Signals to Monitor

Do not monitor every available metric with equal priority. Before deploying, clarify the change's objective and the signals that can reflect its impact.

You can start with the four operational signal groups commonly called golden signals:

| Group | Question | Example |
|---|---|---|
| Traffic | How many requests is the system receiving? | Requests/second, job count, connection count |
| Errors | How many requests are failing? | HTTP 5xx, exceptions, timeouts, job retries |
| Latency | How long do users have to wait? | p50, p95, p99, job processing duration |
| Saturation | Do resources or dependencies have headroom left? | CPU, memory, thread pools, connection pools, queue lag |

For services with business workflows, add **business signals**:

- Checkout or payment success rate.
- Orders created, confirmed, or completed.
- Unexpected transaction decline rate.
- Records processed vs. records rejected.
- Data synchronization success rate.
- Time from event receipt to business completion.
- Backlogged or dead-lettered tasks.

Each change should have a primary signal set and several guardrail signals. For example, a payment API change should track API error rate, p95 latency, payment success rate, provider timeouts, and pending transactions. Watching CPU and HTTP 200 alone will not be enough.

## 3. Monitoring Errors and Error Rates

Absolute error counts do not convey full impact. Ten errors out of ten million requests means something very different from ten errors out of one hundred requests. Therefore, examine error count, error rate, traffic volume, and affected user groups together.

### 3.1. Classifying Errors by Source

You can classify errors as:

- **Application errors:** unhandled exceptions, validation errors, logic bugs, or serialization errors.
- **Dependency errors:** database timeouts, unavailable cache, external API returning errors.
- **Infrastructure errors:** pod restarts, resource exhaustion, network failures, or DNS issues.
- **Business errors:** rejected transactions, invalid states, or flawed processing rules.
- **Client errors:** malformed requests, user cancellations, or client retries.

Not every HTTP 4xx is a release defect. For example, 401 or 404 may be normal behavior. Define which error types indicate service degradation and which are expected outcomes.

### 3.2. Computing Error Rate with the Right Denominator

Error rate is typically calculated as:

\[
\text{Error rate} =
\frac{\text{Failed requests}}
{\text{Total evaluated requests}}
\times 100\%
\]

The denominator must be consistent. If you count only completed requests, timeouts at the gateway layer may be missed. If a metric counts multiple retries, distinguish original requests from retry attempts to avoid skewing the rate.

Illustrative PromQL example for HTTP 5xx rate:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

Metric names and labels depend on your instrumentation system. Filter by the right service, route, or release when comparing. For a canary, compute the new version cohort and the control cohort separately.

### 3.3. Distinguishing Traffic-Driven Error Spikes from Quality Regressions

If request volume doubles, absolute error count can double even when error rate stays flat. Conversely, a small subset of requests may suffer a high error rate masked by large overall traffic.

Examine together:

- Request count and error count.
- Error rate by service, route, region, and release.
- Error distribution by exception type or dependency.
- Number of affected users or tenants if safely measurable.
- Timing of the error increase relative to the release marker.

Do not create metric labels from user IDs, emails, or very high-cardinality data. When per-user investigation is needed, use access-controlled logs/tracing with desensitized identifiers.

## 4. Monitoring Latency with Percentiles

Average latency can hide a poor experience for a subset of requests. For instance, most requests complete in 100 ms while some take 8 seconds. The average may still look fine while users experience timeouts.

Track percentiles:

- **p50:** median latency, reflecting the typical request experience.
- **p90:** 90% of requests have latency less than or equal to this value.
- **p95:** useful for observing the tail of the distribution.
- **p99:** reflects the slowest requests, often sensitive to resource or dependency issues.

Example p95 query from a Prometheus histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

When comparing, keep the same units, sampling method, and request group. Do not compare p95 of the entire service against p95 of a single route and conclude the release increased latency.

### 4.1. Separating Application Latency from Dependency Latency

Total latency can originate from:

- Processing time inside the application.
- Database queries.
- Cache misses or cache contention.
- Calls to external APIs.
- Queues and asynchronous processing.
- Network or gateway hops.
- Time spent waiting on connection/thread pools.

Distributed tracing helps pinpoint which span consumes the most time in a request. Metrics show trends; traces identify specific paths; logs provide event details. Combine all three rather than staring at a single latency dashboard.

### 4.2. Monitoring Timeouts and Tail Latency

When p99 rises, a subset of requests may be slowed by lock contention, cascading retries, connection pool exhaustion, or a dependency with high tail latency. Excessive retries can load the system even further.

Monitor timeouts, retry counts, pool wait times, in-flight requests, and saturation. If a timeout is configured shorter than a dependency's legitimate processing time, the system may generate many errors even when the dependency eventually finishes.

## 5. Monitoring Business Signals

Business signals answer the most important question: did the change keep the workflows users actually perform working properly?

An endpoint returning HTTP 200 does not guarantee business success. For example, an order API might return 200 without saving the order; a payment service might accept a request yet leave the transaction stuck in pending.

### 5.1. Choosing Metrics by Change Objective

| Change type | Business signals to monitor |
|---|---|
| Checkout | Checkout completion rate, abandoned carts/orders, completion time |
| Payments | Authorization/capture success rate, pending, duplicate transactions |
| Sign-in | Login success rate, MFA errors, abnormal account lockouts |
| Event processing | Events received/processed, queue lag, dead-letter count, and processing time |
| Data sync | Records synced, sync latency, failed or mismatched records |
| Search | Queries returning results, latency, index errors, or stale data |
| Reporting | Job completion rate, data freshness, row counts, and consistency |

Each metric must clearly define the start event, completion event, denominator, and time window. For example, payment success rate must separate legitimate declines from unexpected technical failures.

### 5.2. Measuring Data Correctness

Some bugs cannot be caught via HTTP status or latency. For example, a mapping change might record the wrong currency, duplicate events, or update the wrong status.

You can add:

- Business invariant checks.
- Input vs. output record count reconciliation.
- Duplicate key or multi-processed event checks.
- Batch reconciliation of totals, quantities, or checksums.
- Monitoring late, missing, or out-of-order data.
- Checking schema compatibility between producers and consumers.

For financial or critical data, reconciliation checks must have clear scope and permissions. Do not put personal data or detailed transaction values into metric labels.

### 5.3. Distinguishing Early Signals from Delayed Signals

Some metrics appear right after deploy, such as exception rates or queue lag. Others need time to accumulate enough samples, such as order completion rates or customer retention.

Do not declare a release safe merely because delayed signals lack data yet. Define which metrics are immediate blockers, which require longer observation, and which proxy signals can be used early on.

## 6. Combining Metrics, Logs, and Traces

The three telemetry types complement each other:

| Type | Question answered | Post-deployment role |
|---|---|---|
| Metrics | What is changing and by how much? | Trends, alerts, release comparison |
| Logs | Which specific event occurred? | Error and context investigation |
| Traces | Which components did the request cross and where was it slow? | Pinpoint the failing dependency or span |

Attach relevant metadata to telemetry:

- Service name and environment.
- Release ID or version.
- Artifact digest or build identifier if supported.
- Deployment timestamp or change marker.
- Region, cluster, and workload.
- Trace ID or correlation ID in logs.

### 6.1. Release Markers

A release marker is an event recorded at the exact moment deployment starts or finishes. Markers should include release ID, commit SHA, artifact digest, environment, config revision, and timestamp.

When dashboards display markers, operators can see whether shifts in errors or latency began before or after deploy. Markers do not prove causation, but they narrow the investigation window.

Example release metadata:

~~~json
{
  "release_id": "orders-2026.11.18-03",
  "commit_sha": "8f2a...c91d",
  "artifact_digest": "sha256:...",
  "environment": "production",
  "config_revision": "orders-prod-v12",
  "deployed_at": "2026-11-18T08:30:00Z"
}
~~~

### 6.2. Protecting Telemetry Data

Logs and traces can contain sensitive data. Never log passwords, tokens, session cookies, card details, or full personal payloads. Apply appropriate redaction, access controls, retention, and sampling.

Correlation IDs link a request's logs and traces without putting user-identifying info into every metric. When linking to an account is needed, use an internal identifier mechanism with access controls and retention limits.

## 7. Comparing Against Baselines and Control Groups

A metric shifting after deploy does not automatically prove the release caused it. Traffic may grow by hour of day, a marketing campaign may shift behavior, or an external dependency may be having an outage.

Two complementary comparison methods exist:

- **Pre-deploy baseline:** compare against the same service and traffic type over a period prior to the change.
- **Concurrent control group:** compare the new version against the old version serving traffic at the same time, such as in a canary.

Concurrent comparison is often better when traffic varies over time, provided both cohorts are comparable in region, route, client type, and workload.

### 7.1. Choosing the Observation Window

Too short a window suffers noise from few requests; too long a window delays detection. Choose based on traffic, business characteristics, and how quickly errors surface.

Examples:

- High-traffic services can detect technical errors within minutes.
- Low-volume payment flows need enough time to gather a reliable sample.
- Hourly batch jobs need at least one relevant processing cycle observed.
- Daily sync jobs need freshness and outcome verification after the cycle finishes.

Do not use one fixed duration for every release. When sample size is insufficient, the proper state is **INSUFFICIENT_DATA** or continued observation—do not default to pass.

### 7.2. Being Careful with Rates on Small Samples

If there are only 5 requests and 1 fails, the error rate is 20%, yet uncertainty is huge. With 100,000 requests and 1,000 failures, a 1% rate carries very different statistical and operational meaning.

Require a minimum sample size before deciding based on rates. For low-volume workflows, combine synthetic testing, invariant checks, and manual review.

### 7.3. Accounting for Seasonality and External Changes

Before/after comparisons should consider:

- Time of day and day of week.
- Events or campaigns altering traffic.
- External dependency outages.
- Concurrent configuration or infrastructure changes.
- Routing or traffic-split changes across regions.

If multiple changes occur simultaneously, record a separate marker for each change to avoid misattributing the cause.

## 8. Monitoring by Version and Blast Radius

Aggregate figures can hide a failure occurring only on the new version or a specific traffic segment. You need the ability to slice by:

- Release ID or version.
- Artifact digest.
- Region, cluster, or availability zone.
- Route/API operation.
- Client version or request type.
- Tenant tier or feature group, where appropriate and safe.
- Canary vs. control cohort.

Avoid creating very high-cardinality labels such as request ID, user ID, email, or order ID. Those fields belong in access-controlled logs/traces rather than every time-series metric.

When traffic spans multiple instances, know which release each instance is running. A rollout can have multiple versions coexisting simultaneously; dashboards labeled only at the service level cannot separate candidate signals from control signals.

## 9. Designing Post-Deploy Validation Stages

Validation should progress in stages aligned with release impact and observability. A reference flow:

| Stage | Content | Continuation condition |
|---|---|---|
| Immediate post-deploy | Readiness, process state, basic endpoints, version/digest | Workload ready and right version |
| Smoke validation | Minimal business flows and core dependencies | No critical failures |
| Early observation | Error rate, latency, saturation, logs, and traces | No guardrail threshold breaches |
| Business validation | Conversion, transaction success, queue/data correctness | Business signals do not degrade beyond threshold |
| Progressive rollout | Increase traffic step by step | Each step has enough data and passes gates |
| Release confirmation | Record results, release marker, and evidence | All mandatory gates pass |

### 9.1. Immediately After Deployment

Start with readiness and version verification. Confirm the application runs the approved artifact digest and config revision. If a version endpoint only returns a mutable tag, add build ID or digest for exact verification.

### 9.2. Early Observation Stage

Watch for errors that surface immediately: exceptions, 5xx, timeouts, restarts, OOMs, connection pools, and dependency failures. If a metric breaches a critical threshold, halt the rollout before increasing traffic.

### 9.3. Business Observation Stage

Wait for sufficient data to evaluate metrics such as payment rate, order completion, queue processing, or data freshness. If business signals lag, set the observation period to match the workflow's real cycle.

## 10. Canary and Progressive Delivery

Canary deployment exposes the new version to a portion of traffic before expanding. The goal is to limit blast radius and use live traffic to validate behavior.

An example progression:

1. Deploy the candidate without traffic yet.
2. Run readiness and smoke tests.
3. Shift a small percentage of traffic to the candidate.
4. Compare errors, latency, and business signals against control.
5. If passing, step traffic up incrementally.
6. If data is insufficient, hold the ratio and keep observing.
7. If gates fail, halt rollout and route traffic back to the stable version.
8. Once target traffic and observation time are satisfied, finalize the release.

~~~mermaid
flowchart LR
    A["Candidate 0%"] --> B["Smoke test"]
    B --> C["Canary 5%"]
    C --> D["Compare metrics and business KPIs"]
    D --> E{"Pass gate?"}
    E -- "Yes" --> F["Canary 25%"]
    F --> G["Observe again"]
    G --> H{"Pass gate?"}
    H -- "Yes" --> I["Canary 50% then 100%"]
    E -- "Insufficient data" --> J["Hold ratio and wait"]
    H -- "Insufficient data" --> J
    J --> D
    E -- "No" --> K["Halt rollout / shift traffic to stable"]
    H -- "No" --> K
~~~

Percentages like 5%, 25%, or 50% are only examples. Increments must fit isolation capabilities, traffic volume, and blast radius. Low-volume or sensitive-data systems may require more conservative rollouts.

### 10.1. Comparing Canary Against Control

Compare cohorts over the same time window under equivalent conditions. If the candidate only receives traffic from a higher-latency region, the difference may stem from routing rather than code.

Monitor:

- Error rate by cohort.
- p95/p99 latency by route.
- Resource saturation and dependency errors.
- Business success rate.
- Request count large enough to draw conclusions.
- Duration the candidate has been serving traffic.

Canary analysis should return **PASS**, **FAIL**, or **INCONCLUSIVE**. Do not force every result into a boolean when data is insufficient.

## 11. Setting Thresholds, SLOs, and Rollout Decisions

Validation thresholds should be based on SLOs, baselines, and acceptable impact. Never use a single global number for every application.

Example condition types:

- Candidate error rate does not exceed the defined absolute threshold.
- Candidate error rate is not worse than control beyond the allowed margin.
- p95 latency does not increase beyond the acceptable delta.
- No new critical errors or crash loops appear.
- Business success rate does not drop past the threshold.
- Queue lag and backlog do not grow uncontrollably.
- Minimum request count reached for statistical significance.

### 11.1. Relating to SLOs and Error Budgets

An SLO defines the target reliability level over a time window. The error budget is the tolerable amount of failure corresponding to that SLO.

For instance, if the availability SLO is 99.9% over a defined window, the error budget represents the remaining downtime permitted within that window. A release burning error budget rapidly may require halting the rollout even before breaching an instantaneous error threshold.

Long-term SLOs do not replace short-term post-deploy gates. You can combine:

- Immediate guardrail thresholds to catch severe failures.
- Candidate/control comparison during canary phases.
- Error budget burn-rate monitoring.
- Business guardrails protecting critical workflows.

### 11.2. Defining Three Clear Outcomes

| Outcome | Meaning | Action |
|---|---|---|
| **PASS** | Sufficient data and all conditions met | Continue rollout or confirm release |
| **FAIL** | A condition breached threshold or critical failure occurred | Halt rollout, roll back, or act per runbook |
| **INCONCLUSIVE** | Insufficient sample, missing telemetry, or observability dependency error | Hold traffic share, fix observability, or require review |

If the monitoring system has no data, you cannot conclude the application is safe. Distinguish an application failure from an observability failure, but missing mandatory telemetry must never auto-pass.

## 12. Automated Rollout Halt and Rollback

You can automate halting or rolling back when clear conditions are breached. However, rollback must respect compatibility and data state.

Possible triggers include:

- Error rate exceeding threshold across consecutive windows.
- p95 or p99 latency rising sharply compared to control.
- Crash loops, OOMs, or continuous restarts.
- Significant drop in business success rate.
- Queue lag or dead-letter counts exceeding thresholds.
- Severe security vulnerability or data corruption.
- Candidate failing to achieve readiness within the deadline.

Do not roll back on a single isolated data point if it could be noise. Require sustained thresholds across windows, minimum sample counts, or multiple corroborating signals. For severe issues like data leaks or transaction corruption, act immediately without waiting for statistical windows.

### 12.1. Checking Rollback Preconditions

Before rolling back, verify:

- The previous version still exists and can be redeployed.
- Previous artifact digest and configuration were preserved.
- Database schemas and event contracts remain compatible.
- Migrations are reversible or require a forward fix.
- Rotated credentials remain compatible with the previous version.
- Traffic shifting can be performed safely.
- The previous version can be re-verified as healthy.

If safe rollback is impossible, halt the rollout and ask operators to select an alternative remediation. Automated rollback is not appropriate for every data change or irreversible migration.

### 12.2. Verifying After Rollback

Rollbacks also require validation:

1. Confirm traffic has returned to the stable version.
2. Verify running release ID and artifact digest.
3. Run readiness and smoke tests.
4. Observe error rates, latency, and business signals.
5. Record the rollback status along with the reason.
6. Retain candidate telemetry for investigation.

Do not mark a rollback successful just because the rollback command exited 0. Verify actual system state and health.

## 13. Investigating When Signals Degrade After a Change

When metrics worsen, establish scope and correlation with the release before concluding root cause.

An investigation sequence:

1. Identify the release marker timestamp and release ID.
2. Compare candidate against control or the corresponding baseline.
3. Slice by route, region, workload, and request type.
4. Inspect error types, exceptions, and dependency failures.
5. Use traces to find spans with abnormal latency or errors.
6. Reconcile business events, queue lag, and output data.
7. Check concurrent config, infrastructure, or dependency changes.
8. Decide whether to continue observing, halt rollout, roll back, or roll forward.
9. Document results and link to incidents/tickets if applicable.

### Common Scenarios

| Symptom | Possible cause | Where to check |
|---|---|---|
| 5xx spikes right after deploy | New exception, bad config, or incompatible dependency | Classify errors, traces, and logs by release |
| Average latency normal, p99 rises | Tail latency, pool contention, or slow dependency | Inspect histograms, spans, and wait times |
| CPU rises without error rate spike yet | Higher compute load, loop, or performance regression | Track saturation and latency by cohort |
| Health check passes, orders fail | Business logic bug or incorrect data writes | Reconcile business events and database |
| Queue lag climbs steadily | Slow consumer, retry loop, or reduced throughput | Check processing rate, retries, and dead-letter queue |
| Only one region affected | Region-specific routing, config, or dependency | Slice metrics by region |
| Canary shows high error rate on tiny sample | Insufficient traffic to conclude | Return INCONCLUSIVE and continue observing |
| No metrics after deploy | Broken agent, exporter, or telemetry pipeline | Fix observability before judging release |
| Delayed failure appears | Memory leak, pool exhaustion, or batch job | Extend window and inspect trends |
| Errors persist after rollback | Incompatible schema/config or mutated data | Inspect migrations and data state |

Do not delete or overwrite candidate telemetry after a rollback. That data helps find root causes and prevent recurrence.

## 14. Example Post-Deployment Validation Policy

The example below illustrates a conceptual policy. Thresholds must be derived from each service's SLOs, baselines, and characteristics:

~~~yaml
post_deployment_validation:
  release:
    require_release_marker: true
    verify_artifact_digest: true
    verify_config_revision: true

  immediate_checks:
    - readiness
    - smoke_test
    - running_version

  observation:
    metrics:
      - error_rate
      - p95_latency
      - p99_latency
      - saturation
      - dependency_errors
    business_signals:
      - transaction_success_rate
      - queue_lag
      - data_quality_failures
    require_minimum_sample: true

  canary:
    enabled: true
    stages:
      - traffic_percent: 5
      - traffic_percent: 25
      - traffic_percent: 50
      - traffic_percent: 100
    decisions:
      pass: continue
      fail: stop_and_apply_rollback_policy
      inconclusive: hold_and_observe

  rollback:
    require_previous_artifact: true
    require_compatibility_check: true
    verify_after_rollback: true
~~~

A real policy must map metrics, queries, thresholds, windows, minimum samples, owners, and actions to the monitoring/deployment tools in use. Never apply a single template threshold blindly to every service.

## 15. Practice Roadmap

You can practice on a staging application with these steps:

1. **Choose release objective:** state which routes, dependencies, or business workflows the change affects.
2. **Choose signals:** identify error rate, p95/p99, saturation, and 1–3 critical business metrics.
3. **Define metrics:** align on names, units, denominators, labels, and retry handling.
4. **Establish baseline:** gather pre-deploy data over an appropriate time frame.
5. **Attach release marker:** store release ID, commit SHA, artifact digest, config revision, and timestamp.
6. **Check immediately post-deploy:** run readiness, smoke tests, and version/digest verification.
7. **Observe candidate:** slice metrics by release or cohort, comparing against control.
8. **Set guardrails:** define pass/fail/inconclusive thresholds and minimum sample sizes.
9. **Test progressive rollout:** step traffic up incrementally, advancing only when gates pass.
10. **Rehearse failure:** inject a controlled error in staging, verify alerts, halt rollout, and roll back.
11. **Verify business correctness:** reconcile business outcomes and data after the change.
12. **Archive evidence:** generate a release report with telemetry snapshots, gate decisions, and final status.

### Completion Criteria

Learners can consider the lab complete when they demonstrate:

- Selecting technical and business signals aligned with the change objective.
- Computing and interpreting error rates with a clear denominator.
- Tracking p50, p95, p99 and distinguishing average from tail latency.
- Linking metrics, logs, and traces to a release ID.
- Comparing candidate against an appropriate baseline or control group.
- Handling small samples or missing telemetry using an inconclusive status.
- Setting guardrails aligned with SLOs, error budgets, and business impact.
- Executing conditional canary/progressive rollouts.
- Halting rollout or rolling back when signals violate policy.
- Re-verifying the system after rollback.
- Preserving evidence and release-decision traceability.

## Conclusion

Monitoring errors, latency, and business signals after a change validates software under real operating conditions. Error rates reveal failure magnitude, latency percentiles expose tail experiences, and business signals confirm whether user-facing workflows actually behave correctly. Metrics, logs, and traces must carry release markers to correlate changes with observed data.

A reliable process uses baselines or control groups, appropriate observation windows, minimum sample sizes, and clear pass/fail/inconclusive outcomes. Canaries limit blast radius; SLOs and business guardrails guide decisions; rollbacks are complete only after the prior version and system health are re-verified. Thus, pipelines make release decisions based on real impact rather than merely on whether the deploy command finished.

# Actionable Alert Thresholds and Runbook Linking

## 1. A Good Alert Must Lead to Concrete Action

Monitoring collects and displays system signals. Alerting decides when a signal requires human or automated intervention. A dashboard may display hundreds of metrics; an alert should fire only when a situation calls for investigation, remediation, or a decision.

In Java serverless applications, issues typically surface as function errors, timeouts, rising cold starts, throttling, queue backlogs, dead-letter queue (DLQ) messages, dependency failures, or anomalous cost spikes. Simply configuring an alert for “high CPU” or “exception occurred” leaves the on-call engineer unaware of the user impact, urgency, or where to start.

An actionable alert must answer:

- **What is happening?** Service, environment, region, version, and the specific symptom.
- **Who is impacted?** What percentage of requests, which tenants, event types, or business flows.
- **How severe is it?** Is it breaching an SLO, losing data, corrupting business state, or merely a signal to watch?
- **When should we respond?** Which threshold, sustained duration, and sample count were exceeded.
- **Who owns it?** Team/service owner and receiving alert channel.
- **What is the next step?** Direct runbook link, relevant dashboard, and safest first action.

A good alert does not merely say “Error rate > 5%”. It clearly states the error rate of `order-api` in production, which version is affected, for how long, how it compares to the SLO/baseline, how many requests failed, who needs to handle it, and links to the matching runbook.

## 2. Distinguishing Metrics, Logs, Traces, Alerts, and Runbooks

| Component | Question Answered | Examples |
| --- | --- | --- |
| Metric | How much is a value changing over time? | Error rate, p99 duration, queue age, throttles |
| Log | How did a specific event happen? | Invocation timeout, validation failure, downstream 503 |
| Trace | Which components did a request traverse and where was it slow? | API gateway → Java function → database → payment API |
| Alert | Which situation needs immediate response or ticket creation? | High SLO burn rate across two time windows |
| Dashboard | What is the overall health and trend? | Errors/latency/concurrency by version and region |
| Runbook | What should the responder check and execute? | Verify downstream, pause rollout, roll back, or replay DLQ |

Alerts do not replace logs and traces. They should carry just enough context for the responder to open the right dashboard, log query, or trace. Runbooks describe how to investigate and act; alerts must link directly to the exact runbook rather than pointing to the monitoring home page.

## 3. Designing Thresholds from SLIs, SLOs, and Error Budgets

### 3.1. Choosing User-Meaningful SLIs

A Service Level Indicator (SLI) is a measurement reflecting the service quality users actually experience. Common SLIs for serverless:

- Ratio of successful HTTP requests out of all valid requests.
- Ratio of requests completing within the committed latency threshold.
- Ratio of messages processed successfully within the target deadline.
- Latency from event creation to completed consumer processing.
- Ratio of workflows completing within SLA.
- Ratio of business transactions succeeding without duplicate side effects.

Not every technical metric is an SLI. Memory or cold starts help explain root causes, whereas users care whether requests succeed and finish fast enough. Choose SLIs at service or business boundaries, then use technical metrics for diagnostics.

### 3.2. SLOs and Error Budgets

A Service Level Objective (SLO) is a target for an SLI over a time window. For example, a 99.9% availability SLO over 30 days allows at most 0.1% of valid requests to fail within that window.

An error budget is the allowable failure share under the SLO:

\[
Error\ budget = 1 - SLO
\]

With a 99.9% SLO, the error budget is 0.1%. If the actual error rate spikes, the team may be burning through the budget faster than allowed. Error-budget-based alerting prioritizes issues threatening service commitments instead of paging on every minor spike.

An SLO must clearly define:

- Scope: which service, API, tenant, or workflow.
- Eligibility criteria: which valid requests enter the denominator.
- Failure criteria: which status codes, timeouts, invalid responses, or overdue events count as failures.
- Window: rolling 7/30 days or calendar window.
- Data source: reliable metrics with full coverage and no double counting.

If the denominator is wrong, the SLO and alerts will be wrong too. For instance, do not mix internal health checks or invalid-input rejections into the same SLI as business requests if service commitments exclude them.

### 3.3. Burn Rate

Error budget burn rate expresses the current consumption rate relative to the allowed rate. Given observed error ratio `e` and allowed error ratio `b`:

\[
Burn\ rate = \frac{e}{b}
\]

With a 99.9% SLO, `b = 0.001`. If the actual error rate is 1%, the burn rate is 10x. If the actual error rate is exactly 0.1%, the burn rate is 1x and the budget is being consumed at the exact average pace allowed by the SLO.

High burn rate in a single short window may be a transient spike. Combining short and long windows distinguishes ongoing severe incidents from brief noise. Common multi-window/multi-burn-rate pairs for a 30-day SLO include:

| Reference Signal Level | Long Window | Short Window | Burn Rate |
| --- | --- | --- | ---: |
| Critical | 1 hour | 5 minutes | 14.4x |
| High | 6 hours | 30 minutes | 6x |
| Medium | 24 hours | 2 hours | 3x |
| Low, watch closely | 72 hours | 6 hours | 1x |

These are reference values for a 30-day SLO window, not universal defaults for every service. A multi-window alert typically fires only when burn rate exceeds the threshold in both the short and long windows. The short window catches emerging incidents; the long window confirms they are persistent enough to consume substantial error budget.

### 3.4. Low Traffic and Minimum Sample Size

A low-invocation function can hit a 100% error rate from a single failed request. Ratio alerts must not fire without considering sample size. Combine:

- Minimum request/event count in the window.
- Absolute error count.
- Synthetic probes independent of real traffic.
- Queue age or workflow age for asynchronous flows.

For example, evaluate error ratio only when there are at least 100 requests in 10 minutes; if traffic is lower, use synthetic probes to verify availability and alert separately when telemetry is missing. The value 100 is illustrative and must be tuned to traffic and criticality.

## 4. Setting Context-Aware Thresholds

### 4.1. Static Thresholds

Static thresholds fit well when limits are clear and relatively stable:

- Queue age exceeds maximum SLA.
- New messages appear in the DLQ.
- Concurrent executions approach quota.
- Function timeouts rise above a defined limit.
- Storage capacity or connection pool utilization exceeds safe bounds.
- Daily spend exceeds approved budget.

Thresholds must map to actions. For example, a queue age alert over 5 minutes might require inspecting consumer backlog and downstream health. If queue age exceeds 30 minutes when the SLA is 15 minutes, severity may require paging because the backlog has already breached commitments.

### 4.2. Relative Thresholds and Baselines

For latency, invocation volume, or costs with seasonal patterns, relative baselines can be more helpful than fixed numbers. Comparing against the same hour/day in the prior cycle or against a stable version helps catch regressions.

Do not rely on baselines blindly. A prolonged incident can cause an automated baseline to learn the faulty state as normal. Keep baselines controlled, exclude incident/maintenance periods, and pair them with absolute guardrails.

### 4.3. Duration and Breach-Count Thresholds

Alerts should specify sustained conditions, such as:

- Error rate exceeds 2% continuously for 5 minutes.
- p99 latency breaches SLO across two consecutive windows.
- Oldest-message queue age exceeds 10 minutes across 3 evaluations.
- At least one new message lands in a production DLQ.
- Throttling persists continuously with impacted requests.

Sustained windows reduce false positives from brief spikes. However, for severe events such as data loss, unauthorized access, or double charges, do not wait through a long window merely to filter noise. Classify severity and define immediate critical conditions separately.

### 4.4. Hysteresis and Recovery Thresholds

If an alert fires at 80% quota and resolves immediately when the metric drops to 79%, the system can flap between firing and resolving as the metric hovers near the threshold. Hysteresis uses a lower resolve threshold than the fire threshold, or requires stability for a period of time.

Example:

- Fire when concurrency exceeds 85% of quota for 5 minutes.
- Resolve when concurrency drops below 70% for 10 minutes.

Specific thresholds should match scaling speed and recovery behavior. For SLO-based alerts, use window and burn-rate logic rather than applying hysteresis to a single gauge alone.

## 5. Critical Signals for Java Serverless

### 5.1. HTTP Functions

Minimum signals to monitor:

| Signal | Meaning | When to Alert |
| --- | --- | --- |
| Request count | Actual traffic | Traffic drops unexpectedly to 0 or surges to overload |
| Error ratio / 5xx | Failed requests | Burn rate exceeds threshold or absolute errors climb |
| p95/p99 duration | Tail latency | Breaches SLO in a window with sufficient samples |
| Timeout count | Function failed to finish | Rising steadily or impacting critical flows |
| Throttles / rejected concurrency | Unable to allocate execution capacity | Requests/events are delayed or rejected |
| Cold start / init duration | Runtime initialization overhead | Regression impacts latency or error budget |
| Dependency failures | External database/API errors | Prolonged dependency errors affecting multiple functions |

### 5.2. Queue and Event Consumers

For message-processing functions, error rate alone does not tell the full story. Monitor additionally:

- Oldest message age or event lag.
- Queue depth/backlog and backlog growth rate.
- Retry/redelivery count.
- DLQ message count and rate of messages entering the DLQ.
- Batch failures and partial batch responses.
- Consumer concurrency and throughput.
- Checkpoint/offset progress for streams.
- Elapsed time from event creation to business completion.

A queue with backlog while consumers continue processing successfully may be normal during peak hours. Alerts should rely on age/SLA and backlog trends rather than raw message counts alone.

### 5.3. Long-Running Workflows

For Durable Functions or similar workflow engines, monitor:

- Unusual spikes in failed/terminated instances.
- Instances running longer than business SLAs.
- Activity retry counts and activity durations.
- Workflows waiting past deadlines for external events.
- Workflows stuck in a single state.
- Compensation failures.
- Storage/task hub backlog or provider throttling.

An instance in `Running` state may legitimately be waiting on a timer for hours by design. Alert only when instance age or time spent in a state exceeds expected SLAs.

### 5.4. Cost and Usage Anomalies

Track cost by service, environment, function, tag, and time:

- Function compute cost growing faster than traffic.
- Unusual invocation spikes caused by retry loops or bot traffic.
- Memory/duration increases after a release.
- Sudden jumps in log ingestion or trace volume.
- Rising queue transactions, storage operations, or egress.
- Higher concurrency/instance counts driving downstream costs.

Budget alerts are typically financial notices or tickets rather than on-call pages. If cost spikes because a runaway loop is degrading the system, configure a dedicated operational alert to stop the source.

## 6. Severity and Alert Routing

### 6.1. Severity Classification

| Severity | Meaning | Typical Channel/Response |
| --- | --- | --- |
| SEV1 / Critical | Widespread outage, data loss, security risk, or severe transaction corruption | Immediate on-call page, incident commander, and escalation |
| SEV2 / High | Significant degradation, a critical business flow breaching SLO | Page owning team on-call, update incident |
| SEV3 / Warning | Risk of breaching SLO or growing backlog without severe impact yet | Ticket/chat channel, handle during shift or business hours |
| SEV4 / Info | Trend, capacity, or budget item needing review | Dashboard/report, no page |

Severity must reflect impact and urgency, not technical complexity. A single error in a test environment should not be SEV1 merely because of a long stack trace. Conversely, a lost business event or duplicate payment can be very severe even when overall error rate is low.

### 6.2. Owner-Based Routing

Every alert should include routing metadata:

- `service`: service/function name.
- `team`: accountable team.
- `environment`: production, staging, or development.
- `severity`: severity level.
- `region`: deployment region.
- `version`: affected revision or artifact.
- `runbook_url`: specific runbook link.
- `dashboard_url`: diagnostic dashboard.

Production alerts must route to the exact owning team with escalation if unacknowledged within the defined time. Staging alerts generally should not page on-call unless staging is a critical release or test gate.

### 6.3. Grouping, Deduplication, and Inhibition

A shared database outage can trigger alerts across 30 functions simultaneously. Sending 30 separate pages floods the on-call engineer. The alert manager should group by dependency, service, or incident fingerprint; deduplicate alerts sharing the same cause; and apply inhibition so low-level symptom alerts do not drown out the root-cause alert.

Do not group so broadly that you hide which specific function or region is failing. Alert groups must display the list of affected instances/services and allow drilldown.

Maintenance windows or deployment silences can suppress expected alerts during planned changes. Silences must have an expiration, an owner, and a reason; never use long-term silences to hide chronic errors.

## 7. Runbooks Must Be Linked Directly from Alerts

### 7.1. What Is a Runbook?

A runbook is an operational guide for a specific scenario. It helps the on-call responder verify impact, isolate root causes, take safe mitigation actions, verify recovery, and collect evidence.

A good runbook includes:

1. Scenario name and triggering symptom.
2. Service owner and escalation path.
3. Impact scope and related SLOs.
4. Dashboards, log queries, and trace filters to open.
5. Ordered verification steps, from lowest risk to deeper inspection.
6. Permitted mitigation actions.
7. Criteria to halt, roll back, or escalate.
8. How to verify recovery.
9. How to handle remaining data, retries, or DLQs.
10. Maintainer, review date, and links to supporting docs.

### 7.2. Linking Runbooks in Alerts

Alerts should include a specific URL to the runbook page matching the service and scenario. Example metadata structure:

```yaml
labels:
  service: order-api
  team: payments-platform
  environment: production
  severity: critical
  alert_id: FunctionHighErrorRate
annotations:
  summary: "order-api production error rate is above its SLO threshold"
  description: "Version {{ $labels.version }} has error ratio {{ $value }}."
  runbook_url: "${RUNBOOK_URL}"
  dashboard_url: "${DASHBOARD_URL}"
```

`RUNBOOK_URL` and `DASHBOARD_URL` are placeholders to replace with real URLs in your operations repository/wiki. Never leave production alerts pointing to fake links, generic home pages, or docs readable only by the authoring team. Verify access permissions using an on-call account.

### 7.3. Sample Alert Message

```text
[SEV2] order-api / production / ap-southeast-1

Condition: 5xx error ratio exceeded 2% for 10 minutes.
Impact: 8.4% of valid create-order requests failed in the last 10 minutes.
Candidate: version 42 accounts for most failures; stable version 41 is within baseline.
First action: compare version 42 traces and dependency errors; pause rollout if confirmed.
Owner: payments-platform
Dashboard: ${DASHBOARD_URL}
Runbook: ${RUNBOOK_URL}
```

Alert messages should be concise enough to read on a phone while carrying decision-making context. Detailed investigation steps belong in the runbook and dashboard.

### 7.4. Runbooks Must Not Contain Uncontrolled Dangerous Actions

Actions such as deleting queues, purging history, rotating keys, dramatically raising concurrency, or rolling back databases can cause data loss or heavy cost. Runbooks must specify:

- Preconditions permitting execution.
- Required permissions/roles.
- Impact and how to roll back the action.
- Required approvers if applicable.
- Post-action verification steps.

Never put secrets or tokens inside runbooks. Use a secret manager and describe how to access them under granted permissions.

## 8. Example Prometheus Alert Rule

The Prometheus rule below illustrates an alert with threshold, sustained duration, owner, and runbook link. Metric names are illustrative application metrics; map them to your actual exporter or telemetry backend when deploying.

```yaml
groups:
  - name: serverless-function-alerts
    rules:
      - alert: FunctionHighErrorRate
        expr: |
          (
            sum by (service, environment, version) (
              rate(function_invocations_total{outcome="error",environment="production"}[5m])
            )
            /
            clamp_min(
              sum by (service, environment, version) (
                rate(function_invocations_total{environment="production"}[5m])
              ),
              0.001
            )
          ) > 0.02
          and on (service, environment, version)
          sum by (service, environment, version) (
            increase(function_invocations_total{environment="production"}[5m])
          ) >= 100
        for: 10m
        labels:
          severity: page
          team: serverless-platform
        annotations:
          summary: "Function error ratio is above 2%"
          description: "{{ $labels.service }} version {{ $labels.version }} has elevated errors."
          runbook_url: "${RUNBOOK_URL}"
          dashboard_url: "${DASHBOARD_URL}"
```

In this example, the rule requires an error ratio above 2%, at least 100 invocations in the evaluation window, and the condition sustained for 10 minutes. `clamp_min` prevents division by zero; the minimum sample condition stops a single failed request from firing a ratio alert. Verify syntax and missing-series handling against your Prometheus/Alertmanager version.

Do not copy the exact same rule for every function. A low-traffic function may need synthetic checks or absolute error counts; a payment function may need stricter thresholds. Metric labels must have bounded cardinality; never place request IDs, user IDs, or nonces in labels.

## 9. Alerting on SLO Burn Rate

Conceptual PromQL example for an availability SLI using `http_requests_total` and label `status_class`:

```promql
sum(rate(http_requests_total{status_class="5xx"}[5m]))
/
sum(rate(http_requests_total[5m]))
```

That error ratio is divided by the error budget ratio to compute burn rate. With a 99.9% SLO, the error budget ratio is 0.001. A critical alert might require a burn rate above 14.4x across both 5-minute and 1-hour windows. Example expression:

```promql
(
  error_ratio_5m / 0.001 > 14.4
)
and
(
  error_ratio_1h / 0.001 > 14.4
)
```

`error_ratio_5m` and `error_ratio_1h` here are pre-defined recording rules. This illustrates multi-window logic; production rules need minimum traffic guards, valid-request filtering, proper label grouping, and missing-data checks.

With only a static `5xx > 5%` alert, teams can miss smaller prolonged incidents that burn through the error budget, or get paged by brief spikes with negligible impact. Combining burn rates and windows ties alerting directly to service objectives.

## 10. Integrating with Cloud Platforms

### 10.1. AWS Lambda and CloudWatch

CloudWatch provides metrics and alarms for Lambda. Key metrics to monitor include `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions`, and `AsyncEventsDropped`/async invocation metrics when relevant. Cold start/init duration may require additional telemetry or instrumentation depending on runtime and observability setup.

CloudWatch Alarms transition between `OK`, `ALARM`, and `INSUFFICIENT_DATA`; alarm actions can notify SNS or trigger configured workflows/automation. For Lambda:

- Split metrics by function and alias/version where appropriate dimensions exist.
- Avoid merging candidate and stable traffic so regressions are not masked.
- Monitor event source mappings, queue age, and DLQs using event-source metrics.
- Include runbook/dashboard URLs in alarm descriptions or notification templates.
- Verify alarm action permissions and destination health.

### 10.2. Azure Functions and Azure Monitor

Azure Functions can emit telemetry via Application Insights/Azure Monitor. Monitor invocations, failures, duration, dependencies, exceptions, host restarts, and trigger-specific backlogs. Azure Monitor alert rules can use metric alerts or log search alerts; Action Groups route notifications to email, SMS, webhooks, ITSM, or automation per configuration.

When designing:

- Separate function errors from dependency errors.
- Use operation/correlation IDs to connect invocations and dependency traces.
- Scope dimensions by function name, app, slot, region, and version when supported.
- Avoid overly broad log queries or alerting on isolated exceptions with no impact.
- Include runbook links in alert rules/action payloads and verify access permissions.

### 10.3. Google Cloud Functions and Cloud Run

Cloud Monitoring supports alerting policies on metrics, log-based metrics, and SLOs. Notification channels can send to email, chat, webhooks, or incident management integrations. For Cloud Run/function workloads, monitor request counts, latency, 4xx/5xx, instance counts, container startups, concurrency, and dependency errors.

For event-driven services, combine metrics from Pub/Sub or event sources such as undelivered messages, oldest unacked age, backlog, and dead-letter deliveries. Do not alert solely on container instance counts because scaling out can be a normal response to higher traffic.

### 10.4. Provider-Neutral Alert Metadata

Regardless of platform, standardize alert fields at the operations layer:

```json
{
  "alertId": "FunctionHighErrorRate",
  "service": "order-api",
  "environment": "production",
  "region": "ap-southeast-1",
  "version": "42",
  "severity": "SEV2",
  "owner": "payments-platform",
  "startedAt": "2026-11-17T10:15:00Z",
  "summary": "Request error ratio is above the service threshold",
  "runbookUrl": "${RUNBOOK_URL}",
  "dashboardUrl": "${DASHBOARD_URL}"
}
```

Standardization keeps routing and incident tooling consistent across multiple cloud providers. Actual payloads should match your alert manager/ITSM schema.

## 11. Java Instrumentation for Useful Signals

### 11.1. Cardinality-Controlled Metrics

Java functions can use Micrometer or the OpenTelemetry API to emit metrics. Use labels with small value sets such as `service`, `operation`, `outcome`, `region`, and `version`. Never use user IDs, order IDs, request IDs, or exception messages as labels because series counts can grow without bound.

Micrometer example:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderMetrics {
    private final Counter success;
    private final Counter failure;
    private final Timer duration;

    public OrderMetrics(MeterRegistry registry) {
        this.success = Counter.builder("order_function_invocations")
                .tag("outcome", "success")
                .register(registry);
        this.failure = Counter.builder("order_function_invocations")
                .tag("outcome", "failure")
                .register(registry);
        this.duration = Timer.builder("order_function_duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordSuccess() {
        success.increment();
    }

    public void recordFailure() {
        failure.increment();
    }

    public Timer duration() {
        return duration;
    }
}
```

This is an instrumentation example; metric export depends on the runtime and platform. For short-lived functions, ensure metrics flush/export before execution environments stop or use an appropriate extension/collector. Do not allow synchronous metric exports to add significant handler latency.

### 11.2. Structured Logging

Structured logs enable querying by service, function, invocation ID, trace ID, version, and error code. JSON example:

```json
{
  "timestamp": "2026-11-17T10:15:30Z",
  "level": "ERROR",
  "service": "order-api",
  "function": "CreateOrder",
  "version": "42",
  "invocationId": "inv-91",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT",
  "dependency": "payment-provider",
  "message": "Payment request exceeded timeout"
}
```

Never log access tokens, secrets, card details, or sensitive payloads. Use stable error codes instead of exception messages as dimensions/labels.

### 11.3. Trace Context and Correlation

Propagating trace context across HTTP headers or message metadata connects functions with dependencies. With OpenTelemetry, use trace/span IDs to pull failing traces from alerts. Preserve correlation IDs across queues, retries, and workflows; do not generate new IDs that break linkage to the original event.

Sampling may omit traces for some requests. Alerts must never depend entirely on trace sampling; metrics must detect problems reliably while traces assist deep investigation.

## 12. Sample Runbooks for Common Serverless Alerts

### 12.1. High Function Error Rate

**Trigger:** error ratio exceeds SLO threshold across two evaluation windows or error count climbs steadily with sufficient sample size.

**Checks:**

1. Identify affected service, region, function, version, and start time.
2. Compare error rates of stable/candidate versions and other regions.
3. Open traces/logs by invocation ID and error code.
4. Check dependency failures, recent deployments, secrets/config, and quotas.
5. Determine whether errors stem from input validation or runtime/dependency failures.

**Actions:**

- If the regression ties to a new version, pause rollout and roll back traffic per release procedure.
- If a shared dependency is failing, apply timeouts/circuit breakers and notify the dependency owner.
- If errors come from malicious input or abnormal traffic, enable rate limiting/WAF rules per approved procedure.
- Never blindly retry non-idempotent requests.

**Verify recovery:** error ratio and burn rate return to normal, latency stabilizes, and no backlog or duplicate side effects require reconciliation.

### 12.2. Rising Queue Age or Backlog

**Trigger:** oldest message age exceeds SLA or backlog grows steadily while consumer throughput trails producer rate.

**Checks:**

1. Identify affected queue/subscription, partition, consumer version, and when backlog began growing.
2. Inspect consumer concurrency, throttles, timeouts, and retry counts.
3. Check whether downstream databases/APIs are throttling or exhausting connections.
4. Inspect DLQ, poison messages, and schema versions of failing messages.
5. Estimate backlog growth rate and drain time at current throughput.

**Actions:**

- Increase concurrency only when downstream systems have capacity and quotas allow.
- Halt or roll back candidate consumer versions if they introduced errors or reduced throughput.
- Isolate poison messages per policy; never delete messages simply to shrink backlog.
- If downstream is overloaded, throttle consumer rate or apply backpressure.

**Verify recovery:** oldest message age declines, backlog trends downward, DLQ stops growing abnormally, and business completion lag returns within SLA.

### 12.3. New Messages in DLQ

**Trigger:** DLQ count rises or new messages arrive in a critical production queue.

**Checks:**

1. Identify message ID, source queue, event type, and schema version.
2. Read error metadata and retry history without logging sensitive payloads.
3. Check consumer releases, permissions, dependencies, and poison payloads.
4. Determine whether messages can be replayed safely and whether consumers are idempotent.

**Actions:**

- Fix the root cause before replaying.
- Keep messages in DLQ/quarantine during investigation.
- Replay in small batches and monitor outcomes.
- Never purge a DLQ merely to clear an alert.

**Verify recovery:** messages are processed or have explicit business disposition; DLQ count and message age are under control.

### 12.4. Throttling or Concurrency Near Quota

**Trigger:** throttles rise or concurrency remains above the defined capacity threshold.

**Checks:**

1. Identify affected function/region and account/service quotas.
2. Check invocation rate, duration, retry storms, and event source batch sizes.
3. Verify whether downstream connections/throughput can survive scaling out.
4. Check for anomalous traffic or mutual invocation loops.

**Actions:**

- Curb traffic sources or retry storms if possible.
- Adjust reserved/provisioned concurrency or quotas per capacity plan.
- Increase batch size/concurrency only when semantics and downstream capacity permit.
- Apply backpressure and client rate limits.

**Verify recovery:** throttles drop, latency/queue age stabilize, and downstream systems are not overloaded.

### 12.5. Anomalous Cost Spike

**Trigger:** cost rate exceeds budget or climbs sharply above baseline over a sustained window.

**Checks:**

1. Break down cost by service, function, region, tag, and resource type.
2. Compare invocations, duration, memory, log ingestion, egress, and retries.
3. Check recent deployments, abnormal traffic, and recursive triggers.
4. Determine whether the increase reflects legitimate workload or a loop/bug.

**Actions:**

- Throttle traffic sources or pause triggers per approved procedure if a runaway loop exists.
- Fix retry policies, log verbosity, or payload sizes if those are the cause.
- Never reduce memory/concurrency arbitrarily if doing so increases timeouts and retries.

**Verify recovery:** cost rate returns to a reasonable baseline while business workloads continue processing without breaching backlog SLAs.

## 13. Testing Alerts and Runbooks

Alert rules are code and require testing and review. Before production:

- Use sample data to verify rules fire accurately when thresholds are crossed.
- Confirm rules stay silent during low traffic or unexpected missing metrics.
- Verify alerts resolve when conditions recover.
- Confirm notifications reach the right team/channel with complete labels.
- Open runbook links from alerts using an on-call account.
- Practice runbooks in game days or incident simulations.
- Verify rollback/scale/replay actions have proper permissions and guardrails.
- Test alert grouping, deduplication, escalation, and silence expiration.
- Verify fallback alerting when the telemetry backend or notification channel fails.

Do not test only the query expression. A rule can be syntactically right while nobody receives notifications because Action Group/SNS/webhook permissions are misconfigured or the runbook URL is inaccessible.

### 13.1. Testing Thresholds with Fixtures

Prepare test datasets:

| Fixture | Expected Outcome |
| --- | --- |
| Low error ratio, normal traffic | Does not fire |
| High error ratio from a single request | Does not page when minimum sample is unmet |
| High, sustained error ratio | Fires with accurate severity |
| Brief spike followed by recovery | Does not fire if below sustained duration |
| Missing metric data | Missing-telemetry alert or unknown state per policy |
| Candidate failing, stable healthy | Alert tagged with candidate version |
| Both stable and candidate failing from dependency | Alert on dependency/service impact, not blaming candidate alone |
| Queue backlog rising while age remains in SLA | Warning or no alert per policy |
| Production DLQ receives a message | Fires at the business queue's configured severity |

### 13.2. Periodic Runbook Reviews

Every runbook needs an owner, review date, and version. After incidents, update investigation steps with new evidence; remove obsolete commands; verify dashboard/query URLs still work; confirm access permissions and escalation contacts. A runbook is not complete simply because a doc page shares the alert's name.

## 14. Reducing Alert Fatigue

Alert fatigue occurs when responders receive too many low-value, repetitive, or non-actionable alerts. Over time, they may start ignoring critical alerts too.

Ways to reduce it:

- Page only for urgent impact; send warnings to tickets or chat channels.
- Use SLO burn rates instead of paging on every minor threshold.
- Combine minimum sample sizes with sustained durations.
- Group alerts by incident/dependency.
- Deduplicate identical fingerprints and suppress symptom alerts when root-cause alerts fire.
- Auto-resolve once recovery conditions stabilize.
- Assign owners to every alert and delete unowned alerts.
- Measure alerts per incident, false-positive rate, off-hours pages, and acknowledgment times.
- Review alerts after every incident and architectural change.

Never reduce alert fatigue by muting noisy alerts without fixing the underlying issue. If an alert is not actionable, fix its query, threshold, routing, or runbook.

## 15. Managing Missing Data and Alerting System Failures

No metrics does not mean the service is healthy. A function may stop emitting metrics due to exporter failures, revoked permissions, blocked networking, or telemetry pipeline outages.

Distinguish:

- **Zero traffic:** genuinely no requests/events during that window.
- **Zero errors:** requests occurred with no recorded errors.
- **Missing telemetry:** no samples or pipeline stopped delivering data.
- **Stale data:** latest metric is too old relative to the update interval.

For critical services, configure separate alerts for the telemetry pipeline, heartbeats, or synthetic probes. Never use `or vector(0)` or unconditionally coerce missing series to 0 if doing so masks a dead exporter.

The notification path must also be monitored: check the alarm engine, webhooks, SNS/Action Groups/notification channels, and escalation services. Run periodic synthetic alert tests to verify the entire path from rule evaluation to responder delivery.

## 16. Runbook-Linked Alert Design Checklist

- [ ] Alert ties to an SLI/SLO or an operational limit with clear actionability.
- [ ] Threshold, evaluation window, sustained duration, and minimum sample size are defined where needed.
- [ ] Severity reflects impact and urgency.
- [ ] Includes service owner, team, environment, region, and version.
- [ ] Alert distinguishes candidate/stable versions or key cohorts.
- [ ] Message describes symptom, impact, and breached condition.
- [ ] Includes a direct `runbook_url` for the exact scenario.
- [ ] Includes dashboard/log/trace links to assist investigation.
- [ ] Runbook covers verification steps, safe actions, rollback/escalation, and recovery validation.
- [ ] URLs and access permissions were verified with an on-call account.
- [ ] Alert grouping, deduplication, inhibition, and silences are bounded.
- [ ] Alerts exist for missing telemetry and notification pipeline failures.
- [ ] Firing, resolving, missing data, and routing have been tested.
- [ ] Rule and runbook have an owner and review date.
- [ ] A post-incident process updates or retires low-value alerts.

## 17. Conclusion

Actionable alert thresholds help operations teams focus on issues affecting users and service objectives. Start from SLIs/SLOs and error budgets, choose thresholds accounting for duration, sample size, and burn rate, and classify severity by impact. For serverless, monitor HTTP errors/latency/concurrency alongside queue age, retries, DLQs, workflow age, and cost anomalies.

Every production alert needs an owner, metadata, a dashboard, and a direct runbook URL. Runbooks must specify verification steps, safe mitigations, rollback/escalation criteria, and recovery checks. Test both rules and notification paths, watch for missing telemetry, and review alerts after incidents to keep them valuable. An alert is truly useful only when the recipient understands what is happening and knows the exact next step to take.

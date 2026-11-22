# Logs and Alerts in Observability for Java Applications

## 1. The Problem: We Have Logs, So When Should We Alert?

A Java application continuously emits events: requests complete, database connections time out, jobs rerun, messages are redelivered, exceptions are thrown, and circuit breakers open. **Logs** help describe those events. **Alerts** must help on-call operators know **when a condition is important enough to require action**.

These are two different questions:
- **Log:** "What happened at this moment, with which operation and context?"
- **Alert:** "Is there something abnormal with enough impact that someone needs to handle it immediately or on a schedule?"

For example, a request receiving a 500 error may produce an `ERROR` log and a metric recording a failed request. That **does not mean** the system should wake up the on-call engineer immediately. If the error rate rises continuously, affects user checkout, and exceeds an agreed criterion, an alert may be appropriate. Conversely, a service that stops sending telemetry altogether may **have no ERROR lines left** while still experiencing an outage.

**Key takeaway:** logs are a data source for diagnosis; an alert is a **decision based on signals, time windows, impact level, and response policy**. Do not equate `logger.error(...)` with "an alert has been sent."

Objectives after this lesson:
1. Distinguish logs, metrics, traces, events, and alerts in observability.
2. Understand log-based alerts, metric-based alerts, and SLI/SLO-based alerts; recognize the limitations of each.
3. Design rules with windows, thresholds, minimum traffic, persistence, deduplication, grouping, severity, recovery, and no-data policies.
4. Write a standalone Java 17 example simulating a **log summary and alert state machine** with deterministic stdout output.
5. Design runbooks, routing, escalation, dashboards, and correlation for actionable alerts.
6. Test alerts to reduce false positives, false negatives, alert storms, and sensitive data exposure.

## 2. Distinguishing Logs, Metrics, Traces, and Alerts

| Component | Question Answered | Example | Notes |
| --- | --- | --- | --- |
| **Log** | Which specific event occurred? | `event=db_timeout requestId=req-17` | Contains detailed metadata; volume can be large |
| **Metric** | How is the frequency/magnitude changing? | `http_requests_total{result="error"}` | Used to compute rates, ratios, and latency; labels need low cardinality |
| **Trace** | Which steps did a processing flow pass through? | HTTP → order-service → database | Helps reveal the critical path, dependencies, and bottlenecks |
| **Alert rule** | Which condition indicates risk or impact? | Error ratio exceeds threshold long enough | Not just a single log event |
| **Alert instance** | For which group is the rule firing? | `HighErrorRatio{service="checkout"}` | Has FIRING/RESOLVED states depending on the management system |
| **Notification/page** | Who receives the notification and what should they do? | On-call receives a page with a runbook | Has routing, grouping, escalation, and silence policies |

**Log level is not alert severity.** `ERROR` reflects how a developer assessed an event at the time it was logged. Alert severity such as page/ticket/info reflects operational impact and urgency. A component might only log `WARN` due to continuous retries yet trigger a critical alert when the service fails to meet its SLO.

**Metrics do not replace logs.** Metrics show that the error rate jumped from 0.2% to 8%, while logs/traces help identify which requests and dependencies are affected. Conversely, having only per-request logs makes it very hard to recognize the overall pattern without proper aggregation.

**Traces do not automatically guarantee every request is observed.** Sampling, agent drops, and missing instrumentation can leave traces incomplete. When designing alerts, you must know how much coverage and reliability a signal has.

## 3. From an Exception to an Alert: The Right Path

A common flow:

```text
User request / background job
               |
               v
        Java application
               |
          +----+----+
          |         |
          v         v
    Structured log  Counters/histograms
          |         |
          v         v
     Log collector  Metrics pipeline
          |         |
          +----+----+
               |
               v
     Query / aggregation / SLI
               |
               v
     Rule + window + thresholds
               |
               v
    Alert state: pending / firing
               |
               v
    Dedup + group + route + silence
               |
               v
       Notification / page
               |
               v
  Dashboard + logs + traces + runbook
```

This diagram is a **conceptual model**; not every architecture has to send logs through the same system as metrics. Some tools support log-based alerts directly on the log store, while others convert logs into metrics before evaluating them; failures of the monitoring system itself must be observed separately.

### 3.1. Three Principles

1. **Detect with stable signals:** request error rate, latency, backlog, queue lag, job failure rate, dependency status, or the number of security events requiring response.
2. **Investigate with context:** when an alert opens, query logs/traces by `service`, `operation`, `error_code`, `trace_id` (when appropriate), deployment version, and time range.
3. **Respond with ownership:** an alert must indicate who handles it, the urgency level, user impact, verification steps, and mitigation actions.

Do not use an increase in `ERROR` log lines as a success metric for observability. The goal is to detect incidents accurately, quickly, with low noise, and to support safe remediation.

## 4. Log-Based Alerts: When Are They Appropriate?

A **log-based alert** evaluates a condition over collected log records: the count of `event=job_failed` within 10 minutes, the occurrence of code `AUTH_INTEGRITY_VIOLATION`, or the ratio of an error code among parsed events.

This approach is useful when:
- The system does not yet have a dedicated metric for a rare but important event.
- There is a **standardized event code**, such as `AUDIT_PIPELINE_WRITE_FAILED`, that can be queried reliably.
- You want to detect a sequence of logs describing a subsystem state such as prolonged failover or a poison message.
- You have a sufficiently reliable log pipeline with known ingestion latency bounds.

However, you must clearly understand the risks:

| Risk | Why It Causes Wrong Alerts |
| --- | --- |
| **Logs never reach the sink** | Agent down, full queue, process crash, or network error causes missing records |
| **Duplicate log entries** | Logger additivity, collector retries, or duplicate delivery inflate counts |
| **Sampling / rate limiting** | Dropped log lines make counters differ from actual event counts |
| **Text message changes** | Substring/regex queries break when developers change wording |
| **Log level changes** | Events may no longer be logged at the old level |
| **Ingestion time skew** | Late or out-of-order events cause windows to be computed inaccurately |
| **High cardinality** | Grouping by requestId/userId creates many alert instances |
| **Missing denominator** | "100 errors" does not indicate error rate when total requests vary |

**Solution:** if you use log alerts, rely on `event_code`, `service`, `result`, and a governed schema; control duplicate ingestion and no-data, and always distinguish **event time** from **ingestion time**. When a signal is an important SLI, it is usually better to emit a **metric counter/histogram right where the outcome is known** and use logs for investigation.

## 5. An ERROR Log Is Not Automatically a Page

Consider three examples:

**A. A single random failed request:**

```text
ERROR event=payment_dependency_failed errorCode=UPSTREAM_TIMEOUT
```

A single event does not determine the blast radius, frequency, or recoverability. You can record a counter and trace for investigation, but paging on every exception easily causes alert fatigue.

**B. Checkout failure rate spikes over 10 minutes:**

```text
metric: checkout_requests_total{result="error"} increasing continuously
metric: checkout_requests_total{result="all"} still has traffic
alert: CheckoutErrorBudgetBurn is FIRING
```

This is a user-impacting pattern. It may be worth paging if it violates SLO policy, has sufficient impact, and is actionable.

**C. The system stops emitting metrics/logs:**

```text
heartbeat: missing
scrape_target: unavailable
application log: no new lines
```

"No ERRORs" **does not mean** the system is healthy. For critical services, you need an availability or telemetry-missing alert, distinct from normal error rate alerts.

### 5.1. Symptom-First, Cause-Second

**Symptom alerts** reflect what customers experience: high error rates, latency exceeding targets, orders failing to be created, or an unprocessed message backlog. **Cause alerts** reflect potential root causes: a nearly full database connection pool, GC pauses, disk usage, or rising retry counts.

An effective policy usually prioritizes paging on **impactful symptoms**, while cause signals support diagnosis or tickets. That does not mean eliminating all cause alerts: a certain risk with severe consequences—such as disk nearly full before writing audit logs, an expiring certificate, or a queue unable to drain—may also require proactive alerting.

## 6. Designing Meaningful Alert Rules

A good rule is more than `count > 10`. It must answer:

1. **Signal:** what value is measured? From logs, metrics, synthetic checks, or health signals?
2. **Scope:** which service, environment, cluster, region, or tenant? Avoid high-cardinality labels.
3. **Window:** what time range is evaluated, and how is late-arriving data handled?
4. **Threshold:** what level is concerning based on baseline/SLO/actionability?
5. **Persistence/for:** how long must the condition hold to filter out noise?
6. **Minimum volume:** when traffic is too low, is a percentage reliable enough?
7. **Grouping/dedup:** do multiple instances failing from the same cause create one incident or hundreds of notifications?
8. **Recovery:** when does the alert resolve, and is there anti-flapping/hysteresis?
9. **No-data:** are there no samples because the service is idle or because the collector failed?
10. **Owner, severity, runbook:** who handles it, what needs to be done, and what is the impact?

### 6.1. Count, Ratio, and Traffic

For example, within the same window:
- 5 errors out of 10 requests is a 50% error rate, but the sample size is small.
- 500 errors out of 100,000 requests is 0.5%, but the number of affected users is much larger.
- 0 `ERROR` lines in logs does not prove a 0% error rate if logging is being dropped.

Therefore, when alerting on **error ratio**, you need a clear denominator, a low-traffic policy, and complete metrics. An **absolute count** alert may fit rare events that must be handled individually, such as audit data failing to write; however, you must explain why count rather than ratio makes sense.

### 6.2. Window, Persistence, and Latency

Evaluating over a 1-minute window can be sensitive but noisy; a 30-minute window is more stable but slower to detect issues. With `for: 10m`, the condition must be observed continuously according to the alert engine's logic before transitioning to firing. A "10m" duration is an example configuration, **not a universal best practice** for every alert.

Do not forget:
- Late-arriving data or sampling can make different windows diverge.
- Dashboard timezone settings do not remove the need for consistent timestamps.
- How the engine handles missing data/stale series affects PENDING/FIRING transitions.
- A query running every 30s does not guarantee a reaction in exactly 30s.

### 6.3. Recovery and Flapping

If an alert opens at error rate `> 5%` and closes immediately when it drops to 4.9%, a value oscillating near the threshold can repeatedly open and close. You can use:
- A sustained condition duration before opening.
- Different open/close thresholds (**hysteresis**).
- Averaged windows or multiple windows.
- Cooldown, deduplication, and grouping in the alert manager.
- Auto-resolve that checks for actual data rather than closing by default when telemetry disappears.

Hysteresis is not a substitute for investigating the cause; a rule that is too slow may miss short but severe outages.

## 7. Alerting on SLI, SLO, and Error Budget

An **SLI** is a metric measuring experienced quality, such as the ratio of successful requests or the ratio of requests below a latency threshold. An **SLO** sets a target for an SLI over a period; an **error budget** is the allowable unreliability within that target.

An **illustrative** example, not an SLO applicable to every service:
- Success SLO: **99.9%** over 30 days.
- Error budget fraction: `1 - 0.999 = 0.001` (0.1% of total eligible requests).
- If the actual error ratio over a period is **2%**, the budget burn rate equals `0.02 / 0.001 = 20` times the average allowable rate for the evaluated period.

**Burn rate** ties the error rate to the allowable budget rather than paging on an arbitrary threshold. Alert design can combine **multi-window, multi-burn-rate**: a short window detects incidents quickly, a long window reduces noise, and paired conditions match different urgency levels.

Notes:
- An SLI must clearly define the denominator (**eligible requests**) and numerator (**bad requests**). Do not use "total ERROR logs" as the numerator if one request can emit multiple logs or a failed request does not print `ERROR`.
- A 4xx status from invalid input usually does not count as a service error in an availability SLI, though the definition depends on the product contract.
- For latency SLIs, do not take an unweighted average of p95 across multiple instances and treat it as system-wide p95.
- Define SLOs for critical user-facing journeys first, rather than inventing an SLO for every log line.
- Burn rate thresholds and windows must be designed around the error budget policy; the numbers above are only for learning the formula.

**Relationship:** Logs help investigate specific requests that degraded the SLI; SLO/burn-rate alerts tell you whether that condition is worth waking up the operations team.

## 8. Standalone Java 17 Example: Separating Event Logs and Alert Lifecycle

The following example uses `java.util.logging` (JUL) from JDK 17 and a simulated evaluator. It has two output streams:
- `LOG INFO ...`: summary of request/failure counts for each fixed 1-minute window.
- `ALERT OPEN/RESOLVED ...`: alert state-change events. This is **console output only**; it **does not send notifications, does not connect to Alertmanager, and is not a production alert engine**.

Demo rules:
1. Evaluate only when there are at least **20 requests** in the window.
2. If failures are **20% or higher**, transition from inactive to active and emit **one** OPEN alert.
3. When a window with sufficient traffic has a failure rate below 20%, transition from active to inactive and emit RESOLVED.
4. If already active and still violating, do not emit OPEN again for every window.
5. Windows with fewer than 20 requests **do not open or close the alert**. This is an illustrative choice, not a replacement for a complete no-data policy.

Create `LogAndAlertDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogAndAlertDemo {
    private record Window(int minute, long requests, long failures) {}

    private static final class PlainHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println("LOG " + record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static final class Evaluator {
        private final Logger logger;
        private boolean active;

        Evaluator(Logger logger) {
            this.logger = logger;
        }

        void evaluate(Window window) {
            logger.info("event=window_summary"
                    + " minute=" + window.minute()
                    + " requests=" + window.requests()
                    + " failures=" + window.failures());

            // Assume request/failure counts are aggregated accurately.
            // Keep the current state if the sample size is not large enough.
            if (window.requests() < 20) {
                return;
            }

            boolean unhealthy =
                    window.failures() * 100L >= window.requests() * 20L;

            if (unhealthy && !active) {
                active = true;
                System.out.println(
                        "ALERT OPEN rule=high_failure_ratio minute="
                                + window.minute());
            } else if (!unhealthy && active) {
                active = false;
                System.out.println(
                        "ALERT RESOLVED rule=high_failure_ratio minute="
                                + window.minute());
            }
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.observability.alert");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler handler = new PlainHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            Evaluator evaluator = new Evaluator(logger);
            evaluator.evaluate(new Window(0, 100, 2));
            evaluator.evaluate(new Window(1, 100, 25));
            evaluator.evaluate(new Window(2, 120, 30));
            evaluator.evaluate(new Window(3, 100, 1));
            evaluator.evaluate(new Window(4, 10, 5));
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac LogAndAlertDemo.java
java LogAndAlertDemo
```

**Exact stdout** when run in a fresh JVM, with no other code interfering with the logger:

```text
LOG INFO event=window_summary minute=0 requests=100 failures=2
LOG INFO event=window_summary minute=1 requests=100 failures=25
ALERT OPEN rule=high_failure_ratio minute=1
LOG INFO event=window_summary minute=2 requests=120 failures=30
LOG INFO event=window_summary minute=3 requests=100 failures=1
ALERT RESOLVED rule=high_failure_ratio minute=3
LOG INFO event=window_summary minute=4 requests=10 failures=5
```

### 8.1. Explaining the Output

- **Minute 0:** 2/100 = 2%, below 20%; only LOG is emitted.
- **Minute 1:** 25/100 = 25%, above threshold; transitions to active and emits **one ALERT OPEN**.
- **Minute 2:** 30/120 = 25%; still violating, but the alert is already active, so **no second OPEN is created**.
- **Minute 3:** 1/100 = 1%; sufficient traffic and below threshold, emits **ALERT RESOLVED**.
- **Minute 4:** 5/10 = 50% but only 10 requests; the demo treats data as insufficient, keeps the current state, and does not trigger an alert. A production policy may differ if 5 errors represent a serious incident for a low-traffic service.
- `Logger.setUseParentHandlers(false)` prevents the root handler from adding timestamps/other formatting, keeping stdout deterministically comparable.
- `PlainHandler` prints directly to stdout for learning purposes; it has no queue/network and is not a production appender.
- `ALERT OPEN/RESOLVED` is a **line simulating an action outside the logger**, not because calling `logger.severe` automatically gives you a pager.

### 8.2. Why This Java Sample Is Not Yet a Production Alert Engine

Intentional limitations:
- Windows are pre-aggregated `Window` records; the program **does not** count real HTTP requests or handle late/out-of-order data.
- There is no persistence for `active`; a restart forgets the alert state and may emit OPEN again.
- The 20%/20-request threshold is pedagogical and does not reflect real SLOs.
- There is no moving window, hysteresis, `for` duration, silence, routing, cluster-wide deduplication, or escalation.
- If no new windows arrive, the demo **does not know telemetry is broken**; a separate no-data/missing-heartbeat alert is required.
- There are no label scopes across multiple services, instances, regions, or tenants; it simulates only a single rule.
- It does not validate counts (e.g., `failures <= requests`) or guard against overflow for unrealistic `long` values. Production needs reliable metric sources and validation.
- Using `System.out.println` to simulate alerts has no ACK, retries, or notification delivery. Alertmanager or an equivalent platform handles those steps.

**Core learning point:** Many logs/summaries do not mean many pages; a rule requires **state and policy**. At the same time, an "ALERT OPEN" log is only an event—it does not prove anyone was successfully notified.

## 9. Integrating Observability in a Java Web Service

### 9.1. Log with Event Codes Instead of Free-Form Text

A safe, structured, and easily queryable log:

```java
// SLF4J integration snippet: logger and variables are already created in the application.
logger.warn("event=dependency_failure service={} operation={} "
                + "dependency={} errorCode={} requestId={}",
        "checkout", "place_order", "payment-gateway",
        "UPSTREAM_TIMEOUT", safeRequestId);
```

This is **not a standalone program**. `safeRequestId` must be server-generated or validated and bounded in length/characters—do not use arbitrary raw headers. Do not log raw request bodies, Authorization bearer tokens, session IDs, or payment card details.

If you want to alert from logs, query `event=dependency_failure` and `errorCode=UPSTREAM_TIMEOUT` after schema validation by a parser; **do not** search for a phrase like "failed!" that changes with wording or exception messages.

However, **a dependency failure log does not necessarily equal a final failed request**. If a retry succeeds, the attempt-level log still exists, but the request-level failure metric does not increment. This is one reason not to use `WARN`/`ERROR` counts as a user-facing SLI.

### 9.2. Emit Metrics at the Boundary Where the Final Outcome Is Known

In a Java web application, the middleware/filter/observation layer typically knows the HTTP status, duration, and route template. Application code should emit:
- A counter for eligible requests by service/route group/status class or normalized outcome.
- A counter for failed requests according to the **SLI definition**.
- A latency histogram or corresponding distribution measurement.
- Counters for retries, dependency failures, circuit breakers, and logging pipeline health.

If using Micrometer/Spring Boot, meter names and available tags **depend on your stack and version**. Do not assume every application exposes `http_requests_total` or `outcome=error` as in the example rule below. **Verify the actually emitted metrics** before configuring alerts.

An API may return 4xx due to invalid user input, which should not be counted in an availability SLI if the SLI contract excludes it. For batch/message consumers, the final outcome may be record committed, message acknowledged, DLQ, or backlog; do not evaluate them like HTTP requests when semantics differ.

### 9.3. Structured Fields with SLF4J 2.x

```java
// SLF4J 2.x integration snippet + backend/encoder supporting key-value pairs.
logger.atError()
      .addKeyValue("event", "operation_failed")
      .addKeyValue("service", "checkout")
      .addKeyValue("operation", "place_order")
      .addKeyValue("error_code", "PAYMENT_DEPENDENCY_UNAVAILABLE")
      .addKeyValue("request_id", safeRequestId)
      .log("Checkout operation failed");
```

`atError()` does not send an alert by itself. Key-value pairs are only emitted according to your backend/encoder configuration. If you want a stack trace, consider that exception messages/causes may contain credentials/PII; do not attach a throwable to every log just because an alert is firing.

### 9.4. Correlating from Alerts Back to Logs/Traces

Suppose alert `CheckoutHighErrorRatio` has labels `service=checkout`, `environment=prod`, `region=ap-southeast`:
- Open the dashboard filtered to the matching service/environment/region and the alert's time range.
- Check error code distribution and recently deployed versions.
- Filter logs by `service=checkout` and `error_code`; use sample `requestId`/`traceId` values **inside logs/traces**—do not put unique IDs into alert labels.
- Compare latency, saturation, dependency errors, and traffic changes.
- From trace samples, pinpoint whether the bottleneck is at the payment gateway, database, or a local bug.

**Grouping labels by request ID/user ID is the wrong layer:** if 10,000 requests fail together, one rule will generate thousands of alert instances. Keep routing labels at the level of an **accountable unit**, and keep high-cardinality IDs in logs/traces.

## 10. Illustrative Rule: Prometheus/Alertmanager Style

The YAML example below **assumes** the application already exports counter `http_requests_total` with labels `service` and `result`, where `result="error"` is properly defined for the target SLI. These are not guaranteed default metric names across all Java frameworks.

```yaml
groups:
  - name: checkout-sli
    rules:
      - alert: CheckoutHighErrorRatio
        expr: |
          (
            sum(rate(http_requests_total{service="checkout",result="error"}[5m]))
            /
            clamp_min(
              sum(rate(http_requests_total{service="checkout"}[5m])),
              0.001
            )
          ) > 0.05
          and
          sum(rate(http_requests_total{service="checkout"}[5m])) > 1
        for: 10m
        labels:
          severity: page
          team: checkout
        annotations:
          summary: "Checkout error ratio elevated"
          description: "Investigate checkout outcome and dependency errors"
          runbook_url: "https://example.test/runbooks/checkout-errors"
```

**Do not copy this rule into production and assume it is validated.** Understand that:
1. **Metric names/labels are assumed.** If the real names differ or `result="error"` does not exist on the corresponding counter, the expression may return empty data.
2. `rate(...[5m])` estimates the counter's per-second increase over 5 minutes, not the absolute request total. Counters can reset and scrapes can be missed.
3. Dividing by total request rate evaluates the ratio. `clamp_min(...,0.001)` prevents near-zero division, while the `>1` clause is a **traffic condition** (in requests/second) to avoid paging on extremely low volume.
4. `>0.05` means more than 5% errors in the window; this is an **illustrative threshold** that must match actual needs/SLOs.
5. `for: 10m` requires the condition to persist according to the rule evaluator's semantics before becoming FIRING; it does not reflect a guaranteed end-to-end latency.
6. `severity: page` is only a routing label. Without Alertmanager/notification policy configuration, this label **will not send SMS or place phone calls on its own**.
7. The runbook URL uses the example domain `example.test`, not an existing runbook.
8. This rule lacks no-data alerts, SLO burn-rate, multi-window checks, regional scoping, inhibition, and missing-telemetry handling.
9. SLIs should align labels and denominators across both counters; do not mix incompatible traffic types.

### 10.1. Alerting Directly from Log Events

If your log aggregation tool supports it, you can define a query in **tool-neutral pseudocode**, not standard SQL/PromQL syntax:

```text
SOURCE = structured_logs
FILTER service == "audit-api"
   AND event == "audit_write_failed"
GROUP BY environment, service
WINDOW = last 5 minutes
CONDITION count > 0
ACTION route to security/on-call with event reference
```

An event like `audit_write_failed` may warrant immediate alerting because it involves losing a mandatory audit trail, but only when event semantics guarantee it is not a recovered retry and the log pipeline has suitable reliability. If the component writing audit/logs fails completely, it may **emit no event at all**; independent health/synthetic monitoring is required.

## 11. Alert Lifecycle: Pending, Firing, Acknowledged, Resolved

An alert rule can have both evaluator-internal states and incident-handling states:

```text
NORMAL
  |
  | condition violated
  v
PENDING
  |
  | sufficient duration/persistence
  v
FIRING ---> notification routed
  |              |
  |              v
  |          ACKNOWLEDGED / OWNED
  |              |
  |         investigate / mitigate
  |
  | recovery condition met
  v
RESOLVED
```

Depending on the tool, state names vary; **ACKNOWLEDGED is not a universal Prometheus rule state** and typically belongs to the notification/incident management system. `RESOLVED` also does not necessarily prove the root cause is completely fixed—only that the rule's condition is no longer firing given available data.

Key concepts:
- **Pending:** the condition is violated, but not yet for long enough to open.
- **Firing:** the rule satisfies its trigger logic.
- **Notification delivered:** the tool sends a notification; it can be delayed, fail, or be silenced.
- **Acknowledged:** a person/team has taken ownership of the incident in the corresponding workflow.
- **Resolved:** the rule condition is no longer true according to evaluation logic.
- **Silenced/muted:** notifications are suppressed by policy; this does not mean the issue has disappeared.
- **Inhibited:** a secondary alert is suppressed while a root alert in the same scope is firing.

**Do not design alerts that alter business behavior solely because a notification fired.** A rule meant for humans does not replace application circuit breakers, retry budgets, rate limits, transaction rollbacks, or failovers.

## 12. Grouping, Deduplication, Routing, and Escalation

For example, a database failure causes 200 pods to experience timeouts simultaneously. If every pod triggers a page, on-call engineers get flooded and struggle to identify the root cause.

**Grouping** bundles alerts sharing the same service/environment/incident signal into one useful group. **Deduplication** prevents sending the same alert instance repeatedly without end. **Inhibition** suppresses downstream alerts when a clearly related root alert is already active. **Routing** directs alerts to the right team.

| Policy | Purpose | Example |
| --- | --- | --- |
| Group by `service,environment,alertname` | View one incident as one group | 50 checkout pods with the same high error ratio |
| Dedup by stable fingerprint/labels | Do not create a new incident while the rule remains firing | A single alert instance is updated |
| Inhibit downstream | Reduce secondary alerts when root outage is clear | DB unavailable causing multiple API failures |
| Escalation | Escalate if on-call does not respond | Primary on-call → backup |
| Time-bounded silence | Planned maintenance without notification spam | Silence during a deployment window |
| Routing by team/severity | Reach the right responder | Page for user-facing outage, ticket for non-urgent |

**Pitfall:** Grouping too broadly can hide two independent incidents; grouping too narrowly turns one outage into thousands of pages. Do not use request ID, user ID, event ID, full exception message, or pod UID as default group keys if they cause unbounded cardinality.

Assign an owner to every rule; when a service changes teams, update routing and runbooks. An unowned alert can be as dangerous as having no alert at all.

## 13. Writing Actionable Alert Notifications

A good notification should concisely answer:
- **What is affected?** Service, environment, region, user journey.
- **What is the impact and confidence?** Error ratio, request volume, latency, backlog, threshold.
- **Since when?** Time window, firing start time, current status.
- **What is the first action?** Check dashboard, rollback, dependency status, or SLO evaluation.
- **Where is the evidence?** Links to dashboard/log query/trace samples and runbook.
- **Who is responsible?** Team and escalation policy.

Illustrative notification content:

```text
CheckoutHighErrorRatio [PROD] — FIRING
Impact: checkout 5xx/error ratio over threshold for 10m
Scope: service=checkout, region=ap-southeast
Evidence: dashboard checkout SLI; errors by code; recent deploys
Next: check payment dependency, new version, rollback criteria
Owner: checkout on-call | Runbook: internal/checkout-errors
```

Do not attach full request bodies, access tokens, or stack traces containing secrets to Slack, email, SMS, or tickets. Notifications are also **a data sink**, with their own retention and access permissions. Include only safely classified labels and sample metadata.

### 13.1. Runbooks Must Be Genuinely Useful

A good runbook includes:
1. An explanation of what the rule means and how to verify whether it is genuinely firing or a telemetry failure.
2. Verified queries/dashboards with the right time range and labels.
3. Triage steps ordered by impact: user impact, recent deploys, dependencies, saturation, logs/traces.
4. Safe mitigation actions (feature rollback, load shedding, dependency bypass) along with **conditions and authorization to execute them**.
5. Recovery verification criteria, not just "notifications stopped."
6. Escalation path and where to record postmortems.
7. Security boundaries—never copy raw secrets from logs into chat/tickets.

If an alert does not lead to a specific action or decision, consider **lowering its severity, moving it to a dashboard/ticket, or removing the rule**.

## 14. Alerting for Messaging Systems and Background Jobs

In Kafka/RabbitMQ/SQS consumers or job schedulers, "one exception" usually does not equal an outage. Measure **final outcomes and processing progress**:

- **Queue lag/backlog:** unprocessed message count or processing rate falling behind SLA.
- **Oldest message age:** actual delay compared to business requirements.
- **Processing failure ratio:** failures over attempts or unique messages according to chosen semantics.
- **DLQ rate/depth:** messages sent to a dead-letter queue or discarded after retries.
- **Idempotency duplicates:** duplicate deliveries; an increase may indicate ack/commit/rebalance issues.
- **Job missed deadline:** tasks not completing on schedule, even without exceptions.
- **Consumer liveness:** no longer processing messages while the queue has a backlog, rather than relying solely on `ERROR` logs.

When a message is redelivered 10 times, the listener might log 10 warning lines and one final failure. If an alert counts warning logs, it can **amplify the impact of a single logical message**. Choose a clear denominator: attempt failures, unique messages failed, or number of unsuccessful business operations. Each definition serves a different type of alert.

Do not put message payloads, cookies, credentials, or full headers into alerts. Use `eventId` for trace/log investigation in access-controlled systems; do not use it as an alert label.

## 15. Alerting for Logging/Observability Pipeline Failures

The observability system itself can fail:
- File appender fails to write.
- Async logging queue fills up and drops events.
- Collector backlog grows or batches fail to send.
- Storage/index becomes unavailable or cost/retention limits are exceeded.
- Scrape target goes down; metric series disappear.
- Alert evaluator stops running or notification delivery fails.

You need **meta-monitoring** or independent monitoring for critical telemetry paths. Examples of stable indicators:
- `log_events_dropped_total` and queue depth.
- Collector ingest errors, export retries, and backlog.
- `up` or health/synthetic checks for scrape targets if using Prometheus.
- Alertmanager/notification delivery failures and rule evaluation errors.
- Count of failed audit writes to durable storage if auditing is mandatory.

In particular, a rule like `count(log ERROR) == 0` does not prove the system is safe. If the appender dies, the log count is also 0. Use heartbeats/synthetic checks from an independent vantage point to detect "abnormal silence."

**Do not log appender errors through the failing appender itself**, as that can cause recursion. Use a status logger/internal diagnostics and a separate metrics/health channel with rate limiting and failure isolation.

## 16. Security and Privacy of Log-Driven Alerts

Logs and alerts can contain personal data, user identifiers, or system secrets. An exception might print a raw URL containing an API key; an alert generated from raw logs could forward that string to email, phones, and incident management systems.

Principles:
1. **Never log secrets at the source:** passwords, tokens, Cookies, private keys, signed URLs, raw request bodies, or unnecessary PII.
2. Allow only safe fields in alert labels and annotations: service, environment, error code, aggregate SLI, runbook link.
3. Set separate read, query, export, and retention permissions for logs, dashboards, alert history, and incidents.
4. Do not use raw exception messages as `alertname`, labels, or dedup keys; they can be sensitive data and high cardinality.
5. Redaction at the collector/alert template is defense in depth; if raw logs have already been sent, dashboard masking does not protect upstream sinks.
6. Restrict detail by notification channel; SMS/push usually only need a summary and a link to an authenticated system.
7. Treat logs containing user identifiers, IPs, session references, or resource IDs as data subject to privacy review and retention limits.
8. When credentials are found to have leaked into logs/alerts, trigger incident response, revoke/rotate per policy, and audit all downstream copies.

**Alert queries can also leak data** if they use a free-form label from user input. Normalize and constrain fields before emitting events.

## 17. Testing Alerts: Not Just Testing Java Code

A production alert must be verified end-to-end:

| Test | What to Verify |
| --- | --- |
| Errors rise above threshold | Rule enters pending/firing properly with sufficient persistence |
| Brief error spike then recovery | Does not generate a false page outside policy |
| Low traffic | Minimum sample/volume policy is clear; no division by zero |
| Zero traffic | Distinguishes idle service from missing telemetry |
| Logging pipeline drop/duplicate | Log-based alert does not miscount events |
| Metric counter reset | Rate query behaves sensibly |
| Late/out-of-order ingestion | Window and timestamp semantics are verified |
| Multiple pods failing together | Alert grouping prevents a page storm |
| Multiple exception logs per request | Not counted as multiple failed requests |
| Successful retry | Attempt metric rises, but user-facing error SLI is not inflated |
| Continuously violating alert | Dedup/cooldown does not send infinite notifications |
| Alert recovering near threshold | No excessive flapping |
| Primary on-call does not ACK | Escalation works according to policy |
| Silence during maintenance | Silence expires on time and does not hide out-of-scope incidents |
| Notification endpoint down | Meta-monitoring alert and appropriate retries exist |
| Service deployed/scaled | Routing labels and SLI do not lose coverage |
| Fake secret in error message | Does not appear in alert annotations, email, push, or tickets |
| Runbook/links | Dashboards and queries show data with the right scope/time window |

### 17.1. Testing Alerts with Synthetic Signals

One strategy is to emit metrics/logs **from a test environment**, using controlled tags and synthetic event codes without causing a real outage:
1. Verify the baseline when the system is healthy.
2. Create an interval with errors exceeding the threshold in staging (or a rule test engine).
3. Observe PENDING then FIRING, with notifications routed to a **test route**, without waking production on-call.
4. Let the signal recover and verify RESOLVED.
5. Test missing data, collector failure, metric resets, and duplicate ingestion.
6. Verify the runbook, owner, route, and links to logs/traces.
7. Record false positives/negatives in alert reviews and adjust rules with clear rationale.

**Do not break production databases/files just to test an alert.** With Prometheus-style rules, you can unit test rules with synthetic data if the system provides appropriate tooling; you do not have to run a real outage.

### 17.2. Evaluating Alert Quality Over Time

Track:
- Ratio of truly actionable alerts vs. noise.
- MTTD (mean time to detect), MTTA (mean time to acknowledge), and MTTR (mean time to resolve) with clear definitions.
- False page rate, notification volume per on-call shift, and escalation effectiveness.
- Rate of missed incidents or incidents detected only by customers.
- Alert coverage for critical user journeys/SLOs.
- Number of rules lacking an owner/runbook or no longer receiving data.

Do not turn "reduce alert count" into **disabling all alerts**; quality must balance detection capability against interruption cost.

## 18. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Every `logger.error` sends a page | Alert storm; one request can emit multiple errors | Evaluate SLI/impact; use rules and windows |
| Counting raw log lines as failed requests | Log duplicates/sampling/drops distort numbers | Use request-outcome metrics or proper event identity |
| Querying by message substring | Wording changes; exceptions contain free-form data | Use event codes, structured fields, schema versions |
| Setting only a count threshold | Traffic fluctuates; missing denominator | Use rate/ratio + volume and an appropriate policy |
| Setting only a ratio threshold | 1 error / 1 request = 100% on a tiny sample | Minimum volume, multi-window, or dedicated rule |
| No `for` duration or persistence | Alert flapping on noisy metrics | Duration/window/hysteresis aligned with SLO |
| Closing alerts immediately when telemetry drops | Can mask a real outage | No-data/missing-telemetry policy |
| Grouping by requestId/userId | Thousands of alert instances, high cardinality | Stable labels by service/environment |
| One dependency error pages all callers | Multiple notifications for one root cause | Symptom-first, grouping/inhibition |
| Treating INFO/WARN as unimportant | Impact can be high despite low log level | Severity based on user impact and policy |
| Assuming `ERROR` means operation failed | Successful retries still log failed attempts | Separate attempt-level from final outcome |
| Sending stack traces/secrets to SMS/chat | Data leak via alert sink | Safe metadata and authenticated access links |
| Monitoring only application logs | Collector down leaves zero logs | Meta-monitoring, synthetic/heartbeat checks |
| No owner/runbook | Nobody knows how to respond | Assign team, routing, and triage steps |
| Indefinite silences | Masks new incidents | Scoped, expiring, approved silences |
| Using demo rules as production SLOs | Thresholds do not reflect the real system | Calibrate with baselines/SLOs and incident history |
| Treating an ALERT OPEN log as a sent page | No notification delivery guarantee | Monitor alert manager and incident acknowledgment |

## 19. Exercises and Answers

**Exercise 1.** A Java service logs 100 `ERROR` lines for 10 failed requests because each request retries 10 times. If a log-based alert counts `ERROR > 50`, what is wrong?

**Answer:** The rule measures **attempts/log statements**, not final failed requests. Use a post-retry outcome counter or define a separate alert for retry pressure; do not infer 100 failed user requests.

**Exercise 2.** 1 error / 2 requests in 5 minutes yields a 50% error ratio. Should it page immediately?

**Answer:** Not enough information to decide. You must consider minimum traffic, severity, SLO, user impact, and history; for low-traffic but business-critical flows, a dedicated absolute-failure alert may be more appropriate.

**Exercise 3.** An alert remains FIRING, but nobody receives the Slack notification. Is it a Java logging bug?

**Answer:** Not necessarily. Check routing, grouping, silences, the notification provider, credentials/quotas, and the Alertmanager/incident system. `FIRING` and `notification delivered` are two separate states.

**Exercise 4.** Application logs are completely empty while users report the service is unreachable. Can you conclude the error rate is 0?

**Answer:** No. The service or logging pipeline may have stopped, the collector may have failed, or requests may not be reaching the service. Use uptime/synthetic checks and meta-monitoring.

**Exercise 5.** A log collector sends a batch twice after a timeout; the alert query counts each document as an error. What happens?

**Answer:** It can cause false positives or artificially inflate severity. You need to understand ingestion semantics, use event identity/dedup where appropriate, or use outcome metrics from a more reliable source.

**Exercise 6.** An alert has labels `service=checkout, request_id=req-123`. When 10,000 requests fail, what goes wrong?

**Answer:** `request_id` creates high cardinality and thousands of alert instances; it is unsuitable as a routing/dedup label. Keep IDs in logs/traces; alert by service/env/operation with an owner.

**Exercise 7.** In the Java demo, minute 2 has 30 errors / 120 requests—why is no additional `ALERT OPEN` emitted?

**Answer:** The rule has been active since minute 1; the demo only prints OPEN on an inactive → active transition. In real systems, the alert manager handles deduplication and separate notification repeat intervals.

**Exercise 8.** A team wants an alert for "disk usage 80%." What should you ask before assigning page severity?

**Answer:** Growth rate, time remaining until critical capacity, what function the disk serves, whether auto-cleanup exists, user/audit impact when full, required response time, and owner/runbook. An 80% threshold alone does not determine urgency.

## 20. Log and Alert Design Checklist

1. **Separate logs and alerts:** a logger call does not mean a notification or incident.
2. Choose the right signal: metrics/SLIs for overall impact, structured logs for specific events and tracing details, traces for request flows.
3. Rules have scope, window, threshold, persistence, minimum volume, recovery, and no-data policies.
4. SLIs accurately define eligible requests/bad requests, without double-counting retries or inferring from raw ERROR line counts.
5. Severity is based on user impact and actionability, not just log level.
6. Labels have low cardinality; request ID/event ID stay in logs/traces, never as group keys.
7. Grouping, deduplication, inhibition, routing, escalation, and time-bounded silences are configured.
8. Alerts have an owner, dashboard, runbook, log/trace links, and clear information without secrets.
9. Meta-monitoring covers agents/collectors/metrics/alert manager; missing data is not treated as HEALTHY.
10. Rules are tested with low/high traffic, retries, duplicate logs, missing metrics, recovery, notification failures, and multiple instances.
11. Alert quality metrics (MTTD, false pages, missed incidents, noise) and review cadences are in place.
12. Critical alerts are designed around SLOs/error budgets, not mechanically copied from illustrative thresholds.
13. Audit/security events have dedicated retention and alert policies; mandatory events are never blindly sampled out.
14. When an incident occurs, investigate with a clear **correlation workflow**: alert → dashboard → log → trace → dependency → remediation.

**Conclusion:** In Observability, **logs record events; alerts turn meaningful signals into calls to action**. A well-built Java system neither pages on every `ERROR` nor assumes that zero logs means zero incidents. Build a stable event schema, use SLIs/metrics and logs for their proper purposes, define rules based on impact and duration, handle alert lifecycle/no-data/dedup, and test the entire notification pipeline. That way, operations teams can both detect actionable incidents and rely on trustworthy logs and traces to find root causes without noise or data leaks.

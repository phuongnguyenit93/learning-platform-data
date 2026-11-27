# Building SLIs, SLOs, and Error Budgets for User Journeys

In serverless, a single request may traverse an API Gateway, a Java function, a database, a queue, and one or more workers before the user receives the final outcome. A function may return HTTP 202 very quickly while downstream work fails, or every invocation may succeed while users still cannot complete a purchase journey. Therefore, monitoring invocation counts, function error rates, or CPU alone is not enough to tell whether the service is meeting user expectations.

Quality must be measured at the **user journey** level using SLIs (Service Level Indicators), targets set via SLOs (Service Level Objectives), and error budgets used to decide how much risk is acceptable when shipping changes. For Java serverless, these metrics must connect synchronous requests with asynchronous outcomes, properly account for retries and duplicates, and reflect both latency and business correctness.

This lesson covers how to select journeys, define good and eligible events, build SLIs/SLOs for HTTP and message/event flows, calculate error budgets, alert on burn rate, and integrate results into operations and release workflows.

## 1. Distinguishing SLI, SLO, and SLA

These three concepts are related but distinct:

- **SLI (Service Level Indicator):** a quantitative measurement of the service quality experienced by users, e.g., percentage of checkouts completed within 10 seconds.
- **SLO (Service Level Objective):** an internal target for an SLI over a time window, e.g., at least 99.9% of valid checkouts completed within 10 seconds over 30 days.
- **SLA (Service Level Agreement):** a service commitment to customers or partners, typically carrying contractual terms and commercial consequences if missed.

SLOs should generally be stricter than SLAs so operations teams have buffer time to respond before breaching external commitments. Not every SLO needs to become an SLA.

Example:

| Component | Example |
|---|---|
| Journey | User creates an order |
| SLI | Percentage of valid order creation requests confirmed successfully within 5 seconds |
| SLO | 99.9% over a 30-day window |
| SLA | Public contractual commitment to customers, if any |

SLIs must reflect outcomes users care about. Technical metrics such as CPU utilization, container count, cold start count, or queue depth help explain root causes, but on their own they do not prove a journey succeeded.

## 2. Starting from the User Journey

Pick a journey meaningful to users with a clear start and end. Do not start from the list of metrics the system already happens to emit.

Example journeys in a serverless application:

| Journey | Starting Point | Expected User Outcome |
|---|---|---|
| Sign in | Submit credentials | Receive a valid session/token and enter the application |
| Create order | Submit checkout request | Order is created with a confirmed status |
| Payment | Initiate payment | Payment is clearly confirmed or failed |
| Download report | Request export | Receive a valid file before the deadline |
| Data sync | Submit import request | Data is processed with a final outcome |
| Send notification | Notification-triggering event occurs | Notification is accepted or delivered by provider per contract |

A journey may span multiple services and multiple triggers. For example, checkout might cross an HTTP function, a database transaction, a queue, a payment worker, and a webhook callback. Measure at the point where the user initiates the action and the point where the final outcome is confirmed.

### Mapping the Flow Before Choosing SLIs

~~~mermaid
flowchart LR
    User[User]
    API[HTTP API / Java function]
    DB[(Order database)]
    Queue[Queue / event bus]
    Worker[Java payment worker]
    Provider[Payment provider]
    Callback[Webhook / result handler]
    UserResult[Final state]

    User --> API
    API --> DB
    API --> Queue
    API -->|Accepted response| User
    Queue --> Worker
    Worker --> Provider
    Provider --> Callback
    Callback --> DB
    DB --> UserResult
~~~

In this flow, HTTP 202 only means the system accepted the work per contract. It does not prove payment succeeded. If the user journey is “payment confirmed,” the SLI must track the final outcome rather than stopping at the 202 response.

## 3. Defining SLIs via Numerator and Denominator

A ratio-based SLI typically follows this structure:

```text
SLI = good events / total eligible events
```

Both parts must be defined precisely:

- **Eligible events:** which operations are included in the denominator?
- **Good events:** what conditions prove an operation met requirements?

Example availability SLI for checkout:

```text
Good event:
  Valid request accepted and order created per contract.

Eligible event:
  All valid checkout requests sent to the endpoint during the measurement window.

Availability SLI:
  Good checkout requests / Eligible checkout requests
```

For a latency SLI, a good event must satisfy both the success condition and the time threshold:

```text
Good latency event:
  Successful checkout completed in <= 5 seconds.

Latency SLI:
  Successful checkout requests completed within 5s
  / Eligible checkout requests
```

This definition prevents a system from achieving good latency by failing fast. A failed request does not count as good simply because it finished in a few milliseconds.

### Do Not Manipulate the Denominator to Make SLIs Look Better

If too many requests are excluded from the denominator, an SLI can look healthy while users still experience errors. Document exclusions explicitly:

- Malformed requests or requests missing required fields may be excluded from backend availability SLIs if they are caller errors, but must be tracked separately to catch broken client integrations.
- Requests denied for missing permissions may not be availability failures, yet if a service misconfiguration causes IAM errors that reject valid users, that is a service failure.
- Requests actively canceled by users can be handled separately, but timeouts caused by a slow backend must never be labeled as user cancellations.
- Test/synthetic traffic should be excluded from production SLIs only when clearly identified and never used to mask real errors.

Do not exclude dependency errors, timeouts, throttling, or platform-induced cold starts from SLIs simply because they happen outside Java code.

## 4. Choosing SLI Types Fitting the Journey

A single journey may need multiple SLIs to capture different dimensions.

| SLI Type | Question Answered | Example |
|---|---|---|
| Availability | Can the user complete the action? | Percentage of orders created successfully |
| Latency | Does it complete fast enough? | Percentage of API responses within 500 ms |
| Correctness | Is the result accurate? | Percentage of orders with valid totals and state |
| Freshness | Is data updated promptly? | Percentage of events reflected within 60 seconds |
| Completion | Does async work finish? | Percentage of exports completed within 5 minutes |
| Durability | Are accepted requests ever lost? | Percentage of jobs durably stored with a terminal state |
| Coverage | Does the system cover all required scope? | Percentage of tenants/regions able to complete the journey |

There is no need to create an SLO for every metric. Pick indicators tied directly to user experience or product commitments. Some metrics belong in diagnostics rather than service targets.

## 5. SLOs for HTTP APIs

For synchronous APIs, requests usually have a clear start and response. An availability SLI can count valid requests returning an expected success result per contract divided by total valid requests.

Example:

```text
Availability SLI =
  eligible requests with expected success outcome
  / eligible requests
```

Do not define every HTTP 2xx as success if the response only acknowledges work intake. For an export endpoint returning 202, synchronous request success means the job was durably persisted and a valid job ID was returned. Journey completion success means the export file finished before the deadline; that is a separate SLI for the asynchronous part.

### Latency SLI

You can measure the proportion of requests completing within a threshold:

```text
Latency SLI =
  eligible requests completed within threshold
  / eligible requests
```

Example SLO: 99% of order status lookup requests complete within 400 ms over 30 days.

Percentiles like p95/p99 are useful for inspecting latency distributions, while threshold-ratio SLIs usually map more cleanly to error budgets. p99 can be tracked as a diagnostic metric; do not confuse “p99 under 400 ms” with “99% of requests under 400 ms” when aggregation methods or windows differ.

### Correctness SLI

An API can return 200 while returning wrong data. For critical journeys, measure correctness using business checks:

- Totals calculated accurately.
- Valid state transitions.
- Responses scoped to the right tenant and resource.
- Idempotency keys do not create duplicate orders.
- Data is durably persisted before confirmation.

Correctness often requires business invariants, reconciliation, or sampled validation. Do not rely on status codes alone.

## 6. SLOs for Message and Event-Driven Functions

With queues or streams, a record may be delivered multiple times. Invocation success does not mean the message completed exactly once. A consumer might return success while persisting only partial side effects, or a message might retry after a database commit.

For asynchronous journeys, define SLIs by **business operation/event**, not by invocation count.

Example:

```text
Eligible event:
  A valid export request durably recorded with an operationId.

Good event:
  Export file completed, verified, and ready for download
  within 5 minutes of acceptance.

Completion SLI:
  Good export operations / Eligible export operations
```

If a message is delivered three times yet produces one successful export, the denominator is still one business operation, not three invocations. Retries are execution details, not three different users.

### Defining Deadlines

Async journeys must have a deadline or completion window:

- 95% of notifications sent within 30 seconds.
- 99% of exports completed within 5 minutes.
- 99.9% of payment events processed and reflected in status within 2 minutes.

An operation still incomplete when the deadline passes is counted as bad or overdue per defined rules. Never drop an operation from the denominator merely because it is still in processing state.

### Queue Age Is Not a Completion SLI

Queue age or iterator age metrics show how far behind consumers are, which is very useful for diagnostics. However, they do not show whether individual operations completed per contract. A queue with low age can still contain poison messages retrying; high queue age might impact a specific tenant group masked by aggregate metrics.

Combine:

- Business completion rate.
- Time-to-completion.
- Queue age/iterator age.
- Retry count and DLQ count.
- Overdue operation rate.
- Successfully reconciled operation rate.

## 7. Tracking a Journey Across Multiple Invocations

An operation may pass through an HTTP handler, queue producer, worker, webhook handler, and database. A stable business identifier is needed to link steps.

Event envelope example:

~~~json
{
  "operationId": "export-2026-00418",
  "eventId": "evt-91a2",
  "tenantId": "tenant-42",
  "eventType": "report.export.requested",
  "occurredAt": "2026-11-17T09:00:00Z",
  "schemaVersion": 1
}
~~~

- `operationId` identifies the business journey.
- `eventId` identifies a specific event for deduplication.
- `tenantId` supports tenant scope analysis, but must be verified per trust contract.
- `traceparent` or trace context can be passed in message attributes to link distributed traces.

Do not use `operationId` or `tenantId` as high-cardinality metric labels. They belong in controlled logs, traces, or event stores. Metrics should use bounded dimensions such as journey, outcome, region, or service version.

### Start and Completion Timestamps

Record the creation timestamp at the source and the final completion timestamp. Use well-synchronized system clocks; for timing inside a single process, use a monotonic clock. When comparing timestamps across services, account for clock skew and prefer trace durations or normalized timestamps.

If an operation can retry hours later, persist the start timestamp in a database/event store. Do not rely on static variables or instance creation times.

## 8. Avoiding Miscounts from Retries, Duplicates, and Cancellations

This is critical in at-least-once serverless architectures.

### Retries

If a worker times out on the first attempt after committing downstream, the retry may find the operation already completed. Business outcomes should be counted only once. Use operation state and idempotency markers to determine the final result.

### Duplicate Deliveries

The same event may be redelivered. Do not increment eligible business operations every time the handler receives a message. Deduplicate by `eventId` or `operationId` per contract.

### Partial Batch Failures

With stream consumers using partial batch responses, some records succeed while others are retried. Count outcomes per record/business operation, rather than treating the entire invocation as a single good or bad event.

### Cancellations

Distinguish legitimate user cancellations from cancellations caused by function timeouts or shutdowns. If the backend proactively cancels due to overload, that may be a service failure that must count in the SLI per contract. Never mark every `CANCELLED` status as excluded.

### Operations Without a Terminal Outcome

If an event lands in a DLQ or exhausts retries, the operation must still have an observable terminal state. Otherwise it can vanish from reports and skew SLIs. Use reconciliation to catch accepted operations lacking a completion record after the deadline.

## 9. Choosing SLO Windows and Targets

SLOs are typically evaluated over a rolling window, such as 7 days or 30 days. Longer windows smooth out short fluctuations for steady reliability tracking; shorter windows react faster to regressions.

An SLO specification should define:

- Exact SLI and formula.
- Target percentage.
- Time window.
- Data sources and deduplication rules.
- Exclusion criteria.
- Handling of incomplete events.
- Service, tenant, or region scope.
- Accountable owner.

Examples:

| Journey | SLI | Illustrative SLO | Window |
|---|---|---:|---|
| Sign in | Percentage of valid logins completed within 1 second | 99.9% | 30 days |
| Order lookup | Percentage of successful requests within 500 ms | 99.5% | 30 days |
| Report export | Percentage of exports completed within 5 minutes | 99% | 30 days |
| Payment event processing | Percentage of events reflected in state within 2 minutes | 99.9% | 30 days |

These are illustrative targets, not defaults for every product. Targets must be grounded in user needs, baselines, technical feasibility, and cost.

### Do Not Arbitrarily Set a 100% SLO

A 100% target is usually unrealistic in distributed systems with external dependencies and network failures. Overly aggressive SLOs drive up cost and slow down delivery without delivering proportional user value.

Ask: do users actually notice the difference between 99.9% and 99.95%? What is the cost and complexity of achieving the tighter target? Some journeys like payments may warrant higher reliability than search pages, but decisions must reflect real user impact.

## 10. What Is an Error Budget?

An error budget is the amount of failure permitted under the SLO within the measurement window.

If the availability SLO is 99.9%, the error budget is:

```text
Error budget = 100% - 99.9% = 0.1%
```

With 100,000 eligible operations in the window, the corresponding error budget is:

```text
100,000 × 0.1% = 100 bad operations
```

If 60 bad operations have occurred, 40 operations remain in the budget. If bad operations exceed 100, the SLO is breached for that window.

General formula for a request-based SLO:

\[
B = N \times (1 - S)
\]

Where:

- (B): allowed bad events.
- (N): eligible events.
- (S): SLO as a ratio, e.g., 0.999.

For time-based SLOs, calculations may be based on total minutes or intervals where the service failed criteria. Do not mix request-based error budgets with downtime minutes when SLIs and denominators differ.

### Example Budgets by Target

| SLO | Error Budget | Bad Events per 100,000 Operations |
|---:|---:|---:|
| 99% | 1% | 1,000 |
| 99.5% | 0.5% | 500 |
| 99.9% | 0.1% | 100 |
| 99.95% | 0.05% | 50 |
| 99.99% | 0.01% | 10 |

An error budget is not a quota to intentionally burn through. It is a tool for balancing reliability and velocity of change.

## 11. Burn Rate and Error Budget Consumption Speed

Burn rate measures the current error rate relative to the rate allowed by the SLO.

```text
Burn rate = observed error ratio / allowed error ratio
```

With a 99.9% SLO, the allowed error ratio is 0.1%. If an observation window sees a 1% error ratio, the burn rate is 10x.

A burn rate of 1 means the budget is being consumed at the exact pace matching the SLO window. A burn rate of 10 means the budget is burning 10 times faster. If sustained, the system will exhaust its error budget early.

### Example

30-day 99.9% SLO:

- Allowed error ratio: 0.1%.
- Observed error ratio over one hour: 1.44%.
- Burn rate: 1.44% / 0.1% = 14.4.

One hour at a burn rate of 14.4 consumes roughly 2% of a 30-day budget if that rate stays steady. That is a noteworthy signal even though a single hour does not yet prove the monthly SLO has been breached.

### Multi-Window Burn-Rate Alerts

Combining short and long windows avoids paging on brief spikes while catching ongoing incidents quickly.

Illustrative policy for a 30-day SLO:

| Alert | Short Window | Long Window | Meaning |
|---|---|---|---|
| Critical | 5 minutes at very high burn rate | 1 hour still at high burn rate | Likely burning a significant share of budget rapidly |
| Warning | 30 minutes at moderate-high burn rate | 6 hours sustaining notable burn rate | Needs investigation before budget exhaustion |
| Budget low | Remaining error budget below internal threshold | Over rolling window | Release risk posture needs adjustment |

Exact thresholds must reflect the SLO window, traffic volume, impact, and team response capacity. Avoid copying burn-rate numbers blindly without calculating what percentage of budget they consume in the corresponding period.

## 12. Bringing Error Budgets into Release Decisions

Error budgets give product and engineering teams shared rules for deciding whether to keep shipping features or prioritize reliability.

Example policy:

| Budget State | Action |
|---|---|
| Healthy budget, normal burn rate | Continue releasing per standard process |
| Fast-shrinking budget | Increase checks, narrow canary scope, require post-deploy monitoring |
| Budget nearly exhausted | Defer high-risk changes; prioritize reliability work |
| Budget exhausted or sustained SLO breach | Pause non-urgent feature releases; focus on fixing root causes |
| Security/data-loss incident | Follow incident policy immediately without waiting for budget |

Policies must state who can grant exceptions, how risks are documented, and criteria for resuming releases. Error budgets must never become a mechanism for blaming individuals or hiding incidents.

Not all changes carry equal risk. An urgent security patch may need immediate deployment even when budget is low, accompanied by a mitigation plan and tighter monitoring.

## 13. Instrumentation in Java Serverless

Metrics must be recorded where the business outcome is known. Function runtime metrics usually report only whether an invocation succeeded or failed; they do not know whether an order was paid or an export finished before its deadline.

You can use Micrometer or OpenTelemetry to instrument journeys. Simple Micrometer example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class CheckoutSliRecorder {

    private final MeterRegistry registry;

    public CheckoutSliRecorder(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String outcome,
            long elapsedNanos,
            boolean withinLatencyTarget) {

        registry.counter(
                "user_journey_operations_total",
                "journey", "checkout",
                "outcome", outcome
        ).increment();

        registry.counter(
                "user_journey_good_events_total",
                "journey", "checkout",
                "good", Boolean.toString(
                        "success".equals(outcome)
                                && withinLatencyTarget)
        ).increment();

        Timer.builder("user_journey_duration")
                .tag("journey", "checkout")
                .tag("outcome", outcome)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Here, `outcome` should take only a bounded set of values such as `success`, `validation_error`, `dependency_error`, or `timeout`. In production, clearly define which error categories belong in the eligible denominator and which count as bad events. The example illustrates metric recording; it does not automatically make every outcome a valid SLI without agreed semantics.

Call `record()` exactly once per eligible business operation at an authoritative recording point. Requests excluded from the denominator by the SLI definition need a separate metric rather than calling this recorder. Then total `user_journey_operations_total` forms the denominator and `user_journey_good_events_total{good="true"}` forms the numerator.

### Measuring an Operation Inside a Handler

```java
long started = System.nanoTime();

try {
    CheckoutResult result = checkoutService.createOrder(command);

    long elapsedNanos = System.nanoTime() - started;
    boolean withinTarget = elapsedNanos <= targetNanos;

    sliRecorder.record(
            result.isSuccessful() ? "success" : "business_failure",
            elapsedNanos,
            withinTarget);

    return toResponse(result);
} catch (DependencyTimeoutException ex) {
    long elapsedNanos = System.nanoTime() - started;
    sliRecorder.record(
            "timeout",
            elapsedNanos,
            false);
    throw ex;
}
```

This illustrative snippet must sit at the boundary where operation validity and final outcome are known. If validation fails due to the caller, record a separate metric or exclude per SLI definition. If a dependency times out, that is normally a bad journey event.

Do not record the same operation multiple times across controller, service, and repository into the same counter. Pick one authoritative recording point to prevent double counting.

### Metric Labels Must Be Low-Cardinality

Do not use these values as metric labels:

- user ID.
- tenant ID when tenant count is large.
- order ID or operation ID.
- email, full URL, or request ID.
- message payload or exception message.

Those values belong in controlled logs or traces. Metric labels should be journey, outcome, region, service/revision, or bounded plan tiers.

## 14. Instrumentation for Async Journeys

For async workflows, operation state must be stored durably. A table or event store might contain:

~~~sql
CREATE TABLE user_operations (
    operation_id VARCHAR(128) PRIMARY KEY,
    journey      VARCHAR(64) NOT NULL,
    accepted_at  TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    status       VARCHAR(32) NOT NULL,
    result_code  VARCHAR(64) NULL
);
~~~

When the API accepts work, create an operation record and publish a message using the outbox pattern if consistency between database commit and event publish is required.

Workers update the terminal status when work succeeds or fails. An evaluator or stream processor can compute the completion SLI:

- Count operations accepted within the cohort/window.
- Identify operations completed cleanly before the deadline.
- Count failed, overdue, or DLQ operations as bad per policy.
- Do not recount operations on message retries.
- Reconcile operations lacking a terminal status after the deadline.

Do not use queue dwell time alone as end-to-end duration. A journey may begin before the message is published and end after several downstream steps.

### Eventual Consistency of SLIs

Completion SLIs have inherent lag because they must wait for operations to finish or deadlines to pass. Near-real-time dashboards can display two groups:

- **Provisional:** operations still within their deadline, not yet conclusive.
- **Finalized:** operations that succeeded or passed their deadline/terminal failure.

If an SLI is calculated only over finished operations, stuck jobs can fall out of the denominator and make ratios look artificially good. Keep them in the cohort and mark them bad once the deadline expires.

## 15. Distributed Tracing Connecting the Journey

Traces help pinpoint the cause of a slow or failing operation across multiple functions and dependencies.

For HTTP requests, use OpenTelemetry context propagation via standard headers like `traceparent`. When publishing messages, inject trace context into message attributes; consumers extract context to create linked spans. For long workflows or fan-out, use span links instead of stretching a single parent-child trace too long.

A trace may include:

- API Gateway/HTTP ingress.
- Java function handler.
- Database transaction.
- Queue publish.
- Queue receive/consumer invocation.
- External API call.
- Webhook callback.
- Final state update.

Traces aid latency and dependency diagnosis, but do not replace SLIs. Sampling may drop traces; SLIs require complete metric/event accounting or a reconcilable data source.

Do not use sampled trace counts as an SLO denominator.

## 16. SLO Dashboards

A useful dashboard should answer three questions: are users experiencing issues, how much error budget remains, and which component is causing the problem?

Suggested panels:

1. Current SLI and SLO target.
2. Good events, bad events, and eligible events.
3. Remaining error budget by count and percentage.
4. Burn rate over short/long windows.
5. Latency distribution p50/p95/p99 and percentage under threshold.
6. Completion time of async operations.
7. Queue age/iterator age, retries, and DLQ.
8. Error breakdown by service, region, and release.
9. Business outcomes such as checkout success or export completion.
10. SLIs by journey/critical tenant cohort with controlled cardinality.

Aggregate metrics can hide failures affecting a single region or customer segment. Break down by meaningful segments while avoiding unbounded metric dimensions. Use logs/traces to drill down to a specific tenant or operation.

## 17. Alerting on SLOs Instead of CPU Alone

CPU, memory, and invocation counts are infrastructure signals. On-call alerts should prioritize user-facing symptoms and error budget impact.

Examples:

- Alert when checkout availability SLI drops.
- Alert when export completion SLI burns budget rapidly.
- Alert when overdue operations rise.
- Alert when queue age climbs alongside degrading completion latency.
- Alert when DLQ spikes or operations lose terminal status.
- Alert when a release lowers business success rate.

You can keep CPU/memory alerts as diagnostic or capacity warnings. However, 90% CPU is not necessarily an incident if SLIs remain healthy; conversely, low CPU does not prove service health if functions are hitting IAM denials or dependency errors.

### Alerts Need Clear Actionability

A good alert should include:

- Affected journey and SLI.
- Region/revision scope if identifiable.
- Current error budget/burn rate.
- Links to relevant dashboards and traces/logs.
- Guidance for checking dependencies, queues, releases, and config.
- Owner and priority level.

Avoid alerts that simply say “Lambda errors increased” without showing how users are impacted.

## 18. Segmentation and Fairness

A global SLO can mask failures affecting only a large tenant, a distant region, or a specific client type. Analyze meaningful cohorts:

- Region or zone.
- API version or release revision.
- Journey type.
- Bounded tenant tier/plan groups.
- Client platform or version.
- Operation type or payment provider.

If a key tenant is failing while millions of others succeed, the overall SLI may hide their experience. You can define dedicated SLOs for critical tiers or journeys when justified by product needs.

Do not create per-tenant SLOs by default when tenant counts are high and individual traffic is low; low volume yields noisy ratios. Use anomaly alerts, support signals, or aggregate cohorts for smaller tenants.

## 19. Common SLI/SLO Design Mistakes

- **Treating invocation success as user success:** functions return 200/202 while downstream workflows fail; measure final outcomes.
- **Counting invocations instead of business operations:** retries and duplicates distort the denominator; deduplicate by operation/event ID.
- **Omitting pending operations:** stuck jobs disappear from SLIs; keep them in the cohort and mark bad after the deadline.
- **Measuring only average latency:** tail latency can be terrible; measure threshold ratios and percentile distributions.
- **Treating every 2xx as success:** 202 only confirms intake; define outcomes per contract.
- **Excluding all 4xx errors:** some 4xx errors caused by service IAM/config or auth flows affect legitimate users; classify carefully.
- **Setting a 100% SLO:** unrealistic targets drive unnecessary cost; choose targets based on experience and risk.
- **Setting SLOs without owners:** nobody takes responsibility when budget runs out; assign owners and policies.
- **Monitoring only CPU/queue depth:** those are diagnostic metrics; business SLIs are required.
- **Using sampled traces as the denominator:** traces can be sampled out; use complete metric/event accounting.
- **Using tenantId/orderId as metric labels:** cardinality explodes; use logs/traces for drill-down.
- **Not bridging async trace context:** hard to diagnose end-to-end; propagate context through messages.
- **Ignoring clock skew:** cross-service durations can be wrong; use monotonic durations and synchronized timestamps.
- **Not defining cancellations:** backend failures may be wrongly excluded; distinguish user cancellations from system timeouts.
- **Not reconciling missing-status operations:** jobs can vanish from reports; implement reconciliation.

## 20. Process for Building SLOs in Java Serverless

You can roll out in this sequence:

1. Select a critical user journey with a clear start and end.
2. Map HTTP, database, queue, worker, and external dependencies in the journey.
3. Define the business operation ID and how retries/duplicates are deduplicated.
4. Define eligible events, good events, bad events, and exclusion rules.
5. Choose appropriate SLIs: availability, latency, correctness, freshness, or completion.
6. For async flows, define deadlines and handling for pending/DLQ operations.
7. Choose SLO targets and rolling windows based on user needs, baselines, and costs.
8. Calculate error budgets from the SLI denominator.
9. Instrument metrics where business outcomes are known; use traces for diagnostics.
10. Build SLI, budget, and burn-rate dashboards.
11. Set up multi-window alerts and response actions.
12. Embed error budgets into release policies and incident reviews.
13. Test duplicates, retries, timeouts, dropped events, overdue operations, and clock skew.
14. Review SLI definitions whenever products or contracts evolve.

Starting with a few critical journeys is far more sustainable than creating dozens of unowned SLOs.

## 21. Complete Example: SLO for an Order Creation Journey

Suppose a system has a Java HTTP function accepting checkouts, saving orders, and publishing messages for a worker to process payments.

Definitions:

- **Journey:** checkout.
- **Start:** valid request received at the API.
- **Eligible:** request passes basic business validation with a valid tenant/customer.
- **Good:** order is created exactly once, final status is PAID or another contract-accepted outcome, and the result is reflected to the user within 2 minutes.
- **Bad:** payment failure due to system error, operation exceeds deadline, message enters DLQ, or state cannot be reconciled.
- **SLO:** 99.9% of eligible checkout operations achieve good over a rolling 30-day window.
- **Latency companion SLI:** 99% of requests are accepted and return an operation ID within 500 ms.
- **Diagnostic metrics:** API p95, queue age, worker retries, provider latency, DB errors, and DLQ.

If there are 50,000 eligible checkouts in 30 days, the error budget for a 99.9% SLO is:

```text
50,000 × 0.001 = 50 bad checkout operations
```

If 30 operations exceed the deadline, 12 payment operations fail due to dependencies, and 8 operations enter the DLQ, that totals 50 bad operations; the budget is exhausted. Do not recount the same operation when retried three times.

This is a policy example. In practice, decide whether payment declines from users/issuers count as bad service events or valid business outcomes. If the payment provider returns a decline per contract, it can be treated as a valid business outcome; if the provider times out or integration fails, that is typically a bad event. Definitions must faithfully reflect product commitments.

## 22. Key Takeaways

SLIs measure the quality users actually experience; SLOs set targets for SLIs over a time window; error budgets quantify allowable failures before targets are breached. For Java serverless, measure by business operation and end-to-end journey, not solely by function invocations.

HTTP 202 may represent only work intake. With queues and events, retries/duplicates do not create extra business operations, while operations pending past deadlines must count as bad. Use operation IDs to connect steps, low-cardinality metrics to compute SLIs, traces to isolate causes, and reconciliation to catch lost work.

Burn rate shows how fast the error budget is being consumed. Combine multi-window alerts, journey-based dashboards, and clear release policies so teams can balance shipping velocity with reliability. An SLO delivers value when it reflects user experience, has verifiable measurement definitions, and drives concrete operational action.

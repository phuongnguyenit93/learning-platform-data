# Organizing a Diagnostic Workflow from Alert to Metrics, Traces, Logs, and Related Evidence

## 1. What Must a Diagnostic Workflow Answer?

When the system reports "payments are slow", the on-call operator needs to determine how users are impacted, when the failure started, where it lies, and what action can reduce impact. A red chart or a single error line does not answer all those questions.

**Diagnostics is the process of narrowing hypotheses with evidence sharing the same scope and time window.** Every tool opened must serve a specific question. The workflow usually moves from alert to aggregated metrics, execution traces, logs, and then evidence about deployments, resources, or dependencies. You can step back when new data changes the hypothesis.

Terms to master:

| Component | Primary question | Limits to remember |
| --- | --- | --- |
| Alert | What condition requiring human attention occurred? | A crossed threshold does not by itself pinpoint root cause |
| Metric | What are the severity, trend, and blast radius? | Aggregated numbers do not fully reconstruct individual requests |
| Trace | Which operations did a request pass through, and where did it wait? | Shows only what was instrumented, collected, and retained |
| Span | How did one operation in a trace start, end, and relate to others? | A standalone span name or duration does not prove root cause |
| Log | At a specific timestamp, what events and errors did code record? | Can be missing, duplicated, late, or stripped of context |
| Supporting evidence | Do changes, limits, or events explain the symptom? | Coincidence in time still needs verification |
| Runbook | Who checks what, how, and when to escalate? | Must tie to the real system, with an accountable owner |

A trace consists of spans with parent–child or link relationships; it helps show an activity's path through instrumented components. See [OpenTelemetry trace model](https://opentelemetry.io/docs/concepts/signals/traces/).

A good workflow distinguishes three levels of conclusion:

- **Observation:** "The HTTP 5xx rate of checkout-api rose in the 5-minute window."
- **Hypothesis:** "Requests may be waiting on the payment service."
- **Substantiated conclusion:** "In the inspected error traces, waiting time concentrated in the payment call; logs sharing the trace recorded timeouts; the payment side showed rising queue depth during that exact period."

Do not turn "may be" into "proven" solely because of a screenshot.

## 2. Actuator's Role in the Observability Pipeline

In a Spring Boot application, Actuator provides inspection points of the application process itself. With suitable instrumentation, Micrometer produces metrics; tracers and trace receivers support finding request paths; centralized logging stores events. Dashboards and alerting tools build on the collected data.

Data flow differs from investigation flow:

```text
Data flow:
Application → metrics collector → time-series store → dashboards/alerts
            → trace exporter → trace store
            → log output → log collector → log store

Investigation flow:
Alert → verify impact → metrics → representative traces → correlated logs
      → deployment/resource/dependency evidence
      → mitigate impact → verify recovery → follow-up investigation
```

Actuator does not turn itself into a long-term metrics store, trace server, or log search system. The `metrics` endpoint inspects meters of one instance; the `prometheus` endpoint exports data for Prometheus scraping and requires `micrometer-registry-prometheus`. Enabling an endpoint, exposing it over HTTP, and granting access permissions are distinct conditions. See [Actuator Endpoints for Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`/actuator/health` returning `UP` only reports the outcome of configured health checks. It does not prove every business flow meets latency objectives, has zero errors, or that all users succeed. Health is one piece of evidence in the workflow, not the sole verdict.

## 3. Preparing So Tools Can Connect Together

Before incidents occur, agree on the correlation fields used when switching between sources:

| Information | How it is used in investigation |
| --- | --- |
| Service name, environment, deployment region | Avoid mixing production metrics with staging logs or confusing regions |
| Instance/pod and lifetime | Distinguish failing instances, replaced instances, and newly started processes |
| Application version, build ID, deploy time | Before–after comparisons and version grouping |
| Business route, method, outcome type | Isolate which operation is affecting users |
| Timestamp with time zone | Keep the same window when switching dashboards, trace stores, and log stores |
| Trace ID, span ID when present | Jump from one activity to spans and logs in the right context |
| Incident ID | Gather questions, actions, evidence, and accountable owners |

Use UTC or explicitly state time-zone offsets; distinguish event time from system ingestion time. Late-arriving logs do not mean the event just happened. Skewed host clocks can make cross-service ordering look nonsensical; when in doubt, note the skew rather than forcing timestamps to align.

Do not force every source to use identical label spellings. For example, `service.name` in a tracing system may correspond to `application` in metrics and `service` in logs. Runbooks must state the actual mapping clearly. Do not assume Prometheus automatically adds `env`, `version`, or application name if the pipeline has not configured them.

Keep metric label combinations (cardinality) under control. Service names, methods, and route templates like `/orders/{id}` can be used for grouping. Trace IDs, order IDs, emails, or URLs with dynamic IDs should not become regular metric labels. Per-request keys fit logs/traces governed by corresponding data policies.

## 4. First Step: Verify the Alert and Impact Level

Upon receiving an alert, immediately capture the query expression, condition, evaluation range, start time, and runbook link. "High latency" is not clear enough without route, unit, quantile, and calculation window.

Follow this sequence:

1. **Verify the exact target:** which service, environment, region, and business route?
2. **Verify signal freshness:** is the collector receiving data, are samples missing, targets lost, or ingestion lagging?
3. **Verify impact:** how did success rate, request count, and user-side or gateway latency change?
4. **Set time scope:** pick a pre-incident baseline range and a failing range; keep them consistent when switching tools.
5. **Assign roles:** one coordinator, application investigator, and dependency investigator when impact requires multiple people.
6. **Record first hypothesis with next check:** no need to declare root cause yet.

Example of an inspectable alert:

```text
Service: checkout-api
Environment: production, region: vn-a
Symptom: p95 POST /checkout > 1 second, sustained 10 minutes
p95 window: 5 minutes
Cross-check needed: traffic, error rate, data freshness
Investigation range: 09:45–10:15 UTC
```

These values are lesson assumptions, not universal production thresholds. Real thresholds must rely on service quality objectives (SLOs), traffic, and business impact.

The four-signal framework—latency, traffic, errors, and resource saturation—is often useful. This is a general way of asking questions; high CPU alone does not mandate paging an on-call responder. See [Google SRE's Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/).

If metrics vanish and a latency alert switches to "no data", do not conclude the system recovered. Distinguish application failures from observability-collection pipeline failures.

## 5. Using Metrics to Narrow the Scope

### 5.1. From Whole Service to Anomalous Group

First view request count, error rate, and latency over the same scope. Then split by route, region, instance, or version to find where differences lie.

Ordered questions:

- Are all routes slow or only one route?
- Are all instances failing or only one group?
- When did traffic rise, drop, or shift distribution?
- Did 5xx errors rise together with latency, or did latency rise while still returning 2xx?
- Are there saturation signs such as growing queues, connection shortages, thread waits, or prolonged GC?
- Do gateway-side and application-side metrics show the same trend?

Differences between gateway and application are informative: requests may be rejected before entering the app, time out at the proxy, or remain stuck and thus not appear yet in completed-request statistics. Or the two sides may count different scopes. Check definitions before blaming one component.

### 5.2. Three Queries Used to Ask Questions

Assume Prometheus has collected the application's HTTP counters and **classic histogram**. Examples use labels `job="checkout-api"`, `env="prod"`; this is the example dataset's contract, not guaranteed default labels. In real use, add required cluster/region scopes and check metric names and labels in exported data.

Completed request rate per second, by route template:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="checkout-api", env="prod"
  }[5m])
)
```

5xx ratio over total completed requests for the whole service:

```promql
sum(rate(http_server_requests_seconds_count{
  job="checkout-api", env="prod", status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="checkout-api", env="prod"
}[5m]))
```

A result of `0.04` means 4%, not 0.04%. In systems that do not create a 5xx series before an error occurs, the numerator may be empty; at zero traffic, division yields no meaningful ratio. Dashboards/rules must handle no-data and zero-traffic states explicitly and check collector health; do not color all empty results green by replacing everything with 0.

p95 by route, aggregated across instances:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="checkout-api", env="prod"
    }[5m])
  )
)
```

`rate` computes the per-second growth rate of counters and handles counter resets; it must be applied to each series before summing. With classic histograms, keep the `le` label when summing buckets. `histogram_quantile` gives an estimated value from buckets, here in seconds. Expressions follow [Prometheus query function rules](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Use the third query only when `_bucket` series exist. Do not average per-instance p95s and call that service-wide p95. For example, an instance serving 10 requests and an instance serving 10,000 requests do not carry equal weight. Histograms allow aggregating distributions before estimating quantiles; application-side pre-calculated percentiles do not aggregate that way. See [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

Quantiles over a window with few requests can fluctuate wildly. Always place request count alongside latency charts. Long windows smooth data yet can mask short error bursts; windows too short relative to scrape cadence can lack samples.

### 5.3. Checking Actuator on One Instance

The snippet below is a configuration fragment for an **existing Spring Boot 3.3 web application** already having `spring-boot-starter-actuator` and `micrometer-registry-prometheus`. It serves a local lab on the same machine, not a standalone application or production exposure configuration.

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

After the application has received web requests, use Bash with `curl` from the same machine:

```bash
curl -fsS 'http://127.0.0.1:9091/actuator/health'
curl -fsS 'http://127.0.0.1:9091/actuator/metrics/http.server.requests'
curl -fsS 'http://127.0.0.1:9091/actuator/prometheus'
```

If the application has security enabled, use the lab's permitted authentication mechanism; the commands do not bypass authentication themselves. When running inside a container, loopback belongs to the container's network namespace, not automatically the host running the terminal.

The metrics endpoint uses the name `http.server.requests`; names exported to Prometheus may be normalized into underscores with units and suffixes. Histogram config enables aggregated quantile calculation; verify actual exported data rather than guessing from property names. See [Metrics for Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

These are reads of live data, so there is no fixed stdout: measurements depend on load, libraries, and query timing. Expected outcomes are a JSON health response, JSON meter description, and text metrics data; 401/403 indicates permissions need checking, while 404 requires checking endpoint, path, port, and dependencies.

Do not use one `/actuator/metrics` call to replace 5-minute history in Prometheus. A newly started instance or one that has not served that route yet may lack the sought meter; that differs from "the route never errors". Nor should you infer the business port works merely because the separate management port still responds.

## 6. Selecting Traces to Inspect a Specific Path

After metrics, the question must narrow: "Why was POST /checkout in region vn-a slow during 10:00–10:10 UTC?" Use that exact time range and scope to search traces, instead of opening the newest trace at random.

Pick a representative set of traces:

- Error requests to see the path leading to failure.
- Slow yet successful requests to spot waits not exceeding timeouts.
- Normal requests on the same route as a baseline comparison.
- If an instance or version is suspected, compare the suspected group against the rest.

When reading a trace, inspect the entry operation, span relationships, wait gaps, and dependency calls. Pay attention to the execution path determining the request's completion time. Parallel spans overlap in time, so do not sum all span durations to infer end-to-end latency.

Illustrative example of a slow request:

| Operation | Observed duration | Next question |
| --- | --- | --- |
| POST /checkout | 2,400 ms | Where did the user wait? |
| Read cart | 35 ms | Is this unusual compared to normal requests? |
| HTTP client calling payment | 2,200 ms | Waiting for connection, network, payment-side processing, or retries? |
| Write result | 40 ms | Did the operation complete or get canceled? |

This is a hypothetical trace. HTTP client span duration does not mean all 2,200 ms were CPU on payment. It can include wait time and other stages depending on instrumentation. Check server-side spans, logs, and dependency metrics.

A large span may also wrap multiple unseparated operations. Then a valid conclusion is "isolated to the payment call", not yet "identified the exact failing statement".

### When No Trace Is Found

Separate these possibilities:

1. The request was not sampled.
2. Trace exporter or receiver failed, was overloaded, or was lagging.
3. The trace expired from retention.
4. Filters had the wrong service, time zone, region, or time range.
5. Trace context was lost across an HTTP client, queue, or async task.
6. The segment to inspect was not instrumented.

With Spring Boot 3.3, correlating logs with traces requires suitable Micrometer Tracing infrastructure; Actuator alone does not create the full tracing pipeline. Spring Boot has property `management.tracing.sampling.probability` controlling sampling probability for the corresponding configuration. Use HTTP client builders auto-configured by Spring Boot to preserve context propagation; manually constructed clients can break the path. See [Tracing for Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Do not raise sampling to 100% across all of production just to "guarantee seeing errors". If changes are needed, define scope, duration, ingestion capacity, and rollback method. Having no trace for an error does not prove the error never happened; continue with metrics, logs, and other evidence.

## 7. From Traces to Logs: Find Context, Not Just the Word ERROR

Use the selected trace ID to search logs in the right environment and time range. Add span ID when narrowing one operation, yet do not filter to a single span if you need the whole journey across services.

Useful fields include event time, service name, instance, version, log level, business event, trace ID, span ID, and error type. Keep relevant stack traces if collection is permitted; a message saying "failed" is usually not enough.

The example below is a **custom log format designed by a hypothetical application**, not Spring Boot 3.3's default JSON:

```json
[
  {
    "timestamp": "2026-01-15T10:03:21.100Z",
    "service": "checkout-api",
    "instance": "checkout-2",
    "version": "1.8.2",
    "level": "WARN",
    "event": "payment_call_failed",
    "traceId": "0123456789abcdef0123456789abcdef",
    "spanId": "1111111111111111",
    "errorType": "ReadTimeout",
    "elapsedMs": 2200
  },
  {
    "timestamp": "2026-01-15T10:03:21.110Z",
    "service": "checkout-api",
    "instance": "checkout-2",
    "version": "1.8.2",
    "level": "ERROR",
    "event": "checkout_failed",
    "traceId": "0123456789abcdef0123456789abcdef",
    "spanId": "2222222222222222",
    "httpStatus": 503
  }
]
```

Two events on the same trace show the payment call failed and checkout subsequently returned an error in the example. Two different span IDs do not mean broken correlation: one trace can contain many spans. Nor should these two lines be counted as two independent failed requests.

Read by questions:

- Where is the first relevant error, or are later lines merely consequences?
- Did the timeout happen waiting for a connection, while connecting, or waiting for a response?
- Were there retries, how many times, and did they amplify load on the dependency?
- Does the error belong to one instance or many instances?
- How do normal logs on the same route differ?

ERROR line counts do not replace failed-request ratios. One exception can be logged at multiple layers; conversely, a 5xx response can have no ERROR log at all.

If logs lack trace IDs, narrow by time, service, instance, and pre-designed correlation IDs. Note clearly that this is a weaker join; do not claim two lines belong to the same request just because they are a few milliseconds apart. For async tasks, check how context is propagated and restored rather than merely appending an arbitrary ID string to the message.

When collecting logs, do not log tokens, passwords, card data, or full sensitive bodies in exchange for diagnostics. Store only necessary fields, mask data per policy, and restrict access to incident records.

## 8. Adding Supporting Evidence by Hypothesis

Collect only evidence capable of distinguishing hypotheses. A large data bundle lacking clear source, timestamp, or instance is hard to use.

| Hypothesis | Evidence to cross-check | What cannot be concluded from one sign |
| --- | --- | --- |
| Error tied to a new deployment | Rollout timestamp, version per instance, config changes, un-upgraded group | A deploy near an incident does not prove the deploy caused it |
| Dependency responding slowly | Client/server spans, timeouts, queues, and dependency-side resources | Long client wait does not prove high server CPU |
| Database connection shortage | Active/waiting connections, acquisition time, queries, and DB-side locks | Full pool may be a consequence of slow queries or connections held too long |
| Blocked threads or lock contention | Multiple planned thread dumps spaced apart, thread states, queue metrics | A single snapshot showing WAITING does not prove deadlock |
| Memory/GC causing pauses | Memory curve, GC pause time, restarts/OOM, and related logs | High current memory does not prove a leak |
| Network or routing failure | Gateway evidence, DNS/TLS, connect timeouts, route changes | Absence of app logs does not mean requests were never sent |
| Observability pipeline failure | Scrape/export status, ingestion lag, store capacity, filters | Missing telemetry does not mean zero impact |

Actuator can assist with `threaddump`, `loggers`, `info`, or other diagnostic endpoints when configured and properly authorized. Do not assume every endpoint exists, has data, or is permitted. Build info in `info` also requires a corresponding data-generation source.

Thread dumps, heap dumps, and changing log levels carry different costs and sensitivities. Heap dumps can be large, put pressure on resources, and contain in-memory data. Do not capture dumps in bulk on a degraded system without first defining the question to answer. Prefer existing data; collect additional data following the system's operational procedure.

If temporary DEBUG is needed, scope to the exact logger, instance, and duration, recording the old level and who will revert it. Check disk space, latency, and data-exposure risk. Increasing logging application-wide can worsen the incident and create noise.

## 9. Recording Reproducible Evidence

Each piece of evidence should include:

- Source and scope: service, environment, region, instance, version.
- Time range, time zone, data retrieval timestamp.
- Queries and filters; units and aggregation windows for metrics.
- Access links or protected excerpts; retention period.
- Direct observations, interpretation, and what remains unknown.
- Collector, related action, and action timestamp.

Chart screenshots help communicate quickly yet should preserve queries and time ranges. If a link points to "last 15 minutes", someone opening it tomorrow will see different data. Use fixed time ranges or save suitable excerpts while preserving access controls.

Example of a sufficiently clear record:

```text
Incident: INC-042
Scope: checkout-api, production, vn-a, POST /checkout
Observation window: 2026-01-15 10:00–10:10 UTC
Observation: 5xx rate roughly 5%; p95 roughly 2.4 seconds
Source: metrics query saved in record, grouped by route
Sample trace: 0123456789abcdef0123456789abcdef
Observation in sample: payment call span took 2,200 ms then timed out
Related logs: payment_call_failed and checkout_failed on the same trace
Hypothesis: payment wait time contributed to checkout failures
Unknown: internal cause of slowness inside payment; representativeness of sample
Next check: cross-check queues and configuration changes on payment side
```

Numbers are illustrative data. "Roughly" is used for dashboard/estimated readings; do not turn them into exact counts if the source does not provide that precision.

## 10. Mitigating Impact and Verifying Recovery

You do not need to wait for root cause to mitigate severe impact. However, every action needs a hypothesis, scope, executor, and rollback condition.

For example: if evidence points to a new version causing errors and the old version remains compatible with current data, you may choose rollback per deployment procedure. If a dependency is overloaded, mitigation may be controlled load shedding or temporarily disabling nonessential functionality. Choosing a measure depends on architecture and actual operational permissions.

Do not treat raising timeouts or increasing pool sizes as a default fix. Longer timeouts can hold resources longer; adding connections can increase DB pressure; synchronized retries can amplify load. Evaluate cascading impacts and business safety, especially for operations that could create duplicate transactions.

Before a change, save lightweight evidence at risk of loss if conditions allow. Do not delay rescuing the system just to assemble a perfect record. Explicitly note timestamps of restarts, rollbacks, or traffic shifts because those actions also alter observed data.

After an action, verify across multiple dimensions:

1. Error rate and latency return to acceptable levels over the agreed observation window.
2. Traffic or business checks show requests are still being served, not merely that users disappeared.
3. Queues, backlogs, and resources stabilize; the problem was not simply shifted to another service.
4. Metrics/logs/traces collectors still work, so an "alert cleared" state is meaningful.
5. In-flight transactions are reconciled according to business procedures.
6. Temporary diagnostic changes are reverted or assigned an owner to track.

Recovery after a restart only proves symptoms subsided under fresh state. It does not explain why the system degraded. Separate service restoration time from root-cause conclusion.

## 11. End-to-End Scenario: Checkout Slow Because of Waiting on Payment

The entire scenario below is hypothetical to practice organizing an investigation.

### 11.1. Receiving the Alert and Narrowing Scope

At 10:05 UTC, an alert reported p95 of POST /checkout exceeded 1 second. The responder opened 09:45–10:15 UTC, confirmed fresh data, and checked actual traffic.

| Data in failing window | Illustrative value | Meaning |
| --- | --- | --- |
| Completed requests reconciled in counting source | 30,000 | Denominator is needed before stating a percentage |
| 5xx requests in the same counting scope | 1,500 | Ratio is 1,500 / 30,000 = 5% |
| p95 POST /checkout | Roughly 2.4 seconds | Distribution tail is slower than normal |
| GET /catalog | Near normal level | Scope may focus on checkout |
| Checkout CPU | No clear increase | No basis yet to blame checkout CPU as bottleneck |
| Multiple checkout instances | Same worsening trend | Check shared components |

Counts in the table are assumed reconciled over the same interval; do not require `rate` or `increase` to always reproduce those exact integers.

### 11.2. Connecting Traces, Logs, and the Dependency Side

The responder picked 10 error traces, 5 slow successful traces, and 5 normal traces. In 8/10 selected error traces, substantial waiting fell on the payment call. That is a property of the **selected sample**, not to be turned into a claim that "80% of all requests fail at payment".

Logs sharing the trace recorded timeouts. Therefore the team checked payment further instead of immediately enlarging the checkout pool.

The payment side provided two new pieces of evidence in the exact time range:

- Processing queue grew starting at 10:00 UTC, while incoming load stayed near prior levels.
- A configuration change at 09:59 UTC lowered concurrent workers from 32 to 8.

The team formed a hypothesis: reduced processing capacity caused the queue to grow, lengthening payment wait times and causing timeouts in checkout. To test it, they compared deployed configuration, queue charts, and the healthy pre-incident period; they also verified no other contradictory signals existed.

### 11.3. Action and Bounded Conclusion

Under an authorized procedure in the scenario, the team reverted only the payment config change, logged 10:12 UTC, and monitored queue draining.

Afterward, the queue dropped, and checkout p95 and 5xx rate returned to baseline while traffic remained comparable. This chain of evidence **strongly supports** the hypothesis that reduced processing capacity was a contributing factor to the incident. The record still needs to explain why the bad config entered, which tests were missing, and whether any other simultaneous change occurred.

A useful conclusion is a testable chain: config change → reduced processing capacity → longer wait times → checkout timeouts. "Payment had an issue" is too vague; "rolled back so we definitely found every cause" overclaims.

## 12. Short Runbook for the Same Alert Class

A runbook applicable to the scenario above can be organized as follows:

| Stage | Actions | Transition condition |
| --- | --- | --- |
| Triage | Record service, region, route, threshold, time, and coordinator | Exact alert and scope confirmed |
| Verify | Check telemetry freshness, traffic, errors, and latency | Real impact distinguished from observability failure |
| Isolate | Compare routes, instances, versions, and gateway | A few concrete hypotheses formed |
| Inspect traces | Pick error, slow, and normal samples in the same window | Segment needing deep check identified or missing traces noted |
| Inspect logs | Search by trace ID and scope; read cause/effect chain | Events or error types identified to cross-check |
| Gather evidence | Check deploys, config, queues, or dependencies per hypothesis | Basis to pick an action or refute hypothesis |
| Mitigate | Execute authorized option, log timestamp and rollback method | Mitigation deployed and evaluation method known |
| Verify | Check serving quality, load, backlog, and observability pipeline | Agreed stability conditions met |
| Handover | Save record, unknowns, monitor owner, and rollback items | Next owner understands follow-up work |

If impact grows fast or exceeds responder capacity, escalate immediately to the designated operations/dependency lead. Do not spend too long on one hypothesis without new evidence; set timeboxes suited to urgency and update the record when changing direction.

## 13. Self-Practice and Reasoning Check

### Exercise

Use the following hypothetical facts, without causing an incident on a real system:

- Observation window 14:00–14:10 UTC has 12,000 completed requests, 240 HTTP 5xx requests.
- p95 rose on POST /checkout; read routes remained roughly stable.
- Available trace of one failed request spends most of its time in the payment call.
- Logs sharing the trace record a timeout, yet no payment-side evidence exists yet.
- One instance just restarted and has little historical data.
- Dashboard cannot find a trace for another failed request.

Write an investigation note containing the error rate, observations, hypotheses, unknowns, and next checks. Then explain why you should not yet conclude "payment ran out of CPU" or "a request without a trace succeeded".

### Reference Guide

The error rate is `240 / 12,000 = 0.02 = 2%` in the given counting scope. The trace observation only shows one request waiting on the payment call path. Hypotheses could be a slow dependency, connection wait, or network issue; there is not yet data to single out CPU.

Reasonable next steps are selecting more slow/normal samples, cross-checking payment-side metrics and logs, checking deployment timestamps, and verifying data freshness. The recently restarted instance must be kept distinct from instances running throughout the window; do not compare their cumulative counters as if they shared the same lifetime.

A request without a trace may be unsampled or missing data in the pipeline. Keep that missing information in the record and use remaining sources. If deciding to mitigate, state the concrete measure along with verification criteria, without claiming root cause is already known.

An investigation passes requirements when others can trace back from the alert to queries, trace samples, logs, and supporting evidence—and clearly recognize what is fact, what is hypothesis, and why the chosen action was selected.

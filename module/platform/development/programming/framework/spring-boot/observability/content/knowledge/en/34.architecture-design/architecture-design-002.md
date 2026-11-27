# Selecting Traces for Latency Investigation

In a Spring Boot system composed of multiple services, a slow request may traverse several layers: HTTP server, business layer, database, message broker, and external services. Metrics show where latency is increasing and how many requests are affected; distributed tracing helps follow a specific request to pinpoint the processing segment contributing most to wait time. Logs add event details at that exact moment.

Selecting a trace is an investigative decision. A trace must represent the observed symptom, carry enough context to explain the request path, and be comparable against a normal baseline case. Simply opening the slowest trace in the system is often insufficient: it could be an anomalous outlier, a trace missing spans, or a case outside the affected user group.

## 1. Starting from Latency Signals on Metrics

Before searching for traces, determine precisely which latency is rising. A service-wide aggregate metric can mask a problem occurring only on one endpoint, one application version, or one deployment region.

For HTTP servers, start with duration histograms and percentiles such as p50, p95, and p99. The average may remain healthy while a small fraction of requests suffer severe slowdowns. Also check request rate, error rate, and resource saturation such as CPU, memory, connection pools, or thread pools. These signals help distinguish an isolated slow request from a problem impacting an entire group of requests.

Record meaningful filter dimensions before opening the tracing backend:

| Filter Dimension | Question to Answer | Example |
| --- | --- | --- |
| Service and operation | Which component has abnormal latency? | `checkout`, `POST /checkout` |
| Time | When did the issue start and how long did it last? | 14:00–14:15, matching dashboard timezone |
| Deployment version | Did the issue appear after a release? | `service.version=2026.11.22` |
| Region or cluster | Is the issue localized or system-wide? | `region=ap-southeast-1` |
| Outcome | Are slow requests also failing? | HTTP 5xx, exception, timeout |

Prefer dimensions with bounded, comparable value domains. Do not put every request attribute into metrics; high-cardinality values can explode time series counts and storage costs.

## 2. Understanding Traces and Spans Before Sampling

A **trace** represents the journey of a request across one or more components. A trace has a trace ID to correlate spans belonging to the same journey. A **span** represents a unit of work with a start time, duration, operation name, span kind, status, and descriptive attributes.

For example, a `POST /checkout` request might produce a span tree like:

```text
checkout-api  [SERVER]
├── validate-cart
├── inventory.reserve  [CLIENT]
│   └── inventory-service  [SERVER]
│       └── inventory-db.query  [CLIENT]
├── payment.authorize  [CLIENT]
│   └── payment-service  [SERVER]
└── checkout-db.update  [CLIENT]
```

Span names and grouping depend on the instrumentation in use. The diagram above illustrates parent-child relationships; not every library produces spans with these exact names.

When investigating latency, distinguish between:

- **Trace or root span duration** shows the total time measured between the start and end of the root operation. For an HTTP server span, this is typically the server-side request processing time.
- **Individual child span duration** shows how long a specific operation took, such as calling a database or another service.
- **Gaps between spans** may indicate queueing, scheduling, processing in uninstrumented code, or missing context propagation.
- **Parent-child relationships and start timestamps** reveal whether operations execute sequentially or in parallel.

Do not sum all child span durations to derive request latency. Nested spans overlap in time, and parallel branches run concurrently. When identifying root causes, examine the critical path: the chain of operations that determines when the request can complete.

## 3. Process for Selecting Valuable Traces

### Step 1: Turn the Symptom into Concrete Filters

From the dashboard, identify the affected service, operation, time window, version, and region. For example: p95 of `POST /checkout` increased for 15 minutes after deploying a new version in one region. These filters narrow the search space and avoid mixing requests with different characteristics.

Choose a time range close to when the metric spike occurred. If an incident lasted only a few minutes, searching across multiple days can pull in unrelated traces.

### Step 2: Retrieve Traces from the Right Request Group

In the tracing backend, filter by the identified attributes. Depending on the storage system, field names may vary; semantically, filters typically include:

```text
service.name = "checkout"
span.kind = SERVER
http.request.method = "POST"
http.route = "/checkout"
deployment.version = "2026.11.22"
start_time within the investigation window
```

Then sort by duration and inspect the distribution. Do not use raw URLs containing order IDs or user IDs as the primary filter if a route template suffices to distinguish the operation. Tracing backends have different query syntaxes; the snippet above is an illustrative attribute set, not a universal query statement across all products.

### Step 3: Select Both Slow Traces and Reference Traces

A good sample set typically includes multiple trace types:

1. **Traces near p95 or p99** to represent the request group forming the latency tail.
2. **A few significantly slower traces** to uncover outliers and rare causes.
3. **Normal reference traces** of the same operation, version, and region, with durations near p50 or typical levels.
4. **Error or timeout traces**, if error rates increased concurrently or errors might prolong requests.

Traces near the percentile help understand the experience of the affected request group. Outliers can reveal edge cases, but a single outlier should not represent the entire incident. Reference traces help identify which spans appear or lengthen exclusively in the slow group.

If the tracing backend supports finding traces via metric exemplars, start from the latency histogram's exemplars. An exemplar links a metric observation to a trace ID, allowing a direct jump from an aggregated signal to a specific request. This capability depends on instrumentation, exporter, and backend configuration.

### Step 4: Verify the Trace Has Sufficient Context

Before drawing conclusions, verify that the trace includes an appropriate root span, key child spans, and trace context across services. A trace containing only the initial HTTP span may reflect missing instrumentation or propagation rather than proving the request made no dependency calls.

Check span status, exceptions, timeouts, service attributes, version, and timestamps as well. If spans arrive late or are dropped during export, the trace may be incomplete. When traces are missing data, cross-check against logs and metrics for the same time window.

### Step 5: Read the Critical Path to Find Latency Contributors

Open the root span and follow child spans by start and end times. Focus on spans lying on the critical path with abnormal durations compared to reference traces.

For example, a 1.4-second `POST /checkout` trace might show:

| Operation | Illustrative Duration | Interpretation |
| --- | ---: | --- |
| Root HTTP server span | 1,400 ms | Total processing time measured at the server |
| `payment.authorize` | 1,080 ms | Likely the branch governing completion time |
| `inventory.reserve` | 75 ms | Close to normal level |
| `checkout-db.update` | 28 ms | Not the dominant segment in this trace |

Child span durations may overlap or run in parallel, so this table is not a summation for root duration. Verify via the timeline. If `payment.authorize` is on the critical path and takes much longer than in reference traces, inspect downstream spans in the payment service, external dependencies, retries, and timeouts.

If no child span explains the majority of the time, look for gaps between spans. Gaps may stem from queues, thread pools, lock contention, schedulers, uninstrumented code, or propagation failing across an asynchronous boundary. Use pool, queue, and resource metrics alongside logs at that timestamp to test hypotheses.

### Step 6: Correlate Logs, Metrics, and Deployment Changes

Traces reveal structure and duration; logs reveal events and error details; metrics reveal prevalence and trends. Use the trace ID or span ID in logs to pull matching log lines. Use timestamp, service, route, and version to cross-reference dashboards.

Check whether latency coincides with configuration changes, releases, traffic spikes, database migrations, dependency incidents, or connection/thread pool limit changes. A single trace helps form a hypothesis; metric trends and multiple similar traces help confirm it.

### Step 7: Confirm the Cause with a Controlled Comparison

After identifying a suspect operation, compare multiple slow traces against normal traces along the same filter dimensions. Verify whether the pattern repeats for the same dependency, version, or region. If possible, compare against a pre-release time window or a set of instances that have not received the change.

Conclude only when evidence aligns across multiple signals. For instance, increased duration on payment call spans, elevated latency in payment service metrics, and retry timeout entries in logs form stronger evidence than a single trace with a long payment span.

## 4. Using Micrometer Observation to Produce Useful Traces in Spring Boot

In Spring Boot, Micrometer Observation provides a unified instrumentation point. An Observation can be processed by handlers to produce metrics, tracing, or both, depending on application configuration. With Spring Boot 3, Micrometer Tracing is commonly used to connect tracing with the corresponding bridge and exporter.

Auto-instrumented libraries can create spans for HTTP servers, HTTP clients, or other integrations when dependencies and configuration are in place. Verify actual instrumentation for each client and framework. For important business operations not yet observed, create Observations around meaningful boundaries rather than creating spans for every method call.

Example instrumenting an inventory reservation operation:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryFacade {
    private final ObservationRegistry observationRegistry;
    private final InventoryService inventoryService;

    public InventoryFacade(
            ObservationRegistry observationRegistry,
            InventoryService inventoryService) {
        this.observationRegistry = observationRegistry;
        this.inventoryService = inventoryService;
    }

    public Reservation reserve(String sku, int quantity) {
        return Observation.createNotStarted(
                        "inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> inventoryService.reserve(sku, quantity));
    }
}
```

Observation names should be stable and describe the operation. Low-cardinality key-values such as `operation=reserve` can serve as dimensions for both metrics and spans. Add only key-values with investigative value; avoid putting per-request varying data into low-cardinality tags.

When you need to attach a value meaningful only in traces, Micrometer Observation supports high-cardinality key-values. However, high-cardinality does not mean zero cost: values are still transmitted and stored in the tracing backend. Include only necessary attributes, and never record secrets or unauthorized personal data.

### Configuring Sampling Deliberately

With Spring Boot configured for Micrometer Tracing, sampling probability can be set via `management.tracing.sampling.probability`. The example below merely illustrates configuration syntax; actual rates must be based on traffic volume, investigation goals, storage budgets, and operational policies:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

A value of `0.10` means probabilistic sampling of 10% under the corresponding head-based mechanism. Check your Spring Boot version, tracing bridge, and exporter to confirm the configuration is applied properly. Sampling configuration only decides which traces are retained; it does not replace instrumentation, context propagation, or export configuration.

## 5. Choosing a Sampling Strategy Based on Investigation Goals

Sampling determines which traces are recorded and sent. Choosing too low a rate can lose rare cases; keeping every trace can drive up bandwidth, CPU, storage volume, and query costs.

| Mechanism | Decision Point | Strengths | Limitations for Latency Investigation |
| --- | --- | --- | --- |
| Head-based sampling | When the trace starts | Early decision, predictable cost; easy to implement in the app | Unknown at decision time whether the request will be slow or fail, so outliers can be missed |
| Tail-based sampling | After the collector receives complete trace data | Can retain slow traces, error traces, or matching traces after outcome is known | Requires a tail-sampling collector with sufficient memory and policies; all spans of a trace must route to the same collector |
| Policy-based sampling | By service, operation, or defined rules | Can allocate different rates to critical flows | Complex policies need monitoring to avoid dropping target request groups |

With head-based sampling, a trace has the same probability of being kept as any other trace at start time, so a request that only slows down late in its journey may still be dropped. Increasing the sampling probability improves visibility but increases data volume across all requests matching that policy.

Tail-based sampling fits when you need to prioritize traces with high duration or error status. The collector must wait for enough spans to evaluate the entire trace. If spans of a trace are distributed across independent collectors, tail sampling policies may lack sufficient data to make the right decision. Routing and memory limits must be sized for actual traffic.

In production, you can combine a baseline sampling rate with collector-tier policies that keep error or slow traces. Monitor received trace counts, dropped trace counts, export latency, and collector capacity after every change. Ensure sampling policies do not discard data required to meet operational goals or incident investigations.

## 6. Ensuring Trace Context Propagates Across the Request

A trace is only useful when trace context propagates across processing boundaries. For HTTP, services must inject and extract the same propagation standard, such as W3C Trace Context via the `traceparent` header. If a service starts a new trace instead of continuing the incoming context, the journey fragments into multiple traces and critical path analysis becomes difficult.

Pay special attention to asynchronous boundaries:

- When offloading work to an executor or another thread, context must be captured and restored via the appropriate context propagation mechanism.
- For message brokers, producers must attach context to message metadata and consumers must restore context upon processing.
- For scheduled jobs or background tasks not originating from a request, create a new trace with appropriate links if information about the initiating task exists.
- For HTTP clients and database clients, verify that the libraries in use have active instrumentation and exporters.

When inspecting a broken trace, verify both propagation and instrumentation. Missing spans may indicate an uninstrumented library; missing links between two services may indicate lost context propagation; spans absent from the backend may also result from sampling or export failures.

## 7. Keeping Cardinality and Span Attributes Within Bounds

Metrics and traces have different cardinality requirements. Metric tags create time series; a tag with millions of distinct values can cause series counts to explode rapidly. Therefore, metrics should use route templates and bounded value domains.

| Recommended for Metrics | Avoid as Metric Tags |
| --- | --- |
| `http.route=/orders/{orderId}` | `/orders/8f3...` with IDs changing per request |
| `http.request.method=POST` | Full URLs with arbitrary query strings |
| `region=ap-southeast-1` | `user.id` or `request.id` |
| `result=success` or `result=failure` | Emails, tokens, phone numbers, or personal data |

Trace spans can carry additional high-cardinality attributes to investigate a specific request, though cost, access control, and retention periods must still be weighed. Never log or record access tokens, session cookies, passwords, payment data, or sensitive payloads in spans or logs. If a business record must be linked to a trace, prefer an approved reference identifier with access controls on the storage backend.

Do not use trace IDs, span IDs, user IDs, or request IDs as metric tags. These IDs are meant for correlating logs and traces, or used via exemplars if the metrics system supports them.

## 8. Correlating Metrics, Logs, and Traces in Investigation Workflows

The three signals answer three different sets of questions:

| Signal | Primary Question | Use During Investigation |
| --- | --- | --- |
| Metrics | How widespread is the issue and when did it start? | Identify percentiles, request rate, error rate, saturation, and blast radius |
| Traces | Which operations did a request traverse and where did it wait? | Select representative traces, analyze spans and critical path |
| Logs | What specific event or error occurred during the operation? | Find exceptions, retries, timeouts, and operational details tied to trace/span IDs |

A good dashboard should allow jumping from a latency histogram to traces via exemplars when supported. Application logs should include trace ID and span ID in MDC or equivalent structured fields so they can be queried alongside traces. Service, environment, version, and timestamp attributes must remain consistent across all three signals.

Never rely on a single trace alone to conclude root cause. Use metrics to confirm scope and trend, traces to pinpoint the suspect operation, and logs to inspect events occurring within that operation.

## 9. Investigation Example: Checkout p95 Spike After Release

Suppose a dashboard shows p95 for `POST /checkout` rising from around 450 ms to 1.4 seconds after deploying a new release. Request rate is nearly unchanged, error rate ticked up slightly, and the symptom is concentrated in a single region.

The trace selection workflow can proceed as follows:

1. Scope the query to `checkout`, route `POST /checkout`, the affected region, the new version, and the 15-minute symptom window.
2. Pick several traces around p95, add a few p99 or outlier traces, and select reference traces near p50 for the same route and version.
3. Inspect the root server span and child spans. If many slow traces show `payment.authorize` taking around one second, whereas reference traces take only tens of milliseconds, that operation warrants deeper investigation.
4. Open spans in the payment service, checking retries, timeouts, and external dependencies. Correlate with payment latency metrics, connection pools, and logs sharing the same trace ID.
5. Compare against the previous version or unaffected regions. If payment latency increased only in the new version and logs show timeout retries, there is grounds to inspect client timeout changes, retry policies, or dependency endpoints in the release.

The takeaway of this example is not that all checkout latency comes from payment. If slow traces show different critical path shapes, group them and investigate separately. If a trace lacks a payment span yet the request is still slow, check instrumentation, context propagation, and gaps between spans.

## 10. Common Pitfalls When Selecting Traces

- **Picking only the slowest trace:** outliers may not represent the affected request group. Select traces by percentile and include reference traces.
- **Using averages to guide investigation:** averages hide tail latency. Check p95, p99, and duration distributions.
- **Summing all child span durations:** nested spans and parallel branches make simple addition wrong. Read the timeline and critical path.
- **Filtering by raw URLs or arbitrary IDs:** creates overly broad or incomparable queries and risks exposing data. Use route templates and controlled attributes.
- **Setting sampling too low without outlier retention:** rare slow traces may be lost. Evaluate head or tail sampling against system capacity.
- **Assuming a missing span means no operation occurred:** verify instrumentation, propagation, sampling, and export before concluding.
- **Inspecting traces without cross-checking other signals:** use metrics and logs to confirm scope, timing, and root cause.

## 11. Pre-Conclusion Checklist

- [ ] Affected service, operation, time range, and percentile have been identified.
- [ ] Traces are filtered by appropriate route template, version, and region.
- [ ] Sample includes traces near p95/p99, outliers where needed, and normal reference traces.
- [ ] Root span, key child spans, status, and trace context are sufficient for interpretation.
- [ ] Critical path is identified from the timeline; span durations are not mechanically summed.
- [ ] Logs correlate via trace ID/span ID and metrics confirm the blast radius.
- [ ] Sampling, propagation, and exporters are not dropping the target trace group.
- [ ] Recorded attributes do not create unbounded cardinality or contain sensitive data.
- [ ] Root cause hypothesis is verified across multiple traces and multiple signals.

Good trace selection narrows an investigation from a latency chart down to an operation backed by concrete evidence. Conclusion quality depends on picking the right request group, preserving trace context end-to-end, reading the critical path accurately, and cross-checking results with metrics and logs. This is how distributed tracing functions as part of observability architecture in Spring Boot, rather than merely collecting traces to view after an outage.

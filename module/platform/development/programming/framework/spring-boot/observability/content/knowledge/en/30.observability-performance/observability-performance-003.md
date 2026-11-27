# Async Exporter in Spring Boot Observability

An application sometimes produces metrics, logs, and spans faster than a telemetry backend can ingest them. If every request had to wait for telemetry to be sent over the network, the exporter could increase business request latency or tie the application's availability directly to the monitoring backend's health. **Async exporters** decouple telemetry recording from data transmission: the application writes to a queue/buffer, and a background worker batches and sends the data.

The **Async Exporter** lesson belongs to the **Observability Performance** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; you will learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to describe an asynchronous export pipeline, understand queues/batching/backpressure/drops/retries, distinguish a Micrometer registry from OpenTelemetry `BatchSpanProcessor`, choose timeouts and batch limits, handle shutdown safely, and monitor the telemetry pipeline itself to detect data loss or exporter backlog.

## 1. Why Is Asynchronous Export Needed?

Exporters send telemetry from the process to a backend or collector. If sent synchronously on the request path, exporter latency adds directly to application latency. If the backend becomes temporarily unavailable, business threads may block or suffer unintended failures.

Async export typically involves these steps:

1. Instrumentation creates observations/spans/log records or updates meters.
2. The SDK/registry writes data into a buffer or queue.
3. A worker pulls data in batches.
4. The exporter serializes and sends over OTLP/HTTP, OTLP/gRPC, or the registry's protocol.
5. The Collector/backend receives and stores the data.

```mermaid
flowchart LR
    A["Application threads"]
    B["Telemetry SDK / registry"]
    C["Bounded queue"]
    D["Batch worker"]
    E["Exporter"]
    F["Collector"]
    G["Observability backend"]
    A --> B --> C --> D --> E --> F --> G
```

The queue acts as a buffer between telemetry generation speed and export speed. It absorbs short bursts, but cannot hold data indefinitely if the backend stops accepting traffic for an extended period.

## 2. Async Does Not Mean Free

Async export shifts cost from request threads to memory, worker threads, and network I/O. These costs still reside inside the process:

- Buffers use heap/direct memory.
- Workers need CPU to serialize, compress, and transmit.
- Queues introduce a delay between when a span ends and when the backend receives it.
- When the queue fills up, the SDK must block, drop, or apply another policy.
- If the process crashes before flushing, data in the in-memory queue may be lost.

Therefore, async export must be designed as a pipeline with capacity, a latency budget, and a failure policy. Do not simply enable async and assume telemetry will always be delivered.

## 3. Distinguishing Pipeline Components

| Component | Responsibility |
| --- | --- |
| Instrumentation | Creates observations/spans/log records or updates meters |
| SDK/registry | Manages lifecycle, processors, aggregation, and export |
| Queue/buffer | Holds telemetry awaiting processing |
| Batch processor | Groups multiple records to reduce send calls |
| Exporter | Converts data to protocol/transport |
| Collector | Receives, processes, batches, filters, retries, and routes telemetry |
| Backend | Stores, queries, dashboards, and alerts |

A Spring Boot application may use Micrometer for metrics and Micrometer Tracing/OTel bridge for traces. Export mechanisms for each signal are not necessarily identical: Prometheus typically scrapes metrics from an endpoint; OTLP traces are typically pushed via an exporter; logs may go through a logging appender/agent or an OTLP pipeline.

Do not refer to all of these paths as a single async exporter. Identify the specific signal and owner before configuring.

## 4. Micrometer Registry vs. OpenTelemetry Batch Processor

Micrometer provides a facade for metrics and Observation. The registry manages meter state/aggregation and exports according to each registry's semantics. For instance, a Prometheus registry typically exposes a scrape endpoint; the backend scrapes periodically rather than necessarily using an async push queue like a span exporter.

With OpenTelemetry tracing, `BatchSpanProcessor` receives ended spans, puts them into a queue, builds batches, and calls `SpanExporter` on a worker thread. This reduces export work on application threads.

Common configuration concepts for a batch processor:

- `maxQueueSize`: limit on queued spans.
- `maxExportBatchSize`: maximum spans in a single export call.
- `scheduleDelay`: wait interval before the worker exports a batch.
- `exportTimeout`: maximum duration for a single export call.

Property/env var names and defaults depend on the OTel SDK/version and how Spring Boot configures the SDK. Check the version selected by dependency management; do not copy defaults from a different SDK release.

## 5. Configuring the OTLP Exporter in Spring Boot

Spring Boot can configure tracing export via OTLP when the corresponding dependencies and auto-configuration are present. Illustrative example:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Verify the endpoint, protocol, and property prefix for your Spring Boot version. Some setups use OTLP/gRPC with a different endpoint/port; do not mix the HTTP path `/v1/traces` with a gRPC endpoint. If configuring the OTel SDK manually, configure the batch processor and exporter using the exact SDK properties or application bean wiring.

Keep endpoints/credentials out of source code. Use environment/configuration management and a secret manager appropriate for your deployment platform. Do not enable a second exporter if an agent or Spring Boot already owns the provider and export pipeline.

## 6. Queue Size and Batch Size

Queue size caps how much telemetry can wait for export. Batch size determines how many records are sent in a single export request.

| Parameter | Too small | Too large |
| --- | --- | --- |
| Queue size | Prone to drops during short bursts | Wastes memory, retains stale data |
| Batch size | Many small requests, high overhead | Large payloads, CPU-heavy serialization/transport and timeout-prone |
| Schedule delay | Frequent exports, underfilled batches | Telemetry arrives later at the backend |
| Export timeout | Fails easily when backend is slow | Worker may stay occupied for a long time |

There is no single optimal value for all services. Measure spans/second, average span size, network throughput, backend ingest capacity, and memory budget before choosing.

A rough estimate for queue memory:

\[
\text{Queue memory} \approx
\text{queued items} \times \text{average in-memory item size}
\]

This is only an estimate. Object overhead, attributes, events, links, string storage, and batch copies can make the footprint larger than the serialized payload.

## 7. Backpressure and Queue Full Behavior

Backpressure is how the pipeline reacts when producers generate telemetry faster than consumers/exporters can process it. Common policies:

- **Drop newest:** discard new records when the queue is full; older data has a chance to be exported.
- **Drop oldest:** evict old records to keep newer data, if supported by the implementation.
- **Block producer:** block the thread generating telemetry until queue space opens; can increase business latency.
- **Bounded wait/reject:** wait up to a limit, then discard data.

The exact policy depends on the SDK/processor. Do not assume every exporter lets you choose any policy. OTel `BatchSpanProcessor` has behavior defined by its implementation; check docs/version before relying on a specific policy.

For tracing, dropping spans can leave gaps in traces but must not fail business requests. Avoid letting telemetry export failures propagate exceptions back to the business path unless there is an extraordinary, explicitly designed requirement.

## 8. Retries, Timeouts, and Duplicate Delivery

Exporters may retry on transient errors such as timeouts, connection resets, or HTTP 5xx responses. Retries must be bounded:

- Use a timeout on every export attempt.
- Use exponential backoff and jitter if supported by the exporter/collector.
- Limit retry duration and attempt counts.
- Avoid unbounded retries that prevent the queue from ever draining.
- Monitor retry counts and export failures.

A timeout does not prove the collector never received the payload. If the exporter retries, duplicate delivery can occur depending on protocol and backend. Trace/span IDs help identify the same telemetry item, though you should not assume every backend deduplicates completely.

Do not wrap an exporter that already has a retry policy in your own retry loop without understanding the interaction; it can multiply send attempts and worsen backlog.

## 9. Shutdown and Data Flushing

When Spring Boot receives SIGTERM, the process needs time to finish in-flight requests, close resources, and flush telemetry queues. If the container is killed immediately, buffered data can be lost.

A shutdown strategy should:

1. Stop accepting new traffic and begin graceful shutdown.
2. Allow in-flight business work to finish within the termination grace period.
3. Invoke SDK/provider/exporter shutdown/close to flush data according to supported lifecycle hooks.
4. Set a flush timeout smaller than the total shutdown budget.
5. Terminate the process before the orchestrator sends SIGKILL.

Spring Boot or the OTel integration may manage the lifecycle automatically. Do not invoke shutdown multiple times or close the provider while the application context still needs it. Verify the lifecycle owner in your actual configuration.

For example, Kubernetes `terminationGracePeriodSeconds` must cover both application draining and telemetry flushing, without being excessively long just to try forcing everything out while the collector is down.

## 10. Metrics, Traces, and Logs Have Different Export Semantics

| Signal | Common export mechanism | What to observe |
| --- | --- | --- |
| Metrics | Pull/scrape or push registry exporter | Scrape failures, scrape duration, series count, export errors |
| Traces | Batch processor push exporter | Queue occupancy, dropped spans, export latency/failures |
| Logs | Appender/agent/OTLP pipeline | Appender queue, blocked appenders, dropped log events |

For instance, Prometheus scraping does not use an in-application queue the same way `BatchSpanProcessor` does. If a metrics registry uses step aggregation or a push exporter, semantics differ again. Check the specific registry before applying queue/batch concepts.

Logs often have different retention/audit requirements than traces. If a log appender blocks when the backend slows down, logging can become a bottleneck; if the appender drops logs, counters/alerts are needed to know data was lost.

## 11. Observing the Exporter Pipeline Itself

The exporter also needs to be observable. Useful signals:

- Queue size/current occupancy and utilization ratio.
- Queue capacity/max.
- Dropped spans/records.
- Export batch size.
- Export duration/latency.
- Export request failures/timeouts.
- Retry count/backoff.
- Shutdown flush duration and records flushed.
- Collector receiver refused/failed records.

Metric names depend on the SDK/exporter/collector. Do not hardcode meter names before checking what your metrics endpoint or exporter instrumentation actually emits.

Alerts should reflect impact:

- Sustained high queue utilization.
- Increasing drop counter.
- Export failure rate exceeding baseline.
- Export duration approaching timeout.
- Collector refusing data or unavailable for an extended period.

A brief queue utilization spike during a burst can be normal if the queue drains quickly with zero drops.

## 12. Sampling and Async Export Are Separate Decisions

Sampling decides which spans are kept for export. The async processor decides how kept spans are transmitted. Increasing queue size does not recover spans discarded by the sampler; increasing the sampling rate does not fix a congested exporter.

Diagnose in order:

1. Verify whether spans were created and kept by sampling.
2. Verify whether ended spans enter the batch processor.
3. Check whether the queue is full or dropping.
4. Check exporter requests and collector responses.
5. Check backend ingest/query.

Do not conclude that missing traces mean sampling dropped them. The issue could lie in instrumentation, queue, exporter, network, collector, or backend.

## 13. Security and Data in Queues/Exports

Async queues usually live in process memory. If an exporter uses disk spooling or a persistent collector queue, telemetry may persist longer and carry protection requirements similar to log data.

- Do not export credentials, access tokens, or raw authorization headers.
- Use TLS for transport over untrusted networks.
- Authenticate exporter-to-collector via workload identity/secret management.
- Limit attributes and payload size.
- Set retention and access policies on the collector/backend.
- Be cautious with disk buffering since telemetry data may contain PII.

An in-memory queue is not durable storage. If you need delivery guarantees across process crashes, choose a pipeline with appropriate persistence/durability and accept the added latency, disk I/O, and operational complexity.

## 14. Testing the Async Exporter

| Test | What to prove |
| --- | --- |
| Batch test | Multiple spans are grouped into batches within limits |
| Queue full test | Behavior when full matches policy and does not break business requests |
| Slow exporter test | Backpressure/drops are controlled |
| Timeout/retry test | Transient failures do not cause infinite retries |
| Shutdown flush test | Provider flushes within budget on close |
| Export failure test | Failure metrics/logs are emitted |
| Duplicate test | Retry behavior does not cause dashboards to double-count outside semantics |
| Security test | Tokens/PII do not appear in exported payloads |

Example test strategy with an in-memory exporter:

```java
// Pseudocode:
// 1. Configure a test SpanExporter that stores exported spans in memory.
// 2. Create a BatchSpanProcessor with a small queue and batch size.
// 3. End several spans.
// 4. Force/await a flush using the processor lifecycle API.
// 5. Assert exported span count and attributes.
// 6. Simulate exporter failure and verify the documented drop/retry behavior.
```

This is pseudocode; exact APIs depend on the OpenTelemetry SDK version. Tests should avoid fixed sleeps if the processor provides flush/shutdown synchronization. No connection to a production backend is required to test batch semantics.

## 15. Common Pitfalls

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Traces appear late | Large schedule delay or queue backlog | Queue occupancy, batch schedule, and export duration |
| Spans lost during traffic bursts | Small queue capacity or slow exporter | Dropped counter, batch size, and collector throughput |
| Request latency rises when collector is down | Export path blocks producers or retries synchronously | Processor, queue policy, and exporter timeout |
| Memory grows over time | Queue backlog not draining or oversized queue | Occupancy trend, average item size, heap |
| Final telemetry lost on shutdown | No flush or grace period too short | SDK lifecycle, flush timeout, and termination budget |
| Continuous export timeouts | Large payloads, slow network/backend | Batch size, timeout, collector health |
| Duplicate telemetry | Retries or multiple pipelines/providers exporting | Provider ownership, retry semantics, and IDs |
| Queue stays nearly full | Sustained producer rate exceeds export capacity | Sampling, collector capacity, and exporter throughput |
| Logs slow down requests | Synchronous/blocking appender | Appender queue, disk/network latency |
| Metrics lack queue stats | Signal/registry does not use that async queue | Check the right exporter/processor and metric source |

## 16. Practical Scenario: Slow Collector Fills Trace Queue

**Hypothetical scenario:** `orders-service` generates about 4,000 spans/second during a traffic surge. The OTLP collector slows down due to a backend storage outage. The application's trace queue grows steadily, exporter timeouts appear, and dropped spans start rising.

Investigation workflow:

1. **Confirm scope:** check queue occupancy, export latency/failures, and dropped spans per pod.
2. **Check the collector:** receiver refused counts, exporter queue, backend ingest latency, and network errors.
3. **Keep the business path stable:** verify application threads are not blocked by telemetry export; inspect request latency and thread dumps if necessary.
4. **Reduce telemetry volume carefully:** adjust sampling or drop low-value spans per policy; do not disable all instrumentation blindly.
5. **Restore capacity:** scale collector/backend throughput or tune payloads/batches based on data; do not simply grow the queue indefinitely.
6. **Check shutdown:** ensure pod termination has a reasonable flush budget.
7. **Verify:** the queue drains back to baseline, export failures/drops stop climbing, and business latency is unaffected.

An async queue absorbs short bursts; it does not resolve a sustained capacity mismatch. If the producer rate stays higher than the consumer rate, the queue will eventually fill.

## 17. Self-Check Exercises

**Exercise 1.** What problem does an async exporter solve?

*Hint:* It decouples network export from the request path using a buffer/worker, reducing the chance that exporter latency blocks business threads.

**Exercise 2.** Why can't a queue grow indefinitely?

*Hint:* Process memory is finite; a huge queue increases heap usage and retains older telemetry longer.

**Exercise 3.** How can a full queue be handled?

*Hint:* Drop, block, or bounded wait depending on the implementation; understand the processor's actual policy.

**Exercise 4.** What are the trade-offs of an overly large batch size?

*Hint:* Large payloads, CPU-heavy serialization, higher risk of network timeouts, and higher peak memory usage.

**Exercise 5.** Why is flushing on shutdown necessary?

*Hint:* Data remaining in the in-memory queue can be lost when the process terminates; flushing sends remaining items within the shutdown budget.

**Exercise 6.** How do sampling and async export differ?

*Hint:* Sampling decides which spans are kept; async export decides how kept spans are transmitted.

**Exercise 7.** Should an alert fire when queue occupancy is high even before drops occur?

*Hint:* Watch the trend and duration; brief spikes can be normal, while sustained backlog signals a capacity issue.

**Exercise 8.** Why doesn't Prometheus scraping necessarily use the same queue model as `BatchSpanProcessor`?

*Hint:* Prometheus typically pulls metrics from the registry; the OTel batch processor pushes spans through an exporter. Each signal has a different lifecycle.

## 18. Key Takeaways

- An async exporter decouples telemetry creation from network export using a queue, worker, and batching; it reduces blocking but still consumes memory, CPU, and network.
- Queues must be bounded. When the producer rate persistently exceeds export capacity, the queue will eventually fill up.
- Know the exact batch size, queue size, schedule delay, timeout, and backpressure policy of the SDK/exporter version you use.
- Retries need bounded timeouts/backoff; a timeout does not prove the collector missed the data, and retries can cause duplicate delivery.
- Shutdown requires a clear lifecycle owner and a flush budget aligned with graceful termination; do not flush indefinitely when the collector is unavailable.
- Metrics, traces, and logs have distinct export semantics; Prometheus scraping is not equivalent to OTel `BatchSpanProcessor`.
- Monitor queue occupancy, dropped records, export duration/failures, retries, and collector health to observe the telemetry pipeline.
- Sampling decides which spans are kept; async export decides how kept spans are delivered. Do not confuse the two causes when investigating missing traces.

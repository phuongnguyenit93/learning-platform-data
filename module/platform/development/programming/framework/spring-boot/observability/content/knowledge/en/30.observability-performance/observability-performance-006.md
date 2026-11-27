# Dropping Telemetry Under Overload

A Spring Boot service receives a sudden surge of requests. The application still processes business logic, yet the trace exporter sends data slowly because the Collector or backend is overloaded. The telemetry queue steadily fills up; if the application kept holding every span, log, and metric in memory, heap usage could climb, export threads could stall, and production requests could ultimately suffer. Controlled telemetry dropping is a protective mechanism: accepting partial observability data loss under overload to keep the application stable and preserve the highest-value signals.

The **Dropping Telemetry Under Overload** lesson belongs to the **Observability Performance** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; you will learn context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Principle:** Telemetry is supporting operational data; exporting telemetry must never become a mandatory synchronous dependency of business requests. Under overload, use bounded queues, timeouts, sampling, filtering, and deliberate prioritization. Monitor queue occupancy, export failures, and dropped records so you know where data is being lost. Never let a drop mechanism hide incidents by dropping the metrics that report lost telemetry.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a telemetry pipeline needs backpressure and drop mechanisms.
2. Identify bottlenecks from instrumentation to the backend exporter.
3. Distinguish sampling, filtering, rate limiting, and dropping.
4. Design bounded queues and timeouts to protect heap/threads.
5. Understand how batch span processors and the Collector handle full queues and slow exports.
6. Prioritize telemetry by operational value and cost.
7. Prevent the exporter or Collector from adding latency to business requests.
8. Monitor dropped spans, logs, metrics, and export failures.
9. Design graceful degradation and post-overload recovery.
10. Test the pipeline when the backend is slow, unreachable, or returning errors.

## 2. Why Can Telemetry Overload an Application?

Every request can produce multiple spans, log records, and measurements. When traffic grows, telemetry record volume grows accordingly. If data creation exceeds export throughput for long enough, a backlog accumulates.

~~~mermaid
flowchart LR
    A["Application instrumentation"] --> B["SDK / Micrometer buffers"]
    B --> C["Exporter workers"]
    C --> D["Collector receivers / processors"]
    D --> E["Backend"]
    B -. "queue full" .-> X["Drop / reject"]
    C -. "export timeout" .-> X
    D -. "memory pressure" .-> X
~~~

Example:
- 5,000 requests/second.
- Each request creates 4 spans.
- The SDK produces roughly 20,000 spans/second.
- The exporter/backend can only process 12,000 spans/second.

Backlog grows by roughly 8,000 spans per second until the queue fills. Increasing queue size only delays when it fills; it does not fix a sustained throughput deficit.

### 2.1 Common Bottlenecks

| Location | Symptom | Consequence |
|---|---|---|
| Instrumentation | Too many spans/attributes/events | Higher CPU and allocation |
| SDK queue | Queue occupancy rises continuously | Queue fills and drops |
| Export worker | High export latency/timeouts | Backlog fails to drain |
| Network | Packet loss, TLS/DNS/connect issues | Export retries/failures |
| Collector receiver | Ingest rate exceeds capacity | Refusals or backpressure |
| Collector processor | Batch/memory limiter hits threshold | Queueing, refusals, or drops |
| Backend | Ingest throttling, slow storage/index | Collector retries or rejections |

Investigate from source to backend; looking only at backend ingest rate can miss that the SDK already dropped spans before they ever reached the Collector.

## 3. Backpressure and Bounded Queues

Backpressure is how a system reacts when downstream falls behind upstream. For telemetry, options include:
- Blocking producers to wait for capacity.
- Rejecting or dropping records when the queue is full.
- Slowing telemetry generation via sampling/filtering.
- Scaling consumer/export capacity if resources allow.
- Buffering temporarily out-of-process if architecture and durability allow.

For a request-serving application, blocking business threads waiting on a telemetry exporter is usually dangerous. A bounded queue caps memory; when full, policy must decide which records are rejected or dropped.

~~~mermaid
flowchart TD
    A["New telemetry record"] --> B{"Queue has capacity?"}
    B -->|Yes| C["Enqueue"]
    C --> D["Export worker"]
    D --> E{"Export succeeds?"}
    E -->|Yes| F["Release record"]
    E -->|No| G["Retry within bounded policy"]
    G --> D
    B -->|No| H["Drop / reject / shed load"]
    G -->|Retry budget exhausted| H
~~~

Bounded queues cap memory usage. However, a larger queue also increases memory footprint and wait time before export. Pick capacity based on record size, burst duration, and achievable drain rate.

## 4. Sampling, Filtering, and Dropping Differ

| Mechanism | When decided? | Meaning |
|---|---|---|
| Sampling | When creating/evaluating a trace | Selects which traces are recorded/exported |
| Filtering | By rules on content/signal type | Excludes unnecessary telemetry |
| Rate limiting | Caps records within a time window | Controls ingest rate |
| Queue overflow drop | When buffer is full | Drops records due to lack of capacity |
| Export failure drop | After retry/timeout policy finishes | Drops records that could not be sent |
| Tail sampling | After the Collector receives the trace | Keeps/drops traces based on observed data |

Sampling proactively cuts volume before overload occurs. Queue overflow dropping is a last-resort reaction when producers still outpace consumers. Filtering removes data by policy; rate limiting controls rate. Tail sampling can retain error/slow traces better than head sampling, but the Collector must receive and process spans before deciding, so it still needs sufficient capacity and memory.

Do not treat every dropped span as sampling. Separate intentional sampling from loss due to full queues/export failures so dashboards accurately reflect telemetry quality.

## 5. OpenTelemetry BatchSpanProcessor

The OpenTelemetry SDK typically uses `BatchSpanProcessor` to collect ended spans and export them in batches instead of calling the exporter synchronously on every span.

Key settings typically include:
- max queue size: maximum spans held in the queue.
- max export batch size: maximum spans in one batch.
- schedule delay: wait interval before exporting a batch.
- exporter timeout: maximum duration for one export operation.

Property/environment variable names and defaults depend on the language SDK/version. For the Java agent or OpenTelemetry Java SDK, verify the official documentation for your exact distribution.

When the queue is full, `BatchSpanProcessor` does not hold new spans indefinitely; spans may be dropped and the SDK often exposes internal metrics/logs for dropped spans depending on version. This is why you must monitor internal SDK telemetry and verify queue settings.

### 5.1 Choosing Queue Size

Queue size must balance burst absorption and memory:
- Queue too small: short bursts immediately cause drops.
- Queue too large: heap usage rises and export latency can stretch.
- Batch size too small: high export/network overhead.
- Batch size too large: payload/CPU/memory spikes; exporter may time out.
- Schedule delay too long: telemetry takes longer to appear in the backend.
- Timeout too long: worker stays tied up for too long when the backend is unresponsive.

There is no single right number for every service. Measure span size, traffic bursts, export throughput, and heap headroom before setting capacity.

## 6. Collector Queue, Retry, and Memory Limiter

The OpenTelemetry Collector can use a sending queue and retry policy in its exporter helper. The queue absorbs bursts and decouples receiver from exporter within capacity limits. Retries handle transient errors, but infinite retries or unbounded queues can drive memory pressure.

The memory limiter processor can reject data when the Collector nears its memory threshold to protect the process. The batch processor groups records into batches for efficient export. Processor ordering and pipelines must match your Collector distribution/version.

Conceptual configuration example:

~~~yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    send_batch_size: 1024
    timeout: 5s

exporters:
  otlp:
    endpoint: telemetry-backend:4317
    sending_queue:
      enabled: true
      queue_size: 5000
    retry_on_failure:
      enabled: true
      max_elapsed_time: 120s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

This is an illustrative configuration, not a complete production config. Verify exporter helper schema, queue storage, retry defaults, processor order, and memory units for your Collector version. In-memory queues can lose data on Collector restarts; persistent queues require a storage extension and assessment of durability/disk pressure.

### 6.1 Retries Do Not Provide Absolute Durability

Retries only help when errors are transient and capacity remains. If the backend keeps rejecting or queues fill up, records can still eventually be dropped. A persistent queue can survive restarts, yet does not guarantee exactly-once delivery; duplicates or replays must be handled according to backend semantics.

## 7. Prioritizing Telemetry Under Overload

Not every record holds equal value during an incident. You can define a policy:
- Keep error traces and slow traces with appropriate sampling.
- Keep aggregated metrics for availability, latency, saturation, and dropped telemetry.
- Keep scrubbed warning/error logs.
- Reduce high-volume debug/info logs.
- Drop spans for health checks/noisy operations if policy allows.
- Strip attributes/events that do not aid investigation.
- Limit payload capture and duplicate stack traces.

Prioritization must occur upstream of the bottleneck. Once the SDK queue is full, Collector tail sampling cannot rescue spans that never left the process. Head sampling in the SDK reduces load early; tail sampling requires a Collector with enough capacity to ingest traces.

### 7.1 Never Drop Telemetry-Loss Metrics

If an overload policy drops spans, you still need metrics for:
- Dropped spans/records.
- Export failures and timeouts.
- Queue size/occupancy.
- Collector refused records.
- Export batch duration.
- Backend throttling/rejection.

If metrics telemetry is also dropping at the same time, rely on out-of-band signals such as process logs, Collector self-telemetry, health endpoints, host metrics, or alerts from queues/backends.

## 8. Keeping Business Requests Independent of the Exporter

The exporter should operate on a worker/background path with a bounded queue. Request threads should only create/close an Observation or enqueue a record at low cost, never waiting on synchronous network export.

Principles:
1. Use an appropriate asynchronous/batch exporter integration.
2. Bound queue size and export timeouts.
3. Never retry on request threads.
4. Never call a remote telemetry backend synchronously/blockingly from an Observation handler.
5. Never let an exporter exception fail a business transaction.
6. Isolate telemetry thread pools from request-handling pools if the integration supports it.
7. Configure shutdown flush with a finite timeout so shutdown never hangs indefinitely.

Some instrumentation still incurs CPU/allocation cost directly on application threads; profile and trim attributes/events if overhead is large. "Async export" does not mean instrumentation is free.

## 9. Drop Policies and Signal-Specific Behavior

Metrics, traces, and logs have different semantics:
- Metrics are typically aggregations; losing measurements can skew counters/rates if loss goes unnoticed. Registries/exporters differ in temporality and cumulative/delta behavior.
- Traces are per-request records; dropping a span can leave gaps in a trace, or drop the entire trace if sampling/queue drops occur.
- Logs are event records; drops can lose specific incident evidence.

Therefore, do not apply one policy across all signals. For example:
- Keep service-level RED metrics (rate, errors, duration) on a prioritized capacity pipeline.
- Sample traces by error/latency and traffic budget.
- Rate-limit repetitive logs and retain error logs with deduplication.
- Avoid capturing every request body or debug payload.
- Measure dropped counts separately per signal.

If the backend or Collector maintains per-signal queues, set budgets and alerts per queue. A trace overload does not necessarily mean the metrics pipeline is overloaded too.

## 10. Adaptive Sampling and Overload Controls

Adaptive sampling adjusts sampling probability based on traffic/throughput budgets. For instance, as traffic rises, lower the rate for normal traces while retaining more error/slow traces if tail sampling is available.

Proceed carefully:
- Sampling policies must stay consistent so trace context does not break across services.
- Parent-based sampling helps downstream services honor upstream trace decisions in supported propagation setups.
- Tail sampling requires memory/decision wait windows and trace-ID-aware routing.
- Under Collector overload, a tail sampling processor can become the bottleneck itself.
- Ensure policy never accidentally drops all traces for an important tenant/route.
- Never use PII as a sampling key or priority attribute.

Adaptive controls need min/max sampling bounds and sampling-rate monitoring. Do not react too fast and cause oscillation or hard-to-interpret shifts in data distribution.

## 11. Cardinality and Payload Size Also Cause Overload

Span count is not the only source of pressure. Individual records can grow large due to:
- Many span attributes/events/links.
- Long exception stack traces.
- HTTP headers/body capture.
- SQL statements and bind values.
- Log messages containing serialized objects.
- Unnecessarily repeated resource attributes.

Shrink payloads:
- Record only attributes with investigative value.
- Use route templates and bounded tags.
- Do not capture request/response bodies by default.
- Truncate or scrub exception details.
- Cap log message size.
- Do not serialize large object graphs into spans/logs.
- Use events/aggregated metrics instead of many spans per internal step when appropriate.

Large payload sizes raise memory, network bandwidth, Collector CPU, and backend indexing costs. Also control PII and cardinality so an operational problem does not turn into a privacy incident.

## 12. Graceful Degradation and Recovery

When the telemetry backend is unavailable:
- The application continues serving business traffic while business dependencies are healthy.
- The exporter queue grows up to its limit and then applies its drop policy.
- Exporter timeouts/retries stay within budget.
- Alerts fire on dropped telemetry and backend unavailability.
- When the backend recovers, the queue drains at a bounded rate.
- Avoid letting a recovery burst overload the backend a second time.

If using a persistent queue, monitor disk usage, queue age, and replay throughput. During replay, the backend may receive old data at high speed; cap the drain rate.

Shutdown:
- Invoke flush/shutdown per integration lifecycle.
- Set a finite timeout.
- Do not block process shutdown indefinitely trying to export the entire backlog.
- Record remaining/dropped records if supported by the SDK.

## 13. Metrics for Observing the Telemetry Pipeline

Useful signals to monitor:

| Metric/Signal | Question |
|---|---|
| SDK queue size/capacity | How full is the buffer? |
| SDK dropped spans | How many spans were dropped before export? |
| Exporter failures | How many exports failed? |
| Export duration | Is export latency climbing? |
| Collector refused records | Are receivers/processors rejecting telemetry? |
| Collector queue size | Is backlog building in the Collector? |
| Collector memory usage | Is the memory limiter nearing its threshold? |
| Backend throttling | Is the backend rate-limiting/rejecting ingest? |
| Application latency | Is telemetry overload impacting requests? |
| Signal volume | Records/second across traces, metrics, and logs? |

Exact metric names depend on the SDK, Collector version, and exporter. Never hardcode names from examples without confirming actual metrics. Use Collector self-telemetry and appropriate SDK instrumentation.

## 14. Testing Overload and Drop Behavior

Do not wait for a production outage to discover your queue policy. Create a test/staging experiment:
1. Use a mock exporter or Collector backend simulating slow responses.
2. Ramp telemetry production rate in a controlled way.
3. Make export latency exceed the ingest rate.
4. Confirm queue occupancy grows without exceeding capacity.
5. Confirm dropped counters rise when the queue is full.
6. Confirm business request latency/error rate does not spike abnormally.
7. Confirm exporter timeouts/retries terminate within budget.
8. Restore the backend and verify steady queue draining.
9. Verify shutdown flush does not block indefinitely.
10. Repeat separately for traces, metrics, and logs.

### 14.1 Fault Injection

You can simulate:
- Network latency/packet loss to the Collector.
- Collector process restarts.
- Backend returning 429/503.
- Unresolvable export endpoints.
- Full disk with a persistent queue.
- Triggering the memory limiter.
- Traffic bursts and oversized span payloads.

Run these in a scoped test environment with clear rollback/stop conditions, and never generate uncontrolled load against production.

## 15. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| SDK dropped spans rising | Batch queue full or slow exporter | Check queue/export duration; lower sampling/volume or increase drain capacity |
| App latency rises alongside exporter errors | Blocking export or thread contention | Check synchronous exporter paths and isolate workers |
| Collector memory grows continuously | Ingest > export, large queue, or large payloads | Bounded queue, memory limiter, reduce payload/rate |
| Collector refused records rising | Memory limiter or receiver overload | Inspect self-telemetry, capacity, and pipeline |
| Backend receives fewer spans than SDK creates | Drops in SDK/network/Collector/backend | Compare counters at every boundary |
| Retry queue does not drain | Backend still throttling or drain rate too high | Bound retries/backoff and replay rate |
| Traces missing child spans | Head/tail sampling, SDK queue drops, or propagation issue | Check sampling decisions and dropped counters |
| Metrics look fine while logs are missing | Different per-signal pipelines | Inspect logs queue/exporter separately |
| Shutdown takes too long | Flush waiting on backend or huge backlog | Bound flush timeout |
| Queue grows after a deploy | Higher instrumentation volume/attribute size | Compare spans per request, events, and payload size |
| Abnormal cardinality spike | Dynamic tag values creating large series/records | Allowlist and normalize dimensions |
| Drops with no alerts | Self-telemetry not exported or missing dashboard | Build alerts from SDK/Collector drop metrics and out-of-band signals |

## 16. Playbook: Slow Telemetry Backend During Peak Hours

**Scenario:** Collector export timeouts rise, SDK dropped spans appear, and request latency starts creeping up.

1. Compare application request rate with spans/log records generated per second.
2. Check SDK queue occupancy, dropped spans, and export duration.
3. Check Collector receiver rate, refused records, memory, and exporter queue.
4. Pinpoint whether the bottleneck is the application SDK, network, Collector processor, or backend ingest.
5. Deliberately reduce telemetry volume: sample normal traces, filter noisy health checks, and cut verbose logs.
6. Retain error/slow traces and availability/latency/dropped-telemetry metrics per policy.
7. Verify the exporter runs in the background without blocking request threads.
8. Tune queue/batch/timeout based on memory headroom and measured throughput.
9. When the backend recovers, drain the backlog at a bounded rate.
10. Monitor drop rate, queue age, and application SLOs post-recovery.

Do not just raise queue size during prolonged backend slowness. Increase capacity or lower input rate; a larger queue only holds more data in memory.

## 17. Self-Check Exercises

**Exercise 1 — Queue math.** The SDK produces 20,000 spans/s, and the exporter ships 12,000 spans/s. By how many spans per second does the queue grow? Why does enlarging the queue only delay drops?

**Exercise 2 — Sampling vs. drop.** Distinguish a trace dropped by head sampling from a span dropped because the `BatchSpanProcessor` queue is full. Which metrics tell you?

**Exercise 3 — Backpressure.** Why should you avoid blocking request threads to wait for a telemetry exporter in a synchronous API system?

**Exercise 4 — Collector.** What roles do the memory limiter, batch processor, and exporter sending queue play? Why must they be configured for your exact version?

**Exercise 5 — Tail sampling.** Why can't tail sampling rescue a span already dropped in the SDK before reaching the Collector?

**Exercise 6 — Signal policy.** Why should traces, metrics, and logs have distinct drop/retention policies?

**Exercise 7 — Recovery.** What issue can happen if a persistent queue drains too rapidly after backend recovery?

**Exercise 8 — Self-observability.** If metrics telemetry itself is being dropped, how can you detect that the pipeline is losing data?

### Suggested Answers

1. It grows by 8,000 spans/s. The queue fills after a finite time; increasing capacity only lengthens the time before overflow.
2. Head sampling is an intentional pre-export policy decision; queue drop is capacity loss. Track sampling decisions/rates and SDK dropped spans.
3. A slow exporter/network will tie up business threads, raise latency, and cause cascading failures.
4. Memory limiter protects the Collector, batching improves export efficiency, and the sending queue absorbs bursts/retries. Schemas/defaults vary by Collector distribution/version.
5. The Collector never received the span, so it has no data for tail sampling to retain.
6. Metrics aggregate for SLOs, traces follow requests, and logs are event records; the value and cost of losing each differ.
7. The backend can get hit by an ingest burst/throttling again; cap the replay/drain rate.
8. Use Collector self-telemetry, process logs, health endpoints, host metrics, or independent external monitoring.

## 18. Official References

- [OpenTelemetry — Batch Span Processor](https://opentelemetry.io/docs/specs/otel/trace/sdk/#batching-processor): batching, queue, and export behavior.
- [OpenTelemetry Java — Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/): Java agent properties, batch processor, and exporter settings.
- [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/): queues, retries, and memory management.
- [OpenTelemetry Collector — Memory Limiter](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor): memory pressure and refusal behavior.
- [OpenTelemetry Collector — Batch Processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor): batching records.
- [OpenTelemetry Collector — Exporter Helper](https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper): sending queues, retries, and timeout configuration.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling concepts.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation handlers and instrumentation lifecycle.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing configuration, sampling, and exporter integration.

**Key takeaway:** A telemetry pipeline must have bounded capacity and be isolated from the request path. When input exceeds export throughput, queues will fill; sampling/filtering trims input intentionally, whereas drops reflect capacity or export failure loss. Monitor dropped records, queue occupancy, export latency, and Collector self-telemetry. Prioritize signals by investigative value, bound payloads and retries, and test overload/recovery to prove a slow telemetry backend will never disrupt business operations.

# Exporter Step and Batch: Metric Export Cadence and Data Grouping in Spring Boot

> **Chapter:** Meter registry and exporter  
> **Lesson:** Exporter step and batch  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. The Problem: Metrics Incremented, Yet the Backend Shows Nothing Immediately

Suppose `order-service` increments a `Counter` on every incoming order-creation request. Application logs show 100 requests processed successfully, yet the metrics dashboard updates in periodic waves, lagging by tens of seconds. Another rollout causes outbound OTLP request volume, exporter CPU, and network traffic to jump sharply. Why?

In an observability pipeline, **the moment an application records a measurement** and **the moment the monitoring backend receives it** are two different points in time:

- `MeterRegistry` updates meter state immediately when code calls `Counter.increment()`, `Timer.record(...)`, or when a `Gauge` is sampled.
- With a **step/push registry**, data is typically prepared and exported on a scheduled `step` interval rather than firing an HTTP request on every `increment()`.
- A single export payload can contain **many metrics/data points**. At an intermediate hop like the OpenTelemetry Collector, a `batch` processor can further group incoming telemetry by size or timeout before forwarding.
- With **Prometheus pull**, Prometheus itself scrapes the endpoint on a `scrape_interval`; this mechanism is distinct from a push registry's `step`.

Therefore, separate two questions:

1. **Exporter step:** how often does the application prepare and send a batch of metrics?
2. **Batch:** which datapoints are grouped together in each transport wave, when are they forwarded, and where are the resource bounds?

**Goal:** understand both layers, configure Spring Boot and OTLP/Prometheus properly, estimate latency vs. cost, monitor export failures, and avoid confusing batching with business event counts or trace sampling.

## 2. From Instrument Call to Dashboard Data

Foundational terms:

| Concept | Explanation | Example |
| --- | --- | --- |
| **Meter** | A Counter, Timer, Gauge, DistributionSummary, LongTaskTimer, etc. with name and tags | `orders.processing.duration{outcome="success"}` |
| **Measurement** | A quantity read from a meter | Count, total time, gauge value |
| **Data point** | A value/stat record with attributes, timestamp, and data type placed into a payload or backend | Count for `outcome=error` in an export window |
| **Step** | Time interval used to aggregate and/or export metrics in a step-style registry | 30 seconds |
| **Publish/export** | An event where the registry sends a payload to a backend/collector | Sending an OTLP HTTP request |
| **Batch** | A group of data points/records transported or processed together | Collector flushing at a size threshold or timeout |
| **Scrape interval** | Interval at which a collector pulls from a pull endpoint | Prometheus scraping every 15 seconds |
| **Temporality** | Whether a metric represents incremental deltas or cumulative totals | Delta vs. cumulative |
| **Retention** | How long the backend keeps ingested data | Governed by monitoring system policy |

~~~mermaid
flowchart LR
    A["Request / batch job"] --> B["Micrometer Counter, Timer, Gauge"]
    B --> C["MeterRegistry"]
    C --> D{"Metric export model"}
    D -->|"Push/step"| E["Close step interval + publish"]
    D -->|"Pull"| F["Endpoint /actuator/prometheus"]
    E --> G["OTLP / vendor backend"]
    G --> H["Collector batch if present"]
    H --> I["Backend stores metrics"]
    F --> J["Prometheus scrape interval"]
    J --> I
    I --> K["Dashboards / alerts"]
~~~

This diagram only shows **common paths**. Not every `MeterRegistry` shares identical publish logic; not every push exporter uses the same wire format or supports configuring batch size; and not every architecture includes a Collector.

**Key point:** even though code creates and updates meters immediately, dashboard viewers must wait for the registry, network, collector, backend, and query refresh cycle to complete. That lag does not mean instrumentation failed.

## 3. What Does `step` Mean in Micrometer?

Micrometer provides a family of step registries, typically via `StepMeterRegistry` and its implementations. `StepMeterRegistry` uses the configured export interval to schedule publishes. Other registry backends may operate on a different model.

Example configuration:

~~~yaml
management:
  otlp:
    metrics:
      export:
        step: 30s
~~~

In a Spring Boot 3.x app with a matching OTLP registry, this asks for OTLP metrics to publish roughly every **30 seconds**. Default `step` values vary by registry type, version, and configuration. Never assume every backend defaults to 1 minute or aggregates every metric identically.

### 3.1. Lifecycle of a 30-Second Step

Suppose a registry ships data periodically, and a Counter receives events throughout the intervals:

~~~text
Time             00:00             00:30             01:00
                 |-----------------|-----------------|
Application      + + + + + + + +   + + + + + + ...
Step             period A          period B
Publish                               ^                 ^
Backend receives                   after mark A      after mark B
~~~

If an event occurs at `00:12`, you may not see new data in the backend until period A is published, transmitted, processed, and stored. If an event occurs at `00:31`, it belongs to the next period under the step registry's bookkeeping, so the backend sees it later.

These timestamps are **illustrative**, not a guarantee that clocks align strictly to `:00` and `:30`. Schedulers, publish execution time, network latency, GC pauses, and registry versions can shift exact timestamps.

### 3.2. Step Does Not Mean "The App Only Measures Every 30 Seconds"

This is a frequent misconception. On `Counter.increment()`, meter state updates right when the event occurs. Step primarily governs the **rollover/read window** and **transmission schedule** of a step-style registry. Business code never needs to buffer counts manually for 30 seconds before calling `increment()`.

Likewise, `Timer.record(...)` records duration into the meter as soon as the operation completes; the exporter later snapshots those statistics periodically. Step does not turn a Timer into a per-call event log—metrics remain **aggregated** data.

### 3.3. Why Does `step` Matter for Counters and Timers?

In many step-based registries, Counters and Timers maintain statistics aligned to each step window, such as count and total duration in that window. However, **what gets sent to the backend still depends on the registry and protocol**. Some backends expect rates; others use delta or cumulative temporality and compute rates themselves.

Never conclude from `step=30s` alone that backend Counter values are "always cumulative totals since app startup," nor assume they are "events per second." Check your exporter's temporality/units and your specific backend's conventions.

## 4. Step, Reporting Latency, and Data Freshness

Lag between a business event and its visibility on a dashboard has multiple layers:

~~~text
Event recorded
  -> wait for end of step (if push/step registry)
  -> publish / serialize / network
  -> received by Collector (if used)
  -> wait in Collector batch or queue
  -> exported to backend
  -> backend ingests/indexes
  -> query cycle or dashboard refresh
~~~

You can approximate this conceptually:

~~~text
visibility_delay ≈ wait_to_next_step
                 + publish_duration
                 + network_delay
                 + collector_queue_and_batch_delay
                 + backend_ingest_delay
                 + dashboard_refresh_delay
~~~

This is an **analytical model**, not an exact prediction formula or guaranteed SLA. Under failures, full queues, retries, backend congestion, or process termination, delay can far exceed `step`, or data may fail to arrive altogether.

| Situation | Implication of `step` |
| --- | --- |
| Event occurred right after a publish tick | May wait nearly a full step until the next publish |
| Publish slowed by network | Configured interval does not guarantee on-time backend delivery |
| Pod stopped before next publish | Unpublished measurements risk loss depending on registry close/retry behavior |
| Backend refreshes every minute | Even if exporter pushes every 15s, users may only see updates on dashboard refresh |
| Prometheus scrapes every 15s | That is a **pull** schedule, not `StepMeterRegistry`'s push schedule |

### Choosing `step` from Operational Requirements

If an alert must detect incidents within ~1 minute, a 5-minute step is too coarse. If you only care about hourly batch summaries, pushing every 5 seconds creates unnecessary traffic. Setting an ultra-short step **does not automatically** improve accuracy: it increases overhead, network chatter, and backend ingestion load, especially with high cardinality or histograms.

## 5. What Is Batching and Which Layers Perform It?

The word "batch" can refer to different behaviors. Always clarify **where batching happens**.

| Layer | What Batching Usually Means | Depends on `step`? |
| --- | --- | --- |
| Business code | Processing multiple records or messages in one job | Not necessarily |
| MeterRegistry / exporter | Packing multiple meters/data points into one or more export payloads | Can occur during a step publish |
| HTTP/gRPC transport | One request carrying multiple data points | Depends on client/protocol |
| OpenTelemetry Collector `batch` processor | Grouping telemetry records/data points before forwarding to the next exporter | Controlled by its own timeout/size thresholds, not Micrometer's step |
| Backend ingest | Grouping, compressing, or organizing incoming writes for storage | Depends on backend |

**Batching does not mean "wait for 100 orders before incrementing the Counter."** Aggregated metrics record into the meter as the app runs; transport or a collector may group multiple data points together to reduce request overhead.

A single batch can contain hundreds of metric names and tag combinations—it does not represent one metric per event. Conversely, a Timer with a histogram can emit multiple data points for a single metric name and tag set.

### 5.1. Two Common Batch Limits

- **Size threshold:** once enough records/data points accumulate, the batcher flushes. In the Collector, exact counting semantics depend on the signal and processor version.
- **Timeout:** if the threshold is not met after waiting a configured duration, the batcher flushes whatever it holds to bound latency.

In most systems, larger batches cut request counts at the expense of higher latency and memory footprint; smaller batches deliver faster with higher transport overhead. No single batch size fits all traffic profiles and backends.

## 6. OTLP Push: Spring Boot Publishing Metrics by Step

A common setup uses Spring Boot with the Micrometer OTLP registry pushing metrics to an OpenTelemetry Collector over OTLP/HTTP.

### 6.1. Maven Dependencies

With Spring Boot 3.x using parent/BOM version management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` provides metrics/management; `micrometer-registry-otlp` provides the OTLP metrics-exporting registry. Never instantiate a separate `MeterRegistry` inside a service, as it will bypass Spring Boot's managed configuration and exporter.

### 6.2. Illustrative `application.yml`

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 30s
  metrics:
    tags:
      application: order-service
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Explanation:

- `management.otlp.metrics.export.url` is the OTLP metrics destination; `/v1/metrics` is the standard OTLP/HTTP metrics receiver path.
- `management.otlp.metrics.export.step` sets the publish cadence for this registry.
- `application=order-service` is a useful bounded label for filtering metrics by service.
- `/actuator/metrics` is an internal inspection endpoint. **Having metrics in Actuator does not prove OTLP export succeeded.**
- A containerized app cannot use `localhost:4318` to reach a Collector in another container. `localhost` refers to **the app's own network namespace/container**; use the deployment's service/host address.

**Version scope:** this example uses Spring Boot 3.x properties. On other Spring Boot versions or older registries, check configuration metadata and documentation for your version. Do not mechanically translate old Boot `management.metrics.export.*` keys without checking.

### 6.3. Changing `step` Does Not Change Business HTTP Request Rate

If an app handles 1,000 requests/second with a 30-second step, each event still updates the Counter/Timer right when code runs. The registry may send a payload containing aggregated stats at the end of each period; it does **not** open 30,000 HTTP connections or send 30,000 OTLP requests in 30 seconds.

Actual payload counts depend on meter counts, labels, histograms, exporter limits, encoding, and any batch splitting. With retries, HTTP requests can exceed the periodic publish count.

## 7. Java Example: Recording Business Metrics Before the Exporter Acts

To clarify boundaries, use a service accepting `MeterRegistry` via constructor injection. The service knows nothing about OTLP URLs or `step`.

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {
    private final MeterRegistry meterRegistry;

    public OrderProcessingService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void processOrder(String incomingChannel, Runnable operation) {
        String channel = normalizeChannel(incomingChannel);
        String outcome = "success";
        Timer.Sample sample = Timer.start(meterRegistry);

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            Timer duration = Timer.builder("orders.processing.duration")
                .description("Duration of completed order attempts")
                .tag("channel", channel)
                .tag("outcome", outcome)
                .register(meterRegistry);

            sample.stop(duration);
        }
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("partner".equals(value)) return "partner";
        return "other";
    }
}
~~~

On a call to `processOrder(...)`:

1. `Timer.Sample` starts timing the synchronous operation.
2. When work finishes or throws, `sample.stop(duration)` records **one duration sample** into the registry.
3. `channel` and `outcome` are low-cardinality tags. Never add `orderId` or `requestId` as metric labels.
4. The target registry determines how count, sum, and histograms (if enabled) are represented and when the exporter publishes. **The service never sends OTLP directly.**
5. If a code path is already instrumented with `@Observed` or equivalent, do not add a manual Timer with the same meaning—otherwise you will double-count.

If `operation.run()` only *submits* an async task and returns, this Timer measures submission time rather than completion time. Align timing boundaries with actual completion or use async-aware instruments.

### 7.1. Relationship to `ObservationRegistry`

Code can also use `ObservationRegistry`:

~~~java
Observation.createNotStarted("orders.processing", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> doBusinessWork());
~~~

When Spring Boot registers a Meter `ObservationHandler`, Observation creates the corresponding meter; if a tracing handler is active, it also creates a span. **Do not manually record a Timer around the same boundary** if Observation already provides the intended metric. Exporter step/batch processing happens **after** meter recording, regardless of whether the meter came from the direct API or an Observation handler.

## 8. OpenTelemetry Collector Batch Processor: Grouping After OTLP Receipt

A common deployment topology:

~~~mermaid
flowchart LR
    A["Spring Boot + Micrometer OTLP"] -->|"step 30s, OTLP/HTTP"| B["OTLP receiver"]
    B --> C["Collector batch processor"]
    C -->|"size trigger / timeout 5s"| D["Collector exporter"]
    D --> E["Metrics backend"]
    E --> F["Dashboards and alerts"]
~~~

The Collector batch processor **does not change Micrometer's step**. It receives data already exported by the app, then decides when to forward batches downstream.

### 8.1. Example `collector-config.yaml` for a Learning Environment

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024
    send_batch_max_size: 2048

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

**This example uses the `debug` exporter** to inspect data in Collector logs while learning—not a production setup shipping metrics to long-term storage. Your Collector distribution/version must include the listed receiver, processor, and exporter.

Meaning:

- `receivers.otlp.protocols.http` receives OTLP/HTTP payloads, commonly on port `4318`.
- `batch.timeout=5s` ensures batches flush after waiting even if the size threshold is not reached.
- `send_batch_size=1024` is a **trigger threshold**, not a promise that every batch contains exactly 1,024 units.
- `send_batch_max_size=2048` caps maximum batch size where supported by the processor version; exact unit counts depend on signal type (spans, metric data points, or log records).
- `exporters.debug` prints telemetry to Collector logs for verification, which can produce massive log volume and expose metadata—use only in controlled test environments.
- `endpoint=0.0.0.0:4318` listens on container/host interfaces; enforce network restrictions and auth/TLS in real deployments. Never expose a debug exporter or unprotected Collector to the internet.

### 8.2. Timeline Example When Step and Batch Differ

Suppose Micrometer publishes around `00:30`. The Collector receives it shortly after without hitting the size threshold; a 5-second batch timeout can forward it around `00:35`. With a single request or small burst, the Collector does not wait forever for 1,024 data points because timeout flushes it.

Conversely, if dozens of instances publish together and exceed the threshold, the batch can flush early. **Combining 30s + 5s does not mean the backend always sees data in exactly 35 seconds.** Network lag, scheduling, queues, retries, rate limits, and backend ingestion all add variance.

### 8.3. Batching Is Not a Durable Queue

The batch processor optimizes grouping and throughput. It **does not provide durable persistence** if the Collector or exporter crashes before sending. For higher reliability, some exporters and Collector deployments support sending queues or persistent storage when explicitly configured—verify per actual component/version and test under failure.

If the backend misses data, never assume "the Collector will safely hold every metric until the network comes back." Check logs, self-telemetry, queue capacity, retry policies, and drop counts.

## 9. Prometheus Pull: Scrape Interval Is Not Exporter Step

With **`PrometheusMeterRegistry`**, the application normally **does not push** metrics to Prometheus every 30 seconds. Prometheus pulls data from `/actuator/prometheus` on the Prometheus server's `scrape_interval`.

### 9.1. Spring Boot Configuring a Pull Endpoint

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

### 9.2. Illustrative Prometheus Scrape Config

~~~yaml
scrape_configs:
  - job_name: order-service
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["order-service:8080"]
~~~

In this example, **Prometheus** initiates endpoint requests roughly every 15 seconds. This config belongs to Prometheus, **not Spring Boot's `application.yml`**. In Kubernetes, targets typically come from service discovery or monitoring operators rather than a static list.

| Question | Step-Based OTLP Push Registry | Prometheus Pull |
| --- | --- | --- |
| Who initiates the transfer? | Application/registry when publish interval arrives | Prometheus server when scrape interval arrives |
| Where is cadence configured? | Exporter `step` property in Spring Boot/registry | `scrape_interval` in Prometheus |
| Application endpoint | Sends outbound to OTLP receiver | Exposes `/actuator/prometheus` |
| Batching mechanism | App payload and optional Collector batch downstream | HTTP response holds many series per scrape; backend processes it |
| How to change cadence? | Adjust `step` and exporter capacity | Adjust `scrape_interval` and target/backend capacity |
| Common mistake | Thinking every event pushes immediately | Thinking OTLP `step` changes Prometheus scrape interval |

**Do not set `management.otlp.metrics.export.step` expecting it to control Prometheus scrape frequency.** They are separate pipelines; an app can enable both registries, exporting measurements to two places via their respective mechanisms.

## 10. Temporality: Step Does Not Guarantee One Fixed Counter Format

When reading metrics from OTLP or another backend, clarify whether a Counter represents **delta** or **cumulative** values.

| Type | Meaning | Example |
| --- | --- | --- |
| **Delta** | Value accrued during the described measurement interval | 120 orders in a 30-second window |
| **Cumulative** | Running total since a start timestamp | 5,320 total orders since process start |
| **Gauge** | Value at read time | 32 jobs currently pending |
| **Timer histogram/distribution** | Multiple duration stats/buckets | Count, sum, latency buckets |

A step-style registry may aggregate over windows, yet **the temporality encoded in OTLP and backend semantics depend on implementation and version**, so never deduce them from the `step` property alone.

### 10.1. Implications for Calculating Rates

If a backend stores cumulative Counters, rates can be computed from increases over time while accounting for restarts/resets. In Prometheus, you commonly query:

~~~promql
sum(
  rate(orders_processing_duration_seconds_count[5m])
)
~~~

This works only when the Timer is exported to Prometheus under that matching series name. On a backend ingesting delta OTLP, rate interpolation differs; some backends convert or compute directly from incoming deltas. **Never take a step value and arbitrarily divide twice by seconds**, because the backend may already express a rate or perform its own conversion.

### 10.2. When a Process Restarts

If a cumulative metric resets on process restart and you compare two raw points, the value can drop—that does not mean negative orders. Some backends track start times/temporality to handle resets. With step/delta, losing a publish can drop part of the total event count depending on the exporter and retry policy.

**Lesson:** to debug strange values, check signal type, units, timestamps, temporality, process restarts, and backend aggregation—not just the `Counter` name.

## 11. Choosing Step and Batch Based on Latency, Cost, and Series Count

No single `step` is ideal for every service. Weigh incident detection time, data point volume, CPU, bandwidth, and backend ingest capacity.

| Illustrative Setting | Benefit | Cost / Risk |
| --- | --- | --- |
| Step 10s | Faster push updates under normal conditions | More publishes, payload volume, transport overhead |
| Step 30s | Balanced freshness and overhead for many services | Sub-minute alerts may see slight lag |
| Step 60s | Fewer publishes | Harder to spot quick spikes, higher display lag |
| Step 5m | Fits low-urgency indicators | Slow detection, misses short bursts |
| Small Collector batch | Forwards data faster | More outbound requests from Collector |
| Large Collector batch | Can cut transport overhead | Higher memory and latency; monitor queues/failures |

These values are **starting points for discussion**; measure in practice. For example, if 10 instances with 5,000 series emit one data point per 30-second step:

~~~text
Publishes per instance per day:
  86,400 / 30 = 2,880

Data points/day (assuming one data point per series per period):
  10 × 5,000 × 2,880 = 144,000,000
~~~

This estimate relies on simplifying assumptions—it is **not** the exact data point count of any Micrometer exporter: Timers can emit multiple stats/buckets, idle series may be skipped, and backends may add metadata or enforce limits. The point is seeing how **cardinality × publish frequency** drives operational scale.

### Simple Cost Estimation Formula

~~~text
publishes_per_day ≈ 86,400 / step_seconds

data_points_per_day ≈ active_series_or_points_per_publish
                    × publishes_per_day
                    × number_of_instances

network_bytes_per_day ≈ average_bytes_per_publish
                      × publishes_per_day
                      × number_of_instances
~~~

Increasing `step` from 30s to 60s with comparable points per payload roughly halves publish calls, while business event counts stay identical. Changing frequency alters dashboard freshness, resolution, and failure sensitivity, so do not adjust it solely to save bandwidth.

## 12. How Do Cardinality and Histograms Affect Batching?

A single `Counter` has one metric name but many tag combinations, each potentially producing a distinct series/data point. Example:

| Tag | Value Count |
| --- | ---: |
| `channel`: web/mobile/partner/other | 4 |
| `outcome`: success/rejected/error | 3 |
| `region`: north/central/south | 3 |
| `instance` (scrape target or resource label) | 8 |

Maximum combinations when all occur: **4 × 3 × 3 × 8 = 288**. Adding a latency histogram with 20 buckets per combination (when enabled and bucketed that way) multiplies series/data volume sharply. Using `@Timed` or Observation does not make this disappear; cardinality comes from **tag value sets and instrument types**.

**Never put** `requestId`, `orderId`, email, exception message, URL containing IDs, or free-form payloads into metric tags. If every request generates a new tag combination, batches can balloon even with low request rates per step because the registry retains registered meters over the app's lifetime.

When you need to trace a specific transaction:

- Use low-cardinality metrics to locate time windows and hotspots.
- Use tracing with controlled high-cardinality span attributes to inspect call paths and errors.
- Use logs with `traceId`/`spanId` when logging correlation is configured.
- Remember that trace sampling and metric `step` are **unrelated concepts**: lowering trace sampling does not reduce metric data points.

**Optimize first by:** eliminating unnecessary cardinality, restricting histograms to where SLOs require them, and pruning purposeless metrics. Increasing `batch-size` only trims transport requests at certain hops; it cannot cure time-series explosion.

## 13. When the Exporter or Collector Fails

A metrics pipeline can fail in distinct ways:

| Scenario | Possible Consequence | What to Inspect |
| --- | --- | --- |
| Wrong OTLP URL or Collector not listening | App records meters locally but fails to ship to Collector | URL/port/protocol config, error logs |
| Connection timeouts / flapping | Slow, failed, or retried publishes depending on implementation | Network latency, retry/backoff, exporter logs |
| Collector batch waiting for timeout | Legitimate added delay before backend receives data | `batch.timeout`, size triggers |
| Collector backend congested | Queue builds up, retries, or drops beyond limits | Collector self-telemetry, queue/retry policies |
| Pod stops before publish | Risk of losing unsent data | Registry shutdown behavior, termination grace period |
| Backend rejects excess series | Dropped/throttled ingest, missing dashboard data | Cardinality, quotas, error responses |
| Series and histograms surge | Huge payloads, slow publishes, or overloaded Collector | Meter/tag counts, histogram buckets, resource usage |
| Prometheus target down | Cannot scrape even while app stays up | Targets/`up`, networking, auth, endpoint |
| Prometheus scrape too sparse | Misses very brief gauge fluctuations | `scrape_interval`, match required resolution |
| Metrics normal, traces missing | Independent tracing exporter, sampling, or propagation | Trace pipeline, `traceparent`, Collector traces |

**Never assume success just because `/actuator/metrics` returns data.** That endpoint shows what the local registry holds; the OTLP exporter can still fail behind the scenes. Likewise, `/actuator/prometheus` returning text does not prove Prometheus is scraping successfully.

### Retries and Backpressure

Exporters may implement different retry/backoff strategies; Collector exporters can support sending queues or persistent storage when configured. Still, **there is no universal exactly-once delivery guarantee** for metrics pipelines.

If you need lossless transaction auditing, store events or records in a durable business database; metrics are for operational observability, not a replacement for transaction logs.

When increasing `batch size` or `step` to reduce load, weigh the impact on **time-to-detect** and potential data loss at shutdown. When shrinking `step` for faster alerts, monitor serialization overhead, memory, network, and Collector load.

## 14. How to Verify Each Stage of the Exporter

### 14.1. Check the In-App Registry

With Spring Boot Actuator:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/orders.processing.duration
~~~

Invoke `OrderProcessingService.processOrder(...)` with a test workload. If the metric is missing from Actuator, check code execution, registry wiring, `MeterFilter`, or instrumentation enablement. **It is not a step/batch bug** if the meter was never even created.

### 14.2. Check OTLP Publish

Use a test Collector receiving OTLP and printing debug logs. After running a workload, inspect:

- Does the app log connection errors to `http://localhost:4318/v1/metrics`?
- Does the Collector receive the expected metric names, tags, and datapoints?
- Does arrival cadence match the configured `step` under normal load?
- Does Collector batching flush downstream per timeout or size?
- Is the backend ingesting data, and are there timestamp gaps?

**Be careful:** because data is aggregated, one OTLP request does not equal one order; never compare OTLP HTTP request count to order attempt count. Inspect **datapoints and Counter/Timer statistics**, not transport request counts.

### 14.3. Check Prometheus Pull

When using the Prometheus registry:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Then check target status in Prometheus and the `up` metric or relevant self-metrics. If the endpoint returns data while `up=0`, the cause lies in Prometheus networking, path, or auth; tuning OTLP `step` will not fix it.

### 14.4. Verify Numeric Accuracy

In a quiet test environment with no background traffic, execute **100 successful operations** and compare the count delta across the registry and backend. Retries or shutdowns can alter counts; before calling it a bug, verify how many business executions actually occurred and whether the meter means "attempts" or "logical orders."

Use a small dataset, bounded tags, and a step short enough to observe publish cycles. Never intentionally congest a production Collector just to watch its queue operate.

## 15. Monitoring Exporter and Collector Health

A system rich in business metrics that **fails to monitor its own telemetry pipeline** cannot tell an application outage apart from an exporter outage.

Signals worth watching (exact metric names depend on version):

- **Export failure counts** and retry counts from the app/registry where emitted.
- **Publish duration** per cycle, especially when approaching or exceeding `step`.
- **Data point and byte counts** per export wave to catch cardinality spikes.
- **Queue size/capacity and dropped items** at the Collector when queueing is enabled.
- **Collector exporter latency and backend ingest status**.
- **Scrape target up/down, scrape duration, and sample counts** for Prometheus pull.
- **App/Collector CPU, memory, and GC** to catch serialization/batching overhead.

Never hardcode a guessed self-metric name into dashboards before checking your actual Collector distribution and configuration: names vary by version, exporter type, and self-telemetry settings. Inspect the Collector's self-telemetry endpoint or backend monitoring tools directly.

### Cross-Signal Investigation via Metrics, Logs, and Tracing

If dashboards lose metrics for 2 minutes, align that gap against exporter logs, Collector status, and application spans/traces. An app can still return HTTP 200 and emit trace spans while metrics export is broken, and vice versa.

Independent signal pipelines corroborate hypotheses, yet **never confuse trace sampling with metric sampling**. If you want exemplars linking a metric point to a trace, your stack must support and configure exemplars; never attach `traceId` as a tag across all series.

## 16. Real-World Scenario: Metrics Lag After Cutting Export Traffic

**Context.** `order-service` runs 12 instances. To reduce backend load, the team changes `management.otlp.metrics.export.step` from `15s` to `60s`. Meanwhile, the Collector has `batch.timeout=10s`. Afterward, the checkout dashboard updates less often, and error alerts become less sensitive to 20–30 second incidents.

**Analysis:**

1. Code still records Timers/Counters on every checkout. Changing `step` did not reduce instrumented checkouts.
2. Because publishing now happens roughly every 60 seconds, an event right after a publish may wait nearly a full minute for the next export, plus Collector batch/queue/backend time.
3. If the Collector receives a large enough payload, `send_batch_size` may flush early; otherwise, timeout adds wait time. **Collector batch timeout does not override the app-side step.**
4. Dashboard refresh and backend query evaluation add further lag.
5. If an instance restarts before the next publish, buffered data can be affected depending on exporter and shutdown behavior.

**Grounded solution:** define alert time-to-detect requirements first. For alerts needing sub-minute response, reduce `step` (e.g., 15–30s after load testing), tune Collector batching/queues, and size data point cost. Data requiring exact transaction auditability belongs in business storage, not pushed metrics.

**Verification:** send a workload with known counts and timestamps, then observe Actuator, Collector receipt time, backend ingestion time, and dashboard visibility. Measure the real end-to-end latency distribution rather than looking only at `step` in YAML.

## 17. Practice Exercises

### Exercise A — Understanding Timing Milestones

An app uses a 30-second exporter step, a 5-second Collector batch timeout, and a 15-second dashboard refresh. A Counter increments right after the most recent publish.

1. List the stages data must pass through before appearing on the dashboard.
2. Explain why you cannot guarantee it will appear in **exactly 50 seconds**.
3. If the Collector hits its batch size threshold before timeout, what changes?
4. If the network goes down for 3 minutes, which mechanisms must you check before claiming no data was lost?

### Exercise B — Configuring Two Pipelines

Write configurations for two separate test environments:

- **Push:** Spring Boot + `micrometer-registry-otlp`, Collector URL `http://localhost:4318/v1/metrics` and step `30s`; Collector has a batch processor with `timeout=5s`.
- **Pull:** Spring Boot + `micrometer-registry-prometheus` and `/actuator/prometheus`; Prometheus scrapes every `15s`.

Explain **why setting `management.otlp.metrics.export.step=10s` does not make Prometheus scrape faster**.

### Exercise C — Sizing Data Volume

With 6 instances, each emitting 2,000 data points per interval:

1. With a 30-second step, roughly how many publishes/instance/day occur?
2. Estimate cluster-wide data points/day if every interval emits 2,000 points.
3. If you add an `orderId` tag that is nearly unique per request, why can batch size or network load explode?
4. If you enable 30 histogram buckets on several Timers, estimate how data point volume grows without assuming all exporters use identical bucket formats.

**Answers to the first two questions:** 86,400 / 30 = **2,880 publishes/instance/day**; 6 × 2,000 × 2,880 = **34,560,000 data points/day** under the given assumptions.

### Exercise D — Debugging a Missing Metric

An HTTP service serves requests normally. `/actuator/metrics/orders.processing.duration` shows an increasing COUNT, yet the OTLP backend shows no new metrics.

Check step by step:

1. Is the OTLP registry added and configured in Spring Boot?
2. Do URL, port, and protocol match the Collector receiver? Does `localhost` point to the right place under Docker/Kubernetes?
3. Are there publish errors, timeouts, or HTTP error codes from the backend/Collector in logs?
4. Does the Collector receiver see payloads? Is the batch processor holding or dropping them?
5. Is the Collector exporter connecting to the backend successfully, with remaining quota/capacity?
6. Do temporality and metric names match the backend's queries?
7. Have enough step intervals, batch timeouts, and dashboard refreshes elapsed?

### Exercise E — Verifying Semantic Correctness

A developer instruments the same method with both `@Observed` and a manual `Timer.Sample`. Later they increase `step` from 30s to 60s, yet the dashboard's operation count remains doubled.

Explain why **changing `step` cannot fix double instrumentation**, and show how to assign a single measurement owner per business boundary. When both metrics and tracing are needed, use a single Observation with matching handlers instead of two overlapping instruments.

### Self-Check Questions

1. What is the difference between when `Counter.increment()` runs and when the exporter publishes?
2. Is `step` synonymous with `scrape_interval`?
3. Does the Collector's batch processor set the application's `step`?
4. When does a size trigger flush a batch vs. a timeout trigger?
5. Why can a single OTLP payload represent thousands of requests without containing thousands of individual request records?
6. How do delta and cumulative temporality differ? Can you infer temporality from `step` alone?
7. Does a large batch size cure high metric cardinality caused by `requestId`?
8. Why can the backend still lack metrics even when the app's Actuator shows them?
9. When an exporter fails, should you assume measurements are durably saved until the network recovers?
10. How can you use logs and tracing to verify the app is still serving requests while the metrics pipeline is failing?

**Completion criteria:** distinguish step, publish, batch, scrape interval, and temporality; configure either an OTLP/Collector push pipeline or a Prometheus pull pipeline; interpret latency and data point counts accurately; manage cardinality, retries/queues, and exporter error reporting; and never confuse trace sampling with metric cadence.

## 18. Key Takeaways

- **Step** is the aggregation and publish cadence of a step-style registry. It does not mean the application only updates a Counter once per period.
- **Batch** is how data points are grouped for transport or processing. Collector batching has its own timeout/size settings and does not replace Micrometer's `step`.
- **OTLP push** and **Prometheus pull** are separate export paths. `management.otlp.metrics.export.step` does not control Prometheus's `scrape_interval`.
- **Temporality** (delta/cumulative) and units must be verified at the exporter/backend; never infer Counter meaning solely from meter name or `step`.
- Shorter steps usually deliver fresh data faster at higher overhead; longer steps reduce publishes at the cost of slower detection. Larger batches reduce request counts while raising latency and memory usage.
- **Cardinality and histograms** usually dominate payload size far more than tuning batch size alone. Keep metric tags finite; put request IDs in logs/traces instead of metric labels.
- Inspect **end-to-end**: in-app meters → publish → Collector → exporter → backend → dashboard. Data in Actuator does not prove export succeeded.
- Keep logging, trace propagation, and sampling configured independently. Metrics detect trends; traces and logs pinpoint specific operations when investigating errors or latency.

## References

- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry Collector — Batch processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor)
- [OpenTelemetry — Metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)

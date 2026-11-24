# Controlling Connection Failures, Data Loss, and Cost During Monitoring Outages

## 1. Understanding the Incident: The App Keeps Running, Yet Visibility Can Be Lost

In Spring Boot Actuator, recording a measurement into Micrometer and delivering that measurement to storage are two distinct steps. A business request can succeed and increment a counter inside the JVM, while the central dashboard stays blank because the metrics collection pipeline is broken.

For example, an order service still accepts orders from 10:00–10:05 while Prometheus cannot reach its metrics endpoint. You cannot conclude sales were zero merely because the graph has no points. Nor can you promise that after 10:05 every minute-by-minute detail from those five minutes will magically reappear.

This article focuses on three questions:

- Where along the metrics pipeline does a failure occur, and does it affect business processing?
- Which measurements can still be inferred after connectivity recovers, and which are lost?
- What limits ensure waiting, retries, and backfilling do not exhaust resources or spike costs unexpectedly?

**Metrics are aggregated or sampled observability data.** If you need per-transaction reconciliation, rely on durable business data or an appropriate event-logging mechanism. Do not use an in-memory counter as a payment ledger.

### Key Terms to Distinguish

| Term | Meaning in This Article |
| --- | --- |
| Registry | Where Micrometer manages meters and measurements currently recorded in the application |
| Scrape | Monitoring system actively reading each application's metrics endpoint |
| Exporter | Component converting/sending metrics to an ingestion system |
| Backend | System that ingests, stores, and serves metrics queries |
| Timeout | Wait limit for a single operation; not synonymous with a time limit on the entire retry sequence |
| Retry | Resending after a potentially transient error |
| Bounded queue | Buffer with a maximum capacity and explicit behavior when full |
| WAL | Write-ahead log on disk; recovery capability still depends on capacity, retention, and the owning component's mechanics |
| Data freshness | Elapsed time from the latest received measurement to the current time |
| Cardinality | Number of distinct metric name and tag value combinations forming separate time series |

## 2. Diagram the Path Before Editing Configuration

Two models are common within Actuator's scope.

### 2.1. Pull: Prometheus Reads from the Application

```text
Business Logic → Micrometer in JVM
                       ↑
                  HTTP scrape
                       |
               Local Prometheus → remote_write → Remote Backend
                       |
                    Query → Dashboard
```

Spring Boot provides `/actuator/prometheus` when a suitable Prometheus registry is present and the endpoint is exposed. `/actuator/metrics` serves diagnostic inspection; it does not replace the Prometheus scrape format. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Three failures in the diagram have different consequences:

1. **Prometheus cannot read the application:** samples are missing right at collection.
2. **Prometheus scrapes fine, but the remote backend fails:** data may still reside in local Prometheus; forwarding capability depends on remote write.
3. **Dashboard or query tier fails:** data may still be collected completely; check the storage tier before concluding data is lost.

In a typical pull model, the application does not send an HTTP request to Prometheus after every business operation. Prometheus going down does not mean business worker threads are blocking on calls to Prometheus. However, registering too many meters or computing gauges with expensive operations can still consume application resources.

### 2.2. Push: Registry Sends Periodically

```text
Business Logic → Micrometer → Periodic Exporter → Collector/Backend
                                                         |
                                      Buffering and retry if configured
```

In this model, inspect the exact registry in use: aggregation temporality, protocol, wait limits, send mechanism, and failure behavior. Do not assume one registry's retry or persistence features exist in another.

If the application sends to a nearby OpenTelemetry Collector, the Collector can forward to the backend. However, guarantees inside the Collector only apply to data that reached the Collector; they cannot recover data that never left the JVM.

**Configuration ownership must follow the component:** scrape timing belongs to Prometheus; registry export timing belongs to Spring Boot/Micrometer; forwarding queues belong to the Collector or Prometheus. Do not invent a `queue-size` key in `application.yml` and assume the application now has a durable buffer.

## 3. Lost Data Points, Lost Totals, and Lost Business Data Are Three Different Levels

### 3.1. Cumulative Counters Can Preserve Total Increase, While Losing Time Distribution

Assume the same JVM process, the same time series, and no counter resets:

| Timestamp | Counter in JVM | Scrape Result |
| --- | ---: | --- |
| 10:00 | 100 | Received 100 |
| 10:01 | 120 | Failed |
| 10:02 | 155 | Failed |
| 10:03 | 190 | Failed |
| 10:04 | 230 | Received 230 |

The two read values show the counter increased by **130** between the two observations. They do not tell you how much it increased during each individual minute. You cannot reconstruct points 120, 155, and 190 from 100 and 230 alone.

With systems using cumulative values to compute server-side rates, the delta between reads can preserve overall totals across an outage. With systems aggregating per interval on the application side, data transitions between the current and previous interval; that is not an archive of all past intervals for indefinite replay. See [Micrometer — Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

The "same process, same series" condition matters greatly. If the application restarts while disconnected, unobserved increments before the restart can be lost. A deployment changing tags can also create a new series; do not subtract values across two different series.

Prometheus provides `rate()` and `increase()` functions that handle visible resets in samples and extrapolate across the query window. `increase()` can return non-integer values. These functions do not recover an activity period with zero observations; windows lacking enough samples will not yield reliable rates either. See [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

### 3.2. Gauges Do Not Retain Intermediate Value History

Suppose in-flight requests are 4, 80, and 6 within one minute. Sampling only at the start and end of the minute sees 4 and 6; the peak of 80 can vanish from collected data.

A gauge represents the value at observation time. Recording values continuously inside the application does not mean every intermediate value is sent and stored. See [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Operational consequences:

- A low memory gauge after recovery does not prove there was no memory spike during the monitoring outage.
- To observe peaks within an interval, choose an appropriate statistic type and configuration; increasing retries does not turn a gauge into a history log.
- For events that need counting, choose a counter or a timer's count rather than simulating event counts with a gauge.

### 3.3. Timers and Histograms Depend on What Data Was Retained

A timer may maintain count, total time, max, or distribution buckets depending on configuration and registry. Do not treat all of those components as having the same lifespan and recoverability.

For example, if cumulative count and total time for the same process are readable at both ends of an outage, you can derive the overall average of measurements in that window by dividing the difference in total time by the difference in count. That still does not tell you per-minute or per-request latency. Decaying windowed maxes and aggregated quantiles may no longer represent the missed period.

When analyzing an incident, state explicitly whether what is missing is **time-series samples**, **a single interval's statistics**, or **all accumulated state before a JVM crash**. Saying "metrics were lost" alone is not enough to choose a fix.

## 4. Classifying Connection Errors to Handle Them Properly

| Symptom | Hypothesis to Check | Action |
| --- | --- | --- |
| Name resolution failure | DNS, wrong service name, resolver config | Check from the sending/scraping component's environment |
| Connection refused | No listening process or wrong port | Check bind address, port, and receiving process |
| Connect timeout | Network path, firewall, connection saturation | Check routing and connection wait limits |
| Read timeout | Connected, but receiver is slow or stalled | Check load, batch size, and response latency |
| TLS handshake/certificate error | Hostname mismatch, trust chain, expired cert | Fix TLS config; do not disable verification as a permanent fix |
| HTTP 401/403 | Invalid credentials or insufficient permissions | Fix credentials/config; relentless retries will not cure it |
| HTTP 404 | Wrong path, unexposed endpoint, misrouting | Check actual endpoint and path configuration |
| HTTP 413 | Batch exceeds receiver size limits | Reduce batch size or adjust limits appropriately |
| HTTP 429 | Rate limited or quota exceeded | Throttle rate and obey protocol/backend retry policies |
| HTTP 5xx | Receiving service/proxy error | Bounded retries if the error is deemed transient |
| HTTP 2xx yet data missing | Wrong query tags, wrong time range, or partial acceptance | Inspect response body and actual accepted point counts |

This table is a diagnostic guide, not a promise that every exporter automatically retries every error listed. Protocols differ on retryable errors and partial-acceptance responses.

Two checks to perform before changing parameters:

1. Test connectivity from the **exact origin of the network request**. A laptop reaching the endpoint does not prove the Prometheus container can reach it.
2. Compare clocks and time zones when aligning error timestamps, measurements, and queries. Delayed or mis-timestamped data can look like data loss.

## 5. Keeping Metrics Export Failures Within Resource Bounds

### 5.1. Decoupling Observability from Business Execution Paths

During order processing, record counters/timers via the configured registry. Do not inject a synchronous HTTP call to the metrics backend after each order and wait indefinitely.

Design goals when the metrics backend fails:

- Business outcomes still reflect actual business results.
- Do not spawn unbounded sender threads, retry tasks, or in-memory objects.
- Monitoring UIs clearly surface missing/stale data.
- Export failures remain visible without creating infinite log storms.

A background exporter still consumes CPU, RAM, connections, and disk. Thus "running in the background" does not mean "zero impact." Test with the backend genuinely unavailable rather than testing only the happy path.

Normally, do not make monitoring backend availability a mandatory readiness/liveness condition for business services. If every instance drops out of the load balancer just because a shared metrics backend went down, an observability outage cascades into a service outage. Cases with special regulatory control requirements must make an explicit decision with appropriate evidence; do not infer such a requirement merely from using Actuator.

### 5.2. Timeouts Are Multiple Distinct Budgets

Distinguish among:

- Connection establishment timeout.
- Response/read timeout.
- Total deadline for a single send attempt, if supported by the library.
- Total duration a batch is retained and retried.
- Application shutdown grace wait time.

Do not assume `connect-timeout + read-timeout` cleanly bounds every phase such as DNS, TLS, request writes, and retries. Read the contract of the specific HTTP client/exporter.

If the export interval is 30 seconds while a single send can take nearly 2 minutes, check actual behavior when a send has not finished: does the schedule slip, skip intervals, or overlap tasks? Do not solve this by raising thread counts indefinitely.

### 5.3. Retries Need Bounds, Backoff, and Jitter

A sound policy typically includes:

1. Retry only errors likely to be transient.
2. Exponentially increase wait intervals up to a cap.
3. Add random jitter so multiple instances do not retry at the exact same instant.
4. Cap retry count or total retry duration.
5. Cap in-flight batches and buffer capacity.
6. Count/record dropped data when the budget is exhausted.

These are evaluation criteria for a sending component, not a universal property set supported by every Micrometer registry. If an existing exporter lacks the required policy, consider delegating forwarding to a dedicated component rather than wrapping an uncontrolled retry loop around it.

After a timeout error, the receiver may have persisted the data even though the response never returned. Retrying then risks duplicates. How this is handled depends on series identity, timestamps, data types, and protocol; never claim "exactly once" just because retries are enabled.

### 5.4. A Full Queue Requires an Explicit Choice

| Option | Trade-off |
| --- | --- |
| Drop newest data | Protects memory but loses the most recent information |
| Drop oldest data | Prioritizes freshness but loses queued history |
| Block the sender | Applies backpressure; dangerous if blocking cascades to business threads |
| Spill to disk | Survives restarts but requires disk budget and replay logic |
| Deliberately shed collected metrics | Reduces load at the cost of detail; policy changes must be documented |

Not every product exposes all options. Determine what behavior is active, what gets dropped, and whether drop counts are observable.

## 6. Illustrative Configuration for Spring Boot 3.3

The snippets below are learning examples for a standalone Spring Boot 3.3 application, not instructions to modify a repository's build. Micrometer versions follow Spring Boot's dependency management. When using a different version, verify against matching documentation before copying properties.

### 6.1. Pull Option: Bounding Scrape Duration in Prometheus

The application needs Actuator and the Prometheus registry. Example Gradle dependencies when the project already uses Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Application configuration for a single-machine lab:

```yaml
spring:
  application:
    name: orders-demo

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: orders-demo
```

This snippet assumes default Actuator paths, an HTTP server application, and no additional security rules blocking lab requests. Binding to loopback permits local access only. If Prometheus runs in another container or host, configure an appropriate address and access controls; `127.0.0.1` inside a container does not point to the host machine.

`prometheus.yml` file for Prometheus running directly on the same machine:

```yaml
global:
  scrape_interval: 15s
  scrape_timeout: 3s

scrape_configs:
  - job_name: orders-demo
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - 127.0.0.1:9091
```

Here, `scrape_timeout` bounds a single scrape; it must not exceed the effective scrape interval. It does not set timeouts for business HTTP requests to the application. Choosing 3 seconds and 15 seconds is illustrative and should be tuned to measured latency and incident-detection needs. For syntax, see [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

When the network path to the endpoint fails, Prometheus may record failed scrapes while the application continues writing metrics to the registry. However, missed samples are not queued at the endpoint for later backfill.

### 6.2. Push Option: Setting Budgets for OTLP Metrics

If choosing Micrometer OTLP instead of the Prometheus registry in the example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

An illustrative Spring Boot 3.3 configuration:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://127.0.0.1:4318/v1/metrics
        connect-timeout: 1s
        read-timeout: 3s
        step: 30s
        batch-size: 1000
```

- The address above targets a Collector supporting OTLP HTTP metrics on the same machine.
- `step` is the export interval; it is not a backfill retention window.
- `batch-size` caps the number of measurements per request; it is not a queue capacity, max byte limit, or total JVM meter cap.
- Timeouts bound waiting on their respective network operations; this configuration does not add a WAL.
- Do not confuse `management.otlp.metrics.export.*` with OTLP tracing configuration.

Property names and semantics were verified against [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html). Values of 1 second, 3 seconds, 30 seconds, and 1000 are example choices, not universal defaults for every environment.

An application with multiple registries on the classpath may export to multiple destinations. Keep/enable only needed registries to avoid unexpected cost and duplicate traffic. To temporarily disable OTLP, the example property is `management.otlp.metrics.export.enabled=false`; editing configuration files typically requires reloading/restarting per deployment mechanics rather than taking effect dynamically.

## 7. What Durable Buffers Help With—and What They Don't

Pipelines can be designed in two ways:

```text
Application → Local Prometheus → remote_write → Remote Backend

Application → Local Collector → forwarding queue → Remote Backend
```

### 7.1. With Prometheus Remote Write

Remote write reads data from the WAL and sends via queues per destination. Raising queue capacity or sender shards can increase RAM/CPU/network usage. Monitor pending samples, ingestion rate, send rate, and retention limits.

Prometheus operational documentation describes the risk of losing unsent data when a backend outage exceeds the WAL window, noting a two-hour horizon in the documented mechanism. Do not treat that mark as a universal durability guarantee across all versions, modes, and configurations. In particular, local database retention time does not automatically become the remote write retry horizon. See [Prometheus — Remote write tuning](https://prometheus.io/docs/practices/remote_write/).

The Prometheus WAL protects only what Prometheus has already ingested. If Prometheus fails to scrape the application for five minutes, no corresponding samples exist in the WAL to backfill.

### 7.2. With OpenTelemetry Collector

The Collector can use sending queues, exponential-backoff retries, and jitter. Suitable components can attach a queue to `file_storage` to persist data across restarts. Even so, data loss can still occur if the queue fills, retry deadlines expire, the disk fills/fails, or storage is lost. See [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/).

When choosing this approach, verify:

- The Collector distribution includes the required exporter and storage extension.
- The extension is actually declared, enabled, and wired into the exporter's queue.
- The storage directory is mounted on persistent volume with write permissions.
- Queue limits are measured in requests, batches, items, or bytes for your specific version/config.
- Retry rules and non-retryable error categories are understood.
- Cleanup, disk limits, and recovery have been tested.

Do not spot a configuration key containing "storage" and conclude all data is safe. Recoverability must be proven by restarting while queued data is pending.

## 8. Calculating Outage Buffer Capacity and Recovery Rate

The formulas below are simple planning models we constructed, not replacements for real resource measurements.

Let:

- `λ`: rate of data entering the buffer, in data points/second.
- `T`: expected receiver downtime duration, in seconds.
- `Q`: usable buffer capacity, expressed in data points.
- `μ`: sustained send rate after recovery, in data points/second.

When the receiver stops ingesting completely and the input rate is steady:

```text
Capacity needed for outage ≈ λ × T
Buffer outage endurance    ≈ Q / λ
```

Example: a system ingests 400 points/second and must survive a 10-minute outage:

```text
400 × 600 = 240,000 points
```

If measurements show an average of 200 bytes per point in the storage format in use, the data payload alone is estimated at:

```text
240,000 × 200 = 48,000,000 bytes ≈ 45.8 MiB
```

200 bytes is an **illustrative assumption**, not a fixed size for Prometheus or OTLP. Actual memory/disk usage also includes labels, indexes, objects, queues, metadata, and serialization overhead. Leave headroom for traffic spikes and measure under load tests.

After recovery, new data continues arriving. If the backlog is 240,000 points and sends succeed at 1000 points/second:

```text
Backlog drain rate = μ − λ = 1000 − 400 = 600 points/second
Time to catch up   ≈ 240,000 / 600 = 400 seconds
```

If `μ ≤ λ`, the system cannot catch up merely by waiting. You must increase receiver capacity, reduce ingress volume, or accept policy-based shedding. Enlarging the queue only delays hitting full capacity.

Actual outage survival is also capped by retry timeouts/data age limits and storage bounds. Having enough disk for one hour does not help if the sender discards data after five minutes.

To prevent recovery backfill from overloading the backend, cap send rate and concurrency during catch-up, and monitor the age of the oldest queued data. A queue that looks small by item count can still hold overly stale data.

## 9. Controlling Cost Even When the Pipeline Is Healthy

Metrics cost is more than a storage bill. Include JVM RAM, serialization/aggregation CPU, network bandwidth, buffer disk, query resources, and operational effort when data is delayed or missing.

### 9.1. Controlling Series Count Before Sacrificing Measurement Quality

A metric tagged with `route`, `status`, and `instance` can produce many series based on active combinations. A simple upper-bound estimate with 20 routes, 5 statuses, and 10 instances:

```text
20 × 5 × 10 = 1000 combinations
```

Not every combination occurs, and a single meter can emit multiple output series. Treat this number as a planning starting point, not a final total.

Adding `userId` with 100,000 values turns that theoretical ceiling into 100 million combinations. That is a label-design problem; raising timeouts will not solve it.

Use route templates such as `/orders/{id}` rather than individual paths containing order IDs. Do not put request IDs or arbitrary error messages into metric tags. When you need to look up a specific request, use appropriate log/trace data. Official guidance likewise emphasizes the cost of labels and series: [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/).

Micrometer offers `MeterFilter` to deny meters or limit tag value counts, such as `maximumAllowableTags`. These are guardrails, not substitutes for bounded label design. Denying a meter means those measurements are not recorded through the denied meter; include this intentional shedding in your observability policy. See [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

### 9.2. Balancing Resolution, Histograms, and Replica Counts

With a steady series count and uniform scrape interval:

```text
Samples/day ≈ series count × 86,400 / scrape_interval_in_seconds
```

Example with 10,000 series:

- 15-second scrape: about 57,600,000 samples/day.
- 60-second scrape: about 14,400,000 samples/day.

This is a sample-count estimate, not a billing formula. Actual cost also depends on pricing per active series, ingested points, storage size, queries, retention, and replicas.

Lengthening the interval reduces resolution and increases detection time for some issues. Do not apply it uniformly across both critical metrics and low-priority metrics.

With classic histograms, each label set typically generates extra bucket, count, and sum series. Inspect actual output because registry types and settings can add further series. Enable only the granularity needed to answer operational/SLO questions, avoiding turning on every percentile/histogram for every meter without measuring cost.

If running multiple Prometheus servers, multiple Collectors, or multiple registries sending the same metrics, understand deduplication/distinction at the receiver. Replicas improve availability in an appropriate design but can also multiply ingestion volume and cost.

### 9.3. During Outages, Cost Also Comes from Retries and Logs

A 10-minute outage can cause load at three points in time:

1. Before the outage: normal metrics traffic.
2. During the outage: failed connections, retries, logs, buffers, and disk growth.
3. After the outage: sending both live data and backfill creates a traffic spike.

Rate-limit repeated logs using appropriate operational mechanisms while retaining error counters and timestamps for investigation. Do not log full payloads or credentials just to diagnose a connection failure.

## 10. Monitoring the Metrics Pipeline Itself

Do not alert only on high/low business metrics; alert when you can no longer observe those values.

In the Prometheus example, two expressions answer two distinct questions:

```promql
up{job="orders-demo"} == 0
```

This expression detects targets still tracked by Prometheus whose scrape failed.

```promql
absent_over_time(up{job="orders-demo"}[5m])
```

This expression detects when the entire series set matching the job has had no samples for five minutes. It does not detect an individual missing instance if other instances of the job still have samples. Detecting each missing instance requires knowing the expected instance list or a suitable reference source. These expressions are illustrative conditions, not complete alerting rules; see [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Also monitor:

- Scrape duration, response size, and series/sample counts.
- Failed, rejected, or dropped export counts on the component actually exporting data.
- Queue capacity, fill level, and data age.
- Timestamp of last successful send and end-to-end delay from collection to query visibility.
- RAM, CPU, disk, and connection counts during backend failures and recovery.

Internal metric names depend on product and version; check the endpoint and documentation of your exact Prometheus/Collector deployment rather than inventing a name and assuming the system exports it.

If Prometheus and its alerting pipeline go down together, that Prometheus instance cannot alert on its own outage. You need an independent check path, such as another system watching for periodic heartbeat signals. On dashboards, render gaps and staleness visibly; do not replace all missing values with 0 just to make lines look continuous.

## 11. Hands-On: Proving What Survives an Outage

This is a verification scenario for a test environment, not results already captured from a specific system.

### 11.1. Verifying the Normal Pull Path

Start the application and Prometheus per Section 6.1. On Windows with curl:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:9091/actuator/health
curl.exe --fail --silent --show-error http://127.0.0.1:9091/actuator/prometheus
```

On Linux/macOS, use `curl` instead of `curl.exe`. If security is enabled, include your environment's authentication; do not disable security just to force commands to work.

Expected: the health endpoint returns a valid response; the Prometheus endpoint returns exposition text rather than a meter-list JSON. Exact metric lists and values depend on the application, dependencies, and load at read time.

In Prometheus, verify the target is UP and has samples. Generate controlled load against an existing business operation; pick a real cumulative counter present in the output and record its **full label set** and starting value.

### 11.2. Simulating Scrape Failure While Business Traffic Continues

In the test environment, temporarily block **only connectivity from Prometheus to management port 9091**, keeping the business traffic path active. Do not block the application's entire network, as that tests a different failure mode.

Maintain the outage across several scrape intervals, continue generating load, and then restore connectivity.

Expected observations:

- The target records failed scrapes; the chart displays a gap with missing samples.
- If the same JVM and same counter series remain alive, the post-recovery value can include the increments recorded during the outage.
- Missed timestamped points are not magically reconstructed.
- Gauges may miss peaks that occurred only while scraping was down.
- Business response times and resource usage should be compared against baseline.

If you cannot block only the scrape path, you can stop Prometheus to observe collection loss. However, when Prometheus is stopped, do not expect it to keep recording `up=0`; that changes the experiment type and must be noted explicitly.

### 11.3. Repeating with an Application Restart

Repeat the outage and intentionally restart the test application after generating additional load. Compare samples before and after the restart timestamp.

Expected: counters in the new JVM start fresh; unscraped increments from the old JVM cannot be recovered from the new JVM alone. Record this conclusion separately from the non-restart case.

### 11.4. Testing a Backend Outage Behind a Buffer

Keep the local Prometheus/Collector running and make only the remote backend stop accepting data.

Check step by step:

1. Incoming data is still accepted locally.
2. The queue grows at the expected rate.
3. Resources remain within budget.
4. When limits/deadlines are reached, verify which data is dropped.
5. After recovery, send rate exceeds ingress rate enough to drain the backlog.
6. If persistent storage is enabled, restart the buffering component and verify queued data is recovered.

Judge by metrics received at the backend and freshness after catch-up, not merely by error logs stopping. If the protocol allows partial acceptance or retries cause duplicates, account for rejected/duplicate items during reconciliation.

## 12. Common Misconceptions

| Misconception | Replacement Understanding |
| --- | --- |
| No points on the chart means traffic is 0 | Distinguish a value of 0 from missing samples |
| Raising timeouts prevents data loss | Timeouts only bound waiting; you also need to understand buffers and metric types |
| Because the counter survived, every lost second can be recovered | Total increase can survive under the right conditions, but per-interval distribution is lost |
| More retries are always safer | Unbounded retries can exhaust RAM/disk or prolong load spikes on the backend |
| Having a WAL means zero loss forever | WALs still have capacity limits, disk failures, retention limits, and coverage boundaries |
| Changing `step` increases backfill duration | Export interval and backfill retention are two separate mechanisms |
| Changing `batch-size` caps total memory | Per-request batch size does not cap all queued data |
| Pushing through Pushgateway provides a history queue | Do not infer historical storage/replay guarantees from a gateway's presence |
| If the metrics backend breaks, mark every app not ready | Evaluate business serving health and observability health independently |
| Once the backend stops throwing errors, the incident is over | Still verify backlog drain, freshness, dropped data, and backfill load spikes |

## 13. Self-Check with Three Scenarios

**Scenario 1:** A counter is scraped at 500. Over the next three minutes the application handles 90 more requests without restarting, and the next scrape reads 590. What do we know?

We know the increase between the two observations is 90 if it is still the same cumulative series. We do not know the exact request count per minute. A specific `increase()` query is also subject to windowing and extrapolation rules; do not equate raw difference with every query result.

**Scenario 2:** A buffer has 120,000 points of headroom, ingress is 400 points/second, and the backend stops accepting writes. How long can it endure?

Under the simple model: `120,000 / 400 = 300 seconds`, or five minutes. If retry timeouts expire sooner, the queue actually has less free space, or traffic rises, usable endurance will be lower.

**Scenario 3:** The backend recovers at 350 points/second while ingress remains 400 points/second. Why doesn't the backlog shrink even after increasing queue size?

The drain rate is lower than the ingress rate, so the backlog continues growing by 50 points/second. You must change capacity, ingress volume, or drop policies; a larger buffer only delays hitting the limit.

When designing Actuator metrics export, the goal is a pipeline with well-understood loss boundaries, resource usage bounded within budget, and verified recovery behavior. Decisions about what loss is acceptable must come from the observability questions you need to answer and actual business requirements.

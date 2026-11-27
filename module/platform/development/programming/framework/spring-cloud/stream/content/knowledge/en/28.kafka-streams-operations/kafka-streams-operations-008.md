# Monitoring Topology, Stream State, and State Store Metrics

A Kafka Streams application may still have a running Spring Boot process while its internal topology has halted, is stuck in prolonged rebalancing, or has lost a stream thread. Similarly, a health endpoint may report `UP` while consumer lag grows, state store restoration slows down, or RocksDB writes degrade. Therefore, operating Kafka Streams requires combining three observability layers: **topology structure**, **runtime state**, and **stream and state store metrics**.

The Spring Cloud Stream Kafka Streams binder provides an Actuator endpoint to retrieve topology descriptions, a health indicator to track stream threads, and metric export via Micrometer `MeterRegistry`. Kafka Streams complements this with metrics at the client, thread, task, processor node, state store, and record cache levels. These indicators help identify bottlenecks across processing, rebalancing, commits, state restoration, and local data access.

This lesson explains how to enable the required endpoints, interpret `KafkaStreams` states, choose metrics by recording level, monitor in-memory/RocksDB state stores, design alerts, and test operational observability.

## 1. Three Observability Layers

No single metric fully describes a topology's health. Separate observability into three layers:

| Layer | Question to Answer | Tools or Data |
|---|---|---|
| Topology | Which processors, sources, sinks, repartition topics, and state stores is the application building? | `kafkastreamstopology` Actuator endpoint and topology description. |
| Runtime state | What state are the Kafka Streams client, stream threads, and tasks in? Are threads failing, rebalancing, or restoring for too long? | Binder health indicator, `KafkaStreams` state, thread/task metadata, and logs. |
| Metrics | How are consumption/processing rates, commit latency, end-to-end latency, state-store latency, RocksDB I/O, and caches changing? | Micrometer `MeterRegistry`, Actuator metrics, Prometheus, or equivalent metrics system. |

A topology description is a structural representation built from the DSL/Processor API. It is not a snapshot of per-record processing state. Runtime state tells you whether the topology is running or transitioning; metrics reveal component performance and behavior over time.

~~~mermaid
flowchart TD
    A[Spring Cloud Stream Kafka Streams application] --> B[Topology description]
    A --> C[Runtime health and state]
    A --> D[Micrometer MeterRegistry]
    B --> E[Actuator topology endpoint]
    C --> F[Actuator health endpoint]
    D --> G[Actuator metrics endpoint]
    D --> H[Prometheus / monitoring backend]
    E --> I[Topology visualization]
    F --> J[Operational alerts]
    G --> J
    H --> J
~~~

## 2. Enabling Actuator and the Topology Endpoint

The Kafka Streams binder exposes:

- **GET /actuator/kafkastreamstopology**: retrieves topology descriptions of processors managed by the application.
- **GET /actuator/kafkastreamstopology/{application-id}**: retrieves a processor's topology description by Kafka Streams application ID.

The topology endpoint is disabled by default. The application needs Spring Boot Actuator and a web runtime; if using WebFlux, you can use `spring-boot-starter-webflux` instead of `spring-boot-starter-web`.

Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Expose the required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
  endpoint:
    health:
      show-details: when_authorized
~~~

Example queries:

~~~http
GET /actuator/kafkastreamstopology
GET /actuator/kafkastreamstopology/order-enrichment-v1
~~~

The path parameter in the second URL is the processor's `application.id`, not the function bean name or binding name. When an application runs multiple Kafka Streams processors, confirm the exact application ID before querying its topology.

The endpoint returns a topology description. You can feed this description into external tools to render graphs and inspect sources/sinks, processing nodes, repartitions, and state stores. The endpoint itself does not provide per-node performance dashboards or live execution state; use metrics and health for those questions.

## 3. Reading a Topology Description

A Kafka Streams topology typically contains these node types:

- **Source:** reads records from one or more input topics.
- **Processor:** applies filters, maps, aggregations, joins, windows, suppression, or custom logic.
- **Sink:** writes records to output topics.
- **Repartition:** writes and re-reads data to change partitioning/keys ahead of an operation requiring co-partitioning.
- **State store:** stores local state for aggregations, joins, windows, or the Processor API.

Example of a topology summing amounts per customer:

~~~mermaid
flowchart LR
    A[(order-amounts)] --> B[Source]
    B --> C[Group by customerId]
    C --> D[Aggregate]
    D <--> E[(amount-by-customer store)]
    D --> F[Sink]
    F --> G[(customer-totals)]
~~~

When inspecting an actual topology, verify:

1. Source nodes read the right topics and expected number of inputs.
2. Repartition nodes appear at the exact points where keys change.
3. Processor nodes are connected in the intended business order.
4. State stores have expected names, types, and linked processors.
5. Sink nodes write to the right output topics.
6. Each application ID's topology matches the configured function definitions.

If a topology changes after adding a join, `groupBy`, or repartition, compare topology descriptions across deployment versions. Topology changes can alter internal topics, state stores, and state restoration requirements.

## 4. Distinguishing KafkaStreams State, Stream Thread State, and Tasks

Kafka Streams has multiple state layers. Avoid using the phrase "stream state" for all layers indiscriminately, because a client may be `RUNNING` while a thread is rebalancing or a task is restoring state.

### KafkaStreams Client State

In Kafka 4.4, the `KafkaStreams.State` enum has these values:

| State | Operational Meaning |
|---|---|
| `CREATED` | `KafkaStreams` instance created but not yet started. |
| `REBALANCING` | One or more threads are revoking/assigning partitions or tasks are not yet ready to process. |
| `RUNNING` | Stream threads are running and active tasks are ready to process. |
| `PENDING_SHUTDOWN` | Closing resources as part of shutdown. |
| `NOT_RUNNING` | Stopped after shutdown completed. |
| `PENDING_ERROR` | Closing resources after a fatal error. |
| `ERROR` | `KafkaStreams` instance is in an error state; can occur when the global thread or all stream threads die. |

Transitioning from `RUNNING` to `REBALANCING` can be normal when partitions are revoked or reassigned. Once active tasks are ready, the client returns to `RUNNING`. If `REBALANCING` persists, investigate task restoration, continuous rebalances, broker connectivity, and state store initialization times.

`PENDING_SHUTDOWN` and `PENDING_ERROR` are transient states. They are not steady operating states; the instance must finish closing resources before entering the corresponding terminal state.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> REBALANCING
    REBALANCING --> RUNNING
    RUNNING --> REBALANCING
    RUNNING --> PENDING_SHUTDOWN
    REBALANCING --> PENDING_SHUTDOWN
    CREATED --> PENDING_SHUTDOWN
    RUNNING --> PENDING_ERROR
    REBALANCING --> PENDING_ERROR
    PENDING_SHUTDOWN --> NOT_RUNNING
    PENDING_ERROR --> ERROR
~~~

### Stream Thread State

The binder health indicator exposes metadata per stream thread, including:

- Thread name.
- Thread state: `CREATED`, `RUNNING`, `PARTITIONS_REVOKED`, `PARTITIONS_ASSIGNED`, `PENDING_SHUTDOWN`, or `DEAD`.
- Active tasks with task IDs and partitions.
- Standby tasks with task IDs and partitions.

These thread state values differ from the `KafkaStreams.State` enum. For example, `PARTITIONS_REVOKED` is a thread-level state during rebalancing; `REBALANCING` is the aggregate state of the `KafkaStreams` client.

### Tasks and Partition Assignment

A topology is divided into tasks based on input partitions. Tasks can be active or standby. Active tasks perform processing; standby tasks maintain state replicas to reduce recovery time when a task migrates to another instance.

When investigating a non-running thread:

1. Identify the thread state.
2. Check assigned active tasks and partitions.
3. Confirm whether tasks are restoring state stores or awaiting partition assignment.
4. Compare task count against partition count and instance count.
5. Inspect rebalance logs and consumer group membership.

A single application ID may have multiple stream threads and tasks. Per-application-ID health details help isolate which processor has an issue when one Spring Boot process runs multiple Kafka Streams processors.

## 5. Enabling the Kafka Streams Binder Health Indicator

The Kafka Streams binder health indicator requires `spring-boot-starter-actuator`. Spring Cloud Stream provides `management.health.binders.enabled` to enable binder health indicators.

Example:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
~~~

Query:

~~~http
GET /actuator/health
~~~

By default, the endpoint shows only overall `UP` or `DOWN`. To inspect thread names, states, active tasks, and standby tasks, set `management.endpoint.health.show-details` to `ALWAYS` or `WHEN_AUTHORIZED`. In production, prefer `WHEN_AUTHORIZED` combined with Spring Security so only authorized users see details.

According to the Kafka Streams binder documentation, the health indicator reports `UP` when all registered Kafka threads are in the `RUNNING` state. Consequently, a brief rebalance can temporarily flip health. Use sustained duration thresholds and combine metrics before triggering automated restarts, avoiding restart loops while tasks are restoring normally.

If an application runs multiple Kafka Streams processors, each processor's health is categorized by application ID. The binder also supports `KStream`, `KTable`, and `GlobalKTable` binding types; when details are shown, similar information may appear across multiple health components.

## 6. Exporting Kafka Streams Metrics via Micrometer

The Spring Cloud Stream Kafka Streams binder exposes Kafka Streams metrics through Micrometer's `MeterRegistry`. With Actuator and Micrometer on the classpath, meters can be inspected via the Actuator metrics endpoint.

Expose the endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
~~~

List metrics:

~~~http
GET /actuator/metrics
~~~

Read a specific metric:

~~~http
GET /actuator/metrics/{metric-name}
~~~

Metric names, tags, and meter counts depend on the Kafka Streams version, Spring Boot, Micrometer, and configured recording level. Inspect the metric list from the live running application before building dashboards; do not copy metric names from a different Kafka version assuming they always exist.

If scraping with Prometheus, add `micrometer-registry-prometheus`, expose the `prometheus` endpoint, and configure Prometheus scraping. `/actuator/prometheus` serves metrics-system formatting, whereas `/actuator/metrics` is geared toward exploring and querying individual meters via Actuator.

## 7. Metric Hierarchy Across Client, Thread, Task, and Processor Node

Kafka Streams organizes metrics hierarchically. Operationally, they group as follows:

| Level | Scope | Example Metrics |
|---|---|---|
| Client | One `KafkaStreams` instance/application ID | `state`, `application-id`, `alive-stream-threads`, `failed-stream-threads`. |
| Thread | One stream thread | `process-rate`, `poll-rate`, `commit-latency-avg`, `process-latency-avg`. |
| Task | One task processing specific partitions | Task-level metrics and metrics attached to processors/stores in that task. |
| Processor node | One source, processor, or sink node | `records-consumed-total`, `records-produced-total`, `record-e2e-latency-avg`. |
| State store/cache | Task store or record cache | `put-latency-avg`, `get-rate`, RocksDB I/O, cache hit ratio. |

When aggregating metrics onto dashboards, always preserve identifying tags such as application ID, client ID, thread ID, task ID, processor node, and store scope when provided by the registry. Stripping all tags can blend values across processors and mask a failing task.

## 8. Recording Levels: info, debug, and trace

Kafka Streams allows tuning metric collection granularity:

| Recording Level | Scope | When to Use |
|---|---|---|
| `info` | Core client, thread, and selected state store metrics. | Default suitable for routine monitoring. |
| `debug` | Adds detailed processor, state store, record cache, and RocksDB metrics. | Enable when diagnosing performance or state store behavior. |
| `trace` | Adds fine-grained metrics such as record end-to-end latency. | Use short-term or for targeted diagnostics. |

In Kafka 4.4, most state-store metrics are recorded at `debug`; a few such as `num-open-iterators` and `num-keys` are at `info`, while `record-e2e-latency-*` are at `trace`. Older Kafka versions may expose a different set per recording level, so verify against the actual Kafka client pulled in by your application's dependency management.

You can configure this at the Kafka Streams binder level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              metrics.recording.level: debug
~~~

Properties equivalent:

~~~properties
spring.cloud.stream.kafka.streams.binder.configuration.metrics.recording.level=debug
~~~

`configuration` forwards Kafka Streams `StreamsConfig` properties to the Kafka Streams client. Because this is binder-level configuration, when multiple processors share the binder, the recording level can apply to all processors under that binder.

Collecting `debug`/`trace` increases instrumentation overhead and metric cardinality. Enable higher detail as needed, monitor time-series count, and revert to `info` once diagnostics finish if extra metrics are no longer needed.

## 9. Key Client and Thread Metrics to Watch

### Client-Level Metrics

| Metric | Meaning | Signal to Investigate |
|---|---|---|
| `state` | `KafkaStreams` client state as a string. | Prolonged `REBALANCING` or `ERROR`. |
| `application-id` | Client application ID. | Identify the exact processor on dashboards. |
| `alive-stream-threads` | Number of live stream threads running or rebalancing. | Unexpected drop below configured count. |
| `failed-stream-threads` | Number of stream threads that failed since client startup. | Increases after deploy or during processing errors. |
| `topology-description` | Description of the running topology. | Compare topology changes across versions. |

### Thread-Level Metrics

| Metric | Meaning | How to Read |
|---|---|---|
| `process-rate` / `process-total` | Rate and total count of processed records. | Drops may indicate idle input, rebalances, or slow processors. |
| `poll-rate` / `poll-total` | Consumer polls per second and total polls. | Reduced polling requires checking thread state and brokers. |
| `poll-records-avg` / `poll-records-max` | Average/max records returned per poll iteration. | Repeated empty polls may indicate empty topics or improper partition assignment. |
| `process-latency-avg` / `process-latency-max` | Record processing duration. | Sustained increases often signal slow logic, I/O, or state-store access. |
| `commit-latency-avg` / `commit-latency-max` | Commit duration. | Increases may relate to brokers, transactions, or state-store commits. |
| `punctuate-latency-avg` / `punctuate-latency-max` | Punctuator execution duration. | Increases can affect windowing, schedules, and periodic work. |
| `process-ratio`, `poll-ratio`, `commit-ratio` | Fraction of thread time spent in each activity. | Distinguishes whether threads are busy processing, waiting on poll, or committing. |

Do not trigger alerts solely because `process-rate` equals 0. If a topic has no new records, a processing rate of 0 is normal. Combine polled record counts, topic input rate, consumer lag, thread state, and time since last processed record.

## 10. Processor-Node and Topic Metrics

Processor-node metrics help pinpoint where in the topology latency or throughput shifts:

- `records-consumed-total`: total records consumed by source processors.
- `records-produced-total`: total records written by sink processors.
- `record-e2e-latency-avg` and `record-e2e-latency-max`: latency from record timestamp to node completion.
- Suppression metrics: records emitted by suppression nodes and final-record emission latency.

Comparing record counts between source and sink must account for filters, branches, joins, aggregations, and suppression. Fewer sink records than source records do not automatically prove data loss; the topology may intentionally drop or aggregate records.

`record-e2e-latency` relies on record timestamps and system clocks. If producers emit incorrect timestamps, future timestamps, or clocks drift across machines, values can appear negative or skewed. Validate event-time semantics before using this metric as an SLO.

## 11. How Are State Stores Created and Materialized?

Kafka Streams automatically creates state stores when DSL operators require state, such as `aggregate`, `count`, `reduce`, joins, or windowed aggregations. With the Processor API, applications may register a `StoreBuilder` explicitly.

Example aggregating total amounts by customer and naming the state store:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerTotalsTopology {

    @Bean
    public Function<KStream<String, Long>, KTable<String, Long>>
            aggregateByCustomer() {
        return input -> input
                .groupByKey()
                .aggregate(
                        () -> 0L,
                        (customerId, amount, total) -> total + amount,
                        Materialized.<String, Long,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "amount-by-customer")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(Serdes.Long())
                );
    }
}
~~~

The name `amount-by-customer` identifies the store in the topology, logs, and metrics. Key/value Serdes must match the actual data types. State stores usually have changelog topics so Kafka Streams can restore state when tasks move to another instance.

If an input binding is a `KTable` and you want to materialize it as a named store, the Kafka Streams binder supports:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-1:
              consumer:
                materialized-as: incoming-store
~~~

In the example above, `process-in-1` is the second input binding of the `process` function. The binding name must match the actual function in the application. For the Processor API, custom stores can be declared as `StoreBuilder` beans; the binder discovers and registers them with the Streams builder during topology initialization.

## 12. State Store Metrics: Latency, Throughput, and Iterators

State-store metrics carry thread, task, and store scopes. For built-in stores, common scopes include:

- `in-memory-state`, `in-memory-lru-state`, `in-memory-window-state`.
- `rocksdb-state`, `rocksdb-window-state`, `rocksdb-session-state`.
- `in-memory-suppression` for suppression buffers.

Key metrics:

| Metric | Meaning | Operational Signal |
|---|---|---|
| `put-latency-avg`, `put-latency-max` | Duration to write a key/value to the store, in ns. | Sustained increases may indicate disk, compaction, or store contention. |
| `get-latency-avg`, `get-latency-max` | Read latency. | Increases can slow down joins or lookups. |
| `delete-latency-avg`, `put-all-latency-avg` | Delete or batch-write latency. | Helps detect shifting workload patterns. |
| `put-rate`, `get-rate`, `delete-rate` | Operations per second. | Correlate with input rate and topology logic. |
| `restore-latency-avg`, `restore-latency-max` | State restoration operation latency. | Increases can lengthen rebalance/startup time. |
| `commit-latency-avg`, `commit-latency-max` | State store commit duration. | Increases can reduce throughput. |
| `num-open-iterators` | Number of open iterators not yet closed. | Monotonic growth without dropping indicates leaked iterators. |
| `iterator-duration-avg`, `iterator-duration-max` | Lifetime of iterators. | Long-lived iterators hold RocksDB resources. |
| `oldest-iterator-open-since-ms` | Creation timestamp of the oldest open iterator. | Helps track down forgotten iterators. |

`num-keys` exists only for in-memory state stores; it is unavailable for RocksDB-backed stores. Do not use `num-keys` to estimate entry counts in RocksDB. For suppression buffers, buffer size/count metrics form a separate group; standard store metrics do not apply to suppression buffers.

The unit of state-store operation latency in Kafka Streams is nanoseconds. When plotting on dashboards, convert units explicitly; avoid directly comparing nanosecond store figures with millisecond thread latencies.

## 13. Monitoring RocksDB State Stores

Kafka Streams typically uses RocksDB for persistent key-value, window, and session stores. RocksDB metrics fall into two groups:

- **Statistics-based:** cumulative counts or rates for reads/writes, flushes, and compaction.
- **Properties-based:** point-in-time state such as memory and cache usage.

Useful metrics:

| Metric | Meaning | Diagnostic Use |
|---|---|---|
| `bytes-written-rate`, `bytes-written-total` | Bytes written to RocksDB. | Estimate write workload and I/O growth. |
| `bytes-read-rate`, `bytes-read-total` | Bytes read. | Identify read-heavy workloads. |
| `memtable-bytes-flushed-rate` | Rate of flushing memtables to disk. | Compare against write rate and disk throughput. |
| `memtable-hit-ratio` | Ratio of lookups served from memtable. | Gauge effectiveness of in-memory write buffers. |
| `block-cache-data-hit-ratio` | Hit ratio of the data block cache. | Prolonged low values can increase disk reads. |
| `block-cache-index-hit-ratio` | Hit ratio of the index block cache. | Evaluate index caching efficiency. |
| `write-stall-duration-avg`, `write-stall-duration-total` | Duration RocksDB spent stalled on writes. | Warns that compaction or disk cannot keep up with writes. |
| `compaction-time-avg`, `compaction-time-max` | Compaction duration. | Identify background RocksDB pressure. |
| `number-file-errors-total` | Total file errors. | Investigate filesystem, disk, and I/O errors. |

In Kafka 4.4, RocksDB statistics at `debug` recording level are collected periodically roughly once per minute. For stores spanning multiple RocksDB instances, such as window/session stores, several metrics are aggregated across the store's instances.

Collecting RocksDB statistics can add operational overhead. Enable `debug` only when detailed tracking is needed, and monitor CPU, I/O, heap, and metric count. Some file error counters may be less informative in newer RocksDB versions; check metric descriptions in your running Kafka client before writing alerts.

## 14. Record Cache and Suppression Buffers

Kafka Streams uses a record cache to coalesce or defer certain state store updates and downstream outputs during processing. Record-cache metrics help evaluate whether caching reduces redundant writes:

- `hit-ratio-avg`, `hit-ratio-min`, `hit-ratio-max`: cache hit ratio.
- Additional hit/miss and cache-size metrics depending on Kafka client version.

A low cache hit ratio is not inherently an error. It depends on workload, key distribution, cache size, topology, and update rate. Compare alongside throughput and state-store write rates before increasing cache size.

Suppression buffers have dedicated metrics:

- `suppression-buffer-size-avg` and `suppression-buffer-size-max`: size of buffered data.
- `suppression-buffer-count-avg` and `suppression-buffer-count-max`: count of buffered records.
- `suppression-emit-rate` and `suppression-emit-total`: rate/total of records emitted downstream.
- `emit-final-latency-avg` and `emit-final-latency-max`: latency of emitting final records.

If the suppression buffer grows continuously while emission rate stays low, inspect window size, grace period, watermarks/event-time, and final emission conditions. Do not immediately treat a large buffer as an error if the workload uses long windows; compare against buffer limits and latency SLOs.

## 15. State Restoration and Rebalance Duration

When a task is assigned to another instance, Kafka Streams must restore its state store from the changelog topic if no suitable standby task exists or local state cannot be reused. During restoration, threads may not yet return to `RUNNING`, and the client may remain in `REBALANCING`.

Signals to observe:

- Duration spent in `REBALANCING` from start until the client returns to `RUNNING`.
- `restore-latency-avg` and `restore-latency-max`.
- Data volume read from changelog / restore rate.
- Active task and standby task counts.
- Input lag during restoration.
- Disk throughput, RocksDB write rate, and compaction.

If restoration takes long after every restart:

1. Check state store and changelog topic sizes.
2. Check disk throughput, free space, and filesystem health.
3. Verify standby replicas are configured and distributed properly.
4. Check partition and task counts assigned per instance.
5. Evaluate whether local state can be preserved across restarts or if cleanup settings are wiping state unnecessarily.

The Spring Cloud Stream Kafka Streams binder does not delete local state by default when a binding stops. You can alter this behavior with a `CleanupConfig` bean to clean up on start, on stop, or never. Only enable cleanup when you understand its impact on restore times: wiping local state forces subsequent runs to restore from Kafka changelogs, lengthening startup.

## 16. Distinguishing Health, Throughput, and Lag

Health `UP` is an important signal, but does not replace capacity and progress metrics:

| Observation | What You Can Conclude | What You Cannot Conclude |
|---|---|---|
| Health `UP` | Registered Kafka threads are `RUNNING` according to the health indicator. | Does not prove consumer lag is low or business output is accurate. |
| High `process-rate` | Threads are processing many records. | Does not prove records are written accurately or without duplicates. |
| `process-rate` equals 0 | No records were processed during the window. | Does not prove threads are hung; the topic may simply have no incoming data. |
| `REBALANCING` | Client is revoking/assigning partitions or preparing tasks. | Not necessarily an error if brief. |
| Rising `restore-latency` | State restoration is taking longer. | Does not pinpoint whether disk or changelog fetch is the bottleneck. |
| Rising `failed-stream-threads` | A thread failed since client startup. | Does not reveal the specific business error without checking logs. |

The regular Kafka binder exposes `spring.cloud.stream.binder.kafka.offset` metrics for consumer group/topic lag. Those metrics belong to the Kafka message-channel binder. Do not assume identical metrics are emitted for the Kafka Streams binder. For Kafka Streams, combine consumer metrics, stream/thread/task metrics, consumer group tooling, and broker-side lag monitoring for your deployed version.

## 17. Observability Configuration for a Processor

Example configuration for the `aggregateByCustomer` processor:

~~~yaml
spring:
  application:
    name: customer-aggregation
  cloud:
    function:
      definition: aggregateByCustomer
    stream:
      bindings:
        aggregateByCustomer-in-0:
          destination: order-amounts
        aggregateByCustomer-out-0:
          destination: customer-totals
      kafka:
        streams:
          binder:
            application-id: customer-aggregation-v1
            configuration:
              metrics.recording.level: debug

management:
  health:
    binders:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics,kafkastreamstopology
  endpoint:
    health:
      show-details: when_authorized
~~~

This configuration:

1. Activates the `aggregateByCustomer` function.
2. Reads `order-amounts` and writes results to `customer-totals`.
3. Sets the application ID to `customer-aggregation-v1`.
4. Enables `debug` metrics for deeper visibility into state stores and processors.
5. Exposes `health`, `metrics`, and topology endpoints.
6. Restricts health details to authorized users.

When running multiple processors in one application, assign an explicit application ID per processor in the Kafka Streams binder configuration. The topology endpoint and health details categorize by application ID, preventing dashboards from mixing states across processors.

## 18. Dashboards and Operational Alerts

A solid dashboard should be organized into rows by purpose:

### Row 1 — Processor Health

- `KafkaStreams` client state by application ID.
- Count of alive stream threads.
- Count of failed stream threads.
- Thread counts in `RUNNING`, `REBALANCING`, or `DEAD`.
- Active/standby tasks and partition assignments.

### Row 2 — Processing Capacity

- Input records/sec and output records/sec.
- `process-rate`, `poll-rate`.
- `process-latency-avg`/`max`.
- `commit-latency-avg`/`max`.
- Record end-to-end latency if `trace` is enabled.

### Row 3 — State Store

- Put/get rates and latencies.
- Restore latency.
- RocksDB bytes read/written.
- Block-cache hit ratio.
- Write-stall duration and compaction time.
- Open iterator count and iterator duration.

### Row 4 — Brokers and Resources

- Consumer lag by input topic/partition.
- Changelog topic throughput and replication health.
- CPU, heap, GC pauses, disk I/O, and free disk space.
- Network throughput and request latency to Kafka brokers.

Alerts should require sustained conditions and combine multiple signals:

| Alert | Suggested Condition | Investigation Action |
|---|---|---|
| Processor in `ERROR` | Client state enters `ERROR`. | Inspect uncaught exceptions, failed threads, and logs. |
| Dead thread | `alive-stream-threads` drops below expected or thread state is `DEAD`. | Check exceptions, shutdown events, and thread failures. |
| Prolonged rebalance | `REBALANCING` exceeds measured operational threshold. | Check task restoration, partition churn, and broker connectivity. |
| Continuously rising lag | Consumer lag rises while input rate exceeds output/process rate. | Look for slow processors, state-store I/O, or insufficient task parallelism. |
| Slow commits | Sustained spike in `commit-latency-max`. | Check brokers, transactions, and state-store flush/commit. |
| Slow restore | Restore latency climbs or startup stalls. | Check changelogs, RocksDB, disk, and standby tasks. |
| RocksDB write stall | `write-stall-duration-total` climbs rapidly. | Check disk, compaction, write rate, and RocksDB resource limits. |
| Leaked iterators | `num-open-iterators` or oldest iterator age rises steadily. | Inspect code creating iterators and ensure all iterators are closed. |
| Growing suppression buffer | Buffer size/count climbs steadily with low emit rate. | Inspect windows, grace periods, and event-time watermarks. |

Do not apply identical static thresholds across all topologies. Measure baselines under normal load, evaluate peak hours, and alert on rate of change or sustained duration rather than single samples.

## 19. Testing Observability

Testing must verify that both endpoints and metrics actually appear on an application running against a test Kafka broker. Topology unit tests do not prove Actuator endpoints are exposed or recording levels are active.

### Topology and Health Scenarios

1. Start the application with a known application ID.
2. Call `/actuator/kafkastreamstopology`.
3. Call `/actuator/kafkastreamstopology/{application-id}`.
4. Cross-check sources, processors, sinks, and state stores against the topology configuration.
5. Call `/actuator/health` as a user authorized to view details.
6. Verify health details contain application ID, thread states, active tasks, and standby tasks.
7. Trigger a controlled rebalance in the test environment and observe client/thread state transitions.

### State Store Metrics Scenarios

1. Create a topology with an aggregation materialized into a named store.
2. Send records across multiple keys to drive put/get activity.
3. Inspect `/actuator/metrics` and confirm Kafka Streams metrics are registered.
4. Check put/get latency and rate by store scope.
5. Enable `debug` recording level and confirm expected RocksDB/state-store metrics appear.
6. Restart the processor in the test environment to trigger state restoration.
7. Observe restore latency, disk I/O, and time to return to `RUNNING`.
8. If the topology opens iterators, confirm iterators are closed and open iterator count returns to baseline.

### Test Matrix

| Scenario | Setup | Result to Verify |
|---|---|---|
| Aggregate topology endpoint | `GET /actuator/kafkastreamstopology`. | Returns descriptions of topologies managed by the binder. |
| Per-application-ID topology | `GET` endpoint with exact ID. | Returns only that processor's topology. |
| Unexposed endpoint | Omit `kafkastreamstopology` from exposure list. | Endpoint is unreachable over web. |
| Normal health | Healthy brokers, restored tasks. | Threads `RUNNING` and health `UP`. |
| Rebalance | Change instance/partition assignment in test. | Thread and client states reflect the transition. |
| Thread failure | Trigger a controlled failure in an appropriate test. | Failed thread/state/health are recorded and logs show the cause. |
| `info` metrics | `metrics.recording.level=info`. | Core client/thread metrics are queryable. |
| `debug` metrics | Enable `debug`. | Additional state-store, processor, and RocksDB metrics appear per Kafka version. |
| `trace` metrics | Enable `trace` when needed. | Fine-grained metrics such as record end-to-end latency can appear. |
| State restore | Wipe local state in test environment or move tasks to a new instance. | Restore latency and rebalance duration are observable. |
| Iterator lifecycle | Open and close iterators in processor. | Open iterator count does not grow unboundedly. |
| Multiple processors | App with multiple application IDs. | Health and topology distinguish each processor. |
| Endpoint security | Access with unauthorized user. | Health details/topology/metrics are protected per policy. |

## 20. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Topology endpoint unreachable | Missing Actuator/web dependency or endpoint not exposed. | Add dependencies and include `kafkastreamstopology` in exposure list. |
| Topology endpoint returns wrong processor | Wrong application ID used. | Confirm the processor's application ID and query the matching endpoint. |
| Health only shows `UP`/`DOWN` | `show-details` unconfigured or user unauthorized. | Set `WHEN_AUTHORIZED` and grant appropriate roles. |
| Health `DOWN` during rebalance | A thread is not yet `RUNNING` or tasks are still restoring. | Inspect thread/task state and rebalance duration before restarting. |
| State-store metrics missing | Recording level is `info`, or store type/version lacks that metric. | Check Kafka client version and enable `debug` when needed. |
| `num-keys` missing | Store uses RocksDB. | `num-keys` is only for in-memory state stores; use RocksDB properties/metrics instead. |
| Metrics missing from Actuator | `MeterRegistry`/Actuator missing or metrics filtered out. | Verify Micrometer dependency, endpoint exposure, and `MeterFilter` beans. |
| Metrics blended across processors | Dashboard strips application ID/client/task/store tags. | Keep identifying tags in queries and alerts. |
| Prolonged restore after restart | Large state, slow changelog reads, slow disk, or local state cleaned up. | Inspect restore metrics, changelogs, RocksDB, and `CleanupConfig`. |
| Open iterators keep rising | Iterators in Processor API are not closed. | Use try-with-resources or close iterators on all paths. |
| Zero `process-rate` triggers constant alerts | Topic has no new records or topology filters all records. | Combine input rate, lag, poll metrics, and business output. |
| Rising RocksDB write stalls | Compaction or disk cannot keep pace with write workload. | Check write rates, compaction, disk latency, and resource limits. |

When investigating, move top-down from client state to threads/tasks, then to processor nodes and state stores. Correlate with input rate, output rate, consumer lag, broker health, and host resources at the same timestamp. Layered inspection pinpoints whether the bottleneck lies in topology structure, partitioning, processing logic, or state-store I/O.

## 21. Pre-Deployment Checklist

- [ ] Configured an explicit application ID per Kafka Streams processor.
- [ ] Added required Actuator and web runtime dependencies.
- [ ] Exposed `health`, `metrics`, and `kafkastreamstopology` as required.
- [ ] Protected the topology endpoint with authentication/authorization.
- [ ] Enabled the binder health indicator.
- [ ] Restricted health details to authorized users.
- [ ] Separated client state, thread state, and task assignment on dashboards.
- [ ] Tagged metrics by application ID, thread, task, processor node, and store.
- [ ] Chosen an appropriate default recording level; enable `debug`/`trace` only when needed.
- [ ] Included process, poll, commit, and record end-to-end latency metrics.
- [ ] Included state store put/get/restore and iterator lifecycle metrics.
- [ ] Included RocksDB I/O, cache, compaction, and write-stall metrics if using RocksDB.
- [ ] Understood `num-keys` applies only to in-memory state stores.
- [ ] Monitored consumer lag, changelogs, and brokers.
- [ ] Defined alert thresholds based on baselines and sustained durations.
- [ ] Tested the topology endpoint, health, metrics, and state restoration.

Monitoring Kafka Streams in Spring Cloud Stream requires combining topology descriptions, runtime health, and metrics. The `kafkastreamstopology` endpoint reveals processor structure; the health indicator tracks stream threads and tasks; and Micrometer with Kafka Streams metrics measures throughput, latency, commits, restoration, state stores, and RocksDB. Preserving tags for application ID, thread, task, and store enables operators to isolate slow processors or state stores, distinguish normal rebalances from prolonged failures, and build alerts grounded in real baselines.

## References

- [Spring Cloud Stream 5.0.3 — Kafka Streams Binder: Health Indicator and Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/accessing-metrics.html)
- [Spring Cloud Stream — Kafka Streams Topology Visualization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/topology-visualization.html)
- [Spring Cloud Stream — Kafka Streams Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Apache Kafka 4.4 — Monitoring Kafka Streams](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 — KafkaStreams.State API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/KafkaStreams.State.html)
- [Apache Kafka 4.4 — Running Streams Applications](https://kafka.apache.org/44/streams/developer-guide/running-app/)

# Records processed and records failed

In **Spring Kafka Reliability Operations**, two questions typically arise first during an incident: **how many records succeeded?** and **how many records failed?** Both figures must be measured precisely because a Kafka consumer can read a record while the listener fails, a single record can be retried multiple times, or business work can finish while the offset fails to commit and the record gets redelivered.

**Records processed** and **records failed** are not built-in Kafka broker metrics with one universal meaning for every application. They are monitoring concepts tied to a specific **measurement point**: Kafka fetch, listener invocation, business transaction, offset commit, or DLT recovery. If dashboards mix these measurement points, a system losing processing capacity can look healthy, or a self-healing retry can look like dozens of broken records.

This lesson explains how to define and instrument these metrics with Micrometer/Spring Kafka, distinguish transient errors from terminal failures, observe them in Prometheus, calculate rates, correlate with lag, and follow operational runbooks.

## 1. What states does a record pass through?

~~~mermaid
flowchart TD
    A[Producer publish] --> B[Kafka topic/partition]
    B --> C[Consumer poll/fetch]
    C --> D{Deserialize succeeded?}
    D -->|No| E[Deserialization error handler]
    D -->|Yes| F[Spring Kafka listener]
    F --> G{Business succeeded?}
    G -->|Yes| H[Listener returns]
    G -->|No| I[Listener throws exception]
    I --> J[Error handler or transaction rollback]
    J -->|Retry| F
    J -->|Retries exhausted| K[Recoverer / DLT]
    H --> L[Offset commit per AckMode/transaction]
    K --> M[Offset advances per recovery policy]
    E --> J
~~~

Each step yields a different type of metric:

| Measurement point | Logical metric | Meaning |
|---|---|---|
| Kafka broker | Produced/appended records | Broker recorded data written to the topic. |
| Kafka consumer | Consumed/fetched records | Client read the record; does not confirm processing succeeded. |
| Listener | Processing attempts | Number of times listener was called, including retries/redeliveries. |
| Listener | Successful attempts | Number of times the method returned normally per contract. |
| Listener | Failed attempts | Number of times the method threw an exception. |
| Business | Business applied | New business effect durably committed. |
| Idempotency | Duplicate suppressed | Previously seen event redelivered without reapplying side effects. |
| Recovery | Terminal failure | Record exhausted retries or is non-retryable and entered error handling. |
| Kafka group | Committed offset | Position where the consumer group will resume after restart. |

Never use a single counter named `records_processed` to represent the entire flow. The **metric contract** must state clearly whether success means listener level, business transaction level, or offset commit level.

## 2. Defining records processed accurately

A practical listener-level metric definition is:

> `records_processed` = number of times the listener processes a record and returns normally without throwing an exception.

Pros: easy to instrument, easy to calculate throughput and compare against failed attempts. Cons: the result does not prove the Kafka offset committed, does not prove a Kafka transaction committed, and does not guarantee a **unique** business effect.

For example, record `evt-123` is processed successfully and the database commits, yet the pod crashes before offset commit. When a new pod receives the same offset again, the listener can return normally a second time. `records_processed` increases by **two**, even though there was only **one** business event.

For services needing to count newly applied events, use separate metrics:

- `records_business_applied`: event produced a new business effect.
- `records_duplicate_suppressed`: event detected as already processed, no repeat effect created.
- `records_business_rejected`: event rejected by business rules, yet the listener handled the rejection state successfully.

**Business rejection is not necessarily a Kafka processing failure.** For instance, a transaction declined for exceeding a limit is a valid outcome; a listener persisting `REJECTED` successfully can still count as processed.

## 3. Defining records failed accurately

A record can fail multiple times yet eventually succeed. Therefore, separate:

| Logical metric | When it increments | What it is used for |
|---|---|---|
| `records_failed_attempts` | Each time a listener invocation throws an exception | Detecting retry storms, infrastructure errors, attempt failure ratio. |
| `records_terminally_failed` | Retry policy finishes without business processing succeeding | Counting record-level failure outcomes, not attempt counts. |
| `records_dlt_published` | DLT publish confirmed per producer send policy | Counting records durably handed off to the DLT. |
| `records_deserialization_failed` | Record failed before the listener was invoked | Capturing errors invisible to listener metrics. |
| `records_recovered_without_dlt` | Record recovered via another mechanism | Separating non-DLT recovery branches from DLT. |

`records_failed_attempts` is a **per-attempt** operational metric. Making `records_terminally_failed` meaningful **per unique record** requires identifying logical events across retry topics, replays, and duplicates. Never infer unique failed events simply by counting exceptions.

## 4. Example: five events yet ten listener invocations

Suppose:

- A succeeds on the first attempt.
- B fails twice, then succeeds on the third attempt.
- C fails four times, then goes to the DLT.
- D is a duplicate; the listener checks the inbox and returns normally without updating the database again.
- E succeeds on the first attempt.

| Event | Listener attempts | Failed attempts | Successful attempts | Newly applied | Duplicate | Terminal DLT |
|---|---:|---:|---:|---:|---:|---:|
| A | 1 | 0 | 1 | 1 | 0 | 0 |
| B | 3 | 2 | 1 | 1 | 0 | 0 |
| C | 4 | 4 | 0 | 0 | 0 | 1 |
| D | 1 | 0 | 1 | 0 | 1 | 0 |
| E | 1 | 0 | 1 | 1 | 0 | 0 |
| **Total** | **10** | **6** | **4** | **3** | **1** | **1** |

If a dashboard shows `failed_attempts=6`, that **does not mean six events broke**. Only event C ended at the terminal recovery branch. B recovered after retries.

If a dashboard shows `processed=4`, that does not mean four new business mutations either: D was merely a safely handled duplicate.

Always define the **denominator** and **unit of count** before reporting an error rate.

## 5. Metric naming conventions and labels

Example application conventions:

~~~text
app.kafka.records.processed
app.kafka.records.failed.attempts
app.kafka.records.business
app.kafka.records.terminally.failed
app.kafka.records.dlt.published
app.kafka.records.deserialization.failed
app.kafka.record.processing.duration
~~~

These are **custom application Micrometer metrics**, not Spring Kafka built-in metric names. With the Prometheus registry, they typically export as:

~~~text
app_kafka_records_processed_total
app_kafka_records_failed_attempts_total
app_kafka_records_business_total
app_kafka_records_terminally_failed_total
app_kafka_records_dlt_published_total
~~~

Exact names depend on naming conventions and registry versions. Always check `/actuator/prometheus` rather than assuming exported names match code strings literally.

### Recommended labels

| Label | Example value | Goal |
|---|---|---|
| `application` | `orders-service` | Distinguish applications. |
| `environment` | `production` | Distinguish environments. |
| `listener` | `orders-listener` | Isolate handlers. |
| `topic` | `orders.events` | Isolate data streams. |
| `consumer_group` | `orders-service` | Correlate with lag/assignments. |
| `outcome` | `applied`, `duplicate`, `rejected` | Categorize bounded business outcomes. |
| `error_category` | `validation`, `dependency_timeout`, `other` | View error groups instead of stack traces. |

### Labels to avoid

- `eventId`, `orderId`, `customerId`, request ID.
- Offsets, payloads, or verbatim exception messages.
- URLs with constantly changing query parameters.
- Freshly generated UUIDs per attempt or replay.

Those labels inflate **cardinality** enormously, straining memory and Prometheus queries. Put them in structured logs/traces instead. The `partition` label is bounded yet can multiply series on very large topics; add it only if partition-level metric analysis is genuinely needed.

## 6. Integrating Spring Boot Actuator and Micrometer

Common Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Illustrative configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: orders-service
      environment: production

spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

`/actuator/metrics` inspects metric names and tags in Actuator format; `/actuator/prometheus` exports data for Prometheus when the registry is installed and the endpoint is properly exposed. In production, enforce network controls, authentication, and authorization on monitoring endpoints. Never expose metrics endpoints publicly without access control.

### Which metric type fits?

- `Counter`: counts of processed records, failed attempts, DLT publishes, duplicates suppressed.
- `Timer`: listener record processing duration; provides both throughput/count and latency.
- `Gauge`: current values like in-flight work or queue size; do not use in place of event counters.

A `Counter` is an **in-process cumulative value** that resets on pod restarts. Dashboards should use `rate()`/`increase()` to inspect changes over time rather than treating the raw counter value as a reliable historical total.

## 7. Instrumenting a listener with Micrometer

Example listener processing single events and counting processed records, failed attempts, and business application outcomes.

~~~java
@Component
public class OrdersKafkaListener {

    private final OrdersService ordersService;
    private final MeterRegistry registry;

    public OrdersKafkaListener(
            OrdersService ordersService,
            MeterRegistry registry) {
        this.ordersService = ordersService;
        this.registry = registry;
    }

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "orders-service")
    public void onMessage(ConsumerRecord<String, OrderEvent> record) {
        long startedAt = System.nanoTime();
        String result = "failed";

        try {
            ApplyResult applyResult =
                    ordersService.applyIdempotently(record.value());

            registry.counter(
                    "app.kafka.records.processed",
                    "listener", "orders-listener"
            ).increment();

            registry.counter(
                    "app.kafka.records.business",
                    "listener", "orders-listener",
                    "outcome",
                    applyResult == ApplyResult.APPLIED
                            ? "applied" : "duplicate"
            ).increment();

            result = "processed";
        }
        catch (RuntimeException ex) {
            registry.counter(
                    "app.kafka.records.failed.attempts",
                    "listener", "orders-listener",
                    "error_category", classify(ex)
            ).increment();

            throw ex;
        }
        finally {
            Timer.builder("app.kafka.record.processing.duration")
                    .tags("listener", "orders-listener",
                          "result", result)
                    .register(registry)
                    .record(System.nanoTime() - startedAt,
                            TimeUnit.NANOSECONDS);
        }
    }

    private static String classify(RuntimeException ex) {
        if (ex instanceof BusinessValidationException) {
            return "validation";
        }
        if (ex instanceof DownstreamTimeoutException) {
            return "dependency_timeout";
        }
        return "other";
    }
}
~~~

`OrdersService`, `OrderEvent`, `ApplyResult`, `BusinessValidationException`, and `DownstreamTimeoutException` are application-defined types. Import `MeterRegistry`, `Timer`, `ConsumerRecord`, `TimeUnit`, Spring annotations, and business classes per your project.

The `processed` measurement sits right after the service call. If the service is a **separate Spring bean** whose database transaction commits before returning, this metric reflects database outcomes per invocation well. However, Kafka offsets/transactions typically commit **after** the listener returns. Therefore, this remains a **listener success counter**, not proof that the Kafka transaction committed.

### Why must exceptions be rethrown?

If a listener catches an exception, increments a failed metric, and neither rethrows nor performs valid recovery:

~~~java
try {
    ordersService.apply(event);
}
catch (Exception ex) {
    registry.counter("app.kafka.records.failed.attempts").increment();
    // Anti-pattern: merely log and return normally.
}
~~~

The container may treat the record as finished and commit the offset per `AckMode`, even though business processing failed. Incrementing a failure counter **does not replace** `DefaultErrorHandler` or transaction rollback.

Conversely, a valid business rejection can be persisted as a business outcome and return normally without throwing an exception.

## 8. Redelivered records: processed is not unique applied

An at-least-once scenario:

~~~text
T1: Consumer processes evt-17, writes DB successfully.
T2: Process crashes before committing Kafka offset.
T3: New consumer receives evt-17 again.
T4: Inbox detects event was already processed, skips side effect.
T5: Listener returns normally again.
~~~

If instrumented at the listener:

~~~text
records_processed += 2
records_business{outcome="applied"} += 1
records_business{outcome="duplicate"} += 1
~~~

Therefore, `business_applied` must be tied to durable business application results rather than method invocations alone. A common pattern is storing `eventId` with a unique constraint inside the same database transaction as the business state change. On redelivery, duplicates are caught before updating again.

If **exact long-term reconciliation** is required, the source of truth should be a business/audit table or durable event log. Prometheus counters are telemetry and can lose increments if a process dies before the next scrape.

## 9. Failed attempts and terminal failures live at different layers

When a listener throws an exception, `DefaultErrorHandler` can retry multiple times. Hence a `catch` block inside the listener may only count a **failed attempt**. The listener does not yet know whether the record will be retried, sent to DLT recovery, or succeed on the next attempt.

~~~mermaid
flowchart LR
    A[Listener throws] --> B[Failed attempt +1]
    B --> C[Error handler]
    C --> D{Retry again?}
    D -->|Yes| E[Re-deliver]
    E --> A
    D -->|No| F[Recoverer]
    F --> G{Recovery confirmed?}
    G -->|Yes| H[Terminal outcome +1]
    G -->|No| I[Recovery failure]
~~~

For example, `FixedBackOff(1000L, 3L)` permits three retries after the initial attempt per Spring `FixedBackOff` semantics. A single record can produce up to four failed attempts before the recoverer runs.

If recovery routes to the DLT, increment `records_dlt_published` only when the publish is **confirmed** per producer ack/send result policy. Depending on version, a recoverer may send asynchronously or support checking send results; returning from a method does not always equal durable persistence.

`records_terminally_failed` must also have an explicit contract: does it count each time a record reaches terminal recovery, or each **unique logical event**? With retry topics/replays, one event can pass through multiple topics, requiring correlation/event IDs to avoid double-counting.

### DLT is not business success

The record moves to the DLT and the source offset can advance per recovery policy. Consumer lag drops, yet the original business operation failed. Dashboards must separate `handled_by_recovery` from `business_applied`.

## 10. Errors occurring before the listener

Not every bad record enters the `@KafkaListener` method. Malformed payloads can make the deserializer throw an exception before the listener is called.

Consequently:

- Listener `records_failed_attempts` can stay at 0.
- The bad record can still stall the consumer or enter error-handler recovery.
- Consumer lag rises or DLT grows.
- Dashboards watching only listener `catch` blocks miss these errors entirely.

Spring Kafka provides `ErrorHandlingDeserializer` to pass deserialization errors into the error-handling path as configured:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": "com.example.orders.events"
~~~

This example illustrates the principle; configure type mappings and trusted packages per your contract. Never open `trusted.packages=*` indiscriminately in production.

To count deserialization failures, instrument the appropriate error-handler/recovery path. Do not merge deserialization errors with listener failed attempts if you want to analyze layers separately.

## 11. Kafka client metrics vs. listener metrics

The Kafka consumer client exposes metrics such as:

- `records-consumed-rate`, `records-consumed-total`.
- `bytes-consumed-rate`.
- `records-lag`, `records-lag-max`.
- Commit latency and poll metrics.

Exact names and export via JMX/Micrometer depend on Kafka client, Spring Boot, and registry versions.

Those metrics reflect **Kafka client fetch/poll/commit**, not business events processed. A consumer may fetch records ahead of listener processing; retries may redeliver the same record; records may be filtered or fail deserialization.

Never assume the equivalence:

~~~text
Kafka records consumed = records processed = unique business events applied
~~~

This equality rarely holds.

### Built-in Micrometer listener timers and observations

Spring Kafka supports Micrometer listener timers and Micrometer Observation in appropriate versions. Legacy timers can appear under names like `spring.kafka.listener` with result/exception tags depending on version.

Example container settings in supported Spring Kafka releases:

~~~java
factory.getContainerProperties().setMicrometerEnabled(true);
~~~

Or using Observation:

~~~java
factory.getContainerProperties().setObservationEnabled(true);
~~~

Verify the active API and behavior for your Spring Kafka version. When Observation is enabled, metrics/trace collection and naming can differ from legacy timers; do not enable both indiscriminately to avoid duplicate telemetry.

**Timer count is listener invocations**, not guaranteed record counts or unique business counts. For batch listeners, one invocation can carry hundreds of records. Inspect `/actuator/metrics` for exact metric/tag names instead of guessing.

## 12. Batch listeners: invocation count is not record count

With a batch listener:

~~~java
@KafkaListener(topics = "orders.events", batch = "true")
public void onBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        ordersService.applyIdempotently(record.value());
    }
}
~~~

If a batch has 100 records:

- Listener timer count may rise by only **1**.
- If each record succeeds, the record-level processed counter should rise by **100** per contract.
- If the 30th record fails, know whether the prior 29 committed or the transaction rolled back.
- If the batch exception does not pinpoint the failing position, the error handler may reprocess the whole batch.

`BatchListenerFailedException` in supported versions helps identify the failing index/record. Instrumentation must tie to actually completed records rather than incrementing for the whole batch upfront.

When a batch spans multiple partitions, offsets and progress must be managed per topic-partition. There is no single global offset for the whole batch.

## 13. Consumer concurrency and multiple pods

Spring Kafka `ConcurrentMessageListenerContainer` can spawn multiple consumer threads; Micrometer counters handle concurrent updates better than unsynchronized `long` variables.

Example:

~~~text
Pod A:
  Thread 1: processed 1,500
  Thread 2: processed 2,100

Pod B:
  Thread 1: processed 1,200
  Thread 2: processed 1,700

Total telemetry at observation time: 6,500
~~~

However, each pod's counters reset on restart. Prometheus dashboards should use `rate()`/`increase()` and sum by application/group/listener/environment so unrelated workloads are not mixed.

If metrics carry `instance` or `pod` labels, handle them explicitly when aggregating across the service. Never combine production and staging data or two consumer groups serving different business purposes.

## 14. Basic Prometheus queries

Suppose the application exports:

~~~text
app_kafka_records_processed_total{application="orders-service",listener="orders-listener"}
app_kafka_records_failed_attempts_total{application="orders-service",listener="orders-listener",error_category="dependency_timeout"}
app_kafka_records_dlt_published_total{application="orders-service",listener="orders-listener"}
~~~

### Successful listener attempts per second

~~~promql
sum by (application, listener) (
  rate(app_kafka_records_processed_total[5m])
)
~~~

### Failed listener attempts per second

~~~promql
sum by (application, listener) (
  rate(app_kafka_records_failed_attempts_total[5m])
)
~~~

### Breakdown by error category

~~~promql
sum by (application, listener, error_category) (
  rate(app_kafka_records_failed_attempts_total[10m])
)
~~~

### Failed attempt ratio across instrumented invocations

~~~promql
sum(rate(app_kafka_records_failed_attempts_total[5m]))
/
clamp_min(
    sum(rate(app_kafka_records_failed_attempts_total[5m]))
  + sum(rate(app_kafka_records_processed_total[5m])),
  0.001
)
~~~

This formula is valid only when every listener invocation falls into either **processed** or **failed attempt**, and both metrics share the same scope. It **excludes** pre-listener deserialization failures if uninstrumented, is not the unique terminal record failure rate, and becomes noisy at very low traffic.

### Terminal failures over one hour

~~~promql
sum by (application, listener) (
  increase(app_kafka_records_terminally_failed_total[1h])
)
~~~

### DLT publishes over one hour

~~~promql
sum by (application, listener) (
  increase(app_kafka_records_dlt_published_total[1h])
)
~~~

When multiple retry topics exist, design a `logical_pipeline` label or consistent mapping to aggregate an event across different listeners. If metrics are split by retry topic name, a single event can appear across multiple stages and get double-counted when trying to measure unique business outcomes.

## 15. Never divide failed by consumed to compute business failure rate

A common but flawed formula:

~~~text
failure_rate = listener_exceptions / kafka_records_consumed
~~~

Distortions arise from:

- A record being retried multiple times.
- The client fetching many records ahead of listener invocations.
- Pre-listener errors.
- Filtered or duplicate records.
- Batch listeners handling many records in one invocation.
- Retry topics emitting extra records on intermediate topics.
- Mismatched windows/labels between the two metrics.

If you need **terminal failure ratio per source event**, measure compatible outcomes:

~~~text
terminal_failure_ratio =
    unique_source_events_terminally_failed
    /
    (unique_source_events_applied
     + unique_source_events_terminally_failed)
~~~

The formula requires clearly defining event identity, time window, pending items, replays, and duplicates. For many applications, maintain **two dashboards**: technical processing attempts and business outcomes.

## 16. Processed rate must be read alongside consumer lag

A service with high processed throughput can still fall behind if producers write faster.

Example:

~~~text
Producer incoming rate:    1,000 records/sec
Successful attempts:         700 /sec
Failed attempts:              50 /sec
Consumer lag: rising
~~~

This example is illustrative, not an exact mathematical identity across all retry/transaction scenarios. Measure the actual **lag slope**.

| Processed | Failed attempts | Lag | Likely investigation target |
|---|---|---|---|
| High | Low | Shrinking | Consumer is catching up. |
| High | Low | Rising | Producer rate rose; consumer lacks capacity. |
| Falling | Rising | Rising | Listener errors or downstream timeouts. |
| Zero | Zero | Rising | Consumer stopped/paused, poll errors, deserialize errors, or missing metrics. |
| Zero | Zero | Zero | Possibly idle traffic; normal per schedule. |
| High | High | Rising | Retry storm burning time on repeated attempts. |
| Rising | Low | Steady, DLT rising | Recovery branch may be bypassing core business work. |

For a stuck partition, compare end offset, committed offset, assignments, and listener exceptions. High lag on one partition while others look normal points to poison pills, hot keys, or pauses.

## 17. How blocking retries and retry topics alter metrics

With `DefaultErrorHandler` blocking retries:

- One failing record can increment `failed_attempts` multiple times.
- Consumer threads can be held by backoff or processing.
- `processed` increments only when an attempt returns normally.
- Lag can rise during retries even if producers keep writing.

With `@RetryableTopic` non-blocking retries:

- Records move from the source topic to one or more retry topics.
- The source topic consumer can keep processing newer records.
- Listeners on retry topics can emit separate metrics.
- One logical event can span multiple invocations across different topics.
- Per-key ordering in the source topic may no longer hold across retry topics.

Never sum `processed` from the source topic and retry topics and call it **unique source events processed**. Define a contract for moving records to retry topics: it is a **handoff**, not business applied.

## 18. Kafka transactions: processed counter can increment before commit

In transactional consume–transform–produce, Spring Kafka can place Kafka outputs and input offsets into the same transaction. However, listener code runs **before the Kafka transaction commits**.

~~~text
1. Listener processes and calls KafkaTemplate.send().
2. Counter records_processed += 1.
3. Listener returns.
4. Container sends offsets to the transaction.
5. Kafka commit fails or producer is fenced.
6. Transaction aborts; input may be redelivered.
~~~

The metric in step 2 already incremented even though the Kafka output never committed. That is because it measures **listener return success**, not transaction committed.

If you need committed Kafka transaction counts, use transaction lifecycle instrumentation or Kafka producer/client metrics per version. Nor can you infer successful database operations from it, because Kafka transactions do not automatically span databases or HTTP calls.

For business effects outside Kafka, idempotency is mandatory on redelivery—even when using EOS for Kafka-to-Kafka processing.

## 19. Record filtering and business rejection

`RecordFilterStrategy` can drop records **before the listener runs**. Kafka consumer fetch metrics may rise while custom listener `processed` stays flat. If filtering is a valid branch, measure `records_filtered` at the filter layer per contract rather than treating filtered records as failed.

Similarly, a business event rejected by valid rules can produce:

~~~text
Input: PaymentRequested amount exceeds limit
Business outcome: REJECTED
Listener persists rejection state successfully
Kafka processing outcome: SUCCESS
~~~

To track business statistics, use `business_outcome=rejected` instead of throwing exceptions into pointless retries. Throw exceptions only when retry/recovery is the intended policy.

## 20. Per-partition monitoring

A topic can have a hot partition or a stalled partition while overall throughput stays high.

~~~text
payments.events
  P0: processed ~400/s, lag ~0
  P1: processed ~0/s,   lag ~30,000
  P2: processed ~380/s, lag ~0
~~~

To investigate P1:

1. Identify the current consumer owner of the partition.
2. Check poll health, pause status, and rebalances.
3. Compare committed offset vs. end offset over time.
4. Find exceptions and the retrying record offset.
5. Check the DLT recoverer if errors are permanent.
6. Measure processing duration and downstream latency.

Putting `partition` as a label on every custom metric can explode series counts. On large clusters, rely on Kafka group/client per-partition metrics for lag and offsets, while aggregating application counters by listener, topic, and error category.

## 21. Minimum production dashboard

| Panel | Metric | Operational meaning |
|---|---|---|
| Processing throughput | Successful listener invocations / sec | Whether listeners are active and at what rate. |
| Failed attempt rate | Failed listener invocations / sec | Whether errors/retries are rising or falling. |
| Attempt failure ratio | Failed / total instrumented attempts | Attempt health, not unique failure rate. |
| Terminal/DLT | DLT published, terminal recovered | Records failing business completion in the main flow. |
| Business outcome | Applied, duplicate, rejected | Actual business results. |
| Processing duration | p50/p95/p99 listener latency | Spotting bottlenecks and timeout risks. |
| Consumer lag | Group/topic/partition lag | Whether consumers are keeping up with data. |
| Group health | Member count, rebalances, assignments | Whether consumers remain active. |
| Poll health | Poll interval, non-responsive events | Detecting blocked threads or stalled polling. |
| Recovery backlog | Retry topic/DLT age and unresolved | Unfinished work accumulating. |

Name panels with unambiguous units. "Successful listener invocations" differs from "Unique business events applied"; "Failed attempts" differs from "Terminally failed records."

## 22. Alerting: never alert on a single counter alone

### Abnormal spike in failed attempts

Combine:
- Failed attempt ratio.
- Sufficiently large invocation count in the window.
- Sustained duration above threshold.
- Consumer lag and processing latency.
- Terminal failures/DLT.

A single error during a very low-traffic hour produces a 100% ratio without necessarily indicating an outage.

### Processed equals zero

Before alerting, verify whether the broker is receiving new records. If a topic normally carries traffic only during business hours, zero processed overnight can be normal. If producer ingress rises and lag grows while processed stays zero, that is a critical alert.

### DLT growing

This outcome requires an owner and replay policy. Steadily climbing DLT counts can be riskier than many failed attempts that recover on retry. Monitor unresolved record age and processing capacity before retention expires.

### Listener duration approaching max.poll.interval.ms

Long retries, downstream timeouts, and large batches can kick a consumer out of the group for exceeding `max.poll.interval.ms`. Duplicates, rebalances, and commit failures can surge; watch poll timing alongside processing duration.

## 23. Runbook: Sharp rise in failed attempts

1. Identify application, listener, topic, environment, and start time.
2. Check breakdown by `error_category`; pull representative stack traces from logs.
3. Correlate timing with deployments, schema changes, database/API timeouts, or broker incidents.
4. Inspect retry policy: attempt count, backoff, non-retryable exceptions.
5. Compare terminal failures/DLT against failed attempts to see if errors self-recover.
6. Check consumer lag, processing duration, and partitions with stalled offsets.
7. For permanent data errors, quarantine/DLT per policy instead of infinite retries.
8. For transient errors, fix the dependency and prevent retry storms.
9. Confirm failure rate drops and business/offset progress recovers.

Never skip offsets just to clear dashboard errors without business approval.

## 24. Runbook: Processed is zero and failed is also zero

1. Check producer ingress and broker end offsets; the topic may genuinely have no traffic.
2. Check group member count, partition assignments, and container running state.
3. Check consumer pause, rebalances, auth, and poll health.
4. Check pre-listener deserialization errors and `RecordFilterStrategy`.
5. Check whether the metrics endpoint/scrape target is still emitting data.
6. Compare committed offset, end offset, and lag per partition.
7. Fix the root cause and verify listener processing and offset progress.

**Having no failed metrics** does not prove every record succeeded; the listener may never have been called.

## 25. Runbook: Processed increases while lag keeps rising

1. Measure producer ingress rate and consumer processing rate over the same window.
2. Identify hot partitions and key distribution.
3. Check partition count vs. consumer concurrency.
4. Measure listener p95/p99 and downstream latency.
5. Check retry overhead or oversized batches.
6. Consider tuning concurrency, batching, backpressure, or optimizing business logic.
7. Never scale concurrency past partition count expecting one partition to process in parallel.
8. Monitor lag slope and terminal/DLT outcomes after changes.

## 26. Runbook: DLT increases while listener failed attempts stay low

1. Check which topic/listener DLT records come from and whether retry topics exist.
2. Check whether permanent errors go straight to recovery without retries.
3. Check whether deserialization errors occur before the listener.
4. Confirm custom counters instrument all retry listeners, not just the root listener.
5. Verify DLT send results were confirmed by the broker.
6. Check source offsets and recovery policies.
7. Add instrumentation on the error-handler/deserialize path so nothing is missed.
8. Prepare replay records and classify business errors appropriately.

## 27. Runbook: Processed spikes right after restart

1. Check consumer group rebalances, pod restarts, and before/after committed offsets.
2. Check for redeliveries of records already applied to the database.
3. Compare `processed`, `business_applied`, and `duplicate_suppressed`.
4. Check unique event ID/inbox constraints.
5. Reconcile Kafka offsets with transaction outcomes.
6. If duplicate side effects occurred, evaluate business compensation.
7. Do not treat replay spikes as new business traffic.
8. Use `rate()`/`increase()` rather than comparing cumulative counter totals across restarts.

## 28. Runbook: Prometheus queries stop returning data

1. Verify `/actuator/prometheus` is exposed and properly secured.
2. Check the Micrometer registry dependency and Actuator configuration.
3. Check whether the scrape target in Prometheus is still `UP`.
4. Check whether metric names changed across versions/naming conventions or when moving from Timer to Observation.
5. Check whether new labels broke query filters.
6. Check whether the listener has traffic to initialize counters; pre-register meters if needed.
7. Check pod labels and relabeling rules.
8. Distinguish **missing series** from zero-valued metrics; never treat missing data as healthy automatically.

## 29. Essential test scenarios for the metric contract

| Scenario | Processed | Failed attempts | Business applied | Terminal/DLT |
|---|---|---|---|---|
| First-attempt success | +1 | 0 | +1 | 0 |
| Retry fails twice then succeeds | +1 | +2 | +1 | 0 |
| Permanent exception to DLT | 0 | +1 if listener received record | 0 | +1 after recovery confirmed |
| Duplicate suppressed | +1 if listener returns normally | 0 | 0; duplicate +1 | 0 |
| Deserialize fails before listener | 0 at listener | 0 at listener | 0 | Per error-handler policy |
| DB commits then crash before Kafka offset | May re-process on redelivery | Depends | Only one effect if idempotent | Depends |
| Kafka transaction aborts after listener return | Processed may already be +1 | Not necessarily incremented | Depends on non-Kafka transaction | Per rollback policy |
| Batch of 100 records succeeds | +100 if instrumented per record | 0 | Depends on new events | 0 |

Unit tests can use `SimpleMeterRegistry` to check `Counter` and `Timer`; integration tests with Kafka are required to verify retries, deserialization, DLT, rebalances, and transactions. The scenarios in this lesson are guidelines, not test execution at STEP 4.

## 30. Control checklist for records processed and records failed

| Control point | Question to answer | Evidence |
|---|---|---|
| Semantics | Does `processed` mean listener return, business applied, or offset committed? | Metric contract and instrumentation. |
| Attempts | Does `failed` count each attempt or unique terminal records? | Retry policy and failure logs. |
| Coverage | Are pre-listener errors (deserialize/filter) captured? | Error-handler instrumentation. |
| Batch | How many records per invocation? | Batch listener and per-record metrics. |
| Duplicate | Do redeliveries increment `processed` without incrementing `business applied`? | Event ID and inbox counters. |
| Transaction | Does the counter increment before or after DB/Kafka commit? | Transaction boundaries and commit logs. |
| Recovery | Does the DLT metric increment only after confirmed publish? | Producer send result and recoverer configuration. |
| Labels | Are there high-cardinality labels? | Meter series count and tag policy. |
| Export | Are metrics visible on Actuator/Prometheus? | Endpoint and scrape status. |
| Aggregation | Do queries aggregate properly by environment, listener, group? | PromQL labels. |
| Performance | Is processing duration viewed alongside lag and throughput? | Dashboards, poll metrics. |
| Alerting | Are traffic thresholds and persistence windows configured? | Alert rules. |
| Business | Do terminal outcomes have an owner and replay SLA? | DLT/quarantine tickets, audit. |

**Conclusion:** The two metrics **records processed** and **records failed** accurately reflect Spring Kafka reliability only when defined against an explicit boundary. Measure **successful listener invocations**, **failed attempts**, **business events applied**, **duplicates suppressed**, and **terminal recovery/DLT** separately. Use Micrometer counters and timers alongside Kafka client/group metrics, without confusing listener success with offset commits or business exactly-once. Combining these signals with consumer lag, retry policies, partition assignments, and business SLAs enables dashboards to pinpoint incidents, quantify impact, and confirm safe recovery.

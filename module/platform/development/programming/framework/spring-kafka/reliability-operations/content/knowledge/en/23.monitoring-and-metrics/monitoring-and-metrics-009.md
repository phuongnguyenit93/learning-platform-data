# Producer send latency

In Spring Kafka, the producer is responsible for serializing records, batching them, and sending data to Kafka brokers. A call to `KafkaTemplate.send(...)` usually returns very quickly because sending is **asynchronous**. Yet the method returning does not mean Kafka has received the record, persisted it durably, or made it readable by downstream consumers. To operate a reliable system, you must accurately measure **producer send latency** across distinct boundaries, find the root cause when latency rises, and assess its impact on business SLAs.

Producer send latency in this lesson refers to the duration a record takes from when the application begins sending until the Kafka producer reports the send outcome, while distinguishing it from producer queue wait time, broker request latency, Kafka transaction commit duration, and end-to-end latency to consumers.

This lesson sits in the **Monitoring and metrics** chapter of **Spring Kafka Reliability Operations**. It uses Spring Boot, `KafkaTemplate`, Kafka producer client metrics, JMX, and Micrometer, along with production incident investigation runbooks.

## 1. A single send has multiple timestamps

Typical flow when an application invokes the producer:

```text
Application                       Kafka producer                    Broker
    |                                    |                             |
 t0 | KafkaTemplate.send(key, value)     |                             |
    +----------------------------------->| serialize / pick partition  |
    |                                    | fetch metadata / buffer     |
 t1 | <---- CompletableFuture returned --+                             |
    |                                    | queue / linger / batch      |
    |                                    | sender thread               |
    |                                    +----- ProduceRequest ------->|
    |                                    |                             | write log /
    |                                    |                             | check acks
    |                                    |<------ ProduceResponse -----+
 t2 | <--- future completes / callback --|                             |
    |                                                                  |
 t3 | (if transactional) commitTransaction() completes                 |
    |                                                                  |
 t4 | (if end-to-end) downstream consumer processes record             |
```

The measurement intervals mean different things:

| Interval | Interpretation | When to use? |
|---|---|---|
| **t1 − t0** | Duration of `send()` before receiving the future. May include serialization, metadata lookup, or buffer wait. | Detect `send()` calls blocking application threads. |
| **t2 − t0** | Time from when the application starts sending until the future succeeds/fails. | Measure application-level producer acknowledgment/completion latency. |
| **t3 − t0** | Time until the transaction commits, if using Kafka transactions. | Evaluate completion latency of transactional publishes. |
| **t4 − t0** | Time from emission until downstream processes it. | Measure end-to-end latency; requires clear traces and timestamps. |

These are **logical** milestones. Not every record uses transactions; not every successful send has the same durability level because `acks` may differ. With `acks=0`, a completed future is not proof the broker received the record.

**Core point:** when someone says "send latency increased," ask whether they are measuring **`send()` call latency**, **future completion time**, **Kafka request latency**, or **transaction commit latency**. Mixing these metrics leads to wrong root-cause diagnoses.

## 2. KafkaTemplate.send() is asynchronous

A listener or REST service might send events like this:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {

        return kafkaTemplate.send("orders.created", orderId, payload);
    }
}
```

In modern Spring Kafka versions (3.x), `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K, V>>`. The future completes successfully or exceptionally, typically after the producer receives the result per `acks` and retry policies.

```java
publisher.publish(orderId, payload)
        .whenComplete((result, exception) -> {
            if (exception == null) {
                log.info(
                    "Kafka send completed: topic={}, partition={}, offset={}",
                    result.getRecordMetadata().topic(),
                    result.getRecordMetadata().partition(),
                    result.getRecordMetadata().offset());
            } else {
                log.error("Kafka send failed: orderId={}", orderId, exception);
            }
        });
```

If the application only measures:

```java
long start = System.nanoTime();
kafkaTemplate.send("orders.created", orderId, payload);
long duration = System.nanoTime() - start;
```

then `duration` mainly reflects **enqueue time** rather than when the broker acknowledged the record. In some cases `send()` can also block waiting for metadata or producer buffer space, so enqueue time is not always near zero.

**Do not call `get()` or `join()` on the future in every listener/request just to collect a metric.** Doing so turns an asynchronous flow synchronous, ties up application threads, and causes unwanted backpressure. When business logic truly must wait for send success, set a bounded timeout and explicit error-handling rules rather than blocking indefinitely.

## 3. Measuring send completion latency at the application layer

To measure from `t0` to `t2`, start a timer **before** calling `KafkaTemplate.send(...)` and stop it when the future completes. Example with Micrometer:

```java
@Component
public class MeteredOrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MeterRegistry registry;

    public MeteredOrderPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String payload) {

        Timer.Sample sample = Timer.start(registry);
        try {
            return kafkaTemplate
                    .send("orders.created", orderId, payload)
                    .whenComplete((result, failure) -> {
                        String outcome =
                                failure == null ? "success" : "failure";

                        sample.stop(registry.timer(
                                "app.kafka.producer.send.completion",
                                "topic", "orders.created",
                                "outcome", outcome));
                    });
        } catch (RuntimeException failure) {
            // Some errors can occur before a future is returned.
            sample.stop(registry.timer(
                    "app.kafka.producer.send.completion",
                    "topic", "orders.created",
                    "outcome", "failure"));
            throw failure;
        }
    }
}
```

Key imports:

```java
import java.util.concurrent.CompletableFuture;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;
```

The `app.kafka.producer.send.completion` metric in this example is an **application-defined metric**, not a mandatory standard name from Kafka or Spring Kafka. It measures from before calling send until the future completes or the call throws synchronously.

Notes:

- `whenComplete` can run on the producer callback thread. Keep callbacks to lightweight metrics/logging; never call databases or slow APIs.
- When a future finishes with an error, still record the timer; recording only successes skews histograms and hides outages.
- Environments lacking a `MeterRegistry` bean must omit the Micrometer piece or configure the proper dependency.
- Never attach `orderId`, payload, or event ID as metric tags: cardinality can grow without bound.
- `topic` and `outcome` are suitable tags when topics are bounded; multi-tenant systems with dynamic topics need cardinality controls.
- If `KafkaTemplate` observation is already enabled, avoid double-instrumenting histograms with identical meanings unless clearly differentiated.

Timer metrics typically support count, total time, and latency distributions when the registry enables histograms or percentiles. For p95/p99 aggregated across multiple pods, prefer server-side histograms suited to your observability backend; client-side quantiles do not always aggregate accurately across instances.

## 4. Built-in Micrometer and observation in Spring Kafka

Spring Kafka supports Micrometer timers and, in modern versions, **Micrometer Observation** for `KafkaTemplate`. Enabling observation with a suitable `ObservationRegistry` lets you track sends via observations/timers and correlate traces.

Example enabling observation on a template when configured manually:

```java
@Bean
KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

This example assumes the application already has Micrometer Observation/`MeterRegistry` or tracing infrastructure. If Spring Boot auto-configures the template and observation, there is no need to declare a new bean just to flip one flag; check actual configuration and version in use.

A common convention name for `KafkaTemplate` observation is `spring.kafka.template`, though exact meter names, tags, trace spans, and metric/observation behavior depend on Spring Kafka, Spring Boot, and registry export versions. Do not guess exact Prometheus series from Java API names; inspect the actual metrics emitted by your application.

Distinguish two layers:

| Measurement source | Description | Limitation |
|---|---|---|
| Application timer / `KafkaTemplate` observation | Send latency seen from application code. | Does not break out queue, broker request, network, and replication shares individually. |
| Kafka producer client metrics | Timing/throughput at the Kafka client layer such as queue, request, retries, buffer. | Does not directly measure full HTTP → downstream consumer business flows. |

Use both layers together to **correlate symptoms and root causes**, rather than staring at one generic latency chart.

## 5. Producer request latency does not equal send completion latency

The Kafka producer emits metrics via JMX/Kafka client metrics. Several key producer metrics:

| Common client metric | Operational meaning |
|---|---|
| `request-latency-avg` / `request-latency-max` | Average/maximum request response time measured by the producer; not the entire time from `send()` to future completion for a single event. |
| `record-queue-time-avg` / `record-queue-time-max` | Time records wait in the producer accumulator before being sent. |
| `record-send-rate` | Rate at which the producer sends records; reflects load and throughput. |
| `record-retry-rate` | Rate of records retried due to retryable errors. |
| `record-error-rate` | Rate of failed record sends. |
| `batch-size-avg` / `batch-size-max` | Sizes of sent batches, useful for analyzing `linger.ms` and batching efficiency. |
| `records-per-request-avg` | Average records per request, an indicator of batching efficiency. |
| `bufferpool-wait-ratio` / `bufferpool-wait-time-total` | Buffer wait levels, revealing internal producer backpressure. |
| `waiting-threads` | Threads currently waiting for buffer allocation at measurement time. |
| `buffer-available-bytes` | Available buffer capacity per Kafka client. |
| `produce-throttle-time-avg` / `produce-throttle-time-max` | Duration the producer was throttled by broker/quotas, in clients/versions exposing this metric. |

Metric names and availability can vary across Kafka client versions; JMX exporters and Micrometer may **rename or normalize dots/hyphens**. This table lists common Kafka client metrics, not a guarantee that every series exists out of the box in Prometheus.

A simple path to understand the difference:

```text
KafkaTemplate.send()
       |
       +-- Metadata lookup / serializer / buffer allocation
       |
       v
Producer accumulator
       |
       +-- record-queue-time
       |
       v
Sender thread / ProduceRequest
       |
       +-- request-latency
       |     (network + broker + response per client definition)
       |
       v
Producer callback / future completion
       |
       +-- application send completion latency
```

With retries, a single record can traverse **multiple requests**, wait multiple times, and incur backoff. Thus, never mechanically add `record-queue-time-avg + request-latency-avg` to claim exact per-record latency. Both numbers are averages over different observation sets.

## 6. Reading Kafka client metrics via JMX

The Kafka producer exposes metrics keyed by Kafka `client.id`. JMX ObjectNames typically look like:

```text
kafka.producer:type=producer-metrics,client-id=order-producer-1
```

Common attributes in this object:

```text
request-latency-avg
request-latency-max
record-queue-time-avg
record-retry-rate
record-error-rate
record-send-rate
bufferpool-wait-ratio
waiting-threads
```

Per-topic metrics typically live under `producer-topic-metrics`, tagged with the matching client ID and topic. If a service publishes to multiple topics, producer-wide aggregation can hide which topic drives heavy load; combine per-topic metrics with application context.

In Kubernetes, you can export Kafka client metrics via Micrometer or a JMX exporter per organizational policy. When configuring exporters, verify:

- The actual `client.id` of the Kafka producer.
- Pod/instance, namespace, and service labels to identify sources.
- JMX metric name mappings to Prometheus series.
- Number of client IDs/topics, avoiding high label cardinality.
- Scrape intervals and rate windows that are sufficiently stable.

**Never treat `request-latency-avg` as an end-to-end p99 histogram.** It is a client-level aggregate; for p95/p99 send completion, use a histogram or timer at the send operation layer with proper export config.

## 7. linger.ms, batch.size, and the producer queue

Kafka producers normally batch multiple records before sending to raise throughput and cut request overhead.

Two key settings:

- `linger.ms`: maximum time the producer can wait to accumulate more records when a batch is not yet full.
- `batch.size`: memory size target per batch per partition, not an absolute limit on a single Kafka message's size.

Example:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[linger.ms]": 5
        "[batch.size]": 32768
```

At low throughput, records may wait close to `linger.ms` before the sender dispatches the batch. At high throughput, batches fill early so records do not always wait the full `linger.ms`.

```text
Record 1 arrives at 00 ms
Record 2 arrives at 02 ms
Record 3 arrives at 04 ms
           |
           v
Sender dispatches batch at the appropriate time
           |
           v
Broker acknowledges batch
```

Raising `linger.ms` can improve batching and throughput at the cost of higher latency for sparse traffic. Lowering `linger.ms` cuts queue wait for sporadic records while increasing request count and overhead, especially at high throughput.

When `record-queue-time-avg` rises, inspect **`batch-size-avg`**, **`records-per-request-avg`**, request rate, and broker load **together**. Never declare "Kafka is slow" from producer queue time alone, since queues grow intentionally under batching policies.

## 8. buffer.memory, max.block.ms, and blocked send calls

The Kafka producer keeps a buffer holding records before the sender thread turns them into `ProduceRequest` calls. If send rate falls below the application's record creation rate, the buffer fills up.

Relevant settings:

| Property | Role |
|---|---|
| `buffer.memory` | Approximate total memory for producer records waiting to be sent; not the client's entire RAM. |
| `max.block.ms` | Maximum time `send()` or equivalent operations can block waiting for metadata or buffer space, per Kafka client rules. |
| `batch.size` | Target capacity per batch per partition. |
| `linger.ms` | Wait interval to accumulate more records before sending. |

Example when the broker responds slowly:

```text
Application produces 10,000 records/second
      |
      v
Producer enqueues records
      |
      v
Sender can only dispatch 4,000 records/second
      |
      v
Buffer utilization climbs steadily
      |
      v
send() calls start blocking on buffer space
      |
      v
May hit TimeoutException due to max.block.ms
```

Here, `t1 − t0` rises because callers must wait, even though `send()` is still invoked asynchronously for the publish itself.

**Distinguish two timeouts:** `max.block.ms` governs waiting inside the API call (e.g., metadata/buffer); `delivery.timeout.ms` governs completing record delivery after it has been accepted. Time spent inside custom serializers or partitioners may follow different timeout rules and is not bounded by `max.block.ms`.

The fix is not raising `buffer.memory` indefinitely. Larger buffers only delay when overload surfaces and increase memory pressure. Address why throughput dropped, or apply **backpressure** at the source to slow down emission.

## 9. request.timeout.ms, delivery.timeout.ms, and retries

A record may not be acknowledged on the first request due to broker/network timeouts, leader elections, or transient faults. The Kafka producer retries according to configuration.

| Setting | Meaning |
|---|---|
| `request.timeout.ms` | Maximum time the client waits for a single request response per Kafka producer rules. |
| `delivery.timeout.ms` | Upper bound on total time the client tries to finish delivering a record, covering batching, requests, and retries per client semantics. |
| `retries` | Number of times the client may retry retryable errors, bounded by delivery timeout. |
| `retry.backoff.ms` | Wait interval between retries. |
| `acks` | Required broker acknowledgment level. |

Normally `delivery.timeout.ms` must be no smaller than `request.timeout.ms + linger.ms` to avoid invalid configs or premature delivery timeouts.

Illustrative configuration:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[linger.ms]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
        "[retry.backoff.ms]": 100
        "[enable.idempotence]": true
```

This is **not optimal for every SLA**. If an application must respond within 200 ms, a future waiting tens of seconds before failing violates end-to-end requirements; choose fail-fast, queueing, async APIs, or an outbox according to business needs.

If `record-retry-rate` rises alongside `request-latency-avg` and send completion p99, suspect the producer is retrying many requests. Find the server/network/quota cause before slashing retries, since cutting retries can raise failure rates and compromise event durability if the app lacks recovery.

## 10. acks and durability latency

`acks` affects both acknowledgment guarantees and latency:

| `acks` | What does send success reflect? | Trade-off |
|---|---|---|
| `0` | Producer does not wait for broker acknowledgment for the record. | Reported completion latency may be low, with no confirmation the broker wrote it. |
| `1` | Leader broker acknowledges per producer send behavior. | Risk of loss if the leader fails before replicas catch up. |
| `all` | Leader waits for acknowledgments from in-sync replicas per Kafka policy. | More durable under proper replication settings; latency can rise when replicas lag. |

With `acks=all`, check broker/topic `min.insync.replicas` and `replication.factor`. If ISR shrinks below the required threshold, the producer can receive errors instead of continuing writes at unacceptable durability.

**Never lower `acks` just to make latency charts look prettier** when business requires confirmed durable persistence in Kafka. Changing `acks` alters **delivery semantics**, not just performance tuning.

Kafka's idempotent producer is typically essential for curbing duplicates from client retries under supported Kafka conditions. With transactional producers, distinguish send future completion from **`commitTransaction()` completion**; a successful send before commit does not prove the transaction was confirmed.

## 11. Transactional producers: send latency is not transaction latency

In a Kafka transaction, a listener or service may send multiple records and then commit:

```text
beginTransaction()
      |
      +--> send(record A) -> future A completes
      +--> send(record B) -> future B completes
      |
      v
commitTransaction()
      |
      v
Transaction actually committed
```

If the broker aborts the transaction or commit fails, outputs are not visible to `read_committed` consumers, even though earlier `send()` futures completed successfully.

Therefore, transactional flows must measure at least:

- Send completion latency for records.
- `commitTransaction()` duration and commit/abort counts.
- Transaction timeouts, fencing, and producer epoch errors.
- Consumer lag and downstream visibility when the producer sits in a Kafka-to-Kafka pipeline.

If the application uses Spring Kafka's `KafkaTransactionManager` with a listener, transaction duration can include business processing and adding consumer offsets to the transaction. Never equate transaction duration with the producer's `request-latency-avg`.

## 12. Network, broker, and quota throttling

Producer request latency can rise even while application CPU stays low. When suspecting broker/network issues, inspect metrics on both sides:

| Symptom | Hypothesis | What to check |
|---|---|---|
| `request-latency-avg` rises across multiple producers simultaneously | Slow network, slow broker responses, quotas, or leader bottleneck. | Broker request latency, network throughput, CPU/disk, and quota throttling. |
| `produce-throttle-time-avg` rises | Client hit throughput quotas. | Kafka quotas, client/user byte rates, and broker metrics. |
| Only one topic shows abnormal latency | Hot partition/leader, replication, or different batch size. | Topic-partition distribution, leaders, ISR, record size. |
| Retry rate rises after broker rolling restart | Leader elections, metadata refreshes, or transient errors. | Broker logs, partition leader state, retry/error metrics. |
| Latency rises alongside ISR churn | Replica lag or replication bottleneck. | Under-replicated partitions, ISR changes, disk/network. |
| Latency rises while broker metrics stay steady | Producer buffer, DNS/TLS, serializer, or blocked app threads. | Buffer pool, send enqueue timing, thread dumps, client logs. |

If the broker enforces quotas, lowering `linger.ms` may not improve latency; more small requests can worsen it. Examine **total bytes sent**, request count, throttle time, and cluster capacity policies.

For topics with a hot partition, producer throughput can be bottlenecked by that partition's leader. Adding producer pods will not automatically raise write capacity to that same hot partition; evaluate key distribution, partition counts, and business ordering.

## 13. Record size, compression, and serializers

Large messages, heavy compression, or CPU-expensive serializers can increase send latency at different stages.

- **Serializer:** runs on the send call path to convert keys/values to bytes; a slow serializer increases `t1 − t0`.
- **Compression:** producers spend CPU compressing batches while reducing bytes sent over the network and stored on brokers.
- **Record size:** large records raise request sizes, buffer pressure, and risk exceeding `max.request.size` or broker/topic message limits.
- **Batching:** larger batches improve efficiency when sending many records at once, yet affect accumulation time and memory usage.

Example:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[compression.type]": zstd
        "[batch.size]": 65536
```

This is an illustrative configuration; verify compatibility with your Kafka version and producer CPU headroom. Never pick compression solely by compression ratio; measure **producer CPU, bytes sent, queue time, request latency, and send completion latency** afterward.

If latency rises only for very large payloads, investigate size distributions, serializers, compression CPU, request/response sizes, and broker message limits before tuning retries.

## 14. Example SLO and alert definitions

Suppose the `orders.created` publish stream has an internal target:

```text
Under normal broker operation:
  send completion p95 under 150 ms
  send completion p99 under 500 ms
  send failure rate under 0.1%
```

These thresholds are **examples**, not Kafka defaults. Financial transaction events have different durability and latency budgets than non-critical telemetry or logs.

A useful dashboard can be divided into:

1. **Golden signals:** application-measured p50/p95/p99 send completion latency and failure rate.
2. **Producer internals:** `request-latency`, `record-queue-time`, buffer waits, retries, throttling, and byte/record send rates.
3. **Broker:** Produce request latency, errors, ISR, disk/network, quota throttling.
4. **Business:** API request latency, event backlog/outbox age, and downstream processing lag.

Instead of alerting on a few seconds of p99, require sufficient sample volume and an observation window to avoid noise during very low traffic. During partial failures, the latency of **successfully completed futures** may look normal while many records fail; always watch failure rates alongside latency.

For transactional systems, add transaction commit/abort metrics. If business events use an outbox, monitor **oldest unpublished outbox record age** alongside producer send latency, since the producer might be fast while the outbox worker is stalled.

## 15. Diagnosing via a symptom matrix

| Scenario | Typical metrics | Likely cause | Investigation path |
|---|---|---|---|
| `send()` returns slowly at caller | Enqueue duration, `bufferpool-wait`, or metadata timeouts rise. | Exhausted buffer, metadata lookup, slow serializer. | Thread dumps, buffer metrics, producer configs, broker metadata. |
| Future is slow, queue time is high | `record-queue-time` rises while request latency looks normal. | Linger/batching, sender falling behind, producer buffer backlog. | `linger.ms`, batch size, sender throughput, request rate. |
| Future is slow, request latency is high | `request-latency` rises. | Broker/network/throttling/replication. | Broker request metrics, ISR, quotas, network. |
| Future is slow, retries surge | `record-retry-rate` and error rate rise. | Transient produce errors, leader elections, request timeouts. | Client exceptions, broker events, delivery timeout. |
| p99 rises only on large payloads | Record/request size, compression CPU rise. | Serialization, compression, or network size. | Payload distribution, profiler, compression config. |
| Transaction commit is slow while send futures are fast | Transaction duration rises while send time barely changes. | Coordinator, commit, long transactions. | Transaction manager, timeouts, producer fencing. |
| Kafka latency is low yet API is slow | Kafka timer normal; DB/HTTP latency rises. | Bottleneck outside the producer. | Request traces, dependency metrics, thread pools. |
| Downstream lag rises despite fast sends | Producer publishes steadily; consumer lag grows. | Consumer processing slowly or paused. | Group assignments, committed offsets, retries/DLT. |

**Diagnose by correlated trends**, never treating a single metric as conclusive. High queue time may be intentional batching, and high request latency may stem from quotas rather than a "weak" broker.

## 16. Runbook: Producer send latency rises after deployment

Suppose after deploying a new version, `app.kafka.producer.send.completion` p99 jumps from 120 ms to 1.2 seconds.

**Step 1 — Verify the metric.** Does p99 measure send-to-future or only `send()` call time? Did metric instrumentation or histogram buckets change in the deploy?

**Step 2 — Isolate scope.** One instance, one topic, or the whole application? Slice by producer client ID, topic, region, and deploy timestamp. Check sample volume to avoid overreacting to tiny sample counts.

**Step 3 — Correlate producer internals.** Inspect `record-queue-time`, `request-latency`, buffer wait, retries, errors, throttling, and records-per-request. Which moved simultaneously with p99?

**Step 4 — Diff configurations.** Did the release change `linger.ms`, `batch.size`, `acks`, `compression.type`, `delivery.timeout.ms`, serializers, record sizes, or the producer factory?

**Step 5 — Check brokers.** Were there rolling restarts, leader elections, ISR shrinks, quotas, disk/network pressure, or broker request latency spikes at the same time?

**Step 6 — Assess business impact.** How many futures failed? Did APIs time out or transactions abort? Is outbox backlog growing? Is consumer lag affected?

**Step 7 — Remediate in a controlled way.** If caused by a config deploy, roll back or apply a targeted adjustment; if capacity-driven, throttle emission and address broker/quota limits. Do not change too many producer parameters simultaneously, which obscures root cause.

**Step 8 — Verify recovery.** Send completion p95/p99 drops, failure/retry rates stabilize, brokers show no anomalies, business backlogs shrink, and no unexpected duplicates appear.

Never reset consumer offsets, purge DLTs, or switch to `acks=0` just to make producer dashboards look good.

## 17. Runbook: Producer buffer full or TimeoutException

Symptoms: `TimeoutException` logs when `send()` waits on metadata/buffer, application threads block, `bufferpool-wait-ratio` climbs, or threads wait on buffer space.

Procedure:

1. Check send enqueue duration to confirm application threads are blocking **before the future is returned**.
2. Check `buffer-available-bytes`, `waiting-threads`, `bufferpool-wait-ratio`, and total record/byte rates.
3. Check producer request latency and broker throughput: is the sender slow due to network/quotas or sheer record volume?
4. Check for unusual traffic spikes, payload sizes, hot partitions, and batching/compression changes.
5. Throttle at the source: bounded queues, rate limiting, semaphores, or proper backpressure, avoiding unbounded in-app buffers.
6. Increase `buffer.memory` only after sizing heap/native memory and confirming brokers can absorb the real load.
7. Check error-handling code: if `send()` throws synchronously, never assume a future exists for callbacks to handle.
8. After recovery, confirm buffer pressure drops, send latency normalizes, and error rates resolve.

**Never retry `send()` in a tight infinite loop** while the buffer is full; each retry contends for resources and amplifies load.

## 18. Runbook: request latency rises due to brokers or quotas

If `request-latency-avg` rises across multiple producers simultaneously:

1. Check Produce request latency on brokers, request handler idle ratio, disk I/O, and network.
2. Check quotas/throttles per client/user; did `produce-throttle-time` increase?
3. Check leaders/ISR of hot partitions, under-replicated partitions, and recent leader elections.
4. Correlate producer retries/errors; if `NotEnoughReplicas` or leader errors appear, do not hastily enlarge buffers.
5. Verify whether clients require `acks=all`, min ISR, and matching replication factors.
6. Reduce peak publish rates or expand capacity/quotas following approved operational procedures.
7. Watch broker metrics and producer completion latency recover together.

A Kafka cluster that looks healthy on aggregate dashboards can still have **one hot partition leader**. Drill down by topic/partition, key distribution, and broker leader placement.

## 19. Common misconceptions

| Misconception | Accurate interpretation |
|---|---|
| "`KafkaTemplate.send()` returns fast, so brokers confirm fast." | The method usually returns an async future; measure through future completion. |
| "`request-latency-avg` is end-to-end latency from app to consumer." | It is a Kafka producer client metric for requests, excluding the full business flow. |
| "Increasing `linger.ms` always raises latency proportionally." | Batches can fill before linger expires; inspect actual throughput and queue time. |
| "Increasing `buffer.memory` permanently fixes a slow producer." | It only adds temporary buffering; if input > output long-term, the buffer fills again. |
| "Future success means the transaction committed." | For transactional producers, send result differs from transaction commit. |
| "`acks=0` is a safe optimization for critical events." | It drops broker acknowledgment, drastically changing durability guarantees. |
| "Low latency proves no data loss." | Check send failures, transactions, durability, DLT/outbox, and downstream. |
| "Record retries are business duplicates." | Client idempotence resolves some retry duplicates; app replays require separate idempotency. |
| "Kafka client metrics share identical Prometheus names across all clusters." | Exporters/registries rename metrics and vary by version. |
| "Disabling retries fixes the root cause." | It may fail futures faster without fixing brokers/networks, increasing event loss if recovery is missing. |

## 20. Pre-change checklist

- [ ] Clearly define which send latency is measured: enqueue, future completion, transaction commit, or end-to-end.
- [ ] Have timers/histograms or observations capturing both success and failure, not just `send()` return time.
- [ ] Have Kafka client metrics for queue, request, buffer, retries, errors, and throttling.
- [ ] Metric tags have controlled cardinality; never attach keys, event IDs, payloads, or dynamic tenants to every series.
- [ ] Know the application's actual `client.id` and producer factory so you do not inspect the wrong producer's metrics.
- [ ] `acks`, idempotence, delivery timeout, and retries align with business delivery guarantees.
- [ ] Understand trade-offs among `linger.ms`, `batch.size`, compression, throughput, and latency.
- [ ] Backpressure protects the app when producer buffers or broker throughput fall behind.
- [ ] For Kafka transactions, measure commit/abort separately rather than treating send futures as committed output.
- [ ] Alerts for p95/p99 pair with failure rates and sufficient sample volume.
- [ ] Runbooks distinguish broker/network, producer queue, and application serialization issues.
- [ ] Tested load spikes, slow brokers, quotas, send timeouts, and shutdown/restart in an isolated environment.

## 21. Conclusion

**Producer send latency** is a family of latencies, not one single number. In Spring Kafka, `KafkaTemplate.send()` normally enqueues the record and returns a future; completion latency must be measured at future success/failure, while Kafka transaction commits and downstream processing are separate milestones.

For reliable operations, combine **application send completion timers**, **Kafka producer queue/request/buffer/retry metrics**, and **broker/quota metrics**. This multi-layer view distinguishes batching effects, full buffers, metadata lookups, networking, ISR issues, and transaction commits. When tuning, preserve `acks`, idempotency, and sound error policies—never trade away business reliability just to lower a latency number on a dashboard.

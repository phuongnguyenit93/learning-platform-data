# Rebalances, Consumer Lag, and Poll Timeout Failures

In a Spring Boot integration flow using Apache Kafka, a consumer may remain connected to the broker while **consumer lag** climbs steadily. After a period of slow processing, logs may show rebalances, revoked partitions, or offset commit failures. The new consumer taking over the partition re-reads uncommitted records, risking duplicate updates in databases or external APIs.

Three related symptoms must be kept distinct:

- **Rebalance:** the consumer group redistributes partition assignments across its members.
- **Consumer lag:** the gap between the end of a partition log and consumption/commit progress under a specific offset measurement.
- **Exceeding `max.poll.interval.ms`:** the consumer fails to call `poll()` again within the allowed time limit and may lose partition ownership under the active protocol.

This belongs to the **Apache Kafka** chapter of **SPRING_BOOT_INTEGRATION**. When integrating HTTP clients, databases, caches, brokers, and Spring Integration adapters, evaluate Kafka configs, event contracts, infrastructure errors, transactions, deduplication, testing, and observability together. Simply raising timeouts or adding replicas does not guarantee data stays consistent.

## 1. Concepts to Understand Before Troubleshooting

### Consumer Groups and Partitions

Suppose topic `orders.events` has 6 partitions and group `order-projection` runs 3 Spring Boot consumers. Within one group, each partition is processed by one consumer at a time; one consumer can handle multiple partitions.

~~~mermaid
flowchart TB
    T["Topic orders.events: 6 partitions"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> A["Consumer A"]
    P1 --> A
    P2 --> B["Consumer B"]
    P3 --> B
    P4 --> C["Consumer C"]
    P5 --> C
    A --> D["Update order state"]
    B --> D
    C --> D
~~~

Offset positions that are easily confused:

| Concept | Meaning |
| --- | --- |
| **Log end offset (LEO)** | Next offset after the latest record in the partition |
| **Consumer position** | Next offset the consumer expects to fetch per client `poll()` progress |
| **Committed offset** | Next offset recorded by the consumer group as its resume point on takeover/restart |
| **Committed lag** | Typically `LEO - committed offset` per partition, when a valid offset exists |
| **Position lag** | Measured from the client's read position; can differ from committed lag |

For example, if LEO = 12,500 and committed offset = 12,200, committed lag is **300 records**. If the client already polled up to offset 12,230 without committing yet, position and committed offset differ, so two metric sources can report different lag numbers.

**Consumer lag counts records, not time latency.** Business SLAs also need processing throughput, event age, ingestion timestamps, and completion timestamps. Even small record lag can represent severe delay if a single record hangs for a long time.

### How Does Lag Evolve?

During a steady observation window, you can approximate:

~~~text
Producer rate: 800 records/sec
Consumer process + commit rate: 600 records/sec
=> Lag grows ~200 records/sec
=> After 5 minutes backlog grows by ~60,000 records
~~~

This estimates the trend; actual behavior also depends on per-partition distribution, batch commits, retries, rebalances, and polled-but-uncommitted offsets.

## 2. When Does a Rebalance Occur?

A **rebalance** is the process by which a group changes partition ownership. It happens when:

1. Consumers join or leave the group due to scaling, rolling deploys, restarts, or crashes.
2. A member loses its heartbeat/session or fails to call `poll()` on time.
3. Partition counts or topic subscriptions change.
4. The consumer group switches assignors or protocols across deployments.
5. An application repeatedly errors and restarts its container, flapping in and out of the group.

During handoffs, affected partitions may pause briefly. If consumer A updated the DB without committing its offset, consumer B receiving that partition re-reads and reprocesses the same record. Therefore design **at-least-once + idempotency** for most flows affecting systems outside Kafka.

### Eager, Cooperative, and Static Membership

| Mechanism | Characteristics | Notes When Using |
| --- | --- | --- |
| **Eager rebalance** | Broad revocation of assignments prior to reassignment | Can pause processing more widely than necessary |
| **Cooperative/incremental rebalance** | Revokes only partitions that must move | Typically reduces disruption; depends on version/protocol/assignor |
| **Static membership** | Stable `group.instance.id` across brief restarts | Requires a unique ID per member; does not fix hung listeners |

Under the **classic** group protocol, cooperative rebalancing uses a supporting assignor such as `CooperativeStickyAssignor`. Newer Kafka releases also provide the broker-coordinated **consumer group protocol**; never mechanically copy every classic property into that protocol.

Static membership avoids unnecessary handoffs during brief restarts. However, if a static member violates `max.poll.interval.ms`, it can stop heartbeating and its partitions remain unassigned until session timeout expires—leaving lag climbing during the wait.

## 3. Distinguishing Timeouts

| Config / Mechanism | What It Monitors | When Exceeded |
| --- | --- | --- |
| `max.poll.interval.ms` | Maximum gap between application calls to `poll()` | Member may be deemed stalled and lose its assignment |
| `session.timeout.ms` | Maximum gap without heartbeats before member is deemed dead in classic groups | Coordinator triggers partition reassignment |
| `heartbeat.interval.ms` | Heartbeat cadence in classic groups | Works alongside session timeout; does not replace `poll()` |
| HTTP/DB client timeout | Maximum wait allowed for an external operation | Listener can block or fail with a timeout |
| Retry backoff | Wait interval between retry attempts | Blocking the consumer thread too long can push poll past its deadline |
| Commit timeout | Time allowed to persist offset progress | Slow or failing commits inflate committed lag |

Under Kafka's **classic protocol**, a background thread continues sending heartbeats while the listener processes records. Thus, **heartbeats can stay healthy while `max.poll.interval.ms` still trips** if the processing thread does not return to `poll()` in time.

With `group.protocol=consumer` in supporting releases, heartbeat/session timings may be broker-controlled. When diagnosing timeouts, verify exact Kafka broker, Kafka client, and group protocol versions rather than reading a config file in isolation.

### Why Can Even a Fast Record Cause Poll Timeouts?

`max.poll.interval.ms` is not a timeout for **a single record**. Suppose:

- `max.poll.records = 20`.
- `max.poll.interval.ms = 300000` (5 minutes).
- Each record hits HTTP + DB, taking 20 seconds in the worst case.
- The listener processes all 20 records from one poll sequentially.

Total processing time can reach `20 × 20 = 400 seconds`, excluding commits and retries. The next `poll()` arrives too late.

~~~mermaid
sequenceDiagram
    participant C as Consumer thread
    participant L as Listener
    participant X as HTTP and DB
    participant G as Group coordinator
    C->>G: Receive assignment
    C->>C: poll() returns up to 20 records
    loop Per record
      C->>L: Invoke listener
      L->>X: Execute I/O
      X-->>L: Return result
      L-->>C: Record finished
    end
    Note over C,G: Gap between polls exceeds max.poll.interval.ms
    G-->>C: Member/assignment may change
    C->>C: Next poll/commit hits group error
~~~

The error may surface on the heartbeat thread, during commit, or on the next poll depending on protocol and client. The diagram shows causal flow rather than guaranteed log ordering. When using pauses, retries, batching, or async processing, measure actual Spring Kafka container behavior.

## 4. Analyzing Consumer Lag: Find the Root Cause Instead of Guessing from One Metric

| Observation | Suspected Cause | How to Verify |
| --- | --- | --- |
| Steady lag growth, few rebalances | Consumption throughput trails input rate | Compare records in/out, CPU, p95/p99 processing times |
| Lag jumps during deploys | Restarts/scaling trigger rebalances | Correlate deploy timeline with revoked/assigned logs |
| Only one partition lags heavily | Hot key, hot partition, or poison pill | Inspect key distribution and logs by topic-partition-offset |
| Low CPU yet high lag | Waiting on HTTP/DB, locks, pool exhaustion, or retries | Check timeouts, downstream latency, thread dumps |
| DB updated yet lag stays flat | Offset uncommitted or commit failing | Compare consumer position vs. committed offset |
| Same offset repeats failing | Poison pill or infinite retry loop | Check exceptions, retry counts, deserializer, DLT |
| Lag jumps right after changing group ID | New group lacks committed offsets | Verify group ID config and `auto-offset-reset` |
| Low lag yet business flow feels slow | Delay upstream or before Kafka ingestion | Check event age and end-to-end traces |

**Lag does not prove a rebalance occurred**; a completely stable consumer builds lag if an external API slows down. Conversely, a brief rebalance during low traffic may barely move lag.

### Inspecting Groups via CLI

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-projection
~~~

Sample partial output:

~~~text
GROUP             TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
order-projection  orders.events  0         12500          12520          20
order-projection  orders.events  1          8000           8500         500
order-projection  orders.events  2          9200           9200           0
~~~

Partition 1 deserves investigation first. **CURRENT-OFFSET** here is the committed offset—it does not directly prove DB/API side effects succeeded accurately. If a group has no committed offset yet, lag cannot be computed this way.

You can also inspect group state and members (supported flags vary by CLI version):

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe --group order-projection --state

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe --group order-projection --members --verbose
~~~

Cross-check with revoked/assigned logs, `CommitFailedException`, pod restarts, member counts, and partition counts. Never reset offsets in production solely to clear a lag metric; doing so replays or skips data.

### Minimum Required Metrics

| Metric | Purpose |
| --- | --- |
| Lag by group/topic/partition (sum and max) | Distinguish broad backlog from hot partitions |
| Listener duration p50/p95/p99 and timeouts | Spot polls/records at risk of exceeding limits |
| Time between polls, last poll age | Detect stalled consumers early |
| Rebalance count and duration | Expose consumer-group churn |
| Records consumed/committed rate | Compare processing speed against produce rate |
| Retries, deserialization errors, DLT, commit failures | Catch stuck offsets or infrastructure failures |
| HTTP/DB latency and pool saturation | Locate bottlenecks outside Kafka |
| Event age at business completion | Measure real SLAs rather than guessing from lag |

Kafka clients expose metrics like `records-lag-max`, `time-between-poll-max`, and rebalance metrics depending on version. **Client-side lag metrics may measure consumer position**, differing from admin-tool committed lag. When building Prometheus/Micrometer dashboards, verify exact metric definitions and labels for your exporter.

A single timeline dashboard combining **lag + HTTP latency + listener duration + rebalance count + commit errors** clearly reveals chains such as: slow API → long processing → late poll → rebalance → commit failures → growing backlog.

## 5. Spring Boot Consumer Configuration

The following example shows a Spring Kafka record listener using the **classic group protocol**. Timeout values are illustrative, not universal production defaults:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      enable-auto-commit: false
      max-poll-records: 20
      properties:
        "[max.poll.interval.ms]": 300000
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
    listener:
      concurrency: 3
      ack-mode: record
~~~

- `max-poll-records` caps **records returned from one `poll()`**, not fetch bytes or client memory.
- Too small a `max.poll.interval.ms` triggers timeouts on slow batches; too large delays detecting genuinely wedged workers.
- `enable-auto-commit: false` and `ack-mode: record`: for record listeners, the Spring Kafka container commits after each record succeeds; still configure error handlers/recovery.
- `concurrency: 3`: one application instance spawns up to three child consumers. Count **total consumers across all replicas**; exceeding partition count does not raise group throughput.
- `auto-offset-reset: earliest` takes effect only when the consumer lacks a valid committed offset; it does not rewind existing groups.
- Heartbeat/session timings above apply to the classic protocol and must fit broker bounds; under `group.protocol=consumer`, check broker-governed parameters.

### Listener with Idempotent Side Effects

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

record OrderChanged(String eventId, String orderId, String status) {}

interface OrderProjector {
    void applyOnce(OrderChanged event);
}

@Service
class OrderProjectionListener {
    private final OrderProjector projector;

    OrderProjectionListener(OrderProjector projector) {
        this.projector = projector;
    }

    @KafkaListener(topics = "orders.events")
    public void onMessage(ConsumerRecord<String, OrderChanged> record) {
        // applyOnce must be atomic/idempotent in the database.
        projector.applyOnce(record.value());
    }
}
~~~

This example assumes the consumer is configured with a deserializer matching `OrderChanged`. `applyOnce` is an application contract: persist `eventId` (or a `topic-partition-offset` key where appropriate) backed by a unique constraint alongside the projection update **in the same DB transaction**. The listener returns only after the transaction completes. On a crash between DB commit and Kafka commit, re-reading the event will not repeat the update.

Enforce finite HTTP/DB timeouts, bounded retries, and connection pool limits. One record stalling for minutes on HTTP is enough to breach `max.poll.interval.ms`, even with `max.poll.records=1`.

**Never share a `KafkaConsumer` across threads**: the client is not thread-safe. If offloading work to a worker pool so the consumer thread can keep polling, implement bounded queues, backpressure, pause/resume, contiguous per-partition offset commits, and partition revocation cleanup. Returning from a listener while async work is unfinished risks data loss if the container acks.

### Estimating Poll Time Budgets

~~~text
Time between two polls (estimate)
≈ returned records × worst-case processing time per record
  + retries + commits + scheduling/overhead

Must stay comfortably below max.poll.interval.ms with real headroom.
~~~

For example, with `max.poll.records=20` and p99 latency of 8 seconds per record: roughly 160 seconds before outliers and retries. If a single HTTP timeout can hit 240 seconds, p99 does not prove 20 records finish within 300 seconds. Solutions require bounding I/O timeouts, shrinking poll batch size, or moving long tasks out of the poll loop.

## 6. Retries, Poison Pills, and Dead-Letter Topics

Retrying on the consumer thread can push a processing cycle past `max.poll.interval.ms`. Conversely, catching an error and returning normally without routing the record lets the container commit the offset and drop data.

| Failure | Example | Usually Appropriate Handling |
| --- | --- | --- |
| Permanent data error | Schema mismatch, missing required field | Do not retry forever; quarantine/DLT and alert |
| Permanent business error | Disallowed state transition | Record domain failure; route to DLT if policy requires |
| Transient failure | HTTP 503, temporary DB outage | Bounded retry with backoff and idempotency |
| Uncertain outcome | Timeout after payment creation request | Reconcile outcome or use idempotency key before retrying |
| Poison pill | Deserializer always fails at the same offset | Error-handling deserializer and dedicated error handling |
| Group/commit failure | Rebalance, generation mismatch | Recover via container mechanics and monitor assignments |

In Spring Kafka, `DefaultErrorHandler` paired with `DeadLetterPublishingRecoverer` performs bounded retries before routing to a DLT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

class InvalidOrderEventException extends RuntimeException {
    InvalidOrderEventException(String message) {
        super(message);
    }
}

@Configuration
class OrderKafkaErrorConfiguration {
    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)); // 2 retries after initial try

        handler.addNotRetryableExceptions(
                InvalidOrderEventException.class);
        return handler;
    }
}
~~~

To make this work in practice, configure a **DLT producer/serializer**, ensure the target DLT topic has matching partitions, verify post-recovery commit policy, and maintain a DLT handling workflow. `InvalidOrderEventException` is an application error thrown for data that retrying cannot fix. For decode failures **before the listener receives the record**, use `ErrorHandlingDeserializer` or equivalent so error details reach the handler.

Long backoffs on the consumer thread must fit within the **poll budget**. Depending on Spring Kafka version, consider **container-pausing backoff** or **retry topics / non-blocking retries** for long waits. Retry topics can alter ordering relative to the original partition; test ordering requirements before adopting. Never treat a DLT as business completion: someone or something must triage, fix, and replay records safely.

## 7. When Rebalances Meet Commits: Duplicates Are a Data Problem

This sequence frequently triggers duplicate events or DB writes:

1. Consumer A calls `poll()` and receives partition 0 offset 100.
2. A updates the DB but **has not yet committed offset 101**.
3. A stalls past the poll interval or crashes; partition 0 moves to B.
4. B reads from committed offset 100 and re-runs business logic.
5. Without idempotency, the system applies the effect a second time.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant D as Database/API
    participant G as Kafka group
    participant B as Consumer B
    A->>A: poll offset 100
    A->>D: Business update
    D-->>A: Success
    Note over A,G: Offset 101 not yet committed
    G->>B: Rebalance, assign partition
    B->>B: Re-read offset 100
    B->>D: Reprocess
    D-->>B: Idempotency check / unique key
~~~

**Kafka offset commits and database transactions are separate things.** Committing before DB success risks lost effects. Succeeding in DB before committing offsets allows replays; external effects must be idempotent. Kafka transactions/EOS help **Kafka-internal** read–process–write flows, without making external HTTP or SQL exactly-once. Most real integrations rely on **inbox/dedup tables**, outboxes, idempotency keys, and compensating workflows.

Never commit the highest offset read if earlier tasks on the same partition have not finished contiguously. When using rebalance callbacks to flush/commit, handle only revoked partitions while the generation is valid, and never assume callbacks have time for slow HTTP calls.

## 8. Reducing Lag Without Compromising Data Correctness

| Measure | Helpful When | Trade-off |
| --- | --- | --- |
| Reduce `max.poll.records` | Many sequential records exceed poll budget | More frequent polls; does not fix a single hung record |
| Bound HTTP/DB timeouts and retries | Downstream slowness blocks threads | Must distinguish permanent errors from uncertain outcomes |
| Raise concurrency or replicas | Unused partitions exist and backend has capacity | Consumers > partitions adds zero throughput; scaling triggers rebalances |
| Increase partitions systematically | Insufficient partition-level parallelism | Alters key distribution/order and adds operational cost |
| Cooperative assignor / static membership | Deploys/scaling cause heavy rebalance churn | Protocol/version-dependent; static IDs must be unique |
| Optimize I/O or business batching | DB/HTTP is the bottleneck | Must preserve ordering, contracts, and transactions |
| DLT and bounded retries | Poison pill blocks one partition | Requires DLT ops, replays, and idempotency rules |
| Tune `max.poll.interval.ms` | Valid workloads need controlled extra time | Setting too high delays detecting wedged consumers |
| Offload long work to async workflows | Minutes-long approvals, callbacks, or heavy compute | Needs progress state, checkpoints, outboxes, bounded queues |

Follow a disciplined sequence: **measure processing time → locate thread blockers → bound timeouts and retries → size poll batches → re-measure lag/latency → only then tune concurrency or poll intervals**. Adding replicas when the DB or API is already saturated only deepens the pileup.

## 9. Testing Rebalances, Lag, and Poll Timeouts

Do not rely solely on unit-testing `@KafkaListener` methods directly, as that skips the group coordinator, assignments, commits, and redeliveries. For integration tests, use embedded Kafka or Testcontainers Kafka with a controllable, time-simulated downstream mock.

| Scenario | Test Action | Expectation |
| --- | --- | --- |
| Normal processing | Produce N events, no errors | Committed offsets advance; lag returns to 0 once sends stop |
| Slow within budget | Simulate bounded slow I/O | Zero rebalances from poll timeouts |
| Exceed `max.poll.interval.ms` | Set low threshold in test; block listener long enough | Observe assignment/group change, then recovery |
| Crash after DB, before Kafka commit | Halt process between the two steps | Event may be re-read, yet side effect occurs once |
| Poison pill | Send schema-invalid or unparseable event | Record handled per policy/DLT; partition never stays wedged |
| Retry after timeout | Downstream returns 503/timeout then recovers | Bounded retries, lag drains, no duplicate effects |
| Scale 1 → 3 → 1 | Add and remove group members | Zero lost records; assignments stabilize after rebalance |
| Hot partition | Concentrate keys onto one partition | Per-partition lag and alerts pinpoint the bottleneck |
| Consumer restart | Restart with uncommitted records | At-least-once and idempotency verified |

In rebalance tests, **assert the actual event occurred** via logs, metrics, or assignments rather than sleeping N seconds and assuming a timeout fired. Idempotency tests should send the **same event ID multiple times**—including across different offsets—and assert DB state, API call counts, or outbox rows. Poll conditions with bounded timeouts rather than fixed `Thread.sleep` calls that cause flaky tests.

## 10. Practical Incident Response Procedure

When alerted to growing consumer lag or continuous rebalances:

1. **Isolate scope:** identify group, topic, partition, onset timestamp; compare total lag against worst partition lag.
2. **Verify mechanics:** member count, partition count, recent restarts/deploys, revoke/assign logs, timeouts, commit failures.
3. **Measure real timings:** poll-to-poll gap, listener p95/p99, records per poll, I/O durations, retry/backoff delays.
4. **Find the bottleneck:** hot partition, poison pill, slow downstream, crashing consumer, or input rate exceeding capacity.
5. **Protect data:** inspect committed offsets, external side effects already triggered, idempotency state, and DLT status before changing anything.
6. **Make one small change and re-measure:** shrink batch size, tighten timeouts, fix retries, optimize DB/API, or align concurrency with partition count.
7. **Prevent recurrence:** add crash/rebalance tests, build unified lag+poll+rebalance dashboards, add event-age alerts, and document replay runbooks.

**Example:** if only partition 4 lags because one event hits a 90-second pricing API call while other partitions keep up, focus on that API, partition 4's data/key, and timeouts. Adding replicas will not let two consumers in the same group process one partition concurrently under normal group assignment.

## 11. Pre-Production Checklist

- [ ] Group ID, partition count, and concurrency match target throughput.
- [ ] Poll interval evaluated alongside p95/p99 listener/HTTP/DB latencies.
- [ ] Finite timeouts, bounded retries, and explicit error classification exist.
- [ ] DLT, quarantine, and replay procedures are established.
- [ ] DB/API/broker side effects enforce idempotency.
- [ ] Committed-offset lag and consumer-position lag are distinguished in dashboards.
- [ ] Metrics track rebalances, poll intervals, per-partition committed lag, retries, and event age.
- [ ] Crash/rebalance tests cover the window around offset commits.
- [ ] Session/heartbeat/assignment configs match exact Kafka client and broker versions.

**Conclusion:** Rebalances shift partition ownership, lag tracks backlog, and `max.poll.interval.ms` bounds how quickly consumers must return to `poll()`. In Spring Boot, start from **real listener and downstream latency**, **offset commit timing**, and **idempotency across ownership changes**, then verify with tests and metrics so the system keeps pace with traffic without corrupting data.

# Designing Load Tests with Representative Data and Faults

## 1. Purpose of load testing in Spring Cloud Stream

Spring Cloud Stream builds event-driven applications using `Supplier`, `Function`, and `Consumer` functions connected to Kafka, RabbitMQ, or Pulsar via bindings and binders. As traffic rises, results depend on far more than messages per second: payload sizes, message key distribution, partition counts, consumer groups, downstream latency, retry behavior, DLQs, and failure recovery.

**Load testing with representative data and faults** means generating a workload closely mirroring production behavior, including normal messages, complex messages, malformed data, and controlled failures. The goal is to uncover throughput limits, latency, backlog, resource limits, and result correctness before deployment.

For example, a service handling 1,000 orders/second may run smoothly when all orders distribute evenly across keys and the payment service responds in 10 ms. The exact same rate can build a backlog when 80% of events concentrate on a handful of hot keys, 2% carry large payloads, and 1% of payment requests time out.

A useful test must answer:

- Under normal traffic, does the service meet SLOs and produce accurate results?
- At peak load, how much do end-to-end latency and backlog grow?
- How do hot keys, large payloads, and legacy schemas affect performance?
- Do retries or redeliveries amplify load exponentially?
- When the broker, consumer, or downstream fails, where do messages go and are any lost or duplicated?
- Once a failure ends, how long does the system take to drain the backlog and return to steady state?

## 2. Defining the system boundaries under measurement

Before generating data, define which segments are actually inside the measurement boundary. A message may pass through multiple components:

~~~mermaid
flowchart LR
    G[Load generator] --> I[(Input topic / queue)]
    I --> B[Spring Cloud Stream input binding]
    B --> F[Function / Consumer]
    F --> S[(Database / HTTP dependency)]
    F --> O[Output binding]
    O --> Q[(Output topic / queue)]
    B -. Failure / retry .-> D[(Retry or DLQ)]
    I -. Lag and backlog .-> M[Metrics and tracing]
    F -. Latency and errors .-> M
    Q -. Delivery verification .-> V[Result verifier]
    D -. Failure accounting .-> V
~~~

Explicitly define at least three time boundaries:

1. **Ingress latency:** from when the producer starts or the broker confirms publish until the consumer receives the message.
2. **Processing latency:** from when the handler starts until processing or output publishing completes per your exact definition.
3. **End-to-end latency:** from when the message enters the front of the system until the final output or business state is confirmed.

Do not confuse producer acknowledgement with consumer completion. With two independent brokers, a successful output publish does not prove a downstream transaction committed either. Specify exact start points, end points, and clock synchronization methods before comparing p95/p99.

## 3. How does load testing differ from functional testing?

Unit tests verify single-function logic; the Spring Cloud Stream Test Binder verifies bindings, conversions, and routing in memory. These tests are valuable, yet they do not fully reproduce real brokers, partition assignment, network jitter, rebalancing, persistence, acknowledgement, or broker-level retries.

| Test layer | What is verified | Limitations |
|---|---|---|
| Unit test | Business rules inside Function/Consumer | No real broker or concurrency |
| Test Binder | In-app message paths, bindings, conversions | Does not fully simulate Kafka/RabbitMQ/Pulsar behavior |
| Integration test | ACLs, consumer groups, serializers, retries, DLQs, broker semantics | Typically runs at low traffic |
| Load test with real broker | Throughput, latency, lag, skew, error amplification, recovery | Requires environment, observability, and load control |

Load tests should run in an environment matching production as closely as possible in broker type, client/binder versions, topics/queues, partitions, replicas, retention, resources, and dependencies. If infrastructure is scaled down relative to production, document the scaling ratio; test results do not extrapolate linearly automatically.

## 4. Writing measurement targets before running

A load scenario is meaningful only with pass/fail criteria. Illustrative SLOs for an order-processing pipeline:

| Metric | Example steady-load target | How to measure |
|---|---|---|
| Confirmed throughput | At least 1,000 valid events/second | Completed events, not just publish counts |
| End-to-end p95 | At most 1,500 ms | Ingress milestone to output state |
| End-to-end p99 | At most 3,000 ms | Latency distribution across valid events |
| Consumer lag | No sustained growth after warm-up | Offset lag or backlog age/size |
| Misrouted DLQ | 0 | Valid events wrongly routed to DLQ |
| Missing events | 0 | Full reconciliation of event IDs across outputs and error states |
| Recovery time | Backlog within threshold in 10 minutes | Measured from when downstream/broker recovers |

These are **illustrative hypothetical targets**, not Spring Cloud Stream defaults. Real targets must be grounded in production behavior and business constraints.

Usually you also monitor error budgets, p50/p95/p99, backlog, memory, CPU, GC, connection counts, broker utilization, and retry/DLQ rates. A system with high throughput that drops events or duplicates business side effects still fails.

## 5. What is representative data?

"Representative" does not mean taking a few identical JSON payloads and blasting them rapidly. The dataset must reproduce the **distributions** of factors affecting processing cost.

| Data dimension | Example distribution to simulate | Impact |
|---|---|---|
| Payload size | Mostly 1–4 KiB, some 32–256 KiB | Serialization, network, memory, GC |
| Field count / JSON nesting | Short records, records with many nested items | Parse and validation CPU |
| Message key | 80% of traffic from 5% of customers | Hot partitions, ordering, skew |
| Schema version | Current, older compatible versions, incompatible errors | Conversion, compatibility |
| Event type | Created, Updated, Cancelled, Refunded | Multiple business branches |
| Event ordering | In-order, late, duplicate, out-of-order | State, idempotency |
| Cardinality | Many distinct IDs, a few keys repeating heavily | Cache hit/miss, state stores |
| Business references | Existing customers vs. missing records | DB lookups, exceptions |
| Timestamps | Near-current event-time and older event-time | Windows, lateness, replay |

Distributions should be derived from aggregated production statistics stripped of sensitive data—such as payload size histograms, event-type ratios, key skew, and error rates. Never copy real customer data into test environments.

## 6. Clean, edge-case, and malformed data

Build a dataset spanning three categories:

1. **Common valid:** valid schema, small payload, existing key, normal order.
2. **Valid but resource-heavy:** large payload, many items, hot key, legacy supported schema version, late event.
3. **Invalid or intentionally fault-inducing:** malformed JSON, missing required fields, incompatible schema, nonsensical business data, downstream timeouts or 503s.

Example mix for 100,000 messages:

| Mutually exclusive category | Share | Message count |
|---|---:|---:|
| Normal valid | 96% | 96,000 |
| Valid with large payload/hot workload | 2% | 2,000 |
| Valid on older supported schema | 0.5% | 500 |
| Malformed payload or missing required fields | 0.5% | 500 |
| Valid hitting transient downstream errors | 0.7% | 700 |
| Non-retryable business error | 0.3% | 300 |
| **Total** | **100%** | **100,000** |

This is an **experimental mix**, not a universal product default. Ratios can be split into separate scenarios to isolate each factor's impact. Avoid changing key skew, payload size, and fault rate simultaneously in a single run without a comparison baseline.

## 7. Generating reproducible, privacy-safe data

Instead of real orders, generate synthetic data with consistent relationships: `customerId`, `orderId`, `eventId`, `amount`, `lineItems`, and `occurredAt`. Use a fixed seed to reproduce the exact same distribution; unique event IDs enable input-to-output reconciliation.

Example valid payload:

~~~json
{
  "eventId": "evt-000042",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "orderId": "ord-000042",
  "customerId": "customer-003",
  "occurredAt": "2026-11-20T08:00:00Z",
  "amountCents": 245000,
  "items": [
    {"sku": "sku-12", "quantity": 2, "priceCents": 122500}
  ]
}
~~~

Example intentionally malformed JSON payload:

~~~text
{"eventId":"evt-bad-003","eventType":"ORDER_CREATED","amountCents":
~~~

If the application consumes a POJO and the framework serializes outgoing messages automatically, you may **not be able to emit malformed JSON** through that producer. Use a raw producer/test harness to actively send corrupted bytes into the test topic/queue. Separate the corrupted-data stream from the valid-data producer so error rates are not skewed.

Never use real emails, phone numbers, tokens, addresses, or real IDs. If data must originate from production records, mask/anonymize it before testing and verify that keys and statistics still match test objectives.

## 8. Designing key distributions and simulating hot partitions

Kafka generally routes messages to partitions by key; a stable key goes to the same partition as long as partition count and routing algorithm remain unchanged. For per-order ordering, keeping `orderId` as the key is essential.

However, artificially uniform key distributions can make test results look better than reality. Certain large accounts or active devices can generate most messages. Experiments should cover:

- **Uniform:** many keys with equal traffic to measure maximum well-balanced capacity.
- **Moderate skew:** a small group of keys generates most messages to observe per-partition lag.
- **Extreme hot key:** a single key generates most traffic to locate sequential processing limits.
- **High key cardinality:** most messages carry fresh keys to test state stores/caches and lookup costs.

For example, simulate 100 customers where 80% of traffic chooses among 5 `customerId`s and 20% chooses among the remaining 95 `customerId`s. This distribution does not imply hot keys are equally sized in production; adjust to match real histograms.

Aggregate consumer lag can mask a single congested partition. Measure lag and processing rate per partition/key range, plus latency on events belonging to hot keys. With RabbitMQ, measure queues and consumer contention; with Pulsar `Key_Shared`, check key distribution and consumer assignment.

## 9. Payload size and real-world overhead

Suppose ingress load is 1,200 messages/second with an average payload size of 3 KiB:

~~~text
payload throughput = 1,200 × 3 KiB/s
                   = 3,600 KiB/s
                   ≈ 3.52 MiB/s
~~~

This covers only transmitted payloads, excluding headers, record metadata, TLS, batching, replication, log segments, indexes, protocol overhead, and downstream outputs or retries. Average payload size also hides tail latency: a few 256 KiB messages can trigger memory pressure or deserialization pauses.

Measure actual size histograms, serialization/deserialization counts, and latency by size bucket. Do not simply crank up message rate and call it a stress test; with tiny payloads, you may be measuring a bottleneck unrelated to your real workload.

## 10. Distinguishing open-loop vs. closed-loop workloads

In an **open-loop load model**, the generator emits events on a scheduled arrival rate, such as 1,000 messages/second, independent of downstream processing speed. This model is ideal for observing backlog growth when the service falls behind.

In a **closed-loop model**, the generator sends a new request only when in-flight requests drop or a prior request finishes. This is common in synchronous API benchmarks, yet it automatically throttles itself when the service slows down, making the system look healthier than it is.

For event-driven applications, a fixed arrival-rate model or production-derived arrival distribution better reflects externally driven events. Specify clearly:

- Target rate and time-varying profile.
- Producer count, connection count, and key distribution.
- Confirmed successfully published message count.
- Error rate of the load generator itself.
- Behavior when the generator cannot sustain the target rate.

If the generator saturates its CPU or the broker rejects publishes, the target rate curve no longer equals actual offered load. Measure messages actually accepted by the broker, not just what the generator attempted to send.

## 11. Load profiles to include in your test plan

| Load profile | Description | Questions to answer |
|---|---|---|
| Baseline | Low load, no faults | Does the system behave properly under baseline config? |
| Ramp-up | Step up 25% → 50% → 100% | At what point does throughput stop keeping up? |
| Steady-state | Sustain normal load long enough | Does lag stay flat? Does memory climb steadily? |
| Peak / burst | Spike to 150–250% briefly | How much does backlog grow and does it recover? |
| Soak | Steady load for many hours | Memory leaks, resource exhaustion, log growth? |
| Recovery | Drop load after spike or restore dependency | How long does it take to clear the backlog? |
| Fault under load | Broker or downstream fails under load | Retries/DLQ, duplicates, loss, degraded SLOs? |

You do not need to run everything at once. Run baseline and single-variable scenarios first, then combined scenarios once baseline metrics exist. Soak tests must run long enough to expose memory growth, GC trends, connection leaks, and log rotation.

## 12. Concrete load scenario matrix

An illustrative test matrix for a service with a nominal load of 1,000 messages/second:

| ID | Load and duration | Data | Injected faults | What to observe |
|---|---|---|---|---|
| T01 | 200/s for 10 min | 100% valid, uniform keys | None | Baseline latency, overhead |
| T02 | 1,000/s for 30 min | Representative mix | Natural errors in mix | SLOs, stable lag, accurate DLQ |
| T03 | Ramp 500 → 1,500/s over 15 min | Representative mix | No infra faults | Saturation point, p99 |
| T04 | 2,000/s for 5 min then 800/s | Representative mix | None | Backlog and drain time |
| T05 | 1,000/s for 20 min | 80% traffic on 5% keys | None | Hot partition lag |
| T06 | 1,000/s for 20 min | 5% large payloads | None | CPU, heap, GC, p99 |
| T07 | 1,000/s for 20 min | Representative mix | 10% downstream 503 for 3 min | Retry amplification, recovery |
| T08 | 1,000/s for 20 min | Representative mix | Stop one consumer replica | Rebalance/redelivery |
| T09 | 1,000/s for 20 min | Representative mix | Controlled broker/network outage | Publish/consume recovery |
| T10 | 1,000/s for 20 min | Representative mix | Poison messages and DLQ | Retry counts, no stream stall |

The rates, durations, and percentages above are **planning examples**, not universal recommendations. Tie each scenario to infrastructure capacity, SLOs, and rollback procedures; run fault injection only in controlled test environments.

## 13. Classifying errors by retryability

Not every exception should be retried the same way:

| Error category | Examples | Typical handling |
|---|---|---|
| Unparseable payload | Malformed JSON, corrupted bytes | Non-retryable; route to DLQ or reject per policy |
| Incompatible schema | Missing required field, unknown enum | Check version; DLQ when unrecoverable |
| Business validation | Negative quantity, unknown order | Non-retryable or business reject |
| Transient downstream | HTTP 503, 429, connection reset | Bounded retry with backoff |
| Resource exhaustion | Thread pool, connection pool, full disk | Shed/throttle load temporarily, controlled retry/backpressure |
| Broker interruption | Partition leader change, network timeout | Client reconnect/retry per binder/broker |
| Duplicate processing | Message redelivery after ack failure | Idempotency/deduplication |

An infinitely retried poison message can block a partition or generate heavy error load even at low input rates. Include enough malformed messages to measure fault isolation, while never letting unintended bad test messages reach production infrastructure.

## 14. Retry amplification and DLQs must be measured

Suppose 100 messages hit a transient error and each is processed up to 3 times; total **processing attempts** can reach 300. Ingress publish rate stays constant, yet requests hitting the downstream database or API can jump sharply.

~~~text
processing attempts ≈ original messages × average attempts
~~~

This formula is only an estimate; actual load also depends on delay/backoff, failure timing, concurrency, and whether retries emit new messages.

In every fault test, record:

- Initial input message count and total processing attempts.
- Retries, redeliveries, backoffs, and attempts broken down by error category.
- Messages exhausting retry limits.
- Messages routed to DLQ and failed DLQ publishes.
- Messages succeeding after retries.
- Latency from first receipt to final state.
- Duplicate side effects prevented by idempotency.

Non-retryable errors must be classified early. When the DLQ itself fails or lacks publish ACLs, the system may retain the failing message or loop endlessly; that is a separate scenario worth testing.

## 15. Ordering, duplicates, and idempotency under load

Kafka and many binders guarantee order only within an appropriate scope such as a partition, with no global order across partitions. With RabbitMQ shared consumers or Pulsar `Shared` subscriptions, multiple consumers process concurrently and can finish out of delivery order.

In tests, explicitly include three groups:

1. Valid in-order events: `CREATED → CONFIRMED → SHIPPED` for the same `orderId`.
2. Late events: `SHIPPED` arriving before `CONFIRMED` due to upstream behavior or replay.
3. Duplicate events: same `eventId` redelivered after redelivery/restart.

What must be verified is **correct business state**—such as recording payment once per order—not merely callback execution counts. Store `eventId` and result IDs for reconciliation; for duplicate events, track re-processing counts separately from actual side effects.

Never conclude that enabling Kafka transactions automatically gives exactly-once guarantees for an external database, HTTP call, or another broker. Whenever external side effects exist, implement dedicated idempotency/outbox/inbox or transaction mechanisms.

## 16. Consumer groups, partitions, and concurrency

Processing speed depends on partition count, consumers in the group, and downstream capacity:

- With Kafka, a partition within a group is usually assigned to one consumer at a time. Scaling replicas past partition count does not automatically increase parallelism for that data.
- A hot key concentrated on one partition can create high lag even while other partitions sit idle.
- With RabbitMQ, multiple consumers share queue load, while ordering and prefetch shape distribution.
- With Pulsar, `Exclusive`, `Failover`, `Shared`, and `Key_Shared` have different distribution and ordering semantics; configure for your problem.
- With Kafka Streams state stores, stateful processing incurs restore/rebalance and changelog overhead; tests should include state recovery phases.

Keep partition count and consumer replicas fixed in the baseline, then test intentional combinations. Never change partitions, concurrency, batch size, and payloads all at once when trying to pinpoint a cause.

## 17. Measuring lag, backlog, and catch-up capability

Message throughput only measures how fast the system moves data. When ingestion exceeds processing, messages accumulate into a backlog.

Example over 60 seconds:

~~~text
incoming = 1,400 messages/s
completed = 1,000 messages/s
backlog increase ≈ (1,400 - 1,000) × 60 = 24,000 messages
~~~

Suppose after the spike, ingress drops to 800/s while consumers still process 1,000/s; the theoretical backlog drain rate is 200/s:

~~~text
drain time ≈ 24,000 / (1,000 - 800) = 120 s
~~~

This is a simple model assuming steady processing speed and no extra retries. Reality also depends on key skew, batching, payloads, broker I/O, and downstreams.

With Kafka, measure consumer lag by topic-partition/group and message age; with RabbitMQ, measure ready/unacked messages, queue depth, and consumer count; with Pulsar, measure backlog, unacked, redeliveries, and subscription consumer state. **Backlog age** is often more informative than raw message count alone.

## 18. Metrics to collect from both application and broker

| Layer | Key metrics | Anomaly signals |
|---|---|---|
| Generator | Intended rate, actual acknowledged rate, send errors | Generator fails to hit target rate |
| Producer | Send latency, batch size, retries, publish errors | Broker or network congestion |
| Consumer | Processed/s, handler latency, active consumers | Throughput stops scaling when adding replicas |
| Broker | Lag/backlog, broker CPU, disk I/O, throttling | Queue accumulating or broker overloaded |
| JVM | CPU, heap, allocation rate, GC pauses, threads | Large payloads causing pauses, memory pressure |
| Dependency | DB pool wait, HTTP p95/p99, 429/503 | Downstream becomes the bottleneck |
| Reliability | Retries, redeliveries, DLQ, duplicates, missing IDs | Failures amplifying load or dropping events |
| Recovery | Restore/rebalance duration, backlog drain time | Fails to recover within RTO |

Spring Boot Actuator and Micrometer expose JVM, application, and some binder metrics; configure exporters/broker metrics appropriately. Do not assume every binder exposes identical metric sets or names.

## 19. Calculating latency and handling clock skew

If the generator stamps time on machine A and the verifier stamps time on machine B, clock skew can yield negative latencies or distorted p99 values. Use proper clock synchronization and monitor inter-node clock skew.

Solutions:

- Measure intra-process processing latency with a monotonic clock wherever possible.
- Measure end-to-end latency with synchronized UTC timestamps and document margin of error.
- Attach `eventId`/`correlationId` in headers or envelopes, avoiding high-cardinality metric tags like `customerId`.
- Measure percentiles per time window and inspect tail histograms, not just averages.
- Compare latency across runs only when start and end milestones match identically.

Do not use an old business timestamp `occurredAt` as ingress time to measure fresh processing latency: events may be published late or replayed. Distinguish `event-time`, `publish-time`, and `processing-time`.

## 20. Avoiding high metric cardinality

Putting `eventId` or `orderId` directly into Prometheus/Micrometer tags can spawn millions of time series and overload observability infrastructure. Instead:

- Restrict metric labels to bounded dimensions like broker, binding, outcome, exception category, or scenario.
- Record `eventId` and `correlationId` in structured logs or sampled distributed traces.
- Store detailed IDs and error reasons in DLQ reports for reconciliation.
- Bound per-partition/key-range metrics to infrastructure scale; never tag every `customerId`.

Instrumentation itself consumes CPU, RAM, and I/O. Keep sampling settings identical across benchmark runs or document differences to avoid false conclusions.

## 21. Controlled fault injection

Inject faults only in authorized test environments with explicit scope and duration. Every fault needs a trigger, verification that the fault actually occurred, a stop condition, and a recovery procedure.

| Fault | How to test in isolation | What to observe |
|---|---|---|
| Slow downstream | Add fixed/random latency to mock API | Queue wait, timeouts, backlog, p99 |
| Downstream returns 503 | Mock returns 503 at a set rate briefly | Retry rate and backoff |
| Broker disconnect | Temporarily break a test broker/endpoint | Reconnects, publish/consume errors |
| Consumer loses a replica | Stop one test process/pod | Rebalances, redeliveries, recovery |
| DLQ cannot write | Block ACLs or simulate publish failure in test | Detection and alerting of DLQ failure |
| Malformed schema | Send raw bytes or unsupported version | Non-retryable classification |
| Hot key | Concentrate traffic on one key/range | Partition lag and per-key fairness |
| Slow disk/DB | Throttle test dependency throughput | Thread pools, connection pools, lag |

Run one fault at a time against the baseline to isolate individual effects before combining faults likely to co-occur. Never inject faults without observability confirming the fault actually reached the intended component.

## 22. Designing a minimal test harness

The load generator should run separately from the service under test so it does not share CPU and heap with consumers. It must precisely control event rate, key distribution, payload mix, and fault profiles.

An illustrative scenario manifest (not a runnable Spring Cloud Stream configuration):

~~~yaml
scenario: orders-steady-with-faults
seed: 42
arrival:
  mode: fixed-rate
  targetMessagesPerSecond: 1000
  durationSeconds: 1200
data:
  populationSize: 100
  hotKeyCount: 5
  hotTrafficPercent: 80
  largePayloadPercent: 2
faults:
  malformedPayloadPercent: 0.5
  oldCompatibleSchemaPercent: 0.5
  downstreamTransientPercent: 0.7
  businessRejectPercent: 0.3
validation:
  requireEventId: true
  capturePublishAcknowledgement: true
  reconcileFinalOutcomes: true
~~~

Because one event could combine multiple traits (e.g., both a hot key and a large payload), clearly distinguish **independent** data-dimension percentages from **mutually exclusive fault categories**. The manifest illustrates multiple dimensions; when implementing the generator, pick the fault/category bucket first, then apply keys and sizes so a single event is not inadvertently counted as multiple independent faults.

The generator must monitor its own CPU, RAM, pending sends, and publish failures. If the generator hits limits before the broker does, test results do not reflect the service's true capacity.

## 23. Java example for reproducible key skew

The code below only generates fixtures; it does not send messages. Run single-threaded so the sequence generated from a fixed seed is deterministic. Suppose there are 100 customers and 5 hot customers generate roughly 80% of events:

~~~java
import java.time.Instant;
import java.util.Random;

record LoadEvent(
    String eventId,
    String customerId,
    int schemaVersion,
    Instant occurredAt,
    long amountCents
) {}

final class LoadEventFactory {
    private final Random random = new Random(42L);

    LoadEvent next(long index) {
        boolean hot = random.nextDouble() < 0.80;
        int customerNumber = hot
            ? random.nextInt(5)
            : 5 + random.nextInt(95);

        return new LoadEvent(
            "evt-" + index,
            "customer-" + customerNumber,
            2,
            Instant.parse("2026-11-20T08:00:00Z").plusMillis(index * 100),
            10_000L + random.nextInt(500_000)
        );
    }
}
~~~

In practice, add event types, item counts, older schema versions, size buckets, late events, and error classes per your design. Supply real keys when publishing to Kafka/Pulsar and verify routing; having `customerId` inside JSON does not guarantee the broker partitions by it.

If running a multi-threaded generator, do not share a single stateful `Random` expecting identical sequences across runs. Split the workload into fixed shards with distinct seeds, or pre-generate the dataset and replay it on an explicit schedule.

## 24. Application bindings and binder in the load test environment

Example Spring Cloud Stream flow with a `Function` receiving events from Kafka and emitting confirmed events. Minimal configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: loadtest.orders.input
          group: loadtest-order-processor
        acceptOrder-out-0:
          destination: loadtest.orders.output
      kafka:
        binder:
          brokers: ${LOADTEST_KAFKA_BROKERS}
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Provision topics, partitions, ACLs, retries, and DLQs ahead of time per scenario; never auto-create production resources. With multiple binders, declare the binder explicitly per binding. For RabbitMQ/Pulsar, swap the binder configuration and measure backlog/ack metrics tailored to that broker.

This snippet is an illustrative test-environment fragment; it **does not automatically configure retry/DLQ or fault injection**. Those capabilities require corresponding binder settings and must be verified against your actual version before drawing conclusions.

## 25. Building a verifier to reconcile every event ID

Do not declare completion from output counts alone. Build a verifier that collects outcomes by `eventId` and final state:

~~~text
INPUT_ACCEPTED
  ├── BUSINESS_SUCCESS
  ├── BUSINESS_REJECTED
  ├── DLQ_RECORDED
  └── STILL_PENDING_OR_UNKNOWN
~~~

For every input message acknowledged by the broker, the verifier should know which state that event is in when the test ends. After waiting until the recovery deadline, reconcile:

~~~text
accepted input IDs
  = unique successful IDs
  + unique rejected IDs
  + unique DLQ IDs
  + unique pending/unknown IDs
~~~

If the same ID appears in multiple buckets, investigate duplicate outcomes or business semantics; do not double-count it in the total. Count redeliveries and executed side effects separately.

Pending/unknown events must never be silently treated as successes. A test run may end with valid remaining backlog, but the report must explicitly list its count, age, and the evaluation cutoff.

## 26. Execution flow for a load test cycle

1. Document topology, binder version, instance count, partitions/queues, and downstream resources.
2. Agree on SLOs, failure budgets, throughput, and recovery deadlines.
3. Prepare a synthetic dataset with a fixed seed, event IDs, and production-like distributions.
4. Provision topics/queues, consumer groups, retry/DLQ, and ACLs in an isolated environment.
5. Verify the generator actually sustains the target rate in a brief smoke test.
6. Warm up the JVM, connection pools, caches, and consumer assignments before official measurement.
7. Run a fault-free baseline and save reference numbers.
8. Run selected load scenarios; inject faults at recorded timestamps.
9. Monitor the generator, service, broker, dependencies, and verifier together.
10. End faults, measure backlog drain, and record actual recovery time.
11. Reconcile event IDs, duplicates, retries/DLQ, and business outcomes.
12. Save a report with configuration, seed, dataset profile, timestamps, metrics, and failure causes.

Before each run, clarify reuse of consumer groups, offsets, queues, and DLQs. Reusing stale backlogs makes runs incomparable; reset test data cleanly or create distinct destinations/groups per run ID.

## 27. Result report template

A load test report should contain enough detail for someone else to reproduce it:

| Field | What to record |
|---|---|
| Scenario/run ID | `T05-hot-key-2026-11-24` |
| Git revision and binder version | Application revision and relevant dependency versions |
| Infrastructure | Broker type/version, node sizes, partition count, replica count |
| Dataset | Seed, total IDs, size histogram, key skew, schema mix |
| Offered/accepted rate | Target rate and rate actually accepted by the broker |
| Output throughput | Business events completed per second |
| Latency | p50/p95/p99, boundary definitions, sample count |
| Backlog/lag | Max, age, growth rate, and drain time |
| Error handling | Retry attempts, redeliveries, DLQ, non-retryable counts |
| Correctness | Missing/duplicate IDs, business rejects |
| Resources | CPU, memory, GC, broker/disk/network, downstreams |
| Fault injection | Start/end times, target, and confirmation method |
| Verdict | Pass/fail against each SLO with evidence |

Do not report only run-wide averages. Time-series charts must annotate ramp, peak, fault, and recovery phases so you know exactly when tail latency shifted.

## 28. Interpreting results and choosing actions

| Observation | Possible explanation | Next check |
|---|---|---|
| Lag rises on one partition while others stay flat | Hot key or partition skew | Key distribution, partition routing, handler on hot key |
| High CPU with p99 rising with payload size | Parse/serialize or allocation pressure | Heap profile, GC, size histogram |
| Throughput stalls when adding replicas | Partition limit, DB bottleneck, or locks | Consumer assignment, DB pool, downstreams |
| Input rate steady while attempt rate climbs | Retry amplification | 503 rate, retry count, backoff |
| DLQ rises while input stays constant | Schema/validation errors or broken dependency | DLQ reasons, sample events, schema compatibility |
| Lag drains very slowly after fault clears | Small capacity headroom or retry backlog | Net processing rate, max concurrency, pending retries |
| Output count matches yet side effects duplicate | Redeliveries without idempotency | Event IDs, business transactions, inbox/outbox |
| Generator rate falls below target | Generator/broker publish bottleneck | Producer latency, pending sends, generator CPU |

Change only one configuration variable in the next control experiment whenever possible. For example, adding consumer replicas when the bottleneck is application CPU helps, whereas adding replicas usually fails if a hot partition is serialized by ordering or a DB pool is already saturated.

## 29. Common mistakes

- Using identical messages, causing unrealistically high cache hit rates.
- Using purely random keys, hiding hot-partition bottlenecks.
- Measuring only broker publish throughput while ignoring successful completion throughput.
- Running for only a few minutes, missing memory leaks, backlog accumulation, or GC buildup.
- Testing only valid flows while skipping poison messages, retries, and DLQs.
- Injecting too many faults simultaneously from the start, obscuring root causes.
- Using real production data without privacy masking.
- Letting the producer self-throttle on slow consumers without tracking actual offered rate.
- Extrapolating production Kafka/RabbitMQ/Pulsar throughput from the Test Binder.
- Asserting only total output counts without reconciling event IDs and duplicate side effects.
- Skipping recovery measurement after peaks or failures end.
- Tweaking multiple parameters and claiming improvement without a fair baseline.

## 30. Load test design checklist

- [ ] Documented topology diagram, measurement boundaries, and latency definitions.
- [ ] Defined clear SLO/SLAs for steady, peak, and recovery phases.
- [ ] Prepared histograms for payload size, event type, schema version, and key distribution.
- [ ] Used fixed seeds/dataset IDs without real personal data.
- [ ] Documented malformed message ratios and fault profiles.
- [ ] Included hot-key, large-payload, and duplicate/redelivery scenarios.
- [ ] Covered baseline, ramp, steady, peak, soak, and recovery as appropriate.
- [ ] Generator tracks acknowledged send rate and publish failures.
- [ ] Collected app, broker, dependency, JVM, retry/DLQ, and backlog-age metrics.
- [ ] Fault injections have triggers, durations, recovery steps, and chart annotations.
- [ ] Built an event-ID verifier distinguishing success/reject/DLQ/pending.
- [ ] Verified idempotency, duplicate side effects, and business-required ordering.
- [ ] Produced a complete report covering config, versions, seed, results, and extrapolation limits.

Effective load test design for Spring Cloud Stream starts with **realistic data and faults**, and only then selects message rates. A rich dataset includes key distributions, payload sizes, schema versions, late events, duplicates, and business errors. Measurements must capture end-to-end latency, completion throughput, lag/backlog, retries/DLQ, resource usage, and recovery time. Only when every event ID is reconciled and system behavior under high load and faults is fully explained does a load test provide trustworthy evidence for deployment decisions.

## References

- [Spring Cloud Stream — Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/)
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Apache Pulsar — Monitoring](https://pulsar.apache.org/docs/administration-stats/)

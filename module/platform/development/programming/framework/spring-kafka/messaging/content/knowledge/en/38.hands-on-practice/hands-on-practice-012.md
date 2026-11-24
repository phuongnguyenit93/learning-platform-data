# Architectural Summary and Trade-Offs

A reliable Spring Kafka application needs more than just sending and receiving records. It requires a coherent architecture spanning event creation, serialization, publishing, storage in Kafka, delivery to consumers, business processing, offset acknowledgment, and error retry or dead-letter routing. Every choice carries trade-offs across durability, ordering, latency, throughput, recoverability, operational cost, and complexity.

This summary connects what you learned in the **SPRING_KAFKA_MESSAGING** module into an event-driven architecture ready to deploy and operate. The goal is not to pick the heaviest mechanism for every system, but to pick the right mechanism for business requirements, define clear guarantee boundaries, and know what to measure for verification.

## Expected Outcomes

After this lesson, you will be able to:

- Diagram and explain an architecture across producers, Kafka clusters, consumer groups, and downstream services.
- Choose boundaries between synchronous APIs, event publication, and asynchronous processing.
- Design topics, partition keys, consumer groups, and ordering requirements.
- Choose serializers, type headers, schema versions, and schema evolution strategies.
- Distinguish at-most-once, at-least-once, and exactly-once within Kafka's scope.
- Combine retries, dead-letter topics, idempotency, and safe replay.
- Choose Kafka transactions, database outbox/inbox, or sagas based on data boundaries.
- Balance throughput, latency, concurrency, partition count, and resource capacity.
- Design security with TLS, SASL, and ACLs.
- Build observability, integration tests, runbooks, and rollout processes.
- Document architectural decisions along with rationales and trade-offs.

## 1. Big-Picture Architecture

An event-driven flow typically consists of the following components:

~~~mermaid
flowchart LR
    A[API / Domain Service] --> B[Database Transaction]
    B --> C[Outbox]
    C --> D[Outbox Relay / CDC]
    D --> E[Kafka Topic]
    E --> F[Consumer Group A]
    E --> G[Consumer Group B]
    F --> H[Business Service A]
    G --> I[Business Service B]
    F --> J[Retry / DLT]
    G --> K[Retry / DLT]
~~~

Another implementation option is publishing directly with `KafkaTemplate` after business logic creates the event. This approach is simpler, but if the service both commits to a database and sends to Kafka, it must handle the failure window between the two systems. When database changes and the intent to publish an event must be persisted atomically, an outbox is usually the right choice.

Kafka serves as a distributed event log. Producers and consumers do not need direct knowledge of each other's implementations; they coordinate through topics, keys, headers, and event contracts.

## 2. Choosing Boundaries Between Commands and Events

A command instructs a service to perform an action; an event describes something that has already occurred.

| Concept | Example | Characteristics |
|---|---|---|
| Command | `CreateOrder` | Has an accountable recipient and can be rejected. |
| Event | `OrderCreated` | Describes an occurrence that already happened; may have multiple independent consumers. |
| Query | `GetOrderStatus` | Requests reading current state. |

Not every API call should become a Kafka event. If the caller needs a synchronous answer to proceed, HTTP/gRPC may fit better. Kafka shines when decoupling processing timing, fanning out to multiple consumers, absorbing bursts, or retaining events for reprocessing.

An API may return `202 Accepted` after recording a command/outbox row, while clearly distinguishing an "accepted" state from "business processing completed."

## 3. Event Contracts as Service Interfaces

Events should describe stable business data without exposing the producer's database schema or internal classes.

Example:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        int eventVersion,
        Instant occurredAt,
        String customerId,
        BigDecimal total,
        String currency
) {}
~~~

Fields should each serve a clear purpose:

- `eventId`: unique identifier for idempotency and tracing.
- `orderId`: aggregate/business identifier.
- `eventVersion`: contract version per system convention.
- `occurredAt`: timestamp when the business event happened.
- Business fields required by consumers, avoiding redundant data.

Do not place passwords, tokens, or unnecessary personal data in events. Events may remain in Kafka retention, DLTs, logs, and archive systems far longer than the original request lifecycle.

## 4. Topics, Partition Keys, and Ordering

Kafka guarantees ordering within a single partition. Kafka does not provide global ordering across multiple partitions.

If events for the same order must be processed in order, use `orderId` as the key:

~~~java
kafkaTemplate.send(
        "orders.events",
        event.orderId(),
        event
);
~~~

Trade-offs:

| Decision | Benefit | Cost/risk |
|---|---|---|
| Few partitions | Low overhead, easier ordering management | Limited parallelism. |
| Many partitions | Higher consumer parallelism | More metadata, replicas, segment files, and operational cost. |
| Aggregate key | Preserves ordering per aggregate | Hot keys can cause partition skew. |
| No key | Can distribute more evenly depending on partitioner | Does not preserve per-aggregate ordering. |

Increasing the partition count can map keys to different partitions for new records. If long-term ordering matters, plan migrations or carry sequence/version numbers in events before scaling partitions.

## 5. Consumer Groups and Parallelism

Each consumer group maintains its own offsets. Multiple groups can read the same topic independently; within a single group, partitions are distributed among consumer members.

Example for a 6-partition topic:

- A group with 3 consumers can assign 2 partitions per consumer.
- A group with 8 consumers has at most 6 consumers receiving partitions from that topic at once.
- Two different groups can both read all 6 partitions and advance offsets independently.

Concurrency should be chosen based on partition count, processing time, CPU, connection pools, and downstream capacity. Increasing concurrency beyond the partition count does not automatically increase throughput.

## 6. Producers: Durability, Retries, and Batching

Producer configuration should reflect how critical the events are.

Common baseline configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Meaning and trade-offs:

- `acks=all`: waits for acknowledgment according to the ISR and `min.insync.replicas`; increases durability, though writes may be rejected if ISR is insufficient.
- Idempotent producer: prevents duplicates caused by retries at the producer protocol layer; does not prevent application-level resends of the same business event.
- Retries and delivery timeout: send duration must be bounded; unbounded retries can hold buffers and raise latency.
- Batching/linger: improves network efficiency but can add wait time before sending.
- Compression: reduces bytes transmitted/stored at the cost of CPU.

Never tune producers for throughput alone. Measure send latency, error rates, buffer wait time, and consumer outcomes.

## 7. Consumers: Offsets and Delivery Semantics

For typical consumers, at-least-once is the standard choice: process the record successfully, then commit the offset.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

| Semantics | How confirmation works | Trade-offs |
|---|---|---|
| At-most-once | Commit before processing | Records may be lost if the process stops after committing. |
| At-least-once | Process then commit | Redelivery is possible and requires idempotency. |
| Kafka exactly-once | Output and input offset in the same Kafka transaction | More complex; covers only operations inside the Kafka transaction. |

Do not interpret exactly-once as meaning a listener executes only once. A listener can rerun after a rollback; what is protected is the committed Kafka outcome in a properly configured consume-transform-produce pipeline.

## 8. Idempotency as the Guard Against Side Effects

At-least-once can redeliver records. Consumers should use a stable `eventId` to prevent repeated side effects.

An inbox pattern:

~~~text
Database transaction:
  1. Insert eventId into inbox (unique constraint)
  2. If already exists: skip business mutation
  3. Apply business mutation
  4. Commit
~~~

The unique constraint must live in the same database transaction as the business state change. Simply calling `existsById` followed by insert without a unique constraint still has race conditions when two consumers run concurrently.

Idempotency does not mean ignoring every record with the same payload. An event ID must represent a unique logical event; if the producer generates a new ID on every business retry, the consumer cannot detect duplicates.

## 9. Kafka Transactions and Exactly-Once Scope

Kafka transactions fit when a single processing step must write to multiple output topics/partitions and commit the input offset atomically.

~~~mermaid
flowchart TD
    A[Consume input] --> B[Transform]
    B --> C[Begin Kafka transaction]
    C --> D[Produce output records]
    D --> E[Add input offsets]
    E --> F{Commit}
    F -->|Success| G[Output visible and offset advances]
    F -->|Abort| H[Output aborted and input can replay]
~~~

Downstream consumers need `isolation.level=read_committed` to see only outputs from committed transactions.

Kafka transactions do not automatically roll back databases, HTTP calls, emails, or object storage. If a listener updates a database and the Kafka transaction aborts, the database write may still be committed. Across database/Kafka boundaries, consider outbox/inbox or sagas/compensation.

## 10. Outbox: Coordinating Database and Kafka

The outbox pattern closes the failure window between committing to a database and publishing an event:

1. Within one database transaction, update business tables.
2. Within the same transaction, insert an outbox row.
3. Commit the database transaction.
4. A relay or CDC process reads the outbox and publishes to Kafka.
5. Mark/reconcile relay status per design.

If the relay publishes successfully before recording completion, the event may be published again. Therefore consumers still need idempotency.

Outbox improves reliability at the cost of extra tables, relay/CDC components, monitoring, retention, and outbox backlog management. It does not automatically create end-to-end exactly-once semantics.

## 11. Retries: Recovering from Transient Errors

Classify errors before choosing a retry strategy:

| Error category | Handling approach |
|---|---|
| Transient network/database timeout | Bounded retry with backoff. |
| Rate limit/downstream unavailable | Bounded retry, respecting `retry-after` if available. |
| Permanent payload/schema error | Do not retry indefinitely; route to recovery/DLT. |
| Invalid business rule | Handle per business logic or reject with audit. |
| Invalid authentication/authorization | Fix credentials/ACLs; endless retries will not help. |

Blocking retry holds the affected partition while waiting, which can preserve ordering at the expense of throughput. Non-blocking retry topics free up the main flow faster, but retried events can arrive behind newer events and alter ordering. Choose based on business needs.

## 12. Dead-Letter Topics and Replay

A DLT stores records that cannot be processed after retries/recovery. A DLT workflow needs:

- Preservation of raw key/value and essential headers.
- Storage of original topic, partition, offset, and exception metadata.
- Defined owner, case status, and retention.
- Root-cause classification before replaying.
- Replay ID and audit trail.
- Test replay of a single record or small batch first.
- Verification of idempotency, aggregate state, and ordering.
- Rate-limiting replays to avoid sudden load spikes.

Replaying an old record does not return it to its old offset. When republished, the record gets a new offset; if ordering matters, consumers must check sequence/version numbers or use a dedicated recovery workflow.

## 13. Serialization and Schema Evolution

JSON serializers/deserializers are convenient, yet type headers carrying FQCNs can couple producers to consumers' Java packages. Use stable tokens via type mapping when multiple event types require polymorphic deserialization.

Example wire token:

~~~text
__TypeId__ = order-created
~~~

Producers and consumers map that token to their own internal classes. Type tokens do not replace event versions or schema compatibility. For polyglot systems or strict governance, consider Avro, Protobuf, or JSON Schema with a Schema Registry.

Rollout rule: consumers must support new tokens/schemas before producers emit new data. Test both older records still in retention and newer payloads during rolling deployments.

## 14. Security: Identity, Transport, and Permissions

A production Kafka connection typically combines:

- TLS to encrypt connections and verify broker certificates.
- SASL to authenticate clients, such as SCRAM or OAUTHBEARER depending on the platform.
- ACLs to restrict which principals can read/write topics, use consumer groups, or use transactional IDs.
- Secret management to issue, rotate, and revoke credentials.

Successful authentication does not automatically grant read/write authorization. Use dedicated principals per role where appropriate and apply least privilege. Never commit secrets, JAAS passwords, tokens, or private keys to repositories or logs.

## 15. Performance and Capacity Planning

Three metric groups must be evaluated together:

| Metric | Meaning |
|---|---|
| Throughput | Records or bytes processed per second. |
| Latency | Time from a defined start point to a defined end point. |
| Consumer lag | Offset distance between log end and committed offset per partition. |

Measure p50/p95/p99 rather than averages alone. Monitor retries/DLT, producer buffer wait, listener processing time, database pool wait, broker disk/network, and rebalances.

Benchmarks need warm-up, steady state, realistic payloads, realistic key distributions, and explicit offered load. Open-loop load tests reveal growing backlogs when systems slow down; closed-loop tests can self-throttle and mask overload.

## 16. Observability: Measuring Flow Health

A minimal dashboard should cover:

- Producer acknowledged/failed rate and send latency.
- Consumer processing rate and p95/p99.
- Lag by topic/partition/group.
- Listener errors, retries, and DLT incoming/backlog rates.
- Rebalances and partition assignments.
- Broker offline partitions, under-replicated partitions, and ISR shrinks.
- Transaction commits/aborts and fencing.
- CPU, heap, GC, disk, network, and downstream latency.

Logs should correlate via event ID, correlation ID, topic, partition, offset, group ID, and service version. Never use event IDs or customer IDs as high-cardinality metric labels.

## 17. Multi-Layer Testing

| Test layer | Objective | Tools/suggestions |
|---|---|---|
| Unit | Business mapping, validation, idempotency logic | JUnit, Mockito, AssertJ. |
| Serializer/contract | JSON bytes, type headers, version compatibility | ObjectMapper, contract fixtures. |
| Spring Kafka integration | Listeners, producers, acks, retries, DLT | EmbeddedKafka. |
| Broker integration | Broker versions, transactions, security, metadata | Testcontainers or Kafka test cluster. |
| Failure testing | Crash windows, rebalances, timeouts, broker interruptions | Controlled fault injection. |
| Load testing | Throughput, latency, lag, and capacity | Open-loop/closed-loop generators. |

Kafka processes asynchronously; tests need Awaitility, `BlockingQueue`, `CountDownLatch`, or bounded consumer polling. Avoid fixed `Thread.sleep`, unbounded polling, and sharing groups/topics that cause tests to read stale data.

## 18. Operations and Controlled Change Management

Every topic needs an owner and a documented baseline:

- Partition count and replication factor.
- Retention and cleanup policy.
- Min ISR and producer acknowledgment expectations.
- ACLs and service principals.
- Schema/type tokens and versioning policy.
- Consumer groups and expected lag.
- DLT destination, owner, and replay procedure.

When increasing partitions, evaluate key remapping and ordering. When resetting offsets, confirm whether records will be skipped or replayed. When replaying a DLT, fix the root cause first and verify idempotency. During secret rotation, verify all instances have adopted the new credential before revoking the old one.

## 19. Architecture Selection Matrix

| Requirement | Typical suitable choice | Trade-offs to accept |
|---|---|---|
| Simple event publishing, no DB side effect in same transaction | `KafkaTemplate` + idempotent producer | Application must still handle send failures and business duplicates. |
| DB update must accompany event publish intent | Transactional outbox | Adds relay/CDC and backlog management. |
| Consumer only updates DB, must survive redelivery | At-least-once + inbox/idempotency | Records may be redelivered, while side effects are deduplicated. |
| Kafka consume-transform-produce needing atomic output/offset | Kafka transactions + `read_committed` | Adds transaction coordination and timeout limits. |
| Per-aggregate ordering required | Key by aggregate ID, process sequentially per partition | Hot keys cap parallelism. |
| Recovering from transient failures | Bounded retries with backoff | Increases latency or backlog. |
| Isolating poison pills | DLT + quarantine/replay workflow | Requires an owner, retention, and recovery procedures. |
| Multiple event types in a JSON topic | Stable type mapping or envelope discriminator | Requires managing token/schema contracts. |
| Polyglot systems and schema governance | Schema Registry with Avro/Protobuf/JSON Schema | Adds registry infrastructure and compatibility workflows. |
| Securing a production cluster | SASL_SSL + ACLs + secret management | Requires managing certificates, credentials, and policies. |

These are starting points, not rigid rules. Final decisions must depend on SLAs, data-loss tolerance, duplicate tolerance, ordering, volume, and operational team capacity.

## 20. Reference Flow: Order Service

A reference architecture for orders:

1. API receives the order creation command.
2. Database transaction saves the `Order` and `OutboxEvent`.
3. Outbox relay publishes `OrderCreated` to `orders.events` keyed by `orderId`.
4. Fulfillment consumer group reads events and uses inbox/`eventId` to prevent duplicate processing.
5. Consumer emits `OrderAccepted` or `OrderRejected` based on the outcome.
6. An independent Notification consumer group reads relevant events to send notifications.
7. Transient errors retry within bounds; unrecoverable errors move to the DLT.
8. Operators investigate the DLT, fix the root cause, and replay under control.
9. Dashboards monitor producers, lag, listener latency, retries, DLT, and broker health.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Order DB + Outbox
    participant R as Outbox Relay
    participant K as Kafka
    participant F as Fulfillment Consumer
    participant N as Notification Consumer
    API->>DB: Save order + outbox in one DB transaction
    DB-->>API: Commit
    R->>DB: Read unpublished outbox rows
    R->>K: Publish OrderCreated (key=orderId)
    K-->>R: Broker acknowledgement
    K->>F: Deliver to fulfillment group
    F->>F: Inbox/idempotency + business update
    K->>N: Deliver to notification group
    N->>N: Send notification idempotently
~~~

Consumer groups operate independently. If notification slows down, fulfillment can keep moving; if fulfillment errors out, that group's retry/DLT is managed independently.

## 21. Questions to Answer Before Production

Before taking a pipeline to production, the team should answer:

1. Which events form public contracts between services?
2. Where is the event ID generated, and does it remain stable across retries?
3. Which key preserves per-aggregate ordering?
4. Which workload justifies the partition count and replication factor?
5. Do producer acknowledgments and min ISR meet durability expectations?
6. Under what condition does the consumer commit offsets?
7. Which mechanism prevents duplicate side effects?
8. Do DB updates and Kafka publishing require an outbox?
9. Which errors are retried, how many times, and with what backoff?
10. Who owns the DLT, how long is it retained, and what is the replay procedure?
11. How are schemas/type tokens versioned and rolled out?
12. Which principals may read/write which topics and groups?
13. Which dashboard proves the pipeline is healthy?
14. Who is on call and which runbook is used during an incident?
15. Which tests prove crashes, retries, rebalances, and recovery are safe?

Without clear answers for data ownership, duplicates, ordering, and recovery, a pipeline is not production-ready just because a producer/consumer demo works.

## 22. End-of-Module Capstone Exercise

Design and implement an Order Messaging system meeting these requirements:

**Data flow**

- API creates an order and saves it to the database.
- `OrderCreated` events are published via an outbox.
- The topic is keyed by `orderId` and has multiple partitions.
- Fulfillment and Notification are two independent consumer groups.
- Fulfillment updates order state using inbox/idempotency.
- Notification sends alerts with appropriate deduplication.

**Reliability**

- Producer uses appropriate acknowledgments and idempotence.
- Consumers use at-least-once semantics and commit after processing.
- Kafka transactions are used if any Kafka-to-Kafka pipeline requires atomic output/offset updates.
- Retries are bounded; poison pills route to a DLT.
- DLT replay includes event IDs, replay IDs, auditing, and rate limiting.
- Per-`orderId` ordering is verified via sequence/version numbers.

**Contracts and security**

- Stable JSON type tokens or a schema registry.
- Event versioning and rolling compatibility rules.
- `SASL_SSL` connections, dedicated principals, and least-privilege ACLs.
- Secrets fetched from a secret manager with a rotation plan.

**Observability and testing**

- Dashboards for producer/consumer throughput, p95/p99, lag, retries, DLT, and broker health.
- Integration tests using `EmbeddedKafka` or Testcontainers.
- Tests for duplicates, crash windows, transaction aborts, rebalances, deserialization failures, and replays.
- Load tests with representative key distributions and payloads.
- Runbooks for producer outages, lag, DLT backlogs, and partition degradation.

**Completion criteria**

- No lost event publication intent once a database transaction commits.
- Duplicate deliveries never produce repeated business side effects.
- Consumer groups recover cleanly after restarts/rebalances.
- Failed records can be investigated and replayed safely under control.
- Ordering guarantees are proven within their stated scope.
- Security principals hold only necessary permissions.
- Throughput/latency meet defined SLAs with headroom.
- Operations teams have dashboards, owners, and runbooks.

## 23. Order of Architecture Refinement

| Stage | Decision | Required evidence |
|---|---|---|
| 1. Domain contract | Events, IDs, versions, ownership | Contracts and sample payloads. |
| 2. Topic design | Topics, keys, partitions, retention | Ordering requirements and capacity estimates. |
| 3. Producer | Serializers, acks, idempotence, retries | Send metrics and failure tests. |
| 4. Consumer | Groups, concurrency, AckMode | Offset behavior and lag dashboards. |
| 5. Reliability | Idempotency, retries, DLT | Duplicate/recovery tests. |
| 6. Consistency | Kafka transactions or outbox/inbox | Failure-window tests. |
| 7. Security | TLS, SASL, ACLs, secrets | Positive/negative authorization tests. |
| 8. Performance | Throughput, p95/p99, capacity | Repeatable benchmarks. |
| 9. Operations | Alerts, runbooks, ownership | Incident drills and recovery evidence. |
| 10. Release | Compatibility, rollout, rollback | Consumer-first rollout plan and version matrix. |

This lesson is complete when you can explain why the architecture selects each mechanism, what is guaranteed, what can happen when failures occur, and how operations will recover. A sound architecture does not eliminate all failures; it makes failures observable, bounded, investigable, and recoverable while protecting business data.

Spring Kafka provides building blocks such as `KafkaTemplate`, listener containers, error handlers, transaction managers, and serializers/deserializers. Ultimate reliability comes from pairing them with event contracts, partitioning strategies, idempotency, outbox/inbox patterns, security, observability, and operational procedures matched to real-world requirements.


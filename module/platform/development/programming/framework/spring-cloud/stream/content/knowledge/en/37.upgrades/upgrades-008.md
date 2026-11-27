# Regression Testing Contracts, Offsets, DLQ, and Transactions During Upgrades

Upgrading a Spring Cloud Stream application can change the versions of Spring Boot, Spring Cloud Function, Spring Cloud Stream, Kafka/RabbitMQ/Pulsar binders, serializers, or business code. Even if functions still run and unit tests stay green, the system can fail when the new version reads old messages, when a consumer resumes from a saved position, when failed messages route to a DLQ, or when an in-flight transaction aborts mid-way.

In event-driven systems, a safe upgrade must preserve the committed **data contract**, **message consumption progress**, **error-handling path**, and **delivery guarantees**. Regression testing is the process of proving those behaviors through reproducible test scenarios, including when old and new versions run concurrently and when rolling back.

This lesson focuses on Spring Cloud Stream under the `Supplier`/`Function`/`Consumer` model with bindings and binders. Kafka has offsets and transactions; RabbitMQ uses queues/ACKs; Pulsar uses subscription cursors and message acknowledgments. Therefore, a shared set of criteria is needed, while broker-specific verifications must be separated.

## 1. Four contract layers to preserve during upgrades

| Regression layer | Question to answer | Test evidence |
|---|---|---|
| Payload and message contract | Can the new consumer read old messages? Can the old consumer read new messages during a rolling upgrade? | Deserialization tests, schema compatibility, headers, keys, types, and semantic fields. |
| Consumption progress | Does the consumer resume from the right processed position? Are messages lost or reprocessed uncontrollably? | Offsets/subscription cursors before and after restart, rebalance, crash; business idempotency. |
| Retry and DLQ | Do failed messages retry per policy and route to the right place once attempts are exhausted? | Handler invocation counts, DLQ counts, payloads, headers, replay, and failure injection. |
| Transactions and side effects | When a failure occurs mid read–process–write, do outputs and read positions commit/roll back together? | Checks on committed/aborted outputs, offsets, duplicates, and outbox/DB behavior. |

Do not rely solely on `ApplicationContext starts` or an HTTP health check as success criteria. A started app can still read the wrong schema, stall on a nonexistent offset, drop failed messages, or emit duplicate outputs.

~~~mermaid
flowchart LR
    A[Producer v1/v2] --> B[(Input topic/queue)]
    B --> C[Consumer v1/v2]
    C --> D[Output/DB]
    C --> E[Retry / DLQ]
    C --> F[Offset / ACK / Cursor]
    D --> G[Business verification]
    E --> G
    F --> G
~~~

## 2. Preparing a baseline before changing versions

Before an upgrade, capture the data needed for comparison:

1. **Version matrix:** Spring Boot, Spring Cloud release train, Spring Cloud Stream, Spring Cloud Function, binders, and Kafka/Rabbit/Pulsar clients and brokers.
2. **Binding map:** `spring.cloud.function.definition`, input/output binding names, `destination`, `group`, and specific binders.
3. **Contract snapshot:** current schemas, content types, key/partitioning strategies, required/optional fields, headers, and raw message samples.
4. **Consumer progress:** Kafka group offsets per topic/partition; Rabbit queue ready/unacked counts; Pulsar subscription cursors/backlog.
5. **Error policy:** retry attempts, backoff, DLQ/requeue settings, DLQ serialization format, and replay tooling.
6. **Transaction policy:** Kafka transaction ID prefix, downstream isolation level, ACK/commit timing, and non-Kafka side effects.
7. **Operational baseline:** throughput, lag, redeliveries, DLQ rate, duplicate business keys, p95/p99 latency.

Record the actually deployed parameters, not just config file contents. Environment variables, profiles, binder defaults, and dependency updates can alter effective configuration even when property names stay unchanged.

Test datasets should carry immutable IDs, such as `evt-0001` through `evt-0100`, to reconcile inputs against outputs. For sensitive data, use synthetic fixtures and never copy production payloads into tests indiscriminately.

## 3. Old/new version matrix

For a producer P and consumer C, run at least the following combinations:

| Producer | Consumer | Purpose |
|---|---|---|
| P1 | C1 | Legacy baseline: establishes currently supported behavior. |
| P1 | C2 | New consumer must read legacy messages and historical backlog. |
| P2 | C2 | Target post-upgrade system running end-to-end. |
| P2 | C1 | Verifies whether the old consumer can read new messages during rolling upgrades or rollbacks. |

Not every combination is required to succeed. If the new contract only provides backward compatibility, P2/C1 may not be supported; in that case, upgrade all consumers before producer P2 begins emitting the new schema.

Pay special attention to testing:

- **Mixed deployment:** some C1 and C2 instances sharing a consumer group during rollout.
- **Restart:** stopping C2 and restarting it with the same group/subscription.
- **Rollback:** switching back from C2 to C1, covering messages emitted by both P1 and P2.
- **Replay:** consumer re-reading older messages after offsets/cursors are rewound in a test environment.

The matrix must cover both application versions **and** broker-side schemas; a new app running against an old schema registry, DLQ policy, or topic config may behave differently from a new app running against updated infrastructure.

## 4. Payload contract regression testing

The message contract extends beyond the function's Java parameter type. For an `OrderCreated` event, specify:

- Event name/type, version, and business meaning.
- Field names, types, optionality/defaults/nullability, units, and invariants.
- Serialization: JSON, Avro, Protobuf, primitive, or byte array.
- Spring Cloud Stream content type and Pulsar/native schema if used.
- Message key, partition/routing key, and ordering requirements.
- Headers for correlation, tracing, idempotency, event time, tenant, or content type.
- Handling of unknown fields, unknown enum values, and tombstone/null payloads.

Example V1:

~~~json
{
  "eventId": "evt-0001",
  "orderId": "ord-100",
  "amount": 125000
}
~~~

V2 adds a field:

~~~json
{
  "eventId": "evt-0001",
  "orderId": "ord-100",
  "amount": 125000,
  "source": "MOBILE"
}
~~~

If `source` is optional and the new consumer applies a sensible default when reading V1, this may be compatible. If V2 changes `amount` from a number to a string or from dollars to cents without updating the contract, the code may compile while business logic silently produces wrong results.

### 4.1. Schema compatibility is not semantic compatibility

A Schema Registry can check data types and structural evolution rules, yet it does not know how business logic interprets `amount`, `status`, or `eventTime`. Tests must verify both technical contracts and business outcomes:

| Change | Required tests |
|---|---|
| Add optional field | V1 → C2 uses default; P2 → C1 ignores field if supported. |
| Rename field | Whether old/new consumers have aliases/migration; never assume compatibility. |
| Change data type | Whether schema registry accepts/rejects; whether serializer and business logic handle it. |
| Add enum value | Whether old consumer falls back/uses UNKNOWN or fails. |
| Change field meaning | Compare computed results, not just successful deserialization. |
| Change message key | Does it affect partitioning, ordering, compaction, and idempotency? |
| Change headers | Does it drop correlation, tracing, routing, or content-type? |
| Tombstone/null value | Do new and old consumers handle it per topic contract? |

### 4.2. Upgrade rules by compatibility strategy

| Strategy | Simplified meaning | Typically suitable rollout order |
|---|---|---|
| BACKWARD | New consumer reads data written with previous schema. | Consumers first, producers second. |
| BACKWARD_TRANSITIVE | New consumer reads all checked historical schemas. | Consumers first, producers second; suits long-term replay. |
| FORWARD | Old consumer reads data created by new producer. | Producers first, consumers second; check older retained data. |
| FULL/FULL_TRANSITIVE | Bidirectional compatibility across checked versions. | More flexible for rolling upgrades; still test semantic contracts. |

Exact rules depend on format and registry. Kafka does not provide Confluent Schema Registry natively; if using an external Avro/Protobuf/JSON Schema registry, verify compatibility there. Pulsar has its broker-side schema registry and compatibility strategies. With JSON serialized via Spring message conversion into Pulsar's `Schema.BYTES`, do not confuse a JSON content type with a broker-managed JSON schema.

### 4.3. Regression fixtures for historical data

Save message fixtures exactly as emitted by V1, including bytes and necessary metadata, then test with V2:

~~~java
@Test
void v2ReaderAcceptsV1Json() throws Exception {
    ObjectMapper objectMapper = new ObjectMapper();
    String historicalJson = """
        {"eventId":"evt-0001","orderId":"ord-100","amount":125000}
        """;

    OrderCreatedV2 event =
        objectMapper.readValue(historicalJson, OrderCreatedV2.class);

    assertThat(event.eventId()).isEqualTo("evt-0001");
    assertThat(event.orderId()).isEqualTo("ord-100");
    assertThat(event.amount()).isEqualTo(125000);
    assertThat(event.source()).isNull();
}

record OrderCreatedV2(
    String eventId, String orderId, long amount, String source
) {}
~~~

This only tests JSON conversion and a single class contract. For Avro, Protobuf, or Pulsar native schemas, test with real serializers/deserializers and schema IDs/versions on the broker/registry. For payloads encoded with key/value serializers, retain key bytes, headers, and version metadata to expose compatibility bugs invisible in plain JSON text checks.

## 5. Test Binder verifies wiring and functions, not broker semantics

`spring-cloud-stream-test-binder` provides `InputDestination`, `OutputDestination`, and `@EnableTestBinder` to test function/binding flows inside the JVM. This is a fast regression layer for a Spring Cloud Function/Spring Cloud Stream upgrade:

- Did function definitions and binding names change?
- Are JSON conversion, headers, and routing correct?
- Does function composition execute in the expected order?
- Are exceptions thrown at the right point for the binder/container to handle?

Example testing a simple text function:

~~~java
@SpringBootTest(
    classes = WiringRegressionTest.TestApp.class,
    properties = "spring.cloud.function.definition=normalize"
)
class WiringRegressionTest {
    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void bindsFunctionWithExpectedNames() {
        Message<byte[]> request = MessageBuilder
            .withPayload("order-1".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(request, "normalize-in-0");

        Message<byte[]> result =
            output.receive(1000, "normalize-out-0");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ORDER-1");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApp {
        @Bean
        Function<String, String> normalize() {
            return text -> text.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Do not infer from this test that Kafka commits offsets right, Rabbit ACKs/DLQs right, or Pulsar preserves subscription cursors. Those verifications must run against real binders and brokers in integration tests.

## 6. Kafka: offsets track consumer group progress

In Kafka, offsets increment per partition. A committed offset represents where the consumer will resume reading; usually it is **the next offset after the last committed record**. For example, after processing/committing records at offsets 0 through 4, the saved position is typically 5.

The Spring Kafka listener container has AckModes such as `RECORD`, `BATCH`, and `MANUAL`. When Kafka transactions are enabled, offsets are included in the transaction rather than committed independently in the regular way.

During an upgrade, it is critical to keep stable:

- `destination` (Kafka topic) and binding `group`.
- Serializers/deserializers, keys, and partitioning strategies.
- AckMode, batch mode, retry/error handler, and commit behavior.
- Concurrency, partition counts, and rebalance rules.
- Consumer authentication/authorization and transactional visibility.

If `group` changes unintentionally, the application becomes a new consumer group. It does not inherit committed offsets from the old group; the starting position depends on `startOffset`/`auto.offset.reset`. In the Spring Cloud Stream Kafka binder, an explicit group typically starts from `earliest` when no committed offset exists, while an anonymous group typically starts from `latest`. Verify defaults/overrides for your binder version.

### 6.1. Do not use resetOffsets as a routine upgrade step

`start-offset` controls the starting position when a group has no committed offset or the offset is no longer valid. `reset-offsets: true` instructs the binder to reset the position per config whenever the binding starts. The two serve different purposes:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              start-offset: earliest
              reset-offsets: false
~~~

This illustrative config keeps the group stable and avoids actively resetting offsets. Do not add `reset-offsets: true` to "make sure it reads from the start" in production rollouts; doing so can replay huge volumes of data, trigger duplicate side effects, and spike lag.

If a replay is genuinely needed, plan it separately: choose an offset/time range, use a distinct consumer group or offset-management tool, control side effects, and document the recovery point. Never reset offsets while a consumer group is active without coordinating through broker procedures.

### 6.2. Offset regression scenario

A Kafka integration test should:

1. Create a multi-partition topic and use a fixed group `orders-upgrade-test`.
2. Publish 100 messages with unique event IDs and keys distributed across partitions.
3. Run consumer V1 until it processes/commits a known subset of messages.
4. Record committed offsets per partition and the count of processed business records.
5. Stop V1 cleanly, then start V2 with the **same group**.
6. Publish more messages and wait for V2 to finish processing all of them.
7. Reconcile the union of processed event IDs against the expected input set; zero events may be lost.
8. Verify committed offsets did not jump back to the beginning or skip to the end outside the chosen policy.

On a **graceful restart**, few or no duplicates may be expected depending on commit mode. On a **crash between processing and commit**, at-least-once semantics allow some messages to reappear. Tests must verify idempotency rather than asserting every restart produces zero duplicates.

### 6.3. Testing rebalances in mixed deployments

During a rolling upgrade, C1 and C2 may join the same consumer group simultaneously. Kafka distributes partitions among members, though it does not guarantee proportional record counts per instance. Check:

- Consumers V1 and V2 process the same schema and semantic contract.
- No partition is left orphaned after rebalancing.
- Every member finishes processing within `max.poll.interval.ms`.
- Once V1 stops, partitions transfer to V2 and lag returns to normal levels.
- No duplicate side effects exceed designed idempotency guarantees.

If `spring.cloud.function.definition`, binding names, or `group` changed during refactoring, compare the effective binding map before and after upgrade. Renamed bindings can silently stop binding-specific retry, DLQ, or offset properties from applying.

## 7. RabbitMQ and Pulsar do not use Kafka offsets

Do not apply the same "offset before/after" assertion across all binders.

| Broker | Consumption progress | What to test during upgrade |
|---|---|---|
| Kafka | Consumer-group committed offset per topic/partition. | Restart, rebalance, commit/seek, replay, and `read_committed`. |
| RabbitMQ | Queue, delivery tag, ACK/NACK, ready/unacked messages. | Queue name/binding, post-processing ACK, requeue, redelivery, and DLX/DLQ. |
| Pulsar | Subscription cursor, message ID, ACK/NACK/redelivery. | Subscription name/type, backlog, ACK timeout, dead-letter policy, and cursor. |

### 7.1. RabbitMQ: restarts and ACKs

With the Rabbit binder, `group` affects the queue/durable subscription name. Changing the group can create a different queue, leaving old messages stranded in the previous queue while the new consumer never sees them.

Tests should publish messages with fixed IDs, stop the consumer mid-handler before ACK, and then start V2 on the same queue/group. Verify unacked messages are redelivered per configuration; already-ACKed messages are not unexpectedly re-consumed. Inspect ready/unacked counts, the `redelivered` flag, retry counts, and idempotent side effects.

### 7.2. Pulsar: subscriptions and cursors

With Pulsar, subscription name and subscription type dictate delivery/ACK mechanics and ordering guarantees. Changing the subscription name during an upgrade can cause the consumer to use a fresh cursor and read from a different position.

Tests must use the same subscription per the rollout plan, verifying ACK/NACK and subscription backlog before and after restarts. With `Shared` subscriptions, Pulsar's dead-letter policy can trigger by redelivery threshold; with `Exclusive`/`Failover`, verify Spring Pulsar's error-handling mechanism because native DLQ does not provide identical support. Do not assume all subscription types share the same DLQ behavior.

## 8. Testing retry and DLQ paths

An upgrade can alter retry counts, retryable exception types, backoff, error publishing, or post-recovery ACK/commits. Tests must prove **failed messages are handled or saved for replay**, not just that the function throws an exception.

Minimum matrix:

| Input | Handler behavior | Expected outcome |
|---|---|---|
| Valid message | Succeeds on first attempt | Output/business side effect happens exactly once; not sent to DLQ. |
| Transient error | Succeeds after a few attempts | Invocation count/delay matches policy; not sent to DLQ. |
| Poison message | Always fails | Exhausts retries then routes to the right DLQ, retaining data/metadata for investigation. |
| Deserialization error | Handler cannot run | Follows configured error/deserialization path without silently killing listener. |
| DLQ broker/topic error | Recovery publish fails | Does not silently ACK/commit and drop message; verify retry, logs, and alerts. |
| Consumer crashes during retry | Process terminates | Unacked/uncommitted message is redelivered per guarantees. |
| DLQ replay | Fix root cause then replay | Idempotency holds; no infinite poison message loop. |

Cases should assert payload bytes or schema version, event ID, original topic/queue, partition/key where applicable, exception category, retry count, and correlation metadata.

### 8.1. Kafka binder: DLQ configuration

Example for a consumer **without transactional binder enabled**:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.dlq
~~~

Kafka DLQ requires a declared consumer group; anonymous groups cannot use this feature. When `enable-dlq` is enabled, failed records after exhausting retries can be routed to a dead-letter topic. The default DLQ topic is `error.<destination>.<group>` if `dlq-name` is omitted.

Inspect the serializer of the DLQ producer: whether raw bytes, native payloads, or POJOs are used affects which serializer is needed. By default, DLQ publishing often targets the same partition number as the original record, so the DLQ partition count must match or a different partition resolver must be configured.

Test the same poison record on V1 and V2 to compare retry counts, backoff, original headers, and DLQ record counts. When upgrading Spring Kafka error handlers, also test non-retryable exceptions and post-recovery behavior.

### 8.2. Rabbit binder: DLX, requeue, and republish

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: orders-processor
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              requeue-rejected: false
~~~

`auto-bind-dlq` lets the binder provision the DLQ/DLX and appropriate routing when permitted. `republish-to-dlq` causes the binder to republish failed messages with exception metadata (such as the `x-exception-stacktrace` header). `requeue-rejected: false` prevents infinite requeue loops on unhandled failures.

During an upgrade, verify actual queues, DLXs, routing keys, TTLs, dead-letter routing, queue arguments, and broker policies. Switching from reject/requeue to republish can alter ACK behavior and headers. Checking that a message "went to the DLQ" is not enough; tests must read the message from the right queue and inspect required metadata.

### 8.3. Pulsar: redelivery and dead-letter policy

Pulsar's native DLQ is tied to the consumer's dead-letter policy, subscription type, and redelivery counts. With a `Shared` subscription, `maxRedeliverCount` and a DLQ topic can be configured; other subscription types require verifying support with your specific client/Spring Pulsar version.

Write tests covering: consistently failing handler, ACK timeout or negative acknowledgment per configuration, waiting through all redeliveries, reading the message from the DLQ, comparing event ID/schema, and verifying the subscription backlog is no longer blocked. For partitioned topics, name the DLQ topic explicitly to avoid partition-suffixed defaults that are harder to manage.

## 9. Kafka transactions: exact scope of guarantees

The Spring Cloud Stream Kafka binder supports a transactional binder. For a processor reading from a Kafka topic and writing to a Kafka topic, the transaction can atomically combine **produced records** and **offsets of consumed records** in a single commit.

Illustrative configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-tx-instance-a-
~~~

`transaction-id-prefix` must be unique enough across concurrently running instances to prevent unintended transactional producer fencing. In a processor application, the listener container begins the transaction; outputs sent on the consumer thread join that transaction; when the listener succeeds, consumed offsets are sent to the transaction and committed alongside outputs.

When using the transactional binder, producer bindings share a producer factory configured at `spring.cloud.stream.kafka.binder.transaction.producer.*`; individual Kafka binding producer properties may be ignored. Test effective configuration, especially when upgrading binders and changing serializers/partitioning.

### 9.1. Atomic read–process–write, not all side effects

Suppose the Kafka input is `orders.created` and Kafka output is `orders.validated`:

~~~mermaid
sequenceDiagram
    participant K as Kafka input
    participant C as Processor
    participant O as Kafka output
    C->>K: Poll event E1
    C->>C: Begin Kafka transaction
    C->>O: Send validated E1
    C->>C: Stage consumed offset
    alt Success
        C->>C: Commit transaction
        Note over O: Output and offset committed together
    else Exception/abort
        C->>C: Abort transaction
        Note over K,O: Offset not committed; output aborted
    end
~~~

Spring Kafka describes Exactly Once Semantics for **read–process–write across Kafka topics**; the read/process step itself may still be invoked more than once. A Kafka transaction does not automatically make database updates, HTTP API calls, emails, or RabbitMQ/Pulsar outputs part of an atomic transaction with Kafka.

If the processor both writes to a DB and publishes to Kafka, use a consistency strategy such as transactional outbox, idempotent consumer, or compensation. Synchronizing two transaction managers is not equivalent to distributed XA atomic commit; one side can still commit before the other fails.

### 9.2. Consumer isolation and test assertions

When verifying Kafka transactional outputs, consumers must use `isolation.level=read_committed` to ignore records from aborted transactions. Using `read_uncommitted` can count uncommitted/aborted records and lead to false conclusions about exactly-once behavior.

Tests should cover:

1. E1 succeeds: output appears accurately and consumed offset advances.
2. Throw an exception after sending output but before commit: transaction aborts; `read_committed` reader sees no aborted output; offset is not committed.
3. Let consumer reprocess E1 and succeed: only one valid committed output appears for E1.
4. Kill processor mid-transaction: verify transaction fencing/recovery and no partial output.
5. Run two instances with distinct prefixes: they do not fence each other; upgrades/rolling deployments preserve instance uniqueness.

If the application enables non-blocking retries or a custom error handler, verify they are compatible with the transaction boundary created by the binder.

### 9.3. Retry and DLQ in the transactional binder

Standard binder-level retry/DLQ does not run inside the main transaction the way it does in non-transactional mode; publishing to a DLQ inside a transaction that then rolls back would roll back the DLQ record too. The transactional binder delegates retry/recovery to the listener container, using `DefaultAfterRollbackProcessor` after rollback.

Tests must verify this sequence:

1. Function throws an exception.
2. Output/offset transaction aborts.
3. After-rollback processor performs retries per policy.
4. Once retries are exhausted, recovery sends to the configured DLQ and handles committing the recovered record's offset in a new transaction when supported.

Do not copy a non-transactional `enable-dlq` configuration to the transactional binder and assume behavior stays identical. Verify `txCommitRecovered`, exception retryability, transaction manager, and recoverer in the target binder version.

## 10. Failing at the right points: crashes and redelivery

Fault injection is more informative than only throwing an exception at the start of a handler. For each event `E42`, test stopping the process at these points:

| Failure point | Non-transactional Kafka | Transactional Kafka | Rabbit/Pulsar |
|---|---|---|---|
| Before business logic | Record may be redelivered if offset uncommitted. | Transaction aborts, neither offset nor output commits. | Message unacked, redelivered per policy. |
| After business logic, before ACK/commit | External side effects may repeat. | Kafka output/offset roll back; non-Kafka side effects may still have occurred. | Side effects may repeat on redelivery. |
| After publishing output, before commit | Duplicate output may appear after restart. | Aborted output invisible to `read_committed`; offset uncommitted. | ACK and output are not automatically atomic across distinct brokers/transactions. |
| After commit/ACK | Normally not re-read once progress is saved. | Output and offset committed. | ACKed message normally not redelivered on the same subscription/queue. |
| When DLQ publish fails | Must ensure recovery does not silently drop message. | Verify after-rollback recovery and offset transaction. | Verify requeue/NACK and alerts when DLQ is unavailable. |

Verify results using **event ID + business state + broker position + output/DLQ**, not just function invocation counts. Under at-least-once, an event may invoke the handler multiple times while final business state remains exact if idempotency is properly designed.

## 11. Kafka Streams: testing stateful upgrades

If a Spring Cloud Stream application uses the Kafka Streams binder, upgrades require checks beyond ordinary consumer offsets:

- Preserve or intentionally change `application.id`: it identifies the application and governs internal topics/consumer groups.
- Preserve readability of state stores and changelogs written by the old version.
- Do not arbitrarily rename state stores, key/value serdes, or topologies if restoring existing state.
- Test state restoration on clean instances, rebalances, and task migration during rolling upgrades.
- If incompatible topology/state schema changes exist, plan versioning/migration/reset accordingly.

Tests should seed data and state with the old version, shut down the instance, start the new version with the same `application.id`, and verify aggregate/window/join outputs are neither unexpectedly reset nor duplicated. For intentional state migrations, maintain clear checkpoints and rebuild tooling.

Do not delete local state or internal changelog topics as a "quick fix" during an upgrade. Doing so can destroy required state or trigger massive replays; perform resets only as part of a verified reset plan.

## 12. Designing an integration test suite with real brokers

Use isolated brokers for tests:

- Kafka broker in Testcontainers or a staging cluster with dedicated topics/groups.
- RabbitMQ broker with dedicated queues/DLX/DLQ.
- Pulsar broker with dedicated subscriptions, schema registry, and policies.
- Dedicated Schema Registry if the Kafka architecture uses an external Avro/Protobuf/JSON Schema registry.

No in-memory Test Binder fully simulates Kafka transactions, Rabbit queue ACKs, and Pulsar cursors together. Separate test contexts by binder/driver, and do not mix the test binder onto the classpath of real-broker tests if it could auto-configure instead of the real binder.

Principles for reliable tests:

1. Create destinations and groups/subscriptions with a unique namespace per run.
2. Clean test data or generate fresh IDs per run to avoid seeing leftover messages.
3. Await conditions (poll/await) with timeouts; avoid fixed sleeps guessing broker timing.
4. Capture committed offsets, queue depths, and subscription backlogs at defined checkpoints.
5. Collect outputs and DLQs with an independent consumer and compare event ID sets.
6. Test both graceful shutdowns and hard kills.
7. Reconcile DB side effects using unique keys/idempotency tables.
8. Ensure test clients and resources are cleaned up/closed after every run.

When testing transactions directly, readers inspecting committed outputs must configure `read_committed`. When testing DLQs, ensure DLQ topics have enough partitions, matching serializers, and isolated subscriptions/queues so messages from separate cases do not mix.

## 13. Minimum regression test matrix for an upgrade

| ID | Scenario | PASS evidence |
|---|---|---|
| CT-01 | P1 → C2 reads historical V1 events. | Deserialization and semantic fields match. |
| CT-02 | P2 → C1 during mixed rollout if contract requires. | Old consumer reads safely or rollout blocks P2 per design. |
| CT-03 | Unknown fields/enums/nulls/tombstones. | Fallback or error follows contract without silent data corruption. |
| CT-04 | Key/header/partition routing. | Keys and metadata preserved, no broken ordering/idempotency. |
| OF-01 | Graceful restart in same Kafka group. | Offset not reset; remaining backlog processed continuously. |
| OF-02 | Crash before commit/ACK. | No lost events; duplicates handled by idempotency. |
| OF-03 | Mixed C1/C2 and rebalance. | Normal partition ownership/lag, no lost events. |
| MQ-01 | Rabbit queue/group preserved on upgrade. | Ready/unacked/ACK and redelivery behave accurately. |
| PS-01 | Pulsar subscription/cursor preserved. | Backlog/ACK/redelivery match subscription type. |
| DL-01 | Transient error recovers after retries. | Exact attempt count; nothing sent to DLQ. |
| DL-02 | Poison event exhausts retries. | Message appears in right DLQ with metadata. |
| DL-03 | Deserializer fails before function. | Message not lost; recovery/error path executes properly. |
| DL-04 | DLQ publish fails then recovers. | Never silently ACKs/commits and drops message. |
| TX-01 | Kafka read–process–write succeeds. | Output and offset commit together. |
| TX-02 | Throw after send before commit. | No aborted output visible to `read_committed`; offset uncommitted. |
| TX-03 | Crash and restart transactional instance. | No half-committed Kafka transaction; proper recovery. |
| TX-04 | DB/API side effect alongside Kafka. | Idempotency/outbox/compensation works when one side fails. |
| ST-01 | Kafka Streams state restore. | State/aggregates accurate after upgrade and rebalance. |
| RB-01 | Rollback C2 → C1. | Old consumer handles committed contract; progress not reset. |

For every test case, archive the **input fixture**, **version matrix**, **effective config**, **expected counts/IDs**, **actual counts/IDs**, **broker checkpoints**, and **logs/traces**. This helps separate business logic bugs from binder, broker, or deployment bugs.

## 14. Canary, shadow consumer, and rolling deployments

When testing C2 before full traffic, several rollout patterns exist:

### Canary in the same consumer group

A subset of replicas runs C2 in the same group as C1. The broker distributes partitions/messages across replicas. Advantage: exercises real traffic; drawback: you cannot directly compare the same message on C1 and C2 since each partition goes to only one Kafka consumer in the group at a time.

### Shadow consumer in a separate group

Test C2 in a separate group reading the same topic in parallel. This is ideal for comparing contracts and latency across the entire stream, but it reads from its own starting position and can cause **duplicate side effects** if DB writes, output publishing, or API calls remain active.

A shadow consumer must:

- Disable side effects or redirect outputs to sandbox destinations/DBs.
- Use a dedicated group and ACLs.
- Control backlog, offsets, and retention.
- Keep shadow data out of production business metrics and production DLQs.

### Dual producer / staged schema rollout

If the contract must change, you can support V1/V2 concurrently during transition or emit two versions to separate topics per chosen strategy. Any dual write must carry an event ID/causal link for reconciliation and to avoid duplication when consumers are active simultaneously.

For changes requiring a new partition key or altered semantics, a new topic/version and migration plan are sometimes needed rather than just swapping serializers on the same topic.

## 15. Rollback is also a contract test

Rolling back code does not automatically revert schemas, offsets, DLQs, and Kafka transaction state. Before upgrading, verify:

1. Can the old version still read new events emitted by producers during the upgrade window?
2. If not, must new producers be paused, dual-format used, or traffic moved to a V2 topic?
3. Must committed offsets/subscription cursors stay intact to avoid replays or skips?
4. Do DB schemas and side effects remain compatible with the old code?
5. Do DLQs and retry schedulers hold events the old version cannot understand?
6. Do Kafka transactional ID prefixes and producer epochs/fencing impact rollback while new and old instances overlap?
7. Can the old version still read Kafka Streams state/changelogs?

A strong rollback drill runs: start V1 → upgrade to V2 → process a batch of new events → stop V2 → start V1 in a test environment and reconcile contracts/progress/business state. If rollback cannot be done safely, clearly document the point of no return and prepare a roll-forward plan.

## 16. Post-upgrade monitoring and rollout stop conditions

During rollout, monitor:

| Metric | Warning sign |
|---|---|
| Kafka consumer lag / committed offsets | Lag climbs continuously; offsets reset or jump abnormally. |
| Rabbit queue ready/unacked | Unacked messages stuck; redeliveries climbing continuously. |
| Pulsar backlog / ack timeouts | Subscription backlog growing; frequent redeliveries. |
| Deserialization/schema errors | Consumer unable to read events from another producer version. |
| Retry/DLQ rate | Sudden spike after version change. |
| Kafka transaction aborts/fencing | Conflicting producer instance prefixes or transactions failing to commit. |
| Output uniqueness | Business events emitted/saved repeatedly beyond normal rates. |
| Processing latency p95/p99 | Poll intervals, retries, or blocking calls causing slowdowns. |
| Stateful restore duration | Kafka Streams restore taking too long or state diverging from baseline. |

Set thresholds before rollout—for example, zero deserialization errors on standard fixtures, zero lost event IDs, DLQ rate within known bounds, and consumer lag returning to baseline within an observation window. If thresholds are breached, halt the rollout and preserve artifacts and broker checkpoints before proceeding.

In transactional environments, distinguish "send attempted" metrics from "transaction committed". Calling send does not prove a record is visible to `read_committed` consumers.

## 17. End-to-end execution workflow

1. **Lock baseline:** record active versions, binding map, schemas, offsets/cursors, DLQ policy, and transaction config.
2. **Create fixtures:** valid V1/V2 messages, poison messages, malformed bytes, unknown enums, tombstones, multiple keys/partitions.
3. **Unit + contract tests:** verify semantic fields, defaults, nullability, keys, and headers.
4. **Test Binder:** prove functions, bindings, composition, and serialization operate properly at the Spring layer.
5. **Broker integration:** run real Kafka/Rabbit/Pulsar for ACK/offset/cursor, DLQ, redelivery, and security.
6. **Fault injection:** failures before/after business writes, before commit/ACK, during DLQ publish, and on restarts.
7. **Kafka transactions:** verify `read_committed`, offset/output atomicity, and external side-effect protection.
8. **Mixed rollout:** run C1/C2 in the same group or an isolated shadow group, measuring lag and output uniqueness.
9. **Rollback drill:** revert to the old version on messages already touched by the new version.
10. **Deployment gate:** allow rollout only if the regression suite and operational thresholds pass.

### Checklist before marking an upgrade successful

- [ ] V1/V2 schemas verified against the right registry/format and semantic contract.
- [ ] Old raw message fixtures remain readable by the new consumer.
- [ ] P2/C1 tested, or rollout ordering guarantees that combination is unnecessary.
- [ ] Intentional group/destination/binding name changes reconciled.
- [ ] Kafka committed offsets and rebalances do not skip messages.
- [ ] Rabbit queues/ACKs/requeues and Pulsar subscriptions/cursors did not change unexpectedly.
- [ ] Retries, DLQ, deserialization failures, and DLQ-publish failures tested against a real broker.
- [ ] Kafka transactional read–process–write and `read_committed` verified.
- [ ] Kafka transactions are not mistaken for atomic transactions with databases/APIs.
- [ ] Kafka Streams changelog/state restore tested if the app has a stateful topology.
- [ ] Idempotency and duplicate business event detection are in place.
- [ ] Rollback drill or roll-forward plan verified.
- [ ] Dashboards/alerts have clear rollout stop thresholds.
- [ ] Test artifacts, version matrix, and broker checkpoints archived for reproducibility.

Regression testing a Spring Cloud Stream upgrade must go further than verifying a function returns the expected payload. Contract tests prove old/new data compatibility; offset/ACK/cursor tests prove no events are skipped; retry/DLQ tests prove failures are isolated; and transaction tests prove Kafka outputs and progress commit or roll back within their true guarantee boundaries. Combining these test layers with mixed deployments and a rollback drill catches dangerous regressions before they disrupt production event streams.

## References

- [Spring Cloud Stream – Kafka Binder: Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring Cloud Stream – Kafka Binder: Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream – Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream – Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Kafka – Message Listener Containers and Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka – Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Cloud Stream Rabbit Binder – Dead-Letter Queue](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/README.html)
- [Spring Pulsar – Message Consumption and Dead Letter Policy](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Apache Pulsar – Schema Evolution and Compatibility](https://pulsar.apache.org/docs/4.2.x/schema-evolution-compatibility/)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)

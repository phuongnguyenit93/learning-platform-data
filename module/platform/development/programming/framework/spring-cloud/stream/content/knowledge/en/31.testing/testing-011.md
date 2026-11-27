# Testing Duplicates, Out-of-Order Events, and Schema Contracts

An event stream can receive the same event multiple times, receive events out of business order, or encounter payloads produced under a different schema version. These are normal occurrences in distributed systems: producer retries, consumer restarts, broker redelivery, DLQ replays, and staggered producer/consumer deployments can all produce them.

Testing Spring Cloud Stream therefore needs to go beyond "send one message and receive one message." Tests must prove that the consumer handles duplicates safely, detects or defers out-of-order events, and reads data versions within the committed contract boundaries.

## 1. Three Issues That Must Be Tested Separately

| Issue | Manifestation | Question to Answer |
|---|---|---|
| Duplicate delivery | The same event is delivered one or more extra times | Are business side effects applied multiple times? |
| Out-of-order delivery | An event with a later sequence is processed before an earlier one | Is the final state accurate and are gaps detected? |
| Schema incompatibility | Producer and consumer use different versions of the data structure | Can old/new consumers read data during rollout windows? |

All three issues can happen at once. For instance, a consumer receives event sequence 12 before sequence 11, fails processing 12, the broker redelivers 12, and then DLQ replays 11. Without idempotency, sequence guards, and schema compatibility tests, data can be corrupted even though no individual attempt threw an exception.

## 2. Why Can an Event Be Delivered Multiple Times?

Duplicates are not necessarily broker bugs. They routinely arise from failure windows across publishing, business processing, and progress tracking:

- The producer sends a record without receiving timely confirmation and retries. The broker may already have persisted the earlier attempt.
- The consumer completes a database update, then the process stops before the offset/ack is recorded. Upon restart, the record is redelivered.
- The consumer times out or disconnects while the broker is uncertain whether the application finished processing.
- Retry policies, redelivery, DLQ replays, or operational re-runs re-emit the same event.
- The producer emits the same business event twice due to application-layer retries or a rerun job.

Therefore, "sent once" does not imply "side effect applied once." Design consumers to be idempotent: processing the same event multiple times produces the same business outcome as processing it once.

### 2.1. Event IDs Must Be Stable

Each event should have a unique identifier that remains stable across retries and replays, such as `eventId`. Do not generate a new UUID each time a producer retries the same business operation; doing so prevents consumers from recognizing two messages as the same event.

A simple envelope:

```java
public record OrderPlaced(
        UUID eventId,
        String orderId,
        long sequence,
        int schemaVersion,
        Instant occurredAt,
        BigDecimal total,
        String currency) {
}
```

`eventId` identifies the event emission. `orderId` identifies the business aggregate. `sequence` represents the event order within an order. `schemaVersion` can aid observability or converter selection, though it does not replace a serializer's schema registry/version metadata. `occurredAt` is the business timestamp, not necessarily when the consumer receives the message.

## 3. Idempotent Consumers Using Inbox / Processed Events

A common pattern is storing processed `eventId` values in the same database transaction as the business side effect. The inbox table needs a unique constraint on the event identifier scoped to the consumer. When receiving an event:

1. Attempt to insert `eventId` into the inbox.
2. If the event already exists, treat it as a duplicate and exit without repeating side effects.
3. If the event is new, update business data within the same transaction.
4. Commit the transaction. Only after this transaction succeeds is the message considered processed at the business layer.

Example PostgreSQL schema:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

The primary key includes both `consumer_name` and `event_id` because the same event may be processed once by multiple independent consumers. If each consumer has its own database or inbox, `event_id` alone may suffice; choose the uniqueness scope matching your architecture.

```java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderPlaced event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_event
                    (consumer_name, event_id, event_type, processed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "order-projection",
                event.eventId(),
                "OrderPlaced",
                OffsetDateTime.now(ZoneOffset.UTC));

        if (inserted == 0) {
            return false; // This event was already applied.
        }

        jdbc.update("""
                UPDATE orders
                   SET total = ?, last_event_sequence = ?
                 WHERE order_id = ?
                """,
                event.total(), event.sequence(), event.orderId());

        return true;
    }
}
```

This SQL uses PostgreSQL `ON CONFLICT` syntax. On other databases, use the equivalent insert-if-absent mechanism while still relying on a database unique constraint. Never just call `existsById()` followed by `save()`: two concurrent consumers can both observe "not yet present" and both apply side effects unless the database enforces uniqueness.

A Spring Cloud Stream consumer can accept a payload or `Message<T>`:

```java
@Bean
Consumer<OrderPlaced> projectOrder(OrderProjectionService service) {
    return service::applyOnce;
}
```

With `Consumer<T>`, the service's return value does not become an output message. If you need to log duplicates, emit metrics, or classify events, use `Consumer<Message<OrderPlaced>>` and read `eventId` from payload/headers. Do not log entire payloads or sensitive data.

### 3.1. The Transaction Must Span Both Inbox and Side Effect

Writing the inbox in transaction A and updating the order in transaction B creates a failure window: the inbox may commit while the business update fails. Subsequent redeliveries see the event already in the inbox and skip it, leaving the business state permanently un-updated.

Conversely, updating business state first and writing the inbox in a separate transaction can repeat side effects if the process stops between the two steps. Keep both operations inside the same database transaction, using the same transaction manager, and ensure the method is invoked through a Spring proxy. For external side effects outside the database—such as payments, emails, or REST APIs—use idempotency keys on the target service or a suitable workflow/outbox pattern.

### 3.2. Producer Idempotency Does Not Replace Consumer Idempotency

Kafka producer idempotence reduces duplicates from producer protocol retries within a producer session/sequence scope. It does not deduplicate business events re-emitted after restarts, rerun jobs, DLQ replays, or another producer. RabbitMQ publisher confirms and Pulsar producer send acknowledgements likewise do not guarantee that consumer side effects happen only once.

Keep event IDs stable and design consumers to be idempotent even when producers or brokers offer their own deduplication features.

## 4. Testing Duplicates with the Test Binder

The Test Binder lets you send the same payload multiple times to an input binding to test idempotency logic without a real broker. For example, a test sends the same `eventId` twice and verifies that the projection is updated only once.

```java
@SpringBootTest(properties = {
        "spring.cloud.function.definition=projectOrder"
})
@Import(TestChannelBinderConfiguration.class)
class DuplicateOrderEventTest {

    @Autowired
    InputDestination input;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void appliesSameEventOnlyOnce() {
        UUID eventId = UUID.fromString("d8f6aeb0-34a1-4f30-a94f-4e2f65dcb210");
        OrderPlaced event = new OrderPlaced(
                eventId, "order-42", 1, 1,
                Instant.parse("2026-11-24T08:00:00Z"),
                new BigDecimal("250000"), "VND");

        input.send(new GenericMessage<>(event), "projectOrder-in-0");
        input.send(new GenericMessage<>(event), "projectOrder-in-0");

        await().atMost(Duration.ofSeconds(3)).untilAsserted(() -> {
            Integer count = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM processed_event
                     WHERE consumer_name = 'order-projection' AND event_id = ?
                    """, Integer.class, eventId);
            assertThat(count).isEqualTo(1);
        });
    }
}
```

This example uses Awaitility (`await`) and AssertJ (`assertThat`); add the corresponding test libraries if the project does not already include them. The test context should use an isolated test database and clean data between tests. For synchronous functions in the Test Binder, assertions can run right after `send`; use bounded waits if channels or side effects are processed asynchronously.

This test verifies consumer logic when receiving the same event twice. It does not prove a real broker will redeliver records after a crash, nor verify that offsets/acks commit properly. Those behaviors require integration tests with the corresponding broker.

## 5. Detecting Out-of-Order Events with Sequences

Ordering must be scoped by business boundaries. Usually, we need to preserve order among events belonging to the same aggregate—such as the same `orderId` or `accountId`—rather than a global order across every event in the system.

Each aggregate can increment `sequence` monotonically:

| Event | Aggregate | Sequence | Meaning |
|---|---|---:|---|
| `OrderPlaced` | `order-42` | 1 | Order created |
| `OrderPaid` | `order-42` | 2 | Payment succeeded |
| `OrderPacked` | `order-42` | 3 | Packed |
| `OrderShipped` | `order-42` | 4 | Handed to carrier |

If the consumer receives sequence 3 before sequence 2, it may be missing an event needed for a valid state transition. Relying solely on timestamps is insufficient because producer clocks can drift and events can arrive late.

Basic handling rules when the current state has `lastSequence`:

| Condition | Interpretation | Typical Action |
|---|---|---|
| `incoming == lastSequence + 1` | Next event in order | Apply and advance sequence |
| `incoming <= lastSequence` | Duplicate or stale event | Ignore safely if already processed/superseded per contract |
| `incoming > lastSequence + 1` | Sequence gap detected | Do not apply yet; store pending, retry, or request replay of missing events |

Not every event needs a contiguous sequence. If producers emit multiple independent event types or sequences increment within another scope, the consumer must understand the exact sequence contract before applying these rules.

### 5.1. Atomic Sequence Checks

Checking `lastSequence` and updating in two separate statements without locking or conditions can race when two workers process the same aggregate concurrently. Use optimistic locking, row locks, or conditional update statements to guard state transitions.

Illustrative SQL updating only when the incoming sequence is next:

```sql
UPDATE order_projection
   SET status = :new_status,
       last_sequence = :incoming_sequence
 WHERE order_id = :order_id
   AND last_sequence = :incoming_sequence - 1;
```

If the updated row count is 1, the event is applied. If 0, read the current state to distinguish duplicate/stale from a gap. Writing the inbox and updating the projection must remain in a unified transaction; when a gap is detected, do not mark the event as completed unless it has been persisted in a recoverable pending table.

## 6. Handling Sequence Gaps Instead of Dropping Events

Suppose the consumer has processed sequence 1 and receives sequence 3. Several strategies exist:

1. **Bounded retry:** keep the record unacknowledged and retry after event 2 has had a chance to arrive. Watch out for partition blocking and broker retry semantics.
2. **Durable pending inbox:** save sequence 3 into a pending table within a transaction, then wait for sequence 2. When sequence 2 arrives, process waiting consecutive events.
3. **Replay from source:** request the producer/event store to re-emit the missing sequence.
4. **Quarantine:** route the event to an error workflow with full metadata if the gap persists or violates the contract.

Do not acknowledge sequence 3 and discard it simply because sequence 2 has not arrived yet. Once acked/committed without durable storage, event 3 can be permanently lost from the stream since the broker will no longer redeliver it.

A pending table can use a unique key `(aggregate_id, sequence)` to prevent storing the same sequence twice. When the next sequence arrives, the worker processes in order and deletes the pending record after side effects commit. Bound pending counts, gap age, and alerting policies so one missing event does not cause unbounded backlog growth.

A key distinction is **durably received** versus **business-applied**. If sequence 3 arrives before sequence 2, you can insert sequence 3 into `pending_event` and acknowledge the message after the pending-save transaction commits. Do not insert sequence 3 into the `processed_event` table used for applied events; if you do, when the worker returns to process sequence 3 after sequence 2, deduplication will skip it. When sequence 2 arrives, the transaction applies sequence 2, looks up the next event in pending, applies sequence 3, and transitions each event to completed. Updating projections, pending state, and processed markers must have clear transaction boundaries.

## 7. Ordering Depends on Partitions and Concurrency

Brokers typically guarantee ordering within narrow scopes, not globally across the entire system:

| Broker | Ordering Scope to Design For |
|---|---|
| Kafka | Record order within a single partition. Use stable keys so events for the same aggregate land in the same partition. There is no total order across partitions. |
| RabbitMQ | A queue preserves enqueue/delivery order per queue semantics, yet multiple consumers, redelivery/requeue, priorities, and concurrent processing can make business completion order differ from receive order. |
| Pulsar | Ordering depends on subscription type, partitioned topics, producer batching, and key-based routing. When key ordering is needed, select the right mode/key and verify under your specific configuration. |

With Kafka, the key is usually `orderId` or `accountId`, not a random UUID per event. If the key changes across events of the same aggregate, they may land in different partitions and lose per-aggregate ordering.

Concurrency also affects completion order. A consumer may receive record A before B yet hand A and B off to two worker threads; B finishes before A. If business rules require sequential processing per key, process sequentially per partition/key or use sequencing/pending state. Never assume receive order equals side-effect completion order.

## 8. Testing Out-of-Order and Gap Scenarios

A test suite should feed events in varied orders:

| Scenario | Input | Expected Outcome |
|---|---|---|
| In order | 1, 2, 3 | Final state reflects 3 |
| Duplicate | 1, 2, 2, 3 | Event 2 applied only once |
| Swapped two events | 1, 3, 2 | 3 is held pending; after 2, 3 is applied |
| Late stale event | 1, 2, 1 | Event 1 does not regress state |
| Unfilled gap | 1, 3 then timeout | 3 remains stored pending/quarantined with an alert |
| Two interleaved aggregates | A1, B1, A2, B2 | Each aggregate maintains its own sequence independently |
| Concurrent duplicates | Two workers receive event 2 simultaneously | Unique constraint/locking permits only one side effect |

With the Test Binder, you can send messages in any desired order to test state machine logic. To test partition ordering, competing consumers, redelivery, and real concurrency, write broker integration tests. In particular, test both one key with many events and many independent keys to avoid accidentally serializing the entire system.

## 9. Schema Contracts Between Producers and Consumers

A schema describes the payload structure emitted by producers and accepted by consumers. The contract should define:

- Event name and business meaning.
- Required fields, optional fields, data types, and units.
- Nullability and default rules.
- Event ID, aggregate ID, sequence, and timestamp.
- Rules for adding, renaming, or removing fields.
- Serializer/schema versions and compatibility policies.
- How consumers handle unknown fields or new enum values.

Example JSON event:

```json
{
  "eventId": "d8f6aeb0-34a1-4f30-a94f-4e2f65dcb210",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "orderId": "order-42",
  "sequence": 1,
  "occurredAt": "2026-11-24T08:00:00Z",
  "total": 250000,
  "currency": "VND"
}
```

Do not leave each consumer to guess the schema from current payloads. Producers and consumers must share a versioned contract verified by tests.

## 10. Backward, Forward, and Full Compatibility

Schema registries and tooling typically define compatibility modes. Exact wording depends on the tool, but the general meanings are:

| Mode | Core Question | Rollout Implication |
|---|---|---|
| Backward | Can a consumer using the new schema read data written with the old schema? | New consumers can deploy before new producers |
| Forward | Can an old consumer read data written with the new schema? | New producers can deploy before all consumers upgrade |
| Full | Can old and new schemas read each other's data bidirectionally? | Supports more flexible mixed rollouts |

Some registries check against the latest version or the full history (`BACKWARD`/`BACKWARD_TRANSITIVE` and variants). Read the exact definition of your registry; do not infer deployment policy from the mode name alone.

### 10.1. Adding New Fields

Adding an optional field is generally safer than adding a new required field. New consumers must handle old records lacking the field. With Avro, the reader schema may need a default to read records written with an older schema. With JSON Schema, `default` is typically an annotation; validators do not inject default values into payloads automatically. The application must apply fallbacks when fields are absent.

### 10.2. Removing or Renaming Fields

Removing a field can prevent new consumers from reading old records if code still expects that field. Renaming is usually equivalent to deleting the old field and adding a new field; do not assume registries treat both names as the same field. A safer path uses a transition period: add the new field, have producers populate both during the compatibility window, migrate consumers to the new field, and only then retire the old field per policy.

### 10.3. Changing Data Types or Field Semantics

Changing `amount` from integer to string, changing units from VND to cents, or changing timestamp timezone/meaning can break the contract even if JSON still parses. Semantic changes are often more dangerous than syntactic changes. Introduce a new field/version or new event type when semantics are no longer compatible.

## 11. Rules Specific to Avro, JSON Schema, and Protobuf

| Format | What to Check During Evolution |
|---|---|
| Avro | Writer/reader schema resolution, defaults on new fields, unions/nullability, record names/namespaces, and registry compatibility |
| JSON Schema | `required`, `additionalProperties`, types/formats, enums, nullable, and how the app handles absent fields; `default` does not mutate payloads |
| Protobuf | Never reuse deleted field numbers; mark old numbers/names `reserved`; check wire compatibility and enum/oneof semantics |

Do not apply one blanket rule across all formats. For instance, adding a field with a default in Avro behaves differently from adding a `default` annotation in JSON Schema. Protobuf can preserve wire compatibility by field number while still breaking business semantics if a field is repurposed improperly.

## 12. Message Conversion and Native Serdes Are Two Different Layers

Spring Cloud Stream can convert payloads using `content-type` and message converters. With Kafka, applications can also use native Kafka serializers/deserializers or Serdes, especially with the Kafka Streams Binder. With Pulsar and RabbitMQ, serializers/converters can also be configured per binder.

A test sending a Java object directly into `InputDestination` may bypass part of the wire serialization/deserialization path. Therefore, distinguish:

- Testing business functions with pre-constructed objects.
- Testing message conversion with real payload bytes/Strings and content types.
- Testing serializers/Serdes with the exact implementations used by production producers/consumers.
- Testing schema registry authentication, schema lookup, and compatibility against a production-equivalent registry environment.

Do not conclude a schema contract is safe just because a function receives an object in the Test Binder. The Test Binder alone does not prove that serializers, schema registries, or broker-native Serdes use the right schema.

## 13. Testing Schema Contracts with Versioned Fixtures

Keep representative fixtures for every still-supported schema version, such as `order-placed-v1.json` and `order-placed-v2.json`. Test that new consumers read both old and new fixtures; test that new producers emit payloads conforming to the active schema.

Example deserialization test with Jackson:

```java
class OrderPlacedSchemaTest {

    private final ObjectMapper mapper = new ObjectMapper()
            .findAndRegisterModules();

    @Test
    void readsSupportedV1Payload() throws Exception {
        String json = Files.readString(
                Path.of("src/test/resources/contracts/order-placed-v1.json"));

        OrderPlaced event = mapper.readValue(json, OrderPlaced.class);

        assertThat(event.orderId()).isEqualTo("order-42");
    }

    @Test
    void readsCurrentV2Payload() throws Exception {
        String json = Files.readString(
                Path.of("src/test/resources/contracts/order-placed-v2.json"));

        OrderPlaced event = mapper.readValue(json, OrderPlaced.class);

        assertThat(event.sequence()).isEqualTo(1);
        assertThat(event.currency()).isEqualTo("VND");
    }
}
```

This snippet illustrates fixture-based deserialization; models and mappers must reflect production configuration accurately, including unknown fields, date/time modules, and null handling. If using JSON Schema, add a step validating fixtures and producer payloads with the exact schema validator. If using Avro/Protobuf, use the actual serializers/deserializers and corresponding schemas rather than just parsing JSON.

### 13.1. Testing Compatibility in CI

The pipeline can perform these steps:

1. Validate the new schema for syntax and format rules.
2. Check the new schema against the compatibility mode configured in the registry.
3. Serialize sample payloads using the production serializer.
4. Deserialize old payloads using the new consumer version.
5. If rollouts require new producers with old consumers, test the reverse direction as well.
6. Test enums, nulls, defaults, unknown fields, and boundary values.
7. Publish/register the schema only after compatibility checks pass per the release workflow.

If the registry supports compatibility checks via API/CLI, run CI checks against the real registry or a compatible test instance. Do not hard-code compatibility conclusions from a few fixtures; fixtures provide evidence for critical business cases while the registry enforces formal schema rules.

## 14. Contract Tests at the Producer/Consumer Boundary

Producer contracts verify that events are emitted with the expected fields, types, event types, and semantics. Consumer contracts verify that the application can read any payload producers are permitted to emit during compatibility windows.

A contract table might record:

| Field | Required? | Meaning | Evolution Rule |
|---|---|---|---|
| `eventId` | Yes | Stable ID for deduplication | Do not change format/meaning |
| `orderId` | Yes | Aggregate key | Never reuse for another order |
| `sequence` | Yes if ordering needed | Event order within an order | Strictly increasing per order |
| `occurredAt` | Yes | Business timestamp UTC | Keep format and units explicit |
| `total` | Yes | Total amount | Never silently change units |
| `currency` | Yes | Currency code | Values within published enum/code set |
| `note` | No | Optional note | Consumer must handle missing/null |

Contract tests must verify both structure and semantics. A payload with `total: 250000` is valid JSON yet broken in business terms if the producer thinks in VND and the consumer thinks in cents. Schema documentation should specify units, timezones, ranges, and field semantics.

## 15. Testing with the Test Binder vs. Real Brokers

Each testing layer answers a different question:

| Test Layer | Can Verify | Should Not Be Used to Conclude |
|---|---|---|
| Unit test | Idempotency rules, sequence guards, state transitions | Real broker redelivery or schema registry |
| Spring Cloud Stream Test Binder | Function bindings, basic message conversion, duplicate payloads sent repeatedly | Offsets, partitions, broker acks, transactions, or post-crash redelivery |
| Schema/contract test | Schema compatibility, old/new fixtures, serializers/deserializers | Broker topology and delivery guarantees |
| Broker integration test | Partition/key ordering, retries, redelivery, acks/offsets, DLQ, and real serializers | Production behavior under heavy load without load tests |
| Failure/load test | Crash windows, concurrency, throughput, backlogs, and recovery | Schema correctness unless contract tests also run |

The Test Binder is great for quickly verifying functions and message contracts. To prove duplicate handling under redelivery, run a test broker, send a record, let the consumer apply side effects, and stop the process before/during offset commit in a controlled scenario. After restart, confirm the record is redelivered while the side effect occurs only once.

## 16. Broker Integration Tests for Duplicates and Ordering

With Kafka, tests can create a multi-partition topic, publish events with the same key, and verify they are processed in order within a partition. Then test multiple keys to verify partitions process concurrently. To test redelivery, simulate process shutdown after database commit but before offset commit; confirm the event is re-read and the inbox unique constraint blocks duplicate side effects.

With RabbitMQ, test queue topology, manual ack/nack, requeue, competing consumers, and concurrency. With multiple consumers or retries, verify that completion order can differ from enqueue order; when business rules require ordering, apply suitable queue/consumer strategies and application-level sequence guards.

With Pulsar, test subscription types, acknowledgement timeouts, negative acknowledgements, redelivery, and key-based ordering per producer/consumer configuration. Do not infer ordering behavior from the subscription name alone; verify with the deployed binder and broker versions.

Scenarios to cover:

- Producer sends the same event ID multiple times.
- Consumer commits database changes, then stops before broker records ack/offset.
- Consumer fails before committing database changes.
- Two events for the same aggregate are processed concurrently.
- A later-sequence event arrives before an earlier-sequence event.
- DLQ replay creates a duplicate of an already-processed event.
- A new-schema producer emits payloads while an old consumer is still running.
- A new consumer reads records created by an old-schema producer.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Duplicates inflate balances or create double orders | No stable event ID or inbox lacks a unique constraint | Use idempotency keys and transactional inbox + side effects |
| Two workers apply the same event simultaneously | Non-atomic check-then-write | Rely on unique constraints and handle conflicts inside transactions |
| Newer event arriving before older event regresses state | Missing sequence check or unreliable timestamps | Use per-aggregate sequences and conditional updates |
| Sequence-gapped event is lost | Consumer acks later event and discards unmet event | Persist pending durably or retry/replay before marking complete |
| Same aggregate lands across multiple partitions | Changing keys or inconsistent partitioning | Use aggregate ID as key and verify partitioner |
| Consumer receives in order yet side effects finish out of order | Asynchronous/concurrent execution loses ordering | Serialize per key or use sequence guards |
| New consumer fails to read old records | Non-backward-compatible evolution or missing defaults/converters | Add compatibility tests with fixtures and schema registry |
| Old consumer breaks when producer adds a field | Consumer rejects unknown fields or wrong schema mode | Check `additionalProperties`, unknown-field policy, and rollout order |
| JSON parses cleanly yet data is wrong | Field changed units/semantics without updating contract | Version semantics and test boundary/domain rules |
| Test Binder passes yet broker still redelivers | Test Binder does not emulate offset/ack and crash semantics | Add broker integration tests with fault injection |

## 18. Pre-Release Testing Workflow

1. Define event ID, aggregate key, and sequence semantics for each event type.
2. Verify consumers use an inbox/idempotency store or equivalent deduplication mechanism.
3. Verify the inbox and business side effects commit in the same database transaction.
4. Define required ordering per key/partition and gap-handling rules.
5. Feed test events in order, duplicated, out of order, and with missing sequences.
6. Specify schema format, versions, and compatibility mode.
7. Run contract tests with fixtures for all supported versions.
8. Run serializer/deserializer tests using production implementations.
9. Run Test Binder tests for functions and message conversion.
10. Run broker integration tests for redelivery, acks/offsets, partition ordering, retries, and DLQs.
11. Simulate restarts/concurrency and verify no duplicate side effects and no state regression.
12. Monitor duplicate rates, sequence gaps, schema validation errors, and DLQs during canary rollouts.

## 19. Pre-Deployment Checklist

- [ ] Events carry a stable `eventId` across retries and replays.
- [ ] Consumers deduplicate using unique constraints or equivalent atomic mechanisms.
- [ ] Inbox writes and database side effects execute in the same transaction.
- [ ] External side effects have their own idempotency keys/workflows.
- [ ] Aggregate keys and sequences are clearly defined.
- [ ] Ordering requirements are scoped accurately to keys/partitions.
- [ ] Consumers handle duplicates, stale events, and sequence gaps intentionally.
- [ ] Pending/gap storage has size bounds, timeouts, and alerts.
- [ ] Schemas have contracts, versions, and compatibility policies.
- [ ] Fixtures exist for all still-supported schema versions.
- [ ] Production serializers/deserializers are tested, not only Java objects via the Test Binder.
- [ ] CI checks schema compatibility and producer/consumer contracts.
- [ ] Broker integration tests cover redelivery, ordering, retries, and DLQs.
- [ ] Monitoring tracks duplicate counts, gap age, schema errors, and replay outcomes.

Duplicate delivery is an expected characteristic of event-driven systems; consumers must be idempotent so repeated events do not repeat side effects. Ordering must be scoped per aggregate/key and protected with partitioning and sequence guards, because brokers do not provide a global order across all streams. Schema contracts must be versioned, checked for backward/forward compatibility, and tested with real serializers. Combining unit tests, the Test Binder, contract tests, and broker integration tests catches issues in both business logic and delivery semantics before release.

## References

- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/testing.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/)
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Avro — Schema Resolution](https://avro.apache.org/docs/current/specification/)
- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating)

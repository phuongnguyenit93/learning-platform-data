# Tombstones, KafkaNull, and Data Deletion Events

In Kafka, a record with a **non-null key** and a **null value** is called a tombstone. On a topic with log compaction enabled, a tombstone indicates that the current value for that key has been deleted. This is how Kafka communicates key-based state deletions, such as removing a customer from a compacted state topic.

Spring Messaging does not allow a `Message<?>` to have a Java `null` payload. Therefore, Spring for Apache Kafka provides `KafkaNull.INSTANCE` as a sentinel value when sending a tombstone through a Spring `Message`. The Kafka binder converts this sentinel into a Kafka record with a null value. When received by a Spring Cloud Stream function, a tombstone is represented by a payload of type `KafkaNull`; when using the Kafka listener API directly, the payload can be `null` and should be marked with `@Payload(required = false)`.

Tombstones fit topics storing the latest state by key. They do not replace business events containing payloads like `CustomerDeleted` when consumers need to know who performed the deletion, why, or when.

## 1. What Is a Tombstone?

A Kafka record consists primarily of topic, partition, key, value, timestamp, and headers. For a compacted topic, the key identifies the entity or state entry, and the value holds the latest state.

~~~text
Key                 Value
customer-42         { "name": "An", "status": "ACTIVE" }
customer-42         { "name": "An", "status": "SUSPENDED" }
customer-42         null       <- tombstone: deletes key customer-42
~~~

A tombstone is a real record written to the log with a key and a null value. It is not an immediate physical deletion at publish time. The Kafka log cleaner performs compaction in the background; after compaction, older values for the key are removed, and the tombstone itself is retained for a configured window before it can also be removed.

Important conditions:

- The key must be non-null so Kafka knows which key's state to delete.
- The value must be a true null at the Kafka record layer.
- The tombstone must use the exact same key and key serialization as earlier state records.
- The topic must have a cleanup policy that includes `compact`.
- Consumers must interpret a null value as a delete signal rather than a regular state object.

If you send a record with a null key and null value, Kafka has no identifier to delete a specific entry. If you send the right key with an empty string or JSON `null` as the value, that is still a non-null byte payload, not a tombstone.

## 2. Log Compaction Retains the Latest State by Key

Log compaction is a key-based log cleanup mechanism. Kafka retains the latest record for each key in compacted segments while preserving the offset order of remaining records. It differs from time- or size-based retention, which deletes entire old segments.

Example log before compaction:

~~~text
Offset  Key             Value
100     customer-42     ACTIVE
101     customer-77     ACTIVE
102     customer-42     SUSPENDED
103     customer-88     ACTIVE
104     customer-42     null
105     customer-77     PREMIUM
~~~

After the log cleaner compacts eligible segments, the final state can be represented as:

~~~text
Key             Value
customer-77     PREMIUM
customer-88     ACTIVE
~~~

The older records for `customer-42` and its tombstone have been processed so the key no longer has an active state. This happens asynchronously; never assume old records vanish immediately after sending a tombstone.

A topic can enable compaction via configuration:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic customers.state \
  --partitions 3 \
  --replication-factor 1 \
  --config cleanup.policy=compact \
  --config delete.retention.ms=86400000
~~~

In this example, `cleanup.policy=compact` enables log compaction. `delete.retention.ms=86400000` sets tombstone retention to 24 hours. These are illustrative values; choose them based on how long a consumer can be offline and how long it takes to rebuild a snapshot.

You can inspect topic configuration:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name customers.state --describe
~~~

If you use `cleanup.policy=compact,delete`, Kafka applies both compaction and time/size-based segment deletion. This can cause even the latest state for a key to disappear once its segment expires. For topics serving as the canonical state source for rebuilding projections, enabling only `compact` is usually more predictable; combine it with `delete` only when bounded retention is an intentional business decision.

## 3. Tombstones Differ from Other "Empty" Values

The following payloads have different meanings:

| Value Written to Kafka | Is It a Tombstone? | Meaning |
|---|---|---|
| Null value, non-null key | Yes | Deletes the key's state in a compacted topic |
| Empty string `""` | No | A value of length 0 |
| JSON `null` | No | Bytes containing the JSON `null` literal |
| Empty JSON object `{}` | No | An object with empty contents |
| Null key, null value | Not a useful tombstone | Cannot identify which key to delete |
| Undeserializable value | Not necessarily | Likely a serializer/deserializer error |

Do not use a DTO like `CustomerDeleted` as a tombstone if the goal is to write a null value. That DTO serializes into JSON bytes and Kafka treats it as an ordinary value. Conversely, if consumers need deletion reason, timestamp, actor, or compliance details, publish a business event with a payload instead of sending only a tombstone.

## 4. Distinguishing Tombstones from Business Deletion Events

A tombstone is a key-based state update signal. A `CustomerDeleted` event is a business event carrying data that can be retained for auditing.

| Criterion | Tombstone | `CustomerDeleted` |
|---|---|---|
| Kafka value | `null` | Non-null payload |
| Key | ID of the deleted entity | Can use the same customer ID |
| Purpose | Remove current value in a compacted topic | Publish the business fact of deletion |
| Reason/actor data | Not present in value | Can include `deletedAt`, `actor`, `reason` |
| Compaction | Removes old key state | Event record remains a value; does not delete state on its own |
| Business audit/replay | Insufficient information alone | Better suited when the contract includes needed metadata |

An architecture can emit both:

~~~text
Delete customer command
        |
        v
Customer service
        |
        +----> customers.events
        |        CustomerDeleted {
        |          eventId, customerId,
        |          deletedAt, reason, actor
        |        }
        |
        +----> customers.state (compacted)
                 key = customerId
                 value = null
~~~

The `customers.events` topic stores event history according to the contract. The `customers.state` topic stores the latest state per key; tombstones remove customer state from the compacted snapshot. These two topics serve different purposes and should not be conflated.

## 5. Sending Tombstones with KafkaNull via Spring Cloud Stream

Because Spring Messaging forbids null payloads in `Message<?>`, use `KafkaNull.INSTANCE`. The Kafka binder converts this sentinel into a record with a null value.

Example publisher using `StreamBridge`:

The state DTO is the contract serialized to a JSON value when publishing regular records:

~~~java
public record CustomerState(
    String customerId,
    String name,
    String status
) {}
~~~

Place this record in `CustomerState.java`. The publisher and consumer examples below use the same DTO from a shared contract package.

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.KafkaNull;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class CustomerStatePublisher {

    private final StreamBridge streamBridge;

    public CustomerStatePublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(CustomerState state) {
        Message<CustomerState> message = MessageBuilder
            .withPayload(state)
            .setHeader(KafkaHeaders.KEY, state.customerId())
            .build();

        return streamBridge.send("customerState-out-0", message);
    }

    public boolean delete(String customerId) {
        Message<?> tombstone = MessageBuilder
            .withPayload(KafkaNull.INSTANCE)
            .setHeader(KafkaHeaders.KEY, customerId)
            .build();

        return streamBridge.send("customerState-out-0", tombstone);
    }

}
~~~

In Spring Kafka 2.9+, `KafkaHeaders.KEY` is the header used to set the record key; older versions may use `KafkaHeaders.MESSAGE_KEY`. Use the constant appropriate for the Spring Kafka version managed by your application's BOM. The key in the tombstone must match the key used when publishing prior state, including type and serialization format.

Output binding configuration:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: customerState-out-0
      bindings:
        customerState-out-0:
          destination: customers.state
          content-type: application/json
~~~

`StreamBridge.send` returns a boolean indicating whether the message was handed off to the binding/channel. Do not treat `true` as universal proof that the record has been durably stored by the broker. If you need publish confirmation, configure producer acknowledgements/record metadata mechanisms supported by the Kafka binder and observe send results.

If using `KafkaTemplate` directly, Spring Kafka lets you send a null value via the `send(topic, key, null)` overload. For overloads accepting a Spring `Message<?>`, use `KafkaNull.INSTANCE` in place of a null payload.

## 6. Receiving Tombstones in a Spring Cloud Stream Function

When received through the Spring Cloud Stream Kafka binder, a tombstone payload is represented by `org.springframework.kafka.support.KafkaNull`. Therefore, the function should accept `Message<T>` so it can read both the payload and the key header.

The repository is an application adapter; the example below assumes it updates a projection by customer ID:

~~~java
public interface CustomerRepository {
    void save(CustomerState state);
    void deleteById(String customerId);
}
~~~

Place this interface in `CustomerRepository.java`; an actual implementation might use Spring Data, JDBC, or another projection store.

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.kafka.support.KafkaNull;
import org.springframework.messaging.Message;

@Configuration
public class CustomerStateConsumers {

    @Bean
    Consumer<Message<CustomerState>> customerStateConsumer(
            CustomerRepository repository) {

        return message -> {
            Object payload = message.getPayload();
            String key = (String) message.getHeaders()
                .get(KafkaHeaders.RECEIVED_KEY);

            if (payload instanceof KafkaNull) {
                if (key == null || key.isBlank()) {
                    throw new IllegalArgumentException(
                        "Tombstone record is missing its Kafka key"
                    );
                }

                repository.deleteById(key);
                return;
            }

            CustomerState state = (CustomerState) payload;
            repository.save(state);
        };
    }

}
~~~

`KafkaHeaders.RECEIVED_KEY` is the inbound key header in Spring Kafka 2.9+. In older versions, the constant name may be `KafkaHeaders.RECEIVED_MESSAGE_KEY`. The Java type of the key depends on the key deserializer; the example uses `String`, while byte-array keys must be decoded accordingly.

Consumer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: customerStateConsumer

    stream:
      bindings:
        customerStateConsumer-in-0:
          destination: customers.state
          group: customer-state-projection
          content-type: application/json
~~~

Do not declare the parameter simply as `CustomerState` if the function must distinguish tombstones and access the key. Using `Message<CustomerState>` allows reading both the sentinel payload and headers. Across different binder versions, verify how the converter handles tombstones with an integration test.

### When Using the Kafka Listener API Directly

When using `@KafkaListener` instead of a Spring Cloud Stream function, Spring Kafka can pass a genuine `null` payload. Mark the payload parameter as optional and read the key from the header:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class CustomerTombstoneListener {

    private final CustomerRepository customerRepository;

    public CustomerTombstoneListener(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @KafkaListener(
        id = "customer-tombstone-listener",
        topics = "customers.state"
    )
    public void listen(
            @Payload(required = false) CustomerState value,
            @Header(KafkaHeaders.RECEIVED_KEY) String key) {

        if (value == null) {
            customerRepository.deleteById(key);
        } else {
            customerRepository.save(value);
        }
    }
}
~~~

In this API, the `value` parameter is `null` when receiving a tombstone; it is not a `KafkaNull` object. Do not mix the two representations: Spring Cloud Stream functions use the sentinel message payload, whereas listener methods can use `@Payload(required = false)` to receive `null`.

## 7. Keys Must Remain Stable from Write to Delete

Compaction operates per key within each partition. Therefore, producers must use the same key for every state version and tombstone:

~~~text
customer-42 -> ACTIVE
customer-42 -> SUSPENDED
customer-42 -> null       (delete)
~~~

If state records use key `customer-42` while the tombstone uses key `42`, Kafka treats them as two different keys and will not delete the old state.

Points that must remain consistent:

- Keys represent a stable business identifier, such as customer ID.
- Key serializer and byte representation are identical across state records and tombstones.
- Producers use the same partitioning strategy so keys are written to the same partition.
- Never change key types from `String` to `Long` or alter string normalization without a migration plan.
- Do not use a custom business header instead of the Kafka record key unless the binder is configured to map that header to the key.

When partition count changes, the default partitioner may map a key to a different partition. Compaction only processes keys within each partition; it does not merge records with the same key across two partitions. For a compacted topic storing state, increasing partitions can leave an old value in the previous partition while the new value/tombstone goes to another partition. Plan a migration or rebuild the topic if changing partition count affects key mapping.

## 8. Tombstones and Kafka Streams KTable

Kafka Streams uses key/value semantics to represent state tables. For a `KTable<K, V>`, a record with a null value is interpreted as deleting the key from the table. This aligns with tombstones on a compacted topic.

~~~java
KTable<String, CustomerState> customers =
    builder.table("customers.state");
~~~

If the topic emits:

~~~text
customer-42 -> CustomerState(...)
customer-42 -> null
~~~

then `KTable` no longer has a row for `customer-42` after processing the tombstone. The state store and related changelog streams also reflect the deletion according to Kafka Streams semantics.

Distinguish `KTable` from `KStream`: `KTable` represents the latest state per key, whereas `KStream` represents a stream of records. In `KStream`, a null-value record is still an emitted record and operators must handle null explicitly. Never access value fields before checking for null.

Tombstones are also used in state store changelog topics to record key deletions. Do not manually delete records from changelog or compacted topics outside Kafka Streams while an application manages the state store; use appropriate APIs and migration procedures.

## 9. How Long Are Tombstones Retained?

Kafka does not drop tombstones immediately when the producer sends them. The log cleaner runs in the background and only compacts eligible segments. After a tombstone has been kept for at least `delete.retention.ms`, the marker can be purged during a compaction pass alongside old values for that key.

`delete.retention.ms` also sets the time window within which a consumer rebuilding a snapshot from offset 0 must finish in order to guarantee seeing the necessary tombstones. If a consumer lags beyond this window, tombstones may be purged by the cleaner before the consumer reaches them; the consumer's local state could retain already-deleted data.

Choose tombstone retention based on:

- Maximum duration a consumer may remain offline.
- Topic size and how long a consumer takes to scan from the beginning.
- Recovery time after outages or upgrades.
- Replay policies and projection rebuild mechanisms.
- Tolerance for incomplete snapshot reconstruction.

For consumers backed by a local database, establish a bootstrap/snapshot or rebuild procedure if they exceed the tombstone retention window. Do not assume a consumer can stay offline indefinitely, replay a compacted topic, and still see every historical delete marker.

## 10. Tombstones Do Not Replace Deletion in Downstream Systems

Sending a tombstone only writes a record to Kafka. It does not automatically delete rows in a database, cache, search index, or object storage. Each consumer must receive the tombstone and execute the deletion in its own projection.

For example, a customer deletion event might flow across multiple projections:

~~~text
customers.state
      |
      +----> customer-search-index: delete document
      |
      +----> customer-cache: evict key
      |
      +----> customer-reporting: remove current row
      |
      +----> customer-state-store: remove key
~~~

If one consumer fails or misses the tombstone, data in that projection may remain. Monitor consumer lag, processing errors, DLQs/quarantines, and replay capability. For sensitive data or regulatory deletion requirements, establish a verified deletion workflow with auditing and reconciliation across all copies; a tombstone is a state propagation signal, not proof that every system has completed deletion.

## 11. Testing Tombstones End-to-End

Tests should verify both the Kafka record key/value and consumer behavior.

### Testing Publishing

Use `KafkaTemplate` to produce two state updates and one tombstone:

~~~java
// In the test method, declare throws Exception to wait for the send result.
kafkaTemplate.send(
    "customers.state",
    "customer-42",
    new CustomerState("customer-42", "An", "ACTIVE")
).get();

kafkaTemplate.send(
    "customers.state",
    "customer-42",
    new CustomerState("customer-42", "An", "SUSPENDED")
).get();

kafkaTemplate.send(
    "customers.state",
    "customer-42",
    null
).get();
~~~

The `send(topic, key, value)` overload of `KafkaTemplate` allows a null value. If sending via Spring Messaging `Message<?>`, use `KafkaNull.INSTANCE` because Spring `Message` rejects null payloads.

### Testing Consumption

- Send a state record and verify the consumer creates/updates the projection.
- Send a tombstone with the same key and verify the consumer deletes the projection.
- Send a tombstone without a key and verify the application rejects or warns on it.
- Send an empty string or JSON `null` and verify they are not mistaken for a tombstone.
- Send with the same key serializer/partitioner used in production.
- Restart the consumer and verify state is rebuilt accurately from the compacted topic.

### Testing Compaction

Compaction runs asynchronously, so do not assert that old records disappear immediately after sending a tombstone. Test consumer logic by reading tombstones first; test compaction separately using a test topic, cleaner configuration, and appropriate wait times. In automated tests, prefer verifying that the consumer receives a null value and deletes the projection rather than depending on when the log cleaner runs.

Use Testcontainers Kafka or an embedded Kafka broker to test serialization, key headers, tombstone values, and binder converters. Unit tests that merely invoke a method with `KafkaNull.INSTANCE` do not prove the binder actually writes a null value to Kafka.

## 12. Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| Consumer does not delete state | Producer sent a `CustomerDeleted` DTO instead of a null value | Use `KafkaNull.INSTANCE` or `KafkaTemplate` with a null value |
| Tombstone does not delete old key | Key differs from the state record's key | Use the exact same key and serializer |
| Function throws error on receiving tombstone | Code assumes payload is always the DTO | Accept `Message<T>` and check for `KafkaNull` |
| Consumer listener does not receive tombstone | Payload is marked required | Use `@Payload(required = false)` with direct Kafka listeners |
| Empty string triggers accidental deletion | Code treats empty string as null | Distinguish zero-byte values from Kafka null |
| Consumer rebuilding state misses deletes | Consumer was offline longer than `delete.retention.ms` | Adjust retention and snapshot/rebuild procedures |
| Compaction has not removed old records yet | Log cleaner has not processed the segment yet | Wait for compaction; do not expect instant removal |
| Some keys retain old values after partition expansion | New keys routed to a different partition | Plan migration/rebuild of the compacted topic |
| Audit lacks who deleted and why | Only a tombstone was emitted | Also emit a business event `CustomerDeleted` |

## 13. Practice Sequence and Completion Criteria

Work through the exercise with a customer state topic:

1. Create topic `customers.state` with `cleanup.policy=compact`.
2. Define `CustomerState` and standardize on customer ID as the Kafka key.
3. Write a publisher using `StreamBridge` that sends state records with `KafkaHeaders.KEY`.
4. Write a `delete` method using `KafkaNull.INSTANCE` and keeping the same key.
5. Configure the output binding pointing to `customers.state`.
6. Write a Spring Cloud Stream consumer accepting `Message<CustomerState>`.
7. Check for `KafkaNull` payload, read `KafkaHeaders.RECEIVED_KEY`, and delete the corresponding projection.
8. Send state, update state, and send a tombstone for the same customer ID.
9. Verify the consumer deletes the right key; confirm other keys remain intact.
10. Test empty strings, JSON `null`, and a keyless tombstone to distinguish semantics.
11. Observe the log cleaner and test rebuilding a snapshot within the `delete.retention.ms` window.
12. Emit an additional `CustomerDeleted` event if audit, reason, or actor is needed.
13. Run integration tests with the real Kafka binder and record your Spring Cloud Stream/Spring Kafka versions.

This exercise is complete when you can explain a tombstone's record key/value; send tombstones using `KafkaNull.INSTANCE`; receive and recognize tombstones through Spring Cloud Stream; delete projections by key; configure compacted topics; and design retention/replay so consumers do not miss delete markers.

## 14. Official References

- [Spring Cloud Stream — Tombstone Records](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/tombstone.html) — how to receive tombstones in Spring Cloud Stream functions.
- [Spring for Apache Kafka — Null Payloads and Log Compaction of Tombstone Records](https://docs.spring.io/spring-kafka/reference/kafka/tombstones.html) — `KafkaNull.INSTANCE`, sending null payloads, and receiving tombstones.
- [Apache Kafka — Log Compaction](https://kafka.apache.org/documentation/#compaction) — compaction semantics, delete markers, and consumer scan boundaries.
- [Apache Kafka — Topic Configs](https://kafka.apache.org/43/configuration/topic-configs/) — `cleanup.policy`, `delete.retention.ms`, and topic configurations.
- [Spring Kafka — KafkaHeaders API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/support/KafkaHeaders.html) — outbound and inbound Kafka key headers.
- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html) — Kafka binder configuration and integration.

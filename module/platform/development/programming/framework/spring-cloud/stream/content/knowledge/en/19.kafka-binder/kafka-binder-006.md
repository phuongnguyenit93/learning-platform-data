# Consuming from Multiple Topics or Topic Name Patterns

A Kafka consumer application may need to read multiple topics within a single processing stream. For example, an audit service might need to receive order-created, order-cancelled, and order-shipped events; a versioned processor might need to read every topic matching the pattern `orders.*`. The Spring Cloud Stream Kafka Binder supports both approaches: listing multiple topics in the `destination` property or registering a regular expression so the Kafka consumer discovers matching topics.

These two approaches serve different purposes. A topic list is suitable when the set of topics is known and stable. A topic pattern is suitable when topics are created according to a naming convention and the application needs to automatically pick up new topics matching the pattern. With either approach, a single input binding still has one consumer configuration and one consumer group; therefore, you must consider schemas, offsets, access permissions, and how to distinguish the source topic before combining them into the same binding.

## 1. A Single Input Binding Can Read Multiple Topics

In the functional model, an input binding typically takes the function name plus the `-in-0` suffix. For example, the function bean `auditEvents` creates the binding `auditEvents-in-0`. The binding's `destination` property can accept a comma-separated list of Kafka topics:

```yaml
spring:
  cloud:
    function:
      definition: auditEvents
    stream:
      bindings:
        auditEvents-in-0:
          destination: orders.created,orders.cancelled,orders.shipped
          group: order-audit
          content-type: application/json
```

With this configuration, a single input binding subscribes to consume from three topics. The Kafka Binder connects the binding to the corresponding topics and uses the consumer group `order-audit`. All messages from the three topics enter the same function:

```java
@Bean
Consumer<OrderEvent> auditEvents() {
    return event -> auditService.record(event);
}
```

The destination list applies to the input binding. Every topic in the list shares binding configuration such as group, content type, concurrency, retries, and Kafka Binder consumer properties. If one topic needs a different group, content type, security policy, or error handling, consider creating a separate binding.

Do not include unnecessary spaces or separator characters in topic names. Each topic must exist or be provisioned according to Kafka Binder/broker policy. If the environment disables automatic topic creation, administrators must pre-create all topics and grant permissions to the application.

## 2. Distinguishing Multiple Topics from Multiple Consumer Groups

When one binding reads multiple topics, those topics are consumed within the same consumer group. Kafka manages offsets per topic-partition pair. Consumer instances in the same group share partitions across all topics the group subscribes to.

For example, group `order-audit` reads three topics:

| Topic | Partitions | Consumption Progress |
|---|---|---|
| `orders.created` | 0, 1 | Separate offset per partition |
| `orders.cancelled` | 0, 1 | Separate offset per partition |
| `orders.shipped` | 0, 1 | Separate offset per partition |

If two independent applications both need to receive all events, each application needs its own consumer group. If two instances of the same application use the same group, Kafka distributes partitions between them instead of delivering every message to both instances.

Having one binding read multiple topics does not establish a global ordering across topics. Kafka only guarantees ordering within each partition. Messages from `orders.created` and `orders.cancelled` may be read or processed interleaved; business ordering cannot be inferred from topic names alone. If business logic requires ordering, carry an aggregate version/sequence or design the event stream around a shared partition key and explicit convention.

## 3. Reading the Source Topic from Message Headers

When multiple topics enter the same binding, the function often needs to know which topic a message came from in order to choose the right logic. The Kafka Binder puts record metadata into Spring Message headers. You can read the topic, partition, and offset using Spring Kafka headers:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> auditEvents() {
    return message -> {
        String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
            .get(KafkaHeaders.OFFSET, Long.class);

        OrderEvent event = message.getPayload();
        auditService.record(topic, partition, offset, event);
    };
}
```

These headers help identify the data source and investigate messages. They do not replace an `eventType` in the payload: the topic tells you where the record was stored, whereas `eventType` describes business semantics. If the same topic holds multiple event types, consumers still need a discriminator in the payload or schema.

Do not use the topic name as a source of producer or tenant authentication. The topic is routing metadata supplied by the broker; publish and read permissions must be enforced using Kafka ACLs, client identities, and application policies.

## 4. When Should You Use a Topic Pattern?

If topics are created following a naming convention, such as:

- `orders.created.v1`
- `orders.cancelled.v1`
- `orders.shipped.v1`
- `orders.created.v2`

then updating the destination list every time a new topic appears can become tedious. The Kafka Binder supports subscribing a consumer using a regular expression. In that case, `destination` is interpreted as a topic name pattern expression rather than a fixed topic name.

Example:

```yaml
spring:
  cloud:
    function:
      definition: auditEvents
    stream:
      bindings:
        auditEvents-in-0:
          destination: '^orders\.(created|cancelled|shipped)\.v[0-9]+$'
          group: order-audit
          content-type: application/json
      kafka:
        bindings:
          auditEvents-in-0:
            consumer:
              destination-is-pattern: true
```

Here, `destination` is a regular expression. The `destination-is-pattern` property belongs to Kafka Binder consumer properties and must be enabled so the binder interprets `destination` as a `Pattern`. The regex above only matches topics starting with `orders.`, followed by `created`, `cancelled`, or `shipped`, and then a version segment like `v1`, `v2`, `v3`, and so on.

Anchor the regex with `^` and `$` to avoid matching topics with unexpected prefixes or suffixes. Use explicit alternation groups and version constraints instead of overly broad patterns like `.*`; a broad regex can cause the application to accidentally read internal topics or topics belonging to another business domain.

## 5. Discovering New Topics Matching a Pattern

The Kafka consumer subscribes to the pattern and the broker returns topics currently matching it. When a new topic is created whose name matches the regex, the consumer can pick up that topic after metadata is refreshed.

Discovery latency for new topics depends on the consumer property `metadata.max.age.ms`. Current Kafka Binder documentation notes the Kafka client default is 300,000 ms (5 minutes). It can be tuned in consumer configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvents-in-0:
          destination: '^orders\..*\.v[0-9]+$'
          group: order-audit
      kafka:
        bindings:
          auditEvents-in-0:
            consumer:
              destination-is-pattern: true
              configuration:
                metadata.max.age.ms: 30000
```

This example sets metadata refresh to 30 seconds. A smaller value can detect new topics faster, but also increases metadata refresh frequency. Choose a value based on operational requirements and cluster load; do not treat it as an absolute time guarantee between topic creation and when the consumer starts reading.

For a newly discovered topic, the consumer group still needs to determine the starting offset according to `startOffset` and Kafka's offset policy. If the group has no committed offset for the new topic-partition yet, the consumer applies the configured starting rule. Decide explicitly whether you need to read history from new topics or only care about messages produced after the consumer begins listening.

## 6. Differences Between Topic Lists and Regex Patterns

| Criterion | Destination List | Topic Pattern |
|---|---|---|
| Configuration | `orders.created,orders.cancelled` | Regex in `destination` |
| Requires `destination-is-pattern` | No | Yes |
| Topic set | Explicitly declared | Determined by topic names matching the regex |
| New topics | Requires updating config or bindings | Automatically discovered on metadata refresh |
| Topic provisioning | Binder can provision known names if permitted | Binder does not provision topics because the exact set of names is unknown |
| Kafka Binder `enable-dlq` | Configurable as supported by binding/binder | Not supported when `destination-is-pattern=true` |
| Primary risk | Forgetting to add new topics or config drift | Overly broad regex or accidentally consuming out-of-scope topics |

Do not combine comma-separated lists with regex patterns in the same `destination`. Choose one representation per input binding. If a fixed set of topics needs specific policies, use an explicit list; if topics are created dynamically under a naming convention with uniform handling, use a pattern.

## 7. Provisioning and DLQ Limitations When Using Patterns

When `destination-is-pattern` is enabled, the Kafka Binder does not know the exact names of matching topics at binding provisioning time. Therefore:

- The binder does not automatically create topics matching the regex.
- Topics must be created by a Kafka administrator, deployment platform, or producers with appropriate permissions.
- The Kafka Binder does not allow enabling `enable-dlq` on a binding using a destination pattern, because the binder cannot provision DLQs for an unknown set of topics.

This is an important distinction when designing error handling. If you need a DLQ for a pattern subscription, design an application-level error flow or use a centralized error sink with a fixed destination name. When sending errors to a shared topic, record the source topic, partition, offset, key, event ID, and exception metadata in the error record for investigation.

Do not assume enabling `autoCreateTopics` on the binder will create topics matching a regex. Likewise, do not enable `enableDlq` expecting the binder to automatically infer a separate DLQ for topics that do not exist at startup.

## 8. All Topics in One Binding Must Have Compatible Data Contracts

A binding has a single content type configuration and a single deserialization/conversion strategy. When grouping multiple topics into one binding, messages must have formats compatible with how the consumer converts payloads.

For example, if all three topics send the same envelope:

```java
public record DomainEvent(
    String eventId,
    String eventType,
    int schemaVersion,
    JsonNode payload
) {}
```

then a single consumer can deserialize every topic into `DomainEvent` and dispatch by `eventType`. If `orders.created` sends `OrderCreated`, `orders.cancelled` sends `OrderCancelled`, and `orders.shipped` sends an entirely different schema, a `Consumer<OrderCreated>` is not a safe choice for a binding reading all three.

There are three ways to handle this:

1. Standardize the topics to share a common envelope/schema and dispatch the inner payload by `eventType`/`version`.
2. Accept `byte[]` or an intermediate type and select a deserializer by source topic, if the application genuinely needs to support multiple wire formats.
3. Create separate bindings for individual topics or groups of topics that have different schemas and policies.

Do not rely solely on topic names to guess schemas if producers can change conventions. Manage schema version, content type, and `eventType` as part of the event contract.

## 9. Consumer Groups, Partitions, and Scalability

A consumer group reading multiple topics receives the total partitions across all subscribed topics. Kafka distributes those partitions among the consumer instances in the group. If total partitions exceed consumer count, one consumer may be assigned multiple partitions. If consumers exceed total partitions, some consumers will have no partitions to process.

Binding concurrency increases the number of internal consumers within each instance. For example, three topics with four partitions each yield twelve partitions in total. If the application runs three replicas with concurrency two, the group has up to six consumers; each consumer may receive roughly two partitions depending on the assignment strategy.

Adding a new topic changes the total partition count and triggers a rebalance. Monitor rebalance duration, lag, and load per topic/partition. Do not scale concurrency indefinitely; database capacity and downstream systems remain the real bottlenecks.

## 10. Access Permissions and Topic Scope Control

Consumers using either a topic list or a regex require read permissions for the corresponding topics. With patterns, permissions must also cover topics created in the future. Depending on cluster configuration and ACL mechanics, consumers may need metadata describe permissions to discover matching topics.

Guidelines:

- Use domain-specific prefixes and naming conventions, such as `orders.*`.
- Restrict regexes to the specific event types and versions to be consumed.
- Grant minimal `Read`/`Describe` ACLs for the valid set of topics.
- Never use a broad regex to read every topic in the cluster.
- Verify newly created topics have the right owner, retention, partition count, and schema policy.
- Monitor the actual list of topics the binding is subscribed to.

A topic matching a regex does not mean the application is authorized to process all data in that topic. Producer authentication, ACLs, and event type validation must still be enforced.

## 11. When Should You Split into Multiple Bindings?

Use a single binding for multiple topics when the topics share:

- Consumer group and load-sharing requirements.
- Content type, serializer/deserializer, and schema envelope.
- Retry, DLQ/error handling, and acknowledgement policies.
- Access permissions and operational lifecycle.
- Compatible processing objectives and ordering requirements.

Split bindings if a topic needs a different schema, a different consumer group, different retry settings, or different retention or access permissions. For instance, an audit service might read `orders.created` and `orders.cancelled` in one binding if both share the same envelope. A separate payment-processing consumer may need an independent binding and group so it is unaffected by traffic spikes or failures in the order stream.

## 12. Complete Example: Reading Order Topics by Pattern

Suppose teams publish topics following this convention:

- `orders.created.v1`
- `orders.cancelled.v1`
- `orders.shipped.v1`
- `orders.created.v2`

The audit service reads all versioned order events:

```yaml
spring:
  cloud:
    function:
      definition: auditOrders
    stream:
      bindings:
        auditOrders-in-0:
          destination: '^orders\.(created|cancelled|shipped)\.v[0-9]+$'
          group: audit-service
          content-type: application/json
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              destination-is-pattern: true
              configuration:
                metadata.max.age.ms: 60000
```

The consumer receives a common envelope and logs the source topic:

```java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<DomainEvent>> auditOrders(AuditService auditService) {
    return message -> {
        String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);

        DomainEvent event = message.getPayload();
        auditService.record(topic, event.eventId(),
            event.eventType(), event.schemaVersion(), event.payload());
    };
}
```

In this example, metadata is refreshed every 60 seconds to discover new matching topics. Topics must be provisioned externally; `audit-service` uses a shared consumer group. Because the binding uses a regex, the Kafka Binder does not support `enable-dlq` on this binding. If error storage is needed, design a separate error flow and record the source topic alongside record metadata.

## 13. Testing Topic Lists and Patterns

Testing should cover these scenarios:

- Start a binding with a multi-topic list and verify messages from each topic arrive at the consumer.
- Send a message to a topic not in the list and verify the consumer does not receive it.
- Start a binding with a regex and verify all currently matching topics are subscribed.
- Create a new topic matching the regex after the consumer is already running; verify it is discovered after a metadata refresh.
- Create a topic not matching the regex and verify it is not subscribed.
- Verify offsets per topic-partition within the same consumer group.
- Verify received topic/partition/offset headers and event type in the payload.
- Send a payload with a different schema to one topic in the set; verify conversion errors are observed and handled per policy.
- Verify the regex binding does not enable Kafka Binder `enable-dlq`; test the alternative error flow if present.
- Verify ACLs when a new topic is provisioned and the consumer begins reading.

The Test Binder can verify function logic and bindings at the application level, but it does not fully simulate Kafka topic discovery, metadata refresh, regex subscription, partition assignment, and ACLs. Integration tests with real Kafka or an equivalent broker test environment are required to validate those behaviors.

## 14. Implementation Checklist

- [ ] Chosen either a destination list or a regex for each input binding.
- [ ] If using a list, topics are comma-separated and exist/provision per policy.
- [ ] If using a regex, `spring.cloud.stream.kafka.bindings.<binding>.consumer.destination-is-pattern` is enabled.
- [ ] Regex is anchored and constrained by domain/event/version.
- [ ] `metadata.max.age.ms` is configured according to new-topic discovery requirements.
- [ ] Offset policy for new topics and a stable consumer group are defined.
- [ ] All topics in the binding have compatible content types/schemas.
- [ ] Function can identify the source topic via `KafkaHeaders.RECEIVED_TOPIC` when needed.
- [ ] Total partitions across all topics are accounted for when choosing concurrency and replica count.
- [ ] Topics are provisioned and appropriate `Read`/`Describe` ACLs are granted.
- [ ] If using a pattern, Kafka Binder `enable-dlq` is not configured; an alternative error flow is designed if needed.
- [ ] New topics, non-matching topics, schema errors, rebalances, and metadata refreshes have been tested against real Kafka.

A single input binding can read multiple known topics via a destination list or automatically discover new topics via regex. Lists fit fixed topic sets; patterns fit controlled naming conventions. When combining multiple topics, ensure schemas and consumer policies are compatible, distinguish message sources via headers, enforce ACLs, and remember that pattern subscriptions do not support topic provisioning or the Kafka Binder DLQ.

## References

- [Spring Cloud Stream 5.1 — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html)

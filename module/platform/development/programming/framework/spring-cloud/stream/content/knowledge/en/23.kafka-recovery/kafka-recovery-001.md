# Configuring enableDlq, dlqName, and Consumer Group Requirements

When a Kafka consumer cannot process a message after the configured number of retry attempts, the system needs a place to hold the message for investigation or later processing. Spring Cloud Stream's Kafka Binder supports a **dead-letter topic (DLT/DLQ)**: failed messages are published to a separate Kafka topic after processing fails according to the retry policy.

Three configurations that must be understood together are `enableDlq`, `dlqName`, and `group`. `enableDlq` enables forwarding failed messages to a dead-letter topic; `dlqName` lets you specify that topic's name; `group` identifies the logical consumer group receiving the original message and is required so the Kafka Binder can identify where to handle errors. An anonymous consumer has no stable group and therefore cannot use this DLQ mechanism in the standard way.

This lesson belongs to the **Kafka Recovery** chapter of the `SPRING_CLOUD_STREAM` module, focusing on Kafka Binder configuration in the `Supplier`/`Function`/`Consumer` functional model, DLQ naming, the relationship between consumer groups and DLQs, topic provisioning, retries, partitioning, access permissions, replay, and testing.

## 1. What Problem Does a DLQ Solve?

A consumer may encounter messages that cannot be processed automatically: invalid payload schemas, invalid business data, references to non-existent entities, or a dependency that fails continuously. If it simply retries indefinitely, that message can block the processing stream, generate unnecessary load, and cause consumer lag to grow.

A DLQ is a dedicated topic to hold messages that have failed after the error-handling policy. The main consumer continues processing new messages according to the binder/broker mechanism, while failed messages are retained for investigation, data repair, or replay once the root cause is fixed.

```text
Kafka topic: orders.events
          |
          v
Consumer group: order-processor
          |
          v
   processOrder function
          |
          +---- processing succeeded ----> complete per commit/ack mechanism
          |
          +---- processing failed
                    |
                    v
             Retry as configured
                    |
          +---------+---------+
          |                   |
      Succeeded        Attempts exhausted
                              |
                              v
                 Kafka dead-letter topic
                 orders.events.order-processor.dlq
```

A DLQ does not fix messages and does not resolve errors by itself. It preserves evidence of failed messages, keeping the main flow from getting stuck on an unprocessable record. The operations team still needs a workflow for observing, triaging, fixing errors, and replaying.

## 2. Distinguishing destination, consumer group, and DLQ name

These three names represent three distinct roles:

| Property | Role | Example |
|---|---|---|
| `destination` | Source Kafka topic from which the binding receives messages | `orders.events` |
| `group` | Logical consumer group coordinating processing of the source topic | `order-processor` |
| `dlqName` | Kafka topic receiving failed messages | `orders.events.order-processor.dlq` |

`destination` and `group` are declared on the general Spring Cloud Stream binding. `enableDlq` and `dlqName` are Kafka Binder-specific properties, placed under the Kafka consumer configuration for that binding.

Do not use the DLQ name as `group`. The DLQ is the target topic for storing failed records; the group is the logical consumer identity for the source topic. A single source topic can have multiple independent groups, each processing the same data for different purposes.

## 3. Why Does Kafka DLQ Require a Consumer Group?

The Kafka Binder requires a consumer group to be declared when enabling a DLQ. A consumer that does not declare `group` is an anonymous consumer; it lacks a stable processing identity for the binder to attach an error policy and dead-letter destination per group.

Explicitly declaring a group helps:

- Identify which replicas are coordinating to process the same business stream.
- Distinguish multiple independent applications reading from the same topic.
- Generate a default DLQ name tied to the destination and group.
- Keep DLQ configuration stable when the application restarts or scales.
- Prevent anonymous consumers from producing unpredictable error-handling behavior.

Example of two applications reading `orders.events`:

| Consumer | Group | Purpose | Default DLQ by binder convention |
|---|---|---|---|
| Inventory projection | `inventory-projection` | Update inventory | `orders.events.inventory-projection.dlq` |
| Analytics projection | `analytics-projection` | Update metrics | `orders.events.analytics-projection.dlq` |

The two groups receive data independently and may have different error-handling outcomes. A message might succeed in inventory but fail in analytics; in that case, only the analytics flow needs to keep the message in its own DLQ.

Do not create a new group per pod/replica. Replicas of the same logical consumer must share the same group to distribute load; if each replica uses its own group, each group may receive a full copy of the topic stream.

## 4. Configuring `enableDlq`

Suppose an application has a `processOrder` function receiving order events from the `orders.events` topic. Configure the consumer group and enable DLQ:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
```

Explanation:

- `processOrder-in-0` is the input binding of the `processOrder` function.
- `destination: orders.events` selects the source topic.
- `group: order-processor` creates a consumer group with a stable identity.
- `max-attempts: 3` allows up to three processing attempts, including the initial attempt.
- `enable-dlq: true` enables Kafka Binder dead-letter handling for this binding.

`enable-dlq` belongs to the `spring.cloud.stream.kafka.bindings.<bindingName>.consumer` namespace. It is not a generic property used identically for RabbitMQ or Pulsar. Other binders have their own dead-letter mechanisms.

When the handler continues to fail after the allowed number of attempts, the Kafka Binder can route the message to the DLQ according to the binder's error handling. If the handler succeeds during a retry, the message does not need to be sent to the DLQ.

## 5. Configuring `dlqName`

If no custom name is specified, the Kafka Binder uses a default DLQ naming convention based on the destination and group, typically in the form:

```text
<destination>.<group>.dlq
```

With `destination = orders.events` and `group = order-processor`, the conventional name is:

```text
orders.events.order-processor.dlq
```

You can specify a different topic name using `dlq-name`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.failed.v1
```

`dlq-name` is the name of the Kafka topic that receives failed messages. This name must follow topic naming rules and be provisioned or permitted for auto-creation per cluster policy. Using a clear name helps the operations team identify error streams, though you should avoid sharing one DLQ across multiple consumers with different schemas and processing permissions unless there is a unified contract.

Default names and provisioning details may depend on the Kafka Binder version. For production, you should configure `dlq-name` explicitly when topic names are part of managed infrastructure, then verify the actual topic when the application starts.

## 6. Complete Consumer Function Example

The function can be a standard `Consumer<OrderEvent>`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
```

If `orderService.process` throws an exception, the error is passed into the binding's error-handling mechanism. The binder applies retries as configured; when retries fail and DLQ is enabled, the message is forwarded to the error topic according to the Kafka Binder configuration.

This example assumes `OrderService` throws an exception when processing fails. If the service catches the exception itself and only logs or returns normally, the binder will not see the error to apply retry/DLQ. Only catch errors when the application has genuinely handled them or intentionally delegates error responsibility to another mechanism.

## 7. `maxAttempts` Determines When a Message Goes to the DLQ

The DLQ typically receives a message after the consumer's retry mechanism has exhausted its attempts. `max-attempts` is the total number of processing attempts, including the first one.

| `max-attempts` | Initial attempt | Maximum retries |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 5 | 1 | 4 |

For example, `max-attempts: 3` means the handler can be invoked up to three times for a message before error handling moves to the next step. It does not mean three retries in addition to the initial attempt.

You can configure backoff to avoid continuous tight retries:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 8000
            back-off-multiplier: 2.0
```

Retry and DLQ address two different stages: retry is for recoverable errors; DLQ retains messages when automatic processing fails. Do not increase `max-attempts` indefinitely to avoid the DLQ, because data errors or programming bugs usually do not resolve themselves on retry.

## 8. Classifying Errors Before Routing to the DLQ

Not every error should be retried. Transient errors such as timeouts or intermittent dependency broker disruptions may recover. Schema errors, malformed data, or business rule violations usually require isolation or data correction.

| Error type | Example | Handling approach |
|---|---|---|
| Transient error | API returns 503, connection reset | Bounded retry with backoff |
| Overload | Dependency returns 429 | Backoff; respect dependency limits |
| Data error | Missing `orderId`, malformed JSON | Do not retry for long; route to error handling/DLQ |
| Business error | Invalid order | Produce a business outcome or isolate per policy |
| Config/permission error | Producer lacks write permission to DLQ | Fix ACL/configuration; message may not have been safely persisted |
| Programming bug | Null dereference | Investigate code; DLQ preserves the message but does not replace fixing the bug |

The Kafka Binder supports classifying retryable exceptions in consumer properties in compatible versions. Check `defaultRetryable` and `retryableExceptions` for the version in use if you want to retry only a specific set of exceptions. Do not assume all exceptions are treated identically when configuring a custom error handler.

## 9. DLQ Topics Must Be Provisioned and Authorized

Enabling `enable-dlq` does not replace preparing the Kafka infrastructure. The DLQ topic must be creatable or already exist according to cluster policy. Depending on binder configuration, automatic topic provisioning may be enabled or disabled; in production environments it is usually better to manage topics through an explicit infrastructure process.

Verify these conditions:

- The DLQ topic exists or the binder's principal is permitted to create topics per policy.
- The consumer/producer principal has the necessary permissions on both the source topic and the DLQ.
- The binder's producer has write permission to the DLQ.
- Retention, replication factor, and partition count of the DLQ match error-retention requirements.
- Operational tools have read permission on the DLQ, and the replay process has permission to publish back to the source topic.
- Monitoring can detect failures when publishing to the DLQ.

If a consumer can read from the source topic but lacks write permission to the DLQ, the error-handling path may fail right when the message needs to be saved. Check not only read permissions on the main topic, but also write permissions on the dead-letter topic.

## 10. DLQ Partitioning

When a source topic has multiple partitions, you must decide which DLQ partition failed messages will be written to. This matters if you want to preserve partitioning metadata or replay by ordering/key.

Several points to verify:

- Whether the DLQ partition count is compatible with how the binder selects partitions.
- Whether the original record key needs to be preserved.
- Whether source partitions need to map to corresponding DLQ partitions.
- Whether a custom `DlqPartitionFunction` or separate partitioning configuration is present.
- Whether consumers depend on key ordering during replay.

In partitioned configurations, the Kafka Binder may require the DLQ to have a partition count matching the source topic or an explicit DLQ partitioning strategy. Do not assume a single-partition DLQ is suitable for every topic. Check the documentation for your exact binder version and actual topology before provisioning.

## 11. Each Consumer Group Should Have Its Own Logical DLQ

Suppose `orders.events` is processed by two groups:

```text
                         orders.events
                         /           \
                        /             \
                       v               v
             inventory-projection   analytics-projection
                       |               |
                       v               v
        orders.events.inventory-   orders.events.analytics-
        projection.dlq             projection.dlq
```

Inventory and analytics may use different schema validation, dependencies, and retry policies. If an event causes analytics to fail while inventory succeeds, only analytics needs to place the record into its own DLQ.

A dedicated DLQ per group helps:

- Avoid mixing failed messages from multiple applications with different handling logic.
- Grant read/replay permissions per responsible team/group.
- Track error rates and backlogs independently.
- Replay to the exact topic/group with the matching contract.

If you intentionally share `dlq-name` across multiple groups, you must design a unified schema, source metadata, access permissions, partitioning, and replay process. Otherwise, messages may be processed by inappropriate tools or consumers.

## 12. Metadata to Preserve in Dead-Letter Messages

When a message is routed to the DLQ, operations teams need to know where it came from and why it failed. Depending on the binder version and error-handling mechanism, dead-letter messages may carry metadata headers such as:

- Source topic.
- Source partition and offset.
- Associated consumer group.
- Exception class and error details.
- Timestamp or processing attempt information.
- Original key and payload.

Specific header names may vary by version and binder mechanism. Read metadata from actual messages in integration tests instead of hardcoding header names based on assumptions.

Do not log secrets or full stack traces into headers if the DLQ system has broad access. Balance investigation needs with data protection requirements. The original payload should be preserved if replay is needed, while controlled diagnostic metadata can be attached alongside it.

## 13. Reading and Processing Messages in the DLQ

A DLQ is a Kafka topic, so it can be consumed by a dedicated consumer. For example, a consumer dedicated to recording failed messages for operational lookup:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class DeadLetterAuditConfiguration {

    @Bean
    Consumer<Message<byte[]>> inspectFailedOrder(
            DeadLetterAuditService auditService) {
        return message -> auditService.record(
            message.getPayload(),
            message.getHeaders()
        );
    }
}
```

The DLQ consumer should have its own group, such as `order-dlq-audit`, so that reading for monitoring does not affect business consumers. If you need to preserve the payload regardless of schema errors, using a byte array type may be more suitable than deserializing directly into a business DTO.

Do not let an audit consumer automatically delete or replay messages before a clear policy is in place. The DLQ may serve as an investigation data source; retention and read permissions must be managed just like other business topics.

## 14. Replaying Messages from the DLQ

Once the root cause is resolved, failed messages can be replayed back to the source topic or a dedicated recovery topic. Replay must be controlled to avoid introducing further errors or duplicate business effects.

The workflow should include:

1. Read the DLQ message and inspect the failure cause.
2. Verify that the schema, data, and code version have been fixed.
3. Determine whether the message is still valid from a business perspective or has expired.
4. Preserve the event ID so consumer idempotency recognizes the redelivery.
5. Preserve the key and required business metadata; do not keep old error headers if they are no longer relevant.
6. Publish to the source topic or an approved recovery topic.
7. Audit who/what process performed the replay, the timestamp, count, and result.
8. Monitor the target consumer group and confirm the messages were processed.

Do not continuously replay the entire DLQ when the root cause has not been fixed. That creates an error loop and can rapidly grow the backlog. For payment or inventory data, check current state before replaying; idempotency prevents duplicates, but it does not automatically make a business-invalid event valid.

## 15. Differences from Retry Topics and Broker Redelivery

A DLQ is not the same as a retry topic and not the same as broker redelivery:

| Mechanism | Goal | When to use |
|---|---|---|
| In-place retry | Quickly retry the same message | Transient errors recoverable within a short time |
| Retry topic | Delay a message and retry later | Errors needing long backoff or to avoid blocking the main stream |
| Broker redelivery | Broker redelivers unacknowledged messages | Consumer/handler failures under broker semantics |
| DLQ | Isolate messages that failed after the handling policy | Messages requiring investigation, repair, or intentional replay |

Kafka does not have a queue requeue mechanism like RabbitMQ. Consumer groups manage offsets; retries and DLQs are typically implemented at the binder/application layer by publishing records to another topic. Distinguish between committing an offset, publishing a record to the DLQ, and a DLQ publish failure.

## 16. DLQ Security and Governance

DLQs often contain failed messages that may include sensitive data, invalid payloads, or internal information. Apply the following:

- ACLs allowing only error consumers and authorized operational tools to read.
- DLQ write permissions granted only to the required producers/binders.
- Retention and cleanup policies aligned with audit requirements.
- Encryption in transit and at rest per cluster policy.
- Auditing for every replay, deletion, or data export action.
- Restricting who has permission to publish directly to the source topic during replay.
- Monitoring capacity and alerting when the DLQ grows abnormally.

Do not grant cluster-wide `ALL` permissions just so an application can write to a DLQ. Grant permissions strictly to the source topic, the DLQ, and the resources actually needed.

## 17. Testing enableDlq, dlqName, and group

A test suite should verify both valid configurations and infrastructure conditions:

| Scenario | How to test | Expected result |
|---|---|---|
| DLQ disabled | `enable-dlq: false` or omitted | Do not expect the binder to publish messages to a DLQ |
| DLQ enabled with group | `enable-dlq: true`, stable group | Binding initializes as configured and can use the DLQ |
| DLQ enabled without group | Omit `group` | Configuration fails to meet Kafka Binder requirements; verify version-specific startup/validation error |
| Default DLQ name | Omit `dlq-name` | Verify the topic name used by the binder per version convention |
| Custom DLQ name | Set `dlq-name: orders.failed.v1` | Failed messages arrive at the specified custom topic |
| Handler fails then succeeds | Throw error on first attempt, succeed on next | Message does not go to DLQ if retry succeeds |
| `max-attempts` exhausted | Handler always throws error | Message is routed according to the configured DLQ mechanism |
| DLQ topic does not exist | Disable auto provisioning or skip creating topic | Provisioning/publish error is detected and observed |
| Missing DLQ write ACL | Revoke producer permission on DLQ | DLQ routing failure is detected; do not assume the message was saved |
| Multiple consumer groups | Two groups reading the same topic | Each group has independent error behavior and DLQ |
| Multi-partition topic | Send messages across multiple partitions | Check partition/key mapping to the DLQ |
| Replay | Read DLQ and resend after fixing the bug | Event ID is preserved and consumer processes safely |

The test binder helps verify functions and bindings at the Spring layer, but it does not replace integration tests with real Kafka when you need to confirm topic provisioning, ACLs, partitions, offsets, and dead-letter publishing.

## 18. Observing the DLQ in Production

Metrics to monitor:

- Number of messages published to the DLQ by source topic and group.
- Growth rate and total backlog of each DLQ.
- Age of the oldest message in the DLQ.
- Common exception types and bindings generating errors.
- Average retry count before entering the DLQ.
- DLQ publish failures, ACL errors, and provisioning errors.
- Number of replayed messages, replay success rate, and messages that continue to fail.

Logs should include event ID, source topic, consumer group, partition/offset, and exception class if metadata is provided. Do not use event ID as a high-cardinality metric label. You can create metrics by binding, group, exception type, and DLQ topic.

Set alerts when the DLQ grows rapidly, contains overly aged messages, or when producers cannot write to the DLQ. An unmonitored DLQ can become an indefinite error dumping ground and cause business incidents to go unnoticed.

## 19. DLQ Configuration Workflow

When deploying a Kafka consumer with dead-letter handling:

1. Identify the function and input binding to protect.
2. Set `destination` to the source topic.
3. Set a stable `group` for the logical consumer; share the group across replicas of the same application.
4. Choose `max-attempts` and backoff according to error types and SLA.
5. Enable `enable-dlq: true` under the Kafka consumer binding.
6. Choose an explicit `dlq-name` if topic names are part of managed infrastructure.
7. Provision the DLQ topic, partitions, retention, replication, and ACLs.
8. Test handler failures, retry exhaustion, and publishing to the DLQ.
9. Build an audited workflow for investigation, data repair, and replay.
10. Monitor backlog, message age, DLQ publish errors, and replay results.

## 20. Self-Check

- [ ] Can explain the role of `enable-dlq`.
- [ ] Know that `dlq-name` specifies the Kafka topic receiving failed messages.
- [ ] Can explain why the Kafka Binder requires a consumer group when enabling DLQ.
- [ ] Distinguish `destination`, `group`, and the DLQ topic.
- [ ] Understand that the default DLQ name is constructed from destination and group per binder convention.
- [ ] Can configure `max-attempts` and backoff before routing to the DLQ.
- [ ] Know that a DLQ topic requires proper provisioning, partitioning, and ACLs.
- [ ] Understand that two independent consumer groups may need separate DLQs.
- [ ] Distinguish in-place retry, retry topics, broker redelivery, and DLQs.
- [ ] Can design a controlled workflow for reading, investigating, and replaying messages.
- [ ] Can test missing group, custom DLQ name, retry exhaustion, and DLQ publish failures.

## Conclusion

The Kafka Binder uses `enable-dlq` to enable dead-letter handling and `dlq-name` to select the topic receiving failed messages. This mechanism requires a stable consumer group; `destination` identifies the source topic, `group` identifies the logical consumer, and the DLQ is a dedicated topic for storing failed records. Messages should only be routed to the DLQ after the configured retry policy, and the DLQ topic must be provisioned, authorized, monitored, and paired with a clear replay process. Separating DLQs by consumer group allows independent applications to handle errors without affecting one another.

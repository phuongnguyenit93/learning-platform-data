# Configuring DLQ and Defining the Protection Scope for Each Error Type

The Kafka Streams binder can route undecodable records to a dead-letter topic (DLQ), but this mechanism does not automatically catch every exception in the topology. Errors occurring before a record becomes a `KStream` element, errors inside business functions, errors when writing output, and Kafka Streams runtime errors occur at different boundaries and require different handling mechanisms.

An important operational principle is identifying **which step raised the error** before configuring a DLQ. If a payload cannot be deserialized into a key/value, the deserialization exception handler can send the failed record to a DLQ. If code inside `map`/`filter`/`processor` throws an exception after the record has entered the topology, application-level handling is required, such as `RecordRecoverableProcessor` or `DltAwareProcessor`. If the broker rejects output writes, production exception handling is needed. A single DLQ property does not cover all three scenarios.

## 1. Placing the DLQ Correctly in the Record Lifecycle

A record goes through these basic stages:

1. The consumer reads bytes from the input topic.
2. The deserializer or message converter transforms the key/value into the data types used by the topology.
3. `KStream`/`KTable` passes the record into processor nodes.
4. Business logic transforms, filters, joins, or updates state stores.
5. The topology serializes and publishes output records.
6. Kafka Streams manages offsets, transactions, and task state.

A DLQ only operates at a boundary that has a corresponding error handler or recovery handler.

~~~mermaid
flowchart TD
    A[Read bytes from input topic] --> B{Deserialize / convert succeeded?}
    B -->|No| C[DeserializationExceptionHandler]
    C --> D[logAndFail / logAndContinue / sendToDlq]
    B -->|Yes| E[Record enters KStream topology]
    E --> F{Business logic succeeded?}
    F -->|No| G[RecordRecoverableProcessor / DltAwareProcessor]
    G --> H[Custom recovery or DLT]
    F -->|Yes| I[Serialize and publish output]
    I --> J{Publish succeeded?}
    J -->|No| K[Production exception handling]
    J -->|Yes| L[Kafka Streams continues processing]
~~~

| Error Type | Stage | Mechanism to Consider | Automatically Caught by Deserialization Handler DLQ? |
|---|---|---|---|
| Malformed key/value bytes, cannot deserialize | Before entering topology | `DeserializationExceptionHandler`, optionally selecting `sendToDlq` | Yes |
| Framework message conversion fails | When converting record to application type | Kafka Streams binder `DeserializationExceptionHandler` | Yes, per binder support |
| Validation or business function throws an exception | Inside `map`/`filter`/`processor` | `RecordRecoverableProcessor`, `DltAwareProcessor`, or custom application recovery | No |
| Output serialization or broker publish fails | When topology writes output | `ProductionExceptionHandler` / producer and runtime configuration | No |
| Stream thread, state store, or runtime fails | During Kafka Streams execution | Runtime config, uncaught exception policy, monitoring, and app recovery | No |

Therefore, do not enable `sendToDlq` and assume all processing errors are isolated. You need an error matrix and dedicated tests for each stage.

## 2. Three Deserialization Exception Handler Options

Kafka Streams provides two foundational handlers:

- `LogAndContinueExceptionHandler`: logs the deserialization error and skips the bad record to continue reading subsequent records.
- `LogAndFailExceptionHandler`: logs the error and fails processing. This is the default of the Kafka Streams binder.

The Spring Cloud Stream Kafka Streams binder adds the `sendToDlq` option to publish deserialization-failed records to a DLQ topic.

| Value | Behavior | When Appropriate |
|---|---|---|
| `logAndFail` | Logs and fails upon encountering an undeserializable record. | When you want to halt processing to investigate schemas or corrupted data without silently dropping records. |
| `logAndContinue` | Logs and skips the failed record, continuing with the next record. | Only when skipping records is business-approved and tracked separately. |
| `skipAndContinue` | Skips the failed record and continues under the binder's skip policy. | When configuring skip behavior for a specific input binding. |
| `sendToDlq` | Sends the failed record to a dead-letter topic and continues per handler mechanics. | When poison pills must be retained for investigation or fixing and replay. |

The binder-level default is `logAndFail`. Without configuring a handler, an undecodable record will cause the processor to fail instead of automatically going to a DLQ.

## 3. Enabling sendToDlq at the Binder Level

Binder-level properties apply to input bindings across the Kafka Streams binder application:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
        processOrders-out-0:
          destination: orders.validated
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
            applicationId: order-validation
~~~

With the configuration above, if the key or value of a record from an input binding cannot be deserialized, the binder sends the failed record to the DLQ. This handler works with both native deserialization and framework-provided message conversion.

Do not confuse this setting with the `enableDlq` property of the regular Kafka message-channel binder. The two binders have different namespaces and error-handling scopes:

| Regular Kafka Binder | Kafka Streams Binder |
|---|---|
| `enableDlq` property on the consumer binding. | `deserializationExceptionHandler` property. |
| DLQ usually handles errors in the message listener after retries. | `sendToDlq` handles deserialization/message conversion errors before records enter the topology. |
| Configured under `spring.cloud.stream.kafka.bindings.` | Configured under `spring.cloud.stream.kafka.streams.` |
| Has `max-attempts` for message-channel consumers. | Does not use regular binder `max-attempts` to control the deserialization handler. |

Putting `enableDlq` in the wrong namespace will not enable DLQ for the Kafka Streams binder.

## 4. Choosing a DLQ Topic with dlqName

You can set a fixed DLQ name for an input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: sendToDlq
          bindings:
            processOrders-in-0:
              consumer:
                dlqName: orders-events-deserialization-dlq
~~~

If `dlqName` is not set and no `DlqDestinationResolver` is provided, the binder uses a default name in the format:

~~~text
error.<input-topic-name>.<application-id>
~~~

For example, if the input topic is `orders.events` and the application ID is `order-validation`, the default name is `error.orders.events.order-validation`.

Create and manage DLQ topics explicitly through infrastructure (IaC, Kafka administration, or platform provisioning workflows). Explicit topic creation ensures control over partition counts, replication factor, retention, ACLs, and quotas rather than relying on the application's auto-create topic permissions.

## 5. Dynamic Routing with DlqDestinationResolver

When an application reads multiple input topics or needs separate DLQs by data category, you can provide a `DlqDestinationResolver` bean. The resolver receives the `ConsumerRecord` and exception, and returns the destination topic name.

~~~java
@Bean
DlqDestinationResolver dlqDestinationResolver() {
    return (record, exception) -> {
        if ("orders.events".equals(record.topic())) {
            return "orders-events-deserialization-dlq";
        }
        if ("customers.events".equals(record.topic())) {
            return "customers-events-deserialization-dlq";
        }
        return "unclassified-deserialization-dlq";
    };
}
~~~

The resolver can inspect topic, partition, key, headers, and exception to choose the destination. Only rely on validated metadata; do not construct topic names directly from untrusted data if doing so could spawn unbounded topics.

Precedence order:

1. If a `DlqDestinationResolver` bean exists, the resolver takes precedence.
2. If there is no resolver, the binder uses the input binding's `dlqName` if configured.
3. If neither is present, the binder uses the default name `error.<input-topic-name>.<application-id>`.

**Important note:** when using `DlqDestinationResolver`, the binder cannot auto-provision dynamic topics because it does not know all possible names the resolver might return. The application or platform must pre-create every DLQ topic that could be selected. If a topic or write permission is missing, the DLQ send operation itself can fail.

## 6. Application-Wide Scope vs. Per-Input-Binding Configuration

`deserializationExceptionHandler` at the binder level applies application-wide. If an application has multiple functions or multiple inputs, a single global choice may not suit every data source.

Example processor receiving two inputs: an orders `KStream` and a customers `KTable`:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, CustomerProfile>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) -> orders
        .leftJoin(customers, EnrichedOrder::from);
}
~~~

Suppose the `orders.events` input must retain failed records in a DLQ, whereas `customer-snapshot` is a reference table where the organization accepts skipping bad records under an agreed policy. You can configure them separately:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.events
        enrichOrders-in-1:
          destination: customer-snapshot
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
                dlqName: orders-deserialization-dlq
            enrichOrders-in-1:
              consumer:
                deserializationExceptionHandler: skipAndContinue
~~~

Consumer-binding configuration takes precedence over binder-level configuration. This allows a multi-input processor to apply distinct error policies per source. Only choose `skipAndContinue` when you have accepted that those records will not enter the topology and have appropriate metrics, alerts, or reconciliation.

## 7. Partitioning of the DLQ

By default, the binder sends failed records to the same partition number as the original record. Therefore, if the input topic has 12 partitions, the DLQ needs at least 12 partitions so every failed record has a matching target partition.

Preserving corresponding partition numbers helps when tracing source partitions or performing controlled recovery. However, the DLQ is a separate topic; ordering between failed records and remaining records in the original topic does not form a global business order.

### Customizing with DlqPartitionFunction

You can provide a `DlqPartitionFunction` bean to select the target partition:

~~~java
@Bean
DlqPartitionFunction dlqPartitionFunction() {
    return (group, record, exception) -> 0;
}
~~~

The function receives the consumer group (typically matching the application ID in Kafka Streams), the failed `ConsumerRecord`, and the exception. The example above routes all failed records to partition 0. Only one `DlqPartitionFunction` bean may exist in the application context; if multiple input bindings require different strategies, use a single shared function branching by topic/group.

If the consumer binding sets `dlqPartitions` to `1` and the binder's `minPartitionCount` is also `1`, the binder can use partition 0 without a `DlqPartitionFunction`. If `dlqPartitions` is greater than `1` or `minPartitionCount` is greater than `1`, you must provide a `DlqPartitionFunction`, even when the DLQ partition count equals the source partition count.

Example configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            processOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
                dlqName: orders-deserialization-dlq
                dlqPartitions: 1
~~~

Only use a single-partition configuration when load, DLQ consumption capacity, and tracing needs permit. A single DLQ partition can become a bottleneck if many source partitions produce errors simultaneously.

## 8. Deserialization DLQ Does Not Catch Business Logic Exceptions

Once a record is deserialized successfully and enters `KStream`, exceptions in `map`, `filter`, `flatMap`, `transform`, or business functions are no longer deserialization exceptions.

Example:

~~~java
@Bean
Function<KStream<String, OrderEvent>,
         KStream<String, OrderSummary>> processOrders() {
    return input -> input.mapValues(event -> {
        if (event.amount() < 0) {
            throw new IllegalArgumentException("Amount must be non-negative");
        }
        return OrderSummary.from(event);
    });
}
~~~

If `amount` is negative while the payload deserialized into `OrderEvent` successfully, `sendToDlq` on `deserializationExceptionHandler` will not catch this exception. The binder does not directly intercept business code inside DSL operators. Logic that can fail must be wrapped in a record-level recovery mechanism.

Do not catch exceptions and arbitrarily return `null`. Doing so can cause records to vanish from the stream without DLQ, audit, or metrics. Decide explicitly whether failed records should be skipped, published to a DLT, recorded as error events, or fail the processor.

## 9. DltAwareProcessor for Routing Business Logic Errors to a DLT

The Kafka Streams binder provides `RecordRecoverableProcessor` for record-level error handling. `DltAwareProcessor` is an implementation capable of publishing failed records to a dead-letter topic (DLT).

Example of an input-only consumer processing each record using the Processor API:

~~~java
@Bean
Consumer<KStream<String, OrderEvent>> processOrders(
        DltPublishingContext dltPublishingContext,
        OrderService orderService) {
    return input -> input.process(() ->
        new DltAwareProcessor<>(
            record -> {
                orderService.validateAndEnrich(record.value());
                return record;
            },
            "orders-processing-dlt",
            dltPublishingContext
        )
    );
}
~~~

`DltPublishingContext` is auto-configured by the Kafka Streams binder and provides publishing infrastructure. `DltAwareProcessor` accepts the record-processing function, DLT name, and this context. When the handler function throws an exception, the processor sends the failed record to the DLT.

Key distinctions:

- `DeserializationExceptionHandler` `sendToDlq` handles records that cannot be deserialized before entering the topology.
- `DltAwareProcessor` handles exceptions thrown inside the logic wrapped within the processor.
- `DltAwareProcessor` does not automatically wrap every `map`/`filter` in the topology. To protect a piece of logic, place that logic inside the recoverable processor.
- If the inner logic performs side effects outside Kafka, the DLT does not roll back side effects executed before the exception occurred.

The DLT name in the example is a topic that must be provisioned with appropriate write permissions. Separate business-logic DLTs from deserialization DLQs if operations teams need distinct classification and redrive procedures.

## 10. RecordRecoverableProcessor with Application-Controlled Recovery

If you do not want to send failed records to a DLT automatically, you can use `RecordRecoverableProcessor` and supply a custom recoverer. The recoverer receives the failed record and the exception:

~~~java
@Bean
Consumer<KStream<String, OrderEvent>> processOrders(
        OrderService orderService,
        FailureAuditService failureAuditService) {
    return input -> input.process(() ->
        new RecordRecoverableProcessor<>(
            record -> {
                orderService.validateAndEnrich(record.value());
                return record;
            },
            (record, exception) -> {
                failureAuditService.record(
                    record.key(),
                    record.value(),
                    exception.getClass().getSimpleName(),
                    exception.getMessage()
                );
            }
        )
    );
}
~~~

The recoverer is a `BiConsumer` receiving the record and exception. The application can write an audit record, emit an error event, increment a metric, or apply another business rule. By default, `RecordRecoverableProcessor` only logs the error and lets the application continue; if records must be durably retained, implement a recoverer that persists or publishes them reliably.

If the recoverer also fails, that failure must be handled by its own policy. Never treat logging a line as a guarantee that a message was durably preserved.

## 11. DltAwareProcessor and Record Key Serializers

`DltAwareProcessor` uses `StreamBridge`, meaning the publishing path goes through the regular Kafka binder. The payload value is converted to `byte[]` by Spring Cloud Stream; the key is passed via a message header and is not automatically converted to `byte[]` in the same way.

Therefore, if the key is not `byte[]` (for example, `String`), configure a key serializer for the DLT destination:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          orders-processing-dlt:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

In the example, `orders-processing-dlt` is the DLT destination name passed to `DltAwareProcessor`. If using `Long`, `UUID`, or custom key types, select the corresponding serializer. Failing to configure the right serializer can trigger a `ClassCastException` or serialization error when publishing the failed record, causing the DLT publish itself to fail.

This is configuration on the regular Kafka binder used by `StreamBridge`, not `deserializationExceptionHandler` on the Kafka Streams binder. Double-check the namespace when configuring the key serializer.

## 12. Output Publish Failures Are Production Exceptions

If the business function succeeds but the Kafka producer cannot write the output, that is a production exception. The Kafka Streams binder does not provide the same first-class DLQ mechanism for this category as it does for deserialization handlers.

You can customize the production exception handler through a `StreamsBuilderFactoryBean` customizer and the corresponding Kafka Streams mechanism. The handling strategy should consider:

- Transient errors from broker disconnections or timeouts.
- Unrecoverable errors such as authorization failures or missing topics.
- Producer retries and delivery timeouts.
- Transaction/processing guarantees in use.
- Application policies for failing, retrying, or continuing.

Do not send the input record to a DLQ simply because output publishing failed without checking commit status. If the processor continues and offsets advance while output was not written, business results can be lost. For critical production errors, failing/retrying via producer/runtime mechanisms is usually needed so progress is not committed when output is unconfirmed.

## 13. Retry, DLQ, and Replay Serve Different Goals

A DLQ is not an automatic retry queue. Once a record is sent to a DLQ, Kafka Streams does not automatically re-read it after a delay. A separate consumer or redrive process is required.

| Mechanism | Goal | When to Use |
|---|---|---|
| Retry in processor | Retry an operation likely to succeed after a transient fault. | External dependency timeouts, brief network glitches. |
| DLQ/DLT | Isolate records that cannot be processed in the current flow. | Malformed schema payloads, data constraint violations, errors needing investigation. |
| Replay from input topic | Reprocess a range of data from the source of truth. | After fixing logic to rebuild a projection or recover an offset range. |
| Parking-lot topic | Hold records requiring operator decision. | Business or data errors needing manual intervention. |

With Kafka Streams, do not assume the regular Kafka binder's `max-attempts` property controls retries for topology operators. If business logic needs retries, design retries in the processor or via a separate delayed retry topology with bounded attempts, backoff, and explicit state tracking.

When redriving, preserve the original event ID, attach replay metadata, and ensure consumers are idempotent. If reprocessing a record that already caused external side effects outside Kafka, check idempotency keys so you do not send emails, issue payments, or update databases twice.

## 14. Metadata and Information to Preserve in the DLQ

When investigating a failed record, at minimum you need to identify:

- Source topic, partition, and offset.
- Original key and raw value if safely retainable.
- Application ID or consumer binding that failed.
- Exception type and message.
- Timestamp when the error was detected.
- Schema version or content type if available.
- Event ID/correlation ID if the record contains those fields.
- DLQ destination and publish timestamp.

For deserialization failures, the record may not produce a Java object. Thus, investigation tools must read raw bytes or exception metadata rather than assuming the value is always a POJO. Do not transform and overwrite the original payload if exact replay capability is required.

For business logic errors handled by `DltAwareProcessor`, the record already has Java types. Ensure the DLT serializer can serialize both payload and key according to the target schema.

Never write secrets, tokens, or sensitive personal data into exception messages/logs unnecessarily. DLQs require ACLs, retention, and data deletion workflows aligned with security policies.

## 15. Testing Each Error Scope

`TopologyTestDriver` is useful for testing business transformations, but it does not replace integration tests for deserializers, Kafka brokers, topic provisioning, or DLT publishing. Test DLQ mechanisms against a real broker or Testcontainers Kafka.

| Scenario | How to Trigger the Error | Result to Verify |
|---|---|---|
| Key deserialization fails | Send malformed key bytes. | `logAndFail`, `logAndContinue`, or `sendToDlq` behaves as configured. |
| Value deserialization fails | Send a payload violating schema/format. | Raw record is routed to the DLQ if `sendToDlq` is enabled. |
| Framework message conversion fails | Send a payload unconvertible to the binding type. | Kafka Streams binder handler runs per configuration. |
| One input in multi-input processor fails | Corrupt a record on the first or second input. | Per-binding handler applies to the right input. |
| Resolver returns different topics | Send poison pills from multiple source topics. | Records go to the right DLQ and all target topics are pre-created. |
| DLQ partitioning | Send errors from multiple source partitions. | DLQ partitions are accurate and the topic has sufficient partitions. |
| Business function throws exception | Throw an exception inside logic wrapped by `DltAwareProcessor`. | Record is sent to the DLT with intact input key/value. |
| Custom recoverer | Use `RecordRecoverableProcessor`. | Recoverer receives the exact record and exception; audit is persisted. |
| String DLT key | Publish a failed record with a `String` key. | Key serializer works with no `ClassCastException`. |
| Output publish fails | Revoke write ACL or stop output broker in test. | Production exception is handled; not confused with deserialization DLQ. |
| DLT missing / lacks ACL | Omit topic creation or revoke write permission. | DLT send failure is detected and alerted; do not assume record was isolated. |
| Replay already-processed record | Redrive the same event ID. | Idempotent consumer creates no duplicate business side effects. |

Verify the contents of the DLQ/DLT topic, key, partition, raw payload, exception context, input offset, and processor state. Checking only for an error line in logs is insufficient.

## 16. Observing and Operating DLQs

Metrics and alerts to include:

- Deserialization error count by input binding, topic, and exception category.
- Number of records sent to each DLQ/DLT.
- Age of the oldest record in the DLQ.
- Number of DLT publish failures.
- Error rate by schema version or event type.
- Consumer lag and Kafka Streams processor state.
- Number of stream thread restarts or application failures.
- Number of records redriven, replayed, and parked in parking-lot topics.
- Time from error detection to completed recovery.

Logs should include topic, partition, offset, application ID, binding, event ID, and exception type. Use low-cardinality metric labels; never place full event IDs or free-form exception messages in metric tags.

A DLQ must have an owner, retention, ACLs, alerts, and a runbook. Without someone responsible for handling it, a DLQ merely moves errors out of the main stream and creates an unmanaged backlog.

## 17. Common Configuration Mistakes

1. Using `enableDlq` from the regular Kafka binder on the Kafka Streams binder. The two namespaces and error scopes differ.
2. Assuming `sendToDlq` catches exceptions inside `map`/`filter`. That handler is for deserialization/message conversion errors.
3. Omitting a stable application ID. Default DLQ names include the application ID; changing the ID creates a different DLQ.
4. Using `DlqDestinationResolver` while forgetting to pre-provision the topics the resolver returns.
5. Giving the DLQ fewer partitions than the input topic while the binder sends to the same source partition index.
6. Setting `dlqPartitions` greater than 1 without providing a `DlqPartitionFunction`.
7. Configuring a handler at the binder level and unintentionally applying it to all input bindings.
8. Enabling `skipAndContinue` without metrics or reconciliation for skipped records.
9. Using `DltAwareProcessor` without configuring a key serializer for non-`byte[]` keys.
10. Assuming `DltAwareProcessor` automatically wraps every operator in the topology. Only logic placed inside the recoverable processor is protected.
11. Failing to distinguish output publish errors from deserialization errors. Production exceptions require a separate mechanism.
12. Treating the DLQ as a retry queue and leaving records sitting there with no redrive process.
13. Neglecting to test DLQ send failures caused by missing topics, ACLs, or serializers.

## 18. DLQ Design Workflow for Kafka Streams

1. List input bindings, topics, application IDs, and key/value types.
2. Classify errors across deserialization, conversion, business logic, output production, and runtime.
3. Choose `logAndFail`, `logAndContinue`, `skipAndContinue`, or `sendToDlq` appropriately per input.
4. Use binder-level handlers when all inputs share one policy; use consumer-level handlers when bindings differ.
5. Configure `dlqName` or `DlqDestinationResolver`; provision all target topics and ACLs before running.
6. Size DLQ partition counts and `DlqPartitionFunction` based on source partitions and expected load.
7. For business logic errors, wrap failable processing in `RecordRecoverableProcessor` or `DltAwareProcessor`.
8. When using `DltAwareProcessor`, configure a serializer for record keys and verify the `StreamBridge` publish path.
9. Configure production exception handling separately for output publish failures.
10. Define retry, redrive, replay, parking-lot, and idempotency policies.
11. Integration-test errors at every boundary and verify both offsets and DLQ contents.
12. Establish metrics, alerts, ownership, retention, and an error-handling runbook.

A DLQ is valuable when it protects the right error boundary and preserves enough information to recover. In the Kafka Streams binder, `sendToDlq` handles poison pills at deserialization; `RecordRecoverableProcessor`/`DltAwareProcessor` handles record-level business logic errors; and production exception handlers handle output write errors. Separating these three scopes clearly prevents dropped records, avoids misplaced configuration expectations, and builds a verifiable recovery workflow.

## References

- [Spring Cloud Stream 5.1 – Kafka Streams Binder: Error Handling](https://docs.spring.io/spring-cloud-stream/reference/5.1/kafka/kafka-streams-binder/error-handling.html)
- [Spring Cloud Stream – Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream – Kafka Streams Binder Functional Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/functional.html)
- [Apache Kafka Streams – Deserialization Exception Handling](https://kafka.apache.org/documentation/streams/developer-guide/config-streams/)
- [Spring for Apache Kafka – Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)

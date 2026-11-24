# Dead-Letter Not Created

## 1. Distinguish Missing DLT Topic from Record Not Sent to DLT

When people say dead-letters are not being created, determine which situation applies:

- **DLT topic does not exist:** the broker lacks the target topic, or it was created with a different name than the recoverer uses.
- **Topic exists yet contains no records:** the listener never reached recovery, records are still retrying, or publishing to the DLT failed.
- **Record was sent yet cannot be found:** the consumer checks the wrong topic, partition, offset, or group; or records have not been polled because a test consumer lacks subscriptions/assignments.
- **DLT holds records yet the app cannot read them:** the DLT consumer lacks permissions, uses an incompatible deserializer, or the group offset sits at the end of the log.

Never assume a failure solely because a topic does not show up in a Kafka UI. Inspect the processing path, publish call, topic metadata, partitions, permissions, and actual records separately.

In Spring Kafka, dead-lettering is a recovery step. The listener fails, the error handler controls retries; only once retries exhaust or a non-retryable exception occurs does the recoverer publish the record to the target topic. If the listener catches exceptions and returns normally, the error handler never sees a failure to route to the DLT.

~~~mermaid
flowchart TD
    A["Kafka record"] --> B["Listener"]
    B --> C{"Listener throws exception?"}
    C -->|No| D["Succeeds / commit per AckMode"]
    C -->|Yes| E["Error handler"]
    E --> F{"Retries left?"}
    F -->|Yes| G["BackOff and redeliver"]
    G --> B
    F -->|No| H["DeadLetterPublishingRecoverer"]
    H --> I{"Broker acks publish?"}
    I -->|Yes| J["Record in DLT"]
    I -->|No| K["Recovery publish failure"]
~~~

This article focuses on record listeners using blocking retries with `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`, while highlighting differences to check when using transactions or `@RetryableTopic`.

## 2. Determine the Exact DLT Topic Name

A common cause is that the provisioned topic name does not match the destination resolver.

With default `DeadLetterPublishingRecoverer`, the destination name is typically formed by appending `-dlt` to the source topic name while keeping the source partition. For example:

| Source topic | Default DLT topic |
|---|---|
| `orders` | `orders-dlt` |
| `payments` | `payments-dlt` |
| `customer-events` | `customer-events-dlt` |

If operations created `orders.DLT` while the default recoverer sends to `orders-dlt`, records will not show up in the topic they inspect. Conversely, if code configures `.DLT` while `-dlt` was provisioned, the producer targets a different name or fails if auto-create is disabled on the broker.

To use the `orders.DLT` convention, configure an explicit resolver:

~~~java
var recoverer = new DeadLetterPublishingRecoverer(
    kafkaTemplate,
    (record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
    )
);
~~~

When using a custom resolver, align the naming convention across code, topic provisioning, ACLs, dashboards, runbooks, and DLT consumers. Never assume every application version or setup uses the same suffix.

## 3. Check Whether the Listener Actually Propagates Errors

DLTs trigger only when the listener fails and the exception reaches the container. If exceptions are swallowed, Spring Kafka treats the listener call as successful.

Wrong example:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception ex) {
        log.error("Cannot process order", ex);
        // Do not rethrow exception: container does not know processing failed.
    }
}
~~~

Proper approach when letting the error handler manage retries and DLT:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    orderService.process(event);
}
~~~

Or if logging/adding context is needed, rethrow the exception:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    try {
        orderService.process(event);
    }
    catch (OrderProcessingException ex) {
        log.error(
            "Cannot process eventId={}",
            event.eventId(),
            ex
        );
        throw ex;
    }
}
~~~

Check additional cases:

- Does the listener return normally after recording an error in a business result object?
- Is `Acknowledgment.acknowledge()` called before processing finishes?
- Does `MANUAL`/`MANUAL_IMMEDIATE` configuration commit offsets too early?
- Does the listener use Spring Retry's `@Retryable` or a custom retry loop that keeps exceptions from reaching `DefaultErrorHandler`?
- Does an adapter, interceptor, or wrapper catch exceptions and turn them into normal returns?

If the listener handles errors by returning a normal result, a DLT will not appear automatically. Decide explicitly which layer owns retries and recovery.

## 4. Verify the Error Handler Is Wired to the Right Container Factory

Declaring a `DefaultErrorHandler` bean alone is not enough. The listener container must use the factory configured with that error handler.

Example configuration:

~~~java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        recoverer.setFailIfSendResultIsError(true);

        return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);

        return factory;
    }
}
~~~

The listener must reference the right factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderCreatedEvent event) {
    orderService.process(event);
}
~~~

Points to verify:

- Is the bean name in `containerFactory` exact?
- Does the factory call `setCommonErrorHandler()`?
- Are there multiple factories causing the listener to pick the wrong default factory?
- Did Spring Boot auto-configure a separate factory instead of your custom factory?
- Has the listener container restarted with the new configuration since the latest deploy?

One way to verify is assigning an `id` to the listener, looking up the container via `KafkaListenerEndpointRegistry`, and checking container status, concurrency, group ID, and the actual factory.

## 5. Understand the Retry Count Before Recovery

With:

~~~java
new FixedBackOff(1_000L, 2L)
~~~

The container waits 1 second between retries and allows at most two additional retries after the initial delivery. If the listener always fails with a retryable exception, total listener invocations equal three:

1. Initial delivery.
2. First retry.
3. Second retry.
4. Once retries exhaust, the error handler invokes the recoverer to publish to the DLT.

Do not confuse additional retry count with total delivery count. If tests expect only two calls or look for the DLT right after the first failure, expectations will mismatch configuration.

If an exception is classified non-retryable, the error handler can call the recoverer right away without extra retries. If the exception falls into default or customized retryable categories, behavior differs. Inspect the exception classification of the exact `DefaultErrorHandler` attached to the listener.

## 6. Check Whether the Exception Is Classified as Retryable

A record may not have reached the DLT yet because the error handler is still retrying. Another record may move immediately because its exception is marked non-retryable.

Example:

~~~java
handler.addNotRetryableExceptions(
    InvalidOrderPayloadException.class
);
~~~

If the listener throws `InvalidOrderPayloadException`, the recoverer runs immediately per recovery policy. If the listener throws `TransientDatabaseException`, the record can retry per `BackOff`.

During investigation, determine:

- What is the actual root-cause exception?
- Which exception does the error handler see after unwrapping?
- Is that exception in custom retryable/non-retryable lists?
- Does another retry listener, recoverer, or error handler override behavior?
- Do logs show delivery attempt counts and next retry timestamps?

Never mark all `RuntimeException` types mechanically as non-retryable or retryable. Unrecoverable data errors should recover quickly; transient dependency failures like timeouts or unavailability may need bounded retries.

## 7. Verify the DLT Topic Is Provisioned

Never rely on the broker to auto-create DLT topics. In many production clusters, `auto.create.topics.enable` is disabled, or auto-created topics lack suitable partitions, replication factor, and retention.

You can provision the DLT topic using `NewTopic`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Bean
NewTopic ordersDltTopic() {
    return TopicBuilder.name("orders.DLT")
        .partitions(6)
        .replicas(3)
        .config("retention.ms", "604800000")
        .build();
}
~~~

The example uses 6 partitions and replication factor 3; values must suit the cluster and source topic. Do not specify replication factor 3 on a single-broker cluster. In production, topic provisioning may be managed by platform teams or infrastructure pipelines rather than auto-created by applications.

Inspect the topic via CLI:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --describe \
  --topic orders.DLT
~~~

If the CLI reports the topic does not exist, check the destination resolver name, provisioning pipeline, and `CREATE` permission if the application is permitted to create topics. If the topic exists, continue checking partitions, leaders, ISR, and ACLs.

## 8. Check Target Partitions

`DeadLetterPublishingRecoverer` normally routes records to the partition matching the source partition. If a source record arrived on partition 5, the destination needs partition 5 for the resolver to preserve the partition.

Example:

| Topic | Partition count | Outcome |
|---|---:|---|
| `orders` | 6 | Source partitions can range from 0 to 5 |
| `orders.DLT` | 1 | Insufficient partitions if resolver preserves source partition |
| `orders.DLT` | 6 | Matching partitions 0 through 5 exist |

If the DLT has fewer partitions than the source topic, sends can fail because the target partition does not exist. Provision the DLT with matching partitions or adjust the resolver to pick a valid partition with an explicit strategy.

Do not arbitrarily route all records to partition 0 if business logic relies on partition ordering or parallel processing. Changing partitions can break ordering relative to the source stream and create load hotspots.

Also verify partition counts of retry topics when using non-blocking retries. With `@RetryableTopic`, topic topology and partition strategy must align with the source per framework config.

## 9. Check the DLT Producer and Serializers

DLT records are published by an application-side Kafka producer. That producer needs serializers compatible with keys and values of recovered records.

A frequent bug is a producer that serializes normal events yet fails to serialize raw `byte[]` from deserialization failures.

For example, if the DLT template only uses `StringSerializer`, sending a `byte[]` value can fail. For successfully deserialized records, the value may be a domain object; with `ErrorHandlingDeserializer`, raw failing payloads enter recovery as byte arrays.

Check:

- Does the key serializer handle the original key type?
- Does the value serializer support both domain objects and `byte[]`?
- Does the template use the right producer factory and security properties?
- Are headers serialized/forwarded properly?
- Are there `ClassCastException` or serializer exceptions in producer logs?

For multiple payload types, use `DelegatingByTypeSerializer` to select serializers by type:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(String.class, new StringSerializer());
delegates.put(OrderCreatedEvent.class, new JsonSerializer<>());

var valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

This is a structural example; configure key/value serializers and `ProducerFactory` for your application's actual generic types. With JSON serializers, align type headers, trusted packages, and schema/version strategies across producers, consumers, and DLT readers.

When the DLT must preserve exact raw payloads for investigation, consider a dedicated template with `ByteArraySerializer` or type-based serialization rather than deserializing and re-serializing invalid data.

## 10. Enable DLT Send-Failure Detection

`KafkaTemplate.send()` is asynchronous. Merely initiating a send without checking its outcome can hide broker rejections.

With `DeadLetterPublishingRecoverer`, you can require recovery to fail if the send result reports an error:

~~~java
recoverer.setFailIfSendResultIsError(true);
~~~

When enabled, DLT publish failures propagate back to the error handler/container per policy instead of silently treating the record as recovered. Exact timeout and exception details depend on Spring Kafka version and recoverer configuration. Check your dependency's API if this method is absent in older versions.

Check logs for errors:

- Topic authorization or group/cluster authorization.
- Unknown topic or partition.
- Not leader or leader unavailable.
- Request timeouts, network disconnects.
- Serialization exceptions.
- Record too large or quota exceeded.
- Aborted transactions or producer fencing when using transactions.

Do not look solely at listener logs. Inspect DLT producer logs and broker logs to see where the send failed.

## 11. Check ACLs of the DLT Publishing Principal

The consumer reading the source topic and the producer writing the DLT may share the same application principal, yet permissions on the source topic do not automatically grant permissions on the DLT.

The principal needs proper permissions to publish to the DLT—typically `WRITE` on the destination topic, and possibly `DESCRIBE` depending on client flow/broker policy. If a DLT consumer reads records, the DLT consumer principal needs `READ` on the DLT topic and `READ` on its consumer group.

Example checking ACLs via CLI:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config admin-client.properties \
  --list \
  --topic orders.DLT
~~~

Displayed resource names and permissions vary by authorizer. Verify the actual principal seen by the broker, especially with SASL, mTLS, or principal mapping rules.

Common signs:

| Symptom | Possible cause |
|---|---|
| Consumer reads `orders` yet DLT publish is rejected | Missing `WRITE` on `orders.DLT` |
| DLT record exists yet inspection tool cannot read it | Inspection principal lacks `READ` |
| Topic created by admin yet app cannot publish | Application principal's ACL was not updated |
| Admin CLI reads fine yet app fails | The two clients use different principals/credentials |

Never grant `superuser` to silence errors. Grant least-privilege permissions to the DLT producer and DLT consumer within the right namespace.

## 12. Check DLT Producer Security Properties

If the main producer works while the DLT producer fails, verify the DLT `KafkaTemplate` shares matching bootstrap servers, TLS/SASL, truststore, and credentials.

If using a dedicated `KafkaTemplate` for the DLT:

- Verify that template's producer factory.
- Check `security.protocol`, SASL mechanism, and JAAS config.
- Verify truststore/keystore mounts.
- Verify principal mapping and ACLs.
- Check transaction ID prefix if the template is transactional.
- Check serializers and producer interceptors.

Do not assume a DLT template inherits every setting from the primary template when the application builds a custom producer factory.

In Spring Boot, common Kafka properties and producer-specific properties can differ. Compare effective configs of the primary event producer vs. the DLT producer; never log passwords, tokens, or private keys while debugging.

## 13. Check Record Size and Broker Limits

DLT records usually preserve the original payload alongside headers storing exception info and source coordinates. Thus, a DLT record can be larger than the source record.

If sends fail due to oversized records, check:

- Producer `max.request.size`.
- DLT topic `max.message.bytes`.
- Broker `message.max.bytes`.
- Size of headers and exception stack traces appended to the DLT record.
- Compression and batch/request settings.

Do not raise size limits blindly across the entire cluster. Determine whether the bulk comes from the payload or headers, then set sensible limits on producer, topic, and broker. You can suppress/truncate exception stack trace headers if full traces are unnecessary while retaining enough context for investigation.

## 14. Check Transactions and Recovery After Rollback

If the listener container runs with Kafka transactions, exceptions normally roll back the transaction. Post-rollback recovery differs from non-transactional record listener setups.

In that case, inspect `DefaultAfterRollbackProcessor` and its recoverer configuration rather than looking only at `DefaultErrorHandler`. To publish to a DLT and commit recovered offsets transactionally, coordinate `KafkaTemplate`, the transaction manager, and the container properly.

Points to verify:

- Does the listener container have transactions enabled?
- Which `KafkaTransactionManager` is attached to the container?
- Do exceptions roll back transactions as expected?
- Is `DefaultAfterRollbackProcessor` configured with a recoverer?
- Does the recoverer use a template participating properly in transactions?
- Is the source offset committed in the same transaction or under a different policy?
- Are there producer fencing, transaction timeout, or abort errors?

Do not copy a `DefaultErrorHandler` setup onto a transactional listener and assume behavior matches non-transactional flows. Test recovery against your actual transaction manager and broker version.

## 15. Distinguish Blocking Retries from `@RetryableTopic`

When a listener uses `@RetryableTopic`, records route through retry topics created by Spring Kafka or pre-provisioned. Once attempts exhaust, the framework routes the record to the DLT topic per naming strategy.

When the DLT does not appear, check:

- Is `@RetryableTopic` placed on the right listener method?
- Is retry-topic infrastructure enabled per your version/configuration?
- `attempts` is the total expected delivery count, not additional retries like `FixedBackOff`.
- Is the DLT handler registered properly?
- Do retry topic and DLT names match the naming strategy?
- Were retry/DLT topics created with suitable partitions and replication?
- Does the retry/DLT producer have `WRITE` permission?
- Is the record still waiting on its delay in a retry topic?

Do not look for a record in the DLT right after the first failure if it is still sitting in a retry topic awaiting its delay.

With non-blocking retries, ordering can shift because failing records move to separate topics while newer records keep flowing. Inspect retry topics, the DLT, and corresponding consumer groups before concluding a record is lost.

## 16. Check Deserialization Failures

Deserialization errors can occur inside `poll()` before the listener method is called. Breakpoints or logs inside the listener will not appear even though the bad record is being processed.

To let the error handler handle deserialization failures, wrap the real deserializer with `ErrorHandlingDeserializer`. DLT producer configuration must handle raw bytes and retained exception metadata.

Check:

1. Does the consumer use `ErrorHandlingDeserializer`?
2. Are delegate deserializers the right types and configs?
3. Are deserialization exceptions passed via `ConsumerRecord`/headers to the error handler?
4. Can the DLT producer serialize `byte[]`?
5. Does the DLT reader use a deserializer compatible with raw payloads?
6. Are there null-value tombstones or key deserialization failures?

Do not check only for malformed JSON. Incompatible schema versions, wrong type headers, missing trusted packages, and legacy data can all trigger deserialization failures.

## 17. Read DLT Headers to Trace the Source Record

Spring Kafka attaches dead-letter headers to trace back to the original record. Key headers include:

| Header | Meaning |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Source topic |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Source partition |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Source offset |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Source consumer group |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Exception class name |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Exception message |

Headers can vary across versions and recoverer settings. Reference the `KafkaHeaders` constants from your current dependency when writing header-reading code.

Never assume a DLT record shares the same offset as the source record. DLT offsets belong to the DLT's own log; original coordinates live in headers. If a DLT consumer sees no records, check consumer group, `auto.offset.reset`, topic subscription, and current DLT group offsets.

## 18. Use `AdminClient` to Verify Topics and Partitions

You can use `AdminClient` to confirm destination topic existence and partition count:

~~~java
import java.util.List;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class DltTopicProbe {

    public void verify(String bootstrapServers, String topic)
            throws Exception {

        Properties properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var description = admin.describeTopics(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS)
                .get(topic);

            System.out.printf(
                "DLT topic=%s partitions=%d%n",
                topic,
                description.partitions().size()
            );
        }
    }
}
~~~

Add security properties of your real cluster to `properties`. `describeTopics` requires appropriate topic permissions; an authorization error does not necessarily mean the topic does not exist.

Check leaders and replicas in `TopicDescription` as well. If a partition lacks a leader or replicas are out of sync, the producer may hit metadata/availability errors even though the topic exists.

## 19. Verify the Record Is Actually in the DLT

If the topic exists, read it using a separate inspection group starting from the beginning of retained data:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker.example.com:9092 \
  --consumer.config client.properties \
  --topic orders.DLT \
  --group dlt-investigation \
  --from-beginning \
  --timeout-ms 10000 \
  --property print.key=true \
  --property print.headers=true
~~~

Some CLI versions do not support the exact header-printing properties shown; check `--help` for your distribution. You can also write a Java consumer to read `ConsumerRecord` and print key, partition, offset, and headers.

If reusing a group ID that already read the DLT previously, `--from-beginning` will not rewind that group's existing committed offset. Use a fresh investigation group or reset the investigation group's offsets in an appropriate environment. Never reset a production group just to peek at a DLT.

If no record appears, compare:

- Actual DLT topic from the resolver.
- Timestamp when the listener exhausted retries.
- Recoverer send-result logs.
- Target partition and log end offset.
- ACLs and serializers.
- Investigation consumer group and its offsets.

## 20. Correlate Logs and Metrics Across the Event Chain

During investigation, correlate logs by event ID, correlation ID, or record key. Trace these milestones:

1. Record polled.
2. Listener starts processing.
3. Listener throws exception.
4. Error handler receives exception.
5. Retries execute.
6. Recoverer invoked.
7. DLT producer initiates send.
8. Broker acknowledges or returns error.
9. Source offset committed or transaction finishes.

Useful metrics:

| Metric/observation | Question |
|---|---|
| Listener invocation/error count | Did the listener fail? |
| Retry count | Is the record still retrying or done retrying? |
| DLT publish success/failure | Did the recoverer send successfully? |
| Producer error/record error | What did the broker or serializer reject? |
| Source consumer lag | Is the record still in backlog? |
| DLT topic end offset | Were new records appended? |
| DLT consumer lag | Do records exist yet remain unread? |

Exact metric names depend on Micrometer, Spring Kafka version, and instrumentation. Do not assume every application exposes `dlt.publish` out of the box; custom recoverer logging/observation may be needed.

## 21. Quick-to-Deep Investigation Workflow

Follow this workflow to isolate the issue:

1. **Confirm destination:** read the recoverer configuration for the exact DLT topic name.
2. **Confirm failure:** verify the listener throws exceptions and they reach the container.
3. **Confirm retries:** check `BackOff`, retry count, and exception classification.
4. **Confirm recoverer:** verify the error handler/factory or after-rollback processor has a recoverer.
5. **Confirm topic:** check topic existence, partition count, leaders, and ISR.
6. **Confirm publish:** check DLT producer logs/send results and timeouts.
7. **Confirm permissions:** check the principal has `WRITE` on the DLT.
8. **Confirm serializers:** check key/value types, raw bytes, and headers.
9. **Confirm transactions:** check rollbacks, producer transactions, and offset commits.
10. **Confirm reader:** use a fresh investigation consumer group to look for the record.

~~~mermaid
flowchart TD
    A["DLT record not seen"] --> B{"Target topic right?"}
    B -->|No| C["Fix destination resolver / topic name"]
    B -->|Yes| D{"Listener throws exception?"}
    D -->|No| E["Fix listener to propagate errors"]
    D -->|Yes| F{"Retries exhausted / recovery called?"}
    F -->|No| G["Check BackOff and exception classification"]
    F -->|Yes| H{"DLT publish succeeded?"}
    H -->|No| I["Check partition, ACL, serializer, broker, transaction"]
    H -->|Yes| J{"Consumer checking right topic/group?"}
    J -->|No| K["Fix subscription/offset/group"]
    J -->|Yes| L["Compare log end offset and headers"]
~~~

## 22. Integration Testing to Reproduce the Issue

An integration test should prove listener failure, retry exhaustion, DLT publishing, and reading the DLT record.

Example using Embedded Kafka or Testcontainers with pre-created source and DLT topics:

~~~java
@EmbeddedKafka(
    partitions = 2,
    topics = {"orders", "orders.DLT"}
)
@SpringBootTest
class DltPublishingIntegrationTest {
    // Inject KafkaTemplate, registry, and probe listener.
}
~~~

A test listener can always throw an exception:

~~~java
@KafkaListener(
    id = "ordersFailureListener",
    topics = "orders",
    groupId = "orders-dlt-test",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(String payload) {
    throw new IllegalStateException("Simulated processing failure");
}
~~~

Tests should:

- Wait for listener container partition assignment before sending.
- Send a unique message ID.
- Wait for the expected retry count per `FixedBackOff`.
- Poll the DLT with a dedicated consumer group.
- Assert key/value, source topic, source partition, and source offset in headers.
- Assert producer send failures are detected when intentionally configuring an invalid destination.
- Use finite timeouts and clean up containers/contexts afterward.

Never use fixed `Thread.sleep()` calls for synchronization. Use `ContainerTestUtils.waitForAssignment`, `CountDownLatch`, Awaitility, or `KafkaTestUtils.getRecords` with timeouts.

## 23. DLT Publish Failure Test Scenarios

Have dedicated tests for each reproducible cause:

| Scenario | How to simulate | Expected result |
|---|---|---|
| Wrong DLT name | Resolver points to unprovisioned topic, auto-create disabled in test | Recoverer reports publish failure |
| Insufficient partitions | Source topic has more partitions than DLT, resolver preserves partition | Send fails with invalid target partition |
| Missing ACL | Test principal lacks `WRITE` on DLT | Broker rejects publish |
| Serializer lacks `byte[]` support | Send deserialization-error payload through String-only template | Producer reports serialization failure |
| Broker temporarily unavailable | Stop broker/test container or block connectivity | Send timeout/failure observed |
| Transaction aborted | Trigger listener transaction rollback | DLT and offsets follow transactional recovery policy |
| DLT exists yet consumer group at end | Read with group already committed to latest offset | Consumer misses older record even though it exists |

Failure tests need isolated topics, groups, and principals. Never leave a listener endlessly retrying inside a shared test suite where it can interfere with other tests.

## 24. Common Errors and Fixes

| Symptom | Cause | How to handle |
|---|---|---|
| DLT topic missing | Wrong suffix or unprovisioned topic | Check resolver and create the right topic |
| Topic exists yet empty | Listener never reached recovery or publish failed | Check exceptions, retries, and recoverer send result |
| Listener fails yet no retries | Exception caught or listener already acknowledged | Propagate exceptions and check `AckMode` |
| Retries forever without DLT | Large retry count, exception classification, or another retry layer interfering | Inspect `BackOff` and active error handler |
| DLT publish partition error | DLT has fewer partitions than source | Add partitions or redesign resolver |
| DLT publish authorization error | Missing `WRITE` on DLT | Grant ACL to application principal |
| DLT publish serializer error | Raw bytes/object unsupported by serializer | Configure serializer per payload type |
| DLT sent yet unreadable | Inspection consumer targets wrong topic, group, or offset | Use a fresh investigation group and check metadata |
| DLT rolled back | Misconfigured transactional recovery | Check `AfterRollbackProcessor` and transaction manager |
| Retry topic has record, DLT empty | Non-blocking retry still waiting out delay | Inspect retry topics and attempt counts |

## 25. Troubleshooting Checklist

- [ ] Identified actual DLT topic name from destination resolver.
- [ ] Confirmed listener propagates exceptions to the container.
- [ ] Verified the right listener container factory and error handler.
- [ ] Checked retry count, `BackOff`, and exception classification.
- [ ] Confirmed recoverer was invoked.
- [ ] Verified DLT topic exists with expected partition count.
- [ ] Checked leaders, ISR, and broker availability.
- [ ] Verified DLT producer bootstrap servers, TLS/SASL, and credentials.
- [ ] Verified `WRITE` ACL on the DLT topic.
- [ ] Checked serializers for domain objects and raw `byte[]`.
- [ ] Enabled send-result failure detection on the recoverer.
- [ ] Checked transactions and after-rollback recovery if listener is transactional.
- [ ] If using `@RetryableTopic`, checked retry topics, naming strategy, and delays.
- [ ] Used a separate investigation consumer group to read the DLT.
- [ ] Inspected DLT headers and source record metadata.
- [ ] Monitored logs, metrics, consumer lag, and producer errors.
- [ ] Reproduced via integration tests with isolated topics/groups.

Missing dead-letters usually stem from one of three causes: the listener never reached recovery, the recoverer failed to publish, or the investigator is reading the wrong topic/partition/offset. Pinpoint the destination resolver, trace the chain `exception → retry → recoverer → producer send`, and inspect topic, partitions, serializers, ACLs, and transactions. When send results are monitored and DLTs are pre-provisioned properly, errors become easy to isolate without losing records.

# sendDefault with a Default Topic

`KafkaTemplate` is the standard record-sending API in Spring Kafka. When calling methods such as `send(topic, value)` or `send(topic, key, value)`, code must pass the topic name on every send call. If a template primarily sends to one topic, you can configure a default topic on `KafkaTemplate` itself and then use the `sendDefault(...)` methods.

`sendDefault` makes call sites shorter and makes it explicit that the template is designed to send to a preselected topic. It still uses the same ProducerFactory, Kafka producer, serializers, partitioner, acknowledgements, retries, and transaction mechanism as the other send methods. The default topic is only a configuration value at the KafkaTemplate layer; it is not a Kafka broker default setting and does not create the topic on the cluster automatically.

This lesson belongs to the **KafkaTemplate** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building applications that send and receive events with Spring Kafka, KafkaTemplate, and @KafkaListener, understanding topics, partitions, offsets, and consumer groups, while also learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate reliable messaging flows.

## 1. When should you use sendDefault?

Suppose a service only emits order events to the `order-events` topic. If every method writes:

~~~java
kafkaTemplate.send("order-events", event);
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

the topic name is repeated in multiple places. When the topic changes, you have to search and update multiple calls. You can configure a KafkaTemplate with a default topic:

~~~java
kafkaTemplate.setDefaultTopic("order-events");
~~~

Then send using:

~~~java
kafkaTemplate.sendDefault(event);
kafkaTemplate.sendDefault(event.orderId(), event);
~~~

Those calls use the configured default topic. Business code focuses on the payload and key instead of repeating the topic name.

sendDefault fits well when:

- A KafkaTemplate is designed to send primarily to one topic.
- A publisher/service is responsible for emitting one event category to a fixed topic.
- You want to centralize the topic name in bean configuration or application properties.
- You want to reduce typos in topic names across methods sending the same kind of event.

Prefer `send` with an explicit topic when the same template must send to multiple different topics or when the topic is chosen dynamically by business logic. A default topic should not be used to obscure the fact that a publisher is sending to unrelated data streams.

## 2. The default topic belongs to KafkaTemplate

Each KafkaTemplate can be configured with its own default topic. It is not a global property of the Kafka cluster, consumer group, or ProducerFactory.

Send architecture with a default topic:

~~~mermaid
flowchart TD
    A[Business service] --> B[KafkaTemplate]
    C[Default topic configured on template] --> B
    B --> D[sendDefault]
    D --> E[ProducerFactory]
    E --> F[Kafka Producer]
    F --> G[Serializer and partitioner]
    G --> H[Kafka broker]
~~~

KafkaTemplate combines the default topic with the key/value or partition passed into sendDefault. It then follows the same send path as calling `send` with an explicit topic.

This leads to three points:

1. Changing the default topic on one KafkaTemplate only affects sendDefault calls using that template.
2. Calls to `send(topic, ...)` still use the topic passed directly in the call.
3. Configuring a default topic does not alter topics already stored on the broker and does not auto-create topics.

If the application has multiple publishers with different default topics, you can create multiple clearly named KafkaTemplate beans and inject them with `@Qualifier`.

## 3. Configuring the default topic with Spring Boot

Spring Boot supports configuring KafkaTemplate's default topic via the `spring.kafka.template.default-topic` property.

Example `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    template:
      default-topic: order-events
~~~

In this configuration:

- `bootstrap-servers` specifies the broker address used to initialize connections.
- `key-serializer` and `value-serializer` specify how keys/values are converted to bytes.
- `acks` controls the broker acknowledgement level for records.
- `template.default-topic` is the default topic Spring Boot applies to the auto-configured KafkaTemplate.

When using Spring Boot auto-configuration, you can inject KafkaTemplate and call sendDefault:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.sendDefault(event.orderId(), event);
    }
}
~~~

There is no need to call setDefaultTopic again if Spring Boot has already configured the template from `application.yml`. Pick a single place to manage the default topic to avoid duplicate configuration that makes the final value hard to trace.

The default topic value can be overridden per environment using Spring Boot's externalized configuration mechanism. For instance, local, test, and production can use different clusters or topic naming conventions.

## 4. Configuring the default topic in Java

If you create the KafkaTemplate bean manually, you can call setDefaultTopic while initializing the bean:

~~~java
@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {

        KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);

        template.setDefaultTopic("order-events");
        return template;
    }
}
~~~

In the example:

- ProducerFactory provides the Kafka producer and client settings.
- KafkaTemplate provides the record-sending API.
- setDefaultTopic assigns the default topic to the template.
- The publisher injects this bean and uses sendDefault.

Configure the default topic during bean creation before the bean is used to send records. Do not repeatedly mutate the default topic while multiple threads are sharing the template, because that makes sendDefault's target topic depend on when a call reads the configuration.

If you need to send to different topics per business operation, pass the topic explicitly or create separate templates with clear responsibilities.

## 5. Common sendDefault overloads

KafkaTemplate provides sendDefault overloads to send a value, key/value, or partition/key/value to the default topic.

| Method | Meaning |
| --- | --- |
| `sendDefault(V data)` | Sends a value without providing a key or specifying a partition. |
| `sendDefault(K key, V data)` | Sends a key and value; the partitioner chooses a partition based on the key. |
| `sendDefault(Integer partition, K key, V data)` | Sends to the specified partition of the default topic with the corresponding key/value. |

### 5.1. Sending only a value

~~~java
kafkaTemplate.sendDefault(event);
~~~

This call passes no key. The producer uses the partitioner to choose a partition based on configuration and Kafka client version. With modern default partitioners, keyless records are typically handled via sticky partitioning to optimize batching.

### 5.2. Sending key and value

~~~java
kafkaTemplate.sendDefault(event.orderId(), event);
~~~

The key allows the partitioner to route events with the same orderId to the same partition under the default algorithm. This is the right choice when business logic requires preserving change order for a given order within a partition.

### 5.3. Specifying a partition

~~~java
kafkaTemplate.sendDefault(2, event.orderId(), event);
~~~

This call requests sending the record to partition 2 of the default topic. The partition must exist in the topic. Specifying a partition takes precedence over letting the partitioner choose automatically.

Specifying a partition directly can be helpful when the application has its own partitioning strategy, but do not hard-code partitions without understanding the impact of partition count changes and cluster topology.

Overloads can vary across Spring Kafka versions. When a custom timestamp or headers are needed, you can build a ProducerRecord and send it through the `send(ProducerRecord)` method supported by your API version. Check the Javadoc of your dependency version rather than assuming all versions share identical signatures.

## 6. Example publisher using sendDefault

Suppose the application has an event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Configure a KafkaTemplate with `order-events` as its default topic. The publisher can expose methods tailored to business needs:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.sendDefault(event.orderId(), event);
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publishWithoutKey(
            OrderCreated event) {

        return kafkaTemplate.sendDefault(event);
    }
}
~~~

The `publish` method uses orderId as the key so events for the same order are routed deterministically by the partitioner. The `publishWithoutKey` method sends keyless records, suitable when ordering by orderId is unnecessary.

Even when using sendDefault, the producer must still serialize the event. If JsonSerializer is configured for values, OrderCreated is converted into JSON bytes before sending. Consumers must have a compatible deserializer and contract to read the payload.

## 7. sendDefault does not create topics automatically

The default topic is only the topic name that KafkaTemplate uses when sending. It does not create the topic on the broker.

The topic must be provisioned via one of these approaches:

- Declare a NewTopic bean with KafkaAdmin in the application.
- Create the topic using the Kafka Admin API or CLI.
- Use an infrastructure pipeline such as Terraform or cluster administration procedures.
- Rely on the broker's auto-create topic setting if the environment allows it, though production usually requires intentional topic management.

Example declaring a NewTopic bean:

~~~java
@Bean
public NewTopic orderEventsTopic() {
    return TopicBuilder.name("order-events")
        .partitions(6)
        .replicas(3)
        .build();
}
~~~

The name in TopicBuilder must match KafkaTemplate's default topic. If the default topic is `order-events` while the created topic is `order-event`, the producer will send to a different name and may hit `UnknownTopicOrPartition` or create an unintended topic if the broker enables auto-create.

If the topic does not exist and the broker does not auto-create it, `send` may fail when the producer fetches metadata or sends the record. Verify topics and ACL permissions when deploying.

## 8. Send results and asynchronous handling

sendDefault returns an asynchronous result just like `send`. In Spring Kafka 3.x, the return type is `CompletableFuture<SendResult<K,V>>`. The future completes when the producer receives the result according to the configured acknowledgement or when the send operation fails.

Example logging metadata:

~~~java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.sendDefault(event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Failed to send orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Sent orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

RecordMetadata indicates the topic, partition, offset, and timestamp of the record written by the broker. This data is useful for tracing events between producer and consumer.

Do not treat calling sendDefault without a synchronous exception as proof of successful delivery. Network or broker errors may be reported to the future after the method has already returned. If the caller needs to know the outcome before responding, you can wait on the future with an intentional timeout; weigh the impact of blocking threads on throughput.

In Spring Kafka versions prior to 3.x, the returned future type may be `ListenableFuture` instead of `CompletableFuture`. Use the API matching your project's version.

## 9. Does sendDefault preserve key and partition semantics?

Yes. sendDefault does not change how Kafka handles keys or partitions. It simply reads the topic from the configured default topic and passes the record to the same producer pipeline.

| Call | Topic | Key | Partition |
| --- | --- | --- | --- |
| sendDefault(value) | Default topic | null | Chosen by partitioner |
| sendDefault(key, value) | Default topic | Passed key | Chosen by partitioner from key |
| sendDefault(partition, key, value) | Default topic | Passed key | Specified partition |
| send(topic, key, value) | Explicitly passed topic | Passed key | Chosen by partitioner from key |

If the key is null, the partitioner applies its keyless record strategy. If the key is non-null, the default partitioner typically uses the serialized key to select a partition. If a partition is specified, the producer sends to that partition.

sendDefault does not guarantee topic-wide ordering. Kafka only guarantees ordering within a single partition. If business logic requires sequential ordering by orderId, pass orderId as the key and design a stable partition count.

## 10. One template or multiple templates?

A KafkaTemplate with a default topic works well when a group of publishers all send to one topic. If a service sends several event types to different topics, there are two options.

### 10.1. Use one template and pass the topic explicitly

~~~java
kafkaTemplate.send("order-events", orderEvent);
kafkaTemplate.send("payment-events", paymentEvent);
~~~

This works well when topics share the same ProducerFactory, serializers, and cluster. The topic is chosen at call time.

### 10.2. Use multiple templates with separate default topics

~~~java
@Bean("orderKafkaTemplate")
KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(producerFactory);
    template.setDefaultTopic("order-events");
    return template;
}

@Bean("paymentKafkaTemplate")
KafkaTemplate<String, PaymentCompleted> paymentKafkaTemplate(
        ProducerFactory<String, PaymentCompleted> producerFactory) {
    KafkaTemplate<String, PaymentCompleted> template =
        new KafkaTemplate<>(producerFactory);
    template.setDefaultTopic("payment-events");
    return template;
}
~~~

The publisher injects the right template:

~~~java
@Service
@RequiredArgsConstructor
public class PaymentEventPublisher {

    @Qualifier("paymentKafkaTemplate")
    private final KafkaTemplate<String, PaymentCompleted> kafkaTemplate;

    public CompletableFuture<SendResult<String, PaymentCompleted>> publish(
            PaymentCompleted event) {
        return kafkaTemplate.sendDefault(event.paymentId(), event);
    }
}
~~~

The example above illustrates bean naming and template selection. When multiple beans share generic types, use `@Qualifier` or constructor injection with an explicit qualifier to prevent Spring from injecting the wrong one.

Do not create multiple templates merely because each topic has a different name if they share identical configuration. Multiple templates make sense when you need to separate default topics, payload types, clusters, or producer policies.

## 11. sendDefault in transactions

If KafkaTemplate is configured with a transactional ProducerFactory and is participating in a Kafka transaction, sendDefault sends records to the default topic within the same transaction just like other send methods.

Usage example:

~~~java
@Transactional("kafkaTransactionManager")
public void publishOrder(OrderCreated event) {
    kafkaTemplate.sendDefault(event.orderId(), event);
}
~~~

This snippet only illustrates calling within a transaction; the application must configure `KafkaTransactionManager` and a `ProducerFactory` with an appropriate transaction ID prefix. The transaction ID prefix must be unique across concurrently running application instances.

sendDefault does not start a transaction automatically just because the method name contains `default`. Transactions depend on the template configuration, transaction manager, and active transaction boundary.

Kafka transactions can coordinate record writes and offset commits within Kafka under the proper configuration. They do not automatically cover database, HTTP, or email operations. If a service both updates a database and sends events, design an outbox or suitable consistency mechanism to bridge the gap between the two systems.

## 12. Testing the default topic

A test should confirm that the template actually sends to the default topic without passing the topic name in the call.

You can use Embedded Kafka or Testcontainers to run a broker for integration tests. The test should:

1. Initialize KafkaTemplate with a default topic.
2. Send a record using sendDefault.
3. Wait for the future to complete within a bounded timeout.
4. Assert that `RecordMetadata.topic()` matches the default topic.
5. Assert key and value as expected.
6. Read the record from a test consumer if end-to-end verification is needed.

Example:

~~~java
@Test
void shouldSendToConfiguredDefaultTopic() throws Exception {
    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    );

    SendResult<String, OrderCreated> result =
        kafkaTemplate.sendDefault(event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("order-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
    assertThat(result.getRecordMetadata().offset())
        .isGreaterThanOrEqualTo(0);
}
~~~

The test requires a broker, the `order-events` topic, and a KafkaTemplate configured with the default topic. Do not merely assert that the future is non-null; wait for the result and inspect metadata to prove the record was sent to the right topic.

Additional test cases can cover:

- Template has no default topic configured.
- Topic does not exist or producer lacks write permissions.
- Serializer fails on an invalid payload.
- Broker temporarily unavailable.
- Sending within a transaction followed by commit or rollback.
- Template has its own default topic, yet `send(topic, value)` still uses the explicitly passed topic.

## 13. Common mistakes

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| sendDefault throws an error when called | KafkaTemplate has no default topic set | Check `spring.kafka.template.default-topic` or `setDefaultTopic` |
| Record goes to the wrong topic | Wrong KafkaTemplate injected or wrong default topic configured | Check bean names, `@Qualifier`, and per-environment config values |
| sendDefault does not create the topic | Default topic is only a target name, not a `NewTopic` declaration | Provision the topic via `KafkaAdmin`/`NewTopic` or infrastructure pipeline |
| Producer receives UnknownTopicOrPartition | Topic does not exist, wrong cluster, or metadata not refreshed | Check bootstrap servers, topic metadata, and ACLs |
| Payload fails to deserialize | Producer serializer and consumer deserializer are incompatible | Check JSON/schema/type headers and event contract |
| Sending keyless yet expecting a specific partition | No partition passed and relying on default partitioner | Use the partition overload or design an appropriate key |
| Mutating default topic at runtime causes hard-to-trace behavior | Multiple threads share the template while configuration is mutated | Fix configuration at bean initialization or create separate templates |
| Future completes with error after method returns | Asynchronous sending | Observe `CompletableFuture`/callbacks and handle errors |
| Confusing sendDefault with sending to a broker default topic | Default topic is a setting on KafkaTemplate | Check which template is injected and its configuration |

## 14. Checklist for using sendDefault

Before using sendDefault, verify:

1. KafkaTemplate has a clear default topic configured at initialization.
2. The default topic exists or has a corresponding provisioning process.
3. ProducerFactory connects to the right Kafka cluster.
4. Key/value serializers match the data types being sent.
5. Whether a key is passed accurately reflects partitioning requirements.
6. A partition is specified only when the application truly needs target control.
7. Futures/callbacks are observed to detect asynchronous send failures.
8. Multiple KafkaTemplate beans have distinct names and qualifiers.
9. Transactions are used only when ProducerFactory and the transaction manager are properly configured.
10. Integration tests confirm metadata topic matches the intended default topic.

sendDefault reduces topic-name repetition and makes a publisher's responsibility to emit to a preselected stream explicit. Its value lies in centralized configuration and cleaner business code; all semantics regarding serialization, partitioning, acknowledgements, retries, and transactions remain governed by the existing producer and KafkaTemplate configuration.


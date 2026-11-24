# ConsumerFactory and Producer Factory

In Spring Kafka, an application usually does not create a Kafka producer or consumer directly everywhere it needs to send or receive events. Instead, Spring Kafka places factories in between to manage client configuration and lifecycle:

- **ProducerFactory** creates and manages Kafka producers. **KafkaTemplate** uses this factory to send records.
- **ConsumerFactory** creates Kafka consumers. The listener container uses this factory to read records and invoke **@KafkaListener** methods.
- **ConcurrentKafkaListenerContainerFactory** creates listener containers with policies such as concurrency, acknowledgement, and error handling. It is not a Kafka ConsumerFactory.

Understanding these three components accurately helps you configure Kafka clients consistently, control the number of connections, handle transactions, and scale consumers without manually managing client lifecycles in each business class.

This lesson belongs to the **Spring Kafka Architecture** chapter in the **SPRING_KAFKA_MESSAGING** module. This module focuses on building applications that send and receive events with Spring Kafka, understanding topics, partitions, offsets, and consumer groups, while laying the groundwork for configuring serialization, retries, dead-letter handling, transactions, concurrency, and testing.

## 1. Where Factories Sit in Spring Kafka Architecture

A Spring Kafka application typically has two main flows:

1. Sending flow: a business service calls KafkaTemplate; KafkaTemplate obtains a producer from ProducerFactory; the producer serializes and sends the record to the broker.
2. Receiving flow: the listener container obtains a consumer from ConsumerFactory; the consumer polls records; the container dispatches records to the @KafkaListener method and coordinates offset acknowledgement.

Overview diagram:

~~~mermaid
flowchart LR
    subgraph Sending["Producer flow"]
        A[Business service] --> B[KafkaTemplate]
        B --> C[ProducerFactory]
        C --> D[Kafka Producer]
        D --> E[Kafka Broker]
    end

    subgraph Receiving["Consumer flow"]
        E --> F[Kafka Consumer]
        F --> G[ConsumerFactory]
        G --> H[Listener Container]
        H --> I[@KafkaListener]
        I --> J[Business processing]
    end

    K[ConcurrentKafkaListenerContainerFactory] --> H
~~~

The diagram illustrates the responsibility relationships. At runtime, ConsumerFactory is called by the listener container to create consumers; the consumer connects to the broker and polls data. ConcurrentKafkaListenerContainerFactory is used at the container configuration step, typically via the containerFactory attribute of @KafkaListener.

A factory is the object that manages creating clients, not the client performing sends or polls. Producers and consumers are the objects that actually communicate with the Kafka broker.

## 2. Core Interfaces and Implementations

Spring Kafka provides interfaces so applications can program to abstractions or swap implementations when needed:

| Component | Responsibility | Common implementation |
| --- | --- | --- |
| ProducerFactory<K,V> | Provides producers to send records and manages producer lifecycle | DefaultKafkaProducerFactory<K,V> |
| ConsumerFactory<K,V> | Creates consumers with corresponding key/value and group configurations | DefaultKafkaConsumerFactory<K,V> |
| KafkaTemplate<K,V> | API for sending records, receiving send results, and supporting producer operations | KafkaTemplate<K,V> |
| KafkaListenerContainerFactory<C> | Creates containers that execute listeners | ConcurrentKafkaListenerContainerFactory<K,V> |
| KafkaMessageListenerContainer | Container that runs a listener with a single consumer | KafkaMessageListenerContainer |
| ConcurrentMessageListenerContainer | Container that manages multiple child containers/consumers | ConcurrentMessageListenerContainer |

K and V are the key and value types on the application side. For example, ProducerFactory<String, OrderCreated> indicates the application sends String keys and OrderCreated payloads. Before sending, serializers convert these values into bytes. On the receiving side, deserializers convert bytes back into the types used by the listener.

Generic types provide compile-time type checking. They do not automatically guarantee that serializers and deserializers on both sides are compatible. Data format configuration must still be agreed upon.

## 3. ProducerFactory and DefaultKafkaProducerFactory

### 3.1. What problem does ProducerFactory solve?

KafkaProducer is the client from the Kafka Java API. An application could create a KafkaProducer itself, call send, and close the producer. However, if multiple services or components send data, creating clients individually in each place easily leads to:

- Repeating configurations for bootstrap servers, serializers, acknowledgements, retries, and security.
- Creating too many connections or failing to close producers properly.
- Difficulty managing transactions and reusing producers.
- Difficulty changing configurations across development, testing, and production environments.
- Components having inconsistent error handling and timeouts.

ProducerFactory centralizes creating and managing producers. KafkaTemplate receives a ProducerFactory via constructor or dependency injection, then uses producers provided by the factory to send records.

### 3.2. DefaultKafkaProducerFactory creates and reuses producers

DefaultKafkaProducerFactory is the common implementation of ProducerFactory. With standard configuration, the factory uses a single shared producer. KafkaProducer is designed to be thread-safe, so multiple threads can send records through the same producer without creating a separate producer per call.

Default model:

~~~text
ProducerFactory
      |
      +---- Shared KafkaProducer
                 ^
                 |
          KafkaTemplate
            /   |   \
         Thread A  Thread B  Thread C
~~~

Using a shared producer avoids repeated client initialization and broker connection overhead. KafkaTemplate can be used as a singleton bean in a Spring application.

ProducerFactory manages acquiring and returning producers according to the factory's policy. When using KafkaTemplate, the application normally does not close the producer after each send. The factory is responsible for closing resources when the application context stops.

### 3.3. ProducerFactory and KafkaTemplate have distinct roles

These two classes are often injected alongside each other in the configuration/architecture, but do not replace each other:

- ProducerFactory creates and manages Kafka producers.
- KafkaTemplate provides a convenient API for business code: sending by topic/key/value, sending ProducerRecords, receiving futures, executing callbacks, or operating inside transactions.
- KafkaProducer is the actual client that communicates with the broker.

Example of sending an event:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

The service depends only on KafkaTemplate. The service does not need to know how the factory creates producers, how producers are reused, or where serializer configuration lives. Client configuration belongs to the messaging infrastructure layer.

### 3.4. Configuring the producer factory

ProducerFactory accepts a configuration map following Kafka ProducerConfig and Spring Kafka serializer settings. Common properties:

| Property | Meaning |
| --- | --- |
| bootstrap.servers | List of brokers used to establish initial connections and fetch cluster metadata |
| key.serializer | Serializer for keys |
| value.serializer | Serializer for values |
| acks | Broker acknowledgement level for records |
| enable.idempotence | Enables producer idempotence to limit duplicates caused by producer-layer retries |
| retries | Number of times the producer retries sending upon retryable errors |
| delivery.timeout.ms | Upper bound on time to complete a send, including awaiting acknowledgement and retries |
| request.timeout.ms | Time to wait for a response to a single request |
| linger.ms | Time the producer may wait to batch records together |
| batch.size | Target batch size per partition |
| compression.type | Compression type for record batches |

Do not copy every property blindly into every environment. For example, acks, idempotence, retries, and delivery timeout must be chosen together based on durability, latency, and fault-tolerance requirements.

Example of configuring producer properties in Java:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> orderProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    props.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    return new DefaultKafkaProducerFactory<>(props);
}
~~~

In the example, DefaultKafkaProducerFactory reads the configuration map and creates a KafkaProducer with StringSerializer for keys and JsonSerializer for values. Setting acks=all requires the leader to wait for acknowledgement from replicas currently in the ISR according to the replication protocol. Actual durability also depends on the topic/broker replication factor and min.insync.replicas.

### 3.5. Serializers belong to producer factory configuration

Kafka stores records as bytes. Therefore, the producer factory must know how to convert the application's key/value types into bytes.

Examples:

- StringSerializer is suitable when the key or value is a string.
- ByteArraySerializer is suitable when the application already produces a byte payload.
- Spring Kafka's JsonSerializer converts objects into JSON.
- Avro or Protobuf serializers can be used when the system manages schemas in those formats.

Serializers can be declared by class in the configuration map. The Kafka client instantiates the serializer for the producer. For custom serializers that require dependencies or their own state, inspect how the serializer is instantiated and configured to avoid unintended state sharing.

ProducerFactory does not turn a Java object into JSON unconditionally by magic. It creates producers with the configured serializer; the serializer itself performs the conversion at send time.

### 3.6. Shared producer and thread-bound producers

Because KafkaProducer is thread-safe, the shared model is a suitable default for many applications. However, DefaultKafkaProducerFactory also has a per-thread producer option via producerPerThread in supported versions.

When producerPerThread is enabled, the factory keeps a producer bound to each thread instead of using only one shared producer. This can be useful in certain scenarios requiring thread-level state isolation, but increases the number of producers and connection resources. The application must call closeThreadBoundProducer() when a thread no longer uses that producer to release resources properly.

Do not enable producerPerThread simply because the application has multiple threads. The shared producer is already designed to support concurrent access. Change the policy only when there is a clear technical reason and you have measured the impact.

## 4. ConsumerFactory and DefaultKafkaConsumerFactory

### 4.1. What problem does ConsumerFactory solve?

KafkaConsumer is the client that reads records from Kafka. Unlike KafkaProducer, KafkaConsumer is not thread-safe. A single consumer must not be used concurrently from arbitrary threads.

In a Spring Kafka application, the listener container manages the consumer and the poll loop. ConsumerFactory creates consumers according to the configuration the container requests. As a result, the application does not need to manually instantiate a KafkaConsumer in every listener.

ConsumerFactory centralizes:

- default bootstrap servers and group ID.
- key deserializer and value deserializer.
- auto commit, offset reset, and poll/fetch limits.
- client ID and connection properties.
- creating new consumers for each listener container or child container.

DefaultKafkaConsumerFactory is the common implementation. Whenever a container needs a consumer, the factory creates a new KafkaConsumer with the corresponding configuration. These consumers belong to the specified group and are assigned partitions by the Kafka group coordinator.

### 4.2. Each consumer must be owned by a single processing thread

Typical model when a listener container has concurrency set to three:

~~~text
ConcurrentKafkaListenerContainerFactory
                  |
                  v
        ConcurrentMessageListenerContainer
             /          |          \
            v           v           v
       Child 1       Child 2       Child 3
            |           |           |
            v           v           v
       Consumer 1   Consumer 2   Consumer 3
            |           |           |
         Partition   Partition   Partition
~~~

Each consumer is managed by the container along its own lifecycle and execution thread. The container coordinates polling, invoking the listener, handling exceptions, and committing offsets according to configuration.

Do not take a single KafkaConsumer and share it across multiple listener threads. Doing so violates KafkaConsumer's thread-safety model and can lead to concurrent access errors, invalid poll state, or errors when committing.

### 4.3. Configuring the consumer factory

ConsumerFactory uses Kafka ConsumerConfig properties along with deserializers. Common properties:

| Property | Meaning |
| --- | --- |
| bootstrap.servers | Broker addresses for initiating connections |
| group.id | Consumer group name |
| key.deserializer | Converts keys from bytes back to application types |
| value.deserializer | Converts values from bytes back to application types |
| enable.auto.commit | Enables/disables Kafka client auto commit |
| auto.offset.reset | Starting position when the group does not yet have a valid offset |
| max.poll.records | Maximum number of records returned in a single poll |
| max.poll.interval.ms | Maximum interval between polls before the consumer is considered stalled |
| session.timeout.ms | Session timeout when the coordinator does not receive heartbeats |
| heartbeat.interval.ms | Heartbeat sending interval in the group membership mechanism |
| fetch.min.bytes | Minimum amount of data the consumer wants to receive in a fetch |
| client.id | Client identifier for monitoring and metrics |

In a listener container, Spring Kafka typically manages offset commits based on listener outcomes. Therefore, enable.auto.commit=false is commonly configured so the container controls acknowledgement and commits. Do not enable auto commit without understanding its impact on actual processing timing.

Example of creating a consumer factory:

~~~java
@Bean
public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    props.put(
        "spring.json.value.default.type",
        OrderCreated.class.getName()
    );
    props.put(
        "spring.json.trusted.packages",
        "com.example.orders.events"
    );

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

In the example, the consumer reads String keys and decodes values into OrderCreated. The default type configuration must match the event contract the application expects to receive. Trusted packages should be limited to packages containing allowed types for deserialization, avoiding overly broad scope.

If the producer sends type headers, the consumer can use the header to determine the type according to JsonDeserializer configuration. If the application does not want to rely on type headers, agree on a default type or type mapping across services. The key point is that both sides must understand the same schema and payload semantics.

### 4.4. How are deserializers created and configured?

DefaultKafkaConsumerFactory can receive deserializer configuration by class in the map, by instance, or by supplier depending on the constructor and Spring Kafka version. When there are multiple consumers, avoid sharing a deserializer with mutable state across consumers if that implementation is not thread-safe.

Using a class in the configuration map is simple: the Kafka client creates a deserializer for each consumer. For custom deserializers, a supplier can be used so the factory creates a separate instance for each consumer. This is useful when a deserializer holds state, needs dependencies, or must be configured per consumer.

A deserializer is responsible for converting bytes into Java types. It does not replace business validation. A successfully decoded payload might still lack an orderId, have a negative total amount, or violate order state; the listener or application layer must still validate data against business rules.

## 5. ConsumerFactory is NOT ConcurrentKafkaListenerContainerFactory

This is an easy point of confusion when reading Spring Kafka configurations.

| Object | What it creates | Responsibility |
| --- | --- | --- |
| DefaultKafkaConsumerFactory | Kafka Consumer | Creates the client that reads data from the broker |
| ConcurrentKafkaListenerContainerFactory | Listener container | Creates and configures containers that execute @KafkaListener |
| KafkaMessageListenerContainer | Managed consumer and listener loop | Polls and invokes the listener with a single consumer |
| ConcurrentMessageListenerContainer | Child containers | Coordinates multiple consumers according to concurrency |

Example of configuring a listener container factory:

~~~java
@Bean(name = "kafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(orderConsumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

In the example:

- setConsumerFactory connects the listener container factory with the configured ConsumerFactory.
- setConcurrency(3) instructs the container to manage up to three consumers for this listener.
- AckMode.RECORD instructs the container to commit progress after the listener successfully processes each record, following the container's rules and constraints.

The listener method can select a container factory by bean name:

~~~java
@Component
public class BillingOrderListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.startBilling(event);
    }
}
~~~

If the application only has one default listener container factory, the containerFactory attribute can be omitted. When there are multiple different listener configurations, giving clear bean names and specifying containerFactory helps avoid accidentally using the wrong consumer factory or processing policy.

## 6. Spring Boot Configuration vs. Manual Factory Configuration

There are two common ways to configure Kafka clients in a Spring Boot application.

### 6.1. Letting Spring Boot auto-configure

When the Spring Kafka dependency and spring.kafka properties in application.yml are present, Spring Boot can create default beans such as ProducerFactory, ConsumerFactory, KafkaTemplate, and the listener container factory.

Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
    listener:
      ack-mode: record
      concurrency: 3
~~~

This approach fits when the application uses a single Kafka cluster and needs environment-specific client configuration. Spring Boot manages creating the foundational beans, reducing configuration code.

Not all Kafka properties sit at the same configuration level. Producer, consumer, listener, and extended properties must be placed under the right branch. Putting a producer property under consumer or vice versa may prevent the client from receiving the intended setting.

### 6.2. Declaring factories manually when control is needed

When you need multiple clusters, special serializers, transaction configuration, or distinct listener policies, the application can declare ProducerFactory, ConsumerFactory, and container factory beans manually.

A complete manual configuration might look like:

~~~java
@Configuration
@EnableKafka
public class KafkaClientConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class
        );
        props.put(
            "spring.json.value.default.type",
            OrderCreated.class.getName()
        );
        props.put(
            "spring.json.trusted.packages",
            "com.example.orders.events"
        );

        return new DefaultKafkaConsumerFactory<>(props);
    }

    @Bean(name = "kafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Imports are omitted to focus on bean relationships. The example uses modern Spring Kafka APIs; specific constructor signatures or configuration options may vary across versions. Check the Spring Boot and Spring Kafka versions your project uses before copying configurations.

When declaring beans manually, understand Spring Boot's auto-configuration mechanism. Some defaults will back off in favor of application-provided beans. If you create your own ProducerFactory or ConsumerFactory, verify that dependent beans such as KafkaTemplate and the listener container factory are wired to the right factory.

### 6.3. Which configuration approach to choose?

| Requirement | Suitable approach |
| --- | --- |
| One Kafka cluster, standard serializer/deserializer config | Spring Boot properties |
| Want to change ack mode or concurrency for listeners | Configure the listener container factory |
| Multiple independent Kafka clusters | Declare separate factories, templates, and container factories |
| Need transactional producer | Configure DefaultKafkaProducerFactory with a transaction ID prefix |
| Custom serializer/deserializer | Configure the factory with an appropriate class, instance, or supplier |
| Want to test against a different broker than runtime | Override properties or provide dedicated test factories |

You do not need to create a separate factory for every topic. If topics are on the same cluster and share key/value types, serializers, and client policies, a single ProducerFactory can serve multiple topics. Likewise, a single ConsumerFactory can serve multiple listeners sharing basic client configuration; each listener container can still have its own concurrency, group, or error handling.

## 7. Multiple Factories and Multiple Kafka Clusters

An application may connect to multiple Kafka clusters, such as an internal cluster for business events and a separate cluster for exchanging data with partner systems. Each cluster can have different bootstrap servers, credentials, serializers, timeouts, and security policies.

In this case, create clearly named beans:

~~~java
@Bean("internalProducerFactory")
ProducerFactory<String, OrderCreated> internalProducerFactory() {
    // Internal cluster configuration
}

@Bean("partnerProducerFactory")
ProducerFactory<String, PartnerEvent> partnerProducerFactory() {
    // Partner cluster configuration
}

@Bean("internalKafkaTemplate")
KafkaTemplate<String, OrderCreated> internalKafkaTemplate(
        @Qualifier("internalProducerFactory")
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}

@Bean("partnerKafkaTemplate")
KafkaTemplate<String, PartnerEvent> partnerKafkaTemplate(
        @Qualifier("partnerProducerFactory")
        ProducerFactory<String, PartnerEvent> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

The snippet illustrates how to name and inject the right factory; specific configuration details are omitted. For consumers, you can create corresponding ConsumerFactory and listener container factory beans and then specify containerFactory on each @KafkaListener.

When multiple beans share the same interface or generic type, use @Qualifier to prevent Spring from injecting the wrong one. Bean names should reflect the cluster or business purpose rather than generic names like factory1 and factory2.

Note that a factory is tied to its cluster configuration and serializers/deserializers. Do not use one cluster's KafkaTemplate to send to another cluster simply by changing the topic name. Broker addresses belong to the producer factory, not the topic name.

## 8. Factories and Transactions

ProducerFactory plays an important role when an application uses Kafka transactions. With DefaultKafkaProducerFactory, you can configure a transaction ID prefix so the factory creates transactional producers.

Example:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> transactionalProducerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    props.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );
    props.put(ProducerConfig.ACKS_CONFIG, "all");

    var factory =
        new DefaultKafkaProducerFactory<String, OrderCreated>(props);

    factory.setTransactionIdPrefix("orders-tx-instance-a-");
    return factory;
}
~~~

The transaction ID prefix must be unique across concurrently running application instances. When running multiple replicas, each instance must have its own prefix to avoid transactional ID collisions. In real deployments, the prefix is typically composed of the service name and an instance identifier stable over the process lifetime.

When the factory is configured with a transaction ID prefix, it manages transactional producers and reuses producers that have completed transactions according to its caching policy. Do not set a static shared transactional.id across multiple instances when the factory is responsible for assigning IDs.

You can create a KafkaTransactionManager from ProducerFactory to integrate Kafka transactions with Spring's transaction mechanism:

~~~java
@Bean
public KafkaTransactionManager<String, OrderCreated> kafkaTransactionManager(
        ProducerFactory<String, OrderCreated> transactionalProducerFactory) {
    return new KafkaTransactionManager<>(transactionalProducerFactory);
}
~~~

How transactions are applied depends on the processing flow: sending multiple records within one transaction, using @Transactional with the corresponding transaction manager, or configuring the listener container to participate in Kafka transactions. Choose the proper transaction boundary and verify behavior when a listener throws an exception.

Kafka transactions can coordinate writing records to Kafka and committing offsets in Kafka under the right configuration. They do not automatically encompass database writes, REST API calls, or sending emails. For side effects outside Kafka, you still need idempotency, outbox/inbox, or an appropriate consistency mechanism.

## 9. Concurrency, Client Counts, and Partitions

Listener container concurrency determines how many consumers the container can create for parallel processing. ConsumerFactory creates each consumer according to that demand.

For example, if a topic has six partitions and the listener container has concurrency set to three, the group can distribute the six partitions across three consumers, each handling one or more partitions. If concurrency is increased to eight, the group still only has six partitions to distribute; some consumers may not be assigned any partitions.

A few principles:

- The number of usefully active consumers in a group is bounded by the number of partitions assigned to the group.
- A partition at any point in time is assigned to at most one consumer in the same group.
- Increasing concurrency increases the number of consumers, connections, and resource requirements.
- More consumers do not automatically guarantee higher throughput; it also depends on processing time, brokers, network, batching, and downstream dependencies.
- Rebalances can occur when group members change or a consumer fails to poll within limits.

ProducerFactory and ConsumerFactory have different resource models. A producer can be shared across threads by default; a consumer must be owned by its respective thread/container. Do not apply producer-sharing thinking to consumers.

## 10. Lifecycle and Closing Resources

In a Spring application, factories and templates are normally container-managed beans. Let Spring manage their lifecycle rather than arbitrarily closing clients inside business services.

### 10.1. Producer

KafkaTemplate obtains a producer from ProducerFactory when it needs to send. For shared producers, the factory reuses the client. For transactional producers, the factory manages allocating and reclaiming producers per transaction. When the application context stops, the factory closes producers and related resources.

Do not call close() on a shared producer after each send. If you obtain a producer directly from the factory for a special operation, follow the factory's acquire/release resource contract for your API version.

### 10.2. Consumer

The listener container creates consumers from ConsumerFactory when the container starts. When the container stops, it exits the poll loop, performs the appropriate shutdown/commit sequence, and closes the consumer.

Do not manually close a consumer managed by a listener container. Nor should you create a shared KafkaConsumer inside a singleton service for multiple threads to call poll or commit.

### 10.3. Graceful shutdown

When the application stops, the container needs time to stop accepting new records and finish in-flight processing according to shutdown configuration. If listener processing takes longer than the allotted shutdown timeout, the application may be terminated before completion. Therefore, shutdown timeout, business processing duration, and offset commits must be considered together.

## 11. Testing Factories and Listener Configurations

Factories are infrastructure components and should be tested at an appropriate level. Testing can be divided into three layers:

1. Configuration checks: verify beans are created with the right bootstrap servers, serializers/deserializers, and group.
2. Integration testing with Kafka: send events through KafkaTemplate, receive through @KafkaListener, and verify payload/metadata.
3. Error and lifecycle testing: verify behavior when deserialization fails, the broker temporarily disconnects, a listener fails, or the container stops.

You can use Embedded Kafka in Spring Kafka or Testcontainers to run a real broker in integration tests. A real broker verifies serialization, partitioning, group assignment, and offset commits against actual Kafka behavior. Mocking producers/consumers is useful for unit testing specific logic branches, but does not replace integration tests when broker interaction must be verified.

An integration test should check at least:

- ProducerFactory and KafkaTemplate send to the right topic, key, and payload.
- ConsumerFactory creates consumers with the right group and deserializer.
- Listener container invokes the right listener.
- Deserialized payload preserves data accurately.
- Listener errors flow through the configured error handler.
- Consumers are closed when the container stops.

Do not merely check that the ApplicationContext starts up successfully and conclude the messaging flow works. Serializer configuration may be valid as a bean yet produce an incompatible format for the consumer; a listener container may start yet receive no partition assignment; or a listener may receive records yet commit differently than expected.

## 12. Common Configuration Errors and How to Investigate

| Symptom | Possible cause | Investigation steps |
| --- | --- | --- |
| KafkaTemplate fails to send records | ProducerFactory uses wrong bootstrap servers, ACLs, or serializer | Check exception from future, producer properties, broker, and serializer |
| Producer sends successfully but consumer receives nothing | ConsumerFactory uses wrong cluster/topic/group or has no partition assignment | Check cluster, subscription, group state, assignment, and offsets |
| Listener fails deserialization | Value deserializer or default type does not match payload | Check byte format, type headers, trusted packages, and event contract |
| Too many producer connections created | Unnecessary multiple factories/producers created or producerPerThread enabled | Check bean scope, number of factories, producer policy, and thread lifecycle |
| Consumer rebalances continuously | Processing takes too long between polls, heartbeats, or unstable network | Check max.poll.interval.ms, session.timeout.ms, listener duration, and group logs |
| Listener does not run even though container is created | Consumer has no partition assignment or listener uses wrong container factory | Check group assignment, topic, bean name, and containerFactory attribute |
| Ambiguous bean injection | Multiple ProducerFactory/ConsumerFactory beans of the same type | Use @Qualifier or distinct bean names |
| Transactional producer fails to initialize | Transaction ID prefix missing or colliding across instances | Check transaction config and uniqueness of prefix |

When investigating, pinpoint which layer the error occurs at: the factory failed to create the client, the client cannot connect to the broker, serialization/deserialization failed, the container was misconfigured, or the listener threw an error. Do not blame every send/receive issue on ProducerFactory or ConsumerFactory simply because they sit at the configuration layer.

## 13. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| ProducerFactory is KafkaProducer itself. | The factory creates and manages producers; KafkaProducer is the client communicating with the broker. |
| ConsumerFactory is the listener container. | ConsumerFactory creates consumers; the listener container manages polling and invoking listeners. |
| ConcurrentKafkaListenerContainerFactory creates Kafka consumers directly. | It creates listener containers; containers use ConsumerFactory to create consumers. |
| Every KafkaTemplate.send call creates a new producer. | The default factory reuses a shared producer; transactional and factory options have their own policies. |
| A single KafkaConsumer can be shared across multiple threads. | KafkaConsumer is not thread-safe; the container manages consumers on appropriate threads. |
| Increasing concurrency always increases throughput. | Concurrency is still bounded by partitions, processing capacity, and resources. |
| A single factory can only be used for one topic. | A factory can serve multiple topics on the same cluster with compatible client configuration. |
| Changing the topic name switches Kafka clusters. | The cluster is determined by bootstrap servers in the factory; a topic is just a data stream within a cluster. |
| Factories handle all business errors automatically. | Factories manage clients; retries, DLT, and business logic belong to listener containers/error handlers and the application. |
| Using Kafka transactions includes the database. | Kafka transactions do not automatically cover systems outside Kafka. |

## 14. Factory Design Checklist for a Spring Kafka Application

Before putting the configuration into production, answer these questions:

1. Does the application connect to one or multiple Kafka clusters?
2. Which ProducerFactory and ConsumerFactory does each cluster require?
3. What data types do keys and values use; are serializers and deserializers compatible?
4. What acks, idempotence, retry, and timeout levels does the producer need?
5. How is the consumer group named; is auto commit disabled so the container manages offsets?
6. How much concurrency does the listener need and does the topic have enough partitions?
7. Is a separate listener container factory needed for batching, acknowledgement, or error handling?
8. Are Kafka transactions used; is the transaction ID prefix unique across instances?
9. Which beans are auto-configured by Spring Boot and which are declared by the application?
10. Who owns client lifecycle and where are resources closed?
11. Are there integration tests verifying serialization, listeners, offsets, and shutdown?

When these questions are clearly answered, ProducerFactory and ConsumerFactory become a stable configuration boundary between the business layer and the Kafka client. Business services can focus on the events to send or process; the messaging layer handles creating clients, applying configuration, coordinating listeners, and managing resources across the application lifecycle.


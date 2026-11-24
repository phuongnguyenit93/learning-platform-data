# Configuring Multiple Container Factories

In Spring Kafka, `ConcurrentKafkaListenerContainerFactory` is where you configure how listener containers are created: which consumer factory is used, concurrency, record-by-record vs. batch processing, acknowledgment mode, error handler, and transaction manager. An application can declare multiple container factories to serve Kafka streams with different requirements.

For example, a service might consume `OrderCreated` with a record listener at high concurrency while consuming `AuditEvent` in batches at lower concurrency. The two listeners may need different deserializers, consumer groups, `AckMode` settings, and error handling. You create two named factories and select the corresponding factory on each `@KafkaListener`.

A container factory is a configuration blueprint for creating listener containers; it is neither a consumer nor a running container. When Spring processes a `@KafkaListener`, the selected factory creates a container endpoint with the corresponding configuration.

## 1. Why Are Multiple Container Factories Needed?

A Kafka application often has multiple data streams with different characteristics:

- `orders.events`: JSON events that need deserialization into `OrderCreated`, record-by-record processing, and commits after each record.
- `audit.events`: multiple audit records can be grouped into batches to reduce database write overhead.
- `payments.commands`: requires custom retry/error-handler handling and bounded concurrency to protect the payment system.
- `inventory.events`: requires a different consumer group and deserializer from the remaining streams.

If all listeners share a single factory, properties such as consumer factory, deserializer, concurrency, batch mode, and error handler may not fit every stream. Multiple factories encapsulate configuration by purpose and make explicit which policy each listener uses.

| Requirement | Configuration Separable by Factory |
| --- | --- |
| Different payloads | Separate `ConsumerFactory` and deserializers |
| Different processing speeds | `concurrency`, `pollTimeout`, `max.poll.records` |
| Record listener vs. batch listener | `setBatchListener(true/false)` |
| Different offset commit strategies | `AckMode` |
| Different retry/DLT policies | Separate `CommonErrorHandler` |
| Different transactions | Appropriate transaction manager or container properties |
| Different message conversion | Record/batch message converter |

It is not necessary to create a new factory for every listener. If two listeners share the same consumer, deserializer, and container semantics, they can share a single factory. Create a separate factory only when there is a meaningful difference to manage.

## 2. Distinguishing the Components

| Component | Responsibility |
| --- | --- |
| `ConsumerFactory<K,V>` | Creates Kafka consumers with configuration, key/value deserializers, and client properties |
| `ConcurrentKafkaListenerContainerFactory<K,V>` | Creates listener containers and applies concurrency, `AckMode`, error handler, transactions, and converters |
| `ConcurrentMessageListenerContainer<K,V>` | The actual container created by the factory; manages one or more child consumer containers |
| `@KafkaListener` | Declares a record-receiving endpoint and selects the container factory |
| `KafkaTemplate<K,V>` / `ProducerFactory<K,V>` | Sends records; not part of consumer listener container configuration |

A `ConcurrentKafkaListenerContainerFactory` can use a `ConsumerFactory` shared across multiple endpoints. Conversely, multiple factories can also share the same `ConsumerFactory` when differences lie only in container-level settings such as concurrency or `AckMode`.

For example:

```text
ordersKafkaListenerContainerFactory
    └── ordersConsumerFactory
          └── String key + OrderCreated JSON value

auditBatchKafkaListenerContainerFactory
    └── auditConsumerFactory
          └── String key + AuditEvent JSON value

@KafkaListener(containerFactory = "ordersKafkaListenerContainerFactory")
@KafkaListener(containerFactory = "auditBatchKafkaListenerContainerFactory")
```

## 3. Default Factory and Explicitly Selected Factories

If `@KafkaListener` omits the `containerFactory` attribute, Spring Kafka looks up the default factory by the bean name `kafkaListenerContainerFactory`.

Example declaring the default factory:

```java
@Bean(name = "kafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, Object>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, Object> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, Object>();
    factory.setConsumerFactory(consumerFactory);
    return factory;
}
```

Additional factories can use distinct names:

```java
@Bean(name = "ordersKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(...) { ... }

@Bean(name = "paymentsKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
        paymentsKafkaListenerContainerFactory(...) { ... }
```

Select a factory on the listener via the `containerFactory` attribute:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
```

The name in `containerFactory` must match the bean name exactly. If the bean name does not exist or the factory is incompatible with the key/value/deserializer types, the listener endpoint may fail to initialize or throw errors when receiving records.

Spring Boot usually auto-configures the default factory when the application does not provide one. If you only add custom factories with distinct names, Boot's default factory may still exist. When you want to replace the default factory, declare a bean named `kafkaListenerContainerFactory` and configure it completely for the application.

`@Primary` helps Spring pick a bean when autowiring by type with multiple candidates, but it does not override the default factory name convention used by `@KafkaListener`. If you want an endpoint to use a custom factory, specify `containerFactory` explicitly.

In Spring Framework configurations without Spring Boot auto-configuration, you must enable listener annotation processing with `@EnableKafka` on a `@Configuration` class. With Spring Boot Kafka auto-configuration, the listener infrastructure is usually already enabled; avoid duplicate configuration if the application already has this mechanism.

## 4. Creating Multiple ConsumerFactories for Different Payloads

Each `ConsumerFactory` defines how Kafka consumers are created. When topics carry different payloads, you can use deserializers typed for each DTO.

Suppose you have two DTOs:

```java
package com.example.messaging.event;

import java.math.BigDecimal;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

```java
package com.example.messaging.event;

public record AuditEvent(
        String eventId,
        String actor,
        String action,
        long occurredAt
) {}
```

You can configure two `ConsumerFactory` beans with different JSON deserializer target types:

```java
package com.example.messaging.config;

import java.util.HashMap;
import java.util.Map;
import com.example.messaging.event.AuditEvent;
import com.example.messaging.event.OrderCreated;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class KafkaConsumerFactories {

    private Map<String, Object> baseConsumerProperties(
            String bootstrapServers,
            String groupId
    ) {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        return props;
    }

    @Bean
    public ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers
    ) {
        return new DefaultKafkaConsumerFactory<>(
                baseConsumerProperties(bootstrapServers, "orders-service"),
                new StringDeserializer(),
                new JsonDeserializer<>(OrderCreated.class)
        );
    }

    @Bean
    public ConsumerFactory<String, AuditEvent> auditConsumerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers
    ) {
        return new DefaultKafkaConsumerFactory<>(
                baseConsumerProperties(bootstrapServers, "audit-service"),
                new StringDeserializer(),
                new JsonDeserializer<>(AuditEvent.class)
        );
    }
}
```

Both factories use the same broker and key deserializer, yet differ in group ID and value target type. In a real project, group ID, offset reset, security, and fetch settings can be placed in `application.yml`/configuration properties instead of hardcoding as in the example.

`JsonDeserializer` can use type headers to select the class if configured to do so. If you want each consumer factory to always deserialize into a fixed DTO, configure the target type and type-header usage policy consistently. Only trust packages containing required contracts; do not broaden trusted packages indiscriminately.

## 5. Creating Multiple ConcurrentKafkaListenerContainerFactories

Once the `ConsumerFactory` beans exist, create the corresponding container factories:

```java
package com.example.messaging.config;

import com.example.messaging.event.AuditEvent;
import com.example.messaging.event.OrderCreated;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaListenerContainerFactories {

    @Bean(name = "ordersKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                    @Qualifier("ordersConsumerFactory")
                    ConsumerFactory<String, OrderCreated> consumerFactory
            ) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );
        return factory;
    }

    @Bean(name = "auditBatchKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
            auditBatchKafkaListenerContainerFactory(
                    @Qualifier("auditConsumerFactory")
                    ConsumerFactory<String, AuditEvent> consumerFactory
            ) {
        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);
        factory.setBatchListener(true);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );
        return factory;
    }
}
```

Here:

- `ordersKafkaListenerContainerFactory` creates a record listener with three consumers per application instance and commits per `RECORD`.
- `auditBatchKafkaListenerContainerFactory` creates a batch listener with two consumers per instance and commits per `BATCH`.
- Each factory uses its correspondingly typed `ConsumerFactory`.
- `@Qualifier` helps Spring inject the right bean when multiple beans implement the same `ConsumerFactory` interface.

This illustrates configuring two listeners with different semantics. The actual number of consumers in each group also depends on the number of application replicas and topic partitions. Increasing concurrency beyond the partition count does not produce useful additional partition assignments.

## 6. Selecting a Factory in @KafkaListener

The Order listener selects the record factory:

```java
package com.example.messaging.consumer;

import com.example.messaging.event.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service",
            containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        // Process a single OrderCreated record.
    }
}
```

The Audit listener selects the batch factory:

```java
package com.example.messaging.consumer;

import java.util.List;
import com.example.messaging.event.AuditEvent;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class AuditListener {

    @KafkaListener(
            id = "auditListener",
            topics = "audit.events",
            groupId = "audit-service",
            containerFactory = "auditBatchKafkaListenerContainerFactory"
    )
    public void onAuditEvents(List<AuditEvent> events) {
        // Process a batch of AuditEvent records.
    }
}
```

The method signature must match the factory. A record listener typically accepts a single payload or `ConsumerRecord`; a batch listener can accept `List<Payload>`, `List<ConsumerRecord<K,V>>`, or other batch forms supported by Spring Kafka. Do not pick a batch factory and keep a method signature that only accepts a single DTO like a record listener.

## 7. Record Listener vs. Batch Listener

`setBatchListener(true)` causes the container to pass the list of records from a poll into the listener method. This can reduce overhead and allow bulk data processing, while changing error and commit boundaries.

| Characteristic | Record Listener | Batch Listener |
| --- | --- | --- |
| Common parameter | Single payload/record | List of payloads/records |
| Unit of processing | Individual record | A batch from poll |
| Common `AckMode` | `RECORD` or `BATCH` depending on needs | `BATCH` or manual by design |
| When a record fails | Can retry/recover individual record | Must identify the failing record in batch or retry entire batch |
| Throughput | Simple, record-by-record processing | Can optimize bulk I/O |
| Ordering | Easy to reason per record | Requires care when processing concurrently inside a batch |

Batch listeners suit bulk inserts, bulk updates, or APIs supporting lists. If you process a batch across multiple threads and return before all tasks finish, offsets can be acknowledged prematurely; acknowledgment and completion must be managed explicitly.

## 8. Each Factory Can Have Its Own Concurrency

`setConcurrency(n)` sets how many child consumer containers each listener container created by the factory uses. Thus, two factories can configure different concurrencies:

| Factory | Concurrency per Instance | Replicas | Total Consumer Members |
| --- | ---: | ---: | ---: |
| Orders | 3 | 2 | 6 |
| Audit batch | 2 | 2 | 4 |

The total is `replicas × concurrency` per listener endpoint. A group can only use parallelism up to the number of assigned partitions; if consumer members exceed partition count, some members will have no partitions.

You can override concurrency on an individual `@KafkaListener` via the `concurrency` attribute when differing from the factory default:

```java
@KafkaListener(
        topics = "orders.priority",
        groupId = "orders-service",
        containerFactory = "ordersKafkaListenerContainerFactory",
        concurrency = "5"
)
public void onPriorityOrder(OrderCreated event) {
    // This listener uses its own concurrency.
}
```

Do not raise concurrency just because you can. Consider partition count, CPU, downstream capacity, listener latency, and consumer lag.

## 9. Separate AckMode and Commit Policy per Stream

A factory can configure `AckMode` via `ContainerProperties`:

```java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
);
```

Common modes:

| AckMode | General Meaning |
| --- | --- |
| `RECORD` | Commit after each record listener invocation succeeds |
| `BATCH` | Commit after all records from a poll succeed |
| `TIME` | Commit when a time threshold is reached at container checkpoints |
| `COUNT` | Commit when a processed record count threshold is reached |
| `COUNT_TIME` | Combines count and time thresholds |
| `MANUAL` | Listener calls `Acknowledgment.acknowledge()`; container commits per mode semantics |
| `MANUAL_IMMEDIATE` | Requests immediate commit on acknowledgment on the consumer thread |

`enable.auto.commit=false` is commonly used so the Spring Kafka container manages offsets. Do not enable Kafka auto-commit alongside manual/container acknowledgment designs without fully understanding the interaction, as commits could happen before business logic finishes.

If listeners have different commit requirements, set `AckMode` on separate factories. Test listener failure, retry, and process restart scenarios to confirm which records may be redelivered.

## 10. Attaching Separate CommonErrorHandlers per Factory

Streams can have different error policies. For instance, Orders might need a few quick retries followed by DLT; Audit might use a longer backoff or a different recoverer.

A factory supports configuring `CommonErrorHandler`:

```java
factory.setCommonErrorHandler(ordersErrorHandler);
```

Example creating two independent handlers:

```java
@Bean
public DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer ordersRecoverer
) {
    return new DefaultErrorHandler(
            ordersRecoverer,
            new FixedBackOff(500L, 2L)
    );
}

@Bean
public DefaultErrorHandler auditErrorHandler(
        DeadLetterPublishingRecoverer auditRecoverer
) {
    return new DefaultErrorHandler(
            auditRecoverer,
            new FixedBackOff(2_000L, 5L)
    );
}
```

Imports require `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, and `FixedBackOff`; the recoverers can route to corresponding DLTs. Attach each handler to the appropriate factory:

```java
ordersFactory.setCommonErrorHandler(ordersErrorHandler);
auditFactory.setCommonErrorHandler(auditErrorHandler);
```

When using a batch listener, choose an appropriate way to indicate a failing record, such as `BatchListenerFailedException` to pinpoint the failing record's index. If the failing record cannot be identified, the error handler may have to retry/recover the entire batch per corresponding semantics. Check the behavior of your Spring Kafka version and listener type.

Do not share the same `DeadLetterPublishingRecoverer` if two streams require different destinations, serializers, or ACLs that the recoverer cannot handle. The error handler must be compatible with the record type and container mode.

## 11. Configuring Separate Transactions per Factory

If one listener needs Kafka transactions, a transaction manager can be attached to the container properties/factory per Spring Kafka configuration. Other listeners can still use non-transactional factories.

For Kafka transactions, configure a producer factory with a transaction ID prefix and an appropriate `KafkaTransactionManager`. The container participates in the transaction according to the configured semantics; offsets and Kafka outputs can be coordinated within the Kafka transaction.

Do not apply the same transaction manager mechanically to every factory. Distinguish between:

- A listener that only consumes and updates a database.
- A listener that consumes and publishes Kafka outputs needing Kafka transactions.
- A listener that updates a database and publishes to Kafka needing an outbox or appropriate coordination mechanism.

A Kafka transaction does not automatically encompass JDBC/HTTP side effects. If a listener updates a database and then the Kafka transaction rolls back, the database may still have committed unless the application coordinates separate transactions.

## 12. Shared Configuration vs. Specific Configuration

Not every property needs to be repeated. You can create a shared helper function for base consumer settings and override specific properties.

Example `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[security.protocol]": ${KAFKA_SECURITY_PROTOCOL:PLAINTEXT}

app:
  kafka:
    orders:
      group-id: orders-service
      concurrency: 3
    audit:
      group-id: audit-service
      concurrency: 2
```

You can bind the `app.kafka` section to `@ConfigurationProperties` for strongly typed configuration management. Each `ConsumerFactory` uses its own group ID and specific properties; each container factory uses its own concurrency/`AckMode`.

When using Spring Boot's auto-configured `ConsumerFactory`, shared properties under `spring.kafka.consumer` can be reused. However, if different deserializers per DTO are needed, you usually must create separate `ConsumerFactory` beans or configure a delegating deserializer capable of handling multiple types.

Do not copy full security or tuning settings across multiple places if they are identical. Create a shared property builder or configuration properties class to avoid drift across factories.

## 13. Sharing One ConsumerFactory Across Multiple Container Factories

If listeners share the same broker, group, deserializers, and consumer client properties, you can share a single `ConsumerFactory` while creating multiple container factories for different concurrency or `AckMode`:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersFastFactory(
                @Qualifier("ordersConsumerFactory")
                ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersLowConcurrencyFactory(
                @Qualifier("ordersConsumerFactory")
                ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(1);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.BATCH);
    return factory;
}
```

Both factories share consumer properties yet create containers with different concurrency and acknowledgment settings. If listeners share the same `group.id` and subscribe to the same topic, they join the same group and split partitions among themselves. If each needs independent copies of all events, separate group IDs are required.

Avoid sharing the same `ConsumerFactory` when listeners genuinely need different group IDs, deserializers, or security identities. Consumer-level properties belong on `ConsumerFactory` and cannot be separated solely via container factories.

## 14. Message Converters and Payload Types

Beyond deserializers, a container factory can configure a message converter to translate `ConsumerRecord`/messages into listener parameters. Distinguish:

- Kafka deserializers convert byte arrays into Java keys/values.
- Spring message converters convert payloads/headers into method argument types.
- The listener method signature determines the parameter types the endpoint receives.

For example, a factory can set a record message converter:

```java
factory.setRecordMessageConverter(recordMessageConverter);
```

A batch listener may require an appropriate batch message converter if converting the whole batch into `List<SomeType>` or Spring `Message`. Do not configure a record converter for a batch listener and assume identical semantics; check the converter type and listener signature.

When using a JSON deserializer with a direct target type, the listener typically receives the deserialized DTO. When using `StringDeserializer` with a Spring-level JSON converter, standardize on one strategy to avoid double deserialization or receiving `String` when the listener expects a DTO.

## 15. Container Factories Are Not Dynamic Containers

Multiple factories and dynamic containers are related but distinct concepts:

- Multiple factories define multiple configuration profiles for creating listener containers.
- Dynamic containers are containers created, registered, and started/stopped at runtime according to application needs.

`@KafkaListener` is usually processed when the application context starts. If you need to create listener endpoints or containers for tenants/topics appearing at runtime, you can use `KafkaListenerEndpointRegistry` or `ConcurrentKafkaListenerContainerFactory.createContainer(...)` and manage lifecycle yourself.

Example creating a container manually from a factory:

```java
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;

ConcurrentMessageListenerContainer<String, OrderCreated> container =
        ordersKafkaListenerContainerFactory.createContainer("orders.tenant-a");

container.getContainerProperties().setGroupId("orders-tenant-a");
container.setupMessageListener((MessageListener<String, OrderCreated>) record -> {
    orderService.handleTenant("tenant-a", record.value());
});

container.start();
```

Manually created containers must have their references retained and be stopped/closed properly per lifecycle when no longer needed. Do not create a new container per HTTP request; doing so can spawn excessive consumers and group memberships. Manage the container set along tenant or topic lifecycles with resource limits.

If you only need fixed listeners with differing configurations, declaring multiple `@KafkaListener` methods and selecting factories is generally simpler than building dynamic containers manually.

## 16. Naming and Organizing Configuration

Bean names should reflect their purpose and processing style, for example:

| Bean Name | Purpose |
| --- | --- |
| `kafkaListenerContainerFactory` | Default factory |
| `ordersKafkaListenerContainerFactory` | Record listener factory for Order |
| `auditBatchKafkaListenerContainerFactory` | Batch listener factory for Audit |
| `paymentsKafkaListenerContainerFactory` | Payment listener factory with dedicated error policy |
| `ordersConsumerFactory` | Consumer factory for Order |
| `auditConsumerFactory` | Consumer factory for Audit |

Configuration classes can be split by domain (`OrdersKafkaConfiguration`, `AuditKafkaConfiguration`) as the number of factories grows. If everything lives in one oversized configuration class, changing one listener could inadvertently impact another stream.

Use `@Qualifier` when injecting multiple beans sharing the same interface. Give clear names to `ConsumerFactory`, `CommonErrorHandler`, `KafkaTemplate`, and container factory beans to avoid relying on ordering or generic types that IDEs struggle to disambiguate.

## 17. Verifying Effective Factory Configuration

When the application runs, verify each listener uses the expected factory:

- Check `containerFactory` on each `@KafkaListener`.
- Check bean names registered in the application context.
- Inspect container startup logs and consumer client IDs.
- Verify group IDs, key/value deserializers, and assignments.
- Verify concurrency via the number of consumer members in the group.
- Verify `AckMode`, error handler, and transaction manager per factory.

You can inspect groups using the Kafka CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

This command reports consumer members, topics/partitions, offsets, and lag. It does not directly show all Spring factory settings, so combine it with application logs or actuator/metrics to verify concurrency, processing times, and error handling.

## 18. Testing Multiple Container Factories

Integration tests should confirm that each listener actually uses the right factory and receives the expected payload type.

A scenario with `@EmbeddedKafka` or Testcontainers:

1. Create `orders.events` and `audit.events` with appropriate partitions.
2. Start a context containing both `ordersKafkaListenerContainerFactory` and `auditBatchKafkaListenerContainerFactory`.
3. Send `OrderCreated` to the Orders topic and verify the record listener receives a single DTO.
4. Send multiple `AuditEvent` records to the Audit topic and verify the batch listener receives a list.
5. Check the group ID and partition assignment of each listener.
6. Verify the different concurrencies between the two factories.
7. Make a listener throw an exception and verify the corresponding factory's error handler is invoked.
8. Check `AckMode`/committed offsets on both success and failure.
9. If transactions are used, verify rollback/commit behavior on the corresponding factory.
10. Verify the application still has a default factory for listeners omitting `containerFactory` if the design relies on it.

Do not merely check that beans exist. Verify that endpoints are registered, containers have started, and messages pass through the right deserializers/handlers. Use `CountDownLatch`, `BlockingQueue`, or timeout-bounded assertions rather than fixed `Thread.sleep()`.

## 19. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Listener fails to start | `containerFactory` points to a non-existent bean name | Check bean name and spelling |
| Listener receives `LinkedHashMap` instead of DTO | Deserializer/type headers not configured for expected target type | Check `JsonDeserializer`, type mapping, and trusted packages |
| Listener receives wrong payload type | Wrong factory or `ConsumerFactory` selected | Check `containerFactory` and `@Qualifier` |
| Multiple `ConsumerFactory` beans cause injection error | Multiple beans of the same interface without qualifiers | Use `@Qualifier` explicitly |
| Batch listener receives a single record instead of `List` | Factory does not have `setBatchListener(true)` enabled | Use the right batch factory and method signature |
| Record listener receives unexpected type | Batch factory assigned to record endpoint or vice versa | Align factory mode with listener signature |
| Concurrency differs from expectations | Annotation override or partition count limiting assignments | Check factory, endpoint, and group assignments |
| Two listeners unintentionally split messages | Sharing the same group ID on the same topic | Use distinct group IDs if independent fan-out is needed |
| Error handler is not invoked | Handler attached to a different factory than the one the listener uses | Check the endpoint's factory bean |
| Offset commits behave unexpectedly | Misaligned `AckMode`/auto-commit or manual acknowledgment | Inspect container properties and test crash/retry |
| Transactions have no effect | Factory lacks proper transaction manager or producer factory is non-transactional | Check transaction configuration per endpoint |
| Too many consumers created | Many factories/endpoints with high concurrency across many replicas | Calculate total consumers and partitions before scaling |

## 20. Multiple-Factory Configuration Checklist

Before deploying, confirm:

1. A default factory named `kafkaListenerContainerFactory` exists if any listener relies on the default.
2. Each custom factory has a unique, clear bean name.
3. Each `@KafkaListener` selects the right `containerFactory`.
4. `ConsumerFactory` beans have appropriate group IDs, deserializers, and security properties.
5. `@Qualifier` is used when injecting multiple beans of the same interface.
6. Record/batch mode matches the method signature.
7. Concurrency is sized based on partition count and replica count.
8. `AckMode` aligns with processing and retry boundaries.
9. Error handlers/recoverers are attached to the right factories.
10. Transaction managers are configured only for listeners requiring transactions.
11. Message converters match record/batch payloads.
12. Factories are shared only when consumer-level properties are genuinely compatible.
13. Dynamic containers have separate lifecycle management if created at runtime.
14. Integration tests verify routing, deserialization, assignment, error handling, and offsets.
15. Metrics/logs exist to monitor consumer groups, lag, processing latency, and rebalances.

Multiple `ConcurrentKafkaListenerContainerFactory` beans allow a service to organize listeners according to distinct requirements for consumers, payloads, concurrency, batching, acknowledgment, and error handling. Selecting a factory via `containerFactory` ensures each endpoint uses the right configuration. Separate factories when semantics differ, share configurations when compatible, and always test actual containers rather than just verifying bean creation.

## 21. Self-Check

1. How do `ConsumerFactory` and `ConcurrentKafkaListenerContainerFactory` differ in responsibility?
2. Why does Spring Kafka look for the `kafkaListenerContainerFactory` bean by default when an annotation omits `containerFactory`?
3. When should an application create multiple `ConsumerFactory` beans rather than just multiple container factories?
4. How does `@KafkaListener` select a custom factory?
5. Why is `@Qualifier` needed when injecting multiple `ConsumerFactory` beans?
6. How does `setBatchListener(true)` affect the method signature?
7. Why can each factory configure its own concurrency and `AckMode`?
8. What happens if listeners share the same group ID and subscribe to the same topic?
9. How do multiple container factories differ from dynamic containers created at runtime?
10. What should you test to confirm a listener actually uses the right factory?

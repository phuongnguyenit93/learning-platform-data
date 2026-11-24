# ConcurrentKafkaListenerContainerFactory

In Spring Kafka, **ConcurrentKafkaListenerContainerFactory** is the factory used to create listener containers for methods annotated with **@KafkaListener**. The factory combines **ConsumerFactory**, container configuration, and endpoint metadata to produce a **ConcurrentMessageListenerContainer**. This container manages one or more Kafka consumers, invokes the listener, handles acknowledgments, commits offsets, and coordinates operational mechanisms such as error handlers, concurrency, and transactions.

The factory is a critical configuration point for the consumer side of a Spring Kafka application. When tuning how listeners run in production, development teams configure the factory rather than manually creating `KafkaConsumer` instances and writing poll loops.

## 1. Where does the factory sit in the Spring Kafka architecture?

A listener pipeline has these main components:

- **Kafka broker** stores records by topic and partition, serves fetch requests, manages consumer groups, and stores committed offsets.
- **ConsumerFactory** creates Kafka consumers with client configurations such as bootstrap servers, deserializers, group ID, security, and consumer properties.
- **ConcurrentKafkaListenerContainerFactory** creates listener containers and applies operational settings to them.
- **ConcurrentMessageListenerContainer** manages child listener containers and the configured number of consumers.
- **KafkaMessageListenerContainer** owns one Kafka consumer, performs polling, and invokes the listener on its processing thread.
- **@KafkaListener** marks the method that receives a record or batch of records.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["Kafka listener endpoint registry"]
    B --> C["ConcurrentKafkaListenerContainerFactory"]
    D["ConsumerFactory"] --> C
    E["Container configuration<br/>AckMode, concurrency, error handler"] --> C
    C --> F["ConcurrentMessageListenerContainer"]
    F --> G["KafkaMessageListenerContainer 1"]
    F --> H["KafkaMessageListenerContainer 2"]
    F --> I["KafkaMessageListenerContainer N"]
    G --> J["Kafka consumer 1"]
    H --> K["Kafka consumer 2"]
    I --> L["Kafka consumer N"]
    J --> M["Kafka broker"]
    K --> M
    L --> M
~~~

The factory is neither a Kafka broker nor a polling Kafka consumer. It is an object that configures and creates containers. Actual consumers are created from `ConsumerFactory` when the listener container starts.

## 2. Distinguishing commonly confused components

| Component | Responsibility |
|---|---|
| **ConsumerFactory** | Creates Kafka consumers and provides client configuration |
| **ConcurrentKafkaListenerContainerFactory** | Creates concurrent listener containers, applies concurrency and container properties |
| **ConcurrentMessageListenerContainer** | Coordinates multiple child `KafkaMessageListenerContainer` instances |
| **KafkaMessageListenerContainer** | Manages one consumer, polls records, and invokes the listener |
| **@KafkaListener** | Declares a message-receiving endpoint and metadata such as topics, group ID, and container factory |
| **KafkaListenerEndpointRegistry** | Registers and manages the lifecycle of listener containers created from endpoints |

A helpful mnemonic: **ConsumerFactory creates clients; listener container factory creates containers; the container manages clients and invokes the listener**.

Do not mistakenly configure consumer properties on the container factory. For example, deserializers, bootstrap servers, and group ID are Kafka consumer settings, usually provided via `ConsumerFactory`. `AckMode`, poll timeout, concurrency, and error handler are settings governing listener container execution.

## 3. How the factory is used with @KafkaListener

When an application enables annotation-driven listener support, Spring registers endpoints declared with **@KafkaListener**. The endpoint registry uses the appropriate factory to create a container for each endpoint.

In plain Spring Framework applications, this capability can be enabled with **@EnableKafka**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;

@Configuration
@EnableKafka
public class KafkaListenerEnablement {
}
~~~

With Spring Boot, Kafka auto-configuration typically already sets up annotation-driven listener infrastructure. There is no need to add **@EnableKafka** mechanically if Boot already manages this.

Example listener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrderCreated(OrderCreated event) {
        inventoryService.reserve(event);
    }
}
~~~

If the application has a factory bean with the default name **kafkaListenerContainerFactory**, endpoints can use that factory without explicitly specifying the **containerFactory** attribute. When there are multiple factories, specify the factory name on the annotation:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

The **containerFactory** value must match a factory bean name registered in the Spring context. If the bean name is wrong or the factory does not exist, the endpoint cannot be created with the intended configuration.

## 4. Basic factory configuration

A factory typically needs a `ConsumerFactory`, concurrency, acknowledgment mode, and error handler. The example below uses modern Spring Kafka APIs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)
                )
        );

        return factory;
    }
}
~~~

In the example:

- **setConsumerFactory** supplies the factory that creates Kafka consumers.
- **setConcurrency(3)** instructs the container to run with three child consumers for endpoints using this factory.
- **AckMode.RECORD** instructs the container to commit progress after each successfully processed record according to that mode's semantics.
- **DefaultErrorHandler** provides an exception handling policy with a 1-second backoff and up to two retries in this illustrative setup.

Error handler APIs can differ by Spring Kafka version. For older codebases, check the dependency version before using **setCommonErrorHandler** or newer APIs. Do not mix configuration examples from multiple versions in the same application.

The listener can select the factory by bean name:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

If using a single default factory across the entire application, you can name the bean **kafkaListenerContainerFactory**. Spring Boot usually creates a default factory when the application has not provided a bean with that name. When defining the default bean yourself, review Boot's previous auto-config settings so you do not accidentally omit configurations like message converters or customizers currently used by the application.

## 5. Configuring via Spring Boot

For applications using Spring Boot, many listener properties can be declared in **application.yml**:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
    listener:
      concurrency: 3
      ack-mode: record
      poll-timeout: 1s
~~~

Spring Boot can auto-configure `ConsumerFactory` and the default listener container factory from these properties. This is simple when the application has only one group of consumers sharing the same policy.

If multiple listener configurations are needed, declare separate factories. For example, an order-processing service needs higher concurrency, while a reporting service needs lower concurrency and a batch listener. Each factory can use a `ConsumerFactory` and container properties suited to its workload.

Distinguish two configuration groups:

| Configuration group | Examples | Where applied |
|---|---|---|
| Kafka consumer client | bootstrap servers, group ID, deserializer, security, fetch settings | `ConsumerFactory` |
| Listener container | concurrency, `AckMode`, poll timeout, error handler, transaction manager | `ConcurrentKafkaListenerContainerFactory` / `ContainerProperties` |

Some Boot properties can be bound to the default factory. When creating a custom factory, do not assume every YAML property automatically applies to your custom bean. Explicitly configure needed values or use customizer mechanisms provided by your Boot version.

## 6. Concurrency and how the container creates consumers

A key capability of **ConcurrentKafkaListenerContainerFactory** is configuring the number of consumers running in parallel for a listener endpoint.

~~~java
factory.setConcurrency(3);
~~~

When the container starts, **ConcurrentMessageListenerContainer** creates and manages child **KafkaMessageListenerContainer** instances. Each child container uses one Kafka consumer and polls on its own thread.

With concurrency 3, an endpoint can be served by three consumers. If the consumers join the same consumer group, Kafka distributes subscribed partitions among the group members according to the assignment mechanism.

Example of a topic with six partitions and listener concurrency 3:

~~~mermaid
flowchart TD
    A["orders.created<br/>6 partitions"] --> B["Consumer group inventory-service"]
    B --> C["Consumer 1<br/>Partition 0, 1"]
    B --> D["Consumer 2<br/>Partition 2, 3"]
    B --> E["Consumer 3<br/>Partition 4, 5"]
~~~

The diagram shows one illustrative distribution. Actual assignment depends on the partition assignor, number of active consumers, member subscriptions, and group state.

### Concurrency is not partition count

A topic with six partitions cannot create six parallel processing streams simply by setting an arbitrarily large concurrency if the application only has six partitions and one group. When the number of consumers exceeds assignable partitions, some consumers receive no partitions and process no records.

For a single-partition topic, increasing concurrency in the same group creates no additional parallel processing for that partition. Kafka still preserves record order within a partition and assigns that partition to only one consumer in the group at a time.

### Choosing concurrency

Consider these factors:

- Number of partitions in the topics the listener subscribes to.
- Target throughput and processing time per record.
- Parallelism capacity of the database or downstream services.
- Application CPU, memory, and network.
- Number of consumers running in the same group on other instances.
- Rebalance cost when consumer counts change.

Too low concurrency can leave some partitions underutilized. Too high concurrency can create idle consumers, increase connections, and overload downstream. Measure performance in a production-like environment before choosing a value.

### Concurrency across multiple instances

If there are three application instances and each instance creates a listener with concurrency 3, total consumers in the group can be nine. Calculate total consumers across the whole deployment, rather than looking only at the concurrency value in one pod.

Example:

| Instance count | Concurrency per instance | Expected total consumers |
|---:|---:|---:|
| 1 | 3 | 3 |
| 2 | 3 | 6 |
| 3 | 3 | 9 |
| 4 | 2 | 8 |

Actual consumers may be lower if containers have not started or listeners are stopped. If consumer count exceeds assigned partitions, some consumers have no partitions to process.

## 7. One factory or multiple factories?

One default factory is enough when listeners share the same requirements for consumer, acknowledgment, concurrency, error handling, and transactions.

When workloads behave differently, separating factories makes operational policies clearer.

Example:

- **ordersListenerFactory** uses a record listener, concurrency 4, and short retries for transient errors.
- **auditBatchListenerFactory** uses a batch listener, concurrency 2, and appropriate batch error handling.
- **transactionalListenerFactory** uses a transaction manager and dedicated transaction configuration.
- **slowDependencyListenerFactory** has low concurrency to protect a slow downstream service.

Each factory can share the same `ConsumerFactory` if consumer client properties are compatible, or use separate `ConsumerFactory` instances if different default group IDs, deserializers, security, or fetch configurations are needed.

Example declaring two factories:

~~~java
@Configuration
public class ListenerFactoriesConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
    auditBatchListenerFactory(
            ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

        factory.setConsumerFactory(auditConsumerFactory);
        factory.setConcurrency(2);
        factory.setBatchListener(true);

        return factory;
    }
}
~~~

Listeners select their corresponding factory:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}

@KafkaListener(
    topics = "audit.events",
    groupId = "audit-processor",
    containerFactory = "auditBatchListenerFactory"
)
public void onAuditEvents(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
~~~

Two factories allow configuring concurrency and listener type separately. They also clarify the owner of each workload when investigating errors, lag, or throughput.

Do not create a new factory for every listener if settings are identical and there is no specific operational reason. Too many similar factories make configuration harder to follow and risk unintended divergence.

## 8. Record listener and batch listener

The factory can create containers operating in record mode or batch mode.

### Record listener

This is the common mode when each listener invocation processes one record:

~~~java
factory.setBatchListener(false);

@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    orderService.process(event);
}
~~~

The container invokes the listener for each record. This fits processing independent events, classifying errors per record, or controlling side effects individually for each message.

### Batch listener

When batch mode is enabled:

~~~java
factory.setBatchListener(true);
~~~

The listener receives a collection of records from a single poll:

~~~java
@KafkaListener(
    topics = "audit.events",
    containerFactory = "auditBatchListenerFactory"
)
public void onAuditEvents(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
~~~

Batch listeners can reduce downstream call overhead or enable batch database writes. In return, error handling is more complex because one failing record can affect handling of the entire batch. You must determine which records succeeded, which failed, and which offsets may be committed.

Do not use a batch listener factory for a method designed to receive a single record. Listener parameter types must be compatible with the container mode.

## 9. Configuring ContainerProperties

The factory provides **getContainerProperties()** to configure properties affecting how the container runs.

Common settings:

| Property | Effect |
|---|---|
| **AckMode** | Selects when and how the container commits offsets |
| **pollTimeout** | Wait time during a single poll |
| **ackTime** | Time threshold used with `AckMode.TIME` |
| **ackCount** | Record threshold used with `COUNT` or `COUNT_TIME` |
| **syncCommits** | Selects synchronous or asynchronous commits |
| **shutdownTimeout** | Time the container waits during shutdown |
| **idleEventInterval** | Interval for emitting idle events when applicable |
| **transactionManager** | Connects the listener container with a transaction manager per supported API/version |

Example:

~~~java
var properties = factory.getContainerProperties();

properties.setAckMode(ContainerProperties.AckMode.TIME);
properties.setAckTime(5_000L);
properties.setPollTimeout(1_000L);
properties.setSyncCommits(true);
~~~

Properties must be chosen according to delivery semantics and operational requirements. For instance, `TIME` batches offsets by time; `RECORD` commits per processed record; `MANUAL` lets the listener explicitly acknowledge. Do not choose an `AckMode` merely to reduce commit requests while ignoring redelivery implications.

**ContainerProperties** is container configuration. Properties such as deserializers, group ID, and security still belong to consumer configuration created via `ConsumerFactory`.

## 10. Error handlers and error recovery

The factory is where **CommonErrorHandler** can be attached for containers created from it. The error handler decides how the container reacts when a listener throws an exception: retry, backoff, recover, or route the record to another processing flow.

Example attaching `DefaultErrorHandler`:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

factory.setCommonErrorHandler(
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L)
        )
);
~~~

This example retries with a 1-second pause and two retries. Real policies need error classification:

- Transient errors like downstream timeouts can be retried with backoff.
- Invalid data errors should usually not be retried many times.
- Authorization or configuration errors are typically not resolved by continuous retries.
- Poison messages need controlled recovery, potentially routed to a DLT if the producer has permissions and the DLT is configured.

For record listeners and batch listeners, error handler semantics can differ. Batch listeners need to identify the failing record in the batch and the acknowledged offset portion. With APIs such as **BatchListenerFailedException**, applications can provide the failing record position to the appropriate handler.

A factory sharing an error handler can fit listeners with the same policy. If workloads need different retry policies, split factories or configure separate handlers as supported by your Spring Kafka version.

## 11. Transactions and acknowledgments

The listener container can coordinate with a Kafka transaction manager or other appropriate transaction manager depending on Spring Kafka configuration.

With Kafka transactions, the container can process records within a transaction and coordinate offsets with the transaction upon commit. If the transaction rolls back, records may be read again depending on consumer state and configuration. When using transactions, examine transactional listener container semantics instead of simply extrapolating from non-transactional `AckMode` behavior.

The factory can be configured to use a transaction manager via **ContainerProperties**. Specific APIs have changed across Spring Kafka versions; use the right transaction manager type and method for your application's version.

Some principles:

- Do not catch exceptions inside the listener and return normally if you want the transaction to roll back.
- Do not treat a database transaction and a Kafka transaction as an automatically atomic single transaction.
- If the listener updates a database and emits events to Kafka, consider outbox/inbox or an appropriate coordination mechanism.
- Consumers still need idempotency when redelivery is possible.
- Use exactly-once only when clearly defining the scope of resources protected by the Kafka transaction.

## 12. Rebalances, ordering, and thread safety

Each child consumer managed by the concurrent container joins the consumer group. When consumer counts change, instances start/stop, or partitions are added, Kafka may perform a rebalance to redistribute partitions.

Rebalances can cause:

- Partitions temporarily going unprocessed while assignments shift.
- Listeners starting to process newly assigned partitions.
- Uncommitted records being read again.
- Consumer lag increasing during handover.
- Duplicate side effects if the application is not idempotent.

Concurrency does not create global ordering across partitions. Kafka preserves order within one partition. If events for the same aggregate must be processed sequentially, the producer must choose a stable key so they land in the same partition, and the listener should not offload side effects to unordered async tasks.

Because the factory can create multiple consumers and invoke listeners concurrently, listener beans and shared dependencies must be thread-safe. Avoid storing per-message mutable state in fields of a singleton listener without proper synchronization. Prefer stateless listeners and place business state in a database or dedicated state store.

If the listener calls a database or external API, cap concurrency according to downstream capacity. Adding consumers does not help when the database connection pool is already saturated.

## 13. Container lifecycle and management

The factory creates containers when endpoints are registered. The endpoint registry manages containers created from **@KafkaListener** methods and controls their lifecycle per application configuration.

Key points to understand:

- **autoStartup** decides whether the container starts automatically with the lifecycle.
- Containers can be managed through **KafkaListenerEndpointRegistry**.
- When controlled stopping or starting of a listener is needed, operate on the container via the registry.
- The factory is configuration for creating containers; changing the factory after containers have been created does not automatically ensure running containers are reconfigured.
- When changing critical settings like concurrency or consumer properties, follow an appropriate restart/recreate procedure and verify state post-deployment.

Example getting a container by ID:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class ListenerLifecycleManager {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleManager(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null && container.isRunning()) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
~~~

To retrieve a container by ID, the endpoint must declare an ID:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

Stopping a listener can cause consumers to leave the group and trigger a rebalance. Before stopping, consider draining in-flight work, shutdown timeout, committed offsets, and redelivery possibility.

## 14. Per-endpoint customization

One factory can serve multiple endpoints. If an endpoint needs different settings, check annotation-level overrides or container customizers supported by your Spring Kafka version.

Information typically decided at the endpoint:

- Topic or pattern subscription.
- Group ID.
- Listener ID.
- Container factory to use.
- Auto startup.
- Concurrency override if supported by the API version.
- Topic partition assignment if explicit partition assignment is needed.

Example of two endpoints using the same factory with different topics and group IDs:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}

@KafkaListener(
    id = "returnsListener",
    topics = "returns.created",
    groupId = "returns-service",
    containerFactory = "ordersListenerFactory"
)
public void onReturnCreated(ReturnCreated event) {
    returnsService.process(event);
}
~~~

Sharing a factory means both endpoints share default container settings from the factory. They can still have separate group IDs and topics. If concurrency, error handler, transaction, or batch mode requirements differ, consider separate factories so one change does not affect multiple workloads.

## 15. Observing and diagnosing listener factories

When a listener does not run or throughput falls short, inspect layer by layer instead of looking only at listener method logs.

| Symptom | Check in application | Check in Kafka |
|---|---|---|
| Listener does not start | Does factory bean exist, `containerFactory` name, endpoint registration, startup exceptions | Bootstrap connectivity, authentication, and authorization |
| No records received | Topic subscription, group ID, deserializer, listener lifecycle, filter | Topic/partition, committed offset, ACL READ, and group coordination |
| Concurrency does not increase throughput | Effective concurrency value, instance count, listener processing, and downstream bottleneck | Partition count, assignment, and consumer group membership |
| Consumer idle | Did factory create enough containers, subscription, and group ID | Partition assignment, partition count, and topic availability |
| Continuous rebalances | Listener processing time, poll interval, shutdown, and exceptions | Group coordinator, network, and cluster stability |
| Slow offset commit | `AckMode`, `ackTime`/`ackCount`, error handler, and commit configuration | Commit latency, coordinator health, and network |
| Duplicate record processing | Side effects, acknowledgment, transaction rollback, and idempotency | Committed offset and rebalance state |
| Batch processing errors | Batch listener signature, error handler, and failed record index | Records in partition and offset state |

### Metrics to monitor

- Consumer lag by group, topic, and partition.
- Active consumer count and partition assignments.
- Record consumption rate.
- Listener processing time.
- Commit rate and commit latency.
- Rebalance count and rebalance duration.
- Retry, recovery, and DLT rates.
- Number of running or stopped listener containers.

Metric names depend on Kafka client, Micrometer, and monitoring system. Tag with service, environment, group ID, and listener ID to investigate the right workload.

## 16. Common configuration errors

**No factory bean with matching name.** Annotation points to **ordersListenerFactory** but the Spring context has no such bean. Check bean names and configuration package scanning.

**Multiple listeners sharing a factory despite different requirements.** A concurrency or error handler change can affect all endpoints using the factory. Split factories when genuine operational differences exist.

**Confusing ConsumerFactory with ConcurrentKafkaListenerContainerFactory.** Deserializers and security are configured on the consumer client, not on the container factory.

**Increasing concurrency beyond partition count.** Consumer count increases without adding partitions; some consumers may sit idle without increasing throughput.

**Ignoring instance count.** Concurrency is multiplied by running instances. Total consumer group size can be much larger than expected.

**Using a batch factory for a record listener.** Listener type and batch mode must match. Misconfiguration can cause message conversion or listener invocation errors.

**Using an inappropriate error handler.** Batch listeners and record listeners have different semantics. Retry/recovery must be designed for the listener type.

**Assuming factory changes auto-update running containers.** The factory creates containers. Configuration changes require a restart or recreate procedure and runtime verification.

**Singleton listener holding non-thread-safe state.** Concurrency can cause multiple threads to call the same listener bean. Mutable state must be protected or eliminated.

**Increasing concurrency to handle slow downstream.** This can overload the dependent database or API further. Measure the bottleneck before adding consumers.

## 17. Runbook when a listener factory has issues

When a listener endpoint is not behaving as expected:

1. Identify the listener ID, topic, group ID, and affected instance.
2. Verify the endpoint is registered and using the intended **ConcurrentKafkaListenerContainerFactory** bean.
3. Check the `ConsumerFactory` used by the factory.
4. Read effective concurrency, `AckMode`, poll timeout, error handler, and transaction configuration.
5. Verify partition count and total consumers across all instances.
6. Check startup logs, authentication/authorization, deserialization, and listener exceptions.
7. Cross-check consumer lag, partition assignments, commit latency, and rebalance count.
8. If changing configuration, identify which endpoints use that factory to assess blast radius.
9. Deploy changes cleanly, verifying containers are recreated or restarted properly.
10. Monitor throughput, lag, duplicates, retries, and DLT after recovery.

When an issue affects multiple listeners sharing a factory, check shared configuration before fixing individual listeners. When only one endpoint fails, focus on endpoint metadata, subscription, and selected factory.

## 18. Checklist before deploying a listener factory to production

**Structure and configuration**

- [ ] `ConsumerFactory` is properly configured with bootstrap servers, group ID, deserializers, and security.
- [ ] Factory bean name matches the listener's **containerFactory** attribute.
- [ ] Default **kafkaListenerContainerFactory** exists if endpoints rely on the default.
- [ ] `AckMode`, poll timeout, and commit behavior align with delivery semantics.
- [ ] Error handler has clear retry, backoff, and recovery rules.

**Concurrency and listener type**

- [ ] Concurrency is chosen based on partition count and total instances.
- [ ] Checked for idle consumers when concurrency exceeds assignable partitions.
- [ ] Record listeners and batch listeners use matching factory modes.
- [ ] Listeners and shared dependencies are thread-safe.
- [ ] Concurrency does not overload downstream systems.

**Lifecycle and recovery**

- [ ] Listener ID is declared if management via registry is needed.
- [ ] Shutdown and restart are controlled.
- [ ] Rebalances and redelivery are accounted for.
- [ ] Consumer idempotency protects side effects.
- [ ] Transaction behavior is clearly understood if a transaction manager is used.

**Observability**

- [ ] Monitor consumer lag, throughput, processing time, and commit latency.
- [ ] Monitor rebalances, retries, recoveries, and DLT.
- [ ] Logs include service, environment, group ID, listener ID, topic, and partition.
- [ ] Runbook explains how to identify the factory and effective configuration.

## 19. Design principles

**ConcurrentKafkaListenerContainerFactory** centralizes how Spring Kafka creates and configures listener containers. It connects `ConsumerFactory` with **@KafkaListener** endpoints, determining concurrency, listener type, and container policies such as acknowledgment, error handling, and transaction integration.

Use the default factory when listeners share the same operational requirements. When workloads differ in concurrency, batch processing, retries, or transactions, create dedicated factories and bind them explicitly to each endpoint. Evaluate total consumers across the whole deployment, keep listeners thread-safe, and monitor lag, commits, and rebalances to adjust configuration based on real system behavior.

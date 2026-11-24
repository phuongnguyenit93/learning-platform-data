# Registering Endpoints Dynamically

In many applications, the list of Kafka listeners is known before startup and can be declared directly with `@KafkaListener`. However, some systems need to create subscriptions at runtime: a new tenant is activated, a user subscribes to an event stream, an operational task needs to listen to a topic for a limited time, or subscription configurations are loaded from a database.

Spring Kafka supports registering listener endpoints via `KafkaListenerEndpointRegistry`. Each endpoint describes which topic, partition, or topic pattern the listener should run on; the container factory creates the corresponding consumer container. This lets you create, look up, stop, and remove containers during the application lifecycle without calling `KafkaConsumer.poll()` yourself.

## 1. Distinguishing Endpoint, Container, and Consumer Group

Three concepts should be kept separate:

- **Listener endpoint:** describes the subscription configuration and message listener, such as endpoint ID, group ID, topic, and record-processing callback.
- **Listener container:** the Spring Kafka component that creates and manages Kafka consumers, the poll loop, threads, acknowledgment, error handler, and lifecycle.
- **Consumer group:** a group of consumers coordinated by Kafka to divide partitions. The group ID is a Kafka-side identifier, distinct from the application's endpoint ID.

`KafkaListenerEndpointRegistry` holds containers created from endpoints, including endpoints declared with `@KafkaListener` and endpoints registered programmatically. The registry helps look up containers by ID and manage their lifecycle.

| Identifier | Scope | Example |
| --- | --- | --- |
| Endpoint ID | Unique within the registry of an application context | `tenant-orders-42` |
| Consumer group ID | Used by Kafka to coordinate consumers | `orders-tenant-42` |
| Topic | Stream of records in Kafka | `orders` |

Do not treat the endpoint ID as if it automatically creates a consumer group. If multiple endpoints share the same group ID and subscribe to the same topic, Kafka treats them as consumers in the same group and divides partitions among them. If each tenant needs to receive all records independently, each tenant usually needs its own group ID.

## 2. Preparing a Listener Container Factory

Dynamic endpoints still require a `KafkaListenerContainerFactory`. The factory uses a `ConsumerFactory` to create consumers and applies shared configuration such as deserializers, concurrency, error handler, acknowledgment, and transactions.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class DynamicKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    dynamicOrderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);
        return factory;
    }
}
```

This example sets concurrency to two consumer threads per container. Effective concurrency is bounded by the number of assigned partitions and application resources. If many endpoints are created at once, the total number of consumers and threads can grow rapidly; do not pick a high concurrency simply because the factory allows it.

A factory can be shared across multiple endpoints if they have the same deserializer configuration and processing policies. If each subscription type requires different security, transaction, or error-handling settings, use separate factories or an appropriate endpoint configuration.

## 3. Registering an Endpoint with KafkaListenerEndpointRegistry

`SimpleKafkaListenerEndpoint` fits when the application wants to attach a `MessageListener` directly to an endpoint. The following example creates a subscription for a tenant:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.config.SimpleKafkaListenerEndpoint;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.stereotype.Service;

@Service
class DynamicOrderSubscriptions {

    private final KafkaListenerEndpointRegistry registry;
    private final ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory;
    private final OrderRecordHandler orderRecordHandler;

    DynamicOrderSubscriptions(
            KafkaListenerEndpointRegistry registry,
            ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory,
            OrderRecordHandler orderRecordHandler) {
        this.registry = registry;
        this.factory = factory;
        this.orderRecordHandler = orderRecordHandler;
    }

    public synchronized void registerTenant(String tenantId) {
        String endpointId = "tenant-orders-" + tenantId;
        String groupId = "orders-tenant-" + tenantId;

        if (registry.getListenerContainer(endpointId) != null) {
            throw new IllegalStateException(
                    "Endpoint already registered: " + endpointId);
        }

        SimpleKafkaListenerEndpoint<String, OrderCreated> endpoint =
                new SimpleKafkaListenerEndpoint<>();
        endpoint.setId(endpointId);
        endpoint.setGroupId(groupId);
        endpoint.setTopics("orders");
        endpoint.setMessageListener(
                (MessageListener<String, OrderCreated>) orderRecordHandler::handle);

        // true: start the container immediately after registration.
        registry.registerListenerContainer(endpoint, factory, true);
    }
}
```

`OrderRecordHandler` is the business service that receives records, for example:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;

interface OrderRecordHandler {
    void handle(ConsumerRecord<String, OrderCreated> record);
}
```

In this example, `tenantId` produces a distinct endpoint ID and group ID. The naming scheme is illustrative; the application should normalize and validate values before using them. `registerListenerContainer(endpoint, factory, true)` registers the endpoint in the registry and starts the container immediately. If registering before the application context starts its lifecycle, you can pass `false` so the container is started by the registry according to the context lifecycle.

To use the registry, the application must enable Spring Kafka's listener infrastructure. Spring Boot typically auto-configures this infrastructure when the appropriate Kafka dependencies are present; manually configured Spring applications can use `@EnableKafka` and declare the factory/registry accordingly.

## 4. Choosing Subscription by Topic, Pattern, or Partition

An endpoint can subscribe in several ways:

| Registration Style | API on Endpoint | When Appropriate |
| --- | --- | --- |
| One or more topics | `setTopics("orders", "payments")` | Known list of topics |
| Topic pattern | `setTopicPattern(pattern)` | Subscribing to topics matching a regex, e.g. `tenant-.*-events` |
| Specific partitions | `setTopicPartitions(...)` | Explicitly specifying topic-partitions and starting offsets |

Example using a topic pattern:

```java
endpoint.setTopicPattern(Pattern.compile("tenant-.*-orders"));
```

When using a pattern, the consumer can discover new matching topics on metadata refresh intervals. Constrain the pattern tightly enough so the listener does not accidentally subscribe to out-of-scope topics.

With `TopicPartitionOffset`, the application can specify partitions and offsets or relative starting positions according to the Spring Kafka API. This is an explicit assignment mode; do not simultaneously assume the consumer group divides partitions as in standard topic subscription. Check group management and offset reset configuration before using manual assignment.

Registering an endpoint does not mean the topic already exists. Provision topics, partitions, replication, and ACLs through infrastructure governance processes. Do not rely on broker auto-creation to dynamically create topics from user input.

## 5. Looking Up, Stopping, Restarting, and Unregistering a Container

After registration, the registry allows looking up the container by endpoint ID:

```java
import org.springframework.kafka.listener.MessageListenerContainer;

public void stopTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null) {
        container.stop();
    }
}

public void startTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null && !container.isRunning()) {
        container.start();
    }
}

public synchronized void unregisterTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null) {
        container.stop();
        registry.unregisterListenerContainer(endpointId);
    }
}
```

`stop()` stops the container while keeping it registered in the registry, so it can be `start()`ed again. `unregisterListenerContainer(id)` removes the registered container from the registry; to listen again afterward, you must register a new endpoint. Verify which APIs are available in your exact Spring Kafka version when upgrading the framework.

When stopping a container, account for in-flight records and the acknowledgment policy. Use the container's stop lifecycle so Spring Kafka completes the shutdown cleanly; do not close `KafkaConsumer` directly from another thread. For applications requiring responsive feedback, expose states like `STARTING`, `RUNNING`, `STOPPING`, and `STOPPED` rather than treating the stop/start call as an instantaneous state transition.

## 6. Endpoint ID and Group ID Must Be Managed Separately

The endpoint ID is the key for managing the container within the application context. It must be unique in the registry and stable so the application can look up or remove the right container. The group ID is the consumer's identity on the Kafka side, affecting partition assignment, committed offsets, and consumer restart behavior.

Two common models:

| Goal | Group ID | Outcome |
| --- | --- | --- |
| Multiple containers share load on the same subscription | Share one group ID | Kafka divides partitions among consumers in the group |
| Each tenant needs to receive all events independently | Separate group ID per tenant | Each group has its own offsets and receives its own copy of the record stream |

Do not generate a new group ID on every application restart if you want to resume from committed offsets. A group ID should represent a logical subscription with a clear lifecycle. If the group ID changes, the consumer starts at a different read position according to `auto.offset.reset` when no committed offset exists.

## 7. Avoiding Unbounded Container Creation

Dynamic containers are useful, yet each container carries overhead: consumer connection, poll loop, threads, heartbeats, metrics, and memory. A container with high concurrency spawns even more consumers. Creating a container per HTTP request or every time a user opens a screen can quickly multiply consumers and overload both the broker and the application.

Design a subscription manager with clear policies:

1. Validate the tenant, topic, and access permissions before registering.
2. Use deterministic endpoint IDs and check for duplicates before creating containers.
3. Limit subscription count and concurrency per tenant/application.
4. Persist subscription configuration durably if recovery after restart is required.
5. Stop and remove containers when subscriptions expire or tenants are disabled.
6. Monitor running container count, consumer count, lag, and startup errors.

The registry is an in-memory manager for a single application context; it is not a distributed configuration store. If the application restarts or runs multiple replicas, each replica has its own registry. To restore subscriptions after restart, store configurations in a database/config service and reload them on startup. If multiple replicas receive commands to create a subscription, use a coordination mechanism to avoid duplicates or unwanted replicas registering simultaneously.

## 8. Startup Registration vs. Runtime Registration

Not every case requires runtime registration:

- If the list of listeners is fixed, `@KafkaListener` keeps code readable and lets the framework manage lifecycle naturally.
- If the endpoint list is determined while configuring the application context, you can use `KafkaListenerEndpointRegistrar` via `KafkaListenerConfigurer` to register endpoints during the configuration phase.
- If subscriptions are created or removed while the application is running, use `KafkaListenerEndpointRegistry.registerListenerContainer()` and the container lifecycle APIs.

`KafkaListenerEndpointRegistrar` mainly serves endpoint registration during listener configuration. `KafkaListenerEndpointRegistry` is the management point for containers and supports runtime registration. Choosing the right mechanism avoids manual container management when annotations already meet the requirements.

## 9. Error Handling and Security Configuration

Dynamic containers use the error handler policy of their factory or corresponding endpoint configuration. Ensure listeners have proper retry/backoff and recoverer/DLT behavior; dynamic registration does not change Spring Kafka's error-handling principles.

Inputs used to construct endpoints must be controlled:

- Do not allow clients to pass arbitrary topics or regexes without an allowlist.
- Do not concatenate tenant IDs directly into group IDs without character sanitization and length limits.
- Check topic subscription permissions and data read permissions per tenant.
- Do not treat the group ID as a security boundary; access control must be enforced by broker ACLs and the application.
- Do not log credentials, sensitive payloads, or full consumer security configurations.

If an endpoint fails to start due to a missing topic, misconfigured ACL, deserializer error, or invalid group configuration, record the endpoint ID and root cause. You can expose a failed registration state so operations can retry after fixing the configuration.

## 10. Testing Dynamic Endpoints

Integration tests should verify lifecycle and actual Kafka behavior:

1. Register a new endpoint; verify the container appears in the registry and is started when `startImmediately=true`.
2. Send a record to the topic; verify the right handler receives it.
3. Register a second endpoint with the same group ID; verify consumers share partitions rather than each endpoint receiving all records.
4. Register two endpoints with distinct group IDs; verify each group can receive the full record stream with independent offsets.
5. Call stop then start; verify the container stops and resumes according to the configured offsets/group.
6. Unregister the endpoint; verify the container is no longer in the registry and stops polling.
7. Test duplicate endpoint IDs, invalid topics, missing ACLs, and startup failures; verify the application reports clear status.
8. Restart the application; verify subscriptions are recreated from durable configuration if required by business rules.

## 11. Implementation Checklist

- [ ] Chosen `@KafkaListener`, `KafkaListenerEndpointRegistrar`, or runtime registry according to when subscriptions are created.
- [ ] Endpoint ID is unique in the registry and distinct from the group ID.
- [ ] Endpoint has the required topic, topic pattern, or partition assignment.
- [ ] Container factory is configured with the right `ConsumerFactory`, deserializers, concurrency, acknowledgment, and error handler.
- [ ] `registerListenerContainer()` uses `startImmediately` appropriate for the lifecycle.
- [ ] Stop/start/unregister transitions have explicit state and clear handling of in-flight records.
- [ ] Group ID reflects the intended load-sharing or independent-stream model.
- [ ] Limits are enforced on container, consumer, and thread counts.
- [ ] Topics, ACLs, and tenants are validated before registration.
- [ ] Subscriptions that must survive restarts are persisted and restored from a durable source.
- [ ] Tested registration, delivery, group behavior, stop/start, and unregister.

`KafkaListenerEndpointRegistry` enables creating listener containers from endpoints while the application is running. When endpoint IDs, group IDs, topic subscriptions, and lifecycles are managed clearly, an application can support dynamic subscriptions while still leveraging Spring Kafka's consumer factory, container, acknowledgment, and error handling.

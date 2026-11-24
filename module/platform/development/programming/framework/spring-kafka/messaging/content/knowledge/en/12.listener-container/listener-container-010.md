# autoStartup and lifecycle

Spring Kafka creates a listener container for each endpoint declared with `@KafkaListener`. The container manages the consumer, the `poll()` loop, invoking the listener, and participating in the consumer group. By default, containers are started along with the Spring application context. The **`autoStartup`** property controls this automatic startup behavior; lifecycle APIs allow the application to explicitly start or stop containers when needed.

Lifecycle control is useful when an application needs to wait for dependencies to become ready, toggle consumers via feature flags, pause a processing stream during maintenance, or close consumers cleanly when shutting down.

## 1. Listener containers and autoStartup

When Spring processes `@KafkaListener`, the framework registers the endpoint and creates a listener container via `KafkaListenerEndpointRegistry`. The container manages the Kafka consumer and runs the listener on consumer threads.

`autoStartup` determines whether the container starts automatically during Spring's lifecycle:

- `true`: the container starts automatically when the application context starts.
- `false`: the container is still created and registered, but does not start automatically. The application can start it later using lifecycle APIs.

The listener container defaults to auto-starting. On the annotation, `autoStartup` is a String attribute to support placeholders or SpEL. If omitted, the container uses the default from the listener container factory.

An important point: `autoStartup=false` does not delete the endpoint or disable all Kafka usage in the application. It only prevents that specific listener container from starting automatically. Producers using `KafkaTemplate` or manually created consumers continue operating according to their own configuration.

## 2. Configuring autoStartup with Spring Boot

With Spring Boot auto-configuration, you can set the default for the listener container factory via `spring.kafka.listener.auto-startup`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
    listener:
      auto-startup: false
```

In the example, listener containers using the default factory will not start automatically. The application can explicitly start each container via the registry after verifying readiness conditions.

If most listeners should start automatically while one listener needs delayed startup, leave the default as `true` and override it on that listener's annotation. Conversely, if the default should stay stopped, selectively enable required listeners with `autoStartup="true"`.

## 3. Configuring autoStartup on @KafkaListener

The annotation supports the `autoStartup` attribute. The following example configures a listener not to start automatically:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-projection",
            autoStartup = "false"
    )
    public void onOrderEvent(OrderCreatedEvent event) {
        // Update projection from event.
    }
}
```

Here:

- `id="ordersListener"` is the listener container's ID, used to look up the container via the registry.
- `groupId="order-projection"` is the consumer group ID used to manage membership and committed offsets.
- `autoStartup="false"` keeps the container stopped when the context starts.

`id` and `groupId` serve two different purposes. Do not use the group ID to look up a container in the registry; use the listener `id`.

You can drive the attribute via external configuration:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-projection",
        autoStartup = "${app.kafka.listeners.orders.auto-startup:true}"
)
public void onOrderEvent(OrderCreatedEvent event) {
    // Process event.
}
```

And in `application.yml`:

```yaml
app:
  kafka:
    listeners:
      orders:
        auto-startup: false
```

Placeholders let you enable or disable listeners per profile or environment without changing source code. The default after the `:` is `true` if the property is not declared.

## 4. Setting the default on the listener container factory

If not using Spring Boot auto-configuration or when a dedicated factory is needed, you can call `setAutoStartup(false)` on `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setAutoStartup(false);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Specify this factory in the annotation:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "ordersListenerFactory"
)
public void onOrderEvent(OrderCreatedEvent event) {
    // Process event.
}
```

When `autoStartup` is not specified on the annotation, the endpoint uses the value from the factory. If the annotation declares `autoStartup`, the endpoint-level value overrides that factory default.

## 5. Managing containers via KafkaListenerEndpointRegistry

Containers created from `@KafkaListener` are managed by `KafkaListenerEndpointRegistry`. They are not standalone beans retrieved with `applicationContext.getBean(...)` by container class. Inject the registry and look up containers by the annotation's `id`.

Example listener control service:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException("ordersListener not found");
        }

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
```

`getListenerContainer(id)` returns the container if the ID exists, or `null` if not found. Check the result before calling lifecycle methods to avoid errors when an ID changes or an endpoint has not been registered.

The registry also exposes registered IDs and containers, which is useful for displaying status or controlling multiple listeners. Only start/stop containers that the application actually intends to manage.

## 6. Starting listeners after the application is ready

A common scenario is allowing consumers to begin reading only after the application has initialized its database, cache, or other dependencies. You can set `autoStartup=false`, then start the listener when Spring publishes `ApplicationReadyEvent`:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class KafkaListenerStartup {

    private final KafkaListenerLifecycleService lifecycleService;

    public KafkaListenerStartup(KafkaListenerLifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        lifecycleService.startOrdersListener();
    }
}
```

`ApplicationReadyEvent` is published once Spring Boot completes application startup. This fits when the listener must wait for all startup steps and application runners to finish. If it only needs to wait on one specific dependency, use that dependency's own readiness or lifecycle hook rather than delaying every listener until the end of startup.

Do not set `autoStartup=false` and forget to start the listener. While stopped, the application may still report HTTP healthy even though the consumer group receives no records. Include critical listener state in appropriate health/readiness checks or monitoring.

## 7. Distinguishing start/stop from pause/resume

Lifecycle operations and pause/resume serve two different needs:

| Operation | Behavior | Consumer group |
|---|---|---|
| `start()` | Starts the container and consumer threads. | Consumer joins group and receives partition assignments. |
| `stop()` | Stops the container, closes the consumer, and leaves the group. | Partitions may rebalance to other members. |
| `pause()` | Temporarily stops receiving new records from partitions via consumer pause; container maintains required poll loop. | Consumer keeps its membership/assignment while paused. |
| `resume()` | Resumes receiving records after a pause. | Retains current assignment if the group has no other changes. |

If you need brief maintenance or load throttling while retaining group membership, pause/resume is usually better than stop/start. If you want to release the consumer and let another member take over partitions, use stop.

Pause does not necessarily stop processing records already in flight at the moment it is called. Design active listener executions to complete safely and verify the pause/resume API of your Spring Kafka version.

## 8. Graceful shutdown and Spring's lifecycle

Listener containers participate in Spring's lifecycle via `KafkaListenerEndpointRegistry` and `SmartLifecycle`. When the application context closes normally, the registry stops the containers it manages so consumers stop polling and release resources.

During shutdown:

1. The application stops accepting new work per the container's stop sequence.
2. In-flight listeners are given an opportunity to finish according to container shutdown configuration and wait timeout.
3. Consumers close and leave the group; the coordinator may rebalance partitions to remaining members.
4. Producers and other Spring resources continue closing in their lifecycle order.

Avoid calling `System.exit()` or killing the process immediately after requesting a stop if you want graceful shutdown. Let the Spring context close normally and configure shutdown timeouts aligned with the listener's maximum processing time. If the listener calls external systems, ensure side effects are idempotent and handle redelivery after an abrupt consumer stop.

Synchronous `stop()` can wait for the container to stop; lifecycle APIs also support a callback when stopping finishes. In orchestration or admin endpoints, avoid blocking request threads too long if shutdown takes time, and report stop completion only once the container has actually stopped.

## 9. Checking listener status

You can inspect container state via the registry:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    boolean running = container.isRunning();
    // Record status for health indicator or monitoring.
}
```

The registry can provide `getListenerContainerIds()`, `getListenerContainers()`, and `getAllListenerContainers()` to inspect registered listeners. Note that `isRunning()` only indicates the container's lifecycle state; it does not confirm the consumer holds partition assignments, has zero lag, or is processing successfully. For a full health assessment, combine consumer group state, lag, listener errors, and dependency health.

## 10. Testing autoStartup and lifecycle

In integration tests, explicitly verify two scenarios:

- With `autoStartup=false`, the container is registered but not running right after context initialization.
- After calling `start()`, the consumer begins receiving records; after `stop()`, the consumer stops per lifecycle rules.

Example checking container state:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

import static org.assertj.core.api.Assertions.assertThat;

class ListenerLifecycleTest {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void startsAndStopsListenerOnDemand() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();
        assertThat(container.isRunning()).isTrue();

        container.stop();
        assertThat(container.isRunning()).isFalse();
    }
}
```

This is a skeleton example; a complete test needs a Spring context configured with `autoStartup=false`, a test broker/Embedded Kafka setup, and confirmation that state transitions finish before asserting if startup is asynchronous. Add a test that sends a record after starting to confirm the listener actually receives data.

## 11. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Listener receives no records after app starts | `autoStartup=false` and `start()` was never called. | Use the registry to start the container or enable auto-startup. |
| Container not found in registry | Mistakenly used group ID instead of listener ID, or ID wasn't declared as expected. | Set an explicit `id` on `@KafkaListener` and look up by that ID. |
| One listener still auto-starts even with factory `autoStartup=false` | Annotation overrode it with `autoStartup="true"`. | Check endpoint-level configuration and placeholders. |
| Changing property does not toggle a running listener | Placeholders resolve when the endpoint/container is created; editing config files does not update lifecycle automatically. | Use actuator/management flows or a dedicated dynamic config mechanism. |
| Calling `stop()` triggers partition reassignment to another consumer | Consumer left the group and the coordinator rebalanced. | Normal behavior; ensure safe processing/commits before stopping. |
| `isRunning()` is true but no records arrive | Container may lack partition assignments, topic has no data, or consumer has lag/other errors. | Check assignments, group state, lag, subscription, and listener logs. |
| Shutdown drags out | Listener is taking too long or external dependency is unresponsive. | Set reasonable timeouts, bound I/O duration, and support safe cancellation/completion. |

## 12. Key takeaways

- `autoStartup` controls whether a listener container starts automatically with the Spring context; the default is typically `true`.
- `spring.kafka.listener.auto-startup` sets the default for factories configured by Spring Boot.
- `@KafkaListener(autoStartup="...")` can override the factory default and supports property placeholders/SpEL.
- Assign a stable `id` to listeners to look up containers via `KafkaListenerEndpointRegistry`; listener ID is distinct from consumer group ID.
- Use `start()`/`stop()` for lifecycle management; use `pause()`/`resume()` when temporarily halting record delivery while keeping consumer membership.
- Spring manages listener containers via the registry and stops them during application context lifecycle shutdown.
- `isRunning()` does not replace checking partition assignments, lag, and processing errors.
- When disabling auto-startup, ensure an explicit start procedure and tests so listeners are not left idle unintentionally.

When designing listener lifecycles, determine when consumers are permitted to join the group, who is responsible for starting/stopping them, and how the system verifies operational health. Clear `autoStartup` settings combined with the registry, readiness checks, and graceful shutdown help Kafka streams start at the right time and stop safely.

## References

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Boot — Kafka Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#application-properties.integration.spring.kafka.listener.auto-startup)

# JmsListenerEndpointRegistry and Controlling Listener Lifecycle

## Objectives

In Spring JMS, each method annotated with `@JmsListener` is turned into a listener endpoint and served by a `MessageListenerContainer`. Spring creates the container through `JmsListenerContainerFactory`, while `JmsListenerEndpointRegistry` holds those containers and controls their lifecycle.

The registry helps the application look up listeners by ID, list listeners, start or stop an individual listener, control all listeners, and register new endpoints when needed.

After this lesson, you can:

- Explain the relationship among `@JmsListener`, the endpoint, the listener container, and the registry.
- Set a stable ID to manage each listener.
- Look up a container with `getListenerContainer()` and list them with `getListenerContainerIds()`.
- Start or stop one listener or all listeners.
- Understand the role of `SmartLifecycle` when the ApplicationContext starts and closes.
- Configure auto-start for a listener container.
- Register endpoints in code and understand the limits of the registry.

## 1. Components in the Listener Mechanism

An endpoint describes where to receive messages and how to invoke the processing code. When Spring detects `@JmsListener`, the annotation infrastructure creates the corresponding endpoint. A `JmsListenerContainerFactory` uses that endpoint to create a `MessageListenerContainer`.

Main components:

| Component | Role |
|---|---|
| `@EnableJms` | Enables the infrastructure that processes `@JmsListener` annotations |
| `@JmsListener` | Declares the destination and the message-processing method |
| `JmsListenerEndpoint` | Describes a JMS endpoint |
| `JmsListenerContainerFactory` | Creates and configures the listener container |
| `MessageListenerContainer` | Manages the consumer, session, connection, and message receiving |
| `JmsListenerEndpointRegistry` | Stores and manages the lifecycle of containers created for endpoints |

Initialization flow:

~~~text
@EnableJms
    |
    v
JmsListenerAnnotationBeanPostProcessor
    |
    v
Detect @JmsListener method
    |
    v
JmsListenerEndpoint
    |
    v
JmsListenerContainerFactory
    |
    v
MessageListenerContainer
    |
    v
JmsListenerEndpointRegistry manages the container
~~~

Each listener method is served by a container created from the corresponding factory. The registry manages these containers within the lifecycle of the Spring ApplicationContext.

**Point to remember:** containers managed by the registry are not separate beans in the ApplicationContext and cannot be injected directly by bean name like regular beans. To access them for management, use the registry. Containers declared manually as separate beans are a different case and do not automatically appear in the registry.

## 2. Enabling Annotation Listeners and Creating Endpoints

Add `@EnableJms` to the configuration so Spring registers the `@JmsListener` processing infrastructure.

Example factory configuration:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }
}
~~~

Spring by default looks for a factory with the bean name `jmsListenerContainerFactory` if the endpoint does not specify its own factory. A specific factory can be set in the `containerFactory` attribute of `@JmsListener`.

Listener declaration:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
        id = "ordersListener",
        destination = "orders.queue"
    )
    public void handleOrder(String orderId) {
        System.out.println("Received order: " + orderId);
    }
}
~~~

When the ApplicationContext initializes, Spring detects the `handleOrder` method and creates an endpoint and a container for that endpoint. The registry stores the container under the ID `ordersListener`.

The Java examples in this lesson are integration snippets for a Spring JMS application; they require the Spring JMS dependency, a Jakarta Messaging provider, and a configured `ConnectionFactory` in the application.

## 3. Why Set an Explicit ID?

The `id` attribute of `@JmsListener` is the identifier of the container managing the endpoint.

~~~java
@JmsListener(
    id = "billingListener",
    destination = "billing.queue"
)
public void handleBilling(String message) {
    // Process the billing message.
}
~~~

If `id` is omitted, Spring generates an ID automatically. That still lets the listener work, but makes it harder to manage in code because the application lacks a stable name to look up.

Set an explicit ID when you need to:

- Pause or start a listener based on business requirements.
- Display listener status on an administration page.
- Control listeners by tenant or functional group.
- Write integration tests for each endpoint.
- Coordinate listeners by dependency state, such as only receiving messages after configuration data is ready.

The ID must be unique in the registry. If two endpoints are registered with the same ID, Spring reports an `IllegalStateException`. Name by function and keep it stable across restarts.

In Spring Framework 7.0.10, `@JmsListener` has the attributes `id`, `destination`, `containerFactory`, `concurrency`, `selector`, and `subscription`; the annotation does not have an `autoStartup` attribute. Container auto-start is configured through the listener container factory.

## 4. Accessing Containers via JmsListenerEndpointRegistry

The registry is typically injected like this:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class ListenerMonitor {

    private final JmsListenerEndpointRegistry registry;

    public ListenerMonitor(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }
}
~~~

Important lookup methods:

| Method | Result |
|---|---|
| `getListenerContainer(id)` | The container with the corresponding ID; returns `null` if it does not exist |
| `getListenerContainerIds()` | The set of IDs of the containers managed by the registry |
| `getListenerContainers()` | The collection of containers managed by the registry |
| `isRunning()` | The running state of the registry according to the managed containers |

Example of listing listeners. This is a method fragment placed inside a listener-management class:

~~~java
import java.util.Set;

public Set<String> getListenerIds() {
    return registry.getListenerContainerIds();
}
~~~

Example of retrieving one container:

~~~java
import org.springframework.jms.listener.MessageListenerContainer;

public MessageListenerContainer findListener(String id) {
    MessageListenerContainer container = registry.getListenerContainer(id);

    if (container == null) {
        throw new IllegalArgumentException("Unknown JMS listener: " + id);
    }

    return container;
}
~~~

The collection returned by `getListenerContainers()` and the ID set are read-only views, not places to add or remove endpoints. Register endpoints using the registry's registration API or the JMS configuration infrastructure.

## 5. Controlling One Listener

`MessageListenerContainer` implements `SmartLifecycle`, so the container has the operations `start()`, `stop()`, `isRunning()`, and `getPhase()`.

You can control a specific listener by ID:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerControl {

    private final JmsListenerEndpointRegistry registry;

    public OrderListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container = requireContainer("ordersListener");

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container = requireContainer("ordersListener");

        if (container.isRunning()) {
            container.stop();
        }
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container = registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException("Unknown JMS listener: " + id);
        }

        return container;
    }
}
~~~

This is an integration class in a Spring application, requiring a listener bean with ID `ordersListener` and configured JMS infrastructure. The methods can be called from an admin service, a scheduler, or an internal orchestration flow.

When `stop()` is called, the container stops receiving messages. The endpoint remains in the registry, so `start()` can be called to run it again. Stopping the consumer does not delete the Queue/Topic on the broker and does not automatically delete pending messages. Messages continue to follow the provider's retention, subscription, and delivery policies.

## 6. Controlling All Listeners

The registry also implements `SmartLifecycle` and provides `start()` and `stop()` to control all containers it manages.

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class AllListenersControl {

    private final JmsListenerEndpointRegistry registry;

    public AllListenersControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseAllListeners() {
        registry.stop();
    }

    public void resumeAllListeners() {
        registry.start();
    }
}
~~~

The two operations above have registry-wide scope:

- `registry.stop()` stops all containers managed by the registry.
- `registry.start()` sends a start signal to all containers managed by the registry. When called after the ApplicationContext has refreshed, registered containers are started.

If you only want to stop one listener, retrieve the container by ID and call `stop()` on that container. Do not use `registry.stop()` to pause an individual endpoint because other listeners will also stop.

## 7. SmartLifecycle and the ApplicationContext Lifecycle

`JmsListenerEndpointRegistry` implements `SmartLifecycle`, a Spring lifecycle contract. As a result, Spring can start and stop the registry according to the lifecycle of the ApplicationContext.

Important methods:

- `start()`: starts the managed containers.
- `stop()`: stops the managed containers synchronously.
- `stop(Runnable callback)`: stops the containers and invokes the callback after the containers have stopped.
- `isRunning()`: indicates whether the registry is currently running.
- `isAutoStartup()`: indicates whether the lifecycle component is automatically started by Spring when the context refreshes.
- `getPhase()`: returns the phase used to order the lifecycle sequence.

Spring uses the phase to coordinate the start and stop order among lifecycle components. When configuring a custom phase for listener containers, containers managed by the registry should use a consistent phase. The registry takes the phase from a container with a custom phase; differing custom values across factories can cause a phase mismatch error.

During ApplicationContext closing, Spring invokes lifecycle stop before destroying beans. The registry stops the managed containers; when the registry is destroyed, it also destroys containers that implement `DisposableBean`. Applications normally do not need to call `destroy()` themselves.

### 7.1. Asynchronous Stopping

`stop(Runnable callback)` is useful when containers need time to finish stopping. The registry sends stop requests to each container and calls the callback after all stop callbacks have completed.

Example:

~~~java
registry.stop(() -> {
    System.out.println("All JMS listener containers have stopped");
});
~~~

The callback only runs after the registry receives all stop signals from the containers. This approach suits shutdown procedures that need to coordinate many components.

## 8. Configuring Auto-Start of Listener Containers

The factory controls whether the container starts automatically during ApplicationContext refresh. Example disabling auto-start:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setAutoStartup(false);
    return factory;
}
~~~

With this configuration, the listener container is created and registered, but does not automatically receive messages during the context's auto-startup phase. The application can wait for a readiness condition and then start the listener.

Example starting after a dependency is ready:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class StartupCoordinator {

    private final JmsListenerEndpointRegistry registry;

    public StartupCoordinator(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void onDependenciesReady() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException("ordersListener is not registered");
        }

        container.start();
    }
}
~~~

You need to distinguish two configuration layers:

- `setAutoStartup(false)` on the factory controls auto-start of containers created by the factory.
- `registry.start()` is a registry-wide lifecycle operation; it starts the managed containers when called explicitly after the context has refreshed.

In Spring Framework 7.0.10, `@JmsListener` does not declare `autoStartup`. Configure this property on `JmsListenerContainerFactory` or control the container directly after looking it up by ID.

## 9. Registering Endpoints in Code

Besides endpoints discovered from `@JmsListener`, Spring lets you register a `JmsListenerEndpoint` in code. `SimpleJmsListenerEndpoint` is a simple implementation that takes a JMS `MessageListener`.

Example:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.stereotype.Component;

@Component
public class DynamicListenerRegistrar {

    private final JmsListenerEndpointRegistry registry;
    private final JmsListenerContainerFactory<?> listenerFactory;

    public DynamicListenerRegistrar(
            JmsListenerEndpointRegistry registry,
            @Qualifier("jmsListenerContainerFactory")
            JmsListenerContainerFactory<?> listenerFactory) {
        this.registry = registry;
        this.listenerFactory = listenerFactory;
    }

    public void register(String endpointId, String destination) {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(endpointId);
        endpoint.setDestination(destination);
        endpoint.setMessageListener(
            message -> System.out.println("Received a dynamic JMS message")
        );

        registry.registerListenerContainer(endpoint, listenerFactory, true);
    }
}
~~~

This is an integration example; the application must supply a suitable factory and a valid destination. When called after the context has started, the `startImmediately=true` parameter asks the registry to start the new container immediately if needed.

There are two overloads:

~~~java
registry.registerListenerContainer(endpoint, listenerFactory);
registry.registerListenerContainer(endpoint, listenerFactory, true);
~~~

The overload without the boolean parameter corresponds to registering without requesting immediate start. When you need the endpoint to be active right after runtime registration, use the overload with `true`.

The endpoint needs an ID different from existing endpoints. If the ID is duplicated, the registry throws `IllegalStateException`. The registry API provides registration and container lookup; there is no corresponding public API to unregister an endpoint. Therefore, design the lifecycle of dynamic endpoints clearly before creating many endpoints per tenant or per runtime request.

### 9.1. Registering Endpoints During the Configuration Phase

If endpoints are known right when the application starts, you can use `JmsListenerConfigurer` and `JmsListenerEndpointRegistrar` to register endpoints during the configuration phase:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class ProgrammaticJmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditListener");
        endpoint.setDestination("audit.queue");
        endpoint.setMessageListener(
            message -> System.out.println("Audit message received")
        );

        registrar.registerEndpoint(endpoint);
    }
}
~~~

The registrar is used during the endpoint-registration phase of configuration. The registry is used at runtime to access and control containers that have already been created. The two objects have related but different roles.

## 10. Which Containers Does the Registry Manage?

The registry manages containers created from endpoints registered with the JMS listener infrastructure, including endpoints discovered from `@JmsListener` and endpoints registered via the endpoint registrar mechanism or the registry's registration API.

Containers declared manually as separate beans do not automatically belong to the registry:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
DefaultMessageListenerContainer manualListenerContainer(
        ConnectionFactory connectionFactory) {
    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("manual.queue");
    container.setMessageListener(message -> {
        System.out.println("Manual container received a message");
    });
    return container;
}
~~~

This container is managed as a separate Spring bean. The application can inject the bean directly and control its lifecycle through that bean. `registry.getListenerContainers()` only returns containers managed by the registry.

## 11. Coordinating Listeners by Application State

You can use the registry to control listeners according to business state or infrastructure state:

- Only receive messages after caches or reference data have finished loading.
- Pause a group of consumers during maintenance.
- Restart listeners after the broker or dependent services recover.
- Run some listeners in maintenance mode while other listeners continue operating.
- Expose container IDs and state to internal monitoring tools.

Example workflow:

~~~text
ApplicationContext starts
        |
        v
Listeners are registered
        |
        v
Check dependencies and configuration
        |
        +---- Not ready -------> Keep listener in stopped state
        |
        v
Dependencies ready
        |
        v
registry.getListenerContainer("ordersListener")
        |
        v
container.start()
        |
        v
Listener receives and processes messages
        |
        v
Maintenance or shutdown
        |
        v
container.stop() or registry.stop()
~~~

When stopping a listener, account for in-flight messages and the broker's redelivery policy. If the listener uses transactions or acknowledgement, the container and provider configuration determine how messages being delivered at stop time are handled.

## 12. Common Mistakes and How to Handle Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| `getListenerContainer(id)` returns `null` | Wrong ID, endpoint not registered, or factory has not created the container | Check IDs in `getListenerContainerIds()` and annotation configuration |
| Cannot find a container bean to inject | Containers managed by the registry are not separate beans in the context | Inject `JmsListenerEndpointRegistry` and look up by ID |
| Calling `registry.stop()` stops every listener | The method controls the whole registry | Look up the container by ID and call `stop()` on that container |
| Listener does not receive messages automatically after startup | Factory sets `autoStartup=false` or container has not been started | Check the factory and call `container.start()` when conditions are ready |
| Two endpoints have the same ID | Duplicate ID in the registry | Assign a unique ID to each endpoint |
| Dynamic listener does not run immediately | Registered with the overload that does not request immediate start | Use `registerListenerContainer(endpoint, factory, true)` or start the container proactively |
| Manual listener does not appear in the registry | Container is declared as a separate bean | Manage the bean directly or switch to endpoint registration |
| Application closes but listeners do not stop in the right order | Lifecycle phase or stop callback has not been coordinated | Check the phase and use `stop(Runnable)` when asynchronous stopping is needed |
| Listener receives duplicate messages after restart | Messages were redelivered due to acknowledgement/transaction | Design an idempotent consumer and check listener transactions |
| Phase mismatch when registering multiple containers | Factories use inconsistent custom phases | Use a consistent phase for containers in the same registry |

## 13. Safe Operation Principles

- Set an explicit `id` for listeners that need to be managed at runtime.
- Inject the registry as `JmsListenerEndpointRegistry`; do not try to inject a container created by the registry as a separate bean.
- Use `getListenerContainer(id)` and handle the case where the container is not found.
- Use `container.start()` or `container.stop()` when controlling only one listener.
- Use `registry.start()` and `registry.stop()` when you need to control all listeners managed by the registry.
- Set `setAutoStartup(false)` on the factory if a listener must wait for a readiness condition before receiving messages.
- Use `registerListenerContainer(endpoint, factory, true)` when registering a new endpoint that needs to run right away.
- Ensure the dynamic endpoint's ID is unique.
- Distinguish the endpoint registrar used at configuration time from the endpoint registry used at runtime.
- Set a consistent lifecycle phase if you need to control start/stop order.
- Design acknowledgement, transactions, and idempotency to handle messages in flight when a listener stops or restarts.
- Monitor listener ID, running state, connection errors, processed message count, and redelivery count.

## 14. Deployment Checklist

- [ ] Enabled `@EnableJms` if using annotation listeners.
- [ ] Declared an appropriate `JmsListenerContainerFactory`.
- [ ] Every listener that needs management has a stable and unique ID.
- [ ] Understood that containers created by the registry are not separate beans in the ApplicationContext.
- [ ] Used `getListenerContainerIds()` or `getListenerContainer(id)` for lookup.
- [ ] Chose between controlling one container or the entire registry.
- [ ] Configured auto-start on the factory to match the application startup sequence.
- [ ] Handled the case where the ID does not exist.
- [ ] If registering endpoints at runtime, assigned a unique ID and chose `startImmediately` according to requirements.
- [ ] Checked lifecycle phases when there are multiple custom factories.
- [ ] Coordinated stop, transactions, and acknowledgement during shutdown.
- [ ] Tested start, stop, restart, context shutdown, and dynamic registration.

## 15. References

- [Spring Framework — JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [Spring Framework — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework — JmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpoint.html)
- [Spring Framework — MessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/MessageListenerContainer.html)
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework — SimpleJmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)

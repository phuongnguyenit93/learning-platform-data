# Event Publishing and Dispatching Flow

In the Spring Framework, an event is a notification describing something that has happened in the application. The event-publishing component only needs to know the `ApplicationEventPublisher` contract; listeners registered with an interest in the corresponding event type will receive and handle the notification. This mechanism decouples where an event originates from the tasks that react to it.

For example, `OrderService` completes creating an order and then publishes `OrderCreatedEvent`. Components such as sending an email, writing an audit log, or updating statistics can listen to that event without `OrderService` needing to call each component directly.

After this lesson, you will be able to:

- Describe the path of an event from a publisher to listeners.
- Distinguish between `ApplicationEventPublisher`, `ApplicationEventMulticaster`, `ApplicationListener`, and `@EventListener`.
- Explain how Spring selects matching listeners and its default synchronous behavior.
- Recognize when asynchronous processing or binding a listener to a transaction is needed.

## 1. Components in the Event Model

| Component | Role |
|---|---|
| `ApplicationEventPublisher` | Contract for publishing an event into the Spring application context. |
| `ApplicationContext` | Provides `ApplicationEventPublisher` and manages the lifecycle of listener beans. |
| Event object | Carries information about what happened, such as order ID and creation timestamp. |
| `ApplicationEventMulticaster` | Coordinates dispatching events to matching listeners. |
| `ApplicationListener<E>` | Interface-based listener for receiving events of type `E`. |
| `@EventListener` | Marks a method on a Spring bean as a listener. |

### Publisher

`ApplicationEventPublisher` is the entry point for publishing events. Typically, a service receives the publisher via constructor injection:

~~~java
public class OrderService {
    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

`ApplicationContext` provides the publisher contract, so the service does not need to look up or invoke each listener itself. Injecting this interface also makes the service easier to test.

An event can be published using:

~~~java
publisher.publishEvent(event);
~~~

The `publishEvent(Object event)` method allows publishing any object. If the object does not already extend `ApplicationEvent`, Spring wraps it in a `PayloadApplicationEvent` before dispatching. This mechanism supports POJO or Java record events without requiring a subclass of a framework class.

### Event object

An event should carry the data needed for listeners to understand what happened. For POJO events, an immutable record can be used:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

A legacy-style event can extend `ApplicationEvent`:

~~~java
public final class LegacyOrderCreatedEvent extends ApplicationEvent {
    private final String orderId;

    public LegacyOrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

`ApplicationEvent` stores `source`, which is the object that originated the event. With POJO events, put the necessary information directly in the payload. Prefer immutable and sufficient data; avoid putting a large mutable entity into an event if listeners only need a few fields.

### Listener

There are two common ways to register a listener:

- Implement `ApplicationListener<E>` and define `onApplicationEvent(E event)`.
- Annotate a method in a Spring bean with `@EventListener`.

Example using the annotation:

~~~java
@Component
public class OrderCreatedListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }
}
~~~

The bean must be managed by Spring for the method to be detected. During application context initialization, Spring finds methods annotated with `@EventListener` and registers them into the event dispatch mechanism. One bean can have multiple listener methods; multiple beans can also listen to the same event type.

Implementing the interface remains useful when you want to represent a listener as a dedicated bean or need an explicit type contract:

~~~java
public class AuditListener implements ApplicationListener<OrderCreatedEvent> {
    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Record the order ID in the audit log.
    }
}
~~~

## 2. Event Publishing and Dispatching Flow

When a service calls `publishEvent(event)`, Spring executes the following high-level flow:

1. **Create the event:** The business component creates an object containing data describing the event, such as `OrderCreatedEvent("ORD-1001")`.
2. **Publish the event:** The service calls `ApplicationEventPublisher.publishEvent(event)`. The service does not need to know how many listeners are registered.
3. **Normalize the event:** If the object is already an `ApplicationEvent`, Spring uses it directly. If it is a regular object, Spring wraps it in a `PayloadApplicationEvent`.
4. **Pass to the multicaster:** The application context forwards the event to `ApplicationEventMulticaster` for dispatching.
5. **Find matching listeners:** The multicaster selects listeners with compatible event types. A listener for a superclass or interface can receive events of a matching subclass; Spring also supports resolving generic listener types.
6. **Invoke listeners:** Each matching listener is invoked according to the configured execution model. With the default configuration, listeners run synchronously on the event-publishing thread.
7. **Propagate to parent context:** If the current context has a parent context, the event is forwarded to the parent context so listeners there can also receive matching events.

Simplified diagram:

~~~mermaid
flowchart TD
    A["Service / Publisher"] --> B["publishEvent(event)"]
    B --> C["ApplicationContext"]
    C --> D["Normalize event if needed"]
    D --> E["ApplicationEventMulticaster"]
    E --> F{"Find listeners by event type"}
    F -->|Match| G["Listener A"]
    F -->|Match| H["Listener B"]
    F -->|No listener| I["No listener handles it"]
    G --> J["Dispatch complete"]
    H --> J
~~~

An event can be delivered to multiple listeners. Listeners are selected based on the event type and registration conditions; Spring does not send every event to every bean in the context.

### Role of ApplicationEventMulticaster

`ApplicationEventMulticaster` is the component that coordinates listener invocation. In a typical application context, Spring uses `SimpleApplicationEventMulticaster` by default if the application does not provide its own multicaster bean named `applicationEventMulticaster`.

The multicaster is responsible for retrieving the list of matching listeners and invoking them. It does not replace listener business logic, store event history, or automatically provide a durable retry mechanism.

## 3. Runnable Example with Spring Framework

The example below uses Java 17 and Spring Context 6.2.0. The application creates a context, registers a service and a listener, and then publishes an event when placing an order.

Directory structure:

~~~text
spring-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ApplicationEventsDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class).placeOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    record OrderCreatedEvent(String orderId) {}

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void placeOrder(String orderId) {
            System.out.println("Saving order " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(orderId));
            System.out.println("Publisher continues");
        }
    }

    static class OrderCreatedListener {

        @EventListener
        public void onOrderCreated(OrderCreatedEvent event) {
            System.out.println("Listener received: " + event.orderId());
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Stdout result:

~~~text
Saving order ORD-1001
Listener received: ORD-1001
Publisher continues
~~~

The line `Listener received` appears before `Publisher continues` because the listener runs synchronously under the default configuration. When `publishEvent` finishes, the synchronous listener has already completed before the service executes the next statement.

The example uses a POJO record as the event, so there is no need to extend `ApplicationEvent`. `OrderService` only knows the publisher and the event type; it does not depend on `OrderCreatedListener`. You can add listeners to send emails or write audit logs without modifying the service's event-publishing flow.

## 4. Synchronous, Ordering, and Asynchronous Execution

### Synchronous by Default

`SimpleApplicationEventMulticaster` invokes listeners directly on the thread publishing the event if no executor is configured. This has several consequences:

- `publishEvent` typically returns only after synchronous listeners complete.
- Long-running listeners prolong the processing time of the publisher.
- An exception from a listener can propagate back to the caller. With the default configuration having no `ErrorHandler`, an exception can stop the dispatch cycle before subsequent listeners are invoked.

Therefore, synchronous listeners should perform short, predictable tasks and handle errors appropriately for the business logic.

### Listener Ordering

You can use `@Order` or the `Ordered` interface to specify listener order. Smaller order values have higher priority:

~~~java
@EventListener
@Order(1)
public void updateInventory(OrderCreatedEvent event) {
    // Process first.
}

@EventListener
@Order(2)
public void writeAuditLog(OrderCreatedEvent event) {
    // Process later.
}
~~~

This ordering is useful when synchronous listeners need to run in a deterministic sequence. If listeners run asynchronously, the order in which they are scheduled does not guarantee completion order; tasks may finish at different times.

### Asynchronous Execution

If a listener performs a slow task such as sending an email or calling an external service, it can be configured to run asynchronously. A common approach is to enable async processing and annotate the listener with `@Async`:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}

@Component
class AsyncOrderListener {

    @Async
    @EventListener
    public void sendConfirmation(OrderCreatedEvent event) {
        // Send email or perform time-consuming task.
    }
}
~~~

You must enable `@EnableAsync` in the Spring configuration and ensure the listener is a Spring bean. You can configure a suitable executor to control the thread pool. Another option is to provide a custom `SimpleApplicationEventMulticaster` with a task executor to dispatch listeners through that executor.

When running asynchronously:

- The publisher can continue before the listener finishes.
- You should not rely on the completion order of listeners.
- Exceptions occurring in the async processing thread do not propagate back to the thread that called `publishEvent` as in the synchronous case.
- You need to manage the executor, queue limits, logging, and error handling to avoid overload or loss of observability.

Only enable async when business requirements allow decoupling processing from the event-publishing flow. If the task must finish before returning a result to the caller, keep processing synchronous or use an explicit result-coordination mechanism.

## 5. Events and Transactions

A standard `@EventListener` is invoked at the moment the event is published. If the publisher publishes an event inside a transaction, a synchronous listener can still run before the transaction commits. If the transaction rolls back afterward, side effects performed by the listener are not automatically undone.

When processing needs to follow the transaction lifecycle, use `@TransactionalEventListener`. For example:

~~~java
@Component
class OrderAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCommitted(OrderCreatedEvent event) {
        // Execute only after the transaction commits successfully.
    }
}
~~~

`AFTER_COMMIT` is the default phase of `@TransactionalEventListener`. This type of listener requires an active transaction at the time the event is published; if there is no transaction, the listener is not invoked by default unless `fallbackExecution = true` is enabled.

Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Choose the phase based on when the business logic needs to react. This annotation belongs to Spring transaction support, so the application must configure the corresponding transaction infrastructure and dependencies.

Note: `@TransactionalEventListener` does not turn an event into a durable message. If the process stops unexpectedly or messages need to be sent across multiple services, consider a transactional outbox or an appropriate message broker.

## 6. Parent and Child Contexts

In a hierarchical application context structure, events published from a child context can be forwarded up to the parent context. Therefore, listeners in the parent context can receive events published by the child context if the event type matches.

The reverse does not happen automatically: events published in the parent context are not dispatched down to child contexts. When designing an application with multiple contexts, identify where listeners are registered to avoid misunderstanding the event reception scope.

## 7. Common Mistakes

| Mistake or Misconception | Consequence | Resolution |
|---|---|---|
| Listener is not a Spring bean | Method with `@EventListener` is not registered. | Register the bean via component scanning or `@Bean`. |
| Listener parameter type is incompatible with the event | Listener is not selected to receive the event. | Check the exact event type, superclass, and generic type. |
| Assuming publishing an event saves history | Listeners registered later do not receive past events. | Use persistence or a message broker if storage and replay are needed. |
| Assuming all listeners always run asynchronously | Slow tasks still block the publisher under the default configuration. | Configure `@Async` or a task executor when appropriate. |
| Using an async listener but expecting exceptions to propagate to the publisher | The publisher does not receive exceptions from the async processing thread. | Set up error handling and logging for async tasks. |
| Publishing an event in a transaction and triggering side effects immediately | Side effects may occur even if the transaction later rolls back. | Use `@TransactionalEventListener` with the appropriate phase. |
| Sharing a mutable object across multiple listeners | Listeners may observe data modified by another listener. | Prefer immutable events containing only the necessary data. |
| Creating an infinite event loop | A listener publishes another event that loops back to itself. | Define clear termination conditions and avoid cyclic dependencies between listeners. |

## 8. When to Use Application Events?

Application events are suitable when a component within the same application needs to notify other components of a business occurrence without directly depending on them. For example:

- Order created: send notifications, write audit logs, update statistics.
- User registered: initialize secondary profiles or send a welcome email.
- File finished processing: update status and notify interested components.

Do not treat application events as a message broker. This mechanism primarily serves communication within the same Spring application context; by default, it does not provide durable storage, retries, delivery acknowledgments, or cross-network messaging.

## 9. Event Flow Checklist

When implementing an event flow, verify the following:

1. Do the event name and payload clearly represent what happened?
2. Does the publisher receive `ApplicationEventPublisher` via dependency injection?
3. Is the listener registered as a Spring bean?
4. Does the event type accepted by the listener match the published object?
5. Does the work need to run synchronously or can it run asynchronously?
6. Where are exceptions from listeners logged and handled?
7. If the event is published inside a transaction, which phase should the listener run in?
8. Is there a need to persist events, retry, or deliver to another service? If so, plain application events may not meet the requirements.

The core of this flow is that a publisher publishes an object via `ApplicationEventPublisher`; the application context passes the object to `ApplicationEventMulticaster`; the multicaster selects listeners by event type and invokes them according to the execution configuration. Understanding the listener selection step and synchronous/asynchronous modes helps accurately predict execution order, when exceptions appear, and the relationship between events and transactions.

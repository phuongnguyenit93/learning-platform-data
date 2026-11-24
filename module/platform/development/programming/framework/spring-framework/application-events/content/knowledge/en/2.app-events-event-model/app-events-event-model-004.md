# Relationship Between ApplicationContext and the Event Bus

In the Spring Framework, **ApplicationContext** serves both as the container managing beans and application lifecycle and as the publication point for application events. A service can emit an event via **ApplicationEventPublisher** without needing to know how many listeners are listening. Event coordination is performed inside the context through **ApplicationEventMulticaster**.

In this lesson, "event bus" is a term describing Spring's internal event publishing and dispatching mechanism. It is not a standalone message broker like Kafka or RabbitMQ.

## 1. Components and Their Relationships

### ApplicationContext

**ApplicationContext** is the central interface of the Spring container. Beyond bean lookup, resource management, message sources, and context lifecycle, this interface also extends **ApplicationEventPublisher**. Therefore, an ApplicationContext can accept event publish calls and forward events to the listener system.

An application typically has one main context; a web application may have a root context and a child context. Each context has its own event infrastructure, which can interact with its parent context according to hierarchy rules.

### ApplicationEventPublisher

**ApplicationEventPublisher** is the event publishing contract. Business code only needs to depend on this interface:

- Call `publishEvent(event)` to announce that an event has occurred.
- No need to look up listeners, invoke listeners directly, or know which module listeners reside in.
- Can publish an event object extending `ApplicationEvent` or a regular Java object.

Prefer injecting `ApplicationEventPublisher` into a service rather than injecting the entire `ApplicationContext` if the service only needs to publish events. This reduces coupling to the container and makes the code's intent clearer.

### ApplicationEventMulticaster

**ApplicationEventMulticaster** is the component that dispatches events to listeners registered in the context. It is responsible for selecting listeners matching the event type and invoking them.

If the application does not declare a bean named **applicationEventMulticaster**, Spring creates a default **SimpleApplicationEventMulticaster** for the context. An application can declare its own bean with that name to configure dispatching behavior, such as providing a task executor or an error handler.

The multicaster is the part that performs dispatching. The publisher is the API for sending events; `ApplicationContext` connects that API to the multicaster.

### Events and Listeners

An **Event** is data describing something that has happened, such as an order being created or a profile being approved. An event should have a name expressing a past occurrence and the data needed for listeners to handle it.

There are two common ways to register a listener:

- **ApplicationListener**: implement the interface and handle a specific `ApplicationEvent` type. This is a familiar pattern in older Spring applications or APIs.
- **@EventListener**: annotate a method on a Spring bean. The method's parameter type indicates the type of event the method receives.

Since Spring Framework 4.2, a regular POJO can be published without extending `ApplicationEvent`. When a regular object is published, Spring represents it as a `PayloadApplicationEvent` at the event layer; listeners can directly declare the payload type they want to receive.

## 2. Event Publishing and Dispatching Flow

Basic processing flow:

1. A business bean calls `ApplicationEventPublisher.publishEvent(event)`.
2. `ApplicationContext` receives the event and forwards the request to that context's own `ApplicationEventMulticaster`.
3. The multicaster finds listeners matching the event type.
4. Listeners are invoked according to the configured execution mechanism.
5. Each listener performs its own reaction; the publisher does not need to call each listener directly.

For example, `OrderService` emits `OrderCreated`. One listener may send an email, while another may update metrics or write an audit log. `OrderService` is only responsible for announcing that the order has been created.

### Listener Registration in the Context Lifecycle

When the context is refreshed, Spring initializes the event multicaster and registers listeners. Beans implementing `ApplicationListener` are detected during this process. For methods annotated with `@EventListener`, Spring uses an annotation processor to detect the methods and register corresponding adapters with the multicaster.

Consequently, a class with `@EventListener` that is not instantiated as a bean in the context will not automatically receive events. Listeners must be within Spring's management scope, for example declared with `@Bean` or discovered by component scanning.

### Event Types and Acceptance Conditions

Listeners only receive events compatible with the type they declare. With `@EventListener`, the method parameter type is the primary criterion Spring uses to determine which events to deliver. You can use the `condition` attribute of `@EventListener` for additional filtering with SpEL expressions when needed.

If multiple listeners receive the same event, Spring invokes each registered listener. You can use `@Order` or the `Ordered` interface to specify order when processing sequence truly matters. Do not rely on arbitrary order or accidental registration order.

## 3. Synchronous, Asynchronous, and Error Handling

### Synchronous by Default

**SimpleApplicationEventMulticaster invokes listeners synchronously on the thread publishing the event by default.** This has several consequences:

- The `publishEvent` call completes only after all synchronous listeners finish executing.
- A slow listener delays the business flow that published the event.
- Listeners can read data residing in the same execution context, but can also increase request latency.
- Exceptions from a listener can propagate back to the event-publishing site if no error handler handles them.

Therefore, do not assume that merely publishing an event makes the task run in the background. Events in Spring do not automatically spawn a new thread by default.

### Asynchronous Configuration

You can configure an executor for the `SimpleApplicationEventMulticaster` bean named `applicationEventMulticaster` via `setTaskExecutor`, or use `@Async` on listeners and enable the corresponding async processing. When switching to asynchronous execution, consider:

- Listeners may run on a different thread and finish after the publisher has returned.
- Completion order across listeners is no longer the original synchronous order.
- Shared data must be safe for concurrent access.
- Exceptions in async tasks need to be observed and handled separately; the caller usually does not receive those exceptions directly.
- Do not pass objects tied to the request thread or transaction thread to the executor if they are unsafe to use on another thread.

Only enable async when there is a latency or workload reason. If the listener's result is needed before continuing the business flow, synchronous processing or calling the service directly is usually more appropriate.

### Transaction-Bound Events

If a listener should run only when a transaction commits or rolls back, you can use **@TransactionalEventListener**. By default, this listener is bound to the `AFTER_COMMIT` phase. It is useful when reacting after data has been committed, such as sending a notification after an order is successfully created.

An active transaction must exist at the time the event is published for the listener to bind to that transaction. If you want the listener to still run when no transaction is present, you can consider `fallbackExecution`, but only enable it when that behavior matches the business logic. `@TransactionalEventListener` does not turn internal events into durable messages; it still belongs to the in-process event mechanism.

## 4. Runnable Example with Java 17 and Spring Framework

The example below creates an `ApplicationContext`, injects `ApplicationEventPublisher` into `OrderService`, and registers a listener using `@EventListener`. The event is a regular Java record, not extending `ApplicationEvent`.

### Directory Structure

~~~text
application-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventDemo.java
~~~

### pom.xml

The example uses Spring Framework 6.2.0 and Java 17. The `spring-context` dependency provides `ApplicationContext`, configuration annotations, and event infrastructure.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-event-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ApplicationEventDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orderService = context.getBean(OrderService.class);
            orderService.placeOrder("DH-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void placeOrder(String orderId) {
            System.out.println("Order created: " + orderId);
            publisher.publishEvent(new OrderCreated(orderId));
        }
    }

    public record OrderCreated(String orderId) {
    }

    public static class OrderCreatedListener {

        @EventListener
        public void onOrderCreated(OrderCreated event) {
            System.out.println("Received OrderCreated: " + event.orderId());
        }
    }
}
~~~

### Compile and Run

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApplicationEventDemo
~~~

Stdout result:

~~~text
Order created: DH-1001
Received OrderCreated: DH-1001
~~~

The first line is printed inside `OrderService`. Then `publishEvent` passes `OrderCreated` through the context to the listener. Because the multicaster is synchronous by default, the listener runs immediately on the thread calling `placeOrder` and prints the second line before the method finishes.

Key points to observe in the example:

- `OrderService` depends only on `ApplicationEventPublisher`.
- `AppConfig` creates `OrderService` and the listener as beans in the same context.
- `OrderCreated` is an immutable record containing only the order ID needed by the listener.
- `OrderCreatedListener` is not called directly by `OrderService`; Spring finds and invokes the `@EventListener` method.
- Closing the context with try-with-resources ends the context lifecycle cleanly.

## 5. Relationship Between Parent and Child Contexts

`ApplicationContext` supports a hierarchical structure. When a child context publishes an event, the event is handled by the child context's multicaster and Spring also forwards the event up to the parent context. This propagation goes from child to parent; events published in a parent context do not automatically propagate down to child contexts.

This is useful in applications with multiple contexts, but you should avoid registering listeners in both parent and child if the same event could cause handling to execute twice. When designing listeners, identify which context a bean belongs to and which context emits the event.

## 6. When Should You Use Spring's Event Bus?

It is suitable when components within the same application need to react to an event without the publisher depending directly on each receiving component. For example:

- After creating an order, send a confirmation email and write an audit log.
- After updating a profile, refresh an internal cache.
- After completing a business operation, update metrics or send an in-app notification.
- Decouple secondary reactions from the main flow so business modules depend less on each other.

Do not treat the `ApplicationContext` event bus as a distributed messaging system. Internal events are not automatically persisted durably, have no history to replay after an application restart, and do not guarantee delivery across multiple processes or services. If business requirements demand retries, persistence, replay, independent consumers, or cross-service messaging, use an appropriate message broker and consider a Transactional Outbox to synchronize data commits with message publishing.

## 7. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Injecting `ApplicationContext` just to publish events | Service depends on a broader container than needed | Inject `ApplicationEventPublisher` |
| Assuming listeners run in the background by default | Requests still have to wait for listeners to finish | Configure async intentionally if appropriate |
| Using internal events instead of a broker | No durability or distributed delivery guarantees | Use a broker/outbox when cross-process communication is needed |
| Listener is not a Spring bean | `@EventListener` method is not registered | Declare a bean or configure component scan |
| Event contains a mutable entity or too much data | Listeners may depend on changing state and become hard to control | Prefer immutable events containing IDs and necessary data |
| Listener performs slow tasks on the synchronous flow | Increases latency of the event-publishing site | Evaluate async or separate the task |
| Not handling listener exceptions | Secondary failures can affect the event-publishing flow | Define an error handling and logging policy |
| Using `@TransactionalEventListener` while publishing outside a transaction | Transaction-phase listener may not be invoked | Check transaction boundaries or configure `fallbackExecution` when valid for business logic |

## 8. Choosing the Right API

| Need | Approach |
|---|---|
| Announce an event from a service | Inject `ApplicationEventPublisher` and call `publishEvent` |
| Handle an event with a concise method | Use `@EventListener` on a bean |
| Integrate via the traditional listener interface | Implement `ApplicationListener` for the corresponding `ApplicationEvent` type |
| Process only after transaction commit | Use `@TransactionalEventListener` with the appropriate phase |
| Need async dispatching | Configure an executor for the multicaster or use `@Async` properly |
| Need durable delivery across services | Use a broker and a data-guarantee design, such as Transactional Outbox |

The core relationship is: **ApplicationContext provides event publishing capabilities; ApplicationEventPublisher is the contract used by business code; ApplicationEventMulticaster dispatches events; listeners are beans that receive and handle events.** By decoupling publishers from listeners, modules within the same application can coordinate via events without knowing each other's implementation details.
# Default Synchronous Events in Spring

## 1. Objectives and Context

Spring Application Events allows one component to announce that an event has occurred so other components can react without the publisher calling each listener directly. For example, an order creation service emits `OrderCreatedEvent`; listeners can send notifications, write audit logs, or update related data.

In Spring Framework's default configuration, event processing is **synchronous**. When a publisher calls `ApplicationEventPublisher.publishEvent(...)`, Spring invokes matching listeners directly on the event-publishing thread. The `publishEvent` call returns only after all synchronous listeners finish running.

This is the default behavior of `ApplicationContext` when Spring uses `SimpleApplicationEventMulticaster` without a configured `TaskExecutor`. Behavior can change if the application replaces the multicaster or explicitly uses an asynchronous mechanism. Therefore, distinguish the `publishEvent` contract from the actual dispatch configuration: the `publishEvent` API hands the event to the multicaster; the multicaster itself decides how listeners are invoked.

After this lesson, you will be able to:
- Describe the flow from publisher to listener and the role of `ApplicationEventPublisher`.
- Explain why listeners run on the same thread as the publisher by default.
- Write a small Spring application to observe execution order.
- Recognize the impact of slow listeners, exceptions, and transactions.
- Know common ways to switch listeners to asynchronous processing when genuinely needed.

## 2. Components in the Event Model

**Event** is an object describing an event that has occurred, typically carrying data needed for listeners to process. Name events after what happened, such as `OrderCreatedEvent`, `PaymentCompletedEvent`, or `UserRegisteredEvent`. Using a record or immutable class prevents event data from being unintentionally modified after publishing.

**Publisher** is the component that emits events through `ApplicationEventPublisher`. In a Spring application, inject this interface into a service instead of finding or calling each listener manually.

**Listener** is the component that receives events. A common approach is placing `@EventListener` on a method of a Spring-managed bean. Spring registers that method and invokes it when a matching event is published.

**ApplicationEventMulticaster** is the component that coordinates delivering events to registered listeners. If the application does not provide a bean named `applicationEventMulticaster`, `ApplicationContext` creates a default `SimpleApplicationEventMulticaster`. When no `TaskExecutor` is attached, the multicaster invokes listeners directly on the current thread.

Since Spring Framework 4.2, a publisher can emit a regular Java object; events are not required to extend `ApplicationEvent`. The example below uses the `OrderCreatedEvent` record.

## 3. Synchronous Execution Flow

Suppose a service performs three steps:

1. Print a message before publishing the event.
2. Call `publishEvent(new OrderCreatedEvent(...))`.
3. Print a message after `publishEvent` returns.

When a matching listener exists, the default order is:

~~~text
Publisher: before publishEvent
Listener:  start handling event
Listener:  finished handling event
Publisher: after publishEvent
~~~

The listener runs right inside the `publishEvent` call. If the publisher is running on a thread named `publisher-thread`, the synchronous listener also runs on `publisher-thread`. No new thread or intermediate queue is created simply because the application uses `@EventListener`.

This means listener processing time is part of the publisher's execution time. If a listener takes 800 ms, the publisher must wait for that processing to finish before proceeding, unless the listener or multicaster is configured asynchronously.

## 4. Runnable Example with Java 17+

The example uses Spring Framework 6.2.0, Maven, and Java 17. Create the project structure:

~~~text
spring-sync-events/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── EventDemo.java
                        ├── OrderCreatedEvent.java
                        ├── OrderService.java
                        └── OrderCreatedListener.java
~~~

### 4.1. Declaring Dependencies

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-sync-events</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Creating the Event

File `src/main/java/com/example/events/OrderCreatedEvent.java`:

~~~java
package com.example.events;

public record OrderCreatedEvent(String orderId) {
}
~~~

The record stores the order ID and provides the `orderId()` accessor. This is a regular event object; there is no need to extend `ApplicationEvent`.

### 4.3. Creating the Publisher

File `src/main/java/com/example/events/OrderService.java`:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void create(String orderId) {
        System.out.println("1. Before publish: "
                + Thread.currentThread().getName());

        eventPublisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println("3. After publish: "
                + Thread.currentThread().getName());
    }
}
~~~

`OrderService` depends only on `ApplicationEventPublisher`. The service does not need to know how many listeners exist, where they are located, or what work they will perform.

### 4.4. Creating the Listener

File `src/main/java/com/example/events/OrderCreatedListener.java`:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println("2. Listener: "
                + Thread.currentThread().getName()
                + " handling " + event.orderId());
    }
}
~~~

Spring detects the `@EventListener` method in a managed bean and registers it as a listener for `OrderCreatedEvent`. The method parameter determines the event type accepted by the listener.

### 4.5. Initializing ApplicationContext and Running

File `src/main/java/com/example/events/EventDemo.java`:

~~~java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class EventDemo {

    public static void main(String[] args) {
        Thread.currentThread().setName("publisher-thread");

        try (var context =
                     new AnnotationConfigApplicationContext(EventDemo.class)) {
            context.getBean(OrderService.class).create("ORD-1001");
        }
    }
}
~~~

`@ComponentScan` specifies no package, so Spring scans `EventDemo`'s package and subpackages. `OrderService` and `OrderCreatedListener` in the same package are registered as beans.

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventDemo
~~~

Program output:

~~~text
1. Before publish: publisher-thread
2. Listener: publisher-thread handling ORD-1001
3. After publish: publisher-thread
~~~

The listener line appears between the publisher's two lines. All three lines display `publisher-thread`, proving the listener runs on the thread calling `publishEvent`. If the listener ran asynchronously, the publisher could print line 3 before the listener completed, and the listener's thread could be different.

## 5. What Happens When There Are Multiple Listeners?

An event can be of interest to multiple listeners simultaneously. When an event is published, the multicaster finds listeners capable of handling that event type and invokes them according to the dispatch configuration.

If you need to specify order among listeners, you can use `@Order` on methods or beans. Smaller order values have higher priority. For example:

~~~java
@Order(1)
@EventListener
public void updateInventory(OrderCreatedEvent event) {
    // Update inventory
}

@Order(2)
@EventListener
public void sendNotification(OrderCreatedEvent event) {
    // Send notification
}
~~~

Do not rely on arbitrary order or accidental registration order when business rules require one listener to run before another. If steps are tightly coupled, a sequential orchestrating service is often clearer and easier to control than splitting them into multiple independent listeners.

## 6. Consequences of Synchronous Processing

### 6.1. Slow Listeners Slow Down the Publisher

The publisher must wait for synchronous listeners to complete. A listener calling an external service, running a slow database query, or performing heavy computation can increase response times for the thread calling `publishEvent`.

Therefore, default listeners are suitable for short tasks that need to execute immediately in the same processing flow. Do not place long-running work in a listener if the publisher does not need to wait for it.

### 6.2. Exceptions Can Propagate Back to the Publisher

With the default `SimpleApplicationEventMulticaster` having no `ErrorHandler` configured, exceptions raised while invoking a listener can propagate back through `publishEvent` to the publisher. An error in one listener can also halt the current multicast cycle before subsequent listeners are called.

Thus, decide clearly how to handle errors in listeners. You can catch and handle errors inside the listener when recoverable locally; if an error should cause the event-publishing operation to fail, let it propagate according to the business design. Do not swallow every exception, as doing so may mislead the publisher into thinking all processing succeeded.

### 6.3. Events in Spring Are Not a Message Queue

Application Events is an in-process communication mechanism within the same `ApplicationContext`. By itself, it does not provide durable storage, retries after application shutdown, delivery acknowledgments, cross-application distribution, or exactly-once delivery guarantees.

If you need cross-service communication, retries, event persistence, or processing after a process restarts, consider a message broker and transactional outbox. Do not treat `publishEvent` as a command sending a message to an external system.

## 7. When Is Asynchronous Execution Needed?

If the publisher does not need to wait for a listener's work, you can explicitly configure asynchronous execution. A common approach is to enable async processing and annotate the listener with `@Async`:

~~~java
package com.example.events;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
@ComponentScan
public class AsyncEventConfiguration {
}
~~~

~~~java
package com.example.events;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @Async
    @EventListener
    public void handle(OrderCreatedEvent event) {
        // This work is executed via the @Async executor.
    }
}
~~~

In production applications, configure an executor suited to the workload rather than leaving the number of tasks unbounded.

Another approach is to declare a `SimpleApplicationEventMulticaster` bean named `applicationEventMulticaster` and attach a `TaskExecutor` to it. This changes dispatching at the `ApplicationContext` level, so assess its impact on all relevant listeners.

When switching to asynchronous execution, note:

- The publisher can continue before the listener finishes processing.
- Listeners may run on a different thread; you cannot rely on `ThreadLocal` or the publisher's thread context unless explicitly propagated or re-established.
- Asynchronous listener exceptions do not propagate back to the original `publishEvent` call. For `void` methods, configure how async errors are logged and handled.
- Account for thread limits, queue capacities, timeouts, and potential executor overload.
- With `@Async` on an `@EventListener` method, do not rely on the method's return value to publish a follow-up event; async processing does not use the event-return mechanism like synchronous listeners.

Switch to async only when business requirements allow the publisher not to wait for results and the system has mechanisms for error tracking and resource limits.

## 8. Events Related to Transactions

A regular `@EventListener` runs immediately when the event is published. If a publisher emits an event inside a `@Transactional` method, a synchronous listener is typically invoked within that transaction flow before the transactional method completes.

This can cause issues if the listener performs external actions before the transaction commits. For example, a listener sends an email successfully, but the transaction saving the order rolls back afterward; the system has sent a notification for an order that was never saved.

When processing needs to follow the transaction lifecycle, use `@TransactionalEventListener`:

~~~java
package com.example.events;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedTransactionalListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        // Process only after the event-publishing transaction has committed.
    }
}
~~~

To compile and use transactional listeners, add the `spring-tx` dependency of the matching Spring Framework version to `pom.xml` and configure an appropriate `PlatformTransactionManager`. The publisher must also emit the event inside an active transaction, typically through a `@Transactional` method with transaction management enabled. The runnable example in section 4 only demonstrates synchronous handling and does not configure a transaction manager.

By default, the phase of `@TransactionalEventListener` is `AFTER_COMMIT`. If there is no transaction, the listener is not called unless `fallbackExecution = true` is enabled. This annotation controls timing relative to a transaction; by itself, it does not imply asynchronous execution.

If post-commit work must be guaranteed not to be lost when a process stops unexpectedly, in-memory `ApplicationContext` callbacks alone are insufficient; design durable storage such as a transactional outbox or an appropriate messaging mechanism.

## 9. Common Errors and How to Check

| Symptom | Common Cause | How to Check or Resolve |
|---|---|---|
| Listener is not called | Listener bean is not in `ApplicationContext`, package scan does not cover the bean, or parameter type does not match the event | Check component scan, bean registration, and event type |
| Publisher is slow | Synchronous listener performs long-running work | Measure duration of each listener; move suitable work to async |
| Exception appears at `publishEvent` | Synchronous listener threw an exception | Inspect listener stack trace and `ErrorHandler` policy |
| Listener runs on another thread | `@Async` is present or multicaster uses a `TaskExecutor` | Check async configuration and thread names |
| Transactional listener does not run | Event was not published inside a transaction and `fallbackExecution` is not enabled | Check `@Transactional` boundaries and phase |
| Notification sent despite transaction rollback | Regular `@EventListener` used to perform actions before commit | Consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or an outbox |

When debugging, check sequentially: does the publisher actually call `publishEvent`; is the created event the right type; is the listener a Spring bean; does the method have `@EventListener`; and is `ApplicationContext` using the default multicaster or has a custom configuration replaced it.

## 10. Key Takeaways

In Spring's default configuration, `ApplicationContext` uses `SimpleApplicationEventMulticaster` without a `TaskExecutor`. Therefore, matching listeners are invoked directly on the event-publishing thread, and the publisher waits for listeners to finish before `publishEvent` returns. This approach is simple, observable, and suitable for short tasks within the same application.

When you need to reduce wait time, explicitly use `@Async` or configure an executor for the multicaster. When you need to tie processing to commit timing, use `@TransactionalEventListener`. When you need durability, retries, or inter-process communication, choose a persistent messaging mechanism that fits system requirements.

# Void Listeners That Only Produce Side Effects

## 1. Objectives and Scope

In Spring Application Events, listeners are commonly used to react to an occurrence by performing an action. Many listeners do not need to send result data back to where the event was published. They only need to perform a side effect, such as writing an audit log, updating a cache, incrementing a metric, sending a notification, or updating auxiliary state.

Such a listener typically has a method returning `void`. The publisher emits the event, Spring dispatches the event to the listener, and the listener performs its own work. The publisher does not receive a result value from the listener through `publishEvent()`.

After this lesson, you will be able to:

- Explain `void` listeners and the meaning of side effects.
- Write listeners using `@EventListener` or `ApplicationListener<E>`.
- Distinguish a listener that only produces side effects from a listener that returns a new event.
- Understand how execution timing, errors, and transactions affect side effects.
- Choose direct service calls when a processing result must be returned.

The scope of this lesson is internal events within a single Spring ApplicationContext. Examples use Java 17+ and Spring Framework without requiring Spring Boot.

## 2. What Is a Side Effect?

A side effect is an observable change or action that occurs when a method executes, apart from returning a value to the caller. For example:

- Writing an entry to an audit log.
- Saving a history record to a database.
- Evicting a cache entry so the next read fetches fresh data.
- Sending an email or notification.
- Incrementing a metric counter.
- Submitting a task to an executor or messaging system.

Suppose the application publishes an `OrderPlaced` event after creating an order. A listener can record the order history:

```java
@EventListener
public void recordOrder(OrderPlaced event) {
    auditService.record("ORDER_PLACED", event.orderId());
}
```

The `recordOrder` method returns `void`: it does not provide result data to the publisher. Its job is to produce a side effect by calling `auditService`.

A listener can have multiple side effects if they belong to the same clear responsibility. However, if a single method sends emails, updates inventory, charges fees, and records audits, split them into separate listeners or services so each action can be understood, tested, and error-handled independently.

## 3. How Does a Void Listener Work?

With `@EventListener`, the parameter type tells Spring which kind of event the listener wants to receive. The method can return `void`:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // perform side effect
}
```

Spring registers the method on a Spring bean and invokes the method when a matching event is published. The publisher typically only needs to state that the event occurred:

```java
publisher.publishEvent(new OrderPlaced("ORD-2001"));
```

The `ApplicationEventPublisher.publishEvent(Object)` API has a `void` return type. It does not aggregate results from listeners and does not return business results from individual listeners.

Under the default configuration, listeners are called synchronously. Therefore, the `publishEvent()` call usually returns only after synchronous listeners finish. That does not mean the publisher receives a result from listeners: it only knows that synchronous listener invocation has completed. If a listener throws an exception, the exception can propagate back to the publisher.

If a listener is configured asynchronously, the publisher can continue before the side effect completes. In that case, the publisher also does not know whether the work succeeded or failed just from calling `publishEvent()`.

### Not Returning Data Does Not Mean No Effect

A `void` listener still produces an observable outcome in the system. For example, a new audit record appears in the database or a cache entry is evicted. That outcome lives in the state modified by the listener, not in the method's return value.

This aligns with the event notification model: the publisher announces that something happened, and listeners react independently. If the publisher needs a return value to decide the next business step, a `void` event listener is not the right contract.

## 4. Complete Example: Writing an Audit on a New Order

The following example creates an `OrderPlaced` event. A listener receives the event and writes an entry to an in-memory audit log. The listener returns no value.

### Maven Configuration

Create a Maven project, place the source code at `src/main/java/demo/SideEffectListenerDemo.java`, and add the following configuration sections inside the root `<project>` element of `pom.xml`. The example uses Spring Framework 6.2.19 and Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>6.2.19</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.0</version>
        </plugin>
        <plugin>
            <groupId>org.codehaus.mojo</groupId>
            <artifactId>exec-maven-plugin</artifactId>
            <version>3.5.0</version>
        </plugin>
    </plugins>
</build>
```

### Source Code

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class SideEffectListenerDemo {

    @Bean
    AuditLog auditLog() {
        return new AuditLog();
    }

    @Bean
    OrderPlacedListener orderPlacedListener(AuditLog auditLog) {
        return new OrderPlacedListener(auditLog);
    }

    @Bean
    OrderService orderService(ApplicationEventPublisher publisher) {
        return new OrderService(publisher);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SideEffectListenerDemo.class)) {

            OrderService orderService =
                    context.getBean(OrderService.class);

            orderService.place("ORD-2001");

            AuditLog auditLog = context.getBean(AuditLog.class);
            System.out.println("Audit entries: " + auditLog.entries());
        }
    }

    record OrderPlaced(String orderId) {
    }

    static class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void place(String orderId) {
            System.out.println("Publisher: order created " + orderId);
            publisher.publishEvent(new OrderPlaced(orderId));
            System.out.println("Publisher: publishEvent returned");
        }
    }

    static class OrderPlacedListener {
        private final AuditLog auditLog;

        OrderPlacedListener(AuditLog auditLog) {
            this.auditLog = auditLog;
        }

        @EventListener
        public void recordAudit(OrderPlaced event) {
            auditLog.append("Order placed: " + event.orderId());
            System.out.println("Listener: audit recorded");
        }
    }

    static class AuditLog {
        private final List<String> entries = new ArrayList<>();

        void append(String entry) {
            entries.add(entry);
        }

        List<String> entries() {
            return List.copyOf(entries);
        }
    }
}
```

Key points to note:

1. `OrderService` depends only on `ApplicationEventPublisher`. It has no knowledge of `OrderPlacedListener` or `AuditLog`.
2. `OrderPlaced` is a Java record, so the event data is immutable after creation.
3. `OrderPlacedListener.recordAudit()` has a `void` return type. The side effect occurs in the `auditLog.append(...)` call.
4. `AuditLog.entries()` returns an unmodifiable copy of the list so readers cannot mutate the internal state of the audit log.
5. The classes are registered with `@Bean`, so Spring manages the listener and detects `@EventListener` when creating the ApplicationContext.

The audit log in the example is stored in memory solely to observe behavior. Real applications can inject a service that writes audits to a database or an appropriate logging system.

### Compile and Run

From the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SideEffectListenerDemo
```

Stdout output:

```text
Publisher: order created ORD-2001
Listener: audit recorded
Publisher: publishEvent returned
Audit entries: [Order placed: ORD-2001]
```

The line `Listener: audit recorded` appears before `Publisher: publishEvent returned` because listeners run synchronously by default. The last line confirms that the side effect updated the audit log. No return value from the listener was passed back to `OrderService`.

## 5. One Event Can Have Multiple Void Listeners

A single event can be of interest to multiple listeners. For example, when `OrderPlaced` is published, the application might:

- Write an audit record.
- Evict an order summary cache.
- Record a metric for new orders.
- Send a confirmation notification.

Each listener can be a separate bean with a `void` method:

```java
@Component
class OrderAuditListener {

    @EventListener
    public void record(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}

@Component
class OrderCacheListener {

    @EventListener
    public void evict(OrderPlaced event) {
        orderCache.evict(event.orderId());
    }
}

@Component
class OrderMetricListener {

    @EventListener
    public void count(OrderPlaced event) {
        metrics.increment("orders.placed");
    }
}
```

This is a structural illustration assuming `OrderPlaced`, `auditService`, `orderCache`, and `metrics` are already declared and injected appropriately.

The publisher emits just one event. The event multicaster dispatches the event to each matching listener. Independent listeners do not need to call each other or return results to one another.

If ordering among listeners does not matter, keep them independent. If a genuine ordering dependency exists, you can use `@Order`, though you should not rely on listener order to build a complex business workflow. For workflows needing step-by-step control and results, an explicit coordinating service is easier to understand.

## 6. Comparing Void Listeners and Event-Returning Listeners

Spring allows an `@EventListener` method to return an object. When a method returns a value instead of `void`, Spring publishes that value as a new event. This is a way to create an event chain:

```java
@EventListener
public OrderAuditRecorded record(OrderPlaced event) {
    auditService.record(event.orderId());
    return new OrderAuditRecorded(event.orderId());
}
```

This example performs two actions: writing the audit and emitting `OrderAuditRecorded`. Listeners for the new event can then continue processing.

| Characteristic | `void` Listener | Object-Returning Listener |
|---|---|---|
| Method return value | None | An event object |
| Side effects | Possible | Possible |
| Automatically publishes follow-up event | No | Yes, if non-null object returned |
| Publisher receives result directly | No | No |
| Typical purpose | Perform an auxiliary action | Perform an action and announce a subsequent occurrence |

The return value from a listener is not a response to `publishEvent()`. Spring treats the returned object as a new event and dispatches it like any other event. If you want a listener only to produce side effects, declare the method as `void` and return no event.

Do not return an object merely to inform the publisher that the listener succeeded. The publisher does not receive that object as the result of its call. When a synchronous result is needed, call a service with an appropriate return type.

## 7. Void Listeners and the ApplicationListener Interface

In addition to the `@EventListener` annotation, Spring provides the `ApplicationListener<E>` interface. The `onApplicationEvent` method inherently has a `void` return type:

```java
public class OrderAuditListener
        implements ApplicationListener<OrderPlaced> {

    private final AuditService auditService;

    public OrderAuditListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        auditService.record(event.orderId());
    }
}
```

This class must also be registered as a bean. The interface is suitable when you want to represent a listener as a dedicated class or use the traditional listener API. For most application listeners, `@EventListener` is more concise and readable.

Whether using annotations or the interface, listeners do not create a return channel back to the publisher. Both fit the notification-style event handling model.

## 8. Synchronous and Asynchronous Side Effects

### Synchronous by Default

By default, Spring invokes listeners on the thread that emits the event. When `publishEvent()` is called:

1. Spring finds matching listeners.
2. Spring calls each listener synchronously.
3. The listener performs its side effect.
4. Once processing finishes, `publishEvent()` returns.

This is useful when the side effect is small, fast, and must complete within the same execution flow. For example, updating an in-memory data structure or recording a simple change within the same transaction.

However, a slow listener slows down the publisher. If a listener sends email over the network or calls an external service, latency can increase significantly.

### Asynchronous

When a side effect can run in the background, you can combine `@Async` with `@EventListener` and enable async processing:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
}

@Component
class NotificationListener {

    @Async
    @EventListener
    public void sendNotification(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event.orderId());
    }
}
```

This snippet assumes `EnableAsync`, `Async`, `Component`, and the corresponding event and service types are imported. The listener bean must be Spring-managed and the call must go through the Spring proxy; an internal call within the same object does not trigger `@Async` in default proxy mode.

For asynchronous listeners:

- The publisher can continue before the side effect finishes.
- The publisher does not know whether the listener succeeded or failed via `publishEvent()`.
- Exceptions from a `void` method do not propagate back to the event-emitting thread. You can configure an `AsyncUncaughtExceptionHandler` to handle errors; by default, Spring logs async errors.
- Do not assume completion order across multiple async listeners.
- The publisher's transaction context is not automatically propagated to the executor thread.
- Configure an executor with bounded threads, a queue, and a rejection policy suited to the workload.

`@Async` moves work onto another thread, but does not create a durable queue. If the application stops before the task completes, the side effect might never occur.

## 9. Errors When a Listener Performs Side Effects

### Synchronous Listener Throwing an Exception

With the default multicaster when no `ErrorHandler` is configured, an exception from a synchronous listener can propagate to the `publishEvent()` caller and interrupt dispatch. Subsequent listeners might not be called if the exception escapes the multicaster.

Example:

```java
@EventListener
public void record(OrderPlaced event) {
    throw new IllegalStateException("Audit storage unavailable");
}
```

If `OrderService` calls `publishEvent()` without handling exceptions, the error can propagate up the call stack. Clearly decide which side effects are permitted to fail the primary operation. You can handle errors inside the listener, configure an `ErrorHandler` on the multicaster, or let errors propagate if that is the desired policy.

Do not catch every exception and silently discard it. If writing an audit or sending a notification fails, proper logging and observability are needed so operators know the action failed.

### Asynchronous Listener Encountering Errors

For an `@Async` listener returning `void`, the publisher cannot receive exceptions from the executor thread. Use `AsyncUncaughtExceptionHandler`, logging, and monitoring to record errors. If the business process requires retries or needs to know completion status, design a dedicated tracking mechanism or use an appropriate message broker.

### Side Effects May Be Repeated

An internal event can be emitted multiple times due to repeated business calls, request retries, or application-layer errors. Therefore, duplicate-sensitive side effects such as sending emails, recording financial transactions, or granting permissions should include idempotency mechanisms when needed.

For instance, storing a processed `eventId` or business key and checking it before performing the action can prevent duplicate execution. Checking and recording the idempotency key must be designed consistently with the transaction and storage layer.

## 10. Side Effects and Transactions

If a listener updates a database on the same thread and within the same active transaction, those changes can participate in the current transaction depending on the transaction manager configuration and resources used. When the transaction rolls back, database changes belonging to that transaction can roll back as well.

A side effect outside the database, such as sending an email or calling an HTTP API, generally cannot be rolled back simply because the database transaction fails. If a listener sends an email before the transaction commits and the transaction then rolls back, the recipient may still receive an email about a non-existent order.

When a side effect must wait for the transaction to commit, use `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderConfirmationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void sendConfirmation(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event.orderId());
    }
}
```

Transaction management must be configured and the event must be published within an active transaction. `AFTER_COMMIT` is the default phase of `@TransactionalEventListener`. If there is no transaction, the listener is not invoked by default; enable `fallbackExecution = true` only when you intentionally want to handle that case as well.

An after-commit listener is still just an in-process callback inside the application. If the process stops after the database commits but before the email is sent, the side effect can be missed. For durable delivery requirements, consider a Transactional Outbox or a messaging system with persistence and retries.

## 11. When to Use Side-Effect-Only Listeners

Use a `void` listener when an event describes something that has happened and other components can react independently without returning a result to the publisher. For example:

- Recording an audit when a user updates their profile.
- Evicting a cache when product data changes.
- Incrementing metrics when an order is created.
- Sending a notification after a successful payment.
- Updating a search index when content is published.

Call a service directly when:

- The publisher needs return data to decide the next step.
- The side effect is a mandatory condition for the main business operation to succeed.
- Explicit control over the sequence, result, and errors of each step is required.
- The caller must know immediately whether the operation succeeded or failed.

A useful rule of thumb: events fit notifying that something has happened; direct service calls fit requesting an action and receiving the result of that action.

## 12. Testing Void Listeners

Because a `void` listener has no return value, tests should verify the side effects it produces.

### Unit Testing the Listener

Call the method directly with a sample event, then verify that dependencies were invoked:

```java
@Test
void recordsAuditWhenOrderIsPlaced() {
    AuditService auditService = mock(AuditService.class);
    OrderAuditListener listener = new OrderAuditListener(auditService);

    listener.record(new OrderPlaced("ORD-2001"));

    verify(auditService).record("ORD-2001");
}
```

This test snippet assumes the listener accepts `AuditService` via its constructor and has a `record` method; JUnit Jupiter and Mockito are required in test dependencies.

### Testing Event Dispatch

Use an ApplicationContext in an integration test to confirm that the listener bean is registered and invoked when the publisher emits the matching event. You can use `@RecordApplicationEvents` along with Spring Test's `ApplicationEvents` to capture published events.

### Testing Asynchronous Listeners

Do not assert async side effects immediately after `publishEvent()`, because the task may not have finished running yet. Use a latch, Awaitility, or an appropriate synchronization mechanism to wait for completion with a finite timeout. Avoid fixed `Thread.sleep()` calls as they make tests slow and flaky.

### Testing Error Handling

Verify the policy when a dependency throws an exception: does the error propagate to the publisher or get handled in the listener? For async listeners, verify `AsyncUncaughtExceptionHandler` or the error-logging mechanism. Also test duplicate event emission if the side effect requires idempotency.

## 13. Common Design Mistakes

1. **Expecting the publisher to receive a result from a listener:** `publishEvent()` returns `void`; use a service with a return type if a result is needed.
2. **Returning an object just to signal success:** Spring treats an object returned from `@EventListener` as a new event. It does not become a response to the publisher.
3. **Assuming listeners run in the background by default:** listeners run synchronously by default; enable async and use `@Async` if you want them to run on an executor.
4. **Putting critical side effects in async listeners without monitoring:** the publisher does not know whether the listener succeeded or failed.
5. **Sending emails before transaction commit:** external side effects outside the database do not roll back automatically. Use transaction-bound listeners when appropriate.
6. **Swallowing exceptions:** side-effect failures become hidden and hard to detect. Logging, monitoring, or recovery mechanisms are needed.
7. **Failing to guard against duplicate processing:** the same event may be published multiple times. Important side effects should consider idempotency.
8. **Lumping too many responsibilities into one listener:** the listener becomes hard to test and failure in one action can affect others. Split by responsibility.
9. **Using events for operations requiring a response:** event communication is not request-response. Call a service directly when result data is needed.

## 14. Pre-Production Listener Checklist

- [ ] Event clearly describes an occurrence that has happened.
- [ ] Listener is registered as a Spring bean.
- [ ] Method returns `void` when only side effects are needed.
- [ ] Event payload is small and immutable.
- [ ] Publisher does not depend on any return value from the listener.
- [ ] Decided whether the listener runs synchronously or asynchronously.
- [ ] Defined where exceptions will be handled.
- [ ] External non-database side effects run only after commit if business rules require it.
- [ ] Critical side effects have error observability and deduplication when needed.
- [ ] Tested the produced side effect, execution timing, and error scenarios.

## 15. References

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework API — EventListener](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/event/EventListener.html)



# @Order on Event Listeners

## 1. The Role of @Order in Event Processing

An event in Spring can be received by multiple listeners. When listeners need to be invoked in a defined order, Spring provides an ordering mechanism via `@Order` and the `Ordered` contract.

For example, after receiving `OrderPlaced`, an application may need to sequentially run data validation, inventory reservation, audit logging, and notification sending. If these steps are synchronous listeners receiving the same event, a priority can be assigned to each listener so Spring invokes them in order.

`@Order` describes the priority order when a Spring mechanism supports ordering. For event listeners, it affects the dispatch order of matching listeners for the same event publication. It does not create a workflow, does not automatically guarantee an atomic transaction across multiple listeners, and does not control bean initialization order.

## 2. Ordering Rules

Spring follows the rules of the `Ordered` interface:

- A smaller order value means higher priority, and the listener is invoked first.
- A larger order value is invoked later.
- If no order is declared, the listener uses `Ordered.LOWEST_PRECEDENCE`, which corresponds to the lowest priority.
- `Ordered.HIGHEST_PRECEDENCE` or `Ordered.LOWEST_PRECEDENCE` can be used to express the two ends of the priority range.
- If two listeners have the same order, you should not rely on method declaration order or component scan order to decide which listener runs first.

Example:

| Listener | Order | Dispatch order |
|---|---:|---|
| ValidateOrder | 10 | First |
| ReserveInventory | 20 | Second |
| WriteAudit | 30 | Third |
| NotifyCustomer | Default | After listeners with an explicit order in the example |

Order is not time. `@Order(10)` does not mean the listener waits 10 milliseconds, runs 10 times, or takes 10 units of execution time.

You should choose spaced values such as 10, 20, 30 to make it easy to insert new steps. If the order has business significance, assign different values to the related listeners.

## 3. Placing @Order on @EventListener Methods

For annotation-declared listeners, place `@Order` directly on the `@EventListener` method:

```java
@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("10 validate");
    }

    @EventListener
    @Order(20)
    public void reserveInventory(OrderPlaced event) {
        System.out.println("20 reserve");
    }

    @EventListener
    @Order(30)
    public void writeAudit(OrderPlaced event) {
        System.out.println("30 audit");
    }
}
```

During ApplicationContext refresh, Spring detects listener methods, creates corresponding adapters, and registers them with the application event multicaster. When an `OrderPlaced` is published, the multicaster selects the matching listeners and sorts them by order before dispatching.

Order only compares listeners participating in the same dispatch. A listener receiving `PaymentCaptured` is not placed before or after a listener receiving `OrderPlaced` just because the two methods have different order values; the two events are distributed in two separate dispatches.

## 4. Listeners Without an Explicit Order

If an `@EventListener` method does not have `@Order` and the listener does not provide another order via the corresponding contract, it is treated as having the default priority `Ordered.LOWEST_PRECEDENCE`.

Example:

```java
@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("validate");
    }

    @EventListener
    public void notifyCustomer(OrderPlaced event) {
        System.out.println("notify");
    }
}
```

The `validate` listener has higher priority than the listener without a declared order. However, when multiple listeners use the default level or the same value, the relative order between them is not a contract you should rely on for business logic.

## 5. Using ApplicationListener and Ordered

If you want to represent a listener as a class implementing `ApplicationListener<E>`, you can place `@Order` on the class:

```java
@Component
@Order(10)
public class AuditListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("audit: " + event.orderId());
    }
}
```

Or implement the `Ordered` interface:

```java
@Component
public class InventoryListener
        implements ApplicationListener<OrderPlaced>, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        System.out.println("reserve: " + event.orderId());
    }
}
```

With `@EventListener`, declaring order on the method is the direct approach. With `ApplicationListener`, order can be provided at the class level or via `getOrder()`. Choose a single clear configuration source so maintainers can easily determine the actual priority.

## 6. @Order Does Not Determine Bean Initialization Order

You should not use `@Order` to tell Spring to initialize bean A before bean B. These two concerns belong to different mechanisms:

| Mechanism | Purpose |
|---|---|
| `@Order` on `@EventListener` method | Orders listeners during event distribution. |
| `@Order` on class or `Ordered` | Provides ordering for Spring mechanisms that support ordering. |
| Constructor injection | Declares dependencies between beans. |
| `@DependsOn` | Declares a bean that must be initialized before a dependent bean. |
| `SmartLifecycle#getPhase()` | Orders the start and stop sequence of lifecycle components. |

If one bean needs another bean, express the dependency through constructor injection or the appropriate lifecycle mechanism. Putting `@Order(1)` on a component does not replace Spring's dependency graph.

## 7. Ordering with Synchronous Listeners

By default, `SimpleApplicationEventMulticaster` invokes listeners synchronously on the event-publishing thread when no executor is configured. In this case, listeners are dispatched in order; the earlier listener invocation completes before the multicaster moves on to the next listener.

This can be useful when steps need to run sequentially on the same thread. However, `@Order` does not turn multiple listeners into a shared transaction. If the second listener fails, side effects already performed by the first listener outside a transaction may still persist.

With the default multicaster without an `ErrorHandler`, an exception from a synchronous listener can escape the dispatch process and prevent subsequent listeners from being invoked. If an `ErrorHandler` is configured, whether dispatching continues depends on how the handler deals with exceptions. Clearly define which listeners are mandatory and the error policy for each step.

## 8. Ordering with Asynchronous Listeners

There are two common ways to make a listener run asynchronously:

- Place `@Async` on the listener method so the async proxy delegates execution to an executor.
- Configure a `TaskExecutor` on `SimpleApplicationEventMulticaster` so the multicaster submits async-capable listeners to the executor.

Order can determine the order in which adapters are evaluated and tasks are submitted. It does not guarantee the order in which tasks start or complete when multiple threads are involved.

Example:

```java
@Async
@EventListener
@Order(10)
public void sendEmail(OrderPlaced event) {
    // Processed on the executor.
}
```

The task for the order 10 listener may be submitted before the order 20 task, but the order 20 task can still finish first if the order 10 task is slower. Do not use `@Order` to create a dependency such as "step B only runs after step A succeeds" in async processing.

When sequential coordination is needed, call an explicit orchestration service or combine `Future`/`CompletableFuture` so the next step depends on the result of the previous step. For async listeners returning `void`, errors do not automatically propagate back to the publisher; configure an `AsyncUncaughtExceptionHandler` if centralized handling is needed.

## 9. Combining with @TransactionalEventListener

`@TransactionalEventListener` is also a type of event listener and can use ordering to sort callbacks that are triggered together. However, `TransactionPhase` determines when the callback is invoked relative to the transaction; `@Order` only determines the priority order within the group of matching callbacks.

Example:

```java
@Component
public class OrderTransactionListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(10)
    public void updateSearchIndex(OrderPlaced event) {
        // Callback after commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Order(20)
    public void publishNotification(OrderPlaced event) {
        // Callback after commit, with lower priority order.
    }
}
```

An `AFTER_COMMIT` listener is not invoked before commit just because it has `@Order(1)`. If two listeners belong to two different phases, the transaction phase determines when they execute; order does not override the phase.

## 10. Listeners Returning Another Event

An `@EventListener` method can return an event object instead of `void`. Spring will publish the return value as a new event; if the method returns an array or collection, the elements are published as separate events.

```java
@EventListener
@Order(10)
public InventoryCheckRequested onOrderPlaced(OrderPlaced event) {
    return new InventoryCheckRequested(event.orderId());
}
```

Order here sorts the listeners receiving `OrderPlaced`. Listeners receiving `InventoryCheckRequested` are sorted in the new dispatch according to their own order.

For a listener method marked `@Async`, you cannot use the method's return value to publish the next event via `@EventListener`'s return-value mechanism. If you need to publish from an async method, inject `ApplicationEventPublisher` and call `publishEvent` explicitly.

## 11. Runnable Java 17 + Spring Context Example

This example creates a record event payload and three listener methods in the same bean. The methods are assigned orders 10, 20, and 30 to demonstrate dispatch ordering.

Project structure:

```text
event-order-demo/
├── pom.xml
└── src/main/java/com/example/events/
    ├── Application.java
    ├── OrderPlaced.java
    └── OrderListeners.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>event-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.0</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
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
                    <mainClass>com.example.events.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**OrderPlaced.java**

```java
package com.example.events;

public record OrderPlaced(String orderId) {
}
```

**OrderListeners.java**

```java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class OrderListeners {

    @EventListener
    @Order(10)
    public void validate(OrderPlaced event) {
        System.out.println("10 validate: " + event.orderId());
    }

    @EventListener
    @Order(20)
    public void reserveInventory(OrderPlaced event) {
        System.out.println("20 reserve: " + event.orderId());
    }

    @EventListener
    @Order(30)
    public void writeAudit(OrderPlaced event) {
        System.out.println("30 audit: " + event.orderId());
    }
}
```

**Application.java**

```java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderListeners.class)) {
            context.publishEvent(new OrderPlaced("ORD-42"));
        }
    }
}
```

Run with Java 17 and Maven:

```bash
mvn -q compile exec:java
```

Stdout:

```text
10 validate: ORD-42
20 reserve: ORD-42
30 audit: ORD-42
```

The output shows that the listener with order 10 is invoked before order 20, followed by order 30. Because all three methods run synchronously in the example, the output accurately reflects the completion order of each invocation.

## 12. Testing Listener Ordering

You should test against a real ApplicationContext to verify that Spring has detected the annotations, registered the listener adapters, and dispatched the event properly:

1. Register the listener beans that receive the same event type.
2. Assign distinct orders to listeners that require a stable order.
3. Publish an event through the ApplicationContext.
4. Record the step IDs or names in a shared collection in the test.
5. Compare the actual list against the expected order.
6. Test exceptions separately for synchronous listeners and async listeners.

Example assertion for testing:

```java
assertEquals(List.of("validate", "reserve", "audit"), calls);
```

This is an illustrative assertion; a complete test needs to initialize the context, register the listeners, and publish the event. For async listeners, wait for tasks to complete using a latch or Future before checking the collection. Do not use a fixed `Thread.sleep` to guess whether a task has finished running.

Do not write tests that require a specific order between two listeners with the same order. If that order matters, assign two different values.

## 13. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| Order 20 runs before order 10 | Inverted understanding of priority rules | Smaller numbers are invoked first. |
| Default listener runs inconsistently relative to another listener | Multiple listeners share `LOWEST_PRECEDENCE` | Assign explicit orders for steps that need ordering. |
| Method order in source determines the result | Relying on method declaration order | Place `@Order` on each listener method. |
| Beans do not initialize according to order | Using `@Order` to control dependencies | Use constructor injection, `@DependsOn`, or lifecycle phase. |
| Async tasks complete out of order | Confusing submission order with completion order | Use an orchestration service or compose Futures. |
| Subsequent listeners do not run when an earlier listener fails | Synchronous exception escapes the multicaster | Define an ErrorHandler policy and handle errors. |
| Two listeners have the same order and test passes or fails intermittently | Test relies on an unguaranteed order | Assign different orders. |
| Listeners on different events are grouped into one sequence | Confusing separate dispatch cycles | Use a workflow/service if cross-event coordination is needed. |

## 14. Implementation Checklist

1. Identify listeners that receive the same event and require an invocation order.
2. Place `@Order` directly on `@EventListener` methods.
3. Use smaller numbers for listeners that need to be invoked earlier.
4. Use distinct values when relative order matters.
5. Understand that listeners without a declared order use `Ordered.LOWEST_PRECEDENCE`.
6. For `ApplicationListener`, use class-level `@Order` or `Ordered#getOrder()`.
7. Do not use `@Order` to control bean initialization or replace dependency injection.
8. For async listeners, distinguish dispatch, submission, start, and task completion order.
9. Define the behavior when a synchronous listener throws an exception.
10. Use an orchestration workflow/service when a later step depends on the result of an earlier step.
11. Test with a real ApplicationContext and avoid depending on order between listeners with the same order.

## 15. References

- [Spring Framework Reference — Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @Order Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/annotation/Order.html)
- [Spring Framework 6.2 — @EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — Ordered Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/core/Ordered.html)

`@Order` helps declare clear priorities for listeners handling the same event. Use smaller numbers for listeners that should be invoked first, keep values distinct when order matters, and use a separate coordination mechanism for async work or result-dependent steps.

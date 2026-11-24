# Ordering Among Multiple Listeners for the Same Event in Spring Framework

When an event is published via `ApplicationEventPublisher.publishEvent(...)`, multiple listeners may be interested in that event type. For example, after an invoice issued event, the application may need to record audit logs, update analytics metrics, and send notifications. Spring provides a mechanism to determine the **listener invocation order**; however, you must distinguish **invocation** order from **completion** order, especially when asynchronous processing or transaction-bound listeners are involved.

## 1. How Does Spring Select and Invoke Listeners?

With a standard `ApplicationContext`, the default mechanism uses `SimpleApplicationEventMulticaster`:

1. Upon receiving an event, Spring selects the listeners that match the **event type** and applicable conditions (if any).
2. The listener list is sorted by the priority Spring recognizes.
3. Under the default configuration, Spring **invokes them sequentially and synchronously on the event-publishing thread**. The `publishEvent(...)` method usually returns only after the synchronous listeners have finished running.
4. If `@Async` or an asynchronous executor is configured for the multicaster, the order in which listeners complete is a different matter.

`@Order` is the right tool if you need to control the *invocation* order of independent listeners for the same event in synchronous execution. It does not determine bean creation order, does not order different event publications, and does not automatically create a transactionally guaranteed business workflow.

## 2. Rules of `@Order`

Place `@Order` **on each method annotated with `@EventListener`**. **Smaller numeric values have higher priority**, and are invoked earlier in the corresponding listener list.

| Declaration | Meaning within the same synchronous event publication |
| --- | --- |
| `@Order(-10)` | Before `@Order(0)` and `@Order(10)` |
| `@Order(0)` | Before `@Order(10)` |
| `@Order(10)` | After listeners with smaller values |
| No `@Order` declared | Defaults to the lowest priority, `Ordered.LOWEST_PRECEDENCE` (`Integer.MAX_VALUE`) |

Values do not have to be consecutive: `@Order(10)`, `@Order(100)`, and `@Order(1000)` are still sorted in that order. You can use the constants `Ordered.HIGHEST_PRECEDENCE` and `Ordered.LOWEST_PRECEDENCE`, though it is better to use readable values so the development team understands the intent.

**Two listeners with the same `@Order` value (or both without a declaration) have no relative order guaranteed by Spring.** Do not rely on the order methods appear in source code, method names, package scan order, bean initialization order, or results observed in a single run. If the order between A and B matters, give them two different priority values.

## 3. Complete Runnable Example with Java 17+

This example does not require Spring Boot, only `spring-context`. Create a Maven project with the structure:

```text
event-order-demo/
├── pom.xml
└── src/main/java/ListenerOrderDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>ListenerOrderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Contents of `src/main/java/ListenerOrderDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class ListenerOrderDemo {

    public record InvoiceIssued(String invoiceId) {}

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(InvoiceListeners.class);
            context.refresh();

            context.publishEvent(new InvoiceIssued("INV-42"));
        }
    }

    public static class InvoiceListeners {

        @EventListener
        @Order(30)
        public void notifyCustomer(InvoiceIssued event) {
            System.out.println("3. notify " + event.invoiceId());
        }

        @EventListener
        @Order(10)
        public void recordAudit(InvoiceIssued event) {
            System.out.println("1. audit " + event.invoiceId());
        }

        @EventListener
        @Order(20)
        public void updateAnalytics(InvoiceIssued event) {
            System.out.println("2. analytics " + event.invoiceId());
        }
    }
}
```

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java
```

The three lines printed by the listeners, in exact order, are:

```text
1. audit INV-42
2. analytics INV-42
3. notify INV-42
```

The `notifyCustomer` method is **declared first** in the class, yet runs **last** because of `@Order(30)`. `recordAudit` runs first because of `@Order(10)`, followed by `updateAnalytics` with `@Order(20)`. The `InvoiceIssued` record does not need to extend `ApplicationEvent`: Spring supports publishing plain objects via `publishEvent(Object)` and listeners can accept that exact payload type.

Note that this example only prints messages to observe ordering. In a real system, you should not treat `@Order` as a guarantee for interdependent business steps (for example, requiring the invoice to be saved successfully before disbursing funds).

## 4. If Using the `ApplicationListener` Interface Instead of `@EventListener`

A bean implementing `ApplicationListener<E>` can declare its order through the `Ordered` interface by returning a priority from `getOrder()`. The following example is an **illustrative snippet**, assuming `InvoiceIssuedEvent` is a class extending `ApplicationEvent` and the listener is registered as a Spring bean:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.core.Ordered;

public final class AuditListener
        implements ApplicationListener<InvoiceIssuedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(InvoiceIssuedEvent event) {
        // Handle the corresponding event.
    }
}
```

With this approach, `getOrder()` plays the same role as `@Order(10)`. A type difference to remember: `ApplicationListener<E>` requires `E extends ApplicationEvent`, whereas a method annotated with `@EventListener` can accept a plain payload object like the record in the example above.

When using `@EventListener`, place `@Order` directly on the **listener method**, so you do not mistakenly assume that a class-level `@Order` meant for another purpose (such as ordering beans when injecting a list) will determine the order of individual methods.

## 5. Cases Where Completion Order Cannot Be Inferred from `@Order`

### 5.1. Asynchronous Listeners

Example:

```java
@Async
@EventListener
@Order(10)
public void writeAudit(InvoiceIssued event) {
    // May run on an executor thread.
}

@EventListener
@Order(20)
public void updateMetrics(InvoiceIssued event) {
    // May complete before writeAudit.
}
```

The snippet above only illustrates the listener methods; for `@Async` to take effect, asynchronous processing must be enabled, for instance via `@EnableAsync`, and a suitable executor must be configured. Spring may **invoke/schedule** the `@Order(10)` listener first, but the work on another thread may finish after the `@Order(20)` listener. Similarly, if an executor is configured on `SimpleApplicationEventMulticaster`, sorting before submitting tasks to the executor does not mean the tasks start or finish in that order.

Therefore, `@Order` is not a happens-before guarantee between two asynchronous tasks, does not turn listeners into a sequential queue, and does not guarantee ordering in a distributed system. If B is only allowed to run after A succeeds, you must coordinate explicitly via direct calls, a controlled pipeline, chained `CompletableFuture`, or a queue/workflow system with appropriate ordering semantics.

### 5.2. Transaction-Bound Listeners

`@TransactionalEventListener` has phases such as `BEFORE_COMMIT`, `AFTER_COMMIT` (default), `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Callback timing is governed by the **transaction phase**; `@Order` can prioritize transactional listeners within the same matching phase, but it does not force an `AFTER_COMMIT` listener to run before logic currently processing the event inside the transaction just because it carries a smaller number.

You should not compare order using `@Order` alone when some listeners are regular `@EventListener`s and others are `@TransactionalEventListener`s. If there is no active transaction, transactional listeners are normally not invoked unless `fallbackExecution = true` is configured.

### 5.3. Errors in Synchronous Listeners

Under the default configuration, if a synchronous listener throws an exception, `SimpleApplicationEventMulticaster` has no `ErrorHandler` to swallow the error: the error is propagated back to the event publisher and the current dispatch stops. As a result, an `@Order(10)` listener failing can prevent an `@Order(20)` listener **from being invoked**. Do not assume every listener runs just because they are registered.

If independent error handling is desired, you must intentionally design error catching/logging or configure an `ErrorHandler`, taking into account the impact on business correctness.

### 5.4. Nested Events and Multiple Event Publications

If listener A is running and publishes a new event B, under synchronous execution B's listeners can run immediately within the nested call, before Spring returns to the next listener for event A. `@Order` only orders listeners applicable to **one corresponding dispatch cycle**, and does not create a global order across multiple events.

## 6. When to Use and How to Test

Use `@Order` when you have multiple **relatively independent** synchronous listeners that need an observable order, such as one listener adding logging context before other tracking listeners run. If an operation depends on the successful outcome of a previous operation, model that with an explicit orchestrating service and pass results between steps; event listeners are better suited for side reactions, notifications, and extensions that do not need to be tightly coupled to the main flow.

When testing order, initialize a Spring context with the listeners, publish **one specific event**, collect callback names into a list, and compare against the expected list. The test must use synchronous dispatch if verifying `@Order`. You can try reordering method declarations and still expect results according to `@Order` values. For asynchronous listeners, test using synchronization primitives/latches if you need to check completion; do not use `Thread.sleep` delays to assert order.

Common mistakes:

- Inverting priority: **smaller numbers run first**, not larger numbers.
- Assigning the same value to listeners while expecting a fixed order.
- Putting `@Order` on a class and assuming all `@EventListener` methods inside will take the desired order.
- Confusing listener order with bean initialization order or event ordering.
- Applying conclusions from synchronous dispatch to `@Async`, executor-backed multicasters, or transactional listeners.
- Using `@Order` as a guarantee for a mandatory-success business sequence, or forgetting that an exception in an earlier listener can prevent later listeners from being called.

## References

- [Spring Framework Reference – Application Events and Ordering Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc – `@EventListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Javadoc – `Ordered` and same-order behavior](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html)
- [Javadoc – `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Javadoc – `@TransactionalEventListener`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)

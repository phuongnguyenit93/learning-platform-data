# Filtering by Business State in Spring Framework Application Events

## 1. The Problem: One Event Type, Multiple States

In an order system, an order can transition through states such as `NEW`, `CONFIRMED`, `PAID`, `SHIPPED`, and `CANCELLED`. When the state changes, the system emits an `OrderStatusChanged` event; however, **not every listener needs to handle every change**:

- The invoicing service only cares when the new state is `PAID`.
- The shipping notification service only cares when the new state is `SHIPPED`.
- The cancellation handling service only cares when the new state is `CANCELLED`.
- Transitioning from `NEW` to `CONFIRMED` does not trigger the three tasks above.

That is **filtering by business state**: choosing to execute a listener based on the state value or state transition encapsulated in the event. Two filtering layers must be distinguished:

1. **By event type**: a method accepting `OrderStatusChanged` is only selected for the matching event type.
2. **By event content**: the condition `status == PAID` (or `oldStatus -> newStatus`) decides whether the method is invoked.

Filtering with `@EventListener(condition = ...)` does not make the event disappear from the entire `ApplicationContext`: other listeners can still receive the exact same event according to their own conditions. Listener filtering also **does not replace** validating state transition rules at the business layer.

## 2. Designing Events with Enough Information for Filtering

An event should be data describing what happened, rather than only holding a reference to an entity whose state continues to change. With Java 17+, you can use a `record`:

```java
public enum OrderStatus {
    NEW, CONFIRMED, PAID, SHIPPED, CANCELLED
}

public record OrderStatusChanged(
        String orderId,
        OrderStatus oldStatus,
        OrderStatus newStatus
) {}
```

Meaning of each property:

| Property | Meaning | Role when filtering |
| --- | --- | --- |
| `orderId` | Business key of the order | Identifies the target object to act on |
| `oldStatus` | State before the change | Distinguishes state transition paths |
| `newStatus` | New state after the change | Filters listeners by target state |

For example, `CONFIRMED -> PAID` and `NEW -> PAID` have the same target state but may carry different meanings depending on system rules. If the goal is simply "every paid order", filtering `newStatus == PAID` is enough; if only one transition path is accepted, **both** values must be checked.

In a real system, add `eventId` and `occurredAt` when tracking, auditing, or deduplication is needed. Event data should be immutable; `record` supports this at the structural level, though if a field holds a mutable object, an appropriate copy of the data is still needed.

## 3. Filtering Directly with `@EventListener(condition)` and SpEL

Spring allows `condition` to be a Spring Expression Language (SpEL) expression. The expression is evaluated **before** invoking the listener method; the method only runs when the condition evaluates to `true`.

```java
@EventListener(condition = "#p0.newStatus().name() == 'PAID'")
public void onPaid(OrderStatusChanged event) {
    // Only runs for events whose new status is PAID.
}
```

Here:

- `#p0` is the first parameter of the listener method, namely the `OrderStatusChanged` object. You can write `#a0` or `#root.args[0]` with the same meaning.
- `newStatus()` is the auto-generated accessor of the Java `record`; `name()` converts the enum constant to the string name `PAID`.
- `'PAID'` uses single quotes per SpEL string syntax. Renaming the enum constant requires updating the expression.
- `#event` by *Java parameter name* only works if parameter names are retained in bytecode (for example, compiled with `-parameters`). Using `#p0` keeps the example independent of that setting.
- `#root.event` points to the underlying `ApplicationEvent`; when publishing a plain Java object, Spring may wrap it in `PayloadApplicationEvent`. To directly access payload fields in the listener, `#p0` is usually clearer.

Multiple conditions can be combined:

```java
// Only handle transitions from CONFIRMED to PAID:
@EventListener(condition =
        "#p0.oldStatus().name() == 'CONFIRMED' && " +
        "#p0.newStatus().name() == 'PAID'")
public void onConfirmedOrderPaid(OrderStatusChanged event) {
    // Appropriate business handling.
}
```

SpEL supports logical operators such as `&&`, `||`, `!` (or `and`, `or`, `not`) and comparisons such as `==`, `!=`. For values that may be `null`, check for `null` before calling methods, e.g., `#p0.newStatus() != null && #p0.newStatus().name() == 'PAID'`. Better yet, design the event so statuses are non-`null` to avoid repeating checks in every listener.

## 4. Complete Runnable Example with Java 17 and Spring Framework

The following example runs in a plain `ApplicationContext`, without needing a web application, database, or message broker. We explicitly publish four events; only the three events matching the conditions print output lines.

**File structure**

```text
status-event-demo/
├── pom.xml
└── src/main/java/example/BusinessStatusEventDemo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>status-event-demo</artifactId>
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
                    <mainClass>example.BusinessStatusEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Version `6.2.0` is pinned so the example is reproducible; real projects should use a maintained Spring patch release and the project's dependency version management approach.

**`src/main/java/example/BusinessStatusEventDemo.java`**

```java
package example;

import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class BusinessStatusEventDemo {

    public enum OrderStatus {
        NEW, CONFIRMED, PAID, SHIPPED, CANCELLED
    }

    public record OrderStatusChanged(
            String orderId,
            OrderStatus oldStatus,
            OrderStatus newStatus
    ) {
        public OrderStatusChanged {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(oldStatus, "oldStatus");
            Objects.requireNonNull(newStatus, "newStatus");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static class OrderListeners {
        @EventListener(condition = "#p0.newStatus().name() == 'PAID'")
        public void whenPaid(OrderStatusChanged event) {
            System.out.println("PAID: " + event.orderId());
        }

        @EventListener(condition = "#p0.newStatus().name() == 'SHIPPED'")
        public void whenShipped(OrderStatusChanged event) {
            System.out.println("SHIPPED: " + event.orderId());
        }

        @EventListener(condition = "#p0.newStatus().name() == 'CANCELLED'")
        public void whenCancelled(OrderStatusChanged event) {
            System.out.println("CANCELLED: " + event.orderId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.NEW, OrderStatus.CONFIRMED));
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.CONFIRMED, OrderStatus.PAID));
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.PAID, OrderStatus.SHIPPED));
            context.publishEvent(new OrderStatusChanged(
                    "O-102", OrderStatus.NEW, OrderStatus.CANCELLED));
        }
    }
}
```

**Run** from the directory containing `pom.xml`, with JDK 17+ and Maven installed:

```bash
mvn -q compile exec:java
```

The `System.out` lines produced by the program, in exact order:

```text
PAID: O-101
SHIPPED: O-101
CANCELLED: O-102
```

The `NEW -> CONFIRMED` event is still published successfully, but no listener in the example matches its condition, so no line is printed. Each of the remaining event publications triggers only the listener with the matching target status. Log lines from libraries or build tools, if configured, are separate from the three business output lines above.

**Why does the example work?** `AnnotationConfigApplicationContext` registers `DemoConfig` and the `OrderListeners` bean; Spring detects the methods annotated with `@EventListener`. When `publishEvent(...)` receives an `OrderStatusChanged`, Spring matches the parameter type and evaluates each `condition` expression against that payload. By default, listeners run synchronously on the publishing thread, so the publishing order in `main` is also the output line order of the example.

## 5. Choosing Filtering Techniques by Complexity

| Scenario | Suitable Approach | Reason |
| --- | --- | --- |
| A single state or simple, data-only condition | `@EventListener(condition = "...")` | Concise; listener is not invoked if it does not match |
| Need both old and new states | SpEL condition on `oldStatus` and `newStatus` | Precisely distinguishes transitions |
| Complex rules needing service calls, configuration, or data queries | `@EventListener` then check in Java or a policy service | Easier to read, test, and handle errors than long SpEL |
| Only process after the data-writing transaction commits | `@TransactionalEventListener(phase = AFTER_COMMIT, condition = "...")` | Avoids side effects when the transaction rolls back |
| A business milestone with independent, stable semantics | Publish a dedicated event type like `OrderPaidEvent` | Clearer model; reduces repeated conditions across listeners |

When business logic needs to check permissions, call APIs, or read current state from a database, do not cram this logic into `condition`. Instead, keep the expression simple and perform the check in Java:

```java
// Integration illustration: notificationPolicy and notificationService
// are business dependencies to be provided in a real application.
@EventListener(condition = "#p0.newStatus().name() == 'PAID'")
public void notifyEligibleOrder(OrderStatusChanged event) {
    if (!notificationPolicy.canNotify(event.orderId())) {
        return;
    }
    notificationService.sendPaymentConfirmation(event.orderId());
}
```

The snippet above is an integration illustration, **not a standalone compilable class** without defining those dependencies. It shows the boundary: SpEL filters simple conditions; Java handles rules that vary with business state.

## 6. Listener State Filtering Does Not Replace Managing State Transitions

A listener only knows that an event was emitted; it does not prove on its own that the state transition was valid or durably persisted. In the service that updates order state, execute the proper sequence:

1. Read and lock/update the order using an appropriate concurrency mechanism.
2. Compare the old status and requested status; if unchanged, typically **do not emit** a status-changed event.
3. Validate state transition rules (for example, disallow `SHIPPED -> NEW`).
4. Persist the new status and publish `OrderStatusChanged` containing the **old/new status snapshot**.
5. Choose a listener mechanism appropriate for commit timing and required reliability.

Integration-style service code example (depending on `OrderRepository`, the `Order` entity, and actual business rules):

```java
@Transactional
public void updateStatus(String orderId, OrderStatus target) {
    Order order = repository.findByIdForUpdate(orderId)
            .orElseThrow();
    OrderStatus previous = order.getStatus();

    if (previous == target) {
        return;
    }

    validateTransition(previous, target);
    order.setStatus(target);
    repository.save(order);

    publisher.publishEvent(
            new OrderStatusChanged(orderId, previous, target));
}
```

In this integration example, `@Transactional` is applied via Spring transaction management; `findByIdForUpdate` and `validateTransition` are illustrative contracts defined by the project. If the repository uses optimistic locking or a different transaction type, the concurrency implementation must adapt accordingly.

**Timing note:** A synchronous `@EventListener` runs immediately at `publishEvent`, which may be before the enclosing transaction commits. If the listener sends an email or calls an external service, that side effect may already have occurred even if the transaction later rolls back.

For side effects that must wait for data persistence to succeed, switch to a transactional listener:

```java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Method inside a Spring bean; requires spring-tx and
// a transaction manager managing an actual transaction.
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.newStatus().name() == 'PAID'")
public void afterOrderPaid(OrderStatusChanged event) {
    // Example: emit a signal to start issuing an invoice.
}
```

Key points to remember:

- `AFTER_COMMIT` is the default phase of `@TransactionalEventListener`; you can choose `BEFORE_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION` for other purposes.
- By default, `fallbackExecution = false`: if no transaction is active at publish time, the transactional listener **does not run**. That is why the plain `main` example in section 4 uses `@EventListener`.
- `AFTER_COMMIT` indicates that the transaction committed; it does not mean the callback automatically has a new write transaction. If you need to write to the DB inside a post-commit listener, design an appropriate new transaction (typically `REQUIRES_NEW` in a Spring-managed service).
- Transaction-bound events are **not a durable queue**. When notifications must not be lost if the process dies or when reliable retries are needed, consider a transactional outbox paired with a worker/broker and idempotency mechanisms.

## 7. Testing State-Based Conditions

Split testing into two layers: **listener filtering** and **state transition policy**. For the example in section 4, the expected matrix is:

| Published event | `whenPaid` | `whenShipped` | `whenCancelled` |
| --- | --- | --- | --- |
| `NEW -> CONFIRMED` | No | No | No |
| `CONFIRMED -> PAID` | Yes | No | No |
| `PAID -> SHIPPED` | No | Yes | No |
| `NEW -> CANCELLED` | No | No | Yes |

Additional things to test:

- Events for two different `orderId`s do not mix data.
- Listeners produce no side effects when the state does not match; assert **invocation counts**, not just log contents.
- Same old/new state is ignored by the service; invalid transitions are rejected **before emitting** an event.
- If using `@TransactionalEventListener`, separately test **commit**, **rollback**, and **no transaction** scenarios. Do not use a test that only calls `publishEvent` outside a transaction to conclude that an `AFTER_COMMIT` callback is broken.
- When switching to `@Async`, verify concurrency, errors, and retries; do not rely on print order or synchronous completion anymore. Async listeners normally do not propagate exceptions back to the publishing thread.

## 8. Common Mistakes

1. **Using the entity's current state instead of the state at publish time.** The entity could be updated further before an async listener runs. Put immutable `oldStatus` and `newStatus` in the event.
2. **Checking only `newStatus` when the business rule needs to distinguish the transition source.** For example, refunding on `PAID -> CANCELLED` differs from cancelling before payment `NEW -> CANCELLED`; the condition needs to consider both.
3. **Relying on `#event` as a variable name without compiling to retain parameter names.** Use `#p0` or `#a0` for stability across build configurations.
4. **Writing overly long SpEL or depending on complex services.** Hard to test and debug; move multi-branch rules into a Java method/policy.
5. **Forgetting to distinguish `@EventListener` and `@TransactionalEventListener`.** One filters by content when the event is delivered; the other additionally binds execution to a transaction phase.
6. **Treating listeners as a guarantee of exactly-once processing.** Duplicate publications, retries, or application restarts require an `eventId`/idempotency key and persisted processing state if the business requires it.
7. **Assuming every listener always runs on the same thread.** Synchronous is the default, but a custom `ApplicationEventMulticaster` or `@Async` can change that. Do not rely on non-deterministic ordering across multiple listeners for the same event.

## 9. Project Application Checklist

- The event contains old status, new status, and object identifier in snapshot form.
- The publisher emits the event **after accepting a valid change**, not for no-ops.
- The `@EventListener(condition = ...)` expression accurately reflects the target state or state pair to observe.
- Simple conditions live in SpEL; complex business logic lives in testable Java code.
- Commit-dependent tasks use `@TransactionalEventListener` and are tested with real transactions.
- Critical side effects have appropriate error, retry/idempotency, and durability policies.

**Official documentation for reference:**

- [Spring Framework — ApplicationContext Events and `@EventListener`](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
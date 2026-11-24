# Avoiding Complex Conditions in Listeners (Spring Application Events)

## 1. The Problem to Solve

In Spring Framework, `@EventListener` accepts an event type and can declare a `condition` using the Spring Expression Language (SpEL) to run only when the condition is true. This is a useful filtering mechanism, but overly long expressions, querying data directly inside the expression, or chains of `if/else` branches inside the listener make code hard to read, test, and maintain.

A well-designed listener should clearly answer three questions: **Which event is relevant?** (event type), **when should it be handled?** (simple condition), and **what should be done?** (delegating to business logic with clear responsibility). Avoid turning a listener into the home for all business rules.

By default, Spring uses `SimpleApplicationEventMulticaster` and invokes listeners **synchronously on the event-publishing thread**. Therefore, time-consuming check expressions or slow processing logic will slow down the `publishEvent(...)` call as well. Filtering in the right place reduces overhead and clarifies behavior, though it does not replace asynchronous processing design when truly needed.

## 2. Recognizing When a Condition Is Too Complex

Common warning signs:

- `@EventListener(condition = "...")` contains many `&&`, `||`, nested branches, long property chains, or unpredictable `null` handling.
- The SpEL expression calls a bean to query a database, make an HTTP call, check permissions over the network, or perform side-effecting operations. When that happens, cost and failure points are hidden inside an annotation.
- A single listener accepts a very broad event and then uses many `if/else` branches to distinguish unrelated business cases.
- The same business condition is duplicated across multiple listeners; changing a rule requires editing multiple places.
- Behavior tests are forced to boot an entire Spring context just to test one long expression.

Having multiple conditions is not automatically wrong. The issue is whether the **complexity, cost, and responsibility** of the condition fit the event-filtering site.

## 3. Placing Each Kind of Condition in the Right Spot

| Condition type | Recommended organization | Reason |
| --- | --- | --- |
| Interested in only one event type | Parameter with a concrete type, e.g., `OrderPaidEvent` | Spring selects the matching listener automatically; no manual type checking needed |
| A simple flag or value on the event | `@EventListener(condition = "#a0.receiptRequested()")` or an early-return `if` | Readable and low overhead |
| Multi-branch business rules | A policy/service class with a clearly named method, called from the listener body | Easy to test and reuse |
| Filtering requiring data from DB/external services | Handle via a service with error, timeout, and transaction management; consider event publish timing | Do not hide I/O inside SpEL |
| Multiple independent actions | Separate listeners by responsibility or events with narrower semantics | Reduces `if/else` chains and coupling |

With `condition`, Spring evaluates the expression on each type-matched event before invoking the listener method. `#a0` (equivalent to `#p0`) is the first parameter; using this syntax does not depend on whether Java parameter names are retained in bytecode. `#root.event` references Spring's original event object; when the published event is a plain object, the listener parameter can be that object itself. Avoid writing `#event` when no parameter named `event` is provided.

## 4. Example: Filter Fast, Move Policy Out of the Listener

Requirement: When an order is paid, only send a receipt if the customer requested one and the amount is greater than 0. The two conditions play different roles:

1. `receiptRequested` is a simple flag and can be filtered right on `@EventListener`.
2. `amountCents() > 0` is an illustrative business rule placed in `ReceiptPolicy` so it can be tested independently.

The following example is **one complete Java 17+ file** running in a Spring Boot 3.x application depending on `spring-boot-starter`. Create the file `src/main/java/example/events/EventFilterApplication.java`:

```java
package example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class EventFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventFilterApplication.class, args);
    }

    // Event object does not have to extend ApplicationEvent.
    public record OrderPaidEvent(
            String orderId,
            boolean receiptRequested,
            long amountCents) {
    }

    public static class ReceiptPolicy {
        public boolean canSend(OrderPaidEvent event) {
            return event.amountCents() > 0;
        }
    }

    public static class ReceiptListener {
        private final ReceiptPolicy policy;

        public ReceiptListener(ReceiptPolicy policy) {
            this.policy = policy;
        }

        // Simple filter; no DB queries or external service calls.
        @EventListener(condition = "#a0.receiptRequested()")
        public void onOrderPaid(OrderPaidEvent event) {
            if (!policy.canSend(event)) {
                return; // Guard clause: skip invalid event.
            }
            System.out.println("Send receipt: " + event.orderId());
        }
    }

    @Bean
    ReceiptPolicy receiptPolicy() {
        return new ReceiptPolicy();
    }

    @Bean
    ReceiptListener receiptListener(ReceiptPolicy policy) {
        return new ReceiptListener(policy);
    }

    @Bean
    CommandLineRunner publishSampleEvents(ApplicationEventPublisher publisher) {
        return args -> {
            publisher.publishEvent(new OrderPaidEvent("OD-101", true, 12000));
            publisher.publishEvent(new OrderPaidEvent("OD-102", false, 8000));
            publisher.publishEvent(new OrderPaidEvent("OD-103", true, 0));
        };
    }
}
```

With a module configured with the Spring Boot Gradle plugin, run `./gradlew bootRun` (on Windows you can use `gradlew.bat bootRun`). In the startup log, there will be **only one line printed by the listener**:

```text
Send receipt: OD-101
```

Execution flow explanation:

- `OD-101`: matching event type, `receiptRequested() == true`, and `canSend(...) == true`, so the message is printed.
- `OD-102`: `condition` returns `false`; Spring does not invoke `onOrderPaid`.
- `OD-103`: `condition` is true; the listener is invoked, but `ReceiptPolicy` returns `false`, so it returns early and prints nothing.
- The example prints to console for easy verification; a real system would delegate sending the receipt to a dedicated service while handling errors and preventing duplicate sends.

The syntax `#a0.receiptRequested()` directly invokes the Java record accessor. If using a regular JavaBean with `getReceiptRequested()` or `isReceiptRequested()`, use the corresponding SpEL property access. Any rename of fields or methods must be verified by tests because SpEL strings are not type-checked by the Java compiler like direct method calls.

## 5. When Should You Drop SpEL Entirely?

When all conditions can be expressed clearly in Java, you can use `@EventListener` without `condition` and return early:

```java
@EventListener
public void onOrderPaid(OrderPaidEvent event) {
    if (!event.receiptRequested()) {
        return;
    }
    if (!policy.canSend(event)) {
        return;
    }
    System.out.println("Send receipt: " + event.orderId());
}
```

This is a **method replacement snippet** inside `ReceiptListener` in the example above, not a standalone Java program. The advantage is that conditions are type-checked by Java and easy to debug. In exchange, the listener is still invoked before checking the flag. Choose what is clearest for the team: `condition` suits small expressions, while `if`/guard clauses suit multi-step logic that benefits from direct testing.

If you are writing a chain of `if (event instanceof ...)` for different events, consider designing specific event types and splitting listeners by function before adding conditions.

## 6. Limits Regarding Performance, Transactions, and Errors

- **Synchronous path:** By default, `publishEvent(...)` waits for synchronous listeners to finish. Calling a repository or API inside `condition` or the listener body still consumes time on the publishing thread, even if the event ends up being skipped.
- **Asynchronous processing:** `@Async` can move heavy work off the publishing thread, but requires proper async configuration; exceptions in async listeners do not automatically propagate back to the caller of `publishEvent`. Transaction context and `ThreadLocal` are not transferred to another thread by default. Do not use `@Async` just to hide hard-to-read filter conditions.
- **After commit:** When an action must only run after a successful transaction, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` according to data consistency requirements. This annotation addresses **when** the event is received, not simplifying the policy; such listeners have specific behavior when no transaction is active.
- **Errors in conditions:** SpEL accessing a wrong property, calling a method on `null`, or calling a service that throws an error can cause event handling to fail. Conditions should rely on stable event data and avoid side effects.
- **Correctness:** Listeners are for reacting to events; do not put rules that are mandatory for a transaction to be allowed to succeed only inside a listener. Side effects such as sending emails need idempotent design to avoid duplicate processing if events are re-emitted or tasks retried.

## 7. Testing Conditions at Two Levels

First, test `ReceiptPolicy.canSend(...)` as a regular Java method without starting a Spring context. Then, use an integration test with a Spring context to verify that `@EventListener(condition = ...)` selects the right events.

| Data | Listener method invoked? | Action executed? |
| --- | --- | --- |
| `receiptRequested=true`, `amountCents=12000` | Yes | Yes |
| `receiptRequested=false`, `amountCents=8000` | No | No |
| `receiptRequested=true`, `amountCents=0` | Yes | No |

When adding policies for customers, permissions, or configuration, test the policy with boundary cases, missing data, and exceptions; in the integration test, only verify the wiring event → condition → listener → service. To evaluate performance, measure execution time in a real context and count I/O calls; do not judge solely from shorter-looking code.

## 8. Checklist Before Adding a Condition to a Listener

1. Is the event type specific enough, or is a single generic event causing excessive branching?
2. Can the `condition` expression be understood in a few seconds, reading only stable data with no I/O?
3. Does the business rule have a clear name and independent tests in a policy/service?
4. Can non-matching cases exit early without causing side effects?
5. Have you considered how default synchronous execution, errors, and transactions affect the publisher?
6. Are there tests covering the executed path, the filtered-out path, and the policy-rejected path?

**Practical guideline:** Use **event types** to filter by domain essence, **short SpEL or guard clauses** for simple checks, and **services/policies** to hold business decisions. The goal is readable conditions, verifiable behavior, and processing costs placed where they are easy to control.

*Reference:* [Spring Framework — ApplicationContext Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html).
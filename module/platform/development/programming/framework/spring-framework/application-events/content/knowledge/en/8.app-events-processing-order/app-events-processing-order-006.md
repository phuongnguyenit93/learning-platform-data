# Designing Order-Independent Listeners in Spring Framework Application Events

## 1. Objectives and Context

When a business operation emits an event, multiple components may react simultaneously: generating a receipt, updating statistics, sending notifications, or saving history. In Spring Framework, listeners annotated with `@EventListener` can receive the same event together. However, if listener B only works when listener A has run earlier and written intermediate data, the system has an **implicit ordering dependency**.

Designing order-independent listeners means: given the same valid event, **each listener has sufficient data and rules to process correctly regardless of whether it is invoked before or after another listener**. The outcome must not depend on bean registration order, `@Order`, or thread timing.

For example, `OrderPlacedEvent` has two consumers: one generates a receipt, and one records revenue metrics. Both must work under both the "receipt → metrics" order and the "metrics → receipt" order.

## 2. Understanding Invocation Order in Spring

`ApplicationEventPublisher.publishEvent(event)` publishes an event to listeners in the `ApplicationContext`. With the default configuration, Spring typically uses `SimpleApplicationEventMulticaster`, invoking listeners **synchronously on the publisher's thread**.

- `@Order` can adjust the **invocation priority** of listeners (smaller values take priority first). It should not be the contract guaranteeing business correctness.
- When a synchronous listener throws an exception, the default multicaster without an `ErrorHandler` can stop the dispatch cycle and propagate the error back to the publisher. Remaining listeners may not have been invoked yet.
- If `@Async` or an asynchronous executor is used, scheduling order does not equal completion order; tasks can overlap.
- `@Order` does not create a separate transaction, does not automatically add retries or idempotency, and does not ensure events are persisted for replay.

Thus, **independence in data and logic** differs from **error and runtime isolation**. Both must be designed if one failing task must not affect another.

## 3. Identifying an Order-Dependent Design

Suppose two listeners both receive `OrderPlacedEvent` yet use shared data:

```text
Listener A: calculates reward points; writes sharedPoints[orderId] = points
Listener B: reads sharedPoints[orderId]; uses points to issue a voucher
```

If B runs before A, the `points` value does not exist. Assigning `@Order(1)` to A and `@Order(2)` to B only masks the issue in the synchronous dispatch case. When parallel processing, retries, or configuration changes occur, the dependency can corrupt business logic.

Two cases must be distinguished:

1. **Two genuinely independent responsibilities:** A and B both take input from an immutable event or committed data source, and each handles its own part. Neither reads a temporary cache created by another listener.
2. **A genuine before–after relationship:** move the steps into an explicit application service/workflow, or publish a follow-up event after the previous step completes, such as `OrderPlaced → PointsCalculated → VoucherIssued`. Follow-up events express dependencies, yet require a reliable delivery mechanism if losing steps is unacceptable.

## 4. Design Principles

### 4.1. Define Events as Business Facts

Name events after **what happened**, such as `OrderPlacedEvent` or `PaymentConfirmedEvent`. The payload should be an immutable snapshot containing the data consumers genuinely need: business ID, stable `eventId`, amount, version, or timestamp when meaningful. With Java 17+, `record` is convenient for payloads consisting of immutable values.

Do not pass JPA entities that still have lazy loading or mutable objects for multiple listeners to modify concurrently. If a listener re-reads the DB via `orderId`, consider whether the data has already committed and whether a specific version is needed.

### 4.2. Each Listener Owns Its Own Side Effect

The receipt-generating listener manages receipt records; the statistics listener manages statistics records. No listener relies on temporary data just saved by another listener. Sharing a correlation ID for logging and tracing is reasonable; sharing a mutable variable to make decisions is not.

### 4.3. Idempotency and Duplicate Delivery

You must account for retries, application restarts, or the same logical event being re-delivered. A reliable listener needs to handle repeated processing without creating incorrect side effects:

- For DB operations, use a unique constraint on a business key (e.g., each `orderId` has at most one receipt) or on `(consumerName, eventId)`; place recording the processed status and modifying business data in the same transaction.
- For email/external APIs, use an idempotency key on the receiving side when possible, or use an outbox/job to track status, retries, and completion confirmation. Do not mark "sent successfully" before receiving a reliable result.
- When retrying the same logical event, keep the same `eventId`. Generating a different ID on each retry defeats event-based deduplication.

Idempotency does not mean Spring application events inherently have durable storage.

## 5. Standalone Runnable Java 17+ Example

This example uses Spring Context without Spring Boot or a database. Two listeners simply read the same immutable event and produce two distinct results, without using `@Order`.

Structure:

```text
independent-listeners/
├── build.gradle
└── src/main/java/demo/IndependentListenersExample.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.IndependentListenersExample'
}
```

Contents of `src/main/java/demo/IndependentListenersExample.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class IndependentListenersExample {

    public record OrderPlaced(String orderId, long totalCents) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ReceiptListener receiptListener() {
            return new ReceiptListener();
        }

        @Bean
        public MetricsListener metricsListener() {
            return new MetricsListener();
        }
    }

    public static class ReceiptListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("RECEIPT " + event.orderId());
        }
    }

    public static class MetricsListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "METRIC " + event.orderId() + " " + event.totalCents()
            );
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.publishEvent(new OrderPlaced("ORD-42", 19_900L));
        }
    }
}
```

With JDK 17+ and Gradle installed, run from the project directory:

```bash
gradle run --quiet
```

Two lines are printed (order may vary; do not assert on order):

```text
RECEIPT ORD-42
METRIC ORD-42 19900
```

`ReceiptListener` only needs `orderId`; `MetricsListener` only needs `orderId` and `totalCents`. Regardless of which is called first, the content of each line stays the same. `@Bean` registers the two listeners in the context, and Spring detects the `@EventListener` methods on the corresponding beans.

This is an example of **logical independence**. If you replace `System.out.println` with saving to a DB or calling an API, you need to add transactions, retries, and idempotency. If one handler throws an exception, the default synchronous dispatch mode can still affect the remaining handler.

## 6. Error Isolation: Do Not Confuse with Order Independence

The default `SimpleApplicationEventMulticaster` does not automatically catch and ignore every listener error. In synchronous dispatch, an unhandled runtime error can propagate back to the publisher and prevent subsequent listeners from running.

Choose a policy based on the nature of the task:

- **Retryable secondary task:** place error handling in the responsible service, log/emit metrics with `eventId`, schedule retries, and alert if retries are exhausted. Do not swallow errors and report false success.
- **Wanting the multicaster to keep invoking other consumers after an error:** consider configuring `SimpleApplicationEventMulticaster.setErrorHandler(...)`; understand that suppressing exceptions can leave the caller unaware that a consumer failed, so separate monitoring and recovery are required.
- **Task that can be processed later:** use `@Async` along with `@EnableAsync` and a managed executor, or switch to a durable queue if needed. Asynchronous listeners do not guarantee completion before `publishEvent` returns; exceptions are not propagated back to the caller the same way as synchronous listeners. You need an `AsyncUncaughtExceptionHandler` or appropriate error tracking mechanism.
- **Multiple steps that must succeed together:** perform intentional orchestration/transactions. Simple event fan-out is not an atomic coordination mechanism.

Listener slowness is also a form of coupling when using synchronous dispatch: a slow listener can block the publisher thread. Separate processing responsibilities and choose executors based on real requirements.

## 7. Transactions and Processing Timing

If a publisher emits an event inside a `@Transactional` service, a regular synchronous `@EventListener` may run **before the transaction commits**. Sending emails or calling external systems at that point risks creating side effects even if the original transaction rolls back.

When a task is only allowed to start after commit, use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. `AFTER_COMMIT` is the default phase of this annotation. If there is no active transaction, the listener **is not invoked**, unless `fallbackExecution = true` is used.

The example below is an illustrative method inside a Spring-managed bean, assuming the application has defined `OrderPlacedEvent` and `receiptJobService`:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void enqueueReceipt(OrderPlacedEvent event) {
    receiptJobService.enqueue(event.orderId());
}
```

The `AFTER_COMMIT` mechanism addresses **timing**, not guaranteeing that the process will not lose the event if the application crashes after commit yet before the side effect completes. If an after-commit listener needs to create a new DB record, use an appropriate new transaction (such as a service called via proxy with `REQUIRES_NEW`), rather than assuming the just-committed transaction can safely continue writing.

When you need to guarantee an event survives restarts, consider the **transactional outbox**: save the outbox record in the same transaction as the business data, have a worker forward records to a broker/consumer, and keep the receiving side idempotent with retries/monitoring. Regular application events are simply event dispatches within an application context, not a durable broker.

## 8. Properly Testing Independence

Do not test with the condition "the RECEIPT line must always appear before METRIC". Test business outcomes under different execution orders and modes.

| Scenario | How to Test | Expected Result |
| --- | --- | --- |
| Reversed order | Invoke two handlers/services in A→B and B→A order on two equivalent initial states | Same final result; neither needs temporary data from the other handler |
| Duplicate delivery | Process the same `eventId` twice | No invalid extra records or duplicate side effects created |
| One listener fails | Have one service throw an error and run with the chosen error-handling policy | Appropriate logging/retries occur; isolation of the remaining listener matches the design |
| Transaction rollback | Publish inside a rolled-back transaction and inspect the `AFTER_COMMIT` listener | Post-commit-only work does not run |
| Asynchronous execution | Intentionally vary completion order, wait using test synchronization | Final result is correct; does not rely on arbitrary sleep durations |

Extract business logic into directly callable services to test order swapping. Integration tests with `ApplicationContext` verify event registration and dispatch; DB/API tests verify real idempotency constraints, transactions, and retries.

## 9. Common Mistakes

1. **Using `@Order` to turn a business dependency into timing luck.** If B needs A's output, express the A→B step explicitly.
2. **Letting multiple listeners modify a shared mutable object or shared cache.** This is a source of implicit dependencies and race conditions.
3. **Assuming every listener is guaranteed to be called even if another listener throws an error.** The default synchronous multicaster can halt dispatch.
4. **Assuming `@Async` guarantees independence.** Completion order becomes even less predictable; error handling, executors, and observability are still required.
5. **Sending external side effects before commit.** The originating transaction may roll back after the email has already been sent.
6. **Treating `@TransactionalEventListener` as a durable queue.** This annotation only binds timing to the transaction.
7. **Deduplicating with an in-memory Map.** Restarts or multiple instances lose or fragment state.
8. **Testing log order instead of business state.** Such tests easily pass in one environment and fail in another.

## 10. Review Checklist

- Can each listener run before the other listeners and still produce the right result?
- Does input data come from an immutable event or a committed source with an appropriate version?
- Does any listener rely on another listener's side effect as a precondition to proceed?
- Are idempotency keys, transactions, and retries commensurate with each side effect?
- Is the behavior defined when one listener fails, is slow, or finishes after the others?
- For after-commit/async events, have thread context, durability, and potential event loss been considered?
- Do tests cover order reversal, duplicates, errors, rollbacks, and async execution where applicable?

**Guiding principle:** multiple listeners hearing the same business fact should be autonomous consumers. If one step must wait for another step's result, model that flow explicitly and control its errors and recovery.

## References

- [Spring Framework — ApplicationContext Events, @EventListener, @Order, and @Async](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)

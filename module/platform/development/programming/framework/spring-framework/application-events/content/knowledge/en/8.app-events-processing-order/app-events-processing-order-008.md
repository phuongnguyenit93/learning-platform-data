# Testing Order When Business Logic Genuinely Requires It

In Spring Framework Application Events, a single event can be handled by multiple listeners. Occasionally, business logic has a genuine dependency: *confirming the reservation* must happen before *sending a reservation-confirmed notification*. In such cases, tests need to prove that the order matters to the business outcome. If listeners are independent (recording metrics, sending secondary notifications, updating counters), pinning invocation order often makes tests brittle and couples components unnecessarily.

This lesson focuses on defining ordering contracts, writing observable tests with Spring Test + JUnit 5, and distinguishing listener invocation order from processing completion when asynchrony or transactions are involved.

## 1. Decide First: Does Business Logic Truly Require Ordering?

| Scenario | Should you test ordering? | What must be guaranteed |
| --- | --- | --- |
| Listener A sets state `RESERVED`, listener B may only notify when that state exists | **Yes**, if the system intentionally uses the same event and synchronous processing | B does not succeed before A establishes the state |
| Listener A records metrics, listener B writes independent audit logs | **No** | Each required side effect occurs; no coupling between A and B |
| Send email after order data has committed | **Test transaction phase**, not merely `@Order` | Send only after successful commit; do not send on rollback |
| Two listeners run via `@Async` or a shared executor | **Do not test by arbitrary completion order** | Test synchronization conditions or asynchronous processing contracts |
| Two application instances receive events via a message broker | **Do not use `@Order` to promise system-wide order** | Use a mechanism with ordering guarantees/business keys and idempotency as needed |

Decisive question: **If A and B were swapped and the data, decisions, or business rules remained valid, is there any reason to make the test fail?** If not, test each listener's outcome individually.

Example with a genuine dependency:

1. When the system receives `PaymentCaptured(orderId)`, listener A marks the order as reserved.
2. Listener B checks that it has been reserved before recording the notification.
3. Acceptance requirement: the notification is created only when reservation succeeds.

In this example, we can verify ordering **within a single synchronous event publication**. In real systems, if two steps form a mandatory workflow, an explicit orchestrating service or a follow-up event like `ReservationCompleted` usually makes the dependency clearer than relying long-term on listener priority.

## 2. The `@Order` Mechanism and Scope of Its Guarantee

By default, Spring ApplicationContext uses `SimpleApplicationEventMulticaster` to publish events **synchronously on the publisher's thread**, when no asynchronous executor is configured. For listeners receiving **the same event type** in the same dispatch cycle:

- `@EventListener` marks the event-receiving method.
- `@Order(10)` takes priority before `@Order(20)`: **smaller numbers are invoked first**.
- `@Order` on an `@EventListener` method controls the corresponding invocation order; it does not create a transaction and does not turn multiple listeners into an atomic operation.
- When a listener throws an error in default synchronous mode and no error handler swallows it, the error can propagate back to the publisher; subsequent listeners may not be invoked. Therefore, tests should also reflect expected error-handling behavior.

The scope above changes when `@Async` is enabled, a `TaskExecutor` is configured on the multicaster, `@TransactionalEventListener` is applied, or multiple publishers/threads publish concurrently. **Start/invocation order does not mean task completion order**, and ordering within one JVM does not guarantee cross-process order.

## 3. Writing Test Conditions Around Observable Behavior

Write the contract in *Given – When – Then*:

- **Given:** A reservation listener `@Order(10)` and a notification listener `@Order(20)`; both are managed by Spring in a synchronous context.
- **When:** A `PaymentCaptured("O-42")` is published.
- **Then:** The system records `reserved:O-42` before `notified:O-42`, and the notification listener confirms that the reserved state already exists.

You should verify **both the business outcome and the meaningful sequence of steps**. Tests that merely do `verify(listenerA)` then `verify(listenerB)` do not necessarily prove order; tests that only count events also do not prove listener order.

## 4. Spring + JUnit 5 Integration Test Example

The following Java 17+ example is **a complete test file**, without needing a Spring Boot application. Place it at `src/test/java/example/events/ListenerOrderTest.java`. The test project requires Spring Context, Spring Test, and JUnit Jupiter; `SpringJUnitConfig` integrates Spring TestContext with JUnit 5.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ListenerOrderTest.TestConfig.class)
class ListenerOrderTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    Trace trace;

    @Test
    void reservationMustPrecedeNotification() {
        publisher.publishEvent(new PaymentCaptured("O-42"));

        assertEquals(
            List.of("reserved:O-42", "notified:O-42"),
            trace.steps()
        );
    }

    record PaymentCaptured(String orderId) { }

    static class Trace {
        private final List<String> steps = new ArrayList<>();
        private final Set<String> reservedOrders = new HashSet<>();

        void reserve(String orderId) {
            reservedOrders.add(orderId);
            steps.add("reserved:" + orderId);
        }

        void notifyIfReserved(String orderId) {
            if (!reservedOrders.contains(orderId)) {
                throw new IllegalStateException(
                    "Cannot notify before reservation: " + orderId
                );
            }
            steps.add("notified:" + orderId);
        }

        List<String> steps() {
            return List.copyOf(steps);
        }
    }

    static class BusinessListeners {
        private final Trace trace;

        BusinessListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        @Order(10)
        public void reserve(PaymentCaptured event) {
            trace.reserve(event.orderId());
        }

        @EventListener
        @Order(20)
        public void notifyCustomer(PaymentCaptured event) {
            trace.notifyIfReserved(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        BusinessListeners businessListeners(Trace trace) {
            return new BusinessListeners(trace);
        }
    }
}
~~~

**How to run:** in a Gradle project configured with the test dependencies above and using JUnit Platform, run:

~~~bash
./gradlew test --tests "example.events.ListenerOrderTest"
~~~

On Windows PowerShell, you can use `./gradlew.bat` instead of `./gradlew`. When all dependencies and test configurations are correct, the test **passes**; the program does not print `reserved:...` or `notified:...` to stdout, because those two values are stored in `Trace` and compared via assertion.

**Why does this test properly verify ordering?**

1. `@SpringJUnitConfig` creates a real context; `BusinessListeners` is a bean with two `@EventListener` methods.
2. `publishEvent` sends an event of the right type to the default synchronous multicaster; the test does not manually invoke the two listeners in the desired order.
3. `@Order(10)` causes `reserve` to be invoked before `notifyCustomer`'s `@Order(20)`.
4. `notifyIfReserved` contains the business condition: if the order is inverted, the method throws `IllegalStateException`; the test fails.
5. `assertEquals` additionally checks the observable trace, catching missing or duplicate step invocations.

To test the sensitivity of the test, temporarily swap `@Order(10)` and `@Order(20)`: with the default synchronous multicaster, the notification listener will encounter an unreserved state and make the test fail. Revert the change after verifying. This helps confirm that the assertion protects a real business dependency rather than always passing.

Note: `Trace` intentionally uses `ArrayList` and `HashSet` to keep the example simple and is only suitable for the synchronous execution flow described above. If switching to asynchronous execution, these structures and the entire testing approach must be redesigned for thread safety.

## 5. When There Is No Order Dependency: Test What Must Be True

Suppose one listener updates metrics and another writes audit logs. No rule forces metrics to finish before audit logs. In that case:

- Check the count/values of metrics and audit logs actually created.
- Check that one publication produces the right events, without unintended duplicates.
- Do not assert `List.of("metric", "audit")`, and do not pin `@Order` numbers just to stabilize the test.

Spring TestContext provides `@RecordApplicationEvents` and `ApplicationEvents` to record **published events** in each test. Example snippet placed inside a Spring-configured test class:

~~~java
@RecordApplicationEvents
@SpringJUnitConfig(TestConfig.class)
class PublicationTest {
    @Autowired
    ApplicationEventPublisher publisher;

    @Test
    void publishesOnePaymentEvent(ApplicationEvents events) {
        publisher.publishEvent(new PaymentCaptured("O-42"));

        assertEquals(1, events.stream(PaymentCaptured.class).count());
    }
}
~~~

The snippet above **illustrates the idea**, not a standalone file: you need to define `TestConfig`, `PaymentCaptured`, and import classes as in the previous example, along with `org.springframework.test.context.event.ApplicationEvents` and `org.springframework.test.context.event.RecordApplicationEvents`. It proves that one event was published, **not that listener A ran before B**. For listeners with side effects, separate assertions on the state/interactions of those side effects are needed.

## 6. Asynchronous Cases: Do Not Infer Completion Order from `@Order`

When a listener method has `@Async` (with async support enabled), or `SimpleApplicationEventMulticaster` uses an executor, dispatch can cause the work to execute on another thread. **Do not assume that a listener with `@Order(10)` will finish before a listener with `@Order(20)`**.

A test like the one below is unreliable:

~~~java
publisher.publishEvent(new PaymentCaptured("O-42"));
assertEquals(List.of("reserved:O-42", "notified:O-42"), trace.steps());
// May assert before the task finishes, or be affected by the scheduler.
~~~

With async processing, test according to the real contract:

- If two tasks are independent: use a waiting mechanism with a bounded timeout (`CountDownLatch`, `CompletableFuture`, or dedicated test utilities) and assert **both results**, without checking completion order.
- If B depends on A's output: model the dependency with an explicit processing chain—for example, A finishes then publishes `ReservationCompleted` to trigger B, or use an orchestrating service; then test that B does not run before the readiness condition is met.
- Do not use `Thread.sleep(...)` to "stabilize" ordering: sleep does not establish a happens-before relationship under business contracts and easily creates flaky tests under heavy CI load.
- Async tests must explicitly observe exceptions and timeouts. Exceptions in async listeners do not automatically propagate back to the publish call; do not treat a normal return from publish as proof that listeners succeeded.

If multiple threads publish concurrently, even when listeners in **each individual** dispatch are synchronous, steps from two different events can still interleave. You must inspect by `orderId`/correlation ID and design appropriate data constraints; do not impose a global event sequence.

## 7. Transaction Cases: Testing Commit/Rollback Timing

`@TransactionalEventListener` binds processing to a transaction phase. The default is `TransactionPhase.AFTER_COMMIT`; others include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. If no appropriate transaction is active, the listener generally does not run unless `fallbackExecution = true` is enabled.

Example of a listener sending notifications after commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendAfterCommit(PaymentCaptured event) {
    notificationSink.send(event.orderId());
}
~~~

This is a **method snippet** inside a Spring bean, requiring imports for `TransactionalEventListener` and `TransactionPhase`. In an integration test with a real transaction manager, the test should observe:

1. While **inside** the transaction, the notification has not been sent yet.
2. After a successful commit, the notification is sent exactly once.
3. After a rollback, the notification is not sent.

One way to control completion timing in tests is using `TransactionTemplate` (snippet inside a test with `transactionTemplate`, `publisher`, and `notificationSink` injected):

~~~java
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new PaymentCaptured("O-42"));
    assertEquals(0, notificationSink.count());
});
assertEquals(1, notificationSink.count()); // After commit.

notificationSink.reset();
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new PaymentCaptured("O-43"));
    status.setRollbackOnly();
});
assertEquals(0, notificationSink.count()); // Rollback does not trigger AFTER_COMMIT.
~~~

This snippet describes a **test scenario**, not a standalone program. It assumes an active transaction manager and an observable test double `notificationSink`. In Spring tests with `@Transactional` on the test method itself, Spring TestContext normally rolls back by default at the end; `AFTER_COMMIT` callbacks therefore **do not run as in a committed case**. Simply placing `@Commit` on the test method also does not let assertions running **inside** the method observe the post-commit moment; explicitly conclude the transaction with an appropriate test utility (such as `TestTransaction`) or use `TransactionTemplate` in a test not wrapped by a test-managed transaction.

`@Order` can participate in sorting listeners at the same appropriate processing point, but **do not use priority ordering to replace the "after commit" guarantee**. Comparing a regular listener with an `AFTER_COMMIT` listener using only `@Order` numbers is out of scope.

## 8. Choosing the Right Test Level

| Test Level | What to Verify | What to Avoid |
| --- | --- | --- |
| Listener unit test | One listener respects preconditions, updates state properly, handles errors properly | Unit testing two methods by calling them manually and concluding Spring orders them properly |
| Integration test with Spring Context | `@EventListener`, `@Order`, actual multicaster, and business outcome within a single publish | Mocking the entire dispatch mechanism, leaving configuration untested |
| Integration test with transactions | Not sent before commit, sent after commit, not sent after rollback | Confusing default test rollback with an actual commit |
| Async/concurrency test | Bounded-timeout completion, proper dependency relationships, no lost/duplicated effects | Relying on sleep, thread speed, or unstable log order |
| End-to-end across broker/multiple instances | Ordering contracts by business key, retries, and idempotency | Extrapolating local `@Order` to system-wide ordering |

If you only want to check that **the publisher emitted the event**, `@RecordApplicationEvents` is the right tool. If you want to prove **which listener ran first**, you must observe actual listener behavior through a context with the corresponding dispatch configuration. If you want to prove **business invariants**, asserting on post-processing data/state is the main focus.

## 9. Common Mistakes and How to Avoid Them

**1. Locking the order of every listener because "`@Order` exists".** Adding a new listener can break tests even when the business outcome remains valid. Only assert pairs of actions whose dependency has been analyzed.

**2. Testing order by manually calling A then B.** That verifies test code, not `ApplicationEventMulticaster`. Publish through `ApplicationEventPublisher` in a context with real listener beans.

**3. Using `@RecordApplicationEvents` to draw conclusions about execution order.** It records **published events**; listeners for the same event are not represented as an "A before B" sequence in that API.

**4. Assuming `@Order` resolves data contention.** It does not acquire locks, does not establish cross-thread coordination, does not guarantee successful execution, and does not handle retries.

**5. Confusing commit with regular listener invocation timing.** Testing transaction callbacks requires controlling commit/rollback, transaction manager configuration, and the corresponding phase.

**6. Assertions depending on timestamps/logs.** Close timestamps, clock resolution, and log buffering can all introduce noise. Observe business data or an event-keyed trace right at the point of state change.

**7. Not testing error branches.** For mandatory dependencies, test when the preparatory listener fails: notifications must not be emitted as if the flow succeeded. If errors must be recovered via retries/idempotency, that is a separate contract to test.

## 10. Checklist Before Keeping an Order Test in the Codebase

- Can you state the business reason forcing A before B in a single testable sentence?
- Does the test publish through a real Spring context and explicitly know whether the multicaster runs synchronously or asynchronously?
- Does the test observe outcomes and preconditions rather than depending on the order of independent steps?
- Are there dedicated tests/designs for transactions, threads, or brokers if those boundaries exist?
- Does the test fail meaningfully when the required order is reversed, and still pass when unrelated listeners are changed?
- If the dependency is critical, have you considered explicit orchestration or follow-up events instead of relying solely on `@Order`?

**Remember:** order testing exists to protect **business rules**, not an incidental framework ordering. In a synchronous model, `@Order` can be verified with a clean integration test; when moving to async, transactions, or multiple processes, contracts and tests must align with the corresponding guarantee mechanisms.

## References

- [Spring Framework – Application Events and ordering listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework TestContext – Recording Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

# Testing Listener Ordering in Spring Framework Application Events

## 1. Goal: Testing Which Order, and Under What Conditions?

Spring allows multiple listeners to subscribe to the same event. For example, an `OrderPlaced` event may be sent to three listeners:

- `ValidateListener` checks additional conditions;
- `AuditListener` records an audit trail;
- `NotificationListener` prepares a notification.

If all three are regular `@EventListener`s running under the **default synchronous** multicaster, the application can use `@Order` to determine **listener invocation order**. However, a proper test suite must not conflate three distinct concepts:

1. **The order in which Spring selects and invokes listeners** — related to `@Order`, `Ordered`, and the listener registry.
2. **The order in which work actually completes** — which can differ when listeners run with `@Async`, an executor, or spawn tasks themselves.
3. **Transaction phase ordering** — `@TransactionalEventListener` listeners may execute at `BEFORE_COMMIT`, `AFTER_COMMIT`, or `AFTER_ROLLBACK`, not immediately at `publishEvent`.

This article shows how to test all three, with **Java 17+ / Spring Framework 6.2** and **JUnit 5** examples. Most importantly: write tests against a Spring-guaranteed contract, not accidental reflection ordering, class names, component scan order, or thread speeds.

## 2. `@Order` Rules for Synchronous Event Listeners

Spring supports placing `@Order` on `@EventListener` methods:

~~~java
@EventListener
@Order(-20)
public void validate(OrderPlaced event) {
    // Higher-priority listener.
}

@EventListener
@Order(0)
public void audit(OrderPlaced event) {
    // Runs after listener with order -20, if synchronous.
}

@EventListener
@Order(20)
public void notifyCustomer(OrderPlaced event) {
    // Runs after listener with order 0, if synchronous.
}
~~~

The code snippet above only illustrates the annotations and assumes `OrderPlaced` and a bean containing the methods already exist.

**Smaller `order` values mean higher priority.** Negative values are valid. For listeners of the same event type under the same default synchronous multicaster, the expected order is:

~~~text
@Order(-20) -> validate
@Order(0)   -> audit
@Order(20)  -> notifyCustomer
~~~

Points to understand clearly:

- Without `@Order`, a listener typically receives the default priority equivalent to `Ordered.LOWEST_PRECEDENCE`; **do not test exact ordering** among listeners sharing the default level.
- If **two listeners share the same `order`**, do not rely on bean registration position or how reflection discovers methods as a stable ordering guarantee.
- You can implement the `Ordered` interface (especially for listeners implementing `ApplicationListener`) to declare priority; for `@EventListener` methods, `@Order` is the intuitive way.
- `@Order` controls **invocation priority**; it does not guarantee a transaction committed, create business dependencies, or wait for async work to finish.
- Ordering behavior must be verified against the **actual multicaster configuration**. Spring defaults to synchronous `SimpleApplicationEventMulticaster`; an application may swap in a custom multicaster.

**Do not use `@Order` to mask a mandatory dependency chain** such as "audit must commit before email can be sent." When such dependencies exist, model explicit business orchestration or durable steps; listeners are best suited for relatively independent subscribers.

## 3. Why Test Against a Real ApplicationContext?

A unit test that simply calls in sequence:

~~~java
validationListener.onOrderPlaced(event);
auditListener.onOrderPlaced(event);
notificationListener.onOrderPlaced(event);
~~~

does not verify whether Spring orders listeners properly. It only verifies the order **the test itself called**.

To test what truly matters, create an `ApplicationContext` containing the listeners, call:

~~~java
context.publishEvent(new OrderPlaced(101L));
~~~

and record invocation history into a test-controlled collector. That exercises `ApplicationEventPublisher`, `ApplicationEventMulticaster`, and the `@EventListener` adapters.

An easy-to-assert result:

~~~text
validate:101
audit:101
notify:101
~~~

With the default synchronous multicaster, `publishEvent(...)` does not return until synchronous listeners finish (unless an exception aborts the chain). Therefore, right after the publisher call, the test can assert the full list **without needing `Thread.sleep()`**.

To avoid noisy tests:

- Define a dedicated event for the test, e.g., `OrderPlaced`, rather than capturing every `ApplicationEvent` in a shared listener.
- Create a fresh context per test or explicitly reset the collector between publishes.
- Do not mix startup events like `ContextRefreshedEvent` into the compared history.
- Do not assert ordering among listeners **without distinct priority values**.
- Do not use elapsed milliseconds to infer invocation order.

## 4. Runnable Java 17+ Project: Main Class and JUnit Tests

This example uses Spring Framework **6.2.19**, JUnit Jupiter **5.12.2**, Gradle, and Java 17+. No Spring Boot or database is needed. The project demonstrates three branches:

1. Three synchronous listeners with distinct `@Order` values.
2. The first synchronous listener throws an exception, halting the multicast before later listeners by default.
3. An `@Async` listener is **scheduled** by priority yet can **complete** after a lower-priority synchronous listener.

### Structure

~~~text
listener-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ListenerOrderDemo.java
    └── test/java/demo/ListenerOrderDemoTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'listener-order-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ListenerOrderDemo'
}

test {
    useJUnitPlatform()
}
~~~

Use Gradle 8.x and JDK 17+ or an appropriate Gradle Wrapper. This example uses no Spring Boot APIs, so there are no Boot dependencies.

### src/main/java/demo/ListenerOrderDemo.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class ListenerOrderDemo {

    private ListenerOrderDemo() {}

    public record OrderPlaced(long orderId) {}
    public record FailureEvent() {}
    public record AsyncEvent() {}

    // Collector usable from both publisher and worker threads.
    public static final class CallLog {
        private final CopyOnWriteArrayList<String> calls =
            new CopyOnWriteArrayList<>();

        public void add(String value) {
            calls.add(value);
        }

        public List<String> snapshot() {
            return List.copyOf(calls);
        }

        public void clear() {
            calls.clear();
        }
    }

    // --- Group 1: synchronous listeners, ordered by @Order ---

    @Configuration
    public static class OrderedConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        ValidateListener validateListener(CallLog log) {
            return new ValidateListener(log);
        }

        @Bean
        AuditListener auditListener(CallLog log) {
            return new AuditListener(log);
        }

        @Bean
        NotifyListener notifyListener(CallLog log) {
            return new NotifyListener(log);
        }
    }

    public static class ValidateListener {
        private final CallLog log;

        public ValidateListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-20)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("validate:" + event.orderId());
        }
    }

    public static class AuditListener {
        private final CallLog log;

        public AuditListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(0)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("audit:" + event.orderId());
        }
    }

    public static class NotifyListener {
        private final CallLog log;

        public NotifyListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(20)
        public void onOrderPlaced(OrderPlaced event) {
            log.add("notify:" + event.orderId());
        }
    }

    // --- Group 2: synchronous listener exception ---

    @Configuration
    public static class FailureConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        FirstFailingListener firstFailingListener(CallLog log) {
            return new FirstFailingListener(log);
        }

        @Bean
        LateListener lateListener(CallLog log) {
            return new LateListener(log);
        }
    }

    public static class FirstFailingListener {
        private final CallLog log;

        public FirstFailingListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(-10)
        public void onFailure(FailureEvent event) {
            log.add("first-throws");
            throw new IllegalStateException("simulated failure");
        }
    }

    public static class LateListener {
        private final CallLog log;

        public LateListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(10)
        public void onFailure(FailureEvent event) {
            log.add("late");
        }
    }

    // --- Group 3: @Async makes completion order differ from invocation order ---

    public static final class Gates {
        public final CountDownLatch started = new CountDownLatch(1);
        public final CountDownLatch release = new CountDownLatch(1);
        public final CountDownLatch completed = new CountDownLatch(1);
    }

    @Configuration
    @EnableAsync
    public static class AsyncConfig {
        @Bean
        CallLog callLog() {
            return new CallLog();
        }

        @Bean
        Gates gates() {
            return new Gates();
        }

        @Bean(name = "taskExecutor")
        ThreadPoolTaskExecutor taskExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("listener-");
            return executor;
        }

        @Bean
        AsyncFirstListener asyncFirstListener(CallLog log, Gates gates) {
            return new AsyncFirstListener(log, gates);
        }

        @Bean
        SyncLaterListener syncLaterListener(CallLog log) {
            return new SyncLaterListener(log);
        }
    }

    public static class AsyncFirstListener {
        private final CallLog log;
        private final Gates gates;

        public AsyncFirstListener(CallLog log, Gates gates) {
            this.log = log;
            this.gates = gates;
        }

        @Async
        @EventListener
        @Order(-50)
        public void onAsyncEvent(AsyncEvent event) {
            gates.started.countDown();
            try {
                if (!gates.release.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("release timed out");
                }
                log.add("async");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            } finally {
                gates.completed.countDown();
            }
        }
    }

    public static class SyncLaterListener {
        private final CallLog log;

        public SyncLaterListener(CallLog log) {
            this.log = log;
        }

        @EventListener
        @Order(50)
        public void onAsyncEvent(AsyncEvent event) {
            log.add("sync");
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderedConfig.class)) {

            CallLog log = context.getBean(CallLog.class);
            context.publishEvent(new OrderPlaced(101L));

            log.snapshot().forEach(System.out::println);
        }
    }
}
~~~

### src/test/java/demo/ListenerOrderDemoTest.java

~~~java
package demo;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ListenerOrderDemoTest {

    @Test
    void invokesSynchronousListenersInOrder() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.OrderedConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            context.publishEvent(new ListenerOrderDemo.OrderPlaced(101L));

            assertEquals(
                List.of("validate:101", "audit:101", "notify:101"),
                log.snapshot()
            );
        }
    }

    @Test
    void preservesConfiguredOrderForEachPublishedEvent() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.OrderedConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            context.publishEvent(new ListenerOrderDemo.OrderPlaced(1L));
            context.publishEvent(new ListenerOrderDemo.OrderPlaced(2L));

            assertEquals(
                List.of(
                    "validate:1", "audit:1", "notify:1",
                    "validate:2", "audit:2", "notify:2"
                ),
                log.snapshot()
            );
        }
    }

    @Test
    void failingSynchronousListenerStopsLaterListenerByDefault() {
        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.FailureConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);

            assertThrows(
                IllegalStateException.class,
                () -> context.publishEvent(
                    new ListenerOrderDemo.FailureEvent())
            );

            assertEquals(
                List.of("first-throws"),
                log.snapshot()
            );
        }
    }

    @Test
    void asyncPriorityDoesNotGuaranteeCompletionOrder()
            throws InterruptedException {

        try (var context = new AnnotationConfigApplicationContext(
                ListenerOrderDemo.AsyncConfig.class)) {

            var log = context.getBean(ListenerOrderDemo.CallLog.class);
            var gates = context.getBean(ListenerOrderDemo.Gates.class);

            try {
                context.publishEvent(new ListenerOrderDemo.AsyncEvent());

                // Wait to confirm the async method actually started.
                assertTrue(gates.started.await(10, TimeUnit.SECONDS));

                // Async listener is waiting for release.
                // Sync listener was invoked later yet finished first.
                assertEquals(List.of("sync"), log.snapshot());
            } finally {
                // Always open the gate so the test does not leave the executor hanging.
                gates.release.countDown();
            }

            assertTrue(gates.completed.await(10, TimeUnit.SECONDS));
            assertEquals(List.of("sync", "async"), log.snapshot());
        }
    }
}
~~~

### Running and Comparing

~~~bash
gradle test
gradle run --quiet
# If Gradle Wrapper is present: ./gradlew test
# On Windows if wrapper is present: gradlew.bat test
~~~

`gradle test` must complete successfully with **4 passing tests**, not merely "printing nothing." If any fail, inspect the test report at `build/reports/tests/test/index.html`. The `System.out` lines printed by `main` when running `gradle run --quiet`:

~~~text
validate:101
audit:101
notify:101
~~~

The third test result proves that **a synchronous exception can interrupt multicast** under the default configuration. The fourth test **deliberately blocks** the `async` listener with a `CountDownLatch` to demonstrate that a higher-priority listener can **finish after** another listener; it does not claim every async run always produces this order.

**Limitation:** this code is written to run with the listed dependencies; Gradle's `gradle test` output also depends on environment, cache, and Gradle version. Spring lifecycle logs or executor logs are not treated as part of verified stdout. In real systems, pin dependencies/Gradle Wrapper via the project's build process.

## 5. Analyzing the Four Tests: What Is Being Proven?

### Test 1 — Invocation Order When Synchronous

Two factors combine:

- Spring sorts listeners with `@Order(-20)`, `@Order(0)`, and `@Order(20)`.
- The default multicaster invokes listeners on the same thread as `publishEvent`.

Therefore, once `publishEvent` returns, the list already holds all three entries in order. The test uses `assertEquals(List.of(...), ...)`, not an unordered collection like `Set`.

### Test 2 — Two Events Do Not Interleave History in Synchronous Mode

When publishing `OrderPlaced(1)` and then `OrderPlaced(2)` on the same thread, each call must complete its synchronous listener chain before the next publish method runs. The expectation is:

~~~text
validate:1, audit:1, notify:1,
validate:2, audit:2, notify:2
~~~

If a listener itself emits **nested events** or the application publishes concurrently across threads, global ordering can differ; do not generalize this test to all architectures.

### Test 3 — Exceptions Can Interrupt Subsequent Listeners

With the default `SimpleApplicationEventMulticaster` **without an ErrorHandler**, an exception from a synchronous listener propagates back to the publisher and can prevent remaining listeners from running. Thus:

~~~text
first-throws
# No "late".
~~~

Do not write a reverse test claiming "all listeners always run even when an earlier listener failed." If the application configures an `ErrorHandler` to **log and suppress** exceptions, both error propagation and subsequent callbacks change. Test against your real configuration, and remember that suppressing an error does not automatically mean business processing succeeded.

### Test 4 — `@Async` Changes Completion Order

`AsyncFirstListener` has `@Order(-50)` and `SyncLaterListener` has `@Order(50)`. Spring can invoke the async adapter first; that adapter hands work to the executor and returns. In the test, the async listener starts yet **waits on a `release` gate**, so the synchronous listener finishes first. Once the test opens the gate, async completes.

Lesson: `@Order` in an async setup is not a "barrier" forcing later listeners to **wait** for earlier ones to finish.

When testing async, use:

- `CountDownLatch` or a timeout-bounded completion signal;
- `CompletableFuture` and appropriate `await` if the listener/API returns a result;
- concurrency testing utilities such as Awaitility when already used by the project;
- assertions on **result sets** or genuinely guaranteed dependencies, rather than forcing an uncontracted total order.

**Avoid `Thread.sleep(1000)`**: varying CI machine speeds produce *flaky* tests. A latch with an explicit timeout provides much more reliable observation.

## 6. How to Test When Two Listeners Share the Same `@Order`?

Suppose:

~~~java
@EventListener
@Order(10)
void handleA(OrderPlaced e) { ... }

@EventListener
@Order(10)
void handleB(OrderPlaced e) { ... }
~~~

Both share the same priority level. Spring may keep actual order consistent within **a specific run**, yet you have **no strong contract** to assert A always precedes B across every configuration or version.

If **order is not required**, assert both executed:

~~~java
assertEquals(
    Set.of("A", "B"),
    new HashSet<>(log.snapshot())
);
~~~

This is an **illustrative JUnit snippet** requiring `Set`, `HashSet`, and `log`. Use this only if each listener is invoked once: comparing `Set`s can hide duplicate calls, so when exact count matters, add `assertEquals(2, log.snapshot().size())`.

If **order is required**, assign distinct priorities and test explicitly:

~~~java
@Order(10)  // A first
@Order(20)  // B second
~~~

If B depends on data committed by A, `@Order` may still be insufficient; move the dependency into service orchestration, transaction boundaries, or an appropriate workflow.

## 7. Testing `@TransactionalEventListener`: Phase Matters More Than Order Number

`@TransactionalEventListener` differs from a regular `@EventListener`. Its method **is bound to a transaction phase**, for example:

~~~java
// Illustrative methods requiring beans, transaction manager,
// and appropriate Spring transaction imports.
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
@Order(-10)
public void beforeA(OrderPlaced event) {
    steps.add("before-A");
}

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
@Order(10)
public void beforeB(OrderPlaced event) {
    steps.add("before-B");
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(-10)
public void afterA(OrderPlaced event) {
    steps.add("after-A");
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
public void afterB(OrderPlaced event) {
    steps.add("after-B");
}
~~~

A test **with a real imperative transaction** can expect:

~~~text
before-A
before-B
# Database commit succeeds
after-A
after-B
~~~

Keep in mind:

1. `@Order` can order callbacks **within the same phase group** (and relative to other transaction synchronizations by order). Do not use `order=-10` on `AFTER_COMMIT` to expect it to run **before** a `BEFORE_COMMIT` callback: phases fire at different times.
2. If T1 **rolls back**, `@TransactionalEventListener(AFTER_COMMIT)` does not run. An `AFTER_ROLLBACK` listener can run if the event was published inside the transaction.
3. If there is **no transaction**, with default `fallbackExecution=false`, transaction-bound listeners are skipped; tests must actively create a transaction.
4. `AFTER_COMMIT` executes after the real commit. A listener may see transaction resources undergoing cleanup, yet **must not assume a fresh transaction is open for DB writes**. When post-commit writes are needed, explicitly design a new transaction, typically `REQUIRES_NEW` in imperative code.
5. With reactive transactions, context lives in the Reactor Context; use appropriate publishing like `TransactionalEventPublisher` and test **subscription + commit/rollback** using reactive APIs.

### Integration Test Pattern with a Real Transaction Manager

A stable approach is using `TransactionTemplate` with `PlatformTransactionManager` and the publisher to control commit timing precisely:

~~~java
// Integration test illustration; requires transactionManager,
// applicationEventPublisher, and steps collector beans in test context.
var template = new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    applicationEventPublisher.publishEvent(new OrderPlaced(101L));

    // Not yet at BEFORE_COMMIT / AFTER_COMMIT.
    assertEquals(List.of(), steps.snapshot());
});

// After executeWithoutResult returns, the transaction is complete.
assertEquals(
    List.of("before-A", "before-B", "after-A", "after-B"),
    steps.snapshot()
);
~~~

This is not a standalone runnable file. It must be paired with `@EnableTransactionManagement` configuration (if using `@Transactional`), a real manager (e.g., `DataSourceTransactionManager` with H2), real listener beans, and a test transaction **created at the right time**. `TransactionTemplate` lets you manage boundaries directly without needing an `@Transactional` method proxy.

### Be Careful with `@Transactional` on Test Classes

In Spring Test, a test method annotated `@Transactional` usually **rolls back by default** when it finishes. If you simply publish an event inside that test and assert immediately, `AFTER_COMMIT` **has not run yet**; if the test rolls back, that callback never runs.

To genuinely test after-commit, you can:

- Run the transaction inside the test via `TransactionTemplate` as shown above, without wrapping the test method in an outer transaction it joins.
- Use Spring Test's `TestTransaction.flagForCommit()` followed by `TestTransaction.end()` when managed by an appropriate test transaction.
- After commit, use an independent DB readback to verify persisted data; avoid asserting based solely on "service was called" logs before the transaction completes.

Beyond callback ordering, tests should assert **the right phase** and **the right DB outcome**. Do not turn `@Order` into a substitute for testing commit/rollback.

## 8. Do Not Infer Ordering Between Two Different Listener Types

The following combinations must be evaluated separately:

| Combination | What Can Be Asserted? | What Should Not Be Asserted? |
| --- | --- | --- |
| Multiple synchronous `@EventListener`s, distinct `order` | Invocation/completion by priority level | Guarantee that business work committed |
| Multiple `@EventListener`s, same `order` | All were invoked, exact count | Fixed A/B order without an explicit contract |
| `@Async @EventListener` and sync listener | Eventual completion, per-handler result | That `Order` is **completion** order |
| Custom multicaster + executor | Results after all tasks complete | Submission order equals completion order |
| Multiple `@TransactionalEventListener`s in same phase | Callback order by `@Order` in test config | Different phases running together at publish time |
| Listeners in parent and child contexts | Child event can be handled in child then propagate to parent | One global `Order` sorting across all contexts |
| A listener emitting nested events | Order per event according to respective dispatch rules | Every event processed strictly in initial appearance order |

**Parent–child contexts:** Spring propagates events from child to parent. Each context has its own listener registry and multicaster. `@Order` values do not form **a single global ordering table across all contexts**.

**Nested events:** a listener for event A may call `publishEvent(B)`; under a synchronous multicaster, B's listeners may run **while** A's listener has not yet finished, before Spring continues to A's remaining listeners. Tests should not assume the combined list is always "all listeners of A, then all listeners of B."

## 9. Can Mockito `InOrder` Be Used?

Yes, when you want to verify **invocation order across mocks**:

~~~java
// Illustrative snippet, not a standalone file.
// Mocks are injected into real listener beans of the test context.
InOrder ordered = Mockito.inOrder(auditRepository, notificationClient);

ordered.verify(auditRepository).save(any());
ordered.verify(notificationClient).enqueue(any());
~~~

Advantage: verifies interactions with dependencies. However:

- If the test **calls** the listeners directly first, it does not verify the event multicaster.
- If listeners run asynchronously, `InOrder` running immediately after publish may miss calls; wait for the proper completion signal.
- If a DB write and network call depend on each other, consider moving that logic into an application service where dependencies are explicit, rather than relying on listener order.
- Mockito `verify` does not replace asserting real persisted data when transactions/rollbacks are involved.

The `CallLog` collector in the example is preferred for this lesson because it requires no extra mock dependencies, easily verifies the full sequence, and works with a real Spring context.

## 10. Common Testing Mistakes

**Mistake 1 — Asserting bean registration order.** Writing `@Bean a()` before `@Bean b()` does not substitute for `@Order`, because the goal is the event listeners' contract rather than how Spring scans classes or constructs beans.

**Mistake 2 — Leaving two listeners without `@Order` and expecting permanent ordering.** Tests may pass accidentally locally yet break when changing Spring versions, proxies, auto-configuration, or classpath.

**Mistake 3 — Using `Thread.sleep(...)` to wait for `@Async`.** Tests flake on CI. Replace with `CountDownLatch`, a `Future`, or a reliable signal.

**Mistake 4 — Testing completion order when the system guarantees only dispatch order.** `Order(-10)` on an async handler does not guarantee finishing before `Order(10)`.

**Mistake 5 — Testing with a mocked publisher instead of a real `ApplicationContext`.** A mocked publisher only records that `publishEvent` was called; it does not run the multicaster's listener sorting. Pick mocks when unit testing services; pick a real context when testing listener ordering.

**Mistake 6 — Asserting the last listener ran even though the first listener threw.** With the default synchronous `SimpleApplicationEventMulticaster` and no `ErrorHandler`, an exception can stop multicast. Test both error branches and error-handling policies.

**Mistake 7 — Forgetting to reset the collector.** `ContextRefreshedEvent` or events from earlier tests easily pollute history. Use specific event types and isolated contexts per test.

**Mistake 8 — Not waiting for the transaction to finish.** `AFTER_COMMIT` runs after commit; asserting directly inside an `@Transactional` body easily fails. Use `TransactionTemplate` or Spring Test transaction controls.

**Mistake 9 — Relying on global ordering across multiple contexts.** Parent and child have separate multicasters. Test the real topology if the application uses multiple contexts.

**Mistake 10 — Treating `@Order` as an exactly-once or durable ordering guarantee.** Local application events do not replace a message broker/outbox, nor do they guarantee recovery after crashes.

## 11. Checklist for Designing Listener Ordering Tests

1. **Identify the exact event type and listeners to verify.**
2. **State the contract:** do you need invocation order, completion order, or transaction-phase order?
3. **Specify `@Order` explicitly** on listeners where order is genuinely required.
4. **Use a real Spring `ApplicationContext`** to verify the event multicaster rather than calling handlers sequentially yourself.
5. **Collect history into a thread-safe collector** and assert the full list on synchronous paths.
6. **Do not enforce ordering among same-priority listeners** unless the application adds a dedicated contract.
7. **For async, wait on a timeout-bounded signal**, checking final outcomes instead of sleep durations.
8. **Test exceptions** from high-priority listeners and verify whether `ErrorHandler` lets execution continue.
9. **For transaction-bound listeners**, test real commit/rollback and distinguish phases from `@Order`.
10. **Test parent–child/nested-event topologies** if actually present, instead of assuming global ordering.
11. **Separate business dependency requirements from event ordering** whenever A's result must commit before B.
12. **Keep tests independent and repeatable**: do not depend on thread scheduling, startup order, or the clock.

### Key Takeaways

~~~text
@Order(-20)  -> higher listener invocation priority than @Order(20)
@EventListener + synchronous multicaster
             -> invocation order can be tested with List

@Async       -> order does not guarantee completion order
               use CountDownLatch / Future / await

@TransactionalEventListener
             -> phase decides when it runs
               @Order only prioritizes among matching callbacks

Default SimpleApplicationEventMulticaster
             -> throwing sync listener can stop multicast

Reliable tests
             -> real ApplicationContext + event + log + assert
~~~

**Conclusion:** When testing listener ordering, verify a small, explicit contract: **synchronous listeners with distinct `@Order` values are invoked by priority**. When moving to async, transactional phases, parent–child contexts, or nested events, adapt your testing strategy to execution timing and Spring's guarantees; a single list comparison cannot cover everything.

## Official Documentation

- [Spring Framework 6.2 — Standard and Custom Events / Ordering Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [JUnit 5 — Writing Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests)

# Directly Testing ApplicationListener with JUnit 5 in Spring

## 1. What Is Direct Testing of ApplicationListener?

In Spring Application Events, a bean can implement `ApplicationListener<E>` to receive a specific event type. When Spring publishes an event via `ApplicationEventPublisher.publishEvent(...)`, the multicaster infrastructure locates matching listeners and invokes:

```java
void onApplicationEvent(E event);
```

**Direct testing** (*direct unit test*) means instantiating a listener as a plain Java object, creating a real event, and **directly calling `listener.onApplicationEvent(event)`**. The test does not need to start a Spring container, database, or web server, and does not need to publish through Spring.

Minimal example:

```java
ReceiptGateway fake = orderId -> System.out.println(orderId);
ReceiptListener listener = new ReceiptListener(fake);

listener.onApplicationEvent(
        new ReceiptRequestedEvent("test", "ORD-1", true));
```

This snippet only illustrates how to invoke it; `ReceiptGateway`, `ReceiptListener`, and `ReceiptRequestedEvent` will be defined completely in the runnable example in section 5.

The core point: **we are testing the callback's logic**, not Spring's dispatch infrastructure. Direct invocation proves that for a given event, the listener takes the right branch, calls the right dependency, and handles errors as required; it **does not prove** that Spring will auto-discover the bean and invoke the listener when an event is published.

## 2. When Should You Choose a Direct Unit Test?

Calling `onApplicationEvent(...)` directly fits when a listener has relatively self-contained logic, such as:

- On an `OrderPaidEvent`, invoking the receipt-sending service with the right order ID.
- When a field indicates no notification is needed, skipping the side effect.
- When a dependency throws an exception, propagating the error or routing it to a handler per the contract.
- When an event is invalid, verifying intentional handling.
- When a listener receives an event twice, verifying what duplication causes and whether idempotency is required.

Advantages: fast tests, independent of context startup or profiles, no real connections opened, controllable data, and clear failure locations.

However, direct tests **do not cover**:

| Question | Direct call | Additional testing needed |
| --- | --- | --- |
| Is the logic of `onApplicationEvent` correct? | Yes | Unit test with fake/mock |
| Are the right fields passed to dependencies? | Yes | Assertions on calls |
| Are exceptions handled properly by the callback? | Yes | `assertThrows` and state |
| Does Spring find the listener bean? | No | Context integration test |
| Does `publishEvent(...)` select the right listener by type? | No | Dispatch integration test |
| Does `@Order` take effect with multiple listeners? | No | Test through the multicaster |
| Does `@Async` run on an executor? | No | Test via Spring proxy and executor |
| Does `@TransactionalEventListener` wait for commit? | No | Test with a real transaction |
| How do listener errors affect the publisher? | Incomplete | Test via `ApplicationEventPublisher` |
| Are events sent to a broker persisted/retried? | No | Integration/outbox/broker test |

Use **two testing layers**: many direct unit tests, plus a few context integration tests to confirm wiring/dispatch and infrastructure-dependent behaviors.

## 3. Understanding ApplicationListener and Event Types Properly

In Spring Framework 6.x, the generic interface has the form:

```java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
```

That means when implementing `ApplicationListener<OrderPaidEvent>`, `OrderPaidEvent` must **extend `org.springframework.context.ApplicationEvent`**.

An event class typically looks like:

```java
public final class OrderPaidEvent extends ApplicationEvent {
    private final String orderId;

    public OrderPaidEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

This is an **illustrative snippet**, requiring `ApplicationEvent` to be imported and placed in its Java file. `source` is the originating object/context that `ApplicationEvent` retains via `getSource()`; `source` must not be `null`.

Distinguish three listener styles:

1. **`ApplicationListener<MyEvent>`:** implements `onApplicationEvent(MyEvent)`; well suited for direct calls in unit tests.
2. **`@EventListener` on a bean method:** does not need to implement `ApplicationListener`; in a direct test, you can call the method as plain Java, though that does not test Spring's annotation mechanism.
3. **`ApplicationListener<PayloadApplicationEvent<MyPayload>>`:** used when catching POJO payloads wrapped by Spring in `PayloadApplicationEvent`. You can invoke it directly with the appropriate wrapper, though Spring does not auto-wrap payloads when you call the method yourself.

**Do not write** `implements ApplicationListener<MyRecord>` with a plain Java record if `MyRecord` does not extend `ApplicationEvent`: that fails the generic bound at compile time. If you want a framework-independent record event, use `@EventListener` accepting the record directly, or use `PayloadApplicationEvent<MyRecord>` on the listener interface.

## 4. Workflow of a Direct Unit Test

A test follows **Arrange – Act – Assert**:

1. **Arrange:** build fakes/mocks for dependencies, construct the listener via its constructor, and prepare an event with deterministic data.
2. **Act:** directly call `listener.onApplicationEvent(event)` once, or multiple times if testing repetition.
3. **Assert:** verify side effects, invocation counts, passed data, exceptions, and final state.

A design point that aids testability is having the listener avoid instantiating dependencies with `new` or calling arbitrary static/global services. Prefer **constructor injection**:

```java
public ReceiptListener(ReceiptGateway gateway) {
    this.gateway = Objects.requireNonNull(gateway);
}
```

Because of this, tests can supply a fake `ReceiptGateway` with no network calls. In real deployment, Spring provides a bean implementation of `ReceiptGateway`.

A simple listener typically follows this structure:

```text
ReceiptRequestedEvent
        |
        v
ReceiptListener.onApplicationEvent(event)
        |
        +--> receipt not required --> return
        |
        +--> receipt required --> ReceiptGateway.sendReceipt(orderId)
                                      |
                                      +--> succeeds
                                      +--> throws exception
```

Tests must cover **both the side-effect branch and the skip branch**, not just the happy path.

## 5. Runnable Java 17+ and JUnit 5 Project Example

This example uses **Spring Framework 6.2.13**, Java 17+, JUnit Jupiter 5.11.4, and Maven. Spring Boot is not required. The business policy **assumed in the example**: if an event has `receiptRequired=true`, the listener must call the gateway to send a receipt; if `false`, do not call it. All orders and the gateway are simulated; no real emails are sent.

### 5.1. Structure

```text
direct-application-listener-test/
├── pom.xml
├── src/main/java/example/events/
│   ├── ReceiptRequestedEvent.java
│   ├── ReceiptGateway.java
│   └── ReceiptListener.java
└── src/test/java/example/events/
    ├── ReceiptListenerTest.java
    └── ReceiptListenerIntegrationTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>direct-application-listener-test</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. ReceiptRequestedEvent.java

```java
package example.events;

import org.springframework.context.ApplicationEvent;

public final class ReceiptRequestedEvent extends ApplicationEvent {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final boolean receiptRequired;

    public ReceiptRequestedEvent(
            Object source, String orderId, boolean receiptRequired) {
        super(source);

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must be present");
        }

        this.orderId = orderId;
        this.receiptRequired = receiptRequired;
    }

    public String getOrderId() {
        return orderId;
    }

    public boolean isReceiptRequired() {
        return receiptRequired;
    }
}
```

This class fixes its data via `final` fields, validates the order ID in the constructor, and extends `ApplicationEvent` to be compatible with `ApplicationListener<ReceiptRequestedEvent>`.

### 5.4. ReceiptGateway.java

```java
package example.events;

public interface ReceiptGateway {
    void sendReceipt(String orderId);
}
```

This is the **dependency port** called by the listener. A real application might implement it with an email provider or notification service. Unit tests supply an in-memory fake to verify whether it was called, without issuing real requests.

### 5.5. ReceiptListener.java

```java
package example.events;

import java.util.Objects;

import org.springframework.context.ApplicationListener;

public final class ReceiptListener
        implements ApplicationListener<ReceiptRequestedEvent> {

    private final ReceiptGateway gateway;

    public ReceiptListener(ReceiptGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }

    @Override
    public void onApplicationEvent(ReceiptRequestedEvent event) {
        if (!event.isReceiptRequired()) {
            return;
        }

        gateway.sendReceipt(event.getOrderId());
    }
}
```

`@Component` is omitted from `ReceiptListener` in this example because unit tests instantiate it directly. The integration test in section 7 registers it as a bean via `@Bean`. Both approaches share the **same** production class; no special test-only logic is needed.

### 5.6. ReceiptListenerTest.java — Direct Unit Tests

```java
package example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReceiptListenerTest {

    // Simple fake, no Mockito or Spring TestContext needed.
    static final class RecordingGateway implements ReceiptGateway {
        final List<String> sentOrderIds = new ArrayList<>();
        int callCount;
        boolean shouldFail;

        @Override
        public void sendReceipt(String orderId) {
            callCount++;

            if (shouldFail) {
                throw new IllegalStateException("provider unavailable");
            }

            sentOrderIds.add(orderId);
        }
    }

    @Test
    void requiredEventInvokesGatewayWithCorrectOrderId() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-101", true);

        listener.onApplicationEvent(event);

        assertEquals(1, gateway.callCount);
        assertEquals(List.of("ORD-101"), gateway.sentOrderIds);
    }

    @Test
    void optionalEventDoesNotCallGateway() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-102", false);

        listener.onApplicationEvent(event);

        assertEquals(0, gateway.callCount);
        assertTrue(gateway.sentOrderIds.isEmpty());
    }

    @Test
    void dependencyFailurePropagatesFromDirectInvocation() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.shouldFail = true;
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-103", true);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> listener.onApplicationEvent(event));

        assertEquals("provider unavailable", error.getMessage());
        assertEquals(1, gateway.callCount);
        assertTrue(gateway.sentOrderIds.isEmpty());
    }

    @Test
    void callingTwiceCausesTwoGatewayCallsWithoutDeduplication() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-104", true);

        listener.onApplicationEvent(event);
        listener.onApplicationEvent(event);

        assertEquals(2, gateway.callCount);
        assertEquals(
                List.of("ORD-104", "ORD-104"),
                gateway.sentOrderIds);
    }

    @Test
    void eventRejectsBlankOrderId() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new ReceiptRequestedEvent(this, " ", true));
    }
}
```

These assertions prove:

1. **Required:** exactly one gateway call with the right order ID.
2. **Optional:** the listener ignores the event and triggers no side effect.
3. **Failure:** the dependency's exception propagates straight to the direct caller, without Spring automatically converting it into a retry or recovery.
4. **Duplicate call:** the current listener **has no idempotency**; calling it twice with the same event sends twice. This test intentionally describes current behavior, not implying that behavior is suitable for production.
5. **Validation:** the event is rejected by its constructor when the order ID is blank.

All of these are **direct unit tests**: the tests do not call `publishEvent(...)`, do not start Spring, and need no mocking framework.

### 5.7. Running the Tests

Using JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn test
```

You can run the unit test class alone:

```bash
mvn -Dtest=ReceiptListenerTest test
```

Once all example files are created accurately, Maven Surefire will discover **5 test methods** in `ReceiptListenerTest`. For the whole project (including the integration test in section 7), **6 test methods** in total. A successful run ends with `BUILD SUCCESS` and `0 failures / 0 errors`; detailed Surefire report line formatting varies depending on how it is invoked.

No fixed timing stdout is given, as execution duration, Maven logs, and local paths depend on the environment. What matters is the number of executed tests and passing assertions; this project requires no ports, DB, or API keys.

## 6. Testing Exceptions and Behavior When a Callback Fails

With a direct call, Java handles exceptions like any ordinary method:

```java
assertThrows(
        IllegalStateException.class,
        () -> listener.onApplicationEvent(event));
```

If `gateway.sendReceipt(...)` throws `IllegalStateException` and the listener does not catch it, the exception propagates to the test itself. **There is no Spring multicaster, error handler, retry proxy, transaction interceptor, or async error handler** in this direct call path.

In real runtime:

- With the default synchronous multicaster, uncaught exceptions can propagate to the `publishEvent(...)` caller, depending on error handler configuration.
- With an executor-backed multicaster, errors may surface on a worker thread instead of the publisher.
- If the listener method runs via `@Async`, exceptions from `void` methods normally do not return to the caller; separate handlers/metrics/logs are required.
- If the listener runs inside a transaction or uses `@TransactionalEventListener`, rollback/phase behavior cannot be concluded from a direct call alone.

**Decide the error contract** for the listener. For telemetry-only events, failures may not be allowed to break the core business flow; for events enforcing critical conditions, they may need to fail the transaction or record state for reprocessing. Direct tests only prove the code handles exceptions as written, not runtime policy itself.

### Testing a Recovery Branch (When Present)

If a listener follows a policy like:

```java
try {
    gateway.sendReceipt(event.getOrderId());
} catch (TemporaryGatewayException ex) {
    failedJobStore.record(event.getOrderId());
}
```

This is an **illustrative snippet**, assuming both dependencies and the exception type exist; it is not part of the runnable project in section 5. The corresponding unit tests should verify:

- When `gateway` succeeds, `failedJobStore` is not called.
- When `TemporaryGatewayException` is thrown, the failed job is recorded exactly once.
- When `failedJobStore` also fails, the final error path follows the contract instead of swallowing exceptions unconditionally.

If the code uses `@Retryable` via Spring AOP, **calling the method directly on a `new` instance does not test the retry annotation**. In that case, unit testing the method's inner logic and integration testing through the proxy are two separate requirements.

## 7. Minimal Integration Test: Confirming Spring Actually Dispatches

A `ReceiptListener` class can pass every unit test yet **never be registered as a bean** in the application. To verify wiring/dispatch, add a separate test using `AnnotationConfigApplicationContext`.

File `src/test/java/example/events/ReceiptListenerIntegrationTest.java`:

```java
package example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptListenerIntegrationTest {

    static final class TestReceiptGateway implements ReceiptGateway {
        final List<String> sentOrderIds = new ArrayList<>();

        @Override
        public void sendReceipt(String orderId) {
            sentOrderIds.add(orderId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        TestReceiptGateway receiptGateway() {
            return new TestReceiptGateway();
        }

        @Bean
        ReceiptListener receiptListener(
                TestReceiptGateway receiptGateway) {
            return new ReceiptListener(receiptGateway);
        }
    }

    @Test
    void springDispatchesEventToRegisteredApplicationListener() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             TestConfig.class)) {

            context.publishEvent(
                    new ReceiptRequestedEvent(this, "ORD-201", true));

            TestReceiptGateway gateway =
                    context.getBean(TestReceiptGateway.class);

            assertEquals(
                    List.of("ORD-201"),
                    gateway.sentOrderIds);
        }
    }
}
```

**How does this test differ from the direct test?**

- It creates a context, reads `@Configuration`, and registers `ReceiptListener` as a bean.
- When `context.publishEvent(...)` is called, Spring uses its multicaster to locate matching `ApplicationListener<ReceiptRequestedEvent>` beans.
- The test asserts that the gateway receives `ORD-201`.
- The context is closed via `try-with-resources`, preventing resources from outliving the test.

This integration test adds evidence of **registration and dispatch**, yet it **does not** automatically test async executors, transaction rollback, durable storage, or external effects. It still uses only `spring-context` and JUnit, without needing full Spring Boot.

A real-world test suite may also need unrelated event types to verify filtering, multiple listeners to verify ordering, or tests with the application's custom multicaster configuration. Those cases belong to the integration layer, not plain direct unit tests.

## 8. Using a Mock or a Fake for Dependencies?

In the example above, `RecordingGateway` is a **fake**: a small implementation that records received calls. Fakes fit well when:

- The interface is small and behavior is simple.
- You want clarity on what the callback does and why a test passes/fails.
- You want to avoid combining multiple annotations/mock infrastructure just to verify one call.

With Mockito, the code can be shorter:

```java
ReceiptGateway gateway = Mockito.mock(ReceiptGateway.class);
ReceiptListener listener = new ReceiptListener(gateway);

ReceiptRequestedEvent event =
        new ReceiptRequestedEvent(this, "ORD-301", true);
listener.onApplicationEvent(event);

Mockito.verify(gateway)
        .sendReceipt("ORD-301");
```

This is an **illustrative snippet**, not in the Maven project in section 5 because that project does not declare Mockito. Compiling it requires adding `org.mockito:mockito-core` in test scope and importing `org.mockito.Mockito`, or using `mockito-junit-jupiter` when JUnit integration is needed.

For the skip branch:

```java
Mockito.verifyNoInteractions(gateway);
```

Choose **one** style appropriate for the test's scope. You do not need Mockito just to assert a listener passes a single string when a simple fake suffices. Whether using a mock or a fake, avoid over-specifying implementation details outside the business contract.

### Avoid Meaningless Getter Checks

For example:

```java
assertEquals("ORD-301", event.getOrderId());
```

This assertion only checks a trivial getter on the event, **without proving the listener used that order ID**. The more important check is that the gateway actually received `ORD-301`. If an event has validation or data normalization rules, testing those rules separately can be useful.

## 9. Testing POJO Payloads and PayloadApplicationEvent

Not every Spring event is a subclass of `ApplicationEvent`. Spring Framework allows:

```java
public record PaymentCaptured(String paymentId) {
}
```

With a plain Java record event, the application can write:

```java
publisher.publishEvent(new PaymentCaptured("PAY-7"));
```

When using this object-publishing mechanism, Spring can wrap the payload in `PayloadApplicationEvent<PaymentCaptured>` for listener infrastructure. Two common registration styles exist:

**Style A: `@EventListener` accepting the POJO**

```java
@EventListener
public void on(PaymentCaptured event) {
    // Application logic.
}
```

**Style B: `ApplicationListener` accepting the wrapper**

```java
public final class PaymentCapturedListener
        implements ApplicationListener<
                PayloadApplicationEvent<PaymentCaptured>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<PaymentCaptured> event) {
        PaymentCaptured payload = event.getPayload();
        // Application logic.
    }
}
```

These snippets are **standalone illustrations**, omitting imports and bean declarations. With Style B, when testing directly, construct the wrapper:

```java
var payload = new PaymentCaptured("PAY-7");
var event = new PayloadApplicationEvent<>(this, payload);

listener.onApplicationEvent(event);
```

Requires importing `org.springframework.context.PayloadApplicationEvent`, `org.springframework.context.ApplicationListener`, defining `PaymentCapturedListener`, and registering it as a bean if you want Spring dispatch. Do not pass `PaymentCaptured` directly to `onApplicationEvent(PayloadApplicationEvent<PaymentCaptured>)` as the types do not match.

**Limitation:** this direct test skips Spring's object-payload wrapping and generic event-type matching steps. To prove `publishEvent(payload)` truly reaches the right listener, test through a context by publishing the real record.

## 10. Testing Ordering and Multiple Listeners

If an application has two listeners for the same event:

```text
OrderPaidEvent
  ├── AuditListener
  └── ReceiptListener
```

Directly unit testing `audit.onApplicationEvent(event)` and `receipt.onApplicationEvent(event)` proves only **each listener's logic**. It does not state which listener Spring will dispatch first. When ordering matters, use Spring-supported ordering mechanisms and test through the multicaster.

Do not try to prove ordering by manually calling listeners in sequence inside a test:

```java
audit.onApplicationEvent(event);
receipt.onApplicationEvent(event);
```

This is an **example of an insufficient test**: the test hardcodes the call order itself and never exercises Spring dispatch. Especially with async listeners, task submission order and completion order are two different concepts; even when `@Order` governs dispatch order, do not assume all async handlers finish in order.

When a dependency between listeners is a strict business requirement, design an explicit workflow/orchestrator rather than relying solely on event listener ordering.

## 11. Does a Unit Test Prove Rollback and Transactions?

**No.** A direct call neither starts a Spring transaction nor invokes transaction interceptors. For example:

```java
listener.onApplicationEvent(event);
```

This call simply runs a normal Java method. It **does not test**:

- Whether `@Transactional` actually opens a transaction through a Spring proxy.
- Whether `@TransactionalEventListener(AFTER_COMMIT)` is invoked after commit.
- Whether the listener is skipped when no transaction is active (the default for `@TransactionalEventListener`).
- Whether the originating transaction commits or rolls back when an exception occurs.
- Whether the publisher's transaction propagates to an async worker (imperative transactions are typically thread-bound and do not propagate automatically).

With `@TransactionalEventListener`, Spring registers callbacks via transaction synchronization; testing by calling the handler method directly **completely bypasses that registration step**. To test phases, publish the event inside a real transaction, commit/roll back, and assert side effects at the proper milestone.

Note when using `@Transactional` on a test: many Spring Test configurations roll back automatically after the test. A test annotated `@Transactional` that waits for `AFTER_COMMIT` may never observe the callback because **the transaction never committed**. In that case use `TestTransaction` or create a real transaction and commit intentionally.

If a post-commit callback also needs to write to the DB in a new transaction, design it via a service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` or an appropriate `TransactionTemplate`; direct tests check only the service's internal logic, not proxy/transaction semantics.

## 12. Does a Unit Test Prove @Async Works?

Again, **no**. An `@Async` method called directly on an instance normally **does not go through a Spring proxy**. As a result, the method can run synchronously on the test thread, even though an executor exists at runtime.

For example:

```java
ReceiptListener listener = new ReceiptListener(fake);
listener.onApplicationEvent(event); // Runs directly on the test thread.
```

For real async listeners, an integration test should:

1. Create a context with `@EnableAsync` and a dedicated executor.
2. Publish the event via `ApplicationEventPublisher`.
3. Use `CountDownLatch`, `CompletableFuture`, or polling with a timeout to wait for completion.
4. Verify the thread/executor when that is part of the requirements.
5. Assert **outcomes** and exception handling, not merely that a task was submitted.

Avoid `Thread.sleep(100)` assuming the handler surely finished: under busy CI load, such tests become flaky. Also avoid demanding the callback run on a different thread under every executor configuration: synchronous executors or fallback/rejection policies can alter behavior.

## 13. Choosing Good Test Data and Assertions

### Test Business-Meaningful Event Names and Data

Events should carry clear data, and tests should use distinct IDs like `ORD-101`, `ORD-102` instead of using `id` in every test. Do not rely on current wall-clock time or randomness unnecessarily.

If an event has a timestamp, use `Clock.fixed(...)` or fixed timestamps for deterministic assertions; if it has a UUID, construct deterministic UUIDs in fixtures. Sensitive data should never be copied verbatim into public test snapshots.

### Verifying "Do Nothing" Is a Valuable Result

In many use cases, the most critical rule is that a listener **does not** trigger side effects under invalid conditions. With a fake, assert `callCount == 0` and an empty call list. With a mock, use `verifyNoInteractions(...)` or `never()` at the right scope.

### Testing Idempotency Must Match the Contract

In section 5's example, the test invokes the same event twice and expects two sends. That documents **current behavior**, not a production requirement. If the business requires executing each event at most once, implement idempotency in the adapter/service using `eventId`/unique keys or appropriate transactions, and then **update the test** to expect one side effect.

A `boolean` field inside a listener works for a single-instance demo but **does not** protect across multiple instances, restarts, or consumer retries. For critical events, a durable deduplication store or downstream idempotency is required.

### Do Not Test Only with "Does Not Throw"

A test like this is too weak:

```java
assertDoesNotThrow(() -> listener.onApplicationEvent(event));
```

It can pass even if the listener accidentally forgets to call the gateway. Assertions on actual outputs or interactions are required. You may combine `assertDoesNotThrow` with other assertions, but never treat it as sufficient proof alone.

## 14. Common Mistakes and How to Fix Them

**Mistake 1 — Thinking a direct test verifies event dispatch.** Calling a method manually does not verify bean registration, event type matching, or the multicaster. Add a short context integration test.

**Mistake 2 — Fetching the listener from a context for every unit test.** Makes tests slow, coupled to broad configuration, and hard to isolate logic. For most branches, construct the listener directly with fakes/mocks.

**Mistake 3 — Not injecting dependencies, instantiating an HTTP client with `new` inside the listener.** Forces tests onto real networks or global state hacks. Extract a port/interface and inject via constructor.

**Mistake 4 — Mocking the listener itself.** If the listener's method is mocked, the real callback never runs; the test only checks mock-stubbed behavior. Mock dependencies and call the real listener.

**Mistake 5 — Using a POJO record as the type argument to `ApplicationListener<E>`.** Generic `E` must extend `ApplicationEvent`. Use an event subclass, `PayloadApplicationEvent<Payload>`, or `@EventListener`.

**Mistake 6 — Testing only the happy path.** Skipped events, invalid data, exceptions, and retry/recovery often hide the main bugs. Test according to a decision table.

**Mistake 7 — Failing to assert side-effect calls.** A test checking only that no exception was thrown cannot catch a gateway never being invoked.

**Mistake 8 — Expecting `@Async` or `@Transactional` to take effect when calling a `new` listener.** Annotations rely on real infrastructure/proxies/transactions; write corresponding integration tests.

**Mistake 9 — Using direct call order to prove `@Order`.** Manual calls do not pass through the multicaster. Test ordering via an event publisher when needed.

**Mistake 10 — Relying on sleep and stdout.** Tests turn flaky and side effects remain unverified. Use fakes/mocks, latches with timeouts, and meaningful assertions.

**Mistake 11 — Treating one invocation as proof of listener idempotency.** When a broker or retry redelivers an event, the same callback can run again. Explicitly test duplicate delivery and design deduplication when business rules demand it.

**Mistake 12 — Coupling unit tests to full DB/email.** A direct unit test needs no external resources; use fakes. Move transaction, broker, persistence, and network contracts into dedicated integration/contract test layers.

## 15. Checklist Before Completing the Test Suite

1. Does the listener properly implement `ApplicationListener<E extends ApplicationEvent>`?
2. Do test names describe **behavior** rather than implementation details?
3. Are event/source data deterministic, and is validation tested if needed?
4. Does the test construct the real listener and inject fake/mock dependencies instead of hitting real infrastructure?
5. Are there assertions on **call count, arguments, and results** for the success branch?
6. Are there assertions for skip branches and important failure paths?
7. When duplicate events occur, are idempotency/side-effect expectations explicitly defined?
8. Is there a clear distinction between **direct tests** and **dispatch integration tests**?
9. If `@Async`, `@Retryable`, or `@TransactionalEventListener` is used, are there tests through Spring infrastructure for those behaviors?
10. Do tests avoid relying on test execution order, fixed thread names, arbitrary timeouts, and logs as primary assertions?
11. Are contexts/resources closed in integration tests to avoid affecting other tests?
12. Does a single `mvn test` run all intended tests without skipped tests or external environment dependencies?

**Conclusion:** Directly testing `ApplicationListener` is a fast, reliable way to validate **handler logic**: construct the real listener, pass a real event into `onApplicationEvent(...)`, observe dependencies with fakes/mocks, and assert both success and failure paths. Because it bypasses the container, add integration tests whenever you need to prove Spring auto-registers the listener, dispatches the right type, and handles async, transactions, or ordering.

## References

- [Spring Framework API — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html): generic bounds, callback, and listener contract.
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): publishing events in an `ApplicationContext`.
- [Spring Framework API — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper for POJO payloads.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): listeners, annotations, event multicaster, and event handling.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): `@Test`, assertions, and test execution.
- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): integrating a Spring context when logic unit tests are insufficient.

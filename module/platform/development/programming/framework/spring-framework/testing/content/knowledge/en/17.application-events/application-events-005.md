# Verifying Conditional Listeners and Handling Failures

When a Spring application publishes an event, calling `ApplicationEventPublisher.publishEvent(...)` only confirms that the event was submitted to the `ApplicationContext`'s event-publishing mechanism. We also need to verify whether the matching listener is actually invoked, whether the filter condition excludes the right events, and which policy governs errors thrown by listeners.

These two points are directly related. A listener may be registered properly yet skipped because its `condition` expression evaluates to `false`. Conversely, a listener may be invoked properly yet throw an exception that causes the event publication call to fail. A good test needs to publish a real event inside a Spring context, observe the processing result, and verify both the success path and the failure path.

## 1. The Mechanism to Verify

Spring supports declaring listeners using `@EventListener` on a bean:

```java
@Component
class PaymentListener {

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        // Handle the event.
    }
}
```

When the `ApplicationContext` initializes, Spring detects `@EventListener` methods and registers them with the event publisher. When the application calls `publishEvent`, Spring finds listeners whose parameter type is compatible with the published event type and invokes those listeners.

A listener can also declare a `condition` attribute. This is a Spring Expression Language (SpEL) expression evaluated for each event. Only when the expression evaluates to `true` does Spring invoke the listener method. For example:

```java
@EventListener(condition = "#root.args[0].amount >= 1000")
public void onLargePayment(PaymentReceived event) {
    // Handle only payments of 1,000 or more.
}
```

In the expression context, `#root.args` is the list of arguments passed to the listener method. `#root.args[0]` is the first argument, which in this example is the `PaymentReceived` event. This syntax clearly expresses the data the condition inspects and does not depend on whether Spring can discover Java parameter names.

By default, `SimpleApplicationEventMulticaster` invokes listeners synchronously on the event-publishing thread. Therefore, listener outcomes and exceptions can directly affect the `publishEvent` call. If the application configures an asynchronous executor or the listener uses `@Async`, when and where errors are received will change. Tests must reflect the exact configuration the application uses.

## 2. Verifying Listener Conditions

We use a simple event to test a payment threshold. Spring allows publishing any object as a payload event; the event class does not have to extend `ApplicationEvent`.

```java
public record PaymentReceived(String paymentId, int amount) {
}
```

The listener stores accepted events so the test can observe the result:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.event.EventListener;

public class LargePaymentListener {

    private final List<PaymentReceived> receivedPayments = new ArrayList<>();

    @EventListener(condition = "#root.args[0].amount >= 1000")
    public void onPaymentReceived(PaymentReceived event) {
        receivedPayments.add(event);
    }

    public List<PaymentReceived> receivedPayments() {
        return List.copyOf(receivedPayments);
    }
}
```

We can test the listener using `AnnotationConfigApplicationContext`. This is a real Spring context—sufficient for Spring to register and invoke `@EventListener`, without needing to boot an entire Spring Boot application:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LargePaymentListenerTest {

    @Test
    void handlesOnlyPaymentsAtOrAboveTheThreshold() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(LargePaymentListener.class);
            context.refresh();

            var listener = context.getBean(LargePaymentListener.class);
            var belowThreshold = new PaymentReceived("PAY-001", 999);
            var atThreshold = new PaymentReceived("PAY-002", 1000);
            var aboveThreshold = new PaymentReceived("PAY-003", 1500);

            context.publishEvent(belowThreshold);
            context.publishEvent(atThreshold);
            context.publishEvent(aboveThreshold);

            assertEquals(
                    List.of(atThreshold, aboveThreshold),
                    listener.receivedPayments());
        }
    }
}
```

Events are published via `context.publishEvent`, so the test goes through Spring's real dispatch mechanism. The expected result proves three cases: a payment below the threshold is skipped, a payment at the threshold is handled, and a payment above the threshold is also handled.

When testing conditions, choose data on both sides of the threshold and right at the threshold. Testing only a value above the threshold can miss a bug where `>` was used instead of `>=`. If the condition has multiple branches, create an event for each branch and explicitly verify the set of processed events.

### When Should You Use `@SpringBootTest`?

`AnnotationConfigApplicationContext` fits when the goal is to test listener registration, SpEL evaluation, and event dispatching. Use `@SpringBootTest` when the listener depends on the application's real configuration, such as beans created by component scanning, profiles, conditional configuration, or other integration components.

In integration tests, you can inject `ApplicationEventPublisher` and publish events through that publisher. Ensure the listener bean under test is actually present in the test's context. If you replace the listener with a mock or only mock `ApplicationEventPublisher`, the test will no longer verify Spring's registration and dispatch mechanism.

## 3. Verifying Errors with Synchronous Listeners

With the default synchronous event multicaster, listeners are invoked directly during the `publishEvent` call. If a listener throws an unhandled exception, a runtime exception can propagate back to the event publisher.

Example listener rejecting an invalid payment:

```java
import org.springframework.context.event.EventListener;

public class RejectingPaymentListener {

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        throw new IllegalArgumentException(
                "Unsupported payment: " + event.paymentId());
    }
}
```

The test needs to verify that the exception occurs right when the event is published and preserves meaningful error information:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class RejectingPaymentListenerTest {

    @Test
    void propagatesRuntimeFailureToThePublisher() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(RejectingPaymentListener.class);
            context.refresh();

            var exception = assertThrows(
                    IllegalArgumentException.class,
                    () -> context.publishEvent(
                            new PaymentReceived("PAY-004", -1)));

            assertEquals("Unsupported payment: PAY-004", exception.getMessage());
        }
    }
}
```

This test verifies the failure contract of the default synchronous configuration: a runtime exception from a listener causes the event publication operation to fail. If the application configures a custom `ErrorHandler`, executor, or asynchronous mechanism, the outcome may differ; in that case, the test must set up that exact configuration.

## 4. Verifying the Event Multicaster's `ErrorHandler`

An application can configure an `ErrorHandler` on `SimpleApplicationEventMulticaster` to centrally handle exceptions raised inside listeners. For example, the handler records errors for logging, monitoring, or forwarding to another processing mechanism.

We register a bean named `applicationEventMulticaster` before refreshing the context. Spring will use this bean as the context's event multicaster:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
```

The following two listeners let us observe both the error path and the normal processing path:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.event.EventListener;

public class HealthyPaymentListener {

    private final AtomicInteger handledCount;

    public HealthyPaymentListener(AtomicInteger handledCount) {
        this.handledCount = handledCount;
    }

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        handledCount.incrementAndGet();
    }
}
```

`RejectingPaymentListener` from the previous section is a listener that intentionally throws `IllegalArgumentException`. The test configures an `ErrorHandler` to record the exception:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

class PaymentListenerErrorHandlerTest {

    @Test
    void recordsListenerFailureAndContinuesDispatching() {
        List<Throwable> failures = new ArrayList<>();
        var healthyListenerCalls = new AtomicInteger();

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster = new SimpleApplicationEventMulticaster();
                        multicaster.setErrorHandler(failures::add);
                        return multicaster;
                    });
            context.registerBean(RejectingPaymentListener.class);
            context.registerBean(
                    HealthyPaymentListener.class,
                    () -> new HealthyPaymentListener(healthyListenerCalls));
            context.refresh();

            context.publishEvent(new PaymentReceived("PAY-005", 1200));

            assertEquals(1, failures.size());
            assertTrue(failures.get(0) instanceof IllegalArgumentException);
            assertEquals(1, healthyListenerCalls.get());
        }
    }
}
```

In this example, the `ErrorHandler` receives the exception and returns normally. As a result, the event multicaster can continue invoking the remaining listener. The test verifies both outcomes: the error was recorded and the healthy listener was still called.

Continuing dispatch depends on whether the `ErrorHandler` completes normally. If the handler itself throws an exception, that error can escape the event publication process. An `ErrorHandler` also does not perform retries automatically; if business rules require retries, design and test a separate retry policy.

## 5. Distinguishing Synchronous and Asynchronous Errors

Expectations for synchronous listeners should not be applied to listeners running asynchronously.

| Configuration | Where It Executes | How to Verify Errors |
|---|---|---|
| Default `SimpleApplicationEventMulticaster` | Same thread calling `publishEvent` | Use `assertThrows` to check exceptions propagated back to the publisher. |
| Multicaster with `TaskExecutor` | Configured executor | The publisher does not necessarily wait for listeners to finish; check results via synchronization or state recorded by the listener. |
| Listener method using `@Async` | Spring Async executor | For `void` methods, configure `AsyncUncaughtExceptionHandler` to observe exceptions. For `Future`/`CompletableFuture` return types, inspect errors via the asynchronous result. |

When testing asynchronously, do not call `publishEvent` and immediately inspect a counter assuming the listener has already finished. Use `CountDownLatch`, `CompletableFuture`, or a condition-waiting library like Awaitility to wait for a result with a time bound. This avoids race conditions and makes the test fail clearly if the listener never finishes.

Conceptual example with `CountDownLatch`:

```java
var completed = new CountDownLatch(1);

// Listener calls completed.countDown() after finishing processing.
context.publishEvent(event);

assertTrue(completed.await(2, TimeUnit.SECONDS));
```

The snippet above illustrates synchronization; in a real test, place the latch inside a Spring-managed listener and also verify the recorded result or exception. Avoid `Thread.sleep`, because a fixed sleep duration does not prove the listener finished and can make tests slow or flaky.

## 6. Common Testing Mistakes

### Publishing an Event Without Verifying the Outcome

A successful `publishEvent` call does not prove a conditional listener ran. The condition might have evaluated to `false`, the event type might be incompatible, or the listener bean might not be registered. Verify output state, invocation counts, or an observable effect.

### Mocking the Publisher When the Goal Is to Test Dispatch

Mocking `ApplicationEventPublisher` only verifies interactions with the mock. It does not run `EventListenerMethodProcessor`, does not evaluate SpEL, and does not invoke listeners. To test those behaviors, use a real Spring context and publish events via the context or the publisher it provides.

### Testing Only One Side of a Condition

With a `>= 1000` threshold, test at least one value below the threshold and the value at the threshold. If the condition is more complex, create data for each branch to catch wrong expressions or incorrect property access.

### Assuming Listeners Always Run in Registration Order

Do not rely on bean creation or registration order to infer listener execution order. If ordering is a business requirement, declare `@Order` appropriately and write a test verifying that order. If ordering is not part of the contract, verify the final outcome instead of invocation order.

### Ignoring the Application's Error Configuration

A test using a default context can behave differently from the real application if the application configures an `ErrorHandler`, an executor, or `@Async`. In integration tests, include the relevant configuration in the context and verify the actual exception path.

## 7. Test Checklist

- [ ] The Spring context registers the bean containing the `@EventListener` method.
- [ ] The published event type is compatible with the listener parameter.
- [ ] There are cases where the condition is not met and cases where the condition is met.
- [ ] Boundary values of the condition are tested.
- [ ] The test confirms the listener was invoked or skipped via an observable outcome.
- [ ] Failure tests verify the exact exception or configured `ErrorHandler`.
- [ ] If dispatching asynchronously, the test waits for results using a synchronization mechanism with a timeout.
- [ ] The test does not depend on listener ordering unless ordering is part of the application contract.

Verifying conditional listeners requires confirming both Spring's event dispatching and SpEL expression evaluation. Verifying failures requires reproducing the application's synchronous or asynchronous mode along with its `ErrorHandler` policy. When both parts are tested individually and together, tests clearly reveal which listener was invoked, which condition blocked processing, and where exceptions were routed.

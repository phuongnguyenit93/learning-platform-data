# Scoping Event Recording When Contexts or Threads Are Shared

## Problem to Solve

In Spring, beans commonly share a single `ApplicationContext`. When a bean calls `ApplicationEventPublisher.publishEvent(...)`, matching listeners in the context receive that event. This is an application-scoped communication mechanism, so a single event can be observed by multiple components.

In testing, an `ApplicationContext` can also be reused across multiple test classes by the Spring TestContext Framework through context caching. Sharing a context makes the test suite run faster, yet requires clear boundaries for event recording. If an event collector stores data as singleton state or in a `static` field, events from an earlier test can appear in the results of a later test. When tests run in parallel or publish events through an executor, per-test-method boundaries also need careful handling.

There are three scopes to distinguish:

| Scope | Meaning | Risk When Shared |
| --- | --- | --- |
| `ApplicationContext` | Lifecycle of beans and listeners inside the context | A singleton listener or collector can outlive individual test methods |
| Test method | Duration during which a single test method executes | Any event emitted during that method can be recorded, including events from setup steps or other components |
| Execution thread | Thread running synchronous calls or asynchronous tasks | Events emitted late or from another thread may fall outside the test's recording session |

The goal of a test is to verify events produced by the action under test, within the exact scope being observed. Not every event that ever appeared in the context should be treated as the outcome of a single operation.

## Using the Dedicated Recorder for Test Methods

The Spring TestContext Framework provides `@RecordApplicationEvents` and `ApplicationEvents` to record application events during test method execution. This is the right choice when you need to inspect events published by services or components inside the test's `ApplicationContext`.

- Place `@RecordApplicationEvents` on the test class to enable recording.
- Inject `ApplicationEvents` into the test using `@Autowired`.
- Use `stream(EventType.class)` to retrieve events of the type to check; use `stream()` only when you genuinely need to inspect all events.
- The recorder is managed per test method lifecycle and refreshed between methods. Because of that, tests can share a cached `ApplicationContext` without needing a global event list.

The example below assumes `OrderService.place(...)` publishes a payload event of type `OrderPlaced`:

```java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(OrderTestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void publishesEventForTheRequestedOrder() {
        UUID orderId = UUID.randomUUID();

        orderService.place(orderId);

        List<OrderPlaced> recorded = applicationEvents
                .stream(OrderPlaced.class)
                .filter(event -> orderId.equals(event.orderId()))
                .toList();

        assertThat(recorded).hasSize(1);
        assertThat(recorded.get(0).orderId()).isEqualTo(orderId);
    }
}
```

The example generates a fresh `UUID` for each run and filters by `orderId`. Even if the context also produces an `OrderPlaced` for another order, that event does not skew the current test's result. Checking both count and identifying data catches two distinct bugs: failing to publish the event, and publishing a wrong or duplicate event for the entity under test.

`ApplicationEvents` records per test method; it does not automatically partition a single method into individual service calls. If one test method invokes two independent operations, both sets of events remain in the same recording session. When you need to distinguish them, use a correlation ID or distinct business key per operation and filter by that key. If two behaviors are independent, splitting them into two test methods creates a cleaner boundary.

## When Multiple Tests Share an `ApplicationContext`

Spring can cache a context and reuse it across multiple test classes with compatible configurations. This is normal behavior, not a sign that test recording data must be shared. With `@RecordApplicationEvents`, recording is tied to the test method lifecycle; there is no need to close the context after every test just to clear the event list.

To avoid picking up unintended events in a shared context, apply these principles:

1. **Filter by event type.** Prefer `stream(OrderPlaced.class)` instead of counting the entire `stream()`. Other events in the same context should not affect assertions for the business operation under test.
2. **Filter by operation identifier.** Use an ID or correlation ID generated specifically for the test. This is helpful when multiple beans publish the same event type or a test method performs multiple operations.
3. **Keep setup controlled.** If `@BeforeEach`, fixtures, or helpers invoke services and emit domain events, those events can fall within the test's recording window. Avoid producing unrelated events in setup; if unavoidable, distinguish them via event identifiers or data.
4. **Do not use global collections.** Avoid `static List<ApplicationEvent>`, singleton recorders accumulating events across tests, or mutable fields shared across test classes. They make results order-dependent and hard to manage under parallel execution.
5. **Do not assert on total context event counts without a clear reason.** Assert the exact type, identifier, count, and payload promised by the business contract.

For example, the following assertion is usually too broad:

```java
assertThat(applicationEvents.stream().count()).isEqualTo(1);
```

It assumes no other events occurred during the test session. Asserting by specific type and business identifier is generally much more resilient:

```java
assertThat(applicationEvents.stream(OrderPlaced.class)
        .filter(event -> orderId.equals(event.orderId())))
        .hasSize(1);
```

If a test class declares `@TestExecutionListeners` in a mode that replaces all default listeners, ensure `ApplicationEventsTestExecutionListener` remains registered. If this listener is omitted, the event-recording annotation will lack the TestContext mechanism it needs to function.

## When Execution Threads Are Shared or Become Asynchronous

With synchronous calls, the service publishes events while the test method is running, so the test can inspect results once the call returns. A different situation arises when a service delegates work to `@Async`, an `Executor`, a scheduler, or a message consumer.

Two distinct issues must be addressed:

- **Timing:** the test method may finish before the background task publishes the event. By then, the test's recording session has ended and assertions may run too early.
- **Threads:** the background task runs on a different thread from the test thread. Do not assume recording state bound to the test thread is automatically propagated to every thread created by the application. Exact behavior depends on the recording mechanism and how the application hands off work.

When testing asynchronous flows:

- Wait for a completion signal using `CountDownLatch`, `CompletableFuture`, or a condition-waiting library such as Awaitility; avoid `Thread.sleep(...)` because fixed delays do not prove the task finished.
- Ensure the event is published before the test method exits if using a method-lifecycle recorder.
- Use a correlation ID to associate events with the request that initiated the task. Do not rely solely on timing or global ordering when multiple tasks run concurrently.
- If you need to observe events published on background threads, carefully check thread limitations of the recorder in your Spring version. When the built-in mechanism does not fit that scenario, create a dedicated test listener with clear registration/unregistration lifecycle and thread-safe storage.
- Distinguish **event published** from **asynchronous listener completed**. Recording an event only proves it passed the publish point; to verify processing outcomes, wait for and assert the listener's state or completion signal.

A thread-safe collection such as `CopyOnWriteArrayList` only prevents concurrent modification errors. It does not create isolation between tests. If multiple tests write to one list, they can still see one another's data even though the list does not corrupt due to race conditions.

## When Events Depend on Transactions

Regular events are published immediately when code calls `publishEvent(...)`. However, listeners using `@TransactionalEventListener` can defer processing until a transaction phase such as `BEFORE_COMMIT` or `AFTER_COMMIT`.

Tests annotated with `@Transactional` in Spring Test normally end with a rollback. Therefore, a listener waiting for `AFTER_COMMIT` may not run in that test. Distinguish two goals:

- If only verifying that the service published the event, you can record the event at publish time and assert its type/contents.
- If verifying post-commit listener side effects, the test must trigger an actual commit, such as using `@Commit` or explicitly controlling the transaction with `TestTransaction` in an appropriate configuration.

Do not conclude a listener is broken simply because the test transaction rolled back before the phase the listener was waiting for. Conversely, recording the event does not prove an `AFTER_COMMIT` listener executed.

## When You Must Write Your Own Event Recorder

`@RecordApplicationEvents` should be the first choice for TestContext-based integration tests. Only write a custom recorder when you need to observe outside what this mechanism supports, such as a specialized background flow or a custom context boundary.

If using `ApplicationListener` or `@EventListener` to collect events, clearly define:

- Which context the recorder belongs to and which context's events it receives.
- When collection starts and when it stops.
- Where data is cleared or discarded after each test.
- Whether multiple threads can write concurrently.
- Which test or correlation ID distinguishes the events.

A singleton listener registered in a cached context lives as long as that context. Thus, merely adding a list to a listener and checking that list in each test is not enough: the list must be isolated and cleaned up according to the proper lifecycle. Using a thread-safe collection does not replace cleanup or session separation.

`@DirtiesContext` is also not the default tool for clearing an event recorder. This annotation marks the context for eviction from the cache and recreation, which is appropriate when the context's own state has been mutated or corrupted beyond reuse. Using it merely to avoid a shared event list increases context startup overhead and hides recorder lifecycle management issues.

## Choosing the Right Scoping Strategy

| Scenario | Recommended Approach |
| --- | --- |
| Multiple test methods share a cached context | `@RecordApplicationEvents` and `ApplicationEvents` per test method |
| One method triggers multiple business operations | Generate a dedicated correlation ID and filter by ID; or split into independent test methods |
| Setup produces unrelated events | Remove events from setup if possible; otherwise filter by type and identifier |
| Multiple tests run in parallel | Avoid global mutable lists; ensure each test has an isolated recording session |
| Events published from an executor or `@Async` | Synchronize completion timing, check thread limitations, and use an appropriate recorder if needed |
| Listener runs only after transaction commit | Commit the transaction in the test when verifying post-commit side effects |
| Custom recorder shares context lifetime | Register/unregister and clear data per test; ensure thread safety |

## Common Mistakes

- **Counting all events and assuming there is only one:** assertions couple to auxiliary events in the same context. Filter by event type and business key.
- **Storing events in a `static` field:** data persists across test methods and can leak across test classes. Use a per-test recorder or a recorder with a dedicated lifecycle.
- **Assuming one test method equals one business call:** a method may emit multiple events from setup, multiple services, or multiple invocations. Use a correlation ID to separate them.
- **Asserting immediately after submitting a background task:** submitting a task does not mean the event has been published. Wait for a meaningful completion condition.
- **Using `@DirtiesContext` for every recording issue:** recreating the context is expensive and does not fix a poorly designed global-state recorder.
- **Confusing event publication with listener completion:** publishing an event does not guarantee every synchronous or asynchronous listener has finished handling it.
- **Forgetting the TestExecution listener when replacing default configuration:** `@RecordApplicationEvents` requires the Spring TestContext listener to manage recording sessions.

## Verification Workflow in a Test

1. Identify the business event to observe and the identifier field that distinguishes the current operation's event.
2. Enable `@RecordApplicationEvents` on the test class and inject `ApplicationEvents`.
3. Create test-specific data or a correlation ID.
4. Execute the exact action under test.
5. If the action is asynchronous or depends on commit, wait for the right completion milestone before reading results.
6. Filter events by type and identifier; assert both count and key data.
7. Let Spring manage recording lifecycle across test methods; if using a custom recorder, explicitly unregister and clear data after the test.

When contexts or execution threads are shared, test reliability depends on defining the right recording boundaries. The per-test-method recorder handles standard cases well; filtering by type and correlation ID scopes results to business logic; and asynchronous tasks and transactions require proper completion signals. These three layers of control help tests verify the exact events produced by the target action without depending on execution order or leftover state from other tests.

# Testing Asynchronous Flows Without Arbitrary Sleeps in Spring Integration

## 1. Why Does `Thread.sleep(...)` Make Message Flow Tests Unreliable?

Spring Integration implements many Enterprise Integration Patterns (EIP) via channels and endpoints. A message may pass through a synchronous `DirectChannel`, an asynchronous `ExecutorChannel`, a `QueueChannel` with a polling consumer, a scheduler-backed Delayer, or Router/Splitter/Aggregator branches that must wait for all results.

In these flows, tests written like this easily go wrong:

~~~java
input.send(MessageBuilder.withPayload("ORDER-501").build());
Thread.sleep(2_000);                 // Not synchronized on any event.
assertEquals("DONE", status.get());   // A busy CI machine may not finish in time.
~~~

Problems:

- **Flaky:** a fast machine finishes in 5 ms, while a busy CI machine takes over 2 seconds; the test passes and fails unpredictably.
- **Wasteful:** when the result is ready in 5 ms, the test still sits idle for 2 full seconds.
- **No causal link:** 2 seconds elapsing does not prove the consumer received the message, the error flow finished, or the Aggregator released.
- **Masks bugs:** the test may inspect a single variable while the message was dropped, routed to another branch, or retried.
- **Hard to maintain:** bumping sleep from 2 to 10 seconds only slows tests down without making the assumption valid.

A better approach is to **wait for an observable condition**, with a **clear maximum timeout**, and then assert content and semantics:

~~~text
Send message
    |
    v
Wait for completion event / received message / final state
    |
    +-- Completed before deadline -> assert immediately
    |
    +-- Timeout expired -> fail with specific diagnostics
~~~

For the **SPRING_INTEGRATION_PATTERN** module, this is the foundation for testing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation branches. The goal is not merely "making tests green," but proving messages **take the right branch, preserve business headers, handle errors per policy, and terminate under the right condition**.

## 2. Principle: Synchronize Tests on Signals, Not Time Guesses

Every asynchronous test should answer four questions:

1. **Trigger:** what action starts the flow? For example, `input.send(...)`.
2. **Observable:** what event can be observed? A message on an output channel, a callback, a DB row, an `ErrorMessage`, a completion signal, or a metric?
3. **Completion condition:** what suffices to deem the scenario finished? For example, receiving the matching `eventId` with status `COMPLETED`.
4. **Timeout budget:** if the condition never occurs, how long should we wait at most and what failure message should be reported?

~~~mermaid
flowchart TD
    A[Test sends message] --> B[Async channel / scheduler / poller]
    B --> C{Completion condition met?}
    C -->|Yes| D[Assert payload, headers, and side effects]
    C -->|No| E{Timeout expired?}
    E -->|No| C
    E -->|Yes| F[Fail with eventId and observed state]
~~~

**Distinguish test wait timeouts from business timeouts.** `receive(3_000)` means the test is willing to wait up to 3 seconds to observe a message on the queue. It does not alter a Delayer's delay, change a Gateway's `replyTimeout`, or cancel the consumer on expiration.

### Tool Selection Table

| Test Goal | Appropriate Tool | Things to Watch Out For |
| --- | --- | --- |
| Wait for a message on a queue | `PollableChannel.receive(timeout)` | Verify payload/headers and exact channel |
| Wait for a callback/handler invocation | `CountDownLatch.await(timeout)` | Create a fresh latch per test |
| Wait for final state in DB or in-memory state | Awaitility `untilAsserted(...)` | Condition must be observable and thread-safe to check |
| Wait for a Java task result | `CompletableFuture.get(timeout)` | Calling `get` may throw `ExecutionException` |
| Coordinate ordering between two threads | Two `CountDownLatch`es or `Phaser` | Use entered/release signals, not sleep to "time" threads |
| Test pure deadline logic | Inject `Clock`, use `Clock.fixed(...)` | Controls only business-logic clock, not Spring's scheduler automatically |
| Test retries and errors | Probe/spy + output/error channel | Assert attempt count and final outcome, avoid log-only checks |
| Guard the whole test from hanging | JUnit `@Timeout` | Safety net only, never replaces asserting completion |

## 3. Complete Example: `ExecutorChannel` and `QueueChannel.receive(timeout)`

The flow below hands the message off to an executor, uppercases the payload, and delivers it to a queue. Because the handler runs on another thread, the producer's `send(...)` **does not prove** the message has reached `async.out`.

Required dependencies when using Spring Boot:

- `spring-boot-starter-integration` for the Spring Integration DSL.
- `spring-boot-starter-test` for JUnit 5/Spring Test.

### 3.1. Flow Configuration

~~~java
import java.util.Locale;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class AsyncPatternTestConfig {

    @Bean(name = "asyncTestExecutor", destroyMethod = "shutdown")
    public ExecutorService asyncTestExecutor() {
        return Executors.newFixedThreadPool(2);
    }

    @Bean("async.in")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean("async.workers")
    public MessageChannel workers(
            @Qualifier("asyncTestExecutor") Executor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean("async.out")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow asyncFlow() {
        return IntegrationFlow.from("async.in")
                .channel("async.workers")
                .handle(String.class, (payload, headers) ->
                        payload.toUpperCase(Locale.ROOT))
                .channel("async.out")
                .get();
    }
}
~~~

In this example:

| Component | Responsibility |
| --- | --- |
| `DirectChannel` at `async.in` | Producer sends requests into the flow |
| `ExecutorChannel` | Hands off execution to the executor |
| Handler | Returns the transformed payload |
| `QueueChannel` at `async.out` | Buffers output messages for the test to receive with a timeout |

The `ExecutorService` bean is shut down by Spring on context close, avoiding leaked threads after tests. In production, use `ThreadPoolTaskExecutor` with bounded concurrency/queue capacity rather than this sample executor.

### 3.2. JUnit: Waiting for the Exact Output Message

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(AsyncPatternTestConfig.class)
class AsyncPatternFlowTest {

    @Autowired
    @Qualifier("async.in")
    MessageChannel input;

    @Autowired
    @Qualifier("async.out")
    PollableChannel output;

    @Test
    @Timeout(10)
    void receivesResultWithoutArbitrarySleep() {
        assertTrue(input.send(
                MessageBuilder.withPayload("order-501")
                        .setHeader("eventId", "event-501")
                        .setHeader("correlationId", "order-501")
                        .build()));

        Message<?> result = output.receive(5_000);

        assertNotNull(result, "No message received within 5 seconds");
        assertEquals("ORDER-501", result.getPayload());
        assertEquals("event-501",
                result.getHeaders().get("eventId"));
        assertEquals("order-501",
                result.getHeaders().get("correlationId"));
    }
}
~~~

`receive(5_000)` **returns immediately** as soon as a message is in the queue; it does not force the test to wait the full 5 seconds. If the timeout expires, it returns `null` so the test fails with a concrete reason.

**Why assert headers?** Transformers/Service Activators may construct a new message. `MessageHeaders.ID` may change, while business headers `eventId` and `correlationId` must remain intact (unless logic intentionally modifies them). Checking the matching event prevents a test from accidentally consuming another test's message.

### Why Should You Not Assert Empty Output Right After `send()`?

~~~java
assertTrue(input.send(message));
assertNull(output.receive(0)); // May fail if the executor finished too fast.
~~~

A very fast task can emit its output before `receive(0)` executes. That is a race between the test thread and worker thread, not necessarily a flow bug. Assert "no message yet" only when backed by a **reliable synchronization signal** or a well-defined business deadline.

## 4. `CountDownLatch`: Waiting for a Handler-Signaled Milestone

To prove a handler actually started and control when it completes, use **multiple latches**:

- `entered`: worker signals "I have entered the handler."
- `allowFinish`: test permits the worker to proceed.
- `completed`: worker signals "I have finished processing."

~~~mermaid
sequenceDiagram
    participant T as Test thread
    participant W as Worker thread
    T->>W: Send message
    W->>T: entered.countDown()
    T->>T: entered.await(timeout) == true
    Note over W: Wait for allowFinish
    T->>T: Assert not yet completed
    T->>W: allowFinish.countDown()
    W->>T: completed.countDown()
    T->>T: completed.await(timeout) == true
~~~

### 4.1. Probe Used in the Test

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class GatedHandlerProbe {
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch allowFinish = new CountDownLatch(1);
    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicReference<String> result = new AtomicReference<>();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();

    public void handle(String payload) {
        entered.countDown();
        try {
            if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test gate timed out");
            }
            result.set(payload.toUpperCase(java.util.Locale.ROOT));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            failure.set(ex);
        } catch (RuntimeException ex) {
            failure.set(ex);
        } finally {
            completed.countDown();
        }
    }

    public boolean awaitEntered() throws InterruptedException {
        return entered.await(3, TimeUnit.SECONDS);
    }

    public void release() {
        allowFinish.countDown();
    }

    public boolean awaitCompleted() throws InterruptedException {
        return completed.await(3, TimeUnit.SECONDS);
    }

    public boolean isCompleted() {
        return completed.getCount() == 0;
    }

    public String result() {
        return result.get();
    }

    public Throwable failure() {
        return failure.get();
    }
}
~~~

Note: a `CountDownLatch` **cannot be reset**. Each test case should create a fresh probe/context, or manage lifecycle cleanup so a latch from a prior test does not start at 0.

### 4.2. Wiring the Probe into an Asynchronous Flow

~~~java
// The methods below belong in a @Configuration class
// annotated with @EnableIntegration, using a declared Executor.

@Bean
GatedHandlerProbe gateProbe() {
    return new GatedHandlerProbe();
}

@Bean("gate.in")
MessageChannel gateInput() {
    return new DirectChannel();
}

@Bean("gate.async")
MessageChannel gateExecutorChannel(
        @Qualifier("asyncTestExecutor") Executor executor) {
    return new ExecutorChannel(executor);
}

@Bean
IntegrationFlow gatedFlow(GatedHandlerProbe gateProbe) {
    return IntegrationFlow.from("gate.in")
            .channel("gate.async")
            .handle(gateProbe, "handle")
            .get();
}
~~~

This snippet **extends** `AsyncPatternTestConfig` from section 3, reusing `asyncTestExecutor` and the declared Spring/Executor imports. Do not copy it verbatim into an empty Java class and treat it as a standalone flow.

### 4.3. Testing Exact Ordering Without Timing Guesses

~~~java
@Test
@Timeout(10)
void handlerWaitsForExplicitRelease() throws Exception {
    // Beans "gate.in" and GatedHandlerProbe are injected from context.
    try {
        assertTrue(gateInput.send(
                MessageBuilder.withPayload("order-502").build()));

        assertTrue(gateProbe.awaitEntered(), "Worker has not entered handler");
        assertFalse(gateProbe.isCompleted(),
                "Handler completed before test released the gate");

        gateProbe.release();

        assertTrue(gateProbe.awaitCompleted(), "Handler has not completed");
        assertNull(gateProbe.failure());
        assertEquals("ORDER-502", gateProbe.result());
    } finally {
        gateProbe.release(); // Ensure worker does not hang if an assertion fails.
    }
}
~~~

The JUnit snippet above assumes `gateInput` (bean `gate.in`) and `gateProbe` are injected fields; it is an additional method for a test class, not a complete test class. It proves a **happens-before/after relationship** using synchronization signals instead of assuming "after 200 ms the handler has surely started."

## 5. Awaitility: Waiting for Final State with Repeated Assertions

When the outcome lives in a database, cache, or service status, there may be no `PollableChannel` to `receive` from. Awaitility waits on a **continuously evaluated condition** and returns immediately once the condition holds.

Example test-only dependency (Maven):

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <scope>test</scope>
</dependency>
~~~

Declare a compatible version in dependency management, or specify `<version>` directly if the project does not manage this dependency.

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

// repository.findStatus(eventId) is the example status-query API.
await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() ->
                assertEquals("COMPLETED",
                        repository.findStatus("event-501")));
~~~

**Unlike sleep:** if the DB returns `COMPLETED` after 120 ms, the test finishes in a few poll cycles rather than always waiting 5 seconds. On failure, Awaitility reports condition timeout along with the expected assertion failure.

To avoid false-positive tests:

- The condition must reflect the **actual state** of the flow, not a flag set before processing completes.
- When querying a DB, the query must read committed state, not uncommitted changes inside the test's own transaction.
- A repeatedly polled condition must be thread-safe; for mutable in-memory state, use `AtomicReference` or proper synchronization.
- Avoid overly aggressive polling that overloads the DB; `50 ms` is only an example for small tests.
- Never trigger business actions inside an Awaitility predicate. Predicates should **read/observe**, never create additional side effects.

### Testing Retry: Wait for Final State, Not Guessed Seconds

~~~java
await()
        .atMost(Duration.ofSeconds(8))
        .untilAsserted(() -> {
            assertEquals("DONE", statusStore.findStatus("event-retry-1"));
            assertEquals(3, attemptCounter.get());
        });
~~~

The example assumes the test deliberately configured the handler to fail on the first two attempts and succeed on the third. Make sure `attemptCounter` counts only this specific event or is keyed by `eventId`; sharing one global counter when multiple messages run concurrently easily breaks assertions.

### Never Use Awaitility to Prove an Event Never Happens Forever

Asserting "no message within 100 ms" only proves **none was observed during a 100 ms window**. To prove a Filter dropped a message, observe both the output and **a completion signal** (for example, the Filter's discard channel received the message with matching `eventId`). Once you know the flow terminated on the discard branch, there is no need to wait arbitrarily to guess the main output is empty.

## 6. Testing Filter and Router: Observing the Right Branch

With a Filter, Router, or Aggregator, a message may not appear on the default channel because of **correct branching logic**, not a broken flow. Never assert merely "output is empty."

### Example Filter Test Criteria

~~~text
Input: order.status = CANCELLED, eventId = order-503
Expected:
  - discard channel receives exact eventId = order-503
  - accepted channel does not receive this eventId
  - no notification side effect occurs
~~~

Test pattern with two destination `PollableChannel`s:

~~~java
Message<?> discarded = discardChannel.receive(3_000);
assertNotNull(discarded, "Filter has not completed discard branch");
assertEquals("order-503", discarded.getHeaders().get("eventId"));

// Use discard as the completion signal instead of Thread.sleep(...).
// Verifying zero side effects requires a matching probe or repository.
assertEquals(0, sendProbe.countFor("order-503"));
~~~

This snippet assumes the Filter has a `discardChannel`, `sendProbe` is a thread-safe test double, and no other branch still processes the same `eventId` after discard. In a complex flow with parallel fan-out branches, wait for **all relevant branches to complete** before asserting no side effect occurred.

### With a Router

- Send a message with header `priority=HIGH` and a distinct `eventId`.
- Wait specifically on `highPriorityChannel` for that message.
- Assert payload, headers, and target branch.
- Intentionally test the default/unresolved branch instead of merely saying "no message seen."

To run tests independently in parallel, use isolated contexts/channels or scenarios with unique keys; if multiple messages share a `QueueChannel`, tests must filter/correlate or control the producer.

## 7. Splitter and Aggregator: Wait for **All Elements**, Never Sleep

A Splitter can emit N messages; each message may traverse a different executor. The Aggregator releases when the group condition is satisfied, typically based on sequence metadata or a defined release strategy.

~~~mermaid
flowchart LR
    A[Input batch] --> S[Splitter]
    S --> B1[Item 1]
    S --> B2[Item 2]
    S --> B3[Item 3]
    B1 --> E[Async handlers]
    B2 --> E
    B3 --> E
    E --> G[Aggregator]
    G --> O[Aggregated output]
~~~

**Good test criteria:**

1. Wait for **one aggregated result** via `output.receive(timeout)`.
2. Assert item count and the set of IDs/payloads, without assuming order if the flow does not mandate it.
3. Assert the appropriate `correlationId` or group key.
4. Test missing elements, duplicates, timeouts, or custom release strategies.

Example asserting the result set (assuming the aggregator returns a `List` of Strings):

~~~java
Message<?> aggregate = aggregatedOutput.receive(5_000);
assertNotNull(aggregate, "Aggregator did not release within timeout");

@SuppressWarnings("unchecked")
java.util.List<String> payloads =
        (java.util.List<String>) aggregate.getPayload();

assertEquals(3, payloads.size());
assertEquals(
        java.util.Set.of("A", "B", "C"),
        new java.util.HashSet<>(payloads));
~~~

If your application's Aggregator returns a domain object or `List<Message<?>>` instead of `List<String>`, assert against the **actual output contract**. When ordering has business significance, configure an explicit resequencing/ordering strategy and assert order; never arbitrarily compare `List`s when ordering is not guaranteed.

### Avoid Assuming Parallel Messages "Will Surely Finish in 500 ms"

The Aggregator's release condition, per-branch retries, and scheduler speed determine when a result appears. A sleep cannot distinguish "still waiting for parts" from "a part failed and went to the error channel." Tests should observe both the **result channel** and the **error path**.

## 8. Testing Delayer: Combining Deadlines with Release Signals

A Delayer intentionally waits for a duration or absolute timestamp. To test "never releases too early," both measure elapsed time **and wait for actual output**, rather than sleeping and checking the clock.

~~~java
import java.util.concurrent.TimeUnit;

long started = System.nanoTime();

assertTrue(input.send(
        MessageBuilder.withPayload("PAYMENT-REMINDER")
                .setHeader("delayMs", 700L)
                .build()));

Message<?> released = output.receive(3_000);
assertNotNull(released, "Message must be released within timeout");

long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - started);
assertTrue(elapsedMs >= 700L, "Must not release before delay expires");
~~~

The example assumes the Delayer uses expression `headers['delayMs']` and an output queue. `System.nanoTime()` is suited for measuring **elapsed durations within the same process**; never use it as a UTC timestamp to store in a database or compare across machines.

**Limitation of timing tests:** if the test thread is paused for a long time right after `send`, the measurement above could miss a premature release. For deadline logic requiring high precision, attach a **probe at the release point** to capture the actual release time, or test deadline calculation separately with a controllable clock/scheduler.

### A Fake `Clock` Does Not Automatically Make Delayer Run Immediately

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-21T10:00:00Z"),
        ZoneOffset.UTC);

boolean expired = !Instant.parse("2026-11-21T09:59:00Z")
        .isAfter(fixed.instant());
assertTrue(expired);
~~~

This snippet tests **application deadline-comparison logic**. It does not affect the Delayer's `TaskScheduler` unless the scheduler itself was designed to use that controllable clock. Never swap `Clock` in a service and assume every Spring Integration scheduled task "fast-forwards" accordingly.

For complex scheduling, a testable design separates:

- **Due-time calculation:** pure function or service accepting `Clock`, testable via `Clock.fixed(...)`.
- **Task scheduling:** an adapter around `TaskScheduler` that can be mocked/captured at `schedule(...)` time.
- **Task execution:** testing that the callback runs properly and the endpoint emits messages per contract.
- **Real integration:** a small number of tests with a real scheduler, bounded timeouts, and sensible headroom.

## 9. Testing Retry and Error Channel Without Relying on Logs

When a handler uses retry, observable events include:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant F as Retry-enabled Flow
    participant C as Handler
    participant E as Error Channel
    T->>F: Message(eventId=evt-901)
    F->>C: Attempt 1
    C--xF: Temporary error
    F->>C: Attempt 2
    C--xF: Temporary error
    F->>C: Attempt 3
    alt Succeeds
       C-->>F: Result
       F-->>T: Success output observable
    else Retries exhausted
       F->>E: ErrorMessage
       E-->>T: Error observable
    end
~~~

With `RequestHandlerRetryAdvice` or retry on a Delayer, how you observe depends on where retries execute. A test should have:

- A thread-safe counter keyed by **`eventId`**, never one global counter when multiple messages run concurrently.
- An output channel for success.
- An error channel or durable DLQ/spy for the failure branch.
- An overall timeout budget aligned with attempt count, backoff, and handler timeout.

Example when recovery is **configured** to emit an `ErrorMessage` to `PollableChannel errors`:

~~~java
Message<?> failed = errors.receive(5_000);
assertNotNull(failed, "No error message observed after retry");
assertInstanceOf(
        org.springframework.messaging.support.ErrorMessage.class, failed);
assertInstanceOf(Throwable.class, failed.getPayload());
assertEquals(3, attemptsByEvent.get("evt-901").get());
~~~

This snippet **does not configure retry/error channels by itself**: you need a flow routing errors into `errors` (such as `ErrorMessageSendingRecoverer` on `RequestHandlerRetryAdvice`), and message `evt-901` must intentionally fail three times. With a synchronous `DirectChannel` lacking a recoverer, exceptions propagate to the caller instead of automatically hitting the global `errorChannel`.

### Testing Non-Retryable Branches

A message with an invalid schema payload should typically be rejected/quarantined **immediately**, without retrying multiple times. Test by:

1. Sending a deterministic invalid message with `eventId`.
2. Waiting on the observable in the quarantine/error branch.
3. Asserting the cause, metadata, and total handler invocation count (e.g., 1).
4. Verifying zero business side effects.

**Note:** if `errors.receive(5_000)` times out with no message, the cause might be misconfigured error routing, the handler never running, or the test sending to the wrong channel. Include diagnostic context like `eventId` and executor/flow state to tell causes apart.

## 10. Concurrent Messages: Distinguishing Outcomes by Identity

In asynchronous flows, completion order can differ from send order. For example, message B with a fast handler may finish before A even though it was sent second.

~~~text
Send:     A -----> B -----> C
Complete:      B -----> C -----> A
~~~

Do not assert FIFO if the architecture does not guarantee FIFO. Assert **result sets and identity**:

~~~java
java.util.Set<String> expected =
        java.util.Set.of("event-A", "event-B", "event-C");
java.util.Set<String> actual = new java.util.HashSet<>();

for (int i = 0; i < expected.size(); i++) {
    Message<?> result = output.receive(5_000);
    assertNotNull(result, "Missing message on output");
    actual.add((String) result.getHeaders().get("eventId"));
}

assertEquals(expected, actual);
~~~

To prove **exactly one message per `eventId`**, check for absence of duplicates using a strong observable: consumer counters, unique constraints in an inbox, total side-effect count, or synchronized completion signals. A single `receive(0) == null` right after reading three messages is just an instantaneous snapshot—it **does not prove no duplicate will arrive in the future**.

### Test Isolation

- Create separate contexts/channels per test when shared queues exist, or use `@DirtiesContext` if needed.
- If sharing a context, reset probes/counters per event ID before each test and ensure no workers remain from previous tests.
- Use a unique `eventId` per test; never use short payloads like `"hello"` as unique identifiers.
- Clean up test queues/DBs in a controlled way; avoid deleting data belonging to other tests.
- Shut down executors and contexts after tests so no background threads keep running past assertions.

## 11. Testing Gateways and Asynchronous Request/Reply

A Gateway waits for a reply up to a configured duration. If the flow crosses a Delayer or executor and responds late, the Gateway can time out even while downstream continues running.

**Distinguish:**

| Event | What Does It Prove? |
| --- | --- |
| Producer/Gateway sends request successfully | Flow accepted the request at the input contract level |
| Gateway `replyTimeout` expires | Caller did not receive a reply before the deadline |
| Final handler finishes | Business side effect may have completed |
| Reply arrives after timeout | Caller may no longer be waiting for the result |

When testing:

1. Configure an explicit `replyTimeout` on the Gateway and an explicit delay downstream.
2. Use `assertThrows` or check the return value matching `errorOnTimeout`/Gateway contract.
3. Wait on **an independent downstream probe** to verify work continues or is cancelled per design, rather than relying solely on caller timeout.
4. Use `eventId` to inspect post-timeout outcomes if the application supports status queries.

For long-running workflows, design requests to return an **accepted ACK**, then deliver results via messages, callbacks, or status polling rather than holding a synchronous Gateway open for minutes.

## 12. Timeout Budgets, Error States, and CI Flakiness

Too short a timeout causes failures on busy machines; too long delays error detection. Choose deadlines based on **actual flow configuration** with deliberate headroom.

Example:

~~~text
Default Delayer delay:            300 ms
Handler retry: 3 attempts, 2 x 100 ms backoff
Per-stub-call limit:              200 ms
Expected max logical duration:    300 + 600 + 200 = 1,100 ms
Suggested test timeout (example): 3,000 ms
~~~

These numbers are illustrative, not Spring Integration SLAs. If CI is slow or real network/database I/O is involved, pick an appropriate timeout; never tune arbitrary sleeps to "fix" tests.

### Preserving Diagnostics on Failure

A helpful assertion should report:

- Which `eventId` failed to complete.
- Which channel or branch was being awaited.
- How many retry attempts were observed.
- Current state of the queue, DB, or consumer.
- Configured timeout and business expectation.

Example:

~~~java
Message<?> result = output.receive(3_000);
assertNotNull(result, "event-501: no output after 3s on async.out");
~~~

JUnit `@Timeout(10)` is a **guard against hung tests**. It does not replace `receive(timeout)` or `latch.await(timeout)`, because completion conditions still require explicit assertions.

### Common Causes of Flaky Async Tests

| Symptom | Common Root Cause | Fix |
| --- | --- | --- |
| Passes locally, fails on CI | Relies on sleep, overly tight timeout, busy CI host | Wait on observables; add justified timeout headroom |
| Occasionally receives wrong message | Shared `QueueChannel` across tests | Isolate contexts or correlate by `eventId` |
| Fails with wrong counter | One shared counter across multiple messages | Count by `eventId`, reset/isolate state |
| "No output" assertion fails intermittently | Observation timing not synchronized | Use gate/latch or branch completion signal |
| Aggregator test never releases | Missing element, wrong correlation ID, release strategy unmet | Check full message set, group, and error path |
| Test hangs indefinitely | Latch not released on assertion failure, executor still running | `try/finally` gate release, timeouts, and shutdown |
| Delayer test fires late | `TaskScheduler` under load or host paused | Measure deadline/release via probe and generous timeout |
| Error channel test sees nothing | Sync error propagated to caller or recovery unconfigured | Verify sync/async boundary |
| Test sees DB data but consumer does not | Test transaction uncommitted or wrong resource | Place transaction boundary properly and observe post-commit |

## 13. Checklist for Designing an Async Pattern Test

Before running a test, check:

1. **Each test has a deterministic input** with a clear `eventId`.
2. **Completion condition is defined** via message, callback, DB row, or probe.
3. **Maximum timeout exists**; no unbounded waits.
4. **Assertions cover payload, headers, routing, and side effects**, not merely `send() == true`.
5. **Success, discard, and error paths** are handled explicitly; never assume `errorChannel` catches every exception.
6. **State across tests is isolated**; no lingering workers from earlier runs.
7. **Thread boundaries are clear** across `DirectChannel`, `ExecutorChannel`, pollers, and brokers.
8. **For Delayer/retry**, distinguish **time logic** from **actual execution scheduling**.
9. **For Splitter/Aggregator**, verify correlation, sequence, and release strategy; never assume ordering under concurrency.
10. **On failure**, test output provides enough info to diagnose **which step got stuck**.

## 14. Practice Exercises

1. Replace `Thread.sleep(2_000)` in an `ExecutorChannel` test with `PollableChannel.receive(timeout)`. Compare runtime on a fast machine vs. CI.
2. Use two `CountDownLatch`es to prove a handler has entered yet not completed before the test signals permission to proceed.
3. Use Awaitility to wait for a DB row transition `PENDING → COMPLETED` after an asynchronous `IntegrationFlow`.
4. Build a Filter routing `CANCELLED` orders to a discard channel. Write a test verifying the discard signal and zero email-sending side effects.
5. Build a priority Router and send three messages with distinct `eventId`s. Assert the message set on each branch regardless of completion order.
6. Split a three-item list and aggregate it. Wait for the aggregated result instead of sleeping, verifying the item set and correlation key.
7. Have a handler fail twice and succeed on the third attempt; wait on the success channel and assert the per-`eventId` attempt counter.
8. Have a handler fail permanently while recovery emits an `ErrorMessage`; wait on the error queue and assert the exception and original message.
9. Test a Delayer waiting 700 ms. Measure release via an output probe and analyze limitations when the test thread is preempted by the OS scheduler.
10. Test a Gateway timing out before downstream finishes. Use a separate probe to verify downstream continues executing per policy.
11. Run async tests in parallel while intentionally sharing a queue. Diagnose cross-test interference and fix it with context isolation/event IDs.
12. Measure test execution time before and after switching to event-driven waiting; check flakiness rates across multiple CI runs.

### Self-Check Questions

- Why does `Thread.sleep(...)` fail to establish causality between producer and consumer?
- How does `PollableChannel.receive(timeout)` differ from sleeping?
- When should you use `CountDownLatch` instead of `Awaitility`?
- Why must you observe a completion signal before asserting "no side effect"?
- Why should an `Aggregator` test not assume FIFO when branches run on separate executors?
- Does using `Clock.fixed(...)` make Spring Integration's `TaskScheduler` run faster?
- Could a missing `ErrorMessage` stem from a synchronous exception or misconfiguration—and where?
- Under retry, which ID should you key attempt counts by to avoid mixing messages?
- Why does a Gateway timeout not prove the business operation failed?

## References

- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): Spring Integration testing tools and test context setup.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, and `QueueChannel`.
- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): schedulers, delay durations, and message release.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous vs. asynchronous errors, `ErrorMessage`, and error channels.
- [JUnit 5 User Guide — Timeouts](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts): preventing hung tests with `@Timeout`.
- [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage): waiting on conditions with `await()` and assertion styles.
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordinating threads via `countDown`/`await` signals.

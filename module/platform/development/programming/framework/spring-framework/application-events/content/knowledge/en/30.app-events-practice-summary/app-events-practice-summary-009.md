# Simulating Failures and Retries in Spring Framework Application Events

An `ApplicationEventPublisher.publishEvent(...)` call is not a durable message queue and **does not automatically retry all listeners** when processing fails. In Spring Framework, ordinary `@EventListener` methods are invoked synchronously by default; an unhandled exception can propagate back to the publisher and halt the multicast loop. With `@Async @EventListener`, errors typically occur on a worker thread and do not flow directly back to the `publishEvent` call. With `@TransactionalEventListener(AFTER_COMMIT)`, listener errors occur **after the source transaction has committed**, so rolling back the source transaction cannot be used to "retry".

**Simulating failures and retries** is the practice of intentionally creating these scenarios in tests to prove the system distinguishes transient errors, permanent errors, exhausted retries, lost acknowledgments after a side effect occurred, and crashes/rollbacks. The goal is to learn how to place retries at **the right boundary**, assert attempt counts, keep a stable `eventId`, prevent duplicate side effects, and know when durable publication storage is required.

This lesson moves from the conceptual model to a Java 17+ test suite with **Spring Framework, Spring Retry, and JUnit 5**. The suite calls real `ApplicationEventPublisher` and `@EventListener` components while simulating transport failures with a controlled fake—**without random timing, real networks, or `Thread.sleep`**. Limits regarding transactions, `@Async`, outboxes, and Spring Modulith are covered separately so in-memory retries are not confused with end-to-end reliability.

## 1. Distinguishing Failures Across Different Layers

Not every `publishEvent` failure shares the same root cause:

| Failure location | Example | Who observes the error | Implication for retries |
| --- | --- | --- | --- |
| Before publish | Invalid command validation | Service/caller | Usually **do not** retry until input is fixed |
| Synchronous listener | `@EventListener` throws `IllegalStateException` | Publisher, if exception is unhandled | Can retry the specific operation; avoid blindly republishing |
| Asynchronous listener | `@Async` method throws exception | Async exception handler / worker telemetry | Caller does not know by default; needs dedicated state/error channel |
| Post-commit listener | `AFTER_COMMIT` gateway call times out | Callback/worker | Source transaction already committed; retry secondary work |
| At task submission | Executor full, `TaskRejectedException` | Can occur on the submitting thread | Must handle overload; distinct from listener body errors |
| External transport | HTTP 503, timeout, connection reset | Handler/gateway | Can retry **if** request is safe and bounded |
| Data or permissions | Invalid schema, 400, permanent permission denied | Handler/gateway | Route to permanent failure / quarantine |
| After side effect | Gateway wrote data but ACK timed out | Handler sees error/unknown outcome only | Retrying can duplicate; needs idempotency/reconciliation |
| After process crash | Event lived only in RAM or executor queue | No worker left to report errors | `RetryTemplate` is insufficient; needs durable record/outbox |

**Note:** `publishEvent` does not return a `Future` aggregating results across all listeners. One event can have multiple listeners; retrying **the entire publish call** can re-run listeners that already succeeded when only one listener failed.

## 2. Retry Model at the Right Boundary

Suppose a `ReceiptRequested(eventId, orderId)` event triggers sending a receipt. The flow should be understood as:

~~~text
publishEvent(ReceiptRequested)
        |
        +-- @EventListener ReceiptHandler   [single dispatch]
                |
                +-- RetryTemplate.execute(...)
                       |
                       +-- attempt 1 -> gateway: transient failure
                       +-- attempt 2 -> gateway: transient failure
                       +-- attempt 3 -> gateway: success
                |
                +-- handler finishes

eventId remains unchanged across attempts.
Handler invocation count = 1.
Gateway attempt count = 3.
Business side effect count = 1.
~~~

We retry **the safely repeatable operation**, rather than blindly retrying event publication across the whole application context.

A solid retry policy must answer:

1. Which exceptions are retried? Is the cause chain inspected?
2. What is the maximum number of **attempts**, including the first try?
3. Are backoff/jitter and a deadline configured?
4. Which errors must stop immediately?
5. When attempts are exhausted, where is state recorded? Who sees and handles it?
6. If the side effect succeeded but the response was lost, is the retry idempotent?
7. Do retries survive application restarts or exist only in the current call stack?

### Retry Is Not Replay or Recovery

- **In-call retry:** `RetryTemplate` or `@Retryable` re-invokes the operation inside the same process.
- **Replay/resubmission:** re-queuing an unfinished logical event/publication for processing (often after a restart).
- **Recovery:** restoring failed work using durable records, attempt/status tracking, retry policies, and idempotency.
- **Compensation:** executing a compensating business action when a side effect already happened and cannot be rolled back.

An in-memory retry cannot recover a task lost during a process crash.

## 3. How Does Spring Framework Handle Listener Errors?

### 3.1. Synchronous Listeners and Exception Propagation

Without an executor configured on the multicaster, `SimpleApplicationEventMulticaster` usually invokes listeners on the publisher's thread. Example:

~~~java
@EventListener
public void onReceipt(ReceiptRequested event) {
    throw new IllegalStateException("gateway unavailable");
}
~~~

This is an **excerpt** from a Spring-managed bean, not a standalone Java file. When the exception is uncaught and no `ErrorHandler` handles it, it can propagate out of `publisher.publishEvent(...)`:

~~~java
try {
    publisher.publishEvent(new ReceiptRequested("evt-1", "ORD-1"));
} catch (IllegalStateException ex) {
    // Under default synchronous dispatch, the caller observes the error here.
}
~~~

If the same event has multiple listeners, an exception from one listener can prevent subsequent listeners from running. `@Order` sets invocation priority but does not isolate errors or coordinate retries. `SimpleApplicationEventMulticaster.setErrorHandler(...)` can alter whether exceptions are suppressed or propagated; do not extrapolate default behavior to every application.

### 3.2. `@Async` Listeners and Exception Propagation

~~~java
@Async("eventsExecutor")
@EventListener
public void onReceiptAsync(ReceiptRequested event) {
    gateway.send(event);
}
~~~

This is an **excerpt** requiring `@EnableAsync`, an executor bean, and a gateway. An exception thrown inside a `void` `@Async` listener is typically passed to `AsyncUncaughtExceptionHandler` or logged; it is **not thrown directly back to the `publishEvent` caller**. Therefore:

~~~java
publisher.publishEvent(event);
assertDoesNotThrow(...); // Does NOT prove the async listener succeeded.
~~~

The second assertion only illustrates a **false inference**, not a standalone test. To test async execution, use a `BlockingQueue`, `CompletableFuture`, latch, or Awaitility with a timeout to capture actual results and exceptions.

**Distinction:** if the executor rejects a task **at submission time**, the publisher can observe `TaskRejectedException`; that differs from exceptions thrown *after* a worker begins executing.

### 3.3. `AFTER_COMMIT` and Rollback

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` runs as a callback after the source transaction commits. It does not run when the source transaction rolls back; without a transaction, the callback does not run by default unless `fallbackExecution=true`. When post-commit processing fails, the source transaction is already finished: there is no mechanism to "throw an exception to roll back the old commit".

If the callback writes to the DB, open a new transaction for that write (such as `REQUIRES_NEW`/`TransactionTemplate`) because old transactional resources may remain bound in the callback without any further commit.

## 4. Choosing Retryable vs. Permanent Failures

A simple classification for this practice:

| Error category | Examples | Typically appropriate policy |
| --- | --- | --- |
| **Transient** | Network reset, HTTP 503, DB deadlock/lock timeout, rate limit with retry guidance | Bounded retries with backoff + jitter and deadline |
| **Permanent** | Invalid payload schema, permanently missing ID, permission error unfixable by retrying | Do not auto-retry; record reason, alert |
| **Unknown outcome** | HTTP timeout after request was accepted | Reconcile / check idempotency before deciding to retry |
| **Overload** | Executor queue full, downstream saturation | Rate limiting / backpressure; avoid retry storms |
| **Programming bug** | `NullPointerException` from faulty code, broken invariant | Fix code/data; do not retry endlessly |

Never write a "retry every `Exception`" policy just to make tests pass. Many permanent errors will be retried unnecessarily, increasing load and potentially causing harm. Conversely, an external API error after **a side effect already succeeded** must not be treated as "nothing happened".

### Attempt Counts and Backoff

`maxAttempts(3)` means **one initial call and at most two retries**, not three retries plus one initial call. In the lab, `noBackoff()` is used solely for fast, deterministic attempt-count testing. **Production generally needs exponential backoff + jitter**:

~~~java
// Spring Retry 2.x excerpt, policy for real runtime:
RetryTemplate retry = RetryTemplate.builder()
    .maxAttempts(5)
    .retryOn(TransientFailure.class)
    .exponentialBackoff(200, 2.0, 5_000, true)
    .build();
~~~

Requires importing `org.springframework.retry.support.RetryTemplate` and the application's `TransientFailure`. Backoff is in milliseconds; with the final parameter `true`, the policy adds randomness to reduce synchronized retries. Do not put real backoff delays into unit tests that count attempts, as it makes tests unnecessarily slow and flaky.

## 5. Complete Lab: Spring Retry + `@EventListener` + JUnit 5

The test suite uses Java 17+, Spring Framework 6.2, Spring Retry 2.0.x, and JUnit Jupiter 5. **No Spring Boot, database, HTTP server, or broker is required.** Application events are dispatched by real Spring infrastructure; a fake transport simulates predictable failures.

We test five scenarios:

1. Transport fails twice, then succeeds on the third attempt.
2. Permanent failure: only one attempt, no retries.
3. Persistent transient failure: exhausts three attempts and the exception propagates synchronously to the publisher.
4. Side effect is recorded, yet the ACK is lost: retry calls transport a second time, and the **idempotency key** prevents duplicate side effects.
5. Another event with a different ID is handled independently: attempts and state never bleed across events.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'spring-event-fault-retry'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.retry:spring-retry:2.0.13'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-retry` is a separate dependency; **Spring Framework Application Events do not bundle Spring Retry**. If a project uses Spring Boot dependency management, prefer the Boot-managed compatible versions instead of forcing manual overrides. `spring-aop` is included for realistic deployment context; the lab uses `RetryTemplate` directly so `@EnableRetry` is unnecessary.

### 5.3. src/test/java/example/events/RetryEventTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RetryEventTest.Config.class)
class RetryEventTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired FakeGateway gateway;
    @Autowired RetryingListener listener;

    @BeforeEach
    void reset() {
        gateway.reset();
        listener.reset();
    }

    @Test
    void retriesTwoTransientFailuresThenSucceeds() {
        gateway.failFirst("evt-transient", 2);

        publisher.publishEvent(new SendRequested("evt-transient"));

        assertEquals(1, listener.invocations());
        assertEquals(3, gateway.attempts("evt-transient"));
        assertEquals(1, gateway.effects("evt-transient"));
    }

    @Test
    void permanentFailureIsNotRetried() {
        gateway.rejectPermanently("evt-invalid");

        PermanentFailure error = assertThrows(
            PermanentFailure.class,
            () -> publisher.publishEvent(
                new SendRequested("evt-invalid")
            )
        );

        assertEquals("invalid:evt-invalid", error.getMessage());
        assertEquals(1, listener.invocations());
        assertEquals(1, gateway.attempts("evt-invalid"));
        assertEquals(0, gateway.effects("evt-invalid"));
    }

    @Test
    void exhaustedTransientRetriesPropagateFailure() {
        gateway.failFirst("evt-down", 99);

        TransientFailure error = assertThrows(
            TransientFailure.class,
            () -> publisher.publishEvent(
                new SendRequested("evt-down")
            )
        );

        assertEquals("temporary:evt-down", error.getMessage());
        assertEquals(1, listener.invocations());
        assertEquals(3, gateway.attempts("evt-down"));
        assertEquals(0, gateway.effects("evt-down"));
    }

    @Test
    void lostAckDoesNotDuplicateAnIdempotentSideEffect() {
        gateway.loseAckOnceAfterEffect("evt-ack");

        publisher.publishEvent(new SendRequested("evt-ack"));

        assertEquals(1, listener.invocations());
        assertEquals(2, gateway.attempts("evt-ack"));
        assertEquals(1, gateway.effects("evt-ack"));
    }

    @Test
    void eventIdsHaveIndependentRetryState() {
        gateway.failFirst("evt-a", 1);

        publisher.publishEvent(new SendRequested("evt-a"));
        publisher.publishEvent(new SendRequested("evt-b"));

        assertEquals(2, listener.invocations());
        assertEquals(2, gateway.attempts("evt-a"));
        assertEquals(1, gateway.attempts("evt-b"));
        assertEquals(1, gateway.effects("evt-a"));
        assertEquals(1, gateway.effects("evt-b"));
    }

    record SendRequested(String eventId) {}

    static final class TransientFailure extends RuntimeException {
        TransientFailure(String message) {
            super(message);
        }
    }

    static final class PermanentFailure extends RuntimeException {
        PermanentFailure(String message) {
            super(message);
        }
    }

    public static final class FakeGateway {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();
        private final Map<String, AtomicInteger> failuresLeft =
            new ConcurrentHashMap<>();
        private final Map<String, AtomicInteger> effectCount =
            new ConcurrentHashMap<>();
        private final Set<String> permanentlyInvalid =
            ConcurrentHashMap.newKeySet();
        private final Set<String> loseAckOnce =
            ConcurrentHashMap.newKeySet();
        private final Set<String> completedKeys =
            ConcurrentHashMap.newKeySet();

        void failFirst(String eventId, int count) {
            failuresLeft.put(eventId, new AtomicInteger(count));
        }

        void rejectPermanently(String eventId) {
            permanentlyInvalid.add(eventId);
        }

        void loseAckOnceAfterEffect(String eventId) {
            loseAckOnce.add(eventId);
        }

        void send(String eventId) {
            calls.computeIfAbsent(
                eventId, ignored -> new AtomicInteger()
            ).incrementAndGet();

            if (permanentlyInvalid.contains(eventId)) {
                throw new PermanentFailure("invalid:" + eventId);
            }

            AtomicInteger remaining = failuresLeft.get(eventId);
            if (remaining != null &&
                    remaining.getAndUpdate(
                        n -> n > 0 ? n - 1 : 0
                    ) > 0) {
                throw new TransientFailure("temporary:" + eventId);
            }

            // Simulates a sink supporting idempotency key = eventId.
            if (completedKeys.add(eventId)) {
                effectCount.computeIfAbsent(
                    eventId, ignored -> new AtomicInteger()
                ).incrementAndGet();
            }

            // The request actually took effect, yet the ACK was "lost".
            if (loseAckOnce.remove(eventId)) {
                throw new TransientFailure("ack-lost:" + eventId);
            }
        }

        int attempts(String eventId) {
            AtomicInteger value = calls.get(eventId);
            return value == null ? 0 : value.get();
        }

        int effects(String eventId) {
            AtomicInteger value = effectCount.get(eventId);
            return value == null ? 0 : value.get();
        }

        void reset() {
            calls.clear();
            failuresLeft.clear();
            effectCount.clear();
            permanentlyInvalid.clear();
            loseAckOnce.clear();
            completedKeys.clear();
        }
    }

    public static final class RetryingListener {
        private final RetryTemplate retry;
        private final FakeGateway gateway;
        private final AtomicInteger listenerCalls = new AtomicInteger();

        RetryingListener(RetryTemplate retry, FakeGateway gateway) {
            this.retry = retry;
            this.gateway = gateway;
        }

        @EventListener
        public void on(SendRequested event) {
            listenerCalls.incrementAndGet();
            retry.execute(context -> {
                gateway.send(event.eventId());
                return null;
            });
        }

        int invocations() {
            return listenerCalls.get();
        }

        void reset() {
            listenerCalls.set(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        RetryTemplate retryTemplate() {
            return RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TransientFailure.class)
                .noBackoff() // Only for deterministic testing.
                .build();
        }

        @Bean
        FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        RetryingListener retryingListener(
                RetryTemplate retryTemplate, FakeGateway gateway) {
            return new RetryingListener(retryTemplate, gateway);
        }
    }
}
~~~

### 5.4. Running the Tests and Expected Results

If the project has a Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.RetryEventTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.RetryEventTest"
~~~

This test suite has **no fixed business stdout**. When passing, JUnit verifies the following outcomes:

| Test | Listener calls | Gateway attempts | Real side effects |
| --- | ---: | ---: | ---: |
| `retriesTwoTransientFailuresThenSucceeds` | 1 | 3 | 1 |
| `permanentFailureIsNotRetried` | 1 | 1 | 0 |
| `exhaustedTransientRetriesPropagateFailure` | 1 | 3 | 0 |
| `lostAckDoesNotDuplicateAnIdempotentSideEffect` | 1 | 2 | 1 |
| `eventIdsHaveIndependentRetryState` | 2 | evt-a: 2; evt-b: 1 | Per event: 1 |

Results do not depend on thread scheduling, network latency, or `Thread.sleep`. `FakeGateway` holds failure scenarios configured deterministically before publishing. `RetryTemplate` retries only `TransientFailure`; `PermanentFailure` passes straight through without retrying.

**Simulating a lost ACK is crucial:** inside `send`, the sink applies the side effect and records `completedKeys`; then the fake throws `TransientFailure("ack-lost:...")` to simulate the client missing the confirmation. The retry invokes the transport again, yet `completedKeys.add(eventId)` returns `false`, so the business effect **is applied only once**.

**Limit of the fake:** `completedKeys` lives only in the memory of the JUnit process. It illustrates the idempotency contract; it does not provide durability across restarts or across multiple replicas. Production must rely on DB unique constraints/atomic upserts, downstream gateway idempotency support, or proper reconciliation.

### 5.5. Why Not Retry by Calling `publishEvent()` Again?

A common anti-pattern:

~~~java
for (int i = 0; i < 3; i++) {
    try {
        publisher.publishEvent(new SendRequested(eventId));
        break;
    } catch (RuntimeException ex) {
        // try republishing the entire event
    }
}
~~~

This snippet **illustrates a risk**, not a recommended solution. If an event has three listeners and listener A succeeded while listener B failed, republishing invokes **both A and B** again. Nor can the publisher observe exceptions inside an async listener body this way.

Instead, retry **the operation inside handler B**, or track publications per `(eventId, handlerId)` via a registry/outbox. Whenever events are intentionally replayed, every listener must be designed to be idempotent.

## 6. Extended Practice: How Does `@Retryable` Differ from `RetryTemplate`?

Spring Retry supports both imperative `RetryTemplate` and annotation/AOP-based `@Retryable`:

~~~java
// Excerpt requiring @EnableRetry and a bean invoked through its proxy.
@Service
class ReceiptService {

    @Retryable(
        retryFor = TransientFailure.class,
        maxAttempts = 3
    )
    public void send(ReceiptRequested event) {
        gateway.send(event.eventId());
    }
}
~~~

This is an excerpt **not from the Section 5 test code**; it requires `@Service`, `@Retryable`, `TransientFailure`, `ReceiptRequested`, and `gateway` defined by the application. `@EnableRetry` (and appropriate AOP dependencies) must be configured.

**Self-invocation note:** if a method in `ReceiptService` calls `this.send(...)` in normal proxy mode, retry advice can be bypassed. For easy testing, place the retryable operation on another bean invoked through its Spring proxy, or use explicit `RetryTemplate` as in the lab. Never "slap on an annotation and guess" without verifying real attempt counts.

`@Recover` (if used) can alter behavior once attempts are exhausted; it can handle the exception rather than letting it propagate. A handler can look "successful" if `@Recover` silently swallows errors, so define the contract: does recovery execute a valid fallback/compensation or only log? When the outcome must be failure, record `FAILED/DEAD` state or throw according to policy rather than hiding it.

### Retries and Transaction Advice

When combining `@Retryable` and `@Transactional`, **advice ordering determines whether each attempt gets its own transaction or all retries share one transaction**. Do not rely on assumptions from annotation names; test rollback rules and real transaction boundaries.

For processing with DB writes, an easy-to-reason-about structure puts retries on **the outside**, with each attempt calling a transactional service method via a proxy or a separate `TransactionTemplate`. If an attempt fails and marks the transaction `rollbackOnly`, retrying within the same transaction can cause `UnexpectedRollbackException` or corrupt state.

Conceptual example (excerpt):

~~~java
retryTemplate.execute(context -> {
    transactionalWorker.processOneAttempt(event);
    return null;
});
~~~

`transactionalWorker` must be a real bean and `processOneAttempt` must have an explicit transaction contract. If the operation performs an external HTTP side effect outside the DB, the source transaction **cannot roll back that effect**; idempotency remains mandatory.

## 7. Simulating Failures in `@Async @EventListener`

When a listener runs asynchronously, prove failures via an observable channel with a timeout. A test-only design can use a `BlockingQueue<Outcome>` to capture results:

~~~java
record Outcome(String eventId, boolean success, Throwable error) {}

@Async("eventsExecutor")
@EventListener
public void onAsync(ReceiptRequested event) {
    try {
        gateway.send(event.eventId());
        outcomes.offer(new Outcome(event.eventId(), true, null));
    } catch (RuntimeException ex) {
        outcomes.offer(new Outcome(event.eventId(), false, ex));
        throw ex; // Error is handled by async exception handling.
    }
}
~~~

This is an **excerpt** requiring `@EnableAsync`, an executor, and the fixture's `outcomes` queue. In JUnit:

~~~java
publisher.publishEvent(new ReceiptRequested("evt-async", "ORD-1"));

Outcome outcome = outcomes.poll(5, TimeUnit.SECONDS);
assertNotNull(outcome, "async listener did not finish");
assertEquals("evt-async", outcome.eventId());
assertFalse(outcome.success());
assertInstanceOf(TransientFailure.class, outcome.error());
~~~

Snippets in this section are **guidelines to wire into a separate test fixture**, not standalone code. Do not add this async listener into the same context as `RetryEventTest`, as that would attach an extra listener to the same event and skew attempt counts in the main lab. Keep event IDs isolated per test, clear queues, and shut down executors with the Spring context lifecycle.

**Do not wait only on `started`:** the listener may enter the method and fail at a later step. The `Outcome` signal must be recorded after the step finishes or inside `catch`. In production, an in-memory `BlockingQueue` does not replace durable error tracking; it is purely a test-waiting tool with a timeout.

If a `void` `@Async` listener does not catch exceptions itself, configure `AsyncUncaughtExceptionHandler` for logging/metrics. `publishEvent` returning before the worker finishes is **never proof of success**.

## 8. Simulating Transaction Rollback and `AFTER_COMMIT`

An application service may write data and publish an event inside a transaction. If a synchronous listener fails and the exception escapes the service, the transaction typically rolls back for `RuntimeException` or `Error` under default Spring 6.x rollback rules.

~~~text
BEGIN TX
  UPDATE order
  publish Event
      @EventListener calls gateway -> throws RuntimeException
  exception escapes transaction boundary
ROLLBACK TX
~~~

However, if the listener already called an external HTTP API before throwing, the external side effect **does not roll back with the DB**. If the app must send notifications only when an order commits, move the work to after-commit:

~~~java
@Component
class ReceiptAfterCommitListener {

    private final ReceiptWorker worker;

    ReceiptAfterCommitListener(ReceiptWorker worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderCommitted(OrderCommitted event) {
        worker.process(event);
    }
}
~~~

This is an **excerpt** requiring `ReceiptWorker`, `OrderCommitted`, and imports. It is not a durable queue. If `worker.process` throws an exception, the business transaction has already committed; an exception from the callback **cannot undo the commit**.

### Testing the Transaction Boundary Properly

- Test **successful commit**: publish the event inside `TransactionTemplate.executeWithoutResult`; assert callbacks only after the transaction completes.
- Test **rollback**: after publishing, throw `IllegalStateException` inside the transaction; `AFTER_COMMIT` does not run.
- Test **no transaction**: listener does not run by default (`fallbackExecution=false`).
- Test **post-commit exception**: the business row still exists; the failure must be recorded or placed in a durable queue.
- If the post-commit listener writes to the DB itself, use a new transaction (`REQUIRES_NEW` or a separate `TransactionTemplate`).
- If the listener is async, await with a timeout after commit; never assert immediately after `publishEvent`.

Be careful with `@Transactional` on **JUnit test methods**: Spring TestContext usually rolls back the test transaction at the end of the method, so `AFTER_COMMIT` callbacks may not run. Explicitly commit using `TransactionTemplate` or `TestTransaction.flagForCommit()/end()` when using test-managed transactions.

## 9. Simulating Durable Retries: Unfinished Events After a Crash

Spring Retry in the test suite is **in-process**; if the JVM dies after the first attempt, nothing guarantees the system knows an event was left unfinished upon restart.

To model reliability, picture a **publication ledger** storing one record per `(event_id, handler_id)`:

~~~text
BEGIN business TX
  UPDATE orders
  INSERT event_publication(
    event_id, handler_id, status='PENDING', attempts=0)
COMMIT

Worker:
  atomic claim due PENDING/FAILED -> PROCESSING
  -> call external sink with fixed idempotency key
      success -> SUCCEEDED
      transient -> FAILED + next_attempt_at
      permanent/max attempts -> DEAD
  -> crash? -> lease expiration + recovery/reclaim
~~~

Suggested schema:

~~~sql
CREATE TABLE event_publication (
  event_id VARCHAR(80) NOT NULL,
  handler_id VARCHAR(100) NOT NULL,
  status VARCHAR(24) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMP NULL,
  lease_until TIMESTAMP NULL,
  claimed_by VARCHAR(100) NULL,
  fencing_token BIGINT NOT NULL DEFAULT 0,
  last_error_code VARCHAR(100) NULL,
  PRIMARY KEY (event_id, handler_id)
);
~~~

This is a **reference design schema**, not a table automatically created by Spring Framework or a complete outbox. Production needs enough event payload/snapshot or `payload_ref` so workers can reconstruct work after restarts.

Conceptual atomic claim example:

~~~sql
UPDATE event_publication
   SET status='PROCESSING',
       attempts=attempts + 1,
       claimed_by=:worker_id,
       lease_until=:lease_until,
       fencing_token=fencing_token + 1
 WHERE event_id=:event_id
   AND handler_id=:handler_id
   AND status IN ('PENDING','FAILED')
   AND attempts < :max_attempts
   AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP);
~~~

`:named_parameters` must be bound via `NamedParameterJdbcTemplate` or an equivalent mechanism. The worker proceeds only if **exactly one row** was updated; two workers must never both read `PENDING` and both trigger the side effect.

**Crash simulation** should cover at least three points:

1. **Before source commit:** event/outbox row must roll back together with business state.
2. **After commit but before worker dispatch:** publication remains `PENDING` and recovery finds it.
3. **After side effect but before marking `SUCCEEDED`:** retries can happen; the sink must be idempotent or reconciled by idempotency key.

A `PROCESSING` row can get stuck if a worker dies. You need `lease_until`, staleness detection, and `fencing_token` to stop an old worker from overwriting state after a new worker claims it. DB fencing does not undo an already-sent external side effect, so idempotency at the sink remains essential.

**Do not re-send every event on every restart** without checking per-handler status; doing so can cause handlers that already succeeded to repeat side effects.

## 10. Spring Modulith Event Publication Registry

If the application already uses Spring Modulith, the **Event Publication Registry** can store publications for transactional event listeners inside the business transaction. When a handler succeeds, the publication is marked completed; failures can be resubmitted via the corresponding API. This avoids hand-building all tracking and recovery for application modules.

Illustrative module listener:

~~~java
@Component
class BillingEventListener {

    @ApplicationModuleListener
    void on(OrderPaid event) {
        billingService.processIdempotently(event);
    }
}
~~~

This is an **excerpt** (requiring Spring Modulith dependencies/imports and appropriate bean/domain types), not part of `RetryEventTest` in Section 5. `@ApplicationModuleListener` carries transactional and async semantics per Modulith version; do not assume it provides exactly-once guarantees at an external sink.

In Spring Modulith **2.x**, publication lifecycles include `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, and `RESUBMITTED`, with APIs to query failed publications, configure resubmission, and detect stale ones. Use `FailedEventPublications`, `IncompleteEventPublications`, and `ResubmissionOptions` according to your exact version.

Example configuration that may be used to resubmit outstanding publications on restart:

~~~properties
spring.modulith.events.republish-outstanding-events-on-restart=true
~~~

This setting is **optional depending on version and operational policy**; do not enable it without accounting for retry storms, idempotency, permanently failing payloads, concurrency, and ordering. Completion modes (`UPDATE`, `DELETE`, `ARCHIVE`) affect publication retention/querying, not duplicate side-effect prevention.

**The registry tracks publications**; it does not replace a business audit ledger, turn HTTP/email into a distributed transaction, or prove an external service processed an item exactly once.

## 11. Systematic Fault-Simulation Practice

To test fault tolerance, rather than waiting for real external environments to break, build **failure injection** into gateways and service adapters. You can test these branches:

| Injection scenario | Simulation mechanism | Key assertion |
| --- | --- | --- |
| Transient failure N times | `failFirst(eventId, N)` | Attempts = N+1 when N is under max |
| Permanent failure | `rejectPermanently(eventId)` | No retries |
| Exhausted attempts | Fail more than `maxAttempts` | Exception/state exhausted without hanging |
| ACK lost after side effect | Record effect then throw transient | Attempts increase yet unique effects = 1 |
| Async consumer failure | Complete future exceptionally / error queue | Test awaits outcome with timeout; publisher does not return body error |
| Worker restart | Persist `PENDING` first, restart worker | Recovery reads `PENDING` without duplicate sends |
| Transaction rollback | Throw exception before commit | No committed business/outbox record |
| Poison message | Invalid payload/schema | Quarantine/`DEAD`, no endless retries |
| Executor saturation | Bounded queue + worker gate | Rejection observed; explicit overload policy |
| Multiple listeners | One listener succeeds, one fails | Retry only failing handler, do not republish all |
| Concurrent workers | Race to claim same publication | Only one atomic claim succeeds |
| Stale worker | Lease expires, new worker claims | Old fencing token cannot mark completed |

### Deterministic Tests: Control Cause Instead of Time

In the lab, `failFirst` uses a counter so it is exact which call throws and which succeeds. Never sleep a random 1 second hoping a failure appears. When testing races/async, use `CountDownLatch` (`started/release`) and `CompletableFuture.get(timeout)` to establish causal order.

Do not mock `ApplicationEventPublisher` itself in integration tests when the goal is verifying Spring dispatch and listener registration; use the real publisher and mock/fake **the listener's external dependencies**.

## 12. What Risks Do Retries Increase?

### 12.1. Duplicate Side Effects

A lost ACK can happen after the gateway finished executing. Retrying the same operation can duplicate emails, charges, or audits. `eventId` should serve as a stable idempotency key; with multiple handlers/sinks, `(eventId, handlerId)` or an action-scoped key is often required.

Checking `SELECT EXISTS` followed by `INSERT` is non-atomic and can race. Use database unique constraints/atomic upserts, or the downstream's idempotency API when the side effect lives outside the database.

### 12.2. Retry Storms

If many instances see HTTP 503 and retry immediately, the downstream gets overwhelmed further. Use **exponential backoff + jitter**, concurrency limits, circuit breakers where appropriate, honor `Retry-After` when trustworthy, and track retry-rate metrics.

### 12.3. Prolonged Transactions

Retrying HTTP calls inside a DB transaction holds connections and locks for the entire backoff window. Usually commit domain/outbox changes first, then run side effects outside the source transaction; each DB attempt gets its own appropriate transaction.

### 12.4. False "Success" from Swallowing Errors

If a listener catches an exception and merely logs it, registries may assume the handler succeeded even though the side effect failed. Distinguish **intentional best-effort** from **mandatory work**. When an outcome is failure, record state or throw per contract so retry/recovery mechanisms know.

### 12.5. Retries Do Not Create Ordering Guarantees

Multiple events for the same aggregate can be reordered by executors or retries. If `OrderCancelled` arrives before a retried `OrderPaid`, processing without version checks can corrupt state. Use aggregate versions, ordered partitions, optimistic locking, or orchestration when ordering is a real business invariant.

## 13. Logging, Metrics, and Verification Signals

The test counts attempts; in operations, observe comparable signals:

| Field / metric | Role |
| --- | --- |
| `event_id` and `handler_id` | Trace one logical work item |
| `attempt` and `max_attempts` | Know which retry attempt is running |
| `error_code` | Sanitized transient/permanent error classification |
| `outcome` | `SUCCEEDED`, `FAILED`, `DEAD` |
| `next_attempt_at` | Scheduled time for next retry |
| `processing_duration_ms` | Spot downstream latency |
| `oldest_pending_age` | Spot unprocessed backlog |
| `duplicate_suppressed` | Track idempotency suppressing duplicates |
| `retry_count` | Detect retry storms |
| `correlation_id`, `trace_id` | Link workflows, logs, and traces |

Do not attach `eventId` as a **metric label** because of high cardinality; use `event_type`, `handler_id`, and `outcome` for aggregation. `eventId` belongs in structured logs and publication registries. Never log raw payloads, tokens, credentials, or full exceptions containing PII.

Illustrative log entry:

~~~json
{
  "message": "event_retry_attempt",
  "event_id": "evt-42",
  "handler_id": "send-receipt",
  "attempt": 2,
  "max_attempts": 3,
  "error_code": "HTTP_503",
  "outcome": "FAILED"
}
~~~

This JSON is an **illustrative log schema**, not actual test output or a JSON encoder configured in this lesson.

## 14. Common Implementation Mistakes

**Mistake 1 — Retrying the whole `publishEvent`:** causes duplicate side effects from listeners that already succeeded. Retry one operation or per-handler publication.

**Mistake 2 — Not classifying exceptions:** schema/permission errors get retried endlessly. Retry only well-defined transient conditions.

**Mistake 3 — Misreading `maxAttempts`:** three attempts = initial try + two retries, not four tries.

**Mistake 4 — Using `Thread.sleep` in tests:** makes tests flaky and slow. Use fake counters, latches, and bounded waits.

**Mistake 5 — Assuming `publishEvent` returning means async listeners succeeded:** await real outcomes and error channels.

**Mistake 6 — Catching and swallowing exceptions in mandatory handlers:** registries/logs report false success; persist failed states instead.

**Mistake 7 — Retrying inside a transaction already marked rollback-only:** a broken transaction cannot be healed by re-running inside the same scope; each attempt needs a clean boundary.

**Mistake 8 — Using `@Retryable` via self-invocation:** advice is bypassed, running only once. Call via bean/proxy or use `RetryTemplate`.

**Mistake 9 — Failing to test lost ACKs after side effects:** leads to double charges, emails, or audits. Design idempotent sinks or reconciliation.

**Mistake 10 — Treating `@TransactionalEventListener(AFTER_COMMIT)` as a durable queue:** the process can crash before the callback; use an outbox/registry when events cannot be lost.

**Mistake 11 — Omitting deadlines and backoff:** causes retry storms and bloated requests/transactions. Separate in-process retries from scheduled deferred retries.

**Mistake 12 — Failing to test multiple event IDs:** sharing one global future/counter makes tests read mixed state. Isolate state by `eventId`/`handlerId`.

**Mistake 13 — Skipping concurrency tests:** two workers both read `PENDING` and process simultaneously. Use atomic claims, leases/fencing, and sink idempotency.

**Mistake 14 — Having no path when attempts exhaust:** events vanish silently. Store `DEAD` or quarantine records, alert, and provide controlled replay procedures.

## 15. Practice Checklist

- [ ] Distinguished sync listener errors, async body errors, and executor rejections.
- [ ] Tests run through real `ApplicationEventPublisher`; only external failing dependencies are faked.
- [ ] Scenarios cover transient, permanent, exhausted, lost ACK, and multiple event IDs.
- [ ] Max attempts asserted explicitly, including the initial attempt.
- [ ] Permanent errors are not retried; transient errors retry only within bounds.
- [ ] Assertions check **side effects**, not only method call counts.
- [ ] Retries target the right handler/operation, never unconditional republishing.
- [ ] Event IDs are stable; sinks have idempotency or reconciliation.
- [ ] Tests do not depend on wall-clock sleeps; async waits use timeouts.
- [ ] With transactions, before-commit/after-commit and rollback are clearly separated.
- [ ] If restart recovery is required, durable publication/outbox and attempt states exist.
- [ ] Bounded queues, overload policies, and exponential backoff + jitter configured for production.
- [ ] Logs, metrics, and alerts cover retries, failed/dead items, and backlogs.
- [ ] Policy defined for permanent/poison events and manual intervention.

## 16. Self-Check Questions

**Q1:** Does `ApplicationEventPublisher` automatically retry `@EventListener` after an exception?

Not in standard configurations. A synchronous exception typically propagates back to the publisher. Retries must be configured explicitly on the operation, listener, or publication/worker infrastructure.

**Q2:** Why retry `gateway.send(eventId)` instead of `publishEvent(event)`?

Because an event can have multiple listeners; retrying the whole publication re-invokes listeners that already succeeded, creating duplicate side effects.

**Q3:** What is the maximum number of retries for `maxAttempts(3)`?

Three total calls to the operation: one initial attempt and up to two retries.

**Q4:** If the fake gateway throws an exception after recording an effect, should you retry with a new event ID?

No. For the same logical event, keep the same idempotency key so the sink recognizes it as a retry and avoids duplicate side effects.

**Q5:** Why not wrap `publishEvent` in `assertThrows` to test an `@Async` listener's exception?

Because the listener body runs on a worker thread; the exception does not propagate directly through the publisher. Use an observable outcome/error handler with a timeout.

**Q6:** Can a retry failing inside `AFTER_COMMIT` roll back the source transaction?

No. The source transaction already committed. To avoid losing secondary work, persist durable processing intent within the source transaction or use an equivalent registry/outbox.

**Q7:** Why might `@Retryable` fail to execute all attempts even when annotated?

Because proxy advice can be bypassed on self-invocation within the same bean, or `@EnableRetry`/dependencies/transaction advice ordering may be misconfigured. Verify attempt counts in integration tests.

**Q8:** Is a publication still marked `PROCESSING` after a restart guaranteed safe to re-send immediately?

No. You must check lease/staleness, worker coordination, sink idempotency, and whether the side effect already happened before the crash.

**Remember:** reliable fault simulation does not just verify "the retry eventually succeeds"—it proves **exact attempt counts, proper error classification, zero duplicate side effects, clean transaction boundaries, and a recovery path after crashes**. Spring Retry handles in-process retries; when reliability across restarts is required, pair it with a publication registry/outbox, idempotency, retry scheduling, and observability.

## References

- [Spring Framework — ApplicationContext Events, synchronous vs asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Retry 2.0 — RetryTemplateBuilder API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Retry 2.0 — RetryTemplate API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplate.html)
- [Spring Modulith — Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)

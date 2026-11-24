# Backoff and Preventing Retry Storms in Spring Application Events

## 1. The Problem: Retries Can Turn a Small Glitch into a Major Incident

In an event-driven system, an `@EventListener` may send emails, call REST APIs, write to a database, publish messages to a broker, or perform another task. When a dependency is slow, returns HTTP 429/503, or drops connections, retries often help overcome transient errors. However, **immediate and synchronized retries** can overload the very dependency that is already struggling.

For example, 1,000 instances receive `503 Service Unavailable` at the exact same time:

```text
t = 0 ms:   1,000 calls to downstream -> 503
t = 1 ms:   1,000 immediate retries   -> 503
t = 2 ms:   1,000 more retries        -> 503
...
Downstream never gets time to recover; connection pools/CPUs stay saturated.
```

This phenomenon is called a **retry storm**; when many clients retry at the exact same moment, it is also known as a *thundering herd*. Even a dependency that was only slow for a few seconds may never recover because retry traffic compounds on top of new incoming traffic. When retries exist across multiple layers (HTTP client, handler, queue consumer, gateway), downstream call counts amplify even further.

**Backoff** is a policy of progressively increasing wait times between attempts. **Jitter** randomizes wait durations to spread clients out instead of letting them call back simultaneously. Preventing retry storms effectively also requires bounding attempt counts, total elapsed time, concurrent requests, idempotency, retriable error classification, retry observability, and a single clear owner of retries.

The goal of this lesson is designing controlled retries around **listener work or integration clients**, without treating `ApplicationEventPublisher.publishEvent(...)` as a durable broker with built-in retries.

## 2. Why Are Spring Application Events Especially Error-Prone with Retries?

Spring Framework supports `ApplicationEventPublisher.publishEvent(Object)` and `@EventListener` methods. Under the default `SimpleApplicationEventMulticaster`, regular listeners run **synchronously on the event-publishing thread**. This means:

- A listener calling downstream and sleeping via `Thread.sleep(...)` for several seconds can **pin the request thread** or the publisher's command-handling thread.
- If published inside a transaction, a synchronous listener may hold the transaction and database resources open longer than needed.
- If a listener throws an unhandled exception, it can propagate back to `publishEvent(...)`. An active transaction may roll back depending on configuration.
- One publish can have **multiple listeners**. Retrying the entire `publishEvent(event)` after the second listener fails can cause the first listener — which already succeeded — to run again.
- With `@Async` or a custom multicaster executor, listener errors do not automatically return to the publisher; the publisher returning does not mean processing succeeded.
- Spring application events within one JVM **are not durably persisted** across process crashes. In-memory retries with thread sleep do not replace a durable queue/outbox.

Therefore, retries usually belong at the **boundary of the specific failing operation** — for example `notificationClient.send(...)` — rather than blindly wrapping the entire publish/fan-out.

```text
Application service
      |
      +-- publishEvent(NotificationRequested)
                     |
                     +-- AuditListener (already succeeded)
                     |
                     +-- EmailListener
                             |
                             +-- EmailClient.send(...) -> 503
                                      |
                                      +-- bounded retry/backoff
                                      +-- idempotency key
                                      +-- failure handling
```

If you re-invoke the entire `publishEvent` after an `EmailClient` failure, `AuditListener` may rerun even though it was unrelated. If you retry only `EmailClient.send`, at least the repetition scope is narrowed. Still, sending email needs idempotency/deduplication when delivery outcomes can be indeterminate.

## 3. Not Every Error Is Retriable

Classify errors based on business contracts, APIs, and operation semantics:

| Scenario | Should it retry? | Notes |
| --- | --- | --- |
| HTTP 429 Too Many Requests | Usually yes | Prioritize rate limiting; honor `Retry-After` if present |
| HTTP 503 Service Unavailable | Usually yes | Capped backoff, jitter, and retry budget |
| HTTP 502/504 from gateway | Conditionally | Target system may have already executed the operation |
| Connection reset / transient timeout | Conditionally | Timeouts can leave an **indeterminate** state |
| DB deadlock / optimistic lock | Conditionally | Retry the right unit of work; do not repeat off-DB side effects |
| HTTP 400 / 422 from bad input | Usually no | Must fix payload or domain rules |
| HTTP 401 / 403 from permissions | Usually no | Fix credentials/permissions; infinite retries are futile |
| Resource already exists / 409 | Depends on contract | May be an idempotent outcome or a real conflict |
| Incompatible schema/payload | Not until fixed | Route to permanent failure handling or DLQ |
| Business error like `ORDER_ALREADY_PAID` | Do not retry mechanically | Do not assume retrying a few milliseconds later will help |

Specifically, **a timeout does not prove an operation did not happen**. For example, a `charge(paymentId)` call may have been processed by the bank while the response was lost. Retrying with a new ID can charge twice. Before retrying, require a **stable idempotency key** and/or a state-query mechanism for reconciliation.

Avoid writing:

```java
// Anti-pattern: catching every error and retrying regardless of cause.
catch (Exception ex) {
    Thread.sleep(100);
    publisher.publishEvent(event);
}
```

This is a snippet **never to use**: it retries the whole publish, has no attempt limit, checks no error type, and ignores the state of prior listeners.

## 4. Backoff Strategies: Fixed, Exponential, Capped, and Jitter

### 4.1. Fixed Delay

```text
After each failure: 200ms, 200ms, 200ms, ...
```

Easy to understand, yet when thousands of clients fail at once, they all retry on the same 200ms cadence, creating recurring bursts.

### 4.2. Exponential Backoff

A common formula for the **k-th retry** (k starting at 1):

\[
D_k = \min(D_{\max}, D_{\mathrm{base}} \times 2^{k-1})
\]

Where `D_base` is the base wait time and `D_max` is the **cap**. For example, `D_base = 200 ms`, `D_max = 2,000 ms`:

| Retry # | Max wait window |
| ---: | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 2,000 ms (cap reached) |
| 6 | 2,000 ms |

Without a cap or deadline, wait times grow enormous; also avoid computing `base * 2^k` via unchecked multiplication because integer overflow can occur for large `k`.

### 4.3. Full Jitter

With **full jitter**, pick a random wait time across the entire window:

\[
W_k \sim \operatorname{Uniform}(0,D_k)
\]

or in code:

```text
cap   = min(maxDelayMs, baseDelayMs * 2^(retryNumber - 1))
delay = random(0, cap)   // full jitter
```

For instance, when the cap is 800ms, clients may pick 25ms, 330ms, 705ms, etc., instead of all piling onto 800ms. This **does not make total retry volume free**; it merely spreads retries out, lowering the chance of synchronized bursts.

There are other variants, such as *equal jitter* (waiting at least half the window) or *decorrelated jitter* (based on the previous delay). They have different latency/load profiles; when using a library, verify the actual algorithm rather than just seeing a parameter named `random`.

### 4.4. Min/Max Attempts, Total Elapsed Time, and Deadlines

**Max attempts** should explicitly state whether it **includes the initial call** or only retries. For example, `maxAttempts = 4` typically means 1 original call + up to 3 retries. Meanwhile, some APIs named `maxRetries = 3` mean 3 retries after the first call.

Beyond attempt counts, you need:

- **Per-attempt timeout**: a single request must not hang indefinitely.
- **Overall deadline**: total retry and processing time must stay below the business deadline.
- **Maximum delay cap**: avoid sleeping excessively long.
- **Retry budget**: cap retries relative to fresh requests or total retries in a window, per dependency.
- **Cancellation/interrupt**: when the request is canceled or the service shuts down, stop retrying and release resources.
- **Retry-After**: when the server sends a wait hint, honor it per contract within deadline limits; do not retry earlier than the server requested.

Total duration is not just the delays. It includes each attempt's execution time and resource wait time. If every attempt has a 5-second timeout, 4 attempts can pin a thread for a long time even if total backoff is small.

## 5. Runnable Maven + Java 17 Example: Capped Retry, Jitter, and Fail-Fast

The example uses Spring Framework **6.2.8** and Java 17, without Spring Boot, a broker, or a database. An `@EventListener` calls a fake gateway, distinguishing transient errors from permanent errors. Policy:

- Maximum **4 attempts** (including the first call).
- Exponential cap starting at 200ms, doubling, capped at 2,000ms.
- Full jitter expressed via a `DoubleSupplier` interface returning values in 0 (inclusive) to 1 (exclusive).
- In the demo, `() -> 0.5` is used for **deterministic output**, not real randomness; production uses `ThreadLocalRandom.current().nextDouble()`.
- `Thread.sleep(...)` is solely for **visualization** in the console. Never use sleep/blocking retries inside a synchronous request listener in production.
- Event ID remains unchanged across attempts, preparing for idempotency mechanisms.

### 5.1. Project Structure

```text
event-retry-backoff/
├── pom.xml
└── src/main/java/demo/RetryBackoffDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-retry-backoff</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.RetryBackoffDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/RetryBackoffDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.DoubleSupplier;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class RetryBackoffDemo {

    public record NotificationRequested(String eventId) {}

    public static final class TemporaryDeliveryFailure
            extends RuntimeException {
        public TemporaryDeliveryFailure() {
            super("downstream temporarily unavailable");
        }
    }

    public static final class PermanentDeliveryFailure
            extends RuntimeException {
        public PermanentDeliveryFailure() {
            super("recipient permanently invalid");
        }
    }

    public static final class FakeGateway {
        private final Map<String, Integer> attempts = new HashMap<>();

        public void deliver(NotificationRequested event) {
            int number = attempts.merge(event.eventId(), 1, Integer::sum);
            String id = event.eventId();

            if ("E-STOP".equals(id)) {
                System.out.println(
                        "gateway: " + id + " permanent attempt=" + number);
                throw new PermanentDeliveryFailure();
            }

            if ("E-OUT".equals(id)
                    || ("E-OK".equals(id) && number < 3)) {
                System.out.println(
                        "gateway: " + id + " transient attempt=" + number);
                throw new TemporaryDeliveryFailure();
            }

            System.out.println(
                    "gateway: " + id + " delivered attempt=" + number);
        }
    }

    @FunctionalInterface
    public interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    public static final class RetryingListener {
        private static final int MAX_ATTEMPTS = 4;
        private static final long BASE_DELAY_MS = 200;
        private static final long MAX_DELAY_MS = 2_000;

        private final FakeGateway gateway;
        private final DoubleSupplier randomFraction;
        private final Sleeper sleeper;

        public RetryingListener(
                FakeGateway gateway,
                DoubleSupplier randomFraction,
                Sleeper sleeper) {
            this.gateway = gateway;
            this.randomFraction = randomFraction;
            this.sleeper = sleeper;
        }

        // failureAttempt = 1 after attempt 1 fails.
        private long cappedWindow(int failureAttempt) {
            long cap = BASE_DELAY_MS;
            for (int i = 1; i < failureAttempt; i++) {
                cap = Math.min(MAX_DELAY_MS, cap * 2);
            }
            return cap;
        }

        @EventListener
        public void onNotification(NotificationRequested event) {
            String id = event.eventId();

            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    gateway.deliver(event);
                    System.out.println("listener: " + id + " completed");
                    return;
                } catch (PermanentDeliveryFailure ex) {
                    System.out.println(
                            "listener: " + id + " non-retryable");
                    throw ex;
                } catch (TemporaryDeliveryFailure ex) {
                    if (attempt == MAX_ATTEMPTS) {
                        System.out.println(
                                "listener: " + id + " exhausted="
                                        + MAX_ATTEMPTS);
                        throw ex;
                    }

                    long cap = cappedWindow(attempt);
                    // Full jitter policy; demo uses fraction = 0.5.
                    long delay = (long) (cap * randomFraction.getAsDouble());
                    System.out.println("retry: " + id
                            + " next-attempt=" + (attempt + 1)
                            + " delay=" + delay + "ms");

                    try {
                        sleeper.sleep(delay);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "Retry interrupted", interrupted);
                    }
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        RetryingListener retryingListener(FakeGateway gateway) {
            // Deterministic demo: half the window on each retry.
            // Production can use:
            // () -> ThreadLocalRandom.current().nextDouble()
            return new RetryingListener(gateway, () -> 0.5, Thread::sleep);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("=== RECOVERY ===");
            context.publishEvent(new NotificationRequested("E-OK"));

            System.out.println("=== PERMANENT ===");
            try {
                context.publishEvent(new NotificationRequested("E-STOP"));
            } catch (PermanentDeliveryFailure ex) {
                System.out.println("main: E-STOP rejected");
            }

            System.out.println("=== EXHAUSTION ===");
            try {
                context.publishEvent(new NotificationRequested("E-OUT"));
            } catch (TemporaryDeliveryFailure ex) {
                System.out.println("main: E-OUT exhausted");
            }
        }
    }
}
```

Run in the project directory, requiring JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Lines printed by the application (excluding extra Maven output):

```text
=== RECOVERY ===
gateway: E-OK transient attempt=1
retry: E-OK next-attempt=2 delay=100ms
gateway: E-OK transient attempt=2
retry: E-OK next-attempt=3 delay=200ms
gateway: E-OK delivered attempt=3
listener: E-OK completed
=== PERMANENT ===
gateway: E-STOP permanent attempt=1
listener: E-STOP non-retryable
main: E-STOP rejected
=== EXHAUSTION ===
gateway: E-OUT transient attempt=1
retry: E-OUT next-attempt=2 delay=100ms
gateway: E-OUT transient attempt=2
retry: E-OUT next-attempt=3 delay=200ms
gateway: E-OUT transient attempt=3
retry: E-OUT next-attempt=4 delay=400ms
gateway: E-OUT transient attempt=4
listener: E-OUT exhausted=4
main: E-OUT exhausted
```

### 5.2. Reading the Output

- **E-OK**: gateway fails transiently twice and succeeds on the 3rd attempt. Backoff has two waits of 100ms and 200ms because the demo fraction is 0.5 and the caps are 200ms and 400ms respectively.
- **E-STOP**: permanent error, **no retry**; even though max attempts is 4, the gateway is called only once.
- **E-OUT**: prolonged transient error, calls all 4 attempts; there are three waits of 100ms + 200ms + 400ms before **exhausted**. No sleep after the final attempt.
- `context.publishEvent(...)` in the example runs synchronously. When an error escapes `@EventListener`, `main` catches the exception and prints the corresponding message.
- `Thread.sleep` blocks the thread during backoff; the entire demo has an intentional wait time of roughly 1,000ms. This is **not how to structure a production listener** if high event/second throughput is needed.

### 5.3. Why Does the Demo Not Use Real Randomness?

The goal of the example is exact predictable stdout. The `DoubleSupplier` interface lets you replace `0.5` with a random value in `[0, 1)` in production, such as:

```java
// Snippet: use in @Bean instead of () -> 0.5.
() -> ThreadLocalRandom.current().nextDouble()
```

With real randomness, delays vary and the exact millisecond numbers in output cannot be predicted; in unit tests, inject a fake source to test boundary values 0, near-1, and the cap. Never seed a fixed value in production just to get "neat" logs: if every instance follows the same jitter sequence, they can re-synchronize.

### 5.4. Important Limitations of the Demo

This models bounded attempts and clear error handling, **not** durable delivery, rate limiting, or backpressure. `FakeGateway` lacks real idempotency, and `attempts` data lives solely in memory. When the system restarts, that state disappears. It also omits DB transactions, brokers, overall deadlines, and cross-replica shared retry budgets. Those elements must be designed additionally before production use.

## 6. Why Does Exponential Backoff Alone Still Cause Retry Storms?

Suppose 10,000 listeners start at the same time and all pick exponential backoff **without jitter**:

```text
t = 0ms       10,000 attempts fail
t = 200ms     10,000 retries #1
t = 600ms     10,000 retries #2 (200 + 400)
t = 1,400ms   10,000 retries #3 (200 + 400 + 800)
```

Backoff spaced out the waves, yet they still land at **the exact same instant**. If downstream can only handle 500 calls per 100ms, those retry waves keep choking it.

Full jitter makes each client pick a different instant in the window; however, in systems with thousands of replicas, do not rely **solely** on jitter. You need a total traffic budget and downstream protection capabilities.

Also note that "fixed 500ms ± 10%" generally spreads poorly compared to full jitter across a wide range under extreme load. In return, full jitter occasionally produces delays very close to 0; therefore, rate limiters/circuit breakers serve as complementary layers, especially with many clients.

## 7. Protection Layers Against Retry Storms

### 7.1. Retry Budget

Cap the ratio of retries relative to original requests or total attempts in a window. For example, a policy might state "no more than 10% of outgoing traffic may be retries" per dependency, or use a dedicated token bucket for retries.

The 10% figure is only an example, not a Spring default. When the budget is exhausted, **defer/fail fast** per contract rather than retrying until every event completes at all costs.

### 7.2. Rate Limiting and Honoring Retry-After

Downstream returning 429 usually means it wants clients to slow down. If `Retry-After` is present, parse/apply it per the HTTP contract: the value may be seconds or an HTTP-date. When that wait exceeds the command's deadline, do not block the request thread indefinitely; persist a retryable/deferred state or report a pending status.

A rate limiter controls **rate**, unlike a concurrency limiter which controls **in-flight operations**. Depending on load, you may need both.

### 7.3. Circuit Breaker

When technical failures tend to persist, a circuit breaker can open to **temporarily halt** calls doomed to fail. After a cooldown, the half-open state lets a few requests probe recovery. Do not let thousands of clients reopen circuits simultaneously and trigger a burst; limit probes and combine with rate limiting/jitter.

A circuit breaker is not retry: it prevents calls when a dependency is unhealthy. When the circuit is open, operations can fail fast, be rescheduled, or be queued depending on business policy.

### 7.4. Concurrency Limits and Bulkheads

Limit the number of in-flight handler/integration calls so one failing dependency does not exhaust all threads, DB connections, and memory. You can use semaphores, dedicated thread pools, bounded queues, bulkheads, or request concurrency limiters.

A pool of 100 workers where every worker sleeps for 3 seconds to retry quickly runs out of capacity. For high workloads, use a scheduler/queue with a `next-attempt` timestamp to **free the worker** between attempts.

### 7.5. Dead-Letter Queue / Parking Lot

After exhausting attempts or encountering permanent errors needing intervention, store details in a DLQ or an investigable `FAILED` state. Never immediately replay an entire DLQ repeatedly and cause a *DLQ replay storm*. Replays should have approvals/rules, rate limits, batch sizes, and a stop switch.

Payloads may contain PII, so DLQs, logs, and retry headers all require data classification, retention limits, and access controls.

### 7.6. Timeouts and Deadlines

Retries only help when each attempt has a suitable timeout and enough time remains before the deadline. If an HTTP client defaults to waiting 30 seconds and `maxAttempts` is 4, even before backoff it could spend up to 120 seconds. Tune connect/read/request timeouts to the event flow's SLO so retries do not push tail latency past business requirements.

## 8. Avoiding Multi-Layer Retry Amplification

Suppose an event consumer calls an application service; the service calls an HTTP client; the HTTP client SDK retries on its own:

```text
Queue consumer: 3 attempts
  -> Service retry: 3 attempts
       -> SDK retry: 3 attempts
            -> Downstream may receive up to 27 calls
```

Approximate formula for a chain of independent retry layers: \(\prod_i A_i\), where `A_i` is the maximum attempts of layer `i`. With 3 layers of 3 attempts each: \(3 \times 3 \times 3 = 27\).

Not every call hits that worst case, yet the example shows why **you must not enable default retries at every layer without coordination**. In practice, clearly assign:

- **Which layer owns retries** for network or broker errors?
- Does the SDK library already retry before returning an error?
- After the listener exhausts attempts, will the queue retry the entire event with its own attempt counter?
- How many downstream attempts does one consumer attempt generate?
- Does a retry budget apply across total calls to a dependency?
- Are correlation IDs and event IDs preserved across layers?

Prefer retrying at the layer that **knows idempotency and outcome**, where it can decide whether to continue, move to a delayed queue, or fail. With broker consumers, many frameworks have built-in retry/delay/backoff/DLQ configs: do not wrap another retry loop inside the listener if it duplicates what the broker layer already provides.

## 9. Idempotency and Indeterminate Outcomes

A retry can duplicate side effects even when code only retries **on exceptions**:

```text
Worker sends request idempotencyKey=E-100
     |
     +-- downstream writes successfully
     +-- response lost / timeout
     |
     +-- worker catches exception, unaware it succeeded
     +-- retries idempotencyKey=E-100
     |
     +-- downstream returns prior result without applying side effect a second time
```

Design pattern:

1. Assign a stable `eventId` when creating the business fact.
2. Use `eventId` or an operation-specific idempotency key per the downstream contract.
3. The consumer or downstream persists processed status with that key in storage enforcing a unique constraint/atomic compare-and-set.
4. When receiving the same key again, return the recorded result or skip the side effect per policy.
5. Never generate a new ID per retry of the same event if deduplication is intended.
6. Set a TTL/retention policy on dedup keys long enough to cover retry windows and replays.

Limitation: idempotency must **actually be enforced on the receiving side**; merely sending an HTTP header named "Idempotency-Key" does nothing if downstream ignores it. A unique event ID also does not prevent sending an email/SMS twice if deduplication happens after the side effect.

For payments, money transfers, and actions that cannot easily be undone, prefer checking status/reconciliation rather than blindly retrying after timeouts.

## 10. Transactions, @TransactionalEventListener, and Durable Retries

### 10.1. Synchronous Listener Inside a Transaction

If a `@Transactional` service publishes an event and a listener calls a REST API with retry/sleep:

- Threads and transactions can be held open during backoff intervals.
- DB transactions can hold locks/connections longer.
- After retries fail, the listener exception can cause the transaction to roll back.
- If the remote API succeeded on an earlier attempt while the caller timed out, DB rollback **does not undo** off-DB side effects.

Therefore, avoid performing long external I/O inside a mid-transaction synchronous listener merely to "ensure retries".

### 10.2. AFTER_COMMIT Reduces Coupling but Is Not Yet Durable

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` executes the callback only after the associated transaction commits successfully. It fits when you want to avoid sending notifications for rolled-back transactions. However, after commit, a callback failure **cannot roll back the completed commit**.

If the process dies after commit before the callback finishes, in-memory events can be lost. The after-commit annotation does not turn an event into a durable retry job. For a post-commit listener needing to write new DB state, open an appropriate independent transaction because old transaction resources may still linger without a subsequent commit.

### 10.3. Transactional Outbox + Delayed Relay

When the requirement is "do not lose events even if the process crashes", store an outbox record in the same transaction updating state:

```text
BEGIN TRANSACTION
  UPDATE orders SET status = 'PAID' WHERE id = ?
  INSERT INTO outbox(
      event_id, type, payload, attempts, next_attempt_at, state)
COMMIT

Relay worker:
  claim due READY rows, with concurrency limit
  -> call downstream with stable idempotency key
  -> success: mark DELIVERED
  -> transient failure: attempts++, set next_attempt_at with backoff+jitter
  -> permanent failure or exhausted: mark FAILED/DLQ
  -> continue small batches, with rate limits and metrics
```

A multi-replica relay needs **claim/lease or row locking** to avoid excessive concurrent processing of the same row; expired leases and crashes can still cause duplicates, so idempotency remains necessary. The outbox table acts as a durable queue: a relay sending successfully and dying before marking DELIVERED can cause the event to be sent once more.

`next_attempt_at` enables backoff **without keeping a worker thread sleeping**. Workers only fetch due rows, schedule the next attempt, and release resources. For high throughput or cross-service integration, delayed broker messages and queue redelivery policies can replace or accompany an outbox, provided retry counts across layers are coordinated.

### 10.4. Do Not Blindly Retry the Entire Publish/Fan-Out

`publishEvent(event)` is a handoff to the multicaster, not a commitment that every listener finished. Synchronously, the first listener may succeed while the second throws; if the service retries `publishEvent`, the first listener runs again.

A better approach is retrying the **idempotent operation inside each handler**, or separating handlers into independent durable jobs with their own event IDs and per-consumer retry policies. Avoid turning 1 publish into `n` publishes just because one external listener is temporarily unavailable.

## 11. Spring Retry, Framework 7, and Resilience Libraries

With **Spring Retry 2.x** (separate library), you have `@Retryable`, `@Backoff`, `RetryTemplate`, and `@EnableRetry` configuration. Illustrative snippet for a **service bean proxied by Spring and invoked across an appropriate boundary**:

```java
// Spring Retry 2.x: snippet, not a standalone program.
// Requires spring-retry, Spring AOP/config, and proper @EnableRetry.
@Retryable(
    retryFor = TemporaryDeliveryFailure.class,
    maxAttempts = 4,
    backoff = @Backoff(
        delay = 200,
        multiplier = 2,
        maxDelay = 2000))
public void callDownstream(NotificationRequested event) {
    gateway.deliver(event);
}
```

In Spring Retry 2.x, `maxAttempts=4` **includes the initial invocation**. The method must be invoked through the right Spring proxy/aspect mechanism; calling `this.callDownstream(...)` within the same bean can bypass advice. The `@Backoff` configuration above does not imply **full jitter** by default. To get exact jitter semantics, check the backoff policy/implementation and options supported by your version.

One common point of confusion: **Spring Framework 7.0** brings resilience features such as `org.springframework.resilience.annotation.Retryable` into the core framework. Attributes and semantics differ from Spring Retry 2.x — for example, `maxRetries` is the number of additional retries after the first attempt. **Do not copy `maxRetries` straight onto Spring Retry's `maxAttempts`**, and do not mix packages/framework versions within one snippet.

Resilience4j also offers Retry, RateLimiter, CircuitBreaker, Bulkhead, and TimeLimiter. Pick tools based on requirements; more important than the library name are:

- Accurate retriable error classification.
- Configuring attempts/deadlines/delays and jitter.
- Coordinating with built-in HTTP client SDK/broker retries.
- Limiting concurrency/rate and using circuit breakers when needed.
- Idempotency, metrics, logging, and exhaustion handling.
- Evaluating blocking vs. non-blocking runtimes against real workloads.

## 12. Testing Backoff and Retry-Storm Prevention Policies

Avoid real `Thread.sleep` in every unit test; tests become slow and flaky. Design the retry policy to allow injecting a `Sleeper`/scheduler, random source, and clock for deterministic tests.

With the example in section 5, you can create a fake `Sleeper` that only records delays into a list, and a `DoubleSupplier` returning `0.5`. Then verify:

| Scenario | Expectation |
| --- | --- |
| Gateway succeeds on first try | 1 attempt, 0 delay |
| Transient failure twice then succeeds | 3 attempts, recorded delays [100, 200]ms |
| Permanent failure | 1 attempt, no sleep, right exception type |
| Prolonged transient failure | 4 attempts, exactly 3 waits [100, 200, 400]ms, exhausted |
| Random fraction = 0 | Delay can be 0, never negative |
| Fraction near 1 | Delay never exceeds cap |
| Exception from interrupt | Preserves interrupted flag, stops retries |
| Multiple listeners | Does not automatically retry whole publish when one listener fails |
| Duplicate event ID | Consumer/downstream does not repeat side effect |
| 429/503 burst | Retry budget, rate limit, and queue depth prevent overload |
| Process crash after commit | Outbox/delayed queue can resume |
| Retry-After exceeds deadline | Defers/fails per policy, does not block indefinitely |

### Testing Retry Behavior at the Right Layer

1. **Unit test retry executor/handler**: assert attempt counts, error types, delay sequences, and stop conditions.
2. **Spring integration test**: ensure `@EventListener` actually receives events, exception handling works, and publishes are not accidentally multiplied.
3. **Transaction test**: sync listener failing before commit produces outcome per rollback policy; after-commit failures do not fake a rollback.
4. **Outbox integration test**: event and state share a transaction; retries after restart, multiple relays, lease expiry, idempotent consumer.
5. **Load/chaos test**: have downstream return 429/503 in bursts; verify retry traffic spreads per jitter, respects rate caps, avoids thread/queue blowups, and recovers cleanly.
6. **Monitoring test**: metrics for retry attempts, exhausted, rejected, queue lag, and dependency availability reflect reality.

A unit test counting attempts accurately **does not by itself prove** retry storms are prevented in a multi-instance deployment. You must test aggregate load and real resource-throttling mechanisms.

## 13. Observability and Operations

Measure distinct signals:

| Metric / log dimension | Helps answer |
| --- | --- |
| `event.publish.attempts` | How many events were requested for dispatch? |
| `handler.attempts` | How many handler executions occurred, including retries? |
| `handler.success` / `handler.failure` | What is the real success rate? |
| `retry.attempts` | What share of load is retries? |
| `retry.exhausted` | How many tasks exhausted their budget? |
| `retry.delay` | What is the actual wait-time distribution? |
| `downstream.429` / `downstream.503` | Is the dependency throttling or unavailable? |
| `queue.depth` / `queue.oldest.age` | Is backlogged work growing? |
| `rate_limiter.rejected` | Are we hitting traffic caps? |
| `circuit.state` | Is the circuit closed, open, or half-open? |

Spring Framework does not automatically create an Observation for every `@EventListener` merely because Micrometer is present. To capture retry counts, delays, and outcomes, instrument the right spots or use metrics/hooks from your configured library.

Never use `eventId`, email, `userId`, or arbitrary raw exception messages as **low-cardinality tags**. You can put classified correlation/event IDs into appropriate logs/traces while avoiding PII and secret leaks. Metrics should use bounded tags such as event type, dependency, outcome, retryable, and failure category.

A good dashboard separates offered rate, original attempts, retry rate, completion throughput, and backlog. If you only watch downstream call counts rise, the system may look like throughput improved while retries are actually driving down success rates.

## 14. Implementation Checklist

- [ ] Only identified transient errors are retried; permanent business/config errors fail fast.
- [ ] The exact layer owning retries is chosen, checking built-in SDK/broker retries.
- [ ] Attempts, delays, and elapsed time are capped; per-attempt timeouts and overall deadlines are set.
- [ ] Exponential backoff with jitter is used to reduce thundering herds.
- [ ] `Retry-After`, rate limits, and retry budgets are honored when dependencies are overloaded.
- [ ] Concurrency and queue capacity are bounded; backpressure/fail/defer policies exist.
- [ ] No long `sleep` inside synchronous request listeners/transactions.
- [ ] When durability is required, an outbox or delayed queue is used instead of RAM-only buffers.
- [ ] Event IDs/idempotency keys stay stable; consumers deduplicate and reconcile indeterminate outcomes.
- [ ] Never blindly retry the whole `publishEvent`, causing already-succeeded listeners to rerun.
- [ ] DLQ/parking lot and controlled replay are configured to avoid a second retry storm.
- [ ] Metrics exist for retries, exhaustion, errors, queue backlog, saturation, and latency.
- [ ] Tests cover attempt counts, delays, deadlines, interrupts, permanent failures, and system-wide load/bursts.
- [ ] Impact on transactions, side effects, rollbacks, and holding threads/resources is evaluated.

## 15. Self-Check Questions

1. **How does backoff differ from plain retries?** — It controls the wait interval between attempts, avoiding immediate tight loops.
2. **Why does exponential backoff without jitter still cause bursts?** — Clients failing together still retry at the exact same timestamps.
3. **In what range does full jitter pick a delay?** — From 0 up to the exponential cap for that retry attempt.
4. **Does max attempts always equal max retries?** — No; check whether the initial invocation is counted.
5. **Why must errors be classified?** — Retrying permanent errors wastes load; timeouts can leave indeterminate outcomes.
6. **Why shouldn't you retry the whole `publishEvent` when the second listener fails?** — The first listener may have already succeeded and would be invoked again.
7. **Why is sleeping inside a synchronous `@EventListener` dangerous?** — It blocks the publishing thread and may hold transactions/locks open.
8. **What can an SDK retrying 3 times inside a handler retrying 3 times cause?** — Retry amplification; the same operation can hit downstream up to 9 times.
9. **Does jitter alone guarantee no overload?** — No; you still need rate/concurrency limits, budgets, and circuit breakers.
10. **Why is an idempotency key needed across all retries?** — A timeout does not prove downstream didn't execute; retries can create duplicate side effects.
11. **Is `AFTER_COMMIT` enough to prevent losing events?** — No; crashing after commit can lose in-memory callbacks; use an outbox when durability is required.
12. **How do you free workers during backoff in a queue?** — Persist `next_attempt_at` or use delayed messages/schedulers instead of sleeping on a worker.
13. **When receiving 429 with `Retry-After`, what should the application do?** — Respect the wait duration per contract within deadline/budget bounds.
14. **Where should permanent errors go?** — Fail fast and/or route to FAILED/DLQ for remediation, never retry infinitely.

## References

- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Retry 2.x — @Retryable API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Framework 7.0 — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [AWS Well-Architected — Control and limit retry calls](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html)
- [AWS — Retry with backoff pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
- [AWS SDK — Retry with full jitter](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)

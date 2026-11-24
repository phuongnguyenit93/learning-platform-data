# Listener Retries and Retry Conditions in Spring Application Events

## 1. What Is Retry and Why Do Listeners Need a Retry Policy?

A Spring application may publish `OrderConfirmed`, and an `@EventListener` then sends a notification to an external service. The service may return `503 Service Unavailable`, time out, or temporarily drop the connection. Failure **does not necessarily** mean the work can never complete; controlled retrying (*retry*) can recover when errors are short-lived.

However, not every error should be retried. Resending a payment request without an idempotency key can charge the customer twice. Retrying an email with an invalid address only generates extra load. Retrying infinitely while the database is down can exhaust all threads across the application and keep queues growing.

**Three actions must be distinguished:**

- **Publish:** Spring receives an event object to dispatch to matching listeners.
- **Retry:** A policy to re-invoke an operation **after that operation fails**, based on the error type and chosen bounds.
- **Recovery:** Handling after attempts are exhausted (or when a non-retryable error is hit), such as recording a failure status, routing to a dead-letter queue, or alerting operations.

`ApplicationEventPublisher.publishEvent(...)` **does not retry listeners by default**. Spring Application Events also does not automatically provide a persistent queue, guaranteed event delivery after a crash, or exactly-once processing. The application itself must define retry conditions, stopping conditions, where work state is kept, and how to prevent duplicate side effects.

Lesson objective: understand when a listener may be retried, how to combine Spring Retry with `@EventListener`, the impact on transactions/rollback, and when to move to an outbox or message broker.

## 2. Retry by Error Type or by Business Outcome?

A good *retry condition* is typically based on: **error type**, **safety of repeating the operation**, **attempts already made**, **remaining time**, and **recoverability**.

| Scenario | Should you retry immediately? | Reason / appropriate action |
| --- | --- | --- |
| HTTP 503/502/504 from downstream | Usually yes, if repeating is safe | Use backoff, timeouts, bounded attempts, and observability |
| HTTP 429 rate limit | Conditionally | Respect `Retry-After`/quota, limit concurrency, do not burst |
| Transient disconnect or connect timeout | Conditionally | Server outcome may be **unknown**; idempotency is required |
| Read timeout after sending request | High risk | Server may already have executed; retry only with dedup key or status check |
| Deadlock or transient DB lock failure | Possible | Retry the **entire unit of work** in a new transaction, with limits |
| HTTP 400/422 due to invalid payload | Usually no | Fix data/contract; retrying the same payload does not help |
| HTTP 401/403 | Usually no | Handle authentication/authorization; do not loop continuously |
| Business invariant violation | No | Return error or perform compensation per workflow |
| Order already processed successfully | Do not replay side effects | Record idempotency; return the processed result |
| Code bug, NullPointerException | Do not retry by default | Investigate/fix bug; retries do not reliably fix bugs |

**Principle:** Do not decide to retry solely because an exception is a `RuntimeException`. Classify exceptions clearly (e.g., `TransientProviderException` vs. `PermanentValidationException`). If an HTTP client wraps all errors in one class, inspect status/code/cause safely inside the adapter and translate into the appropriate exception type before invoking the retry mechanism.

For timeouts, **no response does not mean no side effect occurred**. That is why idempotency must accompany any retry policy.

## 3. Spring Event Dispatch and Where Errors Surface

### Synchronous Listener (Default)

`SimpleApplicationEventMulticaster` by default dispatches listeners on the publishing thread. With an `@EventListener` calling a service synchronously:

```text
publishEvent(OrderConfirmed)
        |
        v
@EventListener receives event
        |
        v
service processes
        |
        +--> succeeds --> listener returns
        |
        +--> uncaught exception --> may propagate back to publisher
```

If the listener runs inside a transaction opened by the application service, an unhandled exception can roll back the transaction depending on exception type and transaction configuration. A successful retry or a recovery that swallows the exception alters the error propagation path: **the transaction can proceed**, even though an auxiliary step exhausted attempts and did not complete.

### Asynchronous Listener

If `@Async` is used with an appropriate executor, the listener invocation runs on a different thread. Exceptions during listener execution **do not automatically** return to the publisher; retries must be configured inside the async processing branch. Large numbers of retries can occupy workers/queues and stall subsequent events.

### Transaction-Bound Listener

`@TransactionalEventListener` can bind processing to `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`. The default is `AFTER_COMMIT`; events published outside an active transaction by default **do not trigger** this type of listener unless `fallbackExecution = true` is set.

Hence, where retries live matters as much as `maxAttempts`. Retrying before commit can affect whether the core business operation commits; retrying after commit cannot automatically reverse already committed data.

## 4. Spring Retry: @Retryable, @Recover, and AOP Proxies

In a **Spring Boot 3.x / Spring Framework 6.x** application, the **Spring Retry 2.x** library can be used to retry bean method calls:

- `@EnableRetry`: enables retry annotation processing on matching beans.
- `@Retryable`: declares retryable exceptions, attempt count, and backoff policy.
- `@Backoff`: declares the delay between attempts.
- `@Recover`: handles failure when a `@Retryable` method cannot complete under the recovery policy.

These annotations belong to package **`org.springframework.retry.annotation`**. **Do not mix them up** with **Spring Framework 7**'s built-in resilience annotations, which have different configuration/parameters (e.g., `maxRetries` instead of `maxAttempts`). The example below pins Spring Boot 3.x and Spring Retry to avoid semantic confusion.

### Important Note on Attempts

In Spring Retry:

```java
@Retryable(
    retryFor = TransientProviderException.class,
    maxAttempts = 3,
    backoff = @Backoff(delay = 200))
public void deliver(DeliveryRequested event) {
    // One initial call + up to two retry attempts.
}
```

This is an **illustrative configuration fragment**; `maxAttempts=3` means **at most three total method invocations**, including the first one. When every attempt fails, there is no fourth attempt. The number of delays between three attempts is at most two.

### Why Put Retries in a Separate Service?

Retry relies on a Spring AOP proxy. A call from bean A to a **public method on a proxy-managed bean B** passes through the retry interceptor. Conversely, a method calling `this.deliver(...)` within **the same instance containing the retry method** normally bypasses the proxy: the annotation may have no effect.

Recommended architecture:

```text
@EventListener bean
    |
    v
retryingService.send(event)  <-- called via Spring bean/proxy
    |
    +--> retry interceptor
            |
            +--> external adapter
            +--> @Recover if attempts exhausted
```

This separation of responsibilities keeps listeners thin, makes the retrying method easy to unit-test independently, and reduces dependence on proxy ordering when combining `@EventListener`, `@Async`, and `@Transactional`.

## 5. Complete Java 17+ Example: Successful Retry and Exhausted Attempts

This example uses **Spring Boot 3.3.13**, Java 17+, Spring Retry 2.x, and Spring AOP. No database or real API is needed; the gateway is simulated with repeatable exceptions so the exact attempt counts can be verified.

Two events are sent:

1. `ORD-OK`: transient failure on attempts 1 and 2, succeeds on attempt 3.
2. `ORD-FAIL`: transient failure on all 3 attempts; `@Recover` is invoked, recording exhausted attempts.

### Project Structure

```text
listener-retry-demo/
├── pom.xml
└── src/main/java/example/events/ListenerRetryDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>listener-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.retry</groupId>
            <artifactId>spring-retry</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### ListenerRetryDemo.java

```java
package example.events;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.EnableRetry;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;

@SpringBootApplication
@EnableRetry
public class ListenerRetryDemo {

    public record DeliveryRequested(String orderId) {
    }

    public static class TransientProviderException
            extends RuntimeException {
        public TransientProviderException() {
            super("Temporary delivery-provider failure");
        }
    }

    // Separate bean so calls from the listener go through the Retry AOP proxy.
    public static class RetryingDeliveryService {
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        @Retryable(
                retryFor = TransientProviderException.class,
                maxAttempts = 3,
                backoff = @Backoff(delay = 10))
        public void deliver(DeliveryRequested event) {
            int n = attempts.computeIfAbsent(
                    event.orderId(), id -> new AtomicInteger())
                    .incrementAndGet();

            System.out.printf(
                    "ATTEMPT order=%s n=%d%n", event.orderId(), n);

            if ("ORD-FAIL".equals(event.orderId()) || n < 3) {
                throw new TransientProviderException();
            }

            System.out.println("DELIVERED order=" + event.orderId());
        }

        @Recover
        public void recover(TransientProviderException error,
                            DeliveryRequested event) {
            // Demo only prints a log. Production must have a durable error
            // recording path / send to DLQ or alert operations per policy.
            System.out.println("EXHAUSTED order=" + event.orderId());
        }
    }

    public static class DeliveryListener {
        private final RetryingDeliveryService deliveryService;

        public DeliveryListener(RetryingDeliveryService deliveryService) {
            this.deliveryService = deliveryService;
        }

        @EventListener
        public void on(DeliveryRequested event) {
            deliveryService.deliver(event);
        }
    }

    @Bean
    RetryingDeliveryService retryingDeliveryService() {
        return new RetryingDeliveryService();
    }

    @Bean
    DeliveryListener deliveryListener(
            RetryingDeliveryService deliveryService) {
        return new DeliveryListener(deliveryService);
    }

    @Bean
    CommandLineRunner scenario(ApplicationEventPublisher publisher) {
        return args -> {
            publisher.publishEvent(new DeliveryRequested("ORD-OK"));
            publisher.publishEvent(new DeliveryRequested("ORD-FAIL"));
        };
    }

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ListenerRetryDemo.class);
        app.setBannerMode(Banner.Mode.OFF);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner has been executed during startup.
        }
    }
}
```

### Compile, Run, and Output

Run in the directory containing `pom.xml`:

```bash
mvn -q package
java -jar target/listener-retry-demo-1.0.0.jar
```

Lines printed by **application code** in the following order (Spring Boot may print other startup/shutdown logs):

```text
ATTEMPT order=ORD-OK n=1
ATTEMPT order=ORD-OK n=2
ATTEMPT order=ORD-OK n=3
DELIVERED order=ORD-OK
ATTEMPT order=ORD-FAIL n=1
ATTEMPT order=ORD-FAIL n=2
ATTEMPT order=ORD-FAIL n=3
EXHAUSTED order=ORD-FAIL
```

**Why is the output deterministic?**

- `@EnableRetry` activates AOP; `DeliveryListener` calls `deliver(...)` on a **separate service bean** so the interceptor sees the invocation.
- For `ORD-OK`, the service throws `TransientProviderException` twice; the interceptor waits briefly and retries. The third attempt does not throw, so `DELIVERED` prints.
- For `ORD-FAIL`, all three attempts throw the exception. `@Recover` has the same `void` return type and accepts `TransientProviderException` plus the original method parameters; Spring Retry selects it once attempts are exhausted.
- `@Recover` here **returns normally**, so the listener and the `publishEvent(...)` call do not see an exception on the `ORD-FAIL` branch. This **does not mean the work was delivered successfully**. The demo intentionally highlights the risk of a log-only recovery.
- Event dispatch in the example is **synchronous**, so publishing `ORD-OK` finishes before `ORD-FAIL` is published. The program uses neither `@Async` nor transactions.

**Important limitation:** The `attempts` map lives only in memory; restarting the application loses that state. A real event needs an `eventId`/idempotency key, status tracking, and a durable recovery mechanism if deliveries must not be missed. `@Recover` does not automatically create a dead-letter entry, persist a job, or guarantee that an operator receives an alert.

Boot version 3.3.13 is used so the lesson has a concrete dependency, not as a recommendation to run an end-of-life branch in production. When deploying for real, choose a supported Spring Boot version and verify the corresponding APIs.

## 6. Define Retryable and Non-Retryable Conditions Explicitly

Production code typically has at least two categories of errors:

```java
public class TransientDeliveryException extends RuntimeException {
    public TransientDeliveryException(String message) {
        super(message);
    }
}

public class InvalidDestinationException extends RuntimeException {
    public InvalidDestinationException(String message) {
        super(message);
    }
}
```

These are **two illustrative classes** that must be placed in their respective Java files or adapted for an enclosing class. Only transient errors are allowed to retry:

```java
@Retryable(
    retryFor = TransientDeliveryException.class,
    noRetryFor = InvalidDestinationException.class,
    notRecoverable = InvalidDestinationException.class,
    maxAttempts = 4,
    backoff = @Backoff(delay = 100, multiplier = 2, maxDelay = 1000))
public void send(NotificationCommand command) {
    // Call provider; adapter maps HTTP/status/cause to error types.
}
```

This is an **illustrative method snippet, not a standalone program**: it assumes `NotificationCommand`, exception classes, annotation imports, and a bean called via proxy already exist.

- `retryFor`: allows retrying when the exception belongs to the listed types.
- `noRetryFor`: excludes those exceptions from retrying.
- `notRecoverable`: skips calling `@Recover` for these exception types; the error propagates to the caller. This is useful when data errors must be surfaced clearly, avoiding recording them as "handled via recovery."
- `maxAttempts=4`: one initial call + up to three retries.
- `delay=100, multiplier=2, maxDelay=1000`: growing backoff with a cap. These numbers are in **milliseconds**; do not copy example numbers blindly—measure real load.

If an error is recoverable yet attempts are exhausted, choose one of two explicit policies: let the exception propagate so the caller decides, or have `@Recover` persist a durable failure state and route the job to a long-term retry system. Never just `catch (Exception ignored)`, because then the application no longer knows which events failed.

### Choosing Retry via Predicate or Exception Mapping

With an HTTP client, you can translate:

```java
if (status == 429 || status == 503) {
    throw new TransientDeliveryException("Provider unavailable");
}
if (status == 400 || status == 422) {
    throw new InvalidDestinationException("Invalid request");
}
```

This is an **illustrative mapping fragment**, not a complete HTTP client. Status 429 should incorporate `Retry-After` and quota details if present; status 503 can also indicate prolonged maintenance, where in-request retries are ineffective. Statuses 409, 500, timeouts, and connection resets must be classified per the specific API—there is no single rule valid for all systems.

## 7. Backoff, Jitter, Time Limits, and Avoiding Retry Storms

If a downstream service is overloaded, 1,000 listeners retrying every second in lockstep can create a **retry storm**, preventing the service from recovering.

Key factors:

- **Attempt count:** bounds repeated work and prevents holding workers indefinitely.
- **Backoff:** waits between retries, typically increasing progressively.
- **Jitter:** adds randomness so workers do not all retry at the exact same instant.
- **Max delay and deadline:** do not wait past the processing time budget or SLA.
- **Rate limit / concurrency limit:** reduces concurrent requests rather than merely delaying each one.
- **Circuit breaker:** temporarily stops calling when downstream exhibits high error rates, instead of adding futile retries.
- **Retry-After:** for HTTP 429/503 when the provider supplies a hint, the policy should factor in the provider-specified wait time.

Theoretical backoff example:

```text
initial delay = 200 ms
multiplier    = 2
max delay     = 2,000 ms

Between attempts: 200 ms, 400 ms, 800 ms, 1,600 ms, 2,000 ms...
```

This is the delay sequence *if enough retries occur*, not Spring Retry's default configuration. For example, `maxAttempts=3` has only **two wait intervals**, not five.

For APIs with many workers, adding jitter helps spread retry timestamps; avoid a fixed synchronized timer across the whole fleet. If a request has already passed its deadline, continuing to retry only increases latency and load without helping the user experience.

**Caution:** Backing off by sleeping on a synchronous listener thread holds the publisher thread; backing off inside an async worker holds worker resources. When retries are needed minutes or hours later, offload to a durable queue/job scheduler rather than keeping Spring threads waiting long-term.

## 8. Retries Can Cause Duplicate Side Effects: Idempotency Is Mandatory When Needed

Suppose a listener sends a payment charge request:

```text
Client -> Payment API: charge ORD-101
Payment API: payment charged successfully
Network: response lost
Client: timeout, assumes failure
Client retry -> Payment API: charge ORD-101 again
```

If the API lacks deduplication, a single successfully processed business event can produce two side effects. **Never infer timeout = not executed.**

Safeguards:

1. Generate a stable **idempotency key** for *one business operation*, such as `paymentAttemptId` or `eventId`; retries must reuse **the same key**, never generating a new key on each attempt.
2. Send that key downstream if the API supports idempotency. If downstream does not support it, implement status checks or locking/unique constraints at the application layer.
3. Consumers maintain a processing ledger (*inbox/dedup table*) with a unique key, status, processing outcome, and appropriate transaction.
4. Distinguish **event seen** from **side effect completed**. Do not mark "processed" before the side effect can be confirmed or properly recovered.
5. If retries can run concurrently across multiple instances, prevent races with DB unique constraints/atomic operations rather than a single-JVM `ConcurrentHashMap`.

Example of an idempotency key at the messaging layer:

```json
{
  "eventId": "f6d7bc9b-5c7a-4c2d-81ec-2f0df60b30ef",
  "eventType": "order.confirmed",
  "orderId": "ORD-101",
  "createdAt": "2026-09-15T11:20:00Z"
}
```

When a message broker redelivers a record because a consumer crashed before ACK, the `eventId` key identifies it as **the same event redelivered**, not a new event. Guaranteeing *exactly-once business effects* requires consistent design across storage and side effects; `@Retryable` alone provides no such guarantee.

## 9. Retrying Listeners in Transactions: Before Commit and After Commit

### 9.1. Synchronous @EventListener When Publisher Is @Transactional

An application service may update an order's state and then call `publisher.publishEvent(new OrderConfirmed(...))` **inside an uncommitted transaction**:

```text
begin transaction
  update order
  publish event
      -> @EventListener
          -> retry send notification
commit / rollback transaction
```

Risk: the listener calls an external service successfully, and then the DB transaction rolls back. Sending emails/payments **does not automatically roll back** with the DB. Or prolonged retries keep the transaction holding locks too long, increasing deadlocks and timeouts.

If the listener throws an unchecked exception after exhausting retries and the exception crosses the transaction boundary, the transaction normally rolls back per Spring's rules; however, if `@Recover` catches the error and returns normally, the publisher may proceed to commit even though the auxiliary action did not complete. **Recovery is a business decision, not merely logging.**

### 9.2. @TransactionalEventListener(AFTER_COMMIT)

When processing should occur only after DB updates have committed, you can use:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {
    private final DeliveryService deliveryService;

    public OrderAfterCommitListener(DeliveryService deliveryService) {
        this.deliveryService = deliveryService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        deliveryService.process(event);
    }
}
```

This is an **illustrative class, not part of the Section 5 demo**. It assumes `DeliveryService`/`OrderConfirmed` are defined and the event is published **inside an active transaction**. Without a transaction, the listener by default **does not run**, because `fallbackExecution=false`.

`AFTER_COMMIT` avoids sending notifications for rolled-back transactions, but understand:

- When the listener runs, the original transaction **has already committed**; failures or exhausted retries **do not roll back the original transaction**.
- The listener may still run synchronously on the transaction-completing thread; long retries can extend response latency even though the DB already committed.
- After commit, some transaction resources remain bound to the thread. If the listener needs to write to the DB **in an independent transaction**, use a separate service with `@Transactional(propagation = Propagation.REQUIRES_NEW)` via a Spring proxy or a `TransactionTemplate` creating a new transaction.
- A process crash after DB commit yet before the listener finishes can still **lose** the auxiliary work.

Do not merely slap `@Async` onto `@TransactionalEventListener` and think durability is solved: async tasks can also be rejected or lost when the process dies.

### 9.3. BEFORE_COMMIT and AFTER_ROLLBACK

- `BEFORE_COMMIT` runs before commit; if the auxiliary work fails and the exception is unhandled, commit can be blocked. Yet calling external APIs before commit still risks non-rollbackable side effects.
- `AFTER_ROLLBACK` is suitable for recording or compensating after a transaction fails by design. It **does not automatically retry the entire business transaction**.
- `AFTER_COMPLETION` executes after the transaction finishes regardless of commit/rollback; verify the business intent before performing side effects.

If retrying a DB operation due to a deadlock or transaction failure, organize retries at **the boundary of the entire unit of work**, giving each attempt a **new transaction**, rather than issuing more statements inside a transaction already marked rollback-only.

## 10. When Is @Retryable Not Enough? Outbox, Job Queues, and DLQ

An in-memory Spring listener is not a durable broker. For critical events (payments, shipment creation, refunds, data distribution), "try three times and stop" usually falls short.

Failure example:

```text
DB commit order CONFIRMED
            |
            v
Application process crash
            |
            X  listener has not run or has not sent successfully yet
```

Not even `AFTER_COMMIT` turns auxiliary work into a durably persisted record. **Transactional Outbox** closes this gap:

```text
One transaction:
  update order
  insert outbox(eventId, payload, status=NEW)
  commit
        |
        v
Outbox worker / CDC
        |
        +--> send succeeded --> record/ACK
        |
        +--> transient error --> retry per schedule and backoff
        |
        +--> limit exhausted / poison message --> DLQ or FAILED
```

Operational components required:

- **Durable retry state:** attempt count, `nextRetryAt`, last error, status, expiration time.
- **Idempotency:** prevent duplicate side effects when a worker crashes after sending but before updating status.
- **Visibility/lease:** prevent two workers from picking up the same job without protection.
- **Poison-message handling:** move unprocessable messages to a DLQ/quarantine, with an investigation and controlled replay process.
- **Dead-letter / exhausted alert:** never silently drop tasks, especially for critical business events.
- **Retention and audit:** define history retention for tracing over an appropriate period.

Spring Retry fits **short retries within a single execution**. Outbox/broker/job schedulers fit **long-term retries surviving restarts/crashes and spanning multiple instances**. Both can be combined: a few quick retries in a worker, then persisting the failure to await the next processing cycle.

## 11. Designing Recovery Instead of Just Swallowing Exceptions

A processing failure typically has three distinct outcomes to represent:

1. **SUCCEEDED:** the side effect was confirmed successful.
2. **RETRY_SCHEDULED:** not yet succeeded, but state was saved for reprocessing.
3. **FAILED_PERMANENTLY / NEEDS_INTERVENTION:** cannot complete automatically; trace and handling workflow exist.

If a `@Recover` method merely logs one line and returns, Spring Retry considers the method invocation recovered, while the publisher sees the call finish normally. This can be valid if the recovery method **persisted a failed job to a durable queue** or applied an explicit business policy; it is invalid if reliable notification delivery is required yet nothing was saved.

A clearer recovery pattern (illustrative only, requiring dependent beans to be supplied):

```java
@Recover
public void recover(TransientDeliveryException ex,
                    DeliveryRequested event) {
    // failedDeliveryRepository must persist state durably;
    // not just a log or in-memory Map.
    failedDeliveryRepository.recordForLaterRetry(
            event.orderId(), ex.getMessage());
}
```

This is an **illustrative configuration snippet**, assuming `failedDeliveryRepository` and types are defined. If saving the failure state itself fails, decide whether to let the exception propagate or route to another safe mechanism; do not keep swallowing.

If the policy is that errors must fail the publisher, **do not declare a swallowing recovery** for that exception type. Use `notRecoverable` for non-recoverable exception groups or let the final exception propagate per contract. What matters is that the caller knows accurately which of the three outcomes occurred, rather than treating every normally returning method call as "sent successfully."

## 12. Retries and Thread Pools: Performance and Backpressure

With `@Async @EventListener` or a multicaster with an executor:

- Each listener waiting on backoff can occupy a worker and hold resources.
- When incoming event rate exceeds completion rate, the queue grows.
- When both the queue and pool are full, the executor may **reject tasks right at submission**. This is a **before-listener-runs** failure, not an exception thrown inside the retry method.
- `@Retryable` inside the listener **does not solve** task-submission errors from the executor.
- If failing retries drag on, end-to-end event latency climbs; never equate `publishEvent(...)` returning with work completion.

An in-memory queue can lose tasks when the process dies. For critical events that must resume after restarts, use durable jobs/outbox.

Minimum dashboard: queue depth, active threads, rejected task count, event processing latency, attempt counts, retry-success rate, exhausted task count, and downstream errors by category. Do not just measure `@Retryable` invocations and conclude "processing succeeded."

## 13. Retry Observability: Metrics, Logs, and Alerts

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `listener.events.received` | Number of events the listener actually received |
| `listener.attempts.total` | Number of operation executions (including initial attempt) |
| `listener.retries.total` | Number of retries, excluding initial attempt |
| `listener.succeeded.total` | Number of tasks completing the side effect |
| `listener.exhausted.total` | Number of tasks exhausting attempts without completing |
| `listener.permanent_failure.total` | Non-retryable errors or errors needing data fixes |
| `listener.retry_delay` | Observed delay/backoff |
| `listener.end_to_end_latency` | From publish until final business state |
| `listener.duplicate_skipped.total` | Number of redelivered events blocked by idempotency |

These are **suggested application metric names**, not metrics automatically exported by Spring Boot. With Micrometer, tag event type, error category, provider name, and outcome; **do not attach `eventId`/`orderId` as tags** because that creates huge cardinality. Put IDs into access-controlled logs/traces.

Useful log fields: event type, eventId, attempt/maxAttempts, retry decision, next retry time, error category, correlation/trace ID, and final outcome. Avoid logging tokens, secrets, and full payloads containing PII in error logs.

Alerts should fire when `exhausted` or `permanent_failure` spikes for critical event types, when queue backlogs persist, or when retry rates climb alongside worsening latency. A rising retry count is not necessarily an outage if the system still completes quickly within thresholds; what matters is business completion and upstream impact.

## 14. Testing Matrix: Retry Correctly and Stop Correctly

| Scenario | What to assert |
| --- | --- |
| Succeeds on first attempt | `deliver()` called exactly once, no backoff |
| Transient failure twice then succeeds | Exactly 3 total attempts; `@Recover` not called |
| Continuous transient failure up to limit | Exactly `maxAttempts`; recovery or final exception per policy |
| Non-retryable error | No loop; exception/recovery per `noRetryFor` and `notRecoverable` |
| Listener calls retry method via another bean | AOP interceptor actually applied |
| Method called via `this.method()` | Test detects self-invocation is not retry-proxied |
| Sync event published when listener throws | Publisher sees exception per multicaster/handler config |
| `@Async` listener throws | Publisher is not assumed to receive async execution exceptions |
| Event published in transaction with AFTER_COMMIT listener | Runs only after successful commit |
| Transaction rolls back | AFTER_COMMIT does not execute side effect |
| Published outside transaction | `@TransactionalEventListener` does not run by default |
| Timeout after downstream already processed | Retry creates no duplicate side effects due to idempotency |
| Worker/process restarts between attempts | With durable model, job resumes from saved state |
| Task rejected by executor before running | Recorded separately, not confused with internal retry exceptions |
| Downstream returns 429 | Respects rate limit/backoff; no retry storm |
| Poison event always fails data checks | Routed to DLQ/quarantine; no infinite loop |

### Spring Boot Testing Tips

- Use a mock/stub gateway with an attempt counter and scripted errors; assert invocation counts and final outcome.
- Test through a real bean in the Spring context to ensure the AOP proxy is active; calling `new RetryingDeliveryService()` in a unit test will **not** trigger `@Retryable`.
- For `AFTER_COMMIT` transaction tests, be careful: many Spring tests roll back by default after the test if marked `@Transactional`. To observe `AFTER_COMMIT`, you need a **real commit** or appropriate test transaction APIs.
- For async, use a latch or timed wait condition rather than arbitrary `Thread.sleep(...)`; do not assert completion order if the design does not guarantee it.
- For outbox, simulate a crash between "downstream received" and "marking outbox sent" to verify idempotency.

In the Section 5 demo, the two scenarios `ORD-OK` and `ORD-FAIL` demonstrated attempt counts and the recovery path. To test fail-fast on permanent exceptions, add an adapter throwing `InvalidDestinationException` and the `noRetryFor/notRecoverable` policy as in Section 6.

## 15. Common Mistakes When Adding Retries to Event Listeners

**Mistake 1 — Assuming Spring automatically retries every listener.** `publishEvent(...)` is not a durable broker; errors can propagate back, be handled by an error handler, or happen on an async thread. Configure retries explicitly.

**Mistake 2 — Putting @Retryable on a method called via this.** Spring Retry uses proxies; self-invocation usually bypasses the interceptor. Call a separate service bean via DI.

**Mistake 3 — Retrying every RuntimeException.** Validation and business errors do not heal themselves; classify exceptions to avoid storms.

**Mistake 4 — Not bounding attempts/delays.** Infinite retries or huge backoffs can tie up threads and clog queues.

**Mistake 5 — Retrying after timeouts without idempotency.** The API may have already processed successfully. Use stable keys and deduplication.

**Mistake 6 — @Recover just logging and returning.** The listener treats the work as resolved while it actually failed. Persist status, send alerts, or propagate the exception per contract.

**Mistake 7 — Confusing DB rollback with rolling back external side effects.** Sent emails and HTTP calls cannot be automatically undone by a Spring transaction.

**Mistake 8 — Treating AFTER_COMMIT as a delivery guarantee.** The process can die after commit before the listener completes. Use an outbox when events must not be lost.

**Mistake 9 — Retrying DB work inside a rollback-only transaction.** When the first attempt leaves the transaction unusable, retrying individual statements in the same transaction is insufficient; retry the entire unit of work with a fresh transaction.

**Mistake 10 — Forgetting async has separate submission errors.** Executor rejection happens before the listener; monitor/protect the task submission path too.

**Mistake 11 — Mixing retry APIs across Spring generations.** Spring Retry 2.x uses `org.springframework.retry.annotation.Retryable` with `maxAttempts`; Spring Framework 7 has a different resilience API. Verify imports/dependencies and semantics before copying examples.

## 16. Implementation Checklist

Before shipping listener retries to production:

1. Are **transient** and **permanent** errors classified by business exception/status?
2. Is the operation **safe to repeat**? If not, is there an idempotency key/unique constraint?
3. Are `maxAttempts`, backoff, jitter, deadline, rate limit, and timeout defined?
4. Is the method actually invoked **through a Spring retry proxy**?
5. With `@Recover`, is the failure outcome persisted/routed rather than merely logged?
6. Does the listener run synchronously or asynchronously, and could it impact requests/thread pools/queues?
7. Should DB-related events run `BEFORE_COMMIT` or `AFTER_COMMIT`, and why?
8. If a failed DB transaction must be retried, is a **fresh transaction per attempt** designed?
9. If the process dies or restarts, do critical events recover via an outbox/broker/job store?
10. Are there metrics/logs for attempts, succeeded, exhausted, rejected, lag, and duplicates?
11. Are there tests for success, exhausted attempts, permanent errors, rollback, async, and idempotency?

**Conclusion:** Listener retries are not just "call again after an error." A proper retry mechanism requires **explicit retry conditions, finite attempts and time bounds, idempotency, transparent recovery outcomes, and proper transaction boundaries**. Use Spring Retry for short-lived errors within a single execution; use durable storage and long-term retry flows when events must not be lost.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): default dispatch, synchronous and asynchronous listeners.
- [Spring Retry — Project documentation](https://github.com/spring-projects/spring-retry): `@EnableRetry`, `@Retryable`, `@Recover`, and Spring Retry 2.x APIs.
- [Spring Retry — Retryable annotation](https://github.com/spring-projects/spring-retry/blob/main/src/main/java/org/springframework/retry/annotation/Retryable.java): `retryFor`, `noRetryFor`, `notRecoverable`, `maxAttempts`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and transaction phases.
- [Spring Framework 7 — Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html): new resilience API; note differences from Spring Retry when reading examples.

# Bounded Retry When Handling Spring Application Events

An event may be published successfully, yet a listener still fails due to a **transient error**: a reset network connection, a downstream service returning HTTP 503, a database deadlock, or a short-lived unavailable resource. If the application **does not retry**, secondary work can be missed. If the application **retries infinitely**, a small failure can pin request threads, saturate thread pools, amplify downstream load, and trigger cascading outages.

**Bounded retry** is a policy permitting **at most a defined number of attempts**, retrying only appropriate failures, with backoff/timeouts and a clear handling path upon exhaustion. With Spring Framework Application Events, what matters is not only "how many times to retry" but also **where to retry, inside which transaction, and what to do with the event when every attempt fails**.

This lesson focuses on `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener`, executors/async, and choosing among **in-JVM synchronous retries**, **Spring Retry via AOP**, and **durable queues/Transactional Outbox**. These strategies provide different guarantee boundaries and cannot be swapped arbitrarily.

## 1. Retry Is Both a Business and Reliability Decision

For example, when creating an order, the application publishes `OrderPlaced`; a listener sends a notification to another service:

```text
OrderService
    |
    +-- save(order)
    |
    +-- publishEvent(OrderPlaced)
              |
              +-- NotificationListener
                      |
                      +-- attempt 1 -> 503 Service Unavailable
                      |
                      +-- backoff 100 ms
                      |
                      +-- attempt 2 -> timeout
                      |
                      +-- backoff 200 ms
                      |
                      +-- attempt 3 -> 200 OK
```

The three calls are not three independent business events; they are **three attempts to process the same logical event**. Thus the event should have a stable identifier (`eventId`) to correlate logs, metrics, and support downstream idempotency.

Distinguish the concepts:

| Concept | Meaning |
| --- | --- |
| **Logical event** | A single business fact, e.g. `OrderPlaced(eventId=evt-42)` |
| **Attempt** | One invocation of event processing; one event may have multiple attempts |
| **Retry policy** | Rules determining whether to retry, maximum attempts, and wait duration |
| **Backoff** | Wait duration between attempts to reduce pressure on a failing resource |
| **Retry exhaustion** | All attempts/budget spent yet the operation still failed |
| **Dead-letter / failure state** | Place holding work that cannot automatically proceed further |
| **Idempotency** | Reprocessing the same event does not create wrong or duplicate side effects |
| **Delivery guarantee** | What the system actually guarantees about persistence, delivery, retries, and event loss |

**Do not equate in-memory retries with durability.** A retry loop running on a listener thread **does not durably persist the event**. Process death before the final attempt can wipe out all work even if the policy specified `maxAttempts=3`.

## 2. Do Spring Event Listeners Retry Automatically?

**No.** `ApplicationEventPublisher.publishEvent(...)` and `@EventListener` in Spring Framework **do not automatically retry failing listeners under a bounded policy**.

With the default `SimpleApplicationEventMulticaster`:

1. Normal listeners run **synchronously** on the thread publishing the event.
2. If a listener throws an exception, there is no default `ErrorHandler`, so the error can **propagate to the publisher** and halt the current multicast pass.
3. If the publisher is inside a transactional method, an unchecked exception propagating out can cause the transaction to **roll back per Spring transaction rules**.
4. If the application configures an executor, `@Async`, or a custom error handler, propagation behavior may differ. Catching and logging an error does not mean the error is retried.

```java
@EventListener
public void handle(OrderPlaced event) {
    notificationGateway.send(event);
}
```

This is only **illustrative code** with application-provided types. If `send(...)` throws a transient error, the default Spring event bus will not call `handle(...)` three times automatically.

### Three Places to Place Retries

| Location | What is retried? | Key consequence |
| --- | --- | --- |
| **Inside synchronous listener** | Repeats calls to a dependency or sub-handler | Can hold request/transaction open longer; final error propagates to publisher |
| **At service/Spring Retry proxy** | Retries a method invocation via AOP | Requires valid proxy, policy, and accurate transaction boundaries |
| **Outbox worker/broker consumer** | Retries a durably persisted job/message | Decoupled from request, survives restarts; needs dedup, queues, backoff, operations |

Do not assume all three give the same guarantee level. Putting retries inside a synchronous listener may suffice for secondary information, but **does not guarantee post-commit event delivery if the process dies**.

## 3. Rules for Designing a Bounded Retry

### 3.1. Retry Only Transient Errors, Not Every Throwable

**Retriable group** when the operation is safe/idempotent and budget remains:

- HTTP 503/502/504 or transient connection errors to a downstream.
- HTTP 429 when the response and contract permit retrying; honor `Retry-After` if present.
- Database deadlocks/serialization conflicts when it is safe to rerun the **entire transactional unit**.
- Timeouts when a mechanism exists to check state or use an idempotency key to prevent duplicate execution.

**Usually not automatically retried:**

- Fixed data errors such as missing required fields, malformed IDs, or violated business invariants.
- HTTP 400/401/403 when nothing changes credentials/permissions.
- Code bugs (`NullPointerException`, bad config, or fixed mapping defects).
- Failures where a side effect already happened yet the client does not know the outcome, **if idempotency/deduplication is absent**.
- Cases past deadline or canceled by the caller.

Do not use `catch (Exception)` to retry all errors blindly. Define a **retryable exception taxonomy** or predicate based on real errors/responses. Exceptions that cannot self-heal must surface early rather than clogging queues.

### 3.2. Attempt Count: Including the First Call

Setting `maxAttempts = 3` means:

```text
attempt 1: initial invocation
attempt 2: first retry
attempt 3: second retry
STOP: no attempt 4
```

This is also how **Spring Retry 2.x `@Retryable(maxAttempts = 3)`** works: at most three invocations **including the initial call**.

**Do not confuse this with Spring Framework 7 core `@Retryable(maxRetries = 3)`**, which specifies **at most three retries after the initial invocation**. Annotation names, packages, and semantics differ; for the **Spring Framework 6.2** project in this lesson, `@Retryable` used in section 6 is the **Spring Retry add-on**, not Spring Framework 7's core annotation.

Document an unambiguous parameter like `maxAttempts` in your project instead of saying "retry 3 times", which can be interpreted as 3 total or 4 total calls.

### 3.3. Backoff, Jitter, and Deadlines

A common policy:

```text
delay(attempt) = min(maxDelay, initialDelay × multiplier^(attempt - 1))
```

Here `attempt` in the formula is the **index of the failure scheduling a retry**, starting at 1. With `initialDelay=100 ms`, `multiplier=2`, `maxDelay=500 ms`, and `maxAttempts=4`:

| Invocation | If failed, wait before next | Notes |
| --- | --- | --- |
| 1 | 100 ms | Retry attempt 2 |
| 2 | 200 ms | Retry attempt 3 |
| 3 | 400 ms | Retry attempt 4 |
| 4 | **No wait** | Exhausted, stop |

Total backoff before exhausting 4 attempts is **700 ms**, excluding each attempt's execution time. If each attempt has a 2-second network timeout, worst-case total time can approach **8.7 seconds** or more due to overhead.

**Jitter** adds randomness to delays to prevent thousands of failing clients from retrying at the exact same instant. Under heavy load, exponential backoff without jitter can cause synchronized retry waves slamming downstream every cycle.

A solid retry policy usually has **two ceilings**:

- **Attempt budget:** e.g., 3 attempts, no infinite loops.
- **Elapsed-time budget/deadline:** e.g., if less than 2 seconds remain, do not start another attempt.

For requests with deadlines, do not merely multiply attempts by timeout and hope to meet SLAs. For meaningful retries, set per-attempt timeouts, an overall timeout, and queue-wait limits in async processing.

### 3.4. On Exhaustion: What Happens?

Exhausting retries is **a business/operational outcome that must be explicitly defined**, not merely printing a stack trace:

- If the listener is a **mandatory pre-commit step**, propagate the final error or mark rollback-only per transaction policy.
- If it is a **post-commit** side effect, the source transaction cannot be rolled back. Persist failure state and provide a reprocessing/reconciliation mechanism.
- If it is only **best-effort telemetry**, you may record a metric and stop deliberately without failing the request.
- If the event entered a **durable queue/outbox**, mark retry exhaustion, move to dead-letter/quarantine, or alert for investigation; never delete the message without a deliberate decision.

You must know the **actual attempt count**, final exception, event ID, and terminal state. A system reporting "success" by swallowing an error after 3 attempts is wrong if required work did not finish.

## 4. Runnable Java 17+ Example: Maximum Three Attempts in @EventListener

This example uses **Spring Framework 6.2.9**, without Spring Boot, a database, or the Spring Retry dependency. To make the algorithm transparent, a `BoundedRetry` class performs at most **3 attempts** and waits `10 ms`, `20 ms` on transient errors. The goal is teaching **bounded retry + backoff + exception propagation**; in production, avoid `Thread.sleep(...)` loops inside requests/transactions when durable workers can run the work.

Three cases are simulated:

1. `evt-A`: first two attempts fail transiently, third attempt succeeds.
2. `evt-B`: all three attempts fail transiently, policy throws `DeliveryExhaustedException` preserving **cause**.
3. `evt-C`: permanent data error, stops **on the very first attempt**, no retry.

### 4.1. Structure

```text
bounded-event-retry-demo/
├── pom.xml
└── src/main/java/example/BoundedEventRetryDemo.java
```

### 4.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>bounded-event-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.BoundedEventRetryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. src/main/java/example/BoundedEventRetryDemo.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class BoundedEventRetryDemo {

    public record NotificationRequested(String eventId) {}

    public static class TransientDeliveryException extends RuntimeException {
        public TransientDeliveryException(String message) {
            super(message);
        }
    }

    public static class DeliveryExhaustedException extends RuntimeException {
        public DeliveryExhaustedException(String eventId, Throwable cause) {
            super("exhausted retries for " + eventId, cause);
        }
    }

    public static class BoundedRetry {
        private static final int MAX_ATTEMPTS = 3;

        public void execute(String eventId, Runnable operation) {
            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    operation.run();
                    return;
                } catch (TransientDeliveryException original) {
                    if (attempt == MAX_ATTEMPTS) {
                        System.out.println("retry: exhausted " + eventId
                                + " after " + attempt + " attempts");
                        throw new DeliveryExhaustedException(eventId, original);
                    }

                    long delayMillis = 10L << (attempt - 1);
                    System.out.println("retry: " + eventId
                            + " attempt=" + attempt
                            + " delayMs=" + delayMillis);
                    try {
                        Thread.sleep(delayMillis);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "retry interrupted for " + eventId,
                                interrupted);
                    }
                }
            }
        }
    }

    public static class NotificationListener {
        private final BoundedRetry retry;
        private final Map<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        public NotificationListener(BoundedRetry retry) {
            this.retry = retry;
        }

        @EventListener
        public void onNotificationRequested(NotificationRequested event) {
            retry.execute(event.eventId(), () -> {
                int current = attempts.computeIfAbsent(
                        event.eventId(), key -> new AtomicInteger())
                        .incrementAndGet();

                System.out.println("listener: " + event.eventId()
                        + " attempt=" + current);

                if ("evt-A".equals(event.eventId()) && current < 3) {
                    throw new TransientDeliveryException("gateway temporary");
                }

                if ("evt-B".equals(event.eventId())) {
                    throw new TransientDeliveryException("gateway temporary");
                }

                if ("evt-C".equals(event.eventId())) {
                    throw new IllegalArgumentException("invalid payload");
                }

                System.out.println("listener: delivered " + event.eventId());
            });
        }
    }

    public static class NotificationService {
        private final ApplicationEventPublisher publisher;

        public NotificationService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void request(String eventId) {
            System.out.println("publisher: " + eventId);
            publisher.publishEvent(new NotificationRequested(eventId));
            System.out.println("publisher: returned " + eventId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        BoundedRetry boundedRetry() {
            return new BoundedRetry();
        }

        @Bean
        NotificationListener notificationListener(BoundedRetry retry) {
            return new NotificationListener(retry);
        }

        @Bean
        NotificationService notificationService(
                ApplicationEventPublisher publisher) {
            return new NotificationService(publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            NotificationService service =
                    context.getBean(NotificationService.class);

            service.request("evt-A");

            try {
                service.request("evt-B");
            } catch (DeliveryExhaustedException exhausted) {
                System.out.println("caller: " + exhausted.getMessage()
                        + " cause="
                        + exhausted.getCause().getClass().getSimpleName());
            }

            try {
                service.request("evt-C");
            } catch (IllegalArgumentException permanent) {
                System.out.println("caller: permanent " + permanent.getMessage());
            }
        }
    }
}
```

Run with JDK 17+ and Maven in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines printed by the program, in exact order during a normal run (excluding Spring/Maven logs):

```text
publisher: evt-A
listener: evt-A attempt=1
retry: evt-A attempt=1 delayMs=10
listener: evt-A attempt=2
retry: evt-A attempt=2 delayMs=20
listener: evt-A attempt=3
listener: delivered evt-A
publisher: returned evt-A
publisher: evt-B
listener: evt-B attempt=1
retry: evt-B attempt=1 delayMs=10
listener: evt-B attempt=2
retry: evt-B attempt=2 delayMs=20
listener: evt-B attempt=3
retry: exhausted evt-B after 3 attempts
caller: exhausted retries for evt-B cause=TransientDeliveryException
publisher: evt-C
listener: evt-C attempt=1
caller: permanent invalid payload
```

### Analysis

- `NotificationListener` is a Spring bean declared via `@Bean`; `@EventListener` is discovered by Spring when the context refreshes.
- `ApplicationEventPublisher` uses the default synchronous multicaster, so the attempts for `evt-A` run **before** `service.request("evt-A")` returns. The `10+20 ms` delays add to the caller's wait time, excluding execution time.
- `BoundedRetry` catches only `TransientDeliveryException`. Therefore, `IllegalArgumentException` for `evt-C` **is not retried**; it exits immediately on the first attempt.
- When `evt-B` exhausts three attempts, `DeliveryExhaustedException` preserves the final exception in `getCause()`. The caller does not receive a generic error hiding the root cause.
- The demo uses a `Map` to **simulate attempt counts within one process**. This is not an idempotency table, does not protect against duplicate events across multiple instances, and does not survive restarts.
- `Thread.sleep(...)` is only to make backoff visible in code. An executor/scheduler or background worker is the right place for longer retry waits; avoid tying up request threads or database transactions.
- The demo **does not open a transaction**, so this stdout must not be used to assert commits or rollbacks. In an application with `@Transactional`, test both propagation policies and database state.

The demo's policy has at most three attempts; **there is no fourth retry**. Each transient failure continues only while attempts remain, whereas permanent errors and interrupts terminate immediately. Real programs also need **deadlines**, jitter, metrics, retry-safe operations, and durable recovery mechanisms when required.

## 5. Spring Retry 2.x: @Retryable and @Recover with Listeners

With Spring Framework 6.2, you can add **Spring Retry** (artifact `org.springframework.retry:spring-retry`) and AOP support to use `org.springframework.retry.annotation.Retryable`, `@EnableRetry`, `@Backoff`, and `@Recover`.

This is an **add-on library**, not built-in retries for every `@EventListener`. You must configure `@EnableRetry` and ensure the method is invoked through a **Spring proxy**. Because an event listener typically orchestrates work, a clean pattern is letting the listener call **a separate retried service**, rather than mixing retry logic directly into the annotated listener method itself.

### Integration Example Using Spring Retry

```java
@Configuration
@EnableRetry
class RetryConfiguration {
    // Spring Retry creates retry advice for eligible beans.
}
```

```java
@Service
public class NotificationDeliveryService {

    @Retryable(
        retryFor = TransientGatewayException.class,
        maxAttempts = 3,
        backoff = @Backoff(delay = 100, multiplier = 2)
    )
    public void deliver(NotificationRequested event) {
        gateway.send(event);
    }

    @Recover
    public void exhausted(
            TransientGatewayException lastFailure,
            NotificationRequested event) {
        throw new DeliveryExhaustedException(
                event.eventId(), lastFailure);
    }
}
```

```java
@Component
public class NotificationEventListener {
    private final NotificationDeliveryService delivery;

    public NotificationEventListener(NotificationDeliveryService delivery) {
        this.delivery = delivery;
    }

    @EventListener
    public void onNotificationRequested(NotificationRequested event) {
        delivery.deliver(event); // Called through another bean's proxy.
    }
}
```

The three snippets above are **illustrative integration code, not a standalone project**: you need imports, `gateway`, event DTOs, exception types, a compatible Spring Retry version, AOP dependencies (in Spring Boot typically `spring-boot-starter-aop`), and Spring context config. `@Recover` requires a signature compatible with the retryable method (matching return type, exception, and remaining arguments). For a `void` method, recovery above is also `void` but throws a wrapped exception rather than lying that delivery succeeded.

Explanation:

- `retryFor = TransientGatewayException.class` restricts which errors are retried; permanent validation errors are not retried.
- `maxAttempts = 3` is the **total invocation count including the first call**, per Spring Retry 2.x.
- `delay=100`, `multiplier=2` applies policy backoff; do not assume this provides durability across process crashes.
- `@Recover` runs once retries exhaust attempts; in the example it **propagates failure** with the cause. You can change it to persist a durable failure state if appropriate, but never swallow errors for mandatory steps without an explicit business decision.
- If `NotificationDeliveryService` calls `this.deliver(...)` from inside its own bean, **self-invocation can bypass the proxy**, preventing retries from running. Calling from a separate listener bean through an injected Spring-managed service avoids this pitfall.
- `@EnableRetry` creates advice/proxies; verify the annotation actually takes effect with an integration test intentionally failing two attempts and succeeding on the 3rd, not just by eyeballing the annotation in source.
- Control the ordering of retry advice and transaction advice. A retry inside a transaction already marked rollback-only is **not equivalent** to re-running a transactional operation after rollback; to retry deadlocks/serialization failures, you normally must retry **an entire new transaction** at a defined boundary.

**Notable difference between Spring Retry 2.x and Spring Framework 7:** Spring Framework 7 core introduces resilience `@Retryable` in its own package with attributes like `maxRetries`, which do not have identical semantics to `maxAttempts` above. Never conflate the two annotations merely because they share a name.

## 6. Retrying Inside Transactions: Be Clear Which Transaction Is Retried

### 6.1. Synchronous Retry Inside the Source Transaction

```java
@Transactional
public void placeOrder(Command command) {
    repository.save(...);
    publisher.publishEvent(new OrderPlaced(...));
}
```

This is **illustrative code**, not standalone runnable code.

Suppose a listener performs three HTTP calls inside the source transaction:

- Backoff waits can hold **transactions/connections/locks** open longer.
- If a DB operation in the listener marks the transaction **rollback-only** on the first attempt, a subsequent successful retry inside **that same transaction** may still fail to commit.
- When the listener finally fails with an unchecked exception that propagates out, the transaction interceptor may roll back. **If the listener catches the error and returns normally**, the transaction may commit even though the side effect failed.
- An external operation may have completed even when the client sees a timeout; retrying without an idempotency key can execute the side effect **twice** before the local transaction learns the result.

If the business requires atomicity, design retries for **the entire use case/transaction** at the right boundary. A transaction marked rollback-only cannot be "revived" by calling a small method again inside that same rollback-only transaction.

### 6.2. @TransactionalEventListener(AFTER_COMMIT)

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    notificationDeliveryService.deliver(event);
}
```

This is **illustrative integration code**, requiring the corresponding beans/imports. The listener is invoked only upon a **successful commit** of the source transaction; by default `fallbackExecution = false`, so publishes outside a matching transaction may be ignored.

Retries inside this callback:

- **Cannot roll back the already-committed source transaction.**
- Can still block the thread completing the commit if the listener and retries run synchronously.
- If the process dies right after commit, an in-JVM callback may never run; the annotation **does not automatically provide durable delivery**.
- If the callback needs to update the DB to record notification delivery status, it may need a **new transaction**, e.g., a `@Transactional(propagation = Propagation.REQUIRES_NEW)` service invoked via a Spring proxy in imperative flows.

Do not treat "event published", "transaction committed", "listener retries exhausted", and "notification delivered" as a single state. They belong to distinct layers of responsibility.

### 6.3. Async Listeners Do Not Carry the Caller's Transaction

With `@Async @EventListener`, work runs on an executor thread and **does not automatically inherit the request's thread-bound transaction**. Errors on the worker do not automatically propagate to the publisher; retries on the worker do not roll back the source transaction either.

You can configure `AsyncUncaughtExceptionHandler` for `void` async methods, or manage completion via `Future`/`CompletableFuture` APIs at the right layer. However, merely "logging async errors" **is not a durable retry queue**.

A transaction-synchronized listener may need to run on the publishing thread to register synchronization; do not configure a custom multicaster executor assuming all transactional listeners are safely moved onto workers.

## 7. Bounded Retries Must Guarantee No Duplicate Delivery Effects

Suppose we call:

```text
sendPaymentConfirmation(evt-42)
   |
   +-- request reaches gateway: gateway SUCCEEDS
   |
   +-- response is lost, client sees timeout
   |
   +-- retry: gateway processes AGAIN
```

From the client's perspective, the first attempt "failed", yet the side effect may already have happened. **Retries alone do not make an operation safe.**

### 7.1. Stable Idempotency Key

Use a stable `eventId`/business operation ID **across all attempts**. For example, an idempotency-aware API accepts a header:

```text
Idempotency-Key: evt-42
```

If the gateway enforces an idempotency contract, two requests with the same key can be handled as one logical operation. Never assume every downstream supports or honors that header automatically.

On the consumer side, you can design a `processed_events` table:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

This is an **illustrative schema**. To guarantee idempotency for DB side effects, checking/recording the marker and applying the business change must be coordinated **in the same transaction or using unique constraints/atomic inserts**. Checking "already processed?" before acting without a unique constraint can race between two workers.

Never use an ID generated **fresh on every retry** as an idempotency key, because that makes attempts look like distinct operations.

### 7.2. Avoiding Retry Storms

When thousands of consumers hit HTTP 503 simultaneously, backoff with jitter, global concurrency limits, circuit breakers, and rate limits may be required. Do not rely solely on `maxAttempts=3`: 1,000 failing requests with 3 attempts can generate **3,000 calls** against an already overloaded service.

Use deadlines and `Retry-After` hints when provided by the backend. For HTTP 429, retrying immediately without backoff usually makes things worse. When a circuit breaker is open, pointless retries can fail fast; define fallbacks or route jobs back to a queue per contract.

## 8. When In-Process Retries Are Not Enough: Transactional Outbox and Workers

If an event reflects a **committed order** and must send an email/webhook **without getting lost**, bounded retries right inside `@TransactionalEventListener(AFTER_COMMIT)` are **not enough**. The process can crash between commit and send, or between attempts, losing the event from RAM.

A more durable design:

```text
Transaction T1:
   INSERT orders(...)
   INSERT outbox_events(
       event_id, aggregate_id, event_type, payload,
       status='PENDING', attempts=0, next_attempt_at=NOW()
   )
   COMMIT

Worker:
   select eligible outbox_events and claim safely
      |
      +-- attempt 1 -> failure -> status=RETRYING,
      |                        attempts=1,
      |                        next_attempt_at=NOW()+backoff
      |
      +-- attempt 2 -> success -> status=SENT
      |
      +-- attempts exhausted -> status=DEAD_LETTER,
                                 last_error=...
```

Benefits:

- Events are persisted **in the same transaction** as business changes.
- Workers can recover after restarts based on `status`/`next_attempt_at` and retry schedules.
- Retries do not pin HTTP request threads waiting on backoff.
- You can measure backlog, retry lag, event age, and dead-letters.
- You can explicitly bound attempts, deadlines, concurrency, and rate limits.

What an outbox **does not automatically guarantee**:

- Does not guarantee downstream receives the event **strictly once**. Sending successfully and crashing before marking `SENT` can cause resends. Consumers still need idempotency.
- Does not automatically handle ordering across multiple aggregates or partitions. If per-aggregate ordering is needed, define an explicit partitioning/ordering strategy.
- Does not automatically resolve permanent business errors; you need dead-letters, investigation workflows, and controlled replay capabilities.
- Does not come free of DB write cost; in exchange, you gain recoverability and decouple I/O time from requests.

### Minimum Worker Rules

1. **Claim atomically** so two workers do not process one event concurrently when the architecture forbids it; use DB-appropriate locking/leases.
2. Record `attempts` consistently at the start or end of each attempt; define it clearly so counts do not drift on crashes.
3. Advance `next_attempt_at` with backoff and jitter capped at a max delay; avoid tight loops when the DB/downstream fails.
4. After the final attempt, transition to `DEAD_LETTER` or `FAILED_PERMANENT`; never silently delete rows.
5. Record `last_error_type`, a secret-scrubbed message, correlation ID, and timestamp for investigation.
6. Use a stable `eventId` and idempotent consumers when redelivering.
7. If an operator wants to replay, define whether replay resets attempts, creates a new event, or simply creates **a new delivery attempt** for the same logical event.

## 9. Choosing Backoff and Total Budget by SLA

Calculate **total time**, not just attempt counts.

Suppose inside a request:

- `maxAttempts = 3`.
- Each downstream call has a max timeout of **500 ms**.
- Delay after first failure is **100 ms**.
- Delay after second failure is **200 ms**.

Worst-case for just the retry mechanics alone approaches:

```text
3 × 500 ms + 100 ms + 200 ms = 1,800 ms
```

This excludes database, controller, framework overhead, and scheduler jitter. If the HTTP endpoint's SLO is **p95 under 300 ms**, this synchronous retry policy is **unsuitable** for the request path. Reduce the attempt budget, cap the deadline, or offload non-mandatory work to a durable worker.

When processed in a post-commit queue, the budget can be sized around the **event completion SLA** (e.g., max 10 minutes). Even with a long total deadline, each attempt still needs a timeout; a hung call without a timeout can pin a worker indefinitely and render every retry budget meaningless.

Choosing delays has no single "standard" value for every downstream. Base it on historical latency, rate limits, transient error distributions, worker count, and event priority. Never use an overly short backoff against a rate-limiting dependency.

## 10. Observability: Counting Retries Properly

In logs/metrics/traces, separate:

| Signal | Example | What to watch |
| --- | --- | --- |
| `eventId` | `evt-42` | Stable across attempts/replays |
| `eventType` | `OrderPlaced` | Bounded set for metrics |
| `consumer` | `NotificationListener` | Who handles it |
| `attempt` | 1, 2, 3 | Current invocation |
| `outcome` | SUCCESS, RETRYING, EXHAUSTED | Outcome of attempt and logical event |
| `error.category` | TRANSIENT, PERMANENT, TIMEOUT | Whether to keep retrying |
| `nextAttemptAt` | Timestamp | When to retry next |
| `elapsed` | Duration | Whether deadline/SLA is breached |
| `transactionPhase` | AFTER_COMMIT | Avoid confusing publication with commit |

An event succeeding on attempt 3 has **two attempt failures** yet **one successful logical event**. Dashboards should separate:

- `retry.attempts.total`: number of attempts.
- `retry.failures.total`: number of failed attempts.
- `event.completed.total`: number of successful logical events.
- `event.exhausted.total`: number of logical events that exhausted budget.
- `retry.delay` and `event.end_to_end_latency`: wait delays and actual completion time.

These are **application-defined suggested metric names**, not metrics emitted automatically by Spring Framework when using `@EventListener`. Spring Framework does not automatically create a separate Micrometer Observation per `@EventListener`.

**Avoid cardinality explosions:** never put `eventId`, `orderId`, ID-bearing URLs, or arbitrary exception messages into low-cardinality metric labels; keep them in logs/traces or high-cardinality attributes per security policies. Never log bearer tokens, payment details, passwords, or full personal payloads in failure records.

### Preserving the Final Exception and Root Cause

On exhaustion, do not do:

```java
throw new RuntimeException("Retry failed");
```

That discards the final error type/stack trace. Instead:

```java
throw new DeliveryExhaustedException(event.eventId(), lastFailure);
```

This is an **illustrative snippet**, requiring application-specific exception classes/variables. A constructor accepting `cause` preserves why all attempts failed for operators.

If recording the failure status itself also fails, record the secondary error **without accidentally hiding the delivery cause**. Depending on the use case, use suppressed exceptions or separate failure records. Never swallow errors when persisting durable status if doing so loses a job the system needs to recover.

## 11. Testing Bounded Retries, Not Just "Was Retried"

For a policy to be truly trustworthy, test:

| Scenario | Expectation |
| --- | --- |
| Succeeds on first try | One attempt, no sleep, no retry |
| Transient failure twice, succeeds on third | Exactly **3 attempts**, 2 backoffs, no exhaustion |
| Continuous transient failure | Stops after **3 attempts**; final exception preserves cause |
| Permanent failure | Only **1 attempt**, no retry |
| Thread interrupted during backoff | Restores interrupt flag and exits without silently continuing retries |
| Deadline expires before next attempt | Stops and records deadline exceeded outcome |
| HTTP 429 with Retry-After | Honors server hint within policy bounds |
| Concurrent retries of same logical event | Idempotency/dedup prevents duplicate side effects |
| Worker crashes between attempts | Outbox job recovers if policy requires durability |
| Listener inside transaction | Knows exact commit/rollback behavior; does not confuse logs with outcomes |
| Retries exhausted after commit | Does not claim source transaction rolled back; records separate failure state |
| Circuit breaker open | Does not create a storm of futile retry calls |

### 11.1. Unit Tests Using Fake Clock/Sleeper

For a retry utility, avoid real `Thread.sleep` when testing delays if you can extract **Sleeper/Clock** as dependencies. Use a fake sleeper recording delays and a controllable fake clock to test deadlines quickly and deterministically.

Pseudo-test:

```java
// Illustrative code: FakeSleeper, Policy, and fakeGateway are test fixtures.
fakeGateway.failTransiently(2);
policy.execute("evt-42", fakeGateway::send);

assertEquals(3, fakeGateway.attemptCount());
assertEquals(List.of(100L, 200L), fakeSleeper.delays());
```

The snippet above is **not a standalone test**; it expresses the test intent for the policy. Never use `Thread.sleep(1000)` to "wait for retries to finish" and assert an arbitrary state.

### 11.2. Spring Event Integration Tests

With `AnnotationConfigApplicationContext` or `@SpringBootTest`:

1. Register the real listener and retried service through a Spring proxy.
2. Publish the event once and verify the **attempt count** using a fake gateway with a counter.
3. Verify `@Recover` is invoked right upon exhaustion and errors are classified properly.
4. When `@TransactionalEventListener` is involved, provide a real transaction manager and test commit/rollback separately.
5. With `@Async`, use `CountDownLatch`, `CompletableFuture`, or a test executor to await real completion.
6. When using `@RecordApplicationEvents`, remember the recorder **proves the event was published**, not that listener retries finished.

A test fake gateway can intentionally throw transient errors twice and then succeed, yet you must assert the listener's side effect actually ran **once from a business standpoint**, not merely count retry calls.

### 11.3. Load/Chaos Testing Before Production

During load testing, measure request p95/p99, throughput, queue depth, error rates, and recovery speed after outages. A system with `maxAttempts=3` and a large queue can still accumulate massive work backlogs.

Simulate scenarios:

- Gateway returns 503 continuously for 5 minutes, then recovers.
- DB deadlocks/serialization conflicts across multiple concurrent transactions.
- Process killed between successful send and updating outbox status.
- Worker restarts, leases expire, jobs are reclaimed.
- 429 responses with `Retry-After` varying under load.
- Consumers intentionally reprocessing the same `eventId` to confirm idempotency.

Observe both **correctness and recovery speed**, not merely whether the system still returns HTTP 200.

## 12. Common Anti-Patterns

**1. A `while(true)` loop inside `@EventListener`.**  
A long-failing downstream can pin requests/workers forever. Always enforce `maxAttempts`, deadlines, and failure policies.

**2. Retrying every exception.**  
Repeating permanent validation errors does not heal anything; it only adds load, pollutes logs, and hides bugs.

**3. Saying "retry 3 times" without specifying total vs. after first attempt.**  
In Spring Retry 2.x `maxAttempts=3` means 3 total; in Spring Framework 7 core `maxRetries=3` means up to 3 retries after the first call. Read the exact API/version.

**4. Catching, logging, and returning.**  
For mandatory business operations, the caller may think it succeeded and commit the transaction; propagate or persist a clearly defined failure state.

**5. Calling a `@Retryable` method via `this` in the same class.**  
Self-invocation can bypass the AOP proxy, so the policy never runs. Use an injected Spring-managed service or proper interceptor structure.

**6. Retrying SQL inside a transaction already marked rollback-only.**  
A successful retry inside a broken transaction will not commit. Retry a fresh transaction after rollback when needed.

**7. Treating `@Async` as a durable queue.**  
In-RAM task queues can be lost on process death. If guaranteed event delivery is required, use a durable outbox/broker.

**8. Backoff without jitter when many consumers fail together.**  
Attempts can synchronize, causing retry storms downstream. Use jitter, concurrency limits, and appropriate circuit breakers.

**9. No per-attempt timeout.**  
One infinitely hung call defeats every `maxAttempts` setting. Set timeouts on I/O clients plus a global deadline.

**10. Generating a new eventId on each attempt.**  
Breaks idempotency so consumers fail to recognize the same logical operation. Keep one ID throughout.

**11. Expecting rollback when an `AFTER_COMMIT` listener fails.**  
The source transaction already committed. Manage post-commit event processing states independently.

**12. Assuming an exception in logs means delivery was retried.**  
Logging is not a scheduler/retry policy. Measure attempts, next retry times, exhaustion, and final outcomes.

**13. Lacking a dead-letter/recovery procedure.**  
Exhausting budget with nobody handling it turns a temporary glitch into prolonged event loss. Set up dashboards, alerts, runbooks, and controlled replays.

**14. Retrying non-idempotent side effects.**  
Timeouts can occur after downstream already executed; retries can create duplicate orders/transfers/emails. Verify protocols and idempotency keys first.

## 13. Bounded Retry Design Checklist

Before shipping a policy to production, answer these questions:

1. **Target:** Which operation is retried? The whole listener, one HTTP call, or the entire use case/transaction?
2. **Error classification:** Which exceptions/status codes are transient? Which stop immediately?
3. **Attempts:** Where is the total invocation cap, including the first call, defined?
4. **Backoff:** Initial delay, multiplier, max delay, jitter, `Retry-After`?
5. **Deadline:** Per-attempt timeout and total operation budget?
6. **Transaction:** Is the retry inside a rollback-only transaction? Does the callback run before or after commit?
7. **Threading:** Does sleeping block an HTTP request or executor worker?
8. **Idempotency:** If an earlier attempt succeeded yet the response was lost, is retrying safe?
9. **Durability:** If the process dies between attempts, does the event remain somewhere recoverable?
10. **Exhaustion:** Is the error thrown, saved as failure state, dead-lettered, or deliberately ignored?
11. **Observability:** Are `eventId`, attempt count, outcome, backoff delay, retry lag, and alerts present?
12. **Capacity:** When an entire downstream fails, how much does load multiply; how do queues, circuit breakers, and bulkheads behave?
13. **Testing:** Are permanent errors, retry exhaustion, interrupts, rollbacks, async, crash/replay, and duplicates tested?

If the answer to **durability** is "no", explicitly document that current bounded retries only guard against transient failures **while the process stays alive**. If critical events must not be lost, use a more reliable persistence layer and worker.

## 14. Self-Check Questions

**1. Does a default `@EventListener` automatically retry when a handler throws an exception?**  
No. With the default synchronous multicaster, the exception can propagate to the publisher and stop the rest of the multicast.

**2. How many total calls does `maxAttempts=3` in Spring Retry 2.x correspond to?**  
At most **three calls in total**, including the initial invocation and two retries.

**3. Why must transient and permanent errors be distinguished?**  
Because retrying permanent errors cannot recover on its own, only adding load and delaying reporting of the real failure.

**4. Why can retrying inside `@Transactional` still cause a rollback even when the last attempt succeeds?**  
Because a failure on an earlier attempt may have marked the current transaction rollback-only; design appropriate retry/transaction boundaries.

**5. Why can't `@TransactionalEventListener(AFTER_COMMIT)` with retries roll back the original order?**  
Because the source transaction already committed before the listener ran in that phase. Failure handling must use separate state or transactions.

**6. Does `@Async` make retries durable across restarts?**  
No. An in-memory executor queue does not guarantee persisting work across process crashes.

**7. If a request reaches a gateway and succeeds yet the response is lost, what can a retry cause?**  
It can create a duplicate side effect. You need a stable idempotency key and duplicate-handling contract from the gateway/consumer.

**8. When all three attempts fail, should you log the error and return success?**  
Only when it is a best-effort side effect and the contract permits it. For mandatory work, propagate or persist a durable failure state.

**9. When a downstream fails broadly, why is `maxAttempts` alone not enough?**  
Because many callers still multiply attempts, causing a retry storm; you need backoff/jitter, timeouts, rate limits, concurrency limits, and circuit breakers.

## 15. Official References

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster (synchronous, error propagation)](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Retry 2.x — @Retryable API (maxAttempts)](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Retry — @Recover API](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Recover.html)
- [Spring Framework 7 — Core Resilience Features (maxRetries differs from maxAttempts)](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)


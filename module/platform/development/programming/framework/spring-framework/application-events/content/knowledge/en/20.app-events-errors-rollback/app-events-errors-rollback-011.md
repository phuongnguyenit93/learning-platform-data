# Distinguishing Business Errors from Infrastructure Errors When Handling Spring Application Events

## 1. Why Must You Distinguish These Two Error Categories?

When a service calls `ApplicationEventPublisher.publishEvent(event)`, multiple components may be involved: domain code checking rules, a repository writing data, `ApplicationEventMulticaster` selecting listeners, listeners calling email/APIs/brokers, and a transaction manager committing or rolling back. If you only log "event failed" or catch every `Exception` and retry, the system easily turns a command **disallowed by business rules** into futile retries, or conversely treats a temporary connection outage as a permanent business rejection.

A **business/domain error** is an outcome that fails to satisfy a rule, state, or policy of the business domain. Examples: insufficient balance, order already paid, cannot cancel a shipped order, allowed limit exceeded. This outcome is usually **predictable from the command and valid domain state**.

An **infrastructure/technical error** is the system's inability to perform a required operation due to technical resources or mechanisms: unreachable database, HTTP timeout, temporarily down broker, exhausted pool, task rejected by executor, filesystem error, or invalid service configuration.

This distinction **is not based solely on exception class names**. A DB unique constraint error can express "order already exists" (a business rule) or signal a race condition/infrastructure issue depending on context; an HTTP 409 can be a domain conflict or a sync error in another system. Errors must be placed in **the context of the operation, aggregate, transaction, and integration contract**.

| Criterion | Business error | Infrastructure error |
| --- | --- | --- |
| Primary cause | Command violates an invariant/policy or disallowed state | Dependency, network, storage, scheduling, or configuration |
| Examples | `OrderAlreadyPaid`, `InsufficientBalance` | `DataAccessResourceFailureException`, timeout, broker unavailable |
| Retrying with same input and state | Usually **does not help** | Can help if error is transient and operation is safe |
| Typical action | Return clear rejection result; guide input/state change | Bounded retry, fallback, circuit breaker, alerting |
| Does it roll back? | **Depends on state to persist and transaction policy** | Usually rolls back uncommitted work; does not undo already occurred side effects |
| Operational observability | Business outcome/denial rate; not an incident by default | Error rate, dependency health, timeouts, retries, DLQ |
| Can it emit a domain event? | Yes, if **being rejected** is a business fact to record | Usually emits technical failure signals/telemetry; do not fake domain facts |

The goal is not "every business exception commits" or "every technical exception rolls back," but rather that **each error category has its own meaning, transaction boundary, and handling policy**.

## 2. Three Layers to Separate: Errors, Business Outcomes, and Domain Events

A domain rule can be represented in two reasonable ways:

**Approach A — reject with a typed result**: `PaymentResult.Rejected("INSUFFICIENT_FUNDS")`. Useful when rejection is a normal business case and callers need to present the reason. Throwing an exception is not mandatory for every rejection decision.

**Approach B — reject with a specifically typed exception**: `BusinessRuleViolationException("ORDER_ALREADY_PAID")`. Useful when execution cannot continue and the calling layer needs rollback/response generation via exception mapping.

Conversely, `PaymentGatewayUnavailableException` or `DatabaseUnavailableException` represents a dependency outage and should not be translated into "customer has insufficient funds." An infrastructure exception may carry technical causes internally (`cause`), yet must never expose stack traces, connection strings, or dependency secrets to end users.

A **domain event** such as `PaymentAccepted` or `OrderRejected` is a fact confirmed by the model. Do not create `PaymentAccepted` merely because `publishEvent(...)` was called; events need **accurate semantics** regarding transaction timing and durability. For example, `OrderRecorded` published inside a transaction means recording was requested, **not proof that commit succeeded**.

A sound design distinguishes:

```text
Command: "Pay order X"
    |
    +-- domain check -> "Rejected: ORDER_ALREADY_PAID"
    |                   (do not retry mechanically)
    |
    +-- domain accepts -> save in transaction
            |
            +-- DB error before commit -> TechnicalFailure
            |                             (rollback, consider retry)
            |
            +-- publish in-process event
                    |
                    +-- sync listener fails -> may propagate exception
                    |                          to publisher, rollback
                    |
                    +-- commit succeeded
                            |
                            +-- AFTER_COMMIT listener fails
                                  -> **commit cannot be undone**
                                  -> retry/outbox/compensation if needed
```

## 3. How Are Errors Propagated in Spring Application Events?

### 3.1. Synchronous `@EventListener` (Default)

Spring Framework by default uses `SimpleApplicationEventMulticaster` to invoke listeners synchronously on the publisher thread. When a synchronous `@EventListener` throws an unchecked exception, the exception can propagate back through `publishEvent(...)` into the service. If the publisher is inside a transaction and the exception escapes the transaction boundary, the transaction manager may roll back.

For example, a synchronous listener calls an email API, the API times out, and the listener throws `RuntimeException`: database updates just performed in the same transaction may roll back, **even though sending email is a dependency outside the database transaction**.

More dangerously, if an earlier listener already sent an email successfully and a later listener fails, rolling back the database transaction does not recall the sent email. In-process Spring events do not turn multiple side effects into an atomic distributed transaction.

### 3.2. Phase-Bound `@TransactionalEventListener`

`@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)` is invoked before commit; an unchecked exception from that logic can prevent the commit from happening.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` runs after a successful commit. A listener failure at this point **cannot roll back the already committed transaction**. For this annotated listener, `AFTER_COMMIT` is processed within the `afterCompletion` sequence; do not assume the exception always propagates back to the publisher like an ordinary synchronous `@EventListener`.

`AFTER_ROLLBACK` runs after rollback; errors there cannot turn a rollback into a commit. `AFTER_COMPLETION` runs after the transaction finishes and is suitable for cleanup/metrics, though it does not by itself distinguish outcomes.

By default, `@TransactionalEventListener` **does not run when no transaction is active**, unless `fallbackExecution = true` is enabled and fallback semantics are accepted.

### 3.3. Asynchronous Listeners

With `@Async` or a multicaster using an executor, listeners can run on another thread. Exceptions raised afterward usually **do not return to the `publishEvent(...)` call**. You need error-observability channels, `AsyncUncaughtExceptionHandler` (for `void` `@Async` methods), futures/completion handles if present, retry policies, or queues/outboxes per requirements.

For imperative transactions, transaction context is usually bound to the thread. Do not assume an async worker shares `TransactionSynchronizationManager` or `SecurityContextHolder` with the publisher. Transactional listeners must register synchronizations within an appropriate transaction context; publishing an event from a thread without a transaction can cause transactional listeners to be skipped.

### 3.4. Event Multicaster `ErrorHandler`

`SimpleApplicationEventMulticaster#setErrorHandler(...)` can change how synchronous listener exceptions are handled; for example, if a handler logs the error and **swallows the exception**, the publisher can continue and the transaction may not roll back. Therefore, **rollback depends not only on exception type, but also on where the exception is caught and the multicaster policy**. Do not configure swallow-all just to reduce log errors if it hides failures with business impact.

## 4. Runnable Java 17 Example: Three Outcomes Inside a Transaction

This example uses **Spring Framework 6.2.8 + H2 + TransactionTemplate**, without Spring Boot. It simulates:

1. `OK-1`: valid order, synchronous listener succeeds; transaction commits.
2. `BAD-1`: invalid amount, service throws a **business exception** before writing DB or publishing events; transaction rolls back and no corresponding event is emitted.
3. `NET-1`: valid domain, inserted inside transaction, yet synchronous listener simulates a notification gateway failure; **infrastructure exception** propagates back to the transaction template and the DB rolls back.

An `AFTER_COMMIT` listener and an `AFTER_ROLLBACK` listener observe the outcome. `@Order` is used to **register transaction callbacks before running the listener that may throw**, avoiding reliance on method discovery order.

### 4.1. Maven Structure

```text
event-error-classification/
├── pom.xml
└── src/main/java/demo/EventErrorDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>event-error-classification</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
                    <mainClass>demo.EventErrorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/EventErrorDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class EventErrorDemo {

    // Event reflects a change being processed inside the transaction;
    // by itself it DOES NOT guarantee the database has committed.
    public record OrderRecorded(String orderId) {}

    public static final class BusinessViolation extends RuntimeException {
        public BusinessViolation(String code) {
            super(code);
        }
    }

    public static final class InfrastructureFailure extends RuntimeException {
        public InfrastructureFailure(String code) {
            super(code);
        }
    }

    public static final class OrderService {
        private final TransactionTemplate transactions;
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(TransactionTemplate transactions,
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            this.transactions = transactions;
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        public void record(String orderId, long amount) {
            transactions.executeWithoutResult(status -> {
                if (amount <= 0) {
                    throw new BusinessViolation("invalid-amount");
                }

                jdbc.update(
                        "insert into orders(id, amount) values (?, ?)",
                        orderId, amount);
                System.out.println("service: inserted " + orderId);

                // Synchronous listener runs on the publisher thread.
                publisher.publishEvent(new OrderRecorded(orderId));
                System.out.println("service: published " + orderId);
            });
        }
    }

    public static final class EventListeners {

        // Register synchronization earlier than a listener that might throw.
        @Order(0)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderRecorded event) {
            System.out.println("tx: committed " + event.orderId());
        }

        @Order(1)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderRecorded event) {
            System.out.println("tx: rolled-back " + event.orderId());
        }

        @Order(10)
        @EventListener
        public void callGateway(OrderRecorded event) {
            // Failure simulation only: DO NOT make real network calls.
            if ("NET-1".equals(event.orderId())) {
                System.out.println("listener: gateway-failed NET-1");
                throw new InfrastructureFailure("gateway-unavailable");
            }
            System.out.println("listener: gateway-ok " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:error_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource source) {
            return new DataSourceTransactionManager(source);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        OrderService orderService(TransactionTemplate template,
                JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
            return new OrderService(template, jdbc, publisher);
        }

        @Bean
        EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    private static boolean exists(JdbcTemplate jdbc, String orderId) {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class, orderId);
        return count != null && count > 0;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("create table orders (" +
                    "id varchar(64) primary key, amount bigint not null)");

            OrderService service = context.getBean(OrderService.class);

            System.out.println("=== SUCCESS ===");
            service.record("OK-1", 100);
            System.out.println("db: OK-1=" + exists(jdbc, "OK-1"));

            System.out.println("=== BUSINESS ERROR ===");
            try {
                service.record("BAD-1", -1);
            } catch (BusinessViolation ex) {
                System.out.println("main: business=" + ex.getMessage());
            }
            System.out.println("db: BAD-1=" + exists(jdbc, "BAD-1"));

            System.out.println("=== INFRASTRUCTURE ERROR ===");
            try {
                service.record("NET-1", 100);
            } catch (InfrastructureFailure ex) {
                System.out.println("main: infrastructure=" + ex.getMessage());
            }
            System.out.println("db: NET-1=" + exists(jdbc, "NET-1"));
        }
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Application `System.out.println(...)` output (excluding Maven logs):

```text
=== SUCCESS ===
service: inserted OK-1
listener: gateway-ok OK-1
service: published OK-1
tx: committed OK-1
db: OK-1=true
=== BUSINESS ERROR ===
main: business=invalid-amount
db: BAD-1=false
=== INFRASTRUCTURE ERROR ===
service: inserted NET-1
listener: gateway-failed NET-1
tx: rolled-back NET-1
main: infrastructure=gateway-unavailable
db: NET-1=false
```

### 4.2. Why Does the Output Have This Order?

- `@Configuration(proxyBeanMethods = false)` creates a standard Spring context; `JdbcTemplate` and `DataSourceTransactionManager` use in-memory H2. The `orders` table is created outside test transactions.
- For `OK-1`, data is inserted inside the transaction; the synchronous `@EventListener` runs immediately and prints `gateway-ok`; the service prints `published`; after `TransactionTemplate`'s callback returns, the database commits, and `AFTER_COMMIT` prints `committed`.
- For `BAD-1`, the amount check happens **before insert and publish**. `BusinessViolation` (unchecked) causes `TransactionTemplate` to roll back. Because no event was published, there is no after-rollback listener for `BAD-1` — even though the transaction still rolled back.
- For `NET-1`, insert was called but not yet committed. Transactional listeners with `@Order(0)`/`@Order(1)` register callbacks before the `@Order(10)` listener. The gateway listener simulates an infrastructure failure, throwing `InfrastructureFailure`; the `publishEvent` call does not return normally, so `service: published NET-1` never appears. `TransactionTemplate` rolls back, the `AFTER_ROLLBACK` callback prints its message, and the exception returns to `main`. The query outside the transaction confirms `NET-1` is not in the DB.
- The `db: ...` lines use a separate connection/outside the finished transaction, so they reflect actual commit or rollback state.
- The demo has no real email, HTTP request, or message broker. Therefore, **the absence of real side effects** does not prove Spring will recall already sent emails or HTTP requests in a real system.

### 4.3. Purpose of the Simulated Failure

In production, infrastructure errors arise from a `GatewayClient` with causes like `IOException`, timeouts, or specific HTTP failures. The example code uses `"NET-1"` to produce a reproducible failure branch—**not as a business rule** and not as a recommendation to drive gateway behavior via IDs.

Although both are `RuntimeException`, `BusinessViolation` and `InfrastructureFailure` carry different meanings, leading to different response, retry, and monitoring policies. Both can cause rollback in the example, so **the rollback result is not a reliable signal to tell error categories apart**.

## 5. Rollback in Spring: Exception Semantics and Boundaries

In declarative transactions with `@Transactional`, the default rules are typically:

- `RuntimeException` or `Error` escaping a method managed by the transaction interceptor → **rollback**.
- Checked `Exception` → **no rollback** by default, unless `rollbackFor` or another global rollback rule is configured.
- `noRollbackFor` can be used for clearly defined exception types, yet **should not** be used to hide errors that leave data inconsistent.
- Spring Framework 6.2 allows changing the global default, such as configuring rollback for all exceptions. Inspect the actual configuration before asserting a checked exception will commit.

An **illustrative** policy example:

```java
@Transactional(
    rollbackFor = ExternalServiceFailure.class,
    noRollbackFor = BusinessRejection.class
)
public void process(Command command) {
    // Only use noRollbackFor when the persisted state remains consistent.
}
```

The snippet above is not a standalone program; `ExternalServiceFailure`, `BusinessRejection`, and `Command` must be defined accordingly. `noRollbackFor` can be useful when you want to **persist a rejection result** (such as a rejection audit) in the same transaction, but you cannot half-update state on failure and "commit because it is a business error."

Proxy semantics note: `@Transactional` is typically applied via a Spring proxy. An internal `this.process()` call does not go through the proxy and may not open a transaction as expected. Inspect transaction boundaries, propagation, rollback-only flags, and the final exception actually escaping, rather than reading annotations alone.

In the runnable example, `TransactionTemplate` explicitly creates transactions. Throwing an unchecked exception from the callback triggers rollback. It does not demonstrate `@Transactional` proxy checked-exception rules; both mechanisms share Spring's transaction manager, yet their APIs and exception-catching policies must be distinguished.

## 6. Error Matrix by Event-Publishing Stage

| Failure point | Possible DB state | Event/listener | Resolution approach |
| --- | --- | --- | --- |
| Validation/domain rejects **before publish** | Not written or rolled back per policy | Do not publish success event | Return business result; do not retry mechanically |
| Repository fails before commit | Transaction can roll back | Previously published events may have caused side effects | Fix ordering or use after-commit/outbox; classify error |
| Synchronous `@EventListener` throws unchecked in transaction | Can roll back if exception escapes transaction boundary | Earlier listeners may already have run | Avoid non-rollbackable I/O on synchronous path |
| `@TransactionalEventListener(BEFORE_COMMIT)` throws | Can prevent commit | Does not reach `AFTER_COMMIT` | Fix error/enforce invariant; avoid permanent side effects |
| `@TransactionalEventListener(AFTER_COMMIT)` fails | **Committed**, cannot roll back that transaction | Delivery/side effect may fail | Retry/outbox/compensation, track independently |
| `@TransactionalEventListener(AFTER_ROLLBACK)` fails | **Rolled back** | Cleanup/compensation may fail | Monitor and use dedicated retry mechanism |
| `@Async` listener fails | Publisher may already have finished/committed | Exception does not automatically return to publisher | Async error handler, future, queue/retry |
| Broker relay fails after DB commit | DB data committed | Message may not have reached consumer | Durable outbox, retry + idempotency |
| Consumer processes duplicate event | Source DB is not undone | Side effects may repeat | Event ID, unique constraint/dedup |

**Never generalize "the listener failed so the DB rolled back" to every case.** The outcome depends on whether the listener ran during or after the transaction, synchronously or asynchronously, whether the exception escaped or was swallowed by an error handler, propagation, and rollback configuration.

## 7. Designing Clear Exception Classification

Have an **error taxonomy** at the application layer rather than catching `Exception` and returning a generic "invalid request."

Suggested example:

```java
// Design snippet, not a standalone program.
sealed interface AppFailure
        permits BusinessFailure, InfrastructureFailure {}

record BusinessFailure(
        String code, String safeMessage) implements AppFailure {}

record InfrastructureFailure(
        String code, boolean retryable, String traceId)
        implements AppFailure {}
```

Principles:

1. **Stable error codes**: `ORDER_ALREADY_PAID`, `INVALID_AMOUNT`, `PAYMENT_GATEWAY_TIMEOUT`. Never use raw exception class names as a client API contract.
2. **Safe messages**: users get actionable details; internal logs can retain `cause`, yet strip tokens, passwords, connection strings, and PII.
3. **Do not lose root causes**: when translating `SocketTimeoutException` to `GatewayUnavailableException`, retain `cause` for investigation rather than overwriting meaning with a generic `IllegalArgumentException`.
4. **Retryability is per-operation**: a technical timeout does not mean the external party never processed the request. Require an idempotency key or status query before retrying.
5. **Clear classification ownership**: domain modules return business codes; infrastructure adapters translate HTTP/JDBC/broker errors; application services enforce use-case policies.
6. **Never turn technical errors into domain decisions**: e.g., "cannot connect to the account system" does not prove the customer has "insufficient balance."

At the HTTP boundary, a business error may map to 400/409/422 depending on protocol and semantics; an infrastructure error may become 503 or 500 with an appropriate `Retry-After`. **There is no single HTTP mapping** for every domain, and raw exceptions/stack traces must not be exposed to clients. In message consumers, decide ack/retry/DLQ based on error codes, retry budgets, and idempotency.

## 8. Retries: Infrastructure Errors Do Not Mean Infinite Retries

Some infrastructure errors are **transient** (timeouts, 503, deadlocks, queue overload). Some are **permanent or require intervention** (wrong credentials, unapplied schema migrations, incompatible payloads, missing topics, permission denied). Retrying forever only increases load and hides the root cause.

A safe retry policy should define:

- **Is it truly retryable?** Based on dependency contracts, HTTP status/error codes, DB state, and queue health.
- **Is the operation idempotent?** Retrying payment charges or emails can repeat side effects; use stable idempotency keys/event IDs and deduplication.
- **Budget**: max attempts, deadline, exponential backoff, and jitter.
- **Circuit breaker/bulkhead**: avoid overwhelming failing dependencies; avoid holding transactions open across long sleeps/retries.
- **Fallback**: use only when the alternative result still satisfies business requirements. Never report "payment succeeded" simply because the payment gateway could not be reached.
- **Dead-letter/parking**: store failed events for investigation and controlled replay without losing data across crashes.
- **Observability**: separate retry counts, recoverable errors, permanent errors, and pending backlogs.
- **Event ordering**: retries can let later events overtake earlier ones unless aggregate/partition ordering is preserved.

For business errors like `ORDER_ALREADY_PAID`, resending **the same command** rarely adds value. You can display the current result or ask for corrected input. However, if a domain policy depends on external state that changes over time, retrying **after conditions genuinely change** can be valid; that is a new command under new conditions, not mechanically retrying the same request.

### Timeout Means "Unknown," Not "Not Done"

If an HTTP request to a payment gateway times out, the gateway **may have received and executed it**. Simply retrying `charge()` can charge twice. You need an idempotency key and a status-lookup API before resending, or a formal reconciliation process. A technical failure does not let you conclude the business operation failed in reality.

## 9. When Should Listeners Be Decoupled From Transactions?

In the example, `@EventListener` sends notifications inside the DB transaction. This is an **intentional anti-pattern for illustration**: if the dependency is flaky, recording orders can roll back even though domain state is valid. Conversely, if the gateway already sent the email and commit later fails, the email is not automatically recalled.

A sensible decoupled design:

```text
@Transactional application service
  |
  +-- domain validate
  +-- update aggregate
  +-- publish domain event inside transaction
         |
         +-- @TransactionalEventListener(AFTER_COMMIT)
                -> start task after DB has committed
                -> call service/worker with retry, idempotency
```

Illustrative annotation example:

```java
@Component
class ReceiptListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderRecorded event) {
        // Runs only after DB commit.
        // An error here DOES NOT undo the transaction that just committed.
    }
}
```

Non-standalone snippet: requires annotation imports, `OrderRecorded` definition, and bean setup. An after-commit listener needing **additional DB writes** may have to open a new transaction, such as on another service using `@Transactional(propagation = Propagation.REQUIRES_NEW)` through a Spring proxy; old transaction resources may still be bound to the thread with no subsequent commit.

**Limitation:** `AFTER_COMMIT` only picks the right *processing timing*; it does not guarantee durable delivery. If the process dies after DB commit before the callback runs, in-memory events can be lost. It is not equivalent to an outbox.

### Transactional Outbox for Tasks Requiring Crash Recovery

```text
BEGIN TRANSACTION
  UPDATE orders SET status = 'PAID' WHERE id = ?
  INSERT INTO outbox(event_id, aggregate_id, type, payload, status)
COMMIT

Relay/worker:
  read undelivered outbox
  -> publish to broker / call integration
  -> confirm success
  -> update status, retry per policy
```

State and outbox commit or roll back **in the same DB transaction**. After a crash, workers can resume reading records. However, if the broker received a message before the worker marked it delivered, it will resend; downstream **must be idempotent**. Never claim exactly-once side effects solely because an outbox exists.

For multi-step cross-service workflows, a local DB rollback also cannot roll back an already committed remote transaction. Consider explicit **Sagas and compensating actions** (such as refunding after a misplaced charge), rather than expecting Spring transactions to span across systems.

## 10. Semantically Accurate Logging and Monitoring

If you log every `BusinessViolation` as an infrastructure ERROR, dashboards and alerts become noisy. Conversely, if you turn timeouts into `INSUFFICIENT_FUNDS`, you lose system-outage signals and show users misleading messages.

Minimum recommended fields:

| Observability field | Suggestion |
| --- | --- |
| `correlationId` / `traceId` | Link command → publish → listener → downstream; avoid direct PII |
| `eventId`, `eventType` | Deduplication, tracking timing and event kind |
| `errorCategory` | `BUSINESS` or `INFRASTRUCTURE`; optionally `UNKNOWN` for investigation |
| `errorCode` | Stable code; never copy raw exception messages containing secrets |
| `phase` | `PUBLISH`, `BEFORE_COMMIT`, `AFTER_COMMIT`, `ASYNC_CONSUME` |
| `transactionOutcome` | `COMMITTED`, `ROLLED_BACK`, `UNKNOWN`; record only once determined |
| `retryCount` / `nextRetryAt` | Useful for workers/relays; never use as high-cardinality tags |

Predictable business errors are usually business outcomes; log levels can be INFO/WARN per product needs rather than becoming incidents by default. Infrastructure errors need metrics/error rates and SLO-based alerts. Avoid putting emails, tokens, OTP codes, card numbers, or sensitive request bodies into events, logs, trace baggage, or DLQs. **Do not log entire event objects if schemas have not been reviewed.**

In async processing, trace context is not automatically preserved across threads: propagate needed context through supported mechanisms rather than arbitrarily copying whole `ThreadLocal`/security contexts.

## 11. Testing to Prove the Policy

A worthwhile test suite for application events:

1. **Business validation**: bad input → rejects with right code, emits no success event, persists no invalid state.
2. **Transaction rollback**: synchronous listener throws unchecked before commit → inserted uncommitted data rolls back.
3. **After commit**: listener error after commit does not roll back the completed transaction; alert/retry happens separately.
4. **After rollback**: `AFTER_ROLLBACK` listener runs only for events published in that transaction when the transaction actually rolls back.
5. **Exception mapping**: gateway errors are classified as `INFRASTRUCTURE` without leaking raw tokens/SQL in responses.
6. **ErrorHandler**: if multicaster is non-default, explicitly assert whether exceptions propagate or are handled by the handler.
7. **Async**: worker task errors enter error channels/queues rather than vanishing; publishers must not treat async results as completed.
8. **Outbox**: state and outbox commit/roll back together, recover via relay after crash, and duplicate delivery causes no duplicate side effects.
9. **Retry safety**: timeout after remote execution causes no double charge thanks to idempotency keys.
10. **Persisted business rejection**: if design requires recording rejections, test that the transaction genuinely commits a valid audit record instead of rolling everything back.
11. **Concurrent commands**: two requests updating the same aggregate need optimistic locking or proper transaction isolation; do not translate every unique constraint failure into an infrastructure error.
12. **Checked exception policy**: test `rollbackFor`/`noRollbackFor` or default rollback rules separately per project version/configuration.

### Example Test Matrix

| Case | DB expectation | Event expectation |
| --- | --- | --- |
| Valid command, simulated gateway OK | `OK-1` present | `@EventListener` runs, `AFTER_COMMIT` runs |
| Command `amount <= 0` | No `BAD-1` | Not published, no phase listeners |
| Simulated gateway error in sync listener | No `NET-1` | `AFTER_ROLLBACK` runs; caller gets technical error |
| Write outbox then roll back | No state/outbox row | No durable event to relay |
| Commit then worker notification fails | State stays committed | Outbox/pending retry record persists if properly designed |

Testing with a real database or transactional H2 reveals real commits/rollbacks; you cannot prove rollback merely by printing a `"rollback"` log in a fake repository.

## 12. Common Misconceptions

**"Business errors must always roll back"** — False. Some cases reject without mutating state; some need to persist a valid `Rejected` record. Rollback depends on desired consistency.

**"Technical errors can always be retried"** — False. Bad credentials, invalid schemas, or permission denied usually need configuration fixes. Timeouts can mean unknown outcomes requiring reconciliation.

**"Calling save means the DB definitely committed"** — False. `save` may sit inside an uncommitted transaction; flushing does not equal committing either.

**"publishEvent is a durable message broker"** — False. Default in-process Spring events are not a durable queue and do not survive crashes.

**"If a sync listener fails, all side effects automatically roll back"** — False. Local DB transactions do not recall already sent emails, HTTP requests, or messages.

**"A failing AFTER_COMMIT listener will roll back"** — False. Commit is already done; a separate retry/compensation mechanism is needed.

**"Catching exceptions and continuing is safe"** — Not necessarily. If a swallowed exception lets a transaction commit with a mandatory step missing, invariants can break.

**"Using @Async always increases reliability"** — False. Async only changes timing/threads; without a durable queue and error handling, errors are even easier to lose.

**"Returning HTTP 500 for every exception is fine"** — False. Clients need to know when to fix requests, when retrying is safe, and when to query status to avoid duplicate side effects.

## 13. Pre-Implementation Checklist

- [ ] Defined business rejection codes and valid domain states; never map technical errors arbitrarily into domain outcomes.
- [ ] Specified transaction boundaries, rollback policies, and phases for every listener.
- [ ] Confirmed which listeners run synchronously, which run async, and whether an `ErrorHandler` exists.
- [ ] Avoided calling non-rollbackable side effects inside transactions without an explicit consistency design.
- [ ] Used `AFTER_COMMIT` or outbox strictly according to timing/durability requirements; never treated them as equivalent.
- [ ] Every retry of a side-effecting operation has proper idempotency/reconciliation.
- [ ] Never retry business errors unconditionally and never retry technical errors infinitely.
- [ ] Recorded technical causes in secure internal logs; APIs return only appropriate error codes/messages.
- [ ] Attached correlation/event IDs, per-category error metrics, and SLO-based infrastructure alerts.
- [ ] Tested rollback, after-commit failures, async failures, duplicate delivery, and remote "unknown" states.
- [ ] Verified `@Transactional` proxy behavior and default rollback rules in the actual configuration.
- [ ] Across services, used outbox/Saga/compensation instead of expecting cross-system rollback.

**Conclusion:** Distinguishing business errors from infrastructure errors guides the right response: **clear rejections/guidance** for business rules, **conditional recovery/retries** for dependency failures. Yet in Spring application events, you must also consider **publish timing, synchronicity, transaction phases, propagation, and event persistence mechanisms**. Only when both dimensions are designed together can you avoid wrong rejections, unexpected rollbacks, lost events, or duplicate side effects.

## References

- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @Transactional settings / rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc 6.2.8](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [SimpleApplicationEventMulticaster Javadoc 6.2.8](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)

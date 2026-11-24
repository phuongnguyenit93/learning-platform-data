# Idempotency of Event Listeners in Spring Framework Application Events

## 1. The Problem: An Event Can Be Processed Multiple Times

A payment application publishes `PaymentCaptured` to schedule sending a receipt. When the environment involves retries, message redelivery, multiple workers, or repeated publish calls, the same event can reach a listener more than once. If every callback executes the same side effect, the system may send two emails, create two invoices, or credit loyalty points twice.

Example:

```text
PaymentCaptured(eventId="evt-pay-100")
             |
             +--> callback 1 --> schedule receipt email
             |
             +--> callback 2 --> schedule receipt email AGAIN
```

Spring Application Events **do not automatically provide exactly-once delivery or deduplication by eventId**. Calling `ApplicationEventPublisher.publishEvent(...)` simply dispatches the event to the distribution infrastructure; the framework does not know that two objects sharing the same `eventId` must be treated as a single business operation. In an application using the default multicaster, listeners normally run synchronously; with `@Async` or a multicaster executor, completion order and timing may differ. In either mode, **idempotency is a contract of the handler and business data**, not an implicit guarantee from the event bus.

**Idempotency** means that reapplying the same operation (according to a clearly defined identity criterion) **does not change the business outcome after the first successful execution**. An idempotent listener may **be invoked multiple times**, but it must not produce **unintended duplicate side effects**.

Important point: idempotency **does not mean the listener only runs once**; nor does it mean the broker delivers the message exactly once; and it does not by itself solve the case where an event is **completely lost**.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish between event replay, duplicate delivery, duplicate side effects, and another valid business action.
- Design an idempotency key based on **consumer + eventId** or an appropriate business invariant.
- Understand why checking `exists(...)` before calling `insert(...)` is unsafe under concurrent processing.
- Use a **unique constraint** and a transaction to ensure recording the marker and creating the internal side effect are atomic.
- Separate the **receipt marker** from the **transactional outbox** and from actual email/HTTP sending operations.
- Use `@TransactionalEventListener(AFTER_COMMIT)` at the right time and understand when `REQUIRES_NEW` is needed.
- Test duplicates, rollbacks, concurrency, retries, and "crash windows".
- Recognize the limitation: **idempotency does not replace durability**, end-to-end exactly-once, or recovery mechanisms.

This topic belongs to the **Reliability** group of Spring Framework Application Events. The focus is on building safe handlers when **the same event is redelivered**.

## 2. When Can the Same Event Appear Again?

Very realistic scenarios include:

1. **Calling publish twice in code.** Two controller/service layers both publish `OrderAccepted`, or a loop calls `publishEvent` repeatedly.
2. **Business method retries.** AOP retries, HTTP client retries, schedulers, or users resubmitting a request.
3. **Broker message redelivery.** A consumer finishes processing but crashes before ack/committing the offset; the broker may redeliver.
4. **Outbox poller re-execution.** A worker sends an event and crashes before marking the outbox row as processed.
5. **Two competing workers.** The same work is claimed due to insufficient locking/distributed coordination.
6. **History replay.** An event store or read-model recovery tool replays old events.
7. **Multiple listener registrations.** An event may reach multiple handlers or two instances serving the same function; idempotency must define **which effect needs protection**.
8. **External timeouts.** Email/HTTP was already processed, but the client never received the response; a retry can repeat the effect.

You must define what an **event occurrence** is. If `PaymentCaptured(eventId="evt-100")` is redelivered, it is normally the **same occurrence** with the same preserved `eventId`. If there are two separate payments for the same order, they may share `orderId` but have **different eventId/paymentId values**, and both are valid.

Do not use an overly broad filter like "this order has already had any event" to block distinct business occurrences.

## 3. Three Concepts: Invocation, Occurrence, and Effect

| Concept | Question | Example |
| --- | --- | --- |
| Listener invocation | How many times was the listener method called? | `onCaptured` receives 3 callbacks |
| Event occurrence | Do those callbacks belong to the same business event? | All 3 carry `eventId="evt-100"` |
| Business effect | How many actual outcomes were created? | Only 1 receipt-sending job in the outbox |

An idempotent listener **does not need to hide the invocation count**. Better yet, explicitly observe `attempts`, `accepted`, and `duplicatesSkipped`. When three callbacks result in one outbox row, we can prove the idempotent effect under the chosen key.

### Not Equivalent to Exactly-Once

You can achieve **effect-once for a specific invariant** (for example, "one outbox row per payment event and consumer") even when the event is delivered at least once. However, you should not claim "system-wide exactly-once" without proving the transaction, broker, external APIs, replicas, and crash scenarios.

Deduplication does not guarantee **every event reaches the listener at least once**. An event lost after commit but before the callback runs cannot be rescued solely by a `processed_events` table.

## 4. Choosing the Right Idempotency Key

### 4.1. eventId Must Remain Stable Across Retries

Payload record:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String correlationId
) {}
```

The fields serve different roles:

- `eventId`: identifies **one occurrence** of the event.
- `paymentId`: business identifier for a single payment.
- `correlationId`: links steps belonging to the same request/workflow; **not a default deduplication key**.
- If `causationId` is present, it describes the direct parent event, not a unique identifier for every child event.

When retrying the **same occurrence**, `eventId` must be preserved. If every retry generates a new UUID, a listener relying on `eventId` will treat them as new events.

### 4.2. Keying by consumer + eventId

A single `PaymentCaptured` event may need **all** of email, audit, and projection:

```text
PaymentCaptured(evt-100)
     |
     +--> receipt-email-scheduler
     |
     +--> accounting-projection
     |
     +--> audit-logger
```

If the processed table keys globally only by `eventId`, the email consumer could accidentally block the projection consumer. To let each consumer independently process the event once, use the pair:

```text
(consumer_name, event_id)
```

Example of three valid markers:

```text
(receipt-email-scheduler, evt-100)
(accounting-projection,  evt-100)
(audit-logger,           evt-100)
```

**Note:** these consumer names are stable functional identities and should not be tied to a random process ID or thread name. If each restart generates a different `consumer_name`, the system loses the ability to recognize previously processed events.

### 4.3. Keying by Business Effect

There are cases where **two different eventIds** both request creating **one invoice for the same paymentId**. In that situation, deduplicating by `(consumer, eventId)` is **not enough** to protect the invariant "one invoice per payment". You should add a unique business key such as:

```sql
CREATE UNIQUE INDEX uq_invoice_payment
    ON invoices(payment_id);
```

This is an integration schema example requiring an existing `invoices` table; it is not part of the Maven program in section 8.

A solid design typically has **two layers of protection**:

1. **Delivery dedupe:** `(consumer_name,event_id)` prevents redelivery of the same occurrence to the same handler.
2. **Business uniqueness:** for example `payment_id + invoice_type` prevents two different events from creating a forbidden duplicate effect.

Do not use `correlationId` to deduplicate an entire workflow: it is normal for one workflow to contain multiple distinct events sharing the same correlation.

## 5. Why Local Memory Is Not Enough

Counterexample:

```java
private final Set<String> processed = ConcurrentHashMap.newKeySet();

@EventListener
public void onCaptured(PaymentCaptured event) {
    if (!processed.add(event.eventId())) {
        return;
    }
    sendReceipt(event.paymentId());
}
```

This snippet is **not safe for production** and is not a standalone program. It only remembers within a single process:

- Restarting loses `processed`.
- Each replica has a different set.
- The event is marked before sending; if sending fails, retries within the same process may be permanently blocked.
- The `sendReceipt` operation might succeed and then time out; the code does not know whether retrying is safe.
- There is no transaction with the database; the marker and side effect are not bound together.

Even though `ConcurrentHashMap` guarantees atomic `add` within **one JVM**, it cannot handle process boundaries, crashes, and external APIs.

Another variant, `if (!repository.existsById(...)) repository.save(...)`, is also unsafe when **two transactions both read "does not exist" and then both insert**. Checking beforehand does not replace a database-enforced unique constraint.

## 6. Protection with Unique Constraints and Atomic Transactions

### 6.1. Per-Consumer Marker

Minimal schema:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

The database rejects a second marker insert with the same key pair. When two workers compete, the database arbitrates via real constraints, transaction isolation, and locks instead of letting two threads evaluate a boolean flag.

### 6.2. Marker and Internal Effect Must Share a Transaction

Suppose the listener wants to create a receipt-sending request in the `notification_outbox` table. Processing flow:

```text
BEGIN TRANSACTION
       |
       +--> INSERT processed_events(consumer, eventId)
       |      |
       |      +--> Duplicate key?  -> ROLLBACK, skip already-processed occurrence
       |
       +--> INSERT notification_outbox(...)
       |
COMMIT
```

If inserting into the outbox fails, the transaction rolls back **the marker as well**; a subsequent retry can legitimately try again. If inserting the marker fails because the key already exists, the transaction containing that call rolls back, and the logic recognizes it as a duplicate.

**Avoid catching a unique constraint exception and continuing to use the failed transaction.** On some databases, a transaction after an SQL error is no longer valid for subsequent statements. The more controllable approach is to let the exception roll back the transaction and only **catch/interpret it outside the transaction boundary**.

### 6.3. Distinguishing Duplicate Errors from Other Errors

Avoid doing this:

```java
try {
    saveMarkerAndOutbox();
} catch (Exception ignored) {
    // "Must be a duplicate" — wrong: could be DB down, timeout,
    // syntax error, invalid data, or outbox insert failure.
}
```

This is a **counterexample**. Only ignore the case where a constraint indicates the marker **already exists** for the target key. Unrelated database errors must be reported, retried, or sent to a DLQ according to the delivery source's policy.

When using Spring JDBC, `DuplicateKeyException` is a specific subtype of `DataIntegrityViolationException`. Real systems should inspect unique constraint error mapping by database/driver and constraint name if multiple constraints can be violated. The demo below catches `DuplicateKeyException` **only around the marker INSERT statement**, then translates it into an internal duplicate signal; all other errors are rethrown.

## 7. Where to Place Transactions with Spring Application Events?

### 7.1. Synchronous @EventListener

With the default multicaster, a synchronous `@EventListener` normally runs on the publishing thread. If the publisher is inside a transaction, the callback can participate in that transaction.

Conceptual example:

```java
@Transactional
public void capturePayment(PaymentCommand command) {
    paymentRepository.save(...);
    publisher.publishEvent(new PaymentCaptured(...));
}
```

This is an illustrative snippet missing repository/command definitions, **not standalone code**. A synchronous listener can run before commit, so if it calls email/HTTP directly, rolling back the business transaction **cannot unsend the email**.

If the listener's marker and DB changes live in the **same source transaction**, a rollback discards both the marker and DB changes together, though you must explicitly decide whether the listener is allowed to produce pre-commit side effects.

### 7.2. @TransactionalEventListener(AFTER_COMMIT)

A post-commit callback:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCaptured(PaymentCaptured event) {
    // Invoked after the source transaction commits successfully.
}
```

By default, `@TransactionalEventListener` uses `AFTER_COMMIT`. If published outside an active transaction, this listener is **normally not invoked** because `fallbackExecution = false`. If the transaction rolls back, the `AFTER_COMMIT` listener is **not executed**.

Important point: **AFTER_COMMIT does not automatically prevent duplicates**. If the publisher emits the same event twice inside a committed transaction, there can be **two post-commit callbacks**. And each time the callback runs, it still needs markers/idempotency to protect the effect.

### 7.3. REQUIRES_NEW When Writing to the DB After Commit

Spring warns that during completion callbacks, some resources of the source transaction may **still be bound to the thread** even though the commit already happened. If you write to the DB after commit without starting a genuinely new transaction, the data might "participate" in the old resource with **no subsequent commit**.

Therefore, when an `AFTER_COMMIT` callback needs to write a new marker and outbox row, use:

- `@Transactional(propagation = Propagation.REQUIRES_NEW)` via a **Spring proxy** on a separate service; or
- A `TransactionTemplate` configured with `PROPAGATION_REQUIRES_NEW`.

Do not call a `@Transactional(REQUIRES_NEW)` method via `this.method()` within the same bean expecting the proxy to activate; self-invocation bypasses Spring AOP transactions.

### 7.4. Critical Warning: AFTER_COMMIT + Marker Still Has an Event Loss Window

Flow:

```text
BEGIN business transaction
    save payment
    publish PaymentCaptured in memory
COMMIT business transaction    <-- business data is durable
    |
    | process crashes here
    v
@TransactionalEventListener(AFTER_COMMIT)
    insert processed marker + outbox
```

If the process dies **after the business commit but before the listener writes the outbox**, there is no callback left to retry after restart. Neither a marker nor an outbox row exists. Idempotency only solves **duplicates if an event is reprocessed**, not rescuing an event that was **never persisted**.

**When events must not be lost:** write the outbox record (representing the event to deliver) **in the same business transaction** as the payment change, then let an independent worker read, retry, and publish it. In that setup, the local post-commit Spring event can be used as a **hint to wake up the worker**, not as the sole source of delivery durability.

## 8. Complete Example: Java 17 + Spring Framework 6.2 + JDBC + H2

This example concretely demonstrates the contract **"the same PaymentCaptured is redelivered, but only one outbox job is created"**. The project uses plain Spring Framework without Spring Boot, a web server, or a message broker.

Model:

- `PaymentCaptured` is a payload record with a stable `eventId`.
- `PaymentCaptured` is published **twice in one committed transaction**, then published **once more in another transaction** to simulate replay.
- Another event is published in a **rolled-back** transaction, so `@TransactionalEventListener(AFTER_COMMIT)` does not process it.
- Yet another event is published **outside a transaction**, so the listener with `fallbackExecution=false` does not run.
- The post-commit listener uses `TransactionTemplate` with `PROPAGATION_REQUIRES_NEW`.
- Inside the new transaction, the listener inserts the marker `(receipt-scheduler,eventId)` and then inserts one `notification_outbox` row. Duplicate repetitions are blocked by the unique constraint.
- No real email is sent: the outbox is a durable **send request**, not proof that an email was sent.

### 8.1. Project Structure

```text
idempotent-spring-event-listener/
├── pom.xml
└── src/main/java/example/IdempotentEventDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>idempotent-spring-event-listener</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.IdempotentEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. src/main/java/example/IdempotentEventDemo.java

```java
package example;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentEventDemo {

    // One payment occurrence: eventId must remain unchanged on replay.
    public record PaymentCaptured(
            String eventId,
            String paymentId,
            String correlationId) {

        public PaymentCaptured {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(paymentId, "paymentId");
            Objects.requireNonNull(correlationId, "correlationId");
            if (eventId.isBlank()
                    || paymentId.isBlank()
                    || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "Identifiers cannot be blank");
            }
        }
    }

    // Represents only a unique key violation on the receipt marker.
    private static final class DuplicateDelivery
            extends RuntimeException {
        DuplicateDelivery(DuplicateKeyException cause) {
            super(cause);
        }
    }

    public static class ReceiptScheduler {
        private static final String CONSUMER = "receipt-scheduler";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate newWorkTx;
        private final AtomicInteger attempts = new AtomicInteger();
        private final AtomicInteger scheduled = new AtomicInteger();
        private final AtomicInteger duplicates = new AtomicInteger();

        public ReceiptScheduler(JdbcTemplate jdbc,
                                TransactionTemplate newWorkTx) {
            this.jdbc = jdbc;
            this.newWorkTx = newWorkTx;
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCaptured(PaymentCaptured event) {
            attempts.incrementAndGet();

            try {
                newWorkTx.executeWithoutResult(status -> {
                    try {
                        // Atomic claim, relying on the DB PRIMARY KEY.
                        jdbc.update(
                                "INSERT INTO processed_events "
                                + "(consumer_name, event_id) "
                                + "VALUES (?, ?)",
                                CONSUMER, event.eventId());
                    } catch (DuplicateKeyException duplicate) {
                        // Let TransactionTemplate roll back before the
                        // caller interprets this as a duplicate.
                        throw new DuplicateDelivery(duplicate);
                    }

                    // Same transaction as the marker: if this fails,
                    // the marker rolls back too so retries can rerun.
                    jdbc.update(
                            "INSERT INTO notification_outbox "
                            + "(consumer_name, event_id, payment_id, "
                            + "correlation_id) VALUES (?, ?, ?, ?)",
                            CONSUMER, event.eventId(),
                            event.paymentId(), event.correlationId());
                });

                // Count only when the new transaction commits successfully.
                scheduled.incrementAndGet();
            } catch (DuplicateDelivery alreadyHandled) {
                duplicates.incrementAndGet();
            }
        }

        public int attempts() {
            return attempts.get();
        }

        public int scheduled() {
            return scheduled.get();
        }

        public int duplicates() {
            return duplicates.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                    new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:idempotency_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("businessTx")
        public TransactionTemplate businessTx(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean("newWorkTx")
        public TransactionTemplate newWorkTx(
                PlatformTransactionManager transactionManager) {
            TransactionTemplate template =
                    new TransactionTemplate(transactionManager);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            return template;
        }

        @Bean
        public ReceiptScheduler receiptScheduler(
                JdbcTemplate jdbc,
                @Qualifier("newWorkTx")
                TransactionTemplate newWorkTx) {
            return new ReceiptScheduler(jdbc, newWorkTx);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate businessTx =
                    context.getBean(
                            "businessTx", TransactionTemplate.class);
            ReceiptScheduler scheduler =
                    context.getBean(ReceiptScheduler.class);

            jdbc.execute(
                    "CREATE TABLE payment_records ("
                    + "event_id VARCHAR(80) PRIMARY KEY,"
                    + "payment_id VARCHAR(80) NOT NULL)");
            jdbc.execute(
                    "CREATE TABLE processed_events ("
                    + "consumer_name VARCHAR(80) NOT NULL,"
                    + "event_id VARCHAR(80) NOT NULL,"
                    + "PRIMARY KEY (consumer_name, event_id))");
            jdbc.execute(
                    "CREATE TABLE notification_outbox ("
                    + "id BIGINT GENERATED BY DEFAULT AS IDENTITY "
                    + "PRIMARY KEY,"
                    + "consumer_name VARCHAR(80) NOT NULL,"
                    + "event_id VARCHAR(80) NOT NULL,"
                    + "payment_id VARCHAR(80) NOT NULL,"
                    + "correlation_id VARCHAR(80) NOT NULL,"
                    + "UNIQUE (consumer_name, event_id))");

            PaymentCaptured captured = new PaymentCaptured(
                    "evt-100", "PAY-42", "flow-7");

            // Publish the same occurrence twice before business commit.
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO payment_records "
                        + "(event_id, payment_id) VALUES (?, ?)",
                        captured.eventId(), captured.paymentId());
                context.publishEvent(captured);
                context.publishEvent(captured);
            });

            // Redeliver the same occurrence in another transaction.
            businessTx.executeWithoutResult(
                    status -> context.publishEvent(captured));

            // Event published in a rolled-back transaction: no AFTER_COMMIT.
            PaymentCaptured rolledBack = new PaymentCaptured(
                    "evt-rollback", "PAY-X", "flow-X");
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO payment_records "
                        + "(event_id, payment_id) VALUES (?, ?)",
                        rolledBack.eventId(), rolledBack.paymentId());
                context.publishEvent(rolledBack);
                status.setRollbackOnly();
            });

            // Outside transaction: fallbackExecution defaults to false.
            context.publishEvent(
                    new PaymentCaptured(
                            "evt-no-tx", "PAY-NO", "flow-NO"));

            System.out.println("Listener attempts: "
                    + scheduler.attempts());
            System.out.println("Scheduled once: "
                    + scheduler.scheduled());
            System.out.println("Duplicates skipped: "
                    + scheduler.duplicates());
            System.out.println("Payment records: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM payment_records",
                            Integer.class));
            System.out.println("Processed markers: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM processed_events",
                            Integer.class));
            System.out.println("Outbox rows: "
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM notification_outbox",
                            Integer.class));
        }
    }
}
```

### 8.4. Running the Application

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Six lines of output printed by the program**, excluding Maven/Spring infrastructure logs:

```text
Listener attempts: 3
Scheduled once: 1
Duplicates skipped: 2
Payment records: 1
Processed markers: 1
Outbox rows: 1
```

Explanation:

1. The first business transaction saves one `payment_records` row and publishes the same `PaymentCaptured("evt-100", ...)` **twice**.
2. The business transaction commits; two post-commit callbacks are triggered. The first callback opens a `REQUIRES_NEW` transaction, inserts the marker and outbox row, and commits successfully. The second callback inserts the same marker, violates the `PRIMARY KEY`, rolls back, and is counted as a duplicate.
3. A new transaction republishes the same `evt-100`. The listener receives the callback again and is again blocked by the committed marker.
4. The transaction containing `evt-rollback` explicitly rolls back. There is no `AFTER_COMMIT` callback for this event; its `payment_records` row also rolls back.
5. The `evt-no-tx` event is published without a transaction; the listener with `fallbackExecution=false` does not run.
6. Therefore, **3 callbacks were executed**, **1 scheduling succeeded**, and **2 duplicates were skipped**; the database has only one payment record, one marker, and one outbox row.

**Why use a new transaction?** `@TransactionalEventListener(AFTER_COMMIT)` is called after the source transaction commits. `newWorkTx` is configured with `PROPAGATION_REQUIRES_NEW`, ensuring the marker and outbox reside in an independent transaction with its own commit.

**Why catch duplicates outside the transaction boundary?** Inside the lambda, only `INSERT processed_events` translates `DuplicateKeyException` into `DuplicateDelivery`. `TransactionTemplate` sees a runtime exception and rolls back. Outside the transaction, the listener catches only `DuplicateDelivery` and marks it skipped. Outbox creation errors or other DB errors **are not swallowed as duplicates**.

**Limitations of the example:** the code uses an H2 in-memory DB and runs in a single process. When the process exits, H2 data does not persist across restarts. `DriverManagerDataSource` does not use connection pooling; it is suitable for demos, not production configuration. To prove crash/restart reliability, you need a durable DB, a real outbox worker, recipient-side idempotency, and multi-process integration tests.

The example verifies **eventId deduplication in a post-commit listener**, but **does not fix the event loss window between business commit and the AFTER_COMMIT callback**. Section 10 presents a stronger architecture to address durability.

## 9. What Happens When Two Workers Process Concurrently?

Suppose two replicas simultaneously receive the same `eventId=evt-100`:

```text
Worker A                      Worker B
   |                             |
   | BEGIN                       | BEGIN
   | INSERT processed(evt-100)   | INSERT processed(evt-100)
   |      |                      |      |
   |      +--> wins DB lock      |      +--> waits or unique error
   | INSERT outbox               |
   | COMMIT                      | ROLLBACK / duplicate
   |
   +--> only one outbox effect
```

With a properly enforced primary key/unique constraint on a shared database, two transactions cannot **both commit** two markers with the same key. The exact details of which worker waits, which receives an exception, and when the error occurs depend on the database/isolation/driver; you should not assume worker B always fails immediately on the INSERT statement.

A check-first pattern:

```java
if (!repository.existsById(key)) {
    repository.insert(key);
    createOutboxWork();
}
```

is a **counterexample**: both workers can read "does not exist" at the same time. Only when the database enforces the constraint and the transaction accompanies the effect do we have a strong enough deduplication foundation across multiple processes.

**However, if `createOutboxWork()` is called before claiming the key**, two workers may have already executed the effect before contesting the marker. Therefore, **claiming the marker before the internal effect**, within the same transaction, is what prevents duplicate effects.

### Difference Between Unique Violation and Timeout/Deadlock

When two transactions contend, besides duplicates, lock timeouts, deadlocks, or connection errors can also occur. You must never catch every `DataAccessException` and treat it as "already processed". A transient failure requires retrying according to policy; a unique violation of the **exact marker key** can be treated as an already-processed duplicate.

In particular, a transaction can fail **before commit** after inserting the marker but before creating the outbox row. If the transaction rolls back, the marker is not durably persisted and retries must be allowed to run again.

## 10. Preventing Event Loss: Transactional Outbox in the Business Transaction

If the business requirement is **no notifications may be lost once a payment has committed**, the stronger solution is to write the outbox **in the same transaction as the payment change**, rather than only trying to write the outbox from a post-commit callback.

```text
Payment service
  BEGIN TRANSACTION
       |
       +--> UPDATE/INSERT payment business state
       |
       +--> INSERT event_outbox(eventId, paymentId, payload)
       |
  COMMIT -- both business state and outbox are durable together
       |
       v
Outbox worker (can run after restart)
  claim pending row
  publish/execute action with retry
  mark delivered/complete
```

Conceptual service pattern:

```java
@Transactional
public void capturePayment(PaymentCommand command) {
    Payment payment = saveCapturedPayment(command);
    outboxRepository.insert(
            new OutboxEntry(
                    payment.eventId(),
                    "PaymentCaptured",
                    payment.paymentId()));
    // Can publish a local event to wake the worker,
    // but the worker must also poll the outbox to avoid losing work.
}
```

This is **not standalone code**; it requires defining `PaymentCommand`, `Payment`, repositories, a transaction manager, and `OutboxEntry`. The key point: the business change and the outbox record **must commit together**.

### Distinguishing Two Outboxes

- `Event outbox` written by the business service in the original transaction: guarantees there is a record to deliver after the business commit.
- `Notification outbox` written by a consumer after receiving the event: guarantees an internal email-sending job is created if the consumer processed it.

Both tables can coexist in a multi-stage architecture. One table does not automatically solve the reliability of the preceding stage. Do not call an `AFTER_COMMIT` listener writing to `notification_outbox` an "end-to-end transactional outbox" if the source event has not been durably persisted.

### Outbound Delivery Workers Must Also Be Idempotent

When a worker calls an email-sending API, two windows still remain:

1. **Send succeeds, crash before writing DONE:** a retry may send it again.
2. **Write DONE before sending, crash:** the email may **never be sent**.

No ordinary ACID transaction spans both an internal database and an external HTTP/email API. You need strategies such as a **provider-side idempotency key**, job states, retries, backoff, reconciliation, or accepting at-least-once with harmless side effects.

In a payment system, the send key can be a **stable operation ID** tied to the payment/event + effect type. Do not use a new random UUID on every retry if you want the provider to recognize the same operation.

## 11. Analyzing "Crash Windows" by Point in Time

| Crash Point | What Remains in DB | Consequence | Mitigation |
| --- | --- | --- | --- |
| Before business commit | Business transaction rolls back | No payment completed | Retry by transaction/request key |
| After business commit, before `AFTER_COMMIT` callback | Payment committed; callback has no marker/outbox yet | **Follow-up event may be lost** | Write event outbox in the same business transaction |
| During marker + notification outbox transaction | New transaction rolls back | No partial marker/effect committed | Retry the entire transaction |
| After marker + outbox commit, before sending email | Outbox exists, marker exists | Can continue via worker | Poll/retry pending rows |
| After email succeeds, before ack/DONE | Email may be sent, internal state not updated yet | Retry may send duplicate | Provider idempotency key/reconcile |
| When two workers claim the same event | May contend on unique key/lock | One worker processes, the other gets duplicate/retry | DB constraint + claim transaction |

**Idempotency controls "do not execute an effect twice"; durability controls "do not lose work that needs to be done".** Both are essential in workflows with financial consequences or critical data.

## 12. Processed Marker State Model

A simple marker only represents **processing finished** when committed alongside an internal effect. For long-running work, especially external I/O, states must be separated more explicitly:

```text
PENDING -> CLAIMED/IN_PROGRESS -> SUCCEEDED
                      |
                      +--> FAILED_RETRYABLE -> PENDING
                      |
                      +--> FAILED_TERMINAL / DEAD_LETTER
```

These states require designing leases/timeouts, `attempt_count`, `next_attempt_at`, and distinguishing transient errors from permanent errors. Do not store a "DONE" marker merely because the handler received the event.

An example outbox table might look like:

```sql
CREATE TABLE event_outbox (
    event_id          VARCHAR(80) PRIMARY KEY,
    event_type        VARCHAR(120) NOT NULL,
    payload_json      CLOB NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempt_count     INTEGER NOT NULL,
    next_attempt_at   TIMESTAMP,
    created_at        TIMESTAMP NOT NULL
);
```

This schema is a standalone example of an **event outbox** design, not the table used by the application in section 8. Production should have appropriate indexes for worker polling, database-proper locking/leasing, retention, and controlled distribution mechanisms.

## 13. Idempotency and Spring Listener Types

### Synchronous @EventListener

- Normally runs on the publishing thread under the default multicaster.
- If the publisher is in a transaction, the listener can participate in the transaction.
- Exceptions can propagate to the publisher and affect commit/rollback depending on the call path.
- If calling an external API directly, DB rollback does not roll back the API; boundaries must be separated.

### @Async @EventListener

```java
@Async("eventExecutor")
@EventListener
public void onCaptured(PaymentCaptured event) {
    // Worker thread: does not carry the source transaction by default.
}
```

This is an integration snippet requiring `@EnableAsync`, an executor bean, and appropriate imports. With `@Async`:

- A publish call can submit a task to the queue and return before the task finishes.
- Errors in `@Async void` usually go through `AsyncUncaughtExceptionHandler`, not back to the caller.
- If processing needs a transaction, the worker opens its own transaction.
- Do not pass mutable entities, persistence contexts, or JDBC connections from the publisher as payloads.
- MDC/security/transaction state does not propagate across threads by default; a `TaskDecorator` for logging context does not replace transactions.
- Duplicates can arise from upstream redelivery, multiple publishes, or retries.
- **A unique constraint on the shared database** remains an essential safeguard across workers.

### @TransactionalEventListener(AFTER_COMMIT)

- Fires callback only when the source transaction has committed, unless configured otherwise via `fallbackExecution`.
- Does not automatically deduplicate repeated publishes.
- When needing to write in the callback, use an appropriate new transaction.
- Has a crash window after business commit before the callback.
- If guaranteed non-loss of events is required, write an event outbox in the original transaction.

### @Order and condition

`@Order` controls the relative order of listeners under applicable conditions; it **does not reduce the callback count** and does not prevent duplicates on retry. `@EventListener(condition = "...")` filters by event/SpEL properties, but **has no memory of processed eventIds**; it is not a durable idempotency mechanism.

### Spring Application Events and Brokers

Spring's `publishEvent(Object)` is an **in-process** mechanism. Kafka, RabbitMQ, or an outbox worker can feed messages into a Spring listener via `publishEvent(...)`, but Spring does not automatically provide cross-process ack/offset/replay. **Sources of duplicates and at-least-once semantics** at the broker boundary must be analyzed separately.

## 14. Pitfalls When Catching Duplicate Errors

A marker table often has multiple constraints. If a listener catches every `DuplicateKeyException` thrown anywhere in the **entire transaction**, it can mistake a duplicate error on a business/outbox table for "event already processed". This is dangerous because the outbox may be in an inconsistent state.

Safer approach:

1. Only **translate** the duplicate exception right around `INSERT processed_events` for the exact consumer key.
2. Let the transaction roll back when the marker already exists.
3. Only **catch the intentional duplicate signal** outside the transaction.
4. Let errors on other SQL statements surface as errors that must be handled.
5. Have a dedicated test where outbox insertion fails to confirm the marker rolls back and is not marked as a duplicate.

**Do not rely on exception message text** because it varies by DB, driver, and locale. Prefer exception types/SQLState/standardized constraint names and test on the target database.

On some databases, `INSERT ... ON CONFLICT DO NOTHING` or `INSERT IGNORE` can be useful, but they have specific semantics and are not portable. If used, you must check **affected rows** (0 or 1) and ensure only the marker's unique key is ignored without masking other data errors. The example in section 8 uses a standard insert to present the mechanism clearly on H2.

## 15. When Events Have Ordering or Aggregate Versions

Idempotency and ordering are two distinct problems:

```text
OrderUpdated(eventId=evt-9, orderId=ORD-42, version=9)
OrderUpdated(eventId=evt-8, orderId=ORD-42, version=8)
```

Both have different eventIds, so the `(consumer,eventId)` marker **treats neither as a duplicate**. However, if a consumer updates a read model by version, processing `version=8` **after** version 9 can regress the data to an older state.

The solution is to add a monotonic version condition:

```sql
UPDATE order_projection
SET status = ?, aggregate_version = ?
WHERE order_id = ?
  AND aggregate_version < ?;
```

This is an illustrative SQL snippet requiring a table with matching columns and handling the case where the row does not yet exist. An `UPDATE` with 0 affected rows may mean "stale version", which is not synonymous with a duplicate `eventId`. For update sequences where skipping versions is unacceptable, buffering/ordering or sequence-based replay may be needed.

**Do not use `correlationId` as a version**. A workflow can include many valid events sharing the same correlation.

## 16. Testing Idempotency Thoroughly

A good test must verify **business outcomes**, not just method call counts.

### 16.1. Test Sending the Same Event Twice

Input:

```text
PaymentCaptured(evt-100, PAY-42, flow-7)
PaymentCaptured(evt-100, PAY-42, flow-7)
```

Expectations:

- The listener may receive **2 callbacks**.
- The consumer's marker table has only **1 row**.
- The notification outbox table has only **1 row**.
- No two emails/credits/transfers originate from the same effect key.

The program in section 8 simulates an additional replay, yielding `attempts=3`, `scheduled=1`, `duplicates=2`.

### 16.2. Test Two Distinct Valid Events

Two events with different `eventId` and different `paymentId` values must both create separate markers/effects when the contract allows. A test that only checks duplicates without testing a second valid event can hide an "over-broad deduplication" bug.

### 16.3. Test Internal Effect Rollback

Intentionally cause the outbox insert to fail **after inserting the marker**; the new transaction must roll back the marker as well. After fixing the simulated failure and retrying, the handler must succeed. If the marker remains after an error, the transaction design is not atomic.

### 16.4. Test Source Transaction Rollback

Publish an event inside a source transaction and roll it back. With `@TransactionalEventListener(AFTER_COMMIT)`, the listener **must not** create a marker/outbox row for that event. The program in section 8 already covers this branch.

### 16.5. Test Publishing Outside a Transaction

With `fallbackExecution=false`, a transaction-bound listener must not be called if published without a transaction. Tests must confirm this policy is appropriate; if out-of-transaction events also need handling, design a separate processing path or choose a deliberate configuration.

### 16.6. Test Contention Between Two Workers

Use two separate transactions/connections, synchronize the moment they submit the marker using a barrier/latch, and do not rely on fixed `Thread.sleep` timings. With a real DB and unique constraint, ultimately **only one marker and one effect** commit. The losing worker must be handled as a duplicate or a contention error requiring retry based on actual state, not by naively swallowing all exceptions.

### 16.7. Test Crash Windows

Integration/system tests outside the unit test JVM are required:

- Kill the process after business commit but before the post-commit callback: **an AFTER_COMMIT-only model can lose follow-ups**.
- Kill the worker after sending an outbound message but before ack: the broker/outbox may redeliver, and the consumer must not create duplicate effects.
- Kill the worker after outbox commit but before sending: the work must be picked up by a new worker.
- Inject transient database errors: the marker must not be marked successful if the effect has not committed.
- Verify idempotency keys are preserved across retries, restarts, and multiple replicas.

### 16.8. Test Using @RecordApplicationEvents

`@RecordApplicationEvents` in Spring TestContext is useful to assert **events were published** with the right payload, but it **does not by itself prove the handler is idempotent**. You must inspect the marker table, outbox, and effects after the transaction commits. An event recorded twice can still produce exactly **one** side effect — that is the idempotent behavior to prove.

## 17. Operational Observability: Counting Attempts, Duplicates, Successes, and Failures

Logs/metrics should answer:

```text
eventType
eventId
consumerName
correlationId
causationId (if present)
aggregateId / paymentId
deliveryAttempt
handlerInvocationId
processingStatus
effectKey
instanceId
```

Example of two callbacks for the same occurrence:

```text
type=PaymentCaptured id=evt-100 consumer=receipt-scheduler
attempt=1 status=SCHEDULED effectKey=receipt:PAY-42

type=PaymentCaptured id=evt-100 consumer=receipt-scheduler
attempt=2 status=DUPLICATE_SKIPPED effectKey=receipt:PAY-42
```

Do not log full customer/payment card details just for debugging. Distinguish `DUPLICATE_SKIPPED` from `FAILED_RETRYABLE`; if every exception is classified as a duplicate, serious infrastructure issues can be masked.

Useful metrics:

- `listener_attempts_total`: number of callbacks entering the handler.
- `listener_succeeded_total`: number of internal effects committed successfully.
- `listener_duplicates_skipped_total`: number of callbacks blocked by the marker.
- `listener_failed_total`: non-duplicate errors.
- `outbox_pending_count` and `outbox_oldest_age`: pending backlog.
- `retry_count`, `dead_letter_count`, `idempotency_conflict_count` per consumer.

If duplicates spike, investigate upstream causes: HTTP retries, redelivery, timeouts, multiple publishers, or slow consumer processing. Idempotency makes the system safer, but **is not an excuse to ignore the root cause**.

## 18. Common Mistakes

1. **Assuming Spring automatically deduplicates eventId.** `publishEvent` has no such contract.
2. **Confusing idempotency with calling a listener exactly once.** Callbacks can be many; the effect remains one.
3. **Using in-RAM `HashSet`/`ConcurrentHashMap` as the sole guarantee.** Does not survive restarts or multiple replicas.
4. **Using `correlationId` as a unique key.** Blocks valid events in the same workflow.
5. **Changing `eventId` when retrying the same occurrence.** The marker fails to recognize duplicates.
6. **Using `orderId` as an overly broad key.** One order can have multiple valid events.
7. **Only doing `SELECT exists` before `INSERT` without a unique constraint.** Two workers can pass at the same time.
8. **Recording the marker and executing the effect in a different transaction without failure handling.** Can miss effects or create duplicates.
9. **Sending email/HTTP then recording the marker, assuming DB rollback will undo the API call.** There is no ACID across external systems.
10. **Marking processed before the external side effect can actually proceed.** Retries can be wrongly locked out.
11. **Catching every exception and treating it as a duplicate.** Swallows DB/outbox errors and loses work.
12. **Catching a unique error inside a transaction and continuing to run SQL on the failed transaction.** Must roll back cleanly.
13. **Using `@TransactionalEventListener(AFTER_COMMIT)` thinking it prevents duplicates.** It only binds timing.
14. **Writing to the DB after commit without opening a new transaction.** Easily attaches to old resources with no next commit.
15. **Assuming a post-commit listener is enough to guarantee no lost events.** A crash window remains after business commit.
16. **Using an outbox only in the post-commit callback without an outbox in the business transaction.** The source leg can still be lost.
17. **Using one global marker for all consumers.** The second consumer is wrongly blocked.
18. **Not checking business uniqueness for two different eventIds causing the same effect.** Delivery dedupe does not protect every invariant.
19. **Thinking `@Async` prevents duplicates.** Async only changes the thread/executor and can make races more visible.
20. **Ignoring ordering when events of different versions arrive out of order.** Idempotency is not version control.
21. **Marking "SENT" as soon as a row enters the outbox.** An outbox row is a request, not proof the provider sent it.
22. **Not testing crashes/restarts.** Synchronous unit tests do not catch event loss between transactions.
23. **Lacking duplicate and retry metrics.** The system may deduplicate properly while upstream is publishing far too many times.
24. **Claiming end-to-end exactly-once when you only have a unique marker.** You have not proven the broker/HTTP/provider and all failure windows.

## 19. Idempotent Listener Design Checklist

- [ ] Defined the **event occurrence** and kept `eventId` stable across delivery/retries.
- [ ] Defined stable **consumer identities**, independent across valid handlers.
- [ ] Deduplication key accurately reflects the effect: `(consumerName,eventId)` and business uniqueness when needed.
- [ ] Unique constraint exists on a **shared database**, not just an in-memory lock.
- [ ] Marker is claimed before the internal effect within the same transaction.
- [ ] When the internal effect fails, the marker also rolls back; retries can still run.
- [ ] Only unique violations of the **exact marker key** are ignored, without swallowing unexpected errors.
- [ ] Distinguished `SCHEDULED` in the outbox from actual `SENT`/`DELIVERED`.
- [ ] If a post-commit listener writes to the DB, it opens a new transaction via `REQUIRES_NEW`/`TransactionTemplate`.
- [ ] Defined the policy for publishing outside a transaction (`fallbackExecution`).
- [ ] If a business commit must not lose events, an event outbox exists inside the business transaction.
- [ ] Outbox worker has retries, backoff, claim/lease, metrics, and downstream idempotency.
- [ ] Did not confuse idempotency with ordering, delivery guarantees, or transaction boundaries.
- [ ] Included tests for sequential and concurrent duplicates, rollbacks, outbox failures, and crash/restart.
- [ ] Logs/metrics separate attempts, skipped duplicates, succeeded, and failed per consumer.
- [ ] Sensitive data is not exposed in logs or unnecessary external idempotency keys.

**Remember:** an idempotent listener is a listener that can **be invoked/redelivered repeatedly** without duplicating the **protected side effect**. Use **stable keys, unique constraints, and atomic transactions** for markers + internal effects. When reliable data is required after commit, additionally design a **transactional outbox in the business transaction** along with retry and downstream idempotency mechanisms. Spring Application Events distributes events; end-to-end reliability remains the architectural responsibility of the system.

## Official Documentation

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

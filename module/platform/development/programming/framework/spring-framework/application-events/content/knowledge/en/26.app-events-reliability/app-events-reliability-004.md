# Ensuring Important Events Are Not Lost in Spring Framework Application Events

## 1. The Reliability Problem: An Important Event Must Not Live Only in Memory

Suppose an application commits an order state of **PAID**, yet the **OrderPaid** event fails to reach the invoicing system. The payment data is right, but the invoice may never be generated. Conversely, if the event is sent **before the transaction commits** and the database rolls back, downstream may issue an invoice for a transaction that never actually succeeded.

This is the **dual-write problem**: two actions that must remain consistent — updating business data and publishing a message — cannot be guaranteed merely by calling two APIs in sequence.

In Spring Framework, **ApplicationEventPublisher.publishEvent(Object)** primarily hands an object to the **in-application** event listener mechanism. A default synchronous **@EventListener** normally runs immediately on the publisher's thread; **@Async** or a custom executor can offload work to another thread. **@TransactionalEventListener(AFTER_COMMIT)** selects the right phase based on the transaction outcome, but does not automatically create a durable queue. None of the three automatically recovers events after a JVM crash.

A high-reliability design typically uses:

1. **Transactional outbox**: update business data and write the record to be published in the **same DB transaction**.
2. **Outbox relay**: a worker or CDC reads committed events, sends them to the broker/downstream, and retries on failure.
3. **At-least-once delivery**: allows redelivery because a crash can happen after a successful send but before ACK.
4. **Idempotent consumer**: does not duplicate business effects even when receiving the same event multiple times.
5. **Monitoring and reconciliation**: detects stuck events, reconciles final state, and recovers in a controlled way.

**Never promise "impossible to lose under any circumstances".** If the database holding the outbox loses committed data, or pending rows are deleted by mistake, the outbox cannot rescue itself either. Real guarantees depend on database durability/backups/replication, broker acks, operations, and the faults the system is engineered to tolerate.

## 2. Identifying Which Events Are Truly Critical

| Event | Impact if lost | Handling approach |
| --- | --- | --- |
| **OrderPaid** needed for invoicing | Payment recorded but invoice missing | Transactional outbox, retries, idempotent consumer |
| **InventoryReserved** used in checkout saga | Orchestrator does not know step finished | Durable result event and workflow state |
| **AccountActivated** for permission sync | Systems drift out of state | Durable integration message, reconciliation |
| **AuditEntryRequired** in same database | Missing business evidence | Write audit in same DB transaction; use outbox if external |
| **SearchIndexUpdateRequested** | Search shows stale data | Per SLA: queue/replay or rebuild/TTL |
| **MetricIncremented** | Missing some telemetry | Best-effort may suffice; avoid unnecessary outbox |

**Key question:** If the JVM stops right after the business transaction commits, does the system still hold durable information to know **what must be sent**?

A plain Java event:

~~~java
public record OrderPaid(String orderId, String paymentId) {}
~~~

Is merely a **POJO payload**, not a durable message. Immutability helps express business facts, not guarantee the event was written to disk or received by a broker.

## 3. Gaps That Lose or Mis-Publish Events

### 3.1. Publishing Before Commit: The Event May Represent a Fact That Never Happened

~~~text
BEGIN DB TRANSACTION
    UPDATE orders SET state = PAID
    publishEvent(OrderPaid)
       |
       +-- listener calls email, HTTP, or broker
    business method throws error
ROLLBACK DB
~~~

With a default synchronous **@EventListener**, a side effect may have already happened even though the transaction later rolled back. In that case, the event no longer represents a committed fact.

### 3.2. Committing First Then Publishing: Crash Window Causes Loss

~~~text
UPDATE orders -> COMMIT succeeds
                   |
                   X JVM is killed or node stops
                   |
              Never got to publish OrderPaid
~~~

There is no durable record left to know an event needs to be sent. Even placing publication right after the save statement or after the transactional method returns still leaves a gap if the two operations lack a durable binding mechanism.

### 3.3. AFTER_COMMIT Does Not Solve Post-Commit Durability

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterPayment(OrderPaid event) {
    invoiceClient.requestInvoice(event.orderId());
}
~~~

This is a snippet; it requires a Spring-managed bean and the related types/imports. **AFTER_COMMIT** makes the handler wait for a successful commit. By default **fallbackExecution=false**, so the listener does not run if published outside an appropriate transaction. However, if the database commits and the JVM dies **before the callback or while the callback is calling a remote API**, Spring does not automatically save the callback to retry after restart.

**AFTER_COMMIT** is very useful to avoid reacting before commit, but must not be treated as a durable queue. If used to "wake a worker", the worker must still be able to scan a **durable outbox** periodically.

### 3.4. @Async Only Changes Threads, Not Durability

~~~java
@Async
@EventListener
public void on(OrderPaid event) {
    invoiceClient.requestInvoice(event.orderId());
}
~~~

The snippet above may place the task into an **in-memory** queue. If the process dies while the task is waiting, work is lost. Exceptions in `void` async methods do not automatically propagate to the caller; adding more threads does not create recovery capability. **ApplicationEventPublisher** and executors do not provide broker ACKs or a shared transaction with the database.

### 3.5. Broker Received It But ACK Was Lost: Can Redeliver

If a worker sends successfully and dies **before marking SENT**, on next startup it will send again. If the client misses the ACK even though the broker persisted the message, a retry may also be needed. Thus a no-event-loss strategy usually requires accepting **at-least-once** and having an **idempotent consumer**.

## 4. Foundational Solution: Transactional Outbox

### 4.1. Writing Business State and Publication Intent in the Same Transaction

~~~text
           Application service
                   |
                   | BEGIN
                   v
          +-------------------+
          | UPDATE orders     |
          | INSERT outbox     |
          +-------------------+
                   |
                  COMMIT
                   |
             Durable database
                   |
                   v
          Relay / poller / CDC
                   |
             send and ACK
                   |
                   v
             Message broker
                   |
             Deliver/retry
                   |
                   v
         Consumer + dedup/inbox
                   |
              Business effect
~~~

**Producer invariant:**

> When business state commits successfully, an **outbox record for the event to publish** must also commit; when the business transaction rolls back, both business state and outbox record must roll back.

The critical condition is **the same real database transaction**. If the order is saved in DB A while the outbox is written in DB B without an appropriate protocol, the two operations are not automatically atomic. If the outbox write uses **REQUIRES_NEW** and commits separately before the business transaction fails, phantom events can still occur.

### 4.2. Outbox Schema and Contents to Store

Architectural schema example:

~~~sql
CREATE TABLE outbox (
    event_id          VARCHAR(80) PRIMARY KEY,
    aggregate_type    VARCHAR(80) NOT NULL,
    aggregate_id      VARCHAR(80) NOT NULL,
    event_type        VARCHAR(120) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           TEXT NOT NULL,
    state             VARCHAR(20) NOT NULL,
    attempts          INTEGER NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    next_attempt_at   TIMESTAMP,
    last_error        TEXT,
    claimed_by        VARCHAR(80),
    claim_until       TIMESTAMP
);
~~~

Notable fields:

- **event_id**: unique ID that stays **stable across all retries** of the same event, typically a UUID/ULID.
- **aggregate_id / aggregate_type**: business entity identity, aiding tracing and maintaining ordering when needed.
- **event_type / schema_version**: integration contract, avoiding arbitrary Java-serializable classes.
- **payload**: snapshot of required data, without a JPA EntityManager or mutable/lazy-loaded entity objects.
- **state**: e.g., PENDING, IN_PROGRESS, SENT, PARKED.
- **attempts / next_attempt_at**: retries and backoff.
- **claimed_by / claim_until**: lease for recovery if a worker dies.
- **created_at / last_error**: monitoring, troubleshooting, and auditing.

This is a **reference schema**, not all fields are mandatory. The runnable example in section 7 uses a simplified schema to focus on atomicity, replay, and idempotency.

### 4.3. Sample @Transactional Service

~~~java
@Service
public final class MarkOrderPaidService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    @Transactional
    public void markPaid(String orderId, String paymentId) {
        Order order = orders.load(orderId);
        order.markPaid(paymentId);
        orders.save(order);

        outbox.insert(
                IntegrationEvent.orderPaid(orderId, paymentId));
    }
}
~~~

**This is an architectural snippet**, lacking full imports/classes to compile standalone. The key point is that **orders.save** and **outbox.insert** use the same transaction manager and proper connection/context. Do not write the outbox from an AFTER_COMMIT callback and assume it is atomic with the order update.

**Recommendation:** The domain can still produce a plain Java **OrderPaid**; application/infrastructure maps it into an integration message and stores it in the outbox. The domain aggregate does not need to directly inject Spring's **ApplicationEventPublisher** or a Kafka client.

## 5. Relay Sending Events: Marking SENT at the Right Time

A production relay typically does:

1. Read due outbox rows and claim them using an appropriate concurrency mechanism.
2. Send the message with a **stable eventId** and required correlation/trace metadata.
3. Wait for a **reliable broker ACK** or protocol-level confirmation result.
4. Only after ACK, update the outbox to SENT.
5. On timeout/error, allow retries with backoff. Do not delete the pending record just because the first send failed.
6. If retries exceed limits, transition to PARKED/DLQ and **alert the responsible owner**, never silently drop it.

If you mark SENT before the broker persists the message, it can be permanently lost. If you mark SENT after ACK, duplicates can be sent when a worker crashes between the two actions. This is an inherent trade-off, so consumers must handle duplicates.

**Do not confuse send() returning a Future with broker confirmation.** Use the exact ack/confirm semantics of the chosen Kafka/RabbitMQ/JMS/client.

### 5.1. Multiple Workers and Claim/Lease

A single-worker demo can use SELECT PENDING; multi-worker production requires concurrency control:

- **SELECT ... FOR UPDATE SKIP LOCKED**, or CAS/optimistic locking depending on dialect.
- **Claim state + claim_until** so records are picked up again if a worker dies.
- Claim transactions should be short, avoiding holding DB locks open while waiting on slow HTTP/broker networks.
- Workers should avoid starvation and record attempt count/`next_attempt_at`.
- For events on the same aggregate, partitioning/sequencing may be needed to preserve appropriate order.

Do not copy `SKIP LOCKED` SQL across PostgreSQL, MySQL, and H2 without verifying transaction isolation/index behavior. DB-specific SQL and worker leasing must be integration-tested on the real database.

## 6. Consumer Idempotency to Handle At-Least-Once

Suppose the same event **EVT-42** arrives twice. The invoicing consumer must create only **one invoice** if that is the business invariant.

Common pattern:

~~~text
BEGIN consumer transaction
  INSERT processed_messages(consumer_name, event_id)
      UNIQUE(consumer_name, event_id)
  IF ID already exists:
      do not repeat the business side effect
  ELSE:
      INSERT invoice / UPDATE business state
COMMIT
ACK broker
~~~

**The processed marker and the DB business effect must be in the same transaction.** If the marker commits first before the invoice is created, a crash makes retries think the event was already processed and skip it. Conversely, if the invoice commits while the marker does not, retries can create duplicates.

Beyond event ID, a **unique business key** such as one primary invoice per order ID can guard against a producer emitting two different event IDs for the same action. For HTTP APIs like payment providers, you need a **provider-side idempotency key**, state reconciliation, and manual review when timeouts leave outcomes unknown. A local inbox DB alone does not make HTTP calls exactly-once.

### 6.1. Three Guarantee Levels Often Confused

| Term | Meaning |
| --- | --- |
| **At-most-once** | Avoids redelivery but can lose work |
| **At-least-once** | Retries to avoid dropping work upon infrastructure recovery; may reprocess |
| **Effectively-once effect** | An idempotent consumer ensures the business outcome occurs only once despite repeated messages |

Never claim **end-to-end exactly-once** merely because the producer uses an idempotent broker mode or the outbox relay has a SENT status. Each DB, broker, and external provider has different commit boundaries and failure modes.

## 7. Runnable Java 17+ Demo: Durable Outbox, Rollback, and Retry Across Restarts

The example below uses **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, **Java 17+**, and **Gradle 8.x**. It requires no Spring Boot, HTTP server, or real broker.

Idea:

1. Write **orders + outbox** inside one **TransactionTemplate** to commit/roll back.
2. Publish a Spring **OutboxWritten** event as an observation signal; an immediate listener prints before commit, while an AFTER_COMMIT listener prints only on the commit branch.
3. Persist the database to an **H2 file** instead of in-memory H2 so data survives after the JVM exits.
4. The relay processes **PENDING** rows and writes into a simulated **consumer_inbox**, then intentionally **simulates a crash before ACK**.
5. On the next command run, the pending outbox row is still visible, and the consumer recognizes the event by **eventId** without duplicating the simulated effect.

**Limitations:** The fake receiver and producer in the demo share the same H2 file for convenience. They execute two separate transactions, but do not simulate a broker, independent services, network partitions, or real crashes. The code does not implement multi-worker claim/lease; it only runs sequential modes.

### 7.1. Structure and Build

~~~text
reliable-spring-events/
  build.gradle
  src/main/java/demo/ReliableEventsDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ReliableEventsDemo'
}
~~~

### 7.2. Complete Java File

**src/main/java/demo/ReliableEventsDemo.java**:

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class ReliableEventsDemo {

    public record OutboxWritten(String eventId) {}
    public record EventRow(String eventId, String payload) {}

    public static final class EventObservers {

        @EventListener
        public void immediate(OutboxWritten event) {
            System.out.println("event-now: " + event.eventId());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OutboxWritten event) {
            // Hint signal so the worker scans the outbox early.
            // The Relay below does NOT depend on this signal.
            System.out.println("event-after-commit: " + event.eventId());
        }
    }

    public static final class Producer {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Producer(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        private int count(String sql, Object... args) {
            return db.queryForObject(sql, Integer.class, args);
        }

        public void reset() {
            db.update("DELETE FROM consumer_inbox");
            db.update("DELETE FROM outbox");
            db.update("DELETE FROM orders");
            System.out.println("reset: done");
        }

        public void rollback() {
            tx.executeWithoutResult(status -> {
                db.update(
                    "INSERT INTO orders (id, state) VALUES (?, ?)",
                    "ORD-ROLL", "PAID");
                db.update(
                    "INSERT INTO outbox "
                    + "(event_id, aggregate_id, payload, state, attempts) "
                    + "VALUES (?, ?, ?, ?, ?)",
                    "EVT-ROLL", "ORD-ROLL",
                    "OrderPaid:ORD-ROLL", "PENDING", 0);

                publisher.publishEvent(new OutboxWritten("EVT-ROLL"));
                status.setRollbackOnly();
            });

            System.out.println("rollback: orders="
                + count("SELECT COUNT(*) FROM orders WHERE id = ?",
                        "ORD-ROLL")
                + " outbox="
                + count("SELECT COUNT(*) FROM outbox WHERE event_id = ?",
                        "EVT-ROLL"));
        }

        public void produce() {
            tx.executeWithoutResult(status -> {
                db.update(
                    "INSERT INTO orders (id, state) VALUES (?, ?)",
                    "ORD-42", "PAID");
                db.update(
                    "INSERT INTO outbox "
                    + "(event_id, aggregate_id, payload, state, attempts) "
                    + "VALUES (?, ?, ?, ?, ?)",
                    "EVT-42", "ORD-42",
                    "OrderPaid:ORD-42", "PENDING", 0);
                publisher.publishEvent(new OutboxWritten("EVT-42"));
            });

            System.out.println("produce: order="
                + count("SELECT COUNT(*) FROM orders WHERE id = ?",
                        "ORD-42")
                + " pending="
                + count("SELECT COUNT(*) FROM outbox WHERE state = ?",
                        "PENDING"));
        }
    }

    public static final class Relay {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;

        public Relay(
                JdbcTemplate db,
                PlatformTransactionManager manager) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
        }

        private int count(String sql, Object... args) {
            return db.queryForObject(sql, Integer.class, args);
        }

        public void status() {
            long attempts = db.queryForObject(
                "SELECT COALESCE(SUM(attempts), 0) FROM outbox",
                Long.class);
            System.out.println(
                "state: orders="
                + count("SELECT COUNT(*) FROM orders")
                + " pending="
                + count("SELECT COUNT(*) FROM outbox "
                        + "WHERE state = 'PENDING'")
                + " sent="
                + count("SELECT COUNT(*) FROM outbox "
                        + "WHERE state = 'SENT'")
                + " inbox="
                + count("SELECT COUNT(*) FROM consumer_inbox")
                + " attempts=" + attempts);
        }

        public void deliver(boolean interruptBeforeAck) {
            List<EventRow> pending = db.query(
                "SELECT event_id, payload FROM outbox "
                + "WHERE state = 'PENDING' ORDER BY event_id",
                (rs, n) -> new EventRow(
                    rs.getString("event_id"),
                    rs.getString("payload")));

            if (pending.isEmpty()) {
                System.out.println("relay: nothing pending");
                return;
            }

            EventRow event = pending.get(0);

            // This demo has a single sequential relay worker.
            db.update(
                "UPDATE outbox SET attempts = attempts + 1 "
                + "WHERE event_id = ? AND state = 'PENDING'",
                event.eventId());

            // Simulated receiver: a separate committed transaction.
            // The inbox row represents a side effect created once.
            boolean duplicate = tx.execute(status -> {
                int exists = count(
                    "SELECT COUNT(*) FROM consumer_inbox "
                    + "WHERE event_id = ?", event.eventId());
                if (exists > 0) {
                    return true;
                }
                db.update(
                    "INSERT INTO consumer_inbox "
                    + "(event_id, payload) VALUES (?, ?)",
                    event.eventId(), event.payload());
                return false;
            });

            System.out.println(
                "receiver: " + (duplicate ? "duplicate " : "new ")
                + event.eventId());

            if (interruptBeforeAck) {
                // Simulate crash AFTER receiver commit, BEFORE outbox ACK.
                System.out.println(
                    "relay: simulated crash after receiver commit, before ACK");
                status();
                return;
            }

            tx.executeWithoutResult(status -> {
                db.update(
                    "UPDATE outbox SET state = 'SENT' "
                    + "WHERE event_id = ? AND state = 'PENDING'",
                    event.eventId());
            });
            System.out.println("relay: marked SENT " + event.eventId());
            status();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                "jdbc:h2:file:./reliable_event_demo;DB_CLOSE_ON_EXIT=FALSE");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate db = new JdbcTemplate(ds);
            db.execute(
                "CREATE TABLE IF NOT EXISTS orders ("
                + "id VARCHAR(80) PRIMARY KEY,"
                + "state VARCHAR(20) NOT NULL)");
            db.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                + "event_id VARCHAR(80) PRIMARY KEY,"
                + "aggregate_id VARCHAR(80) NOT NULL,"
                + "payload VARCHAR(400) NOT NULL,"
                + "state VARCHAR(20) NOT NULL,"
                + "attempts INTEGER NOT NULL)");
            db.execute(
                "CREATE TABLE IF NOT EXISTS consumer_inbox ("
                + "event_id VARCHAR(80) PRIMARY KEY,"
                + "payload VARCHAR(400) NOT NULL)");
            return db;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        EventObservers eventObservers() {
            return new EventObservers();
        }

        @Bean
        Producer producer(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Producer(db, manager, publisher);
        }

        @Bean
        Relay relay(JdbcTemplate db, PlatformTransactionManager manager) {
            return new Relay(db, manager);
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "mode: reset|rollback|produce|relay-crash|relay-retry|status");
        }

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Producer producer = context.getBean(Producer.class);
            Relay relay = context.getBean(Relay.class);

            switch (args[0]) {
                case "reset" -> producer.reset();
                case "rollback" -> producer.rollback();
                case "produce" -> producer.produce();
                case "relay-crash" -> relay.deliver(true);
                case "relay-retry" -> relay.deliver(false);
                case "status" -> relay.status();
                default -> throw new IllegalArgumentException(
                    "unknown mode: " + args[0]);
            }
        }
    }
}
~~~

### 7.3. Run Commands and Expected Output

Run sequentially from the **reliable-spring-events** directory, with Java 17+ and Gradle 8.x installed. Each **gradle run** command is a separate program execution. H2 uses the file **reliable_event_demo.mv.db** so data persists across consecutive runs.

~~~bash
gradle --console=plain -q run --args="reset"
gradle --console=plain -q run --args="rollback"
gradle --console=plain -q run --args="produce"
gradle --console=plain -q run --args="relay-crash"
gradle --console=plain -q run --args="relay-retry"
~~~

**Lines printed by Java**, grouped by command:

~~~text
reset: done

event-now: EVT-ROLL
rollback: orders=0 outbox=0

event-now: EVT-42
event-after-commit: EVT-42
produce: order=1 pending=1

receiver: new EVT-42
relay: simulated crash after receiver commit, before ACK
state: orders=1 pending=1 sent=0 inbox=1 attempts=1

receiver: duplicate EVT-42
relay: marked SENT EVT-42
state: orders=1 pending=0 sent=1 inbox=1 attempts=2
~~~

Blank lines only separate the output of the five runs. Other logs added by Gradle or the environment are excluded.

**Result analysis:**

- **Rollback:** the regular listener immediately prints **event-now: EVT-ROLL**, but the transaction rolls back so neither order nor outbox remains in the database, and the AFTER_COMMIT listener does not print for EVT-ROLL.
- **Produce:** order and outbox commit together. The AFTER_COMMIT listener prints **event-after-commit: EVT-42** after commit; the outbox row remains **PENDING**. This record — not the listener log line — is the recovery source.
- **Relay-crash:** the fake receiver committed row **EVT-42** into the inbox, and the relay intentionally stopped before marking SENT. The outbox remains pending, simulating a crash window causing redelivery.
- **Relay-retry:** a new JVM reads the same H2 file, sees the pending record, and resends the old event ID. The inbox recognizes the duplicate and does not create a second row. The relay marks SENT; **attempts=2**.
- From here, run **gradle --console=plain -q run --args="status"** to see the record marked SENT. If you run **produce** again without **reset**, H2 reports a primary key violation as designed; this is the expected demo behavior.
- **Durability demonstrated:** the H2 file across normal restarts and retry capability. The program does **not** simulate kernel crash/fsync loss, HA DBs, or message broker ACKs.

### 7.4. Pitfall of the Fake Receiver in the Demo

The **SELECT COUNT** then **INSERT** pattern is only valid in a **single sequential worker** scenario. When multiple consumers process events concurrently, two threads can both observe count=0. Production requires:

- **UNIQUE(consumer_name, event_id)** or an equivalent constraint.
- **Atomic insert/upsert** per DB dialect or safe duplicate-key collision handling.
- Deduplication marker and DB business effect in the **same transaction**.
- For external side effects, provider idempotency or reconciliation.
- Never just write to the inbox and return ACK before the real side effect succeeds.

This example does not claim cross-broker exactly-once guarantees and the Relay should not be copied verbatim to production.

## 8. When the Outbox Still Is Not Enough: Infrastructure and Operational Failures

### 8.1. Database Durability

If a database reports commit success while its storage/replication configuration can lose data on power loss/leader failover, the outbox can be lost along with business state or diverge. Check **WAL/fsync, synchronous replication, backups, restore testing, and RPO/RTO**. Do not assume an H2 file demo has the same guarantees as an HA production database.

### 8.2. A Permanently Stuck Worker Is Still a Business Failure

If an outbox has a PENDING row sitting for 10 days with no alert, technically the event was not lost, yet **the workflow was abandoned**. The system needs:

- **pending_count**, **oldest_pending_age**, **retry_count**, **publish_failure_rate**.
- **Broker ACK latency**, **consumer lag**, **DLQ/parked count**, **consumer deduplicated_total**.
- **Business completion lag**, e.g., time from OrderPaid to InvoiceCreated.
- SLA-bound alerts, escalation owners, and audited redrive procedures.
- A policy never to delete PENDING/IN_PROGRESS/PARKED rows before they are handled.

### 8.3. Periodic Reconciliation

A reconciliation job can look for:

~~~text
Orders in PAID state
  without an InvoiceCreated/result
  after the allowed business threshold
      |
      v
Compare outbox, broker/consumer, invoicing system
      |
      +-- Retry/redrive with stable eventId
      +-- Audited repair
      +-- Manual review when outcome is unclear
~~~

If an outbox row was lost due to an operational mistake, reconciling **business state** can help reconstruct a recovery job, while avoiding creating two invoices or uncontrolled side-effect replays.

### 8.4. Per-Aggregate Ordering

For the same order:

~~~text
OrderCreated(version=1)
OrderPaid(version=2)
OrderRefunded(version=3)
~~~

With multiple relay workers and broker partitions, consumers can see events out of order. When ordering is required, use **aggregateId** as the partition/ordering key, versions/sequences, proper claiming, and **state/version guards** on the consumer. Timestamps alone do not prove the absolute commit order of concurrent transactions.

## 9. Testing Reliability by Failure Boundary

### 9.1. Producer Atomicity

- Successful commit: **order and outbox both exist**.
- Rollback-only: **neither exists**.
- Exception after writing outbox but before commit: both roll back.
- Ensure both repositories share the same transaction manager; no unintended REQUIRES_NEW.
- Retrying a request for the same business operation does not create duplicate business/event records.

### 9.2. Relay

- Worker dies before publish: outbox remains and can be retried.
- Broker disconnects: do not mark SENT, apply backoff.
- Broker receives message then ACK is lost: retry with the same eventId.
- Worker dies after ACK before marking SENT: redelivery happens, consumer deduplicates.
- Worker dies after claiming: lease expires and record is reclaimed.
- Multiple workers: claim/CAS works without uncontrolled concurrent processing.
- Poison messages: parked/DLQ with monitoring and runbooks, never silently deleted.

### 9.3. Consumer

- Same eventId delivered twice: **business side effect commits only once**.
- Crash before consumer DB commit: inbox marker and business effect both roll back; retriable.
- Crash after commit before ACK: redelivery is deduplicated.
- Two event IDs for the same business action: unique business constraint protects.
- HTTP timeout: idempotency key and reconciliation, no blind retries.
- Out-of-order / replay: do not apply backward state transitions or emit stale side effects.

### 9.4. Testing Spring Event Hooks

- Regular **@EventListener** can run before DB commit/rollback.
- **@TransactionalEventListener(AFTER_COMMIT)** runs only when commit succeeds and an active transaction matches.
- Outside a transaction: transactional listeners do not run by default unless **fallbackExecution=true**.
- Test methods with **@Transactional** in Spring TestContext normally roll back by default; use **TestTransaction.flagForCommit(); TestTransaction.end()** to verify AFTER_COMMIT within the same test method.
- **Never just verify publisher.publishEvent(...) was called** and declare events durable. Assert the outbox DB row, commit/rollback outcomes, and crash windows.

## 10. Combining Spring Events with an Outbox

A clean design:

~~~text
domain/
   Order
   OrderPaid                       (plain Java domain event)
application/
   MarkPaidUseCase
   OrderRepository, OutboxPort
infrastructure/
   JdbcOrderRepository
   JdbcOutboxWriter
   OutboxRelay / CDC publisher
   BrokerPublisher
   ConsumerInbox / invoice adapter
observability/
   eventId, aggregateId, traceId, retries, backlog age
~~~

**Spring ApplicationEventPublisher** can still support internal observers or an **AFTER_COMMIT hint** helping the worker scan the outbox early. However, always have a **poller/CDC** to recover unsent records without needing the hint. Never use an in-memory callback as the sole data source for critical events.

**Spring Modulith** offers capabilities around storing/tracking publications in certain modules and versions; if choosing that approach, check the exact persistence configuration, retry/resubmission behavior, and guarantee boundaries of your version. Do not assume any single annotation replaces all work around durable broker delivery and consumer idempotency.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Publish directly in transaction and send off-DB side effect | Phantom event on rollback | Write outbox in the same business transaction |
| Commit then call publish in Java | Crash between the two loses the event | Transactional outbox |
| Treat AFTER_COMMIT as a durable queue | Callback still lost if JVM dies | Durable outbox + poller/CDC |
| Use only @Async to ensure eventual delivery | In-memory task can be lost | Queue/outbox, retries |
| Mark SENT right when enqueuing in client memory | Broker may not have received it | Wait for strong enough broker ACK |
| Retry with a new eventId | Consumer cannot deduplicate | Keep eventId stable |
| Write processed marker before side effect in a separate transaction | Crash causes lost effect | Same local transaction for inbox + DB effect |
| Rely on check-then-insert with multiple consumers | Race condition | Unique constraint and atomic deduplication |
| Assume broker exactly-once covers DB/external APIs | Side effects still duplicate or get lost | Idempotency at each system |
| Business DB and outbox in two independent transactions | No atomicity guarantee | One real transaction or clear protocol |
| Multiple workers without claim/lease | Retry storm and races | Locks/CAS/leases, backoff |
| Not monitoring pending age | Events exist yet are never sent | Metrics, alerts, runbook |
| Purging pending outbox rows | Lost recovery records | Retention, audit, and repair |
| Not versioning schemas | Consumers break on deploy | Event types/versions and compatibility |
| Historical replay triggers emails/payments again | Repeated side effects | Separate projections and side-effect policies |

## 12. Implementation Checklist

1. **Have critical events and the consequences of losing them been identified?**
2. **Do business state and the outbox row share the same real transaction?**
3. **Does a rollback discard both?**
4. **If the JVM dies after commit, does the outbox row remain for redelivery?**
5. **Does the relay wait for an ACK at the right guarantee level before marking SENT?**
6. **Do retries preserve the exact eventId?**
7. **Does the consumer deduplicate in the same transaction as DB effects?**
8. **Do external APIs have idempotency/reconciliation?**
9. **Do multiple workers use claiming/leasing/backoff?**
10. **Are poison messages, parked/DLQ handling, and manual review addressed?**
11. **Is there monitoring for pending age, lag, retries, and business completion?**
12. **Do backups/replication/retention protect the committed outbox itself?**
13. **Have crashes after send before ACK, rollbacks, duplicates, and restarts been tested?**
14. **Are broker ACKs clearly distinguished from consumer business completion?**

**Conclusion:** To **avoid dropping critical events after business logic commits**, persist an **outbox in the same database transaction as the business state**, have a relay send and retry until acknowledged, accept **at-least-once**, and make **consumers idempotent**. Spring's **@EventListener**, **@Async**, and **@TransactionalEventListener(AFTER_COMMIT)** remain useful, yet do not create durability on their own. Reliability comes from a chain of invariants and testing across failure windows, combined with monitoring to handle stuck events.

### Official Documentation

- Spring Framework 6.2 — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- H2 Database — *SQL commands and transaction behavior*: https://h2database.com/html/commands.html

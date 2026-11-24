# Producer Commit Timing and the Risk of Consumers Reading Incomplete Data

> **Module:** Spring Framework – concurrency  
> **Topic:** Transactions and Events  
> **Goal:** Understand why a service publishing an event **before its data-writing transaction commits** can cause consumers not to find records or to observe an incomplete state; know how to use `@TransactionalEventListener(phase = AFTER_COMMIT)` appropriately, distinguish **data visibility timing** from **guaranteed event delivery**, and choose a transactional outbox when high reliability is required.

## 1. The Core Problem

Suppose service A creates an order inside a DB transaction and sends an `OrderCreated(42)` event to service B. Service B receives the event and queries the `orders` table using **another connection or a different database**.

If A sends the event while its transaction is still open:

~~~text
Service A / Transaction T1                 Service B / Connection T2
--------------------------                 -------------------------
BEGIN
INSERT orders(id=42, status=NEW)
publish OrderCreated(42) ----------------> receive event
                                          SELECT ... WHERE id=42
                                          -> row not found, or stale version
COMMIT
                                          event was already processed too early
~~~

Under common isolation levels such as `READ_COMMITTED`, an independent transaction **cannot see uncommitted data** from another transaction. As a result, B may report `order not found` even though A commits successfully a few milliseconds later. If A rolls back, the emitted event may describe an order **that never existed in a committed state**.

The key factor is not whether the message broker is fast or slow. This is a **transaction ordering and boundary bug**: publishing an event externally before the DB state becomes durable/visible to independent readers.

**Rule:** When a consumer needs to query the producer's committed state, ensure event processing only starts after the producer's transaction **commits successfully**. Do not conclude, however, that "moving event publishing to after-commit" automatically guarantees the event will never be lost: that is a second, separate problem.

## 2. Distinguishing Three Points in Time

Three distinct milestones are often conflated into one:

1. **In-transaction write:** `INSERT`/`UPDATE` has executed on the producer's connection, but commit has not completed. Code inside **the same transaction** usually reads its own changes; another reader transaction usually cannot see them yet.
2. **Successful commit:** The DB transaction manager requests commit and the DB accepts the new state. Afterward, a new read on the primary with appropriate isolation normally sees the changes. This does not mean every read replica or cache updates instantaneously.
3. **Event processed by the consumer:** The message is actually received and processed by the broker/consumer; this depends on queues, thread pools, retries, network, acknowledgements, and consumer state.

`publishEvent(...)` in Spring is **a request to publish an application event**, not a certificate that the DB has committed; `KafkaTemplate.send(...)` does not implicitly commit a preceding SQL transaction either.

Also distinguish "producer called the send API" from "broker durably stored it", "consumer received it", and "consumer processed it successfully". These have different acknowledgement guarantees; returning from an asynchronous send API does not prove the whole pipeline succeeded.

## 3. Why Can a Consumer Read Incomplete Data?

The most common scenario: the producer opens a transaction, writes to multiple tables, and emits an event in the middle or right after the last SQL statement **but before commit**. The consumer starts working sooner than the producer finishes committing.

Different outcomes arise depending on system design:

| Consumer condition | What the consumer may see |
| --- | --- |
| Reading on another connection with `READ_COMMITTED` before commit | Does not see the new record; older updated data remains visible |
| Reading in the producer's own transaction/connection | May see its own uncommitted changes; **not representative** of an independent consumer |
| Reading after commit on the primary | Normally sees the committed version, provided the query uses the right ID/isolation and no other filter excludes it |
| Reading after commit while the reader transaction holds an older snapshot (`REPEATABLE_READ`/MVCC) | May continue seeing the earlier snapshot until the reader transaction ends |
| Reading replicas/caches/materialized views after commit | May see stale state due to replication lag, cache invalidation, or projection lag |
| DB isolation allowing dirty reads (certain engines/configurations) | May see uncommitted data, but risks rollback/dirty-read anomalies |

Hence, "just publish after commit and the consumer will definitely read it immediately" is **true only within a narrow scope**, not for every database topology. You must consider primary/replicas, reader transactions, caches, and eventual consistency lag.

**Incomplete data** can also mean unstable business state: an order may span multiple tables, inventory may not be updated yet, or the transaction may be about to roll back. If the producer wraps all related changes in **a single transaction**, commit exposes them as one consistent state within the DB's atomicity scope; external system changes, however, **do not automatically join** that transaction.

## 4. Regular @EventListener Does Not Automatically Wait for Commit

In Spring Framework, `ApplicationEventPublisher.publishEvent(event)` publishes an application event to listeners. With the default `SimpleApplicationEventMulticaster` (no executor configured), a regular `@EventListener` runs **synchronously on the event-publishing thread**.

~~~java
@Transactional
public void createOrder(Command command) {
    orderRepository.save(toOrder(command));
    publisher.publishEvent(new OrderCreated(command.orderId()));
    // The transaction may STILL be uncommitted here.
}

@EventListener
public void onOrderCreated(OrderCreated event) {
    // May be invoked before the sender's transaction commits.
}
~~~

This is an **integration snippet**; `Command`, `OrderCreated`, repositories, and injections belong to the application. After `publishEvent` returns, the transactional method may keep executing and only commit **when exiting the transaction interceptor**. `@EventListener` is not a mechanism that waits for DB commit.

There is a self-testing trap: a synchronous listener can query the DB via `JdbcTemplate` on **the same thread** and join the connection bound to the producer's transaction. It can read the uncommitted row itself, creating the impression that all consumers can see it. To simulate a real consumer, you need **a different connection/transaction**, as shown in Section 6.

If the listener is marked `@Async`, or the multicaster is configured to dispatch listeners onto an executor, running on another thread exposes the timing race even more clearly: the consumer may run **before or after commit** depending on scheduling. `@Async` only adds asynchrony; it does **not** enforce an "after-commit" constraint.

## 5. A Real-World Failure Timeline

~~~text
Time           Producer in @Transactional               Consumer / broker
t0             BEGIN
t1             INSERT order 42
t2             UPDATE order_items...
t3             publish event OrderCreated(42) ----------> enqueue
t4                                                        receive
t5                                                        SELECT order 42
t6                                                        -> not found
t7             COMMIT succeeds
t8                                                        already errored or retried
~~~

The root cause is at t3: the producer publishes before the DB commits. When the consumer receives the message quickly, finding the row depends on commit speed rather than a guaranteed contract.

**An immediate retry loop is not the right fix.** It may luckily retry after commit in some cases, yet fail persistently if the producer rolled back, a replica lags, the ID is wrong, or the reader transaction holds an old snapshot. It also adds DB/broker load when the system is busy.

You can hit the same bug with emails linking to an uncommitted invoice, third-party webhooks, search-index updates driven by events, Kafka consumers reading an orders table, or an internal `@Async` task querying right after `save()`.

## 6. Runnable Example: Spring Framework + H2 Proving Visibility

The example uses **Spring Framework 6.2.9**, **H2 2.3.232**, and **Java 17+**. The producer runs inside a `DataSourceTransactionManager` transaction, inserts an order, and calls `publishEvent`. Two listeners both receive `OrderCreated` at **two different times**:

- `@EventListener`: runs immediately on publish; checks the row using an **independent** JDBC connection and sees `false` because the producer has not committed yet.
- `@TransactionalEventListener(phase = AFTER_COMMIT)`: runs only after a successful commit; the independent JDBC connection sees `true`.

The example deliberately uses `DriverManagerDataSource` so every `getConnection()` returns a new connection, **with no pool** in the demo. Because this is an in-memory H2 DB with default `READ_COMMITTED` isolation, it directly verifies visibility to another connection.

### Project Structure

~~~text
commit-visibility-demo/
├── pom.xml
└── src/main/java/demo/CommitVisibilityDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>commit-visibility-demo</artifactId>
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
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.9</version>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### src/main/java/demo/CommitVisibilityDemo.java

~~~java
package demo;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class CommitVisibilityDemo {
    public record OrderCreated(long id) {}

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource(
            "jdbc:h2:mem:commit_visibility;DB_CLOSE_DELAY=-1", "sa", "");
        ds.setDriverClassName("org.h2.Driver");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }

    @Bean
    TransactionTemplate transactionTemplate(
            DataSourceTransactionManager manager) {
        return new TransactionTemplate(manager);
    }

    @Bean
    Observer observer(DataSource ds) {
        return new Observer(ds);
    }

    public static class Observer {
        private final DataSource ds;

        public Observer(DataSource ds) {
            this.ds = ds;
        }

        private boolean committedRowVisible(long id) {
            try (Connection connection = ds.getConnection();
                 PreparedStatement stmt = connection.prepareStatement(
                     "select count(*) from orders where id = ?")) {
                stmt.setLong(1, id);
                try (ResultSet rs = stmt.executeQuery()) {
                    rs.next();
                    return rs.getInt(1) == 1;
                }
            } catch (SQLException ex) {
                throw new IllegalStateException(ex);
            }
        }

        @EventListener
        public void onImmediate(OrderCreated event) {
            System.out.println(
                "Immediate listener sees order: " +
                    committedRowVisible(event.id()));
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderCreated event) {
            System.out.println(
                "After-commit listener sees order: " +
                    committedRowVisible(event.id()));
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     CommitVisibilityDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                context.getBean(TransactionTemplate.class);
            ApplicationEventPublisher publisher = context;

            jdbc.execute(
                "create table orders (id bigint primary key, " +
                "status varchar(32))");

            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "insert into orders (id, status) values (?, ?)",
                    42L, "NEW");
                publisher.publishEvent(new OrderCreated(42L));
            });

            Integer count = jdbc.queryForObject(
                "select count(*) from orders where id = 42",
                Integer.class);
            System.out.println(
                "After transaction sees order: " + (count == 1));
        }
    }
}
~~~

**Important note:** `@EnableTransactionManagement` registers transaction infrastructure and support for `@TransactionalEventListener` in this plain Spring Framework example. Without transaction management enabled or without a `TransactionalEventListenerFactory`, do not expect the annotation to take effect in the right phase automatically. A Spring Boot app with transaction auto-configuration normally prepares this infrastructure, though you should still verify the actual context.

Run from the project root directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CommitVisibilityDemo
~~~

**Program stdout:**

~~~text
Immediate listener sees order: false
After-commit listener sees order: true
After transaction sees order: true
~~~

The code was **compiled targeting Java 17 and executed in practice** with Spring Framework 6.2.9 + H2 2.3.232 on a newer JDK; the three stdout lines above were verified. `@EventListener` runs before commit, whereas `@TransactionalEventListener` is invoked after commit. `Observer` opens a new connection so it does **not** read through the connection bound to the producer's transaction.

If you change the test to read via `JdbcTemplate` on the same thread as the immediate listener, the result can differ because it joins the open transaction. That **does not refute** the risk that an external consumer fails to see the row.

The program does not use Kafka/RabbitMQ. It simulates **DB timing and isolation** inside a single process to explain the race. With a real broker, callback dispatch adds extra latency and delivery failure modes of its own; you cannot rely on broker speed to "accidentally land after commit".

## 7. @TransactionalEventListener and Transaction Phases

Spring provides `@TransactionalEventListener` to bind a listener to the **phase** of the transaction containing the event publication call.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    // Process only after the transaction has committed successfully.
}
~~~

This is an **integration snippet**; `OrderCreated` and transaction-event infrastructure must exist in the right context. `AFTER_COMMIT` is the default if `phase` is omitted.

| Phase | Timing | Suitable for |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction commits | Checks/operations bound to the transaction before commit; **not** a signal that the DB is durable |
| `AFTER_COMMIT` | After successful commit | Sending notifications or marking next steps that rely on committed state |
| `AFTER_ROLLBACK` | After the transaction rolls back | Observing rollbacks / recording errors via a separate mechanism |
| `AFTER_COMPLETION` | After completion, commit or rollback | Cleanup/telemetry independent of specific outcome; must distinguish manually if needed |

When **no active transaction exists** at the time the event is published, a `@TransactionalEventListener` **does not run** by default. You can set `fallbackExecution = true` to run outside a transaction, though that changes the business contract; do not enable it merely as a "fix when the listener doesn't seem to run".

When a transaction rolls back, an `AFTER_COMMIT` listener does not run. It thus prevents a class of **false rollback events** that a regular `@EventListener` can suffer from.

**Do not confuse @TransactionalEventListener with @Async.** A phase-bound listener, unless separately configured as async, does not automatically switch to another worker. If `@Async` is added, the listener may be submitted to run after commit yet still suffer submission errors, shutdown, or insufficient concurrency; a dedicated policy is needed.

## 8. Subtle Warning: Transaction Resources May Still Be Bound After Commit

The Spring Javadoc notes an important caveat: during `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`, the DB transaction has finished, **yet resources bound to the transaction may still be active/bound to the thread** during the callback phase.

Consequence: if the listener invokes DB code that re-joins the old resource, a write operation might think it is still inside a transaction and **fail to commit as you expect** because the main commit already happened. Do not infer that `AFTER_COMMIT` automatically creates a new transaction for every repository call.

If the callback must **write new durable state after commit**, invoke another service bean with a genuinely new transaction:

~~~java
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordSent(long orderId) {
        auditRepository.insert(orderId);
    }
}
~~~

This is an **integration snippet** requiring `@Service`, `@Transactional`, `Propagation`, `auditRepository`, and a suitable transaction manager. The caller must invoke it **through the Spring-managed proxy of another service**; calling `this.recordSent(...)` inside the same bean normally bypasses advice in proxy mode.

However, `REQUIRES_NEW` only creates a new DB transaction; it does **not** solve the whole problem of sending a message to a broker exactly once. If a crash occurs between committing the order and writing the new audit/event record, a window for lost operations still exists. Critical workflows should consider a **transactional outbox**.

In the Section 6 demo, the post-commit listener **only reads through an independent connection** and does not write on the old resource; that intentionally avoids the pitfall above.

## 9. Distinguishing Right Timing From Guaranteed Event Delivery

There are two completely different questions:

1. **Will the consumer run before the DB commits?** Using `AFTER_COMMIT` can ensure an **in-process callback** is invoked after a successful commit, solving this internal race.
2. **Is the event guaranteed to be saved/delivered to the consumer after commit?** Not necessarily. After the DB commits but before durable message sending succeeds, the JVM may crash, the broker may reject the message, or the network may time out. The DB has the order, yet there is no corresponding event.

Another timeline:

~~~text
BEGIN DB transaction
INSERT order 42
COMMIT succeeds       <-- data is now durable
    |
    +-- JVM crash / broker unavailable
    |
    +-- publish event never completed
        --> consumer is never notified without recovery
~~~

Therefore, `@TransactionalEventListener(AFTER_COMMIT)` is useful for **auxiliary events, local processing, or best-effort notifications that can tolerate loss or be recovered**, yet **it is not a mechanism guaranteeing durable event delivery between a DB and a broker**.

Even when the send call inside the callback succeeds, states such as "broker received it but ACK was lost" or "consumer processed it and crashed before acknowledging" remain; proper design handles **duplicates** rather than assuming end-to-end exactly-once by default.

## 10. Transactional Outbox: Writing Data and Event Intent in One Commit

For business requirements where **creating an order successfully must produce a corresponding event**, a common pattern is the **transactional outbox**:

- Inside **the same DB transaction**, write the business record to `orders` and write an event record to an `outbox_events` table.
- **Only after commit**, a poller or CDC connector picks up committed outbox records to send to the broker.
- If the transaction rolls back, both the order and the event record roll back.
- If the app crashes after commit but before sending to the broker, the outbox record still exists and can be resent.
- Because the poller may resend on lost ACKs, the consumer must be **idempotent**.

Typical flow:

~~~text
Producer transaction T1
   |
   +-- INSERT orders(id=42,...)
   +-- INSERT outbox_events(event_id=E-1, aggregate_id=42,...)
   |
   +-- COMMIT atomically
             |
             v
  Poller/CDC sees only committed outbox rows
             |
             v
       Message broker
             |
             v
  Consumer receives event and reads state/order
             |
             +-- Dedupe event_id + apply idempotently
~~~

**Outbox closes the dual-write gap**, because the intent to publish an event lives in the same transaction as the data. It does not force Kafka, RabbitMQ, or the DB into a single global transaction. However, it **does not eliminate duplicates**, does not guarantee strict global ordering across multiple aggregates, and does not eliminate replication lag on consumers reading a slow replica.

## 11. Example Outbox Design in Spring

Illustrative schema **using PostgreSQL SQL** (not a portable schema for every engine):

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL
);
~~~

A Spring `@Transactional` method can write to both tables:

~~~java
@Service
public class OrderCommandService {
    private final JdbcTemplate jdbc;

    public OrderCommandService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void create(long orderId, String eventJson, UUID eventId) {
        jdbc.update(
            "insert into orders(id, status) values (?, ?)",
            orderId, "NEW");

        jdbc.update(
            "insert into outbox_events" +
            "(event_id, aggregate_id, event_type, payload) " +
            "values (?, ?, ?, ?)",
            eventId, orderId, "OrderCreated", eventJson);
    }
}
~~~

This is an **integration snippet**: it requires `JdbcTemplate`, `UUID`, `@Service`, `@Transactional` imports; datasource, migrations, and JSON serializer are provided by the application. It is not a standalone runnable Java file.

Both `jdbc.update` calls must use **the same transaction manager and the same physical DB transaction**, invoking the method through a Spring transaction proxy. If the outbox statement fails and the exception propagates to the interceptor per rollback rules, the order also rolls back. If commit succeeds, the poller can read both the order and the outbox row.

A production schema also needs polling indexes, lease/retry state, delivery attempt counts, last error, tenant/correlation IDs, schema version, retention policies, and payload security. Do not leak secrets or sensitive PII into a broker uncontrolled.

**Do not call `broker.send` directly between two INSERTs inside a transaction** and treat that as part of the same atomic commit: the broker does not automatically join a DB transaction.

## 12. Poller, CDC, and Outbox Limitations

There are two common ways to dispatch outbox events:

**Poller:** a worker periodically fetches unsent rows, claims/locks a bounded batch, publishes messages, and updates status. With multiple instances, you need a DB-level lease/lock mechanism (e.g., `FOR UPDATE SKIP LOCKED` in PostgreSQL inside a short transaction) to prevent concurrent workers from picking the same rows uncontrollably.

**CDC (change data capture):** a connector reads committed changes from the DB's transaction log and turns outbox rows into messages. Debezium Outbox Event Router is one example solution.

Both still must handle:

- Unresponsive broker, poller restarts, or failures in the transaction updating `published_at`.
- Broker **received** the message but the ACK was lost, so the poller resends the same `event_id`.
- Messages sent/stored on the wrong partition; events for the same aggregate can arrive out of order without proper partition keys and versioning.
- Backpressure: slow consumer processing causes outbox backlog growth; track lag metrics, pending event counts, retries, and a dead-letter strategy.
- Purge/retention: do not delete outbox rows before ensuring they are no longer needed for recovery; verify retention contracts and manage archiving.

If production truly needs an *exactly-once effect* on business state, this usually has to be achieved via **idempotent consumers, consumer-side transactions, and deduplication**, rather than expecting the broker never to redeliver.

## 13. Post-Commit Consumers Still Face Eventual Consistency

Even when the producer writes an outbox and commits before the message is sent, a consumer may read a **lagging read replica**, a stale cache, or an unupdated search projection. The event is valid, yet the data store the consumer queries has not caught up.

Strategies depending on needs:

1. **Include a minimal snapshot in the event:** if the consumer only needs `orderId`, `status`, and `total` at commit time, include those fields (sanitized and privacy-checked) in the payload instead of forcing the consumer to query the producer's DB every time.
2. **Read-your-writes / primary read:** for data that must be up to date, the consumer can call an API reading from the primary (if permitted) rather than a lagging read replica.
3. **Version/sequence:** attach `aggregateVersion` so the consumer knows which state version it is handling; prevent stale events from overwriting newer projections.
4. **Bounded retry with jitter:** if a read API temporarily misses a row due to replication lag, bounded retries with a deadline can make sense. Do not turn "not found" into an infinite retry loop.
5. **Reconciliation:** run a reconciliation job comparing producer and consumer data to repair failed, lost, or drifted projections.

An "order created" event is a **point-in-time business fact**, not a guarantee that the entity stays in state `NEW` forever. By the time the consumer reads, the order may already have moved to `PAID` or `CANCELLED`. If you need the state "at emission time", send the appropriate payload/version instead of treating every current read as the state at event time.

## 14. Consumer-Side Idempotency and Event Ordering

**Idempotency:** for each event, the producer should generate a stable `eventId`. The consumer records processed events or uses a unique constraint / business key so delivering the same event twice does not apply side effects twice.

A consumer flow based on a DB transaction:

~~~text
BEGIN
  INSERT processed_events(consumer_id, event_id)
      -- unique(consumer_id, event_id)
  IF duplicate:
      -- skip duplicate business effect
  ELSE:
      UPDATE projection / apply internal side effect
COMMIT
ACK message after DB commit
~~~

This is a **logic diagram**, not verbatim runnable SQL. Inserting the dedupe marker and updating business state should happen in **the same consumer transaction**. If ACK is sent before commit, a crash between the two steps can cause the consumer to lose the effect. If commit succeeds but ACK is lost, the broker may redeliver; deduplication handles the duplicate.

For emails or payments in **systems outside the consumer's DB**, a local transaction cannot cover external side effects. You need external API idempotency keys, outbox/saga patterns, and reconciliation when outcomes are uncertain.

**Ordering:** `OrderCreated`, `OrderPaid`, and `OrderCancelled` may arrive out of order across partitions or retries. If state transitions require strict order, route events for the same aggregate to a consistent partition key and check `aggregateVersion`, or build out-of-order handling rules. "Publish after commit" does not automatically guarantee ordering across a distributed system.

## 15. @Async and Transaction Context: Two Things That Do Not Cross Threads Automatically

An easily spotted anti-pattern in Spring:

~~~java
@Transactional
public void createOrder(Order order) {
    repository.save(order);
    asyncNotifier.notifyCreated(order.getId());
    // The caller's transaction may still be uncommitted.
}

@Async
public void notifyCreated(Long orderId) {
    // Running on a different thread.
    externalConsumerOrDbRead(orderId);
}
~~~

This is an **illustrative integration snippet**, not a standalone Java class. If the `@Async` method is invoked through a proxy, the executor may start running as soon as it is submitted, **before the caller's transaction commits**.

Spring's imperative transaction is thread-bound: the worker does not automatically share the producer's open transaction. That is why adding `@Async` does not make events "safer"; it usually makes the race more obvious.

Also avoid passing a managed Hibernate/JPA entity or lazy-loaded proxy into an async event and assuming the consumer can access every property. The session/transaction may close; the object state may be mutable, lazily initialized, or inconsistent. Use an **immutable event payload** containing IDs, versions, required fields, or a well-defined DTO snapshot.

If you want to process **after commit without blocking the committing thread**, you can use a `@TransactionalEventListener(AFTER_COMMIT)` listener that triggers a concurrency-bounded async task. This solves internal task start ordering, yet still carries risks **between commit and enqueue/persistence**; for events that must be delivered, an outbox is usually more appropriate.

## 16. Exceptions and Rollback: Do Not Mistake Publish Success for Commit Success

A `@Transactional` method might publish an event and then throw an exception at the end:

~~~java
@Transactional
public void createOrder(long id) {
    repository.insert(id);
    publisher.publishEvent(new OrderCreated(id));
    if (businessRuleRejected(id)) {
        throw new IllegalStateException("Rejected");
    }
}
~~~

This is an illustrative snippet, not a standalone runnable class. With default rollback rules for unchecked exceptions and a suitable transaction manager, the database insert may roll back. However, a regular event published beforehand **cannot be recalled** if a consumer already received it or a broker already persisted the message.

When using `@TransactionalEventListener(AFTER_COMMIT)`, the callback does not run if the producer transaction rolls back properly. Still, you must understand actual rollback rules:

- Checked exceptions do not trigger rollback by default in the same way as unchecked exceptions unless configured.
- If code catches the exception and finishes normally, the transaction may commit unless `setRollbackOnly()` or another configuration applies.
- Participating in an existing transaction and `Propagation.REQUIRES_NEW` change commit boundaries.
- Self-invocation of `@Transactional` in proxy mode can bypass transaction advice.
- Only when **a single transaction truly encompasses** the writes does commit yield the expected visibility.

Saying "the method finished running" is not enough; verify which transaction actually committed and when. With `TransactionTemplate`, the transaction callback only returns after the template-managed transaction finishes committing or rolling back.

## 17. Testing Properly: Observing From Another Transaction/Connection

Tests that only assert `repository.save()` or call `findById()` in the same transaction do not prove external consumers see committed data. A proper integration test needs:

1. **Real primary DB and real transactions:** test under `READ_COMMITTED` or the target isolation level, not a mocked `EntityManager`.
2. **Independent connection:** producer holds an uncommitted transaction while the consumer queries via another connection or thread, confirming the row is not visible before commit.
3. **After commit:** commit the producer and re-query in a new read transaction, confirming the row is visible.
4. **Rollback:** force the transaction to roll back; the `AFTER_COMMIT` listener does not run and the consumer never sees the uncommitted row.
5. **Controlled race:** use a `CountDownLatch` to pause the producer before commit; trigger the consumer before/after via latches. Do not rely on `Thread.sleep(10)` hoping timing lines up.
6. **Spring proxies:** test `@Transactional` and `@Async` across Spring-managed beans; `this.method()` can disable advice.
7. **Transaction event factory:** enable `@EnableTransactionManagement` in Framework tests or equivalent config; confirm the listener executes in the right phase.
8. **Post-commit event loss:** simulate broker/poller unavailability after commit; if using an outbox, verify the row persists and can be redelivered.
9. **Duplicates:** deliver the same `eventId` twice; verify the consumer does not apply duplicate business effects.
10. **Replica lag and out-of-order:** expose the consumer to an older snapshot or deliver a newer version first; verify retry/version logic does not overwrite valid state.

When placing `@Transactional` on a **test method** (such as Spring Test's `@Transactional`) where the framework automatically rolls back at the end of the test, `AFTER_COMMIT` listeners may **not run**. That is why you need a test that explicitly controls real commits using `TransactionTemplate` or an appropriate test transaction API.

In the Section 6 demo, commit is controlled explicitly so it is not masked by a test framework's default transaction rollback.

## 18. Diagnosing Production With Logs and Metrics

Maintain correlation across producer -> outbox/broker -> consumer:

| Field | Meaning |
| --- | --- |
| `eventId` | Unique key for deduplication and retry tracing |
| `aggregateId` | Related order/customer/business resource |
| `aggregateVersion` | Used to check ordering and stale projections |
| `producedAt` | Logical time the event was created; **does not** replace commit timestamp |
| `outboxCommittedAt` or `createdAt` | Helps estimate lag, understanding how DB/clock records it |
| `publishedAt` | Time broker send/ACK was recorded per policy |
| `consumedAt` | Time consumer started/finished processing |
| `traceId` | Links requests and background processing without raw PII |

Essential metrics: pending events in outbox, **oldest pending age**, publish retries, broker acknowledgement failures, duplicate events, consumer processing latency, row-not-found after event, replication lag, and dead-letter count. Avoid using raw eventId/orderId as high-cardinality metric labels; use logs or access-controlled tracing instead.

If consumers frequently encounter `not found` immediately after an event, check **publish timing relative to commit**, isolation, read-replica routing, and the consumer's transaction snapshot. Increasing retry counts may only mask the race and heat up the DB.

## 19. Reliability Selection Matrix

| Requirement | Approach | Contract and limitations |
| --- | --- | --- |
| Internal listener only needs to observe post-commit events | `@TransactionalEventListener(AFTER_COMMIT)` | Right phase; does not guarantee events survive crashes |
| Non-critical async notification that can be regenerated | `AFTER_COMMIT` then submit task to a bounded executor | Crash/rejection risk after commit; requires monitoring |
| Broker must receive an event for every committed order | Transactional outbox + poller/CDC | Atomic DB state+intent; idempotent consumer, retry monitoring |
| Consumer reads lagging replicas/projections | Payload/version + read policy + bounded retry/reconciliation | Eventual consistency still applies after commit |
| Multiple producers or complex broker ordering | Aggregate version/partitioning + idempotency | Do not infer global order from local commits |
| Cross-service state updated across multiple steps | Saga/workflow and compensation, per-stage outbox if needed | No single local DB transaction covers the entire system |

No single solution fits every workload. **Define the business contract first**: whether event loss is acceptable, what payload the consumer needs, how fast responses must be, how to recover from crashes, and what level of duplicates/out-of-order delivery must be handled.

## 20. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "`repository.save()` returned, so the DB definitely committed." | The operation may still sit inside an uncommitted transaction. |
| "`publishEvent()` waits for the transaction to finish by default." | Regular listeners can execute immediately inside the open transaction. |
| "If the listener can read the row, other consumers can too." | The listener may be using **the producer's own connection/transaction**. |
| "Marking the listener `@Async` prevents races." | Async decouples scheduling; it can still run before commit. |
| "`@TransactionalEventListener` runs even without a transaction." | It does not run by default; `fallbackExecution=true` is required to allow that. |
| "`AFTER_COMMIT` is a new transaction." | Old resources may remain bound; writing new data may require `REQUIRES_NEW`. |
| "`AFTER_COMMIT` guarantees Kafka always gets the message." | There is a crash window between DB commit and broker publish. |
| "Outbox means consumers never receive duplicates." | Poller/CDC/broker can redeliver; idempotency is required. |
| "After commit, replicas update instantaneously." | Replicas, caches, and projections can lag. |
| "An event always describes the current state when the consumer reads it." | State may already have advanced to a newer version. |
| "The producer's transaction propagates to `@Async` workers." | Imperative transactions are thread/context-bound and do not transfer automatically. |
| "Retrying `not found` indefinitely is safe enough." | It may be a rollback, wrong ID, missing outbox, or duplicate side effects; retries must be bounded. |

## 21. Pre-Implementation Design Checklist

- I know **where the producer transaction opens and when it commits**, with a genuine `@Transactional` proxy and proper rollback rules.
- I do not emit events to independent consumers before commit when consumers depend on committed state.
- I distinguish `@EventListener`, `@TransactionalEventListener(AFTER_COMMIT)`, and `@Async`.
- I verify transactional listeners run only when a transaction is present (or fallback is chosen deliberately).
- I understand `AFTER_COMMIT` does not create a new transaction; writes inside callbacks need an appropriate boundary.
- I have determined whether **losing an event after DB commit** is acceptable; if not, I use an outbox/CDC or equivalent durable mechanism.
- Consumers have `eventId`/business-key deduplication and enough metadata to handle out-of-order delivery.
- I verified whether consumers read primary, replicas, or caches and have a strategy for replication lag.
- I bound retries, backpressure, and queue concurrency, and have dead-letter/reconciliation handling.
- I verified events carry immutable contract payloads rather than depending on managed JPA entities or lazy sessions.
- I have integration tests using two connections with real commits and rollbacks, not just mocks.
- I track outbox lag, broker publish failures, consumer processing, duplicates, and "row not found" errors with appropriate metrics and logs.

**Conclusion:** When a producer publishes an event before its SQL transaction commits, independent consumers may observe stale or nonexistent data; events may also describe rolled-back state. `@TransactionalEventListener(AFTER_COMMIT)` solves **callback ordering relative to commit** inside Spring. If business requirements also demand **no lost events after commit**, persist **business state and event intent in the same DB transaction** (transactional outbox), dispatch via poller/CDC, and handle duplicates on the consumer. Even after commit, read replicas and caches still require an eventual consistency policy.

## References

- [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — transaction-phase events, fallbackExecution, imperative/reactive context.
- [Spring Framework 6.2: TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — default AFTER_COMMIT, AFTER_ROLLBACK, resources still bound after completion.
- [Spring Framework 6.2: TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionPhase.html) — semantics of BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION.
- [Spring Framework: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — proxies, rollbacks, transaction boundaries.
- [Spring Framework: Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — `ApplicationEventPublisher` and event listeners in the Spring context.
- [Spring Framework: TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — afterCommit/afterCompletion, warning that new writes need a separate transaction.
- [Debezium: Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html) — one way to turn outbox rows into messages via CDC.

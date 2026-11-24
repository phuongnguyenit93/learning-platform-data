# Updating Read Models After Domain Changes in Spring Framework Application Events

## 1. Why Do We Need a Separate Read Model?

A Spring application can use a **domain model** to execute business operations while using a **read model** (projection/query model) to serve lookup screens. The two models solve different needs.

- **Write/domain model** represents aggregates, invariants, and valid state transitions. For example, `Order.markPaid(...)` must validate the transaction and prevent rule-breaking operations.
- **Read model** is a denormalized table/document/dataset optimized for querying, pagination, dashboards, or search. For example, `OrderOverview` contains `orderId`, `customerName`, `status`, `total`, `paidAt`, and `lastVersion`.
- **Domain event** describes a fact after a valid change, such as `OrderPaid(orderId, paymentId, version)`.
- **Projection handler** consumes events and updates the read model.
- **Query service** reads the read model instead of having to load multiple aggregates and run complex joins on every request.

This is a **lightweight CQRS** pattern: separating command/write responsibilities from query/read responsibilities. You do not necessarily need two databases, Kafka, or a microservices architecture. A monolith using Spring Framework and two tables in the same database can apply it too.

**Goal of this guide:** Understand how to turn a domain change into an event, update a projection after commit, handle rollbacks, duplicate or out-of-order events, and choose the right consistency level. The guide includes a complete Java 17+ example using Spring JDBC and H2.

~~~text
Command: PayOrder
      |
      v
Application service / transaction
      |
      v
Order aggregate: CREATED -> PAID
      |
      +---- Save domain data
      |
      +---- OrderStateChanged(orderId, state, version)
                          |
                          v
                Projection listener
                          |
                          v
                   OrderOverview
                          |
                          v
                Query API / dashboard
~~~

**Do not confuse publishing an event with the read model already being updated.** The read model can be updated in the same transaction, right after commit, or asynchronously via a broker; each option has different consistency guarantees and failure modes.

## 2. Which Domain Events Should Trigger Projections?

An event useful for a read model should have clear business meaning and carry enough data to update the projection.

Example:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long aggregateVersion) {}
~~~

The record above is **plain Java**, not a Spring `ApplicationEvent` subclass. Spring can publish POJOs as event payloads. However, the domain does not need to know about Spring; an application adapter can publish the event or write to an outbox inside the transaction.

Fields to consider:

| Field | Why Is It Needed? |
| --- | --- |
| **eventId** | Identify redeliveries/duplicates when using an outbox or broker |
| **aggregateId** | Locate the exact row/document to update |
| **aggregateVersion** | Prevent stale events from overwriting newer state |
| **eventType** | Distinguish `OrderPlaced`, `OrderPaid`, `OrderRefunded` |
| **occurredAt** | Display business time and measure projection lag |
| **payload snapshot/delta** | Specify the fields being updated |
| **schemaVersion** | Manage compatibility between producer and consumer versions |
| **correlationId** | Tie commands, events, and projections to the same workflow |

**Do not put an entire mutable JPA entity or lazy-loaded proxy into an event** and carry it across an async boundary. Pass the identity and required immutable data instead; event data must have an explicit schema contract.

An event like **OrderPaid** is a fact; **PaymentRequested** is a request. Do not rename them arbitrarily in a way that blurs commands with completed events.

## 3. Choosing a Synchronization Strategy Before Writing Listeners

### 3.1. Updating the Write and Read Models in the Same Transaction

~~~text
BEGIN TRANSACTION
   validate domain rules
   update orders
   update order_overview
COMMIT
~~~

When the read model lives in the **same database**, strong read-after-write consistency is needed, and the projection is simple, this can be the best choice. Domain state and read model commit together or roll back together.

Pros: no commit gap between the two tables. Cons: the command path takes on the additional write cost, locks, and schema coupling of the projection; updating a different datastore cannot participate in this local transaction.

You can call the projection component directly in the application service instead of using an event. **Do not force event-driven style just because `@EventListener` exists** if an explicit call protects invariants better.

### 3.2. Using Synchronous @EventListener Immediately Upon Publish

~~~java
@EventListener
public void on(OrderPaid event) {
    projector.apply(event);
}
~~~

This is an **illustrative snippet**, requiring a Spring-managed bean, event definition, and projector. With the default **SimpleApplicationEventMulticaster**, the listener can be called **before commit**, right when the service calls **ApplicationEventPublisher.publishEvent(...)**. If the listener writes to another system and the domain transaction rolls back, the projection may reflect a business event that never actually committed.

A synchronous listener writing to the **same DB transaction** can provide atomicity, but you must verify transaction boundaries, multicaster configuration, and ordering. An executor/`@Async` configuration will invalidate the "same thread, same transaction" assumption.

### 3.3. @TransactionalEventListener(AFTER_COMMIT)

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaid event) {
    projector.apply(event);
}
~~~

This is a snippet. Spring triggers the handler when the transaction bound to the event **commits successfully**. If the transaction rolls back, the `AFTER_COMMIT` callback is not invoked. By default **`fallbackExecution=false`**: events published outside an active matching transaction are ignored by the transactional listener.

**Crucial point:** the **AFTER_COMMIT** callback runs after the main transaction has committed, but transaction resources may still be bound to the thread. If the code continues writing to the database without opening a **new transaction**, changes may not be committed. When updating a read model after commit, use **PROPAGATION_REQUIRES_NEW** via a Spring-managed service proxy or `TransactionTemplate`, as shown in Section 6.

`AFTER_COMMIT` is **not atomic** with the domain commit. If the JVM dies or the projector fails after commit, the domain has changed while the projection may stay stale. You need a recovery mechanism when the read model is critical.

### 3.4. Outbox + Consumer: Eventually Consistent Updates

~~~text
BEGIN WRITE DB TRANSACTION
    update orders
    insert outbox(OrderPaid)
COMMIT
      |
      v
Outbox relay / CDC
      |
      v
Durable broker / message transport
      |
      v
Idempotent projection consumer
      |
      v
Read database / search index
~~~

The **transactional outbox** keeps business state and the intent to emit an event in the same commit. The relay can re-read events after a crash and retry delivery. The consumer reads messages and updates the read model in its own transaction.

Pros: decouples command from query infrastructure, recovers across restarts, and scales to multiple consumers. Cons: **eventual consistency**, operating relay/broker infrastructure, duplicate or out-of-order events, schema migrations, and backlog management. **Outbox + retry is typically at-least-once**, with no automatic end-to-end exactly-once guarantee.

### 3.5. Comparison

| Criterion | Same DB Transaction | In-Process AFTER_COMMIT | Outbox + Consumer |
| --- | --- | --- | --- |
| Projection ready as soon as write commits | Yes, if writes share the TX | Not guaranteed before commit; usually updated right after | No; read side may lag |
| Domain rollback | Both roll back together | Commit callback is skipped | Outbox also rolls back with domain |
| Process dies after commit | Both tables already committed | Callback may be lost | Outbox survives if DB is durable |
| Read model in a different database | Cannot easily share local TX | Can call, but not durable | Suitable |
| Ordering and duplicates | Minimal issue within one transaction | Must check if replaying | Must design idempotency/ordering |
| Query SLA | Easy read-after-write | May require waiting state | Needs lag budget/watermark |
| Complexity | Lower | Medium | Higher: relay, retry, monitoring |

**Choose by data contract first, tools second.** Not every projection needs Kafka; nor is every lagging read model wrong.

## 4. Designing the Write Model and Read Model

Suppose the command side has the table:

~~~sql
CREATE TABLE domain_orders (
    order_id VARCHAR(80) PRIMARY KEY,
    state VARCHAR(30) NOT NULL,
    row_version INTEGER NOT NULL
);
~~~

The read side has a table optimized for queries:

~~~sql
CREATE TABLE order_overview (
    order_id VARCHAR(80) PRIMARY KEY,
    state VARCHAR(30) NOT NULL,
    row_version INTEGER NOT NULL
);
~~~

The demo uses minimal columns to clearly show transactions and version guards. A production read model typically adds `customerDisplayName`, `itemCount`, `totalMinorUnits`, `paidAt`, `shippingStatus`, and indexes tailored to real query patterns.

**`row_version` in the read model** indicates which version of the domain aggregate the row has materialized. It prevents old events from overwriting newer ones and lets clients know whether the query side has caught up to `expectedVersion`.

### Snapshot vs. Delta

- **Snapshot event** contains the new state, e.g., `OrderOverviewChanged(orderId, status, version)`. The projection can apply it idempotently by setting the fields if the event is newer.
- **Delta event** contains the change, e.g., `OrderItemAdded(orderId, itemId, quantity, version)`. Adding to `itemCount` or `total` multiple times due to redelivery produces wrong results; this requires a processed-event ledger and strict ordering.
- **ID-only event** forces the projector to query the write model for current state. This is simple for a current-state read model, but does not guarantee step-by-step historical event replay will yield exact intermediate results.

If you need to rebuild projections from an event log, payloads must carry sufficient data or have an appropriate snapshot/history source. Do not assume an ID-only event lets you reconstruct lost historical states.

## 5. When Is an Event Published During a Use Case?

Applications typically publish events using one of these patterns:

**Pattern A — Application service publishes after the domain mutation is accepted:**

~~~java
@Transactional
public void payOrder(String orderId, String paymentId) {
    Order order = orders.load(orderId);
    order.markPaid(paymentId);
    orders.save(order);
    publisher.publishEvent(
            new OrderPaid(newEventId(), orderId, paymentId,
                          order.version()));
}
~~~

This snippet omits full imports/classes. When using an `AFTER_COMMIT` listener, publication happens **inside the active transaction** so Spring registers the callback. When using an outbox, you must **write the outbox record inside the same transaction**, rather than relying solely on `publishEvent`.

**Pattern B — Aggregate collects domain events:**

~~~text
Order.markPaid()
  -> mutate aggregate
  -> record OrderPaid in pendingEvents
Application service
  -> save aggregate and persist outbox events in the same transaction
  -> clear published/persisted pendingEvents according to contract
~~~

This model keeps the domain framework-independent. You must define when to clear pending events; do not clear events from the aggregate and then let the transaction/outbox fail with no way to retry within the same unit of work.

Spring Data provides the **@DomainEvents** mechanism on aggregates to collect/publish events during corresponding repository operations. However, **@DomainEvents** by itself does not create a durable outbox or guarantee post-commit listeners; you must verify the exact lifecycle of your repository, transaction, and application configuration.

## 6. Runnable Java 17+ Example: Domain Commit Followed by Read Model Update

The demo uses **Java 17+**, **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, and **Gradle 8.x**. No Spring Boot, broker, or web server is needed.

Objectives:

1. `TransactionTemplate` persists domain state and publishes the event.
2. The **@TransactionalEventListener(AFTER_COMMIT)** listener handles it only after a successful commit.
3. The projector uses **REQUIRES_NEW** when writing the read model in the post-commit callback.
4. A rolled-back transaction produces no projection.
5. Re-sending an older or same-version event does not overwrite newer state.

The demo uses an **in-memory** H2 database and a **single synchronous worker**; it does not prove multi-consumer race safety or crash recovery. Use an outbox if events must survive restarts.

### 6.1. Directory Structure

~~~text
read-model-demo/
  build.gradle
  src/main/java/demo/ReadModelDemo.java
~~~

File **build.gradle**:

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
    mainClass = 'demo.ReadModelDemo'
}
~~~

### 6.2. Complete Java File

File **src/main/java/demo/ReadModelDemo.java**:

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class ReadModelDemo {

    public record OrderStateChanged(
            String orderId, String state, int version) {}

    public static final class Commands {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Commands(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        public void change(
                String id, String newState, int version, boolean rollback) {
            tx.executeWithoutResult(status -> {
                if (version == 1) {
                    db.update(
                        "INSERT INTO domain_orders "
                        + "(order_id, state, row_version) "
                        + "VALUES (?, ?, ?)",
                        id, newState, version);
                } else {
                    int changed = db.update(
                        "UPDATE domain_orders "
                        + "SET state = ?, row_version = ? "
                        + "WHERE order_id = ? AND row_version = ?",
                        newState, version, id, version - 1);
                    if (changed != 1) {
                        throw new IllegalStateException(
                            "invalid domain transition");
                    }
                }

                publisher.publishEvent(
                    new OrderStateChanged(id, newState, version));

                System.out.println(
                    "domain: " + id + "=" + newState + " v" + version);

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }

        public void replay(
                String id, String state, int version) {
            // Replay/duplicate solely to test the projector.
            tx.executeWithoutResult(status ->
                publisher.publishEvent(
                    new OrderStateChanged(id, state, version)));
        }
    }

    public static final class Projector {
        private final JdbcTemplate db;
        private final TransactionTemplate writeReadModelTx;

        public Projector(
                JdbcTemplate db, PlatformTransactionManager manager) {
            this.db = db;
            this.writeReadModelTx = new TransactionTemplate(manager);
            this.writeReadModelTx.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        }

        public void apply(OrderStateChanged event) {
            writeReadModelTx.executeWithoutResult(status -> {
                List<Integer> versions = db.query(
                    "SELECT row_version FROM order_overview "
                    + "WHERE order_id = ?",
                    (rs, row) -> rs.getInt("row_version"),
                    event.orderId());

                if (!versions.isEmpty()
                        && versions.get(0) >= event.version()) {
                    System.out.println(
                        "projection: ignored "
                        + event.orderId() + " v" + event.version());
                    return;
                }

                if (versions.isEmpty()) {
                    db.update(
                        "INSERT INTO order_overview "
                        + "(order_id, state, row_version) "
                        + "VALUES (?, ?, ?)",
                        event.orderId(), event.state(), event.version());
                } else {
                    int updated = db.update(
                        "UPDATE order_overview "
                        + "SET state = ?, row_version = ? "
                        + "WHERE order_id = ? AND row_version < ?",
                        event.state(), event.version(),
                        event.orderId(), event.version());

                    if (updated != 1) {
                        System.out.println(
                            "projection: ignored "
                            + event.orderId() + " v" + event.version());
                        return;
                    }
                }

                System.out.println(
                    "projection: applied "
                    + event.orderId() + "=" + event.state()
                    + " v" + event.version());
            });
        }

        public String find(String id) {
            List<String> rows = db.query(
                "SELECT state, row_version FROM order_overview "
                + "WHERE order_id = ?",
                (rs, row) -> rs.getString("state")
                        + " v" + rs.getInt("row_version"),
                id);
            return rows.isEmpty() ? "none" : rows.get(0);
        }
    }

    public static final class ProjectionListener {
        private final Projector projector;

        public ProjectionListener(Projector projector) {
            this.projector = projector;
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void on(OrderStateChanged event) {
            projector.apply(event);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:read_model_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS domain_orders ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "state VARCHAR(30) NOT NULL, "
                + "row_version INTEGER NOT NULL)");
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS order_overview ("
                + "order_id VARCHAR(80) PRIMARY KEY, "
                + "state VARCHAR(30) NOT NULL, "
                + "row_version INTEGER NOT NULL)");
            return jdbc;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        Projector projector(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new Projector(jdbc, manager);
        }

        @Bean
        ProjectionListener projectionListener(Projector projector) {
            return new ProjectionListener(projector);
        }

        @Bean
        Commands commands(
                JdbcTemplate jdbc,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Commands(jdbc, manager, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Commands commands = context.getBean(Commands.class);
            Projector projector = context.getBean(Projector.class);

            commands.change("A", "CREATED", 1, false);
            commands.change("A", "PAID", 2, false);
            commands.change("B", "CREATED", 1, true);

            commands.replay("A", "CREATED", 1);
            commands.replay("A", "PAID", 2);

            System.out.println("query A: " + projector.find("A"));
            System.out.println("query B: " + projector.find("B"));
        }
    }
}
~~~

Run from the **read-model-demo** directory:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program itself**, ignoring any other Gradle/environment logs:

~~~text
domain: A=CREATED v1
projection: applied A=CREATED v1
domain: A=PAID v2
projection: applied A=PAID v2
domain: B=CREATED v1
projection: ignored A v1
projection: ignored A v2
query A: PAID v2
query B: none
~~~

### 6.3. Explaining the Output

- **A v1:** the transaction writes the domain order and publishes **OrderStateChanged(A, CREATED, 1)**. The domain log line happens inside the transaction. After commit, Spring triggers the listener; the projector opens a **REQUIRES_NEW** transaction and writes read row version 1.
- **A v2:** the command updates the domain from version 1 to 2, writing `PAID`; after commit the projector applies the new version because version 2 is greater than 1.
- **B v1:** the command writes the domain and publishes the event, then sets rollback-only. The domain insert for B rolls back, **the AFTER_COMMIT listener does not run**, so the read model does not contain B.
- **Replay v1:** a separate transaction simply replays the old event. The projector sees read version 2 and ignores stale v1.
- **Duplicate v2:** the projector sees the read model is already at version 2 and ignores the same-version event.
- Finally, **query A** returns **PAID v2**, while **query B** has no row.

This is an example for **one worker, one database, two transactions**. There is no broker/outbox, so if the JVM dies after the domain commit before writing the projection, the update can be lost. Do not turn this code directly into a production relay.

### 6.4. Why Must the Projector Open a New Transaction?

According to the **@TransactionalEventListener** Javadoc, when `AFTER_COMMIT` runs, the main transaction has completed, yet resources may still be accessible. A `JdbcTemplate`/repository call without opening a new transaction may join the old resources and **fail to commit**. The demo uses:

~~~java
this.writeReadModelTx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

An alternative is calling a method on a **Spring-managed service** annotated with **@Transactional(propagation = Propagation.REQUIRES_NEW)** through a Spring proxy. Do not use self-invocation and assume the advice/interceptor will still apply.

## 7. Preventing Duplicate and Out-of-Order Processing

### 7.1. Version Guard for Snapshot Projections

Suppose there are events:

~~~text
OrderCreated v1
OrderPaid v2
OrderRefunded v3
~~~

If the projector receives **v3 before v2**, a sufficiently complete current-state snapshot can be applied whenever its version exceeds the stored version. When v2 arrives later, ignore it so newer state is not overwritten.

However, with **delta events** such as **LineItemAdded(+2 items)** or **BalanceIncremented(+100)**, skipping an older event can yield wrong totals. Delta projections need to store processed event IDs/sequences, apply every change properly, or provide a rebuild path.

### 7.2. Deduplication by Event ID

An at-least-once consumer typically needs:

~~~text
BEGIN consumer DB transaction
  INSERT processed_events(consumer_name, event_id)
  if event_id already exists:
      skip business effect
  if new:
      update read model
COMMIT
ACK broker
~~~

**The processing marker and the read model update must share the same local transaction**, with an appropriate unique constraint. Do not commit the marker first and update the read model in a separate transaction, because a crash between the two steps causes retries to be skipped and the projection never finishes.

An event with multiple distinct projectors must deduplicate by **(consumerName, eventId)** or an equivalent key. Do not use a single global processed flag that blocks other legitimate subscribers.

### 7.3. Concurrent Workers

The demo uses **SELECT row_version then INSERT/UPDATE**, which suffices for illustrating a single worker. Multiple workers, however, could simultaneously see no existing row or read the same old version. Production requires:

- **Unique key** on the projection identity.
- **Atomic conditional upsert/compare-and-set** appropriate to your SQL dialect.
- **Row locking / optimistic locking**, conflict retries, or single-writer partitioning by aggregate.
- **Ordering keys** and checkpoints if events require sequential processing.
- Integration tests with concurrency/race injection.

Do not treat a version check in Java memory as sufficient synchronization when multiple consumers run concurrently.

## 8. Query API and Eventual Consistency

A user executes **PayOrder** and immediately calls the query endpoint. With async projections, the domain is already `PAID` while the read model may still be `CREATED`. This is **read-model lag**, not necessarily a failed payment.

Better contracts:

1. **Return `expectedVersion` from the command:** the client receives the newly committed version.
2. **Expose `projectionVersion`:** the query returns the version the read model has applied.
3. **Poll with timeout/backoff:** wait until `projectionVersion` reaches `expectedVersion`, or display "syncing."
4. **Read-your-writes fallback:** if an immediate fresh response is mandatory, read from the write side for the just-updated operation.
5. **Optimistic UI:** update the UI based on the command result and clearly indicate pending state.

Illustrative example, not a built-in Spring Framework endpoint:

~~~text
POST /orders/A/pay
-> { "orderId": "A", "expectedVersion": 12 }

GET /orders/A/overview
-> { "status": "PAID", "projectionVersion": 12 }
~~~

**Do not retry the payment command simply because the projection has not caught up yet.** Doing so can cause duplicate side effects. Commands need their own idempotency; read model lag is a query-side concern.

## 9. One Projection from Multiple Event Sources

~~~text
OrderPlaced ---------------------+
PaymentCaptured -----------------+--> OrderOverview
ShipmentScheduled ---------------+
CustomerDisplayNameChanged ------+
~~~

A single read row can aggregate multiple bounded contexts. In that case:

- **Order version** and **Customer version** do not share a single clock; do not compare version numbers from two different aggregates as a global ordering.
- Define **field ownership**: payment events update payment fields, shipment events update shipping fields.
- Use per-source checkpoints/versions or a processed-event ledger.
- When one event is missing, some fields may remain stale even while others update; reconciliation is needed.
- Projections holding only current state sometimes require a **join/aggregation pipeline** with a strategy for waiting on complete data and timeouts.

If an update is **incrementing a counter**, duplicate events cause double-counting; use atomic deduplication and transactional effects. If an update is "set `status=PAID` at version 12", a version guard makes idempotency easier.

## 10. Rebuild, Replay, and Backfill

A read model is derived data. When schemas or projector logic change, you should be able to rebuild it:

~~~text
Durable event log / write-store snapshot
                   |
                   v
         Build projection_v2
                   |
                   v
     Validate count/checksum/queries
                   |
                   v
      Catch up with live event stream
                   |
                   v
      Switch read traffic to v2
~~~

**Spring `ApplicationEventPublisher` does not retain event history by default.** If you only use in-process `@EventListener`, you do not automatically have replay. To rebuild from history, you need a retained event log/event store/outbox archive with sufficient data. If only the current state in the write DB remains, you can rebuild a **current-state snapshot projection** via backfill, though you cannot necessarily reconstruct full event history.

In production, rebuild into a **shadow table/index**, catch up with live events, and then cut over read traffic with verification. Keep versions/checkpoints, test schema compatibility, and preserve cutover rollback capability.

**Do not let projection replay trigger business side effects** such as sending emails, creating payments, or dispatching external commands. Separate read model projectors from listeners that execute side effects.

### Deletes and Tombstones

If the domain emits **OrderDeleted v5**, the projector can delete the row, hide it, or write a versioned tombstone so a late-arriving **OrderCreated v1** does not recreate the row. The decision depends on retention policies, privacy rules, and query contracts.

## 11. Read Models Are Not the Place to Enforce Domain Invariants

Critical decisions—such as sufficient balance for withdrawal, available inventory, whether a voucher was used, or whether a payment is definitively settled—must be confirmed by the **write/domain owner**. Read models can lag, are denormalized, and can be rebuilt.

Use projections strictly for **querying/display** according to their contract. If a read store is designated as the authoritative source for another category of data, that is a separate ownership decision; do not casually rely on an event-driven read model to validate every business mutation.

## 12. Essential Tests

| Test | What to Verify |
| --- | --- |
| Commit domain change | Projection has new status/version in the right phase |
| Rollback domain transaction | `AFTER_COMMIT` handler creates no read row |
| Duplicate event | Side effect/projection is not applied twice |
| Stale event | Older version does not overwrite newer version |
| New event after multiple updates | Query state and `lastVersion` are accurate |
| Read-side DB down during processing | Durable event can still retry if using outbox |
| Consumer crashes after effect before ACK | Redelivery is deduplicated |
| Concurrent projectors | No race/overwrite with unique key and conditional update |
| Rebuild | Query output matches expected data after replay/backfill |
| Query immediately after command | API handles projection lag per contract |
| Schema version mismatch | Consumer has a compatibility/parking strategy |
| Shutdown/restart | Resumes from outbox/offset/checkpoint correctly |

**Testing `projector.apply(event)` directly** only tests mapping logic. To test **Spring `@TransactionalEventListener`**, you must publish events through a real Spring **ApplicationContext** inside a transaction managed by a real transaction manager. Test methods with **@Transactional** typically roll back by default in Spring TestContext; to verify `AFTER_COMMIT` in the same test, you can use **`TestTransaction.flagForCommit(); TestTransaction.end()`** or an explicit `TransactionTemplate` outside a test-managed transaction.

For async consumers, do not rely on a fixed `Thread.sleep()`; use `CountDownLatch`, Awaitility, or poll persisted `projectionVersion` with a timeout.

## 13. Monitoring and Investigating Projection Lag

A projection pipeline should expose:

| Metric/Log Field | Meaning |
| --- | --- |
| **projection_applied_total** | Number of events applied |
| **projection_duplicate_ignored_total** | Number of duplicate events skipped |
| **projection_stale_ignored_total** | Number of stale events blocked |
| **projection_failed_total** | Failed events |
| **projection_lag_seconds** | Time from domain commit/event to projection |
| **projection_version/checkpoint** | Processing watermark |
| **outbox_pending_count** | Events waiting to be delivered |
| **oldest_pending_event_age** | Age of the longest-stuck event |
| **rebuild_progress** | Backfill progress |
| **reconciliation_mismatch_count** | Differences between domain state and read model |

Log **`eventId`, `aggregateId`, `version`, `projectorName`, `traceId`, `attempt`, `result`**, avoiding sensitive payload fields. With brokers, propagate trace context via headers; with async thread pools, configure appropriate propagation. **Sharing the same trace ID does not mean sharing the same transaction.**

Run a periodic job to reconcile write/read data against key invariants rather than merely checking whether the consumer process is alive.

## 14. Common Design Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Using pre-commit `@EventListener` to update another DB | Projection reflects a rolled-back transaction | Same DB transaction or `AFTER_COMMIT`/outbox |
| Writing to DB in `AFTER_COMMIT` without a new TX | Updates may not be committed | `REQUIRES_NEW` and integration tests |
| Thinking `AFTER_COMMIT` guarantees no lost events | Crash after commit still loses callback | Transactional outbox |
| Omitting aggregate version | Stale event overwrites newer state | Version guard/sequence |
| Using version alone when delta events need every step | Incorrect cumulative values | Inbox + strict sequence/replay |
| Not deduplicating `eventId` | Redelivery creates duplicate side effects | Dedup marker and effect in same transaction |
| `SELECT` then `INSERT` across multiple workers without locking | Race condition | Atomic upsert/unique key |
| Sending mutable JPA entities as payloads | Coupling / lazy loading errors | Immutable event/envelope |
| Handler always queries write store | Hard to replay accurate history | Clear snapshot/delta contract |
| Using timestamps as absolute ordering | Clock skew / concurrent writes | Aggregate version |
| Sharing one version across multiple independent sources | Overwrites fields owned by other sources | Per-source version/checkpoint |
| Letting replay re-send notifications | Duplicate side effects | Separate projector from business actions |
| Letting read model decide payment retries | Projection lag causes double charges | Write owner and idempotent commands |
| Having no rebuild/backfill path | Corrupted search/read index cannot recover | Durable history/snapshot and shadow rebuild |
| Test only verifies `publishEvent` | Does not prove new data committed | Assert persisted projection and transaction outcomes |

## 15. Pre-Production Checklist

1. **Are the purpose of the read model and query patterns clear?**
2. **Which domain changes emit events, and what IDs/versions do events carry?**
3. **Why did you choose strong consistency or eventual consistency based on requirements?**
4. **If using `AFTER_COMMIT`, does the projector open a new transaction when writing to the DB?**
5. **If the process dies after domain commit, is there a durable outbox/replay path?**
6. **Does the consumer handle duplicate and stale/out-of-order events?**
7. **Is the version scoped properly to its aggregate/source?**
8. **Do concurrent workers use atomic upserts/locking?**
9. **Does the read API expose `expectedVersion`/`projectionVersion` or have a lag policy?**
10. **Do tombstones/delete events prevent old records from reappearing?**
11. **Is there history/snapshot data for rebuilding, and have cutovers been tested?**
12. **Are projections prevented from triggering dangerous side effects during replay?**
13. **Are there tests for commit/rollback/retry/restart/rebuild/concurrency?**
14. **Is there monitoring for lag, backlog, errors, and reconciliation?**

**Conclusion:** In Spring Framework, **domain events** help separate business logic from **read model** materialization. When updating after commit within the same application, use **@TransactionalEventListener(AFTER_COMMIT)** and a **new transaction for the read model write**. If the projection must survive process crashes, choose a **transactional outbox and an idempotent consumer**. Always design **versioning/ordering**, **eventual consistency** contracts, and **replay/rebuild** capability; the read model is derived data and does not replace domain invariants.

### Official Documentation

- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html

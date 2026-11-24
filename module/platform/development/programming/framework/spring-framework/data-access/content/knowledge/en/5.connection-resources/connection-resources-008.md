# Keep Connections Short-Lived and Avoid Network Waits While Holding a Transaction

## 1. Objectives and Key Message

When developing a data-access layer in Spring Framework, performance does not depend solely on whether SQL queries are fast or slow. An application can run queries that take only a few milliseconds and still exhaust its connection pool if each request **holds a transaction open while waiting on HTTP, RPC, a message broker, file upload, or an external service**.

After this article, you will be able to:

- Distinguish a **physical database connection**, a **connection borrowed from a pool**, a **transaction**, **data locks**, and when each resource is released.
- Explain why making network calls inside `@Transactional` increases connection hold time, latency, lock contention, and cascading failure risk.
- Choose short transaction boundaries: prepare/validate data and call slow services outside; open transactions only for changes that must commit/roll back together.
- Apply **call before transaction**, **call after commit**, **transactional outbox**, and **workflow/Saga** appropriately based on required consistency.
- Design a Spring Boot + JDBC example with SQL, transactions, a notification dispatcher job, and retries without running HTTP inside a transaction holding a connection.
- Monitor HikariCP, transaction duration, and PostgreSQL `pg_stat_activity`; distinguish root-cause fixes from timeouts/pool settings that only limit blast radius.

**Working rule:** **keep transactions short enough to protect data invariants**, and never turn a database transaction into a boundary wrapping network work of unbounded duration. This is a design principle, not a demand that every operation run outside a transaction.

## 2. Understanding Precisely: Connection, Pool, Transaction, Lock

### 2.1. What is a database connection?

In JDBC, a `java.sql.Connection` object represents an interactive session to the DB. Spring Boot typically uses a `DataSource` managed by a connection pool like HikariCP. The pool maintains a set of **physical connections** to the DB for reuse. Application code borrows a connection and returns it to the pool when done; calling `close()` on a pool-issued wrapper usually **returns the connection**, rather than permanently closing the TCP connection.

| Concept | Role | What to Observe |
| --- | --- | --- |
| Physical connection | Real session/connection to the database | Session count, server connection limits |
| Borrowed/active connection | Currently borrowed by the application from the pool | Hikari active, checkout duration |
| Idle connection in pool | Available to be borrowed again, not serving a request | Hikari idle; not the same as DB `idle in transaction` |
| Transaction | Group of DB operations with commit/rollback boundaries and isolation | Start/end timestamps, locks, idle state |
| Row/table lock | DB mechanism protecting concurrent operations | Lock waits, deadlocks, contention |
| Network call | HTTP/RPC/broker call from the app to another system | Connect/read timeouts, retries, tail latency |

Do not confuse HikariCP's `idle` with PostgreSQL's `idle in transaction`. An `idle` connection in the pool is a free resource; a PostgreSQL backend in `idle in transaction` is a session **with an open transaction not currently running SQL**, which can continue holding locks and blocking row-version cleanup.

### 2.2. What boundary does Spring @Transactional own?

In the common imperative model, Spring uses `PlatformTransactionManager` and a transaction interceptor around methods invoked through a Spring proxy. Example:

```java
@Transactional
public void updateOrder() {
    repository.updateStatus(...);
    // other operations
}
```

When the method is called via a valid Spring proxy path, a transaction is started or joined according to `propagation`. When the method returns normally, the manager commits if eligible; an escaping unchecked exception typically triggers rollback by default.

**Note on checkout timing:** logical transaction start does not always mean a physical connection is borrowed right on line one. `DataSourceTransactionManager` typically acquires/binds a JDBC connection on start; some lazy connection setups or JPA providers may defer borrowing until the first SQL statement. Regardless of configuration, **once SQL has run and the thread waits on a network call before commit, the transaction remains open**, and connections/locks can stay held until the transaction completes.

Nor should `@Transactional(readOnly = true)` be misunderstood as "holds no connection" or "has no transaction". It is a transaction hint/attribute suitable for read operations; actual timing and resources still depend on the transaction manager, JDBC driver, JPA provider, and DBMS.

### 2.3. How long do data locks live?

An `UPDATE` or `SELECT ... FOR UPDATE` can hold locks until the end of the transaction. If you do:

```text
T0: begin transaction
T1: UPDATE orders SET status = 'PROCESSING' WHERE id = 42  (DB: fast)
T2: HTTP call to partner; wait for response                 (can be very slow)
T3: UPDATE orders SET status = 'CONFIRMED' WHERE id = 42
T4: COMMIT
```

Between **T2 → T3**, no SQL runs, yet the transaction remains open, the connection may still be borrowed, and the lock from T1 is not released. Other requests wanting to update the same order may have to wait, even though the database is barely busy processing queries.

In PostgreSQL, an open transaction can also hold a snapshot or XID horizon preventing `VACUUM` from reclaiming dead tuple versions normally. The impact depends on isolation level, SQL statements, and how long the transaction stays open, yet **waiting outside the DB is never free**.

## 3. Failure Cascade When Holding Connections for Network Waits

Suppose each SQL operation takes only 10 ms, yet waiting on a payment partner takes 3 seconds between two SQL statements. Under concurrent traffic, each request can hold a connection for several seconds. A 10-connection pool quickly becomes a bottleneck; incoming requests queue for connections even while DB CPU is underutilized.

```text
Request A: [BEGIN][SQL]--------------- HTTP WAIT ---------------[SQL][COMMIT]
Connection A: [======================= in use ==============================]

Request B: [BEGIN][SQL]------------------ HTTP WAIT ----------------[COMMIT]
Connection B: [=========================== in use ==========================]

Request C:                [WAIT FOR POOL CONNECTION ...]
```

Consequences typically unfold in a chain:

1. **Pool exhaustion:** borrowed connection count climbs; wait time exceeds Hikari's `connectionTimeout`.
2. **Queueing and tail latency:** new requests wait at the pool, driving p95/p99 up even though individual queries remain fast.
3. **Lock contention:** transactions waiting on HTTP hold locks; other transactions block on the same rows or tables.
4. **Compounding timeouts and retries:** clients retry HTTP, services retry DB, partners retry webhooks, multiplying traffic.
5. **Consistency risk:** the partner already performed an external side effect while the DB transaction rolls back; retries without idempotency can duplicate side effects.
6. **Higher operational cost:** more DB sessions, threads stacked waiting for connections, pressure on pools and lock managers; blindly raising `maximumPoolSize` can push the overload onto the database.

Evaluate designs by **connection borrow duration** and **open transaction duration**, not solely SQL execution time. These two intervals are related yet not strictly identical across all implementations.

## 4. Anti-Pattern in Spring: Calling HTTP Inside @Transactional

The example below is **code illustrating a design flaw** inside a Spring service:

```java
@Service
public class UnsafeCheckoutService {
    private final OrderRepository orders;
    private final PaymentGateway gateway;

    public UnsafeCheckoutService(
            OrderRepository orders, PaymentGateway gateway) {
        this.orders = orders;
        this.gateway = gateway;
    }

    @Transactional
    public long checkout(CheckoutCommand command) {
        long orderId = orders.insertPending(command); // SQL / holds transaction
        gateway.charge(command.paymentToken(), command.amount()); // HTTP
        orders.markPaid(orderId);                    // SQL
        return orderId;                              // COMMIT after return
    }
}
```

`OrderRepository`, `PaymentGateway`, and `CheckoutCommand` are illustrative types; this snippet is not a standalone compilable class. The mistake is not the `@Transactional` annotation itself: **a DB transaction wraps an HTTP call of uncertain duration**.

Scenarios difficult to resolve with this code:

- Partner responds after 5 seconds: the DB transaction may hold a connection and locks for that entire duration.
- Partner reports success yet `orders.markPaid` or `COMMIT` fails: DB rollback **cannot undo** the transaction executed in the payment system.
- Partner succeeds yet the response is lost on the network: the app assumes failure and retries, risking double-charging.
- Setting `@Transactional(timeout = 5)` does not magically make HTTP atomic with the DB; a transaction timeout is not a reliable mechanism to abort arbitrary external I/O.

**Do not treat a single database's transaction as a distributed transaction.** `@Transactional` manages compatible resources known to the transaction manager, and does not automatically make HTTP and the database commit/roll back together.

## 5. Redesigning by Identifying Business Ordering

Before moving a network call, answer two questions:

1. Does the call only **read data from another system** (pricing, limits, risk decisions), or does it cause a **side effect** (charging money, sending email, publishing a message, creating a ticket)?
2. Does the business require **a single synchronous operation**, or does it allow **intermediate states, background processing, and eventual consistency**?

No single pattern fits every system. Three common patterns apply.

### 5.1. Fetch remote data before the transaction

If you need exchange rates or partner validation before saving to the DB, call the remote service outside the transaction and open a transaction only for the write:

```text
HTTP request
  -> validate input
  -> external service: fetch quote / risk result            (no DB transaction)
  -> application service: check partner result
  -> [BEGIN -> check DB invariants -> INSERT/UPDATE -> COMMIT]
  -> HTTP response
```

Illustrative **code example**:

```java
@Service
public class QuoteOrderService {
    private final QuoteGateway quoteGateway;
    private final ShortOrderWriter writer;

    public QuoteOrderService(
            QuoteGateway quoteGateway, ShortOrderWriter writer) {
        this.quoteGateway = quoteGateway;
        this.writer = writer;
    }

    public long placeOrder(NewOrder input) {
        Quote quote = quoteGateway.fetch(input.productCode()); // network before TX
        return writer.save(input, quote);                     // short TX
    }
}

@Service
class ShortOrderWriter {
    private final OrderRepository repository;

    ShortOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long save(NewOrder input, Quote quote) {
        return repository.insert(input, quote);
    }
}
```

`QuoteGateway`, `NewOrder`, `Quote`, and `OrderRepository` are interfaces/models to declare in the application; the example focuses on where the transaction boundary sits. `QuoteOrderService` calls `writer.save(...)` on **another bean** so the Spring proxy applies `@Transactional` properly. Never call `this.save(...)` and assume the interceptor will run.

**Stale data trap:** between fetching the quote and committing, prices/state can change. Use quote expiration, versions/ETags, conditional DB update checks, or appropriate rejection rules. Putting HTTP inside the transaction **does not** keep another service's state consistent anyway, because the DB cannot lock the partner.

### 5.2. Call the network after the transaction commits

If the DB write succeeds and only then must a secondary signal be sent, you can do:

```text
BEGIN -> INSERT/UPDATE -> COMMIT -> HTTP call
```

This reduces DB transaction hold time. However, if the process crashes right after commit and before HTTP, the signal can be **lost**. If HTTP fails, the DB has still committed. For non-critical notifications or acceptable best-effort handling, publish that policy clearly. For side effects that must eventually be delivered, use a **transactional outbox** or an equivalent reliable workflow.

### 5.3. Transactional outbox for "save then notify" operations

An outbox writes **the business record and the dispatch task** in the same short DB transaction. A separate worker sends the HTTP/message after that transaction has committed.

```text
API / application service
    |
    v
 [BEGIN]
    INSERT purchase_orders
    INSERT notification_outbox (PENDING)
 [COMMIT]  ----------------------------------------------------+
    |                                                          |
    +--> return OrderCreated                                   |
                                                               v
                                             Outbox dispatcher / worker
                                            [claim row + short COMMIT]
                                                               |
                                                    HTTP to partner
                                                               |
                                            [mark DONE + short COMMIT]
```

Guarantees:

- If order creation fails: both the order and outbox roll back together.
- If order creation succeeds: the outbox entry persists durably so a worker can retry delivery even after a process restart.
- The worker **never holds a DB transaction during HTTP calls**; claiming and updating status are separate transactions.
- If delivery succeeds yet marking DONE fails, the event may be resent. This is **at-least-once delivery**; the receiver needs idempotency/deduplication by event ID—never advertise "exactly once" from an outbox alone.

## 6. Spring Boot Example: Short Transaction + Outbox + HTTP Outside DB

This example uses **Java 17+**, Spring Boot **3.3.x** (Spring Framework 6.1), Spring JDBC, PostgreSQL, and `RestClient`. To apply it, place the classes in the same `demo.outbox` package of a configured Spring Boot project. Migrations use PostgreSQL syntax; table creation scripts are for a learning database.

### 6.1. Dependencies and database

In `build.gradle` of a project with the Spring Boot plugin configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

File `src/main/resources/db/migration/V1__orders_and_outbox.sql`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(100) NOT NULL UNIQUE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('CREATED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notification_outbox (
    event_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    event_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'IN_FLIGHT', 'DONE')),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_notification_outbox_pending
    ON notification_outbox (status, available_at, event_id)
    WHERE status <> 'DONE';
```

Table `purchase_orders` has a unique `request_key` to distinguish order creation requests. Table `notification_outbox` stores a single event with a stable `event_id`. Status `IN_FLIGHT` and `lease_until` allow a worker to recover an interrupted job. `lease_token` prevents an old worker from mistakenly marking a job already reclaimed by another worker. Choose a lease longer than the HTTP timeout and provide renewal if tasks can run long; even so, the receiver **must still guard against duplicate delivery**.

Column `available_at` supports retries. Indexes should be reviewed with `EXPLAIN (ANALYZE, BUFFERS)` under real load, especially as DONE rows accumulate.

### 6.2. Shared data types without DB resources

`src/main/java/demo/outbox/OutboxModels.java`:

```java
package demo.outbox;

import java.math.BigDecimal;
import java.util.UUID;

public final class OutboxModels {
    private OutboxModels() {}

    public record NewOrder(String requestKey, BigDecimal amount) {}

    public record CreatedOrder(long orderId, UUID eventId) {}

    public record OutboxJob(UUID eventId, long orderId, UUID leaseToken) {}

    public record Notification(UUID eventId, long orderId) {}
}
```

Records hold application data and outbound messages. No `Connection`, `ResultSet`, or JDBC driver details leak out of the repository.

### 6.3. Very short order creation transaction

`src/main/java/demo/outbox/OrderWriteService.java`:

```java
package demo.outbox;

import java.util.UUID;

import demo.outbox.OutboxModels.CreatedOrder;
import demo.outbox.OutboxModels.NewOrder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriteService {
    private final JdbcTemplate jdbc;

    public OrderWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public CreatedOrder create(NewOrder order) {
        Long orderId = jdbc.queryForObject(
                """
                INSERT INTO purchase_orders(request_key, amount, status)
                VALUES (?, ?, 'CREATED')
                RETURNING id
                """,
                Long.class,
                order.requestKey(),
                order.amount()
        );
        if (orderId == null) {
            throw new IllegalStateException("Database did not return order ID");
        }

        UUID eventId = UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO notification_outbox
                    (event_id, order_id, event_type, status)
                VALUES (?, ?, 'ORDER_CREATED', 'PENDING')
                """,
                eventId,
                orderId
        );

        return new CreatedOrder(orderId, eventId);
    }
}
```

**Boundary:** only two SQL statements execute inside the transaction. There is no `RestClient`, `Thread.sleep`, `CompletableFuture.join`, or broker call inside `create(...)`. If inserting the outbox row fails, the transaction rolls back the order too; if commit succeeds, the dispatch job is durably stored. This is **DB atomicity**, while HTTP delivery occurs independently after commit.

`UUID.randomUUID()` creates an idempotency key dedicated to the event. If the client retries order creation after losing an HTTP response, the unique `request_key` detects the duplicate request; making the API truly idempotent also requires validating repeated payloads, returning the prior result, and handling policy conflicts per business rules. Never assume `UNIQUE` alone makes every request retry-safe.

### 6.4. Claiming an event in a very short transaction

`src/main/java/demo/outbox/OutboxStore.java`:

```java
package demo.outbox;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import demo.outbox.OutboxModels.OutboxJob;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OutboxStore {
    private final JdbcTemplate jdbc;

    public OutboxStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<OutboxJob> claimOne() {
        UUID token = UUID.randomUUID();
        List<OutboxJob> jobs = jdbc.query(
                """
                WITH candidate AS (
                    SELECT event_id
                    FROM notification_outbox
                    WHERE
                        (status = 'PENDING' AND available_at <= now())
                        OR (status = 'IN_FLIGHT' AND lease_until < now())
                    ORDER BY event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE notification_outbox o
                SET status = 'IN_FLIGHT',
                    lease_token = ?,
                    lease_until = now() + interval '60 seconds',
                    attempt_count = attempt_count + 1
                FROM candidate
                WHERE o.event_id = candidate.event_id
                RETURNING o.event_id, o.order_id, o.lease_token
                """,
                (rs, row) -> new OutboxJob(
                        rs.getObject("event_id", UUID.class),
                        rs.getLong("order_id"),
                        rs.getObject("lease_token", UUID.class)
                ),
                token
        );
        return jobs.stream().findFirst();
    }

    @Transactional
    public int markDone(OutboxJob job) {
        return jdbc.update(
                """
                UPDATE notification_outbox
                SET status = 'DONE',
                    lease_token = NULL,
                    lease_until = NULL
                WHERE event_id = ?
                  AND lease_token = ?
                  AND status = 'IN_FLIGHT'
                """,
                job.eventId(),
                job.leaseToken()
        );
    }

    @Transactional
    public int scheduleRetry(OutboxJob job) {
        return jdbc.update(
                """
                UPDATE notification_outbox
                SET status = 'PENDING',
                    available_at = now() + interval '30 seconds',
                    lease_token = NULL,
                    lease_until = NULL
                WHERE event_id = ?
                  AND lease_token = ?
                  AND status = 'IN_FLIGHT'
                """,
                job.eventId(),
                job.leaseToken()
        );
    }
}
```

`claimOne()` uses PostgreSQL `FOR UPDATE SKIP LOCKED` so multiple workers do not contend waiting on a row currently being claimed. The `UPDATE ... RETURNING` and claim operation sit inside a very short transaction; **the transaction finishes before the worker calls HTTP**. `markDone` and `scheduleRetry` also each run in a separate short transaction, never reusing the old connection from `claimOne`.

`lease_token` prevents a worker that lost its claim from updating the state of a newer lease. If `markDone` or `scheduleRetry` returns `0`, log that the event was claimed by another worker, changed state, or is no longer valid. The example intentionally claims one event at a time to highlight boundaries; in operations you can claim an appropriately sized batch, never holding a connection while processing the whole batch over HTTP.

**Limitations of this simplified sample:** retry delay is currently a fixed 30 seconds without dead-lettering, attempt caps, 4xx/5xx differentiation, lease heartbeats, or stuck-event monitoring. Production requires backoff with jitter, a retry budget, non-recoverable error policies, alerts, and retention-based cleanup of completed rows.

### 6.5. HTTP client with timeouts and no DB transaction

`src/main/java/demo/outbox/PartnerNotificationClient.java`:

```java
package demo.outbox;

import demo.outbox.OutboxModels.Notification;
import demo.outbox.OutboxModels.OutboxJob;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PartnerNotificationClient {
    private final RestClient client;

    public PartnerNotificationClient(
            RestClient.Builder builder, Environment environment) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1500);
        factory.setReadTimeout(3000);

        this.client = builder
                .requestFactory(factory)
                .baseUrl(environment.getRequiredProperty("partner.base-url"))
                .build();
    }

    public void send(OutboxJob job) {
        client.post()
                .uri("/notifications")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Idempotency-Key", job.eventId().toString())
                .body(new Notification(job.eventId(), job.orderId()))
                .retrieve()
                .toBodilessEntity();
    }
}
```

Here, the **1.5-second connect timeout** and **3-second read timeout** are illustrative settings that must be tuned to the target system's SLA. `SimpleClientHttpRequestFactory` is used in the example for explicit timeouts; production can pick an HTTP client with appropriate connection pooling, timeouts, metrics, and resilience policies.

The `Idempotency-Key` header only works if **the partner actually implements deduplication** using this key. Sending the header from our server does not by itself guarantee at-most-once execution on the partner side. Never send card details, secret tokens, or sensitive data in illustrative payloads.

### 6.6. Worker running network calls outside a transaction

`src/main/java/demo/outbox/OutboxPublisher.java`:

```java
package demo.outbox;

import java.util.Optional;

import demo.outbox.OutboxModels.OutboxJob;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

@Component
public class OutboxPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OutboxPublisher.class);

    private final OutboxStore outbox;
    private final PartnerNotificationClient partner;

    public OutboxPublisher(
            OutboxStore outbox, PartnerNotificationClient partner) {
        this.outbox = outbox;
        this.partner = partner;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishOne() {
        Optional<OutboxJob> claimed = outbox.claimOne();
        if (claimed.isEmpty()) {
            return;
        }

        OutboxJob job = claimed.get();

        try {
            partner.send(job); // network: NOT inside a DB transaction
        } catch (RestClientException remoteFailure) {
            log.warn(
                    "Remote notification failed for event {}",
                    job.eventId(),
                    remoteFailure
            );
            int updated = outbox.scheduleRetry(job);
            if (updated == 0) {
                log.warn("Retry claim is no longer owned: {}", job.eventId());
            }
            return;
        }

        int updated = outbox.markDone(job);
        if (updated == 0) {
            log.warn("Completion claim is no longer owned: {}", job.eventId());
        }
    }
}
```

`OutboxPublisher.publishOne()` is **not** annotated with `@Transactional`. It calls transactional methods on the `OutboxStore` bean. Once `claimOne()` returns, its transaction has already committed. Afterward, `partner.send(...)` may take seconds without carrying the claim's transaction or connection. Once HTTP finishes, the worker calls `markDone(...)` to open a separate, short transaction.

If the process crashes after HTTP succeeds yet before `markDone`, the lease expires and the event can be resent. Hence, **the receiver must deduplicate** or process messages idempotently. If HTTP takes longer than the lease, another worker may reclaim and resend before the first worker finishes; timeouts and lease duration must align, or leases must be renewed when needed.

If `markDone` hits a DB error after HTTP succeeded, leaving the job to await recovery is acceptable in an at-least-once model. Never widen `markDone`'s transaction upward to wrap `partner.send`.

### 6.7. Entry point and configuration

`src/main/java/demo/outbox/OutboxApplication.java`:

```java
package demo.outbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class OutboxApplication {
    public static void main(String[] args) {
        SpringApplication.run(OutboxApplication.class, args);
    }
}
```

File `src/main/resources/application.yml` (illustrated with environment variables):

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2000

partner:
  base-url: ${PARTNER_BASE_URL}
```

Choosing `maximum-pool-size: 10` and `connection-timeout: 2000` is illustrative only, **not default parameters to copy across every system**. Pool size must be based on DB resources, instance count, real concurrency, query latency, and measurements; raising it unboundedly only shifts the bottleneck to the DB.

Hikari's `connection-timeout` caps **how long to wait when borrowing a connection from the pool**, not SQL or HTTP duration. Set HTTP timeouts separately on the client; SQL/lock limits can be configured at the DB or data-access layer per policy.

With Gradle Spring Boot properly configured, you can run:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. Requires an available PostgreSQL instance, environment variables `DB_JDBC_URL`, `DB_USER`, `DB_PASSWORD`, `PARTNER_BASE_URL`, and a partner endpoint supporting the `POST /notifications` contract. These classes compile when placed in a properly configured project/dependency setup, not as standalone pure Java run via `javac` without Spring libraries.

To trace the flow while learning, invoke `OrderWriteService.create(...)` from a controller/test, check the order and a `PENDING` outbox event, and then watch the worker claim → send → DONE. In learning environments, use a mock HTTP server instead of a real partner system.

## 7. Reading Failure Scenarios Accurately

| When Failure Occurs | DB State | Desired Behavior |
| --- | --- | --- |
| Order insert succeeds, outbox insert fails | Entire transaction rolls back | No committed order missing an outbox entry |
| Order creation transaction commit fails | Do not assume success; real state must be verified when commit outcome is ambiguous | Client/API uses request key and queries back per policy |
| Commit succeeds, process crashes before worker runs | Order and PENDING event exist | Worker can process once the system restarts |
| Claim succeeds, worker crashes before HTTP | Event IN_FLIGHT with lease | Once lease expires, another worker reclaims |
| HTTP succeeds, markDone fails | Event not yet DONE | May resend; partner must be idempotent |
| HTTP times out after partner processed it | Uncertain whether side effect happened | Retry with the same event ID; do not generate a new key |
| Two workers run concurrently | `SKIP LOCKED` and claim token coordinate work distribution | Still design for duplicates caused by leases/retries |
| Permanent HTTP error (e.g., 400 invalid payload) | Should not retry infinitely | Classify, dead-letter/alert, handle operationally |
| DB down when worker needs to claim | Cannot acquire a job | Do not run HTTP without a job; retry per worker lifecycle |

Do not solve "partner already charged yet DB rolled back" by keeping the database transaction open during the network call: that usually **increases** resource hold time and still fails to provide cross-system atomic commit.

## 8. Other Patterns and When to Use Them

### 8.1. Best-effort after commit

You can use Spring `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for secondary work that can afford occasional loss, or to wake an outbox worker. The listener runs only after the transaction commits successfully in a compatible flow. However, an in-memory-only event will be **lost if the process crashes after commit before the listener finishes**; therefore, never treat an in-memory listener as a durable queue replacing an outbox.

When an after-commit listener wants to write further to the DB, note that old transaction resources may still be thread-bound; Spring docs recommend a suitable new transaction such as `REQUIRES_NEW` for new write side effects. Never accidentally run a long transaction inside an after-commit callback.

### 8.2. Using a message broker

Replacing HTTP with Kafka/RabbitMQ does not automatically solve atomicity between "commit SQL" and "publish message". If you publish while the transaction is open, a slow broker still holds the transaction. If you publish after commit, there is a crash window where messages are lost. Outbox + broker relay is one strategy; transactional integration/CDC mechanisms with proven semantics for your actual infrastructure can also be used.

### 8.3. Saga/workflow for multi-service business flows

For payment + inventory + shipment, one local database transaction cannot coordinate multiple independent services. Use application states like `PENDING_PAYMENT`, `CONFIRMED`, `FAILED`, controlled compensations, and idempotency at every step. Each step updates its DB inside a short transaction, with network communication outside. Intermediate states are part of the business contract, not an architectural flaw.

### 8.4. Calling the network before the transaction is not always enough

Prices/quotes can change between "remote read" and "DB write". Re-check version/expiry, use conditional DB updates, or design states requiring later confirmation. If the system demands atomicity across a DB and another service, redefine business boundaries, guarantee protocols, or compensating workflows; `@Transactional` alone cannot achieve that.

### 8.5. Do not fix with the wrong propagation

Putting `@Transactional(propagation = Propagation.NOT_SUPPORTED)` around HTTP inside an outer transaction only **suspends the transaction logically**, without guaranteeing the outer transaction's connection returned to the pool; it may remain held for resumption. Using `REQUIRES_NEW` to "isolate" HTTP can even increase needed connections if an outer transaction still holds resources. The reliable approach is **ending the outer transaction before starting any network call**, or splitting into two services/workers with clear commit boundaries.

## 9. Why Timeouts Cannot Replace Short Transactions

Timeouts guard time bounds, yet do not fix execution ordering.

| Timeout | What It Limits | What It Does Not Limit |
| --- | --- | --- |
| HTTP connect timeout | Time to establish connection to remote | Total remote processing time |
| HTTP read/response timeout | Waiting for data/response per client implementation | Transaction length if HTTP sits inside the transaction |
| Hikari `connectionTimeout` | Waiting to borrow a connection from the pool | How long a request keeps a borrowed connection |
| Spring `@Transactional(timeout = ...)` | Logical transaction timeout depending on transaction manager/driver and managed ops | Does not guarantee aborting `Thread.sleep`, HTTP, or remote side effects |
| PostgreSQL `statement_timeout` | Server-side execution time per SQL statement | Java-side HTTP waits between SQL statements |
| PostgreSQL `lock_timeout` | Time spent waiting to acquire a lock | Network waits outside the DB |
| PostgreSQL `idle_in_transaction_session_timeout` | Aborts a session idling inside a transaction too long | Redesigning the transaction; may cause requests to fail and drop connections |

**Important:** setting `idle_in_transaction_session_timeout` too low can cause the DB to kill valid long-running requests; the pool/app then has to recover broken connections. It is an operational "guardrail", not an excuse to keep HTTP inside transactions. Tune per DBMS/version and specific configuration.

In Spring JDBC/JPA, transaction timeouts should also not be confused with total request deadlines. Even when the DB rolls back due to timeout, an HTTP request already sent to a partner can complete and create side effects. Always design idempotency, cancellation, and retries to match business semantics.

## 10. Sources of Long-Held Connections Even Without Direct HTTP Calls

### 10.1. Streaming ResultSets or very large datasets

Using `JdbcTemplate.queryForStream(...)` can hold `ResultSet`, `Statement`, and connection until the stream is **closed**. An anti-pattern is returning an unclosed `Stream` from repository to controller to serialize JSON incrementally over a slow response. The DB connection then becomes coupled to network/client speed.

Prefer:

- Reading a bounded page, mapping to DTOs, and closing resources before sending the HTTP response.
- If datasets are large and true streaming is required, actively manage lifetime, backpressure, cursors, and timeouts; never leave a DB stream tied by default to browser download speed.
- With manual JDBC, always use `try-with-resources` for `Connection`, `PreparedStatement`, and `ResultSet`; with Spring, follow the stream/transaction closing contract of the API in use.

### 10.2. JPA lazy loading and Open Session in View

When serializing an entity with lazy relationships, a web response can trigger extra SQL outside the intended service boundary. Spring Boot for JPA web apps has Open EntityManager in View (OSIV) enabled depending on config, keeping the persistence context open across the request; while this does not necessarily hold the same physical connection across the whole request, it can cause late queries, N+1 issues, and unpredictable lifecycles.

For REST APIs, consider `spring.jpa.open-in-view=false` and preparing DTOs/projections in the service with an explicit fetch plan. This is an architectural choice requiring testing, not a magic switch that fixes every connection leak.

### 10.3. Heavy CPU/blocking work inside a transaction

Even without network calls, tasks like PDF generation, large file reads, compression, CPU-heavy computation, or waiting on a mutex between two SQL statements prolong transactions. Move data preparation outside the transaction whenever possible; keep inside the same commit only operations needing shared consistency.

### 10.4. Transactions spanning loops over many records

Wrapping `@Transactional` around an entire loop of thousands of items, where each item calls the DB or HTTP, can hold connections/locks for a very long time. Determine the real atomicity required: per item, per small batch, or whole job; use chunking, queues, and idempotency when appropriate. Never split a genuinely atomic business operation into separate transactions just for speed.

### 10.5. Threads or coroutines outside transaction boundaries

With Spring's imperative transactions, resources are typically bound per thread; calling `CompletableFuture.supplyAsync(...)` or spawning a new thread inside `@Transactional` **does not automatically propagate the transaction to the new thread**. That both breaks consistency expectations and invites waiting on `join()` while the original transaction stays open. Reactive transactions with `ReactiveTransactionManager` use Reactor context rather than ThreadLocal in the same way; do not mechanically apply imperative JDBC rules to R2DBC.

## 11. Observing Connection Pools and Transactions in Production

### 11.1. Metrics to watch together

In Spring Boot Actuator + Micrometer + HikariCP, common metrics include (exact names depend on version and registry):

- `hikaricp.connections.active`: borrowed connection count.
- `hikaricp.connections.idle`: idle connections available in the pool.
- `hikaricp.connections.pending`: threads waiting for a connection.
- `hikaricp.connections.timeout`: count of borrow timeouts.
- Acquire/usage durations when instrumented; request p95/p99, transaction duration, and partner call latency.

A telling pattern: SQL latency is steady, remote latency rises, `active` nears `maximumPoolSize`, `pending` climbs, and the DB shows many `idle in transaction` sessions. This pattern **suggests** transactions are holding connections while waiting on non-SQL work; confirm with traces and DB state before concluding.

### 11.2. PostgreSQL pg_stat_activity

In test environments or with proper observability permissions:

```sql
SELECT
    pid,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Watch for aged transactions, `idle in transaction`, and sessions waiting on locks. `pg_stat_activity` is only an **instantaneous snapshot**; it cannot prove which request caused a slowdown without request IDs/tracing. The `query` column may contain sensitive data, so the example intentionally omits it. Production systems need tools correlating HTTP trace ↔ transaction ↔ DB session under observability and access-control policies.

You can inspect lock-waiting sessions:

```sql
SELECT
    pid, state, wait_event_type, wait_event,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
  AND datname = current_database();
```

A lock-waiting session does not itself identify who holds the lock; use `pg_blocking_pids(pid)` and PostgreSQL catalogs when analyzing blocker/waiter relationships. Never run `pg_terminate_backend` haphazardly in production just because a session looks old; identify the owner and follow operational policy.

### 11.3. Hikari leak detection

Hikari's `leakDetectionThreshold` can log stack traces when a connection is borrowed for too long, assisting investigation. This is a **checkout-duration warning**, not proof of a permanent leak; valid long transactions can trigger warnings too. Enable a reasonable threshold temporarily while investigating, handle logs under sensitive-data controls, and fix the code holding connections too long rather than raising the threshold just to silence warnings.

### 11.4. Measure the right segments

When tracing a request, separate:

```text
request total
  ├── validation / auth
  ├── external call latency
  ├── transaction time
  │     ├── pool acquisition
  │     ├── SQL execution
  │     ├── waiting for locks
  │     └── commit/rollback
  └── response serialization
```

If a network call sits **inside the transaction**, those two durations overlap. After refactoring, expect transaction time to drop, pool pending to decrease, and lock waits to become rarer. Simply raising `maximumPoolSize` may mask the bottleneck briefly without making transactions shorter.

## 12. Testing Boundaries and Recovery Failures

### 12.1. Testing the desired properties

For the outbox example, include tests for:

1. **Atomicity:** force the outbox insert to fail; verify no purchase order committed from that request.
2. **Claim transaction separation:** after `OutboxStore.claimOne()` returns, the fake HTTP client invoked on the worker thread sees **no active imperative transaction**.
3. **Partner timeout:** a fake server stalls or drops connections; the worker keeps no DB transaction open, and the event returns to PENDING for retry.
4. **Crash after send:** simulate HTTP succeeding while `markDone` fails; once the lease expires, the event is reclaimed with the same `event_id`.
5. **Multiple workers:** run claims concurrently; an event has only one valid lease at a time; updating with a stale lease token affects 0 rows.
6. **Receiver idempotency:** send the same `Idempotency-Key` twice; the receiver produces only one business side effect per agreed contract.
7. **Load testing:** simulate a slow remote service and compare pool active/pending before and after refactoring via metrics/tracing.

For JDBC transactions, use integration tests with real PostgreSQL or Testcontainers PostgreSQL to validate `FOR UPDATE SKIP LOCKED`, leases, and dialect-accurate isolation. H2 or fake databases may not emulate PostgreSQL locking and statements identically.

### 12.2. Simple guard to detect remote calls inside transactions

In an imperative HTTP client, you can add an assertion for tests/diagnostics:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class TransactionGuard {
    private TransactionGuard() {}

    public static void requireNoActiveTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException(
                    "Remote HTTP call started inside a DB transaction"
            );
        }
    }
}
```

Call `TransactionGuard.requireNoActiveTransaction()` **immediately before sending HTTP** in tests or in adapters explicitly mandated "never call inside a transaction". This checks Spring transaction state **on the current thread**; it does not prove no connection is held on another thread, does not replace reactive transaction management, and does not replace integration/performance tests.

### 12.3. Testing timing and returned data

Do not assert only exceptions. For an outbox, verify DB state before/after commit, event name, idempotency key, and when the remote call actually happens. Specifically, DONE status **cannot** be treated as success unless the partner confirmed per protocol, and an HTTP timeout does not prove the partner did not execute the side effect.

## 13. Common Mistakes

| Mistake | Why Dangerous | How to Handle |
| --- | --- | --- |
| Calling HTTP between two SQL statements in `@Transactional` | Holds transaction, connection, and locks during network wait | Move HTTP outside; use outbox/workflow if needed |
| Raising pool size from 10 to huge values on timeouts | DB connection limits and lock contention remain | Measure transaction/checkout time; fix lifetimes first |
| Believing `@Transactional(timeout)` cancels HTTP | DB timeout does not mean HTTP cancellation | Separate HTTP timeouts and short transaction boundaries |
| Sending HTTP right after commit when events must never be lost | Crash gap between commit and send | Save outbox in the same transaction |
| Thinking outbox guarantees "exactly once" | Crashes/leases/retries cause duplicate delivery | Stable event ID + receiver deduplication |
| Using `REQUIRES_NEW` to wrap HTTP inside an outer transaction | Outer transaction may still hold its connection | Commit outer transaction first |
| Calling `this.save()` on another `@Transactional` method in the same bean | Standard Spring proxy is bypassed | Split beans / go through proxy or use `TransactionTemplate` |
| Wrapping file uploads/serialization/heavy CPU in TX | Long transaction even without SQL | Prepare/stream outside when business logic allows |
| Returning `Stream<ResultSet>` to controller | Connection tied to response/client speed | Materialize small pages; close streams per lifecycle |
| Measuring only query time, ignoring transaction duration | Misses HTTP waits, locks, and pool waits | Trace from request through transaction, pool, and remote |
| Treating `readOnly=true` as "holds no resources" | Read transactions still have lifecycles/connections | Keep read transactions short; avoid extra work in scope |
| Retrying charge with a new key after timeout | Unknown whether remote already processed | Reuse the same idempotency key; reconcile |
| Catching errors and returning normally inside a transaction | Rollback may not occur as expected | Choose propagation, rollback policy, and clear error handling |
| HTTP outside TX using stale quotes indefinitely | External data changes before DB write | TTL/version/conditional update, stale-data policy |

## 14. Hands-on Exercises

**Exercise 1 — Timeline analysis.** A service calls `UPDATE account`, waits 4 seconds on a REST API, and then runs `INSERT audit`, all inside `@Transactional`. List the resources that may be held for 4 seconds and explain why optimizing `UPDATE` from 8 ms down to 2 ms may not solve pool exhaustion.

**Exercise 2 — Pattern selection.** For three requirements: (a) fetching an exchange rate to display; (b) creating an order and mandating a notification; (c) charging money, reserving inventory, and creating a shipment across three services—choose the transaction boundary and one of the patterns: call before transaction, outbox, or Saga/workflow. State consistency caveats for each case.

**Exercise 3 — Refactoring code.** Given a `@Transactional` method containing `repository.save()`, `restClient.post()`, `repository.markSent()`, redesign it into a transaction saving entity + outbox, worker claim/commit, external HTTP, and markDone/commit. Describe behavior if the worker crashes between HTTP and markDone.

**Exercise 4 — Monitoring.** In a dashboard, `hikaricp.connections.active` nears max, `pending` climbs, SQL latency is low, while remote p99 is high. Propose verification steps from traces down to `pg_stat_activity`; distinguish borrowed connections from idle connections in the pool.

**Exercise 5 — Testing.** Write a test with a fake HTTP server that times out, Testcontainers PostgreSQL, and two workers verifying no send happens inside a transaction, no outbox entry is lost after commit, duplicate delivery reuses the same event ID, and business invariants hold.

**Answer hints:** Exercise 1 can hold the transaction, borrowed connection, and locks from UPDATE until COMMIT; speeding up the query barely affects a 4-second wait. Exercise 2: (a) remote call outside DB transaction, watch TTL; (b) outbox; (c) workflow/Saga with idempotency and compensation. Exercise 3: guarantees database atomicity for entity/outbox and at-least-once delivery; does not promise exactly-once. Exercise 4: inspect checkout/transaction times alongside remote traces, distinguishing Hikari idle from PostgreSQL idle in transaction. Exercise 5: verify database state and real side effects, not merely whether a method throws an exception.

## 15. Production Readiness Checklist

- Has each use case clearly identified **which invariants must truly belong to the same transaction**?
- Are any HTTP/RPC/broker calls, future waits, sleeps, file I/O, heavy CPU, response streaming, or long loops running inside `@Transactional`?
- Do out-of-DB operations have clear timeouts, retry budgets, and idempotency keys?
- When saving to DB and mandating event delivery, is there a durable outbox or equivalent guarantee?
- Does the worker commit its claim **before** making network calls and open a separate transaction to markDone?
- Are leases, retries, dead-lettering, permanent error classification, and deduplication designed and tested?
- Is pool sizing based on real load, DB limits, and active/pending metrics rather than guesswork?
- Can you measure transaction duration, connection checkout time, lock waits, remote latency, and observe `idle in transaction`?
- Have exceptions, rollbacks, self-invocation, and propagation been verified via integration tests?
- Does the API clearly document synchronous/asynchronous states, pending states, and safe retries?

**Conclusion:** Optimizing connections is not merely raising the connection count. The sustainable approach is to **start a transaction when ready to write data, run the required SQL, commit early, and wait on the network in a separate step**. For dispatches that must not be lost after commit, a transactional outbox enables short transactions, durable worker retries, and clear state contracts. Each piece must still handle duplicates, timeouts, and eventual consistency with proper business semantics.

## References

- Spring Framework — Declarative transaction management, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction interceptor and thread-bound transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction-bound events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework — JDBC `JdbcTemplate`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — REST Client: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- HikariCP — Pool configuration (`connectionTimeout`, `maximumPoolSize`, `leakDetectionThreshold`): https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- PostgreSQL — Client connection defaults and `idle_in_transaction_session_timeout`: https://www.postgresql.org/docs/current/runtime-config-client.html
- PostgreSQL — `pg_stat_activity`: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL — `SELECT ... FOR UPDATE SKIP LOCKED`: https://www.postgresql.org/docs/current/sql-select.html

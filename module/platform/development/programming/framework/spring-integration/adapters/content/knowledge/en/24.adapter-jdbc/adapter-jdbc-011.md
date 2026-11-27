# Transactions on JDBC Flows in Spring Integration

## 1. Why Is a Transaction on a JDBC Flow More Than One SQL Statement?

A Spring Integration flow can read unprocessed records from a database, convert them into `Message<?>`, write to an outbox table, and send events to Kafka/JMS. When a step fails, the business questions are: **which operations must roll back together, what has already committed, and how will the data be retried?**

Example of one poll:

~~~text
SELECT 10 payment_event state='NEW'
    -> UPDATE rows to 'CLAIMED'
    -> Message<List<PaymentEvent>>
    -> Splitter
    -> INSERT 10 outbox rows
    -> Kafka/JMS publisher
~~~

If `UPDATE` commits while the outbox insert fails, events can remain stuck in `CLAIMED`. If Kafka receives a send while the database transaction rolls back, the same event may be sent again, creating duplicate side effects. Placing an arbitrary `@Transactional` annotation on a class does not solve these cases by itself.

In the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we practice connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`: files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This lesson, **Transactions on JDBC Flows**, focuses on defining **units of work that can commit/roll back**, thread/channel boundaries, errors, and connection lifecycles.

**Goal:** after this lesson, you can determine when `SELECT + UPDATE + service activator` share a transaction; configure transactional pollers and service transactions; understand rollbacks on errors; and design DB–broker communication without confusing local transactions with distributed transactions.

## 2. Concepts That Must Be Kept Separate

| Concept | Meaning | What it does not mean |
|---|---|---|
| **Local JDBC transaction** | Commits/rolls back operations on a single database resource/transaction manager | Kafka/JMS/HTTP automatically roll back too |
| **Transaction boundary** | Scope where a transaction begins and ends | One `IntegrationFlow` always equals one transaction |
| **Spring transaction context** | Transaction state bound to a thread for synchronous JDBC | Automatically propagates across `ExecutorChannel` |
| **Poller transaction** | Wraps `receive()` and synchronous processing within one poll | Each row gets its own separate transaction |
| **`@Transactional` service** | Applies transaction advice when invoked via the Spring proxy | Automatically applies to self-invocation |
| **Transaction synchronization** | Runs callbacks before/after commit/rollback | Turns external non-DB resources transactional |
| **Retry/redelivery** | Re-runs part or all of a unit of work | Zero duplicate side effects |
| **Idempotency** | Reprocessing the same event without repeating business side effects | Prevents all network redeliveries |
| **Outbox** | Records broker-send work inside the same DB transaction | Kafka producer ACK equals consumer completion |

**ACID** applies within a specific resource/transaction scope. When using `DataSourceTransactionManager` or `JdbcTransactionManager`, a transaction generally spans JDBC operations on **the same `DataSource`** on **the same thread**. Sending a message across a different channel does not automatically extend this scope.

## 3. Transactions Follow Threads, Not IntegrationFlow Names

~~~mermaid
flowchart LR
    A["Transactional poller"] --> B["JDBC inbound source"]
    B --> C["DirectChannel"]
    C --> D["JDBC service activator"]
    D --> E["COMMIT / ROLLBACK same TX"]

    B --> F["ExecutorChannel / QueueChannel"]
    F --> G["Different worker / poller"]
    G --> H["Separate transaction"]
~~~

Spring Integration participates in Spring Framework transactions. With JDBC, transaction context is normally held in `TransactionSynchronizationManager` per active thread.

- **`DirectChannel`:** invokes the subscriber on the sender's thread. When the sender is inside a transaction, synchronous handlers can share that transaction.
- **`ExecutorChannel`:** dispatches onto an executor thread. The sender's transaction **does not propagate automatically** to the worker.
- **`QueueChannel`:** sender enqueues the message; another poller/receiver processes it later. The old JDBC transaction does not reopen automatically.
- **`PublishSubscribeChannel`:** if backed by an executor, subscribers can run on different threads. Never infer synchronicity from channel names.
- **`FluxMessageChannel` or reactive boundaries:** do not automatically preserve JDBC's thread-bound transaction propagation.

**Key conclusion:** a flow may look like one continuous arrow on a diagram while actually containing **multiple independent transactions** because it crosses asynchronous boundaries.

## 4. Transactional Pollers vs. Message-Driven Endpoints

The JDBC inbound channel adapter is a **polling message source**: a poller invokes `receive()` on schedule to run SELECT/UPDATE. Conversely, JDBC outbound adapters/gateways are **message-driven handlers**: they execute when a message arrives on an input channel.

| Endpoint | When invoked? | Typical transaction wrapping |
|---|---|---|
| JDBC inbound channel adapter | Poller calls `receive()` | Transaction advice on the **poller** |
| JDBC outbound channel adapter | Message dispatched to handler | Caller's transaction or service/advice at handler |
| JDBC outbound gateway | Request message triggers SQL and emits reply | Caller's transaction or advice at needed boundary |
| JDBC stored procedure outbound | Message arrives at handler | Caller/service transaction or endpoint advice |
| JDBC inbound stored procedure | Poller calls procedure | Transaction on the poller |
| Service activator using `JdbcTemplate` | Message arrives at handler method | `@Transactional` on service or outer transaction |

Declaring an `@Bean IntegrationFlow` **does not enable transactions automatically**. You must configure an appropriate `PlatformTransactionManager` and place boundaries around all JDBC operations that must commit or roll back together.

## 5. Three Commit Windows to Distinguish

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant DB as Database
    participant D as DirectChannel handler
    participant K as Kafka producer
    P->>DB: BEGIN
    P->>DB: SELECT NEW rows
    P->>DB: UPDATE rows to CLAIMED
    P->>D: Message<List<Event>>
    D->>DB: INSERT outbox rows
    D-->>P: Return
    P->>DB: COMMIT
    Note over P,DB: DB rows + outbox are durable
    P->>K: (Better: independent outbox publisher)
    K-->>P: ACK per delivery semantics
    Note over K: Target consumer may process later
~~~

Analysis table:

| Failure point | DB state | Appropriate action |
|---|---|---|
| Error during SELECT | Unchanged if no DML ran | Roll back / wait for retry |
| Error after UPDATE before COMMIT | UPDATE can roll back | Re-read rows on next poll |
| Error inserting outbox in same transaction | Both UPDATE and outbox roll back | Retry whole batch |
| Crash after DB COMMIT, before publish | Outbox durable, not yet sent | Publisher reads outbox after restart |
| Broker receives, crash before marking published | Outbox event may remain pending | Resend with stable ID / idempotent consumer |

**Never infer from `send() == true` that every data store and broker committed.** That boolean reflects channel dispatch semantics, not a cross-system commit receipt.

## 6. Setting Up Spring Boot, Database, and Sample Data

Examples use Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC, and H2. Let the Spring Boot BOM manage compatible versions.

~~~groovy
// build.gradle - illustrative dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml for the H2 practice app
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_tx_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
  sql:
    init:
      mode: always
~~~

Suppose `src/main/resources/schema.sql` contains:

~~~sql
CREATE TABLE payment_event (
    id             BIGINT PRIMARY KEY,
    event_id       VARCHAR(80) NOT NULL UNIQUE,
    order_id       VARCHAR(80) NOT NULL,
    state          VARCHAR(24) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_projection (
    order_id       VARCHAR(80) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE event_outbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    event_type     VARCHAR(80) NOT NULL,
    payload_json   VARCHAR(2000) NOT NULL,
    published      BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO payment_event(id,event_id,order_id,state,version)
VALUES (101,'payment-101','ORD-101','NEW',0),
       (102,'payment-102','ORD-102','NEW',0),
       (103,'payment-103','ORD-103','NEW',0);

INSERT INTO order_projection(order_id,status,version)
VALUES ('ORD-101','RECEIVED',0),
       ('ORD-102','RECEIVED',0),
       ('ORD-103','RECEIVED',0);
~~~

This DDL is for demo purposes; in production use Flyway/Liquibase migrations. H2 does not faithfully reproduce the locking, commit ordering, and dialects of PostgreSQL, Oracle, SQL Server, or MySQL.

## 7. DataSource and PlatformTransactionManager

Spring Boot with `spring-boot-starter-jdbc` normally auto-configures `DataSource`, `JdbcTemplate`, and a JDBC transaction manager when auto-configuration conditions are met. Do not declare a second transaction manager if an appropriate bean already exists.

When you want explicit management over a JDBC resource, you can define:

~~~java
package com.example.jdbc.transaction;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcTxConfiguration {

    // Only declare if the app does NOT already have an appropriate manager.
    @Bean("jdbcTransactionManager")
    public PlatformTransactionManager jdbcTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

`JdbcTransactionManager` is a JDBC transaction manager implementation extending/enhancing `DataSourceTransactionManager` to support exception translation on commit/rollback. `DataSourceTransactionManager` is also a valid choice for synchronous JDBC.

**Never declare two auto-injectable managers** without specifying `@Primary`/`@Qualifier` or an explicit `transactionManager`. With multiple DataSources, each transaction manager must point to the exact datasource used by the JDBC adapters and repositories.

### 7.1. Why Does JdbcTemplate Automatically Join Transactions?

`JdbcTemplate` acquires connections through Spring JDBC's `DataSourceUtils`. When a transaction manager has bound a connection to the current thread for that DataSource, `JdbcTemplate` calls on the same thread normally reuse that transaction-bound connection.

~~~text
@Transactional service / transactional poller
  -> TransactionManager BEGIN
  -> DataSourceUtils acquires/binds connection
  -> JdbcTemplate UPDATE ...
  -> JdbcTemplate INSERT ...
  -> TransactionManager COMMIT/ROLLBACK
  -> Connection returns to pool as appropriate
~~~

Never call `connection.commit()` or `connection.close()` directly on a connection managed by Spring's transaction manager. Manually opened JDBC connections bypassing `DataSourceUtils` may not participate in the active transaction as expected.

## 8. JDBC Inbound: SELECT and UPDATE in One Poll Transaction

The Spring Integration JDBC inbound adapter can run a `SELECT` to create messages and an `UPDATE` to mark read rows. A **poller transaction** is the standard way to wrap both SQL statements—and synchronous downstream steps.

~~~mermaid
sequenceDiagram
    participant Poller
    participant Adapter as JdbcPollingChannelAdapter
    participant DB as Database
    participant Handler as DirectChannel handler
    Poller->>DB: BEGIN
    Poller->>Adapter: receive()
    Adapter->>DB: SELECT state='NEW'
    DB-->>Adapter: Rows 101,102
    Adapter->>DB: UPDATE rows to CLAIMED
    Adapter-->>Handler: Message<List<Row>>
    alt Handler completes
        Handler-->>Poller: Return
        Poller->>DB: COMMIT
    else Handler throws exception
        Handler-->>Poller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

Assuming the transaction manager uses the adapter's `DataSource`, `SELECT` and `UPDATE` execute within the same transaction; this is directly documented in the Spring Integration JDBC Reference.

### 8.1. Java DSL for Spring Integration 7.x

Since Spring Integration **7.0**, the JDBC module provides `Jdbc.inboundAdapter(...)` in `org.springframework.integration.jdbc.dsl.Jdbc`.

~~~java
package com.example.jdbc.transaction;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class PaymentPollingFlow {

    public record PaymentRow(
        long id, String eventId, String orderId) { }

    @Bean
    public IntegrationFlow pollPayments(
            DataSource dataSource,
            PlatformTransactionManager jdbcTransactionManager,
            PaymentOutboxWriter outboxWriter) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                        "SELECT id, event_id, order_id "
                      + "FROM payment_event "
                      + "WHERE state='NEW' ORDER BY id")
                    .maxRows(20)
                    .rowMapper((rs, n) -> new PaymentRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getString("order_id")))
                    .updateSql(
                        "UPDATE payment_event "
                      + "SET state='CLAIMED', version=version+1 "
                      + "WHERE id IN (:ids) AND state='NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(PaymentRow.class::cast)
                            .map(PaymentRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(jdbcTransactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .handle(outboxWriter, "stage")
            .get();
    }
}
~~~

**Conditions for this example's guarantee:** `outboxWriter.stage(PaymentRow)` must only write to the database **using the same `DataSource`** and run synchronously on the poller thread; if it throws and the exception propagates, the poller transaction can roll back both `UPDATE state` and previously staged outbox rows. Here **Kafka is not called inside this transaction**.

`Jdbc.inboundAdapter` builds the message source; `maxRows(20)` caps rows per query; `maxMessagesPerPoll(1)` caps `receive()` calls per trigger, not row count. `.split()` splits `Message<List<PaymentRow>>` into individual `PaymentRow` messages, still processed synchronously when no async channel is present.

**Do not treat this SELECT-then-UPDATE pattern as an atomic claim across multiple pods.** Two pods can SELECT the same row before either UPDATE runs. For exclusive ownership, use vendor-specific row locks/`SKIP LOCKED`, atomic claim/RETURNING, or leases combined with idempotency.

### 8.2. Synchronous Java Outbox Writer Handler

~~~java
package com.example.jdbc.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class PaymentOutboxWriter {

    private final JdbcTemplate jdbc;

    public PaymentOutboxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(PaymentPollingFlow.PaymentRow row) {
        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, aggregate_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            row.eventId(),
            row.orderId(),
            "order.payment.received",
            "{\"orderId\":\"" + row.orderId() + "\"}");
    }
}
~~~

`event_id` is a business key stable across retries. The JSON snippet is for demo only assuming safe `orderId` formatting; in production use a JSON serializer/DTO instead of concatenating JSON strings from untrusted input.

**Key point:** the handler writes to the **outbox**; a separate publisher sends to Kafka/JMS *after commit*. If staging the second row throws `DataAccessException`, the poller transaction rolls back earlier rows when sharing the same resource and thread, avoiding marking `CLAIMED` without staged work to send.

## 9. Spring Integration 6.x: JdbcPollingChannelAdapter and Pollers

Prior to Spring Integration 7.0, use `JdbcPollingChannelAdapter` directly:

~~~java
package com.example.jdbc.transaction;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyJdbcPollingConfiguration {

    @Bean
    public IntegrationFlow legacyPolling(
            DataSource dataSource,
            PlatformTransactionManager jdbcTransactionManager,
            PaymentOutboxWriter outboxWriter) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, order_id "
              + "FROM payment_event WHERE state='NEW' ORDER BY id");

        source.setRowMapper((rs, n) ->
            new PaymentPollingFlow.PaymentRow(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("order_id")));
        source.setMaxRows(20);
        source.setUpdateSql(
            "UPDATE payment_event SET state='CLAIMED' "
          + "WHERE id IN (:id) AND state='NEW'");

        // With a custom RowMapper returning a Java record, configure a factory
        // instead of relying on default Map property projection.
        source.setUpdateSqlParameterSourceFactory(result -> {
            var rows = (java.util.List<?>) result;
            var ids = rows.stream()
                .map(PaymentPollingFlow.PaymentRow.class::cast)
                .map(PaymentPollingFlow.PaymentRow::id)
                .toList();
            return new MapSqlParameterSource("id", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(jdbcTransactionManager)))
            .split()
            .handle(outboxWriter, "stage")
            .get();
    }
}
~~~

This is an **alternative**; do not register both 7.x and 6.x flows on the same table simultaneously without concurrency design. In 6.x, `JdbcPollingChannelAdapter` resides in `org.springframework.integration.jdbc`; the JDBC Java DSL factory starts in 7.x.

## 10. XML Transactional Poller: SELECT + UPDATE

~~~xml
<!-- Fragment; context has int and int-jdbc namespaces. -->
<int:channel id="paymentBatches"/>

<int-jdbc:inbound-channel-adapter
    id="paymentsFromDatabase"
    data-source="dataSource"
    channel="paymentBatches"
    query="SELECT id, event_id, order_id
           FROM payment_event
           WHERE state='NEW'
           ORDER BY id"
    update="UPDATE payment_event
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'"
    max-rows="20">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional
            transaction-manager="jdbcTransactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

In XML form, `:id` uses the default naming convention to extract IDs from SELECT. Downstream needs a splitter to get one message per row; for transaction rollback on downstream failures, downstream handlers must be synchronous on the same thread and not swallow exceptions.

There is no need to add `@Transactional` to each handler if a poller transaction already spans all local JDBC work. However, nested transactions with differing propagation settings can alter behavior (see section 14).

## 11. DirectChannel: Synchronous Stages Can Share the Transaction

Example:

~~~text
Transactional poller BEGIN
  -> JDBC source SELECT/UPDATE
  -> DirectChannel
  -> Splitter
  -> DirectChannel
  -> @ServiceActivator writes outbox
  -> Return
Transactional poller COMMIT
~~~

Because no thread switch occurs, transaction resources can be shared. A `DataAccessException` in the outbox writer, if thrown out of the handler, causes the poller to roll back `SELECT/UPDATE` and other DML statements.

Never judge transactions from a **flow diagram** alone. Verify at runtime: thread, transaction manager, DataSource, exception propagation, propagation policy, and actual COMMIT.

### 11.1. ExecutorChannel: Async Handoff Ends the Prior Transaction Scope

~~~text
Poller BEGIN
  -> SELECT/UPDATE
  -> ExecutorChannel dispatches message to worker
Poller COMMIT

Different worker:
  -> JDBC outbox writer
  -> Exception
  -> May use separate transaction / errorChannel
~~~

**Result:** `CLAIMED` status already committed on the poller, while the outbox error occurred on the worker thread. Do not assume that error travels back to the poller to trigger rollback.

Use `ExecutorChannel` with bounded executors/queues and a **dedicated** transaction on the worker if needed. When “no lost work” is required, stage work into a persistent outbox/work queue **before** the async boundary.

### 11.2. QueueChannel: Send and Receive Decoupled in Time

`QueueChannel` buffers messages for another poller to consume, letting execution outlive the original transaction. An in-memory queue **is not a durable work store** across crashes. For durable queues, use a broker or persistent message store with matching semantics; you still must manage ACK/transaction boundaries across the two resources.

## 12. Transactions on Message-Driven JDBC Handlers

A JDBC outbound adapter/gateway is not automatically wrapped by a JDBC inbound poller if callers come from another channel. A handler can inherit a transaction from its calling service or be wrapped with `@Transactional` at a service boundary.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS inbound"] --> B["MessageChannel"]
    B --> C["Transactional service"]
    C --> D["JdbcTemplate UPDATE"]
    C --> E["JdbcTemplate INSERT outbox"]
    D --> F[("Same DB TX")]
    E --> F
    C --> G["Return DTO/result"]
~~~

Example service updating an order, inserting into the outbox, and committing **when the method finishes**:

~~~java
package com.example.jdbc.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {

    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public PaymentResult apply(String eventId, String orderId) {
        int updated = jdbc.update(
            "UPDATE order_projection "
          + "SET status='PAID', version=version+1 "
          + "WHERE order_id=? AND status='RECEIVED'",
            orderId);

        if (updated != 1) {
            throw new IllegalStateException(
                "Order not found, already paid or state changed");
        }

        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, aggregate_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            eventId, orderId, "order.paid",
            "{\"orderId\":\"" + orderId + "\"}");

        return new PaymentResult(orderId, updated);
    }

    public record PaymentResult(String orderId, int updatedRows) { }
}
~~~

If the `event_outbox` INSERT violates UNIQUE and the exception propagates, the transaction rolls back the `order_projection` UPDATE by default. On message redelivery, look up the event ID/aggregate state to distinguish **an already-succeeded duplicate** from **a conflict**; this example intentionally throws on updated count 0 so learners see the boundary clearly.

### 12.1. Exposing the Method with `@ServiceActivator`

~~~java
package com.example.jdbc.transaction;

import java.util.Map;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PaymentMessageHandler {

    private final PaymentService service;

    public PaymentMessageHandler(PaymentService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "paymentRequests",
        outputChannel = "paymentReplies")
    public PaymentService.PaymentResult handle(
            Map<String, String> payload) {
        return service.apply(
            payload.get("eventId"), payload.get("orderId"));
    }
}
~~~

**Precondition:** `PaymentService` is a Spring bean invoked **through its proxy** from another handler bean. `@Transactional` on the service creates a transaction boundary even when the handler is not invoked by a transactional poller. `paymentReplies` must have an appropriate consumer/reply context; a reply produced at the handler level does not prove an outer caller transaction committed.

## 13. JDBC Outbound Gateway: Replies Arriving Before Commit Can Mislead

The JDBC outbound gateway takes a request message, executes SQL, and emits a reply containing update counts, generated keys, or SELECT rows. **A reply from the handler** and **commit of an outer transaction** are not a single atomic event.

~~~text
@Transactional outerService:
  -> Send request to JDBC outbound gateway
  -> UPDATE produces reply {UPDATED=1}
  -> outerService continues processing
  -> A later step throws RuntimeException
  -> Outer JDBC transaction ROLLS BACK
~~~

The `UPDATED=1` reply merely indicates SQL affected one row **before the rollback**; it is **not a commit receipt**. With generated keys, the database may have allocated a key while the row itself ultimately rolls back.

| SQL | Typical reply | Watch out for |
|---|---|---|
| DML without generated keys | Map `{UPDATED=n}` | Can be rolled back after reply |
| INSERT with generated keys | Driver-dependent map/list of keys | Generated key does not prove COMMIT |
| SELECT | Single row or list per `maxRows` | Data depends on snapshot/isolation |
| UPDATE + SELECT | SELECT result as payload | Does not automatically return a count + rows tuple |

Java DSL example for **Spring Integration 7.x**:

~~~java
// Fragment inside @Bean IntegrationFlow; dataSource is injected.
return IntegrationFlow.from("statusCheckRequests")
    .handle(Jdbc.outboundGateway(dataSource,
        "UPDATE order_projection "
      + "SET status = :payload[newStatus], version=version+1 "
      + "WHERE order_id = :payload[orderId] "
      + "  AND version = :payload[expectedVersion]"))
    .channel("statusCheckReplies")
    .get();
~~~

The request payload is assumed to be a `Map` with `orderId`, `newStatus`, and `expectedVersion`. `UPDATED=0` can indicate no matching row or a version conflict without raising a SQL exception. If you need to update a business table **and** write to an outbox, place both inside one service transaction or synchronous JDBC stage rather than handing the reply off to another worker and hoping they stay atomic.

## 14. @Transactional: Proxies, Rollback Rules, and Propagation

By default, `@Transactional` works via Spring proxies. **Self-invocation** of a method within the same object usually bypasses transaction advice:

~~~java
@Service
public class SelfInvocationExample {

    public void run() {
        update(); // Does not go through Spring's @Transactional proxy.
    }

    @Transactional
    public void update() {
        // JDBC DML...
    }
}
~~~

Fix: invoke the transactional method through **another Spring bean** (injected via proxy) or use `TransactionTemplate`.

### 14.1. Which Exceptions Trigger Rollback?

Normally Spring rolls back when a `RuntimeException` or `Error` escapes a transactional method. Checked exceptions require `rollbackFor` or matching rollback rules:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importPayments() throws Exception {
    // JDBC updates + outbox
}
~~~

A critical trap is **catching an exception and returning normally**:

~~~java
@Transactional
public void unsafeOperation() {
    try {
        // JDBC DML...
    } catch (RuntimeException ex) {
        // If you only log and return, the transaction interceptor may
        // not see the exception to roll back under default rules.
    }
}
~~~

When business logic requires rollback, rethrow the exception or mark rollback-only explicitly. Never catch `DataAccessException` and turn a connectivity error into “data not found”.

### 14.2. Propagation Changes Scope

| Propagation | Meaning | Risk to watch |
|---|---|---|
| `REQUIRED` | Joins current TX or creates a new one | Common default |
| `REQUIRES_NEW` | Suspends outer TX, starts a new TX | May require an extra connection |
| `SUPPORTS` | Joins if active | Without a TX, DML is not grouped atomically |
| `MANDATORY` | Requires an existing TX | Errors if caller has no transaction |
| `NOT_SUPPORTED` | Runs outside current TX | May auto-commit |
| `NESTED` | Savepoint when supported by resource/manager | Not an independent DB transaction |
| `NEVER` | Disallows running in a TX | Throws if an active transaction exists |

`REQUIRES_NEW` is not a magic “safer” default. When a poller transaction already holds a connection, an inner `REQUIRES_NEW` service can require a second connection; too many pollers with a small pool risks connection starvation.

### 14.3. Isolation

| Isolation | Aspect to evaluate |
|---|---|
| `READ_COMMITTED` | Hides uncommitted rows, yet read-then-update races still happen |
| `REPEATABLE_READ` | Snapshot/locking behavior depends on DB vendor |
| `SERIALIZABLE` | Strong isolation, but prone to serialization failures/deadlocks |
| `READ_UNCOMMITTED` | DB may allow dirty reads if supported |
| `DEFAULT` | Follows DB default configuration |

No single isolation level turns JDBC and Kafka into a distributed transaction. For multi-instance polling, you usually still need database locking/atomic claiming/idempotency.

## 15. Optimistic Locking and Update Counts

A `version` column detects concurrent update conflicts:

~~~sql
UPDATE order_projection
SET status = :newStatus,
    version = version + 1
WHERE order_id = :orderId
  AND version = :expectedVersion;
~~~

`updated=1` means the predicate matched at UPDATE time; `updated=0` means the order is missing, its version changed, or a different transition was already applied. Inspect domain state and processed-event IDs before deciding whether to ACK or retry.

~~~text
Attempt 1: event e-101 transitions order RECEIVED -> PAID, version 0 -> 1
DB COMMIT succeeds, but Kafka/JMS source not ACKed yet
Attempt 2: event e-101 is redelivered
UPDATE WHERE version=0 -> 0 rows
~~~

On the second attempt, returning `0` is not necessarily a failure; if it is the exact same event ID and target state already reached, it can be treated as an idempotent duplicate. If a different event causes the version conflict, never silently ACK it as processed.

**Transactions** govern commit/rollback across SQL steps; **optimistic locking** governs whether a concurrent UPDATE is valid. They complement rather than replace each other.

## 16. TransactionTemplate for Explicit Boundaries

`TransactionTemplate` fits when you want exact JDBC transaction boundaries without relying on proxy annotations:

~~~java
package com.example.jdbc.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ExplicitPaymentTransaction {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    public ExplicitPaymentTransaction(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.tx = new TransactionTemplate(manager);
    }

    public int markPaidAndStage(String orderId, String eventId) {
        return tx.execute(status -> {
            int changed = jdbc.update(
                "UPDATE order_projection SET status='PAID', "
              + "version=version+1 "
              + "WHERE order_id=? AND status='RECEIVED'",
                orderId);
            if (changed != 1) {
                throw new IllegalStateException(
                    "Order already processed or conflicting");
            }

            jdbc.update(
                "INSERT INTO event_outbox "
              + "(event_id, aggregate_id, event_type, payload_json) "
              + "VALUES (?, ?, ?, ?)",
                eventId, orderId, "order.paid",
                "{\"orderId\":\"" + orderId + "\"}");
            return changed;
        });
    }
}
~~~

Both DML statements run in the same local JDBC transaction when template and manager share the `DataSource`. Never start a transaction on thread A, dispatch DML via an `ExecutorChannel` to thread B, and expect A's transaction context to follow.

## 17. Poller Transaction Advice and Retry Advice

Java DSL syntax:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

XML syntax:

~~~xml
<int:poller fixed-delay="5000" max-messages-per-poll="1">
    <int:transactional
        transaction-manager="jdbcTransactionManager"/>
</int:poller>
~~~

Transaction advice differs from sprinkling `@Transactional` on arbitrary beans. When a poller combines **retry advice, transaction advice, and metrics/tracing advice**, advice ordering determines whether retries occur **inside** or **outside** the transaction.

For example:
- Retrying after a deadlock normally requires **rolling back first, then re-running the entire transactional unit in a fresh transaction**.
- Retrying one SQL statement inside an already rollback-only transaction cannot salvage that transaction.
- If an advice catches an exception and swallows it, the transaction manager may treat the poll as normal and COMMIT.

Never attach blind retries to `DuplicateKey`, SQL grammar, or validation errors. Base retry policies on `DataAccessException` subtypes, bounded attempts, and backoff/jitter.

## 18. TransactionSynchronization and afterCommit

Spring lets you register callbacks when a transaction completes:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

// Use only when transaction synchronization is active.
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Runs after local JDBC COMMIT.
        }
    });
~~~

Spring Integration provides `TransactionSynchronizationFactory` for polling endpoints, supporting `before-commit`, `after-commit`, and `after-rollback`:

~~~xml
<int:transaction-synchronization-factory id="syncFactory">
    <int:after-commit expression="payload" channel="committedChannel"/>
    <int:after-rollback expression="payload" channel="rolledBackChannel"/>
</int:transaction-synchronization-factory>
~~~

The poller can reference `synchronization-factory="syncFactory"` inside `<int:transactional ... />`. These callbacks **synchronize actions with transaction outcomes**, but they do not turn HTTP/Kafka/JMS into rollback-capable resources.

**Crash window:** DB COMMIT finishes, then the app dies before the `afterCommit` callback sends to Kafka. In-memory callbacks are not a durable work queue. For data that must never be lost, use a **transactional outbox** rather than relying solely on `afterCommit` callbacks.

`afterRollback` must not assume it can reuse the just-rolled-back transaction to write durable audit rows. If you need to persist failure metadata to the DB, use a separate transaction with clear semantics.

## 19. Outbox: Properly Separating DB Transactions from Broker Publishing

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS source"] --> B["Transactional service"]
    B --> C["UPDATE business tables"]
    B --> D["INSERT event_outbox"]
    C --> E[("DB COMMIT")]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Kafka / JMS broker"]
    G --> H["Idempotent consumer"]
~~~

**Inside one DB transaction**: write business changes + outbox and commit together. **In a separate publisher**: read pending outbox rows, send to broker, and mark `published=true` per retry/ACK contract.

If the broker receives the message successfully and the publisher crashes before setting `published`, the message may be sent again. Thus outboxes normally provide **at-least-once delivery** paired with consumer idempotency; they do not automatically guarantee end-to-end exactly-once effects across every system.

### 19.1. Kafka Listeners and JDBC Transactions

A practical sequence:

1. Receive Kafka event `eventId=e-101`.
2. Inside a local JDBC transaction, validate the event, write business changes, record the processed-event ID, and insert the outbox record.
3. COMMIT JDBC.
4. Commit Kafka offset/ACK per listener container semantics.

If the application dies after step 3 but before step 4, Kafka can redeliver. The processed-event unique constraint ensures the second pass **creates no duplicate side effect**. If you commit the Kafka offset before DB COMMIT, a crash can drop the event even though the offset advanced.

Spring Kafka provides mechanisms for transaction coordination, yet it does not provide an XA distributed transaction spanning DB+Kafka by default. Verify commit/rollback ordering and recovery behavior in your exact version.

### 19.2. JMS Is Not Automatically XA with JDBC

A transacted JMS session only manages transactions on the JMS broker/session. A local `DataSourceTransactionManager` does not commit or roll back JMS automatically. When true atomic multi-resource commits are required, design JTA/XA with compatible resource managers; many applications prefer outbox + idempotent receivers to avoid that complexity.

## 20. SELECT–UPDATE Transactions Still Do Not Prevent Two Pollers from Reading the Same Row

~~~text
Pod A SELECT row 101 (state=NEW)
Pod B SELECT row 101 (state=NEW)
Pod A UPDATE row 101 -> CLAIMED, COMMIT
Pod B UPDATE row 101 WHERE state=NEW -> 0 rows
Pod B still holds row 101 in its stale result list
Pod B may emit event 101 twice
~~~

Even when each poll runs in a local JDBC transaction, `SELECT` normally grants no exclusive ownership without an appropriate locking/claiming policy.

Production options include:
- `SELECT ... FOR UPDATE SKIP LOCKED` in PostgreSQL inside the same transaction;
- Atomic `UPDATE ... RETURNING` or SQL Server `UPDATE ... OUTPUT` per vendor;
- `claimed_by`/`lease_until` leases and fencing tokens;
- Partition ownership assigning distinct key subsets;
- Outbox + stable event IDs + idempotent consumers.

Never hold DB locks open waiting on remote HTTP/Kafka calls. Claim/stage work durably in a short transaction, COMMIT, and handle remote delivery through publishers/retries.

## 21. Deadlocks, Timeouts, and Retries After Rollback

| Failure or outcome | Should you retry? | Rule |
|---|---|---|
| Deadlock/serialization | Yes, bounded | Roll back full TX, start fresh TX, backoff |
| Transient DB connection error | Conditionally | Check outcome if near COMMIT |
| Invalid SQL syntax/schema | No | Fix query/migration |
| Duplicate key with same event ID | Business-dependent | Distinguish duplicate vs. conflict |
| UPDATE version mismatch | Business-dependent | Re-read latest state; never retry forever |
| Broker publish timeout | Conditionally | Stable event ID and reconciliation |
| Payload missing required field | No | Validation/DLQ |

A JDBC transaction **may have committed** while the response/connection dropped, leaving the caller uncertain of the outcome. Blind retries risk repeating side effects; use unique event IDs, idempotency, and reconciliation.

`JdbcTemplate` typically throws `DataAccessException`; Spring Integration may wrap it in `MessagingException` or route to `ErrorMessage`/`errorChannel` depending on the handler and thread. Never treat every `errorChannel` message as proof the transaction rolled back; verify whether exceptions are caught before or after transactional advice.

## 22. Multiple DataSources and Transaction Managers

If an application has separate orders and audit databases, a plain `@Transactional` does not make both atomic:

~~~java
// Pseudo API: illustrative only for transaction boundaries.
@Transactional(transactionManager = "ordersTransactionManager")
public void updateAcrossDatabases(String orderId) {
    // ordersJdbcTemplate: orders DB, inside orders local TX
    // auditJdbcTemplate: separate audit DB, NOT automatically in the same TX
}
~~~

`DataSourceTransactionManager`/`JdbcTransactionManager` binds to **a single `DataSource`**. Operations against the second DB may run in autocommit or a separate transaction manager, yielding unsynchronized commits.

Suitable options: use one database when a local atomic unit is required; use outbox/saga/compensation when eventual consistency works; or design XA/JTA when true atomic commits across multiple resources are strictly required and supported by every resource.

### 22.1. `REQUIRES_NEW` and Held Connections

If an outer transaction holds one connection while an inner `REQUIRES_NEW` needs another, 10 poller threads with a pool size of 10 can all hold connections and deadlock waiting for inner transactions. The lesson is to size **pool capacity, transaction duration, and propagation** carefully rather than scaling concurrency blindly.

## 23. Timeouts, `readOnly`, and Blocking I/O

| Setting | Where it applies | Meaning |
|---|---|---|
| Hikari `connectionTimeout` | Connection pool | Wait time to acquire a connection |
| `JdbcTemplate.queryTimeout` | JDBC statement | Statement timeout per driver/DB |
| `@Transactional(timeout=...)` | Transaction manager | Transaction timeout per resource/infrastructure support |
| Gateway reply timeout | Messaging request–reply | Time caller waits for a reply |
| HTTP/Kafka send timeout | External client/broker | Does not roll back an already-committed JDBC TX |

`@Transactional(readOnly=true)` is generally a read optimization hint/contract, **not an authorization guard** guaranteeing the DB rejects UPDATEs. For JDBC inbound `SELECT` plus `UPDATE` marking rows, configure a **read-write** transaction.

JDBC and `JdbcTemplate` are **blocking I/O**. In WebFlux, never call them on the Reactor Netty event loop. When integrating with reactive endpoints, run the entire synchronous `@Transactional` JDBC method inside a bounded worker boundary, or adopt R2DBC if end-to-end reactive transactions are needed. Never split JDBC calls of one transaction across multiple threads assuming they share a connection.

## 24. Testing Local JDBC Rollback with TransactionTemplate

A test should verify **database state after the transaction** rather than merely asserting a method was called. Example using Spring Boot + H2:

~~~java
package com.example.jdbc.transaction;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class LocalJdbcTransactionTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void rollbackRestoresBusinessAndOutbox() {
        String orderId = "ORD-TX-" + UUID.randomUUID();
        String eventId = "evt-" + UUID.randomUUID();

        jdbc.update(
            "INSERT INTO order_projection(order_id,status,version) "
          + "VALUES (?, 'RECEIVED', 0)",
            orderId);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                jdbc.update(
                    "UPDATE order_projection SET status='PAID' "
                  + "WHERE order_id=?",
                    orderId);
                jdbc.update(
                    "INSERT INTO event_outbox "
                  + "(event_id,aggregate_id,event_type,payload_json) "
                  + "VALUES (?,?,?,?)",
                    eventId, orderId, "order.paid", "{}");
                throw new IllegalStateException("failure before commit");
            }));

        String dbStatus = jdbc.queryForObject(
            "SELECT status FROM order_projection WHERE order_id=?",
            String.class, orderId);
        assertEquals("RECEIVED", dbStatus);

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM event_outbox WHERE event_id=?",
            Integer.class, eventId);
        assertEquals(0, count);
    }
}
~~~

The test uses unique IDs to avoid colliding with fixtures and **does not place `@Transactional` on the test method**, because an auto-rolling-back test transaction can mask commit issues. Post-exception assertions query the database after `TransactionTemplate` completes.

### 24.1. Testing Successful COMMIT

~~~java
// Code fragment in a test with jdbc/manager/orderId/eventId initialized.
int updated = new TransactionTemplate(manager).execute(status -> {
    int rows = jdbc.update(
        "UPDATE order_projection SET status='PAID' "
      + "WHERE order_id=? AND status='RECEIVED'",
        orderId);
    jdbc.update(
        "INSERT INTO event_outbox "
      + "(event_id,aggregate_id,event_type,payload_json) "
      + "VALUES (?,?,?,?)",
        eventId, orderId, "order.paid", "{}");
    return rows;
});
~~~

After the transaction finishes, query both the row and outbox from an independent JDBC operation to confirm commit. This snippet is not a standalone app; variables must be initialized in the test.

## 25. Testing Rollback in a JDBC Inbound Flow

For the section 8 flow, an integration test should seed `NEW` rows, run **exactly one poll** inside a transaction, let the handler write outbox rows and throw on the second element, and verify all rows remain `NEW` after rollback.

| Test | Assertion needed |
|---|---|
| SELECT + UPDATE + sync writer succeed | `CLAIMED` and outbox commit together |
| Sync handler throws `RuntimeException` | UPDATE and outbox roll back |
| Handler catches error and returns | Can COMMIT; verify design intent |
| `ExecutorChannel` inserted before writer | Poller DB TX commits without waiting for worker |
| `QueueChannel` + separate poller | Consumer runs in an independent transaction |
| Duplicate outbox event ID | Explicit unique constraint/error policy |
| 2 instances SELECT same row | Does not imply exclusive ownership |
| Wrong transaction manager for DataSource | Test exposes unintended autocommit |
| Metadata checkpoint + outbox in local TX | Both roll back together on failure |
| Broker received but source un-ACKed | Redelivery occurs; idempotency handles it |

**Test setup:** disable unrelated background pollers; avoid parallel tests mutating the same tables; control schedulers, fixture data, consumers, and error channels.

### 25.1. Using TransactionTemplate to Simulate Synchronous Receive

To test a source directly without waiting on a scheduler, call `JdbcPollingChannelAdapter.receive()` and process the payload inside an explicit `TransactionTemplate`, then throw an exception to verify rollback. This tests **JDBC operations sharing a transaction**, though it does not test all `SourcePollingChannelAdapter` retry/error wiring; include a test running the real poller too.

### 25.2. Testing Async Boundaries

Insert an `ExecutorChannel` or `QueueChannel` with a test-controlled consumer. Let the poller COMMIT first, then have the worker throw. Expect that the worker failure **cannot roll back the already-committed `CLAIMED` status**. When zero data loss is required, test outbox/lease/recovery rather than only testing `errorChannel`.

## 26. Testing Database Concurrency and Crash Windows

H2 suffices for local transactions, not for verifying locking/isolation on production DBs. Use Testcontainers or a vendor-matched test database for:

1. Two transactions updating the same row with expected versions.
2. Deadlock/serialization conflicts and full-transaction retries.
3. Vendor `FOR UPDATE SKIP LOCKED`, `UPDATE ... RETURNING`, or `OUTPUT`.
4. Crashes after claim/DB commit before broker publishing.
5. Broker ACK completing while the app dies before setting outbox `published`.
6. `REQUIRES_NEW` under small connection pools and high concurrency.
7. Nested transactions/savepoints if used by the application.
8. Source/poller wired to a transaction manager for the wrong database.
9. Kafka/JMS redelivery and processed-event ID uniqueness.
10. Combining polling with before/after-commit transaction synchronization.

**Never claim exactly-once because one test saw no duplicates.** Perform fault injection across crash windows and inspect business state, outbox, broker, retry backlogs, and processed-event stores.

## 27. Monitoring Transactions in Production

Useful metrics:
- Transaction counts, commit/rollback counts, transaction durations, rollback-only outcomes.
- SQL SELECT/UPDATE latency, `UPDATED=0` counts, deadlocks, lock waits, query timeouts.
- Hikari active/idle/pending connections, connection acquire time, and acquire failures.
- Poll frequency, rows/poll, `maxMessagesPerPoll`, queue depth, and consumer lag.
- Outbox pending count/oldest age, publish attempts, broker ACKs, and duplicate event IDs.
- `errorChannel`/DLQ counts, retry rates, failed message correlation IDs.
- Rows stuck in `CLAIMED`, expired leases, recovery attempts.

Never attach per-`orderId` or per-`eventId` values as high-cardinality metric tags. Put IDs in logs/traces with PII and secrets scrubbed.

### 27.1. Inspecting Active Thread Transactions

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
~~~

This is only a debugging signal; `true` does not prove the transaction manager bound the right `DataSource` or that the final commit succeeded. Try it in a `DirectChannel` handler vs. an `ExecutorChannel` worker to observe that thread-bound transactions do not propagate automatically.

## 28. Security and Stability

- Bind SQL parameters with `PreparedStatement`/named parameters; never concatenate message inputs into SQL.
- Restrict DB account privileges to required tables/procedures; use TLS and a secret manager.
- Avoid holding transactions open while waiting on slow network I/O or Kafka callbacks.
- Bound Hikari pools, executors, poller counts, batch sizes, statement timeouts, and retry attempts.
- In multi-tenant apps, authorize tenants before DML; never trust client-supplied `tenantId` headers.
- Use unique business event IDs, optimistic versions, atomic claims, or outboxes for redelivery/concurrency.
- Protect outbox/metadata schema migrations when old and new deployments run concurrently.

## 29. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “Having an IntegrationFlow means having a transaction” | Boundaries must be configured |
| “`@Transactional` on a self-called method always applies” | Self-invocation normally bypasses the proxy |
| “JDBC transactions propagate across `ExecutorChannel`” | Thread-bound transactions do not propagate automatically |
| “An in-memory `QueueChannel` is a durable work queue” | Contents are lost on crash |
| “`send()` returning true means DB and broker committed” | Only reflects channel send acceptance |
| “Gateway returning `UPDATED=1` means final commit” | Outer TX can still roll back |
| “Checked exceptions always roll back by default” | Depends on rollback rules |
| “`REQUIRES_NEW` is always safer” | Can exhaust pools and split atomicity |
| “`readOnly=true` blocks every SQL UPDATE” | Not a substitute for DB permissions |
| “`READ_COMMITTED` prevents all races” | Still requires locking/versioning/ownership |
| “SELECT then UPDATE prevents duplicates across pods” | Two pods can SELECT the same row |
| “JDBC `@Transactional` covers Kafka/JMS automatically” | Local TX is not distributed |
| “`afterCommit` callbacks guarantee Kafka events are sent” | Crash after DB COMMIT can still lose the publish |
| “Retrying after timeout never duplicates side effects” | Outcome may have committed; idempotency is needed |
| “JDBC inside WebFlux is non-blocking” | JDBC remains blocking |
| “`@Transactional` test seeing data means COMMIT succeeded” | Test TX may auto-roll back |
| “One transaction manager spans two databases” | Requires XA/JTA or a different design |

## 30. Practice Exercises

1. Set up `payment_event`, `order_projection`, and `event_outbox` on H2.
2. Use `TransactionTemplate` to UPDATE and INSERT, then COMMIT; assert DB state.
3. Throw an exception after INSERT and verify both business and outbox tables roll back.
4. Call `@Transactional` `PaymentService` via `@ServiceActivator`; compare with self-invocation.
5. Build a JDBC inbound `SELECT NEW + UPDATE CLAIMED` flow with a transactional poller in Java DSL 7.x.
6. Build the equivalent flow in Spring Integration 6.x using `JdbcPollingChannelAdapter`.
7. Configure XML `<int:transactional/>` on a poller and specify the matching transaction manager.
8. Make a `DirectChannel` outbox writer throw on the second row and verify the whole batch rolls back.
9. Insert an `ExecutorChannel` before the writer and verify the poller's transaction ends early.
10. Route messages through a `QueueChannel` and a second poller; explain the independent transactions.
11. Call a JDBC outbound gateway returning `UPDATED=1`, then roll back an outer transaction to test commit receipts.
12. Compare `REQUIRED` and `REQUIRES_NEW`, observing rollback behavior when the outer service fails.
13. Shrink pool size with inner `REQUIRES_NEW` calls and observe connection wait behavior.
14. Add a `version` column and send two commands with the same expected version to trigger a conflict.
15. Create a race where two pollers SELECT the same rows; distinguish transactions from ownership.
16. On PostgreSQL, test `FOR UPDATE SKIP LOCKED` and atomic claiming.
17. Build a transactional outbox publisher and simulate crashes before/after broker ACK.
18. Add a processed-event unique constraint and verify Kafka/JMS redelivery causes no duplicate effects.
19. Try `TransactionSynchronization.afterCommit` and analyze the crash window before the callback runs.
20. Simulate a deadlock and retry the entire transaction with backoff.
21. Test `DataAccessException`, `MessagingException`, and `errorChannel` with `DirectChannel` vs. `ExecutorChannel`.
22. Split across two `DataSource`s, select matching transaction managers, and identify when outbox/sagas are needed.
23. Misconfigure `@Transactional(readOnly=true)` on a SELECT+UPDATE flow and observe the behavior.
24. Build a dashboard tracking commits/rollbacks, pool waits, outbox lag, and retries/DLQ.

**Comprehensive scenario:** two pods poll `payment_event`, stage into an outbox, and publish to Kafka. Pod A reads 25 rows and fails on the 3rd outbox row; Pod B concurrently reads some of the same rows. An outbox publisher sends one event and crashes before marking `published`. Design the transactional poller, atomic claim/locking, unique event IDs, retries, and idempotent consumer. Diagram how commit/rollback behavior differs when the flow runs over `DirectChannel` versus `ExecutorChannel`.

## 31. References

- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction boundaries across threads/channels and `TransactionSynchronizationFactory`.
- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT + UPDATE inside transactional pollers, `maxRows`, and `maxMessagesPerPoll`.
- [Spring Integration Reference — Messaging Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): poller transactions, advice, and error flows.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): inbound/outbound adapters, gateways, stored procedures.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter` and `Jdbc.outboundGateway` from 7.0.
- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `UPDATED`, generated keys, and replies.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, propagation, and rollbacks.
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager`, `JdbcTransactionManager`, and transaction synchronization.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` and exception translation.

> **Remember:** transactions on JDBC flows define **commit/rollback boundaries for a unit of work**, not an automatic property of every `IntegrationFlow`. A poller can wrap SELECT, UPDATE, and synchronous handlers on the same thread/`DataSource`, while `ExecutorChannel`/`QueueChannel` split transaction contexts. `@Transactional` and `TransactionTemplate` must match the bean proxy, transaction manager, and thread. When writing to a DB and sending to Kafka/JMS/HTTP, local JDBC transactions do not commit distributedly: use an outbox, stable event IDs, retries, and idempotency.

# JDBC Inbound Channel Adapter Running SELECT in Spring Integration

## 1. Goal: Turning Database Data into Messages

Many integration systems do not actively emit events when data changes. For example, a legacy application only writes orders into an `integration_inbox` table. The new system needs to periodically find unprocessed orders, convert them into messages, and then route them to a service, HTTP gateway, JMS/AMQP, or Kafka. When the source is a **relational database over JDBC**, the **JDBC inbound channel adapter** is a suitable approach.

This is the content of the **Adapter JDBC** chapter in the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; controlling message contracts, errors, and connection lifecycles when exchanging data over files, SFTP, HTTP, JMS, AMQP, Kafka, or databases.

**Main responsibilities of the JDBC inbound channel adapter:**

1. On each poll, execute a SQL `SELECT` query on `DataSource`/`JdbcOperations`.
2. Convert the entire result set into **a single message with a `List<?>` payload**.
3. Optionally execute an `UPDATE` statement to mark rows that have already been selected, preventing them from being picked again on subsequent polls.
4. Send the message through a `MessageChannel` for downstream processing. If you need one message **per row**, add a `splitter`.

~~~mermaid
flowchart LR
    DB[("Database: integration_inbox")] -->|"SELECT on poll"| A["JdbcPollingChannelAdapter"]
    A -->|"Message<List<Row>>"| CH["MessageChannel"]
    CH --> SPL["Splitter"]
    SPL -->|"Message<Row> per row"| H["Business Handler"]
    H --> OUT["HTTP / JMS / Kafka / Service"]
    A -.->|"UPDATE mark as selected"| DB
~~~

**Key point to remember:** the adapter executes `SELECT` on a **polling** schedule, not by listening to a real-time database change stream/CDC. If data must be updated nearly instantaneously with very low latency or at large scale, consider CDC, an outbox combined with a broker, or an event-emitting mechanism directly at the source.

## 2. Distinguishing the JDBC Inbound Adapter from Related Components

| Component | Where does it start? | Contract | Use case |
|---|---|---|---|
| **JDBC inbound channel adapter** | Database `SELECT` via poller | DB → message, one-way | Polling queues in a table, periodic data ingestion |
| JDBC outbound channel adapter | Message already in the flow | Message → SQL write/update, one-way | `INSERT`/`UPDATE` after processing an event |
| JDBC outbound gateway | Message in the flow | SQL request → query/update result → reply message | Need JDBC result for downstream processing |
| JDBC stored procedure adapter/gateway | Stored procedure/function | Follows inbound/outbound endpoint and request-reply semantics | Existing system exposes logic via procedures |
| Direct `JdbcTemplate` usage | Java call from a service | Regular Java result | No poller, channel, or IntegrationFlow needed |
| CDC / transactional outbox | Transaction log or outbox table | Event with change/queue semantics | Need to scale, reduce polling, or achieve more reliable delivery |

The JDBC inbound adapter is **not** an HTTP inbound endpoint. It runs on a schedule driven by a poller; there is no HTTP request to return a response to. Likewise, `JdbcPollingChannelAdapter` uses **synchronous JDBC**. Placing it inside an IntegrationFlow named “reactive” does not turn JDBC into non-blocking I/O.

## 3. Message Contract: SELECT Returns a List, Not Individual Rows

Suppose the database has three unprocessed rows:

| id | order_id | amount | state |
|---:|---|---:|---|
| 101 | ORD-101 | 250000 | NEW |
| 102 | ORD-102 | 120000 | NEW |
| 103 | ORD-103 | 560000 | NEW |

SELECT:

~~~sql
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;
~~~

With the default `RowMapper`, the returned message has the logical structure:

~~~text
Message<List<Map<String, Object>>>
  payload:
    - {id: 101, order_id: "ORD-101", amount: 250000}
    - {id: 102, order_id: "ORD-102", amount: 120000}
    - {id: 103, order_id: "ORD-103", amount: 560000}
  headers:
    id: <message UUID>
    timestamp: <creation time>
~~~

In practice, numeric types, key casing (uppercase/lowercase), and column representation depend on the JDBC driver, SQL aliases, and `RowMapper`; the example only illustrates the data.

After a `splitter`, three messages can be produced:

~~~text
Message<Map<String, Object>> (id=101)
Message<Map<String, Object>> (id=102)
Message<Map<String, Object>> (id=103)
~~~

Do not confuse **`maxRows(20)`** with “at most 20 messages per poll”. The adapter typically returns **one message containing at most 20 rows**, and then a splitter breaks it into multiple messages downstream.

## 4. Setting Up the Project and Sample Database

### 4.1. Dependencies

Use the Spring Boot BOM to manage compatible versions of Spring Integration, Spring JDBC, and the JDBC driver.

~~~groovy
// build.gradle — dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    // Use H2 in-memory only for learning/testing.
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-integration-jdbc` provides `JdbcPollingChannelAdapter` and the JDBC endpoints. `spring-boot-starter-jdbc` provides `DataSource`, Spring JDBC, the transaction manager, and typically uses HikariCP. In production, use the appropriate driver for PostgreSQL, MySQL, SQL Server, or Oracle, along with proper pool configuration and secure credentials.

### 4.2. Configuring DataSource for H2

~~~yaml
# application.yml — illustrating a local Spring Boot application
spring:
  datasource:
    url: jdbc:h2:mem:jdbc-adapter-demo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

With Spring Boot SQL initialization configured, you can place the following DDL/DML into `src/main/resources/schema.sql`; this is an **example file for the learner to create**, not a file generated while writing this documentation:

~~~sql
CREATE TABLE integration_inbox (
    id BIGINT PRIMARY KEY,
    order_id VARCHAR(80) NOT NULL,
    amount DECIMAL(14, 2) NOT NULL,
    state VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_inbox_state_id
    ON integration_inbox(state, id);

INSERT INTO integration_inbox(id, order_id, amount, state)
VALUES
    (101, 'ORD-101', 250000.00, 'NEW'),
    (102, 'ORD-102', 120000.00, 'NEW'),
    (103, 'ORD-103', 560000.00, 'NEW');
~~~

In real projects, use Flyway/Liquibase to manage migrations instead of relying on the application's `schema.sql`. For large databases, consider indexing on filter/sort columns and measuring query plans; do not add indexes arbitrarily on high-write tables.

## 5. Starting with Plain SELECT: Repeated Reads to Observe Data

This is a minimal example to see how the adapter acts as a **MessageSource**. The SELECT query has no UPDATE, so `NEW` rows will be read again on the next poll.

~~~java
package com.example.jdbc;

import java.time.Duration;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
public class ReadOnlyJdbcPollingConfiguration {

    @Bean
    public IntegrationFlow observeInbox(DataSource dataSource) {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource, """
                SELECT id, order_id, amount
                FROM integration_inbox
                WHERE state = 'NEW'
                ORDER BY id
                LIMIT 20
                """);

        return IntegrationFlow
            .from(source, endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .handle((Message<?> message) -> {
                System.out.println("Rows from database: "
                    + message.getPayload());
            })
            .get();
    }
}
~~~

With three `NEW` rows, each poll can produce a message containing the list of three rows. **This is a repeated-read demo**, not a pipeline for processing orders once. If the same application runs both this example and the flow with `UPDATE` in the next section, there will be **two competing pollers**; only enable **one** of them when practicing.

When the SELECT query returns no matching rows, the adapter normally does not produce a message for downstream processing. Do not rely on an “empty list payload” as a business event to be received on every poll; if you want heartbeats/idle-time metrics, set up separate poller monitoring.

## 6. SELECT + UPDATE: Marking Selected Rows

For queue-like data, a plain `SELECT` causes rows to be fetched repeatedly. The JDBC inbound adapter supports `updateSql` to update row status right after the SELECT, before the message is pushed into the flow.

~~~sql
-- Step 1: fetch NEW rows
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;

-- Step 2: mark the ids from the result just selected
UPDATE integration_inbox
SET state = 'CLAIMED'
WHERE id IN (:id)
  AND state = 'NEW';
~~~

The `:id` part is **not standard JDBC `?` syntax**, but a **named parameter** handled by Spring JDBC and Spring Integration. By convention, the adapter extracts the `id` column from the SELECT rows and builds a collection/list of IDs to bind to `:id` in the UPDATE. Therefore:

- The SELECT **must return the `id` column** (or configure a corresponding parameter source).
- The UPDATE statement only applies to IDs from the **current SELECT poll**, not all `NEW` rows in the table.
- When there are no results, you should not construct `IN ()` via manual SQL logic; the adapter handles empty results as part of the poll lifecycle.
- Updating the status to `CLAIMED` does not mean business processing is complete; it only marks the fetch phase. You need to design `DONE`/`FAILED` states and recovery for operations.

### 6.1. Java Configuration with JdbcPollingChannelAdapter

The example below uses the standard Java API of `JdbcPollingChannelAdapter`, without depending on the `Jdbc.inboundAdapter(...)` factory introduced in Spring Integration 7.0.

~~~java
package com.example.jdbc;

import java.time.Duration;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class JdbcInboxIntegrationConfiguration {

    @Bean
    public IntegrationFlow pollNewOrders(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource, """
                SELECT id, order_id, amount
                FROM integration_inbox
                WHERE state = 'NEW'
                ORDER BY id
                LIMIT 20
                """);

        source.setUpdateSql("""
            UPDATE integration_inbox
            SET state = 'CLAIMED'
            WHERE id IN (:id)
              AND state = 'NEW'
            """);

        source.setMaxRows(20);

        return IntegrationFlow
            .from(source, endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofSeconds(2))
                    .maxMessagesPerPoll(1)
                    .transactional(transactionManager)))
            .split() // List<Map<String,Object>> -> individual Message<Map<...>>
            .handle((Message<?> message) -> {
                @SuppressWarnings("unchecked")
                Map<String, Object> row =
                    (Map<String, Object>) message.getPayload();

                // Demo: synchronous processing, no external API calls.
                System.out.printf(
                    "Picked id=%s, order=%s, amount=%s%n",
                    row.get("id"),
                    row.get("order_id"),
                    row.get("amount"));
            })
            .get();
    }
}
~~~

The example assumes Spring Boot has configured a `PlatformTransactionManager` managing **the same DataSource** (usually auto-configured by Boot when there is only one JDBC DataSource). If there are multiple transaction managers, select the right one using `@Qualifier`; do not assume a JMS/Kafka manager can control a JDBC transaction.

Step-by-step walkthrough:

1. The poller triggers the adapter roughly every 2 seconds according to `fixedDelay`.
2. The adapter executes the SELECT for up to 20 rows.
3. The adapter executes the UPDATE, marking the selected IDs as `CLAIMED`, within the **same transaction** when the poller has the appropriate transaction advice.
4. The adapter sends **one message containing `List<Map<String,Object>>`**.
5. `split()` splits the list into one message per map.
6. The handler prints the data, executing synchronously within the sample flow.
7. If no error occurs, the transaction is committed; then the SELECT on the next poll will not see the rows that moved out of `NEW`.

**Do not conclude that rows have “finished business processing” just because they were printed to the screen.** In production, a step to update to `DONE`, audit, or emit an event needs clear commit/ACK boundaries. The example intentionally demonstrates only the SELECT → UPDATE → MessageChannel principle.

## 7. Poller: Execution Schedule and Two Easily Confused Limits

The JDBC inbound adapter is a **polling message source**. In Java DSL, `Pollers.fixedDelay(...)` and `Pollers.fixedRate(...)` determine when `receive()` is invoked.

| Configuration | What is limited | Example |
|---|---|---|
| `fixedDelay(2s)` | Pause between triggers per scheduler | Next poll runs roughly 2 seconds after the previous one completes per schedule |
| `fixedRate(2s)` | Fixed trigger cadence by scheduler clock | If tasks are slow, executor and overlap must be controlled |
| `maxMessagesPerPoll(1)` | Number of `receive()` calls per cycle | Usually **one SELECT execution** per poll |
| `setMaxRows(20)` | Number of rows consumed from the result set of **one SELECT** | Payload can be a list of at most 20 elements |
| `LIMIT 20` / `TOP 20` | Limit directly in SQL/database | DB avoids returning too many rows before client truncation |
| Transactional poller | Transaction spanning the poll and related sync processing | Allows SELECT/UPDATE and sync steps to roll back together |

**`maxMessagesPerPoll` is different from `maxRows`**: increasing `maxMessagesPerPoll` from 1 to 5 can cause the adapter to execute SELECT multiple times consecutively within the same cycle, rather than merely increasing batch size. For the JDBC inbound channel adapter, you usually keep the default equivalent to 1, and adjust SQL `LIMIT`/`TOP` for the desired batch size.

Spring Integration recommends **limiting directly in SQL** using the database's syntax, because `setMaxRows` is a JDBC/adapter-side limit and may not help the database optimize scanning/sorting many rows. For example:

~~~sql
-- PostgreSQL / H2 / MySQL (verify version compatibility):
SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20;

-- SQL Server:
SELECT TOP (20) id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id;
~~~

Do not copy `LIMIT` syntax to SQL Server/Oracle without adjusting it. Without a deterministic `ORDER BY`, polls may pick unpredictable sets of rows. `ORDER BY id` only guarantees ordering *within a query result*, and does not by itself resolve contention among multiple pollers.

## 8. RowMapper: From Default Map to Typed DTOs

By default, the JDBC inbound adapter maps each row to a `Map`, which is convenient when the schema is flexible. When business logic requires a type-safe payload, configure a Spring JDBC `RowMapper<T>`.

~~~java
package com.example.jdbc;

import java.math.BigDecimal;

public record InboxOrder(
    long id,
    String orderId,
    BigDecimal amount) { }
~~~

~~~java
import org.springframework.jdbc.core.RowMapper;

RowMapper<InboxOrder> inboxOrderMapper = (rs, rowNum) ->
    new InboxOrder(
        rs.getLong("id"),
        rs.getString("order_id"),
        rs.getBigDecimal("amount"));

JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource, """
        SELECT id, order_id, amount
        FROM integration_inbox
        WHERE state = 'NEW'
        ORDER BY id
        LIMIT 20
        """);

adapter.setRowMapper(inboxOrderMapper);
~~~

**Important note when combining a custom RowMapper with UPDATE:** `updateSql("... WHERE id IN (:id)")` needs to access the `id` property from the row objects created by the mapper. For a JavaBean class with `getId()` or a type explicitly supported by SpEL, property extraction can be direct. For Java records or custom DTOs, you must **verify how Spring Integration/SpEL property accessors behave in your version**; when needed, configure `SqlParameterSourceFactory` explicitly, or use `Map` as in the full example to avoid surprises. Do not use a custom RowMapper and assume update parameters will work automatically in every case.

Regarding data types, monetary columns should be mapped to `BigDecimal`, not cast to `double` due to floating-point precision errors. Timestamp columns must define timezone/`Instant`/`LocalDateTime` consistently with the JDBC driver and schema.

## 9. Batch ID UPDATE and updatePerRow

Spring Integration provides two ways to apply updates after SELECT:

- **Set-based update**: for example `WHERE id IN (:id)`, where `:id` is the list of IDs from the batch just selected.
- **Per-row update**: enable `setUpdatePerRow(true)`, in which case the update parameter factory operates on **one row** at a time and the SQL must match single-row parameters.

Example illustrating the per-row update option:

~~~java
JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource,
        "SELECT id, order_id FROM integration_inbox WHERE state = 'NEW'");

adapter.setUpdatePerRow(true);
adapter.setUpdateSql(
    "UPDATE integration_inbox SET state='CLAIMED' WHERE id=:id");
~~~

With the default row mapper producing a `Map` containing `id`, the default parameter extraction can read from each row. The advantage is being able to express per-row UPDATE conditions easily; the disadvantage is potentially executing multiple SQL UPDATE statements for a single batch. Measure round trips and verify transaction behavior on a real database.

When column names differ from parameter names or mapping logic is complex, configure `setUpdateSqlParameterSourceFactory(...)` to control how parameter sources are created. Do not concatenate `id` or status values from untrusted input into SQL strings; using named parameters/bind values reduces bugs and SQL injection risks.

## 10. Parameterized SELECT: Avoiding Hardcoded States

For SELECT queries with named parameters, the adapter supports `setSelectSqlParameterSource(SqlParameterSource)`:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;

JdbcPollingChannelAdapter adapter =
    new JdbcPollingChannelAdapter(dataSource, """
        SELECT id, order_id, amount
        FROM integration_inbox
        WHERE state = :state
        ORDER BY id
        LIMIT 20
        """);

adapter.setSelectSqlParameterSource(
    new MapSqlParameterSource("state", "NEW"));
~~~

Here `:state` is bound as a SQL value, not string concatenation. Because the parameter source is used during polling without a caller request message, if you need dynamic states/conditions based on runtime state, you must design a parameter source that updates properly. For `ExpressionEvaluatingSqlParameterSourceFactory`, Spring Integration documents `createParameterSourceNoCache` to avoid caching expression results when values need to change between polls.

**Do not use SQL parameters to substitute table/column names.** Schema identifier positions generally cannot be bound the way SQL values are; if you need dynamic table selection, choose only from a predefined allowlist, never directly from user input.

## 11. Transactions: SELECT, UPDATE, and Synchronous Downstream

The SELECT + UPDATE pattern requires consistency: when fetching a batch and marking it, both SQL statements should run in the same transaction. Spring Integration allows wrapping the poller with a transaction advice; the example in section 6 uses:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
    .maxMessagesPerPoll(1)
    .transactional(transactionManager)
~~~

With a compatible `DataSource` and transaction manager, a poller transaction can cover the SELECT, UPDATE, and downstream handlers running **on the same thread, within the same transaction**. When a synchronous handler throws an exception and the transaction is marked for rollback, the `CLAIMED` update can be rolled back, making the rows appear as `NEW` again on the next poll.

~~~mermaid
sequenceDiagram
    participant Poller as Poller (transaction)
    participant DB as JDBC Database
    participant Flow as Direct flow
    Poller->>DB: BEGIN
    Poller->>DB: SELECT rows NEW
    DB-->>Poller: ids = [101, 102]
    Poller->>DB: UPDATE state=CLAIMED WHERE id IN (...)
    Poller->>Flow: Message<List<Row>>
    alt Synchronous handler succeeds
        Flow-->>Poller: Complete
        Poller->>DB: COMMIT
    else Synchronous handler fails
        Flow--xPoller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

**Transaction boundaries do not automatically extend across all channels**:

- `DirectChannel`/synchronous handlers on the same thread can participate in the open JDBC transaction.
- `ExecutorChannel`, `QueueChannel`, brokers, and reactive publishers can decouple threads/processes/execution timing; the poller transaction does **not** cover side effects that happen asynchronously afterward.
- Sending an HTTP request, JMS message, or Kafka record **does not automatically join a database transaction**. If an external send succeeds and JDBC later rolls back, the external partner may still have received the event.
- If delivery guarantees across crashes are required, you need the **outbox** pattern, idempotent consumers, processing state, and reconciliation; do not treat `@Transactional` as a distributed transaction.

In the section 6 example, the handler only logs to stdout: a printed log line cannot be rolled back if the transaction subsequently fails. This illustrates the limitation of external side effects even in a synchronous flow.

## 12. Multiple Polling Instances: Contention and Duplicate Handling

If an application runs two replicas and each replica executes SELECT `WHERE state='NEW'`, **both can read the same row** before either UPDATE commits. Simply writing `UPDATE ... WHERE state='NEW'` **does not guarantee** each row is processed exactly once; you must examine updated row counts, isolation levels, locks, and race conditions.

Several approaches:

1. **Single active poller:** use leader election, scheduler coordination, or table partitioning. Easy to reason about, but failover must be handled.
2. **Pessimistic row locking:** use a locking SELECT with `SKIP LOCKED` if the database supports it; hold the transaction while claiming.
3. **Atomic claim:** use conditional SQL updates, `UPDATE ... RETURNING`, or a dedicated claim transaction structure depending on database capabilities. Only emit rows that were successfully claimed.
4. **Lease/timeout:** mark `CLAIMED` with `claimed_at` and `owner_id`; provide a mechanism to recover stuck claims after a crash.
5. **Idempotent downstream:** receiving duplicate `orderId`/`eventId` values still produces no duplicate side effects.

PostgreSQL example for multiple workers (**database-specific** syntax, not directly applicable verbatim to H2/MySQL/Oracle):

~~~sql
BEGIN;

SELECT id, order_id, amount
FROM integration_inbox
WHERE state = 'NEW'
ORDER BY id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- UPDATE the fetched ids within the same transaction.
-- COMMIT after establishing the claim/dispatch policy.

COMMIT;
~~~

`SKIP LOCKED` helps avoid row-lock contention between workers, but long transactions can hold locks and impact other operations. If SELECT/UPDATE processes batches and downstream is slow, consider **fast claim-and-commit**, moving processing outside the transaction and using lease/retry/outbox for error recovery.

**Do not promise “exactly once”** solely via JDBC polling. In practice, you usually design **at-least-once** at the event level, paired with idempotent consumers and reconcilable state. If “each order is charged only once” is required, that invariant must be enforced in business logic and the database/receiver, not at the poller alone.

## 13. State Architecture: NEW, CLAIMED, DONE, and FAILED

Having only `NEW` and `CLAIMED` is useful for learning, but insufficient for long-term operations. Define a proper state machine:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: Poll/claim batch
    CLAIMED --> DONE: Business processing success
    CLAIMED --> FAILED: Non-retryable error
    CLAIMED --> NEW: Retry/lease timeout/recovery
    FAILED --> NEW: Controlled manual requeue
    DONE --> [*]
~~~

Commonly useful additional columns:

| Column | Purpose |
|---|---|
| `claimed_at` | Detect expired claims |
| `claim_owner` | Identify which worker/process owns the claim |
| `attempt_count` | Bound retries, decide dead-lettering |
| `last_error_code` | Classify recoverable vs. permanent errors |
| `processed_at` | Audit completion timestamp |
| Unique `event_id` | Idempotency and reconciliation with broker/HTTP |

If processing fails after committing `CLAIMED`, rows risk becoming **permanently stuck** without recovery. You can periodically find `CLAIMED` rows past their lease to return them to `NEW` or transition them to `FAILED`. Combine this with idempotency so retries do not duplicate work already completed before a crash.

## 14. Performance: Avoiding Making the Table a Bottleneck

Polling SELECT incurs cost even when the table has not changed. On large tables, the SELECT needs a **WHERE** clause, indexes, and appropriate batch limits. Write-heavy systems can also suffer if the poller frequently holds transactions or scans many rows.

**SQL and poller checklist:**

- Use an index supporting `WHERE state='NEW'` and `ORDER BY id`; inspect `EXPLAIN`/query plans.
- Select only needed columns instead of `SELECT *`; reduce I/O and mapping overhead.
- Use database-appropriate `LIMIT/TOP/FETCH FIRST`; choose batch size based on latency and downstream capacity.
- Set the poll interval based on acceptable latency; polling too aggressively causes unnecessary query load when the source is empty.
- Configure the `DataSource` pool, JDBC query timeout, and connection lifetime appropriately for the environment.
- Bound concurrency/queues when the splitter forwards data to a service or broker.
- For large row counts, measure the cost of set-based `IN (:id)` UPDATEs versus `updatePerRow` and the driver/database maximum parameter list size.
- Keep transactions short; avoid holding locks during blocking handlers or remote HTTP calls.
- Have a strategy for table cleanup, partitioning/archiving `DONE` rows, and index maintenance.

**Do not confuse `maxRows` with backpressure:** the synchronous JDBC adapter collects results into a list; `maxRows` limits the row count of a single call, rather than turning JDBC into a reactive stream driven by `request(n)`. Non-blocking DB I/O requires a reactive driver/API such as R2DBC, and SQL, transaction, and message delivery semantics still need to be designed.

## 15. Error Handling and Retries When Polling Fails

A poller can fail during SELECT, UPDATE, mapping, message sending, splitting, or business handling. Classify errors instead of retrying infinitely.

| Error type | Example | Handling approach |
|---|---|---|
| Database connectivity | Database restart, pool exhausted | Backoff, health check, bounded retries, observability |
| Invalid SQL | Missing column, wrong table, syntax error | Configuration bug; fix deployment/schema, do not hammer with retries |
| Lock/deadlock | Transaction contention | **Bounded** retry, review isolation/indexes/lock duration |
| Duplicate key | DB unique constraint | Review idempotency and data contract; avoid swallowing errors |
| RowMapper failure | Type parse error, unhandled NULL | Fix mapping/schema, attach an appropriate error flow |
| Synchronous downstream error | Logic throws exception inside transaction | Rolls back if in the same transaction and exception propagates |
| Async/remote downstream error | Kafka/HTTP timeout after DB claim committed | Requires outbox/lease/reconciliation; cannot rely on poller rollback |
| No rows | Empty SELECT result | Normal operation, not an error |

Spring Integration provides `errorChannel` and `ErrorMessage` for applicable endpoints/handlers, but **not every error from a poller is automatically routed to your desired error flow by default**. Configure error handling for the poller, scheduler, transaction advice, and channels appropriate to your version, and test actual failure cases.

When error retries occur at **multiple layers** (scheduler, advice, HTTP client, Kafka listener), total processing attempts for a single row can multiply dramatically. Clearly define who owns the retry budget, backoff timings, final `FAILED` state, and operational alerting.

## 16. Monitoring and Testing

### 16.1. Metrics to Monitor

- Poll count, empty poll count, SELECT/UPDATE duration, and transaction duration.
- Rows per batch, rows transitioning `NEW → CLAIMED`, totals for `NEW/CLAIMED/DONE/FAILED`.
- Latency from `created_at` to poll time and to business completion.
- Connection pool active/idle/waiting counts, query timeouts, lock waits, and deadlocks.
- Rows with expired claims, retry counts, duplicate events blocked, and dead-letter counts.
- Queue/message backlog depth and downstream success/failure rates.

Do not log full sensitive row payloads. Use controlled `eventId`/`orderId` values for correlation, with proper masking/redaction policies.

### 16.2. Minimal Test with H2

You can use `@SpringBootTest` and `JdbcTemplate` to verify database state after the flow has polled. Because the poller runs on a schedule, tests need deadline-based waiting and clear observable conditions; avoid simply calling `Thread.sleep(1000)` and assuming it passes reliably on every machine.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class JdbcInboundSmokeTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void queryShowsSeedDataBeforePolling() {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_inbox",
            Integer.class);

        assertThat(count).isNotNull();
        assertThat(count).isGreaterThanOrEqualTo(0);
    }
}
~~~

**Test limitation:** this is only a smoke test verifying schema/connectivity; an auto-running poller may already have changed `state` before the assertion reads the table. For thorough testing, isolate the poller lifecycle in the test (start/stop the endpoint), initialize controlled seed data, capture messages via a `QueueChannel`/test handler, verify the payload is a `List`, apply a splitter, and assert status updates and rollback when the handler throws an exception.

Recommended test matrix:

| Scenario | Expectation |
|---|---|
| No NEW rows | Poller does not emit business events |
| 3 NEW rows | SELECT returns a list containing 3 rows |
| 25 rows with LIMIT 20 | Selects a batch of at most 20 rows |
| Splitter enabled | Each row becomes an individual downstream message |
| UPDATE succeeds | Selected rows no longer match the next SELECT condition |
| Synchronous handler throws | Poller transaction rolls back JDBC changes when configured properly |
| Async handler fails after commit | No automatic rollback for committed transaction; requires recovery |
| Two apps poll concurrently | No duplicate side effects with claim protocol/idempotency |
| CLAIMED row exceeds lease | Recovery/requeue acts according to policy |
| Database down | Observability, bounded retry/error reporting |

## 17. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “SELECT returns three rows so the adapter emits three messages” | A poll's payload is a **List**; a splitter breaks it apart |
| “Even without UPDATE, rows are only read once” | Plain SELECT can fetch the same rows on every poll |
| “`maxMessagesPerPoll(20)` means 20 rows” | It is the number of `receive()` calls, not rows per query |
| “`setMaxRows(20)` replaces SQL LIMIT and optimizes the query” | It limits rows at JDBC; limit directly in SQL |
| “`UPDATE ... WHERE state='NEW'` guarantees exactly-once across two replicas” | SELECT races still exist; need locking/atomic claim/idempotency |
| “`@Transactional` rolls back HTTP/Kafka after sending” | JDBC transactions do not automatically roll back non-DB side effects |
| “`DirectChannel` and `ExecutorChannel` behave identically for transactions” | Crossing threads/queues can break transaction context |
| “Marking CLAIMED means business processing is finished” | You need DONE/FAILED, leases, and recovery |
| “JDBC polling is real-time CDC” | It periodically executes SELECT, incurring polling lag and query cost |
| “Adding Flux makes JDBC non-blocking” | JDBC remains blocking; Reactive Streams is a different contract |

## 18. Practice Exercises

1. Create `integration_inbox` in H2 with three `NEW` rows and run the plain SELECT from section 5. Observe the same rows appearing across multiple polls.
2. Switch to the SELECT + UPDATE flow in section 6; explain why rows transition to `CLAIMED` and do not appear in the next poll.
3. Disable `split()` to observe a single `Message<List<Map<String,Object>>>`; re-enable it to produce one message per row.
4. Increase data from 3 to 50 rows; compare `maxMessagesPerPoll(1)` against `setMaxRows(20)` and `LIMIT 20`.
5. Modify the SELECT query to `WHERE state=:state` and bind a `MapSqlParameterSource`. Try changing the state value without concatenating SQL strings.
6. Add `RowMapper<InboxOrder>` and verify the `BigDecimal` type; if using UPDATE `:id`, confirm the parameter source works with the DTO.
7. Replace the logging handler with a **synchronous JDBC** handler that updates an audit table. Make the handler throw an exception to test transaction rollback.
8. Switch the handler to an `ExecutorChannel` or queue, trigger an error after commit, and explain why the poller cannot roll back automatically.
9. Run two applications/pollers against the same table; simulate a SELECT race and try a claim/lock strategy or leader election, paired with an idempotent consumer.
10. Add `claimed_at`, `attempt_count`, and lease recovery; simulate a crash between CLAIMED and DONE and perform controlled reprocessing.
11. Measure query duration with a large row count; add an index on `state, id` and compare `EXPLAIN` before and after.
12. Build a downstream outbound HTTP/Kafka flow and design outbox/ACK handling so no data is lost when the remote side is slow or failing.

**Design question:** a service runs three replicas, all polling the same orders table. Each row must emit exactly one business event to Kafka, even if an instance is killed after updating `CLAIMED` but before Kafka acknowledges. How would you use locking/claiming, outbox, recovery, and idempotency? Why is `SELECT + UPDATE` inside a single JDBC transaction alone insufficient to guarantee sending to Kafka exactly once?

## 19. References

- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC adapters/gateways, message stores, and dependencies.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT → `List` payload, default Map mapper, `UPDATE`/`:id`, poller, transactions, `max-rows`, and `max-messages-per-poll`.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc` factory, inbound/outbound specs from **Spring Integration 7.0**.
- [Spring Integration API — JdbcPollingChannelAdapter](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): constructors, `setUpdateSql`, `setRowMapper`, `setSelectSqlParameterSource`, `setMaxRows`.
- [Spring Integration — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): polling endpoints and poller configuration.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): transaction advice, thread boundaries, transaction synchronization, and rollback semantics.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `DataSource`, `JdbcTemplate`, `RowMapper`, and named parameters.

> **Remember:** The JDBC inbound channel adapter **periodically runs SELECT** and emits **one message containing a List of rows**. Use `split()` when you need individual rows; use `UPDATE`, poller transactions, and explicit states to avoid repeated reads. In multi-worker systems or with downstream targets outside the database, add atomic claim/locking, idempotency, outbox, and recovery; a single JDBC transaction does not automatically guarantee end-to-end exactly-once delivery across the entire integration pipeline.

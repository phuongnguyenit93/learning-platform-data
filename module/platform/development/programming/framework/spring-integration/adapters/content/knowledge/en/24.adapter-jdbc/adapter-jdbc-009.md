# Polling Queries and Read State in Spring Integration JDBC

## 1. Problem Statement: Reading Data Periodically Without Endless Re-Reads

An application needs to pull pending synchronization records from a database and push them to Kafka, JMS, AMQP, or HTTP. If it simply runs `SELECT * FROM integration_event WHERE state = 'NEW'` every few seconds without updating state, old records get sent on **every poll**. If it marks rows `DONE` immediately upon reading and the application dies before sending succeeds, events can be **lost**.

Spring Integration's **JDBC inbound channel adapter** addresses the core of this problem: a **poller** runs a SQL `SELECT`; depending on configuration, the adapter runs a follow-up SQL `UPDATE` to change the state of the rows just read; then it emits a `Message<?>` onto a `MessageChannel`.

This lesson belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module's scope is connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, covering files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; this lesson focuses on **polling queries, read states, transactions, error handling, ACKs, and recoverability**.

~~~mermaid
flowchart LR
    P["Poller / Scheduler"] --> A["JDBC inbound channel adapter"]
    A --> S["SELECT eligible rows"]
    S --> DB[("Database")]
    DB --> R["List<Row>"]
    R --> U["UPDATE read/CLAIMED state"]
    U --> DB
    R --> M["Message<List<Row>>"]
    M --> F["Splitter / Transformer"]
    F --> D["Kafka / JMS / HTTP / handler"]
    D -.->|"Separate ACK/commit"| K["Reconciliation and completion"]
~~~

**Core takeaway:** “read” only confirms the system **selected** the row in a `SELECT`. “Claimed” confirms the database recorded ownership/state for the work. “Processed” requires proof from the business step and target system. These three milestones are **not equivalent**.

## 2. Distinguishing SELECT, UPDATE, and Business State

| Operation | Meaning | What is not yet proven |
|---|---|---|
| `SELECT` fetching `NEW` rows | Row was eligible at query time | Row is exclusively owned; downstream finished |
| `UPDATE` from `NEW` to `CLAIMED` | DB records state as being worked by a worker | Kafka/JMS/HTTP received it |
| `UPDATE` from `CLAIMED` to `DONE` | Application recorded success per policy | Every external consumer completed end-to-end |
| Source broker `ACK` | Broker records consumer handled/received message per its rules | DB and broker committed atomically |
| Outbox `PUBLISHED` | Publisher recorded send success per delivery contract | Target consumer necessarily processed exactly once |

A practical state machine:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: Poll + atomic claim
    CLAIMED --> DONE: Processed and confirmed
    CLAIMED --> RETRY: Transient error / lease expired
    RETRY --> CLAIMED: Controlled reclaim
    RETRY --> FAILED: Retries exhausted / bad data
    FAILED --> NEW: Manual replay after fix
    DONE --> [*]
~~~

Not every project needs to store all of these states. With a **transactional outbox**, you can model the lifecycle using `NEW/PUBLISHED` plus an attempt counter and retry timestamp. What is mandatory is that **the contract for states and allowed transitions is crystal clear**.

## 3. How Does the JDBC Inbound Adapter Differ from Manual Polling?

| Solution | Execution driver | How data is fetched | What you must build yourself |
|---|---|---|---|
 `JdbcPollingChannelAdapter` | Spring Integration poller | SELECT + optional UPDATE, returns message | Claim/recovery rules, idempotency, downstream |
 `JdbcTemplate` in `@Scheduled` | Spring scheduler | Repository queries directly | Message creation/dispatch, error flow, transactions |
 JDBC inbound stored procedure | Spring Integration poller | Calls routine, receives result set/OUT | Routine design, mapping, and recovery |
 Kafka/JMS inbound adapter | Broker listener/poller per adapter | Broker pushes/delivers messages | ACK/offset, retry/DLQ, DB integration |
 CDC/outbox relay | Log/broker/publisher driven | Watches DB changes or outbox | Redelivery semantics, checkpoints, and idempotency |

The JDBC inbound adapter **does not wait for a request message** to start a query. A `SourcePollingChannelAdapter` polls `MessageSource.receive()` on a schedule and sends results into the integration flow.

**When does it fit?** An outbox table or pending-jobs table with explicit states, straightforward SQL, moderate read throughput, and no requirement for per-change CDC. When business events require strong guarantees across multiple instances, add atomic claims/outbox or choose a dedicated event-relay architecture.

## 4. Payload Contract: Each Poll Usually Emits One Message Containing a List

According to Spring Integration JDBC documentation, a `SELECT` result is represented as **the entire result set in a `List`**. By default each row maps to a `Map<String,Object>`; when a `RowMapper<T>` is provided, each row maps to `T`.

~~~text
SELECT returns 3 rows
  -> JdbcPollingChannelAdapter
  -> Message<List<Map<String,Object>>>
  or Message<List<EventRecord>> if RowMapper is set
  -> Splitter
  -> 3 x Message<EventRecord>
~~~

| Element | Unit | Example |
|---|---|---|
| One row in `ResultSet` | Row | Event with ID 101 |
| Result of one `SELECT` | List | Events 101, 102, 103 |
| Adapter output after one `receive()` | Message with List payload | One `Message<List<EventRecord>>` |
| Downstream `Splitter` | Message per element | Three `Message<EventRecord>` |

Do not place a handler with signature `process(EventRecord)` immediately after the adapter while the payload is still `List<EventRecord>`. Add `.split()` or a transformer with an explicit contract.

**Zero-row case:** typically there is no business data to process. Whether the adapter emits an empty message or nothing must be verified for your version, configuration, and downstream; never assume a `List.empty()` is a SQL error.

## 5. Spring Boot Project and Practice Schema

Examples use Java 17+, Spring Boot, Spring JDBC, and Spring Integration JDBC. H2 is only for testing basic logic; multi-instance locking requires a real vendor database.

~~~groovy
// build.gradle: use Spring Boot BOM to manage compatible versions.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml for demo
spring:
  datasource:
    url: "jdbc:h2:mem:polling_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

In a demo application, place the following DDL in `src/main/resources/schema.sql`. This is an **illustrative example**, not a file that the worker should create in the lesson repository.

~~~sql
CREATE TABLE integration_event (
    id            BIGINT NOT NULL PRIMARY KEY,
    event_id      VARCHAR(80) NOT NULL UNIQUE,
    event_type    VARCHAR(80) NOT NULL,
    payload_json  VARCHAR(2000) NOT NULL,
    state         VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_by    VARCHAR(100),
    claimed_at    TIMESTAMP,
    lease_until   TIMESTAMP,
    completed_at  TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_event_polling
    ON integration_event (state, created_at, id);
~~~

Initial seed data:

~~~sql
INSERT INTO integration_event
    (id, event_id, event_type, payload_json, state)
VALUES
    (101, 'evt-101', 'order.created',
     '{"orderId":"ORD-1001"}', 'NEW'),
    (102, 'evt-102', 'order.paid',
     '{"orderId":"ORD-1002"}', 'NEW'),
    (103, 'evt-103', 'order.shipped',
     '{"orderId":"ORD-1003"}', 'NEW'),
    (104, 'evt-104', 'order.cancelled',
     '{"orderId":"ORD-1004"}', 'DONE');
~~~

`event_id` is a **business-stable ID** used for deduplication when messages are redelivered. Never regenerate event IDs on each poll. `claimed_by`, `claimed_at`, and `lease_until` support recovery extensions; the basic example only transitions `NEW → CLAIMED`.

## 6. Writing the Right Polling Query: WHERE, ORDER BY, and Batch Limits

Baseline SQL:

~~~sql
SELECT
    id, event_id, event_type, payload_json,
    state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id;
~~~

**Why is `WHERE` essential?** Without it, `CLAIMED`/`DONE` records get read again on every poll.

**Why is `ORDER BY` essential?** Without ORDER BY, the database **makes no guarantee** on row ordering. If business logic prefers older records first, choose `created_at, id` and index to match the query predicate. SELECT order does not guarantee publish order if downstream uses `flatMap`, multi-threaded executors, or multi-partition Kafka topics.

**Limiting at the DB:** to fetch at most 20 events per turn, H2/PostgreSQL can use:

~~~sql
SELECT id, event_id, event_type, payload_json,
       state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20;
~~~

SQL Server uses `TOP (20)` or `OFFSET/FETCH`; Oracle has its own limiting syntax. Pick syntax matching your database vendor. `LIMIT` is the H2/PostgreSQL example syntax, not universally portable SQL.

**Never read a million-row table and expect `RowMapper` or `splitter` to act as pagination.** Limiting in SQL cuts I/O and connection hold time; the adapter's `maxRows` can still serve as a secondary guardrail.

## 7. Updating Status After SELECT: A Simple Pattern

After selecting IDs `101, 102, 103`, execute:

~~~sql
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

`:ids` is a Spring JDBC **named parameter**, bound to the list of IDs extracted by the adapter from the SELECT result. With `[101,102,103]`, Spring JDBC expands the appropriate placeholders; never concatenate ID strings directly into SQL.

If you only need the default convention, the Spring Integration JDBC inbound adapter supports `:id` backed by an `id` column in the SELECT result:

~~~xml
<!-- Compact XML fragment: default id projection. -->
<int-jdbc:inbound-channel-adapter
    data-source="dataSource"
    channel="eventBatches"
    query="SELECT id, event_id, event_type
           FROM integration_event
           WHERE state='NEW' ORDER BY id"
    update="UPDATE integration_event
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'">
    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

This XML snippet requires `int`/`int-jdbc` namespaces plus `transactionManager` and `dataSource` beans in the application context. Do not run it alongside the Java DSL flow below against the same table and status unless intentionally testing concurrency.

**What UPDATE does not guarantee by itself:** if another instance claimed a row moments earlier, the UPDATE may affect **0 rows**. The initial SELECT result list may still contain that row; if downstream publishes from that list without checking claim ownership, duplicates can occur.

## 8. Java DSL 7.x: Implementing SELECT → UPDATE → Message

Since **Spring Integration 7.0**, the JDBC module provides `Jdbc.inboundAdapter(...)` and `JdbcInboundChannelAdapterSpec`. Those factory APIs **do not exist under the same factory in Spring Integration 6.x**; section 10 covers the 6.x approach.

### 8.1. DTO and RowMapper

~~~java
package com.example.polling;

import java.time.LocalDateTime;

public record EventRecord(
    long id,
    String eventId,
    String eventType,
    String payloadJson,
    String state,
    int attemptCount,
    LocalDateTime createdAt) {
}
~~~

~~~java
package com.example.polling;

import java.sql.Timestamp;
import org.springframework.jdbc.core.RowMapper;

public final class EventRecordRowMapper implements RowMapper<EventRecord> {

    @Override
    public EventRecord mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {

        Timestamp created = rs.getTimestamp("created_at");
        if (created == null) {
            throw new java.sql.SQLException(
                "created_at unexpectedly NULL");
        }

        return new EventRecord(
            rs.getLong("id"),
            rs.getString("event_id"),
            rs.getString("event_type"),
            rs.getString("payload_json"),
            rs.getString("state"),
            rs.getInt("attempt_count"),
            created.toLocalDateTime());
    }
}
~~~

For nullable numeric columns, `rs.getInt`/`rs.getLong` return 0 on SQL NULL, requiring `rs.wasNull()` or boxed types. In the demo schema, `id` and `attempt_count` are NOT NULL. `LocalDateTime` carries no timezone; production systems must define whether the DB stores local time or UTC and how the JDBC driver interprets it.

### 8.2. IntegrationFlow Using a Custom Parameter Source for UPDATE

~~~java
package com.example.polling;

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
public class EventPollingFlow {

    @Bean
    public IntegrationFlow pollPendingEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_id, event_type, payload_json,
                   state, attempt_count, created_at
            FROM integration_event
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            """;

        String updateSql = """
            UPDATE integration_event
            SET state = 'CLAIMED',
                claimed_at = CURRENT_TIMESTAMP,
                attempt_count = attempt_count + 1
            WHERE id IN (:ids) AND state = 'NEW'
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(new EventRecordRowMapper())
                    .maxRows(20)
                    .updateSql(updateSql)
                    .updatePerRow(false)
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(EventRecord.class::cast)
                            .map(EventRecord::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("claimedEvents")
            .get();
    }
}
~~~

This is a **single-instance learning pattern**, using H2/PostgreSQL `LIMIT` syntax. Flow execution steps:

1. The poller calls `receive()` every 3 seconds per fixed delay.
2. `SELECT` fetches up to 20 `NEW` rows.
3. `RowMapper` maps each row to an `EventRecord`.
4. `updateSqlParameterSourceFactory` receives **`List<EventRecord>`** and builds `ids` for binding into `UPDATE`.
5. `UPDATE` marks those IDs as `CLAIMED` and increments `attempt_count`.
6. The adapter emits a `List<EventRecord>` payload; `filter` drops empty batches and `split()` emits individual `Message<EventRecord>` messages.
7. Downstream on `claimedEvents` consumes each event.

**Important note about DTO data:** `EventRecord.state()` may still read `NEW` because it was mapped from `SELECT` **before** UPDATE ran. Do not rely on this field to assert that the row is claimed or published. When current status verification is needed, re-read the database/metadata per your contract.

### 8.3. Consumer for Each Event

~~~java
package com.example.polling;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class ClaimedEventHandler {

    @ServiceActivator(inputChannel = "claimedEvents")
    public void process(EventRecord event) {
        System.out.printf("Received event %s%n", event.eventId());
        // Demo: in production call a service or adapter with error/ACK policies.
    }
}
~~~

`System.out.printf` merely demonstrates a synchronous subscriber. It does not prove Kafka/JMS delivery or business completion succeeded. If the handler throws an exception on **the same thread and poller transaction**, the DB update can roll back; if the handler offloads work to another thread/queue, commit boundaries change.

## 9. `maxRows` and `maxMessagesPerPoll` Measure Different Units

Per the Spring Integration Reference:

| Configuration | Unit | Notable default | Effect |
|---|---|---|---|
| Adapter `maxRows` | Rows consumed from query result | **0** = unlimited | e.g., `maxRows(20)` caps at 20 rows |
| Poller `maxMessagesPerPoll` | `receive()` calls per trigger | Typically **1** for JDBC inbound | e.g., 1 SELECT per trigger |
| Poller `fixedDelay` | Time interval | Configured by you | e.g., 3 seconds after previous poll finishes |
| SQL `LIMIT/TOP/FETCH` | Rows returned by DB | SQL-dependent | Server-side limit |
| Splitter | Messages emitted from a list | Element count | 20 rows → 20 messages if split |

Example with 57 `NEW` events:

~~~text
maxRows(20), maxMessagesPerPoll(1), update state NEW -> CLAIMED

Poll 1 -> SELECT 20 rows -> UPDATE 20 -> 1 batch message -> 20 item messages
Poll 2 -> SELECT 20 rows -> UPDATE 20 -> 1 batch message -> 20 item messages
Poll 3 -> SELECT 17 rows -> UPDATE 17 -> 1 batch message -> 17 item messages
Poll 4 -> SELECT 0 rows  -> no business rows to process
~~~

Increasing `maxMessagesPerPoll` to 3 can cause the poller to **call SELECT/UPDATE multiple times within a single trigger**, rather than making the query return three rows. With JDBC, keeping the default of 1 usually gives better load control.

**Practical tip:** enforce limits directly in SQL and keep `maxRows` as a secondary guardrail. An overly broad SELECT can still force the DB to scan large amounts of data even if Java truncates the resulting list.

## 10. Spring Integration 6.x: Using JdbcPollingChannelAdapter Directly

In **6.x**, `JdbcPollingChannelAdapter` already supports `SELECT`, `UPDATE`, `RowMapper`, `setMaxRows`, `setUpdateSqlParameterSourceFactory`, and `setUpdatePerRow`. You can instantiate the `MessageSource` and pass it into regular Java DSL:

~~~java
package com.example.polling;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyEventPollingFlow {

    @Bean
    public IntegrationFlow legacyPollEvents(
            DataSource dataSource,
            PlatformTransactionManager tx) {

        var source = new JdbcPollingChannelAdapter(
            dataSource,
            "SELECT id, event_id, event_type, payload_json, "
          + "state, attempt_count, created_at "
          + "FROM integration_event WHERE state = 'NEW' "
          + "ORDER BY created_at, id");

        source.setRowMapper(new EventRecordRowMapper());
        source.setMaxRows(20);
        source.setUpdateSql(
            "UPDATE integration_event "
          + "SET state = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP "
          + "WHERE id IN (:ids) AND state = 'NEW'");
        source.setUpdateSqlParameterSourceFactory(result -> {
            List<?> rows = (List<?>) result;
            List<Long> ids = rows.stream()
                .map(EventRecord.class::cast)
                .map(EventRecord::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, e ->
                e.poller(Pollers.fixedDelay(Duration.ofSeconds(3))
                    .maxMessagesPerPoll(1)
                    .transactional(tx)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("legacyClaimedEvents")
            .get();
    }
}
~~~

**Version distinction:** the `Jdbc.inboundAdapter(...)` Java DSL factory was introduced in Spring Integration 7.0, whereas `JdbcPollingChannelAdapter` has long been available and suits 6.x. The 6.x example uses the source directly without pulling 7.x libraries onto the classpath.

Although conceptually equivalent, production code must be verified against the matching BOM and Java/JDK version. This article has not executed compilation; STEP 6 can test/clarify exact version APIs if needed.

## 11. XML: Configuring SELECT, UPDATE, and Transactional Pollers

Spring Integration JDBC also supports the XML namespace:

~~~xml
<!-- Fragment: context needs int and int-jdbc namespaces declared. -->
<int:channel id="dbEventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="dbEventPoller"
    data-source="dataSource"
    channel="dbEventBatches"
    query="SELECT id, event_id, event_type
           FROM integration_event
           WHERE state = 'NEW'
           ORDER BY id"
    update="UPDATE integration_event
            SET state = 'CLAIMED'
            WHERE id IN (:id) AND state = 'NEW'"
    max-rows="20">

    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

In XML, `query` is the `SELECT`; `update` is the SQL marking fetched rows; `:id` uses the default convention extracting IDs from the result set. `dbEventBatches` receives a message containing a list; to emit individual events, wire a downstream splitter. The XML and Java examples are **alternatives**—do not enable both against the same source in a single-worker demo.

### 11.1. Parameterized SELECT

Sometimes `state='NEW'` cannot be hardcoded and must be passed as a parameter:

~~~sql
SELECT id, event_id, event_type
FROM integration_event
WHERE state = :wantedState
ORDER BY id;
~~~

Use `selectSqlParameterSource` in DSL or `setSelectSqlParameterSource(...)` on `JdbcPollingChannelAdapter`. Unlike UPDATE, SELECT parameters are supplied **before query results exist**:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var selectParams = new MapSqlParameterSource(
    "wantedState", "NEW");

// Inside 7.x JdbcInboundChannelAdapterSpec:
.selectSqlParameterSource(selectParams)
~~~

This is a **DSL fragment**, used inside the source configuration chain. For parameters needing per-poll SpEL re-evaluation, use `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` per Spring Integration documentation; do not mistakenly wire the UPDATE factory to supply SELECT parameters.

## 12. `updatePerRow`, `SqlParameterSourceFactory`, and `RowMapper`

UPDATE has two strategies:

| Mechanism | Factory input | Typical SQL |
|---|---|---|
| `updatePerRow(false)` (default) | `List` of all SELECTed rows | `WHERE id IN (:ids)` |
| `updatePerRow(true)` | Individual row from the result | `WHERE id = :rowId` |

With a `RowMapper` producing `EventRecord`, the factory reads `EventRecord.id()`; with the default mapper, the factory receives rows as `Map`s. **Switching from Map to a record while forgetting to update the factory** easily causes `ClassCastException`.

Per-row example:

~~~java
// 7.x JdbcInboundChannelAdapterSpec configuration fragment:
.updateSql(
    "UPDATE integration_event "
  + "SET state='CLAIMED' WHERE id=:rowId AND state='NEW'")
.updatePerRow(true)
.updateSqlParameterSourceFactory(row ->
    new MapSqlParameterSource(
        "rowId", ((EventRecord) row).id()))
~~~

`updatePerRow(true)` does **not** mean a separate transaction or separate message per row. It only changes the unit/count of UPDATE statements. To make each row a message, add a `Splitter`; to create separate transactions, configure transaction boundaries intentionally.

`ExpressionEvaluatingSqlParameterSourceFactory` can replace the lambda and evaluate SpEL over either the **entire list** or the **current row** per `updatePerRow`. Never put arbitrary SpEL expressions directly into named parameters like `:rowId`—SQL only knows parameter names.

## 13. What Does the Poller Transaction Actually Protect?

Spring Integration allows **wrapping a poll cycle** in a Spring transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(3))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

If `transactionManager` manages the matching `DataSource`, SELECT and UPDATE can share **one local database transaction**. When downstream uses `DirectChannel` and handlers run **synchronously on the same thread**, an exception in a handler before commit triggers rollback.

~~~mermaid
sequenceDiagram
    participant Poller as Transactional poller
    participant DB as JDBC database
    participant Channel as DirectChannel
    participant Handler as Synchronous handler
    Poller->>DB: BEGIN + SELECT NEW rows
    DB-->>Poller: Rows 101, 102
    Poller->>DB: UPDATE rows to CLAIMED
    Poller->>Channel: Message<List<Row>>
    Channel->>Handler: Process
    alt Handler succeeds
        Handler-->>Poller: Return
        Poller->>DB: COMMIT
    else Handler throws exception
        Handler-->>Poller: Exception
        Poller->>DB: ROLLBACK
    end
~~~

**Crucial boundary:** if a handler sends an external HTTP request or Kafka event and the database transaction then rolls back, the remote system **may already have received** the side effect. Local DB rollback does not unsend a broker message or partner HTTP call. Keep transactions spanning only short synchronous downstream steps suited to your transaction strategy; never hold DB locks while waiting on remote I/O.

### 13.1. `DirectChannel` vs. `ExecutorChannel` and `QueueChannel`

| Boundary | When does handler run? | Poller transaction? |
|---|---|---|
| `DirectChannel` | Immediately on caller/poller thread | Can share if using the same resource/manager |
| `ExecutorChannel` | Executor thread | Does not carry thread-bound transaction automatically |
| `QueueChannel` + another poller | Later, at a different time | Separate transaction |
| Kafka/JMS outbound | Per adapter/client/broker semantics | Not automatically atomic with DB transaction |

Do not see `send() == true` and conclude “both database and broker committed” if the flow crosses an async boundary.

## 14. Multi-Instance Contention: SELECT-Then-UPDATE Is Not Enough

Suppose two pods poll concurrently using an ordinary SELECT:

~~~text
T1  Pod A: SELECT row 101 (state=NEW)
T2  Pod B: SELECT row 101 (state=NEW)
T3  Pod A: UPDATE row 101 -> CLAIMED (1 row)
T4  Pod A: emit event 101
T5  Pod B: UPDATE row 101 WHERE state=NEW (0 rows)
T6  Pod B: still holds List<Row> containing event 101 from SELECT at T2
T7  Pod B: emits event 101 a second time
~~~

`WHERE state='NEW'` in the UPDATE prevents **overwriting state** when a row is already claimed, but it **does not remove the row from Pod B's already-fetched result list**. Some applications only check “UPDATE threw no exception” and proceed to emit all SELECTed rows—that is insufficient to ensure single-pod ownership.

### 14.1. Remediation Options

1. **Row-level locking with SKIP LOCKED:** SELECT locks candidate rows, skips rows already locked, and UPDATEs before commit; requires matching transaction/isolation settings.
2. **Atomic UPDATE … RETURNING/OUTPUT:** select and claim in **one statement**, returning only rows actually claimed; exact syntax depends on DB vendor.
3. **Lease/owner:** record `claimed_by`, `lease_until`, and version; another worker reclaims only after lease expiration.
4. **Partition ownership:** each pod polls only an explicitly assigned partition or key range.
5. **Idempotent consumer:** accept at-least-once delivery and prevent duplicate side effects via business event IDs.

In multi-replica systems, prefer **atomic claims + idempotency**; never infer exactly-once just because “each pod runs a poller” or “the DB has transactions”.

## 15. PostgreSQL Example: Locking Rows During SELECT

PostgreSQL provides `FOR UPDATE SKIP LOCKED` so competing transactions skip currently locked rows:

~~~sql
-- PostgreSQL; runs inside a transaction holding locks until commit.
SELECT id, event_id, event_type, payload_json,
       state, attempt_count, created_at
FROM integration_event
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

After collecting IDs, in the same transaction execute:

~~~sql
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

When both SELECT and UPDATE run inside the **poller's transaction**, rows locked during SELECT will not be picked concurrently by another transaction following the same protocol. Still, check isolation levels, indexes, row-lock behavior, and how the DB plans LIMIT/ORDER BY in your real environment.

**Do not copy verbatim to H2/SQL Server/MySQL/Oracle.** Other vendors differ in syntax or locking semantics. Do not assume this SELECT enforces strict global processing order; with multiple workers, locked rows are skipped and processed later.

### 15.1. When You Need an Atomic Claim Returning the Claimed Rows

PostgreSQL supports the pattern illustrated below:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_event
    WHERE state = 'NEW'
    ORDER BY created_at, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE integration_event e
SET state = 'CLAIMED',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.event_id, e.event_type, e.payload_json;
~~~

This is a **PostgreSQL-specific SQL pattern** and must be executed via a mechanism matching the driver and endpoint, such as a repository/`JdbcTemplate` or a stored procedure/message source with a clear contract. Do not assume `JdbcPollingChannelAdapter` with a `selectQuery` is meant to handle arbitrary `RETURNING` DML directly; if choosing this approach, verify how the query and JDBC driver return the result set.

The advantage of atomic claiming is that the returned list strictly matches **rows actually modified**, instead of relying on a stale SELECT. It still **does not** guarantee Kafka/HTTP received the message.

## 16. Claimed, Published, and Processed: Choosing State Milestones

A workflow may persist these milestones:

~~~text
NEW
  -> CLAIMED (worker X, lease until time T)
  -> PUBLISHING
  -> PUBLISHED
  -> DONE (if business ACK/side effect is also tracked)
~~~

For small systems, `CLAIMED → DONE` may suffice. With an outbox, `NEW → PUBLISHED` can be a cleaner contract. Every state name must have a **precise definition**:

| Milestone | Required evidence | Who is responsible? |
|---|---|---|
| `CLAIMED` | DB committed claim and owner/lease | DB/polling worker |
| `PUBLISHED` | Adapter/client recorded send outcome per delivery contract | Publisher/outbox relay |
| `DONE` | Task completed per business contract | Worker/service |
| `FAILED` | Classified non-retryable, with reconciliation metadata | Error handler/recovery |

In particular, a **Kafka producer callback/ack** does not prove a Kafka consumer finished processing the event; JMS/Kafka listener ACKs also mean something different from producer ACKs.

Never add an `is_read=true` boolean column and treat it as a complete delivery design. If you need “read once” across systems, specify **exactly-once effects**, not just exactly-once reads.

## 17. Leases and Recovery When a Worker Dies Mid-Flight

If a row transitions to `CLAIMED` and the application crashes before sending, it may never be SELECTed again if the query only filters `NEW`. A common solution is a **lease**:

~~~sql
-- Illustrative DML with application-bound parameters.
UPDATE integration_event
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = :leaseUntil,
    attempt_count = attempt_count + 1
WHERE id IN (:ids)
  AND state = 'NEW';
~~~

`:workerId`, `:leaseUntil`, and `:ids` must be supplied via a parameter source; this is not the complete SQL from section 8. `leaseUntil` should follow a strict UTC/clock policy; avoid large clock skew across pods. On databases that support computing deadlines directly on the DB server, using the DB clock avoids host clock drift.

A recovery job can scan:

~~~sql
-- Concept: reclaim records whose lease has expired.
SELECT id, event_id, attempt_count
FROM integration_event
WHERE state = 'CLAIMED'
  AND lease_until < CURRENT_TIMESTAMP
ORDER BY lease_until, id;
~~~

Then **reclaim atomically** using locks, versions, or a new owner. Simply reading expired leases and running blind UPDATEs still races when multiple recovery workers run concurrently.

### 17.1. Fencing Tokens to Prevent Stale Workers from Overwriting

Suppose worker A stalls, its lease expires, and worker B takes over the job—yet worker A is still alive. If A finishes and marks `DONE` without checking ownership, it can corrupt B's state.

A defensive pattern is a version/fencing token incremented on every claim:

~~~sql
UPDATE integration_event
SET state = 'DONE',
    completed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND claimed_by = :workerId
  AND claim_version = :claimVersion
  AND state = 'CLAIMED';
~~~

This is an **extended DML pattern** requiring a `claim_version` column and version increment on claim; it will not run verbatim on the section 5 schema. When the affected row count is 0, the worker likely lost ownership; never overwrite blindly to force “completion”.

## 18. Transactional Outbox: Instead of Sending to a Broker Right After SELECT

For business mutations that must emit events, the standard safe pattern is:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Write domain state + outbox in same DB TX"]
    B --> C[("Outbox table")]
    C --> D["Outbox polling relay"]
    D --> E["Kafka / JMS"]
    E --> F["Idempotent consumer"]
    D -->|"Send ACK succeeded"| G["Mark PUBLISHED"]
    D -->|"Failure"| H["Retry / lease"]
~~~

An outbox avoids the failure mode where **the database commit succeeds while the outbound event was never durably recorded**. However, a publisher can still send to the broker and crash **before marking `PUBLISHED`**. On restart, the outbox row is sent again: that gives **at-least-once** delivery, so consumers must remain idempotent.

**Distinguishing the two designs:**

- “Read `NEW` business rows then UPDATE `CLAIMED`”: workers must manage claims, recovery, and downstream outcome verification.
- “Write outbox inside business transaction then relay”: guarantees durable event capture and independent retries; still requires publish-state tracking and deduplication.

Never hold a local database transaction open waiting on slow Kafka or HTTP responses. If business callers need fast responses, insert into the outbox in the transaction and return **ACCEPTED/PENDING** per the application contract.

## 19. How Can Pollers Overload a Database?

Every poll consumes a connection and may execute a SELECT + UPDATE. As pod counts, poller threads, and batch sizes grow, databases can be overloaded by:

- Full table scans due to missing `(state, created_at, id)` indexes.
- Multiple pollers contending on row locks.
- Transactions holding connections/locks too long while downstream handlers block.
- Oversized batches creating `IN (:ids)` statements with thousands of parameters.
- Aggressive retries while the DB is unreachable.
- Repeatedly reading the same rows when UPDATE fails to transition state or rolls back.

| Setting | Where configured | Design recommendation |
|---|---|---|
| Fixed delay | Poller | Size to real throughput; avoid hammering when idle |
| `maxMessagesPerPoll` | Poller | Typically keep at 1 for JDBC inbound |
| `maxRows` | Adapter | Per-poll cap; pair with SQL limits |
| SQL `LIMIT/TOP` | Database | Ensure matching indexes |
| JDBC pool max size | Hikari/DataSource | Never exceed DB capacity |
| Handler concurrency | Channel/executor | Bounded; control transaction boundaries |
| Retry attempts/backoff | Poller/worker/recovery | Cap retries and add jitter to prevent retry storms |

Even when polling many rows, `RowMapper` and splitters do not make JDBC non-blocking. `JdbcTemplate`/JDBC still uses **blocking I/O**; avoid running it on the Reactor Netty event loop in WebFlux applications.

## 20. Failures in SELECT, UPDATE, and Downstream Have Different Consequences

| Failure | When | Possible outcome | How to respond |
|---|---|---|---|
| DB disconnected | Before or during SELECT | No rows read | Alert, bounded retry |
| Bad SQL/schema drift | SELECT | Configuration error | Fix SQL/migration; do not retry forever |
| RowMapper wrong column/type | Mapping rows | Failed before valid payload built | Fix mapper/schema, roll back if needed |
| UPDATE returns 0 rows | After SELECT | Row already claimed/mismatched | Do not assert ownership |
| Deadlock/serialization | UPDATE/commit | Transaction rollback | Retry whole transaction if safe |
| Synchronous downstream throws | After source receive | May roll back poller transaction | Check `DirectChannel`, resource manager |
| Async downstream fails | After poller committed | Row may stay stuck `CLAIMED` | Lease/outbox/error flow |
| Broker received, app crashes before DONE | After send | May redeliver | Stable event ID and consumer idempotency |
| Poller fails repeatedly | Every trigger | Needless DB load | Backoff/health gating, alerting |

Spring JDBC typically translates `SQLException`s into `DataAccessException` subtypes. Spring Integration can route poller/handler errors to `ErrorMessage`/`errorChannel` or configured error handlers depending on endpoint setup. **Do not assume every error becomes a reply message** or is automatically retried by a broker.

### 20.1. Retrying the Right Transaction Unit

If a poller runs SELECT and UPDATE in one transaction and hits a deadlock, retry **the entire poll/transaction after rollback**, not just the UPDATE alone reusing a stale ID list. When connectivity drops near commit time, the outcome is uncertain; re-read state and deduplicate rather than retrying blindly on the assumption rollback definitely occurred.

## 21. Observing State: Metrics and Logging

Metrics to track:

1. **Polls:** execution count, trigger intervals, empty poll count, SELECT/UPDATE durations.
2. **Rows:** rows SELECTed, rows actually UPDATEd/claimed, discrepancy between the two counts.
3. **Backlog:** counts of `NEW`, `CLAIMED`, `FAILED`, age of oldest incomplete row.
4. **Leases:** expired lease count, reclaim count, `CLAIMED`-to-`DONE` duration.
5. **Delivery:** publish count, retries, errors, broker ACKs, duplicate consumer effects.
6. **Database:** active/idle/pending connections, locks, deadlocks, query timeouts, and transaction durations.

Logs should include `event_id`, `workerId`, `pollId`/correlation ID, before/after state, and error type; avoid logging full `payload_json` if it contains sensitive data. Avoid using per-row unique `event_id` values as metric tags where cardinality explodes—keep them in logs and traces instead.

### 21.1. `UPDATE = 0` Is an Operational Signal

If SELECT returns 20 rows while UPDATE only modifies 7, you may have concurrency races, overly tight predicates, concurrent state transitions, or broken SQL parameter mapping. For an application treating all 20 rows as “claimed”, this is a serious design warning.

The JDBC inbound adapter **does not automatically become a distributed ownership coordinator** just because you can inspect row counts. If you need strictly the rows that were actually claimed, implement an atomic claim returning only claimed IDs and feed **that list** into the message source.

## 22. Basic Testing with H2

For single-instance logic, H2 suffices to test SELECT + UPDATE and `RowMapper`. Never treat H2 as proof of locking/transaction semantics for PostgreSQL, SQL Server, or Oracle.

### 22.1. Testing a JDBC Source Directly

An integration test can construct `JdbcPollingChannelAdapter` as a **`MessageSource`** without starting a scheduler, calling `receive()` explicitly. Example:

~~~java
package com.example.polling;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.messaging.Message;

@SpringBootTest
class EventPollingSourceTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void selectsAndMarksRowsForProcessing() throws Exception {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, event_type, payload_json, "
              + "state, attempt_count, created_at "
              + "FROM integration_event "
              + "WHERE state = 'NEW' ORDER BY id");

        source.setMaxRows(2);
        source.setRowMapper(new EventRecordRowMapper());
        source.setUpdateSql(
            "UPDATE integration_event SET state='CLAIMED' "
          + "WHERE id IN (:ids) AND state='NEW'");
        source.setUpdateSqlParameterSourceFactory(rows -> {
            List<?> list = (List<?>) rows;
            List<Long> ids = list.stream()
                .map(EventRecord.class::cast)
                .map(EventRecord::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        // Test instantiates the source directly, so complete lifecycle setup.
        source.afterPropertiesSet();

        Message<?> message = source.receive();
        assertNotNull(message);
        List<?> events = (List<?>) message.getPayload();
        assertEquals(2, events.size());

        Integer claimed = jdbc.queryForObject(
            "SELECT COUNT(*) FROM integration_event "
          + "WHERE state = 'CLAIMED'",
            Integer.class);
        assertEquals(2, claimed);
    }
}
~~~

**Preconditions for this example:** the fixture table must contain three `NEW` rows as in section 5, no other poller/flow should touch the table, no auto-rolling-back test transaction should wrap it, and datasource/bean lifecycles must be compatible. In an app with auto-starting `IntegrationFlow`s, isolate the test context or disable competing sources to prevent interference.

The test above has **no transactional poller**, so it does not verify rollback when downstream fails; it only tests SELECT/UPDATE and the payload. To test transactions, use a real poller or wrap `source.receive()` plus a synchronous downstream operation in `TransactionTemplate` on the same thread.

### 22.2. Testing When No Rows Remain

Once all `NEW` rows are claimed, call `receive()` again and verify source behavior **in your active version** (no business message or empty result per contract). Never write tests that only assert `send()==true` without inspecting DB state.

### 22.3. Minimum Test Matrix

| Scenario | Expectation |
|---|---|
| 3 NEW rows, maxRows=2 | Two rows mapped/marked on first pass |
| Second pass | Remaining row processed; previously CLAIMED rows not re-read |
| No NEW rows remaining | No new business events emitted |
| Wrong column name in RowMapper | Error raised, never silently produces wrong DTO |
| UPDATE predicate does not match | Does not assume claim ownership |
| DirectChannel handler fails | Poller TX rolls back if sharing local DB transaction |
| ExecutorChannel handler fails | Poller TX does not auto-roll back due to separate worker |
| Two instances run same SELECT | Duplicate risk exposed; atomic locking required |
| Worker crashes after CLAIMED | Lease/recovery reclaims row |
| Publisher sends to Kafka then crashes | Stable event ID enables consumer deduplication |

## 23. Testing Concurrency and Crash Recovery

Use a real PostgreSQL/SQL Server/MySQL/Oracle test instance or Testcontainers to reproduce realistic concurrency:

1. Seed 100 `NEW` rows.
2. Run two worker transactions executing the same SELECT under a controlled barrier/latch, confirming the same-row race in the naive design.
3. Switch to `FOR UPDATE SKIP LOCKED` or vendor atomic claim; verify two workers never claim the same ID in committed transactions.
4. Pause/hang one worker between claim and commit; check lock waits/timeouts and rollbacks.
5. Commit a claim, then simulate a crash before publishing; verify lease expiration and reclaim.
6. Simulate the broker receiving the event while the app crashes before marking `DONE`; verify redelivering the same event ID produces no duplicate side effects.
7. Send two business events for the same aggregate with out-of-order versions; verify the consumer does not regress state.
8. Shrink pool size, raise poller count, and monitor connection waits, lock contention, and throughput.

**Do not count callback invocations alone.** To prove a design loses no work, inspect **DB state, broker outcomes, retry backlogs, lease recovery, and idempotent business effects**. Even if one test run shows no duplicates, that does not prove end-to-end exactly-once across all crash windows.

## 24. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “JDBC polling means receiving messages from a broker” | JDBC inbound actively **runs scheduled SELECTs** |
| “A SELECT returning 20 rows makes the adapter emit 20 messages” | Usually one message with a list; a splitter splits it |
| “`maxMessagesPerPoll(1)` fetches only one row” | It is one `receive()` call per trigger |
| “`maxRows(0)` fetches zero rows” | 0 means unlimited at the adapter level |
| “`WHERE state='NEW'` prevents duplicates across pods” | Two pods can SELECT the same row before UPDATE |
| “An UPDATE affecting 0 rows always throws an error” | JDBC UPDATE can succeed with a count of 0 |
| “Updating to CLAIMED means Kafka received it” | DB claims are separate from broker publishes and consumer ACKs |
| “Poller transactions automatically roll back HTTP/Kafka” | Only enlisted resources roll back; external side effects do not |
| “Rows no longer NEW means all work is finished” | They may be stuck in CLAIMED or FAILED |
| “Simply increasing poll frequency clears backlogs” | Can trigger pool exhaustion and lock contention |
| “RowMapper updates read state” | The mapper only builds Java objects; SQL UPDATE changes state |
| “Retries avoid duplicates if event IDs are always regenerated” | Event IDs must remain stable for deduplication |
| “SELECT + UPDATE in a transaction is end-to-end exactly-once” | Requires ownership, recovery, broker ACKs, and consumer idempotency |

## 25. Practice Exercises

1. Create `integration_event` with `NEW/CLAIMED/DONE` states, insert sample rows, and verify only `NEW` rows are selected.
2. Run the JDBC inbound adapter without UPDATE; observe the same rows appearing on subsequent polls.
3. Add the default `UPDATE state='CLAIMED' WHERE id IN (:id)`; compare with a custom `:ids` parameter.
4. Write a 7.x Java DSL flow using `Jdbc.inboundAdapter` and `RowMapper<EventRecord>`; add a splitter to send individual events.
5. Port the same flow to 6.x with `JdbcPollingChannelAdapter` and check lifecycle/imports.
6. Compare `maxRows(20)`, SQL `LIMIT 20`, and `maxMessagesPerPoll(1)` in terms of query counts, row counts, and message counts.
7. Test DB responses of 0 rows, 1 row, and 100 rows; ensure no empty business events are emitted.
8. Try `updatePerRow(true)` for per-row SQL updates; compare with batch updates using ID lists.
9. Build a SELECT with `:wantedState` and `selectSqlParameterSource`; contrast it with the UPDATE parameter factory.
10. Wrap the poller in a transaction, make a downstream `DirectChannel` handler throw, and verify DB rollback.
11. Switch downstream to `ExecutorChannel`; explain why a worker failure after poller commit does not roll back `CLAIMED`.
12. Run two pollers on the same table; reproduce both selecting the same row and examine UPDATE counts.
13. On test PostgreSQL, use `FOR UPDATE SKIP LOCKED` and measure overlapping rows between two transactions.
14. Try vendor-specific atomic `UPDATE ... RETURNING` in a dedicated repository/message source; emit only successfully claimed rows.
15. Add `claimed_by`, `lease_until`, and `attempt_count`, build a recovery job, and alert on stuck rows.
16. Use a fencing token/version on completion; reject `DONE` updates if the worker lost its lease.
17. Switch to a transactional outbox and simulate a crash after DB commit before publishing.
18. Send events to Kafka/JMS and crash after broker ACK before `DONE`; verify consumer idempotency using `event_id`.
19. Measure active pool connections, poll duration, SQL UPDATE counts, backlog, and expired leases under load.
20. Write an integration test on a production-compatible DB to verify locking, transactions, crash windows, and redelivery.

**Scenario question:** Two pods poll an `integration_event` table containing 50,000 `NEW` rows. Each pod fetches 100 rows, marks them `CLAIMED`, sends to Kafka, and then one pod is killed right after the broker received the message but before the database marked `DONE`. Explain how SELECT/UPDATE, locking, leases, outbox, unique event IDs, consumer idempotency, and recovery work together to prevent lost work and duplicate business effects.

## 26. References

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT + optional UPDATE, row mapping, `:id` parameter, transactional pollers, `maxRows` vs. `maxMessagesPerPoll`.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL `Jdbc.inboundAdapter(...)` from Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `rowMapper`, `maxRows`, `updateSql`, `updatePerRow`, `updateSqlParameterSourceFactory`.
- [Spring Integration API — JdbcPollingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): source, SELECT/UPDATE, row mapper, and parameter sources.
- [Spring Integration Reference — Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html): `MessageSource`, `IntegrationFlow.from`, and `Pollers`.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, channel synchronization, and rollback.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, named parameters, and SQL operations.
- [PostgreSQL Documentation — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `SKIP LOCKED`, and `LIMIT`.
- [PostgreSQL Documentation — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM` and `RETURNING` for atomic claim patterns.

> **Remember:** JDBC polling is the cycle **SELECT → map rows → optionally UPDATE state → emit message**. `NEW → CLAIMED` avoids repeated reads in simple cases, but does **not** mean sent or processed successfully. Running multiple instances reliably requires managing transactions, locking/atomic claims, leases/recovery, outboxes, and idempotency; `maxRows` caps rows, `maxMessagesPerPoll` caps source poll calls, and a splitter creates individual messages per row.

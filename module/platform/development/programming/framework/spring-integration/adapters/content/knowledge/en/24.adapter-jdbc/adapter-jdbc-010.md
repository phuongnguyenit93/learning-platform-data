# MetadataStore for Incremental Queries in Spring Integration JDBC

## 1. Problem Statement: Where to Resume Reading After an Application Restart?

A Spring Integration application needs to read new records from a `source_event` table and forward them to Kafka, JMS, AMQP, HTTP, or an internal service. If every poll executes `SELECT` over the entire table, old data is read repeatedly. If it uses `WHERE state='NEW'` followed by `UPDATE`, the application must have permission to modify the source table—which is sometimes forbidden because the database belongs to an ERP or external partner.

For append-only sources, you can use an **incremental query**: persist the last processed position, called a **checkpoint/high-water mark**, and query rows beyond that point.

~~~sql
-- Saved checkpoint: last_id = 102.
SELECT id, event_type, payload_json
FROM source_event
WHERE id > 102
ORDER BY id
LIMIT 50;
~~~

Problems emerge at failure boundaries:

- If `lastId` is stored only in a Java variable, the cursor is lost on JVM restart.
- If the checkpoint is written **immediately after SELECT**, but the worker dies before emitting the events, records can be skipped forever.
- If two pods share the same cursor without coordination, one pod can overwrite the other's progress.
- If a transaction generating ID 105 commits **after** a transaction generating ID 106, advancing the cursor to 106 can miss row 105.
- If the table allows `UPDATE`s on older rows, a cursor on `id` alone cannot detect those changes.

Spring Integration provides `MetadataStore` to persist progress as key–value pairs. `JdbcMetadataStore` stores values durably in a database and provides atomic operations for multi-instance setups.

This article belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, covering files, SFTP, HTTP, JMS, AMQP, Kafka, and databases with a focus on message contracts, errors, and connection lifecycles.

~~~mermaid
flowchart LR
    P["Poller"] --> C["Read checkpoint"]
    C --> S["SELECT rows > cursor"]
    S --> R["List<EventRow>"]
    R --> W["Durably stage work"]
    W --> M["CAS checkpoint"]
    M --> D[("JDBC MetadataStore")]
    W --> O[("Outbox")]
    O --> K["Kafka / JMS publisher"]
~~~

**Core distinction:** metadata is only **coordination state**. It does not hold full business events and does not guarantee a broker received the data.

## 2. MetadataStore, Watermarks, Broker Offsets, and MessageStore

| Concept | Function | Example |
|---|---|---|
| Cursor/watermark | Position deciding what data comes next | `last_id=102` |
| Checkpoint | Cursor durably persisted at a safe point | `source:last-id → "102"` |
| `MetadataStore` | Stores string key/value pairs | `get`, `put`, `remove` |
| `ConcurrentMetadataStore` | Metadata with conditional atomic operations | `putIfAbsent`, `replace` |
| `JdbcMetadataStore` | Key/value implementation on an RDBMS | `INT_METADATA_STORE` table |
| `JdbcMessageStore` | Persists messages/message groups | Queues, aggregators, claim-check |
| Broker offset/ACK | Broker consumer/producer progress | Kafka partition offset |
| Idempotency key | Identifies events to prevent duplicate side effects | `event_id` |

Example metadata region storing a checkpoint:

~~~text
REGION = orders-incremental-v1
METADATA_KEY = source-event:last-id
METADATA_VALUE = "102"
~~~

If downstream consumes records from Kafka and later writes to a database, **Kafka offsets** and **JDBC cursors** are two separate checkpoints. Never treat committing one as committing the other.

## 3. Key Interfaces and APIs

`org.springframework.integration.metadata.MetadataStore` defines a key–value contract:

~~~java
String before = metadataStore.get("orders:last-id");
metadataStore.put("orders:last-id", "102");
String removed = metadataStore.remove("orders:last-id");
~~~

`ConcurrentMetadataStore` adds:

~~~java
String oldValue = concurrentStore.putIfAbsent(
    "orders:last-id", "102"); // null = newly created successfully.

boolean changed = concurrentStore.replace(
    "orders:last-id", "102", "110"); // true if oldValue matched.
~~~

| API | Semantics |
|---|---|
| `get(k)` | Read key value or null if absent |
| `put(k,v)` | Unconditional overwrite |
| `remove(k)` | Delete key and return previous value if present |
| `putIfAbsent(k,v)` | Atomic create-if-absent |
| `replace(k,expected,next)` | Compare-and-set; writes only if current equals expected |

**Do not use `get` then `put` as a distributed lock.** Two pods can both read 102, both run SELECT, and write 110 unaware of the race. `replace` detects lost updates, yet still does not guarantee events were not sent twice to an external system.

### 3.1. Implementations of MetadataStore

Spring Integration provides in-memory `SimpleMetadataStore`, file-based `PropertiesPersistingMetadataStore`, and persistent stores backed by JDBC, Redis, MongoDB, ZooKeeper, etc. `SimpleMetadataStore` does **not** preserve checkpoints across process restarts.

`JdbcMetadataStore`, available since Spring Integration **5.0**, implements `ConcurrentMetadataStore` and can participate in Spring JDBC transactions. It is not a database connection pool or a stream log; it uses the application's `DataSource`.

## 4. Crucial Limitation: JdbcPollingChannelAdapter Does Not Auto-Use MetadataStore

Some File/FTP/SFTP/Feed adapters support metadata/duplicate detection via `MetadataStore`. However, **`JdbcPollingChannelAdapter` has no `setMetadataStore(...)` API for automatic incremental SELECTs**.

JDBC inbound exposes different capabilities:

- `setSelectSqlParameterSource(...)` to supply `SELECT` parameters.
- `setUpdateSql(...)` and `setUpdateSqlParameterSourceFactory(...)` to mark read rows.
- `setRowMapper(...)` to map `ResultSet` rows to DTOs.
- `setMaxRows(...)` to limit row counts.

That means the application **must wire the watermark into SELECT itself** via `SqlParameterSource` or a custom `MessageSource`, and **decide explicitly when to advance the checkpoint**.

~~~java
// WRONG: these methods do not exist on JdbcPollingChannelAdapter.
// jdbcSource.setMetadataStore(store);
// jdbcSource.enableAutomaticIncrementalCheckpoint();
~~~

Even if you declare a bean named `metadataStore`, the JDBC inbound adapter will not automatically append `WHERE id > :lastId` to your SQL.

## 5. Preconditions for an ID Cursor to Be Valid

The pattern `WHERE id > :lastId ORDER BY id` is safe only when you verify:

1. IDs are unique, non-null, and comparably ordered.
2. New business changes appear **after the cursor**, rather than updating older rows.
3. No transaction **commits late** with an ID behind the new watermark—or you have overlap/reconciliation.
4. The checkpoint advances **only after** the protected rows are durably recorded.
5. One stream/partition does not have multiple workers updating the same key without CAS and coordination.
6. You do not need to detect `DELETE`s/tombstones via SELECT on the current table; if you do, use a change log/CDC.

**Note:** sequences/identity columns only guarantee ID allocation; they do **not** guarantee transactions **commit in ID order**. Section 16 analyzes ID 106 committing before ID 105.

## 6. Preparing Spring Boot, DataSource, and Schema

Examples use Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC, and H2 for practice. Use the Spring Boot BOM to manage compatible versions.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
spring:
  datasource:
    url: "jdbc:h2:mem:incremental_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Suppose a practice application puts this DDL in `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE source_event (
    id           BIGINT NOT NULL PRIMARY KEY,
    event_type   VARCHAR(80) NOT NULL,
    payload_json VARCHAR(2000) NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_outbox (
    event_id     VARCHAR(80) NOT NULL PRIMARY KEY,
    source_id    BIGINT NOT NULL UNIQUE,
    event_type   VARCHAR(80) NOT NULL,
    payload_json VARCHAR(2000) NOT NULL,
    published    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE INT_METADATA_STORE (
    METADATA_KEY   VARCHAR(255) NOT NULL,
    METADATA_VALUE VARCHAR(4000) NOT NULL,
    REGION         VARCHAR(100) NOT NULL,
    CONSTRAINT INT_METADATA_STORE_PK
        PRIMARY KEY (METADATA_KEY, REGION)
);

INSERT INTO source_event(id, event_type, payload_json)
VALUES (101, 'order.created', '{"orderId":"ORD-101"}'),
       (102, 'order.paid', '{"orderId":"ORD-102"}'),
       (103, 'order.shipped', '{"orderId":"ORD-103"}');
~~~

**`INT_METADATA_STORE` is the infrastructure table** used by `JdbcMetadataStore`. The `spring-integration-jdbc` module ships schema scripts for various DB vendors; H2 here is illustrative only. Production deployments should manage migrations with Flyway/Liquibase.

**In-memory H2 does not survive process restarts.** To verify metadata persistence across real restarts, use a DB server or file-backed H2; `DB_CLOSE_DELAY=-1` only keeps H2 alive while the JVM is running.

## 7. Configuring JdbcMetadataStore with a Dedicated Region

~~~java
package com.example.incremental;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.metadata.JdbcMetadataStore;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Configuration
public class CheckpointStorageConfiguration {

    @Bean("incrementalCheckpointStore")
    public ConcurrentMetadataStore incrementalCheckpointStore(
            DataSource dataSource) {
        JdbcMetadataStore store = new JdbcMetadataStore(dataSource);
        store.setRegion("orders-incremental-v1");
        return store;
    }
}
~~~

`setRegion(...)` acts as a logical namespace; the default region is `DEFAULT`. Giving each workflow its own region reduces the risk of pipelines colliding on keys.

`JdbcMetadataStore#setLockHint(...)` lets you customize locking syntax during metadata updates; the default is `FOR UPDATE`, whereas SQL Server uses its own lock hints. Configure lock hints only for your actual DB vendor—never copy verbatim from another DB.

Since **Spring Integration 6.2**, `JdbcMetadataStore` implements `SmartLifecycle` and can verify the metadata table exists at startup. If the table matching the configured prefix is missing, startup fails—that is a signal to fix migrations, not a reason to blindly disable checking via `setCheckDatabaseOnStart(false)`.

## 8. Keys, Values, Regions, and Bootstrapping the Cursor

For a single stream:

~~~java
static final String CURSOR_KEY = "source-event:last-id";
~~~

Multi-tenant or multi-partition systems need explicit keys, such as:

~~~text
orders:partition-0:last-id
orders:partition-1:last-id
invoices:tenant-a:last-id
orders:source-event:cursor-v2
~~~

| When key does not exist yet | Meaning | Risk |
|---|---|---|
| Cursor `0` | Read all positive IDs from the start | Huge initial backlog |
| Cursor from reconciled snapshot | Start from a verified point | Wrong point risks skipping data |
| Cursor set to current `MAX(id)` | **Intentionally skip history** | Drops backlog if not permitted |
| Cursor restored from backup | Resume older state | May be out of sync with source/outbox |

Examples here default to `0L` when the key is absent, **assuming IDs > 0**. Never initialize checkpoints to `MAX(id)` at startup unless business requirements explicitly allow skipping historical records.

## 9. Compare-and-Set Checkpoint: Detecting Contention

~~~java
package com.example.incremental;

import org.springframework.integration.metadata.ConcurrentMetadataStore;

public final class IdCheckpoint {

    private final ConcurrentMetadataStore store;
    private final String key;

    public IdCheckpoint(
            ConcurrentMetadataStore store, String key) {
        this.store = store;
        this.key = key;
    }

    public long read() {
        String value = store.get(key);
        return value == null ? 0L : Long.parseLong(value);
    }

    public void advance(String expected, long nextId) {
        long previous = expected == null
            ? 0L : Long.parseLong(expected);

        if (nextId <= previous) {
            throw new IllegalArgumentException(
                "Checkpoint must increase");
        }

        String next = Long.toString(nextId);
        boolean success = expected == null
            ? store.putIfAbsent(key, next) == null
            : store.replace(key, expected, next);

        if (!success) {
            throw new IllegalStateException(
                "Checkpoint changed concurrently");
        }
    }
}
~~~

`expected` must be **the value read before SELECT**. Re-reading metadata right before `replace` and blindly accepting the newer value without checking your batch risks processing stale data and pushing the cursor into an inconsistent state.

**CAS only protects the metadata key; it does not lock source rows or retract events already sent to Kafka/HTTP.** When CAS fails, the worker must roll back local work in its transaction and re-SELECT from the updated cursor.

## 10. Building an Incremental MessageSource Reading from MetadataStore

To control checkpoint reading precisely, build a custom source extending `AbstractMessageSource<List<SourceEvent>>`. Each poll reads the cursor, queries IDs greater than the cursor, and CAS-updates the checkpoint **inside the local transaction opened by the poller**.

~~~java
package com.example.incremental;

public record SourceEvent(
    long id, String eventType, String payloadJson) {
}
~~~

~~~java
package com.example.incremental;

import java.util.List;
import org.springframework.integration.endpoint.AbstractMessageSource;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.JdbcTemplate;

public final class IncrementalEventSource
        extends AbstractMessageSource<List<SourceEvent>> {

    private static final String KEY = "source-event:last-id";

    private final JdbcTemplate jdbc;
    private final ConcurrentMetadataStore checkpoint;

    public IncrementalEventSource(
            JdbcTemplate jdbc, ConcurrentMetadataStore checkpoint) {
        this.jdbc = jdbc;
        this.checkpoint = checkpoint;
    }

    @Override
    protected Object doReceive() {
        String expected = checkpoint.get(KEY);
        long lastId = expected == null
            ? 0L : Long.parseLong(expected);

        List<SourceEvent> rows = jdbc.query(
            "SELECT id, event_type, payload_json "
          + "FROM source_event "
          + "WHERE id > ? ORDER BY id LIMIT ?",
            (rs, index) -> new SourceEvent(
                rs.getLong("id"),
                rs.getString("event_type"),
                rs.getString("payload_json")),
            lastId, 50);

        if (rows.isEmpty()) {
            return null; // Emit no message on this poll.
        }

        long next = rows.get(rows.size() - 1).id();
        String nextValue = Long.toString(next);

        boolean saved = expected == null
            ? checkpoint.putIfAbsent(KEY, nextValue) == null
            : checkpoint.replace(KEY, expected, nextValue);

        if (!saved) {
            throw new IllegalStateException(
                "Cursor race: another poller advanced it");
        }
        return rows;
    }

    @Override
    public String getComponentType() {
        return "jdbc:incremental-event-source";
    }
}
~~~

**Mandatory precondition:** `doReceive()` updates the checkpoint **before** downstream runs. Therefore you must use a transactional poller and **synchronous downstream handlers writing durably to the same `DataSource`** before COMMIT. If the source runs in autocommit and downstream fails, the SELECTed rows can be lost forever.

`AbstractMessageSource` wraps `List<SourceEvent>` into `Message<List<SourceEvent>>`. To turn each row into a separate message, add a downstream `Splitter`. `LIMIT ?` fits H2/PostgreSQL; SQL Server/Oracle use different syntax.

## 11. Writing Checkpoint and Outbox in the Same Transaction

A safer design than updating a cursor and immediately publishing to Kafka is:

1. Poller opens a JDBC transaction.
2. Source reads rows and CAS-updates the checkpoint within the transaction.
3. A **synchronous** handler writes all rows as outbox events in the same transaction.
4. COMMIT checkpoint and outbox together.
5. A separate publisher reads committed outbox rows, sends to Kafka/JMS, and marks them published with retry/deduplication.

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant S as IncrementalEventSource
    participant DB as Source + metadata + outbox DB
    participant W as OutboxWriter
    P->>DB: BEGIN
    P->>S: receive()
    S->>DB: Read checkpoint + SELECT id > lastId
    DB-->>S: Rows [101,102,103]
    S->>DB: CAS cursor -> 103 (uncommitted)
    S-->>W: Message<List<SourceEvent>> -> split
    W->>DB: INSERT outbox for 101,102,103
    alt Success
        P->>DB: COMMIT cursor + outbox
    else Handler/JDBC error
        P->>DB: ROLLBACK cursor + outbox
    end
~~~

### 11.1. OutboxWriter

~~~java
package com.example.incremental;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class OutboxWriter {

    private final JdbcTemplate jdbc;

    public OutboxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(SourceEvent row) {
        String eventId = "source-event-" + row.id();
        jdbc.update(
            "INSERT INTO event_outbox "
          + "(event_id, source_id, event_type, payload_json) "
          + "VALUES (?, ?, ?, ?)",
            eventId, row.id(), row.eventType(), row.payloadJson());
    }
}
~~~

`event_id` and `source_id` carry UNIQUE constraints. When a staged event is replayed, the application must distinguish **an identical duplicate** from **a conflict with the same ID and different payload**; never catch every duplicate-key error and treat it as success.

### 11.2. IntegrationFlow with Transactional Poller

~~~java
package com.example.incremental;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class IncrementalFlowConfiguration {

    @Bean
    public IncrementalEventSource incrementalEventSource(
            JdbcTemplate jdbc,
            @Qualifier("incrementalCheckpointStore")
            ConcurrentMetadataStore checkpoint) {
        return new IncrementalEventSource(jdbc, checkpoint);
    }

    @Bean
    public IntegrationFlow stageIncrementalEvents(
            IncrementalEventSource source,
            OutboxWriter writer,
            PlatformTransactionManager transactionManager) {
        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .handle(writer, "stage")
            .get();
    }
}
~~~

In this flow, `.split()` and `.handle(writer, "stage")` are **synchronous** when no async boundary is inserted; the poller's transaction spans all JDBC operations through the shared transaction manager and `DataSource`.

**Never insert an `ExecutorChannel`/`QueueChannel` before the outbox writer and assume checkpoint and outbox will still commit together.** The poller's thread-bound transaction does not propagate to another worker thread. Nor should you put the checkpoint on one `DataSource` and the outbox on another database and assume a local transaction makes them atomic.

## 12. Crash Windows and Outcomes

| Failure point | Checkpoint | Outbox | What must happen |
|---|---|---|---|
| Before SELECT | Unchanged | Not written | Next poll retries normally |
| After SELECT, before CAS | Unchanged | Not written | Rows remain readable |
| After CAS, before COMMIT | Rolled back on error | Rolled back | No rows skipped |
| Inserting 2nd outbox row fails | Rolled back | Whole batch rolled back | Retry from old checkpoint |
| After JDBC COMMIT | Advanced | Durably written | Publisher relay continues |
| Broker receives, publisher crashes before marking published | Unchanged | Event still pending | Re-publish possible; consumer must be idempotent |

A **local JDBC transaction** does not create a transaction across Kafka/JMS/HTTP. If the publisher sends to the broker and crashes before setting `published=true`, the event may be resent; that is **at-least-once**, not automatic “exactly-once delivery”.

With `DirectChannel`, synchronous failures can roll back the poller transaction. With `ExecutorChannel` or another queue/poller, the checkpoint can COMMIT before the work is actually processed. `send() == true` does not prove downstream committed.

## 13. Using the Built-In JDBC Inbound Adapter with a Dynamic Cursor

If you want to keep Spring Integration's `JdbcPollingChannelAdapter`, you can connect `MetadataStore` into **`selectSqlParameterSource`**:

~~~sql
SELECT id, event_type, payload_json
FROM source_event
WHERE id > :lastId
ORDER BY id
LIMIT 50;
~~~

Correct rules:

1. `:lastId` is read from the checkpoint **before each SELECT**.
2. The JDBC inbound adapter runs the query and emits `Message<List<SourceEvent>>`.
3. An **application handler** durably persists results and CAS-updates the checkpoint in the same local transaction.
4. For multi-instance deployments, the handler must verify the expected value used during SELECT and tolerate CAS conflicts, rather than blindly reading the latest checkpoint and overwriting it.

**Never assume that simply calling `selectSqlParameterSource(...)` will advance the checkpoint automatically.** The JDBC inbound adapter has no built-in mechanism for that.

### 13.1. Creating a Non-Caching SqlParameterSource from MetadataStore

A `SqlParameterSource` for SELECT is reused across polls. If a SpEL expression were cached on the first call, SQL would keep using the old cursor even after `MetadataStore` changed. `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` solves this.

~~~java
package com.example.incremental;

import java.sql.Types;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@Configuration
public class SelectCursorParameterConfiguration {

    public record CursorReader(ConcurrentMetadataStore store) {
        public long lastId() {
            String value = store.get("source-event:last-id");
            return value == null ? 0L : Long.parseLong(value);
        }
    }

    @Bean("cursorReader")
    public CursorReader cursorReader(
            @Qualifier("incrementalCheckpointStore")
            ConcurrentMetadataStore checkpoints) {
        return new CursorReader(checkpoints);
    }

    @Bean("cursorExpressions")
    public ExpressionEvaluatingSqlParameterSourceFactory
            cursorExpressions() {
        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "lastId", "@cursorReader.lastId()"));
        factory.setSqlParameterTypes(Map.of(
            "lastId", Types.BIGINT));
        return factory;
    }

    @Bean("cursorSelectParams")
    public SqlParameterSource cursorSelectParams(
            @Qualifier("cursorExpressions")
            ExpressionEvaluatingSqlParameterSourceFactory factory) {
        return factory.createParameterSourceNoCache("");
    }
}
~~~

The factory is a Spring-managed bean so SpEL has a bean resolver for `@cursorReader`. `createParameterSourceNoCache("")` returns a reusable parameter source across polls; each time `lastId` is needed, it reads the current value.

**Side effect:** because it does not cache, if `:lastId` appears twice in the SQL, the expression may be evaluated multiple times. Avoid expressions that increment counters or mutate state. With multiple pods, CAS/transactions or per-poll snapshotting are still required.

### 13.2. Java DSL 7.x: Incremental SELECT with `Jdbc.inboundAdapter`

Since Spring Integration **7.0**, the JDBC Java DSL provides `Jdbc.inboundAdapter(...)` and `JdbcInboundChannelAdapterSpec`:

~~~java
// Fragment: this is an ALTERNATIVE to the custom source in section 10.
// dataSource, cursorSelectParams, transactionManager, batchHandler
// are beans/variables provided by the application.
return IntegrationFlow.from(
        Jdbc.inboundAdapter(dataSource,
                "SELECT id, event_type, payload_json "
              + "FROM source_event "
              + "WHERE id > :lastId "
              + "ORDER BY id LIMIT 50")
            .selectSqlParameterSource(cursorSelectParams)
            .rowMapper((rs, rowNum) -> new SourceEvent(
                rs.getLong("id"),
                rs.getString("event_type"),
                rs.getString("payload_json")))
            .maxRows(50),
        endpoint -> endpoint.poller(
            Pollers.fixedDelay(Duration.ofSeconds(5))
                .maxMessagesPerPoll(1)
                .transactional(transactionManager)))
    .handle(batchHandler, "stageBatch")
    .get();
~~~

`batchHandler.stageBatch(List<SourceEvent>)` **is not provided by Spring Integration**. It must be an application handler responsible for:

- Writing the fetched rows to durable storage, such as an outbox.
- CAS-updating the checkpoint based on the watermark of that exact query pass, **never moving the watermark backward**.
- Throwing an exception if updating the cursor fails, so the outbox rolls back in the same transaction.
- Never publishing directly to Kafka/JMS before durable persistence commits.

To avoid races where the query parameter changes between reading and updating the checkpoint, either **build a custom source holding the expected baseline** as in section 10, or pass the exact cursor value used via headers/DTOs explicitly. This DSL fragment only shows how to **read** the checkpoint; it does not complete the full concurrency protocol by itself.

## 14. Spring Integration 6.x and XML

In **Spring Integration 6.x**, `JdbcPollingChannelAdapter` has `setSelectSqlParameterSource(...)`, while the 7.x JDBC Java DSL `Jdbc.inboundAdapter(...)` factory **does not exist**.

~~~java
package com.example.incremental;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LegacyIncrementalConfiguration {

    @Bean
    public IntegrationFlow incrementalOnSix(
            DataSource dataSource,
            SqlParameterSource cursorSelectParams,
            PlatformTransactionManager transactionManager,
            BatchOutboxStageHandler batchHandler) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_type, payload_json "
              + "FROM source_event WHERE id > :lastId "
              + "ORDER BY id LIMIT 50");
        source.setSelectSqlParameterSource(cursorSelectParams);
        source.setRowMapper((rs, rowNum) -> new SourceEvent(
            rs.getLong("id"),
            rs.getString("event_type"),
            rs.getString("payload_json")));
        source.setMaxRows(50);

        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .handle(batchHandler, "stageBatch")
            .get();
    }
}
~~~

Here `BatchOutboxStageHandler` is an **application-defined type** with method `stageBatch(List<SourceEvent>)`; it is not a built-in Spring Integration class. To run standalone, implement the handler and ensure checkpoint CAS, outbox, and transactions as described earlier.

An equivalent XML configuration snippet:

~~~xml
<!-- Fragment: int and int-jdbc namespaces must be declared. -->
<int:channel id="incrementalBatches"/>

<int-jdbc:inbound-channel-adapter
    id="incrementalJdbc"
    data-source="dataSource"
    channel="incrementalBatches"
    query="SELECT id, event_type, payload_json
           FROM source_event
           WHERE id > :lastId ORDER BY id"
    select-sql-parameter-source="cursorSelectParams"
    max-rows="50">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

This XML **does not yet** include a service activator to write the outbox and CAS the checkpoint. In production, add that stage or use a custom `MessageSource`. Do not wire `JdbcMetadataStore` directly into `select-sql-parameter-source`, because the attribute expects a `SqlParameterSource`.

## 15. When Is It Safe to Advance the Checkpoint?

| Situation | Should lastId be saved? | Explanation |
|---|---|---|
| Rows SELECTed into RAM | **No** | A crash loses the entire payload |
| Transformed into DTOs | **No** | DTOs still live only in memory |
| Sent to an in-memory/non-durable queue | Usually **no** | Queue contents can be lost on restart |
| Written to outbox in **the same DB transaction** | **Yes** | Cursor and work commit atomically |
| Received Kafka producer ACK | Possible, but has a crash window | Duplicates if crash occurs before checkpoint |
| Received HTTP 200 | Depends on remote contract | Lost response does not mean remote failed |
| Consumer completed work and ACKed | Possible per end-to-end design | Requires reconcilable protocol/ACKs |

**Data loss** example:

~~~text
SELECT 101..110
MetadataStore.put(lastId, "110") -> COMMIT
Application dies before sending to Kafka
Restart: WHERE id > 110
=> 101..110 are never read again.
~~~

**At-least-once and idempotency** example:

~~~text
SELECT 101..110
Work durably persisted / Kafka received
Crash before checkpoint
Restart re-reads 101..110
Consumer uses stable eventId to deduplicate
=> duplicates possible, but zero lost work.
~~~

For critical workloads, **at-least-once delivery + idempotent effects** is usually a more realistic goal than claiming “exactly-once” based solely on `lastId`.

## 16. Late-Commit Hazard: ID Order Is Not Commit Order

An easily overlooked failure mode:

~~~text
10:00  Transaction A allocates ID=105, has not COMMITted yet
10:01  Transaction B allocates ID=106 and COMMITs
10:02  Poller sees 106, advances cursor to 106
10:03  Transaction A COMMITs ID=105
10:04  Poller runs WHERE id > 106
       -> 105 is permanently skipped despite existing in the database.
~~~

Working CAS, restart-durable checkpoints, and transactional pollers still **cannot cure this bug**. The reason is that ID generation order does not force transactions to become visible at COMMIT in ID order.

**Never conclude “since we used `ORDER BY id`, nothing can be skipped”.** `ORDER BY` only sorts rows **already visible** in the query's snapshot.

Options:

1. Use CDC/transaction logs/commit-ordered cursors when every change must be captured in commit order.
2. Use an overlap window combined with idempotency and reconciliation.
3. Use a transactional outbox inside the source transaction if you control the writing application.
4. Use atomic claiming/locking if the source table acts as a work queue.
5. Use an ID cursor only when the source contract **genuinely guarantees** visibility ordering.

## 17. Composite Cursor `(updated_at, id)` for Tables with UPDATEs

If rows can be updated after creation, `id > :lastId` misses updates to older IDs. One approach is a lexicographic cursor over **timestamp and ID**:

~~~sql
SELECT id, updated_at, status
FROM source_entity
WHERE updated_at > :lastUpdatedAt
   OR (updated_at = :lastUpdatedAt AND id > :lastId)
ORDER BY updated_at, id
LIMIT :batchSize;
~~~

Example with identical timestamps:

| updated_at | id |
|---|---:|
| 2026-11-23 08:00:00 | 7 |
| 2026-11-23 08:00:00 | 8 |
| 2026-11-23 08:00:00 | 9 |

If you only saved the timestamp after fetching two rows, the next `updated_at > 08:00:00` query would **skip ID 9**. The `(timestamp, id)` pair resumes cleanly from `(08:00:00, 8)` to `(08:00:00, 9)`.

Storing a composite cursor in `MetadataStore` requires a concrete versioned format:

~~~text
KEY   = source-entity:cursor:v2
VALUE = 2026-11-23T08:00:00.000000Z|8
~~~

Define timezone (UTC), SQL timestamp precision, escaping/parsing, and key versioning. **Timestamp cursors still suffer from the late-commit hazard** if `updated_at` is assigned before COMMIT or written out of order; the tie-breaker only solves multiple rows sharing a timestamp.

## 18. Overlap Windows and Idempotency for Late-Arriving Data

One risk-reduction strategy is re-reading a lookback window before the saved watermark:

~~~sql
-- Pseudo SQL; time subtraction depends on DB/application:
SELECT id, updated_at, status
FROM source_entity
WHERE updated_at >= :checkpointMinusOverlap
ORDER BY updated_at, id;
~~~

When re-reading near the cursor, you need a stable key per **event/version**, not just the row ID if the same row undergoes multiple UPDATEs.

| Component | Role |
|---|---|
| Overlap | Makes late-committed/updated rows visible within a bounded window |
| Dedupe store | Avoids reprocessing the same event/version |
| Checkpoint | Tracks staged progress in stable regions |
| Backfill/reconciliation | Recovers late events exceeding the overlap window |
| CDC | Alternative when zero missed changes are permitted |

**Warning:** a finite overlap window cannot guarantee seeing transactions delayed **indefinitely**. Nor does a pure timestamp watermark detect `DELETE`s once a row vanishes from the current table. If the contract requires zero missed changes, use CDC or an append-only event log with proper semantics.

## 19. Multiple Instances: CAS Is Not a Distributed Work Queue

Two pods can read cursor 100 and both SELECT 101..110. One `replace("100","110")` succeeds while the other fails.

~~~text
Pod A: get 100 -> SELECT 101..110 -> CAS 100->110 succeeds
Pod B: get 100 -> SELECT 101..110 -> CAS 100->110 fails
~~~

If both use the same JDBC transaction for the cursor and **outbox**, Pod B rolls back all DML when CAS fails. However, if Pod B already sent HTTP/Kafka calls outside the DB before CAS, those sent events **cannot be retracted**.

| Architecture | Coordination mechanism |
|---|---|
| Single leader per stream | Distributed lock/leader lease |
| Partitioned stream | Separate cursor key per partition |
| Work queue in DB | Atomic claim + lease + row ownership |
| Transactional outbox | Atomic staging and dedicated publisher |
| CDC connector | Commit-log offsets/checkpoints |

Spring Integration has dedicated JDBC lock registries such as `JdbcLockRegistry`/`DefaultLockRepository`. Metadata CAS on a key **does not equal holding a distributed lock**, nor does it ensure proper data partitioning.

## 20. MetadataStore and Idempotent Receiver

A **checkpoint** tracks the highest processed position according to rules; a **processed-event store** records each completed event individually.

~~~text
Checkpoint:
  source:last-id -> 110

Processed IDs:
  source:evt-101 -> DONE
  source:evt-103 -> DONE
  source:evt-110 -> DONE
~~~

Spring Integration includes the **Idempotent Receiver** pattern supporting metadata stores or `MetadataStoreSelector`. However, the order of recording state determines reliability:

- Marking processed **before** the side effect risks losing the event on crash.
- Marking processed **after** the side effect in a separate transaction risks duplicate processing on crash.
- Within a single database, you can record the processed ID and business mutation in the **same local transaction**, backed by a unique constraint.
- When the same event ID arrives with a different payload, detect the **conflict** rather than treating it as a harmless duplicate.

If storing processed keys with a TTL, ensure the TTL outlives the maximum redelivery/replay window; expiring too early lets old events produce duplicate effects.

## 21. Managing Bootstrapping, Resets, and Backfills

| Operational action | Consequence |
|---|---|
| Deleting checkpoint | May re-read from the start, creating a huge backlog |
| Moving checkpoint backward | Replays history; requires deduplication and idempotent side effects |
| Moving checkpoint forward | Skips older rows; risks data loss |
| Changing `REGION` | Flow may no longer see the old cursor |
| Changing `lastId` format to timestamp | Requires a new key/format version |
| Restoring an old backup | Source/outbox/metadata can drift out of sync |

An operational runbook should include: stop or pause pollers; snapshot metadata and outbox; compute the target cursor; verify business impact; update only via controlled tooling; test with a single instance first; then scale concurrency back up.

**Never expose an HTTP endpoint letting callers set `lastId` or metadata regions** without strict authorization and auditing.

## 22. Error Handling, Retries, and Checkpoint Consistency

| Symptom | Cause | Resolution |
|---|---|---|
| Restarts from the beginning | In-memory `SimpleMetadataStore` / in-memory H2 | Use a real persistent JDBC/Redis store |
| Same rows keep reappearing | Cached select parameters or rollbacks | Use `createParameterSourceNoCache` and check transactions |
| Cursor advances while outbox is empty | Checkpoint committed before durable work | Put both in the same DB transaction |
| `replace` returns false | Another worker updated the key first | Roll back/retry entire poll; discard stale list |
| Cursor fails to parse | Malformed `MetadataStore` value | Halt/alert; never silently reset to 0 |
| Row ID 105 missing | Late commit behind watermark 106 | Overlap/CDC/backfill |
| `DuplicateKey` in outbox | Event already staged or same ID with different payload | Distinguish duplicate vs. conflict |
| Metadata table missing | Unapplied migration or wrong table prefix | Run vendor schema scripts |
| `FOR UPDATE` error | Lock hint incompatible with DB dialect | Configure vendor-accurate `setLockHint` |
| Pool exhausted / SQL timeout | Excessive polling, slow queries, locks | Limit batches, tune SQL, bound concurrency |

For deadlocks or transient network issues, retry **the entire transactional unit** after rollback with backoff/jitter and capped attempts. For schema bugs, malformed cursors, or invalid SQL, infinite retries only add load. When connectivity drops near COMMIT, the outcome is uncertain, so reconcile metadata/outbox and rely on stable event IDs.

## 23. Performance and Security

A single poll can read a checkpoint, run SELECT, CAS metadata, and INSERT multiple outbox rows. Monitor:

1. Poll counts, empty poll ratio, rows/poll, and latencies.
2. Last checkpoint, max visible ID, and lag over time.
3. CAS conflicts, transaction rollbacks, and duplicate/replay counts.
4. Pending outbox count, oldest unpublished event age, and publisher retries.
5. Hikari pool active/idle/pending counts, connection timeouts, and DB locks/deadlocks.
6. Late commits/reconciliation findings and backfilled source IDs.

**Never raise pool size or poll frequency endlessly** to compensate for missing indexes. SQL `WHERE id > :lastId ORDER BY id LIMIT :n` needs proper indexes; inspect explain plans on the production database.

`maxRows` on the JDBC adapter limits **rows per query**; `maxMessagesPerPoll` limits **`receive()` calls per trigger**. One `Message<List<SourceEvent>>` can hold 50 rows and a splitter produce 50 messages from just a single SELECT.

JDBC is **blocking I/O**. In WebFlux applications, never invoke JDBC on the Reactor Netty event loop. Use poller/worker threads or an appropriate reactive database stack; switching threads does not turn JDBC into R2DBC.

For security, grant the DB account access only to required metadata/source/outbox tables; never store PII/tokens in metadata values; never log full `payload_json`; avoid using event IDs as high-cardinality metric tags; manage TLS/credentials via a secret manager.

## 24. Unit Testing CAS and Verifying Rollback

### 24.1. Testing CAS with the Metadata Store

~~~java
// Test snippet; checkpointStore is injected from the Spring context.
String key = "test:cursor:cas";
checkpointStore.remove(key);

assertNull(checkpointStore.putIfAbsent(key, "100"));
assertEquals("100", checkpointStore.get(key));
assertTrue(checkpointStore.replace(key, "100", "105"));
assertFalse(checkpointStore.replace(key, "100", "104"));
assertEquals("105", checkpointStore.get(key));
~~~

This snippet requires JUnit assertion imports and a configured `ConcurrentMetadataStore` bean. Use test-only keys and never delete checkpoints used by production flows.

### 24.2. Testing Transaction Rollback

~~~java
package com.example.incremental;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class MetadataRollbackTest {

    @Autowired
    @Qualifier("incrementalCheckpointStore")
    ConcurrentMetadataStore store;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void rollbackDoesNotSaveCheckpoint() {
        String key = "test:rollback:checkpoint";
        store.remove(key);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                assertNull(store.putIfAbsent(key, "105"));
                throw new IllegalStateException("simulated failure");
            }));

        assertNull(store.get(key));
    }
}
~~~

This test assumes `JdbcMetadataStore` and `PlatformTransactionManager` share **the same `DataSource`**, the metadata table exists, and the Spring container manages lifecycles properly. It only proves metadata rollback—it does **not** yet prove outbox and checkpoint commit together.

### 24.3. End-to-End Integration Testing

With the schema from section 6, verify:

1. Checkpoint key is initially absent; source rows 101, 102, 103 are inserted.
2. Run one poll inside a transaction; outbox has three rows and checkpoint equals `"103"` after commit.
3. Run the next poll; outbox receives no extra rows.
4. Insert ID 104 and poll; checkpoint advances to `"104"`.
5. Make `OutboxWriter` throw on the second row; confirm **both checkpoint and outbox roll back**.
6. Verify the checkpoint survives app restarts with a persistent database, not just in-memory H2.
7. Attach a mock consumer/publisher and simulate a crash after broker ACK before marking the outbox published.

When testing a custom source, do not leave a background scheduler polling the same source table; otherwise tests will hit hard-to-reproduce races.

## 25. Testing Concurrency, Late Commits, and Recovery

| Scenario | Outcome to verify |
|---|---|
| Two pods read cursor 100 | One CAS succeeds, the other rolls back |
| CAS succeeds but outbox staging fails | Checkpoint is not committed |
| Broker receives then publisher crashes | Outbox stays pending; replay is idempotent |
| ID 106 commits before ID 105 | ID-only cursor can miss 105 |
| Same timestamp across two batches | `(updated_at, id)` pair does not drop simultaneous rows |
| Older row updated with ID < cursor | Needs `updatedAt`/change log or CDC |
| Late event beyond overlap | Detected by reconciliation, not falsely guaranteed |
| Metadata table missing | Clear startup/migration failure |
| Two regions with the same key | Metadata properly isolated as designed |
| Same region with colliding keys | Catches two flows trampling one checkpoint |
| Database outage mid-COMMIT | Retry/reconciliation avoids duplicated effects |

H2 works for basic tests; to verify locking, multi-JVM metadata CAS, and transaction isolation, use **Testcontainers or a production-compatible database** (PostgreSQL, SQL Server, Oracle, MySQL as applicable).

## 26. Example of Three Polls and Rollback Behavior

Suppose there are 123 source events, IDs 1 through 123, batch size 50, and **no late commits**:

~~~text
Poll 1: IDs   1..50  -> outbox 50 -> checkpoint 50
Poll 2: IDs  51..100 -> outbox 50 -> checkpoint 100
Poll 3: IDs 101..123 -> outbox 23 -> checkpoint 123
Poll 4: no rows      -> checkpoint stays 123
~~~

If the second poll fails while inserting the 10th outbox row and the transaction rolls back, the checkpoint must remain at 50; the next run re-reads `51..100`. If a transaction commits cursor 100 while the outbox only has 60 rows, the configuration **violates** the atomic staging contract and risks losing work.

## 27. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “JdbcMetadataStore automatically makes JDBC inbound incremental” | The JDBC source must apply the checkpoint in SELECT itself |
| “MetadataStore is where full messages are stored” | It is only key/value storage, unlike `JdbcMessageStore` |
| “SimpleMetadataStore persists across restarts” | In-memory only; lost on process restart |
| “`put` is equivalent to CAS” | No; use `replace` or `putIfAbsent` |
| “CAS prevents duplicate publishing absolutely” | Cannot retract external non-DB side effects |
| “Auto-increment ID means commits happen in ID order” | Transactions can commit out of ID order |
| “ORDER BY id prevents all late-commit skips” | It only orders already-visible rows |
| “The checkpoint is simply the max SELECTed ID” | Should advance only after a durable processing boundary |
| “No-cache SpEL solves multi-instance contention” | Locks/CAS/transactions are still required |
| “maxRows(50) triggers 50 SQL polls” | One `source.receive` can return a 50-row list |
| “Checkpoint commits atomically with Kafka via @Transactional” | JDBC transactions do not cover Kafka by default |
| “Timestamps alone never drop rows” | Tie-breakers are needed; late commits still happen |
| “A 5-minute overlap guarantees zero missed events” | Not if an event commits more than 5 minutes late |
| “Deleting the checkpoint is a safe fix” | Can trigger massive replays or huge backlogs |
| “JDBC inside WebFlux is non-blocking” | JDBC remains blocking I/O |

## 28. Practice Exercises

1. Build the `source_event`, `event_outbox`, and `INT_METADATA_STORE` schema on H2.
2. Declare a `JdbcMetadataStore` bean with `setRegion(...)` and inspect metadata rows directly via SQL.
3. Practice `get`, `putIfAbsent`, and `replace`; verify a failed CAS does not overwrite.
4. Use `SimpleMetadataStore` and compare restart behavior against a persistent store.
5. Write a custom `IncrementalEventSource` running SELECT by `lastId` and returning `Message<List<SourceEvent>>`.
6. Add a splitter, `OutboxWriter`, and transactional poller; observe cursor and outbox committing together.
7. Deliberately throw on the second row; verify transaction rollback and retry from the previous cursor.
8. Insert an `ExecutorChannel` before the outbox writer to demonstrate why the checkpoint can commit before staging.
9. Configure `ExpressionEvaluatingSqlParameterSourceFactory` for `:lastId` with `createParameterSourceNoCache("")`.
10. Build a Spring Integration 7.x JDBC inbound flow using `Jdbc.inboundAdapter(...)` and a cursor-updating handler.
11. Port the example to 6.x with `JdbcPollingChannelAdapter`/XML, comparing APIs and imports.
12. Run two workers sharing the same metadata region/key and analyze CAS conflicts and transactional rollbacks.
13. Partition regions/keys so workers read distinct partitions.
14. Have a source transaction with ID 105 commit after ID 106; demonstrate how an ID-only cursor skips 105.
15. Implement a `(updated_at, id)` cursor and test identical timestamps spanning two batches.
16. Build an overlap window, an idempotent processed-ID store, and reconciliation for late updates.
17. Use an outbox publisher to send to Kafka/JMS and simulate a crash after broker ACK before `published=true`.
18. Use Testcontainers to verify concurrent metadata updates against a real DB vendor.
19. Emit metrics: `lastId`, cursor lag, rows/poll, CAS failures, pending outbox rows, and late commits.
20. Write a checkpoint reset runbook covering snapshots, replay, deduplication, and target cursor verification.
21. Insert a malformed value into metadata; halt and alert rather than silently resetting to 0.
22. Compare watermark, atomic claim, transactional outbox, and CDC architectures for a zero-event-loss requirement.

**Design scenario:** two pods concurrently poll an append-only table with one million rows. The source allocates ID 105 but commits it after ID 106; Pod A has already advanced the checkpoint to 106. Meanwhile, the outbox publisher sends to Kafka and dies before marking `published`. Propose **CDC/commit-order cursors or overlap+reconciliation**, metadata CAS/ownership, atomic outbox staging, stable event IDs, ACK/retry rules, and required tests to prevent missed work and minimize duplicate side effects.

## 29. References

- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): key/value semantics, persistent stores, `ConcurrentMetadataStore`, and Idempotent Receiver.
- [Spring Integration — JDBC Metadata Store](https://docs.spring.io/spring-integration/reference/jdbc/metadata-store.html): `JdbcMetadataStore`, database schema, regions, locking, and transactions.
- [Spring Integration API — JdbcMetadataStore](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/metadata/JdbcMetadataStore.html): `get`, `putIfAbsent`, `replace`, `setRegion`, `setLockHint`.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): polling SELECT/UPDATE, `selectSqlParameterSource`, `maxRows`, and poller transactions.
- [Spring Integration API — JdbcPollingChannelAdapter 6.x](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): actual setters available on the JDBC source.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter` factory from 7.0.
- [Spring Integration API — AbstractMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractMessageSource.html): `doReceive()` and `receive()` contracts.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, `DirectChannel`, and rollbacks.
- [Spring Framework — JDBC and Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager` and `TransactionTemplate`.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): difference between metadata checkpoints and message persistence.

> **Remember:** `MetadataStore` persists checkpoints for incremental queries; `JdbcMetadataStore` provides durable storage and CAS operations. However, **the JDBC inbound adapter neither reads checkpoints nor advances watermarks automatically**: the application must wire the cursor into SQL and advance the mark only after work is durably saved. With multiple workers, use CAS/ownership; with late commits, use overlap/CDC/change logs; when sending to Kafka/JMS/HTTP, use outbox, retries, and idempotency. A steadily advancing cursor **does not mean** zero lost events.

# Locking and Avoiding Duplicate Row Claims in Spring Integration JDBC

## 1. Why Can Two Pollers Pick the Same Row?

A Spring Integration application runs across two pods, both using a **JDBC inbound channel adapter** to fetch `NEW` rows from a database and emit messages to Kafka, JMS, AMQP, or HTTP. On a single instance, running `SELECT ... WHERE state='NEW'` followed by `UPDATE state='CLAIMED'` looks sufficient to avoid re-reading data. In a multi-instance deployment, however, **two transactions can SELECT the same row before either transaction runs UPDATE**.

~~~text
Time           Pod A                            Pod B
----------------------------------------------------------------
t1             SELECT id=101, state='NEW'
t2                                              SELECT id=101, state='NEW'
t3             UPDATE id=101 -> CLAIMED (1)
t4             COMMIT
t5                                              UPDATE id=101
                                                WHERE state='NEW' (0)
t6             publish event 101
t7                                              still holds row 101 in the
                                                List SELECTed at t2;
                                                publishing causes a duplicate.
~~~

Pod B's `UPDATE ... WHERE state='NEW'` **can succeed in SQL with 0 affected rows**. Even though the row was not updated, **the earlier SELECT result has not vanished from the Java `List`**. Therefore, you cannot equate “no SQL error” with the pod having won ownership of the row.

This lesson, **Locking and Avoiding Duplicate Row Claims**, belongs to the **Adapter JDBC** chapter in the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and managing message contracts, errors, and connection lifecycles. Here the focus is **row ownership, locking, transactions, claiming, retries, and idempotency**.

**Two separate questions must be answered:** (1) How do we ensure only one worker *claims* a unit of work at a time? (2) How do we ensure that when work is *redelivered*, business effects are not duplicated? Locking solves (1) within the database; idempotency/outbox solves (2) across retries and external systems.

## 2. Lesson Objectives and Scope

After this lesson, learners can:

1. Reproduce the race condition from `SELECT → UPDATE` and pinpoint where duplicates arise.
2. Distinguish **pessimistic row locks**, **optimistic versioning**, **atomic claims**, **leases**, **fencing tokens**, and **idempotency**.
3. Use `FOR UPDATE SKIP LOCKED` on PostgreSQL, and understand why equivalents on MySQL, SQL Server, and Oracle **are not completely identical**.
4. Configure a transactional Spring Integration JDBC inbound poller and explain why `DirectChannel` differs from `ExecutorChannel`.
5. Build a `MessageSource` using **PostgreSQL `UPDATE ... RETURNING`** to emit strictly the rows actually claimed.
6. Design lease/timeout/recovery for process crashes and fencing to prevent stale workers from overwriting newer workers' state.
7. Test concurrency with two real transactions while measuring lock contention, deadlocks, and duplicate business effects.

No single locking option fits every workload. PostgreSQL-specific SQL examples will be clearly marked; never copy them to H2, SQL Server, MySQL, or Oracle without verifying SQL dialects and transaction semantics.

## 3. Concepts: Read, Lock, Claim, and Successful Processing

| Concept | Definition | What is not yet guaranteed |
|---|---|---|
| **Read** | Row appeared in a SELECT `ResultSet` | Worker owns the row |
| **Row lock** | DB blocks or coordinates concurrent access to a row | An external broker received the event |
| **Claim** | DB records worker state/ownership for the task | Work succeeded |
| **Lease** | Time-bounded claim; can be reclaimed upon expiry | The old worker has definitely stopped running |
| **Fencing token** | Claim code/version that changes on each acquisition | Remote service automatically rejects old tokens |
| **Optimistic locking** | Conditional UPDATE on version/state, checking affected rows | Only one worker ever SELECTed the row |
| **Pessimistic locking** | Locks rows prior to updating | Absence of deadlocks/starvation |
| **Idempotent effect** | Receiving the same event multiple times causes no duplicate side effect | Message is transmitted only once |
| **Transactional outbox** | Writes outbound event and DB mutation in one local transaction | Kafka/JMS consumer finished processing |
| **Exactly-once** | Term that must specify its scope (read, publish, effect) | System-wide guarantee without an explicit protocol |

A common state model:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> CLAIMED: atomic claim
    CLAIMED --> STAGED: stage durable outbox
    CLAIMED --> NEW: lease expired / recover
    CLAIMED --> FAILED: terminal error
    STAGED --> PUBLISHED: broker ACK + publisher bookkeeping
    FAILED --> NEW: controlled replay
    PUBLISHED --> [*]
~~~

**Be careful with state names:** `STAGED` may mean the outbox row is durable, **not** that the consumer applied the side effect. If a pipeline executes work directly inside the worker instead of using an outbox, you may use `DONE` once the transactional work completes. Define each state explicitly per business contract.

## 4. Message Ordering Does Not Replace Row Ownership

Per the Spring Integration JDBC Reference, the **inbound channel adapter** executes SELECT and emits **one message containing the entire result set as a `List`**; by default each row is a `Map<String,Object>`, while a custom `RowMapper<T>` produces DTOs.

~~~text
Poller calls receive() once
  -> SELECT fetches 20 rows
  -> RowMapper called 20 times
  -> 1 Message<List<JobRow>>
  -> Splitter
  -> 20 Message<JobRow>
~~~

Do not confuse these limits:

| Configuration | Unit | Example |
|---|---|---|
| JDBC adapter `maxRows(20)` | At most 20 rows per query result | Not 20 poll executions |
| `maxMessagesPerPoll(1)` | At most one `receive()` per trigger | Not one row |
| SQL `LIMIT 20` | Rows returned by database on SELECT | Choose vendor-specific SQL |
| `.split()` | Turns a list into individual messages | Does not lock the DB |
| `DirectChannel` | Runs synchronously on caller thread | Can participate in the JDBC transaction |
| `ExecutorChannel` | Dispatches to an executor thread | Does not carry thread-bound JDBC transactions by default |

**With two pods, `maxMessagesPerPoll(1)` on each pod does not prevent both from receiving row 101.** Only a database/partition ownership policy handles that.

## 5. Strategies to Avoid Duplicate Claims: Choosing by Need

| Strategy | Best fit | Strengths | Limitations |
|---|---|---|---|
| Single leader/poller | Small flows, simple SLA | Easy to operate and debug | Needs failover/leader election |
| Key-based partitioning | Stable partitioned sources | Reduces contention | Needs rebalancing and ownership |
| `SELECT FOR UPDATE SKIP LOCKED` | DB queues, multiple consumers | Skips locked rows | Must hold TX/lock until UPDATE |
| Atomic `UPDATE ... RETURNING` | PostgreSQL work queues | Returns only actually claimed rows | Vendor-specific SQL |
| `UPDLOCK/READPAST/OUTPUT` | SQL Server work queues | Supports locking and returning rows | Complex hints/RCSI/page locks |
| Optimistic `UPDATE ... WHERE version=...` | Expected-version updates | No long read locks | Can read duplicates; must handle 0 rows |
| Lease + fencing | Workers can crash or stall | Recovery and stale-completion prevention | Requires clock/ownership policy |
| Outbox + idempotent consumer | External non-DB side effects | Safer retries | May publish duplicates; must dedupe |
| CDC/change log | Following commit-log changes | Avoids polling misses | Connector/checkpoint operations |

The right choice depends on **DB vendor**, ability to modify the source schema, replica count, processing duration, and duplicate-**effect** requirements.

## 6. Setting Up Spring Boot, Schema, and Sample Data

Examples use Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC, and PostgreSQL. Let the Spring Boot BOM manage compatible versions; the JDBC Java DSL `Jdbc.inboundAdapter` starts in Spring Integration **7.0**, whereas `JdbcPollingChannelAdapter` works on 6.x.

~~~groovy
// build.gradle (dependencies) for the practice app
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
~~~

~~~yaml
# application.yml (illustrative values; secrets via environment)
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/integration_demo
    username: integration_app
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
app:
  worker-id: "${WORKER_ID}"
~~~

`${DB_PASSWORD}` and `${WORKER_ID}` are Spring Boot placeholders requiring their respective environment variables. `WORKER_ID` must differ across replicas. Never commit real credentials to Git; use a secret manager in production.

Create the sample schema in `schema.sql` of your **practice application** (not a file to write in this task):

~~~sql
CREATE TABLE work_item (
    id             BIGINT PRIMARY KEY,
    event_id       VARCHAR(80) NOT NULL UNIQUE,
    payload_json   TEXT NOT NULL,
    state          VARCHAR(24) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    claimed_by     VARCHAR(100),
    claim_token    UUID,
    claimed_at     TIMESTAMPTZ,
    lease_until    TIMESTAMPTZ,
    staged_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_work_item_ready
    ON work_item (created_at, id)
    WHERE state = 'NEW';

CREATE INDEX idx_work_item_lease
    ON work_item (lease_until, id)
    WHERE state = 'CLAIMED';

CREATE TABLE job_outbox (
    event_id      VARCHAR(80) PRIMARY KEY,
    work_id       BIGINT NOT NULL UNIQUE,
    payload_json  TEXT NOT NULL,
    published     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO work_item(id,event_id,payload_json,state)
VALUES
    (101,'evt-101','{"orderId":"ORD-101"}','NEW'),
    (102,'evt-102','{"orderId":"ORD-102"}','NEW'),
    (103,'evt-103','{"orderId":"ORD-103"}','NEW'),
    (104,'evt-104','{"orderId":"ORD-104"}','STAGED');
~~~

Indexes on `state`/`created_at`/`lease_until` should be verified with `EXPLAIN (ANALYZE, BUFFERS)` under realistic workloads; the partial indexes above are **PostgreSQL-specific**. At millions of rows, index choice and batch size significantly impact lock contention.

## 7. Transactional Poller: Prerequisite

The Spring Integration JDBC inbound source supports **SELECT** plus a post-SELECT **UPDATE** to mark fetched rows. The poller can be wrapped in a Spring JDBC transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(3))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

With a `PlatformTransactionManager` managing the right `DataSource`, SELECT and UPDATE in one poll can share **the same local DB transaction**. Synchronous handlers via `DirectChannel` can also stay inside the transaction until the poller finishes.

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant A as JDBC inbound source
    participant DB as Database
    participant H as DirectChannel handler
    P->>DB: BEGIN
    P->>A: receive()
    A->>DB: SELECT NEW ... FOR UPDATE SKIP LOCKED
    DB-->>A: Rows + locks held
    A->>DB: UPDATE rows to CLAIMED
    A-->>H: Message<List<Row>>
    H->>DB: INSERT job_outbox
    alt Handler succeeds
        P->>DB: COMMIT and release locks
    else Handler throws
        P->>DB: ROLLBACK and release locks
    end
~~~

**Mandatory rule:** `SELECT ... FOR UPDATE` must execute inside an **open** transaction spanning from before SELECT through UPDATE. If `autocommit=true` and SELECT finishes before UPDATE, row locks are released immediately, letting another worker SELECT the same rows.

`@Transactional(readOnly=true)` is the wrong setting for a poll running both SELECT and UPDATE; you must use a read-write transaction. Never hold transactions open waiting on slow remote HTTP/Kafka calls.

## 8. PostgreSQL: SELECT FOR UPDATE SKIP LOCKED

PostgreSQL supports `FOR UPDATE` to acquire row locks, `NOWAIT` to fail immediately if a lock cannot be acquired, and `SKIP LOCKED` to **skip rows currently locked by another transaction**.

~~~sql
-- PostgreSQL; must execute inside an open transaction.
SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;
~~~

Suppose transaction A locks IDs 101 and 102; when B runs the same query, it picks 103 onward instead of blocking. When both A and B execute **locking SELECT → UPDATE state → COMMIT**, they divide work without claiming the same rows.

**Limitations per PostgreSQL documentation:**
- `SKIP LOCKED` returns an **inconsistent view**; it suits queue-like processing, not exact inventory sums or financial reports.
- It only applies to **row-level locks**; ordinary table-level locks are still acquired as usual.
- `ORDER BY` combined with locks and concurrent updates does not guarantee global system-wide processing order.
- `LIMIT` stops locking once enough rows are found, whereas `OFFSET` may still lock skipped rows; queue polling generally avoids OFFSET pagination.
- If one row stays locked for a long time, workers keep skipping it; track metrics and starvation/recovery policies.

### 8.1. Updating Locked Rows in the Same Transaction

~~~sql
UPDATE work_item
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id IN (:ids) AND state = 'NEW';
~~~

`:ids` must come from **the exact locked SELECT result**, never cached from a prior poll. `:workerId` is supplied by the application, never from an untrusted request. With proper transactions and all workers following the same locking protocol, rows locked by A cannot be claimed simultaneously by B while locks hold.

**Never** run a locking SELECT in transaction A and send the ID list over an `ExecutorChannel` for transaction B to update later. By then A's locks may already be gone before B updates.

## 9. Spring Integration Java DSL 7.x: Locking SELECT and UPDATE in a Poller

In Spring Integration **7.x**, the Java DSL factory `Jdbc.inboundAdapter(...)` uses `JdbcInboundChannelAdapterSpec`; this lets you keep the built-in JDBC inbound adapter while adding SQL locking to SELECT.

~~~java
package com.example.integration;

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
public class LockedJdbcInboundFlow {

    public record JobRow(
        long id, String eventId, String payloadJson) { }

    @Bean
    public IntegrationFlow lockedWorkItems(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String select = """
            SELECT id, event_id, payload_json
            FROM work_item
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            FOR UPDATE SKIP LOCKED
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, select)
                    .maxRows(20)
                    .rowMapper((rs, n) -> new JobRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getString("payload_json")))
                    .updateSql(
                        "UPDATE work_item "
                      + "SET state = 'CLAIMED', "
                      + "    claimed_at = CURRENT_TIMESTAMP, "
                      + "    attempt_count = attempt_count + 1 "
                      + "WHERE id IN (:ids) AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(JobRow.class::cast)
                            .map(JobRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> list && !list.isEmpty())
            .split()
            .channel("lockedJobs")
            .get();
    }
}
~~~

**Contract of this example:**

1. The poller opens a read-write transaction for SELECT/UPDATE.
2. PostgreSQL returns `NEW` rows **not locked** by any other worker.
3. `RowMapper` builds `List<JobRow>`.
4. `updateSqlParameterSourceFactory` uses **this SELECT's own result list** to bind `:ids`.
5. Locked rows are updated before the transaction ends.
6. The adapter emits one list message; the splitter breaks it into one message per `JobRow`.

**Design limitation:** this snippet marks `CLAIMED`, but **does not issue a `claim_token`/lease or handle crashes after COMMIT**. A handler on `lockedJobs` may run in a separate transaction, especially if a channel/handler introduces an async boundary. This example demonstrates **proper locking for SELECT+UPDATE**, not a full production pipeline.

### 9.1. Which Payload Should the Handler Receive?

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class LockedJobConsumer {

    @ServiceActivator(inputChannel = "lockedJobs")
    public void process(LockedJdbcInboundFlow.JobRow job) {
        System.out.println(job.eventId());
    }
}
~~~

The handler receives a single `JobRow` because `.split()` ran upstream. `System.out.println` is a demo only, not a durable acknowledgement or broker commit. For real Kafka/JMS integration, add retries/leases/outbox and stable business event IDs.

## 10. Spring Integration 6.x: Using JdbcPollingChannelAdapter Directly

The Java DSL factory `Jdbc.inboundAdapter(...)` was introduced in Spring Integration 7.0. In **6.x**, instantiate `JdbcPollingChannelAdapter` and wrap the poller in a transaction:

~~~java
package com.example.integration;

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
public class LegacyLockedJdbcFlow {

    @Bean
    public IntegrationFlow lockedJobsSix(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_id, payload_json "
              + "FROM work_item WHERE state='NEW' "
              + "ORDER BY created_at, id LIMIT 20 "
              + "FOR UPDATE SKIP LOCKED");
        source.setMaxRows(20);
        source.setRowMapper((rs, n) ->
            new LockedJdbcInboundFlow.JobRow(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("payload_json")));
        source.setUpdateSql(
            "UPDATE work_item SET state='CLAIMED' "
          + "WHERE id IN (:ids) AND state='NEW'");
        source.setUpdateSqlParameterSourceFactory(result -> {
            var rows = (java.util.List<?>) result;
            var ids = rows.stream()
                .map(LockedJdbcInboundFlow.JobRow.class::cast)
                .map(LockedJdbcInboundFlow.JobRow::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .channel("lockedJobsSix")
            .get();
    }
}
~~~

This is an **alternative** to the 7.x flow; do not enable both simultaneously in a single-worker test on the same table. The `work_item` DDL in section 6 and `JobRow` DTO are reused to keep the example concise. For standalone 6.x projects, place `JobRow` in a DTO file without depending on the 7.x configuration class.

## 11. XML: Transaction Must Span Both SELECT and UPDATE

~~~xml
<!-- XML fragment; declare int and int-jdbc namespaces. -->
<int:channel id="lockedBatches"/>

<int-jdbc:inbound-channel-adapter
    id="lockedJdbcPoller"
    data-source="dataSource"
    channel="lockedBatches"
    query="SELECT id, event_id, payload_json
           FROM work_item
           WHERE state='NEW'
           ORDER BY created_at, id
           LIMIT 20
           FOR UPDATE SKIP LOCKED"
    update="UPDATE work_item
            SET state='CLAIMED'
            WHERE id IN (:id) AND state='NEW'"
    max-rows="20">
    <int:poller fixed-delay="3000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

With the default mapper, `:id` is built from the `id` column of the result list. XML is a fragment requiring corresponding Spring beans/namespaces. If you need one message per row, place an `<int:splitter>` downstream; transaction scope still depends on channel and poller synchronicity.

**Never put `FOR UPDATE SKIP LOCKED` into a reporting/read-only SELECT** that does not share a transaction with UPDATE. Once the lock is released, it no longer protects the claim.

## 12. Atomic Claim: Emitting Strictly the Rows Actually Updated

The plain adapter `SELECT → UPDATE` pattern has a subtle verification gap: the row list is built **before UPDATE**, and the list does not automatically shrink if the update count is smaller. For multi-instance queues, a stronger approach is an **atomic claim**: select and mark in **one SQL statement**, returning only the rows **actually updated**.

On PostgreSQL, combine a CTE, row locks, and `UPDATE ... RETURNING`:

~~~sql
WITH picked AS (
    SELECT id
    FROM work_item
    WHERE state = 'NEW'
    ORDER BY created_at, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE work_item AS w
SET state = 'CLAIMED',
    claimed_by = :workerId,
    claim_token = :claimToken,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
    attempt_count = attempt_count + 1
FROM picked
WHERE w.id = picked.id
RETURNING w.id, w.event_id, w.payload_json,
          w.claim_token;
~~~

**Characteristics:**

- `picked` holds at most 20 `NEW` IDs that this transaction managed to lock.
- `UPDATE` modifies **those exact IDs** inside the same statement/transaction.
- `RETURNING` returns data from **the rows actually updated**, not a separate earlier SELECT.
- `claim_token` identifies the current **ownership instance**; generate a fresh token on reclaim.
- `lease_until` bounds how long the worker has to complete work per contract.
- If zero rows are claimed, the statement returns **0 rows**; that is not an error by default.
- `RETURNING` does not guarantee output order; if downstream needs ordering, sort by key after receipt, and design cross-worker ordering separately.

**Important:** this is **PostgreSQL SQL**, not portable SQL syntax. Real SQL must be tested for transaction isolation, indexes, driver behavior, retries, and row counts on your target DB.

### 12.1. Why Not Stuff `UPDATE RETURNING` into Arbitrary JDBC Inbound SELECTs?

`JdbcPollingChannelAdapter` is primarily designed to run a **SELECT query** to produce messages, with an optional **UPDATE query**. An `UPDATE ... RETURNING` statement is **DML with a result set** in PostgreSQL. Do not assume `query=...` on the built-in adapter behaves identically as a message source for this statement across all drivers and versions.

When choosing atomic-claim SQL, the cleanest approach is writing a **dedicated `MessageSource` using Spring JDBC** or an appropriate stored procedure. Then you know for sure that the emitted list matches `RETURNING`, can attach a transaction manager on the poller, and build messages directly from the real result set.

## 13. Atomic-Claim MessageSource Using NamedParameterJdbcTemplate

### 13.1. DTO for Claimed Rows

~~~java
package com.example.integration;

import java.util.UUID;

public record ClaimedJob(
    long id,
    String eventId,
    String payloadJson,
    UUID claimToken) {
}
~~~

With this DTO, the business key `eventId` stays stable across retries, while `claimToken` changes on **each ownership acquisition**. Never use the claim token as the Kafka event ID, because a new token on retry prevents consumers from deduplicating.

### 13.2. Building the Atomic `UPDATE RETURNING` Source

~~~java
package com.example.integration;

import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import org.springframework.integration.endpoint.AbstractMessageSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public final class AtomicClaimMessageSource
        extends AbstractMessageSource<List<ClaimedJob>> {

    private static final String CLAIM_SQL = """
        WITH picked AS (
            SELECT id
            FROM work_item
            WHERE state = 'NEW'
            ORDER BY created_at, id
            LIMIT 20
            FOR UPDATE SKIP LOCKED
        )
        UPDATE work_item AS w
        SET state = 'CLAIMED',
            claimed_by = :workerId,
            claim_token = :claimToken,
            claimed_at = CURRENT_TIMESTAMP,
            lease_until =
                CURRENT_TIMESTAMP + INTERVAL '90 seconds',
            attempt_count = attempt_count + 1
        FROM picked
        WHERE w.id = picked.id
        RETURNING w.id, w.event_id,
                  w.payload_json, w.claim_token
        """;

    private final NamedParameterJdbcTemplate jdbc;
    private final String workerId;

    public AtomicClaimMessageSource(
            NamedParameterJdbcTemplate jdbc,
            String workerId) {
        this.jdbc = jdbc;
        this.workerId = workerId;
    }

    @Override
    protected Object doReceive() {
        UUID token = UUID.randomUUID();

        MapSqlParameterSource params =
            new MapSqlParameterSource()
                .addValue("workerId", workerId)
                .addValue("claimToken", token);

        List<ClaimedJob> claimed = jdbc.query(
            CLAIM_SQL, params,
            (rs, rowNum) -> new ClaimedJob(
                rs.getLong("id"),
                rs.getString("event_id"),
                rs.getString("payload_json"),
                rs.getObject("claim_token", UUID.class)));

        if (claimed.isEmpty()) {
            return null;
        }

        // RETURNING does not guarantee preserving CTE order.
        claimed.sort(Comparator.comparingLong(ClaimedJob::id));
        return claimed;
    }

    @Override
    public String getComponentType() {
        return "jdbc:atomic-claim-work-item";
    }
}
~~~

This is **PostgreSQL-specific**. Spring JDBC executes the `RETURNING` statement through the JDBC driver and maps the result set; test against your exact PgJDBC/SQL version. `AbstractMessageSource` wraps `List<ClaimedJob>` into a message; returning `null` signals no message on this poll.

**Limitation of this source:** it *claims* rows, without yet writing an outbox or completing work. If downstream persists work in the **same transaction** before COMMIT, claim and staging roll back together. If downstream is async and the poller commits right away, you need leases/recovery so work never gets stuck.

## 14. Writing Outbox, Finalizing Claim, and Flow Configuration

### 14.1. OutboxStager Operating Only in the Same Database

~~~java
package com.example.integration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JobOutboxStager {

    private final JdbcTemplate jdbc;

    public JobOutboxStager(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void stage(ClaimedJob job) {
        // event_id UNIQUE: never stage the same event twice.
        jdbc.update(
            "INSERT INTO job_outbox "
          + "(event_id, work_id, payload_json) "
          + "VALUES (?, ?, ?)",
            job.eventId(), job.id(), job.payloadJson());

        int updated = jdbc.update(
            "UPDATE work_item "
          + "SET state='STAGED', staged_at=CURRENT_TIMESTAMP "
          + "WHERE id=? AND state='CLAIMED' AND claim_token=?",
            job.id(), job.claimToken());

        if (updated != 1) {
            throw new IllegalStateException(
                "Worker no longer owns job " + job.id());
        }
    }
}
~~~

If `INSERT` hits a duplicate event ID, `DuplicateKeyException` normally fails the transaction. With recovery replays, the application must verify whether the staged event has **identical content** versus a conflict, rather than catching all unique violations as success.

`WHERE claim_token=?` is a **fencing condition** inside the database: a worker holding an old token cannot finalize state after its token was replaced. This is not yet distributed fencing at an external service; external services also need idempotency keys/versions if work triggers non-DB side effects.

### 14.2. Transactional IntegrationFlow for the Custom Source

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class AtomicClaimFlowConfiguration {

    @Bean
    public AtomicClaimMessageSource atomicClaimSource(
            DataSource dataSource,
            @Value("${app.worker-id}") String workerId) {
        return new AtomicClaimMessageSource(
            new NamedParameterJdbcTemplate(dataSource), workerId);
    }

    @Bean
    public IntegrationFlow stageClaimedJobs(
            AtomicClaimMessageSource source,
            JobOutboxStager stager,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(source,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(2))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .split()
            .handle(stager, "stage")
            .get();
    }
}
~~~

Set `app.worker-id` to a **unique worker instance ID** supplied by deployment/config; never share a hardcoded ID across pods. For stricter leader/partition ownership requirements, add an appropriate coordination mechanism.

**Guarantees in this pattern hold only when:**
- `AtomicClaimMessageSource`, `JobOutboxStager`, and `PlatformTransactionManager` use **the same `DataSource`**.
- There is no async `ExecutorChannel`/`QueueChannel` between the source and writer.
- `JobOutboxStager.stage` throws when staging fails; the poller does not swallow exceptions and commit.
- The database transaction rolls back if the handler fails.
- The outbox publisher runs separately and handles retries/idempotency.

Thus a single transaction claims rows, writes durable outbox records, and transitions `CLAIMED → STAGED`. Kafka/JMS publishing happens **only after** this transaction commits.

### 14.3. Why Two Kinds of IDs Are Needed

| ID | Example | Stable across retries? | Purpose |
|---|---|---|---|
| `work_item.id` | 101 | Yes | DB row primary key |
| `event_id` | `evt-101` | **Yes** | Business event / consumer deduplication |
| `claim_token` | Per-claim UUID | **No** | Prevents stale worker from finalizing state |
| `worker_id` | `pod-2` | Instance lifetime | Logs, lease owner, operations |
| `poll_id` | One correlation ID per poll | No | Tracing a single `source.receive` pass |

A token/UUID regenerated on every retry is **unsuitable as an event ID** when consumers rely on event IDs to avoid duplicate business effects.

## 15. SQL Server: UPDLOCK, READPAST, and OUTPUT

SQL Server does not use PostgreSQL's `FOR UPDATE SKIP LOCKED` syntax. The standard combination is **`UPDLOCK`** to take update locks when reading and **`READPAST`** to skip rows locked by other transactions; **`ROWLOCK`** is a hint, not a guarantee that the DB will only take row locks.

Example locking read inside a transaction:

~~~sql
-- SQL Server; example SELECT under matching isolation/read-committed settings.
SELECT TOP (20)
    id, event_id, payload_json
FROM dbo.work_item WITH (
    UPDLOCK, READPAST, ROWLOCK, READCOMMITTEDLOCK
)
WHERE state = 'NEW'
ORDER BY created_at, id;
~~~

**Practical limitations:**
- `READPAST` skips **row-level locks**, but does **not** automatically skip page-level locks.
- `UPDLOCK` holds update locks until transaction end, reducing the chance two readers pick the same job.
- When `READ_COMMITTED_SNAPSHOT` is enabled, combining lock hints and isolation is constrained; per Microsoft docs, some scenarios require `READCOMMITTEDLOCK`.
- Inspect lock escalation, deadlocks, index access plans, and database compatibility levels.
- `NOLOCK`/`READUNCOMMITTED` is **never** a safe queue concurrency tool: it can read uncommitted data.

SQL Server supports `OUTPUT inserted...` to return the rows actually modified. An illustrative statement can pair a CTE choosing candidate rows:

~~~sql
-- SQL Server T-SQL; test under accurate isolation/lock hints.
;WITH picked AS (
    SELECT TOP (20) id
    FROM dbo.work_item WITH (
        UPDLOCK, READPAST, ROWLOCK, READCOMMITTEDLOCK
    )
    WHERE state='NEW'
    ORDER BY created_at, id
)
UPDATE w
SET state='CLAIMED',
    claimed_by=@workerId,
    claimed_at=SYSUTCDATETIME(),
    attempt_count=attempt_count+1
OUTPUT inserted.id, inserted.event_id,
       inserted.payload_json
FROM dbo.work_item AS w
JOIN picked AS p ON p.id=w.id;
~~~

This returns **modified rows** via `OUTPUT`, though `@workerId` parameter syntax belongs to T-SQL clients; with Spring JDBC, bind parameters per your driver/template rather than copying `@workerId` as if it were Spring's `:workerId` named parameter. The DDL in section 6 is PostgreSQL and **cannot run verbatim** on SQL Server due to `TIMESTAMPTZ`/`UUID` differences.

## 16. MySQL 8.0+/8.4 InnoDB: SKIP LOCKED Exists but Differs from PostgreSQL

MySQL InnoDB supports locking reads `SELECT ... FOR UPDATE SKIP LOCKED` inside a transaction:

~~~sql
-- MySQL InnoDB; autocommit must be managed by the transaction.
START TRANSACTION;

SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- UPDATE the SELECTed and locked IDs in the same transaction.
UPDATE work_item
SET state='CLAIMED', claimed_by=?
WHERE id IN (?,?,...) AND state='NEW';

COMMIT;
~~~

`?` are illustrative JDBC bind placeholders; never concatenate ID lists unchecked into SQL strings. With Spring's `NamedParameterJdbcTemplate`, you can use `:ids` with collection binding.

**Key differences to remember:**
- Under `REPEATABLE READ`, InnoDB may use **next-key/gap locks**; index design and isolation affect lock ranges.
- `SKIP LOCKED` produces an inconsistent view suited to work queues, not exact reporting.
- MySQL docs note that statements using `NOWAIT`/`SKIP LOCKED` are unsafe for **statement-based replication**; check your replication format.
- Do not assume your MySQL version supports PostgreSQL-style `UPDATE ... RETURNING`; typically use locking SELECT + UPDATE in the same transaction or a stored procedure/claim strategy.

MySQL is not H2. Run concurrency tests on real InnoDB and verify transactions/autocommit via Spring JDBC.

## 17. Oracle and Other DB Vendors

Oracle provides `SELECT ... FOR UPDATE SKIP LOCKED` in supported versions, though interactions with `FETCH FIRST`, `ROWNUM`, cursor fetching, and locking queries have version- and SQL-structure-specific restrictions.

~~~sql
-- Oracle: locking read skeleton, batch limit not yet applied.
SELECT id, event_id, payload_json
FROM work_item
WHERE state = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;
~~~

**Do not slap `FETCH FIRST n ROWS ONLY` onto every `FOR UPDATE` query assuming it works identically across all Oracle versions.** Some versions/forms have syntax restrictions or lock behaviors. Choose bounded fetching, stored procedures, or atomic claims per your Oracle docs/driver and run real concurrency tests.

Summary matrix:

| DB vendor | Common approach | Must verify specifically |
|---|---|---|
| PostgreSQL | `FOR UPDATE SKIP LOCKED`; `UPDATE ... RETURNING` | CTE, lock timeout, READ COMMITTED, starvation |
| SQL Server | `UPDLOCK + READPAST`; `OUTPUT inserted` | RCSI, row/page locks, lock escalation |
| MySQL InnoDB | `FOR UPDATE SKIP LOCKED` + UPDATE in same TX | Next-key/gap locks, replication, isolation |
| Oracle | `FOR UPDATE SKIP LOCKED` + bounded fetch/procedure | Version-specific syntax/fetch/locking |
| H2 | Basic schema/SQL testing | Does not prove production concurrency behavior |

**There is no single `setSkipLocked(true)` flag on `JdbcPollingChannelAdapter`** that automatically translates to correct SQL for every vendor. Choose SQL strategy and transactions to match your real database.

## 18. Leases and Recovery: Locks Only Last Until COMMIT

Row locks protect **the claim phase inside a transaction**, but once COMMIT runs, locks are released. If a worker holds work for longer durations or processes asynchronously, you need a **lease**:

~~~text
t0  Worker A atomically claims job 101, lease_until = t0 + 90s
t1  COMMIT -> row locks released
t2  Worker A starts processing outside DB transaction
t3  Worker A crashes / loses connectivity
t4  Lease expires; worker B can reclaim job 101
t5  Worker B gets a new token; A (if still alive) cannot mark DONE
~~~

A query to detect expired leases:

~~~sql
SELECT id, event_id, claimed_by, claim_token, lease_until
FROM work_item
WHERE state = 'CLAIMED'
  AND lease_until < CURRENT_TIMESTAMP
ORDER BY lease_until, id;
~~~

**Simply SELECTing expired leases and running a separate UPDATE afterward** still races across multiple recovery workers. Reclaiming requires **atomic claims** or row locks under the same protocol.

### 18.1. Atomic Reclaim with a Fresh Token (PostgreSQL)

~~~sql
WITH expired AS (
    SELECT id
    FROM work_item
    WHERE state = 'CLAIMED'
      AND lease_until < CURRENT_TIMESTAMP
    ORDER BY lease_until, id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE work_item AS w
SET claimed_by = :newWorkerId,
    claim_token = :newToken,
    claimed_at = CURRENT_TIMESTAMP,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
    attempt_count = attempt_count + 1
FROM expired
WHERE w.id = expired.id
RETURNING w.id, w.event_id, w.claim_token;
~~~

Each reclaim rotates the token; any old token loses permission to update state. Because two recovery transactions can still compete, `FOR UPDATE SKIP LOCKED` and `UPDATE ... RETURNING` run in the same statement.

**Attempt policy:** once retry attempts are exhausted, transition to `FAILED`/DLQ with audit metadata instead of reclaiming endlessly. Losing ownership should be classified differently from transient network errors.

## 19. Fencing Tokens: Blocking Stale Workers from Wrongly Finalizing

Suppose worker A pauses in a stop-the-world GC or loses connectivity long enough for its lease to expire, and worker B reclaims the job with a new token. Worker A wakes up and tries to write `DONE`.

The completion DML must check both token and state:

~~~sql
UPDATE work_item
SET state='STAGED',
    staged_at=CURRENT_TIMESTAMP
WHERE id=:jobId
  AND state='CLAIMED'
  AND claim_token=:claimToken;
~~~

If affected rows = `0`, the worker **lost ownership** or the job already changed state. It must never overwrite with a bare `WHERE id=:jobId` UPDATE.

If you use a numeric `claim_version` instead of a UUID, every reclaim increments the version and every completion UPDATE compares the version. That helps when you need monotonically ordered tokens.

**Database fencing alone does not block remote side effects:** A can still send an HTTP request or Kafka message outside the database even after losing the right to mark `STAGED`. To protect remote services, remote endpoints need idempotency keys, fencing versions, or source/consumer coordination protocols. Never promise “having a lease guarantees zero duplicate effects”.

### 19.1. Extending a Lease

For long-running jobs, an active owner can send a heartbeat:

~~~sql
UPDATE work_item
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
WHERE id = :jobId
  AND state = 'CLAIMED'
  AND claim_token = :claimToken
  AND lease_until > CURRENT_TIMESTAMP;
~~~

If UPDATE affects 0 rows, the token expired or was reclaimed; the worker must stop or switch to reconciliation rather than assuming the renewal succeeded.

Measuring lease expiration against the **database clock** avoids clock-skew hazards across pods. Lease duration must exceed normal critical-section runtime, backed by heartbeats/recovery policies and stuck-job metrics.

## 20. Transaction Boundaries: DirectChannel vs. ExecutorChannel

~~~mermaid
flowchart LR
    A["Poller BEGIN"] --> B["Atomic claim SQL"]
    B --> C["DirectChannel / Splitter"]
    C --> D["Insert outbox + STAGED"]
    D --> E["COMMIT same DB"]
    B --> F["ExecutorChannel"]
    F --> G["Async worker"]
    G --> H["Different TX; does not roll back old claim"]
~~~

**When using `DirectChannel`:** synchronous handlers on the same poller thread can share the local JDBC transaction. Source claiming and outbox staging share the `DataSource`/transaction manager; if the writer throws and the exception propagates, both claim and outbox roll back.

**When using `ExecutorChannel` or `QueueChannel`:** the message hands off to another thread/poller; the poller transaction can COMMIT before worker execution finishes. Thus the source may record `CLAIMED` before the worker creates durable work. To stay safe, stage to an outbox/persistent queue **before** the async boundary, or implement leases/recovery and idempotency.

**Never keep a DB transaction open waiting on slow Kafka producer responses or long HTTP calls.** Long transactions hold connections/locks, degrade throughput, and increase deadlock risk. Split into a fast **claim + durable stage + COMMIT**, followed by separate publishing.

## 21. Crash Windows: Locks Prevent Contention, Not Delivery Failures

| Crash window | Row lock / DB state | How recovery works |
|---|---|---|
| Before claim transaction | `NEW` | Another worker claims normally |
| After locking SELECT, before UPDATE | Transaction rolls back, locks release | Retried/claimed by another worker |
| After UPDATE, before COMMIT | UPDATE rolls back | No job lost |
| After COMMIT `CLAIMED`, before staging | Locks released, job stays `CLAIMED` | Requires lease/reclaim |
| During outbox staging in same TX | Claim + outbox roll back on error | Polled again |
| After COMMIT `STAGED` + outbox | Outbox is durable | Publisher handles delivery |
| Broker received, before marking `published` | Outbox may still be pending | Re-publish; consumer is idempotent |
| Worker A stalls, B reclaims | A's token is invalidated | DB fencing plus remote idempotency |

**Never collapse `CLAIMED`, `STAGED`, `PUBLISHED`, and “consumer processed successfully” into one state.** Each milestone corresponds to a distinct commit/ACK event.

## 22. Idempotency and Outbox: Preventing Duplicate Business Effects

Locking and atomic claims only govern **exclusive job acquisition at a point in time**. Over a network, a request can succeed on the remote side and time out at the client. Retrying under uncertain outcomes can produce duplicate sends. Outboxes and idempotent receivers address that layer.

~~~mermaid
flowchart LR
    A["DB transactional claim"] --> B["Outbox record (stable eventId)"]
    B --> C["COMMIT"]
    C --> D["Kafka/JMS publisher"]
    D --> E["Consumer receives once or more"]
    E --> F["Dedupe eventId + business TX"]
    F --> G["Single business effect"]
~~~

| Component | Contract |
|---|---|
| `event_id` | Immutable across claim/retry/redelivery |
| `job_outbox.event_id UNIQUE` | Prevents staging multiple outbox rows for one event |
| `processed_event(event_id UNIQUE)` | Consumer writes marker inside the business transaction |
| Producer ACK | Broker received per producer contract; does not prove consumer processed |
| Consumer offset/JMS ACK | Records consumer progress; not automatically atomic with DB |
| Reconciliation | Compares pending/staged/published vs. target state on uncertain outcomes |

### 22.1. Database Idempotent Consumer Example

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(80) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

A consumer transaction typically does:
1. `INSERT INTO processed_event(event_id) VALUES (:eventId) ON CONFLICT DO NOTHING`.
2. If 0 rows inserted, the event already ran; treat as a valid duplicate and **skip the side effect**.
3. If 1 row inserted, execute the business UPDATE in **the same transaction**.
4. COMMIT, then ACK Kafka/JMS per container policy.

The marker must live in the same transaction as the business DML; marking processed beforehand in a separate transaction risks **dropping processing** on crash. With external HTTP side effects, a DB marker alone cannot ensure remote exactly-once; pair with remote idempotency keys and reconciliation.

## 23. Do Isolation Levels and MVCC Replace Locking?

Transaction isolation controls what data a transaction sees and how the DB coordinates concurrency. **MVCC/`READ COMMITTED` does not mean a worker claimed a row.** Two `READ COMMITTED` transactions can both SELECT a `NEW` row unless locks or atomic DML are used.

| Isolation | General semantics | Work-queue caveat |
|---|---|---|
| `READ_UNCOMMITTED` | Allows dirty reads or upgrades per DB vendor | Not a solution; dirty reads are dangerous |
| `READ_COMMITTED` | Typically sees committed rows only | Plain SELECT gives no ownership |
| `REPEATABLE_READ` | Snapshot/locking depends on DB | Can raise contention; still needs claim design |
| `SERIALIZABLE` | Strongest isolation against anomalies | Triggers serialization failures requiring full-TX retries |
| `DEFAULT` | Follows datasource/database default | Must verify actual runtime level |

For example, `@Transactional(isolation = Isolation.SERIALIZABLE)` does not mean:
- A and B cannot start selecting the same row concurrently on every DB;
- a Kafka message already sent rolls back with the DB;
- ID order equals COMMIT order;
- you can skip checking affected row counts.

**Explicit row locks or atomic claims remain a far clearer ownership contract** than hoping a general isolation level handles every race automatically.

### 23.1. How Far Do Locks Block and How Long Are They Held?

Operations can hold row locks from locking SELECT/UPDATE until COMMIT or ROLLBACK. When a transaction holds locks too long:
- Other workers skip or block on those rows.
- Pool connections stay tied up.
- Deadlocks and lock timeouts increase.
- Starvation can leave an older job continually skipped.

That is why we separate **short claim + durable stage transactions** from slow HTTP/Kafka calls.

## 24. NOWAIT, SKIP LOCKED, and Waiting on Locks: Choosing Behavior

| Mechanism | When row is locked | Best used when |
|---|---|---|
| Default wait | Waits for lock release or timeout | You must process that exact row and cannot skip |
| `NOWAIT` | Fails immediately if lock unavailable | Interactive/low-latency or controlled retries |
| `SKIP LOCKED` | Skips locked rows, picks others | Multi-worker queues with backlogs |
| Atomic conditional UPDATE | Claims only rows matching predicate at DML time | You need exact affected rows |
| Lock timeout | Caps lock wait duration | Protects threads/connections and alerts on contention |

On PostgreSQL:

~~~sql
-- Separate options; do not combine both at once.
SELECT id FROM work_item
WHERE state='NEW'
FOR UPDATE NOWAIT;

SELECT id FROM work_item
WHERE state='NEW'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` does not replace error lifecycle handling. If a row is held by a stalled transaction, other workers continually skip it. Monitor **oldest job age**, lock durations, attempt counts, and expired leases rather than looking only at aggregate throughput.

### 24.1. Retrying After Deadlock Requires a Fresh Transaction

If the database picks transaction A as a deadlock victim:
1. A must roll back its current transaction.
2. Release connections/locks properly.
3. Wait through backoff (with jitter) to avoid synchronized replica retry storms.
4. Open a fresh transaction and re-run the **atomic claim against current DB state**.
5. Emit messages only for rows claimed on the new attempt.

**Never retry only the UPDATE using an ID list SELECTed inside the failed transaction**, as ownership and snapshots may have changed. `SqlParameterSourceFactory` is not a retry or lock manager.

## 25. Optimistic Versioning: Prevents Lost Updates, Insufficient for Queues

An optimistic locking pattern:

~~~sql
UPDATE work_item
SET state='CLAIMED',
    attempt_count=attempt_count + 1
WHERE id=:id AND state='NEW' AND version=:expectedVersion;
~~~

The DDL in section 6 does not yet include `version`; this is an **extension requiring `ALTER TABLE`** for practice. When affected rows = 1, the worker updated the row at the expected version. When 0, it did not win the claim and must not emit events from the stale SELECT snapshot.

Key differences:
- **Optimistic versioning** fits rare conflicts where retries and 0-row outcomes are straightforward.
- **Pessimistic `FOR UPDATE SKIP LOCKED`** fits many consumers pulling concurrently from a queue.
- **Atomic `RETURNING`/`OUTPUT` claims** give explicit results strictly for rows whose state changed.
- **Idempotency** is still required whenever Kafka/JMS/HTTP redeliver.

Never hold a long transaction open locking a business record for the entire duration of a remote service call. Use optimistic versioning/idempotency at completion instead.

## 26. Performance, Batch Size, Indexes, and Fairness

Common queue-optimization mistakes:
- `SELECT *` fetching huge payloads when only IDs are needed to claim.
- `WHERE state='NEW'` without a matching index.
- `ORDER BY priority DESC, created_at` while only `id` is indexed, forcing large DB sorts.
- Batches of thousands of IDs producing massive `IN (:ids)` lists and long locks.
- Running more pollers than Hikari pool or CPU/IO capacity can sustain.
- Holding transactions open during HTTP/Kafka calls, causing connection waits and lock timeouts.
- Using OFFSET pagination on mutating queues, skipping or locking unnecessary rows.
- Assuming “bigger batches are always faster” without measuring commit/outbox latency.

### 26.1. Approximate Capacity Sanity Check

If one poller claims and stages an average of 20 rows in 100 ms (measured), each poller can handle roughly up to 200 rows/second **with no other bottlenecks**. Real throughput is lower due to network latency, DB locks, disk flushes, scheduler delays, and publish lag. Treat this as capacity reasoning, not a framework benchmark.

To avoid long transactions, measure:
- p50/p95/p99 of `claim transaction duration`;
- rows/claim, rows staged/second, pending outbox count;
- lock wait/deadlock counts;
- active/pending Hikari connections;
- `NEW` row count and oldest `NEW` row age.

### 26.2. Starvation and Priority

With `SKIP LOCKED`, a row locked by another transaction can be skipped across many polls. With `ORDER BY priority DESC` always picking high-priority rows, low-priority items can starve indefinitely under heavy load.

Mitigations:
- Monitor item age and alert on items waiting too long.
- Separate queues/partitions by SLA, or apply aging/fairness policies.
- Bound transaction durations and retries.
- Run a periodic worker for lease-expired/`FAILED` items rather than only selecting `NEW`.
- Evaluate starvation under multiple concurrent pollers and differing indexes/orderings.

**`ORDER BY` in SELECT** does not promise Kafka/JMS receives messages in that order across multiple workers, splitters, executor threads, and broker partitions. If per-aggregate ordering is mandatory, use partition ownership and sequence/event versions.

## 27. Metrics, Logging, and Operational Alerts

| Metric | Meaning |
|---|---|
| `rows_selected_per_poll` | Input rows from SELECT |
| `rows_actually_claimed` | Rows actually modified by UPDATE/RETURNING |
| `claim_conflicts` | 0-row UPDATEs / CAS failures / lost ownership |
| `claim_transaction_duration` | Transaction hold duration, affecting lock contention |
| `db_lock_waits` and deadlocks | Concurrency and index health indicators |
| `new_backlog`, `oldest_new_age` | Queue buildup and starvation |
| `claimed_lease_expired` | Dead, stalled, or slow workers |
| `outbox_pending`, `oldest_unpublished_age` | Slow broker or publisher |
| `duplicate_event_seen` | Redelivery/idempotency activity |
| Hikari active/idle/pending | Pool pressure |
| `dlq_failed_jobs` | Work that cannot auto-retry |

**Early alarm:** if SELECT returns 20 rows while UPDATE modifies only 0–5 and the app still emits 20 messages, you have a severe ownership bug. Atomic `RETURNING` designs emit only actually claimed rows; alert on count mismatches if using two separate SQL statements.

Logs should include `workerId`, `pollId`, `eventId`, `claimToken` (scrubbed if sensitive), counts, and DB transaction outcomes. Never use `eventId` as an unbounded-cardinality metric tag; keep it in logs/traces. Avoid logging `payload_json` or customer PII.

## 28. Testing Two Workers Competing on the Same Table

**Never use H2 as proof of PostgreSQL `FOR UPDATE SKIP LOCKED` or SQL Server `READPAST`.** Concurrency tests need two independent database connections/transactions and a production-compatible DB. Testcontainers fits well here.

### 28.1. Two-Transaction Scenario

~~~mermaid
sequenceDiagram
    participant A as Worker A / Transaction A
    participant DB as PostgreSQL
    participant B as Worker B / Transaction B
    A->>DB: BEGIN + claim 20 rows via UPDATE RETURNING
    Note over DB: A holds locks until COMMIT
    B->>DB: BEGIN + claim 20 rows via UPDATE RETURNING
    DB-->>B: 20 different rows via SKIP LOCKED
    A->>DB: COMMIT
    B->>DB: COMMIT
    Note over A,B: Intersect(claimedIdsA, claimedIdsB) = empty
~~~

If only 20 rows exist, B receives 0 rows while A holds all locks. **Zero overlap** is still valid; receiving 0 is not an error.

### 28.2. JUnit Concurrency Test Template

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class AtomicClaimConcurrencyTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void twoWorkersNeverClaimSameIdInOneRace() throws Exception {
        // Setup in test PostgreSQL DB: at least 40 NEW rows;
        // no background poller running alongside the test.
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Set<Long>> claim = () -> {
            var source = new AtomicClaimMessageSource(
                new NamedParameterJdbcTemplate(dataSource),
                "test-" + UUID.randomUUID());
            source.afterPropertiesSet();
            start.await();

            return new TransactionTemplate(manager).execute(status -> {
                Message<?> message = source.receive();
                if (message == null) {
                    return Set.<Long>of();
                }
                List<?> payload = (List<?>) message.getPayload();
                Set<Long> ids = new HashSet<>();
                for (Object item : payload) {
                    ids.add(((ClaimedJob) item).id());
                }
                return ids;
            });
        };

        try {
            Future<Set<Long>> left = executor.submit(claim);
            Future<Set<Long>> right = executor.submit(claim);
            start.countDown();

            Set<Long> a = left.get(10, TimeUnit.SECONDS);
            Set<Long> b = right.get(10, TimeUnit.SECONDS);
            assertTrue(java.util.Collections.disjoint(a, b));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

**This is a template** requiring Testcontainers PostgreSQL, isolated test data, and a transaction manager bound to that `DataSource`. The test only proves **disjoint claimed IDs during this race**, not crash recovery or Kafka idempotency. Repeat tests across varied interleavings, worker counts, lock contention, and fault injections. Never run background `IntegrationFlow` pollers against the same test table.

### 28.3. Why Query the Database Directly?

Receiving a `Message<?>` does not prove the transaction committed. After tests, query `work_item` to verify `CLAIMED` counts, distinct tokens, `attempt_count`, and remaining `NEW` rows. For outbox tests, also inspect `job_outbox` after writer success and rollback.

## 29. Transaction and Crash-Recovery Test Matrix

| Test case | Expectation |
|---|---|
| Two workers run plain SELECT on same row | Race reproduced in non-locking setup |
| One worker holds `FOR UPDATE` lock | Second worker with `SKIP LOCKED` skips locked rows |
| A rolls back after lock/UPDATE | Rows revert to `NEW`; B can claim next time |
| A commits claim, worker dies | Job stays `CLAIMED`; lease expiry/reclaim recovers it |
| A stalls, B reclaims | A's old token fails to finalize |
| A stages outbox row 1, fails row 2 | Both claim and outbox roll back in the DB transaction |
| Publisher sends to Kafka, crashes before `published` | Event re-sent; consumer handles idempotently |
| Duplicate event ID with different payload | Conflict detected, not silently dropped |
| `UPDATE count = 0` | Does not emit events claiming row ownership |
| Hikari pool too small | Reports acquire waits; concurrency stays bounded |
| Deadlock occurs | Transaction rolls back; full claim retried with backoff |
| SQL Server RCSI ON | Hints/isolation verified against Microsoft docs |
| MySQL InnoDB REPEATABLE READ | Lock/next-key scope measured on real DB |
| Row locked long enough for starvation | Metrics detect rising oldest pending age |
| Lease clock skew | Comparisons use DB clock rather than worker clocks |
| High-priority jobs | Ordering/fairness explicit; broker order not assumed |

Tests must inspect DB state **after COMMIT**, rather than just asserting `send()==true` or callback counts. For Kafka/JMS, test broker ACK/redelivery under real container and producer settings.

## 30. Production Checklist for JDBC Work Queues

1. Selected **a specific DB vendor and version** and verified SQL locking syntax.
2. Transaction manager uses **the same `DataSource`**, and the poller opens a transaction before SELECT/claim.
3. Autocommit is disabled across locking SELECT + UPDATE pairs needing atomicity.
4. In multi-instance deployments, use `SKIP LOCKED` or atomic claims; never rely on `WHERE state='NEW'` alone.
5. Custom source payloads carry **only rows actually claimed**, never stale SELECT lists after 0-row UPDATEs.
6. Unique `event_id` plus claim tokens/versions/worker ownership when required.
7. Lease/recovery mechanism handles `CLAIMED` jobs stranded by crashes.
8. Outbox staging or business DML runs **in the same transaction** as claiming when atomicity is needed.
9. No slow remote Kafka/HTTP calls while holding DB locks.
10. Idempotent consumers or remote idempotency keys in place.
11. Deadlocks/serialization failures retry in a **fresh** transaction with bounded backoff/jitter.
12. System tracks rows selected/claimed, lock waits, oldest item age, and pending outbox count.
13. Two-transaction concurrency tests and crash-window fault injection tests exist.
14. Policies defined for duplicates, conflicts, poison messages, DLQ, and manual replay.
15. Bounded concurrency, SQL indexes, batch sizes, and pool capacity measured in practice.

## 31. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “`SELECT WHERE state='NEW'` gives exclusive access” | Two pods can still SELECT the same rows |
| “UPDATE throwing no error means claim succeeded” | UPDATE count can be 0 |
| “`maxMessagesPerPoll(1)` prevents multi-pod duplicates” | Only limits `receive()` calls inside one poller |
| “`SKIP LOCKED` works with per-statement autocommit” | Locking SELECT must share a transaction with UPDATE |
| “`SKIP LOCKED` gives exact reporting results” | It gives an inconsistent view designed for queues |
| “`ORDER BY` guarantees global message ordering” | Concurrent workers and broker partitions break global order |
| “Passing H2 tests proves PostgreSQL/MySQL behave identically” | Locking behavior is vendor-specific |
| “`READPAST` skips all page and table locks” | SQL Server primarily skips row locks |
| “`ROWLOCK` always forces SQL Server to use row locks only” | Hints do not override query plans/lock escalation |
| “`SERIALIZABLE` guarantees exactly-once Kafka” | Isolation applies only inside the database |
| “Row locks survive DB COMMIT” | Locks release when the transaction ends |
| “Lease expiration proves the old worker is dead” | The old worker may simply be paused or slow |
| “Claim tokens automatically block stale HTTP side effects” | Remote services need idempotency/fencing support |
| “Event IDs should change on every retry” | Event IDs must stay stable for deduplication |
| “Transactional outbox makes brokers receive only once” | Publishers can still redeliver |
| “`ExecutorChannel` inherits the poller's JDBC transaction” | Thread-bound transactions do not propagate automatically |
| “`READ UNCOMMITTED` safely avoids lock contention” | Dirty reads are not ownership |
| “Retrying only the UPDATE after a deadlock suffices” | Must re-run the entire transactional unit |
| “`UPDATE RETURNING` is portable SQL” | Vendor-specific; SQL Server uses `OUTPUT` differently |
| “Locking makes JDBC non-blocking” | JDBC remains blocking I/O |

## 32. Practice Exercises

1. Create `work_item` with IDs 101–104; run two plain SELECT transactions to reproduce row 101 being picked twice.
2. Add `UPDATE ... WHERE state='NEW'` and observe one worker getting 0 updated rows while still holding the row in its Java list.
3. Switch to PostgreSQL `FOR UPDATE SKIP LOCKED` inside a transaction and verify B never receives IDs locked by A.
4. Remove the transaction or enable autocommit to see how SELECT locks no longer protect the subsequent UPDATE.
5. Use Spring Integration 7.x `Jdbc.inboundAdapter` with a locking SELECT and transactional poller.
6. Implement the equivalent in 6.x with `JdbcPollingChannelAdapter` and in XML.
7. Compare `maxRows(20)`, `maxMessagesPerPoll(1)`, and post-splitter message counts.
8. Build an atomic CTE `UPDATE ... RETURNING`; assert returned IDs match the exact rows transitioned to `CLAIMED`.
9. Implement custom `AtomicClaimMessageSource` + `NamedParameterJdbcTemplate` on PostgreSQL.
10. Create the `ClaimedJob` record carrying a stable event ID and a per-claim token.
11. Add `JobOutboxStager`, a transactional poller, and a splitter; fail on the second row and verify both claim and outbox roll back.
12. Insert an `ExecutorChannel` between claim and staging; specify the recovery mechanism needed to avoid losing work.
13. Write a recovery query for expired `CLAIMED` leases and implement atomic reclaim with `RETURNING`.
14. Extend a lease using `WHERE claim_token=:token`; pass a wrong token and verify 0 rows updated.
15. Simulate A pausing, B reclaiming, and A waking up; verify A cannot write `STAGED` with the stale token.
16. Create a `processed_event` unique constraint, send duplicate Kafka/JMS messages, and verify the business effect runs once.
17. On SQL Server, test `UPDLOCK, READPAST`, `READ_COMMITTED_SNAPSHOT`, and page locks.
18. On MySQL InnoDB, test `FOR UPDATE SKIP LOCKED` and next-key/gap locks across different indexes.
19. Compare `NOWAIT` vs. `SKIP LOCKED`, measuring latency and claimed throughput.
20. Trigger a deadlock in a test DB and retry the entire transaction with backoff/jitter.
21. Test batch sizes 5, 20, and 100; measure p95 transaction duration, lock waits, pool utilization, and outbox lag.
22. Deliberately hold a row lock for a long time, measure starvation/oldest pending age, and design an alert.
23. Write a JUnit test with two barrier-synchronized threads and Testcontainers PostgreSQL verifying disjoint claimed IDs.
24. Simulate a crash after broker ACK before `published=true`; verify stable event IDs and consumer idempotency.
25. Compare single-leader, partition ownership, row locking, outbox, and CDC for multi-producer/multi-consumer workloads.
26. Write a runbook for stuck `CLAIMED` rows, lease expiry, DLQ, manual replay, and schema rollouts across live pods.

**Comprehensive scenario:** a system has three pods polling 100,000 `NEW` jobs. Pod A claims 20 jobs and hangs before committing; Pod B picks the next jobs using `SKIP LOCKED`; Pod C claims 20 jobs and dies after the database commits `CLAIMED` but before writing the outbox. One minute later, Pod A wakes up and attempts to finalize jobs whose leases have expired. Define the **transaction boundaries, database locks, atomic claim outputs, claim tokens, leases/heartbeats, outbox staging, retries, and consumer idempotency** needed to handle each failure window without losing jobs or duplicating side effects uncontrollably.

## 33. References

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT/UPDATE, list payloads, RowMapper, `:id`, transactional pollers.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter(...)` from Spring Integration 7.0.
- [Spring Integration API — JdbcPollingChannelAdapter 6.x](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): `setUpdateSql`, `setRowMapper`, `setMaxRows`, parameter factories.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, DirectChannel, and async boundaries.
- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): lock registries when leader/critical-section locking differs from row locking.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `NamedParameterJdbcTemplate`, and row mapping.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `PlatformTransactionManager`, transaction scope, rollback/isolation.
- [PostgreSQL Documentation — SELECT (locking clauses)](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `NOWAIT`, `SKIP LOCKED`, and limitations.
- [PostgreSQL Documentation — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM` and `RETURNING`.
- [Microsoft Learn — SQL Server Table Hints](https://learn.microsoft.com/en-us/sql/t-sql/queries/hints-transact-sql-table): `READPAST`, `UPDLOCK`, `ROWLOCK`, `READCOMMITTEDLOCK`, RCSI.
- [Microsoft Learn — SQL Server OUTPUT Clause](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql): `OUTPUT inserted` for actually modified rows.
- [MySQL 8.4 Reference — InnoDB Locking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html): `FOR UPDATE SKIP LOCKED`, NOWAIT, and replication limits.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): version-specific `FOR UPDATE` and `SKIP LOCKED`.
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): when persistent messages/queues are needed instead of in-memory channels.

> **Remember:** **SELECTing a row does not mean owning that row**. For multiple JDBC pollers to avoid duplicate claims, use transactional row-level locking (such as `FOR UPDATE SKIP LOCKED`) or atomic claims returning **only the rows actually updated**. Locks protect only while the transaction remains open; after COMMIT, you need leases/recovery for unfinished work. When sending to Kafka/JMS/HTTP, combine **stable event IDs, transactional outboxes, and idempotent consumers**: preventing duplicate *claims* and preventing duplicate *business effects* are related but distinct goals.

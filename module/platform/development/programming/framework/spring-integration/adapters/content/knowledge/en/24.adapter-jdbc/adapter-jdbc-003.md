# JDBC Inbound Stored Procedure Adapter in Spring Integration

## 1. Context: Fetching Data from a Database via Stored Procedure

In many systems, applications are not allowed to query arbitrary tables directly with `SELECT`. An ERP system might only expose a stored procedure `POLL_NEW_ORDERS` to return new orders requiring processing; an accounting system might use a procedure to read a batch of unsynchronized journal entries. Spring Integration needs to **actively invoke the procedure periodically** and send the results onto a `MessageChannel` for downstream processing by a transformer, splitter, service activator, or outbound adapter.

The **JDBC inbound stored procedure adapter** is a **polled message source**: on each poll, it calls a stored procedure or stored function via JDBC, reads the returned values, and creates a Spring Integration message. The implementation class is `StoredProcPollingChannelAdapter`, using `StoredProcExecutor` built on Spring JDBC's `SimpleJdbcCall`.

This article belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module covers connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, with a focus on message contracts, errors, and connection lifecycles. Here, the starting point is the **database**, not an HTTP client or Kafka listener.

~~~mermaid
flowchart LR
    A["TaskScheduler / Poller"] --> B["StoredProcPollingChannelAdapter"]
    B --> C["StoredProcExecutor / SimpleJdbcCall"]
    C -->|"EXEC stored procedure"| D[("Relational database")]
    D -->|"ResultSet / OUT parameters"| C
    C --> B
    B -->|"Message<Map> or Message<List>"| E["MessageChannel"]
    E --> F["Filter / Splitter / Transformer"]
    F --> G["JMS / Kafka / HTTP / Service"]
~~~

The running example uses SQL Server. The `POLL_NEW_ORDERS` procedure accepts `maxRows`, identifies a set of orders in `NEW` status, transitions them to `CLAIMED`, and returns a result set. This is an **example with database side effects**; you must understand transactions and recovering claimed-but-unprocessed rows before applying this in production.

## 2. Distinguishing Stored Procedure Inbound from Other JDBC Endpoints

| Endpoint | Who initiates? | Data contract | When to use |
|---|---|---|---|
| JDBC inbound channel adapter | **Poller** running `SELECT` | Database rows → message | Direct queries are permitted and simple enough |
| **Stored procedure inbound channel adapter** | **Poller** calling `CALL/EXEC` | ResultSet/OUT → message | Must call a procedure/function; read logic lives in the DB |
| Stored procedure outbound channel adapter | **Message arriving on input channel** | Message → procedure side effect, no business reply | Write via procedure after receiving an event |
| Stored procedure outbound gateway | **Message arriving on request channel** | Message → procedure → reply message | Need dynamic parameters from a message and receive results |
| JDBC outbound adapter | **Message arriving on input channel** | Message → DML `INSERT/UPDATE/DELETE` | One-way SQL writes |

Common misconceptions:

- The inbound stored procedure adapter **does not wait** for an incoming message before calling the procedure: it is triggered on a schedule by a poller.
- `maxMessagesPerPoll` limits **how many times the message source is polled per cycle**, not the number of rows retrieved from the database.
- A procedure returning multiple rows **does not mean** the adapter emits one message per row. A result set may be mapped to a `List<Row>` inside a single message; to get separate messages you need a splitter.
- JDBC is **blocking I/O**. The poller uses scheduler/worker threads; do not assume it uses R2DBC or Reactive Streams just because the output channel might connect to a WebFlux application.

## 3. Under the Hood: Poller, Executor, SimpleJdbcCall, and Result Map

A typical poll execution:

1. `SourcePollingChannelAdapter` invokes `MessageSource.receive()` on schedule.
2. `StoredProcPollingChannelAdapter` calls `StoredProcExecutor.executeStoredProcedure()`.
3. `StoredProcExecutor` uses Spring JDBC `SimpleJdbcCall` to invoke the procedure/function via `DataSource`.
4. `OUT` parameters, result sets, and applicable return values are placed into a `Map<String, Object>`.
5. The adapter determines the payload according to `expectSingleResult`, builds a message, and sends it to the output channel.
6. Downstream processes the payload; the poller transaction (if configured) commits or rolls back per its configured boundaries.

~~~mermaid
sequenceDiagram
    participant Timer as Poller
    participant Source as StoredProcPollingChannelAdapter
    participant Exec as StoredProcExecutor
    participant DB as Database
    participant Next as Downstream
    Timer->>Source: receive()
    Source->>Exec: executeStoredProcedure()
    Exec->>DB: CALL/EXEC procedure
    DB-->>Exec: ResultSet + OUT parameters
    Exec-->>Source: Map<String,Object>
    Source-->>Next: Message<List<Row>> or Message<Map>
    Note over Timer,Next: When poller transaction is configured, sync downstream can share TX
~~~

**Do not infer from the name `stored procedure` that the call automatically has an atomic transaction across all systems.** A procedure can run DML, commit, or roll back depending on the database and SQL code. A poller transaction only covers resources actually participating in that transaction; JMS/Kafka/HTTP do not automatically commit alongside a JDBC transaction.

## 4. Creating a Sample Procedure on SQL Server

### 4.1. Source Schema

The example uses SQL Server to receive a JDBC `ResultSet` directly. The DDL is SQL Server-specific and will not run verbatim on PostgreSQL, MySQL, Oracle, or H2.

~~~sql
CREATE TABLE dbo.integration_order (
    order_id    BIGINT NOT NULL PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    created_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    claimed_at  DATETIME2 NULL
);
GO

INSERT INTO dbo.integration_order (order_id, status)
VALUES (1001, 'NEW'), (1002, 'NEW'), (1003, 'NEW');
GO
~~~

### 4.2. “Claim and Return Results” Stored Procedure

~~~sql
CREATE OR ALTER PROCEDURE dbo.POLL_NEW_ORDERS
    @maxRows INT
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH candidates AS (
        SELECT TOP (@maxRows)
            order_id, status, created_at, claimed_at
        FROM dbo.integration_order
            WITH (UPDLOCK, READPAST, ROWLOCK)
        WHERE status = 'NEW'
        ORDER BY created_at, order_id
    )
    UPDATE candidates
       SET status = 'CLAIMED',
           claimed_at = SYSUTCDATETIME()
    OUTPUT
       inserted.order_id,
       inserted.status,
       inserted.created_at;
END;
GO
~~~

Analysis:

- `@maxRows` is an input parameter to limit **row count at the database** before sending data to the application.
- `TOP (@maxRows)` is SQL Server syntax; other RDBMSs require their own limiting constructs.
- `UPDLOCK`/`READPAST`/`ROWLOCK` aim to reduce contention among multiple consumers over the same rows, though actual behavior also depends on **isolation level, indexes, and database settings**. Under `READ_COMMITTED_SNAPSHOT`, verify SQL Server's specific locking requirements.
- `UPDATE ... OUTPUT inserted...` both claims and returns a result set of the claimed rows. It is a **DML operation**, not a read-only query.
- `SET NOCOUNT ON` suppresses extra update counts that could clutter the JDBC result structure.

After a poll picking two rows, sample output:

| order_id | status | created_at |
|---:|---|---|
| 1001 | CLAIMED | DB timestamp value |
| 1002 | CLAIMED | DB timestamp value |

**Production issue to address:** if the database commits the claim successfully and the application crashes before forwarding the message, those two rows can remain stuck in `CLAIMED`. You need a **lease/timeout, requeue, recovery worker, or transactional outbox** strategy. Do not treat the sample procedure above as “end-to-end exactly-once”.

## 5. Dependencies, Versions, and Runtime Environment

Spring Integration JDBC uses a `DataSource` and JDBC driver. With Spring Boot, let the BOM manage compatible versions:

~~~groovy
// build.gradle: sample dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    // Driver suitable for SQL Server; Boot BOM manages the version if present.
    runtimeOnly 'com.microsoft.sqlserver:mssql-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml - environment with SQL Server and properly configured TLS
spring:
  datasource:
    url: "jdbc:sqlserver://db.example.internal:1433;databaseName=integration;encrypt=true"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

Host and database names are examples only. Never hardcode passwords in the repository; use environment variables/secret managers. SQL Server must be configured with valid certificates, hostnames, and trust chains; do not disable TLS verification to hide connection errors.

**Spring Integration version distinctions:**

- Starting in **7.0**, the JDBC module provides the Java DSL factory `Jdbc.storedProcInboundAdapter(dataSource)` along with `JdbcStoredProcInboundChannelAdapterSpec`.
- In **6.x**, `StoredProcPollingChannelAdapter`/`StoredProcExecutor` and the XML namespace are still available. Do not assume the 7.x Java DSL factory exists in 6.x.
- JDBC types such as `SqlParameter` belong to Spring Framework; types such as `ProcedureParameter` reside in `org.springframework.integration.jdbc.storedproc`. Choose APIs and imports matching your actual version.

**H2 and stored procedures:** H2 does not implement all `CallableStatement`/result-set semantics identically to every production RDBMS; critical tests should run against real SQL Server or Testcontainers, not just H2.

## 6. Java DSL 7.x: Polling a Stored Procedure and Emitting Each Row

Java DSL 7.x provides a builder to configure the executor, result set mapping, and poller in a single flow. Below is a configuration matching the procedure in section 4.

~~~java
package com.example.integration;

import java.sql.Types;
import java.time.Duration;
import java.time.LocalDateTime;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class StoredProcedureInboundFlow {

    public record OrderRow(
        long orderId, String status, LocalDateTime createdAt) { }

    @Bean
    public IntegrationFlow ordersFromProcedure(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(
                Jdbc.storedProcInboundAdapter(dataSource)
                    .expectSingleResult(true)
                    .configurerStoredProcExecutor(c -> c
                        .storedProcedureName("POLL_NEW_ORDERS")
                        .isFunction(false)
                        .ignoreColumnMetaData(true)
                        .sqlParameter(new SqlParameter(
                            "maxRows", Types.INTEGER))
                        .procedureParameter(new ProcedureParameter(
                            "maxRows", 25, null))
                        .returningResultSetRowMapper(
                            "orders",
                            (rs, rowNum) -> new OrderRow(
                                rs.getLong("order_id"),
                                rs.getString("status"),
                                rs.getTimestamp("created_at")
                                    .toLocalDateTime()))),
                e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)
                    .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows && !rows.isEmpty())
            .split()
            .channel("claimedOrders")
            .get();
    }

    @ServiceActivator(inputChannel = "claimedOrders")
    public void processRow(OrderRow row) {
        System.out.printf("Claimed order %d: %s%n",
            row.orderId(), row.status());
    }
}
~~~

**Component-by-component breakdown:**

1. `Jdbc.storedProcInboundAdapter(dataSource)` creates an **inbound procedure** `MessageSource`, not an outbound gateway.
2. `configurerStoredProcExecutor(...)` sets the procedure name, metadata/parameter declarations, and row mapper.
3. `ignoreColumnMetaData(true)` disables automatic parameter metadata lookup; the example explicitly declares input `maxRows` with `SqlParameter`.
4. `ProcedureParameter("maxRows", 25, null)` provides the **static value 25** at poll time. An inbound adapter has no external request message from which to read `payload.maxRows`.
5. `returningResultSetRowMapper("orders", ...)` maps each row of the JDBC ResultSet to `OrderRow` and places the list in the output map under key `orders`.
6. `expectSingleResult(true)` extracts **the single entry from the result map**. In this example, that is **`List<OrderRow>`**, not a single `OrderRow`.
7. `maxMessagesPerPoll(1)` asks the message source at most once per poll cycle. **It does not replace `maxRows=25`** inside the procedure.
8. `transactional(transactionManager)` lets the poller run in a transaction when an appropriate manager is configured. You must evaluate transaction boundaries across the whole flow; do not assume it spans systems outside the DB.
9. `filter` drops empty lists, and `split()` turns each row in the `List` into an individual message on `claimedOrders`.
10. `@ServiceActivator` illustrates a synchronous consumer; in real applications, do not treat `System.out.println` as durable processing confirmation.

**Important warning:** SQL Server in the example creates the procedure in schema `dbo`. The JDBC account must have a default schema/ability to resolve `POLL_NEW_ORDERS` properly; otherwise, configure the schema on `SimpleJdbcCall` per the supported API or create the procedure in the resolved schema. Never construct schema/procedure names from untrusted input.

### 6.1. How Many Messages Does One Poll Produce?

Suppose `maxRows=25` and the procedure fetches 3 rows:

~~~text
Poller (1 receive call)
  -> StoredProcExecutor
  -> resultMap = {"orders": List<OrderRow>(3)}
  -> expectSingleResult(true)
  -> Message<List<OrderRow>>(3)
  -> filter (non-empty list)
  -> splitter
  -> 3 x Message<OrderRow>
~~~

If you remove `split()`, downstream receives **one message containing a list**. If you change to `expectSingleResult(false)`, downstream can receive a **map** instead of a list, so any splitter/transformer must match that data type.

## 7. expectSingleResult: One Map Result Is Not One Row

After executing the procedure/function, `StoredProcExecutor` returns a `Map<String, Object>`. The map may contain multiple OUT params, a return value, and result sets. `StoredProcPollingChannelAdapter.setExpectSingleResult(true)` operates on the **number of entries in the result map**:

| Executor output | `expectSingleResult=false` | `expectSingleResult=true` |
|---|---|---|
| `{"orders": List<OrderRow>}` | Payload is the map | Payload is `List<OrderRow>` |
| `{"count": 7}` | Payload is the map | Payload is `Integer`/OUT value |
| `{"orders": List, "total": 7}` | Payload is the map | **Error** due to multiple result entries |
| Empty result/no suitable payload | Depends on result map/DB/framework | Do not assume a message with null payload is emitted |

Therefore, **`expectSingleResult(true)` is not a single-row mode**. To turn each row into a message, use a splitter, and if you genuinely need only one row, limit the row count in the procedure/SQL or inspect the mapped result.

Spring Integration documentation also notes that some databases (especially certain H2 function scenarios) return `CallableStatement` outputs differently; the same configuration may still yield a collection rather than a scalar. Always **verify the actual payload type** in an integration test against your target database.

## 8. XML Configuration for Spring Integration 6.x Systems

Spring Integration JDBC has long supported stored procedure inbound adapters via the XML namespace. The following configuration is conceptually equivalent to the Java DSL: a poller calls the procedure, maps the result set, and sends to a channel.

~~~xml
<!-- Fragment: requires int and int-jdbc namespaces in the Spring XML context. -->
<int:channel id="orderBatchChannel"/>

<int-jdbc:stored-proc-inbound-channel-adapter
    id="storedProcOrderPoller"
    channel="orderBatchChannel"
    data-source="dataSource"
    stored-procedure-name="POLL_NEW_ORDERS"
    ignore-column-meta-data="true"
    skip-undeclared-results="true">

    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>

    <int-jdbc:sql-parameter-definition
        name="maxRows" direction="IN" type="INTEGER"/>
    <int-jdbc:parameter
        name="maxRows" type="java.lang.Integer" value="25"/>
    <int-jdbc:returning-resultset
        name="orders" row-mapper="orderRowMapper"/>
</int-jdbc:stored-proc-inbound-channel-adapter>
~~~

This example requires `dataSource`, `transactionManager`, and `orderRowMapper` beans along with Spring Integration XML namespace/schema configuration. `orderBatchChannel` receives messages containing the default **result map**; if downstream should receive `List<OrderRow>` like the section 6 Java DSL, configure `expect-single-result="true"` if supported by your XML schema version and verify the result, or use a transformer to extract `payload['orders']` before splitting.

**Do not copy both the XML snippet and Java DSL into the same application and accidentally run two pollers** against one source, unless intentional concurrency is part of your design. The 7.x configuration in section 6 and the XML here are two alternative implementations.

## 9. Direct Java Configuration for Spring Integration 6.x

When not using XML and the project is still on Spring Integration 6.x, you can instantiate `StoredProcExecutor` together with `StoredProcPollingChannelAdapter` using the API that existed prior to Java DSL 7.x:

~~~java
package com.example.integration;

import java.sql.Types;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.StoredProcExecutor;
import org.springframework.integration.jdbc.StoredProcPollingChannelAdapter;
import org.springframework.integration.jdbc.storedproc.ProcedureParameter;
import org.springframework.jdbc.core.SqlParameter;

@Configuration
public class StoredProcLegacyConfiguration {

    @Bean
    public StoredProcExecutor orderProcedureExecutor(DataSource dataSource) {
        StoredProcExecutor executor = new StoredProcExecutor(dataSource);
        executor.setStoredProcedureName("POLL_NEW_ORDERS");
        executor.setIgnoreColumnMetaData(true);
        executor.setSqlParameters(List.of(
            new SqlParameter("maxRows", Types.INTEGER)));
        executor.setProcedureParameters(List.of(
            new ProcedureParameter("maxRows", 25, null)));
        executor.setReturningResultSetRowMappers(Map.of(
            "orders",
            (rs, rowNum) -> new StoredProcedureInboundFlow.OrderRow(
                rs.getLong("order_id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime())));
        return executor;
    }

    @Bean
    public StoredProcPollingChannelAdapter orderProcedureSource(
            StoredProcExecutor orderProcedureExecutor) {
        StoredProcPollingChannelAdapter source =
            new StoredProcPollingChannelAdapter(orderProcedureExecutor);
        source.setExpectSingleResult(true);
        return source;
    }

    @Bean
    public IntegrationFlow orderProcedureFlow(
            StoredProcPollingChannelAdapter orderProcedureSource) {
        return IntegrationFlow.from(orderProcedureSource,
                e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows && !rows.isEmpty())
            .split()
            .channel("legacyClaimedOrders")
            .get();
    }
}
~~~

**Version/structure note:** this snippet demonstrates the `org.springframework.integration.jdbc.StoredProcExecutor` and `StoredProcPollingChannelAdapter` APIs in 6.x; the `OrderRow` DTO type is borrowed from the 7.x example to avoid repeating the definition, but in a standalone 6.x app declare your own DTO record with the same structure. Transactional pollers were covered in sections 6 and 8; this example intentionally shows only how to build the source, so add a transaction manager if the procedure performs claiming DML.

In 6.x, the framework manages the bean lifecycle of `StoredProcExecutor` automatically when it is a Spring bean; there is no need to call `afterPropertiesSet()` manually in this configuration. Do not mix the 7.x `Jdbc.storedProcInboundAdapter(...)` factory API into a 6.x project.

## 10. Stored Procedure Parameters: IN, OUT, INOUT, and Return Values

`SimpleJdbcCall` can discover parameter metadata from JDBC if the database supports it. When metadata is unreliable or specific types are needed, declare them manually:

| Kind | Role | How to configure |
|---|---|---|
| `IN` | Value passed into the procedure | `SqlParameter` + static/SpEL `ProcedureParameter` |
| `OUT` | Value returned out by the procedure | `SqlOutParameter` or XML `sql-parameter-definition direction="OUT"` |
| `INOUT` | Both input and output | `SqlInOutParameter` or XML `direction="INOUT"` |
| ResultSet | List of rows | `returning-resultset` / `returningResultSetRowMapper(...)` |
| SQL function return | Function return value | `is-function="true"` with matching type/return declaration |

**Crucial point for inbound:** the adapter does not receive an external request message from which to read dynamic `payload`/`headers` parameters. The `maxRows` parameter in the example is a **static value**. Spring Integration documentation states that `sql-parameter-source-factory` and `use-payload-as-parameter-source` **do not apply** to the stored procedure inbound channel adapter.

If the procedure needs **per-message values**, you should usually choose the **stored procedure outbound gateway** to send a `Message<?>` onto a request channel, or implement another active data source with explicitly controlled parameter supply. Do not write SpEL `payload.xxx` on an inbound poller expecting a source payload to exist.

### 10.1. Procedure or Function?

`isFunction(false)` (default) calls a stored procedure. For a function, set `isFunction(true)` and specify the name/return according to the DB contract. SQL functions differ across PostgreSQL, Oracle, MySQL, and SQL Server; some return scalars while others return sets/tables. Test `OUT`, result maps, and `expectSingleResult` with the real driver.

### 10.2. Procedure Name Is Not a Bound SQL Parameter

`stored-procedure-name-expression` on some components allows selecting the procedure name via SpEL. Never let untrusted input dictate the procedure/function name, because placeholders only bind **values** and do not protect against invoking arbitrary routines. For inbound pollers, prefer a fixed routine name and a DB account with minimal `EXECUTE` privileges.

## 11. Poller: Interval, Invocation Count, and Row Limits

| Parameter | Unit | Example | Consequence |
|---|---|---|---|
| `fixedDelay` | Time between end of one poll and start of next | 5 seconds | Does not overlap cycles if a poll runs long in the same config |
| `fixedRate` | Fixed cadence on scheduler clock | 5 seconds | Requires controlling concurrency and scheduler behavior |
| `maxMessagesPerPoll` | Number of `receive()` calls per trigger | 1 | Does not mean one row |
| `maxRows` passed to procedure | Rows claimed/returned **per invocation** | 25 | Limits directly at the database |
| Thread/pool limits | Concurrent tasks/connections in flight | Load-dependent | Avoids creating too many connections and DB locks |

Suppose a poller runs every 5 seconds with `maxMessagesPerPoll(1)` and the procedure selects up to 25 rows. One poll can produce **one message containing 25 rows**, which becomes 25 messages after a splitter. Increasing `maxMessagesPerPoll` to 5 may cause the adapter to call the procedure **multiple times in the same cycle**, depending on source and results, generating extra database calls; it does not magically change to “5 rows”.

**Do not rely on Java-layer row limits to truncate excessive rows already read by the DB.** Prefer LIMIT/TOP/cursors/batching inside the procedure to protect the DB and memory.

### 11.1. Transactional Poller

For a procedure that both claims and returns rows, you can wrap execution in a **poller transaction**:

~~~java
// DSL fragment, transactionManager is a PlatformTransactionManager
e -> e.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

When downstream uses `DirectChannel` and runs **synchronously on the same thread**, JDBC work can share the poller transaction. When inserting an `ExecutorChannel`, `QueueChannel`, or async Kafka/HTTP sends, the poller transaction does not automatically span other threads or processes. You must choose separate commit/ACK/recovery boundaries.

## 12. Transactions, Crash Recovery, and Duplicate Prevention

### 12.1. Why “Claimed” Does Not Mean “Processed”

The sample procedure in section 4 changes status `NEW → CLAIMED`. If downstream fails, there are two scenarios:

- **Same JDBC transaction, synchronous downstream throws before commit**: the transaction can roll back, returning status to `NEW` for the next poll.
- **Claim transaction already committed and downstream runs on another system**: a post-commit error **does not automatically roll back** the claim. You need lease/reclaim and idempotency in subsequent steps.

~~~mermaid
flowchart TB
    A["NEW"] -->|"procedure claim"| B["CLAIMED"]
    B -->|"Processing succeeds + commit"| C["PROCESSED"]
    B -->|"Rollback with transaction"| A
    B -->|"Crash / lease expired"| D["Reclaim or DEAD_LETTER"]
    D -->|"Bounded retry"| A
    D -->|"Permanent error"| E["FAILED + alert"]
~~~

### 12.2. Two Reliable Approaches

**Approach A — synchronous transaction, DB work on the same source.** Wrap the poller and synchronous handlers in the same local `DataSourceTransactionManager`; if a handler throws, roll back the claim. Fits when the entire unit of work truly lives inside one short database transaction. Never hold transactions open while waiting on HTTP/SFTP/Kafka.

**Approach B — claim/lease + outbox/idempotency.** The procedure claims and records `lease_until`/`attempt_count`, and a worker processes the item; if a worker dies, a recovery job reclaims expired leases. For publishing events to a broker, a transactional outbox writes the event in the DB transaction, then a publisher sends it and marks it sent. Downstream consumers use `eventId` to prevent duplicate processing on redelivery.

No poller configuration turns JDBC + Kafka + HTTP into a **single exactly-once distributed transaction** out of the box.

### 12.3. Concurrency When Multiple Instances Run the Same Poller

If multiple application instances/pods call the procedure, each instance runs an independent poller. You must ensure **atomic claiming in the database**, proper locks/cursors, and a lease mechanism for incomplete rows. SQL Server hints are just one example; other DBs use equivalent mechanisms such as `FOR UPDATE SKIP LOCKED` or transactional updates with compatible locking. Never use a plain `SELECT WHERE status='NEW'` and assume pods will not read the same row.

## 13. Errors, Retries, Backoff, and errorChannel

Common error categories:

| Error | Symptom | Handling |
|---|---|---|
| Procedure missing / wrong schema | Invalid object/name | Fix schema, EXECUTE permissions, migration version |
| Parameter name/type mismatch | JDBC metadata/bind failure | Check `SqlParameter`, `ignoreColumnMetaData`, driver |
| Unexpected ResultSet shape | Mapper failure / invalid `expectSingleResult` | Inspect OUT/results, codecs/types, and map entry count |
| DB connection unavailable | `DataAccessResourceFailureException` or driver cause | Bounded retry, backoff, alert |
| Deadlock / lock timeout | Transient data access exception | Retry **entire transaction** if safe |
| Downstream service throws | Message handling exception | Rollback/recovery per channel/transaction |
| No rows | Empty list or no message emitted per semantics | Filter empty, metrics, do not treat as default error |
| Slow DB / large batch | Overlapping polls, pool exhaustion | Bound maxRows, pool, timeouts, and concurrency |

**Retries:** do not configure an aggressive fixed poller when the DB is down; multiple replicas retrying simultaneously can cause a *retry storm*. Add backoff/jitter and circuit-breaker/health gating as needed. Configuration/schema errors should not be retried infinitely. For procedures with claim side effects, retries must preserve idempotency and transaction semantics.

**Error channel:** Spring Integration provides `ErrorMessage`/`errorChannel` or poller error handlers depending on the endpoint and configuration. Do not assume a JDBC failure automatically turns into a normal business message on the output channel, or that errors across all threads reach the same handler. Test exception paths, transaction rollbacks, and re-polling in your target version.

## 14. Payload Contract, Transformation, and Splitting

An inbound procedure often produces **heterogeneous results**: a map keyed by OUT parameters, result set lists, counts, or function return values. The cleanest approach is an explicit conversion boundary:

~~~text
StoredProcExecutor result map
  {"orders": List<OrderRow>}
      |
expectSingleResult(true)
      v
Message<List<OrderRow>>
      |
filter(!empty)
      |
splitter
      v
Message<OrderRow> x N
      |
validator / router / gateway / Kafka adapter
~~~

Do not route a payload to a handler with signature `handle(OrderRow)` if the actual payload is still `Map<String,Object>` or `List<OrderRow>`. Add tests for:

- Map containing a single entry returning a list.
- Map containing an additional OUT parameter; error/transformer handling when `expectSingleResult` is enabled.
- Empty list or missing result set.
- Null SQL columns, `Timestamp` to `LocalDateTime` conversion, column names/aliases.
- Out-of-order events and duplicate IDs.

For downstream file/SFTP/HTTP/JMS/Kafka steps, include business correlation IDs (order ID, event ID, source system) rather than relying solely on Spring Integration-generated message IDs, which can change after retries or splits.

## 15. Security, Performance, and Observability

**Access permissions:** the DB connection account should only have `EXECUTE` on allowed procedures and minimal table privileges required by the routine. Never turn source data into dynamic procedure names and execute arbitrarily; use schemas, allowlists, and migrations to govern routines.

**Connection pool:** the JDBC poller uses connections from `DataSource`, so each running procedure occupies a pool slot and can hold locks. Monitor active/idle/pending connections, acquire wait time, procedure execution time, and transaction rollbacks. Raising poller concurrency indefinitely can slow down the DB.

**Metrics to record:**

1. Poll count, procedure latency, rows per poll, new/processed row counts.
2. Empty batch count, DB error rate, lock waits, deadlocks, timeouts, and retries.
3. Backlog size (`NEW`/`CLAIMED`/`FAILED` counts), age of `CLAIMED`, expired leases.
4. End-to-end latency from row creation to Kafka/JMS/HTTP receipt.
5. Duplicate event counts, redeliveries, outbox lag, DLQ counts, and alerts.

**Data security:** do not log PII/payment data from full result sets, JDBC credentials, or sensitive SQL bind values. Use bounded-cardinality tracing/correlation IDs and verify encryption at rest/TLS per environment policy.

## 16. Testing with a Real Database and Failure Injection

Spring Integration documentation clearly notes that stored procedure support depends on `SimpleJdbcCall` and the JDBC driver, and H2 has limitations around `CallableStatement` semantics. For the SQL Server example, tests should use a **dedicated test SQL Server or Testcontainers**, not merely mock `StoredProcExecutor`.

### 16.1. Integration Test Outline

1. Initialize the table and procedure from section 4 in the test database.
2. Insert 3 `NEW` orders.
3. Start the application flow with `maxRows=2` and controlled test polling timing.
4. Observe **one** poll claim at most 2 rows, return `List<OrderRow>`, and the splitter emit 2 messages.
5. Verify the DB transitioned exactly two rows to `CLAIMED` after transaction commit.
6. Allow the next poll: claim the third row; once no `NEW` rows remain, downstream receives no empty business batches.
7. Throw an exception in a synchronous downstream handler to verify rollback when a poller transaction is configured; check whether the row is polled again.
8. Run 2 app instances concurrently and verify each order ID is claimed according to the concurrency policy.
9. Simulate a crash after claim commit: run the recovery job or lease timeout and verify no rows remain stuck indefinitely.

### 16.2. Unit Testing the Mapper

You can test the RowMapper in a unit test independent of the poller:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.RowMapper;

class OrderRowMapperTest {

    @Test
    void mapsDatabaseColumns() throws Exception {
        ResultSet rs = mock(ResultSet.class);
        LocalDateTime created = LocalDateTime.of(2026, 11, 1, 9, 0);
        when(rs.getLong("order_id")).thenReturn(1001L);
        when(rs.getString("status")).thenReturn("CLAIMED");
        when(rs.getTimestamp("created_at"))
            .thenReturn(Timestamp.valueOf(created));

        RowMapper<StoredProcedureInboundFlow.OrderRow> mapper =
            (resultSet, rowNum) ->
                new StoredProcedureInboundFlow.OrderRow(
                    resultSet.getLong("order_id"),
                    resultSet.getString("status"),
                    resultSet.getTimestamp("created_at")
                        .toLocalDateTime());

        var row = mapper.mapRow(rs, 0);
        assertEquals(1001L, row.orderId());
        assertEquals("CLAIMED", row.status());
        assertEquals(created, row.createdAt());
    }
}
~~~

The Mockito example stubs a `ResultSet` to test field/type mapping, and **does not verify** that the actual procedure returns the expected ResultSet or JDBC metadata. That verification requires a real database. If tests use Spring Boot starter test, ensure the corresponding Mockito/JUnit dependencies are present.

### 16.3. Minimum Test Matrix

| Scenario | What to verify |
|---|---|
| Procedure returns 2 rows | `Message<List<OrderRow>>` → 2 messages after splitter |
| Procedure returns 0 rows | No unwanted empty business events emitted |
| Result map contains multiple OUT entries | `expectSingleResult` and mapping follow the contract |
| SQL parameter wrong type/name | Error raised, metrics/error flow record it |
| DB connection lost | Poller retries/backs off without creating a busy loop |
| Downstream handler throws | Rollback if sharing DB TX; recovery if already committed |
| Multiple pollers/replicas | No duplicate claims beyond design policy |
| Crash after claim before publish | Lease/recovery or outbox handles it |
| H2 differs from SQL Server | Tests do not assume CallableStatement equivalence |
| Wrong DB schema/permissions | Stops/alerts on configuration error, no infinite retry |

## 17. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| “Inbound procedure adapter runs whenever a message arrives” | The **poller** actively invokes `receive()` |
| “`maxMessagesPerPoll(1)` fetches one row” | One source invocation can return a `List` of many rows |
| “`expectSingleResult(true)` fetches one row” | It unwraps **one entry of the result map**, which can be `List<Row>` |
| “Stored procedure returning 3 rows immediately creates 3 messages” | Needs a splitter or row-splitting logic |
| “No rows is necessarily an exception” | Can be a normal state requiring a filter/contract |
| “Having `@Transactional` on any downstream handler is enough” | Thread boundaries, poller TX, and resource managers govern behavior |
| “Procedure claim succeeded means Kafka received the event” | DB TX does not automatically synchronize with a broker |
| “Running multiple replicas automatically prevents double claims” | Requires DB locks/atomic claims and recovery |
| “`Jdbc.storedProcInboundAdapter` works in Spring Integration 6.x” | The Java DSL factory starts in 7.0 |
| “Inbound can read `payload.maxRows` from a request” | There is no request message; parameters must be configured independently |
| “JDBC is non-blocking because the flow is in a WebFlux app” | JDBC is synchronous; manage poller threads/pools |
| “H2 test passing guarantees all vendors behave alike” | Stored procedures/CallableStatement vary by DB/driver |

## 18. Practice Exercises

1. Create the `integration_order` table and `POLL_NEW_ORDERS` procedure on a test SQL Server. Call the procedure manually with `@maxRows=2`.
2. Build a `Jdbc.storedProcInboundAdapter` flow for Spring Integration 7.x polling every 5 seconds; inspect the output map/list.
3. Remove `expectSingleResult(true)` and print the payload type. Then re-enable it and explain why the result is a list rather than a single row.
4. Remove `split()`, then add it back; measure the downstream message count for 2, 5, and 0 rows.
5. Change `maxMessagesPerPoll(1)` to `2` and observe how many times the procedure can execute in one cycle; contrast it with `maxRows`.
6. Create an XML inbound stored-proc configuration for 6.x and compare it with Java `StoredProcExecutor`/`StoredProcPollingChannelAdapter`.
7. Add an OUT parameter `totalClaimed` to the procedure and test a result map with multiple entries alongside `expectSingleResult`.
8. Intentionally misdeclare `SqlParameter` or disable metadata lookup improperly; identify the resulting error from `SimpleJdbcCall`.
9. Add a synchronous DB-writing handler after the splitter and deliberately throw an exception to test poller transaction rollback.
10. Insert an `ExecutorChannel` before the handler and prove that the poller's transaction does not propagate to the new thread.
11. Run two instances calling the same procedure, verifying atomic claim/locking and no duplicates beyond policy.
12. Simulate a crash when rows are `CLAIMED`; add `lease_until`, a recovery job, and idempotency by `orderId`/`eventId`.
13. Forward fetched rows to JMS/Kafka, design an outbox, and define ACK/commit conditions to handle redeliveries.
14. Replace SQL Server with another DB, rewrite the procedure, and adjust JDBC parameter/result mapping for the real vendor.

**Design scenario:** an ERP system only allows reading events via a stored procedure. Two Spring Integration instances poll concurrently; the procedure claims 100 rows and one instance dies before publishing to Kafka. Propose transaction boundaries, lease/reclaim, an outbox table, batch size, deduplication keys, and metrics to prevent losing work and minimize duplicate processing.

## 19. References

- [Spring Integration — Stored Procedures](https://docs.spring.io/spring-integration/reference/jdbc/stored-procedures.html): stored procedure inbound adapter, OUT/IN parameters, resultset mappers, `SimpleJdbcCall`, and XML options.
- [Spring Integration — Java DSL for JDBC Components (7.x)](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.storedProcInboundAdapter(...)`, `configurerStoredProcExecutor`, `expectSingleResult`, poller.
- [Spring Integration API — JdbcStoredProcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcStoredProcInboundChannelAdapterSpec.html): DSL builder starting in version 7.0.
- [Spring Integration API — StoredProcPollingChannelAdapter](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/StoredProcPollingChannelAdapter.html): polling source, constructors, `setExpectSingleResult`.
- [Spring Integration API — StoredProcExecutor](https://docs.spring.io/spring-integration/docs/6.3.0-RC1/api/org/springframework/integration/jdbc/StoredProcExecutor.html): `executeStoredProcedure`, parameters, result set mappers.
- [Spring Integration — Inbound Channel Adapters in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html): `MessageSource`, `IntegrationFlow.from`, and `Pollers`.
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, synchronous message flows, rollback.
- [Spring Framework — SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): JDBC stored procedures/functions, metadata, and mapping.

> **Remember:** The JDBC inbound stored procedure adapter is a **poller-triggered message source** that uses `StoredProcExecutor` and `SimpleJdbcCall` to invoke a procedure/function and send a **result map or list** into Spring Integration. Distinguish `maxMessagesPerPoll` from the procedure's row limit, `expectSingleResult` from row count, and DB transactions from Kafka/JMS ACKs. Reliable operation requires explicit result mapping, atomic claiming, recovery/leases, idempotency, and testing against the real database vendor.

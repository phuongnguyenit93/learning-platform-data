# Batch Updates and Performance in Spring Integration JDBC

## 1. Why Can Per-Message Processing Overload a Database?

Suppose an e-commerce application receives 50,000 inventory updates from Kafka within a short burst. Each change must update the `inventory_projection` table via Spring Integration JDBC. If every message immediately triggers a separate `UPDATE` round trip to the database, the system incurs heavy network round trips, repeated parameter binding, and prolonged connection hold times. As traffic rises, backlogs build up on `MessageChannel`s or brokers.

One solution is **grouping multiple updates into batch executions**. However, the word “batch” has at least three very different meanings:

1. **Batch message**: a single `Message<List<UpdateCommand>>` carrying multiple elements.
2. **JDBC batch**: calling `PreparedStatement.addBatch()` then `executeBatch()` (or Spring JDBC `batchUpdate()`) to execute **one SQL template with multiple parameter sets**.
3. **Set-based SQL**: a single `UPDATE ... WHERE id IN (:ids)` statement updating many rows in **one statement**, without necessarily calling JDBC `executeBatch()`.

In Spring Integration, distinguishing these three layers is key to optimizing properly without sacrificing data integrity for throughput.

~~~mermaid
flowchart LR
    A["Kafka/JMS/HTTP or JDBC inbound"] --> B["MessageChannel"]
    B --> C["Group/retain List<Command> payload"]
    C --> D["JDBC outbound adapter"]
    D --> E["PreparedStatement batchUpdate"]
    E --> F[("Database")]
    F --> G["Commit / rollback"]
~~~

This lesson, **Batch Updates and Performance**, belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems into Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and managing message contracts, errors, and connection lifecycles. This topic focuses on **batch SQL, transactions, row counts, measurable performance, retries, and idempotency**.

**Goal after this lesson:** recognize accurately when Spring Integration actually invokes JDBC batching; write Java DSL/XML, use `JdbcTemplate`/`NamedParameterJdbcTemplate`, choose batch sizes, measure bottlenecks, and handle errors/rollbacks in multi-worker environments.

## 2. Three Batching Layers That Are Not Equivalent

| Layer | Grouping unit | API/example | What it does not guarantee automatically |
|---|---|---|---|
| Message | `List<Command>` in one payload | Aggregator, polling result list | That the database uses a batch API |
| JDBC | Multiple parameter sets for the **same SQL** | `JdbcMessageHandler` with `Iterable`; `JdbcTemplate.batchUpdate` | Atomic cross-system commit |
| Set-based SQL | One statement processing many rows | `UPDATE ... WHERE id IN (:ids)` | Detailed per-row outcomes |
| DB load | Bulk insert, staging table, vendor COPY | PostgreSQL COPY, bulk loaders | Portability across every JDBC adapter |
| Polling | Multiple rows from one SELECT | JDBC inbound `maxRows`, SQL LIMIT | Emitting separate messages without a splitter |
| Transaction | Group of DML committed/rolled back together | `@Transactional` or transactional poller | Kafka/JMS brokers committing alongside the DB |

An example of operation counts:

~~~text
100 Message<UpdateCommand>
    -> per-message handler: can trigger 100 separate SQL executions

1 Message<List<UpdateCommand>> with 100 elements
    -> JdbcMessageHandler receives Iterable:
       one batchUpdate with 100 parameter sets

1 Message<List<Long>> containing 100 IDs
    -> UPDATE ... WHERE id IN (:ids):
       one SQL statement with 100 IDs, not a 100-entry JDBC batch
~~~

**“One message containing 100 elements” does not automatically mean “one database transaction”.** Transactions depend on where they start, the transaction manager, thread/channel boundaries, and how exceptions propagate.

## 3. Reference Architecture: Read, Transform, Batch Write

~~~mermaid
sequenceDiagram
    participant P as JDBC poller
    participant DB as Source database
    participant T as Transformer
    participant H as JdbcMessageHandler
    participant OUT as Target database
    P->>DB: SELECT up to N rows
    DB-->>P: List<SourceRow>
    P->>T: Message<List<SourceRow>>
    T-->>H: Message<List<UpdateCommand>>
    H->>OUT: batchUpdate SQL with N parameter sets
    OUT-->>H: Batch result / exception
    Note over H,OUT: Needs a transaction to roll back on error
~~~

A pipeline preserving `List` from inbound to outbound can leverage **`Iterable` batching** directly. If you insert a `Splitter` right before JDBC outbound, each element becomes **one message** and the handler only sees a single payload; `JdbcMessageHandler` will no longer auto-batch per message.

Conversely, if each message needs independent handling or per-row replies/ACKs, splitting may still be the right business design. Never “batch for speed” by erasing critical error boundaries.

## 4. Practice Schema and Sample Data

Examples use Java 17+, Spring Boot, Spring Integration JDBC, and Spring JDBC. Use the BOM/Spring Boot dependency management instead of mixing incompatible Spring versions manually.

~~~groovy
// build.gradle - dependencies snippet for the practice app
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml: H2 is only for basic tests and demos.
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_batch_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
  sql:
    init:
      mode: always
~~~

Suppose the practice app puts this DDL in `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory_projection (
    item_id       BIGINT NOT NULL PRIMARY KEY,
    quantity      INTEGER NOT NULL,
    version       INTEGER NOT NULL DEFAULT 0,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE incoming_inventory_change (
    id            BIGINT NOT NULL PRIMARY KEY,
    event_id      VARCHAR(80) NOT NULL UNIQUE,
    item_id       BIGINT NOT NULL,
    target_qty    INTEGER NOT NULL,
    state         VARCHAR(24) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_outbox (
    event_id      VARCHAR(80) NOT NULL PRIMARY KEY,
    item_id       BIGINT NOT NULL,
    payload_json  VARCHAR(2000) NOT NULL,
    published     BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO inventory_projection(item_id, quantity, version)
VALUES (201, 10, 0), (202, 20, 0), (203, 30, 0);

INSERT INTO incoming_inventory_change
    (id, event_id, item_id, target_qty, state)
VALUES (101, 'inv-101', 201, 11, 'NEW'),
       (102, 'inv-102', 202, 25, 'NEW'),
       (103, 'inv-103', 203, 34, 'NEW');
~~~

`target_qty` is a replacement snapshot, **not a delta**. With `quantity = quantity + :delta`, duplicate retries can double-count inventory; the idempotency sections examine this closely.

Use real PostgreSQL/MySQL/SQL Server/Oracle when measuring driver batching, locking, isolation, or transactions. H2 is no substitute for production database benchmarks.

## 5. JDBC Inbound: Max N Rows Is Not N Updates

`JdbcPollingChannelAdapter` runs `SELECT` on a poller and emits a `Message<List<Row>>`. Per the Spring Integration JDBC Reference:

- `maxRows` caps **rows in one query result**; `0` means unlimited.
- `maxMessagesPerPoll` is **how many times the poller calls `receive()` per trigger**; for JDBC inbound the default is typically 1.
- SQL `LIMIT`/`TOP`/`FETCH` limits results at the DB; prefer this when tables are large.
- `RowMapper<T>` converts each row to a DTO; a `Splitter` is only needed when downstream expects individual messages.

~~~sql
SELECT id, event_id, item_id, target_qty
FROM incoming_inventory_change
WHERE state = 'NEW'
ORDER BY created_at, id
LIMIT 100;
~~~

~~~text
maxRows=100, maxMessagesPerPoll=1, SQL LIMIT 100
  -> 1 SELECT per trigger
  -> up to 100 rows
  -> 1 Message<List<ChangeRow>>
  -> if split: up to 100 Message<ChangeRow>
~~~

**Do not set `maxMessagesPerPoll(100)` expecting a batch of 100 rows.** Doing so can execute SELECT 100 times consecutively in a single trigger, increasing database load instead of reducing it.

## 6. JDBC Inbound UPDATE: Set-Based vs. Per-Row vs. Driver Batch

The inbound JDBC adapter supports an `UPDATE` statement to mark SELECTed rows. Two usage modes should be distinguished:

### 6.1. Set-Based UPDATE for the Whole Result List

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id IN (:ids) AND state='NEW';
~~~

In `updateSqlParameterSourceFactory`, build a `SqlParameterSource` with `ids` extracted from the **SELECT result `List`**; keep `updatePerRow(false)` (the default). Spring JDBC expands the named parameter collection for `IN`. This is **one set-based SQL statement**, *not* Spring JDBC `batchUpdate()`.

### 6.2. Per-Row UPDATE

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id=:id AND state='NEW';
~~~

With `updatePerRow(true)`, the factory receives each row individually to create a parameter source. The adapter updates row by row, though **do not assume it automatically calls `PreparedStatement.addBatch/executeBatch`**. That is an object-processing mode of the inbound adapter; outbound `JdbcMessageHandler` JDBC batching is a separate mechanism.

| Mechanism | Typical SQL statements for 100 rows | Parameter unit | Strengths | Trade-offs |
|---|---:|---|---|---|
| `updatePerRow(false)` + `IN (:ids)` | 1 | List of 100 IDs | Fewer round trips / SQL executions | No per-row update count |
| `updatePerRow(true)` | 100 | Individual row | Per-row expressions/context | Many statements if not driver-batched |
| `JdbcTemplate.batchUpdate` | 1 JDBC batch of 100 entries | 100 parameter sets | Reuses one SQL template | Driver-dependent row counts/partial failures |
| `UPDATE ... FROM staging` | 1 set-based statement after load | Staging table | Effective for huge bulk loads | Extra staging/maintenance |

The “100” counts in the table are **illustrative logical operation counts**, not a benchmark on any specific driver. With SQL `IN`, placeholder limits, query-plan churn, and packet sizes must be measured for very large batches.

## 7. Real JdbcMessageHandler Feature: `Iterable` Payloads Trigger Batching

Per the Spring Integration Reference, since **version 5.1**, `JdbcMessageHandler` (the JDBC outbound channel adapter) executes `JdbcOperations.batchUpdate()` when **the message payload is an `Iterable`**.

Mechanics:

1. A message arrives at the handler with payload `List<InventoryUpdate>`.
2. The handler iterates over elements. If an element is not already a `Message<?>`, it is wrapped in a message inheriting **the original message's headers**.
3. With `SqlParameterSourceFactory`, the handler creates a `SqlParameterSource[]` array and runs a JDBC batch operation.
4. With `MessagePreparedStatementSetter`, the handler uses the `BatchPreparedStatementSetter` variant to bind each element.
5. **JDBC batch updates are not supported when `keysGenerated` mode is enabled.**

~~~text
Message<List<InventoryUpdate>>
  headers: {correlationId: "batch-27"}
  payload: [
    InventoryUpdate(201, 11),
    InventoryUpdate(202, 25),
    InventoryUpdate(203, 34)
  ]
            |
            v
JdbcMessageHandler.handleMessage(...)
            |
            v
PreparedStatement:
 UPDATE inventory_projection
 SET quantity = ?, version=version+1
 WHERE item_id = ?
  addBatch(qty=11, id=201)
  addBatch(qty=25, id=202)
  addBatch(qty=34, id=203)
  executeBatch()
~~~

**Common mistake:** if the payload is a `List` and you call `.split()` before the handler, each message carries only one `InventoryUpdate`, losing list-wide batching. A `byte[]` is not an `Iterable` just because it holds multiple bytes, nor is a Java array automatically an `Iterable`. To trigger auto-batching, send a payload implementing `Iterable`.

## 8. Spring Integration 7.x Java DSL: Outbound Adapter Batching

Spring Integration **7.0** introduced the Java DSL JDBC factory `org.springframework.integration.jdbc.dsl.Jdbc`. The example below uses `MessagePreparedStatementSetter` to avoid relying on bean-property introspection:

~~~java
package com.example.batch;

public record InventoryUpdate(long itemId, int targetQty) {
}
~~~

~~~java
package com.example.batch;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class JdbcBatchOutboundFlow {

    @Bean
    public IntegrationFlow writeInventoryBatches(DataSource dataSource) {
        return IntegrationFlow.from("inventoryBatchInput")
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE inventory_projection "
                  + "SET quantity=?, version=version+1, "
                  + "    updated_at=CURRENT_TIMESTAMP "
                  + "WHERE item_id=?")
                .preparedStatementSetter((ps, message) -> {
                    InventoryUpdate row =
                        (InventoryUpdate) message.getPayload();
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }))
            .get();
    }
}
~~~

The input must be a `Message<List<InventoryUpdate>>`, not individual `Message<InventoryUpdate>` messages, for the handler to batch the whole list:

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

List<InventoryUpdate> rows = List.of(
    new InventoryUpdate(201L, 11),
    new InventoryUpdate(202L, 25),
    new InventoryUpdate(203L, 34));

MessageChannel channel = /* Bean inventoryBatchInput */;
boolean accepted = channel.send(
    MessageBuilder.withPayload(rows).build());
~~~

**This send snippet is a fragment**; inject `@Qualifier("inventoryBatchInput") MessageChannel channel` from the Spring context. `send() == true` is not proof of cross-system commit; it only reports channel acceptance/send per channel semantics.

An `Iterable` request payload and `keysGenerated=false` are the conditions for the outbound handler to pick batch mode. If business logic needs **per-row update counts**, the one-way outbound **adapter** produces no reply; use a `JdbcTemplate.batchUpdate` service or an explicitly version-verified gateway contract.

### 8.1. Why Not Use a Splitter Before the Outbound Adapter?

~~~java
// Does NOT batch the whole list: splitter emits individual messages.
return IntegrationFlow.from("inventoryBatchInput")
    .split()
    .handle(Jdbc.outboundAdapter(dataSource, sql))
    .get();
~~~

This configuration **may be valid** when each row needs its own processing step, per-row retry, or per-row metrics. However, it defeats “one `Iterable` message → one JDBC batch” unless you **re-aggregate** before the handler.

## 9. Spring Integration 6.x Java Configuration: JdbcMessageHandler

In **6.x**, `JdbcMessageHandler` already supports `Iterable` batching (since 5.1), even though the 7.x JDBC Java DSL factory `Jdbc.outboundAdapter(...)` does not yet exist. You can configure the handler directly:

~~~java
package com.example.batch;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcMessageHandler;

@Configuration
public class LegacyJdbcBatchConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "inventoryBatchInput")
    public JdbcMessageHandler inventoryBatchHandler(
            DataSource dataSource) {
        JdbcMessageHandler handler = new JdbcMessageHandler(
            dataSource,
            "UPDATE inventory_projection SET quantity=?, "
          + "version=version+1 WHERE item_id=?");

        handler.setPreparedStatementSetter((ps, message) -> {
            InventoryUpdate row =
                (InventoryUpdate) message.getPayload();
            ps.setInt(1, row.targetQty());
            ps.setLong(2, row.itemId());
        });
        return handler;
    }
}
~~~

A message carrying `List<InventoryUpdate>` still triggers batching. This is an **alternative**; do not register both section 8's and section 9's configurations on `inventoryBatchInput` in the same context just for demo purposes, as a `DirectChannel` with two subscribers load-balances rather than broadcasting to both.

## 10. XML JDBC Outbound Adapter Handling Iterable Batches

~~~xml
<!-- XML fragment: requires int-jdbc namespace and dataSource bean. -->
<int:channel id="inventoryBatchInput"/>

<int-jdbc:outbound-channel-adapter
    id="inventoryBatchWriter"
    channel="inventoryBatchInput"
    data-source="dataSource"
    query="UPDATE inventory_projection
           SET quantity=:payload[targetQty],
               version=version+1
           WHERE item_id=:payload[itemId]"/>
~~~

With a `List` payload, since Spring Integration 5.1 the outbound `JdbcMessageHandler` executes in batch mode. `:payload[targetQty]` and `:payload[itemId]` are evaluated against **each element's wrapped message** (under the default parameter strategy). This is a **bean property / map path expression**, not full SpEL. To control SQL types or complex data, declare a dedicated `sql-parameter-source-factory` or `prepared-statement-setter` per contract.

Some environments handle bean properties differently from Java records; verify binding on your target Spring version. When certainty is paramount, use `MessagePreparedStatementSetter` as in the Java examples above or a JavaBean DTO with getters.

## 11. No Generated Keys in JDBC Outbound Batch Mode

A constraint explicitly documented by Spring Integration: **`JdbcMessageHandler` does not support batch updates when `keysGenerated` mode is enabled**. This stems from the messaging contract and wide JDBC driver differences in returning generated keys per batch entry.

| Requirement | Approach |
|---|---|
| Batch multiple UPDATEs with known IDs | `Iterable` payload + JDBC outbound adapter |
| Batch multiple INSERTs with app-assigned IDs | `Iterable` payload + `keysGenerated=false` |
| INSERT needing generated keys returned per row | Separate INSERT/gateway flow or driver-verified repository/API |
| Per-row counts / partial failures needed | `JdbcTemplate.batchUpdate` with explicit result/exception handling |
| Returning newly inserted rows via `RETURNING` | Vendor-specific SQL + service/repository or custom message source |

Never enable `.keysGenerated(true)` and claim the outbound adapter still batches. On databases offering `INSERT ... RETURNING`/`OUTPUT`, that is a separate contract requiring driver-specific testing and mapping rather than `JdbcMessageHandler` batch mode.

## 12. Spring JDBC: BatchPreparedStatementSetter

When you need per-row results, update-count checks, or explicit service control, use Spring JDBC directly instead of relying on the one-way outbound adapter:

~~~java
package com.example.batch;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryJdbcBatchRepository {

    private final JdbcTemplate jdbc;

    public InventoryJdbcBatchRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] updateQuantities(List<InventoryUpdate> updates) {
        if (updates.isEmpty()) {
            return new int[0];
        }

        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=?, version=version+1, "
          + "    updated_at=CURRENT_TIMESTAMP "
          + "WHERE item_id=?",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(
                        PreparedStatement ps, int index)
                        throws SQLException {
                    InventoryUpdate row = updates.get(index);
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }

                @Override
                public int getBatchSize() {
                    return updates.size();
                }
            });
    }
}
~~~

`getBatchSize()` returns the number of parameter sets, `setValues(...)` binds each entry, and `batchUpdate(...)` returns the `int[]` update counts reported by the JDBC driver. This fits when the batch is already in memory and needs one `PreparedStatement` with many bindings.

**Never call `jdbc.batchUpdate(...)` on an unbounded list.** For large files/streams, split into memory-bounded chunks or use the chunking overload with `batchSize`; even when JDBC supports batching, holding millions of command objects and parameter values on the heap is risky.

## 13. `NamedParameterJdbcTemplate.batchUpdate` and `SqlParameterSource`

When SQL has many named parameters, `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` keeps code readable. You need **one `SqlParameterSource` per row**, unlike `IN (:ids)` which uses one parameter source holding a list.

~~~java
package com.example.batch;

import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.stereotype.Repository;

@Repository
public class NamedInventoryBatchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public NamedInventoryBatchRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[] update(List<InventoryUpdate> updates) {
        if (updates.isEmpty()) {
            return new int[0];
        }

        SqlParameterSource[] bindings = updates.stream()
            .map(row -> new MapSqlParameterSource()
                .addValue("qty", row.targetQty())
                .addValue("itemId", row.itemId()))
            .toArray(SqlParameterSource[]::new);

        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=:qty, "
          + "    version=version+1 "
          + "WHERE item_id=:itemId",
            bindings);
    }
}
~~~

`MapSqlParameterSource` does not require a record to have `getItemId()`. For JavaBean properties or matching `Map<String,Object>` structures, you can use `SqlParameterSourceUtils.createBatch(...)`:

~~~java
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSourceUtils;

// Assumes records/maps expose properties matching SQL parameter names.
// Verify actual binding behavior in your Spring Framework version.
SqlParameterSource[] batch =
    SqlParameterSourceUtils.createBatch(beanArray);

int[] counts = namedJdbc.batchUpdate(
    "UPDATE inventory_projection "
  + "SET quantity=:targetQty WHERE item_id=:itemId",
    batch);
~~~

`beanArray` is an application-declared array of DTOs. This snippet highlights the `SqlParameterSourceUtils` API rather than forming a complete class. With Java records, null values, or custom types, constructing `MapSqlParameterSource` explicitly is usually easier to verify.

## 14. Splitting a Large Input into Multiple Bounded JDBC Batches

Spring JDBC provides the overload:

`JdbcTemplate.batchUpdate(String sql, Collection<T> args, int batchSize, ParameterizedPreparedStatementSetter<T> pss)`.

It returns `int[][]`, containing **one counts array per sub-batch**:

~~~java
package com.example.batch;

import java.util.Collection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ChunkedInventoryRepository {

    private final JdbcTemplate jdbc;

    public ChunkedInventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int[][] updateInChunks(
            Collection<InventoryUpdate> commands) {
        return jdbc.batchUpdate(
            "UPDATE inventory_projection "
          + "SET quantity=?, version=version+1 "
          + "WHERE item_id=?",
            commands,
            100,
            (ps, row) -> {
                ps.setInt(1, row.targetQty());
                ps.setLong(2, row.itemId());
            });
    }
}
~~~

With 230 commands and `batchSize` 100, **in terms of result shape**, there are typically three sub-batches:

~~~text
counts[0] -> 100 entries
counts[1] -> 100 entries
counts[2] -> 30 entries
~~~

**Important:** splitting 230 entries into three sub-batches **does not create three database transactions by default**. Inside `@Transactional`, all three sub-batches still share **one local transaction**; outside any transaction, driver/`DataSource` autocommit and execution semantics determine partial commits.

When an input has millions of rows, stream/read sequentially by pages or cursors, build moderately sized `List<Command>` chunks, call `batchUpdate`, and release the list—paired with explicit transaction boundaries instead of holding all data in heap.

## 15. Update Counts: 0, Positive Numbers, `SUCCESS_NO_INFO`, and `EXECUTE_FAILED`

JDBC `executeBatch()` reports counts in the order of parameter sets:

| Value | Java constant | Interpretation |
|---|---|---|
| `0` | No dedicated constant | Statement executed, but zero rows matched |
| `1` | — | One row affected per driver report |
| `n > 1` | — | Entry affected multiple rows |
| `-2` | `Statement.SUCCESS_NO_INFO` | Entry succeeded, **exact row count unknown** |
| `-3` | `Statement.EXECUTE_FAILED` | Entry failed when driver continued after error |

When the entire batch succeeds, JDBC `executeBatch()` returns counts; when an entry fails, JDBC may throw `BatchUpdateException`. Depending on the driver, it either **stops at the failing entry** or **continues executing remaining entries**; `getUpdateCounts()` may contain only entries run before the failure, or include `EXECUTE_FAILED` codes for failing entries.

~~~java
import java.sql.Statement;

for (int count : updateCounts) {
    if (count == Statement.SUCCESS_NO_INFO) {
        // Driver reports success, but row count is unknown.
    } else if (count == Statement.EXECUTE_FAILED) {
        // Typically seen when inspecting BatchUpdateException.
    } else if (count == 0) {
        // ItemId may be missing or optimistic version conflicted.
    } else if (count > 0) {
        // Affected `count` rows per driver.
    }
}
~~~

**Never sum all `counts` directly to compute total updated rows**, because `-2` is not a negative row count. If your application must confirm every update affected exactly one row, verify via another mechanism or choose compatible SQL/driver settings when `SUCCESS_NO_INFO` occurs.

### 15.1. `BatchUpdateException` and Exception Translation

Spring `JdbcTemplate` normally translates `SQLException` to `DataAccessException`. When you need root causes or counts for diagnostics, walk the cause chain for `BatchUpdateException`, while still **never treating partial counts as justification to commit successful entries** when business rules require all-or-nothing.

~~~java
import java.sql.BatchUpdateException;

// Pseudocode: inside a DataAccessException catch block.
Throwable current = ex;
while (current != null) {
    if (current instanceof BatchUpdateException batchEx) {
        int[] partial = batchEx.getUpdateCounts();
        // Record metrics / log without leaking sensitive data.
        // Let the transaction roll back; never ACK the batch as succeeded.
        break;
    }
    current = current.getCause();
}
~~~

**Inside a transactional handler**, let exceptions propagate so the transaction manager rolls back per rules. If you catch `DataAccessException` and return normally, the poller/transaction interceptor may COMMIT partial work. Driver partial execution and DB transaction commit are **two distinct layers of semantics**.

## 16. Transactions and Rollback When One Entry in a Batch Fails

A JDBC batch can execute inside one local transaction, keeping all UPDATEs as **a single unit of work**:

~~~java
package com.example.batch;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryBatchService {

    private final NamedInventoryBatchRepository repository;

    public InventoryBatchService(
            NamedInventoryBatchRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int[] apply(List<InventoryUpdate> updates) {
        int[] counts = repository.update(updates);

        for (int count : counts) {
            if (count != 1 &&
                count != java.sql.Statement.SUCCESS_NO_INFO) {
                throw new IllegalStateException(
                    "Unexpected update count: " + count);
            }
        }

        return counts;
    }
}
~~~

In this example, `SUCCESS_NO_INFO` is accepted as **statement success per JDBC**, though it does not prove every row existed or matched version; a stricter policy might **reject** it if an exact count of 1 is mandatory. Policy must follow your business contract.

Conditions for rolling back the entire batch:
- The service is invoked through its **Spring transactional proxy**, not self-invocation.
- The transaction manager manages **the same `DataSource`** used by `NamedParameterJdbcTemplate`.
- Using `JdbcTransactionManager` or `DataSourceTransactionManager` matching the JDBC resource, not a broker transaction manager.
- Statements execute over the connection enlisted in the active transaction.
- Exceptions escape the transactional method or the transaction is marked rollback-only.
- The DB/engine supports transactional DML on that table.

**Important caveat:** without a transaction, earlier entries may already have committed before the driver reports an error. `@Transactional` cannot roll back another database or Kafka/HTTP messages already sent outside the local JDBC transaction.

### 16.1. `TransactionTemplate` When Explicit Boundaries Are Needed

~~~java
import org.springframework.transaction.support.TransactionTemplate;

int[] counts = new TransactionTemplate(transactionManager).execute(
    status -> repository.update(updates));
~~~

`TransactionTemplate` must execute on the thread performing JDBC work, using the matching manager/`DataSource`. If code dispatches `Message<List<...>>` over an `ExecutorChannel`, never assume the sending thread's transaction propagates to the executor.

## 17. Polling Inbound Then Writing JDBC Outbound in One Transaction

A common scenario: an inbound adapter reads `incoming_inventory_change`, marks `NEW → CLAIMED`, and passes the rows to update `inventory_projection`. When **both tables must commit together**, keep downstream synchronous inside the poller transaction.

~~~mermaid
sequenceDiagram
    participant P as Transactional poller
    participant SRC as JDBC inbound
    participant DB as Database
    participant H as JdbcMessageHandler
    P->>DB: BEGIN
    P->>SRC: SELECT up to 100 NEW rows
    SRC->>DB: UPDATE matched IDs to CLAIMED
    SRC-->>H: Message<List<ChangeRow>>
    H->>DB: JDBC batchUpdate 100 updates
    alt Batch succeeds
        P->>DB: COMMIT
    else One entry fails
        H-->>P: Exception
        P->>DB: ROLLBACK both claim and batch
    end
~~~

**Key requirement to verify:** `Message<List<ChangeRow>>` must stay intact until the outbound handler. A transformer converting to `List<InventoryUpdate>` works fine as long as the final payload is an `Iterable`. Inserting a splitter or async channel in between alters transaction and batching semantics.

### 17.1. Spring Integration 7.x Java DSL: Illustrative Flow

~~~java
package com.example.batch;

import java.time.Duration;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ClaimThenBatchFlow {

    public record ChangeRow(
        long id, String eventId, long itemId, int targetQty) { }

    @Bean
    public IntegrationFlow claimAndUpdateProjection(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                    "SELECT id, event_id, item_id, target_qty "
                  + "FROM incoming_inventory_change "
                  + "WHERE state='NEW' ORDER BY id LIMIT 100")
                    .maxRows(100)
                    .rowMapper((rs, n) -> new ChangeRow(
                        rs.getLong("id"),
                        rs.getString("event_id"),
                        rs.getLong("item_id"),
                        rs.getInt("target_qty")))
                    .updateSql(
                        "UPDATE incoming_inventory_change "
                      + "SET state='CLAIMED' "
                      + "WHERE id IN (:ids) AND state='NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> list = (List<?>) result;
                        List<Long> ids = list.stream()
                            .map(ChangeRow.class::cast)
                            .map(ChangeRow::id)
                            .toList();
                        return new MapSqlParameterSource("ids", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(3))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> list && !list.isEmpty())
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE inventory_projection "
                  + "SET quantity=?, version=version+1 "
                  + "WHERE item_id=?")
                .preparedStatementSetter((ps, message) -> {
                    ChangeRow row = (ChangeRow) message.getPayload();
                    ps.setInt(1, row.targetQty());
                    ps.setLong(2, row.itemId());
                }))
            .get();
    }
}
~~~

**This is a single-instance flow for learning batching + transactions**, not a race-free distributed queue. Two pods running plain SELECT can still read the same rows before UPDATE. Multi-instance setups need `SELECT ... FOR UPDATE SKIP LOCKED` in the same transaction, atomic claims returning rows, or partition ownership; adapt the SQL to your DB vendor and run concurrency tests.

Specifically, `ChangeRow.targetQty` is a **replacement snapshot value**. For non-idempotent delta updates or multiple events for the same item within one batch, enforce version/order/idempotency policies; JDBC batching alone does not resolve source/consumer ordering.

### 17.2. When Source and Target Databases Differ

The flow above only commits both tables together when they share **one local `DataSource`/transaction manager**. If inbound reads DB A and outbound writes DB B, `.transactional(managerA)` does not create an atomic DB A + DB B transaction. In that case use outbox/inbox, replay/idempotency, sagas, or carefully tested XA/JTA.

## 18. Grouping Individual Messages with Aggregator: Batch Size and Timeout

When Kafka/JMS/HTTP delivers **one message per event**, you need a grouping stage or application batch buffer before the JDBC outbound handler. Spring Integration offers **`Aggregator`** and `MessageGroupStore`, requiring careful design of:

- **Correlation key:** how messages are grouped (tenant, aggregate, partition). Never use one constant key for all messages if groups are never closed/released properly.
- **Release strategy:** emit when `N` messages arrive or on timeout deadline.
- **Group timeout:** avoid incomplete groups sitting forever without reaching `N`.
- **Partial results:** if releasing fewer than `N`, define retry and ACK units clearly.
- **Persistent `MessageGroupStore`:** to prevent losing buffered messages on crash, use a persistent store/queue.
- **Ordering:** preserve per-item/aggregate order if business logic requires it; multi-worker execution can reorder.
- **Backpressure:** bound in-memory buffering when the DB slows down.

~~~text
Kafka/JMS event stream:
 e1  e2  e3  e4  e5  ...
  |   |   |   |   |
  v   v   v   v   v
Aggregator (size=3 or group timeout)
  -> Message<List<InventoryUpdate>> [e1,e2,e3]
  -> Message<List<InventoryUpdate>> [e4,e5] (partial group)
  -> JDBC outbound adapter batch
~~~

**Do not assume `Aggregator` automatically produces a JDBC batch just by existing.** The released payload must be a suitable `Iterable`. Depending on configuration and release processor, an aggregator's default output may carry a `Collection` payload or `MessageGroup`; verify and use a `Transformer` to build `List<InventoryUpdate>` if needed.

**ACK with Kafka/JMS:** if source offsets/ACKs are committed while events sit only in aggregator memory, a crash loses unreleased groups. For strong guarantees, use broker batch listener containers or persistent aggregators/outboxes before ACKing.

## 19. Choosing Batch Size: Balancing Throughput and Tail Latency

Batch size is a **parameter to measure**, with no universal optimum across databases. A benchmark plan might test `1, 10, 50, 100, 250, 500` entries/batch on the same workload.

| Small batch | Large batch |
|---|---|
| Lower per-event latency under light load | Higher potential throughput under heavy load |
| Easier to retry and pinpoint failing entries | Failure on one entry can roll back a huge batch |
| Lower memory usage and lock hold duration | Larger payloads/buffers and longer transactions |
| More database round trips | Fewer round trips, but hits packet/parameter limits |
| Simpler ordering behavior | Duplicate IDs / ordering require careful handling |

**A two-parameter trade-off:** maximum `batch size` and `max wait`. Waiting strictly for N under light load creates huge latency; flushing too eagerly reduces batching gains. Choose thresholds based on SLA, not rows/sec alone.

### 19.1. Measure Instead of Guessing

From each benchmark run, collect:
- `batch_size_actual` (p50/p95), batches per second.
- `batch_execute_duration` (p50/p95/p99), transaction duration.
- Events/second and rows-affected/second.
- Wait time before flushing a batch (`queue_wait`).
- Database CPU/IO, WAL/redo volume, locks/deadlocks.
- Hikari pool acquire waits, active/pending connections.
- Retries, rolled-back batches, and DLQ counts.
- Heap usage with large buffers.

**Never write “batch 500 is always 5x faster than batch 100”** without measuring. Gains depend on network latency, driver, SQL plan, row sizes, indexes, DB locks, and assembly cost.

## 20. Set-Based SQL vs. JDBC Batch: Sometimes One Statement Is Better

When applying the same state to many IDs, one set-based SQL statement can be faster and simpler to keep atomic:

~~~sql
UPDATE incoming_inventory_change
SET state='CLAIMED'
WHERE id IN (:ids)
  AND state='NEW';
~~~

Whereas when each row carries a distinct quantity, a JDBC batch sharing one SQL template is natural:

~~~sql
UPDATE inventory_projection
SET quantity=:targetQty, version=version+1
WHERE item_id=:itemId;
~~~

For hundreds of thousands of rows needing complex joins/mappings, a **staging table + merge/set-based UPDATE** can perform better:

~~~sql
-- PostgreSQL illustration: staging_inventory already holds clean data.
UPDATE inventory_projection AS i
SET quantity = s.target_qty,
    version = i.version + 1
FROM staging_inventory AS s
WHERE i.item_id = s.item_id;
~~~

Precondition: staging data must be checked for duplicate item IDs; if multiple staging rows match one target row, join/update semantics become unpredictable and DB-dependent. Loading staging, merging, and cleaning up need their own transaction/recovery policy.

**Do not assume JDBC batch = one SQL statement.** A JDBC driver may send multiple executions in a protocol batch; a set-based UPDATE is literally one SQL statement operating on many rows directly.

## 21. Driver-Level Batching and Vendor-Specific Settings

### 21.1. PostgreSQL pgJDBC

pgJDBC offers `reWriteBatchedInserts=true`, which rewrites compatible **batch INSERTs** into multi-row INSERTs to cut network/protocol overhead:

~~~yaml
# PostgreSQL example; password must come from a secret manager.
spring:
  datasource:
    url: "jdbc:postgresql://db.example:5432/app?reWriteBatchedInserts=true"
~~~

Do not conclude this property optimizes **UPDATEs** the same way as INSERTs. It targets eligible batch INSERTs for driver rewriting. Rewriting can also alter **update count shapes**, because the driver may no longer report individual counts per INSERT. Test carefully with `ON CONFLICT`/generated keys/`RETURNING`.

### 21.2. MySQL Connector/J

MySQL Connector/J offers `rewriteBatchedStatements=true` for certain batch scenarios, rewriting compatible `INSERT`/`REPLACE` statements into multi-value forms, subject to packet, generated key, and count caveats:

~~~text
jdbc:mysql://db.example:3306/app?rewriteBatchedStatements=true
~~~

**Note:** when combined with `INSERT ... ON DUPLICATE KEY UPDATE`, per-entry update counts may lose granularity and return `SUCCESS_NO_INFO`. Large SQL/batches must respect `max_allowed_packet` and driver limits.

### 21.3. SQL Server, Oracle, and Other Vendors

Never copy pgJDBC/MySQL flags into SQL Server or Oracle JDBC URLs. Each driver has its own options for statement caching, parameter binding, batch sizing, and bulk APIs. Very large workloads may suit `COPY`/bulk loaders better than JDBC batching.

**Right policy:** align driver versions, measure a baseline, change one knob at a time, verify correctness/update counts, and re-benchmark on the same dataset. Never enable statement rewriting solely because it boosted throughput on another system.

## 22. SQL Parameter Types, NULLs, and Batch Overhead

Batches can slow down due to type inference for `null` values, especially when the driver queries `ParameterMetaData.getParameterType()`. Spring Framework Reference notes that metadata lookup can incur extra round trips; since **Spring Framework 6.1.2**, certain PostgreSQL/SQL Server drivers bypass that default lookup path.

Proactive ways to eliminate ambiguity:

1. Use `PreparedStatement#setNull(index, Types.VARCHAR)`, `setObject(..., sqlType)`, or typed setters.
2. With `MapSqlParameterSource`, specify SQL types via `.addValue(name, value, Types.VARCHAR)` or `registerSqlType(...)`.
3. With `Object[]` arguments, supply `int[] argTypes` on matching overloads.
4. With JavaBeans, Spring infers types from property declarations, though driver behavior on `null` should still be verified.
5. Measure performance before toggling global property `spring.jdbc.getParameterType.ignore`.

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource parameters =
    new MapSqlParameterSource()
        .addValue("id", 201L, Types.BIGINT)
        .addValue("description", null, Types.VARCHAR);
~~~

**Never flip a global flag without measuring**, because some drivers require accurate SQL types for binary/LOB or special columns. For payloads with JSON, UUID, ARRAY, BLOB, CLOB, timezones, or enums, verify vendor binding rather than forcing everything to `VARCHAR`.

### 22.1. Reusing PreparedStatements Does Not Eliminate the Need for Indexes

Batching cuts statement preparation/execution overhead, yet the database still updates the target rows. If `WHERE item_id=?` lacks an index, a 100-entry batch still triggers 100 expensive scans. With a primary key or good index, lookup cost stays low; verify with `EXPLAIN`/actual plans, lock stats, and buffer misses.

## 23. Command Ordering and Colliding Keys in the Same Batch

Suppose two updates for `itemId=201` appear in the same batch:

~~~text
InventoryUpdate(201, 11)
InventoryUpdate(202, 25)
InventoryUpdate(201, 99)
~~~

If they carry **replacement values**, the final state depends on observed execution order and concurrency. JDBC batch entries are added in order, yet across **multiple batches**, connections, workers, or broker partitions there is no global business ordering guarantee.

**Essential rules:**

- If only the latest snapshot matters, coalesce by `itemId` **using a reliable sequence/version**, not merely picking whichever item appeared later in an arbitrary list.
- If updates are **deltas** (adding/subtracting quantities), dropping an event via faulty coalescing loses sales/inventory accuracy.
- When per-aggregate ordering matters, preserve consumer partition/worker ownership or versioned optimistic updates.
- When two commands target the same item with different versions, SQL should check `expected_version` to reject stale updates.
- When retrying a batch after timeout, `SET quantity = :targetQty` is relatively more idempotent than `quantity = quantity + :delta`, yet event/version checks are still needed before claiming an exactly-once effect.

~~~sql
-- Optimistic-version variant; every entry's update count must be checked.
UPDATE inventory_projection
SET quantity=:targetQty,
    version=version+1,
    updated_at=CURRENT_TIMESTAMP
WHERE item_id=:itemId
  AND version=:expectedVersion;
~~~

`UPDATED=0` here is not automatically a SQL error. It can mean conflict, missing row, or an already-processed duplicate; check state/processed-event IDs before deciding whether to ACK or retry.

## 24. Idempotency When Kafka/JMS/HTTP Redelivers an Entire Batch

**Batching optimizes throughput; it does not replace idempotency.** If a Kafka/JMS consumer processes a 100-message batch, commits the database, and fails before committing ACK/offset, **the entire batch or a subset** can be redelivered.

A resilient design:

~~~mermaid
flowchart LR
    A["Kafka/JMS batch / HTTP batch"] --> B["Validate + dedupe by eventId"]
    B --> C["JDBC transaction"]
    C --> D["INSERT processed_event unique"]
    C --> E["UPDATE inventory"]
    C --> F["INSERT outbox if publishing"]
    D --> G[("DB COMMIT")]
    E --> G
    F --> G
    G --> H["ACK/offset per container policy"]
~~~

Processed-event table (illustrative):

~~~sql
CREATE TABLE processed_inventory_event (
    event_id VARCHAR(80) NOT NULL PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Inside **the same JDBC transaction**, each event ID is inserted/claimed to block duplicate business effects. If the marker already exists, verify it is a legitimate duplicate with identical meaning rather than blindly ignoring conflicts.

If a batch has 100 rows and 5 were already processed:
- Filter out the 5 duplicates **before** assembling a 95-entry JDBC batch.
- Or apply vendor-appropriate idempotent SQL (`INSERT ... ON CONFLICT DO NOTHING`/`MERGE`).
- Never regenerate event IDs on retry, or deduplication breaks.
- If updates must publish to Kafka afterward, write to an outbox in the same transaction so events are not lost after DB commit.

**JDBC transactions do not automatically commit Kafka offsets or JMS ACKs.** A local JDBC COMMIT can succeed before the broker ACK; redeliveries are normal and must be anticipated.

## 25. Retrying a Failed Batch: Whole Batch or Bisecting for Poison Records?

Suppose a 100-row batch has a constraint violation on entry 37. Handling depends on the error class:

| Error type | Handling approach |
|---|---|
| Transient deadlock/lock timeout | Roll back full transaction; retry batch in a fresh TX with backoff |
| Network failure near COMMIT | Outcome uncertain; reconcile using event ID/state |
| Valid unique duplicate | Apply deduplication/UPSERT policy; never retry infinitely |
| Invalid schema/SQL syntax | Halt flow, fix migration/config |
| Oversized payload or bad data | Validate, quarantine/DLQ, and manual replay |
| Version conflict (update count 0) | Reconcile state/version; do not treat as DB outage |
| Driver reports `SUCCESS_NO_INFO` | Do not assume exact count of 1 |
| Partial JDBC batch failure | Exception + local rollback; use counts for diagnostics |

### 25.1. Strategy to Isolate Poison Events

When a batch contains one malformed record, you can:
1. Roll back the batch.
2. If the error is **confirmed to be permanent bad data**, use pre-validation or controlled batch splitting (such as binary splitting) to isolate the bad record.
3. Persist a durable error/DLQ record; ACK only events whose contract completed or were safely quarantined.
4. Preserve business event IDs and audit why items were split, skipped, or retried.

**Never blindly bisect batches for retries** when commands depend on each other's ordering or shared atomicity; splitting can alter business outcomes. Never “drop the failing row and commit 99” if business rules require all 100 records to be atomic as a unit.

### 25.2. Never Retry Directly on an Aborted Transaction

In PostgreSQL, once a statement puts a transaction into an aborted state, subsequent SQL cannot proceed normally until rollback. Retries must open a **fresh transaction**. After a deadlock, row lists, ownership, versions, and pending states may have changed: re-read current state instead of assuming cached IDs are still claimed.

## 26. Connections, Transactions, Channels, and Timeouts

Bottlenecks do not live solely in SQL. A batch holds a JDBC connection for the duration of its transaction; if many batches run concurrently, the Hikari pool can starve.

| Setting | Layer | Impact |
|---|---|---|
| `spring.datasource.hikari.maximum-pool-size` | JDBC pool | Max concurrent connections |
| `connection-timeout` | JDBC pool | Wait time to acquire a connection |
| `JdbcTemplate#setQueryTimeout` | JDBC statement | Driver-level query execution cap |
| `@Transactional(timeout=...)` | JDBC transaction | Unit-of-work deadline |
| `maxMessagesPerPoll` | Poller | `receive()`/query calls per trigger |
| `batch size` and max wait | Aggregator/app buffer | Throughput vs. latency/memory |
| Executor pool/queue size | Async channel | Concurrency and backpressure |
| Kafka/JMS ACK timeout | Broker/container | Distinct from JDBC transaction timeout |

**With `DirectChannel`**, the handler runs on the sender thread and can join the active transaction. **With `ExecutorChannel` or `QueueChannel`**, thread-bound transactions do not propagate. If the batch JDBC adapter runs on another worker, open a transaction **on that worker** or durably stage data before handoff.

~~~text
Transactional poller BEGIN
  -> JDBC inbound SELECT/UPDATE
  -> DirectChannel
  -> JdbcMessageHandler batchUpdate
Transactional poller COMMIT/ROLLBACK

--- Inserting ExecutorChannel ---

Poller BEGIN -> inbound UPDATE -> ExecutorChannel.send -> Poller COMMIT
                                               |
                                               v
                                   Worker batchUpdate (separate TX)
~~~

If the worker fails after the poller commits, rolling back the worker **does not** revert `CLAIMED` state at the source. You need leases/recovery or an outbox.

JDBC is **blocking I/O**. In WebFlux applications, never run `JdbcTemplate` batches directly on the Reactor Netty event loop; offload the entire JDBC transaction to an appropriate worker, or use a reactive database under its own contract.

## 27. Diagnosing Performance with Metrics Instead of SQL Logs Alone

Good observability should answer:
- How many entries are in each batch, and how many rows actually changed?
- Is `batchUpdate()` spending time in **DB execution**, **connection acquisition**, or **queue wait**?
- Is the JDBC driver actually batching, or falling back to per-statement round trips?
- Are excessive unique constraints, indexes, or triggers causing write amplification?
- Do large batch sizes inflate p99 transaction durations or lock waits?
- Is the system triggering a retry storm when the DB drops?

### 27.1. Recommended Metrics

| Metric | Interpretation |
|---|---|
| `jdbc_batch_size` | Histogram of actual entries per batch |
| `jdbc_batch_duration` | Execution duration of `batchUpdate` |
| `jdbc_batch_failures` | Failed batches categorized by SQLState/vendor code |
| `rows_updated_known` | Sum of non-negative counts when driver reports exact counts |
| `success_no_info_count` | Succeeded entries with unknown affected row counts |
| `batch_queue_wait` | Time from event arrival to batch flush |
| `transaction_duration` | Duration holding connections and locks |
| `hikari_connections_pending` | Threads waiting for a connection |
| `db_lock_wait` / deadlocks | Contention affecting tail latency |
| `outbox_pending_age` | Backlog risk when broker slows down |
| `duplicate_event_filtered` | Level of redelivery/idempotency activity |

Logs/traces should include `batchId`, event count, correlation ID, query class, elapsed time, and exception type. Never log 500 full JSON payloads containing PII or tokens. Never put per-event `eventId`s into high-cardinality metric labels.

### 27.2. Controlled Benchmark Matrix

| Test variable | Sample levels | Held constant |
|---|---|---|
| Batch size | 1, 10, 50, 100, 250, 500 | Dataset and SQL |
| Concurrency | 1, 2, 4, 8 workers | Pool, batch size |
| Driver rewrite | OFF/ON | Driver version, SQL, workload |
| Indexes | baseline/optimized | Hardware and data volume |
| Transaction scope | per event/per batch | Isolation and replay policy |
| Message assembly | Pre-built List/Aggregator | Actual batch size, max wait |

Include warm-up, sufficient run duration, multiple repetitions, and capture p95/p99 alongside error rates; report CPU, network, and DB resource limits. Comparing in-memory H2 against production PostgreSQL **yields invalid conclusions** about database batch latency.

## 28. Unit Testing Spring JDBC Batch Updates

To verify binding and row-count semantics in a controlled environment, test against the H2 schema from section 4.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class NamedInventoryBatchRepositoryTest {

    @Autowired
    NamedInventoryBatchRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void updatesThreeExistingRows() {
        int[] counts = repository.update(List.of(
            new InventoryUpdate(201, 11),
            new InventoryUpdate(202, 25),
            new InventoryUpdate(203, 34)));

        assertEquals(3, counts.length);

        Integer quantity = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=?",
            Integer.class, 201L);

        assertEquals(11, quantity);
    }
}
~~~

This test assumes `schema.sql` seeded three rows as shown, no background poller modifies the table simultaneously, and the test JDBC driver is compatible. `int[]` may contain `SUCCESS_NO_INFO` instead of exact counts; tests should not hardcode `assertArrayEquals(new int[]{1,1,1}, ...)` across all drivers.

### 28.1. Rolling Back the Entire Batch in One Transaction

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class InventoryBatchRollbackTest {

    @Autowired
    NamedInventoryBatchRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void exceptionRollsBackBatch() {
        int before = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=201",
            Integer.class);

        TransactionTemplate tx = new TransactionTemplate(manager);

        assertThrows(IllegalStateException.class,
            () -> tx.executeWithoutResult(status -> {
                repository.update(List.of(
                    new InventoryUpdate(201, 999),
                    new InventoryUpdate(202, 888)));
                throw new IllegalStateException(
                    "Simulated failure before COMMIT");
            }));

        int after = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=201",
            Integer.class);

        assertEquals(before, after);
    }
}
~~~

**Do not slap `@Transactional` onto a test method just to make code pass easily.** Spring Test rolls back test transactions at the end, masking whether the production flow actually commits properly. The `TransactionTemplate` test above queries outside the transaction to verify rollback cleanly.

## 29. Integration Testing the JDBC Outbound Adapter with a List Payload

Test goal: verify that **one message containing `List<InventoryUpdate>`** reaches `JdbcMessageHandler` and updates all three rows.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class JdbcBatchOutboundAdapterTest {

    @Autowired
    @Qualifier("inventoryBatchInput")
    MessageChannel batches;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void iterablePayloadUpdatesAllRows() {
        boolean sent = batches.send(
            MessageBuilder.withPayload(List.of(
                new InventoryUpdate(201, 11),
                new InventoryUpdate(202, 25),
                new InventoryUpdate(203, 34)))
            .build());
        assertTrue(sent);

        Integer actual = jdbc.queryForObject(
            "SELECT quantity FROM inventory_projection "
          + "WHERE item_id=203",
            Integer.class);
        assertEquals(34, actual);
    }
}
~~~

This is an integration test **of the section 8 Java DSL configuration** in an isolated context without simultaneously enabling `LegacyJdbcBatchConfiguration` (section 9), the inbound flow (section 17), or another poller mutating the same fixtures. `MessageChannel.send` plus SELECT verify the mutation occurred on a synchronous `DirectChannel`, though they **do not measure exact JDBC driver round trips**. To confirm driver batching, use an appropriate datasource-proxy or SQL metrics rather than relying on one driver's log format.

## 30. Testing Single-Entry Failures, Concurrency, and Driver Rewrites

| Scenario | Expectation |
|---|---|
| 100 valid rows in batch | Updated per policy; counts match driver behavior |
| Batch has a nonexistent item ID | Update count 0; policy does not silently ACK |
| Batch has an entry violating CHECK/UNIQUE | Exception raised; transaction rolls back if configured |
| Driver returns `SUCCESS_NO_INFO` | Does not assume 0 or 1 affected row |
| Driver continues after `BatchUpdateException` | Inspects partial counts while rolling back whole TX if required |
| JDBC outbound enables `keysGenerated` | Does not enter auto `Iterable` batch mode |
| `.split()` before `JdbcMessageHandler` | List-wide auto-batching no longer applies |
| `ExecutorChannel` after inbound claim | Poller TX does not roll back on worker failure |
| Batch retried after COMMIT before ACK | Stable IDs / idempotent effects prevent duplicates |
| Two updates for same itemId in one batch | Explicit ordering/version semantics |
| 500 entries with nullable params | Verifies typed nulls and metadata overhead |
| PostgreSQL `rewriteBatchedInserts` ON/OFF | Benchmarked only with eligible INSERTs |
| MySQL `rewriteBatchedStatements` ON/OFF | Checks correctness, counts, and packet limits |
| Large batch with small pool | Avoids lock timeouts and retry storms |
| Deadlock retry | Rolls back, opens a fresh transaction, applies backoff |
| Poller inbound UPDATE before outbound batch fails | Same TX rolls back; async needs recovery |

To verify real PostgreSQL/MySQL/SQL Server/Oracle behavior, use **Testcontainers or a vendor-matched test DB** with production-like network latency. Never use H2 to draw conclusions about statement rewriting, batch packet limits, deadlocks, or driver-specific count codes.

## 31. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “A List payload equals a driver batch” | Only when the handler/service uses a JDBC batch API |
| “Inbound `maxRows=100` equals a JDBC batch of 100 updates” | It caps SELECT results; update strategy is separate |
| “`updatePerRow(true)` always calls `executeBatch`” | It performs per-row updates, not automatically driver-batched |
| “`UPDATE ... IN (:ids)` is `batchUpdate`” | It is one set-based SQL statement |
| “`JdbcMessageHandler` auto-batches Java array payloads” | Auto-batching checks for `Iterable` |
| “A splitter before the outbound adapter increases batching” | It splits an `Iterable` into separate messages |
| “`keysGenerated=true` still batches `Iterable`s” | Batch mode does not support generated keys |
| “The outbound adapter returns per-row counts” | One-way handlers provide no such reply |
| “`SUCCESS_NO_INFO=-2` means a failed update” | It means success with unknown row count |
| “`EXECUTE_FAILED=-3` just means 0 affected rows” | It is a failure code in batch exceptions |
| “One failing entry auto-rolls back the batch under autocommit” | Requires configuring a JDBC transaction |
| “`@Transactional` runs automatically on self-invocation” | Proxies are bypassed on self-calls |
| “`ExecutorChannel` preserves the poller's transaction” | Transactions do not cross to executor threads automatically |
| “A batch commits atomically with Kafka offsets” | Local JDBC transactions are not XA by default |
| “Batch 100 is always faster than batch 10” | Depends on SQL, driver, DB, SLA, and load |
| “Batch size equals connection count” | Batch size is distinct from pool size and concurrency |
| “PostgreSQL `rewriteBatchedInserts` optimizes every UPDATE” | It targets eligible INSERTs |
| “Retrying a batch cannot create duplicates” | Uncertain ACKs/outcomes still require idempotency |
| “SQL UPDATE count 0 always indicates a network error” | Can be a missing row or version conflict |
| “JDBC batching is non-blocking” | JDBC remains blocking I/O |

## 32. Practice Exercises

1. Create `inventory_projection`, `incoming_inventory_change`, and `inventory_outbox` and insert sample data.
2. Run 100 individual `JdbcTemplate.update` calls and record baseline latency against a real DB.
3. Replace with `JdbcTemplate.batchUpdate` and `BatchPreparedStatementSetter`; measure throughput and update counts.
4. Try `NamedParameterJdbcTemplate.batchUpdate` with `MapSqlParameterSource[]`.
5. Try `SqlParameterSourceUtils.createBatch(...)` and inspect JavaBean/record mapping.
6. Use the `batchUpdate(sql, Collection, 100, pss)` overload for 230 rows; inspect `int[][]`.
7. Handle `Statement.SUCCESS_NO_INFO` without accidentally adding -2 to row totals.
8. Throw an exception after a batch inside `TransactionTemplate` and verify rollback.
9. Trigger a constraint violation on a middle entry; inspect `BatchUpdateException`/cause chain and transaction outcome.
10. Configure Spring Integration 7.x Java DSL `Jdbc.outboundAdapter` with `MessagePreparedStatementSetter`.
11. Send a `Message<List<InventoryUpdate>>` and verify the handler updates all rows.
12. Insert `.split()` before the handler and compare JDBC batch execution counts.
13. Wire `JdbcMessageHandler` directly in Spring Integration 6.x or XML `int-jdbc:outbound-channel-adapter`.
14. Enable `keysGenerated` in a practice config and explain why batch mode cannot be used.
15. Build an inbound JDBC poller with `maxRows=100` and contrast it with `maxMessagesPerPoll=1`.
16. Compare inbound `updatePerRow(false)` vs. `updatePerRow(true)` and count SQL executions.
17. Chain inbound JDBC to outbound batching inside the same transactional poller and `DirectChannel`; inject an error to verify both tables roll back.
18. Insert an `ExecutorChannel` before the outbound handler; describe recovery when inbound already marked `CLAIMED`.
19. Use a size/timeout `Aggregator` to group single messages into a `List`; verify the released payload is an `Iterable`.
20. Benchmark batch sizes `1, 10, 50, 100, 250, 500` on PostgreSQL measuring p95/p99, DB CPU, lock waits, and pool waits.
21. Compare PostgreSQL `reWriteBatchedInserts=true/false` on eligible batch INSERTs.
22. Compare MySQL `rewriteBatchedStatements=true/false` and update counts with `ON DUPLICATE KEY UPDATE`.
23. Add nullable parameters, specify `Types.VARCHAR/BIGINT`, and measure metadata lookup overhead.
24. Send two commands for the same `itemId` with differing expected versions; verify ordering/conflict handling.
25. Redeliver duplicate Kafka/JMS events after DB COMMIT before ACK; use a processed-event UNIQUE constraint to protect effects.
26. Process a 100,000-row input using paged reads and bounded batches rather than loading everything into RAM.
27. Replace a JDBC batch with a staging table + set-based UPDATE on PostgreSQL and compare performance and correctness.
28. Build a dashboard for batch size, duration, failures, `SUCCESS_NO_INFO`, queue wait, outbox age, and Hikari pending connections.
29. Write a runbook for handling a poison event inside a batch, separating transient retries, quarantine, and manual replay.
30. Write tests on a production-compatible DB covering driver batching, transactions, and crash windows.

**Comprehensive scenario:** a Kafka consumer receives 500 inventory updates per poll and wants to batch them in JDBC batches of size 100. In the third batch, one record has invalid data; the DB processed several entries before JDBC threw an error. After fixing the data, the consumer restarts right as the transaction commits while the Kafka offset has not yet committed. Design the **transaction boundaries, update count handling, `eventId` deduplication, partial-batch policy, timeouts, retry/ACK logic, and metrics** so no events are lost, no wrong inventory is silently written, and no retry storm occurs.

## 33. References

- [Spring Integration Reference — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): `JdbcMessageHandler` handling `Iterable` payloads with `JdbcOperations.batchUpdate()` since 5.1, `MessagePreparedStatementSetter`, `keysGenerated` limitation.
- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): `List` payloads, `maxRows`, `maxMessagesPerPoll`, update SQL, `updatePerRow`, and transactional pollers.
- [Spring Integration Reference — Java DSL for JDBC](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.outboundAdapter` and `Jdbc.inboundAdapter` from 7.0.
- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `UPDATED` replies vs. one-way outbound adapters, generated keys, and SELECT replies.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): `BatchPreparedStatementSetter`, `NamedParameterJdbcTemplate.batchUpdate`, `SqlParameterSourceUtils`, `ParameterizedPreparedStatementSetter`, and `int[][]`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, named params, JDBC types, `JdbcClient`.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, channel synchronization, and thread boundaries.
- [Java SE API — Statement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Statement.html): JDBC batch update counts, `SUCCESS_NO_INFO`, `EXECUTE_FAILED`.
- [Java SE API — BatchUpdateException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/BatchUpdateException.html): partial update counts when a batch entry fails.
- [PostgreSQL JDBC Driver Documentation](https://jdbc.postgresql.org/documentation/use/): connection parameters, `reWriteBatchedInserts`, and JDBC driver behavior.
- [MySQL Connector/J — Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html): `rewriteBatchedStatements`, generated keys/count limitations, and packet considerations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, rollback rules, proxies, and propagation.

> **Remember:** Improving JDBC performance in Spring Integration requires **distinguishing message batches, JDBC driver batches, and set-based SQL statements**. `JdbcMessageHandler` batches when given an `Iterable` payload (without `keysGenerated`); `JdbcTemplate.batchUpdate` gives explicit control over parameter sets, chunk sizes, and update counts. Inbound `maxRows` differs from poller `maxMessagesPerPoll`; `updatePerRow` is not automatic driver batching. Optimization only pays off when measured on the real DB/driver, placed inside proper transactions, and backed by bounded buffers, retries, outboxes, and idempotent handling for redelivered batches.

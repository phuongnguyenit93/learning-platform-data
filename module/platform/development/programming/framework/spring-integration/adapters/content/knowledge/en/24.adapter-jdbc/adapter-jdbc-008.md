# UpdateSqlParameterSource and Expressions in Spring Integration JDBC

## 1. Problem Statement: SELECT a Batch of Records Then UPDATE Those Exact Records

An integration application may read orders from a database, normalize the data, and forward them to Kafka, JMS, AMQP, or HTTP. Instead of repeatedly reading the same records, a **JDBC inbound channel adapter** typically performs two steps on each poll:

1. Execute a `SELECT` query to fetch eligible records, such as events with `state = 'NEW'`.
2. Execute an `UPDATE` statement to mark **those exact fetched records** as `CLAIMED`, preventing them from being picked again on the next poll.

The challenge is that the `UPDATE` statement needs the list of IDs from the **`SELECT` result**, not a fixed parameter hardcoded in configuration. `SqlParameterSourceFactory`—specifically the **`updateSqlParameterSourceFactory`** property on the JDBC inbound adapter—solves converting query results into SQL parameters. When mapping rules are more involved, we can use **`ExpressionEvaluatingSqlParameterSourceFactory`** to compute parameters with **SpEL expressions**.

This topic belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, where we connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`. The module also covers files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; here the focus is the **SELECT → UPDATE → message contract**, mapping, transactions, errors, and connection lifecycles.

~~~mermaid
flowchart LR
    P["Poller"] --> I["JDBC inbound adapter"]
    I --> S["SELECT NEW rows"]
    S --> R["List<Row> or List<DTO>"]
    R --> F["SqlParameterSourceFactory"]
    F --> U["UPDATE ... WHERE id IN (:ids)"]
    U --> D[("Database")]
    R --> M["Message<List<Row>>"]
    M --> X["Splitter if needed"]
    X --> N["Kafka / JMS / handler"]
~~~

**Learning objectives:** understand the default `:id` parameter convention, know when a custom `SqlParameterSourceFactory` is needed, distinguish SpEL expressions from SQL placeholders, choose between `updatePerRow(false/true)`, configure `selectSqlParameterSource` separately, test transactions, and recognize the limits of the “read-then-mark” pattern.

## 2. Responsibility Contract of Each Component

| Component | Role | What it does not do automatically |
|---|---|---|
| `JdbcPollingChannelAdapter` | Executes SELECT, optionally executes UPDATE after SELECT, returns list payload | Does not guarantee exactly-once between DB and Kafka |
| `RowMapper<T>` | Converts **one** `ResultSet` row into `T` | Does not create a separate message per row |
| `SqlParameterSource` | Supplies values/SQL types for `:param` names | Does not execute SQL |
| `SqlParameterSourceFactory` | Creates a `SqlParameterSource` from input on each call | Not a message payload transformer |
| `ExpressionEvaluatingSqlParameterSourceFactory` | Maps SQL param names to SpEL expressions | Does not turn every `:param` into SpEL automatically |
| `updatePerRow` | Chooses per-row vs. whole-batch parameter scope | Does not create a separate transaction per row |
| `selectSqlParameterSource` | Provides parameters for SELECT before results exist | Does not receive the List of rows from the upcoming query |
| Poller/transaction manager | Controls polling schedule and transaction scope | Does not commit atomically with brokers/HTTP |

Conceptual data flow:

~~~text
DataSource / JdbcTemplate
  SELECT ... WHERE state = 'NEW'
    -> List<Map<String,Object>> or List<EventRow>
      -> updateSqlParameterSourceFactory.createParameterSource(input)
        -> SqlParameterSource: {"ids": [101,102,103]}
          -> UPDATE ... WHERE id IN (:ids)
      -> Message<List<EventRow>>
        -> Splitter, Filter, Router, Service Activator ...
~~~

This is an explanatory model, not a guarantee of internal call ordering across all versions. What remains invariant is: **UPDATE obtains parameters from the SELECTed data**, while the outbound message carries the queried rows as its payload (after `RowMapper` if configured).

## 3. No Custom Factory Needed: The Default `:id` Parameter Convention

The Spring Integration JDBC inbound adapter supports a very convenient default rule: a column named `id` in the SELECT result is **projected into a list of values** for the `:id` parameter in the UPDATE statement.

Example XML configuration:

~~~xml
<!-- XML fragment; assumes int and int-jdbc namespaces are declared. -->
<int:channel id="eventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="pendingEventPoller"
    data-source="dataSource"
    channel="eventBatches"
    query="SELECT id, event_key, state
           FROM sync_event
           WHERE state = 'NEW'
           ORDER BY id"
    update="UPDATE sync_event
            SET state = 'CLAIMED'
            WHERE id IN (:id) AND state = 'NEW'">

    <int:poller fixed-delay="5000"
                max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

If SELECT retrieves rows with IDs `101, 102, 103`, the value bound to `:id` is a collection `[101, 102, 103]`. Spring JDBC's **named parameter support** handles expanding the collection into `IN (...)`.

~~~text
SELECT rows: [{id:101,...},{id:102,...},{id:103,...}]
    |
Default creates SqlParameterSource with key "id"
    |
id = [101,102,103]
    |
UPDATE ... WHERE id IN (:id)
~~~

**`:id` is not “embedding SpEL into SQL”.** It is a parameter name handled by Spring JDBC, paired with Spring Integration's convention for extracting properties/columns from the result list. For complex names/paths, or when combining multiple fields and converting types, use an explicit factory rather than placing arbitrary SpEL expressions directly after the colon.

**Important limitation:** this convention does not resolve contention between two pods selecting the same `NEW` row. Nor does it dictate what happens if UPDATE affects 0 rows because another instance just claimed them first.

## 4. Distinguishing SELECT Params and UPDATE Params

An inbound poll involves **two SQL statements** with two distinct parameter sources:

| SQL | When executed | Where do parameters come from? |
|---|---|---|
| `SELECT ... WHERE state = :wantedState` | Before rows exist | `selectSqlParameterSource`, a parameter source reused across polls |
| `UPDATE ... WHERE id IN (:ids)` | After rows are SELECTed | `updateSqlParameterSourceFactory`, creating parameter sources from **SELECT results** |
| `UPDATE ... WHERE id = :rowId` with `updatePerRow(true)` | For each SELECTed row | Factory receives **one row** at a time |

Do not configure `selectSqlParameterSource` thinking it will supply `:ids` from rows **not yet SELECTed**. Conversely, do not try to use `updateSqlParameterSourceFactory` as the parameter source for the SELECT query.

### 4.1. Evaluation Root Reference Table

| Evaluation site | SpEL `#root` object |
|---|---|
| Inbound UPDATE, `updatePerRow(false)` | **List of SELECT results** |
| Inbound UPDATE, `updatePerRow(true)` | **Single row** from the SELECT result |
| Inbound SELECT with `createParameterSourceNoCache(root)` | **Root object you supply**, not a message or rows |
| Outbound JDBC adapter using expression factory | Typically the incoming **`Message<?>`** (payload + headers) |

This is one of the easiest things to confuse when using `ExpressionEvaluatingSqlParameterSourceFactory` on both inbound and outbound endpoints: **the evaluation root depends on the endpoint and processing mode**, not just the class name.

## 5. Setting Up the Practice Environment and Table

Examples use Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC, and H2 to make post-SELECT UPDATE effects easy to observe.

~~~groovy
// build.gradle - Spring Boot dependency management controls versions
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml for H2 demo
spring:
  datasource:
    url: "jdbc:h2:mem:sql_parameter_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Suppose `src/main/resources/schema.sql` in the practice application contains:

~~~sql
CREATE TABLE sync_event (
    id             BIGINT NOT NULL PRIMARY KEY,
    event_key      VARCHAR(80) NOT NULL UNIQUE,
    event_type     VARCHAR(80) NOT NULL,
    state          VARCHAR(24) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_at     TIMESTAMP NULL
);

INSERT INTO sync_event (id, event_key, event_type, state, attempt_count)
VALUES (101, 'evt-101', 'order.created', 'NEW', 0),
       (102, 'evt-102', 'order.paid', 'NEW', 0),
       (103, 'evt-103', 'order.shipped', 'NEW', 1),
       (104, 'evt-104', 'order.cancelled', 'CLAIMED', 1);
~~~

**The following examples are alternatives**—do not enable all pollers simultaneously: running multiple flows reading `state='NEW'` concurrently causes them to compete and makes learning results unpredictable. H2 is convenient for mapping demos; locking, `SKIP LOCKED`, batch counts, and transaction behavior must be verified against the production DB.

## 6. Java DSL 7.x: Updating by ID List with a Custom Factory

Since **Spring Integration 7.0**, the JDBC module includes the Java DSL `org.springframework.integration.jdbc.dsl.Jdbc`. `JdbcInboundChannelAdapterSpec` provides `rowMapper(...)`, `maxRows(...)`, `updateSql(...)`, `updatePerRow(...)`, `updateSqlParameterSourceFactory(...)`, and `selectSqlParameterSource(...)`.

### 6.1. DTO and RowMapper

~~~java
package com.example.integration;

import java.time.LocalDateTime;

public record EventRow(
    long id, String eventKey, String eventType,
    String state, int attemptCount, LocalDateTime createdAt) {
}
~~~

~~~java
package com.example.integration;

import org.springframework.jdbc.core.RowMapper;

public final class EventRowMapper implements RowMapper<EventRow> {
    @Override
    public EventRow mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {
        return new EventRow(
            rs.getLong("id"),
            rs.getString("event_key"),
            rs.getString("event_type"),
            rs.getString("state"),
            rs.getInt("attempt_count"),
            rs.getTimestamp("created_at").toLocalDateTime());
    }
}
~~~

`id`, `attempt_count`, and `created_at` are all NOT NULL in the demo schema. If production allows NULLs, use boxed Java wrappers or check `rs.wasNull()` / null timestamps before calling `toLocalDateTime()`.

### 6.2. SELECT, Bind ID List, UPDATE, Emit Messages

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
public class EventBatchPollingFlow {

    @Bean
    public IntegrationFlow pollNewEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_key, event_type, state,
                   attempt_count, created_at
            FROM sync_event
            WHERE state = 'NEW'
            ORDER BY id
            """;

        String updateSql = """
            UPDATE sync_event
            SET state = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP,
                attempt_count = attempt_count + 1
            WHERE id IN (:selectedIds) AND state = 'NEW'
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(new EventRowMapper())
                    .maxRows(25)
                    .updateSql(updateSql)
                    .updatePerRow(false)
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(EventRow.class::cast)
                            .map(EventRow::id)
                            .toList();
                        return new MapSqlParameterSource(
                            "selectedIds", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
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

**What happens when SELECT returns three rows `101, 102, 103`:**

1. `RowMapper` maps each row to an `EventRow`.
2. `updatePerRow(false)` causes the factory to receive **the entire `List<EventRow>`**.
3. The lambda creates a `MapSqlParameterSource` with `selectedIds = [101,102,103]`.
4. `NamedParameterJdbcTemplate` binds `:selectedIds` in the `IN (...)` clause and updates the matching rows.
5. The source emits **one message containing `List<EventRow>`**; `split()` splits it into three messages sent to `claimedEvents`.

**Note:** the `EventRow.state` payload field was mapped from SELECT before UPDATE ran, so in the DTO it may still read `NEW` even though the database was updated to `CLAIMED`. If downstream needs the new status, apply an explicit domain/transformer rule; do not assume `RowMapper` re-reads the updated row automatically.

`updateSqlParameterSourceFactory(result -> ...)` is a `SqlParameterSourceFactory` functional interface. It receives the **SELECT result**, not an incoming `Message<?>` from a caller like a JDBC outbound handler. A Java lambda itself is **an alternative** to an expression factory, especially when avoiding SpEL syntax dependencies.

### 6.3. Consumer Receiving Each Row After the Splitter

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class ClaimedEventConsumer {
    @ServiceActivator(inputChannel = "claimedEvents")
    public void process(EventRow event) {
        System.out.printf("Process event %s from DB%n", event.eventKey());
    }
}
~~~

`System.out.printf` is for demo only. In production, a log entry **is not an ACK receipt** from Kafka/JMS, nor does it confirm durable business processing. Design ACKs, outbox, retries, and idempotency separately.

## 7. What Is the Difference Between `updatePerRow(false)` and `updatePerRow(true)`?

`JdbcPollingChannelAdapter#setUpdatePerRow(boolean)` defaults to **false**.

| Attribute | `false` (default) | `true` |
|---|---|---|
| Argument passed to factory | **List of SELECT rows** | **One row** at a time |
| Typical SQL | `WHERE id IN (:ids)` | `WHERE id = :rowId` |
| Number of UPDATE statements | Usually one UPDATE for the batch | Potentially one UPDATE per row |
| Best suited for | Marking the same state for the whole batch | Rows needing row-specific UPDATE values |
| SpEL `#root` | List | Row (Map or mapped DTO) |
| DB cost | Fewer SQL round trips, potentially long parameter list | More SQL executions and round trips |
| Delivery guarantee | Not built-in | Also not built-in |

Example with 3 rows:

~~~text
updatePerRow(false):
  input to factory = [row101, row102, row103]
  UPDATE ... WHERE id IN (101,102,103)

updatePerRow(true):
  input to factory = row101  -> UPDATE ... WHERE id = 101
  input to factory = row102  -> UPDATE ... WHERE id = 102
  input to factory = row103  -> UPDATE ... WHERE id = 103
~~~

**Do not confuse update-per-row with “one transaction per row”.** Transactions are governed by the poller/transaction manager. When a transaction wraps the poll operation, multiple per-row updates can still belong to the same transaction; verify rollback and locking behavior on your target database.

## 8. ExpressionEvaluatingSqlParameterSourceFactory: SpEL per Row

When you prefer not to write a mapping lambda, Spring Integration provides `ExpressionEvaluatingSqlParameterSourceFactory`. The SQL parameter name stays a simple `:rowId`, while the **SpEL expression** is configured on the factory.

With `updatePerRow(true)` and row Maps containing `id`/`event_key`, `#root['id']` reads the ID of the **current row**.

### 8.1. Creating the Expression Factory Bean

~~~java
package com.example.integration;

import java.sql.Types;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;

@Configuration
public class EventSqlParameterConfiguration {

    @Bean("perRowUpdateParameters")
    public ExpressionEvaluatingSqlParameterSourceFactory
            perRowUpdateParameters() {

        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "rowId", "#root['id']",
            "nextState", "'CLAIMED'"));
        factory.setSqlParameterTypes(Map.of(
            "rowId", Types.BIGINT,
            "nextState", Types.VARCHAR));
        return factory;
    }
}
~~~

**Explanation:**

- `"rowId"` is the **SQL** parameter name in `WHERE id = :rowId`.
- `"#root['id']"` is **SpEL** reading key `id` from the Map passed by the adapter into the factory.
- `"'CLAIMED'"` is a SpEL string literal, not a bean or property named `CLAIMED`.
- `setSqlParameterTypes(...)` declares JDBC types when drivers cannot infer them accurately or when explicit binding control is needed; available since Spring Integration 5.0.
- Being Spring-managed gives the factory lifecycle/bean resolution support if expressions reference `@beanName`.

### 8.2. Attaching the Factory to the Inbound Adapter

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PerRowExpressionFlow {

    @Bean
    public IntegrationFlow pollAndUpdatePerRow(
            DataSource dataSource,
            PlatformTransactionManager transactionManager,
            @Qualifier("perRowUpdateParameters")
            ExpressionEvaluatingSqlParameterSourceFactory params) {

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource,
                    "SELECT id, event_key, state FROM sync_event "
                  + "WHERE state = 'NEW' ORDER BY id")
                    .maxRows(10)
                    .updatePerRow(true)
                    .updateSql(
                        "UPDATE sync_event "
                      + "SET state = :nextState, "
                      + "    claimed_at = CURRENT_TIMESTAMP "
                      + "WHERE id = :rowId AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(params),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .channel("perRowEventBatches")
            .get();
    }
}
~~~

**Payload contract:** this snippet declares no `rowMapper(...)`, so each row in the `List` defaults to a Spring JDBC `Map`. Verify column/key names on your actual driver, especially when relying on `#root['id']`. For databases whose column labels differ in casing, use explicit aliases or a custom `RowMapper`/parameter factory.

This is an **alternative** to the flow in section 6; do not enable both pollers reading `sync_event` in a simple test.

### 8.3. When Is an Expression Factory a Good Choice?

SpEL works well when reading nested properties, combining fields, invoking a Spring-managed bean, or coercing types declaratively. When mapping requires complex validation or multi-step logic, an explicit Java `SqlParameterSourceFactory` is usually easier to debug and unit-test.

**Never use SpEL to turn table or column names into uncontrolled dynamic SQL.** Named parameters bind **values**; SQL identifiers must come from trusted allowlists/configs.

## 9. Expressions for the Whole List with `updatePerRow(false)`

SpEL also supports **collection projection** when the root is a list. With SELECT results composed of Maps having key `id`, `#root.![#this['id']]` produces a list of IDs from all rows.

~~~java
@Bean("listUpdateParameters")
ExpressionEvaluatingSqlParameterSourceFactory listUpdateParameters() {
    var factory = new ExpressionEvaluatingSqlParameterSourceFactory();
    factory.setParameterExpressions(java.util.Map.of(
        "ids", "#root.![#this['id']]"));
    factory.setSqlParameterTypes(java.util.Map.of(
        "ids", java.sql.Types.BIGINT));
    return factory;
}
~~~

Corresponding Java DSL fragment:

~~~java
Jdbc.inboundAdapter(dataSource,
        "SELECT id, event_key, state FROM sync_event "
      + "WHERE state = 'NEW' ORDER BY id")
    .maxRows(25)
    .updatePerRow(false)
    .updateSql(
        "UPDATE sync_event SET state = 'CLAIMED' "
      + "WHERE id IN (:ids) AND state = 'NEW'")
    .updateSqlParameterSourceFactory(listUpdateParameters)
~~~

`listUpdateParameters` is an initialized `ExpressionEvaluatingSqlParameterSourceFactory` bean; this is a **DSL fragment** placed inside an `IntegrationFlow`. With three rows, the expression produces `ids=[101,102,103]`.

**Typing caveat:** collection projection depends on row structure. If `RowMapper` turns Maps into Java records, replace `#this['id']` with appropriate property access (or use a lambda factory as in section 6). An expression valid in per-row mode breaks immediately when switched to list mode, and vice versa.

### 9.1. Why `:ids` Is Not SpEL

~~~text
SQL:  WHERE id IN (:ids)
                 |
Placeholder name for NamedParameterJdbcTemplate
                 |
Factory: "ids" -> SpEL "#root.![#this['id']]"
                 |
SqlParameterSource: {ids=[101,102,103]}
~~~

SpEL is the **factory's configuration value**. SQL merely references the parameter name; they are two separate languages. Because Spring named-parameter SQL does not permit arbitrary SpEL characters inside parameter names, this separation is both clear and maintainable.

## 10. Does SqlParameterSourceFactory Have to Use SpEL?

No. `SqlParameterSourceFactory` in `org.springframework.integration.jdbc` is a functional interface with a single method:

~~~java
package org.springframework.integration.jdbc;

import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@FunctionalInterface
public interface SqlParameterSourceFactory {
    SqlParameterSource createParameterSource(Object input);
}
~~~

You can use a Java lambda or dedicated class:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.integration.jdbc.SqlParameterSourceFactory;

SqlParameterSourceFactory factory = input -> {
    if (!(input instanceof List<?> rows)) {
        throw new IllegalArgumentException("Expected list of SQL rows");
    }
    List<Long> ids = rows.stream()
        .map(row -> (Map<?, ?>) row)
        .map(row -> ((Number) row.get("id")).longValue())
        .toList();
    return new MapSqlParameterSource("ids", ids);
};
~~~

This snippet assumes each map contains key `id`; use explicit aliases in SELECT and test with your actual driver. With an `EventRow` record, extracting `EventRow::id` as in section 6 is usually safer than casting Maps.

**Selection rule:**

- Short mapping best expressed declaratively → `ExpressionEvaluatingSqlParameterSourceFactory`.
- Mapping needing type checks, NULL normalization, collection logic, or complex validation → Java lambda/custom class.
- Default `:id` convention already fits → **no custom factory needed**.

Never allocate a new factory **per row** inside a mapper. Register a shared bean/factory and let the adapter create the appropriate `SqlParameterSource` for each UPDATE.

## 11. SELECT Parameters: `createParameterSourceNoCache`

For a SELECT query:

~~~sql
SELECT id, event_key, state
FROM sync_event
WHERE state = :wantedState
ORDER BY id;
~~~

At SELECT time, the adapter **does not yet have a result list**. Therefore it accepts `selectSqlParameterSource`—a `SqlParameterSource` reused across polls, rather than a factory driven by newly read rows.

For **constant** parameters, you can simply use:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var selectParams = new MapSqlParameterSource(
    "wantedState", "NEW");
~~~

If a parameter must be recomputed between polls—such as from a bean `@pollStateProvider.currentState()`—use `ExpressionEvaluatingSqlParameterSourceFactory.createParameterSourceNoCache(...)` to avoid caching stale values.

~~~java
package com.example.integration;

import java.sql.Types;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@Configuration
public class SelectSqlParameterConfiguration {

    @Bean("selectExpressionFactory")
    public ExpressionEvaluatingSqlParameterSourceFactory
            selectExpressionFactory() {
        var factory =
            new ExpressionEvaluatingSqlParameterSourceFactory();
        factory.setParameterExpressions(Map.of(
            "wantedState", "@pollStateProvider.currentState()"));
        factory.setSqlParameterTypes(Map.of(
            "wantedState", Types.VARCHAR));
        return factory;
    }

    @Bean("selectSqlParameters")
    public SqlParameterSource selectSqlParameters(
            @Qualifier("selectExpressionFactory")
            ExpressionEvaluatingSqlParameterSourceFactory factory) {
        return factory.createParameterSourceNoCache("");
    }
}
~~~

This requires a bean named `pollStateProvider` whose `currentState()` returns a valid state such as `NEW`. This demonstrates **SpEL referencing a Spring-managed bean**; never accept arbitrary bean names or SpEL fragments from HTTP requests.

Wiring into the DSL:

~~~java
Jdbc.inboundAdapter(dataSource,
        "SELECT id, event_key, state "
      + "FROM sync_event WHERE state = :wantedState")
    .selectSqlParameterSource(selectSqlParameters)
    .maxRows(25)
~~~

**Important caching notes:**

- `createParameterSource(input)` creates a source that can **cache evaluated parameter results**. For an UPDATE over a fixed batch, this lets the same parameter be reused without re-evaluation.
- `createParameterSourceNoCache(input)` does not cache; it fits `selectSqlParameterSource` reused across polls when values change over time.
- Because it does not cache, if `:wantedState` appears multiple times in one SELECT statement, the expression can be evaluated multiple times in a single pass. Avoid expressions with side effects or values that fluctuate mid-statement.

If state should change on a consistent cadence, consider snapshotting the value before a poll instead of calling a method whose return value might change between calls within the same SQL statement. SQL parameter expressions should be **pure and predictable**.

## 12. `updateSqlParameterSourceFactory` vs. `selectSqlParameterSource`

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as SELECT parameter source
    participant A as JdbcPollingChannelAdapter
    participant DB as Database
    participant U as UPDATE factory
    P->>A: receive()
    A->>S: getValue(:wantedState)
    S-->>A: "NEW"
    A->>DB: SELECT ... state=:wantedState
    DB-->>A: List<Row> (101,102,103)
    A->>U: createParameterSource(List<Row>)
    U-->>A: {ids:[101,102,103]}
    A->>DB: UPDATE ... id IN (:ids)
    A-->>P: Message<List<Row>>
~~~

| Question | SELECT | UPDATE |
|---|---|---|
| Result list exists beforehand? | No | Yes |
| What does the adapter accept? | `SqlParameterSource` | `SqlParameterSourceFactory` |
| Java DSL 7.x config | `selectSqlParameterSource(...)` | `updateSqlParameterSourceFactory(...)` |
| Java 6.x config | `setSelectSqlParameterSource(...)` | `setUpdateSqlParameterSourceFactory(...)` |
| SQL example | `WHERE state=:wantedState` | `WHERE id IN (:ids)` |
| Dynamic parameters | `createParameterSourceNoCache` or appropriate dynamic source | `createParameterSource(result)` per batch/row |

**Do not accidentally share a parameter source holding transaction state:** SELECT values may come from config/beans, whereas UPDATE IDs must come strictly from **rows selected in the same poll**. Reusing an ID list from a previous poll risks marking the wrong records.

## 13. `updatePerRow(true)` When Each Row Follows Different Rules

If each event needs row-specific update values, use `updatePerRow(true)` and a `SqlParameterSourceFactory` reading from each row:

~~~java
// DSL fragment: assumes SELECT payload is a Map with "id", "attempt_count".
Jdbc.inboundAdapter(dataSource,
        "SELECT id, attempt_count FROM sync_event "
      + "WHERE state='NEW' ORDER BY id")
    .maxRows(10)
    .updatePerRow(true)
    .updateSql(
        "UPDATE sync_event "
      + "SET attempt_count = :nextAttempt, state = 'CLAIMED' "
      + "WHERE id = :rowId AND state = 'NEW'")
    .updateSqlParameterSourceFactory(row -> {
        Map<?, ?> values = (Map<?, ?>) row;
        long id = ((Number) values.get("id")).longValue();
        int attempt = ((Number) values.get("attempt_count")).intValue();
        return new MapSqlParameterSource()
            .addValue("rowId", id)
            .addValue("nextAttempt", attempt + 1);
    })
~~~

`Map` and `MapSqlParameterSource` must be imported properly in a real Java file. This is a **configuration fragment**: verify column labels if using a different database driver. A counter can safely be incremented directly in SQL via `SET attempt_count = attempt_count + 1` rather than passing `nextAttempt` computed from the row; the example illustrates binding **row-computed values**, not recommending this optimistic counter pattern under concurrent workers.

**Under contention:** two pollers reading `attempt_count=1` and computing `nextAttempt=2` can cause lost updates or 0-row updates depending on predicates. If optimistic concurrency is needed, add a version predicate; if an atomic counter is needed, compute it in the database.

## 14. SQL Parameter Types, Static Parameters, and Expression Caching

`ExpressionEvaluatingSqlParameterSourceFactory` supports:

~~~java
factory.setParameterExpressions(Map.of(
    "rowId", "#root['id']",
    "normalizedKey", "#root['event_key'].toUpperCase()"));

factory.setSqlParameterTypes(Map.of(
    "rowId", java.sql.Types.BIGINT,
    "normalizedKey", java.sql.Types.VARCHAR));

factory.setStaticParameters(Map.of(
    "sourceSystem", "ERP"));
~~~

These APIs are configured on the factory before use. On expression factories, **static parameters take precedence over parameter expressions if both share the same name**. Therefore, avoid accidentally configuring the same parameter in both maps.

| Need | Approach |
|---|---|
| Uppercase `event_key` | `"#root['event_key'].toUpperCase()"` |
| Use a constant in SQL | `setStaticParameters(Map.of("sourceSystem","ERP"))` |
| Enforce BIGINT type | `setSqlParameterTypes(Map.of("rowId", Types.BIGINT))` |
| SELECT status changing over time | `createParameterSourceNoCache(...)` |
| UPDATE using one row's ID | `updatePerRow(true)` and row-root SpEL |
| UPDATE using multiple rows' IDs | `updatePerRow(false)` and list projection/lambda |

**NULL safety:** if `event_key` can be null, `.toUpperCase()` will throw. SpEL offers null-safe navigation `?.`, though null results must still satisfy SQL/DB constraints. Use proper validation/DTOs instead of silently turning corrupted data into blank keys.

## 15. XML and Direct Java Configuration for Spring Integration 6.x

In Spring Integration **6.x**, `JdbcPollingChannelAdapter` already exposes `setUpdateSqlParameterSourceFactory` and `setSelectSqlParameterSource`. Because the Java DSL factory `Jdbc.inboundAdapter(...)` arrived in **7.0**, 6.x projects can use Java beans or XML.

### 15.1. Java Configuration in 6.x

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
public class LegacyJdbcPollingFlow {

    @Bean
    public IntegrationFlow legacyEvents(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {

        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(dataSource,
                "SELECT id, event_key, state FROM sync_event "
              + "WHERE state = 'NEW' ORDER BY id");

        source.setMaxRows(25);
        source.setUpdateSql(
            "UPDATE sync_event SET state = 'CLAIMED' "
          + "WHERE id IN (:ids) AND state = 'NEW'");
        source.setUpdateSqlParameterSourceFactory(rows -> {
            var selected = (java.util.List<?>) rows;
            var ids = selected.stream()
                .map(item -> (java.util.Map<?, ?>) item)
                .map(item -> ((Number) item.get("id")).longValue())
                .toList();
            return new MapSqlParameterSource("ids", ids);
        });

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .channel("legacyEventBatches")
            .get();
    }
}
~~~

Note that the code uses Java 17+ `stream().toList()`. For Spring Integration 6.x, choose supported Spring Boot/Framework/JDK versions and check imports against actual dependencies. Because there is **no splitter** here, `legacyEventBatches` receives `Message<List<Map<...>>>`.

### 15.2. XML Using an Expression Factory

~~~xml
<!-- Fragment: declare int, int-jdbc namespaces and beans in context. -->
<bean id="perRowExpressions"
      class="org.springframework.integration.jdbc.ExpressionEvaluatingSqlParameterSourceFactory">
    <property name="parameterExpressions">
        <map>
            <entry key="rowId" value="#root['id']"/>
            <entry key="nextState" value="'CLAIMED'"/>
        </map>
    </property>
</bean>

<int:channel id="eventBatchMessages"/>

<int-jdbc:inbound-channel-adapter
    id="eventsFromJdbc"
    data-source="dataSource"
    channel="eventBatchMessages"
    query="SELECT id, event_key, state
           FROM sync_event WHERE state = 'NEW' ORDER BY id"
    update="UPDATE sync_event
            SET state = :nextState
            WHERE id = :rowId AND state = 'NEW'"
    update-per-row="true"
    sql-parameter-source-factory="perRowExpressions"
    max-rows="25">
    <int:poller fixed-delay="5000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int-jdbc:inbound-channel-adapter>
~~~

In XML, `sql-parameter-source-factory` is the **UPDATE** parameter factory, whereas `select-sql-parameter-source` references a separate `SqlParameterSource` bean for SELECT. Never pass `ExpressionEvaluatingSqlParameterSourceFactory` directly to the SELECT attribute when the endpoint expects a **parameter source**, not a factory.

## 16. Poller, `maxRows`, and Stability of Each Read

| Configuration | Unit | Effect |
|---|---|---|
| `fixedDelay(5s)` | Time between poll cycles | Controls DB access cadence |
| `maxMessagesPerPoll(1)` | `receive()` calls per trigger | Not row count |
| `maxRows(25)` | Rows returned by SELECT each time | Does not guarantee DB only scans 25 rows |
| SQL `LIMIT/TOP/FETCH` | Rows DB returns per query | Usually much more effective at bounding DB reads |
| `updatePerRow(false)` | Batch of selected rows | Set-based UPDATE |
| `updatePerRow(true)` | Each row in batch | Individual per-row UPDATE |
| `SqlParameterSourceFactory` | Parameter mapping | Does not alter poll schedule |

`maxMessagesPerPoll(1)` means polling the message source once per trigger, though the source may return a list of 25 rows. With a splitter, downstream receives up to 25 messages; do not confuse that with 25 separate SQL SELECT queries.

**For large datasets:** limit directly in the SELECT query using the DB dialect and indexes, rather than querying the whole table and capping with `maxRows` at the JDBC layer. Selected rows can hold connections, memory, and transaction locks for non-trivial durations.

## 17. Transactions: Are SELECT and UPDATE in One Poll Really Atomic?

Spring Integration inbound adapters let pollers run inside a Spring transaction:

~~~java
endpoint -> endpoint.poller(
    Pollers.fixedDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
~~~

With a matching `DataSourceTransactionManager` (or appropriately configured JDBC transaction manager), SELECT and UPDATE can share **one local DB transaction**.

~~~mermaid
sequenceDiagram
    participant Poller as Poller transaction
    participant Adapter as JDBC inbound adapter
    participant DB as Database
    participant Flow as DirectChannel consumer
    Poller->>Adapter: receive()
    Adapter->>DB: SELECT state='NEW'
    DB-->>Adapter: 101,102
    Adapter->>DB: UPDATE state='CLAIMED' WHERE id IN (...)
    Adapter-->>Flow: Message<List<Row>>
    alt Sync downstream succeeds
        Flow-->>Poller: Return
        Poller->>DB: COMMIT
    else Sync downstream throws
        Flow-->>Poller: Exception
        Poller->>DB: ROLLBACK (if sharing TX)
    end
~~~

**Conditions to examine carefully:**

- With `DirectChannel` and **same-thread synchronous** handlers, downstream can participate in the poller's transaction.
- With `ExecutorChannel`, `QueueChannel`, or async HTTP/Kafka publishers, the poller's transaction **does not automatically cross** to another thread or process.
- Transaction rollback protects **DB changes inside that local transaction**; it cannot retract Kafka/JMS messages or HTTP requests already dispatched and processed remotely.
- A `@Transactional` method invoked improperly outside the Spring proxy will not open a transaction even if the annotation is present in code.

Never conclude that executing an UPDATE guarantees successful processing across every downstream target system.

## 18. Contention Across Multiple Pollers: SELECT-Then-UPDATE Is Not Enough to Prevent Duplicates

Two instances A and B can run concurrently:

~~~text
T1  Instance A: SELECT id=101 WHERE state='NEW'
T2  Instance B: SELECT id=101 WHERE state='NEW'
T3  Instance A: UPDATE id=101 -> CLAIMED
T4  Instance A: publish event 101
T5  Instance B: UPDATE id=101 AND state='NEW' -> 0 rows
T6  Instance B: still holds row 101 in its SELECTed list
T7  Instance B: publishes event 101 a second time
~~~

An UPDATE predicate `state='NEW'` prevents **duplicate DB writes**, but it **does not remove the row from instance B's already-fetched SELECT list**. If downstream publishes based on that list without verifying claim ownership, duplicates still occur.

For multi-pod production deployments, choose one of these patterns:

1. **Vendor-specific atomic claim:** SQL Server can use `UPDATE ... OUTPUT` with appropriate locking; PostgreSQL has `FOR UPDATE SKIP LOCKED` inside a transaction; other DBs require equivalent constructs.
2. **Lease/reclaim:** store `claimed_by`/`lease_until` so stuck work can resume after worker crashes.
3. **Transactional outbox:** write outbound events in the same DB transaction, with a dedicated publisher handling broker sends and redeliveries.
4. **Idempotent consumer:** stable event IDs, unique keys, or a `processed_event` table to neutralize duplicate side effects.
5. **Partition/concurrency partitioning:** assign each instance a distinct partition or key range where needed.

Do not assume `updateSqlParameterSourceFactory`, SpEL, or `updatePerRow` gives you exactly-once semantics; they only build **SQL parameters**.

## 19. Idempotency, Recovery, and the CLAIMED State

If a poll marks rows `CLAIMED` successfully and the application crashes **before Kafka receives the event**, those rows can stay stuck. A bare `CLAIMED` status is insufficient for long-term operations.

~~~mermaid
flowchart LR
    A["NEW"] -->|"Claim atomically"| B["CLAIMED"]
    B -->|"Publish + confirm"| C["PROCESSED"]
    B -->|"Worker crash / lease expired"| D["RECOVERY"]
    D -->|"Retry with stable eventId"| A
    D -->|"Permanent failure"| E["FAILED / DLQ"]
~~~

**Recommended rules:** maintain a stable business `eventKey`; `CLAIMED` rows must track owner, lease expiration, and attempt count; when a lease expires, a recovery worker reclaims per policy; once publishing succeeds, record completion. With a transactional outbox, you often avoid the poller's `NEW → CLAIMED` pattern entirely because event lifecycle centers on the outbox.

**Safe retries:** do not generate a fresh UUID for the same event on each retry if that UUID acts as the idempotency key. If a client times out after the remote side may have written data, query/reconcile the outcome before retrying side-effecting calls.

## 20. Error Handling for Mapping and SQL Parameter Expressions

| Symptom | Common cause | Resolution |
|---|---|---|
| `No value supplied for SQL parameter 'ids'` | Factory did not populate key `ids` | Check `:ids` name and `SqlParameterSource` |
| SpEL cannot find `id` | Root is a List while expression targets a single row, or vice versa | Check `updatePerRow` and root type |
| `ClassCastException` | Configured DTO `RowMapper` but factory casts to Map | Switch factory to DTO accessors |
| `NullPointerException` in SpEL | SQL NULL field or missing key | Validate nullability/aliases |
| `DataAccessException` on UPDATE | Wrong SQL dialect/type, DB down, lock conflict | Classify transient vs. permanent |
| Duplicate messages after poll | Multiple instances or flawed ACK/recovery | Atomic claim/idempotency |
| Same rows repeatedly SELECTed | UPDATE did not match IDs or transaction rolled back | Inspect SQL/bind counts, verify state |
| SELECT status never changes across polls | Cached parameter source used | Use `createParameterSourceNoCache` when needed |
| UPDATE very slow with huge `IN (:ids)` | Oversized batch, locks, and DB parameter limits | Limit rows/chunking/indexes |

**Never swallow exceptions and treat messages as successful.** When an expression fails, the source can fail before emitting a message. Spring JDBC usually translates `SQLException` to `DataAccessException`; the poller has its own error handling and can route failures to `ErrorMessage`/`errorChannel` depending on configuration. Test rollbacks, logging/tracing, and real retry paths.

### 20.1. Avoid Side Effects Inside SpEL

Expressions should read data, normalize values, or pick stable configuration; never invoke an HTTP service inside SpEL relying on evaluation count for business logic. Caching vs. `createParameterSourceNoCache` can cause evaluation counts to differ between SELECT and UPDATE. Side effects belong in handlers/services with explicit transaction and error contracts.

## 21. Security and Performance

**SQL injection:** `:ids`, `:rowId`, and other named parameters are bound by Spring JDBC as values. They **do not replace** validating table names, column names, procedure names, or whole SQL fragments. Never take SQL strings from request headers or untrusted database fields.

**SpEL security:** expressions in `setParameterExpressions(...)` must be **application-controlled configuration**, never accepted arbitrarily from Kafka/HTTP payloads. SpEL can invoke methods or reference Spring beans; letting external input supply expressions opens an unintended execution surface.

**JDBC load:** `JdbcTemplate` and JDBC drivers are **blocking I/O**. Control pool size, poll intervals, SQL query durations, connection acquire timeouts, row limits, update batch sizes, and transaction durations. Never run JDBC on the Reactor Netty event loop assuming Spring Integration makes it non-blocking.

Useful metrics:

- Poll count, SELECT rows/poll, UPDATE rows/poll, zero-match UPDATE count.
- SELECT and UPDATE latencies, connection wait time, query timeouts/deadlocks.
- ID list sizes, parameter counts in `IN` clauses, batch duration.
- Poller errors, retry rates, rollback counts, queue depth, and consumer lag.
- Age of `CLAIMED` rows, expired leases, outbox lag, and duplicate events.

Do not place `eventKey`, user IDs, or sensitive payloads in high-cardinality metric tags; use trace/correlation IDs in scrubbed logs instead.

## 22. Unit Testing a Custom SqlParameterSourceFactory

Separating the factory from `IntegrationFlow` lets you test mapping **without a database**:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.integration.jdbc.SqlParameterSourceFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

class UpdateParameterFactoryTest {

    private record Item(long id) { }

    @Test
    void mapsSelectedRowsToIds() {
        SqlParameterSourceFactory factory = input -> {
            var ids = ((List<?>) input).stream()
                .map(Item.class::cast)
                .map(Item::id)
                .toList();
            return new MapSqlParameterSource("ids", ids);
        };

        var source = factory.createParameterSource(
            List.of(new Item(101), new Item(102)));

        assertEquals(List.of(101L, 102L), source.getValue("ids"));
    }
}
~~~

This test verifies that the factory **extracts the expected list of IDs** and SQL parameter name. It **does not** prove the DB executes/commits the UPDATE, that the SpEL bean resolver works, or that error channels handle failures; add integration tests for those.

### 22.1. Testing Expression Factories

When using `ExpressionEvaluatingSqlParameterSourceFactory`, test these cases:

1. `updatePerRow(true)`: root is a Map with `id`, and `#root['id']` extracts the value.
2. `updatePerRow(false)`: root is a List; projection `#root.![#this['id']]` produces the list of IDs.
3. Unexpected root shape: fails explicitly instead of silently passing empty IDs.
4. NULL/missing key: explicit validation error or defined fallback.
5. Same parameter referenced multiple times: UPDATE source caches values per contract.
6. Dynamic SELECT: `wantedState` re-evaluates between polls when using `createParameterSourceNoCache`.

To test expressions referencing `@beanName`, initialize the factory inside a Spring test context so Spring Integration's bean resolver and lifecycle are active.

## 23. Integration Testing with H2: SELECT, UPDATE, Rollback

With the schema/data from section 5, an end-to-end test should prove both **payload shape** and **DB state**:

~~~text
Setup:
  sync_event 101,102,103 = NEW
  sync_event 104 = CLAIMED

Poll one time with maxRows(2), updatePerRow(false):
  SELECT returns 101,102
  UPDATE uses ids [101,102]
  DB 101,102 -> CLAIMED
  Output Message<List<EventRow>> has exactly 2 elements
  After splitter: 2 × Message<EventRow>

Next poll:
  103 is selected and claimed
  104 remains untouched

When downstream DirectChannel handler throws before commit:
  Poller TX rolls back SELECT/UPDATE work
  Rows eligible again according to original DB state
~~~

### 23.1. Test Matrix

| Scenario | Expectation |
|---|---|
| SELECT 2 rows, batch UPDATE | Factory receives List; UPDATE targets the 2 IDs |
| SELECT 2 rows, per-row UPDATE | Factory receives each row; 2 update calls |
| SELECT 0 rows | No erroneous updates, no empty business events emitted |
| Using DTO RowMapper | Factory does not cast to Map by mistake |
| Mismatched SQL parameter name | Clear error instead of corrupt writes |
| Mismatched SQL status/attempt type | Exception observed, appropriate rollback |
| Dynamic SELECT parameter | Uses no-cache and sees new config on next poll |
| UPDATE affects 0 rows due to race | Does not assume claim succeeded and publish anyway |
| DirectChannel handler throws | DB transaction rolls back when sharing TX |
| ExecutorChannel async handler throws | Does not automatically roll back poller TX |
| Two replicas poll concurrently | Exposes duplicate risk; atomic claim required |
| Crash after DB claim before broker publish | Lease/outbox/recovery prevents lost work |

Do not validate these scenarios merely by checking `send() == true`; verify **the database after commit**, output messages, and exception behavior. For locking/deadlock/concurrency cases, use a vendor-matched test DB or Testcontainers because H2 does not reproduce them faithfully.

## 24. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “`:id` in SQL is SpEL” | It is a named parameter whose value comes from the parameter source |
| “Every UPDATE needs a custom factory” | The `id` column → `:id` convention is often sufficient |
| “`updateSqlParameterSourceFactory` receives an incoming Message” | JDBC inbound passes **the SELECT result**; there is no request message like outbound |
| “`updatePerRow(true)` means one message per row” | It changes UPDATE scope; a **splitter** splits messages |
| “`updatePerRow(false)` SpEL root is a single row” | Default root is the **List of rows** |
| “SELECT parameters come from the rows just read” | SELECT runs **before** rows exist |
| “`createParameterSource` and `createParameterSourceNoCache` are identical” | They differ in caching evaluated expression values |
| “`maxMessagesPerPoll(1)` means one row” | It is one poll of the source per trigger |
| “`maxRows(0)` fetches zero rows” | It sets no row limit at the adapter |
| “Adding a DTO RowMapper does not affect the factory” | The root object changes from Map to DTO |
| “`UPDATE state='CLAIMED'` automatically prevents duplicate publishing” | Two instances can still hold the same SELECTed row |
| “DB rollback retracts Kafka events automatically” | JDBC transactions do not encompass brokers by default |
| “Client-supplied SpEL is safe as a SQL parameter” | Expression evaluation is a separate attack surface; use trusted config only |
| “A JDBC adapter inside WebFlux is non-blocking” | JDBC remains blocking I/O |

## 25. Practice Exercises

1. Create the `sync_event` table per section 5, use a JDBC inbound adapter to SELECT `NEW` rows, and inspect the payload before the splitter.
2. Configure the default `WHERE id IN (:id)` UPDATE without a custom factory; verify the right rows are marked.
3. Change `:id` to `:selectedIds`, write a custom lambda `SqlParameterSourceFactory`, and verify the ID list.
4. Write `EventRowMapper` to switch payloads from Maps to Java records; update the factory accordingly.
5. Enable `updatePerRow(true)` and use `#root['id']` on row Maps; compare SQL UPDATE call counts against batch mode.
6. Use `ExpressionEvaluatingSqlParameterSourceFactory` with list projection `#root.![#this['id']]` in batch mode.
7. Deliberately switch from batch mode to per-row mode while keeping the list expression; observe the error and explain the root type.
8. Configure `setSqlParameterTypes` for `BIGINT`/`VARCHAR` and verify JDBC parameter binding.
9. Add `setStaticParameters` sharing a key with `setParameterExpressions` to verify precedence rules.
10. Configure SELECT `WHERE state = :wantedState` with a fixed `MapSqlParameterSource`.
11. Replace the SELECT state with a dynamic bean, use `createParameterSourceNoCache`, and change the value between two polls.
12. Wrap the poller in a transaction and make a downstream `DirectChannel` handler throw an exception; verify rollback.
13. Move downstream to an `ExecutorChannel` and show why the poller's transaction does not propagate to the worker.
14. Run two pollers or two instances competing for the same rows; prove a predicated UPDATE alone can still cause duplicate publishing.
15. Implement atomic claiming/leasing on a real vendor DB and compare it with SELECT-then-UPDATE.
16. Add a stable outbox/`processed_event` key to handle crashes after claim and before publish.
17. Write a 6.x XML configuration with `sql-parameter-source-factory`, `update-per-row`, and a poller transaction; compare with 7.x Java DSL.
18. Use H2 to test SQL mapping, then run a production-compatible Testcontainers DB to verify locking and rollback.

**Comprehensive scenario:** two pods concurrently poll a table with 100 `NEW` events. One pod SELECTs 25 rows but crashes after UPDATE; the other pod receives some overlapping IDs and already published to Kafka. Identify the `SqlParameterSourceFactory` root in each mode, the right claiming SQL, transaction/lease handling, ACK rules, stable event IDs, outbox design, and tests needed to prevent lost or duplicated effects.

## 26. References

- [Spring Integration Reference — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): default `:id` parameter, `SqlParameterSourceFactory`, SpEL roots, `createParameterSourceNoCache`, pollers, and transactions.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): JDBC Java DSL introduced in Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `updateSqlParameterSourceFactory`, `updatePerRow`, `selectSqlParameterSource`, and `maxRows`.
- [Spring Integration API — JdbcPollingChannelAdapter 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): Java setters, SELECT/UPDATE behavior, and default update-per-row.
- [Spring Integration API — SqlParameterSourceFactory](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/jdbc/SqlParameterSourceFactory.html): factory contract and `createParameterSource(Object)`.
- [Spring Integration API — ExpressionEvaluatingSqlParameterSourceFactory](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/ExpressionEvaluatingSqlParameterSourceFactory.html): `setParameterExpressions`, `setStaticParameters`, `setSqlParameterTypes`, and caching behavior.
- [Spring Integration Reference — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): contrasting message-rooted outbound binding, named parameters, and SpEL.
- [Spring Framework Reference — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `NamedParameterJdbcTemplate`, `SqlParameterSource`, `MapSqlParameterSource`, and JDBC operations.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transactional pollers and synchronous message flows.

> **Remember:** `updateSqlParameterSourceFactory` turns **SELECT results** into UPDATE parameters; `updatePerRow(false)` operates on **the entire list**, while `updatePerRow(true)` operates **row by row**. `ExpressionEvaluatingSqlParameterSourceFactory` uses **separately configured SpEL** to compute values, while `:id`/`:ids` in SQL remain named parameters. SELECT parameters belong to `selectSqlParameterSource` and follow different caching rules. Reliability requires controlling transactions, duplicate polls, atomic claims, recovery, and idempotency; the factory only handles **parameter mapping**, not delivery guarantees.

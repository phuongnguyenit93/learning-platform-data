# DataSource and JdbcTemplate in Spring Integration JDBC

## 1. What Problems Do DataSource and JdbcTemplate Solve?

In an integration flow, data may arrive from HTTP, files, SFTP, JMS, AMQP, or Kafka, and then require querying or persisting changes to a database. For example, when receiving an `order.paid` message, the application must update the order status, record an event in an outbox table, and acknowledge the source message only once the required operations succeed.

Spring JDBC provides two foundational building blocks:

- **`DataSource`** is the JDBC contract for obtaining/allocating a `Connection`. When backed by a connection pool, it also manages connection reuse, concurrency limits, and connection lifecycles.
- **`JdbcTemplate`** is the utility for executing SQL against a `DataSource`. It acquires and releases connections, creates statements, binds parameters, reads `ResultSet`s, and translates `SQLException`s into Spring's `DataAccessException` hierarchy.

In the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, these classes form the foundation for JDBC inbound/outbound adapters, JDBC outbound gateways, stored procedure endpoints, and database-accessing service activators. Overall, the module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; therefore, beyond SQL syntax, this lesson clarifies **message contracts, errors, transactions, load limits, and connection lifecycles**.

~~~mermaid
flowchart LR
    A["Kafka / HTTP / JMS / SFTP"] --> B["Spring Integration MessageChannel"]
    B --> C["JDBC adapter / gateway / service activator"]
    C --> D["JdbcTemplate / JdbcOperations"]
    D --> E["DataSource"]
    E --> F["Connection pool"]
    F --> G[("Database")]
    G --> F
    F --> E
    E --> D
    D -->|"Rows / count / exception"| C
~~~

**Key distinction:** `DataSource` is not a single JDBC connection; `JdbcTemplate` is not a pool. `JdbcTemplate` uses the configured `DataSource`, while `MessageChannel` and endpoints determine when a JDBC operation runs, whether it produces a reply, and which thread runs the transaction.

## 2. Responsibility Map from Message to SQL

| Component | Responsibility | What it does not guarantee automatically |
|---|---|---|
| `MessageChannel` | Delivers Spring Integration messages to handlers | That the database committed when `send()` returns |
| JDBC inbound adapter | Polls `SELECT` and builds messages from rows | One message per row automatically; no duplicates across replicas |
| JDBC outbound adapter | Runs DML from messages with no business reply | Returning update counts downstream |
| JDBC outbound gateway | Runs SQL and returns rows/counts/keys per config | That an outer transaction has committed |
| `DataSource` | Supplies `Connection`s per configuration | Valid SQL or automatic message retries |
| `JdbcTemplate` | Executes SQL, manages JDBC resources, translates exceptions | Business logic, event ordering, idempotency |
| `PlatformTransactionManager` | Manages commit/rollback within resource scope | Atomic transactions across Kafka/JMS/HTTP by default |
| `DataSource` pool (e.g., HikariCP) | Limits/reuses physical connections | Business rate limiting or backpressure across brokers |

For example, a message may flow through:

~~~text
Message<OrderPaid>
  -> DirectChannel
  -> ServiceActivator
  -> OrderJdbcRepository (JdbcTemplate)
  -> DataSource / HikariCP
  -> PreparedStatement UPDATE ...
  -> database transaction
  -> result or exception
~~~

When you need a one-way component, a service activator can be replaced by `JdbcMessageHandler`. When you need a reply, choose `JdbcOutboundGateway` or a service method that returns a value. **Choose endpoints by message contract**, not merely because they use JDBC.

## 3. Setting Up Spring Boot, Spring Integration JDBC, and H2

Examples use Java 17+, Spring Boot, and an H2 database so you can practice without installing a separate server. Use Spring Boot dependency management so Spring Framework, Spring Integration, HikariCP, and the JDBC driver remain compatible.

~~~groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-jdbc` typically brings `JdbcTemplate`, transaction support, and HikariCP into the application; `spring-integration-jdbc` provides JDBC adapters/gateways, message stores, and stored procedure support. H2 is only a learning database; when deploying to PostgreSQL, SQL Server, MySQL, or Oracle, switch to the appropriate driver and SQL dialect.

~~~yaml
# application.yml - H2 demo
spring:
  datasource:
    url: "jdbc:h2:mem:integration_orders;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      pool-name: integration-order-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      max-lifetime: 1800000
  sql:
    init:
      mode: always
~~~

The Hikari values here are **illustrative**, not optimal defaults for every application. Hikari's `connection-timeout`/`max-lifetime` are specified in **milliseconds**. With an embedded database, `DB_CLOSE_DELAY=-1` keeps the database in the JVM until shutdown; data is still not durable across process restarts.

### 3.1. Creating the Schema

Place the content below in `src/main/resources/schema.sql` of your **practice application**; this is merely an example to understand the lesson, not a requirement to create external files outside the assigned Markdown.

~~~sql
CREATE TABLE order_projection (
    order_id       VARCHAR(64) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    total_amount   DECIMAL(18, 2) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_event (
    outbox_id      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id       VARCHAR(64) NOT NULL UNIQUE,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(64) NOT NULL,
    published      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO order_projection(order_id, status, total_amount, version)
VALUES ('ORD-1001', 'RECEIVED', 125000.00, 0),
       ('ORD-1002', 'RECEIVED', 75000.00, 0),
       ('ORD-1003', 'PAID', 30000.00, 1);
~~~

H2 and several databases support multi-row `INSERT` statements as shown; always verify SQL dialects when moving to production. In real projects, prefer Flyway/Liquibase migrations rather than recreating schemas automatically on startup.

## 4. How Does Spring Boot Create DataSource and JdbcTemplate?

When the JDBC starter, a compatible driver, and `spring.datasource.*` properties are present, Spring Boot normally **auto-configures**:

1. A `DataSource`, preferring HikariCP if available on the classpath.
2. A `JdbcTemplate` using that `DataSource`.
3. A `NamedParameterJdbcTemplate` for `:namedParameter` usage.
4. Appropriate JDBC transaction infrastructure when auto-configuration conditions are met.

Therefore, in simple applications, you only need to **inject the existing beans**:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class DatabaseAccessSummary {

    private final DataSource dataSource;
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbc;

    public DatabaseAccessSummary(
            DataSource dataSource,
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbc) {
        this.dataSource = dataSource;
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbc = namedJdbc;
    }
}
~~~

Never construct `new HikariDataSource()` inside each handler or create a new `JdbcTemplate` per message. The pool should be **shared** across JDBC steps serving the same database. `JdbcTemplate` holds a reference to `DataSource` and is designed to be shared across multiple DAOs once configured.

### 4.1. When Should You Define Your Own DataSource?

Defining `@Bean DataSource` manually is typically only necessary when:

- The application connects to multiple databases/tenants with separate pools.
- Custom TLS, credential rotation, or failover goes beyond standard auto-configuration.
- Running inside an application server with a JNDI datasource.
- Infrastructure constraints require explicit control over the datasource bean.

**Caution:** defining your own `DataSource` bean can suppress parts of Boot's DataSource auto-configuration. When using multiple sources, clearly declare `@Primary` or `@Qualifier`, and explicitly specify which transaction manager binds to which database.

## 5. Connection Lifecycle: Acquire, Execute, Release

`DataSource` is the **factory**, while `Connection` is the JDBC resource returned to the pool when done. A typical `JdbcTemplate.query(...)` call:

~~~mermaid
sequenceDiagram
    participant Handler as JDBC handler
    participant Template as JdbcTemplate
    participant Source as DataSource / pool
    participant DB as Database
    Handler->>Template: query(sql, mapper, args)
    Template->>Source: Get Connection
    Source-->>Template: Pooled Connection
    Template->>DB: PreparedStatement + executeQuery
    DB-->>Template: ResultSet
    Template->>Template: RowMapper / ResultSet extraction
    Template->>Source: Release Connection
    Template-->>Handler: List<T> or exception
~~~

`JdbcTemplate` manages closing `ResultSet`/`Statement` objects and releasing connections per Spring JDBC rules. When a transaction is bound to the thread, the connection **may be held until the transaction finishes**, rather than returned immediately after one query.

**Never store a `Connection` in a service field to reuse across messages.** JDBC connections and statements are not resources designed to be shared arbitrarily across threads. When connections leak, available pool slots shrink and subsequent messages time out trying to acquire a connection.

### 5.1. HikariCP Is a Pool, Not the Database

| Hikari setting | Meaning | Misconception to avoid |
|---|---|---|
| `maximum-pool-size` | Maximum number of connections the pool can manage at once | Not SQL statements per second |
| `minimum-idle` | Target number of idle connections to maintain | Not a strict fixed pool size in all situations |
| `connection-timeout` | Max time to wait for a connection before failing | Not SQL query timeout |
| `idle-timeout` | Idle age after which a connection becomes eligible for eviction per pool policy | Does not interrupt active running queries |
| `max-lifetime` | Max connection age before retirement/replacement | Active in-use connections are generally not closed mid-query on expiry |
| `pool-name` | Identifier for logs/metrics | Does not affect message delivery logic |

A workload of 200 messages/sec does not necessarily need 200 connections. Required concurrency depends on connection hold time, SQL throughput, DB server limits, locks, and transactions. When a database suffers from lock contention, **raising pool size indefinitely** usually makes things worse.

## 6. How Does JdbcTemplate Execute SQL?

`JdbcTemplate` provides key API groups:

| API group | Purpose | Typical return type |
|---|---|---|
| `update(sql, args...)` | INSERT/UPDATE/DELETE | `int` affected row count |
| `query(sql, RowMapper, args...)` | SELECT multiple rows | `List<T>` |
| `queryForObject(sql, RowMapper, args...)` | SELECT expecting exactly one row | `T` or exception if row count mismatches |
| `queryForObject(sql, Class<T>, args...)` | Read a single scalar value | `T` or exception if cardinality mismatches |
| `batchUpdate(...)` | Execute multiple homogeneous updates | `int[]`/batch result variants |
| `execute(...)` | Custom JDBC operations | Per callback |
| `call(...)`, `SimpleJdbcCall` | CallableStatement/stored procedures | Per OUT params/result sets |

Common thread: **JDBC is still blocking I/O**. `JdbcTemplate` manages resources, SQL, and exceptions, but it **does not return a non-blocking `Mono`/`Flux`** like R2DBC. In WebFlux or reactive chains, establish explicit thread boundaries so you do not block the event loop.

### 6.1. Creating the Model and RowMapper

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderRecord(
    String orderId,
    String status,
    BigDecimal totalAmount,
    int version) {
}
~~~

`RowMapper<T>` defines how to map **one** JDBC row to a Java object:

~~~java
import org.springframework.jdbc.core.RowMapper;

RowMapper<OrderRecord> orderRowMapper = (rs, rowNum) ->
    new OrderRecord(
        rs.getString("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"),
        rs.getInt("version"));
~~~

`ResultSet.getBigDecimal` suits monetary values better than `double`; for nullable numeric columns, use boxed wrappers or check `rs.wasNull()` so you do not silently receive primitive defaults.

## 7. Complete Example: Repository Using JdbcTemplate

The following repository shows how to reuse the same `JdbcTemplate` to read and write `order_projection`. `RowMapper` is stateless/immutable configuration and can be reused safely.

~~~java
package com.example.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final RowMapper<OrderRecord> ORDER_MAPPER =
        (rs, rowNum) -> new OrderRecord(
            rs.getString("order_id"),
            rs.getString("status"),
            rs.getBigDecimal("total_amount"),
            rs.getInt("version"));

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderRecord> findById(String orderId) {
        return jdbc.query(
            "SELECT order_id, status, total_amount, version "
          + "FROM order_projection WHERE order_id = ?",
            ORDER_MAPPER, orderId)
            .stream()
            .findFirst();
    }

    public List<OrderRecord> findByStatus(
            String status, int limit) {
        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException("limit must be 1..500");
        }
        // LIMIT is an example suited to H2; other DBs may use FETCH/TOP.
        return jdbc.query(
            "SELECT order_id, status, total_amount, version "
          + "FROM order_projection WHERE status = ? "
          + "ORDER BY order_id LIMIT ?",
            ORDER_MAPPER, status, limit);
    }

    public int changeStatus(
            String orderId,
            String expectedStatus,
            String newStatus,
            int expectedVersion) {
        return jdbc.update(
            "UPDATE order_projection "
          + "SET status = ?, version = version + 1, "
          + "updated_at = CURRENT_TIMESTAMP "
          + "WHERE order_id = ? AND status = ? AND version = ?",
            newStatus, orderId, expectedStatus, expectedVersion);
    }

    public int countByStatus(String status) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM order_projection WHERE status = ?",
            Integer.class, status);
        return count == null ? 0 : count;
    }
}
~~~

**Interpreting results:**

- `findById("ORD-1001")` returns `Optional<OrderRecord>`, without throwing just because no row exists. `stream().findFirst()` is fine here because the predicate targets the **PRIMARY KEY**, though it does not replace uniqueness enforcement for arbitrary SELECTs.
- `findByStatus("RECEIVED", 100)` returns a list of at most 100 elements using the chosen SQL dialect.
- `changeStatus(..., expectedVersion)` returns `1` if one row matched, `0` if not found, status/version changed, or the predicate no longer holds.
- `countByStatus` runs a scalar query rather than loading the entire table into memory to count.

**Row ordering:** SQL `ORDER BY` is required whenever business logic depends on ordering; never assume the database returns rows in primary key order without `ORDER BY`.

## 8. `queryForObject`, `query`, and Cardinality

`JdbcTemplate.queryForObject(...)` is designed for **exact single-row** results. If SQL returns 0 or more than 1 row, Spring JDBC normally throws subtypes of `IncorrectResultSizeDataAccessException`, including `EmptyResultDataAccessException` for 0 rows.

~~~java
// Only appropriate when COUNT(*) always yields exactly one row.
int count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM order_projection",
    Integer.class);

// Reading one row by unique key:
OrderRecord record = jdbc.queryForObject(
    "SELECT order_id, status, total_amount, version "
  + "FROM order_projection WHERE order_id = ?",
    orderRowMapper, "ORD-1001");
~~~

If “not found” is a **valid domain outcome**, two approaches work cleanly:

1. `query(..., RowMapper, args).stream().findFirst()` as in the repository in section 7 (with a uniqueness-guaranteeing predicate).
2. Catch `EmptyResultDataAccessException` specifically and return `Optional.empty()`; do not catch all `DataAccessException`s and return empty, as that hides connectivity and SQL syntax errors.

| SQL result | `query(...)` | `queryForObject(...)` |
|---|---|---|
| 0 rows | Empty list | Usually throws `EmptyResultDataAccessException` |
| 1 row | 1-element list | Returns the single object/scalar |
| Multiple rows | Multi-element list | Usually throws `IncorrectResultSizeDataAccessException` |

**Do not confuse absence with timeout:** a query returning no rows is normally a domain result; an unreachable database is an infrastructure failure that must be logged and handled by policy.

## 9. PreparedStatement and NamedParameterJdbcTemplate

### 9.1. Binding Parameters with `?`

In `JdbcTemplate`, parameters are bound via JDBC `PreparedStatement`:

~~~java
int rows = jdbc.update(
    "UPDATE order_projection SET status = ? WHERE order_id = ?",
    "PAID", "ORD-1001");
~~~

`?` placeholders correspond to values left-to-right. Never construct SQL via:

~~~java
// DO NOT DO THIS: external input concatenated into SQL.
String unsafe =
    "SELECT * FROM order_projection WHERE order_id = '" + orderId + "'";
~~~

With SQL injection, even a `SELECT` statement can be abused to read unauthorized data. Use bind parameters for **values**; table names, column names, and sort directions must come from an application-controlled allowlist.

### 9.2. NamedParameterJdbcTemplate for Readable SQL

~~~java
package com.example.orders;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NamedOrderRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public NamedOrderRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Map<String, Object>> findByStatuses(
            List<String> statuses) {
        if (statuses == null || statuses.isEmpty()) {
            return List.of();
        }
        return jdbc.queryForList(
            "SELECT order_id, status, total_amount "
          + "FROM order_projection WHERE status IN (:statuses) "
          + "ORDER BY order_id",
            Map.of("statuses", statuses));
    }
}
~~~

`NamedParameterJdbcTemplate` expands `:statuses` into the matching number of placeholders. The example avoids running `IN ()` with an empty list because empty `IN` syntax is not consistently supported across databases.

**Remember to distinguish:** `NamedParameterJdbcTemplate` uses SQL parameters like `:statuses`; syntax like `:payload[orderId]` in Spring Integration JDBC adapters is **the adapter's way of reading message parameters via property paths**. Do not assume every colon-prefixed token is SpEL; when custom SpEL evaluation is needed, Spring Integration provides `ExpressionEvaluatingSqlParameterSourceFactory`.

### 9.3. JdbcClient as a Fluent API Option

Spring Framework 6.1+ includes `JdbcClient` for writing queries with either named or positional parameters. Under the hood it uses the same Spring JDBC infrastructure, not a separate connection/database stack.

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;

int count = JdbcClient.create(dataSource)
    .sql("SELECT COUNT(*) FROM order_projection WHERE status = :status")
    .param("status", "PAID")
    .query(Integer.class)
    .single();
~~~

`JdbcTemplate` and `NamedParameterJdbcTemplate` remain essential for batching, JDBC callbacks, and Spring Integration endpoints. This article emphasizes `JdbcTemplate` because Spring Integration adapters/gateways accept `DataSource` or `JdbcOperations`/template depending on the API.

## 10. Batch Updates, Generated Keys, and Real-World Costs

### 10.1. Batch Updates Do Not Mean Separate Transactions by Default

Instead of running a SQL UPDATE thousands of times in a loop, `JdbcTemplate.batchUpdate(...)` can group homogeneous statements into a JDBC batch:

~~~java
import java.util.List;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;

record StatusChange(String orderId, String newStatus) { }

List<StatusChange> changes = List.of(
    new StatusChange("ORD-1001", "PAID"),
    new StatusChange("ORD-1002", "PAID"));

int[] counts = jdbc.batchUpdate(
    "UPDATE order_projection SET status = ? "
  + "WHERE order_id = ?",
    new BatchPreparedStatementSetter() {
        @Override
        public void setValues(
                java.sql.PreparedStatement ps, int i)
                throws java.sql.SQLException {
            StatusChange change = changes.get(i);
            ps.setString(1, change.newStatus());
            ps.setString(2, change.orderId());
        }

        @Override
        public int getBatchSize() {
            return changes.size();
        }
    });
~~~

`counts` may contain per-item row counts or special driver values (such as `Statement.SUCCESS_NO_INFO`). **Never assume every element equals 1.** If an element fails, batch state depends on the driver, transaction boundaries, and rollback behavior; verify with integration tests on the real database.

In large applications, bound batch sizes and transaction durations. Huge batches hold locks longer, consume memory, and make retries difficult to control.

### 10.2. Retrieving Generated Keys with KeyHolder

Example inserting an audit/outbox row and reading the auto-generated key:

~~~java
import java.sql.PreparedStatement;
import java.util.Objects;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

int inserted = jdbc.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO outbox_event(event_id, aggregate_id, event_type) "
      + "VALUES (?, ?, ?)",
        new String[] {"outbox_id"});
    ps.setString(1, "evt-1001-paid");
    ps.setString(2, "ORD-1001");
    ps.setString(3, "order.paid");
    return ps;
}, keyHolder);

if (inserted != 1) {
    throw new IllegalStateException("Expected one outbox row");
}
Number generated = Objects.requireNonNull(
    keyHolder.getKey(), "No generated key returned");
long outboxId = generated.longValue();
~~~

Generated key support, column names, and numeric types depend on the JDBC driver/database. H2 is illustrative only; for SQL Server, Oracle, or PostgreSQL, run integration tests in the real dialect. A generated ID **does not automatically deduplicate events**: the unique `event_id` column in the schema serves that role.

## 11. Transactions: In What Scope Does JDBC Execute?

### 11.1. Transaction-Aware Connections

Spring JDBC uses `DataSourceUtils` to acquire and release connections according to Spring's transaction context. When `@Transactional` uses the matching JDBC transaction manager, multiple `JdbcTemplate` calls against **the same datasource** on **the same thread** can participate in **one local DB transaction**.

~~~mermaid
sequenceDiagram
    participant Service as Transactional service
    participant TX as TransactionManager
    participant JDBC as JdbcTemplate
    participant DB as Database
    Service->>TX: begin transaction
    Service->>JDBC: UPDATE order_projection
    JDBC->>DB: SQL on transactional Connection
    Service->>JDBC: INSERT outbox_event
    JDBC->>DB: SQL in same transaction
    alt Success
        Service->>TX: commit
    else RuntimeException
        Service->>TX: rollback
    end
~~~

### 11.2. Example Service Updating Status and Writing Outbox

~~~java
package com.example.orders;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderJdbcRepository orders;
    private final JdbcTemplate jdbc;

    public OrderPaymentService(
            OrderJdbcRepository orders, JdbcTemplate jdbc) {
        this.orders = orders;
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(
            String orderId, int expectedVersion, String eventId) {
        int changed = orders.changeStatus(
            orderId, "RECEIVED", "PAID", expectedVersion);
        if (changed != 1) {
            throw new IllegalStateException(
                "Order missing, stale or already changed: " + orderId);
        }

        jdbc.update(
            "INSERT INTO outbox_event(event_id, aggregate_id, event_type) "
          + "VALUES (?, ?, ?)",
            eventId, orderId, "order.paid");
    }
}
~~~

If inserting into `outbox_event` throws a `DataAccessException` and it propagates out of the method, Spring's default transaction behavior rolls back both operations, **assuming** the method is invoked via a Spring transaction proxy and both operations use the same `DataSource`/transaction manager.

The example does not fully depict duplicate `eventId` handling: on redelivery, `changeStatus` may return 0. For **idempotency**, reconcile against stored event IDs/versions rather than turning every 0 into “successfully reprocessed”. With multiple workers, unique `event_id` constraints and transaction conflict checks are essential.

**Never send a Kafka event directly between two JDBC calls and claim atomicity.** Transactional outbox means saving the event in a table within the DB transaction, then having a separate publisher read the outbox, send to the broker, and update status with retry/deduplication.

### 11.3. @Transactional and Common Pitfalls

- Proxy-based `@Transactional` only intercepts calls made **through the Spring-managed proxy**; self-invoking `this.markPaid(...)` within the same object bypasses the advice.
- `@Transactional(readOnly=true)` is an optimization hint/contract for reads depending on DB/driver support, **not an authorization guard blocking all UPDATEs**.
- By default, Spring rolls back on `RuntimeException`/`Error`; for checked exceptions configure `rollbackFor` or match your version's defaults.
- When multiple transaction managers exist, explicitly specify the manager matching the datasource.
- `REQUIRES_NEW` may require a separate connection while the outer transaction still holds one: account for pool capacity.

## 12. DirectChannel, ExecutorChannel, and Transaction Boundaries

In Spring Integration, the channel type determines the **execution thread** of a JDBC handler:

| Channel/source | How JDBC runs | Consequence |
|---|---|---|
| `DirectChannel` | Sender's thread | Can participate in the caller's JDBC transaction |
| `ExecutorChannel` | Separate executor thread | Thread-bound transactions **do not propagate** to the executor |
| `QueueChannel` with poller | Poller consumes message later | Requires a dedicated transaction boundary at poller/handler |
| JDBC inbound poller | Poller actively runs `SELECT` | Can wrap the poll operation in a transaction |
| Kafka/JMS inbound adapter | Per listener container/adapter | ACK/offset commit is not automatically atomic with DB |

~~~mermaid
flowchart TB
    A["Producer @Transactional"] --> B{"MessageChannel"}
    B -->|"DirectChannel"| C["Same-thread JDBC handler / can share TX"]
    B -->|"ExecutorChannel"| D["Worker thread / different TX"]
    B -->|"QueueChannel"| E["Poller / different timing"]
    D --> F["Needs explicit TX at consumer"]
    E --> F
~~~

**Pattern to avoid:** caller calls `send()` to an `ExecutorChannel`, gets `true`, and immediately ACKs Kafka while the JDBC worker has not run yet or fails later. The boolean returned by `send()` is not a **database commit** receipt in an async flow.

With `DirectChannel`, the JDBC handler can share the caller's transaction; even after DML runs cleanly, the outer transaction can still roll back **after the handler returns**.

## 13. Applying DataSource/JdbcTemplate to JDBC Adapters and Gateways

### 13.1. Java DSL for JDBC Outbound Channel Adapter — Spring Integration 7.x

Since **Spring Integration 7.0**, the JDBC module provides the `org.springframework.integration.jdbc.dsl.Jdbc` factory to configure adapters/gateways in Java DSL. The example below receives `Message<StatusCommand>` and runs a **one-way** DML statement:

~~~java
package com.example.orders;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
@EnableIntegration
public class JdbcOutboundFlow {

    public record StatusCommand(
        String orderId, String status, int expectedVersion) { }

    @Bean
    public IntegrationFlow storeStatuses(DataSource dataSource) {
        return IntegrationFlow.from("statusWriteRequests")
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE order_projection "
                  + "SET status = ?, version = version + 1 "
                  + "WHERE order_id = ? AND version = ?")
                .preparedStatementSetter((ps, message) -> {
                    StatusCommand command =
                        (StatusCommand) message.getPayload();
                    ps.setString(1, command.status());
                    ps.setString(2, command.orderId());
                    ps.setInt(3, command.expectedVersion());
                }))
            .get();
    }
}
~~~

`Jdbc.outboundAdapter(dataSource, sql)` uses the `DataSource` injected by Spring Boot or defined by the application. The endpoint acquires connections through Spring JDBC; you **do not manually open/close `Connection`s** inside handlers.

Because it is an **outbound channel adapter**, this code **does not emit an update-count reply** downstream. If business logic needs `UPDATED=0` vs. `UPDATED=1` for routing, use a **JDBC outbound gateway** or a service activator calling `JdbcTemplate.update(...)` and returning the result.

### 13.2. Using JdbcOperations/JdbcTemplate Instead of DataSource

Many Spring Integration JDBC components accept **`DataSource` or `JdbcOperations`/`JdbcTemplate`** via constructors/factories depending on version. Both target the same database if backed by the same `DataSource`:

~~~java
// Dependency injection concept:
// JdbcTemplate template = Boot bean backed by the DataSource bean.
// JDBC endpoints can accept DataSource or JdbcOperations
// per the overloads of your Spring Integration version.
~~~

Injecting `JdbcTemplate` lets you share template-level settings (such as query timeout or SQL exception translator) when the endpoint actually accepts that template. **Do not assume every endpoint automatically inherits custom settings from a separate `JdbcTemplate` bean** when you pass `DataSource` directly and let the endpoint build its own template.

### 13.3. Spring Integration 6.x: Building JdbcMessageHandler

The Java DSL factory `Jdbc.outboundAdapter(...)` belongs to **7.x**. In Spring Integration **6.x**, you can instantiate the handler directly:

~~~java
package com.example.orders;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcMessageHandler;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyJdbcWriteConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "legacyStatusWriteRequests")
    public MessageHandler legacyJdbcWriter(DataSource dataSource) {
        JdbcMessageHandler handler = new JdbcMessageHandler(
            dataSource,
            "UPDATE order_projection SET status = ? WHERE order_id = ?");
        handler.setPreparedStatementSetter((ps, message) -> {
            JdbcOutboundFlow.StatusCommand command =
                (JdbcOutboundFlow.StatusCommand) message.getPayload();
            ps.setString(1, command.status());
            ps.setString(2, command.orderId());
        });
        return handler;
    }
}
~~~

This 6.x snippet assumes you have the `StatusCommand` DTO from the prior example; if running 6.x **standalone**, move the DTO into your 6.x application rather than adding 7.x Java DSL to the classpath just for the DTO.

In Spring Integration **7.x**, if instantiating `JdbcMessageHandler` directly, the handler package is `org.springframework.integration.jdbc.outbound.JdbcMessageHandler`. **Never mix 6.x and 7.x imports.**

## 14. JdbcTemplate in a Service Activator When Replies or Complex Logic Are Needed

If an integration flow requires **“receive a status command, return the update count”**, a result-returning service activator can be clearer than a one-way DML adapter:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StatusCommandHandler {

    private final OrderJdbcRepository repository;

    public StatusCommandHandler(OrderJdbcRepository repository) {
        this.repository = repository;
    }

    @ServiceActivator(inputChannel = "statusCommandRequests",
                      outputChannel = "statusCommandResults")
    public UpdateResult update(JdbcOutboundFlow.StatusCommand command) {
        int affected = repository.changeStatus(
            command.orderId(),
            "RECEIVED",
            command.status(),
            command.expectedVersion());
        return new UpdateResult(command.orderId(), affected);
    }

    public record UpdateResult(String orderId, int affectedRows) { }
}
~~~

`@ServiceActivator` receives the payload mapped by the messaging framework's converters as configured and sends the returned object as the reply payload. This example returns a typed domain reply `UpdateResult` instead of relying on `Map{UPDATED=n}`; ensure an appropriate consumer or reply context listens on `statusCommandResults`.

**Contract decision needed:** `affectedRows=0` could mean order not found, stale version, or an already-processed event. If certainty is needed, perform a follow-up query/event-ID check within a **business transaction**. Never assume 0 automatically means “success” or “infrastructure error”.

## 15. JDBC Inbound Adapter, Pollers, and Duplicate Data

The JDBC inbound channel adapter runs `SELECT` on a schedule. It uses `DataSource`/`JdbcTemplate` to fetch rows and emit messages; when you need **one message per row**, add a splitter. With a database as an event source, you need rules to mark processed records.

~~~mermaid
flowchart LR
    P["Poller: fixedDelay"] --> A["JDBC inbound adapter"]
    A --> B["SELECT pending rows"]
    B --> C["Message<List<Row>>"]
    C --> D["Splitter"]
    D --> E["Message<Row>"]
    E --> F["Kafka / JMS / handler"]
~~~

Some JDBC inbound endpoints let you pair `SELECT` with `UPDATE` to mark polled rows within the poller transaction. Distinguish:

| Option | Unit | Meaning |
|---|---|---|
| Poller `fixedDelay` | Time duration | Cadence for polling the message source |
| `maxMessagesPerPoll` | Number of `receive()` calls | How many times to poll the source per trigger |
| JDBC inbound `maxRows` | Rows / query | Limit on rows returned by a single query |
| Splitter | Element count | Breaks a list into individual messages |

`maxMessagesPerPoll(1)` does **not** mean one row. It can correspond to one `SELECT` returning a list of 100 rows, which a splitter turns into 100 messages. Poller transactions only cover work within that transaction scope. If forwarding results to Kafka/JMS or an async executor, **the database mark-read update is not automatically atomic** with broker ACKs.

For systems requiring zero lost events, consider an **outbox table, atomic claim/lease, incomplete-message recovery, and consumer idempotency**. Simply polling a table and marking `PROCESSED` before publishing can lose events if the process crashes between the two steps.

## 16. Exception Translation and Error Handling

Spring JDBC translates driver-specific `SQLException`s into the `DataAccessException` hierarchy. This prevents service code from catching myriad vendor-specific `SQLException` variants directly.

| Exception / scenario | Common cause | Response |
|---|---|---|
| `DuplicateKeyException` | Unique/primary key violation | Check duplicate event vs. conflict |
| `DataIntegrityViolationException` | NOT NULL, FK, check constraints, etc. | Fix data/contract |
| `EmptyResultDataAccessException` | `queryForObject` expected 1 row, got 0 | Map to domain not-found |
| `IncorrectResultSizeDataAccessException` | Unexpected result cardinality | Inspect SQL/uniqueness |
| `BadSqlGrammarException` | Invalid SQL/column/table | Fix migration/query; do not retry blindly |
| `DataAccessResourceFailureException` | Connection/DB unavailable | Bounded retry if transient |
| `CannotAcquireLockException` / deadlock-related exception | Lock contention/serialization conflict | Roll back, then retry entire transactional unit if safe |
| SQL statement returns update count 0 | No rows matched predicate | Business result; not an exception by default |

**Never catch `DataAccessException` and return “default success”** in payment/order pipelines. Turning a connection error into `Optional.empty()` misleads callers into thinking the database is healthy and the order simply does not exist.

### 16.1. Retrying the Right Unit

For deadlocks, retrying a single SQL statement inside an already rollback-only transaction will not work. You normally need to retry **the entire transaction** from the business boundary after rollback, with exponential backoff/jitter and capped attempts.

When a connection drops after the DB may already have committed, the outcome is **uncertain** to the caller; idempotency keys and reconciliation matter more than unbounded retries.

### 16.2. Spring Integration Error Channels

Depending on the endpoint and channel type, a `DataAccessException` may propagate synchronously to the caller, be wrapped in `MessagingException`, or route as an `ErrorMessage` to `errorChannel` on a consumer/poller thread.

- `DirectChannel`: caller may receive the exception directly from `send()`.
- `ExecutorChannel`/poller: errors surface asynchronously, needing an error handler/error channel.
- Kafka/JMS inbound: decide retries, DLQ, and ACK/offset commits per adapter and broker semantics.

Do not assume every JDBC failure becomes an error-payload **reply message**; SQL gateways normally return successful query/update results, while errors follow a separate error path.

## 17. JdbcTemplate Is Blocking I/O: Boundary with WebFlux

An application with a WebFlux inbound gateway might need JDBC for lookups. **Calling `JdbcTemplate` directly on a Reactor Netty event loop blocks the thread**, degrading other HTTP requests.

If you are not using R2DBC, offload blocking JDBC work to an appropriate scheduler/worker with bounded concurrency:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<OrderRecord> lookup = Mono
    .fromCallable(() -> repository.findById("ORD-1001"))
    .subscribeOn(Schedulers.boundedElastic())
    .flatMap(optional -> Mono.justOrEmpty(optional));
~~~

In this snippet, `repository` is the `OrderJdbcRepository` bean and `fromCallable` receives `Optional<OrderRecord>`. `subscribeOn(boundedElastic())` moves the JDBC call onto a worker suited for blocking I/O instead of tying up the event loop.

**Limitation:** `boundedElastic` has its own bounds, but it does not make JDBC non-blocking, does not replace Hikari pool limits, and does not propagate thread-bound transactions across arbitrary reactive signals. If you need **multiple JDBC calls in one transaction**, wrap them in **one synchronous `@Transactional` service method** invoked inside the blocking boundary; do not split individual queries across separate `subscribeOn` calls expecting them to share a connection/transaction.

If your workload requires an end-to-end reactive database stack, evaluate `R2dbcEntityTemplate`/R2DBC with its different contract. Do not treat JDBC and R2DBC as the same stack merely because both run SQL.

## 18. Multiple DataSources and Transaction Managers

With multiple databases, avoid injecting an ambiguous `DataSource`. For example, an app with an orders DB and an audit DB:

~~~java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class MultiDatabaseJdbcConfiguration {

    @Bean("ordersJdbcTemplate")
    public JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("auditJdbcTemplate")
    public JdbcTemplate auditJdbcTemplate(
            @Qualifier("auditDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }
}
~~~

The example assumes **`ordersDataSource` and `auditDataSource` are defined and managed elsewhere**. This is a snippet illustrating qualifiers, not a full application configuring both pools by itself.

With `@Transactional(transactionManager = "ordersTransactionManager")`, only resources enlisted with that transaction manager are managed atomically under its semantics. **Two DataSources with two transaction managers do not automatically commit atomically.** When integrating multiple DBs or DB + broker, consider outbox/CDC, sagas, or an explicitly designed distributed transaction mechanism if truly needed.

## 19. Operations: Pool Sizing, Timeouts, Metrics, and Security

### 19.1. Three Distinct Timeouts

| Timeout | Layer | On expiration |
|---|---|---|
| Hikari `connectionTimeout` | Waiting for a connection | Pool throws timeout if no connection is acquired |
| JDBC `queryTimeout` | Statement execution | Driver/database may cancel or error the statement |
| Spring `@Transactional(timeout=...)` | Service transaction | Transaction manager enforces timeout per resource/infrastructure support |

An application-side timeout **does not guarantee the DB rolled back**. For Kafka/JMS messages, idempotency is essential on redelivery because the DB command may have succeeded even though the confirmation was lost.

To configure query timeouts for `JdbcTemplate` calls, you can use Boot properties like `spring.jdbc.template.query-timeout` when supported by auto-configuration, or configure the template directly. When a JDBC adapter constructs its own template from `DataSource`, verify whether that setting carries over.

### 19.2. Metrics to Monitor

1. **Hikari pool:** active, idle, pending/waiting connections, acquire timeouts, connection creation rate.
2. **Database:** p50/p95/p99 query latency, slow SQL, locks, deadlocks, connection errors, statement timeouts.
3. **IntegrationFlow:** ingress/egress message rates, queue depth, consumer lag, failed messages, retry rates, and DLQ.
4. **Transactions:** commit/rollback counts, transaction duration, outbox backlog.
5. **Business:** `UPDATED=0` ratio, duplicate event IDs, record version conflicts, and data freshness.

Micrometer/Actuator can expose relevant metrics once registry/instrumentation is enabled. Do not assume Hikari metrics or SQL tracing appear automatically just because `spring-boot-starter-jdbc` is present. Avoid high-cardinality metric tags like per-`orderId` or per-`eventId`; use bounded tracing/logs to investigate individual transactions.

### 19.3. Security

- Use a secret manager/environment variables instead of hardcoding DB passwords.
- Apply least-privilege DB accounts (`SELECT/INSERT/UPDATE/DELETE/EXECUTE`) scoped to required tables/procedures.
- Enforce proper vendor TLS/truststore settings; never disable certificate validation to bypass errors.
- Bind parameters, validate inputs, and allowlist dynamic SQL identifiers.
- Never log full SQL parameters, tokens, or PII; log controlled correlation IDs and error categories.
- Verify tenant/authorization before writing; a `tenantId` message header does not prove caller authorization for that tenant.

## 20. Testing DataSource, JdbcTemplate, and Transactions

### 20.1. Spring Boot Integration Test on H2

Using the schema and sample data from section 3:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class OrderJdbcRepositoryTest {

    @Autowired
    OrderJdbcRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void queryAndOptimisticUpdate() {
        String id = "ORD-" + UUID.randomUUID();
        jdbc.update(
            "INSERT INTO order_projection "
          + "(order_id, status, total_amount, version) "
          + "VALUES (?, ?, ?, ?)",
            id, "RECEIVED", new java.math.BigDecimal("50000.00"), 0);

        OrderRecord before = repository.findById(id).orElseThrow();
        assertEquals("RECEIVED", before.status());

        assertEquals(1, repository.changeStatus(
            id, "RECEIVED", "PAID", 0));
        assertEquals(0, repository.changeStatus(
            id, "RECEIVED", "PAID", 0));

        OrderRecord after = repository.findById(id).orElseThrow();
        assertEquals("PAID", after.status());
        assertEquals(1, after.version());
    }
}
~~~

This test verifies **row mapping, update counts, and optimistic locking**. To test real transaction rollback, invoke a **`@Transactional` service through its Spring bean proxy**, deliberately throw an exception after the first SQL statement, and then query from a separate transaction/connection. If the test method itself is annotated `@Transactional` and rolls back at the end, seeing data within that same transaction **does not prove a commit happened**.

### 20.2. Testing with a Production-Compatible Database

H2 is great for basic unit/integration tests, but significant differences exist in locking, generated keys, SQL dialects, isolation, and types. For critical systems, test with Testcontainers or a vendor-matched test database:

| Scenario | What to verify |
|---|---|
| Wrong password, DB down | Correct pool timeout/connection exception types |
| 0/1/many rows from query | `query` and `queryForObject` handle cardinality properly |
| UPDATE version mismatch | `affectedRows=0`, status not overwritten |
| Duplicate key | Appropriate exception raised; duplicate vs. conflict distinguished |
| Multi-statement transaction | Full rollback when an error occurs mid-transaction |
| Batch with one failing item | Rollback/partial result behavior per DB/driver and transaction |
| Generated keys | Key names/types match production DB |
| Pool exhausted | Backpressure/bounded queues and timeouts work properly |
| ExecutorChannel instead of DirectChannel | Transaction/ACK/reply semantics shift |
| Kafka/JMS redelivery | No duplicated outbox/business side effects |
| Poller marks rows read | No lost events on crash after DB update before broker publish |

## 21. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “DataSource is a fixed single JDBC Connection” | It is a connection-providing interface, usually backed by a pool |
| “JdbcTemplate creates a new pool for every SQL call” | The template **reuses the injected DataSource** |
| “DataSourceUtils/JdbcTemplate commits every operation immediately” | Inside a transaction, commits follow the transaction manager |
| “`send() == true` means the DB committed” | Depends on channel/transaction boundaries |
| “`maximumPoolSize=20` means 20 SQL/sec” | It is a connection limit, not a throughput rate |
| “`connectionTimeout` is the query timeout” | One waits on the pool; the other bounds SQL statements |
| “SELECT returning 0 rows must be a database error” | Usually a normal business outcome |
| “queryForObject with 0 rows returns null” | Normally throws `EmptyResultDataAccessException` |
| “NamedParameterJdbcTemplate and Integration SpEL are the same” | Named SQL binding differs from SpEL/custom parameter factories |
| “`batchUpdate` always returns exact per-row counts” | Drivers may return `SUCCESS_NO_INFO` and various partial results |
| “@Transactional on the caller propagates across ExecutorChannel” | Thread-bound transactions do not follow worker threads |
| “JDBC inside a WebFlux app is non-blocking” | JDBC is blocking; needs worker boundaries or R2DBC |
| “JDBC outbound adapter creates a reply count automatically” | Needs a gateway or result-returning service activator |
| “Retrying DB errors is always safe” | Outcomes can be uncertain; idempotency is required |
| “Increasing pool/concurrency endlessly solves lock contention” | Can overload the database further |

## 22. Practice Exercises

1. Initialize H2 per section 3, inject `DataSource`, `JdbcTemplate`, and `NamedParameterJdbcTemplate`, and verify they share the same datasource.
2. Write `RowMapper<OrderRecord>` for `order_projection` and compare `BigDecimal` against `double`.
3. Run `query` and `queryForObject` for 0, 1, and multiple rows; record the actual exceptions thrown.
4. Implement order lookup returning `Optional<OrderRecord>` without swallowing `DataAccessException` as “not found”.
5. Execute an UPDATE with `WHERE version = ?`, send two commands with the same version, and confirm one returns 0.
6. Port a query to `NamedParameterJdbcTemplate` with `IN (:statuses)` and handle empty lists safely.
7. Use `batchUpdate` to update multiple orders; test one failing element, update counts, and transaction rollback.
8. Insert a row into `outbox_event`, retrieve the generated key with `KeyHolder`, and test unique `event_id`.
9. Wrap the UPDATE and outbox INSERT in a `@Transactional` service; throw mid-method and verify rollback.
10. Swap an input `DirectChannel` for `ExecutorChannel` and observe threads, connections, and transaction boundaries.
11. Build a one-way JDBC outbound adapter with Java DSL 7.x; replace it with a service activator when downstream needs the update count.
12. Configure a JDBC inbound poller, bound `maxRows` vs. `maxMessagesPerPoll`, and add a splitter for list rows.
13. Build a WebFlux endpoint calling `JdbcTemplate`, offload blocking work to `Schedulers.boundedElastic()`, and measure event-loop impact.
14. Lower Hikari pool size to 1 and send concurrent requests; distinguish connection acquire timeouts from SQL statement timeouts.
15. Connect a Kafka/JMS source and simulate a crash after DB commit before ACK; design an idempotency/outbox table and redelivery flow.
16. Separate two DataSources to practice `@Qualifier`, `@Primary`, and transaction managers; verify that two local transactions are not atomic by default.

**Comprehensive scenario:** Kafka delivers `order.paid`, a `DirectChannel` dispatches to a service that updates the database via `JdbcTemplate` and writes to an outbox. After the DB commits, the application crashes before ACKing Kafka; the message is redelivered. Describe the transaction boundaries, event ID, optimistic versioning, unique constraints, ACK mechanism, outbox publisher, and why raising `maximumPoolSize` does not solve the “no duplicate side effects” requirement.

## 23. References

- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource` auto-configuration, HikariCP, `JdbcTemplate`, and `NamedParameterJdbcTemplate`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, queries/updates, batching, `RowMapper`, and generated keys.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils`, and transaction-aware connections.
- [Spring Framework — JDBC Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, local transactions, propagation, and rollback.
- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC inbound/outbound adapters, gateways, stored procedures, and JDBC message store.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc` factory from Spring Integration 7.0.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): poller, `SELECT`/`UPDATE`, `maxRows`, and transactions.
- [Spring Integration — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): `DataSource`/`JdbcTemplate`, parameter binding, prepared statement callbacks, and batching.
- [Spring Integration — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): reply rows/update counts/generated keys.
- [HikariCP Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): connection pool sizing, acquire timeouts, and lifecycle settings.

> **Remember:** `DataSource` manages **the pool of connections**, `JdbcTemplate` manages **JDBC execution and JDBC resources**, and Spring Integration adapters/gateways manage **how messages trigger SQL and whether replies are emitted**. Reliable operation requires sharing the pool, binding parameters safely, aligning transactions with threads/resources, distinguishing 0-row results from infrastructure errors, bounding load, and designing idempotency for redelivered messages.

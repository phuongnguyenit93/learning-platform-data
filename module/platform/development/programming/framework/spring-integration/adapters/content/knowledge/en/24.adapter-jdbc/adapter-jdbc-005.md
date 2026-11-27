# JDBC Outbound Gateway Returning Results in Spring Integration

## 1. Why Do We Need a JDBC Outbound Gateway?

A Spring Integration flow might receive an order lookup request over HTTP, consume an `order.paid` event from Kafka, or receive a JMS message. After sending a SQL operation to the database, the next step sometimes **needs to know the result**:

- How many rows did the `UPDATE` actually modify?
- What ID did the database assign to the `INSERT`ed record?
- Was the order found by key? If so, what are the returned columns?
- After updating status, what is the latest data to send downstream to another system?

The **JDBC outbound gateway** handles this **request–reply** interaction pattern. It receives a `Message<?>` from an input `MessageChannel`, executes SQL `UPDATE/INSERT/DELETE` and/or `SELECT` via Spring JDBC, and sends a **reply message** containing the result to the output channel or corresponding `replyChannel`. The implementation class is `JdbcOutboundGateway`, an `AbstractReplyProducingMessageHandler`.

This topic belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; those systems may be files, SFTP, HTTP, JMS, AMQP, Kafka, or databases. For the JDBC outbound gateway, the focus is on **request/reply contracts, parameter mapping, result shapes, transactions, and errors**.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / JMS / Service"] --> B["Message<Command>"]
    B --> C["requestChannel"]
    C --> D["JDBC outbound gateway"]
    D --> E["DataSource / JdbcTemplate"]
    E --> F[("Database")]
    F -->|"Rows / update count / generated keys"| E
    E --> D
    D --> G["Message<Result>"]
    G --> H["replyChannel"]
    H --> I["Router / HTTP reply / next adapter"]
~~~

**Do not confuse:** *outbound* describes calling **out to the database**, not outbound HTTP. A *gateway* must produce a **reply** for the flow, unlike the JDBC outbound channel adapter which only executes one-way DML.

## 2. Placing the Gateway Among Other JDBC Endpoints

| Endpoint | Who triggers it? | SQL statements | Returns results to the flow? |
|---|---|---|---|
| JDBC inbound channel adapter | Poller | Scheduled `SELECT` | Emits messages from DB, no request–reply pair |
| JDBC outbound channel adapter | Message arriving on channel | DML: `INSERT/UPDATE/DELETE` | **No** business reply created |
| **JDBC outbound gateway** | **Message on request channel** | **DML**, **SELECT**, or **DML + SELECT** | **Yes**: update count, generated keys, rows |
| Stored procedure inbound adapter | Poller | Calls procedure/function | Emits results periodically |
| Stored procedure outbound adapter | Message arriving on channel | Calls procedure for side effects | No reply created |
| Stored procedure outbound gateway | Message arriving on channel | Procedure/function with OUT/result sets | Reply per procedure contract |

Choose the JDBC outbound gateway when downstream genuinely needs the result. For instance, `UPDATE ... WHERE id=? AND status=?` can affect **0 rows** without SQL throwing an error. If business logic must emit `order.updated` only when a row changed status, the gateway retrieves the update count so a router can decide.

For complex operations involving multiple SQL statements, domain validation, and dedicated transactions, a service activator calling `JdbcTemplate` or a repository service may be easier to maintain. The gateway fits best when a request–reply SQL contract is clean enough to live in a single endpoint.

## 3. Three Main Reply Shapes and Expected Payload Types

According to Spring Integration JDBC, the reply depends on the SQL mode:

| Gateway configuration | Typical reply payload | Notes |
|---|---|---|
| **`update` only**, no `query` and no generated keys | `Map` containing `UPDATED`, e.g. `{UPDATED=1}` | Reports total affected row count |
| **`update` with `keysGenerated=true`** | Map/list of **generated keys** from JDBC driver | Key names and support depend on database |
| **`query` only** | Single row, or list of rows depending on `maxRows` | Useful for message-driven lookups |
| **`update` + `query`** | `SELECT` result after the update executes | Define clear SELECT contract and transaction |
| `query` finds no rows, list mode | **Empty list** since Spring Integration 6.0 | Does not automatically mean “no reply” |

Examples:

~~~text
Message<{orderId:"ORD-1001",status:"PAID"}>
    -> UPDATE order_projection SET status='PAID' WHERE order_id='ORD-1001'
    -> Reply Message<{UPDATED=1}>

Message<{orderId:"ORD-1001"}>
    -> SELECT order_id,status,total_amount FROM order_projection ...
    -> Reply Message<OrderView>    (default maxRows is 1)
~~~

With `maxRows(0)`, the `SELECT` result can be `List<OrderView>`, even when 0 or 1 row is found. Do not write a consumer that always casts to `List` if you configured the gateway for a **single row**; likewise, do not cast the reply to a single row if you requested **multiple rows**.

**Two distinct semantics:** a SQL `UPDATE` returning `UPDATED=0` is not equivalent to a `SELECT` returning an empty list. Both represent different business conditions and must be checked separately.

## 4. Sample Project and Test Schema

Examples use Java 17+, Spring Boot, Spring Integration JDBC, Spring JDBC, and H2 for standard SQL statements. Let the Spring Boot BOM manage compatible versions:

~~~groovy
// build.gradle - dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

~~~yaml
# application.yml - for H2 example only
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_gateway_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

In `src/main/resources/schema.sql` of the **sample** project, you can place:

~~~sql
CREATE TABLE order_projection (
    order_id      VARCHAR(64) PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    total_amount  DECIMAL(18, 2) NOT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE order_audit (
    audit_id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id   VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL
);
~~~

Sample data:

~~~sql
INSERT INTO order_projection (order_id, status, total_amount)
VALUES ('ORD-1001', 'RECEIVED', 125000.00),
       ('ORD-1002', 'RECEIVED', 75000.00),
       ('ORD-1003', 'SHIPPED', 30000.00);
~~~

In production applications, use migrations (Flyway/Liquibase) to manage schema, least-privilege permissions, and backups. H2 is convenient for explaining SQL; generated keys, locking, isolation, and data types can differ from PostgreSQL, MySQL, SQL Server, or Oracle.

### 4.1. Java DSL Introduced in Spring Integration 7.0

The following `Jdbc.outboundGateway(...)` examples target **Spring Integration 7.x**. Official documentation notes that the `org.springframework.integration.jdbc.dsl.Jdbc` factory was introduced in **7.0**. If your project uses **6.x**, do not copy these DSL factory calls: section 12 covers `JdbcOutboundGateway` + `@ServiceActivator` or XML.

In 7.x, the main handler class lives in package `org.springframework.integration.jdbc.outbound.JdbcOutboundGateway`; in 6.x, use `org.springframework.integration.jdbc.JdbcOutboundGateway`. Always verify imports and configuration against your active dependency version.

## 5. Example 1: UPDATE and Receiving the Affected Row Count

### 5.1. Request Contract

The flow receives a `Map<String, Object>` payload containing:

~~~json
{
  "orderId": "ORD-1001",
  "expectedStatus": "RECEIVED",
  "newStatus": "PAID"
}
~~~

The SQL uses named parameters from the message:

~~~sql
UPDATE order_projection
SET status = :payload[newStatus],
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :payload[orderId]
  AND status = :payload[expectedStatus];
~~~

The `AND status = :payload[expectedStatus]` condition acts as a **simple optimistic check**: if another flow already changed the status, the update count can be 0. In real production systems, use a `version` column or explicit state-transition rules to prevent backward status overwrites.

### 5.2. Java DSL 7.x

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderUpdateGatewayFlow {

    @Bean
    public MessageChannel statusRequests() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel statusReplies() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow updateOrderStatus(
            DataSource dataSource,
            @Qualifier("statusRequests") MessageChannel requests) {
        return IntegrationFlow.from(requests)
            .handle(Jdbc.outboundGateway(dataSource,
                "UPDATE order_projection "
              + "SET status = :payload[newStatus], "
              + "    updated_at = CURRENT_TIMESTAMP "
              + "WHERE order_id = :payload[orderId] "
              + "  AND status = :payload[expectedStatus]"))
            .channel("statusReplies")
            .get();
    }
}
~~~

**Point-by-point explanation:**

1. `statusRequests` is the input `DirectChannel`; messages arriving here trigger the gateway immediately on the synchronous dispatch path.
2. `Jdbc.outboundGateway(dataSource, updateSql)` creates a `JdbcOutboundGateway` and configures DML execution.
3. `:payload[orderId]`, `:payload[newStatus]`, and `:payload[expectedStatus]` are resolved from the **request message's Map payload**, never concatenated directly into the SQL string.
4. The handler executes SQL and builds a reply; if one row is updated, the reply payload is a map containing `UPDATED=1`.
5. `.channel("statusReplies")` routes the reply to a `QueueChannel` so demos/tests can call `receive()`. In a real synchronous workflow, this could be replaced by a router or service activator.
6. `statusReplies` is an **output reply channel**, not a poller reading from the database; `receive()` is simply how the application inspects emitted results.

### 5.3. Sending a Message and Reading the Reply

~~~java
import java.util.Map;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

// requests and replies are injected via their respective @Qualifier.
boolean sent = requests.send(MessageBuilder.withPayload(
    Map.of(
        "orderId", "ORD-1001",
        "expectedStatus", "RECEIVED",
        "newStatus", "PAID"))
    .setHeader("correlationId", "req-1001")
    .build());

if (!sent) {
    throw new IllegalStateException("Request was not accepted");
}

Message<?> reply = replies.receive(1_000);
if (reply == null) {
    throw new IllegalStateException("No JDBC reply received");
}

Map<?, ?> result = (Map<?, ?>) reply.getPayload();
Number updated = (Number) result.get("UPDATED");
System.out.println("Updated rows = " + updated.intValue());
~~~

Assume `requests` is the `statusRequests` `MessageChannel` bean and `replies` is the `statusReplies` `PollableChannel` bean. Both beans must be injected or fetched from the Spring context; these variables do not exist out of thin air in a static `main`.

**`UPDATED=1`** means the UPDATE affected one row; **`UPDATED=0`** means no row matched the predicate. An UPDATE returning 0 does not throw an exception by default, nor does it prove the order does not exist: it may mean **the order already changed status**. Distinguish not-found from conflict when the workflow requires it.

### 5.4. Why the Input Channel Does Not Guarantee Commit

In the `DirectChannel` example, the JDBC handler runs synchronously. Without an outer transaction, the database typically executes/commits according to JDBC settings. However, if `requests.send(...)` is called inside an in-progress `@Transactional` method, the transaction can still **roll back after the `UPDATED=1` reply has been emitted**. The reply reports what the SQL statement executed, **not a final durable commit certificate**.

## 6. Routing on Update Count and Business Contracts

If you need logic such as “updated exactly 1 row → emit event, 0 rows → signal conflict”, a router can inspect `UPDATED`:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import java.util.Map;

@Bean
IntegrationFlow routeUpdateResult() {
    return IntegrationFlow.from("statusResultInput")
        .route(message -> {
            Map<?, ?> map = (Map<?, ?>) message.getPayload();
            int updated = ((Number) map.get("UPDATED")).intValue();
            return updated == 1 ? "updated" : "notUpdated";
        }, mapping -> mapping
            .channelMapping("updated", "updatedOrders")
            .channelMapping("notUpdated", "conflictedOrders"))
        .get();
}
~~~

This is a **standalone illustrative flow**; to connect it with the section 5 example, change the gateway's output channel to `statusResultInput` rather than having both `statusReplies` and `statusResultInput` consume one reply without a publish-subscribe design. The router's input must be a `Map` with `UPDATED`; do not reuse this router for a `SELECT` returning a DTO or an `INSERT` returning generated keys.

For idempotent commands, `UPDATED=0` is not necessarily an error: if the event was already processed earlier, the database may already be in the target state. When deciding whether to ACK Kafka/JMS, reconcile against state/event IDs instead of treating every zero as “unprocessed”.

## 7. Example 2: SELECT by Request Message Returning a Single Row

Not every gateway needs to write data. Since Spring Integration 2.2, `JdbcOutboundGateway` supports **SELECT-only queries**, which is useful for enriching payloads or answering lookup HTTP requests.

### 7.1. Using Java DSL 7.x with SELECT Only

~~~java
package com.example.jdbc;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class OrderLookupFlow {

    public record OrderView(
        String orderId, String status, BigDecimal totalAmount) { }

    @Bean
    public IntegrationFlow lookupOrder(DataSource dataSource) {
        return IntegrationFlow.from("lookupRequests")
            .handle(Jdbc.outboundGateway(
                    dataSource,
                    null, // Do not run UPDATE.
                    "SELECT order_id, status, total_amount "
                  + "FROM order_projection "
                  + "WHERE order_id = :payload[orderId]")
                .maxRows(1)
                .rowMapper((rs, rowNum) -> new OrderView(
                    rs.getString("order_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("total_amount"))))
            .channel("lookupReplies")
            .get();
    }
}
~~~

**Note:** the three-argument overload `Jdbc.outboundGateway(dataSource, updateQuery, selectQuery)` makes combined mode explicit. Per the JDBC outbound gateway contract, `updateQuery` may be omitted when only `SELECT` is needed; here `null` indicates “no DML”, while `selectQuery` is provided. If using a different library version, check constructor/factory signatures before use.

With `maxRows(1)` and one matching row, the reply payload is a **single `OrderView`**, not `List<OrderView>`. Without a `rowMapper`, the default mapper produces a `Map<String, Object>` keyed by column names.

Sample input message:

~~~java
Map<String, String> criteria = Map.of("orderId", "ORD-1001");
lookupRequests.send(MessageBuilder.withPayload(criteria).build());
~~~

To run this snippet, `lookupRequests` must be injected as a `MessageChannel`, `MessageBuilder` imported, and `lookupReplies` wired to a downstream consumer (or a `QueueChannel` bean for `receive()`). Always verify result types in tests instead of assuming every SELECT returns a list.

### 7.2. Zero Rows vs. One Row Differ

When `SELECT` finds no matching rows, the response shape depends on `maxRows` and version behavior. Since Spring Integration **6.0**, when the result is an empty list, the gateway **keeps the empty list as the reply** rather than converting it to `null` meaning “no reply”.

Do not rely on a rule like “no reply received means the database has no record”. For single-row lookups, write tests covering **0 rows**, **1 row**, and **multiple rows** in your target version, especially if an upstream HTTP gateway has a reply timeout.

If a public API must return `404 Not Found`, map the missing-record condition explicitly at the business layer rather than letting an empty `List<?>` accidentally turn into a confusing HTTP `200` success.

## 8. `maxRows`: One Row, Multiple Rows, Empty Lists

The default `maxRows` of the JDBC outbound gateway is **1** for `SELECT`. For queries that should return all matching rows, set `maxRows(0)`.

~~~java
@Bean
IntegrationFlow listOrders(DataSource dataSource) {
    return IntegrationFlow.from("listOrderRequests")
        .handle(Jdbc.outboundGateway(
                dataSource,
                null,
                "SELECT order_id, status, total_amount "
              + "FROM order_projection "
              + "WHERE status = :payload[status] "
              + "ORDER BY order_id")
            .maxRows(0)
            .rowMapper((rs, rowNum) ->
                new OrderLookupFlow.OrderView(
                    rs.getString("order_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("total_amount"))))
        .channel("listOrderReplies")
        .get();
}
~~~

With input `{"status":"RECEIVED"}`, the reply can be a `List<OrderView>` containing multiple records. When `maxRows(0)`, an empty list is still a meaningful result: “query succeeded and found no matching rows”.

| Configuration value | Practical meaning | Downstream reply |
|---|---|---|
| `maxRows` omitted | Defaults to limit 1 | Typically one row/map/DTO when data exists |
| `maxRows(1)` | Fetch at most one row | Typically one row when data exists |
| `maxRows(5)` | Limit to at most 5 rows | Multiple rows return a list; test single-row behavior |
| `maxRows(0)` | No gateway row-count cap | List of rows, possibly empty |

**Do not use `maxRows(0)` to load a million-row table into a single message** without constraints. The gateway typically materializes the `SELECT` result into a collection before emitting the reply. Large datasets require pagination, keyset cursors, result limits, batching, or an appropriate streaming protocol.

### 8.1. When You Want One Message Per Row

If `maxRows(0)` returns `List<OrderView>`, downstream can apply a splitter:

~~~java
.handle(Jdbc.outboundGateway(dataSource, null, selectSql)
    .maxRows(0)
    .rowMapper(orderRowMapper))
.split()
.channel("oneOrderPerMessage")
~~~

This is a **Java DSL fragment**; `selectSql` and `orderRowMapper` are variables/beans provided by the application. `split()` turns each list element into a separate message; it **does not** make the JDBC query reactive or turn SQL into cursor streaming with automatic backpressure.

## 9. Example 3: INSERT and Receiving Generated Keys

When a table uses an auto-increment primary key, the outbound gateway can retrieve the key generated by the database. Example using the `order_audit` table from section 4:

~~~sql
INSERT INTO order_audit (order_id, event_type)
VALUES (?, ?);
~~~

Java DSL:

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class OrderAuditGatewayFlow {

    @Bean
    public IntegrationFlow insertAuditAndReturnKey(DataSource dataSource) {
        return IntegrationFlow.from("auditRequests")
            .handle(Jdbc.outboundGateway(dataSource,
                    "INSERT INTO order_audit (order_id, event_type) "
                  + "VALUES (?, ?)")
                .requestPreparedStatementSetter((ps, message) -> {
                    // Assumes payload is Map<String,Object>.
                    var payload = (java.util.Map<?, ?>) message.getPayload();
                    ps.setString(1, payload.get("orderId").toString());
                    ps.setString(2, payload.get("eventType").toString());
                })
                .keysGenerated(true))
            .channel("auditKeys")
            .get();
    }
}
~~~

In this example:

1. `requestPreparedStatementSetter(...)` uses `MessagePreparedStatementSetter` to bind `?` parameters directly from the request message.
2. `keysGenerated(true)` tells JDBC to retrieve generated keys (not all DBs/drivers support key retrieval identically).
3. The gateway returns key results in a Map/list-of-maps structure depending on the DB driver, settings, and row count; **do not hardcode** that the key name is always `audit_id` or `ID`.
4. Inspect the actual reply and convert it into a validated DTO `AuditCreated(auditId, ...)` inside a transformer if downstream needs a stable type.

**Do not configure `requestPreparedStatementSetter` and `requestSqlParameterSourceFactory` simultaneously when both define how to bind the same UPDATE/INSERT.** They are alternative binding strategies suited to different SQL/DTO styles.

### 9.1. Generated Keys Do Not Equal Idempotency

If the application times out or the broker redelivers after the INSERT already committed, a retry can create **two** audit rows with **two generated IDs**. If the operation must run once per `eventId`, use a unique constraint or idempotency table; never rely on auto-generated keys alone.

## 10. Example 4: UPDATE Followed by SELECT Returning the Updated Record

The gateway can execute DML first and then `SELECT` to fetch the current state within the same message handling pass. This fits the “update order status then return DTO” use case.

~~~java
@Bean
IntegrationFlow updateAndRead(DataSource dataSource) {
    return IntegrationFlow.from("updateAndReadRequests")
        .handle(Jdbc.outboundGateway(
                dataSource,
                "UPDATE order_projection "
              + "SET status = :payload[newStatus], "
              + "    updated_at = CURRENT_TIMESTAMP "
              + "WHERE order_id = :payload[orderId]",
                "SELECT order_id, status, total_amount "
              + "FROM order_projection "
              + "WHERE order_id = :payload[orderId]")
            .maxRows(1)
            .rowMapper((rs, n) -> new OrderLookupFlow.OrderView(
                rs.getString("order_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"))))
        .channel("orderAfterUpdate")
        .get();
}
~~~

**The two steps mean different things:**

- `UPDATE` determines what mutation was applied. If no row matched, UPDATE may affect 0 rows.
- `SELECT` determines the **reply payload** sent downstream. If the query finds a row, downstream can receive an `OrderView` even if UPDATE modified zero rows (for example, the record was already in the target state or matched a different predicate).

**Be careful about transactions and consistency:** when `UPDATE + SELECT` must share the same transaction/isolation boundary, configure an explicit transaction manager. `JdbcOutboundGateway` is a synchronous endpoint, but it does not automatically replace all business concurrency and transaction controls. The SELECT data could still be affected by concurrent transactions depending on DB isolation/locking.

If downstream needs **both the update count and the row**, do not assume the gateway automatically returns a `(UPDATED, OrderView)` tuple. Use a service activator running SQL in a transaction to build a custom DTO, or separate stages with explicit persistence/reconciliation contracts.

### 10.1. Querying After INSERT with Generated Keys

When `keysGenerated(true)` is configured, the default parameter source for the **reply SELECT** can be the **generated keys** (a map or list of maps) instead of the original request message. The `SELECT` statement must reference the exact key returned by JDBC with the driver-supported column name; otherwise you risk binding failures or queries returning zero rows.

This is one reason to test both generated-key replies and SELECT-after-INSERT against your production database/driver. H2, PostgreSQL, SQL Server, and Oracle do not necessarily return the same key names or use the same generated-key strategy.

## 11. SQL Binding: Named Parameters, PreparedStatement, and RowMapper

The JDBC outbound gateway has two binding sides:

1. **Request side:** bind parameters for `UPDATE/INSERT/DELETE` when DML is present.
2. **Reply side:** bind parameters for `SELECT` when a result query is present.

When using named parameters, the default root context exposes request `payload` and `headers`:

~~~sql
UPDATE order_projection
SET status = :payload[newStatus]
WHERE order_id = :payload[orderId];

SELECT *
FROM order_projection
WHERE order_id = :payload[orderId];
~~~

These examples assume `payload` is a Map with matching keys. For a Java record DTO, verify property access in the parameter source or configure an explicit factory/binder; do not assume camelCase field names automatically map to snake_case SQL columns.

| Mechanism | Used for | Key caveats |
|---|---|---|
| Named parameters `:payload[orderId]` | SQL needing message values | Depends on root context and property paths |
| `requestSqlParameterSourceFactory` | Custom DML binding | Supports transformation/type expressions |
| `requestPreparedStatementSetter` | Direct JDBC `?` binding for DML | 1-based parameter indices |
| `replySqlParameterSourceFactory` | Dedicated `SELECT` binding | Important when SELECT uses generated keys |
| `rowMapper(...)` | Map each JDBC row to a Java object | Avoids coupling downstream to driver-specific `Map` column names |

### 11.1. RowMapper to Avoid Map Casting Everywhere

~~~java
import org.springframework.jdbc.core.RowMapper;
import java.math.BigDecimal;

RowMapper<OrderLookupFlow.OrderView> mapper = (rs, rowNum) ->
    new OrderLookupFlow.OrderView(
        rs.getString("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"));
~~~

Column names in `RowMapper` must match the `SELECT` list or aliases. For nullable SQL columns, handle nulls explicitly (such as checking `ResultSet.wasNull()` for primitives) rather than silently producing invalid business values.

### 11.2. Preventing SQL Injection

PreparedStatement placeholders and named parameters bind **values**, not table names, column names, arbitrary `ORDER BY` clauses, or full SQL fragments. If input requests varying sort orders or target tables, pick from an application-controlled allowlist; never concatenate `payload.tableName` into SQL.

## 12. Spring Integration 6.x: Java Bean and XML

In 6.x, `Jdbc.outboundGateway(...)` from JDBC Java DSL 7.x does not exist yet. `JdbcOutboundGateway` still exists and can be registered as a reply-producing `MessageHandler`.

### 12.1. Declaring the Handler Bean Directly

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcOutboundGateway;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyJdbcGatewayConfiguration {

    @Bean
    @ServiceActivator(
        inputChannel = "legacyStatusRequests",
        outputChannel = "legacyStatusReplies")
    public MessageHandler jdbcStatusGateway(DataSource dataSource) {
        return new JdbcOutboundGateway(
            dataSource,
            "UPDATE order_projection "
          + "SET status = :payload[newStatus] "
          + "WHERE order_id = :payload[orderId]");
    }
}
~~~

This is the **6.x approach** for creating an outbound gateway. If you also need SELECT, use the constructor taking `selectQuery` and configure `setMaxRows(...)`/`setRowMapper(...)`. In 7.x with manual handler wiring, import `org.springframework.integration.jdbc.outbound.JdbcOutboundGateway`.

### 12.2. XML Configuration

~~~xml
<!-- Fragment in Spring XML with int/int-jdbc namespaces declared. -->
<int:channel id="orderLookupRequests"/>
<int:channel id="orderLookupReplies"/>

<int-jdbc:outbound-gateway
    id="orderLookupGateway"
    request-channel="orderLookupRequests"
    reply-channel="orderLookupReplies"
    data-source="dataSource"
    query="SELECT order_id, status, total_amount
           FROM order_projection
           WHERE order_id = :payload[orderId]"
    max-rows="1"/>
~~~

In XML form, `query` can stand alone without `update`, per the JDBC outbound gateway contract. This is an **alternative configuration style**; do not also register Java DSL for the same channels.

### 12.3. Update Count via XML

~~~xml
<int-jdbc:outbound-gateway
    id="legacyUpdateGateway"
    request-channel="updateRequests"
    reply-channel="updateReplies"
    data-source="dataSource"
    update="UPDATE order_projection
            SET status = :payload[newStatus]
            WHERE order_id = :payload[orderId]"/>
~~~

The default reply for DML is a `UPDATED` map. With `keys-generated="true"` on an INSERT, the reply switches to generated keys per DB contract; do not simultaneously expect `UPDATED` as the primary payload.

## 13. Reply Channel, Correlation, and Request–Reply Workflows

### 13.1. Where Does the Reply Go?

`JdbcOutboundGateway` is an `AbstractReplyProducingMessageHandler`. Replies can go to the output channel configured on the endpoint, or to the `replyChannel` header on the request when no fixed output channel is specified.

~~~mermaid
sequenceDiagram
    participant Caller as Request producer
    participant Input as requestChannel
    participant JDBC as JdbcOutboundGateway
    participant DB as Database
    participant Reply as replyChannel
    Caller->>Input: Message<Command> + reply context
    Input->>JDBC: handle
    JDBC->>DB: SQL query/update
    DB-->>JDBC: Rows/count/keys
    JDBC-->>Reply: Message<Result>
    Reply-->>Caller: Per request-reply contract
~~~

In the section 5 `QueueChannel` example, replies go to `statusReplies` because the DSL specifies an output channel. If a `@MessagingGateway` sends a request and awaits a reply, check how `replyChannel` is created/propagated; attaching a different static output channel can leave the caller waiting forever unless bridged back to the reply context.

**Correlation IDs** link input and output messages; do not treat `MessageHeaders.ID` as a complete replacement for a business `eventId`. When splitting lists or publishing through a broker, a stable business event ID is usually far more useful than a newly generated Spring Integration message ID.

### 13.2. No Reply vs. Empty Reply

A `Message<List<?>>` containing an empty list **is still a message**. In older versions, an empty SELECT result could be turned into `null` resulting in no reply; since Spring Integration 6.0, the gateway preserves empty list results. If an HTTP workflow should return `404` or `204`, define an explicit business mapping.

Specifically, a `@MessagingGateway` with a reply timeout should not use “no reply received” merely to signify that the DB has no row; timeouts can also stem from channel, handler, or transaction failures.

## 14. Transactions and Concurrency: A Reply Is Not a Commit Receipt

### 14.1. DirectChannel and Same-Thread Execution

With `DirectChannel`, the gateway normally executes SQL on the producer's thread. If an active `@Transactional` manages the connection through the matching transaction manager, JDBC operations can join that transaction.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PaymentService {

    private final org.springframework.messaging.MessageChannel requests;

    PaymentService(
            @org.springframework.beans.factory.annotation.Qualifier(
                "statusRequests")
            org.springframework.messaging.MessageChannel requests) {
        this.requests = requests;
    }

    @Transactional
    public void markPaid(String orderId) {
        // Request message runs on the current thread/transaction
        // when dispatched via DirectChannel and a synchronous JDBC handler.
        // The reply can still be emitted before outer commit time.
        requests.send(
            org.springframework.messaging.support.MessageBuilder
                .withPayload(java.util.Map.of(
                    "orderId", orderId,
                    "expectedStatus", "RECEIVED",
                    "newStatus", "PAID"))
                .build());
    }
}
~~~

**If the transaction rolls back after the gateway already returned `UPDATED=1`, the database does not retain the change.** Therefore, never publish an irreversible event to Kafka solely on the basis of an update-count reply before the transaction commits.

### 14.2. ExecutorChannel / QueueChannel

If you swap `DirectChannel` for `ExecutorChannel`, dispatching moves to a worker thread; the sender's transaction does not follow automatically. With `QueueChannel`/poller, the message may be processed later after the sending transaction has already finished. That changes error propagation, reply timeouts, and ACK guarantees.

| Boundary | When does SQL run? | Control recommendations |
|---|---|---|
| DirectChannel | On sender's call path | Transaction manager, exceptions, commit happens after reply |
| ExecutorChannel | Executor thread | Bounded pool/queue, transaction at worker |
| QueueChannel + poller | Poller receives message | Poller transaction, error channel, reply timeout |
| Kafka/JMS inbound | Per listener/adapter | ACK/offset commit, redelivery, idempotency |

**There is no automatic distributed transaction** spanning JDBC, Kafka, JMS, and HTTP just because they live in one `IntegrationFlow`. When you need to write to a database and emit an event, prefer a transactional outbox or an explicitly designed consistency protocol.

### 14.3. Contended Update-and-Select

An “UPDATE status then SELECT record” flow can still be interleaved by concurrent transactions. For business commands needing strict state control, include a `version` column, condition the update on version, and handle `UPDATED=0`; merely re-selecting the row does not prove your command was the one applied.

## 15. SQL Errors, Timeouts, Retries, and Idempotency

Spring JDBC translates many `SQLException`s into `DataAccessException`; Spring Integration may wrap them further in `MessagingException` when a handler fails. Do not confuse a successful SQL query returning zero rows with an exception.

| Case | Typical outcome | Sensible action |
|---|---|---|
| UPDATE matches no rows | `UPDATED=0` | Distinguish not-found, stale version, or duplicate |
| Primary/unique key collision | `DuplicateKeyException` | Check idempotency/conflict; do not retry infinitely |
| Constraint violation | `DataIntegrityViolationException` | Validation/contract error |
| Temporary DB disconnect | `DataAccessResourceFailureException` or driver cause | Bounded retry, reconcile outcome |
| Deadlock/serialization | DB-specific transient data access exception | Roll back and retry **the entire transactional unit** |
| SELECT finds no rows | Empty reply per shape/version | Explicit not-found handling |
| SELECT returns too many rows | Elevated memory/latency | Bound `maxRows`, pagination, and indexes |
| Transaction rolls back after reply | Reply had `UPDATED=1` but data rolled back | Only publish side effects after commit |
| Invalid payload type/key | Binding exception | Fix transformer; do not retry like network error |

### 15.1. Retrying After Timeout Can Cause Duplicate Effects

A client can lose connection **after the database has committed an INSERT**. Retrying the same request can create a second row with a different generated key. For critical operations, use:

1. **Stable business/idempotency keys** and unique constraints.
2. **Transactions** writing business data alongside an idempotency record.
3. **Outbox** for publishing events after DB commit.
4. **Retry policies** scoped to transient errors, with backoff/jitter and capped attempts.
5. **Reconciliation** when outcomes are uncertain.

Never rely on `keysGenerated(true)` to prevent duplicates: a generated key only identifies the ID assigned in one attempt, not that the business event was processed once.

### 15.2. Error Channel

With `DirectChannel`, synchronous SQL errors typically propagate back to the caller; with executors/pollers, errors can route to the endpoint's `ErrorMessage`/`errorChannel`. Do not assume every error automatically turns into a `{ERROR=...}` reply payload: gateways normally return **SQL results**, while errors take their own path. Check where errors happen relative to source ACKs to decide retry/DLQ behavior.

## 16. JDBC Is Blocking I/O: Performance and Operations

`JdbcOutboundGateway` runs over a synchronous JDBC driver. Calling it from a WebFlux inbound handler on the Reactor Netty event loop can block the event loop while waiting on connections or queries.

**Safer structure:** execute JDBC work on bounded worker threads, such as an `ExecutorChannel` or dedicated schedulers, while managing transactions and reply timeouts accordingly. If the application truly needs a reactive database pipeline, consider R2DBC; **switching threads does not make JDBC non-blocking**.

Metrics to track:

- Connection pool active/idle/pending counts and acquire wait time.
- SQL update/SELECT duration, transaction duration, locks/deadlocks.
- Counts of `UPDATED=0`, `UPDATED=1`, and unexpected `UPDATED>1`.
- Result set size, mapping duration, and heap usage.
- In-flight messages, queue depth, request/reply latency, and timeouts.
- Retries, error channel volume, dead-letters, rollbacks, and idempotency conflicts.

Do not raise `maxRows(0)` or thread counts endlessly to chase throughput. Large result sets, unindexed queries, and lock-contending transactions can slow down the entire flow.

## 17. Testing the Gateway: Verifying Replies and DB Data

### 17.1. Spring Boot + H2 Test for UPDATE Count

With `schema.sql` and `data.sql` matching section 4:

~~~java
package com.example.jdbc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class JdbcOutboundGatewayTest {

    @Autowired
    @Qualifier("statusRequests")
    MessageChannel requests;

    @Autowired
    @Qualifier("statusReplies")
    PollableChannel replies;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void updateReturnsAffectedRowCount() {
        // Test precondition: ORD-1001 has status RECEIVED.
        jdbc.update(
            "UPDATE order_projection SET status = ? WHERE order_id = ?",
            "RECEIVED", "ORD-1001");

        boolean sent = requests.send(MessageBuilder
            .withPayload(Map.of(
                "orderId", "ORD-1001",
                "expectedStatus", "RECEIVED",
                "newStatus", "PAID"))
            .build());
        assertTrue(sent);

        Message<?> reply = replies.receive(1_000);
        assertNotNull(reply);
        Map<?, ?> result = (Map<?, ?>) reply.getPayload();
        assertEquals(1, ((Number) result.get("UPDATED")).intValue());

        String status = jdbc.queryForObject(
            "SELECT status FROM order_projection WHERE order_id = ?",
            String.class, "ORD-1001");
        assertEquals("PAID", status);
    }

    @Test
    void missingOrderReturnsZeroUpdated() {
        boolean sent = requests.send(MessageBuilder
            .withPayload(Map.of(
                "orderId", "ORD-DOES-NOT-EXIST",
                "expectedStatus", "RECEIVED",
                "newStatus", "PAID"))
            .build());
        assertTrue(sent);

        Message<?> reply = replies.receive(1_000);
        assertNotNull(reply);
        Map<?, ?> result = (Map<?, ?>) reply.getPayload();
        assertEquals(0, ((Number) result.get("UPDATED")).intValue());
    }
}
~~~

These tests assume **no other consumer** is draining `statusReplies` and that parallel tests are not mutating fixture rows unexpectedly. With `QueueChannel`, replies are retrieved via `receive()`; if production uses a router/service activator instead of a queue, test that downstream output accordingly.

### 17.2. SELECT / Generated Keys Test Matrix

| Case | What to assert |
|---|---|
| DML affects exactly one row | Reply `UPDATED=1`, DB reflects expected change |
| DML matches no rows | Reply `UPDATED=0`, no automatic exception |
| DML unexpectedly affects multiple rows | Alert or reject if contract requires exactly one |
| SELECT with `maxRows(1)` | Single-row payload type when result exists |
| SELECT with `maxRows(0)` | List reply, including empty list |
| SELECT finds no data | Maps to `404`/`NOT_FOUND` per contract, not confused with timeout |
| INSERT generated keys | Reply shape/content matches real JDBC driver |
| INSERT then SELECT by generated keys | Key parameter binding matches production DB |
| UPDATE + SELECT | Post-update data and transaction isolation are accurate |
| Invalid schema/parameters | Handled via error flow, never treated as success |
| Transaction rollback after reply | Durable events are not published before DB commit |
| Kafka/JMS source redelivery | No duplicate effects; controlled ACK/retry |

Specifically, run integration tests on a production-compatible DB for generated keys, transaction isolation, deadlocks, and row counts. H2 may not replicate all semantics of SQL Server, PostgreSQL, or Oracle.

## 18. Common Mistakes

| Misconception | Accurate understanding |
|---|---|
| “JDBC outbound gateway is a poller reading the DB continuously” | The gateway is **triggered by request messages** |
| “Both outbound adapter and outbound gateway return results” | The one-way adapter emits no reply |
| “UPDATE affecting 0 rows always throws an exception” | Usually returns `UPDATED=0` |
| “`UPDATED=1` means the outer transaction already committed” | The reply can be produced **before** outer commit |
| “SELECT gateway always returns a `List`” | Default `maxRows=1` can return a single row |
| “SELECT returning 0 rows always means no reply” | Since SI 6.0, empty lists are preserved rather than converted to null |
| “`maxRows(0)` fetches 0 rows” | It allows fetching **all** query rows |
| “Generated keys are always named `ID`” | Names/shapes depend on JDBC driver/DB |
| “RowMapper makes JDBC reactive” | JDBC remains blocking |
| “`Jdbc.outboundGateway` exists in all 6.x versions” | The Java DSL JDBC factory was added in 7.0 |
| “Request SQL parameter factory and PreparedStatement setter must both be enabled” | They are alternative DML binding mechanisms |
| “UPDATE+SELECT gateway always returns both update count and row” | SELECT determines the reply payload when a query is present |
| “Having auto-generated keys guarantees retries cannot duplicate rows” | Requires unique business keys/idempotency |

## 19. Practice Exercises

1. Initialize the H2 schema and send an UPDATE through `Jdbc.outboundGateway(...)`. Verify the `{UPDATED=1}` reply and DB state.
2. Send a request with a nonexistent `orderId`; confirm `UPDATED=0` and build a router handling not-found/conflict.
3. Update the UPDATE predicate to add `expectedStatus`; run two concurrent commands and evaluate races and reliability.
4. Build a SELECT flow by `orderId` with `maxRows(1)` and `RowMapper<OrderView>`; verify the single-row reply.
5. Switch to `maxRows(0)` returning multiple rows; use `split()` to route each row to a dedicated `MessageChannel`.
6. Run a SELECT matching zero rows; observe empty-list behavior in your version and design a `NOT_FOUND` domain mapping.
7. Use `order_audit` with an auto-generated ID, enable `keysGenerated(true)`, and inspect generated keys. Check the actual key name from the DB.
8. Add a SELECT after INSERT using the generated key; configure `replySqlParameterSourceFactory` and DB-matching parameter names.
9. Write a combined DML + SELECT flow in one message; test the update and `SELECT` reply, analyzing isolation/transactions.
10. Convert the 7.x Java DSL flow to a `JdbcOutboundGateway` bean + `@ServiceActivator` in 6.x. Compare imports and XML config.
11. Trigger a transaction rollback after `send()`; explain why an `UPDATED=1` reply does not guarantee final commit.
12. Replace `DirectChannel` with `ExecutorChannel`; observe threads, error propagation, reply timeouts, and transaction boundaries.
13. Have an HTTP inbound gateway call a JDBC outbound gateway; avoid blocking the WebFlux event loop and return appropriate replies/404s.
14. Send requests from Kafka/JMS and simulate a crash after DB commit before ACK; add idempotency/outbox to prevent duplication.
15. Send unbounded SELECT requests and measure heap/latency; migrate to pagination and proper indexes.

**Design scenario:** a system receives a `payment.captured` event, updates order status via a JDBC outbound gateway, and then publishes a Kafka `order.paid` event. On the first attempt, SQL returns `UPDATED=1` but the app crashes before ACKing the source Kafka message; on redelivery, the UPDATE returns `UPDATED=0` because status is already `PAID`. How do you distinguish “already-processed duplicate” from “conflict”, where is the reply transaction boundary, and how do you use outbox/idempotency to ensure outbound events are still emitted without duplicate side effects?

## 20. References

- [Spring Integration Reference — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `UPDATED` count, generated keys, SELECT, `maxRows`, and empty lists since 6.0.
- [Spring Integration Reference — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): Java DSL `Jdbc` from 7.0 and `JdbcOutboundGatewaySpec`.
- [Spring Integration API — Jdbc Factory](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/Jdbc.html): `outboundGateway(dataSource, updateQuery, selectQuery)` overloads.
- [Spring Integration API — JdbcOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcOutboundGatewaySpec.html): `maxRows`, `keysGenerated`, `rowMapper`, request/reply SQL parameter source factories.
- [Spring Integration API — JdbcOutboundGateway (7.x)](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/outbound/JdbcOutboundGateway.html): constructors and request/reply handler behavior.
- [Spring Integration API — JdbcOutboundGateway (6.x)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/jdbc/JdbcOutboundGateway.html): legacy handler import, row mapper, and max rows.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): DataSource, JdbcTemplate, RowMapper, exception translation.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, commit/rollback, and proxies.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request-reply, replyChannel, timeouts, and correlation.

> **Remember:** The JDBC outbound gateway is a **message-driven request–reply endpoint**. It executes DML/SELECT and returns the corresponding result: `{UPDATED=n}`, generated keys, or rows from SELECT. Correct usage requires clear payload types/`maxRows`, parameter binding, reply channels, transactions, and empty-result handling. Do not mistake an update count for a commit receipt, and do not confuse the JDBC outbound gateway with the one-way side-effect outbound adapter.

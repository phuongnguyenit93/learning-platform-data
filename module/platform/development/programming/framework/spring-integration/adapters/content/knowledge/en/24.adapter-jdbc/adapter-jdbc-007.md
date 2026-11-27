# RowMapper Converting ResultSet to Payloads in Spring Integration JDBC

## 1. Why Does RowMapper Matter in an Integration Flow?

A system reads data from a database and converts it into Spring Integration messages for processing and sending to HTTP, Kafka, JMS, AMQP, or another service. SQL query results are rows in a `ResultSet`, whereas business code wants Java objects like `OrderEvent`, `OrderProjection`, or `ShipmentStatus`. If every handler reads `Map<String, Object>` directly with varying column names, contracts between steps become hard to check, easy to miscast, and fragile to schema changes.

Spring JDBC's **`RowMapper<T>`** is the interface that maps **the current row of a `ResultSet`** to **an object `T`**. Spring JDBC invokes the mapper for each row during a `SELECT`. A Spring Integration JDBC inbound channel adapter can use that mapper to produce a `List<T>` payload; a JDBC outbound gateway can use it to produce a single `T` or `List<T>` reply depending on configuration.

This article belongs to the **Adapter JDBC** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module's scope is connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while clarifying message contracts, errors, and connection lifecycles. In this article, **`RowMapper` is the boundary converting JDBC data into Java payloads**, not a message orchestrator or transaction manager.

~~~mermaid
flowchart LR
    DB[("Database")] -->|"SELECT"| RS["JDBC ResultSet"]
    RS --> RM["RowMapper<T> per row"]
    RM --> LIST["List<T>"]
    LIST --> MSG["Message<List<T>>"]
    MSG --> SPLIT["Splitter if needed"]
    SPLIT --> ITEMS["N × Message<T>"]
    ITEMS --> NEXT["Service / HTTP / Kafka / JMS"]
~~~

**Remember upfront:** `RowMapper` changes the **data type of each row**; it does not by itself change the **number of messages**. A query returning 20 rows can still produce **one** inbound message containing `List<OrderEvent>`. To turn each row into an individual message, add a `Splitter` downstream.

## 2. The `RowMapper<T>` Contract and ResultSet Lifecycle

The Spring JDBC interface looks like this:

~~~java
package org.springframework.jdbc.core;

import java.sql.ResultSet;
import java.sql.SQLException;

@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

Meaning of each element:

| Element | Meaning | Warning |
|---|---|---|
| `ResultSet rs` | Cursor already positioned by the JDBC framework at the **current row** | Never call `rs.next()` inside the mapper |
| `int rowNum` | Row index passed by the framework, starting at **0** | Never use it as a business ID |
| `T` | Resulting DTO/record/bean/map | Do not arbitrarily return `null` for valid rows |
| `SQLException` | Column access or JDBC conversion error | Let Spring JDBC translate it or handle intentionally |

A well-behaved `RowMapper` is **stateless**: it does not store `ResultSet` or `Connection` in fields, does not query the database again per row, does not hold a `MessageChannel` to send messages inside the callback, and causes no business side effects.

~~~text
JdbcTemplate / JDBC adapter:
    while (rs.next()) {
        T mapped = rowMapper.mapRow(rs, rowNum++);
        results.add(mapped);
    }
    // Framework releases ResultSet/Statement/Connection appropriately.
~~~

The snippet above is a **conceptual model**, not Spring JDBC's internal source code. `JdbcTemplate`/the adapter manages iteration and closing JDBC resources. The mapper merely reads columns from the **current row** and constructs an object.

**Never do inside a mapper:** call `rs.close()`, `rs.next()`, `connection.commit()`, `Thread.sleep(...)`, or invoke HTTP to enrich data. Those operations violate the contract or hold resources for abnormally long durations per row.

## 3. Without a Custom RowMapper: What Is the Default Payload?

Per Spring Integration JDBC documentation, the **JDBC inbound channel adapter** runs `SELECT` and puts the **entire result set** into a `List` payload. Without a custom `RowMapper`, each element defaults to a `Map` keyed by column names.

~~~sql
SELECT id, event_key, event_type
FROM inbound_event
WHERE state = 'NEW'
ORDER BY id;
~~~

With two rows, the conceptual payload is:

~~~text
Message<List<Map<String,Object>>>
  payload:
    [
      {id: 101, event_key: "evt-101", event_type: "order.created"},
      {id: 102, event_key: "evt-102", event_type: "order.paid"}
    ]
~~~

With a custom `RowMapper<InboundEvent>`, the same query produces:

~~~text
Message<List<InboundEvent>>
  payload:
    [
      InboundEvent(id=101, eventKey="evt-101", ...),
      InboundEvent(id=102, eventKey="evt-102", ...)
    ]
~~~

**Do not tightly couple to internal Map types** like `LinkedHashMap` or driver-specific column-name casing (uppercase/lowercase). When using the default map, specify explicit SQL aliases and test the actual key names. Creating DTOs via `RowMapper` eliminates downstream reliance on those details.

### 3.1. Four Data Shapes to Distinguish

| Type | Cardinality | Where encountered |
|---|---|---|
| `ResultSet` | One JDBC cursor | Inside `JdbcTemplate`/adapter; never sent raw across channels |
| `List<InboundEvent>` | N mapped elements | Query result before message wrapping |
| `Message<List<InboundEvent>>` | **One message** | JDBC inbound adapter before a splitter |
| `List<Message<InboundEvent>>` or N messages | **N messages** | After a splitter/dispatching handler |

Do not wire a handler expecting `handle(InboundEvent)` directly when upstream is still emitting `List<InboundEvent>`.

## 4. Setting Up the Spring Boot Project and Sample Schema

This article uses Java 17+, Spring Boot, Spring JDBC, Spring Integration JDBC, and H2. To avoid version conflicts, let the Spring Boot BOM manage compatible Spring Framework/Integration dependencies.

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

~~~yaml
# application.yml - for H2 example only
spring:
  datasource:
    url: "jdbc:h2:mem:row_mapper_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
~~~

Place the following SQL in `src/main/resources/schema.sql` of your **practice application**. This authoring task only edits the assigned Markdown/YAML files and does not create standalone project files:

~~~sql
CREATE TABLE inbound_event (
    id             BIGINT NOT NULL PRIMARY KEY,
    event_key      VARCHAR(64) NOT NULL UNIQUE,
    event_type     VARCHAR(64) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    attempt_count  INTEGER NULL,
    state          VARCHAR(20) NOT NULL
);
~~~

Sample test data (can be placed in `data.sql`):

~~~sql
INSERT INTO inbound_event
    (id, event_key, event_type, created_at, attempt_count, state)
VALUES
    (101, 'evt-101', 'order.created',
        TIMESTAMP '2026-11-01 09:00:00', 0, 'NEW'),
    (102, 'evt-102', 'order.paid',
        TIMESTAMP '2026-11-01 09:01:00', NULL, 'NEW'),
    (103, 'evt-103', 'order.shipped',
        TIMESTAMP '2026-11-01 09:02:00', 2, 'CLAIMED');
~~~

In this example, `attempt_count` can be `NULL` so learners observe the difference between `Integer` and `int`. `created_at` is a `TIMESTAMP` without timezone; the article uses `LocalDateTime`. In production, specify timezone rules and timestamp types per database vendor whenever data represents global instants.

## 5. Creating a Java Record DTO and Manual RowMapper

### 5.1. DTO as the Payload Contract

~~~java
package com.example.integration;

import java.time.LocalDateTime;

public record InboundEvent(
    long id,
    String eventKey,
    String eventType,
    LocalDateTime createdAt,
    Integer attemptCount) {
}
~~~

**Why use a record?** It is an immutable data type with accessors such as `id()` and `eventKey()`, convenient for passing between flow stages. `attemptCount` uses `Integer` to preserve SQL `NULL` semantics accurately.

### 5.2. Explicit RowMapper with Data Validation

~~~java
package com.example.integration;

import java.sql.Timestamp;
import org.springframework.dao.DataRetrievalFailureException;
import org.springframework.jdbc.core.RowMapper;

public final class InboundEventRowMapper
        implements RowMapper<InboundEvent> {

    @Override
    public InboundEvent mapRow(
            java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException {

        long id = rs.getLong("id");
        if (rs.wasNull()) {
            throw new DataRetrievalFailureException(
                "inbound_event.id must not be NULL");
        }

        Timestamp timestamp = rs.getTimestamp("created_at");
        if (timestamp == null) {
            throw new DataRetrievalFailureException(
                "created_at must not be NULL");
        }

        return new InboundEvent(
            id,
            rs.getString("event_key"),
            rs.getString("event_type"),
            timestamp.toLocalDateTime(),
            rs.getObject("attempt_count", Integer.class));
    }
}
~~~

`rs.getLong(...)` returns `0` when the SQL column is `NULL`, so `rs.wasNull()` distinguishes SQL `NULL` from an actual numeric 0. Even though the schema declares `id NOT NULL`, the example checks defensively in case queries, joins, or aliases change in the future.

`rs.getObject("attempt_count", Integer.class)` preserves SQL `NULL` as Java `null` on JDBC drivers supporting typed retrieval. Older drivers or special types may have limitations with `getObject(..., Class)`; in that case use `getInt` + `wasNull()`:

~~~java
int value = rs.getInt("attempt_count");
Integer attemptCount = rs.wasNull() ? null : value;
~~~

If business logic requires defaulting attempt counts to 0, express that rule **explicitly** rather than letting JDBC primitive getters silently turn `NULL` into 0 unnoticed.

### 5.3. What RowMapper Should Not Do

A mapper should only perform conversion and basic validation for **one row**. Avoid:

- Querying another database table per row, causing `N+1 queries`.
- Calling HTTP/Kafka/JMS inside `mapRow`; such side effects are not protected by the `SELECT` transaction as expected.
- Generating a random correlation ID per map call when the business ID must stay stable across retries.
- Storing `ResultSet` or `Connection` inside the DTO; both become invalid once the query finishes.
- Calling `rs.next()`, because cursor advancement belongs to the JDBC framework.

**Right place for business logic:** `RowMapper` produces `InboundEvent`; a downstream service activator/transformer validates state transitions, enriches, authenticates, publishes, or writes to an outbox.

## 6. Three Mapping Strategies: Map, Bean, and Record

| Strategy | Output | Pros | Risks |
|---|---|---|---|
| Default mapper/`ColumnMapRowMapper` | `Map<String,Object>` | Fast prototyping, flexible schema | Scattered casting and column-name coupling |
| `BeanPropertyRowMapper<T>` | Java bean with no-arg constructor and setters | Less boilerplate when column names match | Mutable beans, NULL primitives, reflection/conversion |
| `DataClassRowMapper<T>` | Java record/Kotlin data class/constructor-based type | Constructor mapping, immutable DTOs | Column names/types must match constructor |
| Custom `RowMapper<T>` | Any `T` | Explicit validation, aliases, types/precision | Must write and maintain mapping code |

### 6.1. BeanPropertyRowMapper for Mutable Beans

~~~java
package com.example.integration;

public class EventBean {
    private Long id;
    private String eventKey;
    private String eventType;

    public EventBean() { }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getEventKey() { return eventKey; }
    public void setEventKey(String eventKey) {
        this.eventKey = eventKey;
    }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) {
        this.eventType = eventType;
    }
}
~~~

~~~java
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<EventBean> beanMapper =
    BeanPropertyRowMapper.newInstance(EventBean.class);
~~~

Spring maps `event_key` → `eventKey` and `event_type` → `eventType` using underscore-to-camelCase conventions. `BeanPropertyRowMapper` suits mutable DTOs with no-arg constructors and setters; **do not use it by default for Java records**, which lack setters and no-arg constructors.

### 6.2. DataClassRowMapper for Java Records

~~~java
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<InboundEvent> recordMapper =
    DataClassRowMapper.newInstance(InboundEvent.class);
~~~

`DataClassRowMapper` supports data-class constructor mapping for Java records. It works well when JDBC columns and constructor parameters match in name and type. Always **test thoroughly** with `TIMESTAMP`, `UUID`, enums, JSON columns, and SQL `NULL` on your application's actual driver.

**Which mapper to choose?** For simple projections, `DataClassRowMapper` is concise and readable. For money, timestamps/timezones, nullability, enums, or complex SQL aliases, a custom `RowMapper` usually provides a clearer contract and better performance.

### 6.3. ColumnMapRowMapper Only Fits Dynamic Schemas

~~~java
import java.util.Map;
import org.springframework.jdbc.core.ColumnMapRowMapper;
import org.springframework.jdbc.core.RowMapper;

RowMapper<Map<String, Object>> mapMapper =
    new ColumnMapRowMapper();
~~~

This mapper works when tables/columns vary dynamically and downstream explicitly handles maps. Never assume map key casing is identical across all databases; when downstream contracts require stable names, **use explicit SQL aliases or DTOs**.

## 7. SQL Aliases, Column Names, and Type Mapping

A `RowMapper` reads values from `ResultSet` by **column label** or index. When SQL uses joins, renames columns, or has colliding column names, use aliases:

~~~sql
SELECT
    e.id                AS id,
    e.event_key         AS event_key,
    e.event_type        AS event_type,
    e.created_at        AS created_at,
    e.attempt_count     AS attempt_count
FROM inbound_event e
WHERE e.state = 'NEW'
ORDER BY e.id;
~~~

In join queries, avoid `SELECT *` when two tables both have an `id` column. Use explicit aliases like `event_id`, `order_id` and align the mapper accordingly. Explicit aliases also help tests catch accidental contract changes in queries.

| Common SQL type | Suggested Java type | Key caveats |
|---|---|---|
| `BIGINT NOT NULL` | `long` or `Long` | `getLong` + `wasNull` when needed |
| `INTEGER NULL` | `Integer` | Do not lose SQL NULL information |
| `DECIMAL(18,2)` | `BigDecimal` | Never convert money to `double` |
| `VARCHAR` | `String` | Encoding, trimming, empty/null, max length |
| `TIMESTAMP` | `LocalDateTime` or timezone-appropriate type | Timezone/driver rules and precision |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime`/`Instant` per support | Verify against actual driver/DB |
| `BOOLEAN` / bit | `Boolean` or `boolean` | Nullability and SQL dialect |
| `UUID` | `UUID` or `String` | Native UUID vs. CHAR/VARCHAR per vendor |
| JSON/BLOB/CLOB | Appropriate DTO/`byte[]`/stream | Codec, memory, resource handling |

**Money example:** if SQL `DECIMAL(18,2)` stores `125000.50`, `rs.getBigDecimal("amount")` preserves decimal precision; using `getDouble` for financial calculations introduces binary floating-point rounding errors. When business rules require rounding/scale, enforce them in the domain layer or a validated mapper rather than relying on incidental default conversions.

## 8. RowMapper and JdbcTemplate: Testing Mapping Separately Before Integration

Before wiring a mapper into a poller, test it via `JdbcTemplate.query(...)` with a simple SQL query. That isolates column/type mismatches from scheduler, channel, or broker errors.

~~~java
package com.example.integration;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InboundEventRepository {

    private final JdbcTemplate jdbc;
    private final InboundEventRowMapper mapper =
        new InboundEventRowMapper();

    public InboundEventRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<InboundEvent> findNewEvents() {
        return jdbc.query(
            "SELECT id, event_key, event_type, "
          + "created_at, attempt_count "
          + "FROM inbound_event WHERE state = ? ORDER BY id",
            mapper, "NEW");
    }
}
~~~

`JdbcTemplate.query(...)` invokes the mapper **once per row** and returns `List<InboundEvent>`. If no rows match, the result is an empty list; `queryForObject(...)` is a different API that expects **exactly one row** and throws on cardinality mismatch.

~~~java
List<InboundEvent> events = repository.findNewEvents();
System.out.println("Mapped rows = " + events.size());
~~~

**Limitation:** `JdbcTemplate.query(...)` is still synchronous I/O and typically materializes a `List` before returning. `RowMapper` itself does not produce a `Flux<InboundEvent>` or manage backpressure for systems outside the database.

## 9. Spring Integration 7.x Java DSL: Inbound RowMapper → Message Payload

Since **Spring Integration 7.0**, the JDBC module provides the Java DSL factory `Jdbc.inboundAdapter(...)`. `JdbcInboundChannelAdapterSpec.rowMapper(...)` accepts a `RowMapper<?>`, `maxRows(...)` limits rows, and the poller controls polling cadence.

The example below queries `WHERE state = 'NEW'`, updates selected rows to `CLAIMED`, and emits each `InboundEvent` to the `mappedEvents` channel. This is a **claim-and-process** example, not yet an end-to-end exactly-once guarantee.

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
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableIntegration
public class JdbcInboundRowMappingFlow {

    @Bean
    public RowMapper<InboundEvent> inboundEventRowMapper() {
        return new InboundEventRowMapper();
    }

    @Bean
    public IntegrationFlow pollAndMapEvents(
            DataSource dataSource,
            RowMapper<InboundEvent> inboundEventRowMapper,
            PlatformTransactionManager transactionManager) {

        String selectSql = """
            SELECT id, event_key, event_type,
                   created_at, attempt_count
            FROM inbound_event
            WHERE state = 'NEW'
            ORDER BY id
            """;

        return IntegrationFlow.from(
                Jdbc.inboundAdapter(dataSource, selectSql)
                    .rowMapper(inboundEventRowMapper)
                    .maxRows(25)
                    .updateSql(
                        "UPDATE inbound_event SET state = 'CLAIMED' "
                      + "WHERE id IN (:id) AND state = 'NEW'")
                    .updateSqlParameterSourceFactory(result -> {
                        List<?> rows = (List<?>) result;
                        List<Long> ids = rows.stream()
                            .map(InboundEvent.class::cast)
                            .map(InboundEvent::id)
                            .toList();
                        return new MapSqlParameterSource("id", ids);
                    }),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(1)
                        .transactional(transactionManager)))
            .filter(payload ->
                payload instanceof List<?> rows && !rows.isEmpty())
            .split()
            .channel("mappedEvents")
            .get();
    }
}
~~~

Reading sequentially:

1. `Jdbc.inboundAdapter(dataSource, selectSql)` creates a JDBC polling message source for the SQL `SELECT`.
2. `rowMapper(inboundEventRowMapper)` converts **each row** into an `InboundEvent`.
3. `maxRows(25)` caps how many rows the adapter includes in a message per query; unlike `maxMessagesPerPoll(1)`, which is the number of `receive()` calls per trigger.
4. `updateSql(...)` marks read records so subsequent polls do not pick up the same `NEW` rows again. It does not replace a full transaction/recovery strategy.
5. `updateSqlParameterSourceFactory(...)` illustrates extracting IDs from the **already-mapped list** to bind `:id`, avoiding reliance on default field lookup conventions after converting from `Map` to a record.
6. `transactional(transactionManager)` wraps the poll operation when the transaction manager matches the `DataSource`. This helps for the SELECT/UPDATE pair; check threads and channels in section 14.
7. `filter` and `split()` control message shape: a non-empty list is split into N messages each carrying an `InboundEvent` payload.
8. `mappedEvents` is the downstream channel; actual processing requires a subscriber/handler on that channel.

**Note on the example:** `SELECT ... ORDER BY id` plus `UPDATE ... WHERE id IN (...)` is not a safe **atomic claim** algorithm when multiple application pods poll concurrently. Two instances can read the same rows before one commits its UPDATE. Production should use vendor-appropriate claim/locking (such as `FOR UPDATE SKIP LOCKED` or an appropriate update-returning pattern), leases/outbox, and idempotency.

### 9.1. Consumer for Each Payload After the Splitter

~~~java
package com.example.integration;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class InboundEventConsumer {

    @ServiceActivator(inputChannel = "mappedEvents")
    public void handle(InboundEvent event) {
        System.out.printf("Event %d: %s%n",
            event.id(), event.eventType());
    }
}
~~~

The handler receives a **single `InboundEvent`** because `.split()` ran upstream. In production, never treat `System.out.println` as proof that a broker received the event or the database committed. When calling HTTP/Kafka/JMS outbound, design explicit error/ACK boundaries and idempotency.

## 10. How Many Messages Does One Poll Produce?

Suppose SQL returns 3 rows, the mapper produces 3 DTOs, and the poller uses `maxMessagesPerPoll(1)`:

~~~text
Poller:
  1 call to source.receive()
      -> SELECT fetches 3 rows
      -> RowMapper.mapRow(...) runs 3 times
      -> 1 List<InboundEvent> containing 3 objects
      -> 1 Message<List<InboundEvent>>
      -> Splitter
      -> 3 x Message<InboundEvent>
~~~

| Configuration | Result | What stays unchanged |
|---|---|---|
| No custom RowMapper | `Message<List<Map<String,Object>>>` | Message count is still 1 before splitter |
| With `RowMapper<InboundEvent>` | `Message<List<InboundEvent>>` | Message count is still 1 before splitter |
| Add splitter | N `Message<InboundEvent>` | Query still runs on poller schedule |
| `maxRows(25)` | At most 25 rows in one query result | Does not become 25 polls |
| `maxMessagesPerPoll(1)` | One source poll per trigger per policy | Does not limit the SQL query to 1 row |
| SELECT returns 0 rows | No business rows to split | Not automatically treated as a JDBC error |

**Default difference:** the JDBC inbound adapter defaults `maxRows` to **0**, meaning no adapter-level row cap. The JDBC outbound gateway with SELECT defaults `maxRows` to **1**. Sharing the same mapper does not give both endpoints the same reply shape.

### 10.1. Limit at the Database Instead of Only in Java

`maxRows(25)` limits how many records the adapter processes, but on large tables you should limit rows directly in SQL at the database—using `LIMIT`/`FETCH FIRST`/`TOP` per vendor—alongside indexes and pagination. Combined with a deterministic `ORDER BY`, each poll fetches a predictable batch.

**Do not do** `SELECT * FROM huge_table` and rely on the mapper or adapter to discard excess rows when you only want 25 events. `RowMapper` is not a query optimizer and does not stop the JDBC driver/network from transferring extra rows upfront unless constrained.

## 11. Configuring RowMapper in Spring Integration 6.x

The JDBC Java DSL factory `Jdbc.inboundAdapter(...)` was introduced in **Spring Integration 7.0**. In Spring Integration **6.x**, `org.springframework.integration.jdbc.JdbcPollingChannelAdapter` already has `setRowMapper(...)` and can be used directly inside `IntegrationFlow.from(messageSource, pollerSpec)`:

~~~java
package com.example.integration;

import java.time.Duration;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.JdbcPollingChannelAdapter;
import org.springframework.jdbc.core.RowMapper;

@Configuration
public class JdbcRowMappingLegacyFlow {

    @Bean
    public IntegrationFlow legacyMappedEvents(
            DataSource dataSource) {
        JdbcPollingChannelAdapter source =
            new JdbcPollingChannelAdapter(
                dataSource,
                "SELECT id, event_key, event_type, "
              + "created_at, attempt_count "
              + "FROM inbound_event WHERE state = 'NEW' ORDER BY id");

        RowMapper<InboundEvent> mapper = new InboundEventRowMapper();
        source.setRowMapper(mapper);
        source.setMaxRows(25);

        return IntegrationFlow.from(source, endpoint ->
                endpoint.poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                    .maxMessagesPerPoll(1)))
            .filter(payload ->
                payload instanceof java.util.List<?> rows &&
                !rows.isEmpty())
            .split()
            .channel("legacyMappedEventsChannel")
            .get();
    }
}
~~~

**Difference from section 9:** the 6.x example intentionally only performs SELECT and mapping, **without marking processed rows**, to focus on the configuration API. Consequently, it will **re-read the same rows on every poll** if the database does not change. Production code must add `setUpdateSql(...)`/`setUpdateSqlParameterSourceFactory(...)` and a transactional poller, or use an appropriate atomic claim/outbox pattern.

In real projects, pick **one** configuration style matching your active version; do not enable both 7.x and 6.x flows reading the same source concurrently without designing concurrency control.

### 11.1. XML Configuration for 6.x

~~~xml
<!-- Fragment in Spring XML with int and int-jdbc namespaces declared. -->
<bean id="inboundEventRowMapper"
      class="com.example.integration.InboundEventRowMapper"/>

<int:channel id="mappedEventBatches"/>

<int-jdbc:inbound-channel-adapter
    id="jdbcMappedEvents"
    query="SELECT id, event_key, event_type,
                  created_at, attempt_count
           FROM inbound_event WHERE state = 'NEW' ORDER BY id"
    data-source="dataSource"
    channel="mappedEventBatches"
    row-mapper="inboundEventRowMapper"
    max-rows="25">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-jdbc:inbound-channel-adapter>
~~~

The XML emits **one message containing a list of DTOs** onto `mappedEventBatches`. If you need one message per row, add a downstream splitter. When enabling `update` on the inbound adapter, attach a transaction manager to the poller and explicitly define state transition/recovery policies.

## 12. JDBC Outbound Gateway: How Does RowMapper Affect the Reply?

In a **JDBC outbound gateway**, the message arriving on the input channel is the **request** carrying query parameters, while `RowMapper` converts SELECT rows into the **reply payload**. With `maxRows` at its default or `1`, the gateway normally returns a single row; with `maxRows(0)` returning multiple rows, the reply is normally a list.

~~~mermaid
flowchart LR
    A["Message<Map: orderId>"] --> B["JDBC outbound gateway"]
    B --> C["SELECT WHERE order_id = :payload[orderId]"]
    C --> D["ResultSet"]
    D --> E["RowMapper<InboundEvent>"]
    E --> F["Reply: InboundEvent or List<InboundEvent>"]
~~~

### 12.1. Java DSL 7.x for Single-Row SELECT

~~~java
package com.example.integration;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
public class EventLookupGatewayFlow {

    @Bean
    public IntegrationFlow eventLookup(DataSource dataSource) {
        return IntegrationFlow.from("eventLookupRequests")
            .handle(Jdbc.outboundGateway(
                    dataSource,
                    null,
                    "SELECT id, event_key, event_type, "
                  + "created_at, attempt_count "
                  + "FROM inbound_event "
                  + "WHERE id = :payload[id]")
                .maxRows(1)
                .rowMapper(new InboundEventRowMapper()))
            .channel("eventLookupReplies")
            .get();
    }
}
~~~

A sample request payload is `Map.of("id", 101L)`. The gateway executes the query, `RowMapper` constructs an `InboundEvent`, and the reply carries that object **when one row matches**. In the DSL, the three-argument overload `Jdbc.outboundGateway(dataSource, updateSql, selectSql)` with `updateSql = null` specifies SELECT-only mode.

If `SELECT` finds no rows, do not assume the gateway necessarily returns `null` or always times out: since Spring Integration **6.0**, empty list results are **preserved as the reply** rather than converted to “no reply”. Whether the exact reply is a single row or a list also depends on `maxRows` and actual results; test 0/1/many rows explicitly.

### 12.2. When Multiple Rows Are Needed

~~~java
.handle(Jdbc.outboundGateway(
        dataSource, null, selectSql)
    .maxRows(0)
    .rowMapper(new InboundEventRowMapper()))
.split()
.channel("oneEventPerMessage")
~~~

This is a DSL fragment; `selectSql` is an appropriate SELECT query string and `dataSource` is an injected bean. `maxRows(0)` means no gateway-imposed row limit, **not fetching 0 rows**. If a query could match millions of rows, add WHERE filters, pagination, or keyset cursors before using `maxRows(0)`.

## 13. Stored Procedures, Result Sets, and RowMapper

A JDBC stored procedure can return one or more `ResultSet`s, OUT parameters, and a return value. With Spring Integration stored procedure endpoints, you can register `returningResultSetRowMapper("events", mapper)` to map **each row in the result set named `events`** to a DTO.

~~~java
// Configuration fragment inside StoredProcExecutorSpec in Spring Integration 7.x:
.returningResultSetRowMapper(
    "events", new InboundEventRowMapper())
~~~

**Unlike the regular inbound channel adapter:** `StoredProcExecutor` typically produces a **`Map<String,Object>`** containing result sets and OUT parameters. A result set may appear as `List<InboundEvent>` under key `events`; it is not automatically flattened into N messages.

If `expectSingleResult(true)` is enabled on the stored procedure inbound adapter, it unwraps **the single entry of the result map**, not a single row. When the map only has key `events`, the payload becomes `List<InboundEvent>` and still needs a splitter. If the map contains multiple OUT/result entries, `expectSingleResult(true)` is not a substitute for defining the proper map contract.

## 14. RowMapper, SELECT/UPDATE, and Poller Transaction Boundaries

A JDBC inbound adapter can both run `SELECT` to fetch rows and run `UPDATE` to mark polled rows. `RowMapper` only governs **row shape**, whereas selection, marking, and ACK policies belong to the endpoint and transaction.

~~~mermaid
sequenceDiagram
    participant P as Poller / transaction
    participant A as JDBC inbound adapter
    participant DB as Database
    participant R as RowMapper
    participant D as Downstream DirectChannel
    P->>A: receive()
    A->>DB: SELECT NEW rows
    DB-->>A: ResultSet
    A->>R: mapRow for each row
    R-->>A: List<InboundEvent>
    A->>DB: UPDATE claimed rows
    A-->>D: Message<List<InboundEvent>>
    Note over P,D: Sync + same TX can roll back if downstream fails
~~~

With `DirectChannel` and **same-thread synchronous** downstream handlers, database updates can share the poller transaction if the transaction manager targets the same `DataSource`. However, when messages pass through an `ExecutorChannel`, `QueueChannel`, or async HTTP/Kafka calls, the poller transaction **does not automatically continue** on another thread or process.

A plain `SELECT` + `UPDATE` **does not guarantee atomic claiming across multiple replicas** without proper locking/isolation. Choose a vendor-appropriate algorithm, such as locking with `SKIP LOCKED`/`OUTPUT` or leases, instead of letting multiple instances read the same `NEW` rows and publish them concurrently to a broker.

**Crash recovery:** if `UPDATE state='CLAIMED'` commits and the application dies before publishing, records can stay stuck in `CLAIMED`. Use leases/reclaim, transactional outbox, idempotency, and state metrics rather than expecting `RowMapper` to solve delivery reliability.

## 15. Nulls, Precision, Timestamps, and Schema Drift

### 15.1. Null Must Not Silently Become a Real Value

In JDBC:

~~~java
long id = rs.getLong("id");
boolean isNull = rs.wasNull();
~~~

On SQL `NULL`, primitive getters can return `0`, and only `wasNull()` distinguishes it. For retry counts, monetary amounts, or flags, interpreting `NULL` as 0/false can corrupt business logic. Use `Integer`/`Long`/`Boolean` for nullable fields or check `wasNull()` explicitly with the corresponding getter.

### 15.2. Timestamps Need a Timezone Contract

`Timestamp.toLocalDateTime()` represents local calendar fields **without carrying a timezone**. If data represents global UTC instants, consider storing timezone-aware types or mapping in UTC with explicit JDBC driver configuration. Never convert `LocalDateTime` to `Instant` by assuming the server's local timezone without an explicit contract.

### 15.3. Column Aliases and Schema Changes

If the DB renames `event_type` to `type` while the query keeps `AS event_type`, `RowMapper` needs no change. If a column is dropped or changes to an incompatible type, the mapper should fail loudly rather than silently producing an incomplete DTO.

Use migrations and contract tests to detect schema drift early. Never log entire rows containing sensitive data when mapping errors occur.

## 16. RowMapper Is Not ResultSetExtractor or RowCallbackHandler

| Spring JDBC API | When invoked | Return type | Use case |
|---|---|---|---|
| `RowMapper<T>` | **Per row** | One `T` | DTOs for inbound adapters/gateways/`JdbcTemplate` |
| `ResultSetExtractor<R>` | **Once for the whole ResultSet** | Any `R` | Aggregating multiple rows into complex structures |
| `RowCallbackHandler` | **Per row** with callback side effects | Does not return a `T`/row directly | Streaming stats/writing files per row inside callback |

Some domains need to group master-detail data from a JOIN. When a query returns repeated master columns across detail rows, use `ResultSetExtractor` or a `RowMapper` followed by downstream grouping. Do not force a per-row `RowMapper` to **aggregate the entire ResultSet** via shared mutable state.

### 16.1. ResultSetExtractor Example for Aggregation

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.ResultSetExtractor;

ResultSetExtractor<List<Long>> extractor = rs -> {
    List<Long> ids = new ArrayList<>();
    while (rs.next()) {
        ids.add(rs.getLong("id"));
    }
    return ids;
};
~~~

Inside `ResultSetExtractor`, advancing `rs.next()` is **per contract** because the extractor owns iterating the entire cursor. Inside `RowMapper`, doing so **violates the contract**.

## 17. Unit Testing RowMapper in Isolation with Mockito

To test a mapper without a real database, mock `ResultSet` and assert each field is mapped properly:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.*;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class InboundEventRowMapperTest {

    @Test
    void mapsOneRowIncludingNullableCount() throws Exception {
        ResultSet rs = mock(ResultSet.class);
        LocalDateTime created =
            LocalDateTime.of(2026, 11, 1, 9, 1);

        when(rs.getLong("id")).thenReturn(102L);
        when(rs.wasNull()).thenReturn(false);
        when(rs.getString("event_key")).thenReturn("evt-102");
        when(rs.getString("event_type")).thenReturn("order.paid");
        when(rs.getTimestamp("created_at"))
            .thenReturn(Timestamp.valueOf(created));
        when(rs.getObject("attempt_count", Integer.class))
            .thenReturn(null);

        InboundEvent result =
            new InboundEventRowMapper().mapRow(rs, 1);

        assertEquals(102L, result.id());
        assertEquals("evt-102", result.eventKey());
        assertEquals("order.paid", result.eventType());
        assertEquals(created, result.createdAt());
        assertNull(result.attemptCount());
        verify(rs, never()).next();
    }
}
~~~

This test verifies **`RowMapper` logic** and confirms the mapper never advances the cursor. It **does not** prove the SQL query/schema/JDBC driver returns the expected column types, or that poller transactions work; write integration tests for those.

### 17.1. Testing Invalid Data

Add a test with `rs.getTimestamp("created_at") == null` asserting that the mapper throws `DataRetrievalFailureException`. This is far safer than allowing a DTO with `createdAt=null` in a domain requiring a timestamp.

If using `BeanPropertyRowMapper`, test `NULL` columns mapped to primitives; compare throwing `TypeMismatchException` versus `primitivesDefaultedForNullValue` and decide whether silent defaults are acceptable.

## 18. Integration Testing: From JdbcTemplate to MessageChannel

Once the mapper is unit-tested, use H2 or a production-compatible database to test the query and payload shape. Example `@SpringBootTest` with the schema and fixtures from section 4:

~~~java
package com.example.integration;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class InboundEventJdbcMappingTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsSqlRowsToRecord() {
        List<InboundEvent> result = jdbc.query(
            "SELECT id, event_key, event_type, "
          + "created_at, attempt_count "
          + "FROM inbound_event WHERE id = ?",
            new InboundEventRowMapper(), 102L);

        assertEquals(1, result.size());
        assertEquals("evt-102", result.get(0).eventKey());
        assertNull(result.get(0).attemptCount());
    }
}
~~~

**When testing an entire `IntegrationFlow` with a background poller:** do not read from a channel without controlling poll timing, fixtures, and consumers. A sound test can use a test-only `QueueChannel`, insert fixture rows once the app context is ready, and wait up to a bounded deadline using `receive(timeout)`. If the flow has `split()`, assert each payload is an `InboundEvent` rather than a list; if split is omitted, assert the payload is `List<InboundEvent>`.

In production pipelines, use Testcontainers or a vendor-matched database to verify `TIMESTAMP`, `UUID`, enums, JSON, locking, and row mapping under the real driver. H2 does not fully emulate SQL Server/PostgreSQL/Oracle.

## 19. Mapping Errors and Error Handling in Spring Integration

| Symptom | Possible cause | How to check |
|---|---|---|
| `SQLException: Column not found` | Wrong column label/alias | Inspect query projection, test `RowMapper` |
| Downstream `ClassCastException` | Handler expects `InboundEvent` while payload is `List`/`Map` | Check before/after splitter |
| `NullPointerException` in mapper | Unhandled SQL NULL | Switch to wrappers/validation |
| Shifted timestamp values | Inconsistent timestamp/timezone/driver config | Specify UTC/local semantics and test |
| Wrong `BigDecimal` precision | Converted via `double` | Keep decimal values in `BigDecimal` |
| Same data emitted every poll | Missing UPDATE/claim/recovery | Design row lifecycle |
| No messages received | Query returns 0 rows, poller/channel/transaction failed | Check metrics, SQL test, logs/error flow |
| Database connection timeout | Pool exhausted or slow DB | Monitor Hikari/poller concurrency |
| Severely slow RowMapper | N+1 queries or I/O inside mapper | Move enrichment to the service layer |

Spring JDBC normally translates `SQLException` into `DataAccessException`. Inside a Spring Integration poller/endpoint, errors may be wrapped in `MessagingException` or routed via `ErrorMessage`/`errorChannel` depending on execution mode. **Do not assume every mapper error turns into a business message** or propagates synchronously to an HTTP caller.

If the mapper fails halfway through a large result set, the query/operation fails after partially allocating objects in memory. A transaction rollback can undo SQL updates in the same transaction, but **cannot retract Kafka/HTTP/JMS side effects already sent**. Therefore, avoid publishing from inside the mapper and place transaction/outbox boundaries appropriately.

## 20. Performance, Memory, and Backpressure

**`JdbcTemplate`/JDBC is blocking I/O.** `RowMapper` does not turn a query into a reactive publisher; Spring Integration inbound adapters generally build a `List<T>` before emitting a message. With hundreds of thousands of rows, memory usage and connection hold times can spike.

Common safeguards:

1. **Limit rows in SQL:** `LIMIT`, `TOP`, `FETCH FIRST`, keyset pagination per database.
2. **Limit at the adapter:** `maxRows(n)` as an extra safety net, not the sole optimization.
3. **Indexes:** align with `WHERE state='NEW'`/`ORDER BY id` or real predicates; avoid repeated full scans.
4. **Minimal mapper:** no HTTP calls, no N+1 queries, no reading unneeded BLOB/CLOB columns.
5. **Bounded executors/queues:** bound pollers/consumers, connection pools, and backlogs.
6. **Batch/claim policy:** mark/enforce idempotency in proper transactions and handle recovery.
7. **Metrics:** track query duration, rows/poll, mapping failures, backlog, and end-to-end latency.

For WebFlux, if a handler must invoke JDBC directly, offload blocking work to an appropriate worker/scheduler (such as Reactor `boundedElastic`) or decouple through a message queue; **never run `JdbcTemplate.query(...)` on the Netty event loop expecting backpressure to pause SQL automatically**. If you need end-to-end reactive database access, evaluate R2DBC and design around its different contract.

### 20.1. Is RowMapper a Good Choice or Not?

`BeanPropertyRowMapper` and `DataClassRowMapper` are convenient for most simple DTOs. For high-throughput ingestion, complex mappings, or special driver types, a custom `RowMapper` is usually easier to optimize and control on errors. Optimize only after measuring SQL/network/mapper overhead; in most pipelines, bottlenecks reside in DB queries, locks, or external I/O rather than a few Java field assignments.

## 21. Design Checklist and Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| “`RowMapper` receives the entire `ResultSet` and calls `rs.next()` itself” | The mapper handles **the current row**; the JDBC framework iterates the cursor |
| “A query returning 10 rows creates 10 messages” | JDBC inbound usually emits **one message containing a list**; a splitter breaks it up |
| “Having `rowMapper(...)` means payload is always `InboundEvent`” | It can be `List<InboundEvent>` before a splitter |
| “`BeanPropertyRowMapper` suffices for Java records” | Records should use `DataClassRowMapper` or a custom mapper |
| “`getLong` on SQL NULL automatically returns Java null” | Primitives usually return 0; use `wasNull()` |
| “`created_at` LocalDateTime is always a UTC Instant” | `LocalDateTime` carries no timezone |
| “`maxMessagesPerPoll(1)` fetches only one row” | It is the number of source `receive()` calls per trigger |
| “Inbound `maxRows(0)` fetches zero rows” | Default 0 means unlimited at the adapter level |
| “RowMapper prevents duplicate polling” | Requires updates/atomic claims/idempotency and recovery |
| “Having a JDBC transaction rolls back Kafka too” | DB and broker do not share an automatic distributed transaction |
| “RowMapper runs async because the app uses WebFlux” | JDBC queries remain blocking |
| “Selecting fewer columns removes the need for schema checks” | Aliases/types/NULLs must still be tested and managed via migrations |

**Pre-production checklist:** define DTOs and nullability; specify explicit SQL projections/aliases; unit-test `RowMapper`; integration-test against the real DB driver; distinguish list vs. single-row payloads; add splitters as needed; bound pollers/limits/transactions; design claiming, idempotency, ACKs, and recovery; monitor query duration, queue depth, and mapper errors.

## 22. Practice Exercises

1. Create the `inbound_event` table, insert data from section 4, run `JdbcTemplate.query(...)` without a custom mapper, and inspect the resulting map types.
2. Implement `InboundEventRowMapper` and verify two SQL rows convert into `List<InboundEvent>`.
3. Remove `rs.wasNull()` from a nullable field, test the `NULL` case, and explain how data semantics are lost.
4. Use `BeanPropertyRowMapper<EventBean>` to map `event_key` → `eventKey`; change an alias to verify mapping behavior.
5. Use `DataClassRowMapper.newInstance(InboundEvent.class)` for the record and compare `LocalDateTime`/`Integer` handling with the handwritten mapper.
6. Write a join query with two `id` columns; add SQL aliases and update the `RowMapper` to use the exact column labels without reading the wrong column.
7. Use `Jdbc.inboundAdapter(dataSource, selectSql).rowMapper(...)` on Spring Integration 7.x; observe payloads before and after the splitter.
8. Port the same flow to Spring Integration 6.x using `JdbcPollingChannelAdapter#setRowMapper`; explain why the 7.x Java DSL factory is not used.
9. Remove `.split()` and call a handler typed for `InboundEvent`; observe the type mismatch error, then fix the payload contract.
10. Compare `maxRows(25)` against `maxMessagesPerPoll(1)`; measure query execution counts and emitted message counts.
11. Configure `UPDATE state='CLAIMED'` after SELECT, run two pollers concurrently, and identify the limitations of select-then-update.
12. Build a query limited at the DB using vendor-appropriate `LIMIT`/`TOP`/`FETCH FIRST` and a matching index.
13. Use a JDBC outbound gateway SELECT with `RowMapper<InboundEvent>`, testing `maxRows(1)`, `maxRows(0)`, and the 0-row case.
14. Add a stored procedure returning an `events` result set mapped via `returningResultSetRowMapper`; distinguish `expectSingleResult` from a single row.
15. Write Mockito tests for `InboundEventRowMapper` covering `NULL`, wrong column names, timestamps, and schema errors.
16. Write an H2/production-compatible DB integration test verifying the mapper, then test inbound flow message shapes via a test-only `QueueChannel`.
17. Simulate a DB query returning 10,000 rows, measure heap/latency, and apply bounded batching; avoid unbounded lists in gateways.
18. Design lease/outbox handling when a row is `CLAIMED` but the process crashes before Kafka receives the event; explain why fixing `RowMapper` does not prevent data loss.

**Comprehensive scenario:** an ERP system stores tens of thousands of `order_event` rows; Spring Integration polls 50 rows at a time and forwards them to Kafka. Two instances run concurrently, and one crashes after marking rows as `CLAIMED`. Define the payload shape before/after the splitter, query conditions, atomic claiming, lease/recovery, stable event IDs, transaction boundaries, and how to test `RowMapper` so you neither lose rows nor publish duplicates endlessly.

## 23. References

- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): SELECT results as `List` payloads, default mapper, splitters, SELECT/UPDATE, and pollers.
- [Spring Integration — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): `RowMapper` for SELECT replies, `maxRows`, and empty list behavior.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc.inboundAdapter`, `Jdbc.outboundGateway`, and DSL specs from Spring Integration 7.0.
- [Spring Integration API — JdbcInboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/dsl/JdbcInboundChannelAdapterSpec.html): `rowMapper`, `maxRows`, `updateSql`, and parameter source factories.
- [Spring Integration API — JdbcPollingChannelAdapter 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/jdbc/JdbcPollingChannelAdapter.html): constructors, `setRowMapper`, `setMaxRows`, post-poll SQL updates.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, `ResultSetExtractor`, and callback contracts.
- [Spring Framework API — BeanPropertyRowMapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html): bean properties, column labels, null primitives, and convenience mapping trade-offs.
- [Spring Framework API — DataClassRowMapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html): Java record/Kotlin data class constructor mapping.
- [Spring Integration — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transactions in polling message flows and downstream handlers.

> **Remember:** `RowMapper<T>` turns **one row of a JDBC `ResultSet` into one `T` object**, while the JDBC inbound adapter normally packages **the entire `List<T>` into one message**. To get one message per row, add a splitter. Solid designs need explicit DTOs/aliases/nullability, testing with a real JDBC driver, sensible query/poller limits, and separation of mapping concerns from transactions, delivery, idempotency, and recovery.

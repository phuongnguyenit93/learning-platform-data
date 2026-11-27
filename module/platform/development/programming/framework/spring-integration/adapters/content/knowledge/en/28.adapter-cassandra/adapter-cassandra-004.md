# Prepared statements and parameter binding in Cassandra

## 1. Why prepare CQL before passing data?

A Spring Integration flow receives an `OrderPaid` event from JMS and then stores it in Apache Cassandra. Writing statements with string concatenation can look deceptively simple:

~~~java
// DO NOT DO THIS: data from an external source is concatenated directly into CQL.
String unsafe = "SELECT event_id FROM order_event WHERE event_id = '"
        + eventId + "'";
~~~

If `eventId` contains quotes or special CQL characters, the statement can break. More importantly, string-concatenated code creates a **CQL injection** surface and produces a distinct CQL string per value, wasting parse/prepare resources and making queries hard to govern.

The right solution is **prepared statements and parameter binding**:

~~~sql
SELECT event_id, order_id, event_type
FROM order_event
WHERE event_id = ?;
~~~

The application prepares a **stable CQL statement**, then binds the `eventId` value separately to the `?` placeholder. The value is encoded by the driver according to its CQL type; it **never becomes statement syntax**. The Cassandra 4.x driver also maintains a **`CqlSession`-level prepared-statement cache**, and Cassandra maintains server-side caches/metadata for repeated execution.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel` connect files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while enforcing message contracts, error handling, and connection lifecycles. Within the **Adapter Cassandra** chapter, **Prepared statements and parameter binding** focuses on turning a Spring Message into a safe, strongly typed, and testable CQL operation.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish `SimpleStatement`, `PreparedStatement`, and `BoundStatement` in the Java Driver.
2. Use positional `?` markers and named `:name` markers with the right semantics.
3. Write code directly with `CqlSession.prepare(...)`/`bind(...)`, understanding immutability and caching rules.
4. Use Spring Data Cassandra's `CqlTemplate`/`ReactiveCqlTemplate` and `PreparedStatementCreator`/`PreparedStatementBinder`.
5. Pass parameters from `payload`/`headers` in the **Spring Integration Cassandra outbound gateway/adapter**.
6. Distinguish bound values from table/column names, CQL `NULL` from `UNSET`, batch/ingest, and conditional writes.
7. Control retries, idempotency, paging, timeouts, and acknowledgment boundaries with JMS/Kafka.

## 2. SimpleStatement, PreparedStatement, and BoundStatement

In Java Driver 4.x, the three essential types for understanding **prepared binding** are:

| Type | How it is created | Pre-bound? | When to use |
|---|---|---|---|
| `SimpleStatement` | `SimpleStatement.newInstance(cql)` or builder | Can hold positional/named values for higher layers to prepare/bind | Infrequent CQL or constructing a statement before passing to a template |
| `PreparedStatement` | `CqlSession.prepare(cql)` | Does **not** hold values for a single execution yet | CQL executed repeatedly with the same structure |
| `BoundStatement` | `prepared.bind(values...)` or `prepared.boundStatementBuilder()` | **Yes**, holds encoded/type-checked values | Object passed to `CqlSession.execute(...)` |

**Exact driver-level classification:** executable `Statement<?>` types are `SimpleStatement`, `BoundStatement`, and `BatchStatement`; `PreparedStatement` is the **output of the prepare step, not yet a bound statement ready for execution**. The table above focuses on the three objects involved in prepare/bind. Batches can contain `BoundStatement` instances and carry their own partition, consistency, and coordinator-cost semantics.

### 2.1. Prepare and execute sequence

~~~mermaid
sequenceDiagram
    participant App as Spring service / handler
    participant Driver as Java driver CqlSession
    participant Broker as Cassandra coordinator

    App->>Driver: prepare("SELECT ... WHERE event_id = ?")
    Driver->>Broker: PREPARE CQL (if not cached)
    Broker-->>Driver: Prepared ID + parameter type metadata
    Driver-->>App: PreparedStatement
    App->>App: bind("evt-4001") -> BoundStatement
    App->>Driver: execute(bound)
    Driver->>Broker: EXECUTE Prepared ID + encoded values
    Broker-->>Driver: Rows / error
    Driver-->>App: ResultSet / exception
~~~

**A prepared statement is a parsed plan with required metadata, not a command already containing one event's values.** Each request with different values must bind an appropriate `BoundStatement`. When running with `evt-4002`, the application can reuse the **same `PreparedStatement`** and build a new `BoundStatement`.

### 2.2. Why are prepared statements useful?

- **Safer handling of values:** bound values are not parsed as CQL syntax, reducing injection risks via data.
- **Performance for repeated queries:** the coordinator avoids re-parsing the same CQL on every execution via the provider's prepared cache.
- **Early type information:** metadata lets the driver verify codecs/types of bind variables.
- **Routing:** the driver can derive the partition/routing key when all key bind values are present.
- **Smaller wire payload:** Prepared ID + values can be more compact than repeatedly sending the full CQL string.

Not every query should be prepared: a one-off CQL DDL statement during migration can use `SimpleStatement`. Prepared statements do **not** automatically raise consistency levels, create multi-table transactions, or make non-idempotent mutations safe to retry.

## 3. Illustrative schema and environment

The examples use Java 17+, Spring Integration 6+/7+, a compatible Spring Data Cassandra version, and a Cassandra test cluster.

~~~sql
-- Use SimpleStrategy only for a single-node test cluster.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    schema_version int,
    occurred_at timestamp,
    payload_json text
);
~~~

`event_id` is the partition key because the exercise reads and writes by `eventId`. If the business needs all events for an `orderId`, design a separate table with suitable partition/clustering keys. Cassandra optimizes around **query patterns**; simply using a prepared statement will not make arbitrary `WHERE` clauses fast.

Sample event:

~~~json
{
  "eventId": "evt-4001",
  "orderId": "ORD-4001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

### 3.1. Dependencies

With Spring Boot BOM managing compatible versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
<!-- For ReactiveCassandraOperations and the built-in Cassandra adapter/gateway. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Not every application needs both imperative and reactive starters; choose according to your flow. If you only run driver/`CqlTemplate` without Spring Integration, the integration dependency is unnecessary.

A Spring Boot configuration for a lab environment:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

`datacenter1` must match the cluster's local DC. This is an illustrative `application.yml`, **not** a lesson metadata YAML file. Keyspaces/tables must be created deliberately via scripts/migrations; do not assume the starter creates them automatically.

### 3.2. Long-lived CqlSession

`CqlSession` is the driver session normally created and reused by Spring Boot or a configuration bean. Never call `CqlSession.builder()` and `close()` **per Spring Message**: it manages multiple connections/resources, and continuous re-creation can overload the cluster.

**A prepared statement is tied to the session in use.** Creating multiple `CqlSession` instances unintentionally for the same cluster/app fragments the cache and multiplies connections. Production should centralize session lifecycle, credentials, TLS, and ACL management.

## 4. Positional binding: `?` must match in order

CQL with anonymous placeholders:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, schema_version, occurred_at, payload_json
) VALUES (?, ?, ?, ?, ?, ?);
~~~

Bind order is **not based on Java field names**; `index=0` corresponds to the first `?`, then 1, 2...

### 4.1. PreparedStatement and BoundStatement

~~~java
import java.time.Instant;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class OrderEventPreparedDao {

    private final CqlSession session;
    private final PreparedStatement insertEvent;

    public OrderEventPreparedDao(CqlSession session) {
        this.session = session;
        this.insertEvent = session.prepare("""
                INSERT INTO order_event
                (event_id, order_id, event_type,
                 schema_version, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """);
    }

    public void save(String eventId, String orderId,
                     String eventType, int version,
                     Instant occurredAt, String payloadJson) {

        BoundStatement statement = insertEvent.bind(
                eventId, orderId, eventType,
                version, occurredAt, payloadJson);

        session.execute(statement);
    }
}
~~~

Here the constructor calls `prepare(...)` once when the DAO is initialized; each `save(...)` calls `bind(...)` to produce a new statement with different values. This assumes the Cassandra session targets keyspace `shop_integration` and the table exists. For `Instant`, the driver needs a codec for Cassandra `timestamp` (built into modern drivers).

**Avoid swapping the order** of `eventId` and `orderId` because both are `String`; that mistake can **go undetected by both the Java compiler and codecs**. Validate contracts and use integration tests that read the persisted record back from the DB.

### 4.2. Explicit positional setters

~~~java
BoundStatement bound = insertEvent.bind()
        .setString(0, eventId)
        .setString(1, orderId)
        .setString(2, eventType)
        .setInt(3, version)
        .setInstant(4, occurredAt)
        .setString(5, payloadJson);

session.execute(bound);
~~~

**Immutability is a crucial rule:** setters like `setString(...)`, `setInt(...)`, and `setInstant(...)` return a **new `BoundStatement`**. Chain calls as shown or reassign the variable; never call a setter and ignore its return value.

~~~java
// WRONG: the setter result is ignored; the original statement is unchanged.
BoundStatement wrong = insertEvent.bind();
wrong.setString(0, eventId);

// RIGHT:
wrong = wrong.setString(0, eventId);
~~~

The snippets in this section belong inside a class/method that already defines `insertEvent`, `eventId`, and `session`; they do not run standalone outside the DAO context.

## 5. Named binding: `:name` and meaningful parameter names

When a CQL statement has many variables, positional binding makes it easy to swap fields of the same Java type. **Named markers** clarify each parameter's role:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, schema_version, occurred_at, payload_json
) VALUES (
    :eventId, :orderId, :eventType, :schemaVersion, :occurredAt, :payloadJson
);
~~~

### 5.1. Driver binding by name

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare("""
        INSERT INTO order_event
        (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
        VALUES (:eventId, :orderId, :eventType,
                :schemaVersion, :occurredAt, :payloadJson)
        """);

BoundStatement bound = prepared.bind()
        .setString("eventId", eventId)
        .setString("orderId", orderId)
        .setString("eventType", "OrderPaid")
        .setInt("schemaVersion", 1)
        .setInstant("occurredAt", occurredAt)
        .setString("payloadJson", payloadJson);

session.execute(bound);
~~~

In `setXxx("name", ...)` calls, **omit the `:`** in the name argument. Here `eventId` is the marker name, not the Cassandra column name (the column is `event_id`). When authoring CQL, follow consistent naming conventions and avoid reusing the same marker name for two distinct values.

### 5.2. Named binding on CQL written with `?`

The driver can derive names for anonymous markers from **the column the marker references**. For example:

~~~sql
SELECT event_type
FROM order_event
WHERE event_id = ?;
~~~

In some cases you can bind by column name `event_id` instead of index. However, when **the same column appears multiple times** (such as `occurred_at > ? AND occurred_at < ?`), inferred names become ambiguous.

**Recommendation:** use positional indices for CQL written with `?`, or declare **unique named markers** for each distinct position. Do not assume default driver name inference works cleanly for complex expressions.

### 5.3. Choosing between positional and named binding

| Criterion | Positional `?` | Named `:name` |
|---|---|---|
| Quick to write for a few variables | Very convenient | Slightly more verbose |
| Many variables of the same type | Easy to swap accidentally | Clear to read and review |
| Marker name in contract | None | Present, though it is the **CQL marker name**, not automatically a JSON field |
| Driver binding | `bind(v1, v2)`, `setString(0, ...)` | `setString("eventId", ...)` |
| With basic Spring Data `CqlTemplate` | Varargs bind positionally in order | Use callbacks if named control is needed |
| With Spring Integration `.query(...)` | Commonly uses named-marker queries | DSL `.parameter("name", ...)` maps from message |

Never use an unvalidated `Map` to generate dynamic marker names from HTTP/JMS inputs. Mappers and queries must use a **predefined** set of names.

## 6. `BoundStatementBuilder`: optimizing binds and per-request options

Every setter on an immutable `BoundStatement` allocates a new object. When binding many parameters or setting per-operation consistency/timeouts, use `boundStatementBuilder()`:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

BoundStatement toSend = prepared.boundStatementBuilder()
        .setString("eventId", eventId)
        .setString("orderId", orderId)
        .setString("eventType", "OrderPaid")
        .setInt("schemaVersion", 1)
        .setInstant("occurredAt", occurredAt)
        .setString("payloadJson", payloadJson)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true)
        .build();

session.execute(toSend);
~~~

This is a fragment on a **prepared statement with named markers**, not a blanket recommendation to use `LOCAL_QUORUM` or a 2-second timeout in every production cluster. Consistency must fit your replication topology, p99 latency, and domain rules; `setIdempotent(true)` is appropriate only when both the CQL and its business effect are genuinely safe for driver retries.

### 6.1. Immutable statement vs mutable builder

- `PreparedStatement` is reused across independent bind operations.
- `BoundStatement` is treated by the driver as immutable; setters return a new instance.
- `BoundStatementBuilder` is a builder for a single bind operation, producing a `BoundStatement` via `build()`.
- Never share a single mutable builder across threads/calls; create a fresh builder per operation.

For a service processing many messages concurrently, **`PreparedStatement` can be shared**, while each event should get its own **`BoundStatement`**. Never share a global mutable builder and overwrite `eventId` from different threads.

### 6.2. Prepared statements and routing keys

Prepared metadata tells the driver which variables belong to the **partition key**, such as `event_id`. When all partition key values are bound, the driver can compute the routing key and prefer nodes holding relevant replicas (token-aware routing), reducing network hops.

However:

- Missing a partition-key bind value can invalidate the query or prevent token-aware routing.
- Prepared metadata cannot fix a flawed Cassandra table model.
- Unevenly distributed partition keys still cause **hot partitions**.
- For CQL where the partition key cannot be inferred, explicit routing metadata in the statement/driver config may be required.

To optimize read/write throughput, measure **coordinator node distribution** and actual query latency rather than assuming "prepared" automatically equals optimal.

## 7. Null vs UNSET: a difference that can cause data loss

This is one of the most critical distinctions when binding Cassandra values:

| Bind state | Meaning | Typical consequence |
|---|---|---|
| **Concrete value** | Sets a CQL value | Inserts/updates the corresponding column |
| **CQL `NULL`** | Sets the variable to null | In mutations, can create a **tombstone/delete the value** |
| **`UNSET`** | Leaves the marker unset | Under supporting protocols/providers, the mutation skips that field |
| **Unintended missing bind** | Programmer forgot a marker | May fail or behave unexpectedly depending on statement/protocol |

### 7.1. Binding null explicitly

~~~java
// On a BoundStatement for a CQL UPDATE with named marker :payloadJson.
BoundStatement withNull = preparedUpdate.bind()
        .setString("eventId", eventId)
        .setToNull("payloadJson");
session.execute(withNull);
~~~

In an `UPDATE`, null can create a **tombstone** representing a deleted column. It does **not** mean "keep the old value".

### 7.2. UNSET when leaving a column untouched

~~~java
BoundStatement withoutPayloadUpdate = preparedUpdate.bind()
        .setString("eventId", eventId)
        .unset("payloadJson");
session.execute(withoutPayloadUpdate);
~~~

`UNSET` has been supported since Cassandra native protocol V4 (Cassandra 2.2+). In mutations, unset preserves the existing column value. Never treat `unset` and `setToNull` as equivalent.

### 7.3. Partial UPDATE example

~~~sql
UPDATE order_event
SET event_type = :eventType, payload_json = :payloadJson
WHERE event_id = :eventId;
~~~

If the API only wants to update `eventType` while leaving the previous JSON payload intact, use `UNSET` for `payloadJson` or build a separate `UPDATE` statement touching only the target column. **Never** turn a missing JSON field automatically into CQL `NULL`, as that creates tombstones and deletes existing data.

### 7.4. Avoiding ambiguity with Java `null`

A call like `prepared.bind(a, null, c)` does not clearly express whether you intend CQL `NULL` or `UNSET`. For partial updates, explicitly call `setToNull(...)` or `unset(...)` so code reviews and integration tests reveal the intent. If using a Spring Data entity mapper, check its null-saving strategy, version, and write options; **do not extrapolate one DAO mapper's behavior back onto `CqlTemplate`**.

## 8. Binding data types: String does not replace every Cassandra codec

Every marker is prepared by Cassandra with a **CQL type**. The driver uses codecs to serialize Java objects into the expected binary format. Common mappings:

| Cassandra type | Suitable Java value | Example driver setter |
|---|---|---|
| `text`, `varchar` | `String` | `setString(...)` |
| `int` | `int` / `Integer` | `setInt(...)` |
| `bigint` | `long` / `Long` | `setLong(...)` |
| `boolean` | `boolean` | `setBoolean(...)` |
| `uuid` | `java.util.UUID` | `setUuid(...)` |
| `timestamp` | `java.time.Instant` | `setInstant(...)` |
| `date` | `java.time.LocalDate` | `setLocalDate(...)` |
| `decimal` | `java.math.BigDecimal` | `setBigDecimal(...)` |
| `blob` | `java.nio.ByteBuffer` | `setByteBuffer(...)` |
| `list<text>` | `List<String>` | `setList(index, values, String.class)` |

For example, if the schema has `schema_version int` and a Java producer supplies `"1"` as a `String`, the driver is not guaranteed to auto-parse Strings into ints across all codec paths. Convert and validate **before binding**:

~~~java
int version;
try {
    version = Integer.parseInt(versionFromInput);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException("schemaVersion must be an integer", ex);
}

BoundStatement bound = prepared.bind()
        .setString("eventId", eventId)
        .setInt("schemaVersion", version);
~~~

This fragment assumes a query with `:eventId` and `:schemaVersion`. Do not call `setString("schemaVersion", "1")` simply because the incoming JSON had a string.

### 8.1. CQL collections, UDTs, and codecs

Columns like `list<text>`, `set<uuid>`, `map<text,int>`, UDTs, tuples, and vectors carry **type parameters** or complex codecs. Verify compatibility between Java generic types and the CQL schema; for example:

~~~java
BoundStatement bound = preparedTags.bind()
        .setString("eventId", eventId)
        .setList("tags", java.util.List.of("billing", "validated"), String.class);
~~~

Here `preparedTags` is a prepared UPDATE/INSERT with a `:tags` marker for a `list<text>` column. Use the driver APIs matching the collection type; do not serialize a `List<String>` into a CSV string when the table expects `list<text>`.

### 8.2. When schemas or types evolve

When altering CQL schemas in a running environment, prepared-statement/driver metadata may not update instantaneously everywhere. On Cassandra 3 and earlier, prepared `SELECT *` is especially fragile when adding/dropping columns due to cached result metadata. Prefer:

~~~sql
SELECT event_id, order_id, event_type
FROM order_event
WHERE event_id = ?;
~~~

Select explicit columns, coordinate schema migrations with backward-compatible code deployments, and run integration tests post-migration. **Prepared statements do not replace migration management.**

## 9. `CqlTemplate`: prepared binding without calling `session.prepare()` manually

Spring Data Cassandra provides `org.springframework.data.cassandra.core.cql.CqlTemplate` and the `CqlOperations` interface. This **synchronous** API wraps the driver, creating/reusing prepared statements, binding arguments, mapping rows, and translating exceptions.

According to official documentation:

- `execute(String cql)`: runs a static CQL statement normally with no arguments to bind.
- `execute(String cql, Object... args)`: **uses a prepared statement** and binds positional args in order.
- `queryForObject(String cql, Class<T>, Object... args)`: queries a single value with bound arguments.
- Overloads accepting `PreparedStatementCreator` and `PreparedStatementBinder`: allow full customization of preparation and binding.

### 9.1. CqlTemplate INSERT and SELECT

~~~java
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public class EventCqlRepository {

    private final CqlOperations cql;

    public EventCqlRepository(CqlOperations cql) {
        this.cql = cql;
    }

    public void insert(String eventId, String orderId,
                       String eventType, int schemaVersion,
                       java.time.Instant occurredAt, String json) {
        cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
                eventId, orderId, eventType, schemaVersion, occurredAt, json);
    }

    public String findEventType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

Spring injects a `CqlTemplate` bean implementing `CqlOperations` configured with `SessionFactory`/`CqlSession`. The repository must still validate schemas and caller permissions before writing; binding prevents values from turning into CQL syntax, yet **does not automatically authorize every event or tenant to access the database**.

### 9.2. Callbacks to customize preparation

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

List<String> ids = cqlTemplate.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        prepared -> prepared.bind("evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

This is the classic example of **three callbacks**:

1. `PreparedStatementCreator` receives `CqlSession` and produces a `PreparedStatement`.
2. `PreparedStatementBinder` receives `PreparedStatement` and produces a `BoundStatement`.
3. `RowMapper` receives each Cassandra `Row` and maps it to a Java type.

When a query returns multiple rows, `query(...)` materializes a `List<T>`; `RowMapper` does not stream end-to-end by itself. For large datasets, design partitions/paging and never query an entire table into an unbounded list.

### 9.3. Binding by name inside a callback

When using named CQL markers, you can write:

~~~java
String cqlText = """
        SELECT order_id FROM order_event WHERE event_id = :eventId
        """;

List<String> orderIds = cqlTemplate.query(
        session -> session.prepare(cqlText),
        prepared -> prepared.bind()
                .setString("eventId", "evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

Here `cqlText` is a **static CQL string**; `"evt-4001"` is passed strictly as a bound value. If the value comes from HTTP/JMS, extract it from a validated DTO; never pass raw HTTP body content as CQL query text.

### 9.4. `ArgumentPreparedStatementBinder` and `SimplePreparedStatementCreator`

Spring Data Cassandra includes utility classes:

- `SimplePreparedStatementCreator`: implements `PreparedStatementCreator` for a given CQL string.
- `ArgumentPreparedStatementBinder`: implements `PreparedStatementBinder` with an argument array for a `PreparedStatement`.

In most cases `cqlTemplate.execute(cql, values...)` or `queryForObject(...)` suffices; use callbacks/utilities when explicit customization is needed. Spring Data and Driver 4.x already handle caching; do not build an unbounded in-house map keyed by event values.

### 9.5. `CassandraTemplate` and `ReactiveCassandraTemplate`

`CassandraTemplate` is a higher-level API combining `@Table`, `@PrimaryKey`, converters, and query DSLs. Spring Data Cassandra **enables prepared statements by default** for many template operations and lets you adjust this via `setUsePreparedStatements(...)` on supporting templates.

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.data.cassandra.core.CassandraTemplate;

// Fragment in a service with an injected CassandraTemplate.
cassandraTemplate.setUsePreparedStatements(true);

MappedOrderEvent row = cassandraTemplate.selectOne(
        SimpleStatement.newInstance(
                "SELECT event_id, order_id, event_type, schema_version, "
                + "occurred_at, payload_json FROM order_event WHERE event_id = ?",
                "evt-4001"),
        MappedOrderEvent.class);
~~~

`MappedOrderEvent` in the example is an **application-defined entity annotated with `@Table("order_event")`, primary key, and fields mapped to the table**, unlike the unannotated `OrderEvent` DTO in section 12.3 used purely for manual statement binding. **Never toggle `setUsePreparedStatements(...)` per request on a singleton template**, as it is a shared global setting; configure it before the application begins handling messages.

Spring Data can extract query text and arguments from `SimpleStatement` to prepare/bind before execution; do not assume every custom `Statement<?>` implementation can be auto-prepared by templates. Entity-mapped APIs also follow a different CQL-generation path than low-level `CqlTemplate`.

## 10. `ReactiveCqlTemplate`: binding and subscription

`ReactiveCqlTemplate` and `ReactiveCqlOperations` expose similar methods returning **`Mono`/`Flux`** instead of blocking directly:

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveEventCqlRepository {

    private final ReactiveCqlOperations cql;

    public ReactiveEventCqlRepository(ReactiveCqlOperations cql) {
        this.cql = cql;
    }

    public Mono<Boolean> insert(String eventId, String orderId,
                                String eventType, int version,
                                java.time.Instant occurredAt, String json) {
        return cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
                + "VALUES (?, ?, ?, ?, ?, ?)",
                eventId, orderId, eventType, version, occurredAt, json);
    }

    public Mono<String> findType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

**Reactive publishers are lazy**: returning a `Mono` does not mean I/O has started. Subscription must come from WebFlux, a reactive `IntegrationFlow`, or a managed subscriber. Never call `insert(...)` and drop the returned `Mono`:

~~~java
// WRONG: publisher is discarded; the operation may not run.
reactiveRepository.insert(eventId, orderId, eventType, 1, now, json);

// RIGHT: method in a service with an injected reactiveRepository;
// the caller/framework will subscribe to the returned Mono.
public Mono<Void> saveReactive(
        String eventId, String orderId, String eventType,
        java.time.Instant now, String json) {
    return reactiveRepository.insert(eventId, orderId, eventType, 1, now, json)
            .then();
}
~~~

The second snippet is an illustrative method inside a service with an injected `reactiveRepository`, not a standalone class. Never call `Mono.block()` on a Reactor/WebFlux event loop: it blocks the thread and can cause errors or severely degrade throughput.

### 10.1. Prepared callbacks in reactive code

~~~java
reactiveCqlTemplate.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        prepared -> prepared.bind("evt-4001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

This returns a `Flux<String>` (via the `RowMapper` overload). Spring Data thus supports custom preparation/binding in reactive code without requiring every service to write its own driver reactive bridge.

### 10.2. Error signals occur during execution

~~~java
return reactiveRepository.insert(
                eventId, orderId, eventType, 1, now, json)
        .doOnError(ex -> log.warn("Cassandra error eventId={}", eventId, ex))
        .then();
~~~

This fragment assumes an existing service with `log`. `doOnError` only observes the signal; it does not turn a failed write into a success. Retries, where warranted, must be bounded and error-classified. For non-idempotent operations, retries can duplicate side effects.

## 11. Driver cache, prepared metadata, and dynamic CQL issues

With **Java Driver 4+**, prepared statements are cached at the **`CqlSession`** level. Calling `session.prepare(...)` repeatedly with the same query string can hit the cached statement without sending `PREPARE` to the broker every time.

### 11.1. Cache keys do not depend on bound values

~~~text
Static CQL string:
  SELECT event_type FROM order_event WHERE event_id = ?

Bind eventId:
  evt-4001  -> BoundStatement A
  evt-4002  -> BoundStatement B
  evt-4003  -> BoundStatement C

PreparedStatement:
  One CQL structure can be reused for all three binds.
~~~

If code concatenates each `eventId` into the query string, the driver sees **many distinct CQL strings**, lowering cache hit rates and flooding cluster prepared caches. Never optimize by preparing a separate statement per input value.

### 11.2. The cache also considers execution parameters

Driver docs note that caching depends on the **exact query text** and execution attributes present during `prepare` (such as consistency set on a `SimpleStatement` passed to `prepare`). Two strings differing only in whitespace/casing or prepared attributes can produce separate cache entries.

Therefore:

- Use constant query strings or a DAO that prepares statements once.
- Never generate millions of CQL variants by concatenating business values, dynamic table names, or arbitrary column lists.
- For differing execution profiles, standardize preparation and per-operation settings.
- Monitor `cql-prepared-cache-size` (per driver/version metrics) and `PREPARE`/`UNPREPARED` counts if needed.

### 11.3. Repreparing during node restarts and failovers

A prepared statement is **not a permanent SQL file stored inside the application**. Each Cassandra coordinator/node maintains its own cache; when a node does not recognize a prepared ID, the driver handles `UNPREPARED` and re-sends `PREPARE`.

Driver 4.x supports pre-preparing on other nodes and repreparing when a node comes back up. Even so:

- Repreparing has overhead; with thousands of unique CQL strings, startups or failovers can cause spikes.
- Do not hand-roll `UNPREPARED` retry loops in every handler unless a specific driver/provider requires it.
- During schema changes, type/result metadata can become stale; coordinate migrations with restarts/reprepares and version compatibility as needed.

### 11.4. Preparing does not fix a poorly designed query

`SELECT * FROM order_event` with no partition predicate remains expensive even when prepared. Multi-partition `UPDATE`/`DELETE` statements or giant logged batches remain costly. Query shape, partition distribution, page size, consistency, and backpressure matter at least as much as the prepared cache.

## 12. Spring Integration: binding from Spring Message to Cassandra

Spring Integration Cassandra (since **6.0**) provides the **Cassandra outbound channel adapter** and **Cassandra outbound gateway**. Both rely on `CassandraMessageHandler` and `ReactiveCassandraOperations` and **do not accept imperative `CqlTemplate`** in their constructors.

~~~mermaid
flowchart LR
    A["JMS/HTTP inbound"] --> B["Validate + convert"]
    B --> C["Spring Message: payload + headers"]
    C --> D{"Reply needed?"}
    D -->|"No"| E["Cassandra outbound adapter"]
    D -->|"Yes"| F["Cassandra outbound gateway"]
    E --> G["CassandraMessageHandler: STATEMENT"]
    F --> G
    G --> H["ReactiveCassandraOperations"]
    H --> I[("Cassandra")]
    F -. "Result / Error" .-> J["replyChannel / reactive output"]
~~~

For CQL queries populated from Spring Messages:

- `.query(String)` + `.parameter(name, ...)` supports **named parameters** evaluated against `payload` and `headers`; especially useful for SELECT/gateways.
- `.statementFunction(...)` or `.statementExpression(...)` builds a driver `Statement<?>` from the message.
- `.ingestQuery(...)` performs multi-row INSERTs via a `List<List<?>>` matrix.
- `Type.INSERT/UPDATE/DELETE` expects `@Table`-mapped entities; these modes **do not parse a JSON String and infer bindings automatically**.

### 12.1. Outbound gateway SELECT with named parameters

Suppose the input is a Spring Message with a `String eventId` payload:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findEventFlow(ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("findEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, order_id, event_type, "
                           + "schema_version FROM order_event "
                           + "WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel("findEventResults")
            .get();
}
~~~

Here `.query(...)` switches the handler into **`STATEMENT` mode**, `:eventId` is the **CQL named marker**, and `"payload"` is a **SpEL expression** evaluated against the Spring Message. Notice the two different meanings: `:eventId` is CQL syntax, while `payload` is a Spring Message property.

With the default async gateway, the output can be a reactive publisher/response depending on the operation and channel; inspect the payload type on `findEventResults` and wire an appropriate consumer. If synchronous results are needed in an imperative flow, configure `async(false)` on the endpoint, but never call a blocking handler on a WebFlux event loop.

### 12.2. Binding from headers and payload with validation

Example of a row-limited lookup:

~~~java
.handle(Cassandra.outboundGateway(operations)
        .query("SELECT event_id, order_id, event_type "
               + "FROM order_event WHERE event_id = :eventId LIMIT :limit")
        .parameter("eventId", "payload")
        .parameter("limit", message -> message.getHeaders().get("limit")))
~~~

This is a Java DSL fragment inside a flow that already has `operations`. A missing `limit` header, a `String` type, or an excessive value can cause binding errors or overly expensive queries. **Validate and normalize `limit` to a capped `int`** (e.g., 1..100) before reaching the Cassandra endpoint.

`.parameter(name, expression)` accepts a SpEL `String`, an `Expression` object, or a Java `Function<Message<?>, ?>`. **`parameterExpressions` only works with `query(String)`**; do not attach it to a `statementFunction` handler expecting a second pass of binding.

### 12.3. StatementFunction using a prebuilt PreparedStatement

When you need to **explicitly prepare and cache an INSERT statement**, you can expose a `PreparedStatement` bean and bind it per message:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean("insertEventPreparedStatement")
public PreparedStatement insertEventPreparedStatement(CqlSession session) {
    return session.prepare("""
            INSERT INTO order_event
            (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """);
}

@Bean
public IntegrationFlow insertPreparedEventFlow(
        ReactiveCassandraOperations operations,
        PreparedStatement insertEventPreparedStatement) {
    return IntegrationFlow.from("preparedEventWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return insertEventPreparedStatement.bind(
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.schemaVersion(),
                                event.occurredAt(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Entity/DTO used in the example:

~~~java
import java.time.Instant;

public record OrderEvent(
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String payloadJson) {
}
~~~

In this **`STATEMENT`** mode, the handler receives a `BoundStatement` from `statementFunction(...)`; the `OrderEvent` DTO **does not need** `@Table` if it is only used to bind statements manually. Conversely, using `Type.INSERT` with Spring Data mapping requires a properly annotated `@Table` entity.

**Operational condition:** `insertEventPreparedStatement(...)` prepares the CQL at bean initialization, so the schema must be provisioned before the app starts. If migrations haven't created the table yet, startup can fail immediately during `PREPARE`. Fail-fast is often desirable, but deployment ordering must be coordinated.

### 12.4. Why not `new SimpleStatement("..." + payload)`?

A `SimpleStatement` can still carry **positional values** without concatenating data into CQL:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

return SimpleStatement.newInstance(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, schema_version, occurred_at, payload_json) "
        + "VALUES (?, ?, ?, ?, ?, ?)",
        event.eventId(), event.orderId(), event.eventType(),
        event.schemaVersion(), event.occurredAt(), event.payloadJson());
~~~

This is a return fragment inside `statementFunction(...)`. With some Spring Data template APIs, a `SimpleStatement` carrying CQL + values may be **prepared and bound** by the template before execution. However, that depends on the exact API path; if a **driver prepared statement** is strictly required, `PreparedStatement.bind(...)` in section 12.3 is more transparent.

### 12.5. One-way or replying?

| Endpoint | Configuration | Does caller receive a result? |
|---|---|---|
| Outbound channel adapter | `Cassandra.outboundChannelAdapter(operations)` | Emits no Spring reply; must track completion/errors |
| Outbound gateway | `Cassandra.outboundGateway(operations)` | Produces a reply based on operation and async/sync mode |
| Directly declared handler | `CassandraMessageHandler` + `setProducesReply(true/false)` | Depends on `producesReply` and `outputChannel` |

If business logic needs **LWT `[applied]`**, SELECT results, or write status, use a gateway/driver to **read the result**. A one-way outbound adapter will not send a `ResultSet` back to the caller simply because the query was prepared.

## 13. Ingest query and batching: a parameter matrix is not a per-row PreparedStatement

Spring Integration's `CassandraMessageHandler.setIngestQuery(...)` accepts a CQL INSERT with `?` markers and a **`List<List<?>>` payload**, where each inner list holds one row in marker order.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow batchIngestEvents(ReactiveCassandraOperations operations) {
    String ingestCql = """
            INSERT INTO order_event
            (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """;

    return IntegrationFlow.from("batchEventWrites")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(ingestCql),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Example payload sent to `batchEventWrites`:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> values = List.of(
        List.<Object>of("evt-4001", "ORD-4001", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00Z"), "json-a"),
        List.<Object>of("evt-4002", "ORD-4002", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:01:00Z"), "json-b")
);

batchEventWrites.send(MessageBuilder.withPayload(values).build());
~~~

`batchEventWrites` is an injected `MessageChannel`. This snippet only illustrates the **bound-value matrix**; it does not imply Cassandra batches provide global atomicity like an SQL database transaction.

### 13.1. Risks of ingest/batching

- **Exact count and order:** every inner list must contain exactly six values.
- **Exact types:** `schema_version` must be an `int`, and `occurred_at` needs a timestamp codec.
- **Nulls:** Java's `List.of(...)` rejects nulls; if nullable columns exist, choose a suitable structure and clarify `NULL`/`UNSET` semantics.
- **Size limits:** never pack tens of thousands of events into an unbounded payload; use bounded chunks.
- **Partitions:** a logged batch spanning many partitions is typically costlier than well-distributed individual writes; measure coordinator latency and cluster pressure.
- **Recovery:** if upstream retries the whole batch, each event still needs individual idempotency; do not treat the batch as a deduplication lock.

## 14. Conditional CQL and LWT: bind values do not guarantee exactly-once

Standard Cassandra `INSERT` has **upsert semantics**. Re-executing an INSERT with the same primary key can overwrite or merge column values based on timestamps and conflict-resolution rules. Prepared statements only **separate CQL from data**; they do not convert an INSERT into a unique insert.

### 14.1. `IF NOT EXISTS` with PreparedStatement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class InsertOnceDao {

    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public InsertOnceDao(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare("""
                INSERT INTO order_event
                (event_id, order_id, event_type, schema_version, occurred_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                IF NOT EXISTS
                """);
    }

    public boolean saveOnce(OrderEvent event) {
        ResultSet result = session.execute(insertIfAbsent.bind(
                event.eventId(), event.orderId(), event.eventType(),
                event.schemaVersion(), event.occurredAt(), event.payloadJson()));
        return result.wasApplied();
    }
}
~~~

`ResultSet.wasApplied()` indicates whether the lightweight transaction (LWT) condition applied. When `false`, inspect the existing record:

- **Same `eventId` and same immutable payload:** likely a valid retry/duplicate.
- **Same `eventId` with different content:** potential data-contract violation; quarantine/alert rather than blindly treating it as success.
- **Timeout error:** state remains uncertain; query by key or verify idempotency.

**LWT has higher overhead and latency than regular writes.** Do not enable `IF NOT EXISTS` on every operation just because "prepared statements are good". For a carefully designed immutable event log, an idempotent upsert may suffice; when strict write-once semantics are mandatory, LWT fits after evaluating performance and semantics.

### 14.2. `setIdempotent(true)` on a statement is not business deduplication

`BoundStatement.setIdempotent(true)`/the corresponding builder method is a **hint to the driver's retry policy**: the operation is safe to repeat if the outcome is uncertain. It does **not store a registry of event IDs** or stop a producer from sending two distinct JMS messages.

| CQL operation | Safe for blind retry? | Why? |
|---|---|---|
| SELECT by key | Usually yes | Does not mutate state, though it may reflect a newer point in time |
| INSERT immutable event with fixed key | Conditionally yes | Same key/values reduce risk; watch dynamic timestamps/TTLs |
| INSERT with changing timestamp/TTL per retry | Not always | A later attempt can extend TTL or alter conflict resolution |
| UPDATE setting state with version guard | Conditionally | Must enforce version/conditional semantics |
| Counter increment | **No** | Retries can increment twice |
| Business side effects outside Cassandra | **Not automatic** | The driver does not manage emails, HTTP calls, or other DBs |

Even when a statement is marked idempotent, **end-to-end exactly-once business effect** still requires an event contract and verified idempotency design.

## 15. What does parameter binding protect, and what does it not?

Bind parameters apply only to **value expressions** in valid CQL positions. They are **not** a safe mechanism to accept arbitrary keyspace/table/column names or inject entire CQL fragments.

### 15.1. Wrong example: letting the client control the table name

~~~java
// DO NOT DO THIS: tableName comes from an unvalidated HTTP/JMS header.
String cql = "SELECT event_id FROM " + tableName
        + " WHERE event_id = ?";
~~~

Even when `eventId` is properly bound, the table name can contain invalid syntax or breach tenant boundaries. **Prepared markers do not replace authorization** for database object names.

### 15.2. Selecting identifiers from an allowlist

~~~java
public enum EventStore {
    PAID("order_paid_event"),
    CANCELLED("order_cancelled_event");

    private final String table;

    EventStore(String table) {
        this.table = table;
    }

    public String table() {
        return table;
    }
}
~~~

If two tables are genuinely required, application code selects `EventStore` via **validated business rules**, never raw client strings. Prepared CQL for each table remains **two static query strings**, each with its own cache entry. In many systems, a single table with an appropriate event type/partition key is simpler.

### 15.3. Validation steps before binding

1. **Contract:** check non-empty `eventId`, supported `schemaVersion`, and reasonable JSON length.
2. **Types:** parse JSON strings/numbers into Java `int`, `UUID`, `Instant`, etc. intentionally.
3. **Authorization:** verify the sender is permitted to access this tenant/partition.
4. **Query shape:** use static CQL, allowlisted identifiers, and partition-key predicates.
5. **Value binding:** pass codec-compatible Java scalars/collections into `BoundStatement`.
6. **Runtime policy:** consistency, timeouts, retries, tracing, and concurrency limits.
7. **Result:** inspect `ResultSet` or reactive completion, distinguishing success, `applied=false`, timeouts, and exceptions.

**Do not log raw bound values containing PII, tokens, or credentials** just because `PREPARE`/`EXECUTE` is easy to debug. Brokers, driver traces, application logs, and source DLQs may retain metadata or payloads longer than expected.

## 16. Timeouts, transaction boundaries, and JMS/Kafka sources

In Spring Integration, prepared statements operate at the **Cassandra target**; they do not create an atomic transaction with the **message source**.

~~~mermaid
sequenceDiagram
    participant JMS as JMS broker
    participant Adapter as Inbound adapter
    participant H as Handler / CqlTemplate
    participant DB as Cassandra
    JMS->>Adapter: OrderPaid eventId=evt-4001
    Adapter->>H: DirectChannel, validated payload
    H->>DB: PREPARED EXECUTE (bound values)
    DB-->>H: Write completed per CL
    H-->>Adapter: Handler returns
    Adapter-->>JMS: JMS commit/ack
    Note over JMS,DB: The two resources share no atomic commit
~~~

### 16.1. First failure window: DB wrote, source has not committed

~~~text
Cassandra write evt-4001 succeeds
     -> JVM crashes before JMS commit
     -> Broker redelivers evt-4001
     -> INSERT is executed again
~~~

If the event log uses a fixed `eventId` key, immutable payloads, and appropriate semantics, the retry will not create a duplicate business event. If the operation increments a counter or updates state without a version guard, effects can duplicate or regress.

### 16.2. Second failure window: source commits before Cassandra completion

~~~text
JMS listener -> ExecutorChannel / async Cassandra handler
  -> listener sees handoff succeed
  -> JMS commits
  -> Cassandra async operation fails
  -> JMS cannot automatically roll back the already-committed message
~~~

Spring Integration's `CassandraMessageHandler` defaults to **async**; if synchronous error propagation over `DirectChannel` is required, configure `async(false)` on the endpoint. However, this still does **not** create a distributed transaction. Combine proper acknowledgment boundaries, durable handoffs, retries/outboxes, or other safeguards matching your SLA.

### 16.3. A timeout is not proof the write did not happen

The coordinator may have accepted the write and replicas persisted it while the response was lost. The client sees a timeout; a retry with the same event ID or conditional write may follow. Never use a caught timeout exception to conclude "Cassandra never wrote" and mint a brand-new business ID.

### 16.4. Multi-layer retry budgets

An event can be retried by:

- The Cassandra driver retry policy.
- Spring Retry/Resilience4j at the service layer.
- JMS rollback and broker redelivery.
- Kafka consumer replay when offsets are uncommitted.
- Manual DLQ replay after remediation.

When every layer retries independently, total write attempts can explode beyond expectations. Establish **one end-to-end retry budget**, separate transient failures from permanent contract/schema errors, and monitor duplicate/conflicting `eventId` counts.

### 16.5. `errorChannel` does not replace a DLQ

Spring Integration's `errorChannel` routes `ErrorMessage` instances for observation and classification. It does not guarantee JMS rollback, Kafka offset replay, or a durable DLQ. On synchronous paths, if an error handler **swallows the exception**, the source listener may commit even though the Cassandra operation failed.

In reactive code, errors can also surface **after** the publisher-creating call returns. Ensure subscriptions, error handling, and completion-to-source signaling are explicitly designed.

## 17. Observability and optimizing prepared statements

A system using prepared statements can still perform poorly if the Cassandra data model is mismatched, timeouts are unrealistic, or concurrency is unbounded.

| Metric | Source | Why measure it? |
|---|---|---|
| `cql-prepared-cache-size` | Driver 4.x metrics (if enabled) | Tracks how many prepared statements are cached |
| `PREPARE`/`UNPREPARED`/reprepare events | Driver/broker logs/metrics | Detects cache churn and node-restart issues |
| Query request rate | App/driver | Compares input rate against write completion |
| Read/write latency p50/p95/p99 | Driver + Cassandra | Pinpoints real bottlenecks instead of measuring `send()` |
| Timeout/unavailable/overloaded | Driver exceptions | Separates cluster outages from binding/contract errors |
| Bind/codec exception count | App/mapper | Reveals schema/version mismatches |
| In-flight Cassandra operations | Driver/reactive pipeline | Signals overload and missing backpressure |
| Coordinator/node distribution | Cluster metrics | Verifies token-aware routing and hot partitions |
| Tombstone/compaction warnings | Cluster | Reflects TTL/DELETE/NULL-update behavior |
| LWT applied/failed counts | Business metrics | Tracks duplicates and conflicts |
| JMS queue depth / Kafka lag | Source broker | Shows whether slow Cassandra is causing backlog |

### 17.1. A healthy cache does not mean zero reprepares

Even when the application caches a `PreparedStatement`, the driver can send `PREPARE` to a newly joined/recovered node or after an `UNPREPARED` response. This is normal recovery behavior, not necessarily a bug.

What warrants investigation is **rapid growth in unique CQL texts**: for example, code generating a distinct prepared query per `requestId`, dynamic table name, or arbitrary column list. That forces the driver and cluster to maintain excessive entries and hurts cache hit rates.

### 17.2. Just enough tracing

Log sanitized event IDs, logical operation names, elapsed time, error categories, schema versions, and trace IDs. Never log raw JWTs, passwords, payment details, or full JSON payloads. In metrics, **never use per-event `eventId` as a label**, as cardinality will explode; logs and traces are the right place for IDs.

### 17.3. Optimizing the actual bottleneck

If queries are slow, investigate in order:

1. **Query shape:** is there a partition key, `ALLOW FILTERING`, or an overly broad scan?
2. **Workload distribution:** does the partition key create a hot partition?
3. **Concurrency:** how many requests are in-flight, and does the source apply backpressure?
4. **Prepared reuse:** are static CQL texts and stable markers being reused?
5. **Latency:** are driver request timeouts aligned with Cassandra p99?
6. **Consistency:** do read/write CLs fit replication and SLA?
7. **Rows/bytes:** page sizes, payload sizes, batch sizes, and tombstone pressure?

Do not merely tweak `prepare-on-all-nodes`/`reprepare-on-up` to cure a full-table scan.

## 18. Common errors and troubleshooting table

| Symptom | Possible cause | Fix |
|---|---|---|
| Prepared statement has 6 markers, binds 5 values | Missing field or wrong `?` count | Validate argument lists and constant query strings |
| Event ID written into `order_id` column | Two `String` fields swapped in positional binding | Use named binding or integration tests reading rows back |
| `CodecNotFoundException` | Java type mismatches CQL type | Convert to typed DTOs; call `setInt`/`setInstant` per column |
| Named marker does not exist | Passed `"id"` instead of `"eventId"` or included `:` in name | Align marker names with setter arguments |
| Called `setString(...)` yet DB gets null/old value | Discarded immutable `BoundStatement` setter return value | Reassign or chain setters |
| Partial update wipes out old values | Bound CQL `NULL` instead of `UNSET` | Use `unset(...)` or `UPDATE` only target columns |
| CQL syntax error when event contains quotes | Concatenated values into query string | Use `?`/`:name` markers and bound values |
| Table queried from user-supplied header | Binding does not protect CQL identifiers | Allowlist table/column names and authorize |
| Prepared cache grows continuously | Generated distinct query strings per event ID | Separate static query text from bound values |
| Driver reprepares after node restart | Node lacks cached prepared ID | Monitor and let driver recover; avoid manual PREPARE spam |
| `IF NOT EXISTS` returns false | Row already exists for that key | Check valid duplicate vs conflicting payload |
| Cassandra times out yet row exists | Response lost after write | Idempotent retry/state lookup; do not mint a new event ID |
| `CqlTemplate` fails to compile | Wrong driver vs Spring Data import | Check packages and API versions |
| Spring Integration `parameter(...)` has no effect | Used `statementFunction` instead of `query` | Pick one statement-creation/binding mechanism |
| Gateway SELECT returns unconsumed publisher | Reactive output lacks subscriber/consumer | Configure `FluxMessageChannel`/reply handling properly |
| Adapter `send()` returns true yet Cassandra has no row | Async handler by default | Observe completion; use sync when needed |
| JSON String fails in `Type.INSERT` | Handler expects `@Table` entity | Transform JSON → entity or use `STATEMENT` mode |
| Excessive retries when Cassandra degrades | Driver retry × app retry × broker redelivery | Cap retry budget, add backoff, throttle concurrency |
| Prepared SELECT breaks after old schema migration | Cached metadata/result shape changed | Select explicit columns, maintain version compatibility, verify cache |

### Errors you should not handle by endless retrying

Invalid CQL syntax, missing tables/keyspaces, permission denials, invalid JSON contracts, misspelled markers, and codec mismatches will not vanish a second later. **Fail fast**, alert, and fix the root cause. Transient connection drops or overloaded clusters can be retried under control, provided you know whether the operation is idempotent.

## 19. Hands-on lab: building a complete CQL binding flow

**Environment:** Java 17+, Cassandra 4/5 or compatible, Java Driver 4.x, Spring Data Cassandra, and Spring Integration 6+. Use a test cluster/container with keyspace `shop_integration` and table `order_event` from section 3; never test failure cases or destructive CQL in production.

### Exercise A — Prepare once, bind many times

1. Create a Spring-managed `CqlSession` and instantiate `OrderEventPreparedDao` from section 4.
2. Write three distinct events (`evt-4001`, `evt-4002`, `evt-4003`) using the same `PreparedStatement`.
3. Query each row:

~~~sql
SELECT event_id, order_id, event_type, schema_version
FROM shop_integration.order_event
WHERE event_id = 'evt-4001';
~~~

4. Use appropriate metrics/logs to verify the application does not generate a new CQL string per event.
5. Create a fresh `BoundStatement` per event and verify concurrent requests never cross-contaminate values.

**PASS:** three rows exist with matching IDs/values, event IDs are never concatenated into CQL strings, and one prepared query is reused across binds.

### Exercise B — Positional and named markers

1. Run an INSERT using `?` and `prepared.bind(...)`.
2. Run an equivalent INSERT using `:eventId`, `:orderId`, etc. with named setters.
3. Intentionally swap `eventId`/`orderId` in positional mode in a test to see how subtle the bug is.
4. Fix it with named markers; verify the actual query and stored values.
5. Intentionally misspell a marker name (e.g., `setString("event_id", ...)` when CQL defines `:eventId`) and observe the exception.

**PASS:** clear grasp of positional ordering, omitting `:` in named setters, and the risk when multiple fields share the same type.

### Exercise C — Immutability and null/unset

1. Create `BoundStatement bound = prepared.bind()`, call `bound.setString(...)` while discarding the result in a negative test.
2. Fix it with `bound = bound.setString(...)` or builder chaining.
3. Insert a row with a non-empty `payload_json`.
4. Using a prepared `UPDATE`, bind `setToNull("payloadJson")` and observe the field being deleted/tombstoned per Cassandra semantics.
5. Restore the row, call `unset("payloadJson")`, and update another column; confirm the old payload remains intact.
6. Confirm native protocol/provider support for unset.

**PASS:** clear distinction between immutable setters, CQL `NULL`, and `UNSET`, avoiding accidental deletes when JSON fields are absent.

### Exercise D — CqlTemplate and reactive CqlTemplate

1. Use `CqlTemplate.execute(cql, args...)` to INSERT a new event.
2. Use `queryForObject(cql, String.class, eventId)` to read `event_type`.
3. Use `PreparedStatementCreator` + `PreparedStatementBinder` + `RowMapper` to query by key.
4. Port the logic to `ReactiveCqlTemplate`, returning `Mono`/`Flux` to a subscriber.
5. Call the reactive method without subscribing; contrast with subscribing via a consumer/`StepVerifier`.
6. Disconnect Cassandra and contrast synchronous exceptions against reactive error signals.

**PASS:** both imperative and reactive APIs bind parameters properly; errors are observed and reactive publishers are not abandoned.

### Exercise E — Spring Integration gateway using named parameters

1. Configure `findEventFlow` from section 12.1 and a consumer on `findEventResults`.
2. Send a Spring Message with payload `"evt-4001"`; verify `:eventId` receives the value from `payload`.
3. Add a `limit=10` header and `LIMIT :limit` clause; validate type/range before reaching the gateway.
4. Send a message missing the `limit` header or with the wrong type and confirm binding failure is captured.
5. Test a reactive output channel and verify subscription/result mapping.

**PASS:** `.parameter(...)` names match CQL markers, expressions read payload/headers properly, and CQL is never built from raw JSON/strings.

### Exercise F — Spring Integration adapter using PreparedStatement directly

1. Register `insertEventPreparedStatement` and `insertPreparedEventFlow` from section 12.3.
2. Send `Message<OrderEvent>` to `preparedEventWrites`.
3. Read the DB by `eventId` and verify all fields were bound accurately.
4. Pass a wrong CQL type (e.g., string `schemaVersion` instead of int when converting payload) and observe the error in the transformer/binder.
5. Switch the adapter to `async=true` to see `send()` return before Cassandra completes.
6. When business logic requires read results or conditional write status, switch to an outbound gateway with an appropriate reply path.

**PASS:** the statement function returns a valid `Statement<?>`, Spring Integration does not guess bindings from headers, and the caller understands adapter vs gateway differences.

### Exercise G — Retries, LWT, and source acknowledgment

1. Using `InsertOnceDao.saveOnce(...)`, send `evt-4001` the first time and check `wasApplied()==true`.
2. Send the same event again; verify `wasApplied()==false` and inspect the existing row content.
3. Intentionally send the same ID with a different payload; classify it as a **conflicting event** instead of ignoring it unconditionally.
4. Wire a transacted JMS listener → `DirectChannel` → sync Cassandra handler.
5. Let the Cassandra write succeed, simulate an error before JMS commit, and confirm redelivery causes no invalid side effects.
6. Switch to `ExecutorChannel` or an async handler to observe that the JMS callback can commit before the Cassandra operation finishes.
7. Disconnect Cassandra to test timeouts, backoff, and total retries across layers.

**PASS:** prepared statements are not confused with cross-system transactions; retried events carry stable keys and exceptions hit the right boundaries.

### Comprehensive test matrix

| Scenario | PASS indicator |
|---|---|
| Positional binding | Marker count and values match in the right order |
| Named binding | Setter name matches `:marker`; values encoded properly |
| Prepared reuse | Same CQL text reused; never prepared per event value |
| Immutable statement | Setter return values are kept or builder is used properly |
| Null vs unset | Column deletion and skipped updates are clearly separated |
| Typed binding | `int`, `timestamp`, `text`, and collections use matching codecs |
| Query shape | Queries include valid partition predicates |
| `CqlTemplate` | Arg overloads prepare/bind and translate exceptions |
| `ReactiveCqlTemplate` | `Mono`/`Flux` consumed/subscribed; errors not lost |
| Spring Integration parameter | CQL named markers align with payload/header expressions |
| Statement function | `BoundStatement` built per message; one-way/gateway chosen properly |
| LWT | `[applied]` checked when using `IF NOT EXISTS` |
| Timeouts/retries | Timeouts never equated with "DB did not write" |
| Security | No concatenated user identifiers/CQL fragments; no secrets logged |
| Broker/driver recovery | Cassandra reprepares smoothly when nodes restart |

**Caching, prepared metadata, codecs, LWT, failover, and retry semantics cannot be proven solely by mocking `CqlSession`.** Run integration tests with real Cassandra/test containers; verifying JMS redelivery likewise requires a matching test JMS broker.

## 20. Self-assessment questions

1. How do `PreparedStatement` and `BoundStatement` differ in metadata vs concrete execution values?
2. Why can one `PreparedStatement` be reused for `evt-4001` and `evt-4002` without creating two query strings?
3. In what order are positional `?` markers bound to values?
4. For a query with `:eventId`, do you include the colon in `setString(...)`?
5. Why can two `String` columns be swapped accidentally without a compiler error?
6. Do Driver 4.x setters on `BoundStatement` mutate the original object in place?
7. What advantage does `BoundStatementBuilder` offer when a statement has many markers?
8. What is the difference between CQL `NULL` and `UNSET` in an `UPDATE`?
9. Why shouldn't an omitted field in a partial DTO become CQL `NULL` by default?
10. What does `CodecNotFoundException` usually indicate?
11. Which Java type/setter fits `event_id text`? What if it changes to `uuid`?
12. Do CQL bind markers let you bind arbitrary table and column names?
13. Why does preparing a distinct CQL string per event hurt cache efficiency?
14. At what level does Driver 4.x cache prepared statements?
15. What can force the driver to re-send `PREPARE` even when the app reuses `PreparedStatement`?
16. Why should prepared `SELECT *` be avoided when schemas evolve frequently?
17. How does `CqlTemplate.execute(String, Object... args)` differ from `execute(String)` regarding prepared binding?
18. What roles do `PreparedStatementCreator` and `PreparedStatementBinder` play in Spring Data Cassandra?
19. What happens if `ReactiveCqlTemplate` returns a `Mono` with no subscriber?
20. When should you use `CassandraTemplate` instead of `CqlTemplate`?
21. Why does `CassandraMessageHandler` accept `ReactiveCassandraOperations` rather than `CqlTemplate`?
22. In Spring Integration, which two languages are combined in `.query(...).parameter("eventId","payload")`?
23. When using `statementFunction(...)`, should you expect `parameterExpressions` from `query(...)` to run automatically?
24. What structure does `List<List<?>>` represent in `ingestQuery(...)`?
25. Does standard Cassandra `INSERT` reject existing keys like an RDBMS unique insert?
26. What does `IF NOT EXISTS` mean, and why must you read `wasApplied()`?
27. Does `setIdempotent(true)` on a driver statement stop a producer from sending duplicate events?
28. Why doesn't a Cassandra timeout prove data wasn't saved?
29. How does `DirectChannel` with a sync Cassandra handler differ from `ExecutorChannel` with async at the JMS commit boundary?
30. Which metrics help determine that slow queries stem from a hot partition rather than a missing prepared cache?

## 21. Official references

- [Spring Data for Apache Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): `CqlTemplate`/`ReactiveCqlTemplate`, argument overloads, prepared callbacks, and driver caching.
- [Spring Data for Apache Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`, `RowMapper`, execute/query, and exception translation.
- [Spring Data for Apache Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCqlTemplate`, reactive operations, and subscriptions/errors.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/CqlTemplate.html): `execute`, `queryForObject`, `query` overloads, and callback contracts.
- [Spring Data Cassandra API — PreparedStatementBinder](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/PreparedStatementBinder.html): value-binding responsibility.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, `query`, `parameterExpressions`, `statementProcessor`, and `ingestQuery`.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `parameter(name, expression)`, `query`, `statementFunction`, and DSL.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): prepare/bind, immutable `BoundStatement`, named/positional markers, null/unset, and caching.
- [Apache Cassandra Java Driver 4.19 — Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): `SimpleStatement`, `BoundStatement`, `BatchStatement`, and execution attributes.
- [Apache Cassandra Java Driver 4.19 — Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): prepared reuse, request latency, routing, and throughput.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL data types, primary/partition keys, consistency, LWT, schema migrations, and batch semantics.

**Key takeaway:** `PreparedStatement` holds **CQL structure and metadata**, `BoundStatement` holds **bound values for a single execution**, and `CqlSession`/Driver 4.x manages the prepared cache. Both positional `?` markers and named `:name` markers separate data from CQL syntax; neither protects client-supplied table/column names nor automatically creates exactly-once business processing. In Spring Data, use `CqlTemplate`/`ReactiveCqlTemplate` with prepared arguments; in Spring Integration Cassandra, use `.query(...).parameter(...)` or `statementFunction(...)` with `ReactiveCassandraOperations`. Reliable execution requires checking data types, `NULL`/`UNSET`, query patterns, timeouts, idempotency, acknowledgment boundaries, and real Cassandra cluster behavior.






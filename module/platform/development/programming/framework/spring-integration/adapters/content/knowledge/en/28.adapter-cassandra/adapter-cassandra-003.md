# CqlTemplate and session factory in Spring Data Cassandra

## 1. Why understand CqlTemplate before configuring the Cassandra adapter?

A service receives an `OrderPaid` event via JMS, converts it into a Java object, and writes it to Apache Cassandra. When an error occurs, you need to know where the problem lies: the message contract, cluster connection, keyspace, CQL statement, Java mapping, or how an endpoint awaits the result.

Spring Data for Apache Cassandra provides two distinct layers worth separating:

- **`CqlTemplate`**: low-level API for executing CQL, binding parameters, retrieving results, translating exceptions, and managing repetitive Cassandra driver tasks.
- **`SessionFactory`**: an abstraction supplying `CqlSession` for CQL operations; typically backed by a shared, long-lived driver session.

Below lies the DataStax Java Driver **`CqlSession`**. Above sit **`CassandraTemplate`**, **`ReactiveCassandraTemplate`**, and Spring Integration endpoints that use object mapping/reactive APIs.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel` connect files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; every connection needs clear message contracts, error paths, and lifecycles. The **Adapter Cassandra** chapter uses `CqlTemplate` and session factory knowledge to explain the foundation of Cassandra operations triggered from `IntegrationFlow`.

**Learning objectives:**

1. Distinguish `CqlSession`, `CqlSessionFactoryBean`, `SessionFactory`, `DefaultSessionFactory`, and `SessionFactoryFactoryBean`.
2. Create, inject, and use `CqlTemplate` to run SELECT/INSERT/UPDATE/DELETE with safely bound values.
3. Understand `RowMapper`, `ResultSetExtractor`, `PreparedStatementCreator`, and exception translation.
4. Distinguish blocking `CqlTemplate` from `ReactiveCqlTemplate` and entity-mapped templates.
5. Know when a `@ServiceActivator` can use `CqlTemplate`, and why `CassandraMessageHandler` does not accept `CqlTemplate` as a dependency.
6. Design pooling/session lifecycle, keyspaces, consistency, timeouts, idempotency, observability, and integration tests.

## 2. Layer diagram and responsibilities

~~~mermaid
flowchart TB
    A["JMS / HTTP / Kafka / File"] --> B["Spring Integration: Transformer + MessageChannel"]
    B --> C["Custom Service Activator"]
    B --> D["CassandraMessageHandler"]
    C --> E["CqlTemplate or ReactiveCqlTemplate"]
    D --> F["ReactiveCassandraOperations / ReactiveCassandraTemplate"]
    E --> G["SessionFactory / ReactiveSession"]
    F --> G
    G --> H["CqlSession — DataStax Java Driver"]
    H --> I[("Apache Cassandra cluster")]
~~~

This is a **conceptual** diagram: on the reactive branch, `ReactiveSession` bridges the driver `CqlSession` to publisher APIs; imperative `SessionFactory` is not identical to `ReactiveSession`. Do not mistake the arrows for a single class inheritance chain.

| Component | Package/type | Responsible for |
|---|---|---|
| `CqlSession` | `com.datastax.oss.driver.api.core` | Driver session managing node connections, routing, and CQL requests |
| `CqlSessionFactoryBean` | `org.springframework.data.cassandra.config` | Spring `FactoryBean<CqlSession>` that creates/manages the driver session |
| `SessionFactory` | Spring Data Cassandra | Interface supplying a `CqlSession` to the CQL layer |
| `DefaultSessionFactory` | `org.springframework.data.cassandra.core.cql.session` | Default `SessionFactory` returning a singleton session |
| `SessionFactoryFactoryBean` | `org.springframework.data.cassandra.config` | Creates a `SessionFactory` with mapping/schema lifecycle support |
| `CqlTemplate` | `org.springframework.data.cassandra.core.cql` | Blocking CQL execution; callbacks, result mapping, exception translation |
| `ReactiveCqlTemplate` | `org.springframework.data.cassandra.core.cql` | CQL execution via `Mono`/`Flux` |
| `CassandraTemplate` / `ReactiveCassandraTemplate` | `org.springframework.data.cassandra.core` | Entity mapping via `@Table`, converters, and query abstractions |
| `CassandraMessageHandler` | Spring Integration Cassandra | Endpoint receiving Spring Messages and calling `ReactiveCassandraOperations` |

### Three things most easily confused

**`CqlSessionFactoryBean` is not `SessionFactory`.** The former is a *Spring FactoryBean that builds a driver session*, while the latter is the *Spring Data interface used to obtain a driver session*.

**`CqlTemplate` is not `CassandraTemplate`.** `CqlTemplate` is for programmatic CQL and row-by-row callback mapping; `CassandraTemplate` uses Spring Data object mapping.

**`CqlTemplate` is not a direct dependency of `CassandraMessageHandler`.** The Spring Integration Cassandra handler takes `ReactiveCassandraOperations`. If you want to build a flow directly with `CqlTemplate`, write a custom service activator; if you want the built-in Cassandra outbound adapter/gateway, provide reactive operations.

## 3. CqlSession: a long-lived driver resource, not per-message

The driver `CqlSession` is **thread-safe**, manages connections to multiple Cassandra nodes, and is intended to be **long-lived**. A typical application reuses a single session for the same keyspace/cluster instead of opening and closing a session on every message.

~~~mermaid
flowchart LR
    S["One singleton CqlSession"] --> N1["Connection pool to node A"]
    S --> N2["Connection pool to node B"]
    S --> N3["Connection pool to node C"]
    T1["Worker 1"] --> S
    T2["Worker 2"] --> S
    T3["Worker 3"] --> S
~~~

The diagram does not mean three nodes imply exactly three TCP connections; connection counts and routing depend on driver/version/configuration. The point is that the session is a **shared resource** managed by the Spring/container lifecycle.

### 3.1. Using the driver directly to create a session

~~~java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DirectCqlSessionConfiguration {

    @Bean(destroyMethod = "close")
    public CqlSession cqlSession() {
        return CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .withKeyspace("shop_integration")
                .build();
    }
}
~~~

This is **one lab option** when the `shop_integration` keyspace already exists. Datacenter `datacenter1` must match the Cassandra cluster metadata. Spring calls `close()` on bean destruction; **never call `close()` after each SELECT/INSERT**.

With Spring Boot, prefer auto-configuration when available. Do not register both a manually built `CqlSession` and a Boot-created session unless intentionally managing multiple clusters. If the application requires authentication/TLS, supply them via secrets/driver configuration rather than hard-coding credentials in code.

### 3.2. Creating the driver session with CqlSessionFactoryBean

Spring Data provides `CqlSessionFactoryBean`, a Spring `FactoryBean<CqlSession>` that handles session initialization and shutdown.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.CqlSessionFactoryBean;

@Configuration
public class FactoryBeanSessionConfiguration {

    @Bean
    public CqlSessionFactoryBean cqlSession() {
        CqlSessionFactoryBean factory = new CqlSessionFactoryBean();
        factory.setContactPoints("127.0.0.1");
        factory.setPort(9042);
        factory.setLocalDatacenter("datacenter1");
        factory.setKeyspaceName("shop_integration");
        return factory;
    }
}
~~~

**This is an alternative to section 3.1**; do not register both under the same bean name. Spring uses `CqlSessionFactoryBean` to create the `CqlSession` bean; consumers inject type `CqlSession` without manually calling `factory.getObject()`.

#### FactoryBean vs the produced bean

If the factory bean is named `cqlSession`:

- Injecting `CqlSession` or looking up bean `"cqlSession"` returns the **object produced by the FactoryBean**.
- Looking up `"&cqlSession"` (using the `&` prefix in `BeanFactory`) returns the **FactoryBean itself**, mainly for configuration or diagnostics.
- `CqlSessionFactoryBean` does **not** replace `DefaultSessionFactory` or `SessionFactoryFactoryBean` in the Spring Data layer.

Some older articles/snippets still use `CassandraCqlSessionFactoryBean`; that class is deprecated and replaced by `CqlSessionFactoryBean`. Avoid copying legacy API configurations into new implementations.

### 3.3. Spring Boot auto-configuration

In a BOM-managed Spring Boot application, a local example configuration looks like:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

This is the **application's `application.yml`** (not a lesson metadata YAML file). When using `spring-boot-starter-data-cassandra` or the reactive starter, Spring Boot can create `CqlSession` and the corresponding templates; exact beans are conditional on version and auto-config conditions.

Pick **one** session management approach in the application:

1. Spring Boot auto-configuration (common).
2. Driver `CqlSession.builder()` as a lifecycle-managed bean.
3. Spring Data `CqlSessionFactoryBean` or `AbstractCassandraConfiguration` when deep customization is needed.

Do not conclude "Cassandra isn't connected" solely because no bean is literally named `cqlSession`: bean names and auto-configuration conditions can vary. Inspect actual bean types and the dependency tree.

## 4. SessionFactory: CqlSession-level abstraction for CqlTemplate

Spring Data Cassandra defines its own `SessionFactory`. For simple cases, `DefaultSessionFactory` wraps **a single `CqlSession`** and always returns that same session.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.data.cassandra.core.cql.session.DefaultSessionFactory;

@Configuration
public class LowLevelCqlConfiguration {

    @Bean
    public SessionFactory sessionFactory(CqlSession cqlSession) {
        return new DefaultSessionFactory(cqlSession);
    }

    @Bean
    public CqlTemplate cqlTemplate(SessionFactory sessionFactory) {
        return new CqlTemplate(sessionFactory);
    }
}
~~~

This example uses a `CqlSession` bean already configured **by one of the approaches in section 3**. `CqlTemplate` also has a constructor taking `CqlSession` directly:

~~~java
// Valid, though using SessionFactory is cleaner if you need the abstraction.
CqlTemplate template = new CqlTemplate(cqlSession);
~~~

**Lifecycle:** calling `CqlTemplate.query(...)` does not close the driver session after one query. When the Spring app shuts down, the bean owning `CqlSession` is responsible for closing connections. `DefaultSessionFactory` is not a separate connection pool; it simply wraps the shared session.

### 4.1. SessionFactoryFactoryBean in mapping/schema infrastructure

When Spring Data entity mapping and schema actions are needed, configuring `SessionFactoryFactoryBean` is an additional option:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.config.SchemaAction;
import org.springframework.data.cassandra.config.SessionFactoryFactoryBean;
import org.springframework.data.cassandra.core.convert.CassandraConverter;

@Bean
public SessionFactoryFactoryBean mappedSessionFactory(
        CqlSession cqlSession,
        CassandraConverter converter) {

    SessionFactoryFactoryBean factory = new SessionFactoryFactoryBean();
    factory.setSession(cqlSession);
    factory.setConverter(converter);
    factory.setSchemaAction(SchemaAction.NONE);
    return factory;
}
~~~

`CassandraConverter` must be configured with a mapping context/UDT resolver when wired manually; `AbstractCassandraConfiguration` or Boot normally wires these components. `SchemaAction.NONE` specifies **not modifying database schemas automatically on startup** in this example.

**Important:** pick either **`DefaultSessionFactory`** *or* **`SessionFactoryFactoryBean`** for the `SessionFactory` bean injected into `CqlTemplate`; avoid creating two beans of the same type without `@Qualifier` or `@Primary`. `CqlSessionFactoryBean` still creates the lower-level session; `SessionFactoryFactoryBean` creates the higher-level **`SessionFactory`**.

### 4.2. Why not switch keyspaces with CQL `USE` on every request?

A session is bound to its keyspace and driver connection infrastructure. Switching keyspaces via `USE other_keyspace` on a shared session can cause unpredictable behavior across concurrent threads/queries and break mapping consistency.

If the system needs multiple keyspaces/tenants, prefer:

- Dedicated `SessionFactory`/`CqlTemplate` instances per fixed keyspace.
- A routing session factory properly configured and tested with thread-safe context propagation.
- Fully qualified table names where permitted by access controls and allowlisted queries, rather than mutating the session keyspace.

Multi-tenant decisions also involve ACLs, replication, quotas, and isolation; never trust a client-supplied `tenantId` header alone to grant access to another keyspace.

## 5. Preparing schema and dependencies for CQL practice

With a BOM-managed Spring Boot project, common dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
<!-- Only needed when using reactive or the built-in Cassandra adapter/gateway. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Not every application needs both the **imperative starter** and the **reactive starter**: choose based on the APIs you use. `CqlTemplate` belongs to Spring Data Cassandra core; `CassandraMessageHandler` in `spring-integration-cassandra` uses `ReactiveCassandraOperations`. Do not add only the Spring Integration dependency expecting it to auto-create keyspaces/tables.

On **test** Cassandra, create:

~~~sql
-- Use this replication model only in a single-node lab.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text,
    processed_at timestamp
);
~~~

The table is designed to **query by `event_id`**. Frequent queries such as `WHERE order_id = ?` are **not optimal** with this schema because `order_id` is not a partition key. Cassandra design must follow query patterns; do not abuse `ALLOW FILTERING` to "patch" an unsuitable data model.

### Sample data

~~~json
{
  "eventId": "evt-3001",
  "orderId": "ORD-3001",
  "eventType": "OrderPaid",
  "schemaVersion": 1
}
~~~

`eventId` is a business ID stable across retries. `schemaVersion` appears in the payload contract even though the lab table has no dedicated column for it yet; storing it separately requires deliberate schema/mapping updates, not assuming Cassandra splits JSON automatically.

## 6. CqlTemplate: running INSERT with prepared bind values

`CqlTemplate` executes CQL **synchronously (blocking)**. For statements carrying user- or message-supplied values, use `?` placeholders and bound arguments instead of concatenating CQL strings with data:

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public class OrderEventCqlWriter {

    private final CqlOperations cql;

    public OrderEventCqlWriter(CqlOperations cql) {
        this.cql = cql;
    }

    public void save(String eventId, String orderId,
                     String eventType, String json) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, payload_json, processed_at) "
                + "VALUES (?, ?, ?, ?, ?)",
                eventId, orderId, eventType, json, Instant.now());
    }
}
~~~

Once `CqlTemplate` is configured (section 4), it implements `CqlOperations` and can be injected via the interface. The `execute(String cql, Object... args)` overload uses a **prepared statement with bind values**. The driver and Cassandra cache prepared statements, optimizing repeated queries without the application maintaining an unbounded cache itself.

**Do not rely on the boolean returned by `execute(...)` to assume a brand-new event was created.** With standard CQL INSERT, Cassandra uses *upsert semantics*, so the same key can be overwritten; if "insert only if absent" is required, use conditional write `IF NOT EXISTS` and check the applied result.

### 6.1. INSERT is not an RDBMS unique insert

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, payload_json
) VALUES (
    'evt-3001', 'ORD-3001', 'OrderPaid',
    '{"eventId":"evt-3001"}'
);
~~~

Re-running the same `event_id` normally **does not throw a duplicate-key error** like an RDBMS unique constraint. Cassandra uses timestamps/conflict resolution to determine stored values. If a producer resends **the same event ID with different content**, the business effect can be wrong even though CQL succeeds.

For an event log table, treat `eventId` as an **immutable identity** and detect duplicates with conflicting payloads. For an order state table, enforce version ordering or conditional updates so older events cannot overwrite newer state.

### 6.2. UPDATE and DELETE with CqlTemplate

~~~java
public void changeEventType(String eventId, String eventType) {
    cql.execute(
            "UPDATE order_event SET event_type = ? WHERE event_id = ?",
            eventType, eventId);
}

public void delete(String eventId) {
    cql.execute(
            "DELETE FROM order_event WHERE event_id = ?",
            eventId);
}
~~~

Both snippets are methods in a repository holding `cql`. CQL UPDATE can **create new cells/rows if the key does not exist**, depending on the operation; do not assume updates only succeed when a row already exists. Cassandra DELETE creates **tombstones**, impacting compaction and read performance. Never perform wildcard bulk deletes or accept arbitrary user-supplied WHERE clauses.

## 7. SELECT: RowMapper, queryForObject, and queryForList

`CqlTemplate` offers these methods:

- `queryForObject(...)` when expecting **one row/value** or a mapped single object.
- `query(...)` with `RowMapper<T>` for multiple rows.
- `queryForList(...)` for `List<Map<String,Object>>` or a list of values depending on the overload.
- `queryForStream(...)` when streaming via the supported API, ensuring controlled stream closing/consumption.
- `query(...)` with `RowCallbackHandler` or `ResultSetExtractor` when lower-level callbacks are needed.

### 7.1. Fetching a single column with queryForObject

~~~java
import org.springframework.data.cassandra.core.cql.CqlOperations;

public String findType(String eventId) {
    return cql.queryForObject(
            "SELECT event_type FROM order_event WHERE event_id = ?",
            String.class,
            eventId);
}
~~~

`findType` is a method on a repository with `CqlOperations cql`. `queryForObject` expects the exact matching row/column count; **never use it to scan a whole table**. When zero rows or unexpectedly many rows return, the API may throw result-size exceptions depending on version/overload. Define "not found" handling explicitly with tests rather than relying blindly on `null`.

### 7.2. Mapping a row to a DTO

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.Optional;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.data.cassandra.core.cql.RowMapper;

public record OrderEventRow(
        String eventId, String orderId,
        String eventType, String payloadJson) {
}

public class OrderEventCqlReader {

    private final CqlOperations cql;

    public OrderEventCqlReader(CqlOperations cql) {
        this.cql = cql;
    }

    public Optional<OrderEventRow> findById(String eventId) {
        List<OrderEventRow> rows = cql.query(
                "SELECT event_id, order_id, event_type, payload_json "
                + "FROM order_event WHERE event_id = ?",
                (row, index) -> new OrderEventRow(
                        row.getString("event_id"),
                        row.getString("order_id"),
                        row.getString("event_type"),
                        row.getString("payload_json")),
                eventId);
        return rows.stream().findFirst();
    }
}
~~~

The example shows `RowMapper` receiving a Cassandra driver `Row` and building a Java DTO. The `index` parameter provides the row index when needed; it is **not a Cassandra partition ID**. `Row`/`RowMapper` imports are shown so the API origin is clear; the lambda relies on type inference.

**Benefit of RowMapper:** you control column names and conversions without annotating every DTO with `@Table`. **Trade-off:** the mapper must be updated whenever schema/columns or CQL types change; it does not automatically know `CassandraConverter` object-mapping rules.

### 7.3. queryForList returning Map results

~~~java
import java.util.List;
import java.util.Map;

List<Map<String, Object>> result = cql.queryForList(
        "SELECT event_id, event_type FROM order_event WHERE event_id = ?",
        "evt-3001");
~~~

Map results are handy for ad-hoc diagnostics but sacrifice type safety compared to DTOs. Never expose raw database Maps directly in HTTP responses without filtering/stripping sensitive columns; Spring Message payloads should also have well-defined schemas.

## 8. Prepared statements and callback APIs

In Cassandra, a CQL query executed repeatedly can be **prepared** by the driver with bound values; modern drivers cache prepared statements automatically.

### 8.1. Passing arguments is the simplest approach

~~~java
// CqlOperations automatically chooses the prepared-statement path for overloads with args.
String eventType = cql.queryForObject(
        "SELECT event_type FROM order_event WHERE event_id = ?",
        String.class,
        "evt-3001");
~~~

This is the preferred option for most straightforward queries. For static statements with no arguments, `queryForObject(String cql, Class<T>)` can send a direct CQL statement, whereas overloads with arguments use prepared statements.

### 8.2. PreparedStatementCreator + binder for complex logic

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlOperations;

List<String> orderIds = cql.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        ps -> ps.bind("evt-3001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

The three callbacks here are:

1. **PreparedStatementCreator:** prepares the statement via the template-managed `CqlSession`.
2. **PreparedStatementBinder:** binds concrete values to the prepared statement.
3. **RowMapper:** maps each Cassandra row into a Java `String`.

This setup is useful when customizing statement/binding options or unit-testing individual callbacks. Never re-prepare distinct CQL per event by embedding `eventId` directly in the CQL string; that defeats statement caching and introduces injection risk.

### 8.3. ResultSetExtractor and RowCallbackHandler

| Callback | Usage | Benefit | Limitation |
|---|---|---|---|
| `RowMapper<T>` | One `Row` → one `T` | Easy to test, type-safe | Materializes a list when used with list-returning `query(...)` |
| `RowCallbackHandler` | Processes each row via callback | Avoids manual iteration boilerplate | Callback side effects need control |
| `ResultSetExtractor<T>` | Receives `ResultSet` to extract results directly | Flexible for aggregated outcomes | Easily couples code to driver types |
| `PreparedStatementCreator` | Prepares `PreparedStatement` via session | Customizes how statements are prepared | Adds complexity |
| `PreparedStatementBinder` | Binds params onto prepared statement | Avoids string concatenation | Must match placeholder count/types |

Cassandra uses **paging**: list-returning APIs that collect too much data can cause memory pressure. Query specific partitions with sensible page sizes rather than running `SELECT * FROM huge_table` and dumping everything into a `List` for convenience.

## 9. ReactiveCqlTemplate: same CQL, different execution model

`CqlTemplate` follows a **blocking** model. Spring Data Cassandra also provides `ReactiveCqlTemplate` returning Project Reactor publishers:

- `execute(...)` returns `Mono<Boolean>` for applicable CQL write/DDL statements.
- `queryForObject(...)` returns `Mono<T>`.
- `query(...)` can return `Flux<T>`.

**Reactive is two-phase:** *compose the publisher*, then *subscribe*. Calling `reactiveCqlTemplate.execute(...)` builds a `Mono` that performs no I/O until subscribed.

### 9.1. Creating ReactiveCqlTemplate from the same driver session

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.ReactiveCqlTemplate;
import org.springframework.data.cassandra.core.cql.session.DefaultBridgedReactiveSession;

@Configuration
public class ReactiveLowLevelCqlConfiguration {

    @Bean
    public ReactiveCqlTemplate reactiveCqlTemplate(CqlSession session) {
        return new ReactiveCqlTemplate(
                new DefaultBridgedReactiveSession(session));
    }
}
~~~

`DefaultBridgedReactiveSession` adapts the async operations of driver `CqlSession` into reactive publishers. It does not spin up a second Cassandra cluster. Because the underlying session may be shared, **never arbitrarily close the bridge/session inside individual reactive subscriptions**; let the bean owner/container manage the application lifecycle.

If Spring Boot or `AbstractReactiveCassandraConfiguration` already creates these reactive beans, do not register duplicates merely because the example above demonstrates manual wiring. Verify actual configuration via bean definitions and qualifiers.

### 9.2. Reactive DAO for INSERT and SELECT

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveOrderEventDao {

    private final ReactiveCqlOperations cql;

    public ReactiveOrderEventDao(ReactiveCqlOperations cql) {
        this.cql = cql;
    }

    public Mono<Boolean> save(String eventId, String orderId,
                              String eventType, String json) {
        return cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, payload_json) "
                + "VALUES (?, ?, ?, ?)",
                eventId, orderId, eventType, json);
    }

    public Mono<String> findType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

**Correct caller example in a reactive pipeline:**

~~~java
public Mono<Void> recordPaid(String eventId, String orderId, String json) {
    return reactiveOrderEventDao
            .save(eventId, orderId, "OrderPaid", json)
            .doOnNext(applied -> {
                if (!applied) {
                    throw new IllegalStateException("Conditional write not applied");
                }
            })
            .then();
}
~~~

`reactiveOrderEventDao` is an injected dependency. Never call `save(...)` and discard the `Mono`. In WebFlux, returning `Mono<Void>` to the framework ensures subscription within the request pipeline; in background tasks, choose a controlled subscription/lifecycle/error-handling mechanism.

**Do not automatically treat `Boolean applied` as a business uniqueness guarantee.** A CQL INSERT without `IF NOT EXISTS` still has upsert semantics, so `true` does not mean a brand-new unique event was created. When using LWT, verify the applied result for that specific statement.

### 9.3. Mono/Flux and errors

A Cassandra connection failure in a reactive DAO can emit an **error signal after the method has already returned the publisher**. A `try/catch` solely around `save()` will not catch those errors:

~~~java
return reactiveOrderEventDao.save(eventId, orderId, "OrderPaid", json)
        .doOnError(error -> metrics.recordCassandraFailure(error))
        .retryWhen(
            reactor.util.retry.Retry.backoff(2, java.time.Duration.ofMillis(200))
                .filter(this::isTransientCassandraFailure));
~~~

This fragment illustrates a service with an application-provided `metrics` dependency and `isTransientCassandraFailure(...)` predicate. `retryWhen` is a **bounded policy**, not a recommendation to retry every exception. For non-idempotent writes such as incrementing a counter, blind retries cause duplicate side effects.

### 9.4. Do not call `block()` on an event loop

~~~java
// Use only in imperative code where the thread is allowed to block.
Boolean result = reactiveOrderEventDao
        .save(eventId, orderId, "OrderPaid", json)
        .block();
~~~

`block()` makes the execution path blocking; it can throw errors or degrade throughput on a WebFlux/Reactor event loop. If you want a genuinely reactive flow, return `Mono`/`Flux` to the subscriber and manage concurrency/backpressure rather than blocking in an arbitrary handler.

## 10. Distinguishing templates to pick the right API

| API | Model | `@Table` entity mapping? | When to use |
|---|---|---|---|
| `CqlTemplate` | Blocking | Not automatic like `CassandraTemplate` | Small CQL, diagnostics, custom queries, callbacks |
| `ReactiveCqlTemplate` | Reactive `Mono`/`Flux` | Not automatic like `ReactiveCassandraTemplate` | Reactive CQL, counters/ad-hoc operations |
| `CassandraTemplate` | Blocking | **Yes**, uses converter/mapping context | Domain object CRUD, repositories |
| `ReactiveCassandraTemplate` | Reactive | **Yes**, same Spring Data converter | Reactive CRUD, `CassandraMessageHandler` |
| `CqlSession` (driver) | Driver sync/async API | No Spring Data entity mapping | Cases requiring driver-specific operations |

Do not substitute `CqlTemplate` for `ReactiveCassandraOperations` just because both execute CQL. Built-in Spring Integration Cassandra adapters/gateways require **`ReactiveCassandraOperations`**; when you need an imperative API, write a custom service activator.

### 10.1. `CassandraTemplate` adds an object-mapping layer

`CassandraTemplate` builds on `CqlTemplate`/CQL infrastructure while integrating `CassandraConverter` and mapping context to resolve:

- `@Table`: which table an entity maps to.
- `@PrimaryKey`/`@PrimaryKeyClass`: primary key/partition-clustering keys.
- `@Column`: column names and field mapping.
- Type conversions and UDTs configured via the converter.

`CqlTemplate` only knows CQL and Cassandra `Row`; assembling DTOs/entities via `RowMapper` is up to the developer. Thus the two templates **complement** each other rather than being two names for the same class.

### 10.2. Which one does CassandraMessageHandler use?

~~~java
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;

// Correct: the dependency is reactive operations.
CassandraMessageHandler handler =
        new CassandraMessageHandler(reactiveCassandraOperations);
~~~

`reactiveCassandraOperations` is a bean injected from Spring Data reactive. **Never** pass a `CqlTemplate` into this constructor; if it fails to compile, the problem is not keyspace config but an **API mismatch**.

By default `CassandraMessageHandler` is asynchronous and can run `INSERT`, `UPDATE`, `DELETE`, or `STATEMENT`. With `async(false)`, the handler can await completion of the reactive operation, yet it does **not** turn Cassandra into an RDBMS transaction or a default reply producer.

## 11. Using CqlTemplate via a Spring Integration Service Activator

You can invoke `CqlTemplate` directly from a service activator if the application already uses imperative processing, needs low-level CQL, or prefers not to use the built-in Cassandra outbound adapter.

~~~mermaid
flowchart LR
    A["JMS inbound adapter"] --> B["DirectChannel"]
    B --> C["@ServiceActivator"]
    C --> D["OrderEventCqlWriter"]
    D --> E["CqlTemplate"]
    E --> F["SessionFactory -> CqlSession"]
    F --> G[("Cassandra")]
~~~

### 11.1. One-way service activator

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class SavePaidOrderService {

    private final OrderEventCqlWriter writer;

    public SavePaidOrderService(OrderEventCqlWriter writer) {
        this.writer = writer;
    }

    @ServiceActivator(inputChannel = "paidEventsForCassandra")
    public void save(PaidOrderEvent event) {
        writer.save(
                event.eventId(),
                event.orderId(),
                "OrderPaid",
                event.payloadJson());
    }
}

public record PaidOrderEvent(
        String eventId, String orderId, String payloadJson) {
}
~~~

`PaidOrderEvent` is a DTO produced by a transformer/validator **before** the service activator. `OrderEventCqlWriter` uses the blocking CQL API from section 6.

If the input channel is a `DirectChannel` and the method executes synchronously, exceptions from `CqlTemplate` **can propagate back** to the caller/inbound listener. If the JMS listener uses a transacted session and no error flow swallows the exception, the broker can redeliver the message after rollback.

### 11.2. Equivalent Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow savePaidOrdersFlow(
        OrderEventCqlWriter writer) {

    return IntegrationFlow.from("paidEventsForCassandra")
            .handle(PaidOrderEvent.class, (event, headers) -> {
                writer.save(
                        event.eventId(),
                        event.orderId(),
                        "OrderPaid",
                        event.payloadJson());
                return null;
            })
            .get();
}
~~~

This is an **alternative** to the `@ServiceActivator` in section 11.1 on the same input channel. Do not register both just to persist one event: with two consumers, dispatch semantics may differ from expectations.

### 11.3. Transforming JSON from JMS

If a JMS inbound adapter receives a `TextMessage` and the Spring payload is a JSON `String`, transform it first:

~~~java
// Java DSL fragment; objectMapper is already injected.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, PaidOrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("Invalid PaidOrderEvent JSON", ex);
    }
})
.channel("paidEventsForCassandra")
~~~

Do not expect `CqlTemplate` to parse JSON into columns automatically; it is a CQL execution template. Beyond JSON syntax, validate business fields, `schemaVersion`, `eventId`, and authorization before writing to the database.

### 11.4. When not to use blocking CqlTemplate in a flow

If upstream is a WebFlux event loop, a `FluxMessageChannel`, or an end-to-end reactive pipeline, blocking `CqlTemplate` can occupy event-loop threads and hurt throughput. In that case use `ReactiveCqlTemplate` or `ReactiveCassandraOperations` and ensure publishers are properly subscribed.

Offloading blocking work onto a dedicated scheduler is an option, yet it **does not automatically guarantee** a JMS/Kafka source only acks after Cassandra finishes. Design explicit acknowledgment boundaries, error paths, and durable handoffs.

## 12. Exception translation and error classification

One reason to choose Spring Data `CqlTemplate` over raw driver calls everywhere is **exception translation**: Cassandra driver errors are translated into the `org.springframework.dao.DataAccessException` hierarchy whenever possible. This lets services define retry/alert policies by error category without coupling every handler to driver-specific exception classes.

~~~mermaid
flowchart TD
    A["CqlTemplate.execute/query"] --> B["Cassandra driver request"]
    B --> C{"Outcome?"}
    C -->|"Success"| D["ResultSet / mapped row / applied"]
    C -->|"Failure"| E["DriverException or runtime exception"]
    E --> F["PersistenceExceptionTranslator"]
    F --> G["Spring DataAccessException"]
    G --> H{"Transient or permanent?"}
    H -->|"Recoverable"| I["Bounded retry + backoff"]
    H -->|"Bad config/contract"| J["Fail fast + alert/quarantine"]
~~~

Across Spring Data versions, `PersistenceExceptionTranslator` details may be provided via templates, factories/configuration, or converter infrastructure. **Do not write logic depending on a specific exception subclass without verifying it on your version**. Distinguish:

| Error group | Examples | Strategy |
|---|---|---|
| Transient connection/network | Node temporarily unreachable, connection reset | Bounded retry when the operation is idempotent |
| Unavailable/overload | Insufficient replicas for CL, request backlog | Backoff, reduce concurrency, alert |
| Timeout with uncertain outcome | Client misses reply before deadline | Retry **with idempotency**; do not infer Cassandra did not write |
| Invalid CQL/schema | Wrong table/keyspace name, invalid syntax | Fix migration/config; retrying unchanged usually fails |
| Codec/type mismatch | Binding `String` to an incompatible CQL column | Fix contract/mapper |
| Authentication/authorization | Bad credentials or missing permissions | Fix secrets/ACLs; do not hot-retry |
| Too many results | Wrong-partition query, large page size | Fix data model/query; avoid unbounded scans |

### 12.1. Imperative try/catch

~~~java
import org.springframework.dao.DataAccessException;

public void persistSafely(PaidOrderEvent event) {
    try {
        writer.save(
                event.eventId(), event.orderId(),
                "OrderPaid", event.payloadJson());
    } catch (DataAccessException ex) {
        // Log exception class + sanitized eventId;
        // DO NOT log the entire sensitive payload.
        throw ex; // Preserve exception propagation if the source needs rollback.
    }
}
~~~

This fragment illustrates a service with an injected `writer` field. Do not catch every `DataAccessException` and swallow it: with a transacted listener, doing so can cause the source message to **ack/commit even though Cassandra failed to persist**. Complete normally only when the domain deliberately records and handles a rejection/quarantine safely.

### 12.2. Reactive exception signal

With `ReactiveCqlTemplate`, CQL errors may surface **only when the publisher is subscribed**:

~~~java
return reactiveCqlTemplate
        .execute(
            "INSERT INTO order_event "
            + "(event_id, order_id, event_type, payload_json) "
            + "VALUES (?, ?, ?, ?)",
            eventId, orderId, eventType, json)
        .doOnError(ex -> log.warn(
                "Cassandra operation failed for eventId={}", eventId, ex));
~~~

This is a service fragment assuming `reactiveCqlTemplate` and `log`, not a complete method. Logging inside `doOnError` **does not make the publisher succeed**; the error still propagates unless downstream applies `onErrorResume(...)` or a similar operator. For JMS/Kafka sources, ensure whichever component handles acknowledgment is notified of actual completion/error.

### 12.3. Exceptions do not replace cluster monitoring

A small rate of timeouts can be masked by retries while p99 latency, pending requests, and cluster load keep climbing. Monitor both application metrics and Cassandra/driver metrics; do not wait for a system-wide outage to discover a hot partition.

## 13. Consistency, timeouts, pagination, and CqlSession configuration

`CqlSession` dispatches queries to the cluster; Spring Data templates can apply statement defaults. Cassandra uses replication and consistency levels rather than providing a general-purpose SQL transaction across operations.

### 13.1. Consistency levels

| Consistency | Example meaning | Limitation |
|---|---|---|
| `ONE` | One replica response satisfies CL | Does not guarantee all replicas have seen the write yet |
| `LOCAL_QUORUM` | Quorum within the local DC | Depends on actual replication factor and placement |
| `ALL` | Requires every involved replica | Availability drops if any replica fails |
| `LOCAL_ONE` | One local replica | Fits some latency-focused workloads; must weigh read/write CL |

With replication factor 3 in a single datacenter, local quorum is typically 2. With multi-DC topologies and different replication factors, that number cannot be assumed universally. Consistency level does not solve **event v2 arriving before v1** or **two operations on the same key having different timestamps**; use versioning or conditional writes when required by business rules.

### 13.2. Configuring statements rather than mutating CqlTemplate at runtime

`CqlTemplate` exposes defaults such as consistency and page size via `CassandraAccessor`. The driver also provides **execution profiles**, request timeouts, retry policies, and connection settings. Configure these statically per application/operation class rather than mutating a shared singleton template from message headers.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Bean("readCqlTemplate")
public CqlTemplate readCqlTemplate(SessionFactory factory) {
    CqlTemplate template = new CqlTemplate(factory);
    template.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
    template.setPageSize(100);
    return template;
}
~~~

`setConsistencyLevel`/`setPageSize` belong to the Spring Data Cassandra API, though you should verify signatures against your library version. For example, `LOCAL_QUORUM` only fits topologies that support it; in a single-node/RF=1 lab, validate suitability before adopting production settings.

**Do not mutate global template settings per request:** a singleton template can be shared across threads; for per-operation consistency/timeouts, use statements, driver execution profiles, or dedicated statically configured template/DAO beans.

### 13.3. A timeout does not prove the write failed

~~~text
Client sends INSERT evt-3001
  -> Coordinator receives request
  -> Replicas write data
  -> Response is lost on the network
  -> Client sees timeout
  -> Caller retries with same eventId
~~~

If the event upsert is immutable and shares the same primary key, retrying is far safer than retrying a counter increment. For conditional `IF NOT EXISTS` writes, inspect the applied result and existing row. Never blindly retry every `CqlTemplate` operation indefinitely without evaluating idempotency.

### 13.4. Pagination and Cassandra data modeling

When querying multiple rows within a partition:

- Design partition and clustering keys around the exact business queries.
- Use page sizes and continuation/paging states where supported instead of loading everything into memory.
- Bound partition sizes; avoid unpredicated `SELECT *` on large tables.
- Measure p95/p99, rows read, tombstones, and coordinator pressure.
- With reactive `Flux<T>`, manage subscription/backpressure and in-flight query counts rather than assuming `collectList()` is safe.

Sharing connections in `CqlSession` does not mean the Cassandra cluster can absorb unlimited concurrent queries; session reuse and backpressure are separate responsibilities.

## 14. Transaction boundaries with JMS, HTTP, and Kafka

When a Service Activator invokes blocking `CqlTemplate` in a JMS flow, at least two separate resources are involved: the **JMS session** and the **Cassandra operation**.

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Listener as JMS inbound adapter
    participant CQL as Service Activator + CqlTemplate
    participant DB as Cassandra
    Broker->>Listener: Deliver evt-3001
    Listener->>CQL: Spring Message via DirectChannel
    CQL->>DB: INSERT evt-3001
    DB-->>CQL: Write complete per CL
    CQL-->>Listener: Handler completes
    Listener-->>Broker: JMS commit
    Note over Broker,DB: Cassandra write and JMS commit are not atomic
~~~

If Cassandra writes successfully but the JVM crashes **before JMS commits**, the broker can redeliver the message. If Cassandra fails and the exception propagates back over `DirectChannel` to a transacted listener, JMS can roll back and redeliver; however, Cassandra might still have partially or completely applied the write before the exception surfaced.

| Sequence | Risk | Safeguard |
|---|---|---|
| Cassandra write succeeds → JVM crash → JMS uncommitted | Duplicate redelivery | Stable `eventId` primary key, idempotent write |
| JMS commits before async Cassandra completion | Cassandra fails yet broker will not redeliver | Avoid early ack; durable handoff or independent retry |
| Kafka offset commits before Cassandra write | Event not replayed after DB failure | Choose appropriate offset/ack boundary |
| HTTP response returns success before DB completion | Caller believes data is saved | Await completion or return accepted + job tracking |
| Cassandra times out after server actually wrote | Retry causes duplicate side effect | Upsert immutable event or conditional write |

### 14.1. DirectChannel vs ExecutorChannel

~~~text
DirectChannel + blocking CqlTemplate:
  JMS receive -> service activator -> Cassandra write -> return/throw
  -> listener can commit/rollback based on the exception

ExecutorChannel or reactive async:
  JMS receive -> enqueue/dispatch -> listener may commit
                                  -> DB write later fails on another thread
                                  -> cannot roll back the original JMS message
~~~

An in-memory `ExecutorChannel` or `QueueChannel` decouples threads but is **not a durable queue**. If zero event loss is required, persist work in a durable store, inbox/outbox, or use integration-tested end-to-end ack control.

### 14.2. Retries, idempotency, and applied results

`CqlTemplate.execute(...)` does not make a request business-idempotent. For example:

- `INSERT` with the same `eventId` and immutable content: typically safe on redelivery.
- `UPDATE counter = counter + 1` or cumulative updates: **unsafe under blind retries**.
- `INSERT ... IF NOT EXISTS`: a lightweight transaction distinguishing whether a row already existed, requiring checking the applied result and accepting coordination overhead.

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, payload_json
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

In code using `CqlTemplate`, execute the parameterized statement and inspect the boolean outcome of the *conditional* operation:

~~~java
boolean applied = cql.execute(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?) IF NOT EXISTS",
        eventId, orderId, eventType, json);

if (!applied) {
    // Row with the same eventId already exists; inspect content if needed.
}
~~~

With CQL LWT, `applied=false` indicates the condition was not met; **do not automatically conclude it is a benign duplicate**. If the existing row holds a different payload, record a conflict or quarantine for investigation.

## 15. Session lifecycle, security, and cluster operations

### 15.1. Long-lived sessions with recoverable connections

`CqlSession` manages connections across nodes. When one node temporarily fails, the driver can reroute to another coordinator or reconnect per policy. This does **not mean** every in-flight request automatically succeeds or callers never need retries.

**Deployment rules:**

1. Open the session at startup or when the Spring container builds the bean; reuse it across operations.
2. Never call `session.close()` inside a DAO, `RowMapper`, or service activator after each message.
3. Ensure the owner closes the session on application shutdown, draining in-flight work if needed.
4. Never use `USE keyspace` to switch the shared session context per request.
5. Do not manually create pools of hundreds of `CqlSession` beans to "speed things up" without measuring driver/cluster metrics.
6. Never arbitrarily close a `DefaultBridgedReactiveSession` if it shares the underlying driver session with other beans.

### 15.2. Secrets and access permissions

In production, `CqlSession` requires authentication/TLS as dictated by the cluster. Credentials must come from managed secrets/environment configuration, never hard-coded in Java or logged.

Assign a Cassandra role with least privilege on the required keyspaces/tables. A read-only diagnostics service must not hold `DROP TABLE`, `TRUNCATE`, or schema-modification privileges.

Never construct keyspace/table names directly from a `tenantId` header without validation; prepared statements bind **values**, not CQL identifiers if you concatenate table/column names from input. For multi-tenancy, use allowlists and service-identity authorization.

### 15.3. Observability per layer

| Layer | Metrics/logs to track | Meaning |
|---|---|---|
| Spring Integration | Message rate, handler duration, error channel | Is the flow receiving the expected workload? |
| CqlTemplate/DAO | Operation type, latency, exception type | Which queries are failing or slow? |
| Driver `CqlSession` | In-flight requests, timeouts, connections, retry count | Is there saturation or reconnect churn? |
| Cassandra cluster | Read/write latency, compaction, tombstones, pending tasks | Is the backend overloaded or hitting hot partitions? |
| Source JMS/Kafka | Queue depth, oldest message age, offset lag | Are Cassandra failures building up a backlog? |
| Business | Duplicate `eventId`, conflicting payloads, `applied=false` | Is replay preserving correctness? |

`CqlTemplate` can log CQL at DEBUG level via its logger. **Do not enable verbose CQL logging in production without protecting sensitive data**: statements and bind values can contain PII, tokens, or financial details. Use tracing/metrics with bounded-cardinality labels; never use per-event `eventId` as a metric label if cardinality explosion is a risk.

### 15.4. Schema operations

Create keyspaces and tables intentionally through migrations/provisioning rather than letting every app instance auto-DROP/CREATE at startup. With manual Spring Data config, set `SchemaAction.NONE` when migrations manage the schema. When evolving tables/mappings, roll out compatible changes across producers, consumers, and the database in order—never rename CQL columns on half your services expecting `RowMapper` to adapt automatically.

## 16. Quick troubleshooting table

| Symptom | Possible cause | Check/fix |
|---|---|---|
| `No bean of type CqlSession` | Driver not configured / Boot auto-config disabled | Dependencies, properties, bean definitions |
| `No bean of type SessionFactory` | `CqlSession` exists without wrapper for `CqlTemplate` | Define `DefaultSessionFactory` or `SessionFactoryFactoryBean` |
| Duplicate `SessionFactory` bean | Both default and mapping factory defined without qualifier | Pick one or use `@Qualifier` |
| Connection fails on local DC | `datacenter1` differs from cluster metadata | Check `local-datacenter`, `contact-points`, port |
| Keyspace does not exist | Bean initializes before schema provisioning | Run migrations/provisioning before startup |
| Query reports invalid table | Wrong keyspace or table name | Verify `SELECT` with qualified table name |
| `CqlTemplate` fails to compile in `CassandraMessageHandler` | Handler requires `ReactiveCassandraOperations` | Use reactive template/operations or write a Service Activator |
| CQL INSERT succeeds yet data changes on retry | Cassandra upserted same primary key | Keep payloads immutable; use versioning/LWT if needed |
| `queryForObject` fails on size | Query returned zero or multiple rows | Use `query` + `RowMapper` or refine query/key |
| Codec error | Java value incompatible with CQL column type | Check schema and driver codecs |
| Blocking in WebFlux | `CqlTemplate` running on event loop | Use `ReactiveCqlTemplate` and reactive flow |
| Reactive `Mono` created yet no data written | Missing subscription | Return publisher to framework or attach managed subscriber |
| Timeout yet row exists | Uncertain outcome after network glitch | Idempotent retry, inspect state |
| JMS does not redeliver on Cassandra error | Listener already acked or async boundary | Inspect `DirectChannel`/transaction/error flow |
| DLQ grows even after Cassandra recovers | Poison messages or invalid contracts | Classify and perform controlled replay |
| Throughput drops after raising concurrency | Too many in-flight queries, hot partition | Throttle load, measure p95, review partition design |
| Slow startup or too many connections | Creating a session per call/bean | Reuse a singleton session |
| CQL logs expose data | Overly broad DEBUG logging | Restrict logs, mask data, lock down access |

### Pre-production checklist

1. Decide whether the app uses Spring Boot auto-config or Java-created sessions, with no accidental duplicate beans.
2. Verify keyspace, contact points, local DC, replication, auth/TLS, and Cassandra role permissions.
3. Choose imperative `CqlTemplate` vs `ReactiveCqlTemplate`/`ReactiveCassandraTemplate` to match the execution model.
4. Use bind parameters for all values sourced from payloads/headers; never assemble user CQL strings.
5. Verify queries against partition keys, page sizes, consistency levels, and retry/timeout policies.
6. Separate transient errors from invalid schema/permission/codec errors.
7. Maintain a stable business `eventId`, duplicate/conflict payload checks, and ordering where required.
8. Verify exception/ack paths from Spring Integration back to JMS/Kafka/HTTP sources.
9. Track metrics for in-flight requests, p99, cluster load, source backlog, and replay audits.
10. Test restarts, broker failures, Cassandra outages, and graceful shutdown while work is active.

## 17. Hands-on lab: building CqlTemplate and session factory

**Environment:** a dedicated lab Cassandra cluster/test container, Java 17+, Spring Data Cassandra, and Spring Integration 6+ (or compatible versions). Use the `shop_integration` keyspace and `order_event` table from section 5. Never run destructive operations against production.

### Exercise A — One CqlSession, one DefaultSessionFactory

1. Create the driver `CqlSession` via Spring Boot auto-config or the Java bean from section 3.
2. Create `DefaultSessionFactory(cqlSession)` and `CqlTemplate(sessionFactory)` as in section 4.
3. Log the **identity** of the session injected into two lab services to confirm the same instance is reused.
4. Run a SELECT and an INSERT; verify the session remains usable afterward.
5. Stop the Spring context and verify the driver session closes cleanly per lifecycle.

**PASS:** No session creation/closing per message; no ambiguous duplicate `SessionFactory` beans.

### Exercise B — CqlSessionFactoryBean instead of a driver @Bean

1. Disable direct driver configuration and replace it with `CqlSessionFactoryBean`.
2. Inject bean type `CqlSession` into `CqlTemplate`/`DefaultSessionFactory`, **without calling `getObject()` manually**.
3. Inspect the factory bean name and the `&beanName` mechanism in the Spring context.
4. Intentionally misconfigure `local-datacenter` in the test environment and observe startup/connect failure.
5. Fix it and verify the keyspace exists and the session can SELECT/INSERT.

**PASS:** Clear understanding of how `FactoryBean<CqlSession>` differs from `SessionFactory`.

### Exercise C — Prepared statements and RowMapper

1. Call `writer.save("evt-3001", "ORD-3001", "OrderPaid", json)`.
2. Query the `event_type` column by `eventId` using `CqlTemplate.queryForObject(...)`.
3. Query using `OrderEventCqlReader.findById(...)`, returning a DTO or `Optional.empty()` when absent.
4. Use a test string containing quotes in the payload and verify it is bound as data rather than parsed as CQL syntax.
5. Pass mismatched types for `eventId`/`processed_at` to observe exception translation/codec errors.

~~~sql
SELECT event_id, order_id, event_type, payload_json
FROM shop_integration.order_event
WHERE event_id = 'evt-3001';
~~~

**PASS:** SELECT returns expected data; field mappings are explicit; queries never concatenate client data into CQL.

### Exercise D — ReactiveCqlTemplate and subscription

1. Define a `ReactiveCqlTemplate(new DefaultBridgedReactiveSession(cqlSession))` bean.
2. Call `reactiveDao.save(...)` **without subscribing**; confirm lazy execution and do not rely solely on the method return value.
3. Have a subscriber/framework consume the `Mono<Boolean>` and verify data is written.
4. Test a SELECT returning `Mono<String>`; handle empty/result/error cases properly.
5. Disconnect Cassandra mid-operation and observe the error signal and retry budget.

**PASS:** No operations silently dropped due to missing subscription; async errors are not swallowed.

### Exercise E — Spring Integration wiring

1. Create `OrderEventCqlWriter` and `SavePaidOrderService` with `@ServiceActivator(inputChannel="paidEventsForCassandra")`.
2. Send a Spring Message containing `PaidOrderEvent` to `DirectChannel`; verify the Cassandra row.
3. Swap in the Java DSL from section 11.2, **without running both endpoints concurrently** on the same channel.
4. Stop Cassandra and observe the exception propagating over `DirectChannel`.
5. Insert an `ExecutorChannel` before the handler and compare when exceptions surface.
6. Contrast with `CassandraMessageHandler` using `ReactiveCassandraOperations`; do not pass `CqlTemplate` into the built-in handler constructor.

**PASS:** Understand how an imperative service activator flow differs from the built-in reactive Cassandra endpoint and where errors travel.

### Exercise F — Redelivery, timeouts, and idempotency

1. Send `evt-3001` from transacted JMS to a handler backed by blocking `CqlTemplate`.
2. After the Cassandra write succeeds, simulate an error before JMS commit; let the broker redeliver the same event.
3. Confirm the same `eventId` key does not create a duplicate independent event; detect payload changes if the same ID arrives with conflicting content.
4. Test conditional CQL `IF NOT EXISTS`, comparing `applied=true`/`false` against existing rows.
5. Configure sensible timeouts and backoff; simulate Cassandra unavailability followed by recovery and measure attempts.
6. Observe that switching to an async channel prevents Cassandra errors from automatically rolling back the source JMS message after commit.

**PASS:** Accurately defines ack/commit boundaries and never treats a timeout as proof of "not written".

### Final verification matrix

| Case | Required outcome |
|---|---|
| Singleton `CqlSession` | One session reused and closed cleanly at shutdown |
| `SessionFactory` | `DefaultSessionFactory` returns the driver session |
| `CqlSessionFactoryBean` | FactoryBean produces `CqlSession`, not confused with `SessionFactory` |
| `CqlTemplate` | Runs blocking CQL with bound values |
| `RowMapper` | Maps rows with accurate types/columns |
| `ReactiveCqlTemplate` | `Mono`/`Flux` subscribed and errors observed |
| `CassandraMessageHandler` | Accepts `ReactiveCassandraOperations`, not `CqlTemplate` |
| Exception translation | CQL failures become clear application error paths |
| Consistency and timeouts | Neither successful reply nor timeout implies exactly-once |
| Idempotency | Same event ID across replay causes no wrong business side effects |
| Security and lifecycle | No leaked credentials; no per-request session closing |

**Session lifecycle, Cassandra consistency, timeouts, prepared statement behavior, and reconnects cannot be verified by mocking `CqlTemplate` alone.** Use a real Cassandra instance or test container; JMS acknowledgment additionally requires a test JMS broker to observe redelivery/rollback.

## 18. Self-assessment questions

1. Why is `CqlTemplate` not a Spring Integration outbound adapter?
2. How does `CqlSession` differ from `SessionFactory`?
3. What type of object does `CqlSessionFactoryBean` produce, and what is `&beanName` used for?
4. Does `DefaultSessionFactory` create its own separate pool of Cassandra connections?
5. When is `SessionFactoryFactoryBean` more useful than `DefaultSessionFactory`?
6. Why should `CqlSession.close()` not be called after every INSERT?
7. How do `CqlTemplate` and `CassandraTemplate` differ in object mapping?
8. How does `CqlTemplate.execute(String, Object...)` protect bound values?
9. Why is concatenating `eventId` into CQL strings discouraged?
10. How do `RowMapper` and `ResultSetExtractor` serve two different result-processing patterns?
11. Why is `queryForObject` unsuitable for fetching an entire large partition?
12. What does `ReactiveCqlTemplate` require for a `Mono` to actually perform I/O?
13. When should `Mono.block()` be avoided?
14. How do `ReactiveCqlTemplate` and `ReactiveCassandraTemplate` differ regarding object mapping?
15. Why does `CassandraMessageHandler` require `ReactiveCassandraOperations` instead of `CqlTemplate`?
16. Does a Cassandra timeout prove an INSERT failed completely?
17. How does a Cassandra upsert on `event_id` differ from an RDBMS unique insert?
18. What does `IF NOT EXISTS` solve, and what cost does it carry?
19. Why do `DirectChannel` and `ExecutorChannel` create different JMS→Cassandra error paths?
20. With multiple keyspaces/tenants, why is switching a shared session's keyspace with `USE` per request unsafe?

## 19. Official references

- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`, callbacks, `SessionFactory`, and exception translation.
- [Spring Data Cassandra — Connecting to Cassandra with Spring](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html): Java/XML configuration, `CqlSessionFactoryBean`, `SessionFactoryFactoryBean`, and `AbstractCassandraConfiguration`.
- [Spring Data Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): binders, caching, and `PreparedStatementCreator`.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCqlTemplate`, `ReactiveCassandraTemplate`, subscriptions, and error signals.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/CqlTemplate.html): constructors, `execute`, `queryForObject`, `query`, and callbacks.
- [Spring Data Cassandra API — DefaultSessionFactory](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/session/DefaultSessionFactory.html): shared `CqlSession` wrapper.
- [Spring Data Cassandra API — CqlSessionFactoryBean](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/config/CqlSessionFactoryBean.html): Spring `FactoryBean` lifecycle creating the driver session.
- [Spring Data Cassandra API — ReactiveCqlTemplate](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/ReactiveCqlTemplate.html): `Mono`/`Flux` and reactive operations.
- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound adapter/gateway, and the `ReactiveCassandraOperations` requirement.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, replication, consistency, data modeling, LWT, and cluster operations.

**Key takeaway:** `CqlSessionFactoryBean` creates the driver `CqlSession`; `SessionFactory` supplies that session to Spring Data; `CqlTemplate` uses it to execute **blocking CQL** with callbacks, prepared statements, and exception translation. When reactive execution is needed, use `ReactiveCqlTemplate` or object-mapped `ReactiveCassandraTemplate`; meanwhile, Spring Integration `CassandraMessageHandler` accepts **`ReactiveCassandraOperations`**, not `CqlTemplate`. Reliable flows require a proper session lifecycle, partition-key queries, bound values, controlled timeouts/retries/idempotency, and clear acknowledgment boundaries with upstream systems.




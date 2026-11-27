# Data Mapping and Querying with Spring Data Spanner

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to access data, storage, messaging, and identity. On Google Cloud, **Cloud Spanner** is a horizontally scalable distributed relational database supporting SQL, ACID transactions, and strong consistency. Spring Data Spanner provides a way to map Java POJOs to table rows, build repositories, and execute queries in Spring Data style.

This lesson uses an order business domain to practice:

1. Configuring the Spring Boot Starter and ADC to connect to Spanner.
2. Designing tables, single/composite primary keys, and parent-child relationships.
3. Mapping entities using `@Table`, `@Column`, `@PrimaryKey`, `@Interleaved`, and `@NotMapped`.
4. Building a `SpannerRepository` with CRUD and query methods.
5. Writing parameterized SQL with `@Query` and `SpannerTemplate`.
6. Choosing between repositories, templates, DML, and read/write transactions.
7. Designing indexes, schema evolution, and testing with the Spanner Emulator.
8. Distinguishing the Spanner session pool from HikariCP in JDBC.

> **Important scope:** Spring Data Spanner uses the GoogleSQL interface of Cloud Spanner. Spanner's PostgreSQL interface does not support Spring Data Spanner; if the application uses the PostgreSQL interface, choose Spring Data JPA and configure the corresponding dialect/driver. Do not treat Spring Data Spanner as JPA/Hibernate with identical semantics and features.

## 1. Cloud Spanner and Spring Data Spanner

### 1.1. How Does Cloud Spanner Store Data?

Cloud Spanner organizes data into databases, tables, rows, and columns. Every table has a primary key that uniquely identifies a row. The primary key also determines logical ordering and how Spanner distributes key ranges across servers.

Spanner fits systems requiring relational data, consistent transactions, and horizontal scalability. However, key and index design directly affects read/write distribution. A schema suitable for a single-machine database can create hotspots when running on a distributed system.

### 1.2. Where Does Spring Data Spanner Fit?

~~~mermaid
flowchart TD
    API["Spring Boot service"] --> REPO["SpannerRepository"]
    API --> TEMPLATE["SpannerTemplate / SpannerOperations"]
    REPO --> MAP["Mapping context + converters"]
    TEMPLATE --> MAP
    MAP --> CLIENT["Cloud Spanner Java client"]
    CLIENT --> SESSIONS["gRPC session pool"]
    SESSIONS --> DB["Cloud Spanner database"]
~~~

| Component | Role |
| --- | --- |
| Entity POJO | Describes a row in a Spanner table |
| Mapping annotations | Maps Java properties, columns, primary keys, and interleaved rows |
| `SpannerRepository` | CRUD and query methods implemented by Spring Data |
| `SpannerTemplate` | API for reads, writes, SQL queries, DML, and transactions |
| `SpannerDatabaseAdminTemplate` | Supports database/schema administrative operations |
| Cloud Spanner Java client | Communicates via API/gRPC with Spanner |
| Session pool | Reuses Spanner sessions for database operations |

The starter auto-configures common beans such as `SpannerTemplate`, `SpannerDatabaseAdminTemplate`, and discovered repositories in the package. When lower-level operations are needed, you can use `DatabaseClient` from the Google Cloud Java client.

### 1.3. Distinguishing GoogleSQL and the PostgreSQL Interface

Cloud Spanner supports the GoogleSQL dialect and the PostgreSQL interface. The two interfaces have different SQL syntax, data types, and driver ecosystems.

- Spring Data Spanner uses mapping and APIs specific to the GoogleSQL interface.
- The PostgreSQL interface is incompatible with Spring Data Spanner.
- If the PostgreSQL protocol is required, evaluate Spring Data JPA or the corresponding JDBC driver.
- Do not mix Spring Data Spanner annotations with JPA entities and expect the same repository to pick a dialect automatically.

This lesson uses GoogleSQL.

## 2. Adding Dependencies and Configuring Spring Boot

### 2.1. Maven Dependencies

Use the Spring Cloud GCP BOM to manage compatible module versions. Do not pick starter versions independently of Spring Boot and the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-spanner</artifactId>
    </dependency>
</dependencies>
~~~

`${spring-cloud-gcp.version}` is the BOM version chosen by the project. Check the compatibility matrix across Spring Boot, Spring Framework on Google Cloud, and the Java version before locking the BOM. The starter brings in the Cloud Spanner Java client; you usually do not need to declare the client library separately.

### 2.2. Configuring Project, Instance, and Database

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      spanner:
        project-id: rental-platform-dev
        instance-id: orders-spanner
        database: orders
~~~

Key properties:

| Property | Meaning |
| --- | --- |
| `spring.cloud.gcp.spanner.project-id` | Project containing Spanner; can override the general project ID |
| `spring.cloud.gcp.spanner.instance-id` | ID of the Spanner instance |
| `spring.cloud.gcp.spanner.database` | Default database |
| `spring.cloud.gcp.spanner.enabled` | Enables/disables Spanner autoconfiguration |
| `spring.cloud.gcp.spanner.emulator.enabled` | Uses the Spanner Emulator in dev/test environments |
| `spring.cloud.gcp.spanner.emulator-host` | Emulator host/port, commonly `localhost:9010` by default |

Project ID, instance ID, and database name must match actual resources. Instance ID is distinct from project ID and database name.

### 2.3. ADC and Service Accounts

Spring Data Spanner uses Google Cloud credentials from Application Default Credentials (ADC). For local development, you can use credentials generated by the Google Cloud CLI. For production, prefer a service account attached directly to Cloud Run, GKE Workload Identity Federation, or Compute Engine.

Common IAM roles:

- `roles/spanner.databaseUser`: read/write data, run SQL, and perform database operations permitted by the role.
- `roles/spanner.databaseReader`: read-only data access and read queries.
- `roles/spanner.databaseAdmin`: intended for database/schema administration tasks.

`roles/spanner.databaseUser` may include schema update permissions; if the runtime needs a narrower scope, consider fine-grained access control or a custom role. Separate the runtime service account from the principal running schema migrations. Do not assign project-wide `roles/spanner.admin` just so an application can read/write data.

### 2.4. IAM Permissions vs. Application-Layer Permissions

IAM determines which workloads can access Spanner resources. Spring Security or business authorization inside the application determines which orders an end user can view or modify.

For example, a service account may be allowed to read the entire database, yet the API must still verify the logged-in user's `customerId` before returning orders. Do not use IAM database roles to replace per-tenant or per-user authorization.

## 3. Designing the Schema Before Creating Entities

### 3.1. Order Model Example

An order has multiple order items. We use two tables:

~~~sql
CREATE TABLE Orders (
    OrderId STRING(36) NOT NULL,
    CustomerId STRING(36) NOT NULL,
    Status STRING(20) NOT NULL,
    CreatedAt TIMESTAMP NOT NULL
) PRIMARY KEY (OrderId);

CREATE TABLE OrderItems (
    OrderId STRING(36) NOT NULL,
    ItemId STRING(36) NOT NULL,
    ProductId STRING(36) NOT NULL,
    Quantity INT64 NOT NULL,
    UnitPrice NUMERIC NOT NULL
) PRIMARY KEY (OrderId, ItemId),
  INTERLEAVE IN PARENT Orders ON DELETE CASCADE;

CREATE INDEX OrdersByCustomerCreatedAt
ON Orders(CustomerId, CreatedAt DESC);
~~~

In this design:

- `Orders` is the parent table.
- `OrderItems` is a child table interleaved in `Orders`.
- The primary key of `OrderItems` begins with the full primary key of the parent table in the exact same order, followed by its own key `ItemId`.
- Index `OrdersByCustomerCreatedAt` supports queries by customer and creation time.

Interleaving stores child rows physically close to their parent row in Spanner. This is a good choice when the child's lifecycle and queries are tightly coupled to the parent. If the relationship is loosely coupled or children need broad independent access, consider foreign keys or standalone table modeling.

### 3.2. Choosing Primary Keys to Avoid Hotspots

Spanner distributes data by key ranges. If a workload continuously writes monotonically increasing keys—such as a timestamp or an auto-incrementing number as the leading key—new writes can pile onto one range and create a hotspot.

Design approaches:

- Random UUID v4 for independent keys with good write distribution.
- Use a stable natural key if it fits access patterns and does not skew distribution.
- Reverse column order in a composite key to avoid a monotonic value in the leading position.
- Use bit-reversed sequences or shard prefixes when numeric keys are required.
- Order keys based on read/write patterns, not merely entity convenience.

Do not default to `AUTO_INCREMENT` or a timestamp as the leading primary key column for high-write tables. UUID v1 places time components in the high bits and lacks the distribution properties of UUID v4.

### 3.3. Composite Primary Keys

Composite keys are ordered. For example:

~~~sql
PRIMARY KEY (OrderId, ItemId)
~~~

Unlike two independent columns, key order determines sort order and key ranges. When declaring the entity, `keyOrder = 1` must correspond to `OrderId`, and `keyOrder = 2` to `ItemId`.

For interleaved children, the parent's primary key columns must come first in the same order. You cannot arbitrarily reorder annotations without changing the corresponding schema.

### 3.4. Indexes Aligned with Query Patterns

Spanner does not automatically create secondary indexes just because an entity has properties. List the main queries before creating indexes:

| Query pattern | Suggested design |
| --- | --- |
| Fetch order by ID | Primary key `OrderId` |
| Fetch customer's orders, newest first | Index `CustomerId, CreatedAt DESC` |
| Fetch items in an order | Composite key `OrderId, ItemId` |
| Fetch orders by status and time | Consider an index starting with `Status` then `CreatedAt` if actually needed by the workload |

Every index increases write and storage costs. Avoid indexing every column. Verify query plans and metrics before adding indexes to production.

## 4. Mapping Entities with Annotations

### 4.1. Parent Table Entity

Spring Data Spanner maps POJOs to tables. Annotations belong to the `com.google.cloud.spring.data.spanner.core.mapping` package:

~~~java
import com.google.cloud.Timestamp;
import com.google.cloud.spring.data.spanner.core.mapping.Column;
import com.google.cloud.spring.data.spanner.core.mapping.Interleaved;
import com.google.cloud.spring.data.spanner.core.mapping.NotMapped;
import com.google.cloud.spring.data.spanner.core.mapping.PrimaryKey;
import com.google.cloud.spring.data.spanner.core.mapping.Table;

import java.util.ArrayList;
import java.util.List;

@Table(name = "Orders")
public class Order {

    @PrimaryKey
    @Column(name = "OrderId")
    private String orderId;

    @Column(name = "CustomerId")
    private String customerId;

    @Column(name = "Status")
    private String status;

    @Column(name = "CreatedAt")
    private Timestamp createdAt;

    @Interleaved
    private List<OrderItem> items = new ArrayList<>();

    @NotMapped
    private String displayLabel;

    public Order() {
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Timestamp getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Timestamp createdAt) {
        this.createdAt = createdAt;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }
}
~~~

`@Table` specifies the table name. `@PrimaryKey` is required even when a table has only one key column. `@Column` maps a property to a specific column name. `@Interleaved` declares a collection of interleaved child rows. `@NotMapped` marks a property used only in the application and not stored in Spanner.

### 4.2. Child Table Entity

~~~java
import com.google.cloud.spring.data.spanner.core.mapping.Column;
import com.google.cloud.spring.data.spanner.core.mapping.PrimaryKey;
import com.google.cloud.spring.data.spanner.core.mapping.Table;

import java.math.BigDecimal;

@Table(name = "OrderItems")
public class OrderItem {

    @PrimaryKey(keyOrder = 1)
    @Column(name = "OrderId")
    private String orderId;

    @PrimaryKey(keyOrder = 2)
    @Column(name = "ItemId")
    private String itemId;

    @Column(name = "ProductId")
    private String productId;

    @Column(name = "Quantity")
    private long quantity;

    @Column(name = "UnitPrice")
    private BigDecimal unitPrice;

    public OrderItem() {
    }

    // Constructors, getters and setters omitted for brevity.
}
~~~

The two properties `orderId` and `itemId` form the composite primary key. They must match the DDL order. `BigDecimal` is appropriate when exact decimal numbers are required; avoid using `double` for monetary prices.

### 4.3. Naming Strategy

Under the default naming strategy, camelCase Java properties can be mapped to PascalCase. For example, `customerId` can become `CustomerId`. If the schema uses different column names, explicitly declare `@Column(name = "...")`.

Do not rely on implicit rules when the schema has snake_case, legacy names, or special casing. Explicit mapping reduces bugs when renaming Java properties.

### 4.4. Primary Keys and Constructors

Spring Data Spanner supports POJOs with constructors. Constructor parameter names and types must match the persistent properties assigned by the constructor. For complex entities, constructors should not silently drop required fields.

Primary keys should be treated as immutable after row creation. Changing a key value on an object and calling update does not change the old key in place; the operation may apply to the row with the new key. If an identifier must change, design a controlled workflow to create the new row, migrate references, and delete the old row.

### 4.5. Embedded and Custom Converters

`@Embedded` allows properties of a nested object to be stored as columns in the same row; this is useful for reusing groups of fields such as addresses or contact information. If an embedded field participates in the primary key, the corresponding key components must be marked with `@PrimaryKey`.

When a Java type lacks an appropriate default conversion, you can register custom read/write converters. Converters must be symmetric and deterministic: values written to Spanner must read back to the exact same type, including nulls, precision, and timezones.

## 5. Repositories with Spring Data Spanner

### 5.1. Declaring Repositories

~~~java
import com.google.cloud.spring.data.spanner.repository.SpannerRepository;
import com.google.cloud.spanner.Key;

import java.util.List;
import java.util.Optional;

public interface OrderRepository extends SpannerRepository<Order, String> {

    List<Order> findByCustomerId(String customerId);

    List<Order> findTop20ByCustomerIdOrderByCreatedAtDesc(String customerId);

    List<Order> findByCustomerIdAndStatusOrderByCreatedAtDesc(
            String customerId, String status);

    Optional<Order> findByCustomerIdAndOrderId(
            String customerId, String orderId);
}

public interface OrderItemRepository extends SpannerRepository<OrderItem, Key> {
}
~~~

The first generic parameter is the entity type, and the second is the ID type. For entities with a single String primary-key column, use `String`. For composite keys, the repository ID can use `Key` or an array/Iterable type matching the key components; check the requirements of the Spring Data Spanner version in use.

The Spring Boot starter enables repository scanning automatically with default settings. If you need to specify packages or customize behavior, use `@EnableSpannerRepositories`.

### 5.2. CRUD and Semantics of save

Repositories inherit CRUD methods:

~~~java
orderRepository.save(order);
orderRepository.findById(orderId);
orderRepository.findAll();
orderRepository.deleteById(orderId);
~~~

In Spring Data Spanner, `save` and `saveAll` have update-or-insert (upsert) semantics. If business logic requires the row not to exist beforehand, use an explicit insert at the template layer or enforce appropriate unique keys/conditions. Do not assume `save` is equivalent to a pure INSERT.

Collection results typically return an empty collection when no rows match. For a single result that may be absent, use `Optional<T>` to clearly express the not-found case.

### 5.3. Derived Query Methods

Spring Data generates implementations based on method names:

~~~java
List<Order> findByCustomerIdAndStatus(String customerId, String status);

int countByCustomerId(String customerId);

List<Order> findTop10ByStatusOrderByCreatedAtDesc(String status);

int deleteByCustomerIdAndStatus(String customerId, String status);
~~~

Common predicates include equality, greater/less than, null/not null, boolean, like, contains, and in/not in. Not every Spring Data JPA keyword is supported identically. Check the reference documentation when using complex operators or special property expressions.

Long method names are a signal to consider custom SQL. Prefer derived method names for simple, readable queries; use `@Query` when you need explicit control over SQL, projections, or conditions.

### 5.4. Custom SQL with @Query and @Param

~~~java
import com.google.cloud.spring.data.spanner.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends SpannerRepository<Order, String> {

    @Query(
        "SELECT * FROM Orders " +
        "WHERE CustomerId = @customerId AND Status = @status " +
        "ORDER BY CreatedAt DESC LIMIT 50")
    List<Order> findRecentOrders(
            @Param("customerId") String customerId,
            @Param("status") String status);
}
~~~

Spanner SQL uses named parameters formatted like `@customerId`, `@status`. Names in SQL must match the names in `@Param`. Always bind values via parameters; never concatenate user input strings into SQL to avoid injection and escaping bugs.

### 5.5. DML via Query Methods

You can use `@Query` with `dmlStatement = true` for appropriate INSERT/UPDATE/DELETE statements:

~~~java
@Query(
    value = "UPDATE Orders SET Status = @newStatus WHERE OrderId = @orderId",
    dmlStatement = true)
long updateStatus(
        @Param("orderId") String orderId,
        @Param("newStatus") String newStatus);
~~~

The return value is the number of affected rows. Mark `dmlStatement = true` so Spring Data knows the query is DML. DML and the mutation API are two different write mechanisms; choose based on the desired operation and semantics.

### 5.6. Projections and Fetching Only Required Columns

Repositories can return projection interfaces instead of full entities:

~~~java
import com.google.cloud.Timestamp;

public interface OrderSummary {
    String getOrderId();
    String getStatus();
    Timestamp getCreatedAt();
}
~~~

A query projection reduces data read when a screen only needs a few fields. With custom SQL, select the exact columns instead of `SELECT *`. When returning a projection from SQL, aliases and property names must match the mapping Spring Data expects.

### 5.7. Pagination and Result Ordering

You can use `Pageable` and `Sort` with repositories. When paginating, always include a deterministic order, ideally adding the primary key as a tie-breaker. If you sort only by timestamps that may collide, rows can shift positions across pages.

Separate page calls are not implicitly executed within the same snapshot transaction. If data changes between a user fetching page 1 and page 2, results may differ. For reports needing a consistent snapshot, use an appropriate read-only transaction or design cursor/keyset pagination matching the query pattern.

## 6. Querying and Writing with SpannerTemplate

### 6.1. When to Use the Template?

`SpannerTemplate` is appropriate when you need:

- Custom SQL or dynamic parameterized queries.
- Reads by key or key set.
- Reading/writing a subset of properties.
- DML statements and transactions.
- Access to Spanner features not cleanly expressed via repositories.

The Spring Boot starter auto-configures the `SpannerTemplate` bean, which can be injected into services.

### 6.2. Querying with Statement and Named Parameters

~~~java
import com.google.cloud.spanner.Statement;
import com.google.cloud.spring.data.spanner.core.SpannerTemplate;

import java.util.List;

@Service
public class OrderQueryService {

    private final SpannerTemplate spannerTemplate;

    public OrderQueryService(SpannerTemplate spannerTemplate) {
        this.spannerTemplate = spannerTemplate;
    }

    public List<Order> findByCustomerAndStatus(
            String customerId, String status) {

        Statement statement = Statement.newBuilder(
                "SELECT * FROM Orders " +
                "WHERE CustomerId = @customerId AND Status = @status " +
                "ORDER BY CreatedAt DESC")
            .bind("customerId").to(customerId)
            .bind("status").to(status)
            .build();

        return spannerTemplate.query(Order.class, statement);
    }
}
~~~

`Statement.Builder.bind` keeps parameter values separate from the SQL text. This makes queries safe and reusable. For large queries, inspect execution plans, indexes, and rows scanned.

### 6.3. Reading by Primary Key and KeySet

If the key is already known, use the read API instead of a general SQL query:

~~~java
import com.google.cloud.spanner.Key;

Order order = spannerTemplate.read(Order.class, Key.of(orderId));
~~~

For composite keys, construct `com.google.cloud.spanner.Key` from the components in exact schema order. `KeySet` allows reading a set of keys or key ranges; this fits when the range to read is known ahead of time. The read API expresses key-based access patterns more explicitly than a generic SELECT statement.

### 6.4. Insert, Update, and Upsert

~~~java
spannerTemplate.insert(order);  // Inserts a new row.
spannerTemplate.update(order);  // Updates an existing row.
spannerTemplate.upsert(order);  // Updates or inserts.
~~~

Choose the method based on business invariants. `insert` fits when the row must be new; `update` when the row already exists; `upsert` when both cases are allowed.

By default, update writes the entity's properties. When you only want to write certain columns, you can use overloads accepting a list of property/column names supported by your library version. Understand partial updates clearly so you do not overwrite fields unintentionally.

### 6.5. DML and Partitioned DML

`SpannerTemplate` supports executing DML statements. Partitioned DML suits certain bulk updates/deletes across many rows, though it has limitations and does not run inside a standard transaction.

Do not use Partitioned DML as a replacement for a read-write transaction in business workflows requiring multi-step atomicity. Check supported statement limits, affected row counts, and idempotency before running large batches.

## 7. Transactions with Spring Data Spanner

### 7.1. @Transactional

Spring Data Spanner supports `@Transactional` via the Spanner transaction manager provided by the starter:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class OrderWriteService {

    private final OrderRepository orderRepository;
    private final OrderItemRepository itemRepository;

    public OrderWriteService(
            OrderRepository orderRepository,
            OrderItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    @Transactional(transactionManager = "spannerTransactionManager")
    public void createOrder(Order order, List<OrderItem> items) {
        orderRepository.save(order);
        itemRepository.saveAll(items);
    }
}
~~~

The transaction manager name is specified explicitly to avoid ambiguity when the application also has transaction managers for Cloud SQL, JPA, or another datastore. In simple setups with only Spanner, Spring can pick the single manager automatically.

### 7.2. Do Not Nest Transactions

Spanner does not support nested transactions. Do not call `performReadWriteTransaction` or `performReadOnlyTransaction` from inside a `@Transactional` method already running a Spanner transaction. Choose one transaction mechanism per unit of work.

Read-write transactions fit when you need to read and then write related data in one atomic unit. Read-only transactions fit when you need multiple reads across a single consistent snapshot.

### 7.3. Transactions Can Be Retried

Cloud Spanner may abort a read-write transaction due to contention or transient conditions. The client library includes retry logic to re-run the transaction callback. Therefore, code inside the callback must be safe to execute multiple times.

Do not send emails, call payment gateways, publish messages, or write directly to external systems inside a transaction callback. External side effects could happen multiple times even though the database transaction only commits once. Use the outbox pattern or record events within the same transaction and process them after commit.

### 7.4. Keep Transactions Short

Keep transactions short to reduce lock duration and contention:

- Read only the rows you need.
- Avoid calling HTTP services inside a transaction.
- Do not wait on user input or slow I/O inside a transaction.
- Avoid transactions updating overly large row ranges when batching is possible.
- Design keys so atomic operations typically touch a cohesive region of data.

### 7.5. Strong Reads and Stale Reads

Reads/queries default to strong reads: results reflect all changes committed before the read begins. Spanner also supports stale reads at a past timestamp to trade data freshness for latency/throughput benefits in certain scenarios.

Use stale reads for analytics screens or data where slight staleness is acceptable to the business. Do not use stale reads for inventory checks or payment decisions requiring the latest data without carefully evaluating semantics.

## 8. Interleaved Tables and Parent-Child Relationships

### 8.1. When Should You Use @Interleaved?

`@Interleaved` represents child rows interleaved inside a parent table. For example, `OrderItems` belong to an `Order`, are usually read alongside the order, and share its lifecycle.

~~~java
@Table(name = "Orders")
public class Order {
    @PrimaryKey
    private String orderId;

    @Interleaved
    private List<OrderItem> items;
}
~~~

The child entity must include the full primary key of the parent in the same order, followed by the child's own key.

### 8.2. Eager and Lazy Loading

By default, interleaved rows are loaded together with the parent entity. If the collection is large or only occasionally needed, you can choose:

~~~java
@Interleaved(lazy = true)
private List<OrderItem> items;
~~~

Lazy loading reduces child reads when not needed, though accessing the property can trigger additional read operations. Avoid loops accessing each collection and causing many round-trips. Measure query/read counts and choose eager/lazy based on usage patterns.

### 8.3. Interleaving Is Not a General ORM Relationship

Interleaving is a physical decision about data locality in Spanner, not merely an annotation to build JPA-style collections. It fits parent-child relationships with a clear key hierarchy. For many-to-many relationships, independent references, or entities with separate lifecycles, use join tables and foreign keys as appropriate.

Do not interleave every relationship just to avoid writing join queries. Decide based on access patterns, lifecycle, write distribution, and scaling requirements.

## 9. Indexes, Query Performance, and Schema Evolution

### 9.1. Indexes Are Part of Data Design

Spanner requires indexes for query patterns not served directly by the primary key. Indexes can sort across multiple columns in ASC/DESC order. Indexes speed up reads but add write and storage overhead.

Example:

~~~sql
CREATE INDEX OrdersByCustomerCreatedAt
ON Orders(CustomerId, CreatedAt DESC);
~~~

This index fits queries filtering on `CustomerId` and fetching the newest orders. If queries also filter on `Status`, benchmark and consider an index with appropriate columns. Do not add indexes by guesswork.

### 9.2. Avoid SELECT *

If a screen only needs order ID, status, and timestamp, select only those columns or use a projection. Reading less data reduces network transfer and mapping overhead.

~~~sql
SELECT OrderId, Status, CreatedAt
FROM Orders
WHERE CustomerId = @customerId
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

### 9.3. Schema Evolution

Entity annotations describe mappings, but they do not automatically keep the production schema aligned with new classes. DDL changes require a controlled migration process:

1. Create a new versioned DDL migration.
2. Verify backward compatibility with running application versions.
3. Apply DDL via a pipeline or administrative tool.
4. Deploy the application using the new fields.
5. Backfill data if necessary.
6. Remove old columns only after all consumers have transitioned.

A Spanner table's primary key cannot be arbitrarily altered like editing an annotation. Changing keys usually requires redesigning or creating a new table and migrating data.

### 9.4. Schema Utilities

The starter provides `SpannerSchemaUtils` and `SpannerDatabaseAdminTemplate` to generate DDL from an entity hierarchy and execute DDL. This is useful in experiments or environment bootstrapping.

For production, version-control DDL and run reviewed migrations in a deployment pipeline. Avoid letting every replica auto-create or alter schemas at startup, as that causes races, overly broad runtime permissions, and poor auditability.

## 10. Spanner Session Pool vs. HikariCP

### 10.1. Spanner Uses a gRPC Session Pool

Spring Data Spanner uses the Cloud Spanner Java client. The client manages gRPC channels and a **session pool** to reuse Spanner sessions. This is not a JDBC DataSource and not HikariCP.

| Cloud SQL JDBC | Cloud Spanner |
| --- | --- |
| JDBC driver | Cloud Spanner Java client/gRPC |
| HikariCP connection pool | Spanner session pool |
| JDBC connection | Spanner session |
| JDBC URL | Project/instance/database config |
| JDBC transaction manager | Spanner transaction manager |

Do not configure `spring.datasource.hikari` to tune Spring Data Spanner. Instead, use `spring.cloud.gcp.spanner.*` properties matching your Spring Framework on Google Cloud version.

### 10.2. Session Pool Properties

Some configurations available in Spring Cloud GCP:

| Property | Meaning |
| --- | --- |
| `spring.cloud.gcp.spanner.minSessions` | Minimum number of sessions maintained |
| `spring.cloud.gcp.spanner.maxSessions` | Maximum number of sessions in the pool |
| `spring.cloud.gcp.spanner.maxIdleSessions` | Maximum number of idle sessions |
| `spring.cloud.gcp.spanner.failIfPoolExhausted` | Fails immediately when out of sessions instead of waiting |
| `spring.cloud.gcp.spanner.keepAliveIntervalMinutes` | Session keepalive interval |
| `spring.cloud.gcp.spanner.numRpcChannels` | Number of gRPC channels |

Property names and defaults depend on the version. Check the reference documentation for the BOM in use before changing them. Increasing `maxSessions` does not automatically make queries faster and can increase resource usage and concurrency generated by the workload.

### 10.3. Setting Limits Based on Workload

The session pool should be sized based on replica count, concurrency, and transaction patterns. If an application runs many replicas, total sessions grow with the number of processes. Observe pool exhaustion, session usage, RPC latency, and transaction aborts before tuning.

## 11. IAM, Auditing, and Data Protection

### 11.1. Workload Identity

Attach a dedicated service account to the Spring Boot service and let ADC obtain credentials from the runtime. Do not store service account JSON keys in source code, images, or configuration files committed to Git.

Separate principals by responsibility:

- Runtime reading/writing data.
- Migration updating schemas.
- Read-only reporting.
- Operator administering instances/databases.

### 11.2. Least Privilege

`roles/spanner.databaseUser` permits reading/writing and certain schema operations. If the runtime does not need to update schemas, evaluate fine-grained access control, database roles, or custom IAM roles to narrow permissions.

`roles/spanner.databaseReader` fits read-only services. Do not grant instance admin permissions to a service that only queries orders.

### 11.3. Auditing and Application Authorization

Enable audit logging according to organizational policy and record request/correlation IDs at the application layer. Do not log full sensitive payloads or customer data unnecessarily.

Spanner IAM does not replace per-tenant authorization checks. Every query handling tenant data should bind the tenant ID from the authenticated identity, never trusting arbitrary tenant values from the request body.

## 12. Testing with the Cloud Spanner Emulator

### 12.1. Starting the Emulator

The Spanner Emulator provides a local in-memory environment suitable for development and integration tests. Data is not persisted across runs, and the emulator is not a production environment.

It can be started using the Google Cloud CLI:

~~~bash
gcloud emulators spanner start
~~~

Then configure Spring:

~~~yaml
spring:
  cloud:
    gcp:
      spanner:
        project-id: local-project
        instance-id: test-instance
        database: test-db
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

Create the test instance/database in the emulator and apply DDL before running repository tests. If using a different host/port, configure `emulator-host` per the starter version's property.

### 12.2. Integration Tests

You can use the Testcontainers gcloud module with `SpannerEmulatorContainer` for automated CI tests. Tests should cover:

- Field mappings and composite keys.
- Insert, update, upsert, and delete.
- Derived query methods.
- `@Query` with named parameters.
- Interleaved parent-child rows.
- Transaction commits and rollbacks.
- DML updates and affected row counts.
- Schema migrations.
- Entity-not-found cases.

### 12.3. Emulator Limitations

The emulator is useful for verifying logic and mappings, but it does not fully represent production regarding performance, data distribution, contention, quotas, IAM, and certain features/behaviors. Before release, run a suite of integration tests on a sandbox project with IAM/networking similar to production and measure real query latency.

## 13. Diagnosing Common Errors

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Cannot create Spanner client | Wrong Project ID, ADC, or API disabled | Check credentials, project, API, and service account |
| Permission denied | Missing Spanner IAM role | Check `roles/spanner.databaseUser` or appropriate read-only role |
| Database/instance not found | Wrong instance ID or database name | Cross-check properties against Cloud resources |
| Entity fails to map to table | Wrong `@Table` or table name | Check DDL and mapping annotations |
| Column not found | Wrong `@Column` or naming strategy | Compare properties with actual schema |
| Primary key mapping error | Missing `@PrimaryKey` or wrong keyOrder | Check column count and primary key order in DDL |
| Child rows do not load | Wrong composite key/interleave mapping | Verify parent key is present and in the same order |
| Query parameter missing | `@Param` name mismatches SQL placeholder | Compare parameter names in both places |
| Slow queries | Missing index or scanning too many rows | Inspect query plan, indexes, and rows scanned |
| Transaction aborted | Contention or transaction too long | Shorten transaction, reduce write contention hotspots, and let client retry |
| Session pool exhausted | Concurrency exceeds pool/session budget | Monitor session usage and adjust pool/replicas |
| Local tests pass but cloud fails | Emulator does not reflect IAM/quotas/network/prod load | Test on real sandbox with runtime identity |

Do not fix mapping errors by arbitrarily altering production DDL or granting Spanner Admin to the runtime. Identify the exact error layer and reproduce it with a small test.

## 14. Comparing Spring Data Spanner with Other Data Options

| Aspect | Spring Data Spanner | Spring Data JPA + Cloud SQL | AWS/Azure managed relational DB |
| --- | --- | --- | --- |
| Database model | Distributed relational, horizontally scalable | Managed PostgreSQL/MySQL/SQL Server | RDS/Aurora or Azure Database by engine |
| Client | Google Cloud Spanner Java client/gRPC | JDBC driver | JDBC driver |
| Pool | Spanner session pool | Common HikariCP | HikariCP or proxy/pooler |
| Mapping | Spanner-specific annotations | JPA entities/ORM | JPA/JDBC depending on framework |
| Query | GoogleSQL via repository/template | JPQL/SQL by dialect | SQL by engine |
| Transaction | Spanner transaction semantics | Database engine transactions | Database engine transactions |

Spring Data repositories reduce boilerplate, yet they do not turn Spanner into a database with Hibernate semantics. Decisions around primary keys, indexes, interleaving, transaction retries, and session pools still require Spanner-specific expertise.

## 15. Practical Exercises

### Exercise A — Create Schema and Map Entities

Create an `orders` database on a Spanner sandbox. Apply DDL for `Orders` and `OrderItems`, create Java entities with `@Table`, `@Column`, `@PrimaryKey`, and `@Interleaved`. Verify mapping with one parent having two child rows.

### Exercise B — Build Repositories

Create `OrderRepository` extending `SpannerRepository<Order, String>`. Write query methods to find orders by customer, status, and timestamp. Write a custom `@Query` with `@Param` to fetch the 50 newest orders.

### Exercise C — Use SpannerTemplate

Write a service using `SpannerTemplate` and `Statement.Builder.bind` to query by customer ID. Perform insert/upsert and compare semantics with repository `save`.

### Exercise D — Key and Index Design

Create a high-write-load log table. Compare an ascending timestamp primary key against UUID v4 or a shard prefix. Design indexes around query patterns and explain the added write cost.

### Exercise E — Transactions and Retries

Write a transaction creating an order and items. Simulate contention in a test environment; verify retries do not send duplicate emails or publish duplicate messages. Propose an outbox pattern for side effects outside the database.

### Exercise F — Emulator and Cloud Integration

Run repository tests against the Spanner Emulator in CI. Then deploy a test on a real sandbox to verify ADC/IAM, DDL, queries, and behavior under concurrent load.

### Self-Check Questions

1. How does Cloud Spanner differ from Cloud SQL in client architecture and data distribution?
2. Why is Spring Data Spanner not JPA/Hibernate?
3. Can Spanner's PostgreSQL interface use Spring Data Spanner?
4. Is `@PrimaryKey` required when a table has only one key column?
5. Which part of the DDL must `keyOrder` match?
6. Why can sequentially increasing keys cause hotspots?
7. What advantage does UUID v4 have as a primary key?
8. When should you use `@Interleaved`?
9. What do `@NotMapped` and `@Embedded` mean?
10. When should you use a repository vs. `SpannerTemplate`?
11. What is the syntax for named parameters in Spanner SQL?
12. Why should queries bind parameters rather than concatenate strings?
13. What are the semantics of `SpannerRepository`'s `save`?
14. Why must Spanner transactions not be nested?
15. Why might a transaction callback execute multiple times?
16. Why shouldn't you send emails or call payment gateways inside a transaction callback?
17. How does Spanner's session pool differ from HikariCP?
18. Which types of production testing can the emulator not replace?

**Expected outcome:** learners can design Cloud Spanner schemas with appropriate primary keys and indexes, map Java entities with Spring Data Spanner, build parameterized repositories/queries, use SpannerTemplate and transactions with proper semantics, test using the emulator, and implement access control using workload identity.

## References

- [Integrate Spanner with Spring Data](https://docs.cloud.google.com/spanner/docs/adding-spring)
- [Spring Framework on Google Cloud — Spring Data Cloud Spanner reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
- [Spanner schema design best practices](https://docs.cloud.google.com/spanner/docs/schema-design)
- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Cloud Spanner IAM roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/spanner)

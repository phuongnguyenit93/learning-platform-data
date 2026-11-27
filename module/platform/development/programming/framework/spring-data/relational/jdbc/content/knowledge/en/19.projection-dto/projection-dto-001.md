# Separating the Read Model from the Aggregate Used for Updates

In **Spring Data Relational JDBC**, the aggregate root is the unit the application uses to perform business changes and save consistent state. However, a list screen, report, or search API often only needs a few fields from multiple tables. If every query loads the full aggregate and converts it to JSON, the application may read unnecessary data and force the write model to serve very different display needs.

A clear way to organize this is to separate:

- **Write model:** the aggregate root and domain behaviors used to enforce invariants, mutate state, and save through the repository.
- **Read model:** a projection or DTO containing the exact data a query/screen needs.

This is a moderate application of CQRS: separating the read path and write path in terms of models and APIs, while still being able to share the same relational database. There is no need to build event sourcing or two separate storage systems just to use projections.

## 1. Why Not Use Aggregates for Every Query?

Suppose a sales system has the following aggregate:

```text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── status
  ├── customer reference
  ├── shippingAddress
  └── lines
        ├── OrderLine
        ├── OrderLine
        └── ...
```

This model fits business operations such as confirming an order, changing the shipping address, or adding order lines. However, an order list page may only need:

```text
OrderListItem
  ├── orderId
  ├── orderNumber
  ├── customerName
  ├── status
  ├── createdAt
  └── totalAmount
```

If you load each full aggregate to display the list, the application may have to load the order lines and properties that are not displayed. As the number of orders grows, this approach creates extra data transferred over JDBC, objects allocated in the JVM, and mapping work.

A read model lets you query the exact columns needed, combine data according to screen requirements, and return a simple structure. The write model preserves aggregate boundaries so business changes remain controlled.

## 2. Write Model: The Aggregate Responsible for Business Changes

Example order aggregate:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void addLine(OrderLine line) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only a draft order can be changed");
        }
        lines.add(line);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "An order must contain at least one line");
        }
        status = "CONFIRMED";
    }
}

public record OrderLine(
        String sku,
        int quantity
) {}
```

Write repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Service updating the aggregate:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderCommandService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return repository.save(order);
    }
}
```

Here, the service loads the full aggregate, invokes the domain behavior, and saves the root. Confirming an order requires knowing the order lines to check the invariant. This is the job of the write model.

Spring Data JDBC does not use a persistence context and JPA-style dirty checking. When calling `save`, the application sends the aggregate state through the repository; therefore, you should not create an object with only an ID and a few fields and treat it as a full update. Reading the existing aggregate, mutating it via domain methods, and saving it again keeps the state and child relationships accurate.

## 3. Read Model: Returning Only the Data the Query Needs

A read model is usually a DTO or projection. It does not need full domain behavior, state-mutating methods, or a one-to-one mapping to a single table.

Example DTO for a list screen:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        Instant createdAt,
        BigDecimal totalAmount
) {}
```

A DTO can combine data from multiple tables, compute totals, rename fields for the API, or omit columns that are not allowed to be exposed. You do not need to turn a DTO into an aggregate root just because it holds data about an order.

A read DTO should not be passed into `PurchaseOrderRepository.save`. It does not represent the complete state of the aggregate and is not responsible for protecting invariants.

## 4. Interface-Based Projection

Spring Data supports interface-based projections for eligible query methods. The interface declares the accessors the application wants to read:

```java
public interface CustomerSummary {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(String status);
}
```

When calling it:

```java
List<CustomerSummary> active =
        customerRepository.findByStatus("ACTIVE");

for (CustomerSummary customer : active) {
    System.out.println(customer.getFullName());
}
```

Spring Data creates a projection for the query result according to the declared properties. This interface is a read view of the data; it does not replace the `Customer` entity and is not an object to be saved via the repository.

### 4.1. Closed Projection

A projection is a **closed projection** when its accessors correspond directly to properties of the domain type:

```java
public interface CustomerListView {
    Long getId();
    String getFullName();
    String getStatus();
}
```

The framework knows exactly which properties are requested. For query types and modules that support projection optimization, Spring Data can limit the selected data to only the required properties. Specific optimization capabilities depend on Spring Data JDBC, the query type, and the version; observe the actual SQL rather than assuming every interface projection always reduces the column count.

### 4.2. Projection with Computed Accessors

A projection can provide default methods based on existing properties:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

`getDisplayName()` is computed in Java from the two accessors, not from a database column. If the display logic is simple and only used in the read model, a default method can be convenient.

With SpEL-dependent expressions or properties that cannot be statically determined, the projection is no longer a closed projection in the property-optimization sense. Do not use complex dynamic expressions to replace a clearly designed read query.

### 4.3. A Projection Is Not a Write Contract

Do not add setters or state-mutating methods to a projection expecting Spring Data JDBC to persist the changes. Projections serve reading; write operations must go through the aggregate root and its corresponding repository.

## 5. Class-Based Projection and DTO

If you want a concrete data type instead of an interface proxy, you can use a DTO class or a Java record:

```java
public record CustomerCard(
        Long id,
        String fullName,
        String email
) {}
```

A custom query method can return a DTO:

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface CustomerReadRepository
        extends Repository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email
        FROM customer
        WHERE status = :status
        ORDER BY full_name, id
        """)
    List<CustomerCard> findCardsByStatus(
            @Param("status") String status);
}
```

With class-based projections, the constructor/record components and returned column names need to match the mapping mechanism of the Spring Data Relational version in use. If using aliases, choose aliases compatible with property/constructor parameter names; if the query omits required columns or uses incompatible types, mapping may fail.

The SQL example above uses the PostgreSQL column name `full_name`, while the record has a `fullName` component. Verify that your project's naming strategy/column mapping handles this name as expected. When you need certainty about transformations or very complex queries, using `JdbcTemplate` with an explicit `RowMapper` is a clear choice.

### 5.1. DTO Projection and Custom Queries

A read query typically selects only the necessary columns:

```sql
SELECT id, full_name, email
FROM customer
WHERE status = ?
ORDER BY full_name, id;
```

There is no need to select columns such as password hashes, internal details, or fields not used on the screen. This both optimizes data transfer and reduces the risk of accidentally exposing sensitive fields in a response.

Custom queries should:

- Select only the columns the DTO needs.
- Use explicit aliases when result column names need to differ from schema names.
- Use bind parameters for filter values.
- Use a whitelist if dynamic sorting is needed; never concatenate user-supplied identifiers into SQL.
- Verify SQL and Java data types, especially for decimals, date/time values, and nullable columns.

## 6. When You Need Manual Mapping Control: JdbcTemplate and RowMapper

For reports or multi-table JOIN queries, you can use Spring JDBC directly to construct DTOs. This is especially useful when the result does not correspond to a single aggregate.

Example DTO:

```java
import java.math.BigDecimal;

public record OrderListItem(
        Long orderId,
        String orderNumber,
        String customerName,
        String status,
        BigDecimal totalAmount
) {}
```

Read repository:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadDao {

    private final JdbcTemplate jdbcTemplate;

    public OrderReadDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<OrderListItem> findOrderCards(String status) {
        String sql = """
            SELECT
                o.id AS order_id,
                o.order_number,
                c.full_name AS customer_name,
                o.status,
                COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            LEFT JOIN order_line l ON l.purchase_order_id = o.id
            WHERE o.status = ?
            GROUP BY o.id, o.order_number, c.full_name, o.status
            ORDER BY o.id DESC
            """;

        return jdbcTemplate.query(sql, (rs, rowNum) ->
                new OrderListItem(
                        rs.getLong("order_id"),
                        rs.getString("order_number"),
                        rs.getString("customer_name"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                ),
                status
        );
    }
}
```

The SQL above is a PostgreSQL example; the schema needs `customer_id` on the order table and `unit_price`, `quantity` on the order line table. `JdbcTemplate` binds `status` via the `?` parameter, and the `RowMapper` converts each result set row into an `OrderListItem`.

Here, each result row is a read card, not a `PurchaseOrder` aggregate to be saved back. The DTO is built directly from JOIN data and aggregations.

### 6.1. Be Careful with One-to-Many JOINs

If an order has multiple lines, a JOIN produces multiple result rows for the same root. When the DTO only needs the total amount, use `GROUP BY` and an aggregate function such as `SUM`. If the DTO needs a nested list of order lines, a simple row-by-row `RowMapper` will produce multiple DTOs with duplicate roots; you need to group by ID inside a `ResultSetExtractor` or run multiple intentional queries and merge the results.

Do not manually map a flat result set into an update aggregate model if the query does not provide enough data and domain rules to reconstruct the aggregate.

## 7. Dynamic Projection

Spring Data Commons supports dynamic projections for certain query methods: the caller passes the desired projection type. General example:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    <T> List<T> findByStatus(String status, Class<T> projectionType);
}
```

You can call it as:

```java
List<Customer> entities =
        repository.findByStatus("ACTIVE", Customer.class);

List<CustomerSummary> summaries =
        repository.findByStatus("ACTIVE", CustomerSummary.class);
```

This allows the same filter condition to return different views. However, dynamic projection depends on query derivation, the projection type, and the Spring Data JDBC version's support. Not every custom query or complex mapping can arbitrarily swap target types. If your project does not support this signature for a specific query, declare separate read methods with explicit return types.

When there are multiple read shapes, do not turn dynamic projection into an uncontrolled arbitrary API. Only provide projections that the application layer has a reason to use.

## 8. Organizing Repositories and Services Along Read/Write Lines

You can separate the aggregate write repository and the read query component:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

```java
public interface OrderReadRepository {
    List<OrderListItem> findOrderCards(String status);
}
```

Write service:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository repository;

    public OrderCommandService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long id) {
        PurchaseOrder order = repository.findById(id).orElseThrow();
        order.confirm();
        return repository.save(order);
    }
}
```

Read service:

```java
@Service
public class OrderQueryService {

    private final OrderReadRepository readRepository;

    public OrderQueryService(OrderReadRepository readRepository) {
        this.readRepository = readRepository;
    }

    public List<OrderListItem> list(String status) {
        return readRepository.findOrderCards(status);
    }
}
```

`OrderReadRepository` in the example is an application-defined interface; it can be implemented using `JdbcTemplate`, a Spring Data repository projection, or another suitable read technology. The goal is for controllers to call the right use case:

- Command service accepts commands and mutates the aggregate.
- Query service returns projections/DTOs for reading.

For small projects, it is not necessary to create multiple modules or class layers just because you have DTOs. You can place projection query methods directly on the existing repository. Split them out when read queries have distinctly different needs, SQL, or lifecycles.

## 9. Pagination for the Read Model

List screens often require pagination. You can combine projections with `Pageable` if the repository method and version support it:

```java
Page<CustomerSummary> findByStatus(
        String status,
        Pageable pageable
);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);

Page<CustomerSummary> page =
        repository.findByStatus("ACTIVE", pageable);
```

When using projections, you must still sort by valid persistent properties. If the projection only has `id`, `fullName`, and `status` but sorts by `createdAt`, verify that the query/mapping allows sorting by that property even though it is not in the projection output. With custom SQL, declare `ORDER BY` and pagination syntax appropriate for your dialect.

If the client only needs to know "is there a next page", consider `Slice<T>` instead of `Page<T>` when the query type supports it; `Page` typically requires a total element count and may trigger a count query.

## 10. DTOs Do Not Automatically Guarantee Reading Fewer Columns

A common misconception is assuming that simply changing the return type from an entity to a DTO guarantees the database will only send the columns the DTO needs.

Distinguish between:

1. **Result type:** the projection/DTO determines the structure of the returned object.
2. **SQL projection:** the `SELECT` clause determines which columns the database returns.
3. **Mapping optimization:** Spring Data may optimize column selection for supported projection types.

With custom queries, you control the column list in `SELECT`. With derived queries, the framework may optimize closed projections depending on the module/version. Always observe the actual SQL if your goal is to reduce data transfer.

In particular, if a custom query uses `SELECT *` and maps into a DTO, the database still returns all columns selected by the asterisk, even if the DTO only keeps three fields. List only the required columns:

```sql
-- Avoid if only three fields are needed:
SELECT *
FROM customer
WHERE status = ?;

-- Select the exact columns needed:
SELECT id, full_name, email
FROM customer
WHERE status = ?;
```

## 11. Data Consistency Between the Read Path and Write Path

Separating the read model and write model does not mean data is automatically synchronized via events. If both share the same relational database, read queries typically see committed data according to the transaction's isolation level.

A simple flow:

```text
Command API
    │
    ▼
Command Service
    │ load aggregate
    ▼
Aggregate Root ── domain behavior
    │
    ▼
Repository.save(root)
    │
    ▼
Transaction commit
    │
    ▼
Relational database
    ▲
    │ query projection / DTO
    │
Query Service
    ▲
    │
Read API
```

When a read query runs after the write transaction has committed, it reads the committed state according to the appropriate transaction/isolation settings. If a query reads inside another concurrent transaction, the result depends on the isolation level and query timing.

If you later separate the read model into a dedicated database or search index, updates are typically driven by events/messages or a sync pipeline. At that point, **eventual consistency** can arise: a command succeeds, but the read model is not updated immediately. This is a bigger architectural decision than using projections; it requires retry mechanisms, idempotency, lag monitoring, and sync error handling.

## 12. Security and API Data Boundaries

Projections/DTOs are a good opportunity to restrict the data allowed to be returned. Entities may contain internal information such as:

- Password hashes or credential metadata.
- Internal notes, risk control flags.
- Personal data not needed by the screen.
- Technical fields used for persistence.

Do not return entities directly just because they already exist. Create a read DTO containing only the fields the API is allowed to expose publicly:

```java
public record CustomerPublicView(
        Long id,
        String displayName
) {}
```

Projections do not replace authorization. Queries must still restrict data by tenant, user, role, and access permissions. For example:

```sql
SELECT id, full_name
FROM customer
WHERE tenant_id = ?
  AND status = ?;
```

Do not just filter in Java after loading all data. Place access-control conditions in the appropriate query and verify permissions in the service/controller according to the application's security design.

## 13. When to Choose Projection, DTO, or Aggregate?

| Need | Suitable Choice |
| --- | --- |
| Change order state and enforce invariants | Load aggregate root, invoke domain behavior, save root |
| List needing only a few properties of one entity | Interface projection or DTO projection |
| Report combining multiple tables, aggregate functions | DTO with custom query/`JdbcTemplate` |
| Detail screen needing full aggregate behavior and relationships | Aggregate root may be suitable |
| API data needing to strip internal fields | Field-restricted response DTO/projection |
| Multiple display shapes from the same filter criteria | Dynamic projection if supported by query/module |
| Very complex query or custom SQL optimization needed | Dedicated read query DAO and DTO |

Do not create a new aggregate just to hold report results. Do not use a read DTO for writes. And do not split read/write into two databases if the current need is simply to avoid over-fetching.

## 14. Common Mistakes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Projection getter returns null | Accessor name does not match property or result alias | Cross-check Java property, column alias, and mapping |
| DTO constructor is not invoked properly | Parameter names/order or data types mismatch | Check constructor/record components and returned columns |
| DTO still loads many columns | Query uses `SELECT *` or projection is not optimized | Select columns explicitly and inspect SQL |
| JOIN produces duplicate root DTOs | One-to-many relationship duplicates root in result set | GROUP BY/aggregate or group rows with an extractor |
| Calling `save` with a DTO fails to work | DTO is not an aggregate entity | Read the root and update via domain behavior |
| Read API sees stale data | Transaction uncommitted, isolation, or separate read store out of sync | Clarify transaction boundaries and sync model |
| Projection sorting fails | Sort uses column name instead of property or invalid property | Use persistent property or declare ORDER BY in custom SQL |
| Projection leaks unwanted fields | Returning entity/DTO with too many fields | Create a data-restricted DTO and verify authorization |

## 15. Practice Exercises

**Exercise 1 — Separate command and query.** Use `PurchaseOrderRepository` to load and confirm an order. Create a separate query service that returns a list of orders by status.

**Exercise 2 — Interface projection.** Create `CustomerSummary` containing only ID, name, and email. Declare a derived query returning `List<CustomerSummary>` and call it from a service.

**Exercise 3 — DTO projection.** Create a `CustomerCard` record and a custom query selecting only ID, name, and email. Verify column/constructor mapping in your project's Spring Data JDBC version.

**Exercise 4 — JOIN read model.** Use `JdbcTemplate` to build `OrderListItem` including customer name and total amount. Confirm an order with multiple lines yields only one card thanks to `GROUP BY`.

**Exercise 5 — Pagination.** Return a projection with `Pageable`; compare `Page` and `Slice` in terms of metadata and the number of SQL statements executed.

**Exercise 6 — Response security.** Add an internal field to the entity but exclude it from the public DTO. Verify the JSON response does not contain that field and the query includes an appropriate tenant condition.

### References

- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html): interface-based, class-based, and dynamic projections.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods and projections in Spring Data JDBC.
- [Spring Data Relational — JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html): repository abstraction and aggregate access in Spring Data JDBC.

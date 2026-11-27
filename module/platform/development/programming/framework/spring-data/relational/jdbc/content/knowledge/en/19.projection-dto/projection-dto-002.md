# Closed Interface Projections and Selected Properties

In **Spring Data Relational JDBC**, repositories usually return the aggregate root so the application can perform business behaviors. However, many screens only need a few properties of an aggregate, such as order number, status, and creation date. Loading the entire object just to read three fields can add unnecessary overhead.

**Closed interface projections** let you declare an interface containing only the accessors corresponding to the properties you need to read. Spring Data can determine in advance the set of properties the projection requires and, in supported query cases, optimize the SELECT statement to fetch only the necessary columns.

This lesson covers how to declare a closed projection, how getter names bind to Java properties of the aggregate, how repositories return projections, what selected properties mean, and limitations when data is needed from another aggregate or child collection. We will also compare projections with aggregate roots, DTOs, and custom SQL.

## 1. What Is a Projection?

A projection is a **restricted data view** over an object. Instead of returning the entire `PurchaseOrder`, the application can request a type that only describes `id`, `orderNumber`, and `status`.

Suppose the aggregate has many properties:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private Long customerId;
    private String status;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("total_amount")
    private BigDecimal totalAmount;

    // Other properties and domain behaviors.
}
~~~

A list screen might only need:

~~~text
id | orderNumber | status
~~~

If `PurchaseOrder` is returned, the caller receives the other properties as well and potentially mapped components inside the aggregate. If a projection is returned, the caller only sees the accessors declared in the interface.

A projection is not a database table, not a new aggregate root, and does not automatically create an SQL VIEW. It is a result type that Spring Data uses to present queried data.

## 2. What Is a Closed Interface Projection?

An interface projection is considered **closed** when its accessors correspond directly to known properties of the target domain type. Spring Data can determine exactly which properties the projection needs.

Example:

~~~java
package com.example.orders.read;

import java.time.LocalDateTime;

public interface OrderListProjection {

    Long getId();

    String getOrderNumber();

    String getStatus();

    LocalDateTime getCreatedAt();
}
~~~

The getters correspond to the `id`, `orderNumber`, `status`, and `createdAt` properties of `PurchaseOrder`.

The projection does not declare:

- `customerId`, if the screen does not need the customer ID.
- `totalAmount`, if the screen does not display the total amount.
- `lines`, if the screen does not need the list of order lines.
- Other aggregate properties that do not serve the read use case.

Spring Data knows the required property set in advance from the interface. With derived queries and supported projection cases, the framework can limit the columns to read. This is a key benefit of closed projections.

### 2.1. Why Is It Called “Closed”?

The interface closes the scope of data to be accessed: the declared properties can be resolved from the aggregate's metadata. Spring Data does not need to evaluate an arbitrary expression to figure out which fields will be read.

Example:

~~~java
public interface OrderIdentityProjection {
    Long getId();
    String getOrderNumber();
}
~~~

This projection only requests two properties. If the caller only uses the order number and ID, there is no business reason to force it to receive `status`, `customerId`, `createdAt`, or the `lines` collection.

### 2.2. Getters Must Match Java Properties

Getter names are converted to Java property names following JavaBean conventions:

| Getter in projection | Required Java property |
|---|---|
| `getId()` | `id` |
| `getOrderNumber()` | `orderNumber` |
| `getStatus()` | `status` |
| `getCreatedAt()` | `createdAt` |
| `isArchived()` | `archived` |

Names in the interface are based on **Java property names**, not SQL column names. For example:

~~~java
@Column("order_number")
private String orderNumber;
~~~

The projection still declares:

~~~java
String getOrderNumber();
~~~

Do not declare `getOrder_number()` just because the database column name uses snake_case. The `@Column` annotation and naming strategy are responsible for mapping the Java property to the SQL column.

## 3. Using Projections in a Repository

A repository can return a projection interface instead of the aggregate:

~~~java
package com.example.orders.repository;

import java.util.List;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.read.OrderListProjection;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<OrderListProjection> findByStatus(String status);
}
~~~

Calling the repository:

~~~java
List<OrderListProjection> rows =
    repository.findByStatus("SUBMITTED");

for (OrderListProjection row : rows) {
    System.out.println(
        row.getId() + " - " + row.getOrderNumber()
            + " - " + row.getStatus()
    );
}
~~~

The `findByStatus` method still queries by a property of the `PurchaseOrder` aggregate, but the return type is `OrderListProjection`. Spring Data creates projection objects from the query results.

You can use other return types matching the cardinality:

~~~java
List<OrderListProjection> findByStatus(String status);

Optional<OrderListProjection> findByOrderNumber(String orderNumber);

OrderListProjection findFirstByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);
~~~

The last example is only appropriate when business rules and data guarantee a result; if a match might not be found, `Optional` usually expresses the contract more clearly.

Do not declare an inherited method like `findById(Long)` with an incompatible projection return type overriding the one in `CrudRepository`. Use a different query method name, such as `findProjectionByOrderNumber(...)`, or design a separate repository/query interface.

## 4. Which Properties Does a Projection Select?

Consider two projections:

~~~java
public interface OrderIdentityProjection {
    Long getId();
    String getOrderNumber();
}

public interface OrderListProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
    LocalDateTime getCreatedAt();
    BigDecimal getTotalAmount();
}
~~~

The first projection needs two properties. The second projection needs five properties. When the query is optimized for the projection, the column set can be restricted accordingly.

### 4.1. Illustrative SQL for Selected Columns

For `OrderIdentityProjection`, conceptually the SELECT statement only needs:

~~~sql
SELECT id, order_number
FROM purchase_orders
WHERE status = ?;
~~~

For `OrderListProjection`, the SELECT statement needs additional columns:

~~~sql
SELECT
    id,
    order_number,
    status,
    created_at,
    total_amount
FROM purchase_orders
WHERE status = ?;
~~~

This illustrates the **selected property set**, not a guarantee that every Spring Data JDBC version emits this exact SQL string in every situation. The actual statement depends on the query type, mapping, dialect, and framework optimization capabilities.

Enable SQL logging or use a JDBC monitoring tool to verify which columns are read in your running application.

### 4.2. Smaller Projections Give Clearer Read Intent

Do not create a single interface with every getter “for shared convenience” if each screen only needs a small subset of fields. Doing so widens the required property set and defeats the benefit of projections.

Name projections by use case:

~~~java
public interface OrderListProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
}

public interface OrderExportProjection {
    Long getId();
    String getOrderNumber();
    String getStatus();
    LocalDateTime getCreatedAt();
    BigDecimal getTotalAmount();
}
~~~

Both projections can be backed by `PurchaseOrder`, yet express two different read needs. The interface name tells readers what data is requested and where it is used.

## 5. Closed Projections and Computed Properties

A projection can provide default methods computed from declared accessors:

~~~java
public interface OrderListProjection {

    String getOrderNumber();

    String getStatus();

    default String getDisplayLabel() {
        return getOrderNumber() + " [" + getStatus() + "]";
    }
}
~~~

`getDisplayLabel()` does not correspond to a database column. It is a value computed in Java from two properties already present in the projection. Because the default method only uses closed accessors, Spring Data can still determine the source property set.

This works well for simple concatenation for presentation purposes. If the calculation is complex, needs data from multiple tables, or must apply business rules, place the logic in a query service, DTO mapper, or appropriate domain model.

### 5.1. Distinguishing from Open Projections

An open projection can use a SpEL expression to access the target:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface OrderOpenProjection {

    String getOrderNumber();

    @Value("#{target.orderNumber + ' - ' + target.status}")
    String getLabel();
}
~~~

Because a SpEL expression can reference any other properties on `target`, Spring Data cannot determine solely from the interface which properties are needed. Consequently, open projections do not share the same selected-property limiting advantage as closed projections.

When the primary goal is reducing the set of columns read, prefer closed accessors and default methods based solely on those accessors. Do not add `@Value` just to concatenate two simple strings.

## 6. Accessor Data Types

Return types in a projection should be compatible with the aggregate's property types:

| Aggregate property | Projection accessor |
|---|---|
| `Long id` | `Long getId()` |
| `String orderNumber` | `String getOrderNumber()` |
| `BigDecimal totalAmount` | `BigDecimal getTotalAmount()` |
| `LocalDateTime createdAt` | `LocalDateTime getCreatedAt()` |
| `OrderStatus status` | `OrderStatus getStatus()` |
| `boolean archived` | `boolean isArchived()` or matching getter |

If a property can be null, use the corresponding reference type instead of a primitive:

~~~java
public interface CustomerReferenceProjection {
    Long getCustomerId();
    String getOptionalNote();
}
~~~

If the application uses nullable wrappers or `Optional` in projections, ensure the mapping and property types are compatible with your Spring Data version. Do not declare `long getCustomerId()` if the database can return NULL, because a primitive cannot represent null.

For enums, an accessor can use the domain enum type if the aggregate property has that type:

~~~java
public interface OrderStatusProjection {
    OrderStatus getStatus();
}
~~~

Spring Data uses the configured conversion mechanism for the property. If the enum uses a custom storage code, the reading converter must be registered consistently; projections do not replace converters.

## 7. A Projection Is Not a Savable Aggregate

A projection is a read view. It does not replace `PurchaseOrder` in business-mutation workflows.

Example:

~~~java
OrderListProjection row =
    repository.findByOrderNumber("SO-2026-001")
        .orElseThrow();
~~~

You can read:

~~~java
String number = row.getOrderNumber();
String status = row.getStatus();
~~~

But you should not design a flow like:

~~~java
// Not the way to update an aggregate:
row.setStatus("SUBMITTED");
repository.save(row);
~~~

Interface projections typically expose only getters and have no domain behavior. More importantly, a projection does not represent the complete aggregate state, so using it to write could bypass invariants or required properties.

The command flow should load the aggregate:

~~~java
@Transactional
public void submitOrder(Long id) {
    PurchaseOrder order = orders.findById(id)
        .orElseThrow();

    order.submit();
    orders.save(order);
}
~~~

The query flow can use a projection:

~~~java
@Transactional(readOnly = true)
public List<OrderListProjection> listSubmittedOrders() {
    return orders.findByStatus("SUBMITTED");
}
~~~

The two flows serve different goals and can coexist in the same repository or separate query components.

## 8. Do Projections Automatically JOIN Other Aggregates?

Do not assume that adding a getter to a projection automatically generates a JOIN to another table.

Suppose `PurchaseOrder` only stores:

~~~java
private Long customerId;
~~~

and `Customer` is an independent aggregate root. Adding:

~~~java
String getCustomerName();
~~~

does not cause Spring Data JDBC to infer that it needs to JOIN `customers` and fetch `display_name`. `customerName` is not a property of `PurchaseOrder` in this example.

If the screen needs the customer name alongside the order, you can write dedicated read SQL:

~~~sql
SELECT
    o.id AS order_id,
    o.order_number,
    o.status,
    c.display_name AS customer_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status;
~~~

Then map the result into a DTO with `NamedParameterJdbcTemplate`, or use a custom query/projection with mapping explicitly supported in your project's Spring Data JDBC version.

This is the key distinction:

- Closed projections restrict properties of the projected domain type.
- JOINs combine data from multiple tables via SQL.
- DTOs/read models can contain combined or computed values that do not belong to a single aggregate.

Do not invent fake property names on a projection hoping the framework will automatically discover related tables.

## 9. Projections with Child Collections

Suppose the aggregate has:

~~~java
@MappedCollection(idColumn = "order_id")
private Set<OrderLine> lines;
~~~

A list screen only needs `orderNumber` and `status`. A closed projection can request only those two properties:

~~~java
public interface OrderListProjection {
    String getOrderNumber();
    String getStatus();
}
~~~

There is no need to declare `getLines()` if the screen does not use order lines. This avoids requesting unnecessary data when the projection type and query path allow property limiting.

If the screen needs `lineCount` or `totalAmount` calculated from `order_lines`, those are not simple scalar properties of the root unless the aggregate already persists those values. You cannot assume a `getLineCount()` getter will make Spring Data automatically run `COUNT(*)` on the child table.

Use dedicated read SQL:

~~~sql
SELECT
    o.id,
    o.order_number,
    COUNT(l.id) AS line_count,
    COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id, o.order_number;
~~~

The result can be mapped into:

~~~java
public record OrderSummaryDto(
        Long id,
        String orderNumber,
        long lineCount,
        BigDecimal totalAmount
) {
}
~~~

A DTO is more suitable here because `lineCount` and `totalAmount` are computed by the query rather than necessarily being properties stored directly on the aggregate.

## 10. Closed Projections with `@Query`

A repository can also declare custom SQL:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    List<OrderListProjection> findListByStatus(
        @Param("status") String status
    );
}
~~~

When using custom SQL, the SELECT statement must return the required columns with names/aliases compatible with result mapping. Depending on the database, naming strategy, and Spring Data JDBC version's mapping mechanism, alias formatting may need adjustment. Verify with integration tests against your target database rather than assuming camelCase or snake_case aliases are handled identically across all dialects.

In particular:

- Do not omit properties required by the projection in SELECT.
- Do not return multiple columns with the same name after a JOIN without explicit aliases.
- Do not use a root projection assuming child collections will be loaded automatically through a custom SELECT.
- If the query returns aggregated or multi-table results, a DTO/read DAO is usually easier to control.

With simple derived queries, Spring Data can determine properties from the interface projection. With custom SQL, the author bears more responsibility for the column list and aliases.

## 11. Projection, DTO, and Aggregate: Which Should You Choose?

| Criterion | Closed interface projection | DTO/record | Aggregate root |
|---|---|---|---|
| Goal | Read a defined set of properties | Read presentation data or combined results | Execute domain behavior |
| Declaration | Getter interface | Class/record with constructor | Entity/domain class |
| Data source | Usually aggregate properties | Can come from multiple tables or SQL expressions | Aggregate mapping |
| Column set | Can be optimized from closed accessors | Determined by query/mapping | Follows aggregate mapping |
| Computed value | Simple default method | Constructor/mapper or SQL | Domain method |
| Writing data | Not its purpose | Not its purpose | Via root repository |
| Complex JOINs/reports | Does not infer JOINs | Fits custom SQL well | Not the primary goal |

### When to Choose a Closed Projection?

- Derived queries on the aggregate.
- Only a few properties already present on the domain type are needed.
- You want a small, clear interface for a screen or read use case.
- You do not need to modify data via the returned result.

### When to Choose a DTO?

- Results from joining multiple tables.
- Computed columns such as totals, counts, or ranks.
- Returned field names differ from domain properties.
- You want a data structure independent of the entity.
- You need explicit control over the result shape of a report or API.

### When Do You Need the Aggregate Root?

- The use case changes state or data.
- Invariants must be protected.
- You need to work with child entities belonging to the aggregate.
- The result will be saved through the repository.

## 12. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Projection getter is not mapped | Getter name does not match Java property | Name getters according to JavaBean properties |
| Projection requests nonexistent property | Confusing SQL column name with property name or adding a property missing from entity | Check entity and `@Column` mapping |
| SQL still reads more columns than expected | Query path/version does not optimize projection, or projection is open | Inspect actual SQL, use closed accessors and suitable query |
| Adding `@Value` while expecting fewer columns | Open projection allows arbitrary target access | Use closed getters/simple default methods |
| `getCustomerName()` getter does not work | `customerName` is not a property of the aggregate | Use JOIN/DTO or explicit relationship mapping |
| `getLineCount()` getter does not auto-run COUNT | Projections do not generate aggregate functions | Write an aggregate function query and map to a DTO |
| Projection is used for updates | Confusing a read view with a domain entity | Load aggregate root, call business method, `save()` |
| Custom query fails to map columns | Alias or column name mismatches mapping | Use explicit aliases and verify with integration tests |
| Using primitive for nullable property | Primitives cannot represent NULL | Use appropriate wrapper type |
| One projection used for every screen | Interface contains too many properties | Create small projections per use case |

## 13. Verifying Actual SQL of Projections

The property-selection benefit should be confirmed by inspecting the executed SQL. Enable application SQL logging in development:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
    org.springframework.data.jdbc: DEBUG
~~~

Specific logger levels may vary across Spring Boot/Spring Data versions. If logs do not show the full SQL or bind parameters, use a datasource proxy, JDBC monitoring tool, or database logs.

When verifying, compare:

1. Repository method returning `PurchaseOrder`.
2. Repository method returning `OrderIdentityProjection`.
3. Repository method returning `OrderListProjection`.

Observe:

- Does the SELECT column list change according to the projection?
- Are unnecessary tables or collections being read?
- Do the queries share the same WHERE and ORDER BY clauses?
- Do the projection results have accurate values and types?
- Does actual cost decrease on a representative dataset?

Do not draw performance conclusions solely from the number of getters in an interface. Actual results also depend on the database, indexes, row size, driver, mapping, and record count.

## 14. Practice Exercises

### Exercise 1 — Create Your First Closed Projection

1. Create `PurchaseOrder` with `id`, `orderNumber`, `status`, `customerId`, `createdAt`, and `totalAmount`.
2. Create `OrderIdentityProjection` with only `getId()` and `getOrderNumber()`.
3. Declare `List<OrderIdentityProjection> findByStatus(String status)`.
4. Call the repository and print both properties.
5. Enable SQL logging to observe the queried column set.

### Exercise 2 — Create a Projection for a List Screen

1. Create `OrderListProjection` with `id`, `orderNumber`, `status`, and `createdAt`.
2. Create a query method returning the projection.
3. Add `default String getDisplayLabel()` based on `getOrderNumber()` and `getStatus()`.
4. Compare it with an open projection using `@Value`.
5. Explain why closed projections are easier to optimize for selected properties.

### Exercise 3 — Handle Properties Outside the Aggregate

1. Add a `customers` table and a `customerId` property in `PurchaseOrder`.
2. Try declaring a `getCustomerName()` getter in the projection.
3. Identify why the getter does not automatically generate a JOIN to the customer table.
4. Write a JOIN SQL query and map the result into `OrderSummaryDto`.

### Exercise 4 — Aggregate Data from a Child Collection

1. Add an `order_lines` table.
2. Create a query counting lines and summing totals per order.
3. Map the result into a DTO with `lineCount` and `totalAmount`.
4. Compare the reporting DTO with a closed projection that only reads root properties.

### Exercise 5 — Compare Costs

1. Seed test data with many orders and order lines.
2. Read the list using the aggregate root.
3. Read it again using a closed projection.
4. Read the report using a JOIN DTO.
5. Record the SQL, row counts, timing, and amount of returned data.

## 15. Conclusion

**Closed interface projections** declare a set of getters corresponding to known properties of the aggregate. Spring Data can determine the requested properties in advance and optimize the selected columns in supported queries. Getter names are based on **Java properties**, while `@Column` and the naming strategy map those properties to database column names.

Keep projections small and tailored per use case so code stays clear and avoids requesting unnecessary data. Default methods can compute simple values from closed accessors; SpEL expressions create open projections and lose the same selected-property optimization advantage.

A projection is a read view, not an aggregate for updates. When you need to JOIN another aggregate, compute totals from child collections, or build reports, use custom SQL and an appropriate DTO/read model. When business changes are needed, load the aggregate root, enforce invariants, and save through the repository.

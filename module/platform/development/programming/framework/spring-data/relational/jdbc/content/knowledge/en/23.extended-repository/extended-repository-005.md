# Writing JOIN Queries and Custom Write Commands in Fragments

In **Spring Data Relational JDBC**, repository fragments let you extend a repository with operations that basic CRUD or derived queries cannot conveniently express. A fragment can contain a JOIN query to build read data from multiple tables, or a specialized write command that requires precise control over update conditions, affected row counts, and concurrency behavior.

For example, a product catalog screen needs the category name alongside the product name and price. This is read data combined from the product and category tables, making it a good fit for a projection. Another use case needs to deduct stock only when sufficient quantity is available and the version still matches. This is a conditional write command that must execute atomically to prevent two concurrent requests from over-reserving inventory.

Spring Data JDBC lets you combine these operations in a **repository fragment** implemented using Spring JDBC, such as `NamedParameterJdbcTemplate`, `JdbcTemplate`, or `JdbcClient`. The fragment keeps the query API alongside the repository, while the implementation controls the SQL and result mapping.

## 1. What Problems Do Repository Fragments Solve?

A standard repository typically extends `CrudRepository` or `ListCrudRepository` to provide CRUD operations. Derived queries work well for simple predicates, while `@Query` fits fixed SQL statements. When a query or write command needs richer logic, a dedicated fragment separates that logic from the main repository interface.

Commonly suitable cases:

- Multi-table JOINs to construct DTOs or projections.
- Optional filters requiring per-request SQL assembly.
- Dynamic sorting against a list of allowed columns.
- `UPDATE` statements with business predicates and optimistic locking.
- `INSERT`/`UPSERT` depending on database-specific syntax.
- An operation that executes multiple SQL statements and maps custom results.
- Queries requiring a `RowMapper` to transform each row into a specific Java structure.

Model:

~~~text
ProductRepository
    |
    +-- CrudRepository<Product, Long>
    |
    +-- ProductCatalogOperations
              |
              v
      ProductCatalogOperationsImpl
              |
              +-- NamedParameterJdbcTemplate
              |
              v
           Database
~~~

The main repository provides CRUD; the fragment adds specialized query or write behaviors. Do not create a fragment merely to wrap an already-available CRUD method.

## 2. Declaring a Fragment and Composing It into a Repository

Suppose an application has a `Product` entity and needs catalog read operations as well as stock reservation.

### 2.1. Fragment Interface

~~~java
import java.util.List;

public interface ProductCatalogOperations {

    List<ProductCatalogItem> searchCatalog(ProductCatalogFilter filter);

    int reserveStock(Long productId, int quantity, Long expectedVersion);
}
~~~

The fragment interface declares the contract that services can call. It contains no SQL or JDBC details.

DTO and filter:

~~~java
import java.math.BigDecimal;

public record ProductCatalogItem(
        Long productId,
        String sku,
        String productName,
        String categoryName,
        BigDecimal price,
        Integer availableQuantity
) {
}
~~~

~~~java
public enum ProductCatalogSort {
    NEWEST,
    NAME,
    PRICE_ASC,
    PRICE_DESC
}
~~~

~~~java
public record ProductCatalogFilter(
        Long categoryId,
        String status,
        String keyword,
        ProductCatalogSort sort,
        int limit,
        long offset
) {
}
~~~

### 2.2. Composing the Fragment into the Main Repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, ProductCatalogOperations {

    Optional<Product> findBySku(String sku);
}
~~~

The repository inherits both the CRUD contract and the fragment contract. Services can invoke `searchCatalog` or `reserveStock` through the same `ProductRepository` bean.

### 2.3. Implementation Naming Convention

For the `ProductCatalogOperations` fragment, the implementation under the default convention is:

~~~java
public class ProductCatalogOperationsImpl
        implements ProductCatalogOperations {
    // custom JDBC implementation
}
~~~

Spring Data repository composition locates the fragment's implementation using the interface name and the default `Impl` postfix. If the project configures a different postfix, the class name must follow that configuration. Place the implementation in a package scanned by repository scanning.

You can annotate the implementation with `@Repository` to denote its persistence role and participate in Spring's exception translation mechanism:

~~~java
@Repository
public class ProductCatalogOperationsImpl
        implements ProductCatalogOperations {
    // ...
}
~~~

With modern repository composition, each fragment has its own interface to separate behavior groups and allow combining multiple fragments. Do not confuse it with the legacy naming approach that binds a single implementation to the entire repository.

## 3. Example Schema for JOIN Queries and Write Commands

Suppose the catalog has two tables:

~~~sql
CREATE TABLE category (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    category_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL,
    price DECIMAL(19, 2) NOT NULL,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES category(id),
    CONSTRAINT ck_product_quantity
        CHECK (available_quantity >= 0)
);

CREATE INDEX idx_product_category_status
    ON product(category_id, status);
~~~

This is an illustrative schema; ID generation syntax must be adapted to your application's database. The `version` column is used to detect concurrent updates. `available_quantity` is additionally protected by a CHECK constraint so the database never stores a negative quantity.

The root entity can use `@Version`:

~~~java
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        @Version Long version,
        Long categoryId,
        String sku,
        String name,
        String status,
        BigDecimal price,
        Integer availableQuantity,
        LocalDateTime createdAt
) {
}
~~~

`@Version` lets Spring Data JDBC manage optimistic locking when saving aggregates through standard repository methods. A custom SQL command inside a fragment does not automatically pass through the full save pipeline; if that command requires a version check, the implementation must include the version predicate and increment the version in SQL.

## 4. Using NamedParameterJdbcTemplate in a Fragment

`NamedParameterJdbcTemplate` lets you bind parameters by name instead of positional question marks. It fits SQL with multiple conditions and is configured by Spring based on the application's `DataSource`.

~~~java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductCatalogOperationsImpl
        implements ProductCatalogOperations {

    private final NamedParameterJdbcTemplate jdbc;

    public ProductCatalogOperationsImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    // Implement fragment methods.
}
~~~

Constructor injection keeps dependencies explicit and easy to substitute in tests. Never open connections manually with `DriverManager`, and do not create a separate `DataSource` for the fragment. Use the Spring-managed template so SQL statements share the datasource and can participate in the current transaction.

`JdbcClient` is another option starting in Spring Framework 6.1, offering a fluent API for queries/updates. For applications on older versions, `NamedParameterJdbcTemplate` remains widely used and broadly compatible.

## 5. Writing a JOIN Query to Return a Projection

A catalog screen needs data from both products and categories. Because the result is not a complete `Product` aggregate, the fragment should return a read DTO.

### 5.1. SQL JOIN

~~~sql
SELECT
    p.id AS product_id,
    p.sku AS sku,
    p.name AS product_name,
    c.name AS category_name,
    p.price AS price,
    p.available_quantity AS available_quantity
FROM product p
JOIN category c ON c.id = p.category_id
WHERE p.status = :status
ORDER BY p.created_at DESC, p.id DESC;
~~~

Aliases disambiguate columns from different tables and align column labels with `ProductCatalogItem` components. For example, `p.id AS product_id` corresponds to `productId` under standard snake_case naming.

### 5.2. RowMapper Converting ResultSet to DTO

In the implementation:

~~~java
private static final RowMapper<ProductCatalogItem> CATALOG_ROW_MAPPER =
        (rs, rowNum) -> new ProductCatalogItem(
                rs.getLong("product_id"),
                rs.getString("sku"),
                rs.getString("product_name"),
                rs.getString("category_name"),
                rs.getBigDecimal("price"),
                rs.getInt("available_quantity")
        );
~~~

`RowMapper` explicitly specifies which column label maps to which component. Use getters matching the SQL types: `getBigDecimal` for DECIMAL, `getString` for strings, and numeric getters for numeric types. If a column is nullable, use wrapper types and check for nulls properly; for primitive getters like `getInt`, JDBC returns 0 for SQL NULL, so call `wasNull()` immediately after the getter if you need to distinguish them.

### 5.3. Adding Optional Filters

You can assemble the SQL query based on populated filter fields:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Override
public List<ProductCatalogItem> searchCatalog(
        ProductCatalogFilter filter
) {
    validate(filter);

    StringBuilder sql = new StringBuilder("""
            SELECT
                p.id AS product_id,
                p.sku AS sku,
                p.name AS product_name,
                c.name AS category_name,
                p.price AS price,
                p.available_quantity AS available_quantity
            FROM product p
            JOIN category c ON c.id = p.category_id
            WHERE 1 = 1
            """);

    MapSqlParameterSource params = new MapSqlParameterSource();

    if (filter.categoryId() != null) {
        sql.append(" AND p.category_id = :categoryId");
        params.addValue("categoryId", filter.categoryId());
    }

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND p.status = :status");
        params.addValue("status", filter.status().trim());
    }

    if (filter.keyword() != null && !filter.keyword().isBlank()) {
        sql.append(" AND (p.sku LIKE :keyword OR p.name LIKE :keyword)");
        params.addValue(
                "keyword",
                "%" + filter.keyword().trim() + "%"
        );
    }

    String orderBy = switch (filter.sort() == null
            ? ProductCatalogSort.NEWEST : filter.sort()) {
        case NEWEST -> "p.created_at DESC, p.id DESC";
        case NAME -> "p.name ASC, p.id ASC";
        case PRICE_ASC -> "p.price ASC, p.id ASC";
        case PRICE_DESC -> "p.price DESC, p.id DESC";
    };

    sql.append(" ORDER BY ").append(orderBy);
    sql.append(" LIMIT :limit OFFSET :offset");
    params.addValue("limit", filter.limit());
    params.addValue("offset", filter.offset());

    return jdbc.query(sql.toString(), params, CATALOG_ROW_MAPPER);
}
~~~

The example uses `LIMIT/OFFSET` syntax supported by PostgreSQL, MySQL, and several other databases. If the application supports a database with a different pagination syntax, isolate the row-limiting clause by dialect or adjust it for the target database.

### 5.4. Validating Filters Before Building SQL

~~~java
private void validate(ProductCatalogFilter filter) {
    if (filter == null) {
        throw new IllegalArgumentException("Filter must not be null");
    }
    if (filter.limit() < 1 || filter.limit() > 100) {
        throw new IllegalArgumentException("limit must be between 1 and 100");
    }
    if (filter.offset() < 0) {
        throw new IllegalArgumentException("offset must not be negative");
    }
}
~~~

Dynamic conditions need clear semantics:

- Null filter field: skip the corresponding predicate if that is the API convention.
- Empty or whitespace-only string: typically normalized to unapplied.
- Malformed values: reject before querying.
- Sort: select from an enum/whitelist; never concatenate strings sent by the request.
- Limit/offset: enforce bounds to prevent overly large queries.

When searching for literal text, escape `%` and `_` wildcards according to database syntax; the simple example above allows them to act as LIKE wildcards.

### 5.5. Never Concatenate Input into SQL

Values must be bound:

~~~java
sql.append(" AND p.status = :status");
params.addValue("status", filter.status());
~~~

Do not write:

~~~java
sql.append(" AND p.status = '")
   .append(filter.status())
   .append("'");
~~~

Parameter binding prevents input values from being interpreted as SQL syntax. Column names and sort directions cannot be bound as values; map them from an enum or a fixed list of identifiers as in the switch above.

### 5.6. Why Should JOIN Queries Return a DTO Instead of Product?

A join query can return columns from multiple tables. Mapping that result directly into an aggregate root can create the false impression that `Category` is owned by `Product` or omit collections belonging to the aggregate. `ProductCatalogItem` is a read projection and accurately conveys its purpose: combined data for display.

For product updates, services should still load the `Product` root through the standard repository, invoke domain behavior, and save the root. Never treat a join DTO as an entity to pass to `save`.

## 6. Custom Write Command: Conditional Inventory Update

A classic example of a custom write is stock reservation. Requirements:

- Requested quantity must be greater than 0.
- Available stock must be sufficient.
- Version must match the snapshot read by the caller.
- If successful, decrement stock and increment version in the same SQL statement.

### 6.1. Why Not Read Then Update in Two Steps?

Naive approach:

~~~text
SELECT available_quantity
if available_quantity >= requested:
    UPDATE available_quantity = available_quantity - requested
~~~

Two requests could both read an inventory of 5 and each try to reserve 4. Both pass the check before updating; without proper concurrency conditions, inventory could become negative or get overwritten.

Instead, put the conditions directly into the UPDATE statement:

~~~sql
UPDATE product
SET available_quantity = available_quantity - :quantity,
    version = version + 1
WHERE id = :productId
  AND available_quantity >= :quantity
  AND version = :expectedVersion;
~~~

The database evaluates the conditions and modifies the row in one atomic operation. Only one request using the same version can succeed; the other no longer matches the version or quantity condition.

### 6.2. Implementing the Method in the Fragment

~~~java
@Override
public int reserveStock(
        Long productId,
        int quantity,
        Long expectedVersion
) {
    if (productId == null) {
        throw new IllegalArgumentException("productId must not be null");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be greater than 0");
    }
    if (expectedVersion == null || expectedVersion < 0) {
        throw new IllegalArgumentException("expectedVersion is invalid");
    }

    String sql = """
            UPDATE product
            SET available_quantity = available_quantity - :quantity,
                version = version + 1
            WHERE id = :productId
              AND available_quantity >= :quantity
              AND version = :expectedVersion
            """;

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("productId", productId)
            .addValue("quantity", quantity)
            .addValue("expectedVersion", expectedVersion);

    return jdbc.update(sql, params);
}
~~~

The return value is the number of affected rows:

- `1`: the product was updated.
- `0`: no row satisfied all conditions, either because the ID does not exist, stock is insufficient, or the version has changed.

Because `id` is the primary key, an update by ID cannot affect multiple rows. If the result is greater than 1, the schema/conditions or key assumptions need investigation.

### 6.3. Handling the Result in a Service

~~~java
@Service
public class InventoryService {

    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void reserve(
            Long productId,
            int quantity,
            Long expectedVersion
    ) {
        int updated = products.reserveStock(
                productId,
                quantity,
                expectedVersion
        );

        if (updated == 0) {
            throw new StockReservationRejectedException(productId);
        }
        if (updated != 1) {
            throw new IllegalStateException(
                    "Unexpected number of updated rows"
            );
        }
    }
}
~~~

The service uses a Spring transaction. A single UPDATE statement is already atomic in the database; a service-level transaction becomes useful when the use case coordinates additional writes, such as writing an outbox record or creating a reservation record in the same transaction.

If you need to distinguish accurately between "product not found," "insufficient stock," and "stale version," the service can re-read state after the update returns 0. That classification is a post-failure read and can itself experience subsequent race conditions; do not treat it as an absolute failure reason if state continues changing.

### 6.4. Custom SQL Must Maintain Optimistic Locking Manually

With standard repository saves, Spring Data JDBC uses `@Version` to check and increment the version on update. A `jdbc.update` call in a fragment does not automatically run through that optimistic locking mechanism.

If a custom command requires a version check, the SQL must:

1. Compare the current version against `expectedVersion`.
2. Update only when the version matches.
3. Increment the version in the same statement.
4. Check the affected row count.

Do not increment the version in Java and assume the database detected contention. The `WHERE version = :expectedVersion` clause is what detects a stale snapshot.

## 7. Other Specialized Write Commands

Fragments are not just for UPDATEs. They can encapsulate INSERT, DELETE, or UPSERT operations when there is a clear reason.

### 7.1. Conditional Status UPDATE

~~~sql
UPDATE purchase_order
SET status = :newStatus,
    version = version + 1
WHERE id = :orderId
  AND status = :expectedStatus
  AND version = :expectedVersion;
~~~

This statement transitions status only if the order is still in the state the caller expected. It works well for conditional state transitions, provided other order invariants have also been verified.

### 7.2. Conditional DELETE

~~~sql
DELETE FROM product
WHERE id = :productId
  AND status = 'DISCONTINUED';
~~~

The method can return the deleted row count so the service knows whether the condition matched. However, deleting directly from a root table bypasses Spring Data JDBC's child row management and may be rejected by foreign keys. If you need to delete an aggregate with owned collections, prefer `repository.deleteById` or a deletion mechanism designed for the entire aggregate.

Do not add `ON DELETE CASCADE` just to make the statement succeed if deleting child rows could destroy required history or data.

### 7.3. INSERT with Generated Keys

If a write operation needs specialized SQL, Spring JDBC can use `KeyHolder` to retrieve generated keys. Conceptual example:

~~~java
GeneratedKeyHolder keyHolder = new GeneratedKeyHolder();

jdbc.update(
        """
        INSERT INTO audit_entry(event_type, aggregate_id, created_at)
        VALUES (:eventType, :aggregateId, :createdAt)
        """,
        new MapSqlParameterSource()
                .addValue("eventType", eventType)
                .addValue("aggregateId", aggregateId)
                .addValue("createdAt", createdAt),
        keyHolder,
        new String[] {"id"}
);
~~~

Generated key retrieval depends on the driver and how generated column names are specified. If creating a standard aggregate root, `repository.save` is usually better because Spring Data JDBC manages IDs, versions, and aggregate mapping.

### 7.4. Database-Specific UPSERT

PostgreSQL supports `INSERT ... ON CONFLICT`; SQL Server/Oracle and other engines have different syntax or semantics. PostgreSQL example:

~~~sql
INSERT INTO product_price(product_id, price, updated_at)
VALUES (:productId, :price, :updatedAt)
ON CONFLICT (product_id)
DO UPDATE SET
    price = EXCLUDED.price,
    updated_at = EXCLUDED.updated_at;
~~~

This is dialect-specific SQL. If the application supports multiple databases, isolate implementations by dialect or choose a more portable approach. Also decide whether UPSERT is allowed to overwrite regardless of version or must check business conditions first.

## 8. When to Use a Fragment Instead of @Query and @Modifying?

`@Query` combined with `@Modifying` works well for short, fixed statements with simple contracts:

~~~java
@Modifying
@Query("""
       UPDATE product
       SET status = :status
       WHERE id = :id
       """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

A fragment is a better fit when:

- An operation requires SQL dynamically assembled from multiple optional filters.
- It needs JOINs and a dedicated `RowMapper`.
- It needs dynamic identifier whitelisting.
- Multiple SQL statements must execute within one method.
- Fine control over generated keys or specialized update outcomes is needed.
- A group of specialized queries should be packaged into a clearly named API.

Not every piece of SQL requires a fragment. Pick the simplest approach that keeps intent and mapping clear.

## 9. Transactions and JDBC Connections

Custom fragments should use a Spring-managed `NamedParameterJdbcTemplate`, `JdbcTemplate`, or `JdbcClient`. When the template uses the same `DataSource` and transaction manager as the repository, JDBC statements can participate in the active Spring transaction.

Example coordinating a stock update and an outbox write:

~~~java
@Transactional
public void reserveAndRecord(
        Long productId,
        int quantity,
        Long expectedVersion
) {
    int updated = productRepository.reserveStock(
            productId,
            quantity,
            expectedVersion
    );

    if (updated != 1) {
        throw new StockReservationRejectedException(productId);
    }

    outboxRepository.insertStockReserved(productId, quantity);
}
~~~

If writing to the outbox fails, the transaction can roll back the stock update as well. This holds only when both operations participate in the same transaction manager/datasource. If the outbox resides in a different database, a local `@Transactional` does not create a distributed transaction.

### 9.1. Never Open Connections Manually

Avoid calling `DriverManager.getConnection` in a fragment. A manually opened connection is not managed by Spring under the current transaction, causing statements to commit independently or bypass the connection pool. Inject the Spring-configured template via constructor.

### 9.2. Transaction Boundaries in the Service

Fragments should focus on SQL queries and commands. The service defines use case boundaries:

- `@Transactional(readOnly = true)` for read flows needing a transaction.
- `@Transactional` for use cases coordinating multiple write operations.
- Explicit isolation levels when business logic demands specific consistency guarantees.

`readOnly = true` is a hint/intent for transaction infrastructure, not an authorization mechanism, and does not guarantee every database rejects writes.

## 10. Aggregate Boundaries and Custom Write Responsibilities

A fragment using direct SQL can bypass behaviors that standard aggregate repositories perform. Before using a custom write, identify what the command modifies:

- An auxiliary table for search/reporting.
- A technical table such as an outbox or audit log.
- A single attribute of an aggregate root.
- Multiple aggregates or child collections.

If updating an aggregate root, the SQL must preserve the aggregate's invariants. If modifying child collections, foreign keys, ordering, and full ownership rules must be respected. If the operation touches multiple aggregates, define transactions or eventual consistency accordingly.

### 10.1. What Custom SQL Does Not Do Automatically

A `jdbc.update` statement does not automatically:

- Load the aggregate and invoke domain methods.
- Enforce invariants in constructors or domain models.
- Run the full `repository.save` lifecycle.
- Increment `@Version` according to Spring Data JDBC rules.
- Publish domain events or write outbox records.
- Synchronize Java objects currently held in memory.
- Manage child collections like a standard aggregate save.

If these behaviors are needed, implement them explicitly in the service/fragment or use the standard aggregate repository.

### 10.2. When a Custom Write Is a Sound Choice

An operation like "decrement stock if sufficient quantity exists and version matches" is a good fit for atomic SQL because the main goal is ensuring the condition is evaluated at the database in the same operation. The service must still validate inputs, classify outcomes, and publish events/outbox records if business rules require them.

## 11. Security and Correctness of Dynamic SQL

### 11.1. Bind Every Value

Use named parameters:

~~~java
params.addValue("categoryId", filter.categoryId());
~~~

Never concatenate request values into SQL strings. Parameter binding protects values from being interpreted as SQL syntax.

### 11.2. Whitelist Column Names and Sort Directions

Column names, table names, and `ASC`/`DESC` keywords are not ordinary bound values. Select them from enums or constants:

~~~java
String orderBy = switch (sort) {
    case NAME -> "p.name ASC, p.id ASC";
    case PRICE_ASC -> "p.price ASC, p.id ASC";
    case NEWEST -> "p.created_at DESC, p.id DESC";
};
~~~

Never concatenate `request.sortBy()` directly into SQL.

### 11.3. Validate Inputs

Check:

- Required IDs and positive quantities.
- Limit/offset within allowed bounds.
- Collection filters not overly large.
- Strings normalized per business rules.
- Sort fields contained in the whitelist.
- Status transitions within valid sets.

Parameter binding does not replace validation and authorization.

## 12. Testing Repository Fragments

Custom SQL needs integration tests against an appropriate database. Unit tests can verify validation and filter assembly, but they do not prove JOINs, constraints, transactions, or dialects behave correctly.

### 12.1. Testing JOINs

Set up:

- A category with a known name.
- A product pointing to that category.
- A product belonging to a different category.

Verify:

- `categoryName` comes accurately from the category table.
- Aliases `product_id`, `product_name`, and `category_name` map properly.
- Status/category/keyword filters apply accurately.
- Empty matches return an empty list.
- Sorting and limits produce deterministic ordering.

### 12.2. Testing Conditional Writes

For `reserveStock`:

| Scenario | Expected Outcome |
| --- | --- |
| Existing ID, matching version, sufficient stock | Updates one row; stock decreases and version increments |
| Insufficient stock | No update; returns 0 rows |
| Stale version | No update; returns 0 rows |
| Non-existent ID | No update; returns 0 rows |
| Zero or negative quantity | Rejected by validation before executing SQL |
| Two requests with the same version | At most one request updates successfully |

Verify state by reading back after the update, not just checking the affected row count.

### 12.3. Testing Transaction Rollback

In the use case updating stock and writing to the outbox:

1. Let the stock update succeed.
2. Force the outbox write to fail.
3. Verify the transaction rolls back and stock returns to its original value.

This test requires the same transaction manager/datasource. If repositories use different databases, test your separate consistency design.

### 12.4. Test Against the Target Database

If SQL uses `LIMIT`, `ON CONFLICT`, `RETURNING`, JSON functions, or vendor-specific syntax, run tests against the real production database engine or corresponding Testcontainers. H2 does not prove identical syntax or locking behavior to PostgreSQL, MySQL, or SQL Server.

### 12.5. Inspect SQL and Execution Plans

When a JOIN query is slow:

- Check whether JOIN conditions use proper keys/indexes.
- Check indexes on filter and sort columns.
- Inspect intermediate row counts produced by the JOIN.
- Verify the projection does not select unnecessary columns.
- Use the database's execution plan.

Do not add indexes based solely on column names; base them on actual queries and execution plans.

## 13. Common Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Misnaming the fragment implementation | Spring Data fails to compose the implementation | Use fragment interface name + configured postfix |
| Putting all SQL into the repository interface | Bloated interface, hard to separate concerns | Use dedicated fragments |
| Treating a JOIN projection as an aggregate root | Incomplete read data or confused ownership | Return DTO/read model |
| Omitting aliases on JOIN columns | Duplicate labels or mis-mapped columns | Use explicit, meaningful aliases |
| Concatenating inputs into SQL | SQL injection | Use named parameters |
| Concatenating sort fields from requests | Unsafe SQL identifiers | Use an enum/whitelist |
| Opening JDBC connections manually | Bypasses Spring transactions and connection pool | Inject Spring-managed template |
| Updating stock via separate SELECT then UPDATE | Race conditions under concurrent requests | Single conditional UPDATE in WHERE |
| Custom UPDATE ignores version | Overwrites newer data | Compare and increment version in SQL |
| Checking only exceptions without affected rows | Unknown whether the statement updated anything | Return and check affected row count |
| Deleting root with children directly | FK violations or bypassed aggregate lifecycle | Use repository delete or full aggregate deletion design |
| Assuming fragments run domain callbacks automatically | Skips invariants/auditing/events | Invoke domain behavior or implement needed steps explicitly |
| Testing only on H2 | Dialect/locking differences go undetected | Test on the target database |

## 14. Fragment Implementation Workflow

When adding a JOIN query or custom write command:

1. **Identify purpose:** reading a projection, modifying an aggregate, or writing technical data?
2. **Design fragment contract:** name methods and return types to clearly reflect outcomes.
3. **Create fragment interface:** declare only the API services need.
4. **Create implementation by convention:** inject `NamedParameterJdbcTemplate`, `JdbcTemplate`, or `JdbcClient`.
5. **Write SQL with aliases and bound parameters:** select explicit columns, use stable aliases, bind every value.
6. **Map results:** use DTOs and `RowMapper` when JOINs produce a custom result shape.
7. **Guard writes:** validate inputs, encode predicates in SQL, check affected rows, and handle version if needed.
8. **Define transactions:** ensure coordinated operations share the right datasource/transaction manager.
9. **Respect aggregate boundaries:** never turn a projection into a writable entity or bypass root invariants.
10. **Integration test:** verify JOINs, nulls, empty results, concurrency, rollbacks, and the target dialect.

## Key Takeaways

Repository fragments are the right place for JOIN queries and custom write commands when CRUD, derived queries, or a simple `@Query` are no longer clear enough. Use `NamedParameterJdbcTemplate` to bind values, `RowMapper` to transform JOIN results into DTOs, and whitelists for dynamic identifiers.

For conditional writes, place critical business predicates directly in the SQL and check affected row counts. If optimistic locking is needed, compare and increment the version in the custom statement. Fragments use templates sharing the datasource to participate in Spring transactions, but custom SQL does not automatically execute the full lifecycle of an aggregate repository. Keep a clear boundary between read projections and writable aggregates, and test on the target database to verify SQL, mapping, concurrency, and rollback.

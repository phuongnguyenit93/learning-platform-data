# Declaring @Query with Database SQL

In **Spring Data Relational JDBC**, repositories can derive queries from method names, but there are business cases that require specific SQL: joining multiple tables to build read data, using database-specific functions, controlling filter conditions, sorting, pagination, or executing an intentional update statement. The **`@Query`** annotation allows declaring a SQL statement directly on a repository method.

Unlike JPA's JPQL, SQL in Spring Data JDBC's `@Query` operates against **database table names, column names, and SQL syntax**. Spring Data JDBC prepares the statement, binds parameters, and maps the results according to the method's return type. Therefore, the author must understand the schema, data types, result cardinality, and mapping limitations.

This lesson covers how to declare `@Query`, bind parameters safely, map results, use `@Modifying` for data-changing statements, coordinate transactions, handle differences across databases, and test custom SQL.

## 1. When do you need @Query?

Spring Data JDBC supports derived query methods generated from method names:

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByStatusOrderByCreatedAtDesc(String status);
~~~

For simple queries, derived queries keep code concise and readable. However, a method name cannot always express the exact SQL that needs to run.

Common cases for using `@Query`:

- Needing to join tables to produce a read result.
- Needing database-specific SQL functions or operators.
- Needing computed expressions, aggregate functions, or subqueries.
- Needing precise control over `WHERE`, `ORDER BY`, and `GROUP BY` conditions.
- Needing CTEs or advanced SQL syntax that derived queries cannot express.
- Needing a specific update/delete statement via `@Modifying`.

For example, fetching a product by SKU:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE sku = :sku
       """)
Optional<Product> findBySkuWithSql(@Param("sku") String sku);
~~~

This is real SQL running on the database. `product` is the table name; `price_minor_units` is the column name. Spring Data JDBC does not translate `product` into a Java entity name as JPQL does.

## 2. Correct annotation and package

When using Spring Data JDBC, import `@Query` from this package:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
~~~

For data-modifying statements, the corresponding annotation is:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
~~~

Do not confuse it with Spring Data JPA's `@Query`:

~~~java
// Spring Data JDBC:
import org.springframework.data.jdbc.repository.query.Query;

// Do not use the JPA annotation for a Spring Data JDBC repository:
// import org.springframework.data.jpa.repository.Query;
~~~

The two annotations share the same name but belong to two different persistence mechanisms. Spring Data JDBC declares SQL; Spring Data JPA can declare JPQL or native SQL depending on usage. Bringing the JPA import into a JDBC repository may prevent the framework from recognizing the annotation as expected.

## 3. Declaring a repository method with @Query

A repository can extend `CrudRepository` and declare additional query methods:

~~~java
import java.util.Optional;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    @Query("""
           SELECT id, sku, name, price_minor_units
           FROM product
           WHERE sku = :sku
           """)
    Optional<Product> findBySkuWithSql(@Param("sku") String sku);
}
~~~

Components:

- `@Query` contains the SQL statement to execute.
- `:sku` is a named parameter in SQL.
- `@Param("sku")` binds the Java parameter to the placeholder.
- `Optional<Product>` represents at most one result that may not exist.

Java text blocks `""" ... """` make multi-line SQL easier to read (an official feature since Java 15). If using an older Java version, you can use regular strings with appropriate line concatenation.

### 3.1. Choosing the return type by row cardinality

| Return type | Meaning |
| --- | --- |
| `Product` | Expects exactly one result; if there are zero or more than one result, the framework handles it according to the single-query contract and may throw an exception |
| `Optional<Product>` | At most one result; empty Optional if no row is found |
| `List<Product>` | Multiple results; empty list if no row is found |
| `Collection<Product>` / `Iterable<Product>` | General collection of results |
| Scalar types such as `Long`, `Integer`, `String` | A single value selected from the SQL result, when the return type and column are compatible |
| Projection/DTO | A subset of columns mapped according to projection and mapping rules supported by the Spring Data JDBC version |

The return type is part of a query method's contract. If the SQL can return multiple rows, do not declare `Optional<Product>` just because current data happens to have no duplicates.

### 3.2. Empty results

With a method returning Optional:

~~~java
Optional<Product> findBySkuWithSql("UNKNOWN-SKU");
~~~

If the query executes successfully and matches no rows, the result is `Optional.empty()`. If the method returns a List, the result is an empty list.

Do not catch connection errors or SQL errors and convert them into an empty Optional. "No data found" is different from "unable to query data".

## 4. Binding parameters with named parameters

Custom SQL must pass input data through bind parameters, never by concatenating values directly into the SQL string.

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY price_minor_units DESC
       """)
List<Product> findAvailableProducts(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

The `:status` placeholder is bound to the `status` parameter; `:minimumPrice` is bound to the `minimumPrice` parameter.

Advantages of named parameters:

- SQL is easier to read when there are many parameters.
- Does not depend on the positional order of question marks in the statement.
- Lower risk of swapping bind order when adding new parameters.
- Values are passed as data and do not become part of the SQL syntax.

### 4.1. Using @Param explicitly

Use `@Param` when you want an explicit parameter contract:

~~~java
@Query("SELECT * FROM product WHERE sku = :sku")
Optional<Product> findProduct(@Param("sku") String sku);
~~~

Some Spring Data setups can obtain parameter names from Java compilation metadata when `-parameters` is enabled. However, `@Param` avoids depending on that compiler setting and directly shows the relationship between the SQL placeholder and the method parameter.

### 4.2. Do not concatenate input into SQL strings

Do not write:

~~~java
String sql = "SELECT * FROM product WHERE sku = '" + sku + "'";
~~~

If `sku` contains quotes or data intentionally crafted to break syntax, the SQL statement can be altered. This is a source of SQL injection.

Write instead:

~~~java
@Query("SELECT * FROM product WHERE sku = :sku")
Optional<Product> findBySku(@Param("sku") String sku);
~~~

Parameter binding protects input values from being interpreted as SQL syntax. It does not replace access-control checks, business validation, or controlling dynamic column/table names.

### 4.3. Parameters cannot replace table or column names

Bind parameters are for **values**, not SQL identifiers:

~~~sql
SELECT * FROM :tableName
~~~

Databases generally do not allow using a parameter as a table name or column name. If you need to choose a sort column dynamically, map the input to a list of allowed identifiers and then build the SQL in a controlled way or choose separate query methods. Never concatenate column names directly from a request.

### 4.4. Null parameters

When a parameter can be null, you must clarify the intended SQL semantics. The condition:

~~~sql
WHERE category = :category
~~~

does not automatically mean "if category is null, ignore the filter". Comparing with NULL in SQL evaluates to UNKNOWN, not TRUE.

If you want an optional filter:

~~~sql
WHERE (:category IS NULL OR category = :category)
~~~

The placeholder type and null binding behavior must be compatible with the driver/database. For complex queries, you can create separate methods or use `JdbcClient` to build the query with controlled conditions.

## 5. Using @Query with filtering, sorting, and limiting results

Custom SQL gives direct control over conditions:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units BETWEEN :minimum AND :maximum
       ORDER BY name ASC, id ASC
       """)
List<Product> findByPriceRange(
        @Param("status") String status,
        @Param("minimum") long minimum,
        @Param("maximum") long maximum
);
~~~

`ORDER BY name, id` produces a more deterministic order than sorting by name alone, because multiple products can share the same name. A stable order is especially useful for pagination or batch processing.

### 5.1. LIMIT and OFFSET depend on the database

Some databases support:

~~~sql
SELECT id, sku, name
FROM product
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

Other databases may use `FETCH FIRST ... ROWS ONLY`, `OFFSET ... FETCH`, or vendor-specific syntax. Because `@Query` holds raw SQL, do not assume a single row-limiting query runs identically across all database management systems.

### 5.2. Pagination and total record count

When an API needs a page of data along with the total element count, two queries are usually needed:

~~~sql
SELECT id, sku, name
FROM product
WHERE status = :status
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

~~~sql
SELECT COUNT(*)
FROM product
WHERE status = :status;
~~~

One query to fetch the page data and one query to count the total can be declared as two methods. Direct integration with `Page<T>` or `Slice<T>` depends on the query API and the Spring Data JDBC version in use; if no suitable paging contract exists, you can return a DTO containing content and total assembled in the service.

For large tables, a high `OFFSET` can be expensive because the database has to skip many rows. Keyset pagination based on the last sort key can be more efficient:

~~~sql
SELECT id, sku, name
FROM product
WHERE id > :lastSeenId
ORDER BY id
FETCH FIRST :pageSize ROWS ONLY;
~~~

Row-limiting syntax needs to be adjusted for the database. The `id > :lastSeenId` condition is only appropriate if page ordering is based on ascending ID and ID is a stable key.

## 6. Mapping SQL results to entities

When a method returns an entity, the columns in the result set must provide the data Spring Data JDBC needs to construct the entity according to mapping metadata.

Example entity:

~~~java
@Table("product")
public class Product {
    @Id
    private Long id;

    private String sku;
    private String name;

    @Column("price_minor_units")
    private long priceMinorUnits;

    // constructors and accessors...
}
~~~

Query:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE id = :id
       """)
Optional<Product> findProductRow(@Param("id") Long id);
~~~

Column names and data types must be compatible with the mapping. If the entity has embedded properties, a version field, or other required fields, the query must return all data required by the mapping.

### 6.1. Column aliases for properties

When SQL uses expressions or different column names, aliases clarify the result column names:

~~~sql
SELECT
    p.id,
    p.sku,
    p.price_minor_units AS price_minor_units
FROM product p
WHERE p.id = :id;
~~~

If the result is a DTO/projection whose component names differ from the column names, alias them according to the supported mapping rules. Do not assume every naming strategy automatically infers the right alias from complex expressions.

### 6.2. Avoid SELECT * in long-lived queries

`SELECT *` is convenient during experimentation, but production queries should list columns explicitly:

- Makes it clear what data the method needs.
- Avoids accidentally pulling large or sensitive columns.
- Reduces risk when schema changes add columns with unexpected types.
- Clarifies the contract between SQL and the entity/DTO.
- Makes reviews easier when mappings change.

For entities needing many columns, list all persistent columns. For projections, select only the columns actually needed.

### 6.3. Queries returning an aggregate root with child collections

A `@Query` reading the root table should not be assumed to automatically load all child collections in the same way as the standard aggregate read path. Custom SQL queries must be designed and verified against the mapping contract of the Spring Data JDBC version in use. Especially with joins or multiple rows per root, aggregate construction may behave differently from a query returning a single root row.

If the use case needs the full aggregate to execute domain behavior, consider:

- Using standard repository methods to load the aggregate.
- Using `@Query` to find root IDs, then loading aggregates through the repository by ID.
- Using an appropriate custom query/result mapping when full control over the data is needed.

If the use case only needs reporting or screen data, return a projection/DTO rather than pretending a flat result set is a full aggregate.

## 7. Join queries and projections

An order list screen might need the customer's name, even though customer is an independent aggregate. A SQL join fits a read model well:

~~~sql
SELECT
    po.id AS order_id,
    po.order_number,
    po.status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = :status
ORDER BY po.id DESC;
~~~

The result does not have to be a full `PurchaseOrder`. It is a read structure combining data from two aggregates.

A record DTO can represent that structure:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String status,
        String customerName
) {
}
~~~

When the Spring Data JDBC version and projection type support the corresponding DTO mapping, you can declare a query method returning the projection. If the result shape is complex or requires precise control over row mapping, use `JdbcClient` or `JdbcTemplate` with an explicit `RowMapper`:

~~~java
public List<OrderListItem> findOrderList(String status) {
    return jdbcClient.sql("""
            SELECT
                po.id AS order_id,
                po.order_number,
                po.status,
                c.name AS customer_name
            FROM purchase_order po
            JOIN customer c ON c.id = po.customer_id
            WHERE po.status = :status
            ORDER BY po.id DESC
            """)
        .param("status", status)
        .query((rs, rowNum) -> new OrderListItem(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("status"),
                rs.getString("customer_name")
        ))
        .list();
}
~~~

This example uses `JdbcClient` from Spring Framework 6.1 or later. For older versions, `NamedParameterJdbcTemplate` or `JdbcTemplate` can be an appropriate choice.

Projections avoid loading full aggregates when a screen only needs a few fields. They do not replace aggregate roots in business update flows.

## 8. Querying scalar values and aggregate functions

`@Query` can also be used for non-entity results, if the return type and mapping are supported by the framework version.

Example counting products:

~~~java
@Query("""
       SELECT COUNT(*)
       FROM product
       WHERE status = :status
       """)
long countByStatus(@Param("status") String status);
~~~

When there are no matching products, `COUNT(*)` normally returns one row with the value 0.

Example fetching the minimum price:

~~~java
@Query("""
       SELECT MIN(price_minor_units)
       FROM product
       WHERE status = :status
       """)
Long findMinimumPrice(@Param("status") String status);
~~~

`MIN` can return SQL NULL when no rows match. Use a nullable wrapper type if the mapping allows; if business logic wants a default value, consider `COALESCE`:

~~~sql
SELECT COALESCE(MIN(price_minor_units), 0)
FROM product
WHERE status = :status;
~~~

Do not confuse:

- No result row.
- One row with a SQL NULL column.
- One row with the number 0.

These cases have different contracts.

## 9. Data-modifying statements with @Modifying

`@Query` primarily declares SQL. When a query method executes `UPDATE` or `DELETE`, use `@Modifying` to indicate that it is a data-modifying statement:

~~~java
@Modifying
@Query("""
       UPDATE product
       SET name = :name
       WHERE id = :id
       """)
int updateName(
        @Param("id") Long id,
        @Param("name") String name
);
~~~

An integer return type is commonly used to receive the number of affected rows. `void` can be used if the caller does not need the count, according to the supported contract of the version in use.

### 9.1. Bulk updates

~~~java
@Modifying
@Query("""
       UPDATE product
       SET status = :newStatus
       WHERE status = :oldStatus
       """)
int changeStatusForAll(
        @Param("oldStatus") String oldStatus,
        @Param("newStatus") String newStatus
);
~~~

The method can update multiple rows. The return value indicates the number of rows reported as affected by the database (details depend on the driver/database). Name the method to clearly reflect the scope of the change; a bulk statement can affect multiple aggregates at once.

### 9.2. Deleting data

~~~java
@Modifying
@Query("""
       DELETE FROM product
       WHERE status = :status
       """)
int deleteByStatus(@Param("status") String status);
~~~

Before running a bulk delete statement, determine the conditions, foreign keys, and history policies. Do not use a broad DELETE statement if the data must be retained for auditing or is still referenced by other aggregates.

### 9.3. @Modifying is not repository.save

Direct bulk SQL does not go through the full aggregate persistence lifecycle in the same way as `repository.save(entity)`:

- Does not automatically construct and return the updated aggregate object.
- Does not automatically load and check invariants in the domain model.
- Does not automatically manage child collections according to the aggregate lifecycle.
- Should not be assumed to apply aggregate callbacks/auditing or version rules like a standard save operation.

Use `@Modifying` for intentional SQL operations where the statement and data impact are controlled. If you need to execute business behavior on an aggregate, it is usually better to load the root, invoke the domain behavior, and save via the repository.

### 9.4. Optimistic locking and @Version

If the entity uses `@Version`, a custom `UPDATE` statement does not automatically receive optimistic locking conditions like a repository save operation. To detect conflicts, you must include the version in the condition and update the version manually:

~~~sql
UPDATE product
SET name = :name,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If the affected row count is 0, it could be because the ID does not exist or the version has changed. The service needs to define how to distinguish and handle this appropriately, such as re-reading to classify the error. Do not increment the version in Java and assume the database already locked against contention.

### 9.5. Inserts and generated IDs

A custom INSERT statement can be executed through JDBC APIs, but retrieving generated keys, reconstructing immutable entities, applying aggregate callbacks, and handling child relationships are parts that `repository.save` usually manages better.

If you only need to create an aggregate according to the Spring Data JDBC model, prefer `save`. Only use a custom INSERT when there is a clear requirement and you have explicitly designed key retrieval, transaction control, and invariant maintenance.

## 10. Transactions for query methods

A simple read SQL query can run inside a transaction managed by the framework or calling layer. For multiple operations that need the same commit/rollback boundary, place the transaction at the service boundary:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(Long id, String newName) {
        int updated = repository.updateName(id, newName);
        if (updated != 1) {
            throw new IllegalStateException(
                    "Product not found or data has changed"
            );
        }
    }
}
~~~

This example assumes the repository has the corresponding `updateName` method shown above. `@Transactional` ensures the JDBC operations within the managed scope can commit or roll back according to the transaction manager.

### 10.1. Where to place transactions?

Directly declared query methods should not be assumed to carry the exact same transaction semantics as all inherited CRUD methods. A clear approach is to place `@Transactional` on the service for use cases requiring a transaction, or configure transactions on the method/repository when genuinely needed.

Placing the transaction at the service groups business steps together:

~~~text
Service method @Transactional
   |
   +-- read required data
   +-- validate rules
   +-- call modifying query or repository save
   +-- commit / rollback
~~~

### 10.2. Read-only transactions

For read-only queries:

~~~java
@Transactional(readOnly = true)
public List<Product> search(String status) {
    return repository.findByStatus(status);
}
~~~

`readOnly = true` expresses intent and can provide hints to the transaction manager/database. Do not treat it as an authorization mechanism or a guarantee that every database will reject write statements.

### 10.3. Do not hold transactions during external service calls

If a query method is called inside a transaction, avoid keeping the transaction open while waiting on an HTTP API, sending an email, or processing a large file. Database connections and snapshots/locks may be held for a long time, increasing contention and connection pool wait times.

## 11. Database-dependent SQL

`@Query` contains raw SQL, so syntax and functions can depend on the database.

| Need | PostgreSQL | Some other DBMSs |
| --- | --- | --- |
| Row limiting | `LIMIT ... OFFSET ...` | May use `FETCH FIRST` or `OFFSET ... FETCH` |
| String concatenation | `\|\|` | May use `CONCAT` or another operator |
| JSON | PostgreSQL-specific JSON/JSONB operators and functions | Different JSON types and functions |
| Upsert | `INSERT ... ON CONFLICT ...` | May use `MERGE` or vendor-specific syntax |
| Key generation | `GENERATED ... AS IDENTITY` or sequence | Different identity/sequence syntax |
| Date/time functions | PostgreSQL functions/casts | Different function names, timezone, and data type behavior |

If the application runs against only one database, database-specific SQL can be a reasonable choice. If multiple databases must be supported, you must:

- Keep queries within the common intersection of SQL supported by those databases.
- Separate implementations by dialect/database when syntax differs significantly.
- Use Spring JDBC APIs where parameterization and explicit mapping help.
- Write integration tests against each target database.

No annotation automatically turns vendor-specific SQL into portable SQL.

## 12. CTEs, subqueries, and database functions

One benefit of custom SQL is using syntax that derived queries cannot express.

Subquery example:

~~~sql
SELECT p.id, p.sku, p.name, p.price_minor_units
FROM product p
WHERE p.price_minor_units > (
    SELECT AVG(p2.price_minor_units)
    FROM product p2
    WHERE p2.category_id = :categoryId
)
AND p.category_id = :categoryId;
~~~

CTE example (supported syntax depends on the database):

~~~sql
WITH product_totals AS (
    SELECT category_id, COUNT(*) AS product_count
    FROM product
    GROUP BY category_id
)
SELECT category_id, product_count
FROM product_totals
WHERE product_count >= :minimumCount;
~~~

For aggregate-style queries, the return type should be a projection/DTO rather than a full entity if the result does not represent an aggregate. If `@Query` mapping does not fit the result shape, use `JdbcClient`/`JdbcTemplate` and an explicit row mapper.

## 13. Keeping SQL maintainable

SQL inside an annotation sits right next to the repository method, which is convenient for short queries. When queries grow long or have many variants, keep the structure readable:

- Use text blocks and line breaks per clause.
- Select columns explicitly with consistent aliases.
- Use named parameters and `@Param`.
- Name methods to reflect business intent.
- Avoid a single query with too many optional conditions if it becomes hard to read and optimize.
- Move complex queries to a custom repository/JDBC client when annotations are no longer suitable.

Short query example:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
       ORDER BY id
       """)
List<Product> findAllByStatus(@Param("status") String status);
~~~

For queries with multiple CTEs, dynamic filters, or complex result mappings, a custom repository implementation can separate SQL from the interface and allow clearer mappers and logic.

### 13.1. Do not create a single method for arbitrary dynamic SQL strings

Avoid APIs that accept an entire SQL statement from the caller:

~~~java
List<Product> executeSql(String sql);
~~~

This is a dangerous security and maintainability boundary. Callers could execute unintended SQL. Repository methods should define purposeful queries and bind input values. If dynamic queries are needed, build the query from whitelisted components at the persistence layer—never accept arbitrary raw SQL from a request.

## 14. Testing @Query

Custom SQL must be tested on an appropriate database because a statement can be valid Java syntax yet fail due to wrong column names, data types, dialects, or mappings.

### 14.1. Testing a single result

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void findsProductBySku() {
        // Prepare data using an appropriate schema/test fixture.
        Optional<Product> result =
                repository.findBySkuWithSql("BOOK-021");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getSku())
                .isEqualTo("BOOK-021");
    }
}
~~~

This is an illustrative skeleton; actual tests need appropriate imports/assertions and data setup matching the project schema. `@DataJdbcTest` typically configures a slice test for JDBC repositories; the database used in tests must be compatible with the SQL syntax.

### 14.2. Testing empty results

~~~java
assertThat(repository.findBySkuWithSql("MISSING"))
        .isEmpty();
~~~

Checking the absence contract helps catch cases where a query method accidentally returns the wrong type or has an incorrect SQL filter.

### 14.3. Testing modifying queries

~~~java
int updated = repository.updateName(id, "New Name");

assertThat(updated).isEqualTo(1);
assertThat(repository.findById(id))
        .get()
        .extracting(Product::getName)
        .isEqualTo("New Name");
~~~

Verify both the affected row count and the re-read state. If using a version field, verify the version is updated properly according to the logic implemented by the query.

### 14.4. Use a real database or Testcontainers when needed

H2 can be helpful for fast tests, but it is not always fully compatible with PostgreSQL/MySQL/SQL Server SQL. If a query uses vendor-specific functions, JSON, CTEs, locking, generated columns, or syntax, run integration tests against the target database, for example via Testcontainers.

### 14.5. Observing SQL and execution plans

When a query is slow:

- Inspect the actual SQL statement and bound parameters.
- Check whether indexes support the filter/join conditions.
- Use the database's execution plan.
- Measure the number of rows read versus rows returned.
- Avoid looking only at Java method execution time and assuming the database is the sole cause.

Do not enable logging of sensitive parameter values in production without an appropriate data-protection policy.

## 15. Common mistakes

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Importing `org.springframework.data.jpa.repository.Query` by mistake | Using JPA's annotation in a JDBC repository | Import `org.springframework.data.jdbc.repository.query.Query` |
| Writing JPQL instead of SQL | Spring Data JDBC `@Query` works against the SQL schema | Use database table names, column names, and syntax |
| Concatenating input into SQL strings | SQL injection and escaping bugs | Use named parameters and `@Param` |
| Using a parameter for a table/column name | Bind parameters are only for values | Whitelist identifiers or use separate queries |
| Method returns Optional when query can return multiple rows | Incorrect cardinality contract | Use a collection or enforce a unique constraint |
| Query misses required entity columns | Framework cannot construct the full object | Select all required columns and alias properly |
| Using SELECT * in long-lived queries | Mapping depends on a broad schema and is hard to control | List the required columns explicitly |
| Assuming root @Query automatically loads child collections | Confusing custom SQL with the standard aggregate loading path | Verify mapping; use standard root repository or separate result mapping |
| Using @Modifying but forgetting a transaction | Modifying statement lacks the intended transaction boundary | Place the transaction at the service/method level |
| Assuming @Modifying handles @Version automatically | Bulk SQL does not apply optimistic locking like save | Add the version condition manually and check affected rows |
| Using bulk update to mutate an aggregate while bypassing invariants | SQL bypasses domain behavior | Use repository save or enforce all rules in a custom operation |
| Using vendor-specific SQL while testing only on H2 | Tests do not reflect the production dialect | Test on the target database |
| Catching all exceptions and returning an empty collection | Hides SQL/connection errors | Only represent absence when the query actually succeeds |

## 16. Workflow for designing a @Query method

When custom SQL is needed, follow this sequence:

1. **Identify the query goal.** Is it reading an entity, projection, scalar, or updating/deleting?
2. **Determine cardinality.** Zero rows, at most one, or many rows? Choose Optional, entity, or collection matching the contract.
3. **Write SQL against the real schema.** Use table/column names, joins, and functions matching the target database.
4. **Bind parameters.** Use named parameters and `@Param`; never concatenate values into SQL.
5. **Design result mapping.** Ensure required columns have compatible names and types; use a DTO/RowMapper when the result shape is not an aggregate.
6. **Choose annotations.** Use `@Query` for SQL statements and `@Modifying` when the method modifies data.
7. **Set transaction boundaries.** Define the transaction boundary at the service/method level for the use case.
8. **Check concurrency.** If updating versioned entities, maintain version conditions manually and handle affected row counts.
9. **Test against the right dialect.** Cover data present, no data, multiple results, constraints, and error cases.
10. **Measure performance.** Check execution plans, indexes, row counts, and query timing.

## Key takeaways

`@Query` in Spring Data JDBC allows declaring SQL directly in the database's syntax. Use named parameters to bind values safely, choose return types that match cardinality, and ensure the result set aligns with the entity or projection. For data-modifying statements, use `@Modifying` and manage transactions explicitly; if `@Version` is used, handle optimistic locking conditions in the custom SQL yourself.

Custom SQL provides fine-grained query control, but it also shifts responsibility for schema, dialect, result mapping, and concurrency closer to the author. Keep queries purposeful, test against the target database, and use standard aggregate repositories when the use case needs to load or modify full domain state.

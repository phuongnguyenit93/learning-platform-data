# When You Need Native SQL Instead of JPQL

In Spring Data JPA, JPQL lets you query by Entity and Java properties, whereas native SQL lets you write statements using the actual syntax and structure of the database. Native SQL is useful when a query requires database-specific features, syntax that JPQL cannot express, or fine-grained control over a specific SQL statement to integrate with an existing schema.

However, native SQL makes the application more dependent on the database, table/column names, data types, and dialect. Therefore, you should only choose a native query when its benefits in expressiveness, integration, or performance have been clearly established. For standard CRUD and relationship queries, JPQL is generally easier to maintain and migrate.

## 1. How Do JPQL and Native SQL Differ?

JPQL (Jakarta Persistence Query Language) queries over the Entity model. Names in the query are Entity names and Java properties, not physical table and column names.

JPQL example:

~~~java
@Query("""
    select p
    from Product p
    where p.category.name = :categoryName
    order by p.name
    """)
List<Product> findByCategoryName(
        @Param("categoryName") String categoryName
);
~~~

The query uses the `Product` Entity, along with the `category` and `name` properties. Hibernate translates the JPQL into SQL suitable for the current database.

Native SQL queries tables and columns directly:

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    JOIN categories c ON c.id = p.category_id
    WHERE c.name = ?1
    ORDER BY p.name
    """, nativeQuery = true)
List<Product> findByCategoryNameNative(String categoryName);
~~~

The query uses the `products` and `categories` table names and the `category_id` column. This is actual SQL written for the target database.

| Criterion | JPQL | Native SQL |
|---|---|---|
| Query model | Entities and Java properties | Tables, columns, views, and SQL syntax |
| Portability | Generally higher across databases | Depends on SQL dialect and schema |
| Relationships | Navigates via Entity properties | JOINs using foreign keys and SQL conditions |
| Database-specific features | Limited by standard JPQL/provider | Can be used directly |
| Result mapping | Natural with Entities and projections | Requires ensuring columns/aliases match the return type |
| SQL control | Provider generates SQL | Developer writes SQL |
| Maintenance | Less coupled to physical schema | Must be updated when renaming tables/columns or changing databases |

Native SQL can still be executed through `EntityManager` or a Spring Data Repository. Using a native query does not mean abandoning JPA or rewriting an entire module in JDBC.

## 2. When JPQL Is Enough

For common queries, JPQL is usually the first choice:

- Finding an Entity by properties.
- Filtering by status, dates, or value ranges.
- JOINing mapped relationships.
- Sorting and pagination.
- Using `EXISTS`, subqueries, and aggregate functions supported by JPQL.
- Updating or deleting by simple conditions with a JPQL bulk query.

Example:

~~~java
@Query("""
    select p
    from Product p
    where p.active = true
      and p.price between :minimum and :maximum
    """)
Page<Product> findActiveProductsInPriceRange(
        @Param("minimum") BigDecimal minimum,
        @Param("maximum") BigDecimal maximum,
        Pageable pageable
);
~~~

JPQL lets the provider handle Entity names, mappings, and data types. When switching databases, the application typically requires fewer query changes, though you still need to test differences in data types, collation, functions, and performance.

Do not use native SQL just because an SQL statement looks more familiar. If JPQL expresses the requirement clearly and produces a good execution plan, it is usually the more maintainable choice.

## 3. When You Need SQL Features That Standard JPQL Cannot Express

This is the most common reason to choose a native query. Several SQL features have no equivalent syntax in standard JPQL or depend on provider extensions:

- Common Table Expressions (CTEs) with `WITH`.
- Recursive CTEs to traverse trees or hierarchical structures.
- Window functions such as `ROW_NUMBER()`, `RANK()`, `LAG()`, `LEAD()`.
- Certain JSON operators, JSON paths, or database-specific `JSONB` types.
- Array operators, full-text search operators, or spatial operators.
- Database hints, optimizer directives, and specialized lock syntax.
- UPSERT syntax such as PostgreSQL's `ON CONFLICT` or MySQL's `ON DUPLICATE KEY UPDATE`.
- Querying materialized views or specialized legacy structures.

Example using a window function to rank products by price within each category:

~~~java
@Query(value = """
    SELECT
        p.id AS product_id,
        p.category_id AS category_id,
        p.name AS product_name,
        p.price AS price,
        ROW_NUMBER() OVER (
            PARTITION BY p.category_id
            ORDER BY p.price DESC
        ) AS price_rank
    FROM products p
    """, nativeQuery = true)
List<Object[]> rankProductsByCategory();
~~~

`ROW_NUMBER() OVER (PARTITION BY ...)` is an SQL feature. Standard JPQL has no equivalent window function syntax. The example result consists of rows containing ID, category, name, price, and rank; returning `Object[]` is suitable for demonstration, though not the best choice for a long-term API.

You can use a projection or DTO to give fields clearer names and types.

## 4. When You Need a CTE or Recursive Query

CTEs help break complex queries into named parts. Recursive CTEs can traverse category trees, organizational charts, or parent-child relationships.

PostgreSQL example finding a category along with all its subcategories:

~~~java
@Query(value = """
    WITH RECURSIVE category_tree AS (
        SELECT id, parent_id, name
        FROM categories
        WHERE id = ?1

        UNION ALL

        SELECT child.id, child.parent_id, child.name
        FROM categories child
        JOIN category_tree parent
          ON child.parent_id = parent.id
    )
    SELECT id, parent_id, name
    FROM category_tree
    """, nativeQuery = true)
List<Object[]> findCategoryTree(Long rootId);
~~~

This is PostgreSQL syntax. Other databases may differ in recursive CTE syntax, column declarations, recursion limits, or data types. Be sure to test against the actual target engine.

JPQL can navigate mapped relationships, but it does not provide standard recursive CTE syntax to solve every tree structure. If tree querying is a core business requirement, native SQL or a dedicated approach is usually more appropriate.

## 5. When You Need Database-Specific Operators or Data Types

Some databases provide data capabilities that standard JPQL cannot fully express.

PostgreSQL JSONB example:

~~~java
@Query(value = """
    SELECT e.*
    FROM event_records e
    WHERE e.payload ->> 'eventType' = ?1
    """, nativeQuery = true)
List<EventRecord> findEventsByType(String eventType);
~~~

The `->>` operator extracts a text value from `JSONB`. This is PostgreSQL syntax; you cannot assume MySQL, Oracle, or H2 supports the same operator.

Similar scenarios include:

- Full-text search using the database's native engine.
- Geospatial filtering with PostGIS.
- Comparing arrays with database-specific operators.
- Using specialized JSON or string-processing functions.
- Querying data in materialized views.

If the application only needs to store JSON and retrieve the entire payload, you can map the data type using Hibernate or a converter without needing native queries for every operation. Only use native SQL where specific operators are truly required.

## 6. When You Need to Integrate With a Legacy Schema or Views

In legacy systems, the database may have:

- Table/column names that do not follow Entity conventions.
- Views or materialized views built by DBAs.
- Reporting tables or summary tables.
- Data structures that are inconvenient to model as Entities.
- Stored procedures or functions shared across multiple applications.

Native SQL lets you query those structures directly without forcing the entire schema into an Entity model.

Example reading from a reporting view:

~~~java
public interface SalesSummary {
    Long getCustomerId();
    BigDecimal getTotalSales();
}
~~~

~~~java
@Query(value = """
    SELECT
        s.customer_id AS customerId,
        s.total_sales AS totalSales
    FROM customer_sales_summary s
    WHERE s.total_sales >= ?1
    """, nativeQuery = true)
List<SalesSummary> findCustomersBySalesThreshold(
        BigDecimal minimumSales
);
~~~

The aliases `customerId` and `totalSales` must correspond to the projection's accessor methods. Alias naming and how the provider returns column labels can affect mapping, so verify with an integration test against a real database.

## 7. Declaring Native Queries in Spring Data JPA

The most common and widely compatible approach is using `@Query` with `nativeQuery = true`:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(value = """
        SELECT p.*
        FROM products p
        WHERE p.active = true
        ORDER BY p.name
        """, nativeQuery = true)
    List<Product> findAllActiveNative();
}
~~~

When a native query returns `Product`, the SQL statement must select all columns required for the JPA provider to hydrate the Entity according to its mapping. Primary key columns, required fields, inheritance columns, or related mappings must be present with matching names and types.

Do not `SELECT` only a few columns and declare the return type as the full Entity. If you only need partial data, use a projection or DTO.

### Using EntityManager When Direct Control Is Needed

You can create a native query via `EntityManager`:

~~~java
@Repository
public class ProductNativeRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Product> findActiveProducts() {
        return entityManager
                .createNativeQuery(
                    "SELECT * FROM products WHERE active = ?",
                    Product.class
                )
                .setParameter(1, true)
                .getResultList();
    }
}
~~~

`Product.class` instructs JPA to map result rows into `Product` Entities. The `?` placeholder is a positional native SQL parameter in the JPA API; `setParameter(1, ...)` binds a value to the first parameter.

`EntityManager` is suitable when you need the native query API, hints, timeouts, lock modes, or more complex result mappings. For simple queries, `@Query` is usually more concise.

## 8. Binding Parameters Safely

Always use bound parameters instead of concatenating input strings into SQL.

Safe:

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    WHERE p.name = ?1
    """, nativeQuery = true)
List<Product> findByNameNative(String name);
~~~

Unsafe:

~~~java
String sql =
        "SELECT * FROM products WHERE name = '" + name + "'";
~~~

String concatenation opens the door to SQL injection if the value comes from a user. Parameter binding causes the driver to transmit the data as a value rather than interpreting it as SQL syntax.

Notes:

- Parameter binding is for values such as IDs, names, statuses, or dates.
- You cannot use parameter binding to replace table names, column names, the `ORDER BY` keyword, or `ASC`/`DESC` directions.
- If dynamic sort column selection is needed, map the user's choice against an allowlist of permitted identifiers and build the query from that whitelist.
- Never concatenate user-supplied content directly into SQL conditions.
- Native parameter syntax can vary by API/provider. Using positional placeholders `?1` in Spring Data is common; named parameters in native queries are not guaranteed to be portable across all Jakarta Persistence providers.

Sort whitelist example:

~~~java
String sortColumn = switch (requestedSort) {
    case "name" -> "p.name";
    case "price" -> "p.price";
    case "createdAt" -> "p.created_at";
    default -> "p.id";
};
~~~

Only identifiers defined by the application are placed into SQL. Never use raw sort strings sent by the client verbatim.

## 9. Mapping Native Query Results

Native query results can be mapped in several ways. Choose a return type suited to the data volume and intended use.

### Returning an Entity

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    WHERE p.id = ?1
    """, nativeQuery = true)
Optional<Product> findEntityByIdNative(Long id);
~~~

Use this when you need an Entity managed by the persistence context. The `SELECT` must return all columns required by the Entity's mapping.

### Returning an Interface Projection

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

~~~java
@Query(value = """
    SELECT
        p.id AS id,
        p.name AS name,
        p.price AS price
    FROM products p
    WHERE p.active = true
    """, nativeQuery = true)
List<ProductSummary> findActiveProductSummaries();
~~~

Projections fetch only the needed columns and do not require hydrating the entire Entity. Aliases should match the projection's property names; verify how mapping behaves with your provider and Spring Data version.

### Returning a DTO Class

With native queries, mapping directly to a DTO class is not always as automatic as with an interface projection. If the result requires specific constructor mapping, you can use `@SqlResultSetMapping` with `@ConstructorResult`, or retrieve scalar results and map them to DTOs in the repository/service.

Do not rely on `Object[]` column ordering in multiple places throughout the application. If you must use `Object[]`, encapsulate and convert it in one place with explicit type checking and clear aliases.

## 10. Pagination With Native Queries

Native queries can be combined with `Pageable`, but Spring Data needs to know how to count total results. For simple queries, the framework may derive the count query; for complex queries, declare `countQuery` explicitly.

~~~java
@Query(
    value = """
        SELECT p.id AS id, p.name AS name, p.price AS price
        FROM products p
        WHERE p.active = true
        ORDER BY p.name
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM products p
        WHERE p.active = true
        """,
    nativeQuery = true
)
Page<ProductSummary> findActiveSummaries(Pageable pageable);
~~~

`countQuery` must count the exact number of logical records returned by the content query. If the query contains a `JOIN` that duplicates rows, `DISTINCT`, or `GROUP BY`, `countQuery` must reflect that exact semantics.

Dynamic sorting with native queries depends on the Spring Data version and SQL parsing capabilities. Do not assume the framework can safely append `ORDER BY` automatically to every native query. For complex queries, you can define fixed-sort methods or build sort selection using a whitelist.

## 11. Native UPDATE/DELETE and Impact on the Persistence Context

Native SQL can perform updates or deletes directly:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(value = """
    UPDATE products
    SET active = false
    WHERE created_at < ?1
    """, nativeQuery = true)
int deactivateOlderThan(Instant cutoff);
~~~

The method must be invoked within a transaction, typically managed by a service:

~~~java
@Service
public class ProductMaintenanceService {

    private final ProductRepository repository;

    public ProductMaintenanceService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateOldProducts(Instant cutoff) {
        return repository.deactivateOlderThan(cutoff);
    }
}
~~~

Bulk native DML acts directly on the database and does not update individual Entities in the persistence context. Therefore:

- Previously loaded Entities may still hold stale data in memory.
- `@PreUpdate`/`@PreRemove` callbacks do not run automatically for each Entity.
- Dirty checking does not track individual rows modified by the SQL statement.
- Optimistic locking is not automatically enforced as it is when updating Entities via JPA.
- Second-level caches or query caches may require handling depending on configuration/provider.

`flushAutomatically` flushes pending JPA changes before executing the query; `clearAutomatically` clears the persistence context afterward to avoid continuing to use stale Entities. Clearing affects all managed Entities in that persistence context, so only use it when you understand the impact.

If updating via native SQL while still needing optimistic locking, include the version condition in the `WHERE` clause and increment the version in the `UPDATE` statement yourself, then check the updated row count. Do not assume `@Version` automatically protects an arbitrary native SQL statement.

## 12. Are Native Queries Faster Than JPQL?

No. Native SQL is not automatically faster than JPQL. JPQL is typically translated by the provider into equivalent SQL. If both statements produce the same execution plan, performance can be virtually identical.

Native SQL can be helpful when:

- You need exact control over a `JOIN`, CTE, window function, or hint.
- You want to leverage database-specific indexes/operators.
- You need to write a query that JPQL/the provider cannot express.
- You have measured and proven that the provider-generated SQL is suboptimal.
- A DBA has tuned a specific SQL statement for real workloads.

To evaluate, compare:
1. The actual SQL executed.
2. The database execution plan.
3. The number of rows scanned and returned.
4. The indexes used.
5. Runtime performance with production-like data.
6. Write and locking overhead under concurrent transactions.

Do not switch to native SQL just because a query is long or because you assume handwritten SQL is always faster.

## 13. Native SQL and Portability Across Databases

A native query typically depends on:

- Table, column, schema names, and identifier quoting.
- Physical data types.
- Database-specific functions, operators, and syntax.
- Pagination and row-limiting syntax.
- Data types returned by the JDBC driver.
- How the database handles `NULL`, collation, and timestamps.
- Support for CTEs, JSON, window functions, locks, and hints.

PostgreSQL example using `LIMIT`/`OFFSET`:

~~~sql
SELECT *
FROM products
ORDER BY id
LIMIT 20 OFFSET 40;
~~~

Some databases use different pagination syntax. Spring Data can generate dialect-specific pagination for eligible queries, but handwritten SQL containing vendor-specific syntax still requires adjustment when switching engines.

If the application supports multiple databases, isolate native queries in dedicated repositories, name them clearly by database if needed, and maintain integration tests for each engine. Avoid scattering PostgreSQL-specific syntax across multiple services.

## 14. Native Queries and Stored Procedures

A native query is an SQL statement sent directly through JPA. A stored procedure is a routine already defined in the database and invoked via an appropriate API, such as `@NamedStoredProcedureQuery` or `StoredProcedureQuery`.

Stored procedures may be suitable when:

- Heavy data-processing logic needs to run close to the database.
- Multiple applications share a single database routine.
- DBAs centrally manage routines and execution permissions.
- Database-specific procedural capabilities are needed.

On the flip side, business logic becomes split between Java and the database, is harder to test independently, and can create strong vendor lock-in. Do not use a stored procedure just to replace a simple query that JPQL or a native query already handles well.

## 15. Common Pitfalls

**Using Entity names in native SQL**

Native SQL requires real table and column names. Only JPQL uses Entity names and Java properties.

**Using SQL table/column names in JPQL**

JPQL does not understand physical names by default. Use mapped Entity names and properties.

**Returning an Entity while selecting only a subset of columns**

The provider may fail to hydrate the full Entity or return incorrect data. Use a projection or DTO if you only need partial data.

**Concatenating parameters into SQL strings**

This creates a risk of SQL injection. Use bound parameters for all input values.

**Using bound parameters for column names or ORDER BY**

SQL parameters cannot substitute identifiers. Use a whitelist of permitted choices.

**Forgetting countQuery for complex native pagination**

Spring Data may fail to derive the correct row count. Declare a `countQuery` that matches the query logic.

**Running native DML and then reading stale Entities in the same persistence context**

Managed Entities may become stale. Consider flushing/clearing and checking transaction boundaries.

**Assuming native SQL is always faster**

Measure the execution plan and workload. Native SQL increases control; it does not automatically create performance.

**Testing only on H2 when production uses another database**

Data types, syntax, collation, and functions can differ. Run integration tests against the actual target database.

## 16. Decision and Testing Workflow

Before writing a native query, answer these questions:

1. Can standard JPQL express the requirement?
2. Are CTEs, window functions, JSON operators, full-text search, spatial features, hints, or vendor-specific syntax required?
3. Does a native query genuinely improve control or measurable performance?
4. Should the result be an Entity, projection, or DTO?
5. Are pagination and a dedicated `countQuery` needed?
6. Are all parameters bound safely?
7. Does native DML affect the persistence context, lifecycle callbacks, or `@Version`?
8. Which database does the query depend on, and where is it isolated?
9. Do integration tests run on the exact target engine, schema, and version?

After implementation, verify the actual generated SQL, returned data types, projection aliases, transactions, execution plan, and `NULL` edge cases. If the query contains multiple `JOIN`s, check for duplicate rows and verify how `countQuery` counts results.

## 17. Conclusion

Native SQL should be used when standard JPQL cannot express the query, when database-specific features are needed, when integrating with legacy schemas/views, or when controlling an SQL statement that has been measured and tuned. For standard CRUD, relationships, and everyday filtering, JPQL is generally easier to read, maintain, and port. When using native queries, bind parameters safely, map results clearly, handle pagination and the persistence context carefully, and test against the target database.
# Choosing Derived Queries, @Query, or Custom Implementations by Problem

In **Spring Data Relational JDBC**, a repository can fetch data using derived method names, declare SQL directly with `@Query`, or add a custom implementation fragment using Spring JDBC. All three approaches have their place, addressing different levels of complexity.

The right choice depends on query shape, condition dynamism, required return types, aggregate boundaries, performance requirements, and how strongly the query depends on database syntax. A simple query can be expressed cleanly through a method name; a static SQL query fits `@Query`; and dynamic queries or special mappings are usually easier to control inside a custom repository fragment.

This lesson provides a decision framework, examples implementing the same problem across all three approaches, how to combine them in one repository, and considerations around transactions, security, portability, and testing.

## 1. Three querying approaches in Spring Data JDBC

Spring Data JDBC supports three main approaches:

| Approach | How the query is described | Suitable when |
| --- | --- | --- |
| Derived query | Repository method name describes properties and predicates | Simple, static conditions filtering mostly on aggregate root properties |
| `@Query` | Write SQL directly in an annotation on the method | Static SQL needing joins, functions, subqueries, or specific conditions |
| Custom repository implementation | Write Java code using `JdbcClient`, `NamedParameterJdbcTemplate`, or `JdbcTemplate` | Dynamic conditions, multiple branches, complex SQL, custom mapping, or coordinating multiple operations |

Selection flow:

~~~text
Query requirement
      |
      v
Simple, static conditions clearly expressed by method name?
      |
      +-- Yes --> Derived query
      |
      +-- No
            |
            v
       Static SQL with clear result shape?
            |
            +-- Yes --> @Query
            |
            +-- No
                  |
                  v
           Custom repository fragment
           (Dynamic SQL / mapping / orchestration)
~~~

This is a decision guide, not a rigid rule. A simple query may still use `@Query` if explicit SQL improves readability; a complex yet completely static query can stay in an annotation if it remains maintainable.

## 2. When to choose derived queries?

Derived queries fit when intent can be described in a short, clear, stable method name. Spring Data parses the method name to build SQL conditions based on entity properties.

Example aggregate:

~~~java
import java.time.LocalDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String sku,
        String name,
        String status,
        @Column("price_minor_units") long priceMinorUnits,
        @Column("created_at") LocalDateTime createdAt
) {
}
~~~

Repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    List<Product> findByStatus(String status);

    List<Product> findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc(
            String status,
            long minimumPrice
    );

    List<Product> findTop20ByStatusOrderByCreatedAtDesc(String status);

    boolean existsBySku(String sku);

    long countByStatus(String status);
}
~~~

Each method expresses intent directly:

- `findBySku`: find by SKU.
- `findByStatus`: find all products by status.
- `findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc`: filter by status and minimum price, ordered newest first.
- `findTop20ByStatusOrderByCreatedAtDesc`: cap the number of results.
- `existsBySku`: check existence.
- `countByStatus`: count products by status.

### 2.1. Advantages of derived queries

**Less SQL to maintain:** the framework generates SQL from metadata and dialect.

**Method names express intent:** with short predicates, readers immediately see filter conditions.

**Natural repository integration:** works seamlessly with return types like `Optional<T>`, `List<T>`, `boolean`, or others matching query contracts.

**Reduced database syntax coupling:** the framework can generate dialect-appropriate SQL instead of manually writing variants.

### 2.2. Signs a derived query is no longer suitable

A method name becomes hard to read when:

- There are many combined AND/OR conditions.
- There are complex logical groupings.
- The method name grows so long readers must parse every keyword carefully.
- The query requires joining multiple tables or using SQL expressions.
- Conditions apply only when certain parameters are provided.
- Projections or complex aggregations are needed.
- Multiple sorting or pagination variants exist.

Example of an overly long method name:

~~~java
List<Product> findByStatusInAndCategoryIdAndPriceMinorUnitsGreaterThanEqualAndNameContainingIgnoreCaseOrderByCreatedAtDesc(
        Collection<String> statuses,
        Long categoryId,
        long minimumPrice,
        String name
);
~~~

The method may still be valid if all predicates are supported, but as more logical branches accumulate, the method name stops helping readers understand the query. Consider `@Query` or a custom implementation.

### 2.3. Derived queries have limits under the JDBC model

Spring Data JDBC is not an ORM that infers arbitrary object graphs and generates joins automatically. Query derivation works best for mapped properties of the aggregate root and predicates supported by your Spring Data JDBC version.

Do not assume nested property paths, child collections, or aggregate references will automatically translate into joins like in JPA. When a query needs multi-table data or complex conditions, check your version's documentation; if derived queries cannot express it, use explicit SQL or a custom repository.

### 2.4. Do not pick derived queries just because SQL is short

A long, cryptic method name does not become better simply because the framework generates the SQL. Evaluate how easily maintainers understand business conditions, how many methods would proliferate, and how the query will evolve.

## 3. When to choose @Query?

`@Query` fits a **static** SQL statement that belongs right alongside the repository method. The author controls tables, columns, joins, functions, and result ordering.

In Spring Data JDBC, import the annotations:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
~~~

Example finding products above a price threshold with a given status:

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY created_at DESC, id DESC
       """)
List<Product> searchByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

The SQL here is database SQL, not JPQL. `products` and `price_minor_units` are real table and column names in the schema.

### 3.1. Cases where @Query shines

- The query needs to join other tables.
- Subqueries or CTEs are needed.
- Database-specific functions are needed.
- Calculations or aggregates like `COUNT`, `SUM`, `MIN` are needed.
- A read projection clearly defined in SQL is needed.
- A fixed update/delete statement is needed.
- A derived query name would be too long or unable to express the logic.

Example joining orders with customers for a list screen:

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

This is a read query combining two aggregates. The result fits a DTO/projection for the screen rather than a full `PurchaseOrder` aggregate.

### 3.2. Advantages of @Query

**Transparent SQL:** readers see the exact statement instead of inferring it from a method name.

**Precise control:** easy to specify joins, aliases, functions, ordering, and expressions.

**Lives beside the repository contract:** method name, parameters, and SQL sit together.

**Minimal boilerplate:** no separate implementation class is needed for a single static query.

### 3.3. When @Query becomes hard to maintain

Annotations are not ideal for every SQL query. Consider moving to a custom implementation when:

- SQL must be assembled from many optional filters.
- Conditional branches grow with request parameters.
- Multiple allowlists are needed for sort columns or directions.
- Complex result mapping spans multiple DTO shapes.
- Multiple queries or processing steps must be coordinated.
- SQL must be chosen by database/dialect.
- Predicate-building or mapping helpers need reuse.

An annotation packed with a hundred-line SQL statement, numerous null checks, and optional placeholders can be harder to read than structured Java code.

### 3.4. Named parameters and security

Always bind values through placeholders:

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE sku = :sku
       """)
Optional<Product> findBySku(@Param("sku") String sku);
~~~

Never concatenate input into SQL:

~~~java
// Unsafe:
String sql = "SELECT * FROM products WHERE sku = '" + sku + "'";
~~~

Parameter binding ensures values are treated as data, reducing SQL injection risk and avoiding escaping bugs.

Table names, column names, or sort keywords cannot be replaced with standard bind parameters. If dynamic selection is needed, use an allowlist of known identifiers or construct SQL in a custom implementation from safe constants.

## 4. When to choose a custom repository implementation?

A custom repository implementation fits when query logic needs dynamic conditions, multiple SQL statements, custom mapping, or behavior that no longer fits cleanly in an annotation.

Spring Data supports composing repositories from fragments. A fragment has its own interface and corresponding implementation; the main repository extends that fragment.

~~~text
ProductRepository
  |
  +-- CrudRepository<Product, Long>
  |
  +-- ProductSearchRepository
          |
          v
    ProductSearchRepositoryImpl
          |
          v
    NamedParameterJdbcTemplate
          |
          v
       Database
~~~

### 4.1. Declaring the fragment interface

~~~java
import java.util.List;

public interface ProductSearchRepository {
    List<ProductSummary> search(ProductSearchCriteria criteria);
}
~~~

Define the DTO and search criteria:

~~~java
import java.util.List;

public record ProductSummary(
        Long id,
        String sku,
        String name,
        String status,
        long priceMinorUnits
) {
}

public record ProductSearchCriteria(
        List<String> statuses,
        Long categoryId,
        Long minimumPrice,
        String nameContains,
        ProductSort sort,
        int limit
) {
}

public enum ProductSort {
    NEWEST,
    PRICE_ASC,
    PRICE_DESC
}
~~~

`ProductSearchCriteria` groups optional conditions into one object, avoiding methods with too many parameters. `ProductSort` restricts allowed sort options.

### 4.2. Composing the fragment into the repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, ProductSearchRepository {

    Optional<Product> findBySku(String sku);
}
~~~

Spring Data repository composition combines the CRUD repository with the custom fragment. By default convention, an implementation named `ProductSearchRepositoryImpl` is paired with fragment `ProductSearchRepository`. Another postfix can be configured, provided it stays consistent across the project's repository setup.

### 4.3. Implementing with NamedParameterJdbcTemplate

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ProductSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public List<ProductSummary> search(ProductSearchCriteria criteria) {
        if (criteria.limit() <= 0 || criteria.limit() > 200) {
            throw new IllegalArgumentException("limit must be between 1 and 200");
        }

        StringBuilder sql = new StringBuilder("""
                SELECT id, sku, name, status, price_minor_units
                FROM products
                WHERE 1 = 1
                """);

        MapSqlParameterSource params = new MapSqlParameterSource();

        if (criteria.statuses() != null && !criteria.statuses().isEmpty()) {
            if (criteria.statuses().stream().anyMatch(value -> value == null)) {
                throw new IllegalArgumentException("status must not be null");
            }
            sql.append(" AND status IN (:statuses)");
            params.addValue("statuses", criteria.statuses());
        }

        if (criteria.categoryId() != null) {
            sql.append(" AND category_id = :categoryId");
            params.addValue("categoryId", criteria.categoryId());
        }

        if (criteria.minimumPrice() != null) {
            sql.append(" AND price_minor_units >= :minimumPrice");
            params.addValue("minimumPrice", criteria.minimumPrice());
        }

        if (criteria.nameContains() != null
                && !criteria.nameContains().isBlank()) {
            sql.append(" AND name LIKE :namePattern");
            params.addValue(
                    "namePattern",
                    "%" + criteria.nameContains().trim() + "%"
            );
        }

        String orderBy = switch (criteria.sort() == null
                ? ProductSort.NEWEST : criteria.sort()) {
            case NEWEST -> "created_at DESC, id DESC";
            case PRICE_ASC -> "price_minor_units ASC, id ASC";
            case PRICE_DESC -> "price_minor_units DESC, id DESC";
        };

        sql.append(" ORDER BY ").append(orderBy);
        sql.append(" LIMIT :limit");
        params.addValue("limit", criteria.limit());

        RowMapper<ProductSummary> mapper = (rs, rowNum) ->
                new ProductSummary(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getString("name"),
                        rs.getString("status"),
                        rs.getLong("price_minor_units")
                );

        return jdbc.query(sql.toString(), params, mapper);
    }
}
~~~

This example targets a database supporting `LIMIT`. If the target database uses another row-limiting syntax, the end of the SQL must be adapted for that dialect. Column names such as `category_id` and `created_at` must exist in the actual schema.

Key design decisions in this implementation:

- Conditions are appended only when the corresponding parameters are supplied.
- Input values are bound using `MapSqlParameterSource`.
- An empty statuses list is defined in this example as **applying no status filter**. If the contract requires "no status selected means no results", the service should return an empty list before calling the fragment.
- Sort is selected from an enum and mapped to fixed SQL strings. Raw request sort values are never concatenated.
- The result set is mapped explicitly into `ProductSummary`.
- `limit` is bounds-checked before binding.

If `nameContains` must match literal text, escape `%` and `_` wildcards according to the database's `LIKE` rules. If wildcards are intentionally permitted, document that contract clearly.

### 4.4. Why use a repository fragment instead of an arbitrary utility class?

Fragments help by:

- Keeping the search API on the same repository callers already use.
- Separating standard CRUD from specialized queries.
- Making it easy to change implementations without altering service contracts.
- Injecting JDBC dependencies via constructor.
- Sharing Spring-managed transactions and datasources.

There is no need to create a custom implementation just to wrap `findById` or `findAll`. Add a fragment only when behavior genuinely requires custom implementation.

## 5. Comparing all three approaches on the same problem

Suppose we need to find products by status and minimum price, ordered by creation date.

### 5.1. Using a derived query

~~~java
List<Product> findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc(
        String status,
        long minimumPrice
);
~~~

**Suitable when:** there is only one status, one price threshold, and one fixed sort order.

**Limitation:** if multiple statuses, optional category, search keyword, and multiple sort modes are added, the method name becomes long and rigid.

### 5.2. Using @Query

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY created_at DESC, id DESC
       """)
List<Product> searchByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

**Suitable when:** SQL is static, columns and conditions should be explicit, and there is no need to assemble clauses across branches.

**Limitation:** SQL does not change structure based on parameters beyond bound values; with many optional filters, the annotation can become hard to read.

### 5.3. Using a custom fragment

~~~java
List<ProductSummary> search(ProductSearchCriteria criteria);
~~~

**Suitable when:** optional filters, allowlisted dynamic sorting, dedicated projections, and controlled limits are needed in code.

**Trade-off:** more code to write, and the implementer is responsible for constructing SQL, binding parameters, and mapping results.

| Criterion | Derived query | `@Query` | Custom implementation |
| --- | --- | --- | --- |
| Initial complexity | Low | Medium | Higher |
| SQL directly visible | No | Yes | Yes |
| Dynamic conditions | Limited | Usually awkward | Flexible |
| Joins and special functions | Not its strength | Suitable | Suitable |
| Complex DTO mapping | Limited by supported contracts | Depends on supported projections | Full control with RowMapper |
| Reusing query-building helpers | Not flexible | Limited | Good |
| Dialect coupling | Lower | Can be high | Can be high |
| Boilerplate | Minimal | Minimal to moderate | Higher |
| Safe dynamic SQL control | No SQL building needed | Limited | Needs allowlists and proper binding |

## 6. Choosing by problem shape

| Problem | Usually suitable choice | Reason |
| --- | --- | --- |
| Find one product by unique SKU | Derived query | Short, clear method name |
| Filter by status and minimum price | Derived query | Simple, static predicates |
| Filter by a static SQL condition with a function | `@Query` | SQL is clearer than a method name |
| Join order with customer into a DTO | `@Query` or custom fragment | SQL join and result shape are controlled |
| Many optional filters from a search screen | Custom fragment | Add/omit predicates based on parameters |
| Multiple sort options from an allowlist | Custom fragment | Safely select SQL identifiers via enum |
| Query with static CTE/subquery | `@Query` | SQL sits next to the repository method |
| Query needing multiple result shapes or custom row handling | Custom fragment | Explicit RowMapper |
| Static bulk update with simple condition | `@Modifying` + `@Query` | Short SQL, clear intent |
| Bulk update with multiple dynamic branches | Custom fragment | Easier to control conditions and affected rows |
| Load full aggregate to run domain behavior | Standard repository method | Preserves aggregate mapping and ownership |
| Report needing only a few columns | Separate projection/query | Avoids loading full aggregates |

### 6.1. Start from the data contract

Before choosing a tool, clarify:

- Is the result an aggregate root, projection, scalar, or collection?
- Can the query return zero rows, one row, or multiple rows?
- Are conditions static or dependent on optional inputs?
- Is joining across independent aggregates required?
- Do aggregate invariants need to be enforced, or is this read-only reporting?
- Which databases must be supported?

A query can be SQL-complex yet return only a tiny DTO. Conversely, a simple filter query might return a large aggregate and require the repository's full mapping machinery.

## 7. Separating read queries from aggregate update flows

Not every query should return an entity only to save it back. Distinguish:

**Command/update path:** needs the full aggregate to verify invariants and execute domain behavior. Use the root repository, call domain methods, and `save`.

**Read/query path:** needs display or report data. Use projections, SQL joins, or custom queries.

For example, an order list screen may only need:

- Order number.
- Status.
- Customer name.
- Total amount.

There is no need to load every `PurchaseOrder` along with all its `OrderLine`s if the screen never uses them. A DTO query reduces data volume and database access.

Conversely, an order confirmation use case must inspect all order lines and statuses. Do not substitute a thin projection for an aggregate in an update operation.

## 8. Using @Modifying for static modifying SQL

If an update/delete statement is simple and static, `@Query` combined with `@Modifying` can be used:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("""
       UPDATE products
       SET status = :newStatus
       WHERE id = :id
       """)
int updateStatus(
        @Param("id") Long id,
        @Param("newStatus") String newStatus
);
~~~

The method returns the number of affected rows so callers can check whether the ID matched. If versioned, bulk SQL does not automatically apply optimistic locking like aggregate save operations. Include the version check in the predicate and increment it deliberately if conflict detection is needed.

If an update needs multiple dynamic branches, coordination across statements, or custom mapping, move it to a fragment. Never use bulk updates to bypass domain model invariants.

## 9. Transactions and datasources in custom implementations

A custom repository fragment using `NamedParameterJdbcTemplate` or `JdbcClient` participates in Spring transactions when sharing the application's configured `DataSource` and transaction manager.

Example:

~~~java
@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<ProductSummary> search(ProductSearchCriteria criteria) {
        return repository.search(criteria);
    }
}
~~~

`@Transactional(readOnly = true)` expresses a read-only use case. For multi-step write use cases, place `@Transactional` at the service boundary so all operations join the configured transaction together.

In custom implementations:

- Inject Spring-configured templates via constructor.
- Share the same datasource as the repository.
- Never open connections manually via `DriverManager.getConnection`.
- Never instantiate a new `DataSource` just for one query.
- Close resources properly if using low-level JDBC APIs directly.

Spring JDBC templates manage connection acquisition and release through Spring's transaction-aware infrastructure. Opening connections outside that mechanism can prevent operations from participating in the active transaction.

### 9.1. Transactions do not unify multiple databases into one

If a custom fragment calls another database or an HTTP service, local `@Transactional` does not create a distributed transaction. When coordinating multiple systems, design an outbox, saga, or appropriate synchronization mechanism.

## 10. Portability across databases

Derived queries help minimize dialect-specific SQL. With `@Query` and custom fragments, the author takes responsibility for database syntax.

Common differences:

| Need | Areas that can differ |
| --- | --- |
| Row limiting | `LIMIT/OFFSET`, `FETCH FIRST`, `OFFSET ... FETCH` |
| Upsert | `ON CONFLICT`, `MERGE`, or vendor-specific syntax |
| ID generation | Identity, sequence, or custom mechanism |
| JSON | Data types, operators, and functions |
| String concatenation | `||` or `CONCAT` |
| Date and time | Functions, timezones, and timestamp types |
| Locking updates | Locking syntax and isolation behavior |

If only one database is supported, vendor-specific syntax can be pragmatic. If multiple databases must be supported:

- Prefer derived queries when they express intent adequately.
- Stick to common SQL subsets where feasible.
- Separate custom implementations by dialect when differences truly matter.
- Run integration tests on every target database.

Never claim a query is portable just because it passes on H2. Test using the production database or Testcontainers with the matching image and version.

## 11. Security when building queries

Regardless of the chosen approach, request data must be treated as untrusted input.

### 11.1. Value binding

With derived queries, the framework handles parameter binding.

With `@Query`:

~~~java
@Query("SELECT * FROM products WHERE sku = :sku")
Optional<Product> findBySku(@Param("sku") String sku);
~~~

With custom fragments:

~~~java
jdbc.query(
        "SELECT * FROM products WHERE sku = :sku",
        new MapSqlParameterSource("sku", sku),
        rowMapper
);
~~~

Never concatenate values directly into SQL.

### 11.2. Allowlisting dynamic identifiers

Sort columns and table names cannot be bound as values. Use an enum or switch:

~~~java
String orderBy = switch (sort) {
    case NEWEST -> "created_at DESC";
    case PRICE_ASC -> "price_minor_units ASC";
    case PRICE_DESC -> "price_minor_units DESC";
};
~~~

Concatenate only strings from a controlled set of constants. Never write:

~~~java
sql.append(" ORDER BY ").append(request.sortBy());
~~~

if `request.sortBy()` comes directly from external input.

### 11.3. Controlling parameter collections

For `IN`/`NOT IN` conditions:

- Check for null collections.
- Define what an empty collection means.
- Check for null elements.
- Cap the maximum number of elements.
- Use bind parameters instead of concatenating values.

Never allow an empty collection to produce invalid SQL or unexpectedly alter semantics.

## 12. Performance: API choice does not replace SQL measurement

Whether you use a derived query, `@Query`, or a custom fragment does not by itself determine query speed. Performance depends on:

- Generated SQL.
- Indexes and execution plans.
- Number of rows scanned.
- Size of returned data.
- Number of round-trips.
- JVM mapping and allocation.
- Connection pool wait times.
- Transaction/isolation and lock contention.

### 12.1. When derived queries are fast enough

A simple query by ID or status can produce efficient SQL and leverage an appropriate index. Do not rewrite into custom SQL for "optimization" without evidence.

### 12.2. When @Query helps control performance

Explicit SQL lets you fetch only needed columns and use appropriate joins, subqueries, and expressions. Projections avoid materializing large aggregates when a use case only needs a few columns.

### 12.3. When custom implementations are needed

Custom fragments let you construct dynamic predicates so the database evaluates only active filters, rather than a huge SQL statement filled with optional branches. However, handwritten query builders can also generate slow SQL; measure execution plans and row counts.

## 13. Signs it is time to switch from one approach to another

| Current sign | Consider |
| --- | --- |
| Long derived method with confusing AND/OR groups | `@Query` or custom fragment |
| Derived method filters simple properties with a short name | Keep derived query |
| Static, readable SQL that rarely changes | `@Query` |
| `@Query` with many optional predicates and complex placeholders | Custom fragment |
| Long `@Query` with heavy calculations and custom DTO mapping | Custom fragment |
| Custom implementation containing just one simple SELECT | Consider returning to `@Query` or derived query |
| Multiple custom methods repeating the same predicate-building logic | Extract helper/query components in the custom layer |
| Custom code opening connections and managing transactions manually | Switch to Spring-managed templates |
| Query needs a full aggregate while manually mapping every child | Consider standard root repository |
| Screen needs only a few columns while loading full aggregates | Dedicated projection or read query |

Do not switch merely out of personal preference. Switch when the current approach obscures intent, resists extension, makes SQL hard to control, or mismatches mapping needs.

## 14. Testing according to query choice

Each query style warrants its own checks.

### 14.1. Derived queries

Verify:

- Property paths match field names.
- Predicates behave accurately on boundary data.
- Empty results and cardinality.
- Sorting/limiting if present.
- Property nullability.

### 14.2. @Query

Verify:

- Table/column names match the schema.
- Bind parameters match names and types.
- Aliases map properly to properties/DTOs.
- SQL runs on the production dialect.
- Zero rows, one row, and multiple rows.
- Projections receive only selected columns.
- Update/delete statements return accurate affected row counts.

### 14.3. Custom repositories

Verify:

- Each optional filter is added/omitted properly.
- Null inputs and empty collections match the contract.
- Sorting accepts only allowlisted values.
- Limits/page sizes are capped.
- ResultSet mapping handles types and nullability accurately.
- Templates share the application datasource/transactions.
- SQL is safe against injection when inputs contain special characters.

Example integration test:

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void searchesUsingOptionalCriteria() {
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                List.of("ACTIVE", "PENDING"),
                10L,
                100_000L,
                "book",
                ProductSort.NEWEST,
                20
        );

        List<ProductSummary> results = repository.search(criteria);

        assertThat(results).allSatisfy(product -> {
            assertThat(product.priceMinorUnits())
                    .isGreaterThanOrEqualTo(100_000L);
        });
    }
}
~~~

This is an illustrative skeleton; real tests need project-specific schema and test data setup, plus verification that test configuration scans the fragment implementation. If SQL uses vendor-specific syntax, run tests on the matching database instead of relying solely on H2.

## 15. Common mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Using derived queries for overly complex logic | Long, hard-to-read method names | Switch to `@Query` or custom fragment |
| Using `@Query` for every trivial query | Repetitive SQL and higher maintenance cost | Prefer derived queries when method names are clear |
| Putting long dynamic SQL inside annotations | Hard to control conditional branches | Use a custom implementation |
| Assuming `@Query` is JPQL | Wrong table/column names | Write SQL matching the database schema |
| Concatenating input into SQL | SQL injection | Bind parameters |
| Binding column/sort names via placeholders | Database treats identifiers as constant values | Allowlist identifiers |
| Custom fragment opens its own connections | May not join Spring transactions | Inject JdbcClient/JdbcTemplate sharing the DataSource |
| Using a projection where invariants are needed | Missing aggregate state | Load the full aggregate root |
| Loading full aggregates for small reports | Fetching unnecessary data | Use a projection/read query |
| Bulk updates bypassing `@Version` | Concurrent updates may be overwritten | Manage optimistic locking manually or use repository save |
| Testing only with H2 | Misses dialect differences | Test against the target database |
| Creating a custom implementation just to wrap CRUD | Extra classes with no value | Use built-in repository methods |

## 16. Workflow for choosing an implementation approach

When starting a new query, proceed in order:

1. **Identify the purpose:** read aggregate, read projection, count, existence check, or modify data?
2. **Determine the result:** one row, multiple rows, scalar, or DTO?
3. **Evaluate predicates:** simple and static, or many optional conditions?
4. **Check aggregate boundaries:** does the query need root-owned data or joins across independent aggregates?
5. **Choose the least complex approach that remains clear:** derived queries for simple predicates; `@Query` for static SQL; custom fragments for dynamic logic or special mapping.
6. **Design parameter binding:** never concatenate input into SQL; allowlist dynamic identifiers.
7. **Define transactions:** establish service boundaries and shared datasources.
8. **Test the dialect:** verify SQL, mapping, cardinality, and empty cases.
9. **Measure performance:** inspect execution plans, indexes, row counts, and real timings.
10. **Switch approaches when justified:** do not keep an overly complex query method just because it already exists.

## Key takeaways

Choose the query approach matching the real complexity of the problem. **Derived queries** fit simple, static conditions easily expressed in method names. **`@Query`** fits static SQL needing control over tables, columns, joins, or functions. **Custom repository implementations** fit dynamic conditions, complex queries, special mappings, or multi-step logic.

All three can coexist within a single repository. Keep CRUD and aggregate behavior on the root repository; use dedicated SQL/projections for read needs; use custom fragments when annotations stop expressing intent clearly. Regardless of the choice, always bind values safely, control dynamic identifiers, use Spring-managed datasources, place transactions at the right boundaries, and test against the target database.

# Limitations of Query by Example and Alternative Query Options

**Query by Example (QBE)** is a technique for creating queries from a sample object (probe) rather than writing SQL statements or query method names. In Spring Data R2DBC, the application populates search values into a probe, configures an ExampleMatcher to control how matching works, and passes an Example to a reactive repository.

QBE suits simple search screens with many optional fields. It is easy to use and avoids creating a separate repository method for every filter combination. However, QBE only expresses a limited set of conditions. When a query requires complex AND/OR groups, joins, database expressions, custom projections, or explicit SQL control, switch to derived queries, @Query, R2dbcEntityTemplate, or DatabaseClient.

## 1. What Is Query by Example?

QBE consists of three parts:

- **Probe**: an entity instance holding the values to search for.
- **ExampleMatcher**: defines how each property or the overall probe is matched.
- **Example**: combines the probe and matcher for the repository to execute the query.

For example, to find active customers whose name contains the string An, you can create a sample Customer:

~~~java
Customer probe = new Customer(
    null,
    "An",
    null,
    true,
    null
);
~~~

Null values are typically ignored by default. Therefore, this probe only includes the fullName and active properties in the search criteria. A matcher can change fullName matching from exact to containing.

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher(
        "fullName",
        ExampleMatcher.GenericPropertyMatchers.contains()
            .ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
~~~

The repository executes the Example and emits results reactively:

~~~java
Flux<Customer> customers = repository.findAll(example);
~~~

The core idea is: **the values in the probe determine which properties filter the query; ExampleMatcher determines how those values are matched.**

## 2. Using QBE with Spring Data R2DBC

The repository must support reactive Query by Example. Standard Spring Data R2DBC repositories expose QBE operations via ReactiveQueryByExampleExecutor in versions that support it.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email,
    Boolean active,
    @Version Long version
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.query.ReactiveQueryByExampleExecutor;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                ReactiveQueryByExampleExecutor<Customer> {
}
~~~

The example above shows the QBE abstraction the repository needs. In some Spring Data R2DBC versions or configurations, specialized repositories already extend the reactive QBE executor; use the interface provided by your project version and avoid declaring incompatible executors. With reactive repositories, QBE methods return Mono or Flux instead of synchronous types.

Common QBE operations include:

| Method | Result | Purpose |
|---|---|---|
| findOne(example) | Mono<T> | Fetch a single matching result |
| findAll(example) | Flux<T> | Fetch all matching results |
| findAll(example, sort) | Flux<T> | Fetch matching results in order |
| count(example) | Mono<Long> | Count matching results |
| exists(example) | Mono<Boolean> | Check whether a match exists |

Exact signatures and superinterfaces may vary across Spring Data versions. Verify against your project's dependencies when using the QBE API.

## 3. How to Create a Probe

A probe is an instance of the domain type managed by the repository. Non-null properties serve as conditions; null properties are typically ignored by default.

For example:

~~~java
Customer probe = new Customer(
    null,             // id: ignored
    "Nguyen",         // fullName: used for search
    null,             // email: ignored
    true,             // active: used for search
    null              // version: ignored
);
~~~

A probe is not an entity to be saved. It is solely an object carrying search criteria. Do not call save(probe) and do not assign an ID just to run QBE.

Create a dedicated probe for each search operation. Avoid reusing a business entity currently being edited as a probe, because leftover properties can accidentally become query conditions.

### 3.1. Null Properties Are Ignored by Default

With the default ExampleMatcher, null properties do not participate in conditions:

~~~java
Example<Customer> example =
    Example.of(new Customer(null, "An", null, null, null));
~~~

This example filters by fullName; id, email, active, and version are unused because they are null.

This is convenient for optional filters, but it has an implication: **by default, QBE cannot interpret null in a probe as a request to match IS NULL.** Null usually means "no condition supplied".

### 3.2. When You Want to Search for NULL Values

If business logic needs rows where email is NULL, you can use a matcher that includes null values:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIncludeNullValues()
    .withIgnorePaths("id", "fullName", "active", "version");

Example<Customer> example = Example.of(
    new Customer(null, null, null, null, null),
    matcher
);
~~~

Be careful: withIncludeNullValues() can include every null property on the probe in the query, not only email. A probe with many null attributes can produce a query that is overly restrictive or unintended.

If you only want to check that one specific property is NULL, Query/Criteria is usually much clearer:

~~~java
Query query = Query.query(
    Criteria.where("email").isNull()
);

return template.select(Customer.class)
    .matching(query)
    .all();
~~~

For multi-state filters, separate "do not filter", "match NULL", and "match value" using a dedicated Filter type or enum.

### 3.3. Primitive Properties Have Default Values

QBE cannot easily ignore a primitive property because primitives cannot hold null.

For example:

~~~java
public class CustomerProbe {
    private boolean active;
    private int age;
}
~~~

When creating a new object, active defaults to false and age defaults to 0. Those values may be treated as search criteria instead of "no filter provided".

If a field needs to be optional, use wrapper types:

~~~java
private Boolean active;
private Integer age;
~~~

Wrappers allow null to represent "skip this condition". This is an important point when designing probes for search forms.

## 4. Configuring ExampleMatcher

ExampleMatcher controls how properties are matched. The default matcher typically uses exact matching for strings and ignores null properties.

Custom matcher example:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "version")
    .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
    .withIgnoreCase();
~~~

Meaning:

- withIgnorePaths skips properties that should not appear in conditions.
- withStringMatcher sets the default matching mode for String properties.
- withIgnoreCase requests case-insensitive string matching if supported by the store.

You can configure individual properties separately:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "version")
    .withMatcher(
        "fullName",
        ExampleMatcher.GenericPropertyMatchers.contains()
            .ignoreCase()
    )
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact()
            .ignoreCase()
    );
~~~

In this example, fullName uses case-insensitive contains, while email uses case-insensitive exact matching. Other String properties keep the default rule.

### 4.1. StringMatcher Modes

Common modes include:

| StringMatcher | Meaning | Conceptual pattern |
|---|---|---|
| DEFAULT | Uses store/matcher default rule | Usually exact |
| EXACT | Matches the entire string | value |
| STARTING | Starts with string | value% |
| ENDING | Ends with string | %value |
| CONTAINING | Contains string | %value% |

Support and implementation details depend on the store and version. Do not assume every mode or collation behaves identically across all database engines.

QBE is not an API for writing arbitrary full LIKE patterns. When you need wildcard escaping, ESCAPE clauses, full-text search, or database-specific patterns, use Query/Criteria where capable or write SQL with DatabaseClient.

### 4.2. Ignore Case

You can request case-insensitive matching for all String properties:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnoreCase();
~~~

Or for a single property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase()
    );
~~~

Case-insensitive results depend on how Spring Data builds the expression and the database's comparison rules. With Unicode data, accented characters, or special collations, verify behavior against the target database engine.

### 4.3. Matching All and Matching Any

QBE supports two ways of combining selected properties:

- matching(): all conditions are combined with AND.
- matchingAny(): conditions are combined with OR.

AND example:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching();
~~~

If the probe sets fullName and active, results must satisfy both conditions.

OR example:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAny();
~~~

With the same probe, results may match either fullName or active.

matchingAny() is useful for broad searches across a few fields. However, it only combines properties selected by the matcher at a flat level. It is not a general boolean expression builder for nested groups such as:

~~~sql
WHERE tenant_id = :tenant
  AND (full_name LIKE :name OR email LIKE :email)
  AND active = TRUE
~~~

When you need AND/OR groupings like this, use Criteria or explicit SQL.

## 5. Complete Example: Searching Customers with a Probe

Suppose a search screen has fields for name, email, and active status. The user may leave some fields blank.

~~~java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import reactor.core.publisher.Flux;

public Flux<Customer> search(
        String name,
        String email,
        Boolean active) {

    Customer probe = new Customer(
        null,
        name,
        email,
        active,
        null
    );

    ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnorePaths("id", "version")
        .withMatcher(
            "fullName",
            ExampleMatcher.GenericPropertyMatchers.contains()
                .ignoreCase()
        )
        .withMatcher(
            "email",
            ExampleMatcher.GenericPropertyMatchers.exact()
                .ignoreCase()
        );

    Example<Customer> example = Example.of(probe, matcher);

    return repository.findAll(example);
}
~~~

Given input:

~~~text
name = "An"
email = null
active = true
~~~

QBE builds conditions from fullName and active; the null email is ignored. The matcher requires fullName to contain An case-insensitively.

This example assumes null String properties are ignored and active is a Boolean wrapper. If active were a primitive boolean, its default false value could inadvertently become an active condition.

## 6. Key Limitations of Query by Example

QBE is simple because it describes only a probe and a set of matching rules. That simplicity creates clear limitations.

### 6.1. Cannot Express Arbitrary Nested Condition Groups

QBE supports matchingAll and matchingAny, but cannot express arbitrary boolean structures.

For example, the requirement:

~~~sql
WHERE tenant_id = :tenant
  AND (full_name LIKE :name OR email LIKE :email)
  AND active = TRUE
~~~

cannot be expressed accurately with a standard ExampleMatcher alone. matchingAny() can OR probe properties together, yet cannot put just two properties inside an OR group and AND that with tenant and active.

Use Criteria to build grouped conditions, or DatabaseClient when exact SQL is needed.

### 6.2. Unsuitable for Joins and Multi-Table Queries

A probe describes properties of a single entity. QBE is not a tool for constructing arbitrary joins across multiple tables, subqueries, or CTEs.

Spring Data Relational focuses on the aggregate model and relational mapping. Do not assume nested object properties automatically generate joins as in some ORMs.

If you need to combine customer with order, product, or summary tables, use an appropriate SQL-level or template query. For complex joins, DatabaseClient is usually the direct choice.

### 6.3. Cannot Express Custom SQL Expressions

QBE is not meant for writing:

- Column functions such as LOWER(), COALESCE(), or DATE_TRUNC().
- Comparisons between two columns.
- Subqueries or EXISTS clauses.
- Window functions.
- Full-text search or database-specific operators.
- Custom ESCAPE clauses for LIKE.
- JSON expressions or specialized data types.

If a query needs such expressions, use @Query or DatabaseClient.

### 6.4. Limited String Matching

QBE offers a handful of predefined string matching modes. It cannot express arbitrary search patterns such as regex or complex LIKE patterns with multiple wildcards and escape rules.

Specific support for regex or other modes also depends on the datastore. Do not rely on regex support in another Spring Data module and assume Spring Data R2DBC behaves identically.

### 6.5. Nulls and Primitive Defaults Easily Cause Confusion

Null usually means skip the condition. Matching NULL requires configuring includeNullValues or choosing another API. Primitives always hold default values, making "do not filter" awkward to represent.

For search forms, wrapper types and dedicated probes are generally safer.

### 6.6. Not a Tool for Arbitrary Projections

QBE is geared toward finding entities matching a probe. If you only need a few columns, a reporting DTO, aggregates, or calculations, QBE is usually not the right fit.

Use repository projections or DatabaseClient to map results into the required structure.

### 6.7. Matching Behavior Depends on the Database

Ignore case, empty strings, collations, data types, and some StringMatcher modes can yield different results across database engines.

QBE eliminates boilerplate SQL for simple queries, yet does not erase differences between databases. Test against your actual database engine.

## 7. When Should You Choose Derived Queries?

Derived queries are generated from repository method names.

For example:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByFullNameContainingIgnoreCase(String name);

    Flux<Customer> findByEmailIsNull();

    Flux<Customer> findByActiveTrueAndFullNameContainingIgnoreCase(
        String name
    );
}
~~~

Derived queries fit when:

- Query conditions are stable and expressible in method names.
- The number of condition combinations is small.
- You want the repository API to express business intent clearly.
- Custom SQL or overly complex condition grouping is unnecessary.

Avoid creating dozens of methods for every possible filter combination. When filters vary dynamically across many parameters, Criteria or QBE can be cleaner.

## 8. When Should You Choose @Query?

Use @Query when the SQL structure is relatively fixed and should be written explicitly on the repository.

For example:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email, active, version
        FROM customer
        WHERE active = :active
          AND LOWER(full_name) LIKE LOWER(:pattern)
        """)
    Flux<Customer> searchByName(
        @Param("active") Boolean active,
        @Param("pattern") String pattern
    );
}
~~~

@Query fits when:

- SQL needs explicit control.
- The query uses database functions or engine-specific syntax.
- Joins or projections are needed that derived queries or QBE cannot express conveniently.
- The SQL statement is stable and belongs beside the repository method.

The advantage is keeping SQL right next to the repository contract. The drawback is that dynamic queries with many conditional branches make the annotation long and hard to maintain. For complex optional filters, consider a template or custom repository fragment.

## 9. When Should You Choose R2dbcEntityTemplate and Criteria?

R2dbcEntityTemplate fits when a query needs dynamic conditions while still leveraging Spring Data entity mapping.

Example filter with required tenant, optional name, optional email, and optional active flag:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Customer> search(
        Long tenantId,
        String name,
        String email,
        Boolean active) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (name != null && !name.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + name.trim() + "%");
    }

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email")
            .is(email.trim());
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    Query query = Query.query(criteria)
        .limit(100);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

Criteria can be combined with AND and OR to construct far more flexible conditions than QBE. The template also supports sorting, limit, offset, and other entity operations.

Use Criteria when:

- Filters have many optional parameters.
- AND/OR condition groups are needed.
- Explicit NULL checks are required.
- You want to keep Spring Data entity mapping, conversions, and dialect handling.
- You do not need to write all SQL manually.

If the query requires joins, CTEs, or database-specific syntax that Query/Criteria cannot express, move to DatabaseClient.

## 10. When Should You Choose DatabaseClient?

DatabaseClient belongs to Spring R2DBC and lets you execute SQL directly. The application controls the statement, parameter binding, and Row mapping.

For example:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public Flux<CustomerSummary> searchSummary(String keyword) {
    String pattern = "%" + keyword.trim() + "%";

    return databaseClient.sql("""
            SELECT c.id, c.full_name, COUNT(o.id) AS order_count
            FROM customer c
            LEFT JOIN purchase_order o ON o.customer_id = c.id
            WHERE c.full_name LIKE :pattern
            GROUP BY c.id, c.full_name
            ORDER BY c.full_name
            """)
        .bind("pattern", pattern)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
}
~~~

This example uses a join, group by, and projection, so QBE is unsuitable. DatabaseClient lets you write the exact SQL required and map results to a dedicated DTO.

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    Long orderCount
) {}
~~~

Always bind input values instead of concatenating them into SQL strings. When using LIKE and wanting literal matching for wildcards, escape % and _ according to database syntax; parameter binding alone does not strip wildcard meaning.

## 11. Comparing the Options

| Criterion | Query by Example | Derived query | @Query | R2dbcEntityTemplate | DatabaseClient |
|---|---|---|---|---|---|
| Definition style | Probe + ExampleMatcher | Method name | SQL in annotation | Query + Criteria | Direct SQL |
| Optional conditions | Convenient with null properties | Usually needs separate methods | Possible, but annotation gets long | Very flexible | Very flexible |
| Simple AND/OR | matchingAll/matchingAny | Via method name | Arbitrary SQL | Combinable Criteria | Arbitrary SQL |
| Nested boolean groups | Unsuitable | Limited | Yes | Flexible via Criteria API | Full SQL control |
| NULL handling | Include null values, use carefully | IsNull/IsNotNull | Explicit SQL | isNull/isNotNull | Explicit SQL |
| String matching | Predefined modes | Predefined keywords | Arbitrary SQL | Criteria/LIKE | Arbitrary SQL |
| Joins and subqueries | Unsuitable | Limited per repository query | Yes | Not its strength | Well suited |
| Entity mapping | Automatic | Automatic | Automatic when returning matching entity | Automatic | Usually manual mapping |
| Custom projection | Limited | Possible via supported projections | Yes | API-dependent | Very flexible |
| Best suited for | Simple probe-based search | Stable business queries | Fixed, explicit SQL | Dynamic entity-level filters | Complex or specialized SQL |

## 12. Combining Multiple Approaches in One Application

You do not need to force every query into a single abstraction.

One application can:

- Use QBE for simple search screens with independent fields.
- Use derived queries for business operations with stable conditions.
- Use @Query for fixed SQL statements involving joins or database functions.
- Use R2dbcEntityTemplate for dynamic entity-level filters.
- Use DatabaseClient for reports, analytics, or complex SQL queries.

For maintainability, place complex queries inside repositories or custom repository fragments instead of scattering SQL across controllers. Services should coordinate business logic and compose reactive publishers.

### 12.1. Custom Repository Fragments

If a repository has many complex dynamic queries, extract the implementation into a separate fragment.

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> search(CustomerSearchFilter filter);
}
~~~

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

The CustomerSearchRepositoryImpl class can inject R2dbcEntityTemplate or DatabaseClient. This keeps the repository contract clean and isolates search logic in a clearly scoped component.

## 13. Common Mistakes

### 13.1. Using QBE for Every Type of Query

QBE suits simple probe-based searches. Using it for joins, subqueries, complex condition groups, or database expressions makes queries hard to express and understand.

Choose the abstraction based on query structure.

### 13.2. Forgetting Nulls Are Ignored by Default

If a probe has a null email, that usually does not mean email IS NULL. It usually means skip email.

To match NULL, use withIncludeNullValues carefully or use Criteria.isNull().

### 13.3. Using Primitives for Optional Filters

boolean false or int 0 can become unintended conditions. Use Boolean, Integer, or corresponding wrapper types so null represents "do not filter".

### 13.4. Not Ignoring ID and Version

If a probe carries an ID or version, they may enter the query condition and overly narrow results. Use withIgnorePaths for properties outside the filter.

### 13.5. Assuming matchingAny Creates Any OR Group

matchingAny() ORs selected probe properties together. It does not build arbitrary nested boolean groups. Use Criteria or SQL for complex structures.

### 13.6. Using String Matchers Without Checking the Database

Ignore case and StringMatcher behavior can depend on dialect, collation, and version. Test on the target database, especially with Unicode and accented text.

### 13.7. Using a Probe Holding Unrelated Domain State

A domain entity may hold default values or attributes populated elsewhere. Reusing that instance as a probe can accidentally add extra filters. Building a fresh probe from search inputs is far more predictable.

### 13.8. Expecting QBE to Automatically Join Relationships

QBE does not turn nested object properties or other aggregates into arbitrary SQL joins. Use SQL or an appropriate query API when data from multiple tables is needed.

## 14. Process for Choosing a Query Approach

When designing a search feature, you can follow this sequence:

1. Determine whether conditions are fixed or optional.
2. If they are independent property values, consider QBE.
3. If the query is fixed and the method name stays readable, consider a derived query.
4. If fixed SQL, joins, or specialized expressions are needed, consider @Query.
5. If dynamic condition assembly with entity mapping is needed, use R2dbcEntityTemplate with Criteria.
6. If full SQL control, projections, aggregations, or database-specific syntax are needed, use DatabaseClient.
7. If query logic is substantial, encapsulate it in a custom repository fragment.
8. Test on a real database for NULL differences, collation, data types, and dialect behavior.

## 15. Key Takeaways

Query by Example uses a probe and ExampleMatcher to build queries from entity values. It works well for simple filters, particularly when many properties can be omitted via null. Matchers allow selecting exact, containing, starting, ending, ignore case, and matchingAll/matchingAny combinations within what the store supports.

QBE's main limitation is that it cannot express arbitrary boolean condition groups, joins, subqueries, SQL expressions, or custom projections. When a query goes beyond that scope, pick derived queries for fixed conditions, @Query for declarative SQL, R2dbcEntityTemplate/Criteria for dynamic entity-level filters, or DatabaseClient for complex SQL. Choosing the right level of abstraction keeps queries readable, testable, and prevents forcing QBE to solve problems it was not designed for.

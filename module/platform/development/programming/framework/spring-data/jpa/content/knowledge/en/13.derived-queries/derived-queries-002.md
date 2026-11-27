# Query Lookup Strategy: CREATE, USE_DECLARED_QUERY, and CREATE_IF_NOT_FOUND

## 1. What is a query lookup strategy?

Spring Data JPA provides several ways to determine the query for a repository method. When creating a repository, the framework must decide whether to derive the query from the method name, from a `@Query` declaration, or from a JPA named query. This selection rule is called the **query lookup strategy**.

The three strategies available in `QueryLookupStrategy.Key`:

| Strategy | How the query is resolved | When no declared query exists |
| --- | --- | --- |
| `CREATE` | Parses the method name to create the query | Continues creating the query from the method name; fails if the name is invalid |
| `USE_DECLARED_QUERY` | Looks up a declared query, such as `@Query` or a named query | Throws an error because no declared query was found |
| `CREATE_IF_NOT_FOUND` | Looks for a declared query first; if none exists, parses the method name | Falls back to query derivation |

`CREATE_IF_NOT_FOUND` is the default strategy in Spring Data JPA. The name `CREATE` here refers to creating a query from the method name, not the SQL `CREATE TABLE` statement or schema creation operations.

## 2. CREATE: creating a query from the method name

With `CREATE`, Spring Data parses the repository method name and maps parts of the name into conditions based on Entity properties. Example:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
        CustomerStatus status,
        Instant createdAt
    );

    boolean existsByEmail(String email);

    long countByStatus(CustomerStatus status);
}
```

The framework parses components such as:

- `findBy`: queries and returns matching results.
- `Email`: condition on the `email` property.
- `And`: combines two conditions.
- `CreatedAtAfter`: compares whether the timestamp is greater than the parameter.
- `OrderByCreatedAtDesc`: sorts descending by `createdAt`.
- `existsBy`: checks whether at least one matching record exists.
- `countBy`: counts matching records.

Other common keywords include `Or`, `Between`, `LessThan`, `GreaterThan`, `Like`, `Containing`, `StartingWith`, `EndingWith`, `In`, `NotIn`, `IsNull`, `IsNotNull`, `True`, `False`, `IgnoreCase`, `Distinct`, `First`, and `Top`. Exact syntax support depends on the property type and the capabilities of the Spring Data version.

Query derivation references Java property names in the Entity, not physical column names. If the Entity has `createdAt` mapped to column `created_at`, the method must use `findByCreatedAt...`, not `findByCreated_at...`.

For nested properties, Spring Data can resolve property paths. If a property name is ambiguous, an underscore can be used as an explicit separator, for example `findByAddress_ZipCode(...)` to specify `address.zipCode`.

The advantage of CREATE is that methods are short, readable, and well-suited for simple CRUD queries. The disadvantage is that method names can become long or hard to understand when conditions are complex or involve multiple joins, projections, aggregates, or database-specific logic.

## 3. USE_DECLARED_QUERY: requiring a declared query

With `USE_DECLARED_QUERY`, Spring Data requires every query method to have an explicitly declared query. Common declared query sources:

- `@Query` on the repository method.
- JPA `@NamedQuery` or `@NamedQueries` declared on the Entity.
- Named queries declared in `orm.xml`.

If no declared query is found for a method, the repository fails during query initialization. This is a fail-fast approach to detect missing queries at startup/repository initialization rather than silently deriving one from the method name.

Example using `@Query` with JPQL:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("select c from Customer c where lower(c.email) = lower(:email)")
    Optional<Customer> findByEmail(@Param("email") String email);
}
```

JPQL uses the entity name `Customer` and the Java property `email`, not SQL table/column names. `@Param("email")` binds the method parameter to `:email` in the query. Positional parameters `?1`, `?2` can also be used instead of named parameters.

A declared query can also be native SQL when database-specific syntax or features are genuinely needed:

```java
@Query(
    value = "select * from customer where email = :email",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(@Param("email") String email);
```

Native queries use physical table and column names in the schema. You need to verify database compatibility, pagination/sorting behavior, and result mapping; do not write native SQL using Java property names.

## 4. Named queries and naming conventions

JPA allows declaring named queries using `@NamedQuery`. Spring Data JPA looks up named queries following the convention `<EntitySimpleName>.<repositoryMethodName>`.

Entity example:

```java
@Entity
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = ?1"
)
public class Customer {
    @Id
    private Long id;

    private String email;
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

With the method name `findByEmail`, the framework can locate the named query `Customer.findByEmail`. Queries declared with `@NamedQuery` are JPQL, so they reference the Entity and Java properties.

Named queries can be placed in `orm.xml` if the project wants to separate queries from Entity code. When using XML, the query name still needs to match the convention looked up by the repository method.

If the same method has both `@Query` and a named query with the same name, the `@Query` declaration on the method takes precedence in the declared query lookup mechanism. Avoid declaring conflicting query sources for the same method so maintainers know which one is authoritative.

## 5. CREATE_IF_NOT_FOUND: declared query first, derived query second

This is the balanced choice and the default in Spring Data JPA:

1. If the method has `@Query`, use the query declared on the method.
2. Otherwise, look for a matching named query by name.
3. If none exists, parse the method name to derive the query.

Example of a repository using both styles:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    // No @Query or named query: the query is derived from the method name.
    Optional<Customer> findByEmail(String email);

    // Has @Query: uses the JPQL declared below.
    @Query("select c from Customer c where c.status = :status")
    List<Customer> searchByStatus(@Param("status") CustomerStatus status);
}
```

CREATE_IF_NOT_FOUND keeps simple queries concise while allowing complex queries to be explicitly declared in JPQL or native SQL. However, a method can accidentally switch from a derived query to a named query if someone adds a named query with a matching name. Therefore, manage query names carefully and test queries as part of the repository contract.

## 6. Configuring the strategy for repositories

Spring Data JPA lets you choose the strategy via the `queryLookupStrategy` attribute of `@EnableJpaRepositories`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer.repository",
    queryLookupStrategy = QueryLookupStrategy.Key.USE_DECLARED_QUERY
)
public class JpaRepositoryConfiguration {
}
```

Replace the enum value with `CREATE` or `CREATE_IF_NOT_FOUND` according to your project's policy. If the application uses Spring Boot auto-configuration, only add `@EnableJpaRepositories` when you explicitly need to configure repository scanning/strategy; specify base packages clearly and avoid duplicate configuration with other repository registrars.

Do not confuse `queryLookupStrategy` with Hibernate dialect configuration, naming strategies, or DDL. It determines how Spring Data locates the query definition for a repository method and does not alter the database schema.

## 7. Which strategy should you choose?

| Need | Suitable strategy | Reason |
| --- | --- | --- |
| Simple CRUD repositories with clear method names | `CREATE` | Focuses on query derivation, minimal JPQL to write |
| Want to enforce explicit declarations on every query method | `USE_DECLARED_QUERY` | Missing queries are caught during repository initialization |
| Want to combine simple queries and declared queries | `CREATE_IF_NOT_FOUND` | Uses declared queries first, falls back to method names |

`USE_DECLARED_QUERY` is useful when a project wants strict control over every query, reviews JPQL/native SQL, and avoids long method names. In return, every query method needs an explicit declaration and query maintenance is more centralized.

`CREATE` suits convention-driven repositories, but requires keeping method names understandable and verifying property paths. `CREATE_IF_NOT_FOUND` fits most applications because it lets you choose the representation based on each query's complexity.

## 8. Common errors during query lookup

**Property not found when creating repository.** A derived method may reference an incorrect field name or property path. Cross-check with the Entity, paying attention to camelCase and nested relationships.

**Application fails on startup due to missing declared query.** If using `USE_DECLARED_QUERY`, add `@Query`, a named query, or reconfigure the strategy if you want fallback to derivation.

**Named query is not recognized.** Check the `EntitySimpleName.methodName` naming format, the actual Entity name, the repository method, and whether `orm.xml` is loaded.

**Unexpected results even though the method name is valid.** Check parser keywords, And/Or precedence, property order, IgnoreCase, null handling, and generated SQL. Long methods may fail to express the intended logic; switch to `@Query` when clearer control is needed.

**JPQL reports table/column not found.** JPQL uses Entity and Java property names; native SQL uses physical names. Confirm the query type before fixing names.

**Method has `@Query` but is interpreted by its method name.** Check the active strategy. `CREATE` focuses on query derivation; to use declared queries, you need a strategy with declared-query lookup such as `USE_DECLARED_QUERY` or `CREATE_IF_NOT_FOUND`.

**Query succeeds at startup but fails at execution.** Test the query against a real database/dialect, representative data, and parameter types. Some errors related to generated SQL, schema, or data only surface at runtime.

## 9. Does query lookup strategy affect performance?

The strategy itself mainly determines how query definitions are located and created when the repository is initialized. It is not a toggle for caching, JDBC batching, or query plan optimization. A derived query and an equivalent declared JPQL query can generate similar SQL.

Actual performance depends on the generated SQL, indexes, cardinality, execution plan, fetch strategy, number of round-trips, result size, and the database. When a query is slow, inspect the SQL and execution plan rather than switching from CREATE to USE_DECLARED_QUERY expecting an automatic speedup.

## 10. Repository testing workflow

1. For derived queries, verify that method names match Entity properties and run properly with boundary data.
2. For `@Query`, verify JPQL references the right Entity/fields; for native queries, verify the schema's table/column names.
3. For named queries, verify the naming convention and that the expected query is loaded.
4. If using `USE_DECLARED_QUERY`, verify that every query method has a declared query to catch missing declarations.
5. Run integration tests against a database compatible with the deployment environment, rather than relying only on mocked repositories.
6. Verify results, nulls, empty collections, pagination, sorting, and empty result sets.
7. For performance-critical queries, inspect the SQL, measure query counts, and check the execution plan.

## 11. Summary of selection rules

- `CREATE`: creates queries from method names.
- `USE_DECLARED_QUERY`: requires finding `@Query`, a named query, or another declared query; no fallback.
- `CREATE_IF_NOT_FOUND`: searches for a declared query first, then derives from the method name if none is found; this is the default.
- `@Query` is suitable when explicit JPQL/native SQL is needed; named queries are suitable when declaring named queries tied to Entities or XML.
- The query lookup strategy determines the query source, whereas performance depends on SQL and the database.

Choose the strategy based on the level of control your project requires. Whether queries are derived or declared, keep method names clear, manage query sources cleanly, and test against a real database to avoid runtime-only errors.
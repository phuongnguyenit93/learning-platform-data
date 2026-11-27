# Applying Query Hints and Provider-Dependent Limitations

## Objectives

A query hint is an additional directive attached to a JPA query. Hints can instruct the provider to apply a timeout, adjust data-loading behavior, control caching, or optimize result fetching. Spring Data JPA lets you attach hints to repository methods via `@QueryHints`; when using `EntityManager` directly, you can call `Query.setHint`.

Some hints are standardized by Jakarta Persistence, while others are only supported by Hibernate or other providers. Hints serve as guidance to the provider and driver; not every hint is enforced identically across all databases.

After this lesson, you will be able to:

- Understand which layer query hints act on and how they differ from bind parameters.
- Declare JPA-standard hints and vendor-specific hints.
- Use `@QueryHints` on Spring Data repositories.
- Control whether hints apply to the count query of a `Page`.
- Configure query timeouts, lock timeouts, caching, fetch size, and read-only mode.
- Distinguish query hints from `@Transactional(readOnly = true)`, `@Lock`, and `@EntityGraph`.
- Recognize compatibility limits across JPA providers, JDBC drivers, and databases.
- Write tests to ensure hints work as intended and do not become mandatory business-logic dependencies.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. Hibernate-specific examples should be cross-checked against the exact Hibernate version managed by Spring Boot.

## 1. What is a query hint?

A JPA query can be configured with additional properties beyond the JPQL or SQL text. Those properties are called query hints.

For example, the same JPQL:

```java
select e
from Employee e
where e.active = true
```

can be executed with different timeouts, cache modes, or fetch-size hints. A query hint does not change the business conditions in the query; it provides metadata to the JPA provider or JDBC driver about how to execute it.

Common hint categories:

| Category | Purpose |
|---|---|
| Timeout | Limits how long to wait for a query or lock |
| Cache | Controls reading from or writing to shared cache or query cache |
| Fetch | Suggests how to retrieve data and how many rows to fetch per round trip |
| Read-only | Reduces entity change tracking in providers that support it |
| Lock | Adjusts wait time when acquiring locks |
| Diagnostic | Adds information to assist SQL tracing |

Hints can be applied to JPQL, Criteria queries, or native queries, though exact effectiveness depends on query type, provider, and database.

### 1.1. Query hints differ from bind parameters

Bind parameters pass values used in query conditions:

```java
@Query("select e from Employee e where e.email = :email")
Optional<Employee> findByEmail(@Param("email") String email);
```

Query hints configure how the query executes:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "1500"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveEmployees();
```

`:email` is data participating in the `WHERE` condition. `jakarta.persistence.query.timeout` is an execution-time directive. Do not use hints to pass filter criteria or replace bind parameters.

### 1.2. Hints are not a performance guarantee

A hint may be:

- Supported and applied by the provider.
- Forwarded to the JDBC driver or database as a corresponding configuration.
- Ignored because the provider does not support it or the query is incompatible.
- Differently effective across provider/driver versions.

Therefore, a query must still return accurate results even if an optimization hint is ignored. For hints affecting timeouts or locking, verify that the provider and database actually enforce the required behavior.

## 2. Two categories of query hints

### 2.1. JPA-standard hints

Jakarta Persistence defines several standard hint names. Common ones include:

| Hint | Common values | Meaning |
|---|---|---|
| `jakarta.persistence.query.timeout` | Number of milliseconds | Query wait timeout |
| `jakarta.persistence.lock.timeout` | Number of milliseconds | Lock acquisition timeout |
| `jakarta.persistence.cache.retrieveMode` | `USE` / `BYPASS` | Whether to read from shared cache |
| `jakarta.persistence.cache.storeMode` | `USE` / `BYPASS` / `REFRESH` | How to write to shared cache |
| `jakarta.persistence.fetchgraph` | EntityGraph | Uses graph as fetch plan |
| `jakarta.persistence.loadgraph` | EntityGraph | Augments fetch plan with graph |

Standard names use the `jakarta.persistence` prefix in Jakarta Persistence. Older projects using Java Persistence API may use names under `javax.persistence`; do not mix hint names and imports between the two API generations.

Standard hints improve portability, yet actual enforcement still depends on the capabilities of the provider, JDBC driver, and database. For instance, a timeout may be translated into a JDBC statement timeout, while exact precision and cancellation timing depend on the underlying system.

### 2.2. Vendor-specific hints

Providers may offer proprietary hints. With Hibernate, common names in Hibernate 6 versions include:

| Hibernate hint | Purpose |
|---|---|
| `org.hibernate.readOnly` | Marks entity results read-only for Hibernate's dirty checking |
| `org.hibernate.fetchSize` | Suggests JDBC fetch size |
| `org.hibernate.cacheable` | Enables query caching |
| `org.hibernate.cacheRegion` | Specifies the query cache region |
| `org.hibernate.comment` | Adds an SQL comment for diagnostics |
| `org.hibernate.timeout` | Timeout in seconds in the corresponding Hibernate hint API |

Hint lists, constant names, and application behavior can change across Hibernate versions. Prefer constants provided by the provider if your version offers corresponding APIs; avoid copying hint names from examples for other versions without checking documentation.

Do not place vendor-specific hints into a repository shared across multiple providers if the application needs provider portability. When they are necessary, document the dependency and test on the actual deployed provider.

## 3. Using @QueryHints in Spring Data JPA

Spring Data JPA provides the `@QueryHints` annotation in `org.springframework.data.jpa.repository`. Each element inside is a standard Jakarta Persistence `@QueryHint` annotation.

Example:

```java
import jakarta.persistence.QueryHint;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "1500"
        )
    })
    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees();
}
```

Here:

- `@QueryHints` is a Spring Data JPA annotation accepting an array of hints.
- `@QueryHint` is a Jakarta Persistence annotation describing one hint's name and value.
- `value = "1500"` is a string per annotation syntax; for the standard query timeout, this value represents milliseconds.
- Hints are attached to the query executed by the repository method.

Multiple hints can be declared:

```java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "1500"
    ),
    @QueryHint(
        name = "org.hibernate.readOnly",
        value = "true"
    ),
    @QueryHint(
        name = "org.hibernate.fetchSize",
        value = "100"
    )
})
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
List<Employee> findActiveEmployeesForReport();
```

In this example, query timeout is JPA-standard; read-only and fetch size are Hibernate-specific. If the application uses a different provider, the two Hibernate hints may have no effect.

Simply declaring an annotation does not guarantee the provider will enforce every hint. Inspect SQL logs, provider configuration, and test behavior on the target database.

## 4. forCounting: do hints apply to the count query?

A method returning `Page<T>` typically executes two queries:

1. A query retrieving the page content.
2. A count query determining the total number of elements/pages.

Spring Data JPA has a `forCounting` attribute on `@QueryHints`. It defaults to `true`; set it to `false` to prevent applying those hints to the count query.

Example:

```java
@QueryHints(
    value = {
        @QueryHint(
            name = "org.hibernate.fetchSize",
            value = "100"
        ),
        @QueryHint(
            name = "org.hibernate.readOnly",
            value = "true"
        )
    },
    forCounting = false
)
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
Page<Employee> findActiveEmployees(Pageable pageable);
```

Here the hints apply only to the content query, not the count query. This is useful when hints only make sense for queries returning entities or reading many rows, whereas a count query returns a single scalar value.

For a query with an explicit count query:

```java
@Query(
    value = """
            select e
            from Employee e
            where e.department.id = :departmentId
            """,
    countQuery = """
            select count(e)
            from Employee e
            where e.department.id = :departmentId
            """
)
@QueryHints(
    value = @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    ),
    forCounting = false
)
Page<Employee> findByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

If you want the timeout to apply to both the content query and the count query, keep `forCounting = true` or omit the attribute. Choose based on real needs: count queries can also be expensive, especially with `JOIN`, `DISTINCT`, or large tables.

`forCounting = false` only controls whether Spring Data applies hints to the count query; it does not skip the count query and does not turn `Page` into `Slice`.

## 5. Query timeout

Timeouts cap how long to wait for a query. JPA-standard hint:

`jakarta.persistence.query.timeout`

Example:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithinTwoSeconds();
```

The standard value is expressed in milliseconds. However, it is a query hint; the provider may translate it into a JDBC statement timeout or equivalent mechanism. Drivers and databases can vary in resolution, limits, and how statements are cancelled.

When a timeout occurs, the application may receive an exception such as `QueryTimeoutException` or a Spring-translated persistence/SQL exception. Handle it at the transaction boundary and inspect transaction state after failure. Do not continue writing data in a transaction already marked rollback-only.

### 5.1. Hibernate-specific timeout

Hibernate also has its own timeout hint:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.timeout",
        value = "2"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithHibernateTimeout();
```

This Hibernate hint uses seconds in the corresponding API, unlike the millisecond unit of the JPA-standard query timeout. Do not declare both "just to be safe"; choose one mechanism, verify your Hibernate version, and test actual timeout behavior.

### 5.2. Timeouts do not replace query optimization

If a query is slow, inspect:

- Execution plans and indexes.
- Number of rows scanned, `JOIN`s, and filter conditions.
- N+1 queries or overly broad fetch plans.
- Pagination and result limits.
- Lock contention and long-running transactions.

A timeout protects resources when a query exceeds a threshold; it does not make queries faster and does not resolve underlying performance causes.

## 6. Lock timeout and @Lock

The `jakarta.persistence.lock.timeout` query hint adjusts how long to wait when acquiring locks in scenarios supported by the provider/database. Example:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findForUpdate(@Param("id") Long id);
```

The two annotations serve distinct roles:

- `@Lock`: requests a lock mode for the query, such as `PESSIMISTIC_WRITE`.
- `@QueryHints`: supplies extra hints, in this case the lock wait timeout.

Pessimistic locking normally requires an active transaction. If the database does not support timeouts or the provider does not translate the hint properly, behavior may differ from expectations. Some databases use dedicated statements or syntax to set lock timeouts.

Do not confuse lock timeout with query timeout:

| Type | Controls |
|---|---|
| Query timeout | How long the query is allowed to run/wait |
| Lock timeout | How long to wait to acquire a lock |
| Transaction timeout | Time limit for the transaction per the transaction manager/provider mechanism |

These three limits can interact, but they do not replace one another. When designing concurrent workflows, verify deadlocks, lock acquisition order, lock hold duration, and retry policies.

## 7. Cache hints

JPA provides a shared cache at the persistence unit/provider level. Standard hints control cache reads and writes.

### 7.1. Cache retrieve mode

`jakarta.persistence.cache.retrieveMode` accepts values such as:

- `USE`: allows reading data from the shared cache if present.
- `BYPASS`: bypasses the shared cache on reads.

Example:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.cache.retrieveMode",
        value = "BYPASS"
    )
)
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findByIdBypassingSharedCache(@Param("id") Long id);
```

In annotations, `value` is a string; the provider interprets it according to the standard hint type. With programmatic APIs, you can pass the `CacheRetrieveMode.BYPASS` enum.

### 7.2. Cache store mode

`jakarta.persistence.cache.storeMode` controls placing results into the shared cache:

- `USE`: allows storing per cache policy.
- `BYPASS`: does not store results in the shared cache.
- `REFRESH`: updates the cache from read data when supported by the provider.

Example:

```java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.cache.retrieveMode",
        value = "BYPASS"
    ),
    @QueryHint(
        name = "jakarta.persistence.cache.storeMode",
        value = "BYPASS"
    )
})
@Query("select e from Employee e where e.id = :id")
Optional<Employee> findWithoutSharedCache(@Param("id") Long id);
```

JPA's shared cache differs from Hibernate's query cache. The shared cache stores entity state by identity; Hibernate's query cache stores query results via its own mechanism and typically works alongside the second-level cache to resolve entity state.

### 7.3. Hibernate query cache

Hibernate can enable query caching with vendor-specific hints:

```java
@QueryHints({
    @QueryHint(name = "org.hibernate.cacheable", value = "true"),
    @QueryHint(name = "org.hibernate.cacheRegion", value = "employee-active")
})
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveCached();
```

Setting `org.hibernate.cacheable = true` alone is not enough to make caching work. You must configure the query cache, second-level cache/cache region, and appropriate invalidation mechanisms. Query caching may not pay off for frequently updated data or queries returning many rarely reused results.

Do not enable query caching on every repository method. Measure hit rates, memory usage, invalidation, and data freshness before broad adoption.

## 8. Read-only hint vs. @Transactional(readOnly = true)

Hibernate supports the hint:

`org.hibernate.readOnly`

Example:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.readOnly",
        value = "true"
    )
)
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveReadOnly();
```

With Hibernate, this hint can mark entities loaded by the query as read-only with respect to dirty checking, reducing change-tracking overhead in certain cases.

Distinguish this from:

```java
@Transactional(readOnly = true)
public List<Employee> getActiveEmployees() {
    return repository.findActiveEmployees();
}
```

`@Transactional(readOnly = true)` is a Spring-layer transaction attribute. It can be used by the transaction manager/provider as an optimization hint or connection configuration. It is not synonymous with the per-query `org.hibernate.readOnly` hint.

Neither is a database authorization mechanism. Do not rely on read-only hints to prevent unauthorized `UPDATE` statements. If business rules prohibit writes, enforce permissions, transactions, and database constraints appropriately.

If an entity is loaded read-only and then mutated in memory, do not expect Hibernate to dirty-check and persist those changes like a normal managed entity. Only use it when the use case is genuinely read-only.

## 9. Fetch size and JDBC driver-dependent limits

Hibernate supports the hint:

`org.hibernate.fetchSize`

Example:

```java
@QueryHints(
    @QueryHint(
        name = "org.hibernate.fetchSize",
        value = "200"
    )
)
@Query("select e from Employee e order by e.id")
List<Employee> streamableEmployees();
```

Fetch size suggests how many rows the JDBC driver retrieves per batch when reading a `ResultSet`. It can reduce round trips or memory consumption for certain large reads, though behavior depends on the driver and database.

Fetch size is not the same as page size:

- `Pageable` limits how many records belong to a single page and can generate `LIMIT`/`OFFSET` or equivalent syntax.
- Fetch size affects how the driver reads rows from the `ResultSet`; it does not necessarily limit the total query results.

With PostgreSQL JDBC, cursor-based fetching also depends on autocommit/transaction settings and how the `ResultSet` is consumed. Some drivers may ignore fetch size or load the entire result set if preconditions are not met.

When processing very large datasets, consider Spring Data `Stream<T>`, version-appropriate scrolling/batch APIs, keyset pagination, or batch processing. Close streams and keep the transaction open while reading as required by the provider.

## 10. EntityGraph and fetch hints

JPA has the standard hints `jakarta.persistence.fetchgraph` and `jakarta.persistence.loadgraph` to pass an `EntityGraph` to a query. In Spring Data JPA, using the `@EntityGraph` annotation is usually more readable.

Example:

```java
@EntityGraph(attributePaths = {"department"})
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveWithDepartment();
```

`EntityGraph` describes which associations to load for a use case. It addresses the fetch plan; it is not a mechanism for binding query filter conditions.

The two standard hints:

- `fetchgraph`: attributes in the graph are treated as eager for the query; attributes absent from the graph follow fetch-graph rules.
- `loadgraph`: attributes in the graph are added to the default fetch plan.

Details of whether the provider generates a `JOIN` or additional `SELECT` statements can vary. `EntityGraph` does not guarantee a single SQL statement. Inspect generated SQL and avoid overly wide fetch plans, especially when multiple collections are involved.

## 11. Using query hints directly with EntityManager

When not using repository annotations, hints can be set directly on a query:

```java
@Repository
public class EmployeeSearchDao {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Employee> findActive() {
        TypedQuery<Employee> query = entityManager.createQuery(
                """
                select e
                from Employee e
                where e.active = true
                order by e.fullName
                """,
                Employee.class
        );

        query.setHint("jakarta.persistence.query.timeout", 1500);
        query.setHint("org.hibernate.readOnly", true);
        query.setHint("org.hibernate.fetchSize", 100);

        return query.getResultList();
    }
}
```

With the programmatic API, hint values are `Object`s. Pass the data type expected by JPA/the provider; for instance, the standard timeout can be passed as an integer number of milliseconds, whereas the `@QueryHint` annotation represents `value` as a `String`.

You can check supported hints via provider documentation and behavioral testing. There is no portable API guaranteed to enumerate every vendor-specific hint understood by a provider.

## 12. Provider-dependent limitations

Query hints are one of the easiest places to introduce tight coupling to Hibernate or a specific database. Before using them, classify each hint:

| Question | How to evaluate |
|---|---|
| Is the hint in Jakarta Persistence? | Prefer standard names if they meet the need |
| Is the hint Hibernate-only? | Document the dependency and version |
| Is the hint supported by the driver? | Verify JDBC driver/database |
| Could the hint be ignored? | Ensure query stays correct without optimization hints |
| Does the hint affect results or only performance? | Test semantics and failure behavior |
| Does the hint apply to count/native queries? | Verify actual Spring Data and provider behavior |
| Does the hint alter transaction state? | Check exceptions, rollbacks, and locks |

Specific limitations include:

- Hibernate hint names and API constants can change between versions.
- Timeouts do not guarantee query cancellation at an exact millisecond boundary.
- Fetch size does not guarantee the driver uses cursors or streaming.
- Cache hints do not guarantee caches are configured, hit, or always fresh.
- Read-only hints do not replace database write permissions.
- Lock timeouts depend on provider/database capabilities and may be unsupported.
- A hint valid on JPQL may not carry the same meaning on a native query.
- Count queries may require a different set of hints than content queries.

### 12.1. Unsupported hints

A provider may silently ignore vendor-specific hints it does not recognize. In other cases, warnings or exceptions may be raised due to invalid value types or unsupported hints.

Do not treat successful application startup as proof that hints are applied. Inspect SQL/logs/driver metrics and measure actual behavior.

## 13. Testing query hints

Tests should verify both query results and the effect the hint is expected to produce.

Example repository method:

```java
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.query.timeout",
        value = "2000"
    )
)
@Query("select e from Employee e where e.email = :email")
Optional<Employee> findByEmailWithTimeout(@Param("email") String email);
```

Functional test:

```java
@DataJpaTest
class EmployeeQueryHintTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void queryWithHintReturnsExpectedEmployee() {
        repository.save(new Employee(
                "An Nguyen",
                "an@example.com",
                true
        ));

        Optional<Employee> result =
                repository.findByEmailWithTimeout("an@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getFullName())
                .isEqualTo("An Nguyen");
    }
}
```

This test confirms the query still returns accurate data. It does not prove the driver enforced the timeout. To test timeouts, write an integration test with a query of controllable execution duration against your actual deployed database/driver; avoid relying on arbitrary sleep durations as proof.

What should be tested:

- Query remains correct if optimization hints are unsupported.
- Actual timeout enforcement and thrown exceptions.
- Lock timeouts under concurrent transactions holding locks.
- Whether count queries receive hints per `forCounting`.
- Cache hits/misses and invalidation if caching is enabled.
- Fetch size/streaming on the real driver.
- Read-only hints behave as expected on your Hibernate version.
- `EntityGraph` and query hints do not cause N+1 queries or overly broad data loads.

For tests involving locks, caches, timeouts, and driver behavior, use Testcontainers or an equivalent database environment. Embedded databases cannot fully represent production PostgreSQL/MySQL/Oracle behavior.

## 14. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Hint has no effect | Provider/driver does not support it or query does not apply hint | Check documentation, SQL/logs, and test on exact version |
| Query timeout duration differs from expectation | Different units, driver, or database resolution | Distinguish JPA timeout in ms from Hibernate timeout in seconds |
| Count query is slow despite hint on main query | Hint not applied to count query or count query differs | Check `forCounting` and declare appropriate hints |
| Read-only entity still mutated in Java | Read-only does not freeze Java objects or act as authorization | Avoid modifying entities in read-only use cases; enforce write guards elsewhere |
| Fetch size does not reduce memory | Driver loads entire ResultSet or cursor preconditions not met | Check driver, transactions, streaming, and paging |
| Cache returns stale data | Cache region/invalidation/update policy misconfigured | Check cache provider, consistency, and expiration |
| Lock timeout ignored | Database/provider does not support corresponding hint | Verify lock mode and database syntax |
| Hibernate hint breaks after upgrade | Hint name or API changed | Use version-matching constants/docs and integration tests |
| Annotation fails to compile | Imported wrong QueryHints/QueryHint | Use Spring Data `QueryHints` and Jakarta Persistence `QueryHint` |
| Native query does not receive hint as expected | Hints depend on query type and provider | Test native queries separately on target database |

## 15. Checklist for applying query hints

- [ ] Identify the goal: timeout, cache, fetch, read-only, lock, or diagnostics.
- [ ] Prefer JPA-standard hints when available.
- [ ] Document provider/version when using vendor-specific hints.
- [ ] Distinguish standard timeout units from Hibernate-specific timeout units.
- [ ] Set `forCounting` appropriately for `Page`/count queries.
- [ ] Never use read-only hints as a security mechanism.
- [ ] Do not confuse fetch size with `Pageable`/page size.
- [ ] Use `EntityGraph` when the goal is describing a fetch plan.
- [ ] Verify transactions when using locks or timeouts.
- [ ] Measure performance before and after adding hints.
- [ ] Test with the actual provider, JDBC driver, and database.
- [ ] Ensure business correctness holds even if optimization hints are ignored.

## Conclusion

Query hints supply extra directives to the JPA provider for timeouts, caching, fetching, read-only handling, and locking. Spring Data JPA attaches hints to repository methods with `@QueryHints`; `EntityManager` supports setting hints directly via `setHint`.

Prefer Jakarta Persistence standard hints whenever possible. For Hibernate- or database-specific hints, check versions and drivers, measure real impact, and keep query correctness independent of optimizations that might be ignored. `forCounting` lets you control count query hints separately, while `@Lock`, `@EntityGraph`, and `@Transactional(readOnly = true)` address distinct aspects of query execution.
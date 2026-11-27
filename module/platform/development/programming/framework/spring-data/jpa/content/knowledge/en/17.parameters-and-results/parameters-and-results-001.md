# Positional and Named Parameter Binding with @Param

## 1. Why bind parameters?

Repository queries often receive data from requests or business logic: emails, statuses, date ranges, customer IDs, lists of IDs, and so on. These values must be passed into the query safely and with the right type.

Spring Data JPA supports two main ways to bind parameters in JPQL:

- **Positional:** the query references parameters by index such as `?1`, `?2`.
- **Named:** the query references parameters by name such as `:email`, `:status`; the method uses `@Param` to link the query parameter name with the Java parameter.

Parameter binding lets the provider send values separately from the query structure, typically via a prepared statement. Do not concatenate input strings directly into JPQL/SQL because of SQL injection risks, escaping bugs, and poor statement reusability.

## 2. Positional binding with ?1, ?2

In JPQL, positional parameters are numbered starting from 1. `?1` corresponds to the first method parameter, `?2` corresponds to the second method parameter:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("select c from Customer c where c.email = ?1 and c.status = ?2")
    Optional<Customer> findByEmailAndStatus(String email, CustomerStatus status);
}
```

The order in the method signature must match the indices in the query. If you reorder the Java parameters without updating the query, values may be bound to the wrong position or the provider may report a data type error.

A positional parameter can be used multiple times with the same index:

```java
@Query("""
    select c from Customer c
    where c.email = ?1 or c.backupEmail = ?1
    """)
List<Customer> findByPrimaryOrBackupEmail(String email);
```

Do not mix positional parameters with named parameters in the same JPQL query. Choose one style consistently so the query remains readable and avoids binding errors.

## 3. Named binding with @Param

Named parameters are usually easier to maintain when a query has many parameters or when the method signature order changes. Use `:parameterName` in JPQL and `@Param("parameterName")` on the Java parameter:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c from Customer c
        where c.email = :email
          and c.status = :status
        """)
    Optional<Customer> findCustomer(
        @Param("email") String email,
        @Param("status") CustomerStatus status
    );
}
```

`@Param` belongs to the package `org.springframework.data.repository.query.Param`. The name in the annotation must match the name after `:` in the query exactly; names are case-sensitive. Do not include the `:` prefix in the annotation value.

This example continues to work if you reorder the method parameters while keeping the `@Param` mappings intact. Still, keep signatures readable and write query tests to prevent errors during refactoring.

## 4. Is @Param mandatory?

Spring Data can discover Java parameter names in some configurations if classes are compiled with parameter name metadata, such as the `-parameters` compiler option. When parameter names are discovered successfully, the query can reference the method parameter name directly without the annotation.

Example:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(String email);
```

To avoid depending on compiler configuration, framework version, or build metadata, explicit `@Param` is a clear and reliable approach for repository queries with named parameters. When a codebase already follows a different convention, apply it consistently and verify that the compiler preserves parameter names.

Do not confuse `@Param` with validation annotations like `@NotNull` or web annotations like `@RequestParam`. `@Param` only links a method parameter name to a placeholder in a repository query.

## 5. Comparing positional and named parameters

| Criterion | Positional (`?1`) | Named (`:name` + `@Param`) |
| --- | --- | --- |
| Binding mechanism | By parameter position | By declared name |
| Query readability | Hard to tell meaning when there are many positions | Names express the role of each value |
| Reordering method parameters | Can break binding if the query is not updated | Mapping remains valid if `@Param` names stay the same |
| Best suited for | Short queries with few parameters | Queries with many parameters or needing maintainability |

For queries with a single parameter, positional binding is concise. For queries with multiple conditions, named parameters are usually easier to review because readers can see which value is used for each condition.

## 6. Binding parameters for IN conditions

Collection parameters can be used with `IN` in JPQL:

```java
@Query("select c from Customer c where c.status in :statuses")
List<Customer> findByStatuses(
    @Param("statuses") Collection<CustomerStatus> statuses
);
```

The provider binds the collection elements into the condition. You should clearly define how an empty collection is handled: should the application return an empty list, ignore the filter, or reject the request? Do not rely on how each provider/database handles `IN ()`. You can validate the collection in the service layer before calling the repository.

For very large lists, be mindful of database/driver limits on the number of bind parameters. Consider batching, temporary tables, table-valued parameters, or another database-appropriate mechanism if a query needs thousands of values.

## 7. Binding parameters for LIKE

With `LIKE`, the parameter carries the pattern. You can construct the pattern in the service layer or use `concat` in JPQL:

```java
@Query("""
    select c from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    """)
List<Customer> searchByName(
    @Param("keyword") String keyword
);
```

In this example, `%` on both sides enables substring matching. If the user enters `%` or `_`, those characters act as LIKE wildcards; if business requirements expect literal character matching, escape them according to LIKE syntax and declare an appropriate escape character.

Do not concatenate input directly into the query string. Bind the value and handle wildcards according to the intended search semantics.

## 8. Null values and data types

Binding `null` does not automatically ignore a condition. For example, `c.status = :status` with `status = null` does not return rows with a null status under standard comparison; in SQL, comparing with NULL evaluates to UNKNOWN. If you need to match null values, use `IS NULL` or write a dedicated predicate.

Optional filter query example:

```java
@Query("""
    select c from Customer c
    where (:status is null or c.status = :status)
    """)
List<Customer> searchByOptionalStatus(
    @Param("status") CustomerStatus status
);
```

This is a simple approach for a small number of filters, but many `:param is null or ...` expressions can make the query harder to optimize, and certain type/null combinations can cause type inference issues depending on the provider/database. With many optional filters, consider Specification or Querydsl so only the needed predicates are added.

Java parameter types should be compatible with the Entity properties: enums for enums, `Instant`/`LocalDate` for the corresponding temporal properties, numbers for numbers. Avoid converting values to strings just for binding convenience; doing so can forfeit type safety or hurt index usage.

## 9. Pageable, Sort, and special parameters

`Pageable`, `Sort`, and `Limit` (if supported by your Spring Data version) are special parameters handled separately by Spring Data. They are not regular placeholders like `:email` or `?1` in the query.

```java
@Query("select c from Customer c where c.status = :status")
Page<Customer> findPageByStatus(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
```

Do not write `:pageable` or `?2` to bind the Pageable object itself into JPQL. Spring Data uses it to apply pagination/sorting to the query. When using native queries or queries with a fixed `ORDER BY`, verify how your Spring Data version handles dynamic sorting and count queries.

Never allow untrusted input to become a column name, table name, operator, or `ORDER BY` fragment via parameter binding. Parameter binding only substitutes **values**, not SQL structure. For dynamic sorting, use `Sort`/`Pageable` and allow-list valid properties.

## 10. Native SQL and portability

JPQL supports named parameters `:name` and positional parameters `?1`. With native SQL, placeholder syntax and named parameter support depend on the JPA contract, Spring Data, and the specific provider.

Common positional native query example in Spring Data JPA:

```java
@Query(
    value = "select * from customer where email = ?1",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(String email);
```

Native queries must use physical table and column names. Under JPA portability rules, positional parameters are the safe choice for native SQL; named parameters in native queries may be supported by providers like Hibernate, but you should not assume every provider supports them identically. If you use named native parameters, check the documentation and run integration tests against the actual provider/database.

## 11. Parameters cannot replace identifiers or query syntax

You cannot bind a column name or table name as a value:

```java
// Cannot use :columnName to replace a column name in JPQL.
@Query("select c from Customer c order by :columnName")
```

`:columnName` in that position is a parameter value, not an identifier. Similarly, you cannot bind keywords like `ASC`, function names, or SQL condition fragments.

If you need to sort by user-selected columns, map the selection against an allow-list of permitted properties and construct a `Sort`/`Pageable`. Never interpolate raw request strings directly into JPQL or native SQL.

## 12. Common binding errors

**Named parameter not bound.** Verify that every `:name` placeholder has a matching method parameter and that `@Param("name")` matches in spelling and case.

**Parameter name not found.** Add an explicit `@Param` or confirm the build preserves parameter metadata via `-parameters`.

**Positional parameter index out of range.** Indexing in JPQL starts at 1; ensure `?1`, `?2` match the method arguments.

**Wrong type bound.** Check that the Java type is compatible with the Entity property and database column type; avoid passing strings for enums/numbers/temporals unnecessarily.

**IN with an empty collection fails or produces unexpected results.** Handle empty collections before calling the repository according to business rules.

**Querying with null does not match null rows.** Use `IS NULL` or a dedicated predicate; `= :param` with null does not mean `IS NULL`.

**LIKE returns broader results than expected.** Check `%` and `_` wildcards, escape semantics, and case normalization.

**Native query works on Hibernate but fails when switching providers.** Check placeholder syntax and provider named-parameter support; prefer portable positional binding when compatibility matters.

**Trying to bind a column name or ORDER BY.** Parameters are strictly for values; use an allow-list and appropriate query construction for identifiers/sorting.

## 13. Checklist for using @Param

- For JPQL, choose either positional `?1` or named `:name`; do not mix both styles in the same query.
- Use explicit `@Param("name")` for named parameters to avoid relying on compiler metadata.
- Ensure `@Param` names match placeholders exactly.
- Verify argument order when using positional binding; JPQL indices start at 1.
- Define semantics for null, empty collections, and LIKE wildcards.
- Use Java types compatible with Entity properties.
- Treat `Pageable`/`Sort` as special parameters; do not bind them as query values.
- Never interpolate user input into column names, table names, or SQL syntax.
- For native queries, verify syntax and provider/database support.

Named parameters with `@Param` are generally easier to read and less coupled to method argument order than positional binding. Positional binding remains useful for short queries. Whichever approach you choose, bind properly typed values, explicitly define null/empty behavior, and never use parameters to replace query structure.
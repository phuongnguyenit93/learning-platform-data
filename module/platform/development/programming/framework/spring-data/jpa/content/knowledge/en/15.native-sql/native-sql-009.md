# Safe Parameter Binding and Avoiding SQL Concatenation From Input

## Objectives

Spring Data JPA lets you pass values into JPQL and native SQL through bind parameters. This enables the database to separate query structure from user data, avoid syntax errors caused by special characters, and prevent SQL injection through bound values.

Risk arises when an application concatenates input directly into JPQL/SQL strings or injects input into structural elements such as column names, sort directions, and query expressions. Those structural parts cannot be protected by bind parameters alone; the application must select them from an allowlist or use a type-safe query builder API.

After this lesson, you will be able to:

- Understand how SQL injection arises from string concatenation.
- Bind parameters safely in `@Query`, JPQL, native SQL, and `EntityManager`.
- Handle `LIKE`, `IN`, null values, and collection inputs properly.
- Build dynamic filters and sorting using allowlists.
- Identify query parts that cannot be bound as values.
- Write tests verifying that input is treated strictly as data.
- Avoid leaking sensitive data via logs and error messages.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. Why Must Input Never Be Concatenated Into Queries?

Suppose an application looks up an employee by user-entered email. The following string concatenation is unsafe:

```java
String email = request.email();

String jpql =
        "select e from Employee e where e.email = '" + email + "'";

List<Employee> result = entityManager
        .createQuery(jpql, Employee.class)
        .getResultList();
```

The application has mixed JPQL structure with external data. If the input contains quotes or syntactically meaningful text, it can alter the executed query. The consequences can include unauthorized data access, bypassed filter conditions, or broken queries.

A similar bug happens with native SQL:

```java
String sql =
        "select * from employees where email = '" + email + "'";

List<?> rows = entityManager
        .createNativeQuery(sql)
        .getResultList();
```

Do not try to manually escape quotes via character replacement and keep concatenating strings. Manual escaping is highly error-prone across different encodings, data types, databases, and syntax layers. Always use bind parameters.

### 1.1. Bind Parameters Separate Data From Query Structure

A safe query keeps its structure fixed and places a placeholder where the value belongs:

```java
TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.email = :email",
        Employee.class
);

query.setParameter("email", email);

List<Employee> result = query.getResultList();
```

The database/provider receives the query and the parameter value separately. The input content is treated strictly as an email value and is never re-parsed as JPQL/SQL syntax.

This rule applies to both JPQL and native SQL: never concatenate input into query strings; bind values with their proper data types.

## 2. Named Parameters in @Query

With Spring Data JPA, the most readable style is usually named parameters, prefixing the parameter name with a colon and linking it via `@Param`.

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.email = :email
           """)
    Optional<Employee> findByEmail(
            @Param("email") String email
    );
}
```

Spring Data binds the Java parameter's value to the `:email` placeholder. Even if the input contains single quotes, semicolons, or SQL-like syntax, it is passed strictly as the data value of an email.

A query with multiple parameters:

```java
@Query("""
       select e
       from Employee e
       where e.active = :active
         and e.department.id = :departmentId
       """)
List<Employee> findByDepartmentAndStatus(
        @Param("departmentId") Long departmentId,
        @Param("active") boolean active
);
```

The name inside `@Param` must match the placeholder in the query exactly. Using named parameters reduces mistakes when methods have multiple parameters or parameter order changes.

## 3. Positional Parameters

JPQL and Spring Data JPA also support positional parameters:

```java
@Query("""
       select e
       from Employee e
       where e.email = ?1
         and e.active = ?2
       """)
List<Employee> findByEmailAndActive(
        String email,
        boolean active
);
```

Indices start at 1. The first parameter is `?1`, and the second is `?2`.

Positional parameters are still safe when properly bound. However, for queries with many parameters, named parameters are usually easier to read and maintain.

Do not mix named parameters and positional parameters in the same query. Pick one style and stay consistent.

## 4. Binding Parameters in Native SQL

When database-specific SQL is needed, you can use `nativeQuery = true`. Values must still be bound:

```java
@Query(
    value = """
            select *
            from employees
            where email = :email
            """,
    nativeQuery = true
)
Optional<Employee> findByEmailNative(
        @Param("email") String email
);
```

The query uses database table and column names, yet `:email` remains a bind parameter. Never replace it with string concatenation.

With `EntityManager`:

```java
Query query = entityManager.createNativeQuery(
        "select * from employees where email = :email",
        Employee.class
);

query.setParameter("email", email);

List<Employee> employees = query.getResultList();
```

Placeholder names and native query syntax must be tested with your application's JPA provider and database. Parameter binding protects values; it does not make native SQL automatically database-independent.

## 5. Components That Cannot Be Bound as Values

Bind parameters are for data values such as emails, IDs, dates, amounts, or statuses. They cannot substitute table names, column names, SQL keywords, operators, or sort directions.

The following example does not work as intended:

```java
String column = request.sortBy();

@Query("select e from Employee e order by :column")
List<Employee> findSorted(@Param("column") String column);
```

The `:column` placeholder is interpreted as a constant value, not a property name for the database to sort by. The query ends up sorting by the same literal value for every row and fails to select the column as the application intended.

Similarly, you cannot bind a table name:

```sql
select * from :tableName
```

If query structure must vary by input, use an allowlist or Criteria API/Specification/Querydsl to construct controlled expressions.

### 5.1. Dynamic Sorting Using an Allowlist

Suppose the UI allows sorting by name, email, or creation date. Never use a client-supplied string directly as a property or SQL expression.

```java
public enum EmployeeSortField {
    NAME,
    EMAIL,
    CREATED_AT
}
```

Translate the validated choice to a fixed property in code:

```java
private Sort toSort(EmployeeSortField field, Sort.Direction direction) {
    String property = switch (field) {
        case NAME -> "fullName";
        case EMAIL -> "email";
        case CREATED_AT -> "createdAt";
    };

    return Sort.by(direction, property);
}
```

The controller/service must parse input into a valid enum; if invalid, return a validation error or fall back to a defined default. Direction should also be constrained to `ASC` or `DESC` via the `Sort.Direction` enum.

Never pass an arbitrary SQL expression from a request into `JpaSort.unsafe`. `JpaSort.unsafe` injects raw expressions into `ORDER BY` and is only suitable for fixed, trusted expressions controlled by developers.

### 5.2. Dynamic Filtering With the Criteria API

When filter criteria vary dynamically with input, do not concatenate JPQL fragments as strings. Use Spring Data `Specification`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

```java
public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> hasEmail(String email) {
        return (root, query, builder) ->
                email == null
                        ? builder.conjunction()
                        : builder.equal(root.get("email"), email);
    }

    public static Specification<Employee> isActive(Boolean active) {
        return (root, query, builder) ->
                active == null
                        ? builder.conjunction()
                        : builder.equal(root.get("active"), active);
    }
}
```

Combining criteria:

```java
Specification<Employee> specification =
        Specification.where(EmployeeSpecifications.hasEmail(email))
                .and(EmployeeSpecifications.isActive(active));

List<Employee> employees =
        employeeRepository.findAll(specification);
```

The Criteria API constructs predicates from entity metadata and binds values through the provider's mechanism. Property paths in code must still be valid entity properties; external input must never construct arbitrary path names. With many field choices, map an enum/allowlist to fixed properties.

## 6. LIKE: Distinguishing Wildcards From SQL Injection

Using bind parameters does not strip `%` and `_` of their special meaning inside a `LIKE` operator. These are `LIKE` wildcards, not SQL injection syntax:

- `%`: matches zero or more characters.
- `_`: matches exactly one character.

Example searching for names containing a keyword:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
List<Employee> searchByName(
        @Param("keyword") String keyword
);
```

This query is safe against input turning into SQL syntax because the value is bound. However, if a user enters `%`, the query may match nearly every name. That is a difference in search semantics, not SQL injection.

### 6.1. Searching Literal Strings and Escaping Wildcards

If the requirement is to search for literal percent signs or underscores as plain text, escape the wildcards. For example, pick `!` as the escape character:

```java
private String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

Escape the escape character first, then escape the two wildcards. JPQL query:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(:pattern) escape '!'
       """)
List<Employee> searchNameLiteral(
        @Param("pattern") String pattern
);
```

Calling the repository:

```java
String pattern = "%" + escapeLike(keyword) + "%";
List<Employee> result = repository.searchNameLiteral(pattern);
```

Parameter binding protects query structure; `LIKE` escaping ensures wildcard characters are treated as literal text per search requirements. The two solve different problems.

Escape syntax and collation rules can vary by database and provider. Write integration tests against the target database, especially when supporting Unicode or accent/case-insensitive search.

## 7. Passing Collections Into IN

You can bind a collection to an `IN` condition:

```java
@Query("""
       select e
       from Employee e
       where e.id in :ids
       """)
List<Employee> findAllByIds(@Param("ids") Collection<Long> ids);
```

Spring Data/the JPA provider expands the collection into bound values. Never manually join a list of IDs into an SQL string:

```java
// Unsafe and error-prone:
String sql = "select * from employees where id in (" +
        ids.stream().map(String::valueOf)
                .collect(Collectors.joining(",")) + ")";
```

Handle empty collections at the service layer:

```java
public List<Employee> findEmployees(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return repository.findAllByIds(ids);
}
```

Empty handling should match business rules. For a "fetch selected IDs" query, returning an empty list makes sense. For other rules, a validation error may be appropriate. Do not assume every provider and database handles an empty `IN ()` identically.

For very large lists, watch out for database and driver bind-parameter limits. You can batch requests, use temporary tables, table-valued parameters, or another suitable database mechanism.

## 8. Nulls and Optional Parameters

In SQL/JPQL, comparing with `null` does not work like comparing regular values. The expression:

```sql
e.departmentId = :departmentId
```

when `:departmentId` is `null` does not automatically turn into `IS NULL`. The predicate typically evaluates to `UNKNOWN` and matches no rows.

If `null` means "skip this filter", write it explicitly:

```java
@Query("""
       select e
       from Employee e
       where (:active is null or e.active = :active)
       """)
List<Employee> findByOptionalActive(
        @Param("active") Boolean active
);
```

If `null` means "find rows where the column is null", write an explicit condition:

```java
@Query("""
       select e
       from Employee e
       where (:departmentId is null and e.department is null)
          or e.department.id = :departmentId
       """)
List<Employee> findByDepartmentOrWithoutDepartment(
        @Param("departmentId") Long departmentId
);
```

Clarify the semantics of `null` before writing the query:

- Does `null` mean do not apply the filter?
- Does `null` mean match rows where the column is `NULL`?
- Is `null` invalid and meant to be rejected?

With many optional filters, `Specification`/Criteria API is usually far easier to read than a long query filled with `(:x is null or ...)` clauses.

## 9. UPDATE/DELETE Statements Must Also Bind Parameters

`@Modifying` does not remove the requirement to bind parameters. Example updating status by ID:

```java
@Modifying
@Query("""
       update Employee e
       set e.active = :active
       where e.id = :id
       """)
int updateActive(
        @Param("id") Long id,
        @Param("active") boolean active
);
```

Service calling within a transaction:

```java
@Transactional
public void deactivate(Long id) {
    int updated = repository.updateActive(id, false);

    if (updated == 0) {
        throw new IllegalArgumentException("Employee not found");
    }
}
```

Never concatenate IDs or status values into JPQL strings. Beyond preventing injection, parameter binding helps the provider handle data types properly and reduces formatting bugs for dates, numbers, or special characters.

Bulk `UPDATE`/`DELETE` operations can leave already-managed entities in the persistence context holding stale data. When needed, use `flushAutomatically` and `clearAutomatically` deliberately; this is a persistence context synchronization concern, separate from parameter binding.

## 10. SpEL in @Query: Use With Restraint

Spring Data JPA supports certain SpEL expressions inside queries. For example, `#{#entityName}` helps reuse the entity name:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends Repository<T, ID> {

    @Query("""
           select e
           from #{#entityName} e
           where e.id = :id
           """)
    Optional<T> findOneById(@Param("id") ID id);
}
```

`#entityName` resolves entity metadata managed by Spring Data; it is not an arbitrary input string from a request.

Some query expressions can reference method parameters. Even so, never turn user input into a query expression, property name, `ORDER BY`, or SQL fragment. Keep query templates fixed in source code and pass values via bind parameters.

If dynamic query structure is required, use an allowlist or Criteria/Specification/Querydsl. Never evaluate or execute client-supplied query expressions.

## 11. Limits of Bind Parameters and Allowlists

A bind parameter only replaces a value in a valid value slot of a query. It cannot replace:

- Table names or schema names.
- Column names or property names.
- `SELECT`, `WHERE`, `GROUP BY`, or `ORDER BY` keywords.
- SQL operators or expressions.
- `ASC`/`DESC` sort directions.
- Arbitrary `JOIN` clauses or filter fragments.

If business logic requires selecting tables or columns, map the choice to one of the fixed values defined by the application. Never let clients submit raw SQL names freely.

Allowlist example for reporting:

```java
public enum ReportColumn {
    EMAIL,
    FULL_NAME,
    CREATED_AT
}

private String columnFor(ReportColumn column) {
    return switch (column) {
        case EMAIL -> "email";
        case FULL_NAME -> "full_name";
        case CREATED_AT -> "created_at";
    };
}
```

If you must construct dynamic native SQL, only assemble identifiers mapped from a fixed enum/allowlist; keep all data values passed via bind parameters. Carefully enforce access checks so users cannot pick sensitive columns outside their permissions.

## 12. Logging and Error Handling

Bind parameters protect queries at execution time, but logs can still expose sensitive data if all parameter values are logged indiscriminately.

Good practices:

- Do not log passwords, tokens, full card numbers, or unnecessary personal data.
- When tracing is needed, log the query name, request ID, and sanitized metadata.
- Never return raw SQL statements, stack traces, or internal schema details to clients.
- Do not write unsanitized input into logs in ways that enable log injection or corrupt log structure.
- Restrict log access and retention per system policy.

When a query fails, record the error category and needed context on the server. Return an appropriate business message to the client, such as "invalid filter", rather than raw exception or database messages.

## 13. Testing Parameter Safety

Tests should verify that special inputs are treated as data and do not alter query structure.

Example with a repository looking up by email:

```java
@DataJpaTest
class EmployeeRepositorySecurityTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void treatsSpecialCharactersAsParameterValue() {
        repository.save(new Employee(
                "An",
                "an@example.com",
                true
        ));

        String input = "' OR '1'='1";

        Optional<Employee> result = repository.findByEmail(input);

        assertThat(result).isEmpty();
    }
}
```

This test assumes the repository uses a `@Query` named parameter as shown earlier. The input is passed strictly as an email value; it cannot turn into a JPQL `OR` condition.

Additional tests to include:

- Single quotes, double quotes, backslashes, and Unicode characters.
- Strings containing `%` and `_` for literal `LIKE` searches.
- Empty collections and large collections for `IN`.
- `null` parameters matching business semantics.
- Rejecting sort fields not in the allowlist.
- Native queries running against a real database.
- Updates/deletes using parameter binding and proper transactions.

Embedded databases can differ from PostgreSQL/MySQL in native SQL syntax, collation, bind-parameter limits, and data types. For critical queries, run integration tests on the same database engine as production, such as with Testcontainers.

## 14. Complete Service Example With Safe Filtering and Sorting

```java
@Service
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Employee> search(
            String email,
            Boolean active,
            EmployeeSortField sortField,
            Sort.Direction direction,
            int page,
            int size
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("Page must be >= 0");
        }

        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("Page size must be 1..100");
        }

        String property = switch (sortField) {
            case NAME -> "fullName";
            case EMAIL -> "email";
            case CREATED_AT -> "createdAt";
        };

        Sort sort = Sort.by(direction, property);
        Pageable pageable = PageRequest.of(page, size, sort);

        Specification<Employee> spec =
                Specification.where(EmployeeSpecifications.hasEmail(email))
                        .and(EmployeeSpecifications.isActive(active));

        return repository.findAll(spec, pageable);
    }
}
```

This example demonstrates three boundaries:

- Filter values `email`/`active` become predicates bound by the Criteria API.
- The sort field is mapped from an enum to a fixed property.
- `page` and `size` are bounds-checked before constructing `Pageable`.

In a real application, handle `null` for `sortField` and `direction` via validation or defaults. Never accept arbitrary property names and pass them straight into `Sort`.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Query behavior changes when input contains quotes | Input concatenated directly into JPQL/SQL | Use named or positional bind parameters |
| `ORDER BY` does not sort by the client-chosen column | Placeholder used for column name | Map fields through an allowlist |
| `LIKE` returns too many results | Input contains `%` or `_` wildcards | Escape wildcards when literal matching is needed |
| `IN` fails on an empty list | Providers/databases handle empty `IN` differently | Handle empty collections in the service layer |
| `= null` returns no results | SQL/JPQL uses three-valued logic | Use `IS NULL` or explicit optional conditions |
| Native query fails to bind parameter | Incompatible placeholder or provider syntax | Verify named/positional syntax for your provider |
| Dynamic SQL is vulnerable to injection | Identifiers or fragments concatenated from input | Allowlist identifiers and bind all values |
| Sensitive data appears in logs | All bind parameters logged | Mask/redact and restrict logging |
| Sort/filter triggers overly heavy queries | Unbounded fields, page sizes, or filters | Allowlist, validate, and cap resources |

## 16. Checklist Before Deploying Queries to Production

- [ ] No user input concatenated into JPQL, SQL, or query fragments.
- [ ] Named parameters with `@Param` or positional parameters used consistently.
- [ ] Parameters bound with appropriate types for IDs, dates, numbers, and statuses.
- [ ] `LIKE` wildcards escaped separately when literal matching is required.
- [ ] Empty collections handled before `IN` clauses.
- [ ] `null` parameter semantics explicitly defined.
- [ ] Bind parameters not misused for table/column names or `ORDER BY`.
- [ ] Dynamic sorting/filtering mapped via enums or allowlists.
- [ ] Page size and `IN` collection size capped.
- [ ] Secrets and sensitive data excluded from logs.
- [ ] Special inputs and native queries tested against the target database.

## Conclusion

Bind parameters are the standard way to pass values into JPQL and native SQL. They keep input strictly as data, prevent SQL injection from string concatenation, and ensure proper value typing. However, bind parameters cannot substitute table names, column names, keywords, or dynamic expressions.

Keep query templates fixed, bind all values, use allowlists for dynamic query structure, and test edge cases. Combining these rules with validation, resource limits, and safe logging keeps repositories resilient against injection and easier to maintain.
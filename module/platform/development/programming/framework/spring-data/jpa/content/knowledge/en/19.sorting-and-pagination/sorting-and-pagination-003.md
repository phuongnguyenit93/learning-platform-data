# Expression-Based Sorting and the Risks of JpaSort.unsafe

## Objectives

Spring Data JPA lets you sort results using `Sort` and `Pageable`. For ordinary entity properties, you can use `Sort.by("fullName")`. However, some requirements call for sorting by an expression such as converting text to lowercase, computing string length, or another JPQL expression. Spring Data JPA provides `JpaSort.unsafe` to pass such sort expressions.

`JpaSort.unsafe` bypasses the usual validation of property names. Because the expression is placed into the ORDER BY clause of the query, you must not take arbitrary expressions from a request or concatenate user input directly into it. The safe approach is to keep expressions in source code and select them via an allowlist.

After this lesson, you will be able to:

- Distinguish property-based sorting from expression-based sorting.
- Understand how Spring Data JPA applies Sort to JPQL queries.
- Use `JpaSort.unsafe` for fixed, application-controlled expressions.
- Recognize injection risks when building dynamic sorts.
- Build an allowlist for fields and directions.
- Combine expression sorting with Pageable and stable pagination.
- Understand limitations with native queries, databases, and indexes.
- Test queries, result ordering, and invalid input cases.

The examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. How Does Regular Sort Work?

Spring Data JPA allows passing `Sort` to repository methods:

```java
Sort sort = Sort.by(Sort.Direction.ASC, "fullName");
List<Employee> employees = employeeRepository.findAll(sort);
```

Property names in `Sort` are the entity's Java properties, not SQL column names. If an entity has:

```java
@Column(name = "full_name")
private String fullName;
```

then use `fullName`, not `full_name`.

For queries declared with `@Query`, Spring Data JPA appends the sort criteria to the query. Example:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
List<Employee> findActiveEmployees(Sort sort);
```

Call:

```java
List<Employee> employees = repository.findActiveEmployees(
        Sort.by(Sort.Direction.ASC, "fullName")
);
```

Spring Data checks whether the sort path is valid against the domain model properties or an alias declared by the query. If the property does not exist, the query can be rejected instead of inserting an arbitrary expression into ORDER BY.

### 1.1. Sorting by Multiple Properties

Multiple criteria can be combined:

```java
Sort sort = Sort.by(
        Sort.Order.asc("department.name"),
        Sort.Order.asc("fullName"),
        Sort.Order.desc("id")
);
```

Priority runs from left to right: department.name first, then fullName, then id. Nested paths like `department.name` must correspond to valid associations and properties in the entity.

When paginating, include a final criterion that distinguishes rows, usually the primary key. This keeps ordering more stable when multiple records share the same name or timestamp.

### 1.2. Sorting by Query Aliases

With a JPQL projection, a selected alias can be used in Sort if Spring Data recognizes that alias:

```java
@Query("""
       select e.id as employeeId,
              lower(e.fullName) as normalizedName
       from Employee e
       where e.active = true
       """)
List<Object[]> findActiveNames(Sort sort);
```

For example, the query has the alias `normalizedName`. Alias support depends on the query type, parser, and how results are declared. With DTO constructor expressions, not every alias can be used like an entity property. Verify the generated query and actual return type.

## 2. Why Sort by an Expression?

Property-based sorting works when the criterion maps directly to an entity attribute. However, business rules sometimes require sorting by a transformation:

- Case-insensitive sorting: `LOWER(e.fullName)`.
- By name length: `LENGTH(e.fullName)`.
- By a CASE expression to prioritize statuses.
- By a calculation across multiple properties.
- By a database or JPQL function used in the query.

For example, if you use:

```java
Sort.by(Sort.Direction.ASC, "LOWER(fullName)")
```

Spring Data normally treats the entire string as a property path and rejects it because `LOWER(fullName)` is not an entity attribute. This check protects queries from arbitrary expression injection.

When an expression is written statically by the developer and verified, `JpaSort.unsafe` can be used to tell Spring Data that this expression is intentionally allowed.

## 3. What Is JpaSort.unsafe?

`JpaSort.unsafe` is a Spring Data JPA API for creating a Sort containing an ORDER BY expression that is not checked as an ordinary property path.

Example:

```java
JpaSort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
);
```

Used in a repository with JPQL alias `e`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees(Sort sort);
}
```

Call:

```java
List<Employee> employees = repository.findActiveEmployees(
        JpaSort.unsafe(
                Sort.Direction.ASC,
                "LOWER(e.fullName)"
        )
);
```

Spring Data appends the expression to the JPQL ORDER BY clause. The provider translates the query into SQL suitable for the database.

### 3.1. Common Overloads

You can create an unsafe sort with one or more expressions:

```java
JpaSort.unsafe("LENGTH(e.fullName)");

JpaSort.unsafe(
        Sort.Direction.DESC,
        "LENGTH(e.fullName)"
);

JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)",
        "e.id"
);
```

Exact names and overloads should be checked against the project's Spring Data JPA version. `JpaSort.unsafe` returns a Sort object that can be passed to repository methods accepting `Sort` or combined with Pageable.

Do not pass a string that already contains the `ORDER BY` keyword into the expression parameter. Pass valid expressions in query syntax and let Spring Data construct the sort clause.

### 3.2. Unsafe Does Not Mean Bypassing All Query Rules

`JpaSort.unsafe` bypasses Spring Data's property path safety check on expressions. It does not make an arbitrary expression valid syntax in every context.

The expression must still match the query being executed:

- A JPQL expression must be valid for JPQL/the provider.
- The alias must exist in the query.
- The property must exist on the referenced entity or subtype.
- Functions must be supported by the JPA provider/database.
- Native queries require SQL syntax compatible with the database.

For example, `LOWER(e.fullName)` works in JPQL when alias `e` and property `fullName` exist. A PostgreSQL-specific function will not necessarily run on MySQL or on another JPQL provider.

## 4. Risks of Using JpaSort.unsafe with External Input

The danger does not lie in using a fixed expression. The risk arises when taking expressions from users or concatenating request strings into the query.

Unsafe example:

```java
String requestedSort = request.getSortExpression();

Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        requestedSort
);

return repository.findActiveEmployees(sort);
```

A client could send an unintended expression. Because unsafe sort skips regular property path validation, that expression can cause query errors, access data in unintended ways, or inject unwanted syntax into ORDER BY depending on the query/provider.

Another dangerous example is concatenating direction manually:

```java
String direction = request.getDirection();
String expression = request.getSortExpression();

String jpql = "select e from Employee e order by "
        + expression + " " + direction;
```

Both expression and direction are structural parts of the query. They cannot be protected by parameter binding like ordinary values.

### 4.1. Bound Parameters Cannot Replace Column Names or Expressions

Bound parameters are for values:

```java
@Query("""
       select e
       from Employee e
       where e.email = :email
       """)
List<Employee> findByEmail(@Param("email") String email);
```

You cannot write:

```java
order by :sortExpression
```

and expect the value of `:sortExpression` to be interpreted as a column name or function. The database treats it as a value, not as ORDER BY structure.

Therefore, dynamic sorting must be controlled via an allowlist, enum, or fixed mapping in code.

### 4.2. Sort.by Is Not a Place for Arbitrary SQL Strings Either

For regular property paths, `Sort.by` is validated by Spring Data against domain properties/query aliases. `Sort.by` is not a way to execute expressions like `LOWER(e.fullName)`; it will typically be treated as a property name and rejected.

Do not switch to `JpaSort.unsafe` just to make a client-supplied string “work”. If an expression is needed, the developer must predefine the permitted expressions.

## 5. Allowlist for Dynamic Sorting

The safe approach is to let the client pick a clearly named business option, and have the server map that option to a fixed property or expression.

### 5.1. Declaring an Enum for Allowed Fields

```java
public enum EmployeeSortField {
    NAME,
    EMAIL,
    CREATED_AT
}
```

The controller/service parses input into the enum. If the value is invalid, return a validation error or use a documented default. Never keep a free-form string from the request as an expression.

### 5.2. Mapping the Enum to Sort

Suppose the repository query uses alias `e`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    Page<Employee> findActiveEmployees(Pageable pageable);
}
```

The service builds the sort:

```java
@Service
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Page<Employee> search(
            EmployeeSortField field,
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

        Sort sort = switch (field) {
            case NAME -> JpaSort.unsafe(
                    direction,
                    "LOWER(e.fullName)"
            );
            case EMAIL -> JpaSort.unsafe(
                    direction,
                    "LOWER(e.email)"
            );
            case CREATED_AT -> Sort.by(
                    direction,
                    "createdAt"
            );
        };

        // Add ID as the final criterion to stabilize ordering during pagination.
        sort = sort.and(Sort.by(direction, "id"));

        Pageable pageable = PageRequest.of(page, size, sort);
        return repository.findActiveEmployees(pageable);
    }
}
```

In the example:

- `NAME` maps to the fixed expression `LOWER(e.fullName)`.
- `EMAIL` maps to the fixed expression `LOWER(e.email)`.
- `CREATED_AT` uses the normal property path `createdAt`.
- `direction` is the `Sort.Direction` enum, having only ASC or DESC.
- `id` is the tie-breaker so rows with the same primary sort value still have a deterministic order.

The client cannot submit a new JPQL expression. It can only select one of the enum values permitted by the server.

In real code, also handle null `field` or `direction`. You can apply explicit defaults or return a validation error before calling the repository.

### 5.3. When Only Ordinary Properties Are Needed

You do not need unsafe for every field. For mapped property paths, prefer:

```java
Sort sort = Sort.by(direction, "createdAt")
        .and(Sort.by(direction, "id"));
```

Only use `JpaSort.unsafe` for expressions that truly need it, such as functions or calculations. Keeping most sort options as regular properties makes the code easier to verify.

## 6. Common Expressions

### 6.1. Case-Insensitive Sorting

```java
JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
);
```

The query sorts by the result of `LOWER`. Original values in the entity are unchanged; this is only an ORDER BY expression.

If the database has a case-insensitive collation, consider using an appropriate collation or column configuration instead of applying a function to every row. Calling a function on a column can make it harder for the database to use a standard B-tree index unless a functional index or suitable index exists.

### 6.2. Sorting by String Length

```java
JpaSort.unsafe(
        Sort.Direction.DESC,
        "LENGTH(e.fullName)"
);
```

The `LENGTH` expression is a standard JPQL function. Verify that the provider and database handle Unicode characters/string length with the desired semantics. In some databases, character length and byte length are two different concepts.

### 6.3. Sorting by CASE Condition

You can prioritize a group of statuses:

```java
JpaSort.unsafe(
        Sort.Direction.ASC,
        "CASE WHEN e.active = true THEN 0 ELSE 1 END"
);
```

The CASE expression must be valid for JPQL/the provider and must remain fixed in code. If the business only needs a simple status order, consider storing the order in a domain property or sorting by a property to reduce reliance on expressions.

### 6.4. Combining Expressions and Properties

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(
        Sort.by(Sort.Direction.ASC, "id")
);
```

Results are sorted by the normalized name first, then by ID. This provides deterministic ordering for pagination when multiple people share the same name.

## 7. Pageable and Stable Pagination

Unsafe Sort can be passed through Pageable:

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(Sort.by("id"));

Pageable pageable = PageRequest.of(0, 20, sort);

Page<Employee> result =
        employeeRepository.findActiveEmployees(pageable);
```

`Pageable` carries the page number, page size, and Sort. Spring Data applies them when executing the repository method.

### 7.1. Why Is a Tie-Breaker Needed?

Suppose 100 employees have the same fullName after lowercasing. If you sort only by `LOWER(e.fullName)`, the database has no obligation to return tied rows in a fixed order.

When reading page 0 and then page 1, rows with the same sort value can change positions between executions, especially when data is inserted or updated concurrently. Duplicate or skipped records can appear across pages.

Add the primary key as the final criterion:

```java
Sort sort = JpaSort.unsafe(
        Sort.Direction.ASC,
        "LOWER(e.fullName)"
).and(Sort.by(Sort.Direction.ASC, "id"));
```

The tie-breaker makes ordering deterministic within the same data snapshot. It does not eliminate all shifts caused by concurrent writes from other transactions. For continuously changing datasets or deep pagination, consider keyset/scrolling based on the Spring Data version in use.

### 7.2. Dynamic Sort and Count Queries

When a repository returns `Page<T>`, Spring Data may run a content query and a count query. Sort applies to the content query; the count query only needs to count and does not normally need ORDER BY.

If the query has complex JOINs or projections, declare an appropriate `countQuery`. Do not try to force sort expressions into the count query if they do not serve counting.

## 8. Aliases and Expression Scope

Unsafe expressions are usually injected into the query declared by the repository. Therefore, the alias in the expression must match the query's alias.

Example:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
       """)
Page<Employee> findActive(Pageable pageable);
```

The sort expression uses alias `e`:

```java
JpaSort.unsafe("LOWER(e.fullName)")
```

If the query changes its alias from `e` to `employee`, the expression must change too. An expression using the wrong alias can cause the query to fail at execution time.

Do not reuse an expression tied to a specific alias across multiple repository queries with different aliases. Keep sort mappings close to the repository method they serve or encapsulate them in clearly named functions.

## 9. Native Queries and Compatibility Limits

In native SQL, ORDER BY uses database column names, SQL aliases, and database functions, not JPQL entity properties.

Native query example:

```java
@Query(
    value = """
            select *
            from employees
            where active = true
            """,
    countQuery = """
            select count(*)
            from employees
            where active = true
            """,
    nativeQuery = true
)
Page<Employee> findActiveNative(Pageable pageable);
```

Spring Data's ability to parse and append Sort to a native query depends on the version, parser, and SQL complexity. Some complex native queries cannot be automatically rewritten safely to append sorting.

Do not assume a JPQL expression like `LOWER(e.fullName)` can be used verbatim in native SQL. A native query may require `LOWER(full_name)` or different syntax depending on the database.

If native sorting is needed:

- Allow only a predefined set of columns/expressions.
- Use exact SQL column/alias names.
- Verify the dynamic sorting capabilities of the deployed Spring Data version.
- For complex queries, write fixed queries/ORDER BY clauses or a custom repository with an allowlist mapping.
- Run integration tests on the target database and driver.

## 10. Performance of Expression Sorting

Sorting by an expression can force the database to compute the expression for many rows before determining order. For example, `ORDER BY LOWER(full_name)` may not leverage a regular index on `full_name`.

Optimization approaches:

- Measure the query using execution plans and production-like data.
- Create a functional index if supported by the database and the expression is frequently used.
- Consider a normalized column updated according to domain rules.
- Limit results and paginate.
- Filter first with conditions that have suitable indexes.
- Avoid multiple complex expressions in the same ORDER BY if unnecessary.

Do not add an index solely because an expression exists. Indexes carry write, storage, and maintenance costs. Base decisions on query plans, query frequency, and data distribution.

## 11. Testing Safe Sorting

Test the actual ordering, not merely that the repository throws no exception.

Repository example:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           """)
    List<Employee> findActiveEmployees(Sort sort);
}
```

Test:

```java
@DataJpaTest
class EmployeeSortTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void sortsNamesWithoutCaseSensitivity() {
        repository.save(new Employee("bravo", "b@example.com", true));
        repository.save(new Employee("Alpha", "a@example.com", true));
        repository.save(new Employee("charlie", "c@example.com", true));

        Sort sort = JpaSort.unsafe(
                Sort.Direction.ASC,
                "LOWER(e.fullName)"
        ).and(Sort.by(Sort.Direction.ASC, "id"));

        List<Employee> result = repository.findActiveEmployees(sort);

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("Alpha", "bravo", "charlie");
    }
}
```

The test assumes Employee has the constructor and getter as in the example, the repository uses JPQL alias `e`, and JUnit 5, AssertJ, and Spring Boot JPA test support dependencies are present. `@DataJpaTest` normally runs inside a transaction and rolls back after the test.

Add tests for:

- Every allowed sort field enum value.
- ASC and DESC.
- Two or more rows with the same primary sort value.
- Page boundaries when sort has a tie-breaker.
- Fields outside the allowlist rejected before calling the repository.
- Alias mismatch or invalid expression causing an error in tests.
- Native query sorting on the target database if the application uses native queries.

Do not test injection by allowing requests to pass malicious expressions directly to the database. Test that inputs outside the enum/allowlist are rejected and that the repository only receives fixed expressions.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Invalid sort property | Using SQL column name instead of Java property | Use entity property, e.g. fullName |
| LOWER(...) rejected with Sort.by | Spring Data treats expression as property path | Only use JpaSort.unsafe for fixed expressions |
| Query error unrecognized alias | Expression references nonexistent alias | Match alias with @Query |
| Request can alter ORDER BY | Passing input directly into JpaSort.unsafe | Use enum/allowlist mapped to expressions |
| Invalid direction | Accepting free-form ASC/DESC strings | Parse into Sort.Direction and validate |
| Pages have duplicate or missing records | Sort lacks tie-breaker or data changes between reads | Add ID at end of sort; consider keyset pagination |
| Native query fails to append sort | Complex SQL or unsupported by parser | Use fixed ORDER BY/custom repository and test on target DB |
| Query slow after adding LOWER | Database struggles to use regular index | Review execution plan, functional index, or normalized column |
| Expression works on one DB but fails on another | Function/syntax depends on provider/database | Prefer standard JPQL or test each database |
| Sort causes error in count query | Pagination or count query configured improperly | Check content query and separate countQuery |

## 13. Checklist for Using JpaSort.unsafe

- [ ] Only use when an expression is needed; do not replace ordinary Sort.by.
- [ ] Expressions are hardcoded in source code.
- [ ] Do not pass raw sort expressions from requests, headers, or query parameters.
- [ ] Use an enum/allowlist to map client choices to approved expressions.
- [ ] Direction is parsed into Sort.Direction.
- [ ] Alias in the expression matches the JPQL query.
- [ ] Functions and syntax are supported by the provider/database.
- [ ] Add a unique tie-breaker when paginating.
- [ ] Verify native queries separately; do not rely on JPQL assumptions.
- [ ] Measure execution plans before concluding whether an expression sort is fast or slow.
- [ ] Test that invalid fields are rejected before calling the repository.

## Conclusion

`Sort.by` fits valid entity property paths or query aliases. When sorting by an expression such as `LOWER(e.fullName)` is required, Spring Data JPA provides `JpaSort.unsafe` to bypass regular property path validation and include the expression in ORDER BY.

Because an unsafe expression is part of the query structure, it must never come from arbitrary input. Keep expressions in code, let clients select via an enum/allowlist, and use validated `Sort.Direction` values. When combining with Pageable, add a unique tie-breaker for stable ordering; for native queries or database-specific functions, test against the actual provider and deployment database.

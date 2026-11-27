# Query Derivation from Method Names

Spring Data Relational R2DBC lets you declare certain repository queries solely through method names. Spring Data parses the method name, recognizes prefixes such as `find` or `count`, the condition section after `By`, and operators such as `And`, `Or`, `Between`, and `In`, and then generates SQL based on entity metadata and the database dialect.

This mechanism is called *query derivation* or *derived query methods*. It lets repositories express common CRUD and lookup queries without writing SQL for every method. However, method names must follow parser rules, and only operators supported by Spring Data Relational can be translated into queries. When logic becomes too complex or relies on database-specific features, use `@Query`, `DatabaseClient`, or `R2dbcEntityTemplate`.

## 1. How Is a Repository Method Parsed?

A derived query method typically follows the structure:

```text
<subject><By><predicate><OrderBy><sort properties>
```

For example:

```java
Flux<Customer> findByStatusAndAgeGreaterThanOrderByNameAsc(
        String status,
        int age
);
```

Spring Data interprets the name in parts:

- `find`: query operation for retrieving data.
- `By`: marks the beginning of the condition section.
- `Status`: entity property `status`.
- `And`: logical condition connector.
- `AgeGreaterThan`: property `age` with a greater-than operator.
- `OrderByNameAsc`: sorts results by property `name` ascending.

Conceptually, the query corresponds to:

```sql
SELECT ...
FROM customer
WHERE status = ? AND age > ?
ORDER BY name ASC
```

The actual SQL, parameter markers, and column names are generated according to the dialect and mapping metadata. Do not treat the illustrative SQL above as the exact string every driver receives.

Spring Data parses methods when creating repository queries. If a property name does not exist or syntax is unsupported, errors typically surface during repository initialization or query preparation rather than waiting for an incoming user request.

## 2. Subject: The Opening Part of the Method Name

The subject is the part preceding `By`. It tells Spring Data what type of operation to perform. Common query prefixes include:

| Subject | Meaning |
| --- | --- |
| `find…By` | Find entities or projections |
| `read…By` | Read data |
| `get…By` | Get data |
| `query…By` | Execute a query |
| `search…By` | Search |
| `stream…By` | Stream query if return type and module support it |
| `count…By` | Count matching rows |
| `exists…By` | Check whether matching rows exist |
| `delete…By` / `remove…By` | Delete matching rows |

Descriptive subject words such as `find`, `read`, or `get` usually do not alter the SQL condition. They help method names read more naturally. For example, `findByEmail` and `readByEmail` both express finding by the `email` property.

Repository example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Void> deleteByStatus(String status);
}
```

The return types here are reactive: multi-entity queries typically use `Flux<T>`, while single-value results like count or exists typically use `Mono<T>`. The specific return type must match the query type and the capabilities of the Spring Data version in use.

## 3. Predicate: Properties and Operators After `By`

The predicate describes the filtering conditions. Property names are written using the entity's Java property names, typically in camelCase. Spring Data uses mapping metadata to translate properties into column names via `@Column` and the naming strategy.

Entity example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    private String status;

    private Integer age;
}
```

The repository method must use `FirstName`, not the column name `first_name`:

```java
Flux<Customer> findByFirstName(String firstName);
```

Spring Data recognizes `FirstName` as the Java property and uses mapping metadata to build the condition on the `first_name` column.

### Commonly Used Operators

| Keyword in method | Condition meaning | Example |
| --- | --- | --- |
| `Is`, `Equals` | Equal | `findByStatus(String status)` |
| `Not` | Not equal | `findByStatusNot(String status)` |
| `GreaterThan` | Greater than | `findByAgeGreaterThan(int age)` |
| `GreaterThanEqual` | Greater than or equal | `findByAgeGreaterThanEqual(int age)` |
| `LessThan` | Less than | `findByAgeLessThan(int age)` |
| `LessThanEqual` | Less than or equal | `findByAgeLessThanEqual(int age)` |
| `Between` | Within range | `findByAgeBetween(int min, int max)` |
| `After` | After a point in time | `findByCreatedAtAfter(Instant time)` |
| `Before` | Before a point in time | `findByCreatedAtBefore(Instant time)` |
| `IsNull`, `Null` | SQL NULL value | `findByDeletedAtIsNull()` |
| `IsNotNull`, `NotNull` | Non-NULL SQL value | `findByDeletedAtIsNotNull()` |
| `Like` | Matches LIKE pattern | `findByNameLike(String pattern)` |
| `NotLike` | Does not match LIKE pattern | `findByNameNotLike(String pattern)` |
| `StartingWith` | Starts with string | `findByNameStartingWith(String prefix)` |
| `EndingWith` | Ends with string | `findByNameEndingWith(String suffix)` |
| `Containing` | Contains substring | `findByNameContaining(String part)` |
| `In` | Within a set of values | `findByStatusIn(Collection<String> statuses)` |
| `NotIn` | Not within a set of values | `findByStatusNotIn(Collection<String> statuses)` |
| `True`, `False` | Boolean value | `findByEnabledTrue()` |
| `IgnoreCase` | Case-insensitive match | `findByEmailIgnoreCase(String email)` |

These keywords are commonly used in relational queries. Support and generated SQL may differ across Spring Data Relational versions and dialects; do not assume keywords specific to other modules—such as full-text, regex, or geospatial operators—work in R2DBC.

### Equals and Is

If no operator is specified, the property condition defaults to equality:

```java
Flux<Customer> findByStatus(String status);
Flux<Customer> findByStatusIs(String status);
Flux<Customer> findByStatusEquals(String status);
```

These styles share the same query semantics in standard cases. Prefer the shortest, most readable form.

### Between Accepts Two Parameters

`Between` requires two boundary values:

```java
Flux<Customer> findByAgeBetween(int minimum, int maximum);
```

Conceptually equivalent to `age BETWEEN ? AND ?`. Boundary values are inclusive according to SQL `BETWEEN` semantics.

### In Accepts a Collection of Values

`In` is used when a property must match one of several values:

```java
Flux<Customer> findByStatusIn(Collection<String> statuses);
```

Call:

```java
repository.findByStatusIn(List.of("ACTIVE", "PENDING"));
```

represents the condition that status belongs to the supplied set of values. Verify empty-collection behavior in your Spring Data version and dialect; if an empty list is valid business input, handle it explicitly before calling the repository.

### LIKE, StartingWith, EndingWith, and Containing

`Like` typically accepts a caller-supplied pattern, which may include SQL wildcard characters `%` and `_`:

```java
Flux<Customer> findByNameLike(String pattern);
```

`StartingWith`, `EndingWith`, and `Containing` express intent more clearly, with the framework building the corresponding pattern automatically:

```java
Flux<Customer> findByNameStartingWith(String prefix);
Flux<Customer> findByNameEndingWith(String suffix);
Flux<Customer> findByNameContaining(String part);
```

These operators suit string properties. Wildcard handling and collation depend on SQL and the dialect. If inputs can include `%` or `_` and business rules require literal matching, check your module and database escaping rules.

### IgnoreCase

`IgnoreCase` is typically used for string properties:

```java
Mono<Customer> findByEmailIgnoreCase(String email);
```

Spring Data generates a case-insensitive comparison expression according to dialect capabilities, typically via case conversion. Results also depend on database collation and Unicode rules. Do not apply this keyword arbitrarily to non-string types.

## 4. Combining Conditions with `And` and `Or`

Multiple conditions can be chained in one method:

```java
Flux<Customer> findByStatusAndAgeGreaterThan(
        String status,
        int age
);

Flux<Customer> findByFirstNameOrLastName(
        String firstName,
        String lastName
);
```

The first example corresponds to `status = ? AND age > ?`; the second corresponds to `first_name = ? OR last_name = ?` according to entity mapping.

One method can combine both:

```java
Flux<Customer> findByStatusAndAgeGreaterThanOrVipTrue(
        String status,
        int age
);
```

When multiple logical operators appear, the parser splits the predicate into `Or` groups, combining `And` parts within each group. Therefore, the expression above is interpreted with the structure:

```text
(status = ? AND age > ?) OR (vip = true)
```

Long method names with multiple `Or` operators easily cause confusion about condition scope. If logic has multiple branches, complex nesting, or explicit parentheses requirements, use `@Query` or build the query via an API that expresses the predicate clearly.

## 5. Property Paths and Nested Properties

Method names reference entity properties, not SQL column names. For objects with nested properties, Spring Data can resolve property paths via mapping metadata if that structure is supported in the relational model.

Example entity with an embedded address object:

```java
public class Address {
    private String city;
    private String postalCode;
}

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private Address address;
}
```

When the property path is valid in the mapping, you can use an underscore to clarify path boundaries:

```java
Flux<Customer> findByAddress_City(String city);
```

The `_` character is a path separator for the parser; it does not denote a column name. Actual column names are still determined by the embedded property's mapping and naming strategy.

### When Property Names Are Ambiguous

Suppose an entity has both an `addressZip` property and an `address` object containing a `zipCode` property. A concatenated method name could cause the parser to choose an unintended traversal path. An underscore clarifies the path:

```java
Flux<Customer> findByAddress_ZipCode(String zipCode);
```

Whenever possible, name properties clearly and avoid overly long method names. The property path must exist in entity mapping; arbitrary column names or unmapped property names cannot be used.

## 6. Sorting with `OrderBy`

You can append `OrderBy` at the end of a method name to specify result ordering:

```java
Flux<Customer> findByStatusOrderByLastNameAscFirstNameAsc(String status);
```

This method filters by status, then sorts by `lastName` ascending and `firstName` ascending.

Common sort directions:

- `Asc`: ascending.
- `Desc`: descending.

For example:

```java
Flux<Customer> findByStatusOrderByCreatedAtDesc(String status);
Flux<Customer> findByStatusOrderByAgeAscNameDesc(String status);
```

In the second method, results are sorted by age ascending, then by name descending when ages are equal.

If ordering needs to change per request, you can pass a `Sort` parameter when supported by the query method and Spring Data version. Conceptual signature:

```java
Flux<Customer> findByStatus(String status, Sort sort);
```

Check your project version's API and ensure properties in `Sort` are valid entity properties. Never concatenate user-supplied sort strings directly into SQL.

## 7. Limiting Results with `First` and `Top`

`First` and `Top` limit the number of rows returned. They can be used without a number to limit to one row, or with a number to specify the maximum count:

```java
Mono<Customer> findFirstByStatusOrderByCreatedAtDesc(String status);

Flux<Customer> findTop10ByStatusOrderByCreatedAtDesc(String status);
```

The first example retrieves the newest customer by status; the second retrieves at most the 10 newest customers. `Top` and `First` are query-level limits, not operators that take the first elements after loading all data into the application.

Combine limits with `OrderBy` whenever you need deterministic selection of which records are returned. Without an ordering clause, the database does not guarantee which row comes first.

### Mono or Flux?

Choose the return type based on the expected number of elements:

```java
Mono<Customer> findByEmail(String email);
Flux<Customer> findByStatus(String status);
```

`Mono<Customer>` expresses a query expected to return zero or at most one entity. If the actual query produces multiple rows, a single-value publisher may raise a cardinality error. If email must be unique, enforce that rule with a unique constraint in the database.

If the goal is simply picking one row among many matching rows, use `First`/`Top` with explicit `OrderBy`. If you need all matching results, use `Flux<Customer>`.

## 8. Distinct and Subject Modifiers

`Distinct` requests deduplication of duplicate rows according to generated query semantics:

```java
Flux<Customer> findDistinctByStatus(String status);
```

It can be combined with limit modifiers:

```java
Flux<Customer> findDistinctTop20ByStatusOrderByNameAsc(String status);
```

`Distinct` applies at the SQL query level, not merely by calling `distinct()` on a `Flux` after loading data. With projections or multi-column entities, SQL `DISTINCT` semantics operate across the selected columns; do not assume it means "unique on one property" in every situation.

## 9. Derived Count, Exists, and Delete

Beyond entity queries, Spring Data supports subjects for other operations.

### Count

```java
Mono<Long> countByStatus(String status);
```

This method returns the number of matching rows. Because the operation is reactive, the result is emitted via `Mono<Long>` when subscribed to.

### Exists

```java
Mono<Boolean> existsByEmail(String email);
```

This method emits `true` if at least one matching row exists and `false` otherwise. It is an existence check; it does not replace a unique constraint or transaction when preventing two requests from creating duplicate data.

### Delete

```java
Mono<Void> deleteByStatus(String status);
```

This method deletes matching rows. If business logic needs the affected row count, you can use a count return type supported by your Spring Data R2DBC version, such as `Mono<Long>` when supported by the query method and driver. For bulk deletes, be extra careful with filter conditions: an overly broad predicate can wipe out large amounts of data.

`delete…By` or `remove…By` methods are derived delete queries. They do not imply Spring Data loads all entities into memory and deletes each object one by one; exact execution depends on the module and generated query type.

## 10. Parameter Types and Binding Order

In derived queries, method parameters are bound to conditions in the order the parser encounters them in the predicate. Parameter counts and types must match the operators.

For example:

```java
Flux<Customer> findByStatusAndAgeBetween(
        String status,
        int minAge,
        int maxAge
);
```

The method requires three parameters: one for `status`, two for `Between`. For `In`, the parameter is typically a collection or array of values:

```java
Flux<Customer> findByIdIn(Collection<Long> ids);
```

Do not pass a single parameter for `Between` or a scalar value when the query expects a set of values for `In`. If the Java type is incompatible with the property type or the driver cannot bind the value, the query can fail at execution time.

For derived queries, Java parameter variable names do not determine binding; parameter declaration order must match the conditions in the method name. `@Param` is primarily useful for named parameters in `@Query`, whereas derived queries are built from the method name structure.

## 11. Naming Rules and Common Parser Errors

Method names are part of the repository contract. A small typo in a property name or keyword can prevent Spring Data from creating the query.

| Error | Incorrect example | How to fix |
| --- | --- | --- |
| Using column name instead of property name | `findByFirst_name(...)` | Use `findByFirstName(...)` and declare `@Column` if needed |
| Misspelled property | `findByFristName(...)` | Verify the exact Java property name |
| Unsupported keyword | `findByNameRegex(...)` in a module without regex support | Use `@Query` or an appropriate API |
| Missing parameter | `findByAgeBetween(int age)` | Provide both bounds |
| Wrong parameter type | `findByAgeGreaterThan(String age)` | Use a type compatible with the property |
| Using `Mono` for multiple results | `Mono<Customer> findByStatus(...)` when status is not unique | Use `Flux<Customer>` or ordered `First`/`Top` |
| Overly long method with many `Or`s | Single method name packing many condition groups | Split methods or write an explicit query |
| Ambiguous path name | `findByAddressZipCode(...)` when multiple properties could match | Use `_` to disambiguate the property path |
| Expecting raw SQL in method name | `findByAgePlusOneGreaterThan(...)` | Create a `@Query` for custom SQL expressions |

Name methods using domain language while keeping the parser structure readable. If a method name grows into an entire sentence, that is usually a sign the query belongs in `@Query` or a query builder.

## 12. When Is Query Derivation No Longer Suitable?

Derived queries suit property-based filters, common comparisons, sorting, and simple result limits. They are not a general-purpose SQL language.

Consider explicit queries when you need:

- Multi-table joins or complex join conditions.
- Aggregations, group by, having, or computed expressions.
- Subqueries, CTEs, window functions, or recursive queries.
- JSON/JSONB operators, arrays, full-text search, or database-specific types.
- Locking clauses, hints, or dialect-dependent syntax.
- Complex projections or precisely controlled column aliases.
- Condition groups with complex parentheses hard to express in a method name.

### Using `@Query`

For concrete SQL, you can declare a query on a repository method:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("SELECT * FROM customer WHERE status = :status ORDER BY created_at DESC")
    Flux<Customer> findRecentByStatus(@Param("status") String status);
}
```

`@Query` lets you write explicit SQL and use named parameters via `@Param`. Table and column names in SQL must match the real schema; unlike derived queries, Spring Data does not automatically resolve every SQL expression from property paths inside a handwritten SQL string.

For custom `UPDATE` or `DELETE` statements using `@Query`, check `@Modifying` and return-type requirements in your Spring Data R2DBC version. Data-modifying operations must be annotated and declared properly so Spring Data treats them as modifying queries.

### Using `DatabaseClient`

When a query has complex bindings, database-specific SQL, or requires low-level result control, `DatabaseClient` lets you construct the statement explicitly:

```java
Flux<CustomerSummary> summaries = databaseClient.sql("""
            SELECT status, COUNT(*) AS total
            FROM customer
            WHERE created_at >= :fromTime
            GROUP BY status
            ORDER BY status
            """)
        .bind("fromTime", fromTime)
        .map((row, metadata) -> new CustomerSummary(
                row.get("status", String.class),
                row.get("total", Long.class)
        ))
        .all();
```

This is an aggregate query that derived method names struggle to express clearly. `DatabaseClient` also allows binding driver-specific types and controlling per-row mapping.

## 13. Combining Query Derivation with Reactive Pipelines

Derived queries return publishers, so they chain directly with Reactor operators:

```java
public Flux<CustomerView> findActiveCustomerViews() {
    return customerRepository.findByStatusOrderByNameAsc("ACTIVE")
            .filter(Customer::isEnabled)
            .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getName()
            ));
}
```

The `status` condition and ordering by `name` execute in the database query. `filter(Customer::isEnabled)` and `map(...)` are reactive processing steps after rows are emitted. If the `enabled` condition can be expressed in the derived query, move it into the method so the database filters early:

```java
Flux<Customer> findByStatusAndEnabledTrueOrderByNameAsc(String status);
```

Pushing appropriate filters and limits down to the database usually reduces the data transferred and processed in the application. Complex calculations or domain logic, however, may still belong in the Java pipeline.

### Do Not Call `subscribe()` in the Repository Consumer

Services should return the fully composed publisher:

```java
public Mono<CustomerView> findCustomerView(Long id) {
    return customerRepository.findById(id)
            .map(customer -> new CustomerView(
                    customer.getId(), customer.getName()
            ));
}
```

The WebFlux controller or appropriate application layer consumes the publisher. Calling `subscribe()` inside a service can break error coordination, cancellation, and transaction context propagation.

## 14. Testing Derived Query Methods

Derived queries should be tested against a compatible database and driver to confirm the parser generates valid conditions, column mappings match, and parameter types bind correctly.

Example with `StepVerifier`:

```java
StepVerifier.create(repository.findByStatusAndAgeGreaterThan("ACTIVE", 18))
        .expectNextMatches(customer ->
                customer.getStatus().equals("ACTIVE") && customer.getAge() > 18
        )
        .verifyComplete();
```

Test groups to include:

- Equality, greater-than/less-than comparisons, and `Between`.
- `And` and `Or` combinations, especially with multiple groups.
- `IsNull` and `IsNotNull`.
- `Like`, `StartingWith`, `EndingWith`, `Containing`, and `IgnoreCase`.
- `In` with lists of one, multiple, and zero elements.
- Nested property paths and `@Column` mappings.
- `OrderBy`, `First`/`Top`, and `Distinct`.
- `CountBy`, `ExistsBy`, and `DeleteBy`.
- `Mono` return types with zero rows, one row, and multiple rows.
- Ensuring query methods with invalid properties or keywords fail when the repository initializes.

Example testing `Mono` when not found:

```java
StepVerifier.create(repository.findByEmail("missing@example.test"))
        .verifyComplete();
```

For methods returning `Mono<T>`, also test scenarios where multiple rows match to verify that database constraints or query limits enforce the expected cardinality.

## 15. Combined Repository Example

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);

    Flux<Customer> findByStatusAndAgeGreaterThanOrderByNameAsc(
            String status,
            int age
    );

    Flux<Customer> findByEmailIgnoreCase(String email);

    Flux<Customer> findByNameContaining(String part);

    Flux<Customer> findByStatusIn(Collection<String> statuses);

    Flux<Customer> findTop10ByStatusOrderByCreatedAtDesc(String status);

    Mono<Customer> findFirstByEmailOrderByCreatedAtDesc(String email);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Void> deleteByStatus(String status);
}
```

These methods illustrate common query patterns: equality filtering, combined conditions, string matching, value sets, sorting, limiting, counting, existence checks, and deletion. Each can execute within a reactive pipeline without writing SQL manually.

## 16. Key Takeaways

- Derived queries are generated by Spring Data from repository method names; `By` starts the predicate.
- Subjects such as `find`, `count`, `exists`, `delete`, or `remove` specify the operation type.
- Predicates reference Java property names; `@Column` mappings and naming strategies translate properties to SQL columns.
- `And`, `Or`, `Between`, `In`, `Like`, `StartingWith`, `EndingWith`, `Containing`, `IsNull`, `GreaterThan`, and similar keywords express common conditions.
- `OrderBy` defines sorting; `First`/`Top` limits result counts; `Distinct` requests distinct results at the SQL query level.
- `Mono<T>` fits at most one result; `Flux<T>` fits multiple results. Use `First`/`Top` when selecting one row among many matching rows.
- `CountBy`, `ExistsBy`, and `DeleteBy` support operations that do not need to return full entities.
- Nested property paths must match metadata; `_` can clarify path boundaries when names are ambiguous.
- Query derivation does not replace general-purpose SQL. Use `@Query`, `DatabaseClient`, or `R2dbcEntityTemplate` for joins, aggregates, subqueries, and database-specific features.
- Derived queries return reactive publishers; chain them into the pipeline and let the framework or caller manage subscriptions.
- Test against a compatible database and driver to verify parser output, mapping, binding, and actual cardinality.

When designing a repository, begin by identifying conditions expressible directly via entity properties. When method names stay short, clear, and aligned with supported keywords, query derivation is a clean choice. Once method names begin obscuring SQL logic or require database-specific capabilities, switching to explicit queries makes behavior easier to read and control.

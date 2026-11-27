# Constraints on Null Values and Sort Properties in Projections

## 1. Why Do Nulls and Sorting Matter for Projections?

Projections restrict the shape of data returned by a repository. When using interface projections or DTOs, you need to clearly identify which fields can be null, which fields are used for sorting, and whether sort values are returned alongside the results.

With regular queries, a projection can omit many Entity properties. However, when using keyset scrolling, Spring Data must read the sort key values from each result to build the next position. Therefore, sort properties must meet stricter requirements: having non-null values and being included in the projection.

Three concepts need to be separated:

- **Projection nullability:** whether getters can return null or use a wrapper such as `Optional` to represent an absent value.
- **Sort property:** the property name used by `Sort` or `ORDER BY` must be resolvable by Spring Data/JPA to a domain property or an alias in the query.
- **Keyset scrolling:** properties used to build the keyset must be non-null and present in the projection result so the framework can read continuation values.

## 2. Null Values in Interface Projections

Suppose the `Customer` Entity has `phone` and `lastContactAt` as optional fields. If database columns contain NULL, standard reference-type accessors can return null:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    String getPhone();
    Instant getLastContactAt();
}
```

The caller must check for null before using them:

```java
CustomerContactView view = repository.findContactById(id)
    .orElseThrow();

if (view.getPhone() != null) {
    sendSms(view.getPhone());
}
```

A safer approach for truly optional properties is using nullable wrappers. Spring Data supports the following wrappers in interface projection getters:

- `java.util.Optional`
- `com.google.common.base.Optional`
- `scala.Option`
- `io.vavr.control.Option`

Example with Java Optional:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    Optional<String> getPhone();
    Optional<Instant> getLastContactAt();
}
```

If the backing property value is non-null, the getter returns a present wrapper. If the backing value is null, the getter returns an empty wrapper, such as `Optional.empty()`.

```java
view.getPhone().ifPresent(this::sendSms);

String phone = view.getPhone().orElse("Not provided");
Instant lastContact = view.getLastContactAt().orElse(null);
```

Do not call `get()` without checking `isPresent()` or providing a suitable fallback. `Optional` helps express nullability explicitly; it does not turn required data into optional business data.

## 3. Nulls in DTO Projections

DTO classes or records receive data through a constructor. If a column can be NULL, use nullable reference types such as `String`, `Long`, `Integer`, `BigDecimal`, or `Instant` instead of primitives like `long`, `int`, or `boolean`.

```java
public record CustomerContactRow(
    Long id,
    String email,
    String phone,
    Instant lastContactAt
) {
}
```

Do not declare `int age` if the query can return NULL for age. Primitives cannot represent null; depending on the mapping path, results may fail during instantiation or fail to preserve exact semantics. Use `Integer age` if the field is optional.

For DTOs, verify the constructor matches the exact count, order, and types of expressions in the query. `Optional` is often useful in interface projections; for DTO records, nullable reference components are usually simpler and more compatible. If you want a DTO contract to be strictly non-null, ensure the query/domain/schema supplies valid values and validate at the appropriate layer.

## 4. Distinguishing Nullability Across Entity, Projection, and Database

Three constraint layers serve distinct roles:

| Layer | Example | Effect |
| --- | --- | --- |
| Java/Entity | `String phone` or `Optional` in projection | Represents values in the application |
| Bean Validation | `@NotNull`, `@NotBlank` | Validates objects at validation time |
| Database | `NOT NULL`, `CHECK` | Protects data at storage level |

`@Column(nullable = false)` describes mapping/schema generation; for schemas managed by Flyway or Liquibase, migrations must actually create the `NOT NULL` constraint. `@NotNull` validates at the application layer when validation is triggered. Neither annotation replaces database constraints.

If a property is used as a keyset sort, it must be non-null across all records that can appear in the scroll query. Merely placing `@NotNull` on a DTO or projection does not fix existing null data in the database. Verify the data, migrations, constraints, and all write paths.

## 5. Sort Properties Must Be Resolvable

Spring Data JPA requires every property in `Sort.Order` to resolve to a property of the domain model or an alias used in the query. You cannot arbitrarily pass column names or arbitrary expressions and expect the framework to infer them.

For example, an Entity has Java property `createdAt` mapped to column `created_at`. Sort must use the Java property name:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);
```

Do not use `Sort.by("created_at")` merely because that is the physical column name. For derived queries, the property path in Sort must belong to the domain model. For `@Query`, the property must be a valid state-field path or an alias declared by the query.

## 6. Sorting with Interface Projections

Suppose a projection only returns ID and email:

```java
public interface CustomerListView {
    Long getId();
    String getEmail();
}
```

The repository can accept Sort:

```java
List<CustomerListView> findByStatus(
    CustomerStatus status,
    Sort sort
);
```

For regular queries, Sort can reference an Entity property such as `createdAt` even when the `getCreatedAt()` getter is absent from the interface projection. The database can still sort by that property without returning its value to the caller in the projection.

This differs from keyset scrolling: keyset must read sort values from each result to construct the predicate for the next window. Thus, if `createdAt` is used as a keyset property, the projection must declare `getCreatedAt()` and the query must return that property. A property used only for sorting while omitted from the projection can cause keyset extraction to fail.

## 7. Aliases in JPQL Projections

When a query selects scalars or expressions, assign aliases matching the interface projection accessors:

```java
public interface CustomerScoreView {
    Long getId();
    String getEmail();
    Integer getScore();
}
```

```java
@Query("""
    select c.id as id,
           c.email as email,
           c.score as score
    from Customer c
    where c.status = :status
    """)
List<CustomerScoreView> findScoreViews(
    @Param("status") CustomerStatus status,
    Sort sort
);
```

`id`, `email`, and `score` are aliases for the tuple/projection. When sorting by a domain property, use a valid Entity property. If sorting by a selected expression is needed, use the alias actually declared by the query, such as `score` in the example above. Aliases must match the exact name returned by the provider; test queries with a real JPA provider/database.

Spring Data JPA validates Orders in Sort to ensure they are referenceable properties or aliases. An invalid path expression can raise an exception when creating or executing the query.

## 8. Sorting by Expressions and JpaSort.unsafe

Spring Data JPA rejects Sort expressions containing function calls by default to prevent unsafe expressions from being interpolated into queries. When genuinely needed, `JpaSort.unsafe` allows adding ORDER BY expressions bypassing standard property path checks:

```java
Sort sort = JpaSort.unsafe(
    Sort.Direction.ASC,
    "LENGTH(firstName)"
);
```

Only use fixed expressions controlled by developers. Never pass column names, functions, or sort strings directly from user requests into `JpaSort.unsafe`; bind parameters only protect values, not ORDER BY structural fragments concatenated into queries.

If an API allows dynamic sorting, build an allow-list of supported options and map them to `Sort.by("createdAt")`, `Sort.by("email")`, or controlled expressions. Never treat a projection getter as an arbitrary SQL identifier.

## 9. Controlling NULL Placement When Sorting

Spring Data provides null-handling hints for `Sort.Order`: `nullsFirst()`, `nullsLast()`, and `nullsNative()`.

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastContactAt").nullsLast(),
    Sort.Order.asc("id")
);
```

Meaning:

| Declaration | Intent |
| --- | --- |
| `nullsFirst()` | Hint that NULL values appear before non-null values |
| `nullsLast()` | Hint that NULL values appear after non-null values |
| `nullsNative()` | Let the datastore/database decide the default order |

These are hints to the datastore and may not be honored by every database/provider. Default NULL ordering differs by database and sort direction. If the ordering must be consistent, inspect the generated SQL and run integration tests on the target database.

With static JPQL queries, null ordering can be expressed explicitly using `CASE`:

```java
@Query("""
    select c
    from Customer c
    order by
      case when c.lastContactAt is null then 1 else 0 end asc,
      c.lastContactAt asc,
      c.id asc
    """)
List<Customer> findAllOrderedWithNullsLast();
```

Here, non-null values have key 0 and sort first; null values have key 1 and sort afterward. `id` serves as a tie-breaker for a stable order. This is a fixed sort in JPQL; do not combine it with a conflicting dynamic Sort without clearly defining the final ordering.

## 10. Keyset Scrolling Requires Non-Null Sort Properties

Keyset scrolling uses the sort values of the last row in a `Window` to generate the WHERE predicate for the next read. Comparison operators and NULL handling vary across databases; therefore, Spring Data requires keyset properties to be non-nullable. Using `nullsFirst()` or `nullsLast()` does not bypass this limitation.

Example Entity with a required `createdAt`:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @Column(nullable = false)
    private Instant createdAt;

    private String email;
    private CustomerStatus status;
}
```

The projection must contain all properties used as sort keys:

```java
public interface CustomerScrollView {
    Long getId();
    Instant getCreatedAt();
    String getEmail();
}
```

Repository using Window and KeysetScrollPosition:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Window<CustomerScrollView> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus status,
        KeysetScrollPosition position
    );
}
```

Both `createdAt` and `id` appear in the projection. `createdAt` must be non-null in every row that can be read. The primary key ensures unique ordering when multiple customers share the same timestamp. Spring Data may append the primary key or missing primary key components to the keyset order; explicitly declaring `id` in the example makes the sort contract clear.

## 11. Iterating Keyset Windows

Example using `WindowIterator` to process each window:

```java
WindowIterator<CustomerScrollView> customers = WindowIterator
    .of(position -> repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE, position
    ))
    .startingAt(ScrollPosition.keyset());

while (customers.hasNext()) {
    CustomerScrollView customer = customers.next();
    process(customer.getId(), customer.getEmail());
}
```

The example requires the corresponding Spring Data imports, including `WindowIterator`, `ScrollPosition`, and `Window`. The scrolling API depends on the Spring Data version in use. A query method returning `Window<T>` and accepting `KeysetScrollPosition` is a common pattern for keyset scrolling.

Do not omit `createdAt` from the projection merely because the application does not display the timestamp. The framework still needs that value to build the next position. If you do not want to expose the sort field to clients, keep it in an internal projection and map it to another response DTO in the service.

## 12. What Options Exist When a Sort Property Can Be Null?

Keyset scrolling is unsuitable for nullable sort keys. Several options exist:

1. **Use offset-based scrolling or pagination** if NULL values must also be sorted. You can use `nullsFirst()`/`nullsLast()` as hints and test actual behavior.
2. **Choose another always non-null sort key**, such as `createdAt` or ID, if it still satisfies business ordering.
3. **Create a normalized, non-null persisted sort property** if business logic requires ordering based on an optional value. For example, persist a `sortTimestamp` computed by a clear rule with a NOT NULL constraint.
4. **Split null and non-null datasets** into separate flows if business requirements need to process both groups in a specific order.

Do not merely use `COALESCE` in ORDER BY and assume keyset scrolling will work: keyset needs mapped properties that can be read back from results to reconstruct predicates. Arbitrary expressions or computed aliases may not satisfy these requirements.

## 13. Stable Sorting and Indexes

Scrolling needs a stable order. If sorting only by a timestamp where multiple records share the same instant, the ordering among those records is underdetermined. Add a unique key as a tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
);
```

The keyset mechanism can automatically append the primary key or missing components of a composite key to produce a unique ordering. Still, explicitly declaring the tie-breaker helps readers understand the intended order and simplifies testing.

Keyset scrolling performs best when the database has an index matching the filter and sort fields. For queries filtering by status and sorting by `createdAt, id`, consider a corresponding composite index based on workload and database. Do not create indexes purely from property names; inspect execution plans and query metrics.

## 14. Streams and Resources

A projection can also be the element type of a repository method returning `Stream<T>`. Streams allow sequential processing instead of materializing all results into a collection, but they are stateful and may hold provider or JDBC cursors/resources.

```java
@Transactional(readOnly = true)
public void exportActiveCustomers() {
    try (Stream<CustomerContactView> stream =
            repository.streamByStatus(CustomerStatus.ACTIVE)) {
        stream.forEach(this::writeCustomerRow);
    }
}
```

Ensure the stream is closed via try-with-resources and consumed within an active transaction. `Stream<T>` does not guarantee that the driver actually fetches data in small chunks; fetch size and provider/driver behavior affect buffering. For very large datasets, measure memory and check JDBC configuration.

Lightweight projections reduce per-row data, but if a stream projection contains associations or getters that trigger lazy loading, N+1 queries can still occur. Select only the needed fields and inspect the SQL.

## 15. Common Pitfalls

**Optional getter still returns null.** Verify the interface projection is actually instantiated by Spring Data, the accessor returns a supported wrapper, and query aliases/properties match.

**Sort reports property not found.** Use the Entity's Java property name or an alias actually declared by the query; do not use physical column names unless they are matching aliases.

**Sorting by a projection getter absent from the Entity.** Getters do not automatically create domain properties. For query projections, declare appropriate aliases; for derived queries, sorting must resolve against the domain model.

**Keyset scrolling fails when a projection omits sort fields.** Add all required sort properties and ID to the interface/DTO projection.

**Keyset misses or drops rows containing NULL.** Keyset sort properties must be non-null. Use offset scrolling or choose a non-null sort key.

**`nullsLast()` behaves inconsistently across databases.** It is only a hint. Check SQL/provider/dialect; use CASE in fixed JPQL when clearer, more portable semantics are required.

**Windows duplicate or skip rows with identical sort values.** Add a unique key as a tie-breaker and verify whether sort values change during scrolling.

**Streams hold connections long or consume excessive memory.** Close streams, bound processing duration, verify transaction/fetch size, and consider Window-based scrolling.

## 16. Checklist for Designing Projections with Sort/Scroll

- Identify which properties are nullable and represent them clearly with appropriate wrappers/reference types.
- Do not use primitives for values that can be null.
- For interface projections, accessors must match Java properties; scalar queries need accurate aliases.
- For Sort, use only domain properties or aliases supported by the query.
- Only use `JpaSort.unsafe` with fixed developer-controlled expressions.
- Treat `nullsFirst`, `nullsLast`, and `nullsNative` as hints and test on the target database.
- For keyset scrolling, all sort properties must be non-null and present in the projection.
- Include the ID or required primary key components to position results; ensure stable ordering.
- If a sort key is nullable, choose offset scrolling or a non-null sort key.
- Close Streams and verify fetch size, transactions, N+1, and memory.

Projection nullability governs how callers handle missing data; Sort properties govern query ordering; keyset scrolling further requires sort values to be non-null and present in the projection. Designing these three aspects properly keeps projections lean for the application while retaining sufficient data for stable pagination and scrolling.
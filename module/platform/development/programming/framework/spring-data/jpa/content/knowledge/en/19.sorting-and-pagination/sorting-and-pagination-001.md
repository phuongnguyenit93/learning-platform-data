# Sort, Sort.Order, and Multi-Property Sorting in Spring Data JPA

Spring Data provides `Sort` to describe the sort order of query results. A `Sort` consists of one or more `Sort.Order` instances; each Order specifies a **property**, a **sort direction** (ASC/DESC), a case-insensitivity option, and a NULL-handling hint.

When sorting by multiple properties is needed, the declaration order of the Orders determines priority: the first property is evaluated first, and subsequent properties are only used to break ties among rows that are equal on the preceding criteria. Combining `Sort` with a repository method or `Pageable` lets you change result ordering without creating a separate query for each sort combination.

This document uses Spring Data JPA in Spring Boot 3 and later. The repository/service examples are components that require a Spring project, entities, a database, and the corresponding dependencies; they are not standalone Java programs that can be run with just `javac`.

## 1. What Are Sort and Sort.Order?

- **`Sort`** is an object describing a list of sort criteria. It can contain one or more Orders.
- **`Sort.Order`** describes a single criterion: the property to sort by, Direction, case handling, and null handling.
- **`Sort.Direction`** has two main values: `ASC` (ascending) and `DESC` (descending).
- **`Sort.NullHandling`** describes a hint for the position of NULL values: native, first, or last.

Simple example:

```java
Sort sort = Sort.by("name").ascending();
```

This is equivalent to creating an ascending Order on the `name` property.

Sort does not execute a query and does not hold data. It only describes how results should be sorted; the repository or query execution translates this description into an ORDER BY clause appropriate for the store.

## 2. Creating a Sort with One Property

Common ways:

```java
Sort byNameAsc = Sort.by("name");
Sort byNameDesc = Sort.by("name").descending();

Sort byPriceAsc = Sort.by(Sort.Direction.ASC, "price");
Sort byCreatedDesc = Sort.by(Sort.Direction.DESC, "createdAt");
```

If only the property is passed without specifying a direction, the default is ASC.

An Order can be created explicitly:

```java
Sort.Order order = Sort.Order.asc("name");
Sort sort = Sort.by(order);
```

Or:

```java
Sort.Order order = Sort.Order.desc("createdAt");
Sort sort = Sort.by(order);
```

Creating an Order explicitly is useful when you need to add ignoreCase or null handling.

The property passed to Sort is the Java property name in the entity or a valid property path, not the physical column name in the database. For example, if an entity has `createdAt` mapped to column `created_at`, Sort must use `createdAt`.

## 3. Sorting by Multiple Properties

There are several ways to create a Sort with multiple Orders:

```java
Sort sort = Sort.by("lastName", "firstName");
```

Both criteria are ASC. `lastName` takes priority; when two rows have the same lastName, the system then evaluates firstName.

A shared direction can be specified:

```java
Sort sort = Sort.by(
    Sort.Direction.DESC,
    "createdAt",
    "id"
);
```

Both createdAt and id are DESC.

When each property has its own direction, use multiple Orders:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("createdAt")
);
```

The corresponding order in SQL means:

```sql
order by last_name asc,
         first_name asc,
         created_at desc
```

The SQL above is for illustration only; actual column names and syntax are determined by the mapping, provider, and database.

### 3.1. Priority Order of Orders

Suppose the data is:

| lastName | firstName | score |
|---|---|---:|
| Nguyen | An | 90 |
| Nguyen | Binh | 85 |
| Tran | An | 95 |
| Nguyen | An | 98 |

Sort:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("score")
);
```

Logical result:

| lastName | firstName | score |
|---|---|---:|
| Nguyen | An | 98 |
| Nguyen | An | 90 |
| Nguyen | Binh | 85 |
| Tran | An | 95 |

lastName is evaluated first; within the Nguyen group, firstName is evaluated; within the same Nguyen/An group, score DESC determines the order.

Do not reverse the order of Orders if the business requirement calls for a different priority. `Sort.by("firstName", "lastName")` is not equivalent to `Sort.by("lastName", "firstName")`.

## 4. Using Sort.Order for Detailed Configuration

An Order can be created using factory methods:

```java
Sort.Order ascending = Sort.Order.asc("name");
Sort.Order descending = Sort.Order.desc("createdAt");
```

A constructor can also be used:

```java
Sort.Order order = new Sort.Order(
    Sort.Direction.DESC,
    "createdAt"
);
```

Commonly used methods:

| Method | Effect |
|---|---|
| `Sort.Order.asc(property)` | Creates an ascending Order |
| `Sort.Order.desc(property)` | Creates a descending Order |
| `ignoreCase()` | Requests case-insensitive string sorting |
| `nullsFirst()` | Hints to place NULL values first |
| `nullsLast()` | Hints to place NULL values last |
| `nullsNative()` | Uses the datastore's default NULL behavior |
| `with(direction)` | Creates an Order with the same property but a different direction |
| `reverse()` | Reverses the direction of the Order |
| `isAscending()` / `isDescending()` | Checks the sort direction |
| `getProperty()` | Gets the property path |
| `getDirection()` | Gets the direction |
| `getNullHandling()` | Gets the null handling hint |

Order is an immutable value object; configuration methods return a new Order. Assign the returned value when chaining methods.

## 5. Case-Insensitive Sorting

For string properties, `ignoreCase()` can be used:

```java
Sort sort = Sort.by(
    Sort.Order.asc("name").ignoreCase()
);
```

For example, values `alpha`, `Beta`, `CHARLIE` are sorted in a case-insensitive manner according to how the provider/database executes it.

Combining with multiple properties:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName").ignoreCase(),
    Sort.Order.asc("firstName").ignoreCase(),
    Sort.Order.asc("id")
);
```

Notes:

- Only use ignoreCase for string properties.
- The provider may translate it into an expression such as `LOWER(column)` or use the corresponding database mechanism.
- Database collation also affects how uppercase/lowercase letters, diacritics, and locale are compared.
- Applying a function to a column may prevent a regular B-tree index from being used directly; inspect the execution plan or consider an appropriate functional index/collation.
- IgnoreCase does not automatically normalize Vietnamese diacritics or locale-specific sorting rules.

If language-specific ordering is required, define the desired collation in the database and test with accented data, rather than assuming ignoreCase handles all linguistic rules.

## 6. Sorting NULL Values

You can set a NULL position hint on each Order:

```java
Sort nullFirst = Sort.by(
    Sort.Order.asc("publishedAt").nullsFirst()
);

Sort nullLast = Sort.by(
    Sort.Order.asc("publishedAt").nullsLast()
);
```

Three main options:

- `nullsFirst()`: requests that NULL appear before other values.
- `nullsLast()`: requests that NULL appear after other values.
- `nullsNative()`: lets the database/provider use its default behavior.

**Null handling is a hint to the datastore; not every database/provider guarantees identical execution.** Default behavior when sorting ASC/DESC also differs across databases. If NULL positioning is an important business rule, inspect the generated SQL and run integration tests against the actual production database.

If a more portable ordering is needed, you can express the NULL rule using CASE in JPQL:

```jpql
select p
from Product p
order by
    case when p.publishedAt is null then 1 else 0 end asc,
    p.publishedAt desc,
    p.id asc
```

The CASE expression places rows with NULL publishedAt after rows that have a date. However, when combining with dynamic Sort, avoid creating two conflicting criteria on the same property and check the execution plan because CASE can affect index usage.

## 7. Combining Multiple Orders with Direction, ignoreCase, and NULL

Each Order can be configured independently:

```java
Sort sort = Sort.by(
    Sort.Order.asc("country").ignoreCase().nullsLast(),
    Sort.Order.asc("city").ignoreCase().nullsLast(),
    Sort.Order.desc("createdAt").nullsLast(),
    Sort.Order.asc("id")
);
```

Meaning:

1. Country ASC, case-insensitive, NULL last.
2. City ASC, case-insensitive, NULL last.
3. CreatedAt DESC, NULL last.
4. ID ASC to break ties among remaining equal rows.

Not every datastore enforces every null hint; verify actual behavior. ignoreCase is only suitable for string properties.

You can create an Order and then change its direction:

```java
Sort.Order newestFirst = Sort.Order.asc("createdAt")
    .with(Sort.Direction.DESC);

Sort sort = Sort.by(newestFirst, Sort.Order.asc("id"));
```

## 8. Combining and Reversing Sort

Two Sort objects can be combined using `and()`:

```java
Sort primary = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName")
);

Sort tieBreaker = Sort.by(
    Sort.Order.asc("id")
);

Sort combined = primary.and(tieBreaker);
```

The Orders of primary come first, followed by the Orders of tieBreaker.

You can reverse the direction of an entire Sort:

```java
Sort reversed = combined.reverse();
```

Reverse flips ASC to DESC and vice versa for each Order. It does not change the priority order of the properties.

You can inspect a Sort:

```java
if (sort.isSorted()) {
    // There is at least one Order.
}

Sort none = Sort.unsorted();
boolean sorted = none.isSorted(); // false
```

Use `Sort.unsorted()` when you do not want to apply dynamic sorting. Do not pass null if the API allows using an explicit unsorted value.

## 9. Using Sort in Derived Query Methods

Spring Data JPA supports adding a Sort parameter to a repository method:

```java
public interface UserRepository
        extends JpaRepository<User, Long> {

    List<User> findByActiveTrue(Sort sort);
}
```

Calling from a service:

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName"),
    Sort.Order.desc("createdAt")
);

List<User> users = userRepository.findByActiveTrue(sort);
```

Spring Data builds the predicate from the method name and appends the sort order according to the passed Sort.

Some methods can declare static ordering directly in the name:

```java
List<User> findByActiveTrueOrderByLastNameAscFirstNameAsc();
```

Static OrderBy fits when the order is fixed. A Sort parameter fits when the caller needs to choose the order at runtime. Avoid designing a method that has both static OrderBy and a dynamic Sort parameter unless the combination order is clearly understood; inspect the actual query to avoid duplicate or conflicting ORDER BY clauses.

## 10. Using Sort with @Query JPQL

Sort can also be used with repository methods annotated with `@Query`:

```java
@Query("""
    select u
    from User u
    where u.active = true
    """)
List<User> findActiveUsers(Sort sort);
```

Calling:

```java
List<User> users = userRepository.findActiveUsers(
    Sort.by(
        Sort.Order.asc("lastName").ignoreCase(),
        Sort.Order.asc("firstName").ignoreCase()
    )
);
```

Spring Data JPA can dynamically append ORDER BY to JPQL. The property in Sort must resolve to a domain model property or a valid alias present in the query.

Example projection with alias:

```java
@Query("""
    select u.firstname as firstName,
           length(u.firstname) as nameLength
    from User u
    where u.active = true
    """)
List<Object[]> findNamesAndLengths(Sort sort);
```

If the query declares a valid alias and Spring Data recognizes it, you can sort by that alias, for example `Sort.by("nameLength")`. Verify with the specific projection/query type.

## 11. Sorting by Nested Property Paths

Sort can use a property path through an association:

```java
Sort sort = Sort.by(
    Sort.Order.asc("department.name"),
    Sort.Order.asc("lastName")
);
```

If User has a relationship to Department, `department.name` is a property path in the entity model. The provider can generate the necessary JOIN to sort.

Notes:

- The property path must exist and match the Java mapping name.
- Sorting through an association can cause the query to generate a JOIN.
- Sorting through a to-one relationship is generally easier to reason about.
- Sorting by a collection-valued association usually does not have a single clear value per parent entity; write an explicit query/aggregate instead of passing an arbitrary property path.
- JOINs can complicate the query and affect pagination, count, and indexes.

Do not use physical column names like `department_name` if that is not a property path or alias supported by the query.

## 12. Using Sort with Pageable and Pagination

`Pageable` holds the page number, page size, and Sort. It can be created with `PageRequest.of(page, size, sort)`:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<User> result = userRepository.findByActiveTrue(pageable);
```

Page index starts at 0. For example, page 0 is the first page, and size 20 is at most 20 results.

Repository:

```java
Page<User> findByActiveTrue(Pageable pageable);
```

Sort can be passed separately or attached to Pageable. When Pageable is already used, there is no need to add a separate Sort parameter for the same purpose.

### 12.1. Page, Slice, and List

- `Page<T>` contains content, page information, and total element/page counts. Usually requires a count query to calculate totals.
- `Slice<T>` indicates whether there is a next page without requiring the full total page count.
- `List<T>` with Pageable can limit results but does not provide page metadata like Page.

Use Slice if the UI only needs a “next” button and does not need the total record count. Sort inside Pageable still determines the result order.

### 12.2. Stable Ordering During Pagination

When paginating, add a unique property as a tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

If you only sort by createdAt and multiple rows share the same timestamp, the order among tied rows is indeterminate. When data changes between requests, users may see duplicate or skipped rows across different pages.

A unique tie-breaker makes ordering more deterministic. Even so, offset pagination can still shift when new data is inserted/deleted at the beginning of the list. For large datasets with continuous writes, consider keyset/scrolling pagination as supported by Spring Data and the query.

## 13. Dynamic Sort from API and Whitelisting

Do not accept arbitrary property names from a request and pass them directly into Sort without control. Even though Spring Data validates property paths in many cases, a whitelist ensures the API only allows designed criteria and prevents untrusted identifiers from entering special queries.

Example mapping sort values from an API:

```java
public enum UserSortKey {
    NAME,
    CREATED_AT,
    EMAIL
}
```

Creating a Sort from the enum:

```java
public Sort toSort(UserSortKey key, Sort.Direction direction) {
    return switch (key) {
        case NAME -> Sort.by(
            new Sort.Order(direction, "lastName"),
            new Sort.Order(direction, "firstName"),
            Sort.Order.asc("id")
        );
        case CREATED_AT -> Sort.by(
            new Sort.Order(direction, "createdAt"),
            Sort.Order.asc("id")
        );
        case EMAIL -> Sort.by(
            new Sort.Order(direction, "email"),
            Sort.Order.asc("id")
        );
    };
}
```

In the example, ID ASC is always the tie-breaker. If direction also comes from the request, only convert from allowed ASC/DESC values; reject unknown values instead of concatenating strings into a query.

An API can accept multiple criteria, but you should limit the count, allowed properties, and directions. Whitelisting should be based on domain property paths, not SQL column names.

## 14. JpaSort.unsafe and Expression-Based Sorting

Normally, Spring Data JPA validates Sort properties so they correspond to a valid property path or alias. An expression such as `LENGTH(u.firstname)` is not a simple property and may be rejected when passed through regular Sort.

Spring Data JPA provides `JpaSort.unsafe(...)` to add an ORDER BY expression that is not checked as a property path:

```java
import org.springframework.data.jpa.domain.JpaSort;

Sort sort = JpaSort.unsafe(
    Sort.Direction.ASC,
    "LENGTH(u.firstname)"
);
```

Using unsafe carries risk because the expression is inserted into the query string. Only use developer-controlled literals; **never pass user-supplied expressions, column names, or sort fragments directly into JpaSort.unsafe**.

Whenever possible, choose one of the safer alternatives:

1. Put the expression in SELECT with a valid alias and sort by the alias.
2. Write a JPQL query with a fixed ORDER BY.
3. Create a custom repository with a whitelisted list of expressions.
4. Use a properly designed function/column and appropriate database index.

Example query with an alias:

```java
@Query("""
    select u.firstname as firstName,
           length(u.firstname) as nameLength
    from User u
    where u.active = true
    """)
List<Object[]> findActiveNames(Sort sort);
```

Consider sorting by `nameLength` if the query parser and projection support that alias. Test the actual SQL with the Spring Data JPA version in use.

## 15. Sort Does Not Modify Data and Does Not Guarantee Order Without an Order

Sort only changes the order of rows in the query result. It does not:

- Update entity values.
- Change the physical order of rows in the database.
- Automatically create indexes.
- Guarantee ordering if the query has no ORDER BY.
- Replace filtering in WHERE.
- Replace pagination or row limiting.

If no Sort is passed and the query has no ORDER BY, the database does not guarantee a stable order. Do not rely on insertion order, ID, or a previous run.

An empty Sort can be represented by `Sort.unsorted()`. If the query has a fixed ORDER BY, the query can still sort by that order even if no dynamic Sort is passed.

## 16. Indexes and Sorting Performance

ORDER BY may require the database to sort results using memory or temporary storage if an index does not support the required order. Some principles:

- Index columns commonly used in WHERE/JOIN/ORDER BY based on actual workload.
- For filtering by status and sorting by createdAt, evaluate a composite index consisting of status and createdAt.
- When sorting by multiple columns, the column order in the index matters.
- DESC/ASC and backward scan capability depend on the database/index implementation.
- Sorting by LOWER(property) or CASE may require a functional index or expression index.
- Sorting across an association may add a JOIN and increase cost.
- Indexes help reads/sorting but increase storage size and INSERT/UPDATE/DELETE cost.

Example query:

```jpql
select u
from User u
where u.active = true
order by u.createdAt desc, u.id desc
```

A candidate index might start with `active`, followed by `created_at` and `id`, but the optimal structure depends on selectivity, row count, database, and other queries. Use EXPLAIN/EXPLAIN ANALYZE on production-like data to inspect the plan rather than creating indexes by guesswork.

## 17. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Sort cannot find property | Using SQL column name or wrong property path | Use Java property name or valid query alias |
| Multi-criteria sort result in wrong order | Reversed Order sequence | Place the highest-priority criterion first |
| All properties unexpectedly share the same direction | Using `Sort.by(Direction, ...)` with a shared direction | Create individual `Sort.Order` instances |
| IgnoreCase does not behave as expected | Property is not String, or collation/provider differences | Use only for String; test locale/collation |
| NULL appears in the wrong position | Database/provider ignores null handling hint | Inspect SQL; use CASE or a database-specific query |
| Nested property sort makes query slow | Provider generates a JOIN or index is missing | Inspect SQL/EXPLAIN; consider projection |
| Pagination has duplicate/skipped rows | Non-unique ordering or data changes between pages | Add a unique tie-breaker; consider keyset pagination |
| Dynamic sort does not work in native query | Native SQL rewriting capability is limited | Use fixed ORDER BY or custom query with whitelist |
| Function in Sort is rejected | Function is not a valid property path | Use alias/fixed query or JpaSort.unsafe with trusted literal |
| SQL injection via sort expression | Concatenating identifier/fragment from input | Whitelist properties and never pass input directly to unsafe |
| Index is not used | Function, column order, or unsuitable selectivity | Inspect execution plan and design indexes for the workload |

## 18. Testing Sort

Integration tests should verify actual ordering on the target database/provider:

- Single property ASC and DESC.
- Multiple properties with different directions.
- Two rows tied on the first criterion and broken by the next criterion.
- IgnoreCase with uppercase/lowercase characters.
- NULLS FIRST/LAST according to the database in use.
- Nested property sort and generated JOIN.
- Sort combined with PageRequest and Page/Slice.
- Stable ordering when multiple rows share the same sort value.
- Properties outside the whitelist rejected at the API layer.
- Native queries and JpaSort.unsafe controlled, accepting no user-supplied fragments.

Example test for multi-criteria logic:

```java
@Test
void sortsByLastNameThenFirstName() {
    Sort sort = Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("firstName"),
        Sort.Order.asc("id")
    );

    List<User> users = repository.findByActiveTrue(sort);

    assertThat(users)
        .extracting(User::getLastName, User::getFirstName)
        .containsSubsequence(
            tuple("Nguyen", "An"),
            tuple("Nguyen", "Binh"),
            tuple("Tran", "An")
        );
}
```

The example assumes repository, entity, fixtures, and AssertJ tuple assertions are already configured. If multiple rows share the same lastName/firstName, add fixtures and verify the ID tie-breaker to confirm complete ordering.

## 19. Pre-Production Checklist for Sort

- [ ] Are properties in Sort valid domain property paths or query aliases?
- [ ] Is the highest-priority Order placed first?
- [ ] Is Direction configured individually for each property when needed?
- [ ] Is ignoreCase only used on string properties?
- [ ] Has null handling been tested on the actual database?
- [ ] Is there a unique tie-breaker when paginating?
- [ ] Is dynamic sort from requests whitelisted?
- [ ] Is user input never passed to JpaSort.unsafe?
- [ ] Do native queries support dynamic Sort in the current structure?
- [ ] Does nested association sorting generate unexpected JOINs?
- [ ] Have indexes and execution plans been checked?
- [ ] Do Page/count queries return accurate metadata?

## 20. Conclusion

`Sort` is a collection of sort criteria; `Sort.Order` describes a single property, direction, and options such as ignoreCase/null handling. When sorting by multiple properties, Order sequence determines priority: the first property classifies first, and subsequent properties act as tie-breakers.

Use `Sort.by(...)` for simple cases, `Sort.Order` when per-property direction/NULL/case options are needed, `Sort.and()` to combine criteria, and `PageRequest.of(..., sort)` when paginating. Properties must be Java mapping names or valid query aliases, not SQL column names. For dynamic sorting, whitelist properties and directions; only use `JpaSort.unsafe` for trusted static expressions. Finally, verify the SQL, execution plan, and NULL ordering on the actual database before deploying.

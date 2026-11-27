# Sort Direction, NULL Ordering, and Database Differences

Spring Data JPA lets you sort results using Sort, Pageable, derived queries, or ORDER BY in JPQL. Besides choosing ascending (ASC) or descending (DESC), a query must also determine how NULL values are handled. This is an area that easily causes differences across database management systems: the same ORDER BY clause may place NULLs first in one database and last in another.

This lesson explains sort directions, ordering by multiple criteria, null handling options in Spring Data, default behaviors across several databases, how to specify NULL FIRST/LAST explicitly using JPQL CASE, pagination implications, and how to safely accept sort requests from an API.

## 1. What Do ASC and DESC Mean?

ORDER BY specifies the order of rows in a query result:

- **ASC (ascending)**: ascending order.
- **DESC (descending)**: descending order.

For numbers, ASC puts smaller values first and DESC puts larger values first:

~~~sql
SELECT id, total
FROM purchase_orders
ORDER BY total ASC;
~~~

~~~sql
SELECT id, total
FROM purchase_orders
ORDER BY total DESC;
~~~

For dates and times, ASC typically puts earlier timestamps first and DESC puts newer timestamps first. For strings, ordering depends on the database collation, character comparison rules, case sensitivity, and diacritics.

In JPQL, use entity names and Java property names:

~~~jpql
select o
from PurchaseOrder o
order by o.createdAt desc
~~~

Do not use SQL table or column names when writing JPQL. If the Java field is createdAt while the column is created_at, JPQL still uses o.createdAt.

## 2. Sorting by Multiple Criteria

A query can sort by multiple expressions:

~~~jpql
select o
from PurchaseOrder o
order by o.status asc, o.createdAt desc, o.id desc
~~~

The database applies the criteria from left to right:

1. Sort status ascending.
2. If status values are equal, sort createdAt descending.
3. If both status and createdAt are equal, sort id descending.

The final criterion should generally be a unique key to produce a deterministic order. If you sort only by createdAt, multiple records sharing the same timestamp may change positions between executions.

Stable ordering is especially important for pagination, report exports, batch processing, or resuming reads from a previous page.

## 3. Sort in Spring Data JPA

A repository can accept Sort to determine ordering at call time:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(
        OrderStatus status,
        Sort sort
    );
}
~~~

Creating a Sort with one criterion:

~~~java
Sort ascending = Sort.by(
    Sort.Direction.ASC,
    "createdAt"
);

Sort descending = Sort.by(
    Sort.Direction.DESC,
    "createdAt"
);
~~~

Creating a Sort with multiple criteria:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Or configuring each Order individually:

~~~java
Sort sort = Sort.by(
    new Sort.Order(Sort.Direction.DESC, "createdAt"),
    new Sort.Order(Sort.Direction.ASC, "reference")
);
~~~

Property names in Sort are the entity's Java properties. Do not use SQL column names unless you are working with a native query and the column/alias is supported by the parser.

## 4. Sort Direction Is Independent of NULL Ordering

ASC and DESC define the comparison direction among comparable values. However, NULL is not an ordinary value. SQL treats NULL as an absent or unknown value, so its ordering requires a separate rule.

Example data:

| id | dueAt |
|---:|---|
| 1 | 2026-03-01 |
| 2 | NULL |
| 3 | 2026-01-15 |
| 4 | NULL |
| 5 | 2026-02-10 |

There are two independent requirements:

- Sort earlier dates first or newer dates first?
- Should NULL values come before or after non-null dates?

Examples:
- Dates ascending, NULLs first.
- Dates ascending, NULLs last.
- Dates descending, NULLs first.
- Dates descending, NULLs last.

Do not assume DESC always puts NULLs first or ASC always puts NULLs last. The default depends on the database.

## 5. Default NULL Ordering Differs Across Databases

Without specifying a NULL rule, common databases have the following defaults:

| Database | Default ASC | Default DESC |
|---|---|---|
| PostgreSQL | NULLs last | NULLs first |
| Oracle Database | NULLs last | NULLs first |
| MySQL | NULLs first | NULLs last |
| SQL Server | NULLs first | NULLs last |
| SQLite | NULLs first | NULLs last |

This table describes the common default behavior of the listed database systems. Verify against your project's specific database version and syntax, especially when queries run across multiple DBMSs or use complex sort expressions.

Consequently, the same statement:

~~~sql
ORDER BY due_at ASC
~~~

can return different orders between PostgreSQL and MySQL when the due_at column contains NULLs.

If an application switches databases or runs tests on H2 while production uses a different database, tests may fail to catch NULL ordering differences. Requirements regarding NULL positioning must be explicitly stated in the query and tested on the target database.

## 6. NullHandling in Sort.Order

Spring Data provides hints for NULL positioning via Sort.Order:

~~~java
Sort nullsFirst = Sort.by(
    Sort.Order.asc("dueAt").nullsFirst()
);

Sort nullsLast = Sort.by(
    Sort.Order.asc("dueAt").nullsLast()
);

Sort nativeNullOrder = Sort.by(
    Sort.Order.asc("dueAt").nullsNative()
);
~~~

Methods:

- **nullsFirst()**: requests/hints that NULLs appear first.
- **nullsLast()**: requests/hints that NULLs appear last.
- **nullsNative()**: lets the database or datastore apply its default behavior.

In Spring Data, these are null-handling metadata/hints on the Order. A JPA provider or datastore may not implement every hint in the same way. Do not treat nullsFirst()/nullsLast() as an absolute portability guarantee across every provider and database.

Example combining multiple criteria:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("dueAt").nullsLast(),
    Sort.Order.desc("priority"),
    Sort.Order.asc("id")
);
~~~

The intent is dueAt ascending with NULLs last; among rows with the same dueAt, priority descending; and finally id ascending.

Inspect the generated SQL and results on the actual database system. If NULL positioning is a strict business requirement that must behave identically across all databases, express it explicitly in the query.

## 7. NULLS FIRST and NULLS LAST in SQL

Some databases support syntax to specify NULL position directly in ORDER BY:

~~~sql
SELECT id, due_at
FROM tasks
ORDER BY due_at ASC NULLS LAST;
~~~

Or:

~~~sql
SELECT id, due_at
FROM tasks
ORDER BY due_at DESC NULLS FIRST;
~~~

NULLS FIRST/LAST syntax is supported by PostgreSQL and Oracle; SQLite also supports this syntax in modern versions. MySQL and SQL Server do not use this same syntax in ORDER BY; an alternative expression such as CASE is required.

Do not copy native SQL syntax from one database into an application running on another DBMS without checking. Standard JPQL should also avoid relying on dialect-specific NULLS FIRST/LAST syntax. For a more portable expression, use CASE in JPQL.

## 8. Specifying NULL Explicitly with CASE in JPQL

You can create a secondary sort key to separate NULL and non-NULL values.

Example with dates ascending, NULLs last:

~~~java
@Query("""
    select t
    from Task t
    order by
        case when t.dueAt is null then 1 else 0 end asc,
        t.dueAt asc,
        t.id asc
    """)
List<Task> findAllByDueDateAscendingNullsLast();
~~~

Explanation:

- For non-null dueAt, CASE returns 0.
- For NULL dueAt, CASE returns 1.
- Sorting the CASE key ascending puts the group with dates (0) before the NULL group (1).
- dueAt ASC sorts older dates before newer dates within the non-null group.
- id ASC provides a stable secondary order.

Dates ascending, NULLs first:

~~~jpql
order by
    case when t.dueAt is null then 0 else 1 end asc,
    t.dueAt asc,
    t.id asc
~~~

Dates descending, NULLs last:

~~~jpql
order by
    case when t.dueAt is null then 1 else 0 end asc,
    t.dueAt desc,
    t.id desc
~~~

Dates descending, NULLs first:

~~~jpql
order by
    case when t.dueAt is null then 0 else 1 end asc,
    t.dueAt desc,
    t.id desc
~~~

The CASE rule is always sorted ASC to control the NULL/non-NULL groups. The direction of the date property is decided independently with ASC or DESC.

CASE in JPQL is a clear way to avoid depending on database NULL defaults. Integration tests with the JPA provider and database in use are still necessary.

## 9. Entity and Repository Example

Task entity with nullable dueAt:

~~~java
package example.domain;

import jakarta.persistence.*;
import java.time.LocalDate;

@Entity
@Table(name = "tasks")
public class Task {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(name = "due_at")
    private LocalDate dueAt;

    @Column(nullable = false)
    private int priority;

    protected Task() {
    }

    public Task(String title, LocalDate dueAt, int priority) {
        this.title = title;
        this.dueAt = dueAt;
        this.priority = priority;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public LocalDate getDueAt() {
        return dueAt;
    }

    public int getPriority() {
        return priority;
    }
}
~~~

The repository can provide different sorting approaches:

~~~java
package example.repository;

import example.domain.Task;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface TaskRepository extends JpaRepository<Task, Long> {

    @Query("""
        select t
        from Task t
        order by
            case when t.dueAt is null then 1 else 0 end asc,
            t.dueAt asc,
            t.id asc
        """)
    List<Task> findDueDateAscendingNullsLast();

    @Query("""
        select t
        from Task t
        order by
            case when t.dueAt is null then 0 else 1 end asc,
            t.dueAt desc,
            t.id desc
        """)
    List<Task> findDueDateDescendingNullsFirst();

    List<Task> findAll(Sort sort);
}
~~~

Fixed JPQL methods explicitly express NULL ordering without relying on database defaults. The findAll(Sort) method allows dynamic sorting by property paths; use it when the datastore's NULL rule is acceptable or has been tested.

## 10. When to Use Sort Hints vs. CASE?

| Requirement | Appropriate Approach |
|---|---|
| Database default is acceptable | Sort.Order.nullsNative() or regular Sort |
| Want to declare NULL first/last hint via repository | Sort.Order.nullsFirst()/nullsLast(), then test on provider |
| Must place NULL in the same position across multiple databases | JPQL CASE or Criteria API CASE |
| Native SQL query running only on a single known database | Dialect-specific NULLS FIRST/LAST or CASE syntax |
| Need dynamic sort direction and fixed NULL rule | Criteria API/custom repository or whitelisted queries |
| Need complex sorting across multiple expressions | Controlled JPQL/Criteria/native query |

Sort is convenient when the attribute is a simple property path. CASE is useful when the sort rule needs an extra expression, such as always placing NULLs last regardless of whether dates are ascending or descending.

Do not use JpaSort.unsafe with arbitrary user-supplied sort strings to concatenate CASE or SQL. If dynamic expressions are needed, build them with Criteria API or select from predefined queries/expressions.

## 11. Dynamically Sorting Both Direction and NULL Position

A screen might allow users to choose dueAt ASC or DESC and NULL FIRST or LAST.

If using only Sort.Order, you can pass direction and null handling:

~~~java
Sort.Order order = new Sort.Order(direction, "dueAt")
    .nullsLast();
~~~

This expresses intent but remains subject to provider/datastore hint limitations.

If you must guarantee the exact same rule across multiple databases, a custom repository can use CriteriaBuilder to construct a CASE expression. For example:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Task> query = cb.createQuery(Task.class);
Root<Task> task = query.from(Task.class);

Expression<Integer> nullRank = cb.<Integer>selectCase()
    .when(cb.isNull(task.get("dueAt")), 1)
    .otherwise(0);

List<jakarta.persistence.criteria.Order> orders =
    new ArrayList<>();

orders.add(cb.asc(nullRank));

if (direction == Sort.Direction.ASC) {
    orders.add(cb.asc(task.get("dueAt")));
    orders.add(cb.asc(task.get("id")));
} else {
    orders.add(cb.desc(task.get("dueAt")));
    orders.add(cb.desc(task.get("id")));
}

query.select(task).orderBy(orders);
~~~

The example above fixes NULLs at the end and varies the direction of dueAt/id according to direction. To support NULL FIRST, swap nullRank values to 0 for NULL and 1 for non-NULL. In a real custom repository, also add predicates, TypedQuery, parameters, pagination, and appropriate sort property whitelisting.

## 12. Distinguishing NULL from Empty Strings

NULL is not the same as an empty string:

- NULL represents an absent or unknown value.
- An empty string is a String value of length 0 in databases that distinguish the two states.

Some DBMSs have specific rules. Oracle Database treats zero-length character strings as NULL in many SQL contexts. PostgreSQL and MySQL distinguish empty strings from NULL.

Therefore, if a column is VARCHAR and the application stores both NULL and empty strings, sort ordering can differ. Decide whether the domain treats the two states as equivalent and normalize data at the appropriate layer.

Do not use IS NULL to search for empty strings in databases that distinguish the two states. To find empty strings, compare against the empty string according to the database's semantics.

## 13. Collation, Case Sensitivity, and Vietnamese Diacritics

String ordering does not depend solely on ASC/DESC. Databases also use collation to compare characters:

- Whether comparison is case-sensitive or case-insensitive.
- Whether diacritics are distinguished or ignored.
- Locale-specific alphabetical ordering.
- How Unicode characters and normalization are handled.

For example, the names "An", "Ánh", "an" can be sorted differently across collations. Spring Data's Sort.Order.ignoreCase() can request case-insensitive comparison, though how it is translated and its effectiveness depend on the provider/database.

If an application needs consistent Vietnamese ordering, configure an appropriate collation in the database or use a normalized sort expression. Test with actual accented characters, mixed casing, and Unicode text. Do not assume Java String.compareTo() and database ORDER BY share the same rules.

## 14. NULLs and Pagination

Pagination requires stable ordering. If the sort key can contain NULLs, the query must have a clear NULL-positioning rule when results need to be consistent across calls.

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("dueAt").nullsLast(),
    Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Page<Task> page = taskRepository.findAll(pageable);
~~~

If the provider/database does not enforce the null handling hint as desired, pagination results may vary. When portability is needed, use a query with CASE or a custom Criteria query.

Offset pagination can also shift when new data is inserted or deleted between two page fetches. A unique tie-breaker makes ordering deterministic at each query execution, but it does not automatically provide a consistent snapshot across multiple requests.

With keyset scrolling, sort fields participate in the continuation comparison condition. NULLs complicate comparison conditions; many keyset mechanisms require non-null sort keys or have version-specific limitations. Prefer non-null sort keys when keyset is needed, or verify your Spring Data/provider version's support before designing.

## 15. Indexes and Performance When Sorting

ORDER BY can use an index if the index structure and query align. Example:

~~~sql
CREATE INDEX idx_tasks_due_at_id
    ON tasks(due_at, id);
~~~

An index on due_at and id can support queries sorting by those two columns, depending on the database, index direction, filter conditions, and execution plan.

When using CASE to sort by NULL groups, the database may have to evaluate the expression across many rows. A regular index on due_at cannot always satisfy the entire ORDER BY CASE, due_at, id.

Options:

- Inspect EXPLAIN/EXPLAIN ANALYZE.
- Create indexes tailored to actual filter conditions and sort order.
- Consider an expression/function index if supported by the database and usable by the query.
- Use a normalized column or maintained sort key if the business requires it and update overhead is acceptable.
- Avoid sorting overly large datasets before limiting if a more selective filter can be applied first.

Do not create indexes based solely on column names. Measure queries with representative data and review the production database's execution plan.

## 16. Safely Accepting Sort Requests from an API

Do not let clients send arbitrary property names and pass them directly into Sort. Define a whitelist:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "due-date", "dueAt",
    "priority", "priority",
    "title", "title"
);

public Sort buildSort(String requestedField, String requestedDirection) {
    String property = SORT_FIELDS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction direction = switch (
        requestedDirection == null
            ? ""
            : requestedDirection.toLowerCase(Locale.ROOT)
    ) {
        case "asc" -> Sort.Direction.ASC;
        case "desc" -> Sort.Direction.DESC;
        default -> throw new IllegalArgumentException(
            "Direction must be asc or desc"
        );
    };

    return Sort.by(
        new Sort.Order(direction, property).nullsLast()
    );
}
~~~

In the example above:

- Only three public sort keys are permitted.
- They are mapped to Java properties.
- Only asc or desc directions are accepted.
- nullsLast is applied as a hint.

If NULL positioning must be consistent across databases, route to a controlled CASE query or Criteria API instead of relying on hints. Also limit the number of sort criteria and page size.

## 17. Testing NULL Ordering and Database Differences

An integration test suite should include data with:

- A row with an older dueAt.
- A row with a newer dueAt.
- At least two rows with NULL dueAt.
- Two rows with the same dueAt but different IDs.
- Strings with mixed case and Vietnamese diacritics if text sorting is required.

Verify:

1. ASC and DESC sort non-null values in the right direction.
2. nullsFirst/nullsLast behave as expected with the actual provider/database.
3. CASE expressions place NULLs in the exact intended position.
4. Tie-breakers produce deterministic order when primary values match.
5. Pages maintain consistent ordering across pages.
6. Native SQL uses syntax valid for the target database.
7. Empty strings and NULLs are distinguished according to the database.
8. Collation produces results matching language requirements.

If production uses PostgreSQL, MySQL, Oracle, or SQL Server, run integration tests on that exact database engine. H2 can be useful for fast tests, but it does not prove that NULL defaults and collation match the production database.

## 18. Common Pitfalls and Fixes

**1. ASC/DESC returns NULLs in the opposite position from expected**

Check the database's NULL defaults. Use Sort.Order.nullsFirst/nullsLast as a hint, or CASE if an explicit rule is needed.

**2. Same query returns different order in local vs. production**

Check the database engine, version, collation, and NULL ordering. Test against the same target database.

**3. Sort cannot find property**

Use the entity's Java property name instead of the SQL column name. For query projections, check aliases.

**4. nullsLast() does not produce the expected result**

It is a hint and can depend on the provider/datastore. Inspect the generated SQL; if portable behavior is needed, use CASE in JPQL/Criteria.

**5. Pagination duplicates or skips rows**

Add a unique sort criterion as a tie-breaker. Account for data changing between page fetches and use keyset when appropriate.

**6. Vietnamese string sorting is not in the desired order**

Check collation and case/diacritic handling. ignoreCase alone does not resolve all locale rules.

**7. Using NULL interchangeably with empty string**

Check database semantics. Oracle has specific rules for empty strings; other databases may clearly distinguish them.

**8. CASE query is slow**

Review the execution plan and indexes. CASE can make it hard for the database to use existing sort indexes; consider an expression index or a suitable sort key design.

**9. Passing raw sort fields from client into query**

Whitelist sort keys and directions. Never use JpaSort.unsafe with unvalidated input.

## 19. Workflow for Designing Result Ordering

When building a sorted repository query, follow this sequence:

1. Identify the property to sort by and its data type.
2. Choose ASC or DESC according to business requirements.
3. Determine whether NULL values must appear first or last.
4. If database defaults are acceptable, use native behavior and document the dependency.
5. If using Sort.Order.nullsFirst/nullsLast, test the hint on the actual provider.
6. If identical results across multiple databases are required, use CASE or Criteria API.
7. Add a unique key as a tie-breaker.
8. Check collation if sorting on strings.
9. Whitelist sort keys and directions from the API.
10. Verify pagination, keyset, and count queries.
11. Inspect the execution plan and indexes on the target database.
12. Write integration tests covering NULLs, duplicate values, and realistic data.

## 20. Self-Assessment Checklist

- [ ] I can explain ASC and DESC.
- [ ] I know how to sort by multiple criteria in priority order.
- [ ] I understand that NULL is not an ordinary value in SQL sorting.
- [ ] I know that NULL defaults differ across PostgreSQL, Oracle, MySQL, SQL Server, and SQLite.
- [ ] I know Sort.Order.nullsFirst(), nullsLast(), and nullsNative().
- [ ] I understand that null handling in Sort is a hint and requires provider testing.
- [ ] I know how to use CASE in JPQL to place NULLs first or last.
- [ ] I know how to distinguish NULL from an empty string.
- [ ] I understand how collation affects string and Vietnamese sorting.
- [ ] I add a unique tie-breaker to achieve stable ordering.
- [ ] I understand the impact of nullable sort keys on pagination/keyset.
- [ ] I know how to whitelist sort keys and directions from an API.
- [ ] I inspect indexes and execution plans when using CASE expressions.
- [ ] I have integration tests running on the target database.

## 21. Review Questions

**1. How do ASC and DESC differ?**

ASC sorts in ascending order; DESC sorts in descending order. For dates and times, ASC is typically oldest to newest, and DESC is newest to oldest.

**2. Why can't NULL position be inferred solely from ASC/DESC?**

Because NULL has separate sorting rules and defaults vary across databases. You need native null ordering, a Sort hint, or a CASE expression.

**3. Does Sort.Order.nullsLast() guarantee identical behavior across all databases?**

Not strictly. It is a hint to the datastore/provider. Test it and use CASE/Criteria when portable rules are required.

**4. How do you place NULLs last when sorting dates ascending?**

Use CASE to assign 0 to non-null dates and 1 to NULL, sort CASE ASC, then sort date ASC and ID ASC.

**5. How do you place NULLs last when sorting dates descending?**

Keep the CASE null-rank ascending with NULL as 1, then sort date DESC and add a unique key as a tie-breaker.

**6. Why is a tie-breaker needed for pagination?**

Multiple rows can share the same primary sort value. A unique key produces a deterministic order so pages are less likely to shift unexpectedly.

**7. How does collation affect Sort?**

Collation determines how the database compares strings, including case sensitivity, diacritics, and locale. Thus text sort results can differ across databases.

**8. When should you use Criteria API instead of simple Sort?**

When you need dynamic sorting by CASE expressions, portable NULL control, multiple conditions, or whitelisted expressions that Sort property paths cannot express.

By clearly separating ASC/DESC direction, NULL position, and string comparison rules, an application can produce more consistent results across databases, especially when combining Sort with pagination.

## References

- [Spring Data Commons — Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [PostgreSQL — Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html)
- [MySQL — Sorting Rows](https://dev.mysql.com/doc/refman/8.4/en/sorting-rows.html)
- [Oracle Database — Sorting Query Results](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Sorting-Query-Results.html)
- [SQLite — SELECT and ORDER BY](https://www.sqlite.org/lang_select.html)

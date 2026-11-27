# Distinct, countDistinct, and the Real Semantics of Counting in Spring Data JPA

## 1. What does Distinct mean in data queries?

When querying data, a value or an entity may appear multiple times in the results. This often happens when multiple records share the same property value, or when a JOIN on a one-to-many relationship causes a parent entity to appear across multiple SQL result rows.

SQL and JPQL provide the `DISTINCT` keyword to eliminate duplicate results across selected expressions. Spring Data JPA supports declaring distinct via repository method names or writing explicit queries with `@Query`.

Three distinct goals must be separated:

1. **Fetching distinct entities:** each entity appears only once, even when a JOIN produces multiple rows for the same entity.
2. **Fetching distinct property values:** a list of names, emails, cities, or other properties where each value appears only once.
3. **Counting distinct items:** counting the number of distinct entities or distinct values matching a condition.

These three goals are not equivalent. A method containing `Distinct` in its name does not automatically mean it counts distinct values of a property.

## 2. DISTINCT in SQL and JPQL

### 2.1. DISTINCT on selected expressions

Suppose the `users` table has the following data:

| id | name | city |
|---:|---|---|
| 1 | An | Hanoi |
| 2 | Binh | Hanoi |
| 3 | Chi | Da Nang |
| 4 | Dung | Hanoi |
| 5 | Ha | Da Nang |

SQL query:

~~~sql
SELECT DISTINCT city
FROM users;
~~~

The result has only two values:

~~~text
Hanoi
Da Nang
~~~

The database removes duplicate `city` values from the result set.

If the query selects both ID and city:

~~~sql
SELECT DISTINCT id, city
FROM users;
~~~

then all five rows still appear, because every `(id, city)` pair is unique. DISTINCT applies across the entire combination of selected expressions; it does not infer that duplicates should only be removed on the `city` column.

JPQL follows the same rule:

~~~java
@Query("select distinct u.city from User u")
List<String> findDistinctCities();
~~~

JPQL queries entities and Java properties. The entity name `User` and property `city` must match the mapping.

### 2.2. DISTINCT on entities

For example, to fetch a list of active users without returning the same entity multiple times:

~~~java
@Query("select distinct u from User u where u.active = true")
List<User> findDistinctActiveUsers();
~~~

When querying with a JOIN to a collection, a single user with multiple related records can produce multiple SQL rows. The expression `select distinct u` requests entity results with duplicate occurrences of the same user eliminated according to query semantics.

With derived queries, you can declare:

~~~java
List<User> findDistinctByActiveTrue();
~~~

This method returns `User` entities matching the active condition, with distinct applied to the entity results. It does not mean picking one representative user per name or per city.

If the goal is to get distinct cities, select the `city` property in JPQL:

~~~java
@Query("select distinct u.city from User u where u.active = true")
List<String> findDistinctActiveCities();
~~~

## 3. Derived queries with Distinct

Spring Data JPA parses repository method names to build queries. The `Distinct` keyword can be used with method families such as `find`, `read`, `get`, or `count`.

Example:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findDistinctByLastname(String lastname);

    long countDistinctByLastname(String lastname);
}
~~~

These two methods have different meanings:

- `findDistinctByLastname`: finds `User` entities with a matching lastname and eliminates duplicate entity results.
- `countDistinctByLastname`: counts matching entities according to the distinct count query derived by Spring Data.

To understand `countDistinctBy...` accurately, examine the expression Spring Data JPA actually counts.

## 4. Common pitfall: countDistinctByLastname does not count distinct last names

Suppose there are 100 users all having the last name `Nguyen`. If you call `countDistinctByLastname` with argument `Nguyen`, many developers expect `1` because only one distinct last name exists in that group.

However, Spring Data JPA's derived query `countDistinctByLastname` typically translates into a distinct count over the entity ID, conceptually resembling:

~~~sql
SELECT COUNT(DISTINCT u.id)
FROM users u
WHERE u.lastname = ?;
~~~

Because each user's ID is unique, the result equals the number of users with last name `Nguyen`, which can be 100—the same as `countByLastname("Nguyen")`.

This is a critical point:

**countDistinctByLastname typically counts the number of entities whose lastname matches the condition, not the number of distinct lastname values.**

A method name containing `Distinct` is not enough to determine which column is being counted. Inspect the generated query and the data type the business logic actually needs.

### Data example

| id | lastname |
|---:|---|
| 1 | Nguyen |
| 2 | Nguyen |
| 3 | Tran |
| 4 | Nguyen |
| 5 | Le |

With condition lastname = Nguyen:

| Query | Result | Meaning |
|---|---:|---|
| countByLastname("Nguyen") | 3 | Counts entities with last name Nguyen |
| countDistinctByLastname("Nguyen") | 3 | Counts distinct entity IDs with last name Nguyen |
| COUNT(DISTINCT lastname) across table | 3 | Counts distinct last name values: Nguyen, Tran, Le |

If filtering strictly by `lastname = Nguyen`, the number of distinct lastname values in the result set can only be 1 when matching records exist, whereas the entity count can be hundreds or millions.

## 5. Counting distinct property values with COUNT(DISTINCT field)

If business logic needs to count the number of distinct values of a property, write a query that explicitly counts that property.

Example: count the number of distinct cities with active users:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Query("""
        select count(distinct u.city)
        from User u
        where u.active = true
    """)
    long countDistinctActiveCities();
}
~~~

This query counts distinct `city` values, not user IDs.

To get the list of distinct cities:

~~~java
@Query("""
    select distinct u.city
    from User u
    where u.active = true
    order by u.city
""")
List<String> findDistinctActiveCities();
~~~

To count distinct last names within a filtered group:

~~~java
@Query("""
    select count(distinct u.lastname)
    from User u
    where u.active = true
""")
long countDistinctLastnamesOfActiveUsers();
~~~

If further filtering is needed, add conditions to the WHERE clause:

~~~java
@Query("""
    select count(distinct u.city)
    from User u
    where u.active = true
      and u.countryCode = :countryCode
""")
long countDistinctCities(
    @Param("countryCode") String countryCode
);
~~~

`COUNT(DISTINCT u.city)` counts distinct city values in the dataset after applying the WHERE conditions. Under SQL/JPQL semantics, NULL values are excluded from `COUNT(expression)`, even with DISTINCT.

## 6. Distinguishing COUNT(*), COUNT(field), and COUNT(DISTINCT field)

Three common count expressions have different meanings:

| Expression | Meaning |
|---|---|
| COUNT(*) | Counts rows in the result set |
| COUNT(u.city) | Counts rows where city is not NULL |
| COUNT(DISTINCT u.city) | Counts distinct non-NULL city values |

Data example:

| id | city |
|---:|---|
| 1 | Hanoi |
| 2 | Hanoi |
| 3 | Da Nang |
| 4 | NULL |
| 5 | Hanoi |
| 6 | NULL |

Results:

- `COUNT(*)` = 6 rows.
- `COUNT(city)` = 4 rows where city is not NULL.
- `COUNT(DISTINCT city)` = 2 distinct values: Hanoi and Da Nang.

If business rules require counting missing cities as a separate group, express that rule explicitly, for instance using `COALESCE` to replace NULL with an appropriate placeholder value. Choose a placeholder that cannot collide with valid data.

## 7. DISTINCT when JOINing one-to-many relationships

A common scenario is querying a parent entity together with a collection association.

Suppose an order has multiple line items. When JOINing `PurchaseOrder` with `OrderItem`, an order with three line items can generate three SQL result rows for the same order.

Example:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    join o.items i
    where i.productName = :productName
""")
List<PurchaseOrder> findOrdersContainingProduct(
    @Param("productName") String productName
);
~~~

If the same order has multiple matching items, `distinct` ensures each order entity is returned once in the result.

Without `distinct`, a join query may produce duplicate results depending on the query and provider. When you only need to check whether a matching line item exists, consider an `EXISTS` subquery instead of JOINing and deduplicating.

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where exists (
        select i.id
        from OrderItem i
        where i.order = o
          and i.productName = :productName
    )
""")
List<PurchaseOrder> findOrdersWithProduct(
    @Param("productName") String productName
);
~~~

This directly expresses the intent: retrieve orders that have at least one matching line item. Databases often optimize EXISTS well, though actual performance still depends on inspecting the execution plan and indexes.

## 8. DISTINCT with projections and scalar results

When a repository returns entities, `distinct` applies to entity results. When a repository returns a single property such as `String`, `distinct` applies to the selected scalar values.

Example:

~~~java
@Query("select distinct u.department from User u")
List<String> findDistinctDepartments();
~~~

The result is a list of unique department names.

If selecting multiple properties:

~~~java
@Query("""
    select distinct u.department, u.countryCode
    from User u
""")
List<Object[]> findDistinctDepartmentCountryPairs();
~~~

then `distinct` applies across the pair `(department, countryCode)`. Two rows with the same `department` but different `countryCode` remain two distinct results.

In real applications, use a DTO projection instead of `Object[]` when returning multiple fields:

~~~java
public record DepartmentCountry(
    String department,
    String countryCode
) {}
~~~

~~~java
@Query("""
    select distinct new com.example.shop.DepartmentCountry(
        u.department,
        u.countryCode
    )
    from User u
""")
List<DepartmentCountry> findDistinctDepartmentCountryPairs();
~~~

The DTO class name in a JPQL constructor expression must be the fully qualified class name. Parameter data types and order must match the constructor.

## 9. Counting distinct per group with GROUP BY

Sometimes you need to count entities or unique values per group, such as the number of distinct cities per country.

~~~java
@Query("""
    select u.countryCode, count(distinct u.city)
    from User u
    where u.active = true
    group by u.countryCode
    order by u.countryCode
""")
List<Object[]> countDistinctCitiesByCountry();
~~~

Each result row contains a country code and the count of distinct cities in that country. In real applications, replace `Object[]` with a DTO projection for readability and type safety.

Keep clear distinctions:

- `COUNT(DISTINCT u.city)` counts distinct cities within each group.
- `COUNT(u)` counts entities within each group.
- `COUNT(DISTINCT u.id)` counts distinct entity IDs within each group.

If there is a JOIN to a collection, choosing the right count expression is even more critical because JOINs can multiply rows before aggregation.

## 10. DISTINCT and pagination

When using `Page<T>`, Spring Data JPA usually needs two queries:

1. A query to fetch the current page's content.
2. A count query to compute total elements for `Page` metadata.

For queries involving `DISTINCT`, `JOIN`, or `GROUP BY`, an auto-derived count query might not accurately reflect the number of distinct entities or values returned by the page.

Example:

~~~java
@Query(
    value = """
        select distinct u
        from User u
        join u.roles r
        where r.name = :roleName
    """,
    countQuery = """
        select count(distinct u.id)
        from User u
        join u.roles r
        where r.name = :roleName
    """
)
Page<User> findDistinctUsersByRole(
    @Param("roleName") String roleName,
    Pageable pageable
);
~~~

Here:

- The content query returns distinct `User` entities.
- `countQuery` counts distinct user IDs, matching the goal of total entity count.
- If the goal is counting distinct scalar values, the count query must use the corresponding `COUNT(DISTINCT property)`.

When paginated queries have complex JOINs, inspect both the content query and the count query. Declare an explicit `countQuery` to guarantee the page total matches the business definition.

If you only need the page data and whether a next page exists without needing the total count, consider `Slice<T>` to avoid the total count query where appropriate.

## 11. Method names vs. @Query: which to choose?

| Need | Appropriate approach |
|---|---|
| Fetch entities matching condition, remove duplicate entities | findDistinctBy... |
| Count entities matching condition | countBy... |
| Count distinct entity IDs matching condition | countDistinctBy... |
| Count distinct values of a property | @Query with COUNT(DISTINCT e.field) |
| Fetch list of distinct scalar values | @Query with SELECT DISTINCT e.field |
| Count distinct after JOIN or complex grouping | JPQL @Query, declare countQuery if paginating |
| Use database-specific syntax | Native SQL, considering engine portability |

Derived queries work well for simple, readable conditions. When business logic needs to make clear whether it is counting IDs, a single property, or a combination, `@Query` is usually far clearer to readers.

## 12. Performance and practical notes

DISTINCT can force the database to sort or perform a hash aggregate to remove duplicates. On large datasets, this carries CPU, memory, or I/O costs depending on the execution plan.

Things to check:

- **JOIN:** if a JOIN multiplies rows, check whether you truly need distinct entities or can use `EXISTS`.
- **Indexes:** indexes on filter and join columns can help queries; whether an index helps DISTINCT depends on the database, column order, and execution plan.
- **Projections:** select only needed fields; do not load entire entities if only a scalar list is required.
- **COUNT:** distinct count queries on large datasets can be expensive. Measure with production-like data.
- **NULL:** `COUNT(expression)` ignores NULL; if business rules need a NULL group counted, express it separately.
- **Case and collation:** whether two strings differing in case count as the same value depends on expressions, collation, and data normalization.
- **Composite distinct:** standard JPQL does not provide a uniform portable way to count distinct across multiple columns as a tuple. To count pairs or multi-property tuples, use appropriate grouping/subqueries or database-specific native SQL.
- **Generated SQL:** method names are just input to query derivation. When results are unexpected, enable SQL and bind parameter logging in development to inspect the actual query.

Do not add `DISTINCT` out of habit to mask flawed JOIN results. Identify the source of duplicate rows and pick the right projection, JOIN, EXISTS, or count expression.

## 13. Process for determining the right count query

Before writing a repository method, state the requirement in a concrete sentence:

1. Do you want to count **entities** or **distinct property values**?
2. If counting property values, which property is the distinct expression?
3. Should NULLs be ignored or treated as a separate group?
4. Is there a one-to-many JOIN causing a single entity to appear multiple times?
5. Is pagination used, and do you need the total count or only whether a next page exists?
6. Does the generated query match the business meaning?

Examples:

- “How many users have last name Nguyen?” → `countByLastname("Nguyen")`.
- “How many distinct user IDs have last name Nguyen?” → `countDistinctByLastname("Nguyen")`; with unique IDs, the result usually matches a regular entity count.
- “How many distinct last names exist among all active users?” → `COUNT(DISTINCT u.lastname)`.
- “How many distinct cities exist in each country?” → `GROUP BY countryCode` combined with `COUNT(DISTINCT city)`.

## 14. Takeaways

- DISTINCT applies to the expression or set of columns selected in the query.
- `findDistinctBy...` typically returns distinct entities, not distinct values of an arbitrary property.
- Spring Data JPA's `countDistinctBy...` typically counts distinct entity IDs matching the condition; it may yield the same result as `countBy...`.
- To count distinct values of a property, write `COUNT(DISTINCT e.field)` in JPQL or SQL.
- `COUNT(*)`, `COUNT(field)`, and `COUNT(DISTINCT field)` have different meanings; `COUNT(expression)` ignores NULL.
- Collection JOINs can multiply rows; `select distinct entity` or `EXISTS` can express entity retrieval accurately.
- With pagination, the count query must count the same kind of items returned by the page content.
- Inspect generated SQL whenever a method name's meaning is unclear or results are unexpected.

What determines a valid count query is **what is being counted**: rows, entities, IDs, or unique property values. Write queries so the counted expression reflects that exact concept.
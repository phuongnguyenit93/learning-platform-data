# DISTINCT, Null Values, and Duplicate Results from Joins in JPQL

JPQL queries entities and Java attributes through the persistence model. When an entity is JOINed with a collection, a single row on the root entity side can match multiple related rows. Consequently, the same root entity can appear multiple times in the query results. JPQL provides the **DISTINCT** keyword to eliminate duplicate results; at the same time, JPQL follows SQL's three-valued logic for **NULL**, meaning comparisons against NULL do not behave like ordinary Java equality checks.

This lesson explains why JOINs produce duplicate results, how to use DISTINCT for entities and scalar values, how to count unique entities, how to handle NULL, the difference between ON and WHERE conditions in LEFT JOIN, and caveats when combining DISTINCT with pagination or fetch joins.

## 1. JPQL Works with Entities and Relationships

JPQL uses entity names and Java attribute names rather than SQL table and column names directly.

For example, consider two entities `Customer` and `PurchaseOrder`:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String city;

    private String phone;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name, String city, String phone) {
        this.name = name;
        this.city = city;
        this.phone = phone;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }

    public String getPhone() {
        return phone;
    }
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false)
    private String status;

    private BigDecimal total;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer, String status, BigDecimal total) {
        this.customer = customer;
        this.status = status;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

A `Customer` can have many `PurchaseOrder`s. The relationship is mapped as:

- `Customer.orders` is the inverse side with `@OneToMany(mappedBy = "customer")`.
- `PurchaseOrder.customer` is the owning side with `@ManyToOne` and `@JoinColumn`.
- Each `PurchaseOrder` belongs to one `Customer`; a `Customer` can have zero, one, or many orders.

The JPQL examples below use the entity names `Customer` and `PurchaseOrder` along with properties `id`, `city`, `status`, `total`, and `orders`.

## 2. Why Can JOIN Produce Duplicate Results?

Suppose the data contains:

| Customer | PurchaseOrder |
|---|---|
| An | Order 101, PAID |
| An | Order 102, PAID |
| An | Order 103, CANCELLED |
| Binh | Order 104, PAID |
| Chi | No orders |

Query:

~~~jpql
select c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

JOIN produces one result per matching Customer–PurchaseOrder pair. Customer An has two PAID orders, so Customer An matches twice. The logical result set can contain:

~~~text
An
An
Binh
~~~

This does not mean the database stores two Customer An records. One Customer is repeated in the results because two `PurchaseOrder` rows satisfy the JOIN condition.

You can visualize it as:

~~~text
Customer An
    |--- Order 101 (PAID)  ---> one result row
    |--- Order 102 (PAID)  ---> one result row

Customer Binh
    |--- Order 104 (PAID) ---> one result row
~~~

JOIN increases the number of intermediate rows according to the number of matching relationships. This is the normal behavior of a relational join.

## 3. Using SELECT DISTINCT to Retrieve Unique Entities

If the goal is to retrieve each Customer once, write:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    List<Customer> findDistinctByOrderStatus(
        @Param("status") String status
    );
}
~~~

DISTINCT specifies that query results must not contain duplicate entity values. With the query above, Customer An appears only once even with multiple PAID orders.

If you do not need to return the entity and only need customer names, you can query a scalar:

~~~jpql
select distinct c.name
from Customer c
join c.orders o
where o.status = :status
~~~

DISTINCT now applies to the selected value `c.name`. If two different Customers share the name An, the scalar result contains only one `An`. That differs from DISTINCT on the entity, because two entities with different IDs remain distinct entities even with the same name.

Clarify whether you want to deduplicate entities or deduplicate projected result values.

## 4. DISTINCT Across Multiple Columns or Expressions

If the query selects multiple expressions:

~~~jpql
select distinct c.city, o.status
from Customer c
join c.orders o
~~~

DISTINCT applies to the combination of selected values. Two rows are considered duplicates only if all corresponding values in the result match.

Example:

| city | status |
|---|---|
| Hanoi | PAID |
| Hanoi | CANCELLED |
| Ho Chi Minh City | PAID |

Two rows with the same city but different statuses remain two distinct results.

When using constructor expressions or projections, determine which combination of fields must be unique. DISTINCT does not mean that any single individual field in the projection must be unique.

## 5. COUNT and COUNT(DISTINCT ...)

When you need to count Customers who have PAID orders, do not count joined rows directly if the goal is the number of unique customers.

The query:

~~~jpql
select count(c)
from Customer c
join c.orders o
where o.status = :status
~~~

counts the rows after the JOIN. If An has two PAID orders, An is counted twice.

Use:

~~~jpql
select count(distinct c.id)
from Customer c
join c.orders o
where o.status = :status
~~~

Repository:

~~~java
@Query("""
    select count(distinct c.id)
    from Customer c
    join c.orders o
    where o.status = :status
    """)
long countCustomersWithOrderStatus(
    @Param("status") String status
);
~~~

`COUNT(DISTINCT c.id)` counts distinct Customer keys. Since ID is a non-null primary key, this is a clear way to count unique entities after a JOIN.

Common COUNT forms:

| JPQL | Meaning |
|---|---|
| `count(c)` | Counts non-null entity values in the result |
| `count(o.id)` | Counts orders with non-null id |
| `count(distinct c.id)` | Counts unique Customers |
| `count(c.phone)` | Counts non-null phones |
| `count(distinct c.city)` | Counts distinct non-null city values |

`COUNT(expression)` ignores NULL values. `COUNT(DISTINCT expression)` also excludes NULL. If you need to count rows even when an attribute can be null, select a non-null expression such as the primary key.

JPQL uses `COUNT(expression)`, not SQL's `COUNT(*)` syntax.

## 6. DISTINCT Does Not Alter JOIN Conditions

DISTINCT only removes duplicate results after the query determines which rows satisfy JOIN and WHERE. It does not change relationships or record counts in the database.

For example:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

means:

1. Join Customer with related PurchaseOrders.
2. Keep pairs whose status is PAID.
3. Return unique Customers in the result.

If a Customer has no PAID orders, that Customer does not appear because this is an INNER JOIN.

Do not use DISTINCT to mask an incorrect JOIN. If duplicate results appear because of a missing join condition or wrong relationship mapping, fix the root cause in the JOIN first. DISTINCT is appropriate only when entity duplication is the natural consequence of a one-to-many or many-to-many relationship and the business goal requires unique entities.

## 7. INNER JOIN and LEFT JOIN When Related Data Is Missing

INNER JOIN returns only Customers that have at least one matching PurchaseOrder.

~~~jpql
select c
from Customer c
join c.orders o
~~~

Customer Chi has no orders and is therefore excluded from results.

LEFT JOIN preserves the left-side Customer even when no matching PurchaseOrder exists:

~~~jpql
select c
from Customer c
left join c.orders o
~~~

The result can include An, Binh, and Chi. For Chi, attributes of `o` are treated as NULL in the joined result row.

If a Customer has multiple orders, LEFT JOIN can still produce multiple rows for the same Customer. To have each Customer appear once:

~~~jpql
select distinct c
from Customer c
left join c.orders o
~~~

LEFT JOIN does not automatically deduplicate results; it only keeps left-side rows when no right-side row matches.

## 8. Crucial Difference Between ON and WHERE Conditions with LEFT JOIN

The two queries below are not equivalent.

**Condition in ON:**

~~~jpql
select c
from Customer c
left join c.orders o on o.status = :status
~~~

The status condition is applied during the join pairing. Every Customer is still retained; Customers without an order of the selected status will have the `o` side as NULL.

**Condition in WHERE:**

~~~jpql
select c
from Customer c
left join c.orders o
where o.status = :status
~~~

WHERE filters after the JOIN. For Customers without orders, `o.status` is NULL; the condition `o.status = :status` is not true. Those rows are eliminated. The result therefore behaves essentially like an INNER JOIN for this condition.

To retrieve all Customers and pair PAID orders when present, put the condition in ON:

~~~jpql
select c, o
from Customer c
left join c.orders o on o.status = 'PAID'
~~~

To retrieve only Customers with at least one PAID order, use INNER JOIN or LEFT JOIN with WHERE:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

To retrieve Customers with no PAID orders, you can use LEFT JOIN with ON and check for a null right-side key:

~~~jpql
select c
from Customer c
left join c.orders o on o.status = 'PAID'
where o.id is null
~~~

Or use `NOT EXISTS`, which often expresses the intent clearly:

~~~jpql
select c
from Customer c
where not exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
      and o.status = 'PAID'
)
~~~

## 9. NULL in JPQL: Three-Valued Logic

In Java, you typically check for null using:

~~~java
value == null
~~~

In JPQL and SQL, NULL represents an unknown or missing value. Comparing against NULL with ordinary operators evaluates to UNKNOWN instead of TRUE or FALSE.

For example:

~~~jpql
where c.phone = null
~~~

is not the correct way to test for null.

Write:

~~~jpql
where c.phone is null
~~~

And:

~~~jpql
where c.phone is not null
~~~

Three-valued truth outcomes:

| Expression | Result |
|---|---|
| `NULL = NULL` | UNKNOWN |
| `NULL <> 'A'` | UNKNOWN |
| `NULL > 10` | UNKNOWN |
| `NULL LIKE 'A%'` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

WHERE keeps only rows where the condition evaluates to TRUE. Rows evaluating to FALSE or UNKNOWN are excluded.

This explains why equality comparisons with NULL fail to return the expected rows.

## 10. Combining AND, OR, and NOT with NULL

Three-valued logic also affects compound expressions.

Some rules:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Example:

~~~jpql
where c.phone is null or c.city = :city
~~~

If `phone` is NULL, the first operand is TRUE and the entire OR expression is TRUE, regardless of whether the other operand is UNKNOWN.

Conversely:

~~~jpql
where not (c.phone = :phone)
~~~

does not select rows with NULL phone, because the equality check evaluates to UNKNOWN and `NOT UNKNOWN` remains UNKNOWN.

If you want rows whose phone differs from a value or has no phone, state both explicitly:

~~~jpql
where c.phone <> :phone or c.phone is null
~~~

Design conditions around business intent and remember that UNKNOWN is not the same as FALSE in compound expressions.

## 11. Query Parameters with NULL Values

Suppose a repository has a method:

~~~java
@Query("""
    select c
    from Customer c
    where c.city = :city
    """)
List<Customer> findByCity(@Param("city") String city);
~~~

If `city = null` is passed, the condition becomes a comparison against NULL and does not return rows with NULL city as a standard null lookup would.

If you need rows where `city` is NULL, use an explicit condition:

~~~jpql
where c.city is null
~~~

When a parameter is optional, a simple pattern is:

~~~java
@Query("""
    select c
    from Customer c
    where (:city is null or c.city = :city)
    """)
List<Customer> searchByOptionalCity(@Param("city") String city);
~~~

- When `city` is NULL, the first operand is TRUE and the city filter is skipped.
- When `city` has a value, the first operand is FALSE and the query filters by `c.city`.

This pattern suits simple filters. With many optional filters, consider `Specification`, the Criteria API, or dynamic query building to avoid overly long JPQL and OR predicates that hinder index usage in some execution plans.

If you need to distinguish three states—no filter supplied, searching for NULL values, and searching for a specific value—a single nullable parameter cannot represent all three. Use an additional flag or construct a dynamic query based on caller choice.

## 12. COALESCE and NULLIF

JPQL provides useful functions for handling NULL.

**COALESCE** returns the first non-NULL expression:

~~~jpql
select c.id, coalesce(c.city, 'Not updated')
from Customer c
~~~

If `city` is NULL, the expression evaluates to `'Not updated'`.

**NULLIF(a, b)** returns NULL if `a` equals `b`; otherwise it returns `a`:

~~~jpql
select nullif(c.city, '')
from Customer c
~~~

If `city` is an empty string, the expression returns NULL. Otherwise it returns `city`.

COALESCE can be used in filtering or projections, while paying attention to expression data types. Arguments must have compatible types according to JPQL/provider rules.

Do not use COALESCE to hide differences between NULL and empty strings if business rules treat those two states differently.

## 13. NULL in IN and NOT IN

JPQL supports `IN` and `NOT IN`:

~~~jpql
where c.city in :cities
~~~

or:

~~~jpql
where c.city not in :cities
~~~

When the parameter list contains NULL, three-valued logic can make results unpredictable. For example, a value matching no non-null element when the list contains NULL can cause `IN` to yield UNKNOWN; `NOT IN` can likewise fail to return expected rows.

Do not include NULL in an `IN`/`NOT IN` list without clearly defined semantics. Separate null handling into its own condition:

~~~jpql
where c.city in :cities
   or c.city is null
~~~

If the list can be empty, handle that beforehand in the service layer or build a dynamic query. Behavior for empty collection parameters varies across providers/databases; do not depend on how a particular system interprets `IN ()`.

In addition, strip null elements from passed collections if the intent is to compare only non-null values.

## 14. NULL in Relationships and Collections

If a `Customer` has no orders, the `orders` collection relationship is normally an empty collection in the object model when initialized/loaded properly. In JPQL, you can check for an empty collection using `IS EMPTY`:

~~~jpql
select c
from Customer c
where c.orders is empty
~~~

Check for at least one element:

~~~jpql
select c
from Customer c
where c.orders is not empty
~~~

`IS EMPTY` is for collection-valued path expressions. Do not use `IS NULL` to check whether a collection has no elements. An empty collection relationship is different from a basic attribute having a NULL value.

To check whether a to-one relationship is unassigned, you can use:

~~~jpql
where c.primaryAddress is null
~~~

This condition applies when the relationship property is nullable. If the relationship is declared `optional = false` with a `NOT NULL` foreign key column, valid data should never be in that state.

## 15. Joining Multiple Collections Can Multiply Rows

Suppose a `Customer` has many `PurchaseOrder`s and many `Tag`s. If you JOIN both collections:

~~~jpql
select c
from Customer c
join c.orders o
join c.tags t
~~~

A Customer with 3 orders and 4 tags can produce 12 intermediate rows (3 × 4). This is the product of matching combinations from the two relationships.

DISTINCT can remove duplicate Customers:

~~~jpql
select distinct c
from Customer c
join c.orders o
join c.tags t
~~~

However, the database still has to execute the joins and process intermediate rows. DISTINCT may require sorting or hashing to deduplicate, depending on the execution plan.

If you only need to verify that at least one order and at least one tag exist, two `EXISTS` conditions can express the intent clearly and avoid multiplying rows:

~~~jpql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
and exists (
    select t.id
    from CustomerTag t
    where t.customer = c
)
~~~

Choose JOIN when you need data from related entities in the output or conditions. Choose EXISTS when you only need to check existence. Always review actual SQL and execution plans with production-scale data.

## 16. DISTINCT, Fetch Joins, and Lazy Loading

When you need to load `Customer` along with its `orders` collection, you can write:

~~~jpql
select distinct c
from Customer c
left join fetch c.orders
where c.city = :city
~~~

Fetch join loads the relationship in the same query to avoid N+1 queries when iterating each collection. Because a Customer can have many orders, the JOIN still generates multiple SQL rows for the same Customer.

DISTINCT expresses the intent for non-duplicate Customer entity results. SQL behavior and in-memory deduplication can depend on the JPA provider and version. Hibernate 6 automatically deduplicates duplicate entities arising from collection fetch joins in entity results; other providers or versions may behave differently. Verify actual results with your current provider.

Collection fetch joins combined with pagination require particular care. The database paginates over joined rows, whereas the application wants to paginate over Customers. This can yield wrong Customer counts per page or force the provider to load huge datasets and paginate in memory. Hibernate can warn or be configured to throw an exception on collection fetch pagination.

A safer approach:

1. Query a page of Customer IDs matching business criteria.
2. Query Customers together with `orders` via fetch join for that page's ID list.
3. Preserve the page ordering from the first ID query when assembling results.

Example second-step query:

~~~jpql
select distinct c
from Customer c
left join fetch c.orders
where c.id in :ids
~~~

If using `Page`, the count query must count unique Customers and omit collection fetching:

~~~java
@Query(
    value = """
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """,
    countQuery = """
        select count(distinct c.id)
        from Customer c
        join c.orders o
        where o.status = :status
        """
)
Page<Customer> findDistinctCustomersByOrderStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

The count query must reflect the unique entity count of the content page. Counting joined rows would inflate total pages beyond actual Customers.

## 17. DISTINCT and Performance

DISTINCT can add query overhead because the database must eliminate duplicate results. Cost depends on intermediate row count, indexes, join types, and execution plans.

Before adding DISTINCT, ask yourself:

- Do I actually need unique entities?
- Is the JOIN joining the right relationship?
- Could EXISTS replace JOIN?
- Could a DTO or scalar query be used instead of loading entire entities?
- Do all those collections really need to be joined?
- Is the count query counting joined rows instead of unique entities?
- Are there indexes supporting the JOIN and WHERE conditions?

DISTINCT is no substitute for indexes and cannot repair a flawed relationship model. It is part of the query's result semantics.

## 18. Comprehensive Repository Example

A repository can expose different query patterns for various scenarios:

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    List<Customer> findDistinctByOrderStatus(
        @Param("status") String status
    );

    @Query("""
        select count(distinct c.id)
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    long countDistinctByOrderStatus(
        @Param("status") String status
    );

    @Query("""
        select c
        from Customer c
        where c.phone is null
        """)
    List<Customer> findWithoutPhone();

    @Query("""
        select c
        from Customer c
        where (:city is null or c.city = :city)
        """)
    List<Customer> searchByOptionalCity(
        @Param("city") String city
    );

    @Query("""
        select c
        from Customer c
        left join c.orders o on o.status = :status
        where o.id is null
        """)
    List<Customer> findWithoutOrderStatus(
        @Param("status") String status
    );

    @Query(
        value = """
            select distinct c
            from Customer c
            join c.orders o
            where o.status = :status
            """,
        countQuery = """
            select count(distinct c.id)
            from Customer c
            join c.orders o
            where o.status = :status
            """
    )
    Page<Customer> pageDistinctByOrderStatus(
        @Param("status") String status,
        Pageable pageable
    );
}
~~~

These methods illustrate distinct purposes:

- `findDistinctByOrderStatus` fetches unique Customers.
- `countDistinctByOrderStatus` counts unique Customers after JOIN.
- `findWithoutPhone` uses `IS NULL`.
- `searchByOptionalCity` skips the filter when `city` is null.
- `findWithoutOrderStatus` uses `LEFT JOIN ON` and checks for a null right side.
- `pageDistinctByOrderStatus` supplies a count query matching the distinct result set.

When a method starts with `find...` and has `@Query`, Spring Data uses the JPQL declared in the annotation. The method name does not alter the explicit query body.

## 19. Testing DISTINCT and NULL Results

Do not merely check that a query runs—verify the exact counts and identities returned.

Test data should include:

- Customer An with two PAID orders and one CANCELLED order.
- Customer Binh with one PAID order.
- Customer Chi with no orders.
- A Customer with a NULL phone.
- A Customer with a NULL city.
- Two distinct Customers sharing the same city or name.

Assertions to verify:

1. JOIN without DISTINCT returns An twice for two PAID orders.
2. SELECT DISTINCT Customer returns An only once.
3. COUNT(DISTINCT c.id) returns the unique Customer count.
4. DISTINCT c.city collapses duplicate cities and handles NULL according to database/provider distinct semantics.
5. IS NULL returns Customers without a phone.
6. `c.phone = :phone` with null phone is not used as a replacement for IS NULL.
7. `LEFT JOIN ... ON` preserves Customers without matching orders.
8. Placing the right-side condition in WHERE drops Customers without orders.
9. Page's count query returns the accurate total number of unique Customers.
10. Collection fetch joins and pagination are tested with the actual provider.

Simple repository test examples:

~~~java
@Test
void distinctQueryReturnsEachCustomerOnce() {
    List<Customer> customers =
        customerRepository.findDistinctByOrderStatus("PAID");

    assertEquals(2, customers.size());
}

@Test
void countDistinctCountsCustomersRatherThanOrders() {
    long count =
        customerRepository.countDistinctByOrderStatus("PAID");

    assertEquals(2L, count);
}
~~~

These test snippets assume test data has been set up as described and the repository is injected in an integration test. In `@DataJpaTest`, flush data before querying to avoid confusion between in-memory persistence context state and the database.

Run tests against the same database engine used in production when queries depend on NULL behavior, collation, data types, pagination, or SQL optimization. H2 is useful for fast tests but does not guarantee identical behavior to PostgreSQL, MySQL, or SQL Server.

## 20. Common Errors and Fixes

**1. A Customer appears multiple times after JOIN**

This is usually caused by one Customer having multiple related records. Use `SELECT DISTINCT` if the goal is unique entities; if only checking existence, consider `EXISTS`.

**2. COUNT returns more than the entity count**

`COUNT(c)` is counting rows after the JOIN. Use `COUNT(DISTINCT c.id)` when counting unique entities.

**3. WHERE field = NULL returns no results**

Use `IS NULL`. Comparing with NULL using `=` or `<>` produces UNKNOWN.

**4. LEFT JOIN still drops entities without relationships**

Check whether a right-side condition was placed in WHERE. To preserve left-side rows, place the matching condition in ON.

**5. DISTINCT on name drops distinct entities**

DISTINCT applies to the selected expression. Selecting `c.name` merges two Customers with the same name into one value. Select entity `c` or ID if entities must stay distinct.

**6. NOT IN gives unexpected results**

Check whether the list contains NULL. NULL can turn the expression into UNKNOWN. Remove NULLs or use `NOT EXISTS`.

**7. Page has incorrect totalElements**

The count query may be counting joined rows. Use `COUNT(DISTINCT c.id)` and keep filter conditions equivalent to the content query.

**8. Collection fetch join with pagination is slow or returns wrong row counts**

Paginating over joined rows differs from paginating over root entities. Use a two-step query or an appropriate projection.

**9. Query stays slow even after adding DISTINCT**

DISTINCT incurs deduplication cost. Inspect intermediate row counts, JOINs, indexes, and execution plans; consider `EXISTS` or DTO projections.

## 21. Process for Choosing How to Write a Query

When querying across relationships, follow these steps:

1. Determine whether the needed result is an entity, scalar, DTO, or count.
2. Determine whether the JOIN relationship can produce multiple rows per root entity.
3. If unique entities are needed, use `SELECT DISTINCT entity`.
4. If unique values are needed, place `DISTINCT` on the exact scalar or projection expression.
5. If counting unique entities, use `COUNT(DISTINCT primaryKey)`.
6. If only checking whether related data exists, consider `EXISTS`.
7. If preserving left-side entities without relationships, use `LEFT JOIN` and place conditions properly in ON/WHERE.
8. For NULLs, use `IS NULL`/`IS NOT NULL` and remember UNKNOWN logic.
9. If a nullable parameter acts as an optional filter, express the skip-filter case explicitly; if distinguishing between finding NULL and skipping the filter, use separate input states.
10. When paginating, verify the count query and avoid collection fetch join pagination.
11. Inspect actual SQL and execution plans with representative data.
12. Write integration tests verifying counts, entity identity, and NULL cases.

## 22. Self-Assessment Checklist

- [ ] I can explain why a one-to-many JOIN can repeat root entities in results.
- [ ] I know how to use `SELECT DISTINCT` to retrieve unique entities.
- [ ] I can distinguish DISTINCT on entities from DISTINCT on scalars.
- [ ] I know how to use `COUNT(DISTINCT c.id)` to count unique entities.
- [ ] I understand that DISTINCT does not fix wrong JOIN conditions.
- [ ] I can distinguish INNER JOIN and LEFT JOIN.
- [ ] I understand that ON and WHERE have different meanings with LEFT JOIN.
- [ ] I can explain how NULL produces UNKNOWN in comparisons.
- [ ] I know how to use `IS NULL` and `IS NOT NULL`.
- [ ] I understand a null parameter is not equivalent to an `IS NULL` condition.
- [ ] I know how `COALESCE`, `NULLIF`, `IN`, and `NOT IN` interact with NULL.
- [ ] I know how to check collections with `IS EMPTY`.
- [ ] I understand multiple collection JOINs can multiply rows.
- [ ] I know how to use `EXISTS` when only existence checking is needed.
- [ ] I know how to verify count queries and pagination when using DISTINCT.
- [ ] I have integration tests for duplicate results, NULLs, and LEFT JOINs.

## 23. Review Questions

**1. Why can joining Customer with orders return Customer An twice?**

Because each matching order creates a joined result row. If An has two matching orders, An appears in two rows.

**2. How does `SELECT DISTINCT c` differ from `SELECT DISTINCT c.name`?**

`SELECT DISTINCT c` removes duplicate entities at the entity result level. `SELECT DISTINCT c.name` collapses duplicate name values even when they belong to different Customers.

**3. When is `COUNT(DISTINCT c.id)` needed?**

When counting Customers after a JOIN that can produce multiple rows for the same Customer.

**4. Why is `c.phone = NULL` incorrect?**

Because comparing with NULL produces UNKNOWN. Use `c.phone IS NULL` to find missing values.

**5. Why can a LEFT JOIN with a condition in WHERE behave like an INNER JOIN?**

Rows without a right-side match receive NULL values; a WHERE condition on a right-side attribute fails to evaluate to TRUE, so those rows are eliminated.

**6. When should `EXISTS` be used instead of `JOIN DISTINCT`?**

When you only need to determine whether at least one matching related record exists and do not need data from that record. `EXISTS` expresses intent and avoids multiplying rows in the outer result.

**7. Why does a paginated query with a JOIN need its own `countQuery`?**

So that total elements reflect unique entities matching the filter rather than joined row counts. Typically `COUNT(DISTINCT primaryKey)` is used.

**8. Should DISTINCT always be used to avoid duplicate results?**

No. DISTINCT adds cost and can collapse scalar values that business logic wants kept separate. First determine the result type and why duplicate rows occur; then choose DISTINCT, EXISTS, or an appropriate JOIN fix.

Once you understand DISTINCT and NULL logic, you can interpret JPQL results after JOINs accurately, count entities reliably, preserve required rows with LEFT JOIN, and avoid subtle data-filtering bugs.
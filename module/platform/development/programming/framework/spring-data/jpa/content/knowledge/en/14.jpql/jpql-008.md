# Subqueries, EXISTS, and Correlated Conditions

JPQL allows placing a subquery inside the condition of an outer query. Subqueries are commonly used to check for the existence of related data, compare against an aggregate value, or filter Entities by a set of IDs produced by another query.

Two key constructs are `EXISTS` and `NOT EXISTS`. They test whether a subquery returns at least one row. When a subquery references an alias from the outer query, it is a **correlated subquery**. This pattern is very useful for questions like: which customers have placed an order, which orders have at least one qualifying line item, or which products have never been ordered.

## 1. What is a Subquery in JPQL?

A subquery is a SELECT statement nested inside an expression of another JPQL query. The outer query determines which Entity or value to return; the subquery supplies data to test or compare against.

Conceptual example:

~~~sql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
)
~~~

The outer query selects `Customer`. The subquery checks whether any `PurchaseOrder` belongs to the current `Customer`.

In standard JPQL, subqueries are permitted in the `WHERE` and `HAVING` clauses. Standard JPQL does not support placing a subquery in `FROM` as a derived table as commonly seen in SQL. Some HQL or provider extensions support broader syntax, but to keep queries portable across JPA providers, stay within standard JPQL rules.

A subquery can return:

- A single scalar value, such as the result of `COUNT` or `MAX`.
- A set of values, such as a list of IDs used with `IN`.
- A set of rows used with `EXISTS` or `NOT EXISTS`, where the SELECT item itself matters less than whether any matching row exists.

## 2. Data Model Used in Examples

Suppose a sales system has `Customer`, `PurchaseOrder`, `OrderItem`, and `Product`:

~~~text
Customer 1 -------- N PurchaseOrder
PurchaseOrder 1 --- N OrderItem
Product 1 --------- N OrderItem
~~~

A `Customer` can have many orders. Each `PurchaseOrder` has many `OrderItem`s. Each `OrderItem` references a `Product`.

Relevant attributes in the Entities:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    private Integer quantity;
}
~~~

These Entity snippets illustrate the mappings; in a real project they require full imports, constructors, getters, and proper JPA configuration. JPQL uses Entity names and Java attributes rather than SQL table/column names. For example, `PurchaseOrder` is the Entity name and `customer` is the relationship attribute, whereas `purchase_orders` and `customer_id` are physical database names.

## 3. EXISTS: Checking Whether at Least One Matching Row Exists

`EXISTS` returns true when the subquery produces at least one row, and false when it produces none.

General syntax:

~~~sql
SELECT ...
FROM Entity e
WHERE EXISTS (
    SELECT ...
    FROM OtherEntity x
    WHERE condition
)
~~~

Example: find customers who have placed at least one order.

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """)
    List<Customer> findCustomersWithOrders();
}
~~~

Reading the query:

1. JPQL iterates over `Customer` via alias `c`.
2. Conceptually, for each `Customer`, the subquery checks whether any `PurchaseOrder` has `customer` equal to `c`.
3. If at least one order exists, `EXISTS` is true and the `Customer` is included.
4. If no order exists, the `Customer` is excluded from results.

In the subquery, `SELECT o.id` simply forms a valid expression. `EXISTS` does not return the ID value to the outer query; it only checks whether any matching row exists. Selecting a simple attribute such as the ID keeps the intent clear.

## 4. NOT EXISTS: Finding Entities Without Related Data

`NOT EXISTS` is the negation of `EXISTS`. It evaluates to true when the subquery returns no rows.

Example: find customers who have never placed an order.

~~~java
@Query("""
    select c
    from Customer c
    where not exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
    )
    """)
List<Customer> findCustomersWithoutOrders();
~~~

This is a form of anti-join: retrieving `Customer`s that have no related `PurchaseOrder` records.

Common use cases:

- Users with no transactions.
- Products never sold.
- Articles with no comments.
- Accounts with no logins.
- Orders without a payment record.

`NOT EXISTS` directly expresses "no related record exists" and avoids several NULL pitfalls of `NOT IN`.

## 5. What is a Correlated Condition?

A correlated subquery references an alias declared in the outer query. Example:

~~~sql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

Alias `c` is declared in the outer query but used inside the subquery. The condition `o.customer = c` links the subquery to the current `Customer`.

Without a reference to an outer alias, the subquery is an uncorrelated subquery. Example:

~~~sql
select o
from PurchaseOrder o
where o.totalAmount = (
    select max(o2.totalAmount)
    from PurchaseOrder o2
)
~~~

The subquery finds the maximum total amount across all `PurchaseOrder`s independently of the outer alias `o`.

The difference can be summarized as:

| Type | Characteristic | Example |
|---|---|---|
| Uncorrelated | Computes a set or value independent of each outer row | `MAX(totalAmount)` across the whole table |
| Correlated | Uses an outer alias to scope data to the row under evaluation | `PurchaseOrder` belonging to `Customer c` |

Logically, a correlated subquery is interpreted per outer row. However, do not assume the database literally runs a separate subquery per row. The optimizer can transform it into a semi-join, anti-join, or another equivalent execution plan.

## 6. EXISTS Across Multi-Level Relationships

You can traverse multiple relationships inside a subquery. For example, find orders containing at least one `OrderItem` with quantity at or above a threshold:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where exists (
            select i.id
            from OrderItem i
            where i.order = o
              and i.quantity >= :minimumQuantity
        )
        """)
    List<PurchaseOrder> findOrdersWithLargeItemQuantity(
            @Param("minimumQuantity") Integer minimumQuantity
    );
}
~~~

The condition `i.order = o` is the correlation: it inspects only `OrderItem`s belonging to the order being evaluated. The quantity condition restricts which line items qualify.

You can also navigate to `Product`:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where exists (
        select i.id
        from OrderItem i
        where i.order = o
          and i.product.name = :productName
    )
    """)
List<PurchaseOrder> findOrdersContainingProduct(
        @Param("productName") String productName
);
~~~

JPQL allows traversing relationship attributes with dot notation. The provider generates the necessary joins to evaluate `product.name`. When queries span multiple relationship levels or complex conditions, inspect the generated SQL and execution plan.

## 7. Correlated Subqueries with COUNT

A subquery can return an aggregate value. For example, find customers with at least a certain number of orders:

~~~java
@Query("""
    select c
    from Customer c
    where (
        select count(o.id)
        from PurchaseOrder o
        where o.customer = c
    ) >= :minimumOrders
    """)
List<Customer> findCustomersWithAtLeastOrders(
        @Param("minimumOrders") Long minimumOrders
);
~~~

The `COUNT` subquery is correlated with `Customer c` via `o.customer = c`. For each `Customer`, the subquery counts that customer's orders and compares against the parameter.

`COUNT` returns `Long` in JPQL. Therefore, `minimumOrders` should be typed as `Long` to match the result type.

You can write an equivalent check using `EXISTS` if you only need to know whether at least one order exists:

~~~java
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

When you need to count and compare against a threshold greater than one, `COUNT` is appropriate. When you only need an existence check, `EXISTS` expresses the goal directly and avoids requiring a full count.

Note: `COUNT` returns 0 when no matching rows exist. Aggregates such as `MAX`, `MIN`, `AVG`, and `SUM` can return NULL when there are no input values; comparisons against NULL will not evaluate to true.

## 8. Subqueries with IN

`IN` checks whether a value belongs to the set of values returned by a subquery.

Example: find `Product`s appearing in at least one `OrderItem` with quantity 10 or more.

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.id in (
            select i.product.id
            from OrderItem i
            where i.quantity >= :minimumQuantity
        )
        """)
    List<Product> findProductsInLargeOrders(
            @Param("minimumQuantity") Integer minimumQuantity
    );
}
~~~

The subquery returns a set of product IDs. The outer query selects `Product`s whose ID is in that set.

`IN` fits when comparing an attribute against a subquery's result set. However, if the business intent is "there exists at least one related record", `EXISTS` often expresses the correlated relationship more clearly.

## 9. Comparing Against an Aggregate Value with a Subquery

Subqueries do not have to be correlated. For example, find orders whose total amount equals the highest amount in the system:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.totalAmount = (
        select max(o2.totalAmount)
        from PurchaseOrder o2
    )
    """)
List<PurchaseOrder> findOrdersWithMaximumAmount();
~~~

The `MAX` subquery returns a single value. The outer query selects all orders whose `totalAmount` matches that value. Return `List` because multiple orders could share the maximum amount.

You can use comparison operators with scalar subqueries:

- `=` for equal to the subquery value.
- `>` or `>=` for greater than or greater than/equal to.
- `<` or `<=` for less than or less than/equal to.
- `<>` for not equal to.

A subquery used in a scalar context must return at most one value. If the subquery returns multiple rows where a single scalar value is expected, the database/provider will raise a query error.

## 10. How Do EXISTS, IN, and JOIN Differ?

The three constructs can express similar requirements, yet their semantics and result shapes differ.

| Construct | Purpose | Characteristic |
|---|---|---|
| `EXISTS` | Check whether related records exist | Does not need to return data from the related side |
| `IN` | Check whether a value belongs to a result set | Fits sets of IDs/values from a subquery |
| `JOIN` | Combine data across Entities | Can return attributes from both sides; can produce duplicate rows |

Example finding Customers with orders using JOIN:

~~~sql
select c
from Customer c
join c.orders o
~~~

If a Customer has multiple orders, the join can produce multiple rows for the same Customer. When only unique Customers with at least one order are needed, `DISTINCT` may be required:

~~~sql
select distinct c
from Customer c
join c.orders o
~~~

Meanwhile:

~~~sql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

`EXISTS` expresses the existence condition directly without duplicating `Customer` rows in the outer result when multiple orders match.

Choose `JOIN` when you need related data or need to combine multiple attributes. Choose `EXISTS` when you only need an existence check. There is no universal rule that `EXISTS` is always faster than `JOIN`; the database optimizer and indexes determine the final execution plan.

## 11. Why is NOT EXISTS Usually Safer Than NOT IN?

`NOT IN` can produce surprising results if the subquery set contains NULL. Under SQL's three-valued logic, comparing against NULL produces UNKNOWN; consequently, `NOT IN` may fail to evaluate to true as intended.

Illustrative SQL example:

~~~sql
SELECT c.*
FROM customers c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM purchase_orders o
);
~~~

If `customer_id` in the subquery includes NULL, the result of `NOT IN` can be affected.

With `NOT EXISTS`:

~~~sql
SELECT c.*
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM purchase_orders o
    WHERE o.customer_id = c.id
);
~~~

The condition is evaluated per `Customer` and checks whether any matching row exists. NULLs in non-matching rows do not turn the entire check into UNKNOWN the way `NOT IN` does.

In JPQL, when looking for Entities without related records, `NOT EXISTS` is usually the clearer and safer option. If you still use `NOT IN`, ensure the subquery cannot return NULL or filter out NULLs explicitly.

## 12. Putting Subqueries in Spring Data JPA @Query

Subqueries are commonly written directly in `@Query` on a Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
              and o.status = :status
        )
        """)
    List<Customer> findCustomersWithOrderStatus(
            @Param("status") OrderStatus status
    );

    @Query("""
        select c
        from Customer c
        where not exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """)
    List<Customer> findCustomersWithoutOrders();
}
~~~

Spring Data binds parameters via `@Param`. Use parameters instead of concatenating input strings to prevent syntax errors and injection risks.

In JPQL, Entity names and Java attributes must be accurate. If the Entity has a `customer` association, write `o.customer`; write `o.customerId` only if a separate `customerId` attribute exists. Do not use SQL table or column names in JPQL unless writing a native query.

## 13. Paginating Results with Subqueries

Subqueries can be combined with `Pageable`:

~~~java
@Query(
    value = """
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """,
    countQuery = """
        select count(c.id)
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """
)
Page<Customer> findCustomersWithOrders(Pageable pageable);
~~~

`countQuery` counts matching `Customer`s so Spring Data can compute the total page count. Conditions in `countQuery` must match the data query. For complex queries, declare `countQuery` explicitly and test both page contents and total element counts.

The subquery inside `countQuery` is still JPQL, so it follows the same rules for Entities, attributes, and subquery placement.

## 14. Performance and Indexes for Correlated Subqueries

Correlated subqueries frequently reference foreign keys. In our example model, important columns include:

- `purchase_orders.customer_id` to look up orders by Customer.
- `order_items.order_id` to look up line items by PurchaseOrder.
- `order_items.product_id` to look up line items by Product.
- Filtering columns such as `status` or `quantity` depending on conditions and workload.

Indexes on foreign keys can help the database locate related records faster. However, index selection should be based on actual queries, data volume, selectivity, and write overhead.

Basic index examples:

~~~sql
CREATE INDEX idx_purchase_orders_customer
ON purchase_orders (customer_id);

CREATE INDEX idx_order_items_order
ON order_items (order_id);
~~~

If queries frequently filter by `customer_id` and `status` together, consider a composite index ordered for the workload:

~~~sql
CREATE INDEX idx_purchase_orders_customer_status
ON purchase_orders (customer_id, status);
~~~

Do not create indexes on every column mechanically. Indexes consume storage and add overhead to `INSERT`/`UPDATE`/`DELETE`. Use `EXPLAIN` or `EXPLAIN ANALYZE` for your database to inspect whether the optimizer picks an index, semi-join, anti-join, or scan.

A correlated subquery in JPQL is normally sent as a single SQL statement. It is not the same as an application-level N+1 query problem. N+1 typically happens when code loads a list of Entities and then accesses lazy relationships one by one, issuing separate queries. A subquery is processed by the database within that single SQL statement's execution plan, even if the internal plan involves multiple steps.

## 15. Limitations and Caveats of JPQL Subqueries

- Standard JPQL allows subqueries in `WHERE` and `HAVING`; do not use `FROM (subquery)` as in standard SQL.
- Scalar subqueries must return a value compatible with the comparison expression.
- `EXISTS` checks existence only; the subquery's SELECT list is not exposed to the outer result.
- Correlated subqueries must reference a valid alias from the outer query.
- Do not use SQL table/column names instead of Entity/Java attribute names in JPQL.
- Watch out for NULLs when using `NOT IN`.
- Aggregates like `MAX`, `MIN`, `AVG`, and `SUM` can return NULL when there is no data; `COUNT` returns 0.
- Do not assume `EXISTS` is always faster than `JOIN`; benchmark on an actual database.
- If complex queries exceed standard JPQL capabilities, consider Criteria API, native SQL, or specialized queries, noting the level of database coupling.

## 16. Testing Subqueries

For repositories using subqueries, test both cases with and without related records.

Example tests for `EXISTS` and `NOT EXISTS`:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Test
    void findsCustomerThatHasAnOrder() {
        Customer customer =
                customerRepository.save(new Customer("An"));

        orderRepository.save(new PurchaseOrder(customer));

        List<Customer> result =
                customerRepository.findCustomersWithOrders();

        assertTrue(result.stream()
                .anyMatch(c -> c.getId().equals(customer.getId())));
    }

    @Test
    void findsCustomerWithoutOrders() {
        Customer customer =
                customerRepository.save(new Customer("Binh"));

        List<Customer> result =
                customerRepository.findCustomersWithoutOrders();

        assertTrue(result.stream()
                .anyMatch(c -> c.getId().equals(customer.getId())));
    }
}
~~~

This is an illustrative structure; `PurchaseOrder` constructors and mappings must match your actual Entities. In tests, call `flush` when you need to ensure SQL and constraints have executed before querying.

Consider adding test cases for:

1. A Customer with multiple orders appearing only once in `EXISTS` results.
2. A Customer with no orders appearing in `NOT EXISTS`.
3. An order with multiple `OrderItem`s where only one qualifying item makes `EXISTS` true.
4. No matching line items making `EXISTS` false.
5. Threshold parameters equal to 0, boundary values, and values above all data.
6. NULL values in columns involved in the subquery, especially with `NOT IN`.
7. Pagination returning accurate totals and no duplicate Entities.

If production uses PostgreSQL or MySQL, run integration tests on the same database engine or a compatible version. H2 can differ in SQL dialect, optimizer behavior, collation, and edge-case NULL handling.

## 17. Process for Choosing a Query Structure

When writing a query with conditions over related data, clarify the business question first:

- Need data from both Entities? Use `JOIN`.
- Only need to know if at least one related record exists? Use `EXISTS`.
- Need to know that no related record exists at all? Use `NOT EXISTS`.
- Need to check whether a value belongs to a result set? Use `IN`.
- Need to compare against an aggregate value? Use a scalar subquery such as `COUNT`, `MAX`, or `MIN`.
- Need to count related records per outer Entity? Use a correlated `COUNT` subquery or `GROUP BY`/`HAVING` where appropriate.

Then verify aliases, data types, NULL semantics, result counts, generated SQL, and execution plans. Optimize with indexes or query restructuring only after identifying bottlenecks with realistic data.

## 18. Conclusion

Subqueries in JPQL help filter Entities by another value or result set. `EXISTS` and `NOT EXISTS` are well suited to checking the presence or absence of related data; correlated subqueries reference outer query aliases to constrain conditions per Entity under evaluation. `IN` works well for value sets, while aggregate subqueries support `COUNT`, `MAX`, or `MIN` comparisons. Choose `JOIN` when you need data from multiple Entities, use `NOT EXISTS` to avoid `NOT IN` NULL pitfalls, and inspect SQL along with execution plans on the target database to ensure queries are accurate and efficient.
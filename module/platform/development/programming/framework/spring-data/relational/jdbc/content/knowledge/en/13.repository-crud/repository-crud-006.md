# existsById and count in Data Checks

In **Spring Data Relational JDBC (Spring Data JDBC)**, repositories provide data-checking operations without loading full entities into the application. Two fundamental operations are **`existsById(id)`** to determine whether an aggregate root exists by ID, and **`count()`** to count the aggregate roots managed by the repository.

These methods are useful when checking references, displaying record counts, verifying state before a use case, or building reports. However, you need to understand counting scope, query cost, and the limits of “check before writing.”

## 1. Two different questions: does it exist, and how many?

Suppose a sales system has two tables:

- `customers`: stores customers.
- `sales_orders`: stores orders, each having `customer_id` referencing a Customer.

The Order repository can answer:

| Need | Method | Result |
|---|---|---|
| Does order ID 501 exist? | `existsById(501L)` | `true` or `false` |
| How many orders are in the system? | `count()` | An integer of type `long` |
| Does customer ID 10 have any orders? | `existsByCustomerId(10L)` | `true` or `false` |
| How many orders does customer ID 10 have? | `countByCustomerId(10L)` | An integer of type `long` |
| How many orders are in DRAFT status? | `countByStatus("DRAFT")` | An integer of type `long` |

**exists** answers a yes/no logical question; **count** answers a quantity question. If you only need to know whether matching data exists, do not load the entire list and call `isEmpty()`.

~~~mermaid
flowchart TB
    App["Application Service"]
    App --> Exists["existsById(id)<br/>Record exists?"]
    App --> Count["count()<br/>How many records?"]
    Exists --> Bool["boolean"]
    Count --> Number["long"]
    Exists --> DB[("Database")]
    Count --> DB
~~~

## 2. existsById in CrudRepository

`CrudRepository<T, ID>` provides the built-in method:

~~~java
boolean existsById(ID id);
~~~

Repository example:

~~~java
package com.example.sales.order;

import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~

Usage:

~~~java
boolean exists = orderRepository.existsById(501L);

if (exists) {
    System.out.println("Order exists");
} else {
    System.out.println("Order does not exist");
}
~~~

Behavior:

- Returns `true` when the repository finds an aggregate root with the matching ID.
- Returns `false` when no root has that ID.
- The passed ID must be non-null; passing null is not a way to check for an “unassigned ID,” but invalid input under the repository contract.
- The method only returns existence status; it does not return the entity or expose any properties of `Order`.

### How does existsById differ from findById?

~~~java
boolean exists = orderRepository.existsById(orderId);

Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new IllegalArgumentException("Order not found"));
~~~

| Criterion | `existsById` | `findById` |
|---|---|---|
| Purpose | Check if a root exists by ID | Fetch the root by ID |
| Return type | `boolean` | `Optional<Order>` |
| Data received by app | Yes/no | Entity if found |
| When to use | Only need to know existence | Need to read or modify the entity |
| Need to construct aggregate object? | Not needed for caller | Yes, per aggregate mapping |

If the subsequent use case definitely needs the `Order`, calling `findById` once is usually better than calling `existsById` followed by `findById`, because two operations incur two database round-trips. Example:

~~~java
Order order = orderRepository.findById(orderId)
    .orElseThrow(() -> new IllegalArgumentException(
        "Order not found: " + orderId
    ));

order.confirm();
orderRepository.save(order);
~~~

There is no need to check `existsById` before loading the `Order` and continuing. `findById` directly expresses both outcomes.

### How does the framework execute the query?

`existsById` can be implemented via an existence query or equivalent SQL depending on the version, dialect, and database engine. Applications should rely on the **boolean contract** rather than depending on a specific SQL statement.

Conceptually, the SQL may be equivalent to:

~~~sql
SELECT 1
FROM sales_orders
WHERE id = :id;
~~~

Some implementations may use an `EXISTS` expression or another mechanism. You do not need to write the SQL above to use `CrudRepository.existsById`; Spring Data JDBC generates the appropriate operation for the repository.

## 3. count in CrudRepository

`CrudRepository<T, ID>` also provides:

~~~java
long count();
~~~

Example:

~~~java
long totalOrders = orderRepository.count();
System.out.println("Total orders: " + totalOrders);
~~~

The method returns `long` (64-bit), since row counts can exceed the `int` range. `count()` counts the number of root entities represented by the repository; in the `OrderRepository` example, that is **the number of orders**, not the total number of order lines across all orders.

If an `Order` aggregate consists of one row in `sales_orders` and multiple rows in `order_items`, then:

- `orderRepository.count()` counts `Order` roots.
- It does not add rows in `order_items`.
- Nor does it count `Customer` rows.

This is a key distinction between aggregates and database tables: a repository operates by root, whereas the database may store an aggregate across multiple tables.

### Conditional counting with query methods

Besides `count()`, Spring Data JDBC supports query methods derived from method names. Example:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, Long> {

    boolean existsByCustomerId(Long customerId);

    long countByCustomerId(Long customerId);

    long countByStatus(String status);

    long countByCustomerIdAndStatus(
        Long customerId,
        String status
    );

    List<Order> findAllByCustomerIdOrderByIdAsc(Long customerId);
}
~~~

These methods answer:

- `existsByCustomerId(10L)`: does the customer have at least one Order?
- `countByCustomerId(10L)`: how many Orders does the customer have?
- `countByStatus("DRAFT")`: how many Orders are currently drafts?
- `countByCustomerIdAndStatus(10L, "DRAFT")`: how many draft Orders does customer 10 have?

Property names in query methods must match **entity properties**. For example, if the entity has `customerId`, the method name uses `CustomerId`; it does not necessarily use the SQL column name `customer_id`. Spring Data JDBC maps properties to columns via the naming strategy or mapping annotations.

Do not load a list just to count:

~~~java
// Suboptimal if only the count is needed:
long count = orderRepository
    .findAllByCustomerIdOrderByIdAsc(customerId)
    .size();

// Use a count query instead:
long count = orderRepository.countByCustomerId(customerId);
~~~

The first approach can read and instantiate many unnecessary `Order` objects, increasing memory and processing time. The second lets the database compute the count and return a single value.

## 4. Corresponding SQL and data scope

With table `sales_orders`:

~~~sql
-- Total number of orders.
SELECT COUNT(*)
FROM sales_orders;

-- Order count for a specific customer.
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10;

-- Number of orders in DRAFT status.
SELECT COUNT(*)
FROM sales_orders
WHERE status = 'DRAFT';

-- Number of DRAFT orders for a specific customer.
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

These SQL statements illustrate the meaning of the queries. When calling the repository, Spring Data JDBC executes the query and binds parameters; never concatenate user-supplied IDs or statuses directly into SQL strings.

### Counting OrderItem is a different question

If you want to count order items, the query must target the `order_items` table:

~~~sql
SELECT COUNT(*)
FROM order_items;

-- Number of items belonging to one Order.
SELECT COUNT(*)
FROM order_items
WHERE order_id = 501;
~~~

`OrderRepository.count()` does not return those two results. You can use a dedicated reporting repository/query or `@Query` with an appropriate scalar/projection return type to run counts against child tables.

Example of a query method with explicit SQL:

~~~java
@Query("""
    SELECT COUNT(*)
    FROM order_items
    WHERE order_id = :orderId
    """)
long countItemsByOrderId(long orderId);
~~~

Place the method in a repository authorized to perform this read query and ensure column names match the schema. Counting items for a read query does not make `OrderItem` an aggregate root or require a separate write repository.

## 5. existsBy... and countBy... for business conditions

Query methods can check multiple conditions:

~~~java
boolean existsByCustomerIdAndStatus(
    Long customerId,
    String status
);

long countByCustomerIdAndStatus(
    Long customerId,
    String status
);
~~~

Example checking whether a customer has a DRAFT order:

~~~java
boolean hasDraft = orderRepository
    .existsByCustomerIdAndStatus(customerId, "DRAFT");
~~~

Example checking the number of confirmed orders:

~~~java
long confirmedOrders = orderRepository
    .countByCustomerIdAndStatus(customerId, "CONFIRMED");
~~~

These queries reflect current data. If business rules need to distinguish a non-existent customer from an existing customer with zero orders, check `Customer` separately or use a query returning both customer status and the count result.

Example:

~~~java
if (!customerRepository.existsById(customerId)) {
    throw new IllegalArgumentException("Customer not found");
}

long orderCount = orderRepository.countByCustomerId(customerId);
~~~

Note that this snippet makes two database round-trips. If the use case needs more `Customer` details, load `Customer` with `findById` and use the returned entity instead of calling exists and then loading again.

## 6. Performance: existence and count do not have the same cost

### exists usually only needs to know at least one result matches

Logically, once one matching row is found, the existence question is answered. The database engine can leverage primary keys or indexes for a fast lookup. For `existsById`, the ID column is typically the primary key and therefore indexed.

Do not interpret this as meaning every existence query is constant-time or that the database is guaranteed to stop after the first row. Execution plans also depend on indexes, statistics, predicates, data distribution, and the database engine. Inspect with explain/analyze tools when real performance issues arise.

### count must determine how many rows match

`COUNT(*)` must determine the total number of rows matching the conditions. On large tables, exact counting may need to scan many data entries or index entries. Therefore:

- Use `countBy...` instead of loading a full list and calling `size()`.
- Create appropriate indexes for columns frequently used in filter predicates.
- Avoid calling count repeatedly in a loop if queries can be consolidated.
- For dashboards requiring live numbers on huge tables, evaluate queries, caching, summary tables, or suitable counter-maintenance mechanisms.

### Indexes for common queries

If the application frequently filters orders by Customer and status, consider:

~~~sql
CREATE INDEX idx_sales_orders_customer_status
    ON sales_orders(customer_id, status);
~~~

This composite index can assist queries filtering by `customer_id` and `status`. It does not automatically make every count fast; column order, selectivity, data volume, and actual workload must be evaluated. Do not create indexes for every predicate combination because indexes increase storage and write overhead.

Check execution plans with:

~~~sql
-- PostgreSQL
EXPLAIN ANALYZE
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

~~~sql
-- MySQL
EXPLAIN
SELECT COUNT(*)
FROM sales_orders
WHERE customer_id = 10
  AND status = 'DRAFT';
~~~

Choose the command matching your database engine. PostgreSQL's `EXPLAIN ANALYZE` executes the query to measure it; exercise caution if a query has side effects. The examples here are read-only SELECTs.

## 7. existsById does not replace database constraints

A common mistake is checking existence first and assuming the record will still exist when writing:

~~~java
if (customerRepository.existsById(customerId)) {
    orderRepository.save(new Order(customerId));
}
~~~

This scenario can occur:

~~~text
Request A                         Request B
existsById(customerId) -> true
                                  DELETE Customer
                                  COMMIT
INSERT Order(customer_id)
-> FK violation
~~~

The gap between checking and writing creates a **race condition** (TOCTOU: time of check to time of use). Therefore:

- Existence checks in services help return clear business messages.
- Foreign keys let the database guarantee the reference actually exists at insert/update time.
- Transactions, locks, or appropriate coordination mechanisms may be needed if business rules require tighter synchronization.
- Always handle integrity errors on write operations, because state can change concurrently.

**Do not drop foreign keys just because you have existsById.** The two layers serve different purposes: one supports application logic, the other protects data integrity.

## 8. count is not a lock for enforcing limits under concurrency

Suppose each customer can have at most 5 DRAFT orders. Code:

~~~java
long draftCount = orderRepository
    .countByCustomerIdAndStatus(customerId, "DRAFT");

if (draftCount < 5) {
    orderRepository.save(new Order(customerId));
}
~~~

This can fail when two requests run concurrently:

~~~text
Initial state: 4 DRAFT orders

Request A: count = 4       Request B: count = 4
Request A: 4 < 5 -> pass  Request B: 4 < 5 -> pass
Request A: insert          Request B: insert

Result: 6 DRAFT orders
~~~

`count` reflects state at query time; it does not lock future counts. If the limit is a hard invariant, you need an appropriate concurrency design, such as:

- Locking the `Customer` row within a transaction before counting and creating the order, with carefully chosen isolation/locking.
- Storing a counter/slot in a row updated atomically with a conditional statement.
- Using an appropriate isolation level and retrying on serialization conflicts.
- Designing a data structure capable of expressing the constraint via unique keys/constraints if the problem permits.

Simply adding `@Transactional` without considering isolation or locking does not automatically enforce the “at most 5” rule under all concurrent execution schedules.

## 9. existsById and authorization checks

Knowing an Order exists does not mean the current user is permitted to view or modify it:

~~~java
if (orderRepository.existsById(orderId)) {
    // Not sufficient to conclude the user is allowed to access it.
}
~~~

Authorization requires checking the relationship between the current user and the resource's owner, such as which `Customer` the `Order` belongs to and whether that `Customer` is linked to the current user. You can query by both resource ID and owner scope:

~~~java
boolean belongsToCustomer = orderRepository
    .existsByIdAndCustomerId(orderId, currentCustomerId);
~~~

This method both checks existence and restricts by customer ID. Still, if the Order needs updating afterward, load the entity via an appropriately scoped query and enforce authorization within the use case; avoid treating a stale boolean as permanent permission.

Additionally, if the system uses **soft delete** (marking deleted while keeping rows in the table), the default behavior of `existsById` and `count()` depends on how the repository is configured. Basic CRUD methods do not automatically understand a `deleted_at` or `active` column unless you define those predicates. When you only want active records counted, use conditional query methods or explicit custom queries.

## 10. Organizing services: choosing the right operation for each use case

### Only need to confirm whether an ID exists

~~~java
public boolean orderExists(Long orderId) {
    return orderRepository.existsById(orderId);
}
~~~

### Need to load for processing

~~~java
public Order getOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException(
            "Order not found: " + orderId
        ));
}
~~~

### Need to count all

~~~java
public long totalOrders() {
    return orderRepository.count();
}
~~~

### Need to count by Customer

~~~java
public long orderCountFor(Long customerId) {
    return orderRepository.countByCustomerId(customerId);
}
~~~

Service methods should be named after their business meaning, such as `hasOrders` or `countDraftOrders`, when they form part of the application API. Do not let controllers assemble multiple queries and decide invariants themselves.

## 11. Practice exercise

Suppose sample data:

~~~sql
INSERT INTO customers (id, customer_code, display_name) VALUES
    (10, 'CUS-010', 'Nguyen An'),
    (20, 'CUS-020', 'Tran Binh');

INSERT INTO sales_orders (id, customer_id, status) VALUES
    (501, 10, 'CONFIRMED'),
    (502, 10, 'DRAFT'),
    (503, 20, 'CONFIRMED');
~~~

In environments with identity/auto-increment columns, insert explicit IDs only if schema and configuration allow; the example above illustrates values for reasoning about results. You can omit the ID column and let the database generate it during normal practice.

Answer:

1. What does `existsById(501L)` return? What does `existsById(999L)` return?
2. What does `OrderRepository`'s `count()` return?
3. What do `existsByCustomerId(10L)` and `countByCustomerId(10L)` return?
4. What does `countByStatus("DRAFT")` return?
5. What does `countByCustomerIdAndStatus(10L, "DRAFT")` return?
6. Why should you not call `findAllByCustomerId(10L).size()` just to count?
7. If you need to count total items across all Orders, why is `OrderRepository.count()` unsuitable?
8. Why is `existsById(customerId)` insufficient to guarantee a valid FK when inserting an Order?
9. If each Customer is limited to at most 5 DRAFT orders, why can counting then inserting exceed the limit under two concurrent requests?
10. If soft delete is used, how must count/exists queries change to exclude deleted rows?

Expected results:

| Expression | Result |
|---|---:|
| `existsById(501L)` | `true` |
| `existsById(999L)` | `false` |
| `count()` | `3` |
| `existsByCustomerId(10L)` | `true` |
| `countByCustomerId(10L)` | `2` |
| `countByStatus("DRAFT")` | `1` |
| `countByCustomerIdAndStatus(10L, "DRAFT")` | `1` |

## 12. Key takeaways

`existsById` is the right choice when you only need to know whether an aggregate root exists by ID; `findById` is the right choice when you need the entity; `count` counts the repository's roots; `countBy...` and `existsBy...` support checks by properties and conditions.

Do not confuse aggregate count with child-table row count, do not load a full list just to count, and do not treat exists/count results as locks guaranteeing state won't change after the query. **Database constraints protect data at write time; repository queries help the application make decisions based on observed state.** When data grows large, evaluate indexes and execution plans rather than assuming counting is always cheap.

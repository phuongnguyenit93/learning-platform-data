# Pessimistic locking with @Lock and supported LockModes

When multiple transactions read and then update a data row concurrently, simply reading the current value and writing back can lead to lost updates or business rule violations. **Pessimistic locking** asks the database to lock the queried rows so other transactions cannot perform conflicting operations while the lock remains active.

In Spring Data JDBC, you can enable locking on a repository's derived query method using the `@Lock` annotation. The annotation takes a `LockMode` value to select the lock type. Spring Data Relational currently supports exactly two modes:

- `PESSIMISTIC_READ`: requests a pessimistic read lock, typically corresponding to a shared lock, to prevent other transactions from modifying the rows being read.
- `PESSIMISTIC_WRITE`: requests a pessimistic write lock, typically corresponding to a stronger lock to protect read-then-update operations.

The ability to distinguish between the two modes depends on the database. Some databases have no separate representation for a shared read lock, so both modes may translate to a pessimistic write lock.

This lesson focuses on declaring `@Lock` on derived query methods, choosing the mode for your purpose, holding locks within a transaction, and understanding limitations when using database dialects or hand-written SQL queries.

## 1. Why is pessimistic locking needed?

Suppose a warehouse has a product with an available quantity of 5. Two order requests arrive almost simultaneously, each wanting 4 units.

If both transactions read quantity 5 before either writes, both can conclude there is enough stock. Both then decrement inventory, resulting in overselling beyond actual stock.

One execution schedule might look like this:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Read available = 5
                              Read available = 5
Check 5 >= 4
                              Check 5 >= 4
Write available = 1
                              Write available = 1
COMMIT                        COMMIT
~~~

Both requests are accepted even though only 5 units exist. The final result does not reflect the total quantity ordered.

Pessimistic locking changes the order. Transaction A acquires a write lock on the inventory row before reading. Transaction B must wait until transaction A finishes before acquiring a compatible lock. When B then reads, it sees the new quantity 1 and rejects the request for 4 units.

~~~text
Transaction A                 Transaction B
-------------                 -------------
BEGIN
SELECT ... FOR UPDATE
Read available = 5
                              BEGIN
                              SELECT ... FOR UPDATE
                              Wait for A's lock
Check 5 >= 4
Write available = 1
COMMIT
                              Acquire lock
                              Read available = 1
                              Check 1 >= 4
                              Reject request
                              ROLLBACK
~~~

This is a suitable scenario for pessimistic locking: conflicts are likely and the application needs to serialize operations on the same data.

## 2. Which packages contain @Lock and LockMode?

Spring Data JDBC provides the `@Lock` annotation in package `org.springframework.data.relational.repository`. The `LockMode` enum is in package `org.springframework.data.relational.core.sql`.

~~~java
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;
~~~

Do not confuse this annotation with JPA's `jakarta.persistence.Lock` or enum `jakarta.persistence.LockModeType`. Spring Data JDBC has its own locking API and only exposes the two values `PESSIMISTIC_READ` and `PESSIMISTIC_WRITE`.

The annotation is placed on a repository **method**:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySku(String sku);
~~~

Spring Data uses the declared mode to append the appropriate lock clause to the SELECT statement generated for the derived query method.

## 3. The two supported LockModes

<text color="secondary" size="sm">Enum: org.springframework.data.relational.core.sql.LockMode</text>

| LockMode | Meaning | Suitable use case |
| --- | --- | --- |
| `PESSIMISTIC_READ` | Requests a shared read lock to prevent other transactions from modifying rows being read | Reading data that must stay stable while making a decision |
| `PESSIMISTIC_WRITE` | Requests a write lock to prevent conflicting write operations | Reading, checking conditions, and updating the same row |

### 3.1. PESSIMISTIC_READ

A pessimistic read lock is typically implemented by the database as a shared lock. Multiple transactions can hold compatible read locks on a row simultaneously, while a transaction wanting to modify that row must wait.

For example, a process reads limit information and needs to ensure no other transaction modifies the limit while it makes a decision:

~~~java
@Lock(LockMode.PESSIMISTIC_READ)
Optional<AccountLimit> findByAccountNumber(String accountNumber);
~~~

This mode is suitable when the primary operation is reading and concurrent modifications must be prevented for a short window.

Do not automatically choose PESSIMISTIC_READ for every read-only query. If no business decision needs protection from concurrent changes, a plain SELECT is usually enough. Locking reduces concurrency and can make other transactions wait.

### 3.2. PESSIMISTIC_WRITE

A pessimistic write lock asks the database to acquire a stronger lock on the queried rows. Other transactions attempting to modify the same rows or acquire conflicting locks must wait or fail according to the database's timeout/lock policy.

Example:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySku(String sku);
~~~

This is the appropriate mode for reading stock, checking remaining quantity, and decrementing inventory. The lock is acquired when the SELECT executes, before the application reads and processes the returned value.

A write lock does not mean no other transaction can read the row at all. On databases using MVCC, plain read queries may still read an older snapshot. What gets blocked are conflicting operations under the database's locking semantics and isolation level.

### 3.3. Databases may treat both modes identically

Spring Data JDBC cannot guarantee that every database offers two distinct lock behaviors. Spring's documentation explicitly states that some databases do not distinguish between PESSIMISTIC_READ and PESSIMISTIC_WRITE; in such cases both may be equivalent to PESSIMISTIC_WRITE.

Therefore:

- Choose the mode according to business intent.
- Inspect how the database dialect translates the mode into SQL.
- Test against the exact database engine and isolation level of your deployment environment.
- Do not assume PESSIMISTIC_READ always permits multiple concurrent readers to lock the row on every database.

### 3.4. Modes absent in Spring Data JDBC

The `org.springframework.data.relational.core.sql.LockMode` enum currently has only two constants. The following names do not belong to this enum:

- `OPTIMISTIC`
- `OPTIMISTIC_FORCE_INCREMENT`
- `PESSIMISTIC_FORCE_INCREMENT`
- `PESSIMISTIC_READ` with custom timeout
- `PESSIMISTIC_WRITE` with NOWAIT or SKIP LOCKED options

This differs from some JPA or Hibernate APIs. You cannot pass those modes to Spring Data JDBC's `@Lock`. Optimistic locking in Spring Data JDBC is implemented separately via the `@Version` annotation on the aggregate root.

## 4. Example model: stock by SKU and warehouse

We use a `StockItem` entity as an example. Each combination of SKU and warehouse has at most one inventory row. These two fields carry a unique constraint so querying by SKU and warehouse returns at most one row.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("stock_items")
public class StockItem {

    @Id
    private Long id;

    private String sku;
    private String warehouseCode;
    private int available;

    protected StockItem() {
    }

    public StockItem(
            String sku,
            String warehouseCode,
            int available) {
        this.sku = sku;
        this.warehouseCode = warehouseCode;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getWarehouseCode() {
        return warehouseCode;
    }

    public int getAvailable() {
        return available;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (available < quantity) {
            throw new InsufficientStockException(sku);
        }

        available -= quantity;
    }
}
~~~

Illustrative schema:

~~~sql
CREATE TABLE stock_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    warehouse_code VARCHAR(40) NOT NULL,
    available INTEGER NOT NULL CHECK (available >= 0),
    CONSTRAINT uk_stock_sku_warehouse
        UNIQUE (sku, warehouse_code)
);
~~~

The unique constraint is critical. Pessimistic locking protects existing rows returned by the query; it does not enforce uniqueness for SKU/warehouse pairs on its own.

## 5. Declaring @Lock on a repository method

The repository can expose locking methods tailored to their purpose:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.relational.repository.Lock;
import org.springframework.data.relational.core.sql.LockMode;

public interface StockItemRepository
        extends CrudRepository<StockItem, Long> {

    @Lock(LockMode.PESSIMISTIC_READ)
    List<StockItem> findByWarehouseCode(String warehouseCode);

    @Lock(LockMode.PESSIMISTIC_WRITE)
    Optional<StockItem> findBySkuAndWarehouseCode(
        String sku,
        String warehouseCode
    );
}
~~~

Both methods are derived query methods:

- `findByWarehouseCode` is parsed into a filter on property `warehouseCode`.
- `findBySkuAndWarehouseCode` is parsed into a combined condition on `sku` and `warehouseCode`.

The `@Lock` annotation supplies the lock mode for the corresponding SELECT statement. The second method uses `PESSIMISTIC_WRITE` because it serves the stock reservation update flow.

### Choosing the return type

The return type should reflect how many rows the condition can match:

- `Optional<StockItem>` fits when a unique constraint guarantees at most one row.
- `List<StockItem>` fits when a warehouse holds multiple items.
- Do not use `Optional` for queries that can return multiple rows unless the database enforces uniqueness with a constraint.

If a query returns multiple rows, locks apply to the rows returned by SELECT according to the SQL and database semantics. Consider how many rows may end up locked.

## 6. Generated SQL depends on the dialect

`@Lock` does not require developers to concatenate SQL strings manually. Spring Data JDBC uses the dialect to generate the lock clause appropriate for the database.

Conceptual example for a write lock:

~~~sql
SELECT *
FROM stock_items
WHERE sku = ?
  AND warehouse_code = ?
FOR UPDATE;
~~~

Example in the Spring documentation for `PESSIMISTIC_READ` with the MySQL Dialect:

~~~sql
SELECT *
FROM user_table
WHERE lastname = ?
LOCK IN SHARE MODE;
~~~

Actual syntax depends on the database and version. Some databases use `FOR SHARE` for shared locks; others use different syntax or escalate read lock requests to write locks. Do not copy a MySQL lock clause into PostgreSQL, SQL Server, or another database without checking first.

Spring Data Relational provides `Dialect` and `LockClause` abstractions to handle syntax differences. Applications normally just declare `@Lock` and let the dialect generate the SQL.

## 7. Holding the lock inside a transaction

This is the most important part of implementing pessimistic locking.

The database holds row locks until the transaction ends with COMMIT or ROLLBACK. `@Lock` only requests a lock when executing SELECT; it does not automatically create a long transaction wrapping the entire business flow.

If the query runs in auto-commit mode, the transaction can end immediately after the SELECT statement. In that case, the lock is released before the service even checks the quantity and updates the row.

Place the transaction at the service boundary:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockService {

    private final StockItemRepository stockItems;

    public StockService(StockItemRepository stockItems) {
        this.stockItems = stockItems;
    }

    @Transactional
    public void reserve(
            String sku,
            String warehouseCode,
            int quantity) {

        StockItem item = stockItems
            .findBySkuAndWarehouseCode(sku, warehouseCode)
            .orElseThrow(() ->
                new StockItemNotFoundException(sku)
            );

        item.reserve(quantity);

        stockItems.save(item);
    }
}
~~~

Sequence within a service call:

1. Spring opens a transaction.
2. The repository runs the SELECT with PESSIMISTIC_WRITE.
3. The database grants a lock on the matching row.
4. The service checks the quantity and mutates the object.
5. The repository saves the change.
6. The transaction commits and the database releases the lock.

If `item.reserve` throws an exception or saving fails, the transaction can roll back per Spring's rollback rules. For unchecked exceptions such as `InsufficientStockException` extending RuntimeException, the transaction rolls back by default.

### Do not set readOnly on an update flow

A reserve flow that both reads and writes should use a regular writable transaction:

~~~java
@Transactional
public void reserve(...) {
    // lock, validate, update
}
~~~

`@Transactional(readOnly = true)` is inappropriate for flows that call `save`. The readOnly attribute is primarily a hint passed down to the driver/transaction manager; it is not a substitute for locks and does not guarantee every database blocks writes.

### Query methods also need transactions

Custom query methods declared on a repository do not automatically share the same transaction configuration as inherited CRUD methods. Spring Data JDBC documentation recommends making query methods transactional, because materializing an aggregate can issue multiple queries.

When a query method is called from a `@Transactional` service, the repository call joins the outer transaction. This is the convenient way to keep the lock held across the read, check, and write steps.

If a query method is called standalone, transactions can be declared on the repository interface or method. However, a transaction wrapping only the repository method ends as soon as that method returns. If the service needs to continue processing and then write, the transaction must wrap the entire use case in the service.

## 8. Example of two competing transactions

Suppose inventory initially has `available = 5`. Requests A and B both call `reserve(sku, warehouse, 4)`.

Once A acquires PESSIMISTIC_WRITE, B must wait at its locking SELECT statement. A decrements the quantity to 1 and commits. Only then does B read the row in its transaction, see quantity 1, and throw `InsufficientStockException`.

Result:

| Transaction | Quantity read | Quantity requested | Outcome |
| --- | ---: | ---: | --- |
| A | 5 | 4 | Succeeds, 1 remaining |
| B | 1 | 4 | Rejected |

There is no case where both act on the stale quantity 5 to confirm orders.

Conditions for this example to work:

- Both transactions access the same data row.
- The SELECT acquires the write lock before reading the decision value.
- The lock stays active throughout checking and updating.
- The database supports the lock semantics requested by the dialect.
- All related write paths obey the same business rules.

Pessimistic locking does not protect against another write flow if that flow does not contend on the locked row or operates on a different table/object.

## 9. @Lock currently applies only to derived query methods

In current Spring Data JDBC, `@Lock` is supported on **derived query methods**.

Supported example:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
Optional<StockItem> findBySkuAndWarehouseCode(
    String sku,
    String warehouseCode
);
~~~

For this method, Spring Data generates the SELECT from the method name and appends the dialect's lock clause.

### Do not use @Lock with string-based @Query

`@Lock` is currently not applied to query methods declaring SQL via `@Query`:

~~~java
@Lock(LockMode.PESSIMISTIC_WRITE)
@Query("SELECT * FROM stock_items WHERE sku = :sku")
Optional<StockItem> findLockedBySku(String sku);
~~~

In Spring Data JDBC, locking information from `@Lock` on a string-based query is ignored and the framework logs a warning. Current documentation notes that future versions will throw an exception for this case.

If custom SQL with locking is needed:

- Write the lock clause directly in SQL for your target database.
- Or implement a custom repository using an appropriate JDBC API.
- Ensure the SQL runs inside the transaction wrapping the use case.
- Test the SQL and lock behavior on the actual database.

Do not rely on `@Lock` to lock a custom SQL query.

## 10. Lock scope and what @Lock does not protect

Pessimistic locking affects the database rows locked by the SELECT statement. The exact scope also depends on the generated SQL, query plan, indexes, isolation level, and database locking mechanism.

### 10.1. No matching row means no row lock

If the query finds no matching SKU, there is no existing row to lock. Two transactions both checking a nonexistent SKU can both receive empty results and then both attempt to insert.

To protect creation cases:

- Use a unique constraint so the database guarantees no two rows share the same business key.
- Catch and handle duplicate key errors according to business rules.
- If serialization is required even when keys do not exist yet, consider locking an existing parent row or using a database-specific locking mechanism.

Do not assume SELECT FOR UPDATE on an empty result locks a nonexistent key.

### 10.2. Does not automatically lock all child entities

In Spring Data JDBC, an aggregate can consist of a root and child entities in separate tables. `@Lock` on a query method locks the SELECT generated for that repository method. Do not assume locking the root automatically locks all child rows, rows in other aggregates, or all referenced tables.

If a business invariant depends on multiple rows, explicitly identify the rows that need locking and design queries/transactions accordingly. Locking multiple rows in a consistent order reduces deadlock risk.

### 10.3. Does not replace constraints

Pessimistic locking protects concurrent operations, while constraints protect data validity in the database.

Example:

- `CHECK (available >= 0)` prevents negative inventory.
- `UNIQUE (sku, warehouse_code)` prevents duplicate inventory rows.
- `FOREIGN KEY` protects referential relationships.

Combine transactions, locks, and constraints when invariants must be enforced across multiple layers.

## 11. Pessimistic locking vs. optimistic locking with @Version

Spring Data JDBC also supports optimistic locking via a numeric property annotated with `@Version` on the aggregate root. This mechanism differs from `@Lock`.

| Criterion | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Protection mechanism | Acquires database lock before processing | Compares version on update |
| Conflict detection time | When acquiring or waiting for the lock | When update/delete checks version |
| Holds database lock during processing | Yes | Does not require long-lived pessimistic locks |
| Best suited for | Frequent conflicts requiring serialization | Rare conflicts favoring high transaction concurrency |
| Spring Data JDBC API | `@Lock` + `LockMode` | `@Version` |

Optimistic locking example:

~~~java
@Table("stock_items")
public class StockItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private int available;
}
~~~

On update, Spring Data JDBC includes the current version in the UPDATE predicate. If another transaction has already updated and incremented the version, an update using the stale version no longer matches and Spring throws `OptimisticLockingFailureException`.

There is no `OPTIMISTIC` mode in Spring Data JDBC's `LockMode` enum. `@Version` is a separate mechanism for detecting modified data.

You can choose based on workload characteristics:

- A hot inventory row with many concurrent order requests may suit PESSIMISTIC_WRITE.
- A profile rarely updated concurrently may suit optimistic locking.
- Some use cases combine version checks with transaction boundaries and constraints to handle both stale data and write contention.

## 12. Deadlocks, lock waits, and lock duration

Pessimistic locking forces transactions to wait when conflicts occur. If multiple transactions lock rows in different orders, they can create a **deadlock**.

Example:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Lock row 1                    Lock row 2
Wait for row 2                Wait for row 1
~~~

A holds row 1 and waits for row 2; B holds row 2 and waits for row 1. The database detects the wait cycle and aborts one transaction according to its policy.

Principles to reduce risk:

1. Keep transactions short, wrapping only the operations needing protection.
2. Lock multiple rows in the same order across every processing flow.
3. Avoid network API calls, sending emails, or waiting on users while holding locks.
4. Create appropriate indexes so the database locates the right rows quickly.
5. Handle timeouts and deadlocks at the transaction boundary.
6. If retrying is needed, retry the entire transaction in a fresh transaction after the old one rolls back.

`@Lock` takes only a `LockMode`. The annotation does not provide timeout, NOWAIT, or SKIP LOCKED attributes. If those features are needed, implement them using your database's capabilities and SQL access approach.

## 13. Testing pessimistic locking

Unit tests for a service can verify business rules such as invalid quantities or insufficient stock. However, unit tests do not prove the database actually holds row locks.

To verify concurrency, use integration tests against the same database engine as production:

1. Create an inventory row with an initial quantity.
2. Open transaction A and call the repository method with PESSIMISTIC_WRITE.
3. Hold transaction A uncommitted using a barrier/latch in the test.
4. From transaction B, call the same repository method on the same row.
5. Verify that B waits or receives an error according to the database's semantics.
6. Allow A to update and commit.
7. Verify that B proceeds and reads the new state before deciding whether to update.

Do not rely solely on H2 to infer locking behavior in PostgreSQL or MySQL. Lock syntax, isolation levels, MVCC, and timeouts can differ. Test against a real database or Testcontainers with the exact database image you support.

### Observing SQL

Enable SQL logging or inspect database statements to verify the SELECT includes a lock clause. This helps catch cases where:

- The annotation was placed on the wrong method.
- The method uses a string-based `@Query`.
- The dialect does not support the expected syntax.
- Transaction configuration releases the lock prematurely.

Seeing a SQL statement with a lock clause still does not prove the entire use case is safe. You must also check transaction duration, other write paths, and outcomes when two transactions run concurrently.

## 14. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Another transaction still updates after query returns | Transaction ended and lock was released | Place `@Transactional` on the service wrapping both read and write |
| @Lock has no effect on query | Placed on a string-based `@Query` | Use a derived query or write a SQL lock clause manually |
| PESSIMISTIC_READ also blocks other readers | Database maps both modes to a write lock | Check dialect and database semantics |
| Two requests still both create the same SKU | No existing row to lock | Use a unique constraint and handle insert conflicts |
| Deadlock when processing multiple items | Transactions lock rows in different orders | Sort IDs/SKUs in a consistent order before locking |
| Slow query while holding lock | Predicate lacks an appropriate index or transaction is too long | Optimize indexes and shorten transactions |
| Optional receives multiple results | Condition is not guaranteed unique | Use List or add a unique constraint |
| Confusing LockMode with JPA | Wrong package import or JPA enum used | Use Spring Data Relational's Lock and LockMode |
| Expecting NOWAIT/SKIP LOCKED | Enum has only two modes | Use database-specific SQL/APIs |
| Thinking locking root automatically locks all child tables | Lock scope depends on SELECT and database | Explicitly identify every row needing protection |

## 15. Workflow for selecting and implementing LockMode

When a use case needs protection, follow this sequence:

1. Identify the business invariant to protect, such as non-negative stock.
2. Identify the database rows on which the invariant depends.
3. Choose a derived query method returning the exact rows to lock.
4. Use `PESSIMISTIC_READ` if a shared lock is needed for a protected read operation.
5. Use `PESSIMISTIC_WRITE` if you need to read, check, and update.
6. Place `@Transactional` on the service to hold the lock until the use case finishes.
7. Add unique/check/foreign key constraints for the corresponding invariants.
8. Inspect the SQL generated by the dialect and test on the target database.
9. Measure lock hold times, handle timeouts/deadlocks, and retry only the entire transaction when appropriate.

Do not use pessimistic locking just because there are many users. Lock only the data the use case genuinely needs to protect; holding locks for long periods and locking too many rows reduces system throughput.

## 16. Self-practice exercises

### Exercise 1 — Declaring @Lock

Create a repository for `StockItem`. Write one method using `PESSIMISTIC_READ` and one using `PESSIMISTIC_WRITE`. Explain the difference between their intended uses.

### Exercise 2 — Protecting inventory

Write a `@Transactional` `reserve` service method. Use a write-locking repository method, check the quantity, and decrement inventory. Run two concurrent requests to verify overselling cannot occur.

### Exercise 3 — Observing SQL

Enable SQL logging or inspect database statements. Identify the lock clause generated for each LockMode on your database.

### Exercise 4 — Trying different databases

Run the same integration test on PostgreSQL and MySQL. Compare the lock syntax and behavior of PESSIMISTIC_READ/PESSIMISTIC_WRITE.

### Exercise 5 — Query method vs. @Query

Create a derived query with `@Lock` and a string-based `@Query` method also annotated with `@Lock`. Observe the warning and confirm the annotation is not applied to the string-based query.

### Exercise 6 — Nonexistent rows

Have two transactions concurrently create a nonexistent SKU. Explain why a row lock cannot lock a nonexistent row and use a unique constraint to protect the data.

### Exercise 7 — Deadlocks

Create two transactions that lock two rows in opposite orders. Observe the deadlock, then fix both transactions to lock in the same order.

### Exercise 8 — Comparing with @Version

Add a `@Version` property to the aggregate root. Test concurrent updates with optimistic locking and compare with PESSIMISTIC_WRITE regarding when conflicts are detected.

## 17. Official references

- [Spring Data Relational — Transactionality and JDBC Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): enabling locking with `@Lock` on derived query methods, the two supported LockModes, MySQL SQL example, and limitations with string-based `@Query`.
- [Spring Data Relational — @Lock API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/repository/Lock.html): method-level annotation and `value` attribute taking LockMode.
- [Spring Data Relational — LockMode API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/sql/LockMode.html): enum and supported constants.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): optimistic locking via `@Version` on the aggregate root.

`@Lock` lets Spring Data JDBC ask the database to lock rows queried by derived query methods. The two currently supported modes are `PESSIMISTIC_READ` and `PESSIMISTIC_WRITE`. For a lock to actually protect a use case, wrap both the query and the update in the same transaction, understand how your database implements each mode, and combine constraints to protect cases with no existing rows or competing write paths.

# Conditional updates and checking affected row counts in Spring Data JDBC

## 1. Why are conditional updates needed?

When multiple requests operate on the same row concurrently, reading data first and then deciding how to update it can introduce a race condition.

Suppose initial stock is 5. Two concurrent requests both read 5 and each wants to reserve 4 units. If both calculate the new quantity in Java and overwrite the value they read, the system can accept both requests even though stock is insufficient. This is a check-then-act bug: the condition is checked at one point in time, yet the data can change before the write executes.

A safer approach moves the check condition directly into the UPDATE statement:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :productId
  AND :quantity > 0
  AND available_quantity >= :quantity;
~~~

The database evaluates the condition and updates the row in the same statement. A request succeeds only if the quantity at the moment of the UPDATE still satisfies the condition.

**Conditional updates** combine state checking and data mutation in one database operation. The application inspects the affected row count to determine whether the predicate matched.

This approach is useful for reserving/deducting stock, debiting balances, transitioning order statuses, claiming pending jobs, enforcing quotas, or updating only when the version still matches the caller's read.

## 2. Meaning of the affected row count

An UPDATE statement typically returns the number of rows the database/driver reports as affected. In JDBC, this number is returned by APIs such as `JdbcTemplate.update` or a modifying repository query returning an integer.

Example:

~~~sql
UPDATE customers
SET status = 'INACTIVE'
WHERE id = 42;
~~~

| Update count | Common meaning |
|---:|---|
| 1 | One row matched the UPDATE condition and was reported as affected |
| 0 | No rows were reported as affected |
| Greater than 1 | Multiple rows matched the predicate; may be expected or indicate a missing condition/constraint |

If an UPDATE targets a unique primary key, the application typically expects 0 or 1. If the count exceeds 1, review the predicate or data uniqueness.

### 2.1. A count of 0 does not always have a single cause

For the inventory UPDATE above, a count of 0 can mean:

- No product exists with that productId.
- The product exists, but current available stock is insufficient.
- Another condition in the WHERE clause was no longer true when the UPDATE ran.

Do not automatically turn every 0 count into "product not found". The business error name should reflect what the statement actually proved, such as `StockReservationRejectedException`.

If the API must precisely distinguish "does not exist" from "insufficient stock", add a mechanism to obtain that detail. You can read the state after the UPDATE fails, use SQL returning data supported by the database (e.g., `RETURNING` in PostgreSQL), or use a stored procedure. A read after UPDATE can observe newer state if another request continues modifying the row; choose semantics according to business needs.

### 2.2. Update counts depend on driver and database

JDBC provides update counts per the driver's contract, though some databases distinguish between rows matched by the condition and rows whose values actually changed.

For instance, MySQL driver settings can affect whether changed or matched row counts are reported. For an UPDATE setting a column to its current value, the count can vary by database or driver configuration.

When business logic depends on exact counts, test against the real database and driver. Design transformations so success represents an actual state change, while protecting invariants with appropriate constraints.

## 3. Using @Modifying and @Query in Spring Data JDBC

Spring Data JDBC supports custom write statements using `@Query` combined with `@Modifying`. The method can return the affected row count as an `int`.

Stock reservation repository example:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available_quantity = available_quantity - :quantity
        WHERE product_id = :productId
          AND :quantity > 0
          AND available_quantity >= :quantity
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

`@Query` holds the explicit SQL; `@Modifying` tells Spring Data the method executes a data-modifying statement. Parameters are bound safely, avoiding concatenating input values into SQL.

The `:quantity > 0` check adds protection in the database. The service should still validate inputs to return clear errors before calling the repository:

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException("Quantity must be greater than 0");
}
~~~

Checks in the service improve the API contract; conditions in the UPDATE guard the invariant right at write time.

### 3.1. Checking the update count in the service

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than 0"
            );
        }

        int updated = inventory.reserve(productId, quantity);

        if (updated == 0) {
            throw new StockReservationRejectedException(
                    productId,
                    quantity
            );
        }

        if (updated != 1) {
            throw new IllegalStateException(
                    "A productId must identify exactly one inventory row"
            );
        }
    }
}
~~~

The service interprets the row count according to business rules: 0 means the reservation condition was not met; 1 means reservation succeeded; any other value indicates the assumption that one product ID maps to one row no longer holds.

Place `@Transactional` on the service when the use case also writes orders or other data that must commit/roll back together. For a standalone UPDATE, the repository method may already have suitable transaction behavior; service transactions become essential when combining multiple operations.

### 3.2. Do not read and overwrite quantities in Java

A common pattern that is unsafe under concurrency:

~~~java
Inventory item = inventory.findByProductId(productId)
        .orElseThrow();

if (item.getAvailableQuantity() >= quantity) {
    item.setAvailableQuantity(
            item.getAvailableQuantity() - quantity
    );
    inventory.save(item);
}
~~~

Two requests can read the same stale value before either saves. Without optimistic locking or proper locking, one update can overwrite the other.

A conditional UPDATE combines the subtraction and sufficiency check into one database operation. This fits well when the transformation can be expressed directly in SQL.

## 4. Conditional status updates

Applications often follow state workflows. For instance, an order can only be confirmed when it is currently PENDING.

Do not read the status in Java and then UPDATE by ID alone, because another request could change the status between reading and writing. Put the expected status in the WHERE clause:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PENDING';
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = 'CONFIRMED',
        confirmed_at = CURRENT_TIMESTAMP
    WHERE id = :orderId
      AND status = 'PENDING'
    """)
int confirmIfPending(@Param("orderId") Long orderId);
~~~

Service:

~~~java
@Transactional
public void confirm(Long orderId) {
    int updated = orders.confirmIfPending(orderId);

    if (updated == 0) {
        throw new OrderCannotBeConfirmedException(orderId);
    }

    if (updated != 1) {
        throw new IllegalStateException(
                "Order ID must identify exactly one row"
        );
    }
}
~~~

Only one request can transition the row from PENDING to CONFIRMED under this predicate. Once the first request succeeds, the next request evaluates the condition against the new state and no longer matches.

### 4.1. Compare-and-set in the database

This update pattern can be viewed as compare-and-set:

- Compare: the current state must equal the expected value.
- Set: if the condition holds, update to the new value.
- Count: use the update count to see how many rows matched the condition.

General pattern:

~~~sql
UPDATE some_table
SET value = :newValue
WHERE id = :id
  AND value = :expectedValue;
~~~

For state machines, the predicate can enforce multiple conditions:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = :id
  AND status IN ('PENDING', 'CONFIRMED')
  AND payment_status = 'UNPAID';
~~~

The database applies the transition only if the current status is within the allowed states and the payment condition still holds.

## 5. Combining conditional updates with optimistic locking

Spring Data JDBC supports optimistic locking using `@Version`. When saving a versioned aggregate, the framework uses the current version to detect whether another transaction updated the row since the entity was read.

Example:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        @Version Long version,
        String name,
        int availableQuantity
) {}
~~~

When reading the entity, the caller receives the version. When calling repository `save`, Spring Data JDBC uses the version to guard the update and increments the version upon a successful save. If the version no longer matches, the operation can throw `OptimisticLockingFailureException`.

### 5.1. Hand-written conditional SQL must manage version manually

An UPDATE written manually with `@Modifying @Query` is SQL controlled by the application. Do not assume Spring Data JDBC automatically adds a `@Version` predicate or increments the version for that SQL statement.

If you want a conditional UPDATE with optimistic locking, include the version in WHERE and increment it in SET:

~~~sql
UPDATE products
SET available_quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND available_quantity >= :requestedQuantity;
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE products
    SET available_quantity = :newQuantity,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
      AND available_quantity >= :requestedQuantity
    """)
int updateQuantityIfVersionMatches(
        @Param("id") Long id,
        @Param("newQuantity") int newQuantity,
        @Param("expectedVersion") Long expectedVersion,
        @Param("requestedQuantity") int requestedQuantity
);
~~~

If the count is 1, the update succeeded and the version incremented. If the count is 0, one of the conditions no longer held: the row does not exist, the version changed, or the quantity did not satisfy the predicate.

If the application still holds an old entity instance after a direct UPDATE, that instance still carries the stale version. Reload the entity or update in-memory state deliberately; never keep saving the stale instance as though its version were synced.

### 5.2. Choosing a conditional predicate vs. @Version

| Scenario | Suitable mechanism |
|---|---|
| Deduct stock only when quantity is sufficient | Conditional UPDATE with sufficient-quantity predicate |
| Transition status only from PENDING to CONFIRMED | Conditional UPDATE with status predicate |
| Update aggregate matching the version read | `@Version` with repository `save` |
| Need both business condition and version check | Custom UPDATE with both business predicate and version predicate |
| Modify multi-table aggregate via mapping | Repository `save`/aggregate operations and `@Version` |

Optimistic locking detects changes via a version token. Conditional updates directly express a business predicate. Both can be combined when a use case needs both.

## 6. Balance updates and inviolable invariants

Another example is debiting funds from an account. Do not read the balance, compute the new balance in Java, and overwrite it without protection.

SQL:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND :amount > 0
  AND balance >= :amount;
~~~

Repository:

~~~java
@Modifying
@Query("""
    UPDATE accounts
    SET balance = balance - :amount
    WHERE id = :accountId
      AND :amount > 0
      AND balance >= :amount
    """)
int debit(
        @Param("accountId") Long accountId,
        @Param("amount") BigDecimal amount
);
~~~

Service:

~~~java
@Transactional
public void transfer(
        Long sourceId,
        Long targetId,
        BigDecimal amount
) {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("Invalid amount");
    }

    int debited = accounts.debit(sourceId, amount);

    if (debited != 1) {
        throw new DebitRejectedException(sourceId);
    }

    int credited = accounts.credit(targetId, amount);

    if (credited != 1) {
        throw new CreditRejectedException(targetId);
    }
}
~~~

A transaction must wrap both debit and credit. If debit succeeds and credit fails, the transaction must roll back the debit. Without a shared transaction, money could be deducted from the source account without being added to the target account.

The credit statement should also verify the account exists and any related invariants hold. The schema can add appropriate constraints, though constraints do not replace the transaction for the transfer use case.

## 7. Using JdbcTemplate.update when SQL control is needed

Not every conditional UPDATE must live in a repository. For technical tables or custom SQL, `JdbcTemplate` and `NamedParameterJdbcTemplate` provide direct execution and return the update count.

Example:

~~~java
@Repository
public class InventoryDao {

    private final NamedParameterJdbcTemplate jdbc;

    public InventoryDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int reserve(Long productId, int quantity) {
        String sql = """
                UPDATE inventory
                SET available_quantity = available_quantity - :quantity
                WHERE product_id = :productId
                  AND :quantity > 0
                  AND available_quantity >= :quantity
                """;

        var parameters = new MapSqlParameterSource()
                .addValue("productId", productId)
                .addValue("quantity", quantity);

        return jdbc.update(sql, parameters);
    }
}
~~~

`NamedParameterJdbcTemplate.update` returns an `int` representing the update count reported by the JDBC driver. This fits cases needing controlled dynamic SQL, CTEs, or database-specific syntax.

When using a JDBC template directly:

- The application manages the SQL itself.
- Entity mapping is not applied automatically.
- `@Version` predicates and increments are not added automatically.
- Spring Data repository lifecycle callbacks do not run automatically.
- The application must enforce aggregate invariants and table relationships itself.

If the operation belongs to an aggregate and relies on Spring Data JDBC mapping semantics, consider the repository API before dropping down to direct SQL.

## 8. Transactions and update counts

The update count tells you how many rows a statement affected; the transaction decides whether those changes commit or roll back.

- An UPDATE with count 1 can still roll back if the transaction fails later.
- An UPDATE with count 0 generally modifies no rows, yet the transaction can still proceed.
- Multiple UPDATEs can share one transaction when the service sets the right transaction boundary.
- The count is returned before transaction commit; never report "completed" to external systems before commit succeeds.

Example:

~~~java
@Transactional
public void placeOrderAndReserveStock(
        Order order,
        Long productId,
        int quantity
) {
    orders.save(order);

    int updated = inventory.reserve(productId, quantity);

    if (updated != 1) {
        throw new StockReservationRejectedException(
                productId,
                quantity
        );
    }
}
~~~

If reservation fails, the runtime exception escaping the method causes the transaction to roll back by default. The previously saved order record is also rolled back when sharing the same transaction manager and DataSource.

### 8.1. Do not swallow exceptions after a failed count

Inappropriate example:

~~~java
@Transactional
public void placeOrder(...) {
    orders.save(order);

    int updated = inventory.reserve(productId, quantity);

    if (updated == 0) {
        log.warn("Insufficient stock");
        return; // Method returns normally; order may commit.
    }
}
~~~

If stock is insufficient, the order should not be saved, yet returning normally allows the transaction to commit the order. Throw an appropriate exception or return a business result handled before writing the order.

An alternative design runs the conditional UPDATE first and saves the order only if it succeeds. Regardless of order, all steps must run inside a shared transaction if they must be atomic.

## 9. Race conditions: why is conditional UPDATE safer?

Suppose initial stock is 5, and two concurrent requests both ask for 4.

With read-then-write:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: SELECT quantity = 5
    B->>DB: SELECT quantity = 5
    A->>A: 5 >= 4
    B->>B: 5 >= 4
    A->>DB: UPDATE quantity = 1
    B->>DB: UPDATE quantity = 1
    Note over DB: Both requests can be accepted
~~~

With conditional UPDATE:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: UPDATE ... WHERE quantity >= 4
    B->>DB: UPDATE ... WHERE quantity >= 4
    DB-->>A: update count = 1
    DB-->>B: update count = 0
    Note over DB: Only one request reserves 4 units
~~~

The database serializes contention on the updated row. One request succeeds; the other evaluates the predicate against the current value after contention resolves and no longer qualifies.

Exact behavior also depends on isolation level and database engine, but keeping the condition and update in a single statement eliminates the race window of separate read-then-write steps.

## 10. Database constraints are still necessary

Conditional UPDATEs protect an invariant in one operation, but they do not replace schema constraints.

Example:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_quantity_nonnegative
CHECK (available_quantity >= 0);
~~~

This constraint blocks any write path from producing negative quantities, even if another piece of code forgets to use a conditional UPDATE.

Invariants to enforce in the database whenever possible:

- Non-negative inventory stock.
- Non-negative balances if the domain forbids overdrafts.
- Unique business keys.
- Valid foreign keys.
- Non-null required fields.

Combine multiple layers of defense: validate requests in the service; use conditional UPDATEs to enforce conditions at write time; use database constraints to guard invariants against all write paths; and use transactions to group multiple changes into one unit.

## 11. Batch updates and update count arrays

When updating multiple records via JDBC batching, the API typically returns `int[]` instead of a single integer:

~~~java
int[] counts = jdbcTemplate.batchUpdate(
        "UPDATE inventory SET available_quantity = available_quantity - ? "
                + "WHERE product_id = ? AND available_quantity >= ?",
        items,
        200,
        (ps, item) -> {
            ps.setInt(1, item.quantity());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
        }
);
~~~

Each array element corresponds to a batch entry per the driver's contract. Values can be:

- Number of affected rows.
- `Statement.SUCCESS_NO_INFO`: the statement succeeded, but the driver does not report an exact row count.
- `Statement.EXECUTE_FAILED`: the batch entry failed in certain error-reporting modes.

When a batch throws `BatchUpdateException`, the exception may include update counts for entries executed before the error occurred. Do not assume all drivers execute or report errors identically.

If business rules require verifying that each item updated exactly one row, batch APIs may be insufficient if the driver returns `SUCCESS_NO_INFO`. You may need individual statements, smaller batches, or database-supported result-returning SQL.

## 12. Distinguishing update counts from optimistic locking exceptions

| Update approach | How conflicts are reported |
|---|---|
| Repository `save` with `@Version` entity | Can throw `OptimisticLockingFailureException` on version mismatch |
| Custom `@Modifying @Query` returning `int` | Application inspects count; usually 0 means predicate failed to match |
| `JdbcTemplate.update` | Returns update count |
| JDBC batch | Returns array of update counts or throws `BatchUpdateException` |

Do not expect `@Modifying` to throw an optimistic locking exception automatically simply because the SQL WHERE includes a version condition. When a custom query returns 0, the application must interpret it and translate it into an appropriate exception or domain result.

Conversely, do not compare update counts on a repository `save` with `@Version` as if it were a modifying query. Follow the contract of the API you are calling.

## 13. Common mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Two requests reserve past available stock | Reading and writing in Java without an atomic condition/version | Use conditional UPDATE or optimistic locking |
| Update count is 0 but wrong error is reported | A predicate can fail for several reasons | Use a general error or query further if distinction is needed |
| Count exceeds 1 when updating one product | product_id is not unique or predicate lacks conditions | Add a unique constraint and fix WHERE |
| Custom UPDATE ignores version | Expecting Spring to auto-apply `@Version` to hand-written SQL | Add version to WHERE and increment version in SET |
| In-memory entity still holds old version | Direct UPDATE does not sync loaded objects | Reload the entity or update state intentionally |
| Order still saved when stock reservation fails | Count is 0 but method returns normally | Throw an exception or handle the result before committing |
| Debit succeeds while credit fails | The two operations are not in a shared transaction | Place `@Transactional` on the service |
| UPDATE setting the same value returns unexpected count | Database/driver distinguishes matched vs. changed rows | Test the target database's semantics |
| SQL injection in update condition | Concatenating user input into SQL | Bind all values with named/positional parameters |
| Batch count is `SUCCESS_NO_INFO` | Driver does not provide exact row counts | Choose a strategy compatible with the batch contract |
| Check constraint still violated by another write path | Invariant protected in only one method | Add constraints in the database |
| Exception caught and swallowed inside transaction | Caller sees no error to trigger default rollback | Re-throw exception or mark rollback-only deliberately |

## 14. Workflow for implementing conditional updates

1. Identify the invariant to protect, e.g., non-negative quantity or status must be PENDING.
2. Move the check condition into the UPDATE's WHERE clause.
3. Put the data transformation in the same statement.
4. Bind parameters; never concatenate request values into SQL.
5. Pick the right API: `@Modifying @Query`, `JdbcTemplate.update`, or repository `save` with `@Version`.
6. Read the update count and define the exact meaning of 0, 1, or more than 1 rows.
7. Translate the outcome into a domain exception or business result.
8. Wrap multiple atomic operations in a service transaction.
9. Add database constraints for invariants expressible in the schema.
10. Test two concurrent requests against the target database and verify invariants are never breached.

## 15. Practice exercises

### Exercise 1 — Conditional stock reservation

Create an inventory table with available_quantity. Write a `reserve` method with `@Modifying @Query` that deducts only when current stock is sufficient. Test update counts for an existing product, nonexistent product, and insufficient stock.

### Exercise 2 — Two competing requests

Set initial stock to 5. Run two concurrent threads requesting 4 units each. Compare read-then-write with conditional UPDATE. Verify total reserved stock never exceeds 5.

### Exercise 3 — State transition

Write an UPDATE that transitions an order only from PENDING to CONFIRMED. Send two concurrent requests and verify only one receives a count of 1.

### Exercise 4 — Optimistic locking

Add `@Version` to an entity. Read the same entity in two transactions, save sequentially, and observe the optimistic locking failure. Then write a custom UPDATE with a version predicate and manual version increment.

### Exercise 5 — Multi-operation transaction

Write a use case that creates an order and reserves stock. When update count is 0, throw a runtime exception. Verify the order rolls back. Then try catching the exception without re-throwing to observe the difference.

### Exercise 6 — JDBC update count

Write the same conditional UPDATE using `JdbcTemplate.update` and repository `@Modifying @Query`. Compare return values and transaction participation.

### Exercise 7 — Database constraints

Add a CHECK constraint forbidding negative stock. Test another UPDATE statement that omits the stock sufficiency check and verify the database still enforces the invariant.

### Exercise 8 — Batch update

Update multiple products using `batchUpdate`. Inspect `int[]`, test an entry that fails the condition and an entry that violates a constraint. Handle `BatchUpdateException` and driver-reported update counts.

## 16. Key takeaways

- Conditional updates combine checking and modifying data in a single UPDATE statement to eliminate read-then-write race conditions.
- The update count reports how many rows JDBC/the database says were affected; for unique keys, applications normally expect 0 or 1.
- A count of 0 can mean the row does not exist or a business predicate failed; do not assume a specific cause if the statement cannot distinguish them.
- Use `@Modifying @Query` for write SQL in repositories or `JdbcTemplate.update` when direct SQL control is needed.
- Custom SQL does not automatically apply `@Version` optimistic locking; include a version predicate and increment the version in SET when needed.
- Repository `save` with `@Version` has its own optimistic locking contract and can throw `OptimisticLockingFailureException`.
- Put `@Transactional` on the service when multiple database operations must commit or roll back together.
- Update count differs from transaction outcome: a statement can report success while the transaction later rolls back.
- Database constraints continue protecting invariants across every write path.
- With batching, the result is an array of update counts and may contain `SUCCESS_NO_INFO` or `EXECUTE_FAILED`; understand your driver's behavior.

# Atomic Single-Column Updates with SQL Conditions

In a Spring Data JDBC application, sometimes you only need to change **a single column** of a row based on its current state in the database. For example: decrementing inventory if sufficient stock remains, incrementing a counter, or transitioning an order status only when the previous status matches expectations.

An obvious thought is to load the aggregate, modify the field in Java, and call `repository.save`. However, for simple updates that must execute safely under concurrent requests, you can write a **conditional SQL UPDATE** so the database checks the condition and updates the value in the same statement.

Spring Data JDBC supports this via `@Query` combined with `@Modifying`. The statement runs directly against the database and can return the affected row count. This lesson presents how to use it, what atomicity means, transaction scoping, and the side effects to watch for when updating directly instead of saving the aggregate.

## 1. Why Update a Single Column Directly?

Suppose an inventory table has a row:

```text
inventory
+----+---------+--------------------+
| id | sku     | available_quantity |
+----+---------+--------------------+
|  7 | BOOK-01 |                 10 |
+----+---------+--------------------+
```

Two requests simultaneously want to buy one unit of a product. If each request follows the flow:

1. Read `available_quantity` from the database.
2. Check whether stock is sufficient.
3. Compute the new value in Java.
4. Call `save` to persist the aggregate.

then both requests can read the value 10 before either writes. Both compute 9 and both save 9. The final result decreases by only one unit despite two successful orders.

This is a **lost update**: one write based on stale data overwrites the result of another write.

For a simple arithmetic update, you can let the database compute from the current value:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE id = 7;
```

Each statement updates the row's current value directly. The database coordinates concurrent writes using its locking and transaction mechanisms, so two decrements apply sequentially rather than both writing back an old value computed in Java.

## 2. Condition and Change in the Same Statement

If you only write:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE sku = 'BOOK-01';
```

the statement can still drive inventory below 0. We need to place the business condition in `WHERE`:

```sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE sku = 'BOOK-01'
  AND available_quantity >= 1;
```

The database evaluates the condition and performs the update in one operation. When two requests contend for the same row, the database applies its concurrency rules; after one request updates, the other evaluates the condition against the current row state. If stock is no longer sufficient, the UPDATE does not affect that row.

This is commonly called a **conditional atomic update**, or **compare-and-set** when the condition compares an expected previous state and sets a new value.

### 2.1. Distinguishing Statement Atomicity from Transactions

- **Atomic statement:** a single UPDATE executed by the database as one unit. The check and the update are not split into two independent Java operations.
- **Transaction:** groups multiple statements into one commit/rollback unit. A transaction is needed when the use case includes other operations that must succeed or fail together.

A single UPDATE is already an atomic statement under the database's transaction semantics. `@Transactional` in the service layer coordinates it with other database operations in the same use case.

Single-statement atomicity does not automatically enforce invariants across multiple rows, multiple tables, or multiple aggregates. Those cases require transactions, constraints, locks, or an appropriate isolation level.

## 3. `@Modifying` and `@Query` in Spring Data JDBC

Spring Data JDBC lets you declare custom SQL with `@Query`. For INSERT, UPDATE, DELETE, or DDL statements that do not return a row set, mark the method as a modifying query using `@Modifying`.

Imports:

```java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
```

Repository example:

```java
public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available_quantity = available_quantity - :quantity
        WHERE sku = :sku
          AND :quantity > 0
          AND available_quantity >= :quantity
        """)
    int reserve(
        @Param("sku") String sku,
        @Param("quantity") int quantity
    );
}
```

Explanation:

- `@Query` holds the SQL to execute.
- `@Modifying` tells Spring Data that this is a data-modifying query, not an entity read query.
- `:sku` and `:quantity` are named parameters bound from method arguments.
- `available_quantity - :quantity` computes the new value directly in the database.
- `available_quantity >= :quantity` prevents decrementing past available stock.
- `:quantity > 0` rejects invalid requested quantities directly in SQL.
- Return type `int` receives the affected row count.

Spring Data JDBC supports `void`, `int` (updated row count), and `boolean` (whether at least one row was updated) as return types for modifying queries. For operations that need to inspect the exact outcome, `int` is usually more useful.

**Package note:** Spring Data JDBC's `@Modifying` is `org.springframework.data.jdbc.repository.query.Modifying`. Do not mistakenly import the annotation of the same name from Spring Data JPA.

## 4. Interpreting the Affected Row Count

The return value of `reserve` indicates whether the UPDATE condition matched any row:

| Return value | Meaning in example |
| --- | --- |
| `1` | One inventory row was updated; reservation succeeded. |
| `0` | No row matched the condition: SKU does not exist, quantity is invalid, or stock is insufficient. |
| Greater than `1` | Multiple rows matched; schema may lack a unique constraint or `WHERE` is too broad. |

If `sku` is unique, a valid request should update at most one row. The database should enforce that rule with a unique constraint:

```sql
ALTER TABLE inventory
ADD CONSTRAINT uq_inventory_sku UNIQUE (sku);
```

Do not rely solely on Java code to ensure one SKU has one inventory row.

### 4.1. Why Does `0` Not Uniquely Mean "Insufficient Stock"?

In the statement above, `0` can occur when:

- The SKU was not found.
- `quantity` is 0 or negative.
- The SKU exists, but stock is insufficient.

If the business only needs to know whether the operation succeeded, a 0/1 outcome suffices. If you must report the exact reason, the service can run an additional read query to determine the state. However, that follow-up read reflects the state at the moment of the read; data may continue changing under concurrent requests.

For APIs that must distinguish outcomes in a single round trip, consider a database-specific statement returning extra data (such as `UPDATE ... RETURNING` in PostgreSQL) and a custom repository. This capability depends on dialect and result mapping; do not assume every database supports the same syntax.

## 5. Placing the Transaction in the Application Service

A modifying query method is a declared query method; its transaction should be defined explicitly. The standard pattern is to place the transaction on the service to span the entire use case.

```java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be greater than 0"
            );
        }

        int updated = inventory.reserve(sku, quantity);

        if (updated == 0) {
            throw new InsufficientStockException(
                "Cannot reserve stock for SKU " + sku
            );
        }

        if (updated != 1) {
            throw new IllegalStateException(
                "Invalid updated inventory row count: " + updated
            );
        }
    }
}
```

In this example:

1. The service validates input data.
2. The repository sends one conditional UPDATE statement.
3. The database returns the affected row count.
4. The service determines the business outcome.
5. If a runtime exception is thrown within Spring's default transaction, the transaction rolls back according to default rollback rules.

If a modifying query is called on a repository interface annotated with `@Transactional(readOnly = true)` at the interface level, the write method requires a non-read-only transaction (or must be called inside a service write transaction). Do not run an UPDATE inside a read-only transaction.

### 5.1. When to Place `@Transactional` on the Repository?

It can be declared directly:

```java
@Modifying
@Transactional
@Query("""
    UPDATE inventory
    SET available_quantity = available_quantity - :quantity
    WHERE sku = :sku
      AND available_quantity >= :quantity
    """)
int reserve(
    @Param("sku") String sku,
    @Param("quantity") int quantity
);
```

This makes the repository method transactional on its own. However, if the use case also needs to write an order, write history, or trigger other database operations, a service-level transaction expresses the business boundary more clearly and lets multiple repositories participate in one transaction.

Do not open separate transactions per statement when they must commit or roll back together as a single use case.

## 6. Updating a Column Based on Its Current Value

A major advantage of UPDATE expressions is that the database computes the new value from the value currently stored in the updated row.

Counter example:

```sql
UPDATE page_counters
SET view_count = view_count + 1
WHERE page_key = :pageKey;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE page_counters
    SET view_count = view_count + 1
    WHERE page_key = :pageKey
    """)
int incrementViewCount(@Param("pageKey") String pageKey);
```

This is generally safer than:

```java
Counter counter = repository.findByPageKey(pageKey);
counter.setViewCount(counter.getViewCount() + 1);
repository.save(counter);
```

If two requests both read `view_count = 10`, both could write `11`. With `view_count = view_count + 1`, the database applies two increments to the current row value; the result is 12 when both statements succeed.

Similar expressions:

```sql
UPDATE accounts
SET balance = balance + :amount
WHERE id = :id;

UPDATE products
SET sold_count = sold_count + :quantity
WHERE id = :id;

UPDATE tasks
SET retry_count = retry_count + 1
WHERE id = :id;
```

If the calculation is conditional, add the condition to `WHERE` in the same UPDATE instead of checking with a separate SELECT before writing.

## 7. Updating Status Based on an Expected Prior Value

Conditional UPDATE also works well for state transitions. For example, only allow transitioning an order from `PENDING` to `CONFIRMED`:

```sql
UPDATE purchase_orders
SET status = :newStatus
WHERE id = :id
  AND status = :expectedStatus;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :newStatus
    WHERE id = :id
      AND status = :expectedStatus
    """)
int changeStatus(
    @Param("id") Long id,
    @Param("expectedStatus") String expectedStatus,
    @Param("newStatus") String newStatus
);
```

If two requests simultaneously attempt to transition from `PENDING` to two different statuses, only the first sees the old status matching the condition. The second receives an updated row count of 0.

This is a form of **compare-and-set**:

```text
If current status == expectedStatus:
    update to newStatus
Else:
    do not modify the row
```

The service can treat a result of 0 as a status conflict or a nonexistent order. If status is part of a complex state machine, ensure every valid transition is expressed in SQL conditions or coordinated through appropriate domain logic.

## 8. Preserving Optimistic Locking During Direct Updates

If an aggregate root has `@Version`, `repository.save` operations managed by Spring Data JDBC use the version to detect updates based on stale data.

A SQL statement marked with `@Modifying` runs directly on the database. It does not automatically apply the aggregate save path's optimistic locking rules. If you want to preserve optimistic locking on this update path, you must **put the version in `WHERE` and increment the version in the same UPDATE**.

Example:

```sql
UPDATE inventory
SET available_quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND :newQuantity >= 0;
```

Repository:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available_quantity = :newQuantity,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
      AND :newQuantity >= 0
    """)
int updateQuantity(
    @Param("id") Long id,
    @Param("expectedVersion") Long expectedVersion,
    @Param("newQuantity") int newQuantity
);
```

If the version in the database no longer equals `expectedVersion`, the UPDATE matches no row and returns 0. The service can report an optimistic locking conflict or ask the caller to reload data and retry per business policy.

Do not add only `version = version + 1` while omitting the old-version condition if the goal is to detect stale updates. Nor should a direct update modify a row while leaving `version` unchanged, because other flows using `@Version` may fail to notice the row changed.

### 8.1. `@Version` Is Not Always Needed

If the statement only increments an independent counter and the SQL expression already expresses the entire desired operation, a separate version check may not be needed for that operation. For example, `view_count = view_count + 1` is executed by the database against the current value.

Version is needed when business rules require detecting that a client is updating based on a specific snapshot of the aggregate, or when one change can conflict with other aggregate write operations.

## 9. Direct UPDATE and Spring Data JDBC Aggregates

Spring Data JDBC organizes persistence around the aggregate root. When calling `repository.save(root)`, the framework uses mapping metadata to synchronize the root and owned components.

A modifying query such as:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

operates directly on the table. It does not load the aggregate, does not call domain methods, and does not synchronize child entity collections.

This can be appropriate for an independent column, such as:

- A view counter.
- A conditional stock quantity.
- A processing flag or status guarded by `WHERE`.
- A directly updated timestamp or metadata field.

However, do not use direct UPDATE to bypass complex invariants that domain methods must protect. If changing one column requires updating multiple child objects or recalculating multiple values across the aggregate, reconsider the use-case design.

### 9.1. Previously Loaded Objects Do Not Update Automatically

Suppose a service loaded:

```java
InventoryItem item = inventoryRepository.findById(id).orElseThrow();
```

Then a modifying query changes `available_quantity` in the database. The `item` variable in memory still holds the old value; Spring Data JDBC does not automatically mutate objects held in Java variables.

If you need the new value, read it again:

```java
InventoryItem reloaded =
    inventoryRepository.findById(id).orElseThrow();
```

In particular, do not take an old aggregate, run a direct UPDATE, and then continue calling `save(oldAggregate)` without accounting for stale data. The subsequent aggregate save can overwrite the column you just updated directly with its old value.

## 10. Entity Callbacks and Auditing Do Not Run Automatically

Modifying queries execute directly on the database. Spring Data JDBC does not invoke entity callbacks or lifecycle events for these queries. Therefore, auditing fields such as `@LastModifiedDate` or `@LastModifiedBy` do not update automatically simply because an UPDATE changed another column.

If you need to update the modification timestamp, include the column in the SQL itself:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity,
    updated_at = CURRENT_TIMESTAMP
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

Or use a database-managed trigger. If you need to store the actor, pass an authenticated value as a parameter:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity,
    updated_at = CURRENT_TIMESTAMP,
    updated_by = :actor
WHERE sku = :sku
  AND available_quantity >= :quantity;
```

Do not assume that enabling Spring Data JDBC auditing causes every `@Modifying` SQL statement to append audit values automatically. Direct queries must update them unless another trigger/database mechanism handles it.

## 11. SQL Parameter Binding and Safety Conditions

Use named parameters for values:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available_quantity = available_quantity - :quantity
    WHERE sku = :sku
    """)
int decrease(
    @Param("sku") String sku,
    @Param("quantity") int quantity
);
```

Spring Data JDBC binds values through JDBC mechanisms. Do not concatenate request data into SQL strings:

```java
// Unsafe: do not concatenate user values into SQL.
String sql = "UPDATE inventory SET available_quantity = "
    + quantity + " WHERE sku = '" + sku + "'";
```

Parameter binding prevents input values from being interpreted as SQL syntax. However, bind parameters cannot substitute for table names, column names, or SQL keywords. Those identifiers must be fixed in the query or chosen from an allowlist.

Also verify:

- The `quantity` value must be positive.
- ID/SKU must match the schema data type.
- The updated column should have appropriate constraints.
- The `WHERE` clause must be strict enough not to accidentally update multiple rows.
- The SQL must match the dialect of the database in use.

## 12. Testing Conditional Updates

Integration tests should verify both when the update succeeds and when the condition is not met.

Suppose the repository has the `reserve` method from section 3 and the entity:

```java
@Table("inventory")
public record InventoryItem(
    @Id Long id,
    String sku,
    int availableQuantity
) {}
```

An illustrative test:

```java
@DataJdbcTest
class InventoryRepositoryTest {

    @Autowired
    InventoryRepository inventory;

    @Test
    void decreasesQuantityWhenEnoughStockExists() {
        InventoryItem item = inventory.save(
            new InventoryItem(null, "BOOK-01", 10)
        );

        int updated = inventory.reserve("BOOK-01", 3);

        assertThat(updated).isEqualTo(1);

        InventoryItem reloaded = inventory.findById(item.id())
            .orElseThrow();

        assertThat(reloaded.availableQuantity()).isEqualTo(7);
    }

    @Test
    void doesNotDecreaseQuantityWhenStockIsInsufficient() {
        InventoryItem item = inventory.save(
            new InventoryItem(null, "BOOK-02", 2)
        );

        int updated = inventory.reserve("BOOK-02", 5);

        assertThat(updated).isZero();

        InventoryItem reloaded = inventory.findById(item.id())
            .orElseThrow();

        assertThat(reloaded.availableQuantity()).isEqualTo(2);
    }
}
```

These tests require a matching test schema. With `@DataJdbcTest`, the test-slice transaction usually rolls back after each test. If you need to verify real concurrent contention, write an integration test using multiple independent transactions/connections against the actual deployment database and driver.

### 12.1. Testing Concurrent Contention

A concurrency test can launch two transactions trying to reserve more than the total stock. For example, stock is 5, and two requests each try to reserve 4:

- Both call `reserve("BOOK-01", 4)`.
- Only one UPDATE can satisfy the condition and update the row.
- The other sees insufficient stock and returns 0.
- The final state is stock = 1, with only one request succeeding.

The scenario must use two genuinely independent connections/transactions; two sequential calls inside the same transaction do not simulate real concurrent contention.

Do not test concurrency using only `sleep` or random timing. Use barriers/latches to synchronize thread start points and assert on updated row counts and final database state.

## 13. Limitations of a Single UPDATE Statement

A conditional UPDATE is very useful, but it is not a solution for every business rule.

### 13.1. Conditions Based Only on a Single Row

For example, `available_quantity >= :quantity` is a condition directly on the updated inventory row. The database can check and modify the row in one statement.

If an invariant depends on an aggregate sum across multiple rows—such as "total reserved seats across all rooms cannot exceed capacity"—an UPDATE on a single row does not automatically guarantee that invariant if other transactions can also write related rows. You may need constraints, locks, isolation, or a different data model.

### 13.2. Does Not Update Other Aggregates

An UPDATE on `inventory` does not automatically create an order, record a payment, or publish a domain event. If the use case must reserve stock and create an order in the same database, place the necessary operations inside an appropriate transactional service.

If the workflow spans multiple services/databases, design orchestration, an outbox, or a saga. A single JDBC UPDATE cannot act as a distributed transaction.

### 13.3. Database Triggers and Side Effects

An UPDATE can fire triggers or constraints. This is database-managed behavior. Know what triggers exist on the table, especially if they write audit logs, update related tables, or alter other values.

A direct UPDATE does not run Spring Data entity callbacks, but database triggers still fire according to the schema configuration.

## 14. When to Use a Modifying Query vs. `save(root)`?

| Need | Appropriate approach |
| --- | --- |
| Increment/decrement a counter using an expression on the current value | `@Modifying` + conditional UPDATE |
| Deduct inventory if sufficient quantity remains | UPDATE with `available_quantity >= :quantity` |
| Transition status if previous status matches | UPDATE with `WHERE status = :expectedStatus` |
| Modify multiple properties and enforce domain invariants | Load aggregate, call domain method, `repository.save(root)` |
| Synchronize child entity collections belonging to an aggregate | Use aggregate root persistence |
| Need automatic Spring Data entity callbacks/auditing | Use aggregate persistence path or update audit columns manually in SQL |
| Need optimistic locking for a direct update | Include old version in `WHERE` and increment version in the same UPDATE |
| Update multiple tables that must commit/roll back together | Service transaction coordinating repositories/queries |

Do not overuse modifying queries just to save a few lines of code. They are the right tool for operations with clear semantics—typically small, conditional changes that can be expressed accurately in SQL.

## 15. Common Pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| UPDATE does not run or is treated as a read query | Missing `@Modifying` on `@Query` method. | Mark the modifying query with the correct Spring Data JDBC annotation. |
| Wrongly importing JPA's `@Modifying` | Multiple annotations share the same name across Spring Data modules. | Use `org.springframework.data.jdbc.repository.query.Modifying`. |
| Method returns entity when SQL has no result set | Modifying queries return void, row count, or boolean per contract. | Use `int`/`boolean` or a separate read query after updating. |
| Inventory quantity becomes negative | Check condition was omitted from `WHERE` or not strict enough. | Put the invariant in the same UPDATE and add a `CHECK` constraint if appropriate. |
| Two requests lose a counter increment | Reading, computing in Java, and writing back old value. | Use an expression like `column = column + :delta`. |
| Method returns 0 and app treats it as a SQL error | No row satisfied the condition. | Interpret row count as a business outcome. |
| `@LastModifiedDate` does not change | Modifying queries do not invoke entity callbacks/auditing. | Update audit columns in SQL or use a trigger. |
| Next save overwrites with stale data | In-memory aggregate was loaded before the direct UPDATE. | Reload before continuing to save the aggregate. |
| Optimistic locking misses direct updates | SQL neither checks nor increments version. | Add version predicate and increment version in the same UPDATE. |
| Unintended multiple rows updated | Underspecified `WHERE` or missing unique constraint. | Tighten predicate, add constraint, and check row count. |
| Query method runs in a read-only transaction | Repository/service transaction is marked read-only. | Put a writable transaction on the service or modifying method. |

## 16. Process for Designing an Atomic Column Update

When you need to update a single column directly:

1. Identify the exact column to change and the operation type (assign, increment, decrement, transition state).
2. Write the invariant-protecting condition in `WHERE` in the same UPDATE.
3. Use a SQL expression based on the current value if the operation must be safe against lost updates.
4. Declare `@Query` and `@Modifying` in the Spring Data JDBC repository.
5. Use named parameters to bind values.
6. Choose return type `int` if you need to know the affected row count.
7. Place the transaction on the service if the use case coordinates multiple operations; do not run modifying queries inside read-only transactions.
8. If the aggregate has `@Version`, manage version in SQL when the direct update must preserve optimistic locking.
9. Update audit columns in SQL/triggers because entity callbacks do not run automatically.
10. Reload the aggregate if code needs the updated state after a direct update.
11. Test success cases, failure conditions, and concurrency against an appropriate database.
12. Ensure the direct operation does not violate aggregate invariants or ownership.

> **An atomic conditional single-column update means placing the mutation and the check condition in the same UPDATE statement.** In Spring Data JDBC, use `@Modifying` with `@Query`, bind parameters safely, and read the affected row count to determine the outcome. When an operation must preserve optimistic locking, auditing, or multi-invariant aggregate rules, express those rules explicitly in SQL/transactions or use the appropriate aggregate save path.

### References

- [Spring Data JDBC — Query Methods: Modifying Query](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): declaring modifying queries with `@Modifying` and supported return types.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transactions for CRUD and query methods, and configuring transactions for write operations.
- [Spring Data JDBC — @Modifying API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Modifying.html): package and purpose of the `@Modifying` annotation.
- [Spring Data JDBC — @Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): declaring SQL and named parameters for repository methods.
- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): UPDATE syntax, SET expressions, and WHERE clauses.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): transaction behavior when multiple sessions update concurrently.
# Checking Affected Row Counts to Detect Missing Data or Conflicts

In Spring Framework Data Access, an `UPDATE` or `DELETE` statement can execute validly as SQL yet **affect zero records**. If you only check that the method did not throw an exception, the application might reply “update succeeded” even though the record was already deleted, its state is no longer valid, or another transaction updated the data beforehand. The way to control this is to read the **affected row count** (*update count*) and compare it against the number of rows the business logic expects.

This lesson focuses on single-record updates, conditional updates, and **optimistic locking** in Spring JDBC and Spring Data JPA. The goal is to know when `0` means “not found”, when it can mean “conflict”, why `1` usually means success, and why you also need to handle counts greater than `1`.

## 1. Origin and meaning of row count

In Spring JDBC, `JdbcTemplate.update(...)` returns an `int` representing the number of rows the JDBC driver reports were affected by the update statement. For example:

```java
int affected = jdbcTemplate.update(
    "UPDATE orders SET status = ? WHERE id = ?",
    "PAID", 101L
);
```

`JdbcTemplate` **does not by default throw an exception when `affected == 0`**: the SQL is valid and ran successfully, only no rows satisfied the condition (or no rows were counted as changed under the driver's convention). Whether `0` is acceptable or must be turned into a business error is the application's responsibility.

| Result | Interpretation for an operation expected to update exactly one row | Common action |
| --- | --- | --- |
| `1` | Exactly one row updated according to the database/driver's reporting convention | Confirm success |
| `0` | No row matched the entire `WHERE` condition, or no change was counted by the driver | Determine whether the record is absent, condition unmet, or version stale |
| `> 1` | Multiple rows affected, violating the “one record” assumption | Throw error, roll back transaction, inspect `WHERE` and data constraints |

Distinguish the **affected row count** from the row count of `SELECT COUNT(*)`. Row count is the result of the executed DML statement itself; it is **not** the number of rows currently in the table, the number of rows read earlier, or the number of objects in the JPA persistence context.

### Expectations must come from business requirements

- Updating/deleting an entity by primary key: typically expect **exactly 1 row**.
- Transitioning state when the old state must be `PENDING`: expect exactly 1; `0` may be due to an already transitioned state, deletion, or wrong ID.
- Decrementing stock with a sufficient-quantity condition: `0` may mean the product is missing **or** stock is insufficient.
- Intentional bulk updates: multiple rows may be acceptable; compare against dedicated criteria rather than always forcing `== 1`.
- Idempotent deletion: the API contract may treat “already absent” as an acceptable outcome; ignoring `0` must be an intentional decision.

## 2. Why checking row count alone is not enough to detect conflicts

Suppose two requests both read order `id = 101` and both see `status = 'NEW'`.

```sql
UPDATE orders SET status = 'PAID' WHERE id = 101;
UPDATE orders SET status = 'CANCELLED' WHERE id = 101;
```

If both statements succeed sequentially, **both can return 1**, yet the second update overwrote the result of the first (*lost update*). Checking `affected == 1` only proves one row was updated matching the SQL condition; it **does not automatically detect** conflicts if the `WHERE` condition contains no information to recognize that the data changed.

A common solution is **optimistic locking**: store a `version` column, pass the version the caller read, and verify that version right inside `WHERE`. This is an **atomic check-and-update in a single SQL statement**.

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO orders (id, status, version)
VALUES (101, 'NEW', 4);
```

When the caller has read the order at version `4`, execute:

```sql
UPDATE orders
   SET status = 'PAID',
       version = version + 1
 WHERE id = 101
   AND version = 4;
```

- If row `101` is still at version `4`: one row matches, status is updated, version increments to `5`, row count is usually `1`.
- If another transaction already incremented version to `5`: `version = 4` no longer holds, row count is `0`.
- If `id = 101` was deleted: also `0`.

Typical concurrency timeline:

| Time | Request A | Request B | Data |
| --- | --- | --- | --- |
| T1 | Reads `id=101, version=4` | Reads `id=101, version=4` | `version=4` |
| T2 | `UPDATE ... WHERE id=101 AND version=4` → `1` | — | `version=5` |
| T3 | — | `UPDATE ... WHERE id=101 AND version=4` → `0` | Remains A's result |

B is notified of a conflict or stale version; it does not silently overwrite A. This mechanism operates on a condition checked by the database right at update time, without needing a `SELECT` before every `UPDATE`. A `WHERE status = 'NEW'` condition can also protect a specific state transition, but a `version` column is more general when multiple attributes can change.

## 3. Implementation with Spring JDBC: checking for exactly one row

The following example is a Java 17+ service class in a Spring Boot application with a configured `DataSource`, the `spring-boot-starter-jdbc` dependency, and the `orders` table above. The class can be placed at `src/main/java/example/orders/OrderStatusService.java`; this is a **component of a Spring application**, not a standalone program to run directly via `java OrderStatusService`.

```java
package example.orders;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.JdbcUpdateAffectedIncorrectNumberOfRowsException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderStatusService {
    private static final String UPDATE_SQL = """
            UPDATE orders
               SET status = ?,
                   version = version + 1
             WHERE id = ?
               AND version = ?
            """;

    private final JdbcTemplate jdbcTemplate;

    public OrderStatusService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void changeStatus(long orderId, long expectedVersion, String newStatus) {
        int affected = jdbcTemplate.update(
                UPDATE_SQL, newStatus, orderId, expectedVersion);

        if (affected == 0) {
            throw new OptimisticLockingFailureException(
                    "Order " + orderId
                    + " does not exist or has a different version");
        }

        if (affected != 1) {
            throw new JdbcUpdateAffectedIncorrectNumberOfRowsException(
                    UPDATE_SQL, 1, affected);
        }
    }
}
```

**Points to understand in the code:**

1. `UPDATE_SQL` includes the **identifying key** and **expected version**; it increments `version` directly in the database. Parameter order matches the three `?` placeholders: new status, ID, old version.
2. `affected == 0` is treated as the operation being unable to complete for the version supplied by the caller. The message deliberately says “does not exist **or** has a different version”, because from the row count **you cannot know for sure which cause occurred**.
3. `affected > 1` violates the “only one order” invariant and is represented by `JdbcUpdateAffectedIncorrectNumberOfRowsException` (the constructor takes the SQL, expected count, and actual count). With `id` as primary key this case cannot occur if the SQL keeps the right condition; the check is still useful to avoid missing bugs when the SQL changes.
4. `@Transactional` keeps related changes in a single transaction. Both exceptions above are unchecked exceptions, so under Spring's default rollback configuration, escaping the transaction-proxy-managed method rolls back the transaction. This is especially important if earlier write statements preceded this statement.
5. `JdbcTemplate` uses bound parameters, avoiding concatenating ID/status directly into the SQL statement.

**Service layer responsibility:** only signal a business error or data conflict. The HTTP/API layer then decides whether to return `404 Not Found`, `409 Conflict`, or `412 Precondition Failed` based on the API contract and additional evidence. Do not automatically return `404` for every `affected == 0` case when a version condition is present.

### When only detecting “does not exist” is needed

If the business requirement is only deleting a single ID and does not require detecting concurrent updates, the check can be simpler:

```java
int affected = jdbcTemplate.update(
        "DELETE FROM orders WHERE id = ?", orderId);

if (affected == 0) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}
if (affected != 1) {
    throw new IllegalStateException(
            "Expected one deleted row, got " + affected);
}
```

This is a **service snippet**, not a standalone Java class. Without a `version` column in `WHERE`, it does not detect whether someone else modified the row before deletion. If deletion needs to be controlled based on what was read, add `AND version = ?` and treat `0` as “does not exist or conflict”.

## 4. Handling a result of 0 properly

**`0` only confirms that the statement produced zero affected rows under the database/driver's convention.** The business meaning depends on the full `WHERE` clause and how results are counted.

| Update condition | Possibilities when result is `0` |
| --- | --- |
| `WHERE id = ?` | ID missing; some DBMSs/drivers also report `0` when updating to the exact same value |
| `WHERE id = ? AND version = ?` | ID missing; version changed; consider driver counting rules |
| `WHERE id = ? AND status = 'PENDING'` | ID missing or current status is no longer `PENDING` |
| `WHERE sku = ? AND stock >= ?` | SKU missing or insufficient stock |
| `WHERE id = ? AND deleted = FALSE` | Record absent or already soft-deleted |

If the API must distinguish `404` from `409`, you can query the current state **after receiving `0`** (e.g., look up by ID) for diagnostic information. However, state can still change between the two SQL statements depending on isolation level and locking; thus the follow-up query result should not be described as absolute proof of why the earlier update failed. Another API might choose a generic “no longer eligible for update” message and ask the client to reload.

**Do not check existence first and skip checking row count:** two separate `SELECT ... WHERE id = ?` and `UPDATE ... WHERE id = ?` statements create a window in which another transaction can modify or delete the row. Checking the row count directly from the conditional `UPDATE` is the core line of defense.

### Note on “matched rows” vs. “changed rows”

Some databases/drivers report *matched* rows, while others or other configurations report *actually changed* rows. For example, MySQL normally counts actually changed rows for `UPDATE`; with `CLIENT_FOUND_ROWS` it can count rows matching `WHERE`. Therefore:

```sql
UPDATE orders SET status = 'NEW' WHERE id = 101;
```

When the status is already `NEW`, the returned count can differ across configurations even though the ID exists. Incrementing `version = version + 1` in version-checked updates ensures the statement makes an actual change when matched, reducing this ambiguity. You must still verify behavior against the **actual database, JDBC driver, and datasource configuration**.

Do not treat the row count of an upsert, multi-table query, trigger, or cascade as if it always equals the number of *business entities* modified. Reporting rules for each construct can differ.

## 5. Spring Data JPA: two paths and key differences

### 5.1. Using `@Version` with managed entities

In JPA, the preferred approach when working with managed entities is declaring a version attribute:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class OrderEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;

    protected OrderEntity() {
    }

    // Other getters/setters omitted as this is a mapping illustration snippet.
}
```

When an entity is loaded and modified in a transaction, the JPA provider uses `@Version` to perform optimistic locking; if the data was changed by another transaction, the provider can throw `OptimisticLockException`, which Spring typically translates into an optimistic locking exception. **Detection time may be at flush or commit**, not necessarily immediately when calling `save(...)`. Do not manually increment the version in code updating a managed entity when the provider already manages `@Version`.

### 5.2. Using `@Modifying @Query` for direct updates

Spring Data JPA allows data-modifying query methods to return `int`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           UPDATE OrderEntity o
              SET o.status = :newStatus,
                  o.version = o.version + 1
            WHERE o.id = :id AND o.version = :expectedVersion
           """)
    int updateIfVersionMatches(
            @Param("id") Long id,
            @Param("expectedVersion") long expectedVersion,
            @Param("newStatus") String newStatus);
}
```

This method is a **component snippet in a JPA application** and assumes `OrderEntity` has the appropriately declared attributes. Call it from a `@Transactional` service and check `0`/`1`/`>1` as in the JDBC example.

Important notes:

- `@Modifying` bulk JPQL updates **bypass automatic dirty checking and version checking per managed entity**. Therefore, when choosing bulk updates for optimistic locking, the `o.version = :expectedVersion` condition and incrementing `o.version` must be written explicitly in JPQL (or handled via an appropriate provider mechanism).
- `flushAutomatically = true` flushes pending changes before running the bulk query; `clearAutomatically = true` clears the persistence context afterward to reduce the risk of reading stale entities. Clearing also detaches managed entities, so enable it only with an understanding of transaction flow and unflushed data.
- `@Modifying` applies to repository methods with a modifying `@Query`; it does not turn `save(...)` into a method that returns a row count.
- Do not mix updating `@Version` entities with bulk updates that skip version checks without a consistent policy: it is very easy to create write paths that silently overwrite each other.

## 6. Distinguishing exceptions from business errors

A syntactically valid SQL statement can still return `0`. Spring JDBC does not treat `0` as a natural SQL exception. The application needs to convert the result into an appropriate error when postcondition checks fail.

- `JdbcUpdateAffectedIncorrectNumberOfRowsException`: a clear choice when a specific row count is expected and the actual count differs. It belongs to `DataAccessException` and exposes `getExpectedRowsAffected()` and `getActualRowsAffected()`. It can be used for any case other than `1` if distinguishing causes is unnecessary.
- `OptimisticLockingFailureException`: a sensible signal for an operation with a stale version that can no longer apply; when the row count is `0`, still avoid claiming for certain whether the record exists.
- `IllegalArgumentException`, `IllegalStateException`, or a custom domain exception: used when the business layer wants to express “not found”, “invalid state”, or invariant violation. Choose a consistent convention for the API layer to map.
- With JPA managed entities, optimistic locking exceptions may surface at flush/commit; repository callers should not assume they will always receive an integer.

If business logic requires **all operations in a transaction to fail together**, let the appropriate exception escape the transaction boundary or explicitly mark rollback. By default, Spring rolls back on `RuntimeException` and `Error`, not on all checked exceptions. Avoid catching an exception and silently returning “OK”, as that can cause earlier writes to commit.

## 7. Detecting and handling conflicts in an API flow

A versioned update flow can be illustrated as follows:

```text
Client reads: id=101, status=NEW, version=4
       |
Client sends: id=101, status=PAID, expectedVersion=4
       |
Service: UPDATE ... WHERE id=101 AND version=4
       |
       +-- affected = 1  --> Success; version increments to 5
       |
       +-- affected = 0  --> Condition no longer matches:
       |                    missing or version/state changed
       |
       +-- affected > 1  --> Invariant violation; roll back and investigate
```

The API layer can handle this as:

| Identified situation | Illustrative response |
| --- | --- |
| ID genuinely does not exist per the API's lookup policy | `404 Not Found` |
| Record exists but `expectedVersion` is stale | `409 Conflict` |
| API uses HTTP conditional requests with `If-Match`/ETag and condition no longer holds | `412 Precondition Failed` |
| Multiple rows modified unexpectedly | Server error, rollback, log, and alert for investigation; do not return success |

When encountering a conflict, the client should reload the data and let the user decide whether to apply the change on the new version. **Do not automatically retry by fetching the new version and overwriting with the old values without reconciliation**, as doing so can intentionally overwrite someone else's update.

## 8. Cases requiring special consideration

### State-conditional updates

```sql
UPDATE orders
   SET status = 'PAID'
 WHERE id = ?
   AND status = 'NEW';
```

`0` can mean not found, already paid, cancelled, or another state. If business rules only allow the `NEW -> PAID` transition, this protects the transition condition right at the database. When multiple related attributes change, consider combining a version column for general conflict detection.

### Atomic inventory deduction

```sql
UPDATE inventory
   SET available = available - ?
 WHERE sku = ?
   AND available >= ?;
```

Pass the same quantity to deduct in the first and third parameters. `1` means the deduction applied to one matching SKU; `0` means the condition was not satisfied, either missing SKU or insufficient stock. `available >= ?` prevents negative stock under concurrent requests, provided the table has an appropriate SKU uniqueness constraint.

### Soft delete or idempotent operations

```sql
UPDATE orders
   SET deleted = TRUE
 WHERE id = ?
   AND deleted = FALSE;
```

If `0`, the record may already be soft-deleted or have never existed. For an API with a contract of “repeated deletion still succeeds”, `0` can be valid. For an API requiring an actual state transition, `0` must be reported explicitly.

### Batch update

`JdbcTemplate.batchUpdate(...)` typically returns an array of counts per statement. **Do not blindly sum or compare** because JDBC also has special values `Statement.SUCCESS_NO_INFO` (`-2`: executed successfully but row count unknown) and `Statement.EXECUTE_FAILED` (`-3`: statement failed in corresponding batch contexts). When you must ensure *each* update touched exactly one row, inspect each element and choose an appropriate transaction/driver strategy; never treat `-2` as “0 rows”.

## 9. Required tests for row count behavior

Write integration tests with **the same database type and driver as production**, especially when logic depends on affected row counts.

| Scenario | Setup | Expected result |
| --- | --- | --- |
| Success | `id=101` has `version=4`; update with `expectedVersion=4` | `affected=1`, new status, `version=5` |
| Stale version | After the case above, update again with `expectedVersion=4` | `affected=0`, previous change not overwritten |
| Non-existent ID | Update `id=999` with any version | `affected=0` |
| Concurrency | Two transactions use the same initial version | Only one conditional update wins; the other receives a conflict or related DB error |
| Invalid state | `WHERE status='NEW'` while row is `PAID` | `affected=0` |
| Wrong `WHERE` | Test on a table where multiple rows match an overly broad condition | `affected>1` and transaction rolls back |
| No value change | Update with the exact same old value, without incrementing version | Verify actual counting convention of DB/driver |

Example SQL verification on a **dedicated test database**:

```sql
INSERT INTO orders (id, status, version)
VALUES (202, 'NEW', 7);

UPDATE orders
   SET status = 'PAID', version = version + 1
 WHERE id = 202 AND version = 7;
-- Expected: 1 row; version becomes 8.

UPDATE orders
   SET status = 'CANCELLED', version = version + 1
 WHERE id = 202 AND version = 7;
-- Expected: 0 rows; status PAID and version 8 remain unchanged.

SELECT id, status, version FROM orders WHERE id = 202;
-- Expected row: (202, 'PAID', 8).
```

Comments after `--` are **expected outcomes** for testing, not copied stdout from a specific SQL tool. In automated tests, verify **database state after commit/rollback** as well, not just the return value from the service. For rollback cases triggered by `affected>1`, use a real transaction and confirm the changes were not committed.

## 10. Common mistakes and application checklist

| Implementation mistake | Consequence | Fix |
| --- | --- | --- |
| Ignoring `affected` after `JdbcTemplate.update` | Reports success even though no row was modified | Compare against expected business row count |
| Treating every `0` as “not found” | Hides version/state conflicts | Interpret according to full `WHERE` and API contract |
| Relying only on `affected == 1` without version | Fails to prevent lost updates | Add version or appropriate state condition |
| `SELECT` existence check then unconditional `UPDATE` | Race condition between the two statements | Check conditions directly in `UPDATE` and row count |
| Ignoring `affected > 1` | Can modify wrong rows and still return OK | Enforce keys/constraints; roll back on violation |
| Using bulk JPQL while forgetting version | Disables optimistic locking protection | Add `WHERE version` and increment version, or use managed entities |
| Catching errors inside a transaction and still returning success | Risks committing unwanted writes | Let unchecked exceptions escape the boundary or mark rollback |
| Auto-retrying on the new version without merging | Can overwrite another user's data | Require reload and conflict resolution |
| Assuming all databases count UPDATE identically | Misunderstands “no-op update” cases | Test the actual driver/configuration in use |
| Treating `-2` from batch as failure or 0 | Wrong conclusions | Handle `SUCCESS_NO_INFO` explicitly |

**Checklist before completing an update API:**

1. Does the `WHERE` clause include ID/unique key and necessary concurrency guard conditions?
2. Is the expected row count `0`, `1`, a range, or a business-meaningful set of values?
3. Are `0`, `1`, and `>1` handled separately without falsely assuming the cause?
4. Is `@Transactional` at the right boundary and do exceptions roll back when invariants fail?
5. Are there any write paths (bulk JPQL, native SQL, scheduled jobs) bypassing the version mechanism?
6. Have concurrent updates, no-op row counts, rollbacks, and real driver behavior been tested?

**Core principle:** row count is direct evidence of the **write statement just executed**. It becomes a tool for detecting missing data or conflicts when combined with a proper `WHERE`, version or state conditions, `0/1/>1` evaluation rules, and transaction management.

## References

- Spring Framework `JdbcTemplate.update(...)` (Java API): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework `JdbcUpdateAffectedIncorrectNumberOfRowsException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/JdbcUpdateAffectedIncorrectNumberOfRowsException.html
- Spring Data JPA, `@Modifying` query: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.modifying-queries
- Spring Framework, transaction rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- MySQL affected rows (`ROW_COUNT()`): https://dev.mysql.com/doc/refman/8.4/en/information-functions.html
- JDBC `Statement.executeBatch()` / `SUCCESS_NO_INFO`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html
# Lost updates and two users editing the same aggregate

When two users open the same aggregate at the same time, each can see the same initial state. If both edit and save nearly simultaneously, the later save can overwrite the earlier save's changes. This phenomenon is called a **lost update**.

In Spring Data JDBC, the common way to detect this situation is **optimistic locking** using a numeric property annotated with `@Version`. The version is stored on the aggregate root. When the repository saves the aggregate, Spring Data JDBC updates it only if the version in the database still equals the version the application read. If another transaction has saved earlier, the later operation fails with `OptimisticLockingFailureException`.

This lesson explains lost updates using a scenario where two users edit an order concurrently, how to enable `@Version`, how to handle conflicts at the application/API layer, and when pessimistic locking or stronger transaction isolation is needed.

## 1. What is a lost update?

Suppose an order has a status and a list of order lines:

~~~text
SalesOrder #500
    status = DRAFT
    version = 7
    lines:
        - BOOK-01, quantity = 2
        - PEN-02, quantity = 4
~~~

User A and User B both open order #500. Both receive the state at version 7.

- A changes the quantity of BOOK-01 from 2 to 3.
- B changes the quantity of PEN-02 from 4 to 5.
- A saves first.
- B saves later using the stale aggregate copy.

If the system does not detect that the data has changed since B read it, B can write the entire old state of the aggregate along with its own change. A's change disappears.

This is a lost update: a valid committed update is overwritten by another update based on stale data.

### 1.1. Simulating two users editing concurrently

~~~text
Time           User A                      User B
---------      ------------                ------------
T1             Read order #500
               version = 7

T2                                         Read order #500
                                           version = 7

T3             Change BOOK-01: 2 -> 3

T4                                         Change PEN-02: 4 -> 5

T5             Save aggregate
               Database receives A's change

T6                                         Save stale aggregate
                                           Database receives B's change

Result without version check:
    A's change can be overwritten.
~~~

In some designs, B updates only a single column, so A's change might remain intact. However, if B sends a full aggregate representation, or an UPDATE statement replaces the state of the entire aggregate, the risk of a lost update is clear. Writing child collections can also cause the other user's changes to be replaced.

### 1.2. Why is a transaction alone not enough?

`@Transactional` ensures that operations within a transaction follow commit/rollback boundaries. It does not automatically know that an in-memory object is stale compared to data another user just saved.

A transaction can execute completely validly according to SQL and still overwrite a previously committed change.

It is important to distinguish:

| Mechanism | What does it protect? |
|---|---|
| Transaction | Statements in a use case commit or roll back together |
| Foreign key / CHECK | Structural and value constraints in the database |
| Optimistic locking | Detects updates based on a stale version |
| Pessimistic locking | Prevents other transactions from modifying the locked data region |
| Isolation level | Defines what data a transaction can see and which anomalies the database must prevent |

Transactions are a necessary foundation, but to detect lost updates at the aggregate level, the application needs a conflict detection mechanism.

## 2. Optimistic locking in Spring Data JDBC

Optimistic locking assumes conflicts do not happen frequently. The application allows multiple readers to read data concurrently; when saving, it checks whether the data has changed since it was read.

Spring Data JDBC supports optimistic locking using a numeric property on the **aggregate root** annotated with `@Version`.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

import java.util.ArrayList;
import java.util.List;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    private SalesOrder() {
    }

    public static SalesOrder draft() {
        SalesOrder order = new SalesOrder();
        order.status = "DRAFT";
        return order;
    }

    public void changeStatus(String newStatus) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only draft orders can change status"
            );
        }

        this.status = newStatus;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

`@Version` must have a numeric type, such as `Long` or `Integer`. It is placed on the root because the version represents the state of the aggregate. Modifying a child component through saving the aggregate must also be coordinated with the root's version.

When creating a new aggregate, Spring Data JDBC initializes the version according to the framework's new-entity mechanism. For an existing aggregate, the version in the object is the version received when it was read.

## 3. How does Spring Data JDBC check the version on save?

Suppose the database currently stores:

~~~text
sales_orders
+----+---------+---------+
| id | status  | version |
+----+---------+---------+
| 500| DRAFT   | 7       |
+----+---------+---------+
~~~

Both A and B read version 7.

When A saves, Spring Data JDBC generates a conditional UPDATE equivalent to:

~~~sql
UPDATE sales_orders
SET status = :status,
    version = 8
WHERE id = 500
  AND version = 7;
~~~

If exactly one row is updated, the operation succeeded in checking the version. The version in both the object and the database is incremented.

After A commits:

~~~text
sales_orders
+----+---------+---------+
| id | status  | version |
+----+---------+---------+
| 500| ...     | 8       |
+----+---------+---------+
~~~

When B tries to save the object still carrying version 7, the conditional UPDATE is equivalent to:

~~~sql
UPDATE sales_orders
SET status = :status,
    version = 8
WHERE id = 500
  AND version = 7;
~~~

The database now has version 8, so no rows satisfy the condition. Spring Data JDBC detects that the operation updated zero rows and throws `OptimisticLockingFailureException`.

B's change is not saved as a successful update. The application can report a conflict, load the latest state, and ask the user to review it.

### 3.1. Version sequence

~~~text
Database version = 7

A reads version 7
B reads version 7

A save:
    WHERE id = 500 AND version = 7
    UPDATE succeeds
    version -> 8

B save:
    WHERE id = 500 AND version = 7
    0 row updated
    OptimisticLockingFailureException
~~~

The version acts as a change counter. The application does not need to compare every column to determine whether someone else has saved.

### 3.2. Version increments on save and is checked on delete

The Spring Data JDBC documentation also describes optimistic locking for delete operations: the framework checks the version when deleting, but does not increment the version because the record is removed.

This prevents a stale object from deleting an aggregate that another user updated after the object was read.

### 3.3. Version is not a timestamp

You should not use updatedAt as a version just because a timestamp appears to represent the most recent update.

Timestamps can have database/driver-dependent precision, two operations can receive the same timestamp, and timestamp update rules do not necessarily correspond to every write path. A numeric `@Version` property has clear semantics for optimistic locking.

You can store both version and updatedAt:

- version: conflict detection.
- updatedAt: displaying change history and auditing.

These two fields serve different purposes.

## 4. Why does a version on the root protect the entire aggregate?

In Spring Data JDBC, the aggregate root is the persistence boundary. Entities owned by the root are saved as part of the aggregate state.

Example:

~~~text
SalesOrder #500 (version 7)
    |
    +-- OrderLine #1
    +-- OrderLine #2
    +-- OrderLine #3
~~~

If A modifies OrderLine #1 and calls repository.save(order), saving the aggregate must also check the root's version.

If B has already saved any change on the same aggregate and the root version has incremented, A cannot continue saving based on the stale version.

This matters because conflicts do not only happen when two people edit the same column. They may edit two different order lines while still modifying the same aggregate. If business rules require the whole aggregate to be a consistent unit, a shared version at the root detects that someone saved earlier.

### 4.1. One aggregate, one version

| Change | Should the root version change when saving the aggregate? |
|---|---|
| Change order status | Yes |
| Change shipping address belonging to the order | Yes |
| Add order line | Yes |
| Edit order line quantity | Yes |
| Delete order line | Yes |
| Edit child entity saved inside the aggregate | Yes |

An owned child entity does not need an independent version just to protect normal aggregate save operations. The root version protects the entire aggregate update.

If a piece of data is managed as an independent aggregate, it can have its own version according to its own boundary.

## 5. Handling OptimisticLockingFailureException

Detecting a conflict is only half the job. The application must decide how to respond so users do not lose what they just entered.

Repository:

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

Application service:

~~~java
@Service
public class SalesOrderService {

    private final SalesOrderRepository repository;

    public SalesOrderService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public SalesOrder saveChanges(SalesOrder order) {
        return repository.save(order);
    }
}
~~~

When `repository.save(order)` detects a stale version, the exception can be handled at the application boundary or API exception handler.

REST API example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<ProblemDetail> handleOptimisticLocking(
            OptimisticLockingFailureException exception
    ) {
        ProblemDetail problem = ProblemDetail.forStatus(409);
        problem.setTitle("Concurrent modification");
        problem.setDetail(
                "The order has changed. Reload it and review your changes."
        );

        return ResponseEntity.status(409).body(problem);
    }
}
~~~

HTTP 409 Conflict is a reasonable choice for an API to indicate that the resource has changed and the current request cannot be applied to the stale version. An API can return 412 Precondition Failed when the client sends an `If-Match` condition that is no longer satisfied.

Do not return a generic 500 error for a recognized concurrent conflict. Also do not return success if the save was actually rejected.

### 5.1. Do not swallow the exception and return the stale object

Avoid this pattern:

~~~java
try {
    repository.save(order);
} catch (OptimisticLockingFailureException exception) {
    return order;
}
~~~

This misleads the caller into thinking the data was saved. The returned object may still contain stale state that does not reflect the database.

Let the conflict propagate to where it can be translated into a clear response, or converted into a business result with a conflict status.

### 5.2. Do not blindly retry with the same object

If a save fails because of a stale version, retrying save with the same object will typically fail again. The version in that object has not been updated to the latest version.

Even if you reload the new version and assign it to the old object, doing so can overwrite the other user's changes. You must load the latest state, reapply the user's intent on the new state, and re-run domain rules before saving.

## 6. Conflict resolution strategies

There is no single right way to merge every aggregate. The decision depends on the business meaning of the changes.

### 6.1. Ask the user to reload and confirm

This is the safest and clearest approach when two users edit fields that may conflict.

Workflow:

1. The API returns a conflict.
2. The client loads the latest aggregate.
3. Display the fields that changed.
4. The user reviews what they entered.
5. The user decides to reapply or discard their changes.

For example, A changes the order status to CONFIRMED while B changes the shipping address. Even though the two properties are different, confirming the order may change the rule governing whether the shipping address can be edited. The system must reapply domain rules against the new state.

### 6.2. Controlled merge

If the changes are business-independent, the application can merge them.

Example:

- A adds an internal note.
- B updates the contact phone number.
- The two fields have no dependency relationship.

A service can load the latest aggregate, reapply the intended change from the user's command, and save.

~~~java
@Transactional
public void addInternalNote(
        Long orderId,
        String noteText
) {
    SalesOrder latest = repository.findById(orderId)
            .orElseThrow();

    latest.addInternalNote(noteText);

    repository.save(latest);
}
~~~

This example illustrates the idea of reapplying a command onto the latest state. In practice, you also need to handle retry if another transaction saves before this new save.

Merging must be designed around business semantics. Do not automatically combine two values when they conflict, such as two users changing the selling price or order status.

### 6.3. Bounded retry for operations that can be safely reapplied

Some additive or independent operations can be retried after reloading the data. For example, an "add a tag" command can be reapplied if the domain model ensures tags are not duplicated.

Conversely, a "set total amount to 500" command cannot be arbitrarily reapplied after someone else changed a price.

If implementing retries:

- Limit the number of attempts.
- Reload the latest state on each attempt.
- Re-run domain methods and validation.
- Do not reuse the old aggregate object.
- Do not repeat external side effects outside the transaction, such as sending emails or charging money.
- Retry only when the command's semantics allow reapplication.

Do not retry indefinitely because it can create a loop when a resource is continuously updated.

## 7. Exposing version over an HTTP API with ETag and If-Match

When users edit data through a web UI, the GET request and PUT request are often minutes apart. A database transaction should not stay open while the user edits. Instead, send the version with the representation or package the version as an HTTP ETag.

Example response:

~~~http
HTTP/1.1 200 OK
ETag: "order-500-v7"
Content-Type: application/json

{
  "id": 500,
  "status": "DRAFT",
  "version": 7
}
~~~

When the client updates, it sends the ETag it received:

~~~http
PUT /orders/500
If-Match: "order-500-v7"
Content-Type: application/json
~~~

The server checks the version in the request. If the version has changed, it returns 412 Precondition Failed or a conflict response per the API contract.

ETag frees clients from having to invent timestamp comparison logic. It also allows caching and HTTP conditional requests to work with optimistic concurrency.

Make sure the ETag accurately represents the version of the aggregate. If any change inside the aggregate increments the root version, an ETag derived from that version can serve as a validator for the aggregate representation.

### 7.1. Do not trust the client-supplied version as ground truth

The client may send the version in JSON or a header, but the server must still use it as a conditional check against the database. Do not trust the version solely because it is present in the request.

A version is not a secret and does not replace authorization. It only helps detect that a client is acting on a stale version.

## 8. Optimistic locking and transaction boundaries

An aggregate modification flow typically consists of:

1. Read the aggregate.
2. Execute a domain method.
3. Save the aggregate.
4. Commit.

Write operations should run inside a short transaction:

~~~java
@Transactional
public void changeShippingAddress(
        Long orderId,
        Address newAddress
) {
    SalesOrder order = repository.findById(orderId)
            .orElseThrow();

    order.changeShippingAddress(newAddress);

    repository.save(order);
}
~~~

Do not open a transaction when the user loads the page and keep it open until the user clicks Save. A user may take many minutes to edit; long-lived transactions hold connections, may hold locks or snapshots, and degrade the ability to serve other requests.

Instead:

- GET loads the aggregate and returns the version.
- The client edits outside any database transaction.
- PUT/POST starts a short transaction.
- The server loads or receives the required data, checks the version, and saves.
- If the version does not match, return a conflict.

In some API designs, the command payload can include the expected version. The repository must still verify the actual version in the database.

### 8.1. Transaction rollback on conflict

When optimistic locking fails while saving an aggregate, the exception must cause the write transaction to roll back. If the service also wrote audit/outbox records in the same transaction, those operations must roll back as well.

By default, Spring rolls back on RuntimeException and Error. If the application translates the exception into a checked exception, configure rollback rules accordingly.

Do not catch the exception inside the transaction and continue committing partial steps. Once a concurrency error occurs, let the transaction end and handle the conflict at an outer boundary.

## 9. How does optimistic locking differ from pessimistic locking?

Optimistic locking does not lock rows while users read and edit. It only checks the version at write time.

Pessimistic locking asks the database to lock data so other transactions cannot modify the same data region while the lock is held.

| Criterion | Optimistic locking | Pessimistic locking |
|---|---|---|
| How it works | Checks version at write time | Locks data before modifying |
| Conflicts | Detected at save time | Competing transactions wait or fail |
| Cost when conflicts are rare | Low | Incurs lock overhead |
| Best suited for | Read-heavy workloads with rare conflicts | High contention or required serialization |
| Risk | Users must resolve conflicts | Deadlocks, timeouts, long-held locks |
| Scope | Aggregate version | Rows locked by the database |

### 9.1. SELECT FOR UPDATE

On databases that support this syntax, you can lock the root row before making changes:

~~~sql
SELECT id, version, status
FROM sales_orders
WHERE id = :orderId
FOR UPDATE;
~~~

Example using JdbcClient:

~~~java
@Transactional
public void updateOrderWithLock(Long orderId) {
    OrderLockInfo locked = jdbcClient
            .sql("""
                SELECT id, version, status
                FROM sales_orders
                WHERE id = :orderId
                FOR UPDATE
                """)
            .param("orderId", orderId)
            .query((rs, rowNum) -> new OrderLockInfo(
                    rs.getLong("id"),
                    rs.getLong("version"),
                    rs.getString("status")
            ))
            .single();

    // Check status, load/update the aggregate,
    // then save within the same transaction.
}
~~~

The result type can be declared as follows:

~~~java
public record OrderLockInfo(
        Long id,
        Long version,
        String status
) {
}
~~~

The lock exists only for the duration of the transaction. You must use the same datasource and transaction manager when combining lock queries with repository saves.

Pessimistic locks fit short operations with high contention. Do not hold a lock while calling an HTTP service, sending an email, waiting on a user, or processing a long-running task.

### 9.2. Does locking the root protect all child tables?

Locking the root is only effective if all competing write paths follow the same protocol. If another path updates a child table directly without locking the root or checking the version, it may not coordinate properly with the application's locking rules.

For aggregates, a useful convention is that every command modifying the aggregate must check/increment the root version or lock the root before modifying children.

## 10. Does transaction isolation replace @Version?

You should not assume that raising the isolation level replaces optimistic locking.

`@Transactional` defaults to the isolation level of the transaction manager/database. In many systems, the default is READ COMMITTED. At this level, two transactions can both read the same old version before one updates; if the UPDATE statement has no version predicate, the second operation can still overwrite data according to database semantics.

Stricter isolation levels can prevent certain anomalies or cause one transaction to fail, but exact behavior depends on the database.

For example, in PostgreSQL:

- READ COMMITTED: each statement sees data committed before the statement began; subsequent reads in the same transaction can see newly committed data.
- REPEATABLE READ: the transaction keeps a stable snapshot; certain concurrent updates can cause the transaction to fail with a serialization error.
- SERIALIZABLE: the database detects execution schedules not equivalent to any serial order and may roll back a transaction.

With PostgreSQL, REPEATABLE READ and SERIALIZABLE may require the application to retry the entire transaction when a serialization failure occurs. Do not retry only the final SQL statement; rerun the entire transaction from the beginning to obtain a fresh snapshot.

### 10.1. When is stronger isolation needed?

Stronger isolation is useful when an invariant depends on multiple rows or multiple aggregates and cannot be protected by the version of a single root.

For example: allowing a sale only if total reservations and remaining inventory satisfy a condition. Two transactions can both read the total quantity and both decide to allow the sale, even though each transaction only updates a different aggregate.

Solutions can include:

- Moving the invariant into an aggregate with an appropriate boundary.
- Using an inventory row as a synchronization point with a conditional update.
- Using database constraints.
- Locking related rows in a consistent order.
- Using SERIALIZABLE where appropriate along with retry logic.

`@Version` on an order cannot by itself protect a global invariant across multiple orders and a separate inventory record.

## 11. When is the root version not enough?

The root version protects saving the same aggregate through a persistence path that checks the version. It does not automatically protect SQL modifications that bypass the repository.

Example:

~~~sql
UPDATE order_lines
SET quantity = :quantity
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

This statement neither checks nor increments the version of sales_orders. Another repository save may not realize that the child was modified directly.

If a direct SQL mutation is needed, coordinate the root version within the same transaction:

~~~sql
UPDATE sales_orders
SET version = version + 1
WHERE id = :orderId
  AND version = :expectedVersion;
~~~

Check the affected row count. Continue modifying the child only when exactly one root row was successfully claimed. If the child update fails, roll back the version increment as well.

A Java example:

~~~java
@Transactional
public void changeLineQuantity(
        Long orderId,
        Integer lineNo,
        Integer quantity,
        Long expectedVersion
) {
    int claimed = jdbcClient
            .sql("""
                UPDATE sales_orders
                SET version = version + 1
                WHERE id = :orderId
                  AND version = :expectedVersion
                """)
            .param("orderId", orderId)
            .param("expectedVersion", expectedVersion)
            .update();

    if (claimed != 1) {
        throw new OptimisticLockingFailureException(
                "The order has changed"
        );
    }

    int changed = jdbcClient
            .sql("""
                UPDATE order_lines
                SET quantity = :quantity
                WHERE order_id = :orderId
                  AND line_no = :lineNo
                """)
            .param("quantity", quantity)
            .param("orderId", orderId)
            .param("lineNo", lineNo)
            .update();

    if (changed != 1) {
        throw new IllegalArgumentException("Order line not found");
    }
}
~~~

This is an illustrative pattern for direct SQL. You must add domain conditions such as order status, tenant, quantity limits, and other constraints. Every write path must follow the same version rule; if one write path skips the version, optimistic locking no longer protects the entire aggregate.

## 12. Distinguishing same-aggregate conflicts from cross-aggregate conflicts

Suppose two users edit two different orders:

~~~text
SalesOrder #500, version 7
SalesOrder #501, version 3
~~~

These two saves are independent if the business domain has no shared invariant between them. Order #500's version should not block updating order #501.

However, if both orders use a single-use coupon code, or consume limited inventory stock, the two aggregates may compete over a shared invariant.

| Scenario | Is the root version enough? |
|---|---|
| Two people edit the same order | Detectable if both save through a repository with @Version |
| Two people edit two independent orders | They do not need the same version |
| Two orders both purchase a SKU with 1 item left | Not enough if inventory is an independent aggregate/table |
| Two people both change a shipping address on one order | The order's version can detect the conflict |
| Two orders both use a single-use coupon | Must protect the shared coupon/invariant |
| A job updates a child directly while a request saves the aggregate | Not enough unless the job coordinates the root version |

Place concurrency control where the invariant actually lives. Do not use one aggregate's version to assume all related data in the system is locked.

## 13. Testing lost updates with integration tests

A unit test mocking the repository can verify how the application service reacts to an exception, but it does not prove that Spring Data JDBC generates an UPDATE statement with the right version predicate.

Integration tests against a test database are needed to perform two independent reads followed by sequential saves.

Conceptual example:

~~~java
@DataJdbcTest
class SalesOrderOptimisticLockingTest {

    @Autowired
    SalesOrderRepository repository;

    @Test
    void rejectsSavingAnAggregateLoadedBeforeAnotherSave() {
        SalesOrder initial = SalesOrder.draft();

        SalesOrder saved = repository.save(initial);

        SalesOrder first = repository.findById(saved.getId())
                .orElseThrow();

        SalesOrder second = repository.findById(saved.getId())
                .orElseThrow();

        first.changeStatus("CONFIRMED");
        repository.save(first);

        second.changeStatus("CANCELLED");

        assertThatThrownBy(() -> repository.save(second))
                .isInstanceOf(OptimisticLockingFailureException.class);
    }
}
~~~

This is an illustrative example; constructors, factories, and domain methods must match your project's actual model.

### 13.1. Cases to test

| Test case | Expected result |
|---|---|
| Save a new aggregate with @Version | Framework initializes the version |
| Read then save once | Version increments |
| Two objects read the same version, save the first | First save succeeds |
| Save the second object still holding the old version | Throws OptimisticLockingFailureException |
| Same root but modifying two different children | Still detects conflict via root version |
| Delete using an object with a stale version | Operation is rejected |
| Direct SQL modifying child with root version increment | Repository save with old version is rejected |
| Direct SQL without root version increment | Test demonstrates that path can bypass protection |
| Exception occurs midway through multiple writes | Entire transaction rolls back |
| API receives stale If-Match | Returns conflict response per API contract |

### 13.2. Testing true concurrency

A test that reads two objects and saves them sequentially is useful for verifying the version check. To test behavior when two threads/transactions truly run concurrently, use two independent transactions synchronized with a CountDownLatch or barrier.

Do not share a single transaction across both threads, as that does not simulate two independent clients.

The test should verify:

- Both transactions read the same initial version.
- Only one transaction saves successfully.
- The other transaction receives a conflict or serialization error depending on the database strategy.
- The final data reflects one successful update, not a silent overwrite state.

## 14. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Adding only @Transactional | Two transactions can still write based on the same stale data | Use @Version or an appropriate concurrency strategy |
| Placing @Version on a child instead of the root | Does not protect the whole aggregate via root version semantics | Place version on the aggregate root |
| Catching exception and returning the stale object | Client assumes the update succeeded | Return a clear conflict |
| Retrying with the same stale object | Version remains stale; conflicts keep happening or overwrite if version is manually patched | Reload and reapply the command in a controlled way |
| Raising isolation level without understanding the database | May still fail to enforce the invariant, or introduce serialization failures | Understand database semantics and implement retries |
| Direct SQL modifying child without incrementing root version | Repository save misses the out-of-band change | Coordinate version/lock in the same transaction |
| Keeping a transaction open while the user edits a form | Holds connections/locks for too long | Pass version across requests and use short transactions on save |
| Automatically merging all changes | May violate domain rules | Merge only when business rules confirm changes are independent |
| Using root version for cross-aggregate invariants | Fails to detect conflicts on shared resources | Synchronize at the aggregate/row/constraint that actually owns the invariant |

## 15. Workflow for designing safe aggregate updates

When a use case allows multiple users to edit an aggregate concurrently:

**Step 1 — Identify the aggregate boundary.** Which child entities belong to the same root? Which changes must be treated as an edit to the aggregate?

**Step 2 — Add a root version.** Use a numeric property with @Version on the aggregate root.

**Step 3 — Return the version to the client.** Include the version in the response or ETag so the client retains the version it read.

**Step 4 — Keep write transactions short.** Do not hold a transaction open while the user thinks or edits a form.

**Step 5 — Save through the repository.** Let Spring Data JDBC check the version and increment it within the same save.

**Step 6 — Handle conflicts.** Translate OptimisticLockingFailureException into a conflict response; reload the latest state when needed.

**Step 7 — Choose merge/retry deliberately.** Retry only when the command can be safely reapplied and domain invariants re-evaluated.

**Step 8 — Control every write path.** Direct SQL, batch jobs, and external tools must coordinate the version/lock if they modify the same aggregate.

**Step 9 — Protect cross-aggregate invariants.** Use constraints, atomic conditional updates, locks, or appropriate isolation.

**Step 10 — Test with two users.** Verify that no update is silently overwritten.

~~~text
Client A                  Application / Database                 Client B
--------                  ----------------------                 --------
GET order #500  --------> Load version 7
          <-------------- Order + version 7
                                                                  GET order #500
                                             Load version 7 <----
                                                                  <--- Order + version 7

Edit A
PUT with version 7 -----> UPDATE WHERE version = 7
                          Save success, version = 8

                                                                  Edit B
                          UPDATE WHERE version = 7 <------------- PUT with version 7
                          0 rows updated
                          OptimisticLockingFailureException
                          |
                          v
                     Return conflict
                                                                  <--- 409 Conflict

                                                                  Reload latest order
                                                                  Review / merge changes
                                                                  Submit with version 8
~~~

## 16. Self-check scenarios

**Scenario A — Two people editing the status**

A and B both read order version 5. A saves successfully and the version increments to 6. B saves the object with version 5. What happens when @Version is present?

**Hint:** B's UPDATE has the condition WHERE version = 5, updates zero rows, and Spring Data JDBC throws OptimisticLockingFailureException.

**Scenario B — Adding only @Transactional**

Two requests both read a stale version, each running in its own transaction. Is adding only @Transactional enough to prevent a lost update?

**Hint:** Not necessarily. Transactions protect atomicity; you need a version check or locking to detect/prevent concurrent updates.

**Scenario C — Two people editing two different order lines**

A changes the quantity of line 1, B changes the quantity of line 2, both belonging to the same aggregate. Can both save without conflict?

**Hint:** Under the root version model, the second save still conflicts because both are saving the same aggregate. To merge, you must load the latest state and reapply the independent change according to domain rules.

**Scenario D — Automatic retry**

After a conflict, the service loads the new aggregate and saves the old object with the new version. Is this approach safe?

**Hint:** Not automatically safe. The old object can overwrite newer changes. You must reapply the command's intent on the new aggregate and recheck invariants.

**Scenario E — Direct SQL**

A batch job updates order_lines directly. Does the aggregate repository save automatically know that a child changed?

**Hint:** Not if the batch job does not coordinate the root version. You must update the version or lock the root following the same protocol.

**Scenario F — Two aggregates sharing inventory**

Two different orders both order the last item of a product. Is @Version on each order enough to prevent overselling?

**Hint:** No. You need concurrency control at the inventory or shared invariant, such as a conditional atomic update on available stock.

## 17. Key takeaways

| Concept | Role |
|---|---|
| Lost update | A committed update is overwritten by a save based on stale data |
| Optimistic locking | Checks version on write without locking during reads |
| @Version | Marks a numeric version property on the aggregate root |
| OptimisticLockingFailureException | Signals that a save/delete did not match the current version |
| Aggregate root version | Protects aggregate saves, including child entity changes through the repository |
| @Transactional | Groups operations into a transaction; does not replace version checking |
| Pessimistic locking | Locks data so competing transactions must wait |
| SELECT FOR UPDATE | Example of locking rows inside a transaction |
| ETag / If-Match | Passes the read version over HTTP to detect stale requests |
| Conflict handling | Reload, review, merge, or controlled command retry |
| Direct SQL | Must coordinate version/locks when modifying the same aggregate |
| Cross-aggregate invariant | Requires synchronization at the resource or boundary actually shared |

**A lost update occurs when someone saves state based on stale data after another user has updated the same aggregate.** Spring Data JDBC addresses this with optimistic locking via @Version on the aggregate root: the first save increments the version, and a save using a stale version is rejected. The application must report conflicts clearly and only merge/retry when the user's intent can be safely reapplied. For direct SQL or invariants shared across multiple aggregates, add versioning, locking, or constraints wherever the data is modified.

## References

- [Spring Data Relational — Persisting Entities / Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): @Version, version checking on update/delete, and OptimisticLockingFailureException.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): isolation, propagation, and rollback behavior.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): semantics of Read Committed, Repeatable Read, Serializable, and serialization failures.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row-level locks and SELECT FOR UPDATE.
- [HTTP Semantics — Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests): ETag, If-Match, and conditional update requests.

# Ensuring Child Data Integrity During Direct Deletion

In Spring Data JDBC, the aggregate root manages the lifecycle of its child entities. When the application deletes a child row using direct SQL—for example via `@Modifying` or `JdbcTemplate`—the operation goes straight to the database and can bypass the aggregate root's domain behavior.

Direct deletion can be necessary when processing large datasets, performing bulk operations, or avoiding loading an entire aggregate just to remove one record. However, to keep data consistent, multiple layers must be protected simultaneously:

- **Referential integrity:** prevent orphan child records or foreign key violations.
- **Business rules:** delete only when the aggregate state and business conditions allow it.
- **Concurrency:** do not delete based on a stale version while another transaction is modifying the aggregate.
- **Application lifecycle:** handle auditing, events, caches, and dependent data.
- **Atomicity:** validation, version updates, and deletion must commit or roll back together.

This lesson uses an order-with-order-lines example to show how to perform direct deletion safely in Spring Data JDBC, when to use cascades, how to coordinate transactions and optimistic locking, and when operations should remain on the aggregate root.

## 1. Child Data and Types of Integrity

Suppose an order owns multiple order lines:

~~~text
SalesOrder (aggregate root)
    |
    +-- OrderLine #1
    +-- OrderLine #2
    +-- OrderLine #3
~~~

Each order line lives in its own table:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    PRIMARY KEY (order_id, line_no),

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(id),

    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_order_line_price
        CHECK (unit_price >= 0)
);
~~~

The foreign key `order_lines.order_id` ensures every line references an existing order. The composite primary key `(order_id, line_no)` distinguishes lines within the same order.

However, a foreign key only protects storage relationships. It cannot decide whether a confirmed order is allowed to have a line deleted, whether an order is allowed to have zero lines remaining, or who is authorized to delete a line.

Distinguish the layers of integrity:

| Layer | Example | Protection mechanism |
|---|---|---|
| Referential integrity | Line must belong to an existing order | Primary key, foreign key |
| Data validity | Quantity must be greater than 0 | CHECK, NOT NULL, column types |
| Domain invariant | Only draft orders may delete lines | Aggregate behavior, application service, SQL conditions |
| Concurrency integrity | Do not delete against a stale version | `@Version`, version predicate, transaction |
| Audit/side effects | Record who deleted the line | Audit table, outbox, callback, or trigger |
| Transactional integrity | Never increment version while aborting the delete | `@Transactional`, rollback |

A DELETE statement that succeeds in SQL is not necessarily valid in business terms. Safe design must identify every layer that needs protection.

## 2. How Does Direct Deletion Differ from Deleting via the Aggregate Root?

The standard approach in Spring Data JDBC is to load the root, invoke domain behavior, and save the aggregate:

~~~java
@Transactional
public void removeLine(Long orderId, Integer lineNo) {
    SalesOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                    new IllegalArgumentException("Order not found"));

    order.removeLine(lineNo);
    repository.save(order);
}
~~~

This allows the root to enforce invariants such as:

- The order must be in `DRAFT` status.
- The line must exist.
- The order must retain at least one line.
- An invoiced line cannot be deleted.

Spring Data JDBC persists aggregate state according to its persistence mechanism. For an existing aggregate, saving a collection may result in deleting and reinserting referenced entities to reflect the current state.

When deleting directly:

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

The database evaluates only the SQL conditions and constraints. It does not invoke `order.removeLine(...)` in Java.

| Aspect | Deleting via aggregate root | Direct deletion |
|---|---|---|
| Domain invariant checks | Can live in the root | Must be enforced separately |
| Loading full aggregate | Usually yes | Can be avoided |
| SQL control | Spring Data JDBC | Application writes SQL directly |
| Root `@Version` | Applied by Spring Data JDBC on save | Must be coordinated manually |
| Entity callbacks/events | Per repository lifecycle | Do not run automatically for rows deleted by direct SQL |
| Auditing and side effects | Can be handled in domain/service/callbacks | Must be organized separately |
| Bulk deletion | Can be costly to materialize aggregates | Batch SQL is usually more efficient |

Direct deletion is a separate write path. Treat it as a persistence use case that must reproduce the aggregate's necessary protections, not merely a shorter SQL syntax for the same domain behavior.

## 3. How Do Foreign Keys Protect Child Records?

Foreign keys are the first line of defense against orphan data. When deleting an order line, the database checks whether any other table references that line.

For example, a price-adjustment detail table referencing an order line by its composite key:

~~~sql
CREATE TABLE order_line_adjustments (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    adjustment_no INTEGER NOT NULL,
    reason VARCHAR(200) NOT NULL,

    PRIMARY KEY (order_id, line_no, adjustment_no),

    CONSTRAINT fk_adjustment_line
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines(order_id, line_no)
);
~~~

If an adjustment references the line, deleting the line can be rejected by the database. This is the desired behavior if adjustments must be preserved.

### 3.1. Choosing the Right `ON DELETE` Policy

A foreign key can define several actions:

| Policy | Behavior when referenced row is deleted | When appropriate |
|---|---|---|
| `RESTRICT` | Rejects deletion while child records exist | Dependent data must be kept |
| `NO ACTION` | Checks constraint per database semantics | Want database to block invalid references |
| `CASCADE` | Automatically deletes referencing records | Child records depend entirely on the parent |
| `SET NULL` | Sets child FK column to NULL | Optional relationship and nullable FK column |

Example cascading from an order line to its adjustments:

~~~sql
ALTER TABLE order_line_adjustments
    DROP CONSTRAINT fk_adjustment_line;

ALTER TABLE order_line_adjustments
    ADD CONSTRAINT fk_adjustment_line
    FOREIGN KEY (order_id, line_no)
    REFERENCES order_lines(order_id, line_no)
    ON DELETE CASCADE;
~~~

When an order line is deleted, the database automatically deletes adjustments belonging to that line.

Understand the direction of cascades: the constraint lives on the referencing table. `ON DELETE CASCADE` on `order_line_adjustments`'s FK fires when an `order_lines` row is deleted. A cascade from `sales_orders` to `order_lines` only runs when an order is deleted; it does not run when the application only deletes a single line.

### 3.2. Do Not Use `CASCADE` to Mask Broken Ownership

If a record is referenced by multiple independent aggregates, cascading deletes can destroy data outside the aggregate being deleted.

For example, a `Product` is referenced by many orders. Deleting an order should not delete the product. That relationship typically needs a `RESTRICT`/`NO ACTION` FK and ID references across aggregates.

Only use cascades when the child's lifecycle truly depends on the parent and deleting them together aligns with business rules.

### 3.3. `SET NULL` Can Create Meaningless Data

For owned child entities, setting the FK to NULL usually destroys the meaning of "which aggregate does this belong to". If an order line must belong to an order, the FK column must be `NOT NULL` and `ON DELETE SET NULL` should not be used.

`SET NULL` fits optional references better, such as a record that can continue existing after its link to an assignee is removed.

## 4. Direct Deletion of an Order Line with `@Modifying`

Spring Data JDBC supports direct write SQL using `@Modifying` with `@Query`.

Repository:

~~~java
package com.example.shop.order.repository;

import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        DELETE FROM order_lines
        WHERE order_id = :orderId
          AND line_no = :lineNo
        """)
    int deleteLine(
            @Param("orderId") Long orderId,
            @Param("lineNo") Integer lineNo
    );
}
~~~

`@Modifying` marks the query as a data-modifying statement rather than a query returning entities. The method returns `int` to receive the affected row count.

Example:

~~~java
int deleted = repository.deleteLine(100L, 2);

if (deleted == 0) {
    throw new IllegalArgumentException("Order line not found");
}
~~~

The deleted row count is an important signal:

- `1`: exactly one line was deleted.
- `0`: no line satisfied the condition; either it does not exist or does not belong to the specified order.
- Greater than `1`: review the `WHERE` condition and key uniqueness.

With a composite key `(order_id, line_no)`, the valid deleted count for one line is normally 0 or 1.

**Never omit the root ID condition.** Deleting by `line_no` alone can affect lines of other orders if `line_no` is only unique within a single order.

## 5. Checking Business State Directly in the `DELETE` Statement

If only `DRAFT` orders may have lines deleted, put the status check directly in SQL:

~~~java
@Modifying
@Query("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
      AND EXISTS (
          SELECT 1
          FROM sales_orders o
          WHERE o.id = order_lines.order_id
            AND o.status = 'DRAFT'
      )
    """)
int deleteDraftLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
~~~

This condition makes the database delete the line only if the order is still in `DRAFT` status when the statement executes.

However, adding `EXISTS` alone does not solve all concurrency issues. Another transaction could be changing the root's status or version concurrently. If the system requires strict protection between deleting a line and confirming the order, combine optimistic locking or lock the root row in the same transaction.

SQL predicates must include every critical business constraint the direct operation needs to protect. For instance, if an invoiced line cannot be deleted, check invoice status or related tables in the same statement or in a controlled transaction.

## 6. Wrapping Validation and Deletion in a Transaction

A direct deletion operation may comprise multiple steps:

1. Check permissions or state.
2. Update the root version to synchronize concurrency.
3. Delete the child record.
4. Write audit/outbox if needed.
5. Commit.

These steps must share the same transaction if they form a single atomic business change.

Service example:

~~~java
@Service
public class OrderLineCommandService {

    private final SalesOrderRepository repository;

    public OrderLineCommandService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deleteLine(Long orderId, Integer lineNo) {
        int deleted = repository.deleteDraftLine(orderId, lineNo);

        if (deleted != 1) {
            throw new IllegalStateException(
                    "Line does not exist or order cannot be changed"
            );
        }
    }
}
~~~

If the DELETE statement fails or the deleted row count is wrong, throwing a runtime exception rolls back the transaction under Spring's default configuration.

If you need to handle checked exceptions and still roll back, configure an appropriate `rollbackFor` policy.

Do not split checking status in one transaction and deleting in another. The status can change between the two moments, creating a race condition.

### 6.1. Same Transaction Manager and Same `DataSource`

`@Transactional` only protects operations participating in the same transaction manager. If deletion runs via `JdbcTemplate` and the repository uses the same `DataSource`/transaction manager, they can share the same Spring transaction.

If auditing writes to a separate database or external service, a JDBC transaction does not automatically guarantee cross-system atomicity. In that case, an outbox or suitable coordination mechanism is required.

## 7. Optimistic Locking During Direct Deletion

Spring Data JDBC uses `@Version` on the aggregate root to detect updates based on stale state.

Root example:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

When the repository saves the aggregate, Spring Data JDBC checks and updates the version under optimistic locking.

However, a `@Modifying DELETE` targeting `order_lines` directly does not automatically check `sales_orders`'s version. Without coordination, transaction A could delete a line while transaction B has already read the aggregate at the old version and is still modifying the order.

### 7.1. Race Condition Example

~~~text
Transaction A                       Transaction B
-------------                       -------------
Read order #100, version 4          Read order #100, version 4
                                    Change order status
                                    Save root -> version 5
Delete order_lines row
Commit
                                    ...
~~~

If transaction A does not check the version, it can delete the line based on stale state even though the order already moved to a non-editable status.

### 7.2. Conditional Version Update Before Deletion

One technique is to use an atomic UPDATE to check the root, increment the version, and claim the right to mutate the aggregate:

~~~java
@Modifying
@Query("""
    UPDATE sales_orders
    SET version = version + 1
    WHERE id = :orderId
      AND version = :expectedVersion
      AND status = 'DRAFT'
    """)
int advanceVersionForDirectMutation(
        @Param("orderId") Long orderId,
        @Param("expectedVersion") Long expectedVersion
);
~~~

Then delete the line:

~~~java
@Modifying
@Query("""
    DELETE FROM order_lines
    WHERE order_id = :orderId
      AND line_no = :lineNo
    """)
int deleteLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
~~~

Coordinating service:

~~~java
@Service
public class OrderLineCommandService {

    private final SalesOrderRepository repository;

    public OrderLineCommandService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deleteLine(
            Long orderId,
            Integer lineNo,
            Long expectedVersion
    ) {
        int claimed = repository.advanceVersionForDirectMutation(
                orderId,
                expectedVersion
        );

        if (claimed != 1) {
            throw new OptimisticLockingFailureException(
                    "Order changed, does not exist, or is not editable"
            );
        }

        int deleted = repository.deleteLine(orderId, lineNo);

        if (deleted != 1) {
            throw new IllegalArgumentException(
                    "Order line not found"
            );
        }
    }
}
~~~

Meaning of this flow:

1. The UPDATE succeeds only if the ID exists, the version still matches, and status is still `DRAFT`.
2. Updating the root row acquires a write lock on that row per database mechanics, serializing concurrent transactions touching the same root at the update point.
3. If the version does not match or status is invalid, no line is deleted.
4. If the line does not exist, the exception rolls back the version bump as well.
5. On commit, the root version has incremented so aggregate objects loaded at the old version cannot save successfully as if nothing changed.

This approach requires every other write path to respect the version too. If another SQL statement changes status or collections without bumping the version, optimistic locking cannot fully detect that change.

### 7.3. Do Not Reuse an Aggregate Loaded Before Direct Deletion as Current State

After direct SQL modifies a child and bumps the version, a previously loaded `SalesOrder` object still holds the old collection and old version. Do not continue mutating that object and calling `repository.save(order)`.

Discard the stale object and reload the aggregate in the next transaction/use case. If the application caches aggregates, invalidate or update the cache accordingly.

## 8. Pessimistic Locking and Lock Ordering

Another option is to lock the root before deleting the child. For example, in PostgreSQL:

~~~sql
SELECT id, version, status
FROM sales_orders
WHERE id = :orderId
FOR UPDATE;
~~~

`FOR UPDATE` holds a lock on the root row until the transaction ends. Other transactions trying to modify the same row must wait or handle lock errors according to database isolation/timeouts.

This is useful when the operation must read multiple business conditions before deciding to delete. However:

- Locking syntax is database-dependent.
- Transactions must remain short so locks are not held too long.
- Timeouts and deadlocks must be handled.
- Other write paths must use a compatible locking strategy.
- Never lock a root row and then call external services or wait for user input.

Whether using optimistic or pessimistic locking, establish a consistent lock order. For example, every aggregate mutation locks/checks the root first before modifying children. Consistent ordering reduces deadlock risk caused by two transactions locking tables in opposite order.

## 9. Deleting a Child That Has Its Own Children

Suppose an order line has multiple adjustment notes:

~~~text
SalesOrder
    |
    +-- OrderLine
            |
            +-- OrderLineAdjustment
            +-- OrderLineAdjustment
~~~

To delete an `OrderLine`, its adjustments must be handled according to the chosen policy.

### 9.1. Database Cascade

If adjustments have no meaning independently, you can declare the FK with `ON DELETE CASCADE`.

A single DELETE on `order_lines` deletes all adjustments referencing that line.

Pros:

- The database guarantees no orphan adjustments remain.
- No need to write multiple manual DELETE statements.
- Behavior applies across all SQL delete paths, regardless of caller code.

However, cascades perform only database actions. They do not invoke Java callbacks per adjustment, do not emit application events, and do not execute aggregate domain methods.

### 9.2. Manual Deletion in Dependency Order

If you need audit control or want to avoid cascades, delete child-before-parent:

~~~sql
DELETE FROM order_line_adjustments
WHERE order_id = :orderId
  AND line_no = :lineNo;

DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

Both statements must run inside the same transaction. If the second fails, the first must roll back.

For multi-level trees, delete from the leaves upward:

~~~text
DELETE grandchildren
        |
        v
DELETE children
        |
        v
DELETE parent row
~~~

Do not delete a parent before referencing FKs are handled, unless database cascades have been properly designed and tested.

## 10. Directly Deleting a Group of Child Records

Some use cases need to delete multiple lines at once, such as removing all draft lines of a draft order.

SQL:

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no IN (:lineNumbers);
~~~

You can use `NamedParameterJdbcTemplate` to bind a collection:

~~~java
@Repository
public class OrderLineSqlRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderLineSqlRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int deleteLines(Long orderId, Collection<Integer> lineNumbers) {
        if (lineNumbers.isEmpty()) {
            return 0;
        }

        String sql = """
            DELETE FROM order_lines
            WHERE order_id = :orderId
              AND line_no IN (:lineNumbers)
            """;

        return jdbc.update(
                sql,
                new MapSqlParameterSource()
                        .addValue("orderId", orderId)
                        .addValue("lineNumbers", lineNumbers)
        );
    }
}
~~~

Handle empty collections before building the SQL statement. Do not rely on how a driver/database interprets an empty list inside an `IN` clause.

When bulk-deleting:

- Check the total affected row count.
- Determine whether partial deletion is allowed or all lines must be deleted.
- Update the root version once according to policy.
- Write audit records per line or for the overall command, depending on requirements.
- Ensure FK cascade/restrict behavior for dependent tables.
- Use a transaction to roll back if an important step fails.

If you need to identify every deleted line individually, query the target IDs beforehand inside the same transaction or use `RETURNING` on databases that support it. Do not assume every database offers that syntax.

## 11. Physical Delete vs. Soft Delete?

Physical deletion is not always appropriate.

### 11.1. Physical Delete

~~~sql
DELETE FROM order_lines
WHERE order_id = :orderId
  AND line_no = :lineNo;
~~~

The row is removed from the table. Suitable when:

- Data is strictly transient.
- No history needs to be retained.
- There are no auditing or restoration obligations.
- Dependent references are cleanly handled.

### 11.2. Soft Delete

~~~sql
ALTER TABLE order_lines
    ADD COLUMN deleted_at TIMESTAMP NULL,
    ADD COLUMN deleted_by VARCHAR(100) NULL;
~~~

Instead of deleting the row:

~~~sql
UPDATE order_lines
SET deleted_at = CURRENT_TIMESTAMP,
    deleted_by = :actor
WHERE order_id = :orderId
  AND line_no = :lineNo
  AND deleted_at IS NULL;
~~~

Soft delete retains data for auditing or restoration. However, it introduces extra responsibilities:

- Every read query must filter out deleted records where appropriate.
- Unique constraints may need adjustment to allow recreating equivalent records.
- Reports must distinguish active from deleted data.
- FKs remain intact because the physical row is still present.
- Default aggregate mapping may still read soft-deleted rows if the loading query lacks an appropriate filter.

Do not treat soft delete as free. It changes data semantics and requires a consistent read/write convention.

## 12. Which Spring Data JDBC Behaviors Does Direct DELETE Bypass?

A modifying query runs direct SQL without going through standard aggregate save/delete processing. Consequently, the following behaviors do not occur automatically for each deleted row:

### 12.1. Domain Behavior and Invariants

There is no automatic call to `order.removeLine(lineNo)`. Rules such as order status, minimum line count, already issued invoices, or permission limits must be checked in the application service or safely expressed in SQL/transactions.

### 12.2. Entity Callbacks and Lifecycle Events

Direct SQL does not materialize deleted entities to invoke corresponding callbacks. Spring Data JDBC lifecycle events/callbacks do not run automatically for rows deleted via `@Modifying` or `JdbcTemplate`.

If auditing or events are needed, create them explicitly in the use case or use an appropriate database-level mechanism.

### 12.3. Optimistic Locking

A direct child DELETE does not automatically check the root's `@Version`. You must add a version predicate or lock the root in the same transaction.

### 12.4. Auditing

Root fields such as `lastModifiedAt` and `lastModifiedBy` do not update automatically merely because a child row was deleted directly.

If deleting a child counts as modifying the aggregate, update root auditing/version according to business rules.

### 12.5. Caches and Read Models

If the application caches aggregates, line counts, or totals, direct deletion can make caches and read projections stale. Invalidate/update caches after commit or publish events through an outbox.

### 12.6. Domain Events and External Notifications

If deleting a line triggers downstream work such as releasing reservations or updating inventory, a DELETE statement does not emit events automatically. Write an outbox record in the same transaction so a worker can dispatch notifications after commit.

## 13. Auditing and Outbox for Delete Operations

An audit record can store who deleted a line, when, and why:

~~~sql
CREATE TABLE order_line_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    reason VARCHAR(300),
    occurred_at TIMESTAMP NOT NULL
);
~~~

Inside the transaction:

1. Check root/version.
2. Write the audit record.
3. Delete the child.
4. Commit.

If auditing is mandatory, do not run audit logging post-commit as best-effort without retry mechanisms. If deletion succeeds and auditing fails, the system loses the trail of the operation.

For events sent to a message broker, use a transactional outbox:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

The application writes the outbox record in the same transaction that deletes the child. A separate publisher reads the outbox and sends events; if sending fails, it can retry without losing business events.

Do not call a message broker directly mid-transaction and assume sending and DELETE always commit together. A database transaction does not span a standard message broker.

## 14. Access Control and Tenant Boundaries

A DELETE statement must constrain both the target aggregate and the user's scope. In multi-tenant systems, `order_id` alone may not suffice if IDs are not guarded by tenant context.

Example:

~~~sql
DELETE FROM order_lines l
WHERE l.order_id = :orderId
  AND l.line_no = :lineNo
  AND EXISTS (
      SELECT 1
      FROM sales_orders o
      WHERE o.id = l.order_id
        AND o.tenant_id = :tenantId
        AND o.status = 'DRAFT'
  );
~~~

The tenant condition ensures the database deletes only lines belonging to an order in the specified tenant.

However, do not treat a client-supplied `tenantId` parameter as proof of authorization. Obtain the tenant from an authenticated security context and enforce authorization in the application layer. The SQL predicate acts as defense in depth against out-of-scope operations.

Also consider not revealing to the client whether a line does not exist or belongs to a different tenant if security policy requires hiding the difference.

## 15. Testing Integrity During Direct Deletion

Unit tests for services can verify row-count handling branches, but FK constraints and cascade behaviors must be tested against a real or compatible database.

Key scenarios:

| Scenario | Expected outcome |
|---|---|
| Deleting an existing child | Exactly one row deleted |
| Deleting a nonexistent child | Zero rows deleted; service returns appropriate error |
| Deleting a child not belonging to the specified root | Does not affect other orders |
| Deleting a child when root is already confirmed | Rejected |
| Child still referenced by FK with RESTRICT | Database rejects, transaction rolls back |
| Child has descendants with FK CASCADE | Descendants are deleted per policy |
| Version mismatch | Child is not deleted |
| Child deletion fails after bumping version | Transaction rolls back version too |
| Audit/outbox insert fails | Entire operation rolls back if in same transaction |
| Two transactions modify root concurrently | One detects conflict or waits per locking strategy |

### 15.1. Testing Rollback

For example, a use case bumps the version and then deletes a line. Intentionally pass a nonexistent `lineNo` so the DELETE returns 0 and the service throws an exception.

After the transaction rolls back, verify:

- Root version remains at its pre-operation value.
- Other children still exist.
- No incomplete audit/outbox records exist.
- No descendants were unexpectedly deleted.

This tests the atomicity of the entire sequence, not just an isolated DELETE statement.

### 15.2. Testing Concurrency

Use two independent transactions:

~~~text
A: read order #100, version 7
B: read order #100, version 7

A: advance version where version = 7 -> succeeds, version 8
B: save or advance version where version = 7 -> conflict
A: delete child -> commit
~~~

The test must confirm transaction B cannot write using the stale version after A modified the aggregate.

## 16. Common Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Deleting child by `line_no` alone | May delete lines from other orders | Always constrain both root ID and child key |
| Assuming FKs protect all invariants | Confirmed orders can still be mutated | Check domain state and business rules |
| Using `ON DELETE CASCADE` on all relationships | Cascading deletes beyond ownership | Cascade only along strictly dependent lifecycles |
| Deleting child while ignoring descendants | DELETE rejected by FK or orphan data remains | Cascade in the right direction or delete bottom-up |
| Checking state and deleting in separate transactions | Race condition if state changes between steps | Share one transaction and use version/lock control |
| Direct DELETE without bumping root version | Another transaction can save a stale aggregate | Conditionally update version or lock root |
| Reusing aggregate loaded before direct DELETE | Stale object graph and version | Reload aggregate and invalidate caches |
| Expecting `@Modifying` to trigger callbacks | Audits/events are not recorded | Write audit/outbox explicitly |
| Testing only that DELETE returns 1 | Misses FKs, cascades, rollbacks, and concurrency | Run integration tests against a database |
| Soft delete without query filtering | Deleted data still appears | Standardize read predicates and unique constraints |

## 17. Process for Designing a Safe Direct Deletion

When deleting child data with SQL, follow this sequence:

**Step 1 — Define the deletion scope.** Which root does the child belong to? Which columns make up the full identifying key?

**Step 2 — List references.** Which tables reference the child? Are there descendants or other aggregates referencing it?

**Step 3 — Choose the FK policy.** Use `CASCADE`, `RESTRICT`/`NO ACTION`, or `SET NULL` according to data lifecycle.

**Step 4 — Define invariants.** Which states permit deletion? Is there a minimum child count? Are there invoices, reservations, or external workflows?

**Step 5 — Choose a concurrency strategy.** Conditional version update or root lock; ensure every other write path follows the rule.

**Step 6 — Write narrowly scoped SQL.** Include root ID, child key, tenant, and necessary business conditions.

**Step 7 — Open a transaction.** Combine validation/version claim, audit/outbox, and DELETE into one transaction.

**Step 8 — Check the affected row count.** Distinguish not found, conflict, and disallowed state according to API policy.

**Step 9 — Synchronize side effects.** Invalidate caches, update read models, or dispatch outbox events after commit.

**Step 10 — Test against the database.** Verify FKs, cascade/restrict, rollback, version conflicts, and multi-row deletion.

~~~text
Child deletion request
       |
       v
Identify root + child key + tenant
       |
       v
Check FKs and descendants
       |
       v
Check business invariants
       |
       v
Claim root version / lock root
       |
       v
Write audit or outbox if needed
       |
       v
DELETE child (and descendants via FK)
       |
       v
Check affected row count
       |
       v
Commit transaction
       |
       v
Invalidate cache / handle events after commit
~~~

## 18. Self-Check Scenarios

**Scenario A — Deleting an order line**

An order has `order_id = 100`, and a line has `line_no = 2`. Why is a DELETE using only `line_no = 2` unsafe?

**Hint:** `line_no` is unique only within a single order. You must use both `order_id` and `line_no`.

**Scenario B — Adjustments referencing an order line**

An `OrderLine` has three adjustments. When deleting the line, what must the database do?

**Hint:** If adjustments belong to the line's lifecycle, you can use an FK with `ON DELETE CASCADE`. If history must be kept, use `RESTRICT` and archive/audit beforehand.

**Scenario C — Confirmed order**

The SQL DELETE satisfies FKs, but the order is already in `CONFIRMED` status. Should deletion be allowed?

**Hint:** FKs only protect referential integrity. You must enforce business invariants—block via a status predicate in SQL and concurrency control.

**Scenario D — Version mismatch**

The application loaded the order at version 4, while the database is now at version 5. Does a direct child DELETE detect the conflict automatically?

**Hint:** No. Direct DELETE must check or claim the root version within the same transaction.

**Scenario E — Post-delete auditing**

The application successfully deletes a child and then calls an HTTP service to write an audit log. The HTTP service fails. What happens?

**Hint:** The committed DELETE may lack an audit record. If auditing is mandatory, write the audit/outbox record inside the same database transaction.

**Scenario F — Aggregate cache**

A cached aggregate object has three lines. Direct SQL deletes one line. Does the cache update automatically?

**Hint:** No. You must invalidate or update the cache after commit and stop using the stale object graph.

## 19. Takeaways

| Component | Role |
|---|---|
| Foreign key | Prevents child records from referencing a nonexistent parent |
| `ON DELETE CASCADE` | Deletes referencing descendants when the parent is deleted |
| `RESTRICT` / `NO ACTION` | Blocks deletion while dependent data exists |
| `@Modifying` | Executes direct INSERT/UPDATE/DELETE via a repository |
| Affected row count | Confirms how many records were actually modified |
| `@Transactional` | Protects atomicity across checks, version updates, auditing, and DELETE |
| `@Version` | Optimistic locking when repositories save aggregates |
| Version predicate | How direct SQL coordinates concurrency |
| Audit/outbox | Records operations and synchronizes events |
| Soft delete | Preserves history, but requires consistent read/write conventions |
| Integration test | Verifies FKs, cascades, rollbacks, and concurrency against the database |

**Direct deletion is safe when the database protects references and the application protects business rules.** Foreign keys, cascades, and CHECK constraints prevent structurally invalid data; transactions paired with version/locks prevent acting on stale state; auditing and outboxes preserve essential trails. If a delete operation has to replicate too many aggregate invariants, consider moving it back into a domain method on the aggregate root.

## References

- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): modifying queries, `@Modifying`, `@Query`, and custom SQL.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate persistence, entity lifecycle, and optimistic locking.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, transaction boundaries, and rollback.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary keys, foreign keys, CHECK constraints, and referential actions.

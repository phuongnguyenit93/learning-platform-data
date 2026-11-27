# Coordinating JPA and JDBC for Specialized Operations in the Same Transaction

Spring Data JPA works well for CRUD operations on entities and their relationships. However, tasks such as bulk updates, database-specific SQL queries, stored procedure calls, or writing to auxiliary tables can often be written more cleanly and efficiently with JDBC.

You can combine JPA and JDBC within the same Spring transaction so changes commit or roll back together. The essential requirement is that both participate in the same transaction managing the same database. When mixing them, you must proactively manage when JPA flushes changes to the database and the state of entities held in the persistence context.

## 1. When Should You Combine JPA and JDBC?

Use JPA for entity-driven business logic:

- Loading entities and checking business state.
- Mutating properties of managed entities.
- Leveraging cascades, entity relationships, dirty checking, and optimistic locking.
- Persisting data aligned with the domain model.

Use JDBC for SQL needing direct control:

- Updating or deleting large numbers of records in a single SQL statement.
- Using CTEs, window functions, hints, or database-specific syntax.
- Calling stored procedures or interacting with legacy schemas not mapped as entities.
- Writing business audit logs, statistics tables, or auxiliary tables via simple SQL.
- Running reporting queries whose result structure does not fit entities.

For instance, an order-completion workflow might load and transition an `Order` using JPA, then insert a record into `order_audit` using JDBC. Both changes must succeed together.

Do not mix the two access mechanisms merely because you can. If an operation needs full cascades, entity listeners, auditing, or JPA version checks, consider handling it through JPA. JDBC fits when the benefits of direct SQL outweigh the state synchronization work the application must handle itself.

## 2. Requirements for Sharing a Single Transaction

In a Spring application, place the transaction boundary at the service layer using `@Transactional`. The service method coordinates both repository/JPA and JDBC operations.

For both technologies to share a transaction, ensure:

1. JPA and `JdbcTemplate` use the same `DataSource` and the same database.
2. Transactions are managed by a `JpaTransactionManager` bound to the corresponding `EntityManagerFactory`. In standard Spring Boot configurations with a single datasource and one JPA transaction manager, auto-configuration normally satisfies this condition.
3. `JdbcTemplate` receives that same `DataSource`. `JdbcTemplate` obtains connections via Spring's transaction synchronization (`DataSourceUtils`), allowing it to reuse the connection already bound to the active transaction.
4. Operations execute on the same thread and within the same transaction context. Never open an independent connection and call `commit()` manually.

When multiple datasources or multiple transaction managers exist, specify the manager explicitly, such as `@Transactional(transactionManager = "jpaTransactionManager")`. Specify the exact bean name and ensure the JDBC datasource belongs to that same transaction manager.

Dependency layout example:

```text
OrderCompletionService
  ├── OrderRepository ──> EntityManagerFactory ──┐
  └── JdbcTemplate ─────> DataSource ────────────┤
                                                 v
                                       Same transaction/database
```

If JPA and JDBC use two separate datasources, two independent transaction managers, or connections opened outside Spring's mechanism, standard `@Transactional` does not automatically create a distributed transaction. In that case, one operation could commit while the other rolls back. Ensuring atomicity across multiple resources requires a transaction mechanism such as JTA/XA, or an application-level pattern like outbox/saga depending on requirements.

## 3. Example: Updating an Entity with JPA and Writing an Audit Record with JDBC

Assume `Order` is a mapped entity and `OrderRepository` extends `JpaRepository<Order, Long>`. The entity has a business method `complete()` that transitions the order to a completed state.

The service can coordinate both technologies as follows:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityNotFoundException;
import jakarta.persistence.PersistenceContext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCompletionService {

    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    public OrderCompletionService(
            OrderRepository orderRepository,
            JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void complete(Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order " + orderId));

        // Entity is managed by the persistence context.
        order.complete();

        // Flush JPA changes to the database before running SQL that depends on them.
        entityManager.flush();

        int inserted = jdbcTemplate.update(
                """
                INSERT INTO order_audit (order_id, action, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                orderId,
                "COMPLETED"
        );

        if (inserted != 1) {
            throw new IllegalStateException(
                    "Failed to write audit record for order " + orderId);
        }
    }
}
```

In this example:

- `findById()` loads the entity inside the active transaction. The entity is managed by the persistence context.
- `order.complete()` updates state in memory. JPA dirty checking tracks this change; there is no need to call `save()` again on a managed entity.
- `entityManager.flush()` tells JPA to synchronize pending changes to the database. This does not commit the transaction.
- `jdbcTemplate.update()` executes the `INSERT` using the connection participating in the current transaction.
- If the JDBC statement fails and an exception exits the method, the transaction rolls back both the order status change made by JPA and the audit record.

The `?` placeholders are prepared statement parameters. Pass values as arguments to `update()`, never by concatenating input strings into SQL. For queries with many parameters, `NamedParameterJdbcTemplate` can make statements more readable.

The snippet assumes the `order_audit` table already exists, its columns match the `INSERT` statement, and `Order.complete()` conforms to the application's domain model. This illustrates transaction coordination, not a standalone runnable project without the corresponding entity, repository, and schema.

## 4. Why Pay Attention to Flush?

JPA typically defers sending SQL to the database until flush time. Mutating an entity in Java does not mean an `UPDATE` statement has already executed immediately.

This creates a common pitfall:

```java
Order order = orderRepository.findById(orderId).orElseThrow();
order.complete();

// JDBC runs before pending JPA changes are flushed.
Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ?",
        Integer.class,
        "COMPLETED"
);
```

If JPA has not flushed yet, the JDBC query may not see the new status. Whenever a JDBC SQL statement depends on recent JPA changes, call `entityManager.flush()` beforehand.

Points to remember:

- Flushing sends pending SQL statements to the database within the active transaction.
- Flushing does not end the transaction and does not make data visible to other transactions like a commit does.
- With the default `AUTO` flush mode, JPA may auto-flush before certain JPA queries. Do not rely on that automatic behavior to reason about ordering between a JDBC query and JPA mutations.
- Flushing can surface constraint or SQL errors earlier than commit time.
- Flushing may push multiple pending changes in the persistence context, not just the entity you just modified.

Therefore, flush only at points where ordering must be guaranteed or where the database needs to observe JPA changes before JDBC runs.

## 5. When JDBC Modifies Data Already Loaded by JPA

JDBC operates directly against the database and does not update entity objects sitting in the persistence context. If an entity was loaded by JPA and then modified by JDBC, the in-memory object may hold stale values.

Example:

1. JPA loads `Order` with status `PROCESSING`.
2. JDBC executes `UPDATE orders SET status = 'COMPLETED' WHERE id = ?`.
3. The `Order` object in the persistence context may still contain `PROCESSING`.
4. If the application keeps using that object, it may read stale data. A subsequent flush could even risk overwriting the JDBC update if the entity has pending changes.

How to handle this depends on scope:

- Use `entityManager.refresh(order)` to reload a specific entity from the database. Make sure there are no unflushed JPA changes you want to keep, because `refresh` reloads state from the database.
- Use `entityManager.clear()` to detach all managed entities, then reload needed entities. Before clearing, flush any JPA changes you intend to preserve; `clear` discards unflushed changes.
- If the entity is no longer needed in the same transaction, structure the flow to avoid reusing the stale object.

Do not call `refresh()` or `clear()` mechanically. Identify which changes are pending in the persistence context and which data needs to be reloaded.

## 6. JPA Mechanisms That JDBC Does Not Trigger Automatically

SQL executed via JDBC goes straight to the database. It bypasses JPA's entity lifecycle. Consequently, the following mechanisms do not run automatically for JDBC statements:

| Mechanism | When Updating with JDBC |
|---|---|
| Dirty checking | Does not apply; SQL must describe the changes to apply. |
| Cascades and entity associations | Does not automatically propagate operations to related entities. |
| Entity listeners and callbacks such as `@PreUpdate` | Not invoked merely because JDBC updates rows. |
| Entity-lifecycle Bean Validation | Does not run automatically; database constraints may still be enforced. |
| Spring Data JPA auditing | Does not populate `@LastModifiedDate` or `@LastModifiedBy` automatically. |
| Optimistic locking with `@Version` | JDBC SQL must enforce the version condition and increment the version column if needed. |
| Persistence context | Does not automatically synchronize already-loaded entity objects. |

In particular, if a table has a `@Version` column, JDBC update statements should check the current version and increment it according to application rules. Skipping this can prevent JPA entities holding old versions from detecting direct updates, or cause optimistic locking failures on the next flush.

Example of a version-checked update pattern:

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
```

After executing, inspect the affected row count. If it is `0`, either the row does not exist or the version changed; handle this according to your business concurrency rules.

If the application uses a JPA/Hibernate second-level cache or query cache, JDBC updates can also leave cached data stale. Proactively invalidate the relevant cache regions or avoid caching data modified directly via JDBC.

## 7. Rollbacks and Common Configuration Mistakes

By default, Spring rolls back a transaction when a transactional method exits with an unchecked exception (`RuntimeException`) or `Error`. Checked exceptions do not trigger rollback under default rules; when needed, declare it explicitly:

```java
@Transactional(rollbackFor = Exception.class)
public void performOperation() throws Exception {
    // JPA and JDBC operations in the same transaction.
}
```

Do not catch a JDBC exception and swallow it if the business rule requires a rollback. Rethrow the exception or mark the transaction rollback-only when handling errors locally while still needing to abort the entire transaction.

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| JPA rolls back, yet JDBC `INSERT` remains | JDBC used a different datasource/transaction manager or opened its own connection | Verify both use the same datasource and JDBC goes through `JdbcTemplate`/Spring. |
| JDBC does not see changes just made by JPA | JPA has not flushed yet | Call `entityManager.flush()` before the JDBC query that depends on those changes. |
| Entity still holds old values after JDBC `UPDATE` | Persistence context is not synchronized | Use `refresh()` or `clear()` at the right time, then reload. |
| Entity fails with optimistic locking error | JDBC SQL did not update the version column as expected | Check and increment version in SQL; verify affected row count. |
| Callbacks or auditing do not run | JDBC bypasses the entity lifecycle | Handle audit columns explicitly or perform the operation via JPA if lifecycle hooks are required. |
| `@Transactional` has no effect as expected | Self-invocation within the same object, wrong manager, or execution moved to another thread | Call via Spring bean proxy, specify the right transaction manager, and verify execution threads. |
| Checked exception does not roll back | Default rollback rules exclude checked exceptions | Configure `rollbackFor` appropriately. |

Spring transactions are normally bound to the current thread. Work handed off to another thread via `@Async`, an executor, or manual thread creation does not automatically join the active transaction. If asynchronous processing is needed, define separate transaction boundaries and pass the required data explicitly.

## 8. How to Test Atomicity

A useful integration test should prove that both operation types roll back together:

1. Prepare an order in its initial state along with corresponding audit data.
2. Call the transactional service: JPA updates the order, then JDBC writes the audit record.
3. Intentionally cause the JDBC operation to fail—for instance, by violating a constraint configured in the test environment.
4. After the transaction finishes, query the data back in a fresh transaction.
5. Verify the order remains in its initial state and no audit record was created.

You should also have a success test verifying both the order state and audit record are persisted. When testing, pay attention to the test framework's outer transaction: if an entire test runs inside a single auto-rolling-back transaction, verify data after the business transaction completes or configure the test appropriately so you do not confuse the test rollback with the service rollback.

## 9. Deployment Checklist

Before deploying a JPA + JDBC flow, confirm:

- [ ] The service defines a single `@Transactional` boundary encompassing all related operations.
- [ ] JPA and `JdbcTemplate` use the same `DataSource`, the same database, and the appropriate transaction manager.
- [ ] JDBC uses `JdbcTemplate` or `NamedParameterJdbcTemplate`, without manually committing a separate connection.
- [ ] `flush()` is called before JDBC SQL statements that must see pending JPA changes.
- [ ] Entities loaded prior to JDBC updates are refreshed, detached, or handled to prevent stale reads.
- [ ] JDBC SQL handles versioning, auditing, and rules normally managed by JPA if business rules require them.
- [ ] Exceptions propagate out or the transaction is marked rollback-only whenever rollback is required.
- [ ] Integration tests prove that JPA and JDBC changes commit together and roll back together.

Combining JPA with JDBC lets you leverage the entity model for business logic and direct SQL for specialized tasks. Consistency depends on sharing the transaction properly, controlling flush ordering, and proactively synchronizing the persistence context after JDBC updates.
# Update or Delete Queries with @Modifying

## 1. Why is @Modifying needed?

Spring Data R2DBC allows declaring SQL statements directly on repositories using `@Query`. For read queries, Spring Data executes the SQL and maps result rows into entities or projections. For `UPDATE` or `DELETE` statements, however, the main goal is to modify data in the database; the application usually needs to know that the operation completed and how many rows were affected.

The `@Modifying` annotation marks a repository method whose query modifies data. It tells Spring Data to execute the statement along the modifying-query path rather than handling the result like a normal entity read query.

Common use cases:

- Updating the status of multiple records matching a condition.
- Adjusting a few columns without loading entities and calling `save`.
- Physically deleting records that satisfy a condition.
- Performing soft deletes by updating a flag or deletion timestamp.
- Running a specific SQL statement that derived queries cannot express.

`@Modifying` is typically paired with `@Query` on reactive repositories. The SQL executes when the publisher is subscribed to, and the result is usually the affected row count or a completion signal with no value.

## 2. Structure of a @Modifying method

Example repository updating a task's status:

```java
import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface TaskRepository
        extends ReactiveCrudRepository<Task, Long> {

    @Modifying
    @Query("UPDATE task SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(
            @Param("id") Long id,
            @Param("status") String status);
}
```

Components:

- `@Query` holds the SQL statement the repository will execute.
- `@Modifying` indicates that the query modifies data.
- `@Param` links method parameters to named parameters in SQL.
- `Mono<Integer>` emits the number of rows reported as affected, then completes.

Table and column names inside `@Query` are the actual SQL names in the schema. Entity mapping metadata does not automatically rename tables or columns inside an explicitly written SQL statement. If the table is `task_item` or the column is `task_status`, the query must use those exact names.

Do not put `@Modifying` on an ordinary `SELECT` query. For read queries, omit the annotation and declare an appropriate entity/projection return type.

## 3. Updating data with @Modifying

Suppose the `customer` table has columns `id`, `email_address`, `status`, and `updated_at`. You can update a customer's status with:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Modifying
    @Query("UPDATE customer SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(
            @Param("id") Long id,
            @Param("status") String status);
}
```

Usage in a service:

```java
public Mono<String> changeStatus(Long id, String status) {
    return customerRepository.updateStatus(id, status)
            .map(rows -> rows == 0
                    ? "No customer was updated"
                    : "Updated " + rows + " customer(s)");
}
```

If `id` exists and the update affects one row, the publisher typically emits `1`. If no row matches, it may emit `0`. If the SQL statement fails, the publisher terminates with an error signal instead of emitting a row count.

The returned row count is reported by the database/driver. How databases define "rows affected" can vary: some engines report matched rows, while others distinguish rows whose values actually changed. If a statement assigns the same value that is already stored, verify the database engine and driver semantics instead of assuming the result is strictly 0 or 1.

### 3.1. Updating multiple rows

A single statement can update multiple records matching a condition:

```java
@Modifying
@Query("UPDATE task SET status = :target WHERE status = :source")
Mono<Integer> moveTasksToStatus(
        @Param("source") String source,
        @Param("target") String target);
```

This method does not load each `Task` into Java. The database executes one conditional UPDATE and returns the affected row count. This is suitable when changing the same column across many rows under a simple rule.

Service example:

```java
public Mono<Integer> archiveCompletedTasks() {
    return taskRepository.moveTasksToStatus("COMPLETED", "ARCHIVED");
}
```

For bulk updates, ensure the `WHERE` condition is sufficiently restrictive. A missing condition could update the entire table. If a statement has broad scope, consider testing it first in a test/staging environment and logging the affected row count in business logs.

## 4. Deleting data with @Modifying

You can declare custom DELETE statements:

```java
public interface TaskRepository
        extends ReactiveCrudRepository<Task, Long> {

    @Modifying
    @Query("DELETE FROM task WHERE status = :status")
    Mono<Integer> deleteByStatus(@Param("status") String status);
}
```

Usage:

```java
Mono<Integer> deleted = taskRepository.deleteByStatus("ARCHIVED");
```

The result reports the number of rows indicated as affected by the database/driver. This method is useful for conditional data cleanup or purging expired records.

### 4.1. Deleting by ID

If you only need to delete by ID, `ReactiveCrudRepository` already provides `deleteById(id)`:

```java
Mono<Void> deleteById(Long id);
```

This CRUD method returns `Mono<Void>` and does not supply the deleted row count. If business logic needs the affected count, a `@Modifying` query method can be appropriate:

```java
@Modifying
@Query("DELETE FROM task WHERE id = :id")
Mono<Integer> deleteAndReport(@Param("id") Long id);
```

### 4.2. Conditional deletes and foreign keys

When deleting a row referenced by other tables, the database may:

- Allow deletion if no referencing rows exist.
- Reject deletion due to a foreign key constraint.
- Delete child rows via `ON DELETE CASCADE`.
- Update foreign keys via behaviors such as `SET NULL`, if configured in the schema.

`@Modifying` does not automatically cascade relationships at the object-graph level like an ORM with a persistence context. The database enforces constraints and behaviors defined in the schema. Design foreign keys and operation ordering to fit your data model.

## 5. Return types and result semantics

For reactive modifying queries, you usually pick one of two return types:

| Return type | Meaning |
| --- | --- |
| `Mono<Integer>` | Emits the number of affected rows from execution, then completes |
| `Mono<Void>` | Only cares whether the operation completed normally or ended with an error |

Example when row count is needed:

```java
@Modifying
@Query("UPDATE customer SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(Long id, String status);
```

Example when row count is not needed:

```java
@Modifying
@Query("DELETE FROM audit_log WHERE created_at < :cutoff")
Mono<Void> deleteOldAuditLogs(OffsetDateTime cutoff);
```

Check the return types supported in your project's Spring Data R2DBC version. With reactive modifying queries, use an appropriate reactive wrapper rather than declaring a synchronous value and expecting the repository to execute eagerly.

`Mono<Integer>` can emit `0` and still complete normally. This differs from `Mono.empty()`: a numeric modifying query normally returns a row count, whereas empty means the publisher emits no element. If you need to know accurately whether the operation affected data, inspect the emitted numeric value.

With `Mono<Void>`, you cannot infer the affected row count. Completion only confirms the statement did not fail under the execution contract.

## 6. Comparing @Modifying with derived delete queries

Spring Data can derive delete operations from method names, for example:

```java
Mono<Void> deleteByStatus(String status);
```

Derived delete methods are recognized by Spring Data from the method name. Neither `@Query` nor `@Modifying` is needed if query derivation already supports the desired behavior.

Meanwhile:

```java
@Modifying
@Query("DELETE FROM task WHERE status = :status")
Mono<Integer> deleteAndCountByStatus(@Param("status") String status);
```

lets you write explicit SQL and select a return type supported by the modifying query API. This is useful when specific SQL conditions, database expressions, or affected row counts are required.

Choosing by scenario:

| Scenario | Choice |
| --- | --- |
| Deleting by simple properties supported by query derivation | Derived `deleteBy...` |
| Deleting with specific SQL or database expressions | `@Query` + `@Modifying` |
| Updating one or a few columns with explicit SQL | `@Query` + `@Modifying` |
| Returning affected row count for custom SQL | `@Query` + `@Modifying` with a supported numeric return type |
| Loading an entity, checking invariants, then modifying | `findBy...` + domain method + `save` |

## 7. Safe parameter binding

Named parameters keep SQL readable and avoid concatenating input values directly into statements:

```java
@Modifying
@Query("UPDATE customer SET status = :status WHERE email_address = :email")
Mono<Integer> updateByEmail(
        @Param("email") String email,
        @Param("status") String status);
```

Spring Data R2DBC binds parameter values via the driver's mechanism. Do not write:

```java
// Unsafe: input data is concatenated directly into SQL
String sql = "UPDATE customer SET status = '" + status + "' WHERE email_address = '" + email + "'";
```

String concatenation like this can introduce SQL injection and syntax errors when values contain quotes. Use named parameters and `@Param`.

### 7.1. Table or column names cannot be bound as values

Parameter binding is for data values, not SQL identifiers. For example, `SET :column = :value` does not parse `:column` as a column name. If dynamic column selection is needed, use a whitelisted set of identifiers in code and build SQL from controlled choices; never take table/column names directly from requests.

### 7.2. Null parameters

If a parameter can be `null`, clarify what the SQL means. The condition `column = NULL` is not equivalent to `column IS NULL` in SQL three-valued logic. To set a column to NULL, binding null in the SET clause may work if the schema permits it. To filter rows where a column is NULL, use an explicit `IS NULL` condition or design appropriate query branches.

Do not assume every driver version can infer the type of a null parameter in every context. When needed, use a typed bind API or separate SQL statements supported by your driver.

## 8. Updating multiple columns and SQL expressions

A modifying query can update multiple columns:

```java
@Modifying
@Query("""
    UPDATE customer
    SET status = :status,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = :id
    """)
Mono<Integer> changeStatus(
        @Param("id") Long id,
        @Param("status") String status);
```

In this example, `updated_at` is assigned using the database's timestamp. There is no need to pass a value from Java if the database is the authoritative source for update timestamps.

Arithmetic expressions can also be used in UPDATE:

```java
@Modifying
@Query("UPDATE inventory SET available = available - :quantity WHERE product_id = :productId AND available >= :quantity")
Mono<Integer> reserveInventory(
        @Param("productId") Long productId,
        @Param("quantity") Integer quantity);
```

This is a conditional statement that updates the quantity atomically in the database. If stock is insufficient, `available >= :quantity` fails to match and the affected row count can be `0`. This avoids the "read quantity, subtract in Java, then write back" pattern, which is prone to race conditions under concurrent requests.

The service can interpret the result:

```java
public Mono<Void> reserve(Long productId, int quantity) {
    return inventoryRepository.reserveInventory(productId, quantity)
            .flatMap(rows -> rows == 1
                    ? Mono.empty()
                    : Mono.error(new InsufficientInventoryException(productId)));
}
```

The example assumes `product_id` is unique, so at most one row is updated. If a statement can update multiple rows, checks must match the expected count and data model.

## 9. Bulk updates and the domain model

`@Modifying` executes SQL directly against matching rows. Spring Data does not load each entity to invoke its domain methods. This creates an important distinction between bulk updates and the load-modify-save pattern.

Bulk update example:

```java
@Modifying
@Query("UPDATE purchase_order SET status = 'EXPIRED' WHERE status = 'PENDING' AND expires_at < :now")
Mono<Integer> expireOrders(@Param("now") OffsetDateTime now);
```

This query can be efficient when transitioning many orders under a simple condition. However, it bypasses domain methods like `order.expire()` and invariants enforced only inside the aggregate root.

If status transitions depend on complex business rules, emit per-order domain events, or must update multiple objects inside an aggregate, consider loading the aggregate, calling its domain method, and saving via the repository. If bulk operations are required, express necessary invariants directly in SQL conditions/constraints or in a dedicated workflow.

### 9.1. Does not automatically trigger entity lifecycle like save

A modifying query is not equivalent to `findById` followed by `save`. Because Spring Data does not materialize individual entities:

- Entity domain methods are not invoked.
- Java objects already in memory are not automatically updated with new data.
- Entity optimistic locking is not automatically applied as when saving an entity with `@Version`.
- Callbacks/auditing attached to entity saving should not be assumed to run for each bulk-updated row.

If `updated_at`, `version`, audit columns, or domain events need updating, incorporate those changes explicitly in SQL or in the application workflow.

### 9.2. Optimistic locking with modifying queries

Suppose a table has a `version` column. When writing a manual UPDATE, include the version condition and increment the version if you want concurrent update protection:

```java
@Modifying
@Query("""
    UPDATE customer
    SET name = :name,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
    """)
Mono<Integer> renameIfVersionMatches(
        @Param("id") Long id,
        @Param("name") String name,
        @Param("expectedVersion") Long expectedVersion);
```

If the result is `1`, the statement matched both ID and version. If `0`, either the record does not exist or the version has changed. If you need to distinguish the two cases, run an additional query or design specific SQL output.

Do not add `version = version + 1` while forgetting `version = :expectedVersion`; otherwise, concurrent requests can still overwrite each other sequentially.

## 10. Soft deletes with @Modifying

Soft delete keeps rows in the database while marking them inactive. Suppose a table has `deleted_at`:

```sql
ALTER TABLE customer ADD COLUMN deleted_at TIMESTAMPTZ NULL;
```

Repository:

```java
@Modifying
@Query("UPDATE customer SET deleted_at = CURRENT_TIMESTAMP WHERE id = :id AND deleted_at IS NULL")
Mono<Integer> softDelete(@Param("id") Long id);
```

The `deleted_at IS NULL` condition prevents repeated operations from re-marking an already deleted record. Depending on the database, the row count on retries may reflect rows-affected semantics, while the condition still guarantees only undeleted rows match.

Read queries must filter `deleted_at IS NULL` if deleted records should be hidden. You can place this filter in derived queries, `@Query`, custom repositories, or a dedicated read model. `@Modifying` does not automatically inject soft-delete filters into other queries.

Soft deletes also affect unique constraints. For instance, requiring unique emails among active customers may need a partial unique index if supported by your database, or another uniqueness strategy. Do not simply add `deleted_at` and assume deleted records can be recreated with the same email.

## 11. Transactions with modifying queries

A single UPDATE/DELETE statement typically runs under the connection's transaction/autocommit behavior when no external transaction is managed. When a use case requires multiple data-modifying statements to form an atomic unit, define a reactive transaction in the application service.

Example:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Void> cancelOrder(Long id) {
        return orderRepository.markCancelled(id)
                .flatMap(rows -> {
                    if (rows == 0) {
                        return Mono.error(new OrderNotFoundException(id));
                    }

                    return auditRepository.recordCancellation(id);
                });
    }
}
```

This example assumes `markCancelled` and `recordCancellation` participate in the same reactive transaction manager and connection. If the second operation errors, the transaction can roll back the first change. If the audit record is written to a separate system, the R2DBC transaction does not cover that external system.

### 11.1. Require an appropriate transaction manager

Spring Data R2DBC uses `R2dbcTransactionManager` or a reactive transaction manager matching the `ConnectionFactory`. `@Transactional` must be applied within a Spring-managed context, and the publisher must be returned so the interceptor tracks its lifecycle.

Do not call `subscribe()` independently inside a transactional method and return a different publisher. A detached subscription may run outside the transaction context. Chain publishers using `flatMap`, `then`, or suitable operators.

### 11.2. Transactions do not replace WHERE conditions

Transactions group changes into an atomic commit/rollback unit, but do not make an UPDATE statement correct automatically. A statement missing a WHERE clause will still update the entire table inside the transaction and commit successfully.

Clearly specify target row scope, constraints, and any required locking. Transactions do not replace optimistic locking or authorization checks.

## 12. RETURNING clauses and returned row data

Some databases, such as PostgreSQL, support `UPDATE ... RETURNING` or `DELETE ... RETURNING` to return modified rows:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 10
RETURNING id, status;
```

However, `@Modifying` is designed to execute modifying queries and obtain affected row counts or completion signals; do not assume it will map `RETURNING` rows into entities like a read query.

If you need the entity after UPDATE/DELETE, use `DatabaseClient` to consume result rows or write an appropriate custom repository implementation:

```java
public Mono<Customer> activateCustomer(DatabaseClient databaseClient, Long id) {
    return databaseClient.sql("""
            UPDATE customer
            SET status = 'ACTIVE'
            WHERE id = :id
            RETURNING id, name, email_address, status
            """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)))
            .one();
}
```

This example uses PostgreSQL's `RETURNING` syntax and assumes a matching constructor. On other databases, use whatever mechanism the driver supports for returning generated/changed rows, or perform a read query after the update.

## 13. How do @Modifying and DatabaseClient differ?

Both APIs can execute data-modifying SQL, but at different levels of abstraction:

| Criterion | Repository `@Modifying` | `DatabaseClient` |
| --- | --- | --- |
| Where used | Repository methods | Persistence adapters, custom repositories, or appropriate services |
| SQL declaration | `@Query` on method | Calling `sql(...)` in code |
| Parameter binding | Method parameters and `@Param` | `.bind(...)` |
| Typical result | Row count or `Mono<Void>` as supported | Can retrieve `rowsUpdated()` or map result rows |
| Entity mapping | Does not load entities for modifying queries | Can map rows manually if the statement returns results |
| Flexibility | Well-suited for concise, fixed SQL | More flexible for controlled dynamic SQL, RETURNING, and custom mapping |

Choose `@Modifying` when the statement is short, stable, and row counts or completion signals suffice. Choose `DatabaseClient` or a custom repository when you need returned rows, complex query assembly, driver-specific APIs, or fine-grained mapping control.

## 14. Derived updates and modifying queries

Spring Data R2DBC supports derived queries for some operations like deletes, but do not assume any UPDATE statement can be generated from method names as desired. When you need to update a specific set of columns in SQL, `@Query` combined with `@Modifying` is the explicit way.

Example:

```java
@Modifying
@Query("UPDATE task SET completed = TRUE WHERE due_at < :now AND completed = FALSE")
Mono<Integer> completeOverdueTasks(@Param("now") OffsetDateTime now);
```

The method name `completeOverdueTasks` expresses business intent, while the SQL shows the exact update. Not every condition should be crammed into a long method name; for complex queries, `@Query` lets readers see the actual statement.

## 15. Common errors when using @Modifying

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| UPDATE runs but Java entity remains unchanged | Modifying queries only update the database, not in-memory objects | Re-read the entity or use RETURNING results via DatabaseClient |
| Method is not handled as a modifying query | Missing `@Modifying` on a `@Query` method | Add the annotation from the Spring Data R2DBC package |
| SELECT query errors or gives wrong result | Mistakenly put `@Modifying` on a read query | Remove `@Modifying` and declare an entity/projection return type |
| No row count received | Method returns `Mono<Void>` | Use a reactive numeric return type supported by your version |
| UPDATE alters too many rows | Missing or overly broad WHERE condition | Verify the condition, test on sample data, and check rows affected |
| Bind parameter does not work | `@Param` name mismatches named marker or wrong type | Align parameter names and Java/SQL types |
| SQL injection | Concatenating input data into SQL strings | Use bind parameters; whitelist identifiers if dynamic SQL is needed |
| Version does not increment or conflicts go undetected | Bulk UPDATE does not automatically apply entity optimistic locking | Add version condition and increment version explicitly |
| Audit timestamp is not updated | Bulk queries bypass callbacks/entity auditing | Set audit columns directly in SQL or use load-mutate-save |
| Delete fails due to foreign key | Row is referenced by other tables | Determine deletion order or appropriate FK behavior |
| Transaction does not cover all operations | A publisher is subscribed separately or uses a different transaction manager | Chain publishers and verify shared transaction context/ConnectionFactory |

## 16. Testing modifying queries

With reactive repositories, you can use `StepVerifier` to assert the emitted row count:

```java
StepVerifier.create(customerRepository.updateStatus(10L, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();
```

Testing zero matching rows:

```java
StepVerifier.create(customerRepository.updateStatus(-1L, "ACTIVE"))
        .expectNext(0)
        .verifyComplete();
```

For methods returning `Mono<Void>`:

```java
StepVerifier.create(taskRepository.deleteOldAuditLogs(cutoff))
        .verifyComplete();
```

Do not use `expectNext` for `Mono<Void>` because the publisher emits no items. If the SQL fails, `verifyComplete()` fails because the publisher terminates with an error signal.

### 16.1. Verifying data after updating

Tests should verify both the row count and the resulting data state:

```java
StepVerifier.create(customerRepository.updateStatus(customerId, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();

StepVerifier.create(customerRepository.findById(customerId))
        .assertNext(customer -> assertEquals("ACTIVE", customer.getStatus()))
        .verifyComplete();
```

These examples assume test fixtures have already created the customer. Run integration tests against the actual database and driver because SQL syntax, data types, rows affected, and transaction behavior can vary by engine.

### 16.2. Testing transaction rollback

If a use case runs a modifying query followed by a second operation that can fail, test whether the transaction rolls back the first change. The test must run under a real Spring transaction manager and consume the returned publisher; do not split subscriptions with `subscribe()` inside the test.

## 17. Choosing between modifying queries and load-mutate-save

Not every update should be written with `@Modifying`. The two approaches serve different purposes:

| Scenario | Suitable approach |
| --- | --- |
| Changing a column under a simple condition across many rows | `@Modifying` |
| Marking rows expired by a timestamp | `@Modifying` if per-entity behavior is not needed |
| Atomic conditional increment/decrement of quantities | `@Modifying` with SQL condition or DatabaseClient statement |
| Modifying an aggregate with multiple invariants | Load entity, call domain method, `save` |
| Requiring automatic entity optimistic locking | Load-mutate-save with `@Version` |
| Emitting domain events per aggregate | Load-mutate-save or dedicated event workflow |
| Returning the entity after UPDATE | `DatabaseClient` with RETURNING or re-query |
| Bulk updating and recording a summary audit | `@Modifying` paired with explicit auditing |

Bulk updates typically reduce round trips and skip entity mapping, but bypass per-object domain behavior. Load-mutate-save expresses domain rules clearly and can leverage optimistic locking, but requires reading and writing each aggregate and may consume more resources.

## 18. Checklist for building a safe modifying query

When adding an update or delete method with `@Modifying`, verify:

1. Is the SQL actually an UPDATE or DELETE, and does the target database support that syntax?
2. Does the method have `@Query` and `@Modifying` from the right packages?
3. Do named parameters in SQL match `@Param` annotations and data types?
4. Does the WHERE condition accurately constrain the target rows?
5. Does the caller need the affected row count (`Mono<Integer>`) or only completion (`Mono<Void>`)?
6. Does the bulk update bypass any invariants, auditing, versioning, or domain events?
7. Does the operation need to join a reactive transaction with other statements?
8. If returned rows are needed, should `DatabaseClient` be used instead of a modifying query?
9. Do integration tests verify row counts, post-update data, constraint errors, and rollbacks?

`@Modifying` provides an explicit way to declare UPDATE/DELETE queries via `@Query` in Spring Data R2DBC repositories. It lets the database apply changes directly and return the affected row count or a completion signal. When using it, carefully control SQL conditions, parameter binding, transactions, and domain rules that bulk operations do not enforce automatically. If a use case needs the modified entity back or must protect aggregate invariants, choose `DatabaseClient` or an appropriate load-mutate-save flow.

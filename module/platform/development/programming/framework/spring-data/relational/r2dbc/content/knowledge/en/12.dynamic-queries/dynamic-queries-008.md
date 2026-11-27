# Conditional Deletion and Impact Scope Control

Conditional data deletion directly affects data integrity and recoverability. In Spring Data R2DBC, an application can delete by ID via repositories, use `R2dbcEntityTemplate` with `Query` and `Criteria`, or write explicit `DELETE` statements using `@Modifying` or `DatabaseClient`.

When delete conditions are built dynamically from request filters, controlling the scope of affected data is critical. A skipped optional filter, an empty ID list, or a missing tenant condition can turn an operation meant to remove a few records into a bulk deletion. Therefore, enforce mandatory conditions, bind values safely, check affected row counts, and structure transactions appropriately.

## 1. Ways to Delete Data in Spring Data R2DBC

Choose an API based on the scope and complexity of the operation:

| Approach | When Suitable | Scope Notes |
|---|---|---|
| `deleteById(id)` | Deleting a single record identified by primary key | The ID must fall within the user's permitted scope. |
| `deleteAllById(ids)` | Deleting an identified set of IDs | Validate empty lists, list size, and ownership of all IDs. |
| `R2dbcEntityTemplate.delete(query, Entity.class)` | Deleting by `Criteria` that can be built dynamically | Uses entity mapping metadata and returns deleted row count. |
| `@Modifying @Query` | Fixed, explicit SQL statements with concrete conditions | Manually control `WHERE`, table/column names, and parameters. |
| `DatabaseClient` | Dynamic SQL whose condition count varies per request | Concatenate only fixed SQL fragments in code; bind all input values. |

`deleteAll()` spans the entire dataset of a repository. Use it only when business logic genuinely requires wiping everything in a controlled context, such as test data or a specialized administrative workflow. Never use it as a fallback for an endpoint receiving user filters.

## 2. Conditional Deletion with R2dbcEntityTemplate

`R2dbcEntityTemplate` lets you build a `Query` from `Criteria` and execute entity-based deletions. This works well when conditions are assembled from known properties in code and you want Spring Data to handle table/column mapping.

For example, deleting old completed orders belonging to a tenant:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import reactor.core.publisher.Mono;

public Mono<Long> deleteCompletedOrders(
        UUID tenantId, Instant createdBefore) {

    if (tenantId == null || createdBefore == null) {
        return Mono.error(new IllegalArgumentException(
            "tenantId and createdBefore are required"));
    }

    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("status").is("COMPLETED")
            .and("created_at").lessThan(createdBefore)
    );

    return template.delete(query, PurchaseOrder.class);
}
```

The condition has three parts:

- `tenant_id` restricts data to the current tenant.
- `status` restricts which order statuses can be deleted.
- `created_at` bounds the time window, preventing deletion of recent orders.

`template.delete(...)` returns a `Mono<Long>` representing the number of deleted rows. This value is useful for logging, auditing, and business responses. If the count is 0, no rows matched at execution time; this may mean the data did not exist, was already processed, or fell outside the allowed scope.

Column/property names in `Criteria` must align with your application's mapping metadata and schema. For columns mapped via `@Column` or a naming strategy, confirm how your Spring Data version resolves properties.

## 3. Building Dynamic Conditions from Optional Filters

A search API may let users pick statuses, time ranges, or data types. For deletions, do not make every condition optional without a minimum floor. If all filters are absent, the statement could delete every record in the table or across a tenant.

For example, a cleanup workflow requires a tenant and cutoff timestamp; status is an optional additional filter:

```java
public Mono<Integer> deleteOldOrders(
        UUID tenantId,
        Instant createdBefore,
        String status) {

    if (tenantId == null || createdBefore == null) {
        return Mono.error(new IllegalArgumentException(
            "A tenant and cutoff time are required"));
    }

    StringBuilder sql = new StringBuilder(
        "DELETE FROM purchase_order " +
        "WHERE tenant_id = :tenantId " +
        "AND created_at < :createdBefore");

    DatabaseClient.GenericExecuteSpec spec = databaseClient
        .sql(sql.toString())
        .bind("tenantId", tenantId)
        .bind("createdBefore", createdBefore);

    if (status != null && !status.isBlank()) {
        sql.append(" AND status = :status");
        spec = databaseClient.sql(sql.toString())
            .bind("tenantId", tenantId)
            .bind("createdBefore", createdBefore)
            .bind("status", status);
    }

    return spec.fetch().rowsUpdated();
}
```

This example uses two mandatory conditions to bound the scope. `status` merely adds an extra predicate. Values are bound via named parameters, so input strings are never concatenated directly into SQL.

When there are many optional filters, extract SQL construction and parameter binding into a helper to avoid duplication. Column names, operators, and SQL fragments must come from an allowlist in code. Table or column names cannot be bound as SQL values; never concatenate client-sent column names directly into statements.

### 3.1 Avoiding Empty Delete Conditions

Cases to reject or handle explicitly:

- Missing mandatory tenant/user scope.
- No filters provided when business rules require scoped deletion.
- Empty ID list accidentally converted into `deleteAll()`.
- Invalid time ranges, such as start date after end date.
- Filter containing values outside allowed statuses or types.
- Request asking to delete more records than permitted per operation.

Do not rely on a condition like `(:status IS NULL OR status = :status)` as your sole safeguard. When `status` is null, that predicate becomes true for all remaining rows. Moreover, binding `NULL` in some SQL expressions may require explicit parameter types. Adding predicates only when filters exist and validating mandatory conditions is easier to control.

## 4. Using @Modifying for Fixed DELETE Statements

When SQL conditions are static, delete queries can be declared directly on a repository:

```java
import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        DELETE FROM purchase_order
        WHERE tenant_id = :tenantId
          AND status = :status
          AND created_at < :createdBefore
        """)
    Mono<Integer> deleteOldOrders(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status,
        @Param("createdBefore") Instant createdBefore
    );
}
```

`@Modifying` marks the query as a data-modifying operation. The numeric return value indicates the number of rows reported updated/deleted by the database. Exact names and return types must match your project's Spring Data R2DBC API.

SQL inside `@Query` must use physical table and column names. Unlike `R2dbcEntityTemplate` which uses entity metadata, explicit SQL puts the author in charge of schema names, aliases, dialect, and parameters. Never place request SQL fragments into annotations or concatenate strings arbitrarily.

## 5. Deleting by a List of IDs

If the application has identified exact IDs to delete, use `deleteAllById` or an appropriate `IN` condition. Validate the list before calling:

```java
public Mono<Void> deleteSelectedOrders(
        UUID tenantId, Collection<Long> requestedIds) {

    if (tenantId == null || requestedIds == null || requestedIds.isEmpty()) {
        return Mono.error(new IllegalArgumentException(
            "Tenant and at least one order ID are required"));
    }

    if (requestedIds.size() > 200) {
        return Mono.error(new IllegalArgumentException(
            "Too many IDs in one request"));
    }

    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("id").in(requestedIds)
    );

    return template.delete(query, PurchaseOrder.class).then();
}
```

The tenant condition must still appear even when the client sends a list of IDs. Never assume IDs are secrets or that users can only send IDs they own. If using `deleteAllById`, the repository only receives IDs and is unaware of your application's tenant rules; in that case, verify ownership beforehand or use a query with a tenant predicate as shown.

Empty lists must be handled explicitly. Never turn an empty list into `deleteAll()`, and do not rely on how a database handles `IN ()` since syntax varies across engines.

## 6. Limiting Row Counts and Batch Deletion

A single delete statement can affect a vast number of rows, hold locks for a long time, generate heavy transaction logs, and overload the database. For large datasets, split work into bounded batches.

One technique is selecting a bounded set of IDs first matching the condition, then deleting those exact IDs within the same tenant scope:

```java
public Mono<Long> deleteOneBatch(
        UUID tenantId, Instant createdBefore) {

    Query selection = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("created_at").lessThan(createdBefore)
    ).sort(Sort.by("id")).limit(500);

    return template.select(selection, PurchaseOrder.class)
        .map(PurchaseOrder::getId)
        .collectList()
        .flatMap(ids -> {
            if (ids.isEmpty()) {
                return Mono.just(0L);
            }

            Query deletion = Query.query(
                Criteria.where("tenant_id").is(tenantId)
                    .and("id").in(ids)
                    .and("created_at").lessThan(createdBefore)
            );

            return template.delete(deletion, PurchaseOrder.class);
        });
}
```

In this example, each invocation processes at most 500 IDs. It can be invoked repeatedly on a schedule or in a loop until no matching IDs remain. Time and tenant predicates are rechecked in the delete statement to reduce the risk of deleting a record modified after selection.

If multiple workers clean up data concurrently, design work partitioning so they do not repeatedly select the same IDs. Depending on the database, use a claim/lock mechanism or dedicated processing status. `SELECT` followed by `DELETE` are two separate operations; if strict guarantees against concurrent updates are needed, choose appropriate isolation/locking and check database capabilities. Do not assume a `LIMIT` on a select query automatically limits an independent `DELETE`.

## 7. Previewing Scope Before Deleting

For high-impact operations, perform a preview step using `COUNT` or an ID query to report how many records are expected to be affected:

```java
Query query = Query.query(
    Criteria.where("tenant_id").is(tenantId)
        .and("status").is("EXPIRED")
        .and("created_at").lessThan(cutoff)
);

Mono<Long> affectedCount = template.count(query, PurchaseOrder.class);
```

This count can be used to require confirmation above a threshold, record audits, or switch to batch execution. However, `COUNT` and `DELETE` are two separate statements. Data can change between the two instants; thus a preview count is not an exact guarantee of how many rows will be deleted.

If a hard cap on row count is needed, select IDs in a bounded batch and delete that exact ID set. If checking and deleting must act as one consistent unit, use transactions and appropriate database locking/isolation. Even inside a transaction, default isolation levels may not prevent all concurrent changes or phantom rows.

## 8. Transactions and Consistency

A deletion may entail multiple changes: removing child rows, writing audit logs, updating job statuses, or publishing events after commit. If database changes must succeed or fail together, place them in a reactive transaction.

Example with a service returning `Mono`:

```java
@Transactional
public Mono<Long> deleteExpiredOrders(UUID tenantId, Instant cutoff) {
    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("created_at").lessThan(cutoff)
    );

    return template.delete(query, PurchaseOrder.class)
        .flatMap(deleted -> auditRepository
            .recordDeletion(tenantId, "EXPIRED_ORDERS", deleted)
            .thenReturn(deleted));
}
```

In reactive applications, transaction context flows through the reactive chain. The method must return a publisher so Spring can manage the transaction; never call `block()` inside this flow. Configuration must include a reactive transaction manager paired with the `ConnectionFactory`, and operations must use connection infrastructure participating in the same transaction.

If audits are written to an external system outside the database, a database transaction cannot automatically make external writes commit/roll back together. For events emitted after commit, consider the outbox pattern or suitable synchronization mechanisms. Never publish a "deleted" notification before the transaction commits successfully.

## 9. Foreign Keys, Aggregates, and Cascades

Deleting a row can be constrained by foreign keys or affect related rows. Define the handling strategy before running the statement:

- **RESTRICT/NO ACTION:** database rejects deleting a parent row while child rows reference it.
- **ON DELETE CASCADE:** database automatically deletes child rows via foreign key constraint.
- **SET NULL:** database sets child foreign keys to `NULL`, if schema permits.
- **Explicit deletion:** application deletes related rows in order inside a transaction.

Do not assume Spring Data R2DBC traverses an entire object graph and cascades deletes like traditional ORMs. Actual deletion behavior depends on issued statements, aggregate mapping, and database constraints. With `@MappedCollection`, understand how Spring Data manages aggregate members when saving or deleting the root; for independent aggregates, handle them per separate business rules.

Before deleting parent data, check relations for child records, transaction history, documents, or data subject to retention policies. Avoid database-level cascades if business rules require preserving historical records or separate auditing per data type.

## 10. Hard Delete, Soft Delete, and Audit Trails

**Hard delete** removes rows from the table. This fits expired retention periods, temporary data, or policy-mandated erasure. Consider backups, logs, read replicas, caches, and downstream systems because deleting from one table does not remove every copy of the data.

**Soft delete** keeps the row but marks it inactive, such as `deleted_at` or `active = false`:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET deleted_at = :deletedAt
    WHERE tenant_id = :tenantId
      AND id = :id
      AND deleted_at IS NULL
    """)
Mono<Integer> markDeleted(
    UUID tenantId,
    Long id,
    Instant deletedAt
);
```

Soft deletes require consistent conventions across all read queries, unique constraints, reports, and cleanup jobs. If repositories do not automatically filter `deleted_at`, ordinary queries can still return soft-deleted rows. Include that condition in queries or build a shared abstraction.

For both hard and soft deletes, record necessary audit details such as actor, timestamp, reason, request/correlation ID, and impact scope. Avoid logging unnecessary sensitive data. Audit logs should be written inside the transaction when consistency with the database operation is required.

## 11. Access Control and Preventing Accidental Deletion

Deletion conditions must be determined server-side from authenticated identity and permissions. Do not trust client-supplied `tenantId`, `ownerId`, or data scopes when the server can obtain them from the security context. If a request supplies IDs, the server must still verify those IDs belong to the caller's scope.

Useful principles:

1. Always include tenant/owner conditions in statements when data is partitioned by tenant or user.
2. Require at least one additional bounding predicate for bulk delete operations.
3. Permit only filter fields and operators in the application's allowlist.
4. Bind values instead of concatenating SQL strings from inputs.
5. Limit ID counts and rows per batch.
6. Provide preview/count or confirmation steps for large-scope administrative actions.
7. Audit actor, reason, and actual affected row count.
8. Consider soft delete or recovery workflows if business needs reversibility.

Never rely solely on hiding a delete button in the UI. Permissions must be enforced at the service/API layer and scope conditions must live inside the database query.

## 12. Version-Conditional Deletion to Prevent Concurrent Overwrites

If an entity uses optimistic locking with a `@Version` field, entity-based updates may verify the version. For hand-written `DELETE` statements, do not assume the framework automatically injects version checks into custom SQL.

When you need to ensure deletion happens only if the record has not changed since the user read it, add version to the predicate:

```sql
DELETE FROM purchase_order
WHERE tenant_id = :tenantId
  AND id = :id
  AND version = :expectedVersion
```

If the deleted row count is 0, the record may not exist, may belong to another tenant, or its version changed. The service must decide how to surface an appropriate error without leaking another tenant's data through detailed error messages.

This is statement-level concurrency control. If an operation must verify multiple business conditions before deleting, evaluate transactions, isolation, and locks to avoid another transaction mutating data between the check and the delete.

## 13. A Safe Deletion Workflow

A conditional deletion service can follow this sequence:

1. Authenticate caller and resolve tenant/owner from the security context.
2. Validate inputs, including IDs, timestamps, statuses, and allowed condition lists.
3. Require scope-bounding predicates; reject requests lacking minimum conditions.
4. Build `Criteria` or SQL using fixed fragments and bind all values.
5. For large operations, preview counts or select IDs in bounded batches.
6. Execute deletes inside a reactive transaction when coordinating multiple database changes.
7. Read the affected row count and write audit logs after success.
8. Emit events post-commit or use an outbox to synchronize external systems.
9. Monitor execution times, deleted row counts, constraint errors, and threshold violations.

For example, when purging expired orders, the predicate `tenant_id = ... AND created_at < ...` establishes the main scope; status can narrow it further. When deleting by ID, the tenant predicate remains enforced. For large datasets, select IDs in batches and delete again using both IDs and scope conditions. These layered safeguards ensure delete statements reflect business intent and minimize unintended impact.

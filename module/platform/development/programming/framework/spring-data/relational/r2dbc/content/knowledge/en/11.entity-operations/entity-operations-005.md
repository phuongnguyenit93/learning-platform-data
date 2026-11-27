# Deleting by Entity or Condition

In Spring Data R2DBC, a delete operation can start from a loaded entity, from an entity's identifier, or from a query condition. How you choose to delete affects the number of database round-trips, the ability to verify data versions, the affected row count, and how the application handles foreign key relationships.

If you already have an entity and want to delete that exact entity, you can use `ReactiveCrudRepository.delete(entity)` or `R2dbcEntityTemplate.delete(entity)`. If you only have the ID, `deleteById(id)` avoids loading the entity beforehand. If you want to delete multiple rows matching a condition, `R2dbcEntityTemplate` with `Query`/`Criteria` or a SQL `DELETE` via `DatabaseClient` is generally more suitable than loading every entity and deleting them one by one.

It is important to understand the difference between deleting a single entity and deleting by condition. Entity deletion can leverage the identifier and version field to enforce optimistic locking. Conditional bulk deletion usually executes directly in the database without loading individual entities into the application and without applying per-row version checks.

## 1. Three Ways to Specify Data to Delete

A delete operation typically identifies rows to remove in one of three ways:

| Identification Method | Common API | When Suitable |
|---|---|---|
| Existing entity | `repository.delete(entity)` or `template.delete(entity)` | Entity is already loaded, must delete that exact object, and may need `@Version` check |
| Identifier | `repository.deleteById(id)` | Only the ID is known, no need to read data before deleting |
| Condition | `template.delete(Type.class).matching(query).all()` or SQL `DELETE` | Deleting multiple rows by criteria without materializing each entity |

For example, a `person` table might map to an entity like this:

```java
@Table("person")
public record Person(
    @Id Long id,
    String firstname,
    String lastname,
    String status,
    @Version Long version
) {}
```

In this example, `id` is the identifier and `version` is used for optimistic locking. Depending on the schema and business rules, an application may delete by ID, by loaded entity, or delete all users in a given status.

## 2. Deleting by Entity with ReactiveCrudRepository

`ReactiveCrudRepository` provides `delete(T entity)` returning `Mono<Void>`. The application passes the entity to delete:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {
}
```

```java
@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    public Mono<Void> delete(Person person) {
        return repository.delete(person);
    }
}
```

This operation fits when the entity has already been loaded and the business layer needs to apply rules before deleting. For instance, the service might check account status, caller permissions, or business preconditions before calling `delete`.

Entity deletion operates based on the entity's identifier; do not assume Spring Data compares every Java property against database columns to locate the row. If the entity has `@Version`, the version value can also be included in the delete predicate to detect data modified since the entity was read.

`Mono<Void>` represents operation completion or error emission. It does not return the count of deleted rows. If business logic needs to know whether any row was actually affected, use an API that returns row counts such as `R2dbcEntityTemplate` or `DatabaseClient`.

### Deleting an Entity After Loading It

```java
public Mono<Void> deletePerson(Long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(new PersonNotFoundException(id)))
        .flatMap(repository::delete);
}
```

This flow performs two operations: reading the entity, then deleting it. It is useful when status or authorization checks depend on current data. If you only need to delete by ID without inspecting the entity, call `deleteById(id)` directly to avoid an extra `SELECT` query.

Note that between the read step and the delete step, another transaction might modify or delete the row. If the entity has `@Version`, optimistic locking helps detect certain concurrent updates. If multiple business steps need protection, wrap them in an appropriate transaction and design explicit update/delete conditions.

## 3. Deleting by ID

When only the ID is available, `deleteById` is a straightforward choice:

```java
public Mono<Void> deletePerson(Long id) {
    return repository.deleteById(id);
}
```

`deleteById` does not require loading the entity first. This is appropriate for simple deletions when the ID has already been validated and current data does not need inspection.

Because the method returns `Mono<Void>`, the application cannot tell from the emitted signal whether exactly one row was deleted. If you need to distinguish "deleted" from "not found," use a delete statement that returns the affected row count or implement a read/delete flow per your business rules. Be mindful of race conditions if separating existence checks and deletion into two operations.

For multiple IDs, `ReactiveCrudRepository` offers methods like `deleteAllById(...)` depending on the API version. Use them when deleting a set of IDs. If you need affected row counts, additional conditions, or custom SQL, use `DatabaseClient` or the template to obtain the desired result.

## 4. Deleting Entities with R2dbcEntityTemplate

`R2dbcEntityTemplate` provides a Spring Data entity-level operations API. You can delete an existing entity:

```java
public Mono<Void> delete(Person person) {
    return template.delete(person);
}
```

The template uses mapping metadata to determine the entity's table and identifier columns. This is useful when the data access layer already uses `R2dbcEntityTemplate` instead of a Repository, or when combining insert/select/update/delete operations within the same abstraction.

When the entity has a `@Version` field, preserve the version value from the most recent read. If another thread has updated the row and incremented the version, deleting with the stale entity can fail with an optimistic locking error. The application should handle this error as a data conflict—for instance, asking the user to reload or reapplying the operation per business rules.

## 5. Deleting by Condition with Query and Criteria

When deleting all rows matching a condition, there is no need to load each entity. `R2dbcEntityTemplate` lets you build conditions with `Criteria` and pass them into `Query`:

```java
public Mono<Long> deleteInactivePeople() {
    Query query = Query.query(
        Criteria.where("status").is("INACTIVE")
    );

    return template.delete(Person.class)
        .matching(query)
        .all();
}
```

In this example:

1. `Person.class` identifies the entity type and target table.
2. `Criteria.where("status").is("INACTIVE")` builds the condition against the entity property.
3. `Query.query(...)` wraps the condition into a query.
4. `matching(query)` applies the condition to the delete operation.
5. `all()` deletes all matching rows and returns `Mono<Long>` representing the affected row count.

Property names in Criteria are typically Java property names on the entity. The mapping context translates them to the corresponding columns via annotations or the naming strategy. Use the proper value types matching the property types so the driver binds data accurately.

### Combining Multiple Conditions

Example deleting only accounts inactive beyond a certain time:

```java
public Mono<Long> deleteExpiredAccounts(Instant cutoff) {
    Criteria criteria = Criteria.where("status").is("INACTIVE")
        .and("lastLoginAt").lessThan(cutoff);

    return template.delete(Account.class)
        .matching(Query.query(criteria))
        .all();
}
```

Combined conditions narrow the deletion scope. Before running a destructive operation, verify the exact set of rows that will be affected. You can run a `SELECT` query with the same condition in development or operations environments to verify the scope before executing the delete.

### OR Conditions

When deleting across multiple condition branches, you can combine `Criteria` using the API of your Spring Data version. Conceptual example:

```java
Criteria criteria = Criteria.where("status").is("CLOSED")
    .or("status").is("CANCELLED");

return template.delete(Order.class)
    .matching(Query.query(criteria))
    .all();
```

Criteria chaining APIs may vary across versions; verify against the documentation for your project's release train. For complex predicates, explicit SQL via `DatabaseClient` is often easier to inspect.

## 6. Deleting by Condition with SQL via DatabaseClient

When database-specific syntax, complex predicates, or explicit statement control is needed, you can use `DatabaseClient`:

```java
public Mono<Long> deleteOrdersBefore(Instant cutoff) {
    return databaseClient.sql("""
            DELETE FROM purchase_order
            WHERE status = :status
              AND created_at < :cutoff
            """)
        .bind("status", "CANCELLED")
        .bind("cutoff", cutoff)
        .fetch()
        .rowsUpdated();
}
```

`rowsUpdated()` returns the affected row count as a publisher. This approach works well when writing explicit SQL, leveraging engine-specific features, or deleting from tables not mapped to entities.

Always use bound parameters for input values. Never concatenate user-supplied strings directly into SQL statements. Parameter binding protects values, but cannot substitute table names, column names, or SQL keywords. If dynamic column selection is unavoidable, map selections through a fixed allow-list in code.

### Using PostgreSQL DELETE RETURNING

PostgreSQL supports `RETURNING`, allowing you to retrieve data from the rows just deleted:

```java
public Flux<Long> deleteAndReturnIds(String status) {
    return databaseClient.sql("""
            DELETE FROM purchase_order
            WHERE status = :status
            RETURNING id
            """)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
}
```

This is PostgreSQL-specific syntax, not portable SQL across all database engines. If you need information about deleted rows, check the equivalent feature in your database. Avoid running a `SELECT` after deletion to guess which IDs were deleted, as data may change between the two operations.

## 7. Derived Delete Queries and @Query

Spring Data supports query methods for many read operations and certain update/delete operations. For derived delete methods or `@Query` with `@Modifying`, verify supported capabilities and return types in your project's exact Spring Data R2DBC version.

Example of a named delete method:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Mono<Long> deleteByStatus(String status);
}
```

If your release train supports derived delete queries returning a row count, this method can cleanly express deleting by property. If unsupported or if precise SQL control is needed, use `@Modifying` with `@Query` or `DatabaseClient`.

Example of a custom SQL delete method:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Modifying
    @Query("DELETE FROM person WHERE status = :status")
    Mono<Integer> deleteByStatusUsingSql(String status);
}
```

Return types and annotations must match the API of the version in use. Check official documentation, the dependency tree, and integration tests rather than copying examples from another release train. For custom SQL, check table/column names, parameter binding, and database dialect.

## 8. How Entity Delete Differs from Conditional Delete

| Criterion | Delete by Entity | Delete by Condition |
|---|---|---|
| Input | An existing entity instance | Query/Criteria or SQL condition |
| Typical rows affected | One row by identifier | One or many rows |
| Needs entity loaded beforehand? | May already be loaded; loading to inspect adds a SELECT | Does not need to load each entity |
| Optimistic locking | Can check the entity's `@Version` | Does not check version individually per row like entity delete |
| Entity lifecycle callbacks | Can run through framework's entity operation flow | Usually no per-entity callbacks because entities are not materialized |
| Result | Typically `Mono<Void>` | Template/DatabaseClient can return affected row count |
| Best suited for | Deleting one object after business validation | Cleanup, deleting by status, timestamp, or criteria |

Conditional bulk deletion is generally more efficient for large row counts because the database executes the operation directly. However, the application must consider per-entity rules itself, such as version checks, per-record audit logging, or publishing individual domain events for each row.

If business logic must run per entity before deletion, you can query matching entities and process each one individually. This costs more resources and round-trips, but allows per-object logic. For large volumes, consider batch processing or a dedicated cleanup workflow.

## 9. Optimistic Locking When Deleting Entities

Spring Data Relational supports optimistic locking via `@Version`. When an entity has a version, the framework uses the version value to detect whether another transaction modified the entity since it was last read.

Example:

```java
@Table("document")
public record Document(
    @Id Long id,
    String title,
    @Version Long version
) {}
```

Suppose two requests both read a document with `version = 4`. Request A updates the document and the database advances the version to 5. Request B still holds the stale entity with version 4 and calls `delete(entity)`. The delete predicate can include both ID and version; since the row no longer has version 4, the operation deletes nothing and the framework raises an optimistic locking error.

This behavior is valuable when business rules forbid deleting an entity that someone else modified without the user knowing. The service layer can translate the error into a conflict response, prompt the user to reload, or allow re-confirmation.

Conditional bulk deletes do not load each entity to inspect `@Version`. If you need to delete a row only at a specific version, include the version predicate in Query/SQL:

```sql
DELETE FROM document
WHERE id = :id
  AND version = :expectedVersion;
```

Then inspect the affected row count. If the result is 0, either the row does not exist or the version changed. The application can perform a follow-up query to distinguish the two cases, while accounting for race conditions between operations.

## 10. Foreign Key Relationships and Cascade Deletes

Spring Data R2DBC does not perform object-graph cascade removal automatically like some ORMs. When deleting a parent entity, whether child rows are removed depends on the database schema and application logic.

For example, a foreign key may be declared as:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
        ON DELETE CASCADE
);
```

With `ON DELETE CASCADE`, the database automatically deletes `order_line` rows when the corresponding `purchase_order` row is deleted. This is database-level cascading enforced by the foreign key, not Spring Data traversing child entities.

Common options:

- `ON DELETE CASCADE`: deletes child rows when the parent row is deleted. Suitable when child data has no independent meaning outside the parent.
- `ON DELETE RESTRICT` or equivalent default behavior: rejects deleting the parent while referencing child rows exist. Suitable when preserving history or referential data.
- `ON DELETE SET NULL`: sets the foreign key on child rows to null if the relationship is nullable and child data remains meaningful independently.

Do not add cascades just to make a delete statement succeed. For transactional, financial history, or auditable data, cascading deletes can destroy critical information. Consider using cancellation statuses, archiving, or soft deletes instead of physical deletion.

## 11. Deleting Across Multiple Tables in a Reactive Transaction

If database cascades are not used and a business flow must delete from multiple tables, wrap the operations in a transaction to avoid partial states.

Example deleting order lines and then the order:

```java
@Service
public class OrderDeletionService {

    private final DatabaseClient databaseClient;

    public OrderDeletionService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Transactional
    public Mono<Void> deleteOrder(Long orderId) {
        Mono<Long> deleteLines = databaseClient.sql("""
                DELETE FROM order_line
                WHERE order_id = :orderId
                """)
            .bind("orderId", orderId)
            .fetch()
            .rowsUpdated();

        Mono<Long> deleteOrder = databaseClient.sql("""
                DELETE FROM purchase_order
                WHERE id = :orderId
                """)
            .bind("orderId", orderId)
            .fetch()
            .rowsUpdated();

        return deleteLines.then(deleteOrder).then();
    }
}
```

This illustrates deleting children before the parent. `@Transactional` must be handled by a reactive transaction manager sharing the same `ConnectionFactory` as `DatabaseClient`. Both publishers are returned in the same chain so Spring manages the transaction. Never call `subscribe()` inside the method, as that creates an independent subscription that can escape the transaction.

If the database already configures `ON DELETE CASCADE`, deleting only the parent row lets the database remove the children. Choose one approach intentionally to avoid mixing manual child deletion with unnecessary cascades.

## 12. Soft Delete vs. Physical Delete

Not every business case should remove rows from the database. **Soft delete** marks a row as logically deleted while retaining the physical data, for example:

```sql
ALTER TABLE person
    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE NULL;
```

When deleting:

```sql
UPDATE person
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND deleted_at IS NULL;
```

When reading active data, queries add `deleted_at IS NULL`. You can also use `status = 'DELETED'` or a boolean flag if that suits the domain model.

Spring Data R2DBC does not automatically convert delete calls into soft deletes just because an entity has a `deletedAt` field. The application must implement the update operations, query filters, and restoration rules explicitly. You can encapsulate this behavior in a service or data access layer to avoid forgetting filter predicates.

Soft delete carries several implications:

- Unique constraints may need adjustment if recreating a record with the same key after soft deletion is allowed. PostgreSQL can use a partial unique index; other databases offer different mechanisms.
- Read queries must consistently exclude soft-deleted rows.
- Policies must define who can view deleted data, when restoration is allowed, and when physical deletion must occur.
- Personal or retention-bound data must still comply with system deletion and retention policies.

## 13. Handling Results and Errors When Deleting

When using the template or `DatabaseClient`, the affected row count lets the service distinguish outcomes:

```java
public Mono<Void> deletePerson(Long id) {
    return template.delete(Person.class)
        .matching(Query.query(Criteria.where("id").is(id)))
        .all()
        .flatMap(deleted -> deleted == 1
            ? Mono.empty()
            : Mono.error(new PersonNotFoundException(id)));
}
```

This example assumes IDs are unique and treats zero deleted rows as an error. If the system treats delete as idempotent, `deleted == 0` can be accepted as a successful result. The decision depends on the API contract: DELETE can return success when the resource is already gone, or return 404 if the business flow requires confirming the resource existed.

Common errors:

| Error | Cause | Resolution |
|---|---|---|
| Foreign key constraint violation | Other rows still reference the row being deleted | Delete child data in order, configure suitable cascades, or reject per business rules |
| Optimistic locking failure | Entity holds an older version than the database | Reload entity and handle conflict per business rules |
| Zero rows affected | ID does not exist or condition did not match | Decide whether to return 404, ignore, or report no change |
| Unique/constraint or other database error | Trigger, constraint, or rule violation | Classify error and map to an appropriate business error |
| Timeout or connection loss | Slow database or interrupted connection | Log, inspect operation status, and retry only when safe |

Do not automatically retry a delete command when it is unclear whether the database committed. If the response was lost after the server executed the delete, a retry may affect 0 rows. That may be acceptable for idempotent operations, but must align with the API contract and transaction design.

## 14. Safely Combining Dynamic Conditions

A cleanup job may accept multiple criteria such as status, timestamp, and tenant. Never construct SQL by concatenating input strings. With `R2dbcEntityTemplate`, build Criteria from validated values:

```java
public Mono<Long> deleteByStatusAndTenant(
        String status,
        Long tenantId,
        Instant before) {

    Criteria criteria = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status)
        .and("createdAt").lessThan(before);

    return template.delete(AuditRecord.class)
        .matching(Query.query(criteria))
        .all();
}
```

If filters are optional, append conditions only when values are present. Guard against the case where all filters are absent: an unconstrained query can wipe the entire table. For broad cleanup operations, require a mandatory scope such as tenant, time window, or allowed statuses.

If dynamic column names or sorting are needed in SQL, use a fixed allow-list. Never interpolate user-supplied column names directly into statements. Additionally, verify authorization over the target data scope before deleting; bound parameters protect SQL structure, not authorization checks.

## 15. Performance Considerations for Large-Scale Deletes

Bulk deletions can place heavy load on a database. A single delete statement affecting millions of records can hold locks for a long time, generate massive logs, increase replication lag, and block other transactions.

Common strategies:

- Delete in time slices or key ranges to bound the row count per batch.
- Ensure indexes support the `WHERE` predicate; otherwise, the database may perform a full table scan.
- Run cleanup during low-traffic windows and cap concurrency.
- Monitor locks, transaction duration, WAL/redo logs, and replication lag for your database engine.
- Use partitioning and drop/detach partitions for expired data when the workload fits and the database supports it.
- For large audit tables, consider retention policies and archiving workflows before physical deletion.

Avoid bundling a massive cleanup job into one long-running transaction if it can be split into independent batches. Conversely, if rows must be removed as an indivisible business unit, keep the transaction and design appropriate batch limits.

## 16. Choosing a Delete Approach by Requirement

| Requirement | Approach to Consider |
|---|---|
| Entity already loaded, need status or version checks before deleting | `repository.delete(entity)` or `template.delete(entity)` |
| Only have ID and no need to read entity | `repository.deleteById(id)` |
| Delete a set of rows by entity properties | `template.delete(Type.class).matching(Query).all()` |
| Delete with engine-specific SQL or needing `RETURNING` | `DatabaseClient` |
| Need Repository API named after condition | Derived delete query if supported by version; verify return type |
| Need SQL control inside Repository | `@Modifying` + `@Query` if supported by version |
| Need to preserve history instead of physical removal | Soft delete via update operations and query filters |
| Delete child rows when parent row is deleted | Foreign key `ON DELETE CASCADE` if aligned with data policy |

## 17. Workflow for Implementing a Delete Operation

Before writing code, clarify:

1. **Scope:** deleting a single entity, by ID, or multiple rows by condition?
2. **Business rules:** do status, ownership, version, or retention policies need checking?
3. **Relationships:** which foreign keys reference this row? Use cascade, delete children first, or reject deletion?
4. **Result:** should the API return `204`, `404`, deleted row count, or deleted IDs?
5. **Atomicity:** must multiple operations belong to the same reactive transaction?
6. **Volume:** how many rows are expected? Are batching, partitioning, or scheduled cleanup needed?
7. **Testing:** are there tests for existing/missing entities, stale versions, foreign keys, empty conditions, and concurrent deletes?

For entity-based deletes, prioritize business checks and optimistic locking when protecting data that users have already read. For conditional deletes, craft tight Criteria/SQL, verify affected row scope, and remember that bulk operations bypass individual entity processing. Combining the right API with transactions, database constraints, and error-handling rules keeps delete operations in Spring Data R2DBC safe, predictable, and well-suited to data scale.

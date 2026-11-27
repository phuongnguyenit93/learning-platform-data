# `save` Performs Insert or Update Differently Than Expected

In Spring Data R2DBC, `repository.save(entity)` does not mean the database searches for a matching row and decides whether to insert or update. Spring Data determines the entity's new/existing state first, then chooses the corresponding insert or update operation. Therefore, if `save` creates a new row when you expected an update, or runs an update when you expected an insert, the cause usually lies in how Spring Data detects entity state: `@Id` values, `@Version` properties, or the `Persistable.isNew()` contract.

The key point is that `save` is not an upsert command based on arbitrary unique keys. Nor does it perform dirty checking like JPA. Inspect the entity's state right before calling `save`, check the actual SQL sent, and use the entity returned by the publisher after insert if the ID is database-generated.

## 1. How Does `save` Choose Insert or Update?

With Spring Data Relational reactive repositories, `save` typically branches on whether the entity is considered new:

```java
return entityInformation.isNew(entity)
    ? entityOperations.insert(entity)
    : entityOperations.update(entity);
```

This illustrates the selection logic. Internal implementation details depend on the Spring Data version, but the core principle is: entity state is decided before executing any SQL statement.

```mermaid
flowchart TD
    A[repository.save(entity)] --> B{Entity treated as new?}
    B -->|Yes| C[INSERT]
    B -->|No| D[UPDATE]
    C --> E[Database generates ID if configured]
    E --> F[Publisher returns saved entity]
    D --> G[UPDATE by ID and version if present]
    G --> H[Publisher returns updated entity or error]
```

Spring Data does not necessarily run a `SELECT` to check if a row exists before each save. New/existing classification is based on object metadata and state, not a database lookup by unique business key.

## 2. Order of New-Entity Detection

Common Spring Data Relational strategies follow this order:

1. If the entity implements `Persistable`, Spring Data uses `isNew()` provided by the entity.
2. Otherwise, if the entity has a `@Version` property, the version value is used to determine new/existing state.
3. If there is no version property, Spring Data inspects the ID: a null ID usually means a new entity; a primitive ID with a default value such as `0` may be treated as new.

Therefore, do not look only at `id` to predict insert/update if the entity has `@Version` or implements `Persistable`.

| Entity Configuration | Commonly Detected State |
|---|---|
| No `@Version`, `Long id == null` | New → insert |
| No `@Version`, `Long id != null` | Existing → update |
| With `@Version Long version == null` | New → insert |
| With `@Version Long version != null` | Existing → update |
| With `@Version long version == 0` | New → insert per primitive version rules |
| Implements `Persistable`, `isNew() == true` | New → insert |
| Implements `Persistable`, `isNew() == false` | Existing → update |

With wrapper types like `Long`, `0L` is still a non-null value. When using `@Version Long`, do not initialize a new entity's version to `0L` if you want Spring Data to treat it as new; usually leave it `null` and let the framework manage the version. With primitive `long`, `0` can be treated as new.

## 3. `@Id` Determines Which Property Identifies the Entity

Spring Data Relational uses `org.springframework.data.annotation.Id` to mark the entity's identifier property:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String email;
}
```

When `id == null`, the entity is usually considered new unless overridden by a version strategy or `Persistable`. When `id` has a value, the entity is usually considered existing and `save` selects update.

Verify the import of `@Id`. For Spring Data R2DBC, use `org.springframework.data.annotation.Id`. Do not assume an `@Id` annotation from another library carries the same meaning for Spring Data mapping metadata.

If an entity lacks a property recognized as its ID by Spring Data, mapping or saving can fail or behave unexpectedly. Do not infer entity state from a field named `id` if that field is not mapped as the identifier.

## 4. Common Mistake: Pre-Assigned ID Causes `save` to Run UPDATE

Suppose an application imports data from another system and assigns IDs itself:

```java
Customer customer = new Customer(
    9001L,
    "An Nguyen",
    "an@example.test"
);

return customerRepository.save(customer);
```

If the entity has no `@Version` and does not implement `Persistable`, the non-null ID `9001L` leads Spring Data to treat the entity as existing. `save` chooses update.

This can be surprising when your goal is to insert a new row with an externally supplied ID. State your intent explicitly:

- If you want to update row `9001`, use `save` with the existing entity.
- If you want to insert a new row with a pre-assigned ID, use an explicit insert operation or an appropriate `Persistable.isNew()` strategy.
- If you want insert-or-update by business key, implement a dialect/SQL upsert or a conflict-aware workflow with an appropriate transaction.

Do not set the ID to null just to force an insert if that ID is a required business key. Dropping the ID may cause the database to generate a different ID or break linkage with the source system.

## 5. Common Mistake: Null ID Yet Non-Null Version

When an entity has `@Version`, version may take precedence in determining new/existing state. Example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version = 0L;

    private String name;
}
```

`version` is a `Long` wrapper already initialized to a non-null value. Under version-based detection, the entity may be treated as existing even though `id` is null. As a result, Spring Data takes the update branch, causing errors or SQL that conflicts with your intent to insert.

With a wrapper version, leave new entities with a null version:

```java
@Version
private Long version;
```

Let Spring Data manage version initialization during insert/update. Do not assign an initial version manually unless you clearly understand your framework version's new-state rules.

## 6. Common Mistake: Version Not Reset When Creating a New Entity

A factory or mapper may copy version from a source object:

```java
Customer newCustomer = new Customer();
newCustomer.setId(null);
newCustomer.setVersion(source.getVersion());
newCustomer.setName(source.getName());
```

If `source.getVersion()` is non-null, the new entity can be detected as existing. When creating a new entity from a request/DTO, copy only allowed business fields; do not copy persistence IDs or versions from an old entity unintentionally.

Prefer clear factory methods:

```java
public static Customer newCustomer(String name, String email) {
    Customer customer = new Customer();
    customer.setName(name);
    customer.setEmail(email);
    // keep id and version in the new state per mapping strategy.
    return customer;
}
```

For updates, load the current entity or accept a command carrying an explicit ID/version and apply changes according to business rules.

## 7. `@Version` Affects Both New-State Detection and Optimistic Locking

`@Version` plays two related roles:

- Participates in determining whether an entity is new or existing.
- Protects updates from overwriting changes made by concurrent transactions via optimistic locking.

Example:

```java
@Table("inventory_item")
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private String sku;
    private Integer availableQuantity;
}
```

On insert, the framework initializes version according to Spring Data Relational/driver semantics. On update, the statement typically includes ID and current version in the condition while incrementing the version.

Conceptual SQL:

```sql
UPDATE inventory_item
SET available_quantity = :quantity,
    version = :nextVersion
WHERE id = :id
  AND version = :currentVersion;
```

If no row matches because the entity is stale or the row was deleted, Spring Data can emit `OptimisticLockingFailureException` instead of silently overwriting. SQL details and version increments are managed by the framework and dialect; do not manually increment version before calling `save` unless the application has a clear reason.

## 8. Common Mistake: `Persistable.isNew()` Returns the Wrong Value

An entity can implement `Persistable<ID>` to decide its newness explicitly:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

public class ImportedCustomer implements Persistable<String> {

    @Id
    private String id;

    private String displayName;

    @Transient
    private boolean newEntity;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

This illustrates the mechanism; application constructors/factories must set `newEntity` accurately for new objects versus objects loaded from the database. After a successful insert, the state must flip to existing before the next save. This can be done via appropriate lifecycle callbacks or by updating state on the returned entity if mutable.

Two opposite bugs can occur:

- `isNew()` always returns `true`: every save chooses insert, potentially causing duplicate key errors.
- `isNew()` always returns `false`: new entities take the update branch and may fail to create rows.

Do not implement `Persistable` just to work around a mapping error without defining the full lifecycle. If no custom strategy is needed, letting Spring Data rely on ID/version is usually simpler.

## 9. `Persistable` and `@Version` Should Not Contradict Each Other

When an entity implements `Persistable`, `isNew()` becomes a critical contract owned by the application. Avoid letting `isNew()` return a state inconsistent with the current ID/version.

Inconsistent examples:

- Entity is already persisted, ID is set and version incremented, yet `isNew()` remains true.
- Entity was just created with a pre-assigned ID, yet `isNew()` is false when you want to insert.
- Object loaded from the database has a constructor/factory initializing `newEntity = true`.

Map out all object creation paths:

| Entity Source | Expected State |
|---|---|
| Factory creating new record for insert | New |
| Entity read from repository/database | Existing |
| DTO converted to entity for update | Existing with validated ID/version |
| Imported record with pre-assigned ID to insert | New per explicit strategy |
| Entity just inserted successfully | Existing for subsequent saves |

If there are multiple creation paths, test each factory/mapper individually so none accidentally assigns the wrong state.

## 10. `save` Is Not an UPSERT by Unique Business Key

Suppose a table has a unique `email` key:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL
);
```

The application creates a new entity with `id == null`, while that email already exists:

```java
Customer customer = new Customer(null, "an@example.test", "An Updated");
return customerRepository.save(customer);
```

Spring Data still selects insert because the ID indicates a new entity. The database then rejects the insert due to the unique constraint. `save` does not look up by email to switch to update.

Conversely, if the entity has a non-null ID that does not exist in the table, `save` chooses update; it does not fall back to insert just because the update matched zero rows.

| Entity State | Database State | Expected `save` Behavior |
|---|---|---|
| New, null ID | Business key absent | Insert |
| New, null ID | Business key exists | Insert and likely unique violation |
| Existing, ID present | Row exists | Update |
| Existing, ID present | Row missing | Update matches zero rows; may throw optimistic locking error if versioned |

If the requirement is "update if email exists, create if absent," design an upsert around the unique key. Syntax varies across PostgreSQL (`ON CONFLICT`), MySQL (`ON DUPLICATE KEY UPDATE`), and SQL Server/Oracle (`MERGE` or an appropriate pattern). Verify concurrency and generated-value returns per dialect.

## 11. `save` Does Not Perform JPA-Style Dirty Checking

Spring Data R2DBC is part of Spring Data Relational and has no JPA-style persistence context tracking field mutations on loaded entities.

When calling `save(entity)` on an existing entity, the framework builds an update from mapping metadata. Do not assume it updates only modified fields. Other persistent properties on the entity can be included in the update statement according to mapping rules.

Dangerous example:

```java
Customer partial = new Customer();
partial.setId(10L);
partial.setDisplayName("New name");
// email was not set, so it remains null.

return customerRepository.save(partial);
```

If the entity is treated as existing, the update may write `email = NULL` instead of preserving the existing email. This is not a safe partial update.

For partial updates, you can:

- Load the existing entity, modify the target fields, and save.
- Use `R2dbcEntityTemplate.update(...).matching(...).apply(...)` targeting specific columns.
- Use `DatabaseClient` to write an explicit `UPDATE` modifying only the required columns.
- Use a command DTO explicitly representing allowed mutable fields.

Do not pass an incomplete entity as a patch DTO to `save` unless you intend null columns to overwrite database values.

## 12. Immutable Entities: Always Use the Value Returned by `save`

With immutable entities or Java records, Spring Data may instantiate a new object holding the database-generated ID rather than mutating the original object.

Example:

```java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    String orderNo,
    String status
) {}
```

Saving a new entity:

```java
PurchaseOrder input = new PurchaseOrder(null, "ORD-100", "NEW");

return orderRepository.save(input)
    .flatMap(saved -> {
        // saved.id() may now hold the generated ID.
        return orderRepository.findById(saved.id());
    });
```

Do not discard the emitted value:

```java
// Avoid this if you need the database-generated ID.
orderRepository.save(input).thenReturn(input);
```

`input` can still have `id == null` because records are immutable. Continue the pipeline using `saved` emitted by the publisher.

## 13. Reactive Publishers Are Lazy: Subscriptions Trigger SQL Execution

R2DBC operations typically execute when the publisher is subscribed. Merely constructing a `Mono` from `save` does not mean SQL has run:

```java
Mono<Customer> saveOperation = customerRepository.save(customer);
```

If the publisher is never subscribed, the operation may never execute. Conversely, each subscription to a cold publisher can re-execute the operation:

```java
Mono<Customer> saveOperation = customerRepository.save(newCustomer);

// Two independent subscriptions can execute the save twice.
return Mono.zip(saveOperation, saveOperation);
```

Do not reuse a write publisher in ways that accidentally create multiple subscriptions. Compose operations within a single reactive chain:

```java
return customerRepository.save(newCustomer)
    .flatMap(saved -> sendWelcomeEvent(saved).thenReturn(saved));
```

If an already-executed result must be shared across multiple consumers, design sharing/caching intentionally with full awareness of publisher lifecycle. Do not call `subscribe()` manually inside a service to "force" `save` to run and then continue with another chain.

## 14. Why Might an Entity INSERT Multiple Times?

Common causes:

- ID remains null because the original immutable entity never received the generated ID.
- Each request creates a new instance with a null ID.
- `Persistable.isNew()` always returns true.
- `@Version` wrapper stays null because the mapper fails to populate version on load.
- The same `save` publisher is subscribed multiple times.
- Retrying an insert after a timeout without idempotency.
- Mapper creates a new entity instead of updating the existing entity.

Example of retrying an insert after a timeout:

1. Database inserts and commits.
2. Response is lost due to a dropped connection.
3. Application sees an error and retries with the entity still having a null ID.
4. The retry selects insert again.
5. A unique business key blocks the duplicate, or a duplicate row is created if no constraint exists.

For write operations exposed to uncertain commit outcomes, use an idempotency key or unique business key so a request applies at most once per business contract.

## 15. Why Might an Entity UPDATE When You Wanted INSERT?

Common causes:

- ID is pre-assigned and non-null.
- `@Version` wrapper already holds a non-null value.
- `Persistable.isNew()` returns false.
- Entity was mapped from an old DTO carrying ID/version.
- Primitive ID/version holds an unexpected non-default value.
- Factory creating a new entity copied persistence metadata from a saved object.
- Reusing a database-loaded entity by mistake when intending to create a new record.

To insert unambiguously, use an explicit insert API where appropriate. Do not strip ID/version arbitrarily from an existing entity, as doing so can break relationships or bypass optimistic locking.

## 16. Why Does UPDATE Change Zero Rows?

If `save` chooses update yet no row matches, check:

- Is the ID valid and pointing to the current database/schema/table?
- Does the entity carry a stale version?
- Was the row deleted by another transaction?
- Do `@Table`/`@Column` map to the right object names?
- Is `ConnectionFactory` pointing to the wrong environment/tenant?
- Does the update query include an optimistic version condition or custom predicate?

With `@Version` entities, an update failing to match ID/version typically raises `OptimisticLockingFailureException` to signal a conflict. Without `@Version`, do not assume Spring Data detects every stale case the same way. If you need the exact affected row count, use an update query/`DatabaseClient` and inspect `rowsUpdated()` or implement explicit concurrency control.

## 17. Distinguishing Optimistic Locking Failures from Other Database Errors

`OptimisticLockingFailureException` typically indicates an update/delete did not match the version state held by the application. This differs from:

- `DuplicateKeyException`: unique key violation.
- `DataIntegrityViolationException`: constraint violation.
- `TransientDataAccessResourceException`: potentially transient resource error.
- `R2dbcTimeoutException`: operation timed out.
- `BadSqlGrammarException`: invalid SQL statement.
- Authentication/authorization failure: invalid credentials or permissions.

Do not retry all exceptions the same way. Optimistic conflicts usually require re-reading data and resolving per business rules; unique conflicts may represent duplicate requests; connection failures may be retried if the operation is idempotent.

## 18. `@Id` and Generated IDs: Checking Mapping

With database-generated IDs, new entities typically leave ID null:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

The schema defines database-appropriate identity/auto-increment. On a successful insert, Spring Data and the R2DBC driver must support retrieving the generated value and populating the resulting entity.

Do not assume JPA's `@GeneratedValue` annotation is the mechanism for Spring Data R2DBC. Spring Data Relational has its own dialect-specific identifier generation/mapping rules. Check documentation for your version and database driver.

If the ID is not returned:

- Check whether the database column has identity/sequence/default configured.
- Check whether `@Id` is placed on the right field.
- Check whether the driver supports generated values on the insert path being used.
- Check entity type and constructor/wither mapping.
- Check whether code uses the entity returned by `save`.

## 19. Assigned IDs and Generated IDs Are Two Different Strategies

Do not mix both strategies on the same entity without clear rules:

| Strategy | ID Before Insert | New State | Notes |
|---|---|---|---|
| Database-generated ID | null | New by ID/version | Database creates ID; use returned entity |
| Application-assigned ID | Present | Needs matching newness strategy | Existing ID value does not imply row exists |
| Imported ID to preserve | Present | Can use `Persistable.isNew()` or explicit insert | Ensure duplicate IDs are handled properly |
| Existing entity | Present | Existing | Update by ID/version |

If a system uses application-generated UUIDs, the ID always has a value even before insert. Relying solely on `id == null` cannot identify new entities in that case. You can use `Persistable` with an accurate lifecycle, a version property following Spring Data rules, or explicit inserts.

## 20. Using `Persistable` for Application-Assigned IDs

When IDs are created before saving and you still want to use `repository.save`, `Persistable` lets you explicitly describe entity state:

```java
public class ExternalRecord implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    public ExternalRecord(UUID id) {
        this.id = id;
        this.newEntity = true;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

After a successful insert, transition the flag to false:

```java
return externalRecordRepository.save(record)
    .doOnNext(ExternalRecord::markPersisted);
```

This example assumes a mutable entity and calls the method on the returned instance. For immutable entities, express state via an appropriate factory/constructor/callback instead of mutating the object. Entities read from the database must also initialize with `newEntity = false`; if the persistence constructor always marks true, the next save will attempt to insert again.

`@Transient` ensures this state flag does not become a database column. Test the full lifecycle: creation, successful save, reload, and subsequent save.

## 21. Using Explicit INSERT/UPDATE Operations When Intent Must Be Clear

If a use case knows for certain it must insert, use `R2dbcEntityTemplate`'s explicit insert API or SQL insert via `DatabaseClient` instead of letting object state decide:

```java
return r2dbcEntityTemplate.insert(ExternalRecord.class)
    .using(record);
```

Exact API signatures may vary slightly across Spring Data Relational versions; verify `R2dbcEntityTemplate` signatures in your project. An explicit insert will never turn into an update merely because the ID is populated.

When updating specific columns:

```java
return r2dbcEntityTemplate.update(Customer.class)
    .matching(Query.query(Criteria.where("id").is(customerId)))
    .apply(Update.update("displayName", newName));
```

This is an example of update via mapping metadata. Verify property names and API for your version. For multi-column updates or complex predicates, `DatabaseClient` allows writing explicit SQL and checking affected row counts.

Explicit operations clarify the use case's intent:

- Insert: must create a new row; duplicate ID/unique key is an error.
- Update: must modify an existing row; if no row matches, the application handles it per contract.
- Upsert: requires explicit insert-or-update semantics per unique key and dialect.

## 22. `DatabaseClient` Does Not Use Entity New-State Detection

When executing SQL directly:

```java
databaseClient.sql("""
        INSERT INTO customer(email, display_name)
        VALUES (:email, :displayName)
        """)
    .bind("email", email)
    .bind("displayName", displayName)
    .fetch()
    .rowsUpdated();
```

The application explicitly chose `INSERT` in the SQL. `Persistable.isNew()`, `@Version`, and `repository.save` logic will not turn this statement into an update.

Similarly, an `UPDATE` via `DatabaseClient` does not automatically enforce optimistic locking merely because a DTO/entity has `@Version`. If version checking is needed, include version in the SQL predicate and increment it explicitly, or use an entity-operation API that supports optimistic locking per mapping.

This is why `save` errors must be separated from custom SQL errors. Do not apply Repository assumptions to every R2DBC write path.

## 23. `saveAll` Also Applies New-State Detection per Entity

`saveAll` is not always a single SQL bulk insert/update statement. The framework may process entities according to their individual new/existing states, and drivers/dialects execute them in their own way.

If a collection mixes entities with null IDs, pre-assigned IDs, differing versions, or inconsistent `Persistable.isNew()` values, a batch save can unexpectedly mix inserts and updates.

Before calling `saveAll`, check:

- Do all entities follow the same ID/newness strategy?
- Have any entities already been persisted?
- Is `Persistable.isNew()` accurate for each object?
- Are there duplicate unique business keys within the batch?
- How does the driver/database handle batching and generated keys?
- How does an error mid-batch affect the transaction?

If a use case needs pure bulk inserts, consider explicit insert/batch APIs and test against the target database/driver. Do not assume `saveAll` always has the performance or atomicity of a single bulk SQL statement.

## 24. Transactions and Entity State After Errors

If an insert/update runs inside a reactive transaction and a subsequent step fails, the transaction can roll back. However, Java objects in memory may already have had their ID/version updated by the framework or callbacks before the transaction ended.

This means in-memory object state after a failure does not necessarily reflect database state. For instance, a mutable entity may have received a generated ID before the transaction later rolled back; the ID on the object still exists in memory even though the row does not exist in the database.

Do not blindly reuse entities from a failed transaction. Re-read the needed state or construct a fresh command/aggregate from verified data. For retried writes, prefer idempotency keys and a new transaction.

## 25. Retrying a `save` Publisher Can Cause Duplicate Inserts

Example:

```java
return customerRepository.save(new Customer(null, email, name))
    .retryWhen(Retry.max(2));
```

If a failure happens after the database commits but before the client receives the response, the retry can create a new entity still carrying a null ID and choose insert again. `retryWhen` does not know whether commit already occurred.

For reads, retrying transient errors carries lower risk. For writes:

- Use an idempotency key or unique business key.
- Check whether the operation already completed before repeating.
- Retry the entire new transaction, not a statement inside a broken transaction.
- Only retry errors classified as transient.
- Limit attempts, use backoff/jitter, and enforce deadlines.

Do not retry every exception from `save`. Unique violations, validation failures, or mapping errors will not be fixed by re-sending the same statement.

## 26. Diagnosing the Actual SQL Sent by `save`

When results differ from expectations, SQL logs/instrumentation provide crucial evidence. Determine:

1. Did Spring Data send `INSERT` or `UPDATE`?
2. Which table/schema was targeted?
3. Was the ID column included in the `INSERT`?
4. Did the `UPDATE` include `WHERE id = ...` and version?
5. Which columns were updated—were any columns unexpectedly set to null?
6. Did the database return rows updated, a generated ID, or a constraint error?
7. How many subscriptions/SQL executions occurred for one request?

You can use driver logging, a datasource/R2DBC proxy, or appropriate instrumentation. Logging configuration depends on driver and Spring versions. Enable it only in dev/test or with sampling/redaction in production; do not log passwords or sensitive bind parameter data.

## 27. Inspecting the Entity Right Before `save`

Temporarily log non-sensitive state immediately before the operation:

```java
log.debug("Saving customer: id={}, version={}, isNew={}",
    customer.getId(),
    customer.getVersion(),
    customer instanceof Persistable<?> persistable
        ? persistable.isNew()
        : "not-persistable");
```

If the entity does not implement `Persistable`, still inspect the version property and ID. You can write a test/debug-only helper to print state per entity strategy; do not call unstable internal framework APIs in production just for logging.

For sensitive data, never log emails, names, or payloads; log only permitted technical IDs/correlation IDs.

## 28. Checking Table, Schema, and `ConnectionFactory` Mapping

Sometimes the SQL took the right branch, yet you are inspecting the wrong database/table:

- `@Table` points to a different table name than the one you are inspecting.
- Default `schema` or `search_path` routes queries to another schema.
- Repository uses a `ConnectionFactory` for another test/tenant/database.
- Active Spring Boot profile differs from the expected environment.
- Database URL points to a read replica or wrong cluster endpoint.
- Migrations created a table with a different name or in another schema.

Verify the connection's actual endpoint, database, schema, and table. Do not log credentials; log only redacted host/database/schema consistent with policy.

## 29. Distinguishing Full-Entity `save` Updates from Partial Updates

If you want to update a single column, do not construct an entity with only the ID and that field and call `save` if the remaining fields might be null.

Status update example:

```java
public Mono<Integer> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE purchase_order
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .map(Long::intValue);
}
```

The return type of `rowsUpdated()` can be `Mono<Long>` depending on the Spring version; converting to `Integer` here is illustrative, and `Long` should be preserved if many rows might be updated. You can use `Mono<Long>` directly:

```java
public Mono<Long> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE purchase_order
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
```

When `rowsUpdated == 0`, the service can return not found or conflict per contract. If optimistic locking is needed, add `AND version = :version` and increment version in the same statement.

## 30. Explicit Optimistic Update Example

```sql
UPDATE inventory_item
SET available_quantity = :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

The application checks the affected row count:

```java
return databaseClient.sql(UPDATE_INVENTORY_SQL)
    .bind("quantity", newQuantity)
    .bind("id", id)
    .bind("expectedVersion", expectedVersion)
    .fetch()
    .rowsUpdated()
    .flatMap(updated -> updated == 1
        ? Mono.empty()
        : Mono.error(new OptimisticLockingFailureException(
            "Inventory item changed or no longer exists")));
```

Because this is custom SQL, the application manages version increments and zero-row handling itself. If using Repository/Template entity operations with `@Version`, Spring Data can perform optimistic locking for you.

## 31. Testing Insert/Update by New-State

Integration tests on a real database should cover:

| Scenario | Expected Outcome |
|---|---|
| Entity with null ID, no version | Insert and receive ID |
| New entity with null version | Insert and receive initial version |
| Entity with ID from database | Update matching row |
| Entity with pre-assigned ID needing insert | Explicit insert or `Persistable.isNew() == true` |
| `Persistable.isNew() == true` | Insert |
| `Persistable.isNew() == false` | Update |
| Stale version | Optimistic locking failure |
| Existing ID, but row deleted | Zero-row/version failure handled per mapping |
| Duplicate business key with null ID | Unique constraint error, no implicit upsert |
| Immutable entity inserted | Use returned entity with generated ID |

Example test for insert followed by update:

```java
@Test
void savesNewEntityThenUpdatesReturnedEntity() {
    Customer input = new Customer(null, "An", "an-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(customerRepository.save(input)
            .flatMap(saved -> {
                assertThat(saved.getId()).isNotNull();
                saved.setName("An Updated");
                return customerRepository.save(saved);
            })
            .flatMap(updated -> customerRepository.findById(updated.getId())))
        .assertNext(found -> assertThat(found.getName()).isEqualTo("An Updated"))
        .verifyComplete();
}
```

This test uses a mutable entity for illustration; with an immutable entity, construct a new instance from `saved` or use `withName(...)` and continue with the returned value.

## 32. Testing the `Persistable` Lifecycle

When using `Persistable`, test state both before and after insert:

1. Factory for new instances returns `isNew() == true`.
2. Save picks insert and the database creates the row.
3. Returned entity has a valid ID.
4. State flips to existing after insert.
5. Next save picks update.
6. Entity loaded from the database has `isNew() == false`.

If tests only assert the first insert, a bug where `isNew()` stays true will slip through and surface only on the second save.

## 33. Testing Subscriptions and Retries

For write publishers, tests should verify the number of SQL executions:

- One subscription executes one save per contract.
- The same cold publisher is not accidentally subscribed in multiple branches.
- Retries occur only for errors classified as transient.
- Retried writes use idempotency keys and create no duplicates.
- Post-commit/pre-response failures are simulated with fault injection if business rules require verification.

Do not use `StepVerifier` to subscribe multiple times to the same publisher when testing a single save. Each `StepVerifier.create(...)` subscribes to the publisher; create a fresh publisher or cache intentionally per scenario.

## 34. Other Causes of Unexpected Results

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Calling `save` produces no SQL | Publisher was never subscribed | Trace reactive chain and terminal subscriber |
| SQL insert runs twice | Cold publisher subscribed twice or retried | Count query executions, inspect operators/retries |
| `save` inserts even though ID is present | Null version or `Persistable.isNew()` is true | Check new-state detection order |
| `save` updates even though ID is null | Non-null wrapper version or `Persistable.isNew()` is false | Check version and custom newness |
| `save` updates the wrong row | Mis-mapped ID or repository points to wrong schema/database | Check `@Id`, SQL, and `ConnectionFactory` |
| Update writes null to other columns | Partial entity passed to `save` | Load full entity or use partial update |
| Duplicate key on insert | Business key already exists; `save` is not upsert | Use unique key/intentional upsert |
| Update affects no rows | Wrong ID, deleted row, or stale version | Check rows updated and optimistic locking |
| ID missing after insert | Returned entity ignored or driver/generated mapping wrong | Check generated values and immutable mapping |
| Batch save mixes inserts and updates | New-state differs across entities | Check ID/version/`isNew` per element |
| Save after reload becomes an insert | `Persistable.isNew()` or version initialized wrong | Check mapping constructor and lifecycle flag |

## 35. Quick Diagnostic Procedure

When `save` performs an unexpected insert or update, follow these steps in order:

**Step 1 — Inspect the actual entity.** Record ID, version, and `isNew()` immediately before subscription.

**Step 2 — Check mapping metadata.** Verify `@Id`, `@Version`, `@Table`, schema, and column mappings.

**Step 3 — Determine the newness strategy.** Check whether the entity implements `Persistable`; if not, inspect version before ID.

**Step 4 — Inspect the actual SQL.** Confirm whether Spring Data sends `INSERT` or `UPDATE`, the `WHERE` predicate, and written columns.

**Step 5 — Check database data.** Confirm whether the row exists in the right database/schema/table and which unique keys apply.

**Step 6 — Check the return value.** Use the entity emitted by `save`, especially when ID/version are generated or updated.

**Step 7 — Check reactive subscriptions.** Confirm the publisher is subscribed the expected number of times and retries are intentional.

**Step 8 — Determine transaction outcome.** On connection/timeout errors, consider commit uncertainty and do not retry writes blindly.

**Step 9 — Choose an API matching intent.** Use explicit insert/update or business-key upsert if `save` does not express the use case cleanly.

**Step 10 — Add regression tests.** Test new/existing, assigned/generated IDs, versions, immutable entities, and retries against a real database.

## 36. Conclusion

In Spring Data R2DBC, `save` selects `INSERT` or `UPDATE` based on the entity's new/existing state. If the entity implements `Persistable`, `isNew()` decides; otherwise, `@Version` may be checked before ID; without a version, ID usually decides. Consequently, pre-assigned IDs, wrongly initialized wrapper versions, `isNew()` flags that never transition, or mappers dropping IDs can all trigger an unexpected operation.

`save` is not an upsert by unique business key and does not perform JPA-style dirty checking. For immutable entities or database-generated IDs, always use the entity emitted by the publisher. For partial updates, use explicit update APIs instead of saving an incomplete object. When insert, update, or upsert semantics must be unambiguous, pick the API/SQL that states that intent. Combining inspection of actual SQL, new-state detection, transactions, and subscriptions pinpoints the root cause instead of guessing from the name `save`.

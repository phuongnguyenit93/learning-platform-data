# Upsert with `JdbcAggregateTemplate`: Dialect Requirements and Version Limitations

An **upsert** is a write operation with two possible outcomes: if a row with the identifying key already exists, update that row; if it does not exist, insert a new row. Spring Data JDBC provides this operation via `JdbcAggregateTemplate.upsert(instance)` starting in Spring Data Relational **4.1**.

Spring Data JDBC's upsert relies on native single-statement syntax supported by the database, typically `INSERT ... ON CONFLICT` or `MERGE`. Therefore, the operation only works when the dialect and `DataAccessStrategy` support single-statement upsert. The entity must have a pre-assigned ID, and optimistic locking is not currently supported by this feature.

This lesson explains how to use the API, the role of dialects, differences among `save`, `insert`, `update`, and `upsert`, version-specific limitations, the impact on child entities, and how to test against a real database.

## 1. What Problem Does Upsert Solve?

A common write flow is synchronizing data from an external system. The source system has already assigned a stable ID to a customer or order. The application needs to persist that data whether the record already exists or not.

If using a check-then-write approach:

```java
if (repository.existsById(customer.getId())) {
    repository.save(customer);
} else {
    repository.save(customer);
}
```

Beyond not even handling the difference between insert and update properly in that snippet, splitting into two branches still suffers from a race condition:

1. Request A checks and finds the ID does not exist.
2. Request B also checks and finds the ID does not exist.
3. Both execute an INSERT.
4. One request succeeds; the other fails with a duplicate key error.

A native upsert lets the database handle conflicts in a single statement. This eliminates the existence read before writing and delegates key-based conflict handling to the database.

### 1.1. Upsert Is Not a Regular Update Statement

| ID state in the database | Upsert outcome |
|---|---|
| No row exists with that ID | INSERT |
| A row already exists with that ID | UPDATE according to dialect rules |
| No ID is assigned on the entity | Does not meet the API precondition |
| Dialect/`DataAccessStrategy` does not support native upsert | May throw `UnsupportedOperationException` |

Upsert is useful when IDs are known upfront, for example:

- Synchronizing customers from a CRM.
- Importing order data from a partner system.
- Updating state from messages with a stable business key.
- Synchronizing per-tenant configuration.
- Writing snapshots or projections with an application-determined primary key.

Upsert does not replace all save operations. If a use case requires domain invariant checks, optimistic locking, or conditional partial updates, choose a more suitable API.

## 2. The `upsert` API of `JdbcAggregateTemplate`

`JdbcAggregateTemplate` is the template-level API for working directly with aggregates alongside Spring Data JDBC repositories.

You can inject the template as a Spring bean:

```java
@Service
public class CustomerSyncService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public CustomerSyncService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    public Customer synchronize(Customer customer) {
        return aggregateTemplate.upsert(customer);
    }
}
```

The method signature has the general form:

```java
<T> T upsert(T instance)
```

The API accepts an aggregate root, not raw SQL or a table name. Spring Data uses mapping metadata, converters, the dialect, and the data access strategy to build and execute the relational operations.

### 2.1. The ID Must Be Assigned Upfront

The passed entity must have an identifier. This is a crucial requirement because the database needs to know which key determines a conflict.

Example using an application-assigned ID:

```java
@Table("customers")
public record Customer(
        @Id Long id,
        String externalCode,
        String displayName,
        String email
) {
}
```

Calling upsert:

```java
Customer customer = new Customer(
        7001L,
        "CRM-7001",
        "Nguyen An",
        "an@example.test"
);

Customer saved = aggregateTemplate.upsert(customer);
```

`7001L` is an ID determined before the call. Do not design this flow assuming the database will auto-generate an identity ID and then decide whether to insert or update.

If database-generated IDs are the primary requirement, `insert` or `save` is usually more appropriate. Upsert needs the key to identify the conflict target before running.

### 2.2. Return Value

`upsert` returns the aggregate instance after executing the operation. Depending on mapping and dialect, the returned instance may reflect the ID value supplied by the dialect.

Do not rely on upsert to obtain an identity ID that was not already present. The API precondition remains that the entity must have an assigned identifier.

## 3. Spring Data JDBC Versions Supporting Upsert

`JdbcAggregateTemplate.upsert` was introduced in Spring Data Relational **4.1**.

| Spring Data Relational version | `JdbcAggregateTemplate.upsert` API |
|---|---|
| 3.x | Not available |
| 4.0.x | Not available |
| 4.1 and later | Available, if supported by the dialect and data access strategy |

Because Spring Data JDBC depends on Spring Data Relational, verify the actual resolved version of both modules in dependency management. You cannot add an `upsert` call to a codebase on 4.0.x and expect it to work merely because the database supports SQL upsert syntax.

### 3.1. Checking Dependency Versions

With Spring Boot, it is generally best to let the Boot BOM manage compatible Spring Data versions. Inspect the dependency tree or dependency report to confirm resolved versions rather than looking only at direct declarations.

Gradle example:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
}
```

To use the `upsert` API, select a Spring Boot/Spring Data release train that manages Spring Data Relational 4.1 or higher. Do not upgrade `spring-data-relational` alone to a different version from `spring-data-jdbc` without verifying compatibility.

### 3.2. Compile Errors on Older Versions

If compilation fails saying method `upsert(Customer)` is not found on `JdbcAggregateTemplate`, check:

- Which Spring Data JDBC version is in use.
- Which Spring Data Relational version is resolved.
- Whether a dependency override or another BOM pins an older version.
- Whether the IDE and Gradle use the same dependency graph.

Upgrading versions must maintain compatibility with your Spring Boot, Spring Framework, and JDBC driver versions.

## 4. Dialect Requirement: Native Single-Statement Upsert

Not all databases use the same upsert syntax. Spring Data Relational relies on the dialect to know how to construct the corresponding statement.

Two common syntax forms:

### 4.1. PostgreSQL: `INSERT ... ON CONFLICT`

Illustrative SQL example:

```sql
INSERT INTO customers (id, external_code, display_name, email)
VALUES (:id, :externalCode, :displayName, :email)
ON CONFLICT (id)
DO UPDATE SET
    external_code = EXCLUDED.external_code,
    display_name = EXCLUDED.display_name,
    email = EXCLUDED.email;
```

When no row exists with that ID, the database inserts. When a conflict occurs on the target key, the database executes the update branch.

### 4.2. MySQL: `INSERT ... ON DUPLICATE KEY UPDATE`

Illustrative SQL example:

```sql
INSERT INTO customers (id, external_code, display_name, email)
VALUES (?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
    external_code = VALUES(external_code),
    display_name = VALUES(display_name),
    email = VALUES(email);
```

Exact syntax may vary across MySQL versions. Spring Data does not require applications to write this SQL manually when a dialect supports it; the dialect renders the appropriate statement.

### 4.3. `MERGE`

Some databases use a `MERGE` statement to express conditional insert or update on a match condition:

```sql
MERGE INTO customers target
USING (
    SELECT :id AS id, :displayName AS display_name
) source
ON (target.id = source.id)
WHEN MATCHED THEN
    UPDATE SET target.display_name = source.display_name
WHEN NOT MATCHED THEN
    INSERT (id, display_name)
    VALUES (source.id, source.display_name);
```

This is only a general outline. `MERGE` syntax and capabilities differ among SQL Server, Oracle, DB2, and other databases.

### 4.4. Why Must It Be a Single-Statement Upsert?

An implementation pattern like:

1. SELECT to check if the ID exists.
2. If present, UPDATE.
3. If absent, INSERT.

is not equivalent to a native upsert under concurrency. Two transactions can both observe “does not exist” and both attempt to insert.

Native upsert lets the database handle conflicts in a single statement according to vendor semantics. Therefore, the dialect must provide upsert rendering; supporting separate SELECT, INSERT, and UPDATE statements is not enough.
## 5. Supported Databases and Dialects

Spring Data Relational 4.1 documentation lists upsert support for the following databases:

| Database | Common native form |
|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT` |
| H2 | H2 dialect upsert syntax |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` |
| MariaDB | `INSERT ... ON DUPLICATE KEY UPDATE` |
| SQL Server | `MERGE` |
| Oracle | `MERGE` |
| DB2 | `MERGE` |
| HSQLDB | HSQLDB dialect upsert syntax |

Verify the list and level of support against the documentation of the specific release train your application uses. A database may support native upsert at the SQL level while a given Spring Data version's dialect may not yet provide an implementation for it.

### 5.1. Unsupported Databases

If the dialect does not support single-statement upsert, the operation may throw:

```java
UnsupportedOperationException
```

A custom `DataAccessStrategy` must also provide upsert support. A custom implementation or MyBatis adapter does not automatically gain upsert support simply because the high-level interface exposes the method.

When encountering this error:

- Verify the actual database product and dialect.
- Check the Spring Data version.
- Check the configured `DataAccessStrategy`.
- Verify whether the database supports native upsert and the required SQL version.
- Choose custom SQL or upgrade once appropriate support exists.

Do not return a fake dialect for an incompatible database just to get past startup. Incorrect SQL can cause data errors at runtime.

## 6. Differences Among `save`, `insert`, `update`, and `upsert`

These four operations serve different purposes:

| Method | Decision mechanism | Behavior |
|---|---|---|
| `save(instance)` | Based on new/existing state per mapping and entity information | Insert or update |
| `insert(instance)` | Does not check new/existing state | Always inserts |
| `update(instance)` | Does not check new/existing state | Always updates |
| `upsert(instance)` | Based on ID conflict in the database | Native insert-or-update |

### 6.1. `save` Is Not `upsert`

`save` typically chooses insert or update based on entity newness state, such as ID/version or `Persistable.isNew()`.

With assigned IDs, an entity with a non-null ID may be treated as existing under newness rules. If no row exists in the database yet, the update branch may update zero rows.

`upsert` relies on database conflict handling to decide between insert and update by ID. It fits cases where the ID is pre-assigned but the row might not exist yet.

### 6.2. `insert` and `update` When State Is Known

Use `insert` when you are certain the ID does not exist and want an error on duplicate key violations.

Use `update` when you are certain the row already exists and want to update the aggregate. With `@Version`, `update` supports optimistic locking.

Do not use upsert merely to “save just to be safe” if the use case requires detecting pre-existing records or version conflicts.

## 7. Example: Customer Synchronization Service

Entity using an assigned ID:

```java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("external_code") String externalCode,
        @Column("display_name") String displayName,
        String email
) {
}
```

Service:

```java
@Service
public class CustomerSyncService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public CustomerSyncService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public Customer synchronize(Customer incoming) {
        return aggregateTemplate.upsert(incoming);
    }
}
```

When a sync message arrives with ID `7001`:

- If `customers.id = 7001` does not exist, the database inserts the customer.
- If it already exists, the database updates using the dialect's upsert statement.
- The service does not need to call `existsById` before writing.

`@Transactional` establishes the boundary for the service's persistence work. If the aggregate has child actions or multiple statements, the transaction ensures they commit or roll back together when sharing the same `DataSource` and transaction manager.

### 7.1. Use Transactions When Aggregates Have Child Entities

Native upsert for the root is a single statement, yet the aggregate may issue additional relational operations for child rows. If those statements must be atomic, invoke the template inside an appropriate transaction.

Example:

```java
@Transactional
public PurchaseOrder synchronizeOrder(PurchaseOrder incoming) {
    return aggregateTemplate.upsert(incoming);
}
```

Do not assume a standalone template method call always opens an enclosing transaction around every statement. Set explicit transaction boundaries in application services when atomicity is required.

## 8. Upsert with Aggregates Having Child Collections

Spring Data JDBC manages the aggregate root and child entities per the mapping. Upsert has specific aggregate behavior:

- The root is persisted via a native upsert action.
- Referenced/child entities within the aggregate are handled via delete and insert actions.
- Child rows are not upserted row-by-row by their own primary keys by default.

This means the aggregate's child collection can be replaced with the current contents of the instance.

Example:

```java
@Table("orders")
public record PurchaseOrder(
        @Id Long id,
        String orderCode,
        @MappedCollection(idColumn = "order_id")
        List<OrderLine> lines
) {
}
```

If the database currently holds order `100` with two order lines, and a new instance with the same ID has three order lines, upsert performs a native upsert on the root and executes delete/insert actions for child rows according to the aggregate change.

### 8.1. Implications for Child IDs and Metadata

Because child rows are deleted and re-inserted, consider:

- Children with database-generated IDs may receive new IDs.
- Child creation timestamps may be regenerated if mapping/callbacks assign new values.
- Database triggers on DELETE/INSERT may fire.
- Child-level audit logs may record deletions and new creations.
- Foreign keys from other tables pointing directly to a child row may be affected.
- A child row that is unchanged at the domain level may still be physically replaced.

If children have independent identities/lifecycles or must retain their IDs and metadata, upserting the whole aggregate may not be appropriate. Use a dedicated update workflow or specialized child persistence logic instead.

### 8.2. `AggregateReference` Does Not Cascade Upsert

`AggregateReference` represents an ID referencing another aggregate root. It does not mean the referenced aggregate will be automatically upserted alongside the current root.

For example, an order referencing a customer:

```java
private AggregateReference<Customer, Long> customer;
```

Upserting the order stores the customer key value on the order. If the customer also needs to be created or updated, perform that use case explicitly via Customer's repository or template.

## 9. Optimistic Locking Is Not Yet Supported

This is an important limitation of upsert in Spring Data JDBC: **upserts do not currently support optimistic locking**.

If an entity has:

```java
@Version
private Long version;
```

do not assume `upsert` will check the old version and reject writes when another transaction has updated the record.

### 9.1. Risk of Lost Updates

Suppose two requests concurrently read a customer at version 5:

1. Request A changes the email.
2. Request B changes the display name.
3. A writes successfully.
4. B calls upsert with the stale snapshot.
5. B may overwrite A's updates because upsert does not check the version under an optimistic-lock contract.

If the use case requires detecting concurrent update conflicts, use operations that support optimistic locking such as `save`/`update` with `@Version`, or custom SQL with an explicit version predicate.

### 9.2. Choosing an API Based on Concurrency Requirements

| Requirement | Appropriate approach |
|---|---|
| ID available, fast insert-or-update needed, no optimistic lock needed | `upsert` |
| Must check previous version | `save` or `update` with `@Version` |
| Insert only and fail on duplicate key | `insert` |
| Update only and detect version mismatch | `update` with `@Version` |
| Complex atomic conditions required | Custom SQL with version predicate or stored procedure |

Do not add `@Version` and assume data is protected when calling `upsert`. The current API explicitly documents this limitation.

## 10. Upsert and Full State vs. Partial Updates

Upsert takes a domain instance to map into a write statement. Pass an object containing the full state the use case intends to save.

Do not use upsert like a PATCH request carrying only a few populated fields, because remaining fields may map to NULL/defaults and overwrite existing data depending on mapping and generated SQL.

Unsafe example if the goal is only to update email:

```java
Customer partial = new Customer(
        7001L,
        null,
        null,
        "new@example.test"
);

aggregateTemplate.upsert(partial);
```

This object can cause other columns to be overwritten with null/defaults per the mapping. For partial updates, use `JdbcTemplate`, a custom repository with a targeted UPDATE query, or load the current aggregate, update the desired fields, and save with an appropriate API.

### 10.1. Upsert and Other Unique Constraints

The API specifies upsert by the aggregate root's identifier. If a table has another unique constraint, such as `external_code`, conflicts on that constraint may behave differently depending on the database and the conflict target generated by the dialect.

Do not assume an ID-based upsert automatically merges on every unique key. If a business key is the conflict target, check the dialect/API capabilities of your version or write custom SQL with the right conflict target.
## 11. Callbacks and Lifecycle Events

`JdbcAggregateTemplate` executes upsert through the aggregate persistence pipeline. Spring Data JDBC lifecycle callbacks such as `BeforeConvertCallback`, `BeforeSaveCallback`, and `AfterSaveCallback` can participate in this pipeline when configured.

This allows the application to continue using callbacks to:

- Normalize domain values before conversion.
- Populate metadata to be persisted.
- Inspect the aggregate change before SQL runs.
- React after persistence operations have executed.

However, `AfterSaveCallback` does not mean the transaction has committed. If the service method is still running inside a transaction, an exception after the callback can still roll back the transaction.

Do not send emails or publish messages assuming data is already committed just because an after-save callback ran. Use an outbox pattern or an after-commit mechanism when durable side effects are needed.

## 12. Upsert and Transaction Atomicity

A root upsert is rendered by the dialect as a single native statement. Aggregates with child collections can emit additional statements to delete/insert child rows.

If one statement succeeds and a subsequent statement fails, the application needs a transaction so the entire aggregate change commits or rolls back together.

Example:

```java
@Service
public class OrderImportService {

    private final JdbcAggregateTemplate template;

    public OrderImportService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public PurchaseOrder importOrder(PurchaseOrder order) {
        return template.upsert(order);
    }
}
```

The transaction manager must manage the same `DataSource` used by Spring Data JDBC. If part of the work runs against a different `DataSource`, a local JDBC transaction will not automatically become a distributed transaction.

## 13. When Should You Avoid Upsert?

Upsert is not suitable for every write flow.

Avoid it when:

- The entity does not have an ID prior to writing.
- The current database/dialect does not support native upsert.
- The use case requires optimistic locking.
- You only want to update a few columns.
- Child rows must preserve their identities or audit lifecycles.
- Duplicates should raise an error rather than silently updating.
- The conflict target must be a business key other than the aggregate ID and the dialect does not support it.
- A custom `DataAccessStrategy` has not implemented upsert.

In these cases, use `insert`, `update`, `save`, custom SQL, or an explicit application service workflow.

## 14. Fallbacks When Version or Dialect Lacks Support

### 14.1. Using Custom Native SQL

If the database supports upsert but your Spring Data JDBC version lacks the API, you can use `NamedParameterJdbcTemplate` to write native SQL.

PostgreSQL example:

```java
@Repository
public class CustomerNativeUpsertRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public CustomerNativeUpsertRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void upsert(Customer customer) {
        String sql = """
            INSERT INTO customers (id, external_code, display_name, email)
            VALUES (:id, :externalCode, :displayName, :email)
            ON CONFLICT (id)
            DO UPDATE SET
                external_code = EXCLUDED.external_code,
                display_name = EXCLUDED.display_name,
                email = EXCLUDED.email
            """;

        MapSqlParameterSource parameters = new MapSqlParameterSource()
                .addValue("id", customer.id())
                .addValue("externalCode", customer.externalCode())
                .addValue("displayName", customer.displayName())
                .addValue("email", customer.email());

        jdbc.update(sql, parameters);
    }
}
```

This SQL is for PostgreSQL. For MySQL, SQL Server, or other databases, use the corresponding vendor syntax.

Direct custom SQL does not automatically perform aggregate mapping, child replacement, entity callbacks, or auditing like `JdbcAggregateTemplate`. If those behaviors are needed, the application must design and invoke them explicitly.

### 14.2. Avoid SELECT Followed by INSERT/UPDATE When Concurrency Safety Is Needed

A fallback like:

```java
if (template.findById(id, Customer.class) == null) {
    template.insert(customer);
} else {
    template.update(customer);
}
```

may work when there is only a single writer or external locking/serialization exists. However, with multiple concurrent writers, this is check-then-act and has a race condition.

When atomicity is required, prefer native SQL upsert or an explicitly designed locking/serialization mechanism.

## 15. Testing Upsert

Test both the insert path and the update path, dialect behavior, and the optimistic locking limitation.

### 15.1. Testing Insert When ID Does Not Exist

```java
@DataJdbcTest
class CustomerUpsertTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void insertsWhenIdDoesNotExist() {
        Customer customer = new Customer(
                7001L,
                "CRM-7001",
                "Nguyen An",
                "an@example.test"
        );

        Customer saved = template.upsert(customer);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers WHERE id = ?",
                Integer.class,
                7001L
        );

        assertThat(count).isEqualTo(1);
        assertThat(saved.id()).isEqualTo(7001L);
    }
}
```

### 15.2. Testing Update When ID Already Exists

```java
@Test
void updatesWhenIdAlreadyExists() {
    template.insert(new Customer(
            7002L,
            "CRM-7002",
            "Old Name",
            "old@example.test"
    ));

    Customer incoming = new Customer(
            7002L,
            "CRM-7002",
            "New Name",
            "new@example.test"
    );

    template.upsert(incoming);

    String displayName = jdbc.queryForObject(
            "SELECT display_name FROM customers WHERE id = ?",
            String.class,
            7002L
    );

    assertThat(displayName).isEqualTo("New Name");
}
```

### 15.3. Testing Child Collections

Create an aggregate with two children, upsert the same root ID with three children, then verify:

- The root still has only one row.
- Child rows reflect the new collection.
- Child ID behavior matches your generated/assigned ID strategy.
- Related triggers and foreign keys behave as expected.

If child rows are deleted and re-inserted, do not write tests assuming old child IDs are always preserved.

### 15.4. Testing the Optimistic Locking Limitation

If the aggregate has `@Version`, do not write a test expecting `upsert` to throw `OptimisticLockingFailureException` on a stale version. The current feature does not provide optimistic locking for upsert.

Write separate tests for `update` or `save` to prove optimistic locking is enforced in use cases that require it.

### 15.5. Testing on a Real Database

H2 may support upsert, but it does not prove that PostgreSQL/MySQL/SQL Server/Oracle behave the same way. Run integration tests with the actual production database and JDBC driver, especially for:

- Conflict target.
- Generated/assigned IDs.
- Data types and converters.
- Child delete/insert ordering.
- Unique constraints outside the primary key.
- Transaction rollback when a child statement fails.

## 16. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `upsert` method not found at compile time | Spring Data Relational older than 4.1 | Upgrade to a compatible release train or use custom SQL |
| `UnsupportedOperationException` | Dialect/`DataAccessStrategy` does not support upsert | Check database, dialect, and custom strategy |
| Upsert reports missing ID | Entity does not have an identifier yet | Assign the ID before calling |
| Row not inserted when using `save` | Entity detected as existing and `save` chooses update | Use `upsert` when ID-based insert-or-update is needed |
| Upsert overwrites fields with NULL | Passed a partial object | Pass full aggregate state or use a targeted UPDATE |
| Child IDs change after upsert | Child rows were deleted and re-inserted | Use a dedicated update workflow if preserving identity is needed |
| Child audit records regenerated | Child delete/insert lifecycle was triggered | Design auditing per actual semantics or avoid full-aggregate upsert |
| Concurrent modifications go undetected | Upsert does not support optimistic locking | Use `@Version` with `save`/`update` or a SQL version predicate |
| Two databases do not roll back together | Different `DataSource`/transaction managers | Define transaction boundaries and consistency strategy |
| Custom SQL skips callbacks | Calling `JdbcTemplate` directly | Handle mapping/auditing/lifecycle explicitly in the custom path |

## 17. Usage Principles

- `JdbcAggregateTemplate.upsert` was introduced in Spring Data Relational 4.1.
- The entity must have an assigned ID before calling.
- The dialect and `DataAccessStrategy` must support native single-statement upsert.
- The database handles insert/update on identifier conflict; no prior existence SELECT is needed.
- 4.1 documentation lists PostgreSQL, H2, MySQL, MariaDB, SQL Server, Oracle, DB2, and HSQLDB; re-check the list for your specific release.
- The root is upserted via a native action; child entities in the aggregate are handled via delete/insert actions.
- `@Version` and optimistic locking are not currently supported by upsert.
- Pass full aggregate state; do not use upsert as a partial update.
- Use transactions when root and child changes must be atomic.
- `AggregateReference` does not cascade upsert to another aggregate.
- When version/dialect lacks support, use native SQL intentionally and understand that a custom JDBC path does not automatically replicate the full aggregate lifecycle.
- Test against a real database and JDBC driver, including conflicts, child collections, and rollbacks.

Upsert in `JdbcAggregateTemplate` is useful for data synchronization with pre-assigned identifiers where atomic root-level insert-or-update is needed. This capability starts in Spring Data Relational 4.1 and depends on a dialect with native upsert. Carefully weigh child delete/insert behavior and the lack of optimistic locking before using it for multi-part aggregates or concurrent writers.

## References

- [Spring Data Relational 4.1 — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/4.1/jdbc/entity-persistence.html)
- [JdbcAggregateOperations API — upsert](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [RelationalEntityUpsertWriter API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/relational/core/conversion/RelationalEntityUpsertWriter.html)
- [Spring Data Relational 4.1.0 Release Notes](https://github.com/spring-projects/spring-data-relational/releases/tag/4.1.0)






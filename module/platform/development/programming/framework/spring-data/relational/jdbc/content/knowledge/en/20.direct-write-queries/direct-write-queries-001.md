# Combining `@Modifying` with `@Query` for `UPDATE` and `DELETE`

In **Spring Data Relational JDBC**, `@Query` lets you declare SQL directly on a repository method. When the SQL statement modifies data using `INSERT`, `UPDATE`, `DELETE`, or a DDL command that does not return a result table, you need to mark the method with **`@Modifying`** so Spring Data knows this is a write query.

For example:

```java
@Modifying
@Query("UPDATE person SET lastname = :lastname WHERE id = :id")
int updateLastname(@Param("id") Long id, @Param("lastname") String lastname);
```

`@Modifying` causes Spring Data JDBC to execute the SQL statement directly and return the number of affected rows (`int`), whether any row was changed (`boolean`), or ignore the result (`void`). This is a SQL-level write path: it **does not invoke entity callbacks or lifecycle events**, so auditing fields are not updated automatically unless the SQL statement writes them.

This lesson covers how to declare `UPDATE`/`DELETE` queries, bind named parameters, choose return types, manage transactions, and understand the effects on aggregates, auditing, optimistic locking, and foreign keys.

## 1. Distinguishing `@Query` and `@Modifying`

The two annotations have different responsibilities:

| Annotation | Role |
|---|---|
| `@Query` | Provides the SQL statement used when calling the repository method |
| `@Modifying` | Tells Spring Data that the query is a data-modifying command, not a query that reads a result set |
| `@Param` | Binds a method parameter to a named parameter in the SQL |
| `@Transactional` | Defines the transaction boundary for the write operation |

Imports for Spring Data JDBC:

```java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;
```

Do not confuse `org.springframework.data.jdbc.repository.query.Modifying` with Spring Data JPA's `@Modifying` annotation (`org.springframework.data.jpa.repository.Modifying`). Spring Data JDBC has its own annotation in the `org.springframework.data.jdbc.repository.query` package.

### When do you need `@Modifying`?

- `@Query("SELECT ...")`: read query, do not mark with `@Modifying`.
- `@Modifying` + `@Query("UPDATE ...")`: updating rows.
- `@Modifying` + `@Query("DELETE ...")`: deleting rows.
- `@Modifying` + `@Query("INSERT ...")`: inserting data with explicit SQL when you do not need a generated key or result row returned.
- `@Modifying` + DDL command: only use when there is a specific schema-management reason; normally schemas are managed via migrations.

`@Modifying` only makes sense when paired with `@Query`. Derived delete methods such as `deleteByStatus(...)` are parsed by Spring Data from the method name and do not need `@Modifying`.

## 2. `UPDATE` Examples with `@Modifying` and `@Query`

Suppose the `person` table has columns `id`, `firstname`, `lastname`, `status`, and `updated_at`. A repository can declare:

```java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Query("UPDATE person SET lastname = :lastname WHERE id = :id")
    int updateLastname(
            @Param("id") Long id,
            @Param("lastname") String lastname
    );
}
```

Calling the method:

```java
int updated = personRepository.updateLastname(42L, "Nguyen");

if (updated == 1) {
    System.out.println("Person was updated");
} else {
    System.out.println("No matching row was updated");
}
```

`int` is the number of rows the database reports as affected. A value of `0` usually means no row matched the `WHERE` condition, or no change was recorded according to the database/driver semantics. Do not always interpret `0` as an error; it can be a valid business outcome.

### Updating Multiple Columns

```java
@Modifying
@Query("""
    UPDATE person
    SET firstname = :firstname,
        lastname = :lastname,
        status = :status,
        updated_at = :updatedAt
    WHERE id = :id
    """)
int updateProfile(
        @Param("id") Long id,
        @Param("firstname") String firstname,
        @Param("lastname") String lastname,
        @Param("status") String status,
        @Param("updatedAt") Instant updatedAt
);
```

The SQL inside `@Query` is database SQL, so you must use **table names and column names** (`updated_at`), not Java property names (`updatedAt`), unless they happen to be identical. Named parameters (`:id`, `:status`) are bound from method arguments.

## 3. `DELETE` Examples with `@Modifying` and `@Query`

Deleting a single row by ID:

```java
@Modifying
@Query("DELETE FROM person WHERE id = :id")
int deletePerson(@Param("id") Long id);
```

Deleting by condition:

```java
@Modifying
@Query("DELETE FROM person WHERE status = :status")
int deletePeopleWithStatus(@Param("status") String status);
```

Calling the method:

```java
int deleted = personRepository.deletePeopleWithStatus("INACTIVE");
System.out.println("Deleted rows: " + deleted);
```

A direct `DELETE` statement removes rows matching the `WHERE` clause. Be especially careful with SQL statements without a `WHERE` clause: they can delete all data in the table.

If the query deletes multiple rows, an `int` return type lets you capture the number of affected rows. If you only need to know that the operation completed, use `void`. If you only need to know whether at least one row was affected, use `boolean`.

## 4. Choosing the Return Type: `int`, `boolean`, or `void`

Spring Data JDBC supports three return types for modifying queries:

| Return type | Meaning | When appropriate |
|---|---|---|
| `int` | Number of updated/deleted rows | When you need to check whether exactly one row or how many rows were affected |
| `boolean` | Whether at least one row was changed | When you only need a succeeded/had-effect outcome |
| `void` | Ignores the update count | When you do not need to know how many rows were affected |

Examples:

```java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
boolean changeStatus(@Param("id") Long id, @Param("status") String status);

@Modifying
@Query("DELETE FROM person WHERE status = :status")
void deleteAllWithStatus(@Param("status") String status);
```

For business logic that needs to distinguish "no row found" from "exactly one row updated", `int` is usually most useful:

```java
int affected = repository.changeStatus(id, "ACTIVE");

if (affected == 0) {
    // No matching row or no change recorded.
} else if (affected == 1) {
    // One row was updated.
} else {
    // The WHERE condition is not unique or data has an issue.
}
```

Do not declare `Person` or `Optional<Person>` as the return type of a standard modifying query. `@Modifying` is designed for commands that do not return a result table. If you need to retrieve updated rows, generated keys, or results from `RETURNING`, use a custom repository with JDBC operations and a `ResultSet`/`RowMapper` suited to your database, rather than expecting `@Modifying` to map a result set automatically.

## 5. Named Parameters and Safe Binding

Spring Data JDBC supports **named parameters** in string-based `@Query`. Names in SQL must match the names declared by `@Param`:

```java
@Modifying
@Query("UPDATE person SET status = :newStatus WHERE id = :personId")
int updateStatus(
        @Param("personId") Long id,
        @Param("newStatus") String status
);
```

Here:

- `:personId` is bound from the argument annotated with `@Param("personId")`.
- `:newStatus` is bound from the argument annotated with `@Param("newStatus")`.
- Java variable names (`id`, `status`) do not have to match the SQL parameter names once `@Param` specifies them explicitly.

If the project enables the `-parameters` compiler option, Spring can discover Java parameter names and allow omitting `@Param` in some configurations. For learning materials and code that needs clarity across different build environments, using explicit `@Param` is generally easier to read.

### Bind Values, Do Not Concatenate SQL Strings

Correct:

```java
@Modifying
@Query("DELETE FROM person WHERE email = :email")
int deleteByEmail(@Param("email") String email);
```

Do not build SQL by concatenating input:

```java
// Do not do this: input data becomes part of the SQL.
String sql = "DELETE FROM person WHERE email = '" + email + "'";
```

Named parameters are bound as values, preventing user data from becoming SQL syntax. However, parameters cannot represent table names, column names, or SQL keywords. If you need to choose a sort column or table dynamically, map the input through an allowed list of identifiers (whitelist) or write fixed methods/queries.

## 6. Managing Transactions for Modifying Queries

`@Modifying` **does not automatically open a transaction** just because the SQL statement is a write command. The query method must run within an appropriate transaction: you can place `@Transactional` directly on the repository method, or call it from an application service that has already opened a transaction.

Example declared on the repository:

```java
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Transactional
    @Query("UPDATE person SET status = :status WHERE id = :id")
    int updateStatus(
            @Param("id") Long id,
            @Param("status") String status
    );
}
```

Or place the transaction on the application service when a use case involves multiple operations:

```java
@Service
public class PersonMaintenanceService {

    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonMaintenanceService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void deactivatePerson(Long id) {
        int updated = personRepository.updateStatus(id, "INACTIVE");

        if (updated != 1) {
            throw new IllegalStateException("Person was not updated");
        }

        auditRepository.save(new AuditEntry(id, "PERSON_DEACTIVATED"));
    }
}
```

In this example, the update and the audit write participate in the same JDBC transaction if the repositories share the same DataSource/transaction manager. If writing the audit entry fails and the exception triggers rollback, the person status update is rolled back as well.

### When a Repository Defaults to `readOnly = true`

A repository interface may have `@Transactional(readOnly = true)` at the interface level for read queries. A modifying method needs to override it with a writable `@Transactional`:

```java
@Transactional(readOnly = true)
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Transactional
    @Query("DELETE FROM person WHERE active = false")
    int deleteInactivePeople();
}
```

`@Transactional` on the write method overrides the interface's read-only setting. If the method is called within an already active outer transaction, the default `REQUIRED` propagation causes it to join that transaction; the actual transaction attributes are governed by the outer transaction.

By default, Spring rolls back on `RuntimeException` and `Error`. Checked exceptions do not automatically trigger rollback unless `rollbackFor` is configured appropriately. Do not catch and swallow an exception inside a transaction if the business logic requires a rollback.

## 7. Modifying Queries Bypass the Aggregate Lifecycle

This is the most important difference between `repository.save(entity)` and `@Modifying @Query`.

| Aspect | `repository.save(root)` | `@Modifying @Query` |
|---|---|---|
| Write path | Spring Data JDBC plans the aggregate write | SQL runs directly against the database |
| Aggregate children | Framework handles owned entities according to mapping | Does not automatically synchronize collections/children |
| Entity callbacks | Can be invoked per lifecycle | Not invoked |
| Lifecycle events | Can be published per lifecycle | Not published |
| Auditing annotations | Can be handled via auditing callbacks | Not updated automatically unless SQL writes audit columns |
| Optimistic locking | Supported via `@Version` when saving aggregate | Does not automatically add version predicates or increment version |
| Objects in memory | Returns the saved aggregate per repository mechanism | Previously loaded objects do not automatically reflect SQL changes |

For example, an entity has:

```java
@LastModifiedDate
private Instant lastModifiedAt;

@LastModifiedBy
private String lastModifiedBy;
```

If you use `@Modifying`:

```java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

`last_modified_at` and `last_modified_by` are not updated automatically by auditing callbacks. If needed, add them directly to the SQL and pass the corresponding values:

```java
@Modifying
@Query("""
    UPDATE person
    SET status = :status,
        last_modified_at = :modifiedAt,
        last_modified_by = :modifiedBy
    WHERE id = :id
    """)
int updateStatusAndAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("modifiedBy") String modifiedBy
);
```

If you need the current user, retrieve them in the application service/security context and pass them as a parameter. Do not rely on `@LastModifiedBy` to populate automatically during direct DML.

## 8. Impact on `@Version` and Optimistic Locking

Spring Data JDBC uses `@Version` during the aggregate save flow to detect concurrent updates. However, `@Modifying @Query` executes SQL directly, so the framework does not automatically:

- Add `AND version = :oldVersion` to `WHERE`.
- Increment the version column.
- Throw `OptimisticLockingFailureException` merely because the `UPDATE` statement affected zero rows.

If a direct update must preserve optimistic locking, write the predicate and version increment explicitly:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available = available - :quantity,
        version = version + 1
    WHERE product_id = :productId
      AND version = :expectedVersion
      AND available >= :quantity
    """)
int reserveStock(
        @Param("productId") Long productId,
        @Param("quantity") int quantity,
        @Param("expectedVersion") Long expectedVersion
);
```

Interpreting the result:

- `1`: update succeeded; quantity was valid, version still matched, and stock was sufficient.
- `0`: no matching row; the ID may not exist, the version may have changed, or stock may be insufficient.

If you need to distinguish among those three causes, execute an appropriate read query after the update fails or design a dedicated business outcome. Do not increment the version in Java and then call `save()` on a stale object to bypass the optimistic lock.

Direct DML can also make previously loaded objects stale:

```java
Person person = personRepository.findById(id).orElseThrow();
personRepository.updateStatus(id, "INACTIVE");

// The person object in memory still holds the old status.
```

After a direct update, reload the entity if you need the latest state. Spring Data JDBC does not have a JPA-style persistence context to automatically synchronize every object held in memory.

## 9. Impact on Aggregates and Child Collections

Suppose `PurchaseOrder` owns `List<OrderLine>`. If you directly execute:

```java
@Modifying
@Query("UPDATE purchase_order SET status = :status WHERE id = :id")
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

The SQL only updates the row in `purchase_order`. It does not invoke the aggregate save process and does not synchronize `order_line`.

If direct DML modifies a child table:

```java
@Modifying
@Query("DELETE FROM order_line WHERE order_id = :orderId AND line_no = :lineNo")
int deleteLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
```

this operation can change the structure of the collection managed by the aggregate root. If the application later loads the root and calls `save()`, Spring Data JDBC works against the current aggregate state; you must ensure the root's invariants still hold.

**When is direct DML appropriate?**

- A simple bulk update that does not need to run domain behavior on each aggregate.
- A maintenance operation with clear conditions wrapped in a transaction.
- An atomic update based on a SQL expression, such as decrementing inventory if sufficient stock remains.
- A delete command for old data under a retention policy, after verifying foreign key relationships and cascades.

**When should you use `save()`?**

- Changes must go through domain methods to protect invariants.
- Owned entities/collections of the aggregate need to be synchronized.
- Lifecycle callbacks, auditing, or automatic optimistic locking are required.
- Entity state and save results need to be reflected in the returned object.

## 10. Foreign Keys and Deletion Order When Using `DELETE`

A direct `DELETE` statement does not automatically apply aggregate ownership rules. The database still enforces foreign keys according to the schema.

Suppose:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id)
);
```

If an `order_line` still references the order, the following statement can fail:

```sql
DELETE FROM purchase_order WHERE id = :id;
```

You can handle this in one of the following ways, depending on ownership and schema:

1. Delete the children first and then delete the root, in the same transaction.
2. Use `ON DELETE CASCADE` if the children truly have a lifecycle wholly dependent on the root and the schema defines this clearly.
3. Do not delete an independent root if historical data must be kept; use soft delete or an archived status.

Example of two modifying queries:

```java
@Modifying
@Query("DELETE FROM order_line WHERE order_id = :orderId")
int deleteLines(@Param("orderId") Long orderId);

@Modifying
@Query("DELETE FROM purchase_order WHERE id = :orderId")
int deleteOrder(@Param("orderId") Long orderId);
```

The application service coordinates them within a single transaction:

```java
@Transactional
public void permanentlyDeleteOrder(Long orderId) {
    orderRepository.deleteLines(orderId);
    int deleted = orderRepository.deleteOrder(orderId);

    if (deleted != 1) {
        throw new IllegalStateException("Order not found");
    }
}
```

If a foreign key from another independent aggregate still references `purchase_order`, the database may still reject deleting the root. Do not use cascades indiscriminately to delete another aggregate's data.

## 11. SQL Constraints and Update/Delete Results

Direct DML is still subject to database constraints:

- **Primary key/unique:** updating a column to a value already in use can cause a duplicate key error.
- **Foreign key:** changing an FK to a nonexistent ID or deleting a referenced parent can fail.
- **Check constraint:** setting quantity/available to an invalid value can be rejected.
- **NOT NULL:** assigning `NULL` to a required column causes an error.
- **Trigger:** database triggers can still fire on DML; this is a database mechanism, not a Spring Data callback.

Example of a conditional status update:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = :newStatus
    WHERE id = :id
      AND status = :expectedStatus
    """)
int transitionStatus(
        @Param("id") Long id,
        @Param("expectedStatus") String expectedStatus,
        @Param("newStatus") String newStatus
);
```

The `expectedStatus` condition performs a status transition that checks the current status. If the updated row count is 0, the status may have already changed or the ID may not exist. This is a form of compare-and-set in the database; if stronger concurrency control is needed, you can add a version column to the condition.

## 12. Testing Modifying Queries

An integration test should verify both the affected row count and the data after the operation.

```java
@DataJdbcTest
class PersonRepositoryTest {

    @Autowired PersonRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void updatesAndDeletesRows() {
        jdbcTemplate.update(
                "INSERT INTO person(id, firstname, lastname, status) VALUES (?, ?, ?, ?)",
                1L, "An", "Tran", "ACTIVE"
        );

        int updated = repository.updateLastname(1L, "Nguyen");
        assertThat(updated).isEqualTo(1);

        String lastname = jdbcTemplate.queryForObject(
                "SELECT lastname FROM person WHERE id = ?",
                String.class,
                1L
        );
        assertThat(lastname).isEqualTo("Nguyen");

        int deleted = repository.deletePerson(1L);
        assertThat(deleted).isEqualTo(1);
        assertThat(repository.findById(1L)).isEmpty();
    }
}
```

The test requires a `person` schema matching the DDL. `@DataJdbcTest` typically runs inside a test transaction and rolls back when finished; if you need to verify an application service's transaction boundary across multiple transactions, design a separate test with explicit commit/rollback behavior.

### Additional Cases to Cover

- Nonexistent ID: `UPDATE`/`DELETE` returns 0.
- Multiple rows match the condition: update count equals the number of rows.
- Underspecified `WHERE`: verify no unintended rows are updated.
- Unique/FK/check constraint violation: exception is thrown and transaction rolls back.
- `@Version`: direct DML query checks and increments the version itself if required by business rules.
- Auditing: audit columns are updated in SQL if needed, since callbacks do not run.
- Child FKs: deleting a root while children exist is rejected or cascades according to schema.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `@Query("UPDATE ...")` method is treated as a read query | Missing `@Modifying` | Add `org.springframework.data.jdbc.repository.query.Modifying` |
| Parameters fail to bind | `:name` does not match `@Param("name")` | Align named parameter names |
| SQL reports column not found | Java property name used instead of SQL column name, or wrong schema | Check DDL and identifier names in the SQL statement |
| `int` returns 0 | No row matched `WHERE`, version/status mismatch, or driver/database reports no row changed | Check predicate and data; distinguish 0 from exceptions |
| `@LastModifiedDate` does not change | Direct DML does not invoke entity callbacks/auditing | Update audit columns directly in SQL |
| `@Version` does not detect conflicts | Direct DML does not automatically check/increment version | Add version condition and increment version explicitly |
| Deleting parent hits FK violation | Children or another root still reference it | Delete children first, handle FK/cascade per ownership |
| In-memory object still holds stale data | Direct SQL does not update already loaded objects | Reload the entity after DML |
| Bulk update breaks invariants | Bypasses domain methods and aggregate lifecycle | Use `save()`/domain behavior or design SQL to protect invariants |
| Multi-step DML writes only partially | No shared transaction or exception swallowed | Put `@Transactional` on the service and verify rollback |

## 14. Process for Choosing `@Modifying @Query` vs. `save()`

1. **Identify the goal:** are you changing an aggregate according to business behavior or running a direct SQL command?
2. **If you need the aggregate lifecycle:** load the root, call the domain method, and `save(root)`.
3. **If direct DML fits:** declare `@Modifying` with `@Query` and use named parameters.
4. **Choose the return type:** `int` to know row count, `boolean` to know whether any row was affected, `void` to ignore the result.
5. **Place the transaction:** use `@Transactional` on the repository method or application service; ensure the same DataSource/transaction manager is used.
6. **Check concurrency:** if using `@Version`, include the version in the condition and update it in SQL.
7. **Check lifecycle side effects:** audit fields, events, callbacks, and child collections must be handled explicitly.
8. **Check constraints:** FKs, unique, check, nullability, and cascade behavior.
9. **Test:** verify the update count, data after the operation, rollback, and no-matching-row cases.

### Quick Decision Table

| Need | Appropriate approach |
|---|---|
| Modify an entity by domain rules and synchronize children | `repository.save(root)` |
| Directly update a few columns with SQL | `@Modifying` + `@Query` |
| Delete multiple rows by a simple condition | `@Modifying` + `@Query` or derived `deleteBy...` |
| Need number of affected rows | Return `int` |
| Only need to know if any row changed | Return `boolean` |
| Need automatic lifecycle callbacks/auditing | Use aggregate persistence; direct DML must write audit columns manually |
| Need automatic optimistic locking | Use `save()` with `@Version`; for direct DML, check/increment version manually |
| Need generated keys or rows from `RETURNING` | Custom JDBC repository/operations, not standard modifying return types |

**Key takeaway:** `@Modifying` marks a `@Query` statement as DML for Spring Data JDBC to execute directly. Use named parameters to bind values and choose `int`, `boolean`, or `void` as needed. Place the transaction at the use-case boundary when multiple steps are involved. Because direct DML bypasses aggregate callbacks, lifecycle events, auditing, and automatic optimistic locking, the application must actively handle related side effects, versions, FKs, and invariants.

## Official References

- [Spring Data JDBC — Query Methods: Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): `@Modifying` syntax with `@Query`, return types, and skipping callbacks/events.
- [Spring Data JDBC — `@Modifying` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Modifying.html): annotation marking a method as a modifying query.
- [Spring Data JDBC — `@Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): SQL string and named parameters.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transactions for repository query methods and modifying query examples.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, propagation, and rollback rules.
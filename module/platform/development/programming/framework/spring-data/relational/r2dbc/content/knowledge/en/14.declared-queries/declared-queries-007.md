# Return Types and Affected Row Counts for Data-Modifying Queries

In Spring Data R2DBC, a repository can declare SQL directly using **@Query**. When a SQL statement modifies data—such as **INSERT**, **UPDATE**, or **DELETE**—the return type should accurately express what the application cares about: knowing only whether the operation completed, or knowing how many rows were affected.

For data-modifying queries declared with **@Query**, **@Modifying** marks the method as a write operation. A numeric return type can represent the affected row count; **Mono<Void>** is suitable when only a completion or error signal is needed. If the SQL needs to return data rows—for example using PostgreSQL's **RETURNING**—that is a different kind of result and requires choosing an API that reads row results.

## 1. Declared queries and data-modifying queries

Spring Data R2DBC allows declaring SQL statements directly on repository methods:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Query("SELECT * FROM person WHERE status = :status")
    Flux<Person> findByStatus(String status);
}
~~~

For **SELECT** statements, methods typically return **Mono<T>** or **Flux<T>**, depending on cardinality. Spring Data reads the rows and maps them to Java types.

For data-modifying statements, the goal is usually to execute the SQL and obtain the affected row count:

~~~sql
UPDATE person
SET status = 'INACTIVE'
WHERE last_seen < CURRENT_TIMESTAMP - INTERVAL '1 year';
~~~

No entity necessarily has to be returned by this statement. The database may only provide the count of updated rows. Consequently, the return type should describe the update outcome instead of declaring **Mono<Person>** like a regular read query.

## 2. Role of @Modifying

**@Query** declares the SQL to run. For data-modifying queries, **@Modifying** informs Spring Data that the method is a modifying query:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Modifying
    @Query("UPDATE person SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(Long id, String status);
}
~~~

In this example:

- **@Query** contains the update SQL statement.
- **@Modifying** marks this as a data-modifying operation.
- **Mono<Integer>** emits the affected row count after the statement executes.

For declared query methods, use annotations matching their purpose. Do not declare an UPDATE statement and expect Spring Data to treat it like a SELECT query returning entities.

Named parameters like :id and :status are bound from method parameters. If your project does not retain parameter names in bytecode or you want explicit declarations, use **@Param**:

~~~java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

Never concatenate input values directly into SQL. Parameter binding passes values safely and separates data from statement structure.

## 3. Return types representing affected row counts

For modifying queries, a numeric return type reports how many rows the database indicates were affected. A common declaration:

~~~java
@Modifying
@Query("UPDATE inventory SET quantity = :quantity WHERE id = :id")
Mono<Integer> updateQuantity(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

When the publisher emits:

- **1**: one row was updated.
- **0**: no row matched the condition or no row was reported as affected according to driver/database semantics.
- Greater than **1**: multiple rows were affected, typically when the WHERE condition matched several records.

The row count is not the updated entity. Nor does it explain by itself why the count is 0. The application must interpret the value based on its business contract and SQL conditions.

Some versions/APIs may support other numeric types such as **Long** for larger counts. Use a return type supported for modifying queries by your Spring Data R2DBC version; do not assume all numeric types are accepted equally.

## 4. When only completion matters: Mono<Void>

If the caller does not need the row count, you can declare a publisher that emits no value:

~~~java
@Modifying
@Query("DELETE FROM session_token WHERE expires_at < :cutoff")
Mono<Void> deleteExpiredTokens(@Param("cutoff") Instant cutoff);
~~~

**Mono<Void>** represents an operation that can either complete or terminate with an error. It does not emit the deleted row count. When the publisher completes normally, the caller knows the statement executed successfully under the driver contract; if the SQL, connection, or transaction fails, the publisher emits an error.

Choose **Mono<Void>** when the row count has no effect on business decisions. If you need to distinguish "record not found" from "updated one record", use a numeric row-count return type.

## 5. Distinguishing zero rows from errors

An affected row count of 0 is usually a valid outcome, not necessarily a database error.

Example:

~~~sql
UPDATE person
SET status = 'ACTIVE'
WHERE id = 999999;
~~~

If no person exists with that ID, the statement is still valid, just affecting no rows. The database can return a count of 0 and the publisher completes normally.

By contrast, the following situations typically emit an error signal:

- Invalid SQL syntax.
- Non-existent table or column.
- Database user lacks update permissions.
- Value violates a constraint.
- Dropped connection or timeout.
- Transaction rolled back or errored.

Therefore, distinguish:

| Outcome | Meaning |
| --- | --- |
| **Mono<Integer>** emits **0** then completes | SQL executed, with zero rows reported as affected |
| **Mono<Integer>** emits a positive number then completes | SQL executed and the database reported affected rows |
| **Mono<Void>** completes | Operation completed; no row count available to interpret |
| Publisher emits error | Operation failed due to SQL, driver, database, or transaction |

Do not use **onErrorResume** to turn all errors into 0 if business logic needs to know the database experienced a failure. Doing so disguises infrastructure failures as "no matching rows" and makes diagnosis harder.

## 6. Interpreting row counts in the service layer

A service can translate the row count into business outcomes:

~~~java
public Mono<Void> activatePerson(Long id) {
    return personRepository.updateStatus(id, "ACTIVE")
            .flatMap(rowsUpdated -> {
                if (rowsUpdated == 1) {
                    return Mono.empty();
                }

                if (rowsUpdated == 0) {
                    return Mono.error(new PersonNotFoundException(id));
                }

                return Mono.error(new IllegalStateException(
                        "Expected one row to be updated, got " + rowsUpdated
                ));
            });
}
~~~

Here, business logic expects exactly one person to be updated. Zero rows is converted into a not-found error; more than one row signals a flaw in the condition or uniqueness assumption.

Not every use case should treat 0 as an error. For example, an expired-data cleanup job may legitimately find zero rows to delete. How to interpret the count must come from business requirements.

## 7. UPDATE example with affected row counts

A repository can declare multiple write operations:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("UPDATE account SET status = :status WHERE id = :id")
    Mono<Integer> changeStatus(
            @Param("id") Long id,
            @Param("status") String status
    );

    @Modifying
    @Query("UPDATE account SET balance = balance - :amount WHERE id = :id")
    Mono<Integer> debit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount
    );
}
~~~

The service can verify that one row was updated:

~~~java
public Mono<Void> debitAccount(Long accountId, BigDecimal amount) {
    if (amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Amount must be positive"
        ));
    }

    return accountRepository.debit(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(new AccountNotFoundException(accountId));
                }
                return Mono.error(new IllegalStateException(
                        "Unexpected affected row count: " + rows
                ));
            });
}
~~~

This example only illustrates reading row counts. In financial systems, a debit statement needs additional conditions like **balance >= :amount**, concurrency control, transactions, and idempotency rules. Without a balance check, the statement could push the balance negative.

A single statement can combine business guards into SQL:

~~~sql
UPDATE account
SET balance = balance - :amount
WHERE id = :id
  AND balance >= :amount;
~~~

When the row count is 0, either the account does not exist or the balance is insufficient. If you need to distinguish the two cases, design an additional query/result type or use a statement returning detailed database output.

## 8. DELETE example and deleted row counts

For delete queries, the row count reveals how many records matched the condition:

~~~java
public interface SessionRepository
        extends ReactiveCrudRepository<Session, Long> {

    @Modifying
    @Query("DELETE FROM session WHERE user_id = :userId")
    Mono<Integer> deleteSessionsByUserId(@Param("userId") Long userId);
}
~~~

The service can use the row count to report the result:

~~~java
public Mono<Integer> revokeAllSessions(Long userId) {
    return sessionRepository.deleteSessionsByUserId(userId);
}
~~~

If the publisher emits **5**, the database reported five session rows deleted. If it emits **0**, no sessions matched. That is not an error if the user never had any sessions or sessions were already revoked.

For scheduled cleanup tasks, **Mono<Integer>** or an equivalent numeric type is helpful for recording metrics. For tasks where only completion matters, **Mono<Void>** can be simpler.

## 9. INSERT and the difference between row count and generated data

An **INSERT** statement is also a modifying query:

~~~java
@Modifying
@Query("INSERT INTO tag (name) VALUES (:name)")
Mono<Integer> insertTag(@Param("name") String name);
~~~

The row count tells you how many rows were inserted. However, it does not return auto-generated IDs or the complete inserted entity.

If you need generated IDs or database-populated columns, use an API capable of reading returned results. With PostgreSQL, **RETURNING** can return data:

~~~sql
INSERT INTO tag (name)
VALUES (:name)
RETURNING id, name;
~~~

When you need to map returned rows, use **DatabaseClient** or an API suited for row results:

~~~java
public Mono<Tag> insertTag(String name) {
    return databaseClient.sql("""
            INSERT INTO tag (name)
            VALUES (:name)
            RETURNING id, name
            """)
            .bind("name", name)
            .map((row, metadata) -> new Tag(
                    row.get("id", Long.class),
                    row.get("name", String.class)
            ))
            .one();
}
~~~

**RETURNING** is a feature of PostgreSQL and some other databases with their own syntax. Do not assume every database or every modifying repository method supports returning entities the same way.

## 10. Using DatabaseClient.rowsUpdated() when SQL control is needed

When custom SQL is required or you want direct access to the affected row count, **DatabaseClient** provides **rowsUpdated()**:

~~~java
public Mono<Long> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE person
            SET status = :status
            WHERE id = :id
            """)
            .bind("id", id)
            .bind("status", status)
            .fetch()
            .rowsUpdated();
}
~~~

This API returns a publisher of the updated row count using the numeric type provided by your Spring Framework version. Keep the exact type declared by the library; avoid converting arbitrarily between **Integer** and **Long** unless necessary.

Comparison:

| Access approach | When suitable |
| --- | --- |
| **@Query** + **@Modifying** | Data-modifying SQL declared directly on a repository |
| **DatabaseClient.fetch().rowsUpdated()** | Need dynamic SQL building or direct update-count handling |
| **R2dbcEntityTemplate.update(...)** | Want updates driven by entity metadata and **Query**/**Update** |
| **repository.save(entity)** | Saving an entity according to Spring Data's new/existing state |

## 11. Return types of data-modifying queries and transactions

A modifying query can run inside a reactive transaction. Example:

~~~java
@Transactional
public Mono<Void> transferStatus(Long fromId, Long toId) {
    return accountRepository.changeStatus(fromId, "TRANSFERRED")
            .flatMap(sourceRows -> {
                if (sourceRows != 1) {
                    return Mono.error(new IllegalStateException(
                            "Source account was not updated"
                    ));
                }

                return accountRepository.changeStatus(toId, "ACTIVE")
                        .flatMap(targetRows -> targetRows == 1
                                ? Mono.empty()
                                : Mono.error(new IllegalStateException(
                                        "Target account was not updated"
                                )));
            });
}
~~~

If one step emits an error and the publishers are managed within the same reactive transaction, the transaction manager can roll back earlier changes according to its configuration and rollback rules. Never call **subscribe()** inside the method; return the publisher so the transaction interceptor manages the full lifecycle.

Affected row counts do not create transactions on their own. They are simply statement results. Atomicity across multiple statements depends on transaction boundaries and the database.

## 12. Affected row counts and optimistic locking

Optimistic locking uses **@Version** to detect if an entity changed since it was read. When using Spring Data-managed save operations, a version mismatch on update is normally translated into an optimistic locking error instead of silently overwriting.

For hand-written modifying queries, if you want optimistic locking, the SQL must include the current version in the condition and increment the version:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

The method can return the row count:

~~~java
@Modifying
@Query("""
        UPDATE inventory
        SET quantity = :quantity,
            version = version + 1
        WHERE id = :id
          AND version = :expectedVersion
        """)
Mono<Integer> updateQuantity(
        @Param("id") Long id,
        @Param("quantity") int quantity,
        @Param("expectedVersion") Long expectedVersion
);
~~~

If the result is **1**, the row was updated at the expected version. If **0**, the row may not exist or the version changed. The application must decide whether to re-query to distinguish the two or return a conflict error.

A hand-written modifying query does not automatically get the full optimistic locking behavior of Spring Data-managed entity saves. The SQL itself must express both the version predicate and version increment.

## 13. Reported row counts may differ from business interpretation

Affected row counts are values reported by the database/driver for the executed statement. Exact counting behavior can depend on the database engine, triggers, statement structure, driver, and execution mode.

For example:

- An UPDATE statement may match a row while assigning the exact same value it already had. Databases may report matched rows or actually changed rows depending on the engine.
- Triggers can perform additional operations on other tables; the count returned by the main statement does not necessarily reflect the total side effects from triggers.
- Multi-part or batched statements can return counts per result depending on the API and driver.
- A DELETE statement may cascade-delete related rows; the count returned by the primary delete should not be assumed to include all cascaded rows unless defined by the database.

Therefore, treat the affected row count as the statement's execution result under the database's semantics. If business logic needs the exact list of changed entities or total cascaded changes, design a dedicated query/audit rather than inferring it from a single count.

## 14. Cases requiring returned data rows instead of row counts

Some databases support DML statements that return data:

~~~sql
UPDATE person
SET status = 'ACTIVE'
WHERE id = 42
RETURNING id, status;
~~~

These results are data rows, not just an affected row count. With PostgreSQL, **RETURNING** is useful when retrieving updated values or generated IDs without running a separate SELECT query.

When returned data is needed, use **DatabaseClient.map(...).all()** or an appropriate API to map rows. Do not declare a numeric row-count return type if the caller actually needs the columns from **RETURNING**.

Example:

~~~java
public Mono<PersonStatus> activate(Long id) {
    return databaseClient.sql("""
            UPDATE person
            SET status = 'ACTIVE'
            WHERE id = :id
            RETURNING id, status
            """)
            .bind("id", id)
            .map((row, metadata) -> new PersonStatus(
                    row.get("id", Long.class),
                    row.get("status", String.class)
            ))
            .one();
}
~~~

Verify syntax and support in your target database before using **RETURNING**. If the database does not support it, you may need a transaction and a follow-up read query.

## 15. Common mistakes

1. **Forgetting @Modifying on declared DML queries.** Spring Data needs to know the query modifies data.
2. **Declaring Mono<Entity> for an UPDATE that only returns a row count.** Choose a return type matching the actual result.
3. **Using Mono<Void> when you need to distinguish 0 vs. 1 row.** Use a numeric type when the count carries business meaning.
4. **Treating 0 as an error unconditionally.** Having zero matching rows can be a valid outcome.
5. **Treating a positive count as full business success.** Affected counts do not replace validation, transactions, or downstream checks.
6. **Swallowing errors into 0.** Connection or SQL failures must stay errors rather than masquerading as not-found.
7. **Confusing affected rows with cascaded rows.** The primary statement's count does not necessarily include all side effects.
8. **Using a modifying query to upsert without upsert SQL.** @Modifying does not synthesize insert-or-update semantics.
9. **Forgetting to check WHERE conditions.** An update/delete missing a condition can affect far too many rows.
10. **Assuming @Modifying returns the entity after UPDATE.** Receiving rows from DML requires row-returning APIs and syntax such as RETURNING.
11. **Assuming affected counts share identical semantics across all databases.** Verify the target driver and engine.
12. **Calling subscribe manually inside a transactional service.** Return the publisher so the transaction manager coordinates completion and rollback.

## Quick selection rules

- Use **@Query** to declare SQL and **@Modifying** to mark data-modifying statements.
- Use **Mono<Integer>** or a version-supported numeric type when you need the affected row count.
- Use **Mono<Void>** when you only care whether the operation completes or errors.
- Handle 0 according to business rules; it is not automatically a database error.
- Use **DatabaseClient.fetch().rowsUpdated()** when custom SQL and affected counts are needed.
- Use **RETURNING** with a row-mapping API when you need data back after INSERT/UPDATE/DELETE and the database supports it.
- Include version predicates in SQL when writing modifying queries with optimistic locking.
- Use reactive transactions when multiple operations must commit or roll back together.
- Verify affected-count semantics on the exact database and driver deployed.

The return type of a data-modifying query is part of the contract between the repository and service layers. The affected row count reports how many rows the database indicates were updated, inserted, or deleted; **Mono<Void>** only reports completion or failure. When you need the entity or updated data after DML, use an API that returns rows instead of inferring them from a count. Distinguishing these outcomes helps services handle zero-match cases, concurrency conflicts, and execution errors properly.

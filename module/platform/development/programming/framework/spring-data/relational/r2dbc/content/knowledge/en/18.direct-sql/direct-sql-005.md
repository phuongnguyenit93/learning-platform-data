# Receiving Affected Row Counts with rowsUpdated

When executing an INSERT, UPDATE, or DELETE statement through Spring R2DBC, an application often needs to know how many rows the database affected. Spring R2DBC's **rowsUpdated()** API provides the number of rows reported as changed by the SQL operation. This value is useful for confirming whether an update found a record, verifying deletions, handling optimistic locking, or recording the outcome of a write command.

With **DatabaseClient**, the common usage is:

~~~java
Mono<Long> affectedRows = databaseClient
    .sql("UPDATE customer SET active = :active WHERE id = :id")
    .bind("active", false)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
~~~

The result is a reactive publisher of type Mono<Long>. DatabaseClient executes the SQL when the publisher is subscribed to and emits the row count reported by the driver/database for that statement. This is the number of affected rows, not the updated entity or a newly generated ID.

## 1. What Is rowsUpdated() Used For?

rowsUpdated() returns the number of rows reported as updated by the SQL statement. In a DML context, it can be used for:

- INSERT: number of inserted rows.
- UPDATE: number of updated rows as reported by the driver/database.
- DELETE: number of deleted rows.

For example, if an UPDATE statement has WHERE id = :id and only one row matches, the result is typically 1. If no row matches, the result is typically 0.

This count helps the application decide what to do next:

- **1**: the operation affected exactly one row as expected.
- **0**: no rows were affected; the record might not exist, the condition might not match, or the version might be stale.
- **Greater than 1**: the condition may be broader than intended, or business logic permits updating multiple rows.

Remember that rowsUpdated is the result provided by the database/driver. In some DBMSs, the concepts of "affected rows" and "rows whose values actually changed" can differ, especially when an UPDATE assigns a value that is already present. If business logic depends on that distinction, verify the behavior of your target database and driver.

## 2. Using rowsUpdated() with DatabaseClient

DatabaseClient belongs to Spring R2DBC. It provides an API to execute SQL, bind parameters, and read results. When only the affected row count is needed, use fetch().rowsUpdated() instead of mapping each Row.

Example service updating customer status:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class CustomerSqlRepository {

    private final DatabaseClient databaseClient;

    public CustomerSqlRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Long> deactivate(Long customerId) {
        return databaseClient.sql("""
                UPDATE customer
                SET active = FALSE
                WHERE id = :id
                """)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
    }
}
~~~

The method returns Mono<Long>. Callers can combine the result with business logic:

~~~java
return customerSqlRepository.deactivate(customerId)
    .map(rows -> rows == 1);
~~~

If you only need to know whether the operation affected exactly one row, you can map the count to a Boolean. If you need to distinguish not-found, success, and updating too many rows, inspect the concrete count rather than collapsing it to true/false.

### 2.1. General Syntax

~~~java
Mono<Long> count = databaseClient
    .sql("Parameterized DML SQL")
    .bind("parameterName", parameterValue)
    .fetch()
    .rowsUpdated();
~~~

Steps:

1. sql(...) supplies the statement.
2. bind(...) attaches values to named parameters.
3. fetch() selects the result-reading API.
4. rowsUpdated() requests the affected row count.

Do not concatenate input data directly into the SQL string. Parameter binding separates data from SQL syntax and avoids quoting bugs as well as SQL injection risks.

### 2.2. Binding NULL Values

Do not pass null directly to bind(name, value). When a parameter may be null, use bindNull and specify the Java type:

~~~java
Mono<Long> clearEmail(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bindNull("email", String.class)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Declaring the type tells the driver what data type to bind even when the value is null. The Java type must be compatible with the column and driver capabilities.

## 3. Counting Rows on INSERT

For a regular INSERT, rowsUpdated() reports the number of rows the driver says were inserted.

~~~java
Mono<Long> insertCustomer(String fullName, String email) {
    return databaseClient.sql("""
            INSERT INTO customer (full_name, email, active)
            VALUES (:fullName, :email, TRUE)
            """)
        .bind("fullName", fullName)
        .bind("email", email)
        .fetch()
        .rowsUpdated();
}
~~~

If inserting one row succeeds and the driver reports counts, the result is usually 1.

However, rowsUpdated() does not return auto-generated IDs. If you need the ID, use the generated-values mechanism supported by the driver or SQL syntax like RETURNING on databases that support it.

PostgreSQL example:

~~~java
Mono<Long> insertAndGetId(String fullName, String email) {
    return databaseClient.sql("""
            INSERT INTO customer (full_name, email, active)
            VALUES (:fullName, :email, TRUE)
            RETURNING id
            """)
        .bind("fullName", fullName)
        .bind("email", email)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
~~~

In this example, the application reads the ID value from a result row. This is a data-returning query, distinct from merely fetching the row count with rowsUpdated(). RETURNING is DBMS-specific syntax; verify your driver and database.

## 4. Counting Rows on UPDATE

Example updating email by ID:

~~~java
Mono<Long> updateEmail(Long customerId, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

The result is typically interpreted as:

| Value | Possible Meaning |
|---:|---|
| 0 | No rows were reported as updated |
| 1 | One row was reported as updated |
| Greater than 1 | Multiple rows were reported as updated |

If id is a primary key, the expected result is usually 0 or 1. If it is greater than 1, review the schema or statement because a primary-key predicate should not affect multiple rows.

If an UPDATE lacks a sufficiently selective condition, multiple rows may be affected. Always define the update scope clearly and consider UNIQUE/PRIMARY KEY constraints on identifying columns.

### 4.1. Assigning the Same Value Again

A statement such as:

~~~sql
UPDATE customer
SET active = TRUE
WHERE id = 10
~~~

may find the row while active is already TRUE. The reported count can depend on database/driver semantics: some DBMSs report matched rows, while some modes report rows whose values actually changed.

Therefore, do not rely on rowsUpdated as portable proof that a value in the database definitely changed from an old value to a new value. If business logic needs to know the before/after state, design an explicit query or comparison condition.

### 4.2. Updating Only When the Value Differs

You can add a condition to skip rows that already have the desired value:

~~~java
Mono<Long> activateIfInactive(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = TRUE
            WHERE id = :id
              AND active = FALSE
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Here, a count of 1 means a row matching both the ID and inactive status was updated; a count of 0 means no row matched the full condition. It still does not distinguish a missing record from a record that was already active.

## 5. Counting Rows on DELETE

DELETE can also use rowsUpdated():

~~~java
Mono<Long> deleteCustomer(Long customerId) {
    return databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
}
~~~

Typical outcomes are:

- 1: one row deleted.
- 0: no rows matched the condition.
- Greater than 1: the delete condition affected multiple rows.

If customer is referenced by other tables via foreign keys, the database may reject DELETE due to RESTRICT/NO ACTION or apply ON DELETE CASCADE/SET NULL per the schema. When a constraint is violated, the publisher emits an error instead of returning a count of 0.

rowsUpdated() does not mask constraint errors. Handle errors according to business semantics, such as disallowing deletion of a customer with existing orders.

## 6. Distinguishing 0 Rows from SQL Errors

These are two different outcomes:

- **Count of 0**: the SQL statement executed, but no rows were reported as affected.
- **Publisher emits an error**: the statement failed to execute successfully, such as constraint violation, syntax error, connection failure, or binding error.

Example:

~~~java
return deleteCustomer(customerId)
    .flatMap(rows -> {
        if (rows == 0) {
            return Mono.error(
                new CustomerNotFoundException(customerId)
            );
        }

        return Mono.just(rows);
    });
~~~

This snippet turns a count of 0 into a business error. If the database emits an error before producing a count, that error follows the onError path and does not run the success flatMap branch.

Do not broadly use onErrorReturn(0L) to turn all database errors into a count of 0. Doing so equates a missing record with connection failures, constraint violations, or SQL syntax errors, causing the application to report misleading results.

## 7. Handling Counts According to Business Expectations

Many operations expect a specific row count. You can write a helper to enforce exactly one row:

~~~java
private Mono<Void> requireOneRow(Mono<Long> rowsUpdated) {
    return rowsUpdated.flatMap(rows -> {
        if (rows == 1) {
            return Mono.empty();
        }

        if (rows == 0) {
            return Mono.error(
                new IllegalStateException("No row was updated")
            );
        }

        return Mono.error(
            new IllegalStateException(
                "Expected one row, but affected " + rows
            )
        );
    });
}
~~~

Usage:

~~~java
public Mono<Void> renameCustomer(Long id, String newName) {
    Mono<Long> rows = databaseClient.sql("""
            UPDATE customer
            SET full_name = :name
            WHERE id = :id
            """)
        .bind("name", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();

    return requireOneRow(rows);
}
~~~

This helper works well when business logic requires exactly one row. For batch operations or multi-record updates, define another rule, such as a minimum count, exact expected count, or simply logging the total row count.

In real systems, use more meaningful domain exceptions than IllegalStateException, such as CustomerNotFoundException or ConcurrentCustomerUpdateException.

## 8. rowsUpdated() and Optimistic Locking

Optimistic locking uses a version to detect when two operations concurrently update the same record based on stale state.

Suppose the customer table has a version column. A manual update statement can be written as:

~~~java
Mono<Long> updateWithVersion(
        Long id,
        Long expectedVersion,
        String newName) {

    return databaseClient.sql("""
            UPDATE customer
            SET full_name = :name,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """)
        .bind("name", newName)
        .bind("id", id)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated();
}
~~~

Interpretation:

- Count 1: the row with matching ID and version was updated.
- Count 0: no row matched the condition. Either the record does not exist or the version was already incremented by another operation.
- Count greater than 1: the condition does not uniquely identify a row or the schema differs from expectations.

When using a Spring Data R2DBC entity with @Version, the persistence mechanism automatically adds the version predicate and increments the version. When optimistic locking fails, Spring Data typically throws an optimistic locking failure rather than requiring the caller to interpret counts manually. With direct SQL via DatabaseClient, the application is responsible for inspecting rowsUpdated and mapping count 0 to a conflict or not-found error per business policy.

Do not increment version in both the service and the SQL statement if Spring Data already manages version for the same operation. Avoid double-incrementing version or omitting the version predicate.

## 9. rowsUpdated() with UPDATE/DELETE in R2dbcEntityTemplate

If operating at the entity level and wanting to leverage Spring Data mapping, you can use R2dbcEntityTemplate. Its fluent update/delete operations return the affected row count via the corresponding count publisher API.

Example update by Criteria:

~~~java
Query query = Query.query(
    Criteria.where("id").is(customerId)
);

Update update = Update.update("active", false);

Mono<Long> rowsUpdated =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

Example delete by condition:

~~~java
Mono<Long> rowsDeleted =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

The template fits when conditions are constructed dynamically with Query/Criteria and you want Spring Data to handle entity mapping, conversions, and dialect. DatabaseClient fits when you want to write SQL directly.

Distinguish count-returning APIs from standard CRUD repositories. For instance, ReactiveCrudRepository.deleteById(id) typically returns Mono<Void> to signal completion or error without providing a deleted row count. If you need the count, pick a count-returning API like template or DatabaseClient, or design an appropriate custom repository query.

## 10. rowsUpdated() and R2DBC SPI Result

Beneath Spring DatabaseClient lies the R2DBC SPI. Executing a Statement returns Results. R2DBC Result exposes getRowsUpdated() to read the number of rows updated by that result.

Conceptually:

~~~java
Publisher<? extends Result> results =
    connection.createStatement(
        "UPDATE customer SET active = FALSE WHERE id = 10"
    ).execute();
~~~

Each Result can provide a row-count publisher:

~~~java
Publisher<Long> countPublisher =
    result.getRowsUpdated();
~~~

Spring DatabaseClient wraps the execution lifecycle and adapts results into familiar Reactor types, so applications typically write:

~~~java
Mono<Long> count =
    databaseClient.sql(
        "UPDATE customer SET active = FALSE WHERE id = :id"
    )
    .bind("id", 10L)
    .fetch()
    .rowsUpdated();
~~~

When using the SPI directly, the application must manage connections, statements, results, and closing connections manually. DatabaseClient reduces that boilerplate and integrates with Spring's infrastructure.

A statement can produce multiple Results, or drivers may report update counts differently depending on statement type. When executing batches or multiple statements, verify how the driver emits counts and how the API aggregates them; do not extrapolate single-statement count behavior to all batches.

## 11. rowsUpdated() Is Not the Number of Rows Returned by SELECT

rowsUpdated() is for the row count affected by write statements. It is not an API for counting rows returned by a SELECT.

To read data, use map/fetch:

~~~java
Flux<Customer> customers =
    databaseClient.sql("""
            SELECT id, full_name, email
            FROM customer
            WHERE active = TRUE
            """)
        .map((row, metadata) ->
            new Customer(
                row.get("id", Long.class),
                row.get("full_name", String.class),
                row.get("email", String.class),
                null,
                true,
                null
            )
        )
        .all();
~~~

To count rows matching a SELECT condition, use COUNT(*):

~~~java
Mono<Long> countCustomers =
    databaseClient.sql("""
            SELECT COUNT(*)
            FROM customer
            WHERE active = TRUE
            """)
        .map((row, metadata) -> row.get(0, Long.class))
        .one();
~~~

Differences:

| Need | Appropriate API |
|---|---|
| Know how many rows UPDATE affected | fetch().rowsUpdated() |
| Know how many rows DELETE removed | fetch().rowsUpdated() |
| Know how many rows INSERT created | fetch().rowsUpdated() |
| Read SELECT rows | map(...).all() |
| Read a single SELECT row | map(...).one() or first() |
| Count rows matching a SELECT condition | SELECT COUNT(*) and map result |

With SQL using RETURNING, if you need returned values like an ID or new status, map the result rows. Do not use a count in place of returned data.

## 12. Reactive Execution: When Does SQL Actually Run?

DatabaseClient returns Mono/Flux under the reactive model. Publishers are typically lazy: SQL executes when the publisher is subscribed to, directly or via a framework subscriber.

Example:

~~~java
Mono<Long> rows =
    databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated();
~~~

At the moment rows is assigned, the application has only constructed the publisher. The SQL has not necessarily been sent to the database yet. When the controller, service, or framework subscribes to the publisher, the operation executes.

Do not call subscribe() inside a service just to obtain the count and continue processing. Return the publisher or compose it with map/flatMap:

~~~java
public Mono<String> deleteMessage(Long id) {
    return deleteCustomer(id)
        .map(rows -> rows == 1
            ? "Customer deleted"
            : "Customer not found"
        );
}
~~~

This keeps errors, results, and transactions inside the same reactive chain.

## 13. Transactions and the Meaning of Count

rowsUpdated reports the outcome of a single statement, but it does not guarantee that the enclosing transaction has committed.

Consider a transaction with two operations:

1. UPDATE customer.
2. INSERT audit_log.

If step 1 returns a count of 1 but step 2 fails, the transaction can roll back. After rollback, the customer change no longer exists in the database even though the rowsUpdated publisher emitted 1 inside the transaction.

Multiple operations can be coordinated in a reactive transaction:

~~~java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional
public Mono<Long> deactivateAndAudit(Long customerId) {
    return databaseClient.sql("""
            UPDATE customer
            SET active = FALSE
            WHERE id = :id
            """)
        .bind("id", customerId)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(
                    new CustomerNotFoundException(customerId)
                );
            }

            return databaseClient.sql("""
                    INSERT INTO audit_log (entity_id, action)
                    VALUES (:id, 'DEACTIVATE')
                    """)
                .bind("id", customerId)
                .fetch()
                .rowsUpdated()
                .thenReturn(rows);
        });
}
~~~

This example assumes both operations use the same ConnectionFactory and reactive transaction manager. If the audit insert fails, the error propagates through the same publisher chain so the transaction can roll back.

Do not call block() or subscribe() inside a transactional method. Do not split operations into independently running publishers if they need to participate in the same transaction context.

## 14. Error Handling and Logging

You can log the row count after the operation completes:

~~~java
return updateEmail(customerId, email)
    .doOnNext(rows ->
        log.info("Updated customer rows: {}", rows)
    );
~~~

Log only necessary data. Never log passwords, tokens, or sensitive values bound into SQL.

You can translate technical errors or counts into business errors:

~~~java
return updateWithVersion(id, expectedVersion, newName)
    .flatMap(rows -> {
        if (rows == 1) {
            return Mono.just("Updated");
        }
        if (rows == 0) {
            return Mono.error(
                new ConcurrentCustomerUpdateException(id)
            );
        }
        return Mono.error(
            new IllegalStateException(
                "Unexpected affected row count: " + rows
            )
        );
    });
~~~

In practice, a count of 0 could mean either the record does not exist or the version no longer matches. If the API must distinguish both cases, perform an additional check or design explicit errors/update conditions. Any follow-up check must also account for race conditions.

## 15. Common Mistakes

### 15.1. Using rowsUpdated() for SELECT

SELECT returns row data, not a DML affected row count. Use map(...).all(), one(), first(), or SELECT COUNT(*).

### 15.2. Treating Count 0 as a SQL Error

A count of 0 is usually a valid outcome: the statement ran successfully, but no rows matched. Convert it to an error only if business logic requires rows to be affected.

### 15.3. Assuming Count 1 Means the Transaction Committed

The count is the statement result. The transaction can still roll back later if another operation fails.

### 15.4. Assuming rowsUpdated Returns Generated IDs

The count is only the number of rows. To get an ID, use generated values or SQL RETURNING and map the ID column.

### 15.5. Ignoring the Count When One Row Must Be Confirmed

If an update by ID must affect exactly one row, do not discard the result. Check the count to detect missing records or invalid conditions.

### 15.6. Turning All Errors into 0

Do not broadly apply onErrorReturn(0L). Connection, constraint, and SQL syntax errors do not mean zero matching rows.

### 15.7. Omitting Parameter Binding

Concatenating input values into SQL risks syntax errors and SQL injection. Use bind/bindNull for all data values.

### 15.8. Using Count to Infer Whether Values Changed

Databases and drivers can define affected-row counts differently when an UPDATE assigns the existing value. If business logic needs to know whether a change occurred, check DBMS semantics or design the statement accordingly.

## 16. Choosing the Right API

| Need | Recommended API |
|---|---|
| Direct SQL needing a count | DatabaseClient.fetch().rowsUpdated() |
| Entity-mapped update/delete needing a count | R2dbcEntityTemplate |
| Simple CRUD repository needing only completion | ReactiveCrudRepository |
| Custom repository query needing a count | Custom query method with version-supported return type |
| Need ID or values after INSERT/UPDATE | Generated values, RETURNING, and result mapping |
| Need to count SELECT rows | SELECT COUNT(*) |
| Need to read SELECT contents | map(...).all()/one()/first() |

If you only need to know whether deleteById completed or errored, a CRUD repository suffices. If you need the reported affected row count, use a count-returning API such as DatabaseClient or R2dbcEntityTemplate.

## 17. Key Takeaways

Spring R2DBC's rowsUpdated() returns a Mono<Long> representing the number of rows reported by the database/driver as affected by a write operation. Use it with INSERT, UPDATE, and DELETE when inspecting counts; use map/fetch for SELECT and RETURNING data; use COUNT(*) when counting query results.

A count of 0 is not automatically an error, a count of 1 usually fits single-ID operations, and counts greater than 1 must be evaluated against the conditions and business rules. Counts are neither generated IDs nor proof of transaction commit. Bind parameters, handle errors separately from count 0, check optimistic locking where needed, and keep publishers in the same reactive transaction chain.

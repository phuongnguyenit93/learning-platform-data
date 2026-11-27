# Classifying Connection, Syntax, Mapping, and Data Constraint Errors

When working with Spring Data Relational R2DBC, an error that surfaces at a repository does not necessarily originate from the SQL statement itself. It can occur before a connection is established, during parameter binding, while the database parses the statement, when the database checks constraints, or after the statement executes successfully when Spring fails to map result rows to Java objects.

Classifying errors accurately helps you choose the right handling strategy. Transient connection errors can be retried with limits; syntax errors require fixing the SQL; mapping errors require fixing the entity, projection, or converter; constraint errors usually require handling according to business rules. Retrying every error increases load and can repeat a write operation that already succeeded in the database.

This lesson walks through each error category in the reactive R2DBC flow, how Spring translates exceptions, how to read SQLSTATE and vendor error codes, how to handle errors with Reactor, and how to test to distinguish infrastructure failures from data errors.

## 1. Viewing Errors by Layer in the R2DBC Flow

A repository operation can pass through multiple layers:

~~~text
Service / reactive chain
        |
Spring Data repository / template
        |
Spring R2DBC mapping and parameter binding
        |
R2DBC SPI
        |
R2DBC driver
        |
Network / connection pool
        |
Database server
        |
SQL execution and constraints
        |
Rows returned by the driver
        |
Spring row-to-object mapping
~~~

Errors can arise at any layer. You need to determine whether the error occurred before sending the SQL, while the database was executing it, or after the database returned results.

| Error category | Typical point of occurrence | Examples |
| --- | --- | --- |
| Connection and resources | Opening a connection, acquiring a connection from the pool, sending/receiving data. | Database down, DNS/TLS, pool timeout, network reset. |
| SQL syntax and usage | Database parses or executes the statement. | Wrong table/column name, missing bind marker, invalid syntax. |
| Parameter binding and types | Preparing the statement or binding values. | Type mismatch, missing parameter, binding NULL without a type. |
| Data mapping | Converting a row into an entity/projection. | Cannot convert NUMERIC to Java type, missing constructor parameter. |
| Data constraints | Database validates INSERT/UPDATE/DELETE. | Unique, foreign key, NOT NULL, CHECK violation. |
| Transaction and concurrency | Commit, rollback, or concurrent write conflict. | Deadlock, serialization failure, transaction already rolled back. |

An exception at the service layer may wrap an exception from the driver layer. Therefore, do not look only at the outermost exception class; inspect the cause chain, SQLSTATE, and vendor error code when available.

## 2. Spring's Exception Translation

The R2DBC SPI defines exceptions in the `io.r2dbc.spi` package. Spring R2DBC provides a mechanism to translate certain driver errors into Spring's data access exception hierarchy in the `org.springframework.dao` package.

These Spring exceptions typically extend `DataAccessException`. They enable application code to handle errors by semantic category rather than depending directly on a specific driver.

Examples of common categories:

| Meaning | Possible R2DBC-side exception | Possible Spring exception |
| --- | --- | --- |
| SQL syntax error | R2dbcBadGrammarException | BadSqlGrammarException |
| Data/constraint violation | R2dbcDataIntegrityViolationException | DataIntegrityViolationException or DuplicateKeyException |
| Transient resource error | R2dbcTransientResourceException | TransientDataAccessResourceException or another transient type |
| Non-transient resource error | R2dbcNonTransientResourceException | DataAccessResourceFailureException or another non-transient type |
| Timeout | R2dbcTimeoutException | QueryTimeoutException or an appropriate timeout type |
| Rollback error | R2dbcRollbackException | TransactionSystemException or an appropriate transaction exception |

The table above describes mappings you may encounter, not a one-to-one guarantee across all drivers and versions. The exception translator uses information provided by the driver; if the driver only returns a generic exception or omits SQLSTATE/error code, Spring may not be able to classify it in detail.

### Handling at Spring's abstraction level

When the application does not need to read driver-specific details, prefer handling Spring exceptions:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.TransientDataAccessException;

return repository.save(entity)
    .onErrorResume(DuplicateKeyException.class, error ->
        findExistingResult(entity)
    )
    .onErrorMap(TransientDataAccessException.class, error ->
        new TemporaryStorageException("Storage is temporarily unavailable", error)
    )
    .onErrorMap(DataAccessException.class, error ->
        new PersistenceOperationException("Could not persist entity", error)
    );
~~~

This example only illustrates classification ordering. The `DuplicateKeyException` branch must match idempotent business semantics; not every duplicate means you can simply return an existing record. The transient error branch should be handled where enough context exists to decide whether to retry.

Do not catch `DataAccessException` and return a default value for every case. Doing so hides syntax errors, mapping errors, constraint violations, and infrastructure failures.

## 3. Connection and Resource Errors

Connection errors occur before or while the application exchanges data with the database. Some causes include:

- The database server has not started or is restarting.
- Wrong hostname, port, or database name, or DNS cannot be resolved.
- TLS/certificate errors or invalid credentials.
- Network reset, closed socket, or firewall dropping the connection.
- Connection pool exhausted of available connections.
- Connection expired or closed by the server.
- Timeout when acquiring a connection or executing a statement.

Not every connection error is transient. A database restart or brief network interruption may recover on its own; a wrong password, wrong hostname, or invalid certificate usually requires a configuration fix.

### Distinguishing connection acquisition errors from SQL execution errors

Different types of timeouts carry different meanings:

| Situation | Location | Investigation direction |
| --- | --- | --- |
| Pool acquisition timeout | Application cannot obtain a connection from the pool. | Check pool size, long-held connections, concurrency, and subscription leaks. |
| Connect timeout | Driver cannot establish a connection to the server. | Check DNS, network, port, TLS, and server status. |
| Statement/query timeout | Connection was acquired, but the statement runs too long. | Check query plan, locks, server load, and configured timeouts. |
| Connection reset during write | The outcome of the operation may be unknown. | Check commit status using an ID/idempotency key before retrying. |

A timeout after sending a write command can create an uncertain state: the database may have committed, but the response was lost. Blind retrying can create duplicate records or duplicate business transactions.

### Transient vs. non-transient classification

The R2DBC SPI has exception types representing transient and non-transient errors, such as `R2dbcTransientException`, `R2dbcTransientResourceException`, and `R2dbcNonTransientResourceException`. Spring also has a transient/non-transient hierarchy under `DataAccessException`.

However, do not decide to retry based solely on a single outermost class. Some errors are wrapped across multiple layers, and drivers may classify them differently. Inspect the cause chain and SQLSTATE when available.

## 4. SQL Syntax and Statement Usage Errors

Syntax errors occur when the database cannot parse or execute the SQL statement sent to it. Common causes:

- Wrong table, column, schema, or alias name.
- Using a reserved keyword as an identifier without proper quoting.
- Missing commas, parentheses, or keywords.
- Using SQL syntax specific to a different database.
- Invalid JOIN or GROUP BY.
- Calling a non-existent function or passing the wrong number of arguments.
- Placeholders not matching bound parameters.
- Query method or `@Query` referencing the wrong property/column.

Example:

~~~sql
SELECT id, display_name
FROM customers
WHERE customer_id = :customerId
ORDER BY created_at DESC;
~~~

If the `customers` table does not have a `customer_id` column, the database may report a missing column error. Spring may translate the error into `BadSqlGrammarException` or a corresponding exception depending on the driver.

### Distinguishing property names from column names

Derived query methods and `Criteria` typically reference the Java properties of the entity:

~~~java
@Table("customers")
public record Customer(
    @Id Long id,
    @Column("display_name") String displayName,
    @Column("created_at") LocalDateTime createdAt
) {}
~~~

Example repository method using a property:

~~~java
Flux<Customer> findByDisplayName(String displayName);
~~~

Hand-written SQL via `@Query` or `DatabaseClient` must use actual column names:

~~~sql
SELECT id, display_name, created_at
FROM customers
WHERE display_name = :displayName;
~~~

Do not use `displayName` in SQL if the database only has the column `display_name`. Conversely, do not use the column name `display_name` as the property name in a derived query if the entity property is `displayName`.

### Bind markers and named parameters

When using Spring's `DatabaseClient` or `@Query`, named parameters are typically converted by Spring into the markers supported by the driver. Ensure that:

- Every named parameter in the SQL has a corresponding bound value.
- The parameter name in `@Param` matches the name in the SQL.
- The same parameter is not bound with an incompatible type.
- Bind parameters are not used to substitute table names, column names, or keywords.
- Empty lists in `IN` clauses are handled according to an explicit policy.

Syntax errors must be fixed in the query or mapping. Retrying the same SQL statement cannot make an invalid statement valid.

## 5. Parameter Binding and Type Conversion Errors

A syntactically valid query can still fail during parameter binding. Examples:

- A Java `Integer` bound to a column/parameter expecting a `UUID`.
- A date-time string with an invalid format or type.
- A `BigDecimal` exceeding the column's precision/scale.
- A `NULL` value bound without specifying the data type.
- A `Collection` containing `NULL` or incompatible elements.
- A parameter declared in SQL that is never bound.

With `DatabaseClient`, do not pass Java `null` directly to `bind`. Use `bindNull` and declare the type:

~~~java
databaseClient.sql("""
        SELECT id, display_name
        FROM customers
        WHERE deleted_at IS NOT NULL
           OR :includeDeleted = TRUE
        """)
    .bind("includeDeleted", includeDeleted);
~~~

The example above assumes `includeDeleted` always has a value. If a parameter can be null, determine its type and use the corresponding `bindNull` API:

~~~java
spec.bindNull("optionalDate", LocalDateTime.class);
~~~

For required parameters, validate them before building the query rather than letting the error surface deep inside the driver.

### Type mismatches and conversion errors

A value may be valid in Java yet incompatible with the column type:

| Java type | Common database types | Risk |
| --- | --- | --- |
| UUID | UUID, BINARY(16), CHAR(36) | Drivers/databases represent them differently. |
| BigDecimal | NUMERIC/DECIMAL | Exceeding precision or scale. |
| LocalDateTime | TIMESTAMP | Timezone and precision differences. |
| Instant/OffsetDateTime | TIMESTAMP WITH TIME ZONE or equivalent | Mapping depends on the database and driver. |
| Enum | VARCHAR, INTEGER, or native enum | Stored value does not match converter. |
| Boolean | BOOLEAN, BIT, or numeric type | Vendor-specific mapping differences. |

Errors occurring during binding typically belong to the statement/driver layer. Errors occurring when reading rows and converting them to objects typically belong to the mapping layer. Distinguishing these two moments helps you locate the right place to fix.

## 6. Entity and Projection Mapping Errors

Mapping is the process of converting row data returned by the driver into a Java entity, record, or projection. A query can execute successfully while mapping still fails.

Common causes:

- Result column is missing or alias does not match the projection.
- Constructor lacks a matching parameter.
- SQL column is `NULL` while the constructor parameter/field does not allow null for the type used.
- Database returns a data type not supported by any converter.
- Enum column in the database contains a value that does not exist in the Java enum.
- Custom converter is not registered or is not applied in the right direction.
- Incompatible numeric precision/scale or type.
- Mapping expects a full entity while SQL only `SELECT`s a subset of columns.

Example entity:

~~~java
@Table("products")
public record Product(
    @Id UUID id,
    String name,
    BigDecimal price,
    ProductStatus status
) {}
~~~

If the query returns:

~~~sql
SELECT id, name, price
FROM products;
~~~

then the `status` column is missing. If mapping requires the full constructor, Spring may be unable to instantiate `Product`. Choose one of two approaches:

- `SELECT` all required columns needed to construct the entity.
- Use a dedicated projection describing the exact columns returned by the query.

Example projection:

~~~java
public record ProductSummary(
    UUID id,
    String name,
    BigDecimal price
) {}
~~~

### Aliases and column names

Projection SQL should define explicit aliases:

~~~sql
SELECT
    p.id AS id,
    p.name AS name,
    p.unit_price AS price
FROM products p;
~~~

Aliases make mapping predictable, especially when joining multiple tables with overlapping column names. Avoid using `SELECT *` in complex projection queries because schema changes can cause unexpected mapping results.

### Custom converters

When Java and database types lack a suitable default mapping, Spring Data Relational lets you configure converters. Be clear whether the converter is for reading or writing:

- A writing converter transforms a Java object into a database value.
- A reading converter transforms a database value into a Java object.

A converter that works in one direction does not automatically guarantee the other direction. Test both insert/update and readback.

### Distinguishing mapping errors from data errors

If the database returns `status = 'ARCHIVED'` while the Java enum only has `NEW`, `ACTIVE`, and `DISABLED`, mapping can fail. This may indicate schema/data drift, an out-of-sync deployment, or a missing enum value in code. Retrying will not solve it. You must decide whether the new value is valid, then update the enum, converter, or data through a controlled migration.

## 7. Data Constraint Errors

Database constraints protect data validity and integrity. R2DBC or Spring typically represents violations as `R2dbcDataIntegrityViolationException`, `DataIntegrityViolationException`, or `DuplicateKeyException`, depending on the driver and exception translator.

Common constraint groups:

| Constraint | Violation condition | Example |
| --- | --- | --- |
| PRIMARY KEY | Duplicate or missing primary key. | Two records with the same `id`. |
| UNIQUE | Non-unique value or combination of values. | Email already in use. |
| FOREIGN KEY | References a non-existent record or deletes a record still referenced. | `order.customer_id` does not exist. |
| NOT NULL | Writing `NULL` into a required column. | Creating a customer without an email. |
| CHECK | Value does not satisfy the check expression. | `quantity <= 0`. |
| EXCLUSION or database-specific constraint | Violates an exclusion/database-specific rule. | Two time ranges must not overlap. |

### Duplicate key is not always a system error

For example, an email already exists. If business rules require unique emails, this may be an input conflict requiring an HTTP 409 or an appropriate message, and should not be retried.

~~~java
return customers.save(customer)
    .onErrorMap(DuplicateKeyException.class, error ->
        new EmailAlreadyRegisteredException(customer.email(), error)
    );
~~~

Do not catch every `DataIntegrityViolationException` and turn it into "email already exists." That error might be a foreign key, `NOT NULL`, or `CHECK` violation. Inspect the constraint name, SQLSTATE, and vendor code to distinguish them.

### Foreign key violation

If creating an order references a non-existent customer, the database may reject the insert. The application should validate references according to the business contract while still relying on database constraints to protect integrity in case of race conditions.

Do not rely solely on a pre-insert check: the customer could be deleted between the check and the write. The foreign key remains the final line of defense.

### NOT NULL and CHECK violations

These errors usually indicate incomplete validation at the application layer or data arriving from another flow that violates the contract. Map them to specific validation/domain errors when the exact constraint can be identified.

Do not drop database constraints just to stop the application from receiving exceptions. Constraints guard data across every write path, including batch jobs or other services.

## 8. SQLSTATE and Vendor Error Codes

When provided by the driver, `R2dbcException` can contain:

- SQLSTATE: standard SQLSTATE error classification code.
- Error code: database vendor-specific error code.
- SQL: related statement if supplied by the driver.
- Message and cause chain.

Not all drivers populate every field. Do not depend on message text because it can vary by vendor, version, locale, or configuration.

Some commonly useful SQLSTATE classes:

| SQLSTATE class | General meaning | Example situations |
| --- | --- | --- |
| 08 | Connection exception | Lost connection or connection failure. |
| 22 | Data exception | Invalid data format/value, out-of-range value. |
| 23 | Integrity constraint violation | UNIQUE, FK, NOT NULL, or CHECK. |
| 28 | Invalid authorization specification | Invalid credentials or login permissions. |
| 40 | Transaction rollback | Deadlock, serialization failure, or rollback. |
| 42 | Syntax error or access rule violation | Syntax error, missing table/column, or access privilege error. |
| 53 | Insufficient resources | Out of resources as classified by the database. |
| 57 | Operator intervention | Server canceled operation or shutdown as classified. |

SQLSTATE classes are only high-level groups. Specific subcodes and how drivers map them can differ. For instance, a deadlock usually belongs to class `40`, but you must check the specific code for your database.

### Reading error details from R2dbcException

If driver-level diagnostics are needed:

~~~java
import io.r2dbc.spi.R2dbcException;

Throwable current = error;
while (current != null) {
    if (current instanceof R2dbcException r2dbcError) {
        String sqlState = r2dbcError.getSqlState();
        int vendorCode = r2dbcError.getErrorCode();

        log.warn(
            "R2DBC failure: sqlState={}, vendorCode={}",
            sqlState,
            vendorCode
        );
    }

    current = current.getCause();
}
~~~

This snippet illustrates traversing the cause chain. Avoid logging SQL or bind values that contain sensitive data. If the application only needs Spring's exception abstraction, it can handle `DataAccessException` and inspect the driver cause only when additional detail is required.

### Do not classify by substring matching on messages

Do not write logic like:

~~~java
if (error.getMessage().contains("duplicate")) {
    // assume duplicate key
}
~~~

Messages can be localized, change across versions, or contain constraint names. Prefer exception types, SQLSTATE, and vendor codes. If message parsing is unavoidable because the driver lacks metadata, isolate that logic in a dedicated adapter and test it against the specific driver version.

## 9. Translating Technical Exceptions into Business Errors

The service/application layer should not let every upper layer depend directly on PostgreSQL, MySQL, or R2DBC driver exception names. Understood errors can be translated into domain exceptions or appropriate API responses.

Example:

~~~java
public Mono<Customer> register(RegisterCustomerCommand command) {
    Customer customer = Customer.from(command);

    return customers.save(customer)
        .onErrorMap(DuplicateKeyException.class, error ->
            new EmailAlreadyRegisteredException(command.email(), error)
        )
        .onErrorMap(DataIntegrityViolationException.class, error ->
            new CustomerDataRejectedException(error)
        );
}
~~~

Handler ordering matters: `DuplicateKeyException` is typically a subtype of `DataIntegrityViolationException`. Place the specific branch before the general branch so information is not lost.

Do not turn all database errors into a generic business error. Connection errors may require a 503; validation errors may be 400; duplicate conflicts may be 409; mapping or SQL grammar errors are usually internal bugs requiring alerting and investigation.

### Suggested HTTP mapping

| Error category | Typically appropriate response | Notes |
| --- | --- | --- |
| Input validation | 400 Bad Request | Return understandable field/error codes. |
| Unique conflict | 409 Conflict | Describe the business conflict without leaking SQL. |
| Temporarily unavailable resource | 503 Service Unavailable | May include retry guidance if safe. |
| Query timeout | 503 or 504 depending on gateway/API role | Log correlation id, do not expose sensitive queries. |
| SQL grammar/mapping bug | 500 Internal Server Error | Typically an implementation bug; do not blame the client. |
| Database permission error | 500 and operational alert | Usually an application configuration/permission issue. |

These are API design suggestions, not mandatory HTTP rules. Keep responses stable and never return raw exception messages, SQL, or connection details to clients.

## 10. Retry: Only Retry Recoverable Errors

Retrying helps when the failure is genuinely transient, such as a deadlock, serialization conflict, or connection reset before the operation executed. Retrying does not help for syntax errors, mapping errors, or constraint violations caused by invalid data.

| Error category | Retry by default? | Reason |
| --- | --- | --- |
| Invalid SQL/missing column | No | Must fix the statement or schema. |
| Mapping/converter error | No | Must fix the mapping or data. |
| UNIQUE/FK/NOT NULL/CHECK | No | Data or business rules must be addressed. |
| Invalid credentials/permissions | No | Must fix configuration or permissions. |
| Deadlock/serialization failure | Maybe | Can retry the entire transaction. |
| Connection reset before sending command | Maybe | Must confirm the operation has not occurred. |
| Timeout after sending write command | With caution | Commit outcome may be uncertain. |
| Pool acquisition timeout | Maybe, with limits | Retrying too fast can overload the pool further. |

### Retrying with Reactor

You can cap attempts and retry only exceptions classified as transient:

~~~java
import java.time.Duration;

import org.springframework.dao.TransientDataAccessException;
import io.r2dbc.spi.R2dbcTransientException;
import reactor.core.Exceptions;
import reactor.util.retry.Retry;

private boolean isRetryable(Throwable error) {
    Throwable current = Exceptions.unwrap(error);

    while (current != null) {
        if (current instanceof TransientDataAccessException
                || current instanceof R2dbcTransientException) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}

private Retry databaseRetry() {
    return Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) -> signal.failure());
}
~~~

Example call:

~~~java
return performRead()
    .retryWhen(databaseRetry());
~~~

This example is for a read operation that can be safely repeated. Do not assume every `R2dbcTransientException` is automatically safe to retry; consider the operation type and commit state.

### Retrying the entire transaction

For multi-step transactions, if a deadlock or serialization failure rolls back the transaction, you must retry the entire unit of work so every operation runs inside a fresh transaction.

Place the retry outside the publisher wrapped by `TransactionalOperator`:

~~~java
Mono<Order> oneAttempt =
    transactionalOperator.transactional(
        Mono.defer(() -> createOrderAndLines(command))
    );

return oneAttempt.retryWhen(databaseRetry());
~~~

Each resubscription to the transactional publisher starts a new transaction execution under the transaction manager. Placing retry inside an open transaction can cause subsequent operations to keep using a transaction already marked rollback-only or in an unusable state.

### Write retries require idempotency

If a timeout occurs after the database may have committed, retrying can create duplicate data. For critical write operations, use one of these mechanisms:

- A stable business ID generated at the request boundary.
- An idempotency key backed by a unique constraint.
- An upsert with well-defined semantics.
- A status lookup by operation ID before retrying.
- Designing the command so repeated execution produces only a single business outcome.

Do not generate a new ID on every retry if the attempts represent the same business operation.

## 11. Handling Errors in Reactive Chains

Reactive code propagates errors via error signals. Three operators are commonly used:

- `onErrorMap`: changes the exception type while keeping the error path.
- `onErrorResume`: replaces an error with another publisher.
- `doOnError`: observes/logs/records metrics without altering the error.

Example logging and propagating the error:

~~~java
return repository.save(entity)
    .doOnError(error ->
        log.error(
            "Could not save entity, operationId={}",
            operationId,
            error
        )
    );
~~~

Example mapping a duplicate error to a business error:

~~~java
return repository.save(entity)
    .onErrorMap(DuplicateKeyException.class, error ->
        new EntityAlreadyExistsException(entity.id(), error)
    );
~~~

Example fallback when data does not exist:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(
        new EntityNotFoundException(id)
    ));
~~~

Do not use `onErrorResume` to turn every database error into `Mono.empty()`. That prevents callers from distinguishing "no data found" from "database is down."

### Do not swallow errors before a transaction boundary

If a write operation fails and code falls back to a normal value inside a transaction, the transaction manager may see the publisher complete normally and commit. Only recover from an error when business rules allow it and the transaction state remains valid.

Upon a constraint violation, some databases mark the transaction as needing rollback or unable to continue before rollback. With savepoints, you must roll back properly to the savepoint before handling the error and continuing. Do not assume catching an exception is enough to return the transaction to a healthy state.

## 12. Diagnosing via Cause Chain and Point of Failure

When an API returns an error, capture enough information to locate the root cause:

1. Operation name and correlation/request id.
2. Repository method or use case name.
3. Outermost exception type.
4. Cause chain and root cause.
5. SQLSTATE and vendor error code if available.
6. Database vendor/version and R2DBC driver/version.
7. Point of failure: acquiring connection, executing, committing, or mapping results.
8. Transaction state and retry attempt.
9. Connection wait time and query execution time if metrics are available.

Avoid logging:

- Passwords, access tokens, or connection URLs with credentials.
- Bind values containing emails, addresses, phone numbers, or personal data.
- Raw request payloads without protection policies.
- Full SQL containing sensitive literals.
- Exception messages returned directly to clients.

You can log statement names, query fingerprints, constraint names, SQLSTATE, and vendor codes. When bind values are needed for investigation, use masked data and enable them only in controlled environments.

## 13. Distinguishing Connection, SQL, Mapping, and Constraint Errors by Scenario

| Observed scenario | Category to check first | Diagnostic question |
| --- | --- | --- |
| API times out before any SQL log | Pool/connectivity | Does the pool have free connections? Are DNS/TLS/server healthy? |
| SQL log appears, then relation/table not found | SQL/schema | Do schema/table names and migrations match the environment? |
| INSERT reports duplicate key | Constraint | Which constraint was violated? Is this a duplicate request or a bug? |
| INSERT succeeds but returns converter error | Mapping | Was the row written? Which type/alias/converter failed? |
| SELECT fails with enum conversion error | Mapping/data drift | Does the database contain a new enum value not yet supported in code? |
| UPDATE reports foreign key violation | Constraint | Does the referenced record exist, or was it concurrently deleted? |
| Deadlock or serialization failure | Transaction/concurrency | Can the entire transaction be retried? |
| Timeout after sending write command | Uncertain outcome | Check operation ID before retrying. |
| Wrong bind marker or missing named parameter | Bind/query definition | Do the SQL and parameter list match? |
| Connection reset while streaming Flux | Connection/lifecycle | Did the server/network/pool close the connection mid-stream? |

An important point: if a mapping error occurs after an `INSERT` has already been executed by the database, retrying the insert can create duplicates. Determine whether the error happened before or after the statement took effect. When unsure, query by stable ID or idempotency key.

## 14. Testing Error Categories

Unit tests can verify how a service translates exceptions into business errors. Integration tests against a real database are needed to confirm error classification, SQLSTATE, constraints, and mapping with the actual driver.

Cases that should be covered:

| Test case | Expected verification |
| --- | --- |
| Database unavailable | Connection error propagates and is not turned into an empty result. |
| Pool exhausted | Pool acquisition timeout is distinguished from SQL timeout. |
| SQL with wrong column name | Receives grammar/usage error; no retry. |
| Missing bind parameter | Error is caught at the bind/execute layer. |
| Type mismatch | Bind error or database data exception is classified. |
| Projection missing column | Mapping fails and is diagnosed at the conversion layer. |
| Unrecognized enum value | Schema/data drift is detected. |
| Unique constraint | Translated into an appropriate business conflict. |
| Foreign key constraint | Not retried and constraint is not removed. |
| Deadlock/serialization | Bounded retry of the entire transaction when verified safe. |
| Timeout after write | Idempotency/operation ID prevents duplicate results. |

Example unique constraint integration test:

~~~java
@Test
void mapsDuplicateEmailToDomainConflict() {
    StepVerifier.create(customerService.register(commandWithExistingEmail()))
        .expectError(EmailAlreadyRegisteredException.class)
        .verify();
}
~~~

The test must prepare duplicate data in the test database and invoke the service through real Spring beans. Mocking the repository only verifies the exception handling branch; it does not prove that the database/driver actually emits the expected exception.

For example, a mapping test should query data containing a value that cannot convert to the expected enum or projection type. Verify that the error is observed at the mapping layer, and also check whether a preceding write committed if the error happened after a write.

## 15. Common Error Handling Mistakes

| Mistake | Risk | Appropriate approach |
| --- | --- | --- |
| Retrying every exception | Repeats permanent errors and increases database load. | Only retry classified transient errors. |
| Retrying individual statements in a rolled-back transaction | Subsequent statements run in a broken transaction. | Retry the entire transaction in a fresh subscription. |
| Catching DataIntegrityViolationException and returning success | Hides invalid data. | Map specific constraints to domain errors. |
| Parsing messages to detect duplicates | Depends on locale/vendor/version. | Use exception types, SQLSTATE, and vendor codes. |
| Ignoring mapping errors | Data may have been written while the response failed. | Check write status; fix converter/projection. |
| Using `SELECT *` for projections | Mapping breaks when schema changes or columns collide. | List columns and explicit aliases. |
| Binding Java null with `bind` | Bind failure or missing type. | Use `bindNull` with a specific type. |
| Returning raw SQL errors to clients | Leaks schema, table names, and internal data. | Return stable error codes; log details safely. |
| Dropping constraints to stop errors | Removes data integrity protection. | Fix validation, mapping, or business rules. |
| Swallowing all errors with `Mono.empty` | Loses distinction between missing data and failures. | Only fall back for well-defined errors. |

## 16. Error Classification and Handling Workflow

When an R2DBC publisher emits an error, you can follow this sequence:

1. **Identify the timing:** did the error occur during connection acquisition, binding, execution, commit, or row mapping?
2. **Read the exception type:** inspect `DataAccessException`, `R2dbcException`, and the cause chain.
3. **Read metadata:** extract SQLSTATE, vendor error code, and constraint name if available.
4. **Categorize:** connection/resource, SQL grammar, bind/type, mapping, integrity constraint, or transaction.
5. **Decide retryability:** only retry transient errors and operations that are safe to repeat.
6. **Translate to domain/API error:** use stable error codes without leaking database internals.
7. **Log safely:** operation id, statement fingerprint, driver, SQLSTATE, and point of failure.
8. **Check write status:** especially when a timeout or mapping error happens after a write.
9. **Add integration tests:** using the exact database and R2DBC driver deployed in production.
10. **Monitor metrics:** error counts by category, retry rate, pool wait, query latency, and constraint conflicts.

Accurate error classification enables the application to respond meaningfully and recover safely. Connection errors may require retries or infrastructure alerts; SQL errors require fixing statements; mapping errors require aligning entities/projections/converters with the schema; constraint errors require business-level handling. In Spring Data Relational R2DBC, combine Spring's exception translation, metadata from the R2DBC driver, SQLSTATE, and real-database integration tests to decide how to handle errors rather than relying on message text or blanket retries.

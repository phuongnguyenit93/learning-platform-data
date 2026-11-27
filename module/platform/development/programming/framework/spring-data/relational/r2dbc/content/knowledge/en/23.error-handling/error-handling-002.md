# Exception Translation Mechanism to the DataAccessException Hierarchy

When accessing a database with Spring Data Relational R2DBC, errors can stem from invalid SQL, data violating constraints, lost connections, timeouts, transaction conflicts, or improper API usage. R2DBC drivers typically represent these failures using **R2dbcException** and its driver-specific subclasses. If the service layer depends directly on individual driver exceptions, the code becomes tightly coupled to the database and harder to change or test.

Spring provides the **DataAccessException** hierarchy in the **org.springframework.dao** package to standardize data access errors. The exception translation mechanism converts low-level driver errors into exceptions with general meanings such as data integrity violation, bad SQL grammar, resource acquisition failure, timeout, or concurrency conflict.

The goal of this mechanism is to let the business layer handle failures by issue category instead of having to understand each driver's proprietary error codes. Even so, mapping cannot always pinpoint the exact detailed cause: the outcome depends on SQLState, database error codes, the exception types thrown by the driver, and the Spring version in use.

This lesson explains the path of an error from the R2DBC driver to `DataAccessException`, the main branches in the hierarchy, how Spring Data R2DBC applies exception translation, how to handle errors in reactive pipelines, when retrying makes sense, and how to translate technical errors into business/API errors.

## 1. Why Exception Translation Is Needed

Different databases and drivers can represent the same type of failure in different ways. For example, two databases may both reject an `INSERT` because a foreign key value does not exist, yet their error codes, SQLState values, and concrete exception classes may differ.

If a service depends on a single driver's exception:

~~~java
try {
    // call a specific driver
} catch (SomeVendorConstraintException ex) {
    // handle according to the current database
}
~~~

switching drivers or databases can force changes in the business layer as well.

Spring normalizes errors into a common exception family:

~~~text
Repository / R2dbcEntityTemplate / DatabaseClient
                       |
                       v
                  R2DBC driver
                       |
                       v
                 R2dbcException
                       |
                       v
            Spring exception translator
                       |
                       v
                DataAccessException
                       |
                       v
             Service / API error mapping
~~~

For example, a unique constraint violation can be translated into **DuplicateKeyException** if the translator recognizes it; another data integrity error can become **DataIntegrityViolationException**. Invalid SQL errors can become **BadSqlGrammarException**.

The service layer can handle these Spring DAO exception types without importing vendor-specific exception classes from PostgreSQL, MySQL, or another driver.

## 2. What Is DataAccessException?

**DataAccessException** is the base class of Spring's data access exception hierarchy. It is an unchecked exception (extending `RuntimeException` through Spring's exception hierarchy), so repository and service methods do not have to declare `throws` clauses for every database failure.

This class represents a problem occurring during data access or manipulation. Subclasses describe high-level cause categories, such as:

- Data violating a constraint.
- Invalid SQL or improper use of data access resources.
- Failure to read data or unexpected result size.
- Database resources being temporarily unavailable.
- Concurrency conflicts or failure to acquire a lock.
- Queries exceeding allowed execution time.
- Errors not specifically categorized by the translator.

`DataAccessException` is not a business exception. It describes an error at the persistence layer. The service can translate recognized errors into domain exceptions, such as an email already being registered or an account being concurrently updated by another request.

### 2.1. Conceptual Hierarchy

Commonly used branches for classifying errors:

~~~text
DataAccessException
|
+-- NonTransientDataAccessException
|   |
|   +-- DataIntegrityViolationException
|   |   |
|   |   +-- DuplicateKeyException
|   |
|   +-- InvalidDataAccessResourceUsageException
|   |   |
|   |   +-- BadSqlGrammarException (Spring R2DBC)
|   |
|   +-- InvalidDataAccessApiUsageException
|   +-- DataRetrievalFailureException
|   +-- UncategorizedDataAccessException
|
+-- TransientDataAccessException
|   |
|   +-- ConcurrencyFailureException
|   |   |
|   |   +-- PessimisticLockingFailureException
|   |   +-- OptimisticLockingFailureException
|   |
|   +-- QueryTimeoutException
|
+-- RecoverableDataAccessException
~~~

This diagram serves as a guide to the key groups, not an exhaustive list of every subclass or inheritance relationship across all Spring versions. Some concrete classes live in Spring R2DBC or Spring DAO packages, and names or details may evolve across versions.

The most important distinction is between **transient** errors (which may succeed if retried later) and **non-transient** errors (which typically require fixing the statement, data, configuration, or logic before retrying).

## 3. NonTransientDataAccessException and TransientDataAccessException

Spring divides many data access errors into two major groups.

### 3.1. NonTransientDataAccessException

These are errors that generally will not disappear if you rerun the exact same operation with the same statement and data. Examples:

- Syntactically invalid SQL.
- Misusing an API or passing invalid parameters.
- Unique, foreign key, or check constraint violations.
- Insufficient privileges on a table or schema.
- Results failing to meet the query's contract.

Retrying immediately usually only adds load and repeats the failure.

Example: `INSERT`ing an email that already exists will continue failing unless the data or business flow changes. Appropriate handling is returning a meaningful business error or asking the client to supply a different value.

### 3.2. TransientDataAccessException

These are errors that may clear up if retried after a short wait or after concurrent state changes. Examples:

- Temporarily unable to obtain a connection or resource.
- Lock contention caused by another transaction holding a lock.
- Certain timeouts or concurrency errors.
- Certain optimistic/pessimistic locking conflicts.

Transient does not guarantee that a retry will succeed. Retries must be bounded, use backoff, and apply only to operations safe to repeat.

Example: a balance update that fails with an optimistic locking failure usually needs to re-read the latest data and recalculate. Rerunning the original statement with the stale entity can keep failing or corrupt logic.

### 3.3. RecoverableDataAccessException

Spring also includes **RecoverableDataAccessException** for certain failures that can be recovered through retrying or executing an appropriate recovery procedure. It is not a blanket label for every connection error; rely on the actual exception and the recoverability of the operation.

Do not assume that every exception containing the word "resource" is transient or that every driver error is safe to retry.

## 4. Common Exceptions in R2DBC Applications

The table below highlights Spring classes commonly useful when handling errors. Which exact class the translator returns depends on the driver/database and the error metadata provided by the driver.

| Exception | Meaning | Common handling approach |
|---|---|---|
| **DataIntegrityViolationException** | Data violates a constraint or integrity rule | Translate to an appropriate business error; do not blind-retry |
| **DuplicateKeyException** | Specifically recognized unique/primary key violation | Report duplicate code, email, or resource |
| **BadSqlGrammarException** | Invalid SQL or syntax error | Fix SQL, table/column names, or placeholders |
| **InvalidDataAccessResourceUsageException** | Invalid usage of database resources or statements | Check query, parameter types, schema, and privileges |
| **InvalidDataAccessApiUsageException** | Data access API called outside its contract | Fix API usage or input data |
| **DataAccessResourceFailureException** | Data access resource encountered a failure | Check connections, database, and infrastructure |
| **TransientDataAccessResourceException** | Resource failure of a transient nature | May retry with limits if the operation is safe |
| **QueryTimeoutException** | Query exceeded allowed time | Check query, database load, and timeout; consider conditional retry |
| **ConcurrencyFailureException** | Conflict caused by concurrent transactions | Re-read, retry, or handle conflict per business rules |
| **OptimisticLockingFailureException** | Entity version no longer matches during update | Re-read data and re-evaluate/reapply update |
| **PessimisticLockingFailureException** / **CannotAcquireLockException** | Unable to acquire required lock | Wait/retry with limits or return conflict |
| **IncorrectResultSizeDataAccessException** | Number of rows returned violates the contract | Fix query predicates or data/constraints |
| **UncategorizedR2dbcException** | R2DBC error not mapped to a specific category | Inspect cause, SQLState, error code, and log safely |

**DuplicateKeyException** is a specific case of **DataIntegrityViolationException**. When catching errors, match the specific subclass before the parent class.

**BadSqlGrammarException** in Spring R2DBC resides in the **org.springframework.r2dbc** package; general classes such as **DataAccessException** and **DataIntegrityViolationException** reside in **org.springframework.dao**.

Do not depend on a specific subclass if the translator for your target driver does not emit it. For constraint failures, some drivers only yield a general data integrity exception rather than distinguishing duplicate keys.

## 5. How Spring Translates R2DBC Errors

At the low level, drivers emit errors following the R2DBC SPI, typically **R2dbcException** or a subclass. The exception may carry details such as:

- Error message from the database.
- SQLState if provided by the driver.
- Vendor error code.
- Related SQL statement if available.
- Root exception or nested causes.

Spring uses an exception translator to map driver errors into the **DataAccessException** hierarchy. Classification may rely on the R2DBC exception type, SQLState, vendor code, and translator rules.

Some error groups are fairly recognizable, such as syntax errors or data integrity violations. Others can only be mapped to a general exception because the driver does not provide enough metadata.

### 5.1. SQLState and vendor code

SQLState is a standardized SQL error classification code or RDBMS convention. Many databases use code classes to represent failure types, such as integrity constraint violations.

A vendor code is a database-specific numeric code. The same scenario can produce different vendor codes across databases.

Do not write business logic like:

~~~java
if (exception.getSqlState().equals("23505")) {
    // assume every database uses this code for duplicate key
}
~~~

Code **23505** is PostgreSQL's common code for unique violations, not a universal code across all databases. If you must inspect vendor-specific codes, isolate that logic in a persistence adapter tailored to that database/driver.

### 5.2. Uncategorized errors

When the translator cannot determine a specific category, Spring may wrap the failure in an uncategorized exception such as **UncategorizedR2dbcException** or an appropriate **UncategorizedDataAccessException** subclass.

That does not mean the error is harmless. Inspect the cause and metadata for diagnostics while keeping the service layer decoupled from vendor details unless truly necessary.

## 6. Exception Translation in Repositories, Templates, and DatabaseClient

Spring Data R2DBC provides several data access entry points:

- Reactive repositories.
- **R2dbcEntityTemplate**.
- **DatabaseClient**.
- Direct R2DBC SPI.

With repositories, Spring Data manages query execution and entity mapping; driver errors pass through Spring Data/Spring R2DBC's exception translation mechanism.

**R2dbcEntityTemplate** and **DatabaseClient** are also Spring abstractions that execute queries and translate failures into Spring's data access exception hierarchy.

Example with **DatabaseClient**:

~~~java
Mono<Long> insertCustomer(String email) {
    return databaseClient.sql("""
            INSERT INTO customer(email_address)
            VALUES (:email)
            """)
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
~~~

If the database rejects the insert due to a unique constraint, the publisher emits an error. At the layer using Spring abstractions, the error is typically already translated into a corresponding **DataAccessException**.

When using the R2DBC SPI directly (**Connection**, **Statement**, **Result**), the application may receive raw driver exceptions without passing through the same translation path as **DatabaseClient** or repositories. If you want a uniform contract, actively apply an appropriate translator or isolate driver exception handling in the lowest adapter layer.

Do not assume every data access path returns the exact same exception class. Verify with integration tests against the actual entry point your application uses.

## 7. Query Errors Are Not the Same as Empty Results

A key point in reactive repositories is that missing data is usually represented by an empty publisher, not a **DataAccessException**.

| Situation | Typical outcome |
|---|---|
| **findById(id)** finds no row | **Mono.empty()** |
| Derived query returns multiple results | **Flux<T>** may be empty or emit multiple items |
| **existsById(id)** finds nothing | Emits **false** |
| **count()** on an empty table | Emits **0** |
| Row exists, nullable column is SQL **NULL** | Emits entity with that property null |
| Invalid SQL syntax | Error translated into a data access exception |
| Lost connection or timeout | Resource/timeout failure |
| Unique constraint violation | Data integrity failure |

Example:

~~~java
Mono<Customer> customer =
        customerRepository.findById(customerId);
~~~

If the ID does not exist, the publisher completes empty. Do not catch **DataAccessException** to handle this case. Use **switchIfEmpty** when the use case requires the record to exist:

~~~java
return customerRepository.findById(customerId)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(customerId)));
~~~

Similarly, **Flux.empty()** is typically a valid outcome for a search with no matching rows. Do not turn every empty result into a database error.

## 8. Handling DataAccessException in Reactive Pipelines

Because **Mono** and **Flux** execute upon subscription, data access errors are emitted as **onError** signals in the reactive stream. A **try/catch** surrounding the method call that constructs the publisher will not catch errors emitted later.

Avoid:

~~~java
public Mono<Customer> findCustomer(Long id) {
    try {
        return customerRepository.findById(id);
    } catch (DataAccessException ex) {
        // usually cannot catch errors emitted when the publisher executes
        return Mono.empty();
    }
}
~~~

Use reactive operators to observe, transform, or recover from errors.

### 8.1. doOnError: observing errors

**doOnError** performs side effects such as logging or incrementing metrics while preserving the error signal:

~~~java
return customerRepository.findById(id)
        .doOnError(DataAccessException.class, error ->
                log.error("Database access failed for customer lookup", error));
~~~

After **doOnError**, the error still flows downstream to the subscriber. Do not use **doOnError** if your goal is to turn the error into a different result.

Logs should avoid containing passwords, tokens, personal information, or sensitive bind parameters. Driver SQL messages sometimes embed input data or internal schema/table names; log them only when permitted by your application's logging policy.

### 8.2. onErrorMap: translating technical errors to domain errors

Use **onErrorMap** when you want to transform an exception into a type with clearer meaning at the service layer:

~~~java
return customerRepository.save(customer)
        .onErrorMap(
                DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.getEmail(), error));
~~~

This example assumes the translator identifies duplicate keys via **DuplicateKeyException**. If the driver only emits **DataIntegrityViolationException**, handle that class and identify the specific constraint before concluding it is a duplicate email.

Domain exceptions should retain the cause to aid diagnostics:

~~~java
public class EmailAlreadyRegisteredException extends RuntimeException {

    public EmailAlreadyRegisteredException(String email, Throwable cause) {
        super("Email is already registered: " + email, cause);
    }
}
~~~

In production applications, consider excluding full email addresses from logs or responses if they are treated as personal data.

### 8.3. onErrorResume: intentional recovery

**onErrorResume** replaces a failing publisher with another publisher:

~~~java
return configurationRepository.findById(key)
        .onErrorResume(
                DataAccessResourceFailureException.class,
                error -> cachedConfiguration(key));
~~~

This can be appropriate when falling back to cached configuration is acceptable to the business. Do not fall back for all **DataAccessException** types, because SQL errors or data violations are not solved by caching.

Do not turn database errors into **Mono.empty()** just to stop an endpoint from failing:

~~~java
// Avoid: masking a data access failure as "record not found".
return repository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

If an error is converted to empty, the API layer may return 404 or an empty list and hide the real outage.

## 9. Catch Specific Exceptions Before General Ones

Because the hierarchy uses inheritance, handling order matters.

Example:

~~~java
return repository.save(customer)
        .onErrorResume(DuplicateKeyException.class, error ->
                Mono.error(new EmailAlreadyRegisteredException(
                        customer.getEmail(), error)))
        .onErrorResume(DataIntegrityViolationException.class, error ->
                Mono.error(new InvalidCustomerDataException(error)))
        .onErrorResume(DataAccessException.class, error ->
                Mono.error(new CustomerPersistenceException(error)));
~~~

**DuplicateKeyException** is a subtype of **DataIntegrityViolationException**, so the specific branch must precede the general one.

You do not need to catch every exception in every repository method. Place mappings at the service boundary where the application understands the business meaning of the failure. A persistence adapter can also perform this translation if you want to isolate Spring DAO details completely from the domain.

If you only want to log and rethrow the same exception, **doOnError** is usually clearer than **onErrorResume(error -> Mono.error(error))**.

## 10. Handling Data Integrity Errors

Database constraints protect data even under concurrent requests or write paths that bypass the current service.

Common failures:

- Unique constraint: duplicate key or unique value.
- Foreign key constraint: referencing a missing row or deleting a row still referenced.
- NOT NULL constraint: missing required value.
- Check constraint: value fails the check condition.
- Data type/length constraint: invalid data type or length.

Spring typically translates these errors into **DataIntegrityViolationException** or a specific subtype if recognized by the translator.

Example handling duplicate errors:

~~~java
Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
            .onErrorMap(
                    DuplicateKeyException.class,
                    ex -> new EmailAlreadyRegisteredException(
                            customer.getEmail(), ex));
}
~~~

Do not rely solely on checking **existsByEmail** before inserting and assume duplicates are prevented. Two concurrent requests can both receive `false` and both attempt to insert. The unique constraint remains the final safeguard; the service maps the constraint failure to an appropriate business response.

### 10.1. Identifying which constraint was violated

A **DataIntegrityViolationException** can represent many different constraints. Do not map every instance to "email already exists."

Identification can be based on:

- Exception subtype such as **DuplicateKeyException**.
- SQLState/vendor code when supplied by the driver.
- Constraint name in error details if consistently provided by the database/driver.
- Operation context: whether the statement writes an email, order code, or foreign key relation.

If you must inspect vendor codes or constraint names, keep that logic inside a database-specific adapter. Do not scatter database-specific SQLState literals across domain services.

## 11. Handling SQL and API Usage Errors

**BadSqlGrammarException** generally indicates malformed SQL or structural references that the database cannot execute.

Common causes:

- Wrong table or column name.
- Mismatched alias.
- Dialect-incompatible placeholders or parameter binding.
- SQL syntax supported only on a different database.
- Invalid dynamically generated statement.
- Query referencing a schema that does not yet exist.

These usually require fixing code or queries, not retrying.

**InvalidDataAccessApiUsageException** can indicate the application called the persistence API outside its contract, such as passing invalid parameters or invoking an operation on an unsupported data type. Inspect the cause and stack trace to determine whether the issue lies in the query, mapping, or API call.

Never return raw SQL or internal schema details to end clients. API responses should use safe messages; technical details belong in controlled logs.

## 12. Resource Errors, Timeouts, and Transience

**DataAccessResourceFailureException**, **TransientDataAccessResourceException**, or **QueryTimeoutException** can relate to:

- Database temporarily unavailable.
- Connection pool exhausted.
- Network interruption.
- Database overload.
- Statement or transaction exceeding its timeout.
- Temporary driver or server issues.

Not every error in this group should be retried immediately. Before retrying, know:

1. Is the error genuinely transient?
2. Did the database already execute the statement?
3. If the client never received the result, could the operation have committed?
4. Could retrying cause duplicate side effects?
5. Is the database overloaded or only experiencing brief contention?

For example, an `INSERT` may have committed in the database, but the connection dropped before the application received confirmation. Blind retrying can create duplicate records or execute a business action twice. Use unique/idempotency keys to protect operations that need safe retries.

## 13. Retrying Transient Errors in Reactive Pipelines

Reactor provides **retryWhen** to resubscribe to a publisher when an error satisfies a condition.

Illustrative example:

~~~java
return repository.findById(id)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryableDataAccessFailure));
~~~

The filter should identify the truly recoverable error category:

~~~java
private boolean isRetryableDataAccessFailure(Throwable error) {
    return error instanceof TransientDataAccessException
            || error instanceof RecoverableDataAccessException;
}
~~~

This is only a skeleton example. Identify the concrete retryable failures for your actual database and workload. **QueryTimeoutException** may be classified as transient, yet retrying relentlessly while the database is overloaded can worsen the outage.

### 13.1. Retrying transactions at the right boundary

If a use case spans multiple operations inside a transaction, you usually need to retry the **entire transaction** so the new attempt starts from a fresh database state.

~~~java
Mono<TransferReceipt> work = performTransfer(command);

return transactionalOperator.transactional(work)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryableDataAccessFailure));
~~~

With this layout, each resubscription can create a new transaction execution via **TransactionalOperator**. Avoid placing retries inside a transaction already marked rollback-only and re-running partial operations inside that broken transaction.

Retrying the entire `work` means every operation inside the publisher runs again. Therefore, external side effects such as sending emails, calling payment gateways, or publishing messages should not be executed directly inside the transaction without proper idempotency/outbox mechanisms.

### 13.2. Backoff, jitter, and retry limits

A retry strategy needs:

- A bounded number of retries.
- Backoff to avoid slamming requests back simultaneously.
- Jitter when multiple clients compete for the same resource.
- An overall timeout.
- Metrics on retry counts and causes.
- Circuit breaking or load shedding if downstream is losing availability.

Do not retry **BadSqlGrammarException**, **InvalidDataAccessApiUsageException**, or unhandled constraint violations. Those errors require fixing the query, code, or data.

## 14. Optimistic Locking and ConcurrencyFailureException

Spring Data Relational supports optimistic locking via the **@Version** property on an entity. When two transactions read the same entity, the first updates the version. The second transaction attempting to save with the stale version can receive an optimistic locking failure.

Example:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer available;

    @Version
    private Long version;
}
~~~

When saving the entity, Spring Data uses the version to detect concurrent modifications. If the version no longer matches, the operation can emit **OptimisticLockingFailureException**, which belongs to the **ConcurrencyFailureException** branch.

This is a business conflict that may require re-reading the data and recalculating. Do not catch the error and immediately call **save** again with the stale object without loading the new version.

Example handling in a service:

~~~java
return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(
                new ProductNotFoundException(productId)))
        .flatMap(inventory -> {
            if (inventory.getAvailable() < quantity) {
                return Mono.error(new InsufficientStockException());
            }

            inventory.setAvailable(inventory.getAvailable() - quantity);
            return inventoryRepository.save(inventory);
        })
        .onErrorMap(
                OptimisticLockingFailureException.class,
                ex -> new InventoryChangedException(productId, ex));
~~~

The service can ask the client to retry with the fresh state or perform a bounded read-compute-write loop itself if business rules allow.

## 15. Separating Data Access Errors from Business Errors

Do not couple the entire domain to **DataAccessException**. It is a Spring persistence-layer exception.

Example translations:

| Persistence error | Possible mapped business meaning |
|---|---|
| **DuplicateKeyException** on email constraint | Email is already registered |
| **DataIntegrityViolationException** from order FK | Invalid customer or product |
| **OptimisticLockingFailureException** | Data was updated by someone else |
| **CannotAcquireLockException** | Resource is busy; may ask to retry |
| **QueryTimeoutException** | System is slow; ask to retry later |
| **BadSqlGrammarException** | Implementation bug; usually not mapped to a user-specific error |
| **DataAccessResourceFailureException** | Database temporarily unavailable |

Domain exceptions should express something the caller can act on:

~~~java
public class InventoryChangedException extends RuntimeException {
    public InventoryChangedException(Long productId, Throwable cause) {
        super("Inventory changed; reload the latest quantity for product "
                + productId, cause);
    }
}
~~~

Do not convert every database error into **IllegalArgumentException** or HTTP 400. A broken SQL query is a system error; the client cannot fix it by changing the request payload.

## 16. Mapping Exceptions to HTTP Responses

In a WebFlux application, **@RestControllerAdvice** can map domain exceptions to HTTP statuses.

Example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(EmailAlreadyRegisteredException.class)
    ResponseEntity<ApiError> handleDuplicateEmail(
            EmailAlreadyRegisteredException ex) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "EMAIL_ALREADY_REGISTERED",
                        "Email is already registered"));
    }

    @ExceptionHandler(CustomerNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "CUSTOMER_NOT_FOUND",
                        "Customer was not found"));
    }

    @ExceptionHandler(DataAccessResourceFailureException.class)
    ResponseEntity<ApiError> handleDatabaseUnavailable(
            DataAccessResourceFailureException ex) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "DATA_STORE_UNAVAILABLE",
                        "The data service is temporarily unavailable"));
    }
}
~~~

This is an illustrative template; the **ApiError** type and response format vary by API. In many applications, the service already translates persistence exceptions into domain exceptions before reaching controller advice, so the handler only needs to know about domain errors.

Never return **ex.getMessage()** or database stack traces to clients. Those details can expose SQL, table names, constraints, server addresses, or input data.

## 17. Exception Translation When Using the R2DBC SPI Directly

If code works directly with **ConnectionFactory**, **Connection**, **Statement**, and **Result**, errors may remain raw R2DBC driver exceptions.

At the direct SPI layer, do not assume exceptions are automatically translated to **DataAccessException** as they are with Spring abstractions. Choose one of two approaches:

1. Have the persistence adapter catch driver errors and translate them into the application's domain/persistence exceptions.
2. Use the Spring R2DBC exception translator appropriate for your version to standardize errors.

Do not scatter vendor code mapping tables throughout services. If SQLState or vendor-specific error codes must be inspected, isolate that logic in a driver/database-specific adapter.

When using the SPI directly, you must still manage connection cleanup on success, error, and cancellation. Exception translation does not replace resource release obligations.

## 18. Logging and Error Observability

An exception can contain useful diagnostic details:

- Exception class.
- Cause chain.
- SQLState or vendor code.
- Constraint name if provided by the database.
- Operation/service name.
- Trace ID or request correlation ID.

Do not log every bind value or entire entity payloads. Some queries carry emails, phone numbers, payment details, or tokens.

Log at a single boundary with sufficient context to avoid logging the same failure multiple times across repository, service, controller, and global handler.

Metrics can be categorized by stable exception groups, for example:

- **data_integrity_violation**
- **query_timeout**
- **resource_failure**
- **concurrency_failure**
- **bad_sql_grammar**
- **uncategorized_r2dbc**

Avoid using raw messages or dynamic SQL as metric labels because of high cardinality and potential data leakage.

## 19. Common Mistakes When Using DataAccessException

| Mistake | Consequence | Solution |
|---|---|---|
| Catching a single vendor's exception in the service | Business layer coupled to driver/database | Handle **DataAccessException** or domain exceptions |
| Assuming every unique error is **DuplicateKeyException** | Some drivers translate only to **DataIntegrityViolationException** | Verify actual exception behavior on the target driver |
| Treating **Mono.empty()** as a database error | Returns wrong status when no rows match | Use **switchIfEmpty** for not-found rules |
| Wrapping publisher creation in try/catch | Fails to catch errors emitted upon subscription | Use **onErrorMap**, **onErrorResume**, **doOnError** |
| Turning every **DataAccessException** into empty | Masks SQL, connection, and constraint failures | Only recover from well-understood error types |
| Retrying every exception | Repeats permanent failures and overloads the database | Retry with filters, backoff, and limits |
| Retrying stale entity after optimistic locking failure | Continues conflicting or writes wrong business state | Re-read and recalculate |
| Swallowing errors with **onErrorResume** inside a transaction | Transaction may commit if not rollback-only | Propagate errors or mark rollback-only |
| Treating one database's SQLState as universal | Breaks when switching database/driver | Isolate vendor-specific mappings |
| Returning database exception messages to clients | Leaks SQL, schema, or internal details | Map to safe error codes |
| Logging sensitive bind parameters | Leaks personal data or secrets | Redact and log only essential metadata |
| Assuming direct SPI auto-translates exceptions | Service layer receives inconsistent driver errors | Use Spring abstractions or a dedicated translator/adapter |

## 20. Data Access Error Handling Workflow

When a database publisher emits an error, follow this sequence:

1. Identify the actual exception and cause chain.
2. Determine whether the error has been translated by Spring to **DataAccessException** or remains a driver **R2dbcException**.
3. Classify the error as data integrity, SQL/API usage, resource, timeout, or concurrency.
4. Check if the error is genuinely transient and the operation is safe to retry.
5. If the error carries business meaning, map it to a domain exception at the service boundary.
6. If the error is an infrastructure failure, propagate the error signal so the API/global handler returns an appropriate status.
7. If inside a transaction, ensure the error is not swallowed in a way that causes an unintended commit.
8. Log safely, preserving the cause and correlation ID.
9. Test against the real database/driver, as translators can classify errors differently.

Reference decision table:

| Outcome type | Action |
|---|---|
| Empty publisher | Handle according to use case contract |
| **DuplicateKeyException** | Map to a duplicate-data domain error |
| **DataIntegrityViolationException** | Identify the violated constraint and related data |
| **BadSqlGrammarException** | Fix SQL or mapping; do not retry |
| **InvalidDataAccessApiUsageException** | Fix API usage or parameters |
| **TransientDataAccessException** | Retry only if the operation is idempotent and the error is selected |
| **OptimisticLockingFailureException** | Re-read and recalculate, or return conflict |
| **DataAccessResourceFailureException** | Check database, network, and connection pool |
| **UncategorizedR2dbcException** | Use cause/SQLState/vendor code to diagnose; avoid guessing |

## 21. Testing Exception Translation

Unit tests can confirm that a service translates Spring exceptions into domain errors as expected. However, unit tests mocking **DuplicateKeyException** do not prove the real driver will emit that exact exception.

Integration tests should run against the database/driver used by the application and verify:

- Inserting a duplicate unique key.
- Foreign key violation.
- NOT NULL or CHECK constraint violation.
- Invalid SQL syntax or column name.
- No rows found.
- Timeouts or connection errors if the test environment supports simulating them.
- Optimistic locking conflict with two concurrent reads/updates.

Example testing domain mapping:

~~~java
StepVerifier.create(customerService.register(customer))
        .expectError(EmailAlreadyRegisteredException.class)
        .verify();
~~~

Example testing an actual repository:

~~~java
StepVerifier.create(customerRepository.save(duplicateCustomer))
        .expectError(DataIntegrityViolationException.class)
        .verify();
~~~

The exact exception class checked in integration tests should reflect the actual behavior of your Spring version, driver, and database. If the translator returns a specific subtype, assert that subtype; otherwise, assert the appropriate parent class and inspect the cause/SQLState as needed.

Do not write tests that merely assert every failure is a **DataAccessException**. Verify the critical contracts the service relies on, especially the distinction between empty results, data errors, and infrastructure failures.

## 22. Key Takeaways

- **DataAccessException** is Spring's unchecked exception hierarchy for standardizing data access errors.
- Spring translates many driver **R2dbcException** instances into semantically meaningful **DataAccessException** groups.
- **NonTransientDataAccessException** usually requires fixing SQL, data, privileges, or code; retrying the same operation rarely helps.
- **TransientDataAccessException** may be recoverable, but retries must have filters, backoff, limits, and idempotency guarantees.
- **DataIntegrityViolationException** covers integrity errors; **DuplicateKeyException** is a specific subtype when the translator recognizes duplicates.
- **BadSqlGrammarException**, **QueryTimeoutException**, **ConcurrencyFailureException**, and **OptimisticLockingFailureException** describe distinct failure groups requiring tailored handling.
- SQLState/vendor codes and exception subtypes depend on the database/driver; do not treat one database's codes as universal.
- Repositories, **R2dbcEntityTemplate**, and **DatabaseClient** apply Spring exception translation; direct R2DBC SPI may expose raw driver exceptions.
- **Mono.empty()** and **Flux.empty()** indicate no data found, not a **DataAccessException**.
- Reactive errors surface on subscription; use **doOnError**, **onErrorMap**, and **onErrorResume** instead of try/catch around publisher creation.
- Catch specific subtypes before parent classes; only map persistence errors to domain exceptions when the business layer understands their meaning.
- Never swallow errors inside a transaction without clearly deciding commit vs. rollback behavior.
- Retry the entire transaction at the appropriate boundary; do not repeat external side effects without idempotency or an outbox.
- Never return SQL, stack traces, vendor codes, or sensitive bind values to clients.
- Use integration tests on the real database/driver to verify exception translation and actual behavior.

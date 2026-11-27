# Distinguishing Missing Data from Query Failures

In Spring Data R2DBC, a query that finds no rows and a query that fails to execute are two completely different outcomes. The case where no matching rows exist is typically represented by `Mono.empty()` or a `Flux` that completes without emitting any elements. A failed query is represented by a Reactor error signal (`onError`).

Distinguishing these two cases accurately is critical. If you turn every database error into `Mono.empty()`, the application may report "data not found" when the database actually lost connectivity, the SQL was invalid, access was denied, or mapping failed. Conversely, treating an empty result as a system error can cause an API to return unnecessary errors for a valid query.

## 1. Two Kinds of Outcomes in Reactive Flows

A `Mono<T>` has three primary terminal states:

- **Has a value:** emits one `T` element, then completes.
- **Empty:** emits no elements and completes (`Mono.empty()`).
- **Error:** emits an error and terminates (`onError`).

A `Flux<T>` can likewise complete normally after emitting 0 or more elements, or terminate with an error. Emitting zero elements is not synonymous with an error.

| Scenario | Typical reactive outcome | Meaning |
|---|---|---|
| `SELECT` matches no rows | `Mono.empty()` or empty `Flux` | Query succeeded, but no matching data exists. |
| `SELECT` finds one row | `Mono.just(value)` | One result was found. |
| `SELECT` finds multiple rows | `Flux` emits multiple items; single-result API may raise a cardinality error | Result count violates the contract if the caller requested at most one row. |
| Database unreachable | `onError` | Infrastructure or connection failure. |
| Invalid SQL syntax or wrong column name | `onError` | Statement or schema error. |
| Insufficient privileges to execute SQL | `onError` | Access permission error. |
| Returned value cannot map to Java type | `onError` | Conversion/codec/mapping failure. |
| Valid `DELETE` with no matching rows | Typically emits `rowsUpdated = 0` | Command succeeded, but no rows were affected. |

The key takeaway: `Mono.empty()` is a valid completion outcome of a publisher, whereas `onError` is a failure termination. The two states must be handled separately.

## 2. No Rows Is Not the Same as a SQL NULL Column

Two different situations are frequently confused:

1. Zero rows are returned.
2. One row is returned, but one or more of its columns contain SQL `NULL`.

For example, the `customer` table has a row whose `nickname` column is `NULL`. Querying by ID still returns a `Customer`; the `nickname` property can be `null` if the Java type and mapping allow it.

Conversely, if no row carries that ID, the repository `findById` returns `Mono.empty()`.

```java
Mono<Customer> customer = customerRepository.findById(customerId);
```

- `Mono.just(customer)` may contain an object where `customer.getNickname()` is `null`.
- `Mono.empty()` means no `Customer` object was emitted at all.
- `onError` means the read operation did not finish normally.

SQL uses `IS NULL` to filter null columns:

```sql
SELECT id, email
FROM customer
WHERE nickname IS NULL;
```

The expression `nickname = NULL` does not check for null under SQL three-valued logic; comparing against `NULL` yields unknown. Use `IS NULL` or `IS NOT NULL`.

## 3. Repositories Returning Mono and Flux

In reactive repositories, the return type expresses the expected result cardinality:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByTenantIdAndEmail(UUID tenantId, String email);

    Flux<Customer> findByTenantIdAndStatus(UUID tenantId, CustomerStatus status);
}
```

`findByTenantIdAndEmail` can complete empty if no matching customer exists. `findByTenantIdAndStatus` can emit 0, 1, or many customers; if no rows exist, the `Flux` simply completes without emitting items.

A connection failure or SQL error never turns into an empty publisher. It is emitted as an error so the calling layer can log, classify, retry when appropriate, or return an error response to the client.

If a query declares `Mono<T>` yet actually returns multiple rows, Spring Data may emit a result-size error rather than silently picking one row. Do not use a cardinality error to represent "not found"; it signals that the result-count contract was violated.

## 4. Distinguishing with DatabaseClient

`DatabaseClient` lets you observe directly how a query returns data:

```java
Mono<Customer> findCustomer(UUID tenantId, String email) {
    return databaseClient.sql("""
            SELECT id, tenant_id, email, nickname
            FROM customer
            WHERE tenant_id = :tenantId
              AND email = :email
            """)
        .bind("tenantId", tenantId)
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("tenant_id", UUID.class),
            row.get("email", String.class),
            row.get("nickname", String.class)
        ))
        .one();
}
```

With `.one()`:

- Zero rows: publisher completes empty.
- One row: publisher emits one `Customer`.
- More than one row: publisher emits a result-size error.
- SQL or connection failure: publisher emits a database error.

If the business logic only wants one row by priority order, you can use `.first()` alongside an explicit `ORDER BY` in SQL. `.first()` does not verify that only one row matches; it takes the first row and discards the rest. Do not use `.first()` to hide duplicate data when a query ought to be unique.

If you want to read all rows, use `.all()` to receive a `Flux<T>`:

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE tenant_id = :tenantId
        ORDER BY id
        """)
    .bind("tenantId", tenantId)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("email", String.class)))
    .all();
```

If no rows match, the `Flux` completes normally without emitting items. Consumers can use `switchIfEmpty` or `hasElements` if special behavior is needed for the empty case.

## 5. Using switchIfEmpty for Not-Found Cases

`switchIfEmpty` runs the alternative publisher only when the original publisher completes without emitting a value. It does not catch database errors.

Example translating an empty result into a business `CustomerNotFoundException`:

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

If `findById` returns a customer, the value passes through. If no row exists, the service emits a not-found error. If the database loses connection, the connection error continues downstream to the consumer; `switchIfEmpty` does not replace it.

You can use `defaultIfEmpty` when the business domain genuinely defines a default value:

```java
return settingsRepository.findById(userId)
    .defaultIfEmpty(UserSettings.defaultsFor(userId));
```

Only use a default value when "no custom settings exist" has valid business meaning. For mandatory records like accounts, orders, or access permissions, substituting a synthetic object can mask data errors and cause incorrect behavior.

## 6. Using onErrorResume Selectively

`onErrorResume` handles the error path. Only use it when you can identify the error type and have a valid recovery strategy.

Example of selective error handling:

```java
return customerRepository.findById(id)
    .onErrorResume(CustomerReadUnavailableException.class, error ->
        cacheRepository.findCustomer(id)
    );
```

This example assumes the persistence layer translated a specific failure into `CustomerReadUnavailableException`, and the cache can supply fallback data under system policy. Do not fall back to a cache when the error is invalid SQL, broken mapping, or missing data if those scenarios should not be masked.

Avoid writing:

```java
return customerRepository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

This snippet turns every error into "not found." Connection errors, timeouts, access denials, schema bugs, codec failures, and cardinality errors are all hidden. Callers have no way to know the database failed.

Likewise, `onErrorComplete()` turns an error into a normal completion without emitting data. Only use it when business rules permit ignoring a specific failure and proper logs/metrics are recorded; never use it as a blanket way to make a pipeline "never fail."

## 7. Classifying Errors at the Spring and R2DBC SPI Layers

When using `DatabaseClient`, Spring typically applies exception translation to convert data access errors into appropriate `DataAccessException` types. When calling the R2DBC SPI directly, the application may receive exceptions from `io.r2dbc.spi`, typically `R2dbcException` or a subclass.

Common error groups:

| Group | Examples | Handling approach |
|---|---|---|
| Transient connection/resource | Database restart, dropped connection, pool unable to issue connection | Log/record metrics; bounded retry if operation is safe. |
| Timeout | Query exceeded duration, connection acquisition timeout | Identify whether timeout occurred at pool, driver, or database; never treat as missing data. |
| SQL/schema | Syntax error, missing table/column, incompatible type | Fix SQL or migration; retrying usually does not help. |
| Access privileges | Database account lacks permissions | Fix permission configuration or credentials; do not fall back to empty. |
| Constraint | Unique, foreign key, or check constraint violation | Map to an appropriate business error if the constraint is identified. |
| Conversion/codec | Unable to read/write Java or column type | Inspect mapping, converters, and driver codecs. |
| Cardinality | Single-result query returns multiple rows | Fix predicates/constraints or use a multi-result API matching intent. |

Do not rely on exception message strings to classify errors because messages vary by driver, database, and version. When detailed classification is needed, inspect the exception type, SQL state, vendor error code, and root cause (`getCause()`) via the actual APIs.

## 8. Distinguishing Not Found from Zero Affected Rows

Write operations have different semantics from read queries.

### 8.1 UPDATE or DELETE matching no rows

With `DatabaseClient`, `.fetch().rowsUpdated()` returns the count of updated or deleted rows:

```java
Mono<Long> updated = databaseClient.sql("""
        UPDATE customer
        SET display_name = :name
        WHERE id = :id
        """)
    .bind("name", name)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

If the statement runs successfully but matches no rows, the result is typically `0`. This is a normal numeric value, not `Mono.empty()` and not a query error. If the driver/database returns an error during execution, the publisher emits `onError`.

The service can interpret the affected row count:

```java
return updated.flatMap(count -> {
    if (count == 0) {
        return Mono.error(new CustomerNotFoundException(id));
    }
    if (count != 1) {
        return Mono.error(new UnexpectedUpdateCountException(count));
    }
    return Mono.empty();
});
```

For an update by ID, `count == 1` is usually the expected result. For bulk updates, counts greater than one may be valid and should be handled per business rules.

### 8.2 Mono<Void> completing empty means success

A method returning `Mono<Void>` emits no elements when it completes successfully. Thus, you cannot infer "no data found" from a `Mono<Void>` emitting no value. Examine what operation the publisher represents and whether an error was emitted.

Example:

```java
Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
```

`deleteById` can complete successfully without emitting a value. If you need to know whether any row was deleted, use an API that returns the affected row count or execute an appropriate query; do not interpret an empty `Mono<Void>` as a not-found error.

## 9. Aggregate Queries Still Return a Row When Count Is Zero

A `COUNT(*)` query is unlike an entity selection query. Even when the table has no matching rows, an aggregate query without `GROUP BY` still returns one row with a count value of 0:

```sql
SELECT COUNT(*) AS total
FROM customer
WHERE tenant_id = :tenantId;
```

Consequently, `DatabaseClient.one()` for this query typically emits a result containing `total = 0`, not `Mono.empty()`. Similarly, `SUM` or `AVG` can return `NULL` when there are no matching input values, depending on the expression and database; that is a row with a null column, not necessarily zero rows.

If `GROUP BY` is used and no groups match, the result may contain zero rows. Understand the SQL semantics of the query rather than relying solely on the aggregate function name.

## 10. LEFT JOIN and Rows with NULL Related Columns

A `LEFT JOIN` can return a left-side row even when no matching right-side row exists. The right-side columns then have SQL `NULL` values:

```sql
SELECT c.id, c.email, p.id AS profile_id, p.bio
FROM customer c
LEFT JOIN customer_profile p ON p.customer_id = c.id
WHERE c.id = :id;
```

If the customer exists without a profile, the query still returns one row; `profile_id` and `bio` are null. This is not `Mono.empty()`.

If no customer exists with that ID, the entire query returns zero rows and `.one()` completes empty. When mapping nested DTOs, check `profile_id` before constructing a profile object; otherwise you might create a dummy profile with all properties null.

## 11. Retrying Is Not How You Handle Empty Results

Retries fit specific transient failures, such as connection errors or serialization conflicts. Do not retry a query simply because no rows were found: the database executed successfully and found no data at that moment.

Example:

```java
return repository.findById(id)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isTransientDatabaseFailure));
```

`isTransientDatabaseFailure` must classify transient errors by exception type or driver/database error codes. Do not retry all exceptions, and do not use retries to paper over SQL bugs or missing data.

For reads, retrying may return different results if data is created during the wait; consider business semantics. For writes, retrying also requires evaluating idempotency to avoid duplicate writes if the server executed the command but the client lost the response.

## 12. Translating Outcomes into HTTP Responses

At the API layer, cases can be mapped using clear rules:

| Persistence/service state | Typical API response |
|---|---|
| Resource found | `200 OK` with representation, or `204 No Content` for bodyless operations. |
| Resource missing by ID | `404 Not Found` if endpoint semantics require reading a specific resource. |
| Valid request with no search matches | `200 OK` with an empty list if the endpoint is a list search. |
| Business/unique conflict | `409 Conflict` when aligned with the API contract. |
| Database temporarily unavailable | Typically `503 Service Unavailable` or an appropriate server error. |
| SQL/mapping/configuration failure | `500 Internal Server Error`; never return `404`. |

Not every `Mono.empty()` should turn into HTTP 404. For multi-result search endpoints, an empty list is normally a successful response. For single-resource read-by-ID endpoints, `switchIfEmpty` can convert emptiness into a not-found exception so the exception handler maps it to 404.

Never send internal details such as SQL, table names, credentials, or stack traces to clients. Log internally with a correlation ID and enough detail for investigation while avoiding sensitive data.

## 13. Designing Services to Separate Empty from Error

A service can define an explicit return contract:

```java
public Mono<CustomerView> getCustomer(Long id) {
    return customerRepository.findById(id)
        .map(CustomerView::from)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(
            DataAccessResourceFailureException.class,
            error -> new CustomerStoreUnavailableException(error)
        );
}
```

In this example, the no-rows case becomes a business not-found error. A specific database resource error is translated into a meaningful service error. Other errors continue propagating upstream to be handled at the appropriate exception handler layer.

In practice, exception translation can vary depending on whether you invoke `DatabaseClient`, repositories, or the R2DBC SPI directly. Use the exact exception types provided by your running Spring version; do not copy an exception class name if your dependencies do not provide it. If you want a stable abstraction, define custom exceptions at the persistence adapter layer and translate only recognized errors.

## 14. Testing Each State Separately

A single-result read query should have at least three scenarios:

| Scenario | Data/condition | Expected verification |
|---|---|---|
| Not found | No rows match the predicate | `Mono.empty()` or the not-found error explicitly mapped by the service. |
| Found | Exactly one matching row | Emits the expected entity/DTO. |
| Query failure | Database disconnected, invalid SQL, or access denied | Publisher emits an error; never converted to empty. |
| Unexpected multiple rows | Single-result query returns two rows | Cardinality error or well-defined row selection rule. |
| Null column | Row exists with a SQL `NULL` column | Entity is still emitted; nullable property maps properly. |

For updates/deletes, also test:

- `rowsUpdated = 0` when no rows match.
- Positive row count when changes occur.
- `onError` when the statement fails.
- `Mono<Void>` completing normally on success if the API is designed that way.

Unit tests can use `StepVerifier` to assert reactive signals:

```java
StepVerifier.create(service.getCustomer(404L))
    .expectError(CustomerNotFoundException.class)
    .verify();
```

For database failures, you can stub a failing publisher to verify the service does not turn it into empty. However, integration tests against a real database/driver remain necessary to confirm connection, SQL, constraint, and mapping errors are emitted as expected.

## 15. Anti-Patterns to Avoid

| Anti-pattern | Problem |
|---|---|
| `onErrorResume(error -> Mono.empty())` | Masks all database errors as not found. |
| `onErrorComplete()` across an entire repository chain | Drops error signals and can report false success. |
| Using `first()` for queries that should be unique | Hides duplicate data or missing query filters. |
| Treating SQL `NULL` as `Mono.empty()` | Confuses a null column in a row with no row at all. |
| Treating `rowsUpdated = 0` as a connection error | Confuses a valid zero-impact statement with an execution failure. |
| Retrying on `Mono.empty()` | Repeats queries without reason and adds unnecessary load. |
| Retrying every exception | Repeats unrecoverable errors and risks duplicate side effects. |
| Returning 404 for every database error | Masks infrastructure outages and violates the HTTP contract. |

## 16. Query Result Handling Workflow

When building a data access service, determine these in order:

1. Is the query expected to return one row, multiple rows, or aggregate values?
2. Is having zero rows a valid business state or should it become a not-found error?
3. Can any columns be SQL `NULL`, and do the Java types represent them properly?
4. Does the chosen API (`one`, `first`, `all`, repository `Mono`/`Flux`) match the intended cardinality semantics?
5. At which layer are connection, SQL, privilege, constraint, codec, and cardinality errors propagated or translated?
6. Is retrying allowed, and what are the idempotency conditions?
7. For writes, how should `rowsUpdated = 0`, positive counts, and `onError` be distinguished?
8. Should the external API return 404, an empty list, 409, or a server error under the contract?

Missing data and failed queries are two independent states. Use `Mono.empty()`/empty `Flux` for zero-row results, preserve `onError` for execution failures, and use `rowsUpdated` to interpret write impact. Using `switchIfEmpty` for not-found cases and selective `onErrorResume` for recoverable errors helps the application preserve data semantics, avoid hiding database outages, and return consistent responses to callers.

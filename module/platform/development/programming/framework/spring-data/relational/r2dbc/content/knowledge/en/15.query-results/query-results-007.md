# Maintaining a Single-Result Contract and Handling Unexpected Multiple Results

In Spring Data R2DBC, the reactive return type expresses the number of results expected by the application layer. `Mono<T>` represents at most one element, while `Flux<T>` represents a sequence containing zero to many elements. When a query is designed to locate a single record, the application must protect that contract: missing results must be handled explicitly, a single result must be returned properly, and unexpected multiple results must be detected rather than silently picking an arbitrary record.

This is not merely a matter of choosing a return type. It also involves unique constraints in the database, query predicates, Reactor operators, SQL result ordering, and join mappings. Using `first()` to mask a query that ought to be unique can allow duplicate data to persist unnoticed for a long time.

## 1. Cardinality Contracts of `Mono` and `Flux`

Reactive Streams do not emit `null` as an element. A `Mono<T>` can emit one value and complete, complete empty, or emit an error. A `Flux<T>` can emit 0, 1, or many values and then complete or emit an error.

| Return Type | Valid Element Count | Common Meaning |
|---|---:|---|
| `Mono<Customer>` | 0 or 1 | Find one customer by ID, unique email, or business key. |
| `Flux<Customer>` | 0 to many | Find a list of customers by status or filter criteria. |
| `Mono<Long>` | 1 value or empty depending on API | Affected row count, count, or aggregated value. |
| `Mono<Boolean>` | 1 value or empty depending on API | Existence check result if the service explicitly returns a boolean. |
| `Mono<Void>` | Emits no elements | Only cares whether the operation completes or errors, e.g., delete or audit write. |

`Mono<Customer>` does not guarantee that the database contains strictly one row. It indicates that the consumer expects at most one `Customer`. The query may still find no matching rows; that case is represented by `Mono.empty()`. If the database returns multiple rows for an API requiring at most one result, behavior depends on the execution abstraction: cardinality-checking APIs raise a result-size error, whereas APIs taking the first element may discard the rest.

## 2. Declaring Repositories Matching Result Cardinality

In repositories, choose the return type based on the business meaning of the query:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByTenantIdAndEmail(UUID tenantId, String email);

    Flux<Customer> findByTenantIdAndStatus(UUID tenantId, CustomerStatus status);
}
```

The first method represents a single customer within a tenant by email. If email must be unique per tenant, the schema needs a corresponding unique constraint. The second method can return multiple customers, so it uses `Flux<Customer>`.

Example with a declared query:

```java
@Query("""
    SELECT *
    FROM customer
    WHERE tenant_id = :tenantId
      AND email = :email
    """)
Mono<Customer> findByTenantAndEmail(
    @Param("tenantId") UUID tenantId,
    @Param("email") String email
);
```

When declaring a single-result query with `Mono<T>`, Spring Data R2DBC expects the query to return no more than one row. If the query returns multiple rows, the operation may emit `IncorrectResultSizeDataAccessException` instead of picking an arbitrary row. This signals that the query predicate, data, or constraints fail to satisfy the single-result contract.

Conversely, if business logic genuinely needs all results, declare `Flux<T>`. Do not use `Mono<T>` simply because a service currently wants to read one item when the query can validly return multiple rows.

## 3. Distinguishing `DatabaseClient`'s `one()`, `first()`, and `all()`

`DatabaseClient` offers result retrieval methods with different cardinalities. After calling `fetch()`, you can choose:

- `one()`: returns `Mono<T>`, accepting 0 or 1 row; if more than one row is returned, emits a result-size error.
- `first()`: returns `Mono<T>` containing the first row if present; remaining rows are not forwarded to the consumer.
- `all()`: returns `Flux<T>` containing all rows.

Example querying by an email expected to be unique:

```java
Mono<Customer> customer = databaseClient.sql("""
        SELECT id, tenant_id, email, display_name
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
        row.get("display_name", String.class)
    ))
    .one();
```

`one()` fits when multiple rows indicate a data bug or an insufficient query predicate. If the goal is solely to retrieve the leading record under a deterministic order, use `first()` or a bounded query after adding an explicit `ORDER BY`.

Do not confuse `first()` with a uniqueness check. `first()` only satisfies the desire to pick one row; it does not verify that only one row matched the predicate.

## 4. Reactor Operators and Cardinality Semantics

When you have a `Flux<T>` yet a service needs to return `Mono<T>`, Reactor provides several operators with different semantics:

| Operator | Result | Behavior When Multiple Elements Exist |
|---|---|---|
| `next()` | `Mono<T>` | Takes the first element and completes; subsequent elements are ignored. |
| `take(1)` | `Flux<T>` | Keeps at most the first element. |
| `single()` | `Mono<T>` | Requires strictly one element; empty or more than one produces an error. |
| `singleOrEmpty()` | `Mono<T>` | Allows 0 or 1; more than one produces an error. |
| `collectList()` | `Mono<List<T>>` | Collects all elements into a list in memory. |

Example:

```java
Flux<Customer> matches = repository.findByEmail(email);

Mono<Customer> firstMatch = matches.next();
```

This code simply picks the first result. It does not detect duplicate data.

If the contract requires at most one result:

```java
Mono<Customer> zeroOrOne = repository.findByEmail(email)
    .singleOrEmpty();
```

`singleOrEmpty()` completes empty if no element exists and emits an error if two or more elements exist. If business logic strictly requires exactly one element, `single()` can be used, though the empty-data case must be handled separately.

`collectList()` is useful when a list is bounded and the service needs to process all results. Do not collect an unbounded result set into memory just to pick one element or check for duplicates. You can cap the stream at the first two elements to detect cardinality violations without loading the entire result set.

## 5. Detecting Unexpected Multiple Results

Suppose a query searches for a customer by tenant and email, but the data currently contains two matching rows. If the service uses `.next()`, it returns one row and hides the data bug. If it uses `singleOrEmpty()`, the service emits an error when more than one row exists.

A clean bounded check fetches at most two results:

```java
public Mono<Customer> findUniqueCustomer(UUID tenantId, String email) {
    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("email").is(email)
    );

    return template.select(query, Customer.class)
        .take(2)
        .collectList()
        .flatMap(matches -> {
            if (matches.isEmpty()) {
                return Mono.empty();
            }
            if (matches.size() == 1) {
                return Mono.just(matches.get(0));
            }
            return Mono.error(
                new IncorrectResultSizeDataAccessException(1, 2));
        });
}
```

The example above caps collected elements at two. Zero results yields `Mono.empty()`, one result is returned, and two or more are treated as a contract violation. Ensure `Query`, `Criteria`, `R2dbcEntityTemplate`, and `IncorrectResultSizeDataAccessException` are imported accordingly.

A shorter alternative is using `singleOrEmpty()` directly on `Flux` if Reactor's cardinality exception type suits the application layer. If a consistent persistence exception type is desired, translate the cardinality error into a business exception or `DataAccessException` at the service boundary.

Do not catch every exception and turn it into `Mono.empty()`. Doing so can disguise multiple-row errors, codec errors, connection errors, or SQL errors as "not found". Only translate clearly identified errors and let system errors propagate to higher layers.

## 6. Enforcing Uniqueness in the Database

Application-level checks help detect anomalous data, but they do not replace unique constraints. Two concurrent requests can both verify that an email does not exist yet and simultaneously insert two identical rows. Without a database constraint, both operations can succeed.

If email must be unique within each tenant, create a composite unique constraint:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_email
UNIQUE (tenant_id, email);
```

Database constraints enforce uniqueness under concurrent contention. The application should still handle unique constraint violation errors to return a suitable response, such as reporting that the email is already in use.

Do not rely solely on running `SELECT COUNT(*)` before inserting and assuming data will remain unique. Between the check and the write, another transaction can insert the same value. Unique constraints combined with write-error handling provide the final safeguard.

If a single-result query relies on a predicate unprotected by a unique constraint, decide clearly: are multiple rows a business error, or does the query actually need to select the newest/highest-priority record? If multiple rows are valid, the return type should be `Flux<T>` or a bounded `Mono<List<T>>`.

## 7. When There Are No Results: `Mono.empty()` and Not-Found Handling

`Mono.empty()` is a completion state with no value. It is not the same as a row containing SQL `NULL` columns. For example:

- No row matches `WHERE id = :id`: the repository returns `Mono.empty()`.
- A row exists, but column `nickname` is SQL `NULL`: `Mono<Customer>` still emits a `Customer`, in which the `nickname` property may be `null` if mapping allows it.
- A method returning `Mono<Void>` completes successfully: emitting no value is normal semantics, not a failed operation.

In a service, an empty result can be converted into a business exception:

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)));
}
```

Or supply a default value if business logic permits:

```java
return repository.findById(id)
    .defaultIfEmpty(Customer.guest());
```

`switchIfEmpty` is useful when needing to execute another publisher or emit an error; `defaultIfEmpty` is used when a fallback value is already available. Do not use a default value to mask missing mandatory data.

## 8. When Should You Take the First Element?

Some use cases genuinely want one row chosen from many, such as the latest record, most recent status, or highest priority. In that case, taking the first element is valid provided the ordering is clearly defined.

Example using `ORDER BY` and `LIMIT 1`:

```java
@Query("""
    SELECT *
    FROM customer_session
    WHERE customer_id = :customerId
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """)
Mono<CustomerSession> findLatestSession(Long customerId);
```

`created_at DESC` picks the latest session. `id DESC` serves as a tie-breaker so the order is deterministic if multiple rows share the same timestamp. `LIMIT` syntax may need adjustment depending on the database/dialect.

If `first()` is called on an unordered result, the database makes no guarantee about which row comes first. Results can vary with execution plans, indexes, data, or database versions. Thus, `first()` does not mean "newest", "oldest", or "most important" unless the SQL defines an explicit order.

Derived queries like `findFirstBy...OrderByCreatedAtDesc` or `findTopBy...` can be used if supported by your Spring Data syntax and project version. Check the actual generated query and include a tie-breaker when possible.

## 9. Why a Query Expected to Be Unique Might Return Multiple Rows

When encountering `IncorrectResultSizeDataAccessException` or a Reactor cardinality error, check these causes:

1. **Missing unique constraint:** the data may contain multiple rows with the same business value even though code assumes uniqueness.
2. **Insufficient `WHERE` clause:** the query forgot tenant, record type, status, or part of a composite key.
3. **Duplicate data from migrations/imports:** ingestion processes bypassed constraints or the schema lacked constraints earlier.
4. **One-to-many `JOIN`:** one parent row is joined with multiple child rows, yielding multiple SQL rows for a single logical parent entity.
5. **Improper projection mapping:** the query returns multiple rows for one logical object, yet code treats each row as a standalone object.
6. **Misusing single-row retrieval APIs:** `.first()` or `.next()` hides extra results instead of signaling an error.

Inspect the executed SQL, bind parameters, actual row counts, and schema constraints. Do not patch over it by adding `LIMIT 1` if business rules require uniqueness; doing so only hides the root cause.

## 10. One-to-Many Joins and Duplicate Parent Entities

A join query can produce multiple rows for a single parent entity:

```sql
SELECT o.id, o.order_number, l.id AS line_id, l.product_code
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.id = :orderId;
```

If the order has three lines, the SQL result has three rows. Mapping each row into `PurchaseOrder` and declaring `Mono<PurchaseOrder>` can violate cardinality even though there is only one logical order.

Several ways to handle this:

- If only order header data is needed, query the parent table alone or use `SELECT DISTINCT` on the parent entity columns where appropriate.
- If line-level details are needed, return flat DTOs such as `OrderLineView` via `Flux`.
- If a nested object is needed, group rows by parent ID in the mapping layer or use a query/projection designed for explicit aggregation.
- If you only need to know whether line items exist, use `EXISTS` rather than a multi-row join.

Example existence check:

```sql
SELECT EXISTS (
    SELECT 1
    FROM order_line
    WHERE order_id = :orderId
);
```

A boolean result avoids fetching multiple child rows when the service only needs a yes/no answer.

Spring Data R2DBC has no JPA-style persistence context/identity map to automatically coalesce joined rows into an object graph. Defining the result shape and grouping data is the responsibility of the query/projection or application mapping code.

## 11. Controlling Cardinality Errors in Reactive Chains

Do not use an overly broad `onErrorResume` to handle single-result query errors:

```java
// Avoid: all errors are silently turned into not found.
repository.findByEmail(email)
    .onErrorResume(error -> Mono.empty());
```

This turns connection errors, SQL errors, mapping errors, and multiple-result errors into `Mono.empty()`. Consumers cannot distinguish nonexistent data from system failures.

Instead, handle empty results and known errors separately:

```java
repository.findByEmail(email)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(email)))
    .onErrorMap(
        IncorrectResultSizeDataAccessException.class,
        error -> new DuplicateCustomerDataException(email, error)
    );
```

`onErrorMap` translates only the specified exception type. Connection failures and other persistence errors continue propagating for logging, retry policies, or exception handlers to process properly.

Do not automatically retry cardinality errors. If a query returns multiple rows due to duplicate data, retrying the exact same statement will usually produce the exact same result and merely add database load. Retries are suitable only for identified transient errors, such as certain connection errors or deadlocks, and must consider operation idempotency.

## 12. Do Not Use `collectList()` Indiscriminately

`collectList()` gathers all elements of a `Flux` into a `List` inside a `Mono`. While convenient for small lists, its memory consumption scales with result size.

Avoid writing:

```java
repository.findAll()
    .collectList()
    .map(customers -> customers.get(0));
```

This loads the entire table into memory just to grab one element, fails on an empty list, and masks duplicate results. If you want the first element, use an ordered and bounded query. If you want to verify at most one result, use `singleOrEmpty()` or cap at two rows and validate cardinality.

For large lists, stream via `Flux`, use pagination/keyset pagination, or batch appropriately. Only collect into a list when the size is bounded and memory usage has been accounted for.

## 13. Testing the Result Cardinality Contract

For a single-result query, test at least three scenarios:

| Matching Data | Expected Behavior |
|---|---|
| No rows | `Mono.empty()` or a not-found exception translated by the service. |
| Exactly one row | Emits exactly one entity/DTO. |
| Two or more rows | Emits a cardinality error or follows a clearly defined record-selection rule. |

If the query has joins, add a scenario where one parent row has multiple child rows to confirm SQL results map accurately. If uniqueness relies on tenant and email, test the unique constraint with concurrent requests or duplicate inserts.

Tests should run against a database/driver compatible with production when behavior depends on SQL dialect, unique constraints, or codecs. Unit tests with mocked repositories can verify service handling of `Mono.empty()` and cardinality errors, but they do not prove the database schema actually prevents duplicate data.

## 14. Choosing the API by Business Intent

| Intent | Implementation Approach |
|---|---|
| Find one record by primary key | `findById`, returning `Mono<T>`. |
| Find one record by unique business key | `Mono<T>` paired with a unique constraint and complete predicates. |
| Fetch 0 or 1 row from `DatabaseClient` | `fetch().one()`. |
| Take first row by priority | Deterministic `ORDER BY`, single-row limit, or `first()` after ordering. |
| Require exactly one element from `Flux` | `single()`; handle both empty and multi-element cases. |
| Allow 0 or 1 element from `Flux` | `singleOrEmpty()`. |
| Find a list | `Flux<T>` or collect into a bounded list. |
| Check existence | `existsBy...` or SQL `EXISTS`, without loading the full entity. |

The cardinality contract should be enforced consistently from SQL and repository return types up to services and APIs. `Mono` represents at most one element; it does not enforce data uniqueness on its own. When business rules require uniqueness, protect it with database constraints, use APIs that detect multiple rows, and handle `Mono.empty()` explicitly. Only pick the first element when business rules define a true priority rule and the query specifies deterministic ordering.

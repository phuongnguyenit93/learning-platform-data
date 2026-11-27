# Querying exists, count, and Choosing the Right Operation

## 1. Three Distinct Query Needs

When working with data in Spring Data R2DBC, an application does not always need to load an entity. Many use cases only need to know whether a condition holds, or need an aggregate count.

Three common needs are:

- **Existence:** checking whether at least one record satisfies a condition.
- **Count:** counting how many records satisfy a condition.
- **Read:** retrieving entities or projections when the application genuinely needs record data.

Choosing the right operation ensures the database returns only the information required. If you only need to know whether an email is already taken, loading an entire `Customer` is unnecessary. If you need to display the total number of orders, fetching all orders into Java and counting them creates extra network traffic and memory overhead.

In Spring Data R2DBC, reactive repository methods typically return `Mono<Boolean>`, `Mono<Long>`, or `Flux<T>`. The publisher describes the asynchronous result; the query runs when the publisher is subscribed to.

## 2. Checking Existence with ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` provides two important built-in methods:

```java
Mono<Boolean> existsById(ID id);
Mono<Long> count();
```

`existsById` emits `true` if an entity with the given ID exists, or `false` if not. `count()` emits the total number of entities managed by the repository.

Repository example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {
}
```

Usage:

```java
Mono<Boolean> customerExists = customerRepository.existsById(customerId);

Mono<Long> customerCount = customerRepository.count();
```

The return type is `Mono` because results are delivered via the reactive protocol. With `existsById`, the publisher completes with a boolean value. With `count`, the publisher completes with a numeric count—emitting `0` even when no records exist.

Do not confuse `Mono.empty()` with a non-existent result here. `existsById` represents absence as `false`; `count()` represents an empty table as `0`. `Mono.empty()` is typically how entity-lookup queries such as `findById` represent no matching element.

## 3. Derived Queries: existsBy and countBy

Beyond built-in methods, Spring Data R2DBC supports deriving queries from repository method names. The `exists…By` and `count…By` prefixes clearly express the query intent.

Example:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {

    Mono<Boolean> existsByEmail(String email);

    Mono<Boolean> existsByEmailAndStatus(String email, String status);

    Mono<Long> countByStatus(String status);

    Mono<Long> countByStatusAndCountryCode(String status, String countryCode);
}
```

Property names in derived query methods must match the entity's Java properties, not necessarily the physical database column names.

Example entity:

```java
@Table("customer")
public class Customer {

    @Id
    private UUID id;

    @Column("email_address")
    private String email;

    private String status;

    @Column("country_code")
    private String countryCode;
}
```

Because the entity has an `email` property, the method uses `existsByEmail`. Spring Data uses mapping metadata to resolve that property to the `email_address` column.

### 3.1. existsBy Does Not Load the Entity into the Application

Example:

```java
Mono<Boolean> exists = customerRepository.existsByEmail("lan@example.com");
```

The query checks whether any record has the matching email. Spring Data generates an existence query appropriate for the active dialect and version. The application receives only a boolean result instead of a full `Customer`.

This is a good fit for checks such as:

- Whether an email or customer code is already in use.
- Whether an order exists before performing an action.
- Whether any record is currently in a state requiring processing.
- Whether a user has related records satisfying a condition.

### 3.2. countBy Counts Records Matching a Condition

Example:

```java
Mono<Long> activeCustomers = customerRepository.countByStatus("ACTIVE");
```

This method returns the number of customers whose `status` equals `ACTIVE`. `Long` matches SQL count types, which are typically large integers; avoid `Integer` if row counts could exceed its range.

Conditions can be combined according to Spring Data's query derivation rules, such as `countByStatusAndCountryCode`. If query conditions become complex, involve joins, use specialized expressions, or require custom SQL optimization, use `@Query` or `DatabaseClient`.

## 4. Distinguishing exists, count, and find

| Business Need | Operation to Consider | Common Return Type |
| --- | --- | --- |
| Only need to know if a record exists | `existsBy...` | `Mono<Boolean>` |
| Need total record count | `count()` or `countBy...` | `Mono<Long>` |
| Need one entity by ID | `findById(...)` | `Mono<Entity>` |
| Need multiple entities | `findAll()` or `findBy...` | `Flux<Entity>` |
| Need a few columns for a screen/report | Projection or custom SQL query | `Mono<DTO>` or `Flux<DTO>` |

Avoid loading an entity merely to check existence:

```java
// Unnecessary if only true/false is needed
Mono<Boolean> exists = customerRepository.findById(customerId)
        .map(customer -> true)
        .defaultIfEmpty(false);
```

Instead use:

```java
Mono<Boolean> exists = customerRepository.existsById(customerId);
```

A `findById` query may have to read and map all entity columns. An existence query only needs to answer the existence check. If you already have a `Flux<T>` publisher and want to know whether it emits any elements, Reactor provides `hasElements()`, but for clear repository use cases an `existsBy...` method expresses intent better.

## 5. EXISTS at the SQL Level

In SQL, `EXISTS` checks whether a subquery returns at least one row. The database only needs to determine whether a matching row exists; the values of columns in that row are not needed by the application.

PostgreSQL example:

```sql
SELECT EXISTS (
    SELECT 1
    FROM customer
    WHERE email_address = $1
) AS present;
```

The result is a boolean value. `SELECT 1` is a common convention in EXISTS subqueries because the selected expression does not matter; what matters is whether the subquery produces a row.

The database optimizer can stop scanning as soon as it finds one matching row. However, actual efficiency still depends on the execution plan, indexes, statistics, and filter predicates. Do not assume every `EXISTS` query always reads only a single physical row or is always fast regardless of schema.

### 5.1. Using DatabaseClient for EXISTS Queries

When explicit SQL or engine-specific queries are needed, you can use `DatabaseClient`. The following example targets PostgreSQL:

```java
public Mono<Boolean> customerEmailExists(
        DatabaseClient databaseClient,
        String email) {

    return databaseClient.sql("""
            SELECT EXISTS (
                SELECT 1
                FROM customer
                WHERE email_address = :email
            ) AS present
            """)
            .bind("email", email)
            .map((row, metadata) -> row.get("present", Boolean.class))
            .one();
}
```

The `email` value is bound as a parameter rather than concatenated into SQL. Placeholder syntax and boolean representation depend on the driver/dialect; this example uses the parameter marker supported by `DatabaseClient` and PostgreSQL's boolean type.

When custom SQL is unnecessary, a derived query like `existsByEmail` is more concise and lets Spring Data handle query generation.

### 5.2. EXISTS with Multiple Conditions

Example checking whether a customer has any pending orders:

```sql
SELECT EXISTS (
    SELECT 1
    FROM purchase_order
    WHERE customer_id = $1
      AND status = 'PENDING'
) AS present;
```

In a repository, you can express this via a derived method if the predicates fit:

```java
Mono<Boolean> existsByCustomerIdAndStatus(UUID customerId, String status);
```

For more complex predicates, explicit SQL can be easier to read and maintain than overly long method names.

## 6. COUNT at the SQL Level

`COUNT` is an aggregate function returning a count. A query for total customers:

```sql
SELECT COUNT(*) AS total
FROM customer;
```

Counting active customers:

```sql
SELECT COUNT(*) AS total
FROM customer
WHERE status = 'ACTIVE';
```

In PostgreSQL, `COUNT` returns `bigint`. Thus, in Java it should be read as `Long`:

```java
public Mono<Long> countActiveCustomers(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM customer
            WHERE status = :status
            """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> row.get("total", Long.class))
            .one();
}
```

### 6.1. COUNT(*) vs. COUNT(column)

These two counts mean different things:

```sql
SELECT COUNT(*) FROM customer;
SELECT COUNT(phone_number) FROM customer;
```

- `COUNT(*)` counts all rows in the result set, including rows where nullable columns are `NULL`.
- `COUNT(phone_number)` counts only rows where `phone_number` is not `NULL`.

If the question is "how many customers are there?", `COUNT(*)` is normally used. If the question is "how many customers have provided a phone number?", `COUNT(phone_number)` fits.

### 6.2. COUNT(DISTINCT ...)

`COUNT(DISTINCT column)` counts distinct non-null values according to SQL rules:

```sql
SELECT COUNT(DISTINCT country_code) AS country_count
FROM customer;
```

This returns the number of distinct country/region codes present in the data, not the total number of customers.

### 6.3. Counting After a JOIN

When joining a parent table with a child table in a one-to-many relationship, a single parent record can appear across multiple rows in the result set. In that case, `COUNT(*)` counts joined pairs rather than parent entities.

Example:

```sql
SELECT COUNT(*)
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
```

This query counts joined rows—effectively the number of orders that have a matching customer. To count how many customers have at least one order, use:

```sql
SELECT COUNT(DISTINCT c.id)
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
```

Or express it directly with EXISTS:

```sql
SELECT COUNT(*)
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM purchase_order o
    WHERE o.customer_id = c.id
);
```

Choose the formulation based on what needs to be counted and actual execution plans. `COUNT(DISTINCT ...)` may require deduplication work; EXISTS can be better when you only need to check whether a relationship exists.

## 7. Why Not Use count Instead of exists?

An approach that works functionally but misrepresents the intent:

```java
Mono<Boolean> exists = customerRepository.countByEmail(email)
        .map(count -> count > 0);
```

If you only need to know whether a record exists, counting all matching rows asks for more information than necessary. The database may have to compute the total matching row count, whereas existence only needs to find at least one match.

Write instead:

```java
Mono<Boolean> exists = customerRepository.existsByEmail(email);
```

Similarly, do not load every row into memory just to count them:

```java
// Reads all entities through the driver and counts in the application
Mono<Long> count = customerRepository.findAll().count();
```

If you need the total record count in the database, use:

```java
Mono<Long> count = customerRepository.count();
```

`findAll().count()` is a Reactor operator on a `Flux`: it consumes every element emitted by the source and counts them in the pipeline. It does not magically translate into a SQL `COUNT(*)`. This transfers excessive data through the driver, performs unnecessary entity mapping, and increases latency.

## 8. Choosing Operations Based on Business Questions

Examples of choosing the right approach:

| Business Question | Appropriate Approach | Reason |
| --- | --- | --- |
| Is this email already registered? | `existsByEmail` | Only a boolean is needed |
| Does the order exist before cancellation? | `existsById` or `findById` if status is needed | No need to load the entity if only checking existence |
| How many open orders are there? | `countByStatus` | Exact count is needed |
| Need to display order details | `findById` | Entity data is needed |
| Need the 20 newest customers | Sorted/limited query or custom query | A subset of records is needed |
| Are there any unverified customers? | `existsByVerifiedFalse` if derivation fits | Only existence is needed |
| How many distinct country codes exist? | `COUNT(DISTINCT country_code)` | Distinct value count is needed |

Start from the business question, then choose the minimal result shape that satisfies the requirement. Avoid defaulting to `findAll` and filtering/counting in Java when the database can answer directly.

## 9. Combining exists with Reactive Business Flows

Example registering a customer and checking email uniqueness:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(String email, String name) {
        return repository.existsByEmail(email)
                .flatMap(exists -> {
                    if (exists) {
                        return Mono.error(
                                new EmailAlreadyRegisteredException(email));
                    }

                    Customer customer = new Customer();
                    customer.setEmail(email);
                    customer.setName(name);
                    return repository.save(customer);
                });
    }
}
```

This flow checks existence first before creating the entity. `flatMap` is used because the creation branch returns `Mono<Customer>`. There is no need to call `block()` to extract the boolean before calling `save`.

### 9.1. Checking Existence Before Insert Has a Race Condition

The code above is helpful for returning a friendly message, but it does not guarantee email uniqueness on its own. The following can occur:

1. Request A checks the email and receives `false`.
2. Request B nearly simultaneously checks the same email and also receives `false`.
3. Both requests attempt to insert.
4. Without a unique constraint in the schema, two rows with duplicate emails can be saved.

Therefore, uniqueness must be enforced at the database level:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email_address);
```

The database is what enforces the uniqueness invariant under concurrent writes. The application can still call `existsByEmail` beforehand to fail fast, but it must also handle unique constraint errors on insert in case another request wins the race.

In Spring, unique constraint violations are typically translated into a `DataIntegrityViolationException` or a driver/translator-specific exception. Identify which constraint failed before mapping it to `EmailAlreadyRegisteredException`; do not turn every database error into an "email already exists" message.

With PostgreSQL, you can consider `INSERT ... ON CONFLICT` to handle uniqueness atomically. Because that syntax is PostgreSQL-specific, encapsulate it in a repository/custom persistence adapter and handle the outcome under a clear contract.

### 9.2. Exists Does Not Replace Authorization

An `existsById` query only answers whether a record exists. It does not verify that the current user is permitted to read or modify that record. When enforcing permissions, combine owner, tenant, status, and access policies in the query or domain logic.

For example, checking only `existsById(orderId)` before allowing an edit creates a vulnerability if a user can guess another user's order ID. You may need `existsByIdAndCustomerId` or load the aggregate and verify ownership against the authenticated context.

## 10. Count in Limit Enforcement Rules

Some use cases count records to enforce limits—for example, allowing a customer at most 5 shipping addresses:

```java
public Mono<Long> countAddresses(UUID customerId) {
    return addressRepository.countByCustomerId(customerId);
}
```

The application service might compare the result against the cap:

```java
return addressRepository.countByCustomerId(customerId)
        .flatMap(count -> {
            if (count >= 5) {
                return Mono.error(new AddressLimitExceededException());
            }

            return addressRepository.save(newAddress);
        });
```

This illustrates the logic, yet it still suffers from a race condition. Two concurrent requests could both observe a count of 4 and both insert, bringing the total to 6. If the limit is a strict invariant, concurrency protection must live in the database or data model.

Options depending on business rules and database capabilities:

- Maintain a per-customer counter row and perform a conditional update in a single atomic statement.
- Lock the parent row inside a transaction while checking and inserting, if the database/isolation supports it properly.
- Use constraints or a schema model that allows the database itself to enforce the cap.
- Use a higher isolation level with controlled serialization-failure retries where appropriate.

Merely adding `@Transactional` at the default isolation level does not automatically make a "count then insert" sequence atomic under concurrent requests. Consider isolation levels, locking, and the actual SQL statements.

## 11. Exact Counts Can Be Expensive

`COUNT(*)` returns the exact count as of the query snapshot. On large tables or broad filters, the database may have to scan many index entries or heap rows to compute the total. Indexes can reduce how much data is read, but that does not make every count free.

Recommendations:

- Create indexes aligned with common `WHERE` predicates.
- Inspect execution plans instead of assuming count queries are always fast.
- Avoid running count on every request if the UI does not genuinely need an exact total.
- For dashboards that only need approximate or periodically refreshed numbers, consider summary tables, materialized views, caches, or event-maintained counters.
- When a table is huge and users only need the next page, consider keyset pagination instead of counting everything to render total page counts.

Indexes do not always speed up counts dramatically. If a condition selects a large fraction of the table or the engine must check row visibility across many rows, cost remains high. Every index also adds write overhead and storage cost.

## 12. Count and Pagination

A paginated screen often needs two pieces of information:

1. The list of records for the current page.
2. The total matching record count to calculate total pages or display "N results found."

These are two separate queries: one retrieves page items with sort/limit, and the other counts total matching rows. In reactive repositories, avoid loading all records into memory and slicing or counting them there.

If an exact total is required by the UI, execute a separate count query and account for its cost. If you only need to know whether a next page exists, query `pageSize + 1` items or use a cursor/keyset to detect the next page without counting the entire dataset.

Example PostgreSQL query fetching one page:

```sql
SELECT id, email_address, status
FROM customer
WHERE status = $1
ORDER BY id
LIMIT $2 OFFSET $3;
```

And the total count query:

```sql
SELECT COUNT(*)
FROM customer
WHERE status = $1;
```

The two statements may observe different snapshots if data changes between them outside a transaction with appropriate isolation. Consequently, the total count and page items do not necessarily reflect the exact same instant under continuous updates.

Large `OFFSET` values force the database to skip many rows before returning the requested page. On large tables, keyset pagination on the sort key generally performs much better. Exact `Pageable`/`Sort` support in reactive repositories depends on your Spring Data R2DBC version; when strict control over SQL and pagination behavior is required, use custom queries.

## 13. Count and Exists Queries with @Query

When derived queries cannot express a query, declare SQL using `@Query`. Example counting by status:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {

    @Query("SELECT COUNT(*) FROM customer WHERE status = :status")
    Mono<Long> countForStatus(@Param("status") String status);
}
```

Table and column names inside `@Query` are physical SQL names. `@Param` binds method parameters to named markers in the SQL; Spring Data R2DBC handles the concrete binding syntax per driver/dialect.

For custom existence queries, verify how your database and driver map scalar booleans. PostgreSQL example:

```java
@Query("""
    SELECT EXISTS (
        SELECT 1 FROM customer WHERE email_address = :email
    )
    """)
Mono<Boolean> emailExists(@Param("email") String email);
```

If a query relies on engine-specific syntax, document the target database clearly and test against the real driver. Derived `existsBy...` methods are generally more portable because Spring Data generates SQL via the dialect.

## 14. Handling Reactive Results

Because repositories return publishers, combine results using Reactor operators:

```java
customerRepository.existsById(customerId)
        .flatMap(exists -> exists
                ? Mono.just("Customer found")
                : Mono.just("Customer not found"));
```

Or return the result directly in WebFlux:

```java
@GetMapping("/{id}/exists")
public Mono<Boolean> customerExists(@PathVariable UUID id) {
    return customerRepository.existsById(id);
}
```

WebFlux manages the subscription for the publisher returned by the controller. Inside reactive services, avoid calling `block()` to await a `Boolean` or `Long`, as blocking ties up threads and breaks the reactive execution model.

Do not call `subscribe()` inside a service just to extract a result and continue. `subscribe()` starts a separate subscription, detaching errors and lifecycle from the caller's publisher. Use `map`, `flatMap`, `zip`, or other appropriate operators and return the final publisher.

Connection failures, timeouts, SQL errors, and mapping errors propagate as error signals on the publisher. Handle them with `onErrorMap` or `onErrorResume` when there is a clear business policy; avoid silently turning database errors into `false` or `0`, which conflates "no data" with "unable to check data."

## 15. Testing exists and count

You can use `StepVerifier` to test reactive publishers:

```java
StepVerifier.create(customerRepository.existsByEmail("lan@example.com"))
        .expectNext(true)
        .verifyComplete();

StepVerifier.create(customerRepository.countByStatus("ACTIVE"))
        .expectNext(3L)
        .verifyComplete();
```

These examples assume test data has been seeded and the expected counts match. For repository tests, use a suitable test database and clean data between tests so outcomes do not depend on execution order.

Scenarios worth testing:

- `existsById` when the ID exists and when it does not.
- `existsByEmail` for emails present and absent in the table.
- `count()` on an empty table and on a populated table.
- `countByStatus` for statuses with matches and without matches.
- Null values if properties and queries permit nulls.
- Compound conditions across multiple properties.
- Database errors propagating through the publisher rather than turning into false/zero.
- Unique constraints when two concurrent requests insert duplicate data.

Unit tests can mock repositories to verify how application services handle true/false or count values. However, mocks do not prove the generated SQL is valid, indexes are used, or the driver maps scalar types properly. Those behaviors require integration tests with an actual R2DBC driver and database.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Loading an entity just to check existence | Using `findById` or `findAll` when only a boolean is needed | Use `existsById` or `existsBy...` |
| Counting via `findAll().count()` is very slow | Application reads and consumes every entity before counting | Use `count()` or `countBy...` so the database aggregates |
| Using `count > 0` to check existence | Database must determine total matching rows | Use an existence query |
| `count()` returns `0` while hiding connection errors | `onErrorResume` converts errors to a default value | Separate error handling from a valid count of 0 |
| Duplicate emails despite calling exists before insert | Two requests both checked before either wrote | Add a unique constraint and handle constraint violations |
| Record count limit exceeded | Count-then-insert sequence lacks concurrency protection | Use constraints, locks, or atomic updates as appropriate |
| Count after JOIN exceeds expected entity count | Parent entity appears across multiple rows due to one-to-many join | Use `COUNT(DISTINCT root_id)` or EXISTS as needed |
| Count on a large table is slow | Query counts many rows; missing index or suboptimal plan | Inspect execution plan, indexes, and consider summary/counters |
| Derived query cannot find property | Using SQL column name instead of entity property name | Name methods using Java properties per mapping metadata |

## 17. Choosing the Right Operation for a Use Case

When designing a query, identify the minimal output required:

1. If the answer is strictly yes/no, use `existsBy...` or `existsById`.
2. If an exact quantity is needed, use `count()` or `countBy...`.
3. If record contents are needed, use `findBy...` and fetch only required columns when feasible.
4. If grouped aggregations are needed, use aggregate queries like `COUNT`, `GROUP BY`, or projections.
5. If you only need to know whether a next page exists, avoid full counts when limit/cursor techniques work.
6. If count/exists results guard an invariant before a write, handle race conditions in the database via constraints, locks, or atomic statements.
7. Keep results inside the `Mono`/`Flux` pipeline; let the caller manage subscription and avoid blocking inside reactive flows.

`exists` answers yes or no; `count` answers how many; `find` returns data to work with. Using the right operation reduces data transferred to the application and makes query intent explicit. In Spring Data R2DBC, `existsBy...`, `countBy...`, `ReactiveCrudRepository.existsById()`, and `count()` offer direct reactive APIs, while the database still needs proper indexes, constraints, and transactions to ensure performance and correctness under concurrency.

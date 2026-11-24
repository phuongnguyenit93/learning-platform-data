# Specifying Empty Results, Multiple Results, and Errors in the Spring Data Layer

## 1. Why Must This Be Specified Before Writing a Repository?

A data layer call does not merely "return data". It also carries a **result contract**: no matching record found, exactly one found, multiple found, an overly large result set, or a database access failure. Without explicitly defining each case, two developers can write two methods with the same name where one returns `null`, another returns an empty list, and a third catches every error and returns `Optional.empty()`. As a result, services cannot distinguish "does not exist" from "DB is failing", APIs return wrong HTTP status codes, bad data is masked, and operations become hard to diagnose.

This lesson belongs to **Data Layer Design** in Spring Framework. Its goal is to design **explicit contracts for 0, 1, multiple results, and errors**, applied consistently across JDBC/`JdbcClient`, Spring Data JPA, and R2DBC. "Multiple results" is examined in **two distinct senses**:
- **Multiple result rows** (`0/1/N`): deciding whether a multi-item list is valid or a uniqueness constraint violation.
- **Large result sets**: requiring pagination, limits, stable ordering, conditional streaming, and memory/resource protection.

A sound convention answers four questions before executing a query: **How many records are allowed to be returned? What if no records exist? What if more records than expected actually exist? If data access fails, which layer is responsible for interpreting it?**

## 2. Contract Matrix: 0, 1, N, and Errors

| Query type | 0 rows | 1 row | N rows (N > 1) | Recommended result type |
|---|---|---|---|---|
| Lookup **that may be absent** by unique key | Absent result, normal | Return record | **Data/contract error**, never pick arbitrarily | `Optional<T>` / reactive `Mono<T>` |
| Lookup **required to exist** in a business operation | Raise domain `NotFound` error | Return record | Data/contract error | Value `T` or domain exception |
| Search/list by filter | Empty list | Single-element list | Multi-element list, **bounded** | `List<T>`, `Slice<T>`, `Page<T>`, `Flux<T>` |
| Count records with `COUNT(*)` | **One row with value 0** | One row with value 1 | Still **one row** containing N | `long`/`Long` |
| Update/delete expecting exactly one record | `affectedRows = 0`: interpret per contract | `affectedRows = 1`: success | `affectedRows > 1`: abnormal if exactly one was expected | `int`/`long` and check row count |
| SQL error, timeout, lost connection, constraint | **Not "no data"** | **Not success** | **Not an empty list** | Classified exception, log/trace, conditional retry |

**Absence** is a *valid business outcome* for an optional lookup, yet can be a business error for a command requiring an existing resource. **Data access failure** is an *execution error* and must never be treated as an empty result. These rules must live in method names, return types, documentation, and tests.

### Examples of Semantic Differences

- `findById(42)` used to show a "view details" button: `Optional.empty()` is a normal lookup outcome; the controller can translate it to HTTP 404.
- `findOrdersForCustomer(42)` used to display a list: having no orders is usually `[]` and HTTP 200, not 404.
- `findByExternalCode("ORD-42")` on a table with `UNIQUE(external_code)`: getting two rows is a **data or query violation**, never silently pick the first row.
- `searchOrders(page, size)`: a page beyond existing rows usually returns an empty list, though verify whether out-of-range pages are allowed or should return 400 depending on the API contract.
- `countOrders()` with no orders: `COUNT(*)` still returns one row with value `0`. By contrast, `SUM(amount)` can return one row with value `NULL`; distinguish "no rows" from "a row with a NULL column".

## 3. Designing Data Access Interfaces Around Semantics

Prefer method names that communicate **cardinality** and business intent:

```java
// Interface design code in a Java 17+ project.
package example.orders;

import java.util.List;
import java.util.Optional;

public interface OrderReadPort {
    Optional<OrderView> findByExternalCode(String code);

    List<OrderView> findRecentByCustomer(long customerId, int limit);

    long countByCustomer(long customerId);
}
```

`findByExternalCode` only makes sense for 0 or 1: having multiple records with the same code is an error. `findRecentByCustomer` accepts multiple records yet always enforces a limit. `countByCustomer` returns a count, including `0`, without wrapping it in `Optional` just because the table might be empty.

The **repository/adapter** layer knows the access mechanism and raw DB outcomes. The **service/use case** layer knows whether a resource must exist to complete a business action. The **HTTP/API** layer knows whether to return 404, 409, 500, 503, or JSON `[]`. Keeping these responsibilities separate lets the same repository be reused for batch jobs, HTTP APIs, and tests.

Do not design a method like `Object fetch(String sql)` that forces every caller to cast and guess about `null`. An API named `findFirst...` is appropriate when you genuinely want the **first record under a deterministic ordering** (e.g., the newest order); do not use it to hide duplicate data when uniqueness is required.

## 4. When Data Is Missing: Absence Differs from Failure

### 4.1. Returning Empty as a Normal Outcome

- An optional lookup returns `Optional.empty()` (imperative) or `Mono.empty()` (reactive) when not found.
- A multi-row query returns `List.of()`/an empty list or `Flux.empty()`. **Never return `null` for a collection** because every caller would have to check both "null" and "empty".
- An aggregate query can still return a row. `COUNT(*)` returns `0` when no rows match; `SELECT COUNT(*) ... GROUP BY customer_id` can return **zero rows** when there are no groups. Distinguish SQL shapes clearly.
- If a SQL column can be `NULL`, map to a nullable type, `Optional` where appropriate, or use `COALESCE` when business rules define a default. Do not force `0` onto every NULL: sometimes "unknown" differs from "zero".

### 4.2. Absent When Required to Exist

For example, "capture payment for order #42" cannot proceed if the order does not exist. The repository returns `Optional`; the service translates absence into a meaningful domain error:

```java
package example.orders;

public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(String code) {
        super("Order not found: " + code);
    }
}
```

```java
package example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderReadPort orders;

    public OrderLookupService(OrderReadPort orders) {
        this.orders = orders;
    }

    public OrderView requireByCode(String code) {
        return orders.findByExternalCode(code)
            .orElseThrow(() -> new OrderNotFoundException(code));
    }
}
```

`requireByCode` expresses a **use-case policy**. Another use case calling `findByExternalCode` may treat absence as normal. Avoid unconditionally throwing `NotFound` inside every adapter if the same lookup serves multiple contexts.

### 4.3. Never Turn Technical Errors into "Not Found"

**Wrong pattern:**

```java
// Anti-pattern: even a lost connection gets turned into "does not exist".
try {
    return repository.findByExternalCode(code);
} catch (Exception ex) {
    return Optional.empty();
}
```

The snippet above **illustrates an anti-pattern**, not a standalone program. If the driver times out or the SQL is broken, users see 404 even though the DB may contain the data. Monitoring also loses error signals.

**Right approach:** handle absence solely through the result contract; let technical errors flow through classification, logging/observability, and proper HTTP mapping. Never use `catch (Exception)` to fabricate default values without a proven fallback policy.

## 5. When Multiple Results Exist: Expected Multiple or Only One?

### 5.1. Multiple Results Are Normal

Searching by `customer_id` can return 0..N orders. The contract should include:
- Deterministic ordering: `ORDER BY created_at DESC, id DESC` (with a tie-breaker so order is never arbitrary).
- A `limit` or pagination, validating the maximum allowed limit.
- A projection selecting only needed columns rather than `SELECT *`.
- Indexes matching `WHERE` + `ORDER BY`, verified with query plans.
- Never calling `List.size()` on millions of rows just to "count"; use `COUNT(*)` if a count is truly required, noting that counting can itself be expensive.

### 5.2. Multiple Results Are a Violation

When querying by a key defined as unique, **getting more than one row is an error**, not "a longer list than expected". You should:
1. Enforce `PRIMARY KEY`/`UNIQUE` in the database to prevent race conditions.
2. Use a 0..1 API that checks row count (e.g., `JdbcClient.optional()` or repository `Optional<T>`).
3. If legacy data already contains duplicates, fix the root cause with controlled migration/cleanup; never mask it with `LIMIT 1`.
4. If the real intent is "the latest", express `findLatest...` explicitly with stable ordering. Only then is `LIMIT 1` right, not an arbitrary workaround.

**Specifically:** `findFirstBy...`/`first()` can pick one item from a multi-row query; they **do not verify uniqueness**. `Mono.next()` from a `Flux` likewise just takes the first element. Never use them for keys that must be unique.

### 5.3. Very Large Results Need Limits and Pagination

There are three basic strategies:
- **Page**: one page's content plus total metadata when "page 1 of 120" is needed; may require an extra count query.
- **Slice/Window**: fetches a chunk and whether more data exists, suited for infinite scroll; can avoid full table counts.
- **Keyset/cursor pagination**: fetches rows after a sort-key tuple, avoiding deep `OFFSET` issues. Requires matching predicates and indexes, and cursors must align with filters/sorts and data-mutation policies.

Cursor example with PostgreSQL, fetching only rows **older** than the cursor (when both columns are non-NULL):

```sql
SELECT id, external_code, customer_id, total_cents, created_at
FROM order_records
WHERE customer_id = :customerId
  AND (created_at, id) < (:cursorCreatedAt, :cursorId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

**The first page** omits the cursor condition while keeping the same `WHERE customer_id` and `ORDER BY`. The cursor must come from the last record of the previous page, and `pageSize` must be bounded within allowed limits. Inserts/deletes between requests can shift page contents: define the expected consistency level rather than promising a stable snapshot unless a real snapshot is maintained.

## 6. Example Schema for a Consistent Contract

Illustrated with PostgreSQL:

```sql
CREATE TABLE order_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total_cents BIGINT NOT NULL CHECK (total_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_customer_recent
    ON order_records (customer_id, created_at DESC, id DESC);
```

`external_code` has its uniqueness protected by the database. `customer_id` is **not unique**, so list queries must allow N rows. The second index supports the filter and recent-list ordering. Schema and indexes are a vital part of the contract: Java types alone cannot guarantee uniqueness when two transactions write concurrently.

Shared DTO used across the examples:

```java
// OrderView.java
package example.orders;

public record OrderView(
    long id,
    String externalCode,
    long customerId,
    long totalCents
) {}
```

The Spring snippets below belong to a **Spring Boot/Spring Framework project with the required dependencies** and will not compile with bare `javac` alone because they require Spring libraries, drivers, and a DB connection. To try them in practice, create the schema, configure a datasource/connection factory, add the dependencies, and run the app/tests with Gradle/Maven. The JDBC, JPA, and R2DBC examples are **three illustrative implementations** of the same policy; all three need not be enabled at once.

## 7. JDBC/JdbcClient: Distinguishing `optional()`, `single()`, and `list()`

With Spring Framework 6.1+ (Spring Boot 3.2+), `JdbcClient` provides a fluent API over JDBC. Example dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderJdbcReader.java`:

```java
package example.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcReader implements OrderReadPort {
    private static final RowMapper<OrderView> MAPPER = (rs, rowNum) ->
        new OrderView(
            rs.getLong("id"),
            rs.getString("external_code"),
            rs.getLong("customer_id"),
            rs.getLong("total_cents")
        );

    private final JdbcClient jdbc;

    public OrderJdbcReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<OrderView> findByExternalCode(String code) {
        return jdbc.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE external_code = :code
                """)
            .param("code", code)
            .query(MAPPER)
            .optional();
    }

    @Override
    public List<OrderView> findRecentByCustomer(long customerId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return jdbc.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE customer_id = :customerId
                ORDER BY created_at DESC, id DESC
                LIMIT :maxRows
                """)
            .param("customerId", customerId)
            .param("maxRows", limit)
            .query(MAPPER)
            .list();
    }

    @Override
    public long countByCustomer(long customerId) {
        return jdbc.sql("""
                SELECT COUNT(*)
                FROM order_records
                WHERE customer_id = :customerId
                """)
            .param("customerId", customerId)
            .query(Long.class)
            .single();
    }
}
```

**Behaviors to remember:**
- `.query(MAPPER).optional()`: 0 rows → `Optional.empty()`; 1 row → `Optional.of(value)`; >1 row → `IncorrectResultSizeDataAccessException`. If the key has `UNIQUE`, the last case only occurs due to a broken query/schema design or a view/join duplicating rows.
- `.query(MAPPER).single()`: requires exactly one result; 0 rows → `EmptyResultDataAccessException`; >1 → `IncorrectResultSizeDataAccessException`. Use when **the SQL itself guarantees one row**, such as `COUNT(*)` without `GROUP BY`.
- `.query(MAPPER).list()`: 0 rows → empty list; N rows → list of N items. Never call `list()` on an unbounded query when the dataset can grow huge.
- Binding values with `.param` avoids concatenating input into SQL. Dynamic column names or `ORDER BY` clauses must be selected from an **allowlist**, since SQL identifiers cannot be bound as parameter values.

**With legacy `JdbcTemplate`:** `queryForObject(...)` normally expects one row and can throw `EmptyResultDataAccessException` when empty; `query(...)` returns a list and does not treat empty as an error. Do not use `queryForObject` for 0..N searches.

### One Read Does Not Equal One Successful Write

For `UPDATE`/`DELETE`, the affected row count is a different signal from query row counts:
- `0` may mean not found, mismatched state, stale version, or a row deleted between operations.
- `1` typically means success when targeting a single key.
- `>1` is an **expectation violation** when business rules only allow modifying one record.

Conditional update example:

```sql
UPDATE order_records
SET total_cents = :newTotal
WHERE id = :orderId
  AND total_cents = :expectedOldTotal;
```

If affected rows equals 0, **do not immediately conclude "id does not exist"**: the value/version may have changed. To distinguish "not found" from "conflict", design an explicit lookup policy or version/optimistic-lock contract. Update decisions should always prefer atomic DB conditions over `SELECT` followed by an unconditional `UPDATE`.

## 8. Spring Data JPA: Optional for One Record, List/Page/Slice for Many

Spring Data JPA builds on a JPA provider like Hibernate and commonly uses signatures such as:

```java
// OrderJpaRepository.java - example interface in a JPA project
package example.orders;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderJpaRepository
        extends JpaRepository<OrderEntity, Long> {
    Optional<OrderEntity> findByExternalCode(String externalCode);

    Page<OrderEntity> findByCustomerId(Long customerId, Pageable pageable);
}
```

`OrderEntity` here is an entity mapped to `order_records` with corresponding `externalCode` and `customerId` properties; the snippet above **is part of a project requiring an entity declaration**, not a standalone program.

- `findById(id)` returns `Optional<T>`. When no entity exists, it returns `Optional.empty()`.
- Query method `Optional<T> findByExternalCode(...)` expresses **0..1**. If the query matches more than one entity, Spring Data can throw `IncorrectResultSizeDataAccessException`; a unique constraint protects directly at the database.
- Query `Page<T> findByCustomerId(..., Pageable)` expresses paginated multiple records. When empty, the page content is empty; page metadata reports page/total info (sometimes requiring a count query). If you only need to know whether a next page exists, consider `Slice<T>` to avoid count overhead.
- Collection-returning repository methods normally return an empty collection instead of `null`. Projections/DTOs can avoid loading unnecessary entity graphs.
- Spring Data does not force every method to return `Optional`: choose based on cardinality. A method returning `T` without a clear nullability contract can be confusing; if a result is mandatory, make that explicit in the service and handle absence.

**Watch out with raw JPA:** `EntityManager.getSingleResult()` can throw `NoResultException` or `NonUniqueResultException`. Spring Data repositories usually translate exceptions into Spring's abstraction depending on context. Do not tightly couple code to a specific provider exception without verifying the call boundary.

**N+1 and "large data":** a page of 20 entities where each lazy-loads an association can emit 21+ queries. Pagination does not automatically solve N+1; use projections, appropriate `JOIN FETCH`/`@EntityGraph`, and query-count monitoring. Never return large entities directly from a REST API when only a few columns are needed.

**Streaming from JPA:** a stream can hold a connection/`ResultSet`/transaction open. Consume streaming results inside an appropriate transaction and close the `Stream` (try-with-resources). Streaming does not guarantee the driver fetches row-by-row without buffering; check fetch size, provider, and memory behavior.

## 9. R2DBC: `Mono.empty()`, `Flux.empty()`, and Error Signals

With Spring R2DBC, queries produce reactive publishers. Use `DatabaseClient`/Spring Data R2DBC and a compatible driver:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
```

`ReactiveOrderReader.java`:

```java
package example.orders;

import java.util.Objects;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveOrderReader {
    private final DatabaseClient db;

    public ReactiveOrderReader(DatabaseClient db) {
        this.db = db;
    }

    public Mono<OrderView> findByExternalCode(String code) {
        return db.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE external_code = :code
                """)
            .bind("code", code)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("external_code", String.class),
                ((Number) Objects.requireNonNull(
                    row.get("customer_id"))).longValue(),
                ((Number) Objects.requireNonNull(
                    row.get("total_cents"))).longValue()))
            .one();
    }

    public Flux<OrderView> findRecentByCustomer(
            long customerId, int limit) {
        if (limit < 1 || limit > 100) {
            return Flux.error(
                new IllegalArgumentException("limit must be 1..100"));
        }
        return db.sql("""
                SELECT id, external_code, customer_id, total_cents
                FROM order_records
                WHERE customer_id = :customerId
                ORDER BY created_at DESC, id DESC
                LIMIT :maxRows
                """)
            .bind("customerId", customerId)
            .bind("maxRows", limit)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("external_code", String.class),
                ((Number) Objects.requireNonNull(
                    row.get("customer_id"))).longValue(),
                ((Number) Objects.requireNonNull(
                    row.get("total_cents"))).longValue()))
            .all();
    }
}
```

- `.one()`: 0 rows → `Mono.empty()`; one row → emits one `OrderView`; more than one row → error `IncorrectResultSizeDataAccessException`.
- `.first()`: returns the first row and discards the rest. Use only when the query truly asks for "the first" and `ORDER BY` is meaningful.
- `.all()`: emits 0..N rows; 0 rows → publisher completes without emitting items; never emits `null`.
- `Mono.empty()` **differs from** `Mono.error(...)`. DB access errors are emitted via the `onError` signal when subscribed; never treat them as empty data.
- `Mono`/`Flux` execute on subscription lifecycle; do not manually call `subscribe()` inside a service and return `Mono.empty()` to the caller. Doing so detaches error/transaction handling from the request.
- Reactive does not mean results can be unbounded without consuming resources. The driver, connection count, query, pagination, fetch behavior, and consumer backpressure still govern resource usage.

Converting absence into a use-case error in Reactor:

```java
// Method in a reactive service with ReactiveOrderReader injected.
public Mono<OrderView> requireOrder(String code) {
    return reader.findByExternalCode(code)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(code)));
}
```

This is an **illustrative method inside a service with a `reader` field**, not a complete Java file. `switchIfEmpty` handles only empty completion; SQL/connection errors still travel along the `onError` path. Never write `onErrorResume(ex -> Mono.empty())` for all errors because it turns technical failures into 404/not-found. When a fallback is needed, catch only **specific error types** under conditions where fallback preserves business correctness.

### Testing Reactive Flows with StepVerifier

`StepVerifier` verifies **onNext/onComplete/onError**, not merely return values. Scenarios to test:
- Zero rows → `verifyComplete()` immediately, with no `onNext`.
- One row → `expectNextMatches(...)` then `verifyComplete()`.
- Multiple rows when expecting one → `expectError(IncorrectResultSizeDataAccessException.class)`.
- Query/driver error → receives `onError` signal, not converted into `Mono.empty()`.
- `Flux` may have emitted several rows before encountering an error. If callers require atomicity of returned results, define an explicit policy; a reactive stream can already deliver items before signaling failure.

## 10. Data Layer Errors: Classifying and Choosing a Handling Policy

Spring provides the `org.springframework.dao.DataAccessException` hierarchy to abstract differences across drivers/providers. These are **unchecked exceptions** with many subtypes. Do not assume every JDBC/JPA/R2DBC error translates to the exact same subtype across every dialect/version; test against the real DB.

| Scenario | Common signal | Recommended handling |
|---|---|---|
| Lookup 0 rows, **absence allowed** | `Optional.empty()`, `Mono.empty()` | Return empty, do not log ERROR |
| Lookup 0 rows, **must exist** | `EmptyResultDataAccessException` if API requires exactly one; or service throws `NotFound` | Translate to a clear domain error, usually HTTP 404 at the HTTP layer |
| Lookup >1 row under 0..1 contract | `IncorrectResultSizeDataAccessException` | Report invariant/contract error, investigate data and uniqueness |
| Duplicate key on write | `DuplicateKeyException`/`DataIntegrityViolationException` depending on driver/translator | Translate to domain conflict **only when** the matching business constraint is identified |
| FK, NOT NULL, CHECK violation | `DataIntegrityViolationException` or related exception | Fix input data/logic; do not blindly map all of them to 409 |
| Optimistic locking conflict | `OptimisticLockingFailureException` or JPA subtype | Return conflict/stale update, or bounded retry when safe |
| Timeout, deadlock, lock acquisition failure | Timeout/lock exceptions, potentially transient | Evaluate retry with backoff and limits; verify idempotency |
| DB unreachable, pool exhausted | Data access resource/connection failure | Log/monitor, optionally return 503 per API policy; never return empty |
| Invalid SQL / missing column / bad mapping | Bad SQL grammar / type conversion / mapping errors | Programming/configuration bug; fix root cause, do not auto-retry |
| Unexpected NULL column | Mapping failure, NPE, or type mismatch | Check schema/null contract; never turn into not-found |

**No data** and **SQL failure** must emit distinct signals in logs, metrics, and APIs. Putting `catch (DataAccessException)` on every repository method to return a default value defeats Spring's exception translation.

### Retry Rules

- Retry only when an error is genuinely **transient** and the operation is safe to repeat; avoid retrying all `DataAccessException`s indiscriminately.
- Read-only queries are usually safer to retry than side-effecting writes, though timeouts can happen **after the DB has already committed a write** before the client receives acknowledgment.
- For writes, use idempotency keys, unique request IDs, state/version checks, or an outbox mechanism when needed.
- Retries must have **max attempt limits, exponential backoff/jitter**, an overall deadline, and metrics; avoid infinite retry loops when the DB is under resource exhaustion.
- A rolled-back transaction must be restarted cleanly on retry; never "resume a failed transaction".
- Do not retry `DuplicateKeyException` or `IncorrectResultSizeDataAccessException` by default: they usually indicate business/invariant errors rather than random noise.

## 11. Separating Domain Errors, Infrastructure Errors, and HTTP Errors

A typical system has three boundaries:

```text
Database / JDBC / JPA / R2DBC
    ↓ 0/1/N result or DataAccessException
Repository (accesses and maps, preserves cardinality)
    ↓ Optional/List/Page/Mono/Flux or error
Service / use case (require / allow absence; resolve conflict)
    ↓ domain result or domain exception
HTTP controller + @RestControllerAdvice (maps to status/body)
```

Spring MVC 6.x example with `ProblemDetail`:

```java
// OrderApiErrors.java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderApiErrors {
    @ExceptionHandler(OrderNotFoundException.class)
    public ProblemDetail notFound(OrderNotFoundException ignored) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("No order matches the requested code.");
        return problem;
    }
}
```

This maps **one domain error type**. Production systems typically also map validation, conflict, access denied, and infrastructure errors at the common HTTP layer. Never return `SQLException` messages, connection URLs, internal table names, stack traces, or sensitive data to clients. Record detailed errors in secure logs with trace/correlation IDs, and return stable problem codes to clients.

### Suggested API Contract

| Operation | Outcome | Common HTTP status |
|---|---|---|
| `GET /orders/{code}` | One order exists | `200` + DTO |
| `GET /orders/{code}` | Not found | `404` + problem detail |
| `GET /customers/{id}/orders` | No orders | `200` + `[]` or empty page |
| `POST /orders` | Created successfully | `201` + location/body per contract |
| `POST /orders` | Duplicate order code violating business unique constraint | `409` if conflict is confirmed |
| `PATCH /orders/{id}` | Version/state changed concurrently | `409` or `412` when using standard HTTP conditional requests |
| Any endpoint | Invalid client parameters | `400` / validation response |
| Any endpoint | DB failure, lost connection | `5xx`/`503` depending on policy and error nature |

HTTP status codes are boundary decisions, not automatic properties of every `DataAccessException`. For instance, "order not found" may also depend on authorization; an API might intentionally return 404 instead of 403 per security policy. Never let the repository decide HTTP status codes.

## 12. Write Operations: Affected Row Count Is a Critical Result

Consider an update command targeting at most one order:

```java
// Method in a JDBC repository with JdbcClient jdbc.
public boolean updateTotalIfUnchanged(
        long id, long expectedTotal, long nextTotal) {
    int count = jdbc.sql("""
            UPDATE order_records
            SET total_cents = :nextTotal
            WHERE id = :id AND total_cents = :expectedTotal
            """)
        .param("nextTotal", nextTotal)
        .param("id", id)
        .param("expectedTotal", expectedTotal)
        .update();

    if (count > 1) {
        throw new IllegalStateException(
            "Expected at most one updated order");
    }
    return count == 1;
}
```

This is an **illustrative method in a class with a `jdbc` field**; validate `nextTotal >= 0` in the application layer, while DB `CHECK` also enforces the constraint. The boolean contract only tells you **whether the command modified exactly one row**. If `false`, it does not prove the row was deleted; the row may hold a different value. If business logic needs classification, design explicit outcomes such as `UPDATED`, `NOT_FOUND`, `STALE_VERSION`, and avoid introducing a new race when re-querying.

Use `@Version` (JPA) or a version column with `WHERE version = :expectedVersion` to detect stale writes. When calling two commands in one use case, place the transaction on the service and test rollback on failure; never assume two repository calls share a transaction without configuration. With reactive stacks, transactions attach to the Reactor context; do not mix JDBC and R2DBC and assume they share one ACID transaction.

**For duplicate unique-key inserts:** avoid the "check if exists, then insert" strategy as a uniqueness guarantee; there is a race between the two steps. Keep the unique constraint in the DB and handle conflict errors intentionally. PostgreSQL offers `INSERT ... ON CONFLICT ...` for upserts when business logic truly requires upsert; upsert behavior must be an explicit contract, not a surprise fallback.

## 13. Never "Swallow Errors" with Optional, Empty Lists, or Reactive Fallbacks

Recognize these anti-patterns:

```java
// WRONG: infrastructure failure or query bug is hidden as an empty list.
try {
    return jdbcReader.findRecentByCustomer(customerId, 50);
} catch (RuntimeException ex) {
    return java.util.List.of();
}
```

```java
// WRONG in a reactive service: any error becomes "not found".
return reactiveReader.findByExternalCode(code)
    .onErrorResume(ex -> Mono.empty());
```

These snippets are **anti-example code** in a service with the corresponding dependencies. Consequences: monitoring reports false success, caches may store empty results, and the UI cannot tell a DB outage from an account that has never placed an order.

**When is fallback allowed?** Only when requirements permit alternate data and an explicit policy exists, such as a read model backed by a cache with published freshness/expiry guarantees. You must:
- Fall back only on designated error classes; never fall back on constraint, authorization, or mapping bugs.
- Emit logs, a "degraded" metric, traces, and cache data timestamps; never label fallback data as fresh data.
- Never let a fallback turn a failed update into "updated".
- Test the case where both primary and fallback fail.

## 14. Lessons on "Single-Row" Queries: Verifying Data Quality from the Database

If `external_code` must be unique, the design needs at least:
- A `NOT NULL` column if missing codes are disallowed.
- A `UNIQUE` constraint in schema/migrations. On certain DBs, uniqueness with NULLs has special semantics; verify if NULL is allowed.
- Queries matching the full uniqueness scope. For instance, in a multi-tenant system with `UNIQUE(tenant_id, external_code)`, the method must pass **tenant id**; querying solely by `external_code` could legitimately return N records across tenants.
- Tests with two concurrent transactions creating the same code: one succeeds, the other gets a unique violation; response and retry behavior must be clear.
- Never using `DISTINCT` or `LIMIT 1` to hide a JOIN bug that duplicates rows. If a JOIN is legitimately many-to-one, the projection/aggregate must clearly define the result unit.

One row is not the same as one *logical entity*: SQL can produce multiple rows for the same entity when joining a one-to-many relationship. Ask "cardinality of the **entity** or of the **SQL row**?" before choosing a single-result API. Under different projections, the same order can appear across multiple rows; do not infer uniqueness from an id column in a projection alone.

## 15. Contract Testing for Required Scenarios

### Minimum Test Matrix

| Input/database state | Expected repository | Expected service/API |
|---|---|---|
| Order code does not exist | `Optional.empty()` / `Mono.empty()` | Normal for optional lookup; require → 404/domain NotFound |
| Search for customer with no orders | Empty `List` / empty-completing `Flux` | `200` + `[]` or empty page |
| Exactly one order for code | One `OrderView` | `200` + DTO |
| Two rows matching a **uniqueness-guaranteed** query | Cardinality exception | Alert/invariant error; never silently pick first row |
| 1,000 orders with limit 20 | At most 20, stable sort | Matching metadata/cursor, never return all |
| `COUNT(*)` with no matching rows | `0` (one aggregate row) | Valid `0` |
| DB disconnected / timeout | Infrastructure error | 5xx/503 per policy, metrics and trace, never 404/`[]` |
| Duplicate unique key on insert | Constraint error | Domain conflict if constraint clearly identified |
| Update with stale expected version | 0 affected rows or optimistic locking exception | Conflict/stale state per contract |
| Wrong SQL mapping / unexpected NULL | Technical error | Log and fix schema/mapping, never return empty |

### Pure Java 17 Test to Understand Cardinality

The snippet below is **standalone** and needs no Spring; it illustrates the 0..1 vs. 0..N principle. File name `CardinalityDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class CardinalityDemo {
    static <T> Optional<T> atMostOne(List<T> rows) {
        if (rows.size() > 1) {
            throw new IllegalStateException(
                "Expected at most one result");
        }
        return rows.stream().findFirst();
    }

    public static void main(String[] args) {
        System.out.println(atMostOne(List.<String>of()));
        System.out.println(atMostOne(List.of("ORD-1")));
        try {
            atMostOne(List.of("ORD-1", "ORD-2"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac CardinalityDemo.java
java CardinalityDemo
```

Exact stdout:

```text
Optional.empty
Optional[ORD-1]
Expected at most one result
```

Never interpret the exception thrown on the last line as "empty data". Spring uses different APIs/exceptions, yet the **cardinality contract** is identical.

### Required Integration Tests

- Run tests against a production-matched real DB (e.g., PostgreSQL via Testcontainers), since H2 does not always accurately simulate constraints, isolation, locking, nulls, and SQL dialects.
- For JDBC, test `optional()/single()/list()` and ensure query failures are not swallowed.
- For JPA, test `Optional`, natural-key queries, projections, paging/slicing, SQL counts, and query counts when loading associations.
- For R2DBC, use `StepVerifier` to verify empty, element, and error signals. For `Flux`, verify resource cleanup/cancellation and error behavior after prior emissions.
- For transactions, test rollbacks and two contending concurrent requests, versions/constraints. For HTTP, test 404, 409, and 5xx mappings without leaking DB details.
- For large result sets, measure memory, p95/p99, connection pool usage, query plans, and actual row counts. Never use sensitive production data as test fixtures.

## 16. Checklist Before Creating a Repository Method

- [ ] I have defined cardinality: `0..1`, `exactly 1`, `0..N`, or update count.
- [ ] I have documented whether absence is a normal outcome or a business error at the use case.
- [ ] If uniqueness is expected, `UNIQUE`/`PRIMARY KEY` or a clear logical reason exists; the query includes the full uniqueness scope.
- [ ] If multiple records are valid, the method returns a collection/reactive sequence with bounds and stable ordering.
- [ ] If datasets are large, page/slice/cursor and index/query plans exist; results are not all buffered into memory.
- [ ] I distinguish zero rows from SQL NULL and from `COUNT(*) = 0`.
- [ ] I do not unconditionally turn `DataAccessException`/`onError` into `null`, `[]`, `Optional.empty()`, or `Mono.empty()`.
- [ ] I have defined how to handle constraints, optimistic conflicts, timeouts, connection failures, and safe retries.
- [ ] The HTTP layer returns stable status/body; logs do not expose SQL, credentials, or sensitive data.
- [ ] Tests cover 0, 1, >1, large datasets, DB failures, rollback/concurrency, and API responses.

## 17. Core Takeaways

**Empty data** is normal only when the contract permits it; for use cases requiring a resource, translate absence into a domain error. **Multiple results** are normal when a query declares 0..N, yet an **error** when the query promises 0..1; large result sets require limit/pagination policies. **Execution failures** such as lost connections, invalid SQL, timeouts, or constraint violations must retain distinct signals for services/APIs to handle properly rather than being replaced by empty results.

Java/Spring tools express the same idea through different return types: `Optional/List`, `Page/Slice`, `Mono/Flux`, and `DataAccessException`. What matters most is not picking a "convenient" API, but **defining the contract and verifying every single case**.

## References

- Spring Framework — JDBC Core and JdbcClient: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — R2DBC DatabaseClient: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Data Commons — Query Return Types: https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html
- Spring Data Commons — Scrolling: https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html
- Spring Data JPA — Repository Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Framework — Error Responses and ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html

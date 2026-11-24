# UNIQUE or CHECK Constraints to Protect Invariants

## 1. The problem: checking in Java is insufficient when multiple transactions run concurrently

In a Spring application, you might write:

```java
if (!bookingRepository.existsByEventCodeAndSeatCode(event, seat)) {
    bookingRepository.save(new Booking(event, seat, customer));
}
```

This is an **illustrative snippet**, not a standalone compilable class. It appears to enforce the rule "each seat in an event can only be sold once." Yet when two requests run concurrently, both can see the seat as available before either writes:

```text
Time         Transaction T1                    Transaction T2
-----------------------------------------------------------------
t1           SELECT ... -> no booking yet
t2                                             SELECT ... -> no booking yet
t3           INSERT(event=E, seat=A1)
t4                                             INSERT(event=E, seat=A1)
t5           COMMIT                            COMMIT (if DB lacks UNIQUE)

Wrong result: two records for the same seat.
```

`@Transactional` does not automatically turn a **SELECT → INSERT** pair into an exclusive check. Under typical `READ_COMMITTED` isolation, both transactions can read the same "does not exist yet" state. Even checking twice in application code does not resolve the race without proper synchronization.

**Database-level protection:**

```sql
CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
```

Then the DB is responsible for preventing two **committed** rows from violating that unique key. One transaction may have to wait for the other; ultimately only one valid outcome commits, and the other receives a uniqueness error or fails to complete per DB mechanics. **Do not rely on thread win/loss ordering.**

Another invariant: "remaining quantity is non-negative and does not exceed total quantity" requires:

```sql
CONSTRAINT ck_stock_bounds
CHECK (total_units >= 0
   AND available_units >= 0
   AND available_units <= total_units)
```

`CHECK` prevents a row from transitioning into an invalid state **when the DB evaluates the constraint**. When multiple transactions deduct inventory concurrently, combine this with an **atomic conditional UPDATE**, rather than checking only in Java:

```sql
UPDATE inventory
SET available_units = available_units - :amount
WHERE sku = :sku
  AND available_units >= :amount;
```

This is conceptual SQL using named parameters; a complete executable JDBC example uses `?` placeholders. Check the updated row count: `1` means the operation was written in the transaction, `0` means the condition failed or the row was not found. Finally, the transaction must commit successfully for the result to be durable.

### Key takeaways

- **`UNIQUE`:** protects **uniqueness** of a business key at the database level, even when two requests contend.
- **`CHECK`:** protects the **domain/state of a single row** for conditions expressible in the DB.
- **Guarded/conditional `UPDATE`:** atomically protects updates that depend on the current value, such as preventing overselling.
- **`@Transactional`:** establishes commit/rollback boundaries, not a replacement for constraints or proper update algorithms.
- **Validation in Java:** remains useful for friendly error messages and avoiding unnecessary round trips, but is **not the final line of defense** for invariants under concurrency.

This lesson belongs to **Locking and Concurrency → Unique or Check Constraints to Protect Invariants**, focusing on the intersection of database integrity constraints, transaction isolation, Spring JDBC/JPA, and race conditions.

## 2. What is an "invariant" and which layer should enforce it?

An **invariant** is a condition that must always hold true for accepted data states. Examples:

| Business invariant | Characteristics | Appropriate database mechanism |
| --- | --- | --- |
| At most one booking per `(event_code, seat_code)` | Cross-row uniqueness | `UNIQUE(event_code, seat_code)` |
| Each request ID within a tenant creates at most one command | Cross-row uniqueness | `UNIQUE(tenant_id, request_id)` |
| `available_units >= 0` | Single row | `CHECK` + guarded `UPDATE` when deducting stock |
| `available_units <= total_units` | Same-row column relationship | `CHECK` |
| `price >= 0` and non-NULL | Single row | `NOT NULL` + `CHECK` |
| Order must reference an existing customer | Cross-table reference | `FOREIGN KEY` |
| Total bookings across multiple rows do not exceed capacity | Aggregate/cross-row | Atomically updated counter row, locking, or suitable isolation |
| No two booking time intervals overlap | Cross-row interval overlap | Exclusion constraint (if DB supports it), locking, or dedicated design |

Not every invariant can be written with `UNIQUE`/`CHECK`. If a condition depends on an aggregate across multiple rows, a simple `CHECK` is usually **not** the right tool. Databases such as PostgreSQL do not support `CHECK` constraints directly referencing other rows to guarantee a consistent invariant; use tools meant for cross-row constraints or an appropriate transaction protocol.

### 2.1. Application and database rules complement each other

In a Spring service, validation can immediately reject `amount <= 0`, return a clear HTTP error, or indicate a held seat. Yet after validation, the **database constraint must remain the final arbiter**.

```text
HTTP / message input
  -> validation: syntax, input bounds, friendly feedback
  -> Spring transactional service: coordinate business steps
  -> guarded SQL / locking: atomic updates when needed
  -> UNIQUE / CHECK / FK: reject invalid state
  -> COMMIT: DB decides durable outcome
  -> response/event: reflect actually completed result
```

Avoid treating out-of-transaction validation or an `existsBy...` call as having "locked" the data.

## 3. UNIQUE: right business key and right scope

### 3.1. Single-column, composite unique, and primary key

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE bookings (
    booking_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_code VARCHAR(40) NOT NULL,
    seat_code VARCHAR(20) NOT NULL,
    customer_code VARCHAR(80) NOT NULL,
    CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
);
```

`PRIMARY KEY` identifies the row and requires unique + not null. `UNIQUE` can apply to one or more other columns. With `uq_event_seat`, two different events can both use seat code `A1`; only the `(event_code, seat_code)` pair must be unique.

**Wrong scope:**

```sql
UNIQUE (seat_code)
```

If multiple events have seat `A1`, the constraint above over-restricts.

**Right scope:**

```sql
UNIQUE (event_code, seat_code)
```

In multi-tenant applications, `tenant_id` is sometimes added to the key, but only when the business invariant is truly partitioned by tenant. Do not blindly add tenant to a constraint if the key is global.

### 3.2. How does UNIQUE behave on two concurrent INSERTs?

A transactional database with proper uniqueness enforcement must not allow two transactions to **both commit two rows** violating a unique key. On collision, details depend on engine and isolation:

1. The first transaction may insert the key.
2. The second transaction tries to insert the same key.
3. The DB may block the second transaction waiting for the first transaction's commit/rollback outcome.
4. If the first transaction commits, the second insert is rejected for uniqueness; if the first transaction rolls back, the second transaction can proceed.
5. In the Spring application, a SQL error is translated into `DataIntegrityViolationException`/`DuplicateKeyException` or a corresponding error depending on driver/translator, and the current transaction must be completed appropriately.

Do not assume the error always appears right at `repository.save(...)`, because with JPA/Hibernate, the SQL INSERT may be deferred until `flush`/commit. With Spring JDBC, `JdbcTemplate.update(...)` executes the statement immediately and errors usually surface on the update call.

### 3.3. UNIQUE and NULL are a common trap

In many databases, two rows containing `NULL` in a unique column **are not treated as duplicates** under default semantics. PostgreSQL offers the `NULLS NOT DISTINCT` option on supporting versions; H2 defaults to `NULLS DISTINCT` in standard mode.

Therefore, if a business key **must have a value**, add `NOT NULL` **together with** `UNIQUE`. Do not write:

```sql
email VARCHAR(255),
UNIQUE (email)
```

and infer "there cannot be multiple customers without an email" across every DB. If email is allowed to be NULL, the business requirement must specify the difference between "email unknown" and "one unique email."

### 3.4. Key normalization: case, Unicode, whitespace

`UNIQUE(email)` does not mean the DB treats `"A@EXAMPLE.COM"` and `"a@example.com"` identically under every collation. Similarly, `"alice"` and `" alice "`, different Unicode canonical forms, or differently normalized strings can behave differently.

Define **normalization rules** for business keys before storing:

- Normalize email/user IDs per contract (careful not to break domain semantics).
- Use a generated/normalized key column or DB-supported functional index if appropriate.
- Test actual collation, case-sensitivity, and Unicode/diacritics.
- Do not use `toLowerCase()` in Java as a substitute for a "unique constraint": two requests can still race.

### 3.5. Soft delete and uniqueness "only on active rows"

If business rules allow multiple historical rows but only one active version, `UNIQUE(customer_id)` may be too strict. A DB supporting **partial unique indexes** like PostgreSQL can use:

```sql
-- PostgreSQL-specific, NOT general H2 syntax.
CREATE UNIQUE INDEX uq_active_customer
ON subscriptions (customer_id)
WHERE deleted_at IS NULL;
```

This index restricts uniqueness to rows matching the predicate. Examine soft-delete semantics, how `deleted_at` is updated in transactions, and concurrent transactions activating/restoring the same logical key. Do not rely solely on an application-side `WHERE deleted_at IS NULL` check.

## 4. CHECK: preventing a row from entering an invalid state

### 4.1. CHECK evaluates a Boolean expression on a row

```sql
CREATE TABLE inventory (
    sku VARCHAR(40) PRIMARY KEY,
    total_units INT NOT NULL,
    available_units INT NOT NULL,
    CONSTRAINT ck_stock_bounds CHECK (
        total_units >= 0
        AND available_units >= 0
        AND available_units <= total_units
    )
);
```

States:

| `total_units` | `available_units` | Constraint |
| ---: | ---: | --- |
| 10 | 10 | Valid |
| 10 | 0 | Valid |
| 10 | 6 | Valid |
| 10 | -1 | Rejected |
| 10 | 11 | Rejected |
| -5 | 0 | Rejected |
| 0 | 0 | Valid |

SQL `CHECK` is evaluated in the database on insert/update per engine/constraint rules. It blocks invalid data regardless of whether the source is a Spring API, batch job, migration script, admin SQL, another consumer, or code in another language.

### 4.2. CHECK does not implicitly forbid NULL

SQL uses three-valued logic: `TRUE`, `FALSE`, `UNKNOWN`. When an operand is `NULL`, many expressions evaluate to `UNKNOWN`; `CHECK` generally rejects only when the result is **`FALSE`**, not `UNKNOWN`.

Example:

```sql
-- Wrong if business requires price to always be present:
price DECIMAL(12, 2) CHECK (price >= 0)

-- Clearer:
price DECIMAL(12, 2) NOT NULL
    CHECK (price >= 0)
```

H2 documentation states CHECK accepts `TRUE` or `UNKNOWN`. PostgreSQL applies the same rule. That is why in the runnable schema, both `total_units` and `available_units` have `NOT NULL`.

### 4.3. CHECK is usually suited for invariants intrinsic to one row

`CHECK (available_units <= total_units)` works because both columns belong to the same row. However, the following requirements cannot be solved by a simple row-level CHECK:

- Total seats booked across **multiple rows** must not exceed capacity.
- Each customer can have at most three in-progress orders across multiple rows.
- Total ledger debits must equal total credits across multiple transactions.
- Two room-booking time ranges in separate rows must not overlap.

For such conditions, you need a different schema (for example an atomically updated counter row), `UNIQUE`/`FOREIGN KEY`/exclusion constraints, locking, serializable isolation with retries, or an appropriate business workflow. Triggers also require careful concurrency design; a naive trigger that SELECTs then inserts can still race without proper locking/isolation.

### 4.4. CHECK does not fix "lost updates"

Two transactions can both read `available_units = 5` and each write `available_units = 4`. The row still satisfies CHECK, yet the DB recorded **one decrement** instead of two. This is a **lost update**, not directly a CHECK violation.

```text
T1 reads 5  ─── computes 4 ─── UPDATE available=4
T2 reads 5  ─── computes 4 ─── UPDATE available=4
Result may remain 4 even though two reservations occurred.
```

Fix with an atomic arithmetic update or proper locking/optimistic versioning:

```sql
UPDATE inventory
SET available_units = available_units - 1
WHERE sku = 'SKU-1'
  AND available_units >= 1;
```

The DB executes the statement on the row under its transaction/locking rules. When two requests contend for the last unit, only one UPDATE can succeed; the other receives affected row count `0` or a retryable error depending on engine/isolation, rather than writing -1.

`CHECK` remains an additional line of defense if other code tries writing `-1` directly. **The right model combines guarded statements + constraints + transaction boundaries**, not picking one of the three.

## 5. How do Spring transactions handle constraint violations?

### 5.1. Spring JDBC and `DataIntegrityViolationException`

With `JdbcTemplate`, Spring translates JDBC `SQLException`s into the `DataAccessException` hierarchy. `DataIntegrityViolationException` covers data integrity violations; `DuplicateKeyException` is a specific subclass of it.

```java
@Transactional
public void book(String event, String seat, String customer) {
    jdbc.update(
        "INSERT INTO bookings(event_code, seat_code, customer_code) " +
        "VALUES (?, ?, ?)",
        event, seat, customer);
}
```

This snippet needs a `JdbcTemplate jdbc` field and a Spring-managed bean. If uniqueness is violated during the JDBC update, Spring usually throws `DataIntegrityViolationException` or a subclass; because it is a **runtime exception**, `@Transactional`'s default rollback rules request a rollback.

**Do not infer that every `DataIntegrityViolationException` is a duplicate.** It could be a CHECK, NOT NULL, FOREIGN KEY, or another constraint. At the application boundary, distinguish via reliable constraint name/vendor code/SQLState per project adapter standards, avoiding turning unexpected integrity errors into "seat already sold."

### 5.2. Where `catch` is placed matters greatly

Do not write:

```java
@Transactional
public void unsafeFlow() {
    try {
        jdbc.update("INSERT INTO bookings (...) VALUES (...)");
    } catch (DataIntegrityViolationException ignored) {
        // Wrong if treated as recovering the transaction after a SQL error.
    }
    // continue SQL and hope to commit ...
}
```

This is **pseudo-code** with invalid `...` SQL placeholders. On some DBs (such as PostgreSQL), a SQL error puts the current transaction into an aborted state until rollback; in some ORM stacks, the persistence context is also no longer safe to continue using. Catching right inside the transaction can make the interceptor see a normal return, causing commit failure/rollback-only to surface late.

If the goal is returning "seat already booked," usually let the transactional method throw, let the transaction manager complete the rollback, and **catch and map the exception outside the transaction boundary** (in a controller/facade no longer in the same transaction), or use proper database-specific upsert semantics.

```text
Controller / command adapter
   |
   +-- try bookingService.book(...)  // proxy boundary
           -> JDBC INSERT
           -> DB UNIQUE rejects
           -> Spring translates exception
           -> interceptor rolls back
   |
   +-- catch DataIntegrityViolationException
           -> classify known uq_event_seat
           -> return 409 Conflict / domain result
```

When an existing transaction already wraps the controller/facade, "outside the service method" is not necessarily outside the **physical transaction**. Locate the final transaction owner and do not continue writing inside a failed transaction.

### 5.3. JPA can throw late at flush/commit

In Spring Data JPA, calling `repository.save(...)` does not necessarily emit SQL immediately. Hibernate may only INSERT/UPDATE at `flush` or commit. Consequently:

- `save()` returning does not guarantee uniqueness was confirmed by the DB.
- `saveAndFlush()`/`entityManager.flush()` pushes SQL earlier, helping detect some errors before the method returns, yet is **not a commit** and does not catch all commit-time errors.
- Databases supporting deferred constraints can check at commit even after flushing.
- Exceptions may be translated into `DataIntegrityViolationException` via Spring persistence exception translation, though an exact subclass cannot be promised across every provider/version.
- After a Hibernate/JPA persistence failure, do not assume `EntityManager` remains safe to reuse in the same transaction.

The hands-on project uses **Spring JDBC** so statement and error timing are easy to observe; the uniqueness/check principles apply at the DB regardless of JDBC or JPA access.

### 5.4. One successful SQL statement is not yet a commit

`JdbcTemplate.update` returns affected rows inside the transaction; the application still needs `@Transactional` to complete. If commit hits a deadlock, timeout, connection failure, or rollback-only status from elsewhere, the caller may not receive a successful outcome. For operations with important side effects, use business keys/idempotency and reconciliation before retrying.

### 5.5. Constraint names, SQLState, and portability

For example in H2:

- Unique violations typically carry error code/SQLState `23505`.
- CHECK violations use error code `23513` in H2.
- NOT NULL violations are `23502`.

These values are **not fixed standards across every database**; for instance, PostgreSQL CHECK violations use SQLSTATE `23514`. When domain error mapping is needed, isolate reading `SQLException`/constraint names in a persistence adapter, log safely, and maintain integration tests for the production engine. Do not hardcode H2 SQLStates and reuse them verbatim on PostgreSQL/MySQL/Oracle.

## 6. Runnable project: UNIQUE, CHECK, race test, and atomic UPDATE

We create a Spring Boot project using a real H2 datasource with a JDBC transaction manager. The integration tests prove:

1. UNIQUE is scoped to `(event_code, seat_code)`, not global `seat_code`.
2. Duplicate bookings are rejected by the DB, even when both transactions prechecked and saw the seat free.
3. CHECK prevents negative stock / stock exceeding total; NOT NULL forbids NULL state.
4. A constraint failure in a transaction rolls back valid statements executed earlier in it.
5. Guarded UPDATE does not oversell remaining units within one or multiple transactions.
6. Outcomes are verified via SQL **after the service proxy completes**, not merely by exceptions or logs.

### 6.1. Project structure and environment

```text
db-invariants/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/invariants/
    │   │   ├── InvariantsApplication.java
    │   │   ├── BookingService.java
    │   │   └── InventoryService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/invariants/
        └── DatabaseInvariantIntegrationTest.java
```

Use **Java 17+**, a compatible Gradle version, and Spring Boot 3.3.5 with Spring JDBC + H2 + JUnit 5. If using Spring Initializr, you can generate the Gradle Wrapper alongside the project; if creating manually, you need a compatible Gradle installation to run or generate the wrapper. Spring code cannot compile with bare `javac` without dependency classpaths.

`settings.gradle`:

```groovy
rootProject.name = 'db-invariants'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management aligns Spring/JUnit/H2 versions compatible with the Boot version in the example. Ensure Gradle/JDK meet plugin requirements.

### 6.2. DataSource and schema

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:invariants;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`LOCK_TIMEOUT=10000` is an H2 setting for the concurrency test, not a portable isolation configuration. Pool size 5 is sufficient for two concurrent transactions in the fixture. Do not use H2 results to guarantee locking/timing behavior on PostgreSQL or MySQL without re-testing.

`src/main/resources/schema.sql`:

```sql
CREATE TABLE bookings (
    booking_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_code VARCHAR(40) NOT NULL,
    seat_code VARCHAR(20) NOT NULL,
    customer_code VARCHAR(80) NOT NULL,
    CONSTRAINT uq_event_seat UNIQUE (event_code, seat_code)
);

CREATE TABLE inventory (
    sku VARCHAR(40) PRIMARY KEY,
    total_units INT NOT NULL,
    available_units INT NOT NULL,
    CONSTRAINT ck_stock_bounds CHECK (
        total_units >= 0
        AND available_units >= 0
        AND available_units <= total_units
    )
);
```

The schema creates **two invariants** enforced at the DB:

- `uq_event_seat`: no two bookings may share the same event+seat.
- `ck_stock_bounds`: total units non-negative, available between 0 and total (with NOT NULL on the relevant columns).

Naming constraints helps explain errors, migrate schemas, and map domain errors consistently compared to relying on auto-generated names.

### 6.3. Spring Boot application and transaction manager

`src/main/java/com/example/invariants/InvariantsApplication.java`:

```java
package com.example.invariants;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class InvariantsApplication {
    public static void main(String[] args) {
        SpringApplication.run(InvariantsApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

There is only **one** local JDBC transaction manager bean so all services share the same datasource. `DataSourceTransactionManager` and `JdbcTemplate` coordinate the Spring transaction-bound JDBC connection. The H2 database is initialized via `schema.sql` before tests run.

### 6.4. BookingService: one normal method and one intentional precheck race

`src/main/java/com/example/invariants/BookingService.java`:

```java
package com.example.invariants;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
    private final JdbcTemplate jdbc;

    public BookingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void book(String event, String seat, String customer) {
        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            event, seat, customer);
    }

    @Transactional
    public void bookAfterBothSawEmpty(
            String event,
            String seat,
            String customer,
            CountDownLatch ready,
            CountDownLatch release) {

        Integer existing = jdbc.queryForObject(
            "SELECT COUNT(*) FROM bookings " +
            "WHERE event_code = ? AND seat_code = ?",
            Integer.class, event, seat);

        if (existing == null || existing != 0) {
            throw new IllegalStateException(
                "Test precondition: seat already booked");
        }

        // To trigger an intentional race: each transaction SELECTed empty
        // before either transaction is allowed to INSERT.
        ready.countDown();
        try {
            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }

        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            event, seat, customer);
    }

    @Transactional
    public void bookThenBreakStockCheck() {
        jdbc.update(
            "INSERT INTO bookings(event_code, seat_code, customer_code) " +
            "VALUES (?, ?, ?)",
            "FAILED_TX", "Z9", "alice");

        jdbc.update(
            "UPDATE inventory SET available_units = -1 WHERE sku = ?",
            "SKU-1");
    }
}
```

`bookAfterBothSawEmpty` is designed to be **intentionally wrong if UNIQUE were removed**: both threads SELECT `COUNT=0`, then the barrier opens for both to INSERT competitively. This is not a business flow for production; in production, attempt the INSERT atomically and handle constraint violations.

`bookThenBreakStockCheck` demonstrates a constraint failure occurring after a valid INSERT **in the same transaction**, and because the runtime exception escapes the transactional proxy, Spring rolls back the entire transaction. In the H2 demo, CHECK fails right at `JdbcTemplate.update`, without waiting for commit.

### 6.5. InventoryService: guarded UPDATE alongside CHECK

`src/main/java/com/example/invariants/InventoryService.java`:

```java
package com.example.invariants;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final JdbcTemplate jdbc;

    public InventoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean reserve(String sku, int units) {
        if (units <= 0) {
            throw new IllegalArgumentException("units must be positive");
        }

        int changed = jdbc.update(
            "UPDATE inventory " +
            "SET available_units = available_units - ? " +
            "WHERE sku = ? AND available_units >= ?",
            units, sku, units);

        // 1: update executed inside this transaction.
        // 0: SKU missing or insufficient available units.
        // Caller receives the boolean after the transaction advice finishes.
        return changed == 1;
    }
}
```

Because `sku` is the primary key, an UPDATE targets at most one row. `changed==1` must not be interpreted as "durably committed" while code is still **inside** the transactional method. For an **external call through the proxy**, transaction advice performs completion before returning success to the caller. If the caller already has an outer `REQUIRED` transaction, physical commit still waits on the outer transaction owner.

The `available_units >= units` condition is evaluated inside the UPDATE itself. Concurrent transactions updating the same row must coordinate engine locking/visibility, yielding a different outcome from an application-level SELECT precheck. `CHECK` still protects if other code writes an invalid value directly, and `units > 0` prevents negative/zero inputs from skewing semantics.

### 6.6. Integration test: nine scenarios

`src/test/java/com/example/invariants/DatabaseInvariantIntegrationTest.java`:

```java
package com.example.invariants;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class DatabaseInvariantIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private BookingService booking;

    @Autowired
    private InventoryService inventory;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM bookings");
        jdbc.update("DELETE FROM inventory");
        jdbc.update(
            "INSERT INTO inventory(sku, total_units, available_units) " +
            "VALUES (?, ?, ?)",
            "SKU-1", 2, 2);
    }

    private long bookingCount() {
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM bookings", Long.class);
        return count;
    }

    private int available() {
        Integer count = jdbc.queryForObject(
            "SELECT available_units FROM inventory WHERE sku = ?",
            Integer.class, "SKU-1");
        return count;
    }

    @Test
    void uniqueIsScopedToEventAndSeat() {
        booking.book("E1", "A1", "alice");
        booking.book("E2", "A1", "bob");

        assertEquals(2L, bookingCount());
    }

    @Test
    void duplicateSeatIsRejectedByUnique() {
        booking.book("E1", "A1", "alice");

        assertThrows(DataIntegrityViolationException.class,
            () -> booking.book("E1", "A1", "bob"));

        assertEquals(1L, bookingCount());
    }

    @Test
    void checkRejectsNegativeAvailableUnits() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = -1 " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void checkRejectsAvailableGreaterThanTotal() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = 3 " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void notNullClosesTheCheckUnknownGap() {
        assertThrows(DataIntegrityViolationException.class,
            () -> jdbc.update(
                "UPDATE inventory SET available_units = NULL " +
                "WHERE sku = ?", "SKU-1"));

        assertEquals(2, available());
    }

    @Test
    void constraintViolationRollsBackEarlierBookingInsert() {
        assertThrows(DataIntegrityViolationException.class,
            booking::bookThenBreakStockCheck);

        assertEquals(0L, bookingCount());
        assertEquals(2, available());
    }

    @Test
    void guardedUpdatePreventsSequentialOverselling() {
        assertTrue(inventory.reserve("SKU-1", 2));
        assertFalse(inventory.reserve("SKU-1", 1));

        assertEquals(0, available());
    }

    @Test
    void twoThreadsCannotReserveLastUnitTwice() throws Exception {
        jdbc.update(
            "UPDATE inventory SET available_units = 1 WHERE sku = ?",
            "SKU-1");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<Boolean> first = pool.submit(() -> {
                start.await();
                return inventory.reserve("SKU-1", 1);
            });
            Future<Boolean> second = pool.submit(() -> {
                start.await();
                return inventory.reserve("SKU-1", 1);
            });

            start.countDown();

            List<Boolean> results = List.of(
                first.get(15, TimeUnit.SECONDS),
                second.get(15, TimeUnit.SECONDS));

            assertEquals(1L, results.stream()
                .filter(Boolean::booleanValue).count());
            assertEquals(0, available());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    private String tryBookAfterPrecheck(
            String customer,
            CountDownLatch ready,
            CountDownLatch release) {
        try {
            booking.bookAfterBothSawEmpty(
                "CONCERT", "A1", customer, ready, release);
            return "COMMITTED";
        } catch (DataIntegrityViolationException expected) {
            return "REJECTED";
        }
    }

    @Test
    void simultaneousPrechecksCannotBypassUnique() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() ->
                tryBookAfterPrecheck("alice", ready, release));
            Future<String> second = pool.submit(() ->
                tryBookAfterPrecheck("bob", ready, release));

            // Both transactions SELECTed and saw the seat had no booking yet.
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            release.countDown();

            List<String> outcomes = List.of(
                first.get(15, TimeUnit.SECONDS),
                second.get(15, TimeUnit.SECONDS));

            assertEquals(1L, outcomes.stream()
                .filter("COMMITTED"::equals).count());
            assertEquals(1L, outcomes.stream()
                .filter("REJECTED"::equals).count());
            assertEquals(1L, bookingCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

The tests are written so they do not depend on **which thread wins**. The race test uses two separate transactions on two threads; both prechecked before being allowed to INSERT. `UNIQUE` still preserves the invariant.

**Why not put `@Transactional` on the test class?** If the test owns a transaction, `REQUIRED` services may simply join the test's transaction; querying row counts right inside the test would then **not** prove the service committed. In this fixture, the test has no transaction annotation; the service proxy completes the transaction before the caller inspects the DB.

**Concurrency fixture note:** tests run sequentially across methods by default; the two worker threads exist only within each test. `LOCK_TIMEOUT` and pool size are chosen to reduce resource-related flakiness. The scheduler does not guarantee winner order. Database engines have different lock timeout/deadlock/serialization policies than H2; if production DB test results differ, check SQLState, isolation, pool, indexes, and retry policy. Concurrency tests need finite timeouts and executor cleanup in `finally`.

### 6.7. How to run

Inside the `db-invariants` directory, with Gradle Wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project does not yet have a Gradle Wrapper, generate one with a compatible Gradle installation or run `gradle test` with a version supported by the Spring Boot plugin. Compiler and JUnit dependencies are managed by Gradle; no manual `javac` classpath setup is needed.

**Expected result:** 9 integration tests pass in the Java17/Boot3.3.5/H2 fixture per the code above, after downloading dependencies. JUnit does not guarantee test order and produces no fixed stdout. The HTML report is located at `build/reports/tests/test/index.html`. This is a **prediction from the configuration and code**, not a claim that the test suite was executed in the reader's environment.

| Verification | Expected result |
| --- | --- |
| Seat `A1` on two different events | Both bookings kept, count = 2 |
| Two bookings colliding on `E1/A1` | Second booking rejected, count = 1 |
| `available_units=-1` | CHECK rejects, value stays = 2 |
| `available_units=3 > total_units=2` | CHECK rejects, value stays = 2 |
| `available_units=NULL` | NOT NULL rejects, value stays = 2 |
| Insert booking then CHECK fails in same transaction | Whole transaction rolls back, booking count = 0 |
| Reserve 2 then reserve 1 more | First true, second false, available = 0 |
| Two threads concurrently reserve last unit | One true, one false, available = 0 |
| Two threads precheck both seeing empty seat | One commits, one rejected by unique, booking count = 1 |

**Testing distinction:** assert both the exception **and** post-boundary DB state. `assertThrows(DataIntegrityViolationException.class, ...)` alone does not suffice to prove all statements before the error rolled back; that is why the sixth test also asserts booking count equals 0.

## 7. A workflow for handling races in production

### 7.1. Booking: attempting INSERT is the source of truth

A typical flow:

1. Receive `event_code`/`seat_code` from the request and validate format.
2. If UX needs "seat is already held," query status for display, understanding that the result **may be stale**.
3. Inside a transaction, attempt to INSERT the booking with the proper unique key.
4. If insert/commit succeeds, return the created booking.
5. If the DB reports a unique conflict, **after the failed transaction finishes**, map the error to a domain result such as `SEAT_ALREADY_BOOKED`, potentially HTTP 409.
6. For other errors (CHECK/FK/DB unavailable/deadlock), do not map all of them to "seat already sold." Log with a correlation ID and classify safely.
7. When retrying, use a request idempotency key and check previously created resources.

Suppose a duplicate request was already processed successfully but the response was lost: a retry may hit the unique constraint. If the unique key is the **business resource** (seat) and the request belongs to a different customer, that is a conflict. If the unique key is an **idempotency key**, read the previous request's result and verify payload/fingerprint to decide whether to replay the prior result or return a conflict. Do not return blind success upon hitting a duplicate.

### 7.2. Inventory: conditional UPDATE alongside order placement

Suppose you both record a booking and deduct stock in one service:

```java
@Transactional
public void bookAndReserve(String event, String seat, String customer) {
    bookingService.book(event, seat, customer);
    if (!inventoryService.reserve("SKU-1", 1)) {
        throw new IllegalStateException("Not enough inventory");
    }
}
```

This snippet **illustrates structure**, requiring beans/fields `bookingService` and `inventoryService`, with the method invoked via Spring proxy. If both services use `REQUIRED` on the **same transaction manager/DataSource**, inserting the booking and deducting inventory can commit or roll back together; the runtime `IllegalStateException` thrown out of the outer method requests a rollback.

However, if booking and stock live in two different databases or one service uses `REQUIRES_NEW`, the atomicity above **is not automatically guaranteed**. Do not claim a single `@Transactional` automatically protects distributed resources/email/Kafka.

### 7.3. When multi-row invariants are needed

For example, "at most 100 uncancelled bookings per event" where bookings span multiple rows. If you use:

```sql
SELECT COUNT(*) FROM bookings WHERE event_code = 'E';
-- if count < 100 then INSERT ...
```

two transactions can both read `99` and both insert, reaching `101`. `UNIQUE(event,seat)` does not help if two bookings choose **two different seats**; a `CHECK` on each booking row does not know the event-wide count.

Proper options depend on the model:

- An `event_capacity` row maintaining `remaining` and updated with a guarded UPDATE in the same transaction as inserting the booking.
- Using a row-level pessimistic lock on a representative event row before count+insert, with all writers obeying the rule.
- Using `SERIALIZABLE` isolation with idempotent **serialization failure/retry** handling.
- Using stronger constraint forms (exclusion/trigger with locking) if supported and appropriate for the DB.

Different strategies carry different contention, deadlock, throughput, and complexity costs. Do not pick an isolation level arbitrarily and conclude it is safe from a contention-free test.

## 8. Limitations and side effects when deploying schema changes

### 8.1. Adding UNIQUE to existing data

Before adding a constraint to a production table, check for duplicates:

```sql
SELECT event_code, seat_code, COUNT(*) AS n
FROM bookings
GROUP BY event_code, seat_code
HAVING COUNT(*) > 1;
```

This SQL query works across many RDBMSs. If duplicates already exist, adding `UNIQUE` can fail; you need a migration plan to clean up data, handle active concurrent writers, create the index/constraint using the database's online DDL mechanism, and test deploy/rollback. "Created a unique index" does not automatically mean every legacy code path uses the right business key or normalization.

### 8.2. Adding CHECK to existing data

Check for invalid data:

```sql
SELECT sku, total_units, available_units
FROM inventory
WHERE total_units < 0
   OR available_units < 0
   OR available_units > total_units
   OR total_units IS NULL
   OR available_units IS NULL;
```

In the sample schema the columns are already NOT NULL; the two NULL checks are defensive when auditing legacy data with a different schema. Before migrating, agree on how to handle violating rows: fix data per business invariants rather than merely deleting rows "so adding the constraint passes."

### 8.3. Index cost, contention, and locking

A unique constraint is usually enforced by the DB via a unique index. This has write/index-maintenance overhead and can cause contention on hot keys. Yet dropping a unique index to "speed up" and locking only in application code is not a default solution: it removes protection across processes, jobs, and writers not sharing the same distributed lock.

Also avoid creating duplicate indexes. In PostgreSQL, a unique constraint already creates a corresponding unique index; inspect the index plan before creating extra manual indexes.

### 8.4. Constraint violations are not always "bad input data"

A duplicate can be:

- Two users booking the same seat, a normal business conflict.
- A retry of the same idempotent request.
- A bug generating the same key multiple times.
- A job/backfill importing duplicate data.
- Another "active" record already existing due to soft-delete semantics.
- Differences in casefolding/normalization/collation.
- Running in the wrong tenant scope.

Therefore a single generic exception is insufficient to decide HTTP status, retry, or user messaging. The persistence layer must provide constraint context; the domain layer must know which invariant failed, and the API layer then decides the response.

## 9. Comparing concurrency protection techniques

| Technique | Protects best against | Does not automatically solve |
| --- | --- | --- |
| `UNIQUE` | Committing duplicate keys | Aggregate counts, lost updates, semantic duplicates if key normalization is wrong |
| `CHECK` | Invalid row state | Conditions depending on other rows, lost updates |
| `NOT NULL` | Missing required fields | Concurrency uniqueness |
| `FOREIGN KEY` | Referential integrity | Multi-row business quotas |
| Guarded `UPDATE` | Deducting non-negative quantities within a statement | Invariants spanning independent tables |
| `SELECT ... FOR UPDATE` | Coordinating writers locking existing rows | Checking the **absence** of rows not yet present to lock across all DBs/isolations |
| Optimistic locking `@Version` | Detecting update conflicts on the same entity | Does not prevent duplicate inserts without unique |
| `SERIALIZABLE` + retry | Many cross-transaction anomalies | Does not replace all constraints/schema rules |
| `@Transactional` | Atomic commit/rollback boundary for participating resources | Does not lock the right business key if logic still has a TOCTOU race |
| Application prevalidation | UX, fast rejection | Not the final concurrency arbiter |

**TOCTOU** (time-of-check to time-of-use) is the gap between checking and using. In booking, `existsBy...` is the check and `insert` is the use. `UNIQUE` moves the final decision into the same atomic DB write path.

## 10. Self-check questions

**Question 1.** Two requests both run `SELECT COUNT(*)=0` and then `INSERT` a booking with the same event/seat pair. Does `@Transactional` automatically prevent duplicates under `READ_COMMITTED`?

**Answer:** No. You need `UNIQUE(event_code, seat_code)` (or an equivalent constraint mechanism) so the DB rejects duplicate state, even when both prechecked successfully.

**Question 2.** There is `CHECK(available_units >= 0)`. Two requests read `available=1` and both write `available=0`. Can the item be sold twice while the DB remains valid?

**Answer:** Yes, due to a lost update or an improperly updated quota invariant. Use an atomic guarded decrement on the same row or an appropriate locking/isolation strategy, plus CHECK as a safety net.

**Question 3.** Why does `CHECK(price >= 0)` not replace `NOT NULL`?

**Answer:** When price is NULL, the condition usually evaluates to UNKNOWN; CHECK does not necessarily reject it. `NOT NULL` is needed if the value is required.

**Question 4.** Is `UNIQUE(seat_code)` correct for a system with multiple events having seat A1?

**Answer:** No. The business scope is event+seat; a composite unique key is needed.

**Question 5.** If `DataIntegrityViolationException` occurs, can you always return "duplicate booking"?

**Answer:** No. The exception can also come from CHECK/NOT NULL/FK. Classify the constraint or use case properly.

**Question 6.** Why should you avoid catching a duplicate inside a `@Transactional` method and continuing with more SQL?

**Answer:** The DB or ORM transaction may already be in an aborted/rollback-only state. Catching can mask the root error and defer failure to commit; catch at a safe boundary after rollback or use a dedicated upsert with clear semantics.

**Question 7.** Does `JpaRepository.save` succeeding mean uniqueness was definitely confirmed by the DB?

**Answer:** No. JPA can defer SQL until flush/commit; even flush is not a durable commit.

**Question 8.** Two transactions both need to deduct the last unit; which SQL is safer than read-then-write?

**Answer:** An `UPDATE inventory SET available=available-1 WHERE sku=? AND available>=1`, checking the affected row count and transaction completion. CHECK prevents negative values when other code writes improperly.

**Question 9.** Can the rule "total active bookings per event <= 100" be enforced by a CHECK on each booking row?

**Answer:** Not with a standard row-level CHECK. You need an atomic counter row/locking/serializable design or database tools meant for cross-row invariants.

**Question 10.** Why shouldn't a test only use `assertThrows`?

**Answer:** An exception confirms an error path, but the final invariant must be measured after the transaction boundary via a DB query; you also need to verify that statements prior to the error rolled back.

**Question 11.** Do constraints still protect when a job outside Spring runs SQL directly?

**Answer:** Yes, if every writer actually targets that database/schema/table/constraint and the DB enforces the constraint. That is a major advantage over prevalidation living only inside a Spring service.

**Question 12.** If idempotency is needed, is catching a duplicate and always returning success enough?

**Answer:** No. You must distinguish a duplicate business conflict from the same idempotency key from the same request; read the prior outcome and verify payload/hash to return the exact right result.

## 11. Checklist for real-world deployment

1. Write invariants clearly in business language, including tenant, active state, soft delete, and normalization.
2. Choose the right DB primitive: `UNIQUE`, `CHECK`, `NOT NULL`, `FOREIGN KEY`, guarded update, or a cross-row mechanism.
3. Name constraints clearly, e.g., `uq_event_seat`, `ck_stock_bounds`.
4. Audit existing production data before migrating.
5. Design migrations accounting for concurrent writes, lock duration, and the engine's online DDL.
6. Ensure every write path (HTTP, batch, import, admin jobs) goes through the same DB invariants.
7. Keep Java validation for good UX, without treating check-before-write as a lock.
8. Verify `@Transactional` actually passes through the Spring proxy and uses the right transaction manager.
9. Catch/map errors at a boundary after the transaction finishes; classify constraints instead of swallowing all `DataIntegrityViolationException`s.
10. With JPA, verify flush/commit timing rather than just `save` returning.
11. For inventory, use conditional SQL updates and check affected rows; apply appropriate retries when the DB reports deadlocks/serialization conflicts.
12. Write race tests with barriers and timeouts, testing on a real DB or production-like DB; do not rely on a single lucky run.
13. Read the DB after the transaction boundary to verify invariants, not just exceptions/logs/first-level cache.
14. Ensure responses sent to clients reflect the committed outcome, and retries are idempotent when the outcome is uncertain.
15. Monitor unique/check violations with classified metrics without logging secrets or sensitive data.

## 12. References

- [PostgreSQL Documentation — Constraints: CHECK, NOT NULL, UNIQUE, PRIMARY KEY](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [H2 Database — SQL Grammar: CHECK/UNIQUE/NULLS DISTINCT](https://h2database.github.io/html/grammar.html)
- [H2 Database — ErrorCode: duplicate key and CHECK violation](https://h2database.github.io/javadoc/org/h2/api/ErrorCode.html)
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
- [Spring Framework — DuplicateKeyException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/dao/DuplicateKeyException.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Transactional Test Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)

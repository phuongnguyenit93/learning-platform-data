# DuplicateKeyException, DataIntegrityViolationException, and Constraint Errors in Spring Data Access

> **Scope:** Spring Framework Data Access → Data Exceptions. This lesson focuses on the two Spring exception types `DuplicateKeyException` and `DataIntegrityViolationException`, their inheritance relationship, `UNIQUE`/`PRIMARY KEY`/`FOREIGN KEY`/`NOT NULL`/`CHECK` errors, the `SQLException` translation mechanism, transactions, and proper application handling. Examples use Spring JDBC, real PostgreSQL, and Java 17+.

## 1. Understanding Both Exceptions Before Catching Errors

In plain Java JDBC, an `INSERT` or `UPDATE` that violates a constraint can throw `SQLException` or one of its subclasses. Spring's `JdbcTemplate` translates JDBC-layer errors into a unified, driver-independent exception hierarchy called `DataAccessException`.

Abbreviated inheritance tree:

```text
RuntimeException
  └─ NestedRuntimeException
       └─ DataAccessException
            └─ NonTransientDataAccessException
                 └─ DataIntegrityViolationException
                      └─ DuplicateKeyException
```

Key takeaway: **`DuplicateKeyException` is a specific form of `DataIntegrityViolationException`**.

- `DataIntegrityViolationException`: a data constraint or integrity rule was violated, such as `NOT NULL`, `FOREIGN KEY`, `CHECK`, certain unique-key errors, and other constraints. Not every SQL error belongs to this group.
- `DuplicateKeyException`: the specific case of **duplicating a primary key, unique constraint, or unique index value** when Spring recognizes the cause. It commonly occurs when creating a new record with an existing `email`, or reusing an `id` key.
- `NonTransientDataAccessException`: means **the same operation with identical data is not expected to succeed just by retrying immediately**, unlike temporary connection drops, deadlocks, or serialization conflicts. This is a technical classification; business rules may fix the data and retry.

**`catch` order trap:** always catch the more specific class first:

```java
try {
    jdbc.update("INSERT INTO account(id, email) VALUES (?, ?)",
                id, email);
} catch (DuplicateKeyException ex) {
    // Unique/primary key duplicated; may map to a business conflict.
} catch (DataIntegrityViolationException ex) {
    // Remaining data integrity violations.
}
```

If you place `catch (DataIntegrityViolationException)` before `catch (DuplicateKeyException)`, the latter block becomes **unreachable** and Java reports a compile error. Do not use `catch (DataAccessException)` for all errors and assume it means "duplicate data".

## 2. Real Constraints in the Database

| Constraint | Error-triggering data | Expectation with PostgreSQL and standard Spring JDBC setup | PostgreSQL SQLSTATE |
| --- | --- | --- | --- |
| `PRIMARY KEY` | Inserting `id=1` a second time | `DuplicateKeyException` | `23505` |
| `UNIQUE(email)` | Two records using the same `email` | `DuplicateKeyException` | `23505` |
| `FOREIGN KEY` | `purchase.customer_id` does not exist in parent table | `DataIntegrityViolationException` | `23503` |
| `NOT NULL` | `email=NULL` when column forbids NULL | `DataIntegrityViolationException` | `23502` |
| `CHECK` | `status='UNKNOWN'` when only two statuses are allowed | `DataIntegrityViolationException` | `23514` |

These codes belong to PostgreSQL's **SQLSTATE Class 23 — Integrity Constraint Violation**. `23505` is used for both primary key and unique key duplicates, so **from `DuplicateKeyException` or SQLSTATE alone you cannot tell which constraint was duplicated**. To distinguish `email` from `id`, you need the SQL statement, a reliable constraint name from the DB, or business context.

Other important constraint details:

- A column with `UNIQUE` but **without `NOT NULL`** in PostgreSQL can normally hold multiple `NULL` values, because `NULL`s are not treated as equal under a default unique constraint. If email is required, specify **both** `NOT NULL` and `UNIQUE`.
- `FOREIGN KEY` checks the existence of the referenced record; errors can occur on insert/delete/update depending on `ON DELETE`, `ON UPDATE` behavior, and constraint checking timing.
- `CHECK` evaluates only the defined expression. For example, `CHECK (amount > 0)` **does not automatically forbid NULL** in PostgreSQL; add `NOT NULL` if NULL is disallowed.
- Java validation such as `@NotNull` and `@Email` provides early feedback but **does not replace database constraints**: another process, data import, or concurrent request can still write to the DB.

## 3. From PostgreSQL Error to Spring Exception: Which Layers Does It Cross?

```text
Application calls JdbcTemplate.update(...)
          ↓
Spring prepares and executes PreparedStatement
          ↓
PostgreSQL detects UNIQUE/FK/NOT NULL/CHECK violation
          ↓
pgJDBC throws SQLException (with SQLSTATE + vendor error code)
          ↓
JdbcTemplate → SQLExceptionTranslator
          ↓
DataAccessException / DataIntegrityViolationException
                          └─ DuplicateKeyException if key duplication is recognized
          ↓
Transaction marks failure/rollback and business layer handles it
```

`SQLExceptionTranslator` is the Spring interface used to map driver errors into the `DataAccessException` hierarchy. Two common mechanisms should be distinguished:

1. **`SQLExceptionSubclassTranslator`**: the default in Spring Framework 6.x, using `SQLException` subclasses (JDBC 4) and falling back to **`SQLStateSQLExceptionTranslator`**. Thus PostgreSQL SQLSTATE `23505` is typically recognized as `DuplicateKeyException`, and other constraint codes like `23503`/`23502`/`23514` as `DataIntegrityViolationException`.
2. **`SQLErrorCodeSQLExceptionTranslator`**: translates using per-DBMS error-code tables; in Spring 6.x it is chosen automatically when a `sql-error-codes.xml` file exists at the classpath root, or can be set explicitly via `JdbcTemplate.setExceptionTranslator(...)`. Spring's PostgreSQL table maps `23505` to the duplicate group and `23502`, `23503`, `23514` to the integrity group.

Precisely because translation results depend on **driver, DBMS, SQLSTATE/vendor code, and active translator**, you should not promise that every database will always return the exact same Spring subclass. For example, MySQL uses vendor code `1062` for duplicate key; multiple DBMSs may share general SQLSTATE `23000` with different detailed codes. Verify against your real deployment configuration.

`JdbcTemplate` handles `SQLException` inside its own calls. `@Repository` and `PersistenceExceptionTranslationPostProcessor` also assist in translating certain repository/ORM-layer exceptions when the proper infrastructure is configured; **do not mistakenly think** `@Repository` is required for `JdbcTemplate` to translate errors.

### 3.1. Extracting the Root Cause for Diagnostics

At the service/infrastructure layer, log the task name, constraint name if safely provided, SQLState, and vendor code while keeping stack traces in the proper place; **never put raw SQL containing sensitive data into API responses**.

```java
import java.sql.SQLException;
import org.springframework.dao.DataIntegrityViolationException;

static SQLException findSqlCause(DataIntegrityViolationException ex) {
    for (Throwable cause = ex; cause != null; cause = cause.getCause()) {
        if (cause instanceof SQLException sql) {
            return sql;
        }
    }
    return null;
}
```

This helper suffices for simple cases. In batches, `BatchUpdateException` may store additional errors in `SQLException.getNextException()`, so real diagnostics must check the **next-exception chain** as well, not just the cause chain. Do not classify errors based on error message text (`message.contains("duplicate")`), because messages can change by locale, driver, and version.

## 4. Full Hands-On Practice: PostgreSQL + Spring JDBC + Java 17

Experiment goal: trigger all five kinds of data violations, cross-check **Spring exception + SQLSTATE**, and then prove that a two-operation transaction will **roll back completely** when the second operation hits a duplicate key. Do not substitute H2 for PostgreSQL in this lesson, because translation behavior must be observed with the real driver.

### 4.1. Starting Test PostgreSQL

Requires JDK 17+, Maven 3.9+, and Docker. Use a dedicated database/container so real data is untouched.

```bash
docker run --rm -d --name spring-constraint-lab -e POSTGRES_DB=constraint_lab -e POSTGRES_USER=lab -e POSTGRES_PASSWORD=labpass -p 54339:5432 postgres:16

docker exec spring-constraint-lab pg_isready -U lab -d constraint_lab
```

Run the program only after `pg_isready` reports PostgreSQL is accepting connections. In this local lab, `lab/labpass` is only a temporary credential. In real deployments, use a secret manager, TLS, and properly scoped dedicated accounts.

Create structure:

```text
spring-constraint-lab/
├── pom.xml
└── src/main/java/ConstraintDemo.java
```

### 4.2. Maven `pom.xml`

The versions below are pinned so the lesson is reproducible; real applications should use dependency management/BOM and organization-tested versions.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-constraint-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
                <configuration>
                    <mainClass>ConstraintDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring JDBC pulls in the required core dependencies; this program uses `DriverManagerDataSource` for simplicity and to avoid needing Spring Boot. In real web applications, use a connection pool and transaction manager configured by the application.

### 4.3. `src/main/java/ConstraintDemo.java`

```java
import java.sql.SQLException;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ConstraintDemo {
    private static final String INSERT_CUSTOMER =
            "INSERT INTO demo_customer(id, email, status) VALUES (?, ?, ?)";
    private static final String INSERT_PURCHASE =
            "INSERT INTO demo_purchase(id, customer_id, amount) VALUES (?, ?, ?)";

    private static SQLException sqlCause(Throwable error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql) {
                return sql;
            }
        }
        throw new IllegalStateException("No nested SQLException", error);
    }

    // A failure is considered valid only if both the Spring exception type
    // and PostgreSQL's SQLSTATE match expectations.
    private static void expectViolation(
            String label,
            String expectedState,
            Class<? extends DataIntegrityViolationException> expectedType,
            Runnable action) {
        try {
            action.run();
        } catch (DataIntegrityViolationException ex) {
            if (!expectedType.isInstance(ex)) {
                throw new IllegalStateException(
                        "Unexpected Spring type for " + label, ex);
            }
            SQLException sql = sqlCause(ex);
            if (!expectedState.equals(sql.getSQLState())) {
                throw new IllegalStateException(
                        "Unexpected SQLSTATE for " + label
                                + ": " + sql.getSQLState(), ex);
            }
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName()
                    + " / SQLSTATE=" + sql.getSQLState());
            return;
        }
        throw new IllegalStateException(
                "Expected constraint violation: " + label);
    }

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setUrl(System.getenv().getOrDefault(
                "DB_URL",
                "jdbc:postgresql://localhost:54339/constraint_lab"));
        ds.setUsername(System.getenv().getOrDefault("DB_USER", "lab"));
        ds.setPassword(System.getenv().getOrDefault(
                "DB_PASSWORD", "labpass"));

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(ds));

        // Use only these test schema/tables; the program drops and recreates them.
        jdbc.execute("DROP TABLE IF EXISTS demo_purchase");
        jdbc.execute("DROP TABLE IF EXISTS demo_customer");
        jdbc.execute("""
                CREATE TABLE demo_customer (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(120) NOT NULL UNIQUE,
                    status VARCHAR(20) NOT NULL
                        CONSTRAINT chk_demo_customer_status
                        CHECK (status IN ('ACTIVE', 'SUSPENDED'))
                )
                """);
        jdbc.execute("""
                CREATE TABLE demo_purchase (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL
                        REFERENCES demo_customer(id),
                    amount INTEGER NOT NULL
                        CHECK (amount > 0)
                )
                """);
        jdbc.update(INSERT_CUSTOMER, 1, "owner@example.test", "ACTIVE");

        expectViolation(
                "UNIQUE_EMAIL", "23505", DuplicateKeyException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        2, "owner@example.test", "ACTIVE"));

        expectViolation(
                "PRIMARY_KEY", "23505", DuplicateKeyException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        1, "second@example.test", "ACTIVE"));

        expectViolation(
                "FOREIGN_KEY", "23503", DataIntegrityViolationException.class,
                () -> jdbc.update(INSERT_PURCHASE, 1, 999, 100));

        expectViolation(
                "NOT_NULL", "23502", DataIntegrityViolationException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER, 3, null, "ACTIVE"));

        expectViolation(
                "CHECK", "23514", DataIntegrityViolationException.class,
                () -> jdbc.update(
                        INSERT_CUSTOMER,
                        4, "status@example.test", "UNKNOWN"));

        // Two INSERTs in the SAME transaction; the second statement triggers failure.
        try {
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        INSERT_CUSTOMER, 10, "pending@example.test", "ACTIVE");
                jdbc.update(
                        INSERT_CUSTOMER, 11, "owner@example.test", "ACTIVE");
            });
            throw new IllegalStateException(
                    "Expected duplicate-key failure in transaction");
        } catch (DuplicateKeyException ex) {
            if (!"23505".equals(sqlCause(ex).getSQLState())) {
                throw new IllegalStateException(
                        "Transaction did not fail as expected", ex);
            }
        }

        Integer pending = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_customer WHERE id = ?",
                Integer.class, 10);
        if (pending == null || pending != 0) {
            throw new IllegalStateException("Transaction was not rolled back");
        }
        System.out.println("TRANSACTION_ROLLBACK -> pending=0");

        // Skip only conflicts on email, not all data errors.
        int inserted = jdbc.update(
                """
                INSERT INTO demo_customer(id, email, status)
                VALUES (?, ?, ?)
                ON CONFLICT (email) DO NOTHING
                """,
                2, "owner@example.test", "ACTIVE");
        if (inserted != 0) {
            throw new IllegalStateException("Expected conflict to skip insert");
        }
        System.out.println("ON_CONFLICT_INSERTED -> 0");

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_customer",
                Integer.class);
        if (remaining == null || remaining != 1) {
            throw new IllegalStateException("Unexpected final row count");
        }
        System.out.println("CUSTOMERS_LEFT -> 1");
    }
}
```

**Explanation of key points in the code:**

- Each violation attempt uses an independent `jdbc.update(...)`; PostgreSQL returns the corresponding SQLSTATE, and Spring translates it into an exception. The test does not accept "any error passes": both **exception type and SQLSTATE** must match.
- `PRIMARY_KEY` and `UNIQUE_EMAIL` both produce `23505`; the exception type alone is insufficient to distinguish which error occurred. The test differentiates them via the input scenario.
- For `NOT NULL`, a `null` parameter is bound via JDBC PreparedStatement. The result is a DB **constraint** error, not a Java `NullPointerException`.
- `TransactionTemplate` and `JdbcTemplate` share the **same DataSource**; Spring binds the connection to the active transaction, so record `id=10` must be rolled back when record `id=11` causes a duplicate.
- `ON CONFLICT (email) DO NOTHING` is **PostgreSQL** syntax, not `JdbcTemplate` behavior. Only the email conflict is intentionally skipped; other `NOT NULL`, `CHECK`, or `FOREIGN KEY` violations can still fail the statement.

### 4.4. Compiling, Running, and Reading Output

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

On the test PostgreSQL instance with the specified dependencies, when all checks pass, the lines printed by the program are:

```text
UNIQUE_EMAIL -> DuplicateKeyException / SQLSTATE=23505
PRIMARY_KEY -> DuplicateKeyException / SQLSTATE=23505
FOREIGN_KEY -> DataIntegrityViolationException / SQLSTATE=23503
NOT_NULL -> DataIntegrityViolationException / SQLSTATE=23502
CHECK -> DataIntegrityViolationException / SQLSTATE=23514
TRANSACTION_ROLLBACK -> pending=0
ON_CONFLICT_INSERTED -> 0
CUSTOMERS_LEFT -> 1
```

If the Spring/driver version, translator configuration, or DBMS changes the translated type, the program intentionally fails so you investigate rather than printing a neat but misleading result. Maven/driver logs are excluded from the expected stdout above.

Clean up resources when finished:

```bash
docker stop spring-constraint-lab
```

## 5. Transactions Determine Which Data Remains After an Error

### 5.1. Two Statements, One Transaction

In the code above:

```text
BEGIN
  INSERT id=10, email=pending@example.test   → temporarily succeeds
  INSERT id=11, email=owner@example.test      → 23505
ROLLBACK                                        → id=10 does not exist either
```

A `DataAccessException` (including `DuplicateKeyException`) is an **unchecked exception**; with default `@Transactional`, it normally leads to rollback. `TransactionTemplate` also rolls back when its callback throws a runtime exception. Ensure both statements participate in the same transaction: same `DataSource` and same transaction manager, without opening raw external connections manually.

For Spring AOP `@Transactional`, **self-invocation within the same bean** may bypass the proxy, so the transaction interceptor does not run. Do not assume the annotation alone puts all operations inside a transaction: verify with integration tests.

### 5.2. PostgreSQL: Errors Put the Current Transaction in an Aborted State

If a statement triggers `23505` inside a regular PostgreSQL transaction, subsequent statements in that transaction can receive `25P02` (**in_failed_sql_transaction**) until rollback. Therefore, **do not** handle it by catching `DuplicateKeyException` mid-transaction and continuing to update as if nothing happened.

```java
// ANTI-PATTERN: do not do this on PostgreSQL.
@Transactional
public void saveTwo() {
    try {
        jdbc.update("INSERT INTO demo_customer VALUES (?, ?, ?)",
                    1, "owner@example.test", "ACTIVE"); // duplicate PK
    } catch (DuplicateKeyException ignored) {
        // Catching the error here does not restore the PostgreSQL transaction to a valid state.
    }
    jdbc.update("INSERT INTO demo_customer VALUES (?, ?, ?)",
                20, "next@example.test", "ACTIVE"); // may receive 25P02
}
```

The snippet above only illustrates the **wrong path**; do not run it standalone. The right approach is normally to let the exception escape the transaction boundary, roll back the entire unit of work, and handle business logic in the outer caller. When business rules genuinely require keeping work done prior to the error, design savepoints/`PROPAGATION_NESTED` specifically for your driver, transaction manager, and constraints, and test them; do not treat plain try/catch as a savepoint.

Some PostgreSQL constraints can be defined as `DEFERRABLE` and checked at **COMMIT time**. In that case, the error does not necessarily appear at `jdbc.update()` but may appear at the commit boundary, with a different wrapper/exception class. Error handling must wrap the **entire transaction** and preserve the DB cause, rather than catching only a single write statement.

## 6. Duplicate Keys: Prevention, Intentional Handling, and Concurrency

### 6.1. Do Not Rely on "Check If Exists First, Then Insert"

```text
Request A                        Request B
SELECT email='a' → absent         SELECT email='a' → absent
INSERT email='a' → succeeds       INSERT email='a' → 23505
```

Both requests can simultaneously observe "absent". A service-level check improves error messages, but **the DB UNIQUE constraint is what protects consistency under concurrency**. Standard design: define the unique constraint, write within a transaction, and handle duplicates at the business/API boundary.

If the constraint genuinely reflects the business rule "each email can register only once", you can return an intentional conflict response. If the duplicate stems from a bug in `id` generation, out-of-sync sequences, or internal data, do not turn every `DuplicateKeyException` into an "email already exists" message.

### 6.2. Choosing a Solution Based on Business Semantics

| Need | Handling approach | Risks to watch |
| --- | --- | --- |
| Insert new row, report duplicates to user | Keep unique constraint, catch `DuplicateKeyException` at the appropriate layer | Must identify the **exact constraint**, avoid leaking sensitive info |
| Resending the same idempotent request | Idempotency key with unique constraint + stored result/state control | Two competing requests; do not just check-then-insert |
| Intentionally skip on duplicate | PostgreSQL `INSERT ... ON CONFLICT (key) DO NOTHING` | Creates no new record; check `updateCount=0` |
| Update on duplicate | `ON CONFLICT (key) DO UPDATE SET ...` with clear conditions | Avoid unintended overwrites; concurrency still needs testing |
| Duplicate PK from key allocator | Fix sequence/identity/ID generation logic | Retrying with the same ID does not fix the cause |
| Duplicates from re-running a batch | Design unique key/idempotency and per-unit transactions | May roll back the whole batch; must manage committed portions |

**Do not drop a constraint to "fix an exception"**: if the constraint protects a business invariant, removing it can create long-lived inconsistent data. Only alter the schema when business rules intentionally change and a data migration plan exists.

## 7. Foreign Key, NOT NULL, CHECK: Each Requires a Different Fix

**`FOREIGN KEY`:** check whether the parent record exists and is valid within the same transaction, insert/delete ordering, `ON DELETE`/`ON UPDATE` policies, locks, and concurrent scenarios. Never "fix" it by disabling FK checks in production. For example, an FK error when deleting an account with dependent orders differs from an FK error when inserting an order pointing to a nonexistent account.

**`NOT NULL`:** check input data, DTO/entity-to-SQL mapping, required fields, default values, and how `null` is bound. `DEFAULT` applies only if the `INSERT` omits the column or uses `DEFAULT`; it **does not replace** an explicitly passed `NULL` value with the default value.

**`CHECK`:** inspect the constraint expression in the DB, API-generated data, valid enums/value sets, and migrations. For example, `status='UNKNOWN'` is not in `CHECK(status IN ('ACTIVE','SUSPENDED'))`, so either the client must fix the status or the schema must change per business rules. Do not assume every `23514` is an enum issue; it can come from any CHECK expression.

**Unique keys:** identify the exact set of columns marked unique. `UNIQUE(email)` differs from `UNIQUE(tenant_id,email)`; in a multi-tenant system, omitting `tenant_id` can accidentally forbid the same email across two tenants. Stable, clearly named constraints in migrations make diagnostics and testing easier.

The same `DataIntegrityViolationException` should **not** lead to the same remediation for every error.

## 8. Handling at Service/API Layers and Preserving Diagnostics

A sound organizational model:

```text
Controller/API
  └─ Service @Transactional (writes + business verification)
       └─ DAO/Repository with JdbcTemplate (parameterized SQL)
            └─ DB constraint (protects final invariant)
                → SQLException
                → DataAccessException
  ← Transaction rollback
  ← API layer converts an identified business error into an appropriate response
```

At the API layer, HTTP `409 Conflict` **may** be used for expected duplicates (e.g. already-registered email) when disclosing that fact is permitted; certain validation errors may be represented as `400` or `422` per the API contract. There is **no** global rule that every `DataIntegrityViolationException` must return `409`. An FK failure caused by an internal bug or out-of-sync schema is not necessarily a user error, and table structure should not be exposed in responses.

Example business mapping, **illustrative snippet and not a standalone controller**:

```java
try {
    accountService.createAccount(command);
} catch (DuplicateKeyException ex) {
    // Only return this message if you have confirmed the error belongs
    // to the email unique constraint and API policy allows disclosure.
    throw new AccountAlreadyExistsException("Email is already registered", ex);
}
```

With multiple unique constraints, do not rely solely on `DuplicateKeyException` to choose the message. You can inspect the constraint name via driver-supported APIs (e.g. server error details in pgJDBC), combined with write-command context and integration tests; avoid substring matching on natural-language messages. When supporting multiple DBMSs, encapsulate vendor-specific classification in an infrastructure adapter instead of scattering hardcoded SQLSTATEs across services.

Diagnostic logging: operation name, application code, SQLState, vendor code, constraint name (if available), correlation ID/transaction ID; avoid logging sensitive column values (email, tokens, PII). Client responses should be contract-stable and never contain raw SQL, stack traces, or DB passwords.

## 9. Constraint Errors in `batchUpdate()`

`JdbcTemplate.batchUpdate()` uses the JDBC driver's batch capabilities. If an entry duplicates a key or violates FK/CHECK, JDBC may throw `BatchUpdateException`, containing `getUpdateCounts()` and sometimes a `getNextException()` chain; Spring translates the error accordingly. Do not infer that all items after the failing item were applied, because drivers may stop or continue in their own way.

- `Statement.SUCCESS_NO_INFO = -2`: the statement may have succeeded, but the driver has no exact row count.
- `Statement.EXECUTE_FAILED = -3`: marks the failing element in the counts array if supplied by the driver.
- `getUpdateCounts()` does not guarantee the transaction **committed**. If the batch runs inside a transaction and fails, rollback or retry decisions belong at the transaction boundary.
- When using `INSERT ... ON CONFLICT`, define business requirements per element (skip, update, or fail), measure actual rows after commit, and verify idempotency.

For retrying an entire batch, use stable keys/idempotency and know which data committed in prior transactions; never blindly loop the exact same batch that just threw `DuplicateKeyException`. On connection errors where it is unclear whether the server committed, verify business state before re-running.

## 10. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`DuplicateKeyException` is completely unrelated to `DataIntegrityViolationException`" | It is a **subclass** of `DataIntegrityViolationException`. |
| "`DataIntegrityViolationException` means duplicate email" | It is a **broad category** covering many constraints and integrity errors. |
| "Having `@NotNull` removes the need for `NOT NULL` in the DB" | Validators and the DB protect at two different layers; validators can be bypassed or raced. |
| "Checking if an email exists before inserting prevents duplicates forever" | Two concurrent transactions can both pass the precheck. |
| "After `catch`, the PostgreSQL transaction keeps running normally" | After an SQL error, the transaction may be in aborted state `25P02` until rollback/savepoint. |
| "Every Class 23 error on every DB produces the same Spring subclass" | Translators can vary by DBMS/driver/version/config; always verify. |
| "Retrying immediately with the same data clears duplicates" | Unique duplicates are normally non-transient; change data or handle the conflict properly. |
| "`ON CONFLICT DO NOTHING` cures all integrity errors" | It handles only the specified conflict, not other constraints or API policies. |
| "Seeing `BatchUpdateException` means every insert failed" | How many items ran and rolled back/committed depends on driver and transaction. |

## 11. Integration Testing Checklist and Review Questions

A test suite for persistence logic should include **at least**:

1. Inserting valid data and reading it back accurately.
2. Inserting duplicate `PRIMARY KEY` and each `UNIQUE` constraint; checking Spring type and SQLState/vendor code on the target DB.
3. Violating `NOT NULL`, `FOREIGN KEY`, and `CHECK`; verifying no invalid data is written.
4. Two statements in one transaction: first succeeds, second fails; verifying rollback leaves **neither** present.
5. Running two concurrent requests with the same unique key and confirming only one final record exists.
6. Testing `ON CONFLICT`/upsert if used; checking row counts and non-overwrite conditions.
7. Testing a batch with one failing element; verifying rollback policy and actual data.
8. Checking API mappings do not leak SQL, constraint details, or personal information.

**Self-check questions:**

- Why does catching `DataIntegrityViolationException` before `DuplicateKeyException` cause a compile error?
- Is PostgreSQL `23505` enough to know whether email or id was duplicated? What else must be observed?
- Why do `@Transactional` and a unique constraint form a stronger error boundary than a `SELECT EXISTS` precheck?
- Why shouldn't `23503` be handled the same way as `23505`, even though both belong to the integrity group?
- When is `ON CONFLICT DO NOTHING` appropriate, and when can it mask business bugs?
- After a statement fails in a PostgreSQL transaction, why can swallowing the exception and continuing lead to `25P02`?

## References

- Spring Framework, *Using the JDBC Core Classes* (SQLExceptionTranslator): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, `DuplicateKeyException` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DuplicateKeyException.html
- Spring Framework, `DataIntegrityViolationException` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html
- Spring Framework, `SQLExceptionSubclassTranslator` and `SQLStateSQLExceptionTranslator`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/SQLExceptionSubclassTranslator.html
- Spring Framework source, `sql-error-codes.xml` (vendor/SQLSTATE mappings): https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/resources/org/springframework/jdbc/support/sql-error-codes.xml
- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- PostgreSQL, *Error Codes*: https://www.postgresql.org/docs/current/errcodes-appendix.html
- PostgreSQL, *INSERT* (`ON CONFLICT`): https://www.postgresql.org/docs/current/sql-insert.html
- PostgreSQL, *Constraints*: https://www.postgresql.org/docs/current/ddl-constraints.html
- Java SE, `BatchUpdateException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html

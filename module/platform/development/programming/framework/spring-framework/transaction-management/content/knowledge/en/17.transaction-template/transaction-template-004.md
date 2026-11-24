# Returning Results from Callbacks and Handling Exceptions with TransactionTemplate

## Learning Objectives

In Spring Framework, `TransactionTemplate` helps wrap a block of Java code in a transaction **programmatically** (programmatic transaction management). Two scenarios that must be mastered are **when a callback returns a result** and **when a callback fails or requests a rollback**. Their behavior directly affects business correctness:

- `execute(TransactionCallback<T>)` runs the callback, finishes the transaction according to the transaction manager's rules, and then **returns `T`** if the process completes successfully. The callback can return an object, collection, record, `Optional<T>`, or `null`.
- `executeWithoutResult(Consumer<TransactionStatus>)` fits operations that do not need a return value; the callback receives `TransactionStatus` so it can request a rollback.
- If the callback **throws a `RuntimeException` or `Error`** out of the callback, with standard `TransactionTemplate` and transaction managers, Spring performs a rollback and then **propagates the error to the caller**. If rollback fails, a transaction error may replace the original error.
- If the callback **catches an exception and returns normally**, the transaction manager does not automatically know that it was a business failure requiring rollback. If not marked rollback-only, Spring will typically attempt to commit.
- If the callback calls `status.setRollbackOnly()` and returns a value, **that value does not mean the data committed**. With a normal new physical transaction, Spring can roll back and still return the callback's value; when participating in an outer transaction, an error/`UnexpectedRollbackException` can appear at the outer transaction boundary.
- The `TransactionCallback<T>` callback **does not declare `throws` checked exceptions**; `IOException`/`SQLException` must be handled, converted into an unchecked exception, or reported via a failure result with an explicit rollback decision.
- The transaction boundary does not span an async task returned later; returning a `CompletableFuture` or a lazy stream does not keep the transaction alive around subsequent execution.

This lesson covers the nature of the API, result/rollback tables, common exception-handling mistakes, and **a runnable Java 17 + Spring JDBC/H2 example**. The primary scope is synchronous (imperative) transactions using `PlatformTransactionManager`; for reactive transactions, use `TransactionalOperator` and Reactor context instead of extrapolating directly from this example.

## 1. What Does `TransactionTemplate` Do?

Programmatic transactions do not mean manually writing `connection.setAutoCommit(false)`, `commit()`, and `rollback()` in every service. Instead, Spring manages the lifecycle based on `PlatformTransactionManager`. You supply the **business logic** inside a callback.

```text
Caller
   |
   |  T result = transactionTemplate.execute(status -> { ...; return value; });
   v
TransactionTemplate
   |
   +-- getTransaction(transactionDefinition)
   |       opens a physical transaction or joins an existing transaction
   |
   +-- calls TransactionCallback.doInTransaction(status)
   |       JDBC/Repository/DAO executes inside the corresponding transaction
   |
   +-- Callback returns T successfully?
   |       -> calls transactionManager.commit(status)
   |           (may actually commit, roll back due to rollback-only,
   |            or merely complete a scope joining outer)
   |
   +-- Callback throws RuntimeException/Error?
   |       -> rollback(status) then propagate exception
   |
   +-- After successful completion:
           -> returns result T to caller
```

**Three layers to separate:**

1. **The callback's result:** the value produced by `return ...` in Java. It is not a message guaranteeing commit.
2. **Transaction status:** `TransactionStatus`, `isRollbackOnly()`, `isNewTransaction()`, and the transaction manager's decision. A callback does not always have an independent physical transaction.
3. **Committed data outcome in the database:** can only be verified once the physical transaction truly commits; if joining an outer transaction, it may have to wait for outer completion.

With Spring's standard `TransactionTemplate` implementation, the callback is invoked inside a `try`, runtime failures lead to rollback, while the success path calls `commit(status)` before `return result`. A specialized transaction manager implementing `CallbackPreferringPlatformTransactionManager` may handle the callback via a separate branch; therefore treat this as **Spring's contract and typical flow**, rather than relying on internal structure as a business programming API.

## 2. `execute(TransactionCallback<T>)`: Callback with a Return Value

Conceptual declaration:

```java
@FunctionalInterface
public interface TransactionCallback<T> {
    T doInTransaction(TransactionStatus status);
}
```

This is a simplified signature for learning, not a file you need to create yourself; in Spring, the interface lives in `org.springframework.transaction.support.TransactionCallback`. The callback receives the current scope's `TransactionStatus` and returns `T`. The output of `execute` can be `null`; the caller is responsible for handling null.

Example using a lambda:

```java
String invoiceCode = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO invoices(code) VALUES (?)", "INV-001"
    );
    return "INV-001";
});
```

This is a **service snippet** assuming `template`, `jdbcTemplate`, and the `invoices` table exist, not a standalone program. In a new transaction without errors, Spring commits the INSERT before returning the string to the caller. If the commit fails, the caller **does not receive a normal return**; it receives an exception from transaction completion.

### 2.1. How Is Java Generic `T` Inferred?

`T` is the type of value returned by the callback:

```java
// Returning String:
String code = template.execute(status -> "INV-001");

// Returning Integer:
Integer count = template.execute(status ->
    jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM invoices", Integer.class
    )
);

// Returning an immutable object:
record CreateResult(String code, int rowsAffected) {}
CreateResult result = template.execute(status -> {
    int updated = jdbcTemplate.update(
        "INSERT INTO invoices(code) VALUES (?)", "INV-002"
    );
    return new CreateResult("INV-002", updated);
});

// Returning Optional instead of using null to represent not found:
Optional<String> value = template.execute(status ->
    Optional.ofNullable(findCodeById(10L))
);
```

These are **conceptually independent snippets**, not meant to be pasted directly into one Java class: `findCodeById` and the schema must exist in the application; `Optional` needs importing. JDBC's `updated` value is the number of rows affected by the statement, **not a final commit certificate** if an outer transaction later rolls back.

**A good practice:** return a simple DTO/record already materialized inside the transaction; avoid returning a JPA entity still needing lazy-loading later or a `Stream` the caller has not consumed yet. The transaction closing before lazy evaluation can cause `LazyInitializationException` or use a connection outside the transaction.

### 2.2. `return null` Is Not a Rollback Command

```java
String result = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_event(label) VALUES (?)", "NONE"
    );
    return null;
});
```

In a new transaction, if both the SQL and commit succeed, the record **is still committed**, even though `result == null`. `null` is only a **Java result value**; it does not trigger a rollback.

Conversely, `return "SUCCESS"` does not prove the transaction committed either if the callback marked rollback-only or the scope is joining an outer transaction.

### 2.3. Do Not Unbox Nullable Results When Unsure

```java
// Prone to NullPointerException at the caller:
int count = template.execute(status -> null);

// Clearer:
Integer countOrNull = template.execute(status -> null);
int safeCount = (countOrNull == null) ? 0 : countOrNull;
```

These are **two comparison snippets**, not meant to be run together in one example. The unboxing error occurs **after `execute` has returned `null`**; with a newly committed physical transaction, a `NullPointerException` in the caller does not go back and roll back the already completed transaction. If null has business meaning, use `Optional` or an explicit result type and check before using.

## 3. `executeWithoutResult`: Running a Callback Without Needing a Result

Since Spring Framework 5.2, `TransactionOperations` (implemented by `TransactionTemplate`) has the convenience method:

```java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE accounts SET last_reviewed = CURRENT_TIMESTAMP WHERE id = ?",
        42L
    );
});
```

This snippet uses an `accounts` table with the corresponding columns. The callback receives `TransactionStatus`, yet **the callback type is `Consumer<TransactionStatus>`**, returning no `T`. It suits update, delete, audit, and batch-processing operations when the caller only needs to know whether the transaction succeeded or failed via control flow/exceptions.

Comparison:

| API | Lambda | Value caller receives | When to use |
|---|---|---|---|
| `execute(TransactionCallback<T>)` | `status -> { ...; return value; }` | `T` or `null` | Need a DTO, id, count, or query result |
| `executeWithoutResult(Consumer<TransactionStatus>)` | `status -> { ...; }` | No value (`void`) | Only need DB side effects and exception handling |
| `execute(status -> { ...; return null; })` | Has `return null` | `null` | Valid, but less expressive than `executeWithoutResult` for void callbacks |

**Remember:** `executeWithoutResult` does not run transactions "fire-and-forget". It is still **synchronous**: the call only finishes after the transaction template completes the scope and can throw exceptions just like `execute`. Do not confuse it with async execution.

## 4. Decision Table: How Does a Callback End?

Assume the initial cases below are a **new physical transaction**, using a standard JDBC Spring transaction manager and with no system errors occurring during commit/rollback.

| What happens inside callback | Transaction decision | Result at caller |
|---|---|---|
| Returns `"OK"`, not marked rollback-only | Commit | `execute(...)` returns `"OK"` after completion |
| Returns `null`, not marked rollback-only | Commit | `execute(...)` returns `null` |
| `void` callback ends normally | Commit | `executeWithoutResult(...)` returns `void` |
| Throws `IllegalArgumentException` out of callback | Rollback | Exception propagates to caller if rollback succeeds |
| Throws `Error` out of callback | Rollback | `Error` is rethrown if rollback succeeds |
| Catches exception inside and returns `"HANDLED"` | Usually commits | `"HANDLED"`; no automatic rollback merely because an exception was caught |
| Calls `status.setRollbackOnly()` and returns `"NOT_SAVED"` | Rolls back entire new physical transaction | Caller **can receive `"NOT_SAVED"` normally** |
| Callback succeeds but `commit()` fails | Cannot report normal success | Caller receives transaction/system exception; actual outcome must be assessed |
| Callback throws an error and rollback **also** fails | No guarantee cleanup succeeded | Caller may receive rollback's `TransactionException`, potentially masking original error |

**Important exception for transactions joining an outer transaction:** `execute` may only complete a **logical scope** rather than committing a physical transaction. The outer transaction remains alive, and `UnexpectedRollbackException` may only appear when outer attempts to commit. Do not infer "`execute` returned a result => data is physically committed" if propagation is `REQUIRED` and an outer transaction exists.

## 5. `RuntimeException` and `Error`: Roll Back and Propagate the Error

A common pattern:

```java
try {
    String result = template.execute(status -> {
        jdbcTemplate.update(
            "INSERT INTO payments(reference) VALUES (?)",
            "PAY-01"
        );

        if (paymentInvalid()) {
            throw new IllegalStateException("payment invalid");
        }
        return "PAY-01";
    });

    // Reached only when execute returns normally.
    sendSuccessResponse(result);
} catch (IllegalStateException ex) {
    // The callback already caused the transaction manager to process rollback,
    // unless a severe rollback failure occurred.
    sendFailureResponse(ex.getMessage());
}
```

This is a **business snippet**; `paymentInvalid`/`sendSuccessResponse`/`sendFailureResponse` must be supplied by the application. With a new transaction and an unchecked error escaping the callback, Spring invokes rollback. Code in the caller's `catch` branch runs **after** the template has attempted rollback; catching on the outside does not "drive the rollback".

**Why not catch and swallow the error inside the callback?** Because `TransactionTemplate` only sees that the callback ultimately returned normally; it has no information that an exception occurred and was handled. If the business logic truly allows continuing and committing, an inner catch can be right. If everything must be canceled, you must **rethrow an unchecked exception** or call `status.setRollbackOnly()`.

### 5.1. Catching **Outside** the Callback vs. Catching **Inside** the Callback Are Not the Same

**Catching outside** — error escapes the callback:

```java
try {
    template.executeWithoutResult(status -> {
        jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "FIRST");
        throw new IllegalStateException("bad input");
    });
} catch (IllegalStateException ex) {
    // TransactionTemplate already invoked rollback before the error arrived here.
}
```

**Catching inside** — callback returns normally:

```java
template.executeWithoutResult(status -> {
    jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "FIRST");
    try {
        throw new IllegalStateException("bad input");
    } catch (IllegalStateException ex) {
        // Suppose this error can be ignored.
        // Neither rethrown nor marked rollback-only.
    }
    // TransactionTemplate sees the callback end normally:
    // may COMMIT INSERT "FIRST".
});
```

These snippets assume the `events` table exists and `template`/`jdbcTemplate` share the right datasource; they are not standalone programs. The key point is not the syntactic placement of `try/catch`, but **whether an exception ultimately escapes the callback boundary** and whether the status is **rollback-only**.

### 5.2. Exceptions from JDBC/Spring Data Access

`JdbcTemplate` translates many `SQLException`s into **unchecked** `DataAccessException`s (e.g., `DuplicateKeyException`). When a `DataAccessException` escapes the callback, it triggers rollback via the unchecked mechanism. However, if you catch the error inside the callback and ignore it, the transaction manager may attempt to commit. With some databases (e.g., PostgreSQL), a SQL error puts the transaction into an aborted state, making it impossible to continue/commit normally without rolling back to a proper savepoint. Thus "swallowing `DataAccessException`" is not a safe transaction recovery strategy.

If you need to skip one failing batch item while keeping valid ones, consider savepoints/`Propagation.NESTED` with a supporting manager/driver or splitting transactions properly, rather than catching all errors and letting the transaction commit arbitrarily.

## 6. `status.setRollbackOnly()`: Rolling Back Without Throwing an Exception

When business logic decides not to persist data even though the callback can still return a result (e.g., composite validation), use `TransactionStatus.setRollbackOnly()`:

```java
record SaveOutcome(boolean saved, String reason) {}

SaveOutcome outcome = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO reservations(ref) VALUES (?)", "R-01"
    );

    boolean valid = false; // Simulated value for illustration.
    if (!valid) {
        status.setRollbackOnly();
        return new SaveOutcome(false, "quota exceeded");
    }
    return new SaveOutcome(true, "created");
});
```

This is a snippet requiring the `reservations` schema and `template`/`jdbcTemplate` fields in the service. If the template manages a **new physical transaction**, Spring sees rollback-only during completion, rolls back the data, and can still return `SaveOutcome(false, ...)` normally. Application policy must treat `saved=false` as a business failure, **never returning HTTP 201 just because `execute` did not throw an exception**.

**Do not write like this:**

```java
String result = template.execute(status -> {
    jdbcTemplate.update("INSERT INTO events(label) VALUES (?)", "x");
    status.setRollbackOnly();
    return "COMMITTED"; // Misleading value: the data was rolled back.
});
```

This is a **misleading-message anti-pattern snippet**. The return value does not automatically reflect the DB outcome. Fix it to a DTO explicitly stating `rejected`/`notSaved`, or throw a business exception if the caller needs clear differentiation via control flow.

### 6.1. `isRollbackOnly()` and `isNewTransaction()`

The callback can query the status:

```java
template.execute(status -> {
    boolean newPhysical = status.isNewTransaction();
    boolean marked = status.isRollbackOnly();

    // Used for logging/diagnostics, not as a commit promise.
    return "new=" + newPhysical + ", rollbackOnly=" + marked;
});
```

This is a snippet; do not pass `status` to another thread. `isNewTransaction()` helps distinguish a scope starting a new physical transaction from one joining an existing transaction. `isRollbackOnly()` reflects rollback-only at the time of inspection; an outer transaction or manager can still decide to roll back later, so `false` **does not guarantee a future commit**.

### 6.2. When an Outer Transaction Exists

Suppose an outer scope has opened transaction A. An inner `TransactionTemplate` with default `PROPAGATION_REQUIRED` will **join** A:

```text
outer transaction A begins
    |
    +-- inner TransactionTemplate.execute(...)
    |     status.isNewTransaction() == false
    |     inner marks rollback-only
    |     inner may return a value
    |
    +-- outer keeps running, thinking it can commit
    |
    +-- outer commits A -> rolls back due to global rollback-only
                            may throw UnexpectedRollbackException
```

This is a logical model, not universal output for every manager. When the inner side marks rollback-only on a logical scope participating in A, A can be marked **global rollback-only**; outer attempting to commit will hit `UnexpectedRollbackException` so it does not mistakenly believe the commit succeeded.

In particular, **do not treat the return value from an inner `execute` as a physical commit certificate**. Only when the outer transaction completes is the outcome of the entire transaction A known.

If a piece of work must commit independently, `PROPAGATION_REQUIRES_NEW` can create an independent physical transaction, though it carries pool/lock risks and business inconsistency between inner/outer. If partial rollback is needed, `NESTED`/savepoint has different semantics; do not automatically equate it with calling `setRollbackOnly()` in a `REQUIRED` scope.

## 7. Checked Exceptions: How to Handle Them When Callbacks Do Not Declare `throws`?

`TransactionCallback<T>.doInTransaction(TransactionStatus)` **does not** declare `throws IOException` or `throws SQLException`. This means a lambda implementing this interface cannot directly let an unhandled checked exception escape in Java.

Example that **does not compile**:

```java
String content = template.execute(status -> {
    return Files.readString(Path.of("input.txt")); // Unhandled IOException.
});
```

This is an **intentionally invalid example**; `Files.readString` throws checked `IOException`. The Java compiler requires handling it.

### 7.1. Converting a Checked Exception into an Unchecked Exception When Rollback Is Needed

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

String content = template.execute(status -> {
    try {
        String data = Files.readString(Path.of("input.txt"));
        jdbcTemplate.update(
            "INSERT INTO documents(text_content) VALUES (?)", data
        );
        return data;
    } catch (IOException ex) {
        throw new UncheckedIOException("cannot load document", ex);
    }
});
```

This is a snippet requiring `documents`, `template`, and `jdbcTemplate`. If reading the file fails, `UncheckedIOException` escapes the callback and Spring rolls back the DB transaction. The file-read failure itself is not something the DB rolls back, but SQL statements executed **in the same transaction** will be rolled back.

For application checked exceptions, you can use an **unchecked business exception** with a `cause`:

```java
try {
    template.execute(status -> {
        try {
            invokeCheckedService();
            return "OK";
        } catch (CheckedBusinessException ex) {
            throw new IllegalStateException("cannot finish business action", ex);
        }
    });
} catch (IllegalStateException ex) {
    // Inspect getCause() to identify the original error type if needed.
}
```

This is a snippet with symbolic business types/methods. You should not wrap **every** checked exception into a single runtime type if the caller needs to distinguish retryable errors, validation errors, or system errors; design a proper exception hierarchy and log the cause appropriately.

### 7.2. Catching a Checked Exception, Marking Rollback-Only, and Returning a Business Result

Not every error needs to be thrown to the caller. For example, an import job wants to return `ImportResult(success=false, reason=...)` instead of throwing an exception:

```java
record ImportResult(boolean saved, String message) {}

ImportResult result = template.execute(status -> {
    try {
        String csv = readCsvChecked();
        storeCsvInDatabase(csv);
        return new ImportResult(true, "saved");
    } catch (IOException ex) {
        status.setRollbackOnly();
        return new ImportResult(false, "cannot read CSV");
    }
});
```

This is a snippet: `readCsvChecked` and `storeCsvInDatabase` must be defined in the application. **Catching the exception and marking rollback-only are two separate actions**. If you forget `setRollbackOnly()` in the failure-return branch, earlier SQL statements may be committed.

In a new transaction, `ImportResult(false, ...)` can reach the caller **without an exception** even though the DB rolled back; you must handle `saved=false` rather than assuming normal return from `execute` means success.

### 7.3. Do Not Confuse with `@Transactional`'s Checked Exception Rules

`@Transactional` (declarative transaction management) rolls back by default on unchecked `RuntimeException`/`Error`, whereas checked exceptions normally do not roll back unless `rollbackFor` is configured. However, `TransactionTemplate` has a callback contract that **does not declare checked exceptions**; you cannot mechanically copy the rule "checked exceptions do not roll back" onto returning results from a `TransactionTemplate` callback.

**Spring implementation detail:** In the standard transaction manager branch (non-callback-preferring), `TransactionTemplate.execute` has a defensive `catch (Throwable)` clause: if an unexpected checked throwable somehow bypasses the interface (e.g., via sneaky throw), Spring attempts rollback and wraps it in `UndeclaredThrowableException`. This is **not a recommended pattern**; handle/convert checked exceptions explicitly so Java code stays readable and errors carry clear semantics.

### 7.4. Callback Errors and Rollback Errors Can Compound

If a callback throws `IllegalStateException` yet rollback itself fails due to a connection drop, the caller may receive `TransactionSystemException` or another rollback-related exception instead of the original business exception. Spring tries to preserve/reference the original error in some cases, but do not write code catching only one exception class and assuming every rollback succeeds.

For transaction system errors, log both the exception and its cause, mark the request failed, and do not automatically retry non-idempotent operations without knowing how far the DB commit/rollback went.

## 8. Runnable Example: Verifying Return, Void, Exception, Catch, Rollback-Only, and Null

The demo uses **Java 17**, **Spring JDBC**, **H2 in-memory**, and **`JdbcTransactionManager`**. It needs no Spring Boot, web server, or AOP proxy: `TransactionTemplate` takes the transaction manager directly and executes all callbacks synchronously on a Spring-managed JDBC connection.

The program runs **seven scenarios**:

1. Callback returns `String` after a successful INSERT.
2. Void callback writes an INSERT via `executeWithoutResult`.
3. Callback throws an unchecked exception: INSERT rolls back.
4. Callback catches an exception inside and returns a result: INSERT commits.
5. Callback calls `status.setRollbackOnly()` yet still returns `String`: INSERT rolls back, caller still receives the string.
6. Helper throws checked `IOException`, converted to `UncheckedIOException`: INSERT rolls back.
7. Callback returns `null`: INSERT still commits, caller receives `null`.

Afterward, a callback reads out the list of committed labels, showing that **return values and database results are two separate things to observe**.

### 8.1. Project Structure

```text
transaction-template-callback-demo/
├── pom.xml
└── src/main/java/com/example/callback/Main.java
```

### 8.2. `pom.xml` File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>transaction-template-callback-demo</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-jdbc` brings in the transaction infrastructure. H2 is the in-memory database. Pinned versions keep the demo reproducible on JDK 17+. In real projects, manage dependencies with a supported BOM/version and replace `DriverManagerDataSource` with a properly configured connection pool.

### 8.3. `src/main/java/com/example/callback/Main.java` File

```java
package com.example.callback;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static void add(JdbcTemplate jdbc, String label) {
        jdbc.update(
            "INSERT INTO callback_events(label) VALUES (?)",
            label
        );
    }

    private static int rows(JdbcTemplate jdbc) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM callback_events",
            Integer.class
        );
        return count;
    }

    private static List<String> labels(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM callback_events ORDER BY id",
            String.class
        );
    }

    // Simulates a Java API with a checked exception.
    private static void checkedFailure() throws IOException {
        throw new IOException("io-unavailable");
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:callback_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
            "CREATE TABLE callback_events (" +
            "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
            "label VARCHAR(80) NOT NULL)"
        );

        JdbcTransactionManager manager = new JdbcTransactionManager(ds);
        TransactionTemplate tx = new TransactionTemplate(manager);

        // 1. Callback returns String, transaction commits.
        String first = tx.execute(status -> {
            add(jdbc, "A");
            return "A-created";
        });
        System.out.println("success result=" + first +
                " rows=" + rows(jdbc));

        // 2. Void callback, transaction commits.
        tx.executeWithoutResult(status -> add(jdbc, "B"));
        System.out.println("void rows=" + rows(jdbc));

        // 3. Unchecked exception escapes callback -> rollback.
        try {
            tx.execute(status -> {
                add(jdbc, "C");
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            System.out.println("outside caught=" + ex.getMessage());
        }
        System.out.println("after outside catch rows=" + rows(jdbc));

        // 4. Exception caught INSIDE callback -> commit.
        String handled = tx.execute(status -> {
            add(jdbc, "D");
            try {
                throw new IllegalArgumentException("local");
            } catch (IllegalArgumentException ex) {
                return "handled-inside";
            }
        });
        System.out.println("inside result=" + handled +
                " rows=" + rows(jdbc));

        // 5. Mark rollback-only yet still return String.
        String rejected = tx.execute(status -> {
            add(jdbc, "E");
            status.setRollbackOnly();
            return "E-not-committed";
        });
        System.out.println("rollbackOnly result=" + rejected +
                " rows=" + rows(jdbc));

        // 6. Checked IOException -> converted into UncheckedIOException.
        try {
            tx.execute(status -> {
                add(jdbc, "F");
                try {
                    checkedFailure();
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
                return "never-returned";
            });
        } catch (UncheckedIOException ex) {
            System.out.println(
                "checked adapted=" + ex.getCause().getMessage()
            );
        }
        System.out.println("after checked failure rows=" + rows(jdbc));

        // 7. return null is NOT rollback.
        String noValue = tx.execute(status -> {
            add(jdbc, "G");
            return null;
        });
        System.out.println("null result=" + (noValue == null) +
                " rows=" + rows(jdbc));

        // Return a List<String> fully materialized inside the transaction.
        List<String> committed = tx.execute(status -> labels(jdbc));
        System.out.println("committed labels=" + committed);
    }
}
```

**Points to note in the program:**

- `tx.execute(...)` finishes first and only then yields the `String` or `List<String>`; no hidden `@Transactional`/proxy is needed for the callbacks in the demo.
- `JdbcTemplate` uses the datasource managed by the same transaction manager. The `add(...)` calls participate in the callback's JDBC transaction.
- Each `tx.execute` in `main` is called **with no outer transaction active**, so with default `REQUIRED` propagation each callback creates **a new physical transaction**. This is the condition making the normal-return rollback-only behavior in case 5 predictable.
- `checkedFailure()` declares `throws IOException`, which is caught and wrapped unchecked directly inside the lambda. There is no sneaky throw.
- `labels(jdbc)` is materialized into a `List<String>` inside the callback; no lazy stream is returned after the transaction closes.
- Each case prints `rows(jdbc)` **after** completion, using a fresh connection with no active Spring transaction, to verify the data actually committed/rolled back.

### 8.4. Running and Expected Output

From the `transaction-template-callback-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.callback.Main
```

Lines printed **by the program**, excluding environment-dependent Maven/driver logs:

```text
success result=A-created rows=1
void rows=2
outside caught=boom
after outside catch rows=2
inside result=handled-inside rows=3
rollbackOnly result=E-not-committed rows=3
checked adapted=io-unavailable
after checked failure rows=3
null result=true rows=4
committed labels=[A, B, D, G]
```

Reading along the timeline:

| Case | What did the callback insert? | What did the callback return/throw? | Remaining data |
|---|---|---|---|
| 1 | A | Returned `"A-created"` | A committed |
| 2 | B | Void, completed normally | A and B |
| 3 | C | `IllegalStateException("boom")` escaped callback | C rolled back |
| 4 | D | Caught error in lambda, returned `"handled-inside"` | D committed |
| 5 | E | `setRollbackOnly()`, returned `"E-not-committed"` | E rolled back even though caller got string |
| 6 | F | Checked IOException converted to UncheckedIOException | F rolled back |
| 7 | G | Returned `null` normally | G committed |

This is a Java example **designed to be runnable** with the declared dependencies. The output above is **expected according to Spring JDBC/H2 semantics**, not measured from a Maven run in this lesson. If using another engine or changing propagation, run integration tests yourself and inspect actual exceptions/commits.

## 9. Distinguishing Business Errors, Transaction Errors, and Post-Commit Errors

There are at least three sources of failure:

### 9.1. Errors Inside the Callback Before Commit

For example, validation failure or SQL throwing `DataAccessException`. An escaping `RuntimeException` causes the template to request rollback. If rollback succeeds, the original exception is typically propagated to the caller.

**Approach:** set clear rollback policies, return appropriate business errors, and do not continue treating the request as successful.

### 9.2. Errors During Transaction Completion

The callback can **return a valid result**, yet `transactionManager.commit(status)` can still fail: deadlock, serialization failure, deferred constraint check, connection loss, database unavailable, or an error in a synchronization callback.

```text
callback computes result="OK"
        |
        v
commit(status)
   |
   +-- succeeds -> execute() returns "OK"
   |
   +-- fails -> execute() throws exception,
                caller DOES NOT receive normal return
```

**Do not send a "success" response or publish a message inside the callback before commit just because `result` was produced.** Especially with timeout/connection loss at COMMIT, there are cases where the application cannot know for sure whether the server committed. Use an idempotency key, check the transaction outcome, or reconcile before retrying non-idempotent operations.

### 9.3. Side Effects After Callback Logic but Before/Outside Database Completion

Sending emails, HTTP requests, messages, file writes, or cache updates inside a callback **do not roll back along with the JDBC transaction**. If the SQL later rolls back, the side effect may still have happened.

```java
String id = template.execute(status -> {
    String generatedId = createOrderInDatabase();
    emailService.sendOrderCreated(generatedId); // Has side effect.
    return generatedId;
});
```

This is a snippet with symbolic application methods. It is possible for the email to send successfully while the DB commit fails. Do not patch over this with an unconditional `catch` that sends a compensating email; consider transactional outbox, after-commit hooks (with their own limits), or idempotent workflows.

Even when code calls `emailService.send...` **after** `execute` returns normally, an outer transaction still open may not have physically committed yet. When notification must wait until the **final transaction** commits, align with the physical boundary and corresponding coordination mechanism.

## 10. Failure Values Like `Optional.empty()`, `Either.Left`, or `Result.failure` Do Not Roll Back Automatically

In Java, you can design APIs that do not throw and instead return a "failure result":

```java
record SaveDecision(boolean accepted, String reason) {}

SaveDecision decision = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO orders(reference) VALUES (?)", "A-100"
    );

    if (validationFailed()) {
        return new SaveDecision(false, "invalid order");
    }
    return new SaveDecision(true, "created");
});
```

This snippet assumes `validationFailed`. If the failure branch merely does `return new SaveDecision(false,...)` without throwing an exception or calling `setRollbackOnly()`, a new transaction **can commit the INSERT**. Spring `TransactionTemplate` **does not inspect the semantics** of DTOs, `Optional.empty()`, `Either`, `Try`, `ResponseEntity`, `CompletableFuture`, or any custom result class to decide rollback.

A proper approach if rollback is desired when `accepted=false`:

```java
SaveDecision decision = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO orders(reference) VALUES (?)", "A-101"
    );

    if (validationFailed()) {
        status.setRollbackOnly();
        return new SaveDecision(false, "invalid order");
    }
    return new SaveDecision(true, "created");
});
```

Another approach: throw an unchecked business exception and catch it **outside the callback**. Which choice fits depends on the API contract:

- **Exception** is good when transaction failure is exceptional or the caller must be forced to handle errors; rollback occurs because the exception escapes the callback.
- **Result object + rollback-only** is good when expressing expected business rejections with structured data; the caller **must** inspect the result status.
- **Result object without rollback** fits when a failure is reported yet prior DB operations **are intentionally allowed to commit** (e.g., recording a business audit entry); do not treat every error result as an implicit rollback.

Do not rely on Spring 6.1+ handling certain special return value types for **declarative `@Transactional` interception** and assume `TransactionTemplate` has a similar policy for custom callback results. The two mechanisms have different handling paths; with the template, decide rollback explicitly via exceptions or `TransactionStatus`.

## 11. `TransactionTemplate` and Exceptions in Nested Transactions

### 11.1. Default `PROPAGATION_REQUIRED`

By default, `TransactionTemplate` has `PROPAGATION_REQUIRED`:

- If no transaction exists for the same manager/resource, it opens a new one.
- If a valid transaction already exists, it **joins** that physical transaction.
- If the inner scope marks rollback-only or throws an error not isolated from the outer transaction, the outer processing may ultimately roll back the entire transaction.

Conceptual example:

```java
TransactionTemplate outer = new TransactionTemplate(manager);
TransactionTemplate inner = new TransactionTemplate(manager);

outer.executeWithoutResult(outerStatus -> {
    insertOuterRow();

    try {
        inner.executeWithoutResult(innerStatus -> {
            insertInnerRow(); // Joins the same physical transaction A.
            throw new IllegalStateException("inner invalid");
        });
    } catch (IllegalStateException expected) {
        // Inner requested rollback. Because inner joined A,
        // A may already be marked rollback-only.
    }

    insertAnotherOuterRow();
    // May encounter UnexpectedRollbackException when outer attempts to commit.
});
```

This is an **illustrative snippet**; `manager`, `insertOuterRow`, etc. are undefined. With managers based on `AbstractPlatformTransactionManager` that mark global rollback-only by default when a participating transaction fails, outer cannot commit successfully just by swallowing the exception. `UnexpectedRollbackException` signals that the physical transaction could not be committed as the caller expected.

### 11.2. `PROPAGATION_REQUIRES_NEW`

If inner must commit/roll back independently, you can use:

```java
TransactionTemplate independent = new TransactionTemplate(manager);
independent.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
```

In this snippet, importing `TransactionDefinition` and having `manager` are required. When outer A is open, Spring suspends A and creates transaction B; B completes and then A resumes. Inner B failing and being caught in outer **does not automatically** mark A rollback-only, though if an unchecked exception keeps escaping the outer callback then A can still roll back.

**Trade-offs:** B usually needs its own connection and can commit even when A rolls back, introducing connection pool/lock risks or business inconsistency. Do not use `REQUIRES_NEW` merely to avoid understanding exception handling.

### 11.3. `PROPAGATION_NESTED` or Savepoints

When wanting **partial rollback** inside one JDBC physical transaction, `PROPAGATION_NESTED` can use savepoints if supported by the transaction manager/driver. It differs from `REQUIRES_NEW` because it does not physically commit independently: an outer full rollback still discards inner work that previously succeeded.

`TransactionStatus` also extends `SavepointManager`, allowing explicit `createSavepoint()`, `rollbackToSavepoint(...)`, and `releaseSavepoint(...)` when supported. This is an **intentional alternative strategy**, not the default behavior of `execute`.

## 12. Common Programming Mistakes When Returning and Catching Exceptions

| Mistake | Consequence | Fix |
|---|---|---|
| `catch (Exception ignored)` inside callback then returning `"SUCCESS"` | Transaction may commit despite business failure | Catch only recoverable errors, rethrow, or `setRollbackOnly()` |
| Returning DTO `success=false` without marking rollback | Earlier data may commit | Define clear result contract and rollback policy |
| `status.setRollbackOnly()` then returning `"COMMITTED"` | Caller is misled since rollback may happen | Return `notSaved`/`rejected` or throw |
| Catching exception outside `execute` and assuming rollback definitely succeeded | Rollback can fail; commit outcome is sometimes uncertain | Check `TransactionException`/cause and idempotency before retrying |
| Returning JPA lazy entity/stream to process outside callback | Transaction closes, lazy access may fail or run out of scope | Materialize DTO inside callback |
| Returning `null` into a primitive variable | `NullPointerException` after transaction | Use nullable type/Optional and null checks |
| Putting `try/catch` in caller while sending email inside callback | Email already sent even if DB rolls back | Use outbox or proper after-commit hook |
| Thinking returning `CompletableFuture` from callback keeps transaction open until Future finishes | Transaction ends when callback returns; async code runs out of scope | Manage transactions inside the executing worker; do not pass status/thread-bound resources |
| Using `status` after callback returns or from another thread | Status/resource is no longer in a valid scope | Use only synchronously inside the callback |
| Using inner `REQUIRED` `TransactionTemplate` thinking it commits independently | Outer rollback can discard everything; `UnexpectedRollbackException` | Understand physical boundaries, choose right propagation |
| Running callback with datasource A's manager while SQL uses datasource B | SQL B may sit outside A's transaction | Specify matching manager/resource and test multi-datasource behavior |
| Calling `TransactionAspectSupport.currentTransactionStatus()` inside a template callback with no AOP invocation | May throw `NoTransactionException` | Use `status` passed into the callback |
| Letting a checked exception leave the lambda directly | Java compile error | Catch and wrap unchecked or return result + rollback-only |
| Automatically repeating callback after commit failure without idempotency | Can write duplicates when outcome is uncertain | Idempotency keys, controlled retries, reconciliation |
| Thinking `executeWithoutResult` is async | Wrong timing assumptions or wrong cleanup assumptions | Understand it is synchronous; simply returns no object |
| Manually calling `commit()`/`rollback()` on a JDBC connection inside the template | Corrupts transaction manager and connection lifecycle | Let Spring manage it; use `status` to request rollback |

## 13. Testing and Diagnostics in Real Projects

### 13.1. Integration Tests Must Check Both Return Values and the DB

A unit test mocking the callback can verify that Java returns a DTO, but does not prove transaction commit/rollback. For critical logic, run integration tests against a real DB or Testcontainers:

1. Start from data in a clear state.
2. Call the service using `TransactionTemplate.execute`.
3. Assert the return value or exception at the caller.
4. After the physical transaction completes, use another transaction/connection to query committed data.
5. Also test errors caught inside the callback, `setRollbackOnly()`, constraint errors, simulated commit errors, joining an outer transaction, and rollback-only propagation.
6. If retries are needed, test idempotency when the callback has non-DB side effects.
7. Monitor `DataAccessException` and `TransactionException` from the manager, not just business-layer exception classes.

### 13.2. Inspecting Status Inside the Callback

```java
String info = template.execute(status -> {
    boolean newTx = status.isNewTransaction();
    boolean rollbackOnly = status.isRollbackOnly();
    boolean actualTx =
        TransactionSynchronizationManager.isActualTransactionActive();

    return "new=" + newTx +
        ", marked=" + rollbackOnly +
        ", active=" + actualTx;
});
```

This is a snippet requiring importing `TransactionSynchronizationManager`. With a JDBC transaction manager and a callback opening a new physical transaction, you normally see `new=true, marked=false, active=true`. However, do not use `isActualTransactionActive()` as proof of commit: that flag only describes the current thread-bound state, not completion outcome.

### 13.3. Useful Logging

You can enable DEBUG for:

```text
org.springframework.transaction
org.springframework.jdbc.datasource
```

Use logging to observe begin, participating, commit, rollback, suspend/resume, and exceptions. Depending on the Spring version/manager, messages may vary. In production, avoid logging PII and sensitive SQL parameters. Always verify actual DB state after completion rather than inferring from a single "commit requested" line.

### 13.4. `TransactionOperations` Improves Testability

`TransactionTemplate` implements `TransactionOperations`. In services, you can inject the interface:

```java
public final class OrderWriter {
    private final TransactionOperations transactions;
    private final OrderRepository orders;

    public OrderWriter(
            TransactionOperations transactions,
            OrderRepository orders) {
        this.transactions = transactions;
        this.orders = orders;
    }

    public String save(String input) {
        return transactions.execute(status -> orders.insert(input));
    }
}
```

This is an illustrative class requiring `OrderRepository` and a configured `TransactionOperations` bean (which can be a `TransactionTemplate`). Interface-based design makes it easy to swap in mocks/stubs in unit tests; however, **integration tests** are still needed to verify real rollback/commit. Do not replace database tests with mocks for all transactionally constrained business logic.

## 14. Choosing an Appropriate Error-Handling Pattern

**Pattern A — exception is failure, caller handles via catch**

```java
try {
    Receipt receipt = template.execute(status -> {
        return writeAndBuildReceipt();
    });
    return HttpResult.success(receipt);
} catch (BusinessRuntimeException ex) {
    return HttpResult.rejected(ex.getMessage());
}
```

Snippet: `Receipt`, `HttpResult`, `BusinessRuntimeException`, and `writeAndBuildReceipt` are defined by the application. Suitable when failure is exceptional (not a routine outcome) and you want the transaction to roll back naturally.

**Pattern B — business rejection is a structured result**

```java
record Outcome(boolean committed, String reason) {}

Outcome outcome = template.execute(status -> {
    if (!isValid()) {
        status.setRollbackOnly();
        return new Outcome(false, "validation failed");
    }
    writeData();
    return new Outcome(true, "accepted");
});
```

This is a snippet; `isValid`/`writeData` are undeclared. The word `committed` is only accurate when **the scope manages a new physical transaction and completion succeeds**. If the code can join an outer transaction, rename it to `accepted`/`savedInScope` so it does not claim a physical commit prematurely.

**Pattern C — operation with no result**

```java
template.executeWithoutResult(status -> {
    verifyPreconditions();
    performUpdates();
});
```

This is a snippet; failures must throw unchecked exceptions or mark rollback-only. Using `executeWithoutResult` makes the API clearly show that the business code produces no output.

**Pattern D — checked exception when reading an external resource**

```java
ImportOutcome outcome = template.execute(status -> {
    try {
        InputData input = readFromExternalResource();
        writeDb(input);
        return ImportOutcome.ok();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return ImportOutcome.failed("resource unavailable");
    }
});
```

This is a snippet with self-defined types/factories. Make sure handling when `writeDb` throws `DataAccessException` remains clear; only `IOException` is caught here.

**Every pattern must answer three questions:** (1) Who decides failure? (2) Does the whole transaction roll back, or only part of it? (3) Can the caller know **whether it has actually physically committed** at the moment it receives the result?

## 15. Self-Check Questions

1. **How does `execute` differ from `executeWithoutResult`?** — Both run synchronous transactions; `execute` returns `T`/`null`, while `executeWithoutResult` returns no value.
2. **What happens if a callback throws an unchecked exception outward?** — The template requests rollback, then propagates the exception (if rollback itself does not fail).
3. **If a callback catches an error and returns normally, does Spring know to roll back?** — Not automatically; without rollback-only, it may commit.
4. **Does `return null` mean rollback?** — No.
5. **If `status.setRollbackOnly()` is called and `"OK"` is returned, does it commit?** — In a normal new physical transaction, data rolls back yet the caller can still receive `"OK"`; such a return value is misleading.
6. **Can a callback directly throw `IOException` without catching it?** — Not under `TransactionCallback<T>`'s signature because it does not declare checked throws.
7. **Do checked exceptions always lead to commit in `TransactionTemplate` like default `@Transactional`?** — No. Checked exceptions must be handled inside the callback; if converted to unchecked or marked rollback-only, it rolls back.
8. **When a callback returns a `CompletableFuture`, does the transaction automatically wait for the future to complete?** — No. `TransactionTemplate` runs the callback synchronously and does not extend the transaction to asynchronous completion.
9. **When an inner `execute` joins transaction A, does its return value prove A committed?** — Not yet. A may still roll back afterward.
10. **If the callback succeeds yet commit fails, what happens to the caller?** — It does not receive a normal return; it receives a transaction error. The actual outcome must be evaluated before retrying.
11. **Why can sending a message inside a callback cause inconsistency?** — Broker/email side effects do not automatically roll back with the JDBC transaction if the DB commit fails.
12. **What should be verified in integration tests?** — Both the return value/exception and the data after physical transaction completion, via a separate DB connection if needed.

## 16. Summary

- Use `execute(TransactionCallback<T>)` when data needs to be returned; use `executeWithoutResult` when only an action is needed.
- `return` produces a **Java result**, not a DB guarantee. `null` does not roll back; `"SUCCESS"` does not replace checking transaction completion.
- Unchecked `RuntimeException`/`Error` escaping the callback → Spring rolls back and propagates the error in the normal flow.
- Catching an error **inside** the callback and swallowing it → may commit; if rollback is wanted, rethrow or call `status.setRollbackOnly()`.
- `setRollbackOnly()` in a new transaction can allow the callback to return a **business result** despite rolling back; when joining an outer transaction, account for rollback-only and `UnexpectedRollbackException`.
- Checked exceptions are not declared on `TransactionCallback<T>`: catch/convert to unchecked or catch + rollback-only + explicit result.
- `TransactionTemplate` manages **synchronous** transactions. Futures, lazy streams, and external side effects do not automatically follow a JDBC transaction.
- On commit/rollback errors, do not assume the transaction succeeded or retry blindly; check data and design for idempotency.

## References

- Spring Framework — Programmatic Transaction Management (`TransactionTemplate`, callbacks, rollback-only): https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.2 — `TransactionTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionOperations` (`executeWithoutResult`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework — `TransactionCallback<T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionCallback.html
- Spring Framework — `TransactionStatus` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `UnexpectedRollbackException` and transaction propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative rollback rules, for comparing checked/unchecked: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — `PlatformTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring Framework — `TransactionTemplate.java` source and how rollback/checked `Throwable` are handled: https://github.com/spring-projects/spring-framework/blob/v6.2.19/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java

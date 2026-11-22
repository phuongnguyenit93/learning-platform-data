# `SQLException`: cause, SQLState, and the `nextException` chain in Java JDBC

`java.sql.SQLException` is the **checked** exception that JDBC uses to report many kinds of failures in database operations: connection errors, SQL execution errors, data constraint violations, transaction failures, or issues reported by the JDBC driver. Unlike an ordinary `Exception` that only has a message/cause, `SQLException` also has an **SQLState**, a **vendor error code**, and an **additional `SQLException` chain** accessed via `getNextException()`.

Key takeaway of this lesson:

> An `SQLException` can simultaneously have a **cause**, a **nextException**, and **suppressed exceptions**. These are **three different relationships**. Reading `getCause()` alone is often not enough to understand all JDBC errors reported by the driver or cleanup operations.

Example:

~~~java
SQLException error = new SQLException(
        "Không thể hoàn tất giao dịch",
        "40001",
        1205,
        new java.io.IOException("socket read failed"));

error.setNextException(
        new SQLException("duplicate key", "23505", 1062));
~~~

This is an illustrative Java snippet in a scope where `java.sql.SQLException` is imported. `error` has:

- `getMessage()`: the message of the primary error, `"Không thể hoàn tất giao dịch"`.
- `getSQLState()`: the string `"40001"`, describing the class/condition according to the SQLState code system.
- `getErrorCode()`: the number `1205`, which is a **vendor-defined code**, not a generic Java error code.
- `getCause()`: the `IOException` object with the message `"socket read failed"`.
- `getNextException()`: **another `SQLException`** carrying SQLState `23505`, its own message, and its own code.

The codes above are **simulated data for learning purposes**; you cannot infer from a self-constructed example that every JDBC driver returns the same vendor code or the same chain structure.

## 1. Position of `SQLException` in the exception hierarchy

~~~text
java.lang.Object
└── java.lang.Throwable
    └── java.lang.Exception
        └── java.sql.SQLException
            ├── java.sql.SQLTransientException
            │   ├── java.sql.SQLTimeoutException
            │   ├── java.sql.SQLTransientConnectionException
            │   └── java.sql.SQLTransactionRollbackException
            ├── java.sql.SQLNonTransientException
            │   ├── java.sql.SQLIntegrityConstraintViolationException
            │   └── java.sql.SQLSyntaxErrorException
            ├── java.sql.SQLRecoverableException
            ├── java.sql.BatchUpdateException
            └── java.sql.SQLWarning
~~~

This is an **abbreviated** tree of representative branches, not an exhaustive list.

`SQLException extends Exception` and does not inherit from `RuntimeException`, so it is a **checked exception**. If a method calls a JDBC API that can throw `SQLException`, the code must catch or declare it according to checked exception rules:

~~~java
static int executeUpdate(java.sql.Statement statement, String sql)
        throws SQLException {
    return statement.executeUpdate(sql);
}
~~~

The snippet above is a valid Java method when `SQLException` is imported. Declaring `throws SQLException` only describes the possibility of an error; it **does not mean every call will fail**.

`SQLException` also implements `Iterable<Throwable>`, allowing you to iterate over related JDBC information using a `for-each` loop. This point is covered separately after clarifying the two link types: cause and next.

### What do the subclasses indicate?

- `SQLTransientException`: a group of errors where the operation **might** succeed if retried under appropriate conditions; it is not a guarantee that retrying is always safe.
- `SQLNonTransientException`: a group of errors where an identical retry is not expected to succeed without fixing the underlying cause.
- `SQLRecoverableException`: a group of errors that may require a recovery action, such as recreating the connection, before retrying.
- `SQLIntegrityConstraintViolationException`: an integrity constraint violation error.
- `SQLSyntaxErrorException`: an SQL syntax error or invalid access represented by the API/driver as a subclass.
- `SQLTimeoutException`: a subtype of `SQLTransientException` reporting a timeout according to the corresponding JDBC contract.

Not every driver classifies every issue the same way. **Read the subtype, SQLState, vendor code, and driver documentation** before automatically deciding to recover or retry.

## 2. Four main diagnostic pieces of information on an `SQLException`

Consider the constructor:

~~~java
SQLException e = new SQLException(
        "update failed", "23505", 1062);
~~~

The accessors:

| API | Return type | Meaning |
| --- | --- | --- |
| `e.getMessage()` | `String` | The exception's message (*reason*) |
| `e.getSQLState()` | `String` | The SQLState code if present |
| `e.getErrorCode()` | `int` | The database vendor-specific error code |
| `e.getCause()` | `Throwable` | The direct cause if present |
| `e.getNextException()` | `SQLException` | The next `SQLException` in the chain if present |
| `e.getSuppressed()` | `Throwable[]` | Secondary errors retained, usually during resource cleanup |

**`getMessage()` is not the SQLState.** A message like `"duplicate key"` is human-readable text; `23505` is a code with meaning according to a specific environment's SQLState convention. The vendor code `1062` belongs to yet another code system. Do not mix these three values into a single "generic error code".

### Values may be missing

~~~java
SQLException e = new SQLException("unknown failure");

System.out.println(e.getSQLState()); // null
System.out.println(e.getErrorCode()); // 0
System.out.println(e.getNextException()); // null
~~~

The default values in the example are properties of the constructor used; they **do not prove** that every `SQLException` with vendor code `0` has no issue. A driver may use `0` by its own convention; SQLState may be null when not provided.

Do not call `e.getSQLState().substring(0, 2)` before checking for null and length.

## 3. `getCause()`: `Throwable`-style cause relationship

`SQLException` inherits the cause mechanism from `Throwable`:

~~~java
java.io.IOException root =
        new java.io.IOException("TCP connection reset");

SQLException sqlError = new SQLException(
        "database request failed",
        "08006",
        0,
        root);

System.out.println(sqlError.getCause() == root);
// true
~~~

The cause here is the **`IOException` object itself**, not just a copy of the `getMessage()` string. The cause can be any subtype of `Throwable`, not necessarily an `SQLException`.

The relationship:

~~~text
SQLException: database request failed
    └── cause -> IOException: TCP connection reset
~~~

It explains "what did this JDBC failure originate from?". When wrapping passes through multiple layers:

~~~java
IllegalStateException serviceError =
        new IllegalStateException(
                "Không thể khởi động dịch vụ", sqlError);
~~~

the cause chain will be:

~~~text
IllegalStateException
    └── cause -> SQLException
                   └── cause -> IOException
~~~

A constructor accepting `cause` is the preferred choice when the class supports it. Merely copying `sqlError.getMessage()` into the wrapper message does **not** preserve the reference and stack trace of the cause.

### `getCause()` only accesses one link

If you want to know the deepest root error, you must traverse causes one by one. However, do not assume a custom `Throwable` traversal algorithm will never encounter an indirect cycle; a general-purpose error analysis utility should include cycle protection using **object identity**.

**Do not equate the "deepest cause" with the "only error that needs handling".** An `SQLException` in the middle of the chain still holds the SQLState and vendor code—data that the deepest `IOException` does not have.

## 4. `getNextException()`: JDBC's own chain

API:

~~~java
public SQLException getNextException()
public void setNextException(SQLException ex)
~~~

These are illustrative signatures. `getNextException()` returns the next linked `SQLException`; if there is none, it returns `null`. `setNextException(ex)` **appends the exception to the end of the chain**.

Example:

~~~java
SQLException first =
        new SQLException("batch failed", "40001", 10);
SQLException second =
        new SQLException("row rejected", "23505", 11);
SQLException third =
        new SQLException("statement timeout", "HYT00", 12);

first.setNextException(second);
first.setNextException(third);
~~~

Afterward:

~~~text
first
  └── nextException -> second
                          └── nextException -> third
                                                  └── null
~~~

Calling `first.setNextException(third)` **does not replace** the previously attached `second`. It appends `third` to the **end** of the chain.

### Why does JDBC need this chain?

A database operation can generate multiple pieces of error information, for example:

- The first statement fails and the driver returns additional diagnostics from the server.
- A batch of multiple statements encounters several issues that need to be presented together with a primary error.
- The driver and database provide a collection of errors with different SQLStates/vendor codes.

The `nextException` chain allows a primary JDBC error to **contain other `SQLException` instances**, each with its own message, SQLState, vendor code, and cause. However, **not every driver or every operation creates multiple elements**. A single-element chain (with no next) is a normal situation.

### How it differs from cause

`getNextException()` requires another `SQLException`; `getCause()` can be an `IOException`, `IllegalStateException`, or another `Throwable`. A single `SQLException` object can have **both** without any mandatory relationship between them.

## 5. How do cause, nextException, and suppressed differ?

These are three structures that should not be conflated.

~~~text
SQLException main: transaction failed
├── cause -> IOException: socket read failed
├── nextException -> SQLException: duplicate key
│                     └── nextException -> SQLException: timeout
└── suppressed[0] -> IOException: resource close failed
~~~

| Relationship | Data type | When is it formed? | Primary meaning |
| --- | --- | --- | --- |
| Cause | A `Throwable` or null | Constructor with cause, or valid `initCause` | Root/wrapped cause |
| Next exception | An `SQLException` or null per link | Driver or code calls `setNextException` | Linked JDBC diagnostics |
| Suppressed | Array `Throwable[]` | `addSuppressed`, or try-with-resources mechanism | Secondary errors that should not replace the primary error |

Suppose you write:

~~~java
SQLException primary =
        new SQLException("operation failed", "42000");
primary.setNextException(
        new SQLException("detail A", "23505"));
primary.addSuppressed(
        new java.io.IOException("close failed"));
~~~

At this point `primary.getCause()` can still be `null` even though both next and suppressed are present. Adding a next exception does **not** automatically create a cause; adding a suppressed exception does **not** automatically create a next exception.

**Remember:** if you only log `e.getMessage()`, you may miss all the remaining information; if you only read `e.getCause()`, you can still miss the JDBC errors sitting in `getNextException()`.

## 6. What is SQLState?

**SQLState** is a code string used to classify SQL conditions according to conventions such as X/Open and the SQL standard. The standard form is usually **five characters**: the first two characters describe the **class** (condition group), and the last three characters describe the **subclass** (specific condition).

~~~text
SQLState: 23505
          ^^---
          || └── subclass: 505
          └└── class: 23
~~~

The diagram above is just an illustration of splitting the string; to read it accurately in code:

~~~java
String state = "23505";
String sqlClass = state.substring(0, 2);    // "23"
String subclass = state.substring(2);       // "505"
~~~

Some common classes:

| First two characters | Reference condition class |
| --- | --- |
| `00` | Successful completion |
| `01` | Warning |
| `02` | No data |
| `08` | Connection exception |
| `22` | Data exception |
| `23` | Integrity constraint violation |
| `28` | Invalid authorization specification |
| `40` | Transaction rollback |
| `42` | Syntax error or access rule violation |

These classes are useful for **guidance**. Specific values and driver classification behavior must be checked against the database and JDBC driver documentation. Some codes such as `HYT00` follow driver/ODBC conventions and should not be forced into being interpreted as standard codes across every database.

### Commonly seen code examples

- `23505` is used by some database management systems for unique constraint violations.
- `40001` is often associated with transaction failure due to serialization or a corresponding rollback condition.
- `08001` often describes the client being unable to establish an SQL connection under the relevant convention.
- `42...` may suggest a syntax or access rule issue.

**Do not hard-code a "SQLState → action" mapping for all vendors** without checking the driver. For example, a connection error can occur **after** the server has already performed a write operation; blindly retrying could cause duplicate side effects.

## 7. `getErrorCode()` is a vendor code, not SQLState

~~~java
SQLException error =
        new SQLException("unique violation", "23505", 1062);

System.out.println(error.getSQLState());   // 23505
System.out.println(error.getErrorCode());  // 1062
~~~

`getErrorCode()` returns a vendor-determined `int`. The meaning of `1062` in a given database management system **cannot be inferred from the Java API alone**. Do not map all vendor codes into a single shared enum if the application supports multiple databases without designing a dedicated mapping.

The code `0` often appears when no vendor code is provided:

~~~java
SQLException e = new SQLException("message", "08001");
System.out.println(e.getErrorCode()); // 0
~~~

`0` is not definitive proof that the issue has no internal database error code; it is simply the integer returned by the API in that specific situation.

### Messages and error codes have different levels of stability

- `getMessage()`: human-readable text, which may vary by locale, version, and driver configuration.
- `getSQLState()`: a code following the SQLState system, which can help with grouping.
- `getErrorCode()`: a vendor code, which can only be interpreted accurately in the appropriate driver/database context.
- `SQLException` subclass: an additional signal about transient, integrity, or timeout nature.

When building monitoring or retry policies, you need to record **the proper fields**, rather than concatenating them into a single string and parsing it back.

## 8. `SQLException` constructors and initialized data

Important overloads in Java 17:

~~~java
new SQLException()
new SQLException(String reason)
new SQLException(String reason, String sqlState)
new SQLException(String reason, String sqlState, int vendorCode)
new SQLException(Throwable cause)
new SQLException(String reason, Throwable cause)
new SQLException(String reason, String sqlState, Throwable cause)
new SQLException(
        String reason,
        String sqlState,
        int vendorCode,
        Throwable cause)
~~~

The lines above are **illustrative signatures**; do not paste them verbatim into a method as executable expressions, because `reason`/`cause` are just parameter names in API notation.

**Constructors that accept `cause`** store the cause reference at creation time. With overloads that do not accept `cause`, the cause state is usually uninitialized, and `initCause(...)` can be called once under valid conditions. However, if you choose an overload **with a `cause` parameter**, the cause state is initialized even if you pass `null`: you cannot call `initCause` afterward to replace it.

Example:

~~~java
SQLException a = new SQLException("operation failed");
a.initCause(new java.io.IOException("network failed"));
// Succeeds: the constructor did not initialize cause.

SQLException b = new SQLException(
        "operation failed", "08001", 0, null);
b.initCause(new java.io.IOException("later"));
// Throws IllegalStateException: cause was already initialized with null.
~~~

This is a **counter-example snippet that causes a runtime error at the end**; do not run it without catching the exception if you want execution to continue.

### Constructor accepting only `cause`

~~~java
SQLException e = new SQLException(
        new java.io.IOException("socket closed"));
~~~

In the cause-only form, `reason` is typically generated from `cause.toString()`, meaning it may contain both the class name and the message of the cause. If you are translating errors at the JDBC layer, an overload accepting **reason + SQLState + vendor code + cause** usually expresses context much more clearly.

## 9. Iterating through all `nextException`s with a loop

A straightforward way to iterate:

~~~java
SQLException current = primary;
while (current != null) {
    System.out.println(
            current.getMessage() + " / " + current.getSQLState());
    current = current.getNextException();
}
~~~

The snippet assumes `primary` is already available. It reads **the primary error and all next exceptions** in sequence. Each link can carry a different SQLState/vendor code.

If you are writing a general-purpose logging utility that receives data from multiple sources, guard against a malformed next structure or an indirect cycle. A simple solution is to use a reference set:

~~~java
java.util.Set<SQLException> seen =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<SQLException, Boolean>());

for (SQLException current = primary;
        current != null && seen.add(current);
        current = current.getNextException()) {
    System.out.println(current.getMessage());
}
~~~

This is an illustrative snippet with `primary` already declared. `IdentityHashMap` distinguishes elements by **object identity** rather than `equals()`, which is appropriate when the question is "have we seen this exact object already?". With chains normally created by JDBC drivers, you don't need to intentionally construct cyclic chains; cycle detection is a defensive measure for diagnostic utilities.

### Should `setNextException` be called in business code?

Normally, **the JDBC driver or library** builds the diagnostic chain. Application code may use `setNextException` when organizing related JDBC error information itself, but should not turn it into a list of unrelated business errors or use it as a substitute for `cause` in standard exception chaining.

If you wrap `SQLException` at the service layer:

~~~java
throw new IllegalStateException(
        "Không thể lưu đơn hàng", sqlException);
~~~

then **keep the entire `sqlException` object as the cause**. That way, `getNextException()` on the JDBC object itself can still be read after accessing the cause.

## 10. `SQLException implements Iterable<Throwable>`

A lesser-known convenience: you can iterate over an `SQLException` using an enhanced `for` loop:

~~~java
for (Throwable detail : sqlException) {
    System.out.println(
            detail.getClass().getSimpleName()
                    + ": " + detail.getMessage());
}
~~~

This is an illustrative snippet with a variable `sqlException` of type `SQLException`.

`SQLException`'s iterator is designed to traverse chained `SQLException`s and **their corresponding causes** if present, not just the first exception. Because the element type is `Throwable`, an element may **not be an `SQLException`** (for example, an `IOException` serving as a cause). To read `getSQLState()`:

~~~java
for (Throwable detail : sqlException) {
    if (detail instanceof SQLException sql) {
        System.out.println(sql.getSQLState());
    }
}
~~~

Do not cast every iterator element directly to `SQLException`, because a cause may not belong to that class.

### The iterator differs from `getNextException()` in scope

- The `current = current.getNextException()` loop gives you **only the `SQLException` objects in the next chain**.
- `for (Throwable detail : sqlException)` can include **related causes as well**, according to the iterator contract.
- `getSuppressed()` remains a separate relationship; you should not assume suppressed exceptions are included in the iterator.

When writing a logging system with multiple branches, avoid **duplicate printing** of the same error if you use the iterator and then also traverse causes separately. Choose one clear strategy to preserve full information without duplicating every message.

## 11. Complete Java 17+ example without a database or JDBC driver

The following program **self-constructs** `SQLException`, `SQLTimeoutException`, and `IOException` objects. It does not connect to a database, so its output can be verified reliably and does not depend on any SQL dialect.

Save the file as **`SQLExceptionDiagnosticsDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransientException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class SQLExceptionDiagnosticsDemo {

    public static void main(String[] args) {
        SQLException main = sampleFailure();

        System.out.println("== primary ==");
        System.out.println("type="
                + main.getClass().getSimpleName());
        System.out.println("message=" + main.getMessage());
        System.out.println("SQLState=" + main.getSQLState());
        System.out.println("vendorCode=" + main.getErrorCode());
        System.out.println("category=" + category(main));

        System.out.println("== next chain ==");
        Set<SQLException> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<SQLException, Boolean>());
        SQLException current = main;
        int index = 0;
        while (current != null && seen.add(current)) {
            System.out.println(
                    "item" + index + "="
                            + current.getClass().getSimpleName()
                            + "|" + current.getSQLState()
                            + "|" + current.getErrorCode()
                            + "|" + current.getMessage());
            index++;
            current = current.getNextException();
        }
        System.out.println("chainCount=" + index);

        System.out.println("== distinct relationships ==");
        Throwable root = main.getCause();
        System.out.println("cause="
                + root.getClass().getSimpleName()
                + ": " + root.getMessage());
        System.out.println(
                "suppressedCount=" + main.getSuppressed().length);
        System.out.println(
                "suppressed0="
                        + main.getSuppressed()[0]
                                .getClass().getSimpleName()
                        + ": " + main.getSuppressed()[0].getMessage());
        System.out.println(
                "nextIsCause=" + (main.getNextException() == root));

        System.out.println("== classifications ==");
        System.out.println("firstNextCategory="
                + category(main.getNextException()));
        System.out.println("noStateCategory="
                + category(new SQLException("unknown")));
        System.out.println(
                "timeoutIsTransient="
                        + (main.getNextException()
                                   .getNextException()
                                instanceof SQLTransientException));

        System.out.println("== wrapped exception ==");
        IllegalStateException wrapped =
                new IllegalStateException(
                        "cannot save order", main);
        System.out.println(
                "wrapperCauseSame=" + (wrapped.getCause() == main));
        SQLException recovered = (SQLException) wrapped.getCause();
        System.out.println(
                "recoveredNextMessage="
                        + recovered.getNextException().getMessage());

        System.out.println("== try-with-resources ==");
        resourceFailure();
    }

    static SQLException sampleFailure() {
        IOException network =
                new IOException("socket read failed");

        SQLException primary = new SQLException(
                "transaction failed", "40001", 1205, network);

        primary.setNextException(new SQLException(
                "duplicate key", "23505", 1062));

        primary.setNextException(new SQLTimeoutException(
                "statement timed out", "HYT00", 0));

        primary.addSuppressed(
                new IOException("resource close failed"));

        return primary;
    }

    static String category(SQLException failure) {
        String state = failure.getSQLState();
        if (state == null || state.length() < 2) {
            return "unknown";
        }
        return switch (state.substring(0, 2)) {
            case "08" -> "connection";
            case "23" -> "integrity";
            case "40" -> "transaction";
            default -> "other";
        };
    }

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws SQLException {
            throw new SQLException("close failed", "HY000", 99);
        }
    }

    static void resourceFailure() {
        try (FailingResource ignored = new FailingResource()) {
            throw new SQLException("execute failed", "42000", 7);
        } catch (SQLException failure) {
            System.out.println("primaryMessage="
                    + failure.getMessage());
            System.out.println("primaryState="
                    + failure.getSQLState());
            System.out.println("suppressedLength="
                    + failure.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + failure.getSuppressed()[0].getMessage());
            System.out.println("next="
                    + failure.getNextException());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SQLExceptionDiagnosticsDemo.java
java SQLExceptionDiagnosticsDemo
~~~

**Exact expected stdout:**

~~~text
== primary ==
type=SQLException
message=transaction failed
SQLState=40001
vendorCode=1205
category=transaction
== next chain ==
item0=SQLException|40001|1205|transaction failed
item1=SQLException|23505|1062|duplicate key
item2=SQLTimeoutException|HYT00|0|statement timed out
chainCount=3
== distinct relationships ==
cause=IOException: socket read failed
suppressedCount=1
suppressed0=IOException: resource close failed
nextIsCause=false
== classifications ==
firstNextCategory=integrity
noStateCategory=unknown
timeoutIsTransient=true
== wrapped exception ==
wrapperCauseSame=true
recoveredNextMessage=duplicate key
== try-with-resources ==
primaryMessage=execute failed
primaryState=42000
suppressedLength=1
suppressedMessage=close failed
next=null
~~~

### Analysis of the primary section output

`sampleFailure()` constructs the first `SQLException` with a full reason, SQLState, vendor code, and cause. Because the object is `SQLException` itself, `getClass().getSimpleName()` returns `"SQLException"`. The `category` classifier only checks the **first two characters** of SQLState, so `"40001"` returns `"transaction"`.

The `category` function in the example is **a group-identification helper**, not a standard procedure for deciding retries. It does not check the vendor, connection state, or transaction side effects.

### Analysis of the next chain

The two `primary.setNextException(...)` calls produce the order:

1. Primary error `transaction failed`, SQLState `40001`, vendor code `1205`.
2. Next error `duplicate key`, SQLState `23505`, vendor code `1062`.
3. Final error `statement timed out`, SQLState `HYT00`, vendor code `0`.

The loop starts from `primary` itself, so `chainCount=3`. The identity check via `seen.add(current)` is a safeguard in case a chain is constructed abnormally; a normal example has no cycles.

### Analysis of cause and suppressed

`main.getCause()` returns `IOException("socket read failed")`. The first `nextException` entry is **another `SQLException`**, so `nextIsCause=false`. `main.getSuppressed()[0]` is a third `IOException("resource close failed")`, which does not become the cause or next.

### Analysis of the transient type

`SQLTimeoutException` is a subtype of `SQLTransientException` in JDK 17, so the `instanceof SQLTransientException` check returns `true`. This **does not automatically mean a write operation can be safely retried**: code must also consider idempotency, transaction state, timeouts, and the database contract.

### Analysis of wrapping

`IllegalStateException("cannot save order", main)` retains the `SQLException` itself as the cause, so all data on `main`, including the next chain, can be retrieved after casting to the verified type. If you only create `IllegalStateException(main.getMessage())`, the caller loses the object link to the SQLState and next chain via `getCause()`.

### Analysis of try-with-resources

The `try` body throws `SQLException("execute failed", "42000", 7)`. When exiting scope, `FailingResource.close()` throws another `SQLException("close failed", "HY000", 99)`. Java attaches the close error as a **suppressed exception** on the primary error.

Note: **the close error here is not automatically added to `nextException`**. `getNextException()` on the primary error remains `null`. This is an important distinction between the try-with-resources language mechanism and the JDBC error chain explicitly populated by the driver/API.

## 12. Practical example: logging a JDBC exception in full

With real JDBC, you typically catch `SQLException` at the database management boundary:

~~~java
try {
    statement.executeUpdate(sql);
} catch (SQLException e) {
    logSQLException(e);
    throw e;
}
~~~

This is an illustrative snippet inside a method that appropriately declares or catches checked `SQLException`; `statement` and `sql` are assumed to exist. You should not log at every layer if the error is propagated and logged multiple times.

A minimal logger:

~~~java
static void logSQLException(SQLException first) {
    for (SQLException e = first;
            e != null;
            e = e.getNextException()) {
        System.err.println(
                "SQLState=" + e.getSQLState()
                + ", vendorCode=" + e.getErrorCode()
                + ", message=" + e.getMessage());
        if (e.getCause() != null) {
            System.err.println(
                    "cause=" + e.getCause().getClass().getName());
        }
    }
}
~~~

This is an illustrative method that can be placed in a class with `SQLException` imported. A production logger should use an established logging library, structured data, redaction policies, and log limits rather than relying on `System.err` in all cases.

**Security:** the reason, cause, or SQL reported by the driver may contain table names, keys, input values, connection strings, or sensitive data. Do not send the raw full message, SQL text, or stack trace in public responses. You can display a safe application error code and attach a correlation ID for internal log lookup.

## 13. When wrapping `SQLException` in a service-layer exception

If a business module wants to hide JDBC technology from its public API, it can define a custom exception:

~~~java
public final class RepositoryFailure extends Exception {
    public RepositoryFailure(
            String message, SQLException cause) {
        super(message, cause);
    }
}
~~~

This is a standalone Java class if saved in `RepositoryFailure.java`. Callers do not need to depend directly on `SQLException` in the method signature; operators can still find the SQLState, vendor code, and next chain from the cause.

An example method:

~~~java
static void saveOrder(java.sql.Connection connection)
        throws RepositoryFailure {
    try (java.sql.Statement statement =
                 connection.createStatement()) {
        statement.executeUpdate(
                "UPDATE orders SET processed = 1 WHERE id = 42");
    } catch (SQLException cause) {
        throw new RepositoryFailure(
                "Không thể cập nhật trạng thái đơn hàng", cause);
    }
}
~~~

This is a valid Java method when `RepositoryFailure` and `SQLException` are defined/imported accordingly. The SQL in the example is only to demonstrate JDBC structure; there is no guarantee that an `orders` table exists in an actual database.

**Why keep `cause` intact?** When an original `SQLException` has a next chain, you should not merely copy `cause.getMessage()` into the custom exception. Keep **the `cause` object itself** so diagnostic layers can retrieve `getSQLState()` and `getNextException()` when needed.

### Should you also wrap the entire next chain into nested causes?

Usually **no**. `nextException` is a separate JDBC relationship; do not flatten it into a cause chain and lose the distinction. A custom wrapper that keeps the original `SQLException` already preserves the entire chain.

## 14. `SQLWarning`: a related JDBC exception with a different meaning

`java.sql.SQLWarning extends SQLException`, so it also carries a reason, SQLState, vendor code, and warning chain. However, in JDBC, warnings are typically **attached to a `Connection`, `Statement`, or `ResultSet`** and can be read via `getWarnings()` rather than always being thrown as an operation failure.

Illustrative example:

~~~java
SQLWarning warning = statement.getWarnings();
for (SQLWarning current = warning;
        current != null;
        current = current.getNextWarning()) {
    System.out.println(current.getMessage());
}
~~~

This is a code snippet in a scope where `statement` is of type `Statement` and `SQLWarning` is imported. `getNextWarning()` is the dedicated API for the warning chain.

**Do not infer that every `SQLException` is a warning** or that having SQLState class `01` means JDBC will necessarily throw an error. Warning codes and driver warning-reporting mechanisms should be read according to the specific API.

## 15. `BatchUpdateException` and additional information

When running a JDBC batch, an operation may fail and the API reports `BatchUpdateException`, which is a subclass of `SQLException`. In addition to the common diagnostic fields, it holds data about the batch update results:

~~~java
catch (java.sql.BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();
    System.out.println(counts.length);
}
~~~

This is an illustrative `catch` block that must sit inside a `try` block that can throw `BatchUpdateException`. There is also `getLargeUpdateCounts()` when `long` values are needed.

Key points:

- `getUpdateCounts()` does not replace `getNextException()`.
- A `BatchUpdateException` may hold subsequent `SQLException`s providing additional driver-specific diagnostics.
- The contents of the update counts array depend on JDBC driver behavior: a driver may stop after an error or continue processing part of the batch according to its contract.
- **Do not recover a transaction just by looking at a count**, because part of the data may have already been written.

If batch processing has multiple side effects, you must review transaction boundaries, rollback, autocommit, and the application's idempotency policy.

## 16. `SQLException`, transactions, and retry decisions

An error with SQLState class `40`, or subtype `SQLTransientException`, may suggest a potentially recoverable condition. However, retrying requires **many conditions beyond the exception type**.

Before retrying, verify:

1. **Is the operation idempotent?** Could resending the statement cause duplicate side effects?
2. **What is the transaction state?** Was it rolled back, committed, or is the commit outcome unknown?
3. **Is the connection still valid?** Do you need to acquire a new connection from the pool or re-establish the session?
4. **Do the driver and database recommend retrying for this code?** SQLState/vendor code is only a partial signal.
5. **Is there a retry/backoff limit?** Avoid creating an error loop that increases load.
6. **Is there a transaction spanning multiple calls?** Retrying individual statements may be wrong if the entire transaction must be re-executed.
7. **Is there an idempotency key or deduplication?** Especially important for write operations that may have succeeded before a timeout.
8. **Do you need to distinguish validation, authentication, and constraint violation errors?** These errors are generally not fixed by an identical retry.

Design counter-example:

~~~java
catch (SQLException e) {
    while (true) {
        executeAgain();
    }
}
~~~

This is an illustrative Java pseudocode snippet with a hypothetical `executeAgain()`: unbounded retries without error classification can overload the system or duplicate side effects. Do not use this in production.

**Principle:** exception type and SQLState assist with **classification**, while the retry decision is part of the **transaction contract and business correctness**.

## 17. JDBC resource cleanup and suppressed exceptions

JDBC objects such as `Connection`, `Statement`, and `ResultSet` implement `AutoCloseable` in modern APIs. Use try-with-resources when owning these resources:

~~~java
try (java.sql.Connection connection = dataSource.getConnection();
     java.sql.PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT name FROM users WHERE id = ?")) {
    statement.setLong(1, userId);
    try (java.sql.ResultSet results = statement.executeQuery()) {
        if (results.next()) {
            System.out.println(results.getString(1));
        }
    }
} catch (SQLException e) {
    // Handle/log/propagate according to policy.
}
~~~

This is an **illustrative snippet**: it requires `dataSource`, `userId`, a JDBC library, and an actual database. It is not a standalone program to run without configuring a driver.

When the `try` body has already thrown an `SQLException` and a resource's `close()` also throws an error, Java normally attaches the close error to **`getSuppressed()` of the primary exception**. Each suppressed throwable may itself be an `SQLException` with its own SQLState/vendor code.

This is **different** from `setNextException`: the JVM does not automatically add errors from `close()` to the JDBC next chain.

### A `close()` error can be the primary error

If the `try` body **completes normally** but `close()` throws `SQLException`, the close exception can be the **primary error thrown**, not a suppressed one. Therefore, when you see an `SQLException` related to closing a connection, do not assume it is always just a secondary error.

Inspect the actual structure: `getCause()`, `getSuppressed()`, and `getNextException()`.

## 18. Common design mistakes with `SQLException`

### 18.1. Printing only `getMessage()` and ignoring SQLState

The message may not be enough to classify the error, especially when the driver has different codes for connection, constraint, or transaction issues.

### 18.2. Confusing `getNextException()` with `getCause()`

The next chain is a JDBC diagnostic list linking `SQLException`s. Cause is a `Throwable` causal link and can be an `IOException` or another error.

### 18.3. Assuming `getSuppressed()` is the next chain

False. Suppressed exceptions usually come from cleanup; they do not automatically become `nextException`.

### 18.4. Checking only the first `getNextException()`

A chain can have multiple links. Use a loop or the iterator according to contract when full information is needed.

### 18.5. Assuming every `SQLException` has an SQLState

No. `getSQLState()` can return null; classification code must handle null and non-standard strings.

### 18.6. Assuming the vendor code is the SQLState code

False. `getErrorCode()` is a vendor-specific integer; `getSQLState()` is a `String` following SQLState conventions.

### 18.7. Using the literal reason as a machine code

Do not parse `"duplicate key"` or messages that may be translated or changed across versions. Prefer verified SQLState/subtype/vendor code when branching.

### 18.8. Retrying every `SQLTransientException`

Even when an error is transient, a non-idempotent write operation may have already executed on the server. Check the transaction, side effects, and driver policy before retrying.

### 18.9. Retrying every class `23` error

Integrity constraint violations will not necessarily disappear on retry. You may need to fix the input data or handle the conflict.

### 18.10. Converting checked `SQLException` to unchecked while dropping the cause

If a module needs to wrap the error, pass the original `SQLException` to the wrapper constructor to preserve the cause and next chain.

### 18.11. Catching `Exception` and assuming every exception is a database error

An overly broad handler can swallow programming bugs. `catch(SQLException)` when handling JDBC usually expresses responsibility more clearly.

### 18.12. Confusing `SQLWarning` with an error that fails an operation

Warnings can be reported via `getWarnings()`. Not every warning is necessarily thrown out of a JDBC call.

### 18.13. Printing the full SQL statement and user parameters to logs

Logs can expose personal data, access codes, tokens, or sensitive values. Redaction and appropriate log access controls are required.

### 18.14. Ignoring `BatchUpdateException.getUpdateCounts()`

For batches, partial success/failure information can be critical for deciding rollback, recovery, or recording results.

### 18.15. Guessing the database name from a vendor code alone

A single number is not enough when a system has multiple drivers. You must know the database, driver version, and official mapping.

### 18.16. Creating a cyclic next chain yourself

`setNextException` is designed to append to the end of the chain. Do not link objects in a way that creates a cycle or reuse them across unrelated incidents, as this can cause issues for error-traversal utilities.

## 19. JDBC error diagnostic checklist

When you receive `SQLException e`, go through these steps in order:

1. **Record the exception type**: `e.getClass().getName()`, and any useful subtypes.
2. **Retrieve the reason/message** safely, without exposing sensitive information to clients.
3. **Read SQLState** and classify the group when the code is valid.
4. **Read the vendor code** with the corresponding database/driver information.
5. **Traverse the entire next chain** when diagnosing multiple errors.
6. **Traverse the cause** to find lower-level exceptions such as I/O or network errors.
7. **Check suppressed exceptions**, especially resource-closing errors.
8. **If it is a batch**, read the counts and transaction state.
9. **If there are warnings**, check `getWarnings()` using the appropriate API.
10. **Check transaction state/connection state** before deciding to retry.
11. **Use structured logging** and a correlation ID; avoid logging the same error at every layer.
12. **Do not treat stack traces or messages as a stable machine-readable protocol**.
13. **Define user-facing responses separately** from internal SQL details.
14. **Consult the JDBC driver and database documentation** for specific codes instead of guessing.

Not every application flow needs to perform all fourteen steps itself. This checklist is intended for the diagnostic/observability layer or when analyzing a difficult incident.

## 20. Self-check exercises

1. Is `SQLException` checked or unchecked? Why?
2. Does it sit under `Exception` or `RuntimeException`?
3. How do `getMessage()` and `getSQLState()` differ?
4. Is `getErrorCode()` a numeric form of SQLState?
5. Can `getSQLState()` be `null`?
6. What do the first two characters of SQLState usually represent?
7. What condition group does SQLState class `08` suggest?
8. What condition group does SQLState class `23` suggest?
9. Does `getCause()` always return an `SQLException`, or can it be another `Throwable` type?
10. Can `getNextException()` return an `IOException` directly?
11. Does calling `setNextException` twice on the first exception replace the previous element or append to it?
12. Why might a driver create multiple next exceptions?
13. How does `getSuppressed()` relate to try-with-resources?
14. Does an error from `close()` automatically turn into a `nextException`?
15. How is `SQLException implements Iterable<Throwable>` useful?
16. Why should you not cast every element of the iterator to `SQLException`?
17. Can you preserve both the cause and the next chain when wrapping an error in `IllegalStateException`?
18. If a wrapper only copies the message without passing the cause, what is lost?
19. Does `SQLTimeoutException` belong to `SQLTransientException`?
20. Can you immediately retry a write operation when encountering `SQLTransientException`?
21. Why should `23505` not be assumed to have the exact same meaning across every driver?
22. Does `getErrorCode()==0` prove there is no vendor error?
23. Which APIs can `SQLWarning` typically be retrieved from?
24. What additional information does `BatchUpdateException` provide?
25. When there is an error during `close`, why is it necessary to distinguish primary and suppressed?
26. Should a raw SQL/JDBC stack trace be returned to an HTTP client?
27. Why does a class `40` error require checking transaction state before retrying?
28. What abnormal situation should a general-purpose next-chain traversal utility guard against?
29. When handling multiple databases, what source is needed to understand vendor codes?
30. What are the three easily confused diagnostic relationships of `SQLException`?

### Suggested answers

1. Checked; it inherits from `Exception`, not `RuntimeException`.
2. `Exception`.
3. Message is human-readable text; SQLState is an SQL condition code.
4. No; it is a vendor-specific integer code.
5. Yes.
6. The SQL condition class/group.
7. Connection issues.
8. Integrity constraint violation.
9. Any `Throwable` or null.
10. No; the next value is of type `SQLException`.
11. Appends to the end of the chain.
12. To store additional JDBC diagnostic messages with their own codes and messages.
13. Resource-closing errors can be attached as suppressed exceptions to the primary error.
14. Not automatically.
15. Iterates through linked `SQLException`s and causes according to the iterator contract.
16. A cause can be an `IOException` or another `Throwable` type.
17. Yes, if you pass the `SQLException` itself as the wrapper's cause.
18. You lose the link to the original object, SQLState/vendor code, and next chain via the cause.
19. Yes.
20. Not automatically; you must consider idempotency, transaction state, and the driver contract.
21. Vendors and databases may use or extend code conventions differently.
22. No; you must check the specific driver's convention.
23. `Connection.getWarnings()`, `Statement.getWarnings()`, `ResultSet.getWarnings()`.
24. Batch counts via `getUpdateCounts()`/`getLargeUpdateCounts()`.
25. Errors in the `try` body and errors in `close` have different roles; `close` errors can be suppressed.
26. No; it can expose technical details and sensitive data.
27. Because a write operation may have had partial effects or the transaction may need a rollback.
28. Cyclic links or abnormal/malformed data structures.
29. Official documentation of the database and JDBC driver by version.
30. `cause`, `nextException`, and `suppressed exceptions`.

## 21. Key takeaways and API references

**`SQLException` provides more layers of information than an ordinary `Exception`.** Use `getMessage()` for the reason, `getSQLState()` for the SQL condition code, `getErrorCode()` for the vendor code; use `getCause()` to trace the underlying cause, `getNextException()` to read the JDBC diagnostic chain, and `getSuppressed()` to detect secondary errors during cleanup. They do not replace one another. `SQLException` is a checked exception; wrapping it into a higher-level error should **preserve the original cause object**. Do not make retry or business-error decisions based solely on a message or a single SQLState without considering the driver, connection, transaction, and idempotency.

Java 17 standard documentation:

- `SQLException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html
- `SQLTransientException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTransientException.html
- `SQLTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTimeoutException.html
- `SQLWarning`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLWarning.html
- `BatchUpdateException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html

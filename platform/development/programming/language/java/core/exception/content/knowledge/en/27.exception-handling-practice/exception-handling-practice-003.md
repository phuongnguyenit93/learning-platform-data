# Refactoring Multiple Identical catch Blocks into a Multi-catch in Java

> **Topic:** Java Core → Exception → Practice. A guide to refactoring multiple `catch` branches with similar handling into a **multi-catch** (`catch (TypeA | TypeB ex)`) introduced in Java 7, applicable in Java 17+. The goal is not only to reduce duplicate code, but also to **preserve behavior, handling policy, exception types, root causes, and diagnosability**. Includes a standalone before-and-after runnable program, exercises, JUnit 5 tests, and cases where you should not merge.

## 1. Identifying the Problem: Nearly Identical catch Blocks

A method may encounter multiple known exceptions that share the same handling policy:

~~~java
// Excerpt: fetchValue may throw IOException, SQLException.
try {
    return fetchValue();
} catch (IOException ex) {
    recordFailure(ex);
    return "fallback";
} catch (SQLException ex) {
    recordFailure(ex);
    return "fallback";
}
~~~

The two branches differ only in the **exception type**; both call the same recording function and return the same result. Duplicating the body can lead to one branch being updated while the other is forgotten—for example, adding a metric, log, or cleanup to only one branch.

Java allows combining them using the `|` operator **in the catch parameter declaration**:

~~~java
try {
    return fetchValue();
} catch (IOException | SQLException ex) {
    recordFailure(ex);
    return "fallback";
}
~~~

When either type is thrown from the `try` block, the same `catch` body runs. **This is not a bitwise OR or a logical OR on boolean values**: the `|` in this context combines alternative exception types. After refactoring, only one `catch` is selected for each handled exception; the two branches do not run sequentially.

**Necessary condition:** the exception types truly share the **same policy** at this boundary. Having the same body length or both calling `log.error` is not enough to prove identical semantics.

## 2. When Is Multi-catch Appropriate?

It is usually appropriate when:

- Two or more exceptions can be handled with the **same fallback value**.
- They are both translated into a higher-level exception **with the cause preserved**.
- They both lead to a task-termination state, such as failing fast at a boundary.
- They both need to record a diagnostic event with an operation/request ID, while preserving the original type via `ex.getClass()`.
- They are both propagated to the caller according to the `throws` signature.
- They share the same retry/backoff behavior, **and retry has been proven safe for both**.
- The `catch` body does not need to access methods that exist only on a specific subtype.

Example:

~~~java
// Excerpt inside an application method.
try {
    performOperation();
} catch (IOException | SQLException ex) {
    throw new DataAccessFailure("operation failed", ex);
}
~~~

`DataAccessFailure` is an application-defined class with a constructor accepting `String, Throwable`. `ex` remains the **actual exception object** that was thrown; `new DataAccessFailure(..., ex)` preserves the cause chain.

**Do not merge** if `IOException` is a non-retryable error while `SQLException` is a transient error that should be retried; or if `IOException` requires resource recovery while `SQLException` requires a separate transaction rollback. When policies differ, keeping separate `catch` blocks helps readers see the exact intent.

## 3. Correct Multi-catch Syntax

Basic syntax:

~~~java
try {
    riskyOperation();
} catch (IOException | SQLException ex) {
    handle(ex);
}
~~~

Rules:

1. Alternatives are separated by a single `|` inside the **same pair of parentheses** of `catch`.
2. There is only **one variable** at the end of the list, `ex` in this example.
3. The types must be valid exception types: subtypes of `Throwable`, obeying checked/unchecked rules and the possibility of the exception actually being thrown.
4. **No alternative may be a subtype of another alternative** in the same multi-catch; this is a compile-time error.
5. The `ex` variable in a multi-catch is **implicitly final**; it cannot be reassigned to another value.
6. Other `catch` blocks, if present, are still evaluated **from top to bottom**, following the rule that broader handlers come after narrower handlers.
7. Uncaught exceptions continue to propagate; multi-catch does not turn an exception into success.

Incorrect syntax:

~~~java
// WRONG: multiple variables are not allowed in a single catch.
catch (IOException io | SQLException sql) {
    // ...
}
~~~

Correct syntax:

~~~java
catch (IOException | SQLException ex) {
    // A single ex parameter.
}
~~~

The name `ex` is scoped to the `catch` body; it does not exist outside that body. You can use another name, such as `failure`, if it is clearer.

## 4. Two Compile-Time Conditions Often Overlooked

### 4.1. Types in the same multi-catch must not have a direct inheritance relationship

Invalid example:

~~~java
// WRONG: FileNotFoundException is a subclass of IOException.
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    // Compile error: alternatives related by subclassing.
}
~~~

Why? `IOException` already includes `FileNotFoundException`; adding the narrower alternative is redundant and makes the catch contract ambiguous. If the policy is truly identical, simply write:

~~~java
catch (java.io.IOException ex) {
    // Catches both FileNotFoundException and other IOExceptions.
}
~~~

However, **do not replace two unrelated exceptions with an overly broad superclass just for brevity**. For example, `catch (Exception ex)` can swallow unexpected runtime errors and `InterruptedException`. `IOException | SQLException` explicitly states the exact two error families you intend to handle.

### 4.2. The multi-catch variable cannot be reassigned

~~~java
// WRONG: ex is considered final in a multi-catch.
catch (IOException | SQLException ex) {
    ex = new IOException("replacement"); // Compile error.
}
~~~

Create a new variable for transformation, or construct the wrapper directly:

~~~java
catch (IOException | SQLException ex) {
    RuntimeException wrapped =
            new IllegalStateException("operation failed", ex);
    throw wrapped;
}
~~~

You should not overwrite the original exception and lose `cause`. Making the multi-catch variable final also helps keep clear which exception was actually caught.

## 5. The Type of the ex Variable Inside a Multi-catch Body

A common question: is `ex` an `IOException` or a `SQLException`?

At runtime, it still references the specific object that was thrown. At compile time, however, the methods that can be called directly on `ex` are determined by the **appropriate common supertype** of the alternatives. With `IOException | SQLException`, common `Throwable`/`Exception` operations like the following are all available:

~~~java
catch (IOException | SQLException ex) {
    String type = ex.getClass().getSimpleName();
    String message = ex.getMessage();
    Throwable cause = ex.getCause();
    // Call logger passing the full Throwable.
}
~~~

Conversely, `SQLException.getSQLState()` is not a method on `IOException`, so you cannot call `ex.getSQLState()` directly on that union variable.

If the policy truly needs the SQL state, keep two separate branches; or perform explicit type-based branching when it **only adds context without changing the outcome**:

~~~java
catch (IOException | SQLException ex) {
    if (ex instanceof SQLException sql) {
        recordSqlState(sql.getSQLState());
    }
    recordFailure(ex);
    throw new DataAccessFailure("operation failed", ex);
}
~~~

This is an excerpt inside a class that defines `recordSqlState`, `recordFailure`, and `DataAccessFailure`. Java 17 supports pattern matching for `instanceof`. If a `catch` block ends up with multiple `instanceof` checks with different handling paths, that is a sign to reconsider merging: two separate `catch` blocks may be clearer.

## 6. Complete Java 17 Example: Before and After Refactoring

The program intentionally produces **two checked errors from different hierarchies**: `IOException` (file source) and `SQLException` (database source). Both must return the same fallback at the boundary under consideration. The success branch keeps the previous result. It does not depend on a real file or database, so stdout is deterministic.

Save to **`MultiCatchRefactorDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;
import java.util.List;

public class MultiCatchRefactorDemo {
    static String fetch(String source) throws IOException, SQLException {
        if ("file".equals(source)) {
            throw new IOException("disk unavailable");
        }
        if ("db".equals(source)) {
            throw new SQLException("database unavailable");
        }
        return "ready";
    }

    static String fallback(Exception failure) {
        return "fallback(" + failure.getClass().getSimpleName()
                + ": " + failure.getMessage() + ")";
    }

    // Before refactoring: two identical catch bodies.
    static String before(String source) {
        try {
            return "value=" + fetch(source);
        } catch (IOException ex) {
            return fallback(ex);
        } catch (SQLException ex) {
            return fallback(ex);
        }
    }

    // After refactoring: merge the exact two error families sharing the same policy.
    static String after(String source) {
        try {
            return "value=" + fetch(source);
        } catch (IOException | SQLException ex) {
            return fallback(ex);
        }
    }

    // Multi-catch does not require swallowing or wrapping the exception.
    static void relay(String source) throws IOException, SQLException {
        try {
            fetch(source);
        } catch (IOException | SQLException ex) {
            throw ex;
        }
    }

    public static void main(String[] args) {
        for (String source : List.of("ok", "file", "db")) {
            System.out.println(source + ": before=" + before(source)
                    + " | after=" + after(source));
        }

        try {
            relay("file");
        } catch (IOException ex) {
            System.out.println("relay file: "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (SQLException ex) {
            throw new AssertionError("Unexpected SQL exception", ex);
        }

        try {
            relay("db");
        } catch (SQLException ex) {
            System.out.println("relay db: "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (IOException ex) {
            throw new AssertionError("Unexpected IO exception", ex);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac MultiCatchRefactorDemo.java
java MultiCatchRefactorDemo
~~~

**Exact stdout:**

~~~text
ok: before=value=ready | after=value=ready
file: before=fallback(IOException: disk unavailable) | after=fallback(IOException: disk unavailable)
db: before=fallback(SQLException: database unavailable) | after=fallback(SQLException: database unavailable)
relay file: IOException: disk unavailable
relay db: SQLException: database unavailable
~~~

### Analysis

1. `fetch("ok")` completes normally and both methods return `"value=ready"`.
2. `fetch("file")` throws `IOException`. `before` selects `catch IOException`; `after` selects the multi-catch. Both pass it to the same `fallback` helper and preserve the same type and message.
3. `fetch("db")` throws `SQLException`; the policy is the same as the file case.
4. `relay` demonstrates **rethrowing the original exception** from a multi-catch. The caller still catches `IOException` and `SQLException` separately.
5. `List.of` preserves the order of the three cases. There is no concurrency, timeout, or real I/O data, so output order is fixed.
6. In a real application, `fallback` might also update a metric and return a structured `Result`; returning a string like in the example is not required.
7. The program demonstrates **equivalence for the defined scenarios**, not a replacement for full regression testing in production code.

**Takeaway from the code:** collapsing catch branches does not change the runtime class of the exception. Merging is appropriate when the policies for the errors are the same, not merely because they are both checked exceptions.

## 7. Precise Rethrow: Rethrowing While Preserving the Checked Exception Contract

A major benefit of multi-catch is that rethrowing `ex` **does not force** you to declare an overly broad `throws Exception`. For example:

~~~java
// Excerpt from a class that defines fetch(String).
static void relay(String source) throws IOException, SQLException {
    try {
        fetch(source);
    } catch (IOException | SQLException ex) {
        throw ex;
    }
}
~~~

The compiler knows `ex` can only hold the types that the handler caught from `try`. The method can declare the exact `throws IOException, SQLException`; callers handle the two exceptions separately without having to catch all `Exception`.

This is **precise rethrow**, supported since Java 7, which relies on the compiler's exception-type analysis, especially when the catch parameter is not reassigned. Because a multi-catch parameter is implicitly final, code inside the catch block can never overwrite it.

Do not confuse the two forms:

~~~java
// Preserves the original exception object and stack trace.
throw ex;
~~~

and:

~~~java
// Creates a new exception; attach cause to preserve the trail.
throw new IllegalStateException("request failed", ex);
~~~

The second form changes the abstraction/contract: callers may see `IllegalStateException` instead of `IOException`/`SQLException`. Use it when the API intentionally translates a technical error into a domain or unchecked error, **not as an automatic step of multi-catch refactoring**.

### Does precise rethrow apply to a single catch?

Yes. Java 7's checked-exception analysis improvements are not limited to syntax with `|`. With a `catch (Exception ex)` whose parameter **is not reassigned**, the compiler can sometimes determine which checked exceptions can escape based on the `try` context. Still, using `catch (Exception)` to handle all errors can give an overly broad meaning: compiler acceptance does not mean a good runtime policy.

## 8. Handler Ordering and Reachability

Java tries `catch` blocks in the order they appear. Placing a broad handler first can make a subsequent handler **unreachable**, causing a compile-time error.

Incorrect example:

~~~java
// WRONG: catch(Exception) already includes IOException and SQLException.
try {
    fetch(source);
} catch (Exception ex) {
    handle(ex);
} catch (IOException | SQLException ex) {
    handle(ex);
}
~~~

Properly refactored code must ensure:

- A multi-catch of narrower/specific types is placed before a broader handler with different semantics.
- No alternative is a subtype of another alternative in the **same** list.
- Remaining handlers still handle other exception families according to their policies.
- Code inside `try` can throw the corresponding checked exceptions; do not add a checked alternative that the compiler knows has no throw path.
- Do not accidentally include `RuntimeException` or `Exception` as a catch-all for every failure.

Valid example:

~~~java
try {
    fetch(source);
} catch (IOException | SQLException ex) {
    recordExpectedInfrastructureFailure(ex);
} catch (RuntimeException unexpected) {
    reportProgrammingOrContractFailure(unexpected);
}
~~~

This is illustrative code using application-defined helpers. Not every `RuntimeException` is a bug, but this handler is kept separate because the runtime branch's **policy** differs from the two known checked types.

## 9. Do Not Merge If Two Policies Truly Differ

Suppose a system has the following logic:

~~~java
try {
    storeOrder();
} catch (IOException ex) {
    // I/O error while reading a local file: mark input unavailable.
    markInputUnavailable(ex);
} catch (SQLException ex) {
    // Transaction error: roll back and translate cause for DB retry policy.
    rollbackTransaction();
    throw new RepositoryFailure("database write failed", ex);
}
~~~

Merging this into:

~~~java
catch (IOException | SQLException ex) {
    log.warn("operation failed", ex);
}
~~~

is a **dangerous semantic change**: it loses the rollback, swallows the SQL error, flips the outcome, and can leave the system in an invalid state. Even if both original bodies shared a few logging lines, the differing parts carry business semantics and must be preserved.

A better approach is to extract only the shared part:

~~~java
try {
    storeOrder();
} catch (IOException ex) {
    recordCommonContext(ex);
    markInputUnavailable(ex);
} catch (SQLException ex) {
    recordCommonContext(ex);
    rollbackTransaction();
    throw new RepositoryFailure("database write failed", ex);
}
~~~

These are illustrative snippets that cannot run standalone because classes/helpers are omitted. When policies differ, sharing a small helper (`recordCommonContext`) is clearer than a multi-catch filled with `instanceof` checks.

**Signals to keep separate catch blocks:** different retry counts, different log levels, different transaction rollbacks, non-identical fallbacks, different return states, special timeout/cancellation handling, or needing to read subtype-specific APIs.

## 10. InterruptedException Requires Its Own Policy

A common mistake when merging exception types for convenience:

~~~java
// May compile depending on context, but is very likely wrong on policy.
try {
    blockingOperation();
    databaseOperation();
} catch (InterruptedException | SQLException ex) {
    log.warn("operation failed", ex);
    return;
}
~~~

The snippet above is illustrative, assuming `blockingOperation` throws `InterruptedException`, `databaseOperation` throws `SQLException`, and the method can `return`. The problem: `InterruptedException` signals that the **waiting thread** was interrupted. For many blocking APIs such as `Thread.sleep`, `Object.wait`, and `Thread.join`, the interrupt flag is cleared when the exception is thrown.

If the method cannot propagate `InterruptedException` (such as `Runnable.run()`), it typically needs `Thread.currentThread().interrupt()` before exiting. `SQLException`, on the other hand, has a completely different database handling policy. Merging both into a single handler without restoring the flag can break the cancellation protocol.

Keep them separate:

~~~java
try {
    blockingOperation();
    databaseOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (SQLException ex) {
    recordDatabaseFailure(ex);
    return;
}
~~~

An exception should only go into a multi-catch with `InterruptedException` if it **truly** shares the exact same interrupt policy and the application has proven it—a rare situation. Avoid ignoring thread state just because both branches end with `return`.

## 11. Preserving Cause, Stack Trace, and Suppressed Exceptions

Refactoring to multi-catch does not require creating a new exception. If the same error propagates at the right abstraction level, you can `throw ex` or let it propagate naturally. If crossing an abstraction boundary, wrap using a constructor that accepts `cause`:

~~~java
catch (IOException | SQLException ex) {
    throw new DataAccessFailure("unable to load order", ex);
}
~~~

Do not do this:

~~~java
catch (IOException | SQLException ex) {
    throw new IllegalStateException(ex.getMessage()); // Loses cause.
}
~~~

The second form makes it hard for callers to find the original stack trace and technical metadata. Besides `getCause()`, a `Throwable` also carries suppressed exceptions (commonly produced by `try-with-resources`). Multi-catch **does not lose** this data if you pass the original object properly. Do not just copy the message and discard the throwable.

### Try-with-resources still works

~~~java
// Illustrative excerpt, assuming an appropriately opened Connection connection.
try (java.sql.Connection c = connection) {
    writeData(c);
} catch (java.sql.SQLException | IllegalStateException ex) {
    reportFailure(ex);
}
~~~

This snippet is not standalone; `writeData`, `connection`, and `reportFailure` are provided by the application. `try-with-resources` is responsible for closing the resource per its contract; if both the try body and closing throw, the close exception may be attached to `getSuppressed()`. Merging catch blocks **does not turn a failure into a transaction rollback** and does not replace `commit`/`rollback` responsibilities in your DB architecture.

## 12. Logging: Merging Handlers Does Not Automatically Prevent Duplicate Logs

One code-level benefit of multi-catch is centralizing the logging policy for multiple error types:

~~~java
catch (IOException | SQLException ex) {
    log.error("event=order_load_failed operation={} orderId={}",
            operation, orderId, ex);
    throw new OrderLoadFailure("load failed", ex);
}
~~~

This example uses an SLF4J-style logger API; it requires a logger dependency and project-defined variables/classes. If an upper layer also logs the same stack trace and rethrows, **duplicate logs will still occur**, even though this layer uses multi-catch. Log ownership rules are independent of catch syntax:

- A layer that only translates errors: add context/cause and rethrow; it may not need an `ERROR` log locally.
- The layer that owns the final outcome: log one failure event with sufficient operation/request ID/business ID/Throwable.
- Retry/fallback/compensation are **separate events** that may need appropriate logs or metrics.
- Do not use an exception's message as a machine-readable error code.
- Distinguish severity and policy for `IOException`/`SQLException` if they are not truly identical.

If a multi-catch handler has 10 `if (ex instanceof ...)` statements just to pick a message or log level, the refactor may make the code harder to read than two simple catch blocks.

## 13. Do Not Merge Just Because catch Bodies Look Identical

Two blocks that look identical:

~~~java
catch (IOException ex) {
    retry(ex);
}
catch (SQLException ex) {
    retry(ex);
}
~~~

might call a `retry(ex)` helper that inspects the runtime type and applies different policies; you must read the helper's contract before concluding the refactor is safe. Equivalence is not just identical lines of text; it also includes:

- Do the callbacks/arguments passed have the same meaning?
- Are subtype fields (SQLState, file path, status) read elsewhere?
- Does either exception need to restore the interrupt flag?
- Are retry counts, delays, and idempotency the same?
- Is rollback/compensation needed before retrying?
- Are the log level and public error code the same?
- Which exception type will the caller see after the handler finishes?

If the same `handle(ex)` method branches internally by class, multi-catch may still be mechanically valid; however, a refactor should be judged by **clarity of the contract**, not just line count.

## 14. Step-by-Step Safe Refactoring in an IDE

A repeatable practical workflow:

1. **Isolate a try block:** inspect all possible exception sources and every existing catch block.
2. **Find identical catch bodies:** compare returns, throws, finally blocks, logging, cleanup, and mutated state.
3. **Confirm identical policy:** not just identical wording; identical outcome, retry, interrupt, and transaction semantics.
4. **Check type relationships:** exceptions joined by `|` must not be subtypes of one another.
5. **Check subtype-specific methods:** if the catch body uses `getSQLState()`, `getFile()`, etc., restructure or keep separate catch blocks.
6. **Replace with a multi-catch:** keep the body's exact semantics without arbitrarily changing the fallback or creating a different wrapper.
7. **Compile:** the compiler catches unreachable catches, related type alternatives, and reassignment of `ex`.
8. **Run unit tests:** include cases for each alternative and errors outside the list.
9. **Verify side effects:** cause, callback count, metrics, log count, rollback/retry.
10. **Evaluate readability:** if you have to add multiple `instanceof` checks, rollback policies, or casts, revert to separate catch blocks.
11. **Check binary/public contract:** internal refactoring does not necessarily change the API; if `throws` or public wrapper types change, review compatibility.
12. **Review the diff:** fewer lines is a side effect; the key invariant is unchanged behavior.

An IDE may suggest “Join multiple catch sections” or similar, but the developer must still evaluate the handling policy. A syntactically valid quick fix cannot replace domain understanding.

## 15. JUnit 5 Test Suite: Proving Before-and-After Behavior

The `before`, `after`, and `relay` methods in `MultiCatchRefactorDemo` have package-private visibility. If you place the following test class in the **same package**, it can call them directly for verification. This is **JUnit 5 code** and requires the JUnit dependency and test engine; it cannot run with plain JDK `javac` alone.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;

class MultiCatchRefactorDemoTest {
    @Test
    void sameResultForSuccessAndEachHandledException() {
        for (String source : new String[] {"ok", "file", "db"}) {
            assertEquals(MultiCatchRefactorDemo.before(source),
                    MultiCatchRefactorDemo.after(source), source);
        }
    }

    @Test
    void ioExceptionIsStillRethrownAsIoException() {
        IOException ex = assertThrows(IOException.class,
                () -> MultiCatchRefactorDemo.relay("file"));
        assertEquals("disk unavailable", ex.getMessage());
    }

    @Test
    void sqlExceptionIsStillRethrownAsSqlException() {
        SQLException ex = assertThrows(SQLException.class,
                () -> MultiCatchRefactorDemo.relay("db"));
        assertEquals("database unavailable", ex.getMessage());
    }

    @Test
    void successRemainsSuccessful() {
        assertDoesNotThrow(() -> MultiCatchRefactorDemo.relay("ok"));
        assertEquals("value=ready",
                MultiCatchRefactorDemo.after("ok"));
    }
}
~~~

Tests should distinguish:

- The before/after success paths **return the exact same value**.
- Each alternative has at least one dedicated test to detect if one type stops being caught.
- If the policy is rethrow, the caller still receives the **original type** and message/cause per the contract.
- If the policy wraps into a `DomainException`, verify `getCause()` and the error code, not just the wrapper type.
- If there are side effects, verify cleanup/transaction policies and ensure no unexpected logs or metrics are emitted.
- If the handler only returns a `fallback`, tests should verify that other programming errors still propagate rather than being swallowed by an overly broad catch.

The JUnit suite above verifies behavior on a minimal example. In a real project, you can use a fake/mock dependency to trigger each exact exception at the same point instead of touching a real file or database.

## 16. Testing Checked and Unchecked Exceptions Consistently

A call inside `try` can throw both declared checked exceptions and unexpected unchecked exceptions. If only `IOException` and `SQLException` were caught before refactoring, only **those exact two families** should be caught afterward.

Example:

~~~java
// Illustrative snippet.
try {
    fetch(source);
} catch (IOException | SQLException ex) {
    return fallback(ex);
}
~~~

If `fetch` hits a `NullPointerException` due to a bug, it does not automatically become a fallback. This is usually the desired behavior: do not turn a bug into a fake success result. If changed to:

~~~java
catch (Exception ex) {
    return fallback(ex);
}
~~~

the program could swallow a wide range of other `RuntimeException`s as well as checked exceptions outside the designed policy. Tests should include a case that throws `IllegalStateException` or `NullPointerException` through a fake dependency to ensure it still propagates.

**Do not throw a fake unchecked exception just to hit a checked catch branch.** Tests for `catch (IOException | SQLException ex)` must produce an actual `IOException` and an actual `SQLException`; a test that only throws `RuntimeException` does not exercise this handler.

## 17. Multi-catch and Polymorphism: When Is a Single Parent Catch Enough?

If all errors inherit from a base type designed for the domain:

~~~java
// Excerpt with base class DomainFailure.
catch (DomainFailure ex) {
    handleDomainFailure(ex);
}
~~~

this can be clearer than a list of a dozen subtypes. However, that is only true if **every subtype of DomainFailure** needs that policy, including new subtypes added later.

Using multi-catch:

~~~java
catch (ValidationFailure | ConflictFailure ex) {
    handleExpectedRejection(ex);
}
~~~

is more appropriate when only two subtypes have no direct inheritance relationship with each other and you do not want to catch other subtypes of the base class. These class names are illustrative and must be defined if used in a project.

Before choosing, ask: does the system need a policy for the **entire error family** or only **a specific set of errors**? A `catch (DomainFailure)` may become overly broad in the future when the system adds a subtype representing an infrastructure failure. Multi-catch expresses an intentional list of choices.

## 18. Impact on Performance and Maintainability

Multi-catch is primarily a **structural and maintainability improvement**. It may reduce duplicate bytecode/handler code in some situations, but you should not promise noticeable speedups or lower `Throwable` overhead just from turning two catches into one.

An exception is still constructed, thrown, and matched by the JVM; stack trace, logging, or I/O costs do not disappear because of `|`. If exceptions occur frequently as **normal control flow**, evaluate a dedicated result/condition design instead of just optimizing catch blocks. When errors are rare and catch blocks are identical, multi-catch makes code easier to review and reduces the risk of policies drifting apart.

Regarding maintainability:

- One place to update the shared handler.
- Easy to identify the set of exceptions intentionally recovered from.
- Reduces copy-pasted logging/wrapping code.
- Prevents adding an ID or cleanup in one branch while forgetting another.
- However, it can **reduce clarity** if the `|` list gets too long or the policies are only "sort of" similar.

You do not have to merge every catch block. Clear intent and preserved invariants matter more than a low line-of-code count.

## 19. Common Mistakes in Exercises

1. **Merging two subtypes with a parent–child relationship:** `FileNotFoundException | IOException` is invalid.
2. **Naming a variable for each alternative:** multi-catch has only one `ex`.
3. **Reassigning the `ex` parameter:** the variable in a multi-catch is implicitly final.
4. **Putting a parent handler first:** `catch(Exception)` before a narrower handler causes unreachable code.
5. **Replacing the list with `catch(Exception)` for convenience:** swallows unexpected errors.
6. **Merging based on syntax while ignoring policy:** retry, rollback, fallback, and cancel/interrupt may differ.
7. **Calling a subtype-specific method on the union parameter:** `getSQLState()` cannot be called directly when `ex` could be `IOException`.
8. **Wrapping the exception without the cause:** `new RuntimeException(ex.getMessage())` loses the root cause.
9. **Logging and throwing at every layer:** multi-catch does not automatically eliminate duplicate logs.
10. **Treating `InterruptedException` like any other error:** can lose the interrupt flag and prevent workers from stopping.
11. **Catching an exception that cannot be thrown from try:** the compiler may report that the checked exception is never thrown.
12. **Adding `return` to merge two catches:** accidentally turns a failure into success or skips a rollback.
13. **Assuming the compile-time type of ex is a specific subtype:** `ex` must be compatible with all alternatives.
14. **Rethrowing with a new wrapper without updating the API contract:** callers may see their catch behavior change.
15. **Testing only one alternative:** the other branch could be altered without anyone noticing.
16. **Assuming less code is always faster:** without benchmarks or performance evidence.
17. **Forgetting try-with-resources/suppressed exceptions:** handlers should preserve the full Throwable for diagnostics.
18. **Overusing `instanceof` inside multi-catch:** if most of the catch body branches back out, keep separate catch blocks.

## 20. Practice Exercises by Level

### Exercise A — Correctly Refactor Two Identical Branches

Given the code:

~~~java
try {
    export();
} catch (IOException ex) {
    markFailed(ex);
    return false;
} catch (SQLException ex) {
    markFailed(ex);
    return false;
}
~~~

Task: rewrite using multi-catch while preserving behavior. Solution:

~~~java
try {
    export();
} catch (IOException | SQLException ex) {
    markFailed(ex);
    return false;
}
~~~

This is an excerpt, not a complete program. Preconditions: `export()` can throw both checked types, `markFailed` accepts a common parameter such as `Exception`/`Throwable`, and it is designed for a shared policy.

### Exercise B — Spot the Invalid Code

~~~java
// WRONG: the two alternatives have a parent–child relationship.
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    return "failed";
}
~~~

Fix: if all `IOException`s share the same policy, use `catch (IOException ex)`; if you want to handle `FileNotFoundException` separately, place a narrower catch **before** the `IOException` catch and apply a different policy. These two alternatives cannot be placed in the same multi-catch.

### Exercise C — Preserve Checked Exceptions for the Caller

Merge two separate catch blocks that each have `throw ex`:

~~~java
static void load() throws IOException, SQLException {
    try {
        readFromSources();
    } catch (IOException | SQLException ex) {
        throw ex;
    }
}
~~~

This snippet requires `readFromSources()` to be appropriately defined. Verify that the compiler accepts `throws IOException, SQLException` and test that callers still catch each subtype accurately.

### Exercise D — Do Not Merge When Policies Differ

~~~java
catch (IOException ex) {
    useCachedValue();
} catch (SQLException ex) {
    rollbackTransaction();
    throw new StorageFailure("db failed", ex);
}
~~~

Answer: **keep the two branches separate**. Forcing them into a single multi-catch would require `instanceof` in the handler or produce the wrong outcome. You can extract a shared helper if there is truly identical work, without losing the differing behavior.

### Exercise E — Write a Test for a Third Error

Create a fake `fetch` that can throw `IllegalStateException` alongside `IOException`/`SQLException`. Verify that the multi-catch does not swallow `IllegalStateException`. If a refactor accidentally turns into `catch(Exception)`, the test must detect the contract violation.

## 21. Pre-Merge Checklist

- Did the two or more original catch blocks share the **same policy**, not just the same log statement?
- Are the exceptions valid alternatives with no subtype relationship between them?
- Can those checked exceptions actually be thrown from the `try` block?
- Does the `ex` variable avoid needing subtype-specific methods?
- Is the ordering of narrow/broad handlers preserved?
- Does `throw ex` or wrapping preserve the checked-exception contract and `cause`?
- Are `InterruptedException`, rollback, and cancellation handled specially?
- Are there any duplicate logs or unintended changes to severity/error codes?
- Are the fallback value, return/throw, resource state, and side effects identical to before?
- Do tests cover the success path and **each** alternative?
- Do tests prove that errors outside the alternative set are not swallowed?
- Is the refactored code easier to understand than the two original branches?

## 22. Summary

**Multi-catch** in Java lets you share one handler body across multiple exception types using `catch (A | B ex)`. It is a good choice when exceptions **have different types but truly share the same handling**. It eliminates duplication and clarifies the set of intentionally caught errors, while runtime exceptions retain their own type and cause.

In practice, keep five principles in mind: **verify the policy**, **follow subtype and catch-ordering rules**, **do not reassign the multi-catch parameter**, **preserve cause/precise rethrow**, and **test every error type before and after**. If policies differ or the handler body has to branch by type repeatedly, separate catch blocks are usually more accurate and maintainable.

### References

- [Java Language Specification §14.20 — The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20)
- [Java Language Specification §11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
- [Oracle — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/catch-multiple.html)
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html)
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html)

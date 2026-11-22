# Comparing Multi-Catch with an Overly Broad Parent-Type `catch` — Java Core Exception

> **Context:** Java Core → Multi-catch and rethrow. When multiple exception types require the same handling action, `catch (IOException | SQLException e)` usually expresses intent more clearly than `catch (Exception e)`. Both approaches can catch the same expected errors, but **their catch scope and consequences for unexpected errors are very different**. This lesson focuses on how to choose a handler, compilation rules, the multi-catch variable, rethrowing exceptions, and how to decide which handler is appropriate.

## 1. Quick Answer

Consider a call that can throw two types of checked exceptions:

```java
// Illustration inside a method; performOperation() can throw
// IOException or SQLException.
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException e) {
    reportFailure(e);
}
```

Compared to:

```java
try {
    performOperation();
} catch (Exception e) {
    reportFailure(e);
}
```

Both snippets are **illustrative**, because `performOperation()` and `reportFailure(e)` are not defined. Key differences:

- **Multi-catch:** catches only `IOException`, `SQLException`, **and their subclasses**. A programming error such as `NullPointerException` or `IllegalStateException` will not be swallowed by this handler and can propagate to a higher layer.
- **`catch (Exception)`:** also catches `IOException` and `SQLException`, but additionally catches **every subclass of `Exception`**, including most unchecked exceptions such as `NullPointerException`, `NumberFormatException`, and `IllegalStateException`.
- **Neither catches `Error` by default.** `Error` is a different branch of `Throwable`; writing `catch (Throwable)` has an even broader scope, which is usually inappropriate for normal applications.
- **Contract clarity:** multi-catch states the exact failure groups that the handler intends to handle in the same way. `catch (Exception)` does not tell the reader which error groups were considered.
- **Regarding checked exceptions:** Java has a **precise rethrow** rule; one should not say that `catch (Exception)` *always* forces declaring `throws Exception` when rethrowing. A later section provides an example to distinguish this accurately.

### 1.1. Comparison Table

| Criterion | `catch (IOException \| SQLException e)` | `catch (Exception e)` |
| --- | --- | --- |
| Scope by type | The two listed branches and their subtypes | The entire `Exception` hierarchy |
| Catches expected I/O errors | Yes | Yes |
| Catches expected SQL errors | Yes | Yes |
| Catches `NullPointerException` | No | **Yes** |
| Catches `IllegalStateException` | No | **Yes** |
| Catches `AssertionError` | No | No |
| Clearly expresses handling intent | Yes | Less clear |
| Can swallow unexpected programming errors | Less likely; errors outside the declared set propagate further | **Yes**, if the handler handles them generically/swallows errors |
| Can variable `e` be reassigned? | **No**; implicitly final | Can be reassigned syntactically, but loses some precise analysis benefits when rethrowing |
| Can it be rethrown? | Yes | Yes; see precise rethrow |
| When should it be used? | Specific exceptions that need the same logic | Application boundaries with a genuine general-purpose handling policy |

**Design takeaway:** choosing a handler should start from “which error types does this layer actually know how to handle?”, not “which one takes fewer characters to write?”.

## 2. Why Is Multi-Catch a Deliberate Choice?

Before Java 7, if two exception types needed the same logic, developers often duplicated code:

```java
try {
    work();
} catch (java.io.IOException e) {
    log(e);
    markFailed();
} catch (java.sql.SQLException e) {
    log(e);
    markFailed();
}
```

This is an illustrative snippet; the methods are not defined. The `log` and `markFailed` logic is duplicated. Since Java 7, multi-catch can be used:

```java
try {
    work();
} catch (java.io.IOException | java.sql.SQLException e) {
    log(e);
    markFailed();
}
```

The benefit is **combining identical handling without broadening the exception group**. Semantically, multi-catch is a concise way to express the same handling action applied to **multiple independent types**, rather than assuming every `Exception` can be handled the same way.

You should not replace two specific `catch` blocks with a single `catch (Exception)` just to avoid code duplication. A general-purpose handler changes the set of caught errors, not just the presentation.

### 2.1. Multi-Catch Is Not a Mechanism to Catch “All Exceptions”

Syntax:

```java
catch (TypeA | TypeB | TypeC e) {
    // Same handling action for each type.
}
```

`TypeA`, `TypeB`, `TypeC` must be valid exception types under the `Throwable` hierarchy and satisfy the language rules for multi-catch alternatives. The separator is a single **`|`**, not `||`. This is not a boolean check syntax like in an `if` statement.

When an exception is thrown, Java selects the multi-catch if the runtime object is compatible with **at least one** listed type. The handler runs **once**, not repeatedly for the number of alternatives.

### 2.2. Catch Scope Is Determined by Inheritance Relationships

```text
Throwable
├── Error
│   └── AssertionError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    ├── SQLException
    └── RuntimeException
        ├── IllegalStateException
        ├── NullPointerException
        └── IllegalArgumentException
            └── NumberFormatException
```

This tree shows only representative classes.

With `catch (IOException | SQLException e)`:

- `new FileNotFoundException(...)` is caught because it is a subtype of `IOException`.
- `new SQLException(...)` is caught directly.
- `new NumberFormatException(...)` is **not** caught because it lies under `RuntimeException`, outside the two selected branches.
- `new AssertionError(...)` is also not caught.

With `catch (Exception e)`, the first three cases are all caught (because `IOException`, `SQLException`, and `RuntimeException` are all subtypes of `Exception`). `AssertionError` is still not caught.

## 3. Java 17 Program: Visible Difference When a Programming Error Occurs

For a fair comparison, the following two methods call the **same** operation. The multi-catch handler only accepts the two expected infrastructure error types; the broad handler also catches state errors outside the handling plan.

Create the file `CatchScopeDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CatchScopeDemo {
    static void execute(String mode) throws IOException, SQLException {
        switch (mode) {
            case "io" -> throw new IOException("Nguồn đọc lỗi");
            case "db" -> throw new SQLException("Truy vấn lỗi");
            case "bug" -> throw new IllegalStateException("Trạng thái sai");
            default -> System.out.println("Thao tác thành công");
        }
    }

    static void targeted(String mode) {
        try {
            execute(mode);
        } catch (IOException | SQLException e) {
            System.out.println("multi: "
                    + e.getClass().getSimpleName());
        }
    }

    static void broad(String mode) {
        try {
            execute(mode);
        } catch (Exception e) {
            System.out.println("broad: "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        targeted("io");
        targeted("db");

        try {
            targeted("bug");
        } catch (IllegalStateException e) {
            System.out.println("caller: "
                    + e.getClass().getSimpleName());
        }

        broad("bug");
        targeted("ok");
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 CatchScopeDemo.java
java CatchScopeDemo
```

Stdout:

```text
multi: IOException
multi: SQLException
caller: IllegalStateException
broad: IllegalStateException
Thao tác thành công
```

Explanation:

1. `targeted("io")` throws `IOException`; the multi-catch catches it and prints `multi: IOException`.
2. `targeted("db")` throws `SQLException`; that handler also catches it because the second alternative is explicitly listed.
3. `targeted("bug")` throws unchecked `IllegalStateException`. It does **not** belong to `IOException` or `SQLException`, so it propagates to `main`, which has its own handler.
4. `broad("bug")` catches that same error with `catch (Exception)`. In this example we deliberately print it for observation; in a real system, if a broad handler marks it as “handled”, programming errors can be hidden.
5. `targeted("ok")` finishes normally and prints `Thao tác thành công`.

**This is the most important difference:** when the list of errors to handle is known, multi-catch typically preserves the distinction between “an error with a handling plan” and “an unexpected error that must propagate upward”. It does not automatically recover the system, but it avoids accidentally sweeping in branches that do not belong to the contract.

### 3.1. Distinguishing Unexpected Errors from Errors That Must Always Stop

Do not infer that every `RuntimeException` is a bug and never needs handling. `NumberFormatException` from user input can be caught at the UI layer to prompt for re-entry; `IllegalArgumentException` in business code can indicate a caller contract violation. The problem with `catch (Exception)` is that it **does not classify**: it catches both recoverable situations and bugs that the current layer does not know how to handle.

Conversely, do not claim that every checked `IOException` or `SQLException` is recoverable either. Catching an exception of the right type does not prove that data state is still valid, that a transaction has rolled back, or that an operation can be safely retried.

## 4. Compile-Time Constraints of Multi-Catch

A union such as `catch (IOException | SQLException ex)` requires alternatives that have no subtype relationship and checked exceptions that are valid for the throw paths of the `try` block. Two counterexamples:

```java
// Wrong: FileNotFoundException is a subtype of IOException.
catch (IOException | java.io.FileNotFoundException ex) {
    reportFailure(ex);
}
```

```java
// Wrong: parseInt does not throw checked IOException.
try {
    Integer.parseInt("abc");
} catch (java.io.IOException | NumberFormatException ex) {
    reportFailure(ex);
}
```

Both snippets only illustrate compilation errors, not standalone programs. For `parseInt`, catch `NumberFormatException` alone; for a parent–child pair, use `catch (IOException ex)` or separate handlers ordered child before parent. These syntactic constraints are worth checking, but the choice between **multi-catch or `catch (Exception)`** is even more important: should a general-purpose handler be allowed to **consume errors outside the expected scope**?

## 5. What Are the Characteristics of Variable `e` in Multi-Catch?

`catch (IOException | SQLException e)` declares **a single** exception reference variable, implicitly `final`. The static type of `e` is inferred as the **least upper bound** of the alternatives: you can use common methods like `getMessage()`, `getCause()`, and `printStackTrace()`, but you cannot directly call `SQLException.getSQLState()` without narrowing the type.

```java
catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println(e.getClass().getSimpleName());
    if (e instanceof java.sql.SQLException sql) {
        System.out.println(sql.getSQLState());
    }
}
```

This is an illustrative branch inside a valid `try` block. In a broad handler like `catch (Exception e)`, the static type is just `Exception`, and the runtime object does not change its type either. **The decisive difference between the two handlers lies in the set of errors caught**, not whether `getMessage()` can be called.

## 6. Multi-Catch and Rethrow: Declare Only Appropriate Checked Exceptions

Multi-catch can still **rethrow the exact object** it caught:

```java
static void forward() throws java.io.IOException, java.sql.SQLException {
    try {
        fetch();
    } catch (java.io.IOException | java.sql.SQLException e) {
        throw e;
    }
}
```

This is an illustrative method requiring `fetch()` to be defined and able to throw both checked exception types. If the caller needs to distinguish `IOException` and `SQLException`, `throw e` preserves the runtime type. However, the central advantage of the narrow handler in this lesson is **not accidentally catching a programming error like `IllegalStateException`**; that error continues to the monitoring boundary instead of being treated by a broad handler as a recovered infrastructure failure.

## 7. Subtlety: `catch (Exception)` Can Also Perform Precise Rethrow

It is **incorrect** to claim that `catch (Exception e) { throw e; }` always requires `throws Exception`. Java 7+ has **precise rethrow**: if `e` is an *effectively final* `catch` parameter and the compiler determines that the `try` block can only throw `IOException` and `SQLException` among the checked exceptions under consideration, those two types can suffice for the method signature:

```java
static void withBroadCatch()
        throws java.io.IOException, java.sql.SQLException {
    try {
        fetch();
    } catch (Exception e) {
        throw e;
    }
}
```

This is an illustration with `fetch()` declared as `throws IOException, SQLException`. **The types allowed in `throws`** and **the set of exceptions caught by the handler at runtime** are two different aspects. Multi-catch only catches the named branches; `catch (Exception)` also catches many unexpected `RuntimeException`s. If `e` is reassigned in a single-catch, precise rethrow capability can be lost. Therefore, choose the handler based on **recovery responsibility**, not on the false assumption that `catch (Exception)` always forces a wider signature.

## 8. When to Use Separate `catch` Blocks Instead of Multi-Catch?

Multi-catch should only group exception types when **the same handling strategy** is genuinely appropriate. If the remediation differs, separate handlers are clearer:

- `IOException`: might choose another data source or report that the file is unreadable.
- `SQLException`: might record a database access error, mark the task for transaction inspection, and decide to stop.
- `NumberFormatException`: might ask the user to fix the input string.

A multi-catch followed by branching with multiple `instanceof` checks can become a roundabout version of separate handlers.

### 8.1. Java 17 Program: Two Different Recovery Policies

Create `SeparateCatchPoliciesDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SeparateCatchPoliciesDemo {
    static String load(String source) throws IOException, SQLException {
        if ("file".equals(source)) {
            throw new IOException("Tệp tạm không đọc được");
        }
        if ("db".equals(source)) {
            throw new SQLException("Database không sẵn sàng");
        }
        return "Dữ liệu mới";
    }

    static void run(String source) {
        try {
            System.out.println("Kết quả: " + load(source));
        } catch (IOException e) {
            System.out.println("I/O: dùng bản sao lưu");
        } catch (SQLException e) {
            System.out.println("DB: dừng yêu cầu");
        }
    }

    public static void main(String[] args) {
        run("file");
        run("db");
        run("memory");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SeparateCatchPoliciesDemo.java
java SeparateCatchPoliciesDemo
```

Stdout:

```text
I/O: dùng bản sao lưu
DB: dừng yêu cầu
Kết quả: Dữ liệu mới
```

Here each exception requires **a different action**. Forcing both into a multi-catch and then checking `instanceof` inside the handler makes the code longer and harder to follow. `catch (Exception)` is even less suitable because it also accepts errors outside these two groups.

**Note:** the message “dùng bản sao lưu” only simulates a decision; the example does not contain a real backup implementation. In a real program, you must ensure the fallback actually has data and fits system consistency.

## 9. When Is `catch (Exception)` a Reasonable Choice?

Do not turn “always use multi-catch, never catch Exception” into an absolute rule. There are **high-level boundaries** whose primary purpose is to prevent one task's failure from breaking the orchestration flow of other tasks. For example:

- a job-processing worker, where each job has an independent state scope and is marked `FAILED` if an exception escapes;
- a CLI command that needs to turn unexpected exceptions into a general error message and a non-zero exit code;
- a request boundary with a mechanism to log and convert errors into an appropriate error response, while not treating a failed request as successful;
- a monitor that needs to collect diagnostics for any `Exception` escaping an operation.

In such cases, `catch (Exception)` can be appropriate **if there is a clear policy**: record/mark failure, clean up resources, do not reuse untrusted state, have monitoring, and do not swallow errors.

### 9.1. Java 17 Example: Catching Broadly at the Boundary and Reporting Failure

Save `BoundaryCatchDemo.java`:

```java
import java.io.IOException;

public class BoundaryCatchDemo {
    static void execute(String kind) throws IOException {
        switch (kind) {
            case "io" -> throw new IOException("Không thể đọc");
            case "bug" -> throw new IllegalStateException("Sai trạng thái");
            default -> System.out.println("Nội dung đã xử lý");
        }
    }

    static boolean runJob(String kind) {
        try {
            execute(kind);
            return true;
        } catch (Exception e) {
            System.out.println("Job thất bại: "
                    + e.getClass().getSimpleName());
            return false;
        }
    }

    public static void main(String[] args) {
        System.out.println("io success=" + runJob("io"));
        System.out.println("bug success=" + runJob("bug"));
        System.out.println("ok success=" + runJob("ok"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BoundaryCatchDemo.java
java BoundaryCatchDemo
```

Stdout:

```text
Job thất bại: IOException
io success=false
Job thất bại: IllegalStateException
bug success=false
Nội dung đã xử lý
ok success=true
```

Unlike a handler that swallows errors, `runJob` returns `false` to explicitly report the task failure. The example does **not** guarantee safety for all environments: work with side effects needs transactions/compensation if recovery is desired; multi-threaded tasks need synchronization; a real implementation also needs a logging policy and root-cause classification.

The deciding factor is **where the `catch` is placed**: `catch (Exception)` at a monitoring/orchestration boundary can be intentional, whereas `catch (Exception)` in every low-level method often hides errors that are not that method's responsibility.

### 9.2. Why Not Replace Everything with `catch (Throwable)`?

`Throwable` also includes the `Error` branch, such as `OutOfMemoryError`, `StackOverflowError`, `LinkageError`, and `AssertionError`. With many severe errors, the JVM/resource state may not allow safe continuation.

`catch (Exception)` does **not** catch `Error`. `catch (Throwable)` can catch it by type, but it does not make the JVM “never crash”. In normal applications, avoid using `catch (Throwable)` as a general recovery handler.

## 10. Anti-Pattern: Folding All Errors into “Handled Successfully”

Look at the illustrative snippet:

```java
try {
    saveOrder();
} catch (Exception ignored) {
    // Do nothing.
}
return true;
```

This is a non-standalone snippet; `saveOrder()` is not defined. The issue is that if an error occurs, the caller still receives `true`. The order might not have been saved, might have been partially saved, or might have performed side effects before the exception occurred.

In that case, `catch (Exception)` creates an illusion of success and **hides every root cause**. A multi-catch can also be wrong if handled like this. You need to design the contract first:

- If recoverable: perform a verifiable recovery measure, then return the correct result.
- If unrecoverable: return a structured failure, or rethrow/wrap the exception, preserving `cause`.
- If external state is indeterminate: use a status-check API, idempotency key, or appropriate transaction/compensation; do not infer “throwing an error means nothing was written”.

**Choosing the `catch` type does not create a rollback.** It only decides which exception objects enter the handler.

## 11. Handler Ordering When Combining Multi-Catch and Parent Types

You can place a multi-catch before a general handler:

```java
try {
    executeTask();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Lỗi nghiệp vụ hạ tầng đã dự kiến");
} catch (Exception e) {
    System.out.println("Lỗi không dự kiến");
}
```

The illustrative snippet assumes `executeTask()` can throw `IOException` and `SQLException`. This is a valid structure: the first handler catches the two listed types, and the second catches the remaining `Exception`s.

However, the reverse order is **invalid**:

```java
// INTENTIONALLY WRONG: the later multi-catch handler is already covered by Exception.
try {
    executeTask();
} catch (Exception e) {
    System.out.println("Rộng");
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Cụ thể");
}
```

Java rejects the unreachable handler because every `IOException`/`SQLException` is an `Exception` and will be intercepted by the first branch.

If you want to avoid a general handler, you can omit `catch (Exception)` and let unexpected errors propagate upward. This is often a good design in library/domain layers where there is insufficient context to fix all errors.

### 11.1. A Multi-Catch Does Not Allow “Prioritizing” One Type Inside It

`catch (IOException | SQLException e)` has **a single body**. Java does not run one half of the handler for `IOException` and the other half for `SQLException`. If there is genuinely different logic, separate `catch (IOException)` and `catch (SQLException)`; do not use a union catch to replace a switch on exception types.

## 12. Multi-Catch, Checked, and Unchecked: Choosing the Right Error Set

Example of a multi-catch combining checked and unchecked exceptions:

```java
try {
    parseFromFile();
} catch (java.io.IOException | NumberFormatException e) {
    System.out.println("Dữ liệu nguồn không hợp lệ");
}
```

This snippet is illustrative; `parseFromFile()` must actually be able to throw checked `IOException` in its signature/operation. In that case, the handler can be valid because the two types do not cover each other.

Still, before combining them, ask: do a file-reading error and a numeric-string error require the same action? If a parse error requires asking the user to fix the content, while an I/O error requires letting them choose another source, two separate handlers are more appropriate.

**There is no rule** such as “checked always needs multi-catch”, “unchecked always needs a parent catch”, or “each checked exception must have its own `catch`”. Java allows many arrangements; the choice must be based on handling capability, contract, and data integrity.

## 13. Designing a Shared Helper Instead of Broadening the Handler

If two handlers differ at the start but share a final step, multi-catch is not mandatory. You can extract a shared method:

```java
try {
    performOperation();
} catch (java.io.IOException e) {
    logFailure("I/O", e);
    recoverFile();
} catch (java.sql.SQLException e) {
    logFailure("SQL", e);
    haltDatabaseRequest();
}
```

This is an illustrative snippet depending on methods defined in the enclosing class. The two handlers have different policies while still sharing `logFailure(...)`. This approach is often clearer than a multi-catch containing `instanceof` branching.

For APIs that require closing resources, use try-with-resources where appropriate. No handler — whether multi-catch or parent catch — automatically creates cleanup/rollback mechanisms. If an exception occurs while closing a resource, you need to understand primary and suppressed exceptions rather than swallowing both.

## 14. Choices by Architectural Layer

| Layer | Example Task | Appropriate Tendency | Reason |
| --- | --- | --- | --- |
| Input parsing | Converting string to number | `catch (NumberFormatException)` | Can prompt to re-enter the exact field. |
| Storage reading layer | Reading files or querying SQL | Multi-catch if same policy, or two separate catches | Avoids accidentally handling `RuntimeException` bugs. |
| Business service | Creating orders, updating inventory | Specific business exceptions and clear state contracts | Caller needs to know the failure type and extent of state change. |
| CLI / request boundary | Returning user errors, marking request failed | `catch (Exception)` can be reasonable | Responsible for aggregating failures into a response/status. |
| Test framework / specialized runtime | Collecting task failures | Broad handler per framework policy | Must isolate, report, and not hide severe `Error`s. |

Do not apply this mechanically by layer name. A service might genuinely handle `Exception` broadly at a specific boundary, or a request handler might need to classify individual errors. What matters is having a **provable policy** for the caught errors.

## 15. Real-World Scenario: Why `catch (Exception)` Can Break a Contract

Suppose `saveInvoice()` promises that when an invoice cannot be created, the caller receives a clear failure. Inside the method, both `IOException`/`SQLException` and a `NullPointerException` bug can occur.

If you write:

```java
try {
    saveInvoice();
} catch (Exception e) {
    System.out.println("Không lưu được hóa đơn");
}
// Continue as if the invoice had been created.
sendConfirmation();
```

This is an illustrative, non-standalone snippet; the methods are not defined. This handler catches both infrastructure errors and bugs; moreover, **after the catch it still sends confirmation**, violating the contract. Replacing it with multi-catch reduces the scope of caught errors but **does not automatically fix** the problem of continuing after failure:

```java
try {
    saveInvoice();
} catch (java.io.IOException | java.sql.SQLException e) {
    throw new IllegalStateException("Không tạo được hóa đơn", e);
}
sendConfirmation();
```

The second pattern illustrates **not continuing the success path** when an infrastructure error occurs; the wrapper preserves `cause`. However, external side effects still need to be designed for: if the invoice was partially saved before the error, retrying the request could create duplicate records. Transactions, idempotency, state checks, and recovery are additional concerns.

**Lesson:** the catch selects the error scope; the handler body determines whether the handling honors the contract. Both must be evaluated.

## 16. Common Compilation Errors and Misconceptions

| Error / Misconception | Explanation and Fix |
| --- | --- |
| “Multi-catch is just a longer way to write `catch(Exception)`.” | False: multi-catch only covers the listed branches; it does not accept all `RuntimeException`s. |
| “`catch(Exception)` only catches checked exceptions.” | False: `RuntimeException extends Exception`, so this handler also catches many unchecked exceptions. |
| “Multi-catch also catches `Error` if the message name matches.” | False: handler selection is based on type inheritance, not on the message. |
| “You can write `IOException \| FileNotFoundException`.” | False: the two types have a subtype relationship; choose only the parent or use separate handlers. |
| “You can write `IOException \|\| SQLException`.” | Syntax error: multi-catch uses a single `\|`. |
| “Adding `IOException` to a multi-catch is always valid.” | False: a specific checked exception must match the throw possibilities of the `try` block. |
| “Multi-catch `e` can be reassigned like a regular variable.” | False: the multi-catch parameter is implicitly final. |
| “`e` in a union catch can directly call any `SQLException` method.” | False: only members valid for the common static type can be called directly. |
| “`catch(Exception)` rethrow always forces `throws Exception`.” | False when precise rethrow applies and the catch variable is not reassigned. |
| “Catching an error means it has rolled back.” | False: try/catch does not automatically undo prior side effects. |
| “Adding `catch(Throwable)` makes the program never crash.” | False: there are still VM/process errors and recovery is not guaranteed; it can also swallow `Error`s. |
| “One multi-catch is always better than two separate catches.” | False: when two error types require different handling, separate handlers express intent more accurately. |
| “Just logging in catch means the error is handled.” | Insufficient if failure status is not propagated or recovery does not occur. |
| “Within the same `try`, the later handler runs after the first handler.” | False: a propagating exception is handled by the first matching handler; sibling branches do not run sequentially. |

## 17. How to Test the Difference

A good test suite does not only assert log lines, but also asserts which errors **are handled** and which errors **are allowed to escape**.

With `CatchScopeDemo`, test:

1. Input `"io"`: multi-catch handles it and does not throw to `main`.
2. Input `"db"`: multi-catch handles it and does not throw to `main`.
3. Input `"bug"`: `targeted` lets `IllegalStateException` escape; the caller observes it.
4. Input `"bug"` with `broad`: `catch (Exception)` handles it and does not rethrow, even though the programming bug is not necessarily fixed.
5. Input `"ok"`: no handler is executed.

You can write a JUnit 5 test to verify this directly:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CatchScopeDemoTest {
    @Test
    void targetedLetsUnexpectedExceptionEscape() {
        assertThrows(IllegalStateException.class,
                () -> CatchScopeDemo.targeted("bug"));
    }

    @Test
    void broadSwallowsUnexpectedExceptionInThisDemo() {
        assertDoesNotThrow(() -> CatchScopeDemo.broad("bug"));
    }

    @Test
    void targetedHandlesExpectedCheckedExceptions() {
        assertDoesNotThrow(() -> CatchScopeDemo.targeted("io"));
        assertDoesNotThrow(() -> CatchScopeDemo.targeted("db"));
    }
}
```

**This is an illustrative test file**, requiring a project that already has JUnit Jupiter; it is not a standalone `javac` program. `CatchScopeDemo` and the test must be in compatible packages; for example, using the default package. The test result “`broad` does not throw outward” **does not prove `broad` is safe**, it only confirms the broad-catching behavior demonstrated by this program.

When testing a real project, you should also verify object state, written data, and task results, especially after an exception.

## 18. Practice Exercises

### Exercise 1 — Predict the Handler

A method declares `throws IOException, SQLException` and sometimes throws `IllegalArgumentException`. If the caller uses:

```java
try {
    call();
} catch (java.io.IOException | java.sql.SQLException e) {
    System.out.println("Đã dự kiến");
}
```

This illustrative snippet assumes `call()` exists. For `IllegalArgumentException`, does the handler run? **No.** That type lies under `RuntimeException`, not in the two listed checked branches.

### Exercise 2 — Fix an Invalid Multi-Catch

Why does `catch (IOException | FileNotFoundException e)` fail to compile? Write two fixed versions: (a) using only `catch (IOException e)` for a shared policy; (b) two separate handlers, `FileNotFoundException` before `IOException`, when different actions are needed.

### Exercise 3 — Can Variable `e` Be Reassigned?

Try adding `e = new IOException("another");` inside `catch (IOException | SQLException e)`. Explain the compiler error. Compare this with `catch (Exception e)` where reassignment is normally allowed, and why reassignment changes precise rethrow analysis.

### Exercise 4 — Common Static Type of a Union Catch

In `catch (IOException | SQLException e)`, calling `e.getMessage()` is valid, whereas `e.getErrorCode()` is not directly valid. Why? If you truly need the vendor error code from `SQLException`, how would a design with separate handlers be clearer?

### Exercise 5 — Precise Rethrow

Run `MultiCatchRethrowDemo`. Add a `forwardBroad` method using `catch (Exception e) { throw e; }` around `fetch(...)`. Verify that Java 17 can accept `throws IOException, SQLException` thanks to precise rethrow, provided `e` is not reassigned. Then try reassigning `e` and predict the compiler message.

### Exercise 6 — Choose a Handling Policy

A data-import application can encounter: missing file, SQL timeout, invalid numeric string, and `NullPointerException` due to a bug. Determine which layer actually handles each type, when to use multi-catch, when to use separate catches, and which boundary can catch broadly while still **explicitly reporting failure**.

### Exercise 7 — Evaluate the Contract

If a method has already written half the data and then throws `SQLException`, does replacing `catch (Exception)` with `catch (IOException | SQLException)` automatically restore the data? **No.** List the transaction or compensation mechanisms needed to restore state, and how the caller knows the operation failed.

## 19. Handler Selection Checklist Before Committing

- [ ] Do I know the exact **exception types that this layer can handle**?
- [ ] Do those types share the same handling action? If not, split into separate handlers.
- [ ] Do the multi-catch alternatives have a parent–child relationship that causes a compilation error?
- [ ] Does every checked alternative in the multi-catch actually have a source that can throw it from the `try` block?
- [ ] Does the handler accidentally catch an unexpected `RuntimeException` and hide a bug?
- [ ] Should I catch `Exception` at a monitoring boundary rather than in a low-level business layer?
- [ ] If catching broadly, is the result marked as a failure instead of faking success?
- [ ] If using `throw e;`, are the original object and diagnostic `cause` preserved?
- [ ] Am I distinguishing precise rethrow from runtime handler scope?
- [ ] Is the multi-catch variable `e` kept intact per the implicitly final rule?
- [ ] Are handlers in a valid order with no unreachable catch?
- [ ] Are resources and state cleaned up/rolled back via real mechanisms rather than assumptions when an exception occurs?
- [ ] Do tests cover both expected checked exceptions and unplanned unchecked exceptions?

**Conclusion:** **Multi-catch groups explicitly named exceptions when they require the same handling; `catch (Exception)` accepts the entire `Exception` hierarchy, including unplanned programming errors.** At application layers capable of specific handling, prefer a properly scoped handler; at monitoring boundaries, broad catching can be appropriate if it always reports failure and preserves diagnostics. Neither choice replaces state contract design, resource cleanup, and error-path testing.
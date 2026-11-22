# Exceptions Thrown Inside a Java `catch` Block

When a `catch` block is handling an exception, **the statements inside `catch` itself can still throw another exception**. An error may occur due to calling an I/O API, accessing a `null` reference, invalid data conversion, a logging operation, a failed recovery attempt, or the programmer explicitly executing `throw` on a new exception.

The most important point: **a new exception thrown inside a `catch` is not handled by sibling `catch` blocks of that same `try` construct**. Instead, it propagates outward—after executing the associated `finally` block (if any)—to look for a matching handler in an enclosing context or further up the call stack. If you want to handle the new error immediately, you need a nested `try/catch` inside the `catch` block.

This lesson distinguishes between the original exception, an exception thrown inside a handler, rethrowing, cause wrapping, and interaction with `finally`; it also shows how to prevent a secondary error from masking the initial failure. All complete programs run on JDK 17 or later.

## 1. How Does a `try` with Multiple `catch` Blocks Work?

A common structure:

~~~java
try {
    // Operation that may throw an error.
} catch (IllegalArgumentException ex) {
    // Handle IllegalArgumentException.
} catch (IllegalStateException ex) {
    // Handle IllegalStateException thrown in the try block.
} finally {
    // Necessary cleanup.
}
~~~

When an exception is thrown **inside the `try` body**, Java searches for the first compatible `catch` in the list. If the selected `catch` completes normally, the remaining `catch` blocks **do not execute** like `if` branches.

If a statement in the `catch (IllegalArgumentException)` branch throws an `IllegalStateException`, the adjacent `catch (IllegalStateException)` branch **does not catch that new error**, because the scope protected by both handlers is **the corresponding `try` block**, not the body of another handler.

This is the easiest point to misunderstand when reading a multi-`catch` structure: **sibling `catch` blocks are alternative error-handling choices for the same `try` block**, not a layered chain protecting one another.

Model:

~~~text
inner try
    |
    | throws IllegalArgumentException
    v
catch (IllegalArgumentException)  <-- selected
    |
    | handles error but throws new IllegalStateException
    v
finally of inner try (if present)
    |
    v
exits the entire inner try/catch/finally
    |
    +--> catch of enclosing try (if compatible)
    |
    +--> or continues propagating to the caller method

sibling catch (IllegalStateException): NOT selected for errors from sibling catch
~~~

Handler lookup depends on **the dynamic scope of the `try` enclosing the throw point** and the runtime type of the `Throwable` object. A `catch` does not implicitly create a hidden `try` protecting its own body.

## 2. Complete Java Example: A New Exception from `catch` Goes to an Enclosing `catch`

Save as `CatchThrowsDemo.java`:

~~~java
public class CatchThrowsDemo {
    static void execute() {
        try {
            try {
                System.out.println("1. Trong try");
                throw new IllegalArgumentException("đầu vào lỗi");
            } catch (IllegalArgumentException original) {
                System.out.println("2. Catch đầu: " + original.getMessage());
                throw new IllegalStateException("khôi phục thất bại", original);
            } catch (IllegalStateException sibling) {
                System.out.println("Không chạy: sibling catch");
            } finally {
                System.out.println("3. Finally bên trong");
            }
        } catch (IllegalStateException ex) {
            System.out.println("4. Catch ngoài: " + ex.getMessage());
            System.out.println("5. Nguyên nhân: " + ex.getCause().getMessage());
        }
        System.out.println("6. Tiếp tục");
    }

    public static void main(String[] args) {
        execute();
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CatchThrowsDemo.java
java CatchThrowsDemo
~~~

**Exact stdout:**

~~~text
1. Trong try
2. Catch đầu: đầu vào lỗi
3. Finally bên trong
4. Catch ngoài: khôi phục thất bại
5. Nguyên nhân: đầu vào lỗi
6. Tiếp tục
~~~

Order explanation:

1. The innermost `try` block throws `IllegalArgumentException`. Java selects the `catch (IllegalArgumentException original)` branch.
2. This branch prints line 2, then creates and throws `IllegalStateException`. The constructor receives `original` to preserve the original exception as the cause.
3. The `catch (IllegalStateException sibling)` branch of the **same construct** is not used to handle an exception from the previous branch, so `"Không chạy: sibling catch"` is never printed in this run.
4. Before exiting the inner construct, `finally` prints line 3. It completes normally, so the new exception continues propagating outward.
5. `catch (IllegalStateException ex)` of the enclosing `try` construct is selected. `ex.getCause()` returns the original `IllegalArgumentException`.
6. The outer `catch` completes normally, and the method continues to print line 6.

Two observations to remember: **a sibling branch does not handle errors from a handler**, and **`finally` lies on the outward propagation path**. Using the `(message, cause)` constructor preserves traceability to the initial error; this does not happen automatically if you throw a new exception without passing the cause.

## 3. Four Scenarios When Handling Errors in `catch`

Suppose an operation has thrown `original`, and the program is now inside `catch`.

| Behavior inside `catch` | Main outcome |
| --- | --- |
| Valid handling and normal completion | The error is handled; execution can continue after the `try/catch/finally` construct. |
| `throw original;` | Rethrows the **same exception object**; continues propagating outward. |
| `throw new IllegalStateException("...", original);` | Creates another exception and keeps `original` as `cause`; the outside receives the new exception. |
| An operation inside `catch` throws an exception on its own, e.g., `logger.write(...)` or `nullValue.length()` | The exception from that operation starts propagating outward; the original error may be masked if not saved as a cause or suppressed exception. |

A `catch` block can also `return`, `break`, or `continue` in valid contexts; like other exit paths, `finally` can affect the outcome. This topic becomes important when `finally` itself throws an error, which is explained in section 7.

**Object differences:**

~~~java
// Illustrative snippet inside a catch with variable original.
throw original;  // Same Throwable reference.
~~~

~~~java
// Illustrative snippet inside a catch with variable original.
throw new IllegalStateException("Không thể khôi phục", original);
// A new object, with cause linked to the original object.
~~~

~~~java
// Illustrative snippet inside a catch with variable original.
throw new IllegalStateException("Không thể khôi phục");
// A new object, but WITHOUT attaching the original cause.
~~~

The last approach is valid but can lose important information. Only omit `cause` intentionally when there is a clear design reason, such as avoiding exposing sensitive data at a public boundary; generally, you should preserve the original error for internal diagnostics.

## 4. Exceptions in `catch` Can Be Unintentional Errors

Not every exception inside a handler comes from an explicit `throw new`. Statements used to handle errors also carry the risk of failing:

~~~java
// Illustrative snippet: a secondary error occurs inside catch.
try {
    Integer.parseInt("abc");
} catch (NumberFormatException original) {
    String message = null;
    System.out.println(message.length()); // Throws NullPointerException.
}
~~~

In this example, the original `NumberFormatException` brought execution into `catch`, but the line `message.length()` throws `NullPointerException`. Without another `try` protecting this statement, the new exception propagates outward. Someone observing only `NullPointerException` at an upper layer might mistake it for the root cause, even though the first error was number parsing.

Common sources of secondary errors:

- **Logging:** a logger, formatter, `toString()` method, or log destination can fail due to bugs, resources, or I/O. Avoid constructing error messages using multiple error-prone operations.
- **Inspecting the error object:** calling `ex.getCause().getMessage()` when `getCause()` is `null` causes a `NullPointerException`. Never assume every `Throwable` has a cause.
- **Recovery:** reading a fallback copy, calling another service, or rolling back can throw an exception.
- **Manual cleanup:** closing streams, releasing resources, saving audit records, or calling `close()` in a handler can fail.
- **Transforming data for error display:** parsing JSON, extracting an exception message from an external system, re-encoding data, or formatting strings can cause a new error.

In design, **error-handling logic must be simple enough and have pre-planned failure paths**. If a secondary operation must not mask the primary error, protect that operation separately and keep the original exception for forwarding.

## 5. Using a Nested `try/catch` Inside `catch` Itself

You can handle a secondary error right inside `catch` by creating a new `try` construct within the handler's body. Only then can the inner handler catch an exception thrown by the secondary operation.

~~~java
// Illustrative code inside a method with an appropriate throws IOException,
// along with audit(Throwable) throws IOException.
try {
    performAction();
} catch (IllegalArgumentException original) {
    try {
        audit(original);
    } catch (IOException auditFailure) {
        original.addSuppressed(auditFailure);
    }
    throw original;
}
~~~

This is an **illustrative snippet depending on the `performAction` and `audit` methods**. Its meaning:

1. The initial `IllegalArgumentException` is caught by the outer handler.
2. `audit(original)` is a separate operation that can fail with I/O.
3. `catch (IOException auditFailure)` **is inside the new `try` construct**, so it catches the audit error where it occurs.
4. `addSuppressed` attaches the secondary error to `original`, allowing inspection via `getSuppressed()` if the object supports suppression.
5. `throw original` preserves the primary exception as it continues propagating outward.

`addSuppressed` is only appropriate when you want to preserve the primary error and treat the secondary error as an incidental failure during handling. Do not add `original` itself as its own suppressed exception; Java forbids self-suppression. Also, note that custom `Throwable` types may have suppression disabled.

For a recovery operation with independent significance, another option is to throw a new exception, **with `cause` from the original error**, to clearly report the failure in the recovery step. Which approach is right depends on responsibility boundaries and the error types the API expects callers to handle.

## 6. Checked Exceptions Thrown from `catch`: How Does the Compiler Check Them?

The Java compiler checks **checked** exceptions that can escape from a `catch` body, just as it does for other statements. If a handler throws `IOException`, you must either catch it in a suitable enclosing `try` construct or declare it in the `throws` clause of the enclosing method/constructor.

Complete program `CheckedCatchThrowsDemo.java`:

~~~java
import java.io.IOException;

public class CheckedCatchThrowsDemo {
    static void convert(String raw) throws IOException {
        try {
            Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IOException("không chuyển đổi được", ex);
        }
    }

    public static void main(String[] args) {
        try {
            convert("abc");
        } catch (IOException ex) {
            System.out.println("Đã xử lý: " + ex.getMessage());
            System.out.println("Cause: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CheckedCatchThrowsDemo.java
java CheckedCatchThrowsDemo
~~~

Exact output:

~~~text
Đã xử lý: không chuyển đổi được
Cause: NumberFormatException
~~~

Analysis:

- `Integer.parseInt("abc")` throws `NumberFormatException`, an unchecked exception.
- `catch (NumberFormatException ex)` catches that error, then creates and throws a new **checked** `IOException`.
- Because `IOException` escapes the `convert` method, its signature must declare `throws IOException`, or there must be appropriate handling in an enclosing layer.
- `main` catches `IOException` and reads `getCause()` to see the original `NumberFormatException`. There is no obligation to catch `NumberFormatException` just because it is the cause.

If you remove `throws IOException` from `convert`'s signature without adding a suitable handler, the program will fail to compile. You cannot solve this by writing a **sibling `catch (IOException)` below** `catch (NumberFormatException)`: the I/O error is created inside the handler, so it is not inside the `try` block protected by the sibling `catch`.

Another valid approach is to place the entire `try/catch` inside an outer `try`, and then `catch (IOException)` at the outer level. In that case, the exception is thrown **inside an actual `try` block** belonging to the outer level.

## 7. The Role of `finally` When `catch` Throws Another Exception

The `finally` block associated with a `try/catch` construct still executes when the `catch` block terminates abruptly due to `throw`.

There are two different scenarios:

- **`finally` completes normally:** the exception thrown from `catch` continues propagating outward.
- **`finally` itself terminates abruptly** (for example, throwing another exception or executing `return`): the exit reason of `catch` can be replaced, so the error just thrown from `catch` is no longer the outermost exception.

The program `FinallyMasksCatchDemo.java` demonstrates the second scenario:

~~~java
public class FinallyMasksCatchDemo {
    static void process() {
        try {
            try {
                throw new IllegalArgumentException("lỗi gốc");
            } catch (IllegalArgumentException ex) {
                throw new IllegalStateException("lỗi từ catch", ex);
            } finally {
                throw new UnsupportedOperationException("lỗi từ finally");
            }
        } catch (RuntimeException ex) {
            System.out.println("Bên ngoài: " + ex.getMessage());
            System.out.println("Cause null: " + (ex.getCause() == null));
        }
    }

    public static void main(String[] args) {
        process();
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinallyMasksCatchDemo.java
java FinallyMasksCatchDemo
~~~

Exact stdout:

~~~text
Bên ngoài: lỗi từ finally
Cause null: true
~~~

Explanation: `IllegalArgumentException("lỗi gốc")` directs execution into `catch`; the handler creates `IllegalStateException("lỗi từ catch", ex)`. However, `finally` throws `UnsupportedOperationException`. In this example, the final error received by the outer `catch` is the one from `finally`; it was created without a `cause`, so `getCause() == null`. Both earlier errors are masked from the outermost cause chain.

**Do not use this pattern in production code.** The goal here is only to observe the exit-order rules. Avoid arbitrary `throw` or `return` statements in `finally`. If cleanup work can fail, use a resource-management mechanism or handle it separately to preserve the primary error.

A `finally` block containing a `return` statement can also mask an in-flight exception. Therefore, `return` in `finally` is a common design mistake, even when there is no explicit `throw` there.

## 8. How Does `try-with-resources` Differ from Exceptions Thrown in `catch`?

`try-with-resources` is used for `AutoCloseable` resources and handles resource-closing errors specially. If both the **`try` body** and **`close()`** throw exceptions while exiting `try`, the closing error is normally added to `getSuppressed()` of the primary exception, helping preserve traces of both.

However, with a construct like:

~~~java
// Illustrative snippet with appropriate Resource and ErrorType declarations.
try (Resource resource = openResource()) {
    doWork(resource);
} catch (ErrorType original) {
    throw new IllegalStateException("Xử lý lỗi cũng thất bại", original);
}
~~~

The resource in `try-with-resources` has already been closed according to the construct's rules **before the corresponding `catch` handles the exception**. If a statement inside `catch` creates an additional `IllegalStateException`, Java does not automatically attach `ErrorType original` as a suppressed exception of the new error; here the programmer preserves the cause via the `original` parameter in the constructor.

Therefore, distinguish between:

- **Suppressed exceptions from resource closing:** represent secondary errors recorded when resources close in `try-with-resources`.
- **`Cause` from explicit error wrapping:** indicates that one exception is the cause leading to another, e.g., `new IllegalStateException("...", original)`.
- **Exceptions accidentally thrown by a handler:** can mask the original cause if the handling path is not carefully designed.

`Throwable.getCause()` and `Throwable.getSuppressed()` serve two different purposes. When debugging a complex error flow, inspect both.

## 9. Rethrowing the Same Exception and Preserving the Stack Trace

A `catch` branch can rethrow the caught object:

~~~java
// Illustrative snippet inside a method with throws IOException.
try {
    readFromDisk();
} catch (IOException ex) {
    System.err.println("Không đọc được tài nguyên");
    throw ex;
}
~~~

`throw ex;` **does not create a new object**, so it normally does not re-capture the stack trace at the `throw ex` site. A `Throwable`'s stack trace is normally recorded when the object is created or when `fillInStackTrace()` is called; if you simply rethrow the existing reference, the original trace can be preserved.

Meanwhile:

~~~java
// Illustrative snippet with IOException ex in catch.
throw new IllegalStateException("Lỗi đọc dữ liệu ứng dụng", ex);
~~~

creates a new exception at the handling layer; the new exception has its own stack trace, while `ex` is kept as the cause. When printing the full stack trace, there is usually a `Caused by:` chain to trace back to the source error.

Weigh the two approaches:

- **`throw ex`:** preserves the exception type and object identity; suitable when the current layer has no way to recover and does not need to change the contract.
- **Wrapping with a cause:** useful when the current layer wants to provide higher-level context or translate the error type. Do not wrap across multiple layers just to repeat the same message.
- **Not rethrowing:** only appropriate when `catch` has genuinely handled the error, has a valid fallback result, or intentionally transitions to a different error path with clear documentation.

When `ex` is a checked exception, follow the compiler's rules on rethrown exceptions and `throws` signatures. Java performs **precise rethrow** analysis in certain `catch` forms, but that does not turn an unchecked exception into a checked one or change the meaning of `throw ex;`.

## 10. Strategies for Preserving the Original Error When the Handler Also Fails

Ask the question: **which error reflects the primary failure the caller needs to know?** Then choose the appropriate propagation strategy.

### Case A: The new handling error should be reported, with the original error as its cause

~~~java
// Illustrative snippet inside a catch with variable original.
throw new IllegalStateException("Không thể khôi phục trạng thái", original);
~~~

The caller receives a new exception and can use `getCause()` to reach the source error. Suitable if the recovery attempt is the decisive failure step and the current layer is responsible for providing new context.

### Case B: The original error is primary; the audit/cleanup error is only secondary

~~~java
// Illustrative snippet inside a catch with variables original and auditingFailure.
original.addSuppressed(auditingFailure);
throw original;
~~~

This approach preserves the original error and records the secondary failure. Check the rules on self-suppression and on suppressed exception support for the specific `Throwable` class.

### Case C: Handling genuinely completes

~~~java
// Illustrative snippet inside a catch with an appropriate fallback.
String cached = readValidCachedValue();
return cached;
~~~

When a reliable fallback value is computed successfully and the contract allows it, the handler can complete normally. If `readValidCachedValue()` throws an exception, it still needs to be handled or propagated; placing the call inside `catch` does not exempt it from failing.

### Case D: Only reporting the error, without failure-prone operations

~~~java
// Illustrative snippet inside catch with variable ex.
System.err.println("Không hoàn thành thao tác: " + ex.getMessage());
throw ex;
~~~

This is a basic illustration. In real systems, loggers can fail or log duplicates across multiple layers; use a properly managed logger and choose a single boundary responsible for logging. Avoid assuming that every operation inside a handler is completely safe.

There is no single mandatory strategy for every system. What matters is preserving **error semantics, cause inspectability, and the behavior callers expect**.

## 11. Notes on Multiple `catch` Branches and Exception Types

Each `catch` is selected based on the runtime type of the exception object thrown **within the protected section**. Key rules to remember:

1. `catch (RuntimeException ex)` catches `IllegalArgumentException`, `IllegalStateException`, and compatible subclasses, but it does not catch `Error`.
2. When there are multiple `catch` blocks, place subclasses before superclasses; putting `catch (Exception)` before `catch (IOException)` makes the latter unreachable and causes a compile-time error.
3. Multi-catch such as `catch (IOException | SQLException ex)` catches either type **from the same `try` block**. It does not catch a new exception thrown inside the multi-catch body itself.
4. `catch (Exception ex)` can be used, but you should not catch overly broadly and leave it empty, as that can accidentally turn a serious failure into a false success.
5. If a `catch` branch throws a new checked exception type, the compiler checks that type's ability to escape; a sibling `catch` does not automatically handle the new exception.

In particular, the following snippet **does not work the way many people expect**:

~~~java
// Illustrative snippet with perform() matching the example.
try {
    perform();
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("Handler failed", ex);
} catch (IllegalStateException ex) {
    System.out.println("Không bắt được lỗi từ catch trước!");
}
~~~

If `perform()` throws `IllegalArgumentException`, the first handler is selected and throws a new `IllegalStateException`. The second handler does not catch that new exception. However, if **`perform()` itself throws `IllegalStateException`**, the second handler can be selected normally. Even though both are `IllegalStateException`, **the throw site and the `try` scope** determine which branch is used.

## 12. Practical Checklist When a `catch` Does Not Behave as Expected

When reading logs or debugging an exception that occurs inside a handler:

1. Identify **which original exception led to the first `catch` branch**. Inspect its type, message, and initial stack trace.
2. Read each statement in the handler body, especially logging calls, `getCause()` accesses, fallback data reads, and cleanup.
3. Identify **the line that throws the second exception** and its actual type. Do not assume it has the same type as the original error.
4. Mark which `try` **actually encloses the new throw line**. Sibling `catch` blocks of the current construct are not handlers for errors thrown inside `catch`.
5. Check `finally`: which path does it take, and does it throw/return in a way that overrides the propagating error?
6. In the enclosing handler, inspect `getCause()` and `getSuppressed()`; if both are empty, check whether the code dropped the original error when creating a new exception.
7. Choose where to handle or forward intentionally, and write tests simulating both the **initial failure** and the **failure of the handling logic**.

A worthwhile test example: mock the primary API to throw `IOException`, then mock the audit call to also throw `IOException`. Explicitly verify **the error type the caller receives**, **`cause`/`suppressed`**, and **the remaining state of resources**. A test that only exercises the happy path will miss errors masked inside the handler.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing a sibling `catch (B)` expecting to catch B thrown from `catch (A)` | B continues propagating outward; the sibling handler is not selected. | Place a nested `try/catch` inside the handler or use an enclosing `try`. |
| Wrapping a new exception without preserving `cause` | Traceability to the original error is easily lost. | Use the `(message, cause)` constructor or an appropriate mechanism to record the secondary error. |
| Calling `ex.getCause().getMessage()` unconditionally | Can throw `NullPointerException` right while handling an error. | Check that `getCause()` is non-`null` before using it. |
| Using `return` or `throw` inside `finally` | Can mask an exception from `try`/`catch`. | Let `finally` clean up and complete normally whenever possible. |
| Assuming a selected `catch` guarantees complete handling | The handler itself can still fail mid-way. | Design and test the handler's own failure paths. |
| Throwing a new checked exception inside `catch` without declaring `throws` | Compile-time error for the checked exception. | Catch it in a nested `try`, wrap appropriately, or declare it to the caller. |
| Logging the same error at every layer while also rethrowing | Duplicate logs, making it hard to determine the real incident count. | Log at the responsible boundary or only add context when crossing layers. |
| Swallowing a secondary error without recording it when it affects the outcome | Hard to diagnose because recovery failure traces are lost. | Preserve the secondary error in `suppressed`, `cause`, or an appropriate monitoring mechanism. |
| Treating `finally` and `try-with-resources` as completely equivalent | Differences in how resource-closing errors are preserved. | Use `try-with-resources` for `AutoCloseable` when appropriate. |
| Assuming `throw ex` recreates the exception at the handler | Can misread the stack trace. | Distinguish between rethrowing a reference and `throw new` creating a new object. |

## 14. Self-Check

1. **A `try` has `catch (IllegalArgumentException)` followed by `catch (IllegalStateException)`. If the first branch throws `IllegalStateException`, will the second branch catch it?** — No. It can only catch `IllegalStateException` thrown within the protected `try` scope, not from a sibling `catch`.
2. **What should you do to catch an audit error right inside `catch`?** — Place a new nested `try/catch` inside the handler around the audit call.
3. **A `catch` throws a checked `IOException`, and the method has neither `throws IOException` nor an enclosing handler. Does the program compile?** — No; you must catch or declare the new checked exception.
4. **Does `throw original;` create another object?** — No, it is still the exact same `original` reference.
5. **How does `throw new IllegalStateException("fail", original);` allow tracing back to the original error?** — Through `getCause()` and the `Caused by:` section of the stack trace.
6. **If `finally` throws another exception while the handler is throwing an error, which exception can escape?** — The new exception from `finally` can replace the exception waiting to propagate outward.
7. **Are `getSuppressed()` and `getCause()` the same?** — No. Suppressed holds recorded secondary errors; cause describes the causal relationship of an exception.
8. **If `catch` logs and hits a `NullPointerException` in the formatter, does the original error automatically become the cause?** — No. If not preserved in code, the original error can be lost from the cause chain.
9. **Why is it necessary to test the error paths of a handler?** — Because recovery, audit, and cleanup tasks can also fail and change the exception the caller receives.
10. **After `catch` throws a new exception and `finally` completes normally, does the program execute the line immediately after that construct?** — Not on this execution path if the exception is still unhandled; it continues propagating to an enclosing handler or caller above.

## References

- [Java Language Specification 17, §14.20.1 — Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): how a `catch` branch is selected and executed.
- [Java Language Specification 17, §14.20.2 — Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): `finally` rules on abrupt completion paths.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exceptions thrown in method statements.
- [Java Language Specification 17, §11.3 — Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): handler lookup by execution context.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `addSuppressed()`, and stack traces.

**Key takeaway:** a `catch` handling an error does not mean every statement inside it is safe. If a handler throws another exception, that exception is handled according to the `try` blocks enclosing **the new throw site**; sibling `catch` blocks do not catch it for you. Keep handlers simple, preserve the original error via `cause` or `suppressed` when needed, and pay attention to `finally` for accurate diagnostics.

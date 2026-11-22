# Nested `try-catch` and Exception Handling Boundaries in Java

In Java, a `try-catch` can be placed **inside another `try`**. This organization helps separate responsibilities: the inner layer handles errors that it **knows how to recover from**, while the outer layer handles errors **beyond the capability** of the inner layer or decides the outcome of the entire operation.

The hard part is not writing many curly braces, but accurately answering three questions:

1. **Where is the exception thrown?** Which `try` region is it in, and which calls does it pass through?
2. **Which handler is considered first?** A `catch` in an inner region can catch an error before an outer handler sees it, even if the outer handler has a more specific type.
3. **Which layer is responsible for handling it?** After catching the error, should execution continue, rethrow, translate to a new exception with a `cause`, or stop the operation?

**Foundational rule:** Java searches for a matching handler across **active handling regions from inside out**. Within a single `try` construct, `catch` branches are evaluated **in the order they are written from top to bottom**. A handler that finishes handling an exception without rethrowing prevents that exception from propagating to the outer layer.

## 1. Syntax of Nested `try-catch`

General structure:

```java
try {
    // Work of the outer scope.
    try {
        // Work that needs a local handling policy.
    } catch (IllegalArgumentException ex) {
        // Handle this error type within the inner scope.
    } finally {
        // Finish/cleanup for the inner scope.
    }

    // Runs only if the inner construct completes normally.
} catch (IllegalStateException ex) {
    // Receives errors from the outer try, including errors propagating from inside.
} finally {
    // Finish/cleanup for the outer scope.
}
```

This is an **illustrative syntax skeleton**, not a standalone program. You can place `try-catch` inside a method, a loop, a conditional branch, or even inside another `catch` branch.

In the example:

- The outer `try` is executing the entire inner `try-catch-finally` construct as part of its body.
- The inner `catch (IllegalArgumentException)` is evaluated for errors exiting the **inner `try` body**.
- If the inner error does not match the inner `catch`, or the inner `catch` block **throws a new error**, the error can exit to the outside and be caught by the outer `catch` if compatible.
- The inner `finally` normally runs when leaving the inner `try`; the outer `finally` normally runs when leaving the outer `try`. When an error propagates from inside out, cleanup activities occur according to the scope being exited.
- The remaining statements in the `try` part interrupted by the error **do not automatically resume** after the outer-layer handler finishes.

### Path Diagram

```text
outer try
│
├─ preceding operations
│
├─ inner try
│  ├─ statement causing error X
│  ├─ does inner catch match X?
│  │  ├─ Yes → handled → inner finally → continue in outer try
│  │  └─ No  → inner finally → X exits to outer try
│  └─ if inner catch throws Y → inner finally → Y exits to outer try
│
├─ statements after inner try, run only if inner part completes normally
│
├─ outer catch matching X/Y (if X/Y exits outer try)
│
└─ outer finally
   ↓
after the entire construct, if it completes normally
```

A common point of confusion: **"nearest handler" does not mean "the handler declaring the most specific subtype across the whole program"**. What matters first is that the handler is in the **region currently protecting the execution path**.

## 2. Scenario A: The Inner Handler Finishes Handling

Consider the following code inside a method body:

```java
try {
    try {
        throw new NumberFormatException("bad number");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: handled");
    }

    System.out.println("outer: after inner");
} catch (NumberFormatException ex) {
    System.out.println("outer: number-format");
}
```

**Stdout:**

```text
inner: handled
outer: after inner
```

`NumberFormatException` extends `IllegalArgumentException`, so the inner `catch (IllegalArgumentException)` catches the error. Even though the outer `catch (NumberFormatException)` is more specific, it **does not run**, because the exception was already handled inside.

Path: throw error → inner handler → complete inner construct → continue to the statement after the inner construct → outer `try` finishes normally.

When does this make sense? The inner layer has sufficient capability to recover: for example, it detects an invalid input line, skips that line as permitted by the contract, and the outer layer continues processing the remaining lines.

**Note:** "not rethrowing" only makes sense if the handler has truly brought the program back to an acceptable state. An empty `catch` that tricks the outer layer into thinking everything succeeded can be a design flaw.

## 3. Scenario B: Inner Handler Does Not Match, Error Propagates Outward

Example:

```java
try {
    try {
        System.out.println("inner: begin");
        throw new IllegalStateException("repository unavailable");
    } catch (NumberFormatException ex) {
        System.out.println("inner: invalid number");
    } finally {
        System.out.println("inner: cleanup");
    }

    System.out.println("outer: next operation");
} catch (IllegalStateException ex) {
    System.out.println("outer: " + ex.getMessage());
}
System.out.println("after: continue");
```

**Stdout:**

```text
inner: begin
inner: cleanup
outer: repository unavailable
after: continue
```

Analysis:

1. The inner `try` throws `IllegalStateException`.
2. The inner `NumberFormatException` handler does not match.
3. The inner `finally` runs and prints `inner: cleanup`.
4. The error propagates to the outer `try`; the line `outer: next operation` is skipped.
5. The outer `catch (IllegalStateException)` receives and handles the error.
6. If the outer handler completes normally, the program continues at `after: continue`.

Do not assume that once the error is caught outside, the program "goes back" to run `outer: next operation`. The outer `try` region has already completed abruptly at the location of the inner construct.

## 4. Scenario C: Inner Handler Catches and Rethrows the Same Object

```java
try {
    try {
        throw new IllegalArgumentException("quantity <= 0");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner: record context");
        throw ex;
    }
} catch (IllegalArgumentException ex) {
    System.out.println("outer: " + ex.getMessage());
}
```

**Stdout:**

```text
inner: record context
outer: quantity <= 0
```

`throw ex;` rethrows **the exact same exception object** that was caught, thus preserving its runtime type and existing `cause`. The outer handler sees the exception because the inner handler **did not complete normally**.

This can be a reasonable choice when the inner scope needs to record useful information, perform cleanup that cannot be moved to `finally`/`try-with-resources`, or decide that recovery must be handled by another layer.

However, a handler written solely as:

```java
catch (IllegalArgumentException ex) {
    throw ex;
}
```

is usually **redundant** if it adds no action or contract. There is no need to add an extra `try-catch` level just to pass an exception through.

## 5. Scenario D: Inner Handler Translates to a New Exception with a Cause

Sometimes the inner layer knows a technical error, while the outer layer needs an error at the business/orchestration level:

```java
try {
    try {
        Integer.parseInt("abc");
    } catch (NumberFormatException cause) {
        throw new IllegalStateException(
                "cannot prepare order quantity", cause);
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

**Stdout:**

```text
cannot prepare order quantity
NumberFormatException
```

The inner handler creates a **new** `IllegalStateException` object and attaches the original `NumberFormatException` as its `cause`. The outer handler catches the **new** exception by type `IllegalStateException`, rather than looking through `cause` to catch by type `NumberFormatException`.

Distinction:

| Action in handler | Exception exiting to outer layer | Information preserved |
| --- | --- | --- |
| Handle and do not rethrow | That exception does not exit | Can return a valid state |
| `throw ex;` | Same `ex` object | Original type and cause |
| `throw new X("context", ex);` | New object of type `X` | Cause linked to `ex` |
| `throw new X("context");` | New object of type `X` | Risks losing connection to original cause |

Only change the exception type when the **upper-layer contract** or context requires it. Avoid repeatedly wrapping at every layer into meaningless layers of "operation failed".

## 6. Complete Java 17+ Example: Four Paths in Nested `try-catch`

This program runs standalone, requiring no external files or connections. Save as **`NestedTryCatchDemo.java`**:

```java
public class NestedTryCatchDemo {

    static void run(String mode) {
        System.out.println("case=" + mode);

        try {
            System.out.println("outer: enter");

            try {
                System.out.println("inner: enter");

                if ("format".equals(mode)) {
                    throw new NumberFormatException("bad integer");
                }
                if ("state".equals(mode)) {
                    throw new IllegalStateException("closed");
                }
                if ("convert".equals(mode)) {
                    throw new IllegalArgumentException("raw");
                }

                System.out.println("inner: success");

            } catch (NumberFormatException ex) {
                System.out.println("inner: format handled");

            } catch (IllegalArgumentException ex) {
                System.out.println("inner: wrapping argument");
                throw new IllegalStateException(
                        "invalid request", ex);

            } finally {
                System.out.println("inner: finally");
            }

            System.out.println("outer: after inner");

        } catch (IllegalStateException ex) {
            System.out.println(
                    "outer: state=" + ex.getMessage());
            String causeName = ex.getCause() == null
                    ? "none"
                    : ex.getCause().getClass().getSimpleName();
            System.out.println("outer: cause=" + causeName);

        } finally {
            System.out.println("outer: finally");
        }

        System.out.println("after: complete");
    }

    public static void main(String[] args) {
        run("ok");
        run("format");
        run("state");
        run("convert");
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 NestedTryCatchDemo.java
java NestedTryCatchDemo
```

**Exact stdout:**

```text
case=ok
outer: enter
inner: enter
inner: success
inner: finally
outer: after inner
outer: finally
after: complete
case=format
outer: enter
inner: enter
inner: format handled
inner: finally
outer: after inner
outer: finally
after: complete
case=state
outer: enter
inner: enter
inner: finally
outer: state=closed
outer: cause=none
outer: finally
after: complete
case=convert
outer: enter
inner: enter
inner: wrapping argument
inner: finally
outer: state=invalid request
outer: cause=IllegalArgumentException
outer: finally
after: complete
```

### Analysis by Mode

**`ok` — no error:** executes `inner: success`; no handler runs; inner `finally` runs; returns to the outer `try` to print `outer: after inner`; finally outer `finally` and `after: complete`.

**`format` — handled by inner handler:** throws `NumberFormatException`, caught by inner `catch (NumberFormatException)`. It **does not propagate to the outer `catch`**. After inner `finally`, the outer `try` continues to print `outer: after inner`.

**`state` — error not caught by inner handler:** throws `IllegalStateException`. The two inner branches are only for `NumberFormatException` and `IllegalArgumentException`, so neither matches. Inner `finally` runs, then outer `catch (IllegalStateException)` receives the error. Because there is no `cause`, it prints `none`. The line `outer: after inner` does not run.

**`convert` — inner handler translates error:** throws `IllegalArgumentException("raw")`; inner handler catches it and throws `IllegalStateException("invalid request", ex)`. Inner `finally` runs; outer handler catches the new error and prints `IllegalArgumentException` from `getCause()`. The line `outer: after inner` does not run, because the inner construct completed abruptly.

All four cases print `outer: finally` and `after: complete` in this program, because the outer handler resolves the present error types and does not throw a new error.

### Short Decision Table

| Mode | Where error occurs | Final handling handler | Does the part after the inner construct in outer `try` run? |
| --- | --- | --- | --- |
| `ok` | None | Not applicable | Yes |
| `format` | Inner `try` | Inner `catch NumberFormatException` | Yes |
| `state` | Inner `try` | Outer `catch IllegalStateException` | No |
| `convert` | Inner `try`, then wrapper from inner handler | Outer `catch IllegalStateException` | No |

**Meaning of boundaries:** where an error is caught should correspond to the **decision that can be made**. The `format` case has an inner handler because it can be handled locally; `state` and `convert` become the outer layer's responsibility.

## 7. Exceptions Thrown from `catch` Are Not Caught by Sibling `catch` Clauses

A common mistake is believing that a later handler can handle an error thrown by an earlier handler:

```java
try {
    throw new IllegalArgumentException("bad data");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("conversion failed", ex);
} catch (IllegalStateException ex) {
    System.out.println("never reached for this new error");
}
```

This is an **illustrative snippet**; although the branches have valid types, `catch (IllegalStateException)` does not receive errors from the preceding `catch`. Sibling `catch` clauses are only selected for exceptions exiting the **corresponding `try` body**, not to protect each other's bodies.

To catch a new exception from an inner handler, place **an outer `try-catch`**:

```java
try {
    try {
        throw new IllegalArgumentException("bad data");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("conversion failed", ex);
    }
} catch (IllegalStateException ex) {
    System.out.println("outer: " + ex.getMessage());
}
```

**Stdout:**

```text
outer: conversion failed
```

A handling boundary is defined by **which `try` region surrounds the execution block**, not merely by `catch` clauses happening to sit next to each other in the same file.

## 8. Nested `finally` and Cleanup Order

When leaving a `try`, its corresponding `finally` block is normally executed. If an exception propagates across multiple nested constructs, cleanup occurs from the inner scope to the outer scope:

```java
try {
    try {
        System.out.println("work");
        throw new IllegalStateException("failed");
    } finally {
        System.out.println("cleanup-inner");
    }
} catch (IllegalStateException ex) {
    System.out.println("handle-outer");
} finally {
    System.out.println("cleanup-outer");
}
```

**Stdout:**

```text
work
cleanup-inner
handle-outer
cleanup-outer
```

Here there is no inner handler; the inner `finally` runs first, the exception is passed to the outer handler, and then the outer `finally` runs.

### `finally` Does Not Guarantee "No More Errors"

`finally` does not catch exceptions on its own: if there is no matching handler, the error still propagates outward. In addition, a `finally` block **can throw another error**, masking the pending error.

Example:

```java
try {
    try {
        throw new IllegalArgumentException("original");
    } finally {
        throw new IllegalStateException("cleanup");
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
```

**Stdout:**

```text
cleanup
```

Here, the `IllegalStateException("cleanup")` from `finally` replaces the propagation path of the original exception. It does not mean the `original` error never happened. Therefore, avoid actively using `return` or `throw` from `finally` unless you truly intend to alter the error's path.

For `AutoCloseable` resources, `try-with-resources` is more suitable than a chain of `finally` blocks manually calling `close()`: when both the `try` body and closing fail, Java normally keeps the `try` body's error as the primary error and puts the closing error into the **suppressed exceptions** list instead of losing the primary error altogether.

## 9. `try-with-resources` Can Be Nested Inside an Outer `try-catch`

Consider the following method, **illustrative only**, which must be placed in a Java class and given a valid `Path` when called:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

The caller can place an outer `try-catch` boundary:

```java
try {
    String line = readFirstLine(path);
    System.out.println("first line: " + line);
} catch (java.io.IOException ex) {
    System.out.println("Cannot read input file");
}
```

The calling snippet requires a `path` variable of type `java.nio.file.Path` in the same scope. Benefits:

1. The reading layer is responsible for **closing the reader** in `try-with-resources`.
2. The calling layer is responsible for **deciding how to report the file-reading error**.
3. If an error occurs during opening/reading/closing, the I/O exception can exit for the caller to handle according to the contract.
4. There is no need for the outer handler to directly hold and close the lower layer's internal resource.

Do not treat the outer `catch` as a tool that guarantees rollback of all side effects: if part of a file has already been written, a database updated, or another service called, a dedicated recovery/transaction policy is needed.

### What Information Can an Inner Handler Hide?

If the reading layer writes:

```java
try (var reader =
             java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
} catch (java.io.IOException ex) {
    return "";
}
```

This is an **illustrative method body**, assuming the method returns `String`. If an empty string is valid data, the caller cannot distinguish **successfully reading an empty string** from **a failed read**. Only use a fallback if the contract genuinely accepts it and the behavior is documented. If the data is required, letting `IOException` propagate upward is usually more appropriate.

## 10. Layered Handling Boundaries: Library, Business Logic, and Interface

In a Java application, nested `try-catch` often arises naturally across **the call chain between layers**, rather than all sitting inside a single method.

Example call path:

```text
controller.handleRequest()
  └─ service.placeOrder()
       └─ repository.save()
            └─ I/O operation throws IOException
```

A reasonable division of responsibilities:

- **Repository:** knows which kind of I/O operation failed, manages resources, and can throw `IOException` or an exception suited to the storage contract.
- **Service:** knows the business context. It only catches errors if it can retry per policy, perform a compensating action, or translate the error into a meaningful business-layer concept. When changing the exception type, preserve `cause`.
- **Controller or task boundary:** knows what response the caller needs. It can translate the exception into a failed request status, an appropriate HTTP code, or a centralized error record.

**There is no rule that "every layer must have exactly one `catch`."** If the service cannot handle it, letting the error propagate upward is reasonable. If the controller cannot handle it either, a common framework/application error boundary is needed. Catching at every layer and printing the same stack trace only duplicates logs and blurs responsibility.

### Runnable Java 17+ Example: Inner and Outer Layer Boundaries

File **`ExceptionBoundaryDemo.java`**:

```java
import java.io.IOException;

public class ExceptionBoundaryDemo {

    static void repository(int id) throws IOException {
        if (id == 0) {
            throw new IOException("storage not available");
        }
        System.out.println("repository: saved " + id);
    }

    static void service(int id) throws IOException {
        try {
            repository(id);
        } catch (IOException cause) {
            throw new IOException(
                    "service: cannot save order " + id, cause);
        }
    }

    static void controller(int id) {
        System.out.println("request=" + id);

        try {
            service(id);
            System.out.println("response=OK");
        } catch (IOException ex) {
            System.out.println("response=FAILED");
            System.out.println("message=" + ex.getMessage());
            System.out.println(
                    "cause=" + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        controller(7);
        controller(0);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
```

**Exact stdout:**

```text
request=7
repository: saved 7
response=OK
request=0
response=FAILED
message=service: cannot save order 0
cause=IOException
```

Explanation:

- `controller(7)` calls service, repository completes normally; `catch` does not run.
- `controller(0)` calls repository, encounters `IOException`. The handler in service catches it, adds order context, and throws a **new `IOException` containing the cause**.
- The outer handler in controller receives the error wrapped by service, printing the service-level message and the root cause's type.
- Because controller caught it and did not rethrow, it intentionally returns an illustrative failure status instead of leaving an unhandled exception.
- This is a **layered pattern**, not proof that every case must wrap `IOException` in another `IOException`. If the service-level information is not useful, letting the error propagate upward can be easier to maintain.

In real systems, end-user messages and internal log details should be kept separate; do not return `getMessage()` verbatim by default if it may contain paths, configuration, or sensitive data.

## 11. Variable Scope and Its Impact on Splitting Nested `try-catch`

The braces of each `try`, `catch`, and `finally` create a **block scope**. The following example **intentionally does not compile**:

```java
try {
    int value = Integer.parseInt("12");
} catch (NumberFormatException ex) {
    System.out.println(value); // value is not in scope.
}
```

If both the success path and the error-handling path need access to a value, design the variable or result type in an appropriate scope:

```java
int value;
try {
    value = Integer.parseInt(input);
} catch (NumberFormatException ex) {
    value = defaultValue;
}
System.out.println(value);
```

This is **illustrative code**, assuming `input` and `defaultValue` are already defined. Assigning a fallback in `catch` ensures the variable is assigned on both execution paths and Java can verify `definite assignment`; however, a fallback only makes sense when it is part of the contract, not as a way to hide errors.

Also note that the `ex` variable only exists within the scope of the handler that declares it. Nesting `try-catch` too deeply sometimes leaves necessary information out of scope for error reporting; adjust your data design or move handling up to a layer with context instead of using global variables.

## 12. When to Nest, When to Extract into Methods?

Repeatedly nesting multiple `try` levels does not automatically make code safer. A boundary is useful when that layer has a **distinct handling goal**.

**Nest when:**

- A sub-operation has an independent fallback, while the enclosing operation needs to protect the integrity of a larger workflow.
- The inner layer needs to translate a technical exception into a business-level error, and the outer layer decides the response.
- The inner layer manages resources, and the outer layer manages the request outcome.
- You need to distinguish between "locally recovered error" and "error forcing cancellation of the entire task".

**Consider extracting instead of deep nesting when:**

- Multiple `try-catch` levels catch the same type and only log and rethrow.
- One method contains handlers mixing too many responsibilities: input, data access, network, and UI.
- It is unclear which code is protected, or each recovery policy cannot be tested independently.
- Too many `finally` blocks manually managing resources risk cleanup errors masking the primary error.

A readable structure is usually: **small methods manage local errors**, **the calling layer decides the error of the larger operation**. Exceptions still propagate through the call chain when no handler is matched.

## 13. Notes on Checked Exceptions, Multi-Catch, and Unchecked Errors

### Checked Exceptions in the Inner Layer

If a call inside `try` can throw a checked `IOException`, the appropriate scope must catch it or declare `throws` for unhandled cases:

```java
static void caller() throws java.io.IOException {
    try {
        read();
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("missing file");
    }
}
```

This is an **illustrative skeleton** if `read()` is defined with `throws IOException`. Catching `FileNotFoundException` only covers one subclass; other `IOException`s can still exit, so `caller` still declares `throws IOException`.

An outer `try` construct with `catch (IOException)` can also handle the rest, provided the execution path actually lies within that region.

### Multi-Catch in Nested `try`

`catch (IOException | NumberFormatException ex)` is valid syntax when the two error types have no parent/child relationship and the handling action is the same. However, `catch (NumberFormatException | IllegalArgumentException ex)` is **invalid** because `NumberFormatException extends IllegalArgumentException`.

Multi-catch does not change how inside-out scope evaluation works; it simply groups multiple types into **one handler** of a `try` construct.

### Unchecked Errors

An outer `catch (Exception)` can catch many error types, including `RuntimeException`, but does not catch `Error`. Do not use `catch (Throwable)` at every level to "keep the application alive", because `Error` can represent conditions from which the application cannot safely recover.

A general boundary at the start of a request or task may need centralized error reporting, but must still preserve the cause, failure status, and appropriate handling policy.

## 14. Nested `try-catch` and Threads: Boundaries Do Not Cross to Other Threads Automatically

Example:

```java
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("worker failed");
    });
    worker.start();
} catch (IllegalStateException ex) {
    System.out.println("caught in parent");
}
```

This is an **illustrative snippet** and should not be used to demonstrate fixed stdout because uncaught handler behavior depends on the environment. The handler around `worker.start()` protects the `start()` call in the calling thread; it **does not automatically catch** exceptions thrown later when `Runnable` executes on the other worker's stack.

Similarly, `worker.join()` only waits for the thread to finish and does not automatically rethrow errors that occurred inside the worker. If you need to communicate success/failure back to the coordinator, use `Future`, `CompletableFuture`, or a properly designed reporting mechanism.

The scope of `try-catch` is the **dynamic execution scope of the current thread**, not "all work originating from the called statement". This is an important boundary when moving from synchronous Java to multithreading.

## 15. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Catching all errors in inner `try` and ignoring them | Outer layer does not know the operation failed | Only recover when there is a clear contract; otherwise propagate or translate |
| Expecting a more specific outer `catch` to take priority over a parent-type inner `catch` | Misunderstanding handler search order | Evaluate active regions from inside out first |
| Thinking handling in outer `catch` will resume the rest of outer `try` | Missing the interrupted execution path | Put continuation logic after the construct or retry explicitly |
| Expecting a sibling `catch` to catch an exception thrown from another `catch` | The new exception escapes outward | Use an outer `try-catch` or reorganize handlers |
| Using `finally` to unintentionally throw a new error | Can mask the original cause | Clean up safely; prefer `try-with-resources` |
| Repeating logging and wrappers at every level | Log noise, long cause chains | Place logging/translation boundaries responsibly |
| Wrapping an error without passing `cause` | Loss of diagnostic information | Use a constructor accepting `Throwable cause` |
| Catching `IOException` in a `try` that has no compatible checked error source | May not compile | Catch around the actual call that can throw that type |
| Wrapping an entire method in an overly broad `try` | Cannot identify error source, easy to return wrong message | Narrow by operation and handling policy |
| Expecting a handler to catch errors from a `start()`ed thread | Exception is on a different stack | Use task error reporting/observation channels |

## 16. Self-Check Exercises

**Exercise 1 — Inner handler has a parent type:**

```java
try {
    try {
        throw new NumberFormatException("x");
    } catch (IllegalArgumentException ex) {
        System.out.println("inner");
    }
} catch (NumberFormatException ex) {
    System.out.println("outer");
}
```

**Answer:** prints only `inner`. `NumberFormatException` is a subtype of `IllegalArgumentException` and was already handled by the inner handler.

**Exercise 2 — Inner mismatch with `finally`:**

```java
try {
    try {
        throw new IllegalStateException("broken");
    } catch (NumberFormatException ex) {
        System.out.println("wrong catch");
    } finally {
        System.out.println("cleanup");
    }
} catch (IllegalStateException ex) {
    System.out.println("handled outside");
}
```

**Answer:**

```text
cleanup
handled outside
```

The error propagates out of the inner block after `finally` executes.

**Exercise 3 — Error translated inside `catch`:**

```java
try {
    try {
        throw new IllegalArgumentException("bad");
    } catch (IllegalArgumentException ex) {
        throw new IllegalStateException("wrapped", ex);
    }
} catch (IllegalStateException ex) {
    System.out.println(ex.getCause().getMessage());
}
```

**Answer:** prints `bad`. The outer error is `IllegalStateException`, and its `cause` is the original `IllegalArgumentException`.

**Exercise 4 — Does the statement after the inner construct run?**

If the inner `try` throws `IllegalStateException` that is not caught by the inner handler, and the outer handler catches it and completes normally, does the statement **inside the outer `try`, immediately after the inner construct** run?

**No.** The inner construct completed abruptly, interrupting the outer `try`; after the outer handler, execution continues after the outer `try-catch` construct (if it completes normally).

**Exercise 5 — Error in `finally`:**

If the inner `try` is throwing exception A, but the inner `finally` throws exception B, which exception will the outer handler receive according to Java's completion rules?

**Normally B.** The new abrupt completion caused by `finally` can replace A. For `AutoCloseable` resources, `try-with-resources` has a suppressed exceptions mechanism that saves errors when closing resources, so one cannot infer that all errors in `finally` are automatically preserved.

**Exercise 6 — Error from another thread:**

Can you wrap `new Thread(task).start()` in a `try-catch` to catch a `RuntimeException` thrown later by `task.run()` itself?

**Not automatically.** `task.run()` executes in the new thread, not on the call stack of the thread executing `start()`.

## 17. Handling Boundary Design Checklist

When preparing to add a `try-catch` layer, ask yourself:

1. **Which operation does this layer own?** Identify the statements and call chain to protect; avoid accidentally catching from unrelated code.
2. **Can the inner layer fix the error?** If there is a tested recovery policy, handle it here. If not, do not catch just to ignore.
3. **Where does the remaining error go?** If no inner handler matches, it will exit to the outer scope after cleanup.
4. **Is the error translated to a new type?** If so, the outer handler type must be compatible with the **new object**, and `cause` should preserve the original error.
5. **Where does the program continue after the handler runs?** Do not assume skipped statements in `try` will retroactively run.
6. **Are `finally` and resources safe?** Minimize throwing/`return` in `finally`; prefer `try-with-resources` when appropriate.
7. **Are checked exceptions sufficiently declared or caught?** A subclass handler does not always cover the entire parent type declared by the call.
8. **Is there a thread switch?** If so, place a result/error receiving mechanism at the appropriate concurrency boundary.
9. **Are logging and wrappers being duplicated?** Only add a handling layer if that layer adds a new action or context.
10. **Has each branch been tested?** At minimum, test the success path, inner-caught error, outer-propagated error, wrapped error, and cleanup cases.

**Conclusion:** Nested `try-catch` is not "multiple layers of automatic insurance", but a way to express **boundaries of responsibility**. The inner handler is evaluated first for errors within its scope; if it does not match or throws a new error, the outer layer can handle it. Good design gives errors a clear path, manages resources in the right place, and ensures the caller receives genuine failures instead of a false success state.

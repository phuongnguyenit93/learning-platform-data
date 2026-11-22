# Rethrowing the Same Exception Object with `throw e` in Java

In Java, when an exception has been caught with `catch`, a developer can **rethrow that exact exception object** using the `throw e;` statement. This practice is called **rethrowing**. It is useful when the current layer needs to perform a limited action—such as recording context, releasing resources, or updating state—but **does not have the authority or ability to fully handle the error**, and therefore needs to let a higher calling layer decide how to proceed.

The key point is: **`throw e` rethrows the object currently referenced by `e`; it does not create a new exception on its own.** Therefore, the existing object, runtime type, message, cause, and stack trace information are preserved unless the code itself has modified those mutable fields. After `throw e` executes, the current `catch` block also terminates abnormally; Java continues searching for a matching handler in an outer scope.

This lesson focuses on the `throw e` statement itself: why rethrowing is needed, which object is thrown, where the execution flow goes, how checked/unchecked exceptions affect it, stack trace characteristics, the *precise rethrow* rule, and common mistakes that can obscure the original error.

## 1. Syntax of `throw e` and Conditions for Using It

Consider the following code snippet:

```java
try {
    riskyOperation();
} catch (IllegalStateException e) {
    System.out.println("Đã ghi nhận lỗi: " + e.getMessage());
    throw e;
}
```

This is an **illustrative snippet inside a method**, assuming `riskyOperation()` is already defined. Its meaning is:

1. `riskyOperation()` throws an exception of type `IllegalStateException` or a subclass.
2. `catch` receives a **reference** to that exception object via the variable `e`.
3. The print statement inside `catch` performs work at the current layer.
4. `throw e;` rethrows the object that `e` points to.
5. Java skips the rest of the handler (if any) and propagates the exception to the outer scope. Related `finally` blocks or resource closing still execute according to Java rules.

The general syntax of the `throw` statement is `throw <expression>;`, where the expression must have a reference type compatible with `Throwable` according to Java's rules. `e` is usually a `catch` parameter, though it can also be an exception-typed variable from another scope.

**Distinguishing `throw` and `throws`:**

- `throw e;` is a **runtime statement** that actually triggers throwing the object.
- `throws IOException` is a **declaration in a method signature**, indicating that the method may propagate a checked exception; by itself, it does not throw an object.
- `try/catch` determines whether there is a local handler; `throw e` inside a handler means that layer decides **not to finish handling the error here**.

For checked exceptions, the compiler enforces the `catch-or-declare` obligation along the rethrow path. For `RuntimeException` or `Error`, a `throws` clause is not required merely because `throw e` is present.

## 2. Why Catch an Exception Only to Rethrow It?

Catching an exception **does not mean** finishing handling its consequences. A lower layer may know what just happened, but it may not know whether to abort a request, notify the user, choose another file, or cancel a workflow.

For example, suppose a configuration-loading method fails with `IOException`:

- The file-access layer knows which path could not be read.
- The service layer may know which feature was waiting for the configuration.
- The application startup layer can decide whether to abort startup or try a fallback configuration.

If the service layer only wants to record a diagnostic trace and **preserve the exception contract**, rethrowing the same `IOException` is a clear choice. The higher layer receives the same exception object instead of a fake "success" value.

Common valid purposes:

| Reason | Work before `throw e` | Why rethrowing is needed |
| --- | --- | --- |
| Add diagnostic trace | Log request context or operation name, protecting sensitive data | The current layer cannot decide how to recover |
| Cleanup or state update | Cancel local work, mark a step as failed | The caller still needs to know the overall operation failed |
| Preserve API contract | Keep exception type, message, and cause unchanged | The caller already has a handler for the original type |
| Centralize error policy at higher layers | Lower layers do not generate HTTP/UI responses | The boundary layer decides the final response |
| Preserve failure signal | Do not return `null`, `false`, or unauthorized fallback data | Avoid misleading the caller into thinking the operation succeeded |

There is no need to write a `catch` block just to have `throw e` if the current layer does nothing useful. When no handling is needed, you can let the exception propagate naturally; that approach is usually more concise and preserves the failure signal.

## 3. `throw e` Preserves Object Identity

Java compares two references with `==` to determine whether they point to **the exact same object**. The `throw e` statement does not create a new instance, so an outer catch block receives the exact instance thrown by the inner layer.

Save the following program as **`RethrowIdentityDemo.java`**:

```java
public class RethrowIdentityDemo {
    private static IllegalArgumentException original;

    static void lowLevel() {
        original = new IllegalArgumentException("Mã đầu vào sai");
        throw original;
    }

    static void middleLevel() {
        try {
            lowLevel();
        } catch (IllegalArgumentException e) {
            System.out.println("Giữa: cùng đối tượng = " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            middleLevel();
        } catch (IllegalArgumentException e) {
            System.out.println("Ngoài: cùng đối tượng = " + (e == original));
            System.out.println("Loại: " + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
        System.out.println("Đã xử lý ở main");
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 --release 17 RethrowIdentityDemo.java
java RethrowIdentityDemo
```

**Exact stdout** in a UTF-8 display environment:

```text
Giữa: cùng đối tượng = true
Ngoài: cùng đối tượng = true
Loại: IllegalArgumentException
Message: Mã đầu vào sai
Đã xử lý ở main
```

Both `e == original` expressions evaluate to `true`. `middleLevel()` simply rethrows the exact reference it received. The original object is not converted into a `RuntimeException` or another object.

The `original` variable in the example only serves to verify identity; real applications should not store the latest exception in a global `static` field to pass errors across threads, as that can cause contention and retain unnecessary references. The actual error-propagation channel here is `throw`/`catch`.

Also note the distinction: being the same object **does not mean** all properties are immutable. A program can call `setStackTrace(...)`, `fillInStackTrace()`, or certain other `Throwable` APIs to alter diagnostic data; however, the `throw e` statement itself does not perform those modifications.

## 4. How Does `throw e` Change Execution Flow?

When an exception is rethrown, it must continue to a compatible **outer handler** or further up the call stack. Java does not try the remaining `catch` clauses of the **same `try` statement** as if they were handlers for the exception thrown inside the first `catch`.

Simple outline:

```text
caller
  └─ service
       └─ try { repository.read(); }
          catch (IOException e) {
              record error
              throw e   ───────────┐
          }                      │
  ◀──────────────────────────────┘
  catch (IOException e) { handle at caller }
  continue after caller's try/catch
```

Note the consequences:

- Any statement immediately following `throw e;` along that execution path does not run; if placed directly after it without a conditional branch, Java may report a compile-time **unreachable statement** error.
- Code at the end of the `try` block that was interrupted by the exception does not automatically run to catch up either.
- The method that rethrows the exception **exits abnormally**; the caller does not execute statements after the call inside its interrupted `try` branch.
- `finally` blocks and related cleanup actions run when leaving the scope, according to Java rules; if they themselves throw a new exception, the final error signal may change.
- Only when the outer handler finishes **normally** does Java resume from the point after that layer's `try/catch` construct, rather than jumping back to the original call site.

### Example with `finally` and Resumption Point

Save as **`RethrowFlowDemo.java`**:

```java
public class RethrowFlowDemo {
    static void load() {
        throw new IllegalStateException("Không tải được");
    }

    static void process() {
        try {
            System.out.println("1. Trong try");
            load();
            System.out.println("2. Sau load");
        } catch (IllegalStateException e) {
            System.out.println("3. Catch trong");
            throw e;
        } finally {
            System.out.println("4. Finally trong");
        }
    }

    public static void main(String[] args) {
        try {
            process();
            System.out.println("5. Sau process");
        } catch (IllegalStateException e) {
            System.out.println("6. Catch ngoài: " + e.getMessage());
        }
        System.out.println("7. Sau catch ngoài");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 RethrowFlowDemo.java
java RethrowFlowDemo
```

**Exact stdout:**

```text
1. Trong try
3. Catch trong
4. Finally trong
6. Catch ngoài: Không tải được
7. Sau catch ngoài
```

The statement "2. Sau load" does not run because `load()` throws an exception; "5. Sau process" does not run because `process()` exited abnormally. `finally` still executes before the exception reaches the outer `catch`. Finally, `main` continues with statement 7.

This is the difference between **recording at one layer and rethrowing** versus **resolving completely at that layer**. If the `catch` in `process()` did not execute `throw e` and completed normally, the call to `process()` would return normally; then statement 5 would run even though `load()` did not succeed. Whether to continue depends on the contract and system state.

## 5. Stack Trace When Rethrowing the Same Exception

A `Throwable` object typically captures its stack trace at construction time (or when `fillInStackTrace()` is called), provided stack trace recording is enabled for that object. **A normal `throw e` does not initialize a new stack trace on its own.** As a result, the outer layer still sees the trace attached to the original exception; the `throw e` statement is not automatically added as a new origin point just because it rethrows.

Look at an example that checks the top of the stack trace by method name rather than line numbers (since line numbers can shift when editing code). Save as **`RethrowTraceDemo.java`**:

```java
public class RethrowTraceDemo {
    static void source() {
        throw new IllegalArgumentException("Nguồn phát sinh");
    }

    static void relay() {
        try {
            source();
        } catch (IllegalArgumentException e) {
            System.out.println("Trong relay: "
                    + e.getStackTrace()[0].getMethodName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IllegalArgumentException e) {
            System.out.println("Trong main: "
                    + e.getStackTrace()[0].getMethodName());
            System.out.println("Số cause: " + (e.getCause() == null ? 0 : 1));
        }
    }
}
```

Commands:

```bash
javac --release 17 RethrowTraceDemo.java
java RethrowTraceDemo
```

**Exact stdout** on standard Java 17:

```text
Trong relay: source
Trong main: source
Số cause: 0
```

The example shows that the first element of the stack trace still points to `source` in both places. `relay` rethrew using `throw e`, but did not alter the origin trace.

**Important note:** Do not rely on the exact string format of `printStackTrace()`, line numbers, or specific stack trace contents as a stable contract across JVM versions and execution modes. In addition, `Throwable` allows modifying the stack trace via APIs, has a constructor that disables writable stack traces, and the JVM may optimize certain implicitly thrown exceptions under special conditions. The core property to remember is that **no new exception is created** and **`fillInStackTrace()` is not automatically called** merely because of `throw e`.

### Comparison with `throw new ...`

Three patterns that are often confused:

| Code | Object thrown | Type seen by caller | Original error information |
| --- | --- | --- | --- |
| `throw e;` | **The same object `e`** | Actual runtime type of `e` | Preserved as is |
| `throw new IllegalStateException("...", e);` | **New object** | New `IllegalStateException` | `e` is preserved in `cause` |
| `throw new IllegalStateException(e.getMessage());` | **New object** | New `IllegalStateException` | Does not keep `e` in `cause` unless passed separately |

`throw e` makes sense when the caller needs to receive the original type and object. **Wrapping** (`throw new SomeException(message, e)`) makes sense when the current layer needs to change the abstraction level or add context under a new contract. However, wrapping no longer preserves identity with the original exception, and the caller sees the new exception's stack trace, while the old exception can be traced via `getCause()`.

Some situations require preserving the checked exception type for the caller to handle; in those cases, `throw e` may be more appropriate than unintended wrapping.

## 6. Example Contrasting Rethrowing with Wrapping

The following program runs on Java 17+; save it as **`RethrowVsWrapDemo.java`**:

```java
public class RethrowVsWrapDemo {
    static IllegalArgumentException createProblem() {
        return new IllegalArgumentException("Giá trị âm");
    }

    static void rethrow(IllegalArgumentException problem) {
        try {
            throw problem;
        } catch (IllegalArgumentException e) {
            throw e;
        }
    }

    static void wrap(IllegalArgumentException problem) {
        try {
            throw problem;
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException("Không hoàn tất yêu cầu", e);
        }
    }

    public static void main(String[] args) {
        IllegalArgumentException original = createProblem();

        try {
            rethrow(original);
        } catch (IllegalArgumentException e) {
            System.out.println("Rethrow same: " + (e == original));
            System.out.println("Rethrow cause: " + (e.getCause() == null));
        }

        try {
            wrap(original);
        } catch (IllegalStateException e) {
            System.out.println("Wrap same: " + (e == (Object) original));
            System.out.println("Wrap cause same: " + (e.getCause() == original));
            System.out.println("Wrap type: " + e.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac --release 17 RethrowVsWrapDemo.java
java RethrowVsWrapDemo
```

**Exact stdout:**

```text
Rethrow same: true
Rethrow cause: true
Wrap same: false
Wrap cause same: true
Wrap type: IllegalStateException
```

In the rethrow part, the exception is the exact `original` object, and `getCause()` remains `null` because the code did not set a cause. In the wrapping part, the caller catches a new `IllegalStateException`; its `getCause()` points to `original`, allowing the cause chain to be followed.

The comparison `e == (Object) original` in the example casts to `Object` because `e` has type `IllegalStateException` and `original` has type `IllegalArgumentException`, two sibling classes under `RuntimeException`; casting to `Object` allows the illustrative identity comparison. The result is `false` because a new wrapper object was created.

This is why `throw e` and `throw new ...` **differ in contract, type, and diagnostic trace**, even though both cause the current execution flow to terminate abnormally.

## 7. Rethrowing a Checked Exception: `throws` Must Still Match

For a checked exception, `throw e` is still a path that can throw a checked exception at compile time. If a handler catches `IOException` and rethrows it, the enclosing method must **either catch it again in another suitable construct or declare `throws IOException` (or a permitted supertype)**.

Save as **`CheckedRethrowDemo.java`**:

```java
import java.io.IOException;

public class CheckedRethrowDemo {
    static void readConfig() throws IOException {
        throw new IOException("Không đọc được cấu hình");
    }

    static void loadService() throws IOException {
        try {
            readConfig();
            System.out.println("Đã đọc cấu hình");
        } catch (IOException e) {
            System.out.println("Dịch vụ ghi nhận: " + e.getMessage());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            loadService();
        } catch (IOException e) {
            System.out.println("Main xử lý: " + e.getMessage());
        }
        System.out.println("Main vẫn hoạt động");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 CheckedRethrowDemo.java
java CheckedRethrowDemo
```

**Exact stdout:**

```text
Dịch vụ ghi nhận: Không đọc được cấu hình
Main xử lý: Không đọc được cấu hình
Main vẫn hoạt động
```

`IOException` is a checked exception. In `loadService()`, even though `catch (IOException e)` is written, rethrowing means the method can still propagate `IOException` to the caller, so its signature declares `throws IOException`. `main()` handles the error at a higher level.

If you remove `throws IOException` from `loadService()` while keeping `throw e`, the code will fail to compile because the checked exception is neither handled nor declared. Conversely, if the handler catches and fully handles it without rethrowing, depending on the rest of the code, the `throws` declaration may not be needed.

With unchecked exceptions like `IllegalStateException`, there is no such declaration requirement, even when rethrown across multiple layers.

## 8. The *Precise Rethrow* Feature Since Java 7

A less obvious point: Java has a mechanism for **precisely analyzing which checked exception types are rethrown** when the `catch` parameter is **final or effectively final**. This is commonly referred to as *more precise rethrow analysis*.

First, consider a valid Java 17 example; save it as **`PreciseRethrowDemo.java`**:

```java
import java.io.IOException;

public class PreciseRethrowDemo {
    static void read() throws IOException {
        throw new IOException("Hỏng tệp");
    }

    // Even though the catch type is Exception, Java recognizes here
    // that the checked exception that can escape is IOException.
    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Relay: " + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Main: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac --release 17 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

**Exact stdout:**

```text
Relay: IOException
Main: Hỏng tệp
```

Why does `relay()` only declare `throws IOException` instead of `throws Exception`? Because the compiler analyzes which exceptions can be thrown from the `try` body. In this example, the relevant checked exception is `IOException`. The variable `e` is not reassigned, so it satisfies the precise rethrow condition; any unchecked exceptions do not need to be declared. Java does not force the signature to widen to `throws Exception` merely because `catch (Exception e)` is declared.

Important conditions:

1. `e` is the `catch` parameter being rethrown inside the handler.
2. `e` is `final` or **effectively final**: it is not reassigned in the `catch` body.
3. The compiler determines the exception types that can be thrown from the `try` block and caught by this handler, then applies the language's precise rethrow rules.

If the parameter `e` is reassigned, the narrowing precise rethrow rule no longer applies as before; `throw e` may be checked against the parameter's broader declared type. Therefore, the following snippet **intentionally does not compile** when the method only declares `throws IOException`:

```java
// Syntax counterexample inside a class that imports java.io.IOException:
static void changedCatchVariable() throws IOException {
    try {
        throw new IOException("Lỗi A");
    } catch (Exception e) {
        e = new IOException("Lỗi B"); // e is reassigned
        throw e; // May be required to handle/declare type Exception
    }
}
```

To preserve the original error object and take advantage of precise rethrow, **do not reassign the `catch` parameter**. Usually there is also no good reason to replace `e` with a new instance and still call it "rethrowing the same object."

### Multi-catch and Implicitly Final Parameters

Java allows catching multiple unrelated exception types in a single `catch` using `|`. The parameter of a multi-catch is **implicitly final** and cannot be reassigned.

```java
import java.io.IOException;

class MultiCatchExample {
    static void run(boolean ioFailure) throws IOException {
        try {
            if (ioFailure) {
                throw new IOException("I/O");
            }
            throw new IllegalArgumentException("Tham số");
        } catch (IOException | IllegalArgumentException e) {
            throw e;
        }
    }
}
```

This is an illustrative class **without `main`**. `run` declares `IOException` because it is a checked exception, whereas `IllegalArgumentException` is unchecked and does not require declaration. A multi-catch `catch` block still receives only **one object** at runtime; `throw e` rethrows that object.

You cannot use multi-catch with two types where one is a subclass of the other (such as `IOException | Exception`) because overlapping type alternatives are invalid.

## 9. Do Not Confuse Rethrow with Retry

The two English words *rethrow* and *retry* look similar, but their meanings are completely different:

- **Rethrow**: throws the **exception signal** again so another layer can handle it. The previously failing statement does not automatically run again.
- **Retry**: actively **re-executes the operation** (calling the method again, looping, or resending a request), typically after checking that the error is transient.

Example:

```java
try {
    saveOrder();
} catch (IllegalStateException e) {
    recordFailure(e);
    throw e; // Does not call saveOrder() again
}
```

This is an illustrative outline. If `saveOrder()` already wrote data and then failed when returning the result, an uncontrolled retry could create duplicate data. `throw e` only forwards the error; it does not repeat the transaction.

When a real retry is needed, you must determine which error types are recoverable, the retry count, timeout/backoff, the operation's idempotency, and any side effects already completed. Use `throw e` when handling capacity is exhausted and the operation still fails—do not mistake it for a retry mechanism.

## 10. How Does `throw e` in `catch` Interact with `finally`?

A `finally` block attached to `try` normally executes when leaving `try/catch`, even when `catch` rethrows the exception:

```java
try {
    operation();
} catch (RuntimeException e) {
    auditFailure(e);
    throw e;
} finally {
    releaseLocalState();
}
```

This is illustrative code; the helper methods must be defined to run it. When `throw e` occurs, `releaseLocalState()` is called while exiting the construct, and then the exception continues propagating **if `finally` completes normally**.

Two essential warnings:

- If `finally` throws a new exception, the new error can become the escaping exception, **masking the original error** that was being rethrown.
- If `finally` executes `return`, it can override throwing the exception, causing the caller to no longer see the original error.

Therefore, avoid placing `return` or unintended `throw` statements inside `finally`. When managing `AutoCloseable` resources, prefer `try-with-resources` to get a clear closing order and preserve suppressed exceptions when both the `try` body and `close()` fail.

## 11. Rethrowing Combined with `try-with-resources`

For `AutoCloseable` resources, rethrowing does not exempt you from cleanup responsibilities. When leaving a `try-with-resources` block, successfully initialized resources are closed in **reverse order**. Depending on where `catch` is placed, resources may already be closed before the handler receives the error.

Save the following Java 17+ program as **`RethrowResourceDemo.java`**:

```java
public class RethrowResourceDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
        }
    }

    static void work() {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("Dữ liệu lỗi");
        } catch (IllegalArgumentException e) {
            System.out.println("Ghi nhận trong work");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IllegalArgumentException e) {
            System.out.println("Main: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 RethrowResourceDemo.java
java RethrowResourceDemo
```

**Exact stdout:**

```text
Đóng tài nguyên
Ghi nhận trong work
Main: Dữ liệu lỗi
```

The resource is closed **before** the `catch` block directly attached to `try-with-resources` executes. Then `throw e` forwards the exact original exception up to `main`.

If `close()` also throws an exception while the `try` body has already thrown another exception, the closing error is typically recorded in `e.getSuppressed()` on the primary exception. The `throw e` statement preserves the primary object (along with its existing suppressed list), so outer layers can inspect both the primary error and the closing error. For comprehensive diagnostics, do not mechanically ignore suppressed exceptions.

## 12. Common Mistakes When Using `throw e`

### 12.1. Writing `catch` Only to Rethrow

```java
try {
    process();
} catch (Exception e) {
    throw e;
}
```

This is an illustrative outline, with appropriate `throws` required if checked exceptions are involved. If the handler does not record context, perform specific cleanup, or translate the contract, the `catch` block usually adds no value. You can let the exception propagate naturally; place cleanup in `try-with-resources` or `finally` when truly needed.

### 12.2. Duplicate Logging at Every Layer

```text
Repository: log full stack trace then throw e
Service: log full stack trace then throw e
Controller: log full stack trace then return error
```

One error can turn into three long log entries that are hard to follow and costly to operate. Choose a logging point that has sufficient context, use a correlation/request ID where appropriate, and consider avoiding duplicate logs. Rethrowing preserves the exception, but it **does not require** every layer to log it.

### 12.3. Calling `throw new ...` and Thinking It Is Still the Same Object

`throw new RuntimeException(e)` creates a **new wrapper** with `e` as its cause. It is not equivalent to `throw e`. If the goal is simply to propagate as is, use `throw e`.

### 12.4. Reassigning `e` and Then Throwing

```java
// Wrong idea if the goal is to preserve the exact original exception:
catch (IllegalArgumentException e) {
    e = new IllegalArgumentException("Thông điệp khác");
    throw e;
}
```

This is an illustrative fragment inside `try/catch`, not a standalone program. The handler above throws a **new** object, losing the original error's identity and not automatically preserving the old cause/stack trace. With checked exceptions, reassigning the `catch` variable can also disable precise rethrow.

### 12.5. Losing the Cause in an Error-Wrapping Layer

If you need to change the exception type, actively preserve the cause:

```java
// Does not preserve the cause:
throw new IllegalStateException("Không thể lưu đơn hàng");

// Preserves the cause (assuming e is the original exception):
throw new IllegalStateException("Không thể lưu đơn hàng", e);
```

These are two **independent illustrative options**, not meant to be placed sequentially in one execution block. The second creates a new wrapper while keeping `e` in `cause`. When you only need to propagate the original unmodified, `throw e` remains the most direct way to preserve information.

### 12.6. Catching the Wrong Type or Swallowing `Error`

Do not use `catch (Throwable e)` followed by `throw e` just to "catch everything" without a clear architectural reason. `Throwable` includes `Error`, and some types such as `OutOfMemoryError` may leave the system in an unfit state to continue work. If catching broadly at a special monitoring boundary, handling and forwarding must follow the contract; ordinary business code should choose specific types.

### 12.7. Misunderstanding the Stack Trace

`throw e` does not generate a stack trace at the rethrow site. Therefore, if logs rely only on the first line of the stack trace to find the "rethrow point," they may miss where an intermediate layer decided to forward the error. When more context is needed, log at the proper boundary or wrap with a cause according to the contract. Do not call `fillInStackTrace()` just to pretend the original error arose somewhere else.

### 12.8. Using Rethrow to Handle All Business Outcomes

An out-of-stock order, expired coupon code, or empty search result may be an **expected business outcome**, not a technical error to throw across layers. If the contract returns a result with status, keep that model; only use exceptions when truly appropriate to the API's semantics and handling responsibilities.

## 13. Choosing `throw e`, `throw new ...`, or Handling Locally

The question to ask is: **Has the current layer finished handling the consequences of the exception, and what kind of signal does the caller expect?**

| Situation | Usually appropriate choice | Consequence |
| --- | --- | --- |
| No work needed at this layer | Do not create an unnecessary `catch` | Exception propagates naturally |
| Need to record context while keeping original error type | `catch (... e) { ...; throw e; }` | Same object propagates to caller |
| Current layer knows how to recover safely | `catch` and handle completely, no rethrow | Call can complete normally |
| Higher-layer API needs an error at a different abstraction level | `throw new DomainOrServiceException(..., e)` | Creates new exception, keeps original error as cause |
| Failure is an expected business outcome | Return an explicit value/result type if the contract chooses that approach | Caller handles it on the normal branch |
| Checked exception still needs to pass through an intermediate layer | `throw e` and matching `throws` | Checked exception obligation remains |
| Need controlled retry | Write a bounded retry policy understanding side effects; rethrow if exhausted | Retry is a new action, not caused by `throw e` |

A useful design principle: **do not use rethrow to hide responsibility, but also do not force a lower layer to decide a response when it lacks sufficient information.** The caller needs an accurate signal to know whether the operation completed or is still in an error state.

## 14. Knowledge Check Questions

**Question 1.** In `catch (IOException e) { throw e; }`, does `throw e` create a new `IOException`?  
**Answer:** No. It rethrows the exact object referenced by `e`. The caller can receive that very same instance.

**Question 2.** After `throw e` in a handler, does the statement immediately following it in the handler execute?  
**Answer:** Not along that execution path. The exception propagates outward again; directly unreachable code may be flagged as an error by the compiler.

**Question 3.** Does `throw e` change the message, cause, and stack trace?  
**Answer:** The statement itself does not create a new object or modify them. Other code may have modified mutable properties of the object, and certain JVM mechanisms have exceptions regarding stack trace representation.

**Question 4.** Does `catch (Exception e) { throw e; }` always force the method to declare `throws Exception`?  
**Answer:** No. When `e` is `final` or effectively final, the precise rethrow rule can allow the compiler to narrow the set of checked exceptions that can be thrown from `try`; for example, only `throws IOException` may be needed if that is the relevant checked type.

**Question 5.** Why is `throw new IllegalStateException("...", e)` not equivalent to `throw e`?  
**Answer:** It creates a new instance, changes the top-level type, and keeps `e` as the cause; `throw e` preserves the original exception's instance and runtime type.

**Question 6.** If `finally` throws a new exception while `catch` is executing `throw e`, which exception does the caller receive?  
**Answer:** The new exception from `finally` can replace the exception being rethrown, masking the original error. That is why you should not accidentally throw new errors during cleanup.

**Question 7.** If a `try-with-resources` handler rethrows with `throw e`, are the resources already closed?  
**Answer:** The resources declared in that `try-with-resources` statement have already been attempted to be closed before the `catch` handler attached to that construct runs; closing errors may be recorded as suppressed.

**Question 8.** Does `throw e` automatically retry the operation that just failed?  
**Answer:** No. Rethrowing forwards the error signal to another layer; retrying requires code that invokes the operation again according to a policy.

**Question 9.** Is declaring `throws` required when rethrowing an unchecked exception?  
**Answer:** No. `RuntimeException`, `Error`, and their subclasses are unchecked, regardless of whether they are thrown initially or rethrown.

**Question 10.** If a `catch` block cannot recover, has no additional information, and only calls `throw e`, should that handler be kept?  
**Answer:** Usually not. Letting the exception propagate on its own is simpler, as long as cleanup and contracts are ensured in the appropriate places.

## 15. Checklist When Reviewing Code with `throw e`

When reading a handler that rethrows an exception, check for yourself:

1. **Error source:** Which operation did this exception come from, what is its actual runtime type, and is it checked or unchecked?
2. **Handler work:** What useful work does this layer do before rethrowing? Is it logging the same error too many times?
3. **Identity and data:** Is `e` preserved intact, or was a new instance accidentally created/assigned? Have message, cause, stack trace, or suppressed exceptions been altered in a way that hurts diagnostics?
4. **Contract:** Has the method declared the necessary checked exceptions? Is it safely leveraging precise rethrow without reassigning the `catch` parameter?
5. **Execution flow:** Are any statements after the throw point skipped? Where does the caller handle it, and could `finally`/cleanup mask the original exception?
6. **Recovery:** Can the caller handle the error, or does it just keep throwing endlessly? Is there a final point of responsibility at the application boundary?
7. **Data model:** Is this an abnormal error condition or a valid business outcome that should be represented by an explicit value?
8. **Testing:** Have you tested the rethrow path, the caller's catch path, cleanup on error, and checked exceptions in the signature?

## 16. Conclusion

**`throw e` rethrows the same exception object that was caught.** It preserves the original exception's identity and runtime type, typically retains its message, cause, and stack trace information, and terminates the current handler abnormally so the error continues up to a layer that can handle it. This statement **does not** automatically retry the operation, **does not** create a new wrapper, and **does not** mean the current layer recovered successfully.

When the exception is checked, `catch-or-declare` must still be satisfied; Java's *precise rethrow* mechanism allows some handlers to catch a broad type while declaring a narrower set of checked exceptions, provided the `catch` parameter is not reassigned. When you need to change abstraction layers or messages, use a new wrapper **with a cause** rather than confusing it with a raw rethrow. And when there is nothing to do before rethrowing, letting the exception propagate naturally is usually the cleaner design.

The key principle to decide is: **handle when you know how to recover; rethrow when you must preserve the original error for a responsible layer; wrap when the new layer's contract requires a different kind of signal.**

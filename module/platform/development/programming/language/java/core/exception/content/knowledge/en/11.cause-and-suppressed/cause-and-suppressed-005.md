# Distinguishing `cause` and `suppressed exception` in Java

> **Topic:** Java Core → Exception → Cause and suppressed exceptions. A `Throwable` object can carry a **cause** via `getCause()` and simultaneously carry **recorded secondary exceptions** via `getSuppressed()`. These two independent mechanisms answer different questions: **cause** answers “which error led to the creation of the current error?”, whereas **suppressed** answers “what secondary errors occurred while a primary error was retained?”. In Java, try-with-resources since Java 7 is the classic case that automatically creates a suppressed relationship when both the `try` body and `close()` fail.

## 1. At a glance: two different relationships

Suppose a request-handling service encounters an `IOException` while reading data, wraps it into an `IllegalStateException` with business context, and at the same time cleaning up another resource also fails.

```text
IllegalStateException: Không hoàn tất yêu cầu
├── cause: IOException: Không đọc được nguồn
└── suppressed: IOException: Không đóng được tài nguyên
```

Here:

- `IllegalStateException` is the **current exception** that the caller can receive.
- `getCause()` points to `IOException("Không đọc được nguồn")`: the cause attached when creating/initializing the wrapper.
- `getSuppressed()` returns an array containing `IOException("Không đóng được tài nguyên")`: the secondary error recorded without replacing the current exception.
- The caller does not automatically get two `catch` branches for cause and suppressed. **A `catch` handler is selected based on the actual type of the exception being thrown**, without automatically unwrapping `cause` or iterating over `suppressed`.

A `Throwable` may have only a cause, only suppressed exceptions, both, or neither relationship.

### 1.1. Core comparison table

| Criterion | `cause` | `suppressed exception` |
| --- | --- | --- |
| Question answered | “Which error caused this error?” | “Which other errors need to be recorded without replacing the primary error?” |
| API to read | `Throwable.getCause()` | `Throwable.getSuppressed()` |
| Return type | `Throwable` or `null` | `Throwable[]`, possibly empty |
| How it is attached | Constructor taking `cause` or `initCause(...)` | `addSuppressed(...)` or automatically by try-with-resources |
| Direct count | At most one direct cause | Can have multiple direct suppressed exceptions |
| Common relationship | Low-level/infrastructure error wrapped into a high-level error | Resource-closing error when a primary error already exists |
| Does it change the thrown exception type? | No | No |
| Does it participate in `catch` matching? | No | No |
| Structure | A linked chain of causes (cause chain) | A list attached to each Throwable; each element may have its own cause/suppressed |
| Always automatic? | No; must be attached/constructed by the API | No; try-with-resources attaches it automatically under matching conditions |

**Way to remember:** `cause` expresses a **causal relationship**; `suppressed` expresses **failures retained alongside the primary error**. You should not call an exception in `getSuppressed()` a “second cause” because that is a different data relationship.

## 2. Background: what information does `Throwable` store?

In Java, `java.lang.Throwable` is the root class of `Exception` and `Error`. It provides useful APIs:

- `getMessage()`: message describing the error.
- `getCause()`: the object that caused this error, if set.
- `getSuppressed()`: array of secondary exceptions recorded.
- `getStackTrace()`: the `StackTraceElement`s belonging to the Throwable's own trace.
- `printStackTrace()`: prints a human-readable error report, which may include cause and suppressed.
- `initCause(Throwable cause)`: sets the cause in cases where the API allows it.
- `addSuppressed(Throwable exception)`: attaches a secondary exception.

This information is **not a flat structure**. Each `Throwable` has its own message and stack trace; `cause` points to another Throwable; the suppressed array can contain multiple Throwables, and each element has its own stack, cause, or suppressed exceptions.

### 2.1. Cause is not a `StackTraceElement`

`getCause()` returns **a Throwable object**, not a stack frame. The wrapper exception and the cause usually have two separate traces: the wrapper's trace reflects where the wrapper was created, and the cause's trace reflects where the original error was recorded.

Similarly, `getSuppressed()` returns **Throwable objects**, not stack frames or string messages. When detailed analysis is needed, iterate over the objects and inspect their message, type, and stack as needed.

## 3. `cause`: the cause that led to the current exception

Common scenario: a file-reading layer API throws `IOException`, while the service layer wants to report a more meaningful error to the caller. Instead of losing the original exception, the service layer creates a wrapper:

```java
try {
    readSettings();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Không tải được cấu hình", original);
}
```

This is an illustrative snippet; `readSettings()` must be defined. Here:

1. `original` is the caught `IOException` object.
2. `new IllegalStateException("...", original)` creates a **new object** and attaches `original` as its cause.
3. `throw` throws the **wrapper**, not `original` directly.
4. The caller can catch `IllegalStateException` or a supertype, then use `getCause()` to trace back to the origin.

**Meaning:** the cause preserves the trace of the lower-level failure that has been translated into a higher-level context, rather than a “second error occurring in parallel”.

### 3.1. Java 17 — runnable example of cause and wrapper

Create the file **`CauseWrapperDemo.java`**:

```java
import java.io.IOException;

public class CauseWrapperDemo {
    static void loadFile() throws IOException {
        throw new IOException("Nguồn không đọc được");
    }

    static void loadService() {
        try {
            loadFile();
        } catch (IOException original) {
            throw new IllegalStateException(
                    "Không tải được dịch vụ", original);
        }
    }

    public static void main(String[] args) {
        try {
            loadService();
        } catch (IllegalStateException e) {
            System.out.println("Đang bắt: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac -encoding UTF-8 CauseWrapperDemo.java
java CauseWrapperDemo
```

Exact stdout:

```text
Đang bắt: IllegalStateException
Message: Không tải được dịch vụ
Cause: IOException
Cause message: Nguồn không đọc được
Suppressed count: 0
```

The program produces no secondary error, so the wrapper's suppressed array is empty. `getCause()` returns the exact object passed to the wrapper constructor, preserving the type and message from the file-reading layer.

### 3.2. Choosing the wrapper type deliberately

`IllegalStateException` is just an example choice. In real APIs, you can use a custom exception, such as `ConfigurationLoadException`, to express the contract. Do not automatically wrap every `IOException` into a `RuntimeException` just to “avoid” checked exceptions. Consider who is able to handle the error, the API boundary, and what cause the caller needs to see.

A sensible wrapper structure is typically:

```java
class ConfigurationLoadException extends Exception {
    ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a **valid class declaration**, without `main`. Callers of a method throwing this checked type must catch or declare it according to Java rules.

## 4. `initCause()` and the limits of the cause relationship

Besides constructors accepting a cause, `Throwable` has the method:

```java
Throwable initCause(Throwable cause)
```

This method allows setting the cause **once** when the object has not yet had its cause initialized. This API is necessary when using exception classes/constructors that do not accept a cause.

### 4.1. Java 17 — setting the cause exactly once

Create the file **`InitCauseDemo.java`**:

```java
import java.io.IOException;

public class InitCauseDemo {
    public static void main(String[] args) {
        IOException root = new IOException("Lỗi đọc");
        IllegalArgumentException wrapper =
                new IllegalArgumentException("Không hợp lệ");

        wrapper.initCause(root);
        System.out.println("Cause: "
                + wrapper.getCause().getClass().getSimpleName());

        try {
            wrapper.initCause(new IOException("Lỗi mới"));
        } catch (IllegalStateException e) {
            System.out.println("Gắn lần hai: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 InitCauseDemo.java
java InitCauseDemo
```

Stdout:

```text
Cause: IOException
Gắn lần hai: IllegalStateException
```

After the first call, the cause has been initialized. Calling `initCause(...)` a second time is rejected rather than silently replacing the previous cause.

### 4.2. When can `initCause()` not be called?

- If the constructor has already initialized the cause (even a constructor taking `null` that has marked the cause state as initialized), `initCause(...)` may throw `IllegalStateException`.
- A Throwable cannot be used as its own cause: `e.initCause(e)` is invalid and throws `IllegalArgumentException`.
- Prefer a constructor that accepts a cause if the API provides one; do not create a wrapper and forget to attach the cause.
- Only use `initCause()` when there is a specific compatibility or API design reason; do not treat it as a free setter for changing error history.

**Important distinction:** `getCause() == null` does not by itself prove that `initCause(...)` is still allowed. An exception may have already had its cause initialized to `null`, so the API no longer allows changing it.

## 5. `suppressed exception`: a secondary exception recorded without replacing the primary error

A Throwable can receive multiple suppressed exceptions:

```java
Throwable primary = new IllegalStateException("Lỗi chính");
primary.addSuppressed(new java.io.IOException("Lỗi đóng A"));
primary.addSuppressed(new java.io.IOException("Lỗi đóng B"));
```

This is an illustrative snippet inside a method. If you iterate over `primary.getSuppressed()`, you see two `IOException` objects. However:

- `primary.getCause()` can still be `null`.
- `getSuppressed()[0]` does not automatically become the cause.
- `addSuppressed(...)` **does not throw** the secondary exception in Java's control flow. It only stores the information on the primary object.
- An active `catch` handler does not automatically switch to handling a suppressed exception as a new exception.
- The secondary objects retain their own messages and stack traces for analysis if needed.

### 5.1. Why is suppressed needed?

In a two-phase operation, the original error occurs during **work**, and then another error occurs during **cleanup**. If the code only keeps the last error, the most important information about the initial failure can be lost.

Example:

```text
Đọc dữ liệu thất bại         → IOException("read failed")   [primary]
Đóng luồng cũng thất bại      → IOException("close failed")  [suppressed]
```

Java 7 added the suppressed mechanism to `Throwable` and uses it in try-with-resources. It preserves the work error **and** avoids losing the close error, without having to overwrite the first error with the second.

### 5.2. Java 17 — calling `addSuppressed` directly

Create the file **`ManualSuppressedDemo.java`**:

```java
import java.io.IOException;

public class ManualSuppressedDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("Xử lý thất bại");

        primary.addSuppressed(new IOException("Đóng A thất bại"));
        primary.addSuppressed(new IOException("Đóng B thất bại"));

        System.out.println("Primary: " + primary.getMessage());
        System.out.println("Cause: " + primary.getCause());
        System.out.println("Suppressed count: "
                + primary.getSuppressed().length);

        for (Throwable e : primary.getSuppressed()) {
            System.out.println("Suppressed: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ManualSuppressedDemo.java
java ManualSuppressedDemo
```

Stdout:

```text
Primary: Xử lý thất bại
Cause: null
Suppressed count: 2
Suppressed: Đóng A thất bại
Suppressed: Đóng B thất bại
```

`getCause()` returns `null` because the code did not set a cause; the two secondary errors are kept separately. This program does not throw `primary` — we only create the object and print information to observe the API. In practice, a Throwable is typically thrown/caught and then has suppressed exceptions attached as required by handling logic.

## 6. Try-with-resources: where suppressed exceptions arise automatically

This is the scenario you must understand most clearly.

```java
try (MyResource resource = open()) {
    perform(resource);
}
```

This is sample code; `MyResource`/`open`/`perform` are not defined.

If `perform(...)` throws a Throwable **P**, Java still calls `resource.close()`. If `close()` also throws a Throwable **C**, TWR prioritizes keeping **P as the primary** and attaches **C to P's suppressed list**. Therefore:

- An outer `catch` receives the propagating object P.
- `P.getSuppressed()` contains C if suppressed attachment occurs under normal rules.
- `P.getCause()` does not automatically change to C.
- Error C does not separately trigger a `catch` based on C's type, because C does not become the primary exception flying out.

If the body succeeds but `close()` fails, the close error can become the **primary** because there was no prior Throwable from the body to take precedence.

### 6.1. Java 17 — both body and close fail

Create the file **`TwrBodyAndCloseDemo.java`**:

```java
import java.io.IOException;

public class TwrBodyAndCloseDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Xử lý dữ liệu");
            throw new IllegalStateException("Dữ liệu không hợp lệ");
        } catch (Exception e) {
            System.out.println("Primary type: "
                    + e.getClass().getSimpleName());
            System.out.println("Primary message: " + e.getMessage());
            System.out.println("Cause: " + e.getCause());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed type: "
                    + e.getSuppressed()[0].getClass().getSimpleName());
            System.out.println("Suppressed message: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run on Java 17:

```bash
javac -encoding UTF-8 TwrBodyAndCloseDemo.java
java TwrBodyAndCloseDemo
```

Exact stdout:

```text
Xử lý dữ liệu
Đóng tài nguyên
Primary type: IllegalStateException
Primary message: Dữ liệu không hợp lệ
Cause: null
Suppressed count: 1
Suppressed type: IOException
Suppressed message: Không đóng được
```

This is an example with **no cause**, but **one suppressed exception**. It proves why “whichever error is thrown first is the cause, and the second is suppressed” is not an accurate definition: the primary body error is not wrapped, the close error is secondary, and **no cause chain is established**.

### 6.2. Important rule for `catch` handlers

In the example, `catch (Exception e)` receives `IllegalStateException`, because that is the primary object being thrown. Having `IOException` as suppressed does **not** cause the program to invoke `catch (IOException)`.

If you write separate handlers, `catch (IllegalStateException)` receives the body error; `catch (IOException)` can receive the close error if the close error becomes primary **in the scenario where the body succeeds**. In a real source file, the compiler also checks the checked exception sources from `close()`.

## 7. If the body succeeds but closing fails: close becomes primary

Create **`TwrClosePrimaryDemo.java`**:

```java
import java.io.IOException;

public class TwrClosePrimaryDemo {
    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingClose r = new FailingClose()) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwrClosePrimaryDemo.java
java TwrClosePrimaryDemo
```

Stdout:

```text
Thân thành công
Đang đóng
Primary: Lỗi đóng
Suppressed count: 0
```

**Explanation:** there is no error from the `try` body, so `IOException("Lỗi đóng")` is the primary exception exiting TWR. It cannot be “suppressed under a body primary” because no such primary exists.

This matters for writers, buffered output, transaction-adjacent resources, and APIs where `close()` may perform final work. “Printed a success line in the try body” does not guarantee the operation succeeded through the end of the resource lifecycle.

## 8. Multiple resources: suppressed can be a list

Java initializes resources in `try (...)` in declaration order (left to right) and closes them **in reverse declaration order** (right to left).

With two resources A and B:

```text
Khởi tạo A → Khởi tạo B → Thân try
                               ↓
                            Đóng B
                               ↓
                            Đóng A
                               ↓
                        catch ở bên ngoài
```

If the body has already thrown primary P, and closing both B and A fails, P can have two suppressed exceptions, typically in closing order B then A.

### 8.1. Java 17 — two secondary close errors alongside a body error

Create **`TwrMultipleSuppressedDemo.java`**:

```java
import java.io.IOException;

public class TwrMultipleSuppressedDemo {
    static final class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Failing a = new Failing("A");
             Failing b = new Failing("B")) {
            System.out.println("Thân try");
            throw new IllegalArgumentException("body");
        } catch (Exception e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwrMultipleSuppressedDemo.java
java TwrMultipleSuppressedDemo
```

Stdout:

```text
Mở A
Mở B
Thân try
Đóng B
Đóng A
Primary: body
Suppressed: close B
Suppressed: close A
```

When both the body and both closes fail, the body error remains primary. Both close errors are stored in the suppressed array in the order B → A, matching TWR's resource closing order.

### 8.2. What if the body succeeds but multiple closes fail?

When there is no body error, the exception from the **first resource to be closed** can become primary; exceptions thrown while closing subsequent resources are suppressed onto it.

In the A and B example, B closes first, so `IOException("close B")` is typically primary, and `IOException("close A")` is suppressed. Do not assume the suppressed exception is always “the second resource's close error” in declaration order; read the **reverse closing order**.

### 8.3. What if initializing the second resource fails?

TWR still closes the resources **that were previously initialized successfully**. If initializing B throws error P and then `A.close()` throws C, P is typically primary and C is suppressed.

A resource that was not successfully initialized is **not** closed by the outer TWR as a managed object. If a constructor opens an auxiliary resource internally and throws halfway through, internal cleanup is the responsibility of that implementation.

## 9. Cause and suppressed can coexist

There is no rule forbidding a `Throwable` from having both a cause and suppressed exceptions. For example: a service layer wraps an `IOException` into a service error while also retaining a secondary cleanup error.

Create the file **`CauseAndSuppressedTogetherDemo.java`**:

```java
import java.io.IOException;

public class CauseAndSuppressedTogetherDemo {
    public static void main(String[] args) {
        IOException source = new IOException("Nguồn hỏng");
        IllegalStateException service =
                new IllegalStateException("Dịch vụ thất bại", source);

        service.addSuppressed(new IOException("Dọn tệp lỗi"));
        service.addSuppressed(new IOException("Dọn kết nối lỗi"));

        System.out.println("Current: "
                + service.getClass().getSimpleName());
        System.out.println("Cause: "
                + service.getCause().getMessage());
        System.out.println("Suppressed count: "
                + service.getSuppressed().length);
        System.out.println("Suppressed 0: "
                + service.getSuppressed()[0].getMessage());
        System.out.println("Suppressed 1: "
                + service.getSuppressed()[1].getMessage());
    }
}
```

Run:

```bash
javac -encoding UTF-8 CauseAndSuppressedTogetherDemo.java
java CauseAndSuppressedTogetherDemo
```

Stdout:

```text
Current: IllegalStateException
Cause: Nguồn hỏng
Suppressed count: 2
Suppressed 0: Dọn tệp lỗi
Suppressed 1: Dọn kết nối lỗi
```

**Core point:** `getCause()` is a single value, whereas `getSuppressed()` is an array. Both are read from the **same current object**, `service`.

A suppressed exception can also have **its own cause**. Therefore, when building error-analysis tools, do not assume the structure is always a flat chain. Inspect the relationships per object.

## 10. `getCause()` can form a cause chain

If an exception is wrapped across multiple layers:

```text
ApplicationException("request failed")
    └── cause: ServiceException("load failed")
            └── cause: IOException("read failed")
```

`getCause()` on the outermost exception returns its direct cause, not automatically the deepest error. If you need to go deeper, traverse layer by layer.

### 10.1. Java 17 — traversing a cause chain

Create **`CauseChainDemo.java`**:

```java
import java.io.IOException;

public class CauseChainDemo {
    public static void main(String[] args) {
        IOException root = new IOException("read failed");
        IllegalStateException middle =
                new IllegalStateException("load failed", root);
        RuntimeException outer =
                new RuntimeException("request failed", middle);

        Throwable current = outer;
        int depth = 0;

        while (current != null) {
            System.out.println(depth + ": "
                    + current.getClass().getSimpleName()
                    + " / " + current.getMessage());
            current = current.getCause();
            depth++;
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CauseChainDemo.java
java CauseChainDemo
```

Stdout:

```text
0: RuntimeException / request failed
1: IllegalStateException / load failed
2: IOException / read failed
```

The example uses a normal acyclic cause chain. When writing analysis tools for **untrusted or custom-structured** Throwables, use a visited-object set if recursing through both cause and suppressed to avoid infinite loops. Avoid inferring “greater depth means more severe error”; the chain only reflects wrapping steps.

### 10.2. Should you always display the deepest cause?

Not by default. The outermost error carries useful **business context**, such as failing to load configuration; the root error carries technical details, such as failing to read a file. A good report can keep both. Showing only the root cause to end users can sometimes leak internal details or lose high-level context.

## 11. How does `printStackTrace()` display both relationships?

`Throwable.printStackTrace()` is a human-readable display utility. In a typical report:

- The current Throwable appears on the first line with its trace.
- Suppressed exceptions are annotated with **`Suppressed:`** and displayed at the appropriate nesting level.
- The cause is displayed via **`Caused by:`** along with the cause's stack trace.
- Common stack frames may be abbreviated as **`... N more`**.

Illustrative example:

```text
java.lang.IllegalStateException: Dịch vụ thất bại
    at example.Service.run(Service.java:42)
    Suppressed: java.io.IOException: Lỗi đóng
        at example.Resource.close(Resource.java:18)
Caused by: java.io.IOException: Nguồn hỏng
    at example.Reader.read(Reader.java:27)
```

**This is an illustrative diagram**, not the fixed stdout/stderr of a program. Source paths, line numbers, frame counts, and abbreviation order depend on the Throwable structure and execution environment.

If `printStackTrace()` is called with no arguments, Java typically prints to `System.err`. You should not compare stack traces verbatim in unit tests by line numbers and `toString()` strings when what you need to verify is the exception type or cause/suppressed relationship.

### 11.1. `getStackTrace()` does not replace `getCause()` and `getSuppressed()`

`getStackTrace()` returns **the `StackTraceElement[]` array of the current Throwable itself**, without merging traces of other exceptions into one array. To inspect cause/suppressed relationships:

```java
Throwable cause = failure.getCause();
Throwable[] suppressed = failure.getSuppressed();
StackTraceElement[] ownFrames = failure.getStackTrace();
```

This is an illustrative snippet assuming `failure` is a `Throwable`. The three APIs return three different kinds of data. Depending on logging requirements, use a logger that records the full Throwable object so cause/suppressed are not lost, instead of logging only `failure.getMessage()`.

## 12. Rules and common pitfalls of `addSuppressed()`

`addSuppressed(Throwable exception)` does not accept every argument.

- `addSuppressed(null)` is invalid; throws `NullPointerException`.
- `e.addSuppressed(e)` is invalid because it is self-suppression; throws `IllegalArgumentException`.
- **Multiple Throwables** can be attached to the same primary object.
- The API does not automatically conclude that every attached element is a close error. Code can intentionally attach an exception from another secondary step when the contract warrants it.
- Do not use `addSuppressed` as a container for ordinary validation errors when an error-result structure with a list of messages expresses it more clearly.

### 12.1. Java 17 — checking invalid arguments

Create the file **`SuppressedValidationDemo.java`**:

```java
public class SuppressedValidationDemo {
    public static void main(String[] args) {
        Throwable primary = new IllegalStateException("primary");

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException e) {
            System.out.println("null: "
                    + e.getClass().getSimpleName());
        }

        try {
            primary.addSuppressed(primary);
        } catch (IllegalArgumentException e) {
            System.out.println("self: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Suppressed count: "
                + primary.getSuppressed().length);
    }
}
```

Run:

```bash
javac -encoding UTF-8 SuppressedValidationDemo.java
java SuppressedValidationDemo
```

Stdout:

```text
null: NullPointerException
self: IllegalArgumentException
Suppressed count: 0
```

Both invalid attachment operations are rejected, so the suppressed list remains empty.

### 12.2. The `getSuppressed()` array is a copy

`getSuppressed()` returns a new array; modifying the array held by the caller **does not modify the Throwable's internal list**. Because the elements are references to Throwables, replacing an element in the copied array does not alter the suppressed list inside `primary`. However, the referenced Throwable objects themselves still have their own mutable state, so returning a copied array should not be mistaken for deep-copying every Throwable.

### 12.3. There is no `setSuppressed(...)` API

In the standard API, the addition operation is `addSuppressed(...)`. There is no public setter to replace the entire suppressed list like `setSuppressed(Throwable[])`. If you need an error report where elements can be arbitrarily modified or removed, use a dedicated business data structure instead of trying to turn `Throwable` into a general-purpose container.

## 13. Disabling suppression: advanced case

`Throwable` has a protected constructor:

```java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
```

Subclasses can choose **`enableSuppression = false`**. When suppression is disabled, calling `addSuppressed(...)` does not add the exception to the array; `getSuppressed()` returns an empty array. This case is specialized and usually unnecessary for ordinary business exceptions.

### 13.1. Java 17 — demonstrating disabled suppression

Create the file **`SuppressionDisabledDemo.java`**:

```java
import java.io.IOException;

public class SuppressionDisabledDemo {
    static final class QuietException extends Exception {
        QuietException(String message) {
            super(message, null, false, true);
        }
    }

    public static void main(String[] args) {
        QuietException error = new QuietException("primary");
        error.addSuppressed(new IOException("cleanup"));

        System.out.println("Primary: " + error.getMessage());
        System.out.println("Suppressed count: "
                + error.getSuppressed().length);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SuppressionDisabledDemo.java
java SuppressionDisabledDemo
```

Stdout:

```text
Primary: primary
Suppressed count: 0
```

**Design warning:** disabling suppression can lose very useful resource-closing error information. This feature is meant for specially designed exception scenarios, not as a default optimization.

### 13.2. Does `cause` depend on suppression?

No. The two mechanisms are controlled/configured independently. A Throwable with suppression disabled can still have a cause if its constructor/`initCause` allows it. A Throwable with normal suppression does not automatically have a cause either.

## 14. Chronological order does not mean cause

A common misconception:

> “The first exception is always the cause; the second exception is always suppressed.”

This is **incorrect**.

- In TWR, the exception from the **`try` body** takes precedence as primary when it exists. An exception thrown later in `close()` may be suppressed, **not** the cause.
- When the service layer wraps an infrastructure exception into a business exception, the original error is attached as the cause, even though the wrapping happens **after** the original error was thrown.
- When only `close()` fails, the close error can become **primary** even though it occurred late in the resource lifecycle.
- A Throwable can have both a cause and suppressed exceptions, so you cannot classify them based on “first/second” while ignoring the API semantics.

**Practical rule:** read relationships using **`getCause()`** and **`getSuppressed()`**. Do not infer relationships solely from the order of log lines.

## 15. Errors when using `finally` vs. try-with-resources

Old pattern:

```java
Resource resource = open();
try {
    perform(resource);
} finally {
    resource.close();
}
```

This is an illustrative snippet. If `perform` already threw P and `resource.close()` throws C in `finally`, error C can **mask** error P because `finally` completes abruptly.

TWR:

```java
try (Resource resource = open()) {
    perform(resource);
}
```

When applied properly, TWR automatically attempts to close the resource and attaches error C as suppressed on P when P already exists. That is a major benefit beyond reducing line count.

This does not mean TWR automatically recovers or rolls back: data may already have been modified before the exception occurred. Primary and suppressed mainly preserve **diagnostic information**, whereas business consistency requires transactions, pre-change checks, or appropriate recovery mechanisms.

### 15.1. `finally` still has value

`finally` is useful for tasks outside the `AutoCloseable` protocol, such as recording session status or restoring context. Just avoid closing a TWR resource a second time and avoid `return` or throwing a new error in `finally` if the goal is to preserve the original exception.

If an operation in `finally` can throw, design a dedicated way to record that error without accidentally masking the primary. Do not sprinkle manual `addSuppressed` calls everywhere if TWR already handles `close` according to contract.

## 16. Designing a handling strategy when both types of error data exist

Hypothetical scenario: a file-reading transaction fails, and the logging connection fails during cleanup. The handling design should answer:

1. **What is the primary error?** The type and message of the Throwable being thrown.
2. **What is the cause?** Which exception led to the wrapper at the current layer?
3. **What is in suppressed?** Are there secondary close/cleanup errors that need to be reported?
4. **What is the post-error state?** Resources may be partially closed; business side effects may have already occurred.
5. **Which layer is responsible for handling?** The infrastructure layer may translate errors, the API layer may report failure, and the operations layer may log and alert.

A good strategy usually does **not** catch `Throwable` and turn everything into “OK”. Catch appropriate types or let the error propagate to a boundary, ensuring the failure state is communicated to the caller and preserving cause/suppressed for investigation.

### 16.1. Inspecting relationships without confusing them with control flow

Illustrative method example:

```java
static void inspect(Throwable error) {
    System.out.println("Current: " + error.getMessage());

    Throwable cause = error.getCause();
    if (cause != null) {
        System.out.println("Cause: " + cause.getMessage());
    }

    for (Throwable suppressed : error.getSuppressed()) {
        System.out.println("Suppressed: "
                + suppressed.getMessage());
    }
}
```

This is a method that can be placed inside a class. It only **reads** error relationships; it does not rethrow, does not close resources itself, and does not turn suppressed exceptions into the active exception being handled. If rethrowing is needed, execute `throw` according to the appropriate checked/unchecked contract.

### 16.2. What information should be logged?

At the application boundary, the logger should be able to record the full Throwable object so you do not lose:

- The type and message of the outermost exception.
- The trace and cause chain.
- The suppressed exceptions and their traces.
- Request/job context (in accordance with security and privacy policies).

Logging only `getMessage()` is insufficient when diagnosing complex failures. At the same time, you should not return the full stack trace and cause chain to public clients because it may expose classes, files, call paths, data sources, or sensitive information. Returning a structured error/reference code to the client and storing details in a controlled logging system is usually more appropriate.

## 17. Common mistakes to avoid

| Misconception | Correct fact |
| --- | --- |
| “Cause and suppressed are two names for the same error.” | They are two independent relationships, read through two different APIs. |
| “`getCause()` returns an array of errors.” | It returns a single `Throwable` or `null`. |
| “`getSuppressed()` returns a Throwable or `null`.” | It returns `Throwable[]`, which may be empty. |
| “A `close()` error is always the cause.” | TWR typically attaches a close error as suppressed when a primary already exists. |
| “If the body succeeds and close fails, close is still suppressed.” | When there is no prior primary, the close error can become primary. |
| “If there are suppressed exceptions, `getCause()` cannot have data.” | A Throwable can have both a cause and suppressed exceptions. |
| “`catch(IOException)` automatically catches a suppressed IOException.” | Handlers match against the type of the propagating primary Throwable. |
| “`throw new RuntimeException(e.getMessage())` preserves the cause.” | That only copies the message; a constructor taking `cause` is needed to link the original exception. |
| “`initCause` is a setter you can call as many times as you want.” | By contract, the cause can only be initialized once. |
| “`addSuppressed(null)` is ignored.” | It throws `NullPointerException`. |
| “`e.addSuppressed(e)` is valid to record the same error.” | Self-suppression is forbidden and throws `IllegalArgumentException`. |
| “`getSuppressed()` is a secondary stack trace.” | It holds Throwable objects; each has its own stack. |
| “Having multiple suppressed exceptions means there must be multiple causes.” | A Throwable has at most one direct cause; suppressed is a separate list. |
| “TWR guarantees automatic state rollback.” | TWR manages `close()`; rollback requires a different mechanism. |
| “`printStackTrace()` only prints the wrapper's trace.” | The output typically includes `Caused by` and `Suppressed` to show relationships. |
| “If a close error is suppressed, it does not matter.” | Secondary errors can still indicate resource leaks, incomplete writes, or system issues needing investigation. |
| “A cause chain can be used as a list of all concurrent errors.” | Cause describes a causal chain; use a separate composite structure if you need to store multiple peer business errors. |

## 18. Practice exercises

### Exercise 1 — Identify the relationship types

Given the diagram:

```text
IllegalStateException("service")
  cause → IOException("read")
  suppressed → IOException("closeA")
  suppressed → IOException("closeB")
```

Questions:

1. What does `getCause()` return?
2. What is `getSuppressed().length`?
3. Does `catch(IOException)` automatically catch the primary `IllegalStateException`?
4. Which API do you iterate over to print the close errors?

**Answer:** the cause is `IOException("read")`; suppressed count is `2`; the `IOException` handler does not catch the primary; use `getSuppressed()`.

### Exercise 2 — Changing the TWR scenario

Run `TwrBodyAndCloseDemo`, then remove the statement that throws `IllegalStateException` in the body. Predict the primary type and suppressed count. **Guidance:** only the close error remains, so the primary is typically `IOException` from `close()`, and suppressed is empty.

### Exercise 3 — Adding a third resource

In `TwrMultipleSuppressedDemo`, add resource C at the end of the resource list. Keep the body throwing `IllegalArgumentException`. If A, B, and C all fail to close, predict the closing order and the suppressed array. **Answer:** close order C → B → A; suppressed elements in order `close C`, `close B`, `close A`.

### Exercise 4 — Three-level cause chain

Using `CauseChainDemo`, add a wrapper with the message `"API failed"`. Traverse `getCause()` and print depth, type, and message. Verify that the new wrapper can have the old wrapper as its cause without altering the original stored cause.

### Exercise 5 — `initCause` is not a free setter

In `InitCauseDemo`, explain why the second call to `initCause` is rejected. Then try creating `new IllegalArgumentException("wrapper", root)` and calling `initCause(other)`, and predict why the constructor has already initialized the cause relationship.

### Exercise 6 — Preserving information when wrapping exceptions

Write a `loadConfiguration()` method that calls a reading API that may throw `IOException`. Catch it and throw `ConfigurationLoadException("Cannot load config", e)` using a constructor that accepts a cause. At the caller, print the wrapper type and the cause type. If there is also a cleanup error, clearly distinguish the suppressed mechanism instead of attaching it as a nonsensical new cause.

### Exercise 7 — The suppressed array is a copy

Create `Throwable primary` and attach two suppressed exceptions. Call `getSuppressed()` twice to obtain two arrays. Replace the first element of the first array, then read it again from `primary`. Why is `primary`'s suppressed list unchanged?

### Exercise 8 — Designing logging

An API request encounters an `IllegalStateException` with a file-read error as cause and two suppressed exceptions from cleanup. Design the error response sent to the client and the internal log entry. **Guidance:** the client receives an appropriate error code/correlation id; the logger records the full Throwable without exposing stack traces and internal file paths externally.

### Exercise 9 — Primary error and data integrity

Suppose `writer.write(...)` throws `IOException("write")` and `writer.close()` also throws `IOException("close")`. State the primary and suppressed exceptions when using TWR. Then explain why preserving error information **does not prove** that the file was rolled back or does not contain partially written data.

## 19. Checklist for understanding and proper usage

- [ ] Can I explain that `cause` is the cause attached to the current error, while `suppressed` is a secondary error stored alongside it?
- [ ] Do I know that `getCause()` returns a Throwable or `null`, while `getSuppressed()` returns a non-null array?
- [ ] Do I understand that `getCause()` can form a wrapper chain, while suppressed can hold multiple Throwables?
- [ ] Do I use constructors taking `cause` and avoid losing the original error when crossing layers?
- [ ] Do I understand that `initCause` can only be called validly once under appropriate conditions?
- [ ] Do I know that `addSuppressed(null)` and self-suppression are invalid?
- [ ] Can I distinguish TWR's primary exception from suppressed close errors?
- [ ] Do I understand that when the TWR body succeeds but `close` fails, the close error can become primary?
- [ ] Do I know that with multiple resources, Java closes them in reverse declaration order and can accumulate multiple suppressed exceptions?
- [ ] Do I check `getSuppressed()` instead of only reading the primary's message when cleanup also fails?
- [ ] Do I understand that `catch` matches based on the type of the exception being thrown, not on cause or suppressed?
- [ ] Do I avoid using `finally` to close a TWR resource again or accidentally masking the primary error?
- [ ] Do I avoid confusing exception-information preservation with business state rollback/recovery?
- [ ] Do I log the full Throwable in the appropriate place without exposing internal stack traces to public clients?
- [ ] Have I tested scenarios with only cause, only suppressed, both, neither, and multiple close errors?

**Final takeaway:** **Cause** links the current error to its **originating cause** (`getCause()`, constructor taking cause, or `initCause()`); **suppressed exceptions** retain **secondary failures** (`getSuppressed()`, `addSuppressed()`), especially when try-with-resources closes resources after the body has already failed. Both relationships can coexist, neither alters `catch` handler matching on its own, and both must be preserved when diagnosing failures.

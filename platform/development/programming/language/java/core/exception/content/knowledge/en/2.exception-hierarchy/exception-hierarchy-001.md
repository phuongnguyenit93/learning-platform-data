# `Throwable` — the Root of the Exception Hierarchy in Java

In Java, `java.lang.Throwable` is **the common root class of all objects that can be thrown with `throw` and caught with `catch`**. Its two direct branches are `Error` and `Exception`. Understanding the position of `Throwable` helps distinguish application-level errors that need to be handled, serious runtime environment errors, the compiler's exception-checking rules, and how Java preserves diagnostic information.

## 1. Viewing the Hierarchy from the Root

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    │   ├── OutOfMemoryError
    │   └── LinkageError
    │       └── NoClassDefFoundError
    └── java.lang.Exception
        ├── IOException
        ├── SQLException
        └── RuntimeException
            ├── NullPointerException
            ├── IllegalArgumentException
            └── IndexOutOfBoundsException
```

This is a **representative subset** of the inheritance tree, not an exhaustive list of all exception classes. In Java, `Throwable` extends `Object` and implements `Serializable`. Every class below it is also a `Throwable` by the *is-a* relationship: an `IllegalArgumentException` is a `RuntimeException`, an `Exception`, and a `Throwable`.

| Type | Characteristics | Typical Handling |
| --- | --- | --- |
| `Throwable` | Common root; holds the message, cause, stack trace, and suppressed exceptions. | Serves as the foundation for the exception mechanism; rarely instantiated or declared directly in application APIs. |
| `Error` | Represents serious or abnormal problems that an application usually cannot recover from locally. | Typically allowed to propagate for root-cause investigation; not caught broadly to pretend recovery. |
| `Exception` (excluding `RuntimeException`) | Usually represents anticipated and recoverable situations, such as I/O errors. | Must be caught with `catch` or declared with `throws` if thrown from a method. |
| `RuntimeException` | Usually associated with invalid arguments, invalid state, or programming bugs. | Not required to be caught with `catch` or declared with `throws`; handled at a boundary with sufficient context or fixed at the root cause. |

**Checked vs. unchecked is determined by inheritance type, not by severity or class name:**

- **Unchecked:** `RuntimeException` and its subclasses; `Error` and its subclasses.
- **Checked:** the remaining subclasses of `Throwable`, including `Throwable` itself, `Exception`, and subclasses of `Exception` outside the `RuntimeException` branch.

For example, `IOException` is checked, whereas `IllegalArgumentException` and `OutOfMemoryError` are unchecked. The fact that `Error` is unchecked does **not** mean its real-world impact can be ignored.

## 2. How Do `throw`, `throws`, and `catch` Relate to `Throwable`?

`throw` throws **an object** of type `Throwable` or a subclass. `throws` is placed on a method declaration to describe the **exception types** that may propagate out. `catch` receives the thrown object at the corresponding handler.

```java
import java.io.IOException;

class Example {
    static void readConfig(boolean missing) throws IOException {
        if (missing) {
            throw new IOException("Không tìm thấy cấu hình");
        }
    }

    public static void main(String[] args) {
        try {
            readConfig(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Save as `Example.java` and run:

```bash
javac -encoding UTF-8 Example.java
java Example
```

Output:

```text
Không tìm thấy cấu hình
```

Because `IOException` is checked, omitting both the `catch` block and the `throws IOException` declaration in a calling method will prevent the code from **compiling**. Conversely, throwing `IllegalArgumentException` does not require a `throws` declaration.

An object such as `new Throwable("lỗi")` can certainly be created and thrown, but `Throwable` itself is also **checked**. Declaring `throws Throwable` on a public API is usually too broad: it shifts responsibility onto callers for error types they should not attempt to recover from.

When there are multiple `catch` clauses, place **more specific branches before more general ones**. For example, `catch (IOException ex)` must appear before `catch (Exception ex)` if they handle the same `try`; reversing the order makes the `IOException` branch unreachable and causes a compiler error. Syntactically, `catch (Throwable ex)` can catch both `Exception` and `Error`, but it is usually too broad for business-logic handling.

## 3. What Information Does a `Throwable` Store?

A `Throwable` object is more than just an error message. It carries information for tracing the path of the failure.

| Member / API | Meaning and Notes |
| --- | --- |
| `getClass()` | The actual exception type, e.g., `IllegalArgumentException`. |
| `getMessage()` | The message passed when creating the exception; may be `null`. |
| `getLocalizedMessage()` | By default returns `getMessage()`; subclasses may override it for localization. |
| `getCause()` | The underlying cause linked via constructor or `initCause()`; may be `null`. |
| `getStackTrace()` | An array of `StackTraceElement` representing the recorded call path; the first element is typically where the exception was created/recorded. |
| `printStackTrace()` | Prints the exception, call stack, cause, and suppressed exceptions; defaults to the standard error stream `System.err`. |
| `getSuppressed()` | Additional attached exceptions, especially from closing resources in `try-with-resources`. |
| `toString()` | By default concatenates the class name with the message (if present). |
| `fillInStackTrace()` | Updates the stack trace information at the point of the call; mainly intended for specialized cases. |

**The stack trace** records the call chain at the moment the `Throwable` captures its stack, not the history of every prior operation. The first line of the trace usually points to where the exception was created; subsequent lines show who called that method. Locations and line numbers can change when code is edited or recompiled, so a literal stack trace should not be used as fixed expected output in tests.

`Throwable` provides constructors such as `Throwable()`, `Throwable(String message)`, `Throwable(String message, Throwable cause)`, and `Throwable(Throwable cause)`. It also has a `protected` constructor that lets you configure whether suppressed exceptions and the stack trace are collected; this is mainly for subclasses with special requirements.

A common mistake is keeping only `ex.getMessage()` and throwing a new exception, which loses the **original type, stack trace, and cause**. Preserve the cause relationship when translating an exception into another type.

## 4. Runnable Example: Checking Inheritance Relationships and Cause

File `ThrowableDemo.java`:

```java
public class ThrowableDemo {
    public static void main(String[] args) {
        System.out.println("Exception là Throwable: "
                + Throwable.class.isAssignableFrom(Exception.class));
        System.out.println("Error là Throwable: "
                + Throwable.class.isAssignableFrom(Error.class));
        System.out.println("IllegalArgumentException là RuntimeException: "
                + RuntimeException.class.isAssignableFrom(IllegalArgumentException.class));

        try {
            parsePort("abc");
        } catch (IllegalArgumentException ex) {
            System.out.println("Kiểu: " + ex.getClass().getSimpleName());
            System.out.println("Thông điệp: " + ex.getMessage());
            System.out.println("Nguyên nhân: " + ex.getCause().getClass().getSimpleName());
            System.out.println("Phương thức tại frame đầu: "
                    + ex.getStackTrace()[0].getMethodName());
        }
    }

    static int parsePort(String text) {
        final int port;
        try {
            port = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Port phải là số nguyên: " + text, ex);
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Port phải nằm trong 1..65535");
        }
        return port;
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 ThrowableDemo.java
java ThrowableDemo
```

Output:

```text
Exception là Throwable: true
Error là Throwable: true
IllegalArgumentException là RuntimeException: true
Kiểu: IllegalArgumentException
Thông điệp: Port phải là số nguyên: abc
Nguyên nhân: NumberFormatException
Phương thức tại frame đầu: parsePort
```

Note what happens here: `Integer.parseInt("abc")` throws `NumberFormatException`. The `parsePort` method provides an application-context message using `IllegalArgumentException` **and preserves the original exception as the cause**. When investigating the failure, you can still trace back to the number-parsing step. The port range check is placed outside the `try` block that catches `NumberFormatException` to avoid accidentally wrapping a range-validation error.

`Class.isAssignableFrom(...)` is a way to check type relationships at runtime: `A.class.isAssignableFrom(B.class)` returns `true` if a value of type `B` can be assigned to a variable of type `A` under Java's type rules. It does not create or throw an exception itself.

## 5. Cause and Suppressed Exceptions Are Two Different Relationships

**Cause** answers "which error did this error originate from?". A constructor with a `cause` parameter is the standard way to attach a cause chain:

```java
throw new IllegalStateException("Không thể nạp cấu hình", originalException);
```

This is an illustrative snippet inside a method that already has an appropriate `originalException` variable of type `Throwable`; it is not a standalone program. `initCause(cause)` is only used when the cause has not yet been set; it cannot be reset arbitrarily, and an exception cannot be set as its own cause. Prefer a constructor that accepts `cause` because it expresses intent at object creation time.

**Suppressed exceptions** answer "what other secondary errors occurred while handling this failure?". A typical case is a `try-with-resources` block: code inside `try` throws an exception, and `close()` also throws an exception. Java keeps the exception from the `try` body as the primary exception and attaches the resource-closing exception to `getSuppressed()`.

File `SuppressedDemo.java`:

```java
public class SuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Số lỗi phụ: " + ex.getSuppressed().length);
            System.out.println("Lỗi phụ: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
```

Output:

```text
Lỗi chính: work failed
Số lỗi phụ: 1
Lỗi phụ: close failed
```

`getCause()` and `getSuppressed()` are **not interchangeable**. In the example above, `getCause()` on the primary exception is `null`, while `getSuppressed()` contains the exception from `close()`. `Throwable.addSuppressed(...)` can be used to attach one manually when truly needed; the method rejects suppressing the object itself or passing `null`.

## 6. Should You Catch `Throwable`?

Consider the following block:

```java
try {
    performWork();
} catch (Throwable ex) {
    System.out.println("Có lỗi: " + ex.getMessage());
}
```

This is an **illustrative snippet**, assuming `performWork()` is already defined. It will catch `IOException`, `RuntimeException`, and even `OutOfMemoryError` if any of them are thrown inside the `try` block. Printing a single line and continuing execution does not guarantee that the application state remains valid. In practice, this can mask serious failures; with `InterruptedException` (a checked `Exception`), catching too broadly without proper handling can also break task-cancellation mechanisms.

Better alternatives:

1. Catch **the specific type you can actually handle** where you have the right context, such as `IOException` when deciding whether to retry an I/O operation.
2. If recovery is not possible at the current layer, let the exception propagate or **wrap it with a cause** to add business context.
3. Place centralized error handling at application boundaries (such as the API layer or task loop) using an appropriate mechanism; logging an error does not mean it has been resolved.
4. Usually let `Error` propagate. Only catch a specific `Error` subtype when there is a clear technical reason and you know how to handle it safely; not all `Error` cases have the same severity.
5. Avoid `throws Throwable` in normal API contracts when a more specific checked type can be declared.

`catch (Exception ex)` is not a catch-all either: it does not catch errors that belong solely to the `Error` branch. In code that requires cleanup regardless of outcome, `finally` or `try-with-resources` is usually more appropriate than trying to catch `Throwable` just to run cleanup logic.

## 7. Logging, Interpreting Stack Traces, and Common Pitfalls

- **Pass the whole exception object when logging:** a logger that supports an exception parameter will record both the stack trace and the cause chain. Logging only `getMessage()` can lose crucial diagnostic evidence.
- **Do not overuse `printStackTrace()` in production applications:** this method writes directly to a stream, usually lacking context and log management. For small learning examples, it remains useful for inspecting `Throwable` structure.
- **Do not assume `getMessage()`, `getCause()`, or `getStackTrace()[0]` always exist:** the message or cause may be `null`; the stack trace may be empty if the object was configured not to record a trace or if the trace was modified.
- **Avoid `throw ex;` after merely logging without a clear purpose:** when catching and rethrowing, the original stack information on the same object is preserved, but if multiple layers log it, the same error may appear repeatedly. Decide which layer is responsible for logging.
- **Do not replace an exception with `new RuntimeException(ex.getMessage())`:** this statement loses the cause link. If you must wrap it, use `new RuntimeException("Ngữ cảnh", ex)`.
- **Do not arbitrarily call `fillInStackTrace()` or `setStackTrace(...)`:** they alter diagnostic information. Creating and capturing a stack trace also has overhead; special optimizations for high-load systems require profiling evidence before trading away debuggability.

## 8. Self-Check

**Question 1.** Is `throw new String("lỗi");` valid? **No.** `String` does not extend `Throwable`; only objects of type `Throwable` or a subclass can be thrown.

**Question 2.** Is `RuntimeException` outside `Exception`? **No.** It is a direct subclass of `Exception`; the unchecked rule is a language rule based on the inheritance branch.

**Question 3.** Does `catch (Exception ex)` catch every `Error`? **No.** `Error` and `Exception` are two separate branches under `Throwable`.

**Question 4.** Is `Throwable` itself a checked exception? **Yes.** It does not belong to the `RuntimeException` or `Error` branch.

**Question 5.** Does a resource-closing error in `try-with-resources` always replace an error that occurred in the `try` body? **No.** If both places throw an exception, the exception from the `try` body is typically the primary exception, and the resource-closing error is kept in `getSuppressed()`.

**Takeaway:** `Throwable` defines the foundation for Java's throwing, catching, and exception-tracing mechanisms. The inheritance branch determines checked/unchecked rules; `message` explains the failure, `stack trace` points to the call path, `cause` stores the cause chain, and `suppressed` stores secondary exceptions. When writing programs, catch the right type you can handle and preserve sufficient information when propagating errors across layers.

# Suppressed exceptions and their relationship with try-with-resources in Java

In Java, an operation can throw **multiple exceptions related to the same execution**: the main work fails, and then closing the resource also fails. If the program only keeps the last exception, information about the original error can be obscured. The **suppressed exceptions** mechanism of `Throwable` allows attaching secondary exceptions to the **primary exception** without losing the original error object.

`try-with-resources` is where this mechanism most commonly appears: Java automatically closes `AutoCloseable` resources. When the `try` body throws exception A and `close()` throws exception B, **A usually remains the primary exception; B is stored in `A.getSuppressed()`**. This is an important difference compared to a regular `finally` block that might throw B and mask A.

This lesson covers the concept, the `Throwable` API, initialization/closing order, scenarios where one or multiple resources fail, `getCause()` versus `getSuppressed()`, disabling suppression, and how to test on Java 17+.

## 1. Why are suppressed exceptions needed?

Imagine writing to a file:

1. Open a connection or file.
2. Perform the write operation.
3. The write operation throws `IOException("write failed")`.
4. The program attempts to close the resource.
5. `close()` throws `IOException("close failed")`.

Both errors need to be known. The **write error** explains why the main task failed; the **close error** may indicate that the resource was not properly released, or that flush/close did not complete.

If using unguarded manual cleanup:

```java
try {
    writeData();
} finally {
    closeResource();
}
```

this is **illustrative skeleton code**, without definitions for the two methods. When `writeData()` throws error A and `closeResource()` throws B, according to the completion rules of `finally`, **B can replace A** as the exception propagating outward. Java does not automatically link A as the cause or suppressed exception of B in that `try/finally` construct.

If using `try-with-resources`:

```java
try (SomeResource resource = open()) {
    resource.writeData();
}
```

this is also **skeleton code**, with `SomeResource` implementing `AutoCloseable`. When the `try` body throws A and `close()` throws B, the mechanism performed by Java will attempt to keep **A as primary** and attach **B to A's suppressed list**, under specific conditions such as suppression on the primary not being disabled.

**Suppressed does not mean "an error not worth caring about".** It only describes the priority relationship when multiple errors occur together; the system still needs to inspect, record, and handle the effects of cleanup errors.

## 2. Three types of information to distinguish: primary, cause, and suppressed

| Concept | Meaning | How to access |
| --- | --- | --- |
| **Primary exception** | The main exception being thrown or received by a handler in a scenario | The exception variable itself in `catch`, such as `e` |
| **Cause** | The exception that is the root reason leading to another exception, typically when a layer wraps/converts error types | `e.getCause()` |
| **Suppressed exception** | A secondary exception stored alongside the primary instead of replacing it | `e.getSuppressed()` |

Business example:

- The repository throws `IOException` because it cannot read a file.
- The service creates `ConfigurationException("Unable to start", ioError)`. `ioError` becomes the **cause** of the wrapper.
- When the resource is closed, `close()` throws another error; if that error is suppressed onto `ioError`, it resides in **`ioError.getSuppressed()`**, and is not automatically moved to the wrapper's suppressed list.
- The caller may have to follow both the **cause chain** and the **suppressed exceptions on each node** for a complete diagnosis.

Cause and suppressed are not two names for the same array. A `Throwable` can have **one cause** and **multiple suppressed exceptions**, with each object having its own stack trace.

## 3. The `Throwable` API: `getSuppressed()` and `addSuppressed()`

Important methods:

```java
public final synchronized void addSuppressed(Throwable exception)
public final synchronized Throwable[] getSuppressed()
```

These are **illustrative API signatures** (not declarations to be rewritten in an application). `addSuppressed` attaches a secondary Throwable to the current object; `getSuppressed` returns **an array of suppressed exceptions** that have been recorded.

Properties to understand:

- `getSuppressed()` returns an array, not a single exception.
- For an object with no suppressed exceptions, the result is an **empty array**, not `null`.
- The returned array is a **copy**; modifying elements of that array does not modify the internal list on the Throwable.
- Elements are ordered by when they were added; with `try-with-resources`, this is usually tied to the **resource closing order**.
- `addSuppressed(null)` is invalid and throws `NullPointerException`.
- You cannot suppress an object onto itself: `e.addSuppressed(e)` throws `IllegalArgumentException` because **self-suppression** is invalid.
- If suppression was disabled when creating the Throwable, `addSuppressed` does not store additional secondary errors as usual.

You rarely need to call `addSuppressed` manually if you are using standard `try-with-resources`; Java will perform the linking in the appropriate situations.

## 4. First example: manually adding a secondary error

Save the file **`SuppressedApiDemo.java`**:

```java
public class SuppressedApiDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("Lỗi thao tác");
        IllegalArgumentException cleanup =
                new IllegalArgumentException("Lỗi cleanup");

        primary.addSuppressed(cleanup);

        System.out.println("Primary: " + primary.getMessage());
        System.out.println("Số suppressed: "
                + primary.getSuppressed().length);
        System.out.println("Phụ: "
                + primary.getSuppressed()[0].getMessage());
        System.out.println("Cùng object phụ: "
                + (primary.getSuppressed()[0] == cleanup));
        System.out.println("Cause là null: "
                + (primary.getCause() == null));
    }
}
```

Compile/run on Java 17+:

```bash
javac -encoding UTF-8 --release 17 SuppressedApiDemo.java
java SuppressedApiDemo
```

**Exact stdout** with a UTF-8 console:

```text
Primary: Lỗi thao tác
Số suppressed: 1
Phụ: Lỗi cleanup
Cùng object phụ: true
Cause là null: true
```

The result shows that the suppressed list contains **the exact `cleanup` object** (no new object is created just for suppression), and is unrelated to `getCause()`. The primary's `getMessage()` remains `"Lỗi thao tác"`.

If you want to read multiple secondary errors, **iterate over the array** from `getSuppressed()`. In a real application, do not assume element `[0]` always exists; check the length before indexing.

## 5. `try-with-resources` automatically connects primary and suppressed

`try-with-resources` uses the form:

```java
try (Resource resource = open()) {
    work(resource);
} catch (SomeException e) {
    handle(e);
}
```

This is an **illustrative skeleton**, with undefined types and methods. Assuming `Resource implements AutoCloseable`, the process is:

1. Evaluate the resource initialization expression.
2. If successful, execute the `try` body.
3. Upon leaving the `try` body, Java **attempts to call `close()`** on non-`null` resources.
4. If the `try` body threw A, and `close()` throws B, Java **attaches B to A via the suppressed mechanism** if adding errors is supported.
5. After cleanup, the primary exception is passed to the appropriate handler; a `catch` attached directly to that statement runs **after attempting to close the resource**.

If the `try` body completes normally and `close()` throws B, then **B has no A to attach to** and becomes the primary exception.

The key point is that `try-with-resources` does not try to "catch all errors" so the program succeeds. It manages resources and **preserves the exception propagation path** in a structure less error-prone than a hand-written `finally`.

## 6. Full example: `try` body fails, `close()` also fails

Save **`PrimaryAndSuppressedDemo.java`**:

```java
public class PrimaryAndSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close() chạy");
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thực hiện công việc");
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + secondary.getMessage());
            }
        }
        System.out.println("Sau try/catch");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 PrimaryAndSuppressedDemo.java
java PrimaryAndSuppressedDemo
```

**Exact stdout:**

```text
Thực hiện công việc
close() chạy
Primary: Dữ liệu không hợp lệ
Số suppressed: 1
Suppressed: Không đóng được
Sau try/catch
```

Explanation:

- `IllegalArgumentException` is error A from the `try` body.
- `Resource.close()` runs when leaving the block and throws `IllegalStateException` B.
- Java does not replace A with B. B is added to `A.getSuppressed()`.
- `catch (IllegalArgumentException e)` receives **A**, not B.
- The statement after the construct runs because the handler completed normally.

If there is only a `catch (IllegalStateException e)` handler at the same level, it does **not** catch A just because A has B of type `IllegalStateException` in its suppressed list. `catch` selection is based on **the type of the primary exception being thrown**, not on the suppressed exceptions.

## 7. What if only `close()` fails?

If the `try` body runs normally and `close()` throws an exception, the close error becomes the primary error of the statement. There is no previous primary to suppress it onto.

Save **`CloseOnlyDemo.java`**:

```java
public class CloseOnlyDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
            throw new IllegalStateException("Đóng lỗi");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thân try hoàn tất");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CloseOnlyDemo.java
java CloseOnlyDemo
```

**Exact stdout:**

```text
Thân try hoàn tất
Đóng tài nguyên
Bắt: Đóng lỗi
Suppressed: 0
```

The operation in the `try` body completed, but **the entire try-with-resources statement still failed** because the resource could not be closed. Final success should not be reported if the operation's contract requires closing or flushing to succeed.

This is a common terminology misconception: "an exception raised in close is always suppressed". **Incorrect**; it is only suppressed if there is already an exception being preserved with priority (or an earlier close error occurred during the closing of multiple resources).

## 8. Multiple resources: initialization and closing order

With:

```java
try (Resource first = open("A");
     Resource second = open("B");
     Resource third = open("C")) {
    performWork();
}
```

this is **illustrative skeleton code**. Java evaluates resource declarations **from left to right**: A, B, C. Upon leaving the block, successfully initialized resources are attempted to be closed **from right to left**: C, B, A.

If the `try` body throws exception A0 and all three `close()` calls throw C0, B0, A1, then A0 remains primary; the close errors may be added as suppressed in the order **C0 → B0 → A1**.

If the `try` body does not throw an error, but C's `close()` throws C0 first, C0 becomes primary. When B's `close()` and then A's `close()` subsequently throw, they may be suppressed **onto C0**.

Do not confuse the order in the declaration with the order in `getSuppressed()`; the suppressed order is tied to the actual errors raised during cleanup.

## 9. Example: multiple close failures while the `try` body already has a primary

Save **`MultipleCloseFailuresDemo.java`**:

```java
public class MultipleCloseFailuresDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Lỗi đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B");
             Resource c = new Resource("C")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi xử lý");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Số phụ: " + e.getSuppressed().length);
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Phụ: " + secondary.getMessage());
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 MultipleCloseFailuresDemo.java
java MultipleCloseFailuresDemo
```

**Exact stdout:**

```text
Mở A
Mở B
Mở C
Trong try
Đóng C
Đóng B
Đóng A
Chính: Lỗi xử lý
Số phụ: 3
Phụ: Lỗi đóng C
Phụ: Lỗi đóng B
Phụ: Lỗi đóng A
```

Each `Resource.close()` throws an error, but Java still attempts to close all successfully initialized resources. The errors from C, B, and A are preserved instead of replacing the primary from the `try` body.

This **does not automatically prove cleanup succeeded**. The fact that `close()` was called does not mean every resource was completely released. The suppressed exceptions are the very evidence that the resource state needs further examination.

## 10. If the `try` body succeeds but two `close()` calls fail

This is a trickier case: there is no primary error from the `try` body. Java closes the last resource first, and **the first close exception thrown becomes the primary**. Subsequent close errors are kept as suppressed onto that primary.

Full example **`CloseBecomesPrimaryDemo.java`**:

```java
public class CloseBecomesPrimaryDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Lỗi " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Work thành công");
        } catch (IllegalStateException e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + secondary.getMessage());
            }
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CloseBecomesPrimaryDemo.java
java CloseBecomesPrimaryDemo
```

**Exact stdout:**

```text
Work thành công
Đóng B
Đóng A
Primary: Lỗi B
Suppressed: Lỗi A
```

B is closed before A, so B's error becomes primary. When closing A also fails, A's error becomes suppressed onto B's error.

**There is no rule that "the first declared resource is always primary".** The primary depends on the execution path: whether there is an error from the `try` body, the closing order, and which error occurs first while the managed resources are being cleaned up.

## 11. Resource initialization failure: cleanup can still produce suppressed exceptions

With multiple resources, a constructor or factory in a later position can throw an exception before the `try` body starts. Java still attempts to close the resources that **were successfully initialized earlier**.

Suppose:

- Resource A opens successfully.
- While creating resource B, its constructor throws `IllegalArgumentException`.
- Java attempts to close A.
- `A.close()` throws `IllegalStateException`.

B's initialization error can be **primary**, while A's close error is **suppressed** onto B's initialization error. The `try` body is not executed.

Java 17 example **`InitializationSuppressedDemo.java`**:

```java
public class InitializationSuppressedDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Khởi tạo " + name);
            if ("B".equals(name)) {
                throw new IllegalArgumentException("Không tạo được B");
            }
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Không đóng được " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Không chạy đến đây");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 InitializationSuppressedDemo.java
java InitializationSuppressedDemo
```

**Exact stdout:**

```text
Khởi tạo A
Khởi tạo B
Đóng A
Primary: Không tạo được B
Số suppressed: 1
Suppressed: Không đóng được A
```

A was successfully created and is managed by the try-with-resources construct. B threw an error in its constructor, so B **is not considered a successfully initialized resource for Java to call `close()` on**, but A is still closed.

This rule is very useful for sequences of opening files, streams, sockets, or connection resources: an error in a later resource does not leave earlier resources neglected.

## 12. Does a `null` resource create a suppressed exception?

In try-with-resources, a resource specification can contain a `null` reference. If the resource is `null`, Java **does not call `close()` on that reference**. Therefore, a `null` resource does not generate a close error by itself and does not add a suppressed exception merely for being `null`.

Save **`NullResourceSuppressedDemo.java`**:

```java
public class NullResourceSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource missing = null) {
            throw new IllegalArgumentException("Lỗi trong try");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 NullResourceSuppressedDemo.java
java NullResourceSuppressedDemo
```

**Exact stdout:**

```text
Primary: Lỗi trong try
Suppressed: 0
```

Even though `Resource.close()` is written to always throw an exception, that method is not called because the resource variable `missing` is `null`. The primary exception remains `IllegalArgumentException` from the `try` body, with an empty suppressed list.

Distinguish this: **reading or calling a method on a `null` resource in the `try` body can still throw `NullPointerException`**. What try-with-resources safely does here is skip the *automatic close call* for a `null` reference, not make all operations on `null` valid.

## 13. `getCause()` differs from `getSuppressed()` in real applications

Consider a system:

- A network operation throws `IOException`.
- When closing the stream, `close()` also throws another `IOException`; the close error is suppressed onto the network error.
- The service layer wraps the network error in a `ServiceException` whose `cause` is the network exception.

When the caller receives `ServiceException`:

```text
ServiceException                  (wrapper)
└── cause -> IOException A        (primary error at the I/O layer)
    └── suppressed -> IOException B   (stream close error)
```

`ServiceException.getSuppressed()` does **not** automatically contain B. B resides on object A, which is stored by the wrapper as its cause.

Example **`CauseVsSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseVsSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() {
        try {
            repository();
        } catch (IOException e) {
            throw new IllegalStateException("Service failed", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("Wrapper: " + wrapper.getMessage());
            System.out.println("Cause: " + cause.getMessage());
            System.out.println("Wrapper suppressed: "
                    + wrapper.getSuppressed().length);
            System.out.println("Cause suppressed: "
                    + cause.getSuppressed().length);
            System.out.println("Lỗi phụ: "
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CauseVsSuppressedDemo.java
java CauseVsSuppressedDemo
```

**Exact stdout:**

```text
Wrapper: Service failed
Cause: read failed
Wrapper suppressed: 0
Cause suppressed: 1
Lỗi phụ: close failed
```

You need to inspect **both the cause chain and the suppressed lists on the relevant objects**. Simply calling `wrapper.getSuppressed()` and concluding "there was no cleanup error" will miss B on the `cause` object.

## 14. How does `printStackTrace()` display suppressed exceptions?

`Throwable.printStackTrace()` prints the exception description and stack frames. When suppressed exceptions are present, the typical presentation includes lines labeled `Suppressed:`; the cause relationship is shown separately under the label `Caused by:`.

Illustrative example not requiring fixed output:

```java
try {
    runOperation();
} catch (Exception e) {
    e.printStackTrace();
}
```

This is **skeleton code**; `runOperation()` must be defined. The no-argument `printStackTrace()` prints to **standard error** (`System.err`), not stdout, and the formatting may depend on the JVM, source line numbers, build method, and code location.

A similar representation:

```text
java.io.IOException: read failed
    at ...
    Suppressed: java.io.IOException: close failed
        at ...
```

This is only a **visual sample**, not an actual stack trace verified by line numbers. In logging APIs that support `Throwable`, passing the exception object directly usually preserves stack trace, cause, and suppressed information better than logging only `e.getMessage()`.

**`getMessage()` and `toString()` do not automatically list suppressed exceptions by default.** If logs only record a short string without preserving the Throwable object or its relationships, cleanup errors can be lost from observability systems.

## 15. `addSuppressed()` is not `initCause()`

The two mechanisms address two different types of relationships:

```java
Throwable primary = new IllegalStateException("Work failed");
Throwable secondary = new IllegalArgumentException("Cleanup failed");

primary.addSuppressed(secondary);
```

That does not make `primary.getCause()` become `secondary`. To represent the cause of a wrapper, you can use a constructor that accepts a cause:

```java
Throwable root = new IllegalArgumentException("Input failed");
Throwable wrapper =
        new IllegalStateException("Service failed", root);
```

These are **independent illustrative snippets**. A Throwable can have one cause and multiple suppressed exceptions. In the try-with-resources mechanism, adding suppressed exceptions serves **secondary errors arising during cleanup**, rather than expressing that the cleanup error was the cause of the earlier work error.

**Do not use `initCause()` to attach every close error into a cause chain.** That blurs temporal and business relationships; with `try-with-resources`, read the generated suppressed list instead.

## 16. Rules for manually adding suppressed exceptions: no `null` and no self-suppression

`addSuppressed` has its own safety rules to prevent invalid data:

```java
IllegalStateException e =
        new IllegalStateException("Primary");
e.addSuppressed(new IllegalArgumentException("Cleanup"));

// e.addSuppressed(null); // Throws NullPointerException.
// e.addSuppressed(e);    // Throws IllegalArgumentException.
```

This is an **illustrative snippet**. The second and third statements are commented out so they do not break the example. In a real application, an algorithm that automatically manages an error list must avoid **attaching the primary to itself**, as well as not passing a `null` exception.

`getSuppressed()` returns a new array; you can filter, iterate, and print its elements as read-only data. Do not replace elements in the returned array and expect the internal suppressed list to change.

If implementing complex cleanup yourself, consider the `AutoCloseable`/`try-with-resources` API to avoid manually managing rules such as error addition order, checked/unchecked exceptions, and initialization failure states.

## 17. Suppression can be disabled in a custom exception class

`Throwable` has a protected constructor:

```java
protected Throwable(String message, Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace)
```

The `enableSuppression` parameter allows a subclass to **disable the ability to record suppressed exceptions**. This is a rare case in business applications, but important for accurate reasoning: `try-with-resources` still attempts to attach the close error, but if the primary has suppression disabled, `getSuppressed()` may remain empty.

Standalone example **`SuppressionDisabledDemo.java`**:

```java
public class SuppressionDisabledDemo {
    static class NoSuppressionException extends Exception {
        NoSuppressionException(String message) {
            super(message, null, false, true);
        }
    }

    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close bị lỗi");
            throw new IllegalStateException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new NoSuppressionException("work failed");
        } catch (NoSuppressionException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 SuppressionDisabledDemo.java
java SuppressionDisabledDemo
```

**Exact stdout:**

```text
close bị lỗi
Primary: work failed
Suppressed: 0
```

Even though `close()` threw `IllegalStateException`, the primary object did not store the suppressed exception because `enableSuppression=false`. That **does not make `close()` succeed**, and does not mean the secondary error never happened.

In practice: do not disable suppression if the application needs to diagnose concurrent cleanup errors. Also do not confuse `enableSuppression` with `writableStackTrace`; they are two separate options. Disabling writable stack trace affects the exception's stack frames, whereas disabling suppression affects the secondary error list.

## 18. Note on a very rare error: self-suppression on close

The suppression mechanism requires that **primary and suppressed are not the same object**. `Throwable.addSuppressed(this)` is invalid.

Most `close()` implementations create a new exception or throw an independent object, but if an application intentionally **reuses the exact same exception instance** in both the `try` body and `close()`, the suppressed-linking operation can encounter a self-suppression error. This is another reason **not to reuse global exception objects** across independent situations.

In normal design:

- Each failure should have its own Throwable, unless there is a very clear reason and contract.
- Let Java preserve primary/suppressed automatically.
- If using `addSuppressed` manually, check that you do not add the object to itself and do not pass `null`.
- When encountering confusing traces from a special mechanism, do not hastily assume try-with-resources recorded every expected error; also check how libraries create and reuse exceptions.

There is no need to demonstrate self-suppression with a default example since it is not a valid use of the API; understanding this limit is enough to avoid a rare but hard-to-diagnose class of bugs.

## 19. Manual cleanup with `finally` risks masking the primary error

Compare the two constructs:

**Manual cleanup can lose the primary:**

```java
try {
    doWork();
} finally {
    resource.close(); // If this also throws, it may mask the error from doWork().
}
```

**Try-with-resources preserves secondary errors structurally:**

```java
try (Resource resource = openResource()) {
    doWork();
}
```

Both are **illustrative skeleton code**, requiring definitions for `Resource` and the methods. `finally` has no built-in rule to record suppressed errors onto the primary if cleanup throws a new exception. If the primary error cause must be preserved, naive `finally` code is risky.

If an older API does not implement `AutoCloseable`, you can **write an adapter implementing AutoCloseable** instead of manually handling all primary/suppressed cases. That must still ensure the adapter truly owns the resource, closes the right object, and does not mistakenly close a shared resource.

## 20. Adapter example for a legacy API

An older library might only have a `release()` method:

```java
class LegacySession {
    void work() {
        throw new IllegalArgumentException("work failed");
    }

    void release() {
        throw new IllegalStateException("release failed");
    }
}

class SessionAdapter implements AutoCloseable {
    private final LegacySession session;

    SessionAdapter(LegacySession session) {
        this.session = session;
    }

    void work() {
        session.work();
    }

    @Override
    public void close() {
        session.release();
    }
}
```

These are **two illustrative classes**. Using them in a method:

```java
try (SessionAdapter session =
             new SessionAdapter(new LegacySession())) {
    session.work();
}
```

When `work()` throws `IllegalArgumentException` and `release()` throws `IllegalStateException`, try-with-resources keeps the work error as primary and attaches the release error as suppressed (with suppression enabled by default).

Do not try to "fix" errors by catching and ignoring all `Exception`s in `close()`: doing so can lose track of a genuine cleanup incident. If a close error can be considered harmless by contract, the adapter itself or a higher layer must decide based on **the specific error type**, not by ignoring everything.

## 21. Checked exceptions from `AutoCloseable.close()` affect method signatures

`AutoCloseable.close()` has the declaration:

```java
void close() throws Exception;
```

This is an **API signature**. Therefore, when the static type of the resource is `AutoCloseable`, the compiler may require a handler or a `throws Exception` clause for closing.

Example:

```java
static void run(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("Trong try");
    }
}
```

This is an **illustrative method**, using Java 9+ syntax for an effectively final parameter variable. `throws Exception` comes from the possibility that `close()` throws a checked `Exception`, even if the `try` body throws nothing.

If the static type is a subclass that overrides `close()` without declaring a checked exception, the `throws` obligation may be narrower or disappear. If it is `java.io.Closeable`, the `close()` method declares `throws IOException`, narrower than the general `AutoCloseable` contract.

Connection to suppressed: **when close throws a checked exception**, it can be primary or suppressed depending on the execution path. Even when considering the suppressed case, the resource's signature is still analyzed by the compiler; you cannot skip handling checked exceptions just because you think close errors will always be suppressed.

## 22. In what order do resources close, and does closing stop when one `close()` fails?

The answer is: **they close in reverse declaration order, and Java still attempts to close the remaining successfully initialized resources**.

Example with three resources A, B, C:

```text
Initialization: A -> B -> C
try body runs
Closing:        C -> B -> A
```

If `C.close()` throws, Java does not automatically skip B and A. It still attempts to close B and A; if they also throw, the errors are preserved as primary/suppressed as analyzed above.

This is a major difference from hand-written code like:

```java
finally {
    c.close();
    b.close();
    a.close();
}
```

This is **counter-example skeleton code**. If `c.close()` throws, `b.close()` and `a.close()` might never run, unless the programmer adds separate handlers manually. Try-with-resources generates the appropriate cleanup mechanism to avoid that situation.

**Note:** if a resource is `null`, Java skips the close call on it, while still processing the other resources in order. If a later resource initialization fails, only the resources **that were successfully initialized earlier** are attempted to be closed.

## 23. When is `getSuppressed()` empty?

There are many valid reasons:

1. The `try` body has no errors and all `close()` calls succeed.
2. The `try` body throws an error, but `close()` throws none.
3. The `try` body throws an error and the resource is `null`, so there is no automatic close on that resource.
4. The `try` body succeeds, and only one `close()` throws: the close exception is **primary**, not suppressed.
5. A custom Throwable has **disabled suppression**.
6. An exception was created outside try-with-resources without anyone calling `addSuppressed`.
7. You are inspecting a **wrapper** while the suppressed exceptions are on the wrapper's **cause**.

Therefore, **`getSuppressed().length == 0` is not enough to prove there were no cleanup errors in the entire task**. You need to know the object being inspected, the actual call path, the resource type, and whether there is a wrapper/cause.

This is also why errors should be logged as structured Throwables, rather than just printing a message and discarding the object.

## 24. Testing concurrent errors with Java 17

A good test does not just verify "an exception was thrown"; it needs to verify that **the primary exception is the right type** and **the cleanup error was preserved**, without changing the primary.

Example **`SuppressedAssertionsDemo.java`**:

```java
public class SuppressedAssertionsDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("cleanup");
        }
    }

    static void run() {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalArgumentException("work");
        }
    }

    public static void main(String[] args) {
        try {
            run();
            throw new AssertionError("Không có lỗi chính");
        } catch (IllegalArgumentException e) {
            if (!"work".equals(e.getMessage())) {
                throw new AssertionError("Sai primary");
            }

            Throwable[] others = e.getSuppressed();
            if (others.length != 1
                    || !(others[0] instanceof IllegalStateException)
                    || !"cleanup".equals(others[0].getMessage())) {
                throw new AssertionError("Sai suppressed");
            }

            System.out.println("PASS: primary và suppressed chính xác");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SuppressedAssertionsDemo.java
java SuppressedAssertionsDemo
```

**Exact stdout:**

```text
PASS: primary và suppressed chính xác
```

The example intentionally uses `throw new AssertionError(...)` to fail the test, without depending on the `-ea` flag of the `assert` keyword. On the expected path, there is one suppressed exception of type `IllegalStateException` with message `"cleanup"`.

A complete test suite should also check when **only close fails**, **multiple close calls fail**, **resource initialization fails**, and **the resource is null**, because those paths have different primary/suppressed behavior.

## 25. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Suppressed means an exception that has been handled and can be ignored." | It is still an error that needs diagnosis; suppressed only preserves the secondary error relationship relative to the primary. |
| "If `close()` throws an error, that error is always suppressed." | If the `try` body succeeds, the first close error can be the primary. |
| "With one resource, there is only one error to handle." | The `try` body and `close()` can throw two different exceptions. |
| "When multiple close calls fail, only the last-closed resource's error is kept." | Try-with-resources attempts to close the remaining resources and can keep the close errors as suppressed. |
| "Suppressed is the same as `getCause()`." | No; `getCause()` and `getSuppressed()` describe different relationships. |
| "A wrapper automatically copies its cause's suppressed exceptions." | Not automatically. Suppressed exceptions usually remain on the original object that is the cause. |
| "`getSuppressed()` returns `null` when there are no errors." | It returns an **empty array**. |
| "Only `try-with-resources` can use `addSuppressed()`." | No; `addSuppressed()` is a public API on `Throwable`, though Java uses it automatically in try-with-resources when appropriate. |
| "Calling `e.addSuppressed(e)` is valid." | No. Java forbids self-suppression. |
| "`addSuppressed(null)` is simply ignored." | No; a `null` argument is invalid. |
| "If `getSuppressed()` is empty, there was definitely never a close error." | Not necessarily: close might be the primary, suppression might be disabled, or the error might be on the cause. |
| "`finally` and try-with-resources manage errors the same way." | No. A `finally` throwing a new error can mask the primary; try-with-resources has the suppressed mechanism. |
| "All exceptions support recording suppressed exceptions." | Subclasses can disable suppression via the appropriate constructor. |
| "`printStackTrace()` only shows the primary message." | Typically it also displays stack frames, cause, and suppressed exceptions when present. |
| "Every close call succeeds because Java calls it automatically." | Auto-close means Java **attempts to call**, not that cleanup is guaranteed to succeed. |
| "Checked exceptions from close don't need consideration because they will always be suppressed." | No; close can be the primary, and the compiler still checks the checked exception contract. |

## 26. Self-check questions

**Question 1.** The `try-with-resources` body throws A, and `close()` throws B. What is the primary exception?  
**Answer:** Usually A. B is attached as suppressed onto A if suppression is enabled and no rules for adding suppressed exceptions are violated.

**Question 2.** The `try` body runs successfully, and `close()` throws B. Where is B?  
**Answer:** B is the primary exception of the construct; there is no prior A to attach it to as suppressed.

**Question 3.** Resource A is declared before B; both `close()` calls fail and the `try` body does not fail. Which exception is primary?  
**Answer:** The error from `B.close()`, because B closes first; the error from `A.close()` usually becomes suppressed onto B's error.

**Question 4.** The `try` body throws A, and resource C closes before B and then the A-resource. If all three close calls fail, in what order are the suppressed exceptions?  
**Answer:** In the order the errors occur during closing: C, B, A-resource.

**Question 5.** The factory for the second resource throws an exception while the first resource is already open. Is the first resource closed?  
**Answer:** Java attempts to close the previously successfully initialized resource; the close error may be suppressed onto the initialization error.

**Question 6.** What does `getSuppressed()` return if there are no suppressed exceptions?  
**Answer:** An empty `Throwable[]` array.

**Question 7.** Can you call `primary.addSuppressed(primary)` to mark a repeated error?  
**Answer:** No. Self-suppression is forbidden and throws `IllegalArgumentException`.

**Question 8.** A wrapper has `getCause()` as exception A, and B is suppressed on A. Does `wrapper.getSuppressed()` automatically contain B?  
**Answer:** No. You need to check `wrapper.getCause().getSuppressed()` for that case.

**Question 9.** How does `printStackTrace()` differ from `getMessage()`?  
**Answer:** `getMessage()` only returns the message; `printStackTrace()` prints the error description, stack frames, and may include cause/suppressed according to the runtime's formatting.

**Question 10.** If suppression is disabled on the primary, what can `getSuppressed().length` be even if close fails?  
**Answer:** It can be 0, because the object does not store suppressed exceptions added as usual.

**Question 11.** How can `finally { resource.close(); }` mask the primary error?  
**Answer:** If the `try` body threw A and `close()` in `finally` throws B, `finally` completes abruptly with B and B can replace A as the thrown exception.

**Question 12.** Does a `null` resource throw a close error on its own?  
**Answer:** No. Try-with-resources skips the automatic `close()` call for a `null` reference.

**Question 13.** Why is it necessary to test both work failure and cleanup failure concurrently?  
**Answer:** To ensure the primary is not lost and suppressed exceptions are preserved with the right types and order, rather than just verifying that an exception was thrown.

**Question 14.** Is suppressed the same as a rollback result or resource recovery?  
**Answer:** No. It only preserves error information; successful rollback/cleanup requires a separate mechanism.

## 27. Practical checklist

When writing or reviewing resource-handling code:

1. **Is the resource `AutoCloseable`?** If so, prefer `try-with-resources`.
2. **What errors can the `try` body throw?** Identify the possible primary exceptions.
3. **What errors can `close()` throw?** Review the checked/unchecked contract and data impact.
4. **If both fail concurrently, is the primary preserved?** Check `getSuppressed()` rather than only the message.
5. **If only close fails, does the program treat it as the primary error?**
6. **If there are multiple resources, are the left-to-right initialization and right-to-left closing orders properly understood?**
7. **If a constructor/factory fails, are previously opened resources attempted to be closed?**
8. **If a resource is `null`, does cleanup skip it and still close the other resources?**
9. **Is there an exception wrapper?** Follow `getCause()` to the original primary and check suppressed on the right object.
10. **Is suppression disabled on a custom exception?** If so, are the diagnostic implications understood?
11. **Does any code call `addSuppressed` manually?** Verify it does not pass `null` or the primary itself.
12. **Does any `finally` block throw a new exception that masks the primary error?**
13. **Does logging record the Throwable object, stack trace, cause, and suppressed exceptions when needed?**
14. **Do tests cover simultaneous work + cleanup failures?**
15. **Is a policy defined for post-cleanup failures?** Data may need rollback, connections may be broken, or the task must not be reported as successful.

## 28. Key takeaways

**A suppressed exception is a secondary Throwable attached to the primary exception via `addSuppressed()` and read via `getSuppressed()`.** It is not a cause, does not make errors disappear on its own, and does not automatically recover the task.

**`try-with-resources` is the most common mechanism that produces suppressed exceptions**. When the main work throws A and `close()` throws B, Java usually keeps A as primary and attaches B as suppressed. If the main work does not throw an error, the first close error can become primary; with multiple resources, subsequent close errors are attached as suppressed in reverse declaration closing order.

When diagnosing, look at **the right object**: a wrapper may hold cause A via `getCause()`, while suppressed B resides on A. When designing, prefer managing resources with `try-with-resources`, test dual-failure paths, preserve root causes, and do not treat calling `close()` as a guarantee that cleanup succeeded.

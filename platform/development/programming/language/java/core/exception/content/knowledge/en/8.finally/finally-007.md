# Cleanup Exceptions Masking the Original Exception in Java

An operation can fail **twice**: first when performing the main work, and second when cleaning up resources. For example, a program encounters an error while writing data, and then closing the connection also throws an exception. If cleanup is written carelessly inside a `finally` block, **the new cleanup exception can replace the original exception**, causing the caller to see only "failed to close" instead of "failed to write data".

This is the problem of **exception masking** or **improper exception suppression** in the general sense: *the most important root cause is obscured by a subsequent error*. We should distinguish this "masking" phenomenon from Java's official **suppressed exceptions** mechanism. `try-with-resources` is designed to preserve the primary exception and attach exceptions thrown while closing resources to a secondary list via `Throwable.getSuppressed()`.

This lesson analyzes the exact control-flow rules of `finally`, compilable/runnable Java 17 examples, how to inspect error information, how to fix it with `try-with-resources`, and cases where you must handle cleanup manually.

## 1. Scenario Leading to a Masked Exception

Imagine an operation:

1. Open a resource.
2. Perform the main work: read data, send a request, write a file, or update a database.
3. The main work fails and throws exception A.
4. Upon leaving the scope, cleanup also fails and throws exception B.
5. The caller needs to know about both, **especially A**, because A describes why the main work failed.

If the code is written in the pattern:

```java
try {
    doWork();
} finally {
    closeResource();
}
```

this is only **skeleton code**, assuming both methods are already defined. If `doWork()` throws A and then `closeResource()` throws B from `finally`, **B becomes the exception propagated out of the entire construct**. A is not automatically attached as `cause` or `suppressed` of B.

This has consequences:

- The outer stack trace may point operators to `closeResource()` while the first error actually occurred in `doWork()`.
- The operation may have partially written, partially sent, or remained incomplete, yet analysis focuses only on cleanup.
- Exception-type handlers may receive B instead of A, leading to wrong retries, rollbacks, or responses.
- If the system did not record A beforehand, reconstructing the root cause becomes difficult.

**Do not assume that `finally` always loses the original error.** If `finally` completes normally, A continues propagating. Masking occurs when `finally` **completes abruptly for a new reason**, such as throwing a new exception or executing an alternative control-flow transfer.

## 2. Language Rule: The Last Completion Reason Wins

A `try` block can complete **normally** or **abruptly** (abrupt completion), for example due to `throw`, `return`, `break`, or `continue`. When `finally` is present, Java executes `finally` before completing the exit from the construct along the normal path.

Two sets of cases to distinguish:

| Situation | What does `finally` do? | Resulting outcome |
| --- | --- | --- |
| `try` completes normally | `finally` completes normally | Executes statement after the construct |
| `try` throws A | `finally` completes normally | A continues propagating |
| `try` throws A | `finally` throws B | B replaces A as the exit reason |
| `catch` rethrows A | `finally` throws B | B replaces A |
| `try` prepares to `return` value V | `finally` completes normally | Returns V |
| `try` prepares to `return` value V | `finally` throws B | Does not return V; throws B |
| `try` throws A | `finally` executes `return` | Exception A is masked; method returns |
| `try` throws A | `finally` executes a valid `break` or `continue` | Control flow from `finally` can replace throwing A |

A short rule of thumb: **a pending result from `try/catch` is preserved only if `finally` completes normally**. If `finally` completes abruptly, the new completion reason of `finally` generally wins.

This rule is unrelated to checked vs. unchecked exceptions: A and B can both be `RuntimeException`, or one/both can be checked exceptions. The `throws` obligation changes by exception type, but masking is about **execution flow**.

## 3. Standalone Example: Cleanup Loses the Original Exception

Save the file **`FinallyMasksExceptionDemo.java`**:

```java
public class FinallyMasksExceptionDemo {
    static void perform() {
        try {
            System.out.println("Đang xử lý");
            throw new IllegalArgumentException("Dữ liệu đầu vào sai");
        } finally {
            System.out.println("Đang cleanup");
            throw new IllegalStateException("Không đóng được tài nguyên");
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (RuntimeException e) {
            System.out.println("Caller nhận: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause null: " + (e.getCause() == null));
            System.out.println("Suppressed: " + e.getSuppressed().length);
        }
        System.out.println("Main tiếp tục");
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 --release 17 FinallyMasksExceptionDemo.java
java FinallyMasksExceptionDemo
```

**Exact stdout** when the console displays UTF-8:

```text
Đang xử lý
Đang cleanup
Caller nhận: IllegalStateException
Message: Không đóng được tài nguyên
Cause null: true
Suppressed: 0
Main tiếp tục
```

Step-by-step analysis:

1. The `try` body throws `IllegalArgumentException` with message "Dữ liệu đầu vào sai".
2. Before the exception is propagated out of `perform()`, Java enters `finally`.
3. `finally` throws `IllegalStateException` with message "Không đóng được tài nguyên".
4. `perform()` exits with **`IllegalStateException`**, not the original `IllegalArgumentException`.
5. `getCause() == null` and `getSuppressed().length == 0` because no code linked the two exceptions. **`finally` does not automatically create `cause` or `suppressed`.**

`main` catches `RuntimeException`, so it handles B and continues after the handler. If the caller only wrote `catch (IllegalArgumentException e)`, it would **not** catch B; this can cause the error to propagate farther than expected.

> This is an **intentional anti-example** to expose masking. Do not write cleanup that always throws exceptions like this in real applications.

## 4. If `finally` Throws Nothing, the Original Error Survives

Conversely, if `finally` completes normally, the original exception is not replaced. Standalone program **`FinallyKeepsExceptionDemo.java`**:

```java
public class FinallyKeepsExceptionDemo {
    static void perform() {
        try {
            System.out.println("Work");
            throw new IllegalArgumentException("Lỗi gốc");
        } finally {
            System.out.println("Cleanup hoàn tất");
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (IllegalArgumentException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 FinallyKeepsExceptionDemo.java
java FinallyKeepsExceptionDemo
```

**Exact stdout:**

```text
Work
Cleanup hoàn tất
Caller: Lỗi gốc
```

The outer handler receives the exact `IllegalArgumentException`. The only difference from the previous example is that `finally` **completes normally**.

A deeper note: if `finally` calls a cleanup method and that method silently **swallows the cleanup error** and returns normally, A still propagates to the caller, but B can be lost. This does not mask A, yet it can still cause diagnostics to miss secondary errors. You should have an appropriate policy for recording B.

## 5. When `catch` Rethrows, `finally` Can Still Mask It

Having caught and rethrown A with `throw e;` **does not guarantee the caller receives A** if the subsequent `finally` block throws B.

Example:

```java
try {
    doWork();
} catch (IllegalArgumentException e) {
    System.out.println("Ghi nhận lỗi gốc: " + e.getMessage());
    throw e;
} finally {
    closeResource(); // If this throws B, B can replace A.
}
```

This is **skeleton code**, assuming `doWork()` and `closeResource()` are already defined. The sequence when both operations fail:

```text
doWork()                 → throw A
catch                   → receives A, intends to rethrow A
finally                 → closeResource() throws B
caller                  → receives B
```

`throw e` itself does not create a new exception; it keeps the original reference. However, because `finally` completes abruptly, **the pending rethrow result is replaced**.

In addition, an exception thrown from a **`catch` body** is not tested against subsequent `catch` clauses of the same construct. When `finally` throws B, B looks for a handler in an enclosing construct or caller, not back at sibling handlers inside.

## 6. Not Just `throw`: `return` in `finally` Also Masks Errors

A dangerous mistake is returning from `finally`. It can make a program **return a seemingly successful result even though `try` threw an exception**.

Save `FinallyReturnMaskDemo.java`:

```java
public class FinallyReturnMaskDemo {
    static int maskedFailure() {
        try {
            throw new IllegalArgumentException("Không tính được");
        } finally {
            return 10; // Anti-pattern: swallows the original error!
        }
    }

    static int maskedReturn() {
        try {
            return 20;
        } finally {
            return 30; // Anti-pattern: overrides the return value.
        }
    }

    public static void main(String[] args) {
        System.out.println("Lỗi bị che: " + maskedFailure());
        System.out.println("Return bị ghi đè: " + maskedReturn());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 FinallyReturnMaskDemo.java
java FinallyReturnMaskDemo
```

**Exact stdout:**

```text
Lỗi bị che: 10
Return bị ghi đè: 30
```

In `maskedFailure()`, an `IllegalArgumentException` is genuinely thrown in `try`, yet `finally` returns `10` and **no exception escapes to the caller**. In `maskedReturn()`, `return 30` from `finally` overrides the pending `return 20`.

Java allows this syntax in such methods, but the design is very hard to verify and easily hides failures. Practical rule: **do not `return`, `break`, or `continue` from `finally` unless there is a tightly controlled, special reason**; cleanup should complete normally whenever possible.

## 7. Preferred Solution: `try-with-resources`

Since Java 7, `try-with-resources` manages objects that implement the `AutoCloseable` interface. Resources declared in the `try (...)` header are **attempted to be closed** by Java upon leaving the block, even when an exception occurs.

The biggest difference compared to `finally` manually throwing errors:

- If **the `try` body throws A**, and then `close()` throws B, Java generally keeps **A as the primary exception**.
- **B is attached to A as a suppressed exception**, accessible via `A.getSuppressed()`.
- If the `try` body completes normally but `close()` throws B, **B becomes the primary exception**.
- If multiple resources are declared, Java closes them in **reverse order** of declaration.
- If multiple close errors occur while A is propagating, the close errors are attached in the order they were closed, rather than replacing A.

This preserves evidence of both the primary error and cleanup errors, avoiding the problem where a later error masks an earlier one.

### `cause` vs. `suppressed`

| Property | Common way it is set | Meaning |
| --- | --- | --- |
| `getCause()` | Constructors such as `new IllegalStateException("...", cause)`, or a valid `initCause` | An error that **caused** the current exception when wrapping/translating layers |
| `getSuppressed()` | `try-with-resources` or `addSuppressed` | One or more secondary errors **set aside** to preserve the primary exception |

An exception can have both a `cause` and multiple `suppressed` exceptions. Do not assume every cleanup error is always a cause; in `try-with-resources`, **cleanup errors go into suppressed** if there is already a primary error from the `try` body.

## 8. Runnable Example: Preserving Both Primary and Cleanup Errors

Save the file **`SuppressedCleanupDemo.java`**:

```java
public class SuppressedCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đang đóng tài nguyên");
            throw new IllegalStateException("Đóng thất bại");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Đang xử lý");
            throw new IllegalArgumentException("Dữ liệu sai");
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi chính: " + e.getMessage());
            System.out.println("Số lỗi suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Lỗi phụ: "
                    + e.getSuppressed()[0].getMessage());
            System.out.println("Cause null: " + (e.getCause() == null));
        }
        System.out.println("Main tiếp tục");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

**Exact stdout** when displaying UTF-8:

```text
Đang xử lý
Đang đóng tài nguyên
Lỗi chính: Dữ liệu sai
Số lỗi suppressed: 1
Lỗi phụ: Đóng thất bại
Cause null: true
Main tiếp tục
```

Here, the `try` body throws `IllegalArgumentException` (A). Upon leaving `try`, `close()` is called and throws `IllegalStateException` (B). Java keeps A as the primary exception, while B resides at `A.getSuppressed()[0]`. The handler catching A still works; the caller is not unexpectedly switched to handling B.

The output `Cause null: true` shows that no `cause` chain was set; the relationship between A and B is stored in **suppressed**, not `getCause()`.

The example assumes there is always one suppressed exception to demonstrate accessing `[0]`; in real code, **check the array length before indexing** and do not assume every exception has suppressed exceptions.

## 9. Multiple Resources: Reverse-Order Closing and Retaining All Close Errors

When declaring multiple resources, each successfully initialized resource is closed from right to left. If the `try` body already threw a primary exception, exceptions thrown by `close()` are added to the primary exception's suppressed list.

Save **`MultipleCleanupDemo.java`**:

```java
public class MultipleCleanupDemo {
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
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi xử lý");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
            for (Throwable t : e.getSuppressed()) {
                System.out.println("Phụ: " + t.getMessage());
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 MultipleCleanupDemo.java
java MultipleCleanupDemo
```

**Exact stdout:**

```text
Mở A
Mở B
Trong try
Đóng B
Đóng A
Chính: Lỗi xử lý
Suppressed: 2
Phụ: Lỗi đóng B
Phụ: Lỗi đóng A
```

Resource B is closed before A, so the suppressed order is also B's close error first, followed by A's close error. **Not only the last resource is closed**: Java still attempts to close the remaining successfully initialized resources even when one close operation throws an exception.

This is a major advantage of `try-with-resources` over manual cleanup without an explicit policy: close errors do not force the program to lose the primary cause or skip other resources.

## 10. When Cleanup Is the Only Failure, It Becomes the Primary Error

`try-with-resources` does not make close errors disappear. If the `try` body completes normally but `close()` fails, then **the cleanup error is the primary error of the entire statement**.

Save **`OnlyCleanupFailsDemo.java`**:

```java
public class OnlyCleanupFailsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đang đóng");
            throw new IllegalStateException("Lỗi cleanup");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Work thành công");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 OnlyCleanupFailsDemo.java
java OnlyCleanupFailsDemo
```

**Exact stdout:**

```text
Work thành công
Đang đóng
Bắt: Lỗi cleanup
Suppressed: 0
```

The `try` body finished running, but **the entire `try-with-resources` statement did not complete normally** because `close()` failed. B becomes the primary exception, and there is no prior primary error to attach suppressed exceptions to. You should not report the overall operation as successful if the contract requires closing/flushing to succeed before confirmation.

## 11. Resource Initialization Errors Must Also Be Preserved

`try-with-resources` also handles the case where one resource opens successfully, but **initializing the next resource** fails. Java attempts to close the already-opened resources, and if closing raises an error, that error can be attached to the primary exception thrown during initialization.

Standalone example **`InitializationCleanupDemo.java`**:

```java
public class InitializationCleanupDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
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
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Không tới thân try");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Phụ: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 InitializationCleanupDemo.java
java InitializationCleanupDemo
```

**Exact stdout:**

```text
Mở A
Mở B
Đóng A
Chính: Không tạo được B
Phụ: Không đóng được A
```

Resource A initialized successfully. B's constructor threw an exception before B became a successfully managed resource, so Java **does not call `close()` on B** in this construct; A is closed, and A's close error is attached as suppressed to B's initialization error.

This is an important reason to avoid writing long manual open/close resource chains with `finally`: mid-way failure paths easily miss cleanup or accidentally mask the first exception.

## 12. A Practical Example with File I/O

Objects returned by `Files.newBufferedReader` implement `AutoCloseable`, so Java can manage closing the resource through `try-with-resources`.

Example **illustrative method** (no `main` yet, and depends on actual file contents):

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigReader {
    static String firstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

This construct guarantees Java **attempts to call `reader.close()`** upon leaving the block, even if `readLine()` throws `IOException`. If both reading and closing throw exceptions, the close error will be in `getSuppressed()` of the primary read error.

Calling it requires running inside a program with a valid path; because output depends on the environment/file, this example **does not publish a fixed stdout**. `readLine()` can return `null` when reaching end-of-stream, which does not mean an exception occurred.

Avoid the pattern "open reader → call `readLine` → call `close` at the end of the method" without structured cleanup: if `readLine` throws an error, the plain `close` line at the end will be skipped.

## 13. Why Doesn't Java Automatically Convert It to `getCause()`?

If `finally` throws B while A is pending, Java **does not automatically** call `B.initCause(A)` or `B.addSuppressed(A)`. Only code or constructs designed to link exceptions create that relationship.

There are three different models:

| Model | Which primary exception does the caller see? | Where is the remaining error? |
| --- | --- | --- |
| `try` throws A, `finally` throws B (unhandled) | B | A can be lost from the thrown result |
| `try` throws A, `catch` throws `new ServiceException("...", A)` | New wrapper exception | `getCause()` returns A |
| `try-with-resources`: body throws A, `close` throws B | A | `A.getSuppressed()` contains B |

A wrapped exception (*wrapping*) and an attached exception (*suppressed*) both provide diagnostic information, but their relationships differ. **Cause** describes the chain of reasons leading to a higher-level error; **suppressed** typically stores secondary failures that occurred while handling the primary error.

When using `Throwable.printStackTrace()`, Java typically displays a `Suppressed:` section for suppressed exceptions and a `Caused by:` section for causes. Do not rely on the exact text or line numbers of a stack trace as a stable contract; for structured handling, use `getCause()`, `getSuppressed()`, and the actual exception types.

## 14. When You Must Use Manual `finally`: Intentionally Preserve the Primary Exception

Not every legacy resource implements `AutoCloseable`. When forced to perform manual cleanup, you need a policy that **does not overwrite A with B**. One option is to catch the cleanup error and attach it to the primary exception being thrown.

Example **illustrating only the case where both operations declare `IOException`**:

```java
import java.io.IOException;

class LegacyCleanup {
    static void work() throws IOException {
        throw new IOException("Work failed");
    }

    static void cleanup() throws IOException {
        throw new IOException("Cleanup failed");
    }

    static void run() throws IOException {
        IOException primary = null;
        try {
            work();
        } catch (IOException e) {
            primary = e;
            throw e;
        } finally {
            try {
                cleanup();
            } catch (IOException closing) {
                if (primary != null) {
                    primary.addSuppressed(closing);
                } else {
                    throw closing;
                }
            }
        }
    }
}
```

This is an **illustrative class without `main`**. When `work()` throws `IOException`, the handler saves A in `primary` and rethrows A. `finally` runs `cleanup()`, catches B, and attaches B to `primary`, then completes normally; therefore **A continues propagating with suppressed B**.

If `work()` completes normally, `primary == null`, and the cleanup error B is thrown as the primary error. This approach avoids losing the original error **within the designed `IOException` scope**. It is **not** a general-purpose cleanup library for every `RuntimeException` or `Error`: if `work()` throws another type that the handler does not catch, a new cleanup exception can still mask that error. You must also consider whether the resource was actually opened and needs cleanup.

Therefore, **prefer `try-with-resources` whenever possible**. If a legacy library does not implement `AutoCloseable`, consider wrapping it in an `AutoCloseable` adapter and using Java's resource-management construct rather than repeatedly hand-writing primary/suppressed preservation logic.

## 15. Using an `AutoCloseable` Adapter for Legacy APIs

Suppose a legacy API only provides a `release()` method without implementing `AutoCloseable`. You can create an adapter:

```java
class LegacySession {
    void doWork() {
        throw new IllegalArgumentException("Work failed");
    }

    void release() {
        throw new IllegalStateException("Release failed");
    }
}

class SessionAdapter implements AutoCloseable {
    private final LegacySession session;

    SessionAdapter(LegacySession session) {
        this.session = session;
    }

    void doWork() {
        session.doWork();
    }

    @Override
    public void close() {
        session.release();
    }
}
```

These are **two illustrative classes**. When used:

```java
try (SessionAdapter resource =
             new SessionAdapter(new LegacySession())) {
    resource.doWork();
}
```

as a **code snippet inside a method**, Java manages the adapter's `close()`. If `doWork` throws `IllegalArgumentException`, and then `release` throws `IllegalStateException`, the first exception remains the primary exception, and the second is attached as suppressed. The adapter encapsulates cleanup responsibility in one place.

Ensure the adapter truly owns the resource and does not mistakenly close a shared object. Do not automatically "adapt" every dependency if the caller does not have the authority to manage the resource's lifecycle.

## 16. Testing Masking and Suppressed Exceptions by Type, Not Stack Trace Strings

A good test should assert **the primary exception's type and message**, as well as **the suppressed list**. Do not merely check that an error appears on the console.

Standalone Java 17 example **`SuppressedAssertionsDemo.java`** requiring no external test libraries:

```java
public class SuppressedAssertionsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("cleanup");
        }
    }

    static void run() {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("work");
        }
    }

    public static void main(String[] args) {
        try {
            run();
            throw new AssertionError("Phải có exception");
        } catch (IllegalArgumentException e) {
            if (!"work".equals(e.getMessage())) {
                throw new AssertionError("Sai lỗi chính");
            }
            Throwable[] other = e.getSuppressed();
            if (other.length != 1
                    || !(other[0] instanceof IllegalStateException)
                    || !"cleanup".equals(other[0].getMessage())) {
                throw new AssertionError("Sai lỗi suppressed");
            }
            System.out.println("PASS: giữ lỗi chính và lỗi cleanup");
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 SuppressedAssertionsDemo.java
java SuppressedAssertionsDemo
```

**Exact stdout:**

```text
PASS: giữ lỗi chính và lỗi cleanup
```

This test actively throws `AssertionError` when the result contradicts expectations, independent of whether the JVM has `-ea` enabled for the `assert` statement. When the exception occurs as designed, the `catch` branch verifies the error data structure and prints a single message.

In real test suites, you can use JUnit's `assertThrows` and assertions on `getSuppressed()`; the logic to verify remains **the right primary exception** and **the cleanup exception not being lost**.

## 17. Mistakes to Avoid

### 17.1. Catching and Completely Swallowing Cleanup Errors

```java
finally {
    try {
        cleanup();
    } catch (Exception ignored) {
        // Loses track of the cleanup failure.
    }
}
```

This is an **illustrative skeleton**, without `cleanup()`. This approach may preserve the propagating A, but **loses B**. If cleanup errors matter for the resource, use a proper logging/recording strategy or suppressed exceptions; do not simply ignore them.

### 17.2. Cleanup in `finally` Throwing a New Exception

If cleanup fails, `finally` can propagate B and mask A. This is the core problem of this lesson; replace it with `try-with-resources` if you have `AutoCloseable` resources.

### 17.3. Using `return` in `finally`

`return` in `finally` can discard both pending errors and pending return values. Avoid using it for business logic or cleanup.

### 17.4. Assuming `try-with-resources` Always Attaches Suppressed Exceptions

If **only `close()` throws an error**, that error is the primary exception, with no prior primary exception to attach suppressed exceptions to. If `close()` succeeds, there are no new suppressed exceptions. Do not access `getSuppressed()[0]` without first checking that the array has elements.

### 17.5. Reading `getCause()` and Forgetting `getSuppressed()`

A main-work error can have its own cause and **simultaneously** have suppressed cleanup exceptions. Following only `cause` can miss resource-related issues.

### 17.6. Logging at Every Layer or Exposing Details

Choose a layer with sufficient context to log the primary exception, cause, and suppressed exceptions. Avoid putting sensitive information such as passwords, tokens, or internal details into messages, and avoid exposing raw stack traces to end users.

### 17.7. Assuming the Error Is Resolved Just Because a Handler Caught It

A handler may catch the primary exception while leaving resources in an inconsistent state. **Preserving error traces is different from restoring application state.** You may need to roll back transactions, cancel requests, close other resources, or mark a job as failed.

### 17.8. Treating `finally` as an Absolute Guarantee

`finally` normally runs when exiting `try`/`catch` via normal or abrupt Java paths. However, forced process termination, severe JVM crashes, or `System.exit` can prevent cleanup. `try-with-resources` also cannot guarantee an external resource actually closed successfully if `close()` failed.

## 18. How to Diagnose an Error with a Cleanup Failure

When a task fails, ask these questions in order:

1. **What exception did the caller receive?** Class name, message, top stack trace.
2. **Did it occur in the main work or in cleanup?** Read the frames and the `try/finally` or `try-with-resources` structure.
3. **Is there a `getCause()`?** Identify the cause chain when exceptions are wrapped.
4. **Is there a `getSuppressed()`?** List and inspect each secondary error, especially when multiple resources are involved.
5. **Is there a `return`, `throw`, or new exception inside `finally`?** These can lose earlier exceptions.
6. **In what order were resources declared/closed?** With `try-with-resources`, closing happens in reverse order; when initialization fails, already-opened resources are attempted to be closed.
7. **Can the failure be reproduced without dangerous side effects?** Use fake resources like in the examples to test the scenario where both work and cleanup fail.
8. **What is the application policy?** When the main operation fails, do not report success just because cleanup completed; when cleanup fails, evaluate resource impact before continuing.

A reliable testing method is to deliberately make **both paths fail**, then verify that the caller receives **A as primary, B as suppressed**. This directly detects masking bugs that tests checking only "throws an exception" often miss.

## 19. Self-Check Questions

**1. The `try` body throws A, and `finally` completes normally. What does the caller receive?**  
The caller receives A (unless an enclosing handler catches or transforms it). `finally` does not lose A on its own if it completes normally.

**2. The `try` body throws A, and `finally` throws B. What does the caller receive?**  
In a standard `try/finally` construct, B becomes the exiting exception; A is masked and is not automatically placed in `cause` or `suppressed`.

**3. `catch` runs `throw e` for A, and `finally` throws B. Does `throw e` guarantee A reaches the caller?**  
No. B can replace A because `finally` completes abruptly.

**4. What happens if `finally` has `return 1` while `try` throws A?**  
`return` from `finally` can mask A and cause the method to return 1. This is an anti-pattern to avoid.

**5. In `try-with-resources`, the body throws A and `close()` throws B. Which error is primary?**  
Generally A remains primary; B is attached as suppressed. You can inspect B via `A.getSuppressed()`.

**6. What if the `try` body succeeds but `close()` throws B?**  
B becomes the primary exception of the `try-with-resources` statement, not a suppressed exception of a nonexistent exception.

**7. Two resources A and B are declared together in `try (A a = ...; B b = ...)`. What is the closing order?**  
B before A. If both `close()` calls fail when the body already threw an exception, the close errors are recorded as suppressed in the order they occurred.

**8. Are `getCause()` and `getSuppressed()` the same?**  
No. Cause expresses the causal relationship of a wrapper exception; suppressed stores retained secondary exceptions, typically from closing resources.

**9. If resource B throws an error in its constructor while A is already open, is A closed?**  
`try-with-resources` attempts to close A. If closing A also throws, the close error is attached as suppressed to B's initialization error.

**10. Does a suppressed cleanup error mean it no longer needs attention?**  
No. Suppressed only preserves diagnostic information and prioritizes the primary error; you must still consider resource state, leaks, data integrity, or side effects.

## 20. Cleanup Design Checklist

Before finalizing Java code that handles resources:

- Does the resource implement `AutoCloseable`? If so, prefer `try-with-resources`.
- Are there failure paths for both the main work **and** cleanup? Have you tested both happening together?
- If using `finally`, could a new `throw` or `return` statement mask a pending exception?
- Does the cleanup code distinguish **primary errors** from **secondary errors**?
- Can the caller read `getSuppressed()` and `getCause()` for full investigation?
- With multiple resources, have you checked creation/closing order and initialization failure handling?
- For checked exceptions, does the `throws` signature match the contract? If closing can throw a checked exception, the caller must handle/declare it appropriately.
- Does a failed resource close affect data consistency or success confirmation?
- Is there any `catch (Exception ignored)` silently discarding an error that should be recorded?
- Do logs have enough context without exposing sensitive data or duplicating noisily at every layer?

## 21. Final Takeaways

**Cleanup exceptions mask the original exception when cleanup code (typically in `finally`) completes abruptly and replaces the failure reason being propagated.** This can cause the caller to receive a resource-closing error instead of the original business or technical error. A `return` in `finally` can even erase the exception signal altogether.

**`try-with-resources` is the preferred approach for `AutoCloseable` resources**: if the main work throws A and closing throws B, Java keeps A as primary and attaches B in `getSuppressed()`; if only closing fails, B is the primary error. Do not confuse suppressed with cause, and do not assume recording both errors automatically recovers the system.

Guiding principle: **preserve the first meaningful root cause, do not let cleanup accidentally overwrite it, still record cleanup failures, and ensure the caller clearly knows whether the operation succeeded or failed.**

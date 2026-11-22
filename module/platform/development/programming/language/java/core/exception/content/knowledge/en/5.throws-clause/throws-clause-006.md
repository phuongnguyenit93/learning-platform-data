# When Should You `catch` and When Should You `throws` in Java?

In Java, when a method can throw an exception, developers often face two choices: **catch it with `catch` at the current layer** or **let the exception propagate to the caller**, declaring `throws` when required. This is a decision about *error-handling responsibility*, not merely a way to make the compiler accept the program.

The foundational principle: **use `catch` where you can actually handle the error meaningfully; if the current layer cannot recover or decide on an appropriate response, let the error propagate according to the contract**. A `catch` block that cannot recover and merely returns a fake value or ignores the exception is often more dangerous than letting a higher layer see the failure.

It is also important to distinguish three things:

1. **Detecting and throwing an error**: internal logic throws an exception object using `throw`, or an API/the JVM raises one automatically.
2. **Declaring propagation capability**: the `throws` clause in a method signature describes the *checked exceptions* that may escape; it does not handle or throw errors by itself.
3. **Catching and handling**: `try/catch` transfers execution flow to a compatible handler when an exception is thrown.

A method can combine these: catch one type of exception to recover, rethrow another, and still declare `throws` for errors it cannot handle.

## 1. Intuitive Example: The Same Failure, Two Layers with Different Responsibilities

Suppose an application needs to load configuration from a file. The file-reading function knows that *reading failed*, but it does not know whether the application is allowed to use a default configuration. Meanwhile, the application startup layer holds the policy: if a required configuration is missing, abort startup; if only an optional setting is missing, use a fallback value.

A low-level reading method might be written as:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class SettingsReader {
    static String read(Path file) throws IOException {
        return Files.readString(file);
    }
}
```

This is an **illustrative class without `main`**; whether reading succeeds depends on the file on disk. `Files.readString` can throw `IOException`, which is a checked exception. `SettingsReader.read` has no policy for using a fallback value, so it declares `throws IOException` to let the caller decide.

If the startup layer has a valid fallback option:

```java
static String resolveOptionalSetting(Path path) {
    try {
        return SettingsReader.read(path);
    } catch (IOException e) {
        return "default";
    }
}
```

This is an **illustrative method**, assuming `SettingsReader` is already declared. It is only correct if the business requirement *allows using `"default"` for every `IOException` from that operation*. If a default is only allowed when the file does not exist, you should not catch all `IOException`s and thereby mask permission, device, or data corruption errors. In that case, you must classify more specifically, such as `NoSuchFileException`, and let other situations propagate.

If the configuration is required, the startup layer can catch the error at the final boundary to print an appropriate message and decide not to continue. The difference lies in **each layer's contract**, not in whether the exception is already "catchable".

## 2. What Does `catch` Solve, and What Does `throws` Solve?

| Perspective | `catch` | `throws` |
| --- | --- | --- |
| Location | Handler block paired with `try` | Method signature |
| Role | Chooses an action when a matching exception occurs | Declares that an exception may propagate to the caller |
| Stops error propagation by itself? | Yes, **if the handler finishes normally** | No |
| Required for checked exceptions? | One option to satisfy `catch-or-declare` | The other option to satisfy `catch-or-declare` |
| Makes the operation succeed by itself? | No; the handler must actually recover or transition to an allowed result | No |
| Can coexist? | Yes: catch one type, then throw another | Yes: declare checked types that still escape |
| Needed for unchecked exceptions? | Not required, but can be caught proactively | Not required, but can be declared for documentation |

The **catch-or-declare** rule applies to checked exceptions: if a checked exception can escape from a method body, the method must **catch or declare** it (or a suitable supertype) according to Java's exception analysis rules. `RuntimeException`, `Error`, and their subclasses are unchecked; callers are not forced by the compiler to catch or declare them.

Example:

```java
import java.io.IOException;

class ChoiceExample {
    static void checkedOperation() throws IOException {
        throw new IOException("Mất kết nối");
    }

    static void propagate() throws IOException {
        checkedOperation(); // Let IOException propagate to the caller.
    }

    static void handleLocally() {
        try {
            checkedOperation();
        } catch (IOException e) {
            System.out.println("Đã ghi nhận: " + e.getMessage());
        }
    }
}
```

This is a valid class without `main`. `propagate()` is required to declare `throws IOException`, while `handleLocally()` does not need to declare it because it catches the error. However, `handleLocally()` only illustrates the syntax: printing a message and returning does not by itself guarantee that the original task succeeded. A real application must determine whether it is allowed to continue after the failure.

## 3. Signs That You Should `catch` Right Here

### 3.1. The Current Layer Has a Safe Recovery Option

If an alternative option is accepted by the contract and you know for sure that the state remains valid, `catch` makes sense. For example, an optional setting can use a default when the file *does not exist*.

It is important to target the catch narrowly enough **not to mask other errors**. You must verify that the fallback is safe, is permitted, and that the data loss that just occurred will not lead to incorrect behavior later.

### 3.2. You Can Prompt the User to Adjust Input

If a user enters `"abc"` into a quantity field, `Integer.parseInt` may throw `NumberFormatException`. The input-receiving layer can catch the error and return a validation message, because this layer knows the UI and how to handle it.

```java
static String validateQuantity(String input) {
    try {
        int quantity = Integer.parseInt(input);
        return quantity > 0 ? "Hợp lệ" : "Phải lớn hơn 0";
    } catch (NumberFormatException e) {
        return "Phải nhập số nguyên";
    }
}
```

This is an **illustrative method**, without `main`. Catching at the input boundary is appropriate because a valid result or a rejection reason is a normal part of the contract. You should not let raw input errors automatically travel through multiple layers and turn into a "server error" if the boundary already has enough information to interpret them.

### 3.3. An Application Boundary Must Translate Errors into a Response

In a CLI, the outer boundary may print a message and exit with an appropriate exit code. With HTTP, the transport layer may translate application exceptions/results into responses according to the API contract. For a background job, the orchestration layer may mark the job as failed and apply a defined retry policy.

This is usually **where the final reaction is known**. For example, `400 Bad Request` or `500 Internal Server Error` are HTTP protocol choices, not two Java exception types. Do not map every `IllegalArgumentException` to 400, because it can sometimes indicate a bug in internal data; you must consider the error source and the contract.

### 3.4. You Must Perform a Meaningful Action Before Deciding Again

A handler can record a failed step, undo local changes, or add context. Afterward, it can rethrow with `throw e` if the current layer cannot recover. Thus, **catching an error does not necessarily mean swallowing it**.

```java
try {
    operation();
} catch (IOException e) {
    recordFailedAttempt(e);
    throw e;
}
```

This is an **illustrative code skeleton**, assuming the helper methods are defined and the enclosing method allows `IOException` to propagate. The work of `recordFailedAttempt` must itself be safe and must not silently replace the original error; if it throws a new exception, the caller may see the new error instead of the original one.

## 4. Signs That You Should Continue to `throws`

### 4.1. Lack of Information to Decide How to Recover

A data storage library does not know whether to show a dialog, switch to a backup file, return an HTTP status code, or terminate the program. If there is no way to handle the error while preserving the contract, let `IOException` or the appropriate exception propagate to the caller.

Do not do this:

```java
// Anti-pattern: returning fake data when reading fails.
static String unsafeRead(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        return ""; // Cannot distinguish an empty file from a read error.
    }
}
```

This is an illustrative method, requiring imports for `Files`, `Path`, and `IOException`. An empty string is only appropriate if it is genuinely defined as a safe fallback in all cases. Otherwise, this pattern misleads the calling layer into thinking the operation succeeded.

### 4.2. The API Contract Already Publishes Checked Exceptions

A method `readFile() throws IOException` can preserve its contract across intermediate forwarding layers. A higher calling layer knows how to handle I/O errors, such as closing a session, switching files, or canceling the feature.

Note that `throws` does not *alter* or catch the exception. It only clarifies the contract that Java checks at compile time for checked exceptions. If the exception has no matching handler anywhere on the call stack, it can still escape the running thread and cause the operation to fail.

### 4.3. The Error Arises from an Invariant or Precondition That the Current Layer Cannot Fix

If an API detects that a caller passed an invalid argument, `IllegalArgumentException` may be more appropriate than a fake fallback. This is an unchecked exception: **there is no need to write `throws IllegalArgumentException`**; simply letting it propagate is sufficient at the language level.

For example, `Objects.requireNonNull(value)` can throw `NullPointerException` when the argument is `null`. The layer receiving the value should uphold the contract; an intermediate layer should not catch it and "continue as if nothing happened" when required data is missing.

### 4.4. State May Be Corrupted, Requiring Upper Layers to Abort the Entire Operation

Suppose an order-saving feature has written partial data, but the next step fails. The low-level layer must not declare "order created successfully" on its own. It may need to propagate the error so the transaction management layer can decide to roll back or mark an inconsistent state, depending on the actual transaction mechanism implemented.

**Do not assume that `throws` rolls back automatically**. Java exceptions do not automatically undo file changes, database writes, or network calls. Rollback is a transaction mechanism or compensating code built separately into the system.

## 5. Quick Decision Flowchart

For a specific exception, answer in order:

1. **Is this an expected business branch?** If it is a routine "out of stock" or "not found" case, consider returning an explicit result type; you do not necessarily need exceptions for control flow.
2. **Does the current layer have a verifiable recovery option?** If yes, `catch` the exact type and execute that option.
3. **Is this layer responsible for producing a response for the user or calling system?** If yes, catch and translate it into the appropriate response or failure state.
4. **Can this layer only add context without recovering?** You can catch to log/clean up and then `throw e`, or wrap with a cause if the new layer's contract requires it.
5. **Can it do nothing useful?** Do not add a redundant `catch`; let the exception propagate to the caller and declare checked exceptions if needed.
6. **Is the exception in the serious `Error` branch?** Normal business code should not swallow errors to try to keep running normally; prioritize investigating the environment/JVM root cause and operational policy.

Put concisely in a design context: **use `catch` to decide on a valid action; use `throws` to keep handling responsibility with the caller**. Choose based on handling capability, not just to get rid of red squiggles in the IDE.

## 6. Runnable Program: `catch` When There Is a Fallback, `throws` When There Is Not

To avoid depending on an external file system, the following example simulates an I/O operation using `IOException`. Save the whole file as **`CatchOrThrowsDemo.java`**:

```java
import java.io.IOException;

public class CatchOrThrowsDemo {
    static String loadPrimary(boolean available) throws IOException {
        if (!available) {
            throw new IOException("Nguồn chính không sẵn sàng");
        }
        return "primary-config";
    }

    // Policy unknown: keep IOException for the caller.
    static String loadRequired(boolean available) throws IOException {
        return loadPrimary(available);
    }

    // Fallback is known to be allowed: catch and use backup data.
    static String loadOptional(boolean available) {
        try {
            return loadPrimary(available);
        } catch (IOException e) {
            return "default-config";
        }
    }

    public static void main(String[] args) {
        System.out.println("Tùy chọn: " + loadOptional(false));
        System.out.println("Bắt buộc: " + loadOptional(true));

        try {
            System.out.println(loadRequired(false));
        } catch (IOException e) {
            System.out.println("Không thể khởi động: " + e.getMessage());
        }

        System.out.println("Main đã xử lý xong");
    }
}
```

Compile/run on Java 17+:

```bash
javac -encoding UTF-8 --release 17 CatchOrThrowsDemo.java
java CatchOrThrowsDemo
```

**Exact stdout** when displayed with UTF-8:

```text
Tùy chọn: default-config
Bắt buộc: primary-config
Không thể khởi động: Nguồn chính không sẵn sàng
Main đã xử lý xong
```

In `loadOptional(false)`, the fallback is part of the contract, so the current layer proactively `catch`es and returns `"default-config"`. In `loadRequired(false)`, the intermediate layer is only responsible for loading data, so it `throws IOException` and the caller in `main` handles it.

The labels on the first two lines are only for illustrating the printed output: the line `"Bắt buộc: primary-config"` calls `loadOptional(true)` to show a successful read path that can be compared with the fallback. The actual decision for required configuration happens in the subsequent `loadRequired(false)` call.

Simulating with `IOException` serves the lesson on control flow; the program does not touch real files or connections, so the output can be verified deterministically.

## 7. Narrow `catch` to Avoid Masking Other Failures

An API can throw multiple exceptions in the same hierarchy. For instance, reading a file with `Files.readString` can throw `NoSuchFileException` when the file does not exist, or other `IOException`s when the operation fails due to permissions or device issues.

If only **a missing file** is allowed to fall back, you must handle it narrowly:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

class OptionalFileConfig {
    static String read(Path path) throws IOException {
        try {
            return Files.readString(path);
        } catch (NoSuchFileException e) {
            return "default";
        }
    }
}
```

This is an **illustrative class without `main`**. When an exact `NoSuchFileException` occurs, this layer uses the fallback; other `IOException`s continue to be declared with `throws IOException`. This distinguishes an expected branch from technical errors that the code lacks enough information to fix.

Note: a file that exists can still disappear between the check and the read; calling `Files.exists(path)` before reading does not replace exception handling on the actual operation. Avoid assuming that a pre-check eliminates all I/O errors.

### Ordering of `catch` Clauses

When multiple handlers have an inheritance relationship, the more specific branch must come first:

```java
try {
    readSomething();
} catch (NoSuchFileException e) {
    useFallback();
} catch (IOException e) {
    reportIoFailure(e);
}
```

This is an illustrative skeleton. If `IOException` is placed first, the `NoSuchFileException` handler after it becomes unreachable because the superclass already catches every instance of the subclass. Java detects this at compile time.

## 8. Catch and Rethrow: `catch` and `throws` Can Appear Together

A method may need to log or add context at the current layer while still propagating a checked exception. Standalone example, saved as **`RethrowDecisionDemo.java`**:

```java
import java.io.IOException;

public class RethrowDecisionDemo {
    static void read() throws IOException {
        throw new IOException("Không đọc được");
    }

    static void service() throws IOException {
        try {
            read();
        } catch (IOException e) {
            System.out.println("Service ghi nhận lỗi");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IOException e) {
            System.out.println("Main xử lý: " + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 RethrowDecisionDemo.java
java RethrowDecisionDemo
```

**Exact stdout:**

```text
Service ghi nhận lỗi
Main xử lý: Không đọc được
```

`service()` has a `catch` to record the error and `throw e` to **rethrow the exact same exception object**, because this layer cannot recover. It must declare `throws IOException` since the checked error continues to escape. `main()` is the final handler that can decide on the response.

If `service()` does not need to record anything, it can be written more concisely:

```java
static void service() throws IOException {
    read();
}
```

This is an **illustrative alternative method**, belonging to the same class as `read()`, not a snippet to append to the existing program. Removing a pointless handler makes the code cleaner.

## 9. When Should You Wrap Instead of `throw e`?

Sometimes an API at another layer should not expose low-level details. For example, a repository layer raises `IOException`, but the service layer wants to expose "cannot load payment information" using a clear application exception type. In that case, you can **wrap the original exception** in a new exception and preserve `cause`.

Illustrative example:

```java
import java.io.IOException;

class PaymentConfigurationException extends RuntimeException {
    PaymentConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class PaymentConfigurationService {
    static String load() {
        try {
            return readFromSource();
        } catch (IOException e) {
            throw new PaymentConfigurationException(
                    "Không thể nạp cấu hình thanh toán", e);
        }
    }

    static String readFromSource() throws IOException {
        throw new IOException("Nguồn cấu hình không truy cập được");
    }
}
```

This is a valid class **without `main`**. `load()` does not declare `throws IOException` because it catches and converts it into a new unchecked exception. The caller receives `PaymentConfigurationException`, while `getCause()` holds the original `IOException`.

Wrapping is a **contract change**, not just "turning off checked exceptions." Use it only if the current layer has a reason to preserve abstraction and the caller has an appropriate handling policy. If the caller still needs to handle `IOException` specifically, continuing with `throws IOException` or a new checked exception type may be more suitable.

Do not write `throw new RuntimeException(e.getMessage())` when root-cause diagnosis is needed, because the message string **does not contain** the full stack trace and original cause. A constructor taking `cause`, such as `new RuntimeException("...", e)`, preserves the trail.

## 10. `throws` Does Not Replace Cleanup

A method with `throws IOException` must still protect the resources it holds. If you open a file, socket, or `AutoCloseable` object and let an exception propagate, the resource is not automatically released just because `throws` is present.

Use `try-with-resources` to close resources when leaving scope, both on the normal completion path and on exception-throwing paths. Specifically, resources are closed in **reverse order of declaration**.

Save the standalone example **`ThrowsResourceDemo.java`**:

```java
import java.io.IOException;

public class ThrowsResourceDemo {
    static class Session implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đã đóng session");
        }
    }

    static void work() throws IOException {
        try (Session session = new Session()) {
            System.out.println("Đang làm việc");
            throw new IOException("Không hoàn tất");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ThrowsResourceDemo.java
java ThrowsResourceDemo
```

**Exact stdout:**

```text
Đang làm việc
Đã đóng session
Caller: Không hoàn tất
```

`work()` does not `catch`, yet it still cleans up via `try-with-resources`. After closing `session`, the exception propagates to the caller. Similarly, if `close()` also throws an exception while the `try` body has already thrown one, the close error can be attached as a **suppressed exception** on the primary exception; the caller can inspect it with `getSuppressed()`.

`finally` can also be used for cleanup, but do not inadvertently place `return` or throw a new error inside `finally`, as they can mask the primary propagating exception. Also, no cleanup is guaranteed to run if the JVM is forcefully terminated or suffers a fatal crash.

## 11. Checked vs. Unchecked Determines Compile-Time Obligation, Not Recoverability

### Checked Exceptions

For example, `IOException` or `SQLException` (when using APIs that can throw them) are checked exceptions. If a method does not handle them, it must declare the corresponding `throws` or a supertype according to Java's rules. This is a **language rule**, not a claim that checked exceptions are always recoverable.

An `IOException` can occur when a core configuration file is corrupted. Even with `throws IOException` declared, an application without a valid fallback must still treat it as an error that terminates the operation.

### Unchecked Exceptions

`IllegalArgumentException`, `NullPointerException`, and `IllegalStateException` are subclasses of `RuntimeException`, so callers are **not required** to use `catch` or `throws`. If you know how to turn a parse error into an input validation message, you can still proactively `catch (NumberFormatException e)`. If it is an API misuse bug, fix the call site rather than swallowing the exception.

`Error` and its subclasses are also unchecked, but they typically represent environment/JVM failures or severe invariant violations; normal business code should not `catch (Throwable e)` just to block all errors and continue.

### Why `throws RuntimeException` Is Rarely Needed

A signature:

```java
static int parse(String text) throws NumberFormatException {
    return Integer.parseInt(text);
}
```

is valid, but `throws NumberFormatException` **does not force the caller to catch** this unchecked type. If you want to clearly document preconditions, you can use JavaDoc `@throws` or contract descriptions; adding `throws` to the signature can help readers notice it, but it does not change compilation rules.

Do not confuse "no `throws`" with "cannot throw any exception": unchecked exceptions can still occur at runtime.

## 12. `throws Exception` and `catch (Exception e)`: Why Be Cautious?

Both of these broad forms are valid in certain situations, but they can obscure error semantics and make it harder for the system to handle failures accurately.

### Declaring Too Broadly

```java
static void loadEverything() throws Exception {
    readConfig();
}
```

This is illustrative code; `readConfig()` needs to be defined. If `IOException` is actually the only checked exception, the signature `throws IOException` gives callers much more useful information. When declaring `throws Exception`, callers must catch/declare a broader checked type, even when the operation currently only uses I/O errors.

In demo applications or at the `main` boundary, broad signatures sometimes speed up prototyping, but public library APIs should expose specific and stable contracts.

### Catching Too Broadly

```java
try {
    execute();
} catch (Exception e) {
    return fallback();
}
```

This is illustrative code, correct only when the API genuinely permits a fallback for **every** subclass of `Exception` that could arise. `catch (Exception e)` includes both checked exceptions and `RuntimeException`, which can mask bugs that the current layer does not know how to fix. It also **does not** catch `Error`.

Broad catching can be reasonable at a final boundary—for example, a framework managing requests/jobs that must record every failure to keep the service loop running. Even then, choosing the response, error reporting, and subsequent state must be explicitly designed rather than silently treating every exception as success.

## 13. Precise Rethrow: Catching Broadly While Keeping `throws` Narrow

Since Java 7, when a `catch` parameter is `final` or **effectively final** (not reassigned), Java can analyze more precisely which checked exceptions a `throw e` statement can actually propagate. Therefore, `catch (Exception e)` followed by `throw e` does not always force you to declare `throws Exception`.

Runnable example, saved as **`PreciseRethrowChoiceDemo.java`**:

```java
import java.io.IOException;

public class PreciseRethrowChoiceDemo {
    static void read() throws IOException {
        throw new IOException("Lỗi khi đọc");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Relay ghi nhận lỗi");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowChoiceDemo.java
java PreciseRethrowChoiceDemo
```

**Exact stdout:**

```text
Relay ghi nhận lỗi
Caller: Lỗi khi đọc
```

Even though the handler declares `catch (Exception e)`, the `relay` method only needs `throws IOException` because the compiler determines the set of checked exceptions that can escape from the `try` block in the example and the variable `e` is not reassigned. If `e` is reassigned inside the handler, type narrowing under the precise rethrow rule may no longer apply, and `throw e` may be checked against the broader declared type.

This is a **compile-time** analysis feature; the exception object thrown at runtime is still the exact same object received by `catch`. You should not use `catch (Exception e)` everywhere just because precise rethrow exists: catching specific types is still clearer and avoids handling an unintended scope.

## 14. Be Careful with `InterruptedException`

`InterruptedException` is a checked exception that appears in operations that can wait or be interrupted, such as `Thread.sleep`. It also carries the meaning of a **cooperative cancellation/termination signal**; handling it is usually different from handling I/O errors.

If the current layer can declare `throws InterruptedException` and the contract allows it, **propagating it** is usually the clearest way to let the caller decide on stopping the operation.

If a boundary cannot declare this checked exception and must catch it, you generally need to **restore the interrupt status** using `Thread.currentThread().interrupt()` before exiting the handler branch, so higher layers can still observe the signal. In Java, many blocking methods clear the thread's interrupt status when throwing `InterruptedException`.

Illustrative method example:

```java
static boolean pause() {
    try {
        Thread.sleep(1000);
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

This is an **illustrative method without `main`**. Here, `false` is an assumed contracted result representing a canceled operation; the caller must understand and handle it. Do not apply this pattern mechanically to every API: in some cases `throws InterruptedException` is better than converting to a boolean, and some boundaries need additional cleanup. Do not automatically use `catch (Exception e)` and accidentally swallow the interrupt signal.

## 15. Translating Errors at Boundaries While Preserving the Cause

Plain Java code does not dictate that an exception must become a specific HTTP status. At a communication boundary or business module boundary, you can translate a lower-layer error into a more meaningful error type while preserving `cause`, or return a result object when the contract defines it as an expected branch.

Notes when translating errors:

- **Preserve semantics:** a database failure is a technical error; do not pretend it is "not found" just because data could not be read.
- **Preserve the cause:** constructors like `new SomeException("...", cause)` preserve the trail and stack trace of the original error in the `getCause()` chain.
- **Do not leak internal details:** stack traces and configuration secrets should not be placed directly into user-facing messages.
- **Avoid duplicate logging at every layer:** choose a place with sufficient context; every layer does not need to print the entire stack trace before rethrowing.
- **Choose the final policy:** aborting a request, marking a job failed, bounded retries, or reporting missing data belongs to the boundary that knows the overall state.

When converting a checked exception to an unchecked wrapper, callers no longer have a compiler-enforced `catch-or-declare` obligation, but **the failure still exists** and the design still needs a final handling point. If a library publishes checked exceptions as an important part of its API, changing exception types can affect callers and tests; consider compatibility.

## 16. Exceptions in `finally` and Masked Errors

A good `catch` or `throws` decision can still fail if cleanup creates a new error and masks the important one.

Skeleton example:

```java
try {
    throw new IllegalArgumentException("Lỗi chính");
} finally {
    throw new IllegalStateException("Lỗi cleanup");
}
```

If this snippet is placed inside a valid method, the final exception propagated out is `IllegalStateException` from `finally`. The primary exception can be lost from the diagnostic path if not saved separately. Therefore:

1. Prefer `try-with-resources` with `AutoCloseable`.
2. Do not write `return` inside `finally`; it can overwrite a pending exception or return value.
3. If cleanup can fail, decide how to preserve the cause and suppressed exceptions.
4. Do not let a cleanup error make the caller believe the main work succeeded.

A sound `throws` choice must be paired with proper resource-management practices; you cannot use a `throws` clause as a substitute for closing files, sockets, or releasing resources.

## 17. Testing Both Decision Branches

Testing exceptions is not just checking that the program "does not crash." You need to verify the **actual contract** at each layer.

| Case to Test | Expected Behavior |
| --- | --- |
| Success path | Method returns the right data; `catch` does not run |
| Error with allowed fallback | `catch` chooses the right fallback; data/side effects remain consistent |
| Error without fallback | Checked exception is declared and propagates to caller; no false success |
| Error of a different type | Narrow handler does not swallow out-of-scope exceptions |
| Handler only logs and rethrows | Caller still receives the right exception or contracted wrapper with cause |
| Resource fails during use | Resource close is attempted; primary/suppressed errors are preserved appropriately |
| Interrupted operation | Interrupt status is handled according to contract |
| Expected business error | Returns domain result or corresponding error code; does not necessarily throw an exception |

A good test also verifies that a broad handler does not turn bugs like `NullPointerException` into seemingly valid fallback values. If a fallback can lose data, alter transactions, or affect security, you must test post-error invariants rather than just checking the return value.

## 18. Common Mistakes

**Mistake 1: Catching everything and ignoring it.**

```java
try {
    save();
} catch (Exception ignored) {
    // Do nothing.
}
```

This is an illustrative skeleton; `save()` is not defined. If `save()` fails, the caller may proceed as if saving succeeded. Only ignore a specific exception when the contract guarantees that ignoring it is truly safe and there is a clear reason.

**Mistake 2: Using `throws Exception` to avoid understanding errors.** Overly broad signatures make it hard for callers to distinguish I/O, data errors, and other conditions. Declare checked types that match the contract when feasible.

**Mistake 3: Using `catch` just to log and rethrow at every layer.** Duplicate log entries make the system harder to observe. Log where it adds diagnostic value or context, and preserve the original exception or a wrapper with `cause`.

**Mistake 4: Using `catch (Exception e)` as a fallback for every situation.** This can mask `RuntimeException`s caused by bugs; not every exception is recoverable.

**Mistake 5: Thinking `throws` will automatically display errors, retry, or roll back.** `throws` is only a declaration; UI, retries, and transactions require separate code and mechanisms.

**Mistake 6: Converting checked to unchecked just to silence compiler errors.** The error does not disappear; only the compiler obligation changes. You need an appropriate API contract and to preserve `cause`.

**Mistake 7: Forgetting to close resources when letting exceptions propagate.** Use `try-with-resources` or proper cleanup to avoid resource leaks.

**Mistake 8: Swallowing `InterruptedException`.** Blocking the interrupt signal can impede task cancellation; propagate it or restore the interrupt status when appropriate.

**Mistake 9: Treating "data not found" as always being an exception.** If this is an expected outcome, `Optional` or a domain result type can express it more clearly.

**Mistake 10: Trying to catch serious `Error`s as business errors.** JVM/system-level errors like `OutOfMemoryError` generally do not allow business layers to continue safely.

## 19. Self-Check Questions

**1. A file-reading function throws `IOException`, and the current layer does not know which configuration to use. Should you `catch` or `throws`?**  
You should let the exception propagate with `throws IOException`, so the policy-aware layer can decide.

**2. The UI layer catches `NumberFormatException` because the user entered letters in a number field. Does it need to continue `throws`?**  
Not necessarily. If the UI layer can return an appropriate validation error, that is a valuable place to `catch`.

**3. A method can throw `IllegalArgumentException` without `throws`. Is that wrong?**  
No. `IllegalArgumentException` is an unchecked exception, so declaring it is not required.

**4. Does `catch (IOException e) { throw e; }` mean the error has been handled?**  
No. The handler only rethrows the error; the enclosing method can still exit abnormally and must declare the checked exception.

**5. When is a fallback dangerous?**  
When it masks a situation that requires an alert, causes data loss, or makes the caller think the operation succeeded despite an invalid state.

**6. Can you both `catch` type A and `throws` type B in the same method?**  
Yes. You can handle some errors and let others continue propagating according to the contract.

**7. If you are using `try-with-resources` and the `try` body throws an exception, does `throws` prevent `close()` from being called?**  
No. Java attempts to close the resource before the exception continues escaping the construct.

**8. Does `throws IOException` automatically retry the I/O operation?**  
No. Retrying requires its own policy and code, especially when the operation has side effects.

**9. If you want to convert `IOException` into `PaymentConfigurationException`, how do you keep the original trail?**  
Create the new exception with the cause: `new PaymentConfigurationException("...", e)` and let the caller access `getCause()`.

**10. Is a broad catch at the final boundary always wrong?**  
No. An orchestration boundary may need to catch broadly to record failures and keep the service loop running; there must be a safe policy and it must avoid turning internal errors into false successes.

## 20. Decision Checklist When Writing Java APIs

Before writing `catch` or `throws`, review:

1. **Error meaning:** does this exception represent an abnormal technical situation, a contract violation, or an expected business outcome?
2. **Where the information lives:** does the current layer have enough knowledge to recover while keeping data, invariants, and side effects valid?
3. **Return contract:** what result does the caller need to know, is there a valid fallback type, or is an `Optional` or `Result` needed?
4. **Error type:** which checked exceptions need to be declared; which unchecked exceptions should propagate or be handled proactively?
5. **`catch` scope:** can you catch a more specific type so you do not swallow other failures?
6. **If rethrowing:** do you preserve the same object with `throw e` or have a reason to wrap with `cause`? Does it add real value before throwing?
7. **Resources:** are files/sockets/sessions closed properly, and can cleanup exceptions mask the primary error?
8. **Cancellation signal:** is there an `InterruptedException` that needs to be propagated or have its interrupt status restored?
9. **Final boundary:** who displays the message, marks a job failed, or decides on retry or rollback?
10. **Testing:** are the success path, valid fallback, error propagation, cleanup, and out-of-scope errors all verified?

## 21. Key Takeaways

**Use `catch` when the current layer has a specific, valid handling action that preserves system state; continue to `throws` when only the caller has enough information or policy to handle it.** Catching to record and then `throw e` is still **error propagation**, and wrapping must preserve `cause` if you want to retain the root cause.

Checked exceptions require code to follow `catch-or-declare`; unchecked exceptions do not carry that compiler obligation, yet still require clear contracts and handling responsibility. `throws` does not fix errors, retry, roll back, or clean up by itself. Understanding where errors are detected, where recovery happens, and where responses are decided makes exception flow accurate, testable, and maintainable.

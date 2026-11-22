# When `Error` Is Thrown and the Appropriate Scope of Handling in Java

In Java, `Error` is a branch of `Throwable` that typically indicates a **serious problem** that most applications **should not try to catch and continue running from as if it were a normal business exception**. For example: the JVM cannot allocate more memory (`OutOfMemoryError`), the call stack is exhausted (`StackOverflowError`), a class cannot be linked with its compiled definition (`LinkageError`), or static class initialization fails (`ExceptionInInitializerError`).

However, two extreme statements should be avoided:

- **“Every `Error` is thrown by the JVM itself and definitely terminates the entire process.”** False. Java code or libraries can also explicitly throw `AssertionError`; an uncaught `Error` usually terminates the **executing thread**, while other threads and the process may continue running.
- **“Since it is a `Throwable`, we can `catch` it and retry/continue normally.”** Also false. Many `Error` types indicate that the execution environment, class linkage, or a critical invariant is no longer reliable. Swallowing the error and continuing can corrupt data or cause harder-to-diagnose failures.

The right approach: **understand the `Error` type, its source, the post-error state, and the management boundary**. In business logic, usually only appropriate `Exception` types should be handled; at a very narrow boundary such as supervising a task/worker, you may **record it or perform minimal cleanup and then rethrow/let it propagate**, rather than promising that the system has recovered.

This Java 17+ lesson explains the `Error` hierarchy, error categories, the relationship with class initialization, `catch` scope, `finally`, `try-with-resources`, multi-threaded behavior, and safe handling practices. All runnable examples **simulate errors safely using `AssertionError`**, without attempting to trigger real `OutOfMemoryError` or `StackOverflowError`.

## 1. Where `Error` Sits in the Exception Hierarchy

Abbreviated hierarchy:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── IOException                         checked
    │   ├── SQLException                        checked
    │   └── java.lang.RuntimeException          unchecked
    │       ├── IllegalArgumentException
    │       └── IllegalStateException
    └── java.lang.Error                         unchecked
        ├── java.lang.VirtualMachineError
        │   ├── OutOfMemoryError
        │   ├── StackOverflowError
        │   └── InternalError
        ├── java.lang.LinkageError
        │   ├── ExceptionInInitializerError
        │   ├── NoClassDefFoundError
        │   ├── NoSuchMethodError
        │   └── UnsupportedClassVersionError
        ├── AssertionError
        └── ThreadDeath
~~~

Key points to remember:

1. `Exception` is **not** a superclass of `Error`; both are direct branches under `Throwable`.
2. `RuntimeException` is also **not** a superclass of `Error`.
3. `Error` and all of its subclasses are treated as **unchecked** by the compiler's exception checking; `throws Error` is not required and callers are not forced to `catch` it.
4. `catch (Exception ex)` **cannot catch** an actual `Error` object.
5. `catch (Throwable t)` can catch `Error` because `Throwable` is the superclass of both `Error` and `Exception`, but that does not make broad catching the right solution.
6. An `Error` is still a `Throwable` object: it has a `message`, `cause`, stack trace, and may have `suppressed exceptions`, depending on the object's type and configuration.

According to the Java SE 17 documentation, `Error` indicates serious problems that a reasonable application should not normally try to catch. This is a **default handling guideline**, not a JVM rule forbidding `catch (Error)`.

## 2. When Can Different Types of `Error` Occur?

| Group/Name | Typical Scenario | Usually Appropriate Response |
| --- | --- | --- |
| `OutOfMemoryError` | The JVM cannot satisfy an allocation request due to memory/related resource limits | Treat as a critical incident; record via out-of-process monitoring, heap analysis, and resource limits |
| `StackOverflowError` | A thread exceeds its stack capacity, usually due to overly deep recursion or infinite recursion | Investigate recursion, base cases, cyclic data structures, and stack configuration; do not simply retry |
| `InternalError` | The JVM reports a serious internal failure | Inspect the JVM, native libraries, and environment; do not handle as validation |
| `LinkageError` | Binary classes/components are incompatible or cannot be linked | Fix dependencies, bytecode, versions, classloaders, or the build/deploy pipeline |
| `NoSuchMethodError` | Runtime cannot find a compatible method referenced by the compiled bytecode | Check for mismatches between compile-time and runtime versions |
| `UnsupportedClassVersionError` | The runtime does not support the version of the loaded class file | Run with a suitable JDK or compile with a compatible `--release` |
| `ExceptionInInitializerError` | Static initialization of a class/interface failed with a `Throwable` that is not an `Error` | Inspect `getCause()` and static initializers/factories; fix configuration or code |
| `NoClassDefFoundError` | The JVM/ClassLoader cannot find/load a required definition, or the class is in an erroneous initialization state | Distinguish a missing class/dependency from an earlier class initialization failure |
| `AssertionError` | An enabled `assert` statement failed or code explicitly executed `throw new AssertionError(...)` | Fix the broken invariant/assumption; usually not treated as a recoverable input error |
| `ThreadDeath` | Legacy scenario related to thread stopping mechanisms | Do not catch/swallow; avoid unsafe thread-stopping mechanisms |

These are **common scenarios**, not a one-to-one mapping for every case. For instance, `NoClassDefFoundError` does not immediately prove that a `.class` file is missing; a class may have **failed initialization earlier**. And `OutOfMemoryError` is not always simply “the heap is full”; the specific message and diagnostic data may point to another resource region.

## 3. How Does a JVM `Error` Differ from a Normal `Exception`?

An `IOException` from a file read operation is a situation the program can anticipate, handle, report to the user, or fall back to another read path if the contract allows. An `IllegalArgumentException` from invalid input can be handled at the validation boundary.

Conversely, if the system encounters `OutOfMemoryError` during processing:

- Even **logging** may require allocating new objects/buffers and continue to fail.
- The state of an in-progress operation may be incomplete; the application may not know whether a transaction committed or not.
- Returning a normal HTTP response may require resources that are no longer available.
- Immediate retry may repeat the error or increase memory pressure.
- One affected thread does not necessarily mean the entire process; however, other threads still running **does not by itself prove the system is healthy**.

Therefore, you should not write a `catch (Throwable)` rule around every business method and continue as if the failed request had recovered. Place **recovery boundaries only where there is sufficient information about state and resource ownership**.

## 4. `Error` Is Unchecked but Can Still Occur at Runtime

A method can throw `AssertionError` without declaring `throws`:

~~~java
static void verify() {
    throw new AssertionError("bất biến bị vi phạm");
}
~~~

Both creating the object and `throw` are valid Java behavior. Callers are not forced by the compiler:

~~~java
try {
    verify();
} catch (AssertionError err) {
    System.out.println(err.getMessage());
}
~~~

**Just because it compiles does not mean you should catch it.** When `AssertionError` signals a broken programming invariant, the reliable response is usually to **stop the unsafe operation, preserve diagnostic information, and fix the bug**. Catching it to demonstrate how the mechanism works can make sense in a learning program or test, but it should not be the default rule in production systems.

Putting `throws Error` in a method signature also does not make the compiler enforce catch-or-declare. `throws` declarations should focus on checked exceptions that callers are obligated to handle.

## 5. Java 17 Example: `catch (Exception)` Does Not Catch `Error`

File `CatchErrorDemo.java`:

~~~java
public class CatchErrorDemo {
    static void validateInvariant() {
        throw new AssertionError("bất biến bị vi phạm");
    }

    public static void main(String[] args) {
        try {
            validateInvariant();
        } catch (Exception ex) {
            System.out.println("Bắt Exception");
        } catch (AssertionError err) {
            System.out.println("Bắt AssertionError: " + err.getMessage());
        }
        System.out.println("Chương trình minh họa tiếp tục");
    }
}
~~~

Run commands:

~~~bash
javac --release 17 -encoding UTF-8 CatchErrorDemo.java
java CatchErrorDemo
~~~

Exact stdout:

~~~text
Bắt AssertionError: bất biến bị vi phạm
Chương trình minh họa tiếp tục
~~~

Explanation:

- `validateInvariant()` throws an **`AssertionError` object**, not an `Exception`.
- `catch (Exception ex)` does not match the runtime type `AssertionError`.
- `catch (AssertionError err)` matches, so the example prints the expected message.
- After `catch`, `main` continues because **the demo program intentionally handled the error and did not rethrow it**.
- Do not infer from this that production code should swallow every `AssertionError`; the example only demonstrates **the hierarchy and `catch` dispatch**.

If you write a `catch (Throwable)`, it can catch `AssertionError`, `OutOfMemoryError`, and `Exception` alike. However, an overly broad clause easily conflates recoverable errors with critical conditions; you must distinguish between **observation** and **recovery**.

## 6. `VirtualMachineError`: Sign of a Critical Execution Condition

`VirtualMachineError` is an `Error` branch for issues indicating that the JVM cannot continue operating normally as requested under certain conditions.

Important examples:

- **`OutOfMemoryError`**: unable to allocate due to resource limits. May require a heap dump or monitoring data configured **before the error occurs**.
- **`StackOverflowError`**: a thread's stack is exhausted, usually from overly deep recursion, an incorrect base case, or cyclic data when using recursion.
- **`InternalError`**: the JVM detected an internal error condition; inspect the message, JVM version, native code, and related diagnostic logs.

Do not intentionally trigger these errors by doing:

~~~java
// DO NOT RUN: illustrates a dangerous anti-pattern.
// while (true) {
//     buffers.add(new byte[100_000_000]); // Attempt to exhaust the heap.
// }
~~~

Or:

~~~java
// DO NOT RUN: intentional infinite recursion.
// static void recurseForever() { recurseForever(); }
~~~

Such experiments can slow down, hang, or exhaust the host machine's resources and are **unnecessary** for learning how `Error` behaves. This lesson uses an intentionally thrown `AssertionError` to demonstrate throwing/catching mechanics without harming resources.

When investigating real-world incidents, collect the Java version, JVM flags, resources, metrics, stack traces, appropriate dumps, and timestamps. Automatically catching and retrying `OutOfMemoryError` on every request rarely has a safe basis.

## 7. `LinkageError`: Binary Compatibility, Classpath, and Classloader Errors

Another important group of `Error` types arises **not from invalid input data**, but because the compiled program and the runtime environment are no longer compatible.

Examples:

- `NoSuchMethodError`: compiled code references a method that is not found in the currently loaded runtime definition.
- `NoSuchFieldError`: same, for a field.
- `IncompatibleClassChangeError`: an incompatible change to a class/interface is detected.
- `UnsupportedClassVersionError`: the current JVM does not support the class file version.
- `VerifyError`: a class file violates verification constraints.
- `NoClassDefFoundError`: a required class definition cannot be found/loaded, or the class has entered an erroneous initialization state.

Real-world scenario example:

~~~text
Compile Module A with newer Library X
                  ↓
Deploy Module A with older Library X
                  ↓
At runtime, call a method only present in the newer version
                  ↓
             NoSuchMethodError
~~~

The usual fix is to **correct the dependency version, classpath/module path, classloader, or build/deployment artifact**, and then redeploy. Catching `NoSuchMethodError` and returning default data can mask a broken deployment and keep the system running in an invalid state.

**Distinguish** `ClassNotFoundException` (a checked exception that may be declared by class-loading/reflective lookup APIs) from `NoClassDefFoundError` (a linkage/runtime error). Although their messages may look similar, they belong to different branches and arise in different circumstances.

## 8. `ExceptionInInitializerError`: An `Error` Tied to Class Initialization

When a class is **initialized for the first time**, Java runs the appropriate **static field initializers** and **static initializer blocks**. If that process completes abruptly with a `Throwable` **that is not an `Error`**, the JVM normally creates an `ExceptionInInitializerError` wrapping that cause.

Example of a static field calling a factory:

~~~java
static final String VALUE = initialize();

static String initialize() {
    throw new IllegalStateException("thiếu cấu hình");
}
~~~

If this method is used as a class initializer, an access that triggers initialization causes `initialize()` to throw `IllegalStateException`. The JVM reflects the class initialization failure with `ExceptionInInitializerError`, whose `getCause()` points to `IllegalStateException`.

**Two layers of information to read:**

1. **The outer `ExceptionInInitializerError`**: the class initialization operation failed.
2. **Its cause**: the actual reason in the initialization code, e.g., `IllegalStateException("thiếu cấu hình")`.

In modern Java versions, prefer `getCause()`. The `ExceptionInInitializerError.getException()` API exists for historical reasons and is still supported, but is unnecessary for most new code.

One special detail: if a static initializer **directly throws an `Error`**, according to the JLS, that `Error` is typically propagated **without being wrapped in `ExceptionInInitializerError`**. Both failure paths can cause the class to be marked unusable for re-initialization within the same classloader context.

## 9. Java 17: First Initialization Attempt and Subsequent Class Usage

File `ClassInitializationErrorDemo.java`:

~~~java
public class ClassInitializationErrorDemo {
    static final class BrokenConfig {
        static final String VALUE = initialize();

        static String initialize() {
            System.out.println("Bắt đầu khởi tạo lớp");
            throw new IllegalStateException("thiếu cấu hình");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(BrokenConfig.VALUE);
            } catch (ExceptionInInitializerError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
                System.out.println("Nguyên nhân: "
                        + err.getCause().getClass().getSimpleName()
                        + " - " + err.getCause().getMessage());
            } catch (NoClassDefFoundError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            }
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 -encoding UTF-8 ClassInitializationErrorDemo.java
java ClassInitializationErrorDemo
~~~

Exact stdout:

~~~text
Bắt đầu khởi tạo lớp
Lần 1: ExceptionInInitializerError
Nguyên nhân: IllegalStateException - thiếu cấu hình
Lần 2: NoClassDefFoundError
~~~

**Detailed explanation:**

- `BrokenConfig.VALUE` is **not a compile-time constant**, because it obtains its value from a method call. Accessing it triggers the initialization of `BrokenConfig`.
- On the first attempt, `initialize()` prints the message and throws `IllegalStateException`.
- The JVM wraps this error in `ExceptionInInitializerError`; `getCause()` preserves the actual error.
- The class is marked **erroneous** in the current class-loading context.
- On the second attempt, the JVM **does not retry running the initializer**; it throws `NoClassDefFoundError` because the class is in an erroneous initialization state.
- There is only one `Bắt đầu khởi tạo lớp` line, showing that the initializer is not re-executed on the subsequent attempt.

**This is why you should not `catch(ExceptionInInitializerError)` and retry `BrokenConfig.VALUE` as a recovery mechanism.** Fixing a configuration file in-process does not automatically reverse a failed class initialization state. Recovery may require resetting the environment/lifecycle or using a controlled new classloader; for typical applications, fixing the bug and restarting the process is the safer path.

`NoClassDefFoundError` can also have other causes (such as a missing dependency), so you must not conclude that every `NoClassDefFoundError` means “initialization previously failed.” Check the logs and the first error.

## 10. What If a Static Initializer Throws an `Error` Directly?

File `DirectErrorInitializerDemo.java`:

~~~java
public class DirectErrorInitializerDemo {
    static final class BrokenPlugin {
        static final Object INSTANCE = create();

        static Object create() {
            System.out.println("Đang khởi tạo plugin");
            throw new AssertionError("hợp đồng plugin sai");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(BrokenPlugin.INSTANCE);
            } catch (AssertionError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            } catch (NoClassDefFoundError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            }
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 DirectErrorInitializerDemo.java
java DirectErrorInitializerDemo
~~~

Exact stdout:

~~~text
Đang khởi tạo plugin
Lần 1: AssertionError
Lần 2: NoClassDefFoundError
~~~

Compared to the previous example:

| Failed Static Initialization Path | First Use | Subsequent Use in the Same Context |
| --- | --- | --- |
| Initializer throws `IllegalStateException` | `ExceptionInInitializerError` with cause `IllegalStateException` | `NoClassDefFoundError` |
| Initializer throws `AssertionError` | The `AssertionError` itself is propagated | `NoClassDefFoundError` |

The JLS has edge-case details, such as failing to allocate a wrapper error object under out-of-memory conditions. The table describes the **normal execution path verified in the example**, not an absolute guarantee for every JVM under all failure conditions.

Scope note: the name `BrokenPlugin` in the example is just a nested class name for illustration and does not require a real plugin system.

## 11. Class Initialization and Object Instantiation Are Two Different Processes

A constructor or instance field initializer can throw `IllegalStateException` when creating an object:

~~~java
class UserSession {
    UserSession() {
        throw new IllegalStateException("phiên không hợp lệ");
    }
}
~~~

If `new UserSession()` fails, that **does not automatically** mean the `UserSession` class is in an erroneous class initialization state. Subsequent constructor calls may still be allowed and may fail again for the same reason.

Conversely, a failure in a **static initializer** can lead to `ExceptionInInitializerError` or propagate an `Error`, after which the class is marked erroneous.

Comparison table:

| Failure Location | Error Callers Typically Observe | Automatically Marks Class as Erroneous? |
| --- | --- | --- |
| Instance constructor body | The exception thrown by the constructor | No, not merely because the constructor failed |
| Instance field initializer | The exception from object creation | No, not merely because an instance initializer failed |
| Static field initializer | May be `ExceptionInInitializerError` or an original `Error` | Yes, if class initialization completes abruptly |
| Static initializer block | Similar to static field initializer | Yes |
| Class linking/loading failure | An appropriate `LinkageError` | Depends on the error type and the JVM phase being executed |

A static initializer **cannot let a checked exception escape directly** by declaring `throws` like a constructor. If it calls an API that throws `IOException`, it must handle it or translate it into an unchecked exception per contract; when that unchecked exception escapes during class initialization, it may be wrapped in `ExceptionInInitializerError`.

## 12. `AssertionError` and the `assert` Keyword

`AssertionError` is an `Error` class typically associated with checking **programming invariants**. Java provides the syntax:

~~~java
assert condition : "thông điệp kiểm tra";
~~~

When assertions are **enabled** for the corresponding class, if `condition` is `false`, Java throws `AssertionError`. When assertions are disabled, the `assert` statement does not perform that check.

Therefore, **do not use `assert` for mandatory input validation**, such as verifying passwords, access permissions, monetary amounts, or external data constraints. Those checks must run regardless of whether the JVM has assertions enabled.

For API preconditions, typically use:

~~~java
static void pay(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount phải dương");
    }
}
~~~

`IllegalArgumentException` is an unchecked type under `RuntimeException` and is suitable for invalid input. An internal invariant bug can be represented with `AssertionError` or another exception per project policy, but it does not replace validation.

Do not place required side effects inside an `assert` expression because the side effects may not occur when assertions are disabled.

## 13. Java 17: Comparing `assert` Enabled and Disabled

File `AssertionsModeDemo.java`:

~~~java
public class AssertionsModeDemo {
    static void check(int value) {
        assert value >= 0 : "giá trị âm";
        System.out.println("Tiếp tục với: " + value);
    }

    public static void main(String[] args) {
        System.out.println("Assertions bật: "
                + AssertionsModeDemo.class.desiredAssertionStatus());
        try {
            check(-1);
        } catch (AssertionError err) {
            System.out.println("AssertionError: " + err.getMessage());
        }
    }
}
~~~

Compile once:

~~~bash
javac --release 17 -encoding UTF-8 AssertionsModeDemo.java
~~~

Run with assertions **disabled**:

~~~bash
java -da AssertionsModeDemo
~~~

Stdout:

~~~text
Assertions bật: false
Tiếp tục với: -1
~~~

Run with assertions **enabled**:

~~~bash
java -ea AssertionsModeDemo
~~~

Stdout:

~~~text
Assertions bật: true
AssertionError: giá trị âm
~~~

`-ea` enables assertions, and `-da` disables them. When running in other environments, assertion settings can be configured per package/class; the example uses explicit flags to keep the output deterministic.

The most important takeaway is that **the same source code may skip running `assert` checks when disabled**. That is why assertions should only be used for appropriate internal assumptions/invariants, not for all mandatory system conditions.

## 14. Appropriate `catch` Scope: Observation, Cleanup, and Recovery

When dealing with `Error`, separate three goals:

| Goal | Can It Be Appropriate? | Caveat |
| --- | --- | --- |
| **Observation**: recording the type, stack trace, metrics, task status | Yes, at a very clear boundary; prefer reliable monitoring mechanisms | Logging may fail when out of memory or resources |
| **Cleanup**: releasing resources in `finally` or `try-with-resources` | Usually appropriate during normal Java abrupt completion | Not guaranteed if the JVM/process is forcefully terminated, `Runtime.halt` is called, or a critical error prevents the process from continuing |
| **Recovery**: swallowing `Error` and letting the request/worker continue as if nothing happened | Usually not recommended | Only consider for errors designed with a clear boundary where state validity is proven |

Do not confuse **being able to catch an `Error`** with **having fixed the root cause**. For example, a `NoSuchMethodError` caused by a version-mismatched deployment is not fixed by a `catch (NoSuchMethodError)` block.

Most business code should only catch specific `Exception` types it can handle. In a task coordinator, if recording critical failures is truly needed, an out-of-thread/out-of-process monitoring layer may be used; resource recovery or retries must be evaluated separately based on the error type and system state.

## 15. `finally` and `try-with-resources` When an `Error` Is Thrown

When Java performs normal abrupt completion due to an `Error`, language-level cleanup mechanisms can still execute:

~~~java
try {
    throw new AssertionError("sự cố");
} finally {
    System.out.println("Cleanup trong finally");
}
~~~

Normally, the line in `finally` runs **before `AssertionError` continues propagating**. This does not mean you should catch Error.

Similarly, `try-with-resources` invokes `close()` on exit, even when the body throws an `Error`. If `close()` also throws an exception, the closing exception may be attached as a **suppressed** exception on the primary `Error`.

One detail to note when writing examples: if `close()` declares `throws IOException`, the compiler still checks **checked exceptions from the implicit call to `close()`**. Even if the example body intentionally throws `AssertionError`, you still need to catch or declare the `IOException` that could arise from cleanup.

## 16. Java 17: An `Error` Can Still Receive a Suppressed Exception from Cleanup

File `ErrorCleanupDemo.java`:

~~~java
import java.io.IOException;

public class ErrorCleanupDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("không đóng được");
        }
    }

    public static void main(String[] args) throws IOException {
        try (Resource ignored = new Resource()) {
            throw new AssertionError("lỗi kiểm tra");
        } catch (AssertionError err) {
            System.out.println("Error chính: " + err.getMessage());
            System.out.println("Số suppressed: " + err.getSuppressed().length);
            System.out.println("Suppressed: "
                    + err.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("Finally chạy");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 ErrorCleanupDemo.java
java ErrorCleanupDemo
~~~

Exact stdout:

~~~text
Đóng tài nguyên
Error chính: lỗi kiểm tra
Số suppressed: 1
Suppressed: không đóng được
Finally chạy
~~~

Explanation:

1. The `try` body throws `AssertionError`.
2. Java automatically calls `Resource.close()`; the method prints `Đóng tài nguyên` and throws `IOException`.
3. `AssertionError` remains the primary error; the `IOException` from cleanup is added as a **suppressed exception**.
4. The example's `catch (AssertionError)` prints the primary and secondary errors, and `finally` prints the completion message.
5. `main` declares `throws IOException` to satisfy the checked exception check for `close()`. This specific runtime path still keeps `AssertionError` as the primary error and does not let `IOException` escape independently.
6. In general code, you must check the length of `getSuppressed()` before accessing `[0]`; this fixed example knows there is exactly one closing error.

The example only simulates an intentionally thrown `AssertionError`. It **does not prove** that every catastrophic JVM error will let `finally` complete. If the JVM crashes or the process is `kill`ed or `Runtime.halt` is called, Java makes no guarantee that cleanup will execute.

## 17. Does an `Error` in a Worker Thread Necessarily Kill the Entire JVM?

No. When an uncaught `Throwable` escapes the entry point of **one thread**, that thread may terminate and the **uncaught exception handling** mechanism may receive the error information. Other threads may keep running, depending on the program architecture.

Simple worker-thread demo, without triggering a real JVM error.

File `WorkerThreadErrorDemo.java`:

~~~java
public class WorkerThreadErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("worker thất bại"); },
                "worker-demo");

        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("Uncaught tại " + thread.getName()
                        + ": " + error.getClass().getSimpleName()));

        worker.start();
        worker.join();
        System.out.println("Main tiếp tục");
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 WorkerThreadErrorDemo.java
java WorkerThreadErrorDemo
~~~

Exact stdout:

~~~text
Uncaught tại worker-demo: AssertionError
Main tiếp tục
~~~

This only proves: **an uncaught `AssertionError` in a worker can terminate the worker thread, invoke the handler, and still let the main thread continue**.

You must not infer that if the main thread is still alive, the system can always recover. The worker might have been holding a lock, mutating state halfway, or leaving a transaction inconsistent; you must analyze task boundaries and state before re-running work.

Nor should `UncaughtExceptionHandler` be used as a place to attempt full recovery after `OutOfMemoryError`. The handler should be minimal and not rely on assuming enough resources remain for complex operations.

## 18. Principles for `catch` in Business Code

Examples should generally follow this pattern:

~~~java
// Illustration in a method that may throw IOException.
try {
    readData();
} catch (java.io.IOException ex) {
    // Handle the I/O condition declared by the contract.
}
~~~

Or for a request boundary that needs to classify multiple recoverable errors:

~~~java
try {
    processRequest();
} catch (IllegalArgumentException ex) {
    // Respond with an input error per the API contract.
} catch (Exception ex) {
    // Record unexpected failure within the Exception branch.
    // Decide whether to return a response or terminate the task based on state.
}
~~~

This is **non-standalone illustrative code**, requiring `readData()` and `processRequest()` to be defined. Key point to remember: the `catch (Exception)` branch **does not include** `Error`. This is usually an advantage because it avoids swallowing critical errors outside normal business scope.

Only add `catch (Error)` or `catch (Throwable)` when there is a specific reason: for example, a **monitoring boundary**, a test framework, or an infrastructure component that needs to minimize information loss and **must have a post-catch policy**. Do not let an HTTP handler arbitrarily turn `OutOfMemoryError` into a normal error code and keep accepting new requests.

## 19. If You Must Observe `Error` at an Infrastructure Boundary

An idea for a very narrow boundary:

~~~java
// ILLUSTRATIVE CODE, not a general recovery policy.
try {
    runWorker();
} catch (Error err) {
    recordCriticalFailureMinimal(err);
    throw err;
}
~~~

`runWorker()` and `recordCriticalFailureMinimal(...)` are system-dependent functions. The logic above **does not swallow the Error**: after recording it, it rethrows so higher layers know the task terminated abnormally.

Warnings:

- `recordCriticalFailureMinimal` can still fail due to out-of-memory or similar errors.
- If recording the error throws a new error, you may accidentally mask the original `Error`. A separate, minimal monitoring path must be designed.
- Catching and rethrowing an `Error` does not automatically roll back transactions or undo side effects.
- In a JVM crash/termination or certain native errors, Java code may have no opportunity to execute the handler.
- If the goal is simply normal resource cleanup, use `finally` or `try-with-resources` instead of a broad catch.

In many applications, **not writing `catch(Error)`** and instead relying on process/container monitoring, controlled restarts, and pre-configured logs/dumps is the more practical and safer choice.

## 20. Can an `Error` Be Wrapped by a Framework?

Some frameworks or APIs do not surface the raw object across all layers. They may wrap `Throwable` or hold it in an async result, depending on the API contract.

For example, `Future`/`Executor` APIs have mechanisms to surface task failures through a result or an `ExecutionException` when calling `Future.get()`; the inner cause may be the original `Error`. This does not turn the `Error` into a recoverable business error.

When analyzing:

1. Check the **outermost type** being caught.
2. Inspect **`getCause()`** (and deeper causes).
3. Check **`getSuppressed()`** if cleanup/close occurred.
4. Cross-reference the stack trace and handling code at the boundary.
5. Do not change your policy simply because there is a wrapper under the `Exception` branch.

For instance, if an `ExecutionException` wraps an `OutOfMemoryError`, the fact that the caller caught `ExecutionException` does not mean it is safe to retry the task. You must evaluate the **actual root cause** and resource state.

## 21. Decision Table: When to Catch, When to Let Propagate?

| Context | Preferred Approach | Explanation |
| --- | --- | --- |
| Invalid request validation | Use/catch an appropriate business exception or `IllegalArgumentException` | Can return a clear response to the caller |
| File/network failure | Handle/wrap `IOException` per contract | Has a documented recovery or error-reporting path |
| `AssertionError` in tests | Test runner/framework may catch to record a failed test | This is a boundary designed to observe test failures |
| `AssertionError` on production invariant | Usually treated as a serious bug; do not swallow | Business state may be untrustworthy |
| `NoSuchMethodError` after deploy | Stop/mark deployment as broken, fix dependencies | Retrying the same code/dependencies will not fix linkage |
| `ExceptionInInitializerError` | Read cause, fix initializer/config; do not blindly retry class | The class may already be marked erroneous |
| `OutOfMemoryError` | Monitoring/heap dump/controlled restart; do not catch broadly | In-process recovery is unreliable |
| `StackOverflowError` | Fix algorithm/recursion, check cyclic data or stack limit | Retrying the same call may immediately reproduce it |
| Worker management boundary | May record minimally, preserve/rethrow, or let uncaught handler receive it | Only recover when state boundaries are proven |
| `finally`/`try-with-resources` | Use for normal cleanup | Does not promise cleanup for every kind of process termination |

This table is a practical guide, not a guarantee that every `Error` renders the system unable to continue. The appropriate handling depends on the error type, software layer, and actual task isolation.

## 22. Common Misconceptions and How to Fix Them

| Misconception | Reality |
| --- | --- |
| `Error` is a subclass of `Exception` | No. They are two separate branches under `Throwable`. |
| `catch(Exception)` handles OOM/StackOverflow too | It cannot catch `OutOfMemoryError`/`StackOverflowError`. |
| `Error` always stops the entire JVM immediately | An uncaught `Error` may only terminate a thread; do not infer whole-process safety. |
| `Error` cannot be created by programmers | Code can `throw new AssertionError(...)` or create other Errors. |
| `Error` must be declared with `throws` | No; `Error` is unchecked. |
| Catching and ignoring `OutOfMemoryError` restores the app to health | There is no such guarantee; it can also corrupt data/state. |
| `NoClassDefFoundError` always means a missing JAR file | It can result from a previous class initialization failure or another linkage issue. |
| `ExceptionInInitializerError` appears after any instance constructor error | It is tied to **static/class initialization**, not every constructor exception. |
| If a static initializer throws `AssertionError`, the JVM always wraps it in `ExceptionInInitializerError` | If the original object is already an `Error`, it is usually propagated directly. |
| After catching `ExceptionInInitializerError`, you can retry the exact same class and succeed | The class may be in an erroneous state; the next attempt usually throws `NoClassDefFoundError`. |
| `finally` definitely runs even if the JVM is killed/halted | There is no guarantee when the process is forcefully stopped or cannot continue. |
| `try-with-resources` does not run `close()` when the body throws an Error | Under normal Java semantics, opened resources are still closed. |
| Every `AssertionError` comes from the `assert` keyword | Code can explicitly throw `new AssertionError` even when assertions are disabled. |
| The `assert` keyword is suitable for validating required input | False, because assertions can be disabled. |
| Logging `ex.getMessage()` is enough | It can lose the stack trace, cause, and suppressed exceptions. |

## 23. Checklist for Investigating an `Error` in a Java Application

1. **Identify the exact class**: `OutOfMemoryError`, `StackOverflowError`, `LinkageError`, `AssertionError`, etc.
2. **Record the message and stack trace** if the environment is still capable; do not parse JVM messages as a stable contract.
3. **Find the cause**: especially `ExceptionInInitializerError.getCause()` and async/framework wrappers.
4. **Check suppressed exceptions** if errors occurred during `try-with-resources` or cleanup.
5. **Determine the timing**: during class loading/linking, static initialization, object creation, request processing, resource closing, or running a background worker?
6. For `LinkageError`, **compare classpath/module path, JDK runtime, JAR dependencies, build versions, and deployment**.
7. For `StackOverflowError`, inspect **recursion, base cases, and data cycles** before increasing stack size.
8. For `OutOfMemoryError`, inspect **heap/native memory, object counts, leaks, caches, request sizes, and container resources** using appropriate monitoring data.
9. For static initialization errors, look at the **first failure** before the class transitioned to the erroneous state.
10. **Verify data/task consistency** before making any retry decision.
11. **Distinguish one thread continuing from a genuinely healthy system**; a living thread is not sufficient proof of recovery.
12. Establish **memory/resource limits, health checks, restarts, and out-of-process monitoring** before incidents occur, rather than expecting code inside `catch (OutOfMemoryError)` to rescue every situation.

Do not intentionally exhaust the heap or run infinite recursion in shared environments to “test Error handling.” Use unit tests simulating `AssertionError` and diagnostic tools designed for isolated test environments if fault-tolerance testing is genuinely needed.

## 24. Self-Check Questions

**Q1.** Does `Error` belong to `Exception`?

**Answer:** No. Both are branches of `Throwable`.

**Q2.** Does `catch (Exception)` catch `OutOfMemoryError`?

**Answer:** No.

**Q3.** Is `Error` checked or unchecked?

**Answer:** Unchecked; Java does not require `throws Error`.

**Q4.** Does `OutOfMemoryError` definitely cause the entire JVM to stop immediately?

**Answer:** You cannot conclude that from the error type alone. Still, it remains a critical condition, and you should not assume the application is safe to continue.

**Q5.** If a static initializer throws `IllegalStateException`, what outermost error may appear?

**Answer:** `ExceptionInInitializerError`, with `getCause()` holding the original exception in the normal case.

**Q6.** Why can a subsequent use of a class after a failed initialization throw `NoClassDefFoundError`?

**Answer:** The JVM marks the class as being in an erroneous initialization state and does not re-run the initializer in that same context.

**Q7.** If a static initializer directly throws `AssertionError`, is it necessarily wrapped in `ExceptionInInitializerError`?

**Answer:** No. The original `Error` is normally propagated directly on the first attempt.

**Q8.** Can the `assert` keyword be used to validate that a monetary amount is positive for every request?

**Answer:** No. Assertions can be disabled; you must use validation that operates independently of the `-ea` flag.

**Q9.** When `try-with-resources` has an `AssertionError` from the body and an `IOException` from `close()`, which error is primary?

**Answer:** Typically `AssertionError` from the body is the primary error, while the `IOException` from closing the resource is attached as suppressed.

**Q10.** Why does `main` in the cleanup example still declare `throws IOException`?

**Answer:** Because the compiler must check the checked exception that `close()` can throw from the implicit cleanup call, even though the fixed runtime path in the example has `AssertionError` as the primary error.

**Q11.** If a worker thread throws an uncaught `AssertionError`, does the main thread necessarily stop too?

**Answer:** No. The worker may terminate, the uncaught handler is invoked, and main continues. However, whether it is safe to keep running still needs evaluation.

**Q12.** Why is `catch (Throwable)` around all business logic an anti-pattern?

**Answer:** Because it lumps together recoverable errors and critical errors where the process may no longer have a trustworthy state; it easily swallows errors and continues in a broken state.

## 25. Official References

- [Java SE 17 API — `Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): meaning of Error, hierarchy, and unchecked status.
- [Java SE 17 API — `VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html), [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html): VM/resource failures.
- [Java SE 17 API — `LinkageError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): linking and class loading errors.
- [Java SE 17 API — `ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): errors occurring during static initialization.
- [Java SE 17 API — `AssertionError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AssertionError.html): assertion check failures.
- [Java Language Specification 17 — §11.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked and unchecked exceptions.
- [Java Language Specification 17 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class initialization procedure, `ExceptionInInitializerError`, and erroneous state.
- [Java Language Specification 17 — §14.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.10): the `assert` statement.
- [Java Language Specification 17 — §14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `try`, `catch`, `finally`, and `try-with-resources`.
- [Java SE 17 API — `Thread.UncaughtExceptionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): observing uncaught errors in a thread.

**Key takeaway:** `Error` is the **unchecked** branch of `Throwable` and usually signals a serious condition outside the recovery scope of normal business code. Some `Error` types come from the JVM, class linking/initialization, or assertion checks; they do not necessarily stop the entire JVM immediately, but **being able to catch them does not mean fixing the error**. Prefer handling `Exception` types with clear contracts, use standard cleanup, preserve cause/suppressed exceptions, and only observe `Error` at narrow boundaries with a safe policy; do not swallow `Error` to continue as if the system were still normal.
